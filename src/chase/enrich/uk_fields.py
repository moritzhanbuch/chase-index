"""UK payment-practice filings: every useful field beyond payment speed, as entity and group features.

Run      : python -m chase.enrich.uk_fields
Inputs   : data/processed/uk_payment_practices.parquet   (one row per statutory report)
           data/processed/uk_entity_latest.parquet        (latest usable report per entity)
           data/processed/uk_entity_group_map.parquet     (entity -> ranked group)
           data/processed/companies.parquet               (rank, excluded_reason)
           data/interim/uk_dispute_llm.csv                (optional: text_hash, label, reason; labels
                                                           assigned by an LLM reading the dispute text)
Outputs  : data/processed/uk_entity_features.parquet/.csv  one row per CURRENT entity
           data/processed/uk_group_features.parquet/.csv   one row per company_id with current entities
           data/processed/uk_field_signals.csv             one row per (company_id, signal_type)
           evals/gold/uk_dispute_sample.csv                blind hand-check sample for QA (no labels)
           data/interim/uk_dispute_sample_key.csv          the answer key for that sample
           evals/reports/uk_fields.md                      field audit, counts, rubric, agreement

No network. Deterministic. "Current" entity = has a usable report and the latest one is not stale
(same definition as the rest of the project).

Dispute-process rubric (four levels, from the supplier's point of view)
----------------------------------------------------------------------
The statutory report asks each company to describe its dispute resolution process in free text.
The rubric asks two questions a supplier with a stuck invoice would ask: WHERE do I go, and WHAT
happens next?

  named_route  The text tells the supplier where to go (an email address, phone number, portal,
               helpdesk, or a named team or role such as accounts payable, the buyer, the contract
               manager) AND what happens next (a stated timescale, or an escalation step beyond the
               first contact, including mediation / adjudication / arbitration).
  basic        Only one of the two: a contact, or concrete described steps (invoice put on hold,
               credit note requested, query logged), but not both where-to-go and what-happens-next.
  boilerplate  A generic statement with neither, e.g. "disputes are resolved in line with contract
               terms", "we aim to resolve disputes amicably", "discussion with the supplier".
  none         Empty, "n/a", "none", a bare web link, or a text that does not describe a dispute
               process at all.

Reading conventions used for the LLM labels (the regex cannot apply all of them):
  - "If AP cannot resolve it, it goes to X" counts as an escalation step. An unconditional internal
    hand-off ("AP passes disputes to sourcing") does not.
  - A contract clause with timescales and mediation/arbitration but no contact is `basic`.
  - A team or role counts as a route even without an address; "the relevant department" does not.

Two classifiers use the same rubric:
  regex_rules  deterministic keyword rules (classify_dispute_text), applied to every current entity
  llm_read     a language model read each distinct text for entities in the top-300 ranked groups;
               labels are stored by text hash in data/interim/uk_dispute_llm.csv. Where an LLM label
               exists it wins.

The rubric scores what the filing says, not how the company behaves. A short text is not evidence
of a poor process, only of a thin disclosure.

Payment-terms change direction
------------------------------
Text signal (terms_changed_direction): rules on the "Payment terms have changed" free text.
  1. a "from X [days] to Y [days]" pair decides: Y > X longer, Y < X shorter
  2. otherwise keywords: extend / increase / longer -> longer; reduce / shorten / decrease -> shorter
  3. both or a non-length change (payment-run frequency, case by case, negotiated individually,
     correction of an earlier report, "not changed") -> other
  4. nothing matches -> unknown
Number signal (terms_numbers_direction): shortest standard period, longest standard period and
maximum contractual period in the latest report against the report about one year earlier:
longer / shorter / mixed / unchanged, null when there is no earlier report. Both are stored; they
are never merged.

Personal data: the dispute texts are public and sometimes contain employee names or mailboxes.
This module never extracts names; the only place such text can appear is the trimmed raw text.
"""
from __future__ import annotations

import hashlib
import re
import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[3]
PROCESSED = ROOT / "data" / "processed"
INTERIM = ROOT / "data" / "interim"
LLM_LABELS = INTERIM / "uk_dispute_llm.csv"
SAMPLE = ROOT / "evals" / "gold" / "uk_dispute_sample.csv"
SAMPLE_KEY = INTERIM / "uk_dispute_sample_key.csv"
REPORT_MD = ROOT / "evals" / "reports" / "uk_fields.md"

SOURCE_TYPE = "uk_ppr_statutory_report"
EXTRACTION_METHOD = "official_csv_export+uk_fields_rules_v1"
LABELS = ["named_route", "basic", "boilerplate", "none"]
WEAK_LABELS = {"boilerplate", "none"}
SAMPLE_SEED = 20261117
TOP_N_LLM = 300
# Share of invoices not paid due to dispute, value-weighted across a group's current UK entities.
# 10% is a round number at roughly the 92nd percentile of current entities and the 90th percentile
# of matched groups (exact percentiles are printed in evals/reports/uk_fields.md).
DISPUTE_SHARE_HIGH = 10.0
# A group's dispute disclosure is "weak" when at least half its current entities are boilerplate/none.
WEAK_SHARE_MIN = 0.5
QA_HEADING = "## Independent QA of the dispute rubric"


# --------------------------------------------------------------------------- text helpers

def normalise_text(text) -> str:
    if text is None or (isinstance(text, float) and np.isnan(text)) or text is pd.NA:
        return ""
    return " ".join(str(text).lower().split())


def text_hash(text) -> str:
    return hashlib.sha1(normalise_text(text).encode("utf-8")).hexdigest()[:16]


def trim(text, n: int):
    if text is None or text is pd.NA or (isinstance(text, float) and np.isnan(text)):
        return None
    t = " ".join(str(text).split())
    return t if len(t) <= n else t[: n - 1].rstrip() + "…"


# --------------------------------------------------------------------------- dispute rubric (regex)

_NONE_EXACT = {"", "n/a", "na", "n.a.", "n.a", "none", "nil", "no", "not applicable", "-", ".", "..", "tbc",
               "no change", "not defined", "see previous statements", "as above", "no disputes", "0"}
_NOT_A_PROCESS = re.compile(
    r"^(there (are|were|have been) no disputes|no disputes?( (in|during) (the|this) (reporting )?period)?|"
    r"we (do not|don't) have (a|any)( formal)? (dispute )?(resolution )?(process|procedure|policy)|"
    r"no formal (dispute )?(resolution )?(process|procedure|policy))\b[^.]{0,40}\.?$")
# WHERE: a channel or a named team / role the supplier can go to.
_ROUTE = re.compile(
    r"\[email removed\]|\[phone removed\]|"   # public copy: contact details are redacted, the route still counts
    r"[\w.+-]+@[\w-]+\.[\w.-]+|\b(?:tel|telephone|phone|call)\b|\b0\d{2,4}[\s-]?\d{3,4}[\s-]?\d{3,4}\b|"
    r"\b(?:portal|help\s?desk|help\s?line|hotline|mailbox|inbox|e-?mail(?:ing|ed)?|website|www\.|https?://|"
    r"service desk|shared services?|ticket(?:ing)?|query form)\b|"
    r"\b(?:accounts? payable|a/?p (?:team|department|dept|manager|function)|purchase ledger|bought ledger|payables? team|"
    r"finance (?:team|department|dept|function|manager|director|controller|business partner|contact)|"
    r"financial controller|credit control|procurement(?: team| department| manager| lead)?|purchasing (?:team|department|manager)|"
    r"buyer|category manager|contract manager|commercial (?:team|manager|director|department)|"
    r"quantity surveyor|account manager|relationship manager|supplier relations?|vendor management|"
    r"point of contact|usual contact|business contact|named contact|budget holder|"
    r"requisitioner|purchaser|site manager|project manager|operations manager|store manager|"
    r"contact (?:us|the|their|your|our))\b")
