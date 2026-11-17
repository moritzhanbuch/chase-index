"""The first-try experience: every MCP tool and the skill answer in short text first, computed live from data/processed."""
import subprocess

import pytest

from chase import answers as A
from chase import query as q


def _head(text: str) -> str:
    return text.split("\n\n---\n")[0]


def test_generated_outputs_are_not_tracked():
    tracked = subprocess.run(["git", "ls-files", "outputs/queue", "outputs/invites", "outputs/outreach", "outputs/exports"],
                             cwd=q.ROOT, capture_output=True, text=True).stdout
    assert tracked.strip() == ""


def test_answer_code_reads_no_generated_files():
    for f in ("src/chase/answers.py", "src/chase/gtm/api.py", "mcp/server.py", "skill/chase-brief/scripts/chase_brief.py"):
        src = (q.ROOT / f).read_text()
        for d in ("outputs/queue", "outputs/invites", "outputs/outreach", "outputs/exports", '"queue" /', '"invites" /'):
            assert d not in src, (f, d)


def test_start_here_is_five_lines_and_three_questions():
    t = A.start_here()
    assert len([x for x in t.splitlines() if x[:2] in ("1.", "2.", "3.", "4.", "5.")]) == 5
    assert len([x for x in t.splitlines() if x.startswith('- "')]) == 3


def test_queue_answer_leads_with_text_and_carries_opener_and_source():
    t = A.weekly_queue(5)
    head = _head(t)
    assert head.startswith("**Week ") and head.count("Open with:") == 5 and head.count("[source](") >= 10
    head10 = _head(A.weekly_queue(10))
    assert head10.count("Open with:") == A.FULL_N and "**Next 5**" in head10 and len(head10.split()) < 1000
    assert "Details (structured)" in t and "{" not in head.splitlines()[0]


def test_brief_key_number_matches_the_evidence_behind_the_opener():
    head = _head(A.account_brief("Telefónica"))           # scored on Spanish PMP: the key number must be the Spanish one
    assert head.split("- Key number: ")[1].startswith("REPORTED (Spain)")
    head = _head(A.account_brief("Reckitt"))
    assert "Key number: REPORTED (UK)" in head and "Open with" in head and "Why now" in head


def test_proxy_is_never_labelled_reported():
    head = _head(A.account_brief("Walmart"))
    assert "Key number: COMPUTED PROXY" in head and "ESTIMATE" in head


def test_dinner_answer_is_honest_about_local_hq():
    head = _head(A.dinner("munich"))
    assert "headquartered in the Munich area" in head and "[source](" in head


def test_unknown_company_does_not_guess():
    assert "No company called" in A.account_brief("Nonexistent Widgets Corp") or "UK legal entities" in A.account_brief("Nonexistent Widgets Corp")


def test_every_mcp_tool_returns_text_answer_first():
    pytest.importorskip("mcp")
    import importlib.util
    spec = importlib.util.spec_from_file_location("chase_mcp_server", q.ROOT / "mcp" / "server.py")
    srv = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(srv)
    calls = [srv.start_here(), srv.weekly_queue(3), srv.get_account_brief("Reckitt"), srv.dinner_builder("munich"),
             srv.triggers(), srv.top_targets(country="DE", limit=3), srv.get_payment_profile("Diageo"),
             srv.lookup_uk_supplier_payment_record("Tesco Stores", 2), srv.search_companies("siemens", limit=3),
             srv.account_workspace("Nestlé"), srv.byod_status(), srv.explain_methodology("DPO")]
    for out in calls:
        assert isinstance(out, str) and out.strip() and not out.lstrip().startswith(("{", "["))


def test_answers_are_read_only():
    """The MCP server and the skill must not write anything (a plugin install lives in Claude Code's cache)."""
    files = [p for d in ("data", "outputs", "config") for p in (q.ROOT / d).rglob("*") if p.is_file()]
    before = {p: p.stat().st_mtime_ns for p in files}
    A.weekly_queue(5); A.account_brief("Reckitt"); A.dinner("munich"); A.triggers(); A.byod()
    changed = [str(p) for p in files if p.exists() and p.stat().st_mtime_ns != before[p]]
    assert not changed, changed
