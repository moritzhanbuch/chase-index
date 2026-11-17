"""Wikidata (SPARQL, CC0) raw material for the Global 2000-style universe and UK group roll-up.

Run:  python -m chase.sources.wikidata        (cache-backed: reruns are cheap)

Outputs (data/interim):
  wikidata_companies.parquet/.csv      Table 1: items whose latest revenue statement (P2139) is >= ~USD 3B
  wikidata_subsidiaries.parquet/.csv   Table 2: descendants of Table 1 items (P355, inverse P749, inverse P127), depth <= 3
  wikidata_uk_entities.parquet/.csv    Table 3: all items with a Companies House number (P2622) + ancestors
Manifest: data/manifests/wikidata.json

All HTTP goes through chase.common.http (2 s between requests to query.wikidata.org, disk cache).
Queries are sequential and split (amount bands / VALUES batches) to stay inside the 60 s server timeout.
"""
from __future__ import annotations

import json
import re
import sys
import time
from collections import defaultdict
from pathlib import Path

import pandas as pd
import yaml

from chase.common.http import ROOT, fetch, now_iso, write_manifest

ENDPOINT = "https://query.wikidata.org/sparql"
INTERIM = ROOT / "data" / "interim"
FX_PATH = ROOT / "config" / "fx_rates.yaml"

REVENUE_MIN_USD = 3e9
# Lowest raw amount that can reach USD 3B in any currency we convert (KWD ~3.25 USD) is ~0.92e9.
RAW_AMOUNT_FLOOR = 9e8
BATCH = 200
MAX_DEPTH = 3
CONFIDENCE = 0.6

# instance-of QIDs that mark an item as clearly not a company (cheap, direct P31 only)
EXCLUDE_P31 = {
    "Q6256": "country", "Q3624078": "sovereign state", "Q7275": "state", "Q5": "human",
    "Q3918": "university", "Q875538": "public university", "Q902104": "private university",
    "Q23002054": "private not-for-profit educational institution", "Q62078547": "public research university",
    "Q15936437": "research university", "Q38723": "higher education institution",
    "Q476028": "association football club", "Q847017": "sports club", "Q12973014": "sports team",
    "Q7188": "government", "Q327333": "government agency", "Q35657": "U.S. state",
    "Q515": "city", "Q1549591": "big city", "Q4830453x": "", "Q107390": "federated state",
    "Q11424": "film", "Q7889": "video game", "Q7397": "software", "Q5398426": "television series",
    "Q24862": "short film", "Q482994": "album", "Q134556": "single", "Q7725634": "literary work",
    "Q1489259": "superpower", "Q112099": "island country", "Q43702": "federation",
    "Q4120211": "regional organization", "Q1335818": "supranational union", "Q484652": "international organization",
    "Q245065": "intergovernmental organization", "Q192350": "ministry", "Q2659904": "government organization",
    "Q17149090": "armed forces", "Q8473": "military", "Q1802963": "mansion",
    "Q1093829": "city in the United States", "Q1763527": "constituent state", "Q16917": "hospital",
    "Q1774898": "clinic", "Q3914": "school", "Q9842": "primary school", "Q3152824": "cultural institution",
    "Q33506": "museum", "Q2385804": "educational institution", "Q23442": "island", "Q82794": "geographic region",
    "Q13220204": "second-level administrative division", "Q10864048": "first-level administrative division",
    "Q15284": "municipality", "Q1048835": "political territorial entity", "Q41710": "ethnic group",
    "Q7210356": "political organization", "Q7278": "political party", "Q1530022": "religious organization",
    "Q9174": "religion", "Q879146": "Christian denomination", "Q34651": "Christian church",
    "Q1785271": "sports league", "Q15991303": "association football league", "Q623109": "sports league",
    "Q2088357": "musical ensemble", "Q215380": "musical group", "Q24634210": "podcast",
    "Q163740": "nonprofit organization x", "Q4287745": "medical organization x",
}
# a few of the above are too broad for big hospital groups etc.: keep the list conservative
for _k in ("Q4830453x", "Q163740", "Q4287745", "Q16917", "Q1774898"):
    EXCLUDE_P31.pop(_k, None)

# P31 labels that mark an item as a company: these override the exclusion list (e.g. Uber is also "software")
COMPANY_LIKE = set(
    "business|public company|enterprise|company|holding company|conglomerate|state-owned enterprise|bank|corporation|"
    "multinational corporation|subsidiary company|privately held company|concern|corporate group|group of companies|"
    "Chinese state-owned enterprise|Chinese wholly state-owned enterprise|commercial organization|retail chain|"
    "supermarket chain|airline|automobile manufacturer|credit institution|insurance company|public limited company|"
    "open joint-stock company|Societas Europaea|Crown corporation|family business|pharmaceutical company|"
    "software company|technology company|energy company|oil company|telecommunications company|trading company|"
    "aerospace manufacturer|automotive supplier|food manufacturer|railway company|commercial bank|chaebol|"
    "state-owned enterprise of Russia|national oil company|shipping line|financial institution".split("|"))
