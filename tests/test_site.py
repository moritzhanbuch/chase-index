"""Public site: build, required pages, and the legal/ethical guard rails.
Run: .venv/bin/python -m pytest tests/test_site.py -q"""
import csv
import json
import re
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
DIST = ROOT / "site" / "dist"
DISCLAIMER = "Independent project by Moritz Hanbuch."
OGL = "Contains public sector information licensed under the Open Government Licence v3.0."
REQUIRED = ["index.html", "lookup.html", "spain.html", "methodology.html", "data-dictionary.html", "limitations.html",
            "corrections.html", "about.html", "faq.html", "data.html", "sitemap.xml", "robots.txt", "llms.txt",
            "assets/style.css", "assets/site.js", "assets/lookup.js", "data/lookup-index.json",
            "data/chase-index-uk-entities.csv", "data/chase-index-groups.csv"]
# Internal sales data (rule 1). Column / key names in data files may not start with these.
FORBIDDEN_PREFIXES = ("est_", "fit_", "pain_", "signal", "priority", "rank", "rationale", "excluded", "tier", "base_tier",
                      "score", "hook", "sales", "estimate")
# Same terms as free text in data files. Case-sensitive and not preceded by a letter, so that
# "longest_standard..." (contains "est_") and upper-case legal names such as "RANK GROUP" do not trip it.
FORBIDDEN_TEXT = re.compile(r"(?<![A-Za-z])(est_|fit_|pain_|signal|priority|rank|rationale|excluded|tier_|_tier|_score|score_|hook)")
# Internal field names must not appear in any HTML either.
INTERNAL_FIELDS = re.compile(r"fit_score|pain_score|signal_score|priority_tier|priority_score|base_tier|est_group|est_uk|"
                             r"excluded_reason|rationale|pain_evidence|one-pager|target list|dinner", re.I)
ACCUSATORY = re.compile(r"\b(worst|offenders?|abuses?|abusive|scams?|shame[ds]?|shaming|culprits?|blacklist(ed)?|guilty)\b", re.I)
EXTERNAL_INCLUDE = re.compile(
    r"<script[^>]+src=[\"']?(https?:)?//|<link[^>]+rel=[\"']?(stylesheet|preload|preconnect|dns-prefetch|icon)[^>]*href=[\"']?(https?:)?//"
    r"|<link[^>]+href=[\"']?(https?:)?//[^>]+rel=[\"']?(stylesheet|preload|preconnect|dns-prefetch|icon)"
    r"|<(img|iframe|video|audio|source|embed|object)[^>]+(src|data)=[\"']?(https?:)?//|@import|url\(\s*[\"']?(https?:)?//", re.I)


@pytest.fixture(scope="session")
def dist():
    r = subprocess.run([sys.executable, str(ROOT / "site" / "build.py")], capture_output=True, text=True, cwd=ROOT)
    assert r.returncode == 0, r.stderr[-2000:]
    assert "Built" in r.stdout
    return DIST


@pytest.fixture(scope="session")
def html_pages(dist):
    pages = sorted(dist.rglob("*.html"))
    assert len(pages) > 50
    return [(p, p.read_text(encoding="utf-8")) for p in pages]


def data_files(dist):
    return [p for p in dist.rglob("*") if p.is_file() and p.suffix in {".json", ".csv", ".txt", ".xml"}]


def test_required_pages_exist(dist):
    missing = [p for p in REQUIRED if not (dist / p).exists()]
    assert not missing, missing
    assert len(list((dist / "company").glob("*.html"))) > 50


def test_disclaimer_on_every_page(html_pages):
    bad = [str(p) for p, t in html_pages if DISCLAIMER not in t]
    assert not bad, bad[:5]


def test_no_internal_sales_data_in_data_files(dist):
    for p in data_files(dist):
        text = p.read_text(encoding="utf-8")
        hits = sorted({m.group(0) for m in FORBIDDEN_TEXT.finditer(text)})
        assert not hits, f"{p.name}: {hits[:10]}"
    for p in dist.rglob("*.csv"):
        with p.open(encoding="utf-8") as f:
            header = next(csv.reader(f))
        bad = [c for c in header if c.lower().startswith(FORBIDDEN_PREFIXES)]
        assert not bad, f"{p.name}: {bad}"
    idx = json.loads((dist / "data" / "lookup-index.json").read_text(encoding="utf-8"))
    assert not [c for c in idx["cols"] if c.lower().startswith(FORBIDDEN_PREFIXES)]
    assert set(idx) == {"about", "report_base", "cols", "groups", "rows"}
    assert all(len(r) == len(idx["cols"]) for r in idx["rows"])


