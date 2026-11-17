"""Exports from the weekly queue: CRM import files and a Slack-ready digest. Drafts only: nothing is sent.

  python -m chase.gtm.exports            # from this week's queue (builds it if missing)
  python -m chase.gtm.exports --demo

CRM files follow each tool's standard company-import conventions, with the Chase Index fields as custom
properties. Create the custom properties once in the CRM before importing (names are in each file's header and
in docs/crm_exports.md). Companies only: no contact records are exported, on purpose.
"""
from __future__ import annotations

import sys
from datetime import date, timedelta

import pandas as pd

from chase import query as q
from chase.gtm import nba

OUT = q.ROOT / "outputs" / "exports"
ISO3 = {"GB": "United Kingdom", "DE": "Germany", "FR": "France", "ES": "Spain", "US": "United States", "CH": "Switzerland",
        "NL": "Netherlands", "IT": "Italy", "DK": "Denmark", "IE": "Ireland", "SE": "Sweden", "BE": "Belgium", "LU": "Luxembourg",
        "FI": "Finland", "NO": "Norway", "AT": "Austria", "JP": "Japan", "CA": "Canada"}


def _base(qd: pd.DataFrame) -> pd.DataFrame:
    comp = q.companies().set_index("company_id")
    d = qd.copy()
    d["website"] = d.company_id.map(comp.website)
    d["domain"] = d.website.fillna("").str.replace(r"^https?://(www\.)?", "", regex=True).str.split("/").str[0]
    d["country_name"] = d.country.map(lambda c: ISO3.get(c, c))
    d["industry"] = d.sector.str.replace("_", " ").str.title()
    d["revenue_usd"] = d.company_id.map(comp.revenue_usd).round(0)
    d["fit"], d["pain"], d["signal"] = d.company_id.map(comp.fit_score), d.company_id.map(comp.pain_score), d.company_id.map(comp.signal_score)
    d["days"] = d.company_id.map(comp.pain_days).round(0)
    d["basis"] = d.company_id.map(comp.pain_basis)
    return d


def hubspot(d: pd.DataFrame) -> pd.DataFrame:
    # HubSpot company import: standard internal names (name, domain, city, country, industry, annualrevenue) + custom properties
    return pd.DataFrame({
        "Company name": d.company, "Company Domain Name": d.domain, "City": d.hq_city, "Country/Region": d.country_name,
        "Annual Revenue": d.revenue_usd, "chase_index_id": d.company_id, "chase_tier": d.tier, "chase_queue_rank": d.queue_rank,
        "chase_fit_score": d.fit, "chase_pain_score": d.pain, "chase_signal_score": d.signal, "chase_days_to_pay": d.days,
        "chase_evidence_basis": d.basis, "chase_evidence": d.evidence, "chase_evidence_url": d.evidence_url, "chase_why_now": d.why_now,
        "chase_play": d.play, "chase_entry_role": d.who_role, "chase_opener_draft": d.opener_draft, "chase_sector": d.industry})


def attio(d: pd.DataFrame) -> pd.DataFrame:
    # Attio company import: matches on Domains; Name, Primary location; the rest as custom attributes
    return pd.DataFrame({
        "Name": d.company, "Domains": d.domain, "Primary location": (d.hq_city.fillna("") + ", " + d.country_name.fillna("")).str.strip(", "),
        "Categories": d.industry, "Chase Index ID": d.company_id, "Chase tier": d.tier, "Chase queue rank": d.queue_rank,
        "Chase days to pay": d.days, "Chase evidence": d.evidence, "Chase evidence URL": d.evidence_url, "Chase why now": d.why_now,
        "Chase play": d.play, "Chase entry role": d.who_role, "Chase opener draft": d.opener_draft})


