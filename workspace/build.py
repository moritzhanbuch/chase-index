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
DEFAULT_SCHEME = ""  # "light" or "dark" from the theme file; empty = follow the system. The top-bar toggle overrides it per browser
SEARCH: list[tuple[str, str, str]] = []
TICKER: list[dict] = []   # the 8 newest dated triggers, shown in the bar under the nav on every page   # (account name, company_id) for the top-bar search, filled in main()
# variables a theme may set (everything else in the file is ignored); values may not break out of the declaration
THEME_VARS = {"bg", "fg", "muted", "line", "card", "accent", "rep", "rep-bg", "prx", "prx-bg", "est", "est-bg", "flag", "flag-bg",
              "t1", "t2", "t3", "tier-fg", "chip", "chip-fg", "font", "font-mono", "radius", "panel", "faint", "link", "ink",
              "focus", "accent-fg", "glass-hi"}
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
    opts = "".join(f'<option value="{E(n)}" data-id="{E(c)}" data-meta="{E(m)}"></option>' for n, c, m in SEARCH)
    scheme = f' data-theme="{DEFAULT_SCHEME}"' if DEFAULT_SCHEME in ("light", "dark") else ""
    return f"""<!doctype html>
<html lang="en"{scheme}><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<script>try{{var t=localStorage.getItem("chase-workspace-theme");if(t)document.documentElement.setAttribute("data-theme",t);
if(localStorage.getItem("chase-workspace-ticker")==="{TICKER[0]['key'] if TICKER else ''}")document.documentElement.setAttribute("data-ticker","off")}}catch(e){{}}</script>
{NOINDEX}
<title>{E(title)} | Chase Index workspace</title>
<link rel="stylesheet" href="{up}assets/style.css">{f'<link rel="stylesheet" href="{up}assets/theme.css">' if THEME_ON else ''}</head>
<body><header class="top"><div class="wrap"><a class="brand" href="{up}index.html">Chase Index <span>workspace</span></a>
<nav>{navh}</nav>
<div class="tools"><div class="search"><input type="search" id="acct-search" placeholder="Jump to account" aria-label="Jump to an account page (press /)" data-up="{up}" autocomplete="off"
role="combobox" aria-expanded="false" aria-controls="acct-dd" aria-autocomplete="list"><kbd>/</kbd><ul id="acct-dd" class="dd" role="listbox" hidden></ul></div>
<datalist id="acct-list">{opts}</datalist><button type="button" class="theme-btn" data-theme-toggle aria-label="Switch light or dark">Dark</button></div></div>{ticker(up)}</header>
<main class="wrap">{body}</main>
<footer class="wrap foot"><p>Prototype built {date.today().isoformat()} from public data. {DISCLAIMER}</p>
<p class="muted">Reported = statutory filings. Computed proxy = derived from financial statements. Estimate = model output with stated assumptions.</p></footer>
<script src="{up}assets/app.js"></script></body></html>"""


def ticker(up: str) -> str:
    """Thin bar under the nav: the newest dated triggers, scrolling (static with reduced motion), pause on hover, dismissible."""
    if not TICKER:
        return ""
    def items(hidden):
        attrs = ' tabindex="-1"' if hidden else ""
        return "".join(f'<a href="{up}accounts/{E(t["company_id"])}.html"{attrs} title="{E(t["text"])}"><b>{E(t["company"])}</b> \u00b7 {E(t["what"])} \u00b7 {E(t["change"])}</a>'
                       for t in TICKER)
    return (f'<div class="ticker" role="region" aria-label="Newest triggers" data-key="{E(TICKER[0]["key"])}"><span class="tk-lab">Latest</span>'
            f'<div class="tk-view"><div class="tk-track"><span class="tk-set">{items(False)}</span><span class="tk-set" aria-hidden="true">{items(True)}</span></div></div>'
            f'<button type="button" class="tk-x" aria-label="Dismiss the trigger ticker" title="Dismiss">\u00d7</button></div>')


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
        css += (f"@media (prefers-color-scheme:dark){{:root:not([data-theme=light]){{{dark}}}}}\n"
                f":root[data-theme=dark]{{{dark}}}\n")
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
            pts.append((f"FY{int(fy)}" if fy else "latest", es["pmp_days"]))
        return pts, "Spanish PMP by fiscal year (statutory)", 60
    return [], "", None


def sparkline(pts: list[tuple[str, float]], what: str, bench: int | None, w: int = 64, h: int = 18) -> str:
    if len(pts) < 2:
        one = f"{pts[0][1]:.0f}d only" if pts else "no reported series"
        return f'<span class="spark none" title="{E(what or "Computed proxy: no reported series")}">{E(one if pts else "no series")}</span>'
    vals = [v for _, v in pts]
    lo, hi = min(vals + ([bench] if bench else [])), max(vals + ([bench] if bench else []))
    span = (hi - lo) or 1
    pad = 4   # room for the end dot (r=2) and the stroke, so nothing is drawn on the edge
    x = lambda i: pad + i * (w - 2 * pad) / (len(pts) - 1)
    y = lambda v: h - pad - (v - lo) * (h - 2 * pad) / span
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
CONTACT = {"Head of accounts payable or shared services": "AP"}   # everything else is the treasurer or CFO office
LINK_ICON = ('<svg class="ico" width="13" height="13" viewBox="0 0 16 16" aria-hidden="true"><path d="M9 2h5v5M14 2 7 9M12 9.5V13a1 1 0 0 1-1 1H3a1 '
             '1 0 0 1-1-1V5a1 1 0 0 1 1-1h3.5" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round"/></svg>')


def icon_link(url, label="source") -> str:
    if not isinstance(url, str) or not url.startswith("http"):
        return '<span class="nolink" title="no source link">–</span>'
    return f'<a class="src" href="{E(url)}" target="_blank" rel="noopener" title="{E(label)}" aria-label="{E(label)}">{LINK_ICON}</a>'


def avatar(name: str) -> str:
    """Initial in a circle; the hue is derived from the name so it stays the same between builds."""
    hue = sum(ord(ch) for ch in name) * 37 % 360
    return f'<span class="av" style="--h:{hue}" aria-hidden="true">{E(name.strip()[:1].upper())}</span>'


def tier_dot(t) -> str:
    return f'<i class="dot t{E(str(t))}" title="Tier {E(str(t))}" aria-label="Tier {E(str(t))}"></i>' if t is not None else ""


def days_bar(days: int | None, bench: int | None, scale: int, kcls: str, tip: str) -> str:
    if not days:
        return '<span class="days none">n/a</span>'
    w = min(100, days * 100 / scale)
    tick = f'<em style="left:{min(100, bench * 100 / scale):.1f}%"></em>' if bench else ""
    return (f'<span class="days {kcls}" title="{E(tip)}"><span class="num">{days}</span>'
            f'<span class="bar" aria-hidden="true"><i style="width:{w:.1f}%"></i>{tick}</span></span>')


CUR = {"GBP": "\u00a3", "USD": "$", "EUR": "\u20ac", "CHF": "CHF "}


def short_money(v, cur) -> str:
    v = float(v)
    s = f"{v / 1e9:.1f}bn" if v >= 1e9 else f"{v / 1e6:.0f}m"
    return f"{CUR.get(cur, (cur or '') + ' ')}{s}"


def live_by_type(cid: str, public: list[dict] | None) -> dict:
    mine = {}
    for t in sorted((t for t in (public or []) if t["company_id"] == cid and t.get("is_live")), key=lambda t: -(t.get("strength") or 0)):
        mine.setdefault(t["trigger_type"], t)
    return mine