EXCLUDE_LABEL_RE = re.compile(
    r"\btax(es)?\b|excise|^rates$|university|college|medical school|video game|mobile app|\bfilm\b|"
    r"government agency|ministry|sovereign state|^country$|sports|football|award|heritage site|fictional|"
    r"board of |^collection$|financial market|educational institution|government organization|"
    r"intergovernmental|donor advised fund", re.I)

MAIN_PROPS = ["P17", "P159", "P452", "P31", "P946", "P1278", "P5531", "P2622", "P856", "P749", "P127",
              "P1454", "P571", "P576", "P1813", "P361"]
CHILD_PROPS = ["P17", "P2622", "P31"]

QUERY_LOG: list[dict] = []


class SparqlTimeout(Exception):
    pass


def log(msg: str) -> None:
    print(f"[wikidata {time.strftime('%H:%M:%S')}] {msg}", flush=True)


def sparql(query: str, name: str = "") -> list[dict]:
    """Run one SPARQL query. Raises SparqlTimeout on server/client timeout (incl. truncated 200 bodies)."""
    params = {"query": query, "format": "json"}
    last = None
    for attempt, use_cache in enumerate((True, False)):
        t0 = time.time()
        try:
            r = fetch(ENDPOINT, params=params, retries=1, use_cache=use_cache)
            rows = r.json()["results"]["bindings"]  # a query that times out server-side yields broken JSON
            QUERY_LOG.append({"name": name, "rows": len(rows), "retrieved_at": r.retrieved_at,
                              "from_cache": r.from_cache, "sha256": r.sha256,
                              "seconds": round(time.time() - t0, 1), "query": query if len(query) < 600 else query[:600] + " ..."})
            return rows
        except json.JSONDecodeError as e:
            last = e
            if not use_cache:
                break
            # cached body may be a truncated timeout response: refetch once
            continue
        except Exception as e:  # httpx timeouts / 5xx after retries
            last = e
            break
    QUERY_LOG.append({"name": name, "rows": None, "retrieved_at": now_iso(), "error": repr(last)[:200],
                      "query": query if len(query) < 600 else query[:600] + " ..."})
    raise SparqlTimeout(repr(last)[:200])


def lbl(var: str, out: str) -> str:
    """SPARQL snippet: English label of ?var into ?out, falling back to the language-neutral "mul" label
    (Wikidata stores many company names only as "mul" since 2024)."""
    return (f'OPTIONAL {{ ?{var} rdfs:label ?{out}_en. FILTER(LANG(?{out}_en)="en") }} '
            f'OPTIONAL {{ ?{var} rdfs:label ?{out}_mul. FILTER(LANG(?{out}_mul)="mul") }} '
            f'BIND(COALESCE(?{out}_en, ?{out}_mul) AS ?{out})')


def qid(uri: str | None) -> str | None:
    if not uri:
        return None
    return uri.rsplit("/", 1)[-1]


def val(b: dict, k: str) -> str | None:
    return b[k]["value"] if k in b else None


def values_clause(var: str, qids: list[str]) -> str:
    return f"VALUES ?{var} {{ " + " ".join(f"wd:{q}" for q in qids) + " }"


def batched(fn, qids: list[str], name: str, batch: int = BATCH) -> list[dict]:
    """Call fn(batch_qids) over batches; halve the batch on timeout."""
    out: list[dict] = []
    qids = sorted(set(q for q in qids if q and re.fullmatch(r"Q\d+", q)), key=lambda q: int(q[1:]))
    stack = [qids[i:i + batch] for i in range(0, len(qids), batch)][::-1]
    done = 0
    while stack:
        chunk = stack.pop()
        try:
            out.extend(sparql(fn(chunk), name))
            done += len(chunk)
            if done % (batch * 10) < len(chunk):
                log(f"  {name}: {done}/{len(qids)}")
        except SparqlTimeout as e:
            if len(chunk) <= 5:
                log(f"  {name}: giving up on {len(chunk)} items ({e})")
                QUERY_LOG.append({"name": name, "skipped_qids": chunk})
                continue
            mid = len(chunk) // 2
            stack.append(chunk[mid:])
            stack.append(chunk[:mid])
    return out


# ---------------------------------------------------------------- step 1: revenue statements

def revenue_query(lo: float, hi: float | None) -> str:
    hi_f = f" && ?a0 < {hi:.0f}" if hi else ""
    return f"""SELECT ?item ?amt ?unit ?date ?rank WHERE {{
  ?item p:P2139 ?st. ?st ps:P2139 ?a0. FILTER(?a0 >= {lo:.0f}{hi_f})
  ?st psv:P2139 ?v. ?v wikibase:quantityAmount ?amt; wikibase:quantityUnit ?unit.
  ?st wikibase:rank ?rank.
  OPTIONAL {{ ?st pq:P585 ?date }}
}}"""


