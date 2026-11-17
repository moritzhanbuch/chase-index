"""Spain PMP (periodo medio de pago a proveedores): deterministic extractor A.

Extractor "A" of the dual-extractor setup (CLAUDE.md, phase 4). Everything in
the output comes out of this code: text search, regular expressions and HTML
table parsing. No LLM, no network, no hand-typed values.

Run:  python -m chase.sources.spain_pmp

How it works
------------
1. Each source document (ESEF xBRL-JSON text-block facts, or a saved IR web
   page) is linearised into "rows":
   * every innermost HTML ``<tr>`` becomes a row of cells (table mode);
   * text outside tables is cut into pseudo-rows "label text + run of numbers"
     (flow mode, needed for PDF-to-HTML conversions without ``<table>``).
2. Row labels are normalised (lowercase, accents stripped, footnote marks and
   trailing parentheticals removed) and matched against Spanish and English
   label patterns anchored at the END of the label.
3. Every row with a PMP label and at least one number in (0, 400) opens a
   candidate block. Ratios, totals and the Ley 18/2022 percentages are looked
   up in the same table first, then in the rows that follow (until the next
   PMP row).
4. If no table/flow candidate exists, sentence patterns ("... durante el
   ejercicio 2025 es de 26 dias") are tried (prose mode).
5. Candidates are de-duplicated and ranked by scope; the best one is written
   out with sanity checks and a rule-based confidence.

Confidence rules (see ``score_confidence``)
-------------------------------------------
* 0.90  PMP and both ratios found in one block, PMP lies between the two
        ratios (0.5-day tolerance).
* +0.05 payments made and pending also found and the recomputed PMP
        (ratio_paid*paid + ratio_pending*pending)/(paid+pending) is within
        1 day of the stated PMP.
* 0.75  as 0.90, but the recomputed PMP is more than 1 day off.
* 0.50  PMP and both ratios found, but PMP is NOT between the ratios.
* 0.70  PMP found in a table/flow block with only one or no ratio.
* 0.75  prose sentence with PMP and consistent ratios; 0.60 prose PMP only.
* -0.10 column order could not be read from a year header (current year
        assumed to be the first column).
* -0.05 more than one distinct PMP table in the document.
* 0.00  PMP not found or outside (0, 400).
* -0.05 a ratio was found outside the PMP table (following table).

Judgement calls worth knowing
-----------------------------
* When a document prints several PMP tables, group-level beats unknown beats
  parent-only; a table whose header marks a subset ("solo nacionales") loses;
  otherwise the first table in the document wins. The others are listed in
  ``notes`` with their header and PMP.
* ``scope`` is read from the disclosure's own preamble only. If that text
  does not say it, scope is "unknown" (``source_document_scope`` repeats what
  the sourcing step recorded for the document).
* Percentages are classified by their own row label, even where the source
  seems to have swapped labels (a note is added).
* A lone separator followed by three digits is a thousands mark for money
  and counts and a decimal mark for days and percentages.
"""
from __future__ import annotations

import csv
import json
import re
import sys
import time
import unicodedata
from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterable

import lxml.html

ROOT = Path(__file__).resolve().parents[3]
SOURCES_CSV = ROOT / "data/interim/es_pmp_sources.csv"
OUT_JSON = ROOT / "data/interim/es_extract_a.json"
OUT_CSV = ROOT / "data/interim/es_extract_a.csv"
OUT_META = ROOT / "data/interim/es_extract_a_meta.json"

EXTRACTION_METHOD = "regex_table_parse"

OUTPUT_FIELDS = [
    "ticker", "company_name", "fiscal_year", "pmp_days", "ratio_paid_days",
    "ratio_pending_days", "total_payments_made", "total_payments_pending",
    "money_unit", "money_unit_raw", "money_unit_basis",
    "pct_invoices_paid_within_legal_max_by_value",
    "pct_invoices_paid_within_legal_max_by_number",
    "prior_year_pmp_days", "prior_fiscal_year", "scope", "scope_basis",
    "source_document_scope",
    "language", "source_url", "local_path", "location", "quoted_snippet",
    "extraction_method", "extraction_mode", "confidence",
    "check_pmp_in_range", "check_pmp_between_ratios", "pmp_recomputed",
    "check_recomputed_within_1_day", "fiscal_year_basis", "n_pmp_tables",
    "evidence_rows", "notes",
]

# --------------------------------------------------------------------------
# text helpers
# --------------------------------------------------------------------------


def strip_accents(s: str) -> str:
    s = unicodedata.normalize("NFKD", s)
    return "".join(c for c in s if not unicodedata.combining(c))


def squash(s: str) -> str:
    """Collapse all whitespace (incl. non-breaking) to single spaces."""
    return re.sub(r"[\s ​  ]+", " ", s).strip()


def norm_keep(s: str) -> str:
    """Like ``norm`` but length-preserving (one output char per input char),
    so regex offsets found on the result index the original string."""
    out = []
    for ch in s:
        n = strip_accents(ch).lower()
        out.append(n if len(n) == 1 else (ch.lower() if len(ch.lower()) == 1 else "?"))
    return "".join(out)


def norm(s: str) -> str:
    """Lowercase, accent-free, whitespace-collapsed form used for matching."""
    return squash(strip_accents(s)).lower()


_TRAILING_JUNK = re.compile(
    r"\s*(\([^()]{0,60}\)|\[[^\[\]]{0,10}\]|\*+|:|\.|[¹²³])\s*$"
)


def label_core(label: str) -> str:
    """Normalise a row label and strip trailing footnotes / parentheticals.

    "Periodo medio de pago a proveedores (dias) (1)" -> "periodo medio de pago
    a proveedores".
    """
    s = norm(label)
    while True:
        new = _TRAILING_JUNK.sub("", s)
        if new == s:
            break
        s = new
    return s.strip()


# --------------------------------------------------------------------------
# number parsing
# --------------------------------------------------------------------------

_UNIT_WORDS = re.compile(r"(?i)\b(d\s?[ií]\s?as?|days?|eur(os)?)\b|%|€|\$")
_WELL_FORMED = re.compile(r"^\d{1,3}(?:[.,]\d{3})+(?:[.,]\d+)?$|^\d+(?:[.,]\d+)?$")


def collapse_letter_spacing(s: str) -> str:
    """Remove letter-spacing artefacts inside ONE numeric cell.

    "2 1 .0 91" -> "21.091". Only collapses when it is safe:
    * the cell holds nothing but digits, separators and spaces;
    * the collapsed string is one well-formed number;
    * the space-separated pieces are not themselves two or more complete
      numbers with decimals or grouping (e.g. "37,07 37,51" stays untouched),
      and not plain integers that could be two columns (e.g. "37 38").
    A lone space used as thousands separator ("1 234 567") is collapsed.
    """
    t = squash(s)
    if " " not in t:
        return t
    if not re.fullmatch(r"[\d.,\s]+", t):
        return t
    pieces = t.split(" ")
    collapsed = "".join(pieces)
    if not _WELL_FORMED.match(collapsed):
        return t
    # space as thousands separator: 1-3 digits then groups of exactly 3 digits
    if re.fullmatch(r"\d{1,3}( \d{3})+([.,]\d+)?", t):
        return collapsed
    # every piece a complete number on its own -> probably several columns
    if all(re.fullmatch(r"\d+(?:[.,]\d+)*", p) for p in pieces):
        return t
    return collapsed


