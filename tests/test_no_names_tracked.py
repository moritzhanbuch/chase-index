"""No named individual from data/private may appear in any tracked text file or the built workspace,
including as a URL slug (first-last). Skipped when data/private is absent (a fresh clone)."""
import pathlib
import subprocess

import pandas as pd
import pytest

ROOT = pathlib.Path(__file__).resolve().parents[1]
PERSONAS = ROOT / "data" / "private" / "personas.csv"


@pytest.mark.skipif(not PERSONAS.exists(), reason="no local private data")
def test_no_private_names_in_tracked_or_built_files():
    names = [n for n in pd.read_csv(PERSONAS, usecols=["full_name"]).full_name.dropna().unique() if len(n) > 5]
    files = subprocess.run(["git", "ls-files"], cwd=ROOT, capture_output=True, text=True).stdout.split()
    files += [str(p.relative_to(ROOT)) for p in (ROOT / "workspace" / "dist").rglob("*") if p.is_file()]
    bad = set()
    for f in files:
        p = ROOT / f
        if not p.is_file() or p.suffix in {".parquet", ".pdf", ".png", ".jpg"} or f.startswith("data/private"):
            continue
        low = p.read_text(errors="ignore").lower()
        for n in names:
            parts = n.lower().split()
            if n.lower() in low or (len(parts) > 1 and ("-".join(parts) in low or "_".join(parts) in low)):
                bad.add(f)
    assert not bad, f"private names found in: {sorted(bad)}"   # file paths only, never the names


@pytest.mark.skipif(not (ROOT / "data" / "private" / "account_dates.csv").exists(), reason="no local private data")
def test_no_private_source_urls_in_tracked_or_built_files():
    """URLs of private sources (CFO changes, results dates, persona pages) can carry names in their slugs."""
    urls = set()
    for f, cols in (("account_dates.csv", ["cfo_change_url", "next_results_url"]), ("personas.csv", ["source_url"])):
        d = pd.read_csv(ROOT / "data" / "private" / f)
        for c in cols:
            if c in d:
                urls |= {u for u in d[c].dropna().astype(str) if u.startswith("http")}
    # public filing indexes (SEC, ESEF) are not private: only flag URLs whose path carries a name-like slug
    urls = {u for u in urls if "sec.gov" not in u and "filings.xbrl.org" not in u}
    files = subprocess.run(["git", "ls-files"], cwd=ROOT, capture_output=True, text=True).stdout.split()
    files += [str(p.relative_to(ROOT)) for p in (ROOT / "workspace" / "dist").rglob("*") if p.is_file()]
    bad = set()
    for f in files:
        p = ROOT / f
        if not p.is_file() or p.suffix in {".parquet", ".pdf", ".png", ".jpg"} or f.startswith("data/private"):
            continue
        t = p.read_text(errors="ignore")
        if any(u in t for u in urls):
            bad.add(f)
    assert not bad, f"private source URLs found in: {sorted(bad)}"
