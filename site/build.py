"""Build the public Chase Index site into site/dist.

Run: .venv/bin/python site/build.py   (or: make site)

Rules this build enforces (see tests/test_site.py):
- Reads data/processed at build time. No number in the site copy is written by hand.
- Ships ONLY reported figures (UK, Spain) and computed DPO (proxy). Internal sales columns
  (scores, tiers, estimates, rationales, signals) never reach site/dist: public columns are an allow-list.
- Company-level data only, neutral wording, disclaimer on every page, no external requests.
- Local build only. Nothing here deploys or contacts anything.
"""
from __future__ import annotations

import html as _html
import json
import os
import math
import re
import shutil
import sys
from pathlib import Path

import markdown as md
import pandas as pd
from jinja2 import Environment, FileSystemLoader, select_autoescape
from markupsafe import Markup

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from chase import query as q  # noqa: E402  (shared query layer: single source of read logic)

# ----------------------------------------------------------------------------- constants
# Placeholders by default. Set CHASE_SITE_URL, CHASE_CONTACT_EMAIL and CHASE_IMPRINT_ADDRESS for a real release.
# `python site/build.py --release` fails while any placeholder is left in site/dist.
SITE_URL = os.environ.get("CHASE_SITE_URL", "https://example.org/chase-index/").rstrip("/") + "/"
SITE_NAME = "The Chase Index"
CONTACT = os.environ.get("CHASE_CONTACT_EMAIL", "mo@example.com")
IMPRINT_PLACEHOLDER = "[postal address to be added before publication]"
IMPRINT_ADDRESS = os.environ.get("CHASE_IMPRINT_ADDRESS", IMPRINT_PLACEHOLDER)
RELEASE_PLACEHOLDERS = ("example.org", "example.com", IMPRINT_PLACEHOLDER)
CH_ATTRIBUTION = "Contains public sector information from Companies House"
DISCLOSURE = "Disclosure: the author built this index as part of a job application to an agent-to-agent B2B payments startup."
SMALL_BASE_N = 3            # groups resting on fewer UK entities than this get a chip in the home table
MIN_SECTOR_CONFIDENCE = 0.7
DISCLAIMER = q.DISCLAIMER
OGL = "Contains public sector information licensed under the Open Government Licence v3.0."
LICENCE_NAME = "Creative Commons Attribution 4.0 (CC BY 4.0)"
LICENCE_URL = "https://creativecommons.org/licenses/by/4.0/"
PROXY_PAGE_CAP = 300        # company pages for the N largest groups (by revenue) that only have a usable DPO
SECTOR_MIN_REPORTS = 30     # official sector medians based on fewer reports are left out of the chart
HIST_BIN, HIST_MAX = 5, 120
UK_REPORT_BASE = "https://check-payment-practices.service.gov.uk/report/"
UK_SEARCH_URL = "https://www.gov.uk/check-when-businesses-pay-invoices"

SRC = ROOT / "site" / "src"
DIST = ROOT / "site" / "dist"
P = ROOT / "data" / "processed"
DOCS = ROOT / "docs"

NAV = [("index.html", "Index"), ("lookup.html", "Supplier lookup"), ("spain.html", "Spain"),
       ("methodology.html", "Methodology"), ("faq.html", "FAQ"), ("data.html", "Data"), ("about.html", "About")]

# Internal sales data must never ship. Prefix/keyword list from the project rules.
FORBIDDEN_PREFIXES = ("est_", "fit_", "pain_", "signal", "priority", "rank", "rationale", "excluded",
                      "tier", "base_tier", "score", "hook", "sales", "estimate")
INTERNAL_HEADING = re.compile(r"scor|estimate|target|priorit|calibration|tier|signal|outreach|one-pager", re.I)
INTERNAL_SENTENCE = re.compile(r"\b(scor(e|es|ed|ing)|estimates?|tiers?|target list|one-pagers?|rationales?|assumptions\.yaml|"
                               r"calibrat\w+|outreach|signals?|dinner)\b|`(est_|fit_|pain_|priority|rank|excluded)", re.I)
# The methodology intro counts the kinds of numbers. When the internal row is removed, the count has to follow.
PUBLIC_DOC_REPLACEMENTS = [("Three kinds of numbers, never mixed:", "Two kinds of numbers, never mixed:")]
GROUP_FIGURE_SENTENCE = ("Group figures are averages across matched UK entities, weighted by the invoice value each entity "
                         "reports paying. The simple mean is published alongside. "
                         "The change against one year earlier is shown as the median across entities, with the number of entities that got slower. "
                         "Entities that report extreme values (an average of 200 days or more, or a change of 100 days or more in a year) "
                         "are left out of group figures until verified. Their own reports stay visible.")
# Applied to every public doc: correct descriptions and remove repository paths an outside reader cannot follow.
PUBLIC_DOC_ALWAYS = [
    (r"A group figure here is the simple mean across the UK entities we could match to that group\.", GROUP_FIGURE_SENTENCE),
    (r"\s*\(`(?:evals|docs|data|config)/[^`]+`\)", ""),
    (r"\s*(?<![A-Za-z])[A-Z][^.`\n]*`(?:evals|data|config)/[^`]+`\.", ""),
    (r"`data/interim/review_queue\.csv`", "a review queue"),
    (r"`docs/limitations\.md`", "[the limitations page](limitations.html)"),
]

COUNTRY = {"US": "United States", "GB": "United Kingdom", "DE": "Germany", "FR": "France", "ES": "Spain", "CN": "China",
           "RU": "Russia", "CA": "Canada", "NL": "Netherlands", "DK": "Denmark", "JP": "Japan", "IT": "Italy",
           "CH": "Switzerland", "IE": "Ireland", "BR": "Brazil", "SE": "Sweden", "NO": "Norway", "FI": "Finland",
           "BE": "Belgium", "AT": "Austria", "LU": "Luxembourg", "PT": "Portugal", "IN": "India", "KR": "South Korea",
           "AU": "Australia", "MX": "Mexico", "TW": "Taiwan", "HK": "Hong Kong", "SG": "Singapore", "IL": "Israel",
           "ZA": "South Africa", "TR": "Turkey", "PL": "Poland", "GR": "Greece", "SA": "Saudi Arabia", "BM": "Bermuda",
           "AR": "Argentina", "CL": "Chile", "CO": "Colombia", "TH": "Thailand", "ID": "Indonesia", "MY": "Malaysia",
           "AE": "United Arab Emirates", "CZ": "Czechia", "HU": "Hungary", "RO": "Romania", "KY": "Cayman Islands",
           "JE": "Jersey", "GG": "Guernsey", "PH": "Philippines", "VN": "Vietnam", "NZ": "New Zealand", "IS": "Iceland"}
MATCH = {"wikidata_company_number": "company number on Wikidata", "ch_psc_chain": "Companies House ownership chain",
         "exact_name": "exact name", "wikidata_subsidiary_name": "subsidiary listed on Wikidata",
         "brand_prefix": "brand name in the entity name"}
PAYABLES = {"trade": "trade payables", "trade_and_other_broad": "trade and other payables (a broader line)"}
COSTS = {"cost_of_sales": "cost of sales", "operating_expenses_fallback": "operating expenses (cost of sales not tagged)",
         "by_nature_fallback": "costs by nature (cost of sales not tagged)"}
ES_SCOPE = {"consolidated_spanish_entities": "Group, Spanish entities", "parent_only": "Parent company only",
            "unknown": "Not stated in the note"}
ES_FLAG = {"pct_within_limit_measured_against_45_days_not_60":
               "The share paid within the limit is measured against 45 days in this filing, not 60.",
           "pmp_outside_its_own_ratios_as_printed":
               "As printed, the PMP lies outside its own paid and pending ratios. Shown as printed, not corrected."}
ES_MISSING = {"FER": "Non-Spanish issuer (registered in the Netherlands). The filing has no PMP note.",
              "MTS": "Non-Spanish issuer (registered in Luxembourg). The filing has no PMP note.",
              "SAB": "The PMP table is not in the tagged text of the ESEF filing, so it could not be read reliably."}


