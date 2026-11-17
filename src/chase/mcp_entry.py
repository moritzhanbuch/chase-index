"""Console entry point `chase-index-mcp`: runs mcp/server.py (stdio) from the repository checkout.

The data lives in the repository (data/processed), so the server needs the checkout, not just the
package. CHASE_INDEX_ROOT overrides where that checkout is.
"""
from __future__ import annotations

import os
import runpy
import sys
from pathlib import Path


def root() -> Path:
    r = Path(os.environ.get("CHASE_INDEX_ROOT") or Path(__file__).resolve().parents[2])
    if not (r / "data" / "processed" / "companies.parquet").exists():
        sys.exit(f"chase-index: no data at {r}/data/processed. Set CHASE_INDEX_ROOT to the repository checkout.")
    return r


def main() -> None:
    r = root()
    os.environ["CHASE_INDEX_ROOT"] = str(r)
    runpy.run_path(str(r / "mcp" / "server.py"), run_name="__main__")


if __name__ == "__main__":
    main()
