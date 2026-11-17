# Sources

Independent project by Moritz Hanbuch.

Every source was checked live on 2026-11-16 before use. Verdicts first, details per source below (each section was written by the subagent that verified and ingested that source).

| # | Source | Verdict | Used for | Licence / terms | Fallback or gap |
|---|---|---|---|---|---|
| A | UK Payment Practices and Performance Reporting (bulk CSV export at check-payment-practices.service.gov.uk/export/csv/) | Reachable. 116,806 reports, 10,309 entities | Tier 1 reported data, supplier lookup | Open Government Licence v3.0 | None needed. robots.txt disallows query-string URLs, so the spot-check uses `/report/{id}` pages |
| A2 | DBT official statistics 2025 (GOV.UK) | Reachable | Benchmarks (median 32 days, 15% late) | OGL v3.0 | None |
| A3 | Fair Payment Code awardee directory | Reachable as HTML only (857 awardees) | Stored raw, not yet used in scoring | Licence of the directory not verified: not republished | Self-declared code membership from the reports is used instead |
| B | Spain: statutory PMP note (Ley 15/2010 DA 3) in annual reports | 33 of 35 IBEX documents sourced (FY2025), 32 with a value | Tier 1 reported data | Public regulatory filings; we publish derived figures and link out | Ferrovial, ArcelorMittal: non-Spanish issuers, no note. Sabadell: table not in tagged text |
| C | France: overdue-invoice table (Code de commerce L. 441-14 / D. 441-6) | Not attempted. It is a parent-only year-end snapshot of overdue invoices, not average days to pay; article texts not retrieved from Legifrance in this run | Nothing | n/a | France is covered by computed DPO only |
| D | Germany: statutory payment-performance reporting | Does not exist. BGB 271a only caps payment terms; the EU Late Payment Regulation proposal is still pending | Nothing | n/a | Germany is covered by computed DPO only, and thinly (see F) |
| E | SEC EDGAR XBRL (frames + companyfacts + submissions) | Reachable. 1,058 filers with revenue >= USD 4B | Universe, computed DPO | Public domain; fair-access policy followed (declared User-Agent, 2 req/s) | IFRS frames return 404 for recent years: foreign filers found via the 20-F/40-F form indexes |
| F | ESEF filings (filings.xbrl.org static indexes + xBRL-JSON) | Reachable, partial. ES, FR, NL, IT complete; GB partial; DE, IE, CH have no filings there | Universe, computed DPO, Spanish PMP source documents | No explicit licence or robots.txt found: derived figures only, link to filings | German groups have DPO only if they also file with the SEC |
| G | Wikidata SPARQL | Reachable. 1,483 companies with revenue >= about USD 3B | Universe, identifiers, HQ city, parent links | CC0 | Community-edited: revenue year kept and flagged when stale |
| H | Companies House API | No key in this run | Nothing | n/a | Replaced by the free bulk snapshots (H2) |
| H2 | Companies House bulk data: basic company data + PSC snapshot | Reachable, no key or login. robots.txt allows all | UK group roll-up via corporate parent chains | Crown copyright; GOV.UK states no restrictions on use of public register information. Attribution: "Contains public sector information from Companies House" | Only corporate PSC records are parsed; records about individuals are dropped before parsing |
| I | ERP and hiring signals from public careers and press pages | Not collected at scale in this run | Nothing (ERP component is neutral) | n/a | Scoring supports `data/processed/signals.csv` with evidence URLs when someone collects them |
| - | Forbes Global 2000 | Not used | Nothing | Terms not checked, list not scraped | Equivalent universe built from E, F, G with a documented revenue threshold |



---

# Detail: A. UK payment practices

## Source notes: UK Payment Practices and Performance Reporting (Tier 1A)

Verified 2026-11-16 by the `ingest-uk` agent. Everything below was checked against the live pages on that date through the shared client (`chase.common.http`); raw responses are in the HTTP cache and logged in `data/manifests/http_log.jsonl`.

### Verdict

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

#### robots.txt (https://check-payment-practices.service.gov.uk/robots.txt)

`User-agent: *` disallows `/set-cookie-banner-preference/`, `/publish/company/`, `/hide-cookie-banner/` and `/*?*` (any URL with a query string). Several named bots (GPTBot, ChatGPT-User, OAI-SearchBot, Bytespider, Amazonbot, SemrushBot and others) are disallowed entirely.

Consequences for this project:
- `/export/`, `/export/csv/` and `/report/{id}` are allowed for our user agent. That is all we fetch.
- **Search result URLs (`/search?q=...`) are disallowed** because they carry a query string. Do not script the search. Spot checks (`qa`) should open `/report/{id}` pages, which are allowed, or be done by a human in a browser.
- Do not bulk-crawl report pages. The CSV already has every statistical field. Fetch single report pages only for spot checks.

### Who reports

Large UK companies and LLPs, per legal entity, twice per financial year. The official statistics commentary gives the current size test: a business that exceeded 2 of these on its last 2 balance sheet dates: GBP 54 million annual turnover, GBP 27 million balance sheet total, 250 employees. The thresholds were raised in 2025, which reduced the reporting population (official valid reports fell 6.5% from 2024 to 2025).

Reports are by **legal entity** (Companies House number), not by group. A group like Tesco or Amazon files many separate entity reports. Roll-up to parents is Phase 2.

### Columns in the export (exact header names)

