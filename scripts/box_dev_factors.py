"""BOX step 5c — development-scenario factors, pooled per bench across the basin; review page (read-only).

    python -m scripts.box_dev_factors [--wells docs/box/step1-2026-10-06] [--out docs/box/step5c-YYYY-MM-DD] [--workers N] [--boot N]

WCA factors come from the step-5b record (strict cohort + per-well fits); BS2_S is fitted here with the
same pinned engine as the second bench for the per-bench vs per-basin question. Scenario = curated
.dev_scenario (sql/50), recomputed from bench_context for the parent bench and checked by identity.
Reads the warehouse through the ETL session pooler inside READ ONLY transactions; writes nothing to it
(box.risk_factor DDL is step 5d). See box/dev_factor.py (method) and box/dev_factor_report.py.
"""

from __future__ import annotations

import argparse
import datetime as dt
import sys
import time
from pathlib import Path

from box.dev_factor_report import N_BOOT, run
from etl.db import get_connection
from scripts.box_tc_curves import boxfit_sha


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--wells", type=Path, default=Path("docs") / "box" / "step1-2026-10-06")
    ap.add_argument("--out", type=Path, default=Path("docs") / "box" / f"step5c-{dt.datetime.now(tz=dt.UTC).astimezone():%Y-%m-%d}")
    ap.add_argument("--workers", type=int, default=None)
    ap.add_argument("--boot", type=int, default=N_BOOT)
    a = ap.parse_args(argv)
    t0 = time.time()
    with get_connection() as conn:
        res = run(conn, a.wells, a.out, boxfit_sha(), a.workers, a.boot)
    s = res["summary"]
    for b, v in s["benches"].items():
        print(f"{b}: {v['n_cohort']:,} cohort wells, {v['n_est']:,} identify factors; classes {v['class_mix']}; same-bench parent {v['infill_share']:.0%}")
    print(f"area normalisation (EUR) median x{s['norm_mult_eur']['median']:.3f} ({s['norm_mult_eur']['min']:.3f}-{s['norm_mult_eur']['max']:.3f})")
    print(f"wrote {a.out}  ({time.time() - t0:.0f} s)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
