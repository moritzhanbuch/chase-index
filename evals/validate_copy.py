"""Validate the LLM-written copy against the data it is allowed to cite.

Checks
  1. outputs/one_pagers/copy.json      (20 accounts: 3 bullets + angle)
  2. data/processed/rationales_llm.csv (100 rationales)

Every number in the text must equal a value in that account's own facts
(rounded to 0 or 1 decimals). Run:  .venv/bin/python evals/validate_copy.py
Exit code 0 = pass, 1 = fail. Writes evals/reports/copy_validation.md.
"""
from __future__ import annotations

import csv
import hashlib
import itertools
import json
import math
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
FACTS = ROOT / "outputs/one_pagers/facts_for_copy.json"
COPY = ROOT / "outputs/one_pagers/copy.json"
TARGETS = ROOT / "outputs/targets/target_list.csv"
RATIONALES = ROOT / "data/processed/rationales_llm.csv"
REPORT = ROOT / "evals/reports/copy_validation.md"

MAX_BULLET_WORDS = 38
MAX_ANGLE_WORDS = 60
MAX_RATIONALE_WORDS = 45

BENCHMARKS = {30.0, 32.0, 60.0}  # 30-day / 60-day benchmarks, UK large-business median
BANNED = [
    "leverage", "synerg", "unlock", "revolutionis", "revolutioniz", "seamless",
    "game-chang", "game chang", "cutting-edge", "cutting edge", "best-in-class",
    "late payer", "squeez", "worst offender", "offender", "abuse", "scam",
]
DASHES = ["—", "–"]
NUM_RE = re.compile(r"\d+(?:\.\d+)?")
SENT_SPLIT = re.compile(r"(?<=[.!?])\s+(?=[A-Z0-9\"'])")

# keyword -> product capability (only capabilities from the brief)
CAPABILITIES = {
    "matching": ["n-way matching", "matching"],
    "disputes": ["dispute"],
    "early_payment_discount": ["early-payment", "early payment", "discount", "earlier cash", "earlier payment"],
    "payment_timing": ["payment timing"],
    "guardrails": ["guardrail", "minimum apr", "maximum discount", "blocklist", "payroll"],
    "cash_forecast": ["cash forecast"],
    "fraud_checks": ["fraud"],
    "supplier_network": ["invite", "invitation", "emails", "emailing", "email suppliers", "long tail", "not on the network"],
    "sap_human_approval": ["a human approves", "human approval"],
    "outcome_pricing": ["outcome-based"],
}


# --- rules added after the assets review -------------------------------------------------
LATE_RE = re.compile(r"\bpaid late\b|\blate\b", re.I)
TREND_RE = re.compile(r"year on year|than a year earlier|in a year|on the year|got slower|got \d+ days faster", re.I)
NUMWORD = r"(?:\d+|one|two|three|four|five|six|seven|eight|nine|ten|eleven|twelve|thirteen)"
TREND_BASE_RE = re.compile(
    rf"\b{NUMWORD} of (?:the )?{NUMWORD}\b|\bboth\b|\ball {NUMWORD}\b|\b(?:Limited|Ltd|PLC)\b", re.I
)
COPY_BANNED_PHRASES = ["one invitation", "entity by entity", "the promised date is the one proposed"]
RATIONALE_SCORE_RE = re.compile(r"\bscores?\b|\bscored\b|\btiers?\b", re.I)


def entity_key(s: str) -> str:
    return re.sub(r"[^a-z0-9]+", " ", s.lower()).strip()


def words(text: str) -> int:
    return len(text.split())


def sentences(text: str) -> int:
    return len([s for s in SENT_SPLIT.split(text.strip()) if s])


def numbers_in(text: str, allow_20_pct: bool) -> list[str]:
    t = text.replace("S/4HANA", "")
    if allow_20_pct:
        t = re.sub(r"\babout 20% of invoices\b", "", t)
    return NUM_RE.findall(t)


