"""BOX step 11 — water method + acceptance design (READ-ONLY; plan §5 step 11). See box/water11.py.

    python -m scripts.box_water11 reach  --out runs/step11 [--groups WCA,...] [--workers N]
    python -m scripts.box_water11 tune   --out runs/step11 --inputs runs/step11_inputs [--groups ...] [--workers N]
    python -m scripts.box_water11 counts --out runs/step11 [--groups ...]

reach   (a) every covered / covered_provisional location of the record run: measured-water reach on the D54 ladder + the water
        extension, the calculated-fallback share, TX locations drawing NM analogs.
tune    (b) the method comparison on TUNING packages only — the tuning views / box_v2 oil months of each group's tuning run
        (runs/step11_inputs/<group>/, holdout packages were dropped there before anything was written). Never reads a holdout
        well's water.
counts  (c) judgeable-cell counts: tuning measured-water packages per horizon AND holdout package COUNTS (holdout wells' labels
        and months on production only — no volume of a holdout well is read).
"""

from __future__ import annotations

import argparse
import datetime as dt
import glob
import json
import sys
import time
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from box import acceptance as ac
from box import analog as an
from box import backtest_report as br
from box import holdout as ho
from box import tc_curve as tc
from box import tc_curve_report as rep
from box import water11 as w
from box.dev_factor_report import _xy
from etl.db import get_connection

_LOC_SQL = """
SELECT f.location_id, f.bench, f.formation_blueox, f.coverage, f.completed_lateral_ft, f.planned_spacing_ft, f.pad_name,
       extensions.ST_X(p.pt), extensions.ST_Y(p.pt)
FROM box.pud_forecast f
JOIN box.forecast_run r USING (run_id)
JOIN box.location l USING (location_id)
CROSS JOIN LATERAL (SELECT CASE WHEN extensions.GeometryType(l.geom) = 'LINESTRING'
                                THEN extensions.ST_LineInterpolatePoint(l.geom, 0.5)
                                ELSE extensions.ST_Centroid(l.geom) END AS pt) p
WHERE r.is_record AND f.coverage IN ('covered', 'covered_provisional')
"""
_RUN_SQL = "SELECT run_id FROM box.forecast_run WHERE is_record"
_CLS_SQL = """
SELECT api10, prod_date, oil_per_month_bbl, water_per_month_bbl, COALESCE(is_water_proprietary, FALSE)
FROM curated.production
WHERE api10 = ANY(%(a)s) AND months_on_production BETWEEN 1 AND 24 AND oil_per_month_bbl > 0 AND water_per_month_bbl > 0
  AND prod_date <= %(last)s
"""
_SQL41_SQL = "SELECT api10, water_source FROM curated.water_data_quality WHERE api10 = ANY(%(a)s)"
_VDR_SQL = """
SELECT api10, date_trunc('month', prod_date)::date, sum(water_bbl)
FROM vdr.well_daily WHERE api10 IS NOT NULL AND prod_date < (%(last)s::date + interval '1 month')
GROUP BY 1, 2
"""
_MOP_SQL = """
SELECT api10, min(prod_date), max(prod_date) FROM curated.production
WHERE api10 = ANY(%(a)s) AND prod_date <= %(last)s GROUP BY 1
"""


def _chunks(ids: list[str], n: int = 5000) -> list[list[str]]:
    return [ids[i : i + n] for i in range(0, len(ids), n)]


def pull_cls(conn: Any, ids: list[str]) -> pd.DataFrame:
    rows = [r for c in _chunks(ids) for r in rep._read(conn, _CLS_SQL, {"a": c, "last": w.LAST})]
    return pd.DataFrame(rows, columns=["api10", "prod_date", "oil", "water", "prop"])


def pull_vdr(conn: Any) -> pd.DataFrame:
    return pd.DataFrame(rep._read(conn, _VDR_SQL, {"last": w.LAST}), columns=["api10", "month", "water"]).astype({"water": float})


def pull_span(conn: Any, ids: list[str]) -> pd.DataFrame:
    rows = [r for c in _chunks(ids) for r in rep._read(conn, _MOP_SQL, {"a": c, "last": w.LAST})]
    return pd.DataFrame(rows, columns=["api10", "first_month", "last_month"]).set_index("api10")


