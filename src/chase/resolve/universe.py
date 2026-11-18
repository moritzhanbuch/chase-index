"""Build the "Global 2000-style" company universe.

Sources (all public): SEC EDGAR XBRL filers, ESEF filers (filings.xbrl.org), Wikidata.
A company enters the universe when its latest known annual revenue is >= the threshold in
config/assumptions.yaml (default USD 4B). Records from the three sources are merged with
identifiers first (SEC CIK, LEI), then exact normalised-name equality. Nothing fuzzy here.

Output: data/processed/universe.parquet (+csv), one row per company with a stable company_id.
Run: python -m chase.resolve.universe
"""
from __future__ import annotations

import json
import re
from pathlib import Path

import pandas as pd
import yaml

from chase.enrich.sectors import classify
from chase.resolve.names import norm, strip_accents

ROOT = Path(__file__).resolve().parents[3]
INTERIM = ROOT / "data" / "interim"
OUT = ROOT / "data" / "processed"

STALE_BEFORE_YEAR = 2022      # Wikidata revenue older than this is flagged stale
DROP_BEFORE_YEAR = 2015       # ...and older than this is not trusted at all
NON_COMPANY_TYPES = re.compile(r"\b(division|business unit|product line|tax|government agency|ministry|"
                               r"central bank|university|sovereign wealth fund|sports club|military)\b", re.I)


def _split(v) -> list[str]:
    if v is None or (isinstance(v, float) and pd.isna(v)):
        return []
    return [x.strip() for x in str(v).split("|") if x.strip()]


def slugify(name: str) -> str:
    s = strip_accents(name).lower()
    s = re.sub(r"[^a-z0-9]+", "-", s).strip("-")
    return s[:48].strip("-") or "company"


_KEEP_UPPER = {"PLC", "AG", "SE", "SA", "NV", "BV", "AB", "ASA", "LLC", "LP", "USA", "UK", "US", "II", "III", "IV",
               "HP", "IBM", "GE", "RTX", "AT&T", "BP", "BT", "ITV", "GSK", "HSBC", "UBS", "ABB", "SAP", "BMW", "RWE",
               "ACS", "CRH", "DSM", "KLM", "LVMH", "TJX", "CVS", "UPS", "AES", "HCA", "KKR", "CBRE", "NRG", "PPG", "CDW",
               "AMD", "TD", "JD", "WH", "DS", "WPP", "BAE", "SSE", "RELX", "ASML", "ING", "KBC", "OMV", "EDP", "CNH"}
_LOWER = {"and", "of", "de", "del", "la", "y", "e", "the", "van", "von", "der", "des", "du", "et"}


def tidy_name(name: str) -> str:
    """Display name: filing names are often ALL CAPS with EDGAR state suffixes ("CHURCH & DWIGHT CO INC /DE/")."""
    n = re.sub(r"\s*/[A-Z]{2,3}/?\s*$", "", name.strip()).rstrip("/").strip()
    n = re.sub(r"\bP\.L\.C\.?", "PLC", n)
    n = re.sub(r"\bP\.L\.C\.?", "PLC", n)
    letters = [c for c in n if c.isalpha()]
    if not letters or sum(c.isupper() for c in letters) / len(letters) < 0.8 or len(n) <= 4:
        return n
    out = []
    for i, w in enumerate(n.split(" ")):
        bare = w.strip(".,()")
        if bare.upper() in _KEEP_UPPER or (len(bare) <= 3 and "." in w):
            out.append(w.upper() if bare.upper() != "PLC" else w.lower())
        elif bare.lower() in _LOWER and i > 0:
            out.append(w.lower())
        else:
            out.append("-".join(p[:1].upper() + p[1:].lower() for p in w.split("-")))
    return " ".join(out)


# Wikidata labels that are out of date (the item was renamed after a merger). Display name only.
NAME_OVERRIDES = {"Dr Pepper Snapple Group": "Keurig Dr Pepper", "Lkq Corp": "LKQ Corporation"}


