# AEO: getting cited by answer engines

Independent project by Moritz Hanbuch.

## The gap

A public X thread (2026-11-09) showed that when finance leads ask ChatGPT unbranded questions about AP/AR automation, newer two-sided agent networks are not named. The shortlists go to Esker, Stampli, Tipalti, BILL, HighRadius, Coupa, Basware, SAP Taulia, C2FO, Versapay, Medius, Serrala and Billtrust. Answer engines learn a category from comparison tables, data pages and practitioner threads. Original, citable data is one of the strongest ways to earn a citation.

## What this folder contains

| File | What it is |
|---|---|
| `monitor.py` | Share-of-voice baseline. Sends 8 unbranded buyer prompts (the 3 from the thread plus 5 variants) to every answer engine with an API key in `.env`, records which vendors each answer names (pass `--brand "Your Brand"` or set `AEO_BRAND` to track your own name next to the shortlist), writes dated results to `aeo/results/`. |
| `results/` | Dated runs. Empty until someone runs the monitor with a key. |

The AEO assets themselves live in the site (`site/`): a `Dataset` JSON-LD block, a CSV download with a licence note, `llms.txt`, `sitemap.xml`, a `robots.txt` that allows AI crawlers, and an FAQ that answers the unbranded questions factually.

## Status of this run

No model API keys were set, so the monitor was **not executed**. Nothing here is a measured result. `python aeo/monitor.py --dry-run` prints the prompts and the cost estimate without calling anything.

## How to run it

```bash
# add ANTHROPIC_API_KEY and/or OPENAI_API_KEY and/or PERPLEXITY_API_KEY to .env
.venv/bin/python aeo/monitor.py --dry-run     # check prompts and estimated cost
.venv/bin/python aeo/monitor.py --runs 3      # 3 repeats per prompt, answers vary between runs
```

Estimated cost for one run across all three providers is well under $1. The script refuses to start if the estimate exceeds `MAX_API_SPEND_USD`.

## How to read the result

- `share of voice` = share of answers that name a vendor at least once. It is a crude measure: it ignores position and sentiment.
- API answers are not identical to what the consumer apps show (no browsing unless the model has it, different system prompts). Treat the number as a trend line, not as the truth about ChatGPT.
- Run it before publishing the index, then every two weeks. The interesting number is the change, and whether answers start citing the index pages.

## Limits

- It never scrapes consumer chat UIs.
- Eight prompts is a small panel. Add the questions the sales team actually hears.
- Vendor matching is by name regex. `BILL` is matched case-sensitively to avoid counting the common noun.
