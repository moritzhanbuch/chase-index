"""Browser test for the workspace: filters and tabs must change what is actually on screen, not just set an attribute.
(Rows use display:grid, which once overrode [hidden] so the queue tabs set the attribute but showed every row.)
Needs Playwright with Chromium; skipped otherwise. Builds with --neutral so a local theme never matters."""
import functools
import http.server
import subprocess
import sys
import threading
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
DIST = ROOT / "workspace" / "dist"
sync_api = pytest.importorskip("playwright.sync_api")


@pytest.fixture(scope="module")
def site():
    r = subprocess.run([sys.executable, str(ROOT / "workspace" / "build.py"), "--neutral"], cwd=ROOT, capture_output=True, text=True)
    assert r.returncode == 0, r.stderr[-2000:]
    handler = functools.partial(http.server.SimpleHTTPRequestHandler, directory=str(DIST))
    handler.log_message = lambda *a: None
    srv = http.server.ThreadingHTTPServer(("127.0.0.1", 0), handler)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    try:
        with sync_api.sync_playwright() as p:
            try:
                b = p.chromium.launch()
            except Exception as e:  # browser binary not installed
                pytest.skip(f"chromium not available: {e}")
            yield b, f"http://127.0.0.1:{srv.server_port}/"
            b.close()
    finally:
        srv.shutdown()


def _visible(pg, sel):
    return pg.eval_on_selector_all(sel, "els => els.filter(e => e.getBoundingClientRect().height > 0).length")


def test_queue_tabs_filter_the_visible_rows(site):
    b, base = site
    pg = b.new_page(viewport={"width": 1280, "height": 900})
    errors = []
    pg.on("pageerror", lambda e: errors.append(str(e)))
    pg.goto(base + "index.html")
    total = _visible(pg, ".qrow")
    assert total == pg.locator(".qrow").count() > 0
    seen = {}
    for tab in ("treasury", "ap", "dinner", "all"):
        pg.click(f'.tab[data-tab="{tab}"]')
        expected = int(pg.locator(f'.tab[data-tab="{tab}"] .cnt').inner_text())
        seen[tab] = _visible(pg, ".qrow")
        assert seen[tab] == expected, (tab, seen[tab], expected)
        if tab == "treasury":
            assert _visible(pg, '.qrow[data-contact="ap"]') == 0
        if tab == "ap":
            assert _visible(pg, '.qrow[data-contact="treasury"]') == 0
    assert seen["all"] == total and seen["treasury"] + seen["ap"] == total and seen["treasury"] < total
    # the side panel opens from a row and closes with Esc
    pg.locator(".qrow").first.click()
    assert pg.locator("#panel").is_visible()
    pg.keyboard.press("Escape")
    assert not pg.locator("#panel").is_visible()
    assert not errors, errors


def test_trigger_filters_hide_rows_on_screen(site):
    b, base = site
    pg = b.new_page(viewport={"width": 1280, "height": 900})
    pg.goto(base + "triggers.html")
    shown = int(pg.locator(".count").inner_text().split(" of ")[0])
    assert _visible(pg, ".trow") == shown < pg.locator(".trow").count()
    assert _visible(pg, '.trow[data-type="dinner_city"]') == 0
    pg.select_option("select[data-window]", "")
    pg.select_option("select[data-filter=type]", "dinner_city")
    assert _visible(pg, ".trow") == _visible(pg, '.trow[data-type="dinner_city"]') > 0


def test_search_dropdown_arrow_keys_and_enter(site):
    b, base = site
    pg = b.new_page(viewport={"width": 1280, "height": 900})
    pg.goto(base + "index.html")
    pg.keyboard.press("/")
    pg.keyboard.type("si")
    items = pg.locator("#acct-dd li")
    assert pg.locator("#acct-dd").is_visible() and 1 <= items.count() <= 8
    assert pg.locator("#acct-dd .dd-n").first.inner_text().lower().startswith("si")   # prefix matches first
    pg.keyboard.press("ArrowDown")
    want = pg.locator('#acct-dd li[aria-selected="true"] .dd-n').inner_text()
    pg.keyboard.press("Enter")
    pg.wait_for_load_state("networkidle")
    assert "/accounts/" in pg.url and want in pg.locator("h1").inner_text()


def test_ticker_pauses_dismisses_and_respects_reduced_motion(site):
    b, base = site
    pg = b.new_page(viewport={"width": 1280, "height": 900})
    pg.goto(base + "index.html")
    track = ".ticker .tk-track"
    assert pg.eval_on_selector(track, "e => getComputedStyle(e).animationName") == "tk"
    pg.hover(".ticker .tk-view")
    assert pg.eval_on_selector(track, "e => getComputedStyle(e).animationPlayState") == "paused"
    pg.click(".tk-x")
    assert not pg.locator(".ticker").is_visible()
    pg.reload()
    assert not pg.locator(".ticker").is_visible()          # stays dismissed until a newer trigger arrives
    ctx = b.new_context(viewport={"width": 1280, "height": 900}, reduced_motion="reduce")
    pg2 = ctx.new_page()
    pg2.goto(base + "index.html")
    assert pg2.eval_on_selector(track, "e => getComputedStyle(e).animationName") == "none"
    ctx.close()


def test_copy_shows_tick_then_resets(site):
    b, base = site
    ctx = b.new_context(viewport={"width": 1280, "height": 900}, permissions=["clipboard-read", "clipboard-write"])
    pg = ctx.new_page()
    pg.goto(base + "index.html")
    pg.locator(".qrow").first.click()
    btn = pg.locator("#panel button.copy")
    btn.click()
    pg.wait_for_function("() => document.querySelector('#panel button.copy').textContent === 'Copied \u2713'", timeout=1000)
    pg.wait_for_timeout(1700)
    assert btn.text_content() == "Copy opener"
    ctx.close()
