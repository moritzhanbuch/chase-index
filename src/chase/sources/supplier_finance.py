"""Supplier finance arrangements (reverse factoring / supply chain finance) from XBRL TAGS only.

Extractor A ("sfa-a", deterministic) of a dual-extractor setup. Extractor B reads annual-report
text with an LLM; this module never reads prose to produce a value. Every amount here is a tagged
XBRL fact.

Run:  python -m chase.sources.supplier_finance              (top-200 list, full record)
      python -m chase.sources.supplier_finance --universe   (whole universe, slim status table)

Inputs (all cache-backed through chase.common.http; a file is only downloaded if it is not cached):
- data/interim/top200.csv
- SEC company facts  https://data.sec.gov/api/xbrl/companyfacts/CIK##########.json
- ESEF xBRL-JSON per filing from filings.xbrl.org (selection logic reused from esef_xbrl.py)

Outputs: data/interim/sfa_extract_a.json and .csv, one record per top-200 company.
With --universe: data/interim/sfa_universe_tags.csv (+ .json with run meta), one row per company in
data/processed/universe.parquet.

Status vocabulary (IMPORTANT: "not tagged" is NOT "no programme"):
- tagged                a supplier-finance concept carries a numeric value (amount outstanding etc.)
- tagged_text_only      only a text-block concept dedicated to supplier finance is tagged (no amount)
- not_tagged            structured data exists, no supplier-finance concept in it. Says nothing about
                        whether a programme exists: ESEF notes are block-tagged, US filers below
                        materiality do not tag, and SEC company facts carry standard numeric facts only.
- no_structured_source  company is in neither SEC nor ESEF data (or its file is unavailable)

Concept names are DISCOVERED by substring scan of the concept keys (see SFA_NAME_RE); roles are
assigned from name parts (classify_concept), not from a hard-coded list.
"""
from __future__ import annotations

import html
import json
import re
import time
from collections import Counter
from datetime import date
from pathlib import Path

import pandas as pd

from chase.common import http
from chase.common.http import fetch, now_iso
from chase.sources import esef_xbrl as E

ROOT = http.ROOT
TOP200 = ROOT / "data" / "interim" / "top200.csv"
OUT_JSON = ROOT / "data" / "interim" / "sfa_extract_a.json"
OUT_CSV = ROOT / "data" / "interim" / "sfa_extract_a.csv"
UNIVERSE = ROOT / "data" / "processed" / "universe.parquet"
UNIV_CSV = ROOT / "data" / "interim" / "sfa_universe_tags.csv"
UNIV_JSON = ROOT / "data" / "interim" / "sfa_universe_tags.json"
UNIV_FIELDS = ["company_id", "name", "status", "source", "amount", "currency", "period_end", "concept",
               "source_url", "retrieved_at"]
SEC_FACTS_URL = "https://data.sec.gov/api/xbrl/companyfacts/CIK{cik}.json"
SEC_TAXONOMIES = ("us-gaap", "ifrs-full")
ANNUAL_FORMS = {"10-K", "10-K/A", "10-KT", "20-F", "20-F/A", "40-F", "40-F/A"}

# Concepts that count as "supplier finance" (payables side).
SFA_NAME_RE = re.compile(
    r"SupplierFinanc|SupplyChainFinanc|ReverseFactoring|SupplierFinanceArrangement|Confirming"
    r"|AffacturageInvers|PayablesFinanc|StructuredPayable|VendorFinanc", re.I)
# Logged in notes but NOT counted: plain factoring is usually receivables-side.
RELATED_NAME_RE = re.compile(r"Factoring", re.I)

# Key phrases for the cheap text-block signal, strongest first. "confirming" alone is weak in
# English text ("confirming that ..."), so it is searched last and flagged in notes.
TEXT_PHRASES = [
    ("supplier finance", r"supplier\s*financ"),
    ("reverse factoring", r"reverse\s*factoring"),
    ("supply chain finance", r"supply\s*chain\s*financ"),
    ("affacturage inverse", r"affacturage\s*invers"),
    ("payables finance", r"payables\s*financ"),
    ("confirming", r"\bconfirming\b"),
]
TEXT_RES = [(label, re.compile(rx, re.I)) for label, rx in TEXT_PHRASES]
_TAG_RE = re.compile(r"<[^>]+>")
_WS_RE = re.compile(r"\s+")