def test_no_internal_fields_in_html(html_pages):
    bad = [(str(p.relative_to(DIST)), m.group(0)) for p, t in html_pages for m in [INTERNAL_FIELDS.search(t)] if m]
    assert not bad, bad[:5]


def test_neutral_language(html_pages):
    bad = [(str(p.relative_to(DIST)), m.group(0)) for p, t in html_pages for m in [ACCUSATORY.search(t)] if m]
    assert not bad, bad[:5]


def test_no_em_dash(html_pages, dist):
    bad = [str(p) for p, t in html_pages if "—" in t or "&mdash;" in t or "&#8212;" in t]
    assert not bad, bad[:5]
    assert "—" not in (dist / "llms.txt").read_text(encoding="utf-8")


def test_no_external_includes(html_pages, dist):
    bad = [(str(p.relative_to(DIST)), m.group(0)) for p, t in html_pages for m in [EXTERNAL_INCLUDE.search(t)] if m]
    assert not bad, bad[:5]
    for p in (dist / "assets").iterdir():
        t = p.read_text(encoding="utf-8")
        assert not re.search(r"@import|url\(\s*[\"']?(https?:)?//|https?://", t), p.name


def test_required_notes_and_markup(dist):
    home = (dist / "index.html").read_text(encoding="utf-8")
    assert '"@type": "Dataset"' in home and '"@type": "Person"' in home
    assert "UK legal entities only, matched to the group. Not a statement about the group's global payment behaviour." in home.replace("&#39;", "'")
    assert "computed DPO (proxy)" in home.lower() or "Computed DPO (proxy)" in home
    faq = (dist / "faq.html").read_text(encoding="utf-8")
    assert '"@type": "FAQPage"' in faq
    assert "Built independently as a portfolio project. Not affiliated with any company it mentions." in faq
    assert "Covers the group's Spanish entities as disclosed under Ley 15/2010." in (dist / "spain.html").read_text(encoding="utf-8").replace("&#39;", "'")
    assert OGL in (dist / "lookup.html").read_text(encoding="utf-8")
    for p in dist.rglob("*.html"):
        assert '"@type": "Organization"' not in p.read_text(encoding="utf-8")
    robots = (dist / "robots.txt").read_text()
    for ua in ("GPTBot", "ClaudeBot", "PerplexityBot", "Google-Extended"):
        assert f"User-agent: {ua}\nAllow: /" in robots


def test_headline_numbers_come_from_data(dist):
    import pandas as pd
    e = pd.read_parquet(ROOT / "data" / "processed" / "uk_entity_latest.parquet")
    cur = e[e.has_usable_report.fillna(False).astype(bool) & ~e.latest_is_stale.fillna(True).astype(bool)]
    s = json.loads((dist / "build-summary.json").read_text())["headline"]
    assert s["uk_current_n"] == len(cur)
    assert s["uk_median_days"] == pytest.approx(cur.avg_days_to_pay.median(), abs=0.01)
    assert s["uk_share_over_60"] == pytest.approx(100 * (cur.avg_days_to_pay.dropna() > 60).mean(), abs=0.01)
    home = (dist / "index.html").read_text(encoding="utf-8")
    assert f"{len(cur):,}" in home


def test_lookup_index_small_and_consistent(dist):
    import pandas as pd
    p = dist / "data" / "lookup-index.json"
    assert p.stat().st_size < 1_500_000
    idx = json.loads(p.read_text(encoding="utf-8"))
    e = pd.read_parquet(ROOT / "data" / "processed" / "uk_entity_latest.parquet").set_index("company_number")
    for r in idx["rows"][::400]:
        src = e.loc[r[1]]
        assert r[2] == pytest.approx(src.avg_days_to_pay)
        assert src.source_url == idx["report_base"] + str(r[14])


def test_relative_links_resolve(html_pages):
    for p, t in html_pages[:40] + [x for x in html_pages if x[0].parent == DIST]:
        for href in re.findall(r'(?:href|src)="([^"#?:]+)(?:[#?][^"]*)?"', t):
            assert (p.parent / href).resolve().exists(), f"{p.name}: {href}"


