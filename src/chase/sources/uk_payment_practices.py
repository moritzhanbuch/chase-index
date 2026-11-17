"""UK Payment Practices and Performance Reporting (statutory, since 2017): download + parse.

Source   : https://check-payment-practices.service.gov.uk/export/csv/  (one CSV, every published report)
Licence  : Open Government Licence v3.0
Run      : python -m chase.sources.uk_payment_practices [--refresh]

Outputs (data/processed/):
  uk_payment_practices.parquet/.csv   one row per report (entity x reporting period), full history
  uk_entity_latest.parquet/.csv       one row per Companies House number: latest usable report,
                                      previous report, report ~1 year earlier, trends
  uk_official_benchmarks.csv          DBT official statistics (medians) by year / sector / region
Plus evals/reports/uk_ingest_reconciliation.md and data/manifests/uk_payment_practices.json.

Nothing is dropped. Problem reports get a `quality_flag` and `is_usable=False`. See docs/sources/uk.md
and docs/data_dictionary_uk.md.
"""
from __future__ import annotations

import csv
import html
import json
import re
import sys
import zipfile
from pathlib import Path

import numpy as np
import pandas as pd

from chase.common.http import ROOT, fetch_to_file, now_iso, write_manifest

EXPORT_PAGE = "https://check-payment-practices.service.gov.uk/export/"
EXPORT_URL = "https://check-payment-practices.service.gov.uk/export/csv/"
REPORT_URL = "https://check-payment-practices.service.gov.uk/report/{report_id}"
STATS_PAGE = "https://www.gov.uk/government/statistics/large-businesses-payment-practices-and-performance-statistics-2025"
STATS_TABLES_URL = ("https://assets.publishing.service.gov.uk/media/6a54be41c3d64d94cacab833/"
                    "large-business-payment-practices-and-performance-statistics-2025-reference-tables.ods")
STATS_METHOD_URL = ("https://assets.publishing.service.gov.uk/media/6a50c8a69e9c95844ae64ca1/"
                    "large-business-payment-practices-statistics-methodology-and-background-quality-report.pdf")

RAW_DIR = ROOT / "data" / "raw" / "uk"
RAW_CSV = RAW_DIR / "payment_practices_export.csv"
RAW_ODS = RAW_DIR / "dbt_payment_practices_statistics_2025_reference_tables.ods"
RAW_METHOD_PDF = RAW_DIR / "dbt_payment_practices_statistics_methodology.pdf"
PROCESSED = ROOT / "data" / "processed"
MANIFEST_NAME = "uk_payment_practices"
MANIFEST = ROOT / "data" / "manifests" / f"{MANIFEST_NAME}.json"
RECON_MD = ROOT / "evals" / "reports" / "uk_ingest_reconciliation.md"

SOURCE_TYPE = "uk_ppr_statutory_report"
EXTRACTION_METHOD = "official_csv_export"

