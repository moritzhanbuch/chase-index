# Chase Index workspace

The weekly GTM workspace: scoring, priority tiers and draft openers on top of the public data. Live demo:
https://chase-index-mh.vercel.app. Every page carries `noindex` and the deployment sends an `X-Robots-Tag: noindex` header,
so it stays out of search. The press-safe, company-level index site is in `site/`.

## What it is

A static page set a sales person opens on Monday morning:

| Page | What it shows |
|---|---|
| `index.html` (Queue) | CRM-style list, one row per account: company (initial avatar, name, tier dot, country), days to pay with a bar against the benchmark (median in the column header), the single strongest why-now pill, contact (Treasury or AP) and a status pill (click to cycle To do, Contacted, Meeting, Not now; kept in localStorage; **Export status** writes the `config/status/` CSV, Not now = `not_a_fit`, reason "not now"). Tabs: All, Treasury, AP, Dinner. Click a row (or Enter) for the side panel: key number and trend sparkline, evidence with source, every why-now item, the draft opener with Copy, who to ask for and why, play, priority, links to the account page and one-pager. Keys: `j`/`k` move (the panel follows), `c` copies the opener, `Esc` closes, `?` lists the shortcuts. |
| `accounts/<id>.html` | A CRM-style record per queued, top-100, dinner-list and ticker account. Header with tier, country · city · sector, status pill (same storage as the queue) and One-pager. "The angle": one sentence from the opener rules (template with data slots, no model text). KPI tiles with data only (days to pay vs benchmark, paid after 60 days, paid late, supplier finance with the prior-year arrow, trend). Main column: UK entities with mini bars vs the median, Spain, Why now (dated) and Standing facts that are not already shown elsewhere, Supplier finance with terms with and without the programme as range bars on one day axis; collapsed Proxy data (computed DPO with its caveat, never in the main view when there are reported figures or a broad payables basis), Opportunity estimate, How it's scored. Sticky right rail (on top on mobile): ask for with Find on LinkedIn, opener card with Copy, play and priority, links. |
| `dinners.html` | Per dinner city in `config/dinners.yaml` (real dates only in the gitignored `config/dinners.local.yaml`), grouped into City area and Rest of country. Rows: checkbox, company, HQ city, a short reason ("76d · +18d YoY", "SCF £277m"), the role to invite (CFO / Treasurer, CFO, or CFO / Head of AP), invite pill (click to cycle To invite, Invited, Confirmed, Declined; localStorage). The hook is the row tooltip and, with the key number and source, in the side panel. Copy the ticked accounts as CSV or text; **Export invites** writes the `config/byod/dinner_attendees.csv` format (Confirmed = `accepted`). |
| `triggers.html` | Live public triggers grouped Upcoming, This week, Last week, Earlier; one line each, identical e-invoicing mandate events collapsed into one expandable row ("German e-invoicing mandate · 21 accounts") (company · what changed · entity a → b), source as a link icon (a dash without one), full filing text on hover. Opens on the last 30 days without dinner triggers; Type and When filters show the rest. |
| `method.html` | Reported vs Computed proxy vs Estimate, with `docs/methodology.md` behind "Show full methodology". |

Every page has a thin ticker under the nav with the 8 newest dated triggers (pauses on hover, dismissible, static with reduced motion) and an account search in the top bar: `/` focuses it, a dropdown shows the top 8 matches, arrow keys and Enter jump to the account page and a light/dark switch remembered per browser.

Build-time JSON snapshots are in `dist/data/`.

## Theme

Every colour and font is a CSS variable in `static/style.css`; that file is the neutral default. To restyle locally, copy
`config/theme.example.json` to `config/theme.local.json` (gitignored) and edit it: the build writes it to `dist/assets/theme.css`.
Only the listed variables are read and unsafe values are dropped. `accent` colours primary actions (Copy opener, Export invites, Export status) and the selected-row edge, with `accent-fg` as its text colour (keep 4.5:1); `focus` is the focus ring. `"default_scheme": "light"` (or `"dark"`) fixes the starting
scheme instead of following the system; the top-bar switch still changes it. `workspace/build.py --neutral` ignores the local file (use it for
screenshots that get committed).

## Data and privacy

- Data comes only from `chase.gtm.api` and `chase.query` (read-only, no network).
- Public company-level data only. Names of individuals, private-source triggers and the synthetic bring-your-own-data demo are excluded at build time. `tests/test_workspace.py` checks this.

## Build and open locally

```
make workspace                      # or: .venv/bin/python workspace/build.py
python -m http.server -d workspace/dist 8000
# open http://localhost:8000
```

## Deploy

The live demo is a Vercel deployment of the prebuilt `dist/` (no build command, no secrets). Build locally first, then deploy
`workspace/dist`. `vercel.json` adds an `X-Robots-Tag: noindex` header, and `.vercelignore` makes sure the gitignored `dist/` is
uploaded.

Independent project by Moritz Hanbuch.
