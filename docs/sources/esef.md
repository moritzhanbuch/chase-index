# Source: ESEF / UKSEF annual reports via filings.xbrl.org

Verified 2026-11-16 by the `ingest-esef` agent. Used for Tier 2 **computed DPO (proxy)** and for sizing European listed groups. Pipeline: `src/chase/sources/esef_xbrl.py`. Field definitions: `docs/data_dictionary_esef.md`. Run counts: `data/manifests/esef_xbrl.json`.

## Verdict

Usable and free, with one big hole: **there are no German filings at all**. Good for Spain, France, Netherlands, Italy, the Nordics and UK-listed companies. Germany needs another route (see Gaps).

## What it is

filings.xbrl.org is a repository run by XBRL International that collects Inline XBRL annual financial reports filed under ESEF (EU), UKSEF (UK) and the Ukrainian reporting system. For each filing it publishes the iXBRL viewer, the original report package and the tagged data as **xBRL-JSON**. The site itself says the repository "is not complete": some filings fail processing and some cannot be assigned an LEI.

## Endpoints (all verified)

| What | URL | Notes |
|---|---|---|
| Static index, one file per period-end year | `https://filings.xbrl.org/indexes/filings-{YEAR}.json` | The API docs call this "the preferred way to download a list of all filings". Same JSON:API shape as the API (`data` + `included` entities). 2025 file is about 3.8 MB. **This is what the pipeline uses.** |
| Filings API | `https://filings.xbrl.org/api/filings` | JSON:API. `page[size]` (default 30, max 1000), `page[number]` (from 1), `include=entity`, `sort=-period_end` / `-processed`, `filter[country]=ES`, or `filter=[{"name":"period_end","op":"ge","val":"2024-01-01"}]` (ops: eq, ne, lt, le, gt, ge, like, ilike, in, ...). `meta.count` gives the total (27,669 filings on 2026-11-16). |
| Entities API | `https://filings.xbrl.org/api/entities`, `/api/entities/{LEI}`, `/api/entities/{LEI}/filings` | Attributes: `identifier` (LEI), `name`. 7,497 entities. Name search works with `filter=[{"name":"name","op":"ilike","val":"%iberdrola%"}]`. |
| Validation messages | `/api/filings/{id}/validation_messages` | Not used. |
| API docs | `https://filings.xbrl.org/docs/api`, `https://filings.xbrl.org/docs/about` | |

Filing attributes: `period_end`, `country` (ISO2 of the filing system), `fxo_id`, `date_added`, `processed`, `published`, `sha256`, `viewer_url`, `report_url`, `package_url`, `json_url`, `error_count`, `warning_count`, `inconsistency_count`. URL attributes are site-relative paths: prefix with `https://filings.xbrl.org`. The entity LEI and name come from the related `entity` resource.

xBRL-JSON (`json_url`): `{"documentInfo": {...}, "facts": {id: {"value", "decimals", "dimensions": {"concept", "entity", "period", "unit", ...extra axes}}}}`. Typical size 1 to 5 MB.

## Gotchas found

- **Values are full units.** Check: Inditex (LEI 549300TTCXZOGZM2EY83) `ifrs-full:Revenue` for the year to 31 Jan 2026 is 39,864,000,000 EUR in the JSON; the comparative year is 38,632,000,000 EUR, which is the EUR 38.6bn Inditex published for FY2024. No scaling needed.
- **Period ends are written as midnight of the next day** (`2026-02-01T00:00:00` means 31 Jan 2026). The pipeline converts to inclusive dates.
- **One filing carries two years** (current + comparative), so one download per entity gives two fiscal years.
- **Index `period_end` is not always right.** Example: an AEDAS Homes filing indexed under 2026-12-31 contains a report to 2026-03-31. The pipeline takes fiscal periods from the facts, never from the index, and ignores index period ends later than the run date.
- **Dual filers** appear under two countries with the same LEI (Shell: GB and NL). The pipeline keeps one filing per LEI and lists all countries in `countries_filed`.
- 286 index rows have no `json_url` (processing failed); 1,127 filings have validation errors. Errors are mostly calculation inconsistencies, so a filing with errors is still used when it is the only one for the latest period.
- `country` is where the report was filed, not HQ.

## Terms, robots, rate limits

- `https://filings.xbrl.org/robots.txt` returns 404: no crawl restrictions published.
- The about and API pages publish no licence text, no API key requirement and no stated rate limit. The API is described as public. The filings are regulated public disclosures. Treated as: free to access and analyse, attribute the source, link back to the filing. **Open question for Mo:** no explicit redistribution licence was found, so the public site should link to the filings and show derived figures rather than mirror the raw files.
- Our usage: shared client `chase.common.http`, at most one request start per second, descriptive User-Agent, on-disk cache (each file is fetched once), static index files instead of paging the API.

## Coverage of the index by country (period-end year, filings, 2026-11-16)

