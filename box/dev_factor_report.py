"""BOX step 5c — dev-scenario factors for WCA (and BS2_S as the pooling test): inputs, fits, page.

Read-only against the warehouse (session pooler, READ ONLY transactions):
  * WCA: the step-5b deliverable is the record — its strict D9 cohort (members_WCA.csv, area of record
    per well) and its per-well fits (well_fits_WCA.csv, blueox-boxfit @ the pinned SHA); actuals are
    re-cut from curated.production at the SAME as-of month (summary.json prod_asof);
  * BS2_S: the gate-1 final set minus exclusions.csv, D9 cohort flag, lateral midpoint inside the BS2_S
    extent of record, 12 full months by the same as-of; fitted here with the same engine (5b fit_wells);
  * curated.dev_scenario (sql/50) — scenario_class, has_same_bench_parent, bench_context. The class is
    recomputed from bench_context (box/dev_factor.classify) to know the nearest parent bench; the run
    refuses unless the recomputation matches the view on every well.

Nothing is written to the warehouse; box.risk_factor DDL is 5d.
"""

from __future__ import annotations

import datetime as dt
import json
from pathlib import Path
from typing import Any

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import shapely
from scipy.spatial import cKDTree

from box import dev_factor as dfm
from box import edge_gap as eg
from box import edge_gap_report as egr
from box import exclusions
from box import tc_curve as tc
from box import tc_curve_report as rep
from box.edge_gap_report import _CSS, _png, _table

BASIN = "delaware"
STEP5B = Path("docs") / "box" / "step5b-2026-10-10"
POOL_BENCHES: dict[str, tuple[str, ...]] = {"WCA": ("WCA_1", "WCA_2", "WCXY"), "BS2_S": ("BS2_S",)}
LOC_BLOCK_FT = 26_400.0  # 5-mi location blocks for a bench without TC areas (BS2_S) and the WCA robustness check
LOCAL_GOR_K = 15  # D30: median 12-mo GOR of the 15 nearest other cohort wells
N_BOOT = 400
CI = 0.90

# metric -> (stream, column, label); every factor is exp(beta) on ln(metric)
METRICS: dict[str, tuple[str, str, str]] = {
    "oil_qi": ("oil", "oil_qi_kft", "oil qi (per-well fit), bopd/kft"),
    "oil_cum6": ("oil", "oil6_kft", "oil cum-6, bbl/kft (actual)"),
    "oil_cum12": ("oil", "oil12_kft", "oil cum-12, bbl/kft (actual)"),
    "oil_cum24": ("oil", "oil24_kft", "oil cum-24, bbl/kft (actual)"),
    "oil_eur": ("oil", "oil_eur_kft", "oil EUR 50-yr, bbl/kft (per-well fit)"),
    "gas_cum12": ("gas", "gas12_kft", "gas cum-12, mcf/kft (actual)"),
    "gas_eur": ("gas", "gas_eur_kft", "gas EUR 50-yr, mcf/kft (per-well Arps fit)"),
    "gor12": ("gas", "gor12", "12-mo GOR, scf/bbl"),
    "gor12_vs_local": ("gas", "gor12_vs_local", "12-mo GOR / local level (D30: 15 nearest other cohort wells)"),
    "water_cum12": ("water", "water12_kft", "water cum-12, bbl/kft (actual)"),
    "water_eur": ("water", "water_eur_kft", "water EUR 50-yr, bbl/kft (per-well fit)"),
}

_DS_SQL = """
SELECT api10, bench, scenario_class, has_same_bench_parent, youngest_parent_age_days, nearest_parent_offset_ft, bench_context
FROM curated.dev_scenario WHERE api10 = ANY(%(api10s)s)
"""
_EXTENT_SQL = """
SELECT extent_id, version, extensions.ST_AsText(geom) FROM box.extent
WHERE basin = %(basin)s AND bench = %(bench)s AND is_record
"""


# ----------------------------------------------------------------------------
# Inputs
# ----------------------------------------------------------------------------


def _xy(lon: Any, lat: Any) -> tuple[np.ndarray, np.ndarray]:
    tr = eg._transformer()
    x, y = tr.transform(np.asarray(lon, float), np.asarray(lat, float))
    return np.asarray(x) * eg._M_TO_FT, np.asarray(y) * eg._M_TO_FT


def wca_frame(conn: Any, wells_dir: Path, asof: dt.date) -> pd.DataFrame:
    """The 5b strict cohort + its record per-well fits + actuals re-cut at the 5b as-of."""
    mem = pd.read_csv(STEP5B / "members_WCA.csv", dtype={"api10": str})
    wf = pd.read_csv(STEP5B / "well_fits_WCA.csv", dtype={"api10": str}).set_index("api10")
    wells = pd.read_csv(wells_dir / "wells_final_WCA.csv", dtype={"api10": str})[["api10", "mid_lon", "mid_lat", "tvd_ft"]]
    d = mem.merge(wells, on="api10", how="left")
    d["bench_pool"] = "WCA"
    d["loc"] = "a" + d["area_no"].astype(str)
    for s in tc.STREAMS:
        d[f"{s}_qi"] = d["api10"].map(wf[f"{s}_qi"])
        d[f"{s}_eur"] = d["api10"].map(wf[f"{s}_eur"])
    return _with_actuals(conn, d, asof)


