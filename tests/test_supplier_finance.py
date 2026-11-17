"""Unit tests for the deterministic supplier-finance extractor (no network)."""
from datetime import date

from chase.sources import supplier_finance as S


def test_discover_concepts_by_substring():
    names = ["AccountsPayableCurrent", "SupplierFinanceProgramObligation",
             "SupplierFinanceProgramObligationIncrease", "foo:DescriptionOfAccountingPolicyForSupplyChainFinancing",
             "es:ConfirmingPayables", "x:AdjustmentsForNonRecourseFactoring", "x:ReverseFactoringLiabilities"]
    got = S.discover_concepts(names)
    assert "AccountsPayableCurrent" not in got
    assert "x:AdjustmentsForNonRecourseFactoring" not in got  # plain factoring is not counted
    assert set(got) == {"SupplierFinanceProgramObligation", "SupplierFinanceProgramObligationIncrease",
                        "foo:DescriptionOfAccountingPolicyForSupplyChainFinancing", "es:ConfirmingPayables",
                        "x:ReverseFactoringLiabilities"}
    assert S.related_concepts(names) == ["x:AdjustmentsForNonRecourseFactoring"]


def test_classify_concept_roles():
    c = S.classify_concept
    assert c("us-gaap:SupplierFinanceProgramObligation") == "obligation"
    assert c("SupplierFinanceProgramObligationCurrent") == "obligation_current"
    assert c("SupplierFinanceProgramObligationNoncurrent") == "obligation_noncurrent"
    assert c("SupplierFinanceProgramObligationIncrease") == "increase"
    assert c("SupplierFinanceProgramObligationDecreaseSettlement") == "settlement"
    assert c("SupplierFinanceProgramObligationPeriodIncreaseDecrease") == "net_change"
    assert c("ifrs-full:DisclosureOfInformationRelatingToSupplierFinanceArrangementsExplanatory") == "text"
    assert c("x:LiabilitiesPartOfSupplierFinanceArrangementsForWhichSuppliersHaveAlreadyReceivedPayment") == "already_paid"
    assert c("x:RangeOfPaymentDueDatesSupplierFinanceArrangements") == "terms_with"
    assert c("x:RangeOfPaymentDueDatesComparableTradePayablesNotPartOfSupplierFinanceArrangements") == "terms_without"


def _e(end, val, form, filed, start=None):
    d = {"end": end, "val": val, "form": form, "filed": filed, "accn": "0000000001-26-000001"}
    if start:
        d["start"] = start
    return d


ENTRIES = [
    _e("2023-12-31", 90, "10-K", "2024-02-20"),
    _e("2024-12-31", 100, "10-K", "2025-02-20"),
    _e("2024-12-31", 105, "10-K", "2026-02-20"),   # restated comparative in the next 10-K
    _e("2025-12-31", 120, "10-K", "2026-02-20"),
    _e("2025-12-31", 120, "10-Q", "2026-04-30"),
    _e("2026-03-31", 130, "10-Q", "2026-04-30"),   # later quarter: not the fiscal-year value
]


def test_select_latest_instant_prefers_fiscal_year_end_and_restated_prior():
    s = S.select_latest_instant(ENTRIES)
    assert s["latest"]["end"] == "2025-12-31" and s["latest"]["val"] == 120
    assert s["prior"]["end"] == "2024-12-31" and s["prior"]["val"] == 105
    assert s["latest_interim"]["end"] == "2026-03-31"
    assert s["basis"] == "annual_form"


def test_select_latest_instant_without_annual_form_and_empty():
    s = S.select_latest_instant([_e("2026-03-31", 5, "10-Q", "2026-05-01")])
    assert s["latest"]["val"] == 5 and s["prior"] is None and s["basis"] == "any_form"
    assert S.select_latest_instant([]) == {}


def test_select_duration_full_year_only():
    es = [_e("2025-12-31", 30, "10-K", "2026-02-20", start="2025-10-01"),
          _e("2025-12-31", 400, "10-K", "2026-02-20", start="2025-01-01")]
    assert S.select_duration(es, "2025-12-31")["val"] == 400
    assert S.select_duration(es, "2024-12-31") is None


def test_extract_sec_tagged_and_not_tagged():
    doc = {"facts": {"us-gaap": {
        "AccountsPayableCurrent": {"units": {"USD": [_e("2025-12-31", 999, "10-K", "2026-02-20")]}},
        "SupplierFinanceProgramObligationCurrent": {"units": {"USD": ENTRIES}},
        "SupplierFinanceProgramObligationIncrease": {"units": {"USD": [
            _e("2025-12-31", 700, "10-K", "2026-02-20", start="2025-01-01")]}},
    }}}
    r = S.extract_sec(doc, "0000000001")
    assert r["programme_tagged"] and r["obligation_amount"] == 120 and r["obligation_prior_amount"] == 105
    assert r["currency"] == "USD" and r["period_end"] == "2025-12-31" and r["period_start"] == "2025-01-01"
    assert r["invoices_confirmed_in_period"] == 700
    assert r["filing_url"].endswith("/1/000000000126000001/0000000001-26-000001-index.htm")
    assert r["confidence"] == 1.0
    empty = S.extract_sec({"facts": {"us-gaap": {"AccountsPayableCurrent": {"units": {"USD": ENTRIES}}}}}, "1")
    assert empty["programme_tagged"] is False and "obligation_amount" not in empty