# ----------------------------------------------------------------------------- discovery

def local_name(concept: str) -> str:
    return concept.split(":", 1)[-1]


def discover_concepts(names) -> list[str]:
    """Concept names (with or without prefix) that look like supplier-finance concepts."""
    return sorted(n for n in names if SFA_NAME_RE.search(local_name(n)))


def related_concepts(names) -> list[str]:
    return sorted(n for n in names if RELATED_NAME_RE.search(local_name(n))
                  and not SFA_NAME_RE.search(local_name(n)))


def classify_concept(concept: str) -> str:
    """Role from name parts. One of: obligation, obligation_current, obligation_noncurrent,
    increase, settlement, net_change, already_paid, terms_with, terms_without, text, other."""
    n = local_name(concept)
    low = n.lower()
    if re.search(r"explanatory|textblock|policy|descriptionof|disclosureof", low):
        return "text"
    if re.search(r"duedate|paymentterm|paymenttiming|daystopay", low):
        if re.search(r"notpartof|notpart|comparabletradepayables|excluding|without", low):
            return "terms_without"
        return "terms_with"
    if re.search(r"alreadyreceivedpayment|havereceivedpayment|alreadypaid|receivedpaymentfromfinanceprovider", low):
        return "already_paid"
    if re.search(r"periodincreasedecrease|increasedecrease", low):
        return "net_change"
    if re.search(r"decrease|settlement", low):
        return "settlement"
    if "increase" in low:
        return "increase"
    if re.search(r"obligation|carryingamount|liabilit|payable", low):
        if low.endswith("noncurrent"):
            return "obligation_noncurrent"
        if low.endswith("current"):
            return "obligation_current"
        return "obligation"
    return "other"


# ----------------------------------------------------------------------------- SEC

def _days(a: str, b: str) -> int:
    return (date.fromisoformat(b) - date.fromisoformat(a)).days


def sec_entries(concept_obj: dict) -> tuple[str | None, list[dict]]:
    """(unit, entries) for the unit with the most entries."""
    units = concept_obj.get("units") or {}
    if not units:
        return None, []
    unit = max(units, key=lambda u: len(units[u]))
    return unit, units[unit]


def select_latest_instant(entries: list[dict]) -> dict:
    """Latest fiscal-year-end value and the value about one year earlier.

    - one value per end date: the most recently FILED entry wins (restatements)
    - fiscal year ends = end dates reported in an annual form; if none, any end date
    - prior = the end date 330-400 days before the latest
    - latest_interim = a later quarter-end value, if one exists (reported separately)
    """
    inst = [e for e in entries if not e.get("start") and e.get("end") and e.get("val") is not None]
    if not inst:
        return {}
    by_end: dict[str, dict] = {}
    for e in sorted(inst, key=lambda e: e.get("filed") or ""):
        by_end[e["end"]] = e
    fy_ends = {e["end"] for e in inst if e.get("form") in ANNUAL_FORMS}
    basis = "annual_form"
    if not fy_ends:
        fy_ends, basis = set(by_end), "any_form"
    latest_end = max(fy_ends)
    prior_ends = [d for d in by_end if 330 <= _days(d, latest_end) <= 400]
    prior = by_end[max(prior_ends)] if prior_ends else None
    later = [d for d in by_end if d > latest_end]
    return {"latest": by_end[latest_end], "prior": prior, "basis": basis,
            "latest_interim": by_end[max(later)] if later else None}


def select_duration(entries: list[dict], end: str) -> dict | None:
    """Full-year (330-400 days) duration fact ending on `end`; most recently filed wins."""
    c = [e for e in entries if e.get("start") and e.get("end") == end and e.get("val") is not None
         and 330 <= _days(e["start"], e["end"]) <= 400]
    return max(c, key=lambda e: e.get("filed") or "") if c else None


