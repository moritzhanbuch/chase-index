"""Build the internal GTM workspace into workspace/dist/.

Static HTML/CSS/JS, no framework, no network calls. Data comes only from chase.gtm.api and chase.query (read-only).

Privacy guards (public data only):
- demo=False everywhere (never the synthetic bring-your-own-data set)
- keys that can carry names of individuals or private CRM data are dropped before anything is written
- triggers with private_source == True are dropped, including their text inside the queue's why_now summary
- nothing under data/private/ is read here

Run: .venv/bin/python workspace/build.py   (or: make workspace)
"""
from __future__ import annotations

import html
import json
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
<link rel="stylesheet" href="{up}assets/style.css"></head>
<body><header class="top"><div class="wrap"><a class="brand" href="{up}index.html">Chase Index <span>workspace</span></a>
<nav>{navh}</nav></div></header>
<main class="wrap">{body}</main>
<footer class="wrap foot"><p>{DISCLAIMER}</p>
<p class="muted">Internal GTM workspace built {date.today().isoformat()} from public data only. Contains internal scoring: do not publish.
Reported = statutory filings. Computed proxy = derived from financial statements. Estimate = model output with stated assumptions.</p></footer>
<script src="{up}assets/app.js"></script></body></html>"""


def tier_badge(t) -> str:
    return f'<span class="tier t{E(str(t))}">T{E(str(t))}</span>' if t is not None else ""


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
def build_queue(queue: dict, types: dict) -> str:
    rows, countries, plays = [], set(), set()
    for a in queue["accounts"]:
        countries.add(a.get("country") or "")
        plays.add(a.get("play") or "")
        tt = [x for x in (a.get("why_now_types") or "").split("|") if x]
        why = "".join(f"<li>{E(s)}</li>" for s in a["why_now"].split(" | "))
        thin = ' <span class="flag" title="UK invoice value under 1% of group revenue">thin evidence</span>' if a.get("thin_evidence") else ""
        rows.append(f"""<tr data-country="{E(a.get('country') or '')}" data-play="{E(a.get('play') or '')}" data-tier="{E(str(a.get('tier')))}">
<td class="num">{a['queue_rank']}</td>
<td><a href="accounts/{E(a['company_id'])}.html"><strong>{E(a['company'])}</strong></a> {tier_badge(a.get('tier'))}{thin}
<div class="muted small">{E(a.get('country') or '')} · {E(a.get('sector') or '')} · priority {num(a.get('queue_priority'), 1)} ({E(a.get('priority_explained') or '')})</div></td>
<td><span class="play">{E(PLAY_LABEL.get(a.get('play'), a.get('play') or ''))}</span><div class="small muted">Who: {E(a.get('who_role') or 'n/a')}</div></td>
<td class="small"><p class="ev"><span class="lbl rep">Reported</span> {E(a.get('evidence') or '')} {link(a.get('evidence_url'))}</p>
<ul class="why">{why}</ul>{('<div class="small">' + link(a.get('why_now_url'), 'trigger source') + '</div>') if a.get('why_now_url') else ''}
<div class="chips">{''.join(f'<span class="chip" title="{E(types.get(x, x))}">{E(short_label(x))}</span>' for x in tt)}</div></td></tr>""")
    sel = lambda name, vals, lab: (f'<label>{lab} <select data-filter="{name}"><option value="">All</option>'
                                   + "".join(f'<option value="{E(v)}">{E(PLAY_LABEL.get(v, v))}</option>' for v in sorted(vals) if v)
                                   + "</select></label>")
    body = f"""<h1>This week's queue <span class="muted">week {E(queue['week'])}</span></h1>
<p class="lede">{queue['count']} accounts to work this week, out of {queue['eligible_accounts']} eligible. Each row: the play, who to reach (by role),
the reported evidence with its source, and why now. Openers are on the account page. Drafts only: a human sends everything.</p>
<div class="filters" data-target="#queue">{sel('country', countries, 'Country')}{sel('play', plays, 'Play')}{sel('tier', {'1', '2', '3'}, 'Tier')}
<span class="count muted" aria-live="polite"></span></div>
<div class="tablewrap"><table id="queue" class="data"><thead><tr><th>#</th><th>Account</th><th>Play</th><th>Evidence and why now</th></tr></thead>
<tbody>{''.join(rows)}</tbody></table></div>
<p class="small muted">{E(queue['note'].replace(' who_named is present only when local private data exists.', ''))}
Priority boosts from triggers are computed upstream and may include signals not shown here.</p>"""
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
    if DIST.exists():
        shutil.rmtree(DIST)
    (DIST / "assets").mkdir(parents=True)
    for f in ("style.css", "app.js"):
        shutil.copy2(ROOT / "workspace" / "static" / f, DIST / "assets" / f)

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