def bs2s_frame(conn: Any, wells_dir: Path, asof: dt.date, workers: int | None) -> tuple[pd.DataFrame, dict[str, Any]]:
    """BS2_S D9 cohort inside the extent of record, 12 full months by `asof`, fitted with the 5b engine."""
    wells, excluded = exclusions.drop(egr.load_final_sets(wells_dir, ("BS2_S",)))
    rows = rep._read(conn, _EXTENT_SQL, {"basin": BASIN, "bench": "BS2_S"})
    if len(rows) != 1:
        raise RuntimeError(f"expected one BS2_S extent of record, found {len(rows)}")
    ext_id, ext_ver, wkt = rows[0]
    ext = shapely.from_wkt(wkt)
    inside = shapely.contains_xy(ext, wells["mid_lon"].to_numpy(float), wells["mid_lat"].to_numpy(float))
    lat = pd.to_numeric(wells["lateral_length_ft"], errors="coerce")
    cand = wells[wells["cohort"] & inside & (lat > 0)].copy()
    ids = sorted(cand["api10"])
    prod = rep.pull_production(conn, ids, asof)
    meta = rep.pull_meta(conn, ids)
    fits = rep.fit_wells(prod, meta, workers)
    d = cand.rename(columns={"lateral_length_ft": "lateral_ft"})[["api10", "well_name", "operator", "formation_blueox", "first_production_date", "lateral_ft", "mid_lon", "mid_lat", "tvd_ft"]].copy()
    d["first_production_date"] = d["first_production_date"].astype(str)
    d["bench_pool"] = "BS2_S"
    x, y = _xy(d["mid_lon"], d["mid_lat"])
    d["loc"] = "b" + pd.Series(dfm.blocks(x, y, LOC_BLOCK_FT), index=d.index).astype(str)
    d["area_no"] = np.nan
    for s in tc.STREAMS:
        d[f"fit_{s}"] = [bool((fits.get(a) or {}).get(s)) for a in d["api10"]]
        d[f"{s}_qi"] = [((fits.get(a) or {}).get(s) or {}).get("params", {}).get("qi", np.nan) for a in d["api10"]]
        d[f"{s}_eur"] = [((fits.get(a) or {}).get(s) or {}).get("eur", np.nan) for a in d["api10"]]
    d = _with_actuals(conn, d, asof, prod)
    d = d[d["months"].fillna(0) >= 12].reset_index(drop=True)
    meta_out = {"extent_id": int(ext_id), "extent_version": int(ext_ver), "n_excluded": len(excluded), "n_in_extent_cohort": len(cand), "n_full12": len(d)}
    return d, meta_out


def _with_actuals(conn: Any, d: pd.DataFrame, asof: dt.date, prod: pd.DataFrame | None = None) -> pd.DataFrame:
    if prod is None:
        prod = rep.pull_production(conn, sorted(d["api10"]), asof)
    act = rep.actuals(prod, asof)
    act = act[[c for c in act.columns if not c.startswith("rates_")]]
    keep = [c for c in d.columns if c not in act.columns or c == "api10"]
    d = d[keep].merge(act, on="api10", how="left")
    lat = pd.to_numeric(d["lateral_ft"], errors="coerce")
    for s in tc.STREAMS:
        for k in (6, 12, 24):
            d[f"{s}{k}_kft"] = d[f"{s}{k}"] / lat * 1000.0
        d[f"{s}_qi_kft"] = d[f"{s}_qi"] / lat * 1000.0
        d[f"{s}_eur_kft"] = d[f"{s}_eur"] / lat * 1000.0
    d["fpy"] = d["first_production_date"].astype(str).str[:4]
    return d


def attach_scenario(conn: Any, d: pd.DataFrame) -> tuple[pd.DataFrame, dict[str, Any]]:
    """dev_scenario per well + the recomputed class / nearest parent benches; refuses on any mismatch."""
    ds = pd.DataFrame(rep._read(conn, _DS_SQL, {"api10s": sorted(d["api10"])}),
                      columns=["api10", "ds_bench", "view_class", "view_infill", "youngest_parent_age_days", "nearest_parent_offset_ft", "bench_context"])
    d = d.merge(ds, on="api10", how="left")
    cl = pd.DataFrame([dfm.classify(b, c) if isinstance(c, dict) and pd.notna(vc) else dfm.classify("", None)
                       for b, c, vc in zip(d["ds_bench"], d["bench_context"], d["view_class"], strict=True)], index=d.index)
    d = d.join(cl)
    scored = d["view_class"].notna()
    mism = scored & ((d["scenario_class"] != d["view_class"]) | (d["infill"].astype(object) != d["view_infill"].astype(object)))
    if int(mism.sum()):
        raise RuntimeError(f"sql/50 replication failed on {int(mism.sum())} wells, e.g. {list(d.loc[mism, 'api10'][:5])}")
    d["parent_bench"] = [dfm.parent_bench(c, b, a) for c, b, a in zip(d["scenario_class"], d["parent_below"], d["parent_above"], strict=True)]
    d["own_bench_in_pool"] = [b in POOL_BENCHES[p] for b, p in zip(d["ds_bench"], d["bench_pool"], strict=True)]
    d = d.drop(columns=["bench_context"])
    return d, {"n": len(d), "n_unscored": int((~scored).sum()), "n_replicated": int(scored.sum()), "n_mismatch": 0,
               "n_own_bench_outside_pool": int((scored & ~d["own_bench_in_pool"]).sum())}


