"""BOX step 21c — Midland water on the ONE-TIME holdout (PREREGISTRATION §7: D107 ratio on raw mid_r2 oil, D108; D109 holdout cell).

Called by `python -m scripts.box_step21c water`. scripts/box_step21b_water.run_group (the 21b tuning frames) with two differences
and nothing else, the step-12a `side='holdout'` pattern of scripts/box_water11.run_tune:
  * the targets are the HOLDOUT views of the 21c harness runs (view_holdout_v2_<group>_analog_<yyyy>.csv.gz + their observed
    months_mid_r2.npz), and every row must carry package_held_out (the tuning check inverted);
  * the frame is written as <run>/<group>/water_holdout.csv.gz.
Selection, measured labels (as of each cutoff for the pool, as of 2026-08-01 for the target), the measured-pool benchmark, the
F_oil(k) recovered from the harness view and the ratio water are box_step21b_water's own helpers, unchanged. Read-only.
"""

from __future__ import annotations

import datetime as dt
import time
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from box import analog as an
from box import backtest_report as br
from box import tc_curve_report as rep
from box import water11 as w
from box.dev_factor_report import _xy
from scripts import box_step21b_water as bw21
from scripts import box_water11 as bw

BASIN, LAST = bw21.BASIN, bw21.LAST


