"""Next best action per account, and the weekly queue.

For each addressable Tier 1 or Tier 2 account: a queue priority, the live triggers ("why now"), who to
approach, a suggested play and a draft opener. Everything is rule-based and explainable: the rules are
in this file, the weights in config/assumptions.yaml (section `queue`).

Plays: dinner_invite, warm_via_supplier, investor_intro, cold_email, plus the status-driven ones
(brief_owner, follow_up, prepare_meeting, dinner_follow_up). Openers are human-written templates with
slots filled from the data ("Mad Libs"): a model never writes the message.

  python -m chase.gtm.nba                 # this week's queue from your local files
  python -m chase.gtm.nba --demo          # with the SYNTHETIC bring-your-own-data set
  python -m chase.gtm.nba --week 2026-48  # a specific ISO week

The MCP server, the skill and the workspace compute the queue on demand with build_queue(); nothing reads a file.
This command only writes a copy to outputs/queue/YYYY-WW.csv and .md (+ byod_unmatched.csv, all gitignored), without
names of individuals. When
data/private/personas.csv exists, a second copy with the published finance leaders is written to
data/private/queue/ (gitignored). Names never go to outputs/ or site/.
"""
from __future__ import annotations

import zlib

import json
import sys
from datetime import date, timedelta
from pathlib import Path

import pandas as pd
import yaml

from chase import query as q
from chase.gtm import byod, triggers

ROOT = q.ROOT
OUT = ROOT / "outputs" / "queue"

OPENERS = {
    "dinner_invite": ("We're hosting our next small dinner for finance leaders in {city}{on_date}. One number made me think of you: {hook} "
                      "You know the story behind it better than I do, and I'd like to hear it. No deck."),
    "warm_via_supplier": ("{supplier} already settles invoices with us and counts {company_short} among its customers. {hook} "
                          "I'd like to show you what the same invoices look like from your side. Twenty minutes?"),
    "investor_intro": ("Ask {investor} for an introduction. Line to give them: {hook} We'd like to compare notes with {company_short}'s finance team."),
    "cold_email_terms": ("{hook} Long terms that are met are leverage you could price: your side sets the guardrails, the supplier decides "
                         "what early cash is worth. I ran a rough range from your public numbers and would rather you tell me where it's wrong."),
    "cold_email_late": ("{hook}{late_line} In most AP teams paying after terms isn't a decision, "
                        "it's invoices waiting on a match or an answer from the supplier. "
                        "Worth 20 minutes on how agents on both sides clear that?"),
    "cold_email_generic": ("{hook} That number is from your own filing, so you know it better than I do. I'd like to hear how much of it is "
                           "strategy and how much is invoices stuck in matching."),
    "cold_email_late_b": ("{hook}{late_line} When that many invoices miss terms, it's usually not cash, it's approvals: a missing PO match, "
                          "a delivery nobody confirmed, a supplier waiting on an answer. Open to comparing notes for 20 minutes?"),
    "cold_email_terms_b": ("{hook} If those terms are on purpose, some of your suppliers would probably pay for earlier cash, inside limits "
                           "your team sets. I sketched a range from your public filings and I'm sure it's wrong somewhere. Want to tell me where?"),
    "cold_email_generic_b": ("{hook} It's from your own filing, so you'll know what's behind it. My guess is a mix of deliberate terms "
                             "and invoices stuck between AP and the supplier. Is that close?"),
    # a disclosed supplier finance programme means early cash is already on offer to some suppliers: ask about reach and terms
    "cold_email_sf": ("{hook} Your annual report also discloses a supplier finance programme{sf_amount}, so early cash is already on offer "
                      "to some suppliers. Two questions I'd like your view on: which suppliers does it actually reach, and did payment terms "
                      "get longer when it came in?"),
    "cold_email_sf_b": ("{hook} You also disclose a supplier finance programme{sf_amount}. I'd like to understand who it actually reaches, "
                        "only the largest suppliers or the long tail too, and whether terms got longer when it started. Open to 20 minutes?"),
    "brief_owner": "Already in pipeline ({stage}, owner {owner}). Send the owner this: {hook}",
    "follow_up": "Contacted on {date}. Follow up with the newest dated fact: {trigger}",
    "prepare_meeting": "Meeting stage. Bring the one-pager and open with: {hook}",
    "dinner_follow_up": "Met at the {city} dinner{on_date}. Follow up within the week with: {hook}",
}


