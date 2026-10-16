"""BOX acceptance of record (D53, Michael 2026-10-13) — package-level, Novi-agnostic, against a local-offsets benchmark,
with the D52 spatial holdout kept out of every tuning view.

Folds: rolling-origin cutoffs Dec 1 2019 … 2024 (box/backtest_report.run_fold: rebuild areas, curves, factors, F(k) from
wells first-producing before the cutoff, production through the month before it; score the next 12 months' gate-1 WCA wells).
Horizons cum-12 / 24 / 36 / 48 (cum-48 only where the data reach it — the 2019 / 2020 folds — to see whether the drift
compounds into EUR).

Grain = development PACKAGE: scored WCA wells linked as co-developed co-extent neighbours (first production within 180 d,
overlap >= 30 % — rule 9 / sql/47) on the 3-D spacing pairs (box/spacing3d; = curated.well_neighbors, sql/59), as
connected components; a lone well is a package of one. Package error = sum actual / sum predicted - 1 over its members that
reached the horizon. Bias = mean over packages; band = P10 - P90 over packages (P10 = high).

Benchmark = an engineer's quick look (backtest_report.local_offsets): median per-1,000-ft cum-k of the 15 nearest pre-cutoff
cohort wells whose cum-k was known at the cutoff, x lateral. Novi stays an exhibit (step-6 hindcast).

Verdict (D53): for the BOX model of record, each (fold, stream, horizon) cell with >= MIN_PACKAGES packages passes when
|package bias| <= 10 % AND BOX's package band <= the benchmark's + 0.05 (amendment 2026-10-13); BOX passes when every judged cell passes, oil AND gas.

Holdout (D52): a package is HELD OUT when any member's lateral midpoint lies in a holdout block (box/holdout). Held-out
packages are dropped BEFORE any statistic is computed and nothing about their errors is written; only their counts are.
`score_holdout=True` is the one-time final scoring after the model spec is frozen.

Benches (step 9a, plan Phase 2): `bench` picks a BENCH_SPECS entry - the well set (gate-1 / D84 file + tag filter), the
scored targets, the extent of record and the deal-intake bench label. `fold="full"` is the step-6 fold (TC areas, curves,
factors - WCA only: the lat / base context variants need them); `fold="analog"` is the analog-only fold every bench uses
(backtest_report.run_fold_analog) - it produces the v2 variants only (di_p50, box_v2 and their walk-forward forms).
"""

from __future__ import annotations

import datetime as dt
import json
from collections.abc import Iterable, Mapping, Sequence
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from box import analog as an
from box import backtest_report as br
from box import edge_gap_report as egr
from box import exclusions
from box import hindcast as hc
from box import spacing3d as s3
from box import spacing3d_report as s3r
from box import tc_area_report as tar
from box import tc_curve_report as rep
from box.edge_gap_report import _CSS, _table

CUTOFFS: tuple[dt.date, ...] = tuple(dt.date(y, 12, 1) for y in range(2019, 2025))
HORIZONS: tuple[int, ...] = (12, 24, 36, 48)
K_MONTHS = 48
STREAMS = ("oil", "gas")
RECORD = "lat"  # BOX model of record after D50 (Cui lateral efficiency)
REPORTED = ("base", "lat", "lat+s3d", *an.VARIANTS)
F_SAMPLE = 500  # training wells for each analog variant's F(k) (leave-self-out cohorts), seeded
SEED = 20261013
BIAS_TOL = 0.10
BAND_TOL = 0.05  # D53 amendment (Michael 2026-10-13): BOX band may exceed the benchmark's by this much (sampling noise)
MIN_PACKAGES = 30
PACKAGE_OVERLAP = 0.30
PACKAGE_CODEV_DAYS = s3.CODEV_DAYS

