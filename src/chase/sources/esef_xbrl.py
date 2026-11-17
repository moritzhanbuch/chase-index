"""ESEF / UKSEF annual reports from filings.xbrl.org -> company list + computed DPO (proxy).

Run:  python -m chase.sources.esef_xbrl [--max-minutes 35] [--countries ES,FR] [--no-download]

Pipeline (cache-backed, resumable: re-running only downloads what is not cached yet):
1. Filing index: static per-year index files (the method the site asks bulk users to use).
2. Select ONE filing per entity (LEI): the latest period_end; it carries the comparative year too.
3. Download that filing's xBRL-JSON (priority-country order, time-boxed).
4. Extract consolidated facts (facts without any extra dimension) for the latest two fiscal years.
5. Compute DPO = payables / cost x 365 (year-end payables), flag, add provenance, write outputs.

All HTTP goes through chase.common.http (disk cache, >= 1 s between request starts per host).
See docs/sources/esef.md and docs/data_dictionary_esef.md.
"""
from __future__ import annotations

import argparse
import io
import json
import time
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
from datetime import date, datetime, timedelta
from pathlib import Path

import pandas as pd
import yaml

from chase.common import http
from chase.common.http import fetch, now_iso, write_manifest

ROOT = http.ROOT
BASE = "https://filings.xbrl.org"
INDEX_URL = BASE + "/indexes/filings-{year}.json"
INDEX_YEARS = (2023, 2024, 2025, 2026)
MIN_PERIOD_END = "2023-01-01"  # entities whose newest filing is older are treated as stale and skipped
EXCLUDE_COUNTRIES = {"UA"}  # Ukraine Financial Reporting System: different taxonomy, out of scope
PRIORITY_COUNTRIES = ["ES", "DE", "FR", "NL", "IT", "GB", "SE", "DK", "FI", "NO", "BE", "AT", "IE", "PT",
                      "LU", "CH", "PL", "GR"]
FX_PATH = ROOT / "config" / "fx_rates.yaml"
ECB_URL = "https://data-api.ecb.europa.eu/service/data/EXR/A..EUR.SP00.A"
LARGE_CAP_USD = 4e9
SOURCE_TYPE = "esef_xbrl_json"

P = "ifrs-full:"
# Revenue rules in order of preference; a rule with several concepts sums whichever are tagged.
REVENUE_RULES = [
    ("Revenue", ["Revenue"]),
    ("RevenueFromContractsWithCustomers", ["RevenueFromContractsWithCustomers"]),
    ("RevenueFromSaleOfGoods+RevenueFromRenderingOfServices", ["RevenueFromSaleOfGoods", "RevenueFromRenderingOfServices"]),
    ("RevenueAndOperatingIncome", ["RevenueAndOperatingIncome"]),  # includes other operating income
]
# (concept, basis) in order of preference
PAYABLES_CONCEPTS = [
    ("TradeAndOtherCurrentPayablesToTradeSuppliers", "trade"),
    ("CurrentTradePayables", "trade"),
    ("TradeAndOtherPayablesToTradeSuppliers", "trade"),
    ("TradeAndOtherCurrentPayables", "trade_and_other_broad"),
    ("TradeAndOtherPayables", "trade_and_other_broad"),
]
BY_NATURE_COMPONENTS = ["RawMaterialsAndConsumablesUsed", "ServicesExpense", "OtherExpenseByNature"]
# balance-sheet / P&L concepts that only banks and insurers normally tag at consolidated level
FIN_STRONG = ["DepositsFromCustomers", "DepositsFromBanks", "LoansAndAdvancesToCustomers",
              "LoansAndAdvancesToBanks", "InsuranceRevenue", "InsuranceContractsIssuedThatAreLiabilities",
              "LiabilitiesUnderInsuranceContractsAndReinsuranceContractsIssued", "InsuranceServiceResult",
              "InsuranceServiceExpensesFromInsuranceContractsIssued", "InsuranceRevenueOtherAmounts",
              "LiabilitiesDueToCentralBanks"]