def on_date(d) -> str:
    """' on 2026-12-03' when a date is known, else '' (the template already says 'next')."""
    return f" on {str(d)[:10]}" if isinstance(d, str) and d.strip() else ""


def _cfg() -> dict:
    c = yaml.safe_load((ROOT / "config" / "assumptions.yaml").read_text())
    return c.get("queue") or {"size": 25, "trigger_boost_max": 15, "warm_boost": 12, "peer_boost": 3, "dinner_boost": 6,
                              "investor_boost": 6, "sfa_whitespace_boost": 3, "tier2_penalty": 8}


def _personas() -> dict[str, list[dict]]:
    p = ROOT / "data" / "private" / "personas.csv"
    if not p.exists():
        return {}
    d = pd.read_csv(p, dtype=str).fillna("")
    d = d[(d.full_name != "") & (pd.to_numeric(d.confidence, errors="coerce") >= 0.7)]   # excerpt-only rows (0.5) are not shown
    return {cid: g.to_dict("records") for cid, g in d.groupby("company_id")}


def _sfa() -> dict[str, dict]:
    p = ROOT / "data" / "processed" / "supplier_finance.parquet"
    if not p.exists():
        return {}
    d = pd.read_parquet(p)
    return {r["company_id"]: r for r in d.to_dict("records")}


CONTEXT_TRIGGERS = {"einvoicing_mandate", "einvoicing_mandate_suppliers", "dinner_city", "results_date",
                    "sf_disclosed", "scf_started"}   # supplier finance is context, never priority (DECISIONS 38)


SF_ROLE = ("Group treasurer or CFO office",
           "the opener asks about the supplier finance programme (who it reaches, whether terms got longer): treasury owns that")


def suggested_role(r, feats: dict | None, sf_angle: bool = False) -> tuple[str, str]:
    """Role to approach when no named persona is available, from the shape of the evidence.
    sf_angle: the opener uses the supplier finance angle, which is a treasury question whatever the late share says."""
    if sf_angle:
        return SF_ROLE
    late = q._nn(r.uk_pct_paid_late_mean) if r.pain_basis == "uk_reported" else None
    within = q._nn(r.get("es_pct_within_legal_max_by_value")) if r.pain_basis == "es_reported" else None
    if within is not None and within < 60:
        return "Head of accounts payable or shared services", f"only {within:.0f}% of Spanish invoice value paid within the legal maximum points at process, not just terms"
    if late is not None and late >= 25:
        return "Head of accounts payable or shared services", f"{late:.0f}% of UK invoices paid after terms points at matching and approval"
    if r.pain_basis in ("uk_reported", "es_reported"):
        return "Group treasurer or CFO office", "long payment periods with few late invoices are a terms and working-capital topic"
    return "CFO office", "only a balance-sheet proxy is available, so start at group level"


