"""QA spot-check: compare uk_payment_practices.parquet rows with official GOV.UK report pages.
Run: PYTHONPATH=src .venv/bin/python evals/uk_spotcheck.py
Uses the shared rate-limited client; fetches /report/{id} only (no query strings).
The 'Approved by' name is never captured or printed."""
import re, sys, json
from datetime import datetime
from pathlib import Path
import pandas as pd
from bs4 import BeautifulSoup
from chase.common.http import fetch

ROOT = Path(__file__).resolve().parents[1]
SEED = 20261116
COLS = ["report_id","company_name","company_number","period_start","period_end","filing_date","avg_days_to_pay",
        "pct_paid_within_30","pct_paid_31_60","pct_paid_over_60","pct_paid_late",
        "shortest_standard_payment_period_days","longest_standard_payment_period_days",
        "max_contractual_payment_period_days","quality_flag","is_usable","had_qualifying_contracts"]

def sample():
    d = pd.read_parquet(ROOT/"data/processed/uk_payment_practices.parquet", columns=COLS)
    u = d[d.is_usable].sample(16, random_state=SEED)
    n = d[~d.is_usable].sample(4, random_state=SEED)
    return pd.concat([u, n])

def pdate(s):
    return datetime.strptime(re.sub(r"\s+", " ", s.strip()), "%d %B %Y").date()

def parse(html):
    s = BeautifulSoup(html, "lxml")
    m = s.find("main") or s
    lines = [l for l in m.get_text("\n", strip=True).split("\n")]
    # drop approver name (line after "Approved by:")
    out = []; skip = False
    for l in lines:
        if skip: skip = False; continue
        out.append(l)
        if l.startswith("Approved by"): skip = True
    t = "\n".join(out)
    flat = re.sub(r"\s+", " ", t)
    p = {"_text": flat}
    i = out.index("Published reports") + 1 if "Published reports" in out else 0
    p["company_name"] = out[i]
    mm = re.search(r"Company number: (\S+)", flat); p["company_number"] = mm.group(1) if mm else None
    mm = re.search(r"Reporting period: (\d+ \w+ \d{4}) to (\d+ \w+ \d{4})", flat)
    if mm: p["period_start"], p["period_end"] = pdate(mm[1]), pdate(mm[2])
    mm = re.search(r"Report filed on: (\d+ \w+ \d{4})", flat)
    if mm: p["filing_date"] = pdate(mm[1])
    def num(rx):
        mm = re.search(rx, flat); return float(mm[1]) if mm else None
    p["avg_days_to_pay"] = num(r"Average time taken to pay invoices: (\d+(?:\.\d+)?) days")
    p["pct_paid_within_30"] = num(r"within 30 days: (\d+(?:\.\d+)?)%")
    p["pct_paid_31_60"] = num(r"in 31 to 60 days: (\d+(?:\.\d+)?)%")
    p["pct_paid_over_60"] = num(r"in 61 days or more: (\d+(?:\.\d+)?)%")
    p["pct_paid_late"] = num(r"agreed period: (\d+(?:\.\d+)?)%")
    p["shortest_standard_payment_period_days"] = num(r"Shortest standard payment periods? (\d+) days")
    p["longest_standard_payment_period_days"] = num(r"Longest standard payment periods? (\d+) days")
    p["max_contractual_payment_period_days"] = num(r"Maximum contractual payment period agreed (\d+) days")
    return p

FIELDS = ["company_name","company_number","period_start","period_end","filing_date","avg_days_to_pay",
          "pct_paid_within_30","pct_paid_31_60","pct_paid_over_60","pct_paid_late",
          "shortest_standard_payment_period_days","longest_standard_payment_period_days",
          "max_contractual_payment_period_days"]

def eq(a, b):
    if pd.isna(a) if not isinstance(a, str) and a is not None else a is None:
        return b is None
    if b is None: return False
    if isinstance(a, str): return a.strip().upper() == str(b).strip().upper()
    if isinstance(a, (int, float)): return abs(float(a) - float(b)) < 1e-9
    return a == b

def main():
    rows = sample(); res = []
    for _, r in rows.iterrows():
        url = f"https://check-payment-practices.service.gov.uk/report/{int(r.report_id)}"
        resp = fetch(url); p = parse(resp.text)
        mism = []; ok = 0
        for f in FIELDS:
            tv = r[f]; tv = None if (not isinstance(tv, str) and pd.isna(tv)) else tv
            pv = p.get(f)
            if hasattr(tv, "item") and not isinstance(tv, str): tv = tv.item()
            if eq(tv, pv): ok += 1
            else: mism.append((f, tv, pv))
        res.append(dict(report_id=int(r.report_id), company=r.company_name, url=url, usable=bool(r.is_usable),
                        flag=r.quality_flag, hq=r.had_qualifying_contracts, ok=ok, n=len(FIELDS), mism=mism,
                        snippet=(re.search(r"The business stated that it did not enter into any qualifying contracts in the reporting period\.", p["_text"]) or [p["_text"][:0]])[0] if "did not enter into any qualifying" in p["_text"] else "page shows payment statistics (no 'no qualifying contracts' statement)"))
        print(res[-1]["report_id"], ok, len(FIELDS), mism, file=sys.stderr)
    tf = sum(x["ok"] for x in res); tn = sum(x["n"] for x in res); full = sum(1 for x in res if not x["mism"])
    L = ["# UK payment practices spot-check (qa)", "",
         "Checked: `data/processed/uk_payment_practices.parquet` rows vs official report pages on check-payment-practices.service.gov.uk.", "",
         f"- Sample: 20 rows, `random_state={SEED}` (16 `is_usable=True`, 4 `is_usable=False`), `DataFrame.sample` on each subset, no cherry-picking.",
         "- Method: `evals/uk_spotcheck.py` fetches `/report/{report_id}` via the shared client (1 req/s, cached, no query strings), parses the HTML and compares 13 fields (name, company number, period start/end, filing date, avg days to pay, % within 30, 31-60, 61+, % not paid within agreed terms, shortest/longest standard period, max contractual period). Names compared case-insensitively. The 'Approved by' person is deliberately not captured.",
         "", f"## Result: {full}/20 rows fully matching; {tf}/{tn} fields matching", "",
         "| report_id | company | usable | fields ok | mismatches (table vs page) |", "|---|---|---|---|---|"]
    for x in res:
        mm = "; ".join(f"{f}: {a!r} vs {b!r}" for f, a, b in x["mism"]) or "none"
        L.append(f"| [{x['report_id']}]({x['url']}) | {x['company']} | {x['usable']} | {x['ok']}/{x['n']} | {mm} |")
    L += ["", "## Non-usable rows (quality_flag consistency)", ""]
    for x in res:
        if not x["usable"]:
            L.append(f"- report {x['report_id']} ({x['company']}): flag `{x['flag']}`, had_qualifying_contracts={x['hq']}. Page: \"{x['snippet']}\" -> {'consistent' if 'did not enter' in x['snippet'] else 'INCONSISTENT'}")
    L += ["", "## Failures and likely cause", "", "See mismatch column; if none, no failures."]
    (ROOT/"evals/reports/uk_spotcheck.md").write_text("\n".join(L) + "\n")
    print(f"{full}/20 rows, {tf}/{tn} fields")

main()
