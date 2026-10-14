"""BOX step 6 (fail branch) — rolling-origin backtest, Novi-agnostic: rebuild at several cutoffs, score next year.

Per fold (cutoff C = Dec 1 of a year): BOX is rebuilt exactly as in the step-6 hindcast (box/hindcast_report:
step-4 areas inside the same extent, step-5b curves, 5c/5d factors, D36 F(k)) from wells first-producing before C
with production through the month before C (no vendor lag: the data a planner holds on C). The holdout is every
gate-1 WCA well first-producing in [C, C + 12 months), inside a rebuilt area, scored against curated.production
calendar-month cums (each well's newest reported month dropped) at cum-6 / 12 / 24 where reached.

Variants (pre-registered; each calibrates its own F(k) on its own training predictions, so the level is always
the training cohort's and only the shape of the prediction across wells changes):
  base      — BOX as built (curve x lateral / 1,000 x ref_mult x scenario factor; gas at the local GOR level);
  lat       — x Cui & Cross Delaware lateral-length efficiency, 2,000 lb / 60 bbl per ft (box.backtest.CUI_DELAWARE):
              E(L_well) / mean E(L_member) over the area curve's members (the per-kft mean curve is base x mean E);
  lat1700   — the same with the 1,700 lb / 50 bbl curve (sensitivity: the cohort's fluid intensity);
  dens      — x the density term (n_near + same-bench spacing), PPML with the base prediction as offset, training only;
  lat+dens  — both (density fitted on the lat prediction).
Read-only; nothing stored.
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

from box import backtest as bt
from box import dev_factor_report as dfr
from box import edge_gap_report as egr
from box import exclusions
from box import hindcast as hc
from box import hindcast_production as hp
from box import hindcast_report as hr
from box import holdout as ho
from box import spacing3d_report as s3r
from box import tc_curve_report as rep
from box import tc_record_report as trr
from box.edge_gap_report import _CSS, _png, _table

CUTOFFS: tuple[dt.date, ...] = (dt.date(2021, 12, 1), dt.date(2022, 12, 1), dt.date(2023, 12, 1), dt.date(2024, 12, 1))
HORIZONS: tuple[int, ...] = (6, 12, 24)
STREAMS: tuple[str, ...] = ("oil", "gas")
VARIANTS: tuple[str, ...] = ("base", "lat", "lat1700", "dens", "lat+dens", "s3d", "lat+s3d")
S3D_COLS = ("ln_xsec", "ln_lat_spacing", "ln1p_parent_cum")  # 3-D spacing prototype, as of first production
DENS_COLS = ("near", "spacing")
DENS_REF = {"near": "2-3", "spacing": "880-1320"}
_SPACING_SQL = "SELECT api10, lateral_closer_xy_ft FROM curated.wells_enriched WHERE api10 = ANY(%(a)s)"


def _prev_month(d: dt.date) -> dt.date:
    return (d.replace(day=1) - dt.timedelta(days=1)).replace(day=1)


def _add_months(d: dt.date, n: int) -> dt.date:
    m = d.month - 1 + n
    return dt.date(d.year + m // 12, m % 12 + 1, 1)


def spacing(conn: Any, ids: list[str]) -> pd.Series:
    rows = rep._read(conn, _SPACING_SQL, {"a": ids})
    return pd.Series({a: (float(v) if v is not None else np.nan) for a, v in rows}, dtype=float)


def lateral_mult(fr: pd.DataFrame, cb: dict[str, Any], curve: str) -> np.ndarray:
    """E(L_well) / mean E(L) of the well's area oil-curve members (included = oil fit + real lateral)."""
    d = cb["frame"].set_index("api10")
    mean_e = {}
    for a, cur in cb["curves"].items():
        ids = [x for x in cur["streams"]["oil"]["api10s"] if bool(d.at[x, "fit_oil"]) and float(d.at[x, "lateral_ft"] or 0) > 0]
        mean_e[a] = float(np.mean([bt.lateral_efficiency(float(d.at[x, "lateral_ft"]), curve) for x in ids]))
    return np.array([bt.lateral_efficiency(float(r.lateral_ft), curve) / mean_e[int(r.area_no)] for r in fr.itertuples()])