BENCH_SPECS: dict[str, dict[str, Any]] = {
    # wells = the wells_final_<file>.csv set; pool_tags / target_tags filter it on the warehouse tag (formation_blueox)
    # (None = every row); extent = the box.extent bench of record; label = the deal-intake bench passed to selection.
    "WCA": {"wells": "WCA", "pool_tags": None, "target_tags": None, "extent": "WCA", "label": "WCA",
            "desc": "Delaware WCA (WCA_1 + WCA_2 pooled, WCXY one-way; D19 / D20 / D33)"},
    "BS2_S": {"wells": "BS2_S", "pool_tags": None, "target_tags": None, "extent": "BS2_S", "label": "BS2_S",
              "desc": "Delaware BS2_S (gate-1 set + D84 refresh; extent of record 7)"},
    # D20: WCA_1 wells never count as WCXY evidence -> WCXY targets draw from WCXY-tagged wells only. No WCXY extent exists
    # (D20 forbids inferring one from WCA_1); the WCA extent of record is the frame here, pending gate-9a decision 3.
    "WCXY": {"wells": "WCA", "pool_tags": ("WCXY",), "target_tags": ("WCXY",), "extent": "WCA", "label": "WCXY",
             "desc": "Delaware WCXY targets, WCXY-tagged analogs only (D20), inside the WCA extent of record (no WCXY extent exists)"},
    # SENSITIVITY ONLY (not D20 as written): WCXY targets with the whole WCA pool as analogs - informs gate-9a decision 2.
    "WCXY_on_WCA": {"wells": "WCA", "pool_tags": None, "target_tags": ("WCXY",), "extent": "WCA", "label": "WCXY",
                    "desc": "SENSITIVITY: WCXY targets, analogs from the whole WCA pool (WCA_1 + WCA_2 + WCXY) - contradicts D20 as written"},
}


def bench_wells(wells_dir: Path, bench: str) -> tuple[pd.DataFrame, pd.DataFrame, set[str] | None]:
    """(pool wells after exclusions.csv, excluded rows, scored-target api10s or None = all) for a BENCH_SPECS entry."""
    spec = BENCH_SPECS[bench]
    wells, excluded = exclusions.drop(egr.load_final_sets(wells_dir, (spec["wells"],)))
    if spec["pool_tags"] is not None:
        wells = wells[wells["formation_blueox"].isin(spec["pool_tags"])].reset_index(drop=True)
    targets = None if spec["target_tags"] is None else set(wells.loc[wells["formation_blueox"].isin(spec["target_tags"]), "api10"])
    return wells, excluded, targets


# ----------------------------------------------------------------------------
# Pure pieces
# ----------------------------------------------------------------------------


def packages(ids: Sequence[str], pairs: Mapping[str, Iterable[s3.Pair]], min_overlap: float = PACKAGE_OVERLAP, codev_days: int = PACKAGE_CODEV_DAYS) -> dict[str, str]:
    """api10 -> package id (the smallest api10 in its connected component). Edges = co-developed (|dfp| <= codev_days)
    co-extent pairs (overlap >= min_overlap in EITHER direction) between two wells of `ids`."""
    idset = set(ids)
    parent = {a: a for a in ids}

    def find(a: str) -> str:
        while parent[a] != a:
            parent[a] = parent[parent[a]]
            a = parent[a]
        return a

    for a in ids:
        for p in pairs.get(a, ()):
            if p.nbr in idset and abs(p.dfp_days) <= codev_days and p.overlap >= min_overlap:
                ra, rb = find(a), find(p.nbr)
                if ra != rb:
                    parent[max(ra, rb)] = min(ra, rb)
    return {a: find(a) for a in ids}


def package_errors(df: pd.DataFrame, pkg: str, actual: str, pred: str) -> pd.DataFrame:
    """Per package: members with both values, sum actual / sum predicted - 1."""
    ok = np.isfinite(df[actual].astype(float)) & np.isfinite(df[pred].astype(float)) & (df[pred].astype(float) > 0)
    g = df[ok].groupby(pkg).agg(n=(actual, "size"), a=(actual, "sum"), p=(pred, "sum"))
    g["err"] = g["a"] / g["p"] - 1.0
    return g.reset_index()


SCALE_FREE = True  # D58 (Michael 2026-10-14): spreads compared scale-free — band of (actual / forecast) / its mean


def scale_free(band: float, bias: float) -> float:
    """P10–P90 of actual / forecast divided by its mean (1 + bias): removes the 1 / (1 + h) widening a haircut causes and
    the compression a high-biased forecast enjoys, so a corrected forecast is not penalised for being corrected."""
    return band / (1.0 + bias) if np.isfinite(band) and np.isfinite(bias) and bias > -1 else float("nan")


