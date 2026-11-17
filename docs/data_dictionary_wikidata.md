# Data dictionary: Wikidata interim tables

Built by `python -m chase.sources.wikidata`. Source: Wikidata SPARQL endpoint, licence CC0 1.0.
These are **interim** tables (raw material for the universe and for UK group roll-up), not final data.
All three share the provenance columns at the bottom. Multi-valued fields are pipe-separated (`|`) strings.
Missing values are null: nothing is imputed.

## Table 1: `data/interim/wikidata_companies.parquet` (+ `.csv`)

One row per Wikidata item whose **most recent** total revenue statement (P2139) converts to >= ~USD 3B and
that is not typed as an obvious non-company (see `data/interim/wikidata_excluded_non_companies.csv`).

| Column | Type | Meaning |
|---|---|---|
| `qid` | str | Wikidata item id (key). |
| `label_en` | str | English label, falling back to the language-neutral `mul` label (Walmart, Dell and ~120 others only have `mul`). |
| `label_mul`, `label_de`, `label_es`, `label_fr` | str | Label per language, no fallback. |
| `aliases_en` | str | Up to 10 English (or `mul`) aliases ("also known as"). |
| `short_name` | str | P1813 short name(s), up to 5, any language. |
| `country_iso2`, `country_label`, `country_qid` | str | First P17 (country) value and its ISO 3166-1 alpha-2 code (P297). |
| `countries_n` | int | Number of distinct P17 values (>1 means the first one was picked arbitrarily). |
| `hq_city`, `hq_city_qid` | str | First P159 (headquarters location) value. |
| `hq_country_iso2`, `hq_country_label` | str | Country (P17) of that headquarters location. Prefer this over `country_iso2` when both exist. |
| `industries` | str | P452 industry labels. |
| `instance_of`, `instance_of_qids` | str | P31 labels and QIDs. |
| `company_like_type` | bool | At least one P31 label is in the company whitelist (`COMPANY_LIKE` in the module). False for 214 rows: mostly US nonprofits, hospital systems and items typed only as "organization". Filter on this for a strict company universe. |
| `employees`, `employees_year` | Int64 | P1128 value from the most recent dated statement (else undated best rank); year from its P585 qualifier. |
| `revenue_amount` | float | Original amount of the most recent P2139 statement, in `revenue_currency`. |
| `revenue_currency`, `revenue_currency_qid` | str | ISO 4217 code (P498 of the unit item) and unit QID. |
| `revenue_year`, `revenue_date` | Int64 / str | Year and raw value of the statement's P585 (point in time) qualifier. Null if the statement is undated. **Check freshness before use.** |
| `revenue_usd` | float | `revenue_amount` x rough rate from `config/fx_rates.yaml`. Screening value only: one present-day rate applied to all years. |
| `revenue_statements_n` | int | Number of non-deprecated revenue statements above the raw floor (9e8) on the item. |
| `isin` | str | P946. |
| `lei` | str | P1278. |
| `sec_cik` | str | P5531, zero-padded to 10 digits. |
| `ticker`, `stock_exchange` | str | P249 qualifier and P414 value of listings without an end date (all listings if none is current). |
| `listings` | str | All `exchange:ticker` pairs, including ended ones. |
| `uk_company_number` | str | P2622, normalised to 8 characters. |
| `website` | str | First P856. |
| `parent_qid`, `parent_label` | str | P749 parent organisation(s). |
| `owned_by_qid`, `owned_by_label` | str | P127 owner(s). Includes minority and state shareholders. |
| `legal_form` | str | P1454 label(s). |
| `inception` | str | Earliest P571 (ISO datetime string). |
| `dissolved_date`, `is_dissolved` | str / bool | P576. Dissolved or merged entities are kept and flagged, not dropped. |
| `part_of` | str | All P361 labels. |
| `stock_indices` | str | Stock market indices the item is linked to (P361 on the company or P527 on the index, where the target is an instance of "stock market index"). Incomplete. |

Selection rule: non-deprecated P2139 statements with raw amount >= 9e8 are fetched (9e8 is the lowest raw
amount that can reach USD 3B in any convertible currency). Per item, the statement with the latest P585 year wins
(undated statements only if there is no dated one; preferred rank, then larger amount, break ties). Items whose
latest statement has a unit without an ISO 4217 code or without a rate in `config/fx_rates.yaml` are dropped
and counted in the manifest (`unconvertible_latest`).

