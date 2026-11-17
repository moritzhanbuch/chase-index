# Chase Index workspace (internal)

**Warning: this contains internal scoring, priority tiers and draft openers. It is for the GTM team, not the public.**
Every page carries `noindex`. The public, press-safe version of the data is the site in `site/`.

## What it is

A static page set a sales person opens on Monday morning:

| Page | What it shows |
|---|---|
| `index.html` (Queue) | This week's queue: account, tier, play (next best action), who to reach by role, reported evidence with source, why now. Filter by country, play, tier. |
| `accounts/<id>.html` | One page per queued and top-100 account: evidence with source links (Reported, Computed proxy), scores and their components, triggers, supplier finance and UK filing features, the opportunity range (labelled Estimate), draft opener, link to the one-pager. |
| `dinners.html` | Per dinner city in `config/dinners.yaml` (real dates only in the gitignored `config/dinners.local.yaml`): shortlist with hooks. Tick or untick accounts, then copy as CSV or text (clipboard only). |
| `triggers.html` | Live public triggers, newest first, filter by type. E-invoicing mandates say whether they bind the buyer or its small suppliers. |
| `method.html` | Reported vs Computed proxy vs Estimate, plus `docs/methodology.md` rendered. |

Build-time JSON snapshots are in `dist/data/`.

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
