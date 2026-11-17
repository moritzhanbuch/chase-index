# Methodology

Independent project by Moritz Hanbuch.

The Chase Index measures how long large companies take to pay their suppliers, using public data only. This page says exactly what each number is, where it comes from and what it is not. Every weight and assumption mentioned here lives in `config/assumptions.yaml`.

## What the index contains

Three kinds of numbers, never mixed:

| Kind | Label in the data | What it is | Coverage |
|---|---|---|---|
| Reported | `uk_reported`, `es_reported` | Figures the company itself filed under a legal duty | UK legal entities; IBEX 35 groups (Spanish entities) |
| Computed proxy | `computed_dpo_proxy` | Days payable outstanding, calculated from published financial statements | Listed groups with XBRL filings (SEC, ESEF) |
| Estimate | `estimate: true` | Illustrative sizing built on the two above plus stated assumptions | Target list and one-pagers only |

Reported evidence always outranks the proxy. Estimates never appear on the public site as facts.

## UK reported data

Source: the UK government's Payment Practices and Performance Reporting service (statutory since 2017, Open Government Licence v3.0). Large UK companies and LLPs report twice a year, per legal entity: average days to pay, the share of invoices paid within 30 days, in 31 to 60 days and after 60 days, the share not paid within agreed terms, and their standard and maximum payment terms.

- We take the full official CSV export. One row per report. Nothing is dropped: each report gets a `quality_flag` and an `is_usable` marker.
- A report is not usable when the company had no qualifying contracts, when a later filing supersedes it, when the period is not about six months, or when the values are impossible (for example an average above 365 days, or payment bands that do not sum to 100).
- "Latest" always means the latest usable report. An entity whose latest usable report ended more than about 18 months ago is marked stale and left out of group figures.
- Year-on-year change compares the latest report with the usable report whose period ended closest to one year earlier (within 92 days).
- About 6.5% of reports state a share of invoices paid late that cannot be true given their own payment bands (the company probably entered the on-time share). Those values stay in the entity data with a flag, and are excluded from group averages of the late share.
- Check: our parse reproduces the official annual medians for 2018 to 2025, and an independent spot-check of 20 reports against the official report pages matched on every field (`evals/reports/uk_spotcheck.md`).

Benchmark: official statistics put the median time to pay for large UK businesses at 32 days in 2025, with 15% of invoices paid late.

## Rolling UK entities up to groups

UK reports are filed by legal entity, not by group. We link entities to parent groups without a Companies House API key, using the public bulk data. A link is accepted only in three cases:

1. `exact_name`: the entity's own name equals a universe company's name, or its company number is that company's own registered number.
2. `ch_psc_chain`: the Companies House "persons with significant control" bulk snapshot shows an unbroken chain of majority holdings, more than 50% of shares or votes at every step, from the entity up to a company whose name matches a universe company. The nearest such company wins. A step where the registered number leads to a differently named company ends the walk. If the matched group is a bank, insurer or investor, the entity's own name must also carry that group's brand, because a majority investor does not make a portfolio company part of its group. Only corporate ownership records are used. Records about individuals are never extracted.
3. `brand_prefix`: the entity has no corporate owner on record and its name starts with a distinctive brand key built from a universe company's primary name.

Wikidata parent and subsidiary links are used only as corroboration. In the first version they were accepted on their own, and an independent check found them to be the least precise evidence (former owners, minority stakes, joint ventures): overall precision was 0.83. The rules above are the result. When an entity's name and its ownership chain point to different universe companies, the entity goes to `data/interim/review_queue.csv` and is not used. A short list of manual exclusions with reasons lives in `config/overrides.yaml` (for example entities acquired shortly before the reporting period ended). Both rounds of the check are in `evals/reports/entity_resolution.md`.

What this means for coverage: precision was chosen over recall. Many UK entities of large groups are not linked, so a group's UK entity count is a lower bound. Joint ventures held 50/50 are attributed to nobody. UK ownership records stop at the border: the first foreign owner is named, which is not always the global parent.

Group-level UK figures are averages across the group's matched UK entities with a current usable report, weighted by the invoice value each entity reports paying, so that a small sales office cannot mask the main operating company or the reverse. Where an entity does not report invoice value, the simple mean is used and the row says so (`uk_days_aggregation`). The simple mean and the slowest entity are stored as well. An entity reporting an average of 200 days or more, or a change of 100 days or more against the year before, is left out of the group figures and listed separately as an extreme value to verify: such values are far more often filing errors than payment behaviour. It stays in the entity data with its official link. Figures describe each legal entity in its stated reporting period, whoever owned it then. They are not a statement about how the group pays worldwide.

## Spain reported data

Source: the statutory "periodo medio de pago a proveedores" (PMP) note that Spanish companies publish in their annual accounts under Ley 15/2010 (third additional provision, as amended by Ley 18/2022). The formula is set by the ICAC resolution of 29 January 2016: PMP = (ratio of paid operations x payments made + ratio of pending operations x payments pending) / (payments made + payments pending). The legal maximum for B2B payments is 60 days.