def build_queue(today: date | None = None, demo: bool = False, size: int | None = None) -> pd.DataFrame:
    today = today or date.today()
    cfg = _cfg()
    comp = q.companies()
    acc = comp[comp.excluded_reason.isna() & (comp.priority_tier <= 2)].copy()
    trig = triggers.build(today)
    live = trig[trig.is_live]
    if "entity_value_gbp" not in live:
        live = live.assign(entity_value_gbp=float("nan"))
    # strongest first; among equals, the entity carrying the most invoice value (the headline is the material one)
    by_acc = {cid: g.sort_values(["strength", "entity_value_gbp"], ascending=[False, False], na_position="last")
              for cid, g in live.groupby("company_id")}
    flags, unmatched = byod.apply(demo)
    personas, sfa = _personas(), _sfa()
    gf_path = ROOT / "data" / "processed" / "uk_group_features.parquet"
    gfeat = pd.read_parquet(gf_path).set_index("company_id").to_dict("index") if gf_path.exists() else {}
    dinners = {d["country"]: d for d in q.dinner_calendar()}

    rows = []
    for _, r in acc.iterrows():
        cid, fl = r.company_id, flags.get(r.company_id, {})
        st = fl.get("status")
        if fl.get("already_customer") or fl.get("crm_closed") or (st and st["status"] in byod.FINAL_STATUSES):
            continue
        t = by_acc.get(cid)
        tl = [] if t is None else t.to_dict("records")
        hv = q.hook_variables(r)
        hook = hv.get("hook") or ""
        short = q.short_name(r["name"])

        # ---- queue priority: base score + dated triggers + warmth
        # only account-specific events move priority; country-wide mandates, dinners and results dates are context
        tb = [x for x in tl if x["trigger_type"] not in CONTEXT_TRIGGERS]
        strongest = max((x["strength"] for x in tb), default=0.0)
        boost = cfg["trigger_boost_max"] * min(1.0, strongest + 0.1 * max(0, len(tb) - 1))
        prio = float(r.priority_score) + boost
        why_prio = [f"base {r.priority_score:.0f}"]
        if round(boost) > 0:
            why_prio.append(f"triggers +{boost:.0f}")
        if fl.get("warm_via_supplier"):
            prio += cfg["warm_boost"]; why_prio.append(f"warm +{cfg['warm_boost']}")
        elif fl.get("peer_on_network"):
            prio += cfg["peer_boost"]; why_prio.append(f"peer +{cfg['peer_boost']}")
        if fl.get("investor_links"):
            prio += cfg["investor_boost"]; why_prio.append(f"investor +{cfg['investor_boost']}")
        if r.priority_tier == 2:
            prio -= cfg["tier2_penalty"]; why_prio.append(f"tier 2 -{cfg['tier2_penalty']}")
        if bool(r.thin_evidence):
            prio -= cfg.get("thin_penalty", 0); why_prio.append(f"thin UK evidence -{cfg.get('thin_penalty', 0)}")
        s = sfa.get(cid)
        sfa_state, sf_amount = None, ""
        if s is not None:
            sfa_state = s.get("programme_exists")
            if sfa_state == "yes":
                sfa_state = "yes_confirmed" if s.get("programme_confirmed") else "yes_one_reader"
                amt, cur = q._nn(s.get("obligation_amount")), q._nn(s.get("currency"))
                if amt is not None and cur is not None and pd.notna(s.get("period_end")):
                    sf_amount = f" ({cur} {amt / 1e6:,.0f}m outstanding at {str(s['period_end'])[:10]})"
            if sfa_state == "no_evidence" and r.pain_basis == "uk_reported" and cfg["sfa_whitespace_boost"]:
                prio += cfg["sfa_whitespace_boost"]; why_prio.append(f"no disclosed supplier finance +{cfg['sfa_whitespace_boost']}")

        # ---- play
        din = dinners.get(r.country)
        din_hist = fl.get("dinners", [])
        upcoming = bool(din) and q.dinner_upcoming(din, today)
        on_shortlist = any(x["trigger_type"] == "dinner_city" for x in tl)
        attended = next((x for x in din_hist if x["status"] == "attended"), None)
        invited_now = upcoming and any(x["city"] == din["city"] and x["status"] in ("invited", "accepted") for x in din_hist)
        declined_city = upcoming and any(x["city"] == din["city"] and x["status"] == "declined" for x in din_hist)
        late = q._nn(r.uk_pct_paid_late_mean) if r.pain_basis == "uk_reported" else None
        es_within = q._nn(r.get("es_pct_within_legal_max_by_value")) if r.pain_basis == "es_reported" else None
        top_trigger = tl[0]["text"] if tl else hook
        late_v = q._nn(r.uk_pct_paid_late_mean) if r.pain_basis == "uk_reported" else None
        slots = {"hook": hook, "company_short": short, "trigger": top_trigger, "sf_amount": sf_amount,
                 "late_line": "" if late_v is None or "late" in hook or "after terms" in hook
                 else f" They also paid {late_v:.0f}% of invoices after the agreed terms."}
        hold, opener_template = False, None
        if st and st["status"] == "meeting":
            play, opener = "prepare_meeting", OPENERS["prepare_meeting"].format(**slots)
        elif st and st["status"] == "contacted":
            days = (today - pd.to_datetime(st["date"]).date()).days
            hold = days < byod.CONTACT_HOLD_DAYS
            play, opener = "follow_up", OPENERS["follow_up"].format(date=st["date"], **slots)
        elif fl.get("in_pipeline"):
            ip = fl["in_pipeline"]
            play, opener = "brief_owner", OPENERS["brief_owner"].format(stage=ip["stage"], owner=ip["owner"] or "unassigned", **slots)
        elif attended:
            play, opener = "dinner_follow_up", OPENERS["dinner_follow_up"].format(city=attended["city"].title(), on_date=on_date(attended.get("date")), **slots)
        elif fl.get("warm_via_supplier"):
            play, opener = "warm_via_supplier", OPENERS["warm_via_supplier"].format(supplier=fl["warm_via_supplier"][0], **slots)
        elif upcoming and on_shortlist and not invited_now and not declined_city and hv.get("hook_is_strong"):
            play, opener = "dinner_invite", OPENERS["dinner_invite"].format(city=din["city"].title(), on_date=on_date(din.get("date")), **slots)
        elif fl.get("investor_links"):
            play, opener = "investor_intro", OPENERS["investor_intro"].format(investor=fl["investor_links"][0]["investor"], **slots)
        else:
            # a confirmed supplier finance programme changes the conversation: early cash is already on offer, so the
            # opener asks who the programme reaches and whether terms got longer with it (one-reader finds stay context only)
            key = "cold_email_sf" if sfa_state == "yes_confirmed" else \
                  "cold_email_late" if late is not None and 25 <= late <= 75 else \
                  "cold_email_terms" if r.pain_basis in ("uk_reported", "es_reported") and (q._nn(r.pain_days) or 0) >= 55 \
                      and (es_within is None or es_within >= 60) else "cold_email_generic"
            if sfa_state == "yes_one_reader" and key == "cold_email_terms":
                key = "cold_email_generic"    # a programme found by one reader only: don't ask about it, but don't pitch early cash either
            if zlib.crc32(cid.encode()) % 2:          # stable per account, so the wording does not change week to week
                key += "_b"
            play, opener, opener_template = "cold_email", OPENERS[key].format(**slots), key
        if hold:
            continue

        # ---- who
        role, role_why = suggested_role(r, gfeat.get(cid), sf_angle=str(opener_template or "").startswith("cold_email_sf"))
        ps = personas.get(cid, [])
        cfo = next((p for p in ps if p["role_type"] == "cfo"), None)
        named = "; ".join(f"{p['full_name']} ({p['title_as_published']})" for p in ps[:3])

        gf = gfeat.get(cid, {})
        rows.append({
            "queue_priority": round(prio, 1), "priority_explained": ", ".join(why_prio),
            "company_id": cid, "company": r["name"], "country": r.country, "hq_city": q._nn(r.hq_city), "sector": r.sector,
            "tier": int(r.priority_tier), "index_rank": int(r["rank"]), "thin_evidence": bool(r.thin_evidence),
            "evidence": hook, "evidence_url": hv.get("source_url"),
            "why_now": " | ".join(x["text"] for x in tl[:3]) or "No dated trigger this week: standing evidence only",
            "why_now_types": "|".join(dict.fromkeys(x["trigger_type"] for x in tl)), "triggers_live_n": len(tl),
            "why_now_url": next((x["evidence_url"] for x in tl if isinstance(x.get("evidence_url"), str) and not x.get("private_source")), None),
            "who_role": role, "who_role_reason": role_why,
            "who_named": named or None, "who_source": (cfo or {}).get("source_url") if ps else None,
            "play": play, "opener_draft": opener, "opener_template": opener_template,
            "warm_via": "|".join(fl.get("warm_via_supplier", [])) or None, "peer_on_network": bool(fl.get("peer_on_network")),
            "in_pipeline_stage": (fl.get("in_pipeline") or {}).get("stage"), "status": (st or {}).get("status"),
            "uk_offers_scf": gf.get("offers_scf_any"), "supplier_finance_disclosed": sfa_state,
            "one_pager": q._one_pager_path(cid), "byod_mode": "SYNTHETIC demo" if demo else "local files",
        })
    qd = pd.DataFrame(rows).sort_values("queue_priority", ascending=False).reset_index(drop=True)
    qd.insert(0, "queue_rank", range(1, len(qd) + 1))
    qd.attrs["unmatched"] = unmatched
    qd.attrs["full_size"] = len(qd)
    return qd.head(size or cfg["size"])


