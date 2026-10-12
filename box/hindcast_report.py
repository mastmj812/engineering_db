"""BOX step 6 — hindcast vs Novi 2025Q3: rebuild steps 4–5 at the cutoff, predict the holdout, score, page.

Read-only against the warehouse (session pooler, READ ONLY transactions). Nothing is stored.

Cutoff (plan §5 step 6). The 2025Q3 report's per-basin PDP recognition cliff (curated.intel_pdp_cliff_date,
2024-12-01 Delaware) splits the wells: Novi's holdout is every producer first-producing on/after the
cliff and absent from its PDP class (sql/43). BOX sees only production through PROD_ASOF (2025-06, one
quarter before the report's 2025-09-30 vintage date) and only wells first-producing before the cliff.

Rebuilt with that data only — same methods and knobs as the records, nothing re-tuned:
  * step 4: TC areas inside the SAME WCA extent of record (plan: "same extents"), D9 12-mo cohort with 12
    full months by PROD_ASOF (step 1's rule), contiguity-constrained Ward + blocked CV + paired 1-SE k pick
    (box/tc_area.py, D29 method; k is whatever the rule picks on the cutoff data);
  * step 5b: per-well fits on production through PROD_ASOF (blueox-boxfit, the pinned engine), cohort-MEAN
    curve per area per stream through the D10/D37 ladder, gas = ratio mode (D30), exact months (D39);
  * steps 5c/5d: factors of record re-estimated on the cutoff cohorts (WCA = hindcast areas as location FE,
    BS2_S = 5-mi blocks, for the D45 basin rung), D42 + D45 + D47, point estimates; ref_mult per area (D43);
  * D36 F(k): Σ actual / Σ prediction on the WCA training cohort at the cutoff, per stream.

The gate-1 well sets, exclusions.csv and the extents are the frozen records (D28/D29); their small
post-cutoff information content is stated on the page, not removed.

Holdout = sql/43 2025Q3 Delaware rows whose api10 is in the gate-1 WCA set (not excluded), midpoint in a
hindcast area. Scored vs Novi on the `direct` tier (Novi has a matched forecast); BOX alone on every
holdout well. Actuals = sql/43's (cum at months-on-production k, is_latest_reported excluded) for both.
"""

from __future__ import annotations

import datetime as dt
import json
import math
from pathlib import Path
from typing import Any

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import shapely
from scipy.spatial import cKDTree

from box import dev_factor_report as dfr
from box import edge_gap as eg
from box import edge_gap_report as egr
from box import exclusions
from box import hindcast as hc
from box import tc_area as ta
from box import tc_area_report as tar
from box import tc_curve as tc
from box import tc_curve_report as rep
from box import tc_record as tr
from box import tc_record_report as trr
from box.edge_gap_report import _CSS, _png, _table

REPORT = "2025Q3"
BASIN = "delaware"
POOL = "WCA"
PROD_ASOF = dt.date(2025, 6, 1)  # last production month BOX may see (one quarter before the 2025-09-30 vintage date)
STEP4 = Path("docs") / "box" / "step4-2026-10-09"
STEP5B = Path("docs") / "box" / "step5b-2026-10-10"
STEP5D = Path("docs") / "box" / "step5d-2026-10-12"

_CLIFF_SQL = "SELECT curated.intel_pdp_cliff_date(%(r)s, %(b)s)"
_HOLD_SQL = """
SELECT api10, mop, tier, formation_blueox, operator, first_production_date, drilled_ll_ft, novi_ll_ft,
       actual_cum_oil, actual_cum_gas, fcst_cum_oil, fcst_cum_gas, pct_err_oil_perft, pct_err_gas_perft
FROM curated.intel_forecast_accuracy_vintage
WHERE report_version = %(r)s AND basin = %(b)s AND mop = ANY(%(m)s) AND NOT is_latest_reported AND api10 = ANY(%(a)s)
"""
_HOLD_ALL_SQL = """
SELECT DISTINCT api10, tier, formation_blueox, first_production_date
FROM curated.intel_forecast_accuracy_vintage WHERE report_version = %(r)s AND basin = %(b)s AND api10 = ANY(%(a)s)
"""


# ----------------------------------------------------------------------------
# Step 4 at the cutoff
# ----------------------------------------------------------------------------


def cohort_frame(wells: pd.DataFrame, extent_ft: Any, asof: dt.date) -> pd.DataFrame:
    """Step-4 frame at `asof`: midpoint xy (UTM 13N ft), inside the extent, 12-mo oil/ft (Novi pass-through,
    the step-4 response) and the D9 cohort flag with step 1's 12-full-months rule at `asof`."""
    d = wells.copy()
    x, y = eg._transformer().transform(d["mid_lon"].to_numpy(float), d["mid_lat"].to_numpy(float))
    d["x"], d["y"] = np.asarray(x) * eg._M_TO_FT, np.asarray(y) * eg._M_TO_FT
    shapely.prepare(extent_ft)
    d["inside"] = shapely.contains_xy(extent_ft, d["x"].to_numpy(), d["y"].to_numpy())
    ll = pd.to_numeric(d["lateral_length_ft"], errors="coerce")
    cum12 = pd.to_numeric(d["cum_12m_oil_bbl"], errors="coerce")
    d["oil12_ft"] = cum12 / ll
    fp = d["first_production_date"]
    d["c12"] = (pd.Series([f >= tar.COHORT_FP_MIN and f <= asof - dt.timedelta(days=395) for f in fp], index=d.index)
                & ll.between(tar.LL_MIN, tar.LL_MAX) & (cum12 > 0) & d["inside"])
    return d


