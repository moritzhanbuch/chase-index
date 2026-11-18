"""Sales assets: account one-pagers (HTML + PDF) and dinner-invite hooks per city.

  python -m chase.assets.build              # everything
  python -m chase.assets.build --no-pdf     # skip PDF rendering (no browser needed)
  python -m chase.assets.build --company "Nestle"   # one extra one-pager on demand

Numbers come only from data/processed/companies.parquet via chase.query. The suggested first
conversation is a template (conversation_angle) using the same rules as the queue opener in
chase.gtm.nba, so every account follows one logic. The "what would change" block comes from
outputs/one_pagers/copy.json when an entry exists (written by the `assets` agent, grounded in the row and in an agent-to-agent payments team's
publicly described product); otherwise from the deterministic fallback below.
"""
from __future__ import annotations

import html
import json
import sys
from datetime import date
from pathlib import Path

import pandas as pd

from chase import query as q

ROOT = q.ROOT
OUT = ROOT / "outputs"
N_ONE_PAGERS = 20
UK_MEDIAN = 32   # DBT official statistics 2025: median time to pay, large UK businesses
UK_MEDIAN_URL = "https://www.gov.uk/government/statistics/large-businesses-payment-practices-and-performance-statistics-2025"

CSS = """
@page { size: A4; margin: 0; }
* { box-sizing: border-box; }
body { margin: 0; font-family: -apple-system, "Helvetica Neue", Helvetica, Arial, sans-serif; color: #16202a; background: #fff; }
.page { width: 210mm; min-height: 297mm; padding: 13mm 14mm 10mm; position: relative; }
header { display: flex; justify-content: space-between; align-items: flex-start; border-bottom: 2px solid #16202a; padding-bottom: 7px; }
h1 { font-size: 23px; margin: 0 0 2px; letter-spacing: -0.3px; }
.sub { font-size: 10.5px; color: #55616d; }
.tier { font-size: 10px; font-weight: 700; letter-spacing: .6px; text-transform: uppercase; padding: 4px 9px; border-radius: 3px; background: #16202a; color: #fff; white-space: nowrap; }
.kicker { font-size: 9px; font-weight: 700; letter-spacing: .9px; text-transform: uppercase; color: #9a4a00; margin: 13px 0 5px; }
.grid { display: grid; grid-template-columns: 1.15fr 1fr; gap: 14px; }
.big { display: flex; gap: 14px; align-items: flex-end; }
.num { font-size: 50px; font-weight: 700; line-height: .95; letter-spacing: -1.5px; white-space: nowrap; flex: none; }
.num small { font-size: 13px; font-weight: 600; letter-spacing: 0; color: #55616d; }
.cmp { font-size: 11px; color: #55616d; padding-bottom: 5px; flex: 1; }
table { border-collapse: collapse; width: 100%; font-size: 10.5px; }
td, th { padding: 3px 0; border-bottom: 1px solid #e3e7eb; text-align: left; vertical-align: top; }
td.r, th.r { text-align: right; font-variant-numeric: tabular-nums; padding-left: 8px; padding-right: 8px; white-space: nowrap; }
th { font-size: 9px; color: #55616d; font-weight: 600; text-transform: uppercase; letter-spacing: .4px; }
.bar { height: 9px; background: #16202a; border-radius: 1px; }
.barwrap { position: relative; height: 9px; background: #f0f2f4; }
.mark { position: absolute; top: -3px; bottom: -3px; width: 1.5px; background: #c2410c; }
.tag { display: inline-block; font-size: 8.5px; font-weight: 700; letter-spacing: .5px; text-transform: uppercase; padding: 1.5px 5px; border-radius: 2px; }
.reported { background: #e6f0e8; color: #1f5a2c; } .estimate { background: #fdf0d9; color: #8a4b00; } .proxy { background: #e8ecf5; color: #2c3f77; }
.box { border: 1px solid #d9dee3; border-radius: 4px; padding: 9px 11px; }
.est { display: grid; grid-template-columns: repeat(3, 1fr); gap: 6px; margin-top: 6px; }
.est div { background: #fdf7ea; padding: 6px 8px; border-radius: 3px; }
.est b { display: block; font-size: 15px; } .est span { font-size: 9px; color: #6b5a3a; text-transform: uppercase; letter-spacing: .4px; }
ul { margin: 0; padding-left: 15px; } li { font-size: 11px; line-height: 1.42; margin-bottom: 4px; }
p { font-size: 11px; line-height: 1.45; margin: 0 0 5px; }
a { color: #16202a; } .fine { font-size: 8.5px; color: #6a7580; line-height: 1.4; }
footer { position: absolute; left: 14mm; right: 14mm; bottom: 8mm; border-top: 1px solid #d9dee3; padding-top: 5px; }
.angle { background: #16202a; color: #fff; padding: 10px 12px; border-radius: 4px; } .angle p { color: #fff; margin: 0; font-size: 11.5px; }
.angle .kicker { color: #f5b971; margin-top: 0; }
"""


def esc(s) -> str:
    return html.escape(str(s)) if s is not None else ""