def fetch_revenue_statements() -> pd.DataFrame:
    bands: list[tuple[float, float | None]] = [
        (9e8, 1.5e9), (1.5e9, 2.5e9), (2.5e9, 4e9), (4e9, 7e9), (7e9, 1.2e10), (1.2e10, 2.5e10),
        (2.5e10, 6e10), (6e10, 2e11), (2e11, 1e12), (1e12, 1e13), (1e13, None)]
    stack = bands[::-1]
    rows = []
    while stack:
        lo, hi = stack.pop()
        try:
            b = sparql(revenue_query(lo, hi), f"revenue_band_{lo:.3g}_{hi if hi is None else format(hi, '.3g')}")
            log(f"revenue band [{lo:.3g}, {hi}) -> {len(b)} statements")
            rows.extend(b)
        except SparqlTimeout:
            if hi is None:
                hi = lo * 1000
                stack.append((hi, None))
            mid = (lo * hi) ** 0.5
            if hi - lo < 1e6:
                log(f"revenue band [{lo}, {hi}) cannot be split further: skipped")
                continue
            log(f"revenue band [{lo:.3g}, {hi:.3g}) timed out: splitting")
            stack.append((mid, hi))
            stack.append((lo, mid))
    df = pd.DataFrame([{
        "qid": qid(val(b, "item")), "amount": float(val(b, "amt")), "unit_qid": qid(val(b, "unit")),
        "date": val(b, "date"), "rank": (val(b, "rank") or "").rsplit("#", 1)[-1]} for b in rows])
    df = df[df["rank"] != "DeprecatedRank"].drop_duplicates()
    return df


def fetch_units(unit_qids: list[str], fx: dict | None = None) -> pd.DataFrame:
    def q(chunk):
        return f"""SELECT ?item ?iso ?label WHERE {{ {values_clause('item', chunk)}
  OPTIONAL {{ ?item wdt:P498 ?iso }} {lbl('item', 'label')} }}"""
    b = batched(q, unit_qids, "currency_units")
    df = pd.DataFrame([{"unit_qid": qid(val(x, "item")), "currency": val(x, "iso"), "currency_label": val(x, "label")} for x in b],
                      columns=["unit_qid", "currency", "currency_label"])
    # a unit can carry several ISO 4217 codes (current + historical, e.g. PLN and PLZ): prefer one we have a rate for
    df["has_rate"] = df["currency"].isin(fx or {})
    df = df.sort_values(["unit_qid", "has_rate", "currency"], ascending=[True, False, True])
    return df.drop_duplicates("unit_qid").drop(columns="has_rate")


def latest_revenue(st: pd.DataFrame, units: pd.DataFrame, fx: dict) -> pd.DataFrame:
    st = st.merge(units, on="unit_qid", how="left")
    st["year"] = pd.to_numeric(st["date"].str.extract(r"^(-?\d{4})")[0], errors="coerce")
    st["usd"] = st["amount"] * st["currency"].map(fx)
    st["rank_n"] = st["rank"].map({"PreferredRank": 1, "NormalRank": 0}).fillna(0)
    # most recent statement per item: latest year first; undated statements last; preferred rank breaks ties
    st["year_sort"] = st["year"].fillna(-1)
    st = st.sort_values(["qid", "year_sort", "rank_n", "amount"], ascending=[True, False, False, False])
    n_st = st.groupby("qid").size().rename("revenue_statements_n")
    latest = st.drop_duplicates("qid").merge(n_st, on="qid")
    return latest


# ---------------------------------------------------------------- generic fetchers

def fetch_labels(qids: list[str], name: str, langs=("en", "de", "es", "fr"), aliases=True):
    langs = tuple(langs) + ("mul",)
    lang_list = ",".join(f'"{l}"' for l in langs)

    def q(chunk):
        alias = ('UNION { ?item skos:altLabel ?label. FILTER(LANG(?label) IN ("en","mul")) BIND("alias" AS ?kind) }'
                 if aliases else "")
        return f"""SELECT ?item ?kind ?label WHERE {{ {values_clause('item', chunk)}
  {{ ?item rdfs:label ?label. FILTER(LANG(?label) IN ({lang_list})) BIND("label" AS ?kind) }} {alias} }}"""
    labels: dict[str, dict[str, str]] = defaultdict(dict)
    alias_map: dict[str, list[str]] = defaultdict(list)
    for b in batched(q, qids, name):
        i = qid(val(b, "item"))
        if val(b, "kind") == "label":
            labels[i][b["label"].get("xml:lang", "en")] = b["label"]["value"]
        else:
            if b["label"]["value"] not in alias_map[i]:
                alias_map[i].append(b["label"]["value"])
    return labels, alias_map


def fetch_props(qids: list[str], props: list[str], name: str) -> pd.DataFrame:
    pv = " ".join(f"wdt:{p}" for p in props)

    def q(chunk):
        return f"""SELECT ?item ?p ?o ?ol WHERE {{ {values_clause('item', chunk)} VALUES ?p {{ {pv} }}
  ?item ?p ?o. {lbl('o', 'ol')} }}"""
    rows = []
    for b in batched(q, qids, name):
        o = b["o"]
        is_uri = o["type"] == "uri" and "/entity/Q" in o["value"]
        rows.append({"qid": qid(val(b, "item")), "prop": qid(val(b, "p")),
                     "o": qid(o["value"]) if is_uri else o["value"], "o_is_item": is_uri, "o_label": val(b, "ol")})
    return pd.DataFrame(rows, columns=["qid", "prop", "o", "o_is_item", "o_label"]).drop_duplicates()


