"""Tests for chase.enrich.uk_fields: rubric classifier, direction rules, output contracts."""
from pathlib import Path

import pandas as pd
import pytest

from chase.enrich import uk_fields as u

ROOT = Path(__file__).resolve().parents[1]
PROCESSED = ROOT / "data" / "processed"
PROV = ["source_url", "source_type", "retrieved_at", "period_start", "period_end", "extraction_method", "confidence"]


# ---------------------------------------------------------------- rubric classifier

@pytest.mark.parametrize("text,expected", [
    (None, "none"),
    ("", "none"),
    ("N/A", "none"),
    ("None.", "none"),
    ("There were no disputes in the reporting period.", "none"),
    ("Disputes are resolved in line with our standard terms and conditions.", "boilerplate"),
    ("We aim to resolve all disputes amicably and in a timely manner.", "boilerplate"),
    ("Suppliers should contact the accounts payable team.", "basic"),
    ("Invoices in query are placed on hold until a credit note is received.", "basic"),
    ("Disputes are escalated to senior management.", "basic"),
    ("Suppliers should email ap@example.com. We respond within 5 working days.", "named_route"),
    ("Queries go to the purchase ledger team; if the dispute is not resolved it is escalated to the Finance Director.",
     "named_route"),
    ("Raise a query on the supplier portal. Unresolved disputes are referred to mediation.", "named_route"),
])
def test_classify_dispute_text(text, expected):
    assert u.classify_dispute_text(text) == expected


def test_classifier_only_returns_rubric_labels():
    for t in ["x", "contact us", "see contract", "0", "tbc", "a" * 5000]:
        assert u.classify_dispute_text(t) in u.LABELS


def test_text_hash_is_whitespace_and_case_insensitive():
    assert u.text_hash("Contact  AP\nteam") == u.text_hash("contact ap team")
    assert u.text_hash("a") != u.text_hash("b")


# ---------------------------------------------------------------- direction rules

@pytest.mark.parametrize("text,expected", [
    (None, None),
    ("", None),
    ("Standard payment terms increased from 75 to 90 days", "longer"),
    ("Standard terms have changed from 30 days to 60 days but only for newly created vendors.", "longer"),
    ("We are moving to standard 45 days from 30 days.", "longer"),
    ("Invoices are paid within 60 days of invoice date rather than 30 days of invoice date.", "longer"),
    ("Yes, increase in payment terms", "longer"),
    ("The standard payment terms were reduced from 42 days to 37 days", "shorter"),
    ("These changed from 60 days nett to 30 days nett in line with procurement act 2023", "shorter"),
    ("A handful of suppliers requested we shortened payment days. We agreed in all cases.", "shorter"),
    ("Payment cycles moved from daily to weekly", "other"),
    ("Terms have not changed, but payment runs are now more frequent", "other"),
    ("On a case by case basis a few supplier payment terms were changed after consultation", "other"),
    ("New payment terms have been agreed, within the range of 1 day to 120 days", "other"),
    ("The number of invoices in dispute has significantly reduced.", "unknown"),
    ("CVA was entered into in March 2026", "unknown"),
])
def test_terms_direction_from_text(text, expected):
    assert u.terms_direction_from_text(text) == expected


@pytest.mark.parametrize("deltas,expected", [
    ([None, None, None], None),
    ([0, 0, 0], "unchanged"),
    ([0, 30, None], "longer"),
    ([-15, 0, 0], "shorter"),
    ([-15, 30, 0], "mixed"),
    ([float("nan"), 10.0, float("nan")], "longer"),
])
def test_numbers_direction(deltas, expected):
    assert u.numbers_direction(deltas) == expected


@pytest.mark.parametrize("text,expected", [
    ("No", None), ("", None), (None, None),
    ("Prompt Payment Code", "prompt_payment_code"),
    ("Fair Payment Code (formerly the Prompt Payment Code)", "fair_payment_code"),
    ("Groceries Supply Code of Practice", "other_or_unclear"),
])
def test_payment_code_name(text, expected):
    assert u.payment_code_name(text) == expected