def half_up(v: float, nd: int) -> float:
    m = 10 ** nd
    return math.floor(abs(v) * m + 0.5) / m


def roundings(v: float) -> set[float]:
    a = abs(v)
    return {round(a, 0), round(a, 1), half_up(a, 0), half_up(a, 1)}


def collect_numeric(obj, out: set[float]) -> None:
    if isinstance(obj, bool) or obj is None:
        return
    if isinstance(obj, (int, float)):
        if not (isinstance(obj, float) and math.isnan(obj)):
            out |= roundings(float(obj))
    elif isinstance(obj, dict):
        for v in obj.values():
            collect_numeric(v, out)
    elif isinstance(obj, list):
        for v in obj:
            collect_numeric(v, out)


def allowed_for_account(acc: dict) -> set[float]:
    """Numeric values of the account, excluding the estimates block (money ranges must
    not be quoted), plus numbers written in the why-now signal texts and the hook."""
    out: set[float] = set()
    collect_numeric({k: v for k, v in acc.items() if k != "estimates"}, out)
    for s in acc.get("why_now_signals") or []:
        for n in NUM_RE.findall(re.sub(r"\d{4}-\d{2}-\d{2}", "", s.get("text", ""))):
            out |= roundings(float(n))
    return out


def style_errors(text: str) -> list[str]:
    errs = []
    for d in DASHES:
        if d in text:
            errs.append("contains em/en dash")
    low = text.lower()
    for b in BANNED:
        if b in low:
            errs.append(f"banned word '{b}'")
    if "!" in text:
        errs.append("exclamation mark")
    if re.search(r"\b(the )?group pays in\b", low) or re.search(r"\bpays (its )?suppliers in \d", low):
        errs.append("scope: group-level 'pays in' claim")
    return errs


def caps_of(text: str) -> set[str]:
    low = text.lower()
    return {c for c, kws in CAPABILITIES.items() if any(k in low for k in kws)}


def distinct_caps(bullets: list[str]) -> bool:
    sets = [caps_of(b) for b in bullets]
    if any(not s for s in sets):
        return False
    return any(len(set(combo)) == len(combo) for combo in itertools.product(*sets))