def fetch_employees(qids: list[str]) -> pd.DataFrame:
    def q(chunk):
        return f"""SELECT ?item ?n ?date ?rank WHERE {{ {values_clause('item', chunk)}
  ?item p:P1128 ?st. ?st ps:P1128 ?n; wikibase:rank ?rank. OPTIONAL {{ ?st pq:P585 ?date }} }}"""
    rows = [{"qid": qid(val(b, "item")), "employees": float(val(b, "n")), "date": val(b, "date"),
             "rank": val(b, "rank").rsplit("#", 1)[-1]} for b in batched(q, qids, "employees")
            if b["n"]["type"] == "literal"]  # skip "unknown value" statements
    df = pd.DataFrame(rows, columns=["qid", "employees", "date", "rank"])
    df = df[df["rank"] != "DeprecatedRank"]
    df["employees_year"] = pd.to_numeric(df["date"].str.extract(r"^(\d{4})")[0], errors="coerce")
    df["ys"] = df["employees_year"].fillna(-1)
    df["rn"] = (df["rank"] == "PreferredRank").astype(int)
    df = df.sort_values(["qid", "ys", "rn"], ascending=[True, False, False]).drop_duplicates("qid")
    return df[["qid", "employees", "employees_year"]]


def fetch_listings(qids: list[str]) -> pd.DataFrame:
    def q(chunk):
        return f"""SELECT ?item ?ex ?exl ?ticker ?end WHERE {{ {values_clause('item', chunk)}
  ?item p:P414 ?st. ?st ps:P414 ?ex. OPTIONAL {{ ?st pq:P249 ?ticker }} OPTIONAL {{ ?st pq:P582 ?end }}
  {lbl('ex', 'exl')} }}"""
    rows = [{"qid": qid(val(b, "item")), "exchange_qid": qid(val(b, "ex")), "exchange": val(b, "exl"),
             "ticker": val(b, "ticker"), "end": val(b, "end")} for b in batched(q, qids, "listings")]
    return pd.DataFrame(rows, columns=["qid", "exchange_qid", "exchange", "ticker", "end"]).drop_duplicates()


def fetch_stock_indices() -> dict[str, str]:
    b = sparql(f"""SELECT DISTINCT ?idx ?l WHERE {{ ?idx wdt:P31 wd:Q223371. {lbl('idx', 'l')} }}""",
               "stock_index_items")
    return {qid(val(x, "idx")): val(x, "l") for x in b}


def fetch_index_members(qids: list[str]) -> pd.DataFrame:
    """Index membership recorded on the index item (P527 has part) rather than on the company."""
    def q(chunk):
        return f"""SELECT ?item ?idx ?l WHERE {{ {values_clause('item', chunk)} ?idx wdt:P527 ?item; wdt:P31 wd:Q223371.
  {lbl('idx', 'l')} }}"""
    rows = [{"qid": qid(val(b, "item")), "idx": qid(val(b, "idx")), "idx_label": val(b, "l")}
            for b in batched(q, qids, "index_members_p527")]
    return pd.DataFrame(rows, columns=["qid", "idx", "idx_label"])


def fetch_iso2(country_qids: list[str]) -> dict[str, str]:
    df = fetch_props(country_qids, ["P297"], "country_iso2")
    return dict(zip(df["qid"], df["o"]))


# "owned by" (P127) also points at patents, stations, buildings, ships (Samsung: 7,400 items; SNCF: 4,100).
# Keep an owned item only if it carries at least one organisation-like property.
ORG_FILTER = ("FILTER EXISTS { VALUES ?orgp { wdt:P452 wdt:P159 wdt:P1454 wdt:P2622 wdt:P1278 wdt:P946 wdt:P414 "
              "wdt:P2139 wdt:P1128 wdt:P749 wdt:P355 } ?child ?orgp ?orgv }")
MAX_FRONTIER = 30000  # stop expanding a BFS level beyond this many new nodes (time budget), logged in the manifest


def edges_down(parents: list[str], name: str) -> pd.DataFrame:
    def q(chunk):
        v = values_clause("parent", chunk)
        return f"""SELECT ?parent ?child ?rel WHERE {{ {v}
  {{ ?parent wdt:P355 ?child BIND("P355" AS ?rel) }} UNION {{ ?child wdt:P749 ?parent BIND("P749_inverse" AS ?rel) }}
  UNION {{ ?child wdt:P127 ?parent BIND("P127_inverse" AS ?rel) {ORG_FILTER} }} }}"""
    rows = [{"parent": qid(val(b, "parent")), "child": qid(val(b, "child")), "rel": val(b, "rel")}
            for b in batched(q, parents, name, batch=150)]
    df = pd.DataFrame(rows, columns=["parent", "child", "rel"]).drop_duplicates()
    return df[df["child"].str.fullmatch(r"Q\d+", na=False) & (df["parent"] != df["child"])]


