"""Scores, tiers, estimates and the master company table.

Reads the processed tables, writes:
  data/processed/companies.parquet (+csv)   master table: one row per universe company, everything joined
  data/processed/scores.parquet (+csv)      ids, scores, tier, rationale
  outputs/targets/target_list.csv           top 100 with scores, tier, rationale, evidence links

Every weight and assumption comes from config/assumptions.yaml. Scores are deterministic.
Run: python -m chase.score.build
"""
from __future__ import annotations

import json
from datetime import date
from pathlib import Path

import pandas as pd
import yaml

from chase.resolve.names import norm

ROOT = Path(__file__).resolve().parents[3]
P = ROOT / "data" / "processed"
INTERIM = ROOT / "data" / "interim"
GBP_USD_APPROX = 1.27   # plausibility guard only (config/fx_rates.yaml)
EUROPE = set("AT BE BG CH CY CZ DE DK EE ES FI FR GB GR HR HU IE IS IT LI LT LU LV MT NL NO PL PT RO SE SI SK".split())


def lin(x, lo, hi):
    if x is None or pd.isna(x):
        return None
    return float(max(0.0, min(1.0, (x - lo) / (hi - lo))))


def nn(v):
    return None if v is None or (isinstance(v, float) and pd.isna(v)) or v is pd.NA else v


def weighted(parts: dict[str, tuple[float | None, float]], renormalise: bool = False) -> tuple[float, dict]:
    """parts: name -> (share 0..1 or None, weight). A missing part scores zero by default (conservative:
    missing evidence must not inflate a score). With renormalise=True missing parts are dropped instead."""
    avail = {k: v for k, v in parts.items() if v[0] is not None}
    tot = sum(w for _, w in (avail if renormalise else parts).values())
    if not tot:
        return 0.0, {}
    score = 100 * sum(s * w for s, w in avail.values()) / tot
    return round(score, 1), {k: round(100 * s * w / tot, 1) for k, (s, w) in avail.items()}


# ---------------------------------------------------------------- joins
def spain_to_universe(u: pd.DataFrame) -> pd.DataFrame:
    es_path = P / "es_pmp.parquet"
    if not es_path.exists():
        return pd.DataFrame(columns=["company_id"])
    es = pd.read_parquet(es_path)
    ib = pd.read_csv(INTERIM / "ibex35_constituents.csv")
    isin2id, name2id = {}, {}
    for r in u.itertuples():
        for i in str(r.isin or "").split("|"):
            if i:
                isin2id[i] = r.company_id
        for n in [r.name] + str(r.legal_names or "").split("|") + str(r.aliases or "").split("|"):
            k = norm(n)
            if len(k) >= 4:
                name2id.setdefault(k, r.company_id)
    isin_col = next((c for c in ib.columns if c.lower() == "isin"), None)
    t2id = {}
    for r in ib.itertuples():
        cid = isin2id.get(getattr(r, isin_col)) if isin_col and isinstance(getattr(r, isin_col), str) else None
        cid = cid or name2id.get(norm(r.company_name))
        if cid:
            t2id[r.ticker] = cid
    es["company_id"] = es.ticker.map(t2id)
    es.to_parquet(es_path, index=False)   # keep the link in the processed table
    es.to_csv(P / "es_pmp.csv", index=False)
    es = es[es.company_id.notna() & es.pmp_days.notna()].drop_duplicates("company_id")
    ren = {"pmp_days": "es_pmp_days", "ratio_paid_days": "es_ratio_paid_days", "ratio_pending_days": "es_ratio_pending_days",
           "prior_year_pmp_days": "es_prior_year_pmp_days", "fiscal_year": "es_fiscal_year",
           "pct_invoices_paid_within_legal_max_by_value": "es_pct_within_legal_max_by_value",
           "pct_invoices_paid_within_legal_max_by_number": "es_pct_within_legal_max_by_number",
           "scope": "es_scope", "source_url": "es_source_url", "human_readable_report_url": "es_report_url",
           "confidence": "es_confidence", "ticker": "es_ticker", "quoted_snippet": "es_quoted_snippet"}
    return es.rename(columns=ren)[["company_id"] + list(ren.values())]


