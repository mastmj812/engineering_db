"""BOX step 9a — BS2_S + WCXY tuning view (read-only): regression guard, D53 cells per bench, walk-forward haircuts,
D62-style tables + D92 realised factors, BS2_S south-edge strike behaviour, WCXY extent coverage; one review page.

Pure functions over the outputs of `scripts.box_acceptance --fold analog` (cells_<tag>.csv, summary_<tag>.json,
view_<tag>_<yyyy>.csv.gz, months_<tag>.npz) plus a few read-only warehouse pulls done by scripts/box_tune9a.py.
Nothing here re-scores anything: every number on the page is read from those files or computed from them.
"""

from __future__ import annotations

import json
from collections.abc import Iterable, Mapping, Sequence
from pathlib import Path
from typing import Any

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import shapely

from box import acceptance as ac
from box import edge_gap as eg
from box import production as pr
from box import strike as stk
from box.edge_gap_report import _CSS, _png, _table

KEYS = ["cutoff", "stream", "horizon", "variant"]
STATS = ["pkg_bias", "pkg_band", "bench_bias", "bench_band"]
GUARD_VARIANTS = ("di_p50", "box_v2", "di_p50_wf", "box_v2_wf")
EDGE_MI = 5.0  # a scored location within this of the extent boundary is an edge location
SOUTH = (135.0, 225.0)  # bearing (deg, from the extent centroid to the nearest boundary point) of the south edge


# ----------------------------------------------------------------------------
# Regression guard
# ----------------------------------------------------------------------------


def identity(cells: pd.DataFrame, record: pd.DataFrame, variants: Sequence[str] = GUARD_VARIANTS) -> pd.DataFrame:
    """Per (cutoff, variant): record rows found, package / well counts equal, max |diff| per statistic (NaN-aware: a NaN on
    one side only counts as a mismatch, reported as inf)."""
    rows = []
    rec = record[record.variant.isin(variants)]
    for (c, v), b in rec.groupby(["cutoff", "variant"]):
        a = cells[(cells.cutoff == c) & (cells.variant == v)].set_index(KEYS).sort_index()
        b = b.set_index(KEYS).sort_index()
        common = a.index.intersection(b.index)
        a2, b2 = a.loc[common], b.loc[common]
        r = {"cutoff": c, "variant": v, "record_rows": len(b), "found": len(common),
             "counts_equal": bool(len(common) == len(b) and (a2[["n_packages", "n_wells"]].fillna(-1).to_numpy() == b2[["n_packages", "n_wells"]].fillna(-1).to_numpy()).all()),
             "verdicts_equal": bool(len(common) == len(b) and (a2["verdict"].to_numpy() == b2["verdict"].to_numpy()).all())}
        for s in STATS:
            x, y = a2[s].to_numpy(float), b2[s].to_numpy(float)
            both = np.isfinite(x) & np.isfinite(y)
            one = np.isfinite(x) ^ np.isfinite(y)
            r[f"max_abs_{s}"] = float("inf") if one.any() else (float(np.max(np.abs(x[both] - y[both]))) if both.any() else 0.0)
        rows.append(r)
    return pd.DataFrame(rows)


def actuals_drift(new_dir: Path, old_dir: Path, cols: Sequence[str] = ("actual_oil12", "actual_oil24", "actual_gas12", "lateral_ft", "spacing_ft")) -> pd.DataFrame:
    """Per cutoff: scored holdout wells in both frames, and per column the wells whose value changed + the worst relative change
    (old = runs/box7a/view_<yyyy>.csv.gz written by the 7a re-run, new = this run's guard_holdout views)."""
    rows = []
    for f in sorted(old_dir.glob("view_*.csv.gz")):
        y = f.stem.split("_")[1].split(".")[0]
        nf = new_dir / f"view_guard_holdout_{y}.csv.gz"
        if not nf.exists():
            continue
        m = pd.read_csv(f, dtype={"api10": str}).merge(pd.read_csv(nf, dtype={"api10": str}), on="api10", suffixes=("_o", "_n"))
        r: dict[str, Any] = {"cutoff": y, "wells": len(m)}
        for c in cols:
            if f"{c}_o" not in m:
                continue
            o, n = m[f"{c}_o"].astype(float), m[f"{c}_n"].astype(float)
            d = (n - o).abs()
            r[f"{c} changed"] = int((d > 1e-9).sum())
            r[f"{c} max rel"] = float(np.nanmax(d / o.abs().replace(0, np.nan))) if len(m) else np.nan
        rows.append(r)
    return pd.DataFrame(rows)