def write_queue(qd: pd.DataFrame, today: date, demo: bool, out: Path | None = None) -> tuple[Path, Path]:
    """Writes the queue WITHOUT names of individuals to outputs/queue/ (gitignored; shareable). If local private
    data supplied names, the full version goes to data/private/queue/ as well."""
    if qd.who_named.notna().any():
        _write(qd, today, demo, ROOT / "data" / "private" / "queue")
    public = qd.copy()
    public["who_named"], public["who_source"] = None, None
    return _write(public, today, demo, out or OUT)


def _write(qd: pd.DataFrame, today: date, demo: bool, OUT: Path) -> tuple[Path, Path]:
    OUT.mkdir(parents=True, exist_ok=True)
    iso = today.isocalendar()
    stem = f"{iso.year}-{iso.week:02d}" + ("_demo" if demo else "")
    monday = today - timedelta(days=today.weekday())
    qd.to_csv(OUT / f"{stem}.csv", index=False)
    pd.DataFrame(qd.attrs.get("unmatched", [])).to_csv(OUT / "byod_unmatched.csv", index=False)
    plays = qd.play.value_counts().to_dict()
    md = [f"# Weekly queue {stem.replace('_demo', '')}: week of {monday.isoformat()}", "", f"_{q.DISCLAIMER}_", ""]
    if demo:
        md += ["**SYNTHETIC DEMO.** Warm flags, pipeline stages, dinner attendance and statuses in this file come from the invented demo set in "
               "`config/byod/demo/` and `config/status/demo_accounts_status.csv`. The payment evidence and triggers are real public data.", ""]
    md += [f"{len(qd)} accounts, drafts only, nothing was sent. Plays: " + ", ".join(f"{k.replace('_', ' ')} {v}" for k, v in plays.items()) + ".",
           "Each opener is a human-written template with slots filled from the data. Edit before sending. Reported figures describe UK or Spanish "
           "entities, not the whole group.", ""]
    has_names = qd.who_named.notna().any()
    if has_names:
        md += ["This file contains names of individuals from `data/private/`. Keep it internal.", ""]
    for r in qd.itertuples():
        md += [f"## {r.queue_rank}. {r.company} ({r.country}, Tier {r.tier})", "",
               f"- **Play:** {r.play.replace('_', ' ')}" + (f" (warm via {r.warm_via.replace('|', ', ')})" if isinstance(r.warm_via, str) else ""),
               f"- **Why now:** {r.why_now}" + (f" [source]({r.why_now_url})" if isinstance(r.why_now_url, str) else ""),
               f"- **Evidence:** {r.evidence}" + (f" [source]({r.evidence_url})" if isinstance(r.evidence_url, str) else "")
               + (" _Thin evidence: UK invoice value under 1% of group revenue._" if r.thin_evidence else ""),
               f"- **Who:** " + (f"{r.who_named} [source]({r.who_source}). " if isinstance(r.who_named, str) else "")
               + f"Suggested entry: {r.who_role} ({r.who_role_reason}).",
               f"- **Opener (draft):** {r.opener_draft}",
               f"- Priority {r.queue_priority} ({r.priority_explained})" + (f" · [one-pager](../../{r.one_pager})" if isinstance(r.one_pager, str) else ""), ""]
    (OUT / f"{stem}.md").write_text("\n".join(md) + "\n")
    return OUT / f"{stem}.csv", OUT / f"{stem}.md"


def main(argv: list[str]) -> int:
    demo = "--demo" in argv
    today = date.today()
    if "--week" in argv:
        y, w = argv[argv.index("--week") + 1].split("-")
        today = date.fromisocalendar(int(y), int(w), 1)
    qd = build_queue(today, demo)
    c, m = write_queue(qd, today, demo)
    print(f"queue: {len(qd)} of {qd.attrs['full_size']} eligible accounts -> {c.relative_to(ROOT)} and {m.relative_to(ROOT)}"
          + (" (version with names: data/private/queue/)" if qd.who_named.notna().any() else ""))
    print("plays:", qd.play.value_counts().to_dict(), "| unmatched BYOD names:", len(qd.attrs.get("unmatched", [])))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