FIN_EIR = "InterestRevenueCalculatedUsingEffectiveInterestMethod"
# only decisive when the filer tags no revenue concept at all
FIN_WEAK = [FIN_EIR, "InterestRevenueExpense", "FeeAndCommissionIncome", "RevenueFromInterest"]
REVENUE_ALL = [c for _, cs in REVENUE_RULES for c in cs]


# ----------------------------------------------------------------------------- index

def parse_index(doc: dict) -> list[dict]:
    """Flatten a JSON:API filings document (static index file or /api/filings page)."""
    ents = {e["id"]: e["attributes"] for e in doc.get("included", []) if e.get("type") == "entity"}
    out = []
    for f in doc.get("data", []):
        a = dict(f["attributes"])
        ent = ents.get(f["relationships"]["entity"]["data"]["id"], {})
        a["filing_id"] = f["id"]
        a["lei"] = ent.get("identifier")
        a["name"] = ent.get("name")
        out.append(a)
    return out


def load_index(years=INDEX_YEARS) -> pd.DataFrame:
    rows = []
    for y in years:
        try:
            r = fetch(INDEX_URL.format(year=y), max_age_days=3)
        except Exception as e:  # a year without filings has no file
            print(f"index {y}: {e}")
            continue
        rows += parse_index(r.json())
    return pd.DataFrame(rows)


def select_filings(index: pd.DataFrame, min_period_end: str = MIN_PERIOD_END,
                   max_period_end: str | None = None) -> pd.DataFrame:
    """One filing per LEI: latest period_end; ties -> has json, fewest errors, latest processed.

    A filing with validation errors is only used when no clean filing exists for that same period:
    we never fall back to an older year just to avoid errors (most are minor calc inconsistencies).
    """
    max_period_end = max_period_end or date.today().isoformat()
    df = index[~index["country"].isin(EXCLUDE_COUNTRIES) & index["lei"].notna()].copy()
    countries = df.groupby("lei")["country"].agg(lambda s: ",".join(sorted(set(s))))
    df = df[df["json_url"].notna() & (df["period_end"] >= min_period_end) & (df["period_end"] <= max_period_end)]
    df["_err"] = df["error_count"].fillna(0)
    df = df.sort_values(["lei", "period_end", "_err", "processed"], ascending=[True, False, True, False])
    sel = df.drop_duplicates("lei").drop(columns="_err").reset_index(drop=True)
    sel["countries_filed"] = sel["lei"].map(countries)
    return sel


def download_order(sel: pd.DataFrame, countries: list[str] | None = None) -> pd.DataFrame:
    rank = {c: i for i, c in enumerate(PRIORITY_COUNTRIES)}
    s = sel.copy()
    if countries:
        s = s[s["country"].isin(countries)]
    s["_r"] = s["country"].map(lambda c: rank.get(c, 999))
    return s.sort_values(["_r", "country", "lei"]).drop(columns="_r")


# ----------------------------------------------------------------------------- download

def is_cached(url: str) -> bool:
    k = http._key(url, None)
    return (http.CACHE_DIR / f"{k}.bin").exists() and (http.CACHE_DIR / f"{k}.json").exists()


def download(sel: pd.DataFrame, max_minutes: float, workers: int = 4) -> dict:
    """Warm the cache. The shared client spaces request STARTS >= 1 s apart per host; a few threads
    only let slow multi-MB bodies overlap, they do not raise the request rate."""
    deadline = time.monotonic() + max_minutes * 60
    todo = [BASE + u for u in sel["json_url"] if not is_cached(BASE + u)]
    stats = Counter(already_cached=len(sel) - len(todo))

    def one(url):
        if time.monotonic() > deadline:
            return "skipped_time_budget"
        try:
            fetch(url, retries=2)
            return "downloaded"
        except Exception as e:  # 404s etc: logged in http_log.jsonl by the client
            return f"error:{type(e).__name__}"

    with ThreadPoolExecutor(workers) as ex:
        for i, res in enumerate(ex.map(one, todo)):
            stats[res] += 1
            if i % 100 == 0:
                print(f"  download {i}/{len(todo)} {dict(stats)}", flush=True)
    return dict(stats)


