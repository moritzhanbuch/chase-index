# Source: Wikidata (SPARQL)

Verified 2026-11-16 by the `scout-wikidata` subagent. Verdict: **reachable, usable, low-to-medium trust.**
Good for identifiers, aliases and parent/subsidiary links. Not good enough to publish revenue figures from.

| Item | Finding |
|---|---|
| Endpoint | `https://query.wikidata.org/sparql` (GET, `query=` + `format=json`). Verified live. |
| Licence | Structured data in the main and property namespaces is **CC0 1.0** (public domain dedication). No attribution required; we attribute anyway via `source_url`. |
| Auth | None. |
| User-Agent | Wikimedia's User-Agent policy asks for a descriptive UA with contact info; generic UAs can be blocked. We send `ChaseIndex research (contact: <CONTACT_EMAIL>)` from `chase.common.http`. |
| Timeout | Hard server-side limit of 60 s per query. |
| Rate limits | Per client (UA + IP): roughly 60 s of query processing time per 60 s window and a small number of parallel queries; excess returns HTTP 429 with `Retry-After`. We run strictly sequential queries, at least 2 s apart. |
| Freshness | Live graph, lags edits by seconds to minutes. Content freshness depends on volunteers: revenue years are often several years old. |

## Gotchas found while testing

1. **A timed-out query can come back as HTTP 200 with a truncated JSON body** (the server streams results and
   appends a Java timeout stack trace). The HTTP layer would cache that. `chase.sources.wikidata.sparql()` treats a
   JSON decode error as a timeout, refetches once without cache, then splits the query.
2. `GROUP BY` over all revenue value nodes (`psv:P2139`) times out. What works: filter on the simple value
   (`ps:P2139 >= X`) first, then join the value node for the unit, and split by **amount band**
   (about 20k statements per band finish in 30 to 45 s).
3. Detail lookups work well as `VALUES` batches of 200 QIDs over GET (100 for the edge queries).
   The module halves a batch automatically on timeout.
4. The label service (`SERVICE wikibase:label`) is slow on large result sets; we join `rdfs:label` with a
   language filter instead.
5. Revenue (P2139) is a multi-statement property: one statement per year, each with its own currency unit and
   `P585` (point in time) qualifier. Some statements have no date; a few have no currency (unit "1"). We take the
   most recent dated statement per item and keep amount, currency and year.
6. Tickers are normally a qualifier (`P249`) on the stock exchange statement (`P414`), not a direct claim.
7. Index membership (IBEX 35, DAX, FTSE 100...) is patchy: sometimes `P361` on the company, sometimes `P527`
   on the index item. Both are collected; neither is complete. Do not use it as the IBEX 35 constituent list.
8. `P127` (owned by) is noisy when inverted: it also returns brands, buildings, ships, sports clubs and minority
   stakes. `P355` and `P749` are cleaner. Table 2 keeps the relation so downstream can filter.
9. Only about 8,600 items carry a Companies House number (`P2622`), against roughly 6,000 to 7,000 UK payment
   practice reporters per period. Wikidata alone will map only a small share of UK reporting entities; name
   matching and Companies House PSC data stay necessary.

## How we use it

- Table 1 `data/interim/wikidata_companies.parquet`: candidate universe (latest revenue statement >= ~USD 3B).
- Table 2 `data/interim/wikidata_subsidiaries.parquet`: descendants of Table 1 companies, depth <= 3.
- Table 3 `data/interim/wikidata_uk_entities.parquet`: every item with a Companies House number, plus ancestors.
- Column definitions: `docs/data_dictionary_wikidata.md`. Run log: `data/manifests/wikidata.json`.

All rows carry `confidence = 0.6`: community-edited data. Revenue from Wikidata is a screening value only;
SEC/ESEF XBRL revenue should replace it wherever available.

## Fallback

If the endpoint is down: the module is cache-backed (`data/cache/http`), so a rerun rebuilds the tables offline
from the last successful fetch. A full outage on a cold cache means the universe falls back to SEC + ESEF
revenue facts only, with name-based UK roll-up.
