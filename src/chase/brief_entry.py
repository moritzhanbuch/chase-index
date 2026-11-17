"""Console entry point `chase-brief`: the /chase-brief skill script from the repository checkout."""
from __future__ import annotations

import os
import runpy
import sys

from chase.mcp_entry import root


def main() -> None:
    r = root()
    os.environ["CHASE_INDEX_ROOT"] = str(r)
    sys.argv[0] = "chase-brief"
    runpy.run_path(str(r / "skill" / "chase-brief" / "scripts" / "chase_brief.py"), run_name="__main__")


if __name__ == "__main__":
    main()