# ----------------------------------------------------------------------------- extraction

def _d(s: str) -> date:
    return datetime.fromisoformat(s).date()


def parse_period(p: str):
    """xBRL-JSON period -> (start_date|None, end_date), both inclusive calendar dates.

    xBRL-JSON writes the end of a day as T00:00:00 of the NEXT day, so an instant
    '2026-02-01T00:00:00' means balance-sheet date 2026-01-31.
    """
    def end_incl(s):
        dt = datetime.fromisoformat(s)
        return (dt - timedelta(days=1)).date() if dt.time() == datetime.min.time() else dt.date()
    if "/" in p:
        a, b = p.split("/")
        return _d(a), end_incl(b)
    return None, end_incl(p)


def consolidated_facts(doc: dict) -> dict:
    """{(concept, start, end, unit): value} for numeric facts with no extra dimensions.

    Duplicates: the most precise (highest `decimals`) wins.
    """
    best: dict = {}
    for f in doc.get("facts", {}).values():
        dims = f.get("dimensions", {})
        if set(dims) - {"concept", "entity", "period", "unit"}:
            continue  # has an explicit/typed dimension member: not the consolidated total
        unit, concept, period = dims.get("unit"), dims.get("concept"), dims.get("period")
        if not unit or not concept or not period or f.get("value") is None:
            continue
        try:
            val = float(f["value"])
        except (TypeError, ValueError):
            continue
        start, end = parse_period(period)
        dec = f.get("decimals")
        prec = dec if isinstance(dec, (int, float)) else 99
        k = (concept, start, end, unit)
        if k not in best or prec > best[k][1]:
            best[k] = (val, prec)
    return {k: v[0] for k, v in best.items()}


def fiscal_years(facts: dict, n: int = 2) -> list[tuple[date, date]]:
    """Latest n full fiscal years (330-400 day duration periods), newest first.

    The reporting year is the ~12-month period carrying the most facts; the comparative is the
    full-year period that ends roughly one year earlier.
    """
    cnt = Counter((s, e) for (_, s, e, _) in facts if s is not None and 330 <= (e - s).days <= 400)
    if not cnt:
        return []
    top = [p for p, _ in cnt.most_common(2)]
    cur = max(top, key=lambda p: p[1])
    out = [cur]
    prior = [p for p in cnt if 330 <= (cur[1] - p[1]).days <= 400]
    if prior and n > 1:
        out.append(max(prior, key=lambda p: cnt[p]))
    return out[:n]


def _get(facts, concept, start, end, unit):
    return facts.get((P + concept, start, end, unit))


def main_currency(facts: dict, fy: tuple[date, date]) -> str | None:
    cnt = Counter(u for (_, s, e, u) in facts
                  if u.startswith("iso4217:") and "/" not in u and ((s, e) == fy or (s is None and e == fy[1])))
    return cnt.most_common(1)[0][0] if cnt else None


def detect_financial(facts: dict) -> bool:
    """Bank / insurer / asset-manager detection. DPO is not meaningful for them.

    True when there is no CostOfSales at all AND one of:
    - a strong bank/insurance concept is tagged together with at least one more marker;
    - a weak marker (net interest income, fee and commission income, interest revenue) is tagged
      and the filer tags no revenue concept at all;
    - effective-interest revenue is at least half of Revenue.
    Industrial groups with a captive bank (they tag CostOfSales) stay non-financial.
    """
    concepts = {c for (c, _, _, _) in facts}
    if P + "CostOfSales" in concepts:
        return False
    strong = sum(P + c in concepts for c in FIN_STRONG)
    weak = sum(P + c in concepts for c in FIN_WEAK if c != "RevenueFromInterest")
    # one stray marker is not enough: brewers tag LoansAndAdvancesToCustomers, builders DepositsFromBanks
    if strong >= 1 and strong + weak >= 2:
        return True
    has_rev = any(P + c in concepts for c in REVENUE_ALL)
    if not has_rev and (strong or any(P + c in concepts for c in FIN_WEAK)):
        return True
    if P + FIN_EIR in concepts:
        rev = max((abs(v) for (c, s, e, u), v in facts.items() if c == P + "Revenue"), default=0)
        intr = max((abs(v) for (c, s, e, u), v in facts.items() if c == P + FIN_EIR), default=0)
        return rev == 0 or intr >= 0.5 * rev
    return False


