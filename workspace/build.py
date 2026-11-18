"""Build the internal GTM workspace into workspace/dist/.

Static HTML/CSS/JS, no framework, no network calls. Data comes only from chase.gtm.api and chase.query (read-only).

Privacy guards (public data only):
- demo=False everywhere (never the synthetic bring-your-own-data set)
- keys that can carry names of individuals or private CRM data are dropped before anything is written
- triggers with private_source == True are dropped, including their text inside the queue's why_now summary
- nothing under data/private/ is read here

Theme: colours and fonts are CSS variables in static/style.css (a neutral default). An optional, gitignored
config/theme.local.json overrides them at build time (format: config/theme.example.json). --neutral ignores it.

Run: .venv/bin/python workspace/build.py [--neutral]   (or: make workspace)
"""
from __future__ import annotations

import html
import json
import os
import re
import shutil
import sys
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

import markdown as md  # noqa: E402
import yaml  # noqa: E402

from chase import query as q  # noqa: E402
from chase.gtm import api  # noqa: E402

DIST = ROOT / "workspace" / "dist"
DISCLAIMER = "Independent project by Moritz Hanbuch."
NOINDEX = '<meta name="robots" content="noindex">'
# keys that may carry names of individuals or private/CRM data: never written to dist
DROP_KEYS = {"who_named", "who_source", "people_private", "byod_flags", "byod_mode", "warm_via", "peer_on_network",
             "in_pipeline_stage", "status", "in_pipeline"}
PLAY_LABEL = {"cold_email": "Cold email", "dinner_invite": "Dinner invite", "warm_intro": "Warm intro",
              "supplier_activation": "Supplier activation", "linkedin_note": "LinkedIn note"}
E = html.escape
THEME_LOCAL = ROOT / "config" / "theme.local.json"
THEME_ON = False   # set in main(): link assets/theme.css only when a local override was written
# variables a theme may set (everything else in the file is ignored); values may not break out of the declaration
THEME_VARS = {"bg", "fg", "muted", "line", "card", "accent", "rep", "rep-bg", "prx", "prx-bg", "est", "est-bg", "flag", "flag-bg",
              "t1", "t2", "t3", "tier-fg", "chip", "font", "font-mono", "radius"}
_UNSAFE = re.compile(r"[;{}<>\\]|url\(|@|/\*|\*/|expression", re.I)


# ---------------------------------------------------------------- helpers
def scrub(o):
    if isinstance(o, dict):
        return {k: scrub(v) for k, v in o.items() if k not in DROP_KEYS}
    if isinstance(o, list):
        return [scrub(x) for x in o]
    return o


def dump(path: Path, obj) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(scrub(obj), ensure_ascii=False, indent=1, default=str))


def link(url, text="source") -> str:
    if not url or not isinstance(url, str) or not url.startswith("http"):
        return '<span class="muted">no source link</span>'
    return f'<a href="{E(url)}" target="_blank" rel="noopener">{E(text)}</a>'


def num(v, d=0, suffix="") -> str:
    if v is None:
        return '<span class="muted">n/a</span>'
    try:
        return f"{float(v):,.{d}f}{suffix}"
    except (TypeError, ValueError):
        return E(str(v))


def money(v, cur) -> str:
    if v is None:
        return "n/a"
    v = float(v)
    s = f"{v/1e9:,.1f}bn" if abs(v) >= 1e9 else f"{v/1e6:,.1f}m" if abs(v) >= 1e6 else f"{v:,.0f}"
    return f"{E(str(cur or ''))} {s}".strip()


def pct(v) -> str:
    """Values in the data are already percentages (0-100) except shares named *_share (0-1)."""
    return num(v, 0, "%")


