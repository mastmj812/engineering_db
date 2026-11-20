"""BOX sticks: the geologist's structure grids in the landing chain (generator 0.13; Delaware only).

Decided 2026-11-20 (docs/box_sticks_plan.md; bars docs/box_sticks/grid-rung-2026-11-20/BARS.md): the grids are a witness
against wells and an arbiter where control is weak.

  1. `grid` rung in place of the `offset` rung, on the benches of RUNG_BENCHES: landing = the bench's gridded top + the
     bench's fractional position x the gridded thickness there.
  2. A bound on every carried landing (thickness / bracket / offset) of a bench in INTERVALS: more than BOUND_FT outside
     the bench's gridded interval -> pulled to the grid's prediction, rung `grid`, note `grid_bounded`.
  3. A direct landing is never moved; outside its interval by more than BOUND_FT it only carries the note `outside_grid`.

The fraction (0 = gridded top, 1 = gridded base) is learned from evidence wells of the same code whose depth sits in their
own gridded interval, regionally: the distance-weighted median of those FAR_MIN_MI to FAR_MAX_MI away (Gaussian, FAR_SIGMA_MI;
>= MIN_WELLS), widened to WIDE_MAX_MI, then the basin median. Wells inside FAR_MIN_MI are left out on purpose: that is the
situation the rung was tested in (every well within 5 miles removed), and nearer wells belong to the direct and thickness
rungs. The XY top is used here for depth only; it decides no tag and no bench membership.

Pure but for `sampler()`, which reads the grid files. A missing grid or a null surface means no grid value there, and the
chain keeps what it had: this module never fails a run and never invents a depth.
"""
from __future__ import annotations

from collections.abc import Callable

import numpy as np
import pandas as pd
from scipy.spatial import cKDTree

MI = 1609.344
BASIN = "delaware"
SURFACES = ("1BSPGS", "2BSPGC", "2BSPGS", "3BSPGC", "3BSPGS", "WOLFCAMP_XY", "WOLFCAMP_A", "WOLFCAMP-B1")
INTERVALS: dict[str, tuple[str, str]] = {
    "BS1_S": ("1BSPGS", "2BSPGC"), "BS2_C": ("2BSPGC", "2BSPGS"), "BS2_S": ("2BSPGS", "3BSPGC"), "BS3_C": ("3BSPGC", "3BSPGS"),
    "BS3_S": ("3BSPGS", "WOLFCAMP_XY"), "WCXY": ("WOLFCAMP_XY", "WOLFCAMP_A"), "WCA_1": ("WOLFCAMP_A", "WOLFCAMP-B1"), "WCA_2": ("WOLFCAMP_A", "WOLFCAMP-B1"),
}
# Benches whose offset rung the grid replaces, with the grid rung's held-out error (median, P90 ft) from bar G1
# (docs/box_sticks/grid-rung-2026-11-20/g1_by_bench.csv). A bench that failed G1 is not listed and keeps the offset rung.
RUNG_BENCHES: dict[str, tuple[float, float]] = {"BS1_S": (59.9, 182.2), "BS2_C": (76.2, 223.5), "BS2_S": (64.8, 195.4), "BS3_C": (72.4, 216.6), "BS3_S": (47.9, 153.7), "WCXY": (45.6, 125.7), "WCA_1": (55.5, 136.6), "WCA_2": (53.4, 144.8)}
BOUND_FT = 150.0
# Bench x rung cells the bound leaves alone: in the hold-out (g2_by_bench_rung.csv) pulling them to the grid made the
# median error WORSE. They keep their carried depth and carry the note `outside_grid`.
BOUND_SKIP = frozenset({("BS1_S", "thickness"), ("BS3_C", "thickness"), ("BS3_C", "bracket")})
MIN_THICK_FT = 20.0
LEARN_FRAC = (-0.1, 1.1)          # a learning well must sit in (or just outside) its own gridded interval
FAR_MIN_MI, FAR_MAX_MI, WIDE_MAX_MI, FAR_SIGMA_MI, MIN_WELLS = 5.0, 15.0, 25.0, 7.5, 10
CARRIED = ("thickness", "bracket", "offset")
Sampler = Callable[[np.ndarray, np.ndarray], dict[str, np.ndarray]]