def parse_number_ex(raw: str, lang: str = "es", kind: str | None = None):
    """Parse a Spanish- or English-formatted number.

    kind: "days" / "pct" (a lone separator is always a decimal mark),
          "money" / "count" (a lone separator followed by exactly three
          digits is always a thousands mark), or None (use the language
          convention: es -> '.' thousands and ',' decimal; en -> reverse).
    Returns (value or None, set of flags).
    """
    flags: set[str] = set()
    if raw is None:
        return None, flags
    s = squash(str(raw))
    s = _UNIT_WORDS.sub(" ", s)
    s = squash(s)
    neg = False
    m = re.fullmatch(r"\((.*)\)", s)
    if m:
        neg, s = True, m.group(1).strip()
    if s.startswith(("-", "−", "–")) and len(s) > 1:
        neg, s = True, s[1:].strip()
    before = s
    s = collapse_letter_spacing(s)
    if s != before:
        flags.add("letter_spacing_collapsed")
    if not re.fullmatch(r"\d[\d.,]*", s) or not re.search(r"\d$", s):
        return None, flags
    n_dot, n_com = s.count("."), s.count(",")
    if n_dot and n_com:
        dec = "." if s.rfind(".") > s.rfind(",") else ","
        tho = "," if dec == "." else "."
        if s.count(dec) > 1:
            return None, flags
        s2 = s.replace(tho, "").replace(dec, ".")
    elif n_dot + n_com == 0:
        s2 = s
    else:
        sep = "." if n_dot else ","
        cnt = n_dot or n_com
        parts = s.split(sep)
        grouped = all(len(p) == 3 for p in parts[1:]) and 1 <= len(parts[0]) <= 3
        lang_thousands = "." if lang == "es" else ","
        if cnt > 1:
            if not grouped:
                return None, flags
            s2 = "".join(parts)
        elif not grouped:
            s2 = s.replace(sep, ".")  # e.g. 37,07 or 45.3: must be a decimal
        else:
            # ambiguous: one separator followed by exactly three digits
            if kind in ("days", "pct"):
                as_thousands = False
            elif kind in ("money", "count"):
                as_thousands = True
                if sep != lang_thousands:
                    flags.add("separator_against_language_convention")
            else:
                as_thousands = sep == lang_thousands
            s2 = "".join(parts) if as_thousands else s.replace(sep, ".")
    try:
        v = float(s2)
    except ValueError:
        return None, flags
    return (-v if neg else v), flags


def parse_number(raw: str, lang: str = "es", kind: str | None = None):
    return parse_number_ex(raw, lang, kind)[0]


# --------------------------------------------------------------------------
# label matching
# --------------------------------------------------------------------------

_PMP = (
    r"(?:periodo|plazo) medio de pagos?(?: a (?:los )?proveedores)?(?: pmp)?"
    r"|average (?:supplier )?payment period(?: (?:to|for) suppliers)?"
    r"|average period (?:of|for) payment(?: to suppliers)?"
    r"|average (?:payment )?period (?:to|for) suppliers"
)
_RATIO_PAID = (
    r"ratio de (?:las )?operaciones pagadas"
    r"|ratio of (?:transactions|operations|payments) (?:paid|settled)"
    r"|ratio of (?:paid|settled) (?:transactions|operations)"
    r"|(?:paid|settled) (?:transactions|operations) ratio"
)
_RATIO_PENDING = (
    r"ratio de (?:las )?operaciones pendientes(?: de pago)?"
    r"|ratio of (?:transactions|operations) (?:pending|outstanding)(?: (?:of )?payment)?"
    r"|ratio of (?:pending|outstanding|unpaid) (?:transactions|operations|payments)"
    r"|(?:pending|outstanding) (?:transactions|operations) ratio"
)
_TOTAL_PENDING = (
    r"(?<!sobre el )(?<!y los )(?:(?:importe )?total (?:de )?)?pagos pendientes(?: de pago)?"
    r"|total (?:payments (?:pending|outstanding)|(?:pending|outstanding) payments)"
)
_TOTAL_PAID = (
    r"(?<!sobre el )(?<!frente a )(?<!frente al )total (?:de )?pagos(?: realizados)?"
    r"|total payments(?: made)?"
)

LABEL_PATTERNS = [  # order matters: more specific first
    ("pmp", re.compile(r"(?:^|[\s(])(?:" + _PMP + r")$")),
    ("ratio_pending", re.compile(r"(?:^|[\s(])(?:" + _RATIO_PENDING + r")$")),
    ("ratio_paid", re.compile(r"(?:^|[\s(])(?:" + _RATIO_PAID + r")$")),
    ("total_pending", re.compile(r"(?:^|[\s(])(?:" + _TOTAL_PENDING + r")$")),
    ("total_paid", re.compile(r"(?:^|[\s(])(?:" + _TOTAL_PAID + r")$")),
]

_PCT_LABEL = re.compile(r"porcentaje|percentage|(?:^|\s)%|\bpct\b")
_WITHIN_LEGAL = re.compile(
    r"pagad[ao]s? (?:en|dentro de) (?:el |un )?(?:plazo|periodo)|paid within"
)


def is_pct_cell(raw: str) -> bool:
    return "%" in raw


_FLOW_PCT_START = re.compile(r"^(?:\([^()]{0,40}\)\s*)?(?:porcentaje|percentage|%)")


def classify_label(label: str, cells_raw: Iterable[str] = (), flow: bool = False) -> str | None:
    """Return the field a row label stands for, or None.

    Result: "pmp", "ratio_paid", "ratio_pending", "total_paid",
    "total_pending", "pct_by_value", "pct_by_number", "within_legal_mixed".
    Percentage rows are recognised first so that a label ending in
    "... sobre el total de pagos realizados" is never read as a total.
    """
    core = label_core(label)
    if not core:
        return None
    cells_raw = [c for c in cells_raw if squash(c)]
    n_pct = sum(1 for c in cells_raw if is_pct_cell(c))
    all_pct = bool(cells_raw) and n_pct == len(cells_raw)
    full = norm(label)
    if _PCT_LABEL.search(full) or all_pct:
        # in running text a percentage is only trusted when the label is
        # table-like: it starts with "Porcentaje"/"%" and is one phrase
        if flow and (not _FLOW_PCT_START.search(full) or ". " in full):
            return None
        if re.search(r"numero|\bnumber\b", full):
            return "pct_by_number"
        if re.search(r"importe|monetario|pagos|volumen|amount|value|payments", full):
            return "pct_by_value"
        if re.search(r"facturas|invoices", full):
            return "pct_by_number"
        return None
    if n_pct >= 2 and _WITHIN_LEGAL.search(core):
        return "within_legal_mixed"
    for kind, pat in LABEL_PATTERNS:
        if pat.search(core):
            return kind
    return None


# --------------------------------------------------------------------------
# linearisation: HTML -> rows
# --------------------------------------------------------------------------