def run_group(conn: Any, run: Path, group: str, vdr: pd.DataFrame, workers: int | None) -> pd.DataFrame:
    t0 = time.time()
    d = run / group
    z = np.load(d / "months_mid_r2.npz")
    wells = bw21.group_frame(conn, group)
    views = {int(p.name.split("_")[-1][:4]): p for p in sorted(d.glob(f"view_holdout_v2_{group}_analog_20*.csv.gz"))}
    tgt_all = pd.concat([pd.read_csv(p, dtype={"api10": str, "package": str, "state_code": str}) for p in views.values()], ignore_index=True)
    if not tgt_all["package_held_out"].astype(bool).all():
        raise RuntimeError(f"{group}: a holdout view carries a tuning package")
    ids_all = sorted(set(wells["api10"]) | set(tgt_all["api10"]))
    cls = bw21._rows(conn, bw._CLS_SQL, ids_all, ["api10", "prod_date", "oil", "water", "prop"])
    prod = rep.pull_production(conn, ids_all, LAST)
    meta = rep.pull_meta(conn, ids_all)
    ut = an.uturn_leg_spacing(conn, sorted(set(tgt_all["api10"])))
    tw = tgt_all.drop_duplicates("api10")[["api10", "state_code"]].copy()
    tw["state_code"] = tw["state_code"].astype(str).str.replace(".0", "", regex=False)
    t_lab = w.labels_asof(tw, cls, LAST, w.vdr_months_asof(vdr, LAST))
    rows = []
    for y, path in views.items():
        cutoff = dt.date(y, 12, 1)
        asof = br._prev_month(cutoff)
        v = pd.read_csv(path, dtype={"api10": str, "package": str})
        if f"{y}_api10" not in z.files or not len(v):
            continue
        if list(z[f"{y}_api10"].astype(str)) != list(v["api10"]):
            raise RuntimeError(f"{group} {y}: observed months / view order differ")
        oil_m = z[f"{y}_oil"]
        F = bw21.f_array(v, oil_m)
        labels = w.labels_asof(wells, cls, asof, w.vdr_months_asof(vdr, asof))
        pm, pa, pf = bw.pool_asof(wells, labels, asof, cutoff)
        v["label"] = v["api10"].map(t_lab).fillna("insufficient")
        v["row"] = np.arange(len(v))
        v = v[v["label"] == "measured"].reset_index(drop=True)
        if v.empty:
            continue
        vx, vy = _xy(v["mid_lon"], v["mid_lat"])
        v["x"], v["y"] = vx, vy
        v["lat_c"] = [an.completed_lateral(a, float(L), ut) for a, L in zip(v["api10"], v["lateral_ft"], strict=True)]
        locs = [{"api10": r.api10, "x": vx[i], "y": vy[i], "lateral_ft": float(r.lat_c), "spacing_ft": r.spacing_ft,
                 "fp_max": pd.Timestamp(r.first_production_date).date()} for i, r in enumerate(v.itertuples())]
        sel = w.select_many(locs, pm, pa, w.ac_label(group), workers, basin=BASIN)
        need = sorted({a for s in sel for a in s["api10s"]})
        pr = prod[prod["api10"].isin(set(need)) & (prod["prod_date"] <= asof)]
        fits = rep.fit_wells(pr, meta[meta["api10"].isin(set(need))], workers)
        cur = bw.cohort_curves([(s["loc"], s["api10s"]) for s in sel], pf, fits, workers, basin=BASIN)
        act_w = w.stream_matrix(prod, list(v["api10"]), "water_bbl", drop_latest=True)
        act_o = w.stream_matrix(prod, list(v["api10"]), "oil_bbl", drop_latest=True)
        bench = bw.measured_benchmark(pf[pf["label"] == "measured"], prod, asof, v)
        for i, (r, s) in enumerate(zip(v.itertuples(), sel, strict=True)):
            c = cur[r.api10]
            oil = oil_m[int(r.row)]
            row = {"group": group, "cutoff": str(cutoff), "api10": r.api10, "package": r.package, "x": r.x, "y": r.y,
                   "state_code": str(r.state_code).replace(".0", ""), "lateral_ft": float(r.lateral_ft), "lat_c": float(r.lat_c),
                   "source": s["source"], "radius_mi": s["radius_mi"], "n_analogs": len(s["api10s"]), "thin": s["thin"],
                   "analogs": ";".join(s["api10s"]), "ratio_sub_mode": (c["ratio"] or {}).get("sub_mode"),
                   "ratio_alpha": (c["ratio"] or {}).get("alpha"), "ratio_beta": (c["ratio"] or {}).get("beta")}
            for k in w.HORIZONS:
                row[f"actual_w{k}"] = float(np.cumsum(act_w[i])[k - 1]) if np.isfinite(act_w[i, k - 1]) else np.nan
                row[f"actual_o{k}"] = float(np.cumsum(act_o[i])[k - 1]) if np.isfinite(act_o[i, k - 1]) else np.nan
                row[f"box_o{k}"] = float(np.cumsum(oil)[k - 1] * F[k - 1]) if np.isfinite(oil[:k]).all() else np.nan
                row[f"bench_w{k}"] = bench[k][i]
            if c["ratio"] and np.isfinite(oil[:36]).all():
                cw = w.cum_at(w.ratio_water(oil, r.lat_c, c["ratio"]), F)
                row |= {f"ratio_w{k}": cw[k] for k in w.HORIZONS}
            if c["ratio"]:
                ao = np.nan_to_num(act_o[i])
                cw = w.cum_at(w.ratio_water(ao, r.lat_c, c["ratio"]), None)
                row |= {f"ratio_actoil_w{k}": (cw[k] if np.isfinite(act_o[i, k - 1]) else np.nan) for k in w.HORIZONS}
            rows.append(row)
        print(f"[water holdout {group} {y}] {len(v)} measured targets, {len(need)} analogs fitted ({time.time() - t0:.0f} s)", flush=True)
    return pd.DataFrame(rows)


def run(conn: Any, run_dir: Path, groups: list[str], workers: int | None) -> None:
    vdr = pd.DataFrame(rep._read(conn, bw._VDR_SQL, {"last": LAST}), columns=["api10", "month", "water"]).astype({"water": float})
    for g in groups:
        if (run_dir / g / "water_holdout.csv.gz").exists():
            print(f"[water holdout {g}] already done, skipped", flush=True)
            continue
        t = run_group(conn, run_dir, g, vdr, workers)
        conn.rollback()
        t.to_csv(run_dir / g / "water_holdout.csv.gz", index=False)
        print(f"[water holdout {g}] wrote {len(t)} rows (not read here)", flush=True)
