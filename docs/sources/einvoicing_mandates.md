# B2B e-invoicing mandates: sources and dates

Checked: 2026-11-16 by the `scout` subagent. Machine-readable version: `config/einvoicing_mandates.yaml`.

Rule: a date is only used as a sales trigger if it was read on an official source during this run (`verified: true`). Vendor and advisory pages were not used as evidence. Pages were read through a fetch tool that summarises content, so re-open the source before quoting a date to a customer. These dates have been postponed before.

Trigger window as of 2026-11-16 (status upcoming, within 18 months, so up to 2028-05-16): DE 2027-01-01, DE 2028-01-01, FR 2027-09-01, ES 2027-10-06, PL 2027-01-01.

## Germany (DE)

| Date | What | Who | Status |
|---|---|---|---|
| 2025-01-01 | E-invoice rules apply to domestic B2B supplies; transitional relief on issuing | All domestic businesses | In force |
| 2027-01-01 | General relief ends: must issue structured e-invoices | Issuers with prior-year turnover above EUR 800,000 | Upcoming |
| 2028-01-01 | Relief ends for small issuers and for non-compliant EDI | All remaining issuers | Upcoming |

Source: UStG § 27 Abs. 38, https://www.gesetze-im-internet.de/ustg_1980/__27.html

Uncertain: the BMF FAQ (bundesfinanzministerium.de) returned HTTP 503 on three attempts. The statement that all businesses must be able to receive e-invoices since 1 January 2025 was not read on an official page; only the transitional rule in the statute was. During 2027 large issuers may still use EDI with recipient consent (Nr. 3).

## France (FR)

| Date | What | Who | Status |
|---|---|---|---|
| 2026-09-01 | Must be able to receive e-invoices | All companies | In force (date passed) |
| 2026-09-01 | Must issue e-invoices; e-reporting on the same calendar | Large companies and ETIs | In force (date passed) |
| 2027-09-01 | Must issue e-invoices; e-reporting | SMEs and micro-enterprises | Upcoming |

Source: impots.gouv.fr, "Je découvre la facturation électronique" (modified 26/05/2026), https://www.impots.gouv.fr/professionnel/je-decouvre-la-facturation-electronique

Uncertain: the page predates 1 September 2026 and uses the future tense. No official page published after that date was read. economie.gouv.fr returned HTTP 403, so the reported no-penalty tolerance for late 2026 is not verified.

## Spain (ES)

| Date | What | Who | Status |
|---|---|---|---|
| 2026-10-06 | Orden HAC/1028/2026 in force: legal clock starts | All | In force (milestone) |
| 2027-10-06 | Issue and receive e-invoices; report invoice status and payment | VAT turnover above EUR 8M in the prior year | Upcoming |
| 2028-10-06 | Issue and receive e-invoices (legal entities also report status) | All other businesses and professionals | Upcoming |
| 2029-10-06 | Invoice status reporting | Individuals and income-attribution entities at or below EUR 8M | Upcoming |

Sources: Agencia Tributaria implementation calendar, https://sede.agenciatributaria.gob.es/Sede/iva/factura-electronica/calendario-implantacion.html ; Orden HAC/1028/2026 (BOE 5 Oct 2026), https://www.boe.es/diario_boe/txt.php?id=BOE-A-2026-20587 ; Real Decreto 238/2026 (BOE 31 Mar 2026), https://www.boe.es/diario_boe/txt.php?id=BOE-A-2026-7295

Uncertain: nothing material. Large companies must attach a readable PDF for the first 12 months. The status reporting includes actual payment, which ties the mandate to late payment (useful for the pitch).

## United Kingdom (GB)

| Date | What | Who | Status |
|---|---|---|---|
| 2029-04-01 | Issue and receive VAT invoices as e-invoices | VAT-registered persons, public and private sector; limited exemptions | Proposed (not yet law) |

Source: GOV.UK, "Roadmap for e-invoicing implementation" (published 28 October 2026), https://www.gov.uk/government/publications/e-invoicing-implementation-roadmap/roadmap-for-e-invoicing-implementation

Uncertain: primary legislation is to go into Finance Bill 2026 and is expected to become law in Spring 2027. Requirements are to be confirmed between October 2027 and April 2028. Outside the trigger window.

## Belgium (BE)

| Date | What | Who | Status |
|---|---|---|---|
| 2026-01-01 | Structured e-invoices between businesses | All Belgian enterprises liable to VAT | In force |

Source: https://einvoice.belgium.be/en/article/structured-electronic-invoices-between-companies-are-compulsory-2026 (federal government e-invoicing site). Tolerance in the first three months of 2026: https://einvoice.belgium.be/en/news/period-tolerance-during-first-three-months-2026

Uncertain: finance.belgium.be (FPS Finance) served a human-verification challenge and was not read. A 2028 e-reporting step is not mentioned on the pages read: recorded as `verified: false`.

## Poland (PL)

| Date | What | Who | Status |
|---|---|---|---|
| 2026-02-01 | Issue invoices in KSeF | 2024 sales above PLN 200M (incl. VAT) | In force |
| 2026-04-01 | Issue invoices in KSeF | All other businesses, except the smallest | In force |
| 2027-01-01 | Issue invoices in KSeF | Smallest firms (up to PLN 10,000 invoiced per month) | Upcoming |

Sources: https://ksef.podatki.gov.pl/od-kiedy-trzeba-wystawiac-faktury-w-ksef/ (modified 30.04.2026) and https://ksef.podatki.gov.pl/etapy-wdrozenia-ksef/ (modified 29.05.2026)

Uncertain: penalty start date not stated on the pages read: recorded as `verified: false`.

## Italy (IT)

| Date | What | Who | Status |
|---|---|---|---|
| 2019-01-01 | E-invoicing through the Sistema di Interscambio | All invoices between parties resident or established in Italy, B2B and B2C | In force |

Source: Agenzia delle Entrate, https://www.agenziaentrate.gov.it/portale/aree-tematiche/fatturazione-elettronica/guida-fatturazione-elettronica/la-fattura-elettronica

Uncertain: extension to flat-rate taxpayers (2022, 2024) seen only in search snippets: recorded as `verified: false`. No upcoming deadline, so no dated trigger for Italy.

## EU: ViDA

| Date | What | Who | Status |
|---|---|---|---|
| 2025-04-14 | Package in force; Member States can introduce mandatory e-invoicing under specific conditions | Member States | In force |
| 2030-07-01 | Digital Reporting Requirements, based on e-invoicing | Cross-border B2B transactions | Upcoming |
| 2035-01-01 | Domestic real-time reporting systems must align with the EU system | Member States with such systems | Upcoming |

Source: European Commission, DG TAXUD, https://taxation-customs.ec.europa.eu/taxation/vat/vat-digital-age-vida_en (adopted 11 March 2025, Official Journal 25 March 2025)

Uncertain: the Commission page does not use the words "mandatory e-invoicing" for 1 July 2030, so the config keeps the page's wording. The directive text on EUR-Lex was not opened.

## Not reached

| Site | Result |
|---|---|
| bundesfinanzministerium.de (E-Rechnung FAQ and topic page) | HTTP 503, three attempts |
| economie.gouv.fr | HTTP 403 |
| finance.belgium.be | Human-verification challenge, not bypassed |
