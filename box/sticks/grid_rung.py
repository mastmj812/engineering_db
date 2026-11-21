"""BOX sticks: the geologist's structure grids in the landing chain (generator 0.13: Delaware; 0.14: the Midland too,
from its own table, BASINS["midland"]; docs/box_sticks/grid-midland-2026-11-21).

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
from dataclasses import dataclass, replace
from pathlib import Path

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


@dataclass(frozen=True)
class GridTable:
    """One basin's grids: the surfaces read, the gridded interval of each bench, and what the hold-out admitted."""
    basin: str
    surfaces: tuple[str, ...]
    intervals: dict[str, tuple[str, str]]
    rung: dict[str, tuple[float, float]]        # benches whose offset rung the grid replaces -> the grid's held-out (median, P90) ft
    bound: frozenset                            # benches whose carried landings are bounded
    bound_skip: frozenset                       # (bench, rung) cells the bound leaves alone (the pull made the hold-out worse)
    err: dict[str, tuple[float, float]]         # the grid's held-out (median, P90) ft for every bench it can set a depth on


MIDLAND_SURFACES = ("MIDDLE_SPRABERRY", "JO_MILL", "LOWER_SPRABERRY_SHALE", "DEAN", "WOLFCAMP_A", "WOLFCAMP_B", "WOLFCAMP_D", "STRAWN")
# WCB_1, WCB_2 and WCC are left out on purpose (BARS.md): the geologist's Wolfcamp B Lower surface covers 10 % of the wells,
# so their boundary would be a constant nobody picked. US: 46 evidence wells.
MIDLAND_INTERVALS: dict[str, tuple[str, str]] = {
    "MS": ("MIDDLE_SPRABERRY", "JO_MILL"), "JM": ("JO_MILL", "LOWER_SPRABERRY_SHALE"), "LSSH": ("LOWER_SPRABERRY_SHALE", "DEAN"),
    "DEAN": ("DEAN", "WOLFCAMP_A"), "WCA_1": ("WOLFCAMP_A", "WOLFCAMP_B"), "WCD": ("WOLFCAMP_D", "STRAWN"),
}
# From bars M1 and M2 (docs/box_sticks/grid-midland-2026-11-21/g1_by_bench.csv, g2_by_rung.csv).
# M1: the grid beat the offset rung on five benches; WCA_1 failed (same median, a worse tail) and keeps the offset rung.
MIDLAND_RUNG: dict[str, tuple[float, float]] = {"MS": (35.9, 99.0), "JM": (42.9, 135.2), "LSSH": (47.7, 138.9), "DEAN": (40.5, 137.7), "WCD": (43.3, 142.8)}
# M2 FAILED on every rung: pulling a carried landing to the grid made the hold-out worse (offset 62 -> 400 ft median). No bench
# is bounded in the Midland, and none is flagged `outside_grid` either: where a landing and the grid disagree here, the
# hold-out says the landing is usually the one that is right.
MIDLAND_BOUND: frozenset = frozenset()
MIDLAND_BOUND_SKIP: frozenset = frozenset()
MIDLAND_ERR: dict[str, tuple[float, float]] = dict(MIDLAND_RUNG) | {"WCA_1": (47.1, 167.1)}

BASINS: dict[str, GridTable] = {
    "delaware": GridTable("delaware", SURFACES, INTERVALS, RUNG_BENCHES, frozenset(INTERVALS), BOUND_SKIP, RUNG_BENCHES),
    "midland": GridTable("midland", MIDLAND_SURFACES, MIDLAND_INTERVALS, MIDLAND_RUNG, MIDLAND_BOUND, MIDLAND_BOUND_SKIP, MIDLAND_ERR),
}


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


def midland_grid_files() -> dict[str, Path]:
    """surface -> grid file of the Midland set: Grids/Midland/<newest dated folder>, beside the Delaware grids."""
    from box import extent_package as pkg

    root = pkg._ENG / "Grids" / "Midland"            # box/basin.py still lists no grid folder for the Midland: BOX type curves do not use these
    sets = sorted(d for d in root.iterdir() if d.is_dir()) if root.is_dir() else []
    if not sets:
        raise FileNotFoundError(f"no Midland grid set under {root}")
    return {s: sets[-1] / f"HCA_{s}_STRUCTURE_MDXYZ_grid.xyz" for s in MIDLAND_SURFACES}


def midland_sampler() -> Sampler | None:
    """As sampler(), for the Midland surfaces. None when the grid set cannot be loaded."""
    try:
        from pyproj import Transformer
        from scipy.interpolate import RegularGridInterpolator

        from box import extent_package as pkg
        from box import tops_qc_report as rep

        fs = {}
        for s, f in midland_grid_files().items():
            xs, ys, z = pkg._grid(f)
            fs[s] = RegularGridInterpolator((ys, xs), z, bounds_error=False, fill_value=np.nan)
        to_ll = Transformer.from_crs("EPSG:3083", "EPSG:4326", always_xy=True)
    except Exception:  # noqa: BLE001 - no grids: the chain stands as it is
        return None

    def sample(x: np.ndarray, y: np.ndarray) -> dict[str, np.ndarray]:
        lon, lat = to_ll.transform(np.asarray(x, float), np.asarray(y, float))
        gx, gy = rep._to_geology(lon, lat)
        return {s: f(np.column_stack([gy, gx])) for s, f in fs.items()}

    return sample


