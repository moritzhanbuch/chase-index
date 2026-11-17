# Spain: periodo medio de pago a proveedores (PMP)

Scouted 2026-11-16 by `scout-es`. All legal texts below were read on boe.es on that date.

## Legal basis

| What | Reference | URL |
|---|---|---|
| Payment terms: 30 calendar days by default, never more than 60 by agreement | Ley 3/2004, de 29 de diciembre, art. 4 (wording in force since 2013) | https://www.boe.es/buscar/act.php?id=BOE-A-2004-21830 |
| Disclosure duty ("Deber de información") | Ley 15/2010, de 5 de julio, disposición adicional tercera (BOE no. 163, 6 July 2010) | https://www.boe.es/buscar/act.php?id=BOE-A-2010-10708 |
| First amendment of DA 3ª | Ley 31/2014, de 3 de diciembre, disposición final segunda (in force 24 Dec 2014) | https://www.boe.es/buscar/act.php?id=BOE-A-2014-12589 |
| Current wording of DA 3ª (adds invoices paid within the legal maximum) | Ley 18/2022, de 28 de septiembre, "de creación y crecimiento de empresas", art. 9.2 (BOE no. 234, 29 Sept 2022; in force 19 Oct 2022). BOE's consolidated text cites **art. 9.2**, not just art. 9 | https://www.boe.es/buscar/act.php?id=BOE-A-2022-15818 |
| Formula and note layout | Resolución de 29 de enero de 2016 del ICAC (BOE 4 Feb 2016, BOE-A-2016-1112), applies to financial years starting on or after 1 Jan 2015 | https://www.boe.es/buscar/doc.php?id=BOE-A-2016-1112 |

DA 3ª as in force (paraphrased, 4 paragraphs):
1. Every sociedad mercantil states its PMP in the notes (memoria) to its annual accounts.
2. Listed companies publish on their website the PMP, the monetary volume and number of invoices paid within the legal maximum, and the share these represent of all invoices and of all supplier payments. The same goes in the notes.
3. Unlisted companies that do not file abridged accounts publish the same (on their website if they have one) and in the notes.
4. ICAC adapts the calculation method by resolution.

## The statutory formula (ICAC Resolution 29 Jan 2016, art. 5)

```
PMP = (ratio operaciones pagadas x importe total pagos realizados
       + ratio operaciones pendientes de pago x importe total pagos pendientes)
      / (importe total pagos realizados + importe total pagos pendientes)

ratio operaciones pagadas    = sum(días de pago x importe operación pagada) / importe total pagos realizados
ratio operaciones pendientes = sum(días pendientes x importe operación pendiente) / importe total pagos pendientes
```

- Days are calendar days counted from receipt of goods or services (invoice receipt date allowed if that is not reliably known) to payment, or to the period end for pending items (art. 5.2 to 5.4).
- "Proveedores" = trade creditors in current liabilities for goods or services (art. 4.b). Fixed-asset suppliers and financial creditors are out.
- Required table (art. 6.1): PMP, ratio pagadas, ratio pendientes (days); total pagos realizados, total pagos pendientes (amount), current and prior year. Ley 18/2022 adds the paid-within-maximum rows.
- Small companies on the abridged/PYME model use a different, balance-based formula (art. 5.5). Not relevant for IBEX 35 but never mix the two.

## Where the data lives

1. **Notes to the consolidated annual accounts**, inside the ESEF annual financial report. https://filings.xbrl.org hosts every Spanish ESEF filing (API: `/api/filings?filter[country]=ES&include=entity`, no robots.txt, open). Each filing has a `report_url` (XHTML, 5 to 77 MB gzip, slow host at about 65 KB/s on the day) and a `json_url` (xBRL-JSON, 0.7 to 4 MB gzip). Because notes are block-tagged since FY2022, **the JSON text-block facts contain the PMP note**. This was the uniform route: 31 of 33 Spanish-domiciled constituents.
2. **Company IR page "Periodo medio de pago a proveedores"** (the website duty in DA 3ª.2). Used for Santander and BBVA, whose JSON text blocks do not carry the note. These pages state the parent-company figure only.
3. CNMV (`cnmv.es`, informes financieros anuales) holds the same ESEF packages. Not needed.

Files: `data/manifests/es_pmp_sources.json`, `data/interim/es_pmp_sources.csv`, `data/interim/es_snippets/<TICKER>.txt`, raw in `data/raw/es/<TICKER>/`, constituents in `data/interim/ibex35_constituents.csv`.

IBEX 35 composition: BME "Composición histórica IBEX 35" PDF, September 2026 edition (https://www.bolsasymercados.es/dam/descargas/indices/composicion-ibex-35-es-en.pdf). Last change 22 July 2024 (Puig in, Meliá out); every review through 21 Sept 2026 left it unchanged.

## Gotchas for extractors

- **Scope.** The consolidated table covers only the **Spanish entities** of the group, after intragroup eliminations (ICAC art. 2.2 and 6.2). It is not a global group figure. Label it "Spanish group entities". Individual (parent-only) accounts carry a separate table; IR pages of Santander and BBVA give the parent-only figure. Record which one was extracted and never compare them as like for like.
- **Non-Spanish parents.** Ferrovial SE (Netherlands since 2023) and ArcelorMittal (Luxembourg) are IBEX constituents but not Spanish sociedades: no PMP note found in their group reports. Report them as not available, not as zero.
- **Banks and insurers** disclose too, but supplier payments are a small part of their business. Keep, flag `is_financial`, exclude from rankings of commercial payers.
- **Fiscal years.** Inditex FY2025 ends 31 Jan 2026. Logista FY2025 ends 30 Sept 2025.
- **Units vary**: days as integers or with decimals (Spanish decimal comma), amounts in euros, thousands or millions. Some tables have three year columns (CaixaBank).
- **Text artefacts.** Endesa's text has letter-spacing artefacts ("2 1 .0 91" = 21.091). Snippets come from HTML-to-text conversion, so table cells are flattened in reading order: current year first, prior year second.
- **Narrative-only disclosures.** Some companies give the PMP in a sentence, not a table (seen in the Unicaja snippet).
- **Duplicates.** Nested text-block tags repeat the same note; snippets are de-duplicated but an extractor should expect repeats.
- **PMcM and other analyses.** The Plataforma Multisectorial contra la Morosidad publishes its own analyses based on CNMV data, with much higher figures for IBEX non-financials than the statutory PMP. Its method is not the ICAC formula (PMcM's exact method was not verified in this pass). Never mix or compare them in one column. Same for our own computed DPO.
- **Self-reported.** PMP is prepared by the company and audited as part of the notes; confirming (reverse factoring) arrangements can shorten the reported PMP while the cash cost shifts to banks. Endesa's note, for example, describes its confirming lines right next to the table.