def sec_filing_url(cik: str, accn: str | None) -> str | None:
    if not accn:
        return None
    return f"https://www.sec.gov/Archives/edgar/data/{int(cik)}/{accn.replace('-', '')}/{accn}-index.htm"


def extract_sec(doc: dict, cik: str) -> dict:
    """Supplier-finance facts from one SEC companyfacts document."""
    found: dict[str, dict] = {}
    related: list[str] = []
    for tax in SEC_TAXONOMIES:
        concepts = (doc.get("facts") or {}).get(tax) or {}
        for name in discover_concepts(concepts):
            unit, entries = sec_entries(concepts[name])
            if entries:
                found[f"{tax}:{name}"] = {"unit": unit, "entries": entries, "role": classify_concept(name)}
        related += [f"{tax}:{n}" for n in related_concepts(concepts)]
    out = {"concepts_found": sorted(found), "related_concepts": related, "programme_tagged": bool(found)}
    if not found:
        return out
    by_role: dict[str, list[str]] = {}
    for c, v in found.items():
        by_role.setdefault(v["role"], []).append(c)

    notes = []
    amount_concept, sel = None, {}
    # total first; else current (+ noncurrent at the same date)
    for role in ("obligation", "obligation_current", "obligation_noncurrent"):
        cands = [(c, select_latest_instant(found[c]["entries"])) for c in sorted(by_role.get(role, []))]
        cands = [(c, s) for c, s in cands if s]
        if cands:
            amount_concept, sel = max(cands, key=lambda cs: cs[1]["latest"]["end"])
            # a total concept that stopped being used loses to a fresher current-only concept
            if role == "obligation":
                cur = [(c, select_latest_instant(found[c]["entries"])) for c in sorted(by_role.get("obligation_current", []))]
                cur = [(c, s) for c, s in cur if s and s["latest"]["end"] > sel["latest"]["end"]]
                if cur:
                    amount_concept, sel = max(cur, key=lambda cs: cs[1]["latest"]["end"])
            break
    if sel:
        lat, pri = sel["latest"], sel["prior"]
        end = lat["end"]
        amt, pamt = lat["val"], pri["val"] if pri else None
        if classify_concept(amount_concept) == "obligation_current":
            for c in by_role.get("obligation_noncurrent", []):
                s2 = select_latest_instant(found[c]["entries"])
                if s2 and s2["latest"]["end"] == end:
                    amt += s2["latest"]["val"]
                    if pamt is not None and s2["prior"]:
                        pamt += s2["prior"]["val"]
                    amount_concept += "+" + c
                    notes.append("amount = current + noncurrent")
        out.update({
            "period_end": end, "currency": found[amount_concept.split("+")[0]]["unit"],
            "obligation_amount": amt, "obligation_prior_amount": pamt,
            "obligation_prior_period_end": pri["end"] if pri else None,
            "amount_concept": amount_concept, "accn": lat.get("accn"), "form": lat.get("form"),
            "filed": lat.get("filed"), "filing_url": sec_filing_url(cik, lat.get("accn")),
        })
        if sel["basis"] != "annual_form":
            notes.append("no annual-form fact; latest value of any form used")
        li = sel["latest_interim"]
        if li:
            out["latest_interim_period_end"], out["latest_interim_amount"] = li["end"], li["val"]
    # roll-forward flows
    ref_end = out.get("period_end")
    if ref_end is None:  # flows only: use the latest full-year flow
        ends = [e["end"] for c in found.values() for e in c["entries"]
                if e.get("start") and 330 <= _days(e["start"], e["end"]) <= 400]
        ref_end = max(ends) if ends else None
        if ref_end:
            out["period_end"] = ref_end
            notes.append("roll-forward flows tagged but no period-end obligation amount")
    if ref_end:
        for role, key in (("increase", "invoices_confirmed_in_period"), ("settlement", "invoices_paid_in_period"),
                          ("net_change", "net_change_in_period")):
            for c in sorted(by_role.get(role, [])):
                d = select_duration(found[c]["entries"], ref_end)
                if d:
                    out[key] = d["val"]
                    out.setdefault("period_start", d["start"])
                    out.setdefault("currency", found[c]["unit"])
                    if not out.get("filing_url"):
                        out["filing_url"] = sec_filing_url(cik, d.get("accn"))
                    break
    for role in ("already_paid", "terms_with", "terms_without"):
        for c in sorted(by_role.get(role, [])):
            s = select_latest_instant(found[c]["entries"]) or {}
            e = s.get("latest") or max(found[c]["entries"], key=lambda e: e.get("end") or "")
            val = e.get("val")
            if role == "already_paid":
                out["amount_suppliers_already_paid"] = val
            else:
                out[f"payment_{role}_programme"] = f"{val} {found[c]['unit']}"
            break
    out["confidence"] = 1.0  # companyfacts only carries standard-taxonomy concepts
    out["notes"] = notes
    return out


