"""Human-readable answers over the query layer, shared by the MCP server and the /chase-brief skill.

Each function returns text: a short answer first (key number, source link, why now, suggested opener), then a compact
"Details" block with the structured fields a calling agent may need. Everything is computed on demand from
data/processed: no queue, invite or outreach file is read.
"""
from __future__ import annotations

import json
from datetime import date

from chase import query as q
from chase.gtm import api as gtm
from chase.gtm import nba

UK_MEDIAN = 32
FULL_N = 5          # queue accounts shown with their full opener; the rest get one line each
FOOT = ("Drafts only: a person edits and sends every message. UK figures cover the group's UK legal entities, "
        "Spanish figures its Spanish entities. " + q.DISCLAIMER)


# ---------------------------------------------------------------- helpers
def money(v, cur: str = "") -> str:
    if v is None:
        return "n/a"
    a = abs(v)
    s = f"{v/1e9:.1f}bn" if a >= 1e9 else f"{v/1e6:.0f}m" if a >= 1e6 else f"{v/1e3:.0f}k"
    return f"{cur} {s}".strip()


def link(url) -> str:
    return f" [source]({url})" if isinstance(url, str) and url else ""


def details(obj) -> str:
    """Compact structured block: one JSON object per line for lists, so it stays scannable."""
    if isinstance(obj, list):
        body = "\n".join(json.dumps(x, ensure_ascii=False, default=str) for x in obj)
    else:
        body = json.dumps(obj, ensure_ascii=False, default=str)
    return f"\n\n---\nDetails (structured):\n{body}"


def _one_pager(path) -> str | None:
    return str(q.ROOT / path) if isinstance(path, str) else None


def _first_trigger(why_now: str | None) -> tuple[str, int]:
    parts = [p.strip() for p in (why_now or "").split(" | ") if p.strip()]
    return (parts[0] if parts else "no dated trigger this week, standing evidence only"), max(len(parts) - 1, 0)


def _queue_full():
    return nba.build_queue(date.today(), False, size=100000)


# ---------------------------------------------------------------- start_here
QUESTIONS = [
    "What's in this week's queue, and what do I open with?",
    "Brief me on Reckitt.",
    "Who should we invite to the Munich dinner?",
]


def start_here() -> str:
    n = len(q.companies())
    lines = [
        f"1. The Chase Index ranks {n:,} large companies by how slowly they pay suppliers, from official filings (UK statutory reports, Spanish PMP) and computed DPO.",
        "2. Each week it picks 25 accounts with a reason to call now (a new slower UK filing, longer terms, an e-invoicing deadline), who to ask for and a draft opener.",
        "3. Every number links to its official source. Reported figures, computed proxies and estimates are labelled and never mixed.",
        "4. It drafts, it never sends: openers and invite lines are human-written templates with the numbers filled in.",
        "5. Read-only and local: no network calls, no names of individuals, public company-level data only.",
        "",
        "Try asking:",
    ] + [f"- \"{x}\"" for x in QUESTIONS] + ["", q.DISCLAIMER]
    return "\n".join(lines)