def test_cohen_kappa():
    a = pd.Series(["basic", "basic", "none", "named_route"])
    assert u.cohen_kappa(a, a) == pytest.approx(1.0)
    b = pd.Series(["basic", "none", "none", "named_route"])
    assert 0 < u.cohen_kappa(a, b) < 1


# ---------------------------------------------------------------- synthetic end-to-end

def _mini():
    base = dict(policy_regime="Regime-3", value_paid_total_gbp=100.0, participates_in_payment_codes=False,
                payment_codes_text="No", policy_covers_supplier_list_charges=False, charged_for_supplier_list=False,
                shortest_standard_payment_period_days=30.0, longest_standard_payment_period_days=60.0,
                max_contractual_payment_period_days=60.0, suppliers_notified_of_changes_text=None,
                source_type="uk_ppr_statutory_report", retrieved_at="2026-11-16T10:03:07Z")
    reports = pd.DataFrame([
        dict(base, report_id=1, company_number="00000001", company_name="A LTD", period_start="2025-01-01",
             period_end="2025-06-30", filing_date="2025-07-20", offers_supply_chain_finance=False, offers_einvoicing=True,
             pct_not_paid_due_to_dispute=2.0, payment_terms_changed_text=None, dispute_resolution_process_text="n/a",
             source_url="https://check-payment-practices.service.gov.uk/report/1"),
        dict(base, report_id=2, company_number="00000001", company_name="A LTD", period_start="2026-01-01",
             period_end="2026-06-30", filing_date="2026-07-20", offers_supply_chain_finance=True, offers_einvoicing=True,
             pct_not_paid_due_to_dispute=20.0, payment_terms_changed_text="Terms increased from 30 days to 60 days",
             dispute_resolution_process_text="Disputes are resolved in line with contract terms.",
             longest_standard_payment_period_days=90.0, policy_covers_supplier_list_charges=True,
             source_url="https://check-payment-practices.service.gov.uk/report/2"),
        dict(base, report_id=3, company_number="00000002", company_name="B LTD", period_start="2026-01-01",
             period_end="2026-06-30", filing_date="2026-07-25", offers_supply_chain_finance=True, offers_einvoicing=False,
             pct_not_paid_due_to_dispute=0.0, value_paid_total_gbp=300.0, payment_terms_changed_text=None,
             dispute_resolution_process_text="Email ap@example.com; we reply within 2 working days.",
             source_url="https://check-payment-practices.service.gov.uk/report/3"),
    ])
    for c in ("offers_supply_chain_finance", "offers_einvoicing", "participates_in_payment_codes",
              "policy_covers_supplier_list_charges", "charged_for_supplier_list"):
        reports[c] = reports[c].astype("boolean")
    entities = pd.DataFrame([
        dict(company_number="00000001", has_usable_report=True, latest_is_stale=False, latest_report_id=2, yoy_report_id=1),
        dict(company_number="00000002", has_usable_report=True, latest_is_stale=False, latest_report_id=3, yoy_report_id=pd.NA),
        dict(company_number="00000003", has_usable_report=True, latest_is_stale=True, latest_report_id=1, yoy_report_id=pd.NA),
    ])
    entities["latest_report_id"] = entities["latest_report_id"].astype("Int64")
    entities["yoy_report_id"] = entities["yoy_report_id"].astype("Int64")
    gmap = pd.DataFrame([dict(company_number="00000001", company_id="g1", group_name="Group One"),
                         dict(company_number="00000002", company_id="g1", group_name="Group One")])
    return reports, entities, gmap


