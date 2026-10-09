"""BOX step 4 — TC areas on WCA: regionalize inside the extent of record, write the review page (read-only).

    python -m scripts.box_tc_areas [--wells docs/box/step1-2026-10-06] [--out docs/box/step4-YYYY-MM-DD] [--no-puds]
                                   [--store [--record]]

Reads the gate-1 final WCA well set, the WCA extent of record (box.extent), 24-mo / Novi 30-yr
columns and the D1 PUD universe count through the ETL session pooler inside READ ONLY
transactions. See box/tc_area.py for the method and box/tc_area_report.py for the cohorts.

--store additionally writes the areas to box.tc_area (sql/57). That is a warehouse WRITE: it needs
sql/57 applied (scripts.apply_box_tc_area, explicit go-apply) and Michael's explicit go-ahead.
--record makes the stored set the area version of record for its extent.
"""

from __future__ import annotations

import argparse
import datetime as dt
import sys
import time
from pathlib import Path

from box.tc_area_report import run
from etl.db import get_connection


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--wells", type=Path, default=Path("docs") / "box" / "step1-2026-10-06")
    ap.add_argument("--out", type=Path, default=Path("docs") / "box" / f"step4-{dt.datetime.now(tz=dt.UTC).astimezone():%Y-%m-%d}")
    ap.add_argument("--version", type=int, default=1)
    ap.add_argument("--no-puds", action="store_true", help="skip the read-only D1 PUD count per area")
    ap.add_argument("--store", action="store_true", help="WRITE the areas to box.tc_area (needs sql/57 applied + go-ahead)")
    ap.add_argument("--record", action="store_true", help="with --store: make this area set the version of record for its extent")
    a = ap.parse_args(argv)
    t0 = time.time()
    with get_connection() as conn:
        res = run(conn, a.wells, a.out, puds=not a.no_puds)
        if a.store:
            from box.tc_area_store import store_areas

            n = store_areas(conn, res, a.version, make_record=a.record)
            print(f"stored {n} areas as box.tc_area v{a.version} on extent_id {res['extent']['extent_id']}{' (version of record)' if a.record else ''}")
    s = res["summary"]
    print(f"WCA: {s['n_areas']} areas (CV min k = {s['pick']['k_min']}), {s['n_cells']:,} cells, 12-mo cohort n = {s['n_c12']:,}; "
          f"held-out R2 {s['cv_r2_pick']:.2f} (k=1 {s['cv_r2_k1']:.2f}, local kNN {s['knn_local_cv_r2']:.2f}); in-sample {s['r2_in']:.0%}")
    print(f"wrote {a.out}  ({time.time() - t0:.0f} s)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
