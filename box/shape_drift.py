"""BOX step 6 (fail branch) — why do newer WCA wells decline faster after month ~6? (read-only dig + page).

Rolling backtest (backtest/): BOX oil bias grows with months on production in every fold (cum-6 ~0, cum-12 −3…−8 %,
cum-24 −9…−10 %) and with cutoff year — a SHAPE drift. This dig measures shape directly, independent of BOX:

    r12_6 = cum-12 / cum-6,  r24_6 = cum-24 / cum-6     (calendar months from the first reported month)

on the gate-1 WCA wells (fp >= 2016, real lateral, exclusions dropped), and asks which covariates absorb the
first-production-year trend inside a TC area of record (area fixed effects), adding controls one block at a time:
  lateral + completion size (proppant / fluid per ft) -> Novi WellSpacing density (closest XY, wells in radius,
  stack Z, boundedness, child) -> operator -> early-time behaviour (peak month, month-1 share) -> uptime
  (producing days / calendar days, months 7–24). A producing-day version of r24_6 separates downtime from decline.
"""

from __future__ import annotations

import datetime as dt
import json
from collections.abc import Sequence
from pathlib import Path
from typing import Any

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

from box import edge_gap as eg
from box import edge_gap_report as egr
from box import exclusions
from box import tc_curve_report as rep
from box.edge_gap_report import _CSS, _png, _table

K = 36
FP_MIN = dt.date(2016, 1, 1)
TOP_OPERATORS = 15
_SPACING_SQL = """
SELECT DISTINCT ON ("API10") "API10", "ClosestWellXY", "WellsInRadius", "ClosestTwoAvgXY", "StackCloserZ", "StaggerCloserTangent",
       "BoundednessScore", "IsChild", "ParentCount", "LateralCloserXY"
FROM raw_novi."WellSpacing" WHERE "API10" = ANY(%(a)s) AND "DeletedAt" IS NULL
ORDER BY "API10", "ModifiedAt" DESC NULLS LAST
"""
_COMP_SQL = "SELECT api10, proppant_lbs_per_ft, fluid_bbl_per_ft FROM curated.wells_enriched WHERE api10 = ANY(%(a)s)"


# ----------------------------------------------------------------------------
# Pure pieces
# ----------------------------------------------------------------------------


def monthly(prod: pd.DataFrame, ids: Sequence[str], asof: dt.date, k: int = K) -> dict[str, np.ndarray]:
    """[wells, k] calendar-month oil / gas / producing days from each well's first reported month; NaN after asof."""
    out = {c: np.full((len(ids), k), np.nan) for c in ("oil", "gas", "pdays")}
    g = dict(tuple(prod.groupby("api10")))
    for i, a in enumerate(ids):
        p = g.get(a)
        if p is None:
            continue
        p = p.sort_values("prod_date")
        d0 = p["prod_date"].iloc[0]
        idx = np.array([(d.year - d0.year) * 12 + d.month - d0.month for d in p["prod_date"]])
        n = min(k, (asof.year - d0.year) * 12 + asof.month - d0.month + 1)
        for c, col in (("oil", "oil_bbl"), ("gas", "gas_mcf"), ("pdays", "producing_days")):
            v = np.zeros(k) if c != "pdays" else np.full(k, np.nan)
            m = idx < k
            v[idx[m]] = pd.to_numeric(p[col], errors="coerce").to_numpy(float)[m]
            if c != "pdays":
                v = np.nan_to_num(v, nan=0.0)
            out[c][i, :n] = v[:n]
    return out


def shape_metrics(m: dict[str, np.ndarray]) -> pd.DataFrame:
    o, pdy = m["oil"], m["pdays"]
    cum = np.cumsum(o, axis=1)
    c6, c12, c24 = cum[:, 5], cum[:, 11], cum[:, 23]
    with np.errstate(invalid="ignore", divide="ignore"):
        d = pd.DataFrame({"r12_6": c12 / c6, "r24_6": c24 / c6, "m1_share6": o[:, 0] / c6,
                          "peak_month": np.where(np.isfinite(o[:, :12]).all(axis=1), np.nanargmax(np.where(np.isfinite(o[:, :12]), o[:, :12], -1), axis=1) + 1, np.nan)})
        # uptime months 7-24 (producing days / calendar days); producing-day rate shape
        cal = 30.4375
        up = np.nanmean(np.where(np.isfinite(pdy[:, 6:24]), pdy[:, 6:24], np.nan), axis=1) / cal
        d["uptime_7_24"] = np.where(np.isfinite(o[:, 23]), up, np.nan)
        pdr = np.where((pdy > 0) & np.isfinite(pdy), o / pdy, np.nan)  # producing-day rate
        d["pd_rate_ratio_19_24_vs_4_6"] = np.nanmean(pdr[:, 18:24], axis=1) / np.nanmean(pdr[:, 3:6], axis=1)
        d["cal_rate_ratio_19_24_vs_4_6"] = np.nanmean(o[:, 18:24], axis=1) / np.nanmean(o[:, 3:6], axis=1)
    for c in ("r24_6", "uptime_7_24", "pd_rate_ratio_19_24_vs_4_6", "cal_rate_ratio_19_24_vs_4_6"):
        d.loc[~np.isfinite(o[:, 23]), c] = np.nan
    d.loc[~np.isfinite(o[:, 11]), "r12_6"] = np.nan
    return d


