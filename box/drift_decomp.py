"""BOX step 6 fail branch — decompose the vintage drift: time / practice vs remaining-inventory rock vs spacing (read-only).

Michael 2026-10-13: the year-to-year decline steepening may be operators' remaining inventory getting lower quality each
year (tier-1 exhaustion), not a change in how wells are completed / produced. The two call for different fixes — a
location-quality term (PUDs are, by construction, what is left) vs a bench-wide recent-regime shape — so separate them.

Design (fixed before running):
  population  gate-1 WCA wells (exclusions dropped), first production 2016–2024, real lateral, midpoint in a TC area of
              record; regressions on wells whose rock proxy is COVERED.
  responses   level  = ln 12-mo oil / kft (Novi pass-through, the step-4 response);
              shape  = ln (rate months 19–24 / rate months 4–6) — past the median month-2 peak, so peak timing can't move it;
              shape2 = ln (cum-24 / cum-6) (secondary; peak-timing sensitive).
  rock proxy  FIXED IN TIME: median 12-mo oil / kft of the 15 nearest REFERENCE wells (first production 2016–2019, lateral
              6,000–13,000 ft; a reference well excludes itself) at each well's lateral midpoint. Covered when the 15th
              nearest is within 3 mi. Later drilling cannot move it, so a falling proxy at newer wells = newer wells sit on
              rock that early wells around them showed to be poorer.
  spacing     box/spacing3d features as of first production (default Params; ln cross-section, ln lateral spacing,
              ln(1 + parent cum)).
  tests       (i) within-area year effect on the rock proxy itself; (ii) within-area year effects on each response as
              blocks are added (lateral -> rock -> spacing -> both -> + early time, diagnostic) and the share of the mean
              2021–2024 effect each absorbs; (iii) the post-2021 effect by area development intensity tercile and by
              rock-proxy tercile; (iv) step vs trend: ln y ~ area FE + controls + post2021 + (year - 2016).
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
from scipy.spatial import cKDTree

from box import shape_drift as sd
from box import spacing3d_report as s3r
from box import spacing3d_sweep as sw
from box.edge_gap_report import _CSS, _png, _table

REF_YEARS = (2016, 2019)
REF_LAT = (6000.0, 13000.0)
K_ROCK = 15
COVER_FT = 15_840.0
RESPONSES = {"level": "ln_oil12_kft", "shape": "ln_rate_19_24_vs_4_6", "shape2": "ln_r24_6"}
S3D = ["ln_xsec", "ln_lat_spacing", "ln1p_parent_cum"]
INTENSITY = ["ln1p_dev_2mi", "ln1p_dev_5mi"]  # prior horizontals (any bench) within 2 / 5 mi, online > 180 d before FP
COVER_SENS_FT = 26_400.0  # 5-mi coverage sensitivity
YEARS = [str(y) for y in range(2016, 2025)]


def rock_proxy(d: pd.DataFrame) -> pd.DataFrame:
    """Median oil12/kft of the K nearest reference wells (self excluded) + distance to the K-th; fixed in time."""
    fy = d["first_production_date"].map(lambda f: f.year)
    lat = d["lateral_ft"]
    ref = d[fy.between(*REF_YEARS) & lat.between(*REF_LAT) & (pd.to_numeric(d["oil12_kft"], errors="coerce") > 0)]
    tree = cKDTree(ref[["x", "y"]].to_numpy())
    dist, j = tree.query(d[["x", "y"]].to_numpy(), k=K_ROCK + 1)
    ref_ids = ref["api10"].to_numpy()
    vals = pd.to_numeric(ref["oil12_kft"], errors="coerce").to_numpy(float)
    prox, dk = np.empty(len(d)), np.empty(len(d))
    for i, a in enumerate(d["api10"]):
        keep = ref_ids[j[i]] != a  # leave-one-out for reference wells
        jj, dd = j[i][keep][:K_ROCK], dist[i][keep][:K_ROCK]
        prox[i], dk[i] = np.median(vals[jj]), dd[-1]
    return pd.DataFrame({"rock_proxy": prox, "rock_dist_kth_ft": dk, "rock_covered": dk <= COVER_FT, "is_reference": d["api10"].isin(set(ref_ids)).to_numpy()}, index=d.index)


def dev_intensity(conn: Any, d: pd.DataFrame) -> pd.DataFrame:
    """Regional development intensity at first production: producing horizontals (any bench, sql/47 universe) whose
    lateral midpoint is within 2 / 5 mi and that came online more than 180 d before the subject. Observable for a PUD."""
    u = s3r.pull_universe(conn, d[["api10", "mid_lon", "mid_lat"]])
    mid = np.array([[g.interpolate(0.5, normalized=True).x, g.interpolate(0.5, normalized=True).y] for g in u["geom"]])
    ufp = np.array([np.datetime64(f) for f in u["fp"]])
    tree = cKDTree(mid)
    sfp = np.array([np.datetime64(f) for f in d["first_production_date"]])
    out = {}
    for lab, r in (("dev_2mi", 10_560.0), ("dev_5mi", 26_400.0)):
        idx = tree.query_ball_point(d[["x", "y"]].to_numpy(), r=r)
        out[lab] = [int(np.sum(ufp[j] < sfp[i] - np.timedelta64(180, "D"))) for i, j in enumerate(idx)]
    return pd.DataFrame(out, index=d.index)


def ols(df: pd.DataFrame, y: str, num: list[str], fe: list[str]) -> tuple[pd.Series, pd.Series, int]:
    X = [np.ones(len(df))] + [df[c].to_numpy(float) for c in num]
    names = ["_c", *num]
    for f in fe:
        dm = pd.get_dummies(df[f].astype(str), prefix=f, drop_first=True).astype(float)
        X += [dm[c].to_numpy() for c in dm.columns]
        names += list(dm.columns)
    Xa, ya = np.column_stack(X), df[y].to_numpy(float)
    b, *_ = np.linalg.lstsq(Xa, ya, rcond=None)
    r = ya - Xa @ b
    se = np.sqrt(np.clip(np.diag(np.linalg.pinv(Xa.T @ Xa)) * float(r @ r) / max(1, len(ya) - Xa.shape[1]), 0, None))
    return pd.Series(b, index=names), pd.Series(se, index=names), len(ya)


def run(conn: Any, wells_dir: Path, out: Path) -> dict[str, Any]:
    out.mkdir(parents=True, exist_ok=True)
    d = sw.subjects(conn, wells_dir)
    d = d[d["first_production_date"].map(lambda f: f.year) <= 2024].reset_index(drop=True)
    d = pd.concat([d, rock_proxy(d)], axis=1)
    d["ln_rock"] = np.log(d["rock_proxy"])
    P = s3r.build_pairs(conn, d[["api10", "mid_lon", "mid_lat"]])
    d = d.merge(s3r.features_table(P, d["api10"])[["api10", *S3D]], on="api10", how="left")
    d = pd.concat([d, dev_intensity(conn, d)], axis=1)
    d["ln1p_dev_2mi"], d["ln1p_dev_5mi"] = np.log1p(d["dev_2mi"]), np.log1p(d["dev_5mi"])
    d["rock_covered_5mi"] = d["rock_dist_kth_ft"] <= COVER_SENS_FT
    n_area = d.groupby("area_no")["api10"].transform("size")
    d["dev_tercile"] = pd.qcut(n_area.rank(method="first"), 3, labels=["thin", "mid", "deep"]).astype(str)
    cov = d[d["rock_covered"]].copy()
    cov["rock_tercile"] = pd.qcut(cov["rock_proxy"], 3, labels=["poor", "mid", "good"]).astype(str)
    cov["post2021"] = (cov["fpy"].astype(int) >= 2021).astype(float)
    cov["trend"] = cov["fpy"].astype(int) - 2016.0
    # (i) does the rock under new wells get poorer?
    rock_trend = sd.fe_ols(cov, "ln_rock", [], ["area_no"])
    rock_tab = pd.DataFrame([{"response": "ln rock proxy (vs 2018)", "n": rock_trend.attrs["n"], **{y: float(np.expm1(rock_trend.get(y, np.nan))) for y in YEARS if y != "2018"}}])
    # (ii) blocks
    blocks = [("area", []), ("+ lateral", ["ln_lat"]), ("+ rock proxy", ["ln_lat", "ln_rock"]), ("+ 3-D spacing", ["ln_lat", *S3D]),
              ("+ rock + spacing", ["ln_lat", "ln_rock", *S3D]), ("+ regional development intensity", ["ln_lat", *INTENSITY]),
              ("+ rock + spacing + intensity", ["ln_lat", "ln_rock", *S3D, *INTENSITY]),
              ("+ rock + spacing + intensity + early time (diagnostic)", ["ln_lat", "ln_rock", *S3D, *INTENSITY, "peak_month", "m1_share6"])]
    rows = []
    for key, y in RESPONSES.items():
        pop = cov.dropna(subset=[y, "ln_lat", "ln_rock", *S3D, *INTENSITY, "peak_month", "m1_share6"])
        base_mean = None
        for lab, num in blocks:
            c = sd.fe_ols(pop, y, num, ["area_no"])
            m = float(np.mean([c.get(yy, np.nan) for yy in ("2021", "2022", "2023", "2024")]))
            if lab == "+ lateral":
                base_mean = m
            rows.append({"response": key, "spec": lab, "n": c.attrs["n"], **{yy: float(np.expm1(c.get(yy, np.nan))) for yy in YEARS if yy != "2018"},
                         "mean_2021_24": float(np.expm1(m)), "_m": m})
        for r_ in rows:
            if r_["response"] == key:
                r_["absorbed_vs_lateral"] = (1 - r_["_m"] / base_mean) if base_mean else np.nan
    yeff = pd.DataFrame(rows).drop(columns="_m")
    # (iii) heterogeneity of the post-2021 effect
    het = []
    for key, y in RESPONSES.items():
        pop = cov.dropna(subset=[y, "ln_lat", "ln_rock"])
        for grp in ("dev_tercile", "rock_tercile"):
            for g, x in pop.groupby(grp):
                b, se, n = ols(x, y, ["post2021", "ln_lat", "ln_rock"], ["area_no"])
                het.append({"response": key, "split": grp, "group": g, "n": n, "post2021_effect": float(np.expm1(b["post2021"])), "t": float(b["post2021"] / se["post2021"])})
    het = pd.DataFrame(het)
    # (iv) step vs trend
    st = []
    for key, y in RESPONSES.items():
        pop = cov.dropna(subset=[y, "ln_lat", "ln_rock", *S3D, *INTENSITY])
        for lab, num in (("lateral", ["ln_lat"]), ("lateral + rock + spacing", ["ln_lat", "ln_rock", *S3D]),
                         ("lateral + rock + spacing + intensity", ["ln_lat", "ln_rock", *S3D, *INTENSITY])):
            b, se, n = ols(pop, y, ["post2021", "trend", *num], ["area_no"])
            st.append({"response": key, "controls": lab, "n": n, "step_2021": float(np.expm1(b["post2021"])), "step_t": float(b["post2021"] / se["post2021"]),
                       "trend_per_year": float(np.expm1(b["trend"])), "trend_t": float(b["trend"] / se["trend"]),
                       "rock_coef": float(b.get("ln_rock", np.nan)), "rock_t": float(b.get("ln_rock", np.nan) / se.get("ln_rock", np.nan)) if "ln_rock" in b else np.nan})
    st = pd.DataFrame(st)
    # coverage sensitivity: the rock test on the 5-mi-covered population (more of the newer wells)
    cov5 = d[d["rock_covered_5mi"]].copy()
    r5 = sd.fe_ols(cov5, "ln_rock", [], ["area_no"])
    rock_tab = pd.concat([rock_tab, pd.DataFrame([{"response": "ln rock proxy (vs 2018), 5-mi coverage", "n": r5.attrs["n"],
                                                    **{y: float(np.expm1(r5.get(y, np.nan))) for y in YEARS if y != "2018"}}])], ignore_index=True)
    sens = []
    for key, y in RESPONSES.items():
        pop = cov5.dropna(subset=[y, "ln_lat", "ln_rock"])
        for lab, num in (("lateral", ["ln_lat"]), ("+ rock proxy", ["ln_lat", "ln_rock"])):
            c = sd.fe_ols(pop, y, num, ["area_no"])
            sens.append({"response": key, "spec": f"{lab} (5-mi coverage)", "n": c.attrs["n"],
                         "mean_2021_24": float(np.expm1(np.mean([c.get(yy, np.nan) for yy in ("2021", "2022", "2023", "2024")])))})
    yeff = pd.concat([yeff, pd.DataFrame(sens)], ignore_index=True)
    cover = {"n_wells": len(d), "n_covered": int(d["rock_covered"].sum()), "n_covered_5mi": int(d["rock_covered_5mi"].sum()),
             "covered_5mi_share_by_vintage": {str(k): float(v) for k, v in d.groupby("fpy")["rock_covered_5mi"].mean().items()}, "covered_share_by_vintage": {str(k): float(v) for k, v in d.groupby("fpy")["rock_covered"].mean().items()},
             "n_reference": int(d["is_reference"].sum())}
    built = dt.datetime.now(tz=dt.UTC).astimezone().isoformat(timespec="seconds")
    summ = {"built_at": built, "asof": str(d.attrs.get("asof", "")), "coverage": cover, "params": {"ref_years": REF_YEARS, "ref_lateral_ft": REF_LAT, "k": K_ROCK, "cover_ft": COVER_FT}}
    png = rock_png(cov)
    (out / "decomp.html").write_text(render(summ, rock_tab, yeff, het, st, png), encoding="utf-8")
    for name, t in (("rock_by_vintage", rock_tab), ("year_effects", yeff), ("heterogeneity", het), ("step_vs_trend", st)):
        t.to_csv(out / f"{name}.csv", index=False)
    (out / "summary.json").write_text(json.dumps(summ, indent=2, default=str), encoding="utf-8")
    return {"summary": summ, "rock": rock_tab, "yeff": yeff, "het": het, "step": st}


def rock_png(cov: pd.DataFrame) -> str:
    fig, axs = plt.subplots(1, 2, figsize=(13, 3.8))
    g = cov.groupby("fpy")
    yrs = sorted(cov["fpy"].unique())
    axs[0].plot(yrs, [g["rock_proxy"].median()[y] for y in yrs], "o-", color="#2a78d6", label="rock proxy under the well (median)")
    axs[0].plot(yrs, [g["oil12_kft"].median()[y] for y in yrs], "o-", color="#eb6834", label="the well's own 12-mo oil / kft (median)")
    axs[0].set_title("Rock proxy (2016–19 neighbours, fixed) vs actual, by first-production year — raw", fontsize=9)
    axs[0].legend(fontsize=8)
    axs[0].grid(alpha=0.3)
    for t, col in (("poor", "#e34948"), ("mid", "#9a9893"), ("good", "#1baf7a")):
        x = cov[cov["rock_tercile"] == t].groupby("fpy")["cal_rate_ratio_19_24_vs_4_6"].median()
        axs[1].plot(list(x.index), list(x.values), "o-", color=col, label=f"{t} rock")
    axs[1].set_title("Shape: rate months 19–24 / 4–6 by rock tercile (median, raw)", fontsize=9)
    axs[1].legend(fontsize=8)
    axs[1].grid(alpha=0.3)
    fig.tight_layout()
    return _png(fig)


def render(s: dict[str, Any], rock: pd.DataFrame, yeff: pd.DataFrame, het: pd.DataFrame, st: pd.DataFrame, png: str) -> str:
    yrs = [y for y in YEARS if y != "2018"]
    c = s["coverage"]
    return "\n".join([
        "<!doctype html><html><head><meta charset=utf-8><meta name=viewport content='width=device-width,initial-scale=1'><title>BOX drift decomposition</title>",
        f"<style>{_CSS} body{{overflow-x:hidden}} table{{display:block;overflow-x:auto;max-width:100%}}</style></head><body>",
        "<h1>BOX — vintage drift decomposition: time / practice vs remaining-inventory rock vs spacing</h1>",
        (f"<div class=meta>built {s['built_at']} · gate-1 WCA wells fp 2016–2024 in a TC area of record ({c['n_wells']:,}; rock proxy covered {c['n_covered']:,}; "
         f"{c['n_reference']:,} reference wells 2016–19) · rock proxy = median 12-mo oil/kft of the 15 nearest 2016–19 wells (6–13k ft laterals, self excluded), covered "
         "when the 15th is within 3 mi · within-area (TC area fixed effects) throughout · read-only</div>"),
        f"<div class=meta>Coverage by vintage: {', '.join(f'{k}: {v:.0%}' for k, v in c['covered_share_by_vintage'].items())}</div>",
        f"<img src='{png}'>",
        "<h2>(i) Does the rock under newer wells get poorer? Within-area year effect on the fixed rock proxy (vs 2018)</h2>", _table(rock, {y: "+.1%" for y in yrs}),
        "<h2>(ii) Year effects (vs 2018) as blocks are added — level, shape (peak-free), shape2 (cum-24 / cum-6)</h2>",
        "<div class=meta>absorbed = share of the mean 2021–24 effect (with lateral) removed by the block. Early time is a diagnostic: it is not known before a well starts.</div>",
        _table(yeff, {**{y: "+.1%" for y in yrs}, "mean_2021_24": "+.1%", "absorbed_vs_lateral": ".0%"}),
        "<h2>(iii) Post-2021 effect by area development intensity and by rock tercile (within area, lateral + rock controlled)</h2>",
        _table(het, {"post2021_effect": "+.1%", "t": ".1f"}),
        "<h2>(iv) Step vs trend: ln y ~ area FE + controls + post-2021 step + linear year trend</h2>",
        _table(st, {"step_2021": "+.1%", "step_t": ".1f", "trend_per_year": "+.2%", "trend_t": ".1f", "rock_coef": ".3f", "rock_t": ".1f"}),
        "<div class=meta>Classical SEs; neighbouring wells are correlated, so read |t| below ~3 as weak.</div>",
        "</body></html>"])