def compute_dpo(payables, cost):
    if payables is None or cost is None or cost == 0:
        return None
    return round(payables / cost * 365, 1)


def dpo_flag(dpo, is_financial: bool) -> str:
    if is_financial:
        return "not_applicable"
    if dpo is None:
        return "missing_inputs"
    if dpo < 5:
        return "suspicious_low"
    if dpo > 365:
        return "suspicious_high"
    return "ok"


def extract_year(facts: dict, fy: tuple[date, date], unit: str, is_financial: bool) -> dict:
    s, e = fy
    row = {"period_start": s.isoformat(), "period_end": e.isoformat(), "fiscal_year": e.year,
           "currency": unit.split(":")[1] if unit else None}
    # revenue
    row["revenue"], row["revenue_concept"] = None, None
    for label, concepts in REVENUE_RULES:
        vals = [v for v in (_get(facts, c, s, e, unit) for c in concepts) if v is not None]
        if vals:
            row["revenue"], row["revenue_concept"] = sum(abs(v) for v in vals), label
            break
    # cost
    cos = _get(facts, "CostOfSales", s, e, unit)
    comps = {c: _get(facts, c, s, e, unit) for c in BY_NATURE_COMPONENTS}
    row["raw_materials_and_consumables"] = abs(comps["RawMaterialsAndConsumablesUsed"]) if comps["RawMaterialsAndConsumablesUsed"] is not None else None
    row["services_expense"] = abs(comps["ServicesExpense"]) if comps["ServicesExpense"] is not None else None
    row["other_expense_by_nature"] = abs(comps["OtherExpenseByNature"]) if comps["OtherExpenseByNature"] is not None else None
    if cos is not None and cos != 0:
        row["cost"], row["cost_concept"], row["cost_basis"] = abs(cos), "CostOfSales", "cost_of_sales"
    elif comps["RawMaterialsAndConsumablesUsed"] is not None or comps["ServicesExpense"] is not None:
        used = [c for c in BY_NATURE_COMPONENTS if comps[c] is not None]
        row["cost"] = sum(abs(comps[c]) for c in used)
        row["cost_concept"], row["cost_basis"] = "+".join(used), "by_nature_fallback"
    else:
        row["cost"], row["cost_concept"], row["cost_basis"] = None, None, "missing"
    # payables (instant at fiscal year end)
    row["payables"], row["payables_concept"], row["payables_basis"] = None, None, None
    for c, basis in PAYABLES_CONCEPTS:
        v = _get(facts, c, None, e, unit)
        if v is not None and v != 0:
            row["payables"], row["payables_concept"], row["payables_basis"] = abs(v), c, basis
            break
    row["dpo"] = None if is_financial else compute_dpo(row["payables"], row["cost"])
    row["dpo_flag"] = dpo_flag(row["dpo"], is_financial)
    standard = row["cost_basis"] == "cost_of_sales" and row["payables_basis"] == "trade"
    row["confidence"] = 1.0 if standard else 0.7
    return row


def extract_filing(doc: dict) -> dict:
    """-> {"is_financial": bool, "years": [row newest first], "note": str|None}"""
    facts = consolidated_facts(doc)
    fin = detect_financial(facts)
    fys = fiscal_years(facts)
    if not fys:
        return {"is_financial": fin, "years": [], "note": "no_full_fiscal_year_period_found"}
    unit = main_currency(facts, fys[0])
    if not unit:
        return {"is_financial": fin, "years": [], "note": "no_monetary_unit_found"}
    return {"is_financial": fin, "years": [extract_year(facts, fy, unit, fin) for fy in fys], "note": None}


# ----------------------------------------------------------------------------- FX