def fe_ols(df: pd.DataFrame, y: str, num: Sequence[str], cats: Sequence[str], year_col: str = "fpy", ref_year: str = "2018") -> pd.Series:
    """OLS of y on first-production-year dummies (vs ref_year) + numeric controls + categorical FEs; returns the year
    coefficients (rows with any missing input dropped)."""
    cols = [y, year_col, *num, *cats]
    d = df[cols].dropna()
    X = [pd.get_dummies(d[year_col].astype(str), prefix="y").drop(columns=f"y_{ref_year}", errors="ignore").astype(float)]
    if num:
        X.append(d[list(num)].astype(float))
    for c in cats:
        X.append(pd.get_dummies(d[c].astype(str), prefix=c, drop_first=True).astype(float))
    Xm = pd.concat(X, axis=1)
    Xm.insert(0, "_c", 1.0)
    b, *_ = np.linalg.lstsq(Xm.to_numpy(), d[y].to_numpy(float), rcond=None)
    coef = pd.Series(b, index=Xm.columns)
    out = coef[[c for c in coef.index if c.startswith("y_")]]
    out.index = [c[2:] for c in out.index]
    out.attrs["n"] = len(d)
    out.attrs["coef"] = coef
    return out.sort_index()


# ----------------------------------------------------------------------------
# Run
# ----------------------------------------------------------------------------