def prep(fr: pd.DataFrame, sp: pd.Series) -> pd.DataFrame:
    fr = fr.copy()
    fr["near"] = [bt.near_bin(v) for v in pd.to_numeric(fr["n_near"], errors="coerce")]
    fr["spacing_ft"] = fr["api10"].map(sp)
    fr["spacing"] = [bt.spacing_bin(v) for v in fr["spacing_ft"]]
    fr["lat_bin"] = [bt.lateral_bin(v) for v in fr["lateral_ft"]]
    return fr


def run_fold(conn: Any, wells: pd.DataFrame, wells_dir: Path, cutoff: dt.date, workers: int | None, last: dt.date, P: dict[str, Any],
             horizons: tuple[int, ...] = HORIZONS, k_months: int = 24, keep_pred: bool = False, return_internals: bool = False) -> dict[str, Any]:
    asof = _prev_month(cutoff)
    ar = hr.rebuild_areas(conn, wells, asof)
    cb = hr.rebuild_curves(conn, wells, ar, cutoff, asof, workers)
    fx = hr.rebuild_factors(conn, cb, wells, wells_dir, asof, workers)
    tabs = {s: trr.factor_table(fx["rf"], hr.POOL, s) for s in ("oil", "gas")}
    wca = fx["frames"][hr.POOL].reset_index(drop=True)
    rm = hr.ref_mults(cb, wca, tabs["oil"])
    # ---- training
    trn = wca.join(hr.well_factors(wca, tabs))
    trn["lateral_ft"] = pd.to_numeric(trn["lateral_ft"], errors="coerce")
    trn = trn[(trn["lateral_ft"] > 0) & trn["area_no"].notna()].reset_index(drop=True)
    trn["area_no"] = trn["area_no"].astype(int)
    trn["gor_target"] = trn["gor_local"] * trn["f_gor"]
    # ---- holdout
    end = _add_months(cutoff, 12)
    hw = wells[[cutoff <= f < end for f in wells["first_production_date"]]].copy()
    hx, hy = dfr._xy(hw["mid_lon"], hw["mid_lat"])
    hw["area_no"] = rep.assign_area(np.column_stack([hx, hy]), ar["geoms"])
    hw["lateral_ft"] = pd.to_numeric(hw["lateral_length_ft"], errors="coerce")
    hw = hw[(hw["area_no"] > 0) & (hw["lateral_ft"] > 0)].reset_index(drop=True)
    hw["bench_pool"] = hr.POOL
    hs, hrep = dfr.attach_scenario(conn, hw)
    hs["infill"] = hs["infill"].astype(object).where(hs["infill"].notna(), False).astype(bool)
    hs["own_bench_in_pool"] = hs["own_bench_in_pool"].astype(bool)
    hs["gor_local"] = hr.local_gor(wca, np.column_stack(dfr._xy(hs["mid_lon"], hs["mid_lat"])))
    hs["gor12"] = np.nan
    hs = trr.add_pooled_view(hs)
    hs = hs.join(hr.well_factors(hs, tabs))
    hs["gor_target"] = hs["gor_local"] * hs["f_gor"]
    sp = spacing(conn, sorted(set(trn["api10"]) | set(hs["api10"])))
    trn, hs = prep(trn, sp), prep(hs, sp)
    # 3-D spacing as of first production; a holdout well's parent depletion is read at the cutoff at the latest
    trn = trn.merge(s3r.features_table(P, trn["api10"])[["api10", "xsec_ft2", "lat_spacing_ft", *S3D_COLS]], on="api10", how="left")
    hs = hs.merge(s3r.features_table(P, hs["api10"], cap=cutoff)[["api10", "xsec_ft2", "lat_spacing_ft", *S3D_COLS]], on="api10", how="left")
    hs["xsec_bin"] = pd.cut(hs["xsec_ft2"], [0, 1e6, 2e6, 4e6, np.inf], labels=["<1M", "1-2M", "2-4M", ">=4M"]).astype(object)
    # ---- monthly predictions (no F) + actuals
    t_ids = list(trn["api10"])
    t_act = hp.monthly_matrix(cb["prod"][cb["prod"]["api10"].isin(set(t_ids))], t_ids, asof=asof, k=k_months)
    t_box = hp.box_months(trn, cb, rm, k_months)
    prod = rep.pull_production(conn, list(hs["api10"]), last)
    h_act = hp.monthly_matrix(prod, list(hs["api10"]), drop_latest=True, k=k_months)
    h_box = hp.box_months(hs, cb, rm, k_months)
    hs["holdout_block"] = ho.is_holdout(*dfr._xy(hs["mid_lon"], hs["mid_lat"]))  # D52 frozen spatial holdout
    bench = local_offsets(trn, t_act, hs, horizons)  # D53 benchmark: an engineer's quick look
    mult_t = {"base": np.ones(len(trn)), "lat": lateral_mult(trn, cb, "2000-60"), "lat1700": lateral_mult(trn, cb, "1700-50")}
    mult_h = {"base": np.ones(len(hs)), "lat": lateral_mult(hs, cb, "2000-60"), "lat1700": lateral_mult(hs, cb, "1700-50")}
    dens_fit = {}
    for v, basev in (("dens", "base"), ("lat+dens", "lat")):
        tt = trn.assign(a12=np.nansum(t_act["oil"][:, :12], axis=1) * np.where(np.isfinite(t_act["oil"][:, 11]), 1, np.nan),
                        p12=t_box["oil"][:, :12].sum(axis=1) * mult_t[basev])
        f = bt.fit_density(tt, "a12", "p12", DENS_COLS, DENS_REF)
        m_t = bt.density_multiplier(trn, f, DENS_COLS, DENS_REF)
        k = bt.normaliser(tt["p12"].to_numpy(), m_t)
        dens_fit[v] = {"factors": f, "norm": k}
        mult_t[v] = mult_t[basev] * m_t * k
        mult_h[v] = mult_h[basev] * bt.density_multiplier(hs, f, DENS_COLS, DENS_REF) * k
    s3d_fit = {}
    for v, basev in (("s3d", "base"), ("lat+s3d", "lat")):
        tt = trn.assign(a12=np.nansum(t_act["oil"][:, :12], axis=1) * np.where(np.isfinite(t_act["oil"][:, 11]), 1, np.nan),
                        p12=t_box["oil"][:, :12].sum(axis=1) * mult_t[basev])
        f = bt.fit_numeric(tt, "a12", "p12", S3D_COLS)
        m_t = bt.numeric_multiplier(trn, f)
        k = bt.normaliser(tt["p12"].to_numpy(), m_t)
        s3d_fit[v] = {**f, "norm": k}
        mult_t[v] = mult_t[basev] * m_t * k
        mult_h[v] = mult_h[basev] * bt.numeric_multiplier(hs, f) * k
    F = {v: {s: hc.calendar_factor_curve(t_act[s], t_box[s] * mult_t[v][:, None])[0] for s in STREAMS} for v in VARIANTS}
    rows = []
    for v in VARIANTS:
        for s in STREAMS:
            pred_cum = np.cumsum(h_box[s] * mult_h[v][:, None], axis=1) * F[v][s][None, :]
            act_cum = np.cumsum(h_act[s], axis=1)
            for k in horizons:
                hs[f"{v}_err_{s}{k}"] = hc.pct_error(act_cum[:, k - 1], pred_cum[:, k - 1])
                if keep_pred:
                    hs[f"pred_{v}_{s}{k}"] = pred_cum[:, k - 1]
                if v == "base":
                    hs[f"actual_{s}{k}"] = act_cum[:, k - 1]
                    hs[f"base_{s}{k}"] = pred_cum[:, k - 1]
                    hs[f"bench_{s}{k}"] = bench[f"{s}{k}"]
                    hs[f"bench_err_{s}{k}"] = hc.pct_error(act_cum[:, k - 1], bench[f"{s}{k}"])
                rows.append({"cutoff": str(cutoff), "variant": v, "stream": s, "horizon": k, **hc.stats(hs[f"{v}_err_{s}{k}"])})
    hs["cutoff"] = str(cutoff)
    for v in VARIANTS:
        hs[f"mult_{v}"] = mult_h[v]
    extra = {"cb": cb, "trn": trn, "t_act": t_act, "sp": sp} if return_internals else {}
    return {**extra, "cutoff": cutoff, "asof": asof, "k_areas": len(ar["geoms"]), "n_train": len(trn), "n_hold": len(hs), "hold_repl": hrep,
            "F": {v: {s: [float(x) for x in F[v][s]] for s in STREAMS} for v in VARIANTS}, "density": dens_fit, "s3d": s3d_fit, "scores": pd.DataFrame(rows), "hold": hs,
            "n_fitted": cb["n_fitted"]}