| Country | 2021 | 2022 | 2023 | 2024 | 2025 | 2026 |
|---|---|---|---|---|---|---|
| ES | 140 | 139 | 134 | 127 | 122 | 6 |
| FR | 228 | 241 | 218 | 225 | 184 | 23 |
| NL | 132 | 135 | 126 | 130 | 113 | 3 |
| IT | 189 | 187 | 170 | 199 | 125 | 4 |
| GB | 341 | 659 | 643 | 590 | 552 | 163 |
| SE | 363 | 373 | 365 | 359 | 356 | 15 |
| DK | 228 | 399 | 458 | 448 | 491 | 158 |
| NO | 249 | 252 | 240 | 238 | 218 | 2 |
| FI | 232 | 227 | 195 | 214 | 166 | 2 |
| BE | 205 | 145 | 142 | 135 | 58 | 3 |
| AT | 110 | 102 | 99 | 102 | 91 | 8 |
| PT | 54 | 58 | 51 | 49 | 53 | 4 |
| LU | 68 | 68 | 63 | 64 | 3 | 0 |
| PL | 271 | 304 | 161 | 6 | 0 | 0 |
| GR | 143 | 141 | 146 | 150 | 123 | 2 |
| **DE** | 0 | 0 | 0 | 0 | 0 | 0 |
| **IE** | 0 | 0 | 0 | 0 | 0 | 0 |
| **CH** | 0 | 0 | 0 | 0 | 0 | 0 |

Also present: MT, IS, LT, HU, HR, SI, SK, EE, LV, CY, CZ, RO (small or stale) and UA (about 9,900 filings, different taxonomy, excluded).

## Gaps, stated plainly

- **Germany: zero filings.** The entity table has records for Siemens AG, Volkswagen AG and BASF SE, but `/api/entities/{LEI}/filings` returns an empty list for each, and no filing in the index has `country=DE`. German issuers file ESEF reports with the Bundesanzeiger / Unternehmensregister, which this repository does not ingest. DAX/MDAX computed DPO cannot come from this source. Fallbacks for the lead agent: SEC 20-F data for the few German SEC filers, Wikidata revenue for sizing, or the Unternehmensregister ESEF packages (not attempted here: terms and access need their own check).
- **Ireland and Switzerland: zero filings.** Ireland has no ESEF feed here (CRH, for example, only has GB filings for 2021 and 2022 and now reports under US rules). Switzerland is outside ESEF.
- **UK: present and current.** Contrary to the expectation that UK coverage ended after Brexit, UKSEF filings continue (552 filings with 2025 period ends, 163 with 2026). The GB set includes many investment trusts and small caps.
- **Poland, Luxembourg, Belgium, Croatia, Hungary, Romania:** coverage stops or thins out after 2023 or 2024. Figures from those countries can be stale; check `fiscal_year_end`.
- **Banks and insurers:** flagged `is_financial`, DPO set to null (`not_applicable`). They usually tag no `Revenue`, so they fall below the size screen in this table; size them from another source.
- **Tagging choices limit DPO quality.** Many issuers tag only the broad `TradeAndOtherCurrentPayables`, which includes non-supplier payables and overstates DPO (flagged `trade_and_other_broad`, confidence 0.7). Companies reporting expenses by nature have no `CostOfSales`; a documented fallback denominator is used (flagged `by_nature_fallback`, confidence 0.7). Issuers that use extension elements for these lines get `missing_inputs`.
- **Not every entity was downloaded in this run.** Downloads are time-boxed and ordered by country priority. The exact covered counts per country are in `data/manifests/esef_xbrl.json` (`coverage_by_country`: selected vs downloaded). Re-running the module continues from the cache.

## What this run actually covered (2026-11-16, time-boxed to about 25 minutes of downloading)

| Country | Entities selected | Downloaded + parsed | With revenue | Flagged financial | Revenue >= USD 4B | Latest-year DPO computed | >= USD 4B with DPO |
|---|---|---|---|---|---|---|---|
| ES | 128 | 128 (100%) | 113 | 13 | 27 | 88 | 21 |
| FR | 241 | 241 (100%) | 207 | 22 | 66 | 128 | 33 |
| NL | 133 | 133 (100%) | 119 | 15 | 40 | 70 | 25 |
| IT | 197 | 197 (100%) | 164 | 26 | 19 | 143 | 14 |
| GB | 694 | 248 (36%) | 199 | 18 | 27 | 118 | 16 |
| DE, IE, CH | 0 | 0 | | | | | |
| SE, DK, NO, FI, BE, AT, PT, LU, PL, GR and others | 2,379 in total | 0 | | | | | |

Totals: 947 entities parsed, 1,870 entity-year rows, 179 entities with revenue >= USD 4B, of which 109 have a computed DPO for the latest year (102 flagged `ok`, 7 `suspicious_high`), 63 are `missing_inputs` and 7 are banks/insurers. Only 25 of the large groups have the clean combination (`CostOfSales` + trade-supplier payables, confidence 1.0). The same numbers are in the manifest (`coverage_by_country`).

- **GB is a partial, arbitrary sample**: entities are downloaded in LEI order, so the 248 covered are not the largest 248. Large UK groups can be missing (Shell and Unilever are present through their NL filings).
- **Nothing outside ES, FR, NL, IT, GB was downloaded.** Re-run `python -m chase.sources.esef_xbrl --max-minutes N` to continue: cached files are skipped, download order is the country priority list in the module. Observed throughput was about 0.55 files per second (files are 1 to 5 MB), so the remaining ~2,400 entities need roughly 75 minutes.
- **FX:** `revenue_usd` uses the shared `config/fx_rates.yaml`, which holds one hand-typed approximate rate per currency for all years (EUR 1.08, GBP 1.27). It is a size screen, not a published figure. If that file is absent the module builds a per-year table from ECB annual average reference rates instead.

## Selection rule used

One filing per LEI: the latest `period_end` between 2023-01-01 and the run date that has an xBRL-JSON; for the same period, the filing with fewest validation errors, then the most recently processed. Ukraine excluded.