def page(title: str, body: str, depth: int = 0, active: str = "") -> str:
    up = "../" * depth
    nav = [("index.html", "Queue", "queue"), ("dinners.html", "Dinner builder", "dinners"),
           ("triggers.html", "Trigger feed", "triggers"), ("method.html", "Method", "method")]
    navh = "".join(f'<a href="{up}{h}"{" aria-current=page" if k == active else ""}>{t}</a>' for h, t, k in nav)
    return f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
{NOINDEX}
<title>{E(title)} | Chase Index workspace</title>
<link rel="stylesheet" href="{up}assets/style.css">{f'<link rel="stylesheet" href="{up}assets/theme.css">' if THEME_ON else ''}</head>
<body><header class="top"><div class="wrap"><a class="brand" href="{up}index.html">Chase Index <span>workspace</span></a>
<nav>{navh}</nav></div></header>
<main class="wrap">{body}</main>
<footer class="wrap foot"><p>{DISCLAIMER}</p>
<p class="muted">Internal GTM workspace built {date.today().isoformat()} from public data only. Contains internal scoring: do not publish.
Reported = statutory filings. Computed proxy = derived from financial statements. Estimate = model output with stated assumptions.</p></footer>
<script src="{up}assets/app.js"></script></body></html>"""


def tier_badge(t) -> str:
    return f'<span class="tier t{E(str(t))}">T{E(str(t))}</span>' if t is not None else ""


# ---------------------------------------------------------------- theme
def theme_css(cfg: dict) -> str:
    """CSS for a theme override: {"light": {var: value}, "dark": {var: value}}. Unknown variables and unsafe values are dropped."""
    def block(d):
        out = []
        for k, v in (d or {}).items():
            k = str(k).lstrip("-")
            if k in THEME_VARS and isinstance(v, str) and v.strip() and not _UNSAFE.search(v):
                out.append(f"--{k}:{v.strip()}")
        return ";".join(out)
    light, dark = block(cfg.get("light")), block(cfg.get("dark"))
    css = f":root{{{light}}}\n" if light else ""
    if dark:
        css += f"@media (prefers-color-scheme:dark){{:root{{{dark}}}}}\n"
    return css


# ---------------------------------------------------------------- sparkline (reported days to pay over the available reports)
_UK_HIST = None


def _uk_history():
    global _UK_HIST
    if _UK_HIST is None:
        import pandas as pd
        r = pd.read_parquet(ROOT / "data" / "processed" / "uk_payment_practices.parquet",
                            columns=["company_number", "period_end", "avg_days_to_pay", "value_paid_total_gbp", "is_usable", "superseded_by_report_id"])
        r = r[r.is_usable.fillna(False) & r.superseded_by_report_id.isna() & r.avg_days_to_pay.between(0, 365)]
        m = pd.read_parquet(ROOT / "data" / "processed" / "uk_entity_group_map.parquet", columns=["company_number", "company_id"])
        r = r.merge(m, on="company_number")
        pe = pd.to_datetime(r.period_end)
        r["half"] = pe.dt.year.astype(str) + "-H" + (1 + (pe.dt.month > 6)).astype(str)
        _UK_HIST = r
    return _UK_HIST


def days_series(company_id: str, kind: str) -> tuple[list[tuple[str, float]], str, int | None]:
    """[(period label, days)], what the points are, benchmark line. Reported figures only; a computed proxy gets no series."""
    if kind == "uk_reported":
        h = _uk_history()
        h = h[h.company_id == company_id]
        pts = []
        for half, g in sorted(h.groupby("half")):
            w = g.value_paid_total_gbp
            v = float((g.avg_days_to_pay * w).sum() / w.sum()) if w.notna().all() and w.sum() > 0 else float(g.avg_days_to_pay.mean())
            pts.append((half, v))
        n = h.company_number.nunique()
        what = ("UK reports per half-year" + (f", invoice-value weighted across up to {n} UK entities" if n > 1 else ", single UK entity")
                + ". The headline uses each entity's latest report, so the last point can differ.")
        return pts[-8:], what, 32
    if kind == "es_reported":
        es = q.get_payment_profile(company_id).get("reported", {}).get("spain") or {}
        fy = es.get("fiscal_year")
        pts = [(f"FY{int(fy) - 1}", es["prior_year_pmp_days"])] if fy and es.get("prior_year_pmp_days") is not None else []
        if es.get("pmp_days") is not None:
            pts.append((f"FY{fy}", es["pmp_days"]))
        return pts, "Spanish PMP by fiscal year (statutory)", 60
    return [], "", None


def sparkline(pts: list[tuple[str, float]], what: str, bench: int | None, w: int = 64, h: int = 18) -> str:
    if len(pts) < 2:
        one = f"{pts[0][1]:.0f}d only" if pts else "no reported series"
        return f'<span class="spark none" title="{E(what or "Computed proxy: no reported series")}">{E(one if pts else "no series")}</span>'
    vals = [v for _, v in pts]
    lo, hi = min(vals + ([bench] if bench else [])), max(vals + ([bench] if bench else []))
    span = (hi - lo) or 1
    x = lambda i: 2 + i * (w - 4) / (len(pts) - 1)
    y = lambda v: h - 2 - (v - lo) * (h - 4) / span
    line = " ".join(f"{x(i):.1f},{y(v):.1f}" for i, v in enumerate(vals))
    ref = (f'<line class="bench" x1="0" x2="{w}" y1="{y(bench):.1f}" y2="{y(bench):.1f}"/>' if bench else "")
    label = "; ".join(f"{p} {v:.0f}d" for p, v in pts)
    tip = f"{what} {label}." + (f" Dashed line: {bench} days." if bench else "")
    return (f'<svg class="spark" width="{w}" height="{h}" viewBox="0 0 {w} {h}" role="img" aria-label="{E(tip)}"><title>{E(tip)}</title>{ref}'
            f'<polyline points="{line}"/><circle cx="{x(len(vals) - 1):.1f}" cy="{y(vals[-1]):.1f}" r="2"/></svg>')


# ---------------------------------------------------------------- data
def load():
    all_t = api.get_triggers(since="1900-01-01", limit=1_000_000)
    private = {(t["company_id"], t["text"]) for t in all_t["triggers"] if t.get("private_source") is True}
    public = [t for t in all_t["triggers"] if t.get("private_source") is not True]
    queue = api.weekly_queue(limit=25, demo=False)
    for a in queue["accounts"]:
        segs = [s for s in (a.get("why_now") or "").split(" | ") if s and (a["company_id"], s) not in private]
        a["why_now"] = " | ".join(segs) or "No public dated trigger this week: standing evidence only"
        pub_types = {t["trigger_type"] for t in public if t["company_id"] == a["company_id"]}
        a["why_now_types"] = "|".join(x for x in (a.get("why_now_types") or "").split("|") if x and x in pub_types)
    top = q.top_targets(limit=100)
    return all_t, private, public, queue, top


# ---------------------------------------------------------------- pages
ROW_TAG = {"einvoicing_mandate": "e-inv. deadline", "einvoicing_mandate_suppliers": "e-inv. suppliers",
           "einvoicing_started": "e-invoicing", "sf_disclosed": "SCF note", "terms_changed_other": "terms changed",
           "filing_crossed_60": "over 60d", "filing_worsened": "slower", "es_pmp_rose": "ES slower", "dinner_city": "dinner",
           "results_date": "results", "scf_started": "SCF new", "cfo_change": "new CFO", "terms_changed_longer": "terms longer",
           "terms_changed_shorter": "terms shorter"}


ROLE_SHORT = {"Head of accounts payable or shared services": "Head of AP / shared services",
              "Group treasurer or CFO office": "Treasurer / CFO office", "CFO office": "CFO office"}


def key_number(company_id: str) -> tuple[str, str, str, str]:
    """Compact key number for the queue row: ('79d', 'vs 32 UK median', css class, evidence kind). The same figure the opener uses."""
    hv = q.hook_variables(q._row(company_id))
    days, kind = hv.get("days"), hv.get("evidence_kind")
    if not days:
        return "n/a", "", "prx", ""
    if kind == "uk_reported":
        return f"{days}d", "vs 32 UK median", "rep", kind
    if kind == "es_reported":
        return f"{days}d", "vs 60 legal max (ES)", "rep", kind
    med = str(hv.get("benchmark") or "").split(" ")[0]
    return f"{days}d", f"vs {med} sector median, DPO proxy", "prx", kind or "proxy"


STATUS_OPTS = (("todo", "To do"), ("contacted", "Contacted"), ("meeting", "Meeting"), ("not_now", "Not now"))


def summary_strip(queue: dict, keys: dict) -> str:
    acc = queue["accounts"]
    tiers = {t: sum(1 for a in acc if str(a.get("tier")) == t) for t in ("1", "2", "3")}
    rep = sum(1 for a in acc if keys[a["company_id"]][2] == "rep")
    live = sum(1 for a in acc if (a.get("triggers_live_n") or 0) > 0)
    dinner = sum(1 for a in acc if a.get("play") == "dinner_invite")
    pl = lambda n, one, many: f"<b>{n}</b> {one if n == 1 else many}"
    bits = [pl(len(acc), "account", "accounts"), " · ".join(f"<b>{n}</b> T{t}" for t, n in tiers.items() if n),
            " · ".join(x for x in (f"<b>{rep}</b> reported" if rep else "", f"<b>{len(acc) - rep}</b> proxy" if len(acc) - rep else "") if x),
            pl(live, "with a live trigger", "with a live trigger"), pl(dinner, "dinner invite", "dinner invites")]
    return ('<div class="strip" aria-label="Queue summary">' + "".join(f"<span>{b}</span>" for b in bits)
            + '<span class="st-counts" aria-live="polite"></span></div>')


def build_queue(queue: dict, types: dict) -> str:
    rows, countries, plays = [], set(), set()
    keys = {a["company_id"]: key_number(a["company_id"]) for a in queue["accounts"]}
    for a in queue["accounts"]:
        cid = a["company_id"]
        countries.add(a.get("country") or "")
        plays.add(a.get("play") or "")
        tt = [x for x in (a.get("why_now_types") or "").split("|") if x]
        tags = "".join(f'<span class="chip" title="{E(types.get(x, x))}">{E(ROW_TAG.get(x, short_label(x)))}</span>' for x in tt[:2])
        more = f'<span class="chip more" title="{len(tt) - 2} more in the details">+{len(tt) - 2}</span>' if len(tt) > 2 else ""
        kn, kvs, kcls, kind = keys[cid]
        spark = sparkline(*days_series(cid, kind))
        status_sel = (f'<select class="status" data-cid="{E(cid)}" data-company="{E(a["company"])}" data-play="{E(a.get("play") or "")}" '
                      f'aria-label="Status for {E(a["company"])}">' + "".join(f'<option value="{k}">{v}</option>' for k, v in STATUS_OPTS) + "</select>")
        role = a.get("who_role") or "n/a"
        thin = '<span class="flag" title="UK invoice value under 1% of group revenue">thin</span>' if a.get("thin_evidence") else ""
        why = "".join(f"<li>{E(x)}</li>" for x in a["why_now"].split(" | "))
        all_tags = "".join(f'<span class="chip" title="{E(types.get(x, x))}">{E(short_label(x))}</span>' for x in tt) or '<span class="muted">none</span>'
        one_pager = (f' · <a href="one_pagers/{E(cid)}.html">one-pager</a>' if a.get("one_pager") else "")
        rows.append(f"""<details class="qrow" data-status="todo" data-country="{E(a.get('country') or '')}" data-play="{E(a.get('play') or '')}" data-tier="{E(str(a.get('tier')))}">