`Report Id`, `Policy Regime`, `Financial period start date`, `Start date`, `End date`, `Filing date`, `Company`, `Company number`, `Qualifying contracts in reporting period`, `Payments made in reporting period`, `Qualifying construction contracts in reporting period`, `Construction contracts have retention clauses`, `Average time to pay`, `Total value invoices paid within 30 days`, `Total value invoices paid between 31 and 60 days`, `Total value invoices paid later than 60 days`, `% Invoices paid within 30 days`, `% Invoices paid between 31 and 60 days`, `% Invoices paid later than 60 days`, `Total value invoices paid later than agreed terms`, `% Invoices not paid within agreed terms`, `% Invoices not paid due to dispute`, `Shortest (or only) standard payment period`, `Longest standard payment period`, `Standard payment terms`, `Payment terms have changed`, `Suppliers notified of changes`, `Maximum contractual payment period`, `Maximum contractual payment period information`, `Other information payment terms`, 14 retention-clause columns (`Retention clauses included in all construction contracts` through `Retention value compared to total payments as %`), `Dispute resolution process`, `Participates in payment codes`, `E-Invoicing offered`, `Supply-chain financing offered`, `Policy covers charges for remaining on supplier list`, `Charges have been made for remaining on supplier list`, `URL`.

The mapping to our snake_case names is the `RENAME` dict in `src/chase/sources/uk_payment_practices.py` and is documented in `docs/data_dictionary_uk.md`. The parser fails loudly if a header disappears.

The export does **not** contain the name of the director who approved the report. The report web page does ("Approved by: ..."). We do not collect it (personal data, not needed).

### Gotchas (all handled in the parser, none silently)

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

### What we built from it

- `data/raw/uk/payment_practices_export.csv` (raw, gitignored), manifest `data/manifests/uk_payment_practices.json` (url, sha256, bytes, retrieved_at).
- `data/processed/uk_payment_practices.parquet` / `.csv`: 116,806 rows, one per report. The CSV leaves out the long narrative columns to stay smaller; the parquet has everything.
- `data/processed/uk_entity_latest.parquet` / `.csv`: 10,309 rows, one per Companies House number.
- `evals/reports/uk_ingest_reconciliation.md`: row reconciliation plus the cross-check below.
- Re-run: `python -m chase.sources.uk_payment_practices` (add `--refresh` to re-download).

### Official benchmark (verified from the page itself)

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

### Fair Payment Code / Prompt Payment Code signatories

- The Prompt Payment Code was replaced by the **Fair Payment Code**, run by the Office of the Small Business Commissioner. Directory: https://www.smallbusinesscommissioner.gov.uk/fpc/awardees/ (public, no login; robots.txt allows all).
- **No machine-readable download** (no CSV, JSON or API found on the page). The directory is paginated HTML, 10 awardees per page, 86 pages on 2026-11-16.
- We read those 86 pages once through the shared client (1 request/second) with `python -m chase.sources.uk_fair_payment_code` and saved company-level fields only: `data/raw/uk/fair_payment_code_awardees.csv` (857 rows, matching the "Our 857 Awardees" count on the page: 373 Gold, 155 Silver, 327 Bronze, 2 with no level shown). Fields: awardee name, Companies House number (838 of 857 parse to a valid number; raw text kept), industry sector, area, award level, award expiry year, registration date, source page URL, retrieved_at. Manifest: `data/manifests/uk_fair_payment_code.json`.
- Award levels are described on the code's own pages (https://www.smallbusinesscommissioner.gov.uk/fpc/code-criteria/); we did not parse the criteria. Check that page before describing what Gold, Silver or Bronze require.
- Licence of the directory was not verified on the page. Treat it as public information to cite with a link, and confirm the licence before republishing the list in bulk.
- A historical list of Prompt Payment Code signatories was not looked for. The self-declared `payment_codes_text` field covers past PPC claims (9,363 reports mention it).

### Not done / open points

- No Companies House API calls here (group roll-up is Phase 2).
- The 20-row spot check against the website is `qa`'s job. Use `/report/{report_id}` URLs, not the search.
- Processed CSV of the report table is about 78 MB (parquet 28 MB). Under GitHub's 100 MB hard limit but large for a repo; the lead should decide whether to commit it or only the parquet.


---

# Detail: B. Spain PMP

## Spain: periodo medio de pago a proveedores (PMP)

Scouted 2026-11-16 by `scout-es`. All legal texts below were read on boe.es on that date.

### Legal basis

| What | Reference | URL |
|---|---|---|
| Payment terms: 30 calendar days by default, never more than 60 by agreement | Ley 3/2004, de 29 de diciembre, art. 4 (wording in force since 2013) | https://www.boe.es/buscar/act.php?id=BOE-A-2004-21830 |
| Disclosure duty ("Deber de información") | Ley 15/2010, de 5 de julio, disposición adicional tercera (BOE no. 163, 6 July 2010) | https://www.boe.es/buscar/act.php?id=BOE-A-2010-10708 |
| First amendment of DA 3ª | Ley 31/2014, de 3 de diciembre, disposición final segunda (in force 24 Dec 2014) | https://www.boe.es/buscar/act.php?id=BOE-A-2014-12589 |
| Current wording of DA 3ª (adds invoices paid within the legal maximum) | Ley 18/2022, de 28 de septiembre, "de creación y crecimiento de empresas", art. 9.2 (BOE no. 234, 29 Sept 2022; in force 19 Oct 2022). BOE's consolidated text cites **art. 9.2**, not just art. 9 | https://www.boe.es/buscar/act.php?id=BOE-A-2022-15818 |
| Formula and note layout | Resolución de 29 de enero de 2016 del ICAC (BOE 4 Feb 2016, BOE-A-2016-1112), applies to financial years starting on or after 1 Jan 2015 | https://www.boe.es/buscar/doc.php?id=BOE-A-2016-1112 |