def check_copy() -> tuple[list[str], dict]:
    errs: list[str] = []
    facts = json.loads(FACTS.read_text())
    copy = json.loads(COPY.read_text())
    ids = [a["company_id"] for a in facts]
    stats = {"accounts": len(copy), "bullets": 0, "numbers_checked": 0}
    # copy.json may hold a superset (accounts near the rank-20 boundary move between runs); every CURRENT
    # account must have agent copy, and only current accounts are checked and rendered
    if set(ids) - set(copy):
        errs.append(f"accounts without agent copy: {sorted(set(ids) - set(copy))}")
    stats["accounts"] = len(set(ids) & set(copy))
    openers = []
    twenty_pct_accounts: list[str] = []
    for acc in facts:
        cid = acc["company_id"]
        c = copy.get(cid)
        if not c:
            continue
        allowed = allowed_for_account(acc) | BENCHMARKS
        bullets = c.get("what_changes")
        angle = c.get("angle")
        if not isinstance(bullets, list) or len(bullets) != 3:
            errs.append(f"{cid}: needs exactly 3 bullets")
            bullets = bullets if isinstance(bullets, list) else []
        if not isinstance(angle, str) or not angle.strip():
            errs.append(f"{cid}: missing angle")
            angle = ""
        for i, b in enumerate(bullets, 1):
            stats["bullets"] += 1
            if words(b) > MAX_BULLET_WORDS:
                errs.append(f"{cid} bullet {i}: {words(b)} words > {MAX_BULLET_WORDS}")
            if sentences(b) != 1:
                errs.append(f"{cid} bullet {i}: not exactly one sentence")
            if "?" in b:
                errs.append(f"{cid} bullet {i}: question in bullet")
            if not caps_of(b):
                errs.append(f"{cid} bullet {i}: no product capability recognised")
            openers.append(" ".join(b.split()[:3]).lower())
        if len(bullets) == 3 and not distinct_caps(bullets):
            errs.append(f"{cid}: bullets do not cover three different capabilities")
        if words(angle) > MAX_ANGLE_WORDS:
            errs.append(f"{cid} angle: {words(angle)} words > {MAX_ANGLE_WORDS}")
        if angle and sentences(angle) not in (2, 3):
            errs.append(f"{cid} angle: {sentences(angle)} sentences (want 2, at most 3 with a short lead-in)")
        for label, text in [(f"bullet {i}", b) for i, b in enumerate(bullets, 1)] + [("angle", angle)]:
            for e in style_errors(text):
                errs.append(f"{cid} {label}: {e}")
            for n in numbers_in(text, allow_20_pct=True):
                stats["numbers_checked"] += 1
                if float(n) not in allowed:
                    errs.append(f"{cid} {label}: number {n} not in account facts")
        # --- review rules (internal assets review, not in the public copy) ---
        units = [(f"bullet {i}", b) for i, b in enumerate(bullets, 1)] + [("angle", angle)]
        uk = ((acc.get("payment_profile") or {}).get("reported") or {}).get("uk") or {}
        ents = uk.get("entities") or []
        # rule 1a: group late share null -> no late-payment argument at all
        if uk and uk.get("pct_invoices_paid_late_mean") is None:
            for label, text in units:
                if LATE_RE.search(text):
                    errs.append(f"{cid} {label}: late-payment argument but the group late share is null in the facts")
        # rule 1b: an entity whose late share is null or flagged must not be named next to a late share
        for e in ents:
            if e.get("pct_paid_late") is None or e.get("pct_paid_late_note"):
                nm = entity_key(e.get("name", ""))
                for label, text in units:
                    if nm and nm in entity_key(text) and LATE_RE.search(text):
                        errs.append(f"{cid} {label}: late share cited for {e.get('name')}, which is null or flagged in the facts")
        # rule 2: a trend needs its base (how many of how many, or a named entity / single entity)
        multi = (uk.get("entities_n") or 0) > 1
        for label, text in units:
            if multi and TREND_RE.search(text) and not TREND_BASE_RE.search(text):
                errs.append(f"{cid} {label}: trend cited without its base (n of m entities, or the named entity)")
        # rule 5 / 6: no mechanics beyond the listed capabilities, no SAP implication
        for label, text in units:
            low = text.lower()
            for phrase in COPY_BANNED_PHRASES:
                if phrase in low:
                    errs.append(f"{cid} {label}: phrase '{phrase}' not allowed (review rules 5 and 6)")
            if re.search(r"\bSAP\b|S/4HANA", text):
                errs.append(f"{cid} {label}: mentions SAP (must not imply the target runs it)")
            if text.count("weighted by invoice value") and sum(t.count("weighted by invoice value") for _, t in units) > 1:
                errs.append(f"{cid} {label}: 'weighted by invoice value' used more than once in the account")
        if any("about 20% of invoices" in t for _, t in units):
            twenty_pct_accounts.append(cid)
    if len(twenty_pct_accounts) > 2:
        errs.append(f"'about 20% of invoices' line used in {len(twenty_pct_accounts)} accounts (max 2): {twenty_pct_accounts}")
    # variety: no opening three words used more than 3 times across the 60 bullets
    for op in set(openers):
        if openers.count(op) > 3:
            errs.append(f"variety: opening '{op}' used {openers.count(op)} times")
    return errs, stats


