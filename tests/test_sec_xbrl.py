"""Unit tests for SEC XBRL fact selection, dedupe and DPO. No network."""
from chase.sources import sec_xbrl as sx


def fact(val, end, start=None, form="10-K", filed="2026-02-20", accn="0000000001-26-000001", fy=2025, fp="FY"):
    f = {"val": val, "end": end, "form": form, "filed": filed, "accn": accn, "fy": fy, "fp": fp}
    if start:
        f["start"] = start
    return f


def cf(usgaap=None, ifrs=None, name="TEST CO"):
    def wrap(d):
        return {c: {"units": units} for c, units in (d or {}).items()}
    return {"entityName": name, "facts": {"us-gaap": wrap(usgaap), "ifrs-full": wrap(ifrs)}}


BASE = cf(usgaap={
    "Revenues": {"USD": [
        fact(900, "2024-12-31", "2024-01-01", filed="2025-02-20", accn="A-25"),
        fact(1000, "2025-12-31", "2025-01-01", accn="A-26"),
        fact(250, "2025-03-31", "2025-01-01", form="10-Q", filed="2025-05-01", accn="Q1"),  # quarter
        fact(800, "2023-12-31", "2023-01-01", filed="2024-02-20", accn="A-24"),
    ]},
    "CostOfRevenue": {"USD": [
        fact(540, "2024-12-31", "2024-01-01", filed="2025-02-20", accn="A-25"),
        fact(600, "2025-12-31", "2025-01-01", accn="A-26"),
    ]},
    "AccountsPayableCurrent": {"USD": [
        fact(90, "2024-12-31", filed="2025-02-20", accn="A-25"),
        fact(100, "2025-12-31", accn="A-26"),
        fact(999, "2025-12-31", form="10-Q", filed="2026-05-01", accn="Q-later"),  # non-annual form ignored
    ]},
})


def test_days_between_inclusive():
    assert sx.days_between("2025-01-01", "2025-12-31") == 365
    assert sx.days_between("2024-01-01", "2024-12-31") == 366


def test_cik_and_filing_url():
    assert sx.cik10(104169) == "0000104169"
    assert sx.filing_url("0000104169", "0000104169-26-000154") == \
        "https://www.sec.gov/Archives/edgar/data/104169/000010416926000154/"
    assert sx.filing_url(1, None) is None


def test_dedupe_takes_most_recently_filed():
    facts = [fact(1, "2024-12-31", "2024-01-01", filed="2025-02-01", accn="a"),
             fact(2, "2024-12-31", "2024-01-01", filed="2026-02-01", accn="b"),
             fact(3, "2025-12-31", "2025-01-01", filed="2026-02-01", accn="b")]
    out = {f["end"]: f["val"] for f in sx.dedupe_latest_filed(facts)}
    assert out == {"2024-12-31": 2, "2025-12-31": 3}


def test_annual_duration_excludes_quarters_and_non_annual_forms():
    facts = sx.annual_duration_facts(BASE, "Revenues")
    assert sorted(f["val"] for f in facts) == [800, 900, 1000]


def test_select_latest_two_fiscal_years_newest_first():
    years = sx.select_fiscal_years(BASE)
    assert [(y["end"], y["val"]) for y in years] == [("2025-12-31", 1000), ("2024-12-31", 900)]


def test_restated_prior_year_uses_latest_filing():
    c = cf(usgaap={"Revenues": {"USD": [
        fact(900, "2024-12-31", "2024-01-01", filed="2025-02-20", accn="A-25"),
        fact(880, "2024-12-31", "2024-01-01", filed="2026-02-20", accn="A-26"),  # recast comparative
        fact(1000, "2025-12-31", "2025-01-01", filed="2026-02-20", accn="A-26"),
    ]}})
    years = sx.select_fiscal_years(c)
    assert years[1]["val"] == 880 and years[1]["accn"] == "A-26"


def test_revenue_takes_broadest_concept():
    c = cf(usgaap={
        "RevenueFromContractWithCustomerExcludingAssessedTax": {"USD": [fact(700, "2025-12-31", "2025-01-01")]},
        "Revenues": {"USD": [fact(1000, "2025-12-31", "2025-01-01")]},
    })
    y = sx.select_fiscal_years(c)[0]
    assert y["val"] == 1000 and y["concept"] == "Revenues"