def money(v, cur="") -> str:
    if v is None:
        return "n/a"
    a = abs(v)
    s = f"{v/1e9:.1f}bn" if a >= 1e9 else f"{v/1e6:.0f}m" if a >= 1e6 else f"{v/1e3:.0f}k"
    sym = {"GBP": "£", "EUR": "€", "USD": "$", "CHF": "CHF "}.get(cur, (cur + " ") if cur else "")
    return f"{sym}{s}"


def nice(name: str) -> str:
    from chase.resolve.universe import tidy_name
    t = tidy_name(name)
    for a_, b_ in (("Uk", "UK"), ("Ge ", "GE "), ("(Uk)", "(UK)"), ("Nv", "NV"), ("Llp", "LLP"), ("Ltd.", "Ltd"), ("Usa", "USA"), ("Emea", "EMEA")):
        t = " ".join(b_.strip() if w == a_.strip() else w for w in t.split(" "))
    return t


def money2(v, cur="") -> str:
    """Two significant figures, so low / base / high do not collapse into the same rounded number."""
    if v is None:
        return "n/a"
    sym = {"GBP": "£", "EUR": "€", "USD": "$", "CHF": "CHF "}.get(cur, (cur + " ") if cur else "")
    for div, suf in ((1e9, "bn"), (1e6, "m"), (1e3, "k")):
        if abs(v) >= div:
            x = v / div
            return f"{sym}{x:.1f}{suf}" if x < 10 else f"{sym}{x:.0f}{suf}"
    return f"{sym}{v:.0f}"


def pct(v) -> str:
    return "" if v is None else f"{v:.0f}%"


def fallback_copy(b: dict) -> dict:
    """Deterministic copy, used when no agent-written entry exists. Product statements are limited to
    what agent-to-agent payment products describe publicly."""
    uk = b["payment_profile"]["reported"].get("uk")
    es = b["payment_profile"]["reported"].get("spain")
    changes = []
    if uk and (uk.get("pct_invoices_paid_late_mean") or 0) >= 15:
        changes.append(f"{uk['pct_invoices_paid_late_mean']:.0f}% of UK invoices are paid after the agreed terms. An agent on the AP side "
                       "matches invoice, PO and proof of delivery and clears disputes with the supplier's agent before the due date, "
                       "and the ERP posts only after human approval.")
    if uk and uk["entities_n"] >= 3:
        changes.append(f"{uk['entities_n']} UK legal entities report separately. Agents work the long tail of suppliers that AP teams "
                       "rarely get to, across entities, and email suppliers that are not on the network yet.")
    days = (uk or {}).get("avg_days_to_pay_mean_of_entities") or (es or {}).get("pmp_days") or (b["payment_profile"].get("computed_proxy") or {}).get("dpo_days")
    if days and days > 40:
        changes.append("Long payment days are leverage that can be priced. Buyer and supplier agents negotiate early payment against a discount, "
                       "inside guardrails the CFO sets (minimum APR, maximum discount, blocklists).")
    changes.append("Pricing is outcome-based: discount captured and cash that moved. If nothing happens, nothing is paid.")
    angle = (f"Open with the public number, not a product pitch: \"{b['hook']}\" Then ask who owns supplier payment timing today, "
             "treasury or AP, and what share of invoices the team actually chases.")
    return {"what_changes": changes[:3], "angle": angle}


UK_TABLE_ALL_MAX = 8   # show every UK entity up to this many; above it, the 5 slowest