def check_rationales() -> tuple[list[str], dict]:
    errs: list[str] = []
    with TARGETS.open(newline="", encoding="utf-8") as f:
        targets = list(csv.DictReader(f))
    with RATIONALES.open(newline="", encoding="utf-8") as f:
        rows = list(csv.DictReader(f))
    stats = {"rows": len(rows), "numbers_checked": 0}
    if rows and list(rows[0].keys()) != ["company_id", "rationale"]:
        errs.append(f"columns are {list(rows[0].keys())}, expected company_id, rationale")
    # superset allowed (boundary accounts move between runs); every current top-100 account needs one
    by_id = {r["company_id"]: r for r in rows}
    if len(by_id) != len(rows):
        errs.append("duplicate company_id in rationales")
    tids = [t["company_id"] for t in targets]
    if set(tids) - set(by_id):
        errs.append(f"top-100 accounts without a rationale: {sorted(set(tids) - set(by_id))}")
    for t in targets:
        cid = t["company_id"]
        r = by_id.get(cid)
        if not r:
            continue
        text = r["rationale"]
        allowed: set[float] = set(BENCHMARKS)
        for col, val in t.items():
            # estimates must not be cited; the old template rationale is not a source
            if col.startswith("est_") or col in ("rationale", "estimate") or col.endswith("_url"):
                continue
            if col == "signals":
                try:
                    for s in json.loads(val or "[]"):
                        txt = re.sub(r"\d{4}-\d{2}-\d{2}", "", s.get("text", ""))
                        for n in NUM_RE.findall(txt):
                            allowed |= roundings(float(n))
                except json.JSONDecodeError:
                    pass
                continue
            try:
                v = float(val)
            except (TypeError, ValueError):
                continue
            if not math.isnan(v):
                allowed |= roundings(v)
        if words(text) > MAX_RATIONALE_WORDS:
            errs.append(f"{cid}: {words(text)} words > {MAX_RATIONALE_WORDS}")
        if sentences(text) != 2:
            errs.append(f"{cid}: {sentences(text)} sentences, expected 2")
        for e in style_errors(text):
            errs.append(f"{cid}: {e}")
        # review rule 4: no model scores or tier names as the reason
        if RATIONALE_SCORE_RE.search(text):
            errs.append(f"{cid}: cites the model's own score or tier")
        # review rule 1: no late-payment share when the row's late share is null
        if not (t.get("uk_pct_paid_late_mean") or "").strip() and t.get("pain_basis") == "uk_reported" and LATE_RE.search(text):
            errs.append(f"{cid}: late-payment argument but uk_pct_paid_late_mean is null")
        # review rule 2: trend needs its base unless the row has a single UK entity
        try:
            n_ent = int(float(t.get("uk_entities_n") or 0))
        except ValueError:
            n_ent = 0
        if n_ent > 1 and re.search(r"got slower|days (?:more|fewer|longer)|rose \d|fell \d", text) and not re.search(
            rf"\b{NUMWORD} of {NUMWORD}\b|\bboth\b|one entity with a prior report", text, re.I
        ):
            errs.append(f"{cid}: trend cited without its base (n of m entities)")
        if re.search(r"\b(EUR|USD|GBP|CHF)\b|[€$£]", text):
            errs.append(f"{cid}: money amount or currency (estimates are not allowed)")
        for n in numbers_in(text, allow_20_pct=False):
            stats["numbers_checked"] += 1
            if float(n) not in allowed:
                errs.append(f"{cid}: number {n} not a field value of the row")
    return errs, stats