def judge_cell(box: Mapping[str, float], bench: Mapping[str, float], n_pkg: int, tol: float = BIAS_TOL, min_pkg: int = MIN_PACKAGES,
               band_tol: float = BAND_TOL, scale_free_band: bool = SCALE_FREE) -> str:
    if n_pkg < min_pkg or not np.isfinite(box["bias"]):
        return "not judged"
    if scale_free_band:
        bb, rb = scale_free(box["band"], box["bias"]), scale_free(bench["band"], bench.get("bias", float("nan")))
    else:
        bb, rb = box["band"], bench["band"]
    ok = abs(box["bias"]) <= tol and (not np.isfinite(rb) or bb <= rb + band_tol)
    return "PASS" if ok else "FAIL"


def verdict(cells: pd.DataFrame, variant: str = RECORD) -> dict[str, Any]:
    """Overall: every judged cell of `variant` passes, oil AND gas."""
    rec = cells[cells["variant"] == variant]
    judged = rec[rec["verdict"] != "not judged"]
    by_stream = {s: ("PASS" if (judged[judged.stream == s]["verdict"] == "PASS").all() and (judged.stream == s).any() else "FAIL") for s in STREAMS}
    overall = "PASS" if all(v == "PASS" for v in by_stream.values()) else "FAIL"
    return {"overall": overall, "by_stream": by_stream, "n_judged": len(judged), "n_failed": int((judged["verdict"] == "FAIL").sum())}


# ----------------------------------------------------------------------------
# Run
# ----------------------------------------------------------------------------


def add_analog_predictions(view: pd.DataFrame, f: dict[str, Any], cutoff: dt.date, workers: int | None) -> pd.DataFrame:
    """D54 candidate: analog cohort per scored well (box/analog), each variant calibrated by its own F(k) from a seeded
    training sample with leave-self-out cohorts; writes pred_<variant>_<stream><k> and <variant>_err_<stream><k>."""
    cb, trn, t_act = f["cb"], f["trn"], f["t_act"]
    f_oil = dict(zip(trn["api10"], trn["f_oil"], strict=True))
    pool = an.build_pool(cb["frame"], cb["fits"], f["sp"], f_oil)
    xy_v = np.column_stack(br.dfr._xy(view["mid_lon"], view["mid_lat"]))
    xy_t = np.column_stack(br.dfr._xy(trn["mid_lon"], trn["mid_lat"]))

    def locs(df: pd.DataFrame, xy: np.ndarray) -> list[dict[str, Any]]:
        # fp_max: analogs must have first produced BEFORE the location (holdout: all pool wells are pre-cutoff anyway;
        # training sample: excludes later wells, so F(k) is calibrated under the same as-of rule the holdout is predicted under)
        return [{"api10": r.api10, "x": xy[i, 0], "y": xy[i, 1], "lateral_ft": float(r.lateral_ft), "spacing_ft": r.spacing_ft,
                 "gor_local": r.gor_local, "f_oil": r.f_oil, "f_gor": r.f_gor, "fp_max": pd.Timestamp(r.first_production_date).date()} for i, r in enumerate(df.itertuples())]

    rng = np.random.default_rng(SEED)
    ti = np.sort(rng.choice(len(trn), size=min(F_SAMPLE, len(trn)), replace=False))
    pv = an.predict_many(locs(view, xy_v), pool, cutoff, K_MONTHS, workers)
    pt = an.predict_many(locs(trn.iloc[ti].reset_index(drop=True), xy_t[ti]), pool, cutoff, K_MONTHS, workers)
    mv, mt = an.monthly_arrays(pv, K_MONTHS), an.monthly_arrays(pt, K_MONTHS)
    for v in an.VARIANTS:
        for s in STREAMS:
            F, _ = hc.calendar_factor_curve(t_act[s][ti], mt[v][s])
            pred = np.cumsum(mv[v][s], axis=1) * F[None, :]
            for k in HORIZONS:
                if f"actual_{s}{k}" not in view:
                    continue
                view[f"pred_{v}_{s}{k}"] = pred[:, k - 1]
                view[f"{v}_err_{s}{k}"] = hc.pct_error(view[f"actual_{s}{k}"].to_numpy(float), pred[:, k - 1])
    prov = pd.DataFrame([{k_: p.get(k_) for k_ in ("api10", "radius_mi", "n_analogs", "flags", "recent_radius_mi", "recent_n", "recent_fallback", "ref_mult")} for p in pv])
    return prov