Known consequence: a company whose latest statement fell **below** the raw floor (for example a collapse in
revenue) is represented by its latest statement above the floor, so its "latest" year can be older than what
Wikidata actually holds.

## Table 2: `data/interim/wikidata_subsidiaries.parquet` (+ `.csv`)

One row per (Table 1 company, descendant) pair, depth 1 to 3.

| Column | Type | Meaning |
|---|---|---|
| `parent_qid`, `parent_label` | str | The Table 1 company (group root for this row). |
| `child_qid`, `child_label` | str | Descendant item; label in en, falling back to de, fr, es. |
| `child_aliases_en` | str | Up to 10 English aliases. |
| `child_country_iso2` | str | ISO2 of the child's first P17. |
| `child_uk_company_number` | str | P2622, normalised to 8 characters. |
| `child_instance_of` | str | Up to 5 P31 labels. Use it to drop brands, buildings, sports clubs. |
| `relation` | str | Property of the last edge on the path: `P355` (parent has subsidiary child), `P749_inverse` (child names parent organisation), `P127_inverse` (child is "owned by"). Several if more than one applies. |
| `depth` | int | Shortest distance from the Table 1 company (1 = direct). |
| `via_parent_qid`, `via_parent_label` | str | Immediate parent on that path (equals `parent_qid` at depth 1). |
| `child_in_table1` | bool | The child is itself a Table 1 company (large subsidiary, or a cross-holding). |

Filter applied at query time: an "owned by" child is kept only if it has at least one organisation-like
property (industry, HQ, legal form, Companies House number, LEI, ISIN, listing, revenue, employees, parent or
subsidiary). Without it, owned-by returns patents, stations and buildings (Samsung Electronics: 7,400 items).

Caveats: `P127_inverse` still includes minority stakes, so a child can appear under several roots (BlackRock
alone has 4,502 rows because it is listed as a shareholder of many listed companies). A state or holding company in Table 1 can pull in a very large tree. Treat depth 1 `P355`/`P749_inverse`
rows as the high-precision set.

## Table 3: `data/interim/wikidata_uk_entities.parquet` (+ `.csv`)

One row per (item, Companies House number) for every Wikidata item with P2622.

| Column | Type | Meaning |
|---|---|---|
| `qid`, `label` | str | Item and English label. |
| `company_number` | str | Normalised: upper case, separators removed, zero-padded to 8 characters (`SC`, `NI`, `OC` etc. prefixes kept). |
| `company_number_raw` | str | Value as stored in Wikidata. |
| `parent_qid`, `parent_label` | str | Direct parents via P749 (or stated on the parent via P355). |
| `owned_by_qid`, `owned_by_label` | str | Direct owners via P127. |
| `ultimate_ancestor_qid`, `ultimate_ancestor_label` | str | End of the chain when following the preferred parent up to 5 levels (P749/P355 first; P127 only when there is exactly one owner, because P127 lists every shareholder; a Table 1 parent preferred; then lowest QID). Null if the item has no parent. Can be a person, a state or a fund. |
| `ancestor_path` | str | The chain walked, starting at the item. |
| `ancestor_depth` | int | Length of that chain (0 = no parent found). |
| `parent_candidates_n` | int | Number of distinct direct parents/owners. >1 means the chain choice was ambiguous. |
| `universe_ancestor_qid`, `universe_ancestor_label` | str | Nearest ancestor (or the item itself) that is in Table 1, searching all parents breadth-first up to 5 levels. This is the column to use for group roll-up. |
| `universe_ancestor_depth` | Int64 | 0 = the item itself is in Table 1. |

## Provenance columns (all tables)

| Column | Value |
|---|---|
| `source_url` | `https://www.wikidata.org/wiki/{qid}` (child QID in Table 2). |
| `source_type` | `wikidata` |
| `retrieved_at` | ISO timestamp of the build. Per-query fetch times are in `data/manifests/wikidata.json` and `data/manifests/http_log.jsonl`. |
| `extraction_method` | `sparql` |
| `confidence` | `0.6` flat: community-edited data, stale years possible. |

Wikidata has no `period_start`/`period_end`: the only period information is `revenue_year` / `employees_year`.