def add_local_gor(d: pd.DataFrame) -> pd.DataFrame:
    """D30 local level: median 12-mo GOR of the 15 nearest OTHER cohort wells of the same bench pool."""
    d = d.copy()
    d["gor_local"] = np.nan
    for _, g in d.groupby("bench_pool"):
        ok = g["gor12"].gt(0) & g["mid_lon"].notna()
        gg = g[ok]
        x, y = _xy(gg["mid_lon"], gg["mid_lat"])
        xy = np.column_stack([x, y])
        _, j = cKDTree(xy).query(xy, k=LOCAL_GOR_K + 1)
        d.loc[gg.index, "gor_local"] = np.median(gg["gor12"].to_numpy(float)[j[:, 1:]], axis=1)
    d["gor12_vs_local"] = d["gor12"] / d["gor_local"]
    return d


# ----------------------------------------------------------------------------
# Factor runs
# ----------------------------------------------------------------------------


def _ln(v: pd.Series) -> pd.Series:
    v = pd.to_numeric(v, errors="coerce")
    return pd.Series(np.where(v > 0, np.log(v.where(v > 0)), np.nan), index=v.index)


def est_frame(d: pd.DataFrame) -> pd.DataFrame:
    """Rows that identify factors: scored, own warehouse bench inside the pool (a consensus-moved well's
    sql/50 relations are computed on its old bench), real lateral."""
    e = d[d["view_class"].notna() & d["own_bench_in_pool"] & (pd.to_numeric(d["lateral_ft"], errors="coerce") > 0)].copy()
    x, y = _xy(e["mid_lon"], e["mid_lat"])
    e["cluster"] = dfm.blocks(x, y, dfm.BLOCK_FT)
    e["loc_block"] = dfm.blocks(x, y, LOC_BLOCK_FT)
    return e.reset_index(drop=True)


def run_metric(e: pd.DataFrame, metric: str, pair: pd.Series, infill: pd.Series | None, fes: list[pd.Series], n_boot: int, keep_draws: bool = False,
               estimator: str = "ols", terms: pd.DataFrame | None = None) -> pd.DataFrame:
    col = METRICS[metric][1]
    t = dfm.term_frame(pair, infill) if terms is None else terms
    v = pd.to_numeric(e[col], errors="coerce")
    y = _ln(v) if estimator == "ols" else v.where(v > 0)
    out = dfm.estimate(y, t, fes, cluster=e["cluster"].to_numpy(), n_boot=n_boot, ci=CI, estimator=estimator)
    if not keep_draws:
        out.attrs.pop("draws", None)
    out.insert(0, "metric", metric)
    out.insert(1, "stream", METRICS[metric][0])
    return out