def edges_up(children: list[str], name: str) -> pd.DataFrame:
    def q(chunk):
        v = values_clause("child", chunk)
        return f"""SELECT ?child ?parent ?rel WHERE {{ {v}
  {{ ?child wdt:P749 ?parent BIND("P749" AS ?rel) }} UNION {{ ?child wdt:P127 ?parent BIND("P127" AS ?rel) }}
  UNION {{ ?parent wdt:P355 ?child BIND("P355_inverse" AS ?rel) }} }}"""
    rows = [{"child": qid(val(b, "child")), "parent": qid(val(b, "parent")), "rel": val(b, "rel")}
            for b in batched(q, children, name)]
    df = pd.DataFrame(rows, columns=["child", "parent", "rel"]).drop_duplicates()
    return df[df["parent"].str.fullmatch(r"Q\d+", na=False) & (df["parent"] != df["child"])]


# ---------------------------------------------------------------- helpers

def pipe(values, limit: int | None = None) -> str | None:
    seen = []
    for v in values:
        if v is None or (isinstance(v, float) and pd.isna(v)):
            continue
        v = str(v).replace("|", "/").strip()
        if v and v not in seen:
            seen.append(v)
    if limit:
        seen = seen[:limit]
    return "|".join(seen) if seen else None


def norm_company_number(s: str | None) -> str | None:
    if not s:
        return None
    s = re.sub(r"[\s\-./]", "", str(s)).upper()
    m = re.fullmatch(r"([A-Z]{0,2})(\d+)", s)
    if not m:
        return s or None
    pre, num = m.groups()
    if len(pre) + len(num) > 8:
        return s
    return pre + num.zfill(8 - len(pre))


def prop_lists(props: pd.DataFrame, prop: str, col: str = "o") -> dict[str, list]:
    sub = props[props["prop"] == prop]
    return sub.groupby("qid")[col].apply(list).to_dict()


def save(df: pd.DataFrame, stem: str) -> None:
    INTERIM.mkdir(parents=True, exist_ok=True)
    df.to_parquet(INTERIM / f"{stem}.parquet", index=False)
    df.to_csv(INTERIM / f"{stem}.csv", index=False)
    log(f"wrote {stem}: {len(df)} rows")


# ---------------------------------------------------------------- table builders

