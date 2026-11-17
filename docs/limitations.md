# Limitations

Independent project by Moritz Hanbuch.

An honest list of what this dataset cannot tell you.

## Reported UK data

- **Legal entities, not groups.** UK reports are filed per legal entity. A group figure here is an average across the UK entities we could match to that group, weighted by the invoice value each entity reports paying (the simple mean where an entity does not report it). It says nothing about how the group pays suppliers outside the UK.
- **Self-reported.** Companies compute their own figures. A director approves each report, but nobody audits it. Some reports contain obvious errors (for example a late share that contradicts the payment bands). We flag these and keep them out of group averages, but we cannot detect subtle errors.
- **Averages hide the spread.** "Average days to pay" is an unweighted mean of invoices. A company can pay most invoices quickly and a few very late, or the reverse.
- **Invoice receipt date.** The clock starts when the company says it received the invoice. Practices differ.
- **Small UK footprints.** A global group may have one small UK entity. We scale the evidence by the invoice value those entities report, but a small base is still a small base.

## Group roll-up

- **Precision over recall.** Without paid registry data, entities are linked to groups through public bulk ownership data and conservative name rules. A first version was right in only 50 of 60 checked links. The current rules (verified majority-ownership chains) were right in 60 of 60 on a fresh sample, which supports a precision of about 0.95 or better and no more than that. Recall is not measured: many UK entities of large groups are not linked, so a group's UK entity count is a lower bound.
- **Ownership changes.** Figures describe a legal entity in its reporting period, whoever owned it then. A recently acquired or spun-off entity can sit under its new owner with figures from the old one. Known cases are excluded by hand in `config/overrides.yaml`; unknown ones are not.
- **One entity can drive a group figure.** Weighting by invoice value means a single large entity dominates (and self-reported invoice values contain occasional unit errors). The simple mean and the per-entity table are shown next to it.
- **Ownership data stops at the border.** UK ownership records name the first foreign owner, which is not always the global parent.
- **Joint ventures and recent deals** can be attributed to the wrong parent or to none.

## Spain

- **IBEX 35 only**, fiscal year 2025. 32 of 35 have a value. Ferrovial and ArcelorMittal are non-Spanish issuers without the note; Banco Sabadell's table is not in the machine-readable text of its filing.
- **Spanish entities only.** The statutory note covers the group's Spanish companies, or only the parent where marked.
- **Printed inconsistencies stay as printed.** Two companies print a payment period that lies outside its own two ratios. We keep the printed figure, flag it and lower the confidence.
- **No page numbers.** The source is the tagged annual report (ESEF), so locations are fact identifiers and text offsets, not PDF pages.

## Computed DPO

- **A proxy.** Payables divided by cost of sales includes accruals, capital expenditure payables and timing effects. A high DPO does not prove slow invoice payment, and a low one does not prove fast payment.
- **Tagging varies.** Some companies tag only "trade and other payables" or report costs by nature. Those rows have lower confidence and can overstate DPO.
- **Coverage gaps.** Germany, Ireland and Switzerland are missing from the European filing source we used. The DACH slice fills part of that from annual-report PDFs: 23 companies (Bavarian DAX and MDAX members, the largest Swiss listed industrials, Strabag). Other German groups have DPO only if they also file in the US. UK coverage from the filing source is partial. Banks and insurers are excluded because DPO is not meaningful for them.
- **DACH slice specifics** (`evals/reports/dach_extraction.md`). Three reports could not be retrieved without working around a block (Renk, Schaeffler, Fresenius Medical Care). Siemens Energy prints only a combined "trade and other payables" line, so it has no figure. Five nature-of-expense reporters use cost of materials, which reads high against a cost-of-sales median: they carry lower confidence and never earn a dinner hook. The reports are FY2025; September year-end groups publish FY2026 reports from late November 2026. The deterministic extractor was right on none of the values QA had to decide; the agent reader and the QA adjudication carry the accuracy, and a 10-company hand-check (5 of them not fully blind) matched on every value.
- **Universe additions.** Eleven Bavarian index members were added below the USD 4bn threshold because the slice is defined by index membership. Austria is represented by Strabag only: voestalpine, Andritz and Wienerberger are missing from the universe build.

## Universe

- **Not the Forbes Global 2000.** It is a comparable list built from public filings and Wikidata with a revenue threshold of USD 4 billion. Private companies appear only if Wikidata has a revenue figure for them.
- **Wikidata is community-edited.** Revenue years can be stale (flagged) and industry labels are uneven. Sectors without an SEC code were assigned by an LLM from the name and labels, with a confidence value. Some will be wrong.
- **Currency conversion** uses approximate rates and is only used to apply the size threshold.

## Scores and estimates

- **Scores rank, they do not measure.** Fit, pain and signal are weighted formulas chosen by the author and calibrated on a small hand-picked gold set. Change the weights in `config/assumptions.yaml` and the ranking changes.
- **ERP evidence is mostly missing.** No reliable public, crawlable source covers SAP usage across the universe, so the ERP component is neutral for almost every company.
- **Signals are data-driven only.** Hiring and press signals are supported by the model but were not collected at scale in this run.
- **Estimates are illustrative, and small.** The discount opportunity multiplies a spend base by assumed shares and rates. A group-level range exists only where a clean computed DPO is available and uses that DPO as the days: a proxy on a proxy. The UK-scope range is the buyer's gross discount on its UK entities only, before the buyer's funding cost, and for many accounts it is a few hundred thousand pounds. Treat it as the size of a first conversation.
- **Calibration is a consistency check.** The gold set was picked without sight of the scores but from the same reported figures, and the weights were tuned against it over more than 20 logged iterations. There is no holdout.
- **"Pain" is the supplier's pain.** A long payment period met on time is a result many CFOs are proud of. The scores rank where suppliers wait longest, which is where a two-sided product has something to offer both sides. They do not measure a buyer's dissatisfaction.

## Things this project deliberately does not do

- It does not scrape LinkedIn, login-walled sites or anything behind a captcha.
- It does not publish names of individual people.
- It does not contact anyone. Outreach texts are drafts.