def conversation_angle(b: dict, r) -> str:
    """Suggested first conversation, from the same rules as the queue opener (chase.gtm.nba): who to ask for
    (nba.suggested_role), then the framing. Late share 25-75% is a process topic (matching and approvals);
    long reported days with few late invoices are a terms and working-capital topic; otherwise an open
    question. A disclosed supplier finance programme adds the reach-and-terms question and drops the
    early-cash line. Year-on-year changes read "up N days to X days"."""
    from chase.gtm import nba
    from chase.resolve.uk_rollup import EXTREME_YOY_JUMP
    sf0 = b.get("supplier_finance") or {}
    # same rule as the queue: a confirmed programme makes it a treasury conversation
    sf_angle = bool(sf0.get("programme_disclosed") and sf0.get("confirmed"))
    role, _ = nba.suggested_role(r, None, sf_angle=sf_angle)
    basis = b["scores"]["pain_basis"]
    pp = b["payment_profile"]
    uk, es, dpo = pp["reported"].get("uk"), pp["reported"].get("spain"), pp.get("computed_proxy")
    short = q.short_name(b["name"])
    out = [f"Ask for the {role[0].lower() + role[1:]}."]
    days = None
    if basis == "uk_reported":
        days, n = uk["avg_days_to_pay_mean_of_entities"], uk["entities_n"]
        if n == 1:
            ev = f"{q._poss(short)} UK entity pays in {days:.0f} days on average (UK median {UK_MEDIAN})"
        else:
            kind = "weighted by invoice value" if uk.get("aggregation") == "invoice_value_weighted_mean" else "unweighted"
            ev = f"{q._poss(short)} UK entities pay in {days:.0f} days on average ({kind}, {n} entities; UK median {UK_MEDIAN})"
        # same rule as the trigger model: a jump this large is a re-filing or entity change to verify, not a talking point
        movers = [e for e in uk["entities"] if e.get("trend_days_yoy") is not None and 5 <= e["trend_days_yoy"] < EXTREME_YOY_JUMP
                  and e["avg_days_to_pay"] - e["trend_days_yoy"] > 0 and e["avg_days_to_pay"] / (e["avg_days_to_pay"] - e["trend_days_yoy"]) < 4]
        if movers:
            m = max(movers, key=lambda e: e["trend_days_yoy"])
            ev += (f", and {nice(m['name'])} is up {m['trend_days_yoy']:.0f} days to {m['avg_days_to_pay']:.0f} days year on year"
                   if n > 1 else f", up {m['trend_days_yoy']:.0f} days to {m['avg_days_to_pay']:.0f} days year on year")
    elif basis == "es_reported":
        days, prior = es["pmp_days"], es.get("prior_year_pmp_days")
        ev = (f"{q._poss(short)} Spanish payment period is up {days - prior:.0f} days to {days:.0f} days in FY{int(es['fiscal_year'])}"
              if prior is not None and days - prior >= 1 else f"{q._poss(short)} Spanish payment period is {days:.0f} days in FY{int(es['fiscal_year'])}")
        ev += " (legal maximum per payment 60)"
    else:
        days, prior = dpo["dpo_days"], dpo.get("prior_year_dpo_days")
        ev = (f"{q._poss(short)} computed DPO (a balance-sheet proxy) is up {days - prior:.0f} days to {days:.0f} days"
              if prior is not None and days - prior >= 1 else f"{q._poss(short)} computed DPO (a balance-sheet proxy) is {days:.0f} days")
        ev += f" (sector median {dpo['sector_median_dpo_days']:.0f})"
    out.append(f"Open with the public number: {ev}.")

    sf = b.get("supplier_finance") or {}
    ff = b.get("uk_filing_features") or {}
    sf_line = None
    if sf.get("programme_disclosed") and sf.get("confirmed"):
        amt = f" ({money(sf['obligations_outstanding'], sf['currency'])} outstanding at {str(sf['period_end'])[:7]})" if sf.get("obligations_outstanding") else ""
        sf_line = f"The annual report discloses a supplier finance programme{amt}: ask which suppliers it reaches, and did terms get longer when the programme came in?"
    elif basis == "uk_reported" and (ff.get("scf_offered_n") or 0) > 0:
        sf_line = ("UK entities report offering supply chain finance: ask which suppliers it reaches, "
                   "and did terms get longer when the programme came in?")
    late = uk.get("pct_invoices_paid_late_mean") if basis == "uk_reported" else None
    within = es.get("pct_paid_within_legal_max_by_value") if basis == "es_reported" else None
    if late is not None and 25 <= late <= 75:           # nba: cold_email_late
        if not sf_angle:                                # with a confirmed programme the SF question leads, asked of treasury
            out.append(f"With {late:.0f}% of invoices paid after the agreed terms, start with process: what stops an invoice from being "
                       "approved on time (a missing PO match, an unconfirmed delivery, a supplier waiting on an answer)?")
    elif basis in ("uk_reported", "es_reported") and (days or 0) >= 55 and (within is None or within >= 60):   # nba: cold_email_terms
        low = f"only {late:.0f}% of invoices are paid late" if late is not None else "few invoices miss the legal limit"
        out.append(f"Since {low}, the long days are agreed terms: a working-capital topic. Ask whether they are a deliberate lever"
                   + ("." if sf_line else ", and what earlier cash would be worth to suppliers inside limits treasury sets."))
    else:                                               # nba: cold_email_generic
        out.append("Ask how much of the number is deliberate terms and how much is invoices stuck between AP and the supplier.")
    if sf_line:
        out.append(sf_line)
    return " ".join(out)


