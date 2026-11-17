# Data dictionary: Companies House bulk tables

Built by `python -m chase.sources.companies_house_bulk` (module `src/chase/sources/companies_house_bulk.py`).
Source details, licence and gotchas: `docs/sources/companies_house_bulk.md`.

All three tables are company-level. No natural-person PSC records are extracted or stored.

## `data/interim/ch_psc_corporate.parquet`

One row per ACTIVE corporate or legal-person PSC record, for all UK companies (not only reporting entities, because
parent chains pass through holding companies that file no payment-practice report). "Active" means the record has
no `ceased_on` date and no `ceased: true` flag.

| Column | Type | Meaning |
|---|---|---|
| `company_number` | string | Companies House number of the controlled company, 8 chars, zero-padded. |
| `psc_name` | string | Name of the controlling entity as filed. |
| `psc_kind` | string | `corporate-entity-person-with-significant-control` or `legal-person-person-with-significant-control`. |
| `psc_registration_number` | string, nullable | `identification.registration_number` exactly as filed (free text). |
| `psc_registration_number_norm` | string, nullable | Same, normalised to the 8-char Companies House form when it looks like a UK number (`2065` -> `00002065`, `SC 12345` -> `SC012345`). Null otherwise. Looking like a UK number is not proof that it is one. |
| `psc_country_registered` | string, nullable | `identification.country_registered`, free text as filed. |
| `psc_place_registered` | string, nullable | `identification.place_registered`, free text as filed (often the register name). |
| `psc_legal_form` | string, nullable | `identification.legal_form`. |
| `psc_legal_authority` | string, nullable | `identification.legal_authority` (governing law). |
| `natures_of_control` | string | Pipe-joined control codes, e.g. `ownership-of-shares-75-to-100-percent\|voting-rights-75-to-100-percent`. |
| `notified_on` | string (ISO date) | Date the PSC was notified. |

## `data/interim/ch_basic_reporting.parquet`

Basic register data for (a) every payment-practice reporting entity found in the live-company snapshot and (b) every
UK company that appears in any parent chain.

| Column | Type | Meaning |
|---|---|---|
| `company_number` | string | Companies House number, 8 chars. |
| `company_name` | string | Current registered name. |
| `status` | string | `CompanyStatus` (Active, Liquidation, ...). Dissolved companies are not in the snapshot. |
| `category` | string | `CompanyCategory` (Private Limited Company, Public Limited Company, LLP, ...). |
| `post_town` | string, nullable | Registered office post town. |
| `postcode` | string, nullable | Registered office postcode. |
| `country` | string, nullable | Registered office country as filed. |
| `country_of_origin` | string, nullable | `CountryOfOrigin` (United Kingdom for UK-incorporated). |
| `sic_codes` | string, nullable | Up to 4 SIC 2007 codes, pipe-joined, each as `code - text`. |
| `incorporation_date` | string | As in the source, `DD/MM/YYYY`. |
| `previous_names` | string | Up to 10 previous names, pipe-joined. Empty string if none. |
| `is_reporting_entity` | bool | True if the company files payment-practice reports. |
| `source_url`, `source_type`, `retrieved_at`, `snapshot_file` | string | Provenance: download page, `companies_house_basic_bulk`, download timestamp (UTC), zip file name. |

## `data/interim/ch_parent_chains.parquet` (+ `.csv`)

One row per payment-practice reporting entity (every distinct `company_number` in the UK export).

| Column | Type | Meaning |
|---|---|---|
| `company_number` | string | Reporting entity. |
| `company_name` | string, nullable | Current name from the basic snapshot. Null if the entity is not in the live snapshot (dissolved or converted). |
| `chain` | string (JSON) | List of parents from the immediate parent upward, excluding the entity itself. Each element: `name`, `company_number` (null if not a resolved UK company), `country` (free text as registered, or `United Kingdom` for resolved UK hops), `country_iso2` (guess, nullable), `match` (how the hop was resolved, see below). |
| `chain_length` | int | Number of elements in `chain`. 0 means no active corporate PSC on the entity itself. |
| `ultimate_parent_name` | string | Last element of the chain. If the chain is empty, the entity itself. |
| `ultimate_parent_company_number` | string, nullable | Set only when the ultimate parent is a resolved UK company. |
| `ultimate_parent_country` | string, nullable | Free text as registered. |
| `ultimate_parent_country_iso2` | string, nullable | ISO 3166-1 alpha-2 guess from an exact-match lookup of the free text. Null when not unambiguous. |
| `top_uk_company_number`, `top_uk_company_name` | string | Highest resolved UK company in the chain (the entity itself if no UK parent was resolved). Use this as the UK group key. |
| `stop_reason` | string | Why the walk ended, see below. |
| `ambiguous` | bool | True if any company on the path had more than one distinct active corporate PSC. |
| `confidence` | float | 0.9: single unambiguous chain, every hop matched on number and name. 0.8: unambiguous, but at least one hop matched on number only (name differs, country reads as UK). 0.7: ambiguous, or at least one hop matched on name only. |
| `in_companies_house_live_data` | bool | Whether the reporting entity is in the basic (live companies) snapshot. |
| `psc_parts_missing` | int | Number of PSC snapshot parts that were not on disk when the chain was built. Must be 0 for a complete result. |
| `source_url` | string | PSC snapshot page. |
| `source_type` | string | `companies_house_psc_bulk`. |
| `retrieved_at` | string | UTC timestamp of the last PSC part download. |
| `snapshot_file_date` | string | Date in the PSC snapshot file names. |
| `extraction_method` | string | `psc_chain_walk`. |

### `match` values (per hop)

| Value | Rule |
|---|---|
| `number_and_name` | Normalised registration number is a live UK company and the normalised PSC name equals its current or a previous name. |
| `number_only` | Number is a live UK company, name differs, registered country/place reads as UK. |
| `name_only` | No usable number. Normalised name equals exactly one live UK-incorporated company, and the country reads as UK or is blank. |
| `foreign` | Country/place text maps to a non-UK country. Terminal. |
| `foreign_unmapped` | There is country/place text, it is not in the ISO lookup, and no UK company matched. Treated as foreign. Terminal. |
| `unresolved` | Reads as UK or blank, but no live company found (dissolved, non-Companies-House body, typo). Terminal. |

### `stop_reason` values

| Value | Meaning |
|---|---|
| `no_corporate_psc` | The top company has no active corporate PSC. Typical for listed parents, companies controlled by individuals, or companies with a "no PSC" statement. |
| `foreign_parent` | The next PSC is registered outside the UK. The PSC regime stops at the border, so this is the first foreign owner, not necessarily the global ultimate parent. |
| `unresolved_uk_psc` | The next PSC reads as UK but could not be matched to a live company. |
| `unresolved_psc` | The next PSC has no country or place text and could not be matched to a live UK company. Often a foreign parent filed without a country (seen in the data: names ending Inc., A/S, AG). Country is null. |
| `legal_person_psc` | The next PSC is a legal person (government body, corporation sole, etc.) that is not a registered company. |
| `cycle` | The next hop would revisit a company already on the path. |
| `max_hops` | 10 hops reached. |

The three extra stop reasons (`unresolved_uk_psc`, `unresolved_psc`, `legal_person_psc`) and the two extra confidence inputs go beyond the
original four-value brief so that no case is silently forced into the wrong bucket.