# ---------------------------------------------------------------- weekly queue
def weekly_queue(limit: int = 10, play: str | None = None, demo: bool = False) -> str:
    w = gtm.weekly_queue(limit, demo, play)
    acc = w["accounts"]
    if not acc:
        return f"No accounts in the queue{' for play ' + play if play else ''} this week." + details({"week": w["week"]})
    plays = {}
    for a in acc:
        plays[a["play"]] = plays.get(a["play"], 0) + 1
    full = min(25, w["eligible_accounts"])
    L = [f"**Week {w['week']} queue: {'all ' + str(len(acc)) if len(acc) >= full else 'top ' + str(len(acc)) + ' of ' + str(full)}"
         f" accounts this week** (picked from {w['eligible_accounts']} eligible). "
         + ", ".join(f"{v} {k.replace('_', ' ')}" for k, v in plays.items()) + "."
         + (" SYNTHETIC demo CRM data applied." if demo else ""), ""]
    for i, a in enumerate(acc):
        trig, more = _first_trigger(a.get("why_now"))
        role = a["who_role"][0].lower() + a["who_role"][1:]
        if i >= FULL_N:           # beyond the top few: one line each, the opener is one "brief me on" away
            if i == FULL_N:
                L += ["", f"**Next {len(acc) - FULL_N}** (ask \"brief me on <company>\" for the opener):"]
            L.append(f"{a['queue_rank']}. **{a['company']}** ({a['country']}, Tier {a['tier']}), {a['play'].replace('_', ' ')} to the {role}. "
                     f"Why now: {trig}{link(a.get('why_now_url'))}")
            continue
        L += [f"**{a['queue_rank']}. {a['company']}** ({a['country']}, Tier {a['tier']}): {a['play'].replace('_', ' ')}, ask for the {role}",
              f"   - Why now: {trig}{' (+' + str(more) + ' more events)' if more else ''}{link(a.get('why_now_url'))}",
              f"   - Open with: \"{a['opener_draft']}\"{link(a.get('evidence_url'))}"]
        if a.get("thin_evidence"):
            L.append("   - Caution: thin evidence, UK invoice value is under 1% of group revenue.")
        if a.get("supplier_finance_disclosed") in ("yes_confirmed", "yes_one_reader"):
            L.append("   - Context: discloses a supplier finance programme" + (" (one reader, unconfirmed)" if a["supplier_finance_disclosed"] == "yes_one_reader" else "")
                     + ". Ask who it reaches and whether terms got longer with it. Context, not a reason to call.")
    L += ["", "The opener's first sentence is the key number; [source] is its official filing. For any account: \"brief me on <company>\"."
          + (f" The full week is {full}: ask for all {full}." if len(acc) < full else ""),
          FOOT]
    return "\n".join(L) + details([{k: a.get(k) for k in ("queue_rank", "company_id", "company", "tier", "play", "who_role", "queue_priority",
                                                             "priority_explained", "evidence_url", "why_now_url", "supplier_finance_disclosed")}
                                   | {"one_pager": _one_pager(a.get("one_pager"))} for a in acc])


# ---------------------------------------------------------------- account brief
def _evidence_lines(b: dict) -> list[str]:
    """One line per evidence source, the one the score uses first (so the key number matches the opener)."""
    pp = b["payment_profile"]
    uk, es, dpo = pp["reported"].get("uk"), pp["reported"].get("spain"), pp.get("computed_proxy")
    lines = {}
    if uk and uk.get("avg_days_to_pay_mean_of_entities") is not None:
        n, sl = uk["entities_n"], uk["slowest_entity"]
        who = (f"{b['short']}'s UK entity ({q.nice_name(sl['name'])}) pays" if n == 1 else f"{b['short']}'s {n} UK entities pay")
        s = (f"REPORTED (UK): {who} suppliers in {uk['avg_days_to_pay_mean_of_entities']:.0f} days on average"
             f"{'' if n == 1 else (' (weighted by invoice value)' if uk.get('aggregation') == 'invoice_value_weighted_mean' else ' (simple mean of entities)')}, against a UK median of {UK_MEDIAN}")
        extra = []
        if uk.get("pct_invoices_paid_over_60_days_mean") is not None:
            extra.append(f"{uk['pct_invoices_paid_over_60_days_mean']:.0f}% of invoices paid after 60 days")
        if uk.get("pct_invoices_paid_late_mean") is not None:
            extra.append(f"{uk['pct_invoices_paid_late_mean']:.0f}% paid after the agreed terms")
        lines["uk_reported"] = (s + (f"; {', '.join(extra)}" if extra else "") + f". Half-year to {uk['period']['end']}."
                                + ("" if n == 1 else f" Slowest: {q.nice_name(sl['name'])} at {sl['avg_days_to_pay']:.0f} days.")
                                + link(sl["source_url"]))
    if es and es.get("pmp_days") is not None:
        prior = es.get("prior_year_pmp_days")
        lines["es_reported"] = (f"REPORTED (Spain): average supplier payment period {es['pmp_days']:.0f} days in FY{int(es['fiscal_year'])}"
                                f"{' (prior year ' + format(prior, '.0f') + ')' if prior is not None else ''}; legal maximum per payment 60."
                                f"{link(es.get('source_url'))}")
    if dpo and dpo.get("dpo_days") is not None:
        lines["computed_dpo_proxy"] = (f"COMPUTED PROXY (a balance-sheet ratio, not days to pay): DPO {dpo['dpo_days']:.0f} days in "
                                       f"FY{int(dpo['fiscal_year'])}, sector median {dpo['sector_median_dpo_days']:.0f}.{link(dpo.get('source_url'))}")
    first = b["scores"].get("pain_basis")
    order = [first] + [k for k in ("uk_reported", "es_reported", "computed_dpo_proxy") if k != first]
    return [lines[k] for k in order if k in lines]