def uk_filing_dates() -> pd.DataFrame:
    """Latest filing per group, with the URL of THAT report (not the slowest entity's)."""
    m = pd.read_parquet(P / "uk_entity_group_map.parquet")
    from chase.resolve.uk_rollup import EXTREME_DAYS, EXTREME_YOY_JUMP
    e = pd.read_parquet(P / "uk_entity_latest.parquet", columns=["company_number", "company_name", "filing_date", "source_url",
                                                                  "has_usable_report", "latest_is_stale", "avg_days_to_pay", "trend_days_yoy"])
    e = e[e.has_usable_report & ~e.latest_is_stale & e.avg_days_to_pay.notna()]
    e = e[~((e.avg_days_to_pay >= EXTREME_DAYS) | (e.trend_days_yoy.abs() >= EXTREME_YOY_JUMP))]   # same exclusion as the group figures
    j = m.merge(e, on="company_number").sort_values("filing_date")
    last = j.groupby("company_id").tail(1)
    return last[["company_id", "filing_date", "source_url", "company_name"]].rename(columns={
        "filing_date": "uk_latest_filing_date", "source_url": "uk_latest_filing_url", "company_name": "uk_latest_filing_entity"})


def dpo_wide() -> pd.DataFrame:
    d = pd.read_parquet(P / "dpo.parquet")
    a = d[d.year_rank == 1].set_index("company_id")
    b = d[d.year_rank == 2].set_index("company_id")
    out = pd.DataFrame({
        "dpo": a.dpo, "dpo_flag": a.dpo_flag, "dpo_fiscal_year": a.fiscal_year, "dpo_period_end": a.period_end,
        "dpo_currency": a.currency, "dpo_cost_of_sales": a.cost_of_sales, "dpo_payables": a.payables,
        "dpo_cost_basis": a.cost_basis, "dpo_payables_basis": a.payables_basis, "dpo_confidence": a.confidence,
        "dpo_source": a.dpo_source, "dpo_source_url": a.filing_url.fillna(a.source_url),
        "dpo_sector_median": a.sector_median_dpo, "dpo_sector_n": a.sector_n,
    })
    out["dpo_prior"] = b.dpo.reindex(out.index)
    out["dpo_prior_flag"] = b.dpo_flag.reindex(out.index)
    return out.reset_index()


UK_FIELD_SIGNAL_TYPES = ("terms_changed_longer", "scf_started", "einvoicing_started", "dispute_share_high")


def load_signals() -> pd.DataFrame:
    """Web signals (signals.csv) + the dated UK filing-field signals + confirmed supplier finance disclosures.
    Same columns everywhere: company_id, signal_type, text, evidence_url, observed_at."""
    cols = ["company_id", "signal_type", "text", "evidence_url", "observed_at"]
    parts = []
    for name, keep in (("signals.csv", None), ("uk_field_signals.csv", UK_FIELD_SIGNAL_TYPES)):
        p = P / name
        if p.exists():
            s = pd.read_csv(p)
            parts.append(s[s.signal_type.isin(keep)] if keep else s)
    sfp = P / "supplier_finance.parquet"
    if sfp.exists():
        sf = pd.read_parquet(sfp)
        sf = sf[sf.programme_confirmed.fillna(False).astype(bool)]
        parts.append(pd.DataFrame({
            "company_id": sf.company_id, "signal_type": "sf_disclosed",
            "text": [f"Annual report for the year to {str(r.period_end)[:10]} discloses a supplier finance programme"
                     + (f" with {r.currency} {r.obligation_amount / 1e6:,.0f}m outstanding" if pd.notna(r.obligation_amount) and isinstance(r.currency, str) else "")
                     for r in sf.itertuples()],
            "evidence_url": sf.source_url, "observed_at": sf.period_end}))
    if not parts:
        return pd.DataFrame(columns=cols)
    s = pd.concat([x[cols] for x in parts], ignore_index=True)
    return s[s.evidence_url.notna()]


def group_cost_usd(r) -> float | None:
    """Group cost of sales in USD (approx.), for plausibility checks only."""
    cost, rev, rev_usd = nn(r.dpo_cost_of_sales), nn(r.revenue), nn(r.revenue_usd)
    if cost and rev and rev_usd and r.dpo_currency == r.revenue_currency:
        return float(cost) * float(rev_usd) / float(rev)
    return float(rev_usd) * 0.6 if rev_usd else None


