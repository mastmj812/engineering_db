"""BOX acceptance of record (D53): package-level rolling-origin folds vs a local-offsets benchmark; D52 holdout excluded.

    python -m scripts.box_acceptance [--wells docs/box/step1-2026-10-06] [--out docs/box/acceptance] [--workers N]
                                     [--cutoffs 2019-12-01,...,2024-12-01] [--score-holdout]
                                     [--bench WCA|BS2_S|WCXY|WCXY_on_WCA] [--fold full|analog] [--actuals-through YYYY-MM-01]
                                     [--history cells_tuning_v2.csv] [--wca-history cells_tuning_v2.csv] [--tag NAME]

--score-holdout is the ONE-TIME final scoring of the frozen D52 holdout, after the model spec and code SHA are frozen. For a
bench other than WCA it also needs --holdout-once (step 9b; plan Phase 2) — step 9a scores tuning blocks only. Re-running
WCA's holdout is the step-9a regression guard (an identity check against the scored record, not a new score).
--bench / --fold: box/acceptance.BENCH_SPECS; fold 'full' = the step-6 fold (WCA only), 'analog' = the analog-only fold.
--actuals-through caps the live last full month (reproduce a scored record on later data).
Read-only against the warehouse. See box/acceptance.py.
"""

from __future__ import annotations

import argparse
import datetime as dt
import sys
import time
from pathlib import Path

from box import acceptance as ac
from etl.db import get_connection
from scripts.box_tc_curves import boxfit_sha


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--wells", type=Path, default=Path("docs") / "box" / "step1-2026-10-06")
    ap.add_argument("--out", type=Path, default=Path("docs") / "box" / "acceptance")
    ap.add_argument("--workers", type=int, default=None)
    ap.add_argument("--cutoffs", default=",".join(str(c) for c in ac.CUTOFFS))
    ap.add_argument("--score-holdout", action="store_true", help="ONE-TIME final scoring of the frozen D52 holdout")
    ap.add_argument("--holdout-once", action="store_true", help="required with --score-holdout for a bench other than WCA (step 9b)")
    ap.add_argument("--mode", choices=("v1", "v2"), default="v2", help="v1 = the 2026-10-13 five-variant run; v2 = the D57 run")
    ap.add_argument("--bench", choices=tuple(ac.BENCH_SPECS), default="WCA")
    ap.add_argument("--fold", choices=("full", "analog"), default="full")
    ap.add_argument("--actuals-through", type=dt.date.fromisoformat, default=None)
    ap.add_argument("--history", type=Path, default=None, help="tuning cells the holdout's walk-forward haircuts come from")
    ap.add_argument("--wca-history", type=Path, default=None, help="WCA tuning cells -> extra <base>_wf_wca variants (non-WCA benches)")
    ap.add_argument("--tag", default=None)
    a = ap.parse_args(argv)
    if a.score_holdout and a.bench != "WCA" and not a.holdout_once:
        ap.error(f"--score-holdout on {a.bench} is the one-time D52 score (step 9b): pass --holdout-once deliberately")
    t0 = time.time()
    with get_connection() as conn:
        res = ac.run(conn, a.wells, a.out, boxfit_sha(), a.workers, tuple(dt.date.fromisoformat(c) for c in a.cutoffs.split(",")), a.score_holdout, a.mode,
                     bench=a.bench, fold=a.fold, actuals_through=a.actuals_through, history_path=a.history, wca_history_path=a.wca_history, tag=a.tag)
    c = res["cells"]
    rec = c[c.variant == res["summary"]["record_variant"]][["stream", "horizon", "cutoff", "n_packages", "pkg_bias", "pkg_band", "bench_bias", "bench_band", "verdict"]]
    print(rec.round(3).to_string())
    print(res["summary"]["verdict"])
    print(f"wrote {a.out}  ({time.time() - t0:.0f} s)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
