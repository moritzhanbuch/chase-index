# Spain PMP extraction eval (IBEX 35, fiscal year 2025)

Checked by `qa` on 2026-11-16. `qa` built neither extractor. Inputs: `data/interim/es_extract_a.json` (A, deterministic code), `data/interim/es_extract_b.json` (B, LLM reader), `data/interim/es_reconcile.csv`, `data/interim/es_adjudication_queue.json`. Output of this check: `data/interim/es_adjudication.json`.

## 1. Headline numbers

| Metric | Result |
|---|---|
| Coverage | **32 of 35** IBEX 35 companies have a statutory PMP |
| A vs B agreement on PMP | **31 of 32** (96.9%) |
| A vs B agreement on all six numeric fields | **170 of 181** fields where at least one extractor found a value (93.9%). Another 29 fields are null in both. 210 fields compared in total |
| Companies with zero conflicts | 31 of 35 |
| Fields sent to adjudication | **11** fields in 4 companies (6 disagreements, 5 found only by B) |
| Adjudication outcome | **B right on 11 of 11.** A wrong on 6 (all Acerinox), A missing 5 |
| Hand-check, extractor A | **10 of 10 companies, 40 of 40 fields** |
| Hand-check, extractor B | **10 of 10 companies, 40 of 40 fields** |
| Paid API spend | USD 0 |

Why 3 companies have no PMP:
- **FER** (Ferrovial SE, Dutch issuer) and **MTS** (ArcelorMittal S.A., Luxembourg issuer): non-Spanish parents, no Ley 15/2010 note in the group filing.
- **SAB** (Banco de Sabadell): the note text in the tagged filing stops at the sentence that introduces the table. The table itself is not in the tagged text. Needs the PDF or the IR page.

Agreement numbers are computed from `es_reconcile.csv` as written at 11:57. See section 7: extractor A was patched and rerun one minute later, so the current `es_extract_a.json` no longer matches that file for Acerinox.

## 2. Method

1. Two extractors read the same source text independently: A is regex and table parsing, B is an LLM reading the note.
2. Field by field comparison. Agree within 0.5 means accept.
3. Any disagreement, or a value found by only one extractor, goes to a third reader (`qa`) who reads the source and records value, reasoning and a verbatim quote. Nothing is picked silently.
4. `qa` also hand-checks 10 random companies (seed 20261116) by reading the source first, writing down the values, then comparing.
5. Values that look wrong but are printed that way in the source are kept as printed and flagged, never corrected.

## 3. Adjudication log

Full records with quotes: `data/interim/es_adjudication.json`.

| Ticker | Field | A | B | Final | Winner | Why |
|---|---|---|---|---|---|---|
| ACX | pmp_days | 60 | 63 | **63** | B | The note has two tables. The statutory one covers all suppliers (national and foreign) of the Spanish group companies: 63. A took the extra "Solo nacionales" table |
| ACX | ratio_paid_days | 61 | 65 | **65** | B | Same cause |
| ACX | ratio_pending_days | 49 | 44 | **44** | B | Same cause |
| ACX | prior_year_pmp_days | 64 | 67 | **67** | B | Same cause |
| ACX | pct paid within legal max, by value | 49 | 41 | **41** | B | Row labels are swapped in the source. 512,492 / 1,257,041 = 40.8%, so the 41% printed under "número total de facturas" is the value share. 2024 confirms: 467,243 / 1,108,598 = 42.1%, printed 42% |
| ACX | pct paid within legal max, by number | 41 | 49 | **49** | B | By elimination from the row above. The total invoice count is not printed, so it cannot be recomputed. Confidence 0.8 |
| AENA | pct by value | null | 99.5 | **99.5** | B | Separate table with columns "Miles de euros, %, Número de facturas, %". A did not parse this layout |
| AENA | pct by number | null | 98.8 | **98.8** | B | Same table |
| AMS | pct by value | null | 86 | **86** | B | Row "Menor o igual de 45 días": 1,308.3 of 1,529.0 million. Amadeus splits at 45 days, not 60 |
| AMS | pct by number | null | 77 | **77** | B | Row "Menor o igual de 45 días": 20,404 of 26,380 invoices |
| REP | pct by number | null | 95 | **95** | B | Footnote (5): "Representa un 95% (97% en 2024) sobre el total de las facturas de proveedores" |

Sanity flags raised by B (both confirmed as printed in the source, values kept):

| Ticker | Printed | Recomputed from printed totals | Verdict |
|---|---|---|---|
| COL | PMP 38, paid ratio 24, pending ratio 37 (2024: 38 / 38 / 30) | (24 x 118,316 + 37 x 9,180) / 127,496 = 24.9 days | Source inconsistency. The paid ratio of 24 looks like the typo. Keep 38, flag the row |
| SLR | PMP 35, paid ratio 29, pending ratio 26 (2024: 28 / 29 / 26) | (29 x 6,814 + 26 x 2,933) / 9,747 = 28.1 days | Source inconsistency. Keep 35, flag the row, low confidence |

