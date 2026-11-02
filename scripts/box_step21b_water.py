"""BOX step 21b — Midland water on the tuning folds (PREREGISTRATION §7: D107 ratio on raw mid_r2 oil, D108; D109 cells).

Called by `python -m scripts.box_step21b water`. The loop of scripts/box_water11.run_tune (steps 11 / 12a, the code of record for
D107 / D109) for the Midland, with three differences and nothing else:
  * the data-through is the pre-registered 2026-08-01 (box_water11's helpers pin the Delaware 2026-07-01 `w.LAST`; their SQL is
    reused verbatim with this date);
  * basin 'midland' for the selection's lateral tolerance and the fits' terminal Df (step 19; D132);
  * the oil the ratio rides on is RAW mid_r2 (D108 as registered): the uptime-free months the §10 run observed
    (months_mid_r2.npz) x F_oil(k) recovered from the harness view (box/step21b.f_from_view, identity-checked).
Targets = the scored TUNING wells of the §10 views whose own water is measured (as of 2026-08-01); packages = their D53 packages
restricted to measured members. Held-out packages never appear (the harness dropped them). Read-only.
"""

from __future__ import annotations

import datetime as dt
import time
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from box import acceptance as ac
from box import analog as an
from box import backtest_report as br
from box import step21 as st
from box import step21b as sb
from box import tc_curve_report as rep
from box import water11 as w
from box.dev_factor_report import _xy
from scripts import box_water11 as bw

BASIN = "midland"
LAST = dt.date.fromisoformat(st.DEFINITION["folds"]["actuals_through"])


def _rows(conn: Any, sql: str, ids: list[str], cols: list[str]) -> pd.DataFrame:
    return pd.DataFrame([r for c in bw._chunks(ids) for r in rep._read(conn, sql, {"a": c, "last": LAST})], columns=cols)


def group_frame(conn: Any, group: str) -> pd.DataFrame:
    """scripts/box_water11.group_frame on the frozen Midland pool with the 2026-08-01 span."""
    wells, _, _ = ac.bench_wells(st.POOL_DIR, group)
    wells = wells.drop_duplicates("api10").reset_index(drop=True)
    x, y = _xy(wells["mid_lon"], wells["mid_lat"])
    wells["x"], wells["y"] = x, y
    ids = sorted(wells["api10"])
    ut = an.uturn_leg_spacing(conn, ids)
    lat = pd.to_numeric(wells["lateral_length_ft"], errors="coerce")
    wells["lateral"] = [an.completed_lateral(a, float(v), ut) if np.isfinite(v) and v > 0 else np.nan for a, v in zip(wells["api10"], lat, strict=True)]
    wells["spacing"] = wells["api10"].map(br.spacing(conn, ids)).astype(float)
    span = _rows(conn, bw._MOP_SQL, ids, ["api10", "first_month", "last_month"]).set_index("api10")
    wells["first_month"] = wells["api10"].map(span["first_month"])
    wells["last_month"] = wells["api10"].map(span["last_month"])
    wells["state_code"] = wells["state_code"].astype(str).str.replace(".0", "", regex=False)
    return wells[wells["first_month"].notna() & (wells["lateral"] > 0)].reset_index(drop=True)


def f_array(view: pd.DataFrame, months: np.ndarray) -> np.ndarray:
    """F_oil(k) at the scored horizons (recovered from the harness, identity-checked); NaN elsewhere (w.cum_at reads k - 1 only)."""
    F = np.full(w.K, np.nan)
    for k in w.HORIZONS:
        if f"pred_{st.RAW}_oil{k}" in view and view[f"pred_{st.RAW}_oil{k}"].notna().any():
            F[k - 1] = sb.f_from_view(view, months, "oil", k)[0]
    return F


def run_group(conn: Any, run: Path, group: str, vdr: pd.DataFrame, workers: int | None) -> pd.DataFrame:
    t0 = time.time()
    d = run / group
    z = np.load(d / "months_mid_r2.npz")
    wells = group_frame(conn, group)
    views = {int(p.name.split("_")[-1][:4]): p for p in sorted(d.glob(f"view_tuning_v2_{group}_analog_20*.csv.gz"))}
    tgt_all = pd.concat([pd.read_csv(p, dtype={"api10": str, "package": str, "state_code": str}) for p in views.values()], ignore_index=True)
    if tgt_all["package_held_out"].astype(bool).any():
        raise RuntimeError(f"{group}: a tuning view carries a held-out package")
    ids_all = sorted(set(wells["api10"]) | set(tgt_all["api10"]))
    cls = _rows(conn, bw._CLS_SQL, ids_all, ["api10", "prod_date", "oil", "water", "prop"])
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
        F = f_array(v, oil_m)
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
        print(f"[water {group} {y}] {len(v)} measured targets, {len(need)} analogs fitted ({time.time() - t0:.0f} s)", flush=True)
    return pd.DataFrame(rows)


def run(conn: Any, run_dir: Path, groups: list[str], workers: int | None) -> None:
    vdr = pd.DataFrame(rep._read(conn, bw._VDR_SQL, {"last": LAST}), columns=["api10", "month", "water"]).astype({"water": float})
    for g in groups:
        if (run_dir / g / "water_tune.csv.gz").exists():
            print(f"[water {g}] already done, skipped", flush=True)
            continue
        t = run_group(conn, run_dir, g, vdr, workers)
        conn.rollback()
        t.to_csv(run_dir / g / "water_tune.csv.gz", index=False)
        print(f"[water {g}] wrote {len(t)} rows", flush=True)
