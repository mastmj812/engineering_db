"""BOX step 3 — build the buffered extents, calibrate, and write the geology package (read-only).

    python -m scripts.box_extents_export [--wells docs/box/step1-2026-10-06] [--out docs/box/step3-YYYY-MM-DD]
                                        [--version 1] [--no-puds] [--store [--record]]

Reads the gate-1 final well sets, pulls lateral lines (and, for the review page, the D1 PUD
universe) through the ETL session pooler inside READ ONLY transactions, runs the k/cap/floor
backtest on WCA + BS2_S together, builds the extents, and writes review pages + CSVs + GeoJSON +
the geology shapefile package (NAD83 UTM 14N US-ft). See box/extent.py for the rule.

--store additionally writes the generated extents to box.extent / box.extent_edge (sql/54). That is
a warehouse WRITE: it needs the box schema applied (scripts.apply_box_schema, explicit go-apply)
and Michael's explicit go-ahead. --record also makes the stored generated version the version of
record (plan D28: generated extents are adopted without waiting for geology).
"""

from __future__ import annotations

import argparse
import datetime as dt
import sys
import time
from pathlib import Path

from box.extent_report import run
from etl.db import get_connection


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--wells", type=Path, default=Path("docs") / "box" / "step1-2026-10-06")
    ap.add_argument("--out", type=Path, default=Path("docs") / "box" / f"step3-{dt.datetime.now(tz=dt.UTC).astimezone():%Y-%m-%d}")
    ap.add_argument("--version", type=int, default=1)
    ap.add_argument("--no-puds", action="store_true", help="skip the read-only D1 PUD universe count")
    ap.add_argument("--store", action="store_true", help="WRITE the generated extents to box.extent (needs sql/54 applied + go-ahead)")
    ap.add_argument("--record", action="store_true", help="with --store: make the generated version the version of record (D28)")
    a = ap.parse_args(argv)
    t0 = time.time()
    with get_connection() as conn:
        res = run(conn, a.wells, a.out, a.version, puds=not a.no_puds)
        if a.store:
            from box.extent_store import store_generated

            for pool, b in res["builds"].items():
                eid = store_generated(conn, pool, a.version, b, res["bp"], res["summary"]["built_at"], make_record=a.record)
                print(f"stored {pool} v{a.version} generated as extent_id {eid}{' (version of record)' if a.record else ''}")
    bp = res["bp"]
    print(f"chosen: k = {bp.k:g}, cap = {bp.cap_ft:,.0f} ft, floor = {bp.floor_ft:,.0f} ft, ref = {bp.perf_ref}")
    for pool, s in res["summary"]["pools"].items():
        print(f"{pool:>6}: extent {s['extent_sqmi']:,.0f} sq mi (core {s['core_sqmi']:,.0f}), {s['n_parts']} parts, {s['n_holes']} holes, fronts {list(s['fronts']) or 'none'}")
    print(f"wrote {a.out}  ({time.time() - t0:.0f} s)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
