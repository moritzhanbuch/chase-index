"""UK Fair Payment Code awardees directory (Office of the Small Business Commissioner).

Source: https://www.smallbusinesscommissioner.gov.uk/fpc/awardees/ (public HTML directory, paginated,
robots.txt allows crawling). There is no official CSV/JSON download, so this reads the directory pages
through the shared polite client (1 request/second, cached) and keeps company-level fields only.

Run:  python -m chase.sources.uk_fair_payment_code
Out:  data/raw/uk/fair_payment_code_awardees.csv  +  data/manifests/uk_fair_payment_code.json
"""
from __future__ import annotations

import html
import re

import pandas as pd

from chase.common.http import ROOT, fetch, write_manifest

BASE = "https://www.smallbusinesscommissioner.gov.uk/fpc/awardees/"
OUT = ROOT / "data" / "raw" / "uk" / "fair_payment_code_awardees.csv"

_ARTICLE = re.compile(r'<article class="accordion_item[^"]*">(.*?)</article>', re.S)


def _field(block: str, label: str) -> str | None:
    m = re.search(rf"{label}:</strong>(.*?)</p>", block, re.S)
    if not m:
        return None
    txt = html.unescape(re.sub(r"<[^>]+>", " ", m.group(1)))
    return re.sub(r"\s+", " ", txt).strip() or None


def normalise_company_number(raw: str | None) -> str | None:
    """Zero-pad purely numeric Companies House numbers to 8 chars; keep prefixed ones (SC, OC, NI...)."""
    if not raw:
        return None
    s = re.sub(r"\s+", "", raw).upper()
    if s.isdigit() and len(s) <= 8:
        return s.zfill(8)
    m = re.fullmatch(r"([A-Z]{2})(\d{1,6})", s)
    if m:
        return m.group(1) + m.group(2).zfill(6)
    return None  # not a recognisable company number (charity numbers etc.), keep raw only


def parse_page(page_html: str) -> list[dict]:
    rows = []
    for block in _ARTICLE.findall(page_html):
        name = re.search(r'<span class="h3[^"]*">(.*?)</span>', block, re.S)
        award = _field(block, "Award Level")
        level = until = None
        if award:
            m = re.match(r"(Gold|Silver|Bronze)\b(?:.*?Until\s+(\d{4}))?", award)
            if m:
                level, until = m.group(1), m.group(2)
        raw_no = _field(block, "Company House No")
        rows.append({
            "awardee_name": html.unescape(name.group(1)).strip() if name else None,
            "company_number_raw": raw_no,
            "company_number": normalise_company_number(raw_no),
            "industry_sector": _field(block, "Industry Sector"),
            "area": _field(block, "Area"),
            "award_level": level,
            "award_until_year": until,
            "registration_date_text": _field(block, "Registration Date"),
        })
    return rows


def main() -> None:
    first = fetch(BASE, max_age_days=1)
    pages = [int(p) for p in re.findall(r"/fpc/awardees/page/(\d+)/", first.text)]
    last = max(pages) if pages else 1
    rows, entries = [], []
    for n in range(1, last + 1):
        url = BASE if n == 1 else f"{BASE}page/{n}/"
        r = first if n == 1 else fetch(url, max_age_days=1)
        page_rows = parse_page(r.text)
        for row in page_rows:
            row.update(source_url=url, source_type="uk_fair_payment_code_directory",
                       retrieved_at=r.retrieved_at, extraction_method="html_directory_parse", confidence=0.95)
        rows.extend(page_rows)
        entries.append({"source_url": url, "sha256": r.sha256, "bytes": len(r.content),
                        "retrieved_at": r.retrieved_at, "rows": len(page_rows)})
    df = pd.DataFrame(rows)
    df["registration_date"] = pd.to_datetime(df["registration_date_text"], format="%d %B %Y", errors="coerce").dt.date
    OUT.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(OUT, index=False)
    stated = re.search(r"Our\s*(?:<[^>]+>\s*)*(\d[\d,]*)\s*(?:<[^>]+>\s*)*Awardees", first.text)
    write_manifest("uk_fair_payment_code", {
        "output": str(OUT.relative_to(ROOT)), "rows": len(df), "pages": last,
        "awardee_count_stated_on_page": stated.group(1) if stated else None,
        "distinct_names": int(df["awardee_name"].nunique()),
        "with_valid_company_number": int(df["company_number"].notna().sum()),
        "award_levels": df["award_level"].value_counts(dropna=False).to_dict(),
        "pages_fetched": entries,
    })
    print(f"awardees: {len(df)} rows from {last} pages -> {OUT.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