# raw header -> clean name
RENAME = {
    "Report Id": "report_id",
    "Policy Regime": "policy_regime",
    "Financial period start date": "financial_period_start",
    "Start date": "period_start",
    "End date": "period_end",
    "Filing date": "filing_date",
    "Company": "company_name",
    "Company number": "company_number",
    "Qualifying contracts in reporting period": "had_qualifying_contracts",
    "Payments made in reporting period": "payments_made_in_period",
    "Qualifying construction contracts in reporting period": "had_qualifying_construction_contracts",
    "Construction contracts have retention clauses": "construction_contracts_have_retention_clauses",
    "Average time to pay": "avg_days_to_pay",
    "Total value invoices paid within 30 days": "value_paid_within_30_gbp",
    "Total value invoices paid between 31 and 60 days": "value_paid_31_60_gbp",
    "Total value invoices paid later than 60 days": "value_paid_over_60_gbp",
    "% Invoices paid within 30 days": "pct_paid_within_30",
    "% Invoices paid between 31 and 60 days": "pct_paid_31_60",
    "% Invoices paid later than 60 days": "pct_paid_over_60",
    "Total value invoices paid later than agreed terms": "value_paid_late_gbp",
    "% Invoices not paid within agreed terms": "pct_paid_late",
    "% Invoices not paid due to dispute": "pct_not_paid_due_to_dispute",
    "Shortest (or only) standard payment period": "shortest_standard_payment_period_days",
    "Longest standard payment period": "longest_standard_payment_period_days",
    "Standard payment terms": "standard_payment_terms_text",
    "Payment terms have changed": "payment_terms_changed_text",
    "Suppliers notified of changes": "suppliers_notified_of_changes_text",
    "Maximum contractual payment period": "max_contractual_payment_period_days",
    "Maximum contractual payment period information": "max_contractual_payment_period_info_text",
    "Other information payment terms": "other_payment_terms_info_text",
    "Retention clauses included in all construction contracts": "retention_in_all_construction_contracts",
    "Retention clauses included in standard payment terms": "retention_in_standard_payment_terms",
    "Retention clauses are used in specific circumstances": "retention_in_specific_circumstances",
    "Description of specific circumstances for retention clauses": "retention_specific_circumstances_text",
    "Retention clauses used above a specific sum": "retention_above_specific_sum",
    "Value above which retention clauses are used": "retention_threshold_value_gbp",
    "Retention clauses are at a standard rate": "retention_at_standard_rate",
    "Retention clauses standard rate percentage": "retention_standard_rate_pct",
    "Retention clauses have parity with client": "retention_parity_with_client",
    "Description of parity policy": "retention_parity_policy_text",
    "Retention clause money release description": "retention_release_text",
    "Retention clause money release is staged": "retention_release_is_staged",
    "Description of stages for money release": "retention_release_stages_text",
    "Retention value compared to client retentions as %": "retention_value_vs_client_retentions_pct",
    "Retention value compared to total payments as %": "retention_value_vs_total_payments_pct",
    "Dispute resolution process": "dispute_resolution_process_text",
    "Participates in payment codes": "payment_codes_text",
    "E-Invoicing offered": "offers_einvoicing",
    "Supply-chain financing offered": "offers_supply_chain_finance",
    "Policy covers charges for remaining on supplier list": "policy_covers_supplier_list_charges",
    "Charges have been made for remaining on supplier list": "charged_for_supplier_list",
    "URL": "report_url",
}
DATE_COLS = ["financial_period_start", "period_start", "period_end", "filing_date"]
BOOL_COLS = [
    "had_qualifying_contracts", "payments_made_in_period", "had_qualifying_construction_contracts",
    "construction_contracts_have_retention_clauses", "retention_in_all_construction_contracts",
    "retention_in_standard_payment_terms", "retention_in_specific_circumstances",
    "retention_above_specific_sum", "retention_at_standard_rate", "retention_parity_with_client",
    "retention_release_is_staged", "offers_einvoicing", "offers_supply_chain_finance",
    "policy_covers_supplier_list_charges", "charged_for_supplier_list",
]
NUM_COLS = [
    "avg_days_to_pay", "value_paid_within_30_gbp", "value_paid_31_60_gbp", "value_paid_over_60_gbp",
    "pct_paid_within_30", "pct_paid_31_60", "pct_paid_over_60", "value_paid_late_gbp", "pct_paid_late",
    "pct_not_paid_due_to_dispute", "shortest_standard_payment_period_days",
    "longest_standard_payment_period_days", "max_contractual_payment_period_days",
    "retention_threshold_value_gbp", "retention_standard_rate_pct",
    "retention_value_vs_client_retentions_pct", "retention_value_vs_total_payments_pct",
]
CORE_METRICS = ["avg_days_to_pay", "pct_paid_within_30", "pct_paid_31_60", "pct_paid_over_60", "pct_paid_late"]
# Long narrative fields: kept in parquet, left out of the CSV copy to keep it small.
LONG_TEXT_COLS = [c for c in RENAME.values() if c.endswith("_text") and c not in
                  ("standard_payment_terms_text", "payment_codes_text")]

# Flags that make a report unusable for company-level metrics. Everything else is informational.
HARD_FLAGS = {
    "no_qualifying_contracts", "no_payments_made", "metrics_missing",
    "period_dates_implausible", "period_length_out_of_range", "filed_gt_1m_before_period_end",
    "avg_days_gt_365", "pct_buckets_sum_off", "value_total_zero", "value_late_exceeds_total",
    "superseded_by_later_report",
}
# The subset the official DBT statistics use to drop reports (methodology annex "Data preparation").
DBT_FLAGS = HARD_FLAGS - {"avg_days_gt_365", "pct_buckets_sum_off", "period_dates_implausible"}
SOFT_FLAGS = {"pct_late_inconsistent_with_buckets", "avg_days_zero", "payment_terms_gt_365"}

NO_CODE_VALUES = {"no", "n/a", "na", "none", "nil", "not applicable", ".", "..", "-", ""}
MIN_PERIOD_DAYS, MAX_PERIOD_DAYS = 150, 215   # "shorter than 5 months / longer than 7 months" (DBT)
EARLIEST_PLAUSIBLE_START = pd.Timestamp("2016-01-01")  # regulations apply to FYs starting on/after 6 Apr 2017


# --------------------------------------------------------------------------- download

def download(refresh: bool = False) -> dict:
    """Fetch the export (and the official statistics files) through the shared polite client."""
    kw = {"use_cache": not refresh}
    entry = fetch_to_file(EXPORT_URL, RAW_CSV, **kw)
    extras = [fetch_to_file(STATS_TABLES_URL, RAW_ODS, **kw), fetch_to_file(STATS_METHOD_URL, RAW_METHOD_PDF, **kw)]
    manifest = {
        "url": EXPORT_URL, "landing_page": EXPORT_PAGE, "licence": "Open Government Licence v3.0",
        "path": entry["path"], "sha256": entry["sha256"], "bytes": entry["bytes"],
        "retrieved_at": entry["retrieved_at"], "content_type": entry["content_type"],
        "related_files": extras,
    }
    write_manifest(MANIFEST_NAME, manifest)
    return manifest


def load_manifest() -> dict:
    return json.loads(MANIFEST.read_text())


# --------------------------------------------------------------------------- parse

def count_csv_records(path: Path) -> int:
    """Independent count of data records with the stdlib csv module (fields contain newlines)."""
    with open(path, newline="", encoding="utf-8") as f:
        return sum(1 for _ in csv.reader(f)) - 1


def _to_bool(s: pd.Series) -> pd.Series:
    return s.map({"True": True, "False": False}).astype("boolean")