# WHAT NEXT (a): a stated timescale.
_TIMESCALE = re.compile(
    r"\b(?:within|in|after|under|up to|maximum of|no (?:later|more) than)\s+(?:\w+\s+){0,2}?"
    r"(?:\d+|one|two|three|four|five|six|seven|ten|fourteen|thirty)\s*\(?\d*\)?\s*"
    r"(?:working |business |calendar |further )?(?:days?|hours?|weeks?|months?)\b|"
    r"\b\d+\s*(?:working |business |calendar )?(?:days?|hours?)\b(?! (?:payment )?terms)|\b(?:24|48|72)\s?h(?:ou)?rs?\b")
# WHAT NEXT (b): an escalation step beyond first contact.
_ESCALATION = re.compile(
    r"\bescalat\w*|\bmediat\w+|\badjudicat\w+|\barbitrat\w+|\bexpert determination|\bombudsman|"
    r"\bsmall business commissioner|\balternative dispute resolution|\badr\b|\blitigation|\bcourts?\b|"
    r"\b(?:referred|refer|passed|raised|taken) to (?:the |a |our |their )?(?:senior|director|board|head of|"
    r"cfo|chief|finance director|managing director|management|legal)|"
    r"\bif (?:this|the dispute|the matter|the issue|it|a resolution|agreement|resolution)?\s*"
    r"(?:is |remains |are |can ?not be |cannot be |still |fails? to be )?"
    r"(?:not |un)?(?:resolved|agreed|settled|reached|successful)")
# A described step without a channel.
_STEP = re.compile(
    r"\b(?:investigat\w+|review\w*|discuss\w*|negotiat\w+|contact\w*|notif\w+|inform\w*|rais\w+|quer\w+|"
    r"liais\w+|communicat\w+|log(?:ged|s)?|record\w*|credit note|on hold|placed on|meeting|dialogue|"
    r"correspond\w+|approv\w+|reconcil\w+|respond\w*|engage\w*|resolv\w+ (?:by|with|through|via|directly)|work with)\b")


def dispute_features(text) -> dict:
    t = normalise_text(text)
    return {
        "route": bool(_ROUTE.search(t)),
        "timescale": bool(_TIMESCALE.search(t)),
        "escalation": bool(_ESCALATION.search(t)),
        "step": bool(_STEP.search(t)),
    }


def classify_dispute_text(text) -> str:
    """Deterministic rubric classifier. See module docstring for the four levels."""
    t = normalise_text(text)
    if t.strip(" .-") in _NONE_EXACT or _NOT_A_PROCESS.match(t):
        return "none"
    f = dispute_features(t)
    if f["route"] and (f["timescale"] or f["escalation"]):
        return "named_route"
    if f["route"] or f["escalation"] or f["timescale"] or f["step"]:
        return "basic"
    return "boilerplate"


# --------------------------------------------------------------------------- terms change direction

_NUM = r"(\d{1,3})"
_PAIR = re.compile(
    rf"\bfrom\s+(?:\w+\s+){{0,5}}?{_NUM}\s*-?\s*(?:days?)?\b[^.;]{{0,60}}?\bto\s+(?:\w+\s+){{0,5}}?{_NUM}\s*-?\s*days?"
    rf"|\b{_NUM}\s*days?(?:\s+\w+){{0,3}}?\s+to\s+(?:\w+\s+){{0,3}}?{_NUM}\s*days?")
_PAIR_REV = re.compile(
    rf"\bto\s+(?:\w+\s+){{0,4}}?{_NUM}\s*days?\s+from\s+{_NUM}\b(?!\s*(?:st|nd|rd|th)\b)"
    rf"|\b{_NUM}\s*days?\b[^;]{{0,70}}?\b(?:rather than|previously|instead of)\s+{_NUM}\b")
_RANGE = re.compile(r"\brange of\b|\bbetween\b|\branging\b")
_NEAR = r"(?:terms?|days|payment period)"
_LONGER = re.compile(
    rf"(?:\bextend\w*|\bextension|\bincreas\w+|\blonger\b|\blengthen\w*)(?=[^.]{{0,60}}\b{_NEAR}\b)"
    rf"|\b{_NEAR}\b[^.]{{0,60}}(?:\bextend\w*|\bextension|\bincreas\w+|\blonger\b|\blengthen\w*)"
    r"|\bextension on\b|\bextending\b|\bdelay payments\b"
    r"|\bmov(?:e|ed|ing)\b[^.]{0,30}\bto (?:6\d|[7-9]\d|1\d\d)\b")
_SHORTER = re.compile(
    rf"(?:\breduc\w+|\bshorten\w*|\bshorter\b|\bdecreas\w+)(?=[^.]{{0,60}}\b{_NEAR}\b)"
    rf"|\b{_NEAR}\b[^.]{{0,60}}(?:\breduc\w+|\bshorten\w*|\bshorter\b|\bdecreas\w+)"
    r"|\bmoved to max\b|\breduced any\b")
_OTHER = re.compile(r"case[- ]by[- ]case|individual basis|negotiat|payment (?:cycles?|runs?)|weekly|daily|"
                    r"\berror\b|incorrect|not changed|no unilateral|set off|as agreed|mutual agreement|"
                    r"renewal|aligned?|standardis|simplified|updated|amended|changed|changes|moved?|"
                    r"new payment term|introduced")


def terms_direction_from_text(text) -> str | None:
    """'longer' / 'shorter' / 'other' / 'unknown' for a non-empty text; None when there is no text."""
    t = normalise_text(text)
    if not t:
        return None
    pairs: list[tuple[int, int]] = []
    if not _RANGE.search(t):
        for m in _PAIR.finditer(t):
            a, b = (m.group(1), m.group(2)) if m.group(1) else (m.group(3), m.group(4))
            pairs.append((int(a), int(b)))
        for m in _PAIR_REV.finditer(t):
            new, old = (m.group(1), m.group(2)) if m.group(1) else (m.group(3), m.group(4))
            pairs.append((int(old), int(new)))
    pairs = [(a, b) for a, b in pairs if a != b]
    if pairs:
        ups = sum(b > a for a, b in pairs)
        downs = sum(b < a for a, b in pairs)
        if ups and not downs:
            return "longer"
        if downs and not ups:
            return "shorter"
        return "other"
    if re.search(r"\b(?:not|no) (?:been )?chang|\berror\b|incorrect", t):
        return "other"
    longer, shorter = bool(_LONGER.search(t)), bool(_SHORTER.search(t))
    if longer and not shorter:
        return "longer"
    if shorter and not longer:
        return "shorter"
    if longer and shorter:
        return "other"
    if _OTHER.search(t):
        return "other"
    return "unknown"


def numbers_direction(deltas: list[float | None]) -> str | None:
    """Direction from latest-minus-year-earlier deltas of the three term-length fields."""
    d = [x for x in deltas if x is not None and not pd.isna(x)]
    if not d:
        return None
    up, down = any(x > 0 for x in d), any(x < 0 for x in d)
    if up and down:
        return "mixed"
    return "longer" if up else "shorter" if down else "unchanged"


# --------------------------------------------------------------------------- payment codes

def payment_code_name(text) -> str | None:
    """Which code the free text names. Null when the company says it is in no code."""
    t = normalise_text(text)
    if t in {"", "no", "n/a", "na", "none", "nil", "not applicable", ".", "..", "-"}:
        return None
    if re.search(r"fair\s*payment\s*code|\bfpc\b", t):
        return "fair_payment_code"
    if re.search(r"prompt\s*pay|\bppc\b", t):
        return "prompt_payment_code"
    return "other_or_unclear"


# --------------------------------------------------------------------------- entity features

def _b(s: pd.Series) -> pd.Series:
    return s.astype("boolean")


def load_llm_labels(path: Path = LLM_LABELS) -> pd.DataFrame:
    if not path.exists():
        return pd.DataFrame(columns=["text_hash", "label", "reason"])
    d = pd.read_csv(path, dtype=str).drop_duplicates("text_hash")
    bad = set(d["label"]) - set(LABELS)
    if bad:
        raise ValueError(f"unknown labels in {path}: {bad}")
    return d


