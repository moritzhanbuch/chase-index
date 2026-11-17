# Source: SEC EDGAR XBRL APIs

Verified 2026-11-16 by the `ingest-sec` agent. Verdict: **reachable, free, no key, usable as specified**, with one material gap (IFRS frames, see gotcha 1).

## Endpoints used

| Purpose | URL | Verified |
|---|---|---|
| Ticker to CIK map | `https://www.sec.gov/files/company_tickers.json` | 200, 10,404 entries (`cik_str`, `ticker`, `title`) |
| All XBRL facts of one filer | `https://data.sec.gov/api/xbrl/companyfacts/CIK##########.json` (10-digit, zero-padded) | 200. `facts.{dei,us-gaap,ifrs-full}.{Concept}.units.{UNIT}[]` with `start`, `end`, `val`, `accn`, `fy`, `fp`, `form`, `filed`, optional `frame` |
| One concept, all filers, one period | `https://data.sec.gov/api/xbrl/frames/us-gaap/{Concept}/USD/CY2025.json` (duration) and `.../CY2025Q4I.json` (instant) | 200 for us-gaap. Rows: `accn`, `cik`, `entityName`, `loc`, `start`, `end`, `val` |
| Filer profile | `https://data.sec.gov/submissions/CIK##########.json` | 200. `name`, `tickers`, `exchanges`, `sic`, `sicDescription`, `stateOfIncorporation`, `fiscalYearEnd` (MMDD), `category`, `addresses.business` |
| Quarterly filing index by form type | `https://www.sec.gov/Archives/edgar/full-index/{YYYY}/QTR{n}/form.idx` | 200, fixed-width text. Used to list 20-F / 40-F filers |
| Filing folder (for humans checking a number) | `https://www.sec.gov/Archives/edgar/data/{cik_int}/{accession_without_dashes}/` | pattern |

Non-SEC helper: US Treasury Reporting Rates of Exchange, `https://api.fiscaldata.treasury.gov/services/api/fiscal_service/v1/accounting/od/rates_of_exchange` (public domain), used once to write `config/fx_rates_treasury.yaml`.

## Access policy and licence

- SEC fair-access policy: declare a User-Agent with a name and contact email, stay at or below 10 requests per second. We run at 2 requests per second through `chase.common.http` (0.5 s per host, disk cache, backoff on 429/5xx). The email comes from `.env` and is never logged.
- No API key, no login.
- Licence: EDGAR data is a US government work in the public domain. Attribution to SEC EDGAR is good practice.
- Freshness: the JSON APIs update in near real time as filings are accepted.

## Frame coverage measured (rows with value >= USD 4B)

| Concept | CY2025 | CY2024 |
|---|---|---|
| `Revenues` | 401 of 2,261 | 408 of 2,512 |
| `RevenueFromContractWithCustomerExcludingAssessedTax` | 530 of 2,715 | 534 of 2,974 |
| `RevenueFromContractWithCustomerIncludingAssessedTax` | 70 of 665 | 70 of 759 |
| `SalesRevenueNet` | 404 (retired concept) | 404 |

Union across concepts and both years: 904 distinct CIKs (911 after adding `RevenuesNetOfInterestExpense`).

## Gotchas

1. **`ifrs-full` frames are not served for recent periods.** `frames/ifrs-full/Revenue/USD/CY2019.json` returns data, but CY2023, CY2024 and CY2025 return 404 in USD, EUR, JPY, CNY and GBP (also `ProfitLoss`, `Assets`). Foreign private issuers reporting under IFRS therefore cannot be discovered through frames. Fallback used: every CIK that filed a 20-F or 40-F in the last five quarterly form indexes (2025 Q4 to 2026 Q4) is fetched through companyfacts and thresholded there.
2. **A frame holds one fact per filer and is calendar-aligned.** A fiscal year ending 31 Jan 2026 lands in CY2025. Frames are fine for discovery, not for pairing revenue, cost and payables. All final numbers come from companyfacts.
3. **`fy` and `fp` describe the filing, not the fact.** A 10-K for fiscal 2025 carries prior-year comparatives that are also labelled `fy=2025, fp=FY`. Fiscal years must be derived from `start` and `end` (we keep durations of 350 to 380 days, which covers 52/53-week years).
4. **Year-end balances reappear in later 10-Qs.** The balance at fiscal year end is repeated as a comparative in the following quarters. We only accept facts from annual forms (10-K, 20-F, 40-F and amendments), matched on the exact fiscal-year-end date.
5. **Restatements create duplicates.** The same period can appear in several filings with different values. Rule: the most recently filed annual-form value wins, and the accession number of the fact actually used is stored.
6. **Companyfacts holds only facts without dimensions.** Segment or product-level values are absent, so a concept in companyfacts is the consolidated line item. Companies that only tag payables or cost inside a dimension show up as missing.
7. **Concept choice varies by filer.** Revenue and cost of sales are tagged under several concepts, sometimes more than one for the same period (a subset and a total). We take the largest value across the accepted concepts for the period. Some filers tag no cost-of-sales concept at all (many service, airline, utility and holding companies), which triggers the flagged fallback to `CostsAndExpenses` / `OperatingCostsAndExpenses` / `OperatingExpenses` / ifrs `OperatingExpense`. A few filers tag a cost-of-sales concept that is only a sub-line (for example a utility's cost of goods sold): rows where cost is below 5% of revenue get a note and confidence 0.5. When both `AccountsPayableCurrent` and `AccountsPayableTradeCurrent` are tagged, one is a sub-detail, so the larger is used.
8. **Non-USD reporters.** Units are ISO currency codes inside each concept. DPO is a ratio and needs no conversion. Only the USD 4B threshold uses FX (one Treasury rate per currency, 31 Dec 2025, see `config/fx_rates_treasury.yaml`).
9. **Addresses use EDGAR's own state/country codes** (for example `M0` = Japan), with the name in `stateOrCountryDescription`. Newer profiles instead put the name in `country` and the EDGAR code (not ISO, for example `X0` = United Kingdom) in `countryCode`. We map the country name to ISO2 with a small table; unmapped values stay null with a note.
10. **Several CIKs can belong to one group** (finance arms, utility operating companies, dual registrants). This table is per CIK. Group roll-up happens in the universe step.
11. **Some CIKs have no companyfacts file** (404), typically filers without XBRL financial data. They are counted in the manifest and skipped.
12. **Size.** A companyfacts file for a large filer is several MB. The disk cache under `data/cache/http` (gitignored) grows to several GB for about 2,100 candidates. A cold run takes roughly 50 minutes at 2 requests per second; a cached rerun takes about a minute.
13. **Filer scale errors exist.** One filer (Tigo Energy, FY2025) tagged revenue 1,000x too large, which would have put a USD 100M company in the universe. Guard: a CIK is excluded when latest revenue exceeds 25x total assets. Exclusions are listed with the raw values in `data/manifests/sec_xbrl.json` under `excluded_probable_scale_error`. The guard also removes Bullish (a crypto exchange that books gross digital-asset sales as revenue), which is a deliberate side effect to review, not a tagging error.