<summary>
<span class="c-rank">{a['queue_rank']}</span>
<span class="c-co"><strong>{E(a['company'])}</strong> {tier_badge(a.get('tier'))}{thin}<span class="c-cc">{E(a.get('country') or '')}</span></span>
<span class="c-play play-{E(a.get('play') or '')}">{E(PLAY_LABEL.get(a.get('play'), a.get('play') or ''))}</span>
<span class="c-who" title="{E(role)}">{E(ROLE_SHORT.get(role, role))}</span>
<span class="c-key {kcls}" title="{E(kn + ' ' + kvs)}"><b>{E(kn)}</b> <span>{E(kvs)}</span></span>
<span class="c-spark {kcls}">{spark}</span>
<span class="c-tags">{tags}{more}</span>
<span class="c-status">{status_sel}</span>
</summary>
<div class="qdetail">
<div class="qd-main">
<h3>Evidence</h3>
<p><span class="lbl {'rep' if kcls == 'rep' else 'prx'}">{'Reported' if kcls == 'rep' else 'Computed proxy'}</span> {E(a.get('evidence') or '')} {link(a.get('evidence_url'))}</p>
<h3>Why now</h3>
<ul class="why">{why}</ul>
<p class="small">{link(a.get('why_now_url'), 'trigger source') if a.get('why_now_url') else '<span class="muted">no dated public trigger source</span>'} · {a.get('triggers_live_n') or 0} live events</p>
<div class="chips">{all_tags}</div>
<h3>Opener <span class="muted small">draft, edit before sending</span></h3>
<blockquote class="opener">{E(a.get('opener_draft') or '')}</blockquote>
<button type="button" class="copy" data-copy="{E(a.get('opener_draft') or '')}">Copy opener</button>
</div>
<dl class="qd-side">
<dt>Ask for</dt><dd>{E(role)}<div class="small muted">{E(a.get('who_role_reason') or '')}</div></dd>
<dt>Play</dt><dd>{E(PLAY_LABEL.get(a.get('play'), a.get('play') or ''))}</dd>
<dt>Priority</dt><dd>{num(a.get('queue_priority'), 1)} <span class="small muted">({E(a.get('priority_explained') or '')})</span></dd>
<dt>Account</dt><dd>{E(a.get('country') or '')} · {E((a.get('sector') or '').replace('_', ' '))} · index rank {E(str(a.get('index_rank') or ''))}</dd>
<dt>Links</dt><dd><a href="accounts/{E(cid)}.html">account page</a>{one_pager}</dd>
</dl>
</div>
</details>""")
    sel = lambda name, vals, lab: (f'<label>{lab} <select data-filter="{name}"><option value="">All</option>'
                                   + "".join(f'<option value="{E(v)}">{E(PLAY_LABEL.get(v, v))}</option>' for v in sorted(vals) if v)
                                   + "</select></label>")
    body = f"""<div class="qbar"><h1>Queue <span class="muted">week {E(queue['week'])}</span></h1>