def rebuild_areas(conn: Any, wells: pd.DataFrame, asof: dt.date) -> dict[str, Any]:
    ext = tar.pull_extent(conn)
    d = cohort_frame(wells, ext["geom_ft"], asof)
    r = tar.regionalize(ext["geom_ft"], d, ta.DEFAULT)
    return {"extent": ext, "frame": d, "r": r, "geoms": r["geoms"]}


def area_overlap(hind: list[Any], record: list[Any]) -> pd.DataFrame:
    """Each hindcast area's best-overlapping record area (share of the hindcast area's ground)."""
    rows = []
    for i, g in enumerate(hind, start=1):
        a = shapely.area(g)
        ov = [shapely.area(shapely.intersection(g, h)) for h in record]
        j = int(np.argmax(ov))
        rows.append({"area_no": i, "sqmi": a / eg.FT_PER_MI**2, "record_area": j + 1, "share_in_record_area": ov[j] / a,
                     "iou": ov[j] / shapely.area(shapely.union(g, record[j]))})
    return pd.DataFrame(rows)


# ----------------------------------------------------------------------------
# Step 5b at the cutoff
# ----------------------------------------------------------------------------


def rebuild_curves(conn: Any, wells: pd.DataFrame, areas: dict[str, Any], cliff: dt.date, asof: dt.date, workers: int | None) -> dict[str, Any]:
    geoms = areas["geoms"]
    d4 = areas["frame"]
    x, y = d4["x"].to_numpy(), d4["y"].to_numpy()
    in_area = rep.assign_area(np.column_stack([x, y]), geoms) > 0
    pre = pd.Series([f < cliff for f in wells["first_production_date"]], index=wells.index)
    cand = wells[in_area & pre.to_numpy() & (pd.to_numeric(wells["lateral_length_ft"], errors="coerce") > 0).to_numpy()]
    ids = sorted(cand["api10"])
    prod = rep.pull_production(conn, ids, asof)
    meta = rep.pull_meta(conn, ids)
    act = rep.actuals(prod, asof)
    fits = rep.fit_wells(prod, meta, workers)
    rates = {r_.api10: {s: getattr(r_, f"rates_{s}") for s in tc.STREAMS} for r_ in act.itertuples()}
    d = rep.build_frame(cand, {"geoms": geoms}, act, fits, asof)
    d["c12"] = d["api10"].isin(set(d4.loc[d4["c12"], "api10"]))
    nb = rep.neighbours(geoms)
    curves = rep.build_area_curves(d, fits, rates, nb, len(geoms))
    rows = []
    for a, cur in curves.items():
        frame_by = {s: d[d.api10.isin(cur["streams"][s]["api10s"])] for s in tc.STREAMS}
        rows += rep.curve_rows(a, cur, frame_by)
    return {"frame": d, "fits": fits, "prod": prod, "curves": curves, "rows": pd.DataFrame(rows), "n_fitted": len(fits)}


# ----------------------------------------------------------------------------
# Steps 5c/5d at the cutoff
# ----------------------------------------------------------------------------


def wca_factor_frame(conn: Any, cb: dict[str, Any], wells: pd.DataFrame, asof: dt.date) -> pd.DataFrame:
    d = cb["frame"]
    c = d[d["c12"]].copy()
    c = c.drop(columns=[k for k in ("mid_lon", "mid_lat", "tvd_ft") if k in c.columns]).merge(wells[["api10", "mid_lon", "mid_lat", "tvd_ft"]], on="api10", how="left")
    c["bench_pool"] = POOL
    c["loc"] = "a" + c["area_no"].astype(str)
    c["first_production_date"] = c["first_production_date"].astype(str)
    for s in tc.STREAMS:
        c[f"{s}_qi"] = [((cb["fits"].get(a) or {}).get(s) or {}).get("params", {}).get("qi", np.nan) for a in c["api10"]]
        c[f"{s}_eur"] = [((cb["fits"].get(a) or {}).get(s) or {}).get("eur", np.nan) for a in c["api10"]]
    prod = cb["prod"][cb["prod"]["api10"].isin(set(c["api10"]))]
    return dfr._with_actuals(conn, c, asof, prod)


def rebuild_factors(conn: Any, cb: dict[str, Any], wells: pd.DataFrame, wells_dir: Path, asof: dt.date, workers: int | None) -> dict[str, Any]:
    wca = wca_factor_frame(conn, cb, wells, asof)
    bs, bs_meta = dfr.bs2s_frame(conn, wells_dir, asof, workers)
    frames, repl = {}, {}
    for b, d in ((POOL, wca), ("BS2_S", bs)):
        d2, r = dfr.attach_scenario(conn, d)
        d2["infill"] = d2["infill"].astype(object).where(d2["infill"].notna(), False).astype(bool)
        d2["own_bench_in_pool"] = d2["own_bench_in_pool"].astype(bool)
        frames[b], repl[b] = trr.add_pooled_view(dfr.add_local_gor(d2)), r
    w = pd.concat(frames.values(), ignore_index=True)
    built = dt.datetime.now(tz=dt.UTC).astimezone().isoformat(timespec="seconds")
    est = trr.estimate_record(w, 0)
    rf = trr.risk_rows(est, 0, built)
    return {"w": w, "frames": frames, "rf": rf, "repl": repl, "bs2s": bs_meta, "n_est": est["n_est"]}