def group_frame(conn: Any, group: str) -> pd.DataFrame:
    """The group's pool well set (BENCH_SPECS tags, exclusions.csv) with xy, completed lateral, spacing, first / last month."""
    wells, _, _ = ac.bench_wells(w.GROUP_WELLS[group], group)
    wells = wells.drop_duplicates("api10").reset_index(drop=True)
    x, y = _xy(wells["mid_lon"], wells["mid_lat"])
    wells["x"], wells["y"] = x, y
    ids = sorted(wells["api10"])
    ut = an.uturn_leg_spacing(conn, ids)
    lat = pd.to_numeric(wells["lateral_length_ft"], errors="coerce")
    wells["lateral"] = [an.completed_lateral(a, float(v), ut) if np.isfinite(v) and v > 0 else np.nan for a, v in zip(wells["api10"], lat, strict=True)]
    wells["spacing"] = wells["api10"].map(br.spacing(conn, ids)).astype(float)
    span = pull_span(conn, ids)
    wells["first_month"] = wells["api10"].map(span["first_month"])
    wells["last_month"] = wells["api10"].map(span["last_month"])
    wells["state_code"] = wells["state_code"].astype(str).str.replace(".0", "", regex=False)
    return wells[wells["first_month"].notna() & (wells["lateral"] > 0)].reset_index(drop=True)


def pool_asof(wells: pd.DataFrame, labels: pd.Series, asof: dt.date, cutoff: dt.date | None) -> tuple[dict[str, Any], dict[str, Any], pd.DataFrame]:
    """(measured pool, whole pool, frame) of wells first producing before `cutoff` (None = all) with production through `asof`."""
    f = wells[[m <= asof for m in wells["first_month"]]].copy()
    if cutoff is not None:
        f = f[[d < cutoff for d in f["first_production_date"]]]
    f["months"] = [w.month_index(m, asof) + 1 for m in f["first_month"]]
    f["label"] = f["api10"].map(labels).fillna("insufficient")
    f = f.reset_index(drop=True)
    return w.make_pool(f[f["label"] == "measured"].reset_index(drop=True)), w.make_pool(f), f


# ----------------------------------------------------------------------------
# (a) reach
# ----------------------------------------------------------------------------


def run_reach(conn: Any, out: Path, groups: tuple[str, ...], workers: int | None) -> None:
    run_id = rep._read(conn, _RUN_SQL)[0][0]
    loc = pd.DataFrame(rep._read(conn, _LOC_SQL), columns=["location_id", "bench", "formation_blueox", "coverage", "lateral_ft", "spacing_ft", "pad_name", "lon", "lat"])
    loc["group"] = [w.group_of(b, f) for b, f in zip(loc["bench"], loc["formation_blueox"], strict=True)]
    loc["state"] = np.where(loc["lat"] >= 32.0, "NM", "TX")  # Delaware: the TX / NM line is the 32nd parallel
    vdr = pull_vdr(conn)
    vm = w.vdr_months_asof(vdr, w.LAST)
    rows, pools = [], []
    for g in groups:
        t0 = time.time()
        wells = group_frame(conn, g)
        cls = pull_cls(conn, list(wells["api10"]))
        labels = w.labels_asof(wells, cls, w.LAST, vm)
        s41 = dict(rep._read(conn, _SQL41_SQL, {"a": list(wells["api10"])}))
        pm, pa, f = pool_asof(wells, labels, w.LAST, None)
        f["sql41"] = f["api10"].map(s41)
        pools.append(f[["api10", "state_code", "formation_blueox", "first_production_date", "months", "label", "sql41"]].assign(group=g))
        L = loc[loc["group"] == g].reset_index(drop=True)
        lx, ly = _xy(L["lon"], L["lat"])
        locs = [{"api10": f"L{r.location_id}", "x": lx[i], "y": ly[i], "lateral_ft": float(r.lateral_ft), "spacing_ft": r.spacing_ft, "fp_max": None}
                for i, r in enumerate(L.itertuples())]
        res = w.select_many(locs, pm, pa, w.ac_label(g), workers)
        R = pd.DataFrame([{k: v for k, v in r.items() if k != "api10s"} | {"n_analogs": len(r["api10s"])} for r in res])
        R["location_id"] = R["loc"].str[1:].astype(int)
        rows.append(L.drop(columns=["lon", "lat"]).merge(R.drop(columns="loc"), on="location_id"))
        print(f"[{g}] {len(L)} locations, pool {len(pa['api10'])} ({len(pm['api10'])} measured) ({time.time() - t0:.0f} s)", flush=True)
    out.mkdir(parents=True, exist_ok=True)
    pd.concat(rows, ignore_index=True).to_csv(out / "reach_locations.csv.gz", index=False)
    pd.concat(pools, ignore_index=True).to_csv(out / "reach_pools.csv.gz", index=False)
    (out / "reach_meta.json").write_text(json.dumps({"run_id": int(run_id), "production_through": str(w.LAST), "radii_mi": list(w.WATER_RADII_MI),
                                                     "built_at": dt.datetime.now(tz=dt.UTC).isoformat(timespec="seconds"),
                                                     "vdr_wells_with_6mo_water": sum(1 for v in vm.values() if v >= 6)}, indent=2), encoding="utf-8")


