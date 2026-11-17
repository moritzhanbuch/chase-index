# Supplier finance extraction: independent QA

Checked 2026-11-16 by the `qa` agent, which did not build either extractor.

## What was checked

- **Data:** `data/processed/supplier_finance.parquet`, 200 companies. It merges extractor A (XBRL tags) and extractor B (an LLM reading the report text).
- **Adjudication queue:** the 6 rows in `data/interim/sfa_adjudication_queue.json`.
- **Blind hand check:** a stratified random sample of 32 companies (`evals/gold/supplier_finance_sample.csv`):
  - 15 rows where only B found a programme
  - 12 rows where neither extractor found one
  - 5 rows where both found one
- **Method:**
  - QA opened each linked filing (10-K, 40-F exhibit or ESEF xBRL-JSON) and searched the full text for supplier finance, supply chain finance, reverse factoring, confirmed obligations, confirming, affacturage inversé, leverantörsfinansiering and similar terms. The search tolerates the broken letter spacing in PDF-converted UK filings.
  - QA then read the disclosure and recorded yes/no/unclear, the amount, the currency and the location.
  - All 32 labels were written before QA opened any extractor output.
- **Definitions:**
  - Amount = carrying amount of payables in the programme at fiscal year end (US GAAP ASU 2022-04 "confirmed obligations outstanding", IFRS IAS 7.44H).
  - Amounts "agree" when they are within 2%.

## Results (sample, n = 32)

| Stratum | n | QA says yes | QA no | QA unclear | Precision of "exists" | Missed programmes |
|---|---|---|---|---|---|---|
| Only B found one | 15 | 15 | 0 | 0 | 15/15 = 1.00 | n/a |
| Both found one | 5 | 5 | 0 | 0 | 5/5 = 1.00 | n/a |
| Neither found one | 12 | 0 | 11 | 1 | n/a | 0/11 (1 unclear) |
| **All** | **32** | **20** | **11** | **1** | **20/20 = 1.00** | **recall 20/20** |

The miss rate in "neither found" is 0 of 11. With n = 11, the 95% upper bound is still about 25%, so `no_evidence` must not be read as "no programme".

**Amount agreement** (16 rows where the filing states an amount):

| | Within 2% | Missing | Wrong |
|---|---|---|---|
| Provisional parquet (before QA) | 13/16 | 2 (Rolls-Royce, Casino) | 1 (Imperial, 10x too high) |
| Final parquet (after fixes) | 16/16 | 0 | 0 |

- In 4 more yes rows the filing gives no year-end total, and both extractors correctly left the amount null:
  - Cellnex: only a EUR 110m facility limit.
  - DS Smith: FY2024, before the IAS 7 amendment.
  - Airbus: only the EUR 0.9bn already paid to suppliers.
  - Ericsson.
- One provisional "agreement" was imprecise: Mondelez was USD 3.6bn instead of 3,562m. The rule fix below corrects it.

## Adjudication queue (6 rows)

| Company | Issue | Decision | Evidence |
|---|---|---|---|
| Kimberly-Clark | A 1.1bn vs B 1,057m | **USD 1,057m** (B) | 10-K Note 17 rollforward: "Confirmed obligations outstanding at the end of the year $ 1,057" |
| Arrow Electronics | A 1.3bn vs B 1,263m | **USD 1,263,089k** (B) | 10-K Note 5 rollforward |
| GE Aerospace | A tagged, B unclear | **yes, USD 1,247m** (A) | 10-K Note 11: "Supply chain finance programs 1,247 1,259". B only saw the policy paragraph |
| Prysmian | B says no | **no** | FY2024: "non ha evidenziato alcuna casistica significativa" (no significant cases found). FY2025 not checked |
| Pernod Ricard | B unclear | **no_evidence** | "Sans effet significatif" refers to the amendment and does not deny a programme. Only receivables factoring was found |
| Esprinet | B unclear | **unclear** | Mixed "Factoring / Confirming / Securitization" bank line, with no payables-side disclosure |

