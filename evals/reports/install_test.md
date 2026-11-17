# Install test, as a stranger

Date: 2026-11-17. Method: `git clone` of this repository into an empty temp folder, an **empty uv cache** (as on a machine that never ran this project), then the MCP server started with the exact command from `.claude-plugin/plugin.json` through the official MCP Python SDK client. Re-run: `uv run python evals/install_test.py`.

Not run, on purpose: `claude plugin marketplace add` and `claude plugin install`, which change the machine's Claude Code configuration. Teammates need `uv` on the PATH.

| Check | Command (in the clone) | Result |
|---|---|---|
| MCP server, the plugin's exact command | `uv run --quiet --project <clone> python <clone>/mcp/server.py` | 12 tools. First start 17 s with an empty uv cache (installs dependencies), second start 0.4 s |
| Skill entry point | `uv run --quiet chase-brief --queue 3` | OK, queue printed with openers and source links (1 s) |
| Test suite | `uv run --quiet --extra build python -m pytest -q` | OK, 318 passed, 3 skipped in 32.54s (38 s) |
| Workspace build | `uv run --quiet python workspace/build.py` | OK, workspace: 100 account pages, 25 queued, 282 live public triggers, 4 dinner cities, 29 one-pagers -> workspace/dist (20 s) |
| Plugin and marketplace manifests | `claude plugin validate .` | Passed |
| Clone left clean (read-only tools) | `git status --porcelain` | clean |

**Overall: PASS.**

## `start_here`

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

## The three questions from the README

Each tool returns this short answer first, then a compact `Details (structured)` block for the calling agent (not shown). Claude relays the short answer.

### "What's in this week's queue, and what do I open with?"

Tool: `weekly_queue()`, answered in 0.2 s. Check: 960 words, 15 source links, opener: yes, JSON in the answer: no.