def build_companies(fx: dict) -> tuple[pd.DataFrame, dict]:
    st = fetch_revenue_statements()
    log(f"revenue statements >= {RAW_AMOUNT_FLOOR:.0e} raw: {len(st)} on {st['qid'].nunique()} items")
    units = fetch_units(st["unit_qid"].dropna().unique().tolist(), fx)
    latest = latest_revenue(st, units, fx)
    unconverted = latest[latest["usd"].isna()]
    cand = latest[latest["usd"] >= REVENUE_MIN_USD].copy()
    log(f"items with latest (above-floor) revenue statement >= USD {REVENUE_MIN_USD:.0e}: {len(cand)}; "
        f"unconvertible currency/unit: {len(unconverted)}")
    qids = cand["qid"].tolist()

    labels, aliases = fetch_labels(qids, "company_labels")
    props = fetch_props(qids, MAIN_PROPS, "company_props")
    emp = fetch_employees(qids)
    listings = fetch_listings(qids)
    indices = fetch_stock_indices()
    idx_members = fetch_index_members(qids)

    country_q = set(props.loc[props["prop"] == "P17", "o"])
    hq_q = props.loc[(props["prop"] == "P159") & props["o_is_item"], "o"].unique().tolist()
    hq_props = fetch_props(hq_q, ["P17"], "hq_country")
    hq_country = hq_props.drop_duplicates("qid").set_index("qid")[["o", "o_label"]].to_dict("index")
    country_q |= {v["o"] for v in hq_country.values()}
    iso2 = fetch_iso2(sorted(country_q))

    P = {p: prop_lists(props, p) for p in MAIN_PROPS}
    PL = {p: prop_lists(props, p, "o_label") for p in MAIN_PROPS}
    p31 = P["P31"]
    lst = {k: g for k, g in listings.groupby("qid")}
    idxm = idx_members.groupby("qid").apply(lambda g: list(zip(g["idx"], g["idx_label"]))).to_dict() if len(idx_members) else {}
    emp_d = emp.set_index("qid").to_dict("index")
    ts = now_iso()

    rows, excluded = [], []
    for r in cand.itertuples():
        q = r.qid
        types = p31.get(q, [])
        type_labels = [t for t in PL["P31"].get(q, []) if isinstance(t, str)]
        company_like = any(t in COMPANY_LIKE for t in type_labels)
        bad = [t for t in types if t in EXCLUDE_P31] or [t for t in type_labels if EXCLUDE_LABEL_RE.search(t)]
        lab = labels.get(q, {})
        if bad and not company_like:
            excluded.append({"qid": q, "label": lab.get("en") or lab.get("mul"), "types": pipe(PL["P31"].get(q, []))})
            continue
        c_q = (P["P17"].get(q) or [None])[0]
        hq = (P["P159"].get(q) or [None])[0]
        hq_c = hq_country.get(hq, {}) if hq else {}
        g = lst.get(q)
        active = g[g["end"].isna()] if g is not None else None
        use = active if active is not None and len(active) else g
        part_of = list(zip(P["P361"].get(q, []), PL["P361"].get(q, [])))
        idx = [l or i for i, l in part_of if i in indices] + [l or i for i, l in idxm.get(q, [])]
        e = emp_d.get(q, {})
        rows.append({
            "qid": q,
            "label_en": lab.get("en") or lab.get("mul"), "label_mul": lab.get("mul"), "label_de": lab.get("de"), "label_es": lab.get("es"), "label_fr": lab.get("fr"),
            "aliases_en": pipe(aliases.get(q, []), 10),
            "short_name": pipe(P["P1813"].get(q, []), 5),
            "country_iso2": iso2.get(c_q), "country_label": (PL["P17"].get(q) or [None])[0], "country_qid": c_q,
            "countries_n": len(set(P["P17"].get(q, []))),
            "hq_city": (PL["P159"].get(q) or [None])[0], "hq_city_qid": hq if hq and re.fullmatch(r"Q\d+", str(hq)) else None,
            "hq_country_iso2": iso2.get(hq_c.get("o")), "hq_country_label": hq_c.get("o_label"),
            "industries": pipe(PL["P452"].get(q, [])),
            "instance_of": pipe(PL["P31"].get(q, [])), "instance_of_qids": pipe(types),
            "company_like_type": company_like,
            "employees": e.get("employees"), "employees_year": e.get("employees_year"),
            "revenue_amount": r.amount, "revenue_currency": r.currency, "revenue_currency_qid": r.unit_qid,
            "revenue_year": r.year if pd.notna(r.year) else None, "revenue_date": r.date,
            "revenue_usd": r.usd, "revenue_statements_n": r.revenue_statements_n,
            "isin": pipe(P["P946"].get(q, [])), "lei": pipe(P["P1278"].get(q, [])),
            "sec_cik": pipe([str(x).zfill(10) for x in P["P5531"].get(q, [])]),
            "ticker": pipe(use["ticker"].tolist()) if use is not None else None,
            "stock_exchange": pipe(use["exchange"].tolist()) if use is not None else None,
            "listings": pipe([f"{x.exchange}:{x.ticker}" for x in g.itertuples() if x.ticker]) if g is not None else None,
            "uk_company_number": pipe([norm_company_number(x) for x in P["P2622"].get(q, [])]),
            "website": (P["P856"].get(q) or [None])[0],
            "parent_qid": pipe(P["P749"].get(q, [])), "parent_label": pipe(PL["P749"].get(q, [])),
            "owned_by_qid": pipe(P["P127"].get(q, [])), "owned_by_label": pipe(PL["P127"].get(q, [])),
            "legal_form": pipe(PL["P1454"].get(q, [])),
            "inception": (sorted(str(x) for x in P["P571"].get(q, [])) or [None])[0],
            "dissolved_date": (sorted(str(x) for x in P["P576"].get(q, [])) or [None])[0],
            "is_dissolved": bool(P["P576"].get(q)),
            "part_of": pipe([l for _, l in part_of]), "stock_indices": pipe(idx),
            "source_url": f"https://www.wikidata.org/wiki/{q}", "source_type": "wikidata", "retrieved_at": ts,
            "extraction_method": "sparql", "confidence": CONFIDENCE,
        })
    df = pd.DataFrame(rows).sort_values("revenue_usd", ascending=False).reset_index(drop=True)
    for c in ("employees", "employees_year", "revenue_year"):
        df[c] = pd.to_numeric(df[c], errors="coerce").round().astype("Int64")
    stats = {"revenue_statements": int(len(st)), "items_with_statement_above_floor": int(st["qid"].nunique()),
             "candidates_ge_3b_usd": int(len(cand)), "excluded_non_company": len(excluded),
             "unconvertible_latest": int(len(unconverted)),
             "unconvertible_units": unconverted.groupby(["unit_qid", "currency_label"], dropna=False).size()
             .sort_values(ascending=False).head(40).reset_index(name="n").to_dict("records")}
    pd.DataFrame(excluded).to_csv(INTERIM / "wikidata_excluded_non_companies.csv", index=False)
    return df, stats