The decisions, with quotes and reasoning, are in `data/interim/sfa_adjudication.json`. The reconcile module already reads that file.

## Disagreements and causes

1. **A uses later 10-Q comparatives (systematic).** A keeps the most recently filed value per end date. As a result, a year-end amount often comes from a later 10-Q, where it is rounded ("$1.1 billion") or recast, not from the 10-K.
   - Across the full dataset this hit 10 rows: KMB, Arrow, Mondelez, Genuine Parts (3,130m vs 10-K 3,191m), P&G, Amcor, J&J, Pilgrim's, RPM and Tapestry.
   - In every case B's figure equalled the 10-K tag. QA verified this in SEC companyfacts for KMB, Arrow, Mondelez, Genuine Parts, P&G, J&J and Amcor.
2. **B merged digits in spaced text (Imperial).** In the PDF-converted iXBRL, the 2025 and 2024 cells "84" and "3" were read as 843. The cell split was confirmed in the iXBRL viewer.
3. **B found the programme but no amount (Rolls-Royce, Casino).** The amounts sit in a paragraph rather than a table, and in Rolls-Royce's case in spaced text.
4. **Liberty Latin America (QA unclear).** It has USD 306m of interest-bearing "vendor financing", where an intermediary pays vendors and the amount is booked as debt. The filing does not call this a supplier finance program, so the row stays `no_evidence`.
5. **Axalta:** B took the SCF programme only (USD 23m). The total including the virtual card programme is 29m. QA accepts 23m.

## Fixes

- **Rule fix** in `src/chase/sources/supplier_finance_reconcile.py`. The annual-report figure (B) is used when all of these hold:
  - the tag comes from a different SEC filing (accession) than the annual report B read
  - the periods match
  - the two values are within 5%

  This gives `amount_resolution = annual_report_value_tag_from_later_filing` and changes 8 rows. KMB and Arrow are also adjudicated.
- **Flag:** text-only amounts whose location says the source text is irregularly spaced get `amount_resolution = text_only_spacing_risk`.
- **Adjudications:** 10 entries covering the 6 queue rows, plus sample amount corrections for Imperial, Rolls-Royce and Casino. The data was not hand-edited.
- **Test added:** `tests/test_supplier_finance.py::test_reconcile_accession_helper`. `pytest -k supplier` passes 17/17.
- **Recommended, not done:** in extractor A, prefer annual-form entries for fiscal-year-end values (`select_latest_instant`). That is a cleaner fix at the source.

## Final counts (`--final`, 200 companies)

**Programme exists:**

| Value | Rows |
|---|---|
| yes | 87 |
| no_evidence | 89 |
| no_source | 22 |
| no | 1 |
| unclear | 1 |

**Amount resolution** (76 rows have an amount):

| Resolution | Rows |
|---|---|
| tags and text agree | 35 |
| text only, single reader | 27 |
| annual-report value over a later-filing tag | 8 |
| adjudicated | 6 |

## Caveats

- **Single reader:** 27 amounts and 38 "exists" calls rest on reader B alone (`text_only_single_reader`). The sample suggests the existence calls are reliable (15/15). Amounts are weaker: on the 11 B-only amount rows in the sample, 8 were right, 2 were missing and 1 was wrong before QA. Treat single-reader amounts as about 80% reliable.
- **"no_evidence" is not "no programme":** many issuers omit immaterial programmes.
- **Old periods:** Casino, Prysmian and DS Smith use FY2024 documents.
- **Different measures:** amounts are not comparable across companies. US rows report confirmed obligations. IFRS rows report the carrying amount in payables, or for Eni the nominal value classified as financial debt.
- **Missing provenance fields:** 21 rows, mostly the no-document rows, have no `source_url`, `retrieved_at` or `period_end`. These rows existed before this QA.