MIN_CELL_N = 30  # a fold x horizon with fewer scored wells is not reported (e.g. cum-24 on the newest fold)


BENCH_K = 15  # D53 local-offsets benchmark: nearest pre-cutoff cohort wells


def local_offsets(trn: pd.DataFrame, t_act: dict[str, np.ndarray], hs: pd.DataFrame, horizons: tuple[int, ...], k_nn: int = BENCH_K) -> dict[str, np.ndarray]:
    """D53 benchmark — what an engineer's quick look gives: for each scored well, the median per-1,000-ft actual cum-k of
    its k_nn nearest pre-cutoff cohort wells (lateral midpoints) whose cum-k was KNOWN at the cutoff, x its lateral / 1,000
    (linear per-ft, no curve, no factors)."""
    from scipy.spatial import cKDTree

    tx, ty = dfr._xy(trn["mid_lon"], trn["mid_lat"])
    hx, hy = dfr._xy(hs["mid_lon"], hs["mid_lat"])
    lat_t = trn["lateral_ft"].to_numpy(float) / 1000.0
    out = {}
    for s in STREAMS:
        cum = np.cumsum(t_act[s], axis=1)
        for k in horizons:
            per = cum[:, k - 1] / lat_t
            ok = np.isfinite(per) & (per > 0)
            if ok.sum() < k_nn:
                out[f"{s}{k}"] = np.full(len(hs), np.nan)
                continue
            _, j = cKDTree(np.column_stack([tx[ok], ty[ok]])).query(np.column_stack([hx, hy]), k=k_nn)
            out[f"{s}{k}"] = np.median(per[ok][j], axis=1) * hs["lateral_ft"].to_numpy(float) / 1000.0
    return out


