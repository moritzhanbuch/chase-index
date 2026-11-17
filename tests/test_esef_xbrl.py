"""ESEF xBRL-JSON extraction tests. Inline fixtures only, no network."""
from datetime import date

import pandas as pd

from chase.sources import esef_xbrl as m

E = "scheme:LEI"


def fact(concept, period, value, unit="iso4217:EUR", decimals=-6, **dims):
    return {"value": str(value), "decimals": decimals,
            "dimensions": {"concept": f"ifrs-full:{concept}", "entity": E, "period": period, "unit": unit, **dims}}


CUR = "2025-01-01T00:00:00/2026-01-01T00:00:00"
PRI = "2024-01-01T00:00:00/2025-01-01T00:00:00"
CUR_I, PRI_I = "2026-01-01T00:00:00", "2025-01-01T00:00:00"


def doc(facts):
    return {"documentInfo": {}, "facts": {f"f-{i}": f for i, f in enumerate(facts)}}


def standard_doc():
    return doc([
        fact("Revenue", CUR, 1000e6), fact("Revenue", PRI, 900e6),
        fact("CostOfSales", CUR, 730e6), fact("CostOfSales", PRI, -600e6),  # sign varies by filer
        fact("CurrentTradePayables", CUR_I, 100e6), fact("CurrentTradePayables", PRI_I, 90e6),
        fact("TradeAndOtherCurrentPayables", CUR_I, 180e6), fact("TradeAndOtherCurrentPayables", PRI_I, 170e6),
        # dimensional fact (segment) must be ignored
        fact("Revenue", CUR, 400e6, **{"ifrs-full:SegmentsAxis": "x:Retail"}),
        fact("ProfitLoss", CUR, 50e6), fact("ProfitLoss", PRI, 40e6),
        # half-year noise must not be picked as a fiscal year
        fact("Revenue", "2025-01-01T00:00:00/2025-07-01T00:00:00", 480e6),
    ])


def test_parse_period_end_is_inclusive_previous_day():
    assert m.parse_period("2026-02-01T00:00:00") == (None, date(2026, 1, 31))
    assert m.parse_period(CUR) == (date(2025, 1, 1), date(2025, 12, 31))


def test_consolidated_facts_skip_dimensions_and_prefer_precise_duplicate():
    d = doc([fact("Revenue", CUR, 1000e6, decimals=-6), fact("Revenue", CUR, 1000.4e6, decimals=-3),
             fact("Revenue", CUR, 5, **{"ifrs-full:SegmentsAxis": "x:A"})])
    f = m.consolidated_facts(d)
    assert list(f.values()) == [1000.4e6]


def test_two_fiscal_years_from_one_filing_and_dpo():
    ex = m.extract_filing(standard_doc())
    assert ex["is_financial"] is False
    cur, pri = ex["years"]
    assert (cur["period_start"], cur["period_end"], cur["fiscal_year"]) == ("2025-01-01", "2025-12-31", 2025)
    assert pri["period_end"] == "2024-12-31"
    assert cur["revenue"] == 1000e6 and cur["currency"] == "EUR"
    assert cur["payables_concept"] == "CurrentTradePayables" and cur["payables_basis"] == "trade"
    assert cur["cost_basis"] == "cost_of_sales"
    assert cur["dpo"] == 50.0 and cur["dpo_flag"] == "ok" and cur["confidence"] == 1.0
    assert pri["cost"] == 600e6  # absolute value
    assert pri["dpo"] == round(90 / 600 * 365, 1)


def test_broad_payables_fallback_lowers_confidence():
    d = doc([fact("Revenue", CUR, 1000e6), fact("CostOfSales", CUR, 500e6),
             fact("TradeAndOtherCurrentPayables", CUR_I, 200e6)])
    y = m.extract_filing(d)["years"][0]
    assert y["payables_basis"] == "trade_and_other_broad" and y["confidence"] == 0.7
    assert y["dpo"] == 146.0


def test_by_nature_fallback_and_missing_cost():
    d = doc([fact("Revenue", CUR, 1000e6), fact("RawMaterialsAndConsumablesUsed", CUR, 300e6),
             fact("OtherExpenseByNature", CUR, 100e6), fact("CurrentTradePayables", CUR_I, 80e6)])
    y = m.extract_filing(d)["years"][0]
    assert y["cost_basis"] == "by_nature_fallback"
    assert y["cost_concept"] == "RawMaterialsAndConsumablesUsed+OtherExpenseByNature"
    assert y["cost"] == 400e6 and y["dpo"] == 73.0 and y["confidence"] == 0.7
    assert y["raw_materials_and_consumables"] == 300e6

    d2 = doc([fact("Revenue", CUR, 1000e6), fact("CurrentTradePayables", CUR_I, 80e6)])
    y2 = m.extract_filing(d2)["years"][0]
    assert y2["cost_basis"] == "missing" and y2["dpo"] is None and y2["dpo_flag"] == "missing_inputs"


