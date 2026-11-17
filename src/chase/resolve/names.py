"""Company-name normalisation used by every matching step.

Two keys per name:
- `norm(name)`: lowercased, accents stripped, punctuation removed, legal-form suffixes removed.
  "Siemens Aktiengesellschaft" -> "siemens"; "TESCO PLC" -> "tesco"; "Nestlé S.A." -> "nestle"
- `core(name)`: `norm` plus removal of generic descriptor words that UK subsidiaries carry
  ("uk", "holdings", "group", "services", "stores", ...). "Tesco Stores Limited" -> "tesco".
  `core` is deliberately lossy and is only used for conservative brand-level matching.
"""
from __future__ import annotations

import re
import unicodedata

LEGAL = {
    "limited", "ltd", "plc", "llp", "lp", "llc", "inc", "incorporated", "corp", "corporation", "co", "company",
    "ag", "se", "sa", "sau", "sas", "sarl", "nv", "bv", "gmbh", "kg", "kgaa", "spa", "srl", "ab", "asa", "as",
    "oyj", "oy", "aps", "a/s", "sl", "slu", "aktiengesellschaft", "societe", "anonyme", "sociedad", "anonima",
    "public", "the", "cv", "pte", "pty", "bhd", "kk", "tbk", "ord", "shs", "adr", "nvsa", "europaea",
    "societas", "europea", "mbh", "cie", "and", "und", "et", "y", "of", "de", "la", "le", "del", "holding",
}
GENERIC = {
    "uk", "gb", "britain", "great", "united", "kingdom", "england", "europe", "european", "international", "global",
    "worldwide", "group", "holdings", "services", "service", "stores", "store", "retail", "retailing", "operations",
    "operating", "trading", "distribution", "manufacturing", "products", "solutions", "systems", "management",
    "limited", "enterprises", "industries", "supply", "logistics", "sales", "marketing", "ireland", "northern",
    "emea", "no", "number", "one", "two", "1", "2", "3", "commercial", "business", "customer", "support",
    "central", "shared", "corporate", "finance", "financial", "investments", "properties", "property",
}

_PAREN = re.compile(r"\([^)]*\)")
_NONWORD = re.compile(r"[^a-z0-9& ]+")
_WS = re.compile(r"\s+")


def strip_accents(s: str) -> str:
    return "".join(c for c in unicodedata.normalize("NFKD", s) if not unicodedata.combining(c))


def _tokens(name: str) -> list[str]:
    s = strip_accents(str(name)).lower()
    s = s.replace("&", " & ").replace("’", "'").replace("'s ", "s ").replace("'", "")
    s = _PAREN.sub(" ", s)
    s = re.sub(r"\b([a-z])\.(?=[a-z]\b|[a-z]\.)", r"\1", s)  # s.a. -> sa, p.l.c. -> plc
    s = s.replace(".", " ") if not re.search(r"\b[a-z]{2,}\.com\b", s) else s.replace(".com", "com").replace(".", " ")
    s = _NONWORD.sub(" ", s)
    return [t for t in _WS.sub(" ", s).strip().split(" ") if t]


def norm(name: str | None) -> str:
    if not name:
        return ""
    toks = _tokens(name)
    out = [t for t in toks if t not in LEGAL and t != "&"]
    return " ".join(out) if out else " ".join(toks)


def core(name: str | None) -> str:
    if not name:
        return ""
    toks = [t for t in norm(name).split(" ") if t]
    out = [t for t in toks if t not in GENERIC]
    return " ".join(out) if out else " ".join(toks)
