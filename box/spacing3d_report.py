"""BOX — 3-D spacing prototype (read-only): compute box.spacing3d features for the WCA wells and test Michael's
hypothesis (2026-10-12) that the post-month-6 decline drift is the spacing regime of the average well getting tighter.

Universe: every producing Delaware horizontal (any bench) whose lateral lies in the WCA subjects' bounding box + 1 mi
(curated.wells, sql/47's lateral line rule: LP -> BHL else the whole stick; bench = TVD-corrected formation_blueox).
Subjects: gate-1 WCA wells (exclusions dropped), first production >= 2016, real lateral, midpoint in a TC area of record.

Tests:
  1. Has spacing tightened by vintage? Feature medians by first-production year, and the within-area year effect on
     each feature.
  2. Does it explain the shape drift? ln(cum-24 / cum-6) on year dummies + area FE, adding: 3-D spacing as of first
     production -> + parent depletion -> + Novi WellSpacing (head-to-head) -> + children arriving within 24 months
     (diagnostic: not knowable at first production) -> + early-time behaviour. Same well set for every spec.
  3. Level: ln(12-mo oil / kft) with the same blocks.
Nothing is written to the warehouse.
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

from box import edge_gap as eg
from box import edge_gap_report as egr
from box import exclusions
from box import shape_drift as sd
from box import spacing3d as s3
from box import tc_curve_report as rep
from box.edge_gap_report import _CSS, _png, _table

BASIN = "delaware"
FP_MIN = dt.date(2016, 1, 1)
BBOX_PAD_DEG = 0.02  # ~1 mi

_UNIVERSE_SQL = """
SELECT w.api10, COALESCE(t.corrected_code, fb.formation_blueox, '(unmapped)') AS bench, w.first_production_date, w.tvd_ft,
       extensions.ST_AsText(CASE
           WHEN w.landing_point_lat IS NOT NULL AND w.landing_point_lon IS NOT NULL
            AND NOT extensions.ST_Equals(extensions.ST_SetSRID(extensions.ST_Point(w.landing_point_lon, w.landing_point_lat), 4326),
                                         extensions.ST_EndPoint(w.wellstick_geom))
           THEN extensions.ST_MakeLine(extensions.ST_SetSRID(extensions.ST_Point(w.landing_point_lon, w.landing_point_lat), 4326),
                                       extensions.ST_EndPoint(w.wellstick_geom))
           ELSE w.wellstick_geom END)
FROM curated.wells w
LEFT JOIN curated.formation_blueox fb    ON fb.api10 = w.api10
LEFT JOIN curated.formation_blueox_tvd t ON t.api10 = w.api10
WHERE COALESCE(w.novi_slant_calculated, w.enverus_trajectory) ILIKE '%%horizontal%%'
  AND w.first_production_date IS NOT NULL AND w.wellstick_geom IS NOT NULL
  AND w.wellstick_geom && extensions.ST_MakeEnvelope(%(x0)s, %(y0)s, %(x1)s, %(y1)s, 4326)
