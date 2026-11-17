#!/usr/bin/env python3
"""Start the Chase Index MCP server over stdio, call every tool, save evals/reports/mcp_demo.md.

    uv run python mcp/demo_client.py
    uv run python mcp/demo_client.py "Siemens Energy" "Diageo" "Inditex"

Every tool answers in text (short answer first, then a compact Details block); the checks read that text.
"""
from __future__ import annotations

import asyncio
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

ROOT = Path(__file__).resolve().parents[1]
COMPANIES = sys.argv[1:] or ["Nestlé", "Telefónica", "Walmart"]
EXPECTED_TOOLS = {"start_here", "weekly_queue", "get_account_brief", "dinner_builder", "triggers", "top_targets",
                  "get_payment_profile", "lookup_uk_supplier_payment_record", "search_companies", "account_workspace",
                  "byod_status", "explain_methodology"}
PRIVATE = re.compile(r'"(who_named|who_source|people_private|people)": (?!null)')


def _answer(text: str, n: int = 1200) -> str:
    head = text.split("\n\n---\n")[0]
    return head if len(head) <= n else head[:n] + "\n... (truncated)"


async def main() -> int:
    params = StdioServerParameters(command=sys.executable, args=[str(ROOT / "mcp" / "server.py")],
                                   env={"CHASE_INDEX_ROOT": str(ROOT), "PATH": "/usr/bin:/bin"})
    out = ["# MCP server demo", "", f"Run at {datetime.now(timezone.utc).isoformat(timespec='seconds')}. "
           "The script starts `mcp/server.py` over stdio with the official MCP Python SDK client, lists the tools and calls each one. "
           "Below each call is the short answer the tool returns before its Details block.", ""]
    failures, checks = [], []
    async with stdio_client(params) as (r, w):
        async with ClientSession(r, w) as s:
            await s.initialize()
            tools = {t.name: t for t in (await s.list_tools()).tools}
            out += ["## Tools exposed", ""] + [f"- `{n}`: {t.description.strip().splitlines()[0]}" for n, t in tools.items()] + [""]
            if EXPECTED_TOOLS - set(tools):
                failures.append(f"missing tools: {EXPECTED_TOOLS - set(tools)}")

            async def call(name, args, subject, must: tuple[str, ...] = ()):
                res = await s.call_tool(name, args)
                text = "\n".join(c.text for c in res.content if getattr(c, "text", None))
                ok = not res.is_error and bool(text) and not text.lstrip().startswith("{") and all(m in text for m in must)
                checks.append((subject, f"{name}({', '.join(f'{k}={v}' for k, v in args.items())})", ok))
                if PRIVATE.search(text):     # the report is tracked in git: never write local private names into it
                    text = PRIVATE.sub(r'"\1": "[redacted]", "_": ', text)
                out.extend([f"### `{name}` {args or ''}", "", "```text", _answer(text), "```", ""])
                return text

            await call("start_here", {}, "first run", ("Try asking",))
            await call("weekly_queue", {"limit": 3}, "this week", ("Open with", "source"))
            await call("weekly_queue", {"limit": 3, "demo": True}, "demo", ("SYNTHETIC",))
            for c in COMPANIES:
                await call("get_account_brief", {"company": c}, c, ("Key number",))
                await call("get_payment_profile", {"company": c}, c)
                await call("search_companies", {"query": c.split()[0], "limit": 3}, c)
            await call("dinner_builder", {"city": "munich"}, "munich", ("accounts to invite", "source"))
            await call("triggers", {"since": "2026-09-01", "limit": 5}, "since 2026-09-01", ("dated events",))
            await call("top_targets", {"country": "DE", "limit": 3}, "DE", ("Tier",))
            await call("lookup_uk_supplier_payment_record", {"customer": "Tesco Stores", "limit": 2}, "Tesco Stores", ("days to pay",))
            await call("account_workspace", {"company": COMPANIES[0]}, COMPANIES[0], ("Details (structured, full record)",))
            await call("byod_status", {}, "local", ("Your own data",))
            await call("explain_methodology", {"topic": "DPO"}, "DPO", ("DPO",))
    failures += [f"{n} failed for {c}" for c, n, ok in checks if not ok]
    summary = ["## Result", "", f"- Tools listed: {len(tools)} (expected {len(EXPECTED_TOOLS)})",
               f"- Calls checked: {len(checks)}, passed: {sum(ok for *_, ok in checks)}",
               f"- Failures: {failures or 'none'}", "", "| Subject | Call | OK |", "|---|---|---|"] + \
              [f"| {c} | `{n}` | {'yes' if ok else 'NO'} |" for c, n, ok in checks] + [""]
    (ROOT / "evals" / "reports" / "mcp_demo.md").write_text(("\n".join(out[:4] + summary + out[4:]) + "\n").replace(str(ROOT), "<repo>"))
    print("\n".join(summary))
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