def render_one_pager(company: str, copy: dict | None = None) -> tuple[str, str]:
    b = q.get_account_brief(company)
    r = q._row(company)
    hv = q.hook_variables(r)
    b["hook"] = hv.get("hook") or ""
    copy = copy or fallback_copy(b)
    uk = b["payment_profile"]["reported"].get("uk")
    es = b["payment_profile"]["reported"].get("spain")
    dpo = b["payment_profile"].get("computed_proxy")
    rev = b["revenue"]
    sub = " · ".join(x for x in [b["sector"].replace("_", " ").title(), f"HQ {b['hq_city']}, {b['country']}" if b["hq_city"] else f"HQ {b['country']}",
                                 f"Revenue {money(rev['amount'], rev['currency'])} ({str(rev['period_end'])[:4]}{', Wikidata, may be out of date' if rev['source_type'] == 'wikidata' and str(rev['period_end'])[:4] < '2025' else ''})" if rev["amount"] else None] if x)

    # ---- evidence block
    if b["scores"]["pain_basis"] == "uk_reported":
        days = uk["avg_days_to_pay_mean_of_entities"]
        tag = '<span class="tag reported">Reported · UK statutory filings</span>'
        wtd = ", weighted by invoice value" if uk.get("aggregation") == "invoice_value_weighted_mean" and uk["entities_n"] > 1 else ""
        cmp_ = f"days to pay on average across {uk['entities_n']} UK entit{'y' if uk['entities_n'] == 1 else 'ies'}{wtd}<br>UK large-business median: <a href=\"{UK_MEDIAN_URL}\">{UK_MEDIAN} days</a>"
        rows = "".join(
            f"<tr><td><a href=\"{esc(e['source_url'])}\">{esc(nice(e['name']))}</a></td><td class=r>{e['avg_days_to_pay']:.0f}</td>"
            f"<td class=r>{pct(e['pct_paid_late'])}</td>"
            f"<td style='width:34%'><div class=barwrap><div class=bar style='width:{min(100, e['avg_days_to_pay'] / 1.2):.0f}%'></div>"
            f"<div class=mark style='left:{UK_MEDIAN / 1.2:.0f}%'></div></div></td></tr>"
            for e in (uk["entities"] if uk["entities_n"] <= UK_TABLE_ALL_MAX else uk["entities"][:5]))
        facts = [("Invoices paid late", f"{uk['pct_invoices_paid_late_mean']:.0f}%" if uk["pct_invoices_paid_late_mean"] is not None else "n/a"),
                 ("Invoices paid after 60 days", f"{uk['pct_invoices_paid_over_60_days_mean']:.0f}%" if uk["pct_invoices_paid_over_60_days_mean"] is not None else "n/a"),
                 ("Change vs a year earlier", f"{uk['trend_days_year_on_year_mean']:+.1f} days" if uk["trend_days_year_on_year_mean"] is not None else "n/a"),
                 ("Reporting periods", f"{uk['period']['start']} to {uk['period']['end']}")]
        detail = (f"<table><tr><th>UK entity (link = official report)</th><th class=r>Days</th><th class=r>Late</th><th>vs median (red line)</th></tr>{rows}</table>")
        if uk["entities_n"] > UK_TABLE_ALL_MAX:
            detail += f"<p class=fine>The 5 slowest of {uk['entities_n']} entities are shown. All are in the group figure.</p>"
        scope = (f"UK legal entities only, matched to the group with confidence {uk['entity_match_confidence_min']:.2f} or higher. "
                 "Not a statement about the group's global payment behaviour.")
        if uk.get("entities_left_out_of_group_figures_as_extreme"):
            scope += (" Left out of the group figures as extreme values to verify: "
                      + nice(str(uk["entities_left_out_of_group_figures_as_extreme"]).replace("|", "; ")) + ".")
    elif b["scores"]["pain_basis"] == "es_reported":
        days = es["pmp_days"]
        tag = '<span class="tag reported">Reported · Spanish annual accounts</span>'
        cmp_ = f"days: statutory average supplier payment period (PMP), FY{int(es['fiscal_year'])}<br>Legal maximum per payment in Spain: 60 days"
        facts = [("Prior year PMP", f"{es['prior_year_pmp_days']:.0f} days" if es["prior_year_pmp_days"] is not None else "n/a"),
                 ("Ratio of paid operations", f"{es['ratio_paid_days']:.0f} days" if es["ratio_paid_days"] is not None else "n/a"),
                 ("Ratio of pending operations", f"{es['ratio_pending_days']:.0f} days" if es["ratio_pending_days"] is not None else "n/a"),
                 ("Paid within the legal maximum (by value)", f"{es['pct_paid_within_legal_max_by_value']:.0f}%" if es["pct_paid_within_legal_max_by_value"] is not None else "n/a")]
        detail = f"<p class=fine>Source: <a href=\"{esc(es['source_url'])}\">annual report filing</a>. Extracted by two independent extractors that agreed, or adjudicated by a third reader.</p>"
        scope = "Covers the group's Spanish entities as disclosed under Ley 15/2010. Not a statement about global payment behaviour."
    else:
        days = dpo["dpo_days"]
        tag = '<span class="tag proxy">Computed proxy · no reported payment data</span>'
        cmp_ = f"days payable outstanding (computed DPO), FY{dpo['fiscal_year']}<br>Sector median in this dataset: {dpo['sector_median_dpo_days']:.0f} days"
        facts = [("Prior year DPO", f"{dpo['prior_year_dpo_days']:.0f} days" if dpo["prior_year_dpo_days"] is not None else "n/a"),
                 ("Payables basis", dpo["payables_basis"] or "n/a"), ("Cost basis", dpo["cost_basis"] or "n/a")]
        detail = f"<p class=fine>Source: <a href=\"{esc(dpo['source_url'])}\">XBRL financial statements</a>. DPO = trade payables / cost of sales x 365.</p>"
        scope = "A balance-sheet proxy. It is not the same as reported days to pay and includes non-invoice effects."
    # ---- Phase 12: UK filing fields and supplier finance (reported facts, each with a source link)
    ff = b.get("uk_filing_features") or {}
    sf = b.get("supplier_finance") or {}
    extra = []
    if ff.get("late_because_of_dispute_pct") is not None and ff["late_because_of_dispute_pct"] >= 5:   # 10% is the signal threshold; 5% is worth a line
        extra.append(("Paid late because of a dispute (UK)", f"{ff['late_because_of_dispute_pct']:.0f}% of invoices", ff.get("late_because_of_dispute_url")))
    if ff.get("terms_changed_longer_n"):
        extra.append(("UK payment terms changed", "towards longer terms", ff.get("terms_changed_longer_url")))
    if sf.get("programme_disclosed") and sf.get("confirmed"):
        amt = f"{money(sf['obligations_outstanding'], sf['currency'])} outstanding" if sf.get("obligations_outstanding") else "disclosed, no amount"
        extra.append((f"Supplier finance programme (FY to {str(sf['period_end'])[:7]})", amt, sf.get("source_url")))
    elif sf.get("programme_disclosed"):
        extra.append(("Supplier finance programme", "found by one reader, unconfirmed", sf.get("source_url")))
    facts_html = "".join(f"<tr><td>{esc(k)}</td><td class=r><b>{esc(v)}</b></td></tr>" for k, v in facts)
    src_link = lambda u: f' <a href="{esc(u)}">source</a>' if u else ""
    facts_html += "".join(f"<tr><td>{esc(k)}{src_link(u)}</td><td class=r><b>{esc(v)}</b></td></tr>" for k, v, u in extra)

    # ---- estimates
    est = b["estimates"]
    blocks = []
    for key, title in (("uk_scope", "UK foothold (reported invoice value)"), ("group_proxy", "Group (computed DPO, a proxy)")):
        e = est.get(key)
        if not e or e["early_payment_discount_opportunity"]["base"] is None:
            continue
        d = e["early_payment_discount_opportunity"]
        base_label = "annualised UK invoice value" if key == "uk_scope" else "group cost of sales"
        blocks.append(
            f"<p style='margin-top:6px'><b>{title}</b> <span class=fine>· {money(e.get('annual_payments') or e.get('spend_proxy'), e['currency'])} {base_label} at "
            f"{e['days_used']:.0f} days · {money(e['supplier_cash_beyond_30_days'], e['currency'])} outstanding beyond 30 days</span></p>"
            f"<div class=est><div><span>Low</span><b>{money2(d['low'], e['currency'])}</b></div><div><span>Base</span><b>{money2(d['base'], e['currency'])}</b></div>"
            f"<div><span>High</span><b>{money2(d['high'], e['currency'])}</b></div></div>")
    sh = b.get("uk_invoice_value_share_of_group_revenue")
    if sh is not None and est.get("uk_scope"):
        blocks.append(f"<p class=fine style='margin-top:6px'>The UK entities' invoice value is about {sh:.0%} of group revenue: "
                      "this is the size of the first conversation, not of the account.</p>" if sh >= 0.005 else
                      "<p class=fine style='margin-top:6px'>The UK entities' invoice value is under 1% of group revenue.</p>")
    late_ = (uk or {}).get("pct_invoices_paid_late_mean")
    if late_ is not None and late_ >= 30:
        blocks.append(f"<p class=fine style='margin-top:6px'>With {late_:.0f}% of UK invoices paid after terms, faster matching and approval "
                      "come first: an early-payment discount needs an approved invoice.</p>")
    if est.get("uk_scope_note"):
        blocks.append(f"<p class=fine style='margin-top:6px'>{esc(est['uk_scope_note'])}</p>")
    if "group_proxy" not in est:
        blocks.append("<p class=fine style='margin-top:6px'>No group-level estimate: local reported days are not applied to global spend, "
                      "and there is no clean group-level figure for this company.</p>")
    sc = est["assumptions"]["scenarios"]
    est_html = "".join(blocks)
    est_note = (f"Gross discount the buyer could capture per year by paying eligible invoices early = spend x share eligible x annualised rate x days accelerated / 365. "
                f"Low {sc['low']['share_eligible']:.0%} of spend at {sc['low']['annualised_rate']:.0%}, base {sc['base']['share_eligible']:.0%} at {sc['base']['annualised_rate']:.0%}, "
                f"high {sc['high']['share_eligible']:.0%} at {sc['high']['annualised_rate']:.0%}; payment moved to day {est['assumptions']['early_pay_day']}, "
                f"capped at {est['assumptions']['max_days_accelerated']} days. Before the buyer's own funding cost. Existing supply chain finance is not netted out. "
                f"Illustrative, not a forecast. Inputs: config/assumptions.yaml.")

    TRIGGERS = {"trend_worsening", "new_evidence", "finance_hiring", "press", "terms_changed_longer", "scf_started", "einvoicing_started"}
    allsig = b["why_now_signals"]
    trig = [x for x in allsig if x["type"] in TRIGGERS][:3]
    ctx = [x for x in allsig if x["type"] not in TRIGGERS][:2]
    li = lambda x: f"<li>{esc(x['text'])}. <a href=\"{esc(x['url'])}\">source</a></li>"
    sig_html = "".join(li(x) for x in trig) or "<li>No dated trigger in the data. Lead with the evidence itself.</li>"
    ctx_html = ("<div class=kicker>Standing facts</div><ul>" + "".join(li(x) for x in ctx) + "</ul>") if ctx else ""

    # ---- how the score was built (for the reader who wants to check it)
    fp, pp_ = sc_parts = b["scores"]["fit_parts"], b["scores"]["pain_parts"]
    fit_txt = ", ".join(f"{k.replace('_', ' ')} {v:.0f}" for k, v in fp.items())
    pain_txt = ", ".join(f"{k.replace('_', ' ')} {v:.0f}" if k != "uk_materiality_factor" and "ratio" not in k and "factor" not in k
                         else f"{k.replace('_', ' ')} {v}" for k, v in pp_.items())
    check_rows = [("Fit " + f"{b['scores']['fit']:.0f}", fit_txt), ("Pain " + f"{b['scores']['pain']:.0f}", pain_txt)]
    if uk:
        check_rows.append(("Group link", f"{uk['entities_n']} UK entit{'y' if uk['entities_n'] == 1 else 'ies'} linked by {str(uk['entity_match_methods']).replace('|', ', ').replace('_', ' ')}; "
                           f"lowest link confidence {uk['entity_match_confidence_min']:.2f}. Simple mean of the entities (unweighted): {uk['avg_days_to_pay_simple_mean']:.0f} days."))
    check_html = "".join(f"<tr><td style='width:16%'><b>{esc(k)}</b></td><td>{esc(v)}</td></tr>" for k, v in check_rows)
    changes_html = "".join(f"<li>{esc(c)}</li>" for c in copy["what_changes"])
    sc_ = b["scores"]
    body = f"""<div class=page>
<header><div><h1>{esc(b['name'])}</h1><div class=sub>{esc(sub)}</div></div>
<div style="text-align:right"><span class=tier>Tier {b['priority_tier']} · rank {b['rank']}</span>
<div class=sub style="margin-top:5px">Fit {sc_['fit']:.0f} · Pain {sc_['pain']:.0f} · Signal {sc_['signal']:.0f}</div></div></header>

<div class=kicker>The evidence</div>
<div class=grid><div>
  <div class=big><div class=num>{days:.0f}<small> days</small></div><div class=cmp>{cmp_}</div></div>
  <div style="margin:6px 0 7px">{tag}</div>{detail}
</div><div><table>{facts_html}</table><p class=fine style="margin-top:6px">{esc(scope)}</p></div></div>

<div class=grid style="margin-top:4px"><div>
  <div class=kicker>Why now</div><ul>{sig_html}</ul>{ctx_html}
  <div class=kicker>What an agent on both sides would change here</div><ul>{changes_html}</ul>
</div><div>
  <div class=kicker>Size of the prize <span class="tag estimate">Estimate</span></div>
  <div class=box>{est_html}<p class=fine style="margin-top:7px">{esc(est_note)}</p></div>
</div></div>

<div class=angle style="margin-top:12px"><div class=kicker>Suggested first conversation</div><p>{esc(conversation_angle(b, r))}</p></div>

<div class=kicker>How the score was built</div>
<table class=fine style="font-size:9.5px">{check_html}</table>
<p class=fine style="margin-top:4px">Scores are deterministic formulas (docs/methodology.md). Weights and thresholds: config/assumptions.yaml. Missing evidence scores zero.</p>

<footer><div class=fine>The Chase Index · account brief generated {date.today().isoformat()} from public data. Reported figures link to their official source; estimates are labelled.
Product statements describe what agent-to-agent payment products say publicly about themselves. {q.DISCLAIMER}</div></footer>
</div>"""
    doc = f"<!doctype html><html lang=en><head><meta charset=utf-8><title>{esc(b['name'])} · Chase Index account brief</title><style>{CSS}</style></head><body>{body}</body></html>"
    return b["company_id"], doc