"""
_CUM_SQL = "SELECT api10, prod_date, cumulative_oil_bbl FROM curated.production WHERE api10 = ANY(%(a)s) ORDER BY api10, prod_date"

FEATS_FP = ["ln_lat_spacing", "ln_xsec", "n_ellipse", "bounded_sides"]
FEATS_DEP = [*FEATS_FP, "ln1p_parent_cum"]
NOVI = ["ln_closest_xy", "wells_in_radius", "stack_z", "boundedness", "is_child", "parent_count"]


def pull_universe(conn: Any, subj: pd.DataFrame) -> pd.DataFrame:
    b = {"x0": float(subj.mid_lon.min()) - 0.25, "y0": float(subj.mid_lat.min()) - 0.25, "x1": float(subj.mid_lon.max()) + 0.25, "y1": float(subj.mid_lat.max()) + 0.25}
    u = pd.DataFrame(rep._read(conn, _UNIVERSE_SQL, b), columns=["api10", "bench", "fp", "tvd_ft", "wkt"])
    u["tvd_ft"] = pd.to_numeric(u["tvd_ft"], errors="coerce")
    u = u.drop_duplicates("api10").reset_index(drop=True)
    u["geom"] = eg.to_ft([shapely.from_wkt(w) for w in u["wkt"]])
    return u.drop(columns="wkt")


def pull_cum(conn: Any, ids: list[str], chunk: int = 2000) -> dict[str, tuple[np.ndarray, np.ndarray]]:
    out: dict[str, tuple[np.ndarray, np.ndarray]] = {}
    for i in range(0, len(ids), chunk):
        d = pd.DataFrame(rep._read(conn, _CUM_SQL, {"a": ids[i : i + chunk]}), columns=["api10", "d", "c"])
        for a, g in d.groupby("api10"):
            out[a] = (np.array([np.datetime64(x) for x in g["d"]]), pd.to_numeric(g["c"], errors="coerce").ffill().fillna(0.0).to_numpy(float))
    return out


def cum_before(series: tuple[np.ndarray, np.ndarray] | None, when: dt.date) -> float:
    if series is None:
        return 0.0
    d, c = series
    k = int(np.searchsorted(d, np.datetime64(when), side="left")) - 1
    return float(c[k]) if k >= 0 else 0.0


def build_pairs(conn: Any, subj: pd.DataFrame) -> dict[str, Any]:
    """Co-extent pairs for every subject with geometry + the parents' cumulative oil series (one pass; reused by the
    backtest per fold)."""
    u = pull_universe(conn, subj)
    pos = {a: i for i, a in enumerate(u["api10"])}
    s_idx = [pos[a] for a in subj["api10"] if a in pos]
    lines = list(u["geom"])
    tree = shapely.STRtree(lines)
    pairs: dict[str, list[s3.Pair]] = {}
    parents_needed: set[str] = set()
    for i in s_idx:
        a, g, tvd, fp = u.at[i, "api10"], lines[i], float(u.at[i, "tvd_ft"]), u.at[i, "fp"]
        ps = []
        for j in tree.query(g, predicate="dwithin", distance=s3.GATE):
            if j == i:
                continue
            p = s3.pair_geometry(g, lines[j], tvd, float(u.at[j, "tvd_ft"]), (u.at[j, "fp"] - fp).days, u.at[j, "api10"])
            if p is not None:
                ps.append(p)
                if p.relation == "parent" and abs(p.dz) <= s3.PARENT_DZ:
                    parents_needed.add(p.nbr)
        pairs[a] = ps
    return {"pairs": pairs, "cum": pull_cum(conn, sorted(parents_needed)), "length": {u.at[i, "api10"]: float(lines[i].length) for i in s_idx},
            "fp": {u.at[i, "api10"]: u.at[i, "fp"] for i in s_idx},
            "meta": {"n_universe": len(u), "n_subjects": len(subj), "n_subjects_with_geometry": len(s_idx),
                     "n_pairs": int(sum(len(v) for v in pairs.values())), "n_parents_cum": len(parents_needed)}}


def features_table(P: dict[str, Any], ids: Any, cap: dt.date | None = None) -> pd.DataFrame:
    """Per-well features as of first production; parent cum is read at min(first production, cap) — a hindcast at a
    cutoff cannot know production after it."""
    rows = []
    for a in ids:
        if a not in P["pairs"]:
            continue
        ps, fp = P["pairs"][a], P["fp"][a]
        when = fp if cap is None or fp <= cap else cap
        pc = {p.nbr: cum_before(P["cum"].get(p.nbr), when) for p in ps if p.relation == "parent" and abs(p.dz) <= s3.PARENT_DZ}
        ch24 = [p for p in ps if p.relation == "child" and p.dfp_days <= 730]
        rows.append({"api10": a, "geom_lateral_ft": P["length"][a], **s3.features(ps, P["length"][a], pc, ch24)})
    f = pd.DataFrame(rows)
    if len(f):
        f["ln_lat_spacing"] = np.log(f["lat_spacing_ft"].clip(lower=50))
        f["ln_xsec"] = np.log(f["xsec_ft2"].clip(lower=1e4))
        f["ln1p_parent_cum"] = np.log1p(f["parent_cum_kbbl_per_kft"].astype(float).clip(lower=0))
    return f


def compute(conn: Any, subj: pd.DataFrame) -> tuple[pd.DataFrame, dict[str, Any]]:
    P = build_pairs(conn, subj)
    return features_table(P, subj["api10"]).drop(columns=["ln_lat_spacing", "ln_xsec", "ln1p_parent_cum"]), {**P["meta"], "pairs": P["pairs"]}


def run(conn: Any, wells_dir: Path, out: Path) -> dict[str, Any]:
    out.mkdir(parents=True, exist_ok=True)
    wells, _ = exclusions.drop(egr.load_final_sets(wells_dir, ("WCA",)))
    wells["lateral_ft"] = pd.to_numeric(wells["lateral_length_ft"], errors="coerce")
    w = wells[np.array([f >= FP_MIN for f in wells["first_production_date"]]) & (wells["lateral_ft"] > 0).to_numpy()].reset_index(drop=True)
    areas = rep.pull_areas(conn)
    x, y = eg._transformer().transform(w["mid_lon"].to_numpy(float), w["mid_lat"].to_numpy(float))
    w["area_no"] = rep.assign_area(np.column_stack([np.asarray(x) * eg._M_TO_FT, np.asarray(y) * eg._M_TO_FT]), areas["geoms"])
    w = w[w["area_no"] > 0].reset_index(drop=True)
    feats, meta = compute(conn, w)
    # shape + controls (box.shape_drift), same definitions
    asof = rep.last_full_month(rep._read(conn, rep._MONTHS_SQL))
    ids = list(w["api10"])
    m = sd.monthly(rep.pull_production(conn, ids, asof), ids, asof)
    d = pd.concat([w, sd.shape_metrics(m)], axis=1)
    sp = pd.DataFrame(rep._read(conn, sd._SPACING_SQL, {"a": ids}), columns=["api10", "closest_xy", "wells_in_radius", "closest_two_avg_xy", "stack_z", "stagger_tan",
                                                                           "boundedness", "is_child", "parent_count", "lateral_closer_xy"])
    d = d.merge(sp, on="api10", how="left").merge(feats, on="api10", how="left")
    for c in ("closest_xy", "wells_in_radius", "stack_z", "boundedness", "parent_count"):
        d[c] = pd.to_numeric(d[c], errors="coerce")
    d["is_child"] = d["is_child"].astype(object).map({True: 1.0, False: 0.0, "true": 1.0, "false": 0.0})
    d["ln_closest_xy"] = np.log(d["closest_xy"].clip(lower=50))
    d["ln_lat_spacing"] = np.log(d["lat_spacing_ft"].clip(lower=50))
    d["ln_xsec"] = np.log(d["xsec_ft2"].clip(lower=1e4))
    d["ln1p_parent_cum"] = np.log1p(d["parent_cum_kbbl_per_kft"].clip(lower=0))
    d["fpy"] = [str(f.year) for f in d["first_production_date"]]
    d["ln_r24_6"] = np.log(d["r24_6"].where(d["r24_6"] > 0))
    d["ln_oil12_kft"] = np.log(pd.to_numeric(d["oil12_kft"], errors="coerce").where(lambda v: v > 0))
    d["ln_lat"] = np.log(d["lateral_ft"])
    # 1. trend by vintage
    trend = d.groupby("fpy").agg(n=("api10", "size"), lat_spacing_ft=("lat_spacing_ft", "median"), xsec_ft2=("xsec_ft2", "median"),
                                 n_ellipse=("n_ellipse", "mean"), bounded_sides=("bounded_sides", "mean"), parent_cum=("parent_cum_kbbl_per_kft", "median"),
                                 share_parent=("n_parent_ellipse", lambda s: float((s > 0).mean())), n_child_24mo=("n_child_24mo", "mean"),
                                 r24_6=("r24_6", "median")).reset_index()
    fe_trend = []
    for f in ("ln_lat_spacing", "ln_xsec", "n_ellipse", "ln1p_parent_cum", "n_child_24mo"):
        c = sd.fe_ols(d, f, [], ["area_no"])
        fe_trend.append({"feature": f, "n": c.attrs["n"], **{yr: float(v) for yr, v in c.items()}})
    fe_trend = pd.DataFrame(fe_trend)
    # 2./3. does it absorb the drift?
    early = ["peak_month", "m1_share6"]
    specs = [("area", []), ("+ lateral", ["ln_lat"]), ("+ 3-D spacing at first production", ["ln_lat", *FEATS_FP]),
             ("+ parent depletion", ["ln_lat", *FEATS_DEP]), ("Novi WellSpacing instead (head-to-head)", ["ln_lat", *NOVI]),
             ("+ children within 24 months (diagnostic)", ["ln_lat", *FEATS_DEP, "n_child_24mo"]),
             ("+ early time", ["ln_lat", *FEATS_DEP, "n_child_24mo", *early])]
    allc = sorted({c for _, cs in specs for c in cs})
    res_rows, coefs = [], {}
    for resp in ("ln_r24_6", "ln_oil12_kft"):
        pop = d.dropna(subset=[resp, *allc])
        for lab, cs in specs:
            c = sd.fe_ols(pop, resp, cs, ["area_no"])
            coefs[(resp, lab)] = c
            res_rows.append({"response": resp, "spec": lab, "n": c.attrs["n"], **{yr: float(np.expm1(v)) for yr, v in c.items()}})
    yeff = pd.DataFrame(res_rows)
    ctrl = []
    for resp, lab in (("ln_r24_6", "+ parent depletion"), ("ln_oil12_kft", "+ parent depletion"), ("ln_r24_6", "+ children within 24 months (diagnostic)")):
        full = coefs[(resp, lab)].attrs["coef"]
        pop = d.dropna(subset=[resp, *allc])
        for k in full.index:
            if k.startswith(("y_", "_c", "area_no_")):
                continue
            ctrl.append({"response": resp, "spec": lab, "control": k, "coef": float(full[k]), "effect_of_1sd": float(np.expm1(full[k] * pop[k].std()))})
    ctrl = pd.DataFrame(ctrl)
    med = mediation(d)
    case = d[d["well_name"].astype(str).str.contains("BURTON FLAT 3 1", na=False)][["api10", "well_name", "formation_blueox", "first_production_date", "lateral_ft",
                                                                                     "nn_left_ft", "nn_right_ft", "lat_spacing_ft", "xsec_ft2", "n_ellipse",
                                                                                     "parent_cum_kbbl_per_kft", "n_child_24mo", "r24_6", "oil12_kft"]]
    pop_med = d[["lat_spacing_ft", "xsec_ft2", "n_ellipse"]].median().to_dict()
    built = dt.datetime.now(tz=dt.UTC).astimezone().isoformat(timespec="seconds")
    summ = {"built_at": built, "asof": str(asof), **{k: v for k, v in meta.items() if k != "pairs"}, "params": {"gate_ft": s3.GATE, "min_overlap": s3.MIN_OVERLAP,
            "same_dz_ft": s3.SAME_DZ, "aniso": s3.ANISO, "ellipse_ft": s3.ELLIPSE, "parent_dz_ft": s3.PARENT_DZ, "codev_days": s3.CODEV_DAYS}, "population_median": pop_med}
    summ["mediation_n"] = med["n"]
    ctx = {"summary": summ, "trend": trend, "fe_trend": fe_trend, "yeff": yeff, "ctrl": ctrl, "case": case, "png": trend_png(d), "med": med}
    (out / "spacing3d.html").write_text(render(ctx), encoding="utf-8")
    d[["api10", "well_name", "operator", "area_no", "fpy", "formation_blueox", "lateral_ft", "n_pairs", "nn_left_ft", "nn_right_ft", "lat_spacing_ft", "xsec_ft2",
       "n_ellipse", "n_parent_ellipse", "bounded_sides", "parent_cum_kbbl_per_kft", "n_child_24mo", "r12_6", "r24_6", "oil12_kft",
       "closest_xy", "wells_in_radius", "stack_z", "boundedness", "is_child", "parent_count"]].to_csv(out / "wells_spacing3d.csv", index=False)
    for name, t in (("trend_by_vintage", trend), ("feature_year_effects", fe_trend), ("year_effects", yeff), ("controls", ctrl),
                    ("mediation_early_year", med["early_year"]), ("mediation_coefs", med["coefs"]), ("mediation_share", med["mediated"])):
        t.to_csv(out / f"{name}.csv", index=False)
    (out / "summary.json").write_text(json.dumps(summ, indent=2, default=str), encoding="utf-8")
    return {"summary": summ, "trend": trend, "fe_trend": fe_trend, "yeff": yeff, "ctrl": ctrl, "case": case, "med": med}


EARLY = ("peak_month", "m1_share6")
SPACING = ("ln_xsec", "ln_lat_spacing", "ln1p_parent_cum")


def mediation(d: pd.DataFrame) -> dict[str, pd.DataFrame]:
    """Does tighter spacing act on the post-month-6 shape THROUGH early-time behaviour?
    (a) early-time ~ year + area + lateral [+ spacing]: does spacing predict early time, and absorb its year trend?
    (b) ln r24_6 ~ year + area + lateral + spacing [+ early time]: how much of each spacing coefficient survives once
        early time is controlled (share mediated = 1 - direct / total). One well set for every model; classical SEs
        (neighbouring wells are correlated, so read |t| < ~3 as weak)."""
    num = ["ln_lat", *FEATS_DEP]
    pop = d.dropna(subset=["ln_r24_6", *EARLY, *num])
    rows_a, rows_c = [], []
    for e in EARLY:
        for lab, cs in (("year + area + lateral", ["ln_lat"]), ("+ 3-D spacing + depletion", num)):
            c = fe_years(pop, e, cs)
            rows_a.append({"response": e, "spec": lab, "n": c.attrs["n"], **{yr: float(v) for yr, v in c.items()}})
        full = fe_years(pop, e, num)
        for k in SPACING:
            co, se = float(full.attrs["coef"][k]), float(full.attrs["se"][k])
            rows_c.append({"model": f"{e} ~ spacing", "term": k, "coef": co, "t": co / se if se else np.nan, "effect_of_1sd": co * float(pop[k].std())})
    tot = fe_years(pop, "ln_r24_6", num)
    dirc = fe_years(pop, "ln_r24_6", [*num, *EARLY])
    med = []
    for k in SPACING:
        t_, d_ = float(tot.attrs["coef"][k]), float(dirc.attrs["coef"][k])
        med.append({"term": k, "total_coef": t_, "total_t": t_ / float(tot.attrs["se"][k]), "direct_coef": d_, "direct_t": d_ / float(dirc.attrs["se"][k]),
                    "share_mediated_by_early_time": (1 - d_ / t_) if t_ else np.nan, "total_effect_1sd": float(np.expm1(t_ * pop[k].std()))})
    for e in EARLY:
        rows_c.append({"model": "ln r24_6 ~ ... + early time", "term": e, "coef": float(dirc.attrs["coef"][e]), "t": float(dirc.attrs["coef"][e] / dirc.attrs["se"][e]),
                       "effect_of_1sd": float(dirc.attrs["coef"][e] * pop[e].std())})
    return {"early_year": pd.DataFrame(rows_a), "coefs": pd.DataFrame(rows_c), "mediated": pd.DataFrame(med), "n": len(pop)}


def fe_years(pop: pd.DataFrame, y: str, num: list[str]) -> pd.Series:
    return sd.fe_ols(pop, y, num, ["area_no"])


def trend_png(d: pd.DataFrame) -> str:
    fig, axs = plt.subplots(1, 3, figsize=(16, 3.8))
    yrs = sorted(y for y in d["fpy"].unique() if "2016" <= y <= "2025")
    for ax, col, lab in ((axs[0], "lat_spacing_ft", "lateral spacing, ft (mean of nearest left / right within ±250 ft TVD; unbounded = 2,640)"),
                         (axs[1], "xsec_ft2", "drainage cross-section, ft² (Voronoi cell, gunbarrel plane)"),
                         (axs[2], "n_child_24mo", "children inside 660 × 300 ft within the first 24 months (mean)")):
        q = d[d["fpy"].isin(yrs)].groupby("fpy")[col]
        if col == "n_child_24mo":
            ax.plot(yrs, [q.mean()[y] for y in yrs], "o-", color="#2a78d6")
        else:
            ax.fill_between(yrs, [q.quantile(0.25)[y] for y in yrs], [q.quantile(0.75)[y] for y in yrs], color="#2a78d6", alpha=0.15, label="P25–P75")
            ax.plot(yrs, [q.median()[y] for y in yrs], "o-", color="#2a78d6", label="median")
            ax.legend(fontsize=8)
        ax.set_title(lab, fontsize=9)
        ax.set_xlabel("first-production year")
        ax.grid(alpha=0.3)
    fig.tight_layout()
    return _png(fig)


def render(ctx: dict[str, Any]) -> str:
    s = ctx["summary"]
    yrs = [c for c in ctx["yeff"].columns if c.isdigit()]
    p = s["params"]
    return "\n".join([
        "<!doctype html><html><head><meta charset=utf-8><meta name=viewport content='width=device-width,initial-scale=1'><title>BOX 3-D spacing</title>",
        f"<style>{_CSS} body{{overflow-x:hidden}} table{{display:block;overflow-x:auto;max-width:100%}}</style></head><body>",
        "<h1>BOX — 3-D spacing prototype: is the decline drift the spacing regime getting tighter?</h1>",
        (f"<div class=meta>built {s['built_at']} · subjects = gate-1 WCA wells, first production ≥ 2016, in a TC area of record ({s['n_subjects_with_geometry']:,} with lateral geometry) · "
         f"neighbour universe = {s['n_universe']:,} producing Delaware horizontals, any bench · {s['n_pairs']:,} co-extent pairs (overlap ≥ {p['min_overlap']:.0%}, gate {p['gate_ft']:,.0f} ft) · "
         f"features as of first production (parents + codev ±{p['codev_days']} d; children excluded) · anisotropy A = {p['aniso']} · production through {s['asof']} · read-only prototype of SPACING_3D_SCOPE.md</div>"),
        f"<img src='{ctx['png']}'>",
        "<h2>1. Spacing by first-production year (no controls)</h2>",
        _table(ctx["trend"], {"lat_spacing_ft": ",.0f", "xsec_ft2": ",.0f", "n_ellipse": ".2f", "bounded_sides": ".2f", "parent_cum": ".1f", "share_parent": ".0%",
                              "n_child_24mo": ".2f", "r24_6": ".3f"}),
        "<h3>Within-area year effect on each feature (vs 2018; ln features = log change, counts = absolute change)</h3>",
        _table(ctx["fe_trend"], {y: "+.3f" for y in yrs}),
        "<h2>2. Does spacing absorb the decline drift? Year effect on cum-24 / cum-6 and on 12-mo oil / kft, inside a TC area (vs 2018, % change)</h2>",
        ("<div class=meta>Same well set for every spec within a response. Read across: if a block absorbs the drift, the 2021–2024 effects move toward 0. "
         "'Children within 24 months' is diagnostic only — not knowable when a well (or PUD) starts.</div>"),
        _table(ctx["yeff"], {y: "+.1%" for y in yrs}),
        "<h2>3. Feature effects (1-SD move)</h2>", _table(ctx["ctrl"], {"coef": ".4f", "effect_of_1sd": "+.1%"}),
        "<h2>4. Mediation — does spacing act on decline through early-time behaviour?</h2>",
        (f"<div class=meta>{ctx['med']['n']:,} wells with 24 months and every input; within TC area. (a) year effect on peak month (months) and on month-1 share of "
         "cum-6, without and with the spacing block; (b) spacing coefficients on early time; (c) each spacing term's coefficient on ln(cum-24 / cum-6) before (total) and after "
         "(direct) controlling for early time — share mediated = 1 − direct / total. Classical SEs; neighbouring wells are correlated, so |t| below ~3 is weak.</div>"),
        _table(ctx["med"]["early_year"], {y: "+.3f" for y in yrs}),
        _table(ctx["med"]["coefs"], {"coef": ".4f", "t": ".1f", "effect_of_1sd": "+.3f"}),
        _table(ctx["med"]["mediated"], {"total_coef": ".4f", "total_t": ".1f", "direct_coef": ".4f", "direct_t": ".1f", "share_mediated_by_early_time": ".0%", "total_effect_1sd": "+.1%"}),
        "<h2>5. Case: Burton Flat 3 1</h2>",
        _table(ctx["case"], {"lateral_ft": ",.0f", "nn_left_ft": ",.0f", "nn_right_ft": ",.0f", "lat_spacing_ft": ",.0f", "xsec_ft2": ",.0f", "parent_cum_kbbl_per_kft": ".1f",
                             "r24_6": ".3f", "oil12_kft": ",.0f"}),
        (f"<div class=meta>Population medians: lateral spacing {s['population_median']['lat_spacing_ft']:,.0f} ft, cross-section {s['population_median']['xsec_ft2']:,.0f} ft², "
         f"{s['population_median']['n_ellipse']:.0f} neighbours in the ellipse.</div>"),
        "</body></html>"])
