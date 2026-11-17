"""SEC EDGAR XBRL: large filers (revenue >= USD 4B) and computed DPO (proxy).

Run:  python -m chase.sources.sec_xbrl

Pipeline
1. Candidate discovery
   a. us-gaap revenue frames (USD, CY2025 + CY2024) -> every CIK with a value >= threshold.
   b. Foreign private issuers: ifrs-full frames are not served for recent years (404, verified
      2026-11-16), so every CIK that filed a 20-F / 40-F in the last five quarterly EDGAR form
      indexes is a candidate and is thresholded from its own companyfacts (with FX conversion).
2. For each candidate: companyfacts JSON -> latest two full fiscal years of revenue, cost of
   sales and year-end trade payables (annual forms only, restatements deduped by latest filed).
3. Threshold on latest-fiscal-year revenue in USD (reported, or converted with
   config/fx_rates_treasury.yaml: US Treasury Reporting Rates of Exchange).
4. Submissions JSON for the survivors: tickers, SIC, addresses.
5. DPO = payables at fiscal year end / cost of sales x 365, with flags.

All HTTP goes through chase.common.http (disk cache, rate limit, compliant User-Agent).
The pure functions (annual facts, dedupe, selection, DPO) have no network dependency and are
unit-tested in tests/test_sec_xbrl.py.
"""
from __future__ import annotations

import re
import sys
from datetime import date
from pathlib import Path

import httpx
import pandas as pd
import yaml

from chase.common.http import ROOT, fetch, fetch_json, now_iso, write_manifest

# ----------------------------------------------------------------------------- config
REVENUE_THRESHOLD_USD = 4e9
MIN_LATEST_FY_END = "2024-07-01"      # older than this = not a live large filer any more
CURRENT_FY_END = "2025-07-01"         # latest FY ending on/after this counts as "current"
FRAME_YEARS = ["CY2025", "CY2024"]
FORM_INDEX_QUARTERS = [(2025, 4), (2026, 1), (2026, 2), (2026, 3), (2026, 4)]
FX_RECORD_DATE = "2025-12-31"

ANNUAL_FORMS = {"10-K", "10-K/A", "10-K405", "20-F", "20-F/A", "40-F", "40-F/A"}
TAXONOMIES = ("us-gaap", "ifrs-full")
MIN_DAYS, MAX_DAYS = 350, 380         # full fiscal year incl. 52/53-week years

# Revenue: the broadest tagged total wins (max over these concepts for the same period).
REVENUE_CONCEPTS = [
    "Revenues",
    "RevenueFromContractWithCustomerExcludingAssessedTax",
    "RevenueFromContractWithCustomerIncludingAssessedTax",
    "SalesRevenueNet",
    "RevenuesNetOfInterestExpense",
    "Revenue",                               # ifrs-full
    "RevenueFromContractsWithCustomers",     # ifrs-full
]
FRAME_REVENUE_CONCEPTS = REVENUE_CONCEPTS[:5]

# Cost of sales: true cost-of-sales concepts; the broadest (max) for the period wins.
COST_CONCEPTS = [
    "CostOfRevenue",
    "CostOfGoodsAndServicesSold",
    "CostOfGoodsSold",
    "CostOfGoodsAndServiceExcludingDepreciationDepletionAndAmortization",
    "CostOfSales",                           # ifrs-full
]
# Fallbacks in priority order (first available). Flagged, confidence 0.7.
COST_FALLBACK_CONCEPTS = ["CostsAndExpenses", "OperatingCostsAndExpenses", "OperatingExpenses",
                          "OperatingExpense"]   # last one is ifrs-full

