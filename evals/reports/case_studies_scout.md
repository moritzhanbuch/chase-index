# Public AP / early-pay / SCF customer list (external validation scout)

Retrieved 2026-11-16. File: `data/interim/public_scf_case_studies.csv` (the 9-row seed, extended in place). Two new columns: `company_id` (blank when unmatched) and `match_method`. The scout did not look at scores, rankings, `outputs/` or `data/processed/companies*`. Only `company_id, name, legal_names, aliases` were read from `universe.parquet`.

## Counts

| | |
|---|---|
| Rows | 139 |
| Distinct companies | 128 |
| Distinct companies excluding the 2012 UK government list | 99 |
| Distinct with a typed programme (not `unknown`) and not from the 2012 list | 76 |
| Matched to a universe `company_id` | 89 distinct ids (65 excluding the 2012-only rows) |

Programme type by row: supply_chain_finance 49, ap_automation 38, dynamic_discounting 26, unknown 26.

## Vendors and sources scanned

| Vendor / source | Page used | Result |
|---|---|---|
| SAP Taulia | taulia.com/customers/, one success story, casestudies.com/company/taulia | Seed confirmed; REWE (SCF + dynamic discounting) and Sasol (dynamic discounting) upgraded; DFA added. Page 2 of the customer index returned 404. |
| C2FO | casestudies.com/company/c2fo; buyer microsites `<buyer>.c2fo.com` | 12 buyer-side case studies. 13 microsites whose page title reads "<Buyer> Early Payment Program": Amazon, Best Buy, Costco, Ford, The Home Depot, HP, Intel, Kroger, Lowe's, Philips, Sysco, Unilever, Walmart (plus SRF, dropped as too small). c2fo.com/resources/customer-stories/ was a 404. |
| Basware | casestudies.com/company/basware, basware.com Michelin page | 27 rows. basware.com customer index URLs returned 404. |
| Tradeshift | casestudies.com/company/tradeshift | 11 rows. tradeshift.com/customers/ was a 404. |
| PrimeRevenue | casestudies.com/company/primerevenue | 5 rows (AGCO, Boston Scientific, Genuine Parts, Michelin, Volvo Cars). |
| Medius | medius.com/customers, casestudies.com/company/medius | 3 rows (Mowi, Puma, SMC). |
| Kyriba | kyriba.com customer pages, casestudies.com/company/kyriba | 2 rows (Auchan SCF, McCormick). Treasury-only stories skipped. |
| Serrala | serrala.com/customer-success | AkzoNobel (AP story) plus 12 large logo-wall names (`unknown`). |
| HighRadius | highradius.com/customers/ | 3 titled case studies (Abbott, Konica Minolta, Crocs). This is AR-side demand. The logo wall was not used. |
| Esker | esker.com/customers, casestudies.com/company/esker | 1 AP row (Yaskawa America). Most large names are AR or order-management stories and were skipped. |
| Tungsten Network | Unilever campaign page | 1 row. The index URL was a 404. GSK appears in search results only and was not added. |
| Orbian | orbian.com Siemens post, siemens.com/fr-ca SCF page | Siemens. Krispy Kreme skipped (below the size bar). |
| Banks | flow.db.com (Henkel), santandercib.com (Bosch), hitachienergy.com (own SCF page) | 3 rows |
| UK government | gov.uk, 23 Oct 2012 SCF scheme | 32 rows. This is a commitment to "evaluate or continue" offering SCF, not proof of a live programme. Rows are marked as old, weak evidence. |

Failed or blocked: coupa.com/customers (403, so no Coupa rows), demica.com/news (403), ivalua.com/customers (404), corporate.asda.com (425 twice; Asda appears only through the 2012 gov.uk list), businessgreen.com Walmart/HSBC (403), support.taulia.com Vodafone page (TLS error). Billtrust, Jaggaer, Marco Polo/TradeIX and Tungsten/Kofax beyond Unilever were not reached in the time box. casestudies.com robots.txt allows these paths. C2FO robots.txt sets a 10 s crawl-delay, and the microsite checks used 10 s spacing.

## Matching

Normalised exact match on name, legal names and aliases: lowercase, ASCII, punctuation and legal suffixes stripped. Keys that resolved to more than one id were left blank, except 3 resolved by hand to the obvious group (BAE Systems, Heineken N.V., Vodafone Group). 4 further manual matches: AB Foods to Associated British Foods (abbreviation), Ritchie Bros. to RB Global and Finmeccanica to Leonardo (renames), ISS World Services to ISS. Subsidiaries were deliberately left unmatched to their parents: Air France, DHL Express, VINCI Energies, Toyota Industrial Equipment, Yaskawa America, EDF Energy, innogy, Beko. Ericsson is unmatched because the universe has two Ericsson rows (possible universe duplicate). Heineken, McDonald's and Carlsberg rows name a national subsidiary and are matched to the group; `match_method` flags this.

## Known biases and limits

- Vendors showcase big, happy logos. This list says who bought something, not how well it works or whether it is still live.
- Absence means nothing. Most AP and SCF customers are never named publicly, so a missing company is not a negative signal.
- Coverage depends on which vendor sites were reachable. Coupa, Ivalua, Jaggaer and Billtrust are missing for access reasons, not for lack of customers.
- Mixed evidence strength. The 32 gov.uk 2012 rows are 14 years old and only record an intent, so filter them out (`vendor` contains "UK government") for a strict test. Logo-wall rows (Serrala) and C2FO microsite rows rest on alt text or a page title, not narrative text.
- US-retail skew in C2FO and Europe/Nordic skew in Basware/Tradeshift follow the vendors' own markets.
- Several case-study rows come from casestudies.com, which republishes vendor case studies. The vendor's own page was not opened in every case.
- `evidence_year` is blank where the page shows no date.
- `evidence_type` gained one value not in the brief: `company_supplier_page` (Hitachi Energy). Seed `supplier_finance` rows were normalised to `supply_chain_finance`.
