"""DACH slice: computed DPO from the latest consolidated annual report for
  (a) DAX 40 and MDAX members headquartered in Bavaria, and
  (b) the largest Swiss and Austrian listed industrials already in the universe.

Steps (each writes to data/interim/, all downloads go through the polite cached client into data/raw/dach/):

  python -m chase.sources.dach_slice members     # index membership + Bavarian HQ test -> dach_members.csv
  python -m chase.sources.dach_slice docs        # locate and download the annual reports -> dach_documents.csv
  python -m chase.sources.dach_slice extract-a   # extractor A (deterministic: XBRL facts, then note-table regex)
  python -m chase.sources.dach_slice reconcile   # A vs B (agent) -> agreement, adjudication queue
  python -m chase.sources.dach_slice final       # apply the QA adjudication -> dach_dpo.parquet (read by chase.sources.dpo)

Extractor B and the adjudication are agent steps (see docs/model_routing.md): B reads the same documents
independently and writes dach_extract_b.json; a separate QA agent adjudicates every disagreement into
dach_adjudication.json and hand-checks a random sample of 10 into dach_handcheck.json.

What is extracted, per company and fiscal year (latest two, from one report: the year and its comparative):
  - trade payables to suppliers (current), NOT the total "trade and other payables" line
  - cost of sales; if the company reports by nature of expense, cost of materials (labelled, lower confidence)
  - revenue (for the universe row and the estimate)
DPO = trade payables / cost x 365. A balance-sheet proxy, not reported days to pay.
Banks and insurers are excluded.
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

import pandas as pd

from chase.common.http import fetch, now_iso

ROOT = Path(__file__).resolve().parents[3]
INTERIM = ROOT / "data" / "interim"
RAW = ROOT / "data" / "raw" / "dach"
WIKI_API = "https://de.wikipedia.org/w/api.php"
SPARQL = "https://query.wikidata.org/sparql"
BAVARIA = "Q980"
INDUSTRIAL = {"manufacturing", "construction", "automotive"}
FIN_WORDS = re.compile(r"versicher|bank|rückversicher|immobilien|real estate|finanz", re.I)


# ---------------------------------------------------------------- membership
def _wikitext(page: str) -> tuple[str, int, str]:
    r = fetch(WIKI_API, params={"action": "parse", "page": page, "prop": "wikitext|revid", "format": "json", "formatversion": "2"})
    j = r.json()["parse"]
    return j["wikitext"], j["revid"], r.retrieved_at


def _link_target(cell: str) -> tuple[str | None, str]:
    m = re.search(r"\[\[([^\]|#]+)(?:\|([^\]]+))?\]\]", cell)
    if not m:
        return None, cell.strip()
    return m.group(1).strip(), (m.group(2) or m.group(1)).strip()


def _rows(table: str) -> list[list[str]]:
    out = []
    for block in table.split("\n|-")[1:]:
        cells = []
        for line in block.strip().splitlines():
            line = line.strip()
            if line.startswith("|") and not line.startswith("|}"):
                cells += [c.strip() for c in line[1:].split("||")]
        if cells:
            out.append(cells)
    return out


def _table(wt: str, marker: str) -> str:
    i = wt.find(marker)
    return wt[i: wt.find("\n|}", i)]


def _strip_style(c: str) -> str:
    return c.split("|", 1)[1].strip() if re.match(r"^\s*(style|align|class)=", c) and "|" in c else c


def index_members() -> pd.DataFrame:
    rows = []
    wt, rev, ts = _wikitext("DAX")
    for c in _rows(_table(wt, 'id="Zusammensetzung"')):
        c = [_strip_style(x) for x in c]
        title, label = _link_target(c[0])
        rows.append({"index": "DAX", "wiki_title": title, "name": label, "sector_label": c[2] if len(c) > 2 else None,
                     "hq_city_table": _link_target(c[6])[1] if len(c) > 6 else None,
                     "state_table": re.sub(r"[{}]", "", c[7]).strip() if len(c) > 7 else None,
                     "source_url": f"https://de.wikipedia.org/w/index.php?title=DAX&oldid={rev}", "retrieved_at": ts})
    wt, rev, ts = _wikitext("MDAX")
    for c in _rows(_table(wt, 'id="zusammensetzung"')):
        c = [_strip_style(x) for x in c]
        title, label = _link_target(c[1])
        rows.append({"index": "MDAX", "wiki_title": title, "name": label, "sector_label": c[2] if len(c) > 2 else None,
                     "hq_city_table": re.sub(r"\[\[(?:[^\]|]+\|)?([^\]]+)\]\]", r"\1", c[5]) if len(c) > 5 else None,
                     "state_table": None,
                     "source_url": f"https://de.wikipedia.org/w/index.php?title=MDAX&oldid={rev}", "retrieved_at": ts})
    return pd.DataFrame(rows)


def _qids(titles: list[str]) -> dict[str, str]:
    out = {}
    for i in range(0, len(titles), 40):
        r = fetch(WIKI_API, params={"action": "query", "titles": "|".join(titles[i:i + 40]), "prop": "pageprops",
                                    "ppprop": "wikibase_item", "redirects": "1", "format": "json", "formatversion": "2"})
        j = r.json()["query"]
        back = {x["to"]: x["from"] for x in j.get("redirects", [])}
        norm = {x["to"]: x["from"] for x in j.get("normalized", [])}
        for p in j["pages"]:
            t = p["title"]
            src = back.get(t, t)
            src = norm.get(src, src)
            if "pageprops" in p:
                out[src] = p["pageprops"]["wikibase_item"]
    return out


def _sparql(query: str):
    r = fetch(SPARQL, params={"query": query, "format": "json"}, headers={"Accept": "application/sparql-results+json"}, retries=2)
    return r.json()["results"]["bindings"], r.retrieved_at


def _wikidata_facts(qids: list[str]) -> pd.DataFrame:
    """HQ (P159), ISIN, LEI per company; then, per distinct HQ place, whether it lies in Bavaria (P131* Q980).
    Two small queries instead of one path query over all companies (that one times out)."""
    vals = " ".join(f"wd:{q}" for q in qids)
    rows, ts = _sparql(f"""SELECT ?item ?hq (GROUP_CONCAT(DISTINCT ?isin; separator="|") AS ?isins)
                                  (GROUP_CONCAT(DISTINCT ?lei; separator="|") AS ?leis) WHERE {{
        VALUES ?item {{ {vals} }}
        OPTIONAL {{ ?item wdt:P159 ?hq . }} OPTIONAL {{ ?item wdt:P946 ?isin . }} OPTIONAL {{ ?item wdt:P1278 ?lei . }}
      }} GROUP BY ?item ?hq""")
    g = lambda b, k: b.get(k, {}).get("value")
    d = pd.DataFrame([{"qid": g(b, "item").rsplit("/", 1)[1], "hq_qid": (g(b, "hq") or "").rsplit("/", 1)[-1] or None,
                       "isin": g(b, "isins") or None, "lei": g(b, "leis") or None} for b in rows])
    hqs = sorted({h for h in d.hq_qid if h})
    bav, labels = set(), {}
    for i in range(0, len(hqs), 50):
        hv = " ".join(f"wd:{h}" for h in hqs[i:i + 50])
        res, _ = _sparql(f"""SELECT ?hq ?hqLabel ?bav WHERE {{ VALUES ?hq {{ {hv} }}
            BIND(EXISTS {{ ?hq wdt:P131* wd:{BAVARIA} }} AS ?bav)
            SERVICE wikibase:label {{ bd:serviceParam wikibase:language "de,en". }} }}""")
        for b in res:
            h = g(b, "hq").rsplit("/", 1)[1]
            labels[h] = g(b, "hqLabel")
            if g(b, "bav") == "true":
                bav.add(h)
    d["hq_wikidata"] = d.hq_qid.map(labels)
    d["hq_in_bavaria_wikidata"] = d.hq_qid.isin(bav)
    d["wikidata_retrieved_at"] = ts
    return d.groupby("qid").agg({"hq_wikidata": lambda s: "|".join(sorted({x for x in s if isinstance(x, str)})),
                                 "hq_in_bavaria_wikidata": "max", "isin": "first", "lei": "first",
                                 "wikidata_retrieved_at": "first"}).reset_index()


def members() -> pd.DataFrame:
    m = index_members()
    qmap = _qids(sorted({t for t in m.wiki_title if t}))
    m["qid"] = m.wiki_title.map(qmap)
    wd = _wikidata_facts(sorted({q for q in m.qid if isinstance(q, str)}))
    m = m.merge(wd, on="qid", how="left")
    table_bav = m.state_table.fillna("").str.contains("Bayern")
    m["hq_in_bavaria"] = m.hq_in_bavaria_wikidata.fillna(False).astype(bool) | table_bav
    m["bavaria_method"] = [("wikidata_p159_p131+dax_table" if w and t else "wikidata_p159_p131" if w else "dax_table_state" if t else None)
                           for w, t in zip(m.hq_in_bavaria_wikidata.fillna(False), table_bav)]
    m["is_financial"] = m.sector_label.fillna("").str.contains(FIN_WORDS)
    m["slice"] = "bavaria_dax_mdax"
    INTERIM.mkdir(parents=True, exist_ok=True)
    m.to_csv(INTERIM / "dach_index_members.csv", index=False)
    return m


def swiss_austrian(n_ch: int = 8, n_at: int = 5) -> pd.DataFrame:
    """Largest listed industrials headquartered in CH or AT that are already in the universe. US SEC filers
    (Garmin, Amrize) are left out: their DPO already comes from 10-K XBRL with a trade-payables line."""
    u = pd.read_parquet(ROOT / "data" / "processed" / "universe.parquet")
    listed = u[["isin", "lei", "cik", "tickers", "stock_indices"]].notna().any(axis=1)
    ok = u.country.isin(["CH", "AT"]) & u.sector.isin(INDUSTRIAL) & listed & ~u.is_subsidiary_or_unit.fillna(False) \
        & ~u.not_a_company.fillna(False) & u.parent_company_id.isna() & u.cik.isna()
    c = u[ok].sort_values("revenue_usd", ascending=False)
    out = pd.concat([c[c.country == "CH"].head(n_ch), c[c.country == "AT"].head(n_at)])
    return out[["company_id", "name", "country", "hq_city", "sector", "revenue_usd", "isin", "lei", "cik", "wikidata_qid"]]



# ---------------------------------------------------------------- documents
from chase.common.http import fetch_to_file, write_manifest  # noqa: E402
from chase.resolve.universe import slugify  # noqa: E402

FIELDS = ("trade_payables", "cost_of_sales", "cost_of_materials", "revenue")
ESEF_API = "https://filings.xbrl.org/api/entities/{lei}/filings"


def _scout() -> dict:
    p = INTERIM / "dach_documents_scout.json"
    return {slugify(x["name"]): x for x in json.loads(p.read_text())} if p.exists() else {}


def _scout_for(name: str, sc: dict):
    k = slugify(name)
    first = k.split("-")[0]
    return sc.get(k) or next((v for kk, v in sc.items() if kk.split("-")[0] == first), None)


def docs() -> pd.DataFrame:
    """Download each report (polite cached client) into data/raw/dach/<slug>/ and write page texts."""
    from zipfile import ZipFile
    from chase.sources.dach_extract import pdf_pages, xhtml_pages
    t = pd.read_csv(INTERIM / "dach_targets.csv")
    sc = _scout()
    rows, manifest = [], []
    for _, r in t.iterrows():
        slug = slugify(r["name"])
        d = RAW / slug
        rec = {"name": r["name"], "slug": slug, "pdf_url": None, "esef_url": None, "esef_json_url": None, "fiscal_year_end": None,
               "ir_page_url": None, "doc_used_for_text": None, "pages": 0, "status": "ok", "scout_notes": None}
        s_ = _scout_for(r["name"], sc) or {}
        rec.update(pdf_url=s_.get("pdf_url"), esef_url=s_.get("esef_url"), fiscal_year_end=s_.get("fiscal_year_end"),
                   ir_page_url=s_.get("ir_page_url"), scout_notes=s_.get("notes"))
        if isinstance(r.lei, str):        # ESEF filers in the filings.xbrl.org repository (Austria here; Germany is not covered there)
            try:
                for lei in r.lei.split("|"):
                    j = fetch(ESEF_API.format(lei=lei), params={"sort": "-period_end", "page[size]": "5"}).json()
                    fl = [f["attributes"] for f in j.get("data", []) if f["attributes"].get("json_url")]
                    if fl:
                        f = sorted(fl, key=lambda a: (a["period_end"], a["json_url"].endswith("-en.json")), reverse=True)[0]
                        rec["esef_json_url"] = "https://filings.xbrl.org" + f["json_url"]
                        rec["esef_url"] = rec["esef_url"] or "https://filings.xbrl.org" + f["report_url"]
                        rec["fiscal_year_end"] = rec["fiscal_year_end"] or f["period_end"]
                        manifest.append(fetch_to_file(rec["esef_json_url"], d / "esef.json"))
                        break
            except Exception as e:      # 404: the filer is not in the repository (all German filers, Swiss companies)
                rec["esef_repository"] = "not on filings.xbrl.org" if "404" in str(e) else f"lookup failed: {e}"[:120]
        texts = None
        if rec["pdf_url"]:
            try:
                # Accept header only (some IR servers answer 406 without it); our own User-Agent, never a browser's
                manifest.append(fetch_to_file(rec["pdf_url"], d / "report.pdf", headers={"Accept": "application/pdf,*/*"}))
                texts, rec["doc_used_for_text"] = pdf_pages(d / "report.pdf"), "pdf"
            except Exception as e:
                rec["status"] = f"pdf failed: {e}"[:200]
        if rec["esef_url"]:
            try:
                m = fetch_to_file(rec["esef_url"], d / ("esef.zip" if rec["esef_url"].lower().endswith(".zip") else "esef.xhtml"))
                manifest.append(m)
                xb = None
                if rec["esef_url"].lower().endswith(".zip"):
                    with ZipFile(d / "esef.zip") as z:
                        names = [n for n in z.namelist() if n.lower().endswith((".xhtml", ".html")) and "/reports/" in n.lower()] or \
                                [n for n in z.namelist() if n.lower().endswith((".xhtml", ".html"))]
                        if names:
                            xb = z.read(max(names, key=lambda n: z.getinfo(n).file_size))
                            (d / "esef.xhtml").write_bytes(xb)
                else:
                    xb = (d / "esef.xhtml").read_bytes()
                if texts is None and xb:
                    texts, rec["doc_used_for_text"] = xhtml_pages(xb), "esef_xhtml"
            except Exception as e:
                rec["status"] = (rec["status"] + f"; esef failed: {e}")[:200]
        if texts:
            (d / "pages").mkdir(parents=True, exist_ok=True)
            for i, tx in enumerate(texts, 1):
                (d / "pages" / f"p{i:04d}.txt").write_text(tx)
            rec["pages"] = len(texts)
        elif rec["status"] == "ok":
            rec["status"] = "no document"
        rows.append(rec)
        print(f"{r['name']}: {rec['doc_used_for_text']} {rec['pages']} pages {rec['status']}")
    out = pd.DataFrame(rows)
    out.to_csv(INTERIM / "dach_documents.csv", index=False)
    write_manifest("dach_documents", manifest)
    return out


# ---------------------------------------------------------------- extractor A
TRADE_CONCEPTS = ["TradeAndOtherCurrentPayablesToTradeSuppliers", "CurrentTradePayables", "TradeAndOtherPayablesToTradeSuppliers", "TradePayables"]


def _facts_for(d: Path) -> dict:
    from chase.sources.dach_extract import ixbrl_facts
    from chase.sources.esef_xbrl import consolidated_facts
    if (d / "esef.json").exists():
        return consolidated_facts(json.loads((d / "esef.json").read_text()))
    if (d / "esef.xhtml").exists():
        return ixbrl_facts((d / "esef.xhtml").read_bytes())
    return {}


def _from_facts(facts: dict) -> list[dict]:
    from chase.sources.esef_xbrl import fiscal_years, main_currency
    fys = fiscal_years(facts) if facts else []
    if not fys:
        return []
    unit = main_currency(facts, fys[0])
    out = []
    def get(local, s, e):
        for (c, s_, e_, u), v in facts.items():
            if u == unit and c.split(":")[-1] == local and s_ == s and e_ == e:
                return v
        return None
    for rank, (s, e) in enumerate(fys, 1):
        vals = {}
        for c in TRADE_CONCEPTS:
            v = get(c, None, e)
            if v:
                vals["trade_payables"] = (abs(v), "ifrs-full:" + c); break
        for f, c in (("cost_of_sales", "CostOfSales"), ("cost_of_materials", "RawMaterialsAndConsumablesUsed"), ("revenue", "Revenue")):
            v = get(c, s, e)
            if v:
                vals[f] = (abs(v), "ifrs-full:" + c)
        for f, (v, c) in vals.items():
            out.append({"year_rank": rank, "period_end": e.isoformat(), "field": f, "value": v, "currency": unit.split(":")[-1],
                        "method": "xbrl_fact", "concept": c, "page": None, "quote": None})
    return out


def extract_a() -> pd.DataFrame:
    from chase.sources.dach_extract import extract_text
    docs_ = pd.read_csv(INTERIM / "dach_documents.csv")
    rows = []
    for _, r in docs_.iterrows():
        d = RAW / r.slug
        got = _from_facts(_facts_for(d))
        have = {(x["year_rank"], x["field"]) for x in got}
        pages = [p.read_text() for p in sorted((d / "pages").glob("p*.txt"))] if (d / "pages").exists() else []
        fye = str(r.fiscal_year_end)[:10] if isinstance(r.fiscal_year_end, str) else None
        if pages:
            tx = extract_text(pages)
            for f, v in tx.items():
                if f.startswith("_"):
                    continue
                for rank, key in ((1, "current"), (2, "prior")):
                    if (rank, f) in have or v.get("scale") is None:
                        continue
                    pe = fye if rank == 1 else (f"{int(fye[:4]) - 1}{fye[4:]}" if fye else None)
                    got.append({"year_rank": rank, "period_end": pe, "field": f, "value": v[key] * v["scale"], "currency": v["currency"],
                                "method": "printed_" + v.get("where", "statement"), "concept": None, "page": v["page"], "quote": v["quote"]})
        for x in got:
            rows.append({"name": r["name"], "slug": r.slug, **x})
    a = pd.DataFrame(rows)
    a.to_csv(INTERIM / "dach_extract_a.csv", index=False)
    return a


# ---------------------------------------------------------------- reconcile, adjudication, final
TOL = 0.005          # A and B agree when within 0.5%
MIN_COST_SHARE = 0.2 # below this share of revenue the cost line is not a supplier-spend base


def _b() -> pd.DataFrame:
    """Extractor B's output; the agent wrote it in parts, merged here into dach_extract_b.json."""
    parts = sorted(INTERIM.glob("dach_extract_b_part*.json"))
    p = INTERIM / "dach_extract_b.json"
    if parts:
        rows = [x for f in parts for x in json.loads(f.read_text())]
        p.write_text(json.dumps(rows, indent=1, ensure_ascii=False))
        for f in parts:
            f.unlink()
    return pd.DataFrame(json.loads(p.read_text())) if p.exists() else pd.DataFrame(columns=["name", "year_rank", "field", "value"])


