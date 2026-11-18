"""One read-only query layer over data/processed. Used by the /chase-brief skill, the MCP server
and the site build, so there is exactly one implementation of every lookup.

No network calls, no writes. Every response separates reported data from estimates and carries
source URLs and periods.
"""
from __future__ import annotations

import datetime as _dt
import json
import os
import re
from functools import lru_cache
from pathlib import Path

import pandas as pd
import yaml

from chase.resolve.names import core, norm


def dinner_calendar() -> list[dict]:
    """The dinner cities from config/dinners.yaml, overridden by city from config/dinners.local.yaml (gitignored, where
    real dates live). No dates are committed: an undated city marked `next: true` is "the next dinner"."""
    cfg = ROOT / "config"
    base = yaml.safe_load((cfg / "dinners.yaml").read_text())["dinners"]
    lp = cfg / "dinners.local.yaml"
    over = {d["city"]: d for d in ((yaml.safe_load(lp.read_text()) or {}).get("dinners") or [])} if lp.exists() else {}
    out = []
    for d in base:
        d = {**d, **over.get(d["city"], {})}
        d["date"] = str(d["date"])[:10] if d.get("date") else None
        d["next"] = bool(d.get("next")) or d["date"] is not None
        out.append(d)
    return out


def dinner_upcoming(d: dict, today: "_dt.date") -> bool:
    """A dinner is upcoming when it is marked next and either has no date or its date has not passed."""
    return bool(d.get("next")) and (d.get("date") is None or pd.to_datetime(d["date"]).date() >= today)


def dinner_title(city: str, date: str | None) -> str:
    """'Munich dinner (2026-12-03)' when a date is set locally, else 'Next Munich dinner'."""
    return f"{city.title()} dinner ({date})" if date else f"Next {city.title()} dinner"

ROOT = Path(os.environ.get("CHASE_INDEX_ROOT") or Path(__file__).resolve().parents[2])
P = ROOT / "data" / "processed"
DISCLAIMER = "Independent project by Moritz Hanbuch."

# dinner cities -> how "local" is defined (HQ city names as they appear in the data, then country fallback)
CITIES = {
    "munich": {"country": "DE", "hq": {"munich", "münchen", "neubiberg", "unterföhring", "garching", "unterschleißheim", "ismaning"}},
    "paris": {"country": "FR", "hq": {"paris", "boulogne-billancourt", "courbevoie", "la défense", "puteaux", "nanterre",
                                      "issy-les-moulineaux", "levallois-perret", "neuilly-sur-seine", "saint-denis",
                                      "rueil-malmaison", "clichy", "massy", "vélizy-villacoublay", "montrouge", "saint-ouen-sur-seine"}},
    "london": {"country": "GB", "hq": {"london", "city of london", "westminster", "city of westminster", "uxbridge", "slough", "brentford", "weybridge"}},
    "madrid": {"country": "ES", "hq": {"madrid", "alcobendas", "pozuelo de alarcón", "las rozas de madrid", "boadilla del monte"}},
}
try:   # DACH slice: more Bavarian towns around Munich (config/dach_slice.yaml)
    CITIES["munich"]["hq"] |= set((yaml.safe_load((ROOT / "config" / "dach_slice.yaml").read_text()) or {}).get("munich_area_add") or [])
except FileNotFoundError:
    pass
# what counts as a hook worth saying to a CFO: clearly slower than the benchmark
HOOK_MIN = {"uk_reported": 45.0, "es_reported": 50.0, "dpo_ratio": 1.3}


def _nn(v):
    if v is None or v is pd.NA:
        return None
    if isinstance(v, float) and pd.isna(v):
        return None
    if hasattr(v, "item"):
        try:
            v = v.item()
        except (ValueError, AttributeError):
            pass
    if isinstance(v, (pd.Timestamp, _dt.date, _dt.datetime)):
        return str(v)[:10]
    return v


@lru_cache(maxsize=1)
def companies() -> pd.DataFrame:
    return pd.read_parquet(P / "companies.parquet")