@dataclass
class Row:
    label: str
    cells: list[str]            # raw value cells (label excluded)
    text: str                   # full row text, cells joined with " | "
    offset: int                 # char offset in the linearised text of the fact
    table_id: int | None        # None for flow (non-table) rows
    kind: str | None = None
    all_cells: list[str] = field(default_factory=list)


_BLOCK_TAGS = {
    "div", "p", "br", "td", "th", "tr", "li", "ul", "ol", "h1", "h2", "h3",
    "h4", "h5", "h6", "section", "article", "table", "tbody", "thead",
}
_NUM_TOKEN = r"(?<![\w/.,])\d+(?:[.,]\d+)*(?![\w/]|[.,]\d)"
_VALUE_RUN = re.compile(
    r"(?:" + _NUM_TOKEN + r"\s*(?:%|d\s?[ií]\s?as\b|days\b)?\s*)+", re.I
)
_VALUE_TOKEN = re.compile(_NUM_TOKEN + r"\s*(?:%|d\s?[ií]\s?as\b|days\b)?", re.I)
_FOOTNOTE_MARK = re.compile(r"\(\s*(?:\d{1,2}|\*+)\s*\)")


def flow_rows(text: str, base_offset: int = 0) -> list[Row]:
    """Cut running text into pseudo-rows: label text + following numbers."""
    rows: list[Row] = []
    text = _FOOTNOTE_MARK.sub(" ", text)
    prev_end = 0
    for m in _VALUE_RUN.finditer(text):
        label = squash(text[prev_end:m.start()])[-400:]
        cells = [squash(t.group(0)) for t in _VALUE_TOKEN.finditer(m.group(0))]
        run = squash(m.group(0))
        rows.append(Row(label=label, cells=cells, text=squash(label + " " + run),
                        offset=base_offset + max(prev_end, m.start() - len(label)),
                        table_id=None, all_cells=[label] + cells))
        prev_end = m.end()
    return rows


def _localname(el) -> str:
    tag = el.tag
    if not isinstance(tag, str):
        return ""
    return tag.rsplit("}", 1)[-1].lower()


def linearize(html: str) -> list[Row]:
    """Turn an (X)HTML fragment into table rows and flow pseudo-rows."""
    try:
        root = lxml.html.fragment_fromstring(html, create_parent="div")
    except Exception:  # noqa: BLE001  (malformed fragment: no rows)
        return []
    rows: list[Row] = []
    buf: list[str] = []
    state = {"offset": 0, "table_id": 0}

    def flush():
        text = squash("".join(buf))
        buf.clear()
        if text:
            rows.extend(flow_rows(text, state["offset"]))
            state["offset"] += len(text) + 1

    def emit_table(table):
        flush()
        state["table_id"] += 1
        tid = state["table_id"]
        for tr in table.iter():
            if _localname(tr) != "tr":
                continue
            if any(_localname(d) == "tr" for d in tr.iterdescendants()):
                continue
            cells = [squash(c.text_content()) for c in tr
                     if _localname(c) in ("td", "th")]
            cells = [c for c in cells if c]
            if not cells:
                continue
            label_idx = next((i for i, c in enumerate(cells)
                              if re.search(r"[^\W\d_]{2,}", c)), None)
            label = cells[label_idx] if label_idx is not None else ""
            values = [c for i, c in enumerate(cells) if i != label_idx]
            text = " | ".join(cells)
            rows.append(Row(label=label, cells=values, text=text,
                            offset=state["offset"], table_id=tid, all_cells=cells))
            state["offset"] += len(text) + 1

    def walk(el):
        name = _localname(el)
        if not name or name in ("script", "style", "noscript"):
            return
        if name == "table":
            emit_table(el)
            return
        block = name in _BLOCK_TAGS
        if block:
            buf.append(" ")
        buf.append(el.text or "")
        for ch in el:
            walk(ch)
            buf.append(ch.tail or "")
        if block:
            buf.append(" ")

    old = sys.getrecursionlimit()
    sys.setrecursionlimit(max(old, 10000))
    try:
        walk(root)
    finally:
        sys.setrecursionlimit(old)
    flush()
    for r in rows:
        r.kind = classify_label(r.label, r.cells, flow=r.table_id is None)
    return rows


# --------------------------------------------------------------------------
# candidate blocks
# --------------------------------------------------------------------------

_YEAR = re.compile(
    r"(?<!\d)\d{1,2}[/.-]\d{1,2}[/.-](20\d\d)(?!\d)"      # 31/12/2025, 31.12.2025
    r"|(?<![\d/.,-])(20\d\d)(?![\d/]|[.,]\d)"             # plain year, not "15/2010"
)


def find_years(text: str) -> list[int]:
    return [int(a or b) for a, b in _YEAR.findall(text)]
_UNIT_PATTERNS = [
    (re.compile(r"miles de (?:euros|€|eur)|thousands? of euros|euros? thousands?|"
                r"(?:€|eur) ?thousands?|thousand (?:euros|eur)|€ ?000|000 ?€|\bk€"), "thousands EUR"),
    (re.compile(r"millones de (?:euros|€|eur)|millions? of euros|euros? millions?|"
                r"(?:€|eur) ?millions?|million (?:euros|eur)|\bmm ?€"), "millions EUR"),
    (re.compile(r"\((?:en )?euros\)|importes? (?:en )?\(?euros\)?|\(eur\)|in euros|en euros"), "EUR"),
]
# case-sensitive abbreviations, matched on the accent-free but NOT lowercased text
_UNIT_ABBREV = [
    (re.compile(r"(?<![A-Za-z])m ?€"), "thousands EUR"),   # Spanish "m €" = miles
    (re.compile(r"(?<![A-Za-z])M ?€"), "millions EUR"),
]

_SCOPE_SPANISH = re.compile(
    r"ambito nacional|solo nacionales|en espana\b|sociedades espanolas|entidades espanolas|"
    r"companias espanolas|empresas espanolas|radicadas en espana|domiciliadas en espana|"
    r"domicilio(?: social)? en espana|territorio espanol|territorio nacional|"
    r"sociedades (?:del grupo )?(?:con domicilio|domiciliadas|residentes|radicadas)|"
    r"spanish (?:companies|entities|subsidiaries)|in spain\b|located in spain"
)
_SCOPE_GROUP = re.compile(
    r"sociedades del grupo|entidades del grupo|\bdel grupo\b|\bel grupo\b|consolidad|"
    r"sociedades dependientes|\bgroup\b|consolidated"
)
_SCOPE_PARENT_SENTENCE = re.compile(
    r"(?:periodo|plazo) medio de pagos? a (?:los )?proveedores de (?P<ent>.{3,100}?s\.? ?a\.?u?\.?),? durante"
)


def find_unit(text: str):
    """Last money-unit mention in ``text``. Returns (unit, raw) or (None, None)."""
    best = (None, None, -1)
    low = norm(text)
    for pat, unit in _UNIT_PATTERNS:
        for m in pat.finditer(low):
            if m.start() > best[2]:
                best = (unit, m.group(0), m.start())
    cased = squash(strip_accents(text))
    for pat, unit in _UNIT_ABBREV:
        for m in pat.finditer(cased):
            if m.start() > best[2]:
                best = (unit, m.group(0), m.start())
    return best[0], best[1]


