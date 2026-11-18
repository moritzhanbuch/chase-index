# Chase Index workspace (internal)

**Warning: this contains internal scoring, priority tiers and draft openers. It is for the GTM team, not the public.**
Every page carries `noindex`. The public, press-safe version of the data is the site in `site/`.

## What it is

A static page set a sales person opens on Monday morning:

| Page | What it shows |
|---|---|
| `index.html` (Queue) | This week's queue, one compact row per account: rank, company, tier, play, who to ask for, key number vs benchmark, up to 2 why-now tags. Click a row (or Enter) to expand the evidence with its source, all why-now events with links, the draft opener with a copy button, priority breakdown and links to the account page and one-pager. Each row also has a trend sparkline (reported days to pay over the available reports: UK half-years or Spanish fiscal years; dashed line = benchmark; none for a computed proxy) and a status (To do, Contacted, Meeting, Not now) kept in this browser's localStorage. A one-line strip above the list summarises the queue. Filter by country, play, tier, status; expand or collapse all; **Export status CSV** downloads the `config/status/` format (Not now exports as `not_a_fit`, reason "not now"). Keys: `j`/`k` move, `Enter` expands, `c` copies the opener, `?` lists the shortcuts. |
| `accounts/<id>.html` | One page per queued and top-100 account: evidence with source links (Reported, Computed proxy), scores and their components, triggers, supplier finance and UK filing features, the opportunity range (labelled Estimate), draft opener, link to the one-pager. |
| `dinners.html` | Per dinner city in `config/dinners.yaml` (real dates only in the gitignored `config/dinners.local.yaml`): shortlist grouped into City area and Rest of country, one line per account with the key number and the hook (full text on hover and in the copies). Tick accounts, then copy as CSV or text. An invite status (To invite, Invited, Confirmed, Declined) is kept in localStorage; **Export invite CSV** writes the `config/byod/dinner_attendees.csv` format (Confirmed = `accepted`). |
| `triggers.html` | Live public triggers, newest first. Opens on the last 30 days without dinner triggers; the Type and When filters show the rest. A dash marks a trigger without a source link. E-invoicing mandates say whether they bind the buyer or its small suppliers. |
| `method.html` | Reported vs Computed proxy vs Estimate, with `docs/methodology.md` behind "Show full methodology". |

Every page has an account search in the top bar (`/` focuses it, Enter jumps to the account page) and a light/dark switch remembered per browser.

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
