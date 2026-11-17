# Exports (drafts, nothing was sent or uploaded)

Independent project by Moritz Hanbuch.

`make exports` (or `python -m chase.gtm.exports`) builds the weekly queue live and writes these files to `outputs/exports/` (gitignored, so your local exports never land in git). Files ending in `_demo` use the SYNTHETIC bring-your-own-data set.

| File | For | How to import |
|---|---|---|
| `hubspot_companies.csv` | HubSpot | Import > Companies. Map `Company Domain Name` as the unique key. Create the custom company properties starting with `chase_` first (single-line text, except the scores, tier, rank and days, which are numbers) |
| `attio_companies.csv` | Attio | Import to the Companies object, match on `Domains`. Create the attributes starting with `Chase` first |
| `salesforce_accounts.csv` | Salesforce | Data Import Wizard > Accounts. Create the custom fields ending in `__c` first (Text 255 or Long Text for evidence, why now and opener; Number for scores) |
| `slack_digest.md` | Slack | Paste into a channel. Uses Slack mrkdwn links. It is a draft: nobody posted it |

Companies only. No contact or person records are exported, on purpose: names of people stay in `data/private/`.
Field conventions follow each vendor's standard import names as of this build; check them against your own instance, since custom setups differ.
The domain comes from the company's website on Wikidata and is empty where unknown: fill those by hand before importing, otherwise the CRM cannot de-duplicate.