def well_factors(fr: pd.DataFrame, tabs: dict[str, dict[tuple[str, str], float]], *, pud: bool = False) -> pd.DataFrame:
    """f_oil and f_gor per well (D41 x D42 x D45 lookup); a well with no sql/50 row, or whose warehouse bench
    sits outside the pool (gate-1 moved it: its sql/50 relations are on the old bench), gets the reference."""
    scored = fr["view_class"].notna() & fr["own_bench_in_pool"].astype(bool)
    out = pd.DataFrame(index=fr.index)
    for s, col in (("oil", "f_oil"), ("gas", "f_gor")):
        out[col] = [tr.lookup(tabs[s], POOL, p if isinstance(p, str) else None, bool(i), pud=pud) if ok else 1.0
                    for p, i, ok in zip(fr["p_raw_pair"], fr["p_infill"], scored, strict=True)]
    out["scenario_scored"] = scored
    return out


def ref_mults(cb: dict[str, Any], wca: pd.DataFrame, tab_oil: dict[tuple[str, str], float]) -> dict[int, dict[str, Any]]:
    """D43 per area (oil curve's pool): Σ(w/f)/Σw over included members, w = actual cum-12/kft, f = factor."""
    w = wca.set_index("api10")
    fac = well_factors(wca, {"oil": tab_oil, "gas": tab_oil}).set_index(wca["api10"])["f_oil"]
    d = cb["frame"].set_index("api10")
    out = {}
    for a, cur in cb["curves"].items():
        ids = [x for x in cur["streams"]["oil"]["api10s"] if bool(d.at[x, "fit_oil"]) and float(d.at[x, "lateral_ft"] or 0) > 0]
        wt = [float(w.at[x, "oil12_kft"]) if x in w.index else float(d.at[x, "oil12_kft"]) for x in ids]
        f = [float(fac.get(x, 1.0)) for x in ids]
        out[a] = {"ref_mult": tr.weighted_ref_mult(wt, f), "n": len(ids), "n_unscored": int(sum(1 for x in ids if x not in fac.index))}
    return out


# ----------------------------------------------------------------------------
# Holdout
# ----------------------------------------------------------------------------


def pull_holdout(conn: Any, wells: pd.DataFrame) -> pd.DataFrame:
    """One row per holdout well: tier, sql/43 bench, actual + Novi cums / per-ft errors at mop 6 and 12."""
    ids = sorted(wells["api10"])
    allw = pd.DataFrame(rep._read(conn, _HOLD_ALL_SQL, {"r": REPORT, "b": BASIN, "a": ids}), columns=["api10", "tier", "sql43_bench", "fp43"])
    rows = pd.DataFrame(rep._read(conn, _HOLD_SQL, {"r": REPORT, "b": BASIN, "m": list(hc.HORIZONS), "a": ids}),
                        columns=["api10", "mop", "tier", "fb", "operator43", "fp", "drilled_ll_ft", "novi_ll_ft", "ao", "ag", "fo", "fg", "eo", "eg"])
    out = allw.copy()
    for k in hc.HORIZONS:
        r = rows[rows.mop == k].set_index("api10")
        for col, src in (("actual_oil", "ao"), ("actual_gas", "ag"), ("novi_fcst_oil", "fo"), ("novi_fcst_gas", "fg"), ("novi_err_oil", "eo"), ("novi_err_gas", "eg")):
            out[f"{col}{k}"] = pd.to_numeric(out["api10"].map(r[src]), errors="coerce").astype(float)
    ll = rows.drop_duplicates("api10").set_index("api10")
    out["drilled_ll_ft"] = pd.to_numeric(out["api10"].map(ll["drilled_ll_ft"]), errors="coerce")
    out["novi_ll_ft"] = pd.to_numeric(out["api10"].map(ll["novi_ll_ft"]), errors="coerce")
    for s in hc.SCORED_STREAMS:
        for k in hc.HORIZONS:
            out.loc[out["tier"] != "direct", f"novi_err_{s}{k}"] = np.nan
    return out


def local_gor(train: pd.DataFrame, xy: np.ndarray, k: int = dfr.LOCAL_GOR_K) -> np.ndarray:
    """D30 level at new locations: median 12-mo GOR of the k nearest TRAINING cohort wells (gor12 > 0)."""
    t = train[train["gor12"] > 0]
    tx, ty = dfr._xy(t["mid_lon"], t["mid_lat"])
    _, j = cKDTree(np.column_stack([tx, ty])).query(xy, k=k)
    return np.median(t["gor12"].to_numpy(float)[j], axis=1)