def reconcile() -> pd.DataFrame:
    a = pd.read_csv(INTERIM / "dach_extract_a.csv")
    b = _b()
    k = ["name", "year_rank", "field"]
    m = a.rename(columns={c: f"{c}_a" for c in a.columns if c not in k}).merge(
        b.rename(columns={c: f"{c}_b" for c in b.columns if c not in k}), on=k, how="outer")
    def status(r):
        va, vb = r.get("value_a"), r.get("value_b")
        if pd.isna(va) and pd.isna(vb):
            return "neither"
        if pd.isna(va) or pd.isna(vb):
            return "only_a" if pd.isna(vb) else "only_b"
        return "agree" if abs(va - vb) <= TOL * max(abs(va), abs(vb)) else "disagree"
    m["status"] = m.apply(status, axis=1)
    m = m.sort_values(k)
    m.to_csv(INTERIM / "dach_reconcile.csv", index=False)
    # every value that feeds DPO and is not an agreement goes to QA; so does revenue for universe additions
    q = m[(m.status != "agree") & m.field.isin(["trade_payables", "cost_of_sales", "cost_of_materials", "revenue"])]
    (INTERIM / "dach_adjudication_queue.json").write_text(json.dumps(
        [{kk: (None if pd.isna(v) else v) for kk, v in r.items()} for r in q.to_dict("records")], indent=1, ensure_ascii=False, default=str))
    return m


