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

- Relay the answer as printed: it already leads with the key number, its source link, why now and the draft opener. Do not pad it.
- Keep the labels REPORTED, COMPUTED PROXY and ESTIMATE. Never present a proxy or an estimate as a reported fact.
- UK figures cover the group's UK legal entities only; Spanish figures its Spanish entities. Say so when it matters.
- Openers and invite lines are drafts for a person to edit and send. Never send anything.
- If the company is not found, the script falls back to a UK legal-entity lookup or suggests names. Do not guess numbers.
