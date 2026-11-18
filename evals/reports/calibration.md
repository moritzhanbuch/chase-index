# Calibration

Gold set: `evals/gold/calibration.csv`, built by a separate agent that could not see the scores (17 "obvious tens" expected in Tier 1, 15 "obvious zeros" expected in Tier 3). **The gold set should be reviewed by hand.**

Pass rule: every ten in Tier 1 and every zero in Tier 3. Each run of `evals/calibrate.py` appends an iteration below.

## Iteration 1 (2026-11-16 12:09): FAIL

- Change: Baseline: first weights, UK roll-up without Companies House parent chains
- Tens in Tier 1: 13/17. Zeros in Tier 3: 15/15.
- Not in the scored table: 0

| Company | Expected | Got tier | Fit | Pain | Signal | Pain basis | Days | UK entities |
|---|---|---|---|---|---|---|---|---|
| Rolls-Royce | ten (Tier 1) | 2 | 92.0 | 36.0 | 20.0 | uk_reported | 43.2 | 5.0 |
| Airbus | ten (Tier 1) | 2 | 91.2 | 37.1 | 38.8 | uk_reported | 41.0 | 2.0 |
| Anheuser-Busch InBev | ten (Tier 1) | 3 | 89.8 | 0.0 | 0.0 | no_evidence | nan | nan |
| Alstom | ten (Tier 1) | 2 | 92.0 | 40.6 | 18.2 | computed_dpo_proxy | 92.9 | nan |

## Iteration 2 (2026-11-16 12:09): FAIL

- Change: UK group days, late share and >60-day share are now weighted by the invoice value each entity reports (simple mean kept as a separate column)
- Tens in Tier 1: 13/17. Zeros in Tier 3: 15/15.
- Not in the scored table: 0

| Company | Expected | Got tier | Fit | Pain | Signal | Pain basis | Days | UK entities |
|---|---|---|---|---|---|---|---|---|
| Rolls-Royce | ten (Tier 1) | 2 | 92.0 | 54.3 | 20.0 | uk_reported | 66.1 | 5.0 |
| Anheuser-Busch InBev | ten (Tier 1) | 3 | 89.8 | 0.0 | 0.0 | no_evidence | nan | nan |
| Alstom | ten (Tier 1) | 2 | 92.0 | 40.6 | 18.2 | computed_dpo_proxy | 92.9 | nan |
| Saint-Gobain | ten (Tier 1) | 2 | 95.0 | 51.1 | 41.4 | uk_reported | 53.3 | 5.0 |

## Iteration 3 (2026-11-16 12:12): FAIL

- Change: Universe rebuilt with more UK ESEF filers; roll-up now also uses Wikidata subsidiary edges (P355/P749 only, depth <= 2)
- Tens in Tier 1: 11/17. Zeros in Tier 3: 15/15.
- Not in the scored table: 0

| Company | Expected | Got tier | Fit | Pain | Signal | Pain basis | Days | UK entities |
|---|---|---|---|---|---|---|---|---|
| Rolls-Royce | ten (Tier 1) | 2 | 92.0 | 54.3 | 20.0 | uk_reported | 66.1 | 5.0 |
| Nestlé | ten (Tier 1) | 3 | 89.8 | 0.0 | 0.0 | no_evidence | nan | nan |
| Anheuser-Busch InBev | ten (Tier 1) | 3 | 89.8 | 0.0 | 0.0 | no_evidence | nan | nan |
| Alstom | ten (Tier 1) | 2 | 92.0 | 40.2 | 18.2 | computed_dpo_proxy | 92.9 | nan |
| Saint-Gobain | ten (Tier 1) | 2 | 95.0 | 51.1 | 41.4 | uk_reported | 53.3 | 5.0 |
| Mondelez International | ten (Tier 1) | 2 | 81.8 | 53.9 | 0.0 | computed_dpo_proxy | 134.1 | nan |

## Iteration 4 (2026-11-16 12:12): FAIL

- Change: Same-name financing vehicles folded into their group; multi-word aliases usable as brand keys
- Tens in Tier 1: 12/17. Zeros in Tier 3: 15/15.
- Not in the scored table: 0

| Company | Expected | Got tier | Fit | Pain | Signal | Pain basis | Days | UK entities |
|---|---|---|---|---|---|---|---|---|
| Rolls-Royce | ten (Tier 1) | 2 | 92.0 | 54.3 | 20.0 | uk_reported | 66.1 | 5.0 |
| Anheuser-Busch InBev | ten (Tier 1) | 3 | 89.8 | 0.0 | 0.0 | no_evidence | nan | nan |
| Alstom | ten (Tier 1) | 2 | 92.0 | 40.2 | 18.2 | computed_dpo_proxy | 92.9 | nan |
| Saint-Gobain | ten (Tier 1) | 2 | 95.0 | 51.1 | 41.4 | uk_reported | 53.3 | 5.0 |
| Mondelez International | ten (Tier 1) | 2 | 81.8 | 53.9 | 0.0 | computed_dpo_proxy | 134.1 | nan |

## Iteration 5 (2026-11-16 12:13): FAIL

- Change: Common-word list cleaned (it wrongly contained real brand names such as Mondelez); an ordinary word only matches when it is the entity's whole distinctive name
- Tens in Tier 1: 13/17. Zeros in Tier 3: 15/15.
- Not in the scored table: 0

| Company | Expected | Got tier | Fit | Pain | Signal | Pain basis | Days | UK entities |
|---|---|---|---|---|---|---|---|---|
| Rolls-Royce | ten (Tier 1) | 2 | 92.0 | 54.3 | 20.0 | uk_reported | 66.1 | 5.0 |
| Anheuser-Busch InBev | ten (Tier 1) | 3 | 89.8 | 0.0 | 0.0 | no_evidence | nan | nan |
| Alstom | ten (Tier 1) | 2 | 92.0 | 40.2 | 18.2 | computed_dpo_proxy | 92.9 | nan |
| Saint-Gobain | ten (Tier 1) | 2 | 95.0 | 51.1 | 41.4 | uk_reported | 53.3 | 5.0 |

## Iteration 6 (2026-11-16 12:13): FAIL

- Change: tier1_min_pain lowered from 55 to 50
- Tens in Tier 1: 15/17. Zeros in Tier 3: 15/15.
- Not in the scored table: 0

| Company | Expected | Got tier | Fit | Pain | Signal | Pain basis | Days | UK entities |
|---|---|---|---|---|---|---|---|---|
| Anheuser-Busch InBev | ten (Tier 1) | 3 | 89.8 | 0.0 | 0.0 | no_evidence | nan | nan |
| Alstom | ten (Tier 1) | 2 | 92.0 | 40.2 | 18.2 | computed_dpo_proxy | 92.9 | nan |

## Iteration 7 (2026-11-16 12:21): FAIL

- Change: Companies House parent chains added to the UK roll-up (ch_psc_chain)
- Tens in Tier 1: 15/17. Zeros in Tier 3: 15/15.
- Not in the scored table: 0

| Company | Expected | Got tier | Fit | Pain | Signal | Pain basis | Days | UK entities |
|---|---|---|---|---|---|---|---|---|
| GSK plc | ten (Tier 1) | 2 | 86.5 | 44.1 | 10.0 | uk_reported | 55.3 | 11.0 |
| Saint-Gobain | ten (Tier 1) | 2 | 95.0 | 49.0 | 30.0 | uk_reported | 53.3 | 6.0 |

## Iteration 8 (2026-11-16 12:21): PASS

- Change: days_cap lowered from 75 to 65 (about twice the official UK median of 32)
- Tens in Tier 1: 17/17. Zeros in Tier 3: 15/15.
- Not in the scored table: 0

| Company | Expected | Tier | Fit | Pain | Signal |
|---|---|---|---|---|---|
| Diageo | ten | 1 | 89 | 62 | 20 |
| Unilever | ten | 1 | 94 | 62 | 30 |
| Rolls-Royce | ten | 1 | 92 | 63 | 20 |
| GSK plc | ten | 1 | 86 | 51 | 10 |
| Haleon plc | ten | 1 | 85 | 76 | 63 |
| Johnson Matthey plc | ten | 1 | 86 | 97 | 58 |
| Airbus | ten | 1 | 91 | 62 | 30 |
| Nestlé | ten | 1 | 90 | 78 | 65 |
| Anheuser-Busch InBev | ten | 1 | 90 | 64 | 39 |
| Coca-Cola Europacific Partners | ten | 1 | 89 | 62 | 30 |
| Alstom | ten | 1 | 92 | 90 | 55 |
| Saint-Gobain | ten | 1 | 95 | 55 | 30 |
| Siemens Energy AG | ten | 1 | 92 | 85 | 65 |
| Mondelez International | ten | 1 | 84 | 70 | 47 |
| Caterpillar Inc. | ten | 1 | 91 | 62 | 20 |
| Kimberly-Clark | ten | 1 | 83 | 79 | 52 |
| Grifols | ten | 1 | 80 | 98 | 31 |
| HSBC | zero | 3 | 66 | 1 | 10 |
| Lloyds Banking Group plc | zero | 3 | 61 | 6 | 20 |
| Santander Group | zero | 3 | 64 | 16 | 18 |
| Deutsche Bank | zero | 3 | 64 | 26 | 20 |
| Allianz SE | zero | 3 | 66 | 14 | 20 |
| AXA | zero | 3 | 66 | 10 | 30 |
| BAE Systems | zero | 3 | 92 | 0 | 0 |
| Mercedes-Benz Group | zero | 3 | 95 | 6 | 20 |
| BMW | zero | 3 | 95 | 3 | 20 |
| Iberdrola | zero | 3 | 84 | 1 | 0 |
| Naturgy Energy Group SA | zero | 3 | 84 | 0 | 0 |
| Industrial and Commercial Bank of China | zero | 3 | 49 | 0 | 0 |
| Sberbank | zero | 3 | 0 | 0 | 0 |
| Gazprom | zero | 3 | 0 | 24 | 42 |
| Rosneft | zero | 3 | 0 | 0 | 0 |

## Iteration 9 (2026-11-16 12:21): PASS

