"""Internal GTM workspace: build, disclaimer and noindex on every page, and the privacy guard rails.
Run: .venv/bin/python -m pytest tests/test_workspace.py -q"""
import json
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
DIST = ROOT / "workspace" / "dist"
DISCLAIMER = "Independent project by Moritz Hanbuch."
PERSONAS = ROOT / "data" / "private" / "personas.csv"


@pytest.fixture(scope="module", autouse=True)
def built():
    r = subprocess.run([sys.executable, str(ROOT / "workspace" / "build.py")], cwd=ROOT, capture_output=True, text=True)
    assert r.returncode == 0, r.stderr[-2000:]
    return r


def _html():
    return sorted(DIST.rglob("*.html"))


def test_pages_exist():
    for p in ("index.html", "dinners.html", "triggers.html", "method.html"):
        assert (DIST / p).exists(), p
    assert len(list((DIST / "accounts").glob("*.html"))) >= 25
    for j in ("queue.json", "triggers.json", "dinners.json", "accounts.json"):
        assert (DIST / "data" / j).exists(), j


def test_every_page_has_disclaimer_and_noindex():
    pages = _html()
    assert pages
    for p in pages:
        s = p.read_text()
        assert DISCLAIMER in s, p.relative_to(DIST)
        assert '<meta name="robots" content="noindex">' in s, p.relative_to(DIST)


def test_no_personal_names_anywhere():
    """No full_name from the private personas file may appear in any built file. Names are never printed."""
    if not PERSONAS.exists():
        pytest.skip("no local private personas file")
    import pandas as pd
    names = {str(n).strip() for n in pd.read_csv(PERSONAS, usecols=["full_name"]).full_name.dropna() if len(str(n).strip()) > 3}
    leaks = 0
    for f in DIST.rglob("*"):
        if f.is_file() and f.suffix in {".html", ".json", ".js", ".css", ".txt"}:
            s = f.read_text(errors="ignore")
            leaks += sum(1 for n in names if n in s)
    assert leaks == 0, f"{leaks} personal-name occurrences found in workspace/dist (names not printed)"


def test_no_private_keys_or_triggers():
    for f in (DIST / "data").rglob("*.json"):
        s = f.read_text()
        for k in ('"who_named"', '"people_private"', '"who_source"'):
            assert k not in s, (f.name, k)
    t = json.loads((DIST / "data" / "triggers.json").read_text())
    assert t["triggers"], "trigger feed is empty"
    assert not any(x.get("private_source") is True for x in t["triggers"])


def test_private_trigger_text_not_in_queue():
    """The queue's why_now summary must not carry text from private-source triggers."""
    sys.path.insert(0, str(ROOT / "src"))
    from chase.gtm import api
    allt = api.get_triggers(since="1900-01-01", limit=1_000_000)["triggers"]
    private = {(t["company_id"], t["text"]) for t in allt if t.get("private_source") is True}
    q = json.loads((DIST / "data" / "queue.json").read_text())
    for a in q["accounts"]:
        for seg in (a.get("why_now") or "").split(" | "):
            assert (a["company_id"], seg) not in private


def test_no_demo_data():
    q = json.loads((DIST / "data" / "queue.json").read_text())
    assert "SYNTHETIC" not in json.dumps(q)


def test_queue_page_is_compact_rows_with_details():
    """One compact row per account (rank, company, tier, play, role, key number, at most 2 tags), no intro paragraph,
    and the evidence, its source, why-now events and the opener available in the expanded view."""
    import re
    h = (DIST / "index.html").read_text()
    q = json.loads((DIST / "data" / "queue.json").read_text())
    assert 'class="lede"' not in h
    rows = re.findall(r'<details class="qrow".*?</details>', h, re.S)
    assert len(rows) == len(q["accounts"]) > 0
    for row, a in zip(rows, q["accounts"]):
        summary = row.split("</summary>")[0]
        assert re.search(r'class="c-key \w+"[^>]*><b>\d+d</b> <span>vs ', summary), a["company"]
        assert 'class="c-spark' in summary and 'select class="status"' in summary
        assert summary.count('class="chip"') <= 2 and not re.search(r"<(p|li)[ >]", summary)
        detail = row.split("</summary>")[1]
        if a.get("evidence_url"):
            assert html_escape(a["evidence_url"]) in detail
        assert html_escape(a["opener_draft"]) in detail and "Copy opener" in detail
        assert f'accounts/{a["company_id"]}.html' in detail