_SCOPE_ANCHOR = re.compile(
    r"aplazamientos? de pago|(?:periodo|plazo) medio de pago|deber de informacion|ley 15/2010|"
    r"ley 31/2014|ley 18/2022|payment period|law 15/2010")


def detect_scope(context: str):
    """Scope from the text before the PMP row. Returns (scope, basis).

    Only the part of the context that belongs to the disclosure is used: from
    the first mention of the disclosure (law reference, "periodo medio de
    pago", "aplazamientos de pago") onwards, or the last 300 characters if no
    such anchor exists. This keeps unrelated "en Espana" mentions out.
    """
    c = norm(context)
    a = _SCOPE_ANCHOR.search(c)
    c = c[max(0, a.start() - 60):] if a else c[-300:]
    m = _SCOPE_SPANISH.search(c)
    if m:
        return "consolidated_spanish_entities", f"explicit: '{m.group(0)}'"
    m = _SCOPE_GROUP.search(c)
    if m:
        return ("consolidated_spanish_entities",
                f"group keyword only: '{m.group(0)}' (restriction to Spanish entities not stated near the table)")
    return "unknown", None


@dataclass
class Candidate:
    mode: str                       # table / flow / prose
    fact_id: str | None
    concept: str | None
    offset: int
    snippet: str
    lang: str
    values: dict = field(default_factory=dict)
    years: list[int] = field(default_factory=list)
    year_basis: str = "header"
    scope: str = "unknown"
    scope_basis: str | None = None
    same_block: dict = field(default_factory=dict)   # field -> found in same table/flow block
    unit: str | None = None
    unit_raw: str | None = None
    unit_basis: str | None = None
    notes: list[str] = field(default_factory=list)
    evidence: dict = field(default_factory=dict)      # field -> row text it was read from
    header_hint: str = ""
    fact_rank: int = 0

    def key(self):
        v = self.values
        return (v.get("pmp_days"), v.get("prior_year_pmp_days"),
                v.get("ratio_paid_days"), v.get("ratio_pending_days"))

    def filled(self):
        return sum(1 for x in self.values.values() if x is not None)


_NIL_CELL = re.compile(r"^(?:[-\u2013\u2014\u2212]+|n/?a\.?|n\.?d\.?|sin dato)$", re.I)


def _nums(cells, lang, kind):
    """Positional numbers of a row: one entry per numeric-looking cell.

    A cell that holds digits but cannot be parsed, or a nil mark ("-"), keeps
    its position as None so that columns never shift. Text cells are skipped.
    """
    out, flags = [], set()
    for c in cells:
        c = squash(c)
        if _NIL_CELL.match(c):
            out.append(None)
            continue
        if not re.search(r"\d", c):
            continue
        v, f = parse_number_ex(c, lang, kind)
        out.append(v)
        flags |= f
    return out, flags


def _years_before(rows, i, fy_hint):
    """Year header tokens that precede PMP row ``i`` (document order)."""
    r = rows[i]
    if r.table_id is not None:
        j = i
        while j > 0 and rows[j - 1].table_id == r.table_id:
            j -= 1
        text = " ".join(x.text for x in rows[j:i])
        if not find_years(text) and j > 0:
            text = rows[j - 1].text[-200:] + " " + text
    else:
        prev = " ".join(rows[i - 1].cells) if i > 0 else ""
        text = prev + " " + r.label
    years = find_years(text)
    if fy_hint:
        years = [y for y in years if fy_hint - 6 <= y <= fy_hint + 1]
    return years


def _pick(values, n_cols, idx):
    """Value for column ``idx`` out of a row with len(values) numbers."""
    if not values or idx is None:
        return None
    if len(values) == n_cols:
        return values[idx]
    if n_cols and len(values) == 2 * n_cols:      # amount/count interleaved per year
        return values[2 * idx]
    if idx == 0:
        return values[0]
    return None