def mask_thin(scores: pd.DataFrame, min_n: int = MIN_CELL_N) -> pd.DataFrame:
    s = scores.copy()
    thin = s["n"] < min_n
    s.loc[thin, [c for c in s.columns if c not in ("cutoff", "variant", "stream", "horizon", "n")]] = np.nan
    return s


def breakdown(h: pd.DataFrame, by: str, k: int = 6) -> pd.DataFrame:
    """Oil cum-k bias per class of `by`, per variant, all folds pooled + per fold n."""
    rows = []
    for g, x in h.groupby(by, dropna=False):
        r = {by: g if pd.notna(g) else "(none)", "n": int(np.isfinite(x[f"base_err_oil{k}"]).sum()), "lateral_ft_median": float(x["lateral_ft"].median())}
        for v in VARIANTS:
            r[f"{v} bias"] = hc.stats(x[f"{v}_err_oil{k}"])["bias"]
        rows.append(r)
    return pd.DataFrame(rows)


def run(conn: Any, wells_dir: Path, out: Path, engine_sha: str, workers: int | None = None, cutoffs: tuple[dt.date, ...] = CUTOFFS) -> dict[str, Any]:
    out.mkdir(parents=True, exist_ok=True)
    wells, excluded = exclusions.drop(egr.load_final_sets(wells_dir, (hr.POOL,)))
    last = rep.last_full_month(rep._read(conn, rep._MONTHS_SQL))
    subj = wells[np.array([f >= dt.date(2016, 1, 1) for f in wells["first_production_date"]]) & (pd.to_numeric(wells["lateral_length_ft"], errors="coerce") > 0).to_numpy()]
    P = s3r.build_pairs(conn, subj.reset_index(drop=True))
    folds = [run_fold(conn, wells, wells_dir, c, workers, last, P) for c in cutoffs]
    scores = mask_thin(pd.concat([f["scores"] for f in folds], ignore_index=True))
    hold = pd.concat([f["hold"] for f in folds], ignore_index=True)
    built = dt.datetime.now(tz=dt.UTC).astimezone().isoformat(timespec="seconds")
    lat = breakdown(hold, "lat_bin")
    near = breakdown(hold, "near")
    spc = breakdown(hold, "spacing")
    xs = breakdown(hold, "xsec_bin")
    summ = {"built_at": built, "engine_sha": engine_sha, "actuals_through": str(last), "n_excluded": len(excluded),
            "folds": [{k: (str(v) if isinstance(v, dt.date) else v) for k, v in f.items() if k not in ("scores", "hold")} for f in folds]}
    ctx = {"summary": summ, "scores": scores, "lat": lat, "near": near, "spc": spc, "xs": xs, "png": bias_png(scores)}
    (out / "backtest.html").write_text(render(ctx), encoding="utf-8")
    scores.to_csv(out / "scores.csv", index=False)
    keep = ["cutoff", "api10", "well_name", "operator", "area_no", "first_production_date", "lateral_ft", "lat_bin", "n_near", "near", "spacing_ft", "spacing",
            "xsec_ft2", "xsec_bin", "lat_spacing_ft", "ln1p_parent_cum",
            "p_class", "p_infill", "f_oil", *[f"mult_{v}" for v in VARIANTS]]
    keep += [f"{c}{s}{k}" for s in STREAMS for k in HORIZONS for c in ("actual_", "base_")]
    keep += [f"{v}_err_{s}{k}" for v in VARIANTS for s in STREAMS for k in HORIZONS]
    hold[keep].to_csv(out / "holdout.csv", index=False)
    pd.concat([lat.assign(by="lateral"), near.assign(by="near"), spc.assign(by="spacing"), xs.assign(by="xsec")]).to_csv(out / "breakdown_oil6.csv", index=False)
    (out / "summary.json").write_text(json.dumps(rep._clean(summ), indent=2, default=rep._json), encoding="utf-8")
    return {"summary": summ, "scores": scores, "hold": hold}