def test_dpo_formula_and_rows():
    rows = sx.build_dpo_rows(BASE, 123, sic="3711", retrieved_at="2026-11-16T00:00:00Z")
    assert len(rows) == 2
    r = rows[0]
    assert r["cik"] == "0000000123" and r["fiscal_year"] == 2025
    assert r["payables"] == 100 and r["cost_of_sales"] == 600
    assert r["dpo"] == round(100 / 600 * 365, 2)
    assert r["dpo_flag"] == "ok" and r["cost_basis"] == "cost_of_sales" and r["payables_basis"] == "trade"
    assert r["confidence"] == 1.0
    assert rows[1]["dpo"] == round(90 / 540 * 365, 2)


def test_provenance_complete_on_every_row():
    for r in sx.build_dpo_rows(BASE, 123, sic="3711", retrieved_at="2026-11-16T00:00:00Z"):
        for col in ("source_url", "source_type", "retrieved_at", "period_start", "period_end",
                    "extraction_method", "confidence", "filing_url", "accession_number"):
            assert r[col] not in (None, ""), col
        assert r["source_url"].endswith("CIK0000000123.json")
        assert r["source_type"] == "sec_xbrl_companyfacts" and r["extraction_method"] == "xbrl_api"


def test_payables_takes_larger_of_the_two_trade_concepts():
    # when both are tagged, one is a sub-detail of the balance sheet line (seen at 3M FY2024)
    c = cf(usgaap={
        "Revenues": {"USD": [fact(1000, "2025-12-31", "2025-01-01")]},
        "CostOfRevenue": {"USD": [fact(600, "2025-12-31", "2025-01-01")]},
        "AccountsPayableCurrent": {"USD": [fact(120, "2025-12-31")]},
        "AccountsPayableTradeCurrent": {"USD": [fact(30, "2025-12-31")]},
        "AccountsPayableAndAccruedLiabilitiesCurrent": {"USD": [fact(500, "2025-12-31")]},  # broad never beats trade
    })
    r = sx.build_dpo_rows(c, 1, sic="2000")[0]
    assert r["payables_concept"] == "us-gaap:AccountsPayableCurrent" and r["payables"] == 120
    assert r["payables_basis"] == "trade" and r["confidence"] == 1.0


def test_unclassified_balance_sheet_payables_noted():
    c = cf(usgaap={
        "Revenues": {"USD": [fact(1000, "2025-12-31", "2025-01-01")]},
        "CostOfRevenue": {"USD": [fact(600, "2025-12-31", "2025-01-01")]},
        "AccountsPayableCurrentAndNoncurrent": {"USD": [fact(60, "2025-12-31")]},
    })
    r = sx.build_dpo_rows(c, 1, sic="1531")[0]
    assert r["payables_basis"] == "trade" and "unclassified" in r["notes"] and r["dpo"] == 36.5


def test_partial_cost_concept_lowers_confidence():
    c = cf(usgaap={
        "Revenues": {"USD": [fact(1000, "2025-12-31", "2025-01-01")]},
        "CostOfGoodsAndServicesSold": {"USD": [fact(10, "2025-12-31", "2025-01-01")]},
        "AccountsPayableCurrent": {"USD": [fact(100, "2025-12-31")]},
    })
    r = sx.build_dpo_rows(c, 1, sic="4911")[0]
    assert r["dpo_flag"] == "suspicious_high" and r["confidence"] == 0.5 and "sub-line" in r["notes"]


def test_fallbacks_are_flagged_with_lower_confidence():
    c = cf(usgaap={
        "Revenues": {"USD": [fact(1000, "2025-12-31", "2025-01-01")]},
        "CostsAndExpenses": {"USD": [fact(900, "2025-12-31", "2025-01-01")]},
        "AccountsPayableAndAccruedLiabilitiesCurrent": {"USD": [fact(200, "2025-12-31")]},
    })
    r = sx.build_dpo_rows(c, 1, sic="4500")[0]
    assert r["cost_basis"] == "operating_expenses_fallback"
    assert r["payables_basis"] == "trade_and_other_broad"
    assert r["confidence"] == 0.7
    assert "fallback" in r["notes"] and "broad" in r["notes"]
    assert r["dpo"] == round(200 / 900 * 365, 2)


