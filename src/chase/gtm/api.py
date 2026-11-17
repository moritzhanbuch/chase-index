"""Surface functions for the weekly workflow, used by the MCP server, the skill and the static workspace.

They sit on top of chase.query (evidence, briefs) and the gtm modules (triggers, queue, bring-your-own-data).
Names of individuals are returned only when data/private/personas.csv exists locally, and always marked private.
"""
from __future__ import annotations

from datetime import date

import pandas as pd
import yaml

from chase import query as q
from chase.gtm import byod, nba, triggers

ROOT = q.ROOT
P = ROOT / "data" / "processed"


def _clean(d: dict) -> dict:
    return {k: q._nn(v) for k, v in d.items()}


def weekly_queue(limit: int = 25, demo: bool = False, play: str | None = None) -> dict:
    """This week's prioritised accounts with why now, who, play and a draft opener."""
    today = date.today()
    qd = nba.build_queue(today, demo, size=max(limit, 1) if not play else 400)
    if play:
        qd = qd[qd.play == play].head(limit)
    iso = today.isocalendar()
    return {"week": f"{iso.year}-{iso.week:02d}", "byod_mode": "SYNTHETIC demo data" if demo else "local files (if any)",
            "count": int(len(qd)), "eligible_accounts": int(qd.attrs.get("full_size", len(qd))),
            "accounts": [_clean(r) for r in qd.to_dict("records")],
            "note": "Drafts only. Openers are human-written templates with data slots. Reported figures describe UK or Spanish entities, "
                    "not the whole group. who_named is present only when local private data exists.", "disclaimer": q.DISCLAIMER}


def get_triggers(since: str | None = None, trigger_type: str | None = None, limit: int = 50) -> dict:
    """Dated trigger feed: events on or after `since` (default: 30 days ago) plus upcoming ones in their lead window."""
    today = date.today()
    since = since or (pd.Timestamp(today) - pd.Timedelta(days=30)).date().isoformat()
    t = triggers.since(since)
    if trigger_type:
        t = t[t.trigger_type == trigger_type]
    t = t.sort_values(["trigger_date", "strength"], ascending=[False, False]).head(limit)
    return {"since": since, "count": int(len(t)), "types": {k: v[2] for k, v in triggers.SPEC.items()},
            "triggers": [_clean({k: r[k] for k in ("company_id", "company", "trigger_type", "trigger_date", "text", "evidence_url",
                                                    "scope", "strength", "is_live", "private_source", "date_is_approximate")})
                         for r in t.to_dict("records")],
            "disclaimer": q.DISCLAIMER}


def account_workspace(company: str, demo: bool = False) -> dict:
    """Everything on one account: brief, UK filing features, supplier finance disclosure, triggers, bring-your-own-data
    flags, next best action, and (only if local private data exists) the published finance leadership."""
    b = q.get_account_brief(company)
    if not b.get("found"):
        return b
    cid = b["company_id"]
    out = {"brief": b}
    gf = P / "uk_group_features.parquet"
    if gf.exists():
        g = pd.read_parquet(gf)
        g = g[g.company_id == cid]
        out["uk_filing_features"] = _clean(g.iloc[0].to_dict()) if len(g) else None
    sf = P / "supplier_finance.parquet"
    if sf.exists():
        s = pd.read_parquet(sf)
        s = s[s.company_id == cid]
        out["supplier_finance_disclosure"] = _clean(s.iloc[0].to_dict()) if len(s) else {"note": "not in the top-200 sample that was checked"}
    tp = P / "triggers.parquet"
    t = pd.read_parquet(tp) if tp.exists() else triggers.build()
    t = t[t.company_id == cid]
    out["triggers"] = [_clean({k: r[k] for k in ("trigger_type", "trigger_date", "text", "evidence_url", "is_live", "strength",
                                                  "private_source", "date_is_approximate")})
                       for r in t.to_dict("records")]
    flags, _ = byod.apply(demo)
    out["byod_flags"] = flags.get(cid, {})
    out["byod_mode"] = "SYNTHETIC demo data" if demo else "local files (if any)"
    qd = nba.build_queue(date.today(), demo, size=100000)
    row = qd[qd.company_id == cid]
    out["next_best_action"] = (_clean({k: row.iloc[0][k] for k in ("queue_rank", "queue_priority", "priority_explained", "play",
                                                                    "opener_draft", "who_role", "who_role_reason", "why_now")})
                               if len(row) else {"note": "not in the queue (held back by status, already a customer, or below Tier 2)"})
    pp = ROOT / "data" / "private" / "personas.csv"
    if pp.exists():
        p = pd.read_csv(pp).fillna("")
        p = p[(p.company_id == cid) & (p.full_name != "") & (pd.to_numeric(p.confidence, errors="coerce") >= 0.7)]
        out["people_private"] = {"warning": "Named individuals from data/private (local only, official sources). Internal use: never publish.",
                                 "people": p[["role_type", "full_name", "title_as_published", "in_role_since", "source_url", "retrieved_at"]].to_dict("records")}
    else:
        out["people_private"] = {"note": "No local private data. This install only has public company-level data."}
    return out