# ----------------------------------------------------------------------------- helpers
def nn(v):
    """None for missing values, plain Python types otherwise."""
    if v is None or v is pd.NA:
        return None
    if isinstance(v, float) and math.isnan(v):
        return None
    if hasattr(v, "item"):
        try:
            v = v.item()
        except (ValueError, AttributeError):
            pass
    if isinstance(v, float) and math.isnan(v):
        return None
    return v


def d1(v) -> str:
    v = nn(v)
    if v is None:
        return ""
    if isinstance(v, str):
        return v
    s = f"{float(v):.1f}"
    return s[:-2] if s.endswith(".0") else s


def pct(v) -> str:
    s = d1(v)
    return s + "%" if s else ""


def raw(v) -> str:
    v = nn(v)
    return "" if v is None else str(round(float(v), 2))


def int_c(v) -> str:
    v = nn(v)
    return "" if v is None else f"{int(v):,}"


def signed(v) -> str:
    v = nn(v)
    if v is None:
        return "n/a"
    s = d1(abs(v))
    return ("+" if v > 0 else "-" if v < 0 else "") + s + " days"


def dmy(v) -> str:
    v = nn(v)
    if v is None:
        return ""
    t = pd.Timestamp(str(v)[:10])
    return f"{t.day} {t.strftime('%b %Y')}"


def sector_name(s) -> str:
    s = nn(s)
    return "" if not s else str(s).replace("_", " ").capitalize()


def money(v, cur) -> str:
    v = nn(v)
    if v is None:
        return ""
    if v >= 1e9:
        return f"{nn(cur) or ''} {v / 1e9:.1f} billion".strip()
    return f"{nn(cur) or ''} {v / 1e6:.0f} million".strip()


def jsonld(obj) -> str:
    return json.dumps(obj, ensure_ascii=False, indent=1).replace("</", "<\\/")


def public_md(text: str) -> str:
    """Remove internal (sales) material from a markdown doc before it is rendered publicly.
    1. Anything between <!-- internal:start --> and <!-- internal:end --> markers.
    2. Whole sections whose heading names scores, estimates, targets and the like.
    3. Table rows that mention internal material, and single sentences that do."""
    text = re.sub(r"<!--\s*internal:start\s*-->.*?<!--\s*internal:end\s*-->", "", text, flags=re.S)
    out, skip_level, dropped_row = [], None, False
    for line in text.splitlines():
        m = re.match(r"^(#{1,6})\s+(.*)$", line)
        if m:
            level = len(m.group(1))
            if skip_level is not None and level <= skip_level:
                skip_level = None
            if skip_level is None and level > 1 and INTERNAL_HEADING.search(m.group(2)):
                skip_level = level
        if skip_level is not None:
            continue
        if m or not INTERNAL_SENTENCE.search(line):
            out.append(line)
            continue
        if line.lstrip().startswith("|"):
            dropped_row = True
            continue
        lead = re.match(r"^\s*(?:[-*]|\d+\.)\s+", line)
        body = line[lead.end():] if lead else line
        kept = [s for s in re.split(r"(?<=[.!?])\s+", body) if not INTERNAL_SENTENCE.search(s)]
        if kept:
            out.append((lead.group(0) if lead else "") + " ".join(kept))
    text = "\n".join(out)
    for a, b in PUBLIC_DOC_ALWAYS:
        text = re.sub(a, b, text)
    if dropped_row:
        for a, b in PUBLIC_DOC_REPLACEMENTS:
            text = text.replace(a, b)
    return text


def md_html(text: str) -> str:
    h = md.markdown(text, extensions=["tables", "fenced_code", "sane_lists"])
    h = h.replace("<table>", '<div class="table-wrap"><table>').replace("</table>", "</table></div>")
    return re.sub(r'<a href="(https?://[^"]+)"', r'<a rel="noopener" href="\1"', h)


def strip_tags(h: str) -> str:
    return re.sub(r"\s+", " ", _html.unescape(re.sub(r"<[^>]+>", " ", h))).strip()


# ----------------------------------------------------------------------------- data
def load():
    comp = q.companies().copy()
    ents = q.uk_entities().copy()
    for c in ("has_usable_report", "latest_is_stale"):
        ents[c] = ents[c].astype("boolean")
    ents["usable"] = ents.has_usable_report.fillna(False).astype(bool)
    ents["current"] = ents.usable & ~ents.latest_is_stale.fillna(True).astype(bool)
    es = pd.read_parquet(P / "es_pmp.parquet")
    bench = pd.read_csv(P / "uk_official_benchmarks.csv")
    return comp, ents, es, bench


def bench_headline(bench):
    hl = bench[bench.breakdown_type == "headline"]
    days = hl[hl.metric == "Time to pay (days)"].set_index("reporting_year").value.sort_index()
    late = hl[hl.metric.str.startswith("Proportion of invoices paid late, by number")].set_index("reporting_year").value.sort_index()
    return days, late


def headline(comp, ents, es, bench, groups):
    cur = ents[ents.current]
    days = cur.avg_days_to_pay.dropna()
    tr = cur.trend_days_yoy.dropna()
    b_days, b_late = bench_headline(bench)
    es_ok = es[(es.status == "ok") & es.pmp_days.notna()]
    rep = [g for g in groups if g["reported"]]
    return {
        "uk_current_n": len(cur),
        "uk_median_days": float(days.median()),
        "uk_n_over_60": int((days > 60).sum()),
        "uk_share_over_60": 100 * float((days > 60).mean()),
        "uk_share_over_30": 100 * float((days > 30).mean()),
        "uk_trend_n": len(tr),
        "uk_share_longer": 100 * float((tr > 0).mean()),
        "uk_share_shorter": 100 * float((tr < 0).mean()),
        "uk_share_same": 100 * float((tr == 0).mean()),
        "uk_share_small_change": 100 * float((tr.abs() <= 1).mean()),
        "uk_median_late": float(cur.pct_paid_late.dropna().median()),
        "uk_period_min": cur.period_end.astype(str).min(),
        "uk_period_max": cur.period_end.astype(str).max(),
        "uk_period_start_min": cur.period_start.astype(str).min(),
        "official_year": int(b_days.index.max()),
        "official_median_days": float(b_days.iloc[-1]),
        "official_median_late": float(b_late.iloc[-1]),
        "es_n": len(es_ok),
        "es_over_60_n": int((es_ok.pmp_days > 60).sum()),
        "es_median": float(es_ok.pmp_days.median()),
        "es_fy": int(es_ok.fiscal_year.max()),
        "lookup_n": int(ents.usable.sum()),
        "groups_reported_n": len(rep),
        "groups_uk_n": sum(1 for g in rep if g["uk_n"] is not None),
        "groups_es_n": sum(1 for g in rep if g["es_pmp"] is not None),
        "groups_proxy_only_n": len(groups) - len(rep),
        "proxy_page_cap": PROXY_PAGE_CAP,
    }


def group_rows(comp):
    """Groups that get a row in the home table and a company page.
    Rule: every group with reported UK or Spanish data, plus the PROXY_PAGE_CAP largest other groups
    by revenue with a usable computed DPO. Entries flagged as not a company are left out."""
    c = comp[~comp.not_a_company.fillna(False).astype(bool)].copy()
    reported = c.uk_entities_n.notna() | c.es_pmp_days.notna()
    clean = (c.dpo_flag == "ok") & c.dpo.notna() & (c.dpo_payables_basis == "trade") & (c.dpo_cost_basis == "cost_of_sales")
    proxy_only = c[~reported & clean].sort_values("revenue_usd", ascending=False).head(PROXY_PAGE_CAP)
    sel = pd.concat([c[reported], proxy_only])
    rows = []
    for r in sel.itertuples():
        dpo_ok = dpo_is_clean(r)     # home table: clean rows only (trade payables and cost of sales, flag ok)
        cname = COUNTRY.get(nn(r.country), nn(r.country) or "")
        filed = nn(getattr(r, "country_method", None)) == "esef_filing_country" and bool(cname)
        uk_n = nn(r.uk_entities_n)
        rows.append({
            "id": r.company_id, "name": r.name, "country": nn(r.country) or "",
            "country_plain": cname, "country_name": f"Filed in {cname}" if filed else cname,
            "weighted": nn(getattr(r, "uk_days_aggregation", None)) == "invoice_value_weighted_mean",
            "small_base": uk_n is not None and uk_n < SMALL_BASE_N,
            "uk_chip": "" if uk_n is None or uk_n >= SMALL_BASE_N else ("1 entity" if uk_n == 1 else f"{int(uk_n)} entities"),
            "uk_period_end": nn(r.uk_period_end_max),
            "uk_period_end_sort": str(nn(r.uk_period_end_max) or "").replace("-", "")[:8],
            "sector": nn(r.sector) or "", "sector_name": sector_name(r.sector),
            "reported": nn(r.uk_entities_n) is not None or nn(r.es_pmp_days) is not None,
            "uk_n": nn(r.uk_entities_n), "uk_days": nn(r.uk_avg_days_to_pay_mean), "uk_late": nn(r.uk_pct_paid_late_mean),
            "uk_over60": nn(r.uk_pct_paid_over_60_mean), "es_pmp": nn(r.es_pmp_days),
            "dpo": nn(r.dpo) if dpo_ok else None, "dpo_text": d1(r.dpo) if dpo_ok else "",
            "dpo_fy": nn(r.dpo_fiscal_year) if dpo_ok else None,
        })
    rows.sort(key=lambda g: g["name"].lower())    # alphabetical by default: the table is for navigation, not a ranking
    return rows


