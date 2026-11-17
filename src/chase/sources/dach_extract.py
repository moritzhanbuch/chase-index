"""DACH slice, extractor A (deterministic) and the shared document-to-text step.

Text: every PDF page is rebuilt line by line from word positions (pymupdf), so a statement row reads
"Trade payables 12 4,321 3,987" the way it is printed. iXBRL (ESEF) reports are parsed for tagged facts and
also turned into text chunks. The same text files are what extractor B (an agent) reads.

Extractor A, per report:
  1. tagged facts (ESEF xBRL-JSON or iXBRL): CostOfSales, RawMaterialsAndConsumablesUsed, Revenue, and a
     trade-payables concept (CurrentTradePayables / TradeAndOtherCurrentPayablesToTradeSuppliers / ...).
     A combined "trade and other payables" tag is NOT accepted as trade payables.
  2. otherwise the printed statements: consolidated balance sheet (current-liabilities section) and income
     statement rows, by label, in English or German; then the notes for a trade-payables row when the balance
     sheet shows only a combined line.
Every value keeps its page, the printed line (quote) and the unit found on that page.
"""
from __future__ import annotations

import re
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]

# ---------------------------------------------------------------- text
def pdf_pages(pdf: Path) -> list[str]:
    import pymupdf
    out = []
    with pymupdf.open(pdf) as doc:
        for page in doc:
            words = page.get_text("words")          # x0, y0, x1, y1, word, block, line, wno
            rows: list[list] = []
            for w in sorted(words, key=lambda w: (round(w[1], 0), w[0])):
                yc = (w[1] + w[3]) / 2
                if rows and abs(rows[-1][0] - yc) <= 2.5:
                    rows[-1][1].append(w)
                else:
                    rows.append([yc, [w]])
            lines = [" ".join(x[4] for x in sorted(ws, key=lambda w: w[0])) for _, ws in sorted(rows, key=lambda r: r[0])]
            out.append("\n".join(lines))
    return out


def xhtml_pages(xhtml: bytes, chunk: int = 6000) -> list[str]:
    from bs4 import BeautifulSoup
    soup = BeautifulSoup(xhtml, "lxml")
    for t in soup(["script", "style"]):
        t.decompose()
    # ESEF reports usually keep the printed page as a div with a page-break style; split there when present
    pages = soup.find_all("div", style=re.compile(r"page-break-(after|before)", re.I))
    texts = [p.get_text("\n", strip=True) for p in pages] if len(pages) > 20 else []
    if not texts:
        txt = soup.get_text("\n", strip=True)
        texts = [txt[i:i + chunk] for i in range(0, len(txt), chunk)]
    return texts


# ---------------------------------------------------------------- iXBRL
def ixbrl_facts(xhtml: bytes) -> dict:
    """{(concept, start, end, unit): value} for undimensioned numeric facts, in the format chase.sources.esef_xbrl uses."""
    from lxml import etree
    root = etree.fromstring(xhtml, parser=etree.XMLParser(huge_tree=True, recover=True))
    if root is None:
        return {}
    ln = lambda e: etree.QName(e).localname
    ctx, units = {}, {}
    for e in root.iter():
        if not isinstance(e.tag, str):
            continue
        if ln(e) == "context":
            dims = any(ln(x) in ("segment", "scenario") for x in e.iter() if isinstance(x.tag, str))
            per = {ln(x): (x.text or "").strip() for x in e.iter() if isinstance(x.tag, str) and ln(x) in ("instant", "startDate", "endDate")}
            d = lambda s: date.fromisoformat(s[:10]) if s else None
            ctx[e.get("id")] = (dims, d(per.get("startDate")), d(per.get("endDate") or per.get("instant")))
        elif ln(e) == "unit":
            ms = [x.text.strip() for x in e.iter() if isinstance(x.tag, str) and ln(x) == "measure" and x.text]
            units[e.get("id")] = ms[0] if len(ms) == 1 else "/".join(ms)
    facts: dict = {}
    for e in root.iter():
        if not isinstance(e.tag, str) or ln(e) != "nonFraction":
            continue
        c = ctx.get(e.get("contextRef"))
        if not c or c[0]:
            continue
        txt = "".join(e.itertext()).strip()
        fmt = (e.get("format") or "").split(":")[-1].lower()
        if fmt in ("zerodash", "fixed-zero", "fixedzero") or txt in ("-", "–", "—"):
            v = 0.0
        else:
            digits = re.sub(r"[^\d.,]", "", txt)
            if not digits:
                continue
            if "comma" in fmt:       # num-comma-decimal: 1.234,5
                digits = digits.replace(".", "").replace(" ", "").replace(",", ".")
            else:                    # num-dot-decimal: 1,234.5
                digits = digits.replace(",", "").replace(" ", "")
            try:
                v = float(digits)
            except ValueError:
                continue
        v *= 10 ** int(e.get("scale") or 0)
        if e.get("sign") == "-":
            v = -v
        name = e.get("name") or ""
        start, end = (c[1], c[2])
        facts[(name, start, end, units.get(e.get("unitRef"), ""))] = v
    return facts