@lru_cache(maxsize=1)
def uk_entities() -> pd.DataFrame:
    cols = ["company_number", "company_name", "period_start", "period_end", "filing_date", "avg_days_to_pay",
            "pct_paid_within_30", "pct_paid_31_60", "pct_paid_over_60", "pct_paid_late", "shortest_standard_payment_period_days",
            "longest_standard_payment_period_days", "max_contractual_payment_period_days", "trend_days_yoy",
            "has_usable_report", "latest_is_stale", "quality_flag", "source_url", "retrieved_at", "value_paid_total_gbp",
            "offers_supply_chain_finance", "offers_einvoicing", "participates_in_payment_codes"]
    e = pd.read_parquet(P / "uk_entity_latest.parquet", columns=cols)
    mp = P / "uk_entity_group_map.parquet"
    if mp.exists():
        m = pd.read_parquet(mp, columns=["company_number", "company_id", "group_name", "match_method", "match_confidence"])
        e = e.merge(m, on="company_number", how="left")
    return e


@lru_cache(maxsize=1)
def _index() -> list[tuple[str, str, str]]:
    out = []
    for r in companies().itertuples():
        names = [r.name] + str(r.legal_names or "").split("|") + str(r.aliases or "").split("|")[:12]
        for n in names:
            k = norm(n)
            if k:
                out.append((k, core(n), r.company_id))
    return out


def resolve(company: str) -> str | None:
    """company_id for a name or id; exact id, exact normalised name, then prefix/contains by rank."""
    df = companies()
    if company in set(df.company_id):
        return company
    k, c = norm(company), core(company)
    rank = dict(zip(df.company_id, df["rank"]))
    exact = [cid for nk, _, cid in _index() if nk == k]
    if exact:
        return min(exact, key=lambda x: rank[x])
    corem = [cid for _, ck, cid in _index() if ck == c and c]
    if corem:
        return min(corem, key=lambda x: rank[x])
    part = [cid for nk, _, cid in _index() if k and (nk.startswith(k + " ") or f" {k} " in f" {nk} ")]
    if part:
        return min(part, key=lambda x: rank[x])
    return None


def search_companies(query: str, country: str | None = None, sector: str | None = None, limit: int = 10) -> list[dict]:
    df = companies()
    k = norm(query)
    hits: dict[str, int] = {}
    for nk, _, cid in _index():
        if k and k in nk:
            score = 0 if nk == k else 1 if nk.startswith(k) else 2
            hits[cid] = min(hits.get(cid, 9), score)
    sub = df[df.company_id.isin(hits)].copy()
    if country:
        sub = sub[sub.country == country.upper()]
    if sector:
        sub = sub[sub.sector == sector.lower()]
    sub["_m"] = sub.company_id.map(hits)
    sub = sub.sort_values(["_m", "rank"]).head(limit)
    return [{"company_id": r.company_id, "name": r.name, "country": _nn(r.country), "sector": r.sector,
             "priority_tier": int(r.priority_tier), "has_reported_payment_data": _nn(r.pain_evidence_tier) == 1}
            for r in sub.itertuples()]


def _row(company: str):
    cid = resolve(company)
    if cid is None:
        return None
    df = companies()
    return df[df.company_id == cid].iloc[0]