# Payables: tiers in priority order. Inside a tier the largest value at the fiscal year end wins
# (when a filer tags both AccountsPayableCurrent and AccountsPayableTradeCurrent, one of them is
# usually a sub-detail of the balance sheet line). (basis, note, concepts)
PAYABLES_TIERS = [
    ("trade", None, [
        "AccountsPayableTradeCurrent",
        "AccountsPayableCurrent",
        "TradeAndOtherCurrentPayablesToTradeSuppliers",   # ifrs-full
        "CurrentTradePayables",                           # ifrs-full (rare)
    ]),
    ("trade", "unclassified balance sheet: payables concept covers current and noncurrent", [
        "AccountsPayableTradeCurrentAndNoncurrent",
        "AccountsPayableCurrentAndNoncurrent",
        "TradeAndOtherPayablesToTradeSuppliers",          # ifrs-full
    ]),
    ("trade_and_other_broad", None, [
        "AccountsPayableAndAccruedLiabilitiesCurrent",
        "AccountsPayableAndOtherAccruedLiabilitiesCurrent",
        "TradeAndOtherCurrentPayables",                   # ifrs-full
    ]),
    ("trade_and_other_broad", "unclassified balance sheet: payables concept covers current and noncurrent", [
        "AccountsPayableAndAccruedLiabilitiesCurrentAndNoncurrent",
        "TradeAndOtherPayables",                          # ifrs-full
    ]),
]
MAX_REVENUE_TO_ASSETS = 25  # above this the revenue fact is treated as a filer scale error
PARTIAL_COST_RATIO = 0.05   # cost of sales below 5% of revenue: concept is probably a sub-line

SOURCE_TYPE = "sec_xbrl_companyfacts"
EXTRACTION_METHOD = "xbrl_api"

TICKERS_URL = "https://www.sec.gov/files/company_tickers.json"
FACTS_URL = "https://data.sec.gov/api/xbrl/companyfacts/CIK{cik}.json"
SUBMISSIONS_URL = "https://data.sec.gov/submissions/CIK{cik}.json"
FRAME_URL = "https://data.sec.gov/api/xbrl/frames/{tax}/{concept}/{unit}/{frame}.json"
FORM_INDEX_URL = "https://www.sec.gov/Archives/edgar/full-index/{y}/QTR{q}/form.idx"
FX_URL = ("https://api.fiscaldata.treasury.gov/services/api/fiscal_service/v1/accounting/od/"
          "rates_of_exchange?filter=record_date:eq:{d}&page[size]=400")
FX_PATH = ROOT / "config" / "fx_rates_treasury.yaml"

# ISO 4217 -> label used by the US Treasury "Reporting Rates of Exchange" dataset
FX_TREASURY_LABELS = {
    "EUR": "Euro Zone-Euro", "JPY": "Japan-Yen", "GBP": "United Kingdom-Pound",
    "CNY": "China-Renminbi", "TWD": "Taiwan-Dollar", "KRW": "Korea-Won", "INR": "India-Rupee",
    "BRL": "Brazil-Real", "MXN": "Mexico-Peso", "CAD": "Canada-Dollar",
    "CHF": "Switzerland-Franc", "AUD": "Australia-Dollar", "SEK": "Sweden-Krona",
    "NOK": "Norway-Krone", "DKK": "Denmark-Krone", "ILS": "Israel-Shekel",
    "ZAR": "South Africa-Rand", "HKD": "Hong Kong-Dollar", "SGD": "Singapore-Dollar",
    "ARS": "Argentina-Peso", "CLP": "Chile-Peso", "COP": "Colombia-Peso", "PEN": "Peru-Sol",
    "TRY": "Turkey-New Lira", "RUB": "Russia-Ruble", "IDR": "Indonesia-Rupiah",
    "THB": "Thailand-Baht", "PHP": "Philippines-Peso", "MYR": "Malaysia-Ringgit",
    "NZD": "New Zealand-Dollar", "PLN": "Poland-Zloty", "CZK": "Czech Republic-Koruna",
    "HUF": "Hungary-Forint", "SAR": "Saudi Arabia-Riyal", "AED": "United Arab Emirates-Dirham",
    "VND": "Vietnam-Dong", "KZT": "Kazakhstan-Tenge", "NGN": "Nigeria-Naira",
    "EGP": "Egypt-Pound",
}