def _why_now(b: dict, nb: dict | None) -> tuple[str, str | None]:
    if nb and nb.get("why_now") and not nb["why_now"].startswith("No dated trigger"):
        t, more = _first_trigger(nb["why_now"])
        return t + (f" (+{more} more events)" if more else ""), nb.get("why_now_url")
    order = ["trend_worsening", "terms_changed_longer", "new_cfo", "es_pmp_rose", "long_terms", "new_evidence"]
    sigs = sorted(b["why_now_signals"], key=lambda s: order.index(s["type"]) if s["type"] in order else 99)
    if sigs:
        return sigs[0]["text"], sigs[0].get("url")
    return "no dated trigger: standing evidence only", None


def account_brief(company: str) -> str:
    b = q.get_account_brief(company)
    if not b.get("found"):
        ents = q.lookup_uk_entity(company, 5)
        if ents:
            return (f"'{company}' is not one of the ranked groups (listed or large companies, revenue above USD 4bn). "
                    "UK legal entities with that name and a statutory payment report:\n"
                    + "\n".join(f"- {q.nice_name(e['company_name'])} ({e['company_number']}): "
                                f"{'n/a' if e['avg_days_to_pay'] is None else format(e['avg_days_to_pay'], '.0f') + ' days'} to pay, "
                                f"half-year to {e['period_end']}.{link(e['source_url'])}" for e in ents))
        sugg = q.search_companies(company.split()[0], limit=5) if company.split() else []
        return f"No company called '{company}' in the Chase Index." + (" Did you mean: " + ", ".join(s["name"] for s in sugg) + "?" if sugg else "")
    b["short"] = q.short_name(b["name"])
    qd = _queue_full()
    row = qd[qd.company_id == b["company_id"]]
    nb = row.iloc[0].to_dict() if len(row) else None
    sc = b["scores"]
    L = [f"**{b['name']}**: Tier {b['priority_tier']}, rank {b['rank']} of {len(q.companies()):,}"
         + (f", queue #{nb['queue_rank']} this week" if nb and nb["queue_rank"] <= 25 else "")
         + f". {(b['sector'] or '').replace('_', ' ').capitalize()}, {('HQ ' + b['hq_city'] + ', ' + b['country']) if b['hq_city'] else ('headquartered in ' + b['country'])}.", "",
         f"- Key number: {(_evidence_lines(b) or ['No payment evidence in the dataset for this company.'])[0]}"]
    also = [x for x in _evidence_lines(b)[1:] if x.startswith("REPORTED")]
    if also:
        L.append(f"- Also: {also[0]}")
    wn, wn_url = _why_now(b, nb)
    L.append(f"- Why now: {wn}{link(wn_url)}")
    if nb:
        L.append(f"- Open with (draft, {nb['play'].replace('_', ' ')}): \"{nb['opener_draft']}\"")
        L.append(f"- Ask for: {nb['who_role']} ({nb['who_role_reason']}).")
    else:
        L.append("- No opener: " + ("Tier 3, so not in the queue. The evidence does not make it a priority." if b["priority_tier"] == 3
                                    else "not in the queue (excluded, or held back by your status file)."))
    sf = b.get("supplier_finance") or {}
    if sf.get("programme_disclosed"):
        amt = f" with {money(sf.get('obligations_outstanding'), sf.get('currency') or '')} outstanding" if sf.get("obligations_outstanding") else ""
        L.append(f"- Watch: the annual report discloses a supplier finance programme{amt}"
                 f"{'' if sf.get('confirmed') else ' (one reader, unconfirmed)'}. Ask who it reaches and whether terms got longer with it.{link(sf.get('source_url'))}")
    if b.get("thin_evidence"):
        L.append("- Caution: thin evidence, the UK entities' invoice value is under 1% of group revenue.")
    est = b["estimates"]
    e = est.get("uk_scope") or est.get("group_proxy")
    if e and e["early_payment_discount_opportunity"]["base"] is not None:
        d = e["early_payment_discount_opportunity"]
        L.append(f"- ESTIMATE ({'UK entities' if 'uk_scope' in est else 'group, from the DPO proxy'}): early-payment discount opportunity "
                 f"{money(d['low'], e['currency'])} / {money(d['base'], e['currency'])} / {money(d['high'], e['currency'])} a year (low / base / high, "
                 "gross, assumptions in config/assumptions.yaml).")
    op = _one_pager(b.get("one_pager"))
    if op:
        L.append(f"- One-pager: {op}")
    L += ["", FOOT]
    uk = b["payment_profile"]["reported"].get("uk") or {}
    return "\n".join(L) + details({
        "company_id": b["company_id"], "tier": b["priority_tier"], "rank": b["rank"],
        "scores": {k: sc[k] for k in ("fit", "pain", "signal", "priority")}, "pain_basis": sc["pain_basis"],
        "rationale": b["rationale"],
        "uk_entities": [{k: x.get(k) for k in ("name", "avg_days_to_pay", "pct_paid_late", "pct_paid_over_60", "trend_days_yoy", "source_url")}
                        for x in (uk.get("entities") or [])[:6]],
        "why_now_signals": [{"type": s["type"], "text": s["text"], "url": s.get("url")} for s in b["why_now_signals"]],
        "queue": {k: nb.get(k) for k in ("queue_rank", "play", "queue_priority", "priority_explained")} if nb else None,
        "estimate": True if e else None})