# ----------------------------------------------------------------------------
# (b) tuning
# ----------------------------------------------------------------------------


def _members(pool_f: pd.DataFrame, fits: dict[str, Any], ids: list[str]) -> list[tc.Member]:
    sub = pool_f.set_index("api10").loc[ids]
    p = {"api10": np.array(ids), "months": sub["months"].to_numpy(float), "lateral": sub["lateral"].to_numpy(float),
         "params": {a: {s: (fits.get(a, {}).get(s) or {}).get("params") for s in ("oil", "gas", "water")} for a in ids}}
    keep = [i for i, a in enumerate(ids) if p["params"][a]["oil"] or p["params"][a]["water"]]
    return an.members_with_transfer(p, keep)


_T: dict[str, Any] = {}


def _tinit(state: dict[str, Any]) -> None:
    rep._quiet()
    _T.clear()
    _T.update(state)


def _cohort_job(job: tuple[str, list[str]]) -> tuple[str, dict[str, Any]]:
    key, ids = job
    m = _members(_T["pool_f"], _T["fits"], ids)
    return key, (w.cohort_water(m) if len(m) >= w.MIN_USE else {"ratio": None, "arps": None, "arps_months": None})


def cohort_curves(jobs: list[tuple[str, list[str]]], pool_f: pd.DataFrame, fits: dict[str, Any], workers: int | None) -> dict[str, dict[str, Any]]:
    from concurrent.futures import ProcessPoolExecutor

    state = {"pool_f": pool_f, "fits": fits}
    workers = workers or 8
    if workers == 1:
        _tinit(state)
        return dict(_cohort_job(j) for j in jobs)
    with ProcessPoolExecutor(max_workers=workers, initializer=_tinit, initargs=(state,)) as ex:
        return dict(ex.map(_cohort_job, jobs, chunksize=4))