# EDGAR address descriptions -> ISO 3166-1 alpha-2 (only names seen among large filers)
COUNTRY_ISO2 = {
    "japan": "JP", "united kingdom": "GB", "england": "GB", "scotland": "GB", "wales": "GB",
    "ireland": "IE", "netherlands": "NL", "germany": "DE", "france": "FR", "switzerland": "CH",
    "spain": "ES", "italy": "IT", "luxembourg": "LU", "belgium": "BE", "sweden": "SE",
    "norway": "NO", "denmark": "DK", "finland": "FI", "austria": "AT", "portugal": "PT",
    "greece": "GR", "china": "CN", "hong kong": "HK", "taiwan": "TW", "korea, republic of": "KR",
    "south korea": "KR", "india": "IN", "singapore": "SG", "australia": "AU",
    "new zealand": "NZ", "israel": "IL", "brazil": "BR", "mexico": "MX", "argentina": "AR",
    "chile": "CL", "colombia": "CO", "peru": "PE", "south africa": "ZA", "bermuda": "BM",
    "cayman islands": "KY", "jersey": "JE", "guernsey": "GG", "panama": "PA", "turkey": "TR",
    "indonesia": "ID", "philippines": "PH", "thailand": "TH", "malaysia": "MY",
    "russian federation": "RU", "monaco": "MC", "cyprus": "CY", "kazakhstan": "KZ",
    "liberia": "LR", "marshall islands": "MH", "curacao": "CW", "puerto rico": "PR",
    "canada (federal level)": "CA", "canada": "CA", "united states": "US",
    "virgin islands, british": "VG", "isle of man": "IM", "uruguay": "UY", "macau": "MO",
    "united arab emirates": "AE", "viet nam": "VN", "vietnam": "VN", "nigeria": "NG",
    "egypt": "EG", "poland": "PL", "czech republic": "CZ", "hungary": "HU",
    "korea": "KR", "russia": "RU", "british virgin islands": "VG", "macao": "MO",
}
US_STATES = set("AL AK AZ AR CA CO CT DE DC FL GA HI ID IL IN IA KS KY LA ME MD MA MI MN MS MO MT "
                "NE NV NH NJ NM NY NC ND OH OK OR PA RI SC SD TN TX UT VT VA WA WV WI WY".split())
# EDGAR codes for Canadian provinces (A0..B9, Z4 = Canada federal)
CA_PROVINCES = {"A0", "A1", "A2", "A3", "A4", "A5", "A6", "A7", "A8", "A9", "B0", "B1", "B2", "Z4"}


# ----------------------------------------------------------------------------- pure helpers
def cik10(cik) -> str:
    return str(int(cik)).zfill(10)


def days_between(start: str, end: str) -> int:
    return (date.fromisoformat(end) - date.fromisoformat(start)).days + 1


def filing_url(cik, accn: str | None) -> str | None:
    if not accn:
        return None
    return f"https://www.sec.gov/Archives/edgar/data/{int(cik)}/{accn.replace('-', '')}/"


def iter_facts(companyfacts: dict, concept: str):
    """Yield (taxonomy, unit, fact) for a concept across us-gaap and ifrs-full."""
    for tax in TAXONOMIES:
        node = companyfacts.get("facts", {}).get(tax, {}).get(concept)
        if not node:
            continue
        for unit, facts in node.get("units", {}).items():
            for f in facts:
                yield tax, unit, f


def dedupe_latest_filed(facts: list[dict], key=lambda f: (f.get("start"), f["end"])) -> list[dict]:
    """One fact per period: the most recently filed value (restatements win)."""
    best: dict = {}
    for f in facts:
        k = key(f)
        cur = best.get(k)
        if cur is None or (f.get("filed", ""), f.get("accn", "")) > (cur.get("filed", ""), cur.get("accn", "")):
            best[k] = f
    return list(best.values())


def annual_duration_facts(companyfacts: dict, concept: str, unit: str | None = None) -> list[dict]:
    """Full-fiscal-year duration facts from annual forms, deduped per (unit, start, end)."""
    out = []
    for tax, u, f in iter_facts(companyfacts, concept):
        if unit and u != unit:
            continue
        if f.get("form") not in ANNUAL_FORMS or not f.get("start") or f.get("val") is None:
            continue
        if not (MIN_DAYS <= days_between(f["start"], f["end"]) <= MAX_DAYS):
            continue
        out.append({**f, "unit": u, "taxonomy": tax, "concept": concept})
    return dedupe_latest_filed(out, key=lambda f: (f["unit"], f["start"], f["end"]))