def build_candidates(rows: list[Row], fy_hint: int | None, fact_id=None,
                     concept=None, fact_rank=0) -> list[Candidate]:
    cands: list[Candidate] = []
    pmp_idx = []
    for i, r in enumerate(rows):
        if r.kind != "pmp":
            continue
        lang = "es" if "medio" in norm(r.label) else "en"
        vals, _ = _nums(r.cells, lang, "days")
        good = [x for x in vals if x is not None]
        if good and all(0 < x < 400 for x in good):
            pmp_idx.append(i)
    for n, i in enumerate(pmp_idx):
        r = rows[i]
        lang = "es" if "medio" in norm(r.label) else "en"
        pmp_vals, flags = _nums(r.cells, lang, "days")
        n_cols = len(pmp_vals)
        cand = Candidate(mode="table" if r.table_id is not None else "flow",
                         fact_id=fact_id, concept=concept, offset=r.offset,
                         snippet=r.text[-200:] if r.table_id is None else r.text[:200],
                         lang=lang, fact_rank=fact_rank)
        if "letter_spacing_collapsed" in flags:
            cand.notes.append("letter-spacing collapsed in PMP cell")
        # ---- column order from year header
        years = _years_before(rows, i, fy_hint)
        if len(years) >= n_cols and len(set(years[-n_cols:])) == n_cols:
            cols = years[-n_cols:]
            cur_idx = cols.index(max(cols))
            cur_year = cols[cur_idx]
            prior_idx = cols.index(cur_year - 1) if (cur_year - 1) in cols else None
            cand.years, cand.year_basis = cols, "header"
        else:
            cur_idx, prior_idx = 0, (1 if n_cols >= 2 else None)
            cur_year = fy_hint
            cand.year_basis = "assumed_current_year_first"
            cand.notes.append(
                f"year header not readable ({len(years)} year tokens for {n_cols} value columns): "
                "first column assumed to be the source fiscal year")
        if pmp_vals[cur_idx] is None:
            continue                      # current-year cell unreadable: no candidate
        v = cand.values
        v["fiscal_year"] = cur_year
        v["pmp_days"] = pmp_vals[cur_idx]
        cand.evidence["pmp_days"] = r.text[-160:]
        v["prior_year_pmp_days"] = pmp_vals[prior_idx] if prior_idx is not None else None
        v["prior_fiscal_year"] = (cur_year - 1) if (v["prior_year_pmp_days"] is not None and cur_year) else None
        # ---- block: same table (any position) first, then rows that follow
        end = pmp_idx[n + 1] if n + 1 < len(pmp_idx) else len(rows)
        if r.table_id is not None:
            j0 = i
            while j0 > 0 and rows[j0 - 1].table_id == r.table_id:
                j0 -= 1
            j1 = i
            while j1 + 1 < len(rows) and rows[j1 + 1].table_id == r.table_id:
                j1 += 1
            j1 = min(j1, end - 1)
            prev_end = pmp_idx[n - 1] if n > 0 else -1
            j0 = max(j0, prev_end + 1)
            same = list(range(i + 1, j1 + 1)) + list(range(j0, i))
        else:
            j0, j1 = i, i
            same = []
            prev_end = pmp_idx[n - 1] if n > 0 else -1
        after = [j for j in range(j1 + 1, end)
                 if rows[j].offset - r.offset <= 8000 and j - i <= 80]
        # tables placed just before the PMP table (totals first, days second)
        before = [j for j in range(j0 - 1, prev_end, -1)
                  if rows[j].table_id is not None and r.offset - rows[j].offset <= 3000]
        before.reverse()
        if r.table_id is None:
            same, after, before = after, [], []   # flow: everything that follows is "the block"
        targets = {
            "ratio_paid": ("ratio_paid_days", "days"),
            "ratio_pending": ("ratio_pending_days", "days"),
            "total_paid": ("total_payments_made", "money"),
            "total_pending": ("total_payments_pending", "money"),
            "pct_by_value": ("pct_invoices_paid_within_legal_max_by_value", "pct"),
            "pct_by_number": ("pct_invoices_paid_within_legal_max_by_number", "pct"),
        }
        found_row: dict[str, int] = {}
        for where, idxs in (("same", same), ("after", after), ("before", before)):
            for j in idxs:
                row = rows[j]
                if row.kind == "within_legal_mixed":
                    _mixed_row(rows, j, cand, lang, n_cols, cur_idx, where)
                    continue
                if row.kind not in targets:
                    continue
                name, kind = targets[row.kind]
                if v.get(name) is not None:
                    continue
                vals, fl = _nums(row.cells, lang, kind)
                val = _pick(vals, n_cols, cur_idx)
                if val is None:
                    continue
                if kind == "days" and not (0 <= val < 2000):
                    continue
                if kind == "pct" and not (0 <= val <= 100):
                    continue
                v[name] = val
                cand.same_block[name] = where == "same"
                cand.evidence[name] = row.text[-160:]
                found_row[name] = j
                if kind == "pct" and j > 0 and rows[j - 1].kind not in ("pct_by_value", "pct_by_number"):
                    prev_label = norm(rows[j - 1].label)
                    prev_is_number = bool(re.search(r"numero|\bn o\b|\bnumber\b", prev_label))
                    prev_is_value = bool(re.search(r"monetario|importe|amount", prev_label)) and not prev_is_number
                    if (row.kind == "pct_by_number" and prev_is_value) or \
                            (row.kind == "pct_by_value" and prev_is_number):
                        cand.notes.append(
                            f"{name}: classified by its own label, but the row above it is about "
                            f"{'amounts' if prev_is_value else 'invoice counts'} "
                            "(labels may be swapped in the source)")
                if "separator_against_language_convention" in fl:
                    cand.notes.append(
                        f"{name}: thousands separator differs from the document's number format "
                        f"(row: '{row.text[:80]}')")
                if "letter_spacing_collapsed" in fl:
                    cand.notes.append(f"{name}: letter-spacing collapsed")
        # percentages still missing: the Ley 18/2022 table may sit after a
        # second PMP table of the same note (shared by both); flagged in notes
        for j in range(end, len(rows)):
            row = rows[j]
            if rows[j].offset - r.offset > 8000:
                break
            if row.kind not in ("pct_by_value", "pct_by_number"):
                continue
            name, kind = targets[row.kind]
            if v.get(name) is not None:
                continue
            vals, _fl = _nums(row.cells, lang, kind)
            val = _pick(vals, n_cols, cur_idx)
            if val is None or not (0 <= val <= 100):
                continue
            v[name] = val
            cand.same_block[name] = False
            cand.evidence[name] = row.text[-160:]
            cand.notes.append(f"{name}: row sits after another PMP table of the same note "
                              "(may refer to either table)")
        for name, _k in targets.values():
            v.setdefault(name, None)
        # ---- percentages given in a sentence/footnote rather than in a row
        tail = " ".join(rows[j].text for j in range(i, end)
                        if rows[j].offset - r.offset <= 8000)
        for name, val, quote in prose_pcts(tail, lang, cur_year):
            if v.get(name) is None:
                v[name] = val
                cand.same_block[name] = False
                cand.evidence[name] = quote[:160]
                cand.notes.append(f"{name}: read from a sentence, not from a table row")
        # ---- money unit: last mention between block start and the totals row
        tot_j = found_row.get("total_payments_made", found_row.get("total_payments_pending"))
        if tot_j is not None:
            start = min(j0, tot_j, i)
            if rows[tot_j].table_id is not None:
                while start > 0 and rows[start - 1].table_id == rows[tot_j].table_id:
                    start -= 1
            lo, hi = min(start, tot_j), tot_j
            block_text = " \n ".join(rows[k].text for k in range(lo, hi)) + " \n " + rows[tot_j].label
            unit, raw = find_unit(block_text)
            basis = "stated in the table/block header"
            if unit is None:
                pre = " ".join(rows[k].text for k in range(max(0, lo - 6), lo))[-600:]
                unit, raw = find_unit(pre)
                basis = "inferred from the text just before the table (not stated in the table itself)"
            cand.unit, cand.unit_raw, cand.unit_basis = unit, raw, (basis if unit else None)
        # ---- scope from preceding text
        ctx = []
        size = 0
        k = i
        while k >= 0 and size < 1500:
            t = rows[k].label if k == i else rows[k].text
            ctx.append(t)
            size += len(t)
            k -= 1
        context = " ".join(reversed(ctx))[-1500:]
        cand.scope, cand.scope_basis = detect_scope(context)
        cand.header_hint = squash(" ".join(rows[k].text for k in range(max(j0, i - 3), i)))[:120] \
            if r.table_id is not None else squash(r.label)[-120:]
        cands.append(cand)
    return cands


def _mixed_row(rows, j, cand, lang, n_cols, cur_idx, where):
    """Row like 'pagadas en el plazo legal | 3.396 | 93,5 % | 1.433.816 | 96,0 %'.

    The order amount/number is read from the nearest header row of the same
    table that names both; without such a header nothing is taken.
    """
    row = rows[j]
    pcts = [parse_number(c, lang, "pct") for c in row.cells if is_pct_cell(c)]
    pcts = [p for p in pcts if p is not None and 0 <= p <= 100]
    if len(pcts) != 2 * n_cols:
        return
    order = None
    k = j - 1
    while k >= 0 and rows[k].table_id == row.table_id:
        t = norm(rows[k].text)
        a, b = re.search(r"importe|amount", t), re.search(r"numero|number", t)
        if a and b:
            order = "value_first" if a.start() < b.start() else "number_first"
            break
        k -= 1
    if order is None:
        cand.notes.append("mixed amount/percentage row found but column order not readable")
        return
    first, second = pcts[2 * cur_idx], pcts[2 * cur_idx + 1]
    by_value, by_number = (first, second) if order == "value_first" else (second, first)
    v = cand.values
    if v.get("pct_invoices_paid_within_legal_max_by_value") is None:
        cand.evidence["pct_invoices_paid_within_legal_max_by_value"] = row.text[:160]
        cand.evidence["pct_invoices_paid_within_legal_max_by_number"] = row.text[:160]
        v["pct_invoices_paid_within_legal_max_by_value"] = by_value
        cand.same_block["pct_invoices_paid_within_legal_max_by_value"] = where == "same"
    if v.get("pct_invoices_paid_within_legal_max_by_number") is None:
        v["pct_invoices_paid_within_legal_max_by_number"] = by_number
        cand.same_block["pct_invoices_paid_within_legal_max_by_number"] = where == "same"


