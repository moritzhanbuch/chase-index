# Data dictionary: UK payment practices tables

Source: UK statutory Payment Practices and Performance Reporting, bulk CSV export (`https://check-payment-practices.service.gov.uk/export/csv/`), Open Government Licence v3.0. Built by `python -m chase.sources.uk_payment_practices`. Source notes and gotchas: `docs/sources/uk.md`.

All figures are **self-reported by the company** for one legal entity and one reporting period (normally 6 months). Percentages are 0 to 100. Days are calendar days. Money is GBP. Null means the company did not report the value or it was not collected under the rules at the time. Nothing is imputed.

## 1. `data/processed/uk_payment_practices.parquet` (+ `.csv`)

One row per published report (entity x reporting period), full history, 116,806 rows on 2026-11-16. Key: `report_id`. The CSV copy omits the long narrative columns marked (parquet only).

### Identity and period

| Column | Type | Meaning | Unit |
|---|---|---|---|
| `report_id` | int64 | Report id assigned by the service. Unique. | id |
| `company_name` | string | Company name as shown on the report (can change over time for one company number). | text |
| `company_number` | string | Companies House number, 8 characters, zero-padded, upper case (prefixes such as SC, NI, OC kept). Entity key. | id |
| `period_start` | date | First day of the reporting period, as reported. | date |
| `period_end` | date | Last day of the reporting period, as reported. | date |
| `filing_date` | date | Date the report was filed. | date |
| `reporting_year` | int64 | Calendar year containing most of the period; ties go to the starting year (same rule as the official DBT statistics). | year |
| `period_days` | int64 | `period_end - period_start + 1`. | days |
| `policy_regime` | string | `Regime-1` (rules before 2025), `Regime-2`, `Regime-3` (2025 rules). See source notes. | category |
| `financial_period_start` | date | Start of the financial year the report belongs to. Mostly null before 2025. | date |

### Payment performance (the core metrics)

| Column | Type | Meaning | Unit |
|---|---|---|---|
| `avg_days_to_pay` | float64 | "Average time to pay": average number of days from receipt of invoice to payment, as reported. | days |
| `pct_paid_within_30` | float64 | Share of invoices paid within 30 days. | % of invoices |
| `pct_paid_31_60` | float64 | Share of invoices paid in 31 to 60 days. | % of invoices |
| `pct_paid_over_60` | float64 | Share of invoices paid in 61 days or more. | % of invoices |
| `pct_paid_late` | float64 | "% Invoices not paid within agreed terms": share of payments due in the period that were not paid within the agreed period. Check `quality_flag` for `pct_late_inconsistent_with_buckets`. | % of payments due |
| `pct_not_paid_due_to_dispute` | float64 | Share of payments due not made in the period because of a dispute. Collected from 2025 only; null under Regime-1. | % |
| `value_paid_within_30_gbp` | float64 | Total value of invoices paid within 30 days. 2025 rules only. | GBP |
| `value_paid_31_60_gbp` | float64 | Total value of invoices paid in 31 to 60 days. 2025 rules only. | GBP |
| `value_paid_over_60_gbp` | float64 | Total value of invoices paid in 61 days or more. 2025 rules only. | GBP |
| `value_paid_total_gbp` | float64 | **Computed**: sum of the three value bands (null unless all three present). | GBP |
| `value_paid_late_gbp` | float64 | Total value of payments not paid within the agreed period. 2025 rules only; Regime-1 placeholder zeros are null. | GBP |
| `pct_value_paid_late` | float64 | **Computed**: `100 * value_paid_late_gbp / value_paid_total_gbp`, null if the total is zero or the late value exceeds it. | % of value |

### Payment terms and practices