def predict_frame(fr: pd.DataFrame, cb: dict[str, Any], rm: dict[int, dict[str, Any]], F: dict[str, dict[int, float]] | None) -> pd.DataFrame:
    """BOX cum-6 / cum-12 oil + gas for each row (needs area_no, lateral_ft, gor_target, f_oil); also the
    curve-only and no-F variants for the decomposition."""
    out = []
    cache: dict[tuple[int, int], dict[str, float]] = {}
    for r in fr.itertuples():
        a = int(r.area_no)
        st = cb["curves"][a]["streams"]
        co = cache.setdefault((a, -1), hc.curve_cums(st["oil"]["curve"], None))
        cg = hc.curve_cums(st["gas"]["curve"], r.gor_target)
        cums = {**{f"oil{k}": co[f"oil{k}"] for k in hc.HORIZONS}, **{f"gas{k}": cg[f"gas{k}"] for k in hc.HORIZONS}}
        lat = float(r.lateral_ft)
        full = hc.predict(cums, lat, rm[a]["ref_mult"], r.f_oil, F)
        noF = hc.predict(cums, lat, rm[a]["ref_mult"], r.f_oil, None)
        # curve only: the as-built area mean curve at the area's own GOR level (no D30 shift, no factors, no F)
        cg0 = cache.setdefault((a, -2), hc.curve_cums(st["gas"]["curve"], _curve_gor12(st["gas"]["curve"])))
        raw = hc.predict({**{f"oil{k}": co[f"oil{k}"] for k in hc.HORIZONS}, **{f"gas{k}": cg0[f"gas{k}"] for k in hc.HORIZONS}}, lat, 1.0, 1.0, None)
        out.append({**{f"box_{k}": v for k, v in full.items()}, **{f"noF_{k}": v for k, v in noF.items()}, **{f"raw_{k}": v for k, v in raw.items()}})
    return pd.DataFrame(out, index=fr.index)


def _curve_gor12(curve: dict[str, Any]) -> float | None:
    g = curve.get("gas_ratio")
    f = curve["fits"]["oil"].get(curve["record"])
    if not g or not f:
        return None
    ov = tc.monthly_volumes(f)
    return tc.window_gor(ov, tc.ratio_monthly_volumes(ov, float(g["alpha"]), float(g["beta"])), 12)


# ----------------------------------------------------------------------------
# Run
# ----------------------------------------------------------------------------