# ----------------------------------------------------------------------------- ESEF

def strip_html(s: str) -> str:
    return _WS_RE.sub(" ", html.unescape(_TAG_RE.sub("", s))).strip()


def find_text_mention(text: str, width: int = 200) -> dict | None:
    """First hit of the strongest key phrase in (HTML) text -> {phrase, snippet} or None."""
    if not text or len(text) < 12:
        return None
    plain = strip_html(text) if "<" in text else _WS_RE.sub(" ", text)
    for label, rx in TEXT_RES:
        m = rx.search(plain)
        if m:
            a = max(0, m.start() - width // 3)
            return {"phrase": label, "snippet": plain[a:a + width]}
    return None


_PHRASE_RANK = {label: i for i, (label, _) in enumerate(TEXT_PHRASES)}


def _is_number(v) -> bool:
    try:
        float(v)
        return True
    except (TypeError, ValueError):
        return False


def extract_esef(doc: dict) -> dict:
    """Supplier-finance facts and a text-mention flag from one xBRL-JSON report."""
    facts = doc.get("facts") or {}
    numeric: dict[str, list[dict]] = {}
    text_concepts: dict[str, str] = {}
    related: set[str] = set()
    mention = None
    for fid, f in facts.items():
        dims = f.get("dimensions") or {}
        concept, val = dims.get("concept"), f.get("value")
        if not concept or val is None:
            continue
        extra = {k: v for k, v in dims.items() if k not in ("concept", "entity", "period", "unit", "language")}
        member_hit = any(SFA_NAME_RE.search(local_name(str(v))) for v in extra.values())
        is_sfa = bool(SFA_NAME_RE.search(local_name(concept))) or member_hit
        if not is_sfa and RELATED_NAME_RE.search(local_name(concept)):
            related.add(concept)
        if dims.get("unit") and _is_number(val):
            if is_sfa:
                start, end = E.parse_period(dims["period"]) if dims.get("period") else (None, None)
                numeric.setdefault(concept, []).append({
                    "fact_id": fid, "val": float(val), "unit": dims["unit"], "extra_dims": extra,
                    "start": start.isoformat() if start else None, "end": end.isoformat() if end else None})
            continue
        if not isinstance(val, str):
            continue
        if is_sfa:
            text_concepts.setdefault(concept, fid)
        m = find_text_mention(val)
        if m:
            m["fact_id"], m["concept"] = fid, concept
            if mention is None or _PHRASE_RANK[m["phrase"]] < _PHRASE_RANK[mention["phrase"]]:
                mention = m
    concepts = sorted(set(numeric) | set(text_concepts))
    out = {"concepts_found": concepts, "related_concepts": sorted(related),
           "programme_tagged": bool(concepts), "numeric_tagged": bool(numeric),
           "text_mention_found": mention is not None,
           "text_mention_phrase": mention["phrase"] if mention else None,
           "text_mention_snippet": mention["snippet"] if mention else None,
           "text_mention_fact_id": mention["fact_id"] if mention else None,
           "text_mention_concept": mention["concept"] if mention else None,
           "notes": []}
    if not concepts:
        return out
    out["confidence"] = 1.0 if all(c.startswith("ifrs-full:") for c in concepts) else 0.8
    if not numeric:
        out["notes"].append("only a text-block concept is tagged; no amount in structured data")
        return out

    def pick(role_names, want_latest=True):
        """Prefer facts without extra dimensions; latest end date; returns (concept, latest, prior)."""
        best = None
        for c in sorted(numeric):
            if classify_concept(c) not in role_names:
                continue
            fs = [x for x in numeric[c] if x["end"]]
            plain = [x for x in fs if not x["extra_dims"]] or fs
            if not plain:
                continue
            lat = max(plain, key=lambda x: x["end"])
            pri = [x for x in plain if 330 <= _days(x["end"], lat["end"]) <= 400
                   and x["extra_dims"] == lat["extra_dims"] and (x["start"] is None) == (lat["start"] is None)]
            cand = (c, lat, max(pri, key=lambda x: x["end"]) if pri else None)
            if best is None or lat["end"] > best[1]["end"]:
                best = cand
        return best

    ob = pick({"obligation", "obligation_current"})
    if ob:
        c, lat, pri = ob
        out.update({"amount_concept": c, "period_end": lat["end"], "period_start": lat["start"],
                    "currency": lat["unit"].split(":")[-1], "obligation_amount": lat["val"],
                    "obligation_prior_amount": pri["val"] if pri else None,
                    "obligation_prior_period_end": pri["end"] if pri else None})
        if lat["extra_dims"]:
            out["notes"].append(f"amount fact carries dimensions {lat['extra_dims']}")
    ap = pick({"already_paid"})
    if ap:
        out["amount_suppliers_already_paid"] = ap[1]["val"]
    for role in ("terms_with", "terms_without"):
        t = pick({role})
        if t:
            out[f"payment_{role}_programme"] = f"{t[1]['val']} {t[1]['unit']}"
    if not ob:
        out["notes"].append("numeric supplier-finance concept tagged but no carrying-amount role recognised")
    return out


# ----------------------------------------------------------------------------- build

FIELDS = ["rank", "company_id", "name", "country", "source", "sources_checked", "programme_tagged", "status",
          "period_start", "period_end", "currency", "obligation_amount", "obligation_prior_amount",
          "obligation_prior_period_end", "amount_suppliers_already_paid", "invoices_confirmed_in_period",
          "invoices_paid_in_period", "net_change_in_period", "latest_interim_period_end",
          "latest_interim_amount", "payment_terms_with_programme", "payment_terms_without_programme",
          "amount_concept", "concepts_found", "related_concepts", "text_mention_found", "text_mention_phrase",
          "text_mention_snippet", "text_mention_fact_id", "text_mention_concept", "source_url", "filing_url",
          "source_type", "retrieved_at", "extraction_method", "confidence", "notes"]


def _split(v) -> list[str]:
    return [x.strip() for x in str(v or "").split("|") if x.strip() and x.strip().lower() != "nan"]


def _load(url: str):
    """(json, retrieved_at, error). Cached files are read from disk; a missing one is fetched once."""
    try:
        r = fetch(url, retries=2)
        return r.json(), r.retrieved_at, None
    except Exception as e:  # logged by the client
        return None, None, f"{type(e).__name__}"


def build_record(row: dict, esef_sel: pd.DataFrame, today: date | None = None) -> dict:
    today = today or date.today()
    rec = {k: None for k in FIELDS}
    rec.update({"rank": int(row["rank"]) if str(row.get("rank") or "").strip() else None, "company_id": row["company_id"], "name": row["name"],
                "country": row.get("country"), "extraction_method": "xbrl_tags"})
    notes, checked = [], []
    sec_best, sec_meta = None, None
    for cik in _split(row.get("cik")):
        url = SEC_FACTS_URL.format(cik=cik.zfill(10))
        doc, ts, err = _load(url)
        if doc is None:
            notes.append(f"SEC companyfacts unavailable for CIK {cik} ({err})")
            continue
        checked.append("sec")
        ex = extract_sec(doc, cik)
        better = sec_best is None or (ex["programme_tagged"] and (
            not sec_best["programme_tagged"] or (ex.get("period_end") or "") > (sec_best.get("period_end") or "")))
        if better:
            sec_best, sec_meta = ex, {"source_url": url, "retrieved_at": ts, "source_type": "sec_xbrl_companyfacts"}
    esef_best, esef_meta = None, None
    for lei in _split(row.get("lei")):
        if lei not in esef_sel.index:
            continue
        f = esef_sel.loc[lei]
        url = E.BASE + f["json_url"]
        doc, ts, err = _load(url)
        if doc is None:
            notes.append(f"ESEF xBRL-JSON unavailable for LEI {lei} ({err})")
            continue
        checked.append("esef")
        ex = extract_esef(doc)
        ex.setdefault("period_end", None)
        ex["filing_period_end"] = f["period_end"]
        human = f.get("viewer_url") or f.get("report_url")
        meta = {"source_url": url, "retrieved_at": ts, "source_type": "esef_xbrl_json",
                "filing_url": E.BASE + human if isinstance(human, str) and human else None}
        if esef_best is None or (ex["programme_tagged"] and not esef_best["programme_tagged"]):
            esef_best, esef_meta = ex, meta
    rec["sources_checked"] = "|".join(dict.fromkeys(checked)) or None

    if sec_best is None and esef_best is None:
        rec.update({"source": "none", "status": "no_structured_source", "programme_tagged": False})
        notes.append("not in SEC or ESEF structured data; says nothing about whether a programme exists")
        rec["notes"] = "; ".join(notes)
        return rec

    # primary source: numeric tags (SEC, then ESEF) > ESEF text concept > whatever exists
    if sec_best and sec_best["programme_tagged"]:
        prim, meta, src = sec_best, sec_meta, "sec"
    elif esef_best and esef_best["programme_tagged"]:
        prim, meta, src = esef_best, esef_meta, "esef"
    elif sec_best:
        prim, meta, src = sec_best, sec_meta, "sec"
    else:
        prim, meta, src = esef_best, esef_meta, "esef"
    rec["source"] = src
    rec.update(meta)
    for k in ("period_start", "period_end", "currency", "obligation_amount", "obligation_prior_amount",
              "obligation_prior_period_end", "amount_suppliers_already_paid", "invoices_confirmed_in_period",
              "invoices_paid_in_period", "net_change_in_period", "latest_interim_period_end",
              "latest_interim_amount", "amount_concept", "confidence"):
        if prim.get(k) is not None:
            rec[k] = prim[k]
    rec["payment_terms_with_programme"] = prim.get("payment_terms_with_programme")
    rec["payment_terms_without_programme"] = prim.get("payment_terms_without_programme")
    if prim.get("filing_url"):
        rec["filing_url"] = prim["filing_url"]
    rec["concepts_found"] = "|".join(prim["concepts_found"]) or None
    rel = sorted(set((sec_best or {}).get("related_concepts", [])) | set((esef_best or {}).get("related_concepts", [])))
    rec["related_concepts"] = "|".join(rel) or None
    rec["programme_tagged"] = bool(prim["programme_tagged"])
    numeric = prim["programme_tagged"] and (src == "sec" or prim.get("numeric_tagged"))
    rec["status"] = "tagged" if numeric else ("tagged_text_only" if prim["programme_tagged"] else "not_tagged")
    notes += prim.get("notes", [])
    if esef_best:  # the text signal is always carried, also when SEC is the primary source
        for k in ("text_mention_found", "text_mention_phrase", "text_mention_snippet", "text_mention_fact_id",
                  "text_mention_concept"):
            rec[k] = esef_best.get(k)
        if src != "esef":
            notes.append(f"text mention fields come from the ESEF filing {esef_meta['source_url']}")
        if esef_best.get("text_mention_phrase") == "confirming":
            notes.append("text mention is the word 'confirming' only: weak signal")
        if rec["period_end"] is None and src == "esef":
            rec["period_end"] = esef_best.get("filing_period_end")
            notes.append("period_end is the filing's reporting period end")
    if rec["status"] == "not_tagged":
        rec["confidence"] = None
        notes.append("no supplier-finance concept tagged; NOT evidence that no programme exists")
    if rel:
        notes.append("factoring concepts found but not counted (may be receivables-side)")
    if rec["status"] == "tagged" and rec["period_end"] and _days(rec["period_end"], today.isoformat()) > 550:
        notes.append("latest tagged period is older than 18 months: tagging may have stopped")
    if rec["status"] == "tagged" and rec["obligation_amount"] is None:
        notes.append("no period-end amount tagged")
    if src == "sec" and rec["status"] == "tagged":
        notes.append("payment terms are not available in SEC company facts (numeric standard facts only)")
    rec["notes"] = "; ".join(dict.fromkeys(notes)) or None
    return rec


def _meta(recs: list[dict], t0: float) -> dict:
    usage = Counter(c for r in recs for c in _split(r["concepts_found"]))
    return {"generated_at": now_iso(), "extractor": "sfa-a (deterministic, XBRL tags only)",
            "runtime_seconds": round(time.monotonic() - t0, 1), "companies": len(recs),
            "status_counts": dict(Counter(r["status"] for r in recs)),
            "source_counts": dict(Counter(r["source"] for r in recs)),
            "text_mention_found": int(sum(bool(r["text_mention_found"]) for r in recs)),
            "concept_usage": dict(usage.most_common()),
            "interpretation": "not_tagged is NOT 'no programme'; see module docstring"}


def run() -> tuple[pd.DataFrame, dict]:
    t0 = time.monotonic()
    top = pd.read_csv(TOP200, dtype=str).fillna("")
    sel = E.select_filings(E.load_index()).set_index("lei")
    recs = [build_record(r, sel) for r in top.to_dict("records")]
    df = pd.DataFrame(recs, columns=FIELDS)
    meta = _meta(recs, t0)
    OUT_JSON.write_text(json.dumps({"meta": meta, "records": recs}, indent=1, ensure_ascii=False, default=str))
    df.to_csv(OUT_CSV, index=False)
    return df, meta


def universe_row(rec: dict) -> dict:
    """Slim one-row-per-company view of a full record for the universe table."""
    return {"company_id": rec["company_id"], "name": rec["name"], "status": rec["status"],
            "source": rec["source"], "amount": rec["obligation_amount"], "currency": rec["currency"],
            "period_end": rec["period_end"],
            "concept": rec["amount_concept"] or rec["concepts_found"] or rec["text_mention_concept"],
            "source_url": rec["source_url"], "retrieved_at": rec["retrieved_at"]}


def run_universe() -> tuple[pd.DataFrame, dict]:
    """Same extractor over every company in the universe. Cache first; missing files fetched politely."""
    t0 = time.monotonic()
    uni = pd.read_parquet(UNIVERSE, columns=["company_id", "name", "country", "cik", "lei"])
    uni = uni.astype("string").fillna("")
    sel = E.select_filings(E.load_index()).set_index("lei")
    recs = [build_record(r, sel) for r in uni.to_dict("records")]
    df = pd.DataFrame([universe_row(r) for r in recs], columns=UNIV_FIELDS)
    meta = _meta(recs, t0)
    meta["tagged_with_amount"] = int(((df["status"] == "tagged") & df["amount"].notna()).sum())
    UNIV_JSON.write_text(json.dumps({"meta": meta}, indent=1, ensure_ascii=False, default=str))
    df.to_csv(UNIV_CSV, index=False)
    return df, meta


def main(argv: list[str] | None = None):
    import argparse
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--universe", action="store_true",
                    help="run over data/processed/universe.parquet and write sfa_universe_tags.csv")
    args = ap.parse_args(argv)
    _, meta = run_universe() if args.universe else run()
    print(json.dumps(meta, indent=1))


if __name__ == "__main__":
    main()
