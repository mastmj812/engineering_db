"""BOX step 5b — baseline type curve per WCA TC area per stream; review page (read-only).

    python -m scripts.box_tc_curves [--wells docs/box/step1-2026-10-06] [--out docs/box/step5b-YYYY-MM-DD] [--workers N]

Fits every candidate well with the shared engine (blueox-boxfit, anduin's per-well pipeline), builds
one curve per TC area of record per stream through the D10 ladder, and writes the curve pages plus the
gate-5 tests (WCA_1 vs WCA_2, b / Di vs GOR, the D30 gas level). Reads the warehouse through the ETL
session pooler inside READ ONLY transactions; writes nothing to it (box.type_curve DDL is step 5d).
See box/tc_curve.py (method) and box/tc_curve_report.py (inputs, tests, page).
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import sys
import time
from importlib import metadata
from pathlib import Path

from box.tc_curve_report import run
from etl.db import get_connection


def boxfit_sha() -> str:
    """The anduin commit the installed blueox-boxfit was built from (pip's direct_url.json)."""
    try:
        info = json.loads(metadata.distribution("blueox-boxfit").read_text("direct_url.json") or "{}")
    except metadata.PackageNotFoundError:
        return "not-installed"
    return (info.get("vcs_info") or {}).get("commit_id") or info.get("url", "unknown")


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--wells", type=Path, default=Path("docs") / "box" / "step1-2026-10-06")
    ap.add_argument("--out", type=Path, default=Path("docs") / "box" / f"step5b-{dt.datetime.now(tz=dt.UTC).astimezone():%Y-%m-%d}")
    ap.add_argument("--workers", type=int, default=None)
    ap.add_argument("--asof", type=dt.date.fromisoformat, default=None, help="production cutoff (default: last fully reported month)")
    a = ap.parse_args(argv)
    t0 = time.time()
    with get_connection() as conn:
        res = run(conn, a.wells, a.out, boxfit_sha(), a.workers, a.asof)
    s = res["summary"]
    print(f"WCA: {s['n_areas']} area curves from {s['n_cohort']:,} cohort wells ({s['n_wells_fitted']:,} wells fitted), production through {s['prod_asof']}; "
          f"rungs {s['rungs']}; max |sum of exact months - stored| / stored (D39) {s['max_abs_reconcile']:.1e} ({'PASS' if s['reconcile_pass'] else 'FAIL'} < 0.1 %)")
    print(f"wrote {a.out}  ({time.time() - t0:.0f} s)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