def final() -> pd.DataFrame:
    """Accepted values: A and B agree, or the QA adjudication decided. -> dach_values.csv and dach_dpo.parquet."""
    from chase.sources.esef_xbrl import dpo_flag
    m = pd.read_csv(INTERIM / "dach_reconcile.csv")
    adj_p = INTERIM / "dach_adjudication.json"
    adj = {(x["name"], int(x["year_rank"]), x["field"]): x for x in json.loads(adj_p.read_text())} if adj_p.exists() else {}
    docs_ = pd.read_csv(INTERIM / "dach_documents.csv").set_index("name")
    man = {x["source_url"]: x for x in json.loads((ROOT / "data" / "manifests" / "dach_documents.json").read_text())} \
        if (ROOT / "data" / "manifests" / "dach_documents.json").exists() else {}
    vals = []
    for _, r in m.iterrows():
        key = (r["name"], int(r.year_rank), r.field)
        if r.status == "agree":
            v = dict(value=r.value_a, currency=r.currency_a if isinstance(r.currency_a, str) else r.get("currency_b"),
                     page=r.page_b if not pd.isna(r.get("page_b")) else r.page_a, quote=r.quote_b if isinstance(r.get("quote_b"), str) else r.quote_a,
                     period_end=r.period_end_a if isinstance(r.period_end_a, str) else r.get("period_end_b"), how="dual_extractor_agreement")
        elif key in adj and adj[key].get("value") is not None:
            x = adj[key]
            v = dict(value=float(x["value"]), currency=x.get("currency"), page=x.get("page"), quote=x.get("quote"),
                     period_end=x.get("period_end") or (r.period_end_a if isinstance(r.period_end_a, str) else r.get("period_end_b")),
                     how="qa_adjudication", reasoning=x.get("reasoning"))
        else:
            continue
        vals.append({"name": r["name"], "year_rank": int(r.year_rank), "field": r.field, **v})
    V = pd.DataFrame(vals)
    V.to_csv(INTERIM / "dach_values.csv", index=False)

    t = pd.read_csv(INTERIM / "dach_targets.csv").set_index("name")
    rows = []
    for (name, rank), g in V.groupby(["name", "year_rank"]):
        f = {x.field: x for x in g.itertuples()}
        tp = f.get("trade_payables")
        cost = f.get("cost_of_sales") or f.get("cost_of_materials")
        basis = "cost_of_sales" if "cost_of_sales" in f else ("cost_of_materials" if "cost_of_materials" in f else "missing")
        d = docs_.loc[name]
        url = d.pdf_url if isinstance(d.pdf_url, str) else (d.esef_url if isinstance(d.esef_url, str) else d.esef_json_url)
        pe = next((x.period_end for x in f.values() if isinstance(x.period_end, str)), None)
        dpo = round(tp.value / cost.value * 365, 1) if tp is not None and cost is not None and cost.value else None
        rev = f["revenue"].value if "revenue" in f else None
        # a cost base under 20% of revenue (software, marketplaces) makes payables/cost meaningless, not "slow"
        small_base = dpo is not None and rev and cost.value < MIN_COST_SHARE * rev
        how = sorted({x.how for x in (tp, cost) if x is not None})
        tr = t.loc[name]
        rows.append({
            "name": name, "qid": tr.qid, "lei": tr.lei if isinstance(tr.lei, str) else None, "isin": tr.isin if isinstance(tr.isin, str) else None,
            "slice": tr.slice, "fiscal_year": int(pe[:4]) if pe else None, "period_end": pe,
            "period_start": (pd.Timestamp(pe) - pd.DateOffset(years=1) + pd.Timedelta(days=1)).date().isoformat() if pe else None,
            "currency": (tp or cost).currency if (tp or cost) is not None else None,
            "revenue": f["revenue"].value if "revenue" in f else None,
            "cost_of_sales": cost.value if cost is not None else None, "cost_concept": basis, "cost_basis": basis,
            "payables": tp.value if tp is not None else None, "payables_concept": "trade_payables_to_suppliers",
            "payables_basis": "trade" if tp is not None else None,
            "dpo": None if small_base else dpo, "dpo_flag": "not_meaningful_small_cost_base" if small_base else dpo_flag(dpo, False),
            "dpo_unscored": dpo if small_base else None,
            # cost of materials (nature-of-expense reporters) is a narrower base than cost of sales: lower confidence,
            # so these rows do not enter the sector medians and are scaled down in the pain score (0.7, the same as the
            # existing by-nature ESEF rows: below the Tier 1 pain threshold on the proxy alone)
            "confidence": (1.0 if basis == "cost_of_sales" else 0.7) if dpo is not None and not small_base else None,
            "extraction_method": "+".join(how) if how else None,
            "source_url": url, "filing_url": url,
            "source_type": "annual_report_esef" if d.doc_used_for_text == "esef_xhtml" else "annual_report_pdf",
            "retrieved_at": (man.get(url) or {}).get("retrieved_at"),
            "notes": "; ".join(f"{x.field} p.{int(x.page) if not pd.isna(x.page) else '?'}: {str(x.quote)[:120]}" for x in (tp, cost) if x is not None),
        })
    out = pd.DataFrame(rows)
    import yaml
    per = (yaml.safe_load((ROOT / "config" / "dach_slice.yaml").read_text()) or {}).get("perimeter_change_prior_year") or {}
    latest_fy = out.groupby("name").fiscal_year.transform("max")
    hit = out.name.isin(per) & (out.fiscal_year < latest_fy) & out.dpo.notna()
    out.loc[hit, "dpo_flag"] = "perimeter_change"
    out.loc[hit, "notes"] = out.loc[hit, "name"].map(per) + "; " + out.loc[hit, "notes"].fillna("")
    out.to_parquet(INTERIM / "dach_dpo.parquet", index=False)
    out.to_csv(INTERIM / "dach_dpo.csv", index=False)
    return out