def pdfs(paths: list[Path]) -> int:
    from playwright.sync_api import sync_playwright
    n = 0
    with sync_playwright() as p:
        br = p.chromium.launch()
        pg = br.new_page()
        for h in paths:
            pg.goto(h.resolve().as_uri())
            pg.pdf(path=str(h.with_suffix(".pdf")), format="A4", print_background=True)
            n += 1
        br.close()
    return n


def one_pagers(extra: list[str] | None = None, make_pdf: bool = True) -> list[str]:
    d = OUT / "one_pagers"
    d.mkdir(parents=True, exist_ok=True)
    copy_path = d / "copy.json"
    copy = json.loads(copy_path.read_text()) if copy_path.exists() else {}
    df = q.companies()
    # thin evidence (UK invoice value under 1% of group revenue) stays on the target list with a flag but gets no one-pager
    top = df[df.excluded_reason.isna() & (df.priority_tier == 1) & ~df.thin_evidence].head(N_ONE_PAGERS).company_id.tolist()
    ids = top + [q.resolve(x) for x in (extra or []) if q.resolve(x)]
    paths, index = [], []
    keep = set(ids)
    trash = ROOT / "tmp" / "trash" / "one_pagers"
    for old in list(d.glob("*.html")) + list(d.glob("*.pdf")):      # outdated pages from an earlier ranking
        if old.stem not in keep:
            trash.mkdir(parents=True, exist_ok=True)
            old.replace(trash / old.name)
    for cid in dict.fromkeys(ids):
        cid, doc = render_one_pager(cid, copy.get(cid))
        f = d / f"{cid}.html"
        f.write_text(doc)
        paths.append(f)
        r = q._row(cid)
        index.append({"rank": int(r["rank"]), "company_id": cid, "name": r["name"], "html": f"outputs/one_pagers/{cid}.html",
                      "pdf": f"outputs/one_pagers/{cid}.pdf", "copy": "agent_written" if cid in copy else "deterministic_fallback"})
    pd.DataFrame(index).to_csv(d / "index.csv", index=False)
    (d / "facts_for_copy.json").write_text(json.dumps(
        [{"company_id": i["company_id"], **{k: v for k, v in q.get_account_brief(i["company_id"]).items()
                                            if k in ("name", "country", "hq_city", "sector", "revenue", "scores", "why_now_signals", "payment_profile", "estimates")},
          "hook": q.hook_variables(q._row(i["company_id"])).get("hook")} for i in index if i["company_id"] in top], indent=1, default=str))
    if make_pdf:
        pdfs(paths)
    return [str(p) for p in paths]