def annual_instant_facts(companyfacts: dict, concept: str, unit: str | None = None) -> list[dict]:
    """Balance-sheet (instant) facts from annual forms, deduped per (unit, end)."""
    out = []
    for tax, u, f in iter_facts(companyfacts, concept):
        if unit and u != unit:
            continue
        if f.get("form") not in ANNUAL_FORMS or f.get("start") or f.get("val") is None:
            continue
        out.append({**f, "unit": u, "taxonomy": tax, "concept": concept})
    return dedupe_latest_filed(out, key=lambda f: (f["unit"], f["end"]))


def _max_fact(cands: list[dict]) -> dict | None:
    return max(cands, key=lambda f: f["val"]) if cands else None


def select_fiscal_years(companyfacts: dict, n: int = 2) -> list[dict]:
    """Latest n full fiscal years, defined by revenue facts. Returns newest first.

    Reporting currency = unit of the latest revenue period (USD preferred on a tie).
    For each fiscal year end the broadest (max) revenue concept is taken.
    """
    rev = []
    for c in REVENUE_CONCEPTS:
        rev += annual_duration_facts(companyfacts, c)
    rev = [f for f in rev if f["val"] > 0 and len(f["unit"]) == 3]
    if not rev:
        return []
    latest_end = max(f["end"] for f in rev)
    units = {f["unit"] for f in rev if f["end"] == latest_end}
    unit = "USD" if "USD" in units else sorted(units)[0]
    rev = [f for f in rev if f["unit"] == unit]
    years = []
    for end in sorted({f["end"] for f in rev}, reverse=True):
        # two fiscal year ends closer than ~11 months = same year tagged twice; skip the older
        if years and days_between(end, years[-1]["end"]) < 330:
            continue
        years.append(_max_fact([f for f in rev if f["end"] == end]))
        if len(years) == n:
            break
    return years


def pick_cost(companyfacts: dict, unit: str, start: str, end: str) -> tuple[dict | None, str | None]:
    """Cost of sales for the fiscal year (start, end). Returns (fact, cost_basis)."""
    def match(concept):
        return [f for f in annual_duration_facts(companyfacts, concept, unit)
                if f["end"] == end and abs(days_between(start, f["start"]) - 1) <= 7 and f["val"] > 0]
    cands = []
    for c in COST_CONCEPTS:
        cands += match(c)
    if cands:
        return _max_fact(cands), "cost_of_sales"
    for c in COST_FALLBACK_CONCEPTS:
        m = match(c)
        if m:
            return m[0], "operating_expenses_fallback"
    return None, None


def pick_payables(companyfacts: dict, unit: str, end: str) -> tuple[dict | None, str | None]:
    """Trade payables at fiscal year end. Returns (fact, payables_basis). Fact may carry a 'tier_note'."""
    for basis, note, concepts in PAYABLES_TIERS:
        m = []
        for concept in concepts:
            m += [f for f in annual_instant_facts(companyfacts, concept, unit) if f["end"] == end and f["val"] > 0]
        if m:
            return {**_max_fact(m), "tier_note": note}, basis
    return None, None


def total_assets(companyfacts: dict, unit: str, end: str) -> float | None:
    m = [f for f in annual_instant_facts(companyfacts, "Assets", unit) if f["end"] == end and f["val"] > 0]
    return _max_fact(m)["val"] if m else None


def probable_scale_error(companyfacts: dict, rev: dict) -> bool:
    """Revenue more than 25x total assets: a tagging scale error (e.g. thousands tagged as millions).

    Even the highest-turnover distributors and staffing firms sit below about 10x.
    """
    assets = total_assets(companyfacts, rev["unit"], rev["end"])
    return assets is not None and rev["val"] / assets > MAX_REVENUE_TO_ASSETS


def is_financial_sic(sic) -> bool:
    try:
        return 6000 <= int(sic) <= 6799
    except (TypeError, ValueError):
        return False


def compute_dpo(payables, cost) -> float | None:
    if payables is None or cost is None or cost <= 0 or payables < 0:
        return None
    return round(payables / cost * 365, 2)


