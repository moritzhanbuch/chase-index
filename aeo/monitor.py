"""AEO share-of-voice monitor (baseline tool).

Sends unbranded buyer questions to each answer engine for which an API key exists in the
environment, records which vendors each answer names, and computes share of voice for
your brand (--brand or AEO_BRAND) versus the usual shortlist. Re-run every two weeks after
publishing the index to see whether citations move.

Runs only through official APIs. It never touches consumer chat UIs.

    python aeo/monitor.py --dry-run          # show prompts + cost estimate, call nothing
    python aeo/monitor.py                    # run against every provider with a key
    python aeo/monitor.py --providers anthropic --runs 2
    python aeo/monitor.py --brand "Your Brand"   # track your own name next to the shortlist

Keys (all optional, read from .env): ANTHROPIC_API_KEY, OPENAI_API_KEY, PERPLEXITY_API_KEY.
Spend guard: estimated cost is checked against MAX_API_SPEND_USD (default 15) before any call.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

import httpx
from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[1]
load_dotenv(ROOT / ".env")
RESULTS = ROOT / "aeo" / "results"

# The three unbranded prompts are the ones from the public thread that showed the gap
# (a public X thread, 2026-11-09). The five variants are ours.
PROMPTS = [
    {"id": "p1", "origin": "public_thread",
     "text": "What software automates chasing suppliers and customers for invoice approvals and payment status?"},
    {"id": "p2", "origin": "public_thread",
     "text": "What are the best AI agents for AP and AR automation for large enterprises?"},
    {"id": "p3", "origin": "public_thread",
     "text": "Which tools help capture early-payment discounts and reduce manual invoice follow-ups?"},
    {"id": "v1", "origin": "variant",
     "text": "We run SAP S/4HANA. Which AI tools can resolve invoice disputes with suppliers automatically?"},
    {"id": "v2", "origin": "variant",
     "text": "What are the alternatives to dynamic discounting platforms for a Global 2000 company in Europe?"},
    {"id": "v3", "origin": "variant",
     "text": "Is there a network where a buyer's AI agent and a supplier's AI agent settle invoices directly?"},
    {"id": "v4", "origin": "variant",
     "text": "How can a CFO reduce supplier payment delays and late-payment complaints without adding AP headcount?"},
    {"id": "v5", "origin": "variant",
     "text": "Which vendors offer agentic accounts payable with outcome-based pricing?"},
]

# Vendor name -> regex. The shortlist answer engines gave in a public thread (2026-11-09).
# Your own brand is added at run time with --brand or AEO_BRAND (see brand_pattern).
VENDORS = {
    "Esker": r"\besker\b",
    "Stampli": r"\bstampli\b",
    "Tipalti": r"\btipalti\b",
    "BILL": r"\bbill\.com\b|\bBILL\b(?=[\s,.)(])",
    "HighRadius": r"\bhigh\s?radius\b",
    "Coupa": r"\bcoupa\b",
    "Basware": r"\bbasware\b",
    "SAP Taulia": r"\btaulia\b",
    "C2FO": r"\bc2fo\b",
    "Versapay": r"\bversapay\b",
    "Medius": r"\bmedius\b",
    "Serrala": r"\bserrala\b",
    "Billtrust": r"\bbilltrust\b",
}

# Default models. Override with --anthropic-model etc. Rough USD prices per million tokens
# (input, output) are only used for the spend guard; check current price lists before trusting them.
PROVIDERS = {
    "anthropic": {"env": "ANTHROPIC_API_KEY", "model": "claude-sonnet-5-5", "price": (3.0, 15.0)},
    "openai": {"env": "OPENAI_API_KEY", "model": "gpt-4o", "price": (2.5, 10.0)},
    "perplexity": {"env": "PERPLEXITY_API_KEY", "model": "sonar", "price": (1.0, 1.0)},
}
MAX_TOKENS = 700


def brand_pattern(brand: str) -> str:
    """Regex for a brand name, tolerant of spacing ("Acme Pay" also matches "AcmePay")."""
    return r"\b" + r"\s*".join(re.escape(w) for w in brand.split()) + r"\b"


def vendors(brand: str | None = None) -> dict[str, str]:
    """The tracked vendors: your brand first (when given), then the shortlist."""
    return ({brand: brand_pattern(brand)} if brand else {}) | VENDORS


def find_vendors(text: str, brand: str | None = None) -> list[str]:
    """Vendors named in an answer. BILL is matched case-sensitively to avoid the common noun."""
    found = []
    for name, pat in vendors(brand).items():
        flags = 0 if name == "BILL" else re.IGNORECASE
        if re.search(pat, text, flags):
            found.append(name)
    return found


def share_of_voice(rows: list[dict], brand: str | None = None) -> dict:
    """Share of answers that mention each vendor, overall and per provider."""
    out: dict = {"overall": {}, "by_provider": {}}
    def tally(sub):
        n = len(sub)
        return {v: round(sum(v in r["vendors"] for r in sub) / n, 3) if n else None for v in vendors(brand)}
    out["overall"] = tally(rows)
    out["n_answers"] = len(rows)
    for p in sorted({r["provider"] for r in rows}):
        out["by_provider"][p] = tally([r for r in rows if r["provider"] == p])
    return out


def estimate_cost(providers: list[str], runs: int) -> float:
    total = 0.0
    for p in providers:
        pin, pout = PROVIDERS[p]["price"]
        calls = len(PROMPTS) * runs
        total += calls * (60 * pin + MAX_TOKENS * pout) / 1e6
    return round(total, 4)


def ask_anthropic(prompt: str, model: str, key: str) -> str:
    r = httpx.post("https://api.anthropic.com/v1/messages", timeout=120,
                   headers={"x-api-key": key, "anthropic-version": "2023-06-01", "content-type": "application/json"},
                   json={"model": model, "max_tokens": MAX_TOKENS, "messages": [{"role": "user", "content": prompt}]})
    r.raise_for_status()
    return "".join(b.get("text", "") for b in r.json()["content"] if b.get("type") == "text")


def ask_openai_compatible(base: str, prompt: str, model: str, key: str) -> str:
    r = httpx.post(f"{base}/chat/completions", timeout=120,
                   headers={"Authorization": f"Bearer {key}", "content-type": "application/json"},
                   json={"model": model, "max_tokens": MAX_TOKENS, "messages": [{"role": "user", "content": prompt}]})
    r.raise_for_status()
    return r.json()["choices"][0]["message"]["content"]


def ask(provider: str, prompt: str, model: str, key: str) -> str:
    if provider == "anthropic":
        return ask_anthropic(prompt, model, key)
    if provider == "openai":
        return ask_openai_compatible("https://api.openai.com/v1", prompt, model, key)
    if provider == "perplexity":
        return ask_openai_compatible("https://api.perplexity.ai", prompt, model, key)
    raise ValueError(provider)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--providers", nargs="*", choices=list(PROVIDERS), help="default: every provider with a key")
    ap.add_argument("--runs", type=int, default=1, help="repeats per prompt (answers vary between runs)")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--brand", default=os.environ.get("AEO_BRAND"), help="your brand, tracked next to the shortlist")
    for p in PROVIDERS:
        ap.add_argument(f"--{p}-model", default=PROVIDERS[p]["model"])
    args = ap.parse_args()

    available = [p for p in PROVIDERS if os.environ.get(PROVIDERS[p]["env"])]
    providers = [p for p in (args.providers or available) if p in available]
    cap = float(os.environ.get("MAX_API_SPEND_USD") or 15)
    cost = estimate_cost(providers, args.runs)
    print(f"Prompts: {len(PROMPTS)} | providers with keys: {providers or 'none'} | runs: {args.runs} | "
          f"estimated cost: ${cost} (cap ${cap})")
    if args.dry_run or not providers:
        for p in PROMPTS:
            print(f"  [{p['id']}] {p['text']}")
        if not providers:
            print("No API keys set. Nothing was sent. Add a key to .env and re-run.")
        return 0
    if cost > cap:
        print("Estimated cost exceeds MAX_API_SPEND_USD. Aborting.")
        return 1

    rows = []
    for provider in providers:
        model = getattr(args, f"{provider}_model")
        key = os.environ[PROVIDERS[provider]["env"]]
        for run in range(args.runs):
            for p in PROMPTS:
                try:
                    answer = ask(provider, p["text"], model, key)
                    err = None
                except Exception as e:  # keep going, record the failure
                    answer, err = "", f"{type(e).__name__}: {str(e)[:200]}"
                rows.append({"provider": provider, "model": model, "run": run, "prompt_id": p["id"],
                             "prompt": p["text"], "answer": answer, "vendors": find_vendors(answer, args.brand), "error": err,
                             "asked_at": datetime.now(timezone.utc).isoformat(timespec="seconds")})
                print(f"  {provider} {p['id']} run {run}: {rows[-1]['vendors'] or '-'}{' ERROR' if err else ''}")

    ok = [r for r in rows if not r["error"]]
    summary = share_of_voice(ok, args.brand)
    summary["brand"] = args.brand
    summary["estimated_cost_usd"] = cost
    stamp = datetime.now(timezone.utc).strftime("%Y-%m-%d_%H%M")
    RESULTS.mkdir(parents=True, exist_ok=True)
    (RESULTS / f"{stamp}_answers.json").write_text(json.dumps(rows, indent=2, ensure_ascii=False))
    (RESULTS / f"{stamp}_summary.json").write_text(json.dumps(summary, indent=2))
    print(json.dumps(summary["overall"], indent=2))
    print(f"Saved to aeo/results/{stamp}_*.json")
    return 0


if __name__ == "__main__":
    sys.exit(main())