TEMPLATE_NOTE = """How to use: the template is written by a human, the slots are filled from the data. Do not let a model write the whole email.

Template (edit to taste):

    Hi {first_name},

    We're hosting a small dinner for finance leaders in {city} on {date}.
    One number made me think of you: {hook} You know the story behind it better than I do, and
    I'd like to hear it. No deck, promise.

    {sender}

`{hook}` is the one data-backed sentence per account below. `{first_name}`, `{date}` and `{sender}` are yours to fill.
"""


def invites() -> None:
    d = OUT / "invites"
    d.mkdir(parents=True, exist_ok=True)
    for city in q.CITIES:
        s = q.dinner_shortlist(city, 15)
        rows = []
        for a in s["accounts"]:
            hv = a["hook_variables"]
            rows.append({"city": city, "rank": a["rank"], "company": a["name"], "company_id": a["company_id"], "tier": a["priority_tier"],
                         "local_link": a["local_link"], "hq_city": a["hq_city"], "sector": a["sector"],
                         "evidence_kind": a["pain_basis"], "days": hv.get("days"), "scope": hv.get("scope"),
                         "benchmark": hv.get("benchmark"), "pct_late": hv.get("late"), "hook": hv.get("hook"),
                         "source_url": hv.get("source_url"), "period": hv.get("period_end")})
        df = pd.DataFrame(rows)
        df.to_csv(d / f"{city}.csv", index=False)
        country = {"munich": "Germany", "paris": "France", "london": "United Kingdom", "madrid": "Spain"}[city]
        n_city = sum(r["local_link"] == "hq_in_city_area" for r in rows)
        md = [f"# {city.title()} dinner: accounts headquartered in {country}", "",
              f"**Read this first.** This is a {country} list, not a {city.title()} list: {n_city} of {len(rows)} accounts have a confirmed HQ in the {city.title()} area. "
              "For the others the HQ is elsewhere in the country or the HQ city is missing in the data. Check where the finance leader sits before inviting. "
              "UK-based figures describe the group's UK subsidiaries: expect \"that's our UK business\" and have the next question ready.", "", f"_{q.DISCLAIMER}_", "", TEMPLATE_NOTE,
              f"## Shortlist ({len(df)} accounts)", "",
              "`local link` says why the account is on this list: `hq in city area` means the HQ city is in the metro area, `hq in country` means HQ elsewhere in the country or HQ city unknown in the data. Each account is on one city list only.", "",
              "Only accounts with a payment figure clearly above the benchmark are listed (UK entities at 45+ days, Spanish payment period at 50+ days, or computed DPO at 1.3x the sector median). " + (f"Only {len(df)} accounts clear that bar for this city." if len(df) < 10 else ""), "",
              "| # | Company | Tier | Local link | Hook (one sentence, from the data) | Source |", "|---|---|---|---|---|---|"]
        for i, r in enumerate(rows, 1):
            md.append(f"| {i} | {r['company']} | {r['tier']} | {r['local_link'].replace('_', ' ')} | {r['hook']} | [link]({r['source_url']}) |")
        bench = q.dinner_bench(city, 10)
        if bench:
            md += ["", f"## Bench ({len(bench)} accounts): verify before use", "",
                   "Slow figure, but weaker evidence. Not invite material on the data alone.", "",
                   "| Company | Tier | Why it is on the bench | Figure | Source |", "|---|---|---|---|---|"]
            md += [f"| {x['name']} | {x['priority_tier']} | {x['bench_reason']} | {x['figure']} | [link]({x['source_url']}) |" for x in bench]
            pd.DataFrame(bench).assign(city=city).to_csv(d / f"{city}_bench.csv", index=False)
        (d / f"{city}.md").write_text("\n".join(md) + "\n")


