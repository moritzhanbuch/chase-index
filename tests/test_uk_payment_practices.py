"""Tests for the UK payment practices parser. Fixture rows are synthetic (FIXTURE ... companies)
but use the exact header of the official export."""
from __future__ import annotations

import datetime as dt
from pathlib import Path

import pandas as pd
import pytest

from chase.sources import uk_payment_practices as uk
from chase.sources.uk_fair_payment_code import normalise_company_number, parse_page

FIXTURE = Path(__file__).parent / "fixtures" / "uk_payment_practices_sample.csv"
RETRIEVED = "2026-11-16T10:03:07Z"
PROVENANCE = ["source_url", "source_type", "retrieved_at", "period_start", "period_end", "extraction_method", "confidence"]


@pytest.fixture(scope="module")
def reports() -> pd.DataFrame:
    return uk.parse(FIXTURE, RETRIEVED)


@pytest.fixture(scope="module")
def entities(reports) -> pd.DataFrame:
    return uk.build_entity_latest(reports)


def _r(df, report_id):
    return df[df["report_id"] == report_id].iloc[0]


def _e(df, number):
    return df[df["company_number"] == number].iloc[0]


def test_row_count_matches_csv_records(reports):
    # the fixture has multi-line fields, so physical lines != records
    assert uk.count_csv_records(FIXTURE) == 12
    assert len(reports) == 12
    assert reports["report_id"].is_unique


def test_dtypes(reports):
    assert reports["report_id"].dtype == "int64"
    for c in ("period_start", "period_end", "filing_date"):
        assert all(isinstance(v, dt.date) for v in reports[c])
    for c in uk.CORE_METRICS + ["value_paid_total_gbp", "max_contractual_payment_period_days"]:
        assert reports[c].dtype == "float64", c
    for c in ("had_qualifying_contracts", "offers_einvoicing", "offers_supply_chain_finance",
              "participates_in_payment_codes", "is_usable"):
        assert reports[c].dtype == "boolean", c
    assert reports["confidence"].dtype == "float64"


def test_company_number_zero_padded_string(reports):
    assert _r(reports, 101)["company_number"] == "01234567"
    assert _r(reports, 104)["company_number"] == "SC123456"
    assert (reports["company_number"].str.len() == 8).all()


def test_provenance_complete(reports, entities):
    for df in (reports, entities):
        for c in PROVENANCE:
            assert df[c].notna().all(), c
        assert (df["source_type"] == "uk_ppr_statutory_report").all()
        assert (df["extraction_method"] == "official_csv_export").all()
        assert (df["confidence"] == 1.0).all()
        assert (df["retrieved_at"] == RETRIEVED).all()
        assert df["source_url"].str.match(r"https://check-payment-practices\.service\.gov\.uk/report/\d+$").all()
    assert _r(reports, 103)["source_url"].endswith("/report/103")


def test_metrics_parsed(reports):
    r = _r(reports, 103)
    assert r["avg_days_to_pay"] == 47
    assert (r["pct_paid_within_30"], r["pct_paid_31_60"], r["pct_paid_over_60"]) == (40, 35, 25)
    assert r["pct_paid_late"] == 36
    assert r["value_paid_total_gbp"] == 1_000_000
    assert r["pct_value_paid_late"] == 25.0
    assert r["offers_supply_chain_finance"] is True or bool(r["offers_supply_chain_finance"])
    assert r["quality_flag"] == "ok" and bool(r["is_usable"])


def test_regime1_placeholder_zero_becomes_null(reports):
    r = _r(reports, 101)
    assert pd.isna(r["value_paid_late_gbp"])
    assert pd.isna(r["pct_not_paid_due_to_dispute"])
    assert _r(reports, 103)["pct_not_paid_due_to_dispute"] == 2


def test_no_qualifying_contracts_keeps_nulls(reports):
    r = _r(reports, 104)
    assert "no_qualifying_contracts" in r["quality_flag"]
    assert all(pd.isna(r[c]) for c in uk.CORE_METRICS)
    assert not bool(r["is_usable"])
    assert pd.isna(r["offers_einvoicing"])


def test_duplicate_period_keeps_latest_filing(reports):
    older, newer = _r(reports, 105), _r(reports, 106)
    assert older["superseded_by_report_id"] == 106
    assert "superseded_by_later_report" in older["quality_flag"] and not bool(older["is_usable"])
    assert pd.isna(newer["superseded_by_report_id"]) and bool(newer["is_usable"])


def test_invalid_values_flagged_not_dropped(reports):
    d = _r(reports, 107)
    assert d["avg_days_to_pay"] == 4000  # value kept as reported
    assert "avg_days_gt_365" in d["quality_flag"] and "payment_terms_gt_365" in d["quality_flag"]
    assert not bool(d["is_usable"])
    e = _r(reports, 108)
    assert e["period_end"] == dt.date(3025, 6, 30)  # typo survives as a date
    assert "period_dates_implausible" in e["quality_flag"] and not bool(e["is_usable"])
    assert "value_late_exceeds_total" in _r(reports, 110)["quality_flag"]
    h = _r(reports, 111)
    assert h["quality_flag"] == "period_length_out_of_range"  # 3-month period; buckets summing to 99 is tolerated


def test_soft_flag_does_not_block_use(reports):
    f = _r(reports, 109)
    assert f["quality_flag"] == "pct_late_inconsistent_with_buckets"
    assert bool(f["is_usable"])


