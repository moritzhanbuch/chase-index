"""Data contracts on the final tables. Skipped when the data has not been built yet."""
import json
from pathlib import Path

import pandas as pd
import pytest
import yaml

ROOT = Path(__file__).resolve().parents[1]
P = ROOT / "data" / "processed"
PROV = ["source_url", "source_type", "retrieved_at", "period_end", "extraction_method", "confidence"]

pytestmark = pytest.mark.skipif(not (P / "companies.parquet").exists(), reason="run `make data score` first")


def load(name, **kw):
    return pd.read_parquet(P / f"{name}.parquet", **kw)


@pytest.mark.parametrize("table,where", [
    ("uk_payment_practices", "is_usable"),
    ("uk_entity_latest", "has_usable_report"),
    ("uk_group_metrics", None),
    ("dpo", "dpo_notna"),
    ("es_pmp", "status_ok"),
    ("scores", None),
])
def test_provenance_complete(table, where):
    cols = None if table != "uk_payment_practices" else PROV + ["is_usable", "period_start"]
    df = load(table, columns=cols) if cols else load(table)
    if where == "dpo_notna":
        df = df[df.dpo.notna()]
    elif where == "status_ok":
        df = df[df.status == "ok"]
    elif where:
        df = df[df[where]]
    assert len(df) > 0
    for c in PROV:
        assert c in df.columns, f"{table} lacks {c}"
        missing = int(df[c].isna().sum())
        assert missing == 0, f"{table}.{c}: {missing} rows without provenance"


def test_universe_provenance_and_ids():
    u = load("universe")
    assert u.company_id.is_unique
    for c in ["source_url", "source_type", "retrieved_at", "extraction_method", "confidence", "revenue_source_url"]:
        assert u[c].notna().all(), c
    # period may be unknown only for Wikidata revenue statements without a date, which must be flagged stale
    assert u[u.period_end.isna()].revenue_stale.all()
    cfg = yaml.safe_load((ROOT / "config/assumptions.yaml").read_text())
    # the only exception: Bavarian DAX/MDAX members added by the DACH slice (DECISIONS 44), each flagged
    below = u.revenue_usd < float(cfg["universe"]["min_revenue_usd"])
    assert (u.loc[below, "merge_methods"] == "dach_slice_index_member").all()


def test_scores_ranges_and_tiers():
    c = load("companies")
    for s in ["fit_score", "pain_score", "signal_score"]:
        assert c[s].between(0, 100).all(), s
    assert set(c.priority_tier.unique()) <= {1, 2, 3}
    cfg = yaml.safe_load((ROOT / "config/assumptions.yaml").read_text())["scoring"]
    assert (c[c.fit_score < cfg["tiers"]["fit_gate"]].priority_tier == 3).all()
    assert (c[c.excluded_reason.notna()].priority_tier == 3).all()
    # reported evidence outranks the proxy: proxy-only pain is capped
    proxy = c[c.pain_evidence_tier == 2]
    assert (proxy.pain_score <= cfg["pain"]["tier2_max"]).all()
    # banks and insurers never get a DPO-based pain score
    assert not ((c.sector == "financials") & (c.pain_basis == "computed_dpo_proxy")).any()


def test_dpo_formula_and_flags():
    d = load("dpo")
    ok = d[d.dpo.notna() & d.payables.notna() & d.cost_of_sales.notna()]
    recomputed = ok.payables / ok.cost_of_sales * 365
    assert ((recomputed - ok.dpo).abs() <= 0.11).all()
    assert d[d.dpo_flag == "not_applicable"].dpo.isna().all()
    assert (d[d.dpo_flag == "ok"].dpo.between(5, 365)).all()


def test_estimates_are_labelled_ordered_and_non_negative():
    c = load("companies")
    assert c.estimate.all()
    for scope in ("est_uk_", "est_group_"):
        sub = c[c[f"{scope}discount_base"].notna()]
        assert len(sub) > 0
        if scope == "est_group_":      # group estimates only ever rest on a clean group-level DPO, never on local reported days
            assert (sub.est_group_days_basis == "computed_dpo_proxy").all()
            assert (sub.est_group_cash_beyond_30 <= sub.dpo_payables * 1.001).all()
        for k in ("discount_low", "discount_base", "discount_high", "cash_beyond_30", "cash_beyond_60"):
            assert (sub[f"{scope}{k}"] >= 0).all(), scope + k
        assert (sub[f"{scope}discount_low"] <= sub[f"{scope}discount_base"] + 1e-6).all()
        assert (sub[f"{scope}discount_base"] <= sub[f"{scope}discount_high"] + 1e-6).all()
        assert (sub[f"{scope}cash_beyond_60"] <= sub[f"{scope}cash_beyond_30"] + 1e-6).all()