| Column | Type | Meaning | Unit |
|---|---|---|---|
| `shortest_standard_payment_period_days` | float64 | Shortest (or only) standard payment period. | days |
| `longest_standard_payment_period_days` | float64 | Longest standard payment period (null if only one). | days |
| `max_contractual_payment_period_days` | float64 | Maximum contractual payment period agreed. | days |
| `standard_payment_terms_text` | string | Standard payment terms in the company's own words. | text |
| `participates_in_payment_codes` | boolean | **Derived**: `payment_codes_text` is something other than no / n/a / empty. Self-declared. | flag |
| `mentions_prompt_payment_code` | boolean | **Derived**: text mentions "prompt payment" or "PPC". | flag |
| `mentions_fair_payment_code` | boolean | **Derived**: text mentions "Fair Payment Code" or "FPC". | flag |
| `payment_codes_text` | string | Answer to "signed up to a code of conduct or standards on payment practices? Which?" as written. | text |
| `offers_einvoicing` | boolean | Company states it offers e-invoicing. | flag |
| `offers_supply_chain_finance` | boolean | Company states it offers supply chain finance. | flag |
| `policy_covers_supplier_list_charges` | boolean | Payment policy covers charges for remaining on the supplier list. | flag |
| `charged_for_supplier_list` | boolean | Company has charged suppliers for remaining on its supplier list. | flag |
| `had_qualifying_contracts` | boolean | Company had qualifying contracts in the period. False means a legitimately blank report. | flag |
| `payments_made_in_period` | boolean | Raw "Payments made in reporting period". Unreliable for reports filed in 2017 and 2018. | flag |
| `payment_terms_changed_text` | string | Changes to standard terms in the period (parquet only). | text |
| `suppliers_notified_of_changes_text` | string | Whether suppliers were notified or consulted (parquet only). | text |
| `max_contractual_payment_period_info_text` | string | Comment on the maximum period (parquet only). | text |
| `other_payment_terms_info_text` | string | Other information on payment terms (parquet only). | text |
| `dispute_resolution_process_text` | string | Dispute resolution process, own words (parquet only). | text |

### Construction retention (2025 rules, sparse)

| Column | Type | Meaning | Unit |
|---|---|---|---|
| `had_qualifying_construction_contracts` | boolean | Had qualifying construction contracts in the period. | flag |
| `construction_contracts_have_retention_clauses` | boolean | Construction contracts include retention clauses. | flag |
| `retention_in_all_construction_contracts` | boolean | Retention clauses in all construction contracts. | flag |
| `retention_in_standard_payment_terms` | boolean | Retention clauses in standard payment terms. | flag |
| `retention_in_specific_circumstances` | boolean | Retention clauses used in specific circumstances. | flag |
| `retention_above_specific_sum` | boolean | Retention clauses used above a specific contract sum. | flag |
| `retention_threshold_value_gbp` | float64 | Contract value above which retention clauses are used. | GBP |
| `retention_at_standard_rate` | boolean | Retention at a standard rate. | flag |
| `retention_standard_rate_pct` | float64 | The standard retention rate. | % |
| `retention_parity_with_client` | boolean | Retention terms mirror those of the client. | flag |
| `retention_release_is_staged` | boolean | Retention money released in stages. | flag |
| `retention_value_vs_client_retentions_pct` | float64 | Retention withheld from suppliers compared with retention withheld by clients. | % |
| `retention_value_vs_total_payments_pct` | float64 | Retention withheld compared with total payments. | % |
| `retention_specific_circumstances_text`, `retention_parity_policy_text`, `retention_release_text`, `retention_release_stages_text` | string | Narrative answers (parquet only). | text |

### Quality

| Column | Type | Meaning | Unit |
|---|---|---|---|
| `quality_flag` | string | `ok`, or one or more flags joined by `;`. See table below. | flags |
| `is_usable` | boolean | True if all five core metrics are present and no hard flag applies. Use this filter for company-level figures. | flag |
| `is_valid_dbt_method` | boolean | True if the report passes our replication of the official DBT cleaning rules (keeps extreme values). Use only to compare with official statistics. | flag |
| `superseded_by_report_id` | Int64 | If a later filing covers the same or an overlapping period, its `report_id`. | id |