REPORTED_V2 = ("lat", "di_p50", "di_p50_wf", "box_v2", "box_v2_wf")  # pre-registered 2026-10-14 (D57)
NON_WF_V2 = ("lat", "di_p50", "box_v2")
RECORD_V2 = "box_v2_wf"  # D58 FROZEN spec of record (2026-10-14)
WF_LOG: list[dict[str, Any]] = []


def add_analog_predictions_v2(conn: Any, view: pd.DataFrame, f: dict[str, Any], cutoff: dt.date, workers: int | None,
                              bench: str = an.BENCH, keep: dict[str, Any] | None = None) -> pd.DataFrame:
    """D57 run: di_p50 (raw laterals) and box_v2 (D56 completed laterals, D55 strike edges, short-lateral Cui translation),
    each calibrated by its own F(k) on a seeded training sample with as-of, leave-self-out cohorts. `bench` = the deal-intake
    bench label; `keep`, when given, receives the uptime-free box_v2 months per location and its F(k) per stream (step 9a)."""
    cb, trn, t_act = f["cb"], f["trn"], f["t_act"]
    f_oil = dict(zip(trn["api10"], trn["f_oil"], strict=True))
    pool = an.build_pool(cb["frame"], cb["fits"], f["sp"], f_oil)
    ut = an.uturn_leg_spacing(conn, sorted(set(pool["api10"]) | set(view["api10"]) | set(trn["api10"])))
    tvd = dict(zip(cb["frame"]["api10"], pd.to_numeric(cb["frame"]["tvd_ft"], errors="coerce"), strict=True))
    pool2 = an.with_completed_laterals(pool, ut, tvd)
    xy_v = np.column_stack(br.dfr._xy(view["mid_lon"], view["mid_lat"]))
    xy_t = np.column_stack(br.dfr._xy(trn["mid_lon"], trn["mid_lat"]))

    def locs(df: pd.DataFrame, xy: np.ndarray) -> list[dict[str, Any]]:
        return [{"api10": r.api10, "x": xy[i, 0], "y": xy[i, 1], "lateral_ft": float(r.lateral_ft),
                 "lateral_eff": an.completed_lateral(r.api10, float(r.lateral_ft), ut), "spacing_ft": r.spacing_ft,
                 "fp_max": pd.Timestamp(r.first_production_date).date()} for i, r in enumerate(df.itertuples())]

    rng = np.random.default_rng(SEED)
    ti = np.sort(rng.choice(len(trn), size=min(F_SAMPLE, len(trn)), replace=False))
    pv = an.predict_many_v2(locs(view, xy_v), pool, pool2, cutoff, K_MONTHS, workers, bench=bench)
    pt = an.predict_many_v2(locs(trn.iloc[ti].reset_index(drop=True), xy_t[ti]), pool, pool2, cutoff, K_MONTHS, workers, bench=bench)
    mv, mt = an.monthly_arrays_v2(pv, K_MONTHS), an.monthly_arrays_v2(pt, K_MONTHS)
    if keep is not None:
        keep.update({"api10": view["api10"].to_numpy(), "months": {s: mv["box_v2"][s] for s in STREAMS}, "F": {}})
    for v in an.VARIANTS_V2:
        for s in STREAMS:
            F, _ = hc.calendar_factor_curve(t_act[s][ti], mt[v][s])
            if keep is not None and v == "box_v2":
                keep["F"][s] = F
            pred = np.cumsum(mv[v][s], axis=1) * F[None, :]
            for k in HORIZONS:
                if f"actual_{s}{k}" not in view:
                    continue
                view[f"pred_{v}_{s}{k}"] = pred[:, k - 1]
                view[f"{v}_err_{s}{k}"] = hc.pct_error(view[f"actual_{s}{k}"].to_numpy(float), pred[:, k - 1])
    keys = ("api10", "radius_mi", "n_analogs", "flags", "v2_radius_mi", "v2_n", "v2_mode", "v2_short", "v2_uturn",
            "v2_strike_az_deg", "v2_strike_r2", "v2_strike_n", "v2_strike_dip_ft_mi")
    return pd.DataFrame([{k_: p.get(k_) for k_ in keys} for p in pv])