def _to_date(s: pd.Series) -> pd.Series:
    # Out-of-range years exist in the source (e.g. 3025). Coerce at second resolution so they survive
    # as dates and can be flagged instead of silently becoming null.
    return pd.to_datetime(s.replace({"None": None, "": None}), format="%Y-%m-%d", errors="coerce").astype("datetime64[s]")


def reporting_year(start: pd.Series, end: pd.Series) -> pd.Series:
    """Calendar year containing most of the period; ties go to the starting year (DBT method)."""
    out = start.dt.year.astype("Int64")
    cross = (end.dt.year > start.dt.year) & start.notna() & end.notna()
    year_end = pd.to_datetime(start.dt.year.astype("Int64").astype(str) + "-12-31", errors="coerce").astype("datetime64[s]")
    days_first = (year_end - start).dt.days + 1
    days_total = (end - start).dt.days + 1
    later = cross & ((days_total - days_first) > days_first)
    out = out.where(~later, end.dt.year.astype("Int64"))
    return out


def _mark_superseded(df: pd.DataFrame) -> pd.Series:
    """For each company, where reports cover the same period or overlap by more than one month,
    keep the most recently filed one (DBT method). Returns the superseding report_id or <NA>.

    Preference order: plausible period first, then reports that carry metrics, then latest filing
    date, then highest report id. Only reports with a plausible period can supersede others.
    """
    sup = pd.Series(pd.NA, index=df.index, dtype="Int64")
    dup_company = df["company_number"].duplicated(keep=False)
    work = df.loc[dup_company, ["company_number", "report_id", "period_start", "period_end", "filing_date"]].copy()
    work["_period_ok"] = df.loc[dup_company, "_period_ok"]
    work["_has_metrics"] = df.loc[dup_company, "_has_metrics"]
    work = work.sort_values(["company_number", "_period_ok", "_has_metrics", "filing_date", "report_id"],
                            ascending=[True, False, False, False, False])
    day = np.timedelta64(1, "D")
    for _, g in work.groupby("company_number", sort=False):
        starts = g["period_start"].to_numpy()
        ends = g["period_end"].to_numpy()
        ok = g["_period_ok"].to_numpy()
        ids = g["report_id"].to_numpy()
        idx = g.index.to_numpy()
        kept: list[int] = []
        for i in range(len(g)):
            hit = None
            for k in kept:
                same = starts[i] == starts[k] and ends[i] == ends[k]
                overlap = (min(ends[i], ends[k]) - max(starts[i], starts[k])) / day + 1
                if same or overlap > 30:
                    hit = k
                    break
            if hit is None:
                if ok[i]:
                    kept.append(i)
            else:
                sup.loc[idx[i]] = ids[hit]
    return sup