OVERRIDES = yaml.safe_load((ROOT / "config" / "overrides.yaml").read_text()) if (ROOT / "config" / "overrides.yaml").exists() else {}
NOT_ONE_COMPANY_QIDS = {"Q183275"}   # "Mitsubishi" (the keiretsu), not Mitsubishi Corporation


class UF:
    def __init__(self):
        self.p: dict[str, str] = {}

    def find(self, x):
        self.p.setdefault(x, x)
        while self.p[x] != x:
            self.p[x] = self.p[self.p[x]]
            x = self.p[x]
        return x

    def union(self, a, b):
        ra, rb = self.find(a), self.find(b)
        if ra != rb:
            self.p[rb] = ra


def load_sources(min_rev: float):
    sec = pd.read_parquet(INTERIM / "sec_companies.parquet")
    esef = pd.read_parquet(INTERIM / "esef_companies.parquet")
    wd = pd.read_parquet(INTERIM / "wikidata_companies.parquet")
    log = {}

    # SEC: drop CIKs without a ticker (finance arms, operating subsidiaries filing debt)
    sec["has_ticker"] = sec["tickers"].fillna("").str.len() > 0
    log["sec_dropped_no_ticker"] = int((~sec.has_ticker).sum())
    wd_ciks = {c.zfill(10) for v in wd.sec_cik.dropna() for c in str(v).split("|")}
    keep = sec.has_ticker | sec.cik.isin(wd_ciks)   # EDGAR ticker data has gaps (e.g. Exxon Mobil): a Wikidata CIK link also qualifies
    log["sec_dropped_no_ticker"] = int((~keep).sum())
    sec = sec[keep & (sec.revenue_usd >= min_rev)].copy()

    # ESEF: non-financial revenue is tagged; banks/insurers rarely tag revenue, they enter via Wikidata/SEC
    esef = esef[esef.revenue_usd >= min_rev].copy()

    # Wikidata: community-edited, so type and dissolution flags are noisy (BASF is typed "brand",
    # Telefónica carries a 1988 dissolution date). An item with a securities/legal identifier
    # (ISIN, LEI or SEC CIK) and a recent revenue statement is trusted over those flags.
    wd = wd[wd.revenue_usd >= min_rev].copy()
    has_id = wd["isin"].notna() | wd["lei"].notna() | wd["sec_cik"].notna()
    yr = wd.revenue_year.astype("Float64")
    recent = yr.fillna(0) >= 2020
    dissolved = wd.is_dissolved.fillna(False)
    is_div = wd.instance_of.fillna("").apply(lambda s: bool(NON_COMPANY_TYPES.search(s)))
    trusted_id = has_id & (recent | yr.isna()) & ~(dissolved & ~recent)
    plain_ok = wd.company_like_type.fillna(False) & ~dissolved & ~is_div & (yr.fillna(0) >= DROP_BEFORE_YEAR)
    keep_wd = trusted_id | plain_ok
    log["wikidata_dropped"] = int((~keep_wd).sum())
    log["wikidata_kept_on_identifier_despite_flags"] = int((trusted_id & ~plain_ok).sum())
    wd = wd[keep_wd].copy()
    return sec, esef, wd, log