def bench_factors(e: pd.DataFrame, bench: str, n_boot: int) -> dict[str, Any]:
    pair = dfm.pair_labels(e["scenario_class"], e["parent_bench"])
    infill = e["infill"].astype(bool)
    fes = [e["loc"], e["fpy"]]
    record = pd.concat([run_metric(e, m, pair, infill, fes, n_boot) for m in METRICS], ignore_index=True)
    record.insert(0, "bench", bench)
    # BOX pooled-bench view (D19 / D33): same-pool vertical parents read as lateral infill
    p2, i2 = dfm.pool_view(pair, infill, POOL_BENCHES[bench])
    pooled = pd.concat([run_metric(e, m, p2, i2, fes, n_boot) for m in ("oil_cum12", "oil_eur", "gas_cum12", "water_cum12")], ignore_index=True)
    pooled.insert(0, "bench", bench)
    # selection-bias ladder (point estimates)
    op = e["operator"].where(e["operator"].isin(e["operator"].value_counts().index[:25]), "other")
    specs = {"raw (no controls)": [], "location FE": [e["loc"]], "location + vintage FE (record)": fes,
             "+ operator FE (top 25)": [*fes, op], "5-mi block FE + vintage (location robustness)": [e["loc_block"], e["fpy"]]}
    sel = []
    for name, f in specs.items():
        for m in ("oil_cum12", "oil_eur"):
            r = run_metric(e, m, pair, infill, f, 0)
            r.insert(0, "spec", name)
            sel.append(r)
    sel_df = pd.concat(sel, ignore_index=True)
    sel_df.insert(0, "bench", bench)
    # shape: same wells (24 months) for cum-6 / 12 / 24 / EUR, identical bootstrap draws
    s24 = e[e["oil24_kft"].gt(0) & e["oil6_kft"].gt(0) & e["oil_eur_kft"].gt(0) & e["oil_qi_kft"].gt(0)].reset_index(drop=True)
    pr24 = dfm.pair_labels(s24["scenario_class"], s24["parent_bench"])
    sh = {}
    for m in ("oil_qi", "oil_cum6", "oil_cum12", "oil_cum24", "oil_eur"):
        sh[m] = run_metric(s24, m, pr24, s24["infill"].astype(bool), [s24["loc"], s24["fpy"]], n_boot, keep_draws=True)
    shape = sh["oil_cum12"][["metric", "term", "n_wells"]].copy()
    for m, r in sh.items():
        shape[f"f_{m}"] = r["factor"].to_numpy()
    d_eur, d_12 = sh["oil_eur"].attrs["draws"], sh["oil_cum12"].attrs["draws"]
    rr = np.exp(d_eur - d_12)
    shape["eur_over_cum12"] = shape["f_oil_eur"] / shape["f_oil_cum12"]
    with np.errstate(all="ignore"):
        shape["eur_over_cum12_lo"] = np.nanquantile(rr, (1 - CI) / 2, axis=0)
        shape["eur_over_cum12_hi"] = np.nanquantile(rr, 1 - (1 - CI) / 2, axis=0)
    shape.insert(0, "bench", bench)
    shape.attrs = {}
    # mean-ratio check (D32: the curve is a MEAN; log-OLS is a geometric-mean ratio)
    mr = pd.concat([run_metric(e, m, pair, infill, fes, n_boot, estimator="ppml") for m in ("oil_cum12", "oil_eur", "gas_cum12", "water_cum12")], ignore_index=True)
    mr.insert(0, "bench", bench)
    # depletion-time diagnostic (youngest parent's age at the subject's first production)
    at = dfm.age_terms(pair, infill, pd.to_numeric(e["youngest_parent_age_days"], errors="coerce"), pd.to_numeric(e["infill_parent_age_days"], errors="coerce"))
    age = pd.concat([run_metric(e, m, pair, None, fes, n_boot, terms=at) for m in ("oil_cum12", "oil_eur")], ignore_index=True)
    age.insert(0, "bench", bench)
    return {"record": record, "pooled_view": pooled, "selection": sel_df, "shape": shape.drop(columns="metric"), "mean_ratio": mr, "age": age, "n_est": len(e), "n24": len(s24)}


LADDER_METRICS = ("oil_cum12", "oil_eur", "gas_cum12", "water_cum12")


def ladders(benches: dict[str, dict[str, Any]], pooling: pd.DataFrame, min_n: int = 30) -> pd.DataFrame:
    """Proposed factor of record per bench x metric x pair (dfm.factor_ladder), with the record-view
    pair estimate beside it."""
    out = []
    for b, bf in benches.items():
        for m in LADDER_METRICS:
            r = bf["record"][bf["record"].metric == m]
            pl = pooling[pooling.metric == m]
            cb = {t: (f, n) for t, f, n in zip(pl.term, pl[b], pl[f"n_{b}"], strict=True)}
            cp = {t: (f, n1 + n2) for t, f, n1, n2 in zip(pl.term, pl.pooled, pl.n_WCA, pl.n_BS2_S, strict=True)}
            lad = dfm.factor_ladder(r[["term", "factor", "n_wells"]], cb, cp, min_n)
            lad.insert(0, "metric", m)
            lad.insert(0, "bench", b)
            lad["pair_estimate"] = r["factor"].to_numpy()
            lad["pair_n"] = r["n_wells"].to_numpy()
            out.append(lad)
    return pd.concat(out, ignore_index=True)