def build_entity_features(reports: pd.DataFrame, entities: pd.DataFrame, llm: pd.DataFrame | None = None) -> pd.DataFrame:
    cur = entities[entities["has_usable_report"].fillna(False).astype(bool)
                   & ~entities["latest_is_stale"].fillna(True).astype(bool)]
    rep = reports.set_index("report_id")
    latest = rep.loc[cur["latest_report_id"].astype("int64")].reset_index()
    out = pd.DataFrame({
        "company_number": latest["company_number"].to_numpy(),
        "company_name": latest["company_name"].to_numpy(),
        "report_id": latest["report_id"].astype("int64").to_numpy(),
        "period_start": latest["period_start"].to_numpy(),
        "period_end": latest["period_end"].to_numpy(),
        "filing_date": latest["filing_date"].to_numpy(),
        "policy_regime": latest["policy_regime"].to_numpy(),
        "value_paid_total_gbp": latest["value_paid_total_gbp"].to_numpy(),
        "pct_paid_late": latest["pct_paid_late"].to_numpy() if "pct_paid_late" in latest else np.nan,
    })
    out["offers_scf"] = _b(latest["offers_supply_chain_finance"]).to_numpy()
    out["offers_einvoicing"] = _b(latest["offers_einvoicing"]).to_numpy()
    out["in_payment_code"] = _b(latest["participates_in_payment_codes"]).to_numpy()
    out["payment_code_name"] = [payment_code_name(t) for t in latest["payment_codes_text"]]
    out["pay_to_stay_policy"] = _b(latest["policy_covers_supplier_list_charges"]).to_numpy()
    out["pay_to_stay_charged"] = _b(latest["charged_for_supplier_list"]).to_numpy()
    out["pct_not_paid_due_to_dispute"] = latest["pct_not_paid_due_to_dispute"].to_numpy()

    # ---- comparison with the report about one year earlier (same yoy report the trend uses)
    yoy_id = cur["yoy_report_id"].to_numpy()
    has_yoy = pd.notna(yoy_id)
    out["yoy_report_id"] = pd.array(yoy_id, dtype="Int64")
    yoy = rep.reindex(pd.Index([int(x) if pd.notna(x) else -1 for x in yoy_id]))
    out["yoy_period_end"] = yoy["period_end"].to_numpy()
    out["yoy_source_url"] = yoy["source_url"].to_numpy()
    for col, name in (("shortest_standard_payment_period_days", "shortest_standard_days"),
                      ("longest_standard_payment_period_days", "longest_standard_days"),
                      ("max_contractual_payment_period_days", "max_contractual_days")):
        out[name] = latest[col].to_numpy()
        out[f"{name}_delta_yoy"] = latest[col].to_numpy() - yoy[col].to_numpy()
    out["terms_numbers_direction"] = [
        numbers_direction([a, b, c]) if h else None
        for a, b, c, h in zip(out["shortest_standard_days_delta_yoy"], out["longest_standard_days_delta_yoy"],
                              out["max_contractual_days_delta_yoy"], has_yoy)]

    txt = latest["payment_terms_changed_text"]
    out["terms_changed_latest"] = txt.notna().astype("boolean").to_numpy()
    out["terms_changed_direction"] = [terms_direction_from_text(t) for t in txt]
    out["terms_changed_text"] = [trim(t, 300) for t in txt]
    out["suppliers_notified_text"] = [trim(t, 300) for t in latest["suppliers_notified_of_changes_text"]]

    for now_col, src_col, name in (("offers_scf", "offers_supply_chain_finance", "scf_started"),
                                   ("offers_einvoicing", "offers_einvoicing", "einvoicing_started")):
        before = yoy[src_col].to_numpy(dtype=object)
        now = out[now_col].to_numpy(dtype=object)
        vals = []
        for n, b, h in zip(now, before, has_yoy):
            if n is pd.NA or n is None:
                vals.append(pd.NA)
            elif not n:
                vals.append(False)
            elif not h or b is pd.NA or b is None:
                vals.append(pd.NA)          # offered now, nothing to compare against
            else:
                vals.append(not bool(b))
        out[name] = pd.array(vals, dtype="boolean")

    # ---- dispute process
    dt = latest["dispute_resolution_process_text"]
    out["dispute_text_hash"] = [text_hash(t) for t in dt]
    out["dispute_process_text"] = [trim(t, 600) for t in dt]
    out["dispute_process_quality_regex"] = [classify_dispute_text(t) for t in dt]
    llm = load_llm_labels() if llm is None else llm
    lab = dict(zip(llm["text_hash"], llm["label"]))
    out["dispute_process_quality_llm"] = out["dispute_text_hash"].map(lab)
    has_llm = out["dispute_process_quality_llm"].notna()
    out["dispute_process_quality"] = out["dispute_process_quality_llm"].where(has_llm, out["dispute_process_quality_regex"])
    out["dispute_process_quality_method"] = np.where(has_llm, "llm_read", "regex_rules")

    # ---- provenance (rule 7)
    out["source_url"] = latest["source_url"].to_numpy()
    out["source_type"] = SOURCE_TYPE
    out["retrieved_at"] = latest["retrieved_at"].to_numpy()
    out["extraction_method"] = EXTRACTION_METHOD
    # Reported flags and numbers are copied from the official export (1.0). Derived labels carry
    # their own method column; this is the confidence of the copied fields.
    out["confidence"] = 1.0
    return out.sort_values("company_number").reset_index(drop=True)


# --------------------------------------------------------------------------- group features

def _top_entity(g: pd.DataFrame, mask: pd.Series) -> pd.Series | None:
    """The entity showing a feature that paid the largest invoice value (ties: lowest number)."""
    h = g[mask.fillna(False).astype(bool)]
    if not len(h):
        return None
    return h.sort_values(["value_paid_total_gbp", "company_number"], ascending=[False, True], na_position="last").iloc[0]


def _names(h: pd.DataFrame, extra: str | None = None, cap: int = 8) -> str | None:
    if not len(h):
        return None
    h = h.sort_values(["value_paid_total_gbp", "company_number"], ascending=[False, True], na_position="last")
    items = [f"{n} ({e})" if extra else n for n, e in zip(h["company_name"], h[extra] if extra else h["company_name"])]
    more = f" (+{len(items) - cap} more)" if len(items) > cap else ""
    return " | ".join(items[:cap]) + more