def guard_verdict(t: pd.DataFrame, tol: float = 1e-12) -> bool:
    return bool(len(t) and t["counts_equal"].all() and t["verdicts_equal"].all() and (t[[f"max_abs_{s}" for s in STATS]] <= tol).all().all())


# ----------------------------------------------------------------------------
# Haircut tables (D62-style) + D92 realised factors
# ----------------------------------------------------------------------------


def haircut_table(cells: pd.DataFrame, variant: str = "box_v2", min_packages: int = ac.MIN_PACKAGES) -> pd.DataFrame:
    """production.haircut_table's rule (package-weighted mean box_v2 bias over judged cells), one row per stream x horizon,
    tolerant of a horizon with no judged cell (factor NaN) — tuning cells of a new bench may not reach cum-48."""
    c = cells[(cells["variant"] == variant) & (cells["n_packages"] >= min_packages) & np.isfinite(cells["pkg_bias"].astype(float))]
    rows = []
    for s in ac.STREAMS:
        for k in pr.HORIZONS:
            x = c[(c["stream"] == s) & (c["horizon"] == k)]
            if x.empty:
                rows.append({"stream": s, "horizon": k, "factor": np.nan, "bias": np.nan, "n_packages": 0, "n_cells": 0, "cutoffs": ""})
                continue
            w = x["n_packages"].to_numpy(float)
            b = float(np.sum(w * x["pkg_bias"].to_numpy(float)) / w.sum())
            rows.append({"stream": s, "horizon": k, "factor": 1.0 + b, "bias": b, "n_packages": int(w.sum()), "n_cells": len(x),
                         "cutoffs": ", ".join(sorted(str(v)[:4] for v in x["cutoff"]))})
    return pd.DataFrame(rows)


def realised_d92(months: np.ndarray, tab: pd.DataFrame, stream: str) -> dict[str, Any]:
    """Apply production.apply_haircut_c1 (the D92 rate shape) with `tab`'s factors to each location's uptime-free box_v2
    months (48 months suffice: the knots are at 12-48 and g is held after 48). Median / P10-P90 of the realised cum factor."""
    t = tab[(tab.stream == stream) & np.isfinite(tab.factor)]
    if len(t) < 2:
        return {"n": 0}
    knots = {int(k): {"factor": float(f)} for k, f in zip(t.horizon, t.factor, strict=True)}
    real, g1, g48, bad = {str(k): [] for k in knots}, [], [], 0
    for m in months:
        if not np.isfinite(m).all() or m.sum() <= 0:
            continue
        try:
            _, info = pr.apply_haircut_c1(m, knots)
        except ValueError:
            bad += 1
            continue
        for k, r in info["realised"].items():
            real[k].append(r)
        g1.append(info["g_month1"])
        g48.append(info["g_tail"])
    q = (lambda v: {"p50": float(np.median(v)), "p90": float(np.quantile(v, 0.1)), "p10": float(np.quantile(v, 0.9))} if v else None)
    return {"n": len(g1), "n_failed": bad, "target": {str(k): v["factor"] for k, v in knots.items()},
            "realised": {k: q(v) for k, v in real.items()}, "g_month1": q(g1), "g_month48": q(g48)}


