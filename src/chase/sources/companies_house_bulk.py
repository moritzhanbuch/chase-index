"""Companies House bulk snapshots -> parent chains for UK payment-practice reporting entities.

No API key needed. Two free bulk products from https://download.companieshouse.gov.uk :
  * Free Company Data Product (basic company data, one zip of CSV)
  * People with significant control (PSC) snapshot (JSON lines, many zip parts)

Run:
    python -m chase.sources.companies_house_bulk                 # download if missing, parse, walk
    python -m chase.sources.companies_house_bulk --download-only
    python -m chase.sources.companies_house_bulk --skip-download  # use what is on disk

Privacy: the PSC snapshot also holds natural persons. Lines of individual kinds are dropped by a
string pre-filter before JSON parsing and are never stored. Only corporate-entity and legal-person
PSC records are kept.

Docs: docs/sources/companies_house_bulk.md, docs/data_dictionary_companies_house.md
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import io
import json
import re
import shutil
import sys
import time
import zipfile
from concurrent.futures import ProcessPoolExecutor
from datetime import datetime, timezone
from pathlib import Path

import httpx

from chase.common.http import ROOT, USER_AGENT

BASE = "https://download.companieshouse.gov.uk/"
BASIC_PAGE = BASE + "en_output.html"
PSC_PAGE = BASE + "en_pscdata.html"

RAW_DIR = ROOT / "data" / "raw" / "companies_house"
PSC_PARTS_DIR = RAW_DIR / "psc_parts_parsed"
BASIC_ALL_PARQUET = RAW_DIR / "basic_all.parquet"
MANIFEST = ROOT / "data" / "manifests" / "companies_house_bulk.json"
INTERIM = ROOT / "data" / "interim"
PSC_OUT = INTERIM / "ch_psc_corporate.parquet"
BASIC_OUT = INTERIM / "ch_basic_reporting.parquet"
CHAINS_OUT = INTERIM / "ch_parent_chains.parquet"
UK_PARQUET = ROOT / "data" / "processed" / "uk_payment_practices.parquet"
UK_RAW_DIR = ROOT / "data" / "raw" / "uk"

KEEP_KINDS = (
    "corporate-entity-person-with-significant-control",
    "legal-person-person-with-significant-control",
)
MAX_HOPS = 10
PAUSE_BETWEEN_FILES = 1.5  # seconds, sequential downloads only


def now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


# --------------------------------------------------------------------------------------
# Download
# --------------------------------------------------------------------------------------

def _client() -> httpx.Client:
    return httpx.Client(
        headers={"User-Agent": USER_AGENT},
        timeout=httpx.Timeout(60.0, read=300.0),
        follow_redirects=True,
    )


def discover(client: httpx.Client) -> dict:
    """Read the two index pages and return the current file names."""
    basic_html = client.get(BASIC_PAGE).text
    time.sleep(1.0)
    psc_html = client.get(PSC_PAGE).text
    basic = sorted(set(re.findall(r'href="(BasicCompanyDataAsOneFile-[\d-]+\.zip)"', basic_html)))
    psc = sorted(
        set(re.findall(r'href="(psc-snapshot-[\d-]+_\d+of\d+\.zip)"', psc_html)),
        key=lambda n: int(re.search(r"_(\d+)of", n).group(1)),
    )
    if not basic or not psc:
        raise RuntimeError("Could not find bulk file links on the Companies House download pages")
    return {"basic": basic[-1], "psc": psc}


def _sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def _load_manifest() -> dict:
    if MANIFEST.exists():
        return json.loads(MANIFEST.read_text())
    return {"source_pages": {"basic": BASIC_PAGE, "psc": PSC_PAGE}, "files": {}}


def _save_manifest(m: dict) -> None:
    MANIFEST.parent.mkdir(parents=True, exist_ok=True)
    MANIFEST.write_text(json.dumps(m, indent=2, sort_keys=True))


def download_file(client: httpx.Client, name: str, manifest: dict) -> Path:
    """Streaming, resumable download of one file. Skips when the size on disk matches."""
    url = BASE + name
    dest = RAW_DIR / name
    part = dest.with_suffix(dest.suffix + ".part")
    head = client.head(url)
    head.raise_for_status()
    size = int(head.headers.get("content-length", 0))
    if dest.exists() and size and dest.stat().st_size == size:
        if name not in manifest["files"]:
            manifest["files"][name] = {
                "url": url, "bytes": size, "sha256": _sha256(dest),
                "retrieved_at": datetime.fromtimestamp(dest.stat().st_mtime, timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
                "last_modified": head.headers.get("last-modified"),
            }
            _save_manifest(manifest)
        return dest
    for attempt in range(5):
        have = part.stat().st_size if part.exists() else 0
        headers = {"Range": f"bytes={have}-"} if have else {}
        try:
            with client.stream("GET", url, headers=headers) as r:
                if r.status_code == 200 and have:
                    have = 0  # server ignored the range: start over
                elif r.status_code not in (200, 206):
                    r.raise_for_status()
                with part.open("ab" if have else "wb") as f:
                    for chunk in r.iter_bytes(1 << 20):
                        f.write(chunk)
            if not size or part.stat().st_size == size:
                break
        except (httpx.TransportError, httpx.HTTPStatusError) as e:
            wait = 2 ** (attempt + 1)
            print(f"  retry {name} after error {e!r}, sleeping {wait}s", flush=True)
            time.sleep(wait)
    else:
        raise RuntimeError(f"Download failed: {url}")
    part.rename(dest)
    manifest["files"][name] = {
        "url": url, "bytes": dest.stat().st_size, "sha256": _sha256(dest),
        "retrieved_at": now_iso(), "last_modified": head.headers.get("last-modified"),
    }
    _save_manifest(manifest)
    return dest


def download_all() -> dict:
    RAW_DIR.mkdir(parents=True, exist_ok=True)
    manifest = _load_manifest()
    with _client() as client:
        names = discover(client)
        manifest["snapshot"] = {"basic": names["basic"], "psc_parts": names["psc"], "discovered_at": now_iso()}
        _save_manifest(manifest)
        for name in [names["basic"], *names["psc"]]:
            t0 = time.time()
            p = download_file(client, name, manifest)
            print(f"ok {name} {p.stat().st_size/1e6:.0f} MB in {time.time()-t0:.0f}s", flush=True)
            time.sleep(PAUSE_BETWEEN_FILES)
    return manifest


def local_files() -> dict:
    """File names to parse: those recorded in the manifest snapshot, if present on disk."""
    m = _load_manifest()
    snap = m.get("snapshot")
    if not snap:
        raise RuntimeError("No manifest snapshot: run the download first")
    return {
        "basic": RAW_DIR / snap["basic"],
        "psc": [RAW_DIR / n for n in snap["psc_parts"]],
    }


# --------------------------------------------------------------------------------------
# Normalisation helpers (pure functions, tested)
# --------------------------------------------------------------------------------------

_UK_PREFIXES = (
    "SC", "NI", "OC", "SO", "NC", "LP", "SL", "NL", "FC", "SF", "NF", "BR", "OE", "IP", "SP", "RC",
    "SR", "NR", "SE", "CE", "CS", "GE", "GS", "IC", "SI", "NP", "NO", "RS", "ZC", "AC", "SA", "NA",
    "PC", "R",
)
_UK_NUM_RE = re.compile(r"^(" + "|".join(_UK_PREFIXES) + r")?(\d{1,8})$")


def norm_company_number(raw: str | None) -> str | None:
    """Normalise a registration number to the 8-char Companies House form when it looks like one.

    '2065'->'00002065', 'SC 12345'->'SC012345', '04366849 '->'04366849'. Returns None otherwise.
    Looking like a UK number is not proof: a foreign number can collide. The chain walk therefore
    also checks the name or the country before it accepts a hop.
    """
    if not raw:
        return None
    s = re.sub(r"[\s.\-/]", "", str(raw).upper())
    s = re.sub(r"^(NO|NUMBER|COMPANYNUMBER|COMPANYNO|REGNO|CRN)[:#]?(?=\d)", "", s)
    m = _UK_NUM_RE.match(s)
    if not m:
        return None
    prefix, digits = m.group(1) or "", m.group(2)
    width = 8 - len(prefix)
    if len(digits) > width:
        return None
    if int(digits) == 0:
        return None
    return prefix + digits.zfill(width)


_SUFFIXES = [
    (r"\bPUBLIC LIMITED COMPANY\b", "PLC"),
    (r"\bP L C\b", "PLC"),
    (r"\bLIMITED LIABILITY PARTNERSHIP\b", "LLP"),
    (r"\bLIMITED\b", "LTD"),
    (r"\bCOMPANY\b", "CO"),
    (r"\bCORPORATION\b", "CORP"),
    (r"\bINCORPORATED\b", "INC"),
    (r"\bCYFYNGEDIG\b", "LTD"),
]


def norm_name(name: str | None) -> str:
    """Conservative company-name key: upper case, & -> AND, no punctuation, legal suffix unified."""
    if not name:
        return ""
    s = str(name).upper().replace("&", " AND ")
    s = re.sub(r"\(\s*THE\s*\)", " ", s)  # register style: "SHELL PETROLEUM COMPANY LIMITED(THE)"
    s = re.sub(r"[.'’`]", "", s)
    s = re.sub(r"[^A-Z0-9]+", " ", s).strip()
    if s.startswith("THE "):
        s = s[4:]
    for pat, rep in _SUFFIXES:
        s = re.sub(pat, rep, s)
    return re.sub(r"\s+", " ", s).strip()


_ISO = {
    "GB": [
        "UNITED KINGDOM", "UK", "U K", "GB", "GREAT BRITAIN", "ENGLAND", "ENGLAND AND WALES", "ENGLAND WALES",
        "WALES", "SCOTLAND", "NORTHERN IRELAND", "ENGLAND UK", "ENGLAND UNITED KINGDOM", "UNITED KINGDOM ENGLAND",
        "UNITED KINGDOM ENGLAND AND WALES", "ENGLAND AND WALES UNITED KINGDOM", "UK ENGLAND AND WALES",
        "ENGLAND AND WALES UK", "SCOTLAND UK", "SCOTLAND UNITED KINGDOM", "UNITED KINGDOM SCOTLAND", "BRITAIN",
        "ENGLAND AND WALES COMPANIES HOUSE", "COMPANIES HOUSE", "ENGLAND AND WALES COMPANY REGISTRY", "ENGLISH",
        "BRITISH", "ENGLAND AND WALES REGISTRAR OF COMPANIES", "REGISTRAR OF COMPANIES FOR ENGLAND AND WALES",
        "COMPANIES HOUSE ENGLAND AND WALES", "REGISTRAR OF COMPANIES ENGLAND AND WALES", "UK COMPANIES HOUSE",
        "COMPANIES HOUSE UK", "REGISTRAR OF COMPANIES", "COMPANIES HOUSE CARDIFF", "CARDIFF", "LONDON",
        "COMPANIES HOUSE ENGLAND", "COMPANIES HOUSE SCOTLAND", "COMPANIES HOUSE EDINBURGH", "EDINBURGH",
        "COMPANIES HOUSE UNITED KINGDOM", "UNITED KINGDOM COMPANIES HOUSE", "REGISTER OF COMPANIES",
        "ENGLAND AND WALES COMPANIES REGISTRY", "COMPANIES REGISTRY ENGLAND AND WALES", "UK REGISTER OF COMPANIES",
        "REGISTRAR OF COMPANIES ENGLAND", "REGISTRAR OF COMPANIES SCOTLAND", "COMPANIES HOUSE NORTHERN IRELAND",
        "COMPANIES HOUSE BELFAST", "BELFAST", "REGISTER OF COMPANIES ENGLAND AND WALES",
    ],
    "US": [
        "UNITED STATES", "UNITED STATES OF AMERICA", "USA", "US", "U S A", "U S", "AMERICA", "DELAWARE",
        "DELAWARE USA", "STATE OF DELAWARE", "DELAWARE UNITED STATES", "NEW YORK", "CALIFORNIA", "TEXAS",
        "NEW JERSEY", "ILLINOIS", "OHIO", "MASSACHUSETTS", "FLORIDA", "NEVADA", "PENNSYLVANIA", "MICHIGAN",
        "MINNESOTA", "VIRGINIA", "MARYLAND", "GEORGIA USA", "WASHINGTON", "INDIANA", "WISCONSIN", "CONNECTICUT",
        "NORTH CAROLINA", "COLORADO", "MISSOURI", "OREGON", "TENNESSEE", "ARIZONA", "UTAH", "KENTUCKY",
        "DELAWARE US", "USA DELAWARE", "UNITED STATES DELAWARE", "DELAWARE UNITED STATES OF AMERICA",
        "STATE OF DELAWARE USA", "NEW YORK USA", "CALIFORNIA USA", "DELAWARE SECRETARY OF STATE",
        "DELAWARE DIVISION OF CORPORATIONS", "STATE OF NEW YORK", "STATE OF CALIFORNIA",
    ],
    "DE": ["GERMANY", "DEUTSCHLAND", "FEDERAL REPUBLIC OF GERMANY", "HANDELSREGISTER", "GERMAN"],
    "FR": ["FRANCE", "FRENCH", "PARIS", "RCS PARIS", "RCS NANTERRE"],
    "NL": ["NETHERLANDS", "THE NETHERLANDS", "HOLLAND", "NEDERLAND", "KAMER VAN KOOPHANDEL", "DUTCH", "AMSTERDAM"],
    "IE": ["IRELAND", "REPUBLIC OF IRELAND", "EIRE", "IRISH", "DUBLIN", "ROI"],
    "LU": ["LUXEMBOURG", "GRAND DUCHY OF LUXEMBOURG", "LUXEMBURG"],
    "JE": ["JERSEY", "JERSEY CHANNEL ISLANDS", "JERSEY CI"],
    "GG": ["GUERNSEY", "GUERNSEY CHANNEL ISLANDS"],
    "IM": ["ISLE OF MAN"],
    "CH": ["SWITZERLAND", "SWISS", "SCHWEIZ"],
    "JP": ["JAPAN", "TOKYO", "JAPANESE"],
    "SE": ["SWEDEN", "SWEDISH"],
    "DK": ["DENMARK", "DANISH"],
    "NO": ["NORWAY", "NORWEGIAN"],
    "FI": ["FINLAND"],
    "ES": ["SPAIN", "ESPANA", "SPANISH", "MADRID"],
    "IT": ["ITALY", "ITALIA", "ITALIAN"],
    "BE": ["BELGIUM", "BELGIAN"],
    "AT": ["AUSTRIA"],
    "PT": ["PORTUGAL"],
    "CA": ["CANADA", "ONTARIO", "ONTARIO CANADA", "BRITISH COLUMBIA", "QUEBEC", "ALBERTA"],
    "AU": ["AUSTRALIA", "NEW SOUTH WALES", "VICTORIA AUSTRALIA"],
    "NZ": ["NEW ZEALAND"],
    "IN": ["INDIA"],
    "CN": ["CHINA", "PEOPLES REPUBLIC OF CHINA", "PRC"],
    "HK": ["HONG KONG", "HONG KONG SAR"],
    "SG": ["SINGAPORE"],
    "KR": ["SOUTH KOREA", "KOREA", "REPUBLIC OF KOREA"],
    "TW": ["TAIWAN"],
    "AE": ["UNITED ARAB EMIRATES", "UAE", "DUBAI", "ABU DHABI"],
    "ZA": ["SOUTH AFRICA"],
    "KY": ["CAYMAN ISLANDS", "CAYMAN", "GRAND CAYMAN"],
    "BM": ["BERMUDA"],
    "VG": ["BRITISH VIRGIN ISLANDS", "BVI", "VIRGIN ISLANDS BRITISH"],
    "GI": ["GIBRALTAR"],
    "MT": ["MALTA"],
    "CY": ["CYPRUS"],
    "IL": ["ISRAEL"],
    "TR": ["TURKEY", "TURKIYE"],
    "PL": ["POLAND"],
    "CZ": ["CZECH REPUBLIC", "CZECHIA"],
    "GR": ["GREECE"],
    "MX": ["MEXICO"],
    "BR": ["BRAZIL"],
    "MY": ["MALAYSIA"],
    "TH": ["THAILAND"],
    "SA": ["SAUDI ARABIA", "KINGDOM OF SAUDI ARABIA"],
    "QA": ["QATAR"],
    "KW": ["KUWAIT"],
    "BH": ["BAHRAIN"],
    "MU": ["MAURITIUS"],
    "LI": ["LIECHTENSTEIN"],
    "BS": ["BAHAMAS", "THE BAHAMAS"],
    "PA": ["PANAMA"],
    "IS": ["ICELAND"],
    "HU": ["HUNGARY"],
    "RO": ["ROMANIA"],
    "NG": ["NIGERIA"],
    "PH": ["PHILIPPINES"],
    "ID": ["INDONESIA"],
    "CL": ["CHILE"],
    "RU": ["RUSSIA", "RUSSIAN FEDERATION"],
}
_ISO_LOOKUP = {v: k for k, vals in _ISO.items() for v in vals}


def _geo_key(s: str | None) -> str:
    if not s:
        return ""
    return re.sub(r"\s+", " ", re.sub(r"[^A-Z]+", " ", str(s).upper().replace("&", " AND "))).strip()


def iso2_guess(country: str | None, place: str | None = None) -> str | None:
    """Best-effort ISO2 from the free-text 'country registered' (fallback: 'place registered').

    Order: exact lookup; then exactly one known country named inside a longer text; then a UK token
    rule. Returns None when the text is empty, unknown or names more than one country.
    """
    for txt in (country, place):
        k = _geo_key(txt)
        if k and k in _ISO_LOOKUP:
            return _ISO_LOOKUP[k]
    k = _geo_key(country) or _geo_key(place)
    # exactly one known country named inside a longer text ("Pennsylvania, United States Of America")
    if k:
        padded = f" {k} "
        hits = {iso for key, iso in _ISO_LOOKUP.items() if len(key) >= 5 and f" {key} " in padded}
        if len(hits) == 1:
            return hits.pop()
    # UK only: token rule for the many spellings ("England, Uk", "Northern Ireland, UK")
    if k and "NEW SOUTH WALES" not in k and "NEW ENGLAND" not in k and _UK_TOKEN_RE.search(k):
        return "GB"
    return None


_UK_TOKEN_RE = re.compile(r"\b(ENGLAND|WALES|SCOTLAND|UNITED KINGDOM|UK|GREAT BRITAIN|COMPANIES HOUSE|NORTHERN IRELAND)\b")
_NO_GEO = {"", "NOT SPECIFIED OTHER", "NOT SPECIFIED", "N A", "NA", "NONE", "UNKNOWN", "OTHER", "NOT APPLICABLE"}


def has_geo_text(country: str | None, place: str | None) -> bool:
    """True if the PSC record carries any usable country/place text."""
    return _geo_key(country) not in _NO_GEO or _geo_key(place) not in _NO_GEO


# --------------------------------------------------------------------------------------
# PSC snapshot parsing (corporate + legal-person only)
# --------------------------------------------------------------------------------------

PSC_COLS = [
    "company_number", "psc_name", "psc_kind", "psc_registration_number", "psc_registration_number_norm",
    "psc_country_registered", "psc_place_registered", "psc_legal_form", "psc_legal_authority",
    "natures_of_control", "notified_on",
]


def parse_psc_line(line: bytes) -> dict | None:
    """One JSON line -> row dict, or None. Individuals never get past the string pre-filter."""
    if b"corporate-entity-person-with-significant-control" not in line and \
            b"legal-person-person-with-significant-control" not in line:
        return None
    rec = json.loads(line)
    d = rec.get("data") or {}
    if d.get("kind") not in KEEP_KINDS:
        return None
    if d.get("ceased_on") or d.get("ceased") is True:
        return None
    ident = d.get("identification") or {}
    raw_num = (ident.get("registration_number") or "").strip() or None
    return {
        "company_number": str(rec.get("company_number") or "").strip().upper().zfill(8),
        "psc_name": (d.get("name") or "").strip(),
        "psc_kind": d["kind"],
        "psc_registration_number": raw_num,
        "psc_registration_number_norm": norm_company_number(raw_num),
        "psc_country_registered": (ident.get("country_registered") or "").strip() or None,
        "psc_place_registered": (ident.get("place_registered") or "").strip() or None,
        "psc_legal_form": (ident.get("legal_form") or "").strip() or None,
        "psc_legal_authority": (ident.get("legal_authority") or "").strip() or None,
        "natures_of_control": "|".join(d.get("natures_of_control") or []),
        "notified_on": d.get("notified_on"),
    }


def _parse_psc_zip(path_str: str) -> tuple[str, int, int]:
    import pandas as pd

    path = Path(path_str)
    out = PSC_PARTS_DIR / (path.stem + ".parquet")
    rows, n_lines = [], 0
    with zipfile.ZipFile(path) as z:
        for member in z.namelist():
            with z.open(member) as f:
                for line in f:
                    n_lines += 1
                    row = parse_psc_line(line)
                    if row:
                        rows.append(row)
    df = pd.DataFrame(rows, columns=PSC_COLS).astype("string")
    tmp = out.with_suffix(".tmp")
    df.to_parquet(tmp, index=False)
    tmp.rename(out)
    return path.name, n_lines, len(df)


def parse_psc(paths: list[Path], workers: int = 6):
    import pandas as pd

    PSC_PARTS_DIR.mkdir(parents=True, exist_ok=True)
    todo = [p for p in paths if p.exists() and not (PSC_PARTS_DIR / (p.stem + ".parquet")).exists()]
    missing = [p.name for p in paths if not p.exists()]
    if missing:
        print(f"WARNING: {len(missing)} PSC parts not on disk, chains will be incomplete: {missing}", flush=True)
    stats_path = PSC_PARTS_DIR / "_line_counts.json"
    stats = json.loads(stats_path.read_text()) if stats_path.exists() else {}
    if todo:
        with ProcessPoolExecutor(max_workers=workers) as ex:
            for name, n_lines, n_kept in ex.map(_parse_psc_zip, [str(p) for p in todo]):
                stats[name] = {"lines": n_lines, "kept": n_kept}
                print(f"parsed {name}: {n_lines:,} lines, kept {n_kept:,}", flush=True)
        stats_path.write_text(json.dumps(stats, indent=1, sort_keys=True))
    parts = [PSC_PARTS_DIR / (p.stem + ".parquet") for p in paths if (PSC_PARTS_DIR / (p.stem + ".parquet")).exists()]
    df = pd.concat([pd.read_parquet(p) for p in parts], ignore_index=True)
    df = df.drop_duplicates().reset_index(drop=True)
    INTERIM.mkdir(parents=True, exist_ok=True)
    df.to_parquet(PSC_OUT if not missing else PSC_OUT.with_suffix(".partial.parquet"), index=False)
    return df, stats, missing


# --------------------------------------------------------------------------------------
# Basic company data
# --------------------------------------------------------------------------------------

def build_basic_all(zip_path: Path) -> None:
    """Basic company CSV (inside the zip) -> slim parquet of all live companies (raw dir, gitignored)."""
    import duckdb

    if BASIC_ALL_PARQUET.exists():
        return
    tmp_dir = RAW_DIR / "extracted_tmp"
    tmp_dir.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(zip_path) as z:
        member = [n for n in z.namelist() if n.lower().endswith(".csv")][0]
        csv_path = tmp_dir / "basic.csv"
        with z.open(member) as src, csv_path.open("wb") as dst:
            shutil.copyfileobj(src, dst, 1 << 22)
    with csv_path.open("r", encoding="utf-8", errors="replace", newline="") as f:
        header = next(csv.reader(f))
    by_clean = {h.strip(): h for h in header}

    def col(clean: str) -> str:
        return '"' + by_clean[clean].replace('"', '""') + '"'

    sic = " || '|' || ".join(f"coalesce({col(f'SICCode.SicText_{i}')}, '')" for i in range(1, 5))
    prev = " || '|' || ".join(f"coalesce({col(f'PreviousName_{i}.CompanyName')}, '')" for i in range(1, 11))
    names_sql = ", ".join("'" + h.replace("'", "''") + "'" for h in header)
    con = duckdb.connect()
    con.execute("SET enable_progress_bar = false")
    out_tmp = BASIC_ALL_PARQUET.with_suffix(".tmp")
    con.execute(f"""
        COPY (
          SELECT upper(trim({col('CompanyNumber')})) AS company_number,
                 trim({col('CompanyName')}) AS company_name,
                 {col('CompanyStatus')} AS status,
                 {col('CompanyCategory')} AS category,
                 {col('RegAddress.PostTown')} AS post_town,
                 {col('RegAddress.PostCode')} AS postcode,
                 {col('RegAddress.Country')} AS country,
                 {col('CountryOfOrigin')} AS country_of_origin,
                 nullif(trim(regexp_replace({sic}, '\\|+', '|', 'g'), '|'), '') AS sic_codes,
                 {col('IncorporationDate')} AS incorporation_date,
                 trim(regexp_replace({prev}, '\\|+', '|', 'g'), '|') AS previous_names
          FROM read_csv('{csv_path}', header=false, skip=1, all_varchar=true, quote='"', escape='"',
                        names=[{names_sql}], null_padding=true, strict_mode=false, parallel=false)
        ) TO '{out_tmp}' (FORMAT parquet)
    """)
    out_tmp.rename(BASIC_ALL_PARQUET)
    csv_path.unlink()  # our own temporary extraction; the zip stays


# --------------------------------------------------------------------------------------
# Hop resolution + chain walk
# --------------------------------------------------------------------------------------

def control_rank(natures: str | None) -> int:
    """Lower is stronger. Used to pick one parent when a company has several active corporate PSCs."""
    n = natures or ""
    if "ownership-of-shares-75-to-100" in n:
        return 0
    if "voting-rights-75-to-100" in n or "75-to-100" in n:
        return 1
    if "ownership-of-shares-50-to-75" in n:
        return 2
    if "50-to-75" in n:
        return 3
    if "right-to-appoint-and-remove" in n:
        return 4
    return 5


def resolve_hop(psc: dict, names_by_number: dict, number_by_name: dict, prev_names_by_number: dict | None = None) -> tuple[str | None, str]:
    """Decide whether a PSC record points at a UK company we can continue from.

    Returns (uk_company_number or None, method). Methods:
      number_and_name  number exists in Companies House data and the name (or a previous name) matches
      number_only      number exists, name differs, registered country reads as UK (or is blank with a UK place)
      name_only        no usable number, normalised name is a unique live UK company, country not foreign
      foreign          registered country/place reads as non-UK
      unresolved       reads as UK or unknown, but no live company found (dissolved, non-CH body, typo)
    """
    prev_names_by_number = prev_names_by_number or {}
    iso = iso2_guess(psc.get("psc_country_registered"), psc.get("psc_place_registered"))
    has_geo = has_geo_text(psc.get("psc_country_registered"), psc.get("psc_place_registered"))
    nname = norm_name(psc.get("psc_name"))
    num = psc.get("psc_registration_number_norm")
    if num and num in names_by_number:
        if nname and (nname == norm_name(names_by_number[num]) or nname in prev_names_by_number.get(num, ())):
            return num, "number_and_name"
        if iso == "GB":
            return num, "number_only"
    # exact unique UK name: accept only when the country reads as UK or no country text was given
    if nname and nname in number_by_name and (iso == "GB" or not has_geo):
        return number_by_name[nname], "name_only"
    if iso not in (None, "GB"):
        return None, "foreign"
    if iso is None and has_geo:
        return None, "foreign_unmapped"  # some country text we could not map and no UK company matched
    return None, "unresolved"


def walk_chain(start: str, psc_by_company: dict, names_by_number: dict, number_by_name: dict,
               prev_names_by_number: dict | None = None, max_hops: int = MAX_HOPS) -> dict:
    """Follow active corporate PSCs upward from one company. Pure function over dict lookups."""
    chain, visited = [], {start}
    current, ambiguous, methods = start, False, []
    top_uk = start
    stop = "max_hops"
    for _ in range(max_hops):
        pscs = psc_by_company.get(current) or []
        if not pscs:
            stop = "no_corporate_psc"
            break
        distinct = {(p.get("psc_registration_number_norm") or norm_name(p.get("psc_name"))) for p in pscs}
        if len(distinct) > 1:
            ambiguous = True
        pick = sorted(pscs, key=lambda p: (control_rank(p.get("natures_of_control")),
                                           0 if p.get("psc_kind") == KEEP_KINDS[0] else 1,
                                           -int((p.get("notified_on") or "0000-00-00").replace("-", "") or 0)))[0]
        nxt, method = resolve_hop(pick, names_by_number, number_by_name, prev_names_by_number)
        if nxt is None:
            iso = iso2_guess(pick.get("psc_country_registered"), pick.get("psc_place_registered"))
            chain.append({"name": pick.get("psc_name"), "company_number": None,
                          "country": pick.get("psc_country_registered") or pick.get("psc_place_registered"),
                          "country_iso2": iso, "match": method})
            if pick.get("psc_kind") == KEEP_KINDS[1] and method == "unresolved":
                stop = "legal_person_psc"
            elif method in ("foreign", "foreign_unmapped"):
                stop = "foreign_parent"
            elif iso == "GB":
                stop = "unresolved_uk_psc"
            else:
                stop = "unresolved_psc"
            break
        if nxt in visited:
            stop = "cycle"
            break
        methods.append(method)
        visited.add(nxt)
        chain.append({"name": names_by_number.get(nxt) or pick.get("psc_name"), "company_number": nxt,
                      "country": "United Kingdom", "country_iso2": "GB", "match": method})
        current = top_uk = nxt
    last = chain[-1] if chain else None
    clean = not ambiguous and all(m == "number_and_name" for m in methods)
    confidence = 0.9 if clean else (0.8 if not ambiguous and all(m in ("number_and_name", "number_only") for m in methods) else 0.7)
    if last is None:
        up_name, up_num, up_country, up_iso = names_by_number.get(start), start, "United Kingdom", "GB"
    else:
        up_name, up_num, up_country, up_iso = last["name"], last["company_number"], last["country"], last["country_iso2"]
    return {
        "company_number": start,
        "company_name": names_by_number.get(start),
        "chain": json.dumps(chain, ensure_ascii=False),
        "chain_length": len(chain),
        "ultimate_parent_name": up_name,
        "ultimate_parent_company_number": up_num,
        "ultimate_parent_country": up_country,
        "ultimate_parent_country_iso2": up_iso,
        "top_uk_company_number": top_uk,
        "top_uk_company_name": names_by_number.get(top_uk),
        "stop_reason": stop,
        "ambiguous": ambiguous,
        "confidence": confidence,
    }


# --------------------------------------------------------------------------------------
# Orchestration
# --------------------------------------------------------------------------------------

def reporting_numbers() -> tuple[list[str], str]:
    import pandas as pd

    def clean(series) -> list[str]:
        s = series.dropna().astype(str).str.strip().str.upper()
        s = s[s != ""].map(lambda x: x.zfill(8))
        return sorted(set(s))

    if UK_PARQUET.exists():
        return clean(pd.read_parquet(UK_PARQUET, columns=["company_number"])["company_number"]), str(UK_PARQUET.relative_to(ROOT))
    for p in sorted(UK_RAW_DIR.glob("**/*.csv")) if UK_RAW_DIR.exists() else []:
        head = pd.read_csv(p, nrows=0)
        cands = [c for c in head.columns if re.sub(r"[^a-z]", "", c.lower()) in ("companynumber", "companyno")]
        if cands:
            return clean(pd.read_csv(p, usecols=[cands[0]], dtype=str)[cands[0]]), str(p.relative_to(ROOT))
    return [], ""


def build(workers: int = 6) -> dict:
    import pandas as pd

    files = local_files()
    manifest = _load_manifest()
    psc, line_stats, missing_parts = parse_psc(files["psc"], workers=workers)
    print(f"PSC corporate/legal-person active rows: {len(psc):,}", flush=True)
    build_basic_all(files["basic"])
    basic = pd.read_parquet(BASIC_ALL_PARQUET)
    print(f"Basic company rows: {len(basic):,}", flush=True)

    names_by_number = dict(zip(basic["company_number"], basic["company_name"]))
    # name index: only names that some unresolved-by-number PSC could need
    psc_names = {norm_name(n) for n in psc["psc_name"].dropna().unique()}
    basic_norm = basic["company_name"].map(norm_name)
    # name matching only against UK-incorporated companies (not overseas-entity / UK-establishment records)
    mask = basic_norm.isin(psc_names) & (basic["country_of_origin"].str.upper() == "UNITED KINGDOM")
    cand = pd.DataFrame({"n": basic_norm[mask], "num": basic.loc[mask, "company_number"]})
    cand = cand[cand["n"] != ""]
    uniq = cand.drop_duplicates("n", keep=False)
    number_by_name = dict(zip(uniq["n"], uniq["num"]))
    pn = basic.loc[basic["previous_names"].fillna("") != "", ["company_number", "previous_names"]]
    prev_names_by_number = {num: {norm_name(x) for x in names.split("|")} for num, names in zip(pn["company_number"], pn["previous_names"])}

    psc_by_company: dict[str, list[dict]] = {}
    for rec in psc.where(psc.notna(), None).to_dict("records"):
        psc_by_company.setdefault(rec["company_number"], []).append(rec)

    numbers, numbers_src = reporting_numbers()
    if not numbers:
        print("No reporting-entity list found yet (uk_payment_practices.parquet / data/raw/uk/*.csv). "
              "PSC + basic tables are built; rerun with --skip-download once it exists.", flush=True)
        return {"psc_rows": len(psc), "basic_rows": len(basic), "reporting": 0}

    psc_files = [v for k, v in manifest["files"].items() if k.startswith("psc-snapshot")]
    retrieved_at = max((f["retrieved_at"] for f in psc_files), default=now_iso())
    rows = []
    for n in numbers:
        r = walk_chain(n, psc_by_company, names_by_number, number_by_name, prev_names_by_number)
        r["in_companies_house_live_data"] = n in names_by_number
        rows.append(r)
    chains = pd.DataFrame(rows)
    chains["source_url"] = PSC_PAGE
    chains["source_type"] = "companies_house_psc_bulk"
    chains["retrieved_at"] = retrieved_at
    chains["snapshot_file_date"] = re.search(r"(\d{4}-\d{2}-\d{2})", manifest["snapshot"]["psc_parts"][0]).group(1)
    chains["extraction_method"] = "psc_chain_walk"
    chains["psc_parts_missing"] = len(missing_parts)
    # With PSC parts missing, a missing parent looks like "no corporate PSC". Never write that under
    # the final file name: partial results go to *.partial.* so nothing downstream picks them up.
    chains_out = CHAINS_OUT if not missing_parts else CHAINS_OUT.with_suffix(".partial.parquet")
    chains.to_parquet(chains_out, index=False)
    chains.to_csv(chains_out.with_suffix(".csv"), index=False)
    if missing_parts:
        print(f"INCOMPLETE: {len(missing_parts)} PSC parts missing. Wrote {chains_out.name} only. "
              "Finish the download (rerun without --skip-download) and rerun.", flush=True)

    wanted = set(numbers)
    for c in chains["chain"]:
        wanted.update(h["company_number"] for h in json.loads(c) if h["company_number"])
    sub = basic[basic["company_number"].isin(wanted)].copy()
    sub["is_reporting_entity"] = sub["company_number"].isin(set(numbers))
    sub["source_url"] = BASIC_PAGE
    sub["source_type"] = "companies_house_basic_bulk"
    sub["retrieved_at"] = manifest["files"].get(files["basic"].name, {}).get("retrieved_at")
    sub["snapshot_file"] = files["basic"].name
    sub.to_parquet(BASIC_OUT if not missing_parts else BASIC_OUT.with_suffix(".partial.parquet"), index=False)
    print(f"Reporting entities: {len(numbers):,} (from {numbers_src}); chains written: {len(chains):,}; "
          f"basic rows kept: {len(sub):,}", flush=True)
    return {"psc_rows": len(psc), "basic_rows": len(basic), "reporting": len(numbers), "line_stats": line_stats}


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--download-only", action="store_true")
    ap.add_argument("--skip-download", action="store_true")
    ap.add_argument("--workers", type=int, default=6)
    a = ap.parse_args(argv)
    if not a.skip_download:
        download_all()
    if a.download_only:
        return 0
    build(workers=a.workers)
    return 0


if __name__ == "__main__":
    sys.exit(main())