# --------------------------------------------------------------------------
# prose mode
# --------------------------------------------------------------------------

_N = r"(\d+(?:[.,]\d+)?)"
_DIAS = r"d ?i ?as"
_PROSE_PMP = re.compile(
    r"(?:periodo|plazo) medio de pagos? a (?:los )?proveedores(?P<ent>(?:(?!medio de pago).){0,120}?)"
    r"durante (?:el ejercicio|los ejercicios|el ano|los anos) (?P<y1>20\d\d)(?: y (?P<y2>20\d\d))?"
    r"(?:,)? (?:es|ha sido|fue|asciende a|se situa en)(?: de)? " + _N + r" " + _DIAS +
    r"(?: y(?: a| de)? " + _N + r" " + _DIAS + r")?"
)
_PROSE_PMP_EN = re.compile(
    r"average (?:supplier )?payment period(?: to suppliers)?(?P<ent>.{0,120}?)"
    r"(?:in|during|for) (?P<y1>20\d\d)(?: and (?P<y2>20\d\d))? (?:was|is|were|amounted to) " + _N +
    r" days(?: and " + _N + r" days)?"
)
_PROSE_RATIO_PAID = re.compile(
    r"ratio de (?:las )?operaciones pagadas.{0,80}?(?:asciende|ascendio|es|fue)(?: a| de)? " + _N + r" " + _DIAS +
    r"(?: y(?: a| de)? " + _N + r" " + _DIAS + r")?")
_PROSE_RATIO_PENDING = re.compile(
    r"ratio de (?:las )?operaciones pendientes(?: de pago)?.{0,80}?(?:a|de|es|fue) " + _N + r" " + _DIAS +
    r"(?: y(?: a| de)? " + _N + r" " + _DIAS + r")?")
_PAREN_PRIOR = r"(?: ?\( ?" + r"\d+(?:[.,]\d+)?" + r" ?% en 20\d\d ?\))?"
_PROSE_PCT_NUMBER = [
    re.compile(_N + r" ?%" + _PAREN_PRIOR + r" sobre el (?:volumen |numero )?total de (?:las )?facturas"),
    re.compile(r"facturas (?:han sido|fueron) pagadas en un (?:plazo|periodo) inferior al maximo legal \( ?" + _N + r" ?% del total ?\)"),
]
_PROSE_PCT_VALUE = [
    re.compile(_N + r" ?%" + _PAREN_PRIOR + r" sobre el (?:importe )?total (?:monetario )?de (?:los )?pagos"),
    re.compile(r"euros (?:han sido|fueron) pagados en un (?:plazo|periodo) inferior al maximo legal \( ?" + _N + r" ?% del total ?\)"),
]


def prose_pcts(text: str, lang: str = "es", fiscal_year: int | None = None):
    """Ley 18/2022 percentages written as a sentence. Returns [(field, value, quote)].

    The first match of each kind is used. Year guard: if the 300 characters
    before a match name a year (parentheticals ignored) and the nearest one is
    not ``fiscal_year``, that match belongs to another year and is skipped.
    """
    t = norm(text)
    out = []
    for name, pats in (("pct_invoices_paid_within_legal_max_by_number", _PROSE_PCT_NUMBER),
                       ("pct_invoices_paid_within_legal_max_by_value", _PROSE_PCT_VALUE)):
        hits = sorted((m for rp in pats for m in rp.finditer(t)), key=lambda x: x.start())
        for m in hits:
            if fiscal_year:
                back = re.sub(r"\([^()]*\)", " ", t[max(0, m.start() - 300): m.start()])
                years = find_years(back)
                if years and years[-1] != fiscal_year:
                    continue
            val = parse_number(m.group(1), lang, "pct")
            if val is not None and 0 <= val <= 100:
                out.append((name, val, t[max(0, m.start() - 40): m.end() + 20]))
                break
    return out


def prose_candidates(text: str, fy_hint: int | None, fact_id=None, concept=None,
                     fact_rank=0) -> list[Candidate]:
    """Sentence patterns on plain text. ``text`` is the readable text."""
    orig = squash(text)
    t = norm_keep(orig)
    out: list[Candidate] = []
    for pat, lang in ((_PROSE_PMP, "es"), (_PROSE_PMP_EN, "en")):
        for m in pat.finditer(t):
            g = m.groups()
            y1 = int(m.group("y1"))
            y2 = int(m.group("y2")) if m.group("y2") else None
            a = parse_number(g[-2], lang, "days")
            b = parse_number(g[-1], lang, "days") if g[-1] else None
            if a is None or not (0 < a < 400):
                continue
            cand = Candidate(mode="prose", fact_id=fact_id, concept=concept,
                             offset=m.start(), snippet=orig[m.start(): m.end()][:200], lang=lang,
                             fact_rank=fact_rank, year_basis="sentence")
            v = cand.values
            pairs = [(y1, a)] + ([(y2, b)] if (y2 and b is not None) else [])
            cur = max(pairs)
            v["fiscal_year"], v["pmp_days"] = cur
            prior = [p for p in pairs if p[0] == cur[0] - 1]
            v["prior_fiscal_year"] = prior[0][0] if prior else None
            v["prior_year_pmp_days"] = prior[0][1] if prior else None
            first_is_current = pairs[0] == cur
            tail = t[m.end(): m.end() + 500]
            for name, rp in (("ratio_paid_days", _PROSE_RATIO_PAID),
                             ("ratio_pending_days", _PROSE_RATIO_PENDING)):
                mm = rp.search(tail)
                val = None
                if mm:
                    x = parse_number(mm.group(1), lang, "days")
                    y = parse_number(mm.group(2), lang, "days") if mm.group(2) else None
                    val = x if first_is_current else y
                v[name] = val
                cand.same_block[name] = val is not None
                if val is not None:
                    cand.evidence[name] = mm.group(0)[:160]
            cand.evidence["pmp_days"] = orig[m.start(): m.end()][:160]
            v["pct_invoices_paid_within_legal_max_by_number"] = None
            v["pct_invoices_paid_within_legal_max_by_value"] = None
            for name, val, quote in prose_pcts(t[m.start(): m.start() + 2500], lang, cur[0]):
                v[name] = val
                cand.evidence[name] = quote[:160]
            v["total_payments_made"] = None
            v["total_payments_pending"] = None
            ent = m.group("ent") or ""
            sent = t[max(0, m.start() - 300): m.end()]
            pm = _SCOPE_PARENT_SENTENCE.search(m.group(0))
            if re.search(r"\bgrupo\b|\bgroup\b|consolidad", ent):
                cand.scope, cand.scope_basis = detect_scope(sent)
            elif pm:
                cand.scope = "parent_only"
                cand.scope_basis = f"sentence names a single legal entity: '{squash(pm.group('ent'))[-60:]}'"
            else:
                cand.scope, cand.scope_basis = detect_scope(sent)
            cand.header_hint = "prose sentence"
            out.append(cand)
    return out