def uk_value_implausible(r) -> bool:
    """UK entities' annualised invoice value above half of the whole group's cost base (all of it for UK groups): almost certainly
    intercompany purchases by a regional hub (Garmin Europe) or a unit error in the filing."""
    ukv, gc = nn(r.uk_value_paid_total_gbp), group_cost_usd(r)
    # a UK-headquartered group can legitimately run most of its purchasing through UK entities
    limit = 2.5 if r.country == "GB" else 0.5     # UK groups: only catch unit errors (VAT, capex and intercompany inflate the reported value)
    return bool(ukv and gc and float(ukv) * 2 * GBP_USD_APPROX > limit * gc)


# ---------------------------------------------------------------- scoring
def score_row(r, cfg, sig_rows: pd.DataFrame, today: date) -> dict:
    sc = cfg["scoring"]
    out: dict = {}

    # ---- fit
    f = sc["fit"]
    rev_share = next(s for lo, s in f["revenue_bands_usd"] if (r.revenue_usd or 0) >= float(lo))
    geo = f["geography"]
    c = r.country
    has_local = nn(r.uk_entities_n) is not None or nn(r.es_pmp_days) is not None
    if c in geo["excluded"]:
        geo_share = 0.0
    elif c in geo["core"]:
        geo_share = geo["core_share"]
    elif c in EUROPE:
        geo_share = geo["europe_share"]
    elif c == "US":
        geo_share = geo["us_share"]
    else:
        geo_share = geo["other_share"]
    if has_local and c not in geo["excluded"]:
        geo_share = max(geo_share, geo["local_reporting_floor"])
    sector_share = f["sector_share"].get(r.sector, f["sector_share"]["other"])
    erp = sig_rows[sig_rows.signal_type == "erp_sap"]
    erp_share = 1.0 if len(erp) else f["erp_unknown_share"]
    emp = nn(r.employees)
    breadth = 0.5 if emp is None else (1.0 if emp >= 50000 else 0.7 if emp >= 10000 else 0.4)
    w = f["weights"]
    fit, fit_parts = weighted({"revenue": (rev_share, w["revenue"]), "geography": (geo_share, w["geography"]),
                               "sector": (sector_share, w["sector"]), "erp": (erp_share, w["erp"]),
                               "supplier_breadth": (breadth, w["supplier_breadth"])})
    if c in geo["excluded"] or r.not_a_company:
        fit = 0.0
    out.update(fit_score=fit, fit_parts=json.dumps(fit_parts))

    # ---- pain
    p = sc["pain"]
    tw = p["tier1_weights"]
    cands = []
    if nn(r.uk_avg_days_to_pay_mean) is not None:
        s, parts = weighted({
            "days": (lin(r.uk_avg_days_to_pay_mean, p["days_floor"], p["days_cap"]), tw["days"]),
            "pct_late": (lin(nn(r.uk_pct_paid_late_mean), 0, p["pct_late_cap"]), tw["pct_late"]),
            "pct_over_60": (lin(nn(r.uk_pct_paid_over_60_mean), 0, p["pct_over_60_cap"]), tw["pct_over_60"]),
            "trend": (lin(nn(r.uk_trend_days_yoy_mean), 0, p["trend_cap_days"]), tw["trend"])})
        # materiality: a group whose matched UK entities pay few invoices is weaker evidence about the group
        ukv = nn(r.uk_value_paid_total_gbp)
        mat = p["uk_materiality_unknown"] if ukv is None else next(f for lo, f in p["uk_materiality_bands_gbp"] if ukv * 2 >= float(lo))
        if uk_value_implausible(r):
            mat = min(mat, p["uk_materiality_implausible"])   # likely intercompany purchases or a unit error
        parts["uk_materiality_factor"] = mat
        s = round(s * mat, 1)
        cands.append((s, "uk_reported", parts, r.uk_avg_days_to_pay_mean))
    if nn(r.es_pmp_days) is not None:
        beyond = None if nn(r.es_pct_within_legal_max_by_value) is None else 100 - r.es_pct_within_legal_max_by_value
        trend = None if nn(r.es_prior_year_pmp_days) is None else r.es_pmp_days - r.es_prior_year_pmp_days
        s, parts = weighted({
            "days": (lin(r.es_pmp_days, p["days_floor"], p["days_cap"]), tw["days"]),
            "pct_late": (lin(beyond, 0, p["pct_late_cap"]), tw["pct_late"]),
            "pct_over_60": (lin(beyond, 0, p["pct_over_60_cap"]), tw["pct_over_60"]),
            "trend": (lin(trend, 0, p["trend_cap_days"]), tw["trend"])})
        cands.append((s, "es_reported", parts, r.es_pmp_days))
    if cands:
        # home-country evidence first for Spanish groups, otherwise the stronger reported evidence
        cands.sort(key=lambda x: (not (x[1] == "es_reported" and c == "ES"), -x[0]))
        s, basis, parts, days = cands[0]
        out.update(pain_score=s, pain_evidence_tier=1, pain_basis=basis, pain_parts=json.dumps(parts), pain_days=float(days))
    elif nn(r.dpo) is not None and r.dpo_flag == "ok" and nn(r.dpo_sector_median) and r.dpo <= p["dpo_max_plausible"]:
        # proxy quality: rows built on a broad payables line or a fallback cost base carry confidence < 1
        # and are scaled down, so they cannot reach Tier 1 on the proxy alone (see evals/reports/dpo_check.md)
        ratio = r.dpo / r.dpo_sector_median
        conf = float(nn(r.dpo_confidence) or 0.7)
        s = round(p["tier2_max"] * lin(ratio, 0.75, p["dpo_ratio_cap"]) * conf, 1)
        out.update(pain_score=s, pain_evidence_tier=2, pain_basis="computed_dpo_proxy",
                   pain_parts=json.dumps({"dpo_vs_sector_median_ratio": round(ratio, 2), "dpo_confidence_factor": conf}),
                   pain_days=float(r.dpo))
    else:
        out.update(pain_score=0.0, pain_evidence_tier=None, pain_basis="no_evidence", pain_parts="{}", pain_days=None)

    # ---- signals ("why now"), each with an evidence URL
    s_cfg = sc["signal"]
    sw = s_cfg["weights"]
    signals = []
    trend_d, trend_url, trend_txt = None, None, None
    if nn(r.uk_trend_days_yoy_mean) is not None and r.uk_trend_days_yoy_mean >= s_cfg["trend_min_days"]:
        trend_d, trend_url = r.uk_trend_days_yoy_mean, r.uk_worst_entity_source_url
        if r.uk_trend_entities_n == 1 and (r.uk_entities_n or 1) > 1:
            trend_txt = (f"One of its {int(r.uk_entities_n)} UK entities has a report from a year earlier, and its average days to pay "
                         f"rose by {r.uk_trend_days_yoy_mean:.1f} days")
        elif r.uk_trend_entities_n == 1:
            trend_txt = f"The UK entity's average days to pay rose by {r.uk_trend_days_yoy_mean:.1f} days year on year"
        else:
            trend_txt = (f"UK entities' days to pay: median entity change {r.uk_trend_days_yoy_median:+.0f} days year on year "
                         f"({int(r.uk_trend_entities_slower_n)} of {int(r.uk_trend_entities_n)} entities with a prior report got slower)")
    elif nn(r.es_pmp_days) is not None and nn(r.es_prior_year_pmp_days) is not None and \
            r.es_pmp_days - r.es_prior_year_pmp_days >= s_cfg["trend_min_days"]:
        trend_d, trend_url = r.es_pmp_days - r.es_prior_year_pmp_days, r.es_source_url
        trend_txt = f"Average supplier payment period in Spain rose from {r.es_prior_year_pmp_days:.0f} to {r.es_pmp_days:.0f} days"
    elif out["pain_evidence_tier"] == 2 and nn(r.dpo_prior) is not None and r.dpo_prior_flag == "ok" and r.dpo - r.dpo_prior >= 5:
        trend_d, trend_url = (r.dpo - r.dpo_prior) / 2, r.dpo_source_url   # proxy: half weight
        trend_txt = f"Computed DPO (proxy) rose from {r.dpo_prior:.0f} to {r.dpo:.0f} days year on year"
    if trend_txt:
        signals.append({"type": "trend_worsening", "text": trend_txt, "url": trend_url})
    fresh = False
    if nn(r.uk_latest_filing_date) is not None:
        age = (today - pd.Timestamp(r.uk_latest_filing_date).date()).days
        if 0 <= age <= s_cfg["new_evidence_days"]:
            fresh = True
            signals.append({"type": "new_evidence", "text": f"Latest statutory UK payment report filed {str(r.uk_latest_filing_date)[:10]} ({str(r.uk_latest_filing_entity).title()})",
                            "url": r.uk_latest_filing_url})
    no_code = nn(r.uk_entities_n) is not None and not bool(r.uk_payment_code_any)
    if no_code:
        signals.append({"type": "code_status", "text": "No UK reporting entity states membership of a payment code",
                        "url": r.uk_worst_entity_source_url})
    long_terms = nn(r.uk_max_contractual_period_days_max) is not None and r.uk_max_contractual_period_days_max >= s_cfg["long_terms_days"]
    if long_terms:
        signals.append({"type": "long_terms", "text": f"Maximum contractual payment period of {int(r.uk_max_contractual_period_days_max)} days reported by a UK entity",
                        "url": r.uk_worst_entity_source_url})
    if nn(r.uk_entities_n) is not None and bool(r.uk_offers_supply_chain_finance_any):
        signals.append({"type": "scf_offered", "text": "A UK entity reports offering supply chain finance to suppliers: ask which suppliers it reaches, at whose cost, and whether it lengthened terms",
                        "url": r.uk_worst_entity_source_url})
    hiring = sig_rows[sig_rows.signal_type == "finance_hiring"]
    press = sig_rows[sig_rows.signal_type == "press"]
    # UK filing fields: one line per type (the first entity), the score counts the type once
    field = sig_rows[sig_rows.signal_type.isin(UK_FIELD_SIGNAL_TYPES + ("sf_disclosed",))].drop_duplicates("signal_type")
    for _, x in pd.concat([hiring, press, field, erp]).iterrows():
        signals.append({"type": x.signal_type, "text": x.text, "url": x.evidence_url})
    has = set(field.signal_type)
    signal = (sw["trend_worsening"] * (lin(trend_d, 0, sc["pain"]["trend_cap_days"]) or 0)
              + sw["finance_hiring"] * (1 if len(hiring) else 0) + sw["press"] * (1 if len(press) else 0)
              + sw["code_status"] * (1 if no_code else 0) + sw["new_evidence"] * (1 if fresh else 0)
              + sw["long_terms"] * (1 if long_terms else 0)
              + sum(sw.get(k, 0) for k in has))
    signal = min(100.0, signal)
    out.update(signal_score=round(float(signal), 1), signals=json.dumps(signals, ensure_ascii=False), signals_n=len(signals))

    # ---- tier
    t = sc["tiers"]
    excluded_reason = None
    if r.not_a_company:
        excluded_reason = "not_a_company"
    elif r.is_subsidiary_or_unit or nn(r.parent_company_id):
        excluded_reason = "unit_of_larger_group"
    elif c in geo["excluded"]:
        excluded_reason = "excluded_country"
    elif r.sector == "financials":
        excluded_reason = "financial_sector"   # banks and insurers are outside the buyer-side ICP
    if fit < t["fit_gate"] or excluded_reason:
        tier, base = 3, 3
    else:
        base = 1 if out["pain_score"] >= t["tier1_min_pain"] else 2 if out["pain_score"] >= t["tier2_min_pain"] else 3
        tier = max(1, base - 1) if signal >= t["signal_upgrade_min"] and base > 1 else base
    out.update(priority_tier=tier, base_tier=base, tier_upgraded_by_signal=bool(tier < base), excluded_reason=excluded_reason)
    ev_bonus = 1 if out["pain_evidence_tier"] == 1 else 0
    pw = sc["priority_score_weights"]
    out["priority_score"] = round(pw["pain"] * out["pain_score"] + pw["fit"] * fit + pw["signal"] * out["signal_score"], 1)
    out["_sort"] = (tier, -ev_bonus, -out["priority_score"])
    return out


