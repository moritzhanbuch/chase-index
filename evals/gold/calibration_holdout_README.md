# Calibration holdout gold set (40 companies)

File: `evals/gold/calibration_holdout.csv`. Built by the `qa-holdout` agent on 2026-11-16, blind to the model's scores. 20 expected "ten" (Tier 1) and 20 expected "zero" (Tier 3). No agreement with the model was computed here. That is a separate step for a different agent.

## Blindness

Not opened: `data/processed/companies.*`, `data/processed/scores.*`, `outputs/targets/`, `outputs/queue/`, `evals/gold/calibration.csv`, `evals/reports/calibration.md`, `config/assumptions.yaml`, any scoring code, and the project's own sector or rationale tables (`data/interim/sector_llm.csv`, `data/processed/rationales_llm.csv`, `top50.csv`, `top200.csv`).

Looked at (raw evidence only):
- `tmp/holdout_candidates.csv` (1,877 candidates; the existing calibration set is already excluded)
- `data/processed/uk_payment_practices.parquet` (official GOV.UK statutory reports, one row per legal entity per period)
- `data/processed/es_pmp.parquet` (Spanish PMP from annual reports, used only as a check)
- `data/interim/ch_parent_chains.parquet` (Companies House PSC bulk data, UK entity to ultimate parent), `wikidata_uk_entities.parquet`
- Industry and revenue: `data/interim/wikidata_companies.parquet` (Wikidata P452), `sec_companies.parquet` (SEC SIC description, financial-SIC flag), `esef_companies.parquet` (ESEF revenue). For ESEF-only candidates the industry came from a live Wikidata SPARQL lookup by LEI (P1278 to P452)
- Live checks (at least 1.1 s between requests, descriptive User-Agent): every cited GOV.UK report page (49 pages; all returned 200, entity name and average days to pay matched the parquet in all 49), and Companies House PSC pages for 6 UK entities whose parent link needed checking

## Criteria

**Ten (expected Tier 1)**, all of these must hold:
1. Fit sector: the industry text matches one of automotive, aerospace/defence, chemicals, pharma/medtech, energy, metals/mining/materials, food/beverage, retail/wholesale, consumer goods, construction/engineering, logistics, industrial manufacturing/machinery/packaging. It must not be financial (keywords: bank, financial, insurance, asset management, investment, finance, reinsurance, private equity, pension, or the SEC financial-SIC flag, excluding real estate SICs).
2. Revenue of at least USD 4B in the raw revenue tables.
3. Slow payment evidence: across the group's UK reporting entities (latest usable, non-superseded report per entity, period ending between 2024-07-01 and 2026-11-16), the median average days to pay is at least 40. At least one matched entity also reports 45 or more days *and* 25% or more of payments paid late. A Spanish PMP above 60 days would also have qualified, but no pick needed it.

**Zero (expected Tier 3)**, either of these:
- (a) Financial sector by the keyword rule above, with no fit-sector keyword present.
- (b) Fast payer: every matched UK entity, and every UK reporter whose name carries the group's brand token, reports 20 days or less on average and 15% or less paid late. No Spanish PMP above 30 days.

**Entity to group linking** (needed for UK evidence): a UK entity counts only if Companies House PSC data or Wikidata links it to the candidate. Where the Companies House ultimate parent is known, it must contain the candidate's brand token. Rejected after a manual Companies House PSC check: Dobbies Garden Centres (no longer Tesco owned, parent Danataugusta Bidco) and Jacobs Douwe Egberts GB (parent chain is JDE, not Keurig Dr Pepper). Dropped from the evidence by hand: Opus Energy (Drax; ownership not confirmed, and Drax qualifies without it) and Renault Truck Commercials (a brand-token match; Renault Trucks is not part of Renault Group).

**Diversity cap:** at most 3 companies per sector bucket in each class. Financial zeros are split into bank, insurer, asset or investment manager, and other financial services.

## Procedure (reproducible)

1. Load the candidates and attach industry, revenue and UK entity evidence (`tmp/holdout_selection/prep.py`).
2. Shuffle the candidate indices with `random.Random(7).shuffle` (Python 3.11).
3. Walk the shuffled list. Test each company for "ten" first, then for "zero". Keep it if it qualifies and its sector cap has room. Stop when both classes have 20. `selection_order` is the 1-based position in the shuffled walk. The walk stopped at position 891.
4. Verify every cited GOV.UK report page live (`tmp/holdout_selection/verify.json`).

Code: `tmp/holdout_selection/holdout_pick.py`. `tmp/` is gitignored, so copy the folder if this should be kept.

## Iterations (logged so the process is visible)

- First pass used Wikidata industry only. Candidates identified by SEC CIK or by LEI had no industry and could never qualify as ten. I fixed this by adding SEC SIC and Wikidata-by-LEI industry, then reran.
- Two rules were tightened after the first pass, before the final run. "holding company" no longer counts as financial: it had swept in China Railway Engineering and Air France-KLM. Brand-named UK reporters must also be fast for a fast-payer zero: Siemens plc was fast, but other Siemens entities reported 43 to 84 days. The same brand entities also count in the ten median.
- Thresholds were briefly loosened (median 38, fast at 25 days) while coverage was broken. They went back to 40 and 20 once the industry fix was in. The final set uses the strict thresholds.

## Known weaknesses

- UK evidence covers UK legal entities only, not global group behaviour. Several tens rest on one or two UK subsidiaries (Continental via Dunlop Oil & Marine, Organon, Puma, Kone, Elanco, Terex, Kerry).
- Stellantis includes IBC Vehicles at 295 days. That is the reported figure and looks anomalous, but the ten also rests on Peugeot Citroen Automobiles UK (67 days, 60% late).
- Some fast-payer zeros are in fit sectors (Ferrovial, Deere, Colgate-Palmolive, Renault). They are zeros because they pay fast in the UK, not because the sector is wrong. A model that weights fit heavily may put them above Tier 3. That is a fair test, but a judgement call.
- Sector buckets come from keyword matching on Wikidata and SEC text, so some bucket names are coarse. The `category` column is the readable version.
- Revenue figures come from the project's raw Wikidata, SEC and ESEF tables. Some Wikidata revenue values are unreliable, but every ten is well above USD 4B.