<span class="muted small">{queue['count']} of {queue['eligible_accounts']} eligible</span>
<div class="filters" data-target="#queue">{sel('country', countries, 'Country')}{sel('play', plays, 'Play')}{sel('tier', {'1', '2', '3'}, 'Tier')}
<label>Status <select data-filter="status"><option value="">All</option>{''.join(f'<option value="{k}">{v}</option>' for k, v in STATUS_OPTS)}</select></label>
<button type="button" data-toggle-all="#queue">Expand all</button><button type="button" id="export-status" title="Download a CSV in the config/status/ format">Export status CSV</button>
<button type="button" class="kbd-btn" data-help aria-label="Keyboard shortcuts" title="Keyboard shortcuts (?)">?</button><span class="count muted" aria-live="polite"></span></div></div>
{summary_strip(queue, keys)}
<div class="qhead" aria-hidden="true"><span>#</span><span>Account</span><span>Play</span><span>Ask for</span><span>Key number</span><span>Trend</span><span>Why now</span><span>Status</span></div>
<div id="queue" class="qlist">{''.join(rows)}</div>
<div id="kbd-help" class="kbd-help" role="dialog" aria-label="Keyboard shortcuts" hidden>
<h2>Keyboard</h2><dl><dt><kbd>j</kbd> <kbd>k</kbd></dt><dd>next / previous account</dd><dt><kbd>Enter</kbd></dt><dd>expand or collapse</dd>
<dt><kbd>c</kbd></dt><dd>copy the opener</dd><dt><kbd>?</kbd></dt><dd>show or hide this</dd><dt><kbd>Esc</kbd></dt><dd>close</dd></dl></div>
<div id="toast" class="toast" role="status" aria-live="polite" hidden></div>
<p class="small muted">Status lives in this browser only (localStorage). Export it, then save the file as <code>config/status/accounts_status.csv</code>
(or append its rows) so <code>make queue</code> and <code>make feedback</code> read it. "Not now" exports as <code>not_a_fit</code> with the reason "not now".
Trend: reported days to pay over the available reports, dashed line = benchmark.</p>
<p class="small muted">Drafts only: a person edits and sends every message. {E(queue['note'].replace(' who_named is present only when local private data exists.', ''))}</p>"""
    return page("Queue", body, 0, "queue")


def section(title: str, inner: str) -> str:
    return f'<section class="card"><h2>{E(title)}</h2>{inner}</section>'


def build_account(w: dict, public_keys: set, in_queue: bool) -> str:
    b = w["brief"]
    cid = b["company_id"]
    s = b["scores"]
    pp = b.get("payment_profile") or {}
    rep = pp.get("reported") or {}
    parts = []

    # header
    rev = b.get("revenue") or {}
    head = f"""<p class="crumbs"><a href="../index.html">Queue</a> / {E(b['name'])}</p>
<h1>{E(b['name'])} {tier_badge(b.get('priority_tier'))}</h1>
<p class="muted">{E(b.get('country') or '')} · {E(b.get('hq_city') or 'HQ city unknown')} · {E(b.get('sector') or '')} · index rank {b.get('rank')}
· revenue {money(rev.get('amount'), rev.get('currency'))} ({E(str(rev.get('period_end') or ''))}, {link(rev.get('source_url'))}){' · <span class="flag">thin evidence</span>' if b.get('thin_evidence') else ''}</p>
<p class="lede">{E(b.get('rationale') or '')} <span class="small muted">({E(b.get('rationale_method') or '')})</span></p>"""
    if b.get("one_pager"):
        head += f'<p><a class="btn" href="../one_pagers/{E(cid)}.html">Open the one-pager</a></p>'
    parts.append(head)

    # next best action
    nba = w.get("next_best_action") or {}
    if "play" in nba:
        parts.append(section("Next best action", f"""<p><span class="play">{E(PLAY_LABEL.get(nba['play'], nba['play']))}</span>
queue rank {nba.get('queue_rank')} · priority {num(nba.get('queue_priority'), 1)} ({E(nba.get('priority_explained') or '')})</p>
<p><strong>Who:</strong> {E(nba.get('who_role') or 'n/a')}. <span class="muted">{E(nba.get('who_role_reason') or '')}</span></p>
<p><strong>Draft opener</strong> <span class="muted small">(template with data slots, a human edits and sends)</span></p>
<blockquote>{E(nba.get('opener_draft') or '')}</blockquote>"""))
    else:
        parts.append(section("Next best action", f"<p class='muted'>{E(nba.get('note') or 'not in the queue')}</p>"))

    # evidence
    ev = []
    uk = rep.get("uk")
    if uk:
        ents = "".join(f"""<tr><td>{E(e['name'] or '')} <span class="muted small">{E(e.get('company_number') or '')}</span></td>
