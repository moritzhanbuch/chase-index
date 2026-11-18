"""Redact contact details and personal names from the public tabular data, in place. Run from the repo root.

  .venv/bin/python tools/redact_public.py

- UK filing free-text fields (*_text, dispute_process_text, suppliers_notified_text): emails, phone numbers (also when
  glued to a word, e.g. "dialing0121..."), title-prefixed names ("Mr J Smith") and the reviewed personal names in
  data/private/redact_names.txt (gitignored, one per line) become [email removed] / [phone removed] / [name removed].
- Every other string column of every csv/parquet: emails only (number patterns there are IDs, dates or filing numbers).
- Dispute-text hashes are recomputed from the redacted text and remapped in every hash-keyed file, so the LLM labels
  and the gold sample still join. Prints counts only, never the names.
"""
from __future__ import annotations

import hashlib
import pathlib
import re

import numpy as np
import pandas as pd

ROOT = pathlib.Path(__file__).resolve().parents[1]
EM = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}")
PH = re.compile(r"(?:\+\s?44\s?\(?0?\)?[\s-]?|\(?(?<!\d)0)(?:\d[\s()-]?){8,11}\d(?!\d)")
TITLED = re.compile(r"\b(?:Mr|Mrs|Ms|Miss|Dr)\.?\s+[A-Z][A-Za-z'\-]*\.?(?:\s+[A-Z][A-Za-z'\-]+){0,2}")
FREE_TEXT = re.compile(r"(_text$|^dispute_process_text$|^suppliers_notified_text$)")
NAMES_FILE = ROOT / "data" / "private" / "redact_names.txt"


def load_names():
    if not NAMES_FILE.exists():
        return None
    names = [l.strip() for l in NAMES_FILE.read_text().splitlines() if l.strip() and not l.startswith("#")]
    return re.compile(r"\b(?:" + "|".join(re.escape(n) for n in sorted(names, key=len, reverse=True)) + r")\b") if names else None


NAMES = load_names()
counts = {"email": 0, "phone": 0, "titled_name": 0, "listed_name": 0}


def norm(t):
    if t is None or (isinstance(t, float) and np.isnan(t)) or t is pd.NA:
        return ""
    return " ".join(str(t).lower().split())


def h(t):
    return hashlib.sha1(norm(t).encode("utf-8")).hexdigest()[:16]


def red_free(t):
    if not isinstance(t, str):
        return t
    t2, n1 = EM.subn("[email removed]", t)
    t2, n2 = PH.subn("[phone removed]", t2)
    t2, n3 = TITLED.subn("[name removed]", t2)
    n4 = 0
    if NAMES is not None:
        t2, n4 = NAMES.subn("[name removed]", t2)
    counts["email"] += n1; counts["phone"] += n2; counts["titled_name"] += n3; counts["listed_name"] += n4
    return t2


def red_email(t):
    if not isinstance(t, str):
        return t
    t2, n = EM.subn("[email removed]", t)
    counts["email"] += n
    return t2


def is_str(s):
    return s.dtype == object or str(s.dtype).startswith("str")


def main():
    hashmap: dict[str, str] = {}
    raw = ROOT / "data" / "processed" / "uk_payment_practices.parquet"
    d = pd.read_parquet(raw)
    col = "dispute_resolution_process_text"
    old = d[col].map(h)
    for c in d.columns:
        if FREE_TEXT.search(c) and is_str(d[c]):
            d[c] = d[c].map(red_free)
    new = d[col].map(h)
    hashmap.update({o: n for o, n in zip(old, new) if o != n})
    d.to_parquet(raw, index=False)
    changed_files = 1
    for p in sorted(ROOT.rglob("*")):
        rel = p.relative_to(ROOT)
        if (not p.is_file() or p.suffix not in (".csv", ".parquet") or p == raw
                or str(rel).startswith((".venv", "node_modules", "data/private", "data/raw", "data/cache", "tmp"))):
            continue
        try:
            d = pd.read_parquet(p) if p.suffix == ".parquet" else pd.read_csv(p, dtype=str, keep_default_na=False, low_memory=False)
        except Exception:
            continue
        changed = False
        for c in d.columns:
            if not is_str(d[c]):
                continue
            before = d[c].copy()
            d[c] = d[c].map(red_free if FREE_TEXT.search(c) else red_email)
            if c in ("dispute_text_hash", "text_hash"):
                d[c] = d[c].map(lambda v: hashmap.get(v, v))
            if not before.equals(d[c]):
                changed = True
        if changed:
            changed_files += 1
            d.to_parquet(p, index=False) if p.suffix == ".parquet" else d.to_csv(p, index=False)
    print(f"files changed: {changed_files} | remapped dispute hashes: {len(hashmap)} | redactions: {counts}"
          + ("" if NAMES is not None else " | no names list found (data/private/redact_names.txt)"))


if __name__ == "__main__":
    main()