def universe_additions(u: pd.DataFrame) -> pd.DataFrame:
    """Rows for Bavarian DAX/MDAX members missing from the universe (config/dach_slice.yaml), in the universe schema."""
    import yaml
    from chase.sources.esef_xbrl import load_fx, to_usd
    cfg = (yaml.safe_load((ROOT / "config" / "dach_slice.yaml").read_text()) or {}).get("additions") or {}
    vp, mp = INTERIM / "dach_dpo.csv", INTERIM / "dach_index_members.csv"
    if not cfg or not vp.exists() or not mp.exists():
        return pd.DataFrame()
    have_q = {q for v in u.wikidata_qid.dropna() for q in str(v).split("|")}
    have_l = {x for v in u.lei.dropna() for x in str(v).split("|")}
    dp = pd.read_csv(vp)
    mem = pd.read_csv(mp).drop_duplicates("qid").set_index("qid")
    fx = load_fx()
    rows = []
    for qid, c in cfg.items():
        if qid in have_q or (qid in mem.index and isinstance(mem.loc[qid].lei, str) and set(mem.loc[qid].lei.split("|")) & have_l):
            continue
        d = dp[(dp.qid == qid)].sort_values("fiscal_year", ascending=False)
        if d.empty or pd.isna(d.iloc[0].revenue):
            continue
        r, mm = d.iloc[0], mem.loc[qid] if qid in mem.index else None
        usd, _ = to_usd(float(r.revenue), r.currency, int(r.fiscal_year), fx)
        rows.append({
            "company_id": f"{slugify(c['name'])}-{qid.lower()}", "name": c["name"], "legal_names": mm["name"] if mm is not None else c["name"],
            "aliases": mm["name"] if mm is not None else None, "country": "DE", "country_method": "dach_slice_index_table",
            "hq_city": c.get("hq_city"), "sector": c["sector"], "sector_method": "manual_dach_slice", "sector_confidence": 0.9,
            "revenue": float(r.revenue), "revenue_currency": r.currency, "revenue_usd": usd,
            "revenue_period_start": r.period_start, "revenue_period_end": r.period_end,
            "revenue_source_type": r.source_type, "revenue_source_url": r.source_url, "revenue_confidence": 1.0, "revenue_stale": False,
            "isin": mm.isin if mm is not None and isinstance(mm.isin, str) else None, "lei": mm.lei if mm is not None and isinstance(mm.lei, str) else None,
            "cik": None, "wikidata_qid": qid, "stock_indices": mm["index"] if mm is not None else None,
            "in_sec": False, "in_esef": False, "in_wikidata": True, "merge_methods": "dach_slice_index_member",
            "source_url": mm.source_url if mm is not None else None, "source_type": "dach_slice_index_member",
            "retrieved_at": mm.retrieved_at if mm is not None else None, "period_start": r.period_start, "period_end": r.period_end,
            "extraction_method": "index_membership+annual_report_revenue", "confidence": 1.0,
            "is_subsidiary_or_unit": False, "not_a_company": False, "parent_company_id": None,
        })
    return pd.DataFrame(rows)


