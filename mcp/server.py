#!/usr/bin/env python3
"""chase-index-mcp: a read-only MCP server over the Chase Index data.

Local stdio transport only. It reads data/processed through the shared query layer (src/chase/query.py) and
renders answers with src/chase/answers.py. Queue, dinner lists and openers are computed on demand: no generated
file is read. No writes, no network calls at query time, no secrets.

Every tool answers in text: a short human-readable answer first (key number, source link, why now, suggested
opener), then a compact "Details" block. Reported data, computed proxies and estimates are labelled.
"""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path

ROOT = Path(os.environ.get("CHASE_INDEX_ROOT") or Path(__file__).resolve().parents[1])
os.environ.setdefault("CHASE_INDEX_ROOT", str(ROOT))
sys.path.insert(0, str(ROOT / "src"))

from mcp.server.mcpserver import MCPServer  # noqa: E402  (MCP Python SDK v2; v1 called this FastMCP)

from chase import answers as A  # noqa: E402
from chase import query as q  # noqa: E402
from chase.gtm import api as gtm  # noqa: E402

mcp = MCPServer(
    "chase-index",
    instructions=(
        "The Chase Index: which large companies pay their suppliers slowly, why now, who to ask for and what to open with. "
        "Routing: new user or 'what can this do' -> start_here. 'This week', 'queue', 'who do I contact', 'what do I open with' -> weekly_queue. "
        "'Brief on X', 'prep for a call with X', 'tell me about X' -> get_account_brief. 'Dinner', 'who to invite in <city>' -> dinner_builder. "
        "'What changed', 'new filings', 'deadlines' -> triggers. Each tool already returns a short answer: relay its first part, keep the "
        "source links and the REPORTED / COMPUTED PROXY / ESTIMATE labels, and never present an estimate as a fact. UK figures cover the "
        "group's UK legal entities only. Openers are drafts for a person to send; never send anything. " + q.DISCLAIMER),
)


@mcp.tool()
def start_here() -> str:
    """Start here. Explains in five lines what the Chase Index does and suggests three questions to ask.
    Use when the user has just installed the plugin, asks what this tool or server can do, or asks how to get started."""
    return A.start_here()


@mcp.tool()
def weekly_queue(limit: int = 10, play: str | None = None, demo: bool = False) -> str:
    """This week's sales queue: which accounts to contact this week and what to open with. Use for "what's in this
    week's queue", "who should I contact this week", "what do I open with", "give me my Monday list", "next best action".
    For each account: the key number with its official source, why now (the newest dated event), the play, who to ask
    for and a draft opener (human-written template, numbers filled in). Computed live from the data.

    Args:
        limit: number of accounts (default 10; a full week is 25)
        play: optional filter: "cold_email" or "dinner_invite"
        demo: true only if the user asks for the SYNTHETIC demo CRM data
    """
    return A.weekly_queue(max(1, min(int(limit), 100)), play, bool(demo))


@mcp.tool()
def get_account_brief(company: str) -> str:
    """Brief on one company before a call, meeting or email. Use for "brief on Reckitt", "prep me for Siemens Energy",
    "tell me about Nestle", "why is X a target", "what would I say to X". Returns: tier and rank, the key payment
    number with its official source, why now, a draft opener and who to ask for, supplier-finance context, an estimate
    range (labelled ESTIMATE) and the one-pager path.

    Args:
        company: company name or alias as the user said it, e.g. "Reckitt", "Siemens Energy", "Tesco"
    """
    return A.account_brief(company)


@mcp.tool()
def dinner_builder(city: str, date: str | None = None, limit: int = 12, demo: bool = False) -> str:
    """Who to invite to a finance-leader dinner in a city. Use for "who should we invite to the Munich dinner",
    "dinner list for London", "Paris dinner guests". Returns the accounts (HQ in the city area first, then the country),
    each with one sourced sentence to use as the hook, a draft invite line, accounts left out and why, and a bench to verify.

    Args:
        city: munich, paris, london or madrid
        date: dinner date YYYY-MM-DD (default: the date in the local config/dinners.local.yaml; without one, "next dinner")
        limit: maximum invites (default 12)
        demo: true only if the user asks for the SYNTHETIC demo CRM data
    """
    return A.dinner(city, date, max(1, min(int(limit), 40)), bool(demo))