def build_group_features(ent: pd.DataFrame, group_map: pd.DataFrame) -> pd.DataFrame:
    m = group_map[["company_number", "company_id", "group_name"]].drop_duplicates("company_number")
    j = ent.merge(m, on="company_number", how="inner")
    rows = []
    for cid, g in j.groupby("company_id", sort=True):
        n = len(g)
        row: dict = {"company_id": cid, "group_name": g["group_name"].iloc[0], "uk_entities_n": n,
                     "uk_period_start_min": str(g["period_start"].min()), "uk_period_end_max": str(g["period_end"].max()),
                     "uk_latest_filing_date": str(g["filing_date"].max())}

        def feat(prefix: str, mask: pd.Series, with_share: bool = True) -> None:
            mk = mask.fillna(False).astype(bool)
            row[f"{prefix}_n"] = int(mk.sum())
            if with_share:
                row[f"{prefix}_share"] = round(float(mk.mean()), 4)
            top = _top_entity(g, mk)
            row[f"{prefix}_evidence_entity"] = None if top is None else top["company_name"]
            row[f"{prefix}_evidence_url"] = None if top is None else top["source_url"]
            row[f"{prefix}_observed_at"] = None if top is None else str(top["filing_date"])

        feat("scf_offered", g["offers_scf"])
        feat("einvoicing_offered", g["offers_einvoicing"])
        feat("scf_started", g["scf_started"], with_share=False)
        feat("einvoicing_started", g["einvoicing_started"], with_share=False)
        row["scf_started_any"] = row["scf_started_n"] > 0
        row["einvoicing_started_any"] = row["einvoicing_started_n"] > 0
        feat("payment_code", g["in_payment_code"])
        codes = sorted(set(g["payment_code_name"].dropna()))
        row["payment_code_names"] = ";".join(codes) if codes else None
        pts = g["pay_to_stay_policy"].fillna(False).astype(bool) | g["pay_to_stay_charged"].fillna(False).astype(bool)
        feat("pay_to_stay", pts, with_share=False)
        row["pay_to_stay_any"] = row["pay_to_stay_n"] > 0
        row["pay_to_stay_charged_n"] = int(g["pay_to_stay_charged"].fillna(False).astype(bool).sum())

        ch = g["terms_changed_latest"].fillna(False).astype(bool)
        row["terms_changed_n"] = int(ch.sum())
        row["terms_changed_entities"] = _names(g[ch], "terms_changed_direction")
        for d in ("longer", "shorter", "other"):
            mask = ch & g["terms_changed_direction"].isin([d] if d != "other" else ["other", "unknown"])
            feat(f"terms_changed_{d}", mask, with_share=False)
        nd = g["terms_numbers_direction"]
        row["terms_numbers_compared_n"] = int(nd.notna().sum())
        row["terms_numbers_longer_n"] = int((nd == "longer").sum())
        row["terms_numbers_shorter_n"] = int((nd == "shorter").sum())

        # dispute share: invoice-value-weighted where every entity with a share also has a value.
        # Filers read this field two ways: share of ALL invoices, or share of the LATE invoices that were late
        # because of a dispute. A value above the entity's own share of invoices paid late can only be the second
        # reading, so it is inconsistent with the field label and is left out (counted in dispute_share_inconsistent_n).
        dd = g[g["pct_not_paid_due_to_dispute"].notna()]
        incons = dd["pct_paid_late"].notna() & (dd["pct_not_paid_due_to_dispute"] > dd["pct_paid_late"] + 0.5)
        row["dispute_share_inconsistent_n"] = int(incons.sum())
        d = dd[~incons]
        row["dispute_share_entities_n"] = len(d)
        if not len(d):
            row["dispute_share_pct"], row["dispute_share_method"] = None, None
        elif d["value_paid_total_gbp"].notna().all() and d["value_paid_total_gbp"].sum() > 0:
            w = d["value_paid_total_gbp"]
            row["dispute_share_pct"] = round(float((d["pct_not_paid_due_to_dispute"] * w).sum() / w.sum()), 2)
            row["dispute_share_method"] = "weighted_by_invoice_value_paid"
        else:
            row["dispute_share_pct"] = round(float(d["pct_not_paid_due_to_dispute"].mean()), 2)
            row["dispute_share_method"] = "simple_mean"
        if len(d):
            top = d.sort_values(["pct_not_paid_due_to_dispute", "value_paid_total_gbp"], ascending=False).iloc[0]
            row.update(dispute_share_max_pct=float(top["pct_not_paid_due_to_dispute"]),
                       dispute_share_evidence_entity=top["company_name"],
                       dispute_share_evidence_url=top["source_url"],
                       dispute_share_observed_at=str(top["filing_date"]))
        else:
            row.update(dispute_share_max_pct=None, dispute_share_evidence_entity=None,
                       dispute_share_evidence_url=None, dispute_share_observed_at=None)

        q = g["dispute_process_quality"]
        for lab in LABELS:
            row[f"dispute_quality_{lab}_n"] = int((q == lab).sum())
        weak = q.isin(WEAK_LABELS)
        row["dispute_quality_weak_share"] = round(float(weak.mean()), 4)
        row["dispute_quality_llm_read_n"] = int((g["dispute_process_quality_method"] == "llm_read").sum())
        top = _top_entity(g, weak)
        row["dispute_quality_weak_evidence_entity"] = None if top is None else top["company_name"]
        row["dispute_quality_weak_evidence_url"] = None if top is None else top["source_url"]
        row["dispute_quality_weak_observed_at"] = None if top is None else str(top["filing_date"])
        best = _top_entity(g, q == "named_route")
        row["dispute_quality_named_route_evidence_url"] = None if best is None else best["source_url"]

        row["entity_numbers"] = ";".join(sorted(g["company_number"]))
        row["source_url"] = g.sort_values("value_paid_total_gbp", ascending=False, na_position="last")["source_url"].iloc[0]
        row["source_type"] = SOURCE_TYPE
        row["retrieved_at"] = g["retrieved_at"].iloc[0]
        row["period_start"] = row["uk_period_start_min"]
        row["period_end"] = row["uk_period_end_max"]
        row["extraction_method"] = "group_rollup_of_uk_entity_features"
        row["confidence"] = 1.0
        rows.append(row)
    out = pd.DataFrame(rows)
    for c in out.columns:
        if c.endswith("_any"):
            out[c] = out[c].astype(bool)
    return out


# --------------------------------------------------------------------------- signals

def _pct(x: float) -> str:
    return f"{x:.0f}%" if abs(x - round(x)) < 0.05 else f"{x:.1f}%"


def _of(n: int, total: int, group: str, verb: str = "say so") -> str:
    if total > 1:
        return f"{n} of {total} current UK reporting entities of {group} {verb}"
    return f"the only current UK reporting entity of {group}"


def build_signals(grp: pd.DataFrame, ent: pd.DataFrame, group_map: pd.DataFrame) -> pd.DataFrame:
    """One row per (company_id, signal_type). Wording states what the filing says, nothing more.
    scf_started / einvoicing_started are subsets of scf_offered / einvoicing_offered: a consumer
    that scores signals should not count both."""
    m = group_map[["company_number", "company_id"]].drop_duplicates("company_number")
    j = ent.merge(m, on="company_number", how="inner").set_index("company_id")
    recs = []

    def add(cid, typ, text, url, when):
        recs.append({"company_id": cid, "signal_type": typ, "text": text, "evidence_url": url, "observed_at": when})

    for r in grp.itertuples(index=False):
        g, n, e = r.group_name, r.uk_entities_n, j.loc[[r.company_id]]
        if r.scf_offered_n:
            add(r.company_id, "scf_offered",
                f"{r.scf_offered_evidence_entity} states in its statutory payment report that it offers supply-chain financing "
                f"({_of(r.scf_offered_n, n, g)}).", r.scf_offered_evidence_url, r.scf_offered_observed_at)
        if r.scf_started_n:
            add(r.company_id, "scf_started",
                f"{r.scf_started_evidence_entity} reports offering supply-chain financing in its latest filing and did not in the "
                f"report one year earlier ({r.scf_started_n} {g} entit{'y' if r.scf_started_n == 1 else 'ies'}).",
                r.scf_started_evidence_url, r.scf_started_observed_at)
        if r.einvoicing_offered_n:
            add(r.company_id, "einvoicing_offered",
                f"{r.einvoicing_offered_evidence_entity} states that it offers e-invoicing to suppliers "
                f"({_of(r.einvoicing_offered_n, n, g)}).", r.einvoicing_offered_evidence_url, r.einvoicing_offered_observed_at)
        if r.einvoicing_started_n:
            add(r.company_id, "einvoicing_started",
                f"{r.einvoicing_started_evidence_entity} reports offering e-invoicing in its latest filing and did not in the "
                f"report one year earlier ({r.einvoicing_started_n} {g} entit{'y' if r.einvoicing_started_n == 1 else 'ies'}).",
                r.einvoicing_started_evidence_url, r.einvoicing_started_observed_at)
        for d, phrase in (("longer", "towards longer terms"), ("shorter", "towards shorter terms"),
                          ("other", "without a clear lengthening or shortening")):
            k = getattr(r, f"terms_changed_{d}_n")
            if not k:
                continue
            name = getattr(r, f"terms_changed_{d}_evidence_entity")
            row = e[e["company_name"] == name].iloc[0]
            quote = trim(row["terms_changed_text"], 160)
            add(r.company_id, f"terms_changed_{d}",
                f"{name} reports that its payment terms changed in the period to {row['period_end']}, {phrase} "
                f"(filing text: \"{quote}\").",
                getattr(r, f"terms_changed_{d}_evidence_url"), getattr(r, f"terms_changed_{d}_observed_at"))
        if r.pay_to_stay_n:
            row = e[e["company_name"] == r.pay_to_stay_evidence_entity].iloc[0]
            charged = bool(row["pay_to_stay_charged"]) if not pd.isna(row["pay_to_stay_charged"]) else False
            what = ("that it charged suppliers a fee to remain on its supplier list in the period" if charged else
                    "that its payment practices and policies cover charging suppliers a fee to remain on its supplier list")
            add(r.company_id, "pay_to_stay", f"{r.pay_to_stay_evidence_entity} reports {what}.",
                r.pay_to_stay_evidence_url, r.pay_to_stay_observed_at)
        if r.dispute_share_pct is not None and not pd.isna(r.dispute_share_pct) and r.dispute_share_pct >= DISPUTE_SHARE_HIGH:
            basis = ("weighted by invoice value paid" if r.dispute_share_method == "weighted_by_invoice_value_paid"
                     else "simple mean")
            if r.dispute_share_entities_n > 1:
                text = (f"Across {r.dispute_share_entities_n} UK reporting entities of {g}, the reported share of invoices not paid "
                        f"within agreed terms because of a dispute is {_pct(r.dispute_share_pct)} ({basis}); the highest is "
                        f"{r.dispute_share_evidence_entity} at {_pct(r.dispute_share_max_pct)}.")
            else:
                text = (f"{r.dispute_share_evidence_entity} reports that {_pct(r.dispute_share_pct)} of invoices were not paid "
                        f"within agreed terms because of a dispute.")
            add(r.company_id, "dispute_share_high", text, r.dispute_share_evidence_url, r.dispute_share_observed_at)
        # QA (blind 60-text check): regex labels miss most weak texts and are not reliable enough for a sales
        # signal, LLM labels are (kappa 0.84). So the weak-process signal needs every entity of the group LLM-read.
        if r.dispute_quality_weak_share >= WEAK_SHARE_MIN and r.dispute_quality_llm_read_n >= n:
            k = r.dispute_quality_boilerplate_n + r.dispute_quality_none_n
            add(r.company_id, "dispute_process_weak",
                f"The dispute resolution process described in the filing of {r.dispute_quality_weak_evidence_entity} names no "
                f"contact, timescale or escalation step ({_of(k, n, g, 'are classed boilerplate or none on the project rubric')}).", r.dispute_quality_weak_evidence_url, r.dispute_quality_weak_observed_at)
    return pd.DataFrame(recs, columns=["company_id", "signal_type", "text", "evidence_url", "observed_at"])


