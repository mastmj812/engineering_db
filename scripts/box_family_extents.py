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

from box import basin as bsn
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
    ap.add_argument("--visual-bodies", type=int, default=None, help="render the visual-check map per pool, marking outline components with >= N modern laterals")
    ap.add_argument("--basin", default="delaware", help="the basin (step 19): its D23 edge metric, PUD pull and labels")
    ap.add_argument("--step", default=None, help="step label on the pages (step 20a: '20a')")
    a = ap.parse_args(argv)
    t0 = time.time()
    page = None
    if a.basin != bsn.DELAWARE:  # step 20a: D134 A (Delaware r / c and D27 constants), D128 (one extent per bench), D117 undrilled
        label = bsn.get(a.basin).label
        page = {"step": a.step or "20a",
                "title": f"BOX step {a.step or '20a'} — proposed D27 extents: {label} {' / '.join(a.pool)} (v{a.version}, generated, NOT stored)",
                "sets_note": f"Well sets = the step-{a.step or '20a'} QC sets (<code>../wells_final_&lt;bench&gt;.csv</code>; one extent per bench, D128).",
                "rules_note": "D134 A: the Delaware D23 r / c and D27 constants as the Midland's (no step-2 repeat); D26 legacy fill; no updip limit; "
                              "no potash area (D24 is the Delaware's).",
                "pud_heading": "Undrilled Novi sticks inside (D117: PUD + RES; remaining_pud / conflict / not yet reconciled; ≥ 50 % of the stick inside)"}
    with get_connection() as conn:
        res = fe.run(conn, a.wells, a.out or a.wells / "extents", tuple(a.pool), a.version, a.regress, _git_sha(), a.visual_bodies, basin=a.basin, page=page)
    s = res["summary"]
    for p, st in s["pools"].items():
        print(f"{p:>6}: extent {st['extent_sqmi']:,.0f} sq mi (core {st['core_sqmi']:,.0f}), {st['n_parts']} parts, {st['n_holes']} holes, "
              f"fronts {list(st['fronts']) or 'none'}, isolated tests {st['n_isolated_tests']}, developed outside {st['developed_outside']}")
    for r in s["pud_d1"]:
        print(f"  undrilled {r['formation_blueox']} {r.get('category', 'PUD')}: in extent {r['in extent']:,} / in core {r['in drilled core']:,}")
    for p, r in s["regression"].items():
        print(f"  regression {p}: record {r['record_sqmi']:,.2f} rebuilt {r['rebuilt_sqmi']:,.2f} ({r['rel_diff']:+.2e})")
    print(f"wrote {a.out or a.wells / 'extents'}  ({time.time() - t0:.0f} s)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