def test_find_text_mention_strips_markup_and_ranks_phrases():
    h = '<div>Trade payables. <span class="_ _1"></span>Re<span></span>verse fac<span></span>toring programme of 41m.</div>'
    m = S.find_text_mention(h)
    assert m["phrase"] == "reverse factoring" and "Reverse factoring programme" in m["snippet"]
    assert len(m["snippet"]) <= 200
    assert S.find_text_mention("El Grupo utiliza el confirming como instrumento de pago")["phrase"] == "confirming"
    assert S.find_text_mention("Nothing relevant in this accounting policy text.") is None


def _fact(concept, value, period, unit=None, **dims):
    d = {"concept": concept, "entity": "x", "period": period, **dims}
    if unit:
        d["unit"] = unit
    return {"value": value, "dimensions": d}


def test_extract_esef_text_only_numeric_and_untagged():
    text_only = {"facts": {"f1": _fact("co:DescriptionOfAccountingPolicyForSupplierFinanceArrangements",
                                       "<p>Supplier finance arrangements exist.</p>", "2025-01-01T00:00:00/2026-01-01T00:00:00")}}
    r = S.extract_esef(text_only)
    assert r["programme_tagged"] and not r["numeric_tagged"] and r["confidence"] == 0.8
    assert r["text_mention_found"] and r["text_mention_fact_id"] == "f1"

    numeric = {"facts": {
        "a": _fact("ifrs-full:CarryingAmountOfFinancialLiabilitiesThatArePartOfSupplierFinanceArrangements", "500",
                   "2026-01-01T00:00:00", "iso4217:EUR"),
        "b": _fact("ifrs-full:CarryingAmountOfFinancialLiabilitiesThatArePartOfSupplierFinanceArrangements", "400",
                   "2025-01-01T00:00:00", "iso4217:EUR"),
        "c": _fact("ifrs-full:CarryingAmountOfFinancialLiabilitiesThatArePartOfSupplierFinanceArrangementsForWhichSuppliersHaveAlreadyReceivedPayment",
                   "300", "2026-01-01T00:00:00", "iso4217:EUR"),
    }}
    r = S.extract_esef(numeric)
    assert r["numeric_tagged"] and r["confidence"] == 1.0
    assert r["obligation_amount"] == 500 and r["obligation_prior_amount"] == 400
    assert r["period_end"] == "2025-12-31" and r["currency"] == "EUR"
    assert r["amount_suppliers_already_paid"] == 300

    none = S.extract_esef({"facts": {"z": _fact("ifrs-full:Revenue", "10", "2025-01-01T00:00:00/2026-01-01T00:00:00", "iso4217:EUR"),
                                     "t": _fact("ifrs-full:DisclosureOfTradeAndOtherPayablesExplanatory",
                                                "<p>The Group has a supply chain financing (SCF) programme.</p>",
                                                "2025-01-01T00:00:00/2026-01-01T00:00:00")}})
    assert none["programme_tagged"] is False and none["text_mention_found"] and none["text_mention_phrase"] == "supply chain finance"


def test_build_record_status_vocabulary(monkeypatch):
    import pandas as pd
    sel = pd.DataFrame(columns=["json_url", "period_end", "viewer_url", "report_url"])
    r = S.build_record({"rank": "1", "company_id": "c", "name": "N", "country": "DE", "cik": "", "lei": ""}, sel)
    assert r["status"] == "no_structured_source" and r["source"] == "none" and r["programme_tagged"] is False

    doc = {"facts": {"us-gaap": {"Revenues": {"units": {"USD": ENTRIES}}}}}
    monkeypatch.setattr(S, "_load", lambda url: (doc, "2026-11-16T00:00:00Z", None))
    r = S.build_record({"rank": "2", "company_id": "d", "name": "M", "country": "US", "cik": "0000000002", "lei": ""},
                       sel, today=date(2026, 11, 16))
    assert r["status"] == "not_tagged" and r["confidence"] is None and "NOT evidence" in r["notes"]
    assert r["source_url"].endswith("CIK0000000002.json") and r["retrieved_at"]


def test_reconcile_accession_helper():
    from chase.sources.supplier_finance_reconcile import _accn
    a = "https://www.sec.gov/Archives/edgar/data/55785/000162828026070754/0001628280-26-070754-index.htm"
    b = "https://www.sec.gov/Archives/edgar/data/55785/000162828026007567/kmb-20251231.htm"
    assert _accn(a) == "000162828026070754" and _accn(b) == "000162828026007567"
    assert _accn("https://filings.xbrl.org/x/2025-12-31/ESEF/GB/0/x.json") is None and _accn(None) is None