<td class="num">{num(e.get('avg_days_to_pay'))}</td><td class="num">{pct(e.get('pct_paid_late')) if e.get('pct_paid_late') is not None else '<span class="muted" title="' + E(e.get('pct_paid_late_note') or '') + '">n/s</span>'}</td>
<td class="num">{pct(e.get('pct_paid_over_60'))}</td><td class="num">{num(e.get('trend_days_yoy'), 0) if e.get('trend_days_yoy') is not None else '<span class="muted">n/a</span>'}</td>
<td class="small">{E(str(e.get('period_start')))} to {E(str(e.get('period_end')))}</td><td>{link(e.get('source_url'))}</td></tr>""" for e in uk.get("entities", []))
        ev.append(f"""<h3><span class="lbl rep">Reported</span> UK statutory payment reports</h3>
<p class="small muted">{E(uk['what'])}</p>
<p>Average days to pay across {uk['entities_n']} UK entities: <strong>{num(uk.get('avg_days_to_pay_mean_of_entities'))} days</strong> ({E(str(uk.get('aggregation') or ''))}).
Share paid late: {pct(uk.get('pct_invoices_paid_late_mean'))}. Over 60 days: {pct(uk.get('pct_invoices_paid_over_60_days_mean'))}.
Trend vs a year earlier: {num(uk.get('trend_days_year_on_year_mean'), 1)} days. Period {E(str((uk.get('period') or {}).get('start')))} to {E(str((uk.get('period') or {}).get('end')))}.
Slowest entity: {E(str((uk.get('slowest_entity') or {}).get('name')))}, {num((uk.get('slowest_entity') or {}).get('avg_days_to_pay'))} days ({link((uk.get('slowest_entity') or {}).get('source_url'))}).</p>
<div class="tablewrap"><table class="data small"><thead><tr><th>UK entity</th><th>Days</th><th>Late</th><th>&gt;60d</th><th>YoY</th><th>Period</th><th>Source</th></tr></thead><tbody>{ents}</tbody></table></div>
<p class="small muted">Entity match confidence (min): {num(uk.get('entity_match_confidence_min'), 2)}, methods: {E(str(uk.get('entity_match_methods') or ''))}.</p>""")
    es = rep.get("spain")
    if es:
        ev.append(f"""<h3><span class="lbl rep">Reported</span> Spain average supplier payment period (PMP)</h3>
<p class="small muted">{E(es['what'])}</p>
<p>PMP FY{E(str(es.get('fiscal_year')))}: <strong>{num(es.get('pmp_days'), 1)} days</strong> (prior year {num(es.get('prior_year_pmp_days'), 1)}; legal maximum 60).
Scope: {E(str(es.get('scope') or 'n/a'))}. Paid within legal maximum by value: {pct(es.get('pct_paid_within_legal_max_by_value'))}. {link(es.get('source_url'))}
<span class="small muted">Extraction confidence {num(es.get('extraction_confidence'), 2)}.</span></p>""")
    cp = pp.get("computed_proxy")
    if cp:
        ev.append(f"""<h3><span class="lbl prx">Computed proxy</span> DPO from XBRL statements</h3>
<p class="small muted">{E(cp['what'])}</p>
<p>DPO FY{E(str(cp.get('fiscal_year')))}: <strong>{num(cp.get('dpo_days'))} days</strong> (prior year {num(cp.get('prior_year_dpo_days'))}; sector median {num(cp.get('sector_median_dpo_days'))}).
Payables basis: {E(str(cp.get('payables_basis') or ''))}, cost basis: {E(str(cp.get('cost_basis') or ''))}, flag: {E(str(cp.get('flag') or ''))}. {link(cp.get('source_url'))}</p>""")
    parts.append(section("Payment evidence", "".join(ev) or "<p class='muted'>No payment evidence in the dataset.</p>"))

    # scores
    def parts_tbl(d):
        return "".join(f"<tr><td>{E(k)}</td><td class='num'>{num(v, 1)}</td></tr>" for k, v in (d or {}).items())
    parts.append(section("Scores and how they were built", f"""<div class="scores">
<div><span class="big">{num(s.get('fit'))}</span>Fit</div><div><span class="big">{num(s.get('pain'))}</span>Pain</div>
<div><span class="big">{num(s.get('signal'))}</span>Signal</div><div><span class="big">{num(s.get('priority'))}</span>Priority</div></div>
<p class="small muted">{E(s.get('method') or '')}. Pain basis: {E(str(s.get('pain_basis')))} (evidence tier {E(str(s.get('pain_evidence_tier')))}: 1 = reported, 2 = computed proxy).
Full formula on the <a href="../method.html#scores">method page</a>.</p>
<div class="two"><table class="data small"><thead><tr><th>Fit component</th><th>Points</th></tr></thead><tbody>{parts_tbl(s.get('fit_parts'))}</tbody></table>
<table class="data small"><thead><tr><th>Pain component</th><th>Points</th></tr></thead><tbody>{parts_tbl(s.get('pain_parts'))}</tbody></table></div>"""))

    # triggers
    live = [t for t in w.get("triggers", []) if (cid, t["text"]) in public_keys]
    live.sort(key=lambda t: str(t.get("trigger_date")), reverse=True)
    trows = "".join(f"""<tr><td class="small">{E(str(t.get('trigger_date')))}</td><td><span class="chip" title="{E(t['trigger_type'])}">{E(short_label(t['trigger_type']))}</span>{' <span class="flag">live</span>' if t.get('is_live') else ''}</td>