```text
**Week 2026-47 queue: top 10 of 25 accounts this week** (picked from 384 eligible). 1 dinner invite, 9 cold email.

**1. Siemens Energy AG** (DE, Tier 1): dinner invite, ask for the group treasurer or CFO office
   - Why now: Siemens Energy Limited (single UK entity) now reports 70 days to pay on average, up from 55 a year earlier (+2 more events) [source](https://check-payment-practices.service.gov.uk/report/117930)
   - Open with: "We're hosting our next small dinner for finance leaders in Munich. One number made me think of you: Siemens Energy's UK entities took 17 days longer to pay suppliers than a year earlier: a weighted UK average of 76 days across 4 entities (by invoice value), against a UK median of 32. You know the story behind it better than I do, and I'd like to hear it. No deck." [source](https://check-payment-practices.service.gov.uk/report/118651)
**2. Alstom** (FR, Tier 1): cold email, ask for the head of accounts payable or shared services
   - Why now: Alstom Engineering and Services Limited (single UK entity) now reports 65 days to pay on average, up from 52 a year earlier (+2 more events) [source](https://check-payment-practices.service.gov.uk/report/118240)
   - Open with: "Alstom's UK entities took 13 days longer to pay suppliers than a year earlier: a weighted UK average of 66 days across 3 entities (by invoice value), against a UK median of 32. They also paid 31% of invoices after the agreed terms. In most AP teams paying after terms isn't a decision, it's invoices waiting on a match or an answer from the supplier. Worth 20 minutes on how agents on both sides clear that?" [source](https://check-payment-practices.service.gov.uk/report/118196)
   - Context: discloses a supplier finance programme (one reader, unconfirmed). Ask who it reaches and whether terms got longer with it. Context, not a reason to call.
**3. Nestlé** (CH, Tier 1): cold email, ask for the group treasurer or CFO office
   - Why now: Nestle UK LTD. (single UK entity) now reports 76 days to pay on average, up from 56 a year earlier (+2 more events) [source](https://check-payment-practices.service.gov.uk/report/115234)
   - Open with: "Nestlé's UK entities took 14 days longer to pay suppliers than a year earlier: a weighted UK average of 70 days across 7 entities (by invoice value), against a UK median of 32. If those terms are on purpose, some of your suppliers would probably pay for earlier cash, inside limits your team sets. I sketched a range from your public filings and I'm sure it's wrong somewhere. Want to tell me where?" [source](https://check-payment-practices.service.gov.uk/report/115188)
**4. GE Vernova Inc.** (US, Tier 1): cold email, ask for the group treasurer or CFO office
   - Why now: UK Grid Solutions Limited (single UK entity) reports 57 days to pay on average, 9 more than a year earlier (+2 more events) [source](https://check-payment-practices.service.gov.uk/report/113926)
   - Open with: "GE Vernova's UK entities paid 43% of supplier invoices after more than 60 days (weighted UK average 61 days across 5 entities; UK median 32). You also disclose a supplier finance programme (USD 1,542m outstanding at 2025-12-31). I'd like to understand who it actually reaches, only the largest suppliers or the long tail too, and whether terms got longer when it started. Open to 20 minutes?" [source](https://check-payment-practices.service.gov.uk/report/114590)
   - Context: discloses a supplier finance programme. Ask who it reaches and whether terms got longer with it. Context, not a reason to call.
**5. Reckitt Benckiser Group plc** (GB, Tier 1): cold email, ask for the group treasurer or CFO office
   - Why now: Reckitt Benckiser Health Limited (single UK entity) now reports 77 days to pay on average, up from 59 a year earlier (+2 more events) [source](https://check-payment-practices.service.gov.uk/report/113505)
   - Open with: "Reckitt's UK entities paid 50% of supplier invoices after more than 60 days (weighted UK average 79 days across 6 entities; UK median 32). Your annual report also discloses a supplier finance programme (GBP 277m outstanding at 2025-12-31), so early cash is already on offer to some suppliers. Two questions I'd like your view on: which suppliers does it actually reach, and did payment terms get longer when it came in?" [source](https://check-payment-practices.service.gov.uk/report/113069)
   - Context: discloses a supplier finance programme. Ask who it reaches and whether terms got longer with it. Context, not a reason to call.

**Next 5** (ask "brief me on <company>" for the opener):
6. **LKQ Corporation** (US, Tier 1), cold email to the head of accounts payable or shared services. Why now: Lkq Group (UK) Limited (single UK entity) reports 86 days to pay on average, 23 more than a year earlier [source](https://check-payment-practices.service.gov.uk/report/114769)
7. **Publicis** (FR, Tier 1), cold email to the head of accounts payable or shared services. Why now: Apx Trading Limited (single UK entity) now reports 87 days to pay on average, up from 53 a year earlier [source](https://check-payment-practices.service.gov.uk/report/114790)
8. **Johnson Matthey plc** (GB, Tier 1), cold email to the head of accounts payable or shared services. Why now: Johnson Matthey Hydrogen Technologies Limited (single UK entity) now reports 65 days to pay on average, up from 53 a year earlier [source](https://check-payment-practices.service.gov.uk/report/118567)
9. **Heineken N.V.** (NL, Tier 1), cold email to the group treasurer or CFO office. Why now: Heineken UK Limited (single UK entity) reports 93 days to pay on average, 17 more than a year earlier [source](https://check-payment-practices.service.gov.uk/report/116547)
10. **Prysmian Group** (IT, Tier 1), cold email to the head of accounts payable or shared services. Why now: Prysmian Cables & Systems Limited (single UK entity) now reports 62 days to pay on average, up from 59 a year earlier [source](https://check-payment-practices.service.gov.uk/report/116280)

The opener's first sentence is the key number; [source] is its official filing. For any account: "brief me on <company>". The full week is 25: ask for all 25.
Drafts only: a person edits and sends every message. UK figures cover the group's UK legal entities, Spanish figures its Spanish entities. Independent project by Moritz Hanbuch.
```

### "Brief me on Reckitt."

Tool: `get_account_brief(company='Reckitt')`, answered in 0.3 s. Check: 279 words, 3 source links, opener: yes, JSON in the answer: no.