def load_months(path: Path) -> dict[str, dict[str, np.ndarray]]:
    z = np.load(path, allow_pickle=False)
    years = sorted({k.split("_")[0] for k in z.files})
    return {y: {"api10": z[f"{y}_api10"], "oil": z[f"{y}_oil"], "gas": z[f"{y}_gas"], "F_oil": z[f"{y}_F_oil"], "F_gas": z[f"{y}_F_gas"]} for y in years}


# ----------------------------------------------------------------------------
# Edge geometry (BS2_S south edge, D55)
# ----------------------------------------------------------------------------


def _bearing(dx: np.ndarray, dy: np.ndarray) -> np.ndarray:
    return (np.degrees(np.arctan2(dx, dy)) + 360.0) % 360.0


def edge_classes(x: np.ndarray, y: np.ndarray, extent_ft: Any, edge_mi: float = EDGE_MI, south: tuple[float, float] = SOUTH) -> pd.DataFrame:
    """Per location (UTM 13N ft): distance to the extent boundary (mi), bearing from the extent centroid to the nearest
    boundary point, the boundary's local axial azimuth there, and the region: south_edge / other_edge / interior."""
    bd = extent_ft.boundary
    c = extent_ft.centroid
    pts = shapely.points(x, y)
    dist = shapely.distance(pts, bd) / eg.FT_PER_MI
    s = shapely.line_locate_point(bd, pts)
    near = shapely.line_interpolate_point(bd, s)
    a = shapely.line_interpolate_point(bd, np.maximum(s - 2640.0, 0.0))
    b = shapely.line_interpolate_point(bd, s + 2640.0)
    nx, ny = shapely.get_x(near), shapely.get_y(near)
    brg = _bearing(nx - c.x, ny - c.y)
    edge_az = _bearing(shapely.get_x(b) - shapely.get_x(a), shapely.get_y(b) - shapely.get_y(a)) % 180.0
    region = np.where(dist > edge_mi, "interior", np.where((brg >= south[0]) & (brg <= south[1]), "south_edge", "other_edge"))
    return pd.DataFrame({"edge_dist_mi": dist, "edge_bearing_deg": brg, "edge_az_deg": edge_az, "region": region})


def region_table(v: pd.DataFrame, horizons: Iterable[int] = (12, 24, 36)) -> pd.DataFrame:
    """Per region: scored locations, strike share, radius reached, axial strike-vs-edge angle, box_v2_wf package bias / band
    (packages restricted to the region's members) and the benchmark's, oil."""
    rows = []
    for reg, g in v.groupby("region"):
        st = g[g["v2_mode"] == "strike"]
        ang = [stk.angle_diff(float(a), float(e)) for a, e in zip(st["v2_strike_az_deg"], st["edge_az_deg"], strict=True) if np.isfinite(a)]
        r = {"region": reg, "locations": len(g), "strike share": float((g["v2_mode"] == "strike").mean()),
             "past 5 mi share": float((g["v2_radius_mi"] > 5.0).mean()), "radius p50 mi": float(g["v2_radius_mi"].median()),
             "strike vs edge angle p50 deg": float(np.median(ang)) if ang else np.nan, "n strike": len(st)}
        for k in horizons:
            col = f"pred_box_v2_wf_oil{k}"
            if col not in g:
                continue
            pp = ac.package_errors(g, "package", f"actual_oil{k}", col)
            bp = ac.package_errors(g, "package", f"actual_oil{k}", f"bench_oil{k}")
            r[f"oil{k} packages"] = len(pp)
            r[f"oil{k} bias"] = float(pp["err"].mean()) if len(pp) else np.nan
            r[f"oil{k} bench bias"] = float(bp["err"].mean()) if len(bp) else np.nan
        rows.append(r)
    return pd.DataFrame(rows)