def anonymised_one_pager(company: str, label: str, descriptor: str) -> str:
    """A one-pager with the company, its entities and all links removed, for showing to practitioners without
    naming anyone. Uses the deterministic copy (the agent-written copy names entities). Numbers are unchanged."""
    import re as _re
    b = q.get_account_brief(company)
    _, doc = render_one_pager(company, None)
    names = {b["name"], q.short_name(b["name"])}
    uk = b["payment_profile"]["reported"].get("uk") or {}
    ents = [e["name"] for e in uk.get("entities", [])]
    if uk.get("slowest_entity"):
        ents.append(uk["slowest_entity"]["name"])
    for i, n in enumerate(dict.fromkeys(ents), 1):
        for variant in {n, nice(n), n.title(), q.nice_name(n)}:
            doc = doc.replace(html.escape(variant), f"UK entity {i}").replace(variant, f"UK entity {i}")
    for n in sorted(names, key=len, reverse=True):
        doc = _re.sub(_re.escape(html.escape(n)), label, doc, flags=_re.I)
        doc = _re.sub(_re.escape(n), label, doc, flags=_re.I)
    doc = _re.sub(r'\.? ?<a href="[^"]*">source</a>', ".", doc)                    # drop "source" links entirely
    doc = _re.sub(r'<a href="[^"]*">(.*?)</a>', r"\1", doc)                       # no links: they identify the company
    doc = _re.sub(r"<h1>.*?</h1>", f"<h1>{label}</h1>", doc, count=1, flags=_re.S)
    doc = _re.sub(r"<title>.*?</title>", f"<title>{label} · anonymised account brief</title>", doc, count=1, flags=_re.S)
    doc = _re.sub(r'<div class=sub>.*?</div>', f"<div class=sub>{html.escape(descriptor)}</div>", doc, count=1, flags=_re.S)
    doc = _re.sub(r"rank \d+", "rank withheld", doc, flags=_re.I)
    doc = doc.replace("</header>", "</header><p class=fine style='margin-top:6px'><b>Anonymised copy for a practitioner test.</b> "
                      "Company and entity names and all source links are removed. The figures are real reported data.</p>", 1)
    return doc