def run_tune(conn: Any, out: Path, inputs: Path, groups: tuple[str, ...], workers: int | None) -> None:
    vdr = pull_vdr(conn)
    out.mkdir(parents=True, exist_ok=True)
    for g in groups:
        t0 = time.time()
        tag = w.TUNING_TAG[g]
        d = inputs / g
        z = np.load(d / f"months_{tag}.npz")
        views = {int(Path(p).name.split("_")[-1][:4]): p for p in sorted(glob.glob(str(d / f"view_{tag}_20*.csv.gz")))}
        wells = group_frame(conn, g)
        tgt_all = pd.concat([pd.read_csv(p, dtype={"api10": str, "package": str, "state_code": str}) for p in views.values()], ignore_index=True)
        if tgt_all["package_held_out"].astype(bool).any():
            raise RuntimeError(f"{g}: a tuning view carries a held-out package")
        ids_all = sorted(set(wells["api10"]) | set(tgt_all["api10"]))
        cls = pull_cls(conn, ids_all)
        prod = rep.pull_production(conn, ids_all, w.LAST)
        meta = rep.pull_meta(conn, ids_all)
        ut = an.uturn_leg_spacing(conn, sorted(set(tgt_all["api10"])))
        # target label = its own (outcome-side) water, all data through LAST
        tw = tgt_all.drop_duplicates("api10")[["api10", "state_code"]].copy()
        tw["state_code"] = tw["state_code"].astype(str).str.replace(".0", "", regex=False)
        t_lab = w.labels_asof(tw, cls, w.LAST, w.vdr_months_asof(vdr, w.LAST))
        rows = []
        for y, path in views.items():
            cutoff = dt.date(y, 12, 1)
            asof = br._prev_month(cutoff)
            v = pd.read_csv(path, dtype={"api10": str, "package": str})
            ids = list(z[f"{y}_api10"].astype(str))
            if ids != list(v["api10"]):
                raise RuntimeError(f"{g} {y}: npz / view order differ")
            labels = w.labels_asof(wells, cls, asof, w.vdr_months_asof(vdr, asof))
            pm, pa, pf = pool_asof(wells, labels, asof, cutoff)
            v["label"] = v["api10"].map(t_lab).fillna("insufficient")
            v["row"] = np.arange(len(v))
            v = v[v["label"] == "measured"].reset_index(drop=True)
            if v.empty:
                continue
            vx, vy = _xy(v["mid_lon"], v["mid_lat"])
            v["lat_c"] = [an.completed_lateral(a, float(L), ut) for a, L in zip(v["api10"], v["lateral_ft"], strict=True)]
            locs = [{"api10": r.api10, "x": vx[i], "y": vy[i], "lateral_ft": float(r.lat_c), "spacing_ft": r.spacing_ft,
                     "fp_max": pd.Timestamp(r.first_production_date).date()} for i, r in enumerate(v.itertuples())]
            sel = w.select_many(locs, pm, pa, w.ac_label(g), workers)
            need = sorted({a for s in sel for a in s["api10s"]})
            pr = prod[prod["api10"].isin(set(need)) & (prod["prod_date"] <= asof)]
            fits = rep.fit_wells(pr, meta[meta["api10"].isin(set(need))], workers)
            jobs = [(s["loc"], s["api10s"]) for s in sel]
            cur = cohort_curves(jobs, pf, fits, workers)
            # actuals (outcome side) + the measured-pool benchmark
            act_w = w.stream_matrix(prod, list(v["api10"]), "water_bbl", drop_latest=True)
            act_o = w.stream_matrix(prod, list(v["api10"]), "oil_bbl", drop_latest=True)
            bench = measured_benchmark(pf[pf["label"] == "measured"], prod, asof, v)
            F = z[f"{y}_F_oil"]
            for i, (r, s) in enumerate(zip(v.itertuples(), sel, strict=True)):
                c = cur[r.api10]
                oil = z[f"{y}_oil"][int(r.row)]
                row = {"group": g, "cutoff": str(cutoff), "api10": r.api10, "package": r.package, "state_code": str(r.state_code).replace(".0", ""),
                       "lateral_ft": float(r.lateral_ft), "lat_c": float(r.lat_c), "source": s["source"], "radius_mi": s["radius_mi"],
                       "n_analogs": len(s["api10s"]), "thin": s["thin"], "nm_share": s["nm_share"],
                       "ratio_sub_mode": (c["ratio"] or {}).get("sub_mode"), "ratio_alpha": (c["ratio"] or {}).get("alpha"),
                       "ratio_beta": (c["ratio"] or {}).get("beta"), "arps_Di": (c["arps"] or {}).get("Di"), "arps_b": (c["arps"] or {}).get("b")}
                ca = np.cumsum(np.nan_to_num(act_w[i], nan=np.nan))
                for k in w.HORIZONS:
                    row[f"actual_w{k}"] = float(ca[k - 1]) if np.isfinite(act_w[i, k - 1]) else np.nan
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
                if c["arps_months"] is not None:
                    cw = w.cum_at(np.asarray(c["arps_months"]) * r.lat_c / 1000.0, F)
                    row |= {f"arps_w{k}": cw[k] for k in w.HORIZONS}
                rows.append(row)
            print(f"[{g} {y}] {len(v)} measured targets, {len(need)} analogs fitted ({time.time() - t0:.0f} s)", flush=True)
        pd.DataFrame(rows).to_csv(out / f"tune_{g}.csv.gz", index=False)
        print(f"[{g}] done ({time.time() - t0:.0f} s)", flush=True)


def measured_benchmark(pm: pd.DataFrame, prod: pd.DataFrame, asof: dt.date, v: pd.DataFrame) -> dict[int, np.ndarray]:
    """D53 local offsets on measured wells: median per-1,000-ft water cum-k of the 15 nearest measured pre-cutoff pool wells (first
    production >= 2016) whose cum-k was known at the cutoff, x the target's lateral."""
    from scipy.spatial import cKDTree

    pm = pm[[d >= dt.date(2016, 1, 1) for d in pm["first_production_date"]]].reset_index(drop=True)
    mat = w.stream_matrix(prod[prod["api10"].isin(set(pm["api10"]))], list(pm["api10"]), "water_bbl", asof=asof)
    vx, vy = _xy(v["mid_lon"], v["mid_lat"])
    out = {}
    lat_p = pd.to_numeric(pm["lateral_length_ft"], errors="coerce").to_numpy(float) / 1000.0
    for k in w.HORIZONS:
        per = np.cumsum(mat, axis=1)[:, k - 1] / lat_p
        ok = np.isfinite(per) & (per > 0)
        if ok.sum() < w.BENCH_K:
            out[k] = np.full(len(v), np.nan)
            continue
        _, j = cKDTree(np.column_stack([pm["x"].to_numpy(float)[ok], pm["y"].to_numpy(float)[ok]])).query(np.column_stack([vx, vy]), k=w.BENCH_K)
        out[k] = np.median(per[ok][j], axis=1) * v["lateral_ft"].to_numpy(float) / 1000.0
    return out


