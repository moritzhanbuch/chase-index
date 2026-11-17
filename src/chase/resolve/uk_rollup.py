"""Roll UK reporting entities (Companies House numbers) up to universe groups.

No Companies House API key is used. Version 2 rules, tightened after the first gold-set check
found precision of 0.83 (evals/reports/entity_resolution.md). A link is accepted only when:

1. exact_name     the entity's own normalised name equals a universe company name (or the entity's
                  company number is the universe company's own number on Wikidata), or
2. ch_psc_chain   the Companies House PSC bulk data shows an unbroken chain of MAJORITY holdings
                  (more than 50% of shares or votes at every step) from the entity up to a company whose
                  name matches a universe company. The nearest such chain member wins. A step where the
                  registered number leads to a differently named company ends the walk. If the matched
                  group is a bank, insurer or investor, the entity name must also carry its brand:
                  a majority-holding investor does not make a portfolio company part of its group, or
3. brand_prefix   the entity has NO corporate parent on record and its name starts with a distinctive
                  universe brand key built from primary names only ("Saint-Gobain Glass (UK) Limited").

Wikidata parent/subsidiary links are used as corroboration only (they were the least precise evidence:
stale owners, minority stakes, joint ventures). When the entity's name and its parent chain point to
different universe companies, the entity goes to data/interim/review_queue.csv and is NOT used.

Outputs:
  data/processed/uk_entity_group_map.parquet   one row per matched entity (method + confidence)
  data/processed/uk_group_metrics.parquet      one row per universe company with UK entities
Run: python -m chase.resolve.uk_rollup
"""
from __future__ import annotations

import json
from pathlib import Path

import pandas as pd

from chase.resolve.names import core, norm

ROOT = Path(__file__).resolve().parents[3]
INTERIM = ROOT / "data" / "interim"
OUT = ROOT / "data" / "processed"

CONF = {"exact_name": 0.95, "ch_psc_chain": 0.9, "brand_prefix": 0.8}
EXTREME_DAYS = 200          # an entity average at or above this is excluded from group figures
EXTREME_YOY_JUMP = 100      # so is a year-on-year change of this many days in either direction
MIN_AUTO_CONFIDENCE = 0.75   # raised if the gold-set precision falls below 0.95 (see evals/reports/entity_resolution.md)
DISABLED_METHODS: set[str] = set()

# single-token brand keys that are ordinary words or shared by unrelated firms: never prefix-match on these
COMMON = set("""target delta phoenix apple national general united first royal british american standard premier
global atlas pioneer summit alliance liberty legacy progressive sterling compass capital central western eastern
northern southern pacific atlantic continental international universal dominion express metro orange shell total
sky virgin next boots visa oracle prudential legal gap ross best dollar republic regions
discover principal travelers reliance genuine waters ball crown sealed dover
southern edison public consolidated lincoln globe hartford marsh brown arthur
energy power water gas oil steel motors motor foods food group holdings partners brands stores markets
industries enterprises resources technologies technology systems solutions services communications media
health healthcare medical pharma life science sciences financial finance bank insurance
china india japan korea france germany spain italy europe america canada australia brazil mexico
cardinal element carrier match bath coach sands associated realty simon digital tower nationwide
smith jones johnson wood taylor wilson morgan stanley wells chase automotive brookfield
insight viking plexus maximus staples brighthouse fidelity mutual pioneer vision focus unity
""".split())


def _split(v) -> list[str]:
    if v is None or (isinstance(v, float) and pd.isna(v)):
        return []
    return [x.strip() for x in str(v).split("|") if x.strip()]


def build_indexes(u: pd.DataFrame):
    exact: dict[str, set[str]] = {}
    brand: dict[str, set[str]] = {}
    qid2id: dict[str, str] = {}
    for r in u.itertuples():
        for q in _split(r.wikidata_qid):
            qid2id[q] = r.company_id
        if bool(getattr(r, "not_a_company", False)):
            continue
        primary = [r.name] + _split(r.legal_names)
        for n in primary:
            k = norm(n)
            if len(k) >= 3:
                exact.setdefault(k, set()).add(r.company_id)
            b = core(n)
            toks = b.split()
            if (len(toks) >= 2 and len(b) >= 8) or (len(toks) == 1 and len(b) >= 5):
                brand.setdefault(b, set()).add(r.company_id)
        for a in _split(r.aliases):
            k = norm(a)
            if len(k) >= 5 and " " in a.strip() or len(k) >= 7:
                exact.setdefault(k, set()).add(r.company_id)
    return exact, brand, qid2id


