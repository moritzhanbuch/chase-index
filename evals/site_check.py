"""Site check: load every page type in a real browser at desktop and mobile widths.

Run: .venv/bin/python evals/site_check.py      (build first: make site)

- serves site/dist from a local static server on a free port (nothing leaves this machine)
- screenshots into evals/reports/site_screenshots/
- records console errors, failed requests and any request to a non-local host
- checks for page-level horizontal overflow at 375 px
- tests the supplier lookup with 10 UK entities picked from the data at run time
- writes evals/reports/site_check.md
"""
import functools
import http.server
import json
import socketserver
import sys
import threading
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd
from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parents[1]
DIST = ROOT / "site" / "dist"
SHOTS = ROOT / "evals" / "reports" / "site_screenshots"
REPORT = ROOT / "evals" / "reports" / "site_check.md"
SEED = 20261116
VIEWPORTS = {"desktop": (1280, 900), "mobile": (375, 812)}


class Quiet(http.server.SimpleHTTPRequestHandler):
    def log_message(self, *a):
        pass


def serve():
    handler = functools.partial(Quiet, directory=str(DIST))
    srv = socketserver.ThreadingTCPServer(("127.0.0.1", 0), handler)
    srv.daemon_threads = True
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    return srv, f"http://127.0.0.1:{srv.server_address[1]}/"


def pick_company_page():
    """One company page with UK entities, Spanish data and a DPO block if such a group exists, else the first with UK data."""
    c = pd.read_parquet(ROOT / "data" / "processed" / "companies.parquet")
    c = c[c.uk_entities_n.notna()]
    both = c[c.es_pmp_days.notna() & (c.dpo_flag == "ok")]
    pick = (both if len(both) else c).sort_values("uk_entities_n", ascending=False).iloc[0]
    return f"company/{pick.company_id}.html"


def lookup_sample():
    e = pd.read_parquet(ROOT / "data" / "processed" / "uk_entity_latest.parquet")
    cur = e[e.has_usable_report.fillna(False).astype(bool) & ~e.latest_is_stale.fillna(True).astype(bool)]
    s = cur.sample(9, random_state=SEED)
    old = e[e.has_usable_report.fillna(False).astype(bool) & e.latest_is_stale.fillna(False).astype(bool)].sample(1, random_state=SEED)
    return pd.concat([s, old])[["company_name", "company_number", "avg_days_to_pay", "latest_is_stale"]]