def run(conn: Any, wells_dir: Path, out: Path, engine_sha: str, workers: int | None = None, asof: dt.date = PROD_ASOF) -> dict[str, Any]:
    out.mkdir(parents=True, exist_ok=True)
    s5b = json.loads((STEP5B / "summary.json").read_text(encoding="utf-8"))
    if s5b["boxfit_sha"] != engine_sha:
        raise RuntimeError(f"installed blueox-boxfit {engine_sha[:7]} != the 5b record's {s5b['boxfit_sha'][:7]}")
    (cliff,), = rep._read(conn, _CLIFF_SQL, {"r": REPORT, "b": BASIN})
    if asof >= cliff + dt.timedelta(days=366):
        raise RuntimeError(f"production as-of {asof} is too far past the {REPORT} cliff {cliff}")
    wells, excluded = exclusions.drop(egr.load_final_sets(wells_dir, (POOL,)))
    # ---- step 4 at the cutoff
    ar = rebuild_areas(conn, wells, asof)
    geoms = ar["geoms"]
    rec_areas = rep.pull_areas(conn)
    ov = area_overlap(geoms, rec_areas["geoms"])
    # ---- step 5b at the cutoff
    cb = rebuild_curves(conn, wells, ar, cliff, asof, workers)
    # ---- steps 5c/5d at the cutoff
    fx = rebuild_factors(conn, cb, wells, wells_dir, asof, workers)
    tabs = {s: trr.factor_table(fx["rf"], POOL, s) for s in ("oil", "gas")}
    wca = fx["frames"][POOL].reset_index(drop=True)
    rm = ref_mults(cb, wca, tabs["oil"])
    # ---- D36 F(k) on the training cohort (actuals at the cutoff; prediction without F)
    trn = wca.join(well_factors(wca, tabs))
    trn["lateral_ft"] = pd.to_numeric(trn["lateral_ft"], errors="coerce")
    trn = trn[(trn["lateral_ft"] > 0) & trn["area_no"].notna()].copy()
    trn["area_no"] = trn["area_no"].astype(int)
    trn["gor_target"] = trn["gor_local"] * trn["f_gor"]
    tp = predict_frame(trn, cb, rm, None)
    Fk = hc.calendar_factor(trn, tp.rename(columns={f"box_{s}{k}": f"{s}{k}" for s in hc.SCORED_STREAMS for k in hc.HORIZONS}))
    F = {s: {k: Fk[s][k]["F"] for k in hc.HORIZONS} for s in hc.SCORED_STREAMS}
    # ---- holdout
    hold = pull_holdout(conn, wells)
    hw = hold.merge(wells[["api10", "well_name", "operator", "formation_blueox", "lateral_length_ft", "mid_lon", "mid_lat", "tvd_ft", "first_production_date"]], on="api10", how="left")
    hx, hy = dfr._xy(hw["mid_lon"], hw["mid_lat"])
    hw["area_no"] = rep.assign_area(np.column_stack([hx, hy]), geoms)
    hw["lateral_ft"] = pd.to_numeric(hw["lateral_length_ft"], errors="coerce").where(lambda v: v > 0, hw["drilled_ll_ft"])
    n_hold_all = len(hw)
    hw = hw[(hw["area_no"] > 0) & (hw["lateral_ft"] > 0)].reset_index(drop=True)
    hw["bench_pool"] = POOL
    hs, hrep = dfr.attach_scenario(conn, hw)
    hs["infill"] = hs["infill"].astype(object).where(hs["infill"].notna(), False).astype(bool)
    hs["own_bench_in_pool"] = hs["own_bench_in_pool"].astype(bool)
    hs["gor_local"] = local_gor(wca, np.column_stack(dfr._xy(hs["mid_lon"], hs["mid_lat"])))
    hs["gor12"] = np.nan  # unknown at the cutoff
    hs = trr.add_pooled_view(hs)
    hs = hs.join(well_factors(hs, tabs))
    hs["gor_target"] = hs["gor_local"] * hs["f_gor"]
    hs = hs.join(predict_frame(hs, cb, rm, F))
    for s in hc.SCORED_STREAMS:
        for k in hc.HORIZONS:
            for v in ("box", "noF", "raw"):
                hs[f"{v}_err_{s}{k}"] = hc.pct_error(hs[f"actual_{s}{k}"], hs[f"{v}_{s}{k}"])
    direct = hs[hs["tier"] == "direct"]
    ver = hc.verdict(direct)
    # ---- tables
    area_tab = []
    for s in hc.SCORED_STREAMS:
        for k in hc.HORIZONS:
            g = hc.score_groups(direct, "area_no", s, k)
            g["qualifies"] = g["n"] >= hc.MIN_AREA_WELLS
            area_tab.append(g)
    area_tab = pd.concat(area_tab, ignore_index=True).rename(columns={"group": "area_no"})
    decomp = decomposition(direct, hs)
    by_class = class_table(direct)
    curves_tab = curve_table(cb, rm, ov)
    built = dt.datetime.now(tz=dt.UTC).astimezone().isoformat(timespec="seconds")
    summ = {
        "built_at": built, "engine_sha": engine_sha, "report": REPORT, "basin": BASIN, "cliff": str(cliff), "prod_asof": str(asof),
        "extent_id": ar["extent"]["extent_id"], "n_excluded": len(excluded),
        "areas": {"k": len(geoms), "pick": ar["r"]["pick"], "n_cohort": int(ar["frame"]["c12"].sum()), "record_k": len(rec_areas["geoms"]),
                  "cv_r2_pick": float(ar["r"]["cv"]["cv"].loc[ar["r"]["cv"]["cv"].k == ar["r"]["pick"]["k_1se"], "r2"].iloc[0]),
                  "median_share_in_one_record_area": float(ov["share_in_record_area"].median()), "median_iou": float(ov["iou"].median())},
        "curves": {"n_fitted": cb["n_fitted"], "rungs": {s: {str(r_): int(n) for r_, n in pd.Series([c["streams"][s]["rung"] for c in cb["curves"].values()]).value_counts().sort_index().items()} for s in tc.STREAMS},
                   "oil_eur_kft": _dist(curves_tab["oil_eur_kft"]), "oil_di_nominal": _dist(curves_tab["oil_Di_nominal"]), "oil_di_eff": _dist(curves_tab["oil_Di_eff_1yr"]),
                   "max_abs_reconcile": float(np.nanmax(np.abs(cb["rows"]["reconcile"].astype(float))))},
        "factors": {"n_est": fx["n_est"], "replication": fx["repl"], "bs2s": fx["bs2s"],
                    "infill": {s: float(tabs[s][("pair", "infill")]) for s in ("oil", "gas")},
                    "ref_mult_oil": _dist(pd.Series([v["ref_mult"] for v in rm.values()]))},
        "F": Fk,
        "holdout": {"n_sql43_in_gate1": n_hold_all, "n_in_areas": len(hs), "by_tier": hs["tier"].value_counts().to_dict(), "replication": hrep,
                    "n_scenario_unscored": int((~hs["scenario_scored"]).sum()),
                    "n_scored_direct": {f"{s}{k}": int((np.isfinite(direct[f"box_err_{s}{k}"]) & np.isfinite(direct[f"novi_err_{s}{k}"])).sum()) for s in hc.SCORED_STREAMS for k in hc.HORIZONS},
                    "box_only_all_tiers": {f"{s}{k}": hc.stats(hs[f"box_err_{s}{k}"]) for s in hc.SCORED_STREAMS for k in hc.HORIZONS}},
        "verdict": ver,
    }
    ctx = {"summary": summ, "area_tab": area_tab, "decomp": decomp, "by_class": by_class, "curves": curves_tab, "rf": fx["rf"], "overlap": ov,
           "map": map_png(geoms, ar["extent"]["geom_ft"], hs), "hist": hist_png(direct)}
    (out / "acceptance.html").write_text(render_page(ctx), encoding="utf-8")
    keep = ["api10", "well_name", "operator", "tier", "formation_blueox", "sql43_bench", "first_production_date", "area_no", "lateral_ft", "drilled_ll_ft", "novi_ll_ft",
            "view_class", "p_class", "p_parent", "p_infill", "scenario_scored", "f_oil", "f_gor", "gor_local", "gor_target"]
    keep += [f"{p}{s}{k}" for s in hc.SCORED_STREAMS for k in hc.HORIZONS for p in ("actual_", "box_", "novi_fcst_", "box_err_", "novi_err_", "noF_err_", "raw_err_")]
    hs[keep].sort_values(["area_no", "api10"]).to_csv(out / "holdout_scores.csv", index=False)
    area_tab.to_csv(out / "area_scores.csv", index=False)
    curves_tab.to_csv(out / "curves_hindcast.csv", index=False)
    cb["rows"].to_csv(out / "curve_rows_hindcast.csv", index=False)
    fx["rf"].assign(params=fx["rf"]["params"].map(json.dumps)).to_csv(out / "risk_factor_hindcast.csv", index=False)
    decomp.to_csv(out / "decomposition.csv", index=False)
    by_class.to_csv(out / "by_class.csv", index=False)
    ov.to_csv(out / "area_overlap.csv", index=False)
    feats = [{"type": "Feature", "properties": {"area_no": i}, "geometry": shapely.geometry.mapping(shapely.set_precision(g, 1e-6))}
             for i, g in enumerate(eg.to_lonlat(geoms), start=1)]
    (out / "areas_hindcast_WCA.geojson").write_text(json.dumps({"type": "FeatureCollection", "crs_note": "EPSG:4326", "features": feats}), encoding="utf-8")
    (out / "summary.json").write_text(json.dumps(rep._clean(summ), indent=2, default=rep._json), encoding="utf-8")
    return {"summary": summ, "holdout": hs, "area_tab": area_tab, "decomp": decomp}