def dpo_flag(dpo: float | None, sic=None) -> str:
    if is_financial_sic(sic):
        return "not_applicable"
    if dpo is None:
        return "missing_inputs"
    if dpo < 5:
        return "suspicious_low"
    if dpo > 365:
        return "suspicious_high"
    return "ok"


def build_dpo_rows(companyfacts: dict, cik, sic=None, retrieved_at: str | None = None) -> list[dict]:
    """One row per fiscal year (latest two) with inputs, DPO, flags and provenance."""
    cik = cik10(cik)
    rows = []
    for rev in select_fiscal_years(companyfacts):
        unit, start, end = rev["unit"], rev["start"], rev["end"]
        cost, cost_basis = pick_cost(companyfacts, unit, start, end)
        pay, pay_basis = pick_payables(companyfacts, unit, end)
        notes = []
        if cost is None:
            notes.append("no cost of sales / operating expense concept tagged for this fiscal year")
        if pay is None:
            notes.append("no accounts payable concept tagged at fiscal year end")
        if cost_basis == "operating_expenses_fallback":
            notes.append(f"cost fallback {cost['concept']}: denominator is broader than cost of sales, DPO biased low")
        if pay_basis == "trade_and_other_broad":
            notes.append(f"broad payables concept {pay['concept']}: includes accruals/other payables, DPO biased high")
        if pay is not None and pay.get("tier_note"):
            notes.append(pay["tier_note"])
        if cost is not None and cost["val"] > rev["val"] * 1.5:
            notes.append("cost exceeds 1.5x revenue: check concept")
        partial_cost = cost is not None and cost["val"] < rev["val"] * PARTIAL_COST_RATIO
        if partial_cost:
            notes.append(f"{cost['concept']} is below {PARTIAL_COST_RATIO:.0%} of revenue: probably a sub-line, "
                         "not total cost of sales; DPO overstated")
        financial = is_financial_sic(sic)
        dpo = None if financial else compute_dpo(pay["val"] if pay else None, cost["val"] if cost else None)
        if financial:
            notes.append("SIC 6000-6799 (financials): DPO not meaningful, not computed")
        flag = dpo_flag(dpo, sic)
        accns = [f for f in (pay, cost, rev) if f]
        primary = max(accns, key=lambda f: (f.get("filed", ""), f.get("accn", "")))
        fallback = cost_basis == "operating_expenses_fallback" or pay_basis == "trade_and_other_broad"
        rows.append({
            "cik": cik,
            "name": companyfacts.get("entityName"),
            "sic": str(sic) if sic not in (None, "") else None,
            "fiscal_year": int(end[:4]),
            "period_start": start,
            "period_end": end,
            "currency": unit,
            "revenue": rev["val"],
            "revenue_concept": f"{rev['taxonomy']}:{rev['concept']}",
            "cost_of_sales": cost["val"] if cost else None,
            "cost_concept": f"{cost['taxonomy']}:{cost['concept']}" if cost else None,
            "cost_basis": cost_basis,
            "payables": pay["val"] if pay else None,
            "payables_concept": f"{pay['taxonomy']}:{pay['concept']}" if pay else None,
            "payables_basis": pay_basis,
            "dpo": dpo,
            "dpo_flag": flag,
            "notes": "; ".join(notes) or None,
            "form": primary.get("form"),
            "accession_number": primary.get("accn"),
            "filed": primary.get("filed"),
            "filing_url": filing_url(cik, primary.get("accn")),
            "revenue_accession": rev.get("accn"),
            "cost_accession": cost.get("accn") if cost else None,
            "payables_accession": pay.get("accn") if pay else None,
            "source_url": FACTS_URL.format(cik=cik),
            "source_type": SOURCE_TYPE,
            "retrieved_at": retrieved_at,
            "extraction_method": EXTRACTION_METHOD,
            "confidence": 0.5 if partial_cost else (0.7 if fallback else 1.0),
        })
    return rows


def to_usd(value: float, currency: str, fx: dict) -> float | None:
    if currency == "USD":
        return float(value)
    rate = fx.get(currency)
    return float(value) / rate if rate else None