def top_of(company_id: str, parent: dict[str, str | None]) -> str:
    seen = set()
    while parent.get(company_id) and company_id not in seen:
        seen.add(company_id)
        company_id = parent[company_id]
    return company_id


def match_entities(ent: pd.DataFrame, u: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame, dict]:
    exact, brand, qid2id = build_indexes(u)
    parent = {c: p for c, p in zip(u.company_id, u.parent_company_id) if isinstance(p, str)}
    name_of = dict(zip(u.company_id, u.name))
    country_of = {c: k for c, k in zip(u.company_id, u.country) if isinstance(k, str)}
    stats: dict = {}

    # --- evidence tables
    num2cid: dict[str, str] = {}
    wduk_path = INTERIM / "wikidata_uk_entities.parquet"
    if wduk_path.exists():
        wduk = pd.read_parquet(wduk_path)
        for r in wduk.itertuples():
            for q in [r.qid] + _split(getattr(r, "ancestor_path", None)) + [r.universe_ancestor_qid, r.ultimate_ancestor_qid]:
                if isinstance(q, str) and q in qid2id:
                    num2cid.setdefault(r.company_number, qid2id[q])
                    break
    for r in u.itertuples():
        for n in _split(r.uk_company_number_wikidata):
            num2cid.setdefault(n.zfill(8), r.company_id)

    sub_name: dict[str, set[str]] = {}
    sub_path = INTERIM / "wikidata_subsidiaries.parquet"
    if sub_path.exists():
        sub = pd.read_parquet(sub_path)
        # high-precision edges only: "has subsidiary" / "parent organisation", at most two levels down.
        # Pure "owned by" edges include minority stakes (BlackRock "owns" 4,500 items) and are ignored.
        sub = sub[sub.relation.str.contains("P355|P749") & (sub.depth <= 2)]
        for r in sub[sub.child_uk_company_number.notna()].itertuples():
            cid = qid2id.get(r.parent_qid)
            if cid:
                num2cid.setdefault(str(r.child_uk_company_number).zfill(8), cid)
        alias_col = next((c for c in sub.columns if "alias" in c), None)
        for r in sub.itertuples():
            cid = qid2id.get(r.parent_qid)
            if not cid:
                continue
            for n in [r.child_label] + (_split(getattr(r, alias_col)) if alias_col else []):
                k = norm(n) if isinstance(n, str) else ""
                if len(k) >= 6:
                    sub_name.setdefault(k, set()).add(top_of(cid, parent))
        stats["wikidata_subsidiary_names"] = len(sub_name)

    chains: dict[str, list[dict]] = {}
    ch_path = INTERIM / "ch_parent_chains.parquet"
    if ch_path.exists():
        ch = pd.read_parquet(ch_path)
        for r in ch.itertuples():
            try:
                chains[r.company_number] = json.loads(r.chain) if isinstance(r.chain, str) else []
            except json.JSONDecodeError:
                chains[r.company_number] = []
        stats["ch_chains_loaded"] = len(chains)
    else:
        stats["ch_chains_loaded"] = 0

    # majority control per ownership record: (company, normalised owner name) -> True when the record
    # states more than 50% of shares or votes. A 25-50% holder (joint ventures, minority investors) is not a parent.
    majority: dict[tuple[str, str], bool] = {}
    psc_path = INTERIM / "ch_psc_corporate.parquet"
    if psc_path.exists():
        psc = pd.read_parquet(psc_path, columns=["company_number", "psc_name", "natures_of_control"])
        is_maj = psc.natures_of_control.fillna("").str.contains("50-to-75|75-to-100")
        for cn, pn, mj in zip(psc.company_number, psc.psc_name, is_maj):
            key = (cn, norm(pn))
            majority[key] = majority.get(key, False) or bool(mj)
    own_number = {}
    for r in u.itertuples():
        for n in _split(r.uk_company_number_wikidata):
            own_number[n.zfill(8)] = r.company_id
    sector_of = dict(zip(u.company_id, u.sector))

    def queue_it(e, reason, cands_txt):
        queue.append({"company_number": e.company_number, "company_name": e.company_name, "reason": reason,
                      "candidates": cands_txt[:300]})

    ov_path = ROOT / "config" / "overrides.yaml"
    import yaml
    excluded_entities = (yaml.safe_load(ov_path.read_text()).get("entity_exclusions") or {}) if ov_path.exists() else {}

    rows, queue = [], []
    for e in ent.itertuples():
        num = e.company_number
        n = e.company_name
        if num in excluded_entities:
            queue_it(e, "manual_exclusion", excluded_entities[num])
            continue

        # ---- evidence from the entity's own name
        name_exact = name_brand = None
        weak_brand = None
        k = norm(n)
        if k in exact and len(exact[k]) == 1:
            name_exact = top_of(next(iter(exact[k])), parent)
        if num in own_number:
            name_exact = name_exact or top_of(own_number[num], parent)
        toks = core(n).split()
        for L in range(min(4, len(toks)), 0, -1):
            b = " ".join(toks[:L])
            if b in brand:
                tops = {top_of(c, parent) for c in brand[b]}
                if b in COMMON and len(toks) > 1:
                    break
                if len(tops) == 1:
                    if " " not in b and len(b) < 9 and len(toks) > 1:
                        weak_brand = (next(iter(tops)), b)
                    else:
                        name_brand = (next(iter(tops)), b)
                break

        # ---- evidence from the Companies House parent chain: walk upward while every step is a verified
        # majority holding; the nearest chain member that is a universe company wins
        chain_hit = None
        chain_named_parent = False       # a majority parent exists (matched or not)
        prev = num
        for hop in chains.get(num, []):
            hn, hnum = hop.get("name"), hop.get("company_number")
            if not hn or prev is None or not majority.get((prev, norm(hn)), False):
                break
            if hop.get("match") == "number_only":
                break                     # the registered number led to a company with a different name: do not trust the step
            chain_named_parent = True
            hk, ck = norm(hn), core(hn)
            cid0, how = None, None
            if hnum and hnum in own_number:
                cid0, how = own_number[hnum], f"chain member {hnum} is the universe company"
            elif hk in exact and len(exact[hk]) == 1:
                cid0 = next(iter(exact[hk]))
                hop_c = hop.get("country_iso2")
                if len(hk) <= 5 and hop_c and country_of.get(cid0) and hop_c != country_of[cid0]:
                    cid0 = None           # very short names collide across countries (EQT AB vs EQT Corp)
                else:
                    how = f"chain member '{hn}'"
            elif ck in brand and ck not in COMMON and len({top_of(c, parent) for c in brand[ck]}) == 1:
                cid0, how = next(iter(brand[ck])), f"chain member '{hn}' (name core '{ck}')"
            if cid0:
                chain_hit = (top_of(cid0, parent), how)
                break
            prev = hnum

        wd = top_of(num2cid[num], parent) if num in num2cid else None   # corroboration only, never decisive

        def row(cid, method, conf, ev, methods):
            rows.append({"company_number": num, "entity_name": n, "company_id": cid, "group_name": name_of.get(cid),
                         "match_method": method, "match_confidence": conf, "match_evidence": ev,
                         "all_methods": "|".join(sorted(methods)), "conflict_note": None})

        name_cid = name_exact or (name_brand[0] if name_brand else None)
        if chain_hit and name_cid and chain_hit[0] != name_cid:
            queue_it(e, "name_and_parent_chain_disagree", f"name:{name_of.get(name_cid)}|chain:{name_of.get(chain_hit[0])}")
        elif name_exact:
            row(name_exact, "exact_name", 0.95, f"'{n}'", {"exact_name"} | ({"ch_psc_chain"} if chain_hit else set()))
        elif chain_hit:
            cid, how = chain_hit
            supported = name_cid == cid or (weak_brand and weak_brand[0] == cid)
            if sector_of.get(cid) == "financials" and not supported:
                # an investor or bank holding a majority does not make a portfolio company part of its group
                queue_it(e, "financial_parent_without_name_link", f"chain:{name_of.get(cid)}")
            else:
                methods = {"ch_psc_chain"} | ({"brand_prefix"} if supported else set()) | ({"wikidata"} if wd == cid else set())
                row(cid, "ch_psc_chain", 0.95 if len(methods) > 1 else 0.9, how, methods)
        elif name_brand:
            cid, b = name_brand
            if chains.get(num):     # any corporate owner on record, majority or not (minority-owned brand licensees, JVs)
                queue_it(e, "brand_prefix_but_entity_has_corporate_owners", f"brand:{name_of.get(cid)}")
            elif sector_of.get(cid) == "financials" and wd != cid:
                queue_it(e, "brand_prefix_financial_unconfirmed", f"brand:{name_of.get(cid)}")
            else:
                row(cid, "brand_prefix", 0.85 if wd == cid else 0.8, f"brand key '{b}', no corporate parent on record", {"brand_prefix"} | ({"wikidata"} if wd == cid else set()))
        elif wd or weak_brand:
            queue_it(e, "wikidata_or_weak_name_only", f"wikidata:{name_of.get(wd)}|weak:{name_of.get(weak_brand[0]) if weak_brand else None}")
    m = pd.DataFrame(rows)
    q = pd.DataFrame(queue)
    stats.update({"entities": len(ent), "matched": len(m), "queued_for_review": len(q),
                  "by_method": m.match_method.value_counts().to_dict() if len(m) else {}})
    return m, q, stats