def _dist(v: pd.Series) -> dict[str, float]:
    v = pd.to_numeric(v, errors="coerce").dropna()
    return {"median": float(v.median()), "min": float(v.min()), "max": float(v.max()), "n": len(v)} if len(v) else {}


# ----------------------------------------------------------------------------
# Diagnostics
# ----------------------------------------------------------------------------


def decomposition(direct: pd.DataFrame, allh: pd.DataFrame) -> pd.DataFrame:
    """Bench-level bias / band by prediction layer: area mean curve only -> + ref_mult, factors, D30 level
    -> + F(k) (= BOX of record); Novi on the same wells; BOX of record on every holdout tier."""
    rows = []
    for s in hc.SCORED_STREAMS:
        for k in hc.HORIZONS:
            ok = np.isfinite(direct[f"box_err_{s}{k}"]) & np.isfinite(direct[f"novi_err_{s}{k}"])
            d = direct[ok]
            for lab, col in (("1 area mean curve x lateral", "raw"), ("2 + ref_mult, scenario factors, local GOR", "noF"), ("3 + F(k) = BOX of record", "box")):
                rows.append({"stream": s, "horizon": k, "layer": lab, "wells": "Novi-matched (direct)", **hc.stats(d[f"{col}_err_{s}{k}"])})
            rows.append({"stream": s, "horizon": k, "layer": "Novi 2025Q3 (per-ft, sql/43)", "wells": "Novi-matched (direct)", **hc.stats(d[f"novi_err_{s}{k}"])})
            rows.append({"stream": s, "horizon": k, "layer": "3 BOX of record", "wells": "every holdout well (direct + unmatched)", **hc.stats(allh[f"box_err_{s}{k}"])})
    return pd.DataFrame(rows)


def class_table(direct: pd.DataFrame) -> pd.DataFrame:
    """Oil cum-6 bias by scenario class (pooled view) and infill, BOX vs Novi, Novi-matched wells."""
    d = direct.copy()
    d["scenario"] = d["p_class"].fillna("(unscored)") + np.where(d["p_infill"].astype(bool), " + infill", "")
    rows = []
    for k in hc.HORIZONS:
        ok = np.isfinite(d[f"box_err_oil{k}"]) & np.isfinite(d[f"novi_err_oil{k}"])
        for g, x in d[ok].groupby("scenario"):
            b, n = hc.stats(x[f"box_err_oil{k}"]), hc.stats(x[f"novi_err_oil{k}"])
            rows.append({"horizon": k, "scenario": g, "n": b["n"], "f_oil_median": float(x["f_oil"].median()), "box_bias": b["bias"], "box_band": b["band"],
                         "novi_bias": n["bias"], "novi_band": n["band"]})
    return pd.DataFrame(rows)


def curve_table(cb: dict[str, Any], rm: dict[int, dict[str, Any]], ov: pd.DataFrame) -> pd.DataFrame:
    rows = cb["rows"]
    rec = rows[rows["record"].astype(bool)]
    out = []
    for a in sorted(cb["curves"]):
        r = rec[rec.area_no == a]
        o = r[r.stream == "oil"].iloc[0]
        g = r[r.stream == "gas"].iloc[0]
        st = cb["curves"][a]["streams"]
        out.append({"area_no": a, "record_area": int(ov.loc[ov.area_no == a, "record_area"].iloc[0]), "rung_oil": st["oil"]["rung"], "rung_gas": st["gas"]["rung"],
                    "n_oil": int(o["n_wells"]), "oil_eur_kft": o["eur_per_kft"], "oil_qi_kft": o["qi"], "oil_Di_nominal": o["Di_nominal"], "oil_Di_eff_1yr": o["Di_eff_1yr"],
                    "oil_b": o["b"], "oil_cum6_kft": o["cum6_kft"], "oil_cum12_kft": o["cum12_kft"], "gas_gor12": g.get("gor12_scf_bbl"),
                    "ref_mult_oil": rm[a]["ref_mult"], "reconcile_oil": o["reconcile"]})
    return pd.DataFrame(out)


# ----------------------------------------------------------------------------
# Figures + page
# ----------------------------------------------------------------------------


