"""Phase 12 wiring: supplier finance, UK field signals, mandates and the queue opener."""
import pandas as pd
import yaml

from chase import query as q
from chase.gtm import nba, triggers
from chase.score import build as sb

P = q.P


def test_mandates_say_who_they_bind():
    m = yaml.safe_load((q.ROOT / "config" / "einvoicing_mandates.yaml").read_text())["mandates"]
    assert all(x.get("binds") in {"buyer_directly", "suppliers_of_buyer", "member_states"} for x in m)


def test_supplier_mandate_triggers_are_labelled_as_such():
    t = pd.read_parquet(P / "triggers.parquet")
    s = t[t.trigger_type == "einvoicing_mandate_suppliers"]
    assert s.text.str.contains("smaller suppliers").all()
    assert not t.trigger_type.eq("einvoicing_mandate").any() or not t[t.trigger_type == "einvoicing_mandate"].text.str.contains("smaller suppliers").any()


def test_only_confirmed_supplier_finance_is_scored_or_triggered():
    sf = pd.read_parquet(P / "supplier_finance.parquet")
    confirmed = set(sf.loc[sf.programme_confirmed, "company_id"])
    sig = sb.load_signals()
    assert set(sig.loc[sig.signal_type == "sf_disclosed", "company_id"]) <= confirmed
    t = pd.read_parquet(P / "triggers.parquet")
    assert set(t.loc[t.trigger_type == "sf_disclosed", "company_id"]) <= confirmed


def test_inconsistent_dispute_shares_are_excluded():
    e = pd.read_parquet(P / "uk_entity_features.parquet")
    g = pd.read_parquet(P / "uk_group_features.parquet")
    bad = e[e.pct_paid_late.notna() & (e.pct_not_paid_due_to_dispute > e.pct_paid_late + 0.5)]
    # no group's evidence entity for the dispute share is an inconsistent filer
    assert not set(g.dispute_share_evidence_entity.dropna()) & set(bad.company_name)


def test_trigger_feed_has_no_future_dated_events_outside_window():
    t = triggers.since("2000-01-01")
    today = pd.Timestamp.today().date()
    past_types = ~t.trigger_type.isin(triggers.UPCOMING_WINDOW)
    assert (t.loc[past_types, "trigger_date"] <= today).all()
    assert t.loc[~past_types, "is_live"].all()


def test_late_opener_is_self_contained():
    from datetime import date
    from chase.gtm import nba
    qd = nba.build_queue(date.today(), demo=False)
    assert not qd.opener_draft.str.contains("that share", regex=False).any()
    assert set(qd.supplier_finance_disclosed.dropna()) <= {"yes_confirmed", "yes_one_reader", "no_evidence", "no_source", "no", "unclear"}