def test_synthetic_pipeline():
    reports, entities, gmap = _mini()
    llm = pd.DataFrame(columns=["text_hash", "label", "reason"])
    ent = u.build_entity_features(reports, entities, llm=llm)
    assert list(ent["company_number"]) == ["00000001", "00000002"]          # stale entity excluded
    a, b = ent.iloc[0], ent.iloc[1]
    assert a["scf_started"] is True or a["scf_started"] == True  # noqa: E712
    assert a["einvoicing_started"] == False  # noqa: E712  offered a year earlier too
    assert pd.isna(b["scf_started"])                                         # offered now, nothing to compare
    assert b["einvoicing_started"] == False  # noqa: E712
    assert a["terms_changed_direction"] == "longer" and a["terms_numbers_direction"] == "longer"
    assert pd.isna(b["terms_changed_direction"]) and pd.isna(b["terms_numbers_direction"])
    assert a["dispute_process_quality"] == "boilerplate" and b["dispute_process_quality"] == "named_route"
    assert set(ent["dispute_process_quality_method"]) == {"regex_rules"}

    grp = u.build_group_features(ent, gmap)
    g = grp.iloc[0]
    assert g["uk_entities_n"] == 2 and g["scf_offered_n"] == 2 and g["scf_started_n"] == 1
    assert g["dispute_share_pct"] == pytest.approx((20 * 100 + 0 * 300) / 400)
    assert g["dispute_share_method"] == "weighted_by_invoice_value_paid"
    assert g["pay_to_stay_any"] and g["terms_changed_longer_n"] == 1
    assert g["dispute_quality_weak_share"] == 0.5

    sig = u.build_signals(grp, ent, gmap)
    assert set(sig["signal_type"]) == {"scf_offered", "scf_started", "einvoicing_offered", "terms_changed_longer",
                                       "pay_to_stay"}   # 5% < threshold: no dispute_share_high; regex-only labels: no dispute_process_weak (QA rule)
    assert sig["evidence_url"].str.startswith("https://").all()


def test_llm_label_wins_over_regex():
    reports, entities, gmap = _mini()
    h = u.text_hash("Disputes are resolved in line with contract terms.")
    llm = pd.DataFrame([dict(text_hash=h, label="none", reason="test")])
    ent = u.build_entity_features(reports, entities, llm=llm)
    a = ent.iloc[0]
    assert a["dispute_process_quality"] == "none" and a["dispute_process_quality_method"] == "llm_read"
    assert a["dispute_process_quality_regex"] == "boilerplate"


def test_simple_mean_when_weight_missing():
    reports, entities, gmap = _mini()
    reports.loc[reports["report_id"] == 3, "value_paid_total_gbp"] = None
    ent = u.build_entity_features(reports, entities, llm=pd.DataFrame(columns=["text_hash", "label", "reason"]))
    g = u.build_group_features(ent, gmap).iloc[0]
    assert g["dispute_share_method"] == "simple_mean" and g["dispute_share_pct"] == pytest.approx(10.0)


# ---------------------------------------------------------------- contracts on the real outputs

needs_outputs = pytest.mark.skipif(not (PROCESSED / "uk_entity_features.parquet").exists(),
                                   reason="run python -m chase.enrich.uk_fields first")

BOOL_COLS = ["offers_scf", "offers_einvoicing", "in_payment_code", "pay_to_stay_policy", "pay_to_stay_charged",
             "terms_changed_latest", "scf_started", "einvoicing_started"]


@needs_outputs
def test_entity_features_contract():
    e = pd.read_parquet(PROCESSED / "uk_entity_features.parquet")
    assert e["company_number"].is_unique and len(e) > 5000
    for c in BOOL_COLS:
        assert str(e[c].dtype) in ("bool", "boolean"), (c, e[c].dtype)
    for c in ("offers_scf", "offers_einvoicing", "in_payment_code", "terms_changed_latest"):
        assert e[c].notna().all()
    for c in PROV:
        assert e[c].notna().all(), c
    assert (e["source_type"] == "uk_ppr_statutory_report").all()
    assert e["source_url"].str.startswith("https://check-payment-practices.service.gov.uk/").all()
    assert set(e["dispute_process_quality"]) <= set(u.LABELS)
    assert set(e["dispute_process_quality_method"]) <= {"llm_read", "regex_rules"}
    assert set(e["terms_changed_direction"].dropna()) <= {"longer", "shorter", "other", "unknown"}
    # direction exists exactly where a change is declared
    assert (e["terms_changed_direction"].notna() == e["terms_changed_latest"].astype(bool)).all()
    assert e["terms_changed_text"].dropna().str.len().max() <= 300
    assert e["dispute_process_text"].dropna().str.len().max() <= 600
    assert e["pct_not_paid_due_to_dispute"].dropna().between(0, 100).all()
    # started implies offered
    assert e.loc[e["scf_started"].fillna(False).astype(bool), "offers_scf"].all()
    assert e.loc[e["einvoicing_started"].fillna(False).astype(bool), "offers_einvoicing"].all()
    # no column that extracts people
    assert not [c for c in e.columns if any(k in c for k in ("person", "contact_name", "officer", "email", "phone"))]