def build_subsidiaries(companies: pd.DataFrame) -> tuple[pd.DataFrame, dict]:
    roots = companies["qid"].tolist()
    all_edges = []
    seen = set(roots)
    frontier = roots
    for depth in range(1, MAX_DEPTH + 1):
        e = edges_down(frontier, f"edges_down_d{depth}")
        all_edges.append(e)
        new = sorted(set(e["child"]) - seen)
        log(f"subsidiary BFS depth {depth}: {len(e)} edges, {len(new)} new nodes")
        seen |= set(new)
        frontier = new
        depth_reached = depth
        if not frontier:
            break
        if len(frontier) > MAX_FRONTIER and depth < MAX_DEPTH:
            log(f"frontier of {len(frontier)} nodes exceeds MAX_FRONTIER={MAX_FRONTIER}: stopping at depth {depth}")
            break
    edges = pd.concat(all_edges).drop_duplicates()
    kids: dict[str, list[tuple[str, str]]] = defaultdict(list)
    rel_pri = {"P355": 0, "P749_inverse": 1, "P127_inverse": 2}
    for r in edges.sort_values("rel", key=lambda s: s.map(rel_pri)).itertuples():
        kids[r.parent].append((r.child, r.rel))
    rel_all = edges.groupby(["parent", "child"])["rel"].apply(lambda s: "|".join(sorted(set(s)))).to_dict()

    rows = []
    for root in roots:
        visited = {root}
        level = [root]
        for depth in range(1, depth_reached + 1):
            nxt = []
            for p in level:
                for c, _ in kids.get(p, []):
                    if c in visited:
                        continue
                    visited.add(c)
                    nxt.append(c)
                    rows.append({"parent_qid": root, "child_qid": c, "relation": rel_all[(p, c)],
                                 "depth": depth, "via_parent_qid": p})
            level = nxt
    sub = pd.DataFrame(rows)
    child_q = sorted(set(sub["child_qid"]) | set(sub["via_parent_qid"]))
    labels, aliases = fetch_labels(child_q, "child_labels", langs=("en", "de", "es", "fr"))
    props = fetch_props(child_q, CHILD_PROPS, "child_props")
    iso2 = fetch_iso2(sorted(set(props.loc[props["prop"] == "P17", "o"])))
    c17 = prop_lists(props, "P17")
    c2622 = prop_lists(props, "P2622")
    c31 = prop_lists(props, "P31", "o_label")

    def best_label(q):
        l = labels.get(q, {})
        return l.get("en") or l.get("mul") or l.get("de") or l.get("fr") or l.get("es")
    root_label = dict(zip(companies["qid"], companies["label_en"]))
    sub["parent_label"] = sub["parent_qid"].map(root_label)
    sub["child_label"] = sub["child_qid"].map(best_label)
    sub["child_aliases_en"] = sub["child_qid"].map(lambda q: pipe(aliases.get(q, []), 10))
    sub["child_country_iso2"] = sub["child_qid"].map(lambda q: iso2.get((c17.get(q) or [None])[0]))
    sub["child_uk_company_number"] = sub["child_qid"].map(lambda q: pipe([norm_company_number(x) for x in c2622.get(q, [])]))
    sub["child_instance_of"] = sub["child_qid"].map(lambda q: pipe(c31.get(q, []), 5))
    sub["via_parent_label"] = sub["via_parent_qid"].map(lambda q: root_label.get(q) or best_label(q))
    sub["child_in_table1"] = sub["child_qid"].isin(set(roots))
    ts = now_iso()
    sub["source_url"] = "https://www.wikidata.org/wiki/" + sub["child_qid"]
    sub["source_type"] = "wikidata"
    sub["retrieved_at"] = ts
    sub["extraction_method"] = "sparql"
    sub["confidence"] = CONFIDENCE
    cols = ["parent_qid", "parent_label", "child_qid", "child_label", "child_aliases_en", "child_country_iso2",
            "child_uk_company_number", "child_instance_of", "relation", "depth", "via_parent_qid", "via_parent_label",
            "child_in_table1", "source_url", "source_type", "retrieved_at", "extraction_method", "confidence"]
    return sub[cols], {"edges": int(len(edges)), "distinct_children": int(sub["child_qid"].nunique()),
                       "depth_reached": depth_reached, "max_depth_target": MAX_DEPTH, "max_frontier": MAX_FRONTIER}