def dpo_is_clean(r) -> bool:
    return (nn(r.dpo_flag) == "ok" and nn(r.dpo) is not None and nn(r.dpo_payables_basis) == "trade"
            and nn(r.dpo_cost_basis) == "cost_of_sales")


def histogram(ents, h):
    days = ents[ents.current].avg_days_to_pay.dropna()
    bins, total = [], len(days)
    for lo in range(0, HIST_MAX, HIST_BIN):
        n = int(((days >= lo) & (days < lo + HIST_BIN)).sum())
        bins.append({"label": f"{lo} to {lo + HIST_BIN - 1} days", "n": n})
    bins.append({"label": f"{HIST_MAX} days or more", "n": int((days >= HIST_MAX).sum())})
    mx = max(b["n"] for b in bins) or 1
    for b in bins:
        b["h"] = round(100 * b["n"] / mx, 2)
        b["share"] = 100 * b["n"] / total
    span = HIST_MAX + HIST_BIN
    ticks = [{"label": str(v), "pct": round(100 * v / span, 2), "end": False} for v in range(0, HIST_MAX, 30)]
    ticks.append({"label": f"{HIST_MAX}+", "pct": 100, "end": True})
    return {"bins": bins, "ticks": ticks, "marker_pct": round(100 * (h["official_median_days"] + 0.5) / span, 2)}


def sector_chart(bench):
    year = int(bench[bench.breakdown_type == "sic_section"].reporting_year.max())
    s = bench[(bench.breakdown_type == "sic_section") & (bench.reporting_year == year)]
    late = s[s.metric.str.startswith("Proportion of invoices paid late, by number")].set_index("breakdown").value
    n = s[s.metric.str.startswith("Number of valid reports")].set_index("breakdown").value
    rows = []
    for name, v in late.items():
        cnt = nn(n.get(name))
        if name == "Unknown" or cnt is None or cnt < SECTOR_MIN_REPORTS or nn(v) is None:
            continue
        full = re.sub(r"^[A-Z]\s*-\s*", "", name)
        rows.append({"full": full, "label": full.split(";")[0].split(",")[0], "v": float(v), "n": cnt})
    rows.sort(key=lambda r: -r["v"])
    mx = max(r["v"] for r in rows) or 1
    for r in rows:
        r["w"] = round(78 * r["v"] / mx, 1)
    return {"year": year, "rows": rows, "min_n": SECTOR_MIN_REPORTS, "source": bench.source_page.iloc[0]}


def trend_chart(bench):
    days, late = bench_headline(bench)
    ymin, ymax = math.floor(days.min()) - 2, math.ceil(days.max()) + 1
    pts = []
    for i, (yr, v) in enumerate(days.items()):
        x = round(100 * i / max(1, len(days) - 1), 2)
        y = round(100 * (ymax - v) / (ymax - ymin), 2)
        pts.append({"year": int(yr), "v": float(v), "x": x, "y": y, "late": nn(late.get(yr))})
    return {"points": pts, "polyline": " ".join(f"{p['x']},{p['y']}" for p in pts), "ymin": ymin,
            "delta": abs(float(days.iloc[-1] - days.iloc[0])), "span": int(days.index.max() - days.index.min()),
            "source": bench.source_page.iloc[0]}