def get_payment_profile(company: str) -> dict:
    r = _row(company)
    if r is None:
        return {"found": False, "query": company, "hint": "Try search_companies or lookup_uk_entity for a UK legal entity name."}
    out: dict = {"found": True, "company_id": r.company_id, "name": r["name"], "country": _nn(r.country), "sector": r.sector,
                 "reported": {}, "computed_proxy": None, "disclaimer": DISCLAIMER}
    if _nn(r.uk_entities_n) is not None:
        ents = uk_entities()
        mine = ents[(ents.company_id == r.company_id) & ents.has_usable_report & ~ents.latest_is_stale] \
            .sort_values("avg_days_to_pay", ascending=False)
        out["reported"]["uk"] = {
            "what": "Statutory UK payment practices reports filed by this group's UK legal entities. "
                    "UK entities only, not global group behaviour.",
            "estimate": False,
            "entities_n": int(r.uk_entities_n),
            "avg_days_to_pay_mean_of_entities": _nn(r.uk_avg_days_to_pay_mean),
            "aggregation": _nn(r.uk_days_aggregation),
            "avg_days_to_pay_simple_mean": _nn(r.uk_avg_days_to_pay_simple_mean),
            "pct_invoices_paid_late_mean": _nn(r.uk_pct_paid_late_mean),
            "pct_invoices_paid_over_60_days_mean": _nn(r.uk_pct_paid_over_60_mean),
            "trend_days_year_on_year_mean": _nn(r.uk_trend_days_yoy_mean),
            "trend_days_year_on_year_median": _nn(r.get("uk_trend_days_yoy_median")),
            "trend_entities_slower": _nn(r.get("uk_trend_entities_slower_n")), "trend_entities_compared": _nn(r.uk_trend_entities_n),
            "slowest_entity": {"name": r.uk_worst_entity_name, "avg_days_to_pay": _nn(r.uk_worst_entity_days),
                               "source_url": r.uk_worst_entity_source_url},
            "period": {"start": _nn(r.uk_period_start_min), "end": _nn(r.uk_period_end_max)},
            "entities_left_out_of_group_figures_as_extreme": _nn(r.get("uk_entities_excluded_extreme")),
            "entity_match_confidence_min": _nn(r.uk_min_match_confidence),
            "entity_match_methods": _nn(r.uk_match_methods),
            "entities": [{"name": e.company_name, "company_number": e.company_number,
                          "avg_days_to_pay": _nn(e.avg_days_to_pay),
                          "pct_paid_late": None if "pct_late_inconsistent" in str(e.quality_flag) else _nn(e.pct_paid_late),
                          "pct_paid_late_note": "reported late share contradicts the entity's own payment bands; not shown" if "pct_late_inconsistent" in str(e.quality_flag) else None,
                          "trend_days_yoy": _nn(e.trend_days_yoy), "invoice_value_gbp_half_year": _nn(e.value_paid_total_gbp),
                          "pct_paid_over_60": _nn(e.pct_paid_over_60),
                          "standard_terms_days": [_nn(e.shortest_standard_payment_period_days), _nn(e.longest_standard_payment_period_days)],
                          "max_contractual_days": _nn(e.max_contractual_payment_period_days),
                          "period_start": _nn(e.period_start), "period_end": _nn(e.period_end), "source_url": e.source_url}
                         for e in mine.head(15).itertuples()],
            "source_type": "uk_ppr_statutory_report",
        }
    if _nn(r.get("es_pmp_days")) is not None:
        out["reported"]["spain"] = {
            "what": "Statutory average supplier payment period (PMP, Ley 15/2010) from the notes to the annual accounts.",
            "estimate": False, "pmp_days": _nn(r.es_pmp_days), "prior_year_pmp_days": _nn(r.es_prior_year_pmp_days),
            "ratio_paid_days": _nn(r.es_ratio_paid_days), "ratio_pending_days": _nn(r.es_ratio_pending_days),
            "pct_paid_within_legal_max_by_value": _nn(r.es_pct_within_legal_max_by_value),
            "fiscal_year": _nn(r.es_fiscal_year), "scope": _nn(r.es_scope), "legal_maximum_days": 60,
            "source_url": _nn(r.es_report_url) or _nn(r.es_source_url), "extraction_confidence": _nn(r.es_confidence),
            "source_type": "es_annual_accounts_pmp_note",
        }
    if _nn(r.dpo_flag) is not None:
        out["computed_proxy"] = {
            "what": "Computed DPO (proxy) = trade payables / cost of sales x 365 from XBRL financial statements. "
                    "A balance-sheet proxy, not reported days to pay.",
            "estimate": False, "is_proxy": True, "dpo_days": _nn(r.dpo), "prior_year_dpo_days": _nn(r.dpo_prior),
            "flag": r.dpo_flag, "fiscal_year": _nn(r.dpo_fiscal_year), "period_end": _nn(r.dpo_period_end),
            "sector_median_dpo_days": _nn(r.dpo_sector_median), "payables_basis": _nn(r.dpo_payables_basis),
            "cost_basis": _nn(r.dpo_cost_basis), "confidence": _nn(r.dpo_confidence), "source_url": _nn(r.dpo_source_url),
            "source_type": f"{_nn(r.dpo_source)}_xbrl",
        }
    if not out["reported"] and not out["computed_proxy"]:
        out["note"] = "No payment evidence in the dataset for this company."
    return out