DA 3ª as in force (paraphrased, 4 paragraphs):
1. Every sociedad mercantil states its PMP in the notes (memoria) to its annual accounts.
2. Listed companies publish on their website the PMP, the monetary volume and number of invoices paid within the legal maximum, and the share these represent of all invoices and of all supplier payments. The same goes in the notes.
3. Unlisted companies that do not file abridged accounts publish the same (on their website if they have one) and in the notes.
4. ICAC adapts the calculation method by resolution.

### The statutory formula (ICAC Resolution 29 Jan 2016, art. 5)

```
PMP = (ratio operaciones pagadas x importe total pagos realizados
       + ratio operaciones pendientes de pago x importe total pagos pendientes)
      / (importe total pagos realizados + importe total pagos pendientes)

ratio operaciones pagadas    = sum(días de pago x importe operación pagada) / importe total pagos realizados
ratio operaciones pendientes = sum(días pendientes x importe operación pendiente) / importe total pagos pendientes
```

- Days are calendar days counted from receipt of goods or services (invoice receipt date allowed if that is not reliably known) to payment, or to the period end for pending items (art. 5.2 to 5.4).
- "Proveedores" = trade creditors in current liabilities for goods or services (art. 4.b). Fixed-asset suppliers and financial creditors are out.
- Required table (art. 6.1): PMP, ratio pagadas, ratio pendientes (days); total pagos realizados, total pagos pendientes (amount), current and prior year. Ley 18/2022 adds the paid-within-maximum rows.
- Small companies on the abridged/PYME model use a different, balance-based formula (art. 5.5). Not relevant for IBEX 35 but never mix the two.

### Where the data lives

1. **Notes to the consolidated annual accounts**, inside the ESEF annual financial report. https://filings.xbrl.org hosts every Spanish ESEF filing (API: `/api/filings?filter[country]=ES&include=entity`, no robots.txt, open). Each filing has a `report_url` (XHTML, 5 to 77 MB gzip, slow host at about 65 KB/s on the day) and a `json_url` (xBRL-JSON, 0.7 to 4 MB gzip). Because notes are block-tagged since FY2022, **the JSON text-block facts contain the PMP note**. This was the uniform route: 31 of 33 Spanish-domiciled constituents.
2. **Company IR page "Periodo medio de pago a proveedores"** (the website duty in DA 3ª.2). Used for Santander and BBVA, whose JSON text blocks do not carry the note. These pages state the parent-company figure only.
3. CNMV (`cnmv.es`, informes financieros anuales) holds the same ESEF packages. Not needed.

Files: `data/manifests/es_pmp_sources.json`, `data/interim/es_pmp_sources.csv`, `data/interim/es_snippets/<TICKER>.txt`, raw in `data/raw/es/<TICKER>/`, constituents in `data/interim/ibex35_constituents.csv`.