def parse(raw_csv: Path, retrieved_at: str, export_url: str = EXPORT_URL) -> pd.DataFrame:
    """Parse the raw export into the one-row-per-report table. No rows are dropped."""
    raw = pd.read_csv(raw_csv, dtype=str, keep_default_na=False, encoding="utf-8")
    missing = [c for c in RENAME if c not in raw.columns]
    if missing:
        raise ValueError(f"export schema changed, missing columns: {missing}")
    extra = [c for c in raw.columns if c not in RENAME]
    df = raw.rename(columns=RENAME)
    if extra:  # keep unknown new columns as text rather than losing them
        df = df.rename(columns={c: "raw_" + re.sub(r"\W+", "_", c.strip().lower()).strip("_") for c in extra})

    df["report_id"] = pd.to_numeric(df["report_id"], errors="raise").astype("int64")
    df["company_name"] = df["company_name"].str.strip()
    df["company_number"] = df["company_number"].str.strip().str.upper().str.zfill(8)
    for c in DATE_COLS:
        df[c] = _to_date(df[c])
    for c in BOOL_COLS:
        df[c] = _to_bool(df[c])
    for c in NUM_COLS:
        df[c] = pd.to_numeric(df[c].replace("", None), errors="coerce").astype("float64")
    text_cols = [c for c in df.columns if c.endswith("_text")]
    for c in text_cols:
        df[c] = df[c].str.strip().replace("", None)

    # Regime-1 (pre-2025 rules) did not collect value-of-late-payments or the dispute share; the
    # export shows a placeholder 0 there. Treat that 0 as "not collected".
    r1 = df["policy_regime"] == "Regime-1"
    for c in ("value_paid_late_gbp", "pct_not_paid_due_to_dispute"):
        df.loc[r1 & (df[c] == 0), c] = np.nan

    # payment codes
    code_txt = df["payment_codes_text"].fillna("").str.strip()
    df["participates_in_payment_codes"] = ~code_txt.str.lower().isin(NO_CODE_VALUES)
    df["mentions_prompt_payment_code"] = code_txt.str.contains(r"prompt\s*payment|\bPPC\b", case=False, regex=True)
    df["mentions_fair_payment_code"] = code_txt.str.contains(r"fair\s*payment\s*code|\bFPC\b", case=False, regex=True)
    for c in ("participates_in_payment_codes", "mentions_prompt_payment_code", "mentions_fair_payment_code"):
        df[c] = df[c].astype("boolean")

    # derived
    df["period_days"] = ((df["period_end"] - df["period_start"]).dt.days + 1).astype("Int64")
    df["reporting_year"] = reporting_year(df["period_start"], df["period_end"])
    total_val = df[["value_paid_within_30_gbp", "value_paid_31_60_gbp", "value_paid_over_60_gbp"]].sum(axis=1, min_count=3)
    df["value_paid_total_gbp"] = total_val
    df["pct_value_paid_late"] = np.where((total_val > 0) & (df["value_paid_late_gbp"] <= total_val),
                                         100 * df["value_paid_late_gbp"] / total_val, np.nan).round(2)

    # ---- quality flags
    has_metrics = df[CORE_METRICS].notna().all(axis=1)
    retrieved = pd.Timestamp(retrieved_at[:10])
    dates_bad = (df["period_start"].isna() | df["period_end"].isna() | (df["period_start"] < EARLIEST_PLAUSIBLE_START)
                 | (df["period_end"] < df["period_start"]) | (df["period_end"] > retrieved + pd.Timedelta(days=366)))
    length_bad = (df["period_days"] < MIN_PERIOD_DAYS) | (df["period_days"] > MAX_PERIOD_DAYS)
    early = (df["period_end"] - df["filing_date"]).dt.days > 31
    df["_period_ok"] = ~(dates_bad | length_bad.fillna(True))
    df["_has_metrics"] = has_metrics
    bucket_sum = df[["pct_paid_within_30", "pct_paid_31_60", "pct_paid_over_60"]].sum(axis=1, min_count=3)
    # Logical bound: if the shortest standard term is >= 30 (60) days, invoices paid within 30 (60) days
    # were on time, so the late share cannot exceed the rest by much. A large gap suggests the company
    # entered the on-time share instead of the late share. Informational only (bases differ slightly).
    bound = pd.Series(np.nan, index=df.index)
    s = df["shortest_standard_payment_period_days"]
    bound = bound.where(~(s >= 30), 100 - df["pct_paid_within_30"])
    bound = bound.where(~(s >= 60), 100 - df["pct_paid_within_30"] - df["pct_paid_31_60"])
    terms = df[["shortest_standard_payment_period_days", "longest_standard_payment_period_days",
                "max_contractual_payment_period_days"]]
    df["superseded_by_report_id"] = _mark_superseded(df)

    flag_masks = {
        "no_qualifying_contracts": df["had_qualifying_contracts"].eq(False),
        "no_payments_made": df["had_qualifying_contracts"].eq(True) & df["payments_made_in_period"].eq(False) & ~has_metrics,
        "metrics_missing": df["had_qualifying_contracts"].eq(True) & df["payments_made_in_period"].eq(True) & ~has_metrics,
        "period_dates_implausible": dates_bad,
        "period_length_out_of_range": length_bad.fillna(False) & ~dates_bad,
        "filed_gt_1m_before_period_end": early.fillna(False) & ~dates_bad,
        "avg_days_gt_365": df["avg_days_to_pay"] > 365,
        "pct_buckets_sum_off": bucket_sum.notna() & ((bucket_sum < 98) | (bucket_sum > 102)),
        "value_total_zero": total_val.notna() & (total_val == 0) & has_metrics,
        "value_late_exceeds_total": total_val.notna() & (df["value_paid_late_gbp"] > total_val),
        "superseded_by_later_report": df["superseded_by_report_id"].notna(),
        "pct_late_inconsistent_with_buckets": bound.notna() & (df["pct_paid_late"] > bound + 10),
        "avg_days_zero": df["avg_days_to_pay"] == 0,
        "payment_terms_gt_365": (terms > 365).any(axis=1),
    }
    assert set(flag_masks) == HARD_FLAGS | SOFT_FLAGS
    flags = pd.Series("", index=df.index)
    hard = pd.Series(False, index=df.index)
    dbt_bad = pd.Series(False, index=df.index)
    for name, mask in flag_masks.items():
        mask = mask.fillna(False).astype(bool)
        flags = flags.where(~mask, flags + ";" + name)
        if name in HARD_FLAGS:
            hard |= mask
        if name in DBT_FLAGS:
            dbt_bad |= mask
    df["quality_flag"] = flags.str.lstrip(";").replace("", "ok")
    df["is_usable"] = (~hard & has_metrics).astype("boolean")
    df["is_valid_dbt_method"] = (~dbt_bad & has_metrics).astype("boolean")
    df = df.drop(columns=["_period_ok", "_has_metrics"])

    # ---- provenance (rule 7)
    df["source_url"] = df["report_url"].where(df["report_url"].str.startswith("https://check-payment-practices.service.gov.uk/report/"),
                                              export_url)
    df["source_export_url"] = export_url
    df["source_type"] = SOURCE_TYPE
    df["retrieved_at"] = retrieved_at
    df["extraction_method"] = EXTRACTION_METHOD
    df["confidence"] = 1.0
    df = df.drop(columns=["report_url"])

    for c in DATE_COLS:  # store as plain dates
        df[c] = df[c].dt.date
    lead = ["report_id", "company_name", "company_number", "period_start", "period_end", "filing_date",
            "reporting_year", "period_days", "policy_regime", "financial_period_start", *CORE_METRICS,
            "pct_not_paid_due_to_dispute", "value_paid_within_30_gbp", "value_paid_31_60_gbp",
            "value_paid_over_60_gbp", "value_paid_total_gbp", "value_paid_late_gbp", "pct_value_paid_late",
            "shortest_standard_payment_period_days", "longest_standard_payment_period_days",
            "max_contractual_payment_period_days", "standard_payment_terms_text",
            "participates_in_payment_codes", "mentions_prompt_payment_code", "mentions_fair_payment_code",
            "payment_codes_text", "offers_einvoicing", "offers_supply_chain_finance",
            "quality_flag", "is_usable", "is_valid_dbt_method", "superseded_by_report_id"]
    tail = ["source_url", "source_export_url", "source_type", "retrieved_at", "extraction_method", "confidence"]
    rest = [c for c in df.columns if c not in lead + tail]
    return df[lead + rest + tail].sort_values("report_id").reset_index(drop=True)