def _estimates(r) -> dict:
    cfg = yaml.safe_load((ROOT / "config" / "assumptions.yaml").read_text())["estimates"]
    est = {"estimate": True,
           "assumptions": {"early_pay_day": cfg["early_pay_day"], "max_days_accelerated": cfg["max_days_accelerated"],
                           "scenarios": cfg["scenarios"], "config_file": "config/assumptions.yaml",
                           "formula": "spend x share_eligible x annualised_rate x days_accelerated / 365"}}
    if _nn(r.get("est_uk_annual_payments_gbp")) is not None:
        est["uk_scope"] = {
            "basis": "Invoice value paid by the matched UK entities in their latest half-year reports, annualised x2 (reported base, estimated result)",
            "currency": "GBP", "annual_payments": _nn(r.est_uk_annual_payments_gbp),
            "days_used": _nn(r.uk_avg_days_to_pay_mean),
            "supplier_cash_beyond_30_days": _nn(r.est_uk_cash_beyond_30),
            "early_payment_discount_opportunity": {"low": _nn(r.est_uk_discount_low), "base": _nn(r.est_uk_discount_base), "high": _nn(r.est_uk_discount_high)}}
    if _nn(r.get("est_group_discount_base")) is not None:
        est["group_proxy"] = {
            "basis": f"Group cost of sales ({_nn(r.est_group_spend_basis)}) with group-level days from computed DPO (proxy), "
                     f"FY{_nn(r.dpo_fiscal_year)}. A balance-sheet proxy, not reported days to pay.",
            "currency": _nn(r.est_currency), "spend_proxy": _nn(r.est_group_spend_proxy), "days_used": _nn(r.est_group_days),
            "supplier_cash_beyond_30_days": _nn(r.est_group_cash_beyond_30),
            "early_payment_discount_opportunity": {"low": _nn(r.est_group_discount_low), "base": _nn(r.est_group_discount_base), "high": _nn(r.est_group_discount_high)}}
    if _nn(r.get("est_uk_note")):
        est["uk_scope_note"] = ("No UK-scope estimate: the invoice value reported by the matched UK entities is implausibly large "
                                "against the group's cost base (intercompany purchases or a unit error).")
    est["whose_money"] = ("The range is the gross annual discount a buyer could capture by paying eligible invoices early, before the buyer's "
                          "own cost of funding that early payment and without netting any existing supply chain finance programme.")
    return est


@lru_cache(maxsize=1)
def _supplier_finance() -> pd.DataFrame:
    p = P / "supplier_finance.parquet"
    return pd.read_parquet(p) if p.exists() else pd.DataFrame(columns=["company_id"])


@lru_cache(maxsize=1)
def _uk_group_features() -> pd.DataFrame:
    p = P / "uk_group_features.parquet"
    return pd.read_parquet(p) if p.exists() else pd.DataFrame(columns=["company_id"])


def supplier_finance(company_id: str) -> dict | None:
    """Supplier finance (reverse factoring) disclosure from the annual report. `confirmed` is False when only one
    reader found it (shown as unconfirmed, never scored)."""
    sf = _supplier_finance()
    m = sf[sf.company_id == company_id]
    if m.empty:
        return None
    r = m.iloc[0]
    if r.programme_exists != "yes":
        return {"programme_disclosed": False, "resolution": _nn(r.programme_resolution), "source_url": _nn(r.source_url)}
    return {"programme_disclosed": True, "confirmed": bool(r.get("programme_confirmed", False)), "confirmed_by": _nn(r.get("confirmed_by")),
            "resolution": _nn(r.programme_resolution),
            "obligations_outstanding": _nn(r.obligation_amount), "prior_year": _nn(r.obligation_prior_amount), "currency": _nn(r.currency),
            "terms_with_programme": _nn(r.payment_terms_with_programme), "terms_without_programme": _nn(r.payment_terms_without_programme),
            "period_end": _nn(r.period_end), "source_url": _nn(r.source_url), "quote": _nn(r.quoted_snippet),
            "extraction_method": _nn(r.extraction_method), "confidence": _nn(r.confidence), "estimate": False}


def uk_filing_features(company_id: str) -> dict | None:
    """Group roll-up of UK filing fields beyond payment speed (disputes, terms changes, SCF, e-invoicing, codes)."""
    g = _uk_group_features()
    m = g[g.company_id == company_id]
    if m.empty:
        return None
    r = m.iloc[0]
    return {"uk_entities_n": int(r.uk_entities_n),
            "late_because_of_dispute_pct": _nn(r.dispute_share_pct), "late_because_of_dispute_method": _nn(r.dispute_share_method),
            "late_because_of_dispute_url": _nn(r.dispute_share_evidence_url),
            "dispute_process_weak_share": _nn(r.dispute_quality_weak_share),
            "terms_changed_longer_n": int(r.terms_changed_longer_n or 0), "terms_changed_longer_url": _nn(r.terms_changed_longer_evidence_url),
            "scf_offered_n": int(r.scf_offered_n or 0), "scf_started": bool(r.scf_started_any),
            "einvoicing_offered_share": _nn(r.einvoicing_offered_share), "einvoicing_started": bool(r.einvoicing_started_any),
            "payment_codes": _nn(r.payment_code_names), "pay_to_stay": bool(r.pay_to_stay_any),
            "source_type": "uk_payment_practices_filing_fields", "period_end": _nn(r.period_end), "estimate": False}