# ----------------------------------------------------------------------------- public data files
ENTITY_COLS = [  # (output column, source column, description)
    ("company_number", "company_number", "Companies House number of the UK legal entity that filed the report."),
    ("company_name", "company_name", "Legal entity name as filed."),
    ("period_start", "period_start", "First day of the reporting period of the latest usable report."),
    ("period_end", "period_end", "Last day of that reporting period."),
    ("filing_date", "filing_date", "Date the report was filed with the official service."),
    ("avg_days_to_pay", "avg_days_to_pay", "Average number of days taken to pay invoices, as reported."),
    ("pct_paid_within_30", "pct_paid_within_30", "Share of invoices paid within 30 days, percent, as reported."),
    ("pct_paid_31_60", "pct_paid_31_60", "Share of invoices paid in 31 to 60 days, percent, as reported."),
    ("pct_paid_over_60", "pct_paid_over_60", "Share of invoices paid after more than 60 days, percent, as reported."),
    ("pct_paid_late", "pct_paid_late", "Share of invoices not paid within agreed terms, percent, as reported."),
    ("shortest_standard_payment_period_days", "shortest_standard_payment_period_days", "Shortest standard payment period, days, as reported."),
    ("longest_standard_payment_period_days", "longest_standard_payment_period_days", "Longest standard payment period, days, as reported. Empty when not stated."),
    ("max_contractual_payment_period_days", "max_contractual_payment_period_days", "Maximum contractual payment period, days, as reported."),
    ("change_in_days_year_on_year", "trend_days_yoy", "Average days to pay in this report minus the report about one year earlier. Positive means slower."),
    ("offers_supply_chain_finance", "offers_supply_chain_finance", "Whether the entity says it offers supply chain finance, as reported."),
    ("offers_einvoicing", "offers_einvoicing", "Whether the entity says it offers e-invoicing, as reported."),
    ("participates_in_payment_codes", "participates_in_payment_codes", "Whether the entity says it is a member of a payment code, as reported."),
    ("is_current", "current", "True when the latest usable report is recent (not marked stale, see methodology)."),
    ("quality_flag", "quality_flag", "ok, or a note on the report's internal consistency, for example a late share that does not fit the payment bands."),
    ("group_company_id", "company_id", "Identifier of the parent group in this index, where the entity was matched with confidence."),
    ("group_name", "group_name", "Name of that parent group."),
    ("group_match_method", "match_method", "How the entity was linked to the group."),
    ("group_match_confidence", "match_confidence", "Confidence of that link, 0 to 1."),
    ("source_url", "source_url", "Official report page on the UK government service."),
    ("retrieved_at", "retrieved_at", "When the official data was retrieved (UTC)."),
]
GROUP_COLS = [
    ("company_id", "company_id", "Stable identifier of the group in this index."),
    ("name", "name", "Group name."),
    ("country", "country", "Headquarters country, ISO 3166 two-letter code. See country_method."),
    ("country_method", "country_method", "Where the country comes from. `esef_filing_country` means the country the annual report was filed in, which is not always the headquarters."),
    ("hq_city", "hq_city", "Headquarters city, where known."),
    ("sector", "sector", "Coarse sector classification made for this index. Some will be wrong."),
    ("sector_confidence", "sector_confidence", "Confidence of the sector classification, 0 to 1."),
    ("is_subsidiary_or_unit", "is_subsidiary_or_unit", "True when the entry is a unit of a larger group."),
    ("revenue", "revenue", "Latest known annual revenue, in revenue_currency."),
    ("revenue_currency", "revenue_currency", "Currency of the revenue figure."),
    ("revenue_period_end", "revenue_period_end", "End of the period the revenue figure covers."),
    ("revenue_source_url", "revenue_source_url", "Source of the revenue figure."),
    ("uk_entities_n", "uk_entities_n", "Reported (UK). Number of matched UK legal entities with a current usable report that are counted in the group figures."),
    ("uk_avg_days_to_pay_mean", "uk_avg_days_to_pay_mean", "Reported (UK). Mean of the entities' average reported days to pay, weighted by reported invoice value where available (see `uk_days_aggregation`). UK legal entities only."),
    ("uk_avg_days_to_pay_simple_mean", "uk_avg_days_to_pay_simple_mean", "Reported (UK). Unweighted mean of the entities' average reported days to pay."),
    ("uk_days_aggregation", "uk_days_aggregation", "How the UK group figures are averaged: `invoice_value_weighted_mean` when every matched entity reports the invoice value it paid, otherwise `simple_mean`."),
    ("uk_pct_paid_late_mean", "uk_pct_paid_late_mean", "Reported (UK). Mean share of invoices not paid within agreed terms, percent. Weighted the same way as the days figure. Reports whose late share does not fit their payment bands are left out."),
    ("uk_pct_paid_over_60_mean", "uk_pct_paid_over_60_mean", "Reported (UK). Mean share of invoices paid after more than 60 days, percent. Weighted the same way as the days figure."),
    ("uk_pct_paid_within_30_mean", "uk_pct_paid_within_30_mean", "Reported (UK). Mean share of invoices paid within 30 days, percent. Weighted the same way as the days figure."),
    ("uk_change_in_days_year_on_year_median", "uk_trend_days_yoy_median", "Reported (UK). Median change in average days to pay against one year earlier, across the entities that have a comparison. Positive means slower. This is the figure shown on company pages."),
    ("uk_change_in_days_year_on_year_weighted_mean", "uk_trend_days_yoy_weighted", "Reported (UK). The same change as a mean weighted by the invoice value each entity reports paying."),
    ("uk_change_in_days_year_on_year_simple_mean", "uk_trend_days_yoy_simple_mean", "Reported (UK). The same change as an unweighted mean."),
    ("uk_change_entities_slower_n", "uk_trend_entities_slower_n", "Reported (UK). Number of entities whose average days to pay is longer than one year earlier."),
    ("uk_change_entities_n", "uk_trend_entities_n", "Reported (UK). Number of entities with a year-earlier report behind those changes."),
    ("uk_entities_left_out_extreme_values", "uk_entities_excluded_extreme", "Reported (UK). Matched entities left out of the group figures until verified because they report extreme values (an average of 200 days or more, or a year-on-year change of 100 days or more). Their own reports stay in the entity file."),
    ("uk_longest_reported_entity_name", "uk_worst_entity_name", "Reported (UK). The matched entity with the longest average reported days to pay."),
    ("uk_longest_reported_entity_days", "uk_worst_entity_days", "Reported (UK). That entity's average reported days to pay."),
    ("uk_longest_reported_entity_source_url", "uk_worst_entity_source_url", "Official report page for that entity."),
    ("uk_period_start_min", "uk_period_start_min", "Earliest reporting period start among the entities used."),
    ("uk_period_end_max", "uk_period_end_max", "Latest reporting period end among the entities used."),
    ("uk_min_match_confidence", "uk_min_match_confidence", "Lowest entity-to-group match confidence among the entities used, 0 to 1."),
    ("es_pmp_days", "es_pmp_days", "Reported (Spain). Statutory average supplier payment period (PMP), days. Spanish entities as disclosed under Ley 15/2010."),
    ("es_prior_year_pmp_days", "es_prior_year_pmp_days", "Reported (Spain). PMP for the previous fiscal year, days."),
    ("es_ratio_paid_days", "es_ratio_paid_days", "Reported (Spain). Ratio of paid operations, days."),
    ("es_ratio_pending_days", "es_ratio_pending_days", "Reported (Spain). Ratio of pending operations, days."),
    ("es_pct_within_legal_max_by_value", "es_pct_within_legal_max_by_value", "Reported (Spain). Share of invoice value paid within the legal maximum, percent."),
    ("es_fiscal_year", "es_fiscal_year", "Fiscal year of the Spanish figure."),
    ("es_scope", "es_scope", "Whether the Spanish figure covers the group's Spanish entities or the parent company only."),
    ("es_source_url", "es_source_url", "Machine-readable filing the Spanish figure was read from."),
    ("es_report_url", "es_report_url", "Human-readable annual report."),
    ("computed_dpo_proxy_days", "dpo", "Computed DPO (proxy): trade payables / cost of sales x 365. Not a reported figure."),
    ("computed_dpo_proxy_prior_year_days", "dpo_prior", "Computed DPO (proxy) for the previous fiscal year."),
    ("computed_dpo_proxy_flag", "dpo_flag", "ok, suspicious_low, suspicious_high, missing_inputs or not_applicable (banks and insurers)."),
    ("computed_dpo_proxy_fiscal_year", "dpo_fiscal_year", "Fiscal year of the financial statements used."),
    ("computed_dpo_proxy_period_end", "dpo_period_end", "Balance sheet date used."),
    ("computed_dpo_proxy_sector_median_days", "dpo_sector_median", "Median computed DPO (proxy) for the group's sector in this index. Only meaningful for rows on the trade payables and cost of sales basis with a confident sector."),
    ("computed_dpo_proxy_payables_basis", "dpo_payables_basis", "Which payables line was used: trade, or the broader trade and other payables. The broader line is likely to overstate DPO."),
    ("computed_dpo_proxy_cost_basis", "dpo_cost_basis", "Which cost line was used: cost of sales, or a fallback (operating expenses or costs by nature). Fallback rows are not comparable with cost-of-sales rows."),
    ("computed_dpo_proxy_source_url", "dpo_source_url", "Filing the inputs were read from."),
    ("retrieved_at", "retrieved_at", "When the group record was assembled (UTC)."),
]
LOOKUP_COLS = ["company_name", "company_number", "avg_days_to_pay", "pct_paid_within_30", "pct_paid_31_60", "pct_paid_over_60",
               "pct_paid_late", "shortest_standard_payment_period_days", "longest_standard_payment_period_days",
               "max_contractual_payment_period_days", "period_start_yyyymmdd", "period_end_yyyymmdd", "report_is_old",
               "late_share_inconsistent", "official_report_id", "group_index"]


def assert_public(cols):
    bad = [c for c in cols if c.lower().startswith(FORBIDDEN_PREFIXES)]
    if bad:
        raise SystemExit(f"Refusing to publish internal columns: {bad}")


def write_csvs(comp, ents):
    (DIST / "data").mkdir(parents=True, exist_ok=True)
    e = ents[ents.usable].sort_values("company_name")
    e_out = pd.DataFrame({out: e[src] for out, src, _ in ENTITY_COLS if src in e.columns})
    assert_public(e_out.columns)
    e_out.to_csv(DIST / "data" / "chase-index-uk-entities.csv", index=False)

    c = comp[~comp.not_a_company.fillna(False).astype(bool)]
    c = c[c.uk_entities_n.notna() | c.es_pmp_days.notna() | c.dpo_flag.notna()].sort_values("name")
    g_out = pd.DataFrame({out: c[src] for out, src, _ in GROUP_COLS if src in c.columns})
    assert_public(g_out.columns)
    g_out.to_csv(DIST / "data" / "chase-index-groups.csv", index=False)
    return {"entities_rows": len(e_out), "groups_rows": len(g_out)}