def bias_png(scores: pd.DataFrame) -> str:
    fig, axs = plt.subplots(1, 4, figsize=(17, 3.8), sharey=True)
    colours = {"base": "#6b7280", "lat": "#2a78d6", "lat1700": "#93c5fd", "dens": "#eb6834", "lat+dens": "#1baf7a", "s3d": "#e87ba4", "lat+s3d": "#4a3aa7"}
    for ax, (s, k) in zip(axs, [("oil", 6), ("oil", 12), ("gas", 6), ("gas", 12)], strict=True):
        x = scores[(scores.stream == s) & (scores.horizon == k)]
        cut = sorted(x.cutoff.unique())
        w = 0.12
        for i, v in enumerate(VARIANTS):
            y = [float(x[(x.cutoff == c) & (x.variant == v)]["bias"].iloc[0]) for c in cut]
            ax.bar(np.arange(len(cut)) + (i - 3) * w, y, w * 0.9, color=colours[v], label=v)
        ax.axhspan(-0.10, 0.10, color="#16a34a", alpha=0.07)
        ax.axhline(0, color="#111827", lw=0.8)
        ax.set_xticks(np.arange(len(cut)), [c[:4] for c in cut])
        ax.set_title(f"{s} cum-{k}: bias by cutoff year", fontsize=10)
        ax.yaxis.set_major_formatter(matplotlib.ticker.PercentFormatter(1.0))
    axs[0].legend(fontsize=8)
    axs[0].set_ylabel("mean(actual / BOX − 1)")
    fig.tight_layout()
    return _png(fig)