- Change: Financial-sector companies are held in Tier 3 explicitly (outside the ICP), not only through a low pain score
- Tens in Tier 1: 17/17. Zeros in Tier 3: 15/15.
- Not in the scored table: 0

| Company | Expected | Tier | Fit | Pain | Signal |
|---|---|---|---|---|---|
| Diageo | ten | 1 | 89 | 62 | 20 |
| Unilever | ten | 1 | 94 | 62 | 30 |
| Rolls-Royce | ten | 1 | 92 | 63 | 20 |
| GSK plc | ten | 1 | 86 | 51 | 10 |
| Haleon plc | ten | 1 | 85 | 76 | 63 |
| Johnson Matthey plc | ten | 1 | 86 | 97 | 58 |
| Airbus | ten | 1 | 91 | 62 | 30 |
| Nestlé | ten | 1 | 90 | 78 | 65 |
| Anheuser-Busch InBev | ten | 1 | 90 | 64 | 39 |
| Coca-Cola Europacific Partners | ten | 1 | 89 | 62 | 30 |
| Alstom | ten | 1 | 92 | 90 | 55 |
| Saint-Gobain | ten | 1 | 95 | 55 | 30 |
| Siemens Energy AG | ten | 1 | 92 | 85 | 65 |
| Mondelez International | ten | 1 | 84 | 70 | 47 |
| Caterpillar Inc. | ten | 1 | 91 | 62 | 20 |
| Kimberly-Clark | ten | 1 | 83 | 79 | 52 |
| Grifols | ten | 1 | 80 | 98 | 31 |
| HSBC | zero | 3 | 66 | 1 | 10 |
| Lloyds Banking Group plc | zero | 3 | 61 | 6 | 20 |
| Santander Group | zero | 3 | 64 | 16 | 18 |
| Deutsche Bank | zero | 3 | 64 | 26 | 20 |
| Allianz SE | zero | 3 | 66 | 14 | 20 |
| AXA | zero | 3 | 66 | 10 | 30 |
| BAE Systems | zero | 3 | 92 | 0 | 0 |
| Mercedes-Benz Group | zero | 3 | 95 | 6 | 20 |
| BMW | zero | 3 | 95 | 3 | 20 |
| Iberdrola | zero | 3 | 84 | 1 | 0 |
| Naturgy Energy Group SA | zero | 3 | 84 | 0 | 0 |
| Industrial and Commercial Bank of China | zero | 3 | 49 | 0 | 0 |
| Sberbank | zero | 3 | 0 | 0 | 0 |
| Gazprom | zero | 3 | 0 | 24 | 42 |
| Rosneft | zero | 3 | 0 | 0 | 0 |

## Iteration 10 (2026-11-16 12:22): PASS

- Change: Steeper revenue bands; priority score inside a tier now weights fit 0.45, pain 0.40, signal 0.15 (was 0.35/0.50/0.15) so large European groups rank above mid-caps with one UK entity
- Tens in Tier 1: 17/17. Zeros in Tier 3: 15/15.
- Not in the scored table: 0

| Company | Expected | Tier | Fit | Pain | Signal |
|---|---|---|---|---|---|
| Diageo | ten | 1 | 88 | 62 | 20 |
| Unilever | ten | 1 | 94 | 62 | 30 |
| Rolls-Royce | ten | 1 | 90 | 63 | 20 |
| GSK plc | ten | 1 | 85 | 51 | 10 |
| Haleon plc | ten | 1 | 82 | 76 | 63 |
| Johnson Matthey plc | ten | 1 | 84 | 97 | 58 |
| Airbus | ten | 1 | 91 | 62 | 30 |
| Nestlé | ten | 1 | 90 | 78 | 65 |
| Anheuser-Busch InBev | ten | 1 | 90 | 64 | 39 |
| Coca-Cola Europacific Partners | ten | 1 | 88 | 62 | 30 |
| Alstom | ten | 1 | 90 | 90 | 55 |
| Saint-Gobain | ten | 1 | 95 | 55 | 30 |
| Siemens Energy AG | ten | 1 | 90 | 85 | 65 |
| Mondelez International | ten | 1 | 83 | 70 | 47 |
| Caterpillar Inc. | ten | 1 | 91 | 62 | 20 |
| Kimberly-Clark | ten | 1 | 80 | 79 | 52 |
| Grifols | ten | 1 | 76 | 98 | 31 |
| HSBC | zero | 3 | 66 | 1 | 10 |
| Lloyds Banking Group plc | zero | 3 | 60 | 6 | 20 |
| Santander Group | zero | 3 | 62 | 16 | 18 |
| Deutsche Bank | zero | 3 | 62 | 26 | 20 |
| Allianz SE | zero | 3 | 66 | 14 | 20 |
| AXA | zero | 3 | 66 | 10 | 30 |
| BAE Systems | zero | 3 | 90 | 0 | 0 |
| Mercedes-Benz Group | zero | 3 | 95 | 6 | 20 |
| BMW | zero | 3 | 95 | 3 | 20 |
| Iberdrola | zero | 3 | 83 | 1 | 0 |
| Naturgy Energy Group SA | zero | 3 | 82 | 0 | 0 |
| Industrial and Commercial Bank of China | zero | 3 | 49 | 0 | 0 |
| Sberbank | zero | 3 | 0 | 0 | 0 |
| Gazprom | zero | 3 | 0 | 24 | 42 |
| Rosneft | zero | 3 | 0 | 0 | 0 |

## Iteration 11 (2026-11-16 12:23): PASS

- Change: Short-name chain matches need the same country (EQT AB is not EQT Corp); two stale display names fixed
- Tens in Tier 1: 17/17. Zeros in Tier 3: 15/15.
- Not in the scored table: 0

| Company | Expected | Tier | Fit | Pain | Signal |
|---|---|---|---|---|---|
| Diageo | ten | 1 | 88 | 62 | 20 |
| Unilever | ten | 1 | 94 | 62 | 30 |
| Rolls-Royce | ten | 1 | 90 | 63 | 20 |
| GSK plc | ten | 1 | 85 | 51 | 10 |
| Haleon plc | ten | 1 | 82 | 76 | 63 |
| Johnson Matthey plc | ten | 1 | 84 | 97 | 58 |
| Airbus | ten | 1 | 91 | 62 | 30 |
| Nestlé | ten | 1 | 90 | 78 | 65 |
| Anheuser-Busch InBev | ten | 1 | 90 | 64 | 39 |
| Coca-Cola Europacific Partners | ten | 1 | 88 | 62 | 30 |
| Alstom | ten | 1 | 90 | 90 | 55 |
| Saint-Gobain | ten | 1 | 95 | 55 | 30 |
| Siemens Energy AG | ten | 1 | 90 | 85 | 65 |
| Mondelez International | ten | 1 | 83 | 70 | 47 |
| Caterpillar Inc. | ten | 1 | 91 | 62 | 20 |
| Kimberly-Clark | ten | 1 | 80 | 79 | 52 |
| Grifols | ten | 1 | 76 | 98 | 31 |
| HSBC | zero | 3 | 66 | 1 | 10 |
| Lloyds Banking Group plc | zero | 3 | 60 | 6 | 20 |
| Santander Group | zero | 3 | 62 | 16 | 18 |
| Deutsche Bank | zero | 3 | 62 | 26 | 20 |
| Allianz SE | zero | 3 | 66 | 14 | 20 |
| AXA | zero | 3 | 66 | 10 | 30 |
| BAE Systems | zero | 3 | 90 | 0 | 0 |
| Mercedes-Benz Group | zero | 3 | 95 | 6 | 20 |
| BMW | zero | 3 | 95 | 3 | 20 |
| Iberdrola | zero | 3 | 83 | 1 | 0 |
| Naturgy Energy Group SA | zero | 3 | 82 | 0 | 0 |
| Industrial and Commercial Bank of China | zero | 3 | 49 | 0 | 0 |
| Sberbank | zero | 3 | 0 | 0 | 0 |
| Gazprom | zero | 3 | 0 | 24 | 42 |
| Rosneft | zero | 3 | 0 | 0 | 0 |

## Iteration 12 (2026-11-16 12:25): PASS

- Change: Rerun after UK roll-up with Companies House parent chains (requested rerun)
- Tens in Tier 1: 17/17. Zeros in Tier 3: 15/15.
- Not in the scored table: 0

| Company | Expected | Tier | Fit | Pain | Signal |
|---|---|---|---|---|---|
| Diageo | ten | 1 | 88 | 62 | 20 |
| Unilever | ten | 1 | 94 | 62 | 30 |
| Rolls-Royce | ten | 1 | 90 | 63 | 20 |
| GSK plc | ten | 1 | 85 | 51 | 10 |
| Haleon plc | ten | 1 | 82 | 76 | 63 |
| Johnson Matthey plc | ten | 1 | 84 | 97 | 58 |
| Airbus | ten | 1 | 91 | 62 | 30 |
| Nestlé | ten | 1 | 90 | 78 | 65 |
| Anheuser-Busch InBev | ten | 1 | 90 | 64 | 39 |
| Coca-Cola Europacific Partners | ten | 1 | 88 | 62 | 30 |
| Alstom | ten | 1 | 90 | 90 | 55 |
| Saint-Gobain | ten | 1 | 95 | 55 | 30 |
| Siemens Energy AG | ten | 1 | 90 | 85 | 65 |
| Mondelez International | ten | 1 | 83 | 70 | 47 |
| Caterpillar Inc. | ten | 1 | 91 | 62 | 20 |
| Kimberly-Clark | ten | 1 | 80 | 79 | 52 |
| Grifols | ten | 1 | 76 | 98 | 31 |
| HSBC | zero | 3 | 66 | 1 | 10 |
| Lloyds Banking Group plc | zero | 3 | 60 | 6 | 20 |
| Santander Group | zero | 3 | 62 | 16 | 18 |
| Deutsche Bank | zero | 3 | 62 | 26 | 20 |
| Allianz SE | zero | 3 | 66 | 14 | 20 |
| AXA | zero | 3 | 66 | 10 | 30 |
| BAE Systems | zero | 3 | 90 | 0 | 0 |
| Mercedes-Benz Group | zero | 3 | 95 | 6 | 20 |
| BMW | zero | 3 | 95 | 3 | 20 |
| Iberdrola | zero | 3 | 83 | 1 | 0 |
| Naturgy Energy Group SA | zero | 3 | 82 | 0 | 0 |
| Industrial and Commercial Bank of China | zero | 3 | 49 | 0 | 0 |
| Sberbank | zero | 3 | 0 | 0 | 0 |
| Gazprom | zero | 3 | 0 | 24 | 42 |
| Rosneft | zero | 3 | 0 | 0 | 0 |

