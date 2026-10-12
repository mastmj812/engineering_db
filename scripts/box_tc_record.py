"""BOX step 5d — build the type-curve + risk-factor record and its review page; optionally store it.

    python -m scripts.box_tc_record [--wells docs/box/step1-2026-10-06] [--out docs/box/step5d-YYYY-MM-DD] [--boot N]
                                    [--drift-check] [--store [--record] [--version N]]

DB-free by default: the record is rebuilt from the committed 5b / 5c deliverables (box/tc_record_report.py)
and checked by identity against them. --drift-check additionally reads curated.dev_scenario (read-only,
a few minutes) to report whether the live sql/50 classes still match the 5c frame.

--store writes box.type_curve, box.tc_member and box.risk_factor (sql/58). That is a warehouse WRITE: it
needs sql/58 applied (scripts.apply_box_type_curve, explicit go-apply) and Michael's explicit go-ahead.
--record makes the stored rows the version of record.
"""

from __future__ import annotations

import argparse
import datetime as dt
import sys
import time
from pathlib import Path

from box import dev_factor_report as dfr
from box import tc_record_report as trr
from scripts.box_tc_curves import boxfit_sha


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--wells", type=Path, default=Path("docs") / "box" / "step1-2026-10-06")
    ap.add_argument("--out", type=Path, default=Path("docs") / "box" / f"step5d-{dt.datetime.now(tz=dt.UTC).astimezone():%Y-%m-%d}")
    ap.add_argument("--boot", type=int, default=dfr.N_BOOT)
    ap.add_argument("--drift-check", action="store_true", help="read-only: compare live curated.dev_scenario with the 5c frame")
    ap.add_argument("--store", action="store_true", help="WRITE the record to box.type_curve / tc_member / risk_factor (needs sql/58 applied + go-ahead)")
    ap.add_argument("--record", action="store_true", help="with --store: make the stored rows the version of record")
    ap.add_argument("--version", type=int, default=1)
    a = ap.parse_args(argv)
    t0 = time.time()
    drift = None
    if a.drift_check or a.store:
        from etl.db import get_connection

        conn = get_connection()
    try:
        if a.drift_check:
            conn.read_only = True
            drift = trr.drift_check(conn, trr.load_frame(a.wells))
            conn.rollback()
            conn.read_only = False
        res = trr.run(a.wells, a.out, boxfit_sha(), a.boot, drift)
        if a.store:
            from box.tc_record_store import store_record

            n = store_record(conn, res, a.version, make_record=a.record)
            print(f"stored v{a.version}: {n['type_curve']} type curves, {n['tc_member']} members, {n['risk_factor']} risk factors{' (version of record)' if a.record else ''}")
    finally:
        if a.drift_check or a.store:
            conn.close()
    s = res["summary"]
    sys.stdout.reconfigure(errors="replace")  # check labels carry Greek letters; a cp1252 console must not abort the report
    for c in s["checks"]:
        print(f"  {'ok  ' if c['pass'] else 'FAIL'} {c['check']}: {c['result']}")
    print("infill factor of record:", ", ".join(f"{k} {v:.3f}" for k, v in s["infill_record"].items()))
    print("ref_mult:", ", ".join(f"{k} median {v['median']:.3f} ({v['min']:.3f}-{v['max']:.3f})" for k, v in s["ref_mult"].items()))
    print(f"wrote {a.out}  ({time.time() - t0:.0f} s)")
    return 0 if all(c["pass"] for c in s["checks"]) else 1


if __name__ == "__main__":
    sys.exit(main())
