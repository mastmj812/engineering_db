"""BOX run 9 inputs from the step-15 TUNING runs (read-only): per step-15 group, at its record variant (raw box_v2 for all ten),
the D69 radius-class package range and the compass-side edge table the workup caveats quote.

    python -m scripts.box_run9_prep [--runs runs/box15t] [--out docs/box/run9-2026-10-18/inputs]

--runs = the `scripts.box_acceptance --bench <B> --fold analog` tuning outputs (runs/box15t/<B>/view_tuning_v2_<B>_analog_<year>.csv.gz,
the runs the step-15 tuning gate read). Writes spread_by_radius_<B>.csv (box.production9c.radius_ranges_from_views, as 9c did for
BS2_S / WCXY) and edge_regions_<B>.csv (box.tune15_report.side_classes + region_table, as the tuning page did - but at the CURRENT
record variant: BS3_S's tuning-page table was box_v2_wf; its record is raw box_v2 since the holdout gate).
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import numpy as np
import pandas as pd

from box import dev_factor_report as dfr
from box import production9c as p9
from box import production_run9 as p9r
from box import rehearse9b as r9
from box import tc_area_report as tar
from box import tune15_report as t15
from etl.db import get_connection


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--runs", type=Path, default=Path("runs") / "box15t")
    ap.add_argument("--out", type=Path, default=p9r.RUN9_INPUTS)
    a = ap.parse_args(argv)
    a.out.mkdir(parents=True, exist_ok=True)
    benches = list(p9r.GROUPS[3:])
    with get_connection() as conn:
        ext = {b: tar.pull_extent(conn, b) for b in benches}
        conn.rollback()
    for b in benches:
        d, tag, var = a.runs / b, f"tuning_v2_{b}_analog", p9.record_variant(b)
        views = {f.name: pd.read_csv(f, dtype={"api10": str, "package": str}) for f in sorted(d.glob(f"view_{tag}_*.csv.gz"))}
        if not views:
            raise SystemExit(f"{b}: no tuning views under {d}")
        rr = p9.radius_ranges_from_views(views, var)
        rr.to_csv(a.out / f"spread_by_radius_{b}.csv", index=False)
        v = r9.load_frames(d, tag)
        x, y = dfr._xy(v["mid_lon"], v["mid_lat"])
        vv = pd.concat([v.reset_index(drop=True), t15.side_classes(np.asarray(x), np.asarray(y), ext[b]["geom_ft"])], axis=1)
        vv["package"] = vv["cutoff"].astype(str) + ":" + vv["package"].astype(str)
        reg = t15.region_table(vv, var)
        reg.to_csv(a.out / f"edge_regions_{b}.csv", index=False)
        print(f"{b} ({var}, extent {ext[b]['extent_id']}, {len(views)} views): radius classes {len(rr)} rows; regions "
              f"{', '.join(f'{g} {x:+.1%}' for g, x in zip(reg['region'], reg['oil12 bias'], strict=True) if np.isfinite(x))}", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
