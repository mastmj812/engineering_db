"""BOX step 6 (fail branch) — shape-drift dig: why newer WCA wells decline faster after month 6 (read-only).

    python -m scripts.box_shape_drift [--wells docs/box/step1-2026-10-06] [--out docs/box/step6-2026-10-12/shape]

See box/shape_drift.py. Reads curated.production, curated.wells_enriched, raw_novi."WellSpacing" and the TC areas of
record inside READ ONLY transactions; writes nothing to the warehouse.
"""

from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

from box import shape_drift as sd
from etl.db import get_connection


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--wells", type=Path, default=Path("docs") / "box" / "step1-2026-10-06")
    ap.add_argument("--out", type=Path, default=Path("docs") / "box" / "step6-2026-10-12" / "shape")
    a = ap.parse_args(argv)
    t0 = time.time()
    with get_connection() as conn:
        res = sd.run(conn, a.wells, a.out)
    print(res["raw"].round(3).to_string())
    y = res["yeff"]
    print(y.round(3).to_string())
    print(res["ctrl"].round(4).to_string())
    print(f"wrote {a.out}  ({time.time() - t0:.0f} s)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