def main():
    if not (DIST / "index.html").exists():
        sys.exit("site/dist is missing. Run: make site")
    SHOTS.mkdir(parents=True, exist_ok=True)
    srv, base = serve()
    pages = {"home": "index.html", "company": pick_company_page(), "lookup": "lookup.html", "spain": "spain.html",
             "methodology": "methodology.html", "faq": "faq.html", "about": "about.html", "data": "data.html",
             "data-dictionary": "data-dictionary.html", "limitations": "limitations.html", "corrections": "corrections.html"}
    rows, problems, lookups = [], [], []
    with sync_playwright() as pw:
        browser = pw.chromium.launch()
        for vp, (w, h) in VIEWPORTS.items():
            for scheme in (["light", "dark"] if vp == "desktop" else ["light"]):
                ctx = browser.new_context(viewport={"width": w, "height": h}, color_scheme=scheme)
                for name, path in pages.items():
                    if scheme == "dark" and name not in ("home", "company"):
                        continue
                    page = ctx.new_page()
                    errors, failed, external = [], [], []
                    page.on("console", lambda m, errors=errors: errors.append(m.text) if m.type == "error" else None)
                    page.on("pageerror", lambda e, errors=errors: errors.append(str(e)))
                    page.on("requestfailed", lambda r, failed=failed: failed.append(r.url))
                    page.on("response", lambda r, failed=failed: failed.append(f"{r.status} {r.url}") if r.status >= 400 else None)
                    page.on("request", lambda r, external=external: external.append(r.url) if not r.url.startswith(base) else None)
                    page.goto(base + path, wait_until="networkidle")
                    m = page.evaluate("""() => ({sw: document.documentElement.scrollWidth, cw: document.documentElement.clientWidth,
                        h1: (document.querySelector('h1') || {}).textContent || '',
                        disclaimer: document.querySelector('footer .disclaimer') ? document.querySelector('footer .disclaimer').textContent : ''})""")
                    overflow = m["sw"] > m["cw"] + 1
                    shot = SHOTS / f"{name}_{vp}{'_dark' if scheme == 'dark' else ''}.png"
                    page.screenshot(path=str(shot), full_page=(name not in ("home", "data-dictionary") or vp == "mobile") and name != "data-dictionary")
                    ok = not errors and not failed and not external and not overflow and bool(m["h1"].strip()) and "Moritz Hanbuch" in m["disclaimer"]
                    rows.append((name, path, f"{vp} {w}px {scheme}", len(errors), len(failed), len(external),
                                 "yes" if overflow else "no", "pass" if ok else "FAIL", shot.name))
                    if not ok:
                        problems.append({"page": path, "viewport": vp, "errors": errors, "failed": failed, "external": external,
                                         "overflow": [m["sw"], m["cw"]]})
                    page.close()
                ctx.close()

        # interaction checks on the home table
        ctx = browser.new_context(viewport={"width": 1280, "height": 900})
        page = ctx.new_page()
        page.goto(base + "index.html", wait_until="networkidle")
        visible = "() => parseInt(document.querySelector('[data-count]').textContent, 10)"
        page.locator("figure.chart").first.scroll_into_view_if_needed()
        page.locator(".charts").screenshot(path=str(SHOTS / "home_charts_desktop.png"))
        n_all = page.evaluate(visible)
        page.select_option("[data-f=country]", "GB")
        n_gb = page.evaluate(visible)
        page.select_option("[data-f=country]", "")
        names0 = page.evaluate("() => [...document.querySelectorAll('#groups-table tbody tr')].map(r => r.getAttribute('data-name'))")
        page.click("#groups-table th[data-col='4'] button")
        vals = page.evaluate("""() => [...document.querySelectorAll('#groups-table tbody tr')].filter(r => !r.hidden)
            .map(r => r.cells[4].getAttribute('data-v')).filter(v => v !== '').map(Number)""")
        default_alpha = names0 == sorted(names0)
        sort_ok = vals == sorted(vals, reverse=True) and len(vals) > 5 and default_alpha
        page.click("button.more")
        shown_all = page.evaluate("() => [...document.querySelectorAll('#groups-table tbody tr')].filter(r => !r.hidden).length")
        sort_ok = sort_ok and shown_all == n_all
        table_ok = 0 < n_gb < n_all and sort_ok
        page.close()

        # lookup test
        page = ctx.new_page()
        requested = []
        page.on("request", lambda r: requested.append(r.url))
        page.goto(base + "lookup.html", wait_until="networkidle")
        lazy = not any("lookup-index.json" in u for u in requested)
        for r in lookup_sample().itertuples():
            for query, kind in ((r.company_name, "name"), (r.company_number, "number")):
                page.fill("#lookup-q", "")
                page.fill("#lookup-q", query)
                sel = f"#lookup-results li.result[data-number='{r.company_number}']"
                try:
                    page.wait_for_selector(sel, timeout=5000)
                    shown = page.get_attribute(sel, "data-days")
                    text = page.inner_text(sel)
                    first = page.get_attribute("#lookup-results li.result", "data-number")
                    ok = shown != "" and float(shown) == float(r.avg_days_to_pay) and "check-payment-practices" in page.get_attribute(sel + " a", "href")
                    if bool(r.latest_is_stale):
                        ok = ok and "old report" in text
                except Exception as e:  # noqa: BLE001
                    shown, first, ok = f"not found ({type(e).__name__})", None, False
                lookups.append((r.company_name, r.company_number, kind, r.avg_days_to_pay, shown, first == r.company_number,
                                bool(r.latest_is_stale), ok))
        page.screenshot(path=str(SHOTS / "lookup_result_desktop.png"))
        page.set_viewport_size({"width": 375, "height": 812})
        lookup_overflow = page.evaluate("() => document.documentElement.scrollWidth > document.documentElement.clientWidth + 1")
        page.screenshot(path=str(SHOTS / "lookup_result_mobile.png"))
        browser.close()
    srv.shutdown()

    by_name = [l for l in lookups if l[2] == "name"]
    by_num = [l for l in lookups if l[2] == "number"]
    n_pass = sum(1 for r in rows if r[7] == "pass")
    summary = json.loads((DIST / "build-summary.json").read_text())
    out = ["# Site check", "",
           f"Run: {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')}. Method: Playwright (Chromium, headless) against a local static server on 127.0.0.1 serving `site/dist`. Nothing was deployed.",
           "", "## Result", "",
           f"- Page loads: {n_pass} of {len(rows)} pass (no console errors, no failed requests, no external requests, no horizontal overflow, h1 and disclaimer present).",
           f"- Console errors: {sum(r[3] for r in rows)}. Failed requests: {sum(r[4] for r in rows)}. Requests to external hosts: {sum(r[5] for r in rows)}.",
           f"- Horizontal overflow at 375 px: {sum(1 for r in rows if r[6] == 'yes' and 'mobile' in r[2])} pages. Lookup results at 375 px overflow: {'yes' if lookup_overflow else 'no'}.",
           f"- Supplier lookup by name: {sum(1 for l in by_name if l[7])} of {len(by_name)} show the same average days to pay as the data. By company number: {sum(1 for l in by_num if l[7])} of {len(by_num)}.",
           f"- Searched entity is the first result when searching by name: {sum(1 for l in by_name if l[5])} of {len(by_name)} (others share a name prefix with a shorter-named entity).",
           f"- Lookup index is lazy-loaded (not requested before the first keystroke): {'yes' if lazy else 'NO'}.",
           f"- Home table: country filter narrows {n_all} rows to {n_gb} for GB, default order is alphabetical, sorting by days to pay works, show-all works: {'pass' if table_ok else 'FAIL'}.",
           f"- Build: {summary['pages_total']} pages, {summary['dist_bytes'] / 1e6:.1f} MB, lookup index {summary['lookup_index_bytes'] / 1e3:.0f} kB.",
           "", "## Pages", "", "| Page | Path | Viewport | Console errors | Failed requests | External requests | Overflow | Result | Screenshot |",
           "|---|---|---|---|---|---|---|---|---|"]
    out += [f"| {r[0]} | `{r[1]}` | {r[2]} | {r[3]} | {r[4]} | {r[5]} | {r[6]} | {r[7]} | `site_screenshots/{r[8]}` |" for r in rows]
    out += ["", "## Lookup test", "", f"10 entities sampled from `uk_entity_latest.parquet` (seed {SEED}): 9 with a current report, 1 with an old report. Each is typed into the search box by name and by company number.",
            "", "| Entity | Number | Query by | Days in data | Days shown | First result | Old report | Result |", "|---|---|---|---|---|---|---|---|"]
    out += [f"| {l[0]} | {l[1]} | {l[2]} | {l[3]:g} | {l[4]} | {'yes' if l[5] else 'no'} | {'yes' if l[6] else 'no'} | {'pass' if l[7] else 'FAIL'} |" for l in lookups]
    out += ["", "## Failures and fixes", ""]
    out += [f"- `{p['page']}` ({p['viewport']}): {json.dumps({k: v for k, v in p.items() if k not in ('page', 'viewport') and v})}" for p in problems] or ["None in this run."]
    REPORT.write_text("\n".join(out) + "\n", encoding="utf-8")
    all_ok = n_pass == len(rows) and all(l[7] for l in lookups) and table_ok and lazy and not lookup_overflow
    print(f"pages {n_pass}/{len(rows)} pass; lookup by name {sum(1 for l in by_name if l[7])}/{len(by_name)}, by number {sum(1 for l in by_num if l[7])}/{len(by_num)}; "
          f"table {'ok' if table_ok else 'FAIL'}; lazy {'ok' if lazy else 'FAIL'}; report {REPORT.relative_to(ROOT)}")
    for p in problems:
        print("PROBLEM", json.dumps(p)[:600])
    sys.exit(0 if all_ok else 1)


if __name__ == "__main__":
    main()
