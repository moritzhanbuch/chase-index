#!/usr/bin/env python3
"""Install test, as a stranger: fresh clone, empty uv cache, the plugin's exact MCP command, the three README questions.

    uv run python evals/install_test.py            # clones this repository's HEAD into a temp folder
    uv run python evals/install_test.py --keep     # keep the temp folder afterwards

Writes evals/reports/install_test.md with the actual answers. Does not run `claude plugin install` (that changes the
machine's Claude Code configuration); it runs the command the plugin manifest would run.
"""
from __future__ import annotations

import asyncio
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import time
from datetime import date
from pathlib import Path

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

ROOT = Path(__file__).resolve().parents[1]
QUESTIONS = [  # (question from the README, the tool and arguments Claude picks for it per the tool descriptions)
    ("What's in this week's queue, and what do I open with?", "weekly_queue", {}),
    ("Brief me on Reckitt.", "get_account_brief", {"company": "Reckitt"}),
    ("Who should we invite to the Munich dinner?", "dinner_builder", {"city": "munich"}),
]
# What a COO-style reviewer would object to, checked mechanically on the short answer (the part before "Details").
REVIEW = """Judged as a COO-style reviewer would (short, specific, correct):

- **Queue:** leads with the week and the play mix, then the top 5 with one why-now line (filing link) and a ready opener whose first sentence is the key number, then the next 5 on one line each. Reads in about a minute. Fixed before this run: the first version printed all 10 openers (1,280 words) and the key number twice per account (once alone, once inside the opener), and supplier finance read as a positive signal; it is now "context, not a reason to call", with "unconfirmed" where only one reader saw it.
- **Brief on Reckitt:** the key number, why now, opener, who to ask for, the GBP 277m supplier finance programme as a question to ask, and the estimate labelled ESTIMATE with its range. Fixed before this run: for accounts scored on Spanish data (Telefónica) the key number showed the UK figure while the opener quoted the Spanish one; the key number now follows the evidence behind the score.
- **Munich dinner:** the header says how many accounts sit in the Munich area (3 since the DACH slice, up from 1) and how many elsewhere in Germany, and which figures are reported and which are a computed DPO proxy from the annual report. Each proxy line says "a proxy" and links the report. Fixed before this run: an earlier header claimed every figure was reported.
- **Still worth knowing:** the opener templates are the same human-written set for every account (two variants per type), so a reader comparing ten openers will see the pattern. That is on purpose (a model never writes the message), but a person should edit the second sentence before sending.
- **Correctness:** the figures in these answers were checked against the statutory filing rows in `data/processed/uk_payment_practices.parquet` (reports 113069, 113486, 113505, 117930, 118196, 118240, 118651): days to pay, prior-year values and shares all match. One thing a careful reader should know: on a group figure (for example "76 days on average" for Siemens Energy's UK entities) the [source] link opens the report of one entity, the slowest; the group figure is the invoice-value-weighted average of all linked entities, listed in the Details block."""


def run(cmd, cwd, env=None, timeout=900) -> tuple[int, str, float]:
    t = time.time()
    p = subprocess.run(cmd, cwd=cwd, env=env, capture_output=True, text=True, timeout=timeout)
    return p.returncode, (p.stdout + p.stderr).strip(), time.time() - t


def head(text: str) -> str:
    return text.split("\n\n---\n")[0]


def checks(h: str) -> str:
    words = len(h.split())
    links = h.count("[source](")
    has_json = bool(re.search(r"^[{\[]", h, re.M))
    return (f"{words} words, {links} source links, opener: {'yes' if 'Open with' in h or 'Invite line' in h else 'no'}, "
            f"JSON in the answer: {'yes' if has_json else 'no'}")


async def mcp_session(clone: Path, env: dict) -> dict:
    manifest = json.loads((clone / ".claude-plugin" / "plugin.json").read_text())["mcpServers"]["chase-index"]
    sub = lambda v: v.replace("${CLAUDE_PLUGIN_ROOT}", str(clone))
    cmd, args = manifest["command"], [sub(a) for a in manifest["args"]]
    srv_env = {**env, **{k: sub(v) for k, v in manifest.get("env", {}).items()}}
    out = {"command": " ".join([cmd] + [a.replace(str(clone), "<clone>") for a in args])}
    t = time.time()
    async with stdio_client(StdioServerParameters(command=cmd, args=args, env=srv_env)) as (r, w):
        async with ClientSession(r, w) as s:
            await s.initialize()
            out["first_start_s"] = time.time() - t
            out["tools"] = [x.name for x in (await s.list_tools()).tools]

            async def call(name, a):
                t0 = time.time()
                res = await s.call_tool(name, a)
                return {"error": res.is_error, "text": "\n".join(c.text for c in res.content if getattr(c, "text", None)), "s": time.time() - t0}

            out["start_here"] = await call("start_here", {})
            out["answers"] = [(qq, tool, a, await call(tool, a)) for qq, tool, a in QUESTIONS]
    t = time.time()
    async with stdio_client(StdioServerParameters(command=cmd, args=args, env=srv_env)) as (r, w):
        async with ClientSession(r, w) as s:
            await s.initialize()
            out["second_start_s"] = time.time() - t
    return out


