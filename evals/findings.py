#!/usr/bin/env python3
"""Compute the headline numbers used in the report and the site copy, so nothing is typed by hand.

    .venv/bin/python evals/findings.py      # prints and writes evals/reports/findings.json
"""
import json
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
P = ROOT / "data/processed"
e = pd.read_parquet(P / "uk_entity_latest.parquet")
cur = e[e.has_usable_report & ~e.latest_is_stale]
c = pd.read_parquet(P / "companies.parquet")
m = pd.read_parquet(P / "uk_entity_group_map.parquet")
es = pd.read_parquet(P / "es_pmp.parquet")
rep = pd.read_parquet(P / "uk_payment_practices.parquet", columns=["report_id", "is_usable"])
g = c[c.uk_entities_n.notna() & c.excluded_reason.isna()]
big = g[g.revenue_usd >= 20e9]
t = cur.trend_days_yoy.dropna()
ok = es[es.status == "ok"]
f = {
    "uk_reports_total": int(len(rep)), "uk_reports_usable": int(rep.is_usable.sum()), "uk_entities_total": int(len(e)),
    "uk_entities_current": int(len(cur)), "uk_median_days_current": float(cur.avg_days_to_pay.median()),
    "uk_entities_over_60_days": int((cur.avg_days_to_pay > 60).sum()),
    "uk_entities_over_60_days_pct": round(float((cur.avg_days_to_pay > 60).mean() * 100), 1),
    "uk_entities_quarter_of_invoices_after_60_days": int((cur.pct_paid_over_60 >= 25).sum()),
    "uk_entities_max_terms_90_plus": int((cur.max_contractual_payment_period_days >= 90).sum()),
    "uk_entities_slower_yoy_pct": round(float((t > 0).mean() * 100), 1), "uk_entities_with_yoy": int(len(t)),
    "uk_period_end_range": [str(cur.period_end.min())[:10], str(cur.period_end.max())[:10]],
    "universe_companies": int(len(c)), "uk_entities_linked": int(len(m)), "groups_with_uk_data": int(c.uk_entities_n.notna().sum()),
    "groups_with_uk_data_addressable": int(len(g)), "groups_uk_median_days": float(g.uk_avg_days_to_pay_mean.median()),
    "groups_uk_over_45": int((g.uk_avg_days_to_pay_mean > 45).sum()), "groups_uk_over_60": int((g.uk_avg_days_to_pay_mean > 60).sum()),
    "big_groups_20bn_with_uk_data": int(len(big)), "big_groups_uk_over_45": int((big.uk_avg_days_to_pay_mean > 45).sum()),
    "big_groups_uk_over_60": int((big.uk_avg_days_to_pay_mean > 60).sum()),
    "big_groups_uk_median_days": float(big.uk_avg_days_to_pay_mean.median()),
    "es_companies": int(len(es)), "es_with_value": int(len(ok)), "es_linked_to_universe": int(ok.company_id.notna().sum()), "es_median_pmp": float(ok.pmp_days.median()),
    "es_above_60": ok[ok.pmp_days > 60][["company_name", "pmp_days"]].values.tolist(),
    "es_50_plus": ok[ok.pmp_days >= 50].sort_values("pmp_days", ascending=False)[["company_name", "pmp_days"]].values.tolist(),
    "tiers": {int(k): int(v) for k, v in c.priority_tier.value_counts().items()},
    "tier1_by_evidence": c[c.priority_tier == 1].pain_basis.value_counts().to_dict(),
    "tier1_by_country_top": c[c.priority_tier == 1].country.value_counts().head(8).to_dict(),
    "dpo_companies": int(c.dpo.notna().sum()),
    "top10": c[c.excluded_reason.isna()].head(10)[["rank", "name", "country", "priority_tier", "pain_basis", "pain_days",
                                                     "uk_entities_n", "uk_pct_paid_late_mean", "uk_worst_entity_source_url", "es_source_url"]]
    .to_dict("records"),
}
(ROOT / "evals/reports/findings.json").write_text(json.dumps(f, indent=1, default=str))
print(json.dumps({k: v for k, v in f.items() if k != "top10"}, indent=1, default=str))
