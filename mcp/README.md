# chase-index-mcp

Independent project by Moritz Hanbuch.

A read-only MCP server over the Chase Index data. Local stdio only. It reads `data/processed/` through the same query layer the `/chase-brief` skill and the site use (`src/chase/query.py`). No writes, no network calls at query time, no secrets. Do not host it publicly.

## Tools

Every tool answers in text: a short answer first (key number with its official source link, why now, suggested
opener), then a compact `Details` block for agents. Queue, dinner lists and openers are computed on demand from
`data/processed/`; no generated file is read.

| Tool | Use it for |
|---|---|
| `start_here()` | What the tool does, in five lines, and three questions to try |
| `weekly_queue(limit?, play?, demo?)` | "What's in this week's queue and what do I open with": accounts with why now, who to ask for and a draft opener |
| `get_account_brief(company)` | "Brief on Reckitt": tier, key number, why now, opener, supplier-finance context, estimate range, one-pager |
| `dinner_builder(city, date?, limit?, demo?)` | "Who should we invite to the Munich dinner": accounts with a sourced hook, an invite line, left-outs and a bench |
| `triggers(since?, trigger_type?, limit?)` | "What changed this month": new filings, longer terms, upcoming e-invoicing deadlines |
| `top_targets(country?, city?, sector?, tier?, limit?)` | The standing ranked list with filters |
| `get_payment_profile(company)` | Payment facts only: reported days to pay per UK entity, Spanish PMP, computed DPO (proxy) |
| `lookup_uk_supplier_payment_record(customer, limit?)` | Supplier-side lookup of any UK legal entity's latest statutory report |
| `search_companies(query, country?, sector?, limit?)` | Resolve an ambiguous name |
| `account_workspace(company, demo?)` | Full raw record for one account, including your own CRM flags |
| `byod_status(demo?)` | Which of your own data files are loaded |
| `explain_methodology(topic?)` | How the numbers are built |

Reported figures, computed proxies (`COMPUTED PROXY`) and estimates (`ESTIMATE`) are labelled in every answer, so a
calling agent cannot mistake one for another.

## One-line install (plugin: skill + MCP server)

The repository is a Claude Code plugin marketplace. Install from GitHub:

```bash
claude plugin marketplace add moritzhanbuch/chase-index && claude plugin install chase-index@chase-index
```

That installs the `/chase-brief` skill and the read-only `chase-index` MCP server. The server starts with
`uv run` inside the plugin folder (needs [uv](https://docs.astral.sh/uv/)); the first start installs the Python
dependencies from `pyproject.toml`, later starts are instant. The data ships in `data/processed/` (public,
company-level only; `data/private/` is never in git).

From a local checkout instead: `claude plugin marketplace add ./ && claude plugin install chase-index@chase-index`,
or without the plugin system: `claude mcp add chase-index -- uv run --project "$(pwd)" python "$(pwd)/mcp/server.py"`.

Tested from a fresh clone: see `evals/reports/install_test.md`.

## Setup without the plugin system

The data ships in `data/processed/`; nothing needs to be built. Claude Code, from the repository folder:

```bash
claude mcp add chase-index -- uv run --quiet --project "$(pwd)" python "$(pwd)/mcp/server.py"
```

Claude Desktop (`claude_desktop_config.json`), with absolute paths:

```json
{
  "mcpServers": {
    "chase-index": {
      "command": "uv",
      "args": ["run", "--quiet", "--project", "/ABSOLUTE/PATH/TO/chase-index", "python", "/ABSOLUTE/PATH/TO/chase-index/mcp/server.py"],
      "env": {"CHASE_INDEX_ROOT": "/ABSOLUTE/PATH/TO/chase-index"}
    }
  }
}
```

The server uses version 2 of the official MCP Python SDK (`mcp>=2.0`).

## Test

```bash
uv run python mcp/demo_client.py            # starts the server, calls every tool for 3 companies
uv run python mcp/demo_client.py "Siemens Energy" "Diageo" "Inditex"
```

Results are written to `evals/reports/mcp_demo.md`.

## Example conversation

> **You:** Who should we invite to the Munich dinner?
>
> **Claude** calls `dinner_builder(city="munich")` and relays the list: each account with its HQ city, one sourced sentence
> (for example the reported days to pay of its UK entities with the GOV.UK link), the draft invite line, and the bench to check.

> **You:** Brief me on Reckitt.
>
> **Claude** calls `get_account_brief(company="Reckitt")`: tier and rank, the key number with its source, why now, the draft
> opener and who to ask for, the disclosed supplier finance programme as context, and the estimate range labelled ESTIMATE.

> **You:** One of our suppliers says Tesco Stores pays late. What does Tesco report?
>
> **Claude** calls `lookup_uk_supplier_payment_record(customer="Tesco Stores")` and quotes the average days to pay, the share
> paid late, the standard terms and the period, with the GOV.UK report link.

Actual answers from a fresh clone: `evals/reports/install_test.md`.