def class_pooling(es: dict[str, pd.DataFrame], n_boot: int) -> pd.DataFrame:
    """Per-bench vs per-basin-across-benches (D11): class-level terms (parent bench collapsed) on the
    stacked WCA + BS2_S frame. Pooled = one factor per class; interacted = class x BS2_S terms give the
    BS2_S / WCA ratio with a joint cluster bootstrap (the benches share ground)."""
    st = pd.concat([e.assign(_b=b) for b, e in es.items()], ignore_index=True)
    cls = st["scenario_class"]
    base = dfm.term_frame(cls, st["infill"].astype(bool))
    is_b = (st["_b"] == "BS2_S").astype(float).to_numpy()
    inter = base.mul(is_b, axis=0).add_suffix("*BS2_S")
    fes = [st["_b"] + ":" + st["loc"], st["_b"] + ":" + st["fpy"]]
    rows = []
    for m in ("oil_cum12", "oil_eur", "gas_cum12", "water_cum12", "gor12_vs_local"):
        y = _ln(st[METRICS[m][1]])
        pooled = dfm.estimate(y, base, fes, cluster=st["cluster"].to_numpy(), n_boot=n_boot, ci=CI)
        full = dfm.estimate(y, pd.concat([base, inter], axis=1), fes, cluster=st["cluster"].to_numpy(), n_boot=n_boot, ci=CI)
        dr = full.attrs.pop("draws")
        pooled.attrs.pop("draws", None)
        k = base.shape[1]
        for i, term in enumerate(base.columns):
            wca_d, bs_d, ratio_d = dr[:, i], dr[:, i] + dr[:, k + i], dr[:, k + i]
            q = lambda v: (float(np.exp(np.nanquantile(v, (1 - CI) / 2))), float(np.exp(np.nanquantile(v, 1 - (1 - CI) / 2))))
            rows.append({"metric": m, "term": term, "pooled": float(pooled.loc[i, "factor"]), "pooled_lo": float(pooled.loc[i, "ci_lo"]), "pooled_hi": float(pooled.loc[i, "ci_hi"]),
                         "WCA": float(full.loc[i, "factor"]), "WCA_lo": q(wca_d)[0], "WCA_hi": q(wca_d)[1],
                         "BS2_S": float(full.loc[i, "factor"] * full.loc[k + i, "factor"]), "BS2_S_lo": q(bs_d)[0], "BS2_S_hi": q(bs_d)[1],
                         "BS2_S_over_WCA": float(full.loc[k + i, "factor"]), "ratio_lo": q(ratio_d)[0], "ratio_hi": q(ratio_d)[1],
                         "n_WCA": int(full.loc[i, "n_wells"] - full.loc[k + i, "n_wells"]), "n_BS2_S": int(full.loc[k + i, "n_wells"])})
    return pd.DataFrame(rows)


def area_normalisation(d: pd.DataFrame, record: pd.DataFrame) -> pd.DataFrame:
    """Per WCA area: class mix of the strict cohort and the multiplier from the as-built (mixed) mean
    curve to the reference-scenario curve, with the EUR factors (weights = per-well EUR/kft) and the
    cum-12 factors (weights = actual cum-12/kft)."""
    areas = pd.read_csv(STEP5B / "areas_WCA.csv")
    tab = {m: dict(zip(record.loc[record.metric == m, "term"], record.loc[record.metric == m, "factor"], strict=True)) for m in ("oil_eur", "oil_cum12")}
    w = d[d["fit_oil"].astype(bool)].copy()
    w["pair"] = dfm.pair_labels(w["scenario_class"].fillna(dfm.REFERENCE), w["parent_bench"])
    # pair labels absent from the estimation (e.g. a moved-bench well's rare pair) fall back to the class's 'other'
    for m, tm in tab.items():
        w[f"f_{m}"] = [dfm.factor_of(p if p in tm or p == dfm.REFERENCE or "|" not in p else p.split("|")[0] + "|other", bool(i), tm)
                       for p, i in zip(w["pair"], w["infill"].fillna(False), strict=True)]
    rows = []
    for a, g in w.groupby("area_no"):
        ar = areas[areas.area_no == a].iloc[0]
        m_eur = dfm.normalisation_multiplier(g["oil_eur_kft"], g["f_oil_eur"])
        m_12 = dfm.normalisation_multiplier(g["oil12_kft"], g["f_oil_cum12"])
        vc = g["scenario_class"].value_counts(normalize=True)
        rows.append({"area_no": int(a), "n": len(g), "codev_stack": vc.get("codev_stack", 0.0), "standalone": vc.get("standalone", 0.0),
                     "topfill": vc.get("topfill", 0.0), "underfill": vc.get("underfill", 0.0), "sandwich": vc.get("sandwich", 0.0),
                     "infill": float(g["infill"].fillna(False).mean()), "record_oil_eur_kft": float(ar.oil_eur_kft),
                     "mult_eur": m_eur, "ref_oil_eur_kft": float(ar.oil_eur_kft) * m_eur, "mult_cum12": m_12})
    return pd.DataFrame(rows)


# ----------------------------------------------------------------------------
# Page
# ----------------------------------------------------------------------------


def forest_png(record: pd.DataFrame, bench: str) -> str:
    r = record[record.metric.isin(["oil_cum12", "oil_eur", "gas_cum12", "water_cum12"])]
    terms = list(dict.fromkeys(r.loc[r.metric == "oil_cum12", "term"]))
    fig, ax = plt.subplots(figsize=(9.5, 0.42 * len(terms) + 1.2))
    off = {"oil_cum12": -0.27, "oil_eur": -0.09, "gas_cum12": 0.09, "water_cum12": 0.27}
    col = {"oil_cum12": "#15803d", "oil_eur": "#86efac", "gas_cum12": "#dc2626", "water_cum12": "#2563eb"}
    for m, o in off.items():
        s = r[r.metric == m].set_index("term").reindex(terms)
        yv = np.arange(len(terms)) + o
        ax.errorbar(s["factor"], yv, xerr=[s["factor"] - s["ci_lo"], s["ci_hi"] - s["factor"]], fmt="o", ms=4, color=col[m], lw=1.2, label=METRICS[m][2])
    ax.axvline(1, color="#6b7280", lw=0.8)
    lab = [f"{t}  (n {int(r.loc[(r.metric == 'oil_cum12') & (r.term == t), 'n_wells'].iloc[0])})" for t in terms]
    ax.set_yticks(range(len(terms)), lab, fontsize=8)
    ax.invert_yaxis()
    ax.set_xlabel(f"factor vs reference (codev_stack, no same-bench parent); {int(CI * 100)} % cluster-bootstrap CI")
    ax.set_title(f"{bench}: dev-scenario factors (location + vintage FE)", fontsize=10)
    ax.legend(fontsize=7, loc="lower right")
    ax.grid(alpha=0.3, axis="x")
    fig.tight_layout()
    return _png(fig)