# --------------------------------------------------------------------------- agreement + sample

def cohen_kappa(a: pd.Series, b: pd.Series, labels: list[str] = LABELS) -> float:
    n = len(a)
    if n == 0:
        return float("nan")
    po = float((a.to_numpy() == b.to_numpy()).mean())
    pe = sum(float((a == lab).mean()) * float((b == lab).mean()) for lab in labels)
    return (po - pe) / (1 - pe) if pe < 1 else float("nan")


def llm_scope_texts(ent: pd.DataFrame, group_map: pd.DataFrame, companies: pd.DataFrame, top_n: int = TOP_N_LLM) -> pd.DataFrame:
    """Distinct dispute texts of current entities linked to a top-N ranked, non-excluded group."""
    top = companies[companies["excluded_reason"].isna()].nsmallest(top_n, "rank")["company_id"]
    nums = group_map[group_map["company_id"].isin(top)]["company_number"]
    e = ent[ent["company_number"].isin(nums)].sort_values(["dispute_text_hash", "company_number"])
    return e.drop_duplicates("dispute_text_hash")


def build_sample(scope: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    """60 texts, 15 per LLM label where available, shortfall filled from the remaining texts."""
    s = scope[scope["dispute_process_quality_llm"].notna()]
    parts = []
    for lab in LABELS:
        p = s[s["dispute_process_quality_llm"] == lab]
        parts.append(p.sample(n=min(15, len(p)), random_state=SAMPLE_SEED))
    picked = pd.concat(parts) if parts else s.head(0)
    short = 60 - len(picked)
    rest = s.drop(picked.index)
    if short > 0 and len(rest):
        picked = pd.concat([picked, rest.sample(n=min(short, len(rest)), random_state=SAMPLE_SEED)])
    picked = picked.sample(frac=1, random_state=SAMPLE_SEED)  # shuffle so order does not reveal the label
    sample = picked[["dispute_text_hash", "company_number", "company_name", "source_url", "dispute_process_text"]].rename(
        columns={"dispute_text_hash": "text_hash"}).copy()
    sample["qa_label"] = ""
    sample["qa_note"] = ""
    key = picked[["dispute_text_hash", "dispute_process_quality_llm", "dispute_process_quality_regex"]].rename(
        columns={"dispute_text_hash": "text_hash", "dispute_process_quality_llm": "llm_label",
                 "dispute_process_quality_regex": "regex_label"})
    return sample.reset_index(drop=True), key.reset_index(drop=True)


def write_sample(sample: pd.DataFrame, key: pd.DataFrame) -> str:
    """Never overwrite a sample that QA has started to fill in."""
    if SAMPLE.exists():
        old = pd.read_csv(SAMPLE, dtype=str, keep_default_na=False)
        if "qa_label" in old.columns and (old["qa_label"].str.strip() != "").any():
            return "kept (QA labels present)"
    SAMPLE.parent.mkdir(parents=True, exist_ok=True)
    sample.to_csv(SAMPLE, index=False)
    key.to_csv(SAMPLE_KEY, index=False)
    return "written"


# --------------------------------------------------------------------------- field audit

# raw header -> (parsed column, used before this module?, what it contains, GTM use)
AUDIT = [
    ("Report Id", "report_id", "yes", "Report identifier, builds the report URL", "provenance key"),
    ("Policy Regime", "policy_regime", "yes", "Which version of the reporting rules applied (Regime-1/2/3)", "needed to read nulls correctly; not a sales field"),
    ("Financial period start date", "financial_period_start", "parsed only", "Start of the financial year", "no"),
    ("Start date", "period_start", "yes", "Reporting period start", "provenance"),
    ("End date", "period_end", "yes", "Reporting period end", "provenance"),
    ("Filing date", "filing_date", "yes", "Date the report was filed", "signal date (observed_at)"),
    ("Company", "company_name", "yes", "Legal entity name", "key"),
    ("Company number", "company_number", "yes", "Companies House number", "key"),
    ("Qualifying contracts in reporting period", "had_qualifying_contracts", "yes (quality flag)", "Whether there were contracts in scope", "no (filter only)"),
    ("Payments made in reporting period", "payments_made_in_period", "yes (quality flag)", "Whether payments were made", "no (filter only)"),
    ("Qualifying construction contracts in reporting period", "had_qualifying_construction_contracts", "parsed only", "Has construction contracts in scope", "low: sector hint for construction accounts"),
    ("Construction contracts have retention clauses", "construction_contracts_have_retention_clauses", "parsed only", "Uses retention clauses", "low: construction-only talking point, not built"),
    ("Average time to pay", "avg_days_to_pay", "yes", "Average days from invoice receipt to payment", "core pain metric"),
    ("Total value invoices paid within 30 days", "value_paid_within_30_gbp", "yes", "GBP value paid within 30 days", "weights"),
    ("Total value invoices paid between 31 and 60 days", "value_paid_31_60_gbp", "yes", "GBP value paid in 31-60 days", "weights"),
    ("Total value invoices paid later than 60 days", "value_paid_over_60_gbp", "yes", "GBP value paid after 60 days", "weights"),
    ("% Invoices paid within 30 days", "pct_paid_within_30", "yes", "Share of invoices by number", "core"),
    ("% Invoices paid between 31 and 60 days", "pct_paid_31_60", "yes", "Share of invoices by number", "core"),
    ("% Invoices paid later than 60 days", "pct_paid_over_60", "yes", "Share of invoices by number", "core"),
    ("Total value invoices paid later than agreed terms", "value_paid_late_gbp", "yes", "GBP value paid late (collected from 2025 rules)", "core"),
    ("% Invoices not paid within agreed terms", "pct_paid_late", "yes", "Share of invoices paid late", "core"),
    ("% Invoices not paid due to dispute", "pct_not_paid_due_to_dispute", "parsed only -> NEW feature", "Share of invoices not paid within terms because of a dispute (collected from 2025 rules; null under Regime-1)", "HIGH: sizes the dispute workload an invoice-matching agent would clear"),
    ("Shortest (or only) standard payment period", "shortest_standard_payment_period_days", "parsed only -> NEW (yoy delta)", "Shortest standard term, days", "medium: number-based terms-change signal"),
    ("Longest standard payment period", "longest_standard_payment_period_days", "yes (group max, site)", "Longest standard term, days", "medium: number-based terms-change signal"),
    ("Standard payment terms", "standard_payment_terms_text", "site lookup only", "Free-text description of standard terms", "medium: quotable on a one-pager; not classified here"),
    ("Payment terms have changed", "payment_terms_changed_text", "parsed only -> NEW feature", "Free text, filled only when terms changed in the period", "HIGH but rare: a dated why-now event, with direction"),
    ("Suppliers notified of changes", "suppliers_notified_of_changes_text", "parsed only -> NEW (kept trimmed)", "Free text: how suppliers were told about the change", "low: colour for the terms-change signal"),
    ("Maximum contractual payment period", "max_contractual_payment_period_days", "yes (group max, site)", "Longest contractual term agreed, days", "medium: number-based terms-change signal; has typos (values above 365)"),
    ("Maximum contractual payment period information", "max_contractual_payment_period_info_text", "parsed only", "Free-text context for the maximum period", "low: context only"),
    ("Other information payment terms", "other_payment_terms_info_text", "parsed only", "Free-text other information on terms", "low: unstructured, occasionally mentions discounts or SCF"),
    ("Retention clauses included in all construction contracts", "retention_in_all_construction_contracts", "parsed only", "Construction retention flag", "low (construction only)"),
    ("Retention clauses included in standard payment terms", "retention_in_standard_payment_terms", "parsed only", "Construction retention flag", "low (construction only)"),
    ("Retention clauses are used in specific circumstances", "retention_in_specific_circumstances", "parsed only", "Construction retention flag", "low (construction only)"),
    ("Description of specific circumstances for retention clauses", "retention_specific_circumstances_text", "parsed only", "Free text", "low (construction only)"),
    ("Retention clauses used above a specific sum", "retention_above_specific_sum", "parsed only", "Construction retention flag", "low (construction only)"),
    ("Value above which retention clauses are used", "retention_threshold_value_gbp", "parsed only", "GBP threshold", "low (construction only)"),
    ("Retention clauses are at a standard rate", "retention_at_standard_rate", "parsed only", "Construction retention flag", "low (construction only)"),
    ("Retention clauses standard rate percentage", "retention_standard_rate_pct", "parsed only", "Standard retention rate, %", "low (construction only)"),
    ("Retention clauses have parity with client", "retention_parity_with_client", "parsed only", "Whether retention mirrors the client's", "low (construction only)"),
    ("Description of parity policy", "retention_parity_policy_text", "parsed only", "Free text", "low (construction only)"),
    ("Retention clause money release description", "retention_release_text", "parsed only", "Free text", "low (construction only)"),
    ("Retention clause money release is staged", "retention_release_is_staged", "parsed only", "Flag", "low (construction only)"),
    ("Description of stages for money release", "retention_release_stages_text", "parsed only", "Free text", "low (construction only)"),
    ("Retention value compared to client retentions as %", "retention_value_vs_client_retentions_pct", "parsed only", "Percent", "low (construction only)"),
    ("Retention value compared to total payments as %", "retention_value_vs_total_payments_pct", "parsed only", "Percent", "low (construction only)"),
    ("Dispute resolution process", "dispute_resolution_process_text", "parsed only -> NEW feature", "Free-text description of how supplier disputes are handled", "HIGH: classified on a 4-level rubric; quotable"),
    ("Participates in payment codes", "payment_codes_text", "yes (group any-flag, scoring)", "Free text: 'No' or the name of a code", "medium: now also which code"),
    ("E-Invoicing offered", "offers_einvoicing", "yes (group share, site)", "Yes/no", "medium: now also 'started in the last year'"),
    ("Supply-chain financing offered", "offers_supply_chain_finance", "yes (group any-flag, scoring, site)", "Yes/no", "HIGH: existing early-payment programme; now also 'started in the last year'"),
    ("Policy covers charges for remaining on supplier list", "policy_covers_supplier_list_charges", "parsed only -> NEW feature", "Yes/no: policy allows charging suppliers to stay listed ('pay to stay')", "medium, rare: supplier-relations talking point"),
    ("Charges have been made for remaining on supplier list", "charged_for_supplier_list", "parsed only -> NEW feature", "Yes/no: such charges were made in the period", "medium, rare"),
    ("URL", "source_url", "yes", "Link to the report on the government service", "provenance"),
]


def _dist(s: pd.Series) -> str:
    n = len(s)
    if str(s.dtype) in ("bool", "boolean"):
        return f"true {s.fillna(False).astype(bool).mean():.1%}"
    if s.dtype.kind in "fi" and s.name != "report_id":
        v = s.dropna()
        if not len(v):
            return "all null"
        return f"median {v.median():g}, p90 {v.quantile(.9):g}, max {v.max():g}"
    if s.name and (str(s.name).endswith("_text")):
        v = s.dropna()
        return f"{v.nunique():,} distinct, median length {int(v.str.len().median()) if len(v) else 0} chars"
    return f"{s.nunique():,} distinct of {n:,}"


def field_audit(reports: pd.DataFrame, latest_ids: pd.Series) -> pd.DataFrame:
    L = reports[reports["report_id"].isin(latest_ids)]
    rows = []
    for raw, col, used, what, gtm in AUDIT:
        s = L[col]
        fill = s.notna().mean()
        if col == "payment_codes_text":
            dist = f"'No' in {(s.str.strip().str.lower() == 'no').mean():.1%}; {s.nunique()} distinct values"
        else:
            dist = _dist(s)
        rows.append({"raw_column": raw, "parsed_as": col, "used_before": used, "contains": what,
                     "fill_rate_current": round(float(fill), 4), "distribution": dist, "gtm_use": gtm})
    return pd.DataFrame(rows)


# --------------------------------------------------------------------------- report

def _counts_block(e: pd.DataFrame, label: str) -> list[str]:
    n = len(e)
    if n == 0:
        return [f"No entities for {label}."]

    def line(name, k, base=n):
        return f"| {name} | {k:,} | {k / base:.1%} |" if base else f"| {name} | {k:,} | n/a |"

    t = lambda c: int(e[c].fillna(False).astype(bool).sum())  # noqa: E731
    ch = e["terms_changed_latest"].fillna(False).astype(bool)
    disp = e["pct_not_paid_due_to_dispute"]
    L = [f"Base: {n:,} {label}.\n", "| Feature | Entities | Share |", "|---|---:|---:|",
         line("Offers supply-chain financing", t("offers_scf")),
         line("  of which started in the last year (not offered in the report one year earlier)", t("scf_started")),
         line("Offers e-invoicing", t("offers_einvoicing")),
         line("  of which started in the last year", t("einvoicing_started")),
         line("States membership of a payment code", t("in_payment_code")),
         line("  names the Fair Payment Code", int((e["payment_code_name"] == "fair_payment_code").sum())),
         line("  names the Prompt Payment Code", int((e["payment_code_name"] == "prompt_payment_code").sum())),
         line("  other or unclear text", int((e["payment_code_name"] == "other_or_unclear").sum())),
         line("Latest report says payment terms changed", int(ch.sum()))]
    for d in ("longer", "shorter", "other", "unknown"):
        L.append(line(f"  direction from text: {d}", int((ch & (e["terms_changed_direction"] == d)).sum())))
    nd = e["terms_numbers_direction"]
    L += [line("Term-length numbers comparable with the report one year earlier", int(nd.notna().sum())),
          line("  numbers moved longer (no decrease)", int((nd == "longer").sum())),
          line("  numbers moved shorter (no increase)", int((nd == "shorter").sum())),
          line("  mixed", int((nd == "mixed").sum())),
          line("  numbers longer but no change declared in the text field", int(((nd == "longer") & ~ch).sum())),
          line("Pay-to-stay: policy covers charging suppliers to remain listed", t("pay_to_stay_policy")),
          line("Pay-to-stay: charges were made in the period", t("pay_to_stay_charged")),
          line("Dispute share reported (not null)", int(disp.notna().sum())),
          line(f"  dispute share at or above {DISPUTE_SHARE_HIGH:g}%", int((disp >= DISPUTE_SHARE_HIGH).sum()))]
    for lab in LABELS:
        L.append(line(f"Dispute process: {lab}", int((e["dispute_process_quality"] == lab).sum())))
    return L


def write_report(audit: pd.DataFrame, ent: pd.DataFrame, grp: pd.DataFrame, sig: pd.DataFrame,
                 companies: pd.DataFrame, group_map: pd.DataFrame, scope: pd.DataFrame, sample_status: str) -> None:
    qa_tail = None
    if REPORT_MD.exists():
        old = REPORT_MD.read_text()
        if QA_HEADING in old:
            qa_tail = old[old.index(QA_HEADING):]
    L: list[str] = ["# UK payment-practice filings: fields beyond payment speed\n",
                    "- Generated by `python -m chase.enrich.uk_fields` (deterministic, no network).",
                    f"- Source: UK statutory payment practices export, retrieved {ent['retrieved_at'].iloc[0]}. "
                    "Every row links to the report page on check-payment-practices.service.gov.uk.",
                    f"- Base: {len(ent):,} current entities (usable latest report, not stale); "
                    f"{len(grp):,} ranked groups have at least one of them.",
                    "- What was checked: all 52 raw columns audited; new features built from the ones not used so far; "
                    "dispute-process text classified by rules and by an LLM read, agreement measured; "
                    "a blind sample prepared for an independent hand-check.\n",
                    "## 1. Field audit (52 raw columns)\n",
                    "Fill rate and distribution are for the latest report of each current entity.\n",
                    "| # | Raw column | Used before | Contains | Fill | Distribution | GTM use |", "|---:|---|---|---|---:|---|---|"]
    for i, r in enumerate(audit.itertuples(index=False), 1):
        L.append(f"| {i} | {r.raw_column} | {r.used_before} | {r.contains} | {r.fill_rate_current:.1%} | {r.distribution} | {r.gtm_use} |")
    L += ["",
          "**Is there a \"deductions\" field? No.** The filing has no field on deductions from invoices, on invoice "
          "discounting demanded from suppliers, or on early-payment discount terms. The closest are the two "
          "\"charges for remaining on supplier list\" yes/no fields (commonly called pay-to-stay): one says the "
          "policy covers such charges, the other says such charges were made in the period. They are built here as "
          "`pay_to_stay_policy` and `pay_to_stay_charged`. Nothing in this module should be described as deductions data.\n",
          "## 2. Headline counts: all current entities\n", *_counts_block(ent, "current entities"), ""]

    top100 = companies[companies["excluded_reason"].isna()].nsmallest(100, "rank")["company_id"]
    nums = group_map[group_map["company_id"].isin(top100)]["company_number"]
    e100 = ent[ent["company_number"].isin(nums)]
    g100 = grp[grp["company_id"].isin(top100)]
    L += ["## 3. Headline counts: top-100 ranked groups\n",
          f"{len(g100)} of the top 100 ranked groups have at least one current UK reporting entity "
          f"({len(e100):,} entities).\n",
          "### Entities of the top-100 groups\n", *_counts_block(e100, "current entities linked to a top-100 group"), "",
          "### Groups (of those with UK entities)\n", "| Feature | Groups |", "|---|---:|",
          f"| Any entity offers supply-chain financing | {int((g100['scf_offered_n'] > 0).sum())} |",
          f"| Any entity started supply-chain financing in the last year | {int(g100['scf_started_any'].sum())} |",
          f"| Any entity offers e-invoicing | {int((g100['einvoicing_offered_n'] > 0).sum())} |",
          f"| Any entity started e-invoicing in the last year | {int(g100['einvoicing_started_any'].sum())} |",
          f"| Any entity states a payment code | {int((g100['payment_code_n'] > 0).sum())} |",
          f"| Any entity reports changed payment terms | {int((g100['terms_changed_n'] > 0).sum())} |",
          f"|   towards longer / shorter / other | {int((g100['terms_changed_longer_n'] > 0).sum())} / "
          f"{int((g100['terms_changed_shorter_n'] > 0).sum())} / {int((g100['terms_changed_other_n'] > 0).sum())} |",
          f"| Any pay-to-stay flag | {int(g100['pay_to_stay_any'].sum())} |",
          f"| Group dispute share at or above {DISPUTE_SHARE_HIGH:g}% | {int((g100['dispute_share_pct'] >= DISPUTE_SHARE_HIGH).sum())} |",
          f"| At least half of entities with boilerplate/none dispute text | {int((g100['dispute_quality_weak_share'] >= WEAK_SHARE_MIN).sum())} |",
          ""]

    d = ent["pct_not_paid_due_to_dispute"].dropna()
    gd = grp["dispute_share_pct"].dropna()
    L += ["## 4. Dispute-share threshold\n",
          f"`dispute_share_high` fires when the group's share of invoices not paid within terms because of a dispute is "
          f"at or above **{DISPUTE_SHARE_HIGH:g}%** (invoice-value-weighted across its current UK entities; simple mean when a value is missing).\n",
          f"- Entity distribution (n={len(d):,}): {(d == 0).mean():.1%} report exactly 0; median {d.median():g}, "
          f"p75 {d.quantile(.75):g}, p90 {d.quantile(.9):g}, p95 {d.quantile(.95):g}, p99 {d.quantile(.99):g}.",
          f"- {DISPUTE_SHARE_HIGH:g}% sits at percentile {(d < DISPUTE_SHARE_HIGH).mean() * 100:.1f} of current entities "
          f"and percentile {(gd < DISPUTE_SHARE_HIGH).mean() * 100:.1f} of matched groups (n={len(gd):,}).",
          f"- Why this number: the distribution is a spike at zero with a long tail, so a percentile near the top decile "
          f"is the natural cut. The entity p90 is {d.quantile(.9):g}%; {DISPUTE_SHARE_HIGH:g}% is the next round number, easy to say in a "
          "sentence.",
          f"- Groups flagged: {int((gd >= DISPUTE_SHARE_HIGH).sum())} of {len(gd):,}.",
          "- Caveat: the field is by number of invoices and self-reported. Some filers enter 0 because they cannot measure it, "
          "and a few say so in their dispute text. A 0 is not evidence of no disputes.",
          f"- Two readings of the field (found in the Phase 12 QA): {int((ent['pct_not_paid_due_to_dispute'] > ent['pct_paid_late'] + 0.5).sum()):,} "
          "current entities report a dispute share ABOVE their own share of invoices paid late, which is only possible if they read "
          "the field as 'share of the late invoices that were late because of a dispute'. Those values are left out of every group "
          "figure and signal (`dispute_share_inconsistent_n`). Values at or below the late share may still use either reading, so "
          "the dispute share is quoted only as the filer's own figure with its label, never converted into an invoice count.\n",
          "## 5. Dispute-process rubric\n",
          "Two questions from the supplier's side: where do I go, and what happens next?\n",
          "| Level | Definition |", "|---|---|",
          "| `named_route` | Says where to go (email address, phone, portal, helpdesk, or a named team or role) AND what happens next (a stated timescale, or an escalation step beyond first contact, including mediation, adjudication or arbitration). |",
          "| `basic` | Only one of the two: a contact, or concrete described steps (invoice on hold, credit note requested), but not both. |",
          "| `boilerplate` | Generic statement with neither, e.g. \"disputes are resolved in line with contract terms\", \"discussion with the supplier\". |",
          "| `none` | Empty, \"n/a\", a bare web link, or a text that does not describe a dispute process. |",
          "",
          "Reading conventions for the LLM labels: \"if AP cannot resolve it, it goes to X\" counts as escalation, an unconditional "
          "internal hand-off does not; a contract clause with timescales and arbitration but no contact is `basic`; a team or role "
          "counts as a route even without an address, \"the relevant department\" does not.",
          "",
          "The rubric rates the disclosure, not the company's behaviour.\n",
          "## 6. Regex rules vs LLM read\n"]
    s = scope[scope["dispute_process_quality_llm"].notna()]
    if len(s):
        a, b = s["dispute_process_quality_llm"], s["dispute_process_quality_regex"]
        cm = pd.crosstab(a, b).reindex(index=LABELS, columns=LABELS, fill_value=0)
        L += [f"- Scope: distinct dispute texts of current entities linked to a top-{TOP_N_LLM} ranked group: "
              f"{len(scope):,} distinct texts, {len(s):,} with an LLM label.",
              "- The LLM labels were assigned by Claude (the model running this build as a subagent inside Claude Code, "
              "no API call) reading each text against the rubric, in batches, without seeing the regex label. Long texts were read "
              "in full unless the first 500 to 900 characters already met `named_route`. Each label has a one-line reason in "
              "`data/interim/uk_dispute_llm.csv` (a generic reason per level, a specific note on borderline cases).",
              "- The regex rules were written before the LLM read and were not tuned against the LLM labels afterwards.",
              f"- Percent agreement: **{(a.to_numpy() == b.to_numpy()).mean():.1%}**; Cohen's kappa: **{cohen_kappa(a, b):.2f}**.",
              f"- Agreement on the binary weak (boilerplate/none) vs not: {(a.isin(WEAK_LABELS).to_numpy() == b.isin(WEAK_LABELS).to_numpy()).mean():.1%}.\n",
              "Confusion matrix (rows: LLM label, columns: regex label):\n",
              "| LLM \\ regex | " + " | ".join(LABELS) + " | total |", "|---|" + "---:|" * (len(LABELS) + 1)]
        for lab in LABELS:
            L.append(f"| {lab} | " + " | ".join(str(int(cm.loc[lab, c])) for c in LABELS) + f" | {int(cm.loc[lab].sum())} |")
        L += ["",
              f"Entities labelled by LLM read: {int((ent['dispute_process_quality_method'] == 'llm_read').sum()):,}; "
              f"by regex rules: {int((ent['dispute_process_quality_method'] == 'regex_rules').sum()):,}. "
              "Where both exist the LLM label is used.",
              "Neither label is ground truth. The independent hand-check below is the accuracy test.\n"]
    else:
        L.append("No LLM labels found in `data/interim/uk_dispute_llm.csv`; all entities carry the regex label.\n")

    L += ["## 7. Signals written\n", f"`data/processed/uk_field_signals.csv`: {len(sig):,} rows for {sig['company_id'].nunique():,} groups.\n",
          "| signal_type | Groups |", "|---|---:|"]
    for k, v in sig["signal_type"].value_counts().items():
        L.append(f"| {k} | {v:,} |")
    L += ["",
          "`scf_started` and `einvoicing_started` are subsets of the `_offered` signals; do not count both. "
          "Terms-change signals come only from the declared text field; number-only movements are kept as features "
          "(`terms_numbers_direction`) and are not signals, because the three numbers are often re-entered inconsistently.\n",
          "## 8. What is NOT in the data\n",
          "- No deductions field. Only the two pay-to-stay yes/no fields described in section 1.",
          "- The supply-chain financing flag is a self-declared yes/no. No programme size, provider, uptake, or whether it is reverse factoring or dynamic discounting.",
          "- The e-invoicing flag does not say which standard, portal or network, or what share of invoices arrives electronically.",
          "- No early-payment discount field of any kind.",
          "- The dispute share is by number of invoices, not value, and is null under the oldest rules (Regime-1).",
          "- \"Payment terms have changed\" is a free-text field filled only by companies that declare a change. An empty field means none was declared, not that none happened.",
          "- No field says how many suppliers or invoices a company has.\n",
          "## 9. Caveats\n",
          "- All flags are self-reported by the company and signed off by a director; nobody audits them.",
          "- Reports are per UK legal entity. A group row describes its matched UK entities, not the global group.",
          "- `scf_started` / `einvoicing_started` compare with the report about one year earlier (within 92 days). Flags flip for clerical reasons too; treat a start as a prompt to check the filing, not as a confirmed launch.",
          "- The payment-code flag is true for any text other than \"No\". A few texts name internal codes or are not codes at all (`payment_code_name` = other_or_unclear). The Prompt Payment Code was replaced by the Fair Payment Code, and older wording persists in filings.",
          "- Direction of a terms change comes from keyword rules on short free text; `other` and `unknown` are common and honest.",
          "- Maximum contractual period contains typos (values far above 365 days); the year-on-year deltas inherit them.",
          "- Dispute texts are public company statements that sometimes name staff. No output column extracts names; the trimmed text is the only place they can appear, and it should stay off any public page unless filtered.",
          f"- Blind QA sample: `evals/gold/uk_dispute_sample.csv` ({sample_status}); key in `data/interim/uk_dispute_sample_key.csv`.\n"]
    text = "\n".join(L) + "\n"
    text += qa_tail if qa_tail else (
        f"{QA_HEADING}\n\n_To be filled by the QA agent: label the 60 texts in `evals/gold/uk_dispute_sample.csv` "
        "(`qa_label`, `qa_note`) using the rubric in section 5 without opening the key, then compare with "
        "`data/interim/uk_dispute_sample_key.csv` and report agreement with the LLM label and with the regex label, "
        "with a list of disagreements._\n")
    REPORT_MD.parent.mkdir(parents=True, exist_ok=True)
    REPORT_MD.write_text(text)


# --------------------------------------------------------------------------- main

def main(argv: list[str] | None = None) -> None:
    reports = pd.read_parquet(PROCESSED / "uk_payment_practices.parquet")
    entities = pd.read_parquet(PROCESSED / "uk_entity_latest.parquet")
    group_map = pd.read_parquet(PROCESSED / "uk_entity_group_map.parquet")
    companies = pd.read_parquet(PROCESSED / "companies.parquet", columns=["company_id", "name", "rank", "excluded_reason"])

    ent = build_entity_features(reports, entities)
    grp = build_group_features(ent, group_map)
    sig = build_signals(grp, ent, group_map)

    ent.to_parquet(PROCESSED / "uk_entity_features.parquet", index=False)
    ent.to_csv(PROCESSED / "uk_entity_features.csv", index=False)
    grp.to_parquet(PROCESSED / "uk_group_features.parquet", index=False)
    grp.to_csv(PROCESSED / "uk_group_features.csv", index=False)
    sig.to_csv(PROCESSED / "uk_field_signals.csv", index=False)

    scope = llm_scope_texts(ent, group_map, companies)
    status = "no LLM labels yet"
    if scope["dispute_process_quality_llm"].notna().any():
        status = write_sample(*build_sample(scope))
    audit = field_audit(reports, ent["report_id"])
    write_report(audit, ent, grp, sig, companies, group_map, scope, status)
    print(f"entities: {len(ent):,} | groups: {len(grp):,} | signals: {len(sig):,} | "
          f"llm-labelled texts in scope: {int(scope['dispute_process_quality_llm'].notna().sum())}/{len(scope)} | sample: {status}")


if __name__ == "__main__":
    main(sys.argv[1:])