# ---------------------------------------------------------------- printed statements
LABELS = {
    "trade_payables": [r"trade (?:accounts )?payables(?! and other)(?: to third parties)?", r"accounts payable[, –-]+trade", r"accounts payable(?! and)",
                       r"trade accounts payable", r"payables to suppliers", r"verbindlichkeiten aus lieferungen und leistungen",
                       r"liabilities to suppliers"],
    "cost_of_sales": [r"cost of (?:sales|goods sold|revenues?)", r"costs? of sales", r"umsatzkosten",
                      r"herstellungskosten der zur erzielung der umsatzerl[öo]se erbrachten leistungen"],
    "cost_of_materials": [r"cost of materials", r"materials? expenses?", r"materialaufwand", r"raw materials(?:,| and) consumables(?: and supplies)? used"],
    "revenue": [r"revenues?", r"net sales", r"sales", r"umsatzerl[öo]se", r"net revenues?"],
}
BS_HEAD = re.compile(r"statement of financial position|balance sheet|bilanz\b", re.I)
BS_TOTAL = re.compile(r"total assets|bilanzsumme|equity and liabilities|total liabilities and (?:shareholders'? )?equity|summe aktiva|summe passiva|^current liabilities|kurzfristige (?:schulden|verbindlichkeiten)", re.I | re.M)
IS_HEAD = re.compile(r"income statement|statement of income|statement of profit or loss|gewinn- und verlustrechnung|statement of (?:comprehensive )?income", re.I)
PARENT_ONLY = re.compile(r"\bHGB\b|parent company|individual financial statements|separate financial statements|einzelabschluss|jahresabschluss der|austrian commercial code|unternehmensgesetzbuch|\bUGB\b", re.I)
CONSOL = re.compile(r"consolidated|group|konzern", re.I)
CUR_LIAB = re.compile(r"^(?:total )?current liabilities|^kurzfristige (?:schulden|verbindlichkeiten)", re.I)
NUM = re.compile(r"(?<![\w.])\(?[-–−]?\d{1,3}(?:[,.'’]\d{3})*(?:[.,]\d+)?\)?(?![\w.,])")
UNIT = [(re.compile(r"thousands? of (?:€|eur|euros?)|(?:€|eur)\s?(?:in )?thousands?|in (?:€|eur)\s?(?:k\b|thousand|tsd)|\bt€|\bteur\b|tsd\.?\s?(?:€|eur)", re.I), ("EUR", 1e3)),
        (re.compile(r"millions? of (?:€|eur|euros?)|(?:€|eur)\s?(?:in )?millions?|in (?:€|eur)\s?(?:m\b|mn\b|mio)|(?:€|eur)\s?m\b|mio\.?\s?(?:€|eur)|(?:€|eur) ?mio", re.I), ("EUR", 1e6)),
        (re.compile(r"thousands? of (?:chf|swiss francs)|chf\s?(?:in )?thousands?|\btchf\b|chf\s?k\b|thousand chf", re.I), ("CHF", 1e3)),
        (re.compile(r"millions? of (?:chf|swiss francs)|chf\s?(?:in )?millions?|million chf|chf\s?m\b|mio\.?\s?chf|chf mio", re.I), ("CHF", 1e6)),
        (re.compile(r"\$ in millions|millions? of (?:us )?(?:dollars|\$|usd)|(?:usd|us\$)\s?(?:in )?millions?|usd\s?m\b|\$\s?m\b", re.I), ("USD", 1e6))]