IBEX 35 composition: BME "Composición histórica IBEX 35" PDF, September 2026 edition (https://www.bolsasymercados.es/dam/descargas/indices/composicion-ibex-35-es-en.pdf). Last change 22 July 2024 (Puig in, Meliá out); every review through 21 Sept 2026 left it unchanged.

### Gotchas for extractors

- **Scope.** The consolidated table covers only the **Spanish entities** of the group, after intragroup eliminations (ICAC art. 2.2 and 6.2). It is not a global group figure. Label it "Spanish group entities". Individual (parent-only) accounts carry a separate table; IR pages of Santander and BBVA give the parent-only figure. Record which one was extracted and never compare them as like for like.
- **Non-Spanish parents.** Ferrovial SE (Netherlands since 2023) and ArcelorMittal (Luxembourg) are IBEX constituents but not Spanish sociedades: no PMP note found in their group reports. Report them as not available, not as zero.
- **Banks and insurers** disclose too, but supplier payments are a small part of their business. Keep, flag `is_financial`, exclude from rankings of commercial payers.
- **Fiscal years.** Inditex FY2025 ends 31 Jan 2026. Logista FY2025 ends 30 Sept 2025.
- **Units vary**: days as integers or with decimals (Spanish decimal comma), amounts in euros, thousands or millions. Some tables have three year columns (CaixaBank).
- **Text artefacts.** Endesa's text has letter-spacing artefacts ("2 1 .0 91" = 21.091). Snippets come from HTML-to-text conversion, so table cells are flattened in reading order: current year first, prior year second.
- **Narrative-only disclosures.** Some companies give the PMP in a sentence, not a table (seen in the Unicaja snippet).
- **Duplicates.** Nested text-block tags repeat the same note; snippets are de-duplicated but an extractor should expect repeats.
- **PMcM and other analyses.** The Plataforma Multisectorial contra la Morosidad publishes its own analyses based on CNMV data, with much higher figures for IBEX non-financials than the statutory PMP. Its method is not the ICAC formula (PMcM's exact method was not verified in this pass). Never mix or compare them in one column. Same for our own computed DPO.
- **Self-reported.** PMP is prepared by the company and audited as part of the notes; confirming (reverse factoring) arrangements can shorten the reported PMP while the cash cost shifts to banks. Endesa's note, for example, describes its confirming lines right next to the table.


---

# Detail: C/D. France and Germany

## France and Germany: is there reported supplier-payment data?

Scouted 2026-11-16 by `scout-es`. Short verdicts only; no pilot was run.

### France: feasible only as a different metric. Verdict: defer.

- **What exists.** Companies whose annual accounts are certified by a statutory auditor must include in the management report (rapport de gestion) information on supplier and customer payment terms: the number and total amount of invoices received (and issued) that are unpaid at the closing date and overdue, broken down by lateness bucket, and as a percentage of the year's purchases (or turnover). Alternatively they may report invoices that suffered a payment delay during the year. Tables follow a model set by ministerial order, and the auditor attests to them.
- **References.** Code de commerce art. **L. 441-14** (legislative basis, numbering since Ordonnance 2019-359) and art. **D. 441-6** (content of the tables). Before the 2019 recodification these were L. 441-6-1 and D. 441-4 (décrets 2015-1553 and 2017-350); older commentary still uses the old numbers. **Caveat: the current article texts were not retrieved from legifrance.gouv.fr in this pass** (two article URLs returned 404). The description above rests on secondary sources (CMS Francis Lefebvre note on D. 441-4, a translation page for D. 441-6 that ties it to L. 441-14 and the ministerial table model, DGCCRF fiche on payment terms). Verify on Légifrance before citing in public methodology.
- **Why it is not comparable.** The French table is a year-end snapshot of overdue invoices for the **parent company (société mère) only**, not an average days-to-pay figure and not a group figure. A CAC 40 holding company often shows a handful of overdue invoices. It cannot sit in the same column as UK "average days to pay" or Spanish PMP.
- **Machine-findability.** The table sits in the URD (Document d'Enregistrement Universel), which CAC 40 issuers file in ESEF. French ESEF filings are on filings.xbrl.org (`filter[country]=FR`), so the same xBRL-JSON text-block route used for Spain may work, but the management report is outside the block-tagged financial statements, so expect to need the full XHTML (large files, slow host). Not tested.
- **Example URLs (entry points, not verified documents):** `https://filings.xbrl.org/api/filings?filter[country]=FR&include=entity` (ESEF filings API), `https://www.info-financiere.fr` (AMF regulated-information store), `https://www.economie.gouv.fr/dgccrf/les-fiches-pratiques/delais-de-paiement-les-regles-connaitre` (DGCCRF rules; DGCCRF also publishes sanctions for late payment by named companies, which is a possible "why now" signal). No three CAC 40 URDs were opened; that part of the brief was cut by the coordinator.
- **Verdict.** A CAC 40 pilot is technically possible but yields a parent-only overdue-invoice table, weak for ranking. Use computed DPO (Tier 2) for France and, if wanted later, DGCCRF sanction notices as a signal.

### Germany: no statutory payment-performance reporting. Verdict: Tier 2 computed DPO only.

- **Checked.** § 271a BGB (read on gesetze-im-internet.de, https://www.gesetze-im-internet.de/bgb/__271a.html): caps agreed payment terms at 60 days unless expressly agreed and not grossly unfair, 30 days for public authorities (over 60 void), 30 days for acceptance periods. It contains **no reporting or disclosure duty**. §§ 286 and 288 BGB (default after 30 days, default interest, EUR 40 lump sum) complete the transposition of Directive 2011/7/EU; they were not re-read in this pass.
- **Secondary confirmation.** A DLA Piper overview of European prompt-payment law (2025) states that the UK requires large companies to report payment practices and that Germany has no such mandatory reporting. No German equivalent of the UK regime or of the Spanish PMP note turned up in searches. (That overview says the same of France, which is right in the sense that France has no UK-style average-days report.)
- **EU level.** The proposed Late Payment Regulation, COM(2023) 533, procedure 2023/0323(COD): Parliament adopted its first-reading position on 23 April 2024; the Legislative Observatory shows the status "Awaiting Council's 1st reading position" on 2026-11-16 (https://oeil.europarl.europa.eu/oeil/en/procedure-file?reference=2023/0323(COD)). Trade press reports a blocking group in Council and signals that the Commission may drop it; no formal withdrawal is recorded on the procedure file. Directive 2011/7/EU therefore remains the law, and it has no company-level reporting duty.
- **Conclusion.** For German companies there is no official reported days-to-pay figure. Germany is covered by computed DPO (proxy) from ESEF/XBRL only, plus UK reports of their UK subsidiaries and Spanish PMP of their Spanish subsidiaries where those exist. Say so plainly on the site.


---

# Detail: E. SEC EDGAR

## Source: SEC EDGAR XBRL APIs

Verified 2026-11-16 by the `ingest-sec` agent. Verdict: **reachable, free, no key, usable as specified**, with one material gap (IFRS frames, see gotcha 1).

### Endpoints used

| Purpose | URL | Verified |
|---|---|---|
| Ticker to CIK map | `https://www.sec.gov/files/company_tickers.json` | 200, 10,404 entries (`cik_str`, `ticker`, `title`) |
| All XBRL facts of one filer | `https://data.sec.gov/api/xbrl/companyfacts/CIK##########.json` (10-digit, zero-padded) | 200. `facts.{dei,us-gaap,ifrs-full}.{Concept}.units.{UNIT}[]` with `start`, `end`, `val`, `accn`, `fy`, `fp`, `form`, `filed`, optional `frame` |
| One concept, all filers, one period | `https://data.sec.gov/api/xbrl/frames/us-gaap/{Concept}/USD/CY2025.json` (duration) and `.../CY2025Q4I.json` (instant) | 200 for us-gaap. Rows: `accn`, `cik`, `entityName`, `loc`, `start`, `end`, `val` |
| Filer profile | `https://data.sec.gov/submissions/CIK##########.json` | 200. `name`, `tickers`, `exchanges`, `sic`, `sicDescription`, `stateOfIncorporation`, `fiscalYearEnd` (MMDD), `category`, `addresses.business` |
| Quarterly filing index by form type | `https://www.sec.gov/Archives/edgar/full-index/{YYYY}/QTR{n}/form.idx` | 200, fixed-width text. Used to list 20-F / 40-F filers |
| Filing folder (for humans checking a number) | `https://www.sec.gov/Archives/edgar/data/{cik_int}/{accession_without_dashes}/` | pattern |

Non-SEC helper: US Treasury Reporting Rates of Exchange, `https://api.fiscaldata.treasury.gov/services/api/fiscal_service/v1/accounting/od/rates_of_exchange` (public domain), used once to write `config/fx_rates_treasury.yaml`.

### Access policy and licence

- SEC fair-access policy: declare a User-Agent with a name and contact email, stay at or below 10 requests per second. We run at 2 requests per second through `chase.common.http` (0.5 s per host, disk cache, backoff on 429/5xx). The email comes from `.env` and is never logged.
- No API key, no login.
- Licence: EDGAR data is a US government work in the public domain. Attribution to SEC EDGAR is good practice.
- Freshness: the JSON APIs update in near real time as filings are accepted.

### Frame coverage measured (rows with value >= USD 4B)

| Concept | CY2025 | CY2024 |
|---|---|---|
| `Revenues` | 401 of 2,261 | 408 of 2,512 |
| `RevenueFromContractWithCustomerExcludingAssessedTax` | 530 of 2,715 | 534 of 2,974 |
| `RevenueFromContractWithCustomerIncludingAssessedTax` | 70 of 665 | 70 of 759 |
| `SalesRevenueNet` | 404 (retired concept) | 404 |

Union across concepts and both years: 904 distinct CIKs (911 after adding `RevenuesNetOfInterestExpense`).

### Gotchas

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


---

# Detail: F. ESEF

## Source: ESEF / UKSEF annual reports via filings.xbrl.org

Verified 2026-11-16 by the `ingest-esef` agent. Used for Tier 2 **computed DPO (proxy)** and for sizing European listed groups. Pipeline: `src/chase/sources/esef_xbrl.py`. Field definitions: `docs/data_dictionary_esef.md`. Run counts: `data/manifests/esef_xbrl.json`.

### Verdict

Usable and free, with one big hole: **there are no German filings at all**. Good for Spain, France, Netherlands, Italy, the Nordics and UK-listed companies. Germany needs another route (see Gaps).

### What it is

filings.xbrl.org is a repository run by XBRL International that collects Inline XBRL annual financial reports filed under ESEF (EU), UKSEF (UK) and the Ukrainian reporting system. For each filing it publishes the iXBRL viewer, the original report package and the tagged data as **xBRL-JSON**. The site itself says the repository "is not complete": some filings fail processing and some cannot be assigned an LEI.

### Endpoints (all verified)

| What | URL | Notes |
|---|---|---|
| Static index, one file per period-end year | `https://filings.xbrl.org/indexes/filings-{YEAR}.json` | The API docs call this "the preferred way to download a list of all filings". Same JSON:API shape as the API (`data` + `included` entities). 2025 file is about 3.8 MB. **This is what the pipeline uses.** |
| Filings API | `https://filings.xbrl.org/api/filings` | JSON:API. `page[size]` (default 30, max 1000), `page[number]` (from 1), `include=entity`, `sort=-period_end` / `-processed`, `filter[country]=ES`, or `filter=[{"name":"period_end","op":"ge","val":"2024-01-01"}]` (ops: eq, ne, lt, le, gt, ge, like, ilike, in, ...). `meta.count` gives the total (27,669 filings on 2026-11-16). |
| Entities API | `https://filings.xbrl.org/api/entities`, `/api/entities/{LEI}`, `/api/entities/{LEI}/filings` | Attributes: `identifier` (LEI), `name`. 7,497 entities. Name search works with `filter=[{"name":"name","op":"ilike","val":"%iberdrola%"}]`. |
| Validation messages | `/api/filings/{id}/validation_messages` | Not used. |
| API docs | `https://filings.xbrl.org/docs/api`, `https://filings.xbrl.org/docs/about` | |

Filing attributes: `period_end`, `country` (ISO2 of the filing system), `fxo_id`, `date_added`, `processed`, `published`, `sha256`, `viewer_url`, `report_url`, `package_url`, `json_url`, `error_count`, `warning_count`, `inconsistency_count`. URL attributes are site-relative paths: prefix with `https://filings.xbrl.org`. The entity LEI and name come from the related `entity` resource.

xBRL-JSON (`json_url`): `{"documentInfo": {...}, "facts": {id: {"value", "decimals", "dimensions": {"concept", "entity", "period", "unit", ...extra axes}}}}`. Typical size 1 to 5 MB.

### Gotchas found

- **Values are full units.** Check: Inditex (LEI 549300TTCXZOGZM2EY83) `ifrs-full:Revenue` for the year to 31 Jan 2026 is 39,864,000,000 EUR in the JSON; the comparative year is 38,632,000,000 EUR, which is the EUR 38.6bn Inditex published for FY2024. No scaling needed.
- **Period ends are written as midnight of the next day** (`2026-02-01T00:00:00` means 31 Jan 2026). The pipeline converts to inclusive dates.
- **One filing carries two years** (current + comparative), so one download per entity gives two fiscal years.
- **Index `period_end` is not always right.** Example: an AEDAS Homes filing indexed under 2026-12-31 contains a report to 2026-03-31. The pipeline takes fiscal periods from the facts, never from the index, and ignores index period ends later than the run date.
- **Dual filers** appear under two countries with the same LEI (Shell: GB and NL). The pipeline keeps one filing per LEI and lists all countries in `countries_filed`.
- 286 index rows have no `json_url` (processing failed); 1,127 filings have validation errors. Errors are mostly calculation inconsistencies, so a filing with errors is still used when it is the only one for the latest period.
- `country` is where the report was filed, not HQ.

### Terms, robots, rate limits

- `https://filings.xbrl.org/robots.txt` returns 404: no crawl restrictions published.
- The about and API pages publish no licence text, no API key requirement and no stated rate limit. The API is described as public. The filings are regulated public disclosures. Treated as: free to access and analyse, attribute the source, link back to the filing. **Open question for Mo:** no explicit redistribution licence was found, so the public site should link to the filings and show derived figures rather than mirror the raw files.
- Our usage: shared client `chase.common.http`, at most one request start per second, descriptive User-Agent, on-disk cache (each file is fetched once), static index files instead of paging the API.

### Coverage of the index by country (period-end year, filings, 2026-11-16)

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

### Gaps, stated plainly

- **Germany: zero filings.** The entity table has records for Siemens AG, Volkswagen AG and BASF SE, but `/api/entities/{LEI}/filings` returns an empty list for each, and no filing in the index has `country=DE`. German issuers file ESEF reports with the Bundesanzeiger / Unternehmensregister, which this repository does not ingest. DAX/MDAX computed DPO cannot come from this source. Fallbacks for the lead agent: SEC 20-F data for the few German SEC filers, Wikidata revenue for sizing, or the Unternehmensregister ESEF packages (not attempted here: terms and access need their own check).
- **Ireland and Switzerland: zero filings.** Ireland has no ESEF feed here (CRH, for example, only has GB filings for 2021 and 2022 and now reports under US rules). Switzerland is outside ESEF.
- **UK: present and current.** Contrary to the expectation that UK coverage ended after Brexit, UKSEF filings continue (552 filings with 2025 period ends, 163 with 2026). The GB set includes many investment trusts and small caps.
- **Poland, Luxembourg, Belgium, Croatia, Hungary, Romania:** coverage stops or thins out after 2023 or 2024. Figures from those countries can be stale; check `fiscal_year_end`.
- **Banks and insurers:** flagged `is_financial`, DPO set to null (`not_applicable`). They usually tag no `Revenue`, so they fall below the size screen in this table; size them from another source.
- **Tagging choices limit DPO quality.** Many issuers tag only the broad `TradeAndOtherCurrentPayables`, which includes non-supplier payables and overstates DPO (flagged `trade_and_other_broad`, confidence 0.7). Companies reporting expenses by nature have no `CostOfSales`; a documented fallback denominator is used (flagged `by_nature_fallback`, confidence 0.7). Issuers that use extension elements for these lines get `missing_inputs`.
- **Not every entity was downloaded in this run.** Downloads are time-boxed and ordered by country priority. The exact covered counts per country are in `data/manifests/esef_xbrl.json` (`coverage_by_country`: selected vs downloaded). Re-running the module continues from the cache.

### What this run actually covered (2026-11-16, time-boxed to about 25 minutes of downloading)

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

### Selection rule used

One filing per LEI: the latest `period_end` between 2023-01-01 and the run date that has an xBRL-JSON; for the same period, the filing with fewest validation errors, then the most recently processed. Ukraine excluded.


---

# Detail: G. Wikidata

## Source: Wikidata (SPARQL)

Verified 2026-11-16 by the `scout-wikidata` subagent. Verdict: **reachable, usable, low-to-medium trust.**
Good for identifiers, aliases and parent/subsidiary links. Not good enough to publish revenue figures from.

| Item | Finding |
|---|---|
| Endpoint | `https://query.wikidata.org/sparql` (GET, `query=` + `format=json`). Verified live. |
| Licence | Structured data in the main and property namespaces is **CC0 1.0** (public domain dedication). No attribution required; we attribute anyway via `source_url`. |
| Auth | None. |
| User-Agent | Wikimedia's User-Agent policy asks for a descriptive UA with contact info; generic UAs can be blocked. We send `ChaseIndex research (contact: <CONTACT_EMAIL>)` from `chase.common.http`. |
| Timeout | Hard server-side limit of 60 s per query. |
| Rate limits | Per client (UA + IP): roughly 60 s of query processing time per 60 s window and a small number of parallel queries; excess returns HTTP 429 with `Retry-After`. We run strictly sequential queries, at least 2 s apart. |
| Freshness | Live graph, lags edits by seconds to minutes. Content freshness depends on volunteers: revenue years are often several years old. |

### Gotchas found while testing

1. **A timed-out query can come back as HTTP 200 with a truncated JSON body** (the server streams results and
   appends a Java timeout stack trace). The HTTP layer would cache that. `chase.sources.wikidata.sparql()` treats a
   JSON decode error as a timeout, refetches once without cache, then splits the query.
2. `GROUP BY` over all revenue value nodes (`psv:P2139`) times out. What works: filter on the simple value
   (`ps:P2139 >= X`) first, then join the value node for the unit, and split by **amount band**
   (about 20k statements per band finish in 30 to 45 s).
3. Detail lookups work well as `VALUES` batches of 200 QIDs over GET (100 for the edge queries).
   The module halves a batch automatically on timeout.
4. The label service (`SERVICE wikibase:label`) is slow on large result sets; we join `rdfs:label` with a
   language filter instead.
5. Revenue (P2139) is a multi-statement property: one statement per year, each with its own currency unit and
   `P585` (point in time) qualifier. Some statements have no date; a few have no currency (unit "1"). We take the
   most recent dated statement per item and keep amount, currency and year.
6. Tickers are normally a qualifier (`P249`) on the stock exchange statement (`P414`), not a direct claim.
7. Index membership (IBEX 35, DAX, FTSE 100...) is patchy: sometimes `P361` on the company, sometimes `P527`
   on the index item. Both are collected; neither is complete. Do not use it as the IBEX 35 constituent list.
8. `P127` (owned by) is noisy when inverted: it also returns brands, buildings, ships, sports clubs and minority
   stakes. `P355` and `P749` are cleaner. Table 2 keeps the relation so downstream can filter.
9. Only about 8,600 items carry a Companies House number (`P2622`), against roughly 6,000 to 7,000 UK payment
   practice reporters per period. Wikidata alone will map only a small share of UK reporting entities; name
   matching and Companies House PSC data stay necessary.

### How we use it

- Table 1 `data/interim/wikidata_companies.parquet`: candidate universe (latest revenue statement >= ~USD 3B).
- Table 2 `data/interim/wikidata_subsidiaries.parquet`: descendants of Table 1 companies, depth <= 3.
- Table 3 `data/interim/wikidata_uk_entities.parquet`: every item with a Companies House number, plus ancestors.
- Column definitions: `docs/data_dictionary_wikidata.md`. Run log: `data/manifests/wikidata.json`.

All rows carry `confidence = 0.6`: community-edited data. Revenue from Wikidata is a screening value only;
SEC/ESEF XBRL revenue should replace it wherever available.

### Fallback

If the endpoint is down: the module is cache-backed (`data/cache/http`), so a rerun rebuilds the tables offline
from the last successful fetch. A full outage on a cold cache means the universe falls back to SEC + ESEF
revenue facts only, with name-based UK roll-up.


---

# Detail: H2. Companies House bulk data

## Source: Companies House bulk snapshots (no API key)

Verified 2026-11-16. Used to roll UK payment-practice reporting entities up to parent groups without the
Companies House API. Code: `src/chase/sources/companies_house_bulk.py`. Tables:
`docs/data_dictionary_companies_house.md`. Download manifest (url, bytes, sha256, retrieved_at per file):
`data/manifests/companies_house_bulk.json`.

### Verdict

Both products are reachable, free, need no key or login, and robots.txt allows everything. Usable.
The only practical problem is download time: about 3.2 GB in 34 files, downloaded one at a time.

### 1. Free Company Data Product (basic company data)

| Item | Value |
|---|---|
| Page | https://download.companieshouse.gov.uk/en_output.html |
| File used | `BasicCompanyDataAsOneFile-2026-11-01.zip` (page says 471Mb; 494,554,856 bytes on disk) |
| Alternative | Same data in 7 parts: `BasicCompanyData-2026-11-01-part1_7.zip` ... `part7_7.zip` (50 to 70 Mb each) |
| Snapshot date | 2026-11-01 (page: "Last Updated: 01/11/2026"). Monthly, within 5 working days of month end. |
| Format | One CSV inside the zip, about 2.6 GB unzipped, UTF-8, quoted, 5,711,779 data rows. |
| Coverage | Live companies on the register only. Dissolved companies are not included. |
| Field list | https://resources.companieshouse.gov.uk/toolsToHelp/pdf/freeDataProductDataset.pdf |

Fields used: `CompanyName`, `CompanyNumber`, `RegAddress.PostTown`, `RegAddress.PostCode`, `RegAddress.Country`,
`CompanyCategory`, `CompanyStatus`, `CountryOfOrigin`, `IncorporationDate`, `SICCode.SicText_1..4`,
`PreviousName_1..10.CompanyName`.

Gotchas:
- Some header names carry a leading space (` CompanyNumber`, ` PreviousName_1.CompanyName`). The parser strips header names before mapping.
- SIC fields are already `code - text` strings.
- `IncorporationDate` is `DD/MM/YYYY`.
- `RegAddress.Country` is free text and empty for about 16% of rows. `CountryOfOrigin` is always filled.
- Company numbers are 8 characters: digits, or a prefix plus digits (`SC`, `NI`, `OC`, `SO`, `NC`, `FC`, `ZC`, ...).
- Status counts in this snapshot: Active 5,179,256; Active - Proposal to Strike off 417,325; Liquidation 107,871; the rest are small.

### 2. People with significant control (PSC) snapshot

| Item | Value |
|---|---|
| Page | https://download.companieshouse.gov.uk/en_pscdata.html |
| Files used | `psc-snapshot-2026-11-16_1of33.zip` ... `_33of33.zip` (80 to 82 Mb listed for parts 1 to 30, then 54, 31, 9 Mb; about 2.5 GB listed in total; parts 1 to 5 were 85 to 87 MB each on disk) |
| Alternative | One file: `persons-with-significant-control-snapshot-2026-11-16.zip` (no size listed on the page) |
| Snapshot date | 2026-11-16 (page: "Last Updated: 16/11/2026 08:28hrs"). Rebuilt every morning before 10am GMT with data up to the previous day. |
| Format | Each zip holds one `.txt` file of JSON lines, 500,000 lines per full part. |
| Field docs | Linked from the page: http://forum.aws.chdev.org/t/psc-streaming-api/529 |

IMPORTANT: the file names change every day. Yesterday's part names are gone once the new snapshot is published. A
download that is interrupted overnight cannot be resumed against the same names: the script re-reads the page, so it
would start a fresh set, and parts from two different days must not be mixed. Finish the download on the same day or
move the old parts away first.

Line shape: `{"company_number": "...", "data": {"kind": ..., "name": ..., "identification": {...},
"natures_of_control": [...], "notified_on": ..., "ceased_on": ..., "address": {...}, "etag": ..., "links": {...}}}`.

Kinds kept: `corporate-entity-person-with-significant-control` and `legal-person-person-with-significant-control`.
Everything else is dropped by a byte-string pre-filter before the JSON is parsed, then checked again on the parsed
`kind`. That covers individuals, super-secure PSCs, PSC statements, the beneficial-owner kinds used for overseas
entities, and the totals line. No natural-person record is parsed into a table, stored or output.

Gotchas:
- Parts are NOT ordered by company number. Part 1 alone spans `00001350` to `ZC000204`. All 33 parts are needed
  before any chain is trustworthy: with a part missing, a missing parent looks exactly like "no corporate PSC". The
  module therefore writes `*.partial.*` files, never the final file names, while any part is missing.
- About 5.5% of lines in part 1 are active corporate or legal-person records (27,661 of 500,000).
- `identification.registration_number` is free text: `2786492`, `02786492`, `SC 12345`, `HRB 6684`. About 86% of the
  kept records in part 1 normalise to something shaped like a UK company number. A foreign number can collide with a
  UK one (`12345` pads to `00012345`), so a number hit alone is never enough: the name must match too, or the
  registered country must read as UK.
- `identification.country_registered` and `place_registered` are free text with many spellings: `England`,
  `England & Wales`, `United Kingdom`, `Uk`, `Companies House Cardiff`, `Delaware`, `Not Specified/Other`.
- Ended control is marked with `ceased_on` (and `ceased: true` on some records). Those are skipped.
- The PSC regime only requires the first registrable relevant legal entity above a company. Chains therefore go one
  hop at a time, and they end at the UK border: a foreign PSC is the first foreign owner, not necessarily the global
  ultimate parent. Listed UK parents usually have no PSC at all.
- The basic file is as of 2026-11-01 and the PSC file as of 2026-11-15, so a company incorporated or dissolved in
  between can be in one and not the other.

### Licence and terms

- `https://download.companieshouse.gov.uk/robots.txt` (fetched 2026-11-16): `User-agent: *` / `Disallow:` (nothing disallowed).
- Neither download page carries a licence statement. Both say the snapshot "is provided free of charge and will not be supported".
- GOV.UK guidance "Companies House data products" (https://www.gov.uk/guidance/companies-house-data-products),
  section "Using Companies House data": "We impose no rules or requirements on how the information on the public
  register is used, and we're not responsible for your use of the company data. You are responsible for complying
  with any applicable data protection, copyright and other legislation and regulations." The page footer states
  Crown copyright and "All content is available under the Open Government Licence v3.0, except where otherwise stated".
- Reading: free to use and reuse. The brief expected an explicit Open Government Licence statement on the data
  itself. That was not found on the download pages. The OGL statement found is the general GOV.UK page footer, so
  attribute as "Contains public sector information from Companies House" and do not claim more than the above.
- Data protection still applies to the natural-person PSC records, which is why this project does not extract them.

### How it was downloaded

- Plain `httpx` streaming to disk, 1 MiB chunks, one file at a time, 1.5 s pause between files, User-Agent
  `ChaseIndex research (contact: <CONTACT_EMAIL>)` from `chase.common.http.USER_AGENT`.
- Resumable: a file whose size matches the server's `Content-Length` is skipped; a `.part` file is continued with an
  HTTP `Range` request; five retries with exponential backoff.
- Observed speed on 2026-11-16: 0.4 to 1.1 MB/s while other project downloads shared the line. Basic file: 538 s.
  PSC parts: 80 s each at first, then 200 to 230 s each.

### Run

```
.venv/bin/python -m chase.sources.companies_house_bulk                  # download what is missing, parse, walk chains
.venv/bin/python -m chase.sources.companies_house_bulk --download-only
.venv/bin/python -m chase.sources.companies_house_bulk --skip-download  # parse + walk from what is on disk
```

Parse and walk take well under a minute per PSC part plus about 30 s for the rest (6 worker processes).

### Status on 2026-11-16 11:38 CET (honest)

- Basic company data: downloaded and parsed in full (5,711,779 companies).
- PSC snapshot: 8 of 33 parts downloaded when the 45-minute budget ran out. Download speed fell to about 0.4 MB/s.
- Because parts are not ordered by company number, chains from 8 parts are not usable. Only
  `data/interim/ch_*.partial.*` files exist. The final `ch_psc_corporate.parquet`, `ch_basic_reporting.parquet` and
  `ch_parent_chains.parquet` are written only when all 33 parts are on disk.
- To finish: run `.venv/bin/python -m chase.sources.companies_house_bulk` on the same day (2026-11-16 file names).
  It skips the files already on disk, continues the rest, then parses and walks.