# --------------------------------------------------------------------------
# checks, confidence, selection
# --------------------------------------------------------------------------


def sanity_checks(v: dict) -> dict:
    pmp, rp, rq = v.get("pmp_days"), v.get("ratio_paid_days"), v.get("ratio_pending_days")
    paid, pend = v.get("total_payments_made"), v.get("total_payments_pending")
    out = {"check_pmp_in_range": None, "check_pmp_between_ratios": None,
           "pmp_recomputed": None, "check_recomputed_within_1_day": None}
    if pmp is None:
        return out
    out["check_pmp_in_range"] = bool(0 < pmp < 400)
    if rp is not None and rq is not None:
        lo, hi = min(rp, rq), max(rp, rq)
        out["check_pmp_between_ratios"] = bool(lo - 0.5 <= pmp <= hi + 0.5)
        if paid is not None and pend is not None and paid >= 0 and pend >= 0 and (paid + pend) > 0:
            rec = (rp * paid + rq * pend) / (paid + pend)
            out["pmp_recomputed"] = round(rec, 2)
            out["check_recomputed_within_1_day"] = bool(abs(rec - pmp) <= 1.0)
    return out


def score_confidence(cand: Candidate, checks: dict, n_distinct: int) -> float:
    v = cand.values
    if v.get("pmp_days") is None or not checks["check_pmp_in_range"]:
        return 0.0
    has_rp = v.get("ratio_paid_days") is not None
    has_rq = v.get("ratio_pending_days") is not None
    if cand.mode == "prose":
        c = 0.75 if (has_rp and has_rq and checks["check_pmp_between_ratios"]) else 0.60
        if has_rp and has_rq and checks["check_pmp_between_ratios"] is False:
            c = 0.50
    elif has_rp and has_rq:
        same = cand.same_block.get("ratio_paid_days") and cand.same_block.get("ratio_pending_days")
        if not checks["check_pmp_between_ratios"]:
            c = 0.50
        elif checks["check_recomputed_within_1_day"] is True:
            c = 0.95
        elif checks["check_recomputed_within_1_day"] is False:
            c = 0.75
        else:
            c = 0.90
        if not same:
            c -= 0.05
    else:
        c = 0.70
    if cand.year_basis == "assumed_current_year_first":
        c -= 0.10
    if n_distinct > 1:
        c -= 0.05
    return round(max(0.0, min(1.0, c)), 2)


_SCOPE_RANK = {"consolidated_spanish_entities": 2, "unknown": 1, "parent_only": 0}


_SUBSET_HEADER = re.compile(r"\bsolo\b|\bonly\b|excluyendo|excluding|sin incluir")


def _rank(c: Candidate):
    mode = {"table": 2, "flow": 1, "prose": 0}[c.mode]
    whole = 0 if _SUBSET_HEADER.search(norm(c.header_hint)) else 1
    return (_SCOPE_RANK.get(c.scope, 1), whole, mode)


def select(cands: list[Candidate]):
    """De-duplicate and pick the preferred candidate.

    Returns (best, distinct candidates in document order).
    Preference: group-level scope > unknown > parent only; a table whose
    header marks it as a subset ("solo ...", "excluding ...") loses against a
    full one; then table > flow > prose; then document order (first wins).
    """
    distinct: dict[tuple, Candidate] = {}
    for c in cands:
        k = c.key()
        if k not in distinct or c.filled() > distinct[k].filled():
            if k in distinct:
                c.fact_rank = min(c.fact_rank, distinct[k].fact_rank)
            distinct[k] = c
    lst = sorted(distinct.values(), key=lambda c: (c.fact_rank, c.offset))
    if not lst:
        return None, []
    best = max(lst, key=lambda c: (_rank(c), -lst.index(c)))
    return best, lst


# --------------------------------------------------------------------------
# documents
# --------------------------------------------------------------------------

_PRECHECK = re.compile(
    r"medio\s+de\s+pago|payment\s+period|period\s+of\s+payment|operaciones\s+pagadas", re.I)


def _fact_candidates(fid, fact, fy, rank):
    value = fact.get("value")
    concept = (fact.get("dimensions") or {}).get("concept")
    rows = linearize(value)
    cands = build_candidates(rows, fy, fid, concept, rank)
    return cands, rows


def extract_esef_json(path: Path, fy: int | None, listed_facts: list[str]):
    """Candidates from an ESEF xBRL-JSON file. Returns (candidates, notes)."""
    notes: list[str] = []
    with open(path, encoding="utf-8") as fh:
        facts = json.load(fh).get("facts", {})
    cands: list[Candidate] = []
    prose: list[Candidate] = []
    seen = set()

    def run(fid, rank):
        fact = facts.get(fid)
        if fact is None or fid in seen:
            return
        seen.add(fid)
        value = fact.get("value")
        if not isinstance(value, str) or len(value) < 100:
            return
        cs, rows = _fact_candidates(fid, fact, fy, rank)
        cands.extend(cs)
        if not cs:
            concept = (fact.get("dimensions") or {}).get("concept")
            # rows joined back = readable text with spaces at block boundaries
            text = " ".join(r.text for r in rows) if rows else re.sub(r"<[^>]+>", " ", value)
            prose.extend(prose_candidates(text, fy, fid, concept, rank))

    for n, fid in enumerate(listed_facts):
        run(fid, n)
    if not cands:
        # fallback: every other text fact that mentions the disclosure
        scanned = 0
        for fid, fact in facts.items():
            if fid in seen:
                continue
            value = fact.get("value")
            if not isinstance(value, str) or len(value) < 200:
                continue
            if not _PRECHECK.search(value) and not _PRECHECK.search(re.sub(r"<[^>]+>", "", value)):
                continue
            scanned += 1
            run(fid, 1000 + scanned)
        if cands:
            notes.append("PMP table not in the facts listed in es_pmp_sources.csv; "
                         f"found by scanning all text facts of the document ({scanned} scanned)")
    if not cands:
        cands = prose
    return cands, notes


def extract_html_page(path: Path, fy: int | None):
    raw = path.read_text(encoding="utf-8", errors="replace")
    doc = lxml.html.fromstring(raw)
    for bad in doc.xpath("//script|//style|//noscript"):
        bad.drop_tree()
    body = doc.find("body")
    body = body if body is not None else doc
    html = lxml.html.tostring(body, encoding="unicode")
    rows = linearize(html)
    cands = build_candidates(rows, fy)
    if not cands:
        text = " ".join(r.text for r in rows) if rows else squash(body.text_content())
        cands = prose_candidates(text, fy)
    return cands, []


def _clean(x):
    if isinstance(x, float) and x == int(x) and abs(x) < 1e15:
        return int(x)
    return x


