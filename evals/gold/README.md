# Gold sets

## calibration.csv

Purpose: an independent check on the priority tiers. It lists 17 "obvious tens" (expected Tier 1) and 15 "obvious zeros" (expected Tier 3). The scoring model passes calibration if tens land in Tier 1 and zeros in Tier 3.

**Mo: please review this file by hand before relying on the calibration result.** It was chosen by an agent (`qa-calibration`), not by a person. Delete or relabel any row you would not defend in front of your team.

### How it was chosen

- Built by a separate agent from the one that built the scoring model.
- The agent was not allowed to read `data/processed/scores.*`, `data/processed/companies.*`, `outputs/`, `src/chase/score/` or `config/assumptions.yaml`, and did not. The set is not reverse-engineered from the model.
- Inputs used: `data/processed/universe.parquet` (candidates; rows flagged `is_subsidiary_or_unit` or `not_a_company` excluded), `uk_entity_latest.parquet` (UK statutory reports, only `has_usable_report` and not `latest_is_stale`), `es_pmp.parquet` (Spanish statutory PMP, FY2025), `dpo.parquet` (only to confirm banks are marked not applicable).
- Benchmark: UK large-business median time to pay of 32 days in 2025 (https://www.gov.uk/government/statistics/large-businesses-payment-practices-and-performance-statistics-2025). Spain: 60-day legal maximum.
- UK entities were linked to groups by searching entity names for the group or brand name, by hand. Entity names, days and report URLs are in `evidence_entities` and `evidence_urls`, so every link can be checked.
- Every figure in `justification` and `evidence_entities` is copied from those files. Nothing was looked up elsewhere. No web fetches were made, so `sap_evidence_url` is empty for all rows.

### Selection rules

- **Tens (17):** large European or Europe-active industrial, consumer goods, pharma or construction groups whose official reported data shows slow payment: UK entities with large invoice value averaging roughly 50+ days (most are 65+), or a Spanish PMP above the 60-day legal maximum. HQ mix: GB 6, FR 3 (incl. Coca-Cola Europacific Partners as coded in the universe), US 3, NL 1, CH 1, BE 1, DE 1, ES 1.
- **Zeros (15):** 6 banks and insurers; 5 large non-financial groups whose reported data shows fast payment; 4 companies outside the addressable market (Russian and Chinese state-owned) with no payment evidence.

### Rows to look at first (least obvious)

- `fast_payer` zeros BMW, Mercedes-Benz Group and BAE Systems: strong sector and size fit, evidence is UK entities only. They are zeros on pain, not on fit. A model that weights fit heavily may put them in Tier 2, and that may be a defensible outcome rather than a model error.
- Iberdrola, Naturgy: utilities with very low Spanish PMP. Zero on pain; fit is debatable.
- Saint-Gobain: 53-55 days across four UK entities. Slow, but the mildest ten.
- Anheuser-Busch InBev: one UK entity only (118 days, GBP 945M).
- Grifols: revenue USD 8.5B, below the USD 10B preference. Only ten based on Spanish PMP.
- Rolls-Royce and Airbus: main entity slow, some smaller entities fast (listed in the evidence).
- Siemens Energy: evidence includes the Siemens Gamesa UK entity, which is a separate row in the universe.
- Allianz: single small UK entity (26 days, 23% late). It is a zero because it is an insurer.

### Left out on purpose

Acerinox (PMP 63 days, but extraction confidence 0.80 and revenue USD 6.2B), Heineken (two universe rows, unclear which is the group), Reckitt, Kingfisher, Novartis, Sainsbury's, Jaguar Land Rover (no matching universe row found), Endesa (has a parent in the universe), Tesco, Stellantis, Bayer, Siemens AG, AstraZeneca (mixed or thin evidence).

### Limits

UK evidence is UK legal entities only and says nothing certain about group behaviour elsewhere. Spanish PMP covers the group's Spanish entities (Santander: parent only). "% late" is measured against each company's own agreed terms, so a company with long terms can show long days and few late invoices.
