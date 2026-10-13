"""BOX — vintage drift decomposition (time / practice vs remaining-inventory rock vs spacing), read-only.

    python -m scripts.box_drift_decomp [--wells docs/box/step1-2026-10-06] [--out docs/box/step6-2026-10-12/decomp]

See box/drift_decomp.py. Writes nothing to the warehouse.
"""

from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

from box import drift_decomp as dd
from etl.db import get_connection


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--wells", type=Path, default=Path("docs") / "box" / "step1-2026-10-06")
    ap.add_argument("--out", type=Path, default=Path("docs") / "box" / "step6-2026-10-12" / "decomp")
    a = ap.parse_args(argv)
    t0 = time.time()
    with get_connection() as conn:
        res = dd.run(conn, a.wells, a.out)
    print(res["summary"]["coverage"])
    for k in ("rock", "yeff", "het", "step"):
        print(res[k].round(3).to_string())
    print(f"wrote {a.out}  ({time.time() - t0:.0f} s)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
