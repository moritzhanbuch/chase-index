"""Reconcile the two independent supplier-finance extractions (A = XBRL tags, B = LLM reading the report text).

  python -m chase.sources.supplier_finance_reconcile           # compare, write queue + QA sample
  python -m chase.sources.supplier_finance_reconcile --final   # apply adjudication, write data/processed/supplier_finance.parquet

Agreement rule: programme existence agrees when A is tagged and B says yes; amounts agree within 2%.
A cannot see untagged text, so "B says yes, A not tagged" is not a disagreement, but it has only one
reader: a random sample of those rows (and of B's "not mentioned" rows) goes to an independent checker.
Final vocabulary for programme_exists: yes / no (the report says so) / no_evidence (nothing tagged and
nothing found in the text read) / unclear / no_source. "no_evidence" is NOT "no programme".
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[3]
I, P = ROOT / "data" / "interim", ROOT / "data" / "processed"
TOL, SEED = 0.02, 20261117
LATER_FILING_TOL = 0.05   # QA 2026-11-16: see _accn() and evals/reports/supplier_finance.md


def _accn(url) -> str | None:
    """SEC accession folder (18 digits) of a filing URL, else None."""
    m = re.search(r"/data/\d+/(\d{18})/", url) if isinstance(url, str) else None
    return m.group(1) if m else None


def load() -> pd.DataFrame:
    a, b = pd.read_csv(I / "sfa_extract_a.csv"), pd.read_csv(I / "sfa_extract_b.csv")
    return a.merge(b, on="company_id", suffixes=("_a", "_b"))


def compare() -> dict:
    j = load()
    tagged = j.status.astype(str).str.startswith("tagged")
    j["case"] = "neither"                                    # not tagged and B found nothing
    j.loc[tagged & (j.programme_exists == "yes"), "case"] = "both_yes"
    j.loc[tagged & (j.programme_exists != "yes"), "case"] = "a_tagged_b_not_yes"
    j.loc[~tagged & (j.programme_exists == "yes"), "case"] = "b_only_yes"
    j.loc[~tagged & j.programme_exists.isin(["no", "unclear"]), "case"] = "b_no_or_unclear"
    j.loc[j.programme_exists == "no_source_document", "case"] = "no_source"
    both_amt = j[j.obligation_amount_a.notna() & j.obligation_amount_b.notna()].copy()
    both_amt["rel_diff"] = (both_amt.obligation_amount_a - both_amt.obligation_amount_b).abs() / both_amt.obligation_amount_a
    amt_dis = both_amt[both_amt.rel_diff > TOL]
    queue = []
    for r in amt_dis.itertuples():
        queue.append({"company_id": r.company_id, "name": r.name_a, "issue": "amount_differs", "value_a": r.obligation_amount_a,
                      "value_b": r.obligation_amount_b, "period_a": r.period_end, "period_b": r.fiscal_period_end,
                      "url_a": r.filing_url, "url_b": r.document_url, "snippet_b": r.quoted_snippet})
    for r in j[j.case == "a_tagged_b_not_yes"].itertuples():
        queue.append({"company_id": r.company_id, "name": r.name_a, "issue": "tagged_but_reader_did_not_confirm", "value_a": r.obligation_amount_a,
                      "value_b": r.programme_exists, "url_a": r.filing_url, "url_b": r.document_url, "snippet_b": r.quoted_snippet})
    for r in j[j.case == "b_no_or_unclear"].itertuples():
        queue.append({"company_id": r.company_id, "name": r.name_a, "issue": f"reader_says_{r.programme_exists}", "value_a": None,
                      "value_b": r.programme_exists, "url_b": r.document_url, "snippet_b": r.quoted_snippet})
    (I / "sfa_adjudication_queue.json").write_text(json.dumps(queue, indent=1, default=str))
    # hand-check sample for the single-reader rows
    samp = pd.concat([
        j[j.case == "b_only_yes"].sample(min(15, (j.case == "b_only_yes").sum()), random_state=SEED).assign(stratum="reader_only_yes"),
        j[j.case == "neither"].sample(min(12, (j.case == "neither").sum()), random_state=SEED).assign(stratum="neither_found"),
        j[j.case == "both_yes"].sample(min(5, (j.case == "both_yes").sum()), random_state=SEED).assign(stratum="both_yes"),
    ])
    (ROOT / "evals" / "gold").mkdir(exist_ok=True)
    samp[["company_id", "name_a", "stratum", "document_type", "document_url", "filing_url", "fiscal_period_end"]].rename(
        columns={"name_a": "name"}).assign(qa_programme_exists="", qa_amount="", qa_currency="", qa_note="").to_csv(
        ROOT / "evals" / "gold" / "supplier_finance_sample.csv", index=False)
    j[["company_id", "name_a", "case"]].to_csv(I / "sfa_reconcile.csv", index=False)
    return {"companies": len(j), "cases": j.case.value_counts().to_dict(), "amounts_compared": len(both_amt),
            "amounts_agree_within_2pct": int((both_amt.rel_diff <= TOL).sum()), "adjudication_queue": len(queue), "hand_check_sample": len(samp)}


def finalise() -> pd.DataFrame:
    j = load()
    cases = pd.read_csv(I / "sfa_reconcile.csv").set_index("company_id").case
    adj_p = I / "sfa_adjudication.json"
    adj = {(r["company_id"], r["field"]): r for r in json.loads(adj_p.read_text())} if adj_p.exists() else {}
    comp = pd.read_parquet(P / "companies.parquet", columns=["company_id", "name"]).set_index("company_id").name
    out = []
    for r in j.itertuples():
        case = cases.get(r.company_id, "neither")
        exists = {"both_yes": "yes", "b_only_yes": "yes", "neither": "no_evidence", "no_source": "no_source",
                  "a_tagged_b_not_yes": "yes"}.get(case, str(r.programme_exists))
        how = {"both_yes": "tags_and_text_agree", "b_only_yes": "text_only_single_reader", "neither": "nothing_tagged_nothing_found",
               "no_source": "no_document", "a_tagged_b_not_yes": "tagged_amount"}.get(case, "text_only_single_reader")
        amt_a, amt_b = r.obligation_amount_a, r.obligation_amount_b
        # Extractor A keeps the most recently FILED value per end date, so a fiscal-year-end amount is often the
        # rounded (or recast) comparative from a later 10-Q ("$1.1 billion") instead of the 10-K figure. When the
        # tag comes from a different SEC filing than the annual report B read, the periods match and the values are
        # close, the annual report figure wins (QA found this in 10/10 such cases; B equalled the 10-K tag each time).
        later = (_accn(r.filing_url) and _accn(r.document_url) and _accn(r.filing_url) != _accn(r.document_url)
                 and str(r.period_end) == str(r.fiscal_period_end))
        if pd.notna(amt_a) and pd.notna(amt_b) and later and amt_a != amt_b and abs(amt_a - amt_b) / amt_a <= LATER_FILING_TOL:
            amount, amount_how, cur, pend = amt_b, "annual_report_value_tag_from_later_filing", r.currency_b if isinstance(r.currency_b, str) else r.currency_a, r.fiscal_period_end
        elif pd.notna(amt_a) and pd.notna(amt_b) and abs(amt_a - amt_b) / amt_a <= TOL:
            amount, amount_how, cur, pend = amt_a, "tags_and_text_agree", r.currency_a, r.period_end
        elif pd.notna(amt_a):
            amount, amount_how, cur, pend = amt_a, "tagged_only" if pd.isna(amt_b) else "unresolved_difference_tag_used", r.currency_a, r.period_end
        elif pd.notna(amt_b):
            amount, amount_how, cur, pend = amt_b, "text_only_single_reader", r.currency_b, r.fiscal_period_end
            if "spaced" in str(r.location).lower():   # PDF-converted iXBRL with split glyphs: digits of adjacent cells can merge
                amount_how = "text_only_spacing_risk"
        else:
            amount, amount_how, cur, pend = None, None, None, r.fiscal_period_end if isinstance(r.fiscal_period_end, str) else r.period_end
        for field, target in (("programme_exists", "exists"), ("obligation_amount", "amount")):
            a_ = adj.get((r.company_id, field))
            if a_:
                if target == "exists":
                    exists, how = a_["final_value"], "adjudicated"
                else:
                    amount, amount_how = a_["final_value"], "adjudicated"
                    cur = a_.get("currency", cur)
                    pend = a_.get("period_end", pend)
        conf = {"tags_and_text_agree": 0.98, "adjudicated": 0.95, "tagged_amount": 0.9, "text_only_single_reader": 0.8,
                "nothing_tagged_nothing_found": 0.6, "no_document": None}.get(how, 0.7)
        url = r.document_url if isinstance(r.document_url, str) else r.filing_url if isinstance(r.filing_url, str) else r.source_url
        out.append({"company_id": r.company_id, "name": comp.get(r.company_id, r.name_a), "rank": r.rank_a,
                    "programme_exists": exists, "programme_resolution": how, "obligation_amount": amount, "currency": cur,
                    "amount_resolution": amount_how, "obligation_prior_amount": r.obligation_prior_amount_a if pd.notna(r.obligation_prior_amount_a) else r.obligation_prior_amount_b,
                    "amount_suppliers_already_paid": r.amount_suppliers_already_paid_b,
                    "payment_terms_with_programme": r.payment_terms_with_programme_b, "payment_terms_without_programme": r.payment_terms_without_programme_b,
                    "balance_sheet_line": r.balance_sheet_line, "quoted_snippet": r.quoted_snippet if isinstance(r.quoted_snippet, str) else None,
                    "source_url": url, "source_type": "annual_report_supplier_finance_disclosure", "retrieved_at": r.retrieved_at,
                    "period_start": r.period_start if isinstance(r.period_start, str) else None, "period_end": pend if isinstance(pend, str) else None,
                    "extraction_method": "dual_extraction(xbrl_tags+llm_read)" + ("+qa_adjudication" if "adjudicated" in (how, amount_how) else ""),
                    "confidence": conf})
    d = pd.DataFrame(out)
    # A "yes" is confirmed when two readers agree, a QA adjudicator decided it, or the blind QA hand-check of
    # evals/gold/supplier_finance_sample.csv verified it (single-reader yes rows there: 15 of 15 correct).
    qa = ROOT / "evals" / "gold" / "supplier_finance_sample.csv"
    qa_yes = set()
    if qa.exists():
        g = pd.read_csv(qa)
        qa_yes = set(g.loc[g.qa_programme_exists.astype(str).str.lower() == "yes", "company_id"])
    d["programme_confirmed"] = (d.programme_exists == "yes") & (
        d.programme_resolution.isin(["tags_and_text_agree", "adjudicated", "tagged_amount"]) | d.company_id.isin(qa_yes))
    d["confirmed_by"] = d.apply(lambda r: None if not r.programme_confirmed else (
        "qa_hand_check" if r.company_id in qa_yes else r.programme_resolution), axis=1)
    d.to_parquet(P / "supplier_finance.parquet", index=False)
    d.to_csv(P / "supplier_finance.csv", index=False)
    return d


if __name__ == "__main__":
    if "--final" in sys.argv:
        d = finalise()
        print(d.programme_exists.value_counts().to_dict(), d.programme_resolution.value_counts().to_dict(), int(d.obligation_amount.notna().sum()), "with amount")
    elif (I / "sfa_adjudication.json").exists() and "--recompare" not in sys.argv:
        print("first-pass comparison is frozen (sfa_adjudication.json exists)")
    else:
        print(json.dumps(compare(), indent=1))
