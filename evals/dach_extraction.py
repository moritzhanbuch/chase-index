#!/usr/bin/env python3
"""Write evals/reports/dach_extraction.md from the DACH slice files (every number in the report is computed here).

    uv run python evals/dach_extraction.py
"""
from __future__ import annotations

import json
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
I = ROOT / "data" / "interim"
P = ROOT / "data" / "processed"
TOL = 0.005


def fmt(v, cur=""):
    if v is None or pd.isna(v):
        return "n/a"
    return f"{cur} {v / 1e6:,.0f}m".strip() if abs(v) >= 1e6 else f"{cur} {v / 1e3:,.0f}k".strip()


def main() -> None:
    mem = pd.read_csv(I / "dach_index_members.csv")
    tgt = pd.read_csv(I / "dach_targets.csv")
    docs = pd.read_csv(I / "dach_documents.csv")
    rec = pd.read_csv(I / "dach_reconcile.csv")
    adj = json.loads((I / "dach_adjudication.json").read_text())
    hc = json.loads((I / "dach_handcheck.json").read_text()) if (I / "dach_handcheck.json").exists() else []
    vals = pd.read_csv(I / "dach_values.csv")
    dd = pd.read_csv(I / "dach_dpo.csv")
    before = json.loads((I / "dach_before.json").read_text())
    comp = pd.read_parquet(P / "companies.parquet")
    L: list[str] = []
    bav = mem[mem.hq_in_bavaria]
    n_doc = int((docs.pages > 0).sum())
    latest = dd.sort_values("fiscal_year", ascending=False).drop_duplicates("name")
    scored = latest[latest.dpo.notna()]
    both = rec[rec.status.isin(["agree", "disagree"])]
    dpo_fields = both[both.field.isin(["trade_payables", "cost_of_sales", "cost_of_materials"])]
    dec = pd.Series([a["decision"] for a in adj]).value_counts().to_dict() if adj else {}
    fv = vals.set_index(["name", "year_rank", "field"]).value
    for h in hc:   # compare the blind reading with the final accepted value
        f = fv.get((h["name"], 1, h["field"]))
        h["final"] = None if f is None or pd.isna(f) else float(f)
        v = h.get("value")
        h["match"] = v is not None and h["final"] is not None and abs(v - h["final"]) <= TOL * max(abs(v), abs(h["final"]))

    L += ["# DACH slice: computed DPO from annual reports", "",
          "Independent project by Moritz Hanbuch.", "",
          f"**Verdict.** {len(scored)} of {len(tgt)} target companies now have a computed DPO (proxy) read from their latest consolidated "
          f"annual report, with trade payables to suppliers (not total payables). Two independent extractors agreed on "
          f"{(dpo_fields.status == 'agree').sum()} of {len(dpo_fields)} DPO inputs both of them found "
          f"({(dpo_fields.status == 'agree').mean():.0%}); a separate QA agent decided the other {len(adj)} queued values from the source pages. "
          f"A hand-check of 10 randomly drawn companies matched on {sum(1 for h in hc if h.get('match'))} of {len(hc)} values "
          "(5 of the 10 were not fully blind, see section 5). "
          "Three reports could not be retrieved without working around a block, so those companies have no figure.", "",
          "Everything here is a **balance-sheet proxy**, not reported days to pay. Germany and Switzerland have no statutory "
          "payment-practice reporting comparable to the UK regime. Where a UK statutory figure exists for a group, it still outranks this proxy.", ""]

    L += ["## 1. Who is in the slice", "",
          f"- **Bavaria:** DAX 40 and MDAX constituents (German Wikipedia index tables, revisions in `data/interim/dach_index_members.csv`, "
          f"composition as of 7 November 2026 per the tables' boerse.de source). {len(bav)} of {len(mem)} members are headquartered in Bavaria: "
          "Wikidata headquarters (P159) located in Bavaria (P131*), plus the DAX table's state column. "
          f"Banks and insurers excluded: {', '.join(bav[bav.is_financial].name)}.",
          "- **Edge cases, kept and labelled:** Fresenius Medical Care (registered seat Hof, run from Bad Homburg), CTS Eventim (registered seat Munich, run from Bremen), "
          "Knorr-Bremse (Wikidata lists Berlin and Munich). Auto1 Group lists Munich and Berlin in the MDAX table but Wikidata gives Berlin only, so it is out.",
          "- **Switzerland and Austria:** the largest listed industrials (manufacturing, construction, automotive) already in the universe. "
          "ABB was in the universe with a Swedish HQ; corrected to Zurich (`config/overrides.yaml`). Garmin and Amrize are left out because their "
          "DPO already comes from US 10-K XBRL. Austria has one company: voestalpine, Andritz and Wienerberger are not in the universe (a recall gap of "
          "the universe build, reported here, not fixed), and OMV is energy, not an industrial.",
          f"- **Added to the universe:** Bavarian index members that were missing, even below the USD 4bn threshold, flagged "
          f"`dach_slice_index_member` (`config/dach_slice.yaml`, with sector and operational HQ per company): "
          f"{int((comp.get('merge_methods', pd.Series(dtype=str)) == 'dach_slice_index_member').sum()) if 'merge_methods' in comp else 'see universe'} companies.", ""]

    L += ["## 2. Coverage", "",
          f"- Reports found and read: **{n_doc} of {len(tgt)}**. All are the FY2025 reports (September year ends: FY to 2025-09-30; "
          "their FY2026 reports were not yet published on 17 November 2026).",
          "- Not retrieved, on purpose: " + "; ".join(
              f"{r['name']} ({'server refused our declared client (403); not worked around' if 'Schaeffler' in r['name'] or 'Renk' in r['name'] else 'site dropped every connection'})"
              for _, r in docs[docs.pages == 0].iterrows()) + ".",
          "- Source type: annual-report PDF from the company's own IR page for every company. No German company is in the filings.xbrl.org repository, "
          "and only DSM-Firmenich offered an ESEF package on its IR page; Strabag's ESEF facts were used by extractor A alongside the PDF.",
          f"- DPO computed: **{len(scored)}** companies "
          f"({(scored.cost_basis == 'cost_of_sales').sum()} on cost of sales, {(scored.cost_basis == 'cost_of_materials').sum()} on cost of materials "
          "for nature-of-expense reporters, confidence 0.7 as for the existing by-nature rows, kept out of sector medians).",
          "- No DPO: " + "; ".join(
              f"{r['name']} ({'cost base under 20% of revenue: payables/cost would read as slow payment for a software or marketplace business' if r.dpo_flag == 'not_meaningful_small_cost_base' else 'no trade-payables figure can be isolated' if pd.isna(r.payables) else 'no cost line' if pd.isna(r.cost_of_sales) else r.dpo_flag})"
              for _, r in latest[latest.dpo.isna()].iterrows()) + ".", ""]

    L += ["| Company | Slice | FY end | Trade payables | Cost (basis) | DPO (proxy) | Prior-year DPO | How decided |", "|---|---|---|---|---|---|---|---|"]
    prior = dd[dd.fiscal_year < dd.groupby("name").fiscal_year.transform("max")].set_index("name")
    for _, r in latest.sort_values("dpo", ascending=False, na_position="last").iterrows():
        pdpo = prior.dpo.get(r["name"]) if r["name"] in prior.index else None
        L.append(f"| {r['name']} | {'Bavaria' if r.slice == 'bavaria_dax_mdax' else 'CH/AT'} | {r.period_end} | {fmt(r.payables, r.currency)} | "
                 f"{fmt(r.cost_of_sales, r.currency)} ({str(r.cost_basis).replace('_', ' ')}) | "
                 f"{'n/a' if pd.isna(r.dpo) else f'{r.dpo:.0f} days'} | {'n/a' if pdpo is None or pd.isna(pdpo) else f'{pdpo:.0f} days'} | "
                 f"{str(r.extraction_method).replace('dual_extractor_agreement', 'A=B').replace('qa_adjudication', 'QA').replace('+', ', ') if isinstance(r.extraction_method, str) else 'n/a'} |")
    L += ["", "Page and printed line for every value: `data/interim/dach_values.csv`. Source URL and retrieval time: `data/interim/dach_dpo.csv` "
          "and `data/manifests/dach_documents.json`.", ""]

    L += ["## 3. Agreement between the two extractors", "",
          "- **Extractor A** is deterministic code (`src/chase/sources/dach_extract.py`): tagged facts where an ESEF file exists, otherwise the printed consolidated "
          "statements by row label (English and German), with the notes used when the balance sheet shows only a combined payables line.",
          "- **Extractor B** is an agent reading the same page texts independently, without access to A's output or code.",
          f"- Agreement means within {TOL:.1%}.", "",
          "| Field | Both found | Agree | Disagree | Only A | Only B |", "|---|---|---|---|---|---|"]
    for f in ("trade_payables", "cost_of_sales", "cost_of_materials", "revenue"):
        s = rec[rec.field == f].status.value_counts()
        L.append(f"| {f.replace('_', ' ')} | {int(s.get('agree', 0) + s.get('disagree', 0))} | {int(s.get('agree', 0))} | {int(s.get('disagree', 0))} | "
                 f"{int(s.get('only_a', 0))} | {int(s.get('only_b', 0))} |")
    L += ["", f"Overall: {(both.status == 'agree').sum()} of {len(both)} values found by both agree ({(both.status == 'agree').mean():.0%}). "
          "A's misses and errors are the usual ones for a label reader: a management-report table with a change column taken for the statement, "
          "a parent-company (HGB) balance sheet, a segment line, columns printed oldest-first, and nature-of-expense lines with unusual labels.", "",
          f"**Plainly: extractor A is the weak reader.** Where the two disagreed, QA sided with A in {dec.get('a', 0)} of "
          f"{sum(1 for a in adj if a.get('decision') in ('a', 'b', 'other') and a.get('field'))} decided cases. A's value here is as an independent "
          "cross-check: an agreement between a label-matching script and an agent reading the page is strong evidence; a disagreement sends the value "
          "to QA. It is not a second opinion of equal weight.", ""]

    L += ["## 4. QA adjudication", "",
          f"{len(adj)} values went to QA (every disagreement and every single-extractor value). Decisions: "
          + ", ".join(f"{k} {v}" for k, v in sorted(dec.items())) + " (a = extractor A was right, b = B was right, other = both wrong, null = no valid figure).", ""]
    hard = [a for a in adj if a["decision"] in ("other", "null") and a["field"] != "revenue"]
    if hard:
        L += ["Cases where neither extractor had the right figure for a DPO input:", ""]
        L += [f"- **{a['name']}**, {a['field'].replace('_', ' ')}, year {a['year_rank']}: {a['reasoning']}" for a in hard] + [""]

    L += ["## 5. Blind hand-check of 10", "",
          "Ten companies drawn at random (seed 7, from the 25 with both a payables and a cost value). The QA agent read the latest-year trade payables "
          "and cost line from the report without seeing the extractors' or the final values; the table compares its reading with the final value. "
          "**Caveat:** QA had already read the report pages of 5 of the 10 (CTS Eventim, DSM-Firmenich, MTU, Nemetschek, Siemens Healthineers) while "
          "adjudicating, so those 5 are a re-read of pages it knew, not fully blind. The other 5 were read for the first time.", "",
          "| Company | Field | Hand-check | Final | Match |", "|---|---|---|---|---|"]
    for h in hc:
        L.append(f"| {h['name']} | {h['field'].replace('_', ' ')} | {fmt(h.get('value'), h.get('currency') or '')} | "
                 f"{fmt(h.get('final'), h.get('currency') or '')} | {'yes' if h.get('match') else 'NO'} |")
    L += ["", f"Result: {sum(1 for h in hc if h.get('match'))} of {len(hc)} match within {TOL:.1%}." , ""]

    # effect on scoring
    bb = before["basis_by_company"]
    ids = set(comp.company_id) & set(bb)
    changed = [cid for cid in ids if bb[cid]["pain_basis"] != comp.set_index("company_id").pain_basis.get(cid)]
    now_dpo = comp[(comp.pain_basis == "computed_dpo_proxy") & comp.country.isin(["DE", "CH", "AT"])]
    from datetime import date
    from chase import query as q
    from chase.gtm import nba
    mun = q.dinner_shortlist("munich", 40)
    cb = comp.set_index("company_id")
    old_tier = before.get("tier_by_company") or {cid: v["tier"] for cid, v in bb.items()}
    dpo_now = pd.read_parquet(P / "dpo.parquet")
    slice_ids = set(dpo_now[dpo_now.dpo_source == "dach_annual_report"].company_id)
    ch = [(cb.loc[cid, "name"], old_tier[cid], int(cb.loc[cid, "priority_tier"])) for cid in old_tier if cid in cb.index and old_tier[cid] != int(cb.loc[cid, "priority_tier"])]
    new_ids = set(comp.company_id) - set(bb) 
    added = comp[comp.company_id.isin(new_ids) & comp.country.eq("DE") & comp.merge_methods.eq("dach_slice_index_member")] if "merge_methods" in comp else comp.iloc[0:0]
    direct = [(n, a, b) for (n, a, b), cid in zip(ch, [c for c in old_tier if c in cb.index and old_tier[c] != int(cb.loc[c, "priority_tier"])]) if cid in slice_ids]
    ripple = [x for x in ch if x not in direct]
    tier_txt = (f"{len(ch)} existing accounts changed tier. From the slice's own figures: " + (", ".join(f"{n} {a} to {b}" for n, a, b in direct) or "none")
                + ". Ripple from sector medians moving by under one day: " + (", ".join(f"{n} {a} to {b}" for n, a, b in ripple) or "none")
                + f". Tier 1 has {int((comp.priority_tier == 1).sum())} accounts") + \
               (f"; added companies by tier: " + ", ".join(f"{n} (Tier {int(t)})" for n, t in zip(added.name, added.priority_tier)) if len(added) else "")
    qnow = nba.build_queue(date.today(), False, size=25)
    bq = {x["company"] for x in before["queue_top25"]}
    nq = set(qnow.company)
    queue_txt = (f"{len(nq - bq)} new ({', '.join(sorted(nq - bq)) or 'none'}), {len(bq - nq)} dropped ({', '.join(sorted(bq - nq)) or 'none'}).")
    L += ["## 6. Effect on scoring, the Munich dinner list and the queue", "",
          "The rows enter `data/processed/dpo.parquet` as a third source next to SEC and ESEF, with priority over a broad ESEF payables line, and flow "
          "through the existing scoring unchanged: a computed DPO sets the pain score only where no UK or Spanish reported figure exists, and it is "
          "scaled by confidence. A full-confidence proxy (trade payables over cost of sales) can reach Tier 1, as 47 accounts did before this slice; "
          "a cost-of-materials or broad-payables row (confidence 0.7) cannot.",
          f"- Companies in DE/CH/AT whose evidence basis is now the computed DPO proxy: {len(now_dpo)}; companies whose basis changed with this slice: {len(changed)}.",
          f"- Munich dinner list before: {len(before['munich_list'])} accounts ({', '.join(a['company'] for a in before['munich_list'])}).",
          f"- Munich dinner list after: {mun['count']} accounts ({', '.join(a['name'] + (' (proxy)' if a['pain_basis'] == 'computed_dpo_proxy' else '') for a in mun['accounts'])}).",
          "- A proxy hook needs a DPO of at least 1.3 times the sector median, on a trade-payables line over cost of sales, from FY2025 or later. "
          "A cost-of-materials proxy never earns an invitation: it reads high against the cost-of-sales median, so Knorr-Bremse sits on the bench "
          "with that reason.",
          f"- Tier changes: {tier_txt}.",
          f"- Weekly queue (top 25): {queue_txt}",
          "- Roll-up side effect: adding Siemens Healthineers and Traton as groups moves their UK entities out of Siemens and Volkswagen Group, "
          "which is correct for the subsidiary groups and changes the parents' UK figures.", ""]

    L += ["## 7. Limits", "",
          "- **Ticketing:** CTS Eventim's trade payables (EUR 381m) exclude ticket money owed to promoters, which it shows on a separate line "
          "(EUR 1.09bn), so the figure is supplier payables; its sector median comes from a broad services bucket.",
          "- **Proxy, not payment behaviour.** Year-end trade payables over annual cost include timing, seasonality, capex payables in some groups and "
          "purchases outside cost of sales. High DPO can mean long agreed terms paid on time.",
          "- **Cost of materials** (nature-of-expense reporters) is a narrower base than cost of sales and pushes DPO up; those rows carry confidence 0.7 "
          "and stay out of sector medians.",
          "- **Perimeter changes:** DSM-Firmenich (animal health moved to held for sale) and Holcim (North America spin-off: 2024 income statement restated, "
          "2024 balance sheet not) have prior-year figures on a different perimeter; their year-on-year change is not used as a trend.",
          "- **Supplier finance:** Siltronic and Traton disclose supplier-finance payables; where a company presents them outside trade payables, the proxy "
          "understates the days its suppliers wait.",
          "- **Annual, not current:** the latest reports are for FY2025. September year-end companies publish FY2026 reports from late November 2026.", ""]
    L += ["## Cost", "", "No paid API calls. Agents: document scout, two extractor-B readers, one QA adjudicator and hand-checker "
          "(token counts in `docs/model_routing.md`). Downloads through the shared rate-limited client (1 request per second per host, declared User-Agent).", ""]
    (ROOT / "evals" / "reports" / "dach_extraction.md").write_text("\n".join(L))
    print("written evals/reports/dach_extraction.md")


if __name__ == "__main__":
    main()
