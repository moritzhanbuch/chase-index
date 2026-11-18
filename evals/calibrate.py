#!/usr/bin/env python3
"""Calibration check: do the scores put the gold "tens" in Tier 1 and the gold "zeros" in Tier 3?

    .venv/bin/python evals/calibrate.py "note about what changed in this iteration"

Appends one iteration to evals/reports/calibration.md (history is kept) and exits 1 if it fails.
The gold set (evals/gold/calibration.csv) was built by an agent that was not allowed to see the scores.
"""
import sys
from datetime import datetime
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
gold = pd.read_csv(ROOT / "evals/gold/calibration.csv")
c = pd.read_parquet(ROOT / "data/processed/companies.parquet")
j = gold.merge(c[["company_id", "priority_tier", "base_tier", "fit_score", "pain_score", "signal_score", "pain_basis",
                  "pain_days", "uk_entities_n", "excluded_reason"]], on="company_id", how="left")
j["ok"] = j.priority_tier == j.expected_tier
tens, zeros = j[j.expected == "ten"], j[j.expected == "zero"]
note = sys.argv[1] if len(sys.argv) > 1 else ""
rep = ROOT / "evals/reports/calibration.md"
head = ("# Calibration\n\nGold set: `evals/gold/calibration.csv`, built by a separate agent that could not see the scores "
        "(17 \"obvious tens\" expected in Tier 1, 15 \"obvious zeros\" expected in Tier 3). **The gold set should be reviewed by hand.**\n\n"
        "Pass rule: every ten in Tier 1 and every zero in Tier 3. Each run of `evals/calibrate.py` appends an iteration below.\n")
txt = rep.read_text() if rep.exists() else head
n = txt.count("\n## Iteration ") + 1
passed = bool(tens.ok.all() and zeros.ok.all())
out = [f"\n## Iteration {n} ({datetime.now().strftime('%Y-%m-%d %H:%M')}): {'PASS' if passed else 'FAIL'}", "",
       f"- Change: {note or 'n/a'}",
       f"- Tens in Tier 1: {int(tens.ok.sum())}/{len(tens)}. Zeros in Tier 3: {int(zeros.ok.sum())}/{len(zeros)}.",
       f"- Not in the scored table: {int(j.priority_tier.isna().sum())}", ""]
miss = j[~j.ok]
if len(miss):
    out += ["| Company | Expected | Got tier | Fit | Pain | Signal | Pain basis | Days | UK entities |", "|---|---|---|---|---|---|---|---|---|"]
    for r in miss.itertuples():
        out.append(f"| {r.name} | {r.expected} (Tier {r.expected_tier}) | {r.priority_tier} | {r.fit_score} | {r.pain_score} | {r.signal_score} | {r.pain_basis} | {r.pain_days} | {r.uk_entities_n} |")
else:
    out += ["| Company | Expected | Tier | Fit | Pain | Signal |", "|---|---|---|---|---|---|"]
    for r in j.itertuples():
        out.append(f"| {r.name} | {r.expected} | {int(r.priority_tier)} | {r.fit_score:.0f} | {r.pain_score:.0f} | {r.signal_score:.0f} |")
rep.write_text(txt + "\n".join(out) + "\n")
print("\n".join(out))
sys.exit(0 if passed else 1)
