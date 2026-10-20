"""Tops-vs-tag QC — pure core (no DB). Plan: ~/.claude/plans/my-geologist-has-exported-buzzing-sketch.md.

Scores each well's formation_blueox tag against the geologist's structure grids, station by station along the
lateral (curated.well_lateral_survey, sql/64) or at the lateral midpoint when the well has no survey. A
disagreement is evidence that EITHER the tag or the grid is wrong; this module only measures position. It never
re-tags anything and never feeds a forecast (grids are context, D25).

Frames: grids are NAD83 UTM 14N US-ft (geology_io.GEOLOGY_CRS), Z = depth below KB (ft, positive down; the
datum is CHECKED in the step-1 report, not assumed silently). Interval k of the stack is the rock between surface
k-1 and surface k; it is labelled by its TOP surface ("ABOVE_<first>" for k = 0).
"""

from __future__ import annotations

import itertools
from dataclasses import dataclass
from pathlib import Path

import numpy as np
import pandas as pd
from scipy.interpolate import RegularGridInterpolator

from box import extent_package as pkg

# Surfaces in stratigraphic order, shallow -> deep (all 17 exist in both the 10-19 and September sets).
STACK: tuple[str, ...] = (
    "BELL_CANYON", "CHERRY_CANYON", "BRUSHY_CANYON",
    "AVALON1", "AVALON2", "1BSPGS", "2BSPGC", "2BSPGS", "3BSPGC", "3BSPGS",
    "WOLFCAMP_XY", "WOLFCAMP_A", "WOLFCAMP-B1", "WOLFCAMP-B2", "WOLFCAMP-C", "WOLFCAMP_D", "STRAWN",
)
INTERVALS: tuple[str, ...] = (f"ABOVE_{STACK[0]}", *STACK)  # interval k labelled by its top surface

# formation_blueox tag -> top surface of the grid interval it should sit in (base = next surface in STACK).
# From extent_package.GRIDS (same top/base pairs) + the codes GRIDS pools or omits: WCXY (XY top -> WCA top) and
# WCA_1 / WCA_2 (both WCA top -> WCB1 top: no grid splits them; they are told apart by position only, step 3).
# AVA_0 has no grid of its own -> Avalon 1 top, as on its BOX map.
TAG_TOP: dict[str, str] = {
    "AVA_0": "AVALON1", "AVA_1": "AVALON1", "AVA_2": "AVALON2",
    "BS1_S": "1BSPGS", "BS2_C": "2BSPGC", "BS2_S": "2BSPGS", "BS3_C": "3BSPGC", "BS3_S": "3BSPGS",
    "WCXY": "WOLFCAMP_XY", "WCA_1": "WOLFCAMP_A", "WCA_2": "WOLFCAMP_A",
    "WCB_1": "WOLFCAMP-B1", "WCB_2": "WOLFCAMP-B2", "WCC": "WOLFCAMP-C", "WCD": "WOLFCAMP_D",
}


def tag_base(tag: str) -> str:
    return STACK[STACK.index(TAG_TOP[tag]) + 1]


@dataclass(frozen=True)
class Grid:
    surface: str
    xs: np.ndarray
    ys: np.ndarray
    z: np.ndarray

    def sample(self, xy: np.ndarray) -> np.ndarray:
        """Bilinear at (N, 2) x, y (geology frame); NaN off-lattice or in a cell touching a null node."""
        f = RegularGridInterpolator((self.ys, self.xs), self.z, bounds_error=False, fill_value=np.nan)
        return f(np.asarray(xy, dtype=float).reshape(-1, 2)[:, ::-1])


def load_stack(grid_dir: Path, surfaces: tuple[str, ...] = STACK) -> dict[str, Grid]:
    out = {}
    for s in surfaces:
        xs, ys, z = pkg._grid(pkg.require_grid(s, grid_dir))
        out[s] = Grid(s, xs, ys, z)
    return out


def sample_stack(stack: dict[str, Grid], xy: np.ndarray, surfaces: tuple[str, ...] = STACK) -> np.ndarray:
    """(N, len(surfaces)) grid depths at xy."""
    return np.column_stack([stack[s].sample(xy) for s in surfaces])


def interval_index(depths: np.ndarray, tvd: np.ndarray) -> np.ndarray:
    """Interval k per point = number of FINITE surfaces at or above the point (depth <= tvd). With a monotonic
    stack that is exactly "between surface k-1 and k"; NaN surfaces are skipped (counted as absent), crossings are
    reported separately by surface_crossings()."""
    d = np.asarray(depths, dtype=float)
    t = np.asarray(tvd, dtype=float).reshape(-1, 1)
    return np.where(np.isfinite(d), d <= t, False).sum(axis=1)