def group_metrics(m: pd.DataFrame, ent: pd.DataFrame) -> pd.DataFrame:
    cur = ent[ent.has_usable_report & ~ent.latest_is_stale & ent.avg_days_to_pay.notna()]
    j = m.merge(cur, on="company_number", how="inner")
    # Extreme entity values are far more often filing errors than payment behaviour (one entity went from
    # 69 to 249 days in a year against a 60-day maximum term). They stay in the entity table and on the
    # entity's own page, but are left out of GROUP figures and listed in uk_entities_excluded_extreme.
    # a 4x year-on-year jump (8 to 84 days) is a re-filing or scope change, not a trend: the entity keeps its
    # current figure but its year-on-year change is dropped from every group trend (Phase 12 critic, Siemens Gamesa UK)
    prior = j.avg_days_to_pay - j.trend_days_yoy
    j.loc[(prior > 0) & (j.avg_days_to_pay / prior >= 4), "trend_days_yoy"] = float("nan")
    j["_extreme"] = (j.avg_days_to_pay >= EXTREME_DAYS) | (j.trend_days_yoy.abs() >= EXTREME_YOY_JUMP)
    extreme = j[j._extreme].groupby("company_id").apply(
        lambda d: "|".join(f"{n} ({a:.0f} days)" for n, a in zip(d.company_name, d.avg_days_to_pay)), include_groups=False).to_dict()
    j = j[~j._extreme]
    out = []
    for cid, g in j.groupby("company_id"):
        worst = g.loc[g.avg_days_to_pay.idxmax()]
        clean_late = g[g.quality_flag.fillna("").str.contains("pct_late_inconsistent") == False]  # noqa: E712
        w = g.value_paid_total_gbp.fillna(0)
        trend = g.trend_days_yoy.dropna()
        # Aggregation: weighted by the invoice value each entity reports paying, when every matched entity
        # reports it (98% do); otherwise the simple mean. Weighting keeps a small, fast-paying sales office
        # from masking the main operating company, and the reverse.
        full_w = bool((g.value_paid_total_gbp.fillna(0) > 0).all())
        def agg(col, frame=g):
            v = frame[col]
            if not v.notna().any():
                return None
            ww = frame.value_paid_total_gbp.fillna(0)
            if full_w and ww[v.notna()].sum() > 0:
                return round(float((v.fillna(0) * ww).sum() / ww[v.notna()].sum()), 1)
            return round(float(v.mean()), 1)
        out.append({
            "company_id": cid, "group_name": g.group_name.iloc[0],
            "uk_entities_n": len(g),
            "uk_days_aggregation": "invoice_value_weighted_mean" if full_w else "simple_mean",
            "uk_avg_days_to_pay_mean": agg("avg_days_to_pay"),
            "uk_avg_days_to_pay_simple_mean": round(g.avg_days_to_pay.mean(), 1),
            "uk_value_paid_total_gbp": float(w.sum()) if w.sum() > 0 else None,
            "uk_pct_paid_late_mean": agg("pct_paid_late", clean_late) if len(clean_late) else None,
            "uk_pct_paid_late_entities_n": int(clean_late.pct_paid_late.notna().sum()),
            "uk_pct_paid_over_60_mean": agg("pct_paid_over_60"),
            "uk_pct_paid_within_30_mean": agg("pct_paid_within_30"),
            "uk_entities_excluded_extreme": extreme.get(cid),
            "uk_trend_days_yoy_weighted": agg("trend_days_yoy"),
            # robust trend: the smaller of the weighted mean and the median, so one entity cannot carry it
            "uk_trend_days_yoy_mean": (None if not len(trend) else
                                       round(float(min(agg("trend_days_yoy"), trend.median())), 1) if len(trend) >= 2 else agg("trend_days_yoy")),
            "uk_trend_days_yoy_simple_mean": round(trend.mean(), 1) if len(trend) else None,
            "uk_trend_days_yoy_median": round(float(trend.median()), 1) if len(trend) else None,
            "uk_trend_entities_slower_n": int((trend > 0).sum()),
            "uk_trend_entities_n": int(len(trend)),
            "uk_max_contractual_period_days_max": g.max_contractual_payment_period_days.max() if g.max_contractual_payment_period_days.notna().any() else None,
            "uk_longest_standard_period_days_max": g.longest_standard_payment_period_days.max() if g.longest_standard_payment_period_days.notna().any() else None,
            "uk_offers_supply_chain_finance_any": bool(g.offers_supply_chain_finance.fillna(False).any()),
            "uk_offers_einvoicing_share": round(float(g.offers_einvoicing.fillna(False).mean()), 2),
            "uk_payment_code_any": bool(g.participates_in_payment_codes.fillna(False).any()),
            "uk_worst_entity_name": worst.company_name, "uk_worst_entity_number": worst.company_number,
            "uk_worst_entity_days": float(worst.avg_days_to_pay),
            "uk_worst_entity_pct_late": None if pd.isna(worst.pct_paid_late) else float(worst.pct_paid_late),
            "uk_worst_entity_source_url": worst.source_url,
            "uk_period_start_min": str(g.period_start.min())[:10], "uk_period_end_max": str(g.period_end.max())[:10],
            "uk_min_match_confidence": float(g.match_confidence.min()),
            "uk_match_methods": "|".join(sorted(set(g.match_method))),
            "uk_entity_numbers": "|".join(g.sort_values("avg_days_to_pay", ascending=False).company_number),
            "source_url": worst.source_url, "source_type": "uk_ppr_statutory_report(group_rollup)",
            "retrieved_at": g.retrieved_at.max(), "period_start": str(g.period_start.min())[:10],
            "period_end": str(g.period_end.max())[:10],
            "extraction_method": "invoice_value_weighted_mean_over_matched_uk_entities" if full_w else "simple_mean_over_matched_uk_entities",
            "confidence": float(g.match_confidence.min()),
        })
    return pd.DataFrame(out)


def run() -> dict:
    u = pd.read_parquet(OUT / "universe.parquet")
    ent = pd.read_parquet(OUT / "uk_entity_latest.parquet")
    m, q, stats = match_entities(ent, u)
    gm = group_metrics(m, ent)
    m.to_parquet(OUT / "uk_entity_group_map.parquet", index=False); m.to_csv(OUT / "uk_entity_group_map.csv", index=False)
    gm.to_parquet(OUT / "uk_group_metrics.parquet", index=False); gm.to_csv(OUT / "uk_group_metrics.csv", index=False)
    q.to_csv(INTERIM / "review_queue.csv", index=False)
    stats["groups_with_current_uk_data"] = len(gm)
    (ROOT / "data" / "manifests" / "uk_rollup.json").write_text(json.dumps(stats, indent=2))
    return stats


if __name__ == "__main__":
    print(json.dumps(run(), indent=2))
