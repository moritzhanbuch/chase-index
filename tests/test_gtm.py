"""Weekly workflow: triggers, bring-your-own-data, queue, feedback, exports."""
from datetime import date
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

ROOT = Path(__file__).resolve().parents[1]
pytestmark = pytest.mark.skipif(not (ROOT / "data/processed/companies.parquet").exists(), reason="run `make data score` first")


def test_triggers_are_dated_sourced_and_nameless():
    from chase.gtm import triggers
    t = triggers.build(date(2026, 11, 16))
    assert len(t) > 50 and t.trigger_date.notna().all() and t.text.notna().all()
    filed = t[t.trigger_type.isin(["filing_crossed_60", "filing_worsened", "es_pmp_rose"])]
    assert filed.evidence_url.notna().all()
    assert set(t.trigger_type) <= set(triggers.SPEC)
    # a CFO-change trigger never carries the person's name in the shared table
    assert not t[t.trigger_type == "cfo_change"].text.str.contains(r"[A-Z][a-z]+ [A-Z][a-z]+ (?:was|is|joins|appointed)", regex=True).any()


def test_trigger_liveness_windows():
    from chase.gtm import triggers
    t = triggers.build(date(2026, 11, 16))
    past = t[t.trigger_type == "filing_worsened"]
    assert (past[past.is_live].days_from_today <= 0).all()
    assert (past[past.is_live].days_from_today >= -triggers.SPEC["filing_worsened"][1]).all()


def test_byod_demo_is_labelled_synthetic_and_changes_the_queue():
    from chase.gtm import byod, nba
    for f in (ROOT / "config/byod/demo").glob("*.csv"):
        assert f.read_text().startswith("# SYNTHETIC DEMO DATA")
    assert (ROOT / "config/status/demo_accounts_status.csv").read_text().startswith("# SYNTHETIC DEMO OUTCOMES")
    today = date(2026, 11, 16)
    plain, demo = nba.build_queue(today, demo=False), nba.build_queue(today, demo=True)
    assert len(plain) == len(demo) == 25
    assert "warm_via_supplier" in set(demo.play) and "warm_via_supplier" not in set(plain.play)
    flags, unmatched = byod.apply(True)
    final = {c for c, f in flags.items() if f.get("status", {}).get("status") in byod.FINAL_STATUSES or f.get("already_customer") or f.get("crm_closed")}
    assert not (set(demo.company_id) & final), "won / lost / not-a-fit / customer accounts must leave the queue"
    assert (demo.byod_mode == "SYNTHETIC demo").all()


def test_queue_rows_are_complete_and_honest():
    from chase.gtm import nba
    qd = nba.build_queue(date(2026, 11, 16), demo=False)
    for c in ["company", "play", "opener_draft", "evidence", "who_role", "why_now", "queue_priority"]:
        assert qd[c].notna().all(), c
    assert qd.queue_priority.is_monotonic_decreasing
    assert not qd.opener_draft.str.contains("{").any(), "unfilled template slot"
    assert not qd.opener_draft.str.contains("—|–").any()
    assert set(qd.play) <= {"dinner_invite", "warm_via_supplier", "investor_intro", "cold_email", "brief_owner", "follow_up",
                            "prepare_meeting", "dinner_follow_up"}
    # investor intro and warm plays are impossible without bring-your-own-data
    assert not set(qd.play) & {"investor_intro", "warm_via_supplier", "brief_owner"}



def test_supplier_finance_accounts_get_the_reach_and_terms_opener():
    """A confirmed supplier finance programme means early cash is already on offer: the cold opener asks who the
    programme reaches and whether terms got longer, and never pitches early cash. One-reader finds never get the early-cash pitch."""
    from chase.gtm import nba
    qd = nba.build_queue(date(2026, 11, 16), demo=False, size=1000)
    cold = qd[qd.play == "cold_email"]
    sf = cold[cold.supplier_finance_disclosed == "yes_confirmed"]
    assert len(sf) > 10
    assert sf.opener_template.str.startswith("cold_email_sf").all()
    assert sf.opener_draft.str.contains("supplier finance programme").all()
    assert sf.opener_draft.str.contains("reach").all() and sf.opener_draft.str.contains("longer").all()
    early_cash_pitch = r"what early cash is worth|pay for earlier cash"
    assert not sf.opener_draft.str.contains(early_cash_pitch).any()
    one = cold[cold.supplier_finance_disclosed == "yes_one_reader"]
    assert not one.opener_draft.str.contains(early_cash_pitch).any()
    assert not one.opener_template.fillna("").str.startswith("cold_email_sf").any(), "an unconfirmed programme is not put to the buyer"
    assert not cold[cold.supplier_finance_disclosed != "yes_confirmed"].opener_template.str.startswith("cold_email_sf").any()