def country_from_address(addr: dict | None) -> tuple[str | None, str | None, str | None]:
    """(iso2, country_name, us_state) from an EDGAR submissions address block."""
    if not addr:
        return None, None, None
    # US addresses: stateOrCountry = state code. Foreign addresses: either stateOrCountry holds an
    # EDGAR country code with the name in stateOrCountryDescription, or (newer layout) the name is
    # in `country` and the EDGAR code in `countryCode`. EDGAR codes are NOT ISO, so map by name.
    code = (addr.get("stateOrCountry") or "").strip().upper()
    name = (addr.get("country") or addr.get("stateOrCountryDescription") or "").strip()
    if code in US_STATES and not addr.get("country"):
        return "US", "United States", code
    key = name.lower()
    if key.endswith(", canada") or code in CA_PROVINCES:
        return "CA", "Canada", None
    return COUNTRY_ISO2.get(key), name or None, None


# ----------------------------------------------------------------------------- network steps
def _get(url: str):
    """fetch() that returns None on 404 (EDGAR has no companyfacts for some CIKs)."""
    try:
        return fetch(url)
    except httpx.HTTPStatusError as e:
        if e.response is not None and e.response.status_code == 404:
            return None
        raise


def load_fx() -> dict:
    """ISO currency -> units per 1 USD. Written once to config/fx_rates_treasury.yaml, then read from it."""
    if FX_PATH.exists():
        return {k: v["per_usd"] for k, v in yaml.safe_load(FX_PATH.read_text())["rates"].items()}
    url = FX_URL.format(d=FX_RECORD_DATE)
    r = fetch(url)
    by_label: dict[str, list[float]] = {}
    for d in r.json()["data"]:
        by_label.setdefault(d["country_currency_desc"], []).append(float(d["exchange_rate"]))
    rates = {}
    for iso, label in FX_TREASURY_LABELS.items():
        vals = by_label.get(label)
        if vals and len(vals) == 1:   # skip currencies with more than one official rate
            rates[iso] = {"per_usd": vals[0], "treasury_label": label}
    doc = {
        "description": "Foreign currency units per 1 USD. Used ONLY to convert non-USD revenue to a rough "
                       "USD figure for the >= USD 4B universe threshold. DPO is a ratio and never uses FX.",
        "source": "US Treasury, Bureau of the Fiscal Service: Treasury Reporting Rates of Exchange",
        "source_url": url,
        "record_date": FX_RECORD_DATE,
        "retrieved_at": r.retrieved_at,
        "licence": "US government work, public domain",
        "rates": rates,
    }
    FX_PATH.parent.mkdir(parents=True, exist_ok=True)
    FX_PATH.write_text(yaml.safe_dump(doc, sort_keys=False, allow_unicode=True))
    return {k: v["per_usd"] for k, v in rates.items()}


def discover_candidates(log=print) -> tuple[dict[str, set], list[dict]]:
    """CIK (10-digit) -> set of discovery routes, plus a manifest of what was fetched."""
    cands: dict[str, set] = {}
    fetched = []
    for concept in FRAME_REVENUE_CONCEPTS:
        for frame in FRAME_YEARS:
            url = FRAME_URL.format(tax="us-gaap", concept=concept, unit="USD", frame=frame)
            r = _get(url)
            if r is None:
                fetched.append({"url": url, "status": 404, "note": "frame not served"})
                continue
            data = r.json()["data"]
            big = [d for d in data if d["val"] >= REVENUE_THRESHOLD_USD]
            for d in big:
                cands.setdefault(cik10(d["cik"]), set()).add("usgaap_frame")
            fetched.append({"url": url, "status": 200, "rows": len(data), "rows_ge_threshold": len(big),
                            "retrieved_at": r.retrieved_at, "sha256": r.sha256})
    n_frames = len(cands)
    pat = re.compile(r"^(20-F|40-F)(/A)?\s+.*?\s+(\d+)\s+\d{4}-\d{2}-\d{2}\s+edgar/")
    for y, q in FORM_INDEX_QUARTERS:
        url = FORM_INDEX_URL.format(y=y, q=q)
        r = _get(url)
        if r is None:
            fetched.append({"url": url, "status": 404})
            continue
        n = 0
        for line in r.text.splitlines():
            m = pat.match(line)
            if m:
                cands.setdefault(cik10(m.group(3)), set()).add("fpi_form_index")
                n += 1
        fetched.append({"url": url, "status": 200, "fpi_annual_filings": n,
                        "retrieved_at": r.retrieved_at, "sha256": r.sha256})
    log(f"candidates: {n_frames} from us-gaap frames, {len(cands)} incl. 20-F/40-F filers")
    return cands, fetched