def mode_table(v: pd.DataFrame, horizons: Iterable[int] = (12, 24, 36)) -> pd.DataFrame:
    """box_v2_wf oil package bias by search mode (circle vs strike), packages restricted to that mode's locations."""
    rows = []
    for m, g in v.groupby("v2_mode"):
        r = {"mode": m, "locations": len(g)}
        for k in horizons:
            pp = ac.package_errors(g, "package", f"actual_oil{k}", f"pred_box_v2_wf_oil{k}")
            r[f"oil{k} packages"], r[f"oil{k} bias"] = len(pp), float(pp["err"].mean()) if len(pp) else np.nan
        rows.append(r)
    return pd.DataFrame(rows)


# ----------------------------------------------------------------------------
# Pictures
# ----------------------------------------------------------------------------


def _outline(ax: Any, g: Any, **kw: Any) -> None:
    for p in getattr(g, "geoms", [g]):
        ax.plot(*np.asarray(p.exterior.coords).T / eg.FT_PER_MI, **kw)
        for h in p.interiors:
            ax.plot(*np.asarray(h.coords).T / eg.FT_PER_MI, **kw)


def edge_map_png(v: pd.DataFrame, extent_ft: Any, title: str) -> str:
    fig, ax = plt.subplots(figsize=(8.5, 8))
    _outline(ax, extent_ft, color="#111827", lw=1)
    colours = {"interior": "#9ca3af", "other_edge": "#2a78d6", "south_edge": "#eb6834"}
    for reg, g in v.groupby("region"):
        circ, strk = g[g.v2_mode != "strike"], g[g.v2_mode == "strike"]
        ax.scatter(circ.x / eg.FT_PER_MI, circ.y / eg.FT_PER_MI, s=8, c=colours[reg], marker="o", label=f"{reg} circle ({len(circ)})", alpha=0.7)
        ax.scatter(strk.x / eg.FT_PER_MI, strk.y / eg.FT_PER_MI, s=22, c=colours[reg], marker="^", label=f"{reg} strike ({len(strk)})", edgecolors="#111827", lw=0.4)
        for r in strk.itertuples():  # strike tick: the ellipse's long axis
            t = np.radians(float(r.v2_strike_az_deg))
            dx, dy = 1.2 * np.sin(t), 1.2 * np.cos(t)
            ax.plot([r.x / eg.FT_PER_MI - dx, r.x / eg.FT_PER_MI + dx], [r.y / eg.FT_PER_MI - dy, r.y / eg.FT_PER_MI + dy], color="#111827", lw=0.6)
    ax.set_aspect("equal")
    ax.set_title(title, fontsize=10)
    ax.set_xlabel("UTM 13N easting (mi)")
    ax.legend(fontsize=7, loc="best")
    fig.tight_layout()
    return _png(fig)


def wcxy_map_png(extent_ft: Any, prod_xy: np.ndarray, pud: pd.DataFrame) -> str:
    fig, ax = plt.subplots(figsize=(8.5, 8))
    _outline(ax, extent_ft, color="#111827", lw=1)
    ax.scatter(prod_xy[:, 0] / eg.FT_PER_MI, prod_xy[:, 1] / eg.FT_PER_MI, s=4, c="#1baf7a", label=f"WCXY producers fp ≥ 2016 ({len(prod_xy)})")
    for lab, g, col in (("PUD inside, ≤ 5 mi to a WCXY producer", pud[pud.inside & (pud.d_wcxy_mi <= 5)], "#2a78d6"),
                        ("PUD inside, > 5 mi", pud[pud.inside & (pud.d_wcxy_mi > 5)], "#eb6834"),
                        ("PUD outside the WCA extent", pud[~pud.inside], "#9ca3af")):
        ax.scatter(g.x / eg.FT_PER_MI, g.y / eg.FT_PER_MI, s=5, c=col, marker="s", label=f"{lab} ({len(g)})", alpha=0.7)
    ax.set_aspect("equal")
    ax.set_title("WCXY: producers, reconciled PUDs (run 7 universe) and the WCA extent of record", fontsize=10)
    ax.legend(fontsize=7, loc="best")
    fig.tight_layout()
    return _png(fig)