- Coverage: IBEX 35, fiscal year 2025, from the annual reports filed in ESEF format (filings.xbrl.org), plus two investor-relations pages.
- Two independent extractors read each document: deterministic code (table and pattern parsing) and an LLM reader. A value is accepted when both agree within 0.5 days. Any disagreement, or a value found by only one of them, goes to a third reader who checks the source and records the reasoning. Nothing is silently picked. See `evals/reports/spain_extraction.md`.
- Scope: the note covers the group's Spanish entities (or the parent company only, where marked). It says nothing about payment behaviour outside Spain.
- Other analyses of Spanish payment delays, such as those by the Plataforma Multisectorial contra la Morosidad, use a different method. We never mix them with the statutory PMP.

## Computed DPO (proxy)

DPO = trade payables at fiscal year end / cost of sales x 365, from XBRL facts in annual filings (SEC EDGAR for US filers and foreign private issuers; ESEF for EU and UK listed groups).

- It is a balance-sheet proxy. It includes accruals and timing effects and is not the same thing as reported days to pay. It is always labelled "computed DPO (proxy)".
- Where a company tags only a broad payables line ("trade and other payables") or reports costs by nature, the row is kept with lower confidence and the basis is stored.
- Banks and insurers are marked `not_applicable`. Values below 5 or above 365 days are flagged as suspicious and excluded from scoring.
- Sector medians use only clean rows (standard concepts, confidence 1.0).
- Germany, Ireland and Switzerland are not available from the ESEF source we used. German groups appear with DPO only when they also file with the SEC. Germany has no statutory payment-performance reporting comparable to the UK regime.
- Check: an independent recomputation from the original filings for 15 random companies (`evals/reports/dpo_check.md`).

### DACH slice: DPO from annual reports

For DAX 40 and MDAX members headquartered in Bavaria and the largest Swiss and Austrian listed industrials in the universe, the inputs are read from the latest consolidated annual report (official IR page; ESEF where published): trade payables to suppliers (not total payables, from the notes where the balance sheet mixes in advances or other payables) and cost of sales, or cost of materials for groups that report by nature of expense. Two extractors read each report independently: deterministic code (tagged facts, then statement and note rows by label) and an agent reading the page text. Values within 0.5% are accepted; every other value is decided by a separate QA agent from the source page, with its reasoning recorded. The rows join the DPO table as a third source with the same flags, confidence rules and sector medians as the filing-based rows. Coverage, agreement, adjudication and a 10-company hand-check: `evals/reports/dach_extraction.md`. Steps: `python -m chase.sources.dach_slice members|targets|docs|extract-a|reconcile|final`; `make dach` rebuilds from the committed extractions offline.

## Company universe

A "Global 2000-style" universe built from public data, not from the Forbes list: companies whose latest known annual revenue is at least USD 4 billion, merged from SEC filers, ESEF filers and Wikidata using SEC CIK, LEI and exact normalised names. Revenue from filings is preferred. Wikidata revenue is community-edited, keeps its year, and is flagged stale when older than 2022. Currency conversion is for the size screen only and uses approximate rates.

Sectors come from SEC SIC codes where available. For the rest, an LLM classified each company into one of 14 coarse sectors from its name and Wikidata industry labels (`sector_method = llm_classification`, with a confidence). The HQ country comes from Wikidata or the SEC business address. For companies known only from a European filing, the filing index gives the country of filing, so an LLM supplied the HQ country and it is applied where it was at least fairly sure (`country_method = llm_hq_country`). A few manual corrections with reasons are in `config/overrides.yaml`.

## Scores

Three scores from 0 to 100, all deterministic.

**Fit** (slow-changing): revenue band (30), geography (25: HQ in Spain, Germany, UK or France scores highest, then the rest of Europe, then the US), sector suitability (30: manufacturing, automotive, construction, retail, consumer goods, energy, pharma and logistics score high; financials low), ERP evidence (10: neutral when unknown) and supplier-base breadth by employee count (5).

**Pain**: from reported data where it exists. A component with no evidence scores zero; weights are not rescaled, so missing data can never raise a score. Average days to pay between 25 and 65 days (45 points; 65 is about twice the UK median), share of invoices paid late (25), share paid after 60 days (15) and year-on-year worsening (15). The year-on-year change used for scoring is the smaller of the invoice-value-weighted mean and the median across entities, so one entity cannot carry a group's trend; the number of entities that got slower is kept next to it. For UK evidence the score is scaled by a materiality factor based on the invoice value the matched UK entities report paying. When that value is larger than half of the whole group's cost base (2.5 times for UK-headquartered groups), it is treated as intercompany purchasing or a unit error and the factor drops to 0.6. Without reported data, pain comes from computed DPO relative to the sector median, is capped at 70 and is multiplied by the confidence of the DPO row, so a proxy can never outrank strong reported evidence and a weak proxy cannot reach Tier 1 alone. A computed DPO above 200 days is treated as a tagging artefact and not scored. `pain_evidence_tier` records which kind was used.