# ---------------------------------------------------------------- estimates
def estimates(r, cfg) -> dict:
    e = cfg["estimates"]
    out = {"estimate": True}
    days = nn(r.pain_days)
    cost = nn(r.dpo_cost_of_sales)
    if cost is not None and cost > 0:
        spend, basis, cur = float(cost), f"cost_of_sales_fy{int(r.dpo_fiscal_year)}" + ("" if r.dpo_cost_basis == "cost_of_sales" else f"({r.dpo_cost_basis})"), r.dpo_currency
    elif nn(r.revenue) is not None:
        ratio = e["external_spend_ratio_by_sector"].get(r.sector, e["external_spend_ratio_default"])
        spend, basis, cur = float(r.revenue) * ratio, f"revenue_x_assumed_external_spend_ratio_{ratio}", r.revenue_currency
    else:
        spend, basis, cur = None, "unavailable", None
    out.update(est_group_spend_proxy=spend, est_group_spend_basis=basis, est_currency=cur)

    def calc(base_amount, d):
        if base_amount is None or d is None:
            return {}
        acc = min(e["max_days_accelerated"], max(0.0, d - e["early_pay_day"]))
        res = {"excess_days_vs_30": round(max(0.0, d - 30), 1), "excess_days_vs_60": round(max(0.0, d - 60), 1),
               "cash_beyond_30": base_amount * max(0.0, d - 30) / 365, "cash_beyond_60": base_amount * max(0.0, d - 60) / 365,
               "days_accelerated": round(acc, 1)}
        for k, s in e["scenarios"].items():
            res[f"discount_{k}"] = base_amount * s["share_eligible"] * s["annualised_rate"] * acc / 365
        return res

    # Group block: group spend needs group-level days. Local reported days (UK or Spanish entities) are never
    # applied to global spend. Only a clean computed DPO (proxy) qualifies; otherwise there is no group estimate.
    gdays = float(r.dpo) if nn(r.dpo) is not None and r.dpo_flag == "ok" and r.dpo <= cfg["scoring"]["pain"]["dpo_max_plausible"] \
        and nn(r.dpo_confidence) and r.dpo_confidence >= 1.0 and cost is not None else None
    g = calc(spend if gdays is not None else None, gdays)
    for k in ("excess_days_vs_30", "excess_days_vs_60", "cash_beyond_30", "cash_beyond_60", "days_accelerated",
              "discount_low", "discount_base", "discount_high"):
        out[f"est_group_{k}"] = g.get(k)
    out["est_group_days"] = gdays
    out["est_group_days_basis"] = "computed_dpo_proxy" if gdays is not None else None
    # UK scope: reported invoice value of the matched UK entities (latest half-year reports), annualised x2
    ukv = nn(r.uk_value_paid_total_gbp)
    out["est_uk_note"] = None
    if uk_value_implausible(r):
        # self-reported invoice values contain unit errors and intercompany purchases; not a credible supplier-spend base
        out["est_uk_note"] = "uk_invoice_value_implausible_vs_group_cost_base_not_used"
    elif ukv is not None and nn(r.uk_avg_days_to_pay_mean) is not None:
        annual = float(ukv) * 2
        out["est_uk_annual_payments_gbp"] = annual
        for k, v in calc(annual, float(r.uk_avg_days_to_pay_mean)).items():
            out[f"est_uk_{k}"] = v
    return out