Scope for the six companies where B found no explicit wording: **all six stay "unknown"** (ELE, ENG, MRL, RED, ROVI, SLR). I searched every PMP mention in each raw document for wording such as "sociedades españolas" or "en España" and found none. A had labelled ENG and ROVI `consolidated_spanish_entities` from the word "Grupo" alone. That is an inference, not something the source says, so B's "unknown" stands.

## 4. Hand-check (10 random companies)

Sample: `random.Random(20261116).sample(sorted(tickers_with_pmp), 10)`. Fields: PMP, paid ratio, pending ratio, prior-year PMP. Values read from the snippet, then confirmed against the raw document (table rows in the xBRL-JSON, or the IR page HTML for BBVA).

| Ticker | PMP | Paid ratio | Pending ratio | Prior-year PMP | A | B |
|---|---|---|---|---|---|---|
| FDR | 50.29 | 52.72 | 29.40 | 50.52 | 4/4 | 4/4 |
| TEF | 48 | 49 | 34 | 51 | 4/4 | 4/4 |
| BBVA | 26 | not published | not published | not published | 4/4 | 4/4 |
| MAP | 6.6 | 6.1 | 22.9 | 5.8 | 4/4 | 4/4 |
| ENG | 23 | not published | not published | 20 | 4/4 | 4/4 |
| COL | 38 | 24 | 37 | 38 | 4/4 | 4/4 |
| IBE | 14 | 14 | 27 | 14 | 4/4 | 4/4 |
| SCYR | 25 | 23 | 40 | 30 | 4/4 | 4/4 |
| ROVI | 46 | 48 | 28 | 47 | 4/4 | 4/4 |
| ITX | 37.07 | 37.83 | 29.71 | 37.51 | 4/4 | 4/4 |

Result: A 40/40, B 40/40. Of the 40 fields, 35 are printed values and 5 are correct nulls (the source does not publish them). The sample did not include any of the four companies in the adjudication queue, so this 100% does not cover the Acerinox error. Counting it, A's PMP was right for 31 of 32 companies on its first pass and B's for 32 of 32.

## 5. Cost and time per document (approximate)

| Extractor | Wall clock | Per document | Model cost |
|---|---|---|---|
| A, deterministic code | 1.62 s for 35 documents (`es_extract_a_meta.json`) | about 0.05 s | USD 0 |
| B, Claude subagent on a subscription | about 5 minutes for 35 documents | about 9 s, about 3.7k tokens (about 130k tokens total) | No paid API spend |

B's figures are estimates from the session, not metered.

## 6. Known limits

- The source is ESEF xBRL-JSON text, not PDF. Locations are fact ids and character offsets, not page numbers.
- The consolidated table covers the group's Spanish entities, not global payment behaviour. For six companies the scope is not stated at all (section 3).
- SAN and BBVA are parent-only figures from IR pages. No ratios, no prior year for BBVA.
- ELE and SLR text has letter-spacing artefacts ("2 1 .0 91" for 21,091). SLR's year header is damaged ("02 5 202 4"), the first column is read as 2025, and its invoice-count percentage is cut off in the fact.
- AMS measures invoices against 45 days, others against 60. The percentage fields are not strictly comparable across companies.
- COL and SLR print a PMP that does not follow from their own ratios. Reported as printed.
- The hand-check sample is 10 of 32. It confirms transcription accuracy, not that the companies' own figures are right.

## 7. Failures and fixes

| # | Failure | Status |
|---|---|---|
| 1 | A picked Acerinox's "Solo nacionales" table (PMP 60) instead of the statutory all-suppliers table (PMP 63) | Adjudicated to 63. A was patched and rerun at 11:58, after the 11:57 reconcile, and now returns 63. **Open:** `es_reconcile.csv` and the queue are stale against the current A output and should be regenerated. The agreement numbers above describe the first pass, which is the honest independent measure. A fix made after seeing B's answer is not independent agreement |
| 2 | A trusts Acerinox's swapped percentage labels (still 49 by value, 41 by number in the current output) | Adjudicated to 41 / 49. **Open in A:** add an arithmetic check (amount paid within the limit / total payments made) before assigning the two percentages |
| 3 | A misses percentages in column-layout tables (AENA, AMS) and in a footnote (REP by number) | Adjudicated values from B. Open in A, low priority: use the adjudicated values |
| 4 | A labels ENG and ROVI `consolidated_spanish_entities` from the word "Grupo" alone. A also says "unknown" for 16 companies where B found explicit wording | Final scope for ENG and ROVI is "unknown". Use B's scope plus the adjudication file downstream, not A's |
| 5 | COL and SLR: printed PMP is outside the range of the printed ratios | Not an extraction error. Keep as printed, carry a `pmp_outside_ratios` style flag and lower confidence into the final table, and do not show these ratios publicly without the flag |
| 6 | SAB: table not in the tagged text | Not fixed. Needs the PDF annual report or the IR page |