| Flag | Hard (excluded from `is_usable`) | Meaning |
|---|---|---|
| `no_qualifying_contracts` | yes | Company reported no qualifying contracts; metrics are legitimately empty. |
| `no_payments_made` | yes | Qualifying contracts but no payments, metrics empty. |
| `metrics_missing` | yes | Payments made but core metrics partly empty. |
| `period_dates_implausible` | yes | Start before 2016, end before start, or end more than a year after retrieval. |
| `period_length_out_of_range` | yes | Period shorter than 150 or longer than 215 days (official "5 to 7 months" rule). |
| `filed_gt_1m_before_period_end` | yes | Filed more than 31 days before the period ended. |
| `avg_days_gt_365` | yes | Average time to pay above 365 days (value kept as reported). |
| `pct_buckets_sum_off` | yes | The three payment bands sum to less than 98 or more than 102. |
| `value_total_zero` | yes | 2025 rules: total value paid is zero although payments were reported. |
| `value_late_exceeds_total` | yes | 2025 rules: value paid late exceeds total value paid. |
| `superseded_by_later_report` | yes | A later filing covers the same or an overlapping (more than 30 days) period. |
| `pct_late_inconsistent_with_buckets` | no | Late share is more than 10 points above what the payment bands and shortest standard term allow. The late share may have been entered the wrong way round. Treat `pct_paid_late` with care. |
| `avg_days_zero` | no | Average time to pay reported as 0 days. |
| `payment_terms_gt_365` | no | A standard or maximum term above 365 days. |

### Provenance (every row, never null)

| Column | Type | Meaning |
|---|---|---|
| `source_url` | string | Public page of this report: `https://check-payment-practices.service.gov.uk/report/{report_id}` (pattern verified). |
| `source_export_url` | string | The bulk export the row was parsed from. |
| `source_type` | string | `uk_ppr_statutory_report`. |
| `retrieved_at` | string | ISO 8601 UTC timestamp of the export download. |
| `extraction_method` | string | `official_csv_export`. |
| `confidence` | float64 | 1.0: values are copied from the official export. This is confidence in the extraction, not in what the company reported. |

`period_start` and `period_end` complete the provenance set required by project rule 7.

## 2. `data/processed/uk_entity_latest.parquet` (+ `.csv`)

One row per Companies House number, 10,309 rows. Key: `company_number`. "Latest" means the most recent **usable** report by period end. Entities with no usable report (752) keep a row with null metrics. These are UK legal entities, not groups.

