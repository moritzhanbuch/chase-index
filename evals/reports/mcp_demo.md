# MCP server demo

Run at 2026-11-17T22:10:46+00:00. The script starts `mcp/server.py` over stdio with the official MCP Python SDK client, lists the tools and calls each one. Below each call is the short answer the tool returns before its Details block.

## Result

- Tools listed: 12 (expected 12)
- Calls checked: 19, passed: 19
- Failures: none

| Subject | Call | OK |
|---|---|---|
| first run | `start_here()` | yes |
| this week | `weekly_queue(limit=3)` | yes |
| demo | `weekly_queue(limit=3, demo=True)` | yes |
| Nestlé | `get_account_brief(company=Nestlé)` | yes |
| Nestlé | `get_payment_profile(company=Nestlé)` | yes |
| Nestlé | `search_companies(query=Nestlé, limit=3)` | yes |
| Telefónica | `get_account_brief(company=Telefónica)` | yes |
| Telefónica | `get_payment_profile(company=Telefónica)` | yes |
| Telefónica | `search_companies(query=Telefónica, limit=3)` | yes |
| Walmart | `get_account_brief(company=Walmart)` | yes |
| Walmart | `get_payment_profile(company=Walmart)` | yes |
| Walmart | `search_companies(query=Walmart, limit=3)` | yes |
| munich | `dinner_builder(city=munich)` | yes |
| since 2026-09-01 | `triggers(since=2026-09-01, limit=5)` | yes |
| DE | `top_targets(country=DE, limit=3)` | yes |
| Tesco Stores | `lookup_uk_supplier_payment_record(customer=Tesco Stores, limit=2)` | yes |
| Nestlé | `account_workspace(company=Nestlé)` | yes |
| local | `byod_status()` | yes |
| DPO | `explain_methodology(topic=DPO)` | yes |

## Tools exposed

- `start_here`: Start here. Explains in five lines what the Chase Index does and suggests three questions to ask.
- `weekly_queue`: This week's sales queue: which accounts to contact this week and what to open with. Use for "what's in this
- `get_account_brief`: Brief on one company before a call, meeting or email. Use for "brief on Reckitt", "prep me for Siemens Energy",
- `dinner_builder`: Who to invite to a finance-leader dinner in a city. Use for "who should we invite to the Munich dinner",
- `triggers`: What changed recently across all accounts: new UK filings that crossed 60 days or got slower, longer payment
- `top_targets`: The standing ranked target list, filtered by country, HQ city, sector or tier. Use for "top targets in Germany",
- `get_payment_profile`: Only the payment facts for one company, no sales angle: reported days to pay, share paid late and after 60
- `lookup_uk_supplier_payment_record`: Supplier-side lookup of one UK legal entity (any size, not only ranked groups): its latest statutory payment
- `search_companies`: Find the exact company in the index when a name is ambiguous or misspelled. Returns names, countries, tiers and ids.
- `account_workspace`: Full raw record for one account, for a deep dive or an export: the brief plus every UK filing feature, every dated
- `byod_status`: Check which of the user's own data files are loaded (CRM pipeline, network suppliers, dinner attendees,
- `explain_methodology`: How the numbers are built: sources, definitions, scoring, estimates and limits. Use for "how is the score

### `start_here` 

```text
1. The Chase Index ranks 1,920 large companies by how slowly they pay suppliers, from official filings (UK statutory reports, Spanish PMP) and computed DPO.
2. Each week it picks 25 accounts with a reason to call now (a new slower UK filing, longer terms, an e-invoicing deadline), who to ask for and a draft opener.
3. Every number links to its official source. Reported figures, computed proxies and estimates are labelled and never mixed.
4. It drafts, it never sends: openers and invite lines are human-written templates with the numbers filled in.
5. Read-only and local: no network calls, no names of individuals, public company-level data only.

Try asking:
- "What's in this week's queue, and what do I open with?"
- "Brief me on Reckitt."
- "Who should we invite to the Munich dinner?"

Independent project by Moritz Hanbuch.
```