def test_payment_code_flags(reports):
    assert bool(_r(reports, 101)["participates_in_payment_codes"]) and bool(_r(reports, 101)["mentions_prompt_payment_code"])
    assert bool(_r(reports, 103)["mentions_fair_payment_code"])
    assert not bool(_r(reports, 105)["participates_in_payment_codes"])


def test_reporting_year_majority_rule(reports):
    assert _r(reports, 101)["reporting_year"] == 2024
    assert _r(reports, 112)["reporting_year"] == 2026  # 1 Dec 2025 to 30 May 2026
    s = pd.Series(pd.to_datetime(["2025-10-01"])).astype("datetime64[s]")
    e = pd.Series(pd.to_datetime(["2026-04-02"])).astype("datetime64[s]")
    assert uk.reporting_year(s, e).iloc[0] == 2025  # tie goes to the starting year


def test_entity_table_one_row_per_company(reports, entities):
    assert len(entities) == reports["company_number"].nunique() == 8
    assert entities["company_number"].is_unique


def test_entity_latest_prev_and_yoy(entities):
    a = _e(entities, "01234567")
    assert a["latest_report_id"] == 103 and a["prev_report_id"] == 102 and a["yoy_report_id"] == 101
    assert a["company_name"] == "FIXTURE ALPHA (UK) LIMITED"
    assert a["company_names_all"] == "FIXTURE ALPHA LIMITED | FIXTURE ALPHA (UK) LIMITED"
    assert a["avg_days_to_pay"] == 47
    assert a["trend_days_yoy"] == 7 and a["trend_pct_late_yoy"] == 6
    assert a["trend_days_vs_prev"] == 3
    assert a["avg_days_to_pay_mean_last2"] == 45.5
    assert a["n_reports"] == 3 and a["n_reports_usable"] == 3
    assert a["period_end"] == dt.date(2025, 6, 30)


def test_entity_uses_surviving_duplicate(entities):
    c = _e(entities, "OC300001")
    assert c["latest_report_id"] == 106 and c["avg_days_to_pay"] == 28
    assert c["n_reports"] == 2 and c["n_reports_usable"] == 1
    assert pd.isna(c["trend_days_yoy"]) and pd.isna(c["yoy_report_id"])


def test_entity_without_usable_report_has_null_metrics(entities):
    for number in ("SC123456", "00000042", "00000043"):
        row = _e(entities, number)
        assert not bool(row["has_usable_report"])
        assert pd.isna(row["avg_days_to_pay"]) and pd.isna(row["latest_report_id"])
        assert pd.notna(row["source_url"]) and pd.notna(row["period_end"])


def test_no_negative_or_out_of_range_percentages_in_usable(reports):
    u = reports[reports["is_usable"].fillna(False).astype(bool)]
    for c in ("pct_paid_within_30", "pct_paid_31_60", "pct_paid_over_60", "pct_paid_late"):
        assert u[c].between(0, 100).all()
    assert u["avg_days_to_pay"].between(0, 365).all()


def test_schema_change_is_loud(tmp_path):
    bad = tmp_path / "bad.csv"
    bad.write_text("Report Id,Company\n1,X\n")
    with pytest.raises(ValueError, match="schema changed"):
        uk.parse(bad, RETRIEVED)


def test_fair_payment_code_helpers():
    assert normalise_company_number("7796021") == "07796021"
    assert normalise_company_number("sc12345") == "SC012345"
    assert normalise_company_number("Ballyhoo Ltd") is None
    page = ('<article class="accordion_item Gold"><span class="h3 mb-0">FIXTURE &amp; CO LTD</span>'
            '<p><strong class="h4">Industry Sector:</strong> Retail</p>'
            '<p><strong class="h4">Company House No:</strong> 123456</p>'
            '<p><strong class="h4">Area:</strong> London</p>'
            '<p><strong class="h4">Award Level:</strong><span><img alt="Gold"><span class="date-level">Gold</span> Until 2028</span></p>'
            '<p><strong class="h4">Registration Date:</strong> 1 May 2026</p></article>')
    rows = parse_page(page)
    assert rows == [{"awardee_name": "FIXTURE & CO LTD", "company_number_raw": "123456", "company_number": "00123456",
                     "industry_sector": "Retail", "area": "London", "award_level": "Gold", "award_until_year": "2028",
                     "registration_date_text": "1 May 2026"}]


@pytest.mark.skipif(not (uk.PROCESSED / "uk_payment_practices.parquet").exists(), reason="processed data not built")
def test_processed_tables_contract():
    """Contract check on the real output: provenance complete, keys unique, counts consistent."""
    r = pd.read_parquet(uk.PROCESSED / "uk_payment_practices.parquet")
    e = pd.read_parquet(uk.PROCESSED / "uk_entity_latest.parquet")
    assert r["report_id"].is_unique and e["company_number"].is_unique
    assert len(e) == r["company_number"].nunique()
    for df in (r, e):
        for c in PROVENANCE:
            assert df[c].notna().all(), c
    assert r["company_number"].str.fullmatch(r"[A-Z0-9]{8}").all()
    usable = r[r["is_usable"]]
    assert usable["avg_days_to_pay"].between(0, 365).all()
    assert e.loc[~e["has_usable_report"], "avg_days_to_pay"].isna().all()