# ---------------------------------------------------------------- dinner
def dinner(city: str, date_: str | None = None, limit: int = 12, demo: bool = False) -> str:
    d = gtm.dinner_builder(city, date_, limit, demo)
    if not d.get("found"):
        return f"No dinner list for '{city}'. Cities: {', '.join(d.get('available', []))}."
    local = sum(1 for a in d["invite"] if a["local_link"] == "hq_in_city_area")
    n_proxy = sum(1 for a in d["invite"] if "computed DPO" in (a.get("hook") or ""))
    country = {"munich": "Germany", "paris": "France", "london": "the UK", "madrid": "Spain"}.get(d["city"], "the country")
    L = [f"**{q.dinner_title(d['city'], d['date'])}: {d['invite_count']} accounts to invite.** {local} headquartered in the {d['city'].title()} area, "
         f"{d['invite_count'] - local} elsewhere in {country}. Each has a payment figure clearly above the benchmark: "
         + (f"reported for {d['invite_count'] - n_proxy}, a computed DPO proxy (balance sheet, not days to pay) for {n_proxy}."
            if n_proxy else "all reported."), ""]
    for i, a in enumerate(d["invite"], 1):
        where = a["hq_city"] or "HQ city unknown"
        L.append(f"{i}. **{a['company']}** (Tier {a['tier']}, {where}): {a['hook']}{link(a.get('source_url'))}"
                 + (f" Warm via {', '.join(a['warm_via'])}." if a.get("warm_via") else ""))
    if d["invite"]:
        L += ["", f"Invite line (draft, for #1): \"{d['invite'][0]['invite_draft']}\""]
    if d["skipped"]:
        L += ["", "Left out: " + "; ".join(f"{s['company']} ({s['reason']})" for s in d["skipped"][:8]) + "."]
    if d["bench_to_verify"]:
        L += ["", "Bench (check before inviting): " + "; ".join(f"{b['name']} ({b['bench_reason']})" for b in d["bench_to_verify"][:5]) + "."]
    L += ["", "This is a country list: check where each finance leader actually sits before inviting. " + FOOT]
    return "\n".join(L) + details({"city": d["city"], "date": d["date"], "date_source": d["date_source"],
                                   "invite": [{k: a.get(k) for k in ("company_id", "company", "tier", "hq_city", "local_link", "source_url")} for a in d["invite"]],
                                   "skipped": d["skipped"], "bench": [{k: b.get(k) for k in ("name", "bench_reason", "source_url")} for b in d["bench_to_verify"]]})