def run(conn: Any, wells_dir: Path, out: Path) -> dict[str, Any]:
    out.mkdir(parents=True, exist_ok=True)
    wells, _ = exclusions.drop(egr.load_final_sets(wells_dir, ("WCA",)))
    wells["lateral_ft"] = pd.to_numeric(wells["lateral_length_ft"], errors="coerce")
    w = wells[np.array([f >= FP_MIN for f in wells["first_production_date"]]) & (wells["lateral_ft"] > 0).to_numpy()].reset_index(drop=True)
    ids = list(w["api10"])
    asof = rep.last_full_month(rep._read(conn, rep._MONTHS_SQL))
    prod = rep.pull_production(conn, ids, asof)
    m = monthly(prod, ids, asof)
    d = pd.concat([w, shape_metrics(m)], axis=1)
    sp = pd.DataFrame(rep._read(conn, _SPACING_SQL, {"a": ids}),
                      columns=["api10", "closest_xy", "wells_in_radius", "closest_two_avg_xy", "stack_z", "stagger_tan", "boundedness", "is_child", "parent_count", "lateral_closer_xy"])
    cp = pd.DataFrame(rep._read(conn, _COMP_SQL, {"a": ids}), columns=["api10", "prop_ft", "fluid_ft"])
    d = d.merge(sp, on="api10", how="left").merge(cp, on="api10", how="left")
    for c in ("closest_xy", "wells_in_radius", "closest_two_avg_xy", "stack_z", "stagger_tan", "boundedness", "parent_count", "lateral_closer_xy", "prop_ft", "fluid_ft"):
        d[c] = pd.to_numeric(d[c], errors="coerce")
    d["is_child"] = d["is_child"].astype(object).map({True: 1.0, False: 0.0, "true": 1.0, "false": 0.0})
    areas = rep.pull_areas(conn)
    x, y = eg._transformer().transform(d["mid_lon"].to_numpy(float), d["mid_lat"].to_numpy(float))
    d["area_no"] = rep.assign_area(np.column_stack([np.asarray(x) * eg._M_TO_FT, np.asarray(y) * eg._M_TO_FT]), areas["geoms"])
    d = d[d["area_no"] > 0].copy()
    d["fpy"] = [str(f.year) for f in d["first_production_date"]]
    top = d["operator"].value_counts().index[:TOP_OPERATORS]
    d["op"] = np.where(d["operator"].isin(top), d["operator"], "other")
    d["ln_lat"] = np.log(d["lateral_ft"])
    d["ln_closest_xy"] = np.log(d["closest_xy"].clip(lower=50))
    d["gor12"] = 1000.0 * np.nansum(m["gas"][:, :12], axis=1)[d.index] / np.nansum(m["oil"][:, :12], axis=1)[d.index]
    d["ln_gor12"] = np.log(d["gor12"].where(d["gor12"] > 0))
    for c in ("r12_6", "r24_6", "pd_rate_ratio_19_24_vs_4_6", "cal_rate_ratio_19_24_vs_4_6"):
        d[f"ln_{c}"] = np.log(d[c].where(d[c] > 0))
    blocks = [
        ("area", [], []),
        ("+ lateral, completion size", ["ln_lat", "prop_ft", "fluid_ft"], []),
        ("+ Novi spacing (closest XY, wells in radius, stack Z, boundedness, child, parents)", ["ln_lat", "prop_ft", "fluid_ft", "ln_closest_xy", "wells_in_radius", "stack_z", "boundedness", "is_child", "parent_count"], []),
        ("+ operator", ["ln_lat", "prop_ft", "fluid_ft", "ln_closest_xy", "wells_in_radius", "stack_z", "boundedness", "is_child", "parent_count"], ["op"]),
        ("+ early time (peak month, month-1 share), GOR", ["ln_lat", "prop_ft", "fluid_ft", "ln_closest_xy", "wells_in_radius", "stack_z", "boundedness", "is_child", "parent_count", "peak_month", "m1_share6", "ln_gor12"], ["op"]),
        ("+ uptime months 7-24", ["ln_lat", "prop_ft", "fluid_ft", "ln_closest_xy", "wells_in_radius", "stack_z", "boundedness", "is_child", "parent_count", "peak_month", "m1_share6", "ln_gor12", "uptime_7_24"], ["op"]),
    ]
    # producing days are reported on a subset only: the calendar-shape specs run on every well with all non-uptime
    # controls (one population, comparable year effects); the uptime spec + the producing-day response on the subset
    common = d.dropna(subset=["ln_r24_6", *blocks[-2][1]])
    pdsub = d.dropna(subset=["ln_r24_6", "ln_pd_rate_ratio_19_24_vs_4_6", *blocks[-1][1]])
    rows, coefs = [], {}
    for lab, num, cats in blocks[:-1]:
        c = fe_ols(common, "ln_r24_6", num, ["area_no", *cats])
        coefs[(lab, "ln_r24_6")] = c
        rows.append({"spec": lab, "population": "all wells", "response": "ln_r24_6", "n": c.attrs["n"], **{yr: float(np.expm1(v)) for yr, v in c.items()}})
    for lab, num, cats, yv in ((blocks[-2][0], blocks[-2][1], blocks[-2][2], "ln_r24_6"), (blocks[-1][0], blocks[-1][1], blocks[-1][2], "ln_r24_6"),
                               (blocks[-2][0], blocks[-2][1], blocks[-2][2], "ln_pd_rate_ratio_19_24_vs_4_6")):
        c = fe_ols(pdsub, yv, num, ["area_no", *cats])
        coefs[(lab, yv, "pd")] = c
        rows.append({"spec": lab, "population": "wells with producing days", "response": yv, "n": c.attrs["n"], **{yr: float(np.expm1(v)) for yr, v in c.items()}})
    yeff = pd.DataFrame(rows)
    full = coefs[(blocks[-2][0], "ln_r24_6")].attrs["coef"]
    ctrl = pd.DataFrame({"control": [k for k in full.index if not k.startswith(("y_", "_c", "area_no_", "op_"))]})
    ctrl["coef"] = [float(full[k]) for k in ctrl["control"]]
    sd = common[ctrl["control"]].std()
    ctrl["effect_of_1sd"] = [float(np.expm1(full[k] * sd[k])) for k in ctrl["control"]]
    # raw by vintage (no controls)
    raw = d.groupby("fpy").agg(n24=("r24_6", lambda s: int(s.notna().sum())), r12_6=("r12_6", "median"), r24_6=("r24_6", "median"),
                                peak_month=("peak_month", "median"), m1_share6=("m1_share6", "median"), uptime_7_24=("uptime_7_24", "median"),
                                cal_19_24_vs_4_6=("cal_rate_ratio_19_24_vs_4_6", "median"), pd_19_24_vs_4_6=("pd_rate_ratio_19_24_vs_4_6", "median"),
                                lateral=("lateral_ft", "median"), prop_ft=("prop_ft", "median"), fluid_ft=("fluid_ft", "median"),
                                closest_xy=("closest_xy", "median"), wells_in_radius=("wells_in_radius", "median"), child=("is_child", "mean"),
                                oil12_kft=("oil12_kft", "median")).reset_index()
    prof = profile_png(m, d)
    built = dt.datetime.now(tz=dt.UTC).astimezone().isoformat(timespec="seconds")
    summ = {"built_at": built, "asof": str(asof), "n_wells": len(d), "n_common": len(common), "n_pd": len(pdsub)}
    (out / "shape.html").write_text(render(summ, raw, yeff, ctrl, prof), encoding="utf-8")
    raw.to_csv(out / "by_vintage.csv", index=False)
    yeff.to_csv(out / "year_effects.csv", index=False)
    ctrl.to_csv(out / "controls.csv", index=False)
    (out / "summary.json").write_text(json.dumps(summ, indent=2), encoding="utf-8")
    return {"summary": summ, "raw": raw, "yeff": yeff, "ctrl": ctrl}


