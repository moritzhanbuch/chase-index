"""Reconcile the two independent Spain PMP extractions (A = deterministic code, B = LLM reader).

Rule: a field is accepted only when both extractors agree (within 0.5). Disagreements, and
fields found by only one extractor, go to an adjudication queue that a third agent (`qa`)
resolves by reading the source. Nothing is ever silently picked.

  python -m chase.sources.spain_reconcile            # compare A and B, write queue
  python -m chase.sources.spain_reconcile --final    # apply data/interim/es_adjudication.json, write final table

Outputs:
  data/interim/es_reconcile.csv            one row per company x field with both values and a status
  data/interim/es_adjudication_queue.json  what the adjudicator must resolve
  data/processed/es_pmp.parquet (+csv)     final table (only with --final)
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[3]
INTERIM = ROOT / "data" / "interim"
OUT = ROOT / "data" / "processed"

FIELDS = ["pmp_days", "ratio_paid_days", "ratio_pending_days", "prior_year_pmp_days",
          "pct_invoices_paid_within_legal_max_by_value", "pct_invoices_paid_within_legal_max_by_number"]
TOL = 0.5
# fiscal years that are not calendar years (from the sourcing manifest)
NON_CALENDAR_FY = {"ITX": ("2025-02-01", "2026-01-31"), "LOG": ("2024-10-01", "2025-09-30")}


def _num(v):
    try:
        f = float(v)
        return None if pd.isna(f) else f
    except (TypeError, ValueError):
        return None


def compare() -> pd.DataFrame:
    a = {r["ticker"]: r for r in json.loads((INTERIM / "es_extract_a.json").read_text())}
    b = {r["ticker"]: r for r in json.loads((INTERIM / "es_extract_b.json").read_text())}
    rows = []
    for t in sorted(set(a) | set(b)):
        ra, rb = a.get(t, {}), b.get(t, {})
        for f in FIELDS:
            va, vb = _num(ra.get(f)), _num(rb.get(f))
            if va is None and vb is None:
                status = "both_null"
            elif va is None or vb is None:
                status = "only_a" if vb is None else "only_b"
            elif abs(va - vb) <= TOL:
                status = "agree"
            else:
                status = "disagree"
            rows.append({"ticker": t, "company_name": ra.get("company_name") or rb.get("company_name"),
                         "field": f, "value_a": va, "value_b": vb, "status": status,
                         "scope_a": ra.get("scope"), "scope_b": rb.get("scope")})
    df = pd.DataFrame(rows)
    df.to_csv(INTERIM / "es_reconcile.csv", index=False)
    queue = df[df.status.isin(["disagree", "only_a", "only_b"])]
    q = []
    for t, g in queue.groupby("ticker"):
        q.append({"ticker": t, "company_name": g.company_name.iloc[0],
                  "fields": [{"field": r.field, "value_a": r.value_a, "value_b": r.value_b, "status": r.status}
                             for r in g.itertuples()],
                  "snippet_path": f"data/interim/es_snippets/{t}.txt",
                  "location_a": a.get(t, {}).get("location"), "location_b": b.get(t, {}).get("location"),
                  "notes_a": a.get(t, {}).get("notes"), "notes_b": b.get(t, {}).get("notes")})
    (INTERIM / "es_adjudication_queue.json").write_text(json.dumps(q, indent=2, ensure_ascii=False))
    return df


def summary(df: pd.DataFrame) -> dict:
    pmp = df[df.field == "pmp_days"]
    both = pmp[pmp.status.isin(["agree", "disagree"])]
    allf = df[df.status.isin(["agree", "disagree"])]
    return {
        "companies": int(pmp.ticker.nunique()),
        "pmp_found_by_a": int(pmp.value_a.notna().sum()), "pmp_found_by_b": int(pmp.value_b.notna().sum()),
        "pmp_found_by_both": int(len(both)), "pmp_agree": int((both.status == "agree").sum()),
        "pmp_agreement_rate": round(float((both.status == "agree").mean()), 3) if len(both) else None,
        "all_fields_compared": int(len(allf)), "all_fields_agree": int((allf.status == "agree").sum()),
        "all_fields_agreement_rate": round(float((allf.status == "agree").mean()), 3) if len(allf) else None,
        "fields_needing_adjudication": int(df.status.isin(["disagree", "only_a", "only_b"]).sum()),
        "status_counts": df.status.value_counts().to_dict(),
    }


def finalise() -> pd.DataFrame:
    df = pd.read_csv(INTERIM / "es_reconcile.csv")
    a = {r["ticker"]: r for r in json.loads((INTERIM / "es_extract_a.json").read_text())}
    b = {r["ticker"]: r for r in json.loads((INTERIM / "es_extract_b.json").read_text())}
    adj_path = INTERIM / "es_adjudication.json"
    adj = {(r["ticker"], r["field"]): r for r in json.loads(adj_path.read_text())} if adj_path.exists() else {}
    src = pd.read_csv(INTERIM / "es_pmp_sources.csv").set_index("ticker")
    out = []
    for t, g in df.groupby("ticker"):
        ra, rb = a.get(t, {}), b.get(t, {})
        rec = {"ticker": t, "company_name": ra.get("company_name") or rb.get("company_name"),
               "fiscal_year": ra.get("fiscal_year") or rb.get("fiscal_year"),
               "prior_fiscal_year": ra.get("prior_fiscal_year") or rb.get("prior_fiscal_year")}
        how, confs = {}, []
        for r in g.itertuples():
            key = (t, r.field)
            if r.status == "agree":
                rec[r.field], how[r.field] = r.value_a, "both_agree"
                confs.append(0.98)
            elif key in adj:
                rec[r.field], how[r.field] = adj[key].get("final_value"), "adjudicated"
                confs.append(float(adj[key].get("confidence", 0.9)) if adj[key].get("final_value") is not None else 0.0)
            else:
                rec[r.field], how[r.field] = None, ("both_null" if r.status == "both_null" else "unresolved")
        rec["field_resolution"] = json.dumps(how)
        # scope: the LLM reader's wording-based scope, overridden by the adjudicator where it ruled.
        # (Extractor A infers scope from keywords only; the adjudicator found that unreliable.)
        scope_adj = adj.get((t, "scope"), {}).get("final_value")
        rec["scope"] = scope_adj or rb.get("scope") or "unknown"
        note = adj.get((t, "note"), {}).get("reasoning")
        rp, rq, pm = rec.get("ratio_paid_days"), rec.get("ratio_pending_days"), rec.get("pmp_days")
        outside = (pm is not None and rp is not None and rq is not None
                   and not (min(rp, rq) - 0.5 <= pm <= max(rp, rq) + 0.5))
        rec["quality_flag"] = "pmp_outside_its_own_ratios_as_printed" if outside else None
        if outside:
            confs.append(0.6)
        if t == "AMS":
            rec["quality_flag"] = "pct_within_limit_measured_against_45_days_not_60"
        rec["quoted_snippet"] = (rb.get("quoted_snippet") or ra.get("quoted_snippet") or "")[:200] or None
        rec["location"] = str(ra.get("location") or rb.get("location") or "")[:300] or None
        s = src.loc[t] if t in src.index else None
        rec["source_url"] = (s.source_url if s is not None and isinstance(s.source_url, str) else None) or ra.get("source_url") or rb.get("source_url")
        rec["human_readable_report_url"] = s.get("human_readable_report_url") if s is not None else None
        rec["document_type"] = s.document_type if s is not None else None
        rec["source_type"] = "es_annual_accounts_pmp_note"
        rec["retrieved_at"] = s.retrieved_at if s is not None else None
        fy = rec["fiscal_year"]
        rec["period_start"], rec["period_end"] = NON_CALENDAR_FY.get(t, (f"{int(fy)}-01-01", f"{int(fy)}-12-31")) if fy else (None, None)
        rec["extraction_method"] = "dual_extraction(regex_table_parse+llm_read)" + ("+qa_adjudication" if "adjudicated" in how.values() else "")
        rec["confidence"] = round(min(confs), 2) if rec.get("pmp_days") is not None and confs else None
        rec["status"] = "ok" if rec.get("pmp_days") is not None else "no_value"
        rec["notes"] = "; ".join(x for x in [adj.get((t, "pmp_days"), {}).get("reasoning"), adj.get((t, "note"), {}).get("reasoning")] if x) or None
        out.append(rec)
    res = pd.DataFrame(out)
    for c in ["human_readable_report_url", "retrieved_at"]:
        res[c] = res[c].where(res[c].notna(), None)
    OUT.mkdir(exist_ok=True)
    res.to_parquet(OUT / "es_pmp.parquet", index=False)
    res.to_csv(OUT / "es_pmp.csv", index=False)
    return res


if __name__ == "__main__":
    if "--final" in sys.argv:
        # the first-pass comparison is frozen once adjudication exists: re-comparing after an
        # extractor was changed would overstate independent agreement
        r = finalise()
        print(r[["ticker", "pmp_days", "ratio_paid_days", "ratio_pending_days", "prior_year_pmp_days", "scope", "confidence", "status"]].to_string())
    elif (INTERIM / "es_adjudication.json").exists() and "--recompare" not in sys.argv:
        print("first-pass comparison is frozen (es_adjudication.json exists); summary of the frozen file:")
        print(json.dumps(summary(pd.read_csv(INTERIM / "es_reconcile.csv")), indent=2))
    else:
        print(json.dumps(summary(compare()), indent=2))
