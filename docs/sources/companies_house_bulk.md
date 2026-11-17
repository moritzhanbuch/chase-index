# Source: Companies House bulk snapshots (no API key)

Verified 2026-11-16. Used to roll UK payment-practice reporting entities up to parent groups without the
Companies House API. Code: `src/chase/sources/companies_house_bulk.py`. Tables:
`docs/data_dictionary_companies_house.md`. Download manifest (url, bytes, sha256, retrieved_at per file):
`data/manifests/companies_house_bulk.json`.

## Verdict

Both products are reachable, free, need no key or login, and robots.txt allows everything. Usable.
The only practical problem is download time: about 3.2 GB in 34 files, downloaded one at a time.

## 1. Free Company Data Product (basic company data)

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

## 2. People with significant control (PSC) snapshot

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

## Licence and terms

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

## How it was downloaded

- Plain `httpx` streaming to disk, 1 MiB chunks, one file at a time, 1.5 s pause between files, User-Agent
  `ChaseIndex research (contact: <CONTACT_EMAIL>)` from `chase.common.http.USER_AGENT`.
- Resumable: a file whose size matches the server's `Content-Length` is skipped; a `.part` file is continued with an
  HTTP `Range` request; five retries with exponential backoff.
- Observed speed on 2026-11-16: 0.4 to 1.1 MB/s while other project downloads shared the line. Basic file: 538 s.
  PSC parts: 80 s each at first, then 200 to 230 s each.

## Run

```
.venv/bin/python -m chase.sources.companies_house_bulk                  # download what is missing, parse, walk chains
.venv/bin/python -m chase.sources.companies_house_bulk --download-only
.venv/bin/python -m chase.sources.companies_house_bulk --skip-download  # parse + walk from what is on disk
```

Parse and walk take well under a minute per PSC part plus about 30 s for the rest (6 worker processes).

## Status on 2026-11-16 12:20 CET

- Complete. All 34 files downloaded (3,160,127,722 bytes; retrieved 10:13 to 11:19 UTC), about 66 minutes in total
  because speed fell to roughly 0.4 MB/s for most PSC parts. That was over the 45-minute budget.
- PSC snapshot: about 16.2 million lines in 33 parts; 849,969 active corporate or legal-person records kept
  (838,987 corporate entity, 10,982 legal person) across 791,133 companies.
- Reporting entities walked: 10,309. Final tables: `data/interim/ch_psc_corporate.parquet`,
  `ch_basic_reporting.parquet` (18,091 rows), `ch_parent_chains.parquet` and `.csv`.
- Results (10,309 entities): 82.2% have at least one corporate parent; stop reasons: no_corporate_psc 62.4%,
  foreign_parent 27.9%, unresolved_psc 3.7%, unresolved_uk_psc 2.4%, max_hops 1.8%, legal_person_psc 1.4%,
  cycle 0.4%. 5.4% of reporting entities are not in the live-company snapshot (dissolved or converted).
- Known limits seen in the output: a foreign parent filed without a country ends as `unresolved_psc`
  (Amazon UK Services Ltd. -> "Amazon.Com, Inc."); a UK top company with a foreign owner that files no PSC ends as
  `no_corporate_psc` (Jaguar Land Rover stops at Jaguar Land Rover Automotive plc); 189 chains hit the 10-hop cap.