## Iteration 13 (2026-11-16 15:47): FAIL

- Change: Roll-up v2 (majority-ownership chains only, Wikidata as corroboration only) after the entity-resolution check found precision 0.83
- Tens in Tier 1: 15/17. Zeros in Tier 3: 15/15.
- Not in the scored table: 0

| Company | Expected | Got tier | Fit | Pain | Signal | Pain basis | Days | UK entities |
|---|---|---|---|---|---|---|---|---|
| Anheuser-Busch InBev | ten (Tier 1) | 3 | 89.8 | 0.0 | 0.0 | no_evidence | nan | nan |
| Alstom | ten (Tier 1) | 2 | 90.5 | 40.2 | 18.2 | computed_dpo_proxy | 92.9 | nan |

## Iteration 14 (2026-11-16 15:47): PASS

- Change: Chain steps matched by unique UK name with a majority holding are accepted again (only number-with-different-name steps end the walk)
- Tens in Tier 1: 17/17. Zeros in Tier 3: 15/15.
- Not in the scored table: 0

| Company | Expected | Tier | Fit | Pain | Signal |
|---|---|---|---|---|---|
| Diageo | ten | 1 | 88 | 62 | 20 |
| Unilever | ten | 1 | 94 | 62 | 30 |
| Rolls-Royce | ten | 1 | 90 | 62 | 20 |
| GSK plc | ten | 1 | 85 | 51 | 10 |
| Haleon plc | ten | 1 | 82 | 76 | 63 |
| Johnson Matthey plc | ten | 1 | 84 | 97 | 58 |
| Airbus | ten | 1 | 91 | 68 | 30 |
| Nestlé | ten | 1 | 90 | 78 | 65 |
| Anheuser-Busch InBev | ten | 1 | 90 | 64 | 39 |
| Coca-Cola Europacific Partners | ten | 1 | 88 | 62 | 30 |
| Alstom | ten | 1 | 90 | 90 | 55 |
| Saint-Gobain | ten | 1 | 95 | 57 | 52 |
| Siemens Energy AG | ten | 1 | 90 | 85 | 65 |
| Mondelez International | ten | 1 | 83 | 70 | 47 |
| Caterpillar Inc. | ten | 1 | 91 | 62 | 20 |
| Kimberly-Clark | ten | 1 | 80 | 79 | 52 |
| Grifols | ten | 1 | 76 | 98 | 31 |
| HSBC | zero | 3 | 66 | 2 | 10 |
| Lloyds Banking Group plc | zero | 3 | 60 | 2 | 10 |
| Santander Group | zero | 3 | 62 | 9 | 0 |
| Deutsche Bank | zero | 3 | 62 | 0 | 0 |
| Allianz SE | zero | 3 | 66 | 15 | 20 |
| AXA | zero | 3 | 66 | 0 | 0 |
| BAE Systems | zero | 3 | 90 | 0 | 0 |
| Mercedes-Benz Group | zero | 3 | 95 | 6 | 20 |
| BMW | zero | 3 | 95 | 2 | 20 |
| Iberdrola | zero | 3 | 83 | 1 | 0 |
| Naturgy Energy Group SA | zero | 3 | 82 | 0 | 0 |
| Industrial and Commercial Bank of China | zero | 3 | 49 | 0 | 0 |
| Sberbank | zero | 3 | 0 | 0 | 0 |
| Gazprom | zero | 3 | 0 | 0 | 0 |
| Rosneft | zero | 3 | 0 | 0 | 0 |

## Iteration 15 (2026-11-16 15:48): PASS

- Change: Sectors for 117 more companies (LLM), manual overrides file, Wikidata parent links ignored for companies with their own filings
- Tens in Tier 1: 17/17. Zeros in Tier 3: 15/15.
- Not in the scored table: 0

| Company | Expected | Tier | Fit | Pain | Signal |
|---|---|---|---|---|---|
| Diageo | ten | 1 | 88 | 62 | 20 |
| Unilever | ten | 1 | 94 | 62 | 30 |
| Rolls-Royce | ten | 1 | 90 | 62 | 20 |
| GSK plc | ten | 1 | 85 | 51 | 10 |
| Haleon plc | ten | 1 | 82 | 76 | 63 |
| Johnson Matthey plc | ten | 1 | 84 | 97 | 58 |
| Airbus | ten | 1 | 91 | 68 | 30 |
| Nestlé | ten | 1 | 90 | 78 | 65 |
| Anheuser-Busch InBev | ten | 1 | 90 | 64 | 39 |
| Coca-Cola Europacific Partners | ten | 1 | 88 | 62 | 30 |
| Alstom | ten | 1 | 90 | 90 | 55 |
| Saint-Gobain | ten | 1 | 95 | 57 | 52 |
| Siemens Energy AG | ten | 1 | 90 | 85 | 65 |
| Mondelez International | ten | 1 | 83 | 70 | 47 |
| Caterpillar Inc. | ten | 1 | 91 | 62 | 20 |
| Kimberly-Clark | ten | 1 | 80 | 79 | 52 |
| Grifols | ten | 1 | 76 | 98 | 31 |
| HSBC | zero | 3 | 66 | 2 | 10 |
| Lloyds Banking Group plc | zero | 3 | 60 | 2 | 10 |
| Santander Group | zero | 3 | 62 | 9 | 0 |
| Deutsche Bank | zero | 3 | 62 | 0 | 0 |
| Allianz SE | zero | 3 | 66 | 15 | 20 |
| AXA | zero | 3 | 66 | 0 | 0 |
| BAE Systems | zero | 3 | 90 | 0 | 0 |
| Mercedes-Benz Group | zero | 3 | 95 | 6 | 20 |
| BMW | zero | 3 | 95 | 2 | 20 |
| Iberdrola | zero | 3 | 83 | 1 | 0 |
| Naturgy Energy Group SA | zero | 3 | 82 | 0 | 0 |
| Industrial and Commercial Bank of China | zero | 3 | 49 | 0 | 0 |
| Sberbank | zero | 3 | 0 | 0 | 0 |
| Gazprom | zero | 3 | 0 | 0 | 0 |
| Rosneft | zero | 3 | 0 | 0 | 0 |

## Iteration 16 (2026-11-16 15:50): PASS

- Change: HQ country corrected for ESEF-only companies (LLM pass, 36 changes)
- Tens in Tier 1: 17/17. Zeros in Tier 3: 15/15.
- Not in the scored table: 0

| Company | Expected | Tier | Fit | Pain | Signal |
|---|---|---|---|---|---|
| Diageo | ten | 1 | 88 | 62 | 20 |
| Unilever | ten | 1 | 94 | 62 | 30 |
| Rolls-Royce | ten | 1 | 90 | 62 | 20 |
| GSK plc | ten | 1 | 85 | 51 | 10 |
| Haleon plc | ten | 1 | 82 | 76 | 63 |
| Johnson Matthey plc | ten | 1 | 84 | 97 | 58 |
| Airbus | ten | 1 | 91 | 68 | 30 |
| Nestlé | ten | 1 | 90 | 78 | 65 |
| Anheuser-Busch InBev | ten | 1 | 90 | 64 | 39 |
| Coca-Cola Europacific Partners | ten | 1 | 88 | 62 | 30 |
| Alstom | ten | 1 | 90 | 90 | 55 |
| Saint-Gobain | ten | 1 | 95 | 57 | 52 |
| Siemens Energy AG | ten | 1 | 90 | 85 | 65 |
| Mondelez International | ten | 1 | 83 | 70 | 47 |
| Caterpillar Inc. | ten | 1 | 91 | 62 | 20 |
| Kimberly-Clark | ten | 1 | 80 | 79 | 52 |
| Grifols | ten | 1 | 76 | 98 | 31 |
| HSBC | zero | 3 | 66 | 2 | 10 |
| Lloyds Banking Group plc | zero | 3 | 60 | 2 | 10 |
| Santander Group | zero | 3 | 62 | 9 | 0 |
| Deutsche Bank | zero | 3 | 62 | 0 | 0 |
| Allianz SE | zero | 3 | 66 | 15 | 20 |
| AXA | zero | 3 | 66 | 0 | 0 |
| BAE Systems | zero | 3 | 90 | 0 | 0 |
| Mercedes-Benz Group | zero | 3 | 95 | 6 | 20 |
| BMW | zero | 3 | 95 | 2 | 20 |
| Iberdrola | zero | 3 | 83 | 1 | 0 |
| Naturgy Energy Group SA | zero | 3 | 82 | 0 | 0 |
| Industrial and Commercial Bank of China | zero | 3 | 49 | 0 | 0 |
| Sberbank | zero | 3 | 0 | 0 | 0 |
| Gazprom | zero | 3 | 0 | 0 | 0 |
| Rosneft | zero | 3 | 0 | 0 | 0 |

## Iteration 17 (2026-11-16 15:56): PASS

- Change: make evals
- Tens in Tier 1: 17/17. Zeros in Tier 3: 15/15.
- Not in the scored table: 0

