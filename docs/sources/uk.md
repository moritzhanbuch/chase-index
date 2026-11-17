# Source notes: UK Payment Practices and Performance Reporting (Tier 1A)

Verified 2026-11-16 by the `ingest-uk` agent. Everything below was checked against the live pages on that date through the shared client (`chase.common.http`); raw responses are in the HTTP cache and logged in `data/manifests/http_log.jsonl`.

## Verdict

**Reachable, bulk CSV, open licence, per-report URLs. Best source in the project.** No key, no login.

| Item | Value |
|---|---|
| Public search (GOV.UK start page) | https://www.gov.uk/check-when-businesses-pay-invoices |
| Service home | https://check-payment-practices.service.gov.uk/ |
| Export landing page | https://check-payment-practices.service.gov.uk/export/ |
| **Bulk CSV (the file we ingest)** | https://check-payment-practices.service.gov.uk/export/csv/ |
| Per-report page (verified, HTTP 200) | `https://check-payment-practices.service.gov.uk/report/{report_id}` (the export's `URL` column carries it for every row) |
| Per-company page | None found. `/company/{number}` returns 404. Use the per-report URL of the latest report. |
| Format | One UTF-8 CSV, 52 columns, about 104.5 MB, 116,806 reports on 2026-11-16. No pagination, no API. |
| Licence | Open Government Licence v3.0 (stated in the service footer: "All content is available under the Open Government Licence v3.0, except where otherwise stated"). Attribution required: "Contains public sector information licensed under the Open Government Licence v3.0." |
| Legal basis | The Reporting on Payment Practices and Performance Regulations 2017, amended by The Reporting on Payment Practices and Performance (Amendment) Regulations 2024 |
| Update cadence | Live. Companies file within about a month of each half-year period ending; backdated filings happen. |
| Rate limits | None published. We use 1 request/second and the whole ingest is a single request. |

### robots.txt (https://check-payment-practices.service.gov.uk/robots.txt)

`User-agent: *` disallows `/set-cookie-banner-preference/`, `/publish/company/`, `/hide-cookie-banner/` and `/*?*` (any URL with a query string). Several named bots (GPTBot, ChatGPT-User, OAI-SearchBot, Bytespider, Amazonbot, SemrushBot and others) are disallowed entirely.

Consequences for this project:
- `/export/`, `/export/csv/` and `/report/{id}` are allowed for our user agent. That is all we fetch.
- **Search result URLs (`/search?q=...`) are disallowed** because they carry a query string. Do not script the search. Spot checks (`qa`) should open `/report/{id}` pages, which are allowed, or be done by a human in a browser.
- Do not bulk-crawl report pages. The CSV already has every statistical field. Fetch single report pages only for spot checks.

## Who reports

Large UK companies and LLPs, per legal entity, twice per financial year. The official statistics commentary gives the current size test: a business that exceeded 2 of these on its last 2 balance sheet dates: GBP 54 million annual turnover, GBP 27 million balance sheet total, 250 employees. The thresholds were raised in 2025, which reduced the reporting population (official valid reports fell 6.5% from 2024 to 2025).

Reports are by **legal entity** (Companies House number), not by group. A group like Tesco or Amazon files many separate entity reports. Roll-up to parents is Phase 2.

## Columns in the export (exact header names)

`Report Id`, `Policy Regime`, `Financial period start date`, `Start date`, `End date`, `Filing date`, `Company`, `Company number`, `Qualifying contracts in reporting period`, `Payments made in reporting period`, `Qualifying construction contracts in reporting period`, `Construction contracts have retention clauses`, `Average time to pay`, `Total value invoices paid within 30 days`, `Total value invoices paid between 31 and 60 days`, `Total value invoices paid later than 60 days`, `% Invoices paid within 30 days`, `% Invoices paid between 31 and 60 days`, `% Invoices paid later than 60 days`, `Total value invoices paid later than agreed terms`, `% Invoices not paid within agreed terms`, `% Invoices not paid due to dispute`, `Shortest (or only) standard payment period`, `Longest standard payment period`, `Standard payment terms`, `Payment terms have changed`, `Suppliers notified of changes`, `Maximum contractual payment period`, `Maximum contractual payment period information`, `Other information payment terms`, 14 retention-clause columns (`Retention clauses included in all construction contracts` through `Retention value compared to total payments as %`), `Dispute resolution process`, `Participates in payment codes`, `E-Invoicing offered`, `Supply-chain financing offered`, `Policy covers charges for remaining on supplier list`, `Charges have been made for remaining on supplier list`, `URL`.

The mapping to our snake_case names is the `RENAME` dict in `src/chase/sources/uk_payment_practices.py` and is documented in `docs/data_dictionary_uk.md`. The parser fails loudly if a header disappears.

The export does **not** contain the name of the director who approved the report. The report web page does ("Approved by: ..."). We do not collect it (personal data, not needed).

## Gotchas (all handled in the parser, none silently)

1. **Multi-line fields.** `wc -l` shows about 359k lines for 116,806 records. Count with a CSV parser.
2. **Three policy regimes.** `Regime-1` (99,898 reports, filed 2017-11 onward), `Regime-2` (7,451, periods starting from 2025-01-01) and `Regime-3` (9,457, financial years starting from 2025-04-01). Observed differences: only Regime-2/3 carry the value of invoices per payment band, the value paid late and the dispute share (introduced by the 2024 amendment regulations). In Regime-1 rows the export shows a placeholder `0` for "Total value invoices paid later than agreed terms" and "% Invoices not paid due to dispute"; the Regime-1 report page does not show those lines at all. We parse those zeros as null. The regime labels themselves are not explained on the export page; the description here is from the data plus the DBT methodology, not from an official definition of the labels.
3. **Legitimate blanks.** 9,487 reports state no qualifying contracts in the period: every metric is empty. Flag `no_qualifying_contracts`, metrics stay null.
4. **`Payments made in reporting period` is unreliable before 2019.** For reports filed in 2017 and 2018 it is almost always `False` even when payment statistics are present (the field seems to have been added later). We keep the raw value and only flag `no_payments_made` when the metrics are actually empty (79 reports).
5. **Duplicates and re-filings.** 3,802 reports share company + identical period with another report; more overlap partially. We follow the official DBT rule: identical period or overlap of more than one month, keep the most recently filed report (ties: report with data, then highest id). 2,474 reports are flagged `superseded_by_later_report` with `superseded_by_report_id`.
6. **Date typos.** Period start as early as 1918-12-30, period end as late as 3025-06-30. Kept as reported, flagged `period_dates_implausible` (17) or `period_length_out_of_range` (1,377 reports shorter than 150 or longer than 215 days, the DBT "5 to 7 months" rule). 53 reports were filed more than a month before the period ended (`filed_gt_1m_before_period_end`).
7. **Impossible averages.** `Average time to pay` goes up to 4,323,394 days. 49 reports exceed 365 days: kept, flagged `avg_days_gt_365`, excluded from `is_usable`. This is stricter than DBT, who keep extremes and rely on medians. For a company-level ranking we do not want a typo at the top of a list.
8. **Payment bands that do not add up.** The three "% paid within" bands should sum to 100. 98 to 102 is tolerated (rounding). 178 reports are outside (mostly all zeros): `pct_buckets_sum_off`.
9. **"% not paid within agreed terms" is sometimes entered the wrong way round.** Example: report 2 states 77% of invoices paid within 30 days, shortest standard term 30 days, and 89% "not paid within agreed terms". Both cannot be true. Where the shortest standard term is at least 30 (or 60) days and the late share exceeds what the payment bands allow by more than 10 points, we add the informational flag `pct_late_inconsistent_with_buckets` (7,561 reports, 6.5%). The value is kept and the report stays usable, because the two figures have slightly different bases (payments due vs payments made) and we cannot know which entry is wrong. **Scoring should not rank a company on `pct_paid_late` alone when this flag is set.**
10. **Value-field errors (2025 rules).** 47 reports with total value zero despite payments, 123 where the value paid late exceeds the total paid. Flagged (`value_total_zero`, `value_late_exceeds_total`), same treatment as DBT.
11. **Terms fields.** Standard and maximum terms go up to 5,475 days; 517 reports have a term above 365 days (`payment_terms_gt_365`, informational). Free-text terms are in the company's own words.
12. **Payment code field is free text.** 715 distinct spellings. `No` in 90.5% of reports. We keep the text and derive three booleans: `participates_in_payment_codes` (anything other than no / n/a / empty), `mentions_prompt_payment_code`, `mentions_fair_payment_code`. It is self-declared; for Fair Payment Code status prefer the awardee directory below.
13. **Names change.** 1,004 company numbers appear under more than one name. The company number is the key; `company_names_all` in the entity table lists every name used.
14. **Self-reported.** DBT: "Businesses are legally required to report correct information, but there is no independent verification of the data." Say this on the public site.
15. **Stale entities.** Of 9,557 entities with a usable report, 6,262 have one whose period ended within about 18 months of retrieval (`latest_is_stale = False`). The rest stopped reporting (below thresholds, dissolved, merged or non-compliant). Use the non-stale set for anything presented as current.

## What we built from it

- `data/raw/uk/payment_practices_export.csv` (raw, gitignored), manifest `data/manifests/uk_payment_practices.json` (url, sha256, bytes, retrieved_at).
- `data/processed/uk_payment_practices.parquet` / `.csv`: 116,806 rows, one per report. The CSV leaves out the long narrative columns to stay smaller; the parquet has everything.
- `data/processed/uk_entity_latest.parquet` / `.csv`: 10,309 rows, one per Companies House number.
- `evals/reports/uk_ingest_reconciliation.md`: row reconciliation plus the cross-check below.
- Re-run: `python -m chase.sources.uk_payment_practices` (add `--refresh` to re-download).

## Official benchmark (verified from the page itself)

Source: Department for Business and Trade, Official Statistics, **"Large businesses' payment practices and performance statistics 2025"**, published 14 July 2026.
- Release page: https://www.gov.uk/government/statistics/large-businesses-payment-practices-and-performance-statistics-2025
- Commentary: https://www.gov.uk/government/statistics/large-businesses-payment-practices-and-performance-statistics-2025/large-businesses-payment-practices-and-performance-statistics-2025-commentary
- Reference tables (ODS): https://assets.publishing.service.gov.uk/media/6a54be41c3d64d94cacab833/large-business-payment-practices-and-performance-statistics-2025-reference-tables.ods
- Methodology (PDF): https://assets.publishing.service.gov.uk/media/6a50c8a69e9c95844ae64ca1/large-business-payment-practices-statistics-methodology-and-background-quality-report.pdf
- Collection: https://www.gov.uk/government/collections/large-businesses-payment-practices-and-performance-statistics
- Licence: Open Government Licence v3.0.

Headline figures (all are **medians across valid reports**, not means; their data was extracted 2026-06-01):

| Reporting year | Time to pay (days) | Invoices paid late, by number (%) | Invoices paid late, by value (%) | Valid reports |
|---|---:|---:|---:|---:|
| 2018 | 35 | 25 | n/a | 13,175 |
| 2019 | 34 | 23 | n/a | 13,177 |
| 2020 | 34 | 23 | n/a | 12,371 |
| 2021 | 33 | 20 | n/a | 12,130 |
| 2022 | 33 | 20 | n/a | 11,830 |
| 2023 | 32 | 18 | n/a | 11,918 |
| 2024 | 32 | 16 | n/a | 11,954 |
| 2025 | **32** | **15** | **14** | 11,178 |

Quotable lines from the commentary: "In 2025, large businesses paid their suppliers in 32 days, down from 35 days in 2018"; "nearly 1 in 6 invoices were paid late in 2025"; Manufacturing had the longest time to pay in 2025 (45 days) and the highest share paid late by number (21%); Financial and insurance activities the shortest time to pay (21 days); London 27 days, East Midlands and West Midlands 38 days. The commentary also names the reference points we use: the Fair Payment Code benchmark of paying within 30 days, and legislative restrictions on terms above 60 days.

Sector (SIC section) and region medians for 2018 to 2025 are parsed into `data/processed/uk_official_benchmarks.csv` (long format, with source URL). Useful as sector benchmarks in scoring.

**Cross-check:** applying DBT's published cleaning rules to our parse reproduces the official median days to pay and median share paid late in 8 of 8 years (see `evals/reports/uk_ingest_reconciliation.md`). Valid-report counts differ slightly (within 0.5% for 2018 to 2024, +303 for 2025), which is expected because filings continued after their 1 June 2026 extract and their exact rule implementation is not published as code.

Oddity: the methodology PDF contains a stray paragraph of placeholder Latin text on its last page. It does not affect the rules we used.

## Fair Payment Code / Prompt Payment Code signatories

- The Prompt Payment Code was replaced by the **Fair Payment Code**, run by the Office of the Small Business Commissioner. Directory: https://www.smallbusinesscommissioner.gov.uk/fpc/awardees/ (public, no login; robots.txt allows all).
- **No machine-readable download** (no CSV, JSON or API found on the page). The directory is paginated HTML, 10 awardees per page, 86 pages on 2026-11-16.
- We read those 86 pages once through the shared client (1 request/second) with `python -m chase.sources.uk_fair_payment_code` and saved company-level fields only: `data/raw/uk/fair_payment_code_awardees.csv` (857 rows, matching the "Our 857 Awardees" count on the page: 373 Gold, 155 Silver, 327 Bronze, 2 with no level shown). Fields: awardee name, Companies House number (838 of 857 parse to a valid number; raw text kept), industry sector, area, award level, award expiry year, registration date, source page URL, retrieved_at. Manifest: `data/manifests/uk_fair_payment_code.json`.
- Award levels are described on the code's own pages (https://www.smallbusinesscommissioner.gov.uk/fpc/code-criteria/); we did not parse the criteria. Check that page before describing what Gold, Silver or Bronze require.
- Licence of the directory was not verified on the page. Treat it as public information to cite with a link, and confirm the licence before republishing the list in bulk.
- A historical list of Prompt Payment Code signatories was not looked for. The self-declared `payment_codes_text` field covers past PPC claims (9,363 reports mention it).

## Not done / open points

- No Companies House API calls here (group roll-up is Phase 2).
- The 20-row spot check against the website is `qa`'s job. Use `/report/{report_id}` URLs, not the search.
- Processed CSV of the report table is about 78 MB (parquet 28 MB). Under GitHub's 100 MB hard limit but large for a repo; the lead should decide whether to commit it or only the parquet.
