# Supplier finance tags across the whole universe (extractor A)

Generated 2026-11-16 by `python -m chase.sources.supplier_finance --universe` (deterministic XBRL tag reader, same code as the top-200 run, new flag only). Output: `data/interim/sfa_universe_tags.csv` (one row per company, 1,909 rows), run meta in `data/interim/sfa_universe_tags.json`. Runtime 143 s. All 999 SEC company-facts files came from cache; 33 ESEF xBRL-JSON files were missing from cache and were downloaded through the shared client (rate limited). No fetch failed, so there is no coverage gap from downloads.

## Read this first

`not_tagged` does NOT mean "no supplier finance programme". ESEF filers tag their notes as text blocks, so an IFRS programme disclosure usually carries no dedicated concept. US filers below materiality do not tag ASU 2022-04 facts at all. SEC company facts only carry standard numeric facts. Treat `tagged` as positive evidence and everything else as "unknown".

## Coverage by status and source

| Source | tagged | tagged_text_only | not_tagged | no_structured_source | Total |
|---|---|---|---|---|---|
| SEC (us-gaap / ifrs-full company facts) | 190 | 0 | 809 | 0 | 999 |
| ESEF (filings.xbrl.org xBRL-JSON) | 1 | 9 | 340 | 0 | 350 |
| None | 0 | 0 | 0 | 560 | 560 |
| **Total** | **191** | **9** | **1,149** | **560** | **1,909** |

- Tagged with a period-end amount: **188** of 191 (183 in USD, 3 CNY, 2 EUR, 1 CAD). The 3 without an amount tag only flows (confirmed / paid in period).
- ESEF: only 1 numeric tag (a company-extension concept); 9 have a dedicated IFRS supplier-finance text block. This reflects block tagging, not the absence of programmes.
- `no_structured_source` (560): 246 companies have neither a CIK nor an LEI in the universe; 314 have an LEI but no ESEF filing in the filings.xbrl.org index (mostly non-EU/UK listings, e.g. Japan, China, India).
- Separately from the tag status, the ESEF text scan found a supplier-finance phrase in 147 filings (`text_mention_*` fields in the full record; not part of the slim CSV).

## Columns

`company_id, name, status, source, amount, currency, period_end, concept, source_url, retrieved_at`. `amount` is the tagged period-end obligation (`obligation_amount` in the full record). `concept` is the amount concept, else the supplier-finance concept found, else the text-mention concept.
