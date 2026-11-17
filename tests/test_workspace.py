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
        assert re.search(r'class="c-key \w+"><b>\d+d</b> <span>vs ', summary), a["company"]
        assert summary.count('class="chip"') <= 2 and "<p" not in summary and "<li" not in summary
        detail = row.split("</summary>")[1]
        if a.get("evidence_url"):
            assert html_escape(a["evidence_url"]) in detail
        assert html_escape(a["opener_draft"]) in detail and "Copy opener" in detail
        assert f'accounts/{a["company_id"]}.html' in detail


def html_escape(s):
    import html
    return html.escape(s)