def get_account_brief(company: str) -> dict:
    r = _row(company)
    if r is None:
        return {"found": False, "query": company}
    return {
        "found": True, "company_id": r.company_id, "name": r["name"], "country": _nn(r.country), "hq_city": _nn(r.hq_city),
        "sector": r.sector, "sector_method": r.sector_method,
        "revenue": {"amount": _nn(r.revenue), "currency": _nn(r.revenue_currency), "period_end": _nn(r.revenue_period_end),
                    "source_url": _nn(r.revenue_source_url), "source_type": _nn(r.revenue_source_type), "stale": bool(r.revenue_stale)},
        "priority_tier": int(r.priority_tier), "rank": int(r["rank"]), "excluded_reason": _nn(r.excluded_reason),
        "thin_evidence": bool(r.get("thin_evidence", False)),
        "uk_invoice_value_share_of_group_revenue": _nn(r.get("uk_invoice_value_share_of_group_revenue")),
        "scores": {"fit": _nn(r.fit_score), "pain": _nn(r.pain_score), "signal": _nn(r.signal_score), "priority": _nn(r.priority_score),
                   "fit_parts": json.loads(r.fit_parts), "pain_parts": json.loads(r.pain_parts),
                   "pain_evidence_tier": _nn(r.pain_evidence_tier), "pain_basis": r.pain_basis,
                   "method": "deterministic formula, weights in config/assumptions.yaml"},
        "rationale": r.rationale, "rationale_method": r.rationale_method,
        "why_now_signals": json.loads(r.signals),
        "estimates": _estimates(r),
        "supplier_finance": supplier_finance(r.company_id),
        "uk_filing_features": uk_filing_features(r.company_id),
        "payment_profile": {k: v for k, v in get_payment_profile(r.company_id).items() if k in ("reported", "computed_proxy")},
        "one_pager": _one_pager_path(r.company_id),
        "disclaimer": DISCLAIMER,
    }


def _one_pager_path(company_id: str) -> str | None:
    p = ROOT / "outputs" / "one_pagers" / f"{company_id}.html"
    return str(p.relative_to(ROOT)) if p.exists() else None


def _brief_row(r) -> dict:
    return {"rank": int(r["rank"]), "company_id": r.company_id, "name": r["name"], "country": _nn(r.country), "hq_city": _nn(r.hq_city),
            "sector": r.sector, "priority_tier": int(r.priority_tier),
            "scores": {"fit": _nn(r.fit_score), "pain": _nn(r.pain_score), "signal": _nn(r.signal_score)},
            "pain_basis": r.pain_basis, "evidence_days": _nn(r.pain_days),
            "evidence_is_reported": _nn(r.pain_evidence_tier) == 1,
            "evidence_url": _nn(r.uk_worst_entity_source_url) if r.pain_basis == "uk_reported" else
            (_nn(r.get("es_report_url")) or _nn(r.get("es_source_url"))) if r.pain_basis == "es_reported" else _nn(r.dpo_source_url),
            "rationale": r.rationale}


def top_targets(country: str | None = None, city: str | None = None, sector: str | None = None,
                tier: int | None = None, limit: int = 20) -> dict:
    df = companies()
    df = df[df.excluded_reason.isna()]
    if country:
        df = df[df.country == country.upper()]
    if city:
        df = df[df.hq_city.fillna("").str.lower() == city.lower()]
    if sector:
        df = df[df.sector == sector.lower()]
    if tier:
        df = df[df.priority_tier == int(tier)]
    return {"filters": {"country": country, "city": city, "sector": sector, "tier": tier}, "count": int(len(df)),
            "targets": [_brief_row(r) for _, r in df.head(limit).iterrows()],
            "note": "Ranked by tier, then reported evidence before proxy evidence, then priority score.",
            "disclaimer": DISCLAIMER}