def extract_company(src: dict) -> dict:
    """One output record from one row of es_pmp_sources.csv."""
    fy = int(src["fiscal_year"]) if str(src.get("fiscal_year", "")).strip().isdigit() else None
    rec = {k: None for k in OUTPUT_FIELDS}
    rec.update(ticker=src["ticker"], company_name=src["company_name"],
               source_url=src.get("source_url") or None,
               local_path=src.get("local_path") or None,
               extraction_method=EXTRACTION_METHOD, scope="unknown", confidence=0.0,
               n_pmp_tables=0,
               source_document_scope=(src.get("scope") or None))  # as listed by the sourcing step
    notes: list[str] = []
    status = (src.get("status") or "").strip()
    path = ROOT / src["local_path"] if src.get("local_path") else None
    if status != "ok":
        notes.append(f"source status '{status}' in es_pmp_sources.csv: document scanned anyway")
    if path is None or not path.exists():
        notes.append("no local document: PMP not extracted")
        rec["notes"] = "; ".join(notes)
        return rec
    try:
        listed = []
        for h in json.loads(src.get("pmp_pages") or "[]"):
            fid = h.get("fact_id")
            if fid and fid not in listed:
                listed.append(fid)
    except (ValueError, AttributeError):
        listed = []
    is_json = path.suffix.lower() == ".json"
    if is_json:
        cands, n2 = extract_esef_json(path, fy, listed)
    else:
        cands, n2 = extract_html_page(path, fy)
    notes += n2
    best, distinct = select(cands)
    if best is None:
        notes.append("no PMP row or sentence matched the deterministic patterns: PMP left null")
        if is_json and listed:
            notes.append("the listed fact(s) mention the disclosure but hold no PMP value in tagged text "
                         "(table probably sits outside the tagged text block)")
        rec["notes"] = "; ".join(notes)
        return rec
    v = best.values
    checks = sanity_checks(v)
    conf = score_confidence(best, checks, len(distinct))
    if checks["check_pmp_in_range"] is False:
        notes.append("PMP outside (0, 400): value dropped")
        v["pmp_days"] = None
    for k in ("fiscal_year", "pmp_days", "ratio_paid_days", "ratio_pending_days",
              "total_payments_made", "total_payments_pending",
              "pct_invoices_paid_within_legal_max_by_value",
              "pct_invoices_paid_within_legal_max_by_number",
              "prior_year_pmp_days", "prior_fiscal_year"):
        rec[k] = _clean(v.get(k))
    has_tot = rec["total_payments_made"] is not None or rec["total_payments_pending"] is not None
    rec["money_unit"] = best.unit if has_tot else None
    rec["money_unit_raw"] = best.unit_raw if has_tot else None
    rec["money_unit_basis"] = best.unit_basis if has_tot else None
    rec["evidence_rows"] = best.evidence
    if has_tot and best.unit is None:
        notes.append("money unit not stated near the totals: left null")
    elif has_tot and best.unit_basis and best.unit_basis.startswith("inferred"):
        notes.append(f"money unit {best.unit_basis}")
    if has_tot and best.unit_raw and re.fullmatch(r"[mM] ?€", best.unit_raw):
        notes.append(f"unit abbreviation '{best.unit_raw}' read by convention (m = miles, M = millones)")
    rec["scope"], rec["scope_basis"] = best.scope, best.scope_basis
    rec["language"] = best.lang
    rec["extraction_mode"] = best.mode
    rec["fiscal_year_basis"] = best.year_basis
    if is_json:
        rec["location"] = (f"fact_id={best.fact_id}; concept={best.concept}; "
                           f"linearised_text_offset={best.offset}")
    else:
        rec["location"] = f"html_text_offset={best.offset} ({best.mode})"
    rec["quoted_snippet"] = best.snippet[:200]
    rec.update(checks)
    rec["confidence"] = conf
    rec["n_pmp_tables"] = len(distinct)
    notes += best.notes
    if fy and rec["fiscal_year"] and rec["fiscal_year"] != fy:
        notes.append(f"fiscal year in table header ({rec['fiscal_year']}) differs from source list ({fy})")
    if checks["check_pmp_between_ratios"] is False:
        notes.append("PMP is not between the two ratios as printed in the source")
    if checks["check_recomputed_within_1_day"] is False:
        notes.append("recomputed PMP differs from stated PMP by more than 1 day")
    if rec["ratio_paid_days"] is None or rec["ratio_pending_days"] is None:
        if rec["pmp_days"] is not None:
            notes.append("ratio(s) not found next to the PMP value")
    if len(distinct) > 1:
        others = []
        for c in distinct:
            if c is best:
                continue
            others.append(f"[{c.mode}, fact {c.fact_id}, scope {c.scope}, PMP {_clean(c.values.get('pmp_days'))}, "
                          f"header '{c.header_hint[:70]}']")
        notes.append(f"{len(distinct)} distinct PMP tables in the document; chosen header "
                     f"'{best.header_hint[:70]}'; others: " + " ".join(others))
    rec["notes"] = "; ".join(dict.fromkeys(notes)) or None
    return rec


def read_sources(path: Path = SOURCES_CSV) -> list[dict]:
    with open(path, encoding="utf-8", newline="") as fh:
        return list(csv.DictReader(fh))


def run(sources_csv: Path = SOURCES_CSV, out_json: Path = OUT_JSON,
        out_csv: Path = OUT_CSV) -> list[dict]:
    t0 = time.perf_counter()
    records, timings = [], {}
    for src in read_sources(sources_csv):
        t1 = time.perf_counter()
        try:
            rec = extract_company(src)
        except Exception as exc:  # noqa: BLE001  one bad document must not stop the run
            rec = {k: None for k in OUTPUT_FIELDS}
            rec.update(ticker=src.get("ticker"), company_name=src.get("company_name"),
                       source_url=src.get("source_url"), local_path=src.get("local_path"),
                       extraction_method=EXTRACTION_METHOD, scope="unknown", confidence=0.0,
                       notes=f"extractor error: {type(exc).__name__}: {exc}")
        timings[src.get("ticker")] = round(time.perf_counter() - t1, 3)
        records.append(rec)
    out_json.parent.mkdir(parents=True, exist_ok=True)
    out_json.write_text(json.dumps(records, ensure_ascii=False, indent=2), encoding="utf-8")
    with open(out_csv, "w", encoding="utf-8", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=OUTPUT_FIELDS, extrasaction="ignore")
        w.writeheader()
        for rec in records:
            row = dict(rec)
            if isinstance(row.get("evidence_rows"), dict):
                row["evidence_rows"] = json.dumps(row["evidence_rows"], ensure_ascii=False)
            w.writerow(row)
    elapsed = round(time.perf_counter() - t0, 2)
    n = len(records)
    with_pmp = sum(1 for r in records if r["pmp_days"] is not None)
    meta = {
        "extractor": "extract-es-a (deterministic)",
        "extraction_method": EXTRACTION_METHOD,
        "run_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "wall_clock_seconds": elapsed,
        "documents": n,
        "seconds_per_document": round(elapsed / n, 3) if n else None,
        "llm_cost_usd": 0.0,
        "with_pmp": with_pmp,
        "seconds_by_ticker": timings,
    }
    OUT_META.write_text(json.dumps(meta, indent=2), encoding="utf-8")
    print(f"spain_pmp: {with_pmp}/{n} companies with PMP, {elapsed}s wall clock "
          f"-> {out_json.relative_to(ROOT)}, {out_csv.relative_to(ROOT)}")
    return records


if __name__ == "__main__":
    run()