def test_estimate_formula_matches_config():
    cfg = yaml.safe_load((ROOT / "config/assumptions.yaml").read_text())["estimates"]
    c = load("companies")
    r = c[c.est_uk_discount_base.notna()].iloc[0]
    s = cfg["scenarios"]["base"]
    acc = min(cfg["max_days_accelerated"], max(0.0, r.uk_avg_days_to_pay_mean - cfg["early_pay_day"]))
    expected = r.est_uk_annual_payments_gbp * s["share_eligible"] * s["annualised_rate"] * acc / 365
    assert abs(expected - r.est_uk_discount_base) < 1.0


def test_signals_have_evidence_urls():
    c = load("companies")
    for sig in c[c.signals_n > 0].signals.head(400):
        for s in json.loads(sig):
            assert s.get("url"), s


def test_rationale_cites_only_row_numbers():
    """Every number in a template rationale must be derivable from the row (rounded)."""
    import re
    c = load("companies")
    sub = c[(c.rationale_method == "deterministic_template") & (c.priority_tier <= 2)].head(150)
    for r in sub.itertuples():
        allowed = set()
        for col in c.columns:
            v = getattr(r, col)
            if isinstance(v, (int, float)) and not pd.isna(v):
                for scale in (1, 1e6, 1e9):
                    allowed |= {f"{v/scale:.0f}", f"{v/scale:.1f}"}
            elif isinstance(v, str):
                allowed |= set(re.findall(r"\d+(?:\.\d+)?", v))
        nums = set(re.findall(r"\d+(?:\.\d+)?", r.rationale))
        assert nums <= allowed, (r.name, nums - allowed)


def test_uk_group_figures_only_use_matched_current_entities():
    m = load("uk_entity_group_map")
    assert m.company_number.is_unique
    assert m.match_confidence.between(0.75, 1.0).all()
    assert m.match_method.notna().all()
    g = load("uk_group_metrics")
    assert (g.uk_entities_n >= 1).all()
    assert g.uk_days_aggregation.isin(["invoice_value_weighted_mean", "simple_mean"]).all()


def test_target_list():
    t = pd.read_csv(ROOT / "outputs/targets/target_list.csv")
    assert len(t) == 100
    assert t["rank"].is_monotonic_increasing
    assert t.rationale.notna().all()


def test_entity_resolution_gold_precision():
    gold = ROOT / "evals/gold/entity_matches.csv"
    if not gold.exists():
        pytest.skip("gold set not built yet")
    g = pd.read_csv(gold, dtype={"company_number": str})
    m = load("uk_entity_group_map")[["company_number", "company_id"]]
    j = g.merge(m, on="company_number", how="inner", suffixes=("_gold", ""))
    judged = j[j.expected_company_id.notna() | (j.expected_match == "none")]
    if not len(judged):
        pytest.skip("no overlap between gold set and auto-matches")
    correct = (judged.company_id == judged.expected_company_id)
    assert correct.mean() >= 0.95, f"precision {correct.mean():.3f} on {len(judged)} auto-matched gold rows"


def test_calibration_passes():
    gold = ROOT / "evals/gold/calibration.csv"
    if not gold.exists():
        pytest.skip("calibration gold set not built yet")
    g = pd.read_csv(gold)
    c = load("companies")[["company_id", "priority_tier"]]
    j = g.merge(c, on="company_id", how="left")
    wrong = j[j.priority_tier != j.expected_tier]
    assert wrong.empty, wrong[["name", "expected_tier", "priority_tier"]].to_dict("records")


def test_no_secrets_tracked():
    import subprocess
    files = subprocess.run(["git", "ls-files"], cwd=ROOT, capture_output=True, text=True).stdout.split("\n")
    assert ".env" not in files


def test_dinner_lists_are_honest():
    from chase import query as q
    seen = {}
    for city, cfg in q.CITIES.items():
        s = q.dinner_shortlist(city, 15)
        assert s["found"] and s["count"] >= 3      # a short honest list beats a padded one (Madrid)
        for a in s["accounts"]:
            assert a["company_id"] not in seen, f"{a['name']} is on {seen.get(a['company_id'])} and {city}"
            seen[a["company_id"]] = city
            assert a["country"] == cfg["country"]
            hv = a["hook_variables"]
            assert hv["hook"] and hv["hook_is_strong"] and hv.get("source_url")
            assert "—" not in hv["hook"] and "–" not in hv["hook"]
            if a["local_link"] == "hq_in_city_area":
                assert a["hq_city"].lower() in cfg["hq"]
            if a["pain_basis"] == "computed_dpo_proxy":
                assert "proxy" in hv["hook"]


def test_entity_payment_profile_hides_inconsistent_late_shares():
    from chase import query as q
    e = q.uk_entities()
    bad = e[e.quality_flag.fillna("").str.contains("pct_late_inconsistent") & e.company_id.notna() & e.has_usable_report & ~e.latest_is_stale]
    if bad.empty:
        pytest.skip("no flagged entity linked to a group")
    row = bad.iloc[0]
    prof = q.get_payment_profile(row.company_id)
    ents = {x["company_number"]: x for x in prof["reported"]["uk"]["entities"]}
    if row.company_number in ents:
        assert ents[row.company_number]["pct_paid_late"] is None