_LEGAL_TAIL = re.compile(r",?\s+(Public Limited Company|Group plc|plc|PLC|S\.A\.|SA|S\.p\.a\.|SE & Co\. KGaA|AG|SE|N\.V\.|NV|Inc\.?|INC\.?|Corp\.?|Corporation|Co|Company|Holding N\.V\.|Scoop|"
                         r"Compañia de Seguridad|Integral|Automocion|Telecom)\.?$")
_SHORT = {"Distribuidora Internacional de Alimentacion SA": "DIA", "Fomento de Construcciones y Contratas S.A.": "FCC",
          "The Coca-Cola Company": "Coca-Cola", "Heineken Holding N.V.": "Heineken", "Reckitt Benckiser Group plc": "Reckitt"}


def short_name(name: str) -> str:
    """The name people actually say ("Bunzl", not "Bunzl Public Limited Company"), for sentences in emails."""
    if name in _SHORT:
        return _SHORT[name]
    out = name
    for _ in range(2):
        out = _LEGAL_TAIL.sub("", out).strip().rstrip(",")
    return out or name


def nice_name(name: str) -> str:
    """Readable casing for UK register names, which are ALL CAPS ("NESTLE UK LTD." -> "Nestle UK Ltd")."""
    from chase.resolve.universe import tidy_name
    fix = {"Uk": "UK", "(Uk)": "(UK)", "Ge": "GE", "Nv": "NV", "Llp": "LLP", "Ltd.": "Ltd", "Usa": "USA", "Emea": "EMEA", "Plc": "plc", "Gb": "GB"}
    return " ".join(fix.get(w, w) for w in tidy_name(str(name)).split(" "))


def _poss(name: str) -> str:
    return f"{name}'" if name.endswith(("s", "S")) else f"{name}'s"


def has_real_hook(r) -> bool:
    if r.pain_basis == "uk_reported":
        return r.uk_avg_days_to_pay_mean >= HOOK_MIN["uk_reported"]
    if r.pain_basis == "es_reported":
        return r.es_pmp_days >= HOOK_MIN["es_reported"]
    if r.pain_basis == "computed_dpo_proxy":
        return bool(_nn(r.dpo_sector_median)) and r.dpo / r.dpo_sector_median >= HOOK_MIN["dpo_ratio"] \
            and int(r.dpo_fiscal_year) >= 2025 and _nn(r.dpo_payables_basis) == "trade" \
            and (_nn(r.get("dpo_confidence")) or 0) >= 1.0   # recent, on a trade-payables line (a broad line overstates), over cost of sales
                                                             # (a cost-of-materials base reads high against a cost-of-sales median)
    return False