def test_bank_is_not_applicable_but_captive_bank_is_not():
    bank = doc([fact("InterestRevenueCalculatedUsingEffectiveInterestMethod", CUR, 900e6),
                fact("DepositsFromCustomers", CUR_I, 5e9), fact("TradeAndOtherPayables", CUR_I, 1e8),
                fact("ProfitLoss", CUR, 1e8)])
    ex = m.extract_filing(bank)
    assert ex["is_financial"] is True
    assert ex["years"][0]["dpo"] is None and ex["years"][0]["dpo_flag"] == "not_applicable"
    retailer = doc([fact("Revenue", CUR, 1000e6), fact("CostOfSales", CUR, 700e6),
                    fact("DepositsFromCustomers", CUR_I, 5e8), fact("CurrentTradePayables", CUR_I, 1e8)])
    assert m.extract_filing(retailer)["is_financial"] is False


def test_dpo_flags():
    assert m.dpo_flag(3.0, False) == "suspicious_low"
    assert m.dpo_flag(400.0, False) == "suspicious_high"
    assert m.dpo_flag(None, False) == "missing_inputs"
    assert m.dpo_flag(60.0, True) == "not_applicable"
    assert m.compute_dpo(100, 0) is None


def test_select_latest_filing_per_lei_prefers_clean_same_period():
    idx = pd.DataFrame([
        dict(lei="A", name="a", country="ES", period_end="2024-12-31", json_url="/a24.json", error_count=0, processed="2025-03-01"),
        dict(lei="A", name="a", country="ES", period_end="2025-12-31", json_url="/a25e.json", error_count=3, processed="2026-03-02"),
        dict(lei="A", name="a", country="ES", period_end="2025-12-31", json_url="/a25.json", error_count=0, processed="2026-03-01"),
        dict(lei="B", name="b", country="NL", period_end="2025-12-31", json_url=None, error_count=0, processed="2026-03-01"),
        dict(lei="B", name="b", country="GB", period_end="2024-12-31", json_url="/b24.json", error_count=5, processed="2025-03-01"),
        dict(lei="C", name="c", country="UA", period_end="2025-12-31", json_url="/c.json", error_count=0, processed="2026-03-01"),
        dict(lei="D", name="d", country="PL", period_end="2021-12-31", json_url="/d.json", error_count=0, processed="2022-03-01"),
    ])
    sel = m.select_filings(idx, max_period_end="2026-11-16").set_index("lei")
    assert sel.loc["A", "json_url"] == "/a25.json"
    assert sel.loc["B", "json_url"] == "/b24.json" and sel.loc["B", "countries_filed"] == "GB,NL"
    assert "C" not in sel.index and "D" not in sel.index


def test_to_usd_with_year_fallback():
    fx = {2024: {"EUR": 1.08, "GBP": 1.28}, 2025: {"EUR": 1.13}}
    assert m.to_usd(10.0, "EUR", 2026, fx) == (11.299999999999999, 2025)
    assert m.to_usd(10.0, "GBP", 2024, fx) == (12.8, 2024)
    assert m.to_usd(10.0, "XXX", 2024, fx) == (None, None)
    assert m.to_usd(None, "EUR", 2024, fx) == (None, None)


def test_revenue_fallback_rules_and_bank_without_revenue():
    d = doc([fact("RevenueFromSaleOfGoods", CUR, 700e6), fact("RevenueFromRenderingOfServices", CUR, 50e6),
             fact("RevenueFromInterest", CUR, 5e6), fact("RawMaterialsAndConsumablesUsed", CUR, 400e6)])
    ex = m.extract_filing(d)
    assert ex["is_financial"] is False
    assert ex["years"][0]["revenue"] == 750e6
    assert ex["years"][0]["revenue_concept"] == "RevenueFromSaleOfGoods+RevenueFromRenderingOfServices"
    bank = doc([fact("InterestRevenueExpense", CUR, 40e9), fact("FeeAndCommissionIncome", CUR, 15e9),
                fact("ProfitLoss", CUR, 1e9)])
    assert m.extract_filing(bank)["is_financial"] is True


def test_single_stray_bank_concept_does_not_make_a_brewer_a_bank():
    d = doc([fact("Revenue", CUR, 34e9), fact("RawMaterialsAndConsumablesUsed", CUR, 12e9),
             fact("RevenueFromInterest", CUR, 1e8), fact("LoansAndAdvancesToCustomers", CUR_I, 2e8),
             fact("TradeAndOtherCurrentPayables", CUR_I, 9e9)])
    ex = m.extract_filing(d)
    assert ex["is_financial"] is False and ex["years"][0]["dpo"] is not None