def render(ctx: dict[str, Any]) -> str:
    s = ctx["summary"]
    sc = ctx["scores"]
    wide = sc.pivot_table(index=["stream", "horizon", "cutoff"], columns="variant", values="bias").reindex(columns=list(VARIANTS)).reset_index()
    band = sc.pivot_table(index=["stream", "horizon", "cutoff"], columns="variant", values="band").reindex(columns=list(VARIANTS)).reset_index()
    n = sc[sc.variant == "base"].set_index(["stream", "horizon", "cutoff"])["n"]
    wide.insert(3, "n", [int(n.get((a, b, c), 0)) for a, b, c in zip(wide.stream, wide.horizon, wide.cutoff, strict=True)])
    folds = pd.DataFrame([{"cutoff": f["cutoff"], "production through": f["asof"], "areas (k)": f["k_areas"], "wells fitted": f["n_fitted"], "training cohort": f["n_train"],
                           "holdout wells": f["n_hold"], "F oil 6 / 12 (base)": f"{f['F']['base']['oil'][5]:.3f} / {f['F']['base']['oil'][11]:.3f}"} for f in s["folds"]])
    dens = pd.DataFrame([{"cutoff": f["cutoff"], "variant": v, **{k: round(x, 3) for k, x in d["factors"].items()}, "norm": round(d["norm"], 3)}
                         for f in s["folds"] for v, d in f["density"].items()])
    pct = {v: "+.1%" for v in VARIANTS}
    p = ["<!doctype html><html><head><meta charset=utf-8><meta name=viewport content='width=device-width,initial-scale=1'><title>BOX rolling backtest</title>",
         f"<style>{_CSS} body{{overflow-x:hidden}} table{{display:block;overflow-x:auto;max-width:100%}}</style></head><body>",
         "<h1>BOX step 6 (fail branch) — rolling-origin backtest vs actuals (Novi-agnostic)</h1>",
         (f"<div class=meta>built {s['built_at']} · Delaware WCA · each fold rebuilt from wells first-producing before the cutoff with production through the month before it "
          f"(areas, curves, factors, F(k) — the step-6 methods) · holdout = gate-1 WCA wells first-producing in the 12 months after the cutoff · actuals curated.production through "
          f"{s['actuals_through']} (each well's newest month dropped) · blueox-boxfit @ {s['engine_sha'][:7]} · read-only</div>"),
         ("<div class=flag>Error = actual / BOX − 1 (negative = BOX HIGH). Variants: <b>base</b> = BOX as built; <b>lat</b> = × Cui &amp; Cross (URTeC 3723784) Delaware lateral-length "
          "efficiency, 2,000 lb / 60 bbl per ft, normalised to the area curve's own lateral mix, extended past 12,500 ft on the last segment's slope; <b>lat1700</b> = the 1,700 / 50 curve; "
          "<b>dens</b> = × package-density term (co-extent neighbours within ±500 ft TVD, parents + codev; same-bench spacing) fitted on training wells only; <b>lat+dens</b> = both; "
          "<b>s3d</b> = × 3-D spacing prototype (ln drainage cross-section, ln lateral spacing, ln(1 + parent cum per kft), as of first production; a holdout well's parent depletion read at the cutoff), PPML on training wells; <b>lat+s3d</b> = both. "
          "Every variant calibrates its own F(k) on its own training predictions.</div>"),
         f"<img src='{ctx['png']}'>",
         "<h2>1. Bias by fold (mean error; green band = ±10 %)</h2>", _table(wide, pct),
         "<h2>2. P10–P90 band by fold (P10 = high)</h2>", _table(band, {v: ".2f" for v in VARIANTS}),
         "<h2>3. Oil cum-6 bias by lateral length (all folds)</h2>", _table(ctx["lat"], {**{f"{v} bias": "+.1%" for v in VARIANTS}, "lateral_ft_median": ",.0f"}),
         "<h2>4. Oil cum-6 bias by package density — co-extent neighbours within ±500 ft TVD (all folds)</h2>", _table(ctx["near"], {**{f"{v} bias": "+.1%" for v in VARIANTS}, "lateral_ft_median": ",.0f"}),
         "<h2>5. Oil cum-6 bias by same-bench spacing, lateral_closer_xy_ft (all folds)</h2>", _table(ctx["spc"], {**{f"{v} bias": "+.1%" for v in VARIANTS}, "lateral_ft_median": ",.0f"}),
         "<h2>6. Oil cum-6 bias by drainage cross-section, 3-D spacing prototype (all folds)</h2>",
         _table(ctx["xs"], {**{f"{v} bias": "+.1%" for v in VARIANTS}, "lateral_ft_median": ",.0f"}),
         "<h2>7. Folds</h2>", _table(folds, {}),
         "<h3>3-D spacing multipliers per fold (exp(b x 1 SD) per term; training only)</h3>",
         _table(pd.DataFrame([{"cutoff": f["cutoff"], "variant": v, **{c: round(float(np.exp(x["b"][c] * x["sd"][c])), 3) for c in x["cols"]}, "norm": round(x["norm"], 3)}
                              for f in s["folds"] for v, x in f["s3d"].items()]), {}),
         "<h3>Density multipliers fitted per fold (reference: 2–3 near neighbours, 880–1,320 ft spacing; norm keeps the training total)</h3>", _table(dens, {}),
         "</body></html>"]
    return "\n".join(p)
