# DACH slice: computed DPO from annual reports

Independent project by Moritz Hanbuch.

**Verdict.** 23 of 29 target companies now have a computed DPO (proxy) read from their latest consolidated annual report, with trade payables to suppliers (not total payables). Two independent extractors agreed on 59 of 80 DPO inputs both of them found (74%); a separate QA agent decided the other 66 queued values from the source pages. A hand-check of 10 randomly drawn companies matched on 20 of 20 values (5 of the 10 were not fully blind, see section 5). Three reports could not be retrieved without working around a block, so those companies have no figure.

Everything here is a **balance-sheet proxy**, not reported days to pay. Germany and Switzerland have no statutory payment-practice reporting comparable to the UK regime. Where a UK statutory figure exists for a group, it still outranks this proxy.

## 1. Who is in the slice

- **Bavaria:** DAX 40 and MDAX constituents (German Wikipedia index tables, revisions in `data/interim/dach_index_members.csv`, composition as of 7 November 2026 per the tables' boerse.de source). 24 of 90 members are headquartered in Bavaria: Wikidata headquarters (P159) located in Bavaria (P131*), plus the DAX table's state column. Banks and insurers excluded: Allianz, Münchener Rück.
- **Edge cases, kept and labelled:** Fresenius Medical Care (registered seat Hof, run from Bad Homburg), CTS Eventim (registered seat Munich, run from Bremen), Knorr-Bremse (Wikidata lists Berlin and Munich). Auto1 Group lists Munich and Berlin in the MDAX table but Wikidata gives Berlin only, so it is out.
- **Switzerland and Austria:** the largest listed industrials (manufacturing, construction, automotive) already in the universe. ABB was in the universe with a Swedish HQ; corrected to Zurich (`config/overrides.yaml`). Garmin and Amrize are left out because their DPO already comes from US 10-K XBRL. Austria has one company: voestalpine, Andritz and Wienerberger are not in the universe (a recall gap of the universe build, reported here, not fixed), and OMV is energy, not an industrial.
- **Added to the universe:** Bavarian index members that were missing, even below the USD 4bn threshold, flagged `dach_slice_index_member` (`config/dach_slice.yaml`, with sector and operational HQ per company): 11 companies.

## 2. Coverage

- Reports found and read: **26 of 29**. All are the FY2025 reports (September year ends: FY to 2025-09-30; their FY2026 reports were not yet published on 17 November 2026).
- Not retrieved, on purpose: Fresenius Medical Care (site dropped every connection); Renk Group (server refused our declared client (403); not worked around); Schaeffler AG (server refused our declared client (403); not worked around).
- Source type: annual-report PDF from the company's own IR page for every company. No German company is in the filings.xbrl.org repository, and only DSM-Firmenich offered an ESEF package on its IR page; Strabag's ESEF facts were used by extractor A alongside the PDF.
- DPO computed: **23** companies (18 on cost of sales, 5 on cost of materials for nature-of-expense reporters, confidence 0.7 as for the existing by-nature rows, kept out of sector medians).
- No DPO: Nemetschek SE (cost base under 20% of revenue: payables/cost would read as slow payment for a software or marketplace business); Scout24 (no cost line); Siemens Energy (no trade-payables figure can be isolated).

| Company | Slice | FY end | Trade payables | Cost (basis) | DPO (proxy) | Prior-year DPO | How decided |
|---|---|---|---|---|---|---|---|
| Schindler Elevator | CH/AT | 2025-12-31 | CHF 1,020m | CHF 2,746m (cost of materials) | 136 days | 132 days | QA |
| Holcim | CH/AT | 2025-12-31 | CHF 3,190m | CHF 9,066m (cost of sales) | 128 days | 175 days | QA |
| Krones AG | Bavaria | 2025-12-31 | EUR 868m | EUR 2,713m (cost of materials) | 117 days | 112 days | A=B, QA |
| Puma SE | Bavaria | 2025-12-31 | EUR 1,271m | EUR 4,016m (cost of sales) | 116 days | 157 days | A=B |
| Hensoldt AG | Bavaria | 2025-12-31 | EUR 591m | EUR 1,930m (cost of sales) | 112 days | 115 days | A=B |
| Knorr-Bremse AG | Bavaria | 2025-12-31 | EUR 1,092m | EUR 3,579m (cost of materials) | 111 days | 108 days | A=B, QA |
| DSM-Firmenich AG | CH/AT | 2025-12-31 | EUR 1,475m | EUR 5,504m (cost of sales) | 98 days | 150 days | QA |
| Strabag | CH/AT | 2025-12-31 | EUR 2,979m | EUR 11,169m (cost of materials) | 97 days | 97 days | A=B |
| ABB Group | CH/AT | 2025-12-31 | USD 5,210m | USD 19,580m (cost of sales) | 97 days | 92 days | A=B |
| Adidas | Bavaria | 2025-12-31 | EUR 2,910m | EUR 12,006m (cost of sales) | 88 days | 97 days | A=B, QA |
| Sika AG | CH/AT | 2025-12-31 | CHF 1,176m | CHF 5,048m (cost of materials) | 85 days | 83 days | QA |
| Infineon | Bavaria | 2025-09-30 | EUR 2,011m | EUR 8,909m (cost of sales) | 82 days | 83 days | A=B, QA |
| Siltronic AG | Bavaria | 2025-12-31 | EUR 243m | EUR 1,236m (cost of sales) | 72 days | 90 days | A=B, QA |
| Siemens | Bavaria | 2025-09-30 | EUR 9,183m | EUR 48,515m (cost of sales) | 69 days | 70 days | A=B, QA |
| CTS Eventim AG & Co. KGaA | Bavaria | 2025-12-31 | EUR 381m | EUR 2,249m (cost of sales) | 62 days | 63 days | QA |
| Siemens Healthineers | Bavaria | 2025-09-30 | EUR 2,296m | EUR 14,345m (cost of sales) | 58 days | 56 days | QA |
| Traton SE | Bavaria | 2025-12-31 | EUR 5,474m | EUR 35,630m (cost of sales) | 56 days | 52 days | A=B |
| Wacker Chemie AG | Bavaria | 2025-12-31 | EUR 692m | EUR 4,828m (cost of sales) | 52 days | 66 days | A=B |
| BMW | Bavaria | 2025-12-31 | EUR 12,488m | EUR 112,858m (cost of sales) | 40 days | 43 days | A=B |
| Stadler Rail | CH/AT | 2025-12-31 | CHF 304m | CHF 3,259m (cost of sales) | 34 days | 29 days | A=B |
| MTU Aero Engines | Bavaria | 2025-12-31 | EUR 588m | EUR 7,075m (cost of sales) | 30 days | 30 days | A=B |
| Suss Microtec SE | Bavaria | 2025-12-31 | EUR 25m | EUR 324m (cost of sales) | 28 days | 47 days | A=B |
| Rational AG | Bavaria | 2025-12-31 | EUR 32m | EUR 516m (cost of sales) | 23 days | 25 days | A=B |
| Nemetschek SE | Bavaria | 2025-12-31 | EUR 27m | EUR 45m (cost of materials) | n/a | n/a | A=B, QA |
| Scout24 | Bavaria | 2025-12-31 | EUR 19m | n/a (missing) | n/a | n/a | A=B |
| Siemens Energy | Bavaria | 2025-09-30 | n/a | EUR 32,498m (cost of sales) | n/a | n/a | QA |

Page and printed line for every value: `data/interim/dach_values.csv`. Source URL and retrieval time: `data/interim/dach_dpo.csv` and `data/manifests/dach_documents.json`.

## 3. Agreement between the two extractors

- **Extractor A** is deterministic code (`src/chase/sources/dach_extract.py`): tagged facts where an ESEF file exists, otherwise the printed consolidated statements by row label (English and German), with the notes used when the balance sheet shows only a combined payables line.
- **Extractor B** is an agent reading the same page texts independently, without access to A's output or code.
- Agreement means within 0.5%.

| Field | Both found | Agree | Disagree | Only A | Only B |
|---|---|---|---|---|---|
| trade payables | 44 | 36 | 8 | 2 | 6 |
| cost of sales | 30 | 21 | 9 | 0 | 8 |
| cost of materials | 6 | 2 | 4 | 2 | 6 |
| revenue | 48 | 31 | 17 | 0 | 4 |

Overall: 90 of 128 values found by both agree (70%). A's misses and errors are the usual ones for a label reader: a management-report table with a change column taken for the statement, a parent-company (HGB) balance sheet, a segment line, columns printed oldest-first, and nature-of-expense lines with unusual labels.

**Plainly: extractor A is the weak reader.** Where the two disagreed, QA sided with A in 0 of 62 decided cases. A's value here is as an independent cross-check: an agreement between a label-matching script and an agent reading the page is strong evidence; a disagreement sends the value to QA. It is not a second opinion of equal weight.

## 4. QA adjudication

66 values went to QA (every disagreement and every single-extractor value). Decisions: b 58, null 4, other 4 (a = extractor A was right, b = B was right, other = both wrong, null = no valid figure).

Cases where neither extractor had the right figure for a DPO input:

- **Adidas**, cost of materials, year 1: A read the parent-only HGB income statement of adidas AG on p99 (management report). Adidas reports consolidated by function of expense, so cost_of_materials does not apply; null.
- **Adidas**, cost of materials, year 2: A read the parent-only HGB income statement of adidas AG on p99 (management report). Adidas reports consolidated by function of expense, so cost_of_materials does not apply; null.
- **DSM-Firmenich AG**, trade payables, year 1: A 2,276 is the 2024 column. B took the BS total 1,481, but note 21 splits out received-in-advance 6 and notes 0; rule takes trade accounts payable 1,475. 2025 excludes ANH held for sale.
- **DSM-Firmenich AG**, trade payables, year 2: A 2,174 is not in this report (likely 2023). B took BS total 2,276 incl. advances 5 and notes 4; note 21 gives 2,267. Caution: 2024 BS still includes ANH while 2024 IS is restated to continuing ops.
- **Holcim**, trade payables, year 1: B gave the BS line 3,426 which includes customer advances 236 (note 10.5, p42). Sum of printed trade lines 149+3,041=3,190. A found nothing.
- **Holcim**, trade payables, year 2: B gave BS line 4,745 incl. customer advances 368; sum of printed trade lines 141+4,236=4,377. Caution: 2024 BS includes the North American business spun off in 2025, IS is restated.
- **Siemens Energy**, trade payables, year 1: A read parent-only HGB trade payables (EUR thousand, p45): wrong entity. Group BS shows only 'Trade and other payables' 5,993 (6,293) (p150); note 12 (p171) gives no trade/other split, so no supplier-only figure can be isolated: null under the rule. Best available proxy if wanted: 5,993 (6,293), all classified as financial liabilities.
- **Siemens Energy**, trade payables, year 2: A read parent-only HGB trade payables (EUR thousand, p45): wrong entity. Group BS shows only 'Trade and other payables' 5,993 (6,293) (p150); note 12 (p171) gives no trade/other split, so no supplier-only figure can be isolated: null under the rule. Best available proxy if wanted: 5,993 (6,293), all classified as financial liabilities.

## 5. Blind hand-check of 10

Ten companies drawn at random (seed 7, from the 25 with both a payables and a cost value). The QA agent read the latest-year trade payables and cost line from the report without seeing the extractors' or the final values; the table compares its reading with the final value. **Caveat:** QA had already read the report pages of 5 of the 10 (CTS Eventim, DSM-Firmenich, MTU, Nemetschek, Siemens Healthineers) while adjudicating, so those 5 are a re-read of pages it knew, not fully blind. The other 5 were read for the first time.

| Company | Field | Hand-check | Final | Match |
|---|---|---|---|---|
| Adidas | trade payables | EUR 2,910m | EUR 2,910m | yes |
| Adidas | cost of sales | EUR 12,006m | EUR 12,006m | yes |
| BMW | trade payables | EUR 12,488m | EUR 12,488m | yes |
| BMW | cost of sales | EUR 112,858m | EUR 112,858m | yes |
| CTS Eventim AG & Co. KGaA | trade payables | EUR 381m | EUR 381m | yes |
| CTS Eventim AG & Co. KGaA | cost of sales | EUR 2,249m | EUR 2,249m | yes |
| DSM-Firmenich AG | trade payables | EUR 1,475m | EUR 1,475m | yes |
| DSM-Firmenich AG | cost of sales | EUR 5,504m | EUR 5,504m | yes |
| MTU Aero Engines | trade payables | EUR 588m | EUR 588m | yes |
| MTU Aero Engines | cost of sales | EUR 7,075m | EUR 7,075m | yes |
| Nemetschek SE | trade payables | EUR 27m | EUR 27m | yes |
| Nemetschek SE | cost of materials | EUR 45m | EUR 45m | yes |
| Puma SE | trade payables | EUR 1,271m | EUR 1,271m | yes |
| Puma SE | cost of sales | EUR 4,016m | EUR 4,016m | yes |
| Siemens Healthineers | trade payables | EUR 2,296m | EUR 2,296m | yes |
| Siemens Healthineers | cost of sales | EUR 14,345m | EUR 14,345m | yes |
| Stadler Rail | trade payables | CHF 304m | CHF 304m | yes |
| Stadler Rail | cost of sales | CHF 3,259m | CHF 3,259m | yes |
| Strabag | trade payables | EUR 2,979m | EUR 2,979m | yes |
| Strabag | cost of materials | EUR 11,169m | EUR 11,169m | yes |

Result: 20 of 20 match within 0.5%.

## 6. Effect on scoring, the Munich dinner list and the queue

The rows enter `data/processed/dpo.parquet` as a third source next to SEC and ESEF, with priority over a broad ESEF payables line, and flow through the existing scoring unchanged: a computed DPO sets the pain score only where no UK or Spanish reported figure exists, and it is scaled by confidence. A full-confidence proxy (trade payables over cost of sales) can reach Tier 1, as 47 accounts did before this slice; a cost-of-materials or broad-payables row (confidence 0.7) cannot.
- Companies in DE/CH/AT whose evidence basis is now the computed DPO proxy: 20; companies whose basis changed with this slice: 6.
- Munich dinner list before: 7 accounts (Siemens Energy AG, Puma, Rheinmetall AG, Brenntag, Heidelberg Materials, Continental AG, Volkswagen Group).
- Munich dinner list after: 10 accounts (Siemens Energy AG, Hensoldt (proxy), Infineon Technologies (proxy), Puma, Rheinmetall AG, Brenntag, Heidelberg Materials, Continental AG, CTS Eventim (proxy), Volkswagen Group).
- A proxy hook needs a DPO of at least 1.3 times the sector median, on a trade-payables line over cost of sales, from FY2025 or later. A cost-of-materials proxy never earns an invitation: it reads high against the cost-of-sales median, so Knorr-Bremse sits on the bench with that reason.
- Tier changes: 9 existing accounts changed tier. From the slice's own figures: ABB Group 3 to 2, Schindler Elevator 3 to 2, Knorr-Bremse 3 to 2, Infineon Technologies 3 to 2. Ripple from sector medians moving by under one day: Verisure plc 2 to 3, Paychex Inc 2 to 3, Gestamp Automocion SA 3 to 2, DuPont 3 to 2, Ferrari N.V. 3 to 2. Tier 1 has 185 accounts; added companies by tier: Hensoldt (Tier 1), CTS Eventim (Tier 1), Siemens Healthineers (Tier 2), Siltronic (Tier 2), Krones (Tier 3), Rational (Tier 3), Traton (Tier 3), Wacker Chemie (Tier 3), SUSS MicroTec (Tier 3), Nemetschek (Tier 3), Scout24 (Tier 3).
- Weekly queue (top 25): 0 new (none), 0 dropped (none).
- Roll-up side effect: adding Siemens Healthineers and Traton as groups moves their UK entities out of Siemens and Volkswagen Group, which is correct for the subsidiary groups and changes the parents' UK figures.

## 7. Limits

- **Ticketing:** CTS Eventim's trade payables (EUR 381m) exclude ticket money owed to promoters, which it shows on a separate line (EUR 1.09bn), so the figure is supplier payables; its sector median comes from a broad services bucket.
- **Proxy, not payment behaviour.** Year-end trade payables over annual cost include timing, seasonality, capex payables in some groups and purchases outside cost of sales. High DPO can mean long agreed terms paid on time.
- **Cost of materials** (nature-of-expense reporters) is a narrower base than cost of sales and pushes DPO up; those rows carry confidence 0.7 and stay out of sector medians.
- **Perimeter changes:** DSM-Firmenich (animal health moved to held for sale) and Holcim (North America spin-off: 2024 income statement restated, 2024 balance sheet not) have prior-year figures on a different perimeter; their year-on-year change is not used as a trend.
- **Supplier finance:** Siltronic and Traton disclose supplier-finance payables; where a company presents them outside trade payables, the proxy understates the days its suppliers wait.
- **Annual, not current:** the latest reports are for FY2025. September year-end companies publish FY2026 reports from late November 2026.

## Cost

No paid API calls. Agents: document scout, two extractor-B readers, one QA adjudicator and hand-checker (token counts in `docs/model_routing.md`). Downloads through the shared rate-limited client (1 request per second per host, declared User-Agent).
