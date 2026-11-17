# Data licence note

The MIT licence in `LICENSE` covers the **code** only. The data in `data/`, `evals/gold/` and `outputs/` comes from
public sources that keep their own terms. Independent project by Moritz Hanbuch.

| Source | Where it appears | Terms |
|---|---|---|
| UK Payment Practices and Performance Reporting (Department for Business and Trade, check-payment-practices.service.gov.uk) | `data/processed/uk_*`, `evals/gold/uk_*`, site, one-pagers | **Open Government Licence v3.0.** Contains public sector information licensed under the Open Government Licence v3.0. This stays OGL in every derived table. |
| UK large-business payment statistics (GOV.UK) | benchmarks (`uk_official_benchmarks.csv`) | Open Government Licence v3.0 |
| Companies House bulk data (PSC snapshot, basic company data) | `data/interim/ch_*` | Open Government Licence v3.0. Corporate and legal-person owners only (companies, public bodies); no records of individuals are included. |
| SEC EDGAR XBRL company facts | `data/interim/sec_*`, DPO, supplier finance tags | US government public data (no copyright claimed by the SEC). Use follows SEC fair-access rules. |
| ESEF filings via filings.xbrl.org | `data/interim/esef_*`, Spanish PMP, supplier finance | The site states no licence. The filings remain the issuers' documents. This repo holds derived figures, short verification quotes and links, not the filings. |
| Spanish and other annual reports (issuers' sites, CNMV) | `data/interim/es_*`, `supplier_finance.*` quoted snippets | Issuers' copyright. Short quotes for verification only, each with its source link. |
| Wikidata | universe, sectors, parents | CC0 |
| Vendor customer and case-study pages | `data/interim/public_scf_case_studies.csv` | Vendors' copyright. Company names, links and quotes of 25 words or fewer, for validation only. |

**Our compilation** (scores, tiers, estimates, matches, labels, eval gold sets and the derived tables, to the extent they
are not covered above) is offered under **CC BY 4.0**: reuse it with attribution to "The Chase Index, Moritz Hanbuch".
Where a table mixes sources, the more restrictive term of its inputs applies to those fields (OGL for UK figures).

**Redactions in this public copy**: email addresses, phone numbers and titled personal names in the UK filings'
free-text fields are replaced with `[email removed]`, `[phone removed]` and `[name removed]`. The original text is on
the official report linked from each row. Dispute-text hashes were recomputed from the redacted text so labels still join.

**Estimates** (`est_*` columns, the one-pager "size of the prize") are illustrative calculations from stated
assumptions (`config/assumptions.yaml`), not reported facts.

**Corrections**: open an issue in this repository.