# ---------------------------------------------------------------- the rest
def triggers(since: str | None = None, trigger_type: str | None = None, limit: int = 20) -> str:
    t = gtm.get_triggers(since, trigger_type, 300)
    today = date.today().isoformat()
    rows = [x for x in t["triggers"] if not x.get("private_source")]
    past = sorted([x for x in rows if str(x["trigger_date"]) <= today], key=lambda x: (str(x["trigger_date"]), x["strength"] or 0), reverse=True)
    upcoming = sorted([x for x in rows if str(x["trigger_date"]) > today], key=lambda x: str(x["trigger_date"]))
    L = [f"**{len(past)} dated events since {t['since']}" + (f" of type {trigger_type}" if trigger_type else "") + f", {len(upcoming)} upcoming deadlines.**", ""]
    for x in past[:limit]:
        L.append(f"- {x['trigger_date']} · {x['company']}: {x['text']}{link(x.get('evidence_url'))}")
    if upcoming:
        seen, ups = set(), []
        for x in upcoming:            # mandates repeat per account: show each deadline once with its account count
            k = (x["trigger_type"], str(x["trigger_date"]), x.get("scope"))
            if k not in seen:
                seen.add(k)
                n = sum(1 for y in upcoming if (y["trigger_type"], str(y["trigger_date"]), y.get("scope")) == k)
                ups.append(f"- {x['trigger_date']} · {t['types'].get(x['trigger_type'], x['trigger_type'])} ({x.get('scope')}, {n} accounts){link(x.get('evidence_url'))}")
        L += ["", "Upcoming:"] + ups[:8]
    L += ["", q.DISCLAIMER]
    return "\n".join(L) + details({"since": t["since"], "types": t["types"],
                                   "events": [{k: x.get(k) for k in ("company_id", "trigger_type", "trigger_date", "evidence_url")} for x in past[:limit]]})


def top_targets(country=None, city=None, sector=None, tier=None, limit: int = 10) -> str:
    t = q.top_targets(country, city, sector, tier, limit)
    f = ", ".join(f"{k} {v}" for k, v in t["filters"].items() if v)
    L = [f"**Top {len(t['targets'])} of {t['count']} ranked accounts{' (' + f + ')' if f else ''}.** Ranked by tier, reported evidence before proxies, then score.", ""]
    for r in t["targets"]:
        kind = "reported" if r["evidence_is_reported"] else "proxy"
        days = f"{r['evidence_days']:.0f} days ({kind})" if r["evidence_days"] is not None else "no payment figure"
        L.append(f"{r['rank']}. **{r['name']}** ({r['country']}, Tier {r['priority_tier']}): {days}.{link(r.get('evidence_url'))} {r['rationale']}")
    L += ["", q.DISCLAIMER]
    return "\n".join(L) + details([{k: r[k] for k in ("rank", "company_id", "name", "priority_tier", "pain_basis", "evidence_days")} for r in t["targets"]])