def run(log=print) -> dict:
    started = now_iso()
    fx = load_fx()
    cands, fetched = discover_candidates(log)
    tick = fetch(TICKERS_URL)
    ticker_map: dict[str, list[str]] = {}
    for v in tick.json().values():
        ticker_map.setdefault(cik10(v["cik_str"]), []).append(v["ticker"])

    companies, dpo_rows = [], []
    stats = {"candidates": len(cands), "companyfacts_404": 0, "no_annual_revenue": 0,
             "below_threshold": 0, "stale": 0, "unknown_currency": [], "scale_error": []}
    for i, cik in enumerate(sorted(cands)):
        if i and i % 200 == 0:
            log(f"  companyfacts {i}/{len(cands)} (kept {len(companies)})")
        r = _get(FACTS_URL.format(cik=cik))
        if r is None:
            stats["companyfacts_404"] += 1
            continue
        try:
            cf = r.json()
        except ValueError:
            stats["companyfacts_404"] += 1
            continue
        years = select_fiscal_years(cf)
        if not years:
            stats["no_annual_revenue"] += 1
            continue
        latest = years[0]
        if latest["end"] < MIN_LATEST_FY_END:
            stats["stale"] += 1
            continue
        rev_usd = to_usd(latest["val"], latest["unit"], fx)
        if rev_usd is None:
            stats["unknown_currency"].append({"cik": cik, "name": cf.get("entityName"), "currency": latest["unit"]})
            continue
        if rev_usd < REVENUE_THRESHOLD_USD:
            stats["below_threshold"] += 1
            continue
        if probable_scale_error(cf, latest):
            stats["scale_error"].append({"cik": cik, "name": cf.get("entityName"), "revenue_as_tagged": latest["val"],
                                         "currency": latest["unit"], "period_end": latest["end"],
                                         "total_assets": total_assets(cf, latest["unit"], latest["end"]),
                                         "accession_number": latest.get("accn")})
            continue

        sub_r = _get(SUBMISSIONS_URL.format(cik=cik))
        sub = sub_r.json() if sub_r else {}
        sic = sub.get("sic") or None
        addr = (sub.get("addresses") or {}).get("business")
        iso2, country_name, state = country_from_address(addr)
        tickers = sub.get("tickers") or ticker_map.get(cik, [])
        notes = []
        if latest["unit"] != "USD":
            notes.append(f"revenue_usd converted from {latest['unit']} at {fx[latest['unit']]} per USD "
                         f"(US Treasury rate {FX_RECORD_DATE}); rough, for thresholding only")
        if iso2 is None:
            notes.append("business address country not mapped to ISO2")
        if not sub:
            notes.append("submissions JSON not available")
        companies.append({
            "cik": cik,
            "name": sub.get("name") or cf.get("entityName"),
            "tickers": ",".join(tickers) or None,
            "exchanges": ",".join(e for e in (sub.get("exchanges") or []) if e) or None,
            "sic": sic,
            "sic_description": sub.get("sicDescription") or None,
            "is_financial_sic": is_financial_sic(sic),
            "country": iso2,
            "country_name": country_name,
            "state": state,
            "state_of_incorporation": sub.get("stateOfIncorporation") or None,
            "fiscal_year_end_mmdd": sub.get("fiscalYearEnd") or None,
            "filer_category": sub.get("category") or None,
            "discovery_route": "+".join(sorted(cands[cik])),
            "latest_fiscal_year": int(latest["end"][:4]),
            "is_latest_fy_current": latest["end"] >= CURRENT_FY_END,
            "revenue": latest["val"],
            "currency": latest["unit"],
            "revenue_usd": round(rev_usd, 0),
            "revenue_usd_method": "reported_usd" if latest["unit"] == "USD" else f"fx_treasury_{FX_RECORD_DATE}",
            "fx_rate_per_usd": 1.0 if latest["unit"] == "USD" else fx[latest["unit"]],
            "revenue_concept": f"{latest['taxonomy']}:{latest['concept']}",
            "period_start": latest["start"],
            "period_end": latest["end"],
            "form": latest.get("form"),
            "accession_number": latest.get("accn"),
            "filed": latest.get("filed"),
            "filing_url": filing_url(cik, latest.get("accn")),
            "source_url": FACTS_URL.format(cik=cik),
            "submissions_url": SUBMISSIONS_URL.format(cik=cik),
            "source_type": SOURCE_TYPE,
            "retrieved_at": r.retrieved_at,
            "extraction_method": EXTRACTION_METHOD,
            "confidence": 1.0,
            "notes": "; ".join(notes) or None,
        })
        dpo_rows += build_dpo_rows(cf, cik, sic, r.retrieved_at)

    comp = pd.DataFrame(companies).sort_values("revenue_usd", ascending=False).reset_index(drop=True)
    dpo = pd.DataFrame(dpo_rows)
    dpo = dpo.drop(columns="name").merge(comp[["cik", "name", "tickers", "country"]], on="cik", how="left")
    dpo = dpo[["cik", "name"] + [c for c in dpo.columns if c not in ("cik", "name")]]
    dpo = dpo.sort_values(["cik", "period_end"], ascending=[True, False]).reset_index(drop=True)

    out = ROOT / "data" / "interim"
    out.mkdir(parents=True, exist_ok=True)
    comp.to_parquet(out / "sec_companies.parquet", index=False)
    comp.to_csv(out / "sec_companies.csv", index=False)
    dpo.to_parquet(out / "sec_dpo.parquet", index=False)
    dpo.to_csv(out / "sec_dpo.csv", index=False)

    latest = dpo.sort_values("period_end").groupby("cik").tail(1)
    manifest = {
        "source": "SEC EDGAR XBRL (frames, companyfacts, submissions, full-index form.idx)",
        "licence": "US government work, public domain",
        "run_started_at": started,
        "run_finished_at": now_iso(),
        "revenue_threshold_usd": REVENUE_THRESHOLD_USD,
        "fx_rates_file": "config/fx_rates_treasury.yaml",
        "discovery_fetches": fetched,
        "counts": {
            **{k: v for k, v in stats.items() if k not in ("unknown_currency", "scale_error")},
            "excluded_probable_scale_error": len(stats["scale_error"]),
            "unknown_currency": len(stats["unknown_currency"]),
            "companies_ge_threshold": len(comp),
            "companies_by_discovery_route": comp["discovery_route"].value_counts().to_dict(),
            "dpo_rows": len(dpo),
            "dpo_flag_all_rows": dpo["dpo_flag"].value_counts().to_dict(),
            "dpo_flag_latest_fy": latest["dpo_flag"].value_counts().to_dict(),
            "cost_basis_latest_fy": latest["cost_basis"].fillna("missing").value_counts().to_dict(),
            "payables_basis_latest_fy": latest["payables_basis"].fillna("missing").value_counts().to_dict(),
        },
        "unknown_currency_candidates": stats["unknown_currency"],
        "excluded_probable_scale_error": stats["scale_error"],
        "outputs": ["data/interim/sec_companies.parquet", "data/interim/sec_companies.csv",
                    "data/interim/sec_dpo.parquet", "data/interim/sec_dpo.csv"],
        "per_request_log": "data/manifests/http_log.jsonl",
    }
    write_manifest("sec_xbrl", manifest)
    log(f"companies >= USD {REVENUE_THRESHOLD_USD/1e9:.0f}B: {len(comp)}; dpo rows: {len(dpo)}")
    log(f"latest-FY dpo flags: {manifest['counts']['dpo_flag_latest_fy']}")
    return manifest


if __name__ == "__main__":
    run()
    sys.exit(0)
