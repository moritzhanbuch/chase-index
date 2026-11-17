# UK payment practices spot-check (qa)

Checked: `data/processed/uk_payment_practices.parquet` rows vs official report pages on check-payment-practices.service.gov.uk.

- Sample: 20 rows, `random_state=20261116` (16 `is_usable=True`, 4 `is_usable=False`), `DataFrame.sample` on each subset, no cherry-picking.
- Method: `evals/uk_spotcheck.py` fetches `/report/{report_id}` via the shared client (1 req/s, cached, no query strings), parses the HTML and compares 13 fields (name, company number, period start/end, filing date, avg days to pay, % within 30, 31-60, 61+, % not paid within agreed terms, shortest/longest standard period, max contractual period). Names compared case-insensitively. The 'Approved by' person is deliberately not captured.

## Result: 20/20 rows fully matching; 260/260 fields matching

| report_id | company | usable | fields ok | mismatches (table vs page) |
|---|---|---|---|---|
| [62479](https://check-payment-practices.service.gov.uk/report/62479) | EVERTON FOOTBALL CLUB WOMEN LIMITED | True | 13/13 | none |
| [31871](https://check-payment-practices.service.gov.uk/report/31871) | RRG GROUP LIMITED | True | 13/13 | none |
| [84160](https://check-payment-practices.service.gov.uk/report/84160) | ARBOR FOREST PRODUCTS LIMITED | True | 13/13 | none |
| [51057](https://check-payment-practices.service.gov.uk/report/51057) | NATS LIMITED | True | 13/13 | none |
| [116778](https://check-payment-practices.service.gov.uk/report/116778) | ALTRAD SUPPORT SERVICES LIMITED | True | 13/13 | none |
| [64737](https://check-payment-practices.service.gov.uk/report/64737) | SHEPHERD AND WEDDERBURN LLP | True | 13/13 | none |
| [110403](https://check-payment-practices.service.gov.uk/report/110403) | INSPIRE PARTNERSHIP ACADEMY TRUST | True | 13/13 | none |
| [91224](https://check-payment-practices.service.gov.uk/report/91224) | ALVAREZ & MARSAL EUROPE LLP | True | 13/13 | none |
| [92805](https://check-payment-practices.service.gov.uk/report/92805) | ATKINSRÉALIS UK LIMITED | True | 13/13 | none |
| [55175](https://check-payment-practices.service.gov.uk/report/55175) | EVERBUILD BUILDING PRODUCTS LIMITED | True | 13/13 | none |
| [113191](https://check-payment-practices.service.gov.uk/report/113191) | G4S CARE AND JUSTICE SERVICES (UK) LIMITED | True | 13/13 | none |
| [88655](https://check-payment-practices.service.gov.uk/report/88655) | FMC TECHNOLOGIES LIMITED | True | 13/13 | none |
| [106169](https://check-payment-practices.service.gov.uk/report/106169) | QUILTER INVESTMENT PLATFORM LIMITED | True | 13/13 | none |
| [81234](https://check-payment-practices.service.gov.uk/report/81234) | GRANT THORNTON AGILE TALENT SOLUTIONS LIMITED | True | 13/13 | none |
| [24096](https://check-payment-practices.service.gov.uk/report/24096) | CHELTENHAM AND GLOUCESTER OMNIBUS COMPANY LIMITED | True | 13/13 | none |
| [56908](https://check-payment-practices.service.gov.uk/report/56908) | EUROFINS FORENSIC SERVICES LIMITED | True | 13/13 | none |
| [59612](https://check-payment-practices.service.gov.uk/report/59612) | EXXONMOBIL UK LIMITED | False | 13/13 | none |
| [105923](https://check-payment-practices.service.gov.uk/report/105923) | LRC PRODUCTS LIMITED | False | 13/13 | none |
| [23505](https://check-payment-practices.service.gov.uk/report/23505) | PARAGON BANKING GROUP PLC | False | 13/13 | none |
| [11295](https://check-payment-practices.service.gov.uk/report/11295) | GRANT THORNTON ACQUISITIONS LIMITED | False | 13/13 | none |

## Non-usable rows (quality_flag consistency)

- report 59612 (EXXONMOBIL UK LIMITED): flag `no_qualifying_contracts`, had_qualifying_contracts=False. Page: "The business stated that it did not enter into any qualifying contracts in the reporting period." -> consistent
- report 105923 (LRC PRODUCTS LIMITED): flag `no_qualifying_contracts`, had_qualifying_contracts=False. Page: "The business stated that it did not enter into any qualifying contracts in the reporting period." -> consistent
- report 23505 (PARAGON BANKING GROUP PLC): flag `no_qualifying_contracts`, had_qualifying_contracts=False. Page: "The business stated that it did not enter into any qualifying contracts in the reporting period." -> consistent
- report 11295 (GRANT THORNTON ACQUISITIONS LIMITED): flag `no_qualifying_contracts`, had_qualifying_contracts=False. Page: "The business stated that it did not enter into any qualifying contracts in the reporting period." -> consistent

## Failures and likely cause

See mismatch column; if none, no failures.