def write_lookup(ents):
    e = ents[ents.usable].sort_values("company_name")
    groups, gidx, rows = [], {}, []

    def num(v):
        v = nn(v)
        if v is None:
            return None
        return int(v) if float(v).is_integer() else round(float(v), 1)

    def ymd(v):
        return int(str(v)[:10].replace("-", ""))

    for r in e.itertuples():
        m = re.search(r"/report/(\d+)$", str(r.source_url))
        if not m:
            continue
        g = nn(getattr(r, "group_name", None))
        if g is not None and g not in gidx:
            gidx[g] = len(groups)
            groups.append(g)
        rows.append([r.company_name, r.company_number, num(r.avg_days_to_pay), num(r.pct_paid_within_30), num(r.pct_paid_31_60),
                     num(r.pct_paid_over_60), num(r.pct_paid_late), num(r.shortest_standard_payment_period_days),
                     num(r.longest_standard_payment_period_days), num(r.max_contractual_payment_period_days),
                     ymd(r.period_start), ymd(r.period_end), 0 if r.current else 1,
                     1 if "pct_late_inconsistent" in str(r.quality_flag) else 0, int(m.group(1)),
                     gidx[g] if g is not None else None])
    idx = {"about": "UK statutory payment practices reports, latest usable report per legal entity. " + OGL,
           "report_base": UK_REPORT_BASE, "cols": LOOKUP_COLS, "groups": groups, "rows": rows}
    path = DIST / "data" / "lookup-index.json"
    path.write_text(json.dumps(idx, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    return len(rows), path.stat().st_size


# ----------------------------------------------------------------------------- pages
def make_env():
    env = Environment(loader=FileSystemLoader(str(SRC / "templates")), autoescape=select_autoescape(["html"]),
                      trim_blocks=True, lstrip_blocks=True)
    env.filters.update(d1=d1, pct=pct, raw=raw, int_c=int_c, signed=signed, dmy=dmy)
    return env


class Site:
    def __init__(self, env, common):
        self.env, self.common, self.pages = env, common, []

    def write(self, path, template, title, description, active="", **ctx):
        root = "../" * path.count("/")
        html = self.env.get_template(template).render(path=path, root=root, title=title, description=description,
                                                      active=active, **self.common, **ctx)
        html = html.replace("—", ", ").replace("–", "-")   # no em dashes in site copy, whatever the source
        out = DIST / path
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(html, encoding="utf-8")
        self.pages.append(path)

    def doc(self, path, body_md, title, description, active="", kicker=""):
        self.write(path, "doc.html", title, description, active=active, body=md_html(body_md), kicker=kicker)


def content(env, name, **ctx):
    return env.from_string((SRC / "content" / name).read_text(encoding="utf-8")).render(**ctx)


def company_page(site, g, row, by_group, h):
    prof = q.get_payment_profile(g["id"])
    uk = prof["reported"].get("uk")
    es = prof["reported"].get("spain")
    dpo = prof.get("computed_proxy")
    if dpo and (dpo.get("dpo_days") is None or dpo.get("flag") not in ("ok", "suspicious_low", "suspicious_high")):
        dpo = None
    entities, other_n = [], 0
    left_out = [re.sub(r"\s*\([^()]*\)\s*$", "", x).strip() for x in str(nn(row.get("uk_entities_excluded_extreme")) or "").split("|") if x.strip()]
    if uk:
        mine = by_group.get(g["id"])
        if mine is not None:
            cur = mine[mine.current].sort_values("avg_days_to_pay", ascending=False)
            other_n = int(len(mine) - len(cur))
            for e in cur.itertuples():
                days, tr = nn(e.avg_days_to_pay), nn(e.trend_days_yoy)
                lo, hi = nn(e.shortest_standard_payment_period_days), nn(e.longest_standard_payment_period_days)
                terms = "" if lo is None else (f"{d1(lo)} days" if hi is None or hi == lo else f"{d1(lo)} to {d1(hi)} days")
                entities.append({"name": e.company_name, "number": e.company_number, "period_start": e.period_start,
                                 "period_end": e.period_end, "days": days,
                                 "prior": None if days is None or tr is None else days - tr,
                                 "w30": e.pct_paid_within_30, "m31": e.pct_paid_31_60, "o60": e.pct_paid_over_60,
                                 "late": e.pct_paid_late, "late_flag": "pct_late_inconsistent" in str(e.quality_flag),
                                 "left_out": e.company_name in left_out,
                                 "terms": terms, "maxc": e.max_contractual_payment_period_days,
                                 "match": MATCH.get(nn(e.match_method), nn(e.match_method) or ""), "url": e.source_url})
    name = prof["name"]
    bits = []
    uk_ctx = {}
    if uk:
        n = uk["entities_n"]
        weighted = nn(row.get("uk_days_aggregation")) == "invoice_value_weighted_mean"
        simple = nn(row.get("uk_avg_days_to_pay_simple_mean"))
        if n == 1:
            label = "average reported days to pay, 1 UK entity"
            bits.append(f"1 UK legal entity matched to {name} reports an average of {d1(uk['avg_days_to_pay_mean_of_entities'])} days to pay invoices.")
        elif weighted:
            label = (f"average reported days to pay across {n} UK entities, weighted by the invoice value each one reports. "
                     f"Simple mean: {d1(simple)}.")
            bits.append(f"{n} UK legal entities matched to {name} report an average of {d1(uk['avg_days_to_pay_mean_of_entities'])} "
                        f"days to pay invoices, weighted by the invoice value each one reports (simple mean: {d1(simple)}).")
        else:
            label = f"average reported days to pay, simple mean of {n} UK entities (not all of them report an invoice value)"
            bits.append(f"{n} UK legal entities matched to {name} report an average of {d1(uk['avg_days_to_pay_mean_of_entities'])} "
                        f"days to pay invoices (simple mean).")
        tn, slower = nn(row.get("uk_trend_entities_n")), nn(row.get("uk_trend_entities_slower_n"))
        med = nn(row.get("uk_trend_days_yoy_median"))
        if not tn or med is None:
            trend_label = "change in days to pay against one year earlier: no entity has a report one year earlier"
        elif n == 1:
            trend_label = "change in days to pay against one year earlier"
        else:
            trend_label = (f"median change in days to pay against one year earlier. "
                           f"{int(slower or 0)} of {int(tn)} entities with a comparison got slower.")
        uk_ctx = {"uk_days_label": label, "uk_weighted": weighted and n > 1, "uk_trend_value": med if tn else None,
                  "uk_trend_label": trend_label,
                  "uk_trend_weighted": nn(row.get("uk_trend_days_yoy_weighted")) if weighted and n > 1 and tn else None,
                  "uk_left_out": ", ".join(left_out)}
    if es:
        bits.append(f"In Spain, the statutory average supplier payment period for fiscal year {d1(es['fiscal_year'])} "
                    f"is {d1(es['pmp_days'])} days.")
    if not bits:
        bits.append(f"There is no reported payment data for {name} in this index. A computed balance-sheet proxy is shown below, clearly labelled.")
    elif dpo:
        bits.append("A computed balance-sheet proxy is shown separately below.")
    dpo_ctx = {}
    if dpo:
        flag = dpo["flag"]
        pay = PAYABLES.get(dpo.get("payables_basis"), dpo.get("payables_basis") or "payables (basis not recorded)")
        cost = COSTS.get(dpo.get("cost_basis"), dpo.get("cost_basis") or "costs (basis not recorded)")
        clean = dpo.get("payables_basis") == "trade" and dpo.get("cost_basis") == "cost_of_sales"
        sc = nn(row.get("sector_confidence"))
        show_median = clean and flag == "ok" and nn(row.sector) != "other" and (sc is None or sc >= MIN_SECTOR_CONFIDENCE)
        if flag != "ok":
            note = "The result is outside the plausible range (below 5 or above 365 days) and is flagged. Treat it as unreliable."
        elif clean:
            note = "Basis: trade payables and cost of sales, as tagged in the filing."
        else:
            note = (f"Lower-confidence calculation: the filing does not tag trade payables or cost of sales separately, so this uses "
                    f"{pay} and {cost} and may overstate DPO. Not comparable with the sector median.")
        dpo_ctx = {
            "dpo_note": note, "dpo_payables": pay, "dpo_cost": cost, "dpo_show_median": show_median,
            "dpo_source_label": "SEC EDGAR filing" if str(dpo.get("source_type", "")).startswith("sec")
                                else "ESEF annual report on filings.xbrl.org",
        }
    c = {"name": name, "country_name": g["country_name"], "hq_city": nn(row.hq_city), "sector_name": g["sector_name"],
         "summary": " ".join(bits), "revenue_text": money(row.revenue, row.revenue_currency),
         "revenue_period_end": nn(row.revenue_period_end), "revenue_source_url": nn(row.revenue_source_url),
         "is_unit": bool(nn(row.is_subsidiary_or_unit))}
    kinds = [k for k, v in (("reported UK days to pay", uk), ("Spanish supplier payment period", es), ("computed DPO (proxy)", dpo)) if v]
    site.write(f"company/{g['id']}.html", "company.html",
               f"{name}: supplier payment times and days to pay | {SITE_NAME}",
               f"How long does {name} take to pay supplier invoices? {', '.join(kinds).capitalize() or 'Payment data'}, with period and official source links.",
               c=c, uk=uk, es=es, dpo=dpo, entities=entities, other_entities_n=other_n, **uk_ctx,
               official_median=h["official_median_days"], **dpo_ctx)


def spain_page(site, es, page_ids, h):
    ok = es[(es.status == "ok") & es.pmp_days.notna()].sort_values("pmp_days", ascending=False)
    rows = []
    for r in ok.itertuples():
        flags = [ES_FLAG.get(f, f.replace("_", " ").capitalize() + ".") for f in str(nn(r.quality_flag) or "").split(";") if f]
        cid = nn(r.company_id)
        rows.append({"name": r.company_name, "ticker": r.ticker, "pmp": r.pmp_days, "prior": r.prior_year_pmp_days,
                     "paid": r.ratio_paid_days, "pending": r.ratio_pending_days,
                     "within": r.pct_invoices_paid_within_legal_max_by_value,
                     "scope": ES_SCOPE.get(nn(r.scope), str(nn(r.scope) or "").replace("_", " ")), "flag": " ".join(flags),
                     "url": nn(r.human_readable_report_url) or r.source_url, "page": cid if cid in page_ids else None})
    missing, total, ibex_date = [], len(ok), ""
    ibex = ROOT / "data" / "interim" / "ibex35_constituents.csv"
    if ibex.exists():
        ib = pd.read_csv(ibex)
        total = len(ib)
        ibex_date = dmy(ib.retrieved_at.max())
        for r in ib[~ib.ticker.isin(ok.ticker)].itertuples():
            missing.append({"name": r.company_name, "ticker": r.ticker,
                            "reason": ES_MISSING.get(r.ticker, "No figure could be read from the filing with confidence.")})
    prior = ok[ok.prior_year_pmp_days.notna()]
    site.write("spain.html", "spain.html",
               f"IBEX 35 supplier payment periods (PMP) {h['es_fy']}: how long Spain's largest companies take to pay | {SITE_NAME}",
               "Statutory average supplier payment period (periodo medio de pago a proveedores) for IBEX 35 companies, with the 60-day legal maximum explained and a source link for every figure.",
               active="spain.html", rows=rows, n=len(ok), total=total, fy=h["es_fy"], median=h["es_median"],
               over60=h["es_over_60_n"], longer=int((prior.pmp_days > prior.prior_year_pmp_days).sum()),
               with_prior=len(prior), missing=missing, ibex_date=ibex_date or "the retrieval date")


def faq_items(h):
    disclosure = f'<p class="disclosure">{DISCLOSURE}</p>'
    cats = """
- **Accounts payable (AP) automation suites** capture invoices, match them to purchase orders, route approvals and pay. Examples: Basware, BILL, Coupa, Esker, Medius, Stampli, Tipalti.
- **Accounts receivable (AR) and collections tools** send reminders, apply cash and manage disputes for the company that is owed money. Examples: Billtrust, HighRadius, Serrala, Versapay.
- **Supply chain finance and dynamic discounting platforms** let a buyer pay suppliers early in return for a discount, or let a funder do it. Examples: C2FO, SAP Taulia.
- **Two-sided agent networks**: a newer category. According to their own descriptions, vendors in this category put an AI agent on the buyer's AP side and another on the supplier's AR side that match invoices, resolve disputes and agree payment timing between them. The author has not tested them.

These lists are examples, not exhaustive.
"""
    items = [
        ("how-long", "How long do large companies take to pay suppliers?",
         f"In the UK, where large companies must report it, the official median time to pay was {d1(h['official_median_days'])} days in "
         f"{h['official_year']}, and the median share of invoices paid late was {d1(h['official_median_late'])}%. In this index, "
         f"{int_c(h['uk_current_n'])} UK legal entities have a current report. Their median average is {d1(h['uk_median_days'])} days, and "
         f"{d1(h['uk_share_over_60'])}% of them report an average of more than 60 days. In Spain, {h['es_over_60_n']} of {h['es_n']} "
         f"IBEX 35 companies with a published figure report an average supplier payment period of more than 60 days for fiscal year "
         f"{h['es_fy']}. 60 days is the legal maximum for an individual payment in Spain; an average above it is not a finding about any "
         f"single invoice. These are averages per reporting entity, so a single company can be well above or below them. "
         f"See the [index](index.html) and the [Spain page](spain.html)."),
        ("which-data", "Which data shows how fast a company pays its invoices?",
         f"Three public sources, in order of reliability. First, the UK's statutory payment practices reports: large UK companies and LLPs "
         f"report twice a year, per legal entity, their average days to pay, the share of invoices paid within 30 days, in 31 to 60 days and "
         f"later, and the share not paid within agreed terms. You can search them on [GOV.UK]({UK_SEARCH_URL}) or with the "
         f"[supplier lookup](lookup.html) here. Second, in Spain every company states its average supplier payment period in the notes to "
         f"its annual accounts under Ley 15/2010. Third, for any listed company you can compute days payable outstanding from the "
         f"balance sheet, which is a rough proxy and not a reported payment time."),
        ("days-vs-dpo", "What is the difference between days to pay and DPO?",
         "Days to pay is measured from invoices: the average time between receiving an invoice and paying it, as the company reports it. "
         "DPO (days payable outstanding) is computed from financial statements: trade payables divided by cost of sales, times 365. DPO "
         "includes accruals, goods received but not yet invoiced and year-end timing, and it depends on which costs are counted. The two can "
         "differ by weeks for the same company. This index always shows reported days to pay first and labels DPO as "
         "\"computed DPO (proxy)\"."),
        ("chasing-software", "What software automates chasing suppliers and customers for invoice approvals and payment status?",
         "It depends on which side of the invoice you are on. Four categories cover most of the market:\n" + cats +
         "\nMany of these tools are bought and run by one side, the buyer or the supplier, and reach the other side through a portal or "
         "email. This index does not rank or recommend any vendor."),
        ("ai-agents", "What are the best AI agents for AP and AR automation for large enterprises?",
         "There is no neutral ranking, and this index does not make one. \"Best\" depends on your ERP, invoice volumes, how many suppliers "
         "you have and whether your problem is capture, approval, disputes or cash timing. What can be said factually is how the options "
         "differ:\n" + cats +
         "\nQuestions worth asking any vendor: does the agent post to the ERP on its own or propose for human approval, what share of "
         "invoices goes through without a human touch in a comparable deployment, how are suppliers onboarded, and how is the pricing tied "
         "to results."),
        ("early-payment", "Which tools help capture early-payment discounts and reduce manual invoice follow-ups?",
         "Early-payment discounts are lost when an invoice is approved too late to pay inside the discount window, so the answer has two "
         "parts: approve faster, and have a way to offer or accept early payment.\n" + cats +
         "\nBefore choosing, measure where you stand: your own average days to pay, the share of invoices paid late and how long approval "
         "takes. For UK entities, the figures your customers and competitors report are public, see the [supplier lookup](lookup.html)."),
    ]
    out = []
    for i, (fid, question, answer) in enumerate(items):
        html = md_html(answer)
        if i >= 3:
            html += disclosure
        out.append({"id": fid, "q": question, "html": html,
                    "text": strip_tags(html)})
    return out


def data_dictionary_md(files):
    lines = ["# Data dictionary", "",
             "Definitions for every column in the public downloads. Reported figures and the computed proxy are kept in separate columns and never mixed.",
             "", f"## chase-index-uk-entities.csv ({int_c(files['entities_rows'])} rows)", "",
             "One row per UK legal entity with a usable statutory report. " + OGL, "", "| Column | Meaning |", "|---|---|"]
    lines += [f"| `{o}` | {d} |" for o, _, d in ENTITY_COLS]
    lines += ["", f"## chase-index-groups.csv ({int_c(files['groups_rows'])} rows)", "",
              "One row per large group with reported data or a computed proxy. UK group figures: UK legal entities only, matched to the group. "
              "Not a statement about the group's global payment behaviour. Spanish figures: covers the group's Spanish entities as disclosed under Ley 15/2010.",
              "", "| Column | Meaning |", "|---|---|"]
    lines += [f"| `{o}` | {d} |" for o, _, d in GROUP_COLS]
    lines += ["", "## data/lookup-index.json", "",
              "The compact index behind the supplier lookup. `rows` is a list of arrays with these positions:", ""]
    lines += [f"{i}. `{c}`" for i, c in enumerate(LOOKUP_COLS)]
    lines += ["", "`group_index` points into the `groups` list. The official report URL is `report_base` plus `official_report_id`."]
    # docs/data_dictionary.md documents the internal pipeline tables, including sales-only columns.
    # It is deliberately not rendered on the public site: only the published files are described here.
    lines += ["", "## Pipeline tables", "",
              "The tables behind these files are documented in the project repository. Only the columns listed on this page are published."]
    lines += ["", DISCLAIMER]
    return "\n".join(lines)


def llms_txt(h, files, pages_n):
    return f"""# {SITE_NAME}

> An independent, source-traceable dataset on how long large companies take to pay their suppliers. Reported figures from UK statutory payment practices reports and from the annual accounts of IBEX 35 companies in Spain, plus a separately labelled computed DPO proxy for listed groups. {DISCLAIMER}

## Headline figures (computed from the data at build time)
- UK legal entities with a current statutory report: {int_c(h['uk_current_n'])}
- Median of their average reported days to pay: {d1(h['uk_median_days'])} days (official {h['official_year']} median for large UK businesses: {d1(h['official_median_days'])} days)
- Share of those entities reporting an average of more than 60 days to pay: {d1(h['uk_share_over_60'])}%
- Change against one year earlier: {d1(h['uk_share_longer'])}% report a longer average, {d1(h['uk_share_shorter'])}% a shorter one (of {int_c(h['uk_trend_n'])} with a comparison). {d1(h['uk_share_small_change'])}% of all changes are one day or less.
- Median share of invoices not paid within agreed terms: {d1(h['uk_median_late'])}%
- IBEX 35 companies with a published average supplier payment period of more than 60 days, fiscal year {h['es_fy']}: {h['es_over_60_n']} of {h['es_n']}. 60 days is the legal maximum for an individual payment in Spain; an average above it is not a finding about any single invoice.
- UK reporting periods covered by current reports: {h['uk_period_min']} to {h['uk_period_max']} (period end dates)

## Files
- {SITE_URL}data/chase-index-uk-entities.csv : one row per UK legal entity with a usable report ({int_c(files['entities_rows'])} rows)
- {SITE_URL}data/chase-index-groups.csv : one row per large group with reported data or a computed proxy ({int_c(files['groups_rows'])} rows)
- {SITE_URL}data/lookup-index.json : compact index behind the supplier lookup
- {SITE_URL}data-dictionary.html : column definitions
- {SITE_URL}methodology.html : how each number is produced
- {SITE_URL}limitations.html : what the data cannot tell you

## Pages
- {SITE_URL}index.html : headline findings, charts and a sortable table of groups
- {SITE_URL}lookup.html : supplier lookup, "How long does my customer take to pay?", by UK company name or number
- {SITE_URL}spain.html : IBEX 35 average supplier payment period (PMP) table
- {SITE_URL}faq.html : days to pay, DPO and categories of AP and AR software
- {SITE_URL}company/<company_id>.html : one page per group ({int_c(pages_n)} pages)

## Definitions
- Average reported days to pay: the average number of days a UK legal entity took to pay invoices in a six-month reporting period, as filed by the entity under the Reporting on Payment Practices and Performance Regulations 2017.
- Share of invoices paid late: the share of invoices not paid within agreed terms, as filed.
- PMP (periodo medio de pago a proveedores): the statutory average supplier payment period Spanish companies disclose in their annual accounts under Ley 15/2010. The legal maximum between companies is 60 days.
- Computed DPO (proxy): trade payables / cost of sales x 365 from published financial statements. A balance-sheet proxy, not a reported payment time.

## Caveats
- UK figures are per legal entity. {GROUP_FIGURE_SENTENCE} UK legal entities only, matched to the group. Not a statement about the group's global payment behaviour.
- Spanish figures cover the group's Spanish entities as disclosed under Ley 15/2010.
- Reported figures and the computed proxy are never mixed. An empty value means no figure, not zero.
- The official source wins. Every figure links to it.
- Company-level data only. No ratings or judgements about companies.

## Licence
- {OGL}
- The selection, cleaning and group links: {LICENCE_NAME}. The UK figures remain public sector information under the Open Government Licence v3.0. Cite "The Chase Index, Moritz Hanbuch".
- {CH_ATTRIBUTION} (group links, corporate records only).

## Disclosure
The author built this index as part of a job application to an agent-to-agent B2B payments startup. {DISCLAIMER}
"""


# ----------------------------------------------------------------------------- main
def build():
    comp, ents, es, bench = load()
    if DIST.exists():
        shutil.rmtree(DIST)
    (DIST / "assets").mkdir(parents=True)
    for f in (SRC / "assets").iterdir():
        shutil.copy(f, DIST / "assets" / f.name)

    groups = group_rows(comp)
    h = headline(comp, ents, es, bench, groups)
    files = write_csvs(comp, ents)
    lookup_n, lookup_bytes = write_lookup(ents)
    data_date = dmy(str(ents.retrieved_at.max())[:10])

    env = make_env()
    common = {"site_url": SITE_URL, "site_name": SITE_NAME, "disclaimer": DISCLAIMER, "ogl": OGL, "nav": NAV,
              "data_date": data_date, "contact": CONTACT, "ch_attribution": CH_ATTRIBUTION, "disclosure": DISCLOSURE}
    site = Site(env, common)
    cctx = dict(h=h, files=files, disclaimer=DISCLAIMER, ogl=OGL, contact=CONTACT, data_date=data_date,
                licence_name=LICENCE_NAME, licence_url=LICENCE_URL, ch_attribution=CH_ATTRIBUTION,
                imprint_address=IMPRINT_ADDRESS)

    # home
    dataset = {
        "@context": "https://schema.org", "@type": "Dataset", "name": f"{SITE_NAME}: how long large companies take to pay their suppliers",
        "description": (f"Reported supplier payment times for {h['uk_current_n']:,} UK legal entities with a current statutory payment practices report "
                        f"and for {h['es_n']} IBEX 35 companies in Spain (statutory average supplier payment period), plus a separately "
                        f"labelled computed DPO proxy for listed groups. Every figure carries its period and official source link. "
                        f"{OGL} {DISCLAIMER}"),
        "url": SITE_URL, "creator": {"@type": "Person", "name": "Moritz Hanbuch"}, "license": LICENCE_URL, "isAccessibleForFree": True,
        "keywords": ["days to pay", "late payment", "supplier payment terms", "accounts payable", "invoice", "payment practices",
                     "days payable outstanding", "periodo medio de pago a proveedores"],
        "temporalCoverage": f"{h['uk_period_start_min']}/{h['uk_period_max']}", "spatialCoverage": ["United Kingdom", "Spain"],
        "variableMeasured": ["Average reported days to pay", "Share of invoices not paid within agreed terms",
                             "Share of invoices paid after more than 60 days", "Average supplier payment period (PMP)",
                             "Computed DPO (proxy)"],
        "distribution": [{"@type": "DataDownload", "encodingFormat": "text/csv", "contentUrl": SITE_URL + "data/chase-index-uk-entities.csv"},
                         {"@type": "DataDownload", "encodingFormat": "text/csv", "contentUrl": SITE_URL + "data/chase-index-groups.csv"}],
        "isBasedOn": [UK_SEARCH_URL, bench.source_page.iloc[0], "https://filings.xbrl.org/", "https://www.sec.gov/edgar"],
    }
    countries = sorted({(g["country"], g["country_plain"]) for g in groups if g["country"]}, key=lambda x: x[1])
    sectors = sorted({(g["sector"], g["sector_name"]) for g in groups if g["sector"]}, key=lambda x: x[1])
    site.write("index.html", "index.html",
               f"{SITE_NAME}: how long large companies take to pay supplier invoices",
               f"Days to pay, late payment shares and supplier payment terms for {h['uk_current_n']:,} UK entities and the IBEX 35, from official "
               f"reports. Free supplier lookup. Every figure linked to its source.",
               active="index.html", h=h, small_base_n=SMALL_BASE_N, groups=groups, countries=countries, sectors=sectors, hist=histogram(ents, h),
               sector=sector_chart(bench), trend=trend_chart(bench), dataset_jsonld=jsonld(dataset))

    # company pages
    crow = comp.set_index("company_id", drop=False)
    by_group = {k: v for k, v in ents[ents.usable & ents.company_id.notna()].groupby("company_id")} if "company_id" in ents else {}
    for g in groups:
        company_page(site, g, crow.loc[g["id"]], by_group, h)
    company_n = len(groups)

    site.write("lookup.html", "lookup.html",
               f"How long does my customer take to pay? Free UK supplier payment lookup | {SITE_NAME}",
               f"Look up how long a UK company takes to pay invoices: average days to pay, share paid late and standard payment terms for "
               f"{lookup_n:,} UK legal entities, from their statutory reports.",
               active="lookup.html", n=lookup_n, current_n=h["uk_current_n"])
    spain_page(site, es, {g["id"] for g in groups}, h)

    # docs
    internal_note = (f"\n\n{CH_ATTRIBUTION}. Group links are derived from its public data on persons with significant control "
                     "(corporate records only)."
                     "\n\n> The author also keeps a private analysis built on this data. It is not part of the public index, "
                     "and none of it is published on this site.\n")
    meth = DOCS / "methodology.md"
    meth_md = public_md(meth.read_text(encoding="utf-8")) + internal_note if meth.exists() else \
        f"# Methodology\n\nThis document is being written. It will describe how each number is produced.\n\n{DISCLAIMER}"
    site.doc("methodology.html", meth_md, f"Methodology: how days to pay, late payment shares and DPO are measured | {SITE_NAME}",
             "How the index is built: UK statutory payment practices reports, Spanish average supplier payment periods, entity-to-group matching and the computed DPO proxy.",
             active="methodology.html", kicker="How the numbers are made")
    lim = DOCS / "limitations.md"
    lim_md = public_md(lim.read_text(encoding="utf-8")) if lim.exists() else f"""# Limitations

The full limitations document is being written. Until it is here, these are the points that matter most:

- UK legal entities only, matched to the group. Not a statement about the group's global payment behaviour.
- Covers the group's Spanish entities as disclosed under Ley 15/2010.
- Computed DPO (proxy) is a balance-sheet ratio. It is not a reported payment time.
- Linking UK legal entities to parent groups is done from public records and can be wrong or incomplete. Only confident matches are used.
- Figures are as filed by the companies. Some reports contain values that do not fit together, and those are flagged, not corrected.
- The official source wins. See [corrections](corrections.html).

{DISCLAIMER}"""
    site.doc("limitations.html", lim_md, f"Limitations: what supplier payment data can and cannot tell you | {SITE_NAME}",
             "What the reported days to pay, late payment shares and the computed DPO proxy in this index do and do not show.",
             kicker="Read this before quoting a figure")
    site.doc("data-dictionary.html", data_dictionary_md(files), f"Data dictionary: columns in the supplier payment dataset | {SITE_NAME}",
             "Definitions of every column in the downloadable CSV files: days to pay, share of invoices paid late, payment terms, PMP and computed DPO (proxy).")
    site.doc("data.html", content(env, "data.md", **cctx), f"Download the data: supplier payment times as CSV | {SITE_NAME}",
             "Free CSV downloads of reported days to pay, late payment shares and supplier payment terms, with licence and attribution.",
             active="data.html", kicker="Open data")
    site.doc("corrections.html", content(env, "corrections.md", **cctx), f"Corrections: how to report an error | {SITE_NAME}",
             "How to report an error in a payment figure or a company match. The official source always wins.")
    site.doc("about.html", content(env, "about.md", **cctx), f"About: who built this supplier payment index and why | {SITE_NAME}",
             "An independent student project that makes public data on days to pay and late payment easy to look up. What it is and what it is not.",
             active="about.html", kicker="About")

    faqs = faq_items(h)
    faq_ld = {"@context": "https://schema.org", "@type": "FAQPage",
              "mainEntity": [{"@type": "Question", "name": f["q"], "acceptedAnswer": {"@type": "Answer", "text": f["text"]}} for f in faqs]}
    site.write("faq.html", "faq.html", f"FAQ: days to pay, DPO, late payment and AP/AR automation software | {SITE_NAME}",
               "Plain answers on how long large companies take to pay suppliers, days to pay versus DPO, and the categories of accounts payable, accounts receivable and early-payment discount tools.",
               active="faq.html", faqs=faqs, faq_jsonld=jsonld(faq_ld))

    # machine-readable extras
    (DIST / "robots.txt").write_text(
        "# The Chase Index: all crawlers welcome, including AI crawlers.\n" +
        "".join(f"User-agent: {ua}\nAllow: /\n\n" for ua in ("GPTBot", "ClaudeBot", "PerplexityBot", "Google-Extended", "*")) +
        f"Sitemap: {SITE_URL}sitemap.xml\n", encoding="utf-8")
    urls = "".join(f"  <url><loc>{SITE_URL}{'' if p == 'index.html' else p}</loc></url>\n" for p in site.pages)
    (DIST / "sitemap.xml").write_text('<?xml version="1.0" encoding="UTF-8"?>\n<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n'
                                      + urls + "</urlset>\n", encoding="utf-8")
    (DIST / "llms.txt").write_text(llms_txt(h, files, company_n), encoding="utf-8")

    size = sum(f.stat().st_size for f in DIST.rglob("*") if f.is_file())
    summary = {"pages_total": len(site.pages), "company_pages": company_n, "groups_reported": h["groups_reported_n"],
               "groups_proxy_only": h["groups_proxy_only_n"], "lookup_rows": lookup_n, "lookup_index_bytes": lookup_bytes,
               "dist_bytes": size, "csv_rows": files,
               "headline": {k: (round(v, 2) if isinstance(v, float) else v) for k, v in h.items()}}
    (DIST / "build-summary.json").write_text(json.dumps(summary, indent=1), encoding="utf-8")
    print(f"Built {len(site.pages)} pages ({company_n} company pages) into {DIST.relative_to(ROOT)}")
    print(f"  dist size {size / 1e6:.1f} MB, lookup index {lookup_bytes / 1e3:.0f} kB ({lookup_n:,} entities)")
    print(f"  UK: {h['uk_current_n']:,} current entities, median {d1(h['uk_median_days'])} days, {d1(h['uk_share_over_60'])}% over 60 days, "
          f"{d1(h['uk_share_longer'])}% slower than a year earlier")
    print(f"  Spain: {h['es_over_60_n']} of {h['es_n']} IBEX 35 companies above 60 days PMP (FY {h['es_fy']})")
    return summary


def release_problems(dist: Path = DIST) -> list[str]:
    """Files in dist that still contain a placeholder (site URL, contact address, imprint). Empty list = releasable."""
    bad = []
    for f in sorted(dist.rglob("*")):
        if f.is_file() and f.suffix in {".html", ".txt", ".xml", ".json", ".csv", ".js", ".css"}:
            text = f.read_text(encoding="utf-8", errors="replace")
            hits = [p for p in RELEASE_PLACEHOLDERS if p in text]
            if hits:
                bad.append(f"{f.relative_to(dist)}: {', '.join(hits)}")
    return bad


if __name__ == "__main__":
    build()
    if "--release" in sys.argv[1:]:
        problems = release_problems()
        if problems:
            print(f"RELEASE CHECK FAILED: placeholders left in {len(problems)} files, for example:")
            for line in problems[:8]:
                print("  " + line)
            print("Set CHASE_SITE_URL, CHASE_CONTACT_EMAIL and CHASE_IMPRINT_ADDRESS and rebuild.")
            sys.exit(1)
        print("Release check passed: no placeholder URL, contact or imprint left in site/dist.")