def profile_png(m: dict[str, np.ndarray], d: pd.DataFrame) -> str:
    fig, axs = plt.subplots(1, 2, figsize=(14, 4.2))
    years = sorted(d["fpy"].unique())
    cmap = plt.get_cmap("Blues")
    for i, yr in enumerate(years):
        idx = d.index[d["fpy"] == yr].to_numpy()
        o = m["oil"][idx]
        ok = np.isfinite(o[:, 23]) if yr <= "2024" else np.isfinite(o[:, 11])
        if ok.sum() < 30:
            continue
        o = o[ok]
        c6 = np.cumsum(o, axis=1)[:, 5:6]
        norm = np.nanmean(o / c6, axis=0)
        col = cmap(0.3 + 0.7 * i / max(1, len(years) - 1))
        axs[0].plot(np.arange(1, K + 1), norm, color=col, lw=1.6, label=f"{yr} (n {int(ok.sum())})")
        pd_ = m["pdays"][idx][ok]
        axs[1].plot(np.arange(1, K + 1), np.nanmean(pd_, axis=0) / 30.4375, color=col, lw=1.6)
    axs[0].set_yscale("log")
    axs[0].set_title("mean monthly oil / own cum-6, by first-production year (wells with 24 months)", fontsize=10)
    axs[0].set_xlabel("calendar month from first report")
    axs[0].legend(fontsize=7, ncol=2)
    axs[1].set_title("mean producing days / calendar days", fontsize=10)
    axs[1].set_xlabel("calendar month from first report")
    axs[1].set_ylim(0.5, 1.02)
    for ax in axs:
        ax.grid(alpha=0.3)
    fig.tight_layout()
    return _png(fig)


def render(s: dict[str, Any], raw: pd.DataFrame, yeff: pd.DataFrame, ctrl: pd.DataFrame, prof: str) -> str:
    yrs = [c for c in yeff.columns if c.isdigit()]
    return "\n".join([
        "<!doctype html><html><head><meta charset=utf-8><meta name=viewport content='width=device-width,initial-scale=1'><title>BOX shape drift</title>",
        f"<style>{_CSS} body{{overflow-x:hidden}} table{{display:block;overflow-x:auto;max-width:100%}}</style></head><body>",
        "<h1>BOX step 6 (fail branch) — shape drift: do newer WCA wells decline faster after month 6?</h1>",
        (f"<div class=meta>built {s['built_at']} · gate-1 WCA wells (exclusions dropped), first production ≥ 2016, real lateral, midpoint in a TC area of record · "
         f"production curated.production through {s['asof']} (calendar months from the first report) · {s['n_wells']:,} wells; regressions on the {s['n_common']:,} with "
         f"24 months and every non-uptime control (uptime + producing-day specs on the {s['n_pd']:,} that report producing days) · read-only</div>"),
        f"<img src='{prof}'>",
        "<h2>1. By first-production year (medians, no controls)</h2>",
        ("<div class=meta>r24_6 = cum-24 / cum-6 (lower = steeper after month 6). cal / pd 19–24 vs 4–6 = mean calendar-day / producing-day rate in months 19–24 over months 4–6 "
         "(the producing-day version removes downtime). Spacing columns are Novi WellSpacing, as of first production.</div>"),
        _table(raw, {c: ".3f" for c in ("r12_6", "r24_6", "m1_share6", "uptime_7_24", "cal_19_24_vs_4_6", "pd_19_24_vs_4_6", "child")} |
               {c: ",.0f" for c in ("lateral", "prop_ft", "fluid_ft", "closest_xy", "oil12_kft")} | {"wells_in_radius": ".1f", "peak_month": ".1f"}),
        "<h2>2. Year effect on shape inside a TC area, controls added block by block (vs 2018; % change)</h2>",
        ("<div class=meta>Each row: OLS of ln(response) on first-production-year dummies + area FE + the listed controls, on one common well set. "
         "If a block absorbs the drift, the year effects shrink toward 0 when it is added.</div>"),
        _table(yeff, {y: "+.1%" for y in yrs}),
        "<h2>3. Controls in the full calendar-day model (ln r24_6, all wells) — effect of a 1-SD move</h2>",
        _table(ctrl, {"coef": ".4f", "effect_of_1sd": "+.1%"}),
        "</body></html>"])
