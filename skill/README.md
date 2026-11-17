# /chase-brief skill

Independent project by Moritz Hanbuch.

A Claude Code skill that answers four GTM questions with source-linked numbers: this week's queue with draft openers, a brief on one account, a dinner invite list, and what changed in the filings.

## Install (plugin: skill + MCP server)

```bash
claude plugin marketplace add moritzhanbuch/chase-index && claude plugin install chase-index@chase-index
```

That installs the `/chase-brief` skill and the read-only `chase-index` MCP server. Both run with
[uv](https://docs.astral.sh/uv/) inside the plugin folder: the first start installs the Python dependencies
from `pyproject.toml` (about a minute), later starts are instant. The data ships in `data/processed/` (public,
company-level only), so there is nothing to build.

From a local checkout instead: `claude plugin marketplace add ./ && claude plugin install chase-index@chase-index`,
or without the plugin system: `claude mcp add chase-index -- uv run --project "$(pwd)" python "$(pwd)/mcp/server.py"`.

Tested from a fresh clone: see `evals/reports/install_test.md`.

## Point it at the data

The skill reads `data/processed/` through `src/chase/query.py` and renders answers with `src/chase/answers.py`, the
same code the MCP server uses. If you copy the skill folder elsewhere, run the script with
`uv run --project /path/to/chase-index chase-brief ...`.

## Use

Weekly workflow flags (computed live from `data/processed`, no generated files needed): `--queue [N]`, `--triggers [YYYY-MM-DD]`, `"<company>" --workspace` (add `--public` to drop anything from local private data).


```
/chase-brief Nestlé
/chase-brief prep for the Diageo dinner
```

or directly:

```bash
uv run chase-brief "Nestlé"
uv run chase-brief "Siemens Energy" --one-pager
uv run chase-brief --dinner munich
uv run chase-brief --queue 10
```

Demo output for 5 companies: `evals/reports/skill_demo.md`.