<td class="small">{E(t['text'])}</td><td>{link(t.get('evidence_url'))}</td></tr>""" for t in live)
    sig = "".join(f"<li>{E(x.get('text') or '')} {link(x.get('url'))}</li>" for x in b.get("why_now_signals") or [])
    parts.append(section("Triggers and why-now signals", (f"""<div class="tablewrap"><table class="data"><thead><tr><th>Date</th><th>Type</th><th>What</th><th>Source</th></tr></thead>
<tbody>{trows}</tbody></table></div>""" if trows else "<p class='muted'>No public triggers.</p>") + (f"<h3>Standing signals</h3><ul>{sig}</ul>" if sig else "")))

    # supplier finance + uk filing features
    sf = b.get("supplier_finance")
    if sf:
        if sf.get("programme_disclosed"):
            conf = "confirmed by two readers" if sf.get("confirmed") else "unconfirmed: one reader only, not scored"
            sfh = f"""<p><span class="lbl rep">Reported</span> Supplier finance programme disclosed ({E(conf)}). Outstanding:
{money(sf.get('obligations_outstanding'), sf.get('currency'))} (prior year {money(sf.get('prior_year'), sf.get('currency'))}), period end {E(str(sf.get('period_end')))}. {link(sf.get('source_url'))}</p>
<p class="small">Terms with programme: {E(str(sf.get('terms_with_programme') or 'n/a'))}. Without: {E(str(sf.get('terms_without_programme') or 'n/a'))}.</p>
{('<blockquote class="small">' + E(sf['quote']) + '</blockquote>') if sf.get('quote') else ''}
<p class="small muted">Extraction: {E(str(sf.get('extraction_method') or ''))}, confidence {num(sf.get('confidence'), 2)}.</p>"""
        else:
            sfh = f"<p>No supplier finance programme found in the annual report ({E(str(sf.get('resolution') or ''))}). {link(sf.get('source_url'))}</p>"
        parts.append(section("Supplier finance disclosure", sfh))
    uf = b.get("uk_filing_features")
    if uf:
        share = uf.get("einvoicing_offered_share")
        parts.append(section("UK filing features", f"""<p class="small muted">From the same statutory UK filings, rolled up over {uf['uk_entities_n']} entities, period end {E(str(uf.get('period_end')))}.</p>
<table class="data small"><tbody>
<tr><td>Late payments caused by disputes</td><td class="num">{pct(uf.get('late_because_of_dispute_pct'))}</td><td>{E(str(uf.get('late_because_of_dispute_method') or ''))} {link(uf.get('late_because_of_dispute_url'))}</td></tr>
<tr><td>Entities that made terms longer</td><td class="num">{uf.get('terms_changed_longer_n')}</td><td>{link(uf.get('terms_changed_longer_url')) if uf.get('terms_changed_longer_url') else ''}</td></tr>
<tr><td>Entities offering supply chain finance</td><td class="num">{uf.get('scf_offered_n')}</td><td>{'newly started' if uf.get('scf_started') else ''}</td></tr>
<tr><td>Share of entities offering e-invoicing</td><td class="num">{pct(share * 100) if share is not None else 'n/a'}</td><td>{'newly started' if uf.get('einvoicing_started') else ''}</td></tr>
<tr><td>Payment codes</td><td colspan="2">{E(str(uf.get('payment_codes') or 'none stated'))}{' · pay to stay reported' if uf.get('pay_to_stay') else ''}</td></tr>
</tbody></table>"""))

    # estimates
    est = b.get("estimates") or {}
    eh = []
    for key, lab in (("uk_scope", "UK scope"), ("group_proxy", "Group (proxy)")):
        x = est.get(key)
        if not x:
            continue
        o = x.get("early_payment_discount_opportunity") or {}
        cur = x.get("currency")
        eh.append(f"""<h3>{lab}</h3><p class="small muted">{E(x['basis'])}</p>
<p>Early-payment discount opportunity per year: <strong>{money(o.get('low'), cur)} to {money(o.get('high'), cur)}</strong> (base {money(o.get('base'), cur)}).
Supplier cash held beyond 30 days: {money(x.get('supplier_cash_beyond_30_days'), cur)}. Days used: {num(x.get('days_used'), 1)}.</p>""")
    if est.get("uk_scope_note"):
        eh.append(f"<p class='small'>{E(est['uk_scope_note'])}</p>")
    a = est.get("assumptions") or {}
    sc = a.get("scenarios") or {}
    sct = " · ".join(f"{k}: {v.get('share_eligible', 0)*100:.0f}% eligible at {v.get('annualised_rate', 0)*100:.0f}% APR" for k, v in sc.items())
    parts.append(f"""<section class="card est"><h2><span class="lbl est">Estimate</span> Opportunity range</h2>
{''.join(eh) or "<p class='muted'>No estimate for this account.</p>"}
<p class="small">Formula: {E(a.get('formula') or '')}. Scenarios: {E(sct)}. Early pay on day {E(str(a.get('early_pay_day')))}, at most {E(str(a.get('max_days_accelerated')))} days accelerated.
Assumptions in {E(a.get('config_file') or '')}.</p><p class="small muted">{E(est.get('whose_money') or '')}</p></section>""")

    if not in_queue:
        parts.append('<p class="small muted">This account is in the top 100 but not in this week\'s queue.</p>')
    return page(b["name"], "".join(parts), 1)


def build_dinners(dinners: list[dict]) -> str:
    blocks = []
    for d in dinners:
        if not d.get("found"):
            continue
        rows = "".join(f"""<tr data-row data-company="{E(a['company'])}" data-hook="{E(a['hook'])}" data-source="{E(a.get('source_url') or '')}"
