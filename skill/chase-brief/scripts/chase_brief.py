#!/usr/bin/env python3
"""/chase-brief <company>: a short account brief (key number with source, why now, draft opener, who to ask for).

Reads the local Chase Index data through the shared query layer (src/chase/query.py).
No network calls. Point it at the data with CHASE_INDEX_ROOT (the project folder); by default it
uses the repository this skill lives in.

    python skill/chase-brief/scripts/chase_brief.py "Nestle"
    python skill/chase-brief/scripts/chase_brief.py "Tesco Stores" --json
    python skill/chase-brief/scripts/chase_brief.py "Siemens Energy" --one-pager   # render one on demand
    python skill/chase-brief/scripts/chase_brief.py --dinner munich                # who to invite, with a sourced hook each
    python skill/chase-brief/scripts/chase_brief.py --start                        # what this does, 3 questions to try
    python skill/chase-brief/scripts/chase_brief.py --queue [N]                    # this week's queue (top N, default 10)
    python skill/chase-brief/scripts/chase_brief.py --triggers [YYYY-MM-DD]        # trigger feed since a date (default 30 days)
    python skill/chase-brief/scripts/chase_brief.py "Diageo" --workspace           # everything on one account, incl. next best action
"""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path

ROOT = Path(os.environ.get("CHASE_INDEX_ROOT") or Path(__file__).resolve().parents[3])
os.environ.setdefault("CHASE_INDEX_ROOT", str(ROOT))
sys.path.insert(0, str(ROOT / "src"))

try:
    from chase import query as q
except Exception as e:  # missing data or dependencies
    sys.exit(f"Cannot load the Chase Index from {ROOT}: {e}\n"
             "Set CHASE_INDEX_ROOT to the project folder and run it with the project's Python (.venv/bin/python).")


if __name__ == "__main__":
    from chase import answers as A
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    as_json = "--json" in sys.argv
    if "--start" in sys.argv:       # chase_brief.py --start
        print(A.start_here()); sys.exit(0)
    if "--dinner" in sys.argv:      # chase_brief.py --dinner munich
        if as_json:
            from chase.gtm import api as gtm
            print(json.dumps(gtm.dinner_builder(args[0] if args else ""), indent=2, default=str))
        else:
            print(A.dinner(args[0] if args else "").split("\n\n---\n")[0])
        sys.exit(0)
    if "--queue" in sys.argv:       # chase_brief.py --queue 10   (computed live from data/processed)
        n = int(args[0]) if args and args[0].isdigit() else 10
        if as_json:
            from chase.gtm import api as gtm
            print(json.dumps(gtm.weekly_queue(n), indent=2, default=str))
        else:
            print(A.weekly_queue(n).split("\n\n---\n")[0])
        sys.exit(0)
    if "--triggers" in sys.argv:    # chase_brief.py --triggers 2026-11-01
        if as_json:
            from chase.gtm import api as gtm
            t = gtm.get_triggers(args[0] if args else None, limit=40)
            t["triggers"] = [x for x in t["triggers"] if not x.get("private_source")] if "--public" in sys.argv else t["triggers"]
            print(json.dumps(t, indent=2, default=str))
        else:
            print(A.triggers(args[0] if args else None).split("\n\n---\n")[0])
        sys.exit(0)
    if "--workspace" in sys.argv:   # chase_brief.py "Diageo" --workspace
        from chase.gtm import api as gtm
        w = gtm.account_workspace(" ".join(args))
        if not w.get("found", True) or "brief" not in w:
            sys.exit(f"No match for {' '.join(args)!r}.")
        w.pop("people_private", None) if "--public" in sys.argv else None
        print(json.dumps(w, indent=2, default=str))
        sys.exit(0)
    if not args:
        sys.exit(__doc__)
    company = " ".join(args)
    if as_json:
        print(json.dumps(q.get_account_brief(company), indent=2, default=str))
        sys.exit(0)
    if "--one-pager" in sys.argv:
        b = q.get_account_brief(company)
        if b.get("found") and not b.get("one_pager"):
            from chase.assets.build import one_pagers
            one_pagers([b["company_id"]], make_pdf=True)
    print(A.account_brief(company).split("\n\n---\n")[0])