def signed_miss(tvd: np.ndarray, top: np.ndarray, base: np.ndarray) -> np.ndarray:
    """0 inside [top, base); tvd - top (< 0) above the top; tvd - base (>= 0) at/below the base. NaN if a surface is."""
    tvd, top, base = (np.asarray(a, dtype=float) for a in (tvd, top, base))
    m = np.where(tvd < top, tvd - top, np.where(tvd >= base, tvd - base, 0.0))
    return np.where(np.isfinite(top) & np.isfinite(base), m, np.nan)


def station_frame(st: pd.DataFrame, stack: dict[str, Grid], tvd_col: str = "tvd") -> pd.DataFrame:
    """Per station: interval, tag top/base depth, position. ``st`` columns: api10, tag, x, y, <tvd_col>.
    Tags outside TAG_TOP get NaN tag metrics (still get an interval)."""
    xy = st[["x", "y"]].to_numpy(float)
    tvd = st[tvd_col].to_numpy(float)
    D = sample_stack(stack, xy)
    out = st[["api10", "tag"]].copy()
    out["tvd"] = tvd
    out["n_nan_surf"] = (~np.isfinite(D)).sum(axis=1)
    out["interval"] = np.array(INTERVALS, dtype=object)[interval_index(D, tvd)]
    col = {s: i for i, s in enumerate(STACK)}
    tops = st["tag"].map(TAG_TOP)
    ti = tops.map(col).to_numpy(float)
    known = np.isfinite(ti)
    top = np.full(len(st), np.nan)
    base = np.full(len(st), np.nan)
    rows = np.where(known)[0]
    top[rows] = D[rows, ti[known].astype(int)]
    base[rows] = D[rows, ti[known].astype(int) + 1]
    out["top"], out["base"] = top, base
    out["ft_below_top"] = tvd - top
    out["ft_above_base"] = base - tvd
    thick = base - top
    out["frac"] = np.where(thick > 0, (tvd - top) / np.where(thick > 0, thick, np.nan), np.nan)
    out["miss"] = signed_miss(tvd, top, base)
    out["in_tag"] = np.where(np.isfinite(out["miss"]), out["miss"] == 0, np.nan)
    return out


def well_summary(sf: pd.DataFrame) -> pd.DataFrame:
    """Per-well reduction of station_frame(): share of the lateral in the tag interval, dominant interval, and
    median position. agree = majority of measurable stations inside the tag interval."""
    g = sf.groupby("api10", sort=False)
    meas = sf[np.isfinite(sf["miss"].astype(float))].assign(
        _above=lambda d: d["miss"] < 0, _below=lambda d: d["miss"] > 0, in_tag=lambda d: d["in_tag"].astype(float))
    gm = meas.groupby("api10", sort=False)
    out = pd.DataFrame({"n_st": g.size()})
    out["n_meas"] = gm.size()
    out["pct_in_tag"] = gm["in_tag"].mean()
    out["pct_above_top"] = gm["_above"].mean()
    out["pct_below_base"] = gm["_below"].mean()
    out["miss_p50"] = gm["miss"].median()
    out["ft_below_top_p50"] = gm["ft_below_top"].median()
    out["ft_above_base_p50"] = gm["ft_above_base"].median()
    out["frac_p50"] = gm["frac"].median()
    out["top_p50"] = gm["top"].median()
    out["base_p50"] = gm["base"].median()
    dom = sf.groupby(["api10", "interval"], sort=False).size().rename("n").reset_index()
    dom = dom.sort_values(["api10", "n"], ascending=[True, False]).drop_duplicates("api10").set_index("api10")
    out["dom_interval"] = dom["interval"]
    out["dom_share"] = dom["n"] / out["n_st"]
    out["max_nan_surf"] = g["n_nan_surf"].max()
    out["verdict"] = np.select(
        [out["n_meas"].fillna(0) == 0, out["pct_in_tag"] >= 0.5, out["pct_above_top"] >= out["pct_below_base"]],
        ["unmeasured", "agree", "shallow"], default="deep")
    return out


def surface_crossings(stack: dict[str, Grid], surfaces: tuple[str, ...] = STACK) -> pd.DataFrame:
    """For each adjacent pair (shallow, deep): nodes where both are finite, share where deep < shallow (a crossing:
    negative isopach), and isopach p05 / p50 (ft). Pairs on different lattices are compared at the shallow
    surface's nodes by bilinear sampling of the deeper one."""
    rows = []
    for a, b in itertools.pairwise(surfaces):
        ga, gb = stack[a], stack[b]
        X, Y = np.meshgrid(ga.xs, ga.ys)
        za = ga.z.ravel()
        zb = gb.sample(np.column_stack([X.ravel(), Y.ravel()]))
        ok = np.isfinite(za) & np.isfinite(zb)
        iso = zb[ok] - za[ok]
        rows.append({"top": a, "base": b, "nodes": int(ok.sum()),
                     "pct_crossing": float((iso < 0).mean()) if ok.any() else np.nan,
                     "iso_p05_ft": float(np.percentile(iso, 5)) if ok.any() else np.nan,
                     "iso_p50_ft": float(np.median(iso)) if ok.any() else np.nan})
    return pd.DataFrame(rows)