def load_fx() -> dict:
    """{year: {CUR: usd_per_unit}} from config/fx_rates.yaml; created from ECB annual averages if absent."""
    cfg = yaml.safe_load(FX_PATH.read_text()) if FX_PATH.exists() else None
    if cfg and cfg.get("usd_per_unit"):
        t = cfg["usd_per_unit"]
        if all(isinstance(v, dict) for v in t.values()):  # {year: {CUR: rate}}
            return {int(y): {k: float(v) for k, v in d.items()} for y, d in t.items()}
        # flat {CUR: rate} file (shared project config, one approximate rate for all years): key 0
        return {0: {k: float(v) for k, v in t.items()}}
    r = fetch(ECB_URL, params={"format": "csvdata", "startPeriod": "2022"})
    d = pd.read_csv(io.BytesIO(r.content))
    table: dict = {}
    for y, g in d.groupby("TIME_PERIOD"):
        per_eur = dict(zip(g["CURRENCY"], g["OBS_VALUE"]))
        usd = per_eur.get("USD")
        if not usd:
            continue
        table[int(y)] = {"EUR": round(float(usd), 6), "USD": 1.0,
                         **{c: round(float(usd / v), 6) for c, v in per_eur.items() if c != "USD" and v == v}}
    out = dict(cfg or {})
    out.update({
        "description": "USD per 1 unit of currency, annual average. Rough conversion for size thresholds only.",
        "source": "ECB euro foreign exchange reference rates, annual averages (EXR A.*.EUR.SP00.A), crossed via EUR/USD",
        "source_url": ECB_URL + "?format=csvdata&startPeriod=2022",
        "retrieved_at": r.retrieved_at,
        "fallback_rule": "fiscal years ending in a year without a published annual average use the latest available year",
        "usd_per_unit": table,
    })
    FX_PATH.parent.mkdir(parents=True, exist_ok=True)
    FX_PATH.write_text(yaml.safe_dump(out, sort_keys=True, allow_unicode=True))
    return table


def to_usd(value, currency, year, fx: dict):
    """-> (usd, fx_year) or (None, None). Falls back to the latest year with a rate."""
    if value is None or currency is None or not fx:
        return None, None
    years = sorted(fx)
    y = year if year in fx else max([k for k in years if k <= year] or years)
    rate = fx[y].get(currency)
    if rate is None:
        return None, None
    return value * rate, (y or None)  # None = flat all-years approximate rate


# ----------------------------------------------------------------------------- build

def build(sel: pd.DataFrame, fx: dict) -> tuple[pd.DataFrame, pd.DataFrame, Counter]:
    comp_rows, dpo_rows, stats = [], [], Counter()
    for f in sel.itertuples():
        url = BASE + f.json_url
        if not is_cached(url):
            stats["not_downloaded"] += 1
            continue
        r = fetch(url)
        try:
            ex = extract_filing(r.json())
        except Exception as e:
            stats["parse_error"] += 1
            ex = {"is_financial": None, "years": [], "note": f"parse_error:{type(e).__name__}"}
        human = f.viewer_url or f.report_url
        prov = {"source_url": url, "report_url": BASE + human if human else None, "source_type": SOURCE_TYPE,
                "retrieved_at": r.retrieved_at, "extraction_method": "xbrl_json"}
        base = {"lei": f.lei, "name": f.name, "country": f.country, "countries_filed": f.countries_filed,
                "filing_id": f.filing_id, "filing_error_count": f.error_count}
        years = ex["years"]
        stats["processed"] += 1
        for i, y in enumerate(years):
            usd, fxy = to_usd(y["revenue"], y["currency"], y["fiscal_year"], fx)
            dpo_rows.append({**base, **y, "year_rank": i + 1, "revenue_usd": usd, "fx_year": fxy,
                             "is_financial": ex["is_financial"], **prov})
        latest = years[0] if years else {}
        usd, fxy = to_usd(latest.get("revenue"), latest.get("currency"), latest.get("fiscal_year", 0), fx)
        comp_rows.append({
            **base, "fiscal_year_end": latest.get("period_end"), "revenue": latest.get("revenue"),
            "revenue_concept": latest.get("revenue_concept"), "currency": latest.get("currency"),
            "revenue_usd": usd, "fx_year": fxy,
            "large_cap_4b": bool(usd is not None and usd >= LARGE_CAP_USD),
            "is_financial": ex["is_financial"], "latest_dpo": latest.get("dpo"),
            "latest_dpo_flag": latest.get("dpo_flag"), "extraction_note": ex["note"],
            **prov, "period_start": latest.get("period_start"), "period_end": latest.get("period_end"),
            "confidence": 1.0 if latest.get("revenue_concept") == "Revenue" else (0.7 if latest.get("revenue") else None),
        })
    return pd.DataFrame(comp_rows), pd.DataFrame(dpo_rows), stats