def map_png(geoms: list[Any], extent_ft: Any, hs: pd.DataFrame) -> str:
    fig, ax = plt.subplots(figsize=(10, 11))
    for g in [extent_ft]:
        for p in getattr(g, "geoms", [g]):
            ax.plot(*p.exterior.xy, color="#111827", lw=1.2)
    for i, g in enumerate(geoms, start=1):
        for p in getattr(g, "geoms", [g]):
            ax.plot(*p.exterior.xy, color="#9ca3af", lw=0.6)
        c = g.representative_point()
        ax.text(c.x, c.y, str(i), fontsize=7, color="#6b7280", ha="center")
    x, y = dfr._xy(hs["mid_lon"], hs["mid_lat"])
    e = hs["box_err_oil6"].to_numpy(float)
    has = np.isfinite(e)
    ax.scatter(x[~has], y[~has], s=5, c="#d1d5db", label="holdout, no cum-6 yet")
    sc = ax.scatter(x[has], y[has], s=np.where(hs["tier"].to_numpy()[has] == "direct", 22, 9), c=np.clip(e[has], -0.5, 0.5), cmap="RdBu", vmin=-0.5, vmax=0.5,
                    edgecolors=np.where(hs["tier"].to_numpy()[has] == "direct", "#111827", "none"), linewidths=0.4)
    fig.colorbar(sc, ax=ax, shrink=0.5, label="BOX oil cum-6 error = actual / BOX − 1 (blue = BOX low, red = BOX high)")
    ax.set_aspect("equal")
    ax.set_xticks([])
    ax.set_yticks([])
    ax.set_title("Hindcast TC areas (cutoff data) + 2025Q3 holdout wells; outlined dots = Novi-matched (scored vs Novi)", fontsize=10)
    ax.legend(loc="lower left", fontsize=8)
    return _png(fig)


def hist_png(direct: pd.DataFrame) -> str:
    fig, axs = plt.subplots(1, 4, figsize=(17, 3.6))
    bins = np.linspace(-1.0, 1.5, 51)
    for ax, (s, k) in zip(axs, [(s, k) for s in hc.SCORED_STREAMS for k in hc.HORIZONS], strict=True):
        ok = np.isfinite(direct[f"box_err_{s}{k}"]) & np.isfinite(direct[f"novi_err_{s}{k}"])
        for col, colr, lab in ((f"novi_err_{s}{k}", "#9ca3af", "Novi"), (f"box_err_{s}{k}", "#2563eb", "BOX")):
            v = direct.loc[ok, col].astype(float).clip(-1, 1.5)
            ax.hist(v, bins=bins, alpha=0.55, color=colr, label=f"{lab}: bias {v.mean():+.1%}")
        ax.axvline(0, color="#111827", lw=0.8)
        ax.set_title(f"{s} cum-{k}, n = {int(ok.sum())}", fontsize=10)
        ax.set_xlabel("actual / forecast − 1")
        ax.legend(fontsize=8)
    fig.tight_layout()
    return _png(fig)


def _pct(v: Any) -> str:
    return "–" if v is None or (isinstance(v, float) and not math.isfinite(v)) else f"{v:+.1%}"


