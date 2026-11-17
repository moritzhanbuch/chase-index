# /chase-brief skill demo

Run at 2026-11-17 23:28. Each block is the unedited output of `skill/chase-brief/scripts/chase_brief.py`. Cases: a reported-UK account, a reported-Spain account, a multi-entity UK account, a proxy-only account, a poor-fit account, a UK legal entity name (falls back to the group or the entity lookup) and a dinner shortlist.

Result: 7/7 runs exited cleanly and carry the disclaimer.

## `/chase-brief Nestlé`

```
**Nestlé**: Tier 1, rank 5 of 1,920, queue #3 this week. Consumer goods, HQ Vevey, CH.

- Key number: REPORTED (UK): Nestlé's 7 UK entities pay suppliers in 70 days on average (weighted by invoice value), against a UK median of 32; 63% of invoices paid after 60 days, 6% paid after the agreed terms. Half-year to 2026-06-30. Slowest: Nestle Purina UK Manufacturing Operations Limited at 78 days. [source](https://check-payment-practices.service.gov.uk/report/115188)
- Why now: Nestle UK LTD. (single UK entity) now reports 76 days to pay on average, up from 56 a year earlier (+2 more events) [source](https://check-payment-practices.service.gov.uk/report/115234)
- Open with (draft, cold email): "Nestlé's UK entities took 14 days longer to pay suppliers than a year earlier: a weighted UK average of 70 days across 7 entities (by invoice value), against a UK median of 32. If those terms are on purpose, some of your suppliers would probably pay for earlier cash, inside limits your team sets. I sketched a range from your public filings and I'm sure it's wrong somewhere. Want to tell me where?"
- Ask for: Group treasurer or CFO office (long payment periods with few late invoices are a terms and working-capital topic).
- ESTIMATE (UK entities): early-payment discount opportunity GBP 2m / GBP 4m / GBP 8m a year (low / base / high, gross, assumptions in config/assumptions.yaml).
- One-pager: <repo>/outputs/one_pagers/nestle-q160746.html

Drafts only: a person edits and sends every message. UK figures cover the group's UK legal entities, Spanish figures its Spanish entities. Independent project by Moritz Hanbuch.
```

## `/chase-brief Telefónica`

```
**Telefónica**: Tier 2, rank 198 of 1,920. Telecom, HQ Madrid, ES.

- Key number: REPORTED (Spain): average supplier payment period 48 days in FY2025 (prior year 51); legal maximum per payment 60. [source](https://filings.xbrl.org/549300EEJH4FEPDBBR25/2025-12-31/ESEF/ES/0/549300EEJH4FEPDBBR25-2025-12-31-1-es/reports/549300EEJH4FEPDBBR25-2025-12-31-1-es.xhtml)
- Also: REPORTED (UK): Telefónica's UK entity (Giffgaff Limited) pays suppliers in 47 days on average, against a UK median of 32; 32% of invoices paid after 60 days, 1% paid after the agreed terms. Half-year to 2026-06-30. [source](https://check-payment-practices.service.gov.uk/report/114140)
- Why now: From 6 October 2027, Spanish companies with turnover above EUR 8 million must issue and receive B2B e-invoices and report invoice status, including when each invoice is actually paid. [source](https://sede.agenciatributaria.gob.es/Sede/iva/factura-electronica/calendario-implantacion.html)
- Open with (draft, cold email): "Telefónica reported an average supplier payment period of 48 days in Spain for FY2025; the legal maximum per payment is 60. It's from your own filing, so you'll know what's behind it. My guess is a mix of deliberate terms and invoices stuck between AP and the supplier. Is that close?"
- Ask for: Group treasurer or CFO office (long payment periods with few late invoices are a terms and working-capital topic).
- ESTIMATE (UK entities): early-payment discount opportunity GBP 185k / GBP 431k / GBP 832k a year (low / base / high, gross, assumptions in config/assumptions.yaml).

Drafts only: a person edits and sends every message. UK figures cover the group's UK legal entities, Spanish figures its Spanish entities. Independent project by Moritz Hanbuch.
```

## `/chase-brief Rolls-Royce`

```
**Rolls-Royce**: Tier 1, rank 49 of 1,920. Manufacturing, HQ London, GB.

- Key number: REPORTED (UK): Rolls-Royce's 4 UK entities pay suppliers in 68 days on average (weighted by invoice value), against a UK median of 32; 74% of invoices paid after 60 days, 4% paid after the agreed terms. Half-year to 2026-06-30. Slowest: Rolls-Royce plc at 70 days. [source](https://check-payment-practices.service.gov.uk/report/114082)
- Why now: Rolls-Royce plc (single UK entity) reports 70 days to pay on average, 6 more than a year earlier (+1 more events) [source](https://check-payment-practices.service.gov.uk/report/114082)
- Open with (draft, cold email): "Rolls-Royce's UK entities paid 74% of supplier invoices after more than 60 days (weighted UK average 68 days across 4 entities; UK median 32). You also disclose a supplier finance programme (GBP 646m outstanding at 2025-12-31). I'd like to understand who it actually reaches, only the largest suppliers or the long tail too, and whether terms got longer when it started. Open to 20 minutes?"
- Ask for: Group treasurer or CFO office (long payment periods with few late invoices are a terms and working-capital topic).
- Watch: the annual report discloses a supplier finance programme with GBP 646m outstanding. Ask who it reaches and whether terms got longer with it. [source](https://filings.xbrl.org/213800EC7997ZBLZJH69/2025-12-31/ESEF/GB/0/213800EC7997ZBLZJH69-2025-12-31-T01.json)
- ESTIMATE (UK entities): early-payment discount opportunity GBP 20m / GBP 48m / GBP 92m a year (low / base / high, gross, assumptions in config/assumptions.yaml).

Drafts only: a person edits and sends every message. UK figures cover the group's UK legal entities, Spanish figures its Spanish entities. Independent project by Moritz Hanbuch.
```