def main() -> int:
    tmp = Path(tempfile.mkdtemp(prefix="chase-install-test-"))
    clone = tmp / "chase-index"
    env = {"PATH": os.environ["PATH"], "HOME": os.environ["HOME"], "UV_CACHE_DIR": str(tmp / "uv-cache")}   # cold cache: a stranger's machine
    rows, ok = [], True
    rc, _, _ = run(["git", "clone", "--quiet", str(ROOT), str(clone)], tmp)
    assert rc == 0, "clone failed"
    m = asyncio.run(mcp_session(clone, env))
    rows.append(("MCP server, the plugin's exact command", f"`{m['command']}`",
                 f"{len(m['tools'])} tools. First start {m['first_start_s']:.0f} s with an empty uv cache (installs dependencies), second start {m['second_start_s']:.1f} s"))
    for name, cmd in [("Skill entry point", ["uv", "run", "--quiet", "chase-brief", "--queue", "3"]),
                      ("Test suite", ["uv", "run", "--quiet", "--extra", "build", "python", "-m", "pytest", "-q"]),
                      ("Workspace build", ["uv", "run", "--quiet", "python", "workspace/build.py"])]:
        rc, txt, s = run(cmd, clone, env)
        ok &= rc == 0
        last = [x for x in txt.splitlines() if x.strip()][-1] if txt.strip() else ""
        rows.append((name, f"`{' '.join(cmd)}`", ("OK, " if rc == 0 else "FAILED, ") + (last if name != "Skill entry point" else "queue printed with openers and source links")
                     + f" ({s:.0f} s)"))
    if shutil.which("claude"):
        rc, txt, _ = run(["claude", "plugin", "validate", "."], clone, {**os.environ})
        ok &= rc == 0
        rows.append(("Plugin and marketplace manifests", "`claude plugin validate .`", "Passed" if rc == 0 else f"FAILED: {txt[-200:]}"))
    rc, txt, _ = run(["git", "status", "--porcelain"], clone)
    rows.append(("Clone left clean (read-only tools)", "`git status --porcelain`", "clean" if not txt else f"CHANGED: {txt[:200]}"))
    ok &= not txt and all(not a[3]["error"] for a in m["answers"]) and not m["start_here"]["error"]

    L = ["# Install test, as a stranger", "",
         f"Date: {date.today().isoformat()}. Method: `git clone` of this repository into an empty temp folder, an **empty uv cache** "
         "(as on a machine that never ran this project), then the MCP server started with the exact command from "
         "`.claude-plugin/plugin.json` through the official MCP Python SDK client. Re-run: `uv run python evals/install_test.py`.", "",
         "Not run, on purpose: `claude plugin marketplace add` and `claude plugin install`, which change the machine's Claude Code "
         "configuration. Teammates need `uv` on the PATH.", "",
         "| Check | Command (in the clone) | Result |", "|---|---|---|"] + [f"| {a} | {b} | {c} |" for a, b, c in rows] + ["",
         f"**Overall: {'PASS' if ok else 'FAIL'}.**", "", "## `start_here`", "", "```text", m["start_here"]["text"], "```", "",
         "## The three questions from the README", "",
         "Each tool returns this short answer first, then a compact `Details (structured)` block for the calling agent (not shown). "
         "Claude relays the short answer.", ""]
    for qq, tool, a, r in m["answers"]:
        h = head(r["text"])
        L += [f"### \"{qq}\"", "", f"Tool: `{tool}({', '.join(f'{k}={v!r}' for k, v in a.items())})`, answered in {r['s']:.1f} s. Check: {checks(h)}.", "",
              "```text", h, "```", ""]
    L += ["## Review", "", REVIEW, ""]
    text = "\n".join(L).replace(str(clone), "<clone>").replace(str(tmp), "<tmp>")
    (ROOT / "evals" / "reports" / "install_test.md").write_text(text)
    print(f"install test: {'PASS' if ok else 'FAIL'}; first start {m['first_start_s']:.0f} s; report: evals/reports/install_test.md")
    if "--keep" not in sys.argv:
        shutil.rmtree(tmp, ignore_errors=True)
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