# --------------------------------------------------------------------------- entity table

LATEST_COLS = ["policy_regime", *CORE_METRICS, "pct_not_paid_due_to_dispute", "value_paid_total_gbp",
               "value_paid_late_gbp", "pct_value_paid_late", "shortest_standard_payment_period_days",
               "longest_standard_payment_period_days", "max_contractual_payment_period_days",
               "standard_payment_terms_text", "participates_in_payment_codes", "mentions_prompt_payment_code",
               "mentions_fair_payment_code", "payment_codes_text", "offers_einvoicing",
               "offers_supply_chain_finance", "quality_flag"]
COMPARE_COLS = ["report_id", "period_start", "period_end", "avg_days_to_pay", "pct_paid_within_30",
                "pct_paid_over_60", "pct_paid_late"]
YOY_TOLERANCE_DAYS = 92
STALE_AFTER_DAYS = 548  # ~18 months without a usable report


def build_entity_latest(reports: pd.DataFrame) -> pd.DataFrame:
    """One row per Companies House number. 'Latest' = most recent usable report (see is_usable)."""
    r = reports.copy()
    r["_end"] = pd.to_datetime(r["period_end"], errors="coerce").astype("datetime64[s]")
    r["_filed"] = pd.to_datetime(r["filing_date"], errors="coerce").astype("datetime64[s]")
    retrieved_at = r["retrieved_at"].iloc[0]
    retrieved = pd.Timestamp(retrieved_at[:10])
    rows = []
    for number, g in r.groupby("company_number", sort=True):
        g_any = g.sort_values(["_filed", "report_id"])
        last_any = g_any.iloc[-1]
        u = g[g["is_usable"].fillna(False).astype(bool)].sort_values(["_end", "report_id"])
        row: dict = {
            "company_number": number,
            "company_name": (u.iloc[-1] if len(u) else last_any)["company_name"],
            "company_names_all": " | ".join(dict.fromkeys(g_any["company_name"])),
            "n_reports": len(g),
            "n_reports_usable": len(u),
            "has_usable_report": len(u) > 0,
            "first_period_start": u["period_start"].min() if len(u) else None,
            "last_period_end": u["period_end"].max() if len(u) else None,
            "most_recent_filing_report_id": int(last_any["report_id"]),
            "most_recent_filing_date": last_any["filing_date"],
            "most_recent_filing_quality_flag": last_any["quality_flag"],
        }
        if len(u):
            latest = u.iloc[-1]
            row.update(latest_report_id=int(latest["report_id"]), period_start=latest["period_start"],
                       period_end=latest["period_end"], filing_date=latest["filing_date"])
            for c in LATEST_COLS:
                row[c] = latest[c]
            row["latest_is_stale"] = bool((retrieved - latest["_end"]).days > STALE_AFTER_DAYS)
            last2 = u.tail(2)
            row["avg_days_to_pay_mean_last2"] = float(last2["avg_days_to_pay"].mean())
            row["pct_paid_late_mean_last2"] = float(last2["pct_paid_late"].mean())
            row["n_reports_in_mean_last2"] = len(last2)
            prev = u.iloc[-2] if len(u) > 1 else None
            earlier = u.iloc[:-1]
            yoy = None
            if len(earlier):
                gap = (earlier["_end"] - (latest["_end"] - pd.Timedelta(days=365))).abs()
                if gap.min() <= pd.Timedelta(days=YOY_TOLERANCE_DAYS):
                    yoy = earlier.loc[gap.idxmin()]
            for prefix, other in (("prev", prev), ("yoy", yoy)):
                for c in COMPARE_COLS:
                    v = other[c] if other is not None else None
                    row[f"{prefix}_{c}"] = int(v) if (c == "report_id" and v is not None) else v
            if prev is not None:
                row["trend_days_vs_prev"] = float(latest["avg_days_to_pay"] - prev["avg_days_to_pay"])
                row["trend_pct_late_vs_prev"] = float(latest["pct_paid_late"] - prev["pct_paid_late"])
            if yoy is not None:
                row["trend_days_yoy"] = float(latest["avg_days_to_pay"] - yoy["avg_days_to_pay"])
                row["trend_pct_late_yoy"] = float(latest["pct_paid_late"] - yoy["pct_paid_late"])
                row["trend_pct_over_60_yoy"] = float(latest["pct_paid_over_60"] - yoy["pct_paid_over_60"])
            src = latest
        else:
            # No usable report: metrics stay null. Provenance points at the most recent filing so the
            # row is still traceable.
            row.update(period_start=last_any["period_start"], period_end=last_any["period_end"],
                       filing_date=last_any["filing_date"], quality_flag=last_any["quality_flag"])
            src = last_any
        for c in ("source_url", "source_export_url", "source_type", "retrieved_at", "extraction_method", "confidence"):
            row[c] = src[c]
        rows.append(row)
    e = pd.DataFrame(rows)

    front = ["company_number", "company_name", "company_names_all", "n_reports", "n_reports_usable",
             "has_usable_report", "first_period_start", "last_period_end", "latest_report_id",
             "period_start", "period_end", "filing_date", "latest_is_stale", *LATEST_COLS,
             "avg_days_to_pay_mean_last2", "pct_paid_late_mean_last2", "n_reports_in_mean_last2",
             *[f"prev_{c}" for c in COMPARE_COLS], *[f"yoy_{c}" for c in COMPARE_COLS],
             "trend_days_vs_prev", "trend_pct_late_vs_prev", "trend_days_yoy", "trend_pct_late_yoy",
             "trend_pct_over_60_yoy", "most_recent_filing_report_id", "most_recent_filing_date",
             "most_recent_filing_quality_flag",
             "source_url", "source_export_url", "source_type", "retrieved_at", "extraction_method", "confidence"]
    for c in front:
        if c not in e.columns:
            e[c] = None
    e = e[front]
    # dtypes
    for c in ("latest_report_id", "prev_report_id", "yoy_report_id", "n_reports_in_mean_last2"):
        e[c] = pd.to_numeric(e[c], errors="coerce").astype("Int64")
    for c in ("participates_in_payment_codes", "mentions_prompt_payment_code", "mentions_fair_payment_code",
              "offers_einvoicing", "offers_supply_chain_finance", "latest_is_stale", "has_usable_report"):
        e[c] = e[c].astype("boolean")
    float_cols = [c for c in e.columns if any(k in c for k in ("avg_days", "pct_", "trend_", "value_", "_period_days"))
                  or c.endswith("payment_period_days")]
    for c in float_cols:
        e[c] = pd.to_numeric(e[c], errors="coerce").astype("float64")
    for c in ("standard_payment_terms_text", "payment_codes_text", "policy_regime"):
        e[c] = e[c].astype("object").where(e[c].notna(), None)
    return e