| Column | Type | Meaning | Unit |
|---|---|---|---|
| `company_number` | string | Companies House number (8 characters). | id |
| `company_name` | string | Name on the latest usable report (or the most recent filing if none is usable). | text |
| `company_names_all` | string | Every name used under this number, oldest first, joined by ` \| `. | text |
| `n_reports` | int64 | All reports filed by the entity. | count |
| `n_reports_usable` | int64 | Reports with `is_usable = True`. | count |
| `has_usable_report` | boolean | At least one usable report. | flag |
| `first_period_start` | date | Earliest period start among usable reports. | date |
| `last_period_end` | date | Latest period end among usable reports. | date |
| `latest_report_id` | Int64 | `report_id` of the latest usable report. | id |
| `period_start`, `period_end`, `filing_date` | date | Period and filing date of the latest usable report (of the most recent filing if none is usable). | date |
| `latest_is_stale` | boolean | Latest usable period ended more than 548 days (about 18 months) before retrieval. The entity has probably stopped reporting. | flag |
| `policy_regime`, `avg_days_to_pay`, `pct_paid_within_30`, `pct_paid_31_60`, `pct_paid_over_60`, `pct_paid_late`, `pct_not_paid_due_to_dispute`, `value_paid_total_gbp`, `value_paid_late_gbp`, `pct_value_paid_late`, `shortest_standard_payment_period_days`, `longest_standard_payment_period_days`, `max_contractual_payment_period_days`, `standard_payment_terms_text`, `participates_in_payment_codes`, `mentions_prompt_payment_code`, `mentions_fair_payment_code`, `payment_codes_text`, `offers_einvoicing`, `offers_supply_chain_finance`, `quality_flag` | as in table 1 | Values of the latest usable report. | as in table 1 |
| `avg_days_to_pay_mean_last2` | float64 | Mean of `avg_days_to_pay` over the latest two usable reports (roughly one year). Simple mean, not weighted. | days |
| `pct_paid_late_mean_last2` | float64 | Same for `pct_paid_late`. | % |
| `n_reports_in_mean_last2` | Int64 | 1 or 2. | count |
| `prev_report_id`, `prev_period_start`, `prev_period_end`, `prev_avg_days_to_pay`, `prev_pct_paid_within_30`, `prev_pct_paid_over_60`, `prev_pct_paid_late` | mixed | The usable report immediately before the latest. | as named |
| `yoy_report_id`, `yoy_period_start`, `yoy_period_end`, `yoy_avg_days_to_pay`, `yoy_pct_paid_within_30`, `yoy_pct_paid_over_60`, `yoy_pct_paid_late` | mixed | The usable report whose period end is closest to one year before the latest period end, within 92 days. Null if none. | as named |
| `trend_days_vs_prev` | float64 | `avg_days_to_pay - prev_avg_days_to_pay`. Positive means slower. | days |
| `trend_pct_late_vs_prev` | float64 | `pct_paid_late - prev_pct_paid_late`. | percentage points |
| `trend_days_yoy` | float64 | `avg_days_to_pay - yoy_avg_days_to_pay`. Positive means slower than a year earlier. | days |
| `trend_pct_late_yoy` | float64 | `pct_paid_late - yoy_pct_paid_late`. | percentage points |
| `trend_pct_over_60_yoy` | float64 | `pct_paid_over_60 - yoy_pct_paid_over_60`. | percentage points |
| `most_recent_filing_report_id` | int64 | The entity's most recently filed report, usable or not. | id |
| `most_recent_filing_date` | date | Its filing date. | date |
| `most_recent_filing_quality_flag` | string | Its `quality_flag`. Shows when the newest filing was blank or flagged. | flags |
| `source_url`, `source_export_url`, `source_type`, `retrieved_at`, `extraction_method`, `confidence` | as in table 1 | Provenance of the latest usable report (of the most recent filing if none is usable). | |

## 3. `data/processed/uk_official_benchmarks.csv`

Official DBT statistics (medians across valid reports), long format, 900 rows. Source: reference tables of "Large businesses' payment practices and performance statistics 2025".

| Column | Type | Meaning |
|---|---|---|
| `breakdown_type` | string | `headline`, `region` (ITL1) or `sic_section`. |
| `breakdown` | string | `UK`, the region name or the SIC section label. |
| `reporting_year` | Int64 | 2018 to 2025. |
| `metric` | string | Metric name as in the official table ("Time to pay (days)", "Proportion of invoices paid late, by number (%)", "... by value (%)", "Number of valid reports"). |
| `value` | float64 | The published figure. |
| `statistic` | string | `median` or `count`. |
| `table_title` | string | Title of the official table. |
| `source_url`, `source_page`, `source_type`, `retrieved_at`, `period_start`, `period_end`, `extraction_method`, `confidence` | | Provenance. |

## 4. `data/raw/uk/fair_payment_code_awardees.csv` (raw, not committed)

Fair Payment Code awardee directory, 857 rows. Columns: `awardee_name`, `company_number_raw`, `company_number` (normalised, null if not a valid Companies House number), `industry_sector`, `area`, `award_level` (Gold / Silver / Bronze), `award_until_year`, `registration_date_text`, `registration_date`, `source_url`, `source_type`, `retrieved_at`, `extraction_method` (`html_directory_parse`), `confidence` (0.95).
