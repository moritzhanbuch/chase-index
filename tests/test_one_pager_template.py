"""One-pager template rules: conversation angle follows the queue-opener logic, YoY phrasing, entity table, labels."""
import re
from pathlib import Path

import pandas as pd
import pytest

ROOT = Path(__file__).resolve().parents[1]
pytestmark = pytest.mark.skipif(not (ROOT / "data/processed/companies.parquet").exists(), reason="run `make data score` first")


def _accounts():
    idx = ROOT / "outputs/one_pagers/index.csv"
    d = pd.read_csv(idx)
    return d[d.columns[0]].tolist() if "company_id" not in d else d.company_id.tolist()


def test_angle_uses_up_n_to_x_and_never_at_n_days():
    from chase import query as q
    from chase.assets import build as B
    for cid in _accounts():
        a = B.conversation_angle(q.get_account_brief(cid), q._row(cid))
        assert not re.search(r"\bat \d+ days\b", a), (cid, a)
        for m in re.finditer(r"up (\d+) days to (\d+) days", a):
            assert int(m.group(2)) > int(m.group(1)) > 0


def test_angle_follows_opener_logic_reckitt():
    from chase import query as q
    from chase.assets import build as B
    cid = "reckitt-benckiser-group-plc-lei48v108"
    b = q.get_account_brief(cid)
    late = b["payment_profile"]["reported"]["uk"]["pct_invoices_paid_late_mean"]
    assert late < 25                                          # low late share, long days
    a = B.conversation_angle(b, q._row(cid))
    assert a.startswith("Ask for the group treasurer or CFO office.")
    assert "working-capital topic" in a and "did terms get longer when the programme came in?" in a
    assert "earlier cash" not in a                            # a disclosed programme drops the early-cash line
    assert "up 18 days to 77 days" in a


def test_process_framing_when_many_invoices_are_late():
    from chase import query as q
    from chase.assets import build as B
    for cid in _accounts():
        b = q.get_account_brief(cid)
        uk = b["payment_profile"]["reported"].get("uk")
        if b["scores"]["pain_basis"] != "uk_reported" or uk["pct_invoices_paid_late_mean"] is None:
            continue
        a = B.conversation_angle(b, q._row(cid))
        sf = b.get("supplier_finance") or {}
        if sf.get("programme_disclosed") and sf.get("confirmed"):     # supplier finance angle: treasury, same as the queue
            assert "group treasurer or CFO office" in a and "did terms get longer" in a and "start with process" not in a, cid
        elif 25 <= uk["pct_invoices_paid_late_mean"] <= 75:
            assert "start with process" in a and "head of accounts payable" in a, cid


def test_entity_table_and_unweighted_label():
    from chase import query as q
    from chase.assets import build as B
    for cid in _accounts():
        b = q.get_account_brief(cid)
        uk = b["payment_profile"]["reported"].get("uk")
        if b["scores"]["pain_basis"] != "uk_reported":       # the entity table is shown for UK-evidence accounts
            continue
        _, doc = B.render_one_pager(cid)
        table = doc.split("UK entity (link = official report)")[1].split("</table>")[0]
        shown = table.count("<tr>")
        assert shown == (uk["entities_n"] if uk["entities_n"] <= B.UK_TABLE_ALL_MAX else 5), cid
        assert "Simple mean of the entities (unweighted)" in doc
        assert "rose by about" not in doc