def test_why_now_and_opener_name_their_basis():
    """Why-now triggers quote one UK entity; the opener quotes the UK average across entities. Each says which it is."""
    from chase.gtm import nba, triggers
    t = triggers.build(date(2026, 11, 16))
    ent = t[t.trigger_type.isin(["filing_crossed_60", "filing_worsened"])]
    assert len(ent) and ent.text.str.contains(r"\(single UK entity\)").all()
    qd = nba.build_queue(date(2026, 11, 16), demo=False, size=1000)
    from chase import query as q
    comp = q.companies().set_index("company_id")
    multi = qd[qd.company_id.map(comp.pain_basis).eq("uk_reported") & qd.company_id.map(comp.uk_entities_n).gt(1)]
    assert len(multi) > 20
    assert multi.opener_draft.str.contains(r"UK average \d+ days across \d+ entities|UK average of \d+ days across \d+ entities").all()
    weighted = multi.company_id.map(comp.uk_days_aggregation).eq("invoice_value_weighted_mean")
    assert multi[~weighted].opener_draft.str.contains("weighted").sum() == 0, "a simple mean is never called weighted"

def test_feedback_needs_enough_outcomes_and_runs_on_demo():
    from chase.gtm import feedback
    assert feedback.analyse(False)["enough"] is False or (ROOT / "config/status/accounts_status.csv").exists()
    res = feedback.analyse(True)
    assert res["enough"] and res["outcomes"] >= 20 and res["components"]
    assert all(0 <= c["auc"] <= 1 for c in res["components"])
    assert feedback.auc(np.array([3.0, 4.0]), np.array([1.0, 2.0])) == 1.0
    assert feedback.auc(np.array([1.0]), np.array([1.0])) == 0.5
    assert "SYNTHETIC" in feedback.report(res, True)


def test_exports_have_no_person_fields():
    from chase.gtm import exports, nba
    d = exports._base(nba.build_queue(date(2026, 11, 16), demo=False))
    for f in (exports.hubspot, exports.attio, exports.salesforce):
        out = f(d)
        assert len(out) == 25
        assert not [c for c in out.columns if any(k in c.lower() for k in ("first", "last name", "email", "phone", "contact", "who_named"))]
    assert "Drafts only" in exports.slack_digest(nba.build_queue(date(2026, 11, 16)), date(2026, 11, 16), False)


def test_tracked_queue_files_never_contain_names(tmp_path):
    """The shareable queue file must not carry who_named even when private personas exist locally."""
    from chase.gtm import nba
    today = date(2026, 11, 16)
    qd = nba.build_queue(today, demo=False)
    csv_path, md_path = nba.write_queue(qd, today, demo=False, out=tmp_path)
    out = pd.read_csv(csv_path)
    assert out.who_named.isna().all() and out.who_source.isna().all()
    assert "data/private" not in str(csv_path)
    assert "names of individuals" not in md_path.read_text()


def test_no_dinner_dates_are_committed_and_outputs_say_next_dinner():
    import yaml
    from chase import answers, query as q
    from chase.gtm import nba
    cal = yaml.safe_load((ROOT / "config/dinners.yaml").read_text())["dinners"]
    assert {d["city"] for d in cal} == {"munich", "paris", "london", "madrid"}
    assert all(d.get("date") is None for d in cal), "real dinner dates belong in config/dinners.local.yaml (gitignored)"
    assert "config/dinners.local.yaml" in (ROOT / ".gitignore").read_text()
    if (ROOT / "config/dinners.local.yaml").exists():
        pytest.skip("a local dinner calendar is set; wording checks assume the committed one")
    text = answers.dinner("munich")
    assert text.startswith("**Next Munich dinner:")
    qd = nba.build_queue(date(2026, 11, 16), demo=False)
    inv = qd[qd.play == "dinner_invite"]
    assert len(inv) and inv.opener_draft.str.contains("our next small dinner for finance leaders in Munich. ").all()
    assert not inv.opener_draft.str.contains(r"\d{4}-\d{2}-\d{2}").any()


def test_local_dinner_calendar_overrides_by_city(tmp_path, monkeypatch):
    from chase import query as q
    (tmp_path / "config").mkdir()
    (tmp_path / "config/dinners.yaml").write_text((ROOT / "config/dinners.yaml").read_text())
    (tmp_path / "config/dinners.local.yaml").write_text("dinners:\n  - {city: paris, date: 2030-03-05}\n")
    monkeypatch.setattr(q, "ROOT", tmp_path)
    cal = {d["city"]: d for d in q.dinner_calendar()}
    assert cal["paris"]["date"] == "2030-03-05" and cal["paris"]["next"] and cal["munich"]["date"] is None
    assert q.dinner_upcoming(cal["paris"], date(2030, 3, 1)) and not q.dinner_upcoming(cal["paris"], date(2030, 3, 6))
    assert q.dinner_upcoming(cal["munich"], date(2030, 3, 6)) and not q.dinner_upcoming(cal["london"], date(2030, 3, 6))
    assert q.dinner_title("paris", "2030-03-05") == "Paris dinner (2030-03-05)" and q.dinner_title("munich", None) == "Next Munich dinner"