| Company | Expected | Tier | Fit | Pain | Signal |
|---|---|---|---|---|---|
| Diageo | ten | 1 | 88 | 62 | 20 |
| Unilever | ten | 1 | 94 | 62 | 30 |
| Rolls-Royce | ten | 1 | 90 | 62 | 20 |
| GSK plc | ten | 1 | 85 | 51 | 10 |
| Haleon plc | ten | 1 | 82 | 76 | 63 |
| Johnson Matthey plc | ten | 1 | 84 | 97 | 58 |
| Airbus | ten | 1 | 91 | 68 | 30 |
| Nestlé | ten | 1 | 90 | 78 | 65 |
| Anheuser-Busch InBev | ten | 1 | 90 | 64 | 39 |
| Coca-Cola Europacific Partners | ten | 1 | 88 | 62 | 30 |
| Alstom | ten | 1 | 90 | 90 | 55 |
| Saint-Gobain | ten | 1 | 95 | 57 | 52 |
| Siemens Energy AG | ten | 1 | 90 | 85 | 65 |
| Mondelez International | ten | 1 | 83 | 70 | 47 |
| Caterpillar Inc. | ten | 1 | 91 | 62 | 20 |
| Kimberly-Clark | ten | 1 | 80 | 79 | 52 |
| Grifols | ten | 1 | 76 | 98 | 31 |
| HSBC | zero | 3 | 66 | 2 | 10 |
| Lloyds Banking Group plc | zero | 3 | 60 | 2 | 10 |
| Santander Group | zero | 3 | 62 | 9 | 0 |
| Deutsche Bank | zero | 3 | 62 | 0 | 0 |
| Allianz SE | zero | 3 | 66 | 15 | 20 |
| AXA | zero | 3 | 66 | 0 | 0 |
| BAE Systems | zero | 3 | 90 | 0 | 0 |
| Mercedes-Benz Group | zero | 3 | 95 | 6 | 20 |
| BMW | zero | 3 | 95 | 2 | 20 |
| Iberdrola | zero | 3 | 83 | 1 | 0 |
| Naturgy Energy Group SA | zero | 3 | 82 | 0 | 0 |
| Industrial and Commercial Bank of China | zero | 3 | 49 | 0 | 0 |
| Sberbank | zero | 3 | 0 | 0 | 0 |
| Gazprom | zero | 3 | 0 | 0 | 0 |
| Rosneft | zero | 3 | 0 | 0 | 0 |

## Iteration 18 (2026-11-16 16:00): FAIL

- Change: Asset review fixes: missing pain components score zero (no renormalising), UK trend weighted like the headline, intercompany-sized UK volumes down-weighted, ISIN bug fixed
- Tens in Tier 1: 14/17. Zeros in Tier 3: 15/15.
- Not in the scored table: 0

| Company | Expected | Got tier | Fit | Pain | Signal | Pain basis | Days | UK entities |
|---|---|---|---|---|---|---|---|---|
| Diageo | ten (Tier 1) | 2 | 87.5 | 40.4 | 33.6 | uk_reported | 82.2 | 5.0 |
| Rolls-Royce | ten (Tier 1) | 2 | 90.5 | 43.3 | 43.6 | uk_reported | 68.1 | 4.0 |
| GSK plc | ten (Tier 1) | 2 | 85.0 | 30.5 | 10.0 | uk_reported | 55.3 | 11.0 |

## Iteration 19 (2026-11-16 16:00): FAIL