def fingerprint(path: Path) -> str:
    h = hashlib.md5(path.read_bytes()).hexdigest()
    m = datetime.fromtimestamp(path.stat().st_mtime, timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    return f"`{path.relative_to(ROOT)}` md5 `{h}` modified {m}"


def main() -> int:
    e1, s1 = check_copy()
    e2, s2 = check_rationales()
    ok = not e1 and not e2
    now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    lines = [
        "# Copy validation",
        "",
        f"Run: {now}. Script: `evals/validate_copy.py`.",
        "",
        f"**Overall: {'PASS' if ok else 'FAIL'}**",
        "",
        "## Inputs this run validated against",
        "",
        "The texts are hand-written against these exact files. If a pipeline rerun changes them, rerun this script:",
        "it lists every text whose numbers no longer match.",
        "",
        *[f"- {fingerprint(p)}" for p in (FACTS, COPY, TARGETS, RATIONALES)],
        "",
        "## What was checked",
        "",
        "- `outputs/one_pagers/copy.json`: 20 keys matching `facts_for_copy.json`; exactly 3 bullets per account;",
        f"  each bullet one sentence of at most {MAX_BULLET_WORDS} words, no question; angle at most {MAX_ANGLE_WORDS} words;",
        "  three different product capabilities per account (keyword map in the script); no em or en dashes;",
        "  no banned words; no exclamation marks; no group-level 'pays in' claims; opening words not reused more than 3 times.",
        "- Every number in the text must equal a numeric value of that account's JSON (estimates block excluded,",
        "  numbers in the why-now signal texts included) rounded to 0 or 1 decimals. Allowed extras: the benchmarks 30, 32, 60,",
        "  the phrase 'about 20% of invoices' (share AP teams chase) and 'S/4HANA'.",
        f"- `data/processed/rationales_llm.csv`: 100 rows matching `target_list.csv`; 2 sentences, at most {MAX_RATIONALE_WORDS} words;",
        "  same style checks; no currency amounts; every number equals a field value of the same row (estimate columns and URLs",
        "  excluded, signal texts included) rounded to 0 or 1 decimals, sign expressed in words. Allowed extras: 30, 32, 60; the tier number is a row field.",
        "",
        "## Result",
        "",
        "| File | Items | Numbers checked | Errors | Result |",
        "|---|---|---|---|---|",
        f"| copy.json | {s1['accounts']} accounts, {s1['bullets']} bullets | {s1['numbers_checked']} | {len(e1)} | {'PASS' if not e1 else 'FAIL'} |",
        f"| rationales_llm.csv | {s2['rows']} rationales | {s2['numbers_checked']} | {len(e2)} | {'PASS' if not e2 else 'FAIL'} |",
        "",
        "## Rules added after the assets review (internal assets review, not in the public copy)",
        "",
        "- Rule 1 (late shares): if the group late share is null in the facts, no text of that account may argue from late payment;",
        "  an entity whose late share is null or carries `pct_paid_late_note` may not be named in a text that cites a late share.",
        "  The literal check 'no percentage equal to a nulled late share' is not feasible because the nulled value is no longer in the",
        "  facts; the number check already rejects any percentage that is not a value of the account. Same null rule for rationales.",
        "- Rule 2 (trend base): in multi-entity accounts a trend phrase needs 'n of m', 'both', 'all n' or a named entity in the same text.",
        "- Rule 4 (rationales): the words score, scores, scored, tier are rejected.",
        "- Rule 5: 'about 20% of invoices' in at most two accounts; 'one invitation', 'entity by entity' rejected.",
        "- Rule 6: any mention of SAP or S/4HANA in the copy is rejected.",
        "- 'weighted by invoice value' at most once per account.",
        "",
        "## Not machine-checked",
        "",
        "- Whether a correctly quoted number is attached to the right entity or metric (the check is on values, not on meaning).",
        "- Absence of personal names (written by rule: roles only; entity names are company names from the statutory reports).",
        "- Tone and neutrality beyond the banned-word list.",
        "",
    ]
    if e1 or e2:
        lines += ["## Failures", ""] + [f"- {e}" for e in e1 + e2] + [""]
    REPORT.parent.mkdir(parents=True, exist_ok=True)
    REPORT.write_text("\n".join(lines), encoding="utf-8")
    print(f"copy.json: {'PASS' if not e1 else 'FAIL'} ({len(e1)} errors, {s1['numbers_checked']} numbers checked)")
    print(f"rationales_llm.csv: {'PASS' if not e2 else 'FAIL'} ({len(e2)} errors, {s2['numbers_checked']} numbers checked)")
    for e in e1 + e2:
        print("  -", e)
    print("OVERALL:", "PASS" if ok else "FAIL")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
