#!/usr/bin/env python3
"""Run the /chase-brief skill script for 5 companies and save evals/reports/skill_demo.md."""
import subprocess
import sys
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "skill/chase-brief/scripts/chase_brief.py"
CASES = [["Nestlé"], ["Telefónica"], ["Rolls-Royce"], ["Walmart"], ["Deutsche Bank"], ["Tesco Stores"], ["--dinner", "madrid"]]
out = ["# /chase-brief skill demo", "", f"Run at {datetime.now().strftime('%Y-%m-%d %H:%M')}. Each block is the unedited output of "
       "`skill/chase-brief/scripts/chase_brief.py`. Cases: a reported-UK account, a reported-Spain account, a multi-entity UK account, "
       "a proxy-only account, a poor-fit account, a UK legal entity name (falls back to the group or the entity lookup) and a dinner shortlist.", ""]
ok = 0
for c in CASES:
    r = subprocess.run([sys.executable, str(SCRIPT), *c], capture_output=True, text=True)
    good = r.returncode == 0 and "Independent project by Moritz Hanbuch" in r.stdout
    ok += good
    out += [f"## `/chase-brief {' '.join(c)}`", "", "```", r.stdout.strip() or r.stderr.strip(), "```", ""]
out.insert(4, f"Result: {ok}/{len(CASES)} runs exited cleanly and carry the disclaimer.\n")
(ROOT / "evals/reports/skill_demo.md").write_text(("\n".join(out) + "\n").replace(str(ROOT), "<repo>"))
print(f"skill demo: {ok}/{len(CASES)} ok")
sys.exit(0 if ok == len(CASES) else 1)
