"""BOX step 7a (D59 condition 2): re-run the frozen D58 holdout scoring (`box_v2_wf`, code d5c3ebd) per cutoff and KEEP
the per-well / per-package frames the acceptance harness does not write, so the 2023-cutoff spread misses can be read.

    python -m scripts.box_spread_diag [--cutoffs 2023-12-01,2022-12-01,2024-12-01,2021-12-01] [--out runs/box7a] [--workers N]

Same code path as `scripts.box_acceptance --mode v2 --score-holdout` (box/acceptance.run), one cutoff at a time; the
walk-forward haircuts come from the TUNING cells (docs/box/acceptance/cells_tuning_v2.csv), exactly as D58 froze them.
Each cutoff's recomputed cells are checked against the scored record (cells_holdout_v2.csv) by identity before anything
is read from it. Read-only against the warehouse; writes only under --out (git-ignored runs/).
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import sys
import time
from pathlib import Path

import numpy as np
import pandas as pd

from box import acceptance as ac
from box import backtest_report as br
from box import edge_gap_report as egr
from box import exclusions
from box import spacing3d_report as s3r
from box import tc_curve_report as rep
from etl.db import get_connection

ACC = Path("docs") / "box" / "acceptance"
KEYS = ["cutoff", "stream", "horizon", "variant"]
VALS = ["n_packages", "n_wells", "pkg_bias", "pkg_band", "bench_bias", "bench_band"]


def check_identity(cells: pd.DataFrame, record: pd.DataFrame, cutoff: str) -> dict[str, float]:
    """Max abs difference per statistic between recomputed and scored cells for this cutoff; raises if counts differ."""
    a = cells[cells.cutoff == cutoff].set_index(KEYS)[VALS].sort_index()
    b = record[record.cutoff == cutoff].set_index(KEYS)[VALS].sort_index()
    a, b = a.loc[a.index.intersection(b.index)], b.loc[a.index.intersection(b.index)]
    if len(a) != len(record[record.cutoff == cutoff]) or not (a[["n_packages", "n_wells"]].fillna(-1) == b[["n_packages", "n_wells"]].fillna(-1)).all().all():
        raise SystemExit(f"{cutoff}: package / well counts differ from the scored record — not the frozen run")
    return {c: float(np.nanmax(np.abs(a[c].to_numpy(float) - b[c].to_numpy(float)))) if a[c].notna().any() else 0.0 for c in VALS[2:]}


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--wells", type=Path, default=Path("docs") / "box" / "step1-2026-10-06")
    ap.add_argument("--out", type=Path, default=Path("runs") / "box7a")
    ap.add_argument("--cutoffs", default="2023-12-01,2022-12-01,2024-12-01,2021-12-01")
    ap.add_argument("--workers", type=int, default=None)
    a = ap.parse_args(argv)
    a.out.mkdir(parents=True, exist_ok=True)
    record = pd.read_csv(ACC / "cells_holdout_v2.csv")
    history = pd.read_csv(ACC / "cells_tuning_v2.csv")
    history = history[history.variant.isin(ac.NON_WF_V2)]
    t0 = time.time()
    with get_connection() as conn:
        wells, _ = exclusions.drop(egr.load_final_sets(a.wells, ("WCA",)))
        last = rep.last_full_month(rep._read(conn, rep._MONTHS_SQL))
        subj = wells[np.array([f >= dt.date(2016, 1, 1) for f in wells["first_production_date"]])
                     & (pd.to_numeric(wells["lateral_length_ft"], errors="coerce") > 0).to_numpy()]
        P = s3r.build_pairs(conn, subj.reset_index(drop=True))
        print(f"actuals through {last}; pairs built ({time.time() - t0:.0f} s)", flush=True)
        for c in (dt.date.fromisoformat(x) for x in a.cutoffs.split(",")):
            f = br.run_fold(conn, wells, a.wells, c, a.workers, last, P, horizons=ac.HORIZONS, k_months=ac.K_MONTHS, keep_pred=True, return_internals=True)
            hs = f["hold"]
            hs["package"] = hs["api10"].map(ac.packages(list(hs["api10"]), P["pairs"]))
            held = set(hs.loc[hs["holdout_block"], "package"])
            hs["package_held_out"] = hs["package"].isin(held)
            view = hs[hs["package_held_out"]].copy().reset_index(drop=True)
            prov = ac.add_analog_predictions_v2(conn, view, f, c, a.workers)
            cells = pd.concat([ac.score_fold(view, str(c), ac.NON_WF_V2), *ac.apply_walk_forward(ac.score_fold(view, str(c), ac.NON_WF_V2), {str(c): view}, history)],
                              ignore_index=True)
            diff = check_identity(cells, record, str(c))
            tag = str(c)[:4]
            view.merge(prov, on="api10", how="left").to_csv(a.out / f"view_{tag}.csv.gz", index=False)
            cells.to_csv(a.out / f"cells_{tag}.csv", index=False)
            (a.out / f"meta_{tag}.json").write_text(json.dumps({"cutoff": str(c), "actuals_through": str(last), "identity_max_abs_diff": diff,
                                                                "walk_forward": [w for w in ac.WF_LOG]}, indent=2, default=str), encoding="utf-8")
            print(f"{c}: {len(view)} wells, {view['package'].nunique()} packages; identity max|diff| {diff} ({time.time() - t0:.0f} s)", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