def test_queue_tool_controls_and_neutral_theme():
    """Summary strip, export button, shortcuts panel; the default build (as in the test fixture with --neutral)
    links no theme override, and every colour in the stylesheet sits in a variable block."""
    import re
    r = subprocess.run([sys.executable, str(ROOT / "workspace" / "build.py"), "--neutral"], cwd=ROOT, capture_output=True, text=True)
    assert r.returncode == 0 and "neutral default" in r.stdout
    h = (DIST / "index.html").read_text()
    assert 'class="strip"' in h and 'id="export-status"' in h and 'id="kbd-help"' in h
    strip = h.split('class="strip"')[1].split("</div>")[0]
    for label in ("over 60 days", "paying slower", "treasurer plays", "AP plays", "dinner invite"):
        assert label in strip, label
    assert " T1" not in strip and "reported" not in strip and "live trigger" not in strip
    assert 'class="lede"' not in (DIST / "triggers.html").read_text()
    assert h.count("Drafts only") == 1 and "1 live events" not in h
    assert "theme.css" not in h and not (DIST / "assets" / "theme.css").exists()
    css = (ROOT / "workspace" / "static" / "style.css").read_text()
    outside = re.sub(r":root[^{]*\{[^}]*\}", "", css)
    assert not re.findall(r"#[0-9a-fA-F]{3,8}\b|rgba?\(", outside), "hard-coded colour outside the theme variables"


def test_dinners_triggers_method_and_search():
    """Dinner builder: no intro, City area / Rest of country groups, key number per row, invite status and export.
    Trigger feed: dinner triggers hidden under 'All', a dash for a missing source, last-30-days window first.
    Method: full methodology collapsed. Every page: account search with one entry per account page."""
    import re
    d = (DIST / "dinners.html").read_text()
    assert 'class="lede"' not in d and "City area (" in d and 'select class="inv"' in d and 'data-act="inv-export"' in d
    assert re.search(r'class="d-key \w+"[^>]*><b>\d+d</b>', d)
    js = (ROOT / "workspace" / "static" / "app.js").read_text()
    assert '"city,date,account_name,status"' in js       # config/byod/dinner_attendees.csv columns
    t = (DIST / "triggers.html").read_text()
    assert 'data-hide-on-all="dinner_city"' in t and '<option value="30">Last 30 days</option>' in t.split("data-window>")[1][:60]
    rows = re.findall(r"<tr data-type=.*?</tr>", t, re.S)
    assert all(("href=" in r.split("</td>")[-2]) or ("\u2013" in r.split("</td>")[-2]) for r in rows)
    assert "no source link" in t
    m = (DIST / "method.html").read_text()
    assert 'class="kinds"' in m and '<details class="full"><summary>Show full methodology</summary>' in m
    q = (DIST / "index.html").read_text()
    ids = re.findall(r'<option value="[^"]*" data-id="([^"]+)">', q)
    assert len(ids) == len(set(ids)) == len(list((DIST / "accounts").glob("*.html")))
    assert all((DIST / "accounts" / f"{i}.html").exists() for i in ids)


def test_theme_override_is_sanitised():
    wb = _wb()
    css = wb.theme_css({"light": {"bg": "#fff", "--accent": "color-mix(in srgb, #123 40%, #fff)", "unknown": "red",
                                  "fg": "red;}body{display:none", "font": "url(http://x)"}, "dark": {"bg": "#000"}})
    assert "--bg:#fff" in css and "--accent:color-mix(in srgb, #123 40%, #fff)" in css
    assert "unknown" not in css and "display:none" not in css and "url(" not in css
    assert "@media (prefers-color-scheme:dark){:root:not([data-theme=light]){--bg:#000}}" in css and ":root[data-theme=dark]{--bg:#000}" in css


def test_sparkline_is_plain_svg():
    wb = _wb()
    s = wb.sparkline([("2024-H1", 50.0), ("2024-H2", 61.0), ("2025-H1", 70.0)], "UK reports per half-year.", 32)
    assert s.startswith("<svg") and "<polyline" in s and 'class="bench"' in s and "2025-H1 70d" in s and "<script" not in s
    assert "no series" in wb.sparkline([], "", None)


def test_status_export_format_is_read_by_the_feedback_loop(monkeypatch):
    """The workspace exports company_id,company,status,reason,date,play with statuses contacted / meeting / not_a_fit.
    The same reader make feedback uses must accept it."""
    import re
    js = (ROOT / "workspace" / "static" / "app.js").read_text()
    assert '"company_id,company,status,reason,date,play"' in js
    exported = set(re.findall(r'\["(\w+)", "[^"]*"\]', js.split("var EXPORT")[1].split(";")[0]))
    sys.path.insert(0, str(ROOT / "src"))
    from chase import query as q
    from chase.gtm import byod
    assert exported and exported <= byod.VALID_STATUSES
    cid = q.companies().company_id.iloc[0]
    tmp_path = ROOT / "tmp" / "test_status_export"   # inside the repo (gitignored): the reader reports paths relative to it
    tmp_path.mkdir(parents=True, exist_ok=True)
    (tmp_path / "accounts_status.csv").write_text(f"company_id,company,status,reason,date,play\n{cid},X,not_a_fit,not now,2026-11-18,cold_email\n")
    monkeypatch.setattr(byod, "STATUS", tmp_path)
    flags, _ = byod.apply(False)
    assert flags[cid]["status"]["status"] == "not_a_fit" and flags[cid]["status"]["reason"] == "not now"


def _wb():
    """workspace/build.py loaded by path (another module named build can already sit in sys.modules)."""
    import importlib.util
    spec = importlib.util.spec_from_file_location("workspace_build", ROOT / "workspace" / "build.py")
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


def html_escape(s):
    import html
    return html.escape(s)