def sampler() -> Sampler | None:
    """(x, y in EPSG:3083 metres) -> {surface: depth ft}. None when the grid set cannot be loaded."""
    try:
        from pyproj import Transformer

        from box import extent_package as pkg
        from box import tops_qc as tq
        from box import tops_qc_report as rep

        stack = tq.load_stack(pkg.GRID_DIR, SURFACES)
        to_ll = Transformer.from_crs("EPSG:3083", "EPSG:4326", always_xy=True)
    except Exception:  # noqa: BLE001 - no grids: the chain stands as it is
        return None

    def sample(x: np.ndarray, y: np.ndarray) -> dict[str, np.ndarray]:
        lon, lat = to_ll.transform(np.asarray(x, float), np.asarray(y, float))
        gx, gy = rep._to_geology(lon, lat)
        d = tq.sample_stack(stack, np.column_stack([gx, gy]), SURFACES)
        return {s: d[:, i] for i, s in enumerate(SURFACES)}

    return sample


def interval(code: str, g: dict[str, np.ndarray]) -> tuple[np.ndarray, np.ndarray]:
    """(top, thickness) of the code's gridded interval; NaN where a surface is null or the interval is too thin."""
    a, b = INTERVALS[code]
    top, thick = np.asarray(g[a], float), np.asarray(g[b], float) - np.asarray(g[a], float)
    ok = np.isfinite(top) & np.isfinite(thick) & (thick > MIN_THICK_FT)
    return np.where(ok, top, np.nan), np.where(ok, thick, np.nan)


def well_fraction(z: np.ndarray, top: np.ndarray, thick: np.ndarray) -> np.ndarray:
    """Fractional position of each well in its interval; NaN where it cannot teach (no interval, or far outside it)."""
    f = (np.asarray(z, float) - top) / thick
    return np.where(np.isfinite(f) & (f >= LEARN_FRAC[0]) & (f <= LEARN_FRAC[1]), f, np.nan)


def weighted_median(v: np.ndarray, w: np.ndarray) -> float:
    o = np.argsort(v)
    c = np.cumsum(w[o]) / w.sum()
    return float(v[o][np.searchsorted(c, 0.5)])


def regional_fraction(pts: np.ndarray, wxy: np.ndarray, wf: np.ndarray, exclude_self: bool = False) -> tuple[np.ndarray, np.ndarray]:
    """(fraction, basis) at each point from learning wells (wxy, wf): '5-15 mi', '5-25 mi' or 'basin'; NaN / '' when
    no well can teach. exclude_self: the points ARE the wells (hold-out); a well never teaches itself, which the
    FAR_MIN_MI ring already guarantees for the two ring bases, and the basin median leaves it out explicitly."""
    ok = np.isfinite(wf)
    xy, f = wxy[ok], wf[ok]
    out, basis = np.full(len(pts), np.nan), np.full(len(pts), "", dtype=object)
    if not len(f):
        return out, basis
    basin = float(np.median(f))
    tree = cKDTree(xy)
    pos = np.full(len(wf), -1)
    pos[np.flatnonzero(ok)] = np.arange(len(f))
    for i, idx in enumerate(tree.query_ball_point(pts, WIDE_MAX_MI * MI)):
        idx = np.asarray(idx, int)
        d = np.hypot(xy[idx, 0] - pts[i, 0], xy[idx, 1] - pts[i, 1]) / MI if len(idx) else np.array([])
        for lim, name in ((FAR_MAX_MI, "5-15 mi"), (WIDE_MAX_MI, "5-25 mi")):
            m = (d > FAR_MIN_MI) & (d <= lim)
            if m.sum() >= MIN_WELLS:
                out[i], basis[i] = weighted_median(f[idx[m]], np.exp(-0.5 * (d[m] / FAR_SIGMA_MI) ** 2)), name
                break
        else:
            if exclude_self:
                keep = np.ones(len(f), bool)
                keep[idx[d <= FAR_MIN_MI]] = False
                out[i] = float(np.median(f[keep])) if keep.any() else np.nan
            else:
                out[i] = basin
            basis[i] = "basin" if np.isfinite(out[i]) else ""
    return out, basis