def parse_num(tok: str) -> float | None:
    t = tok.strip()
    neg = t.startswith("(") and t.endswith(")") or t.lstrip("(").startswith(("-", "–", "−"))
    t = re.sub(r"[()\-–−\s ]", "", t).replace("’", "'")
    if not t:
        return None
    t = t.replace("'", "")
    seps = [c for c in t if c in ",."]
    if len(set(seps)) == 2:                     # both: the last one is the decimal mark
        dec = t[max(t.rfind(","), t.rfind("."))]
        t = t.replace("," if dec == "." else ".", "").replace(dec, ".")
    elif seps:
        sep = seps[0]
        parts = t.split(sep)
        t = t.replace(sep, "") if all(len(p) == 3 for p in parts[1:]) else t.replace(sep, ".")
    try:
        v = float(t)
    except ValueError:
        return None
    return -v if neg else v


def values_on_line(rest: str) -> list[float]:
    rest = _join_space_thousands(rest)
    toks = [m.group(0) for m in NUM.finditer(rest) if not re.match(r"\s?%", rest[m.end():])]
    vals = [parse_num(t) for t in toks]
    vals = [v for v in vals if v is not None]
    # a leading note reference ("12", "(23)") in front of two amounts
    if len(vals) >= 3 and re.fullmatch(r"\(?\d{1,2}(?:\.\d{1,2})?\)?", toks[0].strip()):
        vals = vals[1:]
    return vals


SPACE_THOUSANDS = re.compile(r"(?<![\d.,])(\d{1,3})((?: \d{3})+)(?![\d.,])")


SPACE_DOC = {"on": False}     # set per document by extract_text()


def uses_space_thousands(pages: list[str]) -> bool:
    """Some Swiss reports print 3 426 for 3,426. Decided per document: many space-grouped amounts, almost no comma/dot ones."""
    txt = "\n".join(pages)
    return len(re.findall(r"\b\d{1,3} \d{3}\b", txt)) > 5 * max(1, len(re.findall(r"\b\d{1,3}[,.’']\d{3}\b", txt)))


def _join_space_thousands(rest: str) -> str:
    if not SPACE_DOC["on"] or re.search(r"\d[,.’']\d{3}\b", rest):
        return rest
    return SPACE_THOUSANDS.sub(lambda m: m.group(1) + m.group(2).replace(" ", ""), rest)


def unit_of(text: str):
    for rx, u in UNIT:
        if rx.search(text):
            return u
    return None


def column_order_desc(text: str) -> bool:
    """True when the newest year is the first amount column (the usual layout)."""
    for line in text.splitlines()[:60]:
        ys = [int(y) for y in re.findall(r"\b(20[1-3]\d)\b", line)]
        if len(ys) >= 2 and ys[0] != ys[1]:
            return ys[0] > ys[1]
    return True


NUMERIC_LINE = re.compile(r"^[\s\d.,()'’\-–−]+$")


def find_rows(text: str, key: str) -> list[tuple[int, str, list[float]]]:
    """Rows whose label matches `key` and that carry at least two amounts. In ESEF text every table cell can sit on its
    own line, so up to four purely numeric lines after a bare label are read as that row's amounts."""
    out = []
    lines = text.splitlines()
    for i, line in enumerate(lines):
        low = line.strip().lower()
        for pat in LABELS[key]:
            m = re.match(rf"^(?:[a-z0-9.]{{1,4}}\s+)?{pat}\b[^\d(]*", low)
            if m and not re.search(r"other payables|und sonstige|and other", low[:m.end()]):
                rest, quote = line[m.end():], line.strip()
                if len(values_on_line(rest)) < 2 and m.end() >= len(low.rstrip(" :")) - 1:
                    nxt = []
                    for l2 in lines[i + 1:i + 5]:
                        if not NUMERIC_LINE.match(l2.strip() or "x"):
                            break
                        nxt.append(l2.strip())
                    rest, quote = rest + " " + " ".join(nxt), (line.strip() + " " + " ".join(nxt)).strip()
                vals = values_on_line(rest)
                if len(vals) >= 2:
                    out.append((i, quote, vals))
                break
    return out