# ---------------------------------------------------------------- rationale
def money(v, cur=""):
    if v is None or pd.isna(v):
        return "n/a"
    a = abs(v)
    s = f"{v/1e9:.1f}bn" if a >= 1e9 else f"{v/1e6:.0f}m" if a >= 1e6 else f"{v/1e3:.0f}k"
    return f"{cur} {s}".strip()


def rationale(r) -> str:
    bits = []
    rev = f"{money(r.revenue, r.revenue_currency)} revenue ({str(r.revenue_period_end)[:4]})" if nn(r.revenue) else "revenue n/a"
    bits.append(f"{r.sector.replace('_', ' ')} group, {r.country or 'n/a'} HQ, {rev}; fit {r.fit_score:.0f}.")
    if r.pain_basis == "uk_reported":
        late = f", {r.uk_pct_paid_late_mean:.0f}% of invoices paid late" if nn(r.uk_pct_paid_late_mean) is not None else ""
        bits.append(f"Reported: its {int(r.uk_entities_n)} matched UK entit{'y pays' if r.uk_entities_n == 1 else 'ies pay'} in "
                    f"{r.uk_avg_days_to_pay_mean:.0f} days on average{late}; slowest entity {r.uk_worst_entity_days:.0f} days "
                    f"({r.uk_worst_entity_name}); pain {r.pain_score:.0f}.")
    elif r.pain_basis == "es_reported":
        bits.append(f"Reported: average supplier payment period in Spain of {r.es_pmp_days:.0f} days (FY{int(r.es_fiscal_year)}, statutory PMP); pain {r.pain_score:.0f}.")
    elif r.pain_basis == "computed_dpo_proxy":
        bits.append(f"No reported payment data; computed DPO (proxy) of {r.dpo:.0f} days vs sector median {r.dpo_sector_median:.0f}; pain {r.pain_score:.0f}.")
    else:
        bits.append("No payment evidence found.")
    sig = json.loads(r.signals)
    if sig:
        bits.append(f"Why now: {sig[0]['text']}.")
    if r.tier_upgraded_by_signal:
        bits.append("Upgraded one tier on signal strength.")
    if nn(r.excluded_reason):
        bits.append(f"Held in Tier 3: {r.excluded_reason.replace('_', ' ')}.")
    return " ".join(bits)


