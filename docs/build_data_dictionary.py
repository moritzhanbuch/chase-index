#!/usr/bin/env python3
"""Generate docs/data_dictionary.md from the processed tables plus the per-source dictionaries.

    .venv/bin/python docs/build_data_dictionary.py
"""
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
P = ROOT / "data" / "processed"

TABLES = {
    "companies": "Master table. One row per universe company with identifiers, reported UK and Spanish figures, computed DPO, scores, tier, signals, estimates and rationale. INTERNAL: contains sales scoring.",
    "universe": "The Global 2000-style company universe (revenue >= USD 4B), merged from SEC, ESEF and Wikidata.",
    "uk_payment_practices": "Every UK statutory payment-practices report (one row per report, full history).",
    "uk_entity_latest": "One row per UK legal entity: latest usable report, previous report, year-on-year comparison.",
    "uk_entity_group_map": "Accepted links from UK legal entities to universe groups, with method and confidence.",
    "uk_group_metrics": "UK figures aggregated per universe group over its matched entities with a current report.",
    "es_pmp": "Spain: statutory average supplier payment period (PMP) for IBEX 35 companies, FY2025, after dual extraction and adjudication.",
    "dpo": "Computed DPO (proxy) per company and fiscal year (latest two), from SEC and ESEF XBRL facts.",
    "scores": "Scores, tier and rationale per company (subset of the master table).",
}

DESC = {
    "company_id": "Stable id: slug of the name plus the Wikidata QID, SEC CIK or LEI suffix",
    "source_url": "Where the row's primary data point can be checked", "source_type": "Kind of source",
    "retrieved_at": "ISO timestamp of retrieval", "period_start": "Start of the period the data covers",
    "period_end": "End of the period the data covers", "extraction_method": "How the value was obtained",
    "confidence": "0 to 1. 1.0 = official structured data; lower for fallbacks, community data or probabilistic links",
    "sector": "One of 14 coarse sectors", "sector_method": "sic_code, llm_classification, wikidata_industry_keyword, name_keyword or default",
    "revenue_usd": "Revenue converted to USD with approximate rates (size screen only)",
    "revenue_stale": "True when the revenue figure is older than 2022 or undated",
    "uk_entities_n": "Matched UK legal entities with a current usable report",
    "uk_avg_days_to_pay_mean": "Average reported days to pay across the group's matched UK entities (weighted by invoice value where every entity reports it; see uk_days_aggregation)",
    "uk_avg_days_to_pay_simple_mean": "Unweighted mean of the same",
    "uk_days_aggregation": "invoice_value_weighted_mean or simple_mean",
    "uk_pct_paid_late_mean": "Share of invoices not paid within agreed terms, %, same aggregation; entities with an inconsistent late share are excluded",
    "uk_pct_paid_over_60_mean": "Share of invoices paid after 60 days, %",
    "uk_trend_days_yoy_mean": "Mean year-on-year change in average days to pay across entities with a comparable prior report (positive = slower)",
    "uk_value_paid_total_gbp": "Invoice value the matched entities report paying in their latest half-year reports, GBP",
    "uk_worst_entity_name": "The matched UK entity with the longest average days to pay",
    "uk_min_match_confidence": "Lowest entity-to-group match confidence among the matched entities",
    "es_pmp_days": "Spain: statutory average supplier payment period in days (PMP)",
    "es_scope": "consolidated_spanish_entities, parent_only or unknown",
    "dpo": "Computed DPO (proxy) = payables / cost of sales x 365, latest fiscal year",
    "dpo_flag": "ok, suspicious_low, suspicious_high, not_applicable (financials) or missing_inputs",
    "dpo_sector_median": "Median DPO of clean rows in the same sector",
    "fit_score": "0 to 100, see methodology", "pain_score": "0 to 100, see methodology", "signal_score": "0 to 100, see methodology",
    "pain_evidence_tier": "1 = reported data, 2 = computed proxy, null = none", "pain_basis": "uk_reported, es_reported, computed_dpo_proxy or no_evidence",
    "pain_days": "The days figure the pain score used", "priority_tier": "1, 2 or 3", "base_tier": "Tier before a signal upgrade",
    "excluded_reason": "Why a company is held in Tier 3 regardless of score", "priority_score": "Weighted mix of pain, fit and signal (weights in config/assumptions.yaml); orders companies inside a tier",
    "signals": "JSON list of why-now signals, each with text and evidence URL", "rationale": "Short written reason; cites only fields of the row",
    "estimate": "Always true: marks every est_* column as an estimate",
    "est_uk_annual_payments_gbp": "ESTIMATE base: reported half-year invoice value of matched UK entities x 2",
    "est_uk_discount_base": "ESTIMATE: early-payment discount opportunity per year, UK scope, base scenario (GBP)",
    "est_group_spend_proxy": "ESTIMATE base: cost of sales, or revenue x assumed external-spend ratio",
    "est_group_discount_base": "ESTIMATE: early-payment discount opportunity per year, group illustrative, base scenario",
    "match_method": "wikidata_company_number, ch_psc_chain, exact_name, wikidata_subsidiary_name or brand_prefix",
    "match_confidence": "Confidence of the entity-to-group link (0.75 to 0.97)",
    "avg_days_to_pay": "Average number of days taken to pay invoices, as reported", "pct_paid_late": "Share of invoices not paid within agreed terms, %",
    "pct_paid_within_30": "Share of invoices paid within 30 days, %", "pct_paid_over_60": "Share of invoices paid after 60 days, %",
    "is_usable": "False when the report is flagged as unusable (see quality_flag)", "quality_flag": "Why a row needs care; null when clean",
    "pmp_days": "Statutory average supplier payment period, days", "ratio_paid_days": "Ratio of paid operations, days",
    "ratio_pending_days": "Ratio of operations pending payment, days", "field_resolution": "JSON: per field, both_agree / adjudicated / both_null / unresolved",
}

out = ["# Data dictionary", "", "Independent project by Moritz Hanbuch.", "",
       "Generated by `docs/build_data_dictionary.py` from the tables in `data/processed/` (parquet and csv). "
       "Columns without a description here are documented in the per-source sections at the end.", ""]
for t, what in TABLES.items():
    f = P / f"{t}.parquet"
    if not f.exists():
        continue
    df = pd.read_parquet(f)
    out += [f"## `{t}`", "", what, "", f"Rows: {len(df):,}. Columns: {len(df.columns)}.", "", "| Column | Type | Meaning |", "|---|---|---|"]
    for c in df.columns:
        d = DESC.get(c, "")
        if not d and c.startswith("est_"):
            d = "ESTIMATE, see methodology (Estimates)"
        if not d and c.startswith("prev_"):
            d = "Same field from the previous report"
        if not d and c.startswith("yoy_"):
            d = "Same field from the report one year earlier"
        out.append(f"| `{c}` | {df[c].dtype} | {d} |")
    out.append("")
for f in ["uk", "sec", "esef", "wikidata", "companies_house"]:
    p = ROOT / "docs" / f"data_dictionary_{f}.md"
    if p.exists():
        body = "\n".join(("#" + l if l.startswith("#") else l) for l in p.read_text().strip().splitlines())
        out += ["---", "", body, ""]
(ROOT / "docs" / "data_dictionary.md").write_text("\n".join(out) + "\n")
print("wrote docs/data_dictionary.md", len(out), "lines")
