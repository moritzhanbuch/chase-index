# DPO recompute check (QA)

Checked by the `qa` subagent, independent of the pipeline. Script: `evals/dpo_check.py` (run `.venv/bin/python evals/dpo_check.py`; `explore` prints the statement lines). Date: 2026-11-16.

## What was checked
`data/processed/dpo.parquet`, rows with `year_rank == 1` and `dpo_flag == 'ok'`. Sample: `sample(n, random_state=20261116)`, 10 SEC rows and 5 ESEF rows, no cherry-picking. For each, payables and cost of sales were re-read and DPO = payables / cost x 365 recomputed. Pass = within 2 days of the table.

## Method
- SEC rows (10): read from the rendered financial statements (R-pages `R2..R8.htm`, plus note pages where the pipeline used a note line) in the EDGAR filing folder from `filing_url`, as printed, respecting the stated scale. Nothing from the XBRL API or pipeline code was used.
- ESEF rows (5): the iXBRL viewer documents are very large, so these are marked **independent re-derivation from xBRL-JSON**: own code (`esef_candidates` in the script, written from scratch, pipeline modules not read) lists undimensioned payable and cost facts at fiscal year end from the filing's xBRL-JSON. They were not read from the filing document.
- All HTTP through `chase.common.http.fetch`.

## Results

| Company | FY | Source | Payables as read (m) | Cost as read (m) | DPO recomputed | DPO in table | Diff (days) | Pass | Check type | Payables line | Cost line | Document |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| The Hershey Company | 2025 | sec | 1,255.7 | 7,769.9 | 59.0 | 59.0 | -0.01 | PASS | R-page | Accounts payable (balance sheet) | Cost of sales | https://www.sec.gov/Archives/edgar/data/47111/000162828026008586/ (R5.htm / R3.htm) |
| Diageo | 2025 | sec | 6,952.0 | 8,072.0 | 314.4 | 314.4 | -0.04 | PASS | R-page | Trade and other payables (balance sheet, current) | Cost of sales | https://www.sec.gov/Archives/edgar/data/835403/000083540325000021/ (R5.htm / R3.htm) |
| Alcoa Corp | 2025 | sec | 1,938.0 | 10,658.0 | 66.4 | 66.4 | -0.03 | PASS | R-page | Accounts payable, trade | Cost of goods sold (excl. D&A) | https://www.sec.gov/Archives/edgar/data/1675149/000119312526077167/ (R4.htm / R2.htm) |
| Ardagh Metal Packaging S.A. | 2025 | sec | 1,266.0 | 4,816.0 | 95.9 | 96.0 | -0.05 | PASS | R-page (note 23, R131) | Trade payables (note: Trade and other payables); face shows Trade and other payables 1,539 | Cost of sales | https://www.sec.gov/Archives/edgar/data/1845097/000110465926024068/ (R131.htm / R2.htm) |
| Colgate-Palmolive Company | 2025 | sec | 2,089.0 | 8,131.0 | 93.8 | 93.8 | -0.02 | PASS | R-page | Accounts payable | Cost of sales | https://www.sec.gov/Archives/edgar/data/21665/000002166526000006/ (R5.htm / R3.htm) |
| StandardAero, Inc. | 2025 | sec | 679.8 | 5,165.1 | 48.0 | 48.0 | +0.04 | PASS | R-page | Accounts payable | Cost of revenue | https://www.sec.gov/Archives/edgar/data/2025410/000119312526072618/ (R2.htm / R4.htm) |
| Rio Tinto plc | 2025 | sec | 3,596.0 | 41,784.0 | 31.4 | 31.4 | +0.01 | PASS | R-page (note, R75) | Trade payables (note; face shows Trade and other payables 10,133) | Net operating costs (excl. items disclosed separately) | https://www.sec.gov/Archives/edgar/data/863064/000162828026009531/ (R75.htm / R2.htm) |
| Lowe's | 2026 | sec | 9,762.0 | 57,401.0 | 62.1 | 62.1 | -0.03 | PASS | R-page | Accounts payable | Cost of sales | https://www.sec.gov/Archives/edgar/data/60667/000006066726000029/ (R5.htm / R3.htm) |
| APi Group Corp | 2025 | sec | 526.0 | 5,424.0 | 35.4 | 35.4 | -0.00 | PASS | R-page | Accounts payable | Cost of revenues | https://www.sec.gov/Archives/edgar/data/1796209/000162828026011620/ (R3.htm / R5.htm) |
| Viatris Inc | 2025 | sec | 1,754.1 | 9,286.4 | 68.9 | 68.9 | +0.04 | PASS | R-page | Accounts payable | Cost of sales | https://www.sec.gov/Archives/edgar/data/1792044/000179204426000013/ (R3.htm / R5.htm) |
| Ramsay Generale de Sante | 2026 | esef | 427.7 | 1,150.7 | 135.7 | 135.7 | -0.03 | PASS | independent re-derivation from xBRL-JSON | TradeAndOtherCurrentPayablesToTradeSuppliers @2026-06-30 | RawMaterialsAndConsumablesUsed FY | https://filings.xbrl.org/969500I1EJGUAT223F44/2026-06-30/ESEF/FR/0/ramsaysante-2026-06-30-1-fr.json (xBRL-JSON) |
| Iveco Group N.V. | 2025 | esef | 3,753.0 | 11,328.0 | 120.9 | 120.9 | +0.03 | PASS | independent re-derivation from xBRL-JSON | TradeAndOtherPayablesToTradeSuppliers @2025-12-31 | CostOfSales FY | https://filings.xbrl.org/549300ZWF2ZJDD9EOR96/2025-12-31/ESEF/NL/0/ivecogroupnv-2025-12-31-1-en.json (xBRL-JSON) |
| Distribuidora Internacional de Alimentacion SA | 2025 | esef | 958.4 | 4,215.0 | 83.0 | 83.0 | -0.01 | PASS | independent re-derivation from xBRL-JSON | TradeAndOtherCurrentPayables @2025-12-31 | RawMaterialsAndConsumablesUsed FY | https://filings.xbrl.org/54930063C6K2TNFL6H10/2025-12-31/ESEF/ES/0/54930063C6K2TNFL6H10-2025-12-31-en.json (xBRL-JSON) |
| Esprinet S.p.a. | 2025 | esef | 1,330.4 | 4,057.0 | 119.7 | 119.7 | -0.00 | PASS | independent re-derivation from xBRL-JSON | TradeAndOtherCurrentPayablesToTradeSuppliers @2025-12-31 | CostOfSales FY | https://filings.xbrl.org/8156007E3375956ADD08/2025-12-31/ESEF/IT/1/8156007E3375956ADD08-2025-12-31-1-it.json (xBRL-JSON) |
| Cie Automotive SA | 2025 | esef | 925.8 | 2,240.5 | 150.8 | 150.8 | +0.02 | PASS | independent re-derivation from xBRL-JSON | TradeAndOtherCurrentPayables @2025-12-31 | RawMaterialsAndConsumablesUsed FY | https://filings.xbrl.org/95980020140005381252/2025-12-31/ESEF/ES/0/95980020140005381252-2025-12-31-1-es.json (xBRL-JSON) |