def apply_walk_forward(cells: pd.DataFrame, views: dict[str, pd.DataFrame], history: pd.DataFrame | None = None,
                       suffix: str = "_wf", log: list[dict[str, Any]] | None = None) -> list[pd.DataFrame]:
    """D57: <variant>_wf = prediction x (1 + mean package bias at the same horizon over >= 2 EARLIER cutoffs); cells for a
    cutoff without two earlier judged cutoffs are left unjudged (no prediction). `history` = the cells the haircuts come from
    (default: `cells` themselves); `suffix` names the corrected variants (step 9a: '_wf_wca' = WCA's haircuts on another
    bench); `log` = where the haircuts are logged (default: WF_LOG, cleared first)."""
    if log is None:
        WF_LOG.clear()
        log = WF_LOG
    out = []
    for c, view in sorted(views.items()):
        for base in ("di_p50", "box_v2"):
            for s in STREAMS:
                for k in HORIZONS:
                    col = f"pred_{base}_{s}{k}"
                    if col not in view:
                        continue
                    src = cells if history is None else history  # holdout scoring: haircuts from the TUNING packages only (D58)
                    hist = src[(src.variant == base) & (src.stream == s) & (src.horizon == k) & (src.n_packages >= MIN_PACKAGES)]
                    h = an.walk_forward(dict(zip(hist["cutoff"], hist["pkg_bias"], strict=True)), c)
                    log.append({"cutoff": c, "variant": base, "stream": s, "horizon": k, "haircut": h})
                    pred = view[col].to_numpy(float) * (1.0 + h) if h is not None else np.full(len(view), np.nan)
                    view[f"pred_{base}{suffix}_{s}{k}"] = pred
                    view[f"{base}{suffix}_err_{s}{k}"] = hc.pct_error(view[f"actual_{s}{k}"].to_numpy(float), pred)
        out.append(score_fold(view, c, (f"di_p50{suffix}", f"box_v2{suffix}")))
    return out


def score_fold(hs: pd.DataFrame, cutoff: str, variants: tuple[str, ...] = REPORTED) -> pd.DataFrame:
    rows = []
    for s in STREAMS:
        for k in HORIZONS:
            if f"actual_{s}{k}" not in hs:
                continue
            bp = package_errors(hs, "package", f"actual_{s}{k}", f"bench_{s}{k}")
            bstat = hc.stats(bp["err"])
            for v in variants:
                if f"pred_{v}_{s}{k}" not in hs:
                    continue
                pp = package_errors(hs, "package", f"actual_{s}{k}", f"pred_{v}_{s}{k}")
                st = hc.stats(pp["err"])
                wst = hc.stats(hs[f"{v}_err_{s}{k}"])
                rows.append({"cutoff": cutoff, "stream": s, "horizon": k, "variant": v, "n_packages": st["n"], "n_wells": int(pp["n"].sum()),
                             "pkg_bias": st["bias"], "pkg_median": st["median"], "pkg_band": st["band"],
                             "bench_bias": bstat["bias"], "bench_band": bstat["band"], "well_bias": wst["bias"], "well_band": wst["band"],
                             "verdict": judge_cell({"bias": st["bias"], "band": st["band"]}, {"band": bstat["band"], "bias": bstat["bias"]}, st["n"])})
    return pd.DataFrame(rows)


REPORTED_ANALOG = ("di_p50", "di_p50_wf", "box_v2", "box_v2_wf")  # what fold="analog" produces (no TC-area context variants)
VARIANTS_ANALOG_BASE = ("di_p50", "box_v2")
WCA_WF = "_wf_wca"  # step 9a: box_v2 / di_p50 corrected by WCA's walk-forward haircuts instead of the bench's own


