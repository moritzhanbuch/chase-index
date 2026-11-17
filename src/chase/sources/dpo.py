"""Computed DPO (proxy) for universe companies, from SEC and ESEF XBRL facts and the DACH annual-report slice.

DPO = trade payables at fiscal year end / cost of sales x 365.
It is a balance-sheet proxy. It is NOT the same thing as reported days to pay.

Output: data/processed/dpo.parquet (+csv): one row per company per fiscal year (latest two).
When a company has both an SEC and an ESEF row for a fiscal year, the row with the higher
confidence wins (ties: SEC). Run: python -m chase.sources.dpo
"""
from __future__ import annotations

from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[3]
INTERIM = ROOT / "data" / "interim"
OUT = ROOT / "data" / "processed"

KEEP = ["company_id", "company_name", "fiscal_year", "period_start", "period_end", "currency", "revenue",
        "cost_of_sales", "cost_concept", "cost_basis", "payables", "payables_concept", "payables_basis",
        "dpo", "dpo_flag", "dpo_source", "filing_url", "source_url", "source_type", "retrieved_at",
        "extraction_method", "confidence", "notes"]


def _explode_ids(u: pd.DataFrame, col: str) -> dict[str, str]:
    out = {}
    for cid, v in zip(u.company_id, u[col]):
        if isinstance(v, str):
            for x in v.split("|"):
                out.setdefault(x, cid)
    return out


def build() -> pd.DataFrame:
    u = pd.read_parquet(OUT / "universe.parquet")
    name = dict(zip(u.company_id, u.name))
    sector = dict(zip(u.company_id, u.sector))

    sec = pd.read_parquet(INTERIM / "sec_dpo.parquet")
    sec["company_id"] = sec.cik.map(_explode_ids(u, "cik"))
    sec = sec[sec.company_id.notna()].copy()
    sec["dpo_source"] = "sec"
    if "notes" not in sec:
        sec["notes"] = None

    esef = pd.read_parquet(INTERIM / "esef_dpo.parquet")
    esef["company_id"] = esef.lei.map(_explode_ids(u, "lei"))
    esef = esef[esef.company_id.notna()].copy()
    esef = esef.rename(columns={"cost": "cost_of_sales", "report_url": "filing_url"})
    esef["dpo_source"] = "esef"
    esef["notes"] = None

    # DACH slice: annual reports read by two extractors + QA (trade payables to suppliers, from the notes if needed)
    dp = INTERIM / "dach_dpo.parquet"
    dach = pd.read_parquet(dp) if dp.exists() else pd.DataFrame(columns=["qid", "lei"])
    if len(dach):
        by_q, by_l = _explode_ids(u, "wikidata_qid"), _explode_ids(u, "lei")
        dach["company_id"] = [by_q.get(q) or next((by_l[x] for x in str(l).split("|") if x in by_l), None)
                              for q, l in zip(dach.qid, dach.lei)]
        dach = dach[dach.company_id.notna()].copy()
        dach["dpo_source"] = "dach_annual_report"

    srcs = [x for x in (sec, esef, dach) if len(x)]
    for d in srcs:
        d["company_name"] = d.company_id.map(name)
        for c in ("period_start", "period_end"):
            d[c] = d[c].astype(str).str[:10]
    both = pd.concat([d[[c for c in KEEP if c in d]] for d in srcs], ignore_index=True)
    # same company and year from several sources: higher confidence first, then the DACH reading, then SEC, then ESEF
    both["_src_rank"] = both.dpo_source.map({"dach_annual_report": -1, "sec": 0, "esef": 1}).fillna(1)
    both["_has"] = both.dpo.isna().astype(int)
    both = both.sort_values(["company_id", "fiscal_year", "_has", "confidence", "_src_rank"],
                            ascending=[True, False, True, False, True])
    both = both.drop_duplicates(["company_id", "fiscal_year"], keep="first")
    both["year_rank"] = both.groupby("company_id").fiscal_year.rank(method="first", ascending=False).astype(int)
    both = both[both.year_rank <= 2].drop(columns=["_src_rank", "_has"])

    # universe sector overrides the filing-level flag for financials
    both["sector"] = both.company_id.map(sector)
    fin = both.sector == "financials"
    both.loc[fin, "dpo"] = None
    both.loc[fin, "dpo_flag"] = "not_applicable"

    # only clean rows feed the sector median
    ok = both[(both.dpo_flag == "ok") & (both.year_rank == 1) & (both.confidence >= 1.0)]
    med = ok.groupby("sector").dpo.agg(["median", "count"]).rename(columns={"median": "sector_median_dpo", "count": "sector_n"})
    both = both.merge(med, left_on="sector", right_index=True, how="left")
    both["dpo"] = both.dpo.round(1)
    both["sector_median_dpo"] = both.sector_median_dpo.round(1)

    both.to_parquet(OUT / "dpo.parquet", index=False)
    both.to_csv(OUT / "dpo.csv", index=False)
    return both


if __name__ == "__main__":
    d = build()
    latest = d[d.year_rank == 1]
    print("rows", len(d), "companies", d.company_id.nunique())
    print(latest.dpo_flag.value_counts().to_dict())
    print(latest.dpo_source.value_counts().to_dict())
    print(latest[latest.dpo_flag == "ok"].groupby("sector").dpo.median().round(1).to_dict())