# --------------------------------------------------------------------------- official benchmarks

def _ods_tables(path: Path) -> dict[str, list[list[str]]]:
    """Minimal .ods reader (no extra dependency): sheet name -> rows of cell strings."""
    xml = zipfile.ZipFile(path).read("content.xml").decode("utf-8")
    out = {}
    for tm in re.finditer(r'<table:table table:name="([^"]+)".*?</table:table>', xml, re.S):
        rows = []
        for row in re.findall(r"<table:table-row.*?</table:table-row>", tm.group(0), re.S):
            cells: list[str] = []
            for cm in re.finditer(r"<table:(?:covered-)?table-cell([^>]*?)(?:/>|>(.*?)</table:(?:covered-)?table-cell>)", row, re.S):
                attrs, inner = cm.group(1), cm.group(2) or ""
                rep = re.search(r'number-columns-repeated="(\d+)"', attrs)
                val = re.search(r'office:value="([^"]+)"', attrs)
                text = html.unescape(re.sub(r"<[^>]+>", "", inner)).strip()
                value = val.group(1) if val else text
                n = int(rep.group(1)) if rep else 1
                cells.extend([value] * (n if n < 50 else 1))
            while cells and cells[-1] == "":
                cells.pop()
            if cells:
                rows.append(cells)
        out[tm.group(1)] = rows
    return out


def build_official_benchmarks(ods: Path, retrieved_at: str) -> pd.DataFrame:
    """DBT official statistics (medians across valid reports) in long format."""
    tables = _ods_tables(ods)
    recs = []
    for sheet, rows in tables.items():
        if not sheet.lower().startswith("table"):
            continue
        title = rows[0][0]
        hdr_i = next(i for i, r in enumerate(rows) if r[0] in ("Reporting Year", "ITL1 region", "SIC section"))
        hdr = rows[hdr_i]
        for r in rows[hdr_i + 1:]:
            r = r + [""] * (len(hdr) - len(r))
            if hdr[0] == "Reporting Year":
                for metric, v in zip(hdr[1:], r[1:]):
                    recs.append(("headline", "UK", r[0], metric, v, title))
            else:
                metric = title.split(":", 1)[1].split(" - ")[0].strip()
                kind = "region" if hdr[0] == "ITL1 region" else "sic_section"
                for year, v in zip(hdr[1:], r[1:]):
                    recs.append((kind, r[0], year, metric, v, title))
    b = pd.DataFrame(recs, columns=["breakdown_type", "breakdown", "reporting_year", "metric", "value", "table_title"])
    b["value"] = pd.to_numeric(b["value"].str.replace(",", ""), errors="coerce")
    b = b.dropna(subset=["value"])
    b["reporting_year"] = pd.to_numeric(b["reporting_year"].astype(str).str.extract(r"(\d{4})")[0]).astype("Int64")
    b["statistic"] = np.where(b["metric"].str.contains("Number of valid reports"), "count", "median")
    b["source_url"] = STATS_TABLES_URL
    b["source_page"] = STATS_PAGE
    b["source_type"] = "uk_dbt_official_statistics"
    b["retrieved_at"] = retrieved_at
    b["period_start"] = pd.to_datetime(b["reporting_year"].astype(str) + "-01-01").dt.date
    b["period_end"] = pd.to_datetime(b["reporting_year"].astype(str) + "-12-31").dt.date
    b["extraction_method"] = "official_ods_reference_tables"
    b["confidence"] = 1.0
    return b.reset_index(drop=True)


