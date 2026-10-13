"""BOX — 3-D spacing knob sweep (read-only): feature settings over one generous pair build.

    python -m scripts.box_spacing3d_sweep [--wells docs/box/step1-2026-10-06] [--out docs/box/step6-2026-10-12/spacing3d]

See box/spacing3d_sweep.py. Writes nothing to the warehouse.
"""

from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

from box import spacing3d_sweep as sw
from etl.db import get_connection


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--wells", type=Path, default=Path("docs") / "box" / "step1-2026-10-06")
    ap.add_argument("--out", type=Path, default=Path("docs") / "box" / "step6-2026-10-12" / "spacing3d")
    a = ap.parse_args(argv)
    t0 = time.time()
    with get_connection() as conn:
        res = sw.run(conn, a.wells, a.out)
    print(res["summary"]["reach"], res["summary"]["meta"])
    t = res["table"]
    print(t[["variant", "response", "n", "d_r2_pts", "yr2024_base", "yr2024_with", "absorbed", "median_xsec_ft2"]].round(4).to_string())
    print(f"wrote {a.out}  ({time.time() - t0:.0f} s)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