- Change: Intercompany guard relaxed for UK-headquartered groups (UK entities can carry most of the group's purchasing)
- Tens in Tier 1: 15/17. Zeros in Tier 3: 15/15.
- Not in the scored table: 0

| Company | Expected | Got tier | Fit | Pain | Signal | Pain basis | Days | UK entities |
|---|---|---|---|---|---|---|---|---|
| Diageo | ten (Tier 1) | 2 | 87.5 | 40.4 | 33.6 | uk_reported | 82.2 | 5.0 |
| Rolls-Royce | ten (Tier 1) | 2 | 90.5 | 43.3 | 43.6 | uk_reported | 68.1 | 4.0 |

## Iteration 20 (2026-11-16 16:00): PASS

- Change: Guard for UK-headquartered groups only catches unit-error-sized values (2.5x group cost base)
- Tens in Tier 1: 17/17. Zeros in Tier 3: 15/15.
- Not in the scored table: 0

| Company | Expected | Tier | Fit | Pain | Signal |
|---|---|---|---|---|---|
| Diageo | ten | 1 | 88 | 67 | 34 |
| Unilever | ten | 1 | 94 | 68 | 45 |
| Rolls-Royce | ten | 1 | 90 | 72 | 44 |
| GSK plc | ten | 1 | 85 | 51 | 10 |
| Haleon plc | ten | 1 | 82 | 77 | 65 |
| Johnson Matthey plc | ten | 1 | 84 | 88 | 30 |
| Airbus | ten | 1 | 91 | 72 | 41 |
| Nestlé | ten | 1 | 90 | 78 | 65 |
| Anheuser-Busch InBev | ten | 1 | 90 | 64 | 39 |
| Coca-Cola Europacific Partners | ten | 1 | 88 | 62 | 30 |
| Alstom | ten | 1 | 90 | 90 | 55 |
| Saint-Gobain | ten | 1 | 95 | 57 | 52 |
| Siemens Energy AG | ten | 1 | 90 | 85 | 65 |
| Mondelez International | ten | 1 | 83 | 72 | 51 |
| Caterpillar Inc. | ten | 1 | 91 | 62 | 20 |
| Kimberly-Clark | ten | 1 | 80 | 70 | 30 |
| Grifols | ten | 1 | 76 | 98 | 31 |
| HSBC | zero | 3 | 66 | 2 | 10 |
| Lloyds Banking Group plc | zero | 3 | 60 | 2 | 10 |
| Santander Group | zero | 3 | 62 | 0 | 0 |
| Deutsche Bank | zero | 3 | 62 | 0 | 0 |
| Allianz SE | zero | 3 | 66 | 15 | 20 |
| AXA | zero | 3 | 66 | 0 | 0 |
| BAE Systems | zero | 3 | 90 | 0 | 0 |
| Mercedes-Benz Group | zero | 3 | 95 | 6 | 20 |
| BMW | zero | 3 | 95 | 2 | 20 |
| Iberdrola | zero | 3 | 83 | 1 | 0 |
| Naturgy Energy Group SA | zero | 3 | 82 | 0 | 0 |
| Industrial and Commercial Bank of China | zero | 3 | 49 | 0 | 0 |
| Sberbank | zero | 3 | 0 | 0 | 0 |
| Gazprom | zero | 3 | 0 | 0 | 0 |
| Rosneft | zero | 3 | 0 | 0 | 0 |

## Iteration 21 (2026-11-16 16:09): PASS

- Change: Extreme entity values (200+ days or a 100-day jump) left out of group figures; trend is the smaller of weighted mean and median
- Tens in Tier 1: 17/17. Zeros in Tier 3: 15/15.
- Not in the scored table: 0

| Company | Expected | Tier | Fit | Pain | Signal |
|---|---|---|---|---|---|
| Diageo | ten | 1 | 88 | 64 | 20 |
| Unilever | ten | 1 | 94 | 66 | 39 |
| Rolls-Royce | ten | 1 | 90 | 62 | 20 |
| GSK plc | ten | 1 | 85 | 51 | 10 |
| Haleon plc | ten | 1 | 82 | 76 | 63 |
| Johnson Matthey plc | ten | 1 | 84 | 88 | 30 |
| Airbus | ten | 1 | 91 | 69 | 30 |
| Nestlé | ten | 1 | 90 | 78 | 65 |
| Anheuser-Busch InBev | ten | 1 | 90 | 64 | 39 |
| Coca-Cola Europacific Partners | ten | 1 | 88 | 62 | 30 |
| Alstom | ten | 1 | 90 | 90 | 55 |
| Saint-Gobain | ten | 1 | 95 | 57 | 52 |
| Siemens Energy AG | ten | 1 | 90 | 85 | 65 |
| Mondelez International | ten | 1 | 83 | 72 | 51 |
| Caterpillar Inc. | ten | 1 | 91 | 62 | 20 |
| Kimberly-Clark | ten | 1 | 80 | 70 | 30 |
| Grifols | ten | 1 | 76 | 98 | 31 |
| HSBC | zero | 3 | 66 | 2 | 10 |
| Lloyds Banking Group plc | zero | 3 | 60 | 2 | 10 |
| Santander Group | zero | 3 | 62 | 0 | 0 |
| Deutsche Bank | zero | 3 | 62 | 0 | 0 |
| Allianz SE | zero | 3 | 66 | 15 | 20 |
| AXA | zero | 3 | 66 | 0 | 0 |
| BAE Systems | zero | 3 | 90 | 0 | 0 |
| Mercedes-Benz Group | zero | 3 | 95 | 6 | 20 |
| BMW | zero | 3 | 95 | 2 | 20 |
| Iberdrola | zero | 3 | 83 | 1 | 0 |
| Naturgy Energy Group SA | zero | 3 | 82 | 0 | 0 |
| Industrial and Commercial Bank of China | zero | 3 | 49 | 0 | 0 |
| Sberbank | zero | 3 | 0 | 0 | 0 |
| Gazprom | zero | 3 | 0 | 0 | 0 |
| Rosneft | zero | 3 | 0 | 0 | 0 |

## Iteration 22 (2026-11-16 16:14): PASS

- Change: make evals
- Tens in Tier 1: 17/17. Zeros in Tier 3: 15/15.
- Not in the scored table: 0

| Company | Expected | Tier | Fit | Pain | Signal |
|---|---|---|---|---|---|
| Diageo | ten | 1 | 88 | 64 | 20 |
| Unilever | ten | 1 | 94 | 66 | 39 |
| Rolls-Royce | ten | 1 | 90 | 62 | 20 |
| GSK plc | ten | 1 | 85 | 51 | 10 |
| Haleon plc | ten | 1 | 82 | 76 | 63 |
| Johnson Matthey plc | ten | 1 | 84 | 88 | 30 |
| Airbus | ten | 1 | 91 | 69 | 30 |
| Nestlé | ten | 1 | 90 | 78 | 65 |
| Anheuser-Busch InBev | ten | 1 | 90 | 64 | 39 |
| Coca-Cola Europacific Partners | ten | 1 | 88 | 62 | 30 |
| Alstom | ten | 1 | 90 | 90 | 55 |
| Saint-Gobain | ten | 1 | 95 | 57 | 52 |
| Siemens Energy AG | ten | 1 | 90 | 85 | 65 |
| Mondelez International | ten | 1 | 83 | 72 | 51 |
| Caterpillar Inc. | ten | 1 | 91 | 62 | 20 |
| Kimberly-Clark | ten | 1 | 80 | 70 | 30 |
| Grifols | ten | 1 | 76 | 98 | 31 |
| HSBC | zero | 3 | 66 | 2 | 10 |
| Lloyds Banking Group plc | zero | 3 | 60 | 2 | 10 |
| Santander Group | zero | 3 | 62 | 0 | 0 |
| Deutsche Bank | zero | 3 | 62 | 0 | 0 |
| Allianz SE | zero | 3 | 66 | 15 | 20 |
| AXA | zero | 3 | 66 | 0 | 0 |
| BAE Systems | zero | 3 | 90 | 0 | 0 |
| Mercedes-Benz Group | zero | 3 | 95 | 6 | 20 |
| BMW | zero | 3 | 95 | 2 | 20 |
| Iberdrola | zero | 3 | 83 | 1 | 0 |
| Naturgy Energy Group SA | zero | 3 | 82 | 0 | 0 |
| Industrial and Commercial Bank of China | zero | 3 | 49 | 0 | 0 |
| Sberbank | zero | 3 | 0 | 0 | 0 |
| Gazprom | zero | 3 | 0 | 0 | 0 |
| Rosneft | zero | 3 | 0 | 0 | 0 |

## Iteration 23 (2026-11-16 16:28): PASS

- Change: make evals
- Tens in Tier 1: 17/17. Zeros in Tier 3: 15/15.
- Not in the scored table: 0

| Company | Expected | Tier | Fit | Pain | Signal |
|---|---|---|---|---|---|
| Diageo | ten | 1 | 88 | 64 | 20 |
| Unilever | ten | 1 | 94 | 66 | 39 |
| Rolls-Royce | ten | 1 | 90 | 62 | 20 |
| GSK plc | ten | 1 | 85 | 51 | 10 |
| Haleon plc | ten | 1 | 82 | 76 | 63 |
| Johnson Matthey plc | ten | 1 | 84 | 88 | 30 |
| Airbus | ten | 1 | 91 | 69 | 30 |
| Nestlé | ten | 1 | 90 | 78 | 65 |
| Anheuser-Busch InBev | ten | 1 | 90 | 64 | 39 |
| Coca-Cola Europacific Partners | ten | 1 | 88 | 62 | 30 |
| Alstom | ten | 1 | 90 | 90 | 55 |
| Saint-Gobain | ten | 1 | 95 | 57 | 52 |
| Siemens Energy AG | ten | 1 | 90 | 85 | 65 |
| Mondelez International | ten | 1 | 83 | 72 | 51 |
| Caterpillar Inc. | ten | 1 | 91 | 62 | 20 |
| Kimberly-Clark | ten | 1 | 80 | 70 | 30 |
| Grifols | ten | 1 | 76 | 98 | 31 |
| HSBC | zero | 3 | 66 | 2 | 10 |
| Lloyds Banking Group plc | zero | 3 | 60 | 2 | 10 |
| Santander Group | zero | 3 | 62 | 0 | 0 |
| Deutsche Bank | zero | 3 | 62 | 0 | 0 |
| Allianz SE | zero | 3 | 66 | 15 | 20 |
| AXA | zero | 3 | 66 | 0 | 0 |
| BAE Systems | zero | 3 | 90 | 0 | 0 |
| Mercedes-Benz Group | zero | 3 | 95 | 6 | 20 |
| BMW | zero | 3 | 95 | 2 | 20 |
| Iberdrola | zero | 3 | 83 | 1 | 0 |
| Naturgy Energy Group SA | zero | 3 | 82 | 0 | 0 |
| Industrial and Commercial Bank of China | zero | 3 | 49 | 0 | 0 |
| Sberbank | zero | 3 | 0 | 0 | 0 |
| Gazprom | zero | 3 | 0 | 0 | 0 |
| Rosneft | zero | 3 | 0 | 0 | 0 |

## Iteration 24 (2026-11-16 20:55): PASS

- Change: phase 12 wiring
- Tens in Tier 1: 17/17. Zeros in Tier 3: 15/15.
- Not in the scored table: 0

| Company | Expected | Tier | Fit | Pain | Signal |
|---|---|---|---|---|---|
| Diageo | ten | 1 | 88 | 64 | 20 |
| Unilever | ten | 1 | 94 | 66 | 39 |
| Rolls-Royce | ten | 1 | 90 | 62 | 35 |
| GSK plc | ten | 1 | 85 | 51 | 15 |
| Haleon plc | ten | 1 | 82 | 76 | 63 |
| Johnson Matthey plc | ten | 1 | 84 | 88 | 30 |
| Airbus | ten | 1 | 91 | 69 | 40 |
| Nestlé | ten | 1 | 90 | 78 | 65 |
| Anheuser-Busch InBev | ten | 1 | 90 | 64 | 39 |
| Coca-Cola Europacific Partners | ten | 1 | 88 | 62 | 35 |
| Alstom | ten | 1 | 90 | 90 | 55 |
| Saint-Gobain | ten | 1 | 95 | 57 | 62 |
| Siemens Energy AG | ten | 1 | 90 | 85 | 70 |
| Mondelez International | ten | 1 | 83 | 72 | 66 |
| Caterpillar Inc. | ten | 1 | 91 | 62 | 30 |
| Kimberly-Clark | ten | 1 | 80 | 70 | 45 |
| Grifols | ten | 1 | 76 | 98 | 31 |
| HSBC | zero | 3 | 66 | 2 | 10 |
| Lloyds Banking Group plc | zero | 3 | 60 | 2 | 10 |
| Santander Group | zero | 3 | 62 | 0 | 0 |
| Deutsche Bank | zero | 3 | 62 | 0 | 0 |
| Allianz SE | zero | 3 | 66 | 15 | 20 |
| AXA | zero | 3 | 66 | 0 | 0 |
| BAE Systems | zero | 3 | 90 | 0 | 0 |
| Mercedes-Benz Group | zero | 3 | 95 | 6 | 20 |
| BMW | zero | 3 | 95 | 2 | 20 |
| Iberdrola | zero | 3 | 83 | 1 | 0 |
| Naturgy Energy Group SA | zero | 3 | 82 | 0 | 0 |
| Industrial and Commercial Bank of China | zero | 3 | 49 | 0 | 0 |
| Sberbank | zero | 3 | 0 | 0 | 0 |
| Gazprom | zero | 3 | 0 | 0 | 0 |
| Rosneft | zero | 3 | 0 | 0 | 0 |

## Iteration 25 (2026-11-16 20:57): PASS

- Change: phase 12 wiring
- Tens in Tier 1: 17/17. Zeros in Tier 3: 15/15.
- Not in the scored table: 0

| Company | Expected | Tier | Fit | Pain | Signal |
|---|---|---|---|---|---|
| Diageo | ten | 1 | 88 | 64 | 20 |
| Unilever | ten | 1 | 94 | 66 | 39 |
| Rolls-Royce | ten | 1 | 90 | 62 | 35 |
| GSK plc | ten | 1 | 85 | 51 | 10 |
| Haleon plc | ten | 1 | 82 | 76 | 63 |
| Johnson Matthey plc | ten | 1 | 84 | 88 | 30 |
| Airbus | ten | 1 | 91 | 69 | 40 |
| Nestlé | ten | 1 | 90 | 78 | 65 |
| Anheuser-Busch InBev | ten | 1 | 90 | 64 | 39 |
| Coca-Cola Europacific Partners | ten | 1 | 88 | 62 | 30 |
| Alstom | ten | 1 | 90 | 90 | 55 |
| Saint-Gobain | ten | 1 | 95 | 57 | 62 |
| Siemens Energy AG | ten | 1 | 90 | 85 | 70 |
| Mondelez International | ten | 1 | 83 | 72 | 61 |
| Caterpillar Inc. | ten | 1 | 91 | 62 | 30 |
| Kimberly-Clark | ten | 1 | 80 | 70 | 45 |
| Grifols | ten | 1 | 76 | 98 | 31 |
| HSBC | zero | 3 | 66 | 2 | 10 |
| Lloyds Banking Group plc | zero | 3 | 60 | 2 | 10 |
| Santander Group | zero | 3 | 62 | 0 | 0 |
| Deutsche Bank | zero | 3 | 62 | 0 | 0 |
| Allianz SE | zero | 3 | 66 | 15 | 20 |
| AXA | zero | 3 | 66 | 0 | 0 |
| BAE Systems | zero | 3 | 90 | 0 | 0 |
| Mercedes-Benz Group | zero | 3 | 95 | 6 | 20 |
| BMW | zero | 3 | 95 | 2 | 20 |
| Iberdrola | zero | 3 | 83 | 1 | 0 |
| Naturgy Energy Group SA | zero | 3 | 82 | 0 | 0 |
| Industrial and Commercial Bank of China | zero | 3 | 49 | 0 | 0 |
| Sberbank | zero | 3 | 0 | 0 | 0 |
| Gazprom | zero | 3 | 0 | 0 | 0 |
| Rosneft | zero | 3 | 0 | 0 | 0 |

## Iteration 26 (2026-11-16 21:04): PASS

- Change: phase 12: parent overrides
- Tens in Tier 1: 17/17. Zeros in Tier 3: 15/15.
- Not in the scored table: 0

| Company | Expected | Tier | Fit | Pain | Signal |
|---|---|---|---|---|---|
| Diageo | ten | 1 | 88 | 64 | 20 |
| Unilever | ten | 1 | 94 | 66 | 39 |
| Rolls-Royce | ten | 1 | 90 | 62 | 35 |
| GSK plc | ten | 1 | 85 | 51 | 10 |
| Haleon plc | ten | 1 | 82 | 76 | 63 |
| Johnson Matthey plc | ten | 1 | 84 | 88 | 30 |
| Airbus | ten | 1 | 91 | 69 | 40 |
| Nestlé | ten | 1 | 90 | 78 | 65 |
| Anheuser-Busch InBev | ten | 1 | 90 | 64 | 39 |
| Coca-Cola Europacific Partners | ten | 1 | 88 | 62 | 30 |
| Alstom | ten | 1 | 90 | 90 | 55 |
| Saint-Gobain | ten | 1 | 95 | 57 | 62 |
| Siemens Energy AG | ten | 1 | 90 | 85 | 70 |
| Mondelez International | ten | 1 | 83 | 72 | 61 |
| Caterpillar Inc. | ten | 1 | 91 | 62 | 30 |
| Kimberly-Clark | ten | 1 | 80 | 70 | 45 |
| Grifols | ten | 1 | 76 | 98 | 31 |
| HSBC | zero | 3 | 66 | 2 | 10 |
| Lloyds Banking Group plc | zero | 3 | 60 | 2 | 10 |
| Santander Group | zero | 3 | 62 | 0 | 0 |
| Deutsche Bank | zero | 3 | 62 | 0 | 0 |
| Allianz SE | zero | 3 | 66 | 15 | 20 |
| AXA | zero | 3 | 66 | 0 | 0 |
| BAE Systems | zero | 3 | 90 | 0 | 0 |
| Mercedes-Benz Group | zero | 3 | 95 | 6 | 20 |
| BMW | zero | 3 | 95 | 2 | 20 |
| Iberdrola | zero | 3 | 83 | 1 | 0 |
| Naturgy Energy Group SA | zero | 3 | 82 | 0 | 0 |
| Industrial and Commercial Bank of China | zero | 3 | 49 | 0 | 0 |
| Sberbank | zero | 3 | 0 | 0 | 0 |
| Gazprom | zero | 3 | 0 | 0 | 0 |
| Rosneft | zero | 3 | 0 | 0 | 0 |

## Iteration 27 (2026-11-16 21:04): PASS

- Change: phase 12: parent overrides
- Tens in Tier 1: 17/17. Zeros in Tier 3: 15/15.
- Not in the scored table: 0

| Company | Expected | Tier | Fit | Pain | Signal |
|---|---|---|---|---|---|
| Diageo | ten | 1 | 88 | 64 | 20 |
| Unilever | ten | 1 | 94 | 66 | 39 |
| Rolls-Royce | ten | 1 | 90 | 62 | 35 |
| GSK plc | ten | 1 | 85 | 51 | 10 |
| Haleon plc | ten | 1 | 82 | 76 | 63 |
| Johnson Matthey plc | ten | 1 | 84 | 88 | 30 |
| Airbus | ten | 1 | 91 | 69 | 40 |
| Nestlé | ten | 1 | 90 | 78 | 65 |
| Anheuser-Busch InBev | ten | 1 | 90 | 64 | 39 |
| Coca-Cola Europacific Partners | ten | 1 | 88 | 62 | 30 |
| Alstom | ten | 1 | 90 | 90 | 55 |
| Saint-Gobain | ten | 1 | 95 | 57 | 62 |
| Siemens Energy AG | ten | 1 | 90 | 85 | 70 |
| Mondelez International | ten | 1 | 83 | 72 | 61 |
| Caterpillar Inc. | ten | 1 | 91 | 62 | 30 |
| Kimberly-Clark | ten | 1 | 80 | 70 | 45 |
| Grifols | ten | 1 | 76 | 98 | 31 |
| HSBC | zero | 3 | 66 | 2 | 10 |
| Lloyds Banking Group plc | zero | 3 | 60 | 2 | 10 |
| Santander Group | zero | 3 | 62 | 0 | 0 |
| Deutsche Bank | zero | 3 | 62 | 0 | 0 |
| Allianz SE | zero | 3 | 66 | 15 | 20 |
| AXA | zero | 3 | 66 | 0 | 0 |
| BAE Systems | zero | 3 | 90 | 0 | 0 |
| Mercedes-Benz Group | zero | 3 | 95 | 6 | 20 |
| BMW | zero | 3 | 95 | 2 | 20 |
| Iberdrola | zero | 3 | 83 | 1 | 0 |
| Naturgy Energy Group SA | zero | 3 | 82 | 0 | 0 |
| Industrial and Commercial Bank of China | zero | 3 | 49 | 0 | 0 |
| Sberbank | zero | 3 | 0 | 0 | 0 |
| Gazprom | zero | 3 | 0 | 0 | 0 |
| Rosneft | zero | 3 | 0 | 0 | 0 |

## Iteration 28 (2026-11-16 21:16): PASS

- Change: make evals
- Tens in Tier 1: 17/17. Zeros in Tier 3: 15/15.
- Not in the scored table: 0

| Company | Expected | Tier | Fit | Pain | Signal |
|---|---|---|---|---|---|
| Diageo | ten | 1 | 88 | 64 | 20 |
| Unilever | ten | 1 | 94 | 66 | 39 |
| Rolls-Royce | ten | 1 | 90 | 62 | 35 |
| GSK plc | ten | 1 | 85 | 51 | 10 |
| Haleon plc | ten | 1 | 82 | 76 | 63 |
| Johnson Matthey plc | ten | 1 | 84 | 88 | 30 |
| Airbus | ten | 1 | 91 | 69 | 40 |
| Nestlé | ten | 1 | 90 | 78 | 65 |
| Anheuser-Busch InBev | ten | 1 | 90 | 64 | 39 |
| Coca-Cola Europacific Partners | ten | 1 | 88 | 62 | 30 |
| Alstom | ten | 1 | 90 | 90 | 55 |
| Saint-Gobain | ten | 1 | 95 | 57 | 62 |
| Siemens Energy AG | ten | 1 | 90 | 85 | 70 |
| Mondelez International | ten | 1 | 83 | 72 | 61 |
| Caterpillar Inc. | ten | 1 | 91 | 62 | 30 |
| Kimberly-Clark | ten | 1 | 80 | 70 | 45 |
| Grifols | ten | 1 | 76 | 98 | 31 |
| HSBC | zero | 3 | 66 | 2 | 10 |
| Lloyds Banking Group plc | zero | 3 | 60 | 2 | 10 |
| Santander Group | zero | 3 | 62 | 0 | 0 |
| Deutsche Bank | zero | 3 | 62 | 0 | 0 |
| Allianz SE | zero | 3 | 66 | 15 | 20 |
| AXA | zero | 3 | 66 | 0 | 0 |
| BAE Systems | zero | 3 | 90 | 0 | 0 |
| Mercedes-Benz Group | zero | 3 | 95 | 6 | 20 |
| BMW | zero | 3 | 95 | 2 | 20 |
| Iberdrola | zero | 3 | 83 | 1 | 0 |
| Naturgy Energy Group SA | zero | 3 | 82 | 0 | 0 |
| Industrial and Commercial Bank of China | zero | 3 | 49 | 0 | 0 |
| Sberbank | zero | 3 | 0 | 0 | 0 |
| Gazprom | zero | 3 | 0 | 0 | 0 |
| Rosneft | zero | 3 | 0 | 0 | 0 |

## Iteration 29 (2026-11-16 21:19): PASS

- Change: make evals
- Tens in Tier 1: 17/17. Zeros in Tier 3: 15/15.
- Not in the scored table: 0

| Company | Expected | Tier | Fit | Pain | Signal |
|---|---|---|---|---|---|
| Diageo | ten | 1 | 88 | 64 | 20 |
| Unilever | ten | 1 | 94 | 66 | 39 |
| Rolls-Royce | ten | 1 | 90 | 62 | 35 |
| GSK plc | ten | 1 | 85 | 51 | 10 |
| Haleon plc | ten | 1 | 82 | 76 | 63 |
| Johnson Matthey plc | ten | 1 | 84 | 88 | 30 |
| Airbus | ten | 1 | 91 | 69 | 40 |
| Nestlé | ten | 1 | 90 | 78 | 65 |
| Anheuser-Busch InBev | ten | 1 | 90 | 64 | 39 |
| Coca-Cola Europacific Partners | ten | 1 | 88 | 62 | 30 |
| Alstom | ten | 1 | 90 | 90 | 55 |
| Saint-Gobain | ten | 1 | 95 | 57 | 62 |
| Siemens Energy AG | ten | 1 | 90 | 85 | 70 |
| Mondelez International | ten | 1 | 83 | 72 | 61 |
| Caterpillar Inc. | ten | 1 | 91 | 62 | 30 |
| Kimberly-Clark | ten | 1 | 80 | 70 | 45 |
| Grifols | ten | 1 | 76 | 98 | 31 |
| HSBC | zero | 3 | 66 | 2 | 10 |
| Lloyds Banking Group plc | zero | 3 | 60 | 2 | 10 |
| Santander Group | zero | 3 | 62 | 0 | 0 |
| Deutsche Bank | zero | 3 | 62 | 0 | 0 |
| Allianz SE | zero | 3 | 66 | 15 | 20 |
| AXA | zero | 3 | 66 | 0 | 0 |
| BAE Systems | zero | 3 | 90 | 0 | 0 |
| Mercedes-Benz Group | zero | 3 | 95 | 6 | 20 |
| BMW | zero | 3 | 95 | 2 | 20 |
| Iberdrola | zero | 3 | 83 | 1 | 0 |
| Naturgy Energy Group SA | zero | 3 | 82 | 0 | 0 |
| Industrial and Commercial Bank of China | zero | 3 | 49 | 0 | 0 |
| Sberbank | zero | 3 | 0 | 0 | 0 |
| Gazprom | zero | 3 | 0 | 0 | 0 |
| Rosneft | zero | 3 | 0 | 0 | 0 |

## Iteration 30 (2026-11-16 21:28): PASS

- Change: phase 12 critic fixes
- Tens in Tier 1: 17/17. Zeros in Tier 3: 15/15.
- Not in the scored table: 0

| Company | Expected | Tier | Fit | Pain | Signal |
|---|---|---|---|---|---|
| Diageo | ten | 1 | 88 | 64 | 20 |
| Unilever | ten | 1 | 94 | 66 | 39 |
| Rolls-Royce | ten | 1 | 90 | 62 | 25 |
| GSK plc | ten | 1 | 85 | 51 | 10 |
| Haleon plc | ten | 1 | 82 | 76 | 63 |
| Johnson Matthey plc | ten | 1 | 84 | 88 | 30 |
| Airbus | ten | 1 | 91 | 69 | 30 |
| Nestlé | ten | 1 | 90 | 78 | 65 |
| Anheuser-Busch InBev | ten | 1 | 90 | 64 | 39 |
| Coca-Cola Europacific Partners | ten | 1 | 88 | 62 | 30 |
| Alstom | ten | 1 | 90 | 90 | 55 |
| Saint-Gobain | ten | 1 | 95 | 57 | 52 |
| Siemens Energy AG | ten | 1 | 90 | 85 | 70 |
| Mondelez International | ten | 1 | 83 | 72 | 51 |
| Caterpillar Inc. | ten | 1 | 91 | 62 | 20 |
| Kimberly-Clark | ten | 1 | 80 | 70 | 35 |
| Grifols | ten | 1 | 76 | 98 | 31 |
| HSBC | zero | 3 | 66 | 2 | 10 |
| Lloyds Banking Group plc | zero | 3 | 60 | 2 | 10 |
| Santander Group | zero | 3 | 62 | 0 | 0 |
| Deutsche Bank | zero | 3 | 62 | 0 | 0 |
| Allianz SE | zero | 3 | 66 | 15 | 20 |
| AXA | zero | 3 | 66 | 0 | 0 |
| BAE Systems | zero | 3 | 90 | 0 | 0 |
| Mercedes-Benz Group | zero | 3 | 95 | 6 | 20 |
| BMW | zero | 3 | 95 | 2 | 20 |
| Iberdrola | zero | 3 | 83 | 1 | 0 |
| Naturgy Energy Group SA | zero | 3 | 82 | 0 | 0 |
| Industrial and Commercial Bank of China | zero | 3 | 49 | 0 | 0 |
| Sberbank | zero | 3 | 0 | 0 | 0 |
| Gazprom | zero | 3 | 0 | 0 | 0 |
| Rosneft | zero | 3 | 0 | 0 | 0 |

## Iteration 31 (2026-11-16 21:34): PASS

- Change: make evals
- Tens in Tier 1: 17/17. Zeros in Tier 3: 15/15.
- Not in the scored table: 0

| Company | Expected | Tier | Fit | Pain | Signal |
|---|---|---|---|---|---|
| Diageo | ten | 1 | 88 | 64 | 20 |
| Unilever | ten | 1 | 94 | 66 | 39 |
| Rolls-Royce | ten | 1 | 90 | 62 | 25 |
| GSK plc | ten | 1 | 85 | 51 | 10 |
| Haleon plc | ten | 1 | 82 | 76 | 63 |
| Johnson Matthey plc | ten | 1 | 84 | 88 | 30 |
| Airbus | ten | 1 | 91 | 69 | 30 |
| Nestlé | ten | 1 | 90 | 78 | 65 |
| Anheuser-Busch InBev | ten | 1 | 90 | 64 | 39 |
| Coca-Cola Europacific Partners | ten | 1 | 88 | 62 | 30 |
| Alstom | ten | 1 | 90 | 90 | 55 |
| Saint-Gobain | ten | 1 | 95 | 57 | 52 |
| Siemens Energy AG | ten | 1 | 90 | 85 | 70 |
| Mondelez International | ten | 1 | 83 | 72 | 51 |
| Caterpillar Inc. | ten | 1 | 91 | 62 | 20 |
| Kimberly-Clark | ten | 1 | 80 | 70 | 35 |
| Grifols | ten | 1 | 76 | 98 | 31 |
| HSBC | zero | 3 | 66 | 2 | 10 |
| Lloyds Banking Group plc | zero | 3 | 60 | 2 | 10 |
| Santander Group | zero | 3 | 62 | 0 | 0 |
| Deutsche Bank | zero | 3 | 62 | 0 | 0 |
| Allianz SE | zero | 3 | 66 | 15 | 20 |
| AXA | zero | 3 | 66 | 0 | 0 |
| BAE Systems | zero | 3 | 90 | 0 | 0 |
| Mercedes-Benz Group | zero | 3 | 95 | 6 | 20 |
| BMW | zero | 3 | 95 | 2 | 20 |
| Iberdrola | zero | 3 | 83 | 1 | 0 |
| Naturgy Energy Group SA | zero | 3 | 82 | 0 | 0 |
| Industrial and Commercial Bank of China | zero | 3 | 49 | 0 | 0 |
| Sberbank | zero | 3 | 0 | 0 | 0 |
| Gazprom | zero | 3 | 0 | 0 | 0 |
| Rosneft | zero | 3 | 0 | 0 | 0 |

## Iteration 32 (2026-11-16 21:37): PASS

- Change: make evals
- Tens in Tier 1: 17/17. Zeros in Tier 3: 15/15.
- Not in the scored table: 0

| Company | Expected | Tier | Fit | Pain | Signal |
|---|---|---|---|---|---|
| Diageo | ten | 1 | 88 | 64 | 20 |
| Unilever | ten | 1 | 94 | 66 | 39 |
| Rolls-Royce | ten | 1 | 90 | 62 | 25 |
| GSK plc | ten | 1 | 85 | 51 | 10 |
| Haleon plc | ten | 1 | 82 | 76 | 63 |
| Johnson Matthey plc | ten | 1 | 84 | 88 | 30 |
| Airbus | ten | 1 | 91 | 69 | 30 |
| Nestlé | ten | 1 | 90 | 78 | 65 |
| Anheuser-Busch InBev | ten | 1 | 90 | 64 | 39 |
| Coca-Cola Europacific Partners | ten | 1 | 88 | 62 | 30 |
| Alstom | ten | 1 | 90 | 90 | 55 |
| Saint-Gobain | ten | 1 | 95 | 57 | 52 |
| Siemens Energy AG | ten | 1 | 90 | 85 | 70 |
| Mondelez International | ten | 1 | 83 | 72 | 51 |
| Caterpillar Inc. | ten | 1 | 91 | 62 | 20 |
| Kimberly-Clark | ten | 1 | 80 | 70 | 35 |
| Grifols | ten | 1 | 76 | 98 | 31 |
| HSBC | zero | 3 | 66 | 2 | 10 |
| Lloyds Banking Group plc | zero | 3 | 60 | 2 | 10 |
| Santander Group | zero | 3 | 62 | 0 | 0 |
| Deutsche Bank | zero | 3 | 62 | 0 | 0 |
| Allianz SE | zero | 3 | 66 | 15 | 20 |
| AXA | zero | 3 | 66 | 0 | 0 |
| BAE Systems | zero | 3 | 90 | 0 | 0 |
| Mercedes-Benz Group | zero | 3 | 95 | 6 | 20 |
| BMW | zero | 3 | 95 | 2 | 20 |
| Iberdrola | zero | 3 | 83 | 1 | 0 |
| Naturgy Energy Group SA | zero | 3 | 82 | 0 | 0 |
| Industrial and Commercial Bank of China | zero | 3 | 49 | 0 | 0 |
| Sberbank | zero | 3 | 0 | 0 | 0 |
| Gazprom | zero | 3 | 0 | 0 | 0 |
| Rosneft | zero | 3 | 0 | 0 | 0 |

## Iteration 33 (2026-11-16 21:47): PASS

- Change: make evals
- Tens in Tier 1: 17/17. Zeros in Tier 3: 15/15.
- Not in the scored table: 0

| Company | Expected | Tier | Fit | Pain | Signal |
|---|---|---|---|---|---|
| Diageo | ten | 1 | 88 | 64 | 20 |
| Unilever | ten | 1 | 94 | 66 | 39 |
| Rolls-Royce | ten | 1 | 90 | 62 | 25 |
| GSK plc | ten | 1 | 85 | 51 | 10 |
| Haleon plc | ten | 1 | 82 | 76 | 63 |
| Johnson Matthey plc | ten | 1 | 84 | 88 | 30 |
| Airbus | ten | 1 | 91 | 69 | 30 |
| Nestlé | ten | 1 | 90 | 78 | 65 |
| Anheuser-Busch InBev | ten | 1 | 90 | 64 | 39 |
| Coca-Cola Europacific Partners | ten | 1 | 88 | 62 | 30 |
| Alstom | ten | 1 | 90 | 90 | 55 |
| Saint-Gobain | ten | 1 | 95 | 57 | 52 |
| Siemens Energy AG | ten | 1 | 90 | 85 | 70 |
| Mondelez International | ten | 1 | 83 | 72 | 51 |
| Caterpillar Inc. | ten | 1 | 91 | 62 | 20 |
| Kimberly-Clark | ten | 1 | 80 | 70 | 35 |
| Grifols | ten | 1 | 76 | 98 | 31 |
| HSBC | zero | 3 | 66 | 2 | 10 |
| Lloyds Banking Group plc | zero | 3 | 60 | 2 | 10 |
| Santander Group | zero | 3 | 62 | 0 | 0 |
| Deutsche Bank | zero | 3 | 62 | 0 | 0 |
| Allianz SE | zero | 3 | 66 | 15 | 20 |
| AXA | zero | 3 | 66 | 0 | 0 |
| BAE Systems | zero | 3 | 90 | 0 | 0 |
| Mercedes-Benz Group | zero | 3 | 95 | 6 | 20 |
| BMW | zero | 3 | 95 | 2 | 20 |
| Iberdrola | zero | 3 | 83 | 1 | 0 |
| Naturgy Energy Group SA | zero | 3 | 82 | 0 | 0 |
| Industrial and Commercial Bank of China | zero | 3 | 49 | 0 | 0 |
| Sberbank | zero | 3 | 0 | 0 | 0 |
| Gazprom | zero | 3 | 0 | 0 | 0 |
| Rosneft | zero | 3 | 0 | 0 | 0 |

## Iteration 34 (2026-11-16 21:49): PASS

- Change: make evals
- Tens in Tier 1: 17/17. Zeros in Tier 3: 15/15.
- Not in the scored table: 0

| Company | Expected | Tier | Fit | Pain | Signal |
|---|---|---|---|---|---|
| Diageo | ten | 1 | 88 | 64 | 20 |
| Unilever | ten | 1 | 94 | 66 | 39 |
| Rolls-Royce | ten | 1 | 90 | 62 | 25 |
| GSK plc | ten | 1 | 85 | 51 | 10 |
| Haleon plc | ten | 1 | 82 | 76 | 63 |
| Johnson Matthey plc | ten | 1 | 84 | 88 | 30 |
| Airbus | ten | 1 | 91 | 69 | 30 |
| Nestlé | ten | 1 | 90 | 78 | 65 |
| Anheuser-Busch InBev | ten | 1 | 90 | 64 | 39 |
| Coca-Cola Europacific Partners | ten | 1 | 88 | 62 | 30 |
| Alstom | ten | 1 | 90 | 90 | 55 |
| Saint-Gobain | ten | 1 | 95 | 57 | 52 |
| Siemens Energy AG | ten | 1 | 90 | 85 | 70 |
| Mondelez International | ten | 1 | 83 | 72 | 51 |
| Caterpillar Inc. | ten | 1 | 91 | 62 | 20 |
| Kimberly-Clark | ten | 1 | 80 | 70 | 35 |
| Grifols | ten | 1 | 76 | 98 | 31 |
| HSBC | zero | 3 | 66 | 2 | 10 |
| Lloyds Banking Group plc | zero | 3 | 60 | 2 | 10 |
| Santander Group | zero | 3 | 62 | 0 | 0 |
| Deutsche Bank | zero | 3 | 62 | 0 | 0 |
| Allianz SE | zero | 3 | 66 | 15 | 20 |
| AXA | zero | 3 | 66 | 0 | 0 |
| BAE Systems | zero | 3 | 90 | 0 | 0 |
| Mercedes-Benz Group | zero | 3 | 95 | 6 | 20 |
| BMW | zero | 3 | 95 | 2 | 20 |
| Iberdrola | zero | 3 | 83 | 1 | 0 |
| Naturgy Energy Group SA | zero | 3 | 82 | 0 | 0 |
| Industrial and Commercial Bank of China | zero | 3 | 49 | 0 | 0 |
| Sberbank | zero | 3 | 0 | 0 | 0 |
| Gazprom | zero | 3 | 0 | 0 | 0 |
| Rosneft | zero | 3 | 0 | 0 | 0 |

## Iteration 35 (2026-11-17 13:23): PASS

- Change: DACH slice
- Tens in Tier 1: 17/17. Zeros in Tier 3: 15/15.
- Not in the scored table: 0

| Company | Expected | Tier | Fit | Pain | Signal |
|---|---|---|---|---|---|
| Diageo | ten | 1 | 88 | 64 | 20 |
| Unilever | ten | 1 | 94 | 66 | 39 |
| Rolls-Royce | ten | 1 | 90 | 62 | 25 |
| GSK plc | ten | 1 | 85 | 51 | 10 |
| Haleon plc | ten | 1 | 82 | 76 | 63 |
| Johnson Matthey plc | ten | 1 | 84 | 88 | 30 |
| Airbus | ten | 1 | 91 | 69 | 30 |
| Nestlé | ten | 1 | 90 | 78 | 65 |
| Anheuser-Busch InBev | ten | 1 | 90 | 64 | 39 |
| Coca-Cola Europacific Partners | ten | 1 | 88 | 62 | 30 |
| Alstom | ten | 1 | 90 | 90 | 55 |
| Saint-Gobain | ten | 1 | 95 | 57 | 52 |
| Siemens Energy AG | ten | 1 | 90 | 85 | 70 |
| Mondelez International | ten | 1 | 83 | 72 | 51 |
| Caterpillar Inc. | ten | 1 | 91 | 62 | 20 |
| Kimberly-Clark | ten | 1 | 80 | 70 | 35 |
| Grifols | ten | 1 | 76 | 98 | 31 |
| HSBC | zero | 3 | 66 | 2 | 10 |
| Lloyds Banking Group plc | zero | 3 | 60 | 2 | 10 |
| Santander Group | zero | 3 | 62 | 0 | 0 |
| Deutsche Bank | zero | 3 | 62 | 0 | 0 |
| Allianz SE | zero | 3 | 66 | 15 | 20 |
| AXA | zero | 3 | 66 | 0 | 0 |
| BAE Systems | zero | 3 | 90 | 0 | 0 |
| Mercedes-Benz Group | zero | 3 | 95 | 6 | 20 |
| BMW | zero | 3 | 95 | 2 | 20 |
| Iberdrola | zero | 3 | 83 | 1 | 0 |
| Naturgy Energy Group SA | zero | 3 | 82 | 0 | 0 |
| Industrial and Commercial Bank of China | zero | 3 | 49 | 0 | 0 |
| Sberbank | zero | 3 | 0 | 0 | 0 |
| Gazprom | zero | 3 | 0 | 0 | 0 |
| Rosneft | zero | 3 | 0 | 0 | 0 |

## Iteration 36 (2026-11-17 13:23): PASS

- Change: DACH slice
- Tens in Tier 1: 17/17. Zeros in Tier 3: 15/15.
- Not in the scored table: 0

| Company | Expected | Tier | Fit | Pain | Signal |
|---|---|---|---|---|---|
| Diageo | ten | 1 | 88 | 64 | 20 |
| Unilever | ten | 1 | 94 | 66 | 39 |
| Rolls-Royce | ten | 1 | 90 | 62 | 25 |
| GSK plc | ten | 1 | 85 | 51 | 10 |
| Haleon plc | ten | 1 | 82 | 76 | 63 |
| Johnson Matthey plc | ten | 1 | 84 | 88 | 30 |
| Airbus | ten | 1 | 91 | 69 | 30 |
| Nestlé | ten | 1 | 90 | 78 | 65 |
| Anheuser-Busch InBev | ten | 1 | 90 | 64 | 39 |
| Coca-Cola Europacific Partners | ten | 1 | 88 | 62 | 30 |
| Alstom | ten | 1 | 90 | 90 | 55 |
| Saint-Gobain | ten | 1 | 95 | 57 | 52 |
| Siemens Energy AG | ten | 1 | 90 | 85 | 70 |
| Mondelez International | ten | 1 | 83 | 72 | 51 |
| Caterpillar Inc. | ten | 1 | 91 | 62 | 20 |
| Kimberly-Clark | ten | 1 | 80 | 70 | 35 |
| Grifols | ten | 1 | 76 | 98 | 31 |
| HSBC | zero | 3 | 66 | 2 | 10 |
| Lloyds Banking Group plc | zero | 3 | 60 | 2 | 10 |
| Santander Group | zero | 3 | 62 | 0 | 0 |
| Deutsche Bank | zero | 3 | 62 | 0 | 0 |
| Allianz SE | zero | 3 | 66 | 15 | 20 |
| AXA | zero | 3 | 66 | 0 | 0 |
| BAE Systems | zero | 3 | 90 | 0 | 0 |
| Mercedes-Benz Group | zero | 3 | 95 | 6 | 20 |
| BMW | zero | 3 | 95 | 2 | 20 |
| Iberdrola | zero | 3 | 83 | 1 | 0 |
| Naturgy Energy Group SA | zero | 3 | 82 | 0 | 0 |
| Industrial and Commercial Bank of China | zero | 3 | 49 | 0 | 0 |
| Sberbank | zero | 3 | 0 | 0 | 0 |
| Gazprom | zero | 3 | 0 | 0 | 0 |
| Rosneft | zero | 3 | 0 | 0 | 0 |

## Iteration 37 (2026-11-17 14:49): PASS

- Change: DACH slice
- Tens in Tier 1: 17/17. Zeros in Tier 3: 15/15.
- Not in the scored table: 0

| Company | Expected | Tier | Fit | Pain | Signal |
|---|---|---|---|---|---|
| Diageo | ten | 1 | 88 | 64 | 20 |
| Unilever | ten | 1 | 94 | 66 | 39 |
| Rolls-Royce | ten | 1 | 90 | 62 | 25 |
| GSK plc | ten | 1 | 85 | 51 | 10 |
| Haleon plc | ten | 1 | 82 | 76 | 63 |
| Johnson Matthey plc | ten | 1 | 84 | 88 | 30 |
| Airbus | ten | 1 | 91 | 69 | 30 |
| Nestlé | ten | 1 | 90 | 78 | 65 |
| Anheuser-Busch InBev | ten | 1 | 90 | 64 | 39 |
| Coca-Cola Europacific Partners | ten | 1 | 88 | 62 | 30 |
| Alstom | ten | 1 | 90 | 90 | 55 |
| Saint-Gobain | ten | 1 | 95 | 57 | 52 |
| Siemens Energy AG | ten | 1 | 90 | 85 | 70 |
| Mondelez International | ten | 1 | 83 | 72 | 51 |
| Caterpillar Inc. | ten | 1 | 91 | 62 | 20 |
| Kimberly-Clark | ten | 1 | 80 | 70 | 35 |
| Grifols | ten | 1 | 76 | 98 | 31 |
| HSBC | zero | 3 | 66 | 2 | 10 |
| Lloyds Banking Group plc | zero | 3 | 60 | 2 | 10 |
| Santander Group | zero | 3 | 62 | 0 | 0 |
| Deutsche Bank | zero | 3 | 62 | 0 | 0 |
| Allianz SE | zero | 3 | 66 | 15 | 20 |
| AXA | zero | 3 | 66 | 0 | 0 |
| BAE Systems | zero | 3 | 90 | 0 | 0 |
| Mercedes-Benz Group | zero | 3 | 95 | 6 | 20 |
| BMW | zero | 3 | 95 | 2 | 20 |
| Iberdrola | zero | 3 | 83 | 1 | 0 |
| Naturgy Energy Group SA | zero | 3 | 82 | 0 | 0 |
| Industrial and Commercial Bank of China | zero | 3 | 49 | 0 | 0 |
| Sberbank | zero | 3 | 0 | 0 | 0 |
| Gazprom | zero | 3 | 0 | 0 | 0 |
| Rosneft | zero | 3 | 0 | 0 | 0 |