# --------------------------------------------------------------------------- write + reconcile

def write_tables(reports: pd.DataFrame, entities: pd.DataFrame, out_dir: Path = PROCESSED) -> None:
    out_dir.mkdir(parents=True, exist_ok=True)
    reports.to_parquet(out_dir / "uk_payment_practices.parquet", index=False)
    reports.drop(columns=[c for c in LONG_TEXT_COLS if c in reports.columns]).to_csv(out_dir / "uk_payment_practices.csv", index=False)
    entities.to_parquet(out_dir / "uk_entity_latest.parquet", index=False)
    entities.to_csv(out_dir / "uk_entity_latest.csv", index=False)


def reconcile(raw_csv: Path, reports: pd.DataFrame, entities: pd.DataFrame, manifest: dict,
              benchmarks: pd.DataFrame | None) -> str:
    n_raw = count_csv_records(raw_csv)
    raw_ids = pd.read_csv(raw_csv, dtype=str, keep_default_na=False, usecols=["Report Id", "Company number", "Average time to pay"])
    pq = pd.read_parquet(PROCESSED / "uk_payment_practices.parquet")
    csv_rows = len(pd.read_csv(PROCESSED / "uk_payment_practices.csv", usecols=["report_id"]))
    ent_pq = pd.read_parquet(PROCESSED / "uk_entity_latest.parquet")
    checks = [
        ("Records in raw CSV (stdlib csv reader)", n_raw, len(pq), n_raw == len(pq)),
        ("Rows in processed CSV copy", n_raw, csv_rows, n_raw == csv_rows),
        ("Distinct report ids", raw_ids["Report Id"].nunique(), pq["report_id"].nunique(),
         raw_ids["Report Id"].nunique() == pq["report_id"].nunique()),
        ("Distinct company numbers", raw_ids["Company number"].nunique(), pq["company_number"].nunique(),
         raw_ids["Company number"].nunique() == pq["company_number"].nunique()),
        ("Rows in entity table = distinct company numbers", raw_ids["Company number"].nunique(), len(ent_pq),
         raw_ids["Company number"].nunique() == len(ent_pq)),
        ("Reports with a non-empty 'Average time to pay'", int((raw_ids["Average time to pay"] != "").sum()),
         int(pq["avg_days_to_pay"].notna().sum()),
         int((raw_ids["Average time to pay"] != "").sum()) == int(pq["avg_days_to_pay"].notna().sum())),
        ("Sum of 'Average time to pay' (checksum)", float(pd.to_numeric(raw_ids["Average time to pay"]).sum()),
         float(pq["avg_days_to_pay"].sum()),
         abs(float(pd.to_numeric(raw_ids["Average time to pay"]).sum()) - float(pq["avg_days_to_pay"].sum())) < 1e-6),
    ]
    L = []
    L.append("# UK payment practices: ingest reconciliation\n")
    L.append(f"- Generated: {now_iso()} by `python -m chase.sources.uk_payment_practices`")
    L.append(f"- Source: {manifest['url']} (retrieved {manifest['retrieved_at']}, {manifest['bytes']:,} bytes, sha256 `{manifest['sha256']}`)")
    L.append("- What was checked: every record in the raw export arrives in the processed tables, nothing dropped, nothing duplicated.")
    L.append("- Method: independent count with Python's `csv` module (fields contain line breaks, so `wc -l` is not a valid count) compared with the parquet and CSV outputs.\n")
    L.append("## 1. Row reconciliation\n")
    L.append("| Check | Raw export | Processed | Result |\n|---|---:|---:|---|")
    for name, a, b, ok in checks:
        fa = f"{a:,.0f}" if isinstance(a, (int, float)) else str(a)
        fb = f"{b:,.0f}" if isinstance(b, (int, float)) else str(b)
        L.append(f"| {name} | {fa} | {fb} | {'PASS' if ok else 'FAIL'} |")
    all_ok = all(c[3] for c in checks)
    L.append(f"\n**Result: {'all checks pass' if all_ok else 'FAILURES, see table'}.**\n")

    usable = pq[pq["is_usable"].fillna(False).astype(bool)]
    L.append("## 2. Coverage\n")
    L.append(f"- Reports: {len(pq):,} (report ids {pq['report_id'].min()} to {pq['report_id'].max()})")
    L.append(f"- Distinct entities (Companies House numbers): {pq['company_number'].nunique():,}; distinct company names: {pq['company_name'].nunique():,}")
    L.append(f"- Filing dates: {pq['filing_date'].min()} to {pq['filing_date'].max()}")
    L.append(f"- Period range, all rows as reported (includes obvious typos): {pq['period_start'].min()} to {pq['period_end'].max()}")
    L.append(f"- Period range, usable reports only: {usable['period_start'].min()} to {usable['period_end'].max()}")
    L.append(f"- Usable reports (`is_usable`): {len(usable):,} ({len(usable) / len(pq):.1%}); entities with at least one usable report: {int(ent_pq['has_usable_report'].sum()):,}")
    cur = ent_pq[ent_pq["has_usable_report"].fillna(False).astype(bool) & ~ent_pq["latest_is_stale"].fillna(True).astype(bool)]
    L.append(f"- Entities whose latest usable report is recent (period ended within ~18 months of retrieval): {len(cur):,}")
    L.append(f"- Entities with a year-on-year trend (`trend_days_yoy` not null): {int(ent_pq['trend_days_yoy'].notna().sum()):,}")
    L.append("- Reports by policy regime: " + ", ".join(f"{k}: {v:,}" for k, v in pq["policy_regime"].value_counts().sort_index().items()) + "\n")

    L.append("## 3. Quality flags (a report can carry several; nothing is dropped)\n")
    L.append("| Flag | Reports | Makes report unusable |\n|---|---:|---|")
    exploded = pq["quality_flag"].str.split(";").explode().value_counts()
    for flag, n in exploded.items():
        L.append(f"| `{flag}` | {n:,} | {'yes' if flag in HARD_FLAGS else 'no'} |")
    L.append("")

    if benchmarks is not None:
        L.append("## 4. Cross-check against the official DBT statistics\n")
        L.append("The Department for Business and Trade publishes medians across valid reports per calendar year "
                 f"([statistics page]({STATS_PAGE}), reference tables downloaded {benchmarks['retrieved_at'].iloc[0]}). "
                 "Their data was extracted on 2026-06-01 and businesses can file backdated reports, so small differences in counts are expected. "
                 "`ours` uses `is_valid_dbt_method` (our replication of their published cleaning rules) and their reporting-year rule.\n")
        head = benchmarks[benchmarks["breakdown_type"] == "headline"]
        piv = head.pivot_table(index="reporting_year", columns="metric", values="value", aggfunc="first")
        v = pq[pq["is_valid_dbt_method"].fillna(False).astype(bool)]
        L.append("| Year | Median days to pay (official / ours) | Median % paid late (official / ours) | Valid reports (official / ours) | Diff in count |\n|---|---|---|---|---:|")
        col_days = next(c for c in piv.columns if c.startswith("Time to pay"))
        col_late = next(c for c in piv.columns if "by number" in c)
        col_n = next(c for c in piv.columns if c.startswith("Number of valid"))
        match_days = match_late = 0
        for year, row in piv.iterrows():
            vy = v[v["reporting_year"] == year]
            d, l, n = vy["avg_days_to_pay"].median(), vy["pct_paid_late"].median(), len(vy)
            match_days += int(d == row[col_days])
            match_late += int(l == row[col_late])
            L.append(f"| {year} | {row[col_days]:g} / {d:g} | {row[col_late]:g} / {l:g} | {row[col_n]:,.0f} / {n:,} | {n - row[col_n]:+,.0f} |")
        L.append(f"\nMedian days to pay matches the official figure in {match_days} of {len(piv)} years; "
                 f"median % paid late matches in {match_late} of {len(piv)} years.\n")

    L.append("## 5. Failures and fixes\n")
    L.append("- `wc -l` on the raw file reports about 359k lines for 116k records because narrative fields contain line breaks. Fixed by counting with a real CSV parser.")
    L.append("- Period dates contain typos (for example a start year of 1918 and an end year of 3025). pandas nanosecond timestamps would have turned these into nulls; the parser uses second resolution, keeps the values as reported and flags them `period_dates_implausible`.")
    L.append("- Under the pre-2025 rules the export carries a placeholder 0 for the value of late payments and the dispute share. Parsed as null (not collected), not as zero.")
    L.append("- See `docs/sources/uk.md` for the full list of gotchas.")
    text = "\n".join(L) + "\n"
    RECON_MD.parent.mkdir(parents=True, exist_ok=True)
    RECON_MD.write_text(text)
    return text