def salesforce(d: pd.DataFrame) -> pd.DataFrame:
    # Salesforce Account import (Data Import Wizard / Data Loader): standard API names + custom fields ending in __c
    return pd.DataFrame({
        "Name": d.company, "Website": d.website, "BillingCity": d.hq_city, "BillingCountry": d.country_name, "Industry": d.industry,
        "AnnualRevenue": d.revenue_usd, "Chase_Index_Id__c": d.company_id, "Chase_Tier__c": d.tier, "Chase_Queue_Rank__c": d.queue_rank,
        "Chase_Fit_Score__c": d.fit, "Chase_Pain_Score__c": d.pain, "Chase_Signal_Score__c": d.signal, "Chase_Days_To_Pay__c": d.days,
        "Chase_Evidence__c": d.evidence, "Chase_Evidence_URL__c": d.evidence_url, "Chase_Why_Now__c": d.why_now, "Chase_Play__c": d.play,
        "Chase_Entry_Role__c": d.who_role, "Description": d.opener_draft})


def slack_digest(qd: pd.DataFrame, today: date, demo: bool) -> str:
    monday = today - timedelta(days=today.weekday())
    L = [f":dart: *Chase Index queue, week of {monday.isoformat()}*" + (" _(SYNTHETIC demo data)_" if demo else ""),
         f"{len(qd)} accounts. Plays: " + ", ".join(f"{k.replace('_', ' ')} {v}" for k, v in qd.play.value_counts().items()) + ".", ""]
    for r in qd.head(8).itertuples():
        why = r.why_now.split(" | ")[0]
        link = f" <{r.why_now_url}|source>" if isinstance(r.why_now_url, str) else (f" <{r.evidence_url}|source>" if isinstance(r.evidence_url, str) else "")
        L.append(f"*{r.queue_rank}. {r.company}* ({r.country}) · _{r.play.replace('_', ' ')}_\n>{why}.{link}")
    L += ["", f"Full queue with openers: `make queue` or the `weekly_queue` MCP tool · Drafts only, nothing was sent. UK figures describe UK entities, not the group.",
          f"_{q.DISCLAIMER}_"]
    return "\n".join(L) + "\n"


def run(demo: bool = False) -> None:
    today = date.today()
    qd = nba.build_queue(today, demo)
    nba.write_queue(qd, today, demo)
    d = _base(qd)
    OUT.mkdir(parents=True, exist_ok=True)
    sfx = "_demo" if demo else ""
    hubspot(d).to_csv(OUT / f"hubspot_companies{sfx}.csv", index=False)
    attio(d).to_csv(OUT / f"attio_companies{sfx}.csv", index=False)
    salesforce(d).to_csv(OUT / f"salesforce_accounts{sfx}.csv", index=False)
    (OUT / f"slack_digest{sfx}.md").write_text(slack_digest(qd, today, demo))
    (OUT / "README.md").write_text(f"""# Exports (drafts, nothing was sent or uploaded)

{q.DISCLAIMER}

Built from the weekly queue by `python -m chase.gtm.exports` (`make exports`). Files ending in `_demo` use the SYNTHETIC bring-your-own-data set.

| File | For | How to import |
|---|---|---|
| `hubspot_companies.csv` | HubSpot | Import > Companies. Map `Company Domain Name` as the unique key. Create the custom company properties starting with `chase_` first (single-line text, except the scores, tier, rank and days, which are numbers) |
| `attio_companies.csv` | Attio | Import to the Companies object, match on `Domains`. Create the attributes starting with `Chase` first |
| `salesforce_accounts.csv` | Salesforce | Data Import Wizard > Accounts. Create the custom fields ending in `__c` first (Text 255 or Long Text for evidence, why now and opener; Number for scores) |
| `slack_digest.md` | Slack | Paste into a channel. Uses Slack mrkdwn links. It is a draft: nobody posted it |

Companies only. No contact or person records are exported, on purpose: names of people stay in `data/private/`.
Field conventions follow each vendor's standard import names as of this build; check them against your own instance, since custom setups differ.
The domain comes from the company's website on Wikidata and is empty where unknown: fill those by hand before importing, otherwise the CRM cannot de-duplicate.
""")
    print(f"exports written to outputs/exports ({'demo' if demo else 'local'}): {len(d)} accounts; domains missing for {(d.domain == '').sum()}")


if __name__ == "__main__":
    run("--demo" in sys.argv)