def test_release_check_fails_on_placeholders(dist, tmp_path):
    sys.path.insert(0, str(ROOT / "site"))
    import build as site_build
    problems = site_build.release_problems(dist)
    assert problems, "placeholder URL/contact should be flagged until real values are set"
    (tmp_path / "ok.html").write_text("<p>for example, a real page at https://chase-index.test/</p>", encoding="utf-8")
    assert site_build.release_problems(tmp_path) == []
    (tmp_path / "bad.txt").write_text("write to mo@example.com", encoding="utf-8")
    assert len(site_build.release_problems(tmp_path)) == 1
    r = subprocess.run([sys.executable, str(ROOT / "site" / "build.py"), "--release"], capture_output=True, text=True, cwd=ROOT)
    assert r.returncode != 0 and "RELEASE CHECK FAILED" in r.stdout


def test_group_average_described_as_weighted(dist):
    import pandas as pd
    c = pd.read_parquet(ROOT / "data" / "processed" / "companies.parquet")
    w = c[(c.uk_days_aggregation == "invoice_value_weighted_mean") & (c.uk_entities_n > 1) & ~c.not_a_company.fillna(False).astype(bool)].iloc[0]
    page = (dist / "company" / f"{w.company_id}.html").read_text(encoding="utf-8")
    assert "weighted by the invoice value each one reports. Simple mean:" in page
    assert "Figures describe each legal entity in its stated reporting period, whoever owned it then." in page
    home = (dist / "index.html").read_text(encoding="utf-8")
    assert "Avg days to pay (UK, value-weighted)" in home
    for f in ("llms.txt", "limitations.html", "data-dictionary.html"):
        t = (dist / f).read_text(encoding="utf-8")
        assert "weighted by" in t, f
        assert "simple means across" not in t and "is the simple mean across" not in t, f
    with (dist / "data" / "chase-index-groups.csv").open(encoding="utf-8") as fh:
        header = next(csv.reader(fh))
    assert {"uk_avg_days_to_pay_mean", "uk_avg_days_to_pay_simple_mean", "uk_days_aggregation"} <= set(header)


def test_home_table_default_sort_is_alphabetical(dist):
    home = (dist / "index.html").read_text(encoding="utf-8")
    names = re.findall(r'<tr data-name="([^"]*)"', home)
    assert len(names) > 50
    import html as _h
    names = [_h.unescape(n) for n in names]
    assert names == sorted(names)
    assert re.search(r'<th data-col="0" aria-sort="ascending">', home)
    assert 'aria-sort="descending"' not in home
    assert "Sorting is for navigation." in home


def test_computed_dpo_wording(html_pages):
    assert not [str(p) for p, t in html_pages if "passed the plausibility checks" in t]


def test_no_en_dash(html_pages):
    assert not [str(p) for p, t in html_pages if "\u2013" in t or "&ndash;" in t]


def test_extreme_entities_marked_and_trend_wording(dist):
    import pandas as pd
    c = pd.read_parquet(ROOT / "data" / "processed" / "companies.parquet")
    c = c[c.uk_entities_n.notna() & ~c.not_a_company.fillna(False).astype(bool)]
    if "uk_entities_excluded_extreme" in c.columns:
        for r in c[c.uk_entities_excluded_extreme.notna()].itertuples():
            page = (dist / "company" / f"{r.company_id}.html").read_text(encoding="utf-8")
            assert "are left out of the group figure until verified:" in page, r.company_id
            assert page.count("not in the group figure") == len(r.uk_entities_excluded_extreme.split("|")), r.company_id
    multi = c[(c.uk_trend_entities_n > 1) & (c.uk_entities_n > 1)].iloc[0]
    page = (dist / "company" / f"{multi.company_id}.html").read_text(encoding="utf-8")
    assert "median change in days to pay against one year earlier" in page
    assert f"{int(multi.uk_trend_entities_slower_n)} of {int(multi.uk_trend_entities_n)} entities with a comparison got slower" in page
    with (dist / "data" / "chase-index-groups.csv").open(encoding="utf-8") as fh:
        header = next(csv.reader(fh))
    assert "uk_change_in_days_year_on_year_median" in header and "uk_change_in_days_year_on_year_mean" not in header
    for banned in ("thin_evidence", "uk_invoice_value_share_of_group_revenue"):
        for p in dist.rglob("*"):
            if p.is_file() and p.suffix in {".html", ".csv", ".json", ".txt"}:
                assert banned not in p.read_text(encoding="utf-8", errors="replace"), (banned, p.name)