### `weekly_queue` {'limit': 3}

```text
**Week 2026-47 queue: top 3 of 25 accounts this week** (picked from 384 eligible). 1 dinner invite, 2 cold email.

**1. Siemens Energy AG** (DE, Tier 1): dinner invite, ask for the group treasurer or CFO office
   - Why now: Siemens Energy Limited (single UK entity) now reports 70 days to pay on average, up from 55 a year earlier (+2 more events) [source](https://check-payment-practices.service.gov.uk/report/117930)
   - Open with: "We're hosting our next small dinner for finance leaders in Munich. One number made me think of you: Siemens Energy's UK entities took 17 days longer to pay suppliers than a year earlier: a weighted UK average of 76 days across 4 entities (by invoice value), against a UK median of 32. You know the story behind it better than I do, and I'd like to hear it. No deck." [source](https://check-payment-practices.service.gov.uk/report/118651)
**2. Alstom** (FR, Tier 1): cold email, ask for the head of accounts payable or shared services
   - Why now: Alstom Engineering and Services Limited (single UK entity) now reports 65 days to pay on average, up from 52 a year earlier (+2 more events) [source](https://check-payment-practices.service.gov.uk/report/118240)
   
... (truncated)
```

### `weekly_queue` {'limit': 3, 'demo': True}

```text
**Week 2026-47 queue: top 3 of 25 accounts this week** (picked from 358 eligible). 2 warm via supplier, 1 brief owner. SYNTHETIC demo CRM data applied.

**1. Nestlé** (CH, Tier 1): warm via supplier, ask for the group treasurer or CFO office
   - Why now: Nestle UK LTD. (single UK entity) now reports 76 days to pay on average, up from 56 a year earlier (+2 more events) [source](https://check-payment-practices.service.gov.uk/report/115234)
   - Open with: "SYNTHETIC Packaging Supplier GmbH already settles invoices with us and counts Nestlé among its customers. Nestlé's UK entities took 14 days longer to pay suppliers than a year earlier: a weighted UK average of 70 days across 7 entities (by invoice value), against a UK median of 32. I'd like to show you what the same invoices look like from your side. Twenty minutes?" [source](https://check-payment-practices.service.gov.uk/report/115188)
**2. Reckitt Benckiser Group plc** (GB, Tier 1): warm via supplier, ask for the group treasurer or CFO office
   - Why now: Reckitt Benckiser Health Limited (single UK entity) now reports 77 days to pay on average, up from 59 a year earlier (+2 more events) [source](https://check-payment-practices.
... (truncated)
```

### `get_account_brief` {'company': 'Nestlé'}

```text
**Nestlé**: Tier 1, rank 5 of 1,920, queue #3 this week. Consumer goods, HQ Vevey, CH.

- Key number: REPORTED (UK): Nestlé's 7 UK entities pay suppliers in 70 days on average (weighted by invoice value), against a UK median of 32; 63% of invoices paid after 60 days, 6% paid after the agreed terms. Half-year to 2026-06-30. Slowest: Nestle Purina UK Manufacturing Operations Limited at 78 days. [source](https://check-payment-practices.service.gov.uk/report/115188)
- Why now: Nestle UK LTD. (single UK entity) now reports 76 days to pay on average, up from 56 a year earlier (+2 more events) [source](https://check-payment-practices.service.gov.uk/report/115234)
- Open with (draft, cold email): "Nestlé's UK entities took 14 days longer to pay suppliers than a year earlier: a weighted UK average of 70 days across 7 entities (by invoice value), against a UK median of 32. If those terms are on purpose, some of your suppliers would probably pay for earlier cash, inside limits your team sets. I sketched a range from your public filings and I'm sure it's wrong somewhere. Want to tell me where?"
- Ask for: Group treasurer or CFO office (long payment periods with few late invoices are a terms an
... (truncated)
```

### `get_payment_profile` {'company': 'Nestlé'}