def hook_variables(r) -> dict:
    """Variables for the human-written invite template (Mad Libs: the template is human, the slots are data).
    The hook leads with the account's most striking reported fact, so 15 hooks are not one sentence 15 times."""
    name = short_name(r["name"])
    v = {"company": name, "evidence_kind": r.pain_basis, "hook": None}
    if r.pain_basis == "uk_reported":
        one = r.uk_entities_n == 1
        who = f"{_poss(name)} UK entity" if one else f"{_poss(name)} UK entities"
        days, over60, late, trend = r.uk_avg_days_to_pay_mean, _nn(r.uk_pct_paid_over_60_mean), _nn(r.uk_pct_paid_late_mean), _nn(r.uk_trend_days_yoy_mean)
        v.update(days=f"{days:.0f}", scope="UK entity" if one else "UK entities", benchmark="32",
                 late=f"{late:.0f}%" if late is not None else None, over_60=f"{over60:.0f}%" if over60 is not None else None,
                 slowest_entity=r.uk_worst_entity_name, slowest_days=f"{r.uk_worst_entity_days:.0f}",
                 source_url=r.uk_worst_entity_source_url, period_end=_nn(r.uk_period_end_max))
        # the basis is named in the sentence: a single entity's own figure, or the UK average weighted by invoice value across
        # n entities. "Why now" triggers quote single entities, so the two numbers can differ and must say which is which.
        n = int(r.uk_entities_n)
        wtd = _nn(r.get("uk_days_aggregation")) != "simple_mean"      # weighted unless an entity lacks invoice value (about 2%)
        avg = (f"{days:.0f} days on average" if one else
               f"a {'weighted ' if wtd else ''}UK average of {days:.0f} days across {n} entities{' (by invoice value)' if wtd else ''}")
        avg_p = f"{days:.0f} days on average" if one else f"{'weighted ' if wtd else ''}UK average {days:.0f} days across {n} entities"
        if trend is not None and trend >= 10 and not one and (_nn(r.get("uk_trend_entities_n")) or 0) >= 2 and _nn(r.get("uk_trend_entities_slower_n")) and r.uk_trend_entities_slower_n * 2 > r.uk_trend_entities_n:
            v["hook"] = f"{who} took {trend:.0f} days longer to pay suppliers than a year earlier: {avg}, against a UK median of 32."
        elif over60 is not None and over60 >= 40:
            v["hook"] = f"{who} paid {over60:.0f}% of supplier invoices after more than 60 days ({avg_p}; UK median 32)."
        elif late is not None and 30 <= late <= 75:     # above 75% a late share is more often a filing slip than a fact
            v["hook"] = f"{who} paid {late:.0f}% of supplier invoices later than the agreed terms ({avg_p}; UK median 32)."
        else:
            v["hook"] = f"{who} reported paying suppliers in {avg}, against a UK median of 32."
    elif r.pain_basis == "es_reported":
        prior = _nn(r.es_prior_year_pmp_days)
        v.update(days=f"{r.es_pmp_days:.0f}", scope="Spanish entities", benchmark="60 (legal maximum)",
                 source_url=_nn(r.get("es_report_url")) or _nn(r.es_source_url), period_end=f"FY{int(r.es_fiscal_year)}")
        if prior is not None and r.es_pmp_days - prior >= 3:
            v["hook"] = (f"{_poss(name)} average supplier payment period in Spain rose from {prior:.0f} to {r.es_pmp_days:.0f} days in "
                         f"FY{int(r.es_fiscal_year)}; the legal maximum per payment is 60.")
        else:
            v["hook"] = (f"{name} reported an average supplier payment period of {r.es_pmp_days:.0f} days in Spain for "
                         f"FY{int(r.es_fiscal_year)}; the legal maximum per payment is 60.")
    elif r.pain_basis == "computed_dpo_proxy":
        v.update(days=f"{r.dpo:.0f}", scope="group balance sheet (proxy)", benchmark=f"{r.dpo_sector_median:.0f} (sector median)",
                 source_url=_nn(r.dpo_source_url), period_end=_nn(r.dpo_period_end))
        v["hook"] = (f"{_poss(name)} balance sheet implies about {r.dpo:.0f} days of payables outstanding "
                     f"(computed DPO for FY{int(r.dpo_fiscal_year)}, a proxy; sector median {r.dpo_sector_median:.0f}).")
    v["hook_is_strong"] = has_real_hook(r)
    return v


def dinner_shortlist(city: str, limit: int = 15) -> dict:
    """Accounts for a dinner city. An account is local when its HQ is in the city area or in the country
    (labelled honestly). Only accounts whose data gives a real hook are listed; nobody is invited with a
    sentence that says they pay on time. Each account appears on one city list only (its HQ country's)."""
    key = city.strip().lower()
    key = {"münchen": "munich", "muenchen": "munich"}.get(key, key)
    if key not in CITIES:
        return {"found": False, "city": city, "available": sorted(CITIES)}
    c = CITIES[key]
    df = companies()
    df = df[df.excluded_reason.isna() & (df.priority_tier <= 2) & df.pain_evidence_tier.notna() & (df.country == c["country"])
            & ~df.thin_evidence.fillna(False)]
    df = df[[has_real_hook(r) for _, r in df.iterrows()]] if len(df) else df
    hq_local = df.hq_city.fillna("").str.lower().isin(c["hq"])
    df = df.assign(_local=hq_local.map({True: "hq_in_city_area", False: "hq_in_country"}),
                   _o=(~hq_local).astype(int)).sort_values(["_o", "rank"])
    rows = []
    for _, r in df.head(limit).iterrows():
        b = _brief_row(r)
        b["local_link"] = r._local
        b["hq_city_known"] = _nn(r.hq_city) is not None
        b["hook_variables"] = hook_variables(r)
        rows.append(b)
    return {"found": True, "city": key, "count": len(rows), "accounts": rows,
            "note": "local_link: hq_in_city_area = HQ city is in the metro area; hq_in_country = HQ elsewhere in the country "
                    "or HQ city unknown in the data. Only accounts with a payment figure clearly above the benchmark are listed "
                    "(UK entities at 45+ days, Spanish payment period at 50+ days, or computed DPO at 1.3x the sector median). "
                    "Hooks are template variables filled from the data; a human writes the invite.", "disclaimer": DISCLAIMER}