def _fac_table(r: pd.DataFrame, metrics: list[str]) -> pd.DataFrame:
    terms = list(dict.fromkeys(r.loc[r.metric == metrics[0], "term"]))
    out = pd.DataFrame({"term": terms})
    s0 = r[r.metric == metrics[0]].set_index("term")
    out["n_wells"] = s0.reindex(terms)["n_wells"].to_numpy()
    if "n_clusters" in s0:
        out["n_blocks"] = s0.reindex(terms)["n_clusters"].to_numpy()
    for m in metrics:
        s = r[r.metric == m].set_index("term").reindex(terms)
        out[m] = [f"{f:.3f} [{lo:.2f}–{hi:.2f}]" if np.isfinite(f) and "ci_lo" in s and np.isfinite(lo) else (f"{f:.3f}" if np.isfinite(f) else "–")
                  for f, lo, hi in zip(s["factor"], s.get("ci_lo", s["factor"]), s.get("ci_hi", s["factor"]), strict=True)]
    return out


def _sel_wide(sel: pd.DataFrame) -> pd.DataFrame:
    """term x '<metric>: <spec>' factor grid."""
    out = pd.DataFrame({"term": list(dict.fromkeys(sel["term"]))})
    for m in dict.fromkeys(sel["metric"]):
        for sp in dict.fromkeys(sel["spec"]):
            s = sel[(sel.metric == m) & (sel.spec == sp)].set_index("term")["factor"]
            out[f"{m}: {sp}"] = out["term"].map(s).to_numpy()
    return out


