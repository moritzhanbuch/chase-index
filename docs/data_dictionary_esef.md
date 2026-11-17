# Data dictionary: ESEF tables (interim)

Built by `python -m chase.sources.esef_xbrl` from xBRL-JSON files on filings.xbrl.org. See `docs/sources/esef.md` for source notes and coverage gaps. All monetary values are in full currency units (not thousands or millions), in the filing's reporting currency. Only consolidated totals are used: facts that carry any dimension member (segments, restatements, parent-only columns) are ignored.

DPO here is always **computed DPO (proxy)**: a balance-sheet ratio, not a reported payment time.

## `data/interim/esef_companies.parquet` (+ `.csv`): one row per LEI

| Column | Type | Meaning |
|---|---|---|
| `lei` | str | Legal Entity Identifier of the filer (from the filing index). |
| `name` | str | Entity name as held by filings.xbrl.org. |
| `country` | str | ISO2 country of the filing system the selected filing came from. This is where the report was filed, usually the home market, not necessarily the HQ. |
| `countries_filed` | str | All countries this LEI has filings under in the index, comma separated (e.g. `GB,NL`). |
| `filing_id` | str | filings.xbrl.org filing id. |
| `filing_error_count` | int | Validation errors filings.xbrl.org recorded for the filing. |
| `fiscal_year_end` | date str | End of the latest full fiscal year found in the filing. |
| `revenue` | float | Latest fiscal-year revenue. Null if no revenue concept is tagged (typical for banks). |
| `revenue_concept` | str | First available of: `Revenue`; `RevenueFromContractsWithCustomers`; `RevenueFromSaleOfGoods+RevenueFromRenderingOfServices` (sum of whichever is tagged); `RevenueAndOperatingIncome` (includes other operating income). |
| `currency` | str | ISO 4217 reporting currency. |
| `revenue_usd` | float | `revenue` x rate from `config/fx_rates.yaml`. Rough, for size screening only. |
| `fx_year` | int/null | Year of the FX rate used. Null when the shared config holds one flat approximate rate for all years. |
| `large_cap_4b` | bool | `revenue_usd >= 4e9`. False when revenue is null, so banks/insurers are mostly False here: size them elsewhere. |
| `is_financial` | bool | Bank/insurer heuristic (see below). |
| `latest_dpo`, `latest_dpo_flag` | float, str | Copy of the latest-year values from `esef_dpo`. |
| `extraction_note` | str/null | Why nothing could be extracted (`no_full_fiscal_year_period_found`, `no_monetary_unit_found`, `parse_error:*`). |
| `source_url` | str | The filing's xBRL-JSON URL. |
| `report_url` | str | Human-viewable iXBRL viewer (or report) URL on filings.xbrl.org. |
| `source_type` | str | Always `esef_xbrl_json`. |
| `retrieved_at` | ISO ts | When the xBRL-JSON was downloaded. |
| `period_start`, `period_end` | date str | The latest fiscal year (inclusive dates). |
| `extraction_method` | str | Always `xbrl_json` (deterministic, no LLM). |
| `confidence` | float | 1.0 revenue from `Revenue`; 0.7 from a fallback concept; null if no revenue was found (nothing to be confident about). |

## `data/interim/esef_dpo.parquet` (+ `.csv`): one row per LEI per fiscal year (max two)

Both years come from the same filing: the latest report and its comparative column. `year_rank` 1 is the latest year.

| Column | Type | Meaning |
|---|---|---|
| `lei`, `name`, `country`, `countries_filed`, `filing_id`, `filing_error_count` | | As above. |
| `period_start`, `period_end`, `fiscal_year` | date str, int | Fiscal year covered (inclusive). `fiscal_year` is the calendar year of `period_end`. |
| `year_rank` | int | 1 = latest fiscal year in the filing, 2 = comparative year. |
| `currency` | str | Reporting currency. |
| `revenue`, `revenue_concept`, `revenue_usd`, `fx_year` | | As above, for this year. |
| `cost` | float | Denominator of DPO, absolute value. |
| `cost_concept` | str | `CostOfSales`, or the by-nature components joined with `+`. |
| `cost_basis` | str | `cost_of_sales`: ifrs-full:CostOfSales. `by_nature_fallback`: company reports expenses by nature, so cost = RawMaterialsAndConsumablesUsed + ServicesExpense + OtherExpenseByNature (whichever are tagged; at least one of the first two required). `missing`: neither available. |
| `raw_materials_and_consumables`, `services_expense`, `other_expense_by_nature` | float | Stored separately so a different denominator can be rebuilt. |
| `payables` | float | Year-end payables (instant at `period_end`). |
| `payables_concept` | str | First available of: `TradeAndOtherCurrentPayablesToTradeSuppliers`, `CurrentTradePayables`, `TradeAndOtherPayablesToTradeSuppliers`, `TradeAndOtherCurrentPayables`, `TradeAndOtherPayables`. |
| `payables_basis` | str | `trade` (first three) or `trade_and_other_broad` (last two: includes accruals, tax, payroll and other payables, so DPO is overstated). |
| `dpo` | float | `payables / cost x 365`, one decimal. Year-end balance, not an average. Null for financials or missing inputs. |
| `dpo_flag` | str | `ok`; `suspicious_low` (< 5); `suspicious_high` (> 365); `not_applicable` (bank/insurer); `missing_inputs`. |
| `is_financial` | bool | See below. |
| `confidence` | float | 1.0 only when `cost_basis = cost_of_sales` and `payables_basis = trade`; otherwise 0.7. |
| `source_url`, `report_url`, `source_type`, `retrieved_at`, `extraction_method` | | Provenance, as above. |

## Rules worth knowing

- **Period dates.** xBRL-JSON writes a period end as midnight of the next day. `2026-02-01T00:00:00` is stored as `2026-01-31`.
- **Fiscal year detection.** The reporting year is the 330 to 400 day period that carries the most undimensioned facts; the comparative is the full-year period ending about one year before. Short first fiscal years are not picked up (`extraction_note`).
- **Duplicates.** If a concept is tagged twice for the same period, the more precise value (higher `decimals`) wins.
- **Financial detection.** `is_financial` is true when no `CostOfSales` is tagged and one of: (a) a strong bank/insurance concept (`DepositsFromCustomers`, `DepositsFromBanks`, `LoansAndAdvancesToCustomers`, `LoansAndAdvancesToBanks`, `InsuranceRevenue`, insurance contract liabilities, insurance service result/expenses, `LiabilitiesDueToCentralBanks`) plus at least one more marker (another strong concept, net interest income `InterestRevenueExpense`, `FeeAndCommissionIncome`, effective-interest revenue); (b) any such marker and no revenue concept at all; (c) effective-interest revenue of at least half of revenue. One stray marker is not enough (Heineken tags `LoansAndAdvancesToCustomers`). Industrial and retail groups with a captive bank tag `CostOfSales` and stay non-financial. It is a heuristic: asset managers, real-estate and holding companies are not caught and can show odd DPO values.
- **Extension concepts.** Companies that tag payables or cost lines with their own extension elements instead of ifrs-full concepts end up with `missing_inputs`. No guessing.
- **Comparability.** A `by_nature_fallback` or `trade_and_other_broad` DPO is not comparable with a `cost_of_sales` + `trade` DPO. Compare within the same basis, or use `confidence` to filter.