**Signal** ("why now"): worsening trend (35), finance or AP hiring (20), recent press on supplier payments (15), no payment-code membership (10), a fresh statutory filing (10) and very long contractual terms (10). Hiring and press are only counted with an evidence URL. Only the trend, a fresh filing, hiring and press are shown as triggers on sales assets; payment-code status and long contractual terms are standing facts and are labelled as such.

**Priority tier**: fit below 55 means Tier 3. Otherwise pain of 50 or more is Tier 1, 30 or more is Tier 2, the rest Tier 3. A signal score of 45 or more upgrades one tier. Units of larger groups, non-companies, banks and insurers, and non-addressable countries are held in Tier 3 with a reason. Within a tier, companies with reported evidence rank ahead of proxy-only companies.

Each company gets a short written rationale. It may cite only fields in that company's row. Calibration against a gold set of "obvious tens" and "obvious zeros" is in `evals/reports/calibration.md`.

## Estimates

All estimates are labelled `estimate`, shown as a low / base / high range, and driven by `config/assumptions.yaml`.

- Supplier spend base, UK scope: invoice value the matched UK entities report paying in their latest half-year reports, times two. Self-reported invoice values contain occasional unit errors, so the UK-scope estimate is dropped when that base would exceed the group's own revenue.
- Group level: local reported days are never applied to global spend. A group estimate exists only where a clean computed DPO is available (standard payables and cost-of-sales concepts), using group cost of sales as the base and the DPO as the days. It is a proxy on a proxy and labelled that way. Where no clean DPO exists there is no group estimate.
- Excess supplier days = max(0, days to pay - 30). The 60-day version is stored too.
- Supplier cash outstanding beyond 30 days = spend x excess days / 365.
- Early-payment discount opportunity = spend x share eligible x annualised rate x days accelerated / 365, with days accelerated = days to pay minus day 10, capped at 60. Low: 5% of spend at 8%. Base: 10% at 10%. High: 15% at 12%.

The range is the gross discount a buyer could capture, before the buyer's own cost of funding the early payment and without netting any supply chain finance programme already in place. It is there to size a conversation, not to forecast revenue.

## Limitations

See `docs/limitations.md`. The short version: UK and Spanish figures cover local entities only; DPO is a proxy; group roll-ups are probabilistic; coverage of German groups is thin; estimates are illustrative.

## Corrections

If a figure is wrong, the official source wins. Each reported number links to its source. Corrections can be sent to the author and are applied by re-running the pipeline against the corrected source.

## Phase 12: filing fields, supplier finance, triggers and the weekly queue

**UK filing fields beyond speed** (`src/chase/enrich/uk_fields.py`, report `evals/reports/uk_fields.md`). Dated changes become signals: payment terms changed towards longer terms, supply chain finance or e-invoicing newly offered. The dispute share (filer's figure for invoices not paid within terms because of a dispute) is used only where it does not exceed the entity's own late share: 275 entities report it above their late share, which shows a second reading of the field, and those values are left out. The dispute-process text is rated on a four-level rubric. Only LLM-read labels drive the weak-process signal (a blind QA check found regex labels unreliable: kappa 0.43 vs 0.84).

**Supplier finance disclosures** (`supplier_finance.py`, `supplier_finance_reconcile.py`, report `evals/reports/supplier_finance.md`). IAS 7 / IFRS 7 amendments and ASU 2022-04 require buyers to disclose supplier finance programmes. Two extractors (XBRL tags, text reader) for the top 200, QA adjudication and a blind 32-company hand-check. A "yes" counts in scores and triggers only when `programme_confirmed` (two readers agree, adjudicated, or verified by the hand-check). "No evidence" does not mean "no programme".

**Signal score additions** (weights in `config/assumptions.yaml`): terms changed longer 15, confirmed supplier finance 10, SCF started 5, e-invoicing started 5, high dispute share 5; total capped at 100. Tiers stay pain-led: the signal can only upgrade one tier when the fit gate passes.

**Triggers** (`src/chase/gtm/triggers.py`). A trigger is a dated, sourced event with a strength and a live window. Standing facts are evidence, not triggers. E-invoicing mandates carry `binds`: a deadline that binds the buyer is a trigger at strength 0.5; one that binds only its small suppliers is 0.3 and says so; member-state deadlines are never triggers. Year-on-year jumps of 100+ days or 4x are verification cases, not triggers.

**Weekly queue and next best action** (`src/chase/gtm/nba.py`). Queue priority = base from tier and score + trigger strength + optional bring-your-own-data flags; each account gets a play, a role to ask for, and an opener that is a human-written template with data slots. Accounts with a confirmed supplier finance programme get an opener about the programme's reach and whether terms got longer with it, not an early-cash pitch (DECISIONS 49). A why-now trigger quotes a single UK entity; the opener quotes the UK average across entities, and each is labelled as such (DECISIONS 50).

**External validation** (`evals/reports/external_validation.md`). Blind holdout (15/20 and 19/20), supplier finance tags (size-adjusted odds ratio 1.9 for Tier 1), vendor case studies (no significant link). The ranking says who to talk to first, not who buys.
