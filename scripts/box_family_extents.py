"""BOX step 15 — proposed D27 extents for a bench family (read-only; nothing stored).

    python -m scripts.box_family_extents --wells docs/box/step15a-2026-10-16 --pool BS3_S BS3_C
                                         [--out <wells>/extents] [--regress docs/box/step1-2026-10-06]

Builds each pool's extent with the step-3 method + calibration of record (box/family_extent.py), writes review pages,
CSVs, GeoJSON and the geology shapefile package, and (with --regress) rebuilds the record WCA / BS2_S extents from the
frozen gate-1 sets as a regression guard. Storing an extent in box.extent is a separate, explicit go-apply.
"""

from __future__ import annotations

import argparse
import subprocess
import sys
import time
from pathlib import Path

from box import family_extent as fe
from etl.db import get_connection


def _git_sha() -> str:
    sha = subprocess.run(["git", "rev-parse", "--short", "HEAD"], capture_output=True, text=True, check=False).stdout.strip()
    dirty = subprocess.run(["git", "status", "--porcelain", "--untracked-files=no"], capture_output=True, text=True, check=False).stdout.strip()
    return sha + ("+dirty" if dirty else "")


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--wells", type=Path, required=True)
    ap.add_argument("--pool", nargs="+", required=True)
    ap.add_argument("--out", type=Path, default=None)
    ap.add_argument("--version", type=int, default=1)
    ap.add_argument("--regress", type=Path, default=None, help="gate-1 dir: rebuild the record extents as a regression guard")
    a = ap.parse_args(argv)
    t0 = time.time()
    with get_connection() as conn:
        res = fe.run(conn, a.wells, a.out or a.wells / "extents", tuple(a.pool), a.version, a.regress, _git_sha())
    s = res["summary"]
    for p, st in s["pools"].items():
        print(f"{p:>6}: extent {st['extent_sqmi']:,.0f} sq mi (core {st['core_sqmi']:,.0f}), {st['n_parts']} parts, {st['n_holes']} holes, "
              f"fronts {list(st['fronts']) or 'none'}, isolated tests {st['n_isolated_tests']}, developed outside {st['developed_outside']}")
    for r in s["pud_d1"]:
        print(f"  D1 PUDs {r['formation_blueox']}: in extent {r['in extent']:,} / in core {r['in drilled core']:,}")
    for p, r in s["regression"].items():
        print(f"  regression {p}: record {r['record_sqmi']:,.2f} rebuilt {r['rebuilt_sqmi']:,.2f} ({r['rel_diff']:+.2e})")
    print(f"wrote {a.out or a.wells / 'extents'}  ({time.time() - t0:.0f} s)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