# ----------------------------------------------------------------------------
# (c) counts
# ----------------------------------------------------------------------------


def run_counts(conn: Any, out: Path, groups: tuple[str, ...]) -> None:
    """Per group x cutoff x side (tuning / holdout): scored wells, measured-water wells and packages, and how many reached
    cum-12 / 24 / 36 water. Packages = the D53 rule on the scored wells (box/acceptance.packages over spacing3d pairs).
    Holdout side: labels + months on production only."""
    from box import spacing3d_report as s3r

    vdr = pull_vdr(conn)
    vm = w.vdr_months_asof(vdr, w.LAST)
    rows = []
    for g in groups:
        wells = group_frame(conn, g)
        spec = ac.BENCH_SPECS[g]
        tg = set(wells["api10"]) if spec["target_tags"] is None else set(wells.loc[wells["formation_blueox"].isin(spec["target_tags"]), "api10"])
        cls = pull_cls(conn, list(wells["api10"]))
        lab = w.labels_asof(wells, cls, w.LAST, vm)
        subj = wells[[f >= dt.date(2016, 1, 1) for f in wells["first_production_date"]]].reset_index(drop=True)
        P = s3r.build_pairs(conn, subj)
        ext = rep_extent(conn, spec["extent"])
        for c in ac.CUTOFFS:
            end = br._add_months(c, 12)
            hs = wells[np.array([c <= f < end for f in wells["first_production_date"]]) & wells["api10"].isin(tg).to_numpy()].copy()
            hx, hy = hs["x"].to_numpy(float), hs["y"].to_numpy(float)
            hs = hs[rep.assign_area(np.column_stack([hx, hy]), [ext]) > 0].reset_index(drop=True)
            if hs.empty:
                continue
            hs["package"] = hs["api10"].map(ac.packages(list(hs["api10"]), P["pairs"]))
            hs["holdout_block"] = ho.is_holdout(hs["x"].to_numpy(float), hs["y"].to_numpy(float))
            held = set(hs.loc[hs["holdout_block"], "package"])
            hs["side"] = np.where(hs["package"].isin(held), "holdout", "tuning")
            hs["label"] = hs["api10"].map(lab).fillna("insufficient")
            # months known = newest reported month minus one (drop_latest), = the actuals' horizon rule
            hs["known"] = [w.month_index(a, b) for a, b in zip(hs["first_month"], hs["last_month"], strict=True)]
            for side, s in hs.groupby("side"):
                m = s[s["label"] == "measured"]
                r = {"group": g, "cutoff": str(c), "side": side, "n_wells": len(s), "n_packages": s["package"].nunique(),
                     "n_measured_wells": len(m), "n_measured_packages": m["package"].nunique(),
                     "n_nm_measured_wells": int((m["state_code"] == w.NM).sum())}
                for k in w.HORIZONS:
                    r[f"pk_w{k}"] = m.loc[m["known"] >= k, "package"].nunique()
                rows.append(r)
        print(f"[{g}] counted", flush=True)
    out.mkdir(parents=True, exist_ok=True)
    pd.DataFrame(rows).to_csv(out / "counts.csv", index=False)


def rep_extent(conn: Any, bench: str) -> Any:
    from box import tc_area_report as tar

    return tar.pull_extent(conn, bench)["geom_ft"]


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("cmd", choices=("reach", "tune", "counts"))
    ap.add_argument("--out", type=Path, default=Path("runs") / "step11")
    ap.add_argument("--inputs", type=Path, default=Path("runs") / "step11_inputs")
    ap.add_argument("--groups", default=",".join(w.GROUPS))
    ap.add_argument("--workers", type=int, default=None)
    a = ap.parse_args(argv)
    groups = tuple(a.groups.split(","))
    t0 = time.time()
    with get_connection() as conn:
        {"reach": lambda: run_reach(conn, a.out, groups, a.workers), "tune": lambda: run_tune(conn, a.out, a.inputs, groups, a.workers),
         "counts": lambda: run_counts(conn, a.out, groups)}[a.cmd]()
    print(f"{a.cmd} done ({time.time() - t0:.0f} s)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