```text
**Nestlé**: how long it takes to pay suppliers

- REPORTED (UK): Nestlé's 7 UK entities pay suppliers in 70 days on average (weighted by invoice value), against a UK median of 32; 63% of invoices paid after 60 days, 6% paid after the agreed terms. Half-year to 2026-06-30. Slowest: Nestle Purina UK Manufacturing Operations Limited at 78 days. [source](https://check-payment-practices.service.gov.uk/report/115188)

Independent project by Moritz Hanbuch.
```

### `search_companies` {'query': 'Nestlé', 'limit': 3}

```text
2 matches for 'Nestlé':
- Nestlé (CH, consumer goods, Tier 1, reported payment data), id nestle-q160746
- Nestle Holdings, INC. (US, consumer goods, Tier 3), id nestle-holdings-inc-leimqxp30
```

### `get_account_brief` {'company': 'Telefónica'}

```text
**Telefónica**: Tier 2, rank 198 of 1,920. Telecom, HQ Madrid, ES.

- Key number: REPORTED (Spain): average supplier payment period 48 days in FY2025 (prior year 51); legal maximum per payment 60. [source](https://filings.xbrl.org/549300EEJH4FEPDBBR25/2025-12-31/ESEF/ES/0/549300EEJH4FEPDBBR25-2025-12-31-1-es/reports/549300EEJH4FEPDBBR25-2025-12-31-1-es.xhtml)
- Also: REPORTED (UK): Telefónica's UK entity (Giffgaff Limited) pays suppliers in 47 days on average, against a UK median of 32; 32% of invoices paid after 60 days, 1% paid after the agreed terms. Half-year to 2026-06-30. [source](https://check-payment-practices.service.gov.uk/report/114140)
- Why now: From 6 October 2027, Spanish companies with turnover above EUR 8 million must issue and receive B2B e-invoices and report invoice status, including when each invoice is actually paid. [source](https://sede.agenciatributaria.gob.es/Sede/iva/factura-electronica/calendario-implantacion.html)
- Open with (draft, cold email): "Telefónica reported an average supplier payment period of 48 days in Spain for FY2025; the legal maximum per payment is 60. It's from your own filing, so you'll know what's behind it. My guess is a mix of deli
... (truncated)
```

### `get_payment_profile` {'company': 'Telefónica'}

```text
**Telefónica**: how long it takes to pay suppliers

- REPORTED (Spain): average supplier payment period 48 days in FY2025 (prior year 51); legal maximum per payment 60. [source](https://filings.xbrl.org/549300EEJH4FEPDBBR25/2025-12-31/ESEF/ES/0/549300EEJH4FEPDBBR25-2025-12-31-1-es/reports/549300EEJH4FEPDBBR25-2025-12-31-1-es.xhtml)
- REPORTED (UK): Telefónica's UK entity (Giffgaff Limited) pays suppliers in 47 days on average, against a UK median of 32; 32% of invoices paid after 60 days, 1% paid after the agreed terms. Half-year to 2026-06-30. [source](https://check-payment-practices.service.gov.uk/report/114140)

Independent project by Moritz Hanbuch.
```

### `search_companies` {'query': 'Telefónica', 'limit': 3}

```text
1 match for 'Telefónica':
- Telefónica (ES, telecom, Tier 2, reported payment data), id telefonica-q160229
```

### `get_account_brief` {'company': 'Walmart'}

```text
**Walmart**: Tier 3, rank 695 of 1,920. Retail, HQ Bentonville, US.

- Key number: COMPUTED PROXY (a balance-sheet ratio, not days to pay): DPO 43 days in FY2026, sector median 45. [source](https://www.sec.gov/Archives/edgar/data/104169/000010416926000055/)
- Why now: no dated trigger: standing evidence only
- No opener: Tier 3, so not in the queue. The evidence does not make it a priority.
- ESTIMATE (group, from the DPO proxy): early-payment discount opportunity USD 290m / USD 678m / USD 1.3bn a year (low / base / high, gross, assumptions in config/assumptions.yaml).

Drafts only: a person edits and sends every message. UK figures cover the group's UK legal entities, Spanish figures its Spanish entities. Independent project by Moritz Hanbuch.
```