def payment_profile(company: str) -> str:
    b = q.get_account_brief(company)
    if not b.get("found"):
        return account_brief(company)       # same fallback: UK entity lookup or suggestions
    b["short"] = q.short_name(b["name"])
    pp = b["payment_profile"]
    ev = _evidence_lines(b) or ["No payment evidence in the dataset for this company."]
    L = [f"**{b['name']}**: how long it takes to pay suppliers", ""] + [f"- {x}" for x in ev] + ["", q.DISCLAIMER]
    uk = pp["reported"].get("uk") or {}
    return "\n".join(L) + details({"uk_period": uk.get("period"), "uk_entities": [{k: x.get(k) for k in (
        "name", "company_number", "avg_days_to_pay", "pct_paid_late", "pct_paid_over_60", "standard_terms_days", "max_contractual_days",
        "trend_days_yoy", "source_url")} for x in uk.get("entities") or []], "spain": pp["reported"].get("spain"), "computed_proxy": pp.get("computed_proxy")})


def search(query: str, country=None, sector=None, limit: int = 10) -> str:
    r = q.search_companies(query, country, sector, limit)
    if not r:
        ents = q.lookup_uk_entity(query, 3)
        return f"No ranked company matches '{query}'." + (" UK legal entities: " + ", ".join(q.nice_name(e["company_name"]) for e in ents) + "." if ents else "")
    L = [f"{len(r)} match{'es' if len(r) != 1 else ''} for '{query}':"] + [
        f"- {x['name']} ({x['country']}, {x['sector'].replace('_', ' ')}, Tier {x['priority_tier']}"
        f"{', reported payment data' if x['has_reported_payment_data'] else ''}), id {x['company_id']}" for x in r]
    return "\n".join(L)


def uk_lookup(customer: str, limit: int = 5) -> str:
    r = q.lookup_uk_entity(customer, limit)
    if not r:
        return f"No UK legal entity with a statutory payment report matches '{customer}'. Try the registered name or the Companies House number."
    L = [f"**Latest statutory payment reports for '{customer}'** (UK legal entities):", ""]
    for e in r:
        days = "no usable figure" if e["avg_days_to_pay"] is None else f"{e['avg_days_to_pay']:.0f} days to pay on average"
        late = f", {e['pct_paid_late']:.0f}% paid after terms" if e.get("pct_paid_late") is not None else ""
        terms = e.get("standard_terms_days")
        tt = f", standard terms {terms[0]:.0f} to {terms[1]:.0f} days" if isinstance(terms, list) and len(terms) == 2 else ""
        L.append(f"- {q.nice_name(e['company_name'])} ({e['company_number']}): {days}{late}{tt}. Half-year to {e['period_end']}"
                 f"{' (old report)' if e.get('report_is_old') else ''}.{link(e['source_url'])}")
    L += ["", f"UK large-business median: {UK_MEDIAN} days. " + q.DISCLAIMER]
    return "\n".join(L)


def methodology(topic: str | None = None) -> str:
    m = q.explain_methodology(topic)
    return m["text"].strip() + f"\n\nSource: {m.get('source')}. Other topics: {', '.join(m.get('topics', []))}."


def byod(demo: bool = False) -> str:
    s = gtm.byod_status(demo)
    have = [k for k, v in s["slots"].items() if v["present"]]
    L = [f"**Your own data ({s['mode']}):** " + (", ".join(f"{k} ({s['slots'][k]['rows']} rows)" for k in have) if have else "no files loaded")
         + f"; status file {'present' if s['status_file']['present'] else 'absent'}. {s['accounts_flagged']} accounts flagged.",
         f"Unmatched names: {len(s['unmatched_names'])}." if s["unmatched_names"] else "",
         f"File formats: {s['formats']}. Without these files the queue uses public data only."]
    return "\n".join(x for x in L if x) + details({"flag_counts": s["flag_counts"], "unmatched_names": s["unmatched_names"][:20]})