def render_page(ctx: dict[str, Any]) -> str:
    s = ctx["summary"]
    v = s["verdict"]
    cls = {"PASS": "ok", "FAIL": "bad", "INCONCLUSIVE": ""}
    cells = []
    for c in v["cells"]:
        a, b = c["area"], c["bench"]
        cells.append({"stream": c["stream"], "horizon": f"cum-{c['horizon']}",
                      "area test (D48: count majority)": f"{a['verdict']} — {a['n_pass']}/{a['n_qualifying']} qualifying areas pass {a['qualifying']} ({a['n_wells_qualifying']} wells; {a['n_wells_thin']} in thin areas)",
                      "bench test (all matched wells)": f"{b['verdict']} — n {int(b['n'])}: BOX bias {_pct(b['box_bias'])} band {b['box_band']:.2f} vs Novi bias {_pct(b['novi_bias'])} band {b['novi_band']:.2f}"})
    F = s["F"]
    h = s["holdout"]
    ar = s["areas"]
    pct_cols = [c for c in ctx["area_tab"].columns if c.endswith(("bias", "median", "p10_high", "p90_low"))]
    p = [
        "<!doctype html><html><head><meta charset=utf-8><meta name=viewport content='width=device-width,initial-scale=1'><title>BOX hindcast acceptance</title>",
        f"<style>{_CSS} body{{overflow-x:hidden}} table{{display:block;overflow-x:auto;max-width:100%}}</style></head><body>",
        "<h1>BOX step 6 — hindcast vs Novi 2025Q3 (acceptance)</h1>",
        (f"<div class=meta>built {s['built_at']} · Delaware WCA (WCA_1 + WCA_2 pooled, WCXY one-way; D19/D20/D33) · Novi report {s['report']} (cliff {s['cliff']}) · "
         f"BOX rebuilt from wells first-producing before {s['cliff']} with production through {s['prod_asof']} · extent of record {s['extent_id']} (same extent, plan) · "
         f"blueox-boxfit @ {s['engine_sha'][:7]} · read-only, nothing stored</div>"),
        (f"<div class='flag {cls[v['overall']]}'><b>Verdict: {v['overall']}</b> (oil {v['by_stream']['oil']}, gas {v['by_stream']['gas']}). "
        "§8 per cell: |BOX bias| ≤ 10 % and |BOX bias| &lt; |Novi bias|, and BOX P10–P90 band ≤ Novi's; area test passes on a strict majority of areas with ≥ 10 matched wells "
        "(by area count, D48); the bench test pools every matched well (D48); BOX passes only if every cell passes, oil AND gas (D49).</div>"),
        _table(pd.DataFrame(cells), {}),
        ("<div class=meta>Error = actual / forecast − 1 (sql/43 sign: positive = the forecast was LOW). Bias = mean error over wells. Band = P10 − P90 of the errors, P10 = HIGH (90th percentile). "
        "Novi errors are sql/43's per-ft errors (its stick lateral vs the drilled lateral); BOX predicts at the drilled lateral, so its error is per-ft by construction. "
        "Actuals for both = sql/43 cum at months-on-production k (calendar months, partial first month), newest reported month excluded.</div>"),
        "<h2>1. Error distributions, Novi-matched holdout wells</h2>", f"<img src='{ctx['hist']}'>",
        "<h2>2. Layer decomposition (bench level)</h2>",
        ("<div class=meta>1 = the hindcast area's as-built cohort-MEAN curve (D32) × lateral, gas at the area's own GOR; 2 = + D43 ref_mult, the well's scenario factor "
         "(D41/D42/D45; standalone allowed for an actual well, D44) and the D30 local GOR level × D46 GOR factor; 3 = + D36 calendar factor F(k) = BOX of record. "
         f"F(k) on the training cohort (n wells): oil cum-6 {F['oil'][6]['F']:.3f} ({F['oil'][6]['n']:,}), cum-12 {F['oil'][12]['F']:.3f} ({F['oil'][12]['n']:,}); "
         f"gas cum-6 {F['gas'][6]['F']:.3f} ({F['gas'][6]['n']:,}), cum-12 {F['gas'][12]['F']:.3f} ({F['gas'][12]['n']:,}).</div>"),
        _table(ctx["decomp"], {c: "+.1%" for c in ("bias", "median", "p10_high", "p90_low")} | {"band": ".2f"}),
        "<h2>3. Per hindcast area (Novi-matched wells)</h2>",
        f"<img src='{ctx['map']}'>",
        _table(ctx["area_tab"].sort_values(["stream", "horizon", "n"], ascending=[False, True, False]), {c: "+.1%" for c in pct_cols} | {"box_band": ".2f", "novi_band": ".2f"}),
        "<h2>4. By development scenario (oil, Novi-matched wells)</h2>",
        _table(ctx["by_class"], {"box_bias": "+.1%", "novi_bias": "+.1%", "box_band": ".2f", "novi_band": ".2f", "f_oil_median": ".3f"}),
        "<h2>5. What was rebuilt at the cutoff</h2>",
        (f"<div class=meta>Step 4: {ar['n_cohort']:,} D9 cohort wells (12 full months by {s['prod_asof']}) → the D29 method picks <b>k = {ar['k']}</b> "
         f"(CV min {ar['pick']['k_min']}; held-out R² {ar['cv_r2_pick']:.2f}) vs {ar['record_k']} areas of record; a hindcast area's median share inside one record area "
         f"{ar['median_share_in_one_record_area']:.0%}, median IoU {ar['median_iou']:.2f}. Step 5b: {s['curves']['n_fitted']:,} wells fitted; curve rungs oil {s['curves']['rungs']['oil']}, "
         f"gas {s['curves']['rungs']['gas']}; area oil EUR/kft median {s['curves']['oil_eur_kft']['median']:,.0f} bbl ({s['curves']['oil_eur_kft']['min']:,.0f}–{s['curves']['oil_eur_kft']['max']:,.0f}); "
         f"oil Di nominal median {s['curves']['oil_di_nominal']['median']:.2f}/yr = {s['curves']['oil_di_eff']['median']:.0%} 1-yr effective; "
         f"rule 6 worst |Σ months − stored| {s['curves']['max_abs_reconcile']:.1e}. Steps 5c/5d: estimation wells WCA {s['factors']['n_est']['WCA']:,} / BS2_S {s['factors']['n_est']['BS2_S']:,}; "
         f"infill oil {s['factors']['infill']['oil']:.3f}, GOR {s['factors']['infill']['gas']:.3f}; ref_mult oil median {s['factors']['ref_mult_oil']['median']:.3f} "
         f"({s['factors']['ref_mult_oil']['min']:.3f}–{s['factors']['ref_mult_oil']['max']:.3f}).</div>"),
        (f"<div class=meta>Holdout: {h['n_sql43_in_gate1']:,} sql/43 {s['report']} holdout wells in the gate-1 WCA set; {h['n_in_areas']:,} inside a hindcast area with a lateral "
         f"({h['by_tier']}); scenario unscored (no sql/50 row or warehouse bench outside the pool → reference) {h['n_scenario_unscored']}. "
         f"Scored vs Novi: {h['n_scored_direct']}.</div>"),
        "<h3>Hindcast area curves (record statistic = cohort MEAN per 1,000 ft, D32; Di nominal per year, 1-yr effective alongside; EUR = raw 50-yr integral)</h3>",
        _table(ctx["curves"], {"oil_eur_kft": ",.0f", "oil_qi_kft": ",.1f", "oil_Di_nominal": ".2f", "oil_Di_eff_1yr": ".0%", "oil_b": ".2f", "oil_cum6_kft": ",.0f",
                               "oil_cum12_kft": ",.0f", "gas_gor12": ",.0f", "ref_mult_oil": ".3f", "reconcile_oil": ".1e"}),
        "<h3>Risk factors re-estimated at the cutoff (WCA pairs, after the D45 ladder)</h3>",
        _table(trr.factor_view(ctx["rf"], POOL, "pair"), {"n blocks": ".0f"}),
        "<h2>6. What carries post-cutoff information (stated, not removed)</h2>",
        ("<ul><li>Extent of record (plan: same extents) — built from ≥ 2016 laterals through 2026-10.</li>"
         "<li>Gate-1 bench assignments (frozen record) — consensus neighbourhoods include later wells.</li>"
         "<li>sql/50 scenario classes (live view) — a training well's class is fixed at its own first production, but co-development partners can be later wells.</li>"
         "<li>Production volumes before the cutoff as revised since (reporting revisions).</li></ul>"),
        "</body></html>",
    ]
    return "\n".join(p)
