"""QA check for dpo.parquet. SEC rows: read R-pages (rendered financial statements) from the EDGAR filing.
ESEF rows: independent re-derivation from xBRL-JSON. Usage: .venv/bin/python evals/dpo_check.py [explore]"""
import re, sys, json
import pandas as pd
from bs4 import BeautifulSoup
sys.path.insert(0, "src")
from chase.common.http import fetch

SEED = 20261116
d = pd.read_parquet("data/processed/dpo.parquet")
d = d[(d.year_rank == 1) & (d.dpo_flag == "ok")]
S = pd.concat([d[d.dpo_source == "sec"].sample(10, random_state=SEED),
               d[d.dpo_source == "esef"].sample(5, random_state=SEED)])

def num(s):
    s = s.replace("$", "").replace("€", "").replace(",", "").strip()
    m = re.match(r"^\(?-?[\d.]+\)?$", s)
    if not m: return None
    v = float(s.strip("()"));  return -v if s.startswith("(") else v

def rpages(url):
    out = {}
    for i in range(2, 9):
        try: r = fetch(url + f"R{i}.htm")
        except Exception as e: continue
        soup = BeautifulSoup(r.text, "lxml")
        title = (soup.find("th") or soup.find("title"))
        hdr = soup.get_text(" ", strip=True)[:200]
        rows = []
        for tr in soup.find_all("tr"):
            cells = [c.get_text(" ", strip=True) for c in tr.find_all(["td", "th"])]
            if cells: rows.append(cells)
        out[i] = (hdr, rows)
    return out

def explore(row):
    print("=====", row.company_name, row.fiscal_year, row.period_end, "table: pay", row.payables, "cost", row.cost_of_sales)
    for i, (hdr, rows) in rpages(row.filing_url).items():
        print(" R%d" % i, hdr[30:130])
        for c in rows:
            if len(c[0])<90 and not c[0].startswith("-") and re.search(r"payable|cost of|costs? and expenses|operating expenses", c[0], re.I):
                print("    ", c[:4])

def esef_candidates(row):
    """Independent re-derivation from xBRL-JSON: undimensioned payable / cost facts at FY end.
    xBRL-JSON instants are end-exclusive (period end + 1 day at T00:00), durations likewise."""
    j = fetch(row.source_url).json()
    end = (pd.Timestamp(str(row.period_end)[:10]) + pd.Timedelta(days=1)).strftime("%Y-%m-%d")
    out = []
    for fid, f in j["facts"].items():
        dm = f["dimensions"]
        if [k for k in dm if k not in ("concept", "entity", "period", "unit", "language")]: continue
        c = dm["concept"]; per = dm["period"]
        if not re.search(r"payable|CostOfSales|RawMaterials|OperatingExpense|CostOfGoods|^[^:]+:Revenue$", c, re.I): continue
        if "/" in per:
            a, b = per.split("/")
            if b[:10] == end and 340 < (pd.Timestamp(b[:10]) - pd.Timestamp(a[:10])).days < 380:
                if not re.search("payable", c, re.I): out.append((c, per[:10] + ".." + b[:10], f["value"]))
        elif per[:10] == end and re.search("payable", c, re.I):
            out.append((c, per[:10], f["value"]))
    return sorted(set(out))


# Values as read (millions of reporting currency, or units as printed) from R pages / xBRL-JSON output above.
# name prefix: (payables, cost, scale, check type, payables line as read, cost line as read, doc)
READ = {
 "The Hershey": (1255701, 7769885, 1e3, "R-page", "Accounts payable (balance sheet)", "Cost of sales", "R5.htm / R3.htm"),
 "Diageo": (6952, 8072, 1e6, "R-page", "Trade and other payables (balance sheet, current)", "Cost of sales", "R5.htm / R3.htm"),
 "Alcoa": (1938, 10658, 1e6, "R-page", "Accounts payable, trade", "Cost of goods sold (excl. D&A)", "R4.htm / R2.htm"),
 "Ardagh": (1266, 4816, 1e6, "R-page (note 23, R131)", "Trade payables (note: Trade and other payables); face shows Trade and other payables 1,539", "Cost of sales", "R131.htm / R2.htm"),
 "Colgate": (2089, 8131, 1e6, "R-page", "Accounts payable", "Cost of sales", "R5.htm / R3.htm"),
 "StandardAero": (679772, 5165060, 1e3, "R-page", "Accounts payable", "Cost of revenue", "R2.htm / R4.htm"),
 "RIO": (3596, 41784, 1e6, "R-page (note, R75)", "Trade payables (note; face shows Trade and other payables 10,133)", "Net operating costs (excl. items disclosed separately)", "R75.htm / R2.htm"),
 "Lowe": (9762, 57401, 1e6, "R-page", "Accounts payable", "Cost of sales", "R5.htm / R3.htm"),
 "APi": (526, 5424, 1e6, "R-page", "Accounts payable", "Cost of revenues", "R3.htm / R5.htm"),
 "Viatris": (1754.1, 9286.4, 1e6, "R-page", "Accounts payable", "Cost of sales", "R3.htm / R5.htm"),
 "RAMSAY": (427700000, 1150700000, 1, "independent re-derivation from xBRL-JSON", "TradeAndOtherCurrentPayablesToTradeSuppliers @2026-06-30", "RawMaterialsAndConsumablesUsed FY", "xBRL-JSON"),
 "IVECO": (3753000000, 11328000000, 1, "independent re-derivation from xBRL-JSON", "TradeAndOtherPayablesToTradeSuppliers @2025-12-31", "CostOfSales FY", "xBRL-JSON"),
 "DISTRIBUIDORA": (958410000, 4215044000, 1, "independent re-derivation from xBRL-JSON", "TradeAndOtherCurrentPayables @2025-12-31", "RawMaterialsAndConsumablesUsed FY", "xBRL-JSON"),
 "ESPRINET": (1330435000, 4056984000, 1, "independent re-derivation from xBRL-JSON", "TradeAndOtherCurrentPayablesToTradeSuppliers @2025-12-31", "CostOfSales FY", "xBRL-JSON"),
 "CIE AUTOMOTIVE": (925798000, 2240496000, 1, "independent re-derivation from xBRL-JSON", "TradeAndOtherCurrentPayables @2025-12-31", "RawMaterialsAndConsumablesUsed FY", "xBRL-JSON"),
}

def report():
    rows = []
    for _, r in S.iterrows():
        k = next(k for k in READ if r.company_name.upper().startswith(k.upper()))
        pay, cost, sc, typ, pl, cl, doc = READ[k]
        dpo = pay / cost * 365
        diff = dpo - r.dpo
        rows.append((r.company_name, r.fiscal_year, r.dpo_source, pay * sc / 1e6, cost * sc / 1e6, dpo, r.dpo, diff, abs(diff) <= 2, typ, pl, cl, r.filing_url if r.dpo_source == "sec" else r.source_url, doc))
    return rows

if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "explore":
        for _, r in S[S.dpo_source == "sec"].iterrows(): explore(r)
    else:
        for x in report(): print(x[:10])
        print(sum(x[8] for x in report()), "/", len(S))