def dinner_bench(city: str, limit: int = 10) -> list[dict]:
    """Accounts in the dinner city's country that have a slow figure but did not make the shortlist, with the
    reason. For a human to verify before use; never to be invited on the data alone."""
    key = {"münchen": "munich", "muenchen": "munich"}.get(city.strip().lower(), city.strip().lower())
    if key not in CITIES:
        return []
    on_list = {a["company_id"] for a in dinner_shortlist(key, 100)["accounts"]}
    df = companies()
    df = df[df.excluded_reason.isna() & (df.priority_tier <= 2) & df.pain_evidence_tier.notna() & (df.country == CITIES[key]["country"])
            & ~df.company_id.isin(on_list)]
    out = []
    for _, r in df.iterrows():
        if r.pain_basis == "uk_reported" and r.uk_avg_days_to_pay_mean >= HOOK_MIN["uk_reported"] and bool(r.thin_evidence):
            reason = "thin evidence: UK invoice value under 1% of group revenue"
        elif r.pain_basis == "computed_dpo_proxy" and _nn(r.dpo_sector_median) and r.dpo / r.dpo_sector_median >= HOOK_MIN["dpo_ratio"]:
            reason = ("proxy only, on a broad payables line" if _nn(r.dpo_payables_basis) != "trade" else
                      "proxy only, on cost of materials: reads high against the cost-of-sales sector median" if (_nn(r.get("dpo_confidence")) or 0) < 1.0
                      else "proxy only, from an older fiscal year")
        else:
            continue
        hv = hook_variables(r)
        out.append({"rank": int(r["rank"]), "company_id": r.company_id, "name": r["name"], "hq_city": _nn(r.hq_city),
                    "priority_tier": int(r.priority_tier), "pain_basis": r.pain_basis, "bench_reason": reason,
                    "figure": hv.get("hook"), "source_url": hv.get("source_url")})
    return out[:limit]


def lookup_uk_entity(query: str, limit: int = 10) -> list[dict]:
    """Supplier lookup: how long does my UK customer take to pay? Searches UK legal entities by name or number."""
    e = uk_entities()
    q = query.strip()
    if re.fullmatch(r"[A-Za-z]{0,2}\d{5,8}", q):
        sub = e[e.company_number == q.upper().zfill(8)]
    else:
        k = norm(q)
        names = e.company_name.fillna("").map(norm)
        sub = e[names.str.contains(re.escape(k), regex=True)] if k else e.iloc[0:0]
        sub = sub.assign(_x=(names[sub.index] == k).map({True: 0, False: 1}), _len=sub.company_name.str.len()) \
                 .sort_values(["_x", "latest_is_stale", "_len"])
    out = []
    for r in sub.head(limit).itertuples():
        out.append({"company_name": r.company_name, "company_number": r.company_number,
                    "avg_days_to_pay": _nn(r.avg_days_to_pay), "pct_paid_within_30": _nn(r.pct_paid_within_30),
                    "pct_paid_over_60": _nn(r.pct_paid_over_60), "pct_paid_late": _nn(r.pct_paid_late),
                    "standard_terms_days": [_nn(r.shortest_standard_payment_period_days), _nn(r.longest_standard_payment_period_days)],
                    "max_contractual_days": _nn(r.max_contractual_payment_period_days),
                    "period_start": _nn(r.period_start), "period_end": _nn(r.period_end),
                    "has_usable_report": bool(r.has_usable_report), "report_is_old": bool(r.latest_is_stale),
                    "group": _nn(getattr(r, "group_name", None)), "source_url": r.source_url, "estimate": False,
                    "source_type": "uk_ppr_statutory_report"})
    return out


def explain_methodology(topic: str | None = None) -> dict:
    text = (ROOT / "docs" / "methodology.md").read_text() if (ROOT / "docs" / "methodology.md").exists() else ""
    if not topic:
        heads = re.findall(r"^## (.+)$", text, flags=re.M)
        return {"topics": heads, "text": text[:6000], "source": "docs/methodology.md"}
    sections = re.split(r"(?m)^(?=## )", text)
    t = topic.lower()
    hits = [s for s in sections if t in s.split("\n", 1)[0].lower()] or [s for s in sections if t in s.lower()]
    return {"topic": topic, "text": "\n".join(hits)[:8000] if hits else "No section matches this topic.",
            "topics": re.findall(r"^## (.+)$", text, flags=re.M), "source": "docs/methodology.md"}
