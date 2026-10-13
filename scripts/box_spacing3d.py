"""BOX — 3-D spacing prototype (read-only): features for the WCA wells + the spacing-vs-decline-drift test.

    python -m scripts.box_spacing3d [--wells docs/box/step1-2026-10-06] [--out docs/box/step6-2026-10-12/spacing3d]

See box/spacing3d.py (geometry, features) and box/spacing3d_report.py (universe, tests, page). Reads curated.wells,
curated.production, raw_novi."WellSpacing" and the TC areas of record inside READ ONLY transactions; writes nothing.
"""

from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

from box import spacing3d_report as sr
from etl.db import get_connection


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--wells", type=Path, default=Path("docs") / "box" / "step1-2026-10-06")
    ap.add_argument("--out", type=Path, default=Path("docs") / "box" / "step6-2026-10-12" / "spacing3d")
    a = ap.parse_args(argv)
    t0 = time.time()
    with get_connection() as conn:
        res = sr.run(conn, a.wells, a.out)
    print({k: v for k, v in res["summary"].items() if k != "params"})
    print(res["trend"].round(3).to_string())
    print(res["fe_trend"].round(3).to_string())
    print(res["yeff"].round(3).to_string())
    print(res["case"].round(1).to_string())
    for k in ("early_year", "coefs", "mediated"):
        print(res["med"][k].round(4).to_string())
    print(f"wrote {a.out}  ({time.time() - t0:.0f} s)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