def test_missing_inputs_stay_null():
    c = cf(usgaap={"Revenues": {"USD": [fact(1000, "2025-12-31", "2025-01-01")]}})
    r = sx.build_dpo_rows(c, 1, sic="7370")[0]
    assert r["dpo"] is None and r["dpo_flag"] == "missing_inputs"
    assert r["cost_of_sales"] is None and r["payables"] is None and r["notes"]


def test_financials_not_applicable():
    r = sx.build_dpo_rows(BASE, 1, sic="6021")[0]
    assert r["dpo"] is None and r["dpo_flag"] == "not_applicable"
    assert r["payables"] == 100  # inputs kept, ratio not computed


def test_flag_thresholds():
    assert sx.dpo_flag(4.9) == "suspicious_low"
    assert sx.dpo_flag(5) == "ok"
    assert sx.dpo_flag(365) == "ok"
    assert sx.dpo_flag(365.1) == "suspicious_high"
    assert sx.dpo_flag(None) == "missing_inputs"
    assert sx.dpo_flag(40, sic=6311) == "not_applicable"
    assert sx.compute_dpo(100, 0) is None and sx.compute_dpo(None, 5) is None


def test_ifrs_filer_in_foreign_currency_and_fiscal_year_not_calendar():
    c = cf(ifrs={
        "Revenue": {"JPY": [fact(48_000, "2025-03-31", "2024-04-01", form="20-F", filed="2025-06-18"),
                            fact(45_000, "2024-03-31", "2023-04-01", form="20-F", filed="2025-06-18")]},
        "CostOfSales": {"JPY": [fact(38_000, "2025-03-31", "2024-04-01", form="20-F", filed="2025-06-18")]},
        "TradeAndOtherCurrentPayables": {"JPY": [fact(5_000, "2025-03-31", form="20-F", filed="2025-06-18")]},
    })
    rows = sx.build_dpo_rows(c, 1094517, sic="3711")
    assert rows[0]["currency"] == "JPY" and rows[0]["fiscal_year"] == 2025
    assert rows[0]["payables_basis"] == "trade_and_other_broad" and rows[0]["confidence"] == 0.7
    assert rows[0]["dpo"] == round(5000 / 38000 * 365, 2)
    assert rows[1]["dpo_flag"] == "missing_inputs"
    assert sx.to_usd(48_000, "JPY", {"JPY": 160.0}) == 300.0
    assert sx.to_usd(1, "XXX", {"JPY": 160.0}) is None
    assert sx.to_usd(5, "USD", {}) == 5.0


def test_52_53_week_years_accepted():
    c = cf(usgaap={"Revenues": {"USD": [fact(10, "2026-01-31", "2025-01-26"),      # 53 weeks
                                         fact(9, "2025-01-25", "2024-01-28")]}})  # 52 weeks
    assert [y["val"] for y in sx.select_fiscal_years(c)] == [10, 9]


def test_country_from_address():
    assert sx.country_from_address({"stateOrCountry": "AR", "stateOrCountryDescription": "AR"}) == \
        ("US", "United States", "AR")
    assert sx.country_from_address({"stateOrCountry": "M0", "stateOrCountryDescription": "Japan"}) == \
        ("JP", "Japan", None)
    assert sx.country_from_address({"stateOrCountry": "A6", "stateOrCountryDescription": "Ontario, Canada"})[0] == "CA"
    assert sx.country_from_address({"stateOrCountry": "??", "stateOrCountryDescription": "Atlantis"}) == \
        (None, "Atlantis", None)
    assert sx.country_from_address(None) == (None, None, None)
    # newer layout: name in `country`, EDGAR (non-ISO) code in `countryCode`
    assert sx.country_from_address({"stateOrCountry": None, "stateOrCountryDescription": None,
                                    "country": "United Kingdom", "countryCode": "X0"}) == \
        ("GB", "United Kingdom", None)


def test_scale_error_guard():
    c = cf(usgaap={"Revenues": {"USD": [fact(100_000, "2025-12-31", "2025-01-01")]},
                   "Assets": {"USD": [fact(100, "2025-12-31")]}})
    rev = sx.select_fiscal_years(c)[0]
    assert sx.probable_scale_error(c, rev) is True
    c["facts"]["us-gaap"]["Assets"]["units"]["USD"][0]["val"] = 50_000
    assert sx.probable_scale_error(c, rev) is False
    del c["facts"]["us-gaap"]["Assets"]
    assert sx.probable_scale_error(c, rev) is False   # no assets tagged: no judgement