# ----------------------------------------------------------------------------
# Page
# ----------------------------------------------------------------------------


def record_cells(cells: pd.DataFrame, variants: Sequence[str]) -> pd.DataFrame:
    """One row per (stream, horizon, cutoff): package bias per variant, record (box_v2_wf) band, benchmark, verdict."""
    piv = cells.pivot_table(index=["stream", "horizon", "cutoff"], columns="variant", values="pkg_bias").reindex(columns=list(variants))
    piv.columns = [f"{c} bias" for c in piv.columns]
    rec = cells[cells.variant == ac.RECORD_V2].set_index(["stream", "horizon", "cutoff"])
    t = piv.join(rec[["n_packages", "pkg_band", "bench_bias", "bench_band", "verdict"]])
    w = cells[cells.variant == f"box_v2{ac.WCA_WF}"].set_index(["stream", "horizon", "cutoff"])
    if len(w):
        t = t.join(w[["verdict"]].rename(columns={"verdict": "verdict (WCA haircut)"}))
    t["sf band box_v2_wf"] = [ac.scale_free(b, x) for b, x in zip(rec["pkg_band"].reindex(t.index), rec["pkg_bias"].reindex(t.index), strict=True)]
    t["sf band bench"] = [ac.scale_free(b, x) for b, x in zip(t["bench_band"], t["bench_bias"], strict=True)]
    return t.reset_index()


def _pct_fmt(cols: Iterable[str]) -> dict[str, str]:
    return {c: "+.1%" for c in cols if c.endswith("bias")} | {c: ".2f" for c in cols if "band" in c}