@mcp.tool()
def triggers(since: str | None = None, trigger_type: str | None = None, limit: int = 20) -> str:
    """What changed recently across all accounts: new UK filings that crossed 60 days or got slower, longer payment
    terms, newly offered supply chain finance or e-invoicing, Spanish payment periods that rose, plus upcoming
    e-invoicing deadlines. Use for "what changed this month", "any new filings", "upcoming deadlines".
    For one account, use get_account_brief instead.

    Args:
        since: ISO date YYYY-MM-DD (default: 30 days ago)
        trigger_type: optional filter: filing_crossed_60, filing_worsened, terms_changed_longer, scf_started,
                      einvoicing_started, es_pmp_rose, einvoicing_mandate, einvoicing_mandate_suppliers, sf_disclosed
        limit: maximum events listed (default 20)
    """
    return A.triggers(since, trigger_type, max(1, min(int(limit), 100)))


@mcp.tool()
def top_targets(country: str | None = None, city: str | None = None, sector: str | None = None,
                tier: int | None = None, limit: int = 10) -> str:
    """The standing ranked target list, filtered by country, HQ city, sector or tier. Use for "top targets in Germany",
    "best retail accounts", "Tier 1 accounts in Spain". For this week's priorities with openers, use weekly_queue;
    for a dinner, use dinner_builder.

    Args:
        country: ISO-2 HQ country, e.g. "DE", "GB", "ES", "FR", "US"
        city: HQ city, e.g. "Munich"
        sector: manufacturing, automotive, construction, retail, consumer_goods, energy, pharma, logistics, utilities,
                telecom, technology, services, financials
        tier: 1, 2 or 3
        limit: maximum results (default 10)
    """
    return A.top_targets(country, city, sector, tier, max(1, min(int(limit), 100)))


@mcp.tool()
def get_payment_profile(company: str) -> str:
    """Only the payment facts for one company, no sales angle: reported days to pay, share paid late and after 60
    days, terms and trend per UK entity, Spanish statutory payment period, and computed DPO labelled as a proxy.
    Use for "how long does X take to pay suppliers" or when the user wants the evidence table.

    Args:
        company: company name or alias, e.g. "Diageo"
    """
    return A.payment_profile(company)


@mcp.tool()
def lookup_uk_supplier_payment_record(customer: str, limit: int = 5) -> str:
    """Supplier-side lookup of one UK legal entity (any size, not only ranked groups): its latest statutory payment
    report with the official link. Use for "how long does Tesco Stores Ltd take to pay", a Companies House number,
    or a UK subsidiary that is not a ranked group.

    Args:
        customer: UK legal entity name (e.g. "Tesco Stores") or company number (e.g. "00519500")
        limit: maximum results (default 5)
    """
    return A.uk_lookup(customer, max(1, min(int(limit), 25)))


@mcp.tool()
def search_companies(query: str, country: str | None = None, sector: str | None = None, limit: int = 10) -> str:
    """Find the exact company in the index when a name is ambiguous or misspelled. Returns names, countries, tiers and ids.
    Not needed before the other tools: they accept plain names.

    Args:
        query: name or part of it, e.g. "siemens"
        country: optional ISO-2 HQ country
        sector: optional sector (see top_targets)
        limit: maximum results (default 10)
    """
    return A.search(query, country, sector, max(1, min(int(limit), 50)))


@mcp.tool()
def account_workspace(company: str, demo: bool = False) -> str:
    """Full raw record for one account, for a deep dive or an export: the brief plus every UK filing feature, every dated
    trigger and the user's own CRM flags. For a normal brief use get_account_brief. Names of individuals appear only if
    this machine holds local private data, and are marked private.

    Args:
        company: company name or alias
        demo: true only if the user asks for the SYNTHETIC demo CRM data
    """
    w = gtm.account_workspace(company, bool(demo))
    head = A.account_brief(company).split("\n\n---\n")[0]
    if "brief" not in w:
        return head
    w.pop("brief")
    return head + "\n\n---\nDetails (structured, full record):\n" + json.dumps(w, ensure_ascii=False, default=str)


@mcp.tool()
def byod_status(demo: bool = False) -> str:
    """Check which of the user's own data files are loaded (CRM pipeline, network suppliers, dinner attendees,
    investor links, account status) and which names did not match. Use for setup questions such as "is my CRM file loaded".

    Args:
        demo: true to report on the SYNTHETIC demo set
    """
    return A.byod(bool(demo))


@mcp.tool()
def explain_methodology(topic: str | None = None) -> str:
    """How the numbers are built: sources, definitions, scoring, estimates and limits. Use for "how is the score
    calculated", "what is DPO", "how reliable is this".

    Args:
        topic: optional keyword, e.g. "DPO", "Spain", "scores", "estimates", "roll". Omit for the overview.
    """
    return A.methodology(topic)


if __name__ == "__main__":
    mcp.run()   # stdio
