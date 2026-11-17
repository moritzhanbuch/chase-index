"""Trigger model: dated reasons to contact an account now.

A trigger is a dated, sourced event. Standing facts (a company pays slowly) are evidence, not triggers.
Sources: the UK filings (per entity), the Spanish notes, the UK field signals, the dinner calendar,
e-invoicing mandate deadlines (config/einvoicing_mandates.yaml, each with an official source), and,
only if the private folder exists, CFO changes and results dates (data/private/account_dates.csv).

Output: data/processed/triggers.parquet (+csv). No names of individuals: a CFO change trigger says
"new CFO announced", the name stays in data/private.
Run: python -m chase.gtm.triggers
"""
from __future__ import annotations

from datetime import date, timedelta
from pathlib import Path

import pandas as pd
import yaml

from chase import query as q
from chase.resolve.uk_rollup import EXTREME_DAYS, EXTREME_YOY_JUMP

ROOT = q.ROOT
P = ROOT / "data" / "processed"

# strength 0..1 and how long the trigger stays "live" after its date
SPEC = {
    "filing_crossed_60": (1.00, 180, "A UK entity's reported average crossed 60 days"),
    "filing_worsened": (0.70, 180, "A UK entity reported slower payment than a year earlier"),
    "es_pmp_rose": (0.70, 365, "The Spanish average payment period rose"),
    "terms_changed_longer": (0.80, 240, "A UK entity reported longer payment terms"),
    "terms_changed_other": (0.40, 240, "A UK entity reported changed payment terms"),
    "terms_changed_shorter": (0.30, 240, "A UK entity reported shorter payment terms"),
    "scf_started": (0.60, 365, "A UK entity newly reports offering supply chain finance"),
    "einvoicing_started": (0.50, 365, "A UK entity newly reports offering e-invoicing"),
    "cfo_change": (0.90, 180, "New CFO announced"),
    "results_date": (0.40, 0, "Results due"),
    "einvoicing_mandate": (0.50, 0, "E-invoicing mandate deadline (binds the buyer itself)"),
    "einvoicing_mandate_suppliers": (0.30, 0, "E-invoicing mandate deadline (binds the buyer's small suppliers)"),
    "sf_disclosed": (0.30, 180, "Supplier finance programme disclosed in the annual report (context: can mean extended terms)"),
    "dinner_city": (0.60, 0, "Next dinner in the account's country"),
}
WORSENED_MIN_DAYS = 45   # getting slower only counts once an entity is clearly slow (critic: "worsened to 25 days" headlined)
UPCOMING_WINDOW = {"results_date": 45, "einvoicing_mandate": 540, "einvoicing_mandate_suppliers": 540, "dinner_city": 60}


def _row(cid, typ, d, text, url, scope=None, extra=None):
    return {"company_id": cid, "trigger_type": typ, "trigger_date": str(d)[:10] if d is not None else None, "text": text,
            "evidence_url": url, "scope": scope, **(extra or {})}