def targets() -> pd.DataFrame:
    """The extraction list: Bavarian DAX/MDAX non-financials + CH/AT industrials -> dach_targets.csv."""
    m = pd.read_csv(INTERIM / "dach_index_members.csv")
    bav = m[m.hq_in_bavaria & ~m.is_financial].drop_duplicates("qid")
    rows = [{"slice": "bavaria_dax_mdax", "index": r["index"], "name": r["name"], "qid": r.qid, "isin": r.isin, "lei": r.lei,
             "country": "DE", "hq_city": r.hq_wikidata, "membership_source_url": r.source_url,
             "note": ("registered seat in Bavaria, operations run from elsewhere" if "|" in str(r.hq_wikidata) or r.qid == "Q650259" else None)}
            for _, r in bav.iterrows()]
    for _, r in swiss_austrian().iterrows():
        rows.append({"slice": "ch_at_industrials", "index": None, "name": r["name"], "qid": r.wikidata_qid, "isin": r.isin, "lei": r.lei,
                     "country": r.country, "hq_city": r.hq_city, "company_id": r.company_id, "membership_source_url": "data/processed/universe.parquet", "note": None})
    t = pd.DataFrame(rows)
    t.to_csv(INTERIM / "dach_targets.csv", index=False)
    return t


if __name__ == "__main__":
    step = sys.argv[1] if len(sys.argv) > 1 else "members"
    if step == "members":
        m = members()
        bav = m[m.hq_in_bavaria]
        print(f"{len(m)} index rows, {len(bav)} headquartered in Bavaria ({int(bav.is_financial.sum())} financial)")
        print(bav[["index", "name", "hq_city_table", "hq_wikidata", "bavaria_method", "is_financial", "qid", "isin", "lei"]].to_string())
        print(swiss_austrian().to_string())
    elif step == "docs":
        docs()
    elif step == "extract-a":
        a = extract_a()
        print(a.groupby("name").field.apply(lambda s: ",".join(sorted(set(s)))).to_string())
    elif step == "reconcile":
        m = reconcile()
        print(m.groupby("field").status.value_counts().unstack(fill_value=0).to_string())
    elif step == "final":
        d = final()
        print(d[["name", "fiscal_year", "cost_basis", "dpo", "dpo_flag", "confidence", "extraction_method"]].to_string())
    elif step == "targets":
        print(targets()[["slice", "name", "country", "hq_city", "lei", "note"]].to_string())