def why_pill(a: dict, trig_by_type: dict) -> str | None:
    """The single most specific why-now signal, with its number, at most about 14 characters. Priority:
    terms lengthened > SCF started > confirmed supplier finance with amount > year-on-year change (median UK entity)
    > Spain payment period change > crossed 60 days."""
    tt = set(trig_by_type)
    if "terms_changed_longer" in tt:
        m = re.search(r"from (?:standard )?(\d+)\s*(?:days?\s*)?to (\d+)\s*days", trig_by_type["terms_changed_longer"]["text"])
        return f"Terms {m.group(1)}\u2192{m.group(2)}d" if m else "Terms longer"
    if "scf_started" in tt:
        return "SCF started"
    b = q.get_account_brief(a["company_id"])
    sf = b.get("supplier_finance") or {}
    if sf.get("programme_disclosed") and sf.get("confirmed") and sf.get("obligations_outstanding"):
        return f"SCF {short_money(sf['obligations_outstanding'], sf.get('currency'))}"
    uk = (b.get("payment_profile") or {}).get("reported", {}).get("uk") or {}
    med = uk.get("trend_days_year_on_year_median")
    if med is not None and med >= 1:
        return f"+{int(med + 0.5)}d YoY"
    if "es_pmp_rose" in tt:
        m = re.search(r"from (\d+) to (\d+) days", trig_by_type["es_pmp_rose"]["text"])
        return f"ES {m.group(1)}\u2192{m.group(2)}d" if m else "ES slower"
    if "filing_crossed_60" in tt:
        return "Crossed 60d"
    return None


def opener_card(text: str) -> str:
    """The draft opener as a small document card, Copy as the primary action."""
    return (f'<div class="doc"><blockquote class="opener">{E(text)}</blockquote><div class="doc-foot"><span class="faint">Draft \u00b7 edit before sending</span>'
            f'<button type="button" class="copy primary" data-copy="{E(text)}">Copy opener</button></div></div>')


def build_queue(queue: dict, types: dict, public: list[dict] | None = None) -> str:
    by_key = {(t["company_id"], t["text"]): t for t in (public or [])}
    acc = queue["accounts"]
    keys = {a["company_id"]: key_number(a["company_id"]) for a in acc}
    nums = [int(k[0][:-1]) for k in keys.values() if k[0][:-1].isdigit()]
    scale = max(nums + [90])
    rows, n_tre, n_ap, n_din = [], 0, 0, 0
    for a in acc:
        cid = a["company_id"]
        kn, kvs, kcls, kind = keys[cid]
        days = int(kn[:-1]) if kn[:-1].isdigit() else None
        bench = 32 if kind == "uk_reported" else 60 if kind == "es_reported" else (int(kvs.split()[1]) if kvs.split()[1:2] and kvs.split()[1].isdigit() else None)
        tt = [x for x in (a.get("why_now_types") or "").split("|") if x]
        role = a.get("who_role") or "n/a"
        contact = CONTACT.get(role, "Treasury")
        n_tre += contact == "Treasury"
        n_ap += contact == "AP"
        n_din += a.get("play") == "dinner_invite"
        pv = why_pill(a, live_by_type(cid, public))
        pill = (f'<span class="pill" title="Strongest specific signal. All signals in the details panel.">{E(pv)}</span>' if pv
                else f'<span class="pill">{E(ROW_TAG.get(tt[0], short_label(tt[0])))}</span>' if tt else '<span class="faint">standing evidence</span>')
        spark = sparkline(*days_series(cid, kind), w=120, h=28)
        def why_li(x):
            t = by_key.get((cid, x))
            if not t:
                return f'<li title="{E(x)}"><span class="w-what">{E(x)}</span></li>'
            what, chg = trigger_line(t)
            return (f'<li title="{E(x)}"><span class="w-what">{E(what)}</span><span class="sep">\u00b7</span>'
                    f'<span class="w-chg">{E(chg)}</span>{icon_link(t.get("evidence_url"))}</li>')
        why = "".join(why_li(x) for x in a["why_now"].split(" | "))
        n_shown = len(a["why_now"].split(" | "))
        all_tags = "".join(f'<span class="chip" title="{E(types.get(x, x))}">{E(short_label(x))}</span>' for x in tt) or '<span class="faint">none</span>'
        n_live = a.get("triggers_live_n") or 0
        one_pager = f'<a href="one_pagers/{E(cid)}.html">One-pager</a>' if a.get("one_pager") else ""
        thin = ' <span class="flag" title="UK invoice value under 1% of group revenue">thin evidence</span>' if a.get("thin_evidence") else ""
        status_btn = (f'<button type="button" class="spill" data-cid="{E(cid)}" data-company="{E(a["company"])}" data-play="{E(a.get("play") or "")}" '
                      f'data-status="todo" title="Click to change status">To do</button>')
        rows.append(f"""<div class="qrow" role="row" tabindex="0" data-frow data-cid="{E(cid)}" data-contact="{contact.lower()}" data-play="{E(a.get('play') or '')}" data-status="todo" aria-label="{E(a['company'])}: open details">
<span class="c-co">{avatar(a['company'])}<span class="co-t"><span class="co-n"><b>{E(a['company'])}</b>{tier_dot(a.get('tier'))}</span><span class="sub">{E(a.get('country') or '')}</span></span></span>
{days_bar(days, bench, scale, kcls, kn + ' ' + kvs)}
<span class="c-why">{pill}</span>
<span class="c-contact" title="{E(role)}">{contact}</span>
<span class="c-status">{status_btn}</span>
<template class="detail"><header class="p-head">{avatar(a['company'])}<div><h2>{E(a['company'])} {tier_badge(a.get('tier'))}</h2>
<div class="sub">{E(a.get('country') or '')} · {E((a.get('sector') or '').replace('_', ' '))} · queue #{a['queue_rank']}{thin}</div></div></header>
<section class="p-key"><div><span class="p-num {kcls}">{E(kn)}</span> <span class="muted">{E(kvs)}</span>
<div class="p-basis"><span class="lbl {'rep' if kcls == 'rep' else 'prx'}">{'Reported' if kcls == 'rep' else 'Computed proxy'}</span>{icon_link(a.get('evidence_url'), 'evidence source')}</div></div>{spark}</section>
<section><h3>Why now {('<span class="pill">' + E(pv) + '</span>') if pv else ''} <span class="faint">{('top ' + str(n_shown) + ' of ') if n_live > n_shown else ''}{n_live} live event{'' if n_live == 1 else 's'}</span></h3><ul class="why">{why}</ul></section>
<section><h3>Opener</h3>{opener_card(a.get('opener_draft') or '')}</section>
<section><dl class="p-dl"><dt>Ask for</dt><dd>{E(ROLE_SHORT.get(role, role))} · {linkedin(a['company'], role)}<div class="faint small">{E(a.get('who_role_reason') or '')}</div></dd>
<dt>Links</dt><dd><a href="accounts/{E(cid)}.html">Account page</a>{' · ' + one_pager if one_pager else ''}{(' · ' + link(a.get('evidence_url'), 'Evidence')) if a.get('evidence_url') else ''}{(' · ' + link(a.get('why_now_url'), 'Trigger source')) if a.get('why_now_url') else ''}</dd></dl></section>
<details class="p-more"><summary>More</summary><dl class="p-dl"><dt>Evidence</dt><dd>{E(a.get('evidence') or '')}</dd>
<dt>Play</dt><dd>{E(PLAY_LABEL.get(a.get('play'), a.get('play') or ''))}</dd>
<dt>Priority</dt><dd>{num(a.get('queue_priority'), 1)} <span class="faint">({E(a.get('priority_explained') or '')})</span></dd>
<dt>Signals</dt><dd>{all_tags}</dd><dt>Account</dt><dd>index rank {E(str(a.get('index_rank') or ''))}</dd></dl></details></template>
</div>""")
    tabs = [("all", "All", len(acc)), ("treasury", "Treasury", n_tre), ("ap", "AP", n_ap), ("dinner", "Dinner", n_din)]
    tabh = "".join(f'<button type="button" class="tab" role="tab" data-tab="{k}" aria-selected="{"true" if k == "all" else "false"}">{lab} <span class="cnt">{n}</span></button>'
                   for k, lab, n in tabs)
    wk = str(queue["week"]).split("-")[-1].lstrip("0")
    body = f"""<div class="pagehead"><div class="ph-t"><h1>{len(acc)} accounts to chase this week.</h1>
<div class="ph-sub">Week {E(wk)} \u00b7 {queue['eligible_accounts']} eligible</div></div>
<div class="ph-bar"><div class="tabs" role="tablist" aria-label="Filter the queue">{tabh}</div>
<div class="tools-r"><button type="button" id="export-status" class="primary" title="Download a CSV in the config/status/ format">Export status</button>
<button type="button" class="kbd-btn" data-help aria-label="Keyboard shortcuts" title="Keyboard shortcuts (?)">?</button></div></div></div>
<div class="list qlist" id="queue" role="grid" data-list>
<div class="lhead qgrid" role="row"><span>Company</span><span>Days to pay <span class="faint">· median 32</span></span><span>Why now</span><span>Contact</span><span>Status</span></div>
{''.join(rows)}
</div>
<aside id="panel" class="panel" aria-label="Details" hidden><button type="button" class="pclose" aria-label="Close details (Esc)">×</button><div class="pbody"></div></aside>
<div id="kbd-help" class="kbd-help" role="dialog" aria-label="Keyboard shortcuts" hidden>
<h2>Keyboard</h2><dl><dt><kbd>j</kbd> <kbd>k</kbd></dt><dd>next / previous account</dd><dt><kbd>Enter</kbd></dt><dd>open details</dd>
<dt><kbd>c</kbd></dt><dd>copy the opener</dd><dt><kbd>/</kbd></dt><dd>search accounts</dd><dt><kbd>Esc</kbd></dt><dd>close</dd><dt><kbd>?</kbd></dt><dd>this list</dd></dl>
<p class="small muted">Status lives in this browser. Export it to <code>config/status/accounts_status.csv</code> for <code>make queue</code> and <code>make feedback</code>
("Not now" exports as <code>not_a_fit</code>, reason "not now"). Days bar: reported days to pay, tick = benchmark (UK median 32, Spain legal maximum 60, or the sector median for a computed proxy).
{E(queue['note'].replace(' who_named is present only when local private data exists.', ''))}</p></div>
<div id="toast" class="toast" role="status" aria-live="polite" hidden></div>"""
    return page("Queue", body, 0, "queue")