def _heading_line(pages, n, rx) -> str | None:
    """The statement heading for page n: on the page itself (top), else the last one on the previous page."""
    for line in pages[n].splitlines()[:40]:
        if rx.search(line):
            return line
    prev = [line for line in pages[n - 1].splitlines() if rx.search(line)] if n > 0 else []
    return prev[-1] if prev else None


def _pick_page(pages, head_rx, must_rx, key):
    """Prefer the page under a "consolidated / group / Konzern" statement heading; a parent-only page comes last."""
    cands = []
    for n, t in enumerate(pages):
        h = _heading_line(pages, n, head_rx)
        win = "\n".join(pages[max(0, n - 1): n + 2])
        rows = find_rows(t, key) if h and (must_rx is None or must_rx.search(win)) else []
        if rows:
            # management-report tables repeat the figures with a change column ("4%", "Change"): not the statement itself
            change = 1 if re.search(r"%|\bchange\b|veränderung", rows[0][1], re.I) or re.search(r"\b(?:% )?change\b|veränderung", "\n".join(t.splitlines()[:15]), re.I) else 0
            parent = 1 if PARENT_ONLY.search(win) or re.search(r"commercial code|handelsgesetzbuch", win, re.I) else 0
            cands.append((parent, change, 0 if CONSOL.search(h) else 1, n))
    return sorted(cands)[0][3] if cands else None


def extract_text(pages: list[str]) -> dict:
    SPACE_DOC["on"] = uses_space_thousands(pages)
    out = {"_space_thousands": SPACE_DOC["on"]}

    def take(key, n, rows, prefer_after=None):
        t = pages[n]
        if prefer_after is not None:       # balance sheet: the row in the current-liabilities section
            later = [r for r in rows if r[0] > prefer_after]
            i, line, vals = later[0] if later else rows[-1]
        else:
            i, line, vals = rows[0]
        desc = column_order_desc(t)
        cur, prior = (vals[0], vals[1]) if desc else (vals[1], vals[0])
        u = unit_of(t) or unit_of("\n".join(pages[max(0, n - 1): n + 1]))
        out[key] = {"current": abs(cur), "prior": abs(prior), "page": n + 1, "quote": line[:200],
                    "currency": u[0] if u else None, "scale": u[1] if u else None}

    bs = _pick_page(pages, BS_HEAD, BS_TOTAL, "trade_payables")
    if bs is not None:
        lines = pages[bs].splitlines()
        cl = next((i for i, l in enumerate(lines) if CUR_LIAB.search(l.strip()) and "non" not in l.lower()[:12]), None)
        take("trade_payables", bs, find_rows(pages[bs], "trade_payables"), prefer_after=cl)
        out["trade_payables"]["where"] = "balance_sheet"
    else:   # only a combined line on the face: look in the notes
        bs_any = next((n for n, t in enumerate(pages) if BS_HEAD.search(t) and BS_TOTAL.search(t)), 0)
        for n in range(bs_any, len(pages)):
            rows = find_rows(pages[n], "trade_payables")
            if rows and re.search(r"payables|verbindlichkeiten", pages[n], re.I):
                take("trade_payables", n, rows)
                out["trade_payables"]["where"] = "notes"
                break
    is_ = _pick_page(pages, IS_HEAD, None, "revenue")
    if is_ is not None:
        for key in ("revenue", "cost_of_sales", "cost_of_materials"):
            rows = find_rows(pages[is_], key)
            if rows:
                take(key, is_, rows)
    if "cost_of_sales" not in out and "cost_of_materials" not in out:
        for n, t in enumerate(pages):      # by-nature reporters sometimes put the materials line in a note
            rows = find_rows(t, "cost_of_materials")
            if rows and (is_ is None or n > is_):
                take("cost_of_materials", n, rows)
                break
    return out