## `/chase-brief Walmart`

```
**Walmart**: Tier 3, rank 695 of 1,920. Retail, HQ Bentonville, US.

- Key number: COMPUTED PROXY (a balance-sheet ratio, not days to pay): DPO 43 days in FY2026, sector median 45. [source](https://www.sec.gov/Archives/edgar/data/104169/000010416926000055/)
- Why now: no dated trigger: standing evidence only
- No opener: Tier 3, so not in the queue. The evidence does not make it a priority.
- ESTIMATE (group, from the DPO proxy): early-payment discount opportunity USD 290m / USD 678m / USD 1.3bn a year (low / base / high, gross, assumptions in config/assumptions.yaml).

Drafts only: a person edits and sends every message. UK figures cover the group's UK legal entities, Spanish figures its Spanish entities. Independent project by Moritz Hanbuch.
```

## `/chase-brief Deutsche Bank`

```
**Deutsche Bank**: Tier 3, rank 1489 of 1,920. Financials, HQ Frankfurt, DE.

- Key number: No payment evidence in the dataset for this company.
- Why now: no dated trigger: standing evidence only
- No opener: Tier 3, so not in the queue. The evidence does not make it a priority.

Drafts only: a person edits and sends every message. UK figures cover the group's UK legal entities, Spanish figures its Spanish entities. Independent project by Moritz Hanbuch.
```

## `/chase-brief Tesco Stores`

```
**Tesco**: Tier 3, rank 395 of 1,920. Retail, HQ Welwyn Garden City, GB.

- Key number: REPORTED (UK): Tesco's 11 UK entities pay suppliers in 43 days on average (weighted by invoice value), against a UK median of 32; 7% of invoices paid after 60 days, 1% paid after the agreed terms. Half-year to 2026-08-31. Slowest: Tesco Distribution Limited at 59 days. [source](https://check-payment-practices.service.gov.uk/report/117018)
- Why now: Maximum contractual payment period of 90 days reported by a UK entity [source](https://check-payment-practices.service.gov.uk/report/117018)
- No opener: Tier 3, so not in the queue. The evidence does not make it a priority.
- ESTIMATE (UK entities): early-payment discount opportunity GBP 38m / GBP 89m / GBP 172m a year (low / base / high, gross, assumptions in config/assumptions.yaml).

Drafts only: a person edits and sends every message. UK figures cover the group's UK legal entities, Spanish figures its Spanish entities. Independent project by Moritz Hanbuch.
```

## `/chase-brief --dinner madrid`

```
**Next Madrid dinner: 3 accounts to invite.** 0 headquartered in the Madrid area, 3 elsewhere in Spain. Each has a payment figure clearly above the benchmark: all reported.

1. **Grifols** (Tier 1, Sant Cugat del Vallès): Grifols' average supplier payment period in Spain rose from 71 to 78 days in FY2025; the legal maximum per payment is 60. [source](https://filings.xbrl.org/959800HSSNXWRKBK4N60/2025-12-31/ESEF/ES/0/959800HSSNXWRKBK4N60-2025-12-31-1-es/reports/959800HSSNXWRKBK4N60-2025-12-31-1-es.xhtml)
2. **Puig** (Tier 1, L'Hospitalet de Llobregat): Puig's average supplier payment period in Spain rose from 52 to 59 days in FY2025; the legal maximum per payment is 60. [source](https://filings.xbrl.org/549300OVHNSX30L1AQ94/2025-12-31/ESEF/ES/0/549300OVHNSX30L1AQ94-2025-12-31-es/reports/549300OVHNSX30L1AQ94-2025-12-31-es.xhtml)
3. **Acerinox SA** (Tier 1, HQ city unknown): Acerinox reported an average supplier payment period of 63 days in Spain for FY2025; the legal maximum per payment is 60. [source](https://filings.xbrl.org/95980020140005582721/2025-12-31/ESEF/ES/0/95980020140005582721-2025-12-31-1-es/reports/95980020140005582721-2025-12-31-1-es.xhtml)

Invite line (draft, for #1): "We're hosting our next small dinner for finance leaders in Madrid. One number made me think of you: Grifols' average supplier payment period in Spain rose from 71 to 78 days in FY2025; the legal maximum per payment is 60. You know the story behind it better than I do, and I'd like to hear it. No deck."

Bench (check before inviting): Cie Automotive SA (proxy only, on a broad payables line); Elecnor SA (proxy only, on cost of materials: reads high against the cost-of-sales sector median); Eroski Scoop (proxy only, on a broad payables line); Distribuidora Internacional de Alimentacion SA (proxy only, on a broad payables line); Gestamp Automocion SA (proxy only, on a broad payables line).

This is a country list: check where each finance leader actually sits before inviting. Drafts only: a person edits and sends every message. UK figures cover the group's UK legal entities, Spanish figures its Spanish entities. Independent project by Moritz Hanbuch.
```

