# Supplier finance extractor A (deterministic, XBRL tags): notes for the eval

Generated 2026-11-16T16:02:49Z by `python -m chase.sources.supplier_finance`. All figures below are written by a script from `data/interim/sfa_extract_a.json`; nothing is typed by hand.

## What was checked
- 200 companies in `data/interim/top200.csv`.
- SEC: XBRL company facts per CIK (us-gaap and ifrs-full taxonomies), concept keys scanned for supplier-finance substrings.
- ESEF: the latest xBRL-JSON filing per LEI (same selection as `esef_xbrl.py`), concept names and dimension members scanned; non-numeric facts searched for key phrases (boolean signal only).
- Method: substring discovery (`SFA_NAME_RE`), role from name parts (`classify_concept`), latest fiscal-year-end selection (`select_latest_instant`).

## Coverage

| status | companies |
|---|---|
| not_tagged | 130 |
| tagged | 46 |
| no_structured_source | 21 |
| tagged_text_only | 3 |

| primary source | companies |
|---|---|
| esef | 47 |
| none | 21 |
| sec | 132 |

Sources checked: sec: 119, esef: 47, none: 21, sec|esef: 13.
ESEF filings checked: 60; with a text mention: 32 (of which the weak 'confirming'-only phrase: 3); with a numeric supplier-finance tag: 0.
SEC filers: 132; tagged with an amount: 46; not tagged: 86.

## Concepts that actually exist in the data

| concept | companies using it |
|---|---|
| `us-gaap:SupplierFinanceProgramObligationDecreaseSettlement` | 43 |
| `us-gaap:SupplierFinanceProgramObligationIncrease` | 41 |
| `us-gaap:SupplierFinanceProgramObligation` | 34 |
| `us-gaap:SupplierFinanceProgramObligationCurrent` | 21 |
| `us-gaap:SupplierFinanceProgramObligationPeriodIncreaseDecrease` | 6 |
| `ifrs-full:DisclosureOfInformationRelatingToSupplierFinanceArrangementsExplanatory` | 1 |
| `kerrygroupplc:DescriptionOfAccountingPolicyForSupplierFinanceArrangements` | 1 |
| `wmmorrison:DescriptionOfAccountingPolicyForSupplyChainFinancing` | 1 |

Not found anywhere in the top 200: `SupplierFinanceProgramObligationNoncurrent`, `SupplierFinanceProgramPaymentTimingPeriod`, any numeric `ifrs-full` supplier-finance concept (carrying amount, amount already paid to suppliers, payment due date ranges), any concept containing ReverseFactoring, Confirming or AffacturageInvers.
Factoring concepts seen but NOT counted (likely receivables-side): `casino:AdjustmentsForNonRecourseFactoringAndAssociatedTransactionCosts`, `johnsonmattheyplc:DescriptionOfAccountingPolicyForFactoringArrangements`.

## 8 example rows

| rank | company | source | status | period end | currency | amount | prior amount | concept |
|---|---|---|---|---|---|---|---|---|
| 3 | LKQ Corporation | sec | tagged | 2025-12-31 | USD | 481,000,000 | 416,000,000 | us-gaap:SupplierFinanceProgramObligation |
| 7 | GE Vernova Inc. | sec | tagged | 2025-12-31 | USD | 1,542,000,000 | 2,051,000,000 | us-gaap:SupplierFinanceProgramObligationCurrent |
| 13 | LyondellBasell | sec | tagged | 2025-12-31 | USD | 108,000,000 | 141,000,000 | us-gaap:SupplierFinanceProgramObligation |
| 14 | Eaton Corporation | sec | tagged | 2025-12-31 | USD | 543,000,000 | 398,000,000 | us-gaap:SupplierFinanceProgramObligation |
| 15 | Terex Corp | sec | tagged | 2025-12-31 | USD | 36,000,000 | 25,000,000 | us-gaap:SupplierFinanceProgramObligation |
| 21 | Saint-Gobain | esef | tagged_text_only | 2025-12-31 |  |  |  | ifrs-full:DisclosureOfInformationRelatingToSupplierFinanceArrangementsExplanatory |
| 1 | Alstom | esef | not_tagged | 2026-03-31 |  |  |  |  |
| 2 | Siemens Energy AG | none | no_structured_source |  |  |  |  |  |

## Runtime

5.2 seconds for 200 companies on a warm cache (no model calls, cost 0). Two ESEF files that were in the index but not yet cached (Anheuser-Busch InBev, Azelis Group) were fetched once through the shared client on the first run.

## Gotchas

1. **Not tagged is not "no programme".** No ESEF filer in the top 200 has a numeric supplier-finance tag, yet most of them describe a programme in a text block. ESEF requires detailed tags on the primary statements only; notes are block-tagged. So for IFRS filers this extractor can only give a text signal, and extractor B has to do the reading.
2. **SEC company facts carry numeric standard-taxonomy facts only.** Payment terms (`SupplierFinanceProgramPaymentTimingPeriod` is a duration type), text blocks and company extension concepts are not in the API. `payment_terms_with_programme` and `payment_terms_without_programme` are therefore null for every row.
3. **US filers below materiality do not tag.** A `not_tagged` SEC row is unknown, not a no.
4. **Total versus current.** Some filers use `SupplierFinanceProgramObligation`, others `...ObligationCurrent`; the extractor prefers the total and falls back to current (see `amount_concept`). Where a filer has several programmes tagged with dimensions, company facts only exposes the undimensioned value.
5. **Fiscal year end versus latest quarter.** `obligation_amount` is the latest fiscal-year-end value (an end date reported in a 10-K/20-F). A later quarter-end value, where tagged, is in `latest_interim_period_end` / `latest_interim_amount`. When comparing with extractor B, match on `period_end`.
6. **Restated comparatives.** For each date the most recently filed value wins, so a prior-year amount can differ from the originally reported one.
7. **`tagged_text_only`** (3 rows) means a text-block concept dedicated to supplier finance exists (one standard IFRS disclosure block, two company extension policy blocks). `programme_tagged` is true, but there is no amount; an accounting-policy block is strong but not conclusive evidence of an active programme.
8. **Text mentions are a cheap signal.** Some hits are only the sentence about adopting the IAS 7 / IFRS 7 amendments (for example with "no material impact"), and the word "confirming" alone is weak in non-Spanish text. `text_mention_phrase` says which phrase matched; the snippet is 200 characters of tag-stripped text from the fact named in `text_mention_fact_id`.
9. **xBRL-JSON has no labels**, so the label search asked for could only be done on concept names and dimension member names.
10. **Companies in both sources** (13): SEC is the primary source when it has tags; the ESEF text-mention fields are still filled and the note says where they come from.
11. `period_start` is null when only an instant (balance) fact is tagged; it is filled from the roll-forward period where one exists.
12. Multi-CIK / multi-LEI rows: every identifier is tried; the one with tagged data (latest period) is used.

Files: `src/chase/sources/supplier_finance.py`, `tests/test_supplier_finance.py` (9 tests pass), `data/interim/sfa_extract_a.json`, `data/interim/sfa_extract_a.csv`.
