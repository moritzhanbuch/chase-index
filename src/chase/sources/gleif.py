"""HQ city from GLEIF LEI records, for universe companies with no Wikidata headquarters (P159).

The LEI record carries the address the company registered with its LEI issuer: `headquartersAddress` (preferred)
and `legalAddress`. It is the filing address, so it can name a registered seat rather than the operating HQ;
config/overrides.yaml (hq_cities) corrects those with a reason. Public API, no key, batched 100 LEIs per request.

  python -m chase.sources.gleif        -> data/interim/gleif_hq.csv
"""
from __future__ import annotations

from pathlib import Path

import pandas as pd

from chase.common import http

ROOT = Path(__file__).resolve().parents[3]
OUT = ROOT / "data" / "interim" / "gleif_hq.csv"
API = "https://api.gleif.org/api/v1/lei-records"
RECORD = "https://search.gleif.org/#/record/{lei}"


def nice_city(c) -> str | None:
    if not isinstance(c, str) or not c.strip():
        return None
    c = c.strip()
    return c.title() if c.isupper() else c


def run() -> pd.DataFrame:
    u = pd.read_parquet(ROOT / "data" / "processed" / "universe.parquet", columns=["company_id", "name", "hq_city", "lei"])
    todo = u[u.hq_city.isna() & u.lei.notna()].copy()
    todo["lei1"] = todo.lei.str.split("|").str[0].str.strip()
    rows = []
    leis = todo.lei1.tolist()
    for i in range(0, len(leis), 100):
        batch = leis[i:i + 100]
        data = http.fetch_json(API, params={"filter[lei]": ",".join(batch), "page[size]": 100})
        for rec in data.get("data", []):
            a = rec["attributes"]
            ent = a["entity"]
            hq, legal = ent.get("headquartersAddress") or {}, ent.get("legalAddress") or {}
            rows.append({"lei": a["lei"], "hq_city": nice_city(hq.get("city")) or nice_city(legal.get("city")),
                         "hq_city_basis": "gleif_headquarters_address" if nice_city(hq.get("city")) else "gleif_legal_address",
                         "hq_country": hq.get("country") or legal.get("country"), "legal_city": nice_city(legal.get("city")),
                         "legal_name": (ent.get("legalName") or {}).get("name"),
                         "source_url": RECORD.format(lei=a["lei"]), "source_type": "gleif_lei_record",
                         "retrieved_at": http.now_iso()})
    g = pd.DataFrame(rows)
    out = todo[["company_id", "name", "lei1"]].rename(columns={"lei1": "lei"}).merge(g, on="lei", how="left")
    OUT.parent.mkdir(parents=True, exist_ok=True)
    out.to_csv(OUT, index=False)
    print(f"gleif: {out.hq_city.notna().sum()} of {len(out)} missing HQ cities found -> {OUT.relative_to(ROOT)}")
    return out


if __name__ == "__main__":
    run()
