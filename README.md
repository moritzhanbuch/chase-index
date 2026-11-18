# The Chase Index

Live demo: https://chase-index-mh.vercel.app (the weekly GTM workspace; noindex)

Independent project by Moritz Hanbuch.

> ### Try it in 60 seconds
>
> Needs [Claude Code](https://claude.com/claude-code) and [uv](https://docs.astral.sh/uv/). In a terminal:
>
> ```bash
> claude plugin marketplace add moritzhanbuch/chase-index && claude plugin install chase-index@chase-index
> ```
>
> Then start Claude Code (restart it if it was open). The first start takes about a minute while uv installs the Python dependencies; after that it is instant. Then ask:
>
> 1. "What's in this week's queue, and what do I open with?"
> 2. "Brief me on Reckitt."
> 3. "Who should we invite to the Munich dinner?"
>
> Every answer leads with the key number, its official source link, why now and a draft opener. Nothing is ever sent. Not sure where to start? Ask "what can chase-index do?". Real answers from a fresh install: [`evals/reports/install_test.md`](evals/reports/install_test.md).

A source-traceable dataset and toolkit on how long large companies take to pay their suppliers, turned into a ranked target list, account one-pagers, dinner-invite hooks, a public index site with a supplier lookup, a Claude Code skill and a read-only MCP server. Built with Claude Code and subagents from public data only.

**What it found.** Nestle UK reports paying suppliers in 76 days on average with only 6% of invoices late: long terms by design. Across the 193 largest groups in the data, 27 have UK entities that average more than 60 days. The official UK median is 32.

**What it is for.** A ranked target list, account one-pagers, a weekly queue with draft openers and dinner lists for a GTM team selling to enterprise finance, plus a public index and supplier lookup that answer engines can cite.

**DACH slice.** Germany and Switzerland have no statutory payment reporting, and German groups are missing from the public ESEF repository. So for DAX and MDAX members headquartered in Bavaria and the largest Swiss and Austrian listed industrials, trade payables to suppliers and cost of sales were read from each group's latest annual report by two independent extractors, with QA deciding every disagreement. Result: a computed DPO (proxy, labelled as such) for 23 companies, and a Munich dinner list with three Munich-area accounts instead of one (`evals/reports/dach_extraction.md`).

**Why trust it.** Every number links to an official filing. The first version of the company matching was right only 50 times in 60. An independent agent caught it, the rules were rewritten, and a fresh sample came back 60 of 60. The failed eval is in the repo.

Start with the quickstart below, then `evals/reports/` (every eval, including the ones that failed first) and `docs/limitations.md`.

This is the public copy of the project. Internal planning notes, application drafts, review reports that quote people, and all person-level research are not included. Contact details in the UK filings' free-text fields (email addresses, phone numbers, titled names) are replaced with `[email removed]`, `[phone removed]` and `[name removed]`; the full text is on the official GOV.UK reports linked from every row.

## Quickstart from a clone: the Monday workflow (tested from a fresh clone)

Needs `git` and [uv](https://docs.astral.sh/uv/). No build, no API key: the processed public data is in the repo, and the queue, dinner lists and openers are computed on demand from it.

```bash
git clone https://github.com/moritzhanbuch/chase-index && cd chase-index
uv run chase-brief --queue 10                     # this week's queue, top 10: why now, who to ask for, draft opener
uv run chase-brief "Reckitt"                      # brief on one account
uv run chase-brief --dinner munich                # who to invite, with a sourced hook each
uv run chase-brief --triggers                     # what changed in the last 30 days
uv run python workspace/build.py && python3 -m http.server -d workspace/dist 8000   # the internal workspace
claude plugin marketplace add ./ && claude plugin install chase-index@chase-index  # skill + MCP server from this checkout
```

The weekly loop: `make features score triggers weekly` rebuilds the scores and writes a copy of the queue and the HubSpot, Attio, Salesforce and Slack exports to `outputs/queue/` and `outputs/exports/` (both gitignored; import notes in `docs/crm_exports.md`). Put your own CRM status, customer list and dinner attendance into `config/byod/` (see its README) and outcomes into `config/status/`; `make feedback` then compares reply and meeting rates by tier, which is the validation that matters (`evals/reports/external_validation.md`).

## What is in here

| Path | What |
|---|---|
| `outputs/targets/target_list.csv` | Top 100 accounts with scores, tier, rationale and evidence links |
| `evals/reports/dach_extraction.md` | DACH slice: computed DPO from the annual reports of Bavarian DAX/MDAX members and Swiss/Austrian industrials, two extractors plus QA |
| `outputs/one_pagers/` | One page per top account, HTML + PDF |
| `site/` | Static public index + supplier lookup (`site/dist` after build) |
| `skill/` | `/chase-brief <company>` Claude Code skill, also packaged as a plugin |
| `mcp/` | Read-only MCP server over the same data |
| `workspace/` | Internal GTM workspace: weekly queue, account pages, dinner builder, trigger feed (static, noindex, live demo linked above) |
| `src/chase/answers.py` | The text answers behind the MCP tools and the skill: weekly queue with openers, account brief, dinner list, triggers |
| `src/chase/gtm/nba.py` | Queue rules and the human-written opener templates (filled from the data on demand) |
| `.claude-plugin/` | Plugin + marketplace manifests: one-line install of the skill and MCP server |
| `aeo/` | Answer-engine share-of-voice monitor (not executed: no API keys) |
| `evals/` | Gold sets and eval reports: UK spot-check, entity resolution, DPO recompute, Spain extraction, calibration, site check |
| `docs/` | Methodology, sources, data dictionary, limitations, model routing |
| `data/processed/` | Final tables (parquet + csv) |
| `config/assumptions.yaml` | Every weight and assumption behind scores and estimates |

## Run it

```bash
make setup      # venv, dependencies, Chromium for PDFs and screenshots
cp .env.example .env   # set CONTACT_EMAIL (required by SEC EDGAR's fair-access policy)
make all        # data -> features -> score -> triggers -> queue -> assets -> site -> workspace -> evals -> test
```

To reproduce the committed results from the local cache without fetching anything new, run `make all ESEF_ARGS=--no-download CH_ARGS=--skip-download`. Plain `make all` is cache-backed too, but the ESEF step then spends up to 35 more minutes downloading filings for countries not covered yet, which grows the universe and can shift ranks. The first run downloads about 12 GB into `data/cache` and `data/raw` (both gitignored) and takes a few hours, mostly rate-limited downloads: SEC company facts (about 50 minutes at 2 requests per second), ESEF filings, and the Companies House ownership snapshot (33 files of about 85 MB; it must complete within one day because the snapshot is rebuilt daily). Later runs take minutes.

Single steps:

```bash
make uk sec esef wikidata   # source ingests
make spain                  # deterministic Spain extractor (the LLM reader and the adjudication are agent steps, see below)
make dach                   # DACH slice: reconcile the two extractors + QA decisions into DPO rows (offline)
make universe               # universe (incl. DACH additions), UK roll-up, DPO table
make score                  # scores, tiers, estimates, target list
make assets                 # one-pagers (HTML + PDF); invite lists to outputs/invites (gitignored)
make site                   # static site into site/dist
make test                   # pytest: parsers, data contracts, calibration, site rules
```

Open the site locally:

```bash
cd site/dist && python3 -m http.server 8000    # then http://localhost:8000
```

## The agent steps

Four steps are done by Claude Code subagents, not scripts, because no model API key is used (see `docs/model_routing.md`):

1. Spain extractor B reads the payment-period notes and writes `data/interim/es_extract_b.json`.
2. A `qa` agent adjudicates disagreements between the two Spain extractors into `data/interim/es_adjudication.json`.
3. An agent classifies sectors for companies without an SEC code into `data/interim/sector_llm.csv`.
4. DACH slice: an agent reads each annual report as extractor B into `data/interim/dach_extract_b.json`, and a separate `qa` agent decides every disagreement into `data/interim/dach_adjudication.json` and hand-checks 10 companies into `data/interim/dach_handcheck.json`.

Their outputs are committed, so `make all` reproduces everything else from them. The first-pass comparison of the two Spain extractors is frozen once adjudication exists (`python -m chase.sources.spain_reconcile --recompare` overrides).

## Use it

```bash
uv run chase-brief "Nestlé"                 # account brief: key number, why now, opener
uv run chase-brief --dinner london          # dinner list with hooks
uv run python mcp/demo_client.py            # start the MCP server and call every tool
claude mcp add chase-index -- uv run --quiet --project "$(pwd)" python "$(pwd)/mcp/server.py"   # MCP server without the plugin system
```

## Ground rules this project follows

- Public, legally accessible data only. robots.txt respected, at least one second between requests per host, a declared User-Agent. No LinkedIn, no logins, no captcha bypass.
- Every number carries `source_url`, `source_type`, `retrieved_at`, a period, `extraction_method` and `confidence`. Estimates are labelled and their assumptions sit in one file.
- No names of individual people in the dataset or on the site.
- The tools never send, post or upload anything. Openers and invite lines are drafts for a person to edit and send.
- Neutral wording on the public site. Reported figures are shown with source and period.

## Layout

```
src/chase/common      HTTP client: cache, rate limit, retries, provenance log
src/chase/sources     one module per source (UK, SEC, ESEF, Wikidata, Companies House bulk, Spain, DPO)
src/chase/resolve     universe build, name normalisation, UK entity roll-up
src/chase/enrich      sector mapping
src/chase/score       scores, tiers, estimates, master table
src/chase/assets      one-pagers and invite lists
src/chase/gtm         triggers, weekly queue, openers, bring-your-own-data, CRM exports
src/chase/query.py    the one query layer used by skill, MCP server and site
src/chase/answers.py  the text answers the MCP server and the skill return
```

## Licence

Code: MIT (`LICENSE`). Data: see `DATA_LICENSE.md`. UK payment practices data stays under the Open Government Licence v3.0, with attribution.