def build(min_rev: float | None = None) -> pd.DataFrame:
    cfg = yaml.safe_load((ROOT / "config" / "assumptions.yaml").read_text())
    min_rev = min_rev or float(cfg["universe"]["min_revenue_usd"])
    sec, esef, wd, log = load_sources(min_rev)

    uf = UF()
    recs: dict[str, dict] = {}
    for _, r in sec.iterrows():
        recs[f"cik:{r.cik}"] = {"src": "sec", "row": r}
    for _, r in esef.iterrows():
        recs[f"lei:{r.lei}"] = {"src": "esef", "row": r}
    for _, r in wd.iterrows():
        recs[f"qid:{r.qid}"] = {"src": "wd", "row": r}
    for k in recs:
        uf.find(k)

    # 1. identifier links through Wikidata
    link_methods: dict[str, set] = {}
    def link(a, b, how):
        uf.union(a, b)
        link_methods.setdefault(a, set()).add(how)
        link_methods.setdefault(b, set()).add(how)

    for _, r in wd.iterrows():
        q = f"qid:{r.qid}"
        for c in _split(r.sec_cik):
            k = f"cik:{c.zfill(10)}"
            if k in recs:
                link(q, k, "wikidata_cik")
        for l in _split(r.lei):
            k = f"lei:{l}"
            if k in recs:
                link(q, k, "wikidata_lei")

    # 2. exact normalised-name equality (unique on both sides), any pair of sources
    def name_keys(rec) -> set[str]:
        r = rec["row"]
        if rec["src"] == "wd":
            names = [r.label_en, r.label_de, r.label_es, r.label_fr] + _split(r.aliases_en)
        else:
            names = [r["name"]]
        return {n for n in (norm(x) for x in names if isinstance(x, str)) if len(n) >= 3}

    by_name: dict[str, set[str]] = {}
    for k, rec in recs.items():
        for n in name_keys(rec):
            by_name.setdefault(n, set()).add(k)
    for n, keys in by_name.items():
        srcs = {}
        for k in keys:
            srcs.setdefault(recs[k]["src"], []).append(k)
        if len(srcs) < 2 or any(len(v) > 1 for v in srcs.values()):
            continue  # same-source duplicates or nothing to merge: leave alone
        ks = [v[0] for v in srcs.values()]
        for other in ks[1:]:
            link(ks[0], other, "exact_normalised_name")

    groups: dict[str, list[str]] = {}
    for k in recs:
        groups.setdefault(uf.find(k), []).append(k)

    rows = []
    for root, keys in groups.items():
        s = [recs[k]["row"] for k in keys if recs[k]["src"] == "sec"]
        e = [recs[k]["row"] for k in keys if recs[k]["src"] == "esef"]
        w = [recs[k]["row"] for k in keys if recs[k]["src"] == "wd"]
        s.sort(key=lambda r: -r.revenue_usd); e.sort(key=lambda r: -r.revenue_usd); w.sort(key=lambda r: -r.revenue_usd)
        S, E, W = (s[0] if s else None), (e[0] if e else None), (w[0] if w else None)

        # revenue: filed data first
        if S is not None:
            rev = dict(revenue=float(S.revenue), revenue_currency=S.currency, revenue_usd=float(S.revenue_usd),
                       revenue_period_start=str(S.period_start)[:10], revenue_period_end=str(S.period_end)[:10],
                       revenue_source_type="sec_xbrl_companyfacts", revenue_source_url=S.filing_url,
                       revenue_confidence=1.0, revenue_stale=not bool(S.is_latest_fy_current))
        elif E is not None:
            rev = dict(revenue=float(E.revenue), revenue_currency=E.currency, revenue_usd=float(E.revenue_usd),
                       revenue_period_start=str(E.period_start)[:10], revenue_period_end=str(E.period_end)[:10],
                       revenue_source_type="esef_xbrl_json", revenue_source_url=E.report_url or E.source_url,
                       revenue_confidence=1.0, revenue_stale=False)
        else:
            yr = int(W.revenue_year) if not pd.isna(W.revenue_year) else None
            rev = dict(revenue=float(W.revenue_amount), revenue_currency=W.revenue_currency,
                       revenue_usd=float(W.revenue_usd), revenue_period_start=f"{yr}-01-01" if yr else None,
                       revenue_period_end=f"{yr}-12-31" if yr else None, revenue_source_type="wikidata",
                       revenue_source_url=W.source_url, revenue_confidence=0.6 if yr else 0.4,
                       revenue_stale=(yr is None) or yr < STALE_BEFORE_YEAR)

        name = (W.label_en if W is not None and isinstance(W.label_en, str) else None) or \
               (S["name"] if S is not None else None) or (E["name"] if E is not None else None) or \
               next((x for x in ([W.label_mul, W.label_de, W.label_es, W.label_fr] if W is not None else [])
                     if isinstance(x, str)), None)
        if not name:
            continue  # unlabeled Wikidata item with no filing counterpart: unusable
        name = tidy_name(name)
        name = NAME_OVERRIDES.get(name, name)
        name = OVERRIDES.get("display_names", {}).get(name, name)
        legal_names = sorted({str(x["name"]) for x in s + e})
        aliases = set(legal_names)
        for x in w:
            aliases |= {a for a in [x.label_en, x.label_de, x.label_es, x.label_fr] if isinstance(a, str)}
            aliases |= set(_split(x.aliases_en)) | set(_split(x.short_name))
        aliases.discard(name)

        wd_hq = W.hq_country_iso2 if W is not None and isinstance(W.hq_country_iso2, str) else None
        wd_c = W.country_iso2 if W is not None and isinstance(W.country_iso2, str) else None
        country = wd_hq or (S.country if S is not None and isinstance(S.country, str) else None) or wd_c or \
                  (E.country if E is not None else None)
        country_method = "wikidata_hq" if wd_hq else ("sec_business_address" if S is not None and isinstance(S.country, str)
                          else ("wikidata_country" if wd_c else "esef_filing_country"))

        sic = S.sic if S is not None else None
        industries = W.industries if W is not None and isinstance(W.industries, str) else None
        sector, sector_method = classify(sic, industries, name)
        if sector != "financials" and ((E is not None and bool(E.is_financial)) or
                                       (S is not None and bool(S.is_financial_sic))):
            sector, sector_method = "financials", "filing_flag"

        isins = sorted({i for x in w for i in _split(x["isin"])})   # x.isin would be the pandas method
        leis = sorted({str(x.lei) for x in e} | {l for x in w for l in _split(x.lei)})
        ciks = sorted({str(x.cik) for x in s})
        qids = [x.qid for x in w]
        key_for_id = (qids[0].lower() if qids else (f"cik{int(ciks[0])}" if ciks else f"lei{leis[0][-6:].lower()}"))
        prov = (W if W is not None else (S if S is not None else E))
        methods = sorted(set().union(*[link_methods.get(k, set()) for k in keys])) or ["single_source"]

        rows.append({
            "company_id": f"{slugify(name)}-{key_for_id}",
            "name": name,
            "legal_names": "|".join(legal_names),
            "aliases": "|".join(sorted(aliases))[:2000],
            "country": country, "country_method": country_method,
            "hq_city": W.hq_city if W is not None and isinstance(W.hq_city, str) else None,
            "sector": sector, "sector_method": sector_method,
            "sic": int(sic) if sic is not None and not pd.isna(sic) else None,
            "sic_description": S.sic_description if S is not None else None,
            "wikidata_industries": industries,
            **rev,
            "employees": int(W.employees) if W is not None and not pd.isna(W.employees) else None,
            "employees_year": int(W.employees_year) if W is not None and not pd.isna(W.employees_year) else None,
            "isin": "|".join(isins) or None, "lei": "|".join(leis) or None, "cik": "|".join(ciks) or None,
            "wikidata_qid": "|".join(qids) or None,
            "tickers": S.tickers if S is not None else (W.ticker if W is not None and isinstance(W.ticker, str) else None),
            "stock_indices": W.stock_indices if W is not None and isinstance(W.stock_indices, str) else None,
            "website": W.website if W is not None and isinstance(W.website, str) else None,
            "wikidata_parent_qid": W.parent_qid if W is not None and isinstance(W.parent_qid, str) else None,
            "uk_company_number_wikidata": W.uk_company_number if W is not None and isinstance(W.uk_company_number, str) else None,
            "in_sec": bool(s), "in_esef": bool(e), "in_wikidata": bool(w),
            "merge_methods": "|".join(methods),
            "source_url": prov.source_url, "source_type": "universe_merge(" + "+".join(
                [t for t, f in (("sec", s), ("esef", e), ("wikidata", w)) if f]) + ")",
            "retrieved_at": prov.retrieved_at,
            "period_start": rev["revenue_period_start"], "period_end": rev["revenue_period_end"],
            "extraction_method": "identifier_and_exact_name_merge",
            "confidence": rev["revenue_confidence"],
        })

    u = pd.DataFrame(rows)

    # LLM sector classification for companies without an SEC SIC code (see docs/model_routing.md).
    # SIC-coded rows keep their rule-based sector. Units and non-companies are flagged, not deleted.
    u["is_subsidiary_or_unit"] = False
    u["not_a_company"] = False
    llm_path = INTERIM / "sector_llm.csv"
    if llm_path.exists():
        llm = pd.read_csv(llm_path).drop_duplicates("company_id").set_index("company_id")
        hit = u.company_id.isin(llm.index) & (u.sector_method != "sic_code")
        ids = u.loc[hit, "company_id"]
        u.loc[hit, "sector"] = ids.map(llm.sector).values
        u.loc[hit, "sector_method"] = "llm_classification"
        u.loc[hit, "sector_confidence"] = ids.map(llm.confidence).values
        truthy = lambda v: str(v).strip().lower() == "true"
        u.loc[hit, "is_subsidiary_or_unit"] = ids.map(llm.is_subsidiary_or_unit).map(truthy).values
        u.loc[hit, "not_a_company"] = ids.map(llm.not_a_company).map(truthy).values
    # The ESEF index gives the country where the report was filed, not the HQ. For ESEF-only rows an LLM
    # supplied the HQ country from the company name; applied only where it was at least fairly sure.
    cpath = INTERIM / "country_llm.csv"
    if cpath.exists():
        cl = pd.read_csv(cpath).drop_duplicates("company_id").set_index("company_id")
        hit = (u.country_method == "esef_filing_country") & u.company_id.isin(cl.index)
        ids = u.loc[hit, "company_id"]
        ok = ids.map(cl.confidence).astype(float) >= 0.7
        u.loc[ok[ok].index, "country"] = ids[ok].map(cl.hq_country).values
        u.loc[ok[ok].index, "country_method"] = "llm_hq_country"
    for nm, cc in (OVERRIDES.get("countries") or {}).items():
        u.loc[u.name == nm, ["country", "country_method"]] = [cc, "manual_override"]
    # HQ city: Wikidata P159 first; where it is missing, the headquarters address on the company's LEI record (GLEIF,
    # python -m chase.sources.gleif); overrides last, each with a reason in config/overrides.yaml
    u["hq_city_source"] = u.hq_city.notna().map({True: "wikidata_p159", False: None})
    gpath = INTERIM / "gleif_hq.csv"
    if gpath.exists():
        g = pd.read_csv(gpath).dropna(subset=["hq_city"]).drop_duplicates("company_id").set_index("company_id")
        hit = u.hq_city.isna() & u.company_id.isin(g.index)
        u.loc[hit, "hq_city"] = u.loc[hit, "company_id"].map(g.hq_city).values
        u.loc[hit, "hq_city_source"] = u.loc[hit, "company_id"].map(g.source_url).values
    for nm, city in (OVERRIDES.get("hq_cities") or {}).items():
        u.loc[u.name == nm, ["hq_city", "hq_city_source"]] = [city, "manual_override"]
    for nm, sec_ in (OVERRIDES.get("sectors") or {}).items():
        u.loc[u.name == nm, ["sector", "sector_method", "sector_confidence"]] = [sec_, "manual_override", 0.9]
    # Wikidata items that are a loose family of independent listed companies, not one group
    u.loc[u.wikidata_qid.isin(NOT_ONE_COMPANY_QIDS), "not_a_company"] = True
    if "sector_confidence" not in u:
        u["sector_confidence"] = None
    u.loc[u.sector_method == "sic_code", "sector_confidence"] = 0.9
    u["sector_confidence"] = u.sector_confidence.fillna(0.5)
    # parent links inside the universe (Wikidata P749): flag subsidiaries that sit under another universe member
    qid_to_id = {}
    for _, r in u.iterrows():
        for q in _split(r.wikidata_qid):
            qid_to_id[q] = r.company_id
    u["parent_company_id"] = u.wikidata_parent_qid.apply(
        lambda v: next((qid_to_id[q] for q in _split(v) if q in qid_to_id), None))
    # Wikidata "parent organisation" links go stale (Fresenius Medical Care was deconsolidated in 2023).
    # A company with its own SEC or ESEF annual filing is treated as its own group.
    u.loc[u.in_sec | u.in_esef, "parent_company_id"] = None
    u.loc[u.parent_company_id == u.company_id, "parent_company_id"] = None
    # hand-checked minority or stale links (config/parent_overrides.yaml, each with a reason)
    ov = ROOT / "config" / "parent_overrides.yaml"
    if ov.exists():
        cut = {c["child"] for c in (yaml.safe_load(ov.read_text()) or {}).get("cut", [])}
        u.loc[u.company_id.isin(cut), "parent_company_id"] = None

    # filing-only rows that share their distinctive name with a larger universe company are financing or
    # holding vehicles of that group ("Nestle Holdings, Inc." files bonds; Nestlé is the group)
    from chase.resolve.names import core as _core
    u["_core"] = u.name.map(_core)
    biggest = u.sort_values("revenue_usd", ascending=False).drop_duplicates("_core").set_index("_core").company_id
    from chase.resolve.uk_rollup import COMMON as _COMMON   # ordinary words shared by unrelated firms ("Edison", "Prudential")
    distinctive = u._core.map(lambda c: len(c) >= 5 and not (set(c.split()) & _COMMON))
    veh = (~u.in_wikidata) & u.parent_company_id.isna() & (u._core.map(biggest) != u.company_id) & distinctive
    u.loc[veh, "parent_company_id"] = u.loc[veh, "_core"].map(biggest)
    u.loc[veh, "is_subsidiary_or_unit"] = True
    log["flagged_same_name_vehicles"] = int(veh.sum())
    u = u.drop(columns="_core")

    # DACH slice: Bavarian DAX/MDAX members missing above are added from index membership + annual-report revenue
    from chase.sources.dach_slice import universe_additions
    add = universe_additions(u)
    if len(add):
        add = add.assign(hq_city_source=add.hq_city.notna().map({True: "config/dach_slice.yaml", False: None}))
        u = pd.concat([u, add], ignore_index=True)
    log["dach_slice_added"] = int(len(add))

    dup = u.company_id.duplicated(keep=False)
    if dup.any():
        u.loc[dup, "company_id"] = u[dup].apply(lambda r: f"{r.company_id}-{abs(hash(r['name'])) % 997}", axis=1)
    u = u.sort_values("revenue_usd", ascending=False).reset_index(drop=True)

    OUT.mkdir(parents=True, exist_ok=True)
    u.to_parquet(OUT / "universe.parquet", index=False)
    u.to_csv(OUT / "universe.csv", index=False)
    log.update({
        "min_revenue_usd": min_rev, "companies": len(u),
        "by_source": {"sec": int(u.in_sec.sum()), "esef": int(u.in_esef.sum()), "wikidata": int(u.in_wikidata.sum())},
        "multi_source": int((u[["in_sec", "in_esef", "in_wikidata"]].sum(axis=1) > 1).sum()),
        "by_country_top": u.country.value_counts().head(15).to_dict(),
        "by_sector": u.sector.value_counts().to_dict(),
        "revenue_stale": int(u.revenue_stale.sum()),
        "subsidiaries_of_universe_members": int(u.parent_company_id.notna().sum()),
    })
    (ROOT / "data" / "manifests" / "universe.json").write_text(json.dumps(log, indent=2))
    return u


if __name__ == "__main__":
    u = build()
    print(json.loads((ROOT / "data" / "manifests" / "universe.json").read_text()))