data-tier="{a['tier']}" data-hq="{E(a.get('hq_city') or '')}" data-local="{E(a['local_link'])}">
<td><input type="checkbox" checked aria-label="Include {E(a['company'])}"></td>
<td><a href="accounts/{E(a['company_id'])}.html"><strong>{E(a['company'])}</strong></a> {tier_badge(a['tier'])}
<div class="small muted">{E(a.get('hq_city') or 'HQ city unknown')} · {'HQ in city area' if a['local_link'] == 'hq_in_city_area' else 'HQ elsewhere in country'}</div></td>
<td class="small"><span class="lbl rep">Reported</span> {E(a['hook'])} {link(a.get('source_url'))}</td></tr>""" for a in d["invite"])
        bench = "".join(f"<li>{E(x['name'])}: {E(x['bench_reason'])}. {E(x.get('figure') or '')} {link(x.get('source_url'))}</li>"
                        for x in d.get("bench_to_verify") or [])
        when = d.get("date") or "next dinner"
        blocks.append(f"""<section class="card dinner" data-city="{E(d['city'])}" data-date="{E(str(d.get('date') or ''))}">
<h2>{E(d['city'].title())} <span class="muted">{E(str(when))}</span></h2>
<div class="actions"><button data-act="all">Select all</button><button data-act="none">Clear</button>
<button data-act="csv">Copy as CSV</button><button data-act="text">Copy as text</button><span class="count muted" aria-live="polite"></span></div>
{('<div class="tablewrap"><table class="data"><thead><tr><th></th><th>Account</th><th>Hook (template variable)</th></tr></thead><tbody>' + rows + '</tbody></table></div>') if rows else "<p class='muted'>No account with a strong enough hook.</p>"}
{('<details><summary>Bench: verify before use (' + str(len(d.get("bench_to_verify") or [])) + ')</summary><ul class="small">' + bench + '</ul></details>') if bench else ''}
</section>""")
    body = f"""<h1>Dinner builder</h1>
<p class="lede">Shortlists per dinner city from <code>config/dinners.yaml</code> (dates, if any, from the local <code>config/dinners.local.yaml</code>). Tick the accounts you want, then copy. Hooks are data slots for a
human-written invite, not the invite itself. A country list: check where the finance leader actually sits. UK figures describe UK subsidiaries.</p>
{''.join(blocks)}"""
    return page("Dinner builder", body, 0, "dinners")


SHORT_LABELS = {
    "filing_crossed_60": "crossed 60 days", "filing_worsened": "paying slower", "es_pmp_rose": "Spain: slower",
    "terms_changed_longer": "terms longer", "terms_changed_other": "terms changed", "terms_changed_shorter": "terms shorter",
    "scf_started": "SCF started", "einvoicing_started": "e-invoicing started", "cfo_change": "new CFO",
    "results_date": "results due", "einvoicing_mandate": "e-invoicing deadline (buyer)",
    "einvoicing_mandate_suppliers": "e-invoicing deadline (suppliers)", "sf_disclosed": "supplier finance (context)",
    "dinner_city": "dinner"}


def short_label(code: str) -> str:
    return SHORT_LABELS.get(code, code.replace("_", " "))


def build_triggers(trigs: list[dict], types: dict) -> str:
    rows = []
    for t in trigs:
        tt = t["trigger_type"]
        binds = ("binds the buyer" if tt == "einvoicing_mandate" else "binds its small suppliers" if tt == "einvoicing_mandate_suppliers" else "")
        approx = t.get("date_is_approximate")
        approx_h = ('<span class="flag" title="Date is approximate">approx.</span>' if approx is True else
                    "" if approx is False else '<span class="muted small" title="date_is_approximate not exposed by the API">?</span>')
        acct = (f'<a href="accounts/{E(t["company_id"])}.html">{E(t["company"])}</a>' if t["company_id"] in ACCOUNT_IDS else E(t["company"]))
        rows.append(f"""<tr data-type="{E(tt)}"><td class="small nowrap">{E(str(t.get('trigger_date')))} {approx_h}</td><td>{acct}</td>
<td><span class="chip" title="{E(tt)}">{E(short_label(tt))}</span>{('<div class="small"><strong>' + binds + '</strong></div>') if binds else ''}</td>
<td class="small">{E(t['text'])}</td><td>{link(t.get('evidence_url'))}</td></tr>""")
    opts = "".join(f'<option value="{E(k)}">{E(v)}</option>' for k, v in types.items() if any(t["trigger_type"] == k for t in trigs))
    body = f"""<h1>Trigger feed</h1>
<p class="lede">{len(trigs)} live public triggers, newest first. Each links to its source. E-invoicing mandates are split: some bind the buyer itself,
others bind the buyer's small suppliers (a supplier-onboarding angle).</p>
<div class="filters" data-target="#trig"><label>Type <select data-filter="type"><option value="">All</option>{opts}</select></label><span class="count muted" aria-live="polite"></span></div>
<div class="tablewrap"><table id="trig" class="data"><thead><tr><th>Date</th><th>Account</th><th>Type</th><th>What</th><th>Source</th></tr></thead>
<tbody>{''.join(rows)}</tbody></table></div>
<p class="small muted">"approx." marks dates that are approximate (for example a results date inferred from last year). Triggers from private sources are left out.</p>"""
    return page("Trigger feed", body, 0, "triggers")


def build_method() -> str:
    text = (ROOT / "docs" / "methodology.md").read_text()
    h = md.markdown(text, extensions=["tables", "fenced_code", "sane_lists", "toc"])
    h = h.replace(chr(0x2014), ", ").replace(chr(0x2013), "-")  # no em or en dashes in rendered copy
    body = f"""<h1>Method</h1>