@needs_outputs
def test_group_features_contract():
    g = pd.read_parquet(PROCESSED / "uk_group_features.parquet")
    e = pd.read_parquet(PROCESSED / "uk_entity_features.parquet")
    assert g["company_id"].is_unique
    for c in PROV:
        assert g[c].notna().all(), c
    for c in [c for c in g.columns if c.endswith("_any")]:
        assert str(g[c].dtype) == "bool"
    # every counted feature has an evidence URL
    for p in ("scf_offered", "einvoicing_offered", "scf_started", "einvoicing_started", "payment_code", "pay_to_stay",
              "terms_changed_longer", "terms_changed_shorter", "terms_changed_other"):
        has = g[f"{p}_n"] > 0
        assert g.loc[has, f"{p}_evidence_url"].notna().all(), p
        assert g.loc[~has, f"{p}_evidence_url"].isna().all(), p
    assert g.loc[g["dispute_share_pct"].notna(), "dispute_share_evidence_url"].notna().all()
    q = [f"dispute_quality_{lab}_n" for lab in u.LABELS]
    assert (g[q].sum(axis=1) == g["uk_entities_n"]).all()
    assert g["uk_entities_n"].sum() <= len(e)
    assert g["dispute_share_pct"].dropna().between(0, 100).all()


@needs_outputs
def test_signals_contract():
    s = pd.read_csv(PROCESSED / "uk_field_signals.csv")
    allowed = {"scf_offered", "scf_started", "einvoicing_offered", "einvoicing_started", "terms_changed_longer",
               "terms_changed_shorter", "terms_changed_other", "pay_to_stay", "dispute_share_high", "dispute_process_weak"}
    assert set(s["signal_type"]) <= allowed
    assert s.notna().all().all()
    assert s["evidence_url"].str.startswith("https://check-payment-practices.service.gov.uk/report/").all()
    assert not s.duplicated(["company_id", "signal_type"]).any()
    assert pd.to_datetime(s["observed_at"], errors="coerce").notna().all()
    banned = ["worst", "offender", "abuse", "scam", "poor", "bad ", "fails", "refuses", "—"]
    for w in banned:
        assert not s["text"].str.lower().str.contains(w, regex=False).any(), w
    g = pd.read_parquet(PROCESSED / "uk_group_features.parquet")
    assert set(s["company_id"]) <= set(g["company_id"])
    hi = set(s.loc[s["signal_type"] == "dispute_share_high", "company_id"])
    assert hi == set(g.loc[g["dispute_share_pct"] >= u.DISPUTE_SHARE_HIGH, "company_id"])


@needs_outputs
def test_qa_sample_is_blind():
    p = ROOT / "evals" / "gold" / "uk_dispute_sample.csv"
    if not p.exists():
        pytest.skip("no sample yet")
    s = pd.read_csv(p, dtype=str, keep_default_na=False)
    assert list(s.columns) == ["text_hash", "company_number", "company_name", "source_url", "dispute_process_text",
                               "qa_label", "qa_note"]
    assert len(s) == 60 and s["text_hash"].is_unique
    key = pd.read_csv(ROOT / "data" / "interim" / "uk_dispute_sample_key.csv", dtype=str)
    assert set(key["text_hash"]) == set(s["text_hash"])
    assert not any(c for c in s.columns if "llm" in c or "regex" in c)