def render(ctx: Mapping[str, Any]) -> str:
    s = ctx["meta"]
    p = ["<!doctype html><html><head><meta charset=utf-8><meta name=viewport content='width=device-width,initial-scale=1'><title>BOX step 9a</title>",
         f"<style>{_CSS} body{{overflow-x:hidden}} table{{display:block;overflow-x:auto;max-width:100%}} img{{max-width:100%}}</style></head><body>",
         "<h1>BOX step 9a — BS2_S + WCXY tuning view (read-only)</h1>",
         (f"<div class=meta>built {s['built_at']} · frozen spec <b>box_v2_wf</b> (D58) through the bench-parameterised D53 harness "
          f"(<code>scripts.box_acceptance --fold analog</code>, code {s['code_sha'][:7]}, blueox-boxfit @ {s['engine_sha'][:7]}) · actuals curated.production through "
          f"{s['actuals_through']} (pinned = the scored WCA record's) · tuning blocks only, D52 salt unchanged; no holdout package of BS2_S / WCXY was scored · "
          "error = Σ actual / Σ predicted − 1 per package (negative = forecast HIGH) · oil + gas, uptime-free curves × F(k) as the harness scores them</div>")]
    # 0 guard
    g = ctx["guard"]
    p += ["<h2>0. Regression guard — WCA through the generalised harness</h2>",
          f"<div class='flag {'ok' if g['pass'] else 'bad'}'><b>{'PASS' if g['pass'] else 'FAIL'}</b> — {g['text']}</div>"]
    for name, t in g["tables"].items():
        p += [f"<h3>{name}</h3>", _table(t, {c: ".1e" for c in t.columns if c.startswith("max_abs")})]
    # 1 cells per bench
    for b in ctx["benches"]:
        sm = b["summary"]
        v = sm["verdict"]
        p += [f"<h2>1.{b['n']} {b['title']}</h2>",
              f"<div class=meta>{sm['bench_desc']} · well set {sm['wells_dir']} · pool {sm['n_pool_wells']:,} wells, targets {sm['n_targets']:,} · extent {sm['extent_id']}</div>",
              (f"<div class='flag {'ok' if v['overall'] == 'PASS' else 'bad'}'><b>box_v2_wf (own walk-forward haircut): {v['overall']}</b> — oil {v['by_stream']['oil']}, "
               f"gas {v['by_stream']['gas']}; {v['n_failed']} of {v['n_judged']} judged cells fail. "
               + (" · ".join(f"{k}: {x['overall']} ({x['n_failed']}/{x['n_judged']})" for k, x in sm["verdict_by_variant"].items()) + "</div>")),
              _table(b["cells"], _pct_fmt(b["cells"].columns)),
              "<h3>Folds</h3>", _table(pd.DataFrame(sm["folds"]).drop(columns=["k_areas", "n_factor_no_estimate"], errors="ignore"), {"median_package_wells": ".1f"}),
              (f"<div class=meta>Search mode (locations × cutoffs): {sm.get('v2_mode_counts')} · radius reached: {sm.get('v2_radius_mi')} · short completed laterals "
              f"{sm.get('v2_short_locations')} · U-turns {sm.get('v2_uturn_locations')}</div>")]
    # 2 haircuts
    p += ["<h2>2. Walk-forward haircuts and the D62-style table per bench</h2>",
          ("<div class=meta>Walk-forward haircut = mean package bias of box_v2 at the same horizon over ≥ 2 earlier cutoffs (D57), applied as × (1 + h). "
          "D62-style table = package-weighted mean box_v2 bias over the judged cells (production.haircut_table's rule); for BS2_S / WCXY these are TUNING "
          "cells only (their holdout is unscored, 9b). WCA's record table pools tuning + holdout (D62).</div>"),
          _table(ctx["wf_log"], {c: "+.3f" for c in ctx["wf_log"].columns if c.startswith("cum")}),
          _table(ctx["d62"], {c: ".3f" for c in ctx["d62"].columns if c.startswith(("oil", "gas"))})]
    p += ["<h3>D92 realised factors (C1 rate shape) on each bench's scored locations</h3>",
          ("<div class=meta>Each location's uptime-free box_v2 months × g(k) = a + b ln(min(k, 48)), (a, b) least squares to the bench's D62-style factors; "
          "median [P90 – P10] of the realised cumulative factor and of g at month 1 / month 48 (held after). WCA row = run 7's stored realised medians (PUDs).</div>"),
          _table(ctx["d92"], {})]
    # 3 south edge
    e = ctx["edge"]
    p += ["<h2>3. BS2_S south edge — does the D55 strike search behave?</h2>",
          (f"<div class=meta>Scored BS2_S tuning locations (all cutoffs) classed by distance to the extent-7 boundary: edge = within {EDGE_MI:.0f} mi; south edge = the nearest "
           f"boundary point bears {SOUTH[0]:.0f}–{SOUTH[1]:.0f}° from the extent centroid. Strike search fires only when the 5-mi ring holds fewer than 10 eligible analogs "
           "and local TVD strike is trusted (≥ 8 wells, R² ≥ 0.30). Strike-vs-edge angle: 0° = the ellipse runs along the edge, 90° = across it.</div>"),
          f"<img src='{e['png']}'>", _table(e["regions"], _pct_fmt(e["regions"].columns) | {"strike share": ".0%", "past 5 mi share": ".0%", "radius p50 mi": ".1f", "strike vs edge angle p50 deg": ".0f"}),
          "<h3>By search mode (all BS2_S locations)</h3>", _table(e["modes"], _pct_fmt(e["modes"].columns))]
    # 4 WCXY extent
    w = ctx["wcxy"]
    p += ["<h2>4. WCXY extent — what each option would cover</h2>", f"<img src='{w['png']}'>", _table(w["table"], {}),
          f"<div class=meta>{w['note']}</div>"]
    p += ["<h2>5. Gate-9a decisions</h2>", ctx["decisions_html"], "</body></html>"]
    return "\n".join(p)


def dump(o: Any, path: Path) -> None:
    path.write_text(json.dumps(o, indent=2, default=lambda x: x.tolist() if hasattr(x, "tolist") else str(x)), encoding="utf-8")
