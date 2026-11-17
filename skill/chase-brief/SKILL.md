---
name: chase-brief
description: Sales briefs from the Chase Index, a source-traceable dataset on how slowly large companies pay their suppliers. Use for "what's in this week's queue", "what do I open with", "brief on <company>", "prep for <company>", "who should we invite to the <city> dinner", "how slowly does <company> pay suppliers", or "what changed in the filings".
---

# chase-brief

Answers four questions for a GTM teammate: who to contact this week and what to open with, a brief on one account, who to invite to a dinner, and what changed in the filings. Every number links to its official source. Queue, dinner lists and openers are computed live from `data/processed/`.

## If the chase-index MCP tools are available, use them

They give the same answers: `weekly_queue`, `get_account_brief`, `dinner_builder`, `triggers`, `start_here`. Use the script below only when they are not connected.

## Otherwise run the script

From a plugin install (the plugin folder is two levels above this skill); `uv` installs the dependencies on first use, which takes about a minute:

```bash
uv run --quiet --project "${CLAUDE_SKILL_DIR}/../.." chase-brief --queue 10        # this week's queue: why now, who, draft opener
uv run --quiet --project "${CLAUDE_SKILL_DIR}/../.." chase-brief "Reckitt"         # brief on one account
uv run --quiet --project "${CLAUDE_SKILL_DIR}/../.." chase-brief --dinner munich   # who to invite (munich, paris, london, madrid)
uv run --quiet --project "${CLAUDE_SKILL_DIR}/../.." chase-brief --triggers        # what changed in the last 30 days
uv run --quiet --project "${CLAUDE_SKILL_DIR}/../.." chase-brief --start           # what this does, 3 questions to try
```

From a clone of the repository, run the same commands with `uv run chase-brief ...` in the repository folder. Add `--json` for the structured data, `--one-pager` to a brief to render the one-page HTML + PDF.

## How to present the result

- Relay the answer without padding: keep the tool's wording, numbers and source links.
- For a brief on one account, always use this order, and use it every time:
  1. **Header line**: company name, tier, rank, queue position, sector, headquarters.
  2. **Key number**: with its label (REPORTED / COMPUTED PROXY / ESTIMATE) and source link.
  3. **UK entities table**: include it only when the account has UK entities (`uk_entities` in the structured details, or `--json` from the script). Use the columns Entity | Avg days | Paid >60d | Paid late | YoY. Add one row per entity, slowest first. Link the entity name to its `source_url`, show percentages with %, and show YoY as signed days (e.g. +8, -3). Leave the table out when there are no UK entities.
  4. **Why now**: the trigger signals, with source links.
  5. **Who to ask for**.
  6. **Draft opener**: quoted, marked as a draft to edit and send.
  7. **Estimate**: labelled ESTIMATE, with the low / base / high range.
  8. **One-pager link**.
  9. **My take**: one or two blunt lines from you on the best angle and the weakest point of the pitch.
- Leave out a section only when the tool has no data for it. Do not reorder sections or add new ones.
- Queue, dinner and triggers answers keep the tool's own order.
- Keep the labels REPORTED, COMPUTED PROXY and ESTIMATE. Never present a proxy or an estimate as a reported fact.
- UK figures cover the group's UK legal entities only; Spanish figures its Spanish entities. Say so when it matters.
- Openers and invite lines are drafts for a person to edit and send. Never send anything.
- If the company is not found, the script falls back to a UK legal-entity lookup or suggests names. Do not guess numbers.
