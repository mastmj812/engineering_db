"""BOX step 2 — edge-gap prototype pages for the Delaware pilot pools (read-only).

    python -m scripts.box_edge_gap [--wells docs/box/step1-2026-10-06] [--out docs/box/step2-YYYY-MM-DD] [--r-mi 0.5]

Reads the gate-1 final well sets, pulls lateral lines from curated.wells_enriched +
curated.enverus_lateral_lines through the ETL session pooler inside a READ ONLY transaction, tunes
the closing radius on WCA, and writes per pool an HTML review page + CSVs + GeoJSON, plus
index.html and summary.json. Nothing is written to the warehouse. See box/edge_gap.py.
"""

from __future__ import annotations

import argparse
import datetime as dt
import sys
import time
from pathlib import Path

from box.edge_gap_report import POOLS, run
from etl.db import get_connection


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--wells", type=Path, default=Path("docs") / "box" / "step1-2026-10-06")
    ap.add_argument("--out", type=Path, default=Path("docs") / "box" / f"step2-{dt.datetime.now(tz=dt.UTC).astimezone():%Y-%m-%d}")
    ap.add_argument("--pool", nargs="*", default=list(POOLS))
    ap.add_argument("--r-mi", type=float, default=0.5, help="pin radius r, miles (the sweep shows 0.25 / 0.5 / 0.75)")
    a = ap.parse_args(argv)
    t0 = time.time()
    with get_connection() as conn:
        res = run(conn, a.wells, a.out, tuple(a.pool), a.r_mi)
    p = res["params"]
    print(f"r = {p.pin_radius_ft:,.0f} ft, c = {p.close_ft:,.0f} ft (tuned on WCA)")
    for pool, s in res["summary"]["pools"].items():
        print(
            f"{pool:>6}: {s['n_evidence']:,} evidence laterals, main body {s['main_share']:.1%}; perimeter {s['perimeter_mi']:,.0f} mi, "
            f"{s['pinned_share']:.0%} pinned, gaps n={s['n_gaps']} median {s['gap_median_ft']:,.0f} ft p90 {s['gap_p90_ft']:,.0f} ft, "
            f"{s['mi_per_pinning_well']:.2f} mi/pinning well; step-outs {s['n_stepouts']}; pinning caveats {s['n_pinning_caveat']}"
        )
    print(f"wrote {a.out}  ({time.time() - t0:.0f} s)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