def run(conn: Any, wells_dir: Path, out: Path, engine_sha: str, workers: int | None = None, cutoffs: tuple[dt.date, ...] = CUTOFFS,
        score_holdout: bool = False, mode: str = "v2", *, bench: str = "WCA", fold: str = "full", actuals_through: dt.date | None = None,
        history_path: Path | None = None, wca_history_path: Path | None = None, tag: str | None = None) -> dict[str, Any]:
    """`bench` / `fold`: see the module doc. `actuals_through` caps the live last full month (reproduce a scored record on later
    data). `history_path` = the tuning cells the holdout's walk-forward haircuts come from (default out / cells_tuning_v2.csv).
    `wca_history_path` (non-WCA benches): WCA's tuning cells, scored as the extra <base>_wf_wca variants (gate-9a decision 1)."""
    if fold not in ("full", "analog"):
        raise ValueError(fold)
    if fold == "full" and bench != "WCA":
        raise ValueError("fold='full' rebuilds WCA's TC areas / factors; other benches use fold='analog'")
    if fold == "analog" and mode != "v2":
        raise ValueError("fold='analog' produces the v2 variants only")
    spec = BENCH_SPECS[bench]
    variants = (REPORTED_V2 if fold == "full" else REPORTED_ANALOG) if mode == "v2" else REPORTED
    record = RECORD_V2 if mode == "v2" else RECORD
    out.mkdir(parents=True, exist_ok=True)
    wells, excluded, targets = bench_wells(wells_dir, bench)
    last = rep.last_full_month(rep._read(conn, rep._MONTHS_SQL))
    live_last = last
    if actuals_through is not None and actuals_through < last:
        last = actuals_through
    subj = wells[np.array([f >= dt.date(2016, 1, 1) for f in wells["first_production_date"]]) & (pd.to_numeric(wells["lateral_length_ft"], errors="coerce") > 0).to_numpy()]
    P = s3r.build_pairs(conn, subj.reset_index(drop=True))
    ext = tar.pull_extent(conn, spec["extent"]) if fold == "analog" else None
    cells, fold_meta, analog_prov, views, kept = [], [], [], {}, {}
    for c in cutoffs:
        if fold == "full":
            f = br.run_fold(conn, wells, wells_dir, c, workers, last, P, horizons=HORIZONS, k_months=K_MONTHS, keep_pred=True, return_internals=True)
        else:
            f = br.run_fold_analog(conn, wells, ext["geom_ft"], c, workers, last, horizons=HORIZONS, k_months=K_MONTHS, targets=targets, pool=bench)
        hs = f["hold"]
        hs["package"] = hs["api10"].map(packages(list(hs["api10"]), P["pairs"]))
        held = set(hs.loc[hs["holdout_block"], "package"])
        hs["package_held_out"] = hs["package"].isin(held)
        view = hs[hs["package_held_out"] == score_holdout].copy().reset_index(drop=True)  # tuning view excludes held-out packages entirely
        if mode == "v2":
            kept[str(c)] = {}
            aprov = add_analog_predictions_v2(conn, view, f, c, workers, bench=spec["label"], keep=kept[str(c)])
            cells.append(score_fold(view, str(c), NON_WF_V2 if fold == "full" else VARIANTS_ANALOG_BASE))
            views[str(c)] = view
        else:
            aprov = add_analog_predictions(view, f, c, workers)
            cells.append(score_fold(view, str(c)))
        analog_prov.append(aprov.assign(cutoff=str(c)))
        sizes = hs.drop_duplicates("package")["package"].map(hs["package"].value_counts())
        fold_meta.append({"cutoff": str(c), "asof": str(f["asof"]), "k_areas": f["k_areas"], "n_train": f["n_train"], "n_scored_wells": len(hs),
                          "n_packages": int(hs["package"].nunique()), "median_package_wells": float(sizes.median()) if len(sizes) else None,
                          "max_package_wells": int(sizes.max()) if len(sizes) else None,
                          "n_packages_held_out": len(held), "n_wells_held_out": int(hs["package_held_out"].sum()),
                          "n_factor_no_estimate": int(hs["factor_no_estimate"].sum()) if "factor_no_estimate" in hs else 0,
                          "F_oil_12_36": [f["F"][RECORD]["oil"][11], f["F"][RECORD]["oil"][35]] if f.get("F") else
                          [float(kept[str(c)]["F"]["oil"][11]), float(kept[str(c)]["F"]["oil"][35])] if kept.get(str(c)) else None})
    cells = pd.concat(cells, ignore_index=True)
    wf_wca_log: list[dict[str, Any]] = []
    if mode == "v2":
        history = None
        if score_holdout:
            history = pd.read_csv(history_path or out / "cells_tuning_v2.csv")
            history = history[history.variant.isin(NON_WF_V2)]
        cells = pd.concat([cells, *apply_walk_forward(cells, views, history)], ignore_index=True)
        if wca_history_path is not None:
            wh = pd.read_csv(wca_history_path)
            cells = pd.concat([cells, *apply_walk_forward(cells, views, wh[wh.variant.isin(NON_WF_V2)], suffix=WCA_WF, log=wf_wca_log)], ignore_index=True)
            variants = (*variants, f"di_p50{WCA_WF}", f"box_v2{WCA_WF}")
    prov = pd.concat(analog_prov, ignore_index=True)
    v = {var: verdict(cells, var) for var in variants}
    built = dt.datetime.now(tz=dt.UTC).astimezone().isoformat(timespec="seconds")
    summ = {"built_at": built, "engine_sha": engine_sha, "actuals_through": str(last), "live_last_full_month": str(live_last),
            "bench": bench, "bench_desc": spec["desc"], "fold": fold, "wells_dir": str(wells_dir), "n_pool_wells": len(wells),
            "n_targets": len(targets) if targets is not None else len(wells),
            "extent_id": ext["extent_id"] if ext else None,
            "view": "HOLDOUT (final scoring)" if score_holdout else "tuning (holdout excluded)",
            "record_variant": record, "variants": list(variants), "mode": mode, "bias_tol": BIAS_TOL, "band_tol": BAND_TOL, "min_packages": MIN_PACKAGES,
            "folds": fold_meta, "verdict": v[record],
            "verdict_by_variant": v, "n_excluded": len(excluded),
            "analog_radius_mi": {str(k_): int(n_) for k_, n_ in prov["radius_mi"].value_counts().sort_index().items()},
            "analog_recent_fallback_share": float(prov["recent_fallback"].mean()) if "recent_fallback" in prov else None,
            "v2_mode_counts": prov["v2_mode"].value_counts().to_dict() if "v2_mode" in prov else None,
            "v2_radius_mi": {str(k_): int(n_) for k_, n_ in prov["v2_radius_mi"].value_counts().sort_index().items()} if "v2_radius_mi" in prov else None,
            "v2_short_locations": int(prov["v2_short"].sum()) if "v2_short" in prov else None,
            "v2_uturn_locations": int(prov["v2_uturn"].sum()) if "v2_uturn" in prov else None,
            "walk_forward": WF_LOG, "walk_forward_wca": wf_wca_log}
    if tag is None:
        tag = ("holdout" if score_holdout else "tuning") + ("_v2" if mode == "v2" else "")
        if bench != "WCA" or fold != "full":
            tag += f"_{bench}_{fold}"
    if mode == "v2":
        for c_, view in views.items():  # per-location frame for the step-9a page (provenance + package + the scored columns)
            view.merge(prov[prov.cutoff == c_].drop(columns="cutoff"), on="api10", how="left").to_csv(out / f"view_{tag}_{c_[:4]}.csv.gz", index=False)
        arrays: dict[str, np.ndarray] = {}
        for c_, kk in kept.items():
            if kk:
                y = c_[:4]
                arrays.update({f"{y}_api10": kk["api10"].astype(str), f"{y}_oil": kk["months"]["oil"], f"{y}_gas": kk["months"]["gas"],
                               f"{y}_F_oil": kk["F"]["oil"], f"{y}_F_gas": kk["F"]["gas"]})
        np.savez_compressed(out / f"months_{tag}.npz", **arrays)
    (out / f"acceptance_{tag}.html").write_text(render(summ, cells), encoding="utf-8")
    cells.to_csv(out / f"cells_{tag}.csv", index=False)
    prov.to_csv(out / f"analog_provenance_{tag}.csv", index=False)
    (out / f"summary_{tag}.json").write_text(json.dumps(rep._clean(summ), indent=2, default=rep._json), encoding="utf-8")
    return {"summary": summ, "cells": cells}