def build_uk_entities(companies: pd.DataFrame) -> tuple[pd.DataFrame, dict]:
    b = sparql(f"""SELECT ?item ?num ?label WHERE {{ ?item wdt:P2622 ?num. {lbl('item', 'label')} }}""",
               "uk_entities_p2622")
    uk = pd.DataFrame([{"qid": qid(val(x, "item")), "company_number_raw": val(x, "num"), "label": val(x, "label")} for x in b])
    uk["company_number"] = uk["company_number_raw"].map(norm_company_number)
    uk = uk.drop_duplicates(["qid", "company_number"])
    log(f"UK entities with P2622: {len(uk)} rows, {uk['qid'].nunique()} items")

    up: dict[str, list[tuple[str, str]]] = defaultdict(list)
    seen = set(uk["qid"])
    frontier = sorted(seen)
    n_edges = 0
    for level in range(1, 6):
        e = edges_up(frontier, f"edges_up_l{level}")
        n_edges += len(e)
        for r in e.itertuples():
            if (r.parent, r.rel) not in up[r.child]:
                up[r.child].append((r.parent, r.rel))
        new = sorted(set(e["parent"]) - seen)
        log(f"UK ancestors level {level}: {len(e)} edges, {len(new)} new nodes")
        seen |= set(new)
        frontier = new
        if not frontier:
            break
    anc = sorted(seen - set(uk["qid"]))
    labels, _ = fetch_labels(anc, "ancestor_labels", langs=("en",), aliases=False)
    lab = {q: v.get("en") or v.get("mul") for q, v in labels.items()}
    lab.update({q: l for q, l in zip(uk["qid"], uk["label"]) if l})
    lab.update(dict(zip(companies["qid"], companies["label_en"])))
    t1 = set(companies["qid"])
    pri = {"P749": 0, "P355_inverse": 1, "P127": 2}

    def parents(q):
        return sorted(up.get(q, []), key=lambda x: (pri[x[1]], x[0] not in t1, int(x[0][1:])))

    out = []
    for r in uk.itertuples():
        ps = parents(r.qid)
        p749 = [p for p, rel in ps if rel in ("P749", "P355_inverse")]
        p127 = [p for p, rel in ps if rel == "P127"]
        # ultimate ancestor: follow the preferred parent (P749 first, then P127) up to 5 levels
        cur, path = r.qid, [r.qid]
        for _ in range(5):
            cand = [(p, rel) for p, rel in parents(cur) if p not in path]
            nxt = [p for p, rel in cand if rel != "P127"]
            if not nxt:
                # "owned by" lists every shareholder (incl. index funds): only follow it for a sole owner
                owners = [p for p, rel in cand if rel == "P127"]
                nxt = owners if len(owners) == 1 else []
            if not nxt:
                break
            cur = nxt[0]
            path.append(cur)
        # nearest ancestor (or self) that is in Table 1: BFS over all parents, up to 5 levels
        uni, uni_depth = (r.qid, 0) if r.qid in t1 else (None, None)
        if uni is None:
            level, visited = [r.qid], {r.qid}
            for d in range(1, 6):
                nxt = []
                for c in level:
                    for p, _ in parents(c):
                        if p not in visited:
                            visited.add(p)
                            nxt.append(p)
                hit = [p for p in nxt if p in t1]
                if hit:
                    uni, uni_depth = hit[0], d
                    break
                level = nxt
        out.append({
            "qid": r.qid, "label": r.label, "company_number": r.company_number, "company_number_raw": r.company_number_raw,
            "parent_qid": pipe(p749), "parent_label": pipe([lab.get(p) for p in p749]),
            "owned_by_qid": pipe(p127), "owned_by_label": pipe([lab.get(p) for p in p127]),
            "ultimate_ancestor_qid": cur if cur != r.qid else None,
            "ultimate_ancestor_label": lab.get(cur) if cur != r.qid else None,
            "ancestor_path": "|".join(path) if len(path) > 1 else None, "ancestor_depth": len(path) - 1,
            "parent_candidates_n": len(set(p for p, _ in ps)),
            "universe_ancestor_qid": uni, "universe_ancestor_label": lab.get(uni) if uni else None,
            "universe_ancestor_depth": uni_depth,
        })
    df = pd.DataFrame(out)
    df["universe_ancestor_depth"] = df["universe_ancestor_depth"].astype("Int64")
    ts = now_iso()
    df["source_url"] = "https://www.wikidata.org/wiki/" + df["qid"]
    df["source_type"] = "wikidata"
    df["retrieved_at"] = ts
    df["extraction_method"] = "sparql"
    df["confidence"] = CONFIDENCE
    return df, {"up_edges": n_edges, "with_any_parent": int((df["parent_candidates_n"] > 0).sum()),
                "with_universe_ancestor": int(df["universe_ancestor_qid"].notna().sum())}


def main(argv: list[str] | None = None) -> int:
    argv = argv if argv is not None else sys.argv[1:]
    fx = yaml.safe_load(FX_PATH.read_text())["usd_per_unit"]
    started = now_iso()
    manifest: dict = {"source": "wikidata", "endpoint": ENDPOINT, "licence": "CC0 1.0", "started_at": started,
                      "revenue_min_usd": REVENUE_MIN_USD, "raw_amount_floor": RAW_AMOUNT_FLOOR, "tables": {}}

    companies, s1 = build_companies(fx)
    save(companies, "wikidata_companies")
    manifest["tables"]["wikidata_companies"] = {"rows": len(companies), **s1}

    def flush():
        manifest["finished_at"] = now_iso()
        manifest["queries_n"] = len(QUERY_LOG)
        manifest["queries_from_cache_n"] = sum(1 for q in QUERY_LOG if q.get("from_cache"))
        manifest["queries_failed_n"] = sum(1 for q in QUERY_LOG if q.get("error"))
        by_name: dict[str, dict] = {}
        for q in QUERY_LOG:
            d = by_name.setdefault(q.get("name", ""), {"requests": 0, "rows": 0, "errors": 0, "first_retrieved_at": q.get("retrieved_at"),
                                                       "example_query": q.get("query")})
            d["requests"] += 1
            d["rows"] += q.get("rows") or 0
            d["errors"] += 1 if q.get("error") else 0
            d["last_retrieved_at"] = q.get("retrieved_at")
        manifest["queries"] = by_name
        manifest["skipped_qids"] = [q for q in QUERY_LOG if q.get("skipped_qids")]
        write_manifest("wikidata", manifest)
    flush()

    if "--companies-only" not in argv:
        uk, s3 = build_uk_entities(companies)
        save(uk, "wikidata_uk_entities")
        manifest["tables"]["wikidata_uk_entities"] = {"rows": len(uk), **s3}
        flush()
        sub, s2 = build_subsidiaries(companies)
        save(sub, "wikidata_subsidiaries")
        manifest["tables"]["wikidata_subsidiaries"] = {"rows": len(sub), **s2}
        flush()
    log("done")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
