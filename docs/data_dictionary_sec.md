# Data dictionary: SEC XBRL tables

Built by `python -m chase.sources.sec_xbrl`. Source notes: `docs/sources/sec.md`. Run manifest: `data/manifests/sec_xbrl.json`.

Both tables are per **CIK** (SEC registrant), not per corporate group.

## `data/interim/sec_companies.parquet` (+ `.csv`)

One row per SEC filer whose latest full fiscal year revenue is >= USD 4B.

| Column | Type | Description |
|---|---|---|
| `cik` | string | SEC Central Index Key, 10 digits, zero-padded |
| `name` | string | Registrant name from the submissions API (falls back to companyfacts `entityName`) |
| `tickers` | string | Comma-separated tickers from the submissions API; null if none |
| `exchanges` | string | Comma-separated exchanges |
| `sic` | string | SEC Standard Industrial Classification code; null for some foreign filers |
| `sic_description` | string | SIC label as given by the SEC |
| `is_financial_sic` | bool | SIC 6000 to 6799 (banks, insurers, other financials, real estate): DPO not computed |
| `country` | string | ISO 3166-1 alpha-2 of the business address; null if the EDGAR value could not be mapped |
| `country_name` | string | Country name as given by EDGAR |
| `state` | string | US state of the business address (US filers only) |
| `state_of_incorporation` | string | EDGAR state/country code of incorporation (EDGAR's own code list, not ISO) |
| `fiscal_year_end_mmdd` | string | Fiscal year end as MMDD from the submissions API |
| `filer_category` | string | SEC filer category (for example "Large accelerated filer") |
| `discovery_route` | string | How the CIK became a candidate: `usgaap_frame`, `fpi_form_index` (20-F/40-F filer) or both |
| `latest_fiscal_year` | int | Calendar year in which the latest full fiscal year **ends** |
| `is_latest_fy_current` | bool | Latest fiscal year ends on or after 2025-07-01. False means the filer has not filed a newer annual report (acquired, delisted or late) |
| `revenue` | float | Latest fiscal year revenue in the reporting currency |
| `currency` | string | ISO 4217 reporting currency of the XBRL facts |
| `revenue_usd` | float | Revenue in USD. Equal to `revenue` for USD reporters, otherwise a rough conversion used only for the size threshold |
| `revenue_usd_method` | string | `reported_usd` or `fx_treasury_2025-12-31` |
| `fx_rate_per_usd` | float | Currency units per 1 USD used (1.0 for USD). Rates and source in `config/fx_rates_treasury.yaml` |
| `revenue_concept` | string | `taxonomy:Concept` of the revenue fact used |
| `period_start`, `period_end` | date string | The fiscal year the revenue covers |
| `form` | string | Form type of the filing the revenue fact comes from |
| `accession_number` | string | Accession number of that filing |
| `filed` | date string | Filing date |
| `filing_url` | string | EDGAR folder of that filing |
| `source_url` | string | companyfacts API URL for the CIK |
| `submissions_url` | string | submissions API URL for the CIK (name, SIC, address, tickers) |
| `source_type` | string | Always `sec_xbrl_companyfacts` |
| `retrieved_at` | ISO timestamp | When the companyfacts JSON was downloaded (cache time, UTC) |
| `extraction_method` | string | Always `xbrl_api` |
| `confidence` | float | 1.0 (revenue is a standard tagged concept) |
| `notes` | string | FX conversion note, unmapped country, missing profile |

## `data/interim/sec_dpo.parquet` (+ `.csv`)

One row per CIK per fiscal year, latest two full fiscal years. Same filer set as `sec_companies`.

`dpo` is **computed DPO (proxy)**: a balance-sheet ratio, not a reported payment time.

| Column | Type | Description |
|---|---|---|
| `cik`, `name`, `sic`, `tickers`, `country` | | As above |
| `fiscal_year` | int | Calendar year in which the fiscal year ends |
| `period_start`, `period_end` | date string | Fiscal year covered by revenue and cost. Payables are measured at `period_end` |
| `currency` | string | Reporting currency of all three inputs (always the same unit for one row) |
| `revenue` | float | Revenue for the fiscal year |
| `revenue_concept` | string | `taxonomy:Concept`. The largest value across accepted revenue concepts for the period |
| `cost_of_sales` | float | Denominator. Null if nothing usable is tagged |
| `cost_concept` | string | `taxonomy:Concept` used |
| `cost_basis` | string | `cost_of_sales` (CostOfRevenue, CostOfGoodsAndServicesSold, CostOfGoodsSold, CostOfGoodsAndServiceExcludingDepreciationDepletionAndAmortization, ifrs CostOfSales; largest for the period) or `operating_expenses_fallback` (first available of CostsAndExpenses, OperatingCostsAndExpenses, OperatingExpenses, ifrs OperatingExpense). Fallback makes DPO lower than a true cost-of-sales DPO |
| `payables` | float | Numerator: payables at fiscal year end |
| `payables_concept` | string | `taxonomy:Concept` used. Four tiers in priority order, largest value inside a tier: (1) AccountsPayableTradeCurrent, AccountsPayableCurrent, ifrs TradeAndOtherCurrentPayablesToTradeSuppliers, CurrentTradePayables; (2) unclassified balance sheets: AccountsPayableTradeCurrentAndNoncurrent, AccountsPayableCurrentAndNoncurrent, ifrs TradeAndOtherPayablesToTradeSuppliers; (3) broad: AccountsPayableAndAccruedLiabilitiesCurrent, AccountsPayableAndOtherAccruedLiabilitiesCurrent, ifrs TradeAndOtherCurrentPayables; (4) broad, unclassified: AccountsPayableAndAccruedLiabilitiesCurrentAndNoncurrent, ifrs TradeAndOtherPayables |
| `payables_basis` | string | `trade` or `trade_and_other_broad` (includes accruals and other payables, so DPO is overstated) |
| `dpo` | float | `payables / cost_of_sales * 365`, 2 decimals. Null when inputs are missing or the filer is a financial |
| `dpo_flag` | string | `ok`; `suspicious_low` (< 5); `suspicious_high` (> 365); `not_applicable` (SIC 6000 to 6799, DPO not computed); `missing_inputs` |
| `notes` | string | Why a value is null, which fallback applied, other warnings |
| `form`, `accession_number`, `filed`, `filing_url` | | The most recently filed annual filing among the three facts used. Usually all three come from it |
| `revenue_accession`, `cost_accession`, `payables_accession` | string | Accession number of each individual fact (they differ when a later filing restated one input) |
| `source_url` | string | companyfacts API URL for the CIK |
| `source_type` | string | `sec_xbrl_companyfacts` |
| `retrieved_at` | ISO timestamp | Download time of the companyfacts JSON |
| `extraction_method` | string | `xbrl_api` |
| `confidence` | float | 1.0 with a cost-of-sales concept and a trade payables concept; 0.7 if either fallback or broad concept was used; 0.5 if the cost concept is below 5% of revenue (probably a sub-line, DPO overstated; see `notes`) |

## Selection rules in one place

- Annual forms only: 10-K, 10-K/A, 10-K405, 20-F, 20-F/A, 40-F, 40-F/A.
- Full fiscal year = duration of 350 to 380 days. Fiscal years are derived from the revenue facts.
- Same period reported in several filings: the most recently filed value wins (restated comparatives).
- Year-end average payables are **not** used. DPO uses the closing balance, which is the common convention and reproducible from one filing.
- `revenue_usd` conversion uses one spot rate per currency (US Treasury, 31 Dec 2025), not period averages.