<section class="card"><h2>Three kinds of number</h2>
<dl class="kinds">
<dt><span class="lbl rep">Reported</span></dt><dd>Taken from a statutory filing: UK payment practices reports (by UK legal entity), Spanish PMP notes in annual accounts, supplier finance notes in annual reports. Always shown with source link and period.</dd>
<dt><span class="lbl prx">Computed proxy</span></dt><dd>Calculated by us from XBRL financial statements: DPO = trade payables / cost of sales x 365. A balance-sheet proxy, not reported days to pay.</dd>
<dt><span class="lbl est">Estimate</span></dt><dd>Model output: supplier cash held beyond 30 days and an early-payment discount range (low / base / high). Assumptions live in <code>config/assumptions.yaml</code>. Never a single precise number.</dd>
</dl>
<p class="small">Scores (fit, pain, signal) are deterministic formulas with weights in <code>config/assumptions.yaml</code>. Tier 1 reported evidence always outranks a computed proxy.</p></section>
<section class="card md"><p class="small muted">Rendered from <code>docs/methodology.md</code> at build time.</p>{h}</section>"""
    return page("Method", body, 0, "method")


ACCOUNT_IDS: set[str] = set()


def copy_one_pager(cid: str) -> bool:
    src = ROOT / "outputs" / "one_pagers" / f"{cid}.html"
    if not src.exists():
        return False
    s = src.read_text()
    if "noindex" not in s:
        s = re.sub(r"(<head[^>]*>)", r"\1" + NOINDEX, s, count=1, flags=re.I)
    if DISCLAIMER not in s:
        s = s.replace("</body>", f"<p>{DISCLAIMER}</p></body>")
    out = DIST / "one_pagers" / f"{cid}.html"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(s)
    pdf = src.with_suffix(".pdf")
    if pdf.exists():
        shutil.copy2(pdf, out.with_suffix(".pdf"))
    return True


def main() -> None:
    global THEME_ON
    if DIST.exists():
        shutil.rmtree(DIST)
    (DIST / "assets").mkdir(parents=True)
    for f in ("style.css", "app.js"):
        shutil.copy2(ROOT / "workspace" / "static" / f, DIST / "assets" / f)
    neutral = "--neutral" in sys.argv or os.environ.get("CHASE_THEME") == "neutral"
    if THEME_LOCAL.exists() and not neutral:
        css = theme_css(json.loads(THEME_LOCAL.read_text()))
        if css:
            (DIST / "assets" / "theme.css").write_text(css)
            THEME_ON = True
    print("theme: " + ("local override (config/theme.local.json)" if THEME_ON else "neutral default"))

    all_t, private, public, queue, top = load()
    types = all_t["types"]
    public_keys = {(t["company_id"], t["text"]) for t in public}

    ids = list(dict.fromkeys([a["company_id"] for a in queue["accounts"]] + [t["company_id"] for t in top["targets"]]))
    queued = {a["company_id"] for a in queue["accounts"]}
    index = []
    for cid in ids:
        w = api.account_workspace(cid, demo=False)
        if not w.get("found", True) or "brief" not in w:
            continue
        w = scrub(w)
        w["triggers"] = [t for t in w.get("triggers", []) if (cid, t["text"]) in public_keys]
        if "why_now" in (w.get("next_best_action") or {}):
            w["next_best_action"]["why_now"] = " | ".join(x for x in w["next_best_action"]["why_now"].split(" | ") if (cid, x) not in private)
        ACCOUNT_IDS.add(cid)
        if w["brief"].get("one_pager") and copy_one_pager(cid):
            w["brief"]["one_pager"] = f"one_pagers/{cid}.html"
        else:
            w["brief"]["one_pager"] = None
        (DIST / "accounts").mkdir(exist_ok=True)
        (DIST / "accounts" / f"{cid}.html").write_text(build_account(w, public_keys, cid in queued))
        dump(DIST / "data" / "accounts" / f"{cid}.json", w)
        b = w["brief"]
        index.append({"company_id": cid, "name": b["name"], "country": b.get("country"), "tier": b.get("priority_tier"),
                      "rank": b.get("rank"), "in_queue": cid in queued, "one_pager": b["one_pager"]})

    cal = q.dinner_calendar()
    dinners = [api.dinner_builder(d["city"], demo=False) for d in cal]
    feed = [t for t in public if t.get("is_live")]
    today_s = date.today().isoformat()
    past = sorted([t for t in feed if str(t.get("trigger_date")) <= today_s], key=lambda t: (str(t.get("trigger_date")), t.get("strength") or 0), reverse=True)
    future = sorted([t for t in feed if str(t.get("trigger_date")) > today_s], key=lambda t: str(t.get("trigger_date")))
    feed = past + future

    (DIST / "index.html").write_text(build_queue(queue, types))
    (DIST / "dinners.html").write_text(build_dinners(dinners))
    (DIST / "triggers.html").write_text(build_triggers(feed, types))
    (DIST / "method.html").write_text(build_method())

    dump(DIST / "data" / "queue.json", queue)
    dump(DIST / "data" / "triggers.json", {"types": types, "count": len(feed), "triggers": feed, "disclaimer": DISCLAIMER})
    dump(DIST / "data" / "dinners.json", dinners)
    dump(DIST / "data" / "accounts.json", index)
    print(f"workspace: {len(index)} account pages, {len(queue['accounts'])} queued, {len(feed)} live public triggers, "
          f"{sum(1 for d in dinners if d.get('found'))} dinner cities, "
          f"{sum(1 for i in index if i['one_pager'])} one-pagers -> {DIST.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
