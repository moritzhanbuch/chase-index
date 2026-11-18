# Chase Index workspace (internal)

**Warning: this contains internal scoring, priority tiers and draft openers. It is for the GTM team, not the public.**
Every page carries `noindex`. The public, press-safe version of the data is the site in `site/`.

## What it is

A static page set a sales person opens on Monday morning:

| Page | What it shows |
|---|---|
| `index.html` (Queue) | CRM-style list, one row per account: company (initial avatar, name, tier dot, country), days to pay with a bar against the benchmark (median in the column header), the single strongest why-now pill, contact (Treasury or AP) and a status pill (click to cycle To do, Contacted, Meeting, Not now; kept in localStorage; **Export status** writes the `config/status/` CSV, Not now = `not_a_fit`, reason "not now"). Tabs: All, Treasury, AP, Dinner. Click a row (or Enter) for the side panel: key number and trend sparkline, evidence with source, every why-now item, the draft opener with Copy, who to ask for and why, play, priority, links to the account page and one-pager. Keys: `j`/`k` move (the panel follows), `c` copies the opener, `Esc` closes, `?` lists the shortcuts. |
| `accounts/<id>.html` | One page per queued, top-100 and dinner-list account, in the side-panel style: key number and trend, UK entity table (filing details collapsed), Spain figures, why now (dated triggers as "what · entity a → b" plus standing signals, each with a source icon), opener with Copy, who to ask for with a Find on LinkedIn search link (a plain link you open yourself, nothing is fetched), supplier finance. Collapsed: Proxy data (computed DPO with its caveat; never in the main view when the account has reported figures or the DPO uses the broad payables basis), Opportunity estimate, How it's scored. No internal codes in visible text. |
| `dinners.html` | Per dinner city in `config/dinners.yaml` (real dates only in the gitignored `config/dinners.local.yaml`), grouped into City area and Rest of country. Rows: checkbox, company, HQ city, a short reason ("76d · +18d YoY", "SCF £277m"), the role to invite (CFO / Treasurer, CFO, or CFO / Head of AP), invite pill (click to cycle To invite, Invited, Confirmed, Declined; localStorage). The hook is the row tooltip and, with the key number and source, in the side panel. Copy the ticked accounts as CSV or text; **Export invites** writes the `config/byod/dinner_attendees.csv` format (Confirmed = `accepted`). |
| `triggers.html` | Live public triggers grouped Upcoming, This week, Last week, Earlier; one line each, identical e-invoicing mandate events collapsed into one expandable row ("German e-invoicing mandate · 21 accounts") (company · what changed · entity a → b), source as a link icon (a dash without one), full filing text on hover. Opens on the last 30 days without dinner triggers; Type and When filters show the rest. |
| `method.html` | Reported vs Computed proxy vs Estimate, with `docs/methodology.md` behind "Show full methodology". |

Every page has an account search in the top bar: `/` focuses it, a dropdown shows the top 8 matches, arrow keys and Enter jump to the account page and a light/dark switch remembered per browser.

Build-time JSON snapshots are in `dist/data/`.

## Theme

Every colour and font is a CSS variable in `static/style.css`; that file is the neutral default. To restyle locally, copy
`config/theme.example.json` to `config/theme.local.json` (gitignored) and edit it: the build writes it to `dist/assets/theme.css`.
Only the listed variables are read and unsafe values are dropped. `"default_scheme": "light"` (or `"dark"`) fixes the starting
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

## Deploy later (not done; only after Mo reviews)

- **Vercel:** build locally first. Then from `workspace/` run `vercel deploy` with Root Directory `workspace`. `vercel.json` serves the prebuilt `dist/` (no build command, no secrets) and adds an `X-Robots-Tag: noindex` header. `.vercelignore` makes sure the gitignored `dist/` is uploaded. Put it behind Vercel password protection.
- **GitHub Pages:** `.github/workflows/workspace-pages.yml` runs `make workspace` and publishes `workspace/dist`. It only runs on manual `workflow_dispatch`. Pages sites are public unless the repo is on an Enterprise plan with private Pages, so prefer Vercel with protection.

Independent project by Moritz Hanbuch.