def main(argv: list[str] | None = None) -> None:
    argv = sys.argv[1:] if argv is None else argv
    refresh = "--refresh" in argv
    manifest = download(refresh=refresh) if (refresh or not RAW_CSV.exists() or not MANIFEST.exists()) else load_manifest()
    if not RAW_ODS.exists():
        manifest = download(refresh=False)
    reports = parse(RAW_CSV, manifest["retrieved_at"], manifest["url"])
    entities = build_entity_latest(reports)
    write_tables(reports, entities)
    benchmarks = None
    try:
        ods_meta = next(f for f in manifest.get("related_files", []) if f["path"].endswith(".ods"))
        benchmarks = build_official_benchmarks(RAW_ODS, ods_meta["retrieved_at"])
        benchmarks.to_csv(PROCESSED / "uk_official_benchmarks.csv", index=False)
    except Exception as exc:  # benchmark file is a nice-to-have; never block the ingest on it
        print(f"WARN: official benchmarks not built: {exc!r}")
    manifest.update(rows_reports=len(reports), distinct_entities=int(reports["company_number"].nunique()),
                    rows_entity_latest=len(entities), processed_at=now_iso())
    write_manifest(MANIFEST_NAME, manifest)
    reconcile(RAW_CSV, reports, entities, manifest, benchmarks)
    print(f"reports: {len(reports):,} | entities: {len(entities):,} | usable reports: {int(reports['is_usable'].sum()):,}")
    print(f"wrote {PROCESSED / 'uk_payment_practices.parquet'} and uk_entity_latest.parquet; reconciliation -> {RECON_MD}")


if __name__ == "__main__":
    main()
