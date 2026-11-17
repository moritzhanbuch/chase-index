# Model routing: which model did what, and what it cost

Independent project by Moritz Hanbuch.

The rule for this build: build each tool once and route each job to the cheapest thing that does it well. Code where code is enough, a cheaper model for bulk reading and checking, the strongest model for design, integration, adjudication and critique. Producers and checkers are always different agents.

**Paid API spend: $0.** No model API key was set. All LLM work ran inside one Claude Code session on a subscription, as subagents. Token counts below are the subagent totals reported by the harness (input + output, including tool results), rounded. They are a usage measure, not a bill.

## Where no model was used at all

| Job | How | Why |
|---|---|---|
| UK export parsing, quality flags, trends | pandas | Official structured CSV. A model would add risk and no value |
| SEC and ESEF fact extraction, DPO | XBRL APIs + rules | Tagged data. Concept fallbacks are explicit rules with flags |
| Companies House parent chains | streaming JSON parse + chain walk | 5.7M companies. Only code scales |
| Universe merge, entity matching | identifiers, exact names, conservative brand rules | Must be reproducible and auditable. Every match has a method |
| Scores, tiers, estimates | formulas from `config/assumptions.yaml` | A ranking a founder can argue with needs to be deterministic |
| Spain extractor A | regex + HTML table parsing, 1.6 s for 35 documents | The cheap baseline every LLM extraction should be compared against |
| Template rationales, invite hooks, one-pager numbers | string templates over row fields | Numbers never pass through a model |

## Where a model was used

| Job | Agent | Model | Subagent tokens | Why this model |
|---|---|---|---|---|
| Orchestration, integration code, scoring design, docs | lead | Claude Fable 5.2 (session model) | n/a | Planning and judgement |
| UK source check + ingest pipeline | `ingest-uk` | session model | ~162k | Pipeline code with many edge cases |
| SEC source check + ingest pipeline | `ingest-sec` | session model | ~138k | Same |
| ESEF source check + ingest pipeline | `ingest-esef` | session model | ~147k | Same |
| Wikidata queries + tables | `scout-wikidata` | session model | ~149k | SPARQL design under timeouts |
| Companies House bulk parser + chain walk | `ingest-ch-bulk` | session model | ~126k | Same |
| Spain sourcing (IBEX 35 documents, legal basis) | `scout-es` | session model | ~152k | Web research + judgement on sources |
| Spain extractor A (writes the regex extractor) | `extract-es-a` | session model | ~202k | Writing robust parsing code |
| **Spain extractor B (reads 35 notes)** | `extract-es-b` | **Sonnet** | ~130k (about 3.7k per document) | Bulk reading. Cheaper model is enough |
| Spain adjudication + 10-company hand-check | `qa` | session model | ~122k | The tie-breaker should be the strongest reader |
| **Sector classification, 794 companies** | `enrich-sector` | **Sonnet** | ~99k (about 125 per company) | Simple classification from name + labels |
| **UK spot-check, 20 reports** | `qa` | **Sonnet** | ~57k | Mechanical comparison |
| **DPO recompute check, 15 filings** | `qa` | **Sonnet** | ~79k | Mechanical comparison |
| Calibration gold set | `qa-calibration` | session model | ~109k | Judgement about what an "obvious ten" is, kept blind to the scores |
| Entity-resolution gold set, two rounds of 60 links | `qa` | session model | ~179k | Evidence gathering on the live register and the web, with judgement calls |
| Public site build and review fixes | `web` | session model | ~231k | Front-end build with legal constraints |
| One-pager copy and top-100 rationales (several passes as the ranking moved) | `assets` | session model | ~320k + ~98k | Writing for a critical reader. The repeated passes were the most expensive avoidable cost of the run |
| Reviews: site (journalist, lawyer), sales assets (COO, GTM lead), whole package (six personas) | `critic` | session model | ~219k, ~135k, ~179k | Critique needs the strongest reader |
| HQ country for 226 filing-only companies | `enrich-sector` | **Sonnet** | ~12k | Simple lookup from memory, applied only where confident |
| DACH slice: locate 29 annual reports on official IR pages | `scout` | session model | ~213k | Web research, judgement on official sources and blocks |
| DACH slice extractor B, 26 reports in two parallel readers | `extract-dach-b` | session model | ~86k + ~90k (about 6.8k per report) | Reading statements and notes under a written rule |
| DACH slice adjudication of 66 values + 10-company hand-check | `qa` | session model | ~108k | The tie-breaker should be the strongest reader |

## What the Spain eval says about routing

Both extractors found 32 of 35 values. The regex extractor cost nothing to run and got 31 of 32 payment periods right on its first pass. The LLM reader got 32 of 32, and was right on all 11 fields that went to adjudication (one company with two tables and swapped labels, plus percentages in layouts the regex missed). The pattern for the next run: code first, then a model for documents where the code finds nothing or fails its own arithmetic check. A model on every document is only needed while you are still measuring how often confident regex output is wrong, which here was once in 32.

## If this ran on API keys instead

Nothing in the pipeline needs an API key. The only script that calls a model API is the optional AEO monitor (`aeo/monitor.py`), which was not executed. It estimates its cost before running and refuses to start above `MAX_API_SPEND_USD`.
