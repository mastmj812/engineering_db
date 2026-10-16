"""BOX step 9a page: regression guard + BS2_S / WCXY tuning cells + haircuts + D92 realised + south edge + WCXY extent.

    python -m scripts.box_tune9a [--runs runs/box9a] [--out docs/box/step9a-2026-10-16]

Reads the `scripts.box_acceptance --fold analog` outputs under --runs (guard/, bs2s/, wcxy/, wcxy_on_wca/), the scored WCA
record (docs/box/acceptance), and a few read-only warehouse objects (extents of record, record forecast run's haircut, the
WCXY PUD rows of the record run). Writes index.html + the small CSV / JSON tables to --out. Nothing is stored.
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import subprocess
import sys
from pathlib import Path

import numpy as np
import pandas as pd
from scipy.spatial import cKDTree

from box import acceptance as ac
from box import dev_factor_report as dfr
from box import edge_gap as eg
from box import tc_area_report as tar
from box import tc_curve_report as rep
from box import tune9a_report as t9
from etl.db import get_connection

ACC = Path("docs") / "box" / "acceptance"
BENCHES = (("bs2s", "tuning_BS2_S", "BS2_S — gate-1 set + D84 refresh, extent 7"),
           ("wcxy", "tuning_WCXY", "WCXY targets — WCXY analogs only (D20), WCA extent as the frame"),
           ("wcxy_on_wca", "tuning_WCXY_on_WCA", "SENSITIVITY — WCXY targets on the whole WCA analog pool (contradicts D20 as written)"))

_RUN_SQL = "SELECT run_id, haircut FROM box.forecast_run WHERE is_record"
_WCXY_PUD_SQL = """
SELECT f.location_id, f.coverage, f.inside_extent, extensions.ST_X(extensions.ST_Centroid(l.geom)), extensions.ST_Y(extensions.ST_Centroid(l.geom))
FROM box.pud_forecast f JOIN box.location l USING (location_id)
WHERE f.run_id = %(r)s AND f.formation_blueox = 'WCXY'
"""


def _sha() -> str:
    return subprocess.run(["git", "rev-parse", "HEAD"], capture_output=True, text=True, check=True).stdout.strip()


def _views(d: Path, tag: str) -> pd.DataFrame:
    fs = sorted(d.glob(f"view_{tag}_*.csv.gz"))
    return pd.concat([pd.read_csv(f, dtype={"api10": str}) for f in fs], ignore_index=True)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--runs", type=Path, default=Path("runs") / "box9a")
    ap.add_argument("--out", type=Path, default=Path("docs") / "box" / "step9a-2026-10-16")
    a = ap.parse_args(argv)
    a.out.mkdir(parents=True, exist_ok=True)
    # ---- 0 guard
    g_t = t9.identity(pd.read_csv(a.runs / "guard" / "cells_guard_tuning.csv"), pd.read_csv(ACC / "cells_tuning_v2.csv"))
    g_h = t9.identity(pd.read_csv(a.runs / "guard" / "cells_guard_holdout.csv"), pd.read_csv(ACC / "cells_holdout_v2.csv"))
    ok = t9.guard_verdict(g_t) and t9.guard_verdict(g_h)
    worst = max(float(np.nanmax(g[[f"max_abs_{s}" for s in t9.STATS]].to_numpy())) for g in (g_t, g_h))
    guard = {"pass": ok, "tables": {"Tuning view vs docs/box/acceptance/cells_tuning_v2.csv": g_t, "Holdout (identity re-run) vs cells_holdout_v2.csv": g_h},
             "text": (f"WCA through fold='analog' (the code path BS2_S / WCXY use) reproduces the scored record for di_p50, box_v2 and their walk-forward forms at every "
                      f"cutoff: counts and verdicts equal, worst |difference| of any package statistic {worst:.1e} (float summation order; the 7a re-run read ≤ 1.1e-16). "
                      "The frozen spec does not move." if ok else f"MISMATCH — worst |difference| {worst:.1e}; see the tables. The bench parameter is NOT cleared.")}
    t9.dump({"tuning": g_t.to_dict("records"), "holdout": g_h.to_dict("records"), "pass": ok}, a.out / "guard.json")
    # ---- warehouse (read-only)
    with get_connection() as conn:
        ext = {b: tar.pull_extent(conn, b) for b in ("WCA", "BS2_S")}
        (rid, hcut), = rep._read(conn, _RUN_SQL)
        pud = pd.DataFrame(rep._read(conn, _WCXY_PUD_SQL, {"r": rid}), columns=["location_id", "coverage", "inside_extent", "lon", "lat"])
    # ---- 1 benches
    benches, d62_rows, d92_rows, wf_rows = [], [], [], []
    wca_cells = pd.concat([pd.read_csv(ACC / "cells_tuning_v2.csv"), pd.read_csv(ACC / "cells_holdout_v2.csv")], ignore_index=True)
    for label, cells in (("WCA record (tuning + holdout, = D62 of record)", wca_cells), ("WCA tuning only", pd.read_csv(ACC / "cells_tuning_v2.csv"))):
        t = t9.haircut_table(cells)
        d62_rows.append({"bench": label, **{f"{r.stream} cum-{r.horizon}": r.factor for r in t.itertuples()}})
    for s in ac.STREAMS:
        d92_rows.append({"bench": f"WCA run {rid} (stored, PUDs)", "stream": s,
                         **{f"cum-{k}": f"{v['realised_median']:.3f}" if isinstance(v, dict) and "realised_median" in v else "" for k, v in hcut[s].items() if str(k).isdigit()}})
    views = {}
    for i, (d, tag, title) in enumerate(BENCHES, start=1):
        cells = pd.read_csv(a.runs / d / f"cells_{tag}.csv")
        summ = json.loads((a.runs / d / f"summary_{tag}.json").read_text(encoding="utf-8"))
        shown = [v for v in ("di_p50", "box_v2", "di_p50_wf", "box_v2_wf", f"box_v2{ac.WCA_WF}") if v in set(cells.variant)]
        benches.append({"n": i, "title": title, "summary": summ, "cells": t9.record_cells(cells, shown)})
        cells.to_csv(a.out / f"cells_{tag}.csv", index=False)
        tab = t9.haircut_table(cells)
        tab.to_csv(a.out / f"d62_{tag}.csv", index=False)
        d62_rows.append({"bench": f"{title.split(' —')[0]} tuning only", **{f"{r.stream} cum-{r.horizon}": r.factor for r in tab.itertuples()}})
        for w in summ["walk_forward"]:
            if w["variant"] == "box_v2":
                wf_rows.append({"bench": tag.removeprefix("tuning_"), "haircut from": "own", "stream": w["stream"], "cutoff": w["cutoff"][:4], "horizon": w["horizon"], "h": w["haircut"]})
        for w in summ.get("walk_forward_wca", []):
            if w["variant"] == "box_v2":
                wf_rows.append({"bench": tag.removeprefix("tuning_"), "haircut from": "WCA", "stream": w["stream"], "cutoff": w["cutoff"][:4], "horizon": w["horizon"], "h": w["haircut"]})
        months = t9.load_months(a.runs / d / f"months_{tag}.npz")
        for s in ac.STREAMS:
            m = np.concatenate([months[y][s] for y in months])
            r = t9.realised_d92(m, tab, s)
            row = {"bench": title.split(" —")[0], "stream": s, "locations": r.get("n", 0)}
            for k, q in (r.get("realised") or {}).items():
                row[f"cum-{k}"] = f"{q['p50']:.3f} [{q['p90']:.3f}–{q['p10']:.3f}] (target {r['target'][k]:.3f})" if q else ""
            for k_ in ("g_month1", "g_month48"):
                q = r.get(k_)
                row[k_] = f"{q['p50']:.3f} [{q['p90']:.3f}–{q['p10']:.3f}]" if q else ""
            d92_rows.append(row)
        views[d] = _views(a.runs / d, tag)
    wf = pd.DataFrame(wf_rows)
    wf_log = wf.assign(col=lambda x: "cum-" + x.horizon.astype(str)).pivot_table(index=["bench", "haircut from", "stream", "cutoff"], columns="col", values="h").reset_index() if len(wf) else pd.DataFrame()
    # ---- 3 BS2_S south edge
    v = views["bs2s"].copy()
    x, y = dfr._xy(v["mid_lon"], v["mid_lat"])
    v["x"], v["y"] = x, y
    v = pd.concat([v, t9.edge_classes(np.asarray(x), np.asarray(y), ext["BS2_S"]["geom_ft"])], axis=1)
    v["package"] = v["cutoff"].astype(str) + ":" + v["package"].astype(str)
    edge = {"png": t9.edge_map_png(v, ext["BS2_S"]["geom_ft"], "BS2_S scored tuning locations (all cutoffs) — ▲ = strike-ellipse search, tick = strike axis"),
            "regions": t9.region_table(v), "modes": t9.mode_table(v)}
    edge["regions"].to_csv(a.out / "bs2s_edge_regions.csv", index=False)
    v[["cutoff", "api10", "mid_lon", "mid_lat", "region", "edge_dist_mi", "edge_az_deg", "v2_mode", "v2_radius_mi", "v2_n", "v2_strike_az_deg", "v2_strike_r2",
       "v2_strike_n", "v2_strike_dip_ft_mi"]].to_csv(a.out / "bs2s_edge_locations.csv", index=False)
    # ---- 4 WCXY extent
    wells, _, _ = ac.bench_wells(Path("docs") / "box" / "pool-2026-10-15", "WCXY")
    mod = wells[(pd.to_datetime(wells["first_production_date"]) >= "2016-01-01") & (pd.to_numeric(wells["lateral_length_ft"], errors="coerce") > 0)]
    allw, _, _ = ac.bench_wells(Path("docs") / "box" / "pool-2026-10-15", "WCA")
    a1 = allw[(allw.formation_blueox.isin(["WCA_1", "WCA_2"])) & (pd.to_datetime(allw["first_production_date"]) >= "2016-01-01")]
    pxy = np.column_stack(dfr._xy(mod["mid_lon"], mod["mid_lat"]))
    axy = np.column_stack(dfr._xy(a1["mid_lon"], a1["mid_lat"]))
    import shapely

    g6 = ext["WCA"]["geom_ft"]
    p_in = shapely.contains_xy(g6, pxy[:, 0], pxy[:, 1])
    pud["x"], pud["y"] = dfr._xy(pud["lon"], pud["lat"])
    pud["inside"] = pud["inside_extent"].fillna(False).astype(bool)
    pud["d_wcxy_mi"] = cKDTree(pxy).query(pud[["x", "y"]].to_numpy())[0] / eg.FT_PER_MI
    pud["d_wca12_mi"] = cKDTree(axy).query(pud[["x", "y"]].to_numpy())[0] / eg.FT_PER_MI
    rows = [{"item": "WCXY producers, first prod ≥ 2016 (gate-1 WCA set, WCXY tag, D84 refresh)", "inside WCA extent": int(p_in.sum()), "outside": int((~p_in).sum())},
            {"item": f"WCXY reconciled PUDs (record run {rid}, all not_covered_wcxy)", "inside WCA extent": int(pud.inside.sum()), "outside": int((~pud.inside).sum())}]
    for lim in (2.0, 5.0, 10.0):
        rows.append({"item": f"PUDs inside with a WCXY producer within {lim:.0f} mi", "inside WCA extent": int((pud.inside & (pud.d_wcxy_mi <= lim)).sum()),
                     "outside": int((~pud.inside & (pud.d_wcxy_mi <= lim)).sum())})
    rows.append({"item": "PUDs inside: median distance to nearest WCXY producer (mi) / to nearest WCA_1-2 producer",
                 "inside WCA extent": f"{pud.loc[pud.inside, 'd_wcxy_mi'].median():.1f} / {pud.loc[pud.inside, 'd_wca12_mi'].median():.1f}",
                 "outside": f"{pud.loc[~pud.inside, 'd_wcxy_mi'].median():.1f} / {pud.loc[~pud.inside, 'd_wca12_mi'].median():.1f}"})
    wtab = pd.DataFrame(rows)
    wtab.to_csv(a.out / "wcxy_extent.csv", index=False)
    wcxy = {"png": t9.wcxy_map_png(g6, pxy, pud), "table": wtab,
            "note": "Distances are lateral-midpoint (producers) to PUD-stick centroid, UTM 13N. No WCXY extent exists; a step-3-method WCXY extent (D27 envelope) "
                    "would be built from the WCXY producers alone (D20) — not built here."}
    # ---- page
    decisions = (a.out / "decisions.html").read_text(encoding="utf-8") if (a.out / "decisions.html").exists() else "<div class=meta>(see FINDINGS.md §5)</div>"
    s0 = benches[0]["summary"]
    meta = {"built_at": dt.datetime.now(tz=dt.UTC).astimezone().isoformat(timespec="seconds"), "code_sha": _sha(), "engine_sha": s0["engine_sha"], "actuals_through": s0["actuals_through"]}
    ctx = {"meta": meta, "guard": guard, "benches": benches, "wf_log": wf_log, "d62": pd.DataFrame(d62_rows), "d92": pd.DataFrame(d92_rows), "edge": edge, "wcxy": wcxy,
           "decisions_html": decisions}
    wf_log.to_csv(a.out / "walk_forward.csv", index=False)
    pd.DataFrame(d62_rows).to_csv(a.out / "d62_by_bench.csv", index=False)
    pd.DataFrame(d92_rows).to_csv(a.out / "d92_realised.csv", index=False)
    (a.out / "index.html").write_text(t9.render(ctx), encoding="utf-8")
    t9.dump({"meta": meta, "guard_pass": ok, "guard_worst": worst, "benches": {b["title"]: b["summary"]["verdict"] for b in benches}}, a.out / "summary.json")
    print(f"guard {'PASS' if ok else 'FAIL'} (worst {worst:.1e}); wrote {a.out / 'index.html'}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