def build(today: date | None = None, write: bool = False) -> pd.DataFrame:
    """Compute the trigger table for `today`. Writes data/processed/triggers.* only with write=True (`make triggers`):
    the MCP server, the skill and the queue call this read-only."""
    today = today or date.today()
    comp = q.companies()
    acc = comp[comp.excluded_reason.isna()]
    ids = set(acc.company_id)
    rows: list[dict] = []

    # --- UK filings, per linked entity (extreme values are not triggers: they are verification cases)
    e = q.uk_entities()
    e = e[e.company_id.isin(ids) & e.has_usable_report & ~e.latest_is_stale & e.avg_days_to_pay.notna()]
    full = pd.read_parquet(P / "uk_entity_latest.parquet", columns=["company_number", "yoy_avg_days_to_pay"])
    e = e.merge(full, on="company_number", how="left")
    e = e[~((e.avg_days_to_pay >= EXTREME_DAYS) | (e.trend_days_yoy.abs() >= EXTREME_YOY_JUMP))]
    for r in e.itertuples():
        nm = q.nice_name(r.company_name)
        if pd.notna(r.yoy_avg_days_to_pay) and (abs(r.avg_days_to_pay - r.yoy_avg_days_to_pay) >= EXTREME_YOY_JUMP
                                                or (r.yoy_avg_days_to_pay > 0 and r.avg_days_to_pay / r.yoy_avg_days_to_pay >= 4)):
            continue   # a jump this large is a verification case (re-filing, entity change), not a trigger
        if pd.notna(r.yoy_avg_days_to_pay) and r.avg_days_to_pay >= 60 > r.yoy_avg_days_to_pay:
            rows.append(_row(r.company_id, "filing_crossed_60", r.filing_date,
                             f"{nm} (single UK entity) now reports {r.avg_days_to_pay:.0f} days to pay on average, up from {r.yoy_avg_days_to_pay:.0f} a year earlier",
                             r.source_url, "UK entity", {"entity_value_gbp": r.value_paid_total_gbp}))
        elif pd.notna(r.trend_days_yoy) and r.trend_days_yoy >= 5 and r.avg_days_to_pay >= WORSENED_MIN_DAYS:
            rows.append(_row(r.company_id, "filing_worsened", r.filing_date,
                             f"{nm} (single UK entity) reports {r.avg_days_to_pay:.0f} days to pay on average, {r.trend_days_yoy:.0f} more than a year earlier",
                             r.source_url, "UK entity", {"entity_value_gbp": r.value_paid_total_gbp}))

    # --- Spain
    for r in acc[acc.es_pmp_days.notna() & acc.es_prior_year_pmp_days.notna()].itertuples():
        if r.es_pmp_days - r.es_prior_year_pmp_days >= 3:
            rows.append(_row(r.company_id, "es_pmp_rose", f"{int(r.es_fiscal_year) + 1}-03-31",
                             f"Average supplier payment period in Spain rose from {r.es_prior_year_pmp_days:.0f} to {r.es_pmp_days:.0f} days in FY{int(r.es_fiscal_year)}",
                             r.es_report_url if isinstance(r.es_report_url, str) else r.es_source_url, "Spanish entities",
                             {"date_is_approximate": True}))

    # --- UK field signals (terms changed, SCF or e-invoicing started)
    fs = P / "uk_field_signals.csv"
    if fs.exists():
        s = pd.read_csv(fs)
        s = s[s.company_id.isin(ids) & s.signal_type.isin(SPEC)]
        for r in s.itertuples():
            rows.append(_row(r.company_id, r.signal_type, r.observed_at, r.text, r.evidence_url, "UK entity"))

    # --- supplier finance disclosure (IAS 7 / IFRS 7 amendments, ASU 2022-04): dated at the fiscal year end
    # plus 90 days (filing dates vary; marked approximate). Only programmes confirmed by two readers or by QA.
    sfp = P / "supplier_finance.parquet"
    if sfp.exists():
        sf = pd.read_parquet(sfp)
        sf = sf[sf.company_id.isin(ids) & sf.programme_confirmed.fillna(False).astype(bool) & sf.period_end.notna()]
        for r in sf.itertuples():
            amt = f" of {r.currency} {r.obligation_amount / 1e6:,.0f}m" if pd.notna(r.obligation_amount) and isinstance(r.currency, str) else ""
            d = (pd.Timestamp(r.period_end) + pd.Timedelta(days=90)).date()
            rows.append(_row(r.company_id, "sf_disclosed", d,
                             f"Annual report for the year to {str(r.period_end)[:10]} discloses a supplier finance programme{amt} outstanding",
                             r.source_url, "group", {"date_is_approximate": True}))

    # --- private: CFO change and results dates (no names here)
    ad = ROOT / "data" / "private" / "account_dates.csv"
    if ad.exists():
        a = pd.read_csv(ad)
        for r in a[a.company_id.isin(ids)].itertuples():
            if isinstance(getattr(r, "cfo_change_announced", None), str) and r.cfo_change_announced:
                eff = getattr(r, "cfo_change_effective", None)
                rows.append(_row(r.company_id, "cfo_change", r.cfo_change_announced,
                                 "New CFO announced" + (f", effective {eff}" if isinstance(eff, str) and eff else ""),
                                 getattr(r, "cfo_change_url", None), "group", {"private_source": True}))
            if isinstance(getattr(r, "next_results_date", None), str) and r.next_results_date:
                typ = getattr(r, "next_results_type", "")
                rows.append(_row(r.company_id, "results_date", r.next_results_date,
                                 f"{typ if isinstance(typ, str) and typ else 'Results'} due {r.next_results_date}".strip(),
                                 getattr(r, "next_results_url", None), "group", {"private_source": True}))

    # --- e-invoicing mandates by HQ country
    mp = ROOT / "config" / "einvoicing_mandates.yaml"
    if mp.exists():
        for m in (yaml.safe_load(mp.read_text()) or {}).get("mandates", []):
            if not m.get("date") or not m.get("source_url") or not m.get("verified"):
                continue
            binds = m.get("binds", "buyer_directly")
            if binds == "member_states":
                continue
            typ = "einvoicing_mandate" if binds == "buyer_directly" else "einvoicing_mandate_suppliers"
            text = m["text"] if binds == "buyer_directly" else \
                f"{m['text']} This binds the account's smaller suppliers, not the account itself: a supplier-onboarding angle."
            for r in acc[(acc.country == m["country"]) & (acc.priority_tier <= 2)].itertuples():
                rows.append(_row(r.company_id, typ, m["date"], text, m["source_url"], f"country {m['country']}"))

    # --- dinner calendar by HQ country
    # an undated next dinner is dated today and marked approximate: it is live until a real date is set locally
    for d in q.dinner_calendar():
        if not q.dinner_upcoming(d, today):
            continue
        on_list = {a["company_id"] for a in q.dinner_shortlist(d["city"], 100)["accounts"]}
        for cid in on_list:
            rows.append(_row(cid, "dinner_city", d["date"] or today, f"{q.dinner_title(d['city'], d['date'])}: account is on the {d['country']} shortlist",
                             None, f"country {d['country']}", {"date_is_approximate": d["date"] is None}))

    t = pd.DataFrame(rows)
    if t.empty:
        t = pd.DataFrame(columns=["company_id", "trigger_type", "trigger_date", "text", "evidence_url", "scope"])
    t["trigger_date"] = pd.to_datetime(t.trigger_date, errors="coerce").dt.date
    t = t[t.trigger_date.notna()]
    t["strength"] = t.trigger_type.map(lambda k: SPEC[k][0])
    t["days_from_today"] = t.trigger_date.map(lambda d: (d - today).days)

    def live(r) -> bool:
        if r.trigger_type in UPCOMING_WINDOW:                      # future-dated: live when inside the lead window
            return 0 <= r.days_from_today <= UPCOMING_WINDOW[r.trigger_type]
        return -SPEC[r.trigger_type][1] <= r.days_from_today <= 0  # past-dated: live until it ages out

    t["is_live"] = [live(r) for r in t.itertuples()] if len(t) else []
    name = dict(zip(comp.company_id, comp.name))
    t.insert(1, "company", t.company_id.map(name))
    for c in ("private_source", "date_is_approximate"):
        if c not in t:
            t[c] = False
        t[c] = t[c].fillna(False).astype(bool)
    t["source_type"] = "chase_index_trigger"
    t["built_at"] = today.isoformat()
    t = t.sort_values(["is_live", "strength", "trigger_date"], ascending=[False, False, False]).reset_index(drop=True)
    # tracked files never carry a private source URL (a press-release slug can contain a person's name):
    # the URL stays in data/private/account_dates.csv
    t.loc[t.private_source, "evidence_url"] = None
    if write:
        t.to_parquet(P / "triggers.parquet", index=False)
        t.to_csv(P / "triggers.csv", index=False)
    return t


def since(day: str | date, include_private: bool = True) -> pd.DataFrame:
    """Triggers dated on or after `day` (past events) plus upcoming ones inside their lead window."""
    p = P / "triggers.parquet"
    t = pd.read_parquet(p) if p.exists() else build()
    day = pd.to_datetime(day).date()
    today = date.today()
    upcoming = t.trigger_type.isin(UPCOMING_WINDOW)
    t = t[(~upcoming & (t.trigger_date >= day) & (t.trigger_date <= today)) | (upcoming & t.is_live)]
    return t if include_private else t[~t.private_source]


if __name__ == "__main__":
    t = build(write=True)
    print(len(t), "triggers;", int(t.is_live.sum()), "live")
    print(t[t.is_live].trigger_type.value_counts().to_dict())