### `get_payment_profile` {'company': 'Walmart'}

```text
**Walmart**: how long it takes to pay suppliers

- COMPUTED PROXY (a balance-sheet ratio, not days to pay): DPO 43 days in FY2026, sector median 45. [source](https://www.sec.gov/Archives/edgar/data/104169/000010416926000055/)

Independent project by Moritz Hanbuch.
```

### `search_companies` {'query': 'Walmart', 'limit': 3}

```text
1 match for 'Walmart':
- Walmart (US, retail, Tier 3), id walmart-q483551
```

### `dinner_builder` {'city': 'munich'}

```text
**Next Munich dinner: 10 accounts to invite.** 3 headquartered in the Munich area, 7 elsewhere in Germany. Each has a payment figure clearly above the benchmark: reported for 7, a computed DPO proxy (balance sheet, not days to pay) for 3.

1. **Siemens Energy AG** (Tier 1, Munich): Siemens Energy's UK entities took 17 days longer to pay suppliers than a year earlier: a weighted UK average of 76 days across 4 entities (by invoice value), against a UK median of 32. [source](https://check-payment-practices.service.gov.uk/report/118651)
2. **Hensoldt** (Tier 1, Taufkirchen): Hensoldt's balance sheet implies about 112 days of payables outstanding (computed DPO for FY2025, a proxy; sector median 63). [source](https://investors.hensoldt.net/media/document/a5ee9bbe-ee55-4b0f-960e-542b2dc673eb/assets/DE000HAG0005-JA-2025-EQ-E-00.pdf)
3. **Infineon Technologies** (Tier 2, Neubiberg): Infineon Technologies' balance sheet implies about 82 days of payables outstanding (computed DPO for FY2025, a proxy; sector median 55). [source](https://www.infineon.com/assets/row/public/documents/corporate/investors/annual-reports/2025/2025-annual-report-v01-00-en.pdf)
4. **Puma** (Tier 1, Herzogenaurach): Pu
... (truncated)
```

### `triggers` {'since': '2026-09-01', 'limit': 5}

```text
**48 dated events since 2026-09-01, 86 upcoming deadlines.**

- 2026-11-17 · Volkswagen Group: Next Munich dinner: account is on the DE shortlist
- 2026-11-17 · Infineon Technologies: Next Munich dinner: account is on the DE shortlist
- 2026-11-17 · Heidelberg Materials: Next Munich dinner: account is on the DE shortlist
- 2026-11-17 · Siemens Energy AG: Next Munich dinner: account is on the DE shortlist
- 2026-11-17 · Puma: Next Munich dinner: account is on the DE shortlist

Upcoming:
- 2027-01-01 · E-invoicing mandate deadline (binds the buyer itself) (country DE, 21 accounts) [source](https://www.gesetze-im-internet.de/ustg_1980/__27.html)
- 2027-01-01 · E-invoicing mandate deadline (binds the buyer's small suppliers) (country PL, 3 accounts) [source](https://ksef.podatki.gov.pl/etapy-wdrozenia-ksef/)
- 2027-09-01 · E-invoicing mandate deadline (binds the buyer's small suppliers) (country FR, 27 accounts) [source](https://www.impots.gouv.fr/professionnel/je-decouvre-la-facturation-electronique)
- 2027-10-06 · E-invoicing mandate deadline (binds the buyer itself) (country ES, 14 accounts) [source](https://sede.agenciatributaria.gob.es/Sede/iva/factura-electronica/calendario-impla
... (truncated)
```

### `top_targets` {'country': 'DE', 'limit': 3}