def coverage(sel: pd.DataFrame, index: pd.DataFrame, comp: pd.DataFrame, dpo: pd.DataFrame) -> pd.DataFrame:
    idx = index[~index["country"].isin(EXCLUDE_COUNTRIES)]
    c = pd.DataFrame({
        "entities_in_index_any_year": idx.groupby("country")["lei"].nunique(),
        "entities_selected": sel.groupby("country")["lei"].nunique(),
    })
    if len(comp):
        g = comp.groupby("country")
        c["downloaded_and_parsed"] = g["lei"].nunique()
        c["with_revenue"] = g["revenue"].apply(lambda s: s.notna().sum())
        c["financial"] = g["is_financial"].apply(lambda s: (s == True).sum())  # noqa: E712
        c["large_cap_4b"] = g["large_cap_4b"].sum()
        c["with_dpo_latest"] = g["latest_dpo"].apply(lambda s: s.notna().sum())
        big = comp[comp["large_cap_4b"]]
        c["large_cap_with_dpo"] = big.groupby("country")["latest_dpo"].apply(lambda s: s.notna().sum())
    return c.fillna(0).astype(int).sort_values("entities_selected", ascending=False)


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--max-minutes", type=float, default=35)
    ap.add_argument("--countries", default="")
    ap.add_argument("--no-download", action="store_true")
    ap.add_argument("--download-only", action="store_true", help="warm the cache, skip extraction/outputs")
    a = ap.parse_args(argv)
    started = now_iso()
    index = load_index()
    sel = download_order(select_filings(index), [c for c in a.countries.split(",") if c] or None)
    print(f"index rows {len(index)}; selected entities {len(sel)}", flush=True)
    dl = {} if a.no_download else download(sel, a.max_minutes)
    print("download:", dl, flush=True)
    if a.download_only:
        return None, None
    fx = load_fx()
    comp, dpo, stats = build(sel, fx)
    out = ROOT / "data" / "interim"
    out.mkdir(parents=True, exist_ok=True)
    for name, df in (("esef_companies", comp), ("esef_dpo", dpo)):
        df.to_parquet(out / f"{name}.parquet", index=False)
        df.to_csv(out / f"{name}.csv", index=False)
    cov = coverage(sel, index, comp, dpo)
    print(cov.to_string())
    write_manifest("esef_xbrl", {
        "source": BASE, "index_urls": [INDEX_URL.format(year=y) for y in INDEX_YEARS],
        "run_started_at": started, "run_finished_at": now_iso(),
        "selection_rule": f"one filing per LEI, latest period_end between {MIN_PERIOD_END} and run date, with xBRL-JSON; excludes {sorted(EXCLUDE_COUNTRIES)}",
        "download_stats_this_run": dl, "build_stats": dict(stats),
        "entities_selected": int(len(sel)), "companies_rows": int(len(comp)), "dpo_rows": int(len(dpo)),
        "large_cap_4b": int(comp["large_cap_4b"].sum()) if len(comp) else 0,
        "coverage_by_country": cov.reset_index().rename(columns={"index": "country"}).to_dict("records"),
        "not_covered_note": "Germany (DE), Ireland (IE) and Switzerland (CH) have no filings in the index; see docs/sources/esef.md",
        "outputs": ["data/interim/esef_companies.parquet", "data/interim/esef_companies.csv",
                    "data/interim/esef_dpo.parquet", "data/interim/esef_dpo.csv"],
    })
    return comp, dpo


if __name__ == "__main__":
    main()