def practitioner_kit() -> list[str]:
    """Two anonymised one-pagers for application/practitioner_test.md: one long-terms account, one late-payer account."""
    df = q.companies()
    t = df[df.excluded_reason.isna() & (df.priority_tier == 1) & ~df.thin_evidence & (df.pain_basis == "uk_reported") & (df.uk_entities_n >= 2)]
    terms = t[(t.uk_pct_paid_late_mean <= 15) & (t.uk_pct_paid_over_60_mean >= 45)].head(1)
    late = t[(t.uk_pct_paid_late_mean >= 40) & (t.uk_pct_paid_late_mean <= 75)].head(1)
    d = ROOT / "application" / "practitioner_test"
    d.mkdir(parents=True, exist_ok=True)
    out = []
    for row, label, kind in ((terms, "Company A", "long_terms"), (late, "Company B", "late_payments")):
        if row.empty:
            continue
        r = row.iloc[0]
        band = "over $50bn" if r.revenue_usd >= 50e9 else "$20bn to $50bn" if r.revenue_usd >= 20e9 else "$10bn to $20bn" if r.revenue_usd >= 10e9 else "$4bn to $10bn"
        doc = anonymised_one_pager(r.company_id, label, f"{r.sector.replace('_', ' ').title()} group · revenue {band} · UK entities shown")
        f = d / f"one_pager_{label[-1].lower()}_{kind}.html"
        f.write_text(doc)
        out.append(f)
    if out:
        pdfs(out)
    (d / "KEY_private.md").write_text("# Which company is which (keep private, do not hand out)\n\n" + "\n".join(
        f"- {lab}: see outputs/one_pagers/{row.iloc[0].company_id}.html" for row, lab in ((terms, "Company A"), (late, "Company B")) if not row.empty) + "\n")
    return [str(x) for x in out]


if __name__ == "__main__":
    if "--practitioner-kit" in sys.argv:
        print(practitioner_kit())
        sys.exit(0)
    extra = [sys.argv[sys.argv.index("--company") + 1]] if "--company" in sys.argv else []
    # every account in this week's queue gets a one-pager too (deterministic copy unless agent copy exists),
    # except thin-evidence accounts, which get none anywhere (critic, Phase 12)
    from datetime import date
    from chase.gtm import nba
    qd = nba.build_queue(date.today(), demo=False)          # computed from data/processed, no queue file needed
    extra += qd.loc[~qd.thin_evidence.astype(bool), "company_id"].tolist()
    made = one_pagers(extra, make_pdf="--no-pdf" not in sys.argv)
    invites()
    print(f"one-pagers: {len(made)} in outputs/one_pagers; invites for {', '.join(q.CITIES)} in outputs/invites (gitignored)")