```text
**Top 3 of 81 ranked accounts (country DE).** Ranked by tier, reported evidence before proxies, then score.

1. **Siemens Energy AG** (DE, Tier 1): 76 days (reported). [source](https://check-payment-practices.service.gov.uk/report/118651) Four UK entities averaged 76.2 days with 51% of invoices paid after 60 days, and 4 of 4 with a prior report got slower. The newest filing is from early November, the group is based in Munich and a UK entity offers supply chain finance.
4. **Fresenius Medical Care** (DE, Tier 1): 95 days (reported). [source](https://check-payment-practices.service.gov.uk/report/114573) Fresenius Medical Care (UK) Limited averaged 95 days to pay, 8 more than a year earlier, with 56% of invoices paid late. A second UK entity is left out of the figure as an extreme value, so verify that filing before citing it.
43. **Puma** (DE, Tier 1): 52 days (reported). [source](https://check-payment-practices.service.gov.uk/report/116084) Puma United Kingdom Ltd, the one UK entity reporting, took 52 days to pay with 39% of invoices paid late, 9 days more than a year earlier. The evidence covers one UK entity only.

Independent project by Moritz Hanbuch.
```

### `lookup_uk_supplier_payment_record` {'customer': 'Tesco Stores', 'limit': 2}

```text
**Latest statutory payment reports for 'Tesco Stores'** (UK legal entities):

- Tesco Stores Limited (00519500): 43 days to pay on average, 1% paid after terms, standard terms 5 to 90 days. Half-year to 2026-08-30. [source](https://check-payment-practices.service.gov.uk/report/117091)

UK large-business median: 32 days. Independent project by Moritz Hanbuch.
```

### `account_workspace` {'company': 'Nestlé'}

```text
**Nestlé**: Tier 1, rank 5 of 1,920, queue #3 this week. Consumer goods, HQ Vevey, CH.

- Key number: REPORTED (UK): Nestlé's 7 UK entities pay suppliers in 70 days on average (weighted by invoice value), against a UK median of 32; 63% of invoices paid after 60 days, 6% paid after the agreed terms. Half-year to 2026-06-30. Slowest: Nestle Purina UK Manufacturing Operations Limited at 78 days. [source](https://check-payment-practices.service.gov.uk/report/115188)
- Why now: Nestle UK LTD. (single UK entity) now reports 76 days to pay on average, up from 56 a year earlier (+2 more events) [source](https://check-payment-practices.service.gov.uk/report/115234)
- Open with (draft, cold email): "Nestlé's UK entities took 14 days longer to pay suppliers than a year earlier: a weighted UK average of 70 days across 7 entities (by invoice value), against a UK median of 32. If those terms are on purpose, some of your suppliers would probably pay for earlier cash, inside limits your team sets. I sketched a range from your public filings and I'm sure it's wrong somewhere. Want to tell me where?"
- Ask for: Group treasurer or CFO office (long payment periods with few late invoices are a terms an
... (truncated)
```

### `byod_status` 

```text
**Your own data (your local files):** no files loaded; status file absent. 0 accounts flagged.
File formats: config/byod/README.md and config/status/README.md. Without these files the queue uses public data only.
```

### `explain_methodology` {'topic': 'DPO'}

```text
## Computed DPO (proxy)

DPO = trade payables at fiscal year end / cost of sales x 365, from XBRL facts in annual filings (SEC EDGAR for US filers and foreign private issuers; ESEF for EU and UK listed groups).

- It is a balance-sheet proxy. It includes accruals and timing effects and is not the same thing as reported days to pay. It is always labelled "computed DPO (proxy)".
- Where a company tags only a broad payables line ("trade and other payables") or reports costs by nature, the row is kept with lower confidence and the basis is stored.
- Banks and insurers are marked `not_applicable`. Values below 5 or above 365 days are flagged as suspicious and excluded from scoring.
- Sector medians use only clean rows (standard concepts, confidence 1.0).
- Germany, Ireland and Switzerland are not available from the ESEF source we used. German groups appear with DPO only when they also file with the SEC. Germany has no statutory payment-performance reporting comparable to the UK regime.
- Check: an independent recomputation from the original filings for 15 random companies (`evals/reports/dpo_check.md`).

### DACH slice: DPO from annual reports

For DAX 40 and MDAX members headquartered 
... (truncated)
```