def section(title: str, inner: str) -> str:
    return f'<section><h3>{title}</h3>{inner}</section>'


PAYABLES = {"trade": "trade payables", "trade_and_other_broad": "trade and other payables (broad: includes non-trade items)"}
COST = {"cost_of_sales": "cost of sales", "cost_of_materials": "cost of materials", "by_nature_fallback": "expenses by nature (fallback)",
        "operating_expenses_fallback": "operating expenses (fallback)", "missing": "not available"}
AGG = {"invoice_value_weighted_mean": "weighted by invoice value", "simple_mean": "simple mean of entities"}
MATCH = {"ch_psc_chain": "Companies House ownership chain", "exact_name": "exact name match", "brand_prefix": "brand name match"}
PAIN_BASIS = {"uk_reported": "UK statutory payment reports", "es_reported": "Spanish statutory payment period (PMP)",
              "computed_dpo_proxy": "computed DPO (proxy)", "no_evidence": "no payment evidence"}
PART = {"erp": "ERP signal", "geography": "Geography", "revenue": "Revenue band", "sector": "Sector", "supplier_breadth": "Supplier breadth",
        "days": "Days to pay", "pct_late": "Share paid late", "pct_over_60": "Share paid after 60 days", "trend": "Year-on-year trend",
        "dpo_confidence_factor": "DPO confidence factor", "dpo_vs_sector_median_ratio": "DPO vs sector median (ratio)",
        "uk_materiality_factor": "UK materiality factor"}
RATIONALE = {"llm_written_validated_against_row": "written by a model, every figure checked against the data row",
             "deterministic_template": "template"}
LINKEDIN_ROLE = {"Group treasurer or CFO office": "treasurer", "CFO office": "CFO", "Head of accounts payable or shared services": "head of accounts payable"}


def human(code) -> str:
    return str(code or "").replace("_", " ")


def clean(text) -> str:
    """Plain words for visible copy: snake_case codes become words, 'fy2025' becomes 'FY2025'."""
    t = re.sub(r"\b[a-z]+(?:_[a-z0-9]+)+\b", lambda m: m.group(0).replace("_", " "), str(text or ""))
    return re.sub(r"\b(?:fy|FY)(\d{4})(?:\.0)?(?!\d)", r"FY\1", t)


def fy(v) -> str:
    try:
        return str(int(float(v)))
    except (TypeError, ValueError):
        return E(str(v or ""))


def linkedin(company: str, role: str) -> str:
    """A plain LinkedIn people-search link the user opens by hand. Nothing is fetched or scraped."""
    from urllib.parse import quote
    kw = f"{q.short_name(company)} {LINKEDIN_ROLE.get(role, role)}"
    return (f'<a class="li" href="https://www.linkedin.com/search/results/people/?keywords={quote(kw)}" target="_blank" '
            f'rel="noopener noreferrer" title="Opens a LinkedIn people search for: {E(kw)}">Find on LinkedIn</a>')


_RANGE = re.compile(r"(\d+)\s*(?:to|-|–|and)\s*(\d+)")


def term_ranges(text) -> list[tuple[str, int, int]]:
    """[(label, low, high)] from a filing's payment-terms text: 'cost of inventories 45 to 225 days; freight 120 to 210'.
    Extensions ('extended by 0 to 20 days') are not absolute terms and are skipped."""
    out = []
    for seg in str(text or "").split(";"):
        if re.search(r"\bextended\b[^;]*\bby\b", seg):
            continue
        m = _RANGE.search(seg)
        if not m:
            continue
        lo, hi = int(m.group(1)), int(m.group(2))
        if not (0 <= lo <= hi <= 720):
            continue
        label = re.sub(r"\b(generally|typically|between|maturity dates|general payment terms of|payment terms|majority of suppliers on)\b", "",
                       seg[:m.start()], flags=re.I).strip(" :,()")
        out.append((label, lo, hi))
    return out