def predict(code: str, pts: np.ndarray, g_pts: dict[str, np.ndarray], wxy: np.ndarray, wz: np.ndarray, g_wells: dict[str, np.ndarray],
            exclude_self: bool = False) -> pd.DataFrame:
    """The grid's landing for `code` at `pts`: z, basis, top, base. NaN z where the grid or the fraction is missing."""
    top, thick = interval(code, g_pts)
    wt, wth = interval(code, g_wells)
    frac, basis = regional_fraction(pts, wxy, well_fraction(wz, wt, wth), exclude_self)
    return pd.DataFrame({"z": top + frac * thick, "basis": basis, "top": top, "base": top + thick, "frac": frac})


def apply_to_chain(ch: pd.DataFrame, ev: pd.DataFrame, pads: pd.DataFrame, sample: Sampler | None, rung_benches: dict[str, tuple[float, float]] | None = None,
                   bound: bool = True) -> pd.DataFrame:
    """The chain frame of scripts.box_sticks_phase1c.build_chain with the grid applied. Adds `grid_note` ('' / 'grid_rung' /
    'grid_bounded' / 'outside_grid') and `z_before`. ev: evidence wells (basin, live, x, y, depth_ft). pads: pad_id, cx, cy."""
    rung_benches = RUNG_BENCHES if rung_benches is None else rung_benches
    ch = ch.copy()
    ch["grid_note"], ch["z_before"] = "", ch["z"]
    if sample is None:
        return ch
    cen = pads.set_index("pad_id")[["cx", "cy"]]
    w = ev[ev["basin"] == BASIN]
    for code in INTERVALS:
        rows = np.flatnonzero(((ch["basin"] == BASIN) & (ch["code"] == code) & (ch["rung"] != "none")).to_numpy())
        if not len(rows):
            continue
        pts = cen.loc[ch["pad_id"].to_numpy()[rows]].to_numpy(float)
        cw = w[w["live"] == code]
        wxy = cw[["x", "y"]].to_numpy(float)
        p = predict(code, pts, sample(pts[:, 0], pts[:, 1]), wxy, cw["depth_ft"].to_numpy(float), sample(wxy[:, 0], wxy[:, 1]) if len(wxy) else {s: np.array([]) for s in SURFACES})
        rung, z = ch["rung"].to_numpy()[rows], ch["z"].to_numpy(float)[rows]
        have = np.isfinite(p["z"].to_numpy())
        miss = np.where(z < p["top"], z - p["top"], np.where(z > p["base"], z - p["base"], 0.0))
        out = np.isfinite(miss) & (np.abs(miss) > BOUND_FT)
        take_rung = (rung == "offset") & have & (code in rung_benches)
        skip = np.array([(code, r) in BOUND_SKIP for r in rung], dtype=bool)
        take_bound = bound & np.isin(rung, CARRIED) & out & have & ~take_rung & ~skip
        note = np.where(take_rung, "grid_rung", np.where(take_bound, "grid_bounded", np.where(((rung == "direct") | skip) & out & ~take_rung, "outside_grid", "")))
        new = take_rung | take_bound
        ix = ch.index[rows]
        ch.loc[ix, "grid_note"] = note
        if new.any():
            med, p90 = rung_benches.get(code, (np.nan, np.nan))
            ch.loc[ix[new], "z"] = p["z"].to_numpy()[new]
            ch.loc[ix[new], "how"] = ["grid " + b + ("" if r else f" (bound on {o})") for b, r, o in zip(p["basis"].to_numpy()[new], take_rung[new], rung[new], strict=True)]
            ch.loc[ix[new], "rung"] = "grid"
            ch.loc[ix[new], ["expected_median_ft", "expected_p90_ft"]] = [med, p90]
            if "second_tvd_ft" in ch.columns:
                ch.loc[ix[new], ["second_tvd_ft", "second_share"]] = np.nan          # the second level belonged to the replaced thickness sample
    return ch
