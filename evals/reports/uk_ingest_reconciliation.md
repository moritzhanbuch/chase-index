# UK payment practices: ingest reconciliation

- Generated: 2026-11-16T20:48:04Z by `python -m chase.sources.uk_payment_practices`
- Source: https://check-payment-practices.service.gov.uk/export/csv/ (retrieved 2026-11-16T10:03:07Z, 104,508,155 bytes, sha256 `5a4aa885b642b27a705aa41948538a34e1aa9813f28dd1bd5b6c6724679f1658`)
- What was checked: every record in the raw export arrives in the processed tables, nothing dropped, nothing duplicated.
- Method: independent count with Python's `csv` module (fields contain line breaks, so `wc -l` is not a valid count) compared with the parquet and CSV outputs.

## 1. Row reconciliation

| Check | Raw export | Processed | Result |
|---|---:|---:|---|
| Records in raw CSV (stdlib csv reader) | 116,806 | 116,806 | PASS |
| Rows in processed CSV copy | 116,806 | 116,806 | PASS |
| Distinct report ids | 116,806 | 116,806 | PASS |
| Distinct company numbers | 10,309 | 10,309 | PASS |
| Rows in entity table = distinct company numbers | 10,309 | 10,309 | PASS |
| Reports with a non-empty 'Average time to pay' | 107,240 | 107,240 | PASS |
| Sum of 'Average time to pay' (checksum) | 11,998,317 | 11,998,317 | PASS |

**Result: all checks pass.**

## 2. Coverage

- Reports: 116,806 (report ids 2 to 118763)
- Distinct entities (Companies House numbers): 10,309; distinct company names: 11,360
- Filing dates: 2017-11-07 to 2026-11-13
- Period range, all rows as reported (includes obvious typos): 1918-12-30 to 3025-06-30
- Period range, usable reports only: 2017-01-01 to 2026-10-31
- Usable reports (`is_usable`): 104,993 (89.9%); entities with at least one usable report: 9,557
- Entities whose latest usable report is recent (period ended within ~18 months of retrieval): 6,262
- Entities with a year-on-year trend (`trend_days_yoy` not null): 8,079
- Reports by policy regime: Regime-1: 99,898, Regime-2: 7,451, Regime-3: 9,457

## 3. Quality flags (a report can carry several; nothing is dropped)

| Flag | Reports | Makes report unusable |
|---|---:|---|
| `ok` | 97,018 | no |
| `no_qualifying_contracts` | 9,487 | yes |
| `pct_late_inconsistent_with_buckets` | 7,561 | no |
| `superseded_by_later_report` | 2,474 | yes |
| `period_length_out_of_range` | 1,377 | yes |
| `payment_terms_gt_365` | 517 | no |
| `avg_days_zero` | 307 | no |
| `pct_buckets_sum_off` | 178 | yes |
| `value_late_exceeds_total` | 123 | yes |
| `no_payments_made` | 79 | yes |
| `filed_gt_1m_before_period_end` | 53 | yes |
| `avg_days_gt_365` | 49 | yes |
| `value_total_zero` | 47 | yes |
| `period_dates_implausible` | 17 | yes |

## 4. Cross-check against the official DBT statistics

The Department for Business and Trade publishes medians across valid reports per calendar year ([statistics page](https://www.gov.uk/government/statistics/large-businesses-payment-practices-and-performance-statistics-2025), reference tables downloaded 2026-11-16T10:04:06Z). Their data was extracted on 2026-06-01 and businesses can file backdated reports, so small differences in counts are expected. `ours` uses `is_valid_dbt_method` (our replication of their published cleaning rules) and their reporting-year rule.

| Year | Median days to pay (official / ours) | Median % paid late (official / ours) | Valid reports (official / ours) | Diff in count |
|---|---|---|---|---:|
| 2018 | 35 / 35 | 25 / 25 | 13,175 / 13,157 | -18 |
| 2019 | 34 / 34 | 23 / 23 | 13,177 / 13,177 | +0 |
| 2020 | 34 / 34 | 23 / 23 | 12,371 / 12,370 | -1 |
| 2021 | 33 / 33 | 20 / 20 | 12,130 / 12,124 | -6 |
| 2022 | 33 / 33 | 20 / 20 | 11,830 / 11,852 | +22 |
| 2023 | 32 / 32 | 18 / 18 | 11,918 / 11,942 | +24 |
| 2024 | 32 / 32 | 16 / 16 | 11,954 / 12,008 | +54 |
| 2025 | 32 / 32 | 15 / 15 | 11,178 / 11,481 | +303 |

Median days to pay matches the official figure in 8 of 8 years; median % paid late matches in 8 of 8 years.

## 5. Failures and fixes

- `wc -l` on the raw file reports about 359k lines for 116k records because narrative fields contain line breaks. Fixed by counting with a real CSV parser.
- Period dates contain typos (for example a start year of 1918 and an end year of 3025). pandas nanosecond timestamps would have turned these into nulls; the parser uses second resolution, keeps the values as reported and flags them `period_dates_implausible`.
- Under the pre-2025 rules the export carries a placeholder 0 for the value of late payments and the dispute share. Parsed as null (not collected), not as zero.
- See `docs/sources/uk.md` for the full list of gotchas.