_NUM = __import__("re").compile(r"\d+(?:\.\d+)?")
_ALWAYS_OK = {"30", "32", "60", "1", "2", "3"}      # benchmarks and tier numbers


def numbers_ok(text: str, r) -> bool:
    allowed = set(_ALWAYS_OK)
    for v in r.values:
        if isinstance(v, (int, float)) and not isinstance(v, bool) and not pd.isna(v):
            for scale in (1, 1e6, 1e9):
                allowed |= {f"{v / scale:.0f}", f"{v / scale:.1f}"}
        elif isinstance(v, str):
            allowed |= set(_NUM.findall(v))
    return set(_NUM.findall(text.replace(",", ""))) <= allowed


def build() -> pd.DataFrame:
    cfg = yaml.safe_load((ROOT / "config" / "assumptions.yaml").read_text())
    u = pd.read_parquet(P / "universe.parquet")
    gm = pd.read_parquet(P / "uk_group_metrics.parquet").drop(
        columns=["group_name", "source_url", "source_type", "retrieved_at", "period_start", "period_end", "extraction_method", "confidence"])
    df = u.merge(gm, on="company_id", how="left").merge(uk_filing_dates(), on="company_id", how="left") \
          .merge(spain_to_universe(u), on="company_id", how="left").merge(dpo_wide(), on="company_id", how="left")
    for c in ["es_pmp_days", "es_prior_year_pmp_days", "es_pct_within_legal_max_by_value", "es_fiscal_year", "es_source_url"]:
        if c not in df:
            df[c] = None
    sig = load_signals()
    today = date.today()
    scored = []
    for r in df.itertuples(index=False):
        s = score_row(r, cfg, sig[sig.company_id == r.company_id], today)
        scored.append(s)
    df = pd.concat([df, pd.DataFrame(scored)], axis=1)
    est = [estimates(r, cfg) for r in df.itertuples(index=False)]
    df = pd.concat([df, pd.DataFrame(est)], axis=1)
    # how much of the group the UK evidence represents: annualised UK invoice value / group revenue (approx. FX)
    share = (df.uk_value_paid_total_gbp * 2 * GBP_USD_APPROX / df.revenue_usd).where(df.uk_value_paid_total_gbp.notna())
    df["uk_invoice_value_share_of_group_revenue"] = share.round(4)
    df["thin_evidence"] = (df.pain_basis == "uk_reported") & (share < cfg["scoring"]["thin_evidence_share"])
    df["rationale"] = [rationale(r) for r in df.itertuples(index=False)]
    df["rationale_method"] = "deterministic_template"
    # LLM-written rationales (validated against the row) override the template where present
    rp = P / "rationales_llm.csv"
    if rp.exists():
        llm = pd.read_csv(rp).drop_duplicates("company_id").set_index("company_id").rationale
        # the in-between model: an LLM may write the sentence, but every number in it must be a value of
        # this row as it is NOW (rounded to 0 or 1 decimals). Otherwise the template stays.
        used = rejected = 0
        for i, r in df[df.company_id.isin(llm.index)].iterrows():
            text = str(llm[r.company_id])
            if numbers_ok(text, r):
                df.at[i, "rationale"] = text
                df.at[i, "rationale_method"] = "llm_written_validated_against_row"
                used += 1
            else:
                rejected += 1
        print(f"LLM rationales: {used} used, {rejected} rejected by the row check (template kept)")
    df = df.sort_values("_sort").drop(columns="_sort").reset_index(drop=True)
    df["rank"] = range(1, len(df) + 1)
    df["scored_at"] = pd.Timestamp.now('UTC').strftime("%Y-%m-%dT%H:%M:%SZ")

    df.to_parquet(P / "companies.parquet", index=False)
    df.to_csv(P / "companies.csv", index=False)
    score_cols = ["company_id", "name", "rank", "priority_tier", "base_tier", "tier_upgraded_by_signal", "excluded_reason",
                  "priority_score", "fit_score", "pain_score", "signal_score", "pain_evidence_tier", "pain_basis", "pain_days",
                  "fit_parts", "pain_parts", "signals", "rationale", "rationale_method", "scored_at",
                  "source_url", "source_type", "retrieved_at", "period_start", "period_end", "extraction_method", "confidence"]
    sc_out = df[score_cols].copy()
    # a score's period is the period of the evidence it rests on; with no dated evidence, the scoring date
    today_s = date.today().isoformat()
    sc_out["period_end"] = (df.uk_period_end_max.where(df.pain_basis == "uk_reported")
                            .fillna(df.dpo_period_end.where(df.pain_basis == "computed_dpo_proxy"))
                            .fillna(df.period_end).fillna(today_s).astype(str).str[:10])
    sc_out["period_start"] = (df.uk_period_start_min.where(df.pain_basis == "uk_reported")
                              .fillna(df.period_start).fillna(today_s).astype(str).str[:10])
    sc_out["source_type"] = "chase_index_score(" + df.pain_basis + ")"
    sc_out["extraction_method"] = "deterministic_formula(config/assumptions.yaml)"
    sc_out.to_parquet(P / "scores.parquet", index=False)
    sc_out.to_csv(P / "scores.csv", index=False)

    tl_cols = ["rank", "company_id", "name", "country", "hq_city", "sector", "revenue", "revenue_currency", "revenue_usd",
               "priority_tier", "priority_score", "fit_score", "pain_score", "signal_score", "pain_evidence_tier", "pain_basis",
               "thin_evidence", "uk_invoice_value_share_of_group_revenue", "uk_entities_n", "uk_avg_days_to_pay_mean", "uk_pct_paid_late_mean", "uk_pct_paid_over_60_mean",
               "uk_trend_days_yoy_mean", "uk_worst_entity_name", "uk_worst_entity_days", "uk_worst_entity_source_url",
               "uk_period_end_max", "uk_min_match_confidence", "es_pmp_days", "es_fiscal_year", "es_source_url",
               "dpo", "dpo_fiscal_year", "dpo_sector_median", "dpo_source_url",
               "est_uk_annual_payments_gbp", "est_uk_cash_beyond_30", "est_uk_discount_low", "est_uk_discount_base", "est_uk_discount_high",
               "est_currency", "est_group_spend_proxy", "est_group_spend_basis", "est_group_discount_low", "est_group_discount_base",
               "est_group_discount_high", "estimate", "signals", "rationale", "revenue_source_url"]
    tl = df[df.excluded_reason.isna()].head(100)
    (ROOT / "outputs" / "targets").mkdir(parents=True, exist_ok=True)
    tl[[c for c in tl_cols if c in tl]].to_csv(ROOT / "outputs" / "targets" / "target_list.csv", index=False)
    return df


if __name__ == "__main__":
    d = build()
    print("companies", len(d), "tiers", d.priority_tier.value_counts().sort_index().to_dict(),
          "evidence", d.pain_evidence_tier.value_counts(dropna=False).to_dict())
    pd.set_option("display.width", 250)
    print(d[d.excluded_reason.isna()].head(30)[["rank", "name", "country", "sector", "priority_tier", "fit_score", "pain_score",
                                                  "signal_score", "pain_basis", "pain_days"]].to_string())