```text
**Reckitt Benckiser Group plc**: Tier 1, rank 8 of 1,920, queue #5 this week. Consumer goods, headquartered in GB.

- Key number: REPORTED (UK): Reckitt's 6 UK entities pay suppliers in 79 days on average (weighted by invoice value), against a UK median of 32; 50% of invoices paid after 60 days, 14% paid after the agreed terms. Half-year to 2026-06-30. Slowest: Reckitt Benckiser Healthcare International Limited at 132 days. [source](https://check-payment-practices.service.gov.uk/report/113069)
- Why now: Reckitt Benckiser Health Limited (single UK entity) now reports 77 days to pay on average, up from 59 a year earlier (+2 more events) [source](https://check-payment-practices.service.gov.uk/report/113505)
- Open with (draft, cold email): "Reckitt's UK entities paid 50% of supplier invoices after more than 60 days (weighted UK average 79 days across 6 entities; UK median 32). Your annual report also discloses a supplier finance programme (GBP 277m outstanding at 2025-12-31), so early cash is already on offer to some suppliers. Two questions I'd like your view on: which suppliers does it actually reach, and did payment terms get longer when it came in?"
- Ask for: Group treasurer or CFO office (long payment periods with few late invoices are a terms and working-capital topic).
- Watch: the annual report discloses a supplier finance programme with GBP 277m outstanding. Ask who it reaches and whether terms got longer with it. [source](https://filings.xbrl.org/5493003JFSMOJG48V108/2025-12-31/ESEF/GB/0/5493003JFSMOJG48V108-2025-12-31-T01.json)
- ESTIMATE (UK entities): early-payment discount opportunity GBP 4m / GBP 10m / GBP 20m a year (low / base / high, gross, assumptions in config/assumptions.yaml).
- One-pager: <clone>/outputs/one_pagers/reckitt-benckiser-group-plc-lei48v108.html

Drafts only: a person edits and sends every message. UK figures cover the group's UK legal entities, Spanish figures its Spanish entities. Independent project by Moritz Hanbuch.
```

### "Who should we invite to the Munich dinner?"

Tool: `dinner_builder(city='munich')`, answered in 0.0 s. Check: 521 words, 10 source links, opener: yes, JSON in the answer: no.