def terms_bars(with_t, without_t) -> str:
    """Two horizontal range bars per category (with / without the programme) on one shared day axis."""
    w, wo = term_ranges(with_t), term_ranges(without_t)
    if not w or not wo:
        return ""
    rows = []
    overall_wo = next((r for r in wo if not r[0]), None) if len(wo) == 1 else None
    for lab, lo, hi in w:
        match = next((r for r in wo if r[0] and lab and r[0].lower() == lab.lower()), None) or overall_wo or (wo[0] if len(w) == 1 else None)
        if match:
            rows.append((lab or "All suppliers", (lo, hi), (match[1], match[2])))
    if not rows:
        return ""
    top = max(max(a[1], b[1]) for _, a, b in rows)
    axis = max(60, -(-top // 60) * 60)
    pct = lambda v: f"{v * 100 / axis:.2f}%"

    def bar(cls, r, lab):
        return (f'<div class="tb-row"><span class="tb-k">{lab}</span><span class="tb-track"><i class="{cls}" style="left:{pct(r[0])};width:{pct(r[1] - r[0])}"></i></span>'
                f'<span class="tb-v">{r[0]}–{r[1]}d</span></div>')
    ticks = "".join(f'<span style="left:{pct(t)}">{t}</span>' for t in range(0, axis + 1, 60))
    body = "".join(f'<div class="tb-g"><div class="tb-cat">{E(clean(lab))}</div>{bar("w", a, "With programme")}{bar("wo", b, "Without")}</div>' for lab, a, b in rows)
    return f'<div class="tbars">{body}<div class="tb-axis"><span class="tb-k"></span><span class="tb-ticks">{ticks}</span><span class="tb-v">days</span></div></div>'


def angle(b: dict, cid: str, kn: str, kvs: str, kind: str) -> str:
    """One sentence from the opener rules (chase.gtm.nba), as a template with data slots. No model text."""
    short = q.short_name(b["name"])
    pp = b.get("payment_profile") or {}
    uk, es, cp = (pp.get("reported") or {}).get("uk") or {}, (pp.get("reported") or {}).get("spain") or {}, pp.get("computed_proxy") or {}
    sf = b.get("supplier_finance") or {}
    days = kn.rstrip("d")
    med = uk.get("trend_days_year_on_year_median")
    trend = (f"UK days to pay rose (median entity +{int(med + 0.5)} days, now {days})" if kind == "uk_reported" and med is not None and med >= 1
             else f"days to pay sit at {days}")
    if sf.get("programme_disclosed") and sf.get("confirmed") and sf.get("obligations_outstanding"):
        now, prior, cur = sf["obligations_outstanding"], sf.get("prior_year"), sf.get("currency")
        if prior and abs(now - prior) / prior >= 0.1:
            moved = "fell" if now < prior else "rose"
            return (f"Supplier finance outstanding {moved} from {short_money(prior, cur)} to {short_money(now, cur)} while {trend}; "
                    f"ask treasury why, and whether terms got longer when the programme came in.")
        return f"{short} runs a {short_money(now, cur)} supplier finance programme while {trend}; ask treasury who it reaches and whether terms got longer with it."
    late = uk.get("pct_invoices_paid_late_mean") if kind == "uk_reported" else None
    if late is not None and 25 <= late <= 75:
        return f"{late:.0f}% of UK invoices are paid after the agreed terms at {days} days on average; ask the head of AP what stops invoices being approved on time."
    within = es.get("pct_paid_within_legal_max_by_value") if kind == "es_reported" else None
    if within is not None and within < 60:
        return f"Only {within:.0f}% of Spanish invoice value is paid within the legal 60 days ({days} days on average); ask AP where invoices get stuck."
    if kind in ("uk_reported", "es_reported") and days.isdigit() and int(days) >= 55:
        low = f"only {late:.0f}% paid late" if late is not None else "few invoices over the legal limit"
        return f"{days} days to pay with {low}: the long days are agreed terms; ask treasury whether they are a deliberate working-capital lever."
    if kind not in ("uk_reported", "es_reported") and cp.get("dpo_days") is not None:
        return (f"Computed DPO of {cp['dpo_days']:.0f} days against a sector median of {cp.get('sector_median_dpo_days') or 0:.0f} (a balance-sheet proxy); "
                f"ask the CFO office how much is terms and how much is process.")
    return f"{days} days to pay {kvs}; ask how much is deliberate terms and how much is invoices stuck between AP and the supplier."


def kpi(label, value, sub="", cls="") -> str:
    return f'<div class="kpi"><div class="k-l">{label}</div><div class="k-v {cls}">{value}</div><div class="k-s">{sub}</div></div>'


def build_account(w: dict, public_keys: set, in_queue: bool) -> str:
    from chase.gtm import nba as nba_mod
    b = w["brief"]
    cid = b["company_id"]
    s = b["scores"]
    pp = b.get("payment_profile") or {}
    rep = pp.get("reported") or {}
    uk, es, cp = rep.get("uk"), rep.get("spain"), pp.get("computed_proxy")
    sf = b.get("supplier_finance") or {}
    uf = b.get("uk_filing_features") or {}
    nba = w.get("next_best_action") or {}
    rev = b.get("revenue") or {}
    kn, kvs, kcls, kind = key_number(cid)

    # ---- header
    play = nba.get("play") or ""
    status = (f'<button type="button" class="spill" data-cid="{E(cid)}" data-company="{E(b["name"])}" data-play="{E(play)}" data-status="todo" '
              f'title="Click to change status (same as the queue)">To do</button>')
    head = f"""<p class="crumbs"><a href="../index.html">Queue</a> <span class="faint">/</span> {E(b['name'])}</p>
<header class="rec-head">{avatar(b['name'])}<div class="rh-t"><h1>{E(b['name'])} {tier_badge(b.get('priority_tier'))}</h1>
<div class="sub">{E(b.get('country') or '')} · {E(b.get('hq_city') or 'HQ city unknown')} · {E(human(b.get('sector')))}
<span class="faint"> · index rank {b.get('rank')} · revenue {money(rev.get('amount'), rev.get('currency'))} ({E(str(rev.get('period_end') or '')[:4])})</span>{icon_link(rev.get('source_url'), 'revenue source')}
{' · <span class="flag">thin evidence</span>' if b.get('thin_evidence') else ''}</div></div>
<div class="rh-a">{status}{('<a class="btn" href="../one_pagers/' + E(cid) + '.html">One-pager</a>') if b.get('one_pager') else ''}</div></header>
<div class="angle"><span class="a-l">The angle</span><p>{E(angle(b, cid, kn, kvs, kind))}</p></div>"""

    # ---- KPI tiles (only those with data)
    tiles = [kpi("Days to pay", E(kn), E(kvs), kcls)]
    if uk and uk.get("pct_invoices_paid_over_60_days_mean") is not None:
        tiles.append(kpi("Paid after 60 days", pct(uk["pct_invoices_paid_over_60_days_mean"]), "share of UK invoices"))
    if uk and uk.get("pct_invoices_paid_late_mean") is not None:
        tiles.append(kpi("Paid late", pct(uk["pct_invoices_paid_late_mean"]), "after the agreed terms"))
    if es and es.get("pct_paid_within_legal_max_by_value") is not None:
        tiles.append(kpi("Within legal 60 days", pct(es["pct_paid_within_legal_max_by_value"]), "Spanish invoice value"))
    if sf.get("programme_disclosed") and sf.get("obligations_outstanding"):
        now, prior, cur = sf["obligations_outstanding"], sf.get("prior_year"), sf.get("currency")
        arrow = ""
        if prior:
            arrow = (f'<span class="k-arrow down">↓</span> from {short_money(prior, cur)}' if now < prior
                     else f'<span class="k-arrow up">↑</span> from {short_money(prior, cur)}' if now > prior else "unchanged")
        if not sf.get("confirmed"):
            arrow = (arrow + " \u00b7 " if arrow else "") + "one reader only"
        tiles.append(kpi("Supplier finance", short_money(now, cur), arrow or "outstanding"))
    spark = sparkline(*days_series(cid, kind), w=150, h=40)
    kpis = f'<div class="kpis">{"".join(tiles)}<div class="kpi k-spark"><div class="k-l">Trend</div>{spark}</div></div>'

    main = []
    # ---- UK entities with mini bars vs the median
    if uk:
        ents = uk.get("entities", [])
        scale = max([e.get("avg_days_to_pay") or 0 for e in ents] + [90])
        rows = "".join(f"""<tr><td>{E(_ent(e['name'] or ''))} <span class="faint small">{E(e.get('company_number') or '')}</span></td>
<td class="num">{days_bar(int(e['avg_days_to_pay']) if e.get('avg_days_to_pay') is not None else None, 32, scale, 'rep', f"{e.get('avg_days_to_pay')} days vs UK median 32")}</td>
<td class="num">{pct(e.get('pct_paid_late')) if e.get('pct_paid_late') is not None else '<span class="faint" title="' + E(e.get('pct_paid_late_note') or '') + '">n/s</span>'}</td>
<td class="num">{pct(e.get('pct_paid_over_60'))}</td><td class="num">{('+' if (e.get('trend_days_yoy') or 0) > 0 else '') + num(e.get('trend_days_yoy')) if e.get('trend_days_yoy') is not None else '<span class="faint">n/a</span>'}</td>
<td class="faint small nowrap">{E(str(e.get('period_end'))[:7])}</td><td>{icon_link(e.get('source_url'))}</td></tr>""" for e in ents)
        per = uk.get("period") or {}
        share = uf.get("einvoicing_offered_share")
        feat = f"""<details class="p-more"><summary>UK filing details</summary><dl class="p-dl">
<dt>Late because of disputes</dt><dd>{pct(uf.get('late_because_of_dispute_pct'))} {icon_link(uf.get('late_because_of_dispute_url'))}</dd>
<dt>Terms made longer</dt><dd>{uf.get('terms_changed_longer_n')} entities {icon_link(uf.get('terms_changed_longer_url')) if uf.get('terms_changed_longer_url') else ''}</dd>
<dt>Offer e-invoicing</dt><dd>{pct(share * 100) if share is not None else 'n/a'}{' · newly started' if uf.get('einvoicing_started') else ''}</dd>
<dt>Payment codes</dt><dd>{E(clean(uf.get('payment_codes') or 'none stated'))}{' · pay to stay reported' if uf.get('pay_to_stay') else ''}</dd>
<dt>Entity matching</dt><dd>lowest confidence {num(uk.get('entity_match_confidence_min'), 2)} · {E(', '.join(MATCH.get(m, human(m)) for m in str(uk.get('entity_match_methods') or '').split('|') if m))}</dd>
</dl></details>""" if uf else ""
        main.append(section("UK entities", f"""<p class="sec-sum">{num(uk.get('avg_days_to_pay_mean_of_entities'))} days across {uk['entities_n']} UK entities, {E(AGG.get(uk.get('aggregation'), human(uk.get('aggregation'))))}
· median entity {('+' if (uk.get('trend_days_year_on_year_median') or 0) > 0 else '') + num(uk.get('trend_days_year_on_year_median'))} days year on year · {E(str(per.get('start')))} to {E(str(per.get('end')))}</p>
<div class="tablewrap"><table class="data ents"><thead><tr><th>Entity</th><th class="num">Days <span class="faint">· median 32</span></th><th class="num">Late</th><th class="num">&gt;60d</th><th class="num">YoY</th><th>Period</th><th></th></tr></thead><tbody>{rows}</tbody></table></div>
<p class="faint small">UK legal entities only, not the whole group.</p>{feat}"""))
    if es:
        main.append(section("Spain", f"""<dl class="p-dl"><dt>Payment period</dt><dd>{num(es.get('pmp_days'))} days in FY{fy(es.get('fiscal_year'))} (prior year {num(es.get('prior_year_pmp_days'))}) · legal maximum 60 {icon_link(es.get('source_url'))}</dd>
<dt>Paid in time</dt><dd>{pct(es.get('pct_paid_within_legal_max_by_value'))} of invoice value within the legal maximum</dd>
<dt>Scope</dt><dd>{E(human(es.get('scope')) or 'n/a')} · extraction confidence {num(es.get('extraction_confidence'), 2)}</dd></dl>"""))

    # ---- why now (dated), then standing facts not already shown elsewhere
    live = sorted([t for t in w.get("triggers", []) if (cid, t["text"]) in public_keys], key=lambda t: str(t.get("trigger_date")), reverse=True)
    lines = []
    for t in live:
        what, chg = trigger_line(t)
        lines.append(f'<li title="{E(t["text"])}"><span class="w-date">{E(str(t.get("trigger_date"))[:10])}</span><span class="w-what">{E(what)}</span>'
                     f'<span class="sep">·</span><span class="w-chg">{E(chg)}</span>{icon_link(t.get("evidence_url"))}</li>')
    shown_sf = bool(sf.get("programme_disclosed")) or (uf.get("scf_offered_n") or 0) > 0

    def repeated(text: str) -> bool:
        low = text.lower()
        return (any(low in t["text"].lower() or t["text"].lower() in low for t in live)
                or (uk and "median entity change" in low)                                     # in the UK section and the KPI tiles
                or (shown_sf and ("supplier finance programme" in low or "supply chain finance" in low)))  # in Supplier finance
    facts = [f'<li><span class="w-chg">{E(clean(x.get("text") or ""))}</span>{icon_link(x.get("url"))}</li>'
             for x in b.get("why_now_signals") or [] if not repeated(x.get("text") or "")]
    inner = f'<ul class="why">{"".join(lines)}</ul>' if lines else '<p class="faint">No public dated trigger.</p>'
    if facts:
        inner += f'<h4 class="subh">Standing facts</h4><ul class="why">{"".join(facts)}</ul>'
    main.append(section("Why now", inner))

    # ---- supplier finance, with terms as range bars on one day axis
    if sf or (uf.get("scf_offered_n") or 0) > 0:
        uk_scf = (f'<dt>UK filings</dt><dd>{uf.get("scf_offered_n")} UK entit{"y" if uf.get("scf_offered_n") == 1 else "ies"} report offering supply chain finance'
                  f'{" (newly started)" if uf.get("scf_started") else ""}</dd>') if (uf.get("scf_offered_n") or 0) > 0 else ""
        if sf.get("programme_disclosed"):
            conf = "confirmed by two readers" if sf.get("confirmed") else "one reader only, not used in scoring"
            bars = terms_bars(sf.get("terms_with_programme"), sf.get("terms_without_programme"))
            sfh = f"""<dl class="p-dl"><dt>Programme</dt><dd><span class="lbl rep">Reported</span> disclosed in the annual report · {E(conf)} {icon_link(sf.get('source_url'))}</dd>
<dt>Outstanding</dt><dd>{money(sf.get('obligations_outstanding'), sf.get('currency'))} (prior year {money(sf.get('prior_year'), sf.get('currency'))}) at {E(str(sf.get('period_end'))[:10])}</dd>{uk_scf}</dl>
{('<h4 class="subh">Payment terms, with and without the programme</h4>' + bars) if bars else ''}
<details class="p-more"><summary>Terms as written in the filing</summary><dl class="p-dl"><dt>With it</dt><dd>{E(clean(sf.get('terms_with_programme') or 'n/a'))}</dd>
<dt>Without</dt><dd>{E(clean(sf.get('terms_without_programme') or 'n/a'))}</dd></dl>
{('<blockquote class="small">' + E(sf['quote']) + '</blockquote>') if sf.get('quote') else ''}</details>"""
        else:
            sfh = (f'<p class="muted">No supplier finance programme found in the annual report. {icon_link(sf.get("source_url"))}</p>' if sf else "") + (f'<dl class="p-dl">{uk_scf}</dl>' if uk_scf else "")
        main.append(section("Supplier finance", sfh))

    # ---- collapsed: proxy data, estimate, scoring
    if cp:
        broad = cp.get("payables_basis") == "trade_and_other_broad"
        caveat = ("Computed by us from the balance sheet: payables / cost of sales x 365. A proxy, not reported days to pay."
                  + (" The payables line here is broad (it includes non-trade items), so the figure overstates days and is not used as evidence." if broad else "")
                  + (" The account has reported figures above; those take precedence." if rep else ""))
        main.append(f"""<details class="p-more sec"><summary>Proxy data <span class="faint">computed DPO</span></summary>
<p class="faint small">{E(caveat)}</p><dl class="p-dl"><dt>DPO FY{fy(cp.get('fiscal_year'))}</dt><dd>{num(cp.get('dpo_days'))} days (prior year {num(cp.get('prior_year_dpo_days'))}; sector median {num(cp.get('sector_median_dpo_days'))}) {icon_link(cp.get('source_url'))}</dd>
<dt>Payables</dt><dd>{E(PAYABLES.get(cp.get('payables_basis'), human(cp.get('payables_basis'))))}</dd><dt>Cost</dt><dd>{E(COST.get(cp.get('cost_basis'), human(cp.get('cost_basis'))))}</dd>
<dt>Confidence</dt><dd>{num(cp.get('confidence'), 2)}{'' if cp.get('flag') in (None, 'ok') else ' · ' + E(human(cp.get('flag')))}</dd></dl></details>""")
    est = b.get("estimates") or {}
    eh = []
    for key, lab in (("uk_scope", "UK scope"), ("group_proxy", "Group (proxy)")):
        x = est.get(key)
        if not x:
            continue
        o = x.get("early_payment_discount_opportunity") or {}
        cur = x.get("currency")
        eh.append(f"""<dt>{lab}</dt><dd>{money(o.get('low'), cur)} to {money(o.get('high'), cur)} a year (base {money(o.get('base'), cur)}) ·
supplier cash beyond 30 days {money(x.get('supplier_cash_beyond_30_days'), cur)}<div class="faint small">{E(clean(x['basis']))}</div></dd>""")
    a = est.get("assumptions") or {}
    sct = " · ".join(f"{k}: {v.get('share_eligible', 0)*100:.0f}% eligible at {v.get('annualised_rate', 0)*100:.0f}% APR" for k, v in (a.get("scenarios") or {}).items())
    if eh:
        main.append(f"""<details class="p-more sec"><summary>Opportunity estimate <span class="lbl est">Estimate</span></summary><dl class="p-dl">{''.join(eh)}</dl>
<p class="faint small">{E(clean(a.get('formula') or ''))}. {E(sct)}. Early pay on day {E(str(a.get('early_pay_day')))}, at most {E(str(a.get('max_days_accelerated')))} days accelerated.
Assumptions in {E(a.get('config_file') or '')}. {E(clean(est.get('uk_scope_note') or ''))} {E(clean(est.get('whose_money') or ''))}</p></details>""")

    def tbl(d):
        return "".join(f"<tr><td>{E(PART.get(k, human(k)))}</td><td class='num'>{num(v, 1)}</td></tr>" for k, v in (d or {}).items())
    main.append(f"""<details class="p-more sec"><summary>How it’s scored <span class="faint">fit {num(s.get('fit'))} · pain {num(s.get('pain'))} · signal {num(s.get('signal'))} · priority {num(s.get('priority'))}</span></summary>
<p class="small">{E(clean(b.get('rationale') or ''))} <span class="faint">({E(RATIONALE.get(b.get('rationale_method'), human(b.get('rationale_method'))))})</span></p>
<p class="faint small">Deterministic formula, weights in <code>config/assumptions.yaml</code>. Pain is based on {E(PAIN_BASIS.get(s.get('pain_basis'), human(s.get('pain_basis'))))}; reported evidence always outranks a computed proxy. <a href="../method.html">Method</a></p>
<div class="two"><table class="data small"><thead><tr><th>Fit</th><th class="num">Points</th></tr></thead><tbody>{tbl(s.get('fit_parts'))}</tbody></table>
<table class="data small"><thead><tr><th>Pain</th><th class="num">Points</th></tr></thead><tbody>{tbl(s.get('pain_parts'))}</tbody></table></div></details>""")

    # ---- right rail: who, opener, play, links
    role = nba.get("who_role") or nba_mod.suggested_role(q._row(cid), None)[0]
    reason = nba.get("who_role_reason") or nba_mod.suggested_role(q._row(cid), None)[1]
    trig_url = next((t.get("evidence_url") for t in live if isinstance(t.get("evidence_url"), str) and t["trigger_type"] not in ("dinner_city",)), None)
    ev_url = (uk or {}).get("slowest_entity", {}).get("source_url") if kind == "uk_reported" else (es or {}).get("source_url") if kind == "es_reported" else (cp or {}).get("source_url")
    links = " · ".join(x for x in (
        f'<a href="../one_pagers/{E(cid)}.html">One-pager</a>' if b.get("one_pager") else "",
        link(ev_url, "Evidence") if ev_url else "", link(trig_url, "Trigger source") if trig_url else "") if x)
    rail = [f"""<section><h3>Ask for</h3><p class="r-role">{E(ROLE_SHORT.get(role, role))}</p><p class="faint small">{E(clean(reason))}</p><p>{linkedin(b['name'], role)}</p></section>"""]
    if nba.get("opener_draft"):
        rail.append(f'<section><h3>Opener</h3>{opener_card(nba["opener_draft"])}</section>')
        rail.append(f"""<section><dl class="p-dl"><dt>Play</dt><dd>{E(PLAY_LABEL.get(nba['play'], nba['play']))}</dd>
<dt>Priority</dt><dd>{num(nba.get('queue_priority'), 1)} · queue #{nba.get('queue_rank')}<div class="faint small">{E(nba.get('priority_explained') or '')}</div></dd></dl></section>""")
    else:
        rail.append('<section><p class="faint small">Not in this week’s queue, so no opener draft. In the top 100 or on a dinner list.</p></section>')
    if links:
        rail.append(f'<section><h3>Links</h3><p class="r-links">{links}</p></section>')

    body = f"""<div class="rec">{head}{kpis}<div class="rec-grid"><div class="rec-main">{''.join(main)}</div>
<aside class="rec-rail" aria-label="Next step">{''.join(rail)}</aside></div></div>"""
    return page(b["name"], body, 1)


INVITE_ROLE = {"Group treasurer or CFO office": "CFO / Treasurer", "CFO office": "CFO", "Head of accounts payable or shared services": "CFO / Head of AP"}


def build_dinners(dinners: list[dict], public: list[dict] | None = None) -> str:
    from chase.gtm import nba as nba_mod
    blocks = []
    for d in dinners:
        if not d.get("found"):
            continue

        def row(a):
            kn, kvs, kcls, _ = key_number(a["company_id"])
            pv = why_pill({"company_id": a["company_id"]}, live_by_type(a["company_id"], public))
            if kcls == "prx":                              # a computed DPO is a proxy, said so in the row
                reason = f"{kn} proxy" + (f" \u00b7 {pv}" if pv else "")
            else:
                reason = f"{kn} \u00b7 {pv}" if pv and not pv.startswith(("SCF ", "Terms")) else (pv or kn)
            sf = q.get_account_brief(a["company_id"]).get("supplier_finance") or {}
            role = nba_mod.suggested_role(q._row(a["company_id"]), None, sf_angle=bool(sf.get("programme_disclosed") and sf.get("confirmed")))[0]
            return f"""<tr data-row data-frow tabindex="0" data-cid="{E(a['company_id'])}" data-company="{E(a['company'])}" data-hook="{E(a['hook'])}" data-source="{E(a.get('source_url') or '')}"
data-tier="{a['tier']}" data-hq="{E(a.get('hq_city') or '')}" data-local="{E(a['local_link'])}" data-inv="" title="{E(a['hook'])}">
<td class="d-chk"><input type="checkbox" checked aria-label="Include {E(a['company'])}"></td>
<td class="d-co"><span class="co-n">{avatar(a['company'])}<b>{E(a['company'])}</b>{tier_dot(a['tier'])}</span></td>
<td class="d-city sub">{E(a.get('hq_city') or 'HQ unknown')}</td>
<td class="d-why"><span class="days {kcls}" title="{E(kn + ' ' + kvs + (' (computed DPO, a balance-sheet proxy)' if kcls == 'prx' else ''))}">{E(reason)}</span></td>
<td class="d-role sub" title="{E(role)}">{E(INVITE_ROLE.get(role, role))}</td>
<td class="d-pill"><button type="button" class="ipill" data-inv="" title="Click to change invite status">To invite</button></td>
<template class="detail"><header class="p-head">{avatar(a['company'])}<div><h2>{E(a['company'])} {tier_badge(a['tier'])}</h2>
<div class="sub">{E(a.get('hq_city') or 'HQ city unknown')} · {'HQ in the city area' if a['local_link'] == 'hq_in_city_area' else 'HQ elsewhere in the country'} · {E(d['city'].title())} dinner</div></div></header>
<section class="p-key"><div><span class="p-num {kcls}">{E(kn)}</span> <span class="muted">{E(kvs)}</span></div></section>
<section><h3>Hook <span class="faint">template variable</span></h3><p><span class="lbl {'rep' if kcls == 'rep' else 'prx'}">{'Reported' if kcls == 'rep' else 'Computed proxy'}</span> {E(a['hook'])} {link(a.get('source_url'))}</p>
<button type="button" class="copy" data-copy="{E(a['hook'])}">Copy hook</button></section>
<section><dl class="p-dl"><dt>Invite</dt><dd>{E(INVITE_ROLE.get(role, role))} · {linkedin(a['company'], role)}</dd>
<dt>Links</dt><dd><a href="accounts/{E(a['company_id'])}.html">Account page</a></dd></dl></section></template></tr>"""
        groups = [("City area", [a for a in d["invite"] if a["local_link"] == "hq_in_city_area"]),
                  ("Rest of country", [a for a in d["invite"] if a["local_link"] != "hq_in_city_area"])]
        tables = "".join(f'<tbody class="dg"><tr class="dgroup"><th colspan="6">{g} <span class="faint">{len(xs)}</span></th></tr>{"".join(row(a) for a in xs)}</tbody>'
                         for g, xs in groups if xs)
        bench = "".join(f"<li>{E(x['name'])}: {E(x['bench_reason'])}. {E(x.get('figure') or '')} {link(x.get('source_url'))}</li>"
                        for x in d.get("bench_to_verify") or [])
        when = d.get("date") or "next dinner"
        blocks.append(f"""<section class="dinner" data-city="{E(d['city'])}" data-date="{E(str(d.get('date') or ''))}">
<div class="dhead"><h2>{E(d['city'].title())} <span class="faint">{E(str(when))}</span></h2>
<div class="actions"><span class="count faint" aria-live="polite"></span><button data-act="all">All</button><button data-act="none">None</button>
<button data-act="csv">Copy CSV</button><button data-act="text">Copy text</button><button data-act="inv-export" class="primary" title="Download in the dinner_attendees.csv format">Export invites</button></div></div>
<p class="dnote faint small">Companies without public payment data (e.g. insurers, or groups without UK filings) aren\u2019t listed.</p>
{('<div class="list"><table class="dl" data-list>' + tables + '</table></div>') if tables else "<p class='muted'>No account with a strong enough hook.</p>"}
{('<details class="bench"><summary>Bench: verify before use (' + str(len(d.get("bench_to_verify") or [])) + ')</summary><ul class="small">' + bench + '</ul></details>') if bench else ''}
</section>""")
    body = f"""<div class="pagehead"><div class="ph-t"><h1>Who to invite.</h1>
<div class="ph-sub">{sum(len(d['invite']) for d in dinners if d.get('found'))} accounts across {sum(1 for d in dinners if d.get('found'))} dinner cities</div></div></div>
{''.join(blocks)}
<aside id="panel" class="panel" aria-label="Details" hidden><button type="button" class="pclose" aria-label="Close details (Esc)">×</button><div class="pbody"></div></aside>
<div id="toast" class="toast" role="status" aria-live="polite" hidden></div>"""
    return page("Dinner builder", body, 0, "dinners")


SHORT_LABELS = {
    "filing_crossed_60": "crossed 60 days", "filing_worsened": "paying slower", "es_pmp_rose": "Spain: slower",
    "terms_changed_longer": "terms longer", "terms_changed_other": "terms changed", "terms_changed_shorter": "terms shorter",
    "scf_started": "SCF started", "einvoicing_started": "e-invoicing started", "cfo_change": "new CFO",
    "results_date": "results due", "einvoicing_mandate": "e-invoicing deadline (buyer)",
    "einvoicing_mandate_suppliers": "e-invoicing deadline (suppliers)", "sf_disclosed": "supplier finance (context)",
    "dinner_city": "dinner"}


TYPE_LABEL = {"filing_crossed_60": "Crossed 60d", "filing_worsened": "Paying slower", "es_pmp_rose": "ES slower",
              "terms_changed_longer": "Terms longer", "terms_changed_other": "Terms changed", "terms_changed_shorter": "Terms shorter",
              "scf_started": "SCF started", "einvoicing_started": "E-invoicing started", "einvoicing_mandate": "E-inv. deadline (buyer)",
              "einvoicing_mandate_suppliers": "E-inv. deadline (suppliers)", "sf_disclosed": "SCF in annual report", "dinner_city": "Dinner",
              "results_date": "Results due", "cfo_change": "New CFO"}


def short_label(code: str) -> str:
    return SHORT_LABELS.get(code, code.replace("_", " "))


def _ent(name: str) -> str:
    name = name.strip()
    return name.title().replace("Uk ", "UK ").replace("(Uk)", "(UK)").replace("(Gb)", "(GB)").replace(" Plc", " plc") if name.isupper() else name


def trigger_line(t: dict) -> tuple[str, str]:
    """(what changed, entity a -> b) from the trigger text; the full text stays in the tooltip."""
    tt, x = t["trigger_type"], t["text"]
    m = re.match(r"^(.*?) \(single UK entity\) (?:now )?reports (\d+) days to pay on average, (?:up from (\d+)|(\d+) more than) a year earlier", x)
    if m:
        now = int(m.group(2))
        prior = int(m.group(3)) if m.group(3) else now - int(m.group(4))
        return short_label(tt), f"{_ent(m.group(1))} {prior} → {now} days"
    m = re.search(r"rose from (\d+) to (\d+) days in (FY\d{4})", x)
    if m:
        return "Spain payment period up", f"{m.group(3)} {m.group(1)} → {m.group(2)} days"
    m = re.match(r"^(.*?) reports (?:that its payment terms changed in the period to ([\d-]+)|offering ([\w -]+?) in its latest filing)", x)
    if m:
        return short_label(tt), (f"{_ent(m.group(1))}, period to {m.group(2)}" if m.group(2) else f"{_ent(m.group(1))}, not a year earlier")
    m = re.match(r"^(From|By) ([\d]+ \w+ \d{4})", x)
    if m:
        return short_label(tt), f"{m.group(1).lower()} {m.group(2)}"
    m = re.search(r"supplier finance programme of ([A-Z]{3} [\d.,]+\w*) outstanding", x)
    if m:
        return "supplier finance disclosed", f"{m.group(1)} outstanding"
    if tt == "dinner_city":
        return "dinner shortlist", x.split(":")[0]
    return short_label(tt), (x[:90] + "…") if len(x) > 90 else x


def build_triggers(trigs: list[dict], types: dict) -> str:
    today = date.today()
    groups = {"upcoming": [], "d7": [], "d14": [], "d30": [], "older": []}
    # identical mandate events (same type, date and text across accounts) collapse into one expandable row
    mandates: dict[tuple, list] = {}
    rest = []
    for t in trigs:
        if t["trigger_type"] in ("einvoicing_mandate", "einvoicing_mandate_suppliers"):
            mandates.setdefault((t["trigger_type"], str(t.get("trigger_date"))[:10], t["text"]), []).append(t)
        else:
            rest.append(t)

    def age_group(d):
        try:
            age = (today - date.fromisoformat(d)).days
        except ValueError:
            age = 9999
        return "upcoming" if age < 0 else "d7" if age <= 7 else "d14" if age <= 14 else "d30" if age <= 30 else "older"

    for (tt, d, text), ts in mandates.items():
        nat = re.search(r"\b(German|Spanish|French|Belgian|Polish|Italian|Greek|Croatian|Portuguese|Romanian|Dutch|Irish|Danish|Swedish|Finnish|Austrian|Hungarian|Slovak|Latvian|Lithuanian|Estonian|Slovenian|Bulgarian|Czech|Luxembourg|EU)\b", text)
        title = f"{nat.group(1) + ' ' if nat else ''}e-invoicing mandate{' (suppliers)' if tt == 'einvoicing_mandate_suppliers' else ''}"
        when = trigger_line(ts[0])[1]
        accts = " ".join((f'<a href="accounts/{E(t["company_id"])}.html">{E(t["company"])}</a>' if t["company_id"] in ACCOUNT_IDS else f'<span>{E(t["company"])}</span>')
                         for t in sorted(ts, key=lambda t: t["company"]))
        groups[age_group(d)].append(f"""<details class="tgrp" data-frow data-type="{E(tt)}" data-date="{E(d)}"><summary class="trow" title="{E(text)}">
<span class="t-date">{E(d[5:] if d[:4] == str(today.year) else d)}</span>
<span class="t-line"><b>{E(title)}</b><span class="sep">·</span><span class="t-what">{len(ts)} account{'' if len(ts) == 1 else 's'}</span><span class="sep">·</span><span class="t-chg">{E(when)}</span></span>
{icon_link(ts[0].get('evidence_url'))}</summary><div class="tg-list">{accts}</div></details>""")
    for t in rest:
        d = str(t.get("trigger_date"))[:10]
        g = age_group(d)
        what, change = trigger_line(t)
        tt = t["trigger_type"]
        approx = ' <span class="faint" title="Date is approximate">approx.</span>' if t.get("date_is_approximate") is True else ""
        acct = (f'<a class="co-l" href="accounts/{E(t["company_id"])}.html"><b>{E(t["company"])}</b></a>' if t["company_id"] in ACCOUNT_IDS
                else f'<b>{E(t["company"])}</b>')
        binds = (" (binds the buyer)" if tt == "einvoicing_mandate" else " (binds its small suppliers)" if tt == "einvoicing_mandate_suppliers" else "")
        groups[g].append(f"""<div class="trow" data-frow data-type="{E(tt)}" data-date="{E(d)}" title="{E(t['text'])}">
<span class="t-date">{E(d[5:] if d[:4] == str(today.year) else d)}{approx}</span>
<span class="t-line">{acct}<span class="sep">·</span><span class="t-what">{E(what + binds)}</span><span class="sep">·</span><span class="t-chg">{E(change)}</span></span>
{icon_link(t.get('evidence_url'))}</div>""")
    names = {"upcoming": "Upcoming", "d7": "Last 7 days", "d14": "8\u201314 days", "d30": "15\u201330 days", "older": "Older"}
    secs = "".join(f'<section class="tsec" data-group="{k}"><h3 class="tgroup">{names[k]} <span class="faint">{len(v)}</span></h3><div class="list">{"".join(v)}</div></section>'
                   for k, v in groups.items() if v)
    opts = "".join(f'<option value="{E(k)}" title="{E(v)}">{E(TYPE_LABEL.get(k, v))}</option>' for k, v in types.items() if any(t["trigger_type"] == k for t in trigs))
    body = f"""<div class="pagehead"><div class="ph-t"><h1>What changed.</h1>
<div class="ph-sub">Live public triggers from statutory filings and annual reports</div></div>
<div class="ph-bar"><div class="filters" data-target="#trig"><label>Type <select data-filter="type" data-hide-on-all="dinner_city"><option value="">All but dinner</option>{opts}</select></label>
<label>When <select data-window><option value="30">Last 30 days</option><option value="90">Last 90 days</option><option value="up">Upcoming</option><option value="">Any date</option></select></label>
<span class="count faint" aria-live="polite"></span></div></div></div>
<div id="trig">{secs}</div>"""
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
<section class="card md"><details class="full"><summary>Show full methodology</summary>
<p class="small muted">Rendered from <code>docs/methodology.md</code> at build time.</p>{h}</details></section>"""
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
            global DEFAULT_SCHEME
            DEFAULT_SCHEME = str(json.loads(THEME_LOCAL.read_text()).get("default_scheme") or "")
    print("theme: " + ("local override (config/theme.local.json)" if THEME_ON else "neutral default"))

    all_t, private, public, queue, top = load()
    types = all_t["types"]
    public_keys = {(t["company_id"], t["text"]) for t in public}

    cal = q.dinner_calendar()
    dinners = [api.dinner_builder(d["city"], demo=False) for d in cal]
    dinner_ids = [a["company_id"] for d in dinners if d.get("found") for a in d["invite"]]
    today_s0 = date.today().isoformat()
    newest = sorted((t for t in public if t.get("is_live") and str(t.get("trigger_date"))[:10] <= today_s0
                     and t["trigger_type"] not in ("dinner_city", "einvoicing_mandate", "einvoicing_mandate_suppliers")),
                    key=lambda t: (str(t.get("trigger_date")), t.get("strength") or 0), reverse=True)[:8]
    TICKER[:] = [{"company_id": t["company_id"], "company": t["company"], "text": t["text"], "what": trigger_line(t)[0], "change": trigger_line(t)[1],
                  "key": f'{str(t.get("trigger_date"))[:10]}|{t["company_id"]}'} for t in newest]
    dinner_ids += [t["company_id"] for t in TICKER]
    ids = list(dict.fromkeys([a["company_id"] for a in queue["accounts"]] + [t["company_id"] for t in top["targets"]] + dinner_ids))
    names = {**{t["company_id"]: t["company"] for t in TICKER}, **{a["company_id"]: a["company"] for d in dinners if d.get("found") for a in d["invite"]},
             **{t["company_id"]: t["name"] for t in top["targets"]}, **{a["company_id"]: a["company"] for a in queue["accounts"]}}
    cc = q.companies().set_index("company_id")
    SEARCH[:] = sorted(((names[c], c, f"{cc.loc[c, 'country']} \u00b7 T{int(cc.loc[c, 'priority_tier'])}" if c in cc.index else "") for c in ids), key=lambda x: x[0].lower())
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

    feed = [t for t in public if t.get("is_live")]
    today_s = date.today().isoformat()
    past = sorted([t for t in feed if str(t.get("trigger_date")) <= today_s], key=lambda t: (str(t.get("trigger_date")), t.get("strength") or 0), reverse=True)
    future = sorted([t for t in feed if str(t.get("trigger_date")) > today_s], key=lambda t: str(t.get("trigger_date")))
    feed = past + future

    (DIST / "index.html").write_text(build_queue(queue, types, public))
    (DIST / "dinners.html").write_text(build_dinners(dinners, public))
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