def render_page(ctx: dict[str, Any]) -> str:
    s = ctx["summary"]
    parts = [
        "<!doctype html><html><head><meta charset=utf-8><meta name=viewport content='width=device-width,initial-scale=1'><title>Dev-scenario factors</title>",
        f"<style>{_CSS} body{{overflow-x:hidden}} table{{display:block;overflow-x:auto;max-width:100%}} img{{max-width:100%}}</style></head><body>",
        "<h1>BOX step 5c — development-scenario factors, Delaware WCA (pilot) + BS2_S (pooling test)</h1>",
        (f"<div class=meta>built {s['built_at']} · WCA = the step-5b record cohort ({s['benches']['WCA']['n_cohort']:,} wells) and per-well fits (blueox-boxfit @ {s['boxfit_sha'][:7]}); "
         f"BS2_S = D9 cohort inside extent {s['bs2s']['extent_id']} with 12 months ({s['benches']['BS2_S']['n_cohort']:,} wells), fitted with the same engine; production through {s['prod_asof']}; "
         f"scenario = curated.dev_scenario (sql/50), recomputed from bench_context and matched on every scored well ({s['replication']['WCA']['n_replicated'] + s['replication']['BS2_S']['n_replicated']:,} / 0 mismatches) · read-only</div>"),
        ("<div class='flag'>Factor = exp(β) from ln(metric) = location FE (WCA: TC area of record; BS2_S: 5-mi block) + first-prod-year FE + β·(scenario, parent bench) + γ·same-bench parent. "
         "Reference = <b>codev_stack with no same-bench parent</b>. Pairs with &lt; 10 wells pool to '&lt;class&gt;|other'; sandwich pools to 'sandwich|all'. 'infill' = has_same_bench_parent (lateral infill: an older same-bench well inside the co-extent rule), "
         f"estimated as its own multiplicative term. CI = {int(CI * 100)} % percentile cluster bootstrap over 3-mi blocks ({N_BOOT} draws). n_wells = subject wells carrying the term (= n_pairs). "
         "Per 1,000 ft of lateral; actual cums are calendar months from first report; qi / EUR are the per-well anduin fits (EUR = raw 50-yr integral). Factors are multiplicative and combine (pair × infill).</div>"),
    ]
    for b in ("WCA", "BS2_S"):
        bf = ctx["benches"][b]
        parts += [
            f"<h2>{b} — factors of record view (sql/50 classes, parent bench matched)</h2>",
            f"<div class=meta>{bf['n_est']:,} wells identify the factors (scored, own warehouse bench inside the {b} pool: {', '.join(POOL_BENCHES[b])}).</div>",
            f"<img src='{ctx['forest'][b]}'>",
            _table(_fac_table(bf["record"], ["oil_cum12", "oil_cum6", "oil_qi", "oil_eur"]), {}),
            "<div class=meta>Gas, GOR and water (same model):</div>",
            _table(_fac_table(bf["record"], ["gas_cum12", "gas_eur", "gor12", "gor12_vs_local", "water_cum12", "water_eur"]), {}),
            f"<h3>{b} — BOX pooled-bench view: same-pool vertical parents ({', '.join(POOL_BENCHES[b])}) read as lateral infill</h3>",
            _table(_fac_table(bf["pooled_view"], ["oil_cum12", "gas_cum12", "water_cum12"]), {}),
            f"<h3>{b} — selection-bias ladder (oil, point estimates)</h3>",
            _table(_sel_wide(bf["selection"]), {c: ".3f" for c in _sel_wide(bf["selection"]).columns if c != "term"}),
            f"<h3>{b} — shape: same {bf['n24']:,} wells with 24 months</h3>",
            "<div class=meta>If a factor is a pure level shift, f_eur ≈ f_cum12 ≈ f_cum24 (apply on qi or EUR, same answer). eur_over_cum12 &lt; 1 = the class declines steeper than the reference after year 1.</div>",
            f"<h3>{b} — mean-ratio check (Poisson PML on levels; D32 curves are means)</h3>",
            "<div class=meta>Same model, estimated as a ratio of arithmetic means. If it matches the log-OLS (geometric) factor, the choice of estimator doesn't matter for applying a factor to a mean curve.</div>",
            _table(_fac_table(bf["mean_ratio"], ["oil_cum12", "oil_eur", "gas_cum12", "water_cum12"]), {}),
            f"<h3>{b} — depletion time: youngest parent's age at the subject's first production</h3>",
            "<div class=meta>Vertical classes by the youngest vertical parent (sql/50 youngest_parent_age_days); infill by the youngest same-bench parent. A future PUD's PDP parents are old (mostly ≥ 3 yr).</div>",
            _table(_fac_table(bf["age"], ["oil_cum12", "oil_eur"]), {}),
            f"<h3>{b} — shape detail</h3>",
            _table(bf["shape"], {"f_oil_qi": ".3f", "f_oil_cum6": ".3f", "f_oil_cum12": ".3f", "f_oil_cum24": ".3f", "f_oil_eur": ".3f", "eur_over_cum12": ".3f", "eur_over_cum12_lo": ".3f", "eur_over_cum12_hi": ".3f"}),
        ]
    fm = {c: ".3f" for c in ctx["pooling"].columns if c not in ("metric", "term", "n_WCA", "n_BS2_S")}
    parts += [
        "<h2>Per-bench vs per-basin pooling (D11)</h2>",
        "<div class=meta>Class-level terms (parent bench collapsed) on the stacked WCA + BS2_S frame; location and vintage FE per bench; joint cluster bootstrap. BS2_S_over_WCA CI excluding 1 = the benches differ.</div>",
        _table(ctx["pooling"], fm),
        "<h2>Proposed factor of record (ladder, stamped)</h2>",
        "<div class=meta>Rung 1 = the (class, parent bench) pair when it has ≥ 30 subject wells; rung 2 = the class within the bench; rung 3 = the class pooled across WCA + BS2_S. pair_estimate is shown beside it for every pair.</div>",
        _table(ctx["ladder"], {"factor": ".3f", "pair_estimate": ".3f"}),
        "<h2>WCA area normalisation to the reference scenario</h2>",
        "<div class=meta>Reference curve = record (mixed-cohort mean) curve × mult (a uniform scale: qi scales, Di / b unchanged). mult_eur uses the oil EUR factors with per-well EUR weights; mult_cum12 the cum-12 factors with actual cum-12 weights.</div>",
        _table(ctx["norm"], {"codev_stack": ".0%", "standalone": ".0%", "topfill": ".0%", "underfill": ".0%", "sandwich": ".0%", "infill": ".0%", "record_oil_eur_kft": ",.0f", "mult_eur": ".3f", "ref_oil_eur_kft": ",.0f", "mult_cum12": ".3f"}),
        "</body></html>",
    ]
    return "\n".join(parts)


# ----------------------------------------------------------------------------
# Orchestration
# ----------------------------------------------------------------------------