```text
**Next Munich dinner: 10 accounts to invite.** 3 headquartered in the Munich area, 7 elsewhere in Germany. Each has a payment figure clearly above the benchmark: reported for 7, a computed DPO proxy (balance sheet, not days to pay) for 3.

1. **Siemens Energy AG** (Tier 1, Munich): Siemens Energy's UK entities took 17 days longer to pay suppliers than a year earlier: a weighted UK average of 76 days across 4 entities (by invoice value), against a UK median of 32. [source](https://check-payment-practices.service.gov.uk/report/118651)
2. **Hensoldt** (Tier 1, Taufkirchen): Hensoldt's balance sheet implies about 112 days of payables outstanding (computed DPO for FY2025, a proxy; sector median 63). [source](https://investors.hensoldt.net/media/document/a5ee9bbe-ee55-4b0f-960e-542b2dc673eb/assets/DE000HAG0005-JA-2025-EQ-E-00.pdf)
3. **Infineon Technologies** (Tier 2, Neubiberg): Infineon Technologies' balance sheet implies about 82 days of payables outstanding (computed DPO for FY2025, a proxy; sector median 55). [source](https://www.infineon.com/assets/row/public/documents/corporate/investors/annual-reports/2025/2025-annual-report-v01-00-en.pdf)
4. **Puma** (Tier 1, Herzogenaurach): Puma's UK entity paid 39% of supplier invoices later than the agreed terms (52 days on average; UK median 32). [source](https://check-payment-practices.service.gov.uk/report/116084)
5. **Rheinmetall AG** (Tier 1, Düsseldorf): Rheinmetall's UK entity paid 45% of supplier invoices later than the agreed terms (50 days on average; UK median 32). [source](https://check-payment-practices.service.gov.uk/report/114773)
6. **Brenntag** (Tier 1, Essen): Brenntag's UK entity paid 30% of supplier invoices later than the agreed terms (48 days on average; UK median 32). [source](https://check-payment-practices.service.gov.uk/report/114052)
7. **Heidelberg Materials** (Tier 1, Heidelberg): Heidelberg Materials' UK entities paid 38% of supplier invoices later than the agreed terms (weighted UK average 48 days across 9 entities; UK median 32). [source](https://check-payment-practices.service.gov.uk/report/113632)
8. **Continental AG** (Tier 1, Hanover): Continental's UK entities reported paying suppliers in a weighted UK average of 46 days across 3 entities (by invoice value), against a UK median of 32. [source](https://check-payment-practices.service.gov.uk/report/109396)
9. **CTS Eventim** (Tier 1, Bremen): CTS Eventim's balance sheet implies about 62 days of payables outstanding (computed DPO for FY2025, a proxy; sector median 26). [source](https://corporate.eventim.de/media/document/b42d98d3-2f3a-430e-8cec-44aec6529782/assets/DE0005470306-JA-2025-EQ-E-00.pdf)
10. **Volkswagen Group** (Tier 2, Wolfsburg): Volkswagen Group's UK entities reported paying suppliers in a weighted UK average of 46 days across 4 entities (by invoice value), against a UK median of 32. [source](https://check-payment-practices.service.gov.uk/report/113794)

Invite line (draft, for #1): "We're hosting our next small dinner for finance leaders in Munich. One number made me think of you: Siemens Energy's UK entities took 17 days longer to pay suppliers than a year earlier: a weighted UK average of 76 days across 4 entities (by invoice value), against a UK median of 32. You know the story behind it better than I do, and I'd like to hear it. No deck."

Bench (check before inviting): Fresenius Medical Care (thin evidence: UK invoice value under 1% of group revenue); Bayer (thin evidence: UK invoice value under 1% of group revenue); Lanxess (thin evidence: UK invoice value under 1% of group revenue); Robert Bosch (thin evidence: UK invoice value under 1% of group revenue); Knorr-Bremse (proxy only, on cost of materials: reads high against the cost-of-sales sector median).

This is a country list: check where each finance leader actually sits before inviting. Drafts only: a person edits and sends every message. UK figures cover the group's UK legal entities, Spanish figures its Spanish entities. Independent project by Moritz Hanbuch.
```

## Review

Judged as a COO-style reviewer would (short, specific, correct):

- **Queue:** leads with the week and the play mix, then the top 5 with one why-now line (filing link) and a ready opener whose first sentence is the key number, then the next 5 on one line each. Reads in about a minute. Fixed before this run: the first version printed all 10 openers (1,280 words) and the key number twice per account (once alone, once inside the opener), and supplier finance read as a positive signal; it is now "context, not a reason to call", with "unconfirmed" where only one reader saw it.
- **Brief on Reckitt:** the key number, why now, opener, who to ask for, the GBP 277m supplier finance programme as a question to ask, and the estimate labelled ESTIMATE with its range. Fixed before this run: for accounts scored on Spanish data (Telefónica) the key number showed the UK figure while the opener quoted the Spanish one; the key number now follows the evidence behind the score.
- **Munich dinner:** the header says how many accounts sit in the Munich area (3 since the DACH slice, up from 1) and how many elsewhere in Germany, and which figures are reported and which are a computed DPO proxy from the annual report. Each proxy line says "a proxy" and links the report. Fixed before this run: an earlier header claimed every figure was reported.
- **Still worth knowing:** the opener templates are the same human-written set for every account (two variants per type), so a reader comparing ten openers will see the pattern. That is on purpose (a model never writes the message), but a person should edit the second sentence before sending.
- **Correctness:** the figures in these answers were checked against the statutory filing rows in `data/processed/uk_payment_practices.parquet` (reports 113069, 113486, 113505, 117930, 118196, 118240, 118651): days to pay, prior-year values and shares all match. One thing a careful reader should know: on a group figure (for example "76 days on average" for Siemens Energy's UK entities) the [source] link opens the report of one entity, the slowest; the group figure is the invoice-value-weighted average of all linked entities, listed in the Details block.