**Overall: 15/15 within 2 days** (max absolute difference 0.05 days, i.e. rounding). Arithmetic and extraction are correct for every sampled row.

## Failures
None on the arithmetic test.

## Caveats (concept choice, not extraction errors; these affect how far the proxy can be trusted)

1. **Diageo, DPO 314 days, flagged `ok`.** The pipeline used the face line `Trade and other payables` (USD 6,952m), which includes excise duties, accruals and other non-trade items, over cost of sales (USD 8,072m, which excludes excise duties). The number matches the statement but is not a supplier-payment measure. Recommend flagging DPO > ~200 as suspicious, or preferring the trade-payables note line when available.
2. **Ardagh Metal Packaging and Rio Tinto:** the pipeline used a note-level line (`TradeAndOtherCurrentPayablesToTradeSuppliers`: Ardagh trade payables 1,266 vs face 'Trade and other payables' 1,539; Rio trade payables 3,596 vs face 'Trade and other payables' 10,133). I confirmed both figures in the filing notes (Ardagh R131, Rio R75). This is the better choice, but it differs from what the face of the balance sheet shows, so a reader checking the balance sheet would see a different number. Using the face lines would give Ardagh 116.6 days and Rio 88.7 days.
3. **Rio Tinto cost denominator** is `Net operating costs (excluding items disclosed separately)` (USD 41,784m, tagged OperatingExpense), not a cost-of-sales line (Rio reports none). It is a broad cost base that includes employee, energy and other costs, so DPO is understated relative to a purchases base.
4. **Ramsay, DIA, CIE Automotive** use `RawMaterialsAndConsumablesUsed` (purchases/consumables) as the cost base because there is no cost-of-sales line. It matches the filing, but it is a narrow base (Ramsay: 21% of revenue; CIE: 57% of revenue, 64% of total operating expense), so DPO is overstated for service/labour-heavy businesses (Ramsay is a hospital group). DIA and CIE also use `TradeAndOtherCurrentPayables` (not trade-only; CIE also reports TradeAndOtherPayables 998.4m).
5. Lowe's FY ending 2026-01-30 is labelled `fiscal_year` 2026 in the table (the company calls it fiscal 2025). Cosmetic, period_end is correct.
6. Ardagh's R-pages header says `€ in Millions` but the statements are in USD; the DPO ratio is unaffected. The table's `currency` for Ardagh is USD.
7. Sample size is 15 of the `ok` latest-year rows; it checks correctness of extraction and arithmetic, not whether DPO is a good proxy for days to pay.
8. SEC rows were verified against the filings' rendered R-pages (the same XBRL data the SEC renders), not the PDF/HTML 10-K text; the ESEF rows are a second derivation from the same xBRL-JSON the pipeline used, so they confirm concept selection and arithmetic but are not independent of the filer's tagging.