def dinner_builder(city: str, dinner_date: str | None = None, limit: int = 15, demo: bool = False) -> dict:
    """Build a dinner list for a city and date: shortlist with hooks, minus accounts already invited, declined or
    closed, plus the bench to verify. Uses the dinner calendar when no date is given."""
    s = q.dinner_shortlist(city, 100)
    if not s.get("found"):
        return s
    cal = {d["city"]: d for d in q.dinner_calendar()}
    when = dinner_date or cal.get(s["city"], {}).get("date")
    flags, _ = byod.apply(demo)
    invite, skipped = [], []
    for a in s["accounts"]:
        fl = flags.get(a["company_id"], {})
        st = (fl.get("status") or {}).get("status")
        hist = [d for d in fl.get("dinners", []) if d["city"] == s["city"]]
        reason = ("already a customer" if fl.get("already_customer") else f"status {st}" if st in byod.FINAL_STATUSES else
                  "declined this city before" if any(d["status"] == "declined" for d in hist) else
                  "already invited or accepted" if any(d["status"] in ("invited", "accepted") for d in hist) else None)
        if reason:
            skipped.append({"company": a["name"], "reason": reason})
            continue
        hv = a["hook_variables"]
        invite.append({"company_id": a["company_id"], "company": a["name"], "tier": a["priority_tier"], "hq_city": a["hq_city"],
                       "local_link": a["local_link"], "hook": hv["hook"], "source_url": hv.get("source_url"),
                       "warm_via": fl.get("warm_via_supplier"), "in_pipeline": bool(fl.get("in_pipeline")),
                       "invite_draft": nba.OPENERS["dinner_invite"].format(city=s["city"].title(), on_date=nba.on_date(when), hook=hv["hook"])})
    return {"found": True, "city": s["city"], "date": when, "date_source": "argument" if dinner_date else "config/dinners.local.yaml" if when else "next dinner, no date set",
            "invite_count": len(invite[:limit]), "invite": invite[:limit], "skipped": skipped, "bench_to_verify": q.dinner_bench(city, 10),
            "byod_mode": "SYNTHETIC demo data" if demo else "local files (if any)",
            "note": "A country list: check where the finance leader sits. UK-based figures describe UK subsidiaries. Drafts only.",
            "disclaimer": q.DISCLAIMER}


def byod_status(demo: bool = False) -> dict:
    """Which bring-your-own-data files are present, how many rows, and what did not match."""
    out = byod.status_summary(demo)
    flags, unmatched = byod.apply(demo)
    out["accounts_flagged"] = len(flags)
    out["flag_counts"] = {k: sum(1 for f in flags.values() if f.get(k)) for k in
                          ("warm_via_supplier", "peer_on_network", "already_customer", "in_pipeline", "crm_closed", "dinners", "investor_links", "status")}
    out["unmatched_names"] = unmatched
    out["private_personas_present"] = (ROOT / "data" / "private" / "personas.csv").exists()
    return out
