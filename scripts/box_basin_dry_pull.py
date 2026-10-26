"""BOX step 19 — a read-only dry pull of every basin-parameterized module for one basin (default Midland).

    python -m scripts.box_basin_dry_pull [--basin midland] [--out docs/box/step19-2026-10-26/dry_pull_midland.json]

Proves the paths open for the basin: each module's warehouse pull runs with `basin` and returns rows, and each piece the basin
has not measured yet (step 20 / 21) refuses by name instead of borrowing the Delaware value. Counts only: no Midland output is
reviewed here (gate 19). READ ONLY: every query runs in a read-only transaction; nothing is written to the database.
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path
from typing import Any

import pandas as pd
from psycopg.errors import UndefinedColumn

from box import basin as bsn
from box import bench_qc as bq
from box import extent_package as pkg
from box import extent_report as er
from box import production as pr
from box import prox_study_report as psr
from box import refresh13 as r13
from box import tc_area_report as tar
from box.tc_curve_report import _read
from etl.db import get_connection


def _refuses(fn: Any) -> str:
    try:
        fn()
    except (ValueError, RuntimeError) as e:
        return f"refused: {e}"
    return "NOT refused"


def run(conn: Any, basin: str) -> dict[str, Any]:
    out: dict[str, Any] = {"basin": basin, "params": {k: v for k, v in vars(bsn.get(basin)).items()}}
    t = time.time()
    # bench QC (box/bench_qc, box/family_qc, scripts.box_pool_refresh)
    prod = bq.pull_producers(conn, basin)
    scored = bq.score_consensus(prod)
    tags = scored["formation_blueox"].value_counts()
    top = str(tags.index[0])
    s = bq.bench_summary(scored, top, basin)
    out["bench_qc"] = {"producing_hz": len(prod), "asof": str(prod.attrs.get("asof")), "by_tag_top10": {str(k): int(v) for k, v in tags.head(10).items()},
                       "consensus_status": {str(k): int(v) for k, v in scored["cons_status"].value_counts().items()},
                       f"bench_summary_{top}": {"n_prod_hz": s["n_prod_hz"], "n_cohort": s["n_cohort"], "border_step": s["border_step"]["verdict"]}}
    # production universe + PDP sticks (box/production, scripts.box_pud_run)
    u = pr.universe(conn, covered=(), basins=[basin])
    out["universe"] = {"rows": len(u), "by_coverage": {str(k): int(v) for k, v in u["coverage"].value_counts().items()},
                       "by_bench": {str(k): int(v) for k, v in u["bench"].value_counts().items()}}
    pdp = pr.pdp_sticks(conn, [top], basin)
    out["pdp_sticks"] = {top: len(pdp)}
    # extents (box/extent_report, box/family_extent, box/extent_package, scripts.box_pool_refresh)
    lo, la = prod["mid_lon"].dropna(), prod["mid_lat"].dropna()
    bounds = (float(lo.min()), float(la.min()), float(lo.max()), float(la.max()))
    puds = er.pull_puds(conn, [top], bounds, basin)
    out["extents"] = {"pull_puds": {top: len(puds), "by_status": {str(k): int(v) for k, v in puds["status"].value_counts(dropna=False).items()}},
                      "edge_params": _refuses(lambda: er.edge_params(basin)),
                      "extent_of_record": _refuses(lambda: tar.pull_extent(conn, top, basin)),
                      "grid_root": None if pkg.grid_root(basin) is None else str(pkg.grid_root(basin))}
    # proximity (box/prox_study_report, box/prox_pud_report)
    pu = psr.pull_universe(conn, basin)
    kids = psr.children_of(pu, basin)
    out["proximity"] = {"producers_in_bbox": len(pu), "by_basin": {str(k): int(v) for k, v in pu["basin"].value_counts(dropna=False).items()},
                        "children": len(kids)}
    # refresh driver (box/refresh13, scripts.box_refresh)
    ex = _read(conn, r13.EXTENT_SQL, {"basin": basin, "bench": top, "forms": [top], "x_m": r13.EXTENT_X_MI * r13.MI_M})
    try:
        st = _read(conn, r13.STATE_SQL, {"basin": basin})
        rec: Any = st[0][0] if st else None
    except UndefinedColumn:  # box.forecast_run.basin arrives with sql/70 (D130)
        conn.rollback()
        rec = "box.forecast_run.basin missing: sql/70 not applied on this database"
    out["refresh"] = {"record_run": rec, "extent_trigger": int(ex[0][0]), "groups": _refuses(lambda: r13.groups_for(basin))}
    # water (box/water11 inputs) + the hindcast Novi report (box/hindcast_production)
    ids = sorted(prod.loc[prod["formation_blueox"] == top, "api10"].astype(str))[:500]
    wq = pd.DataFrame(_read(conn, "SELECT water_source, count(*) FROM curated.water_data_quality WHERE api10 = ANY(%(a)s) GROUP BY 1", {"a": ids}))
    out["water"] = {"sample_wells": len(ids), "water_source": {str(r[0]): int(r[1]) for r in wq.itertuples(index=False)}}
    rn = bsn.novi_report(basin, "2025Q3")
    n = _read(conn, "SELECT count(*) FROM (SELECT 1 FROM raw_intel.production_forecast WHERE report_name = %(r)s LIMIT 1000) x", {"r": rn})
    out["hindcast"] = {"novi_report": rn, "forecast_rows_seen": int(n[0][0])}
    out["seconds"] = round(time.time() - t, 1)
    return out


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--basin", default=bsn.MIDLAND)
    ap.add_argument("--out", type=Path, default=None)
    a = ap.parse_args(argv)
    with get_connection() as conn:
        res = run(conn, a.basin)
    txt = json.dumps(res, indent=1, default=str)
    print(txt)
    if a.out:
        a.out.parent.mkdir(parents=True, exist_ok=True)
        a.out.write_text(txt + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    sys.exit(main())