def render(s: dict[str, Any], cells: pd.DataFrame) -> str:
    v = s["verdict"]
    cls = "ok" if v["overall"] == "PASS" else "bad"
    shown = tuple(s.get("variants", REPORTED))
    rec = s.get("record_variant", RECORD)
    piv = cells.pivot_table(index=["stream", "horizon", "cutoff"], columns="variant", values="pkg_bias").reindex(columns=list(shown))
    bench = cells[cells.variant == rec].set_index(["stream", "horizon", "cutoff"])
    tab = piv.join(bench[["n_packages", "n_wells", "pkg_band", "bench_bias", "bench_band", "verdict"]]).reset_index()
    tab = tab.rename(columns={v_: f"{v_} pkg bias" for v_ in shown} | {"pkg_band": f"{rec} pkg band"})
    folds = pd.DataFrame(s["folds"])
    pct = {f"{v_} pkg bias": "+.1%" for v_ in shown} | {"bench_bias": "+.1%", f"{rec} pkg band": ".2f", "bench_band": ".2f"}
    return "\n".join([
        "<!doctype html><html><head><meta charset=utf-8><meta name=viewport content='width=device-width,initial-scale=1'><title>BOX acceptance (D53)</title>",
        f"<style>{_CSS} body{{overflow-x:hidden}} table{{display:block;overflow-x:auto;max-width:100%}}</style></head><body>",
        f"<h1>BOX acceptance of record (D53) — {s['view']}</h1>",
        (f"<div class=meta>built {s['built_at']} · {s.get('bench_desc', 'Delaware WCA')} · rolling-origin folds (cutoff Dec 1; rebuilt from pre-cutoff data; next 12 months' wells scored) · "
         f"actuals curated.production through {s['actuals_through']} (each well's newest month dropped) · blueox-boxfit @ {s['engine_sha'][:7]} · read-only</div>"),
        (f"<div class='flag {cls}'><b>Verdict ({s['view']}): {v['overall']}</b> — oil {v['by_stream']['oil']}, gas {v['by_stream']['gas']}; "
         f"{v['n_failed']} of {v['n_judged']} judged cells fail. A cell (fold × stream × horizon) is judged when it has ≥ {s['min_packages']} packages and passes when "
         f"|package bias| ≤ {s['bias_tol']:.0%} AND the {rec} package band ≤ the local-offsets benchmark's + {BAND_TOL:.2f} (D53 amendment). Record model = <b>{rec}</b>.</div>"),
        (f"<div class=meta>Package = co-developed co-extent {s.get('bench', 'WCA')} wells (first production within 180 d, overlap ≥ 30 %), connected components; error = Σ actual / Σ predicted − 1 "
         "(negative = forecast HIGH). Benchmark = median per-1,000-ft cum-k of the 15 nearest pre-cutoff cohort wells whose cum-k was known at the cutoff × lateral. "
         "Held-out packages (any member in a D52 holdout block) are excluded before any statistic is computed; only their counts appear below.</div>"),
        ("<div class=meta>Verdict by variant (same rule): " + " · ".join(f"<b>{k}</b> {x['overall']} ({x['n_failed']}/{x['n_judged']} fail)" for k, x in s.get("verdict_by_variant", {}).items())
         + f". Analog radius reached (locations): {s.get('analog_radius_mi')}; recency fallback share {s.get('analog_recent_fallback_share')}.</div>"),
        "<h2>1. Package bias and band by fold</h2>", _table(tab, pct),
        "<h2>2. Folds</h2>", _table(folds, {"median_package_wells": ".1f"}),
        "</body></html>"])


def regrade(cells: pd.DataFrame, band_tol: float = BAND_TOL, scale_free_band: bool = SCALE_FREE) -> pd.DataFrame:
    """Re-judge stored cells (no recomputation of any statistic)."""
    c = cells.copy()
    c["verdict"] = [judge_cell({"bias": b, "band": w}, {"band": bb, "bias": bbi}, int(n), band_tol=band_tol, scale_free_band=scale_free_band)
                    for b, w, bb, bbi, n in zip(c["pkg_bias"], c["pkg_band"], c["bench_band"], c["bench_bias"], c["n_packages"], strict=True)]
    return c