def samplers() -> dict[str, Sampler | None]:
    """A sampler per basin that has a table; None for a basin whose grids cannot be loaded."""
    return {"delaware": sampler(), "midland": midland_sampler()}


def interval(code: str, g: dict[str, np.ndarray], intervals: dict[str, tuple[str, str]] | None = None) -> tuple[np.ndarray, np.ndarray]:
    """(top, thickness) of the code's gridded interval; NaN where a surface is null or the interval is too thin."""
    a, b = (INTERVALS if intervals is None else intervals)[code]
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
            exclude_self: bool = False, intervals: dict[str, tuple[str, str]] | None = None) -> pd.DataFrame:
    """The grid's landing for `code` at `pts`: z, basis, top, base. NaN z where the grid or the fraction is missing."""
    top, thick = interval(code, g_pts, intervals)
    wt, wth = interval(code, g_wells, intervals)
    frac, basis = regional_fraction(pts, wxy, well_fraction(wz, wt, wth), exclude_self)
    return pd.DataFrame({"z": top + frac * thick, "basis": basis, "top": top, "base": top + thick, "frac": frac})


def apply_to_chain(ch: pd.DataFrame, ev: pd.DataFrame, pads: pd.DataFrame, sample: Sampler | dict[str, Sampler | None] | None,
                   rung_benches: dict[str, tuple[float, float]] | None = None, bound: bool = True, tables: dict[str, GridTable] | None = None) -> pd.DataFrame:
    """The chain frame of scripts.box_sticks_phase1c.build_chain with the grid applied, basin by basin. Adds `grid_note`
    ('' / 'grid_rung' / 'grid_bounded' / 'outside_grid') and `z_before`. ev: evidence wells (basin, live, x, y, depth_ft).
    pads: pad_id, cx, cy. `sample`: a sampler per basin (samplers()); a bare sampler is the Delaware's. A basin with no
    table or no sampler is left as it is. `rung_benches` overrides the Delaware table's rung (tests)."""
    tables = BASINS if tables is None else tables
    by = sample if isinstance(sample, dict) else {BASIN: sample}
    ch = ch.copy()
    ch["grid_note"], ch["z_before"] = "", ch["z"]
    cen = pads.set_index("pad_id")[["cx", "cy"]]
    for basin, t in tables.items():
        fn = by.get(basin)
        if fn is None:
            continue
        if basin == BASIN and rung_benches is not None:
            t = replace(t, rung=rung_benches, err=rung_benches)
        w = ev[ev["basin"] == basin]
        for code in t.intervals:
            rows = np.flatnonzero(((ch["basin"] == basin) & (ch["code"] == code) & (ch["rung"] != "none")).to_numpy())
            if not len(rows):
                continue
            pts = cen.loc[ch["pad_id"].to_numpy()[rows]].to_numpy(float)
            cw = w[w["live"] == code]
            wxy = cw[["x", "y"]].to_numpy(float)
            g_w = fn(wxy[:, 0], wxy[:, 1]) if len(wxy) else {s: np.array([]) for s in t.surfaces}
            p = predict(code, pts, fn(pts[:, 0], pts[:, 1]), wxy, cw["depth_ft"].to_numpy(float), g_w, intervals=t.intervals)
            rung, z = ch["rung"].to_numpy()[rows], ch["z"].to_numpy(float)[rows]
            have = np.isfinite(p["z"].to_numpy())
            miss = np.where(z < p["top"], z - p["top"], np.where(z > p["base"], z - p["base"], 0.0))
            out = np.isfinite(miss) & (np.abs(miss) > BOUND_FT)
            take_rung = (rung == "offset") & have & (code in t.rung)
            bounded = code in t.bound                                       # a bench outside the bound is neither pulled nor flagged
            skip = np.array([(code, r) in t.bound_skip for r in rung], dtype=bool)
            take_bound = bound & bounded & np.isin(rung, CARRIED) & out & have & ~take_rung & ~skip
            note = np.where(take_rung, "grid_rung", np.where(take_bound, "grid_bounded",
                                                             np.where(bounded & ((rung == "direct") | skip) & out & ~take_rung, "outside_grid", "")))
            new = take_rung | take_bound
            ix = ch.index[rows]
            ch.loc[ix, "grid_note"] = note
            if new.any():
                med, p90 = t.rung.get(code, t.err.get(code, (np.nan, np.nan)))
                ch.loc[ix[new], "z"] = p["z"].to_numpy()[new]
                ch.loc[ix[new], "how"] = ["grid " + b + ("" if r else f" (bound on {o})") for b, r, o in zip(p["basis"].to_numpy()[new], take_rung[new], rung[new], strict=True)]
                ch.loc[ix[new], "rung"] = "grid"
                ch.loc[ix[new], ["expected_median_ft", "expected_p90_ft"]] = [med, p90]
                if "second_tvd_ft" in ch.columns:
                    ch.loc[ix[new], ["second_tvd_ft", "second_share"]] = np.nan          # the second level belonged to the replaced thickness sample
    return ch
