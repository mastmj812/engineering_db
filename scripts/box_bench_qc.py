"""BOX step 1 — bench QC pages for the Delaware pilot benches (read-only).

    python -m scripts.box_bench_qc [--out docs/box/step1-YYYY-MM-DD] [--bench WCA_1 ...]

Reads curated.wells_enriched + curated.formation_blueox_tvd through the ETL
session pooler inside a READ ONLY transaction and writes, per bench, an HTML
review page + per-well CSV, plus index.html and summary.json. Nothing is
written to the warehouse. See box/bench_qc.py for the measures.
"""

from __future__ import annotations

import argparse
import datetime as dt
import sys
import time
from pathlib import Path

from box.bench_qc import PILOT_BENCHES, run
from etl.db import get_connection


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--out", type=Path, default=Path("docs") / "box" / f"step1-{dt.datetime.now(tz=dt.UTC).astimezone():%Y-%m-%d}")
    ap.add_argument("--bench", nargs="*", default=list(PILOT_BENCHES))
    a = ap.parse_args(argv)
    t0 = time.time()
    with get_connection() as conn:
        res = run(conn, a.out, tuple(a.bench))
    m = res["meta"]
    print(f"as-of {m['asof']} | Delaware producing horizontals {m['n_delaware_prod_hz']:,} | clean witnesses {m['n_witness']:,}")
    for s in res["benches"]:
        bs = s["border_step"]
        print(
            f"{s['bench']:>6}: n={s['n_prod_hz']:,} (TX {s['n_tx']:,} / NM {s['n_nm']:,}) cohort={s['n_cohort']:,} "
            f"planned={100 * s['planned_share']:.1f}% (NM {100 * s['planned_share_nm']:.1f}%) round-TVD={100 * s['round_tvd_share']:.1f}% "
            f"sql23-disagree={100 * s['sql23_disagree_share']:.1f}% cons-flags={s['cons_flag_n']} ({100 * s['cons_flag_share']:.1f}%) "
            f"lith-ambig={s['cons_lith_n']} med-oil12={s['cohort_med_oil12_kft']:.0f} bbl/kft border={bs['verdict']}"
        )
    print(f"wrote {a.out / 'index.html'}  ({time.time() - t0:.0f} s)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