def run(conn: Any, wells_dir: Path, out: Path, boxfit_sha: str, workers: int | None = None, n_boot: int = N_BOOT) -> dict[str, Any]:
    out.mkdir(parents=True, exist_ok=True)
    s5b = json.loads((STEP5B / "summary.json").read_text(encoding="utf-8"))
    asof = dt.date.fromisoformat(s5b["prod_asof"])
    if s5b["boxfit_sha"] != boxfit_sha:
        raise RuntimeError(f"installed blueox-boxfit {boxfit_sha[:7]} != the 5b record's {s5b['boxfit_sha'][:7]} (BS2_S would be fitted with a different engine)")
    wca = wca_frame(conn, wells_dir, asof)
    # identity: re-cut 12-mo oil equals the 5b record's oil12_kft
    drift = (wca["oil12_kft"] / pd.read_csv(STEP5B / "members_WCA.csv", dtype={"api10": str}).set_index("api10").reindex(wca["api10"])["oil12_kft"].to_numpy() - 1).abs()
    bs, bs_meta = bs2s_frame(conn, wells_dir, asof, workers)
    frames, repl = {}, {}
    for b, d in (("WCA", wca), ("BS2_S", bs)):
        d2, r = attach_scenario(conn, d)
        frames[b], repl[b] = add_local_gor(d2), r
    es = {b: est_frame(d) for b, d in frames.items()}
    benches = {b: bench_factors(es[b], b, n_boot) for b in es}
    pooling = class_pooling(es, n_boot)
    lad = ladders(benches, pooling)
    norm = area_normalisation(frames["WCA"], benches["WCA"]["record"])
    built = dt.datetime.now(tz=dt.UTC).astimezone().isoformat(timespec="seconds")
    summ: dict[str, Any] = {
        "built_at": built, "prod_asof": str(asof), "boxfit_sha": boxfit_sha, "n_boot": n_boot, "ci": CI, "reference": dfm.REFERENCE,
        "min_pair_wells": dfm.MIN_PAIR_WELLS, "cluster_block_ft": dfm.BLOCK_FT, "loc_block_ft": LOC_BLOCK_FT, "bs2s": bs_meta, "replication": repl,
        "wca_oil12_recut_vs_5b": {"share_within_0.1pct": float((drift < 1e-3).mean()), "max_abs": float(drift.max())},
        "benches": {b: {"n_cohort": len(frames[b]), "n_est": benches[b]["n_est"], "n24": benches[b]["n24"],
                        "class_mix": frames[b]["view_class"].value_counts(dropna=False).rename(index=lambda k: str(k)).to_dict(),
                        "infill_share": float(frames[b]["infill"].fillna(False).mean())} for b in frames},
        "norm_mult_eur": {"median": float(norm["mult_eur"].median()), "min": float(norm["mult_eur"].min()), "max": float(norm["mult_eur"].max())},
        "norm_mult_cum12": {"median": float(norm["mult_cum12"].median()), "min": float(norm["mult_cum12"].min()), "max": float(norm["mult_cum12"].max())},
    }
    ctx = {"summary": summ, "benches": benches, "pooling": pooling, "norm": norm, "ladder": lad, "forest": {b: forest_png(benches[b]["record"], b) for b in benches}}
    (out / "factors.html").write_text(render_page(ctx), encoding="utf-8")
    # risk_factor-shaped table (plan §4.2) for the record view
    rf = []
    for b, bf in benches.items():
        r = bf["record"].copy()
        r["basin"] = BASIN
        r["dev_scenario"] = [t.split("|")[0] if t != "infill" else "infill" for t in r["term"]]
        r["parent_bench"] = [t.split("|")[1] if "|" in t else (b if t == "infill" else None) for t in r["term"]]
        rf.append(r.rename(columns={"n_wells": "n_pairs"}))
    pd.concat(rf, ignore_index=True)[["basin", "bench", "stream", "metric", "dev_scenario", "parent_bench", "term", "factor", "ci_lo", "ci_hi", "n_pairs", "n_clusters", "boot_ok"]].to_csv(out / "factors.csv", index=False)
    pd.concat([bf["pooled_view"] for bf in benches.values()]).to_csv(out / "factors_pooled_view.csv", index=False)
    pd.concat([bf["selection"] for bf in benches.values()]).to_csv(out / "selection_ladder.csv", index=False)
    pd.concat([bf["shape"] for bf in benches.values()]).to_csv(out / "shape.csv", index=False)
    pooling.to_csv(out / "pooling.csv", index=False)
    lad.to_csv(out / "ladder.csv", index=False)
    pd.concat([bf["mean_ratio"] for bf in benches.values()]).to_csv(out / "factors_mean_ratio.csv", index=False)
    pd.concat([bf["age"] for bf in benches.values()]).to_csv(out / "parent_age.csv", index=False)
    norm.to_csv(out / "normalisation_WCA.csv", index=False)
    cols = ["bench_pool", "api10", "well_name", "operator", "area_no", "loc", "first_production_date", "lateral_ft", "ds_bench", "own_bench_in_pool", "view_class", "parent_below",
            "parent_above", "parent_bench", "infill", "youngest_parent_age_days", "infill_parent_age_days", "oil_qi_kft", "oil6_kft", "oil12_kft", "oil24_kft", "oil_eur_kft", "gas12_kft", "gas_eur_kft",
            "gor12", "gor_local", "water12_kft", "water_eur_kft"]
    pd.concat([frames[b][cols] for b in frames]).to_csv(out / "wells.csv", index=False)
    (out / "summary.json").write_text(json.dumps(rep._clean(summ), indent=2, default=rep._json), encoding="utf-8")
    return {"summary": summ, "benches": benches, "pooling": pooling, "norm": norm, "ladder": lad, "frames": frames}
