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


# Geology answers to the step-1 questions (Michael + geologist, 2026-10-20) — decisions of record for scoring:
# * WOLFCAMP-C and WOLFCAMP_D are suspect (to be relabelled or re-picked): a tag whose TOP is one of them is not
#   scored; a tag whose BASE is one of them keeps its shallow/agree verdict but a "deep" call is not trusted.
SUSPECT_SURFACES: frozenset[str] = frozenset({"WOLFCAMP-C", "WOLFCAMP_D"})
# * AVA_1 is the Middle Avalon (operator tops ~110 ft above AVALON2, MAD 24 ft, 29 wells); no grid surface exists
#   for it, so it straddles AVALON2 (AVALON1 = top Upper Avalon, AVALON2 = top Lower Avalon). Unscored until a
#   Middle Avalon surface is built.
NO_SURFACE_TAGS: frozenset[str] = frozenset({"AVA_1"})
# * Pecos County: zero picks (geologist or RRC) for Wolfcamp A-D and AVALON2 — those surfaces are entirely modelled
#   there. WOLFCAMP_XY, the Bone Springs and Bell / Cherry / Brushy have picks (XY dist-to-control p50 6.5k ft vs
#   WCA 52k ft) and stay scored, flagged "caution".
#   Revised 2026-10-21 (Michael): a well against a surface with no picks is NOT hidden. It is "no_control": kept
#   out of agreement and attribution (a modelled surface cannot be wrong or right), but shown on every map and
#   counted in picks_needed() — tagged wells with no picks nearby are exactly where tops need picking.
NO_CONTROL_SURFACES_BY_COUNTY: dict[str, frozenset[str]] = {
    "Pecos": frozenset({"WOLFCAMP_A", "WOLFCAMP-B1", "WOLFCAMP-B2", "WOLFCAMP-C", "WOLFCAMP_D", "AVALON2"}),
}
CAUTION_COUNTIES: frozenset[str] = frozenset({"Pecos"})
SCORED_VERDICTS: tuple[str, ...] = ("agree", "shallow", "deep")


def apply_geology_rules(tag: str, county: str | None, verdict: str) -> str:
    """Override a raw verdict per the geology decisions above. Order: no surface > no control > suspect."""
    if tag in NO_SURFACE_TAGS:
        return "no_surface"
    if tag not in TAG_TOP:
        return verdict
    top, base = TAG_TOP[tag], tag_base(tag)
    no_ctl = NO_CONTROL_SURFACES_BY_COUNTY.get(county or "", frozenset())
    if top in no_ctl or base in no_ctl:
        return "no_control"
    if top in SUSPECT_SURFACES or (base in SUSPECT_SURFACES and verdict == "deep"):
        return "surface_suspect"
    return verdict


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



# ----------------------------------------------------------------------------
# Step 2 — classification, structure-vs-tag attribution, surface offset fields
# ----------------------------------------------------------------------------

EDGE_FT = 25.0                         # default edge tolerance for maps (sensitivity: EDGE_SENSITIVITY)
EDGE_SENSITIVITY: tuple[float, ...] = (10.0, 25.0, 50.0)
GROSS_FT = 300.0                       # |miss| beyond this = data error / grid extrapolation until shown otherwise
BAND_RADIUS_FT = 7_920.0               # 1.5 mi — the gunbarrel-consensus witness radius (bench_qc.ConsensusParams)
BAND_MIN_N = 3                         # >= 3 clean same-tag witnesses (bench_qc min witnesses)
OFFSET_CELL_FT = 2_640.0               # half-mile cells for the surface offset field
DISAGREE: tuple[str, ...] = ("shallow", "deep")
WITNESS_CLASSES: tuple[str, ...] = ("agree", "edge", "shallow", "deep")  # gross is excluded: likely bad data


def classify(verdict: str, miss: float, edge_ft: float = EDGE_FT, gross_ft: float = GROSS_FT) -> str:
    """Refine a step-1 verdict: a shallow / deep call within ``edge_ft`` of the surface is 'edge' (its own class,
    not a disagreement); beyond ``gross_ft`` it is 'gross'. Every other verdict passes through."""
    if verdict not in DISAGREE or not np.isfinite(miss):
        return verdict
    if abs(miss) > gross_ft:
        return "gross"
    if abs(miss) <= edge_ft:
        return "edge"
    return verdict


def attribute(df: pd.DataFrame, edge_ft: float = EDGE_FT, radius_ft: float = BAND_RADIUS_FT,
              min_n: int = BAND_MIN_N) -> pd.DataFrame:
    """Structure-vs-tag attribution for each shallow / deep well against its local SAME-TAG band.

    ``df``: api10, tag, x, y (ft, any planar frame), cls, miss, witness (bool). Witness miss = 0 when it agrees.
    band_miss = median witness miss within ``radius_ft`` (self excluded).
      * structure_suspect — band on the same side as the well and beyond ``edge_ft``: the local same-tag cluster
        sits outside the grid interval (the surface, or a local naming convention, is off by ~band_miss ft);
      * tag_suspect — the band agrees with the grid (|band_miss| <= edge_ft): the well is the outlier;
      * unresolved_mixed — band beyond edge on the OTHER side;  unresolved_sparse — fewer than ``min_n`` witnesses.
    grid_offset_ft = band_miss for structure_suspect (− surface should come up, + go down), else NaN."""
    from scipy.spatial import cKDTree

    out = pd.DataFrame(index=df.index, data={"band_n": 0, "band_miss": np.nan, "attribution": None,
                                             "grid_offset_ft": np.nan})
    wmiss = np.where(df["cls"].eq("agree"), 0.0, df["miss"].astype(float))
    for tag, g in df.groupby("tag", sort=False):
        wit = g[g["witness"].astype(bool)]
        subj = g[g["cls"].isin(DISAGREE)]
        if subj.empty:
            continue
        if wit.empty:
            out.loc[subj.index, "attribution"] = "unresolved_sparse"
            continue
        tree = cKDTree(wit[["x", "y"]].to_numpy(float))
        wm = wmiss[df.index.get_indexer(wit.index)]
        hits = tree.query_ball_point(subj[["x", "y"]].to_numpy(float), r=radius_ft)
        for idx, js, m in zip(subj.index, hits, subj["miss"].astype(float), strict=True):
            js = [j for j in js if wit.index[j] != idx]
            out.at[idx, "band_n"] = len(js)
            if len(js) < min_n:
                out.at[idx, "attribution"] = "unresolved_sparse"
                continue
            b = float(np.median(wm[js]))
            out.at[idx, "band_miss"] = b
            if abs(b) <= edge_ft:
                out.at[idx, "attribution"] = "tag_suspect"
            elif np.sign(b) == np.sign(m):
                out.at[idx, "attribution"] = "structure_suspect"
                out.at[idx, "grid_offset_ft"] = b
            else:
                out.at[idx, "attribution"] = "unresolved_mixed"
    return out


def surface_residuals(w: pd.DataFrame, surface: str) -> pd.DataFrame:
    """Per-well evidence about ONE surface from the wells on both sides of it. ``w``: api10, tag, x, y, cls,
    ft_below_top, ft_above_base, witness. A well whose tag TOP is the surface contributes min(0, ft_below_top)
    (negative = it lands above the surface: the surface should come up); one whose tag BASE is the surface
    contributes max(0, -ft_above_base) (positive = it lands below: the surface should go down). Witnesses only."""
    top = w["tag"].map(TAG_TOP)
    base = w["tag"].map(lambda t: tag_base(t) if t in TAG_TOP else None)
    ok = w["witness"].astype(bool)
    a = w[ok & top.eq(surface)].assign(r=lambda d: np.minimum(0.0, d["ft_below_top"].astype(float)), side="below")
    b = w[ok & base.eq(surface)].assign(r=lambda d: np.maximum(0.0, -d["ft_above_base"].astype(float)), side="above")
    return pd.concat([a, b])[["api10", "tag", "x", "y", "r", "side"]]


def offset_field(res: pd.DataFrame, cell_ft: float = OFFSET_CELL_FT, radius_ft: float = BAND_RADIUS_FT,
                 min_n: int = BAND_MIN_N, edge_ft: float = EDGE_FT) -> pd.DataFrame:
    """Median surface residual on a ``cell_ft`` lattice: every cell centre with >= ``min_n`` residual wells within
    ``radius_ft``. Columns cx, cy, n, offset_ft (median; − up, + down), n_up, n_down (wells pulling each way
    beyond ``edge_ft``: a conflict when both are large), flagged (|median| > ``edge_ft``: the surface wants to
    move there). Unflagged cells are kept so conflicts — tags disagreeing with each other — can be counted."""
    from scipy.spatial import cKDTree

    cols = ["cx", "cy", "n", "offset_ft", "n_up", "n_down", "flagged"]
    if len(res) < min_n:
        return pd.DataFrame(columns=cols)
    xy = res[["x", "y"]].to_numpy(float)
    r = res["r"].to_numpy(float)
    x0, y0 = np.floor(xy.min(axis=0) / cell_ft) * cell_ft
    x1, y1 = np.ceil(xy.max(axis=0) / cell_ft) * cell_ft
    cx, cy = np.meshgrid(np.arange(x0, x1 + cell_ft, cell_ft) + cell_ft / 2, np.arange(y0, y1 + cell_ft, cell_ft) + cell_ft / 2)
    centres = np.column_stack([cx.ravel(), cy.ravel()])
    tree = cKDTree(xy)
    rows = []
    for c, js in zip(centres, tree.query_ball_point(centres, r=radius_ft), strict=True):
        if len(js) < min_n:
            continue
        v = r[js]
        med = float(np.median(v))
        rows.append((c[0], c[1], len(js), med, int((v < -edge_ft).sum()), int((v > edge_ft).sum()), abs(med) > edge_ft))
    return pd.DataFrame(rows, columns=cols)


# ----------------------------------------------------------------------------
# Step 3 — landing position relative to a reference surface (tag-blind), landing zones, tag splits
# ----------------------------------------------------------------------------

MIN_SEPARATION = 0.2      # below this a split depth is reported as "no separation" (degenerate optimum)
KDE_BW_FT = 12.0          # Gaussian KDE bandwidth for landing-zone peaks (~ half the 25 ft edge tolerance)
MODE_WINDOW_FT = 25.0     # a landing zone's members: within this of the peak
MODE_MIN_PROM = 0.10      # a peak must stand >= 10 % of the tallest peak above its surroundings


def relative_positions(st: pd.DataFrame, stack: dict[str, Grid], surfaces: tuple[str, ...], tvd_col: str = "tvd") -> pd.DataFrame:
    """Per well: median over its stations of (tvd − surface depth at the station) for each surface, ft
    (negative = above the surface). ``st``: api10, x, y, <tvd_col>. Columns rel_<surface>."""
    xy = st[["x", "y"]].to_numpy(float)
    tvd = st[tvd_col].to_numpy(float)
    d = pd.DataFrame({"api10": st["api10"].to_numpy()})
    for s in surfaces:
        d[f"rel_{s}"] = tvd - stack[s].sample(xy)
    return d.groupby("api10", sort=False).median()


def kde_modes(v: np.ndarray, bw_ft: float = KDE_BW_FT, window_ft: float = MODE_WINDOW_FT,
              min_prom: float = MODE_MIN_PROM, step_ft: float = 1.0) -> list[dict[str, float]]:
    """Landing zones: peaks of a fixed-bandwidth Gaussian KDE of positions (ft). Each: position, density, n within
    ±window_ft, prominence relative to the tallest peak. Sorted shallow -> deep."""
    from scipy.signal import find_peaks

    v = np.asarray(v, dtype=float)
    v = v[np.isfinite(v)]
    if len(v) < 5:
        return []
    grid = np.arange(np.floor(v.min()) - 3 * bw_ft, np.ceil(v.max()) + 3 * bw_ft + step_ft, step_ft)
    dens = np.exp(-0.5 * ((grid[:, None] - v[None, :]) / bw_ft) ** 2).sum(axis=1)
    dens /= dens.max()
    idx, props = find_peaks(dens, prominence=min_prom)
    return [{"pos_ft": float(grid[i]), "density": float(dens[i]), "prominence": float(p),
             "n": int((np.abs(v - grid[i]) <= window_ft).sum())} for i, p in zip(idx, props["prominences"], strict=True)]


def best_split(upper: np.ndarray, lower: np.ndarray) -> dict[str, float]:
    """The depth t that best separates two tags where ``upper`` should sit above (< t) and ``lower`` below (>= t):
    minimises misclassified wells over both. Ties take the midpoint of the tied run. Returns t, error share,
    separation (1 − error / the error of lumping both tags together: 0 = the depth separates nothing, 1 = perfect)
    and n."""
    u = np.asarray(upper, dtype=float)
    lo = np.asarray(lower, dtype=float)
    u, lo = u[np.isfinite(u)], lo[np.isfinite(lo)]
    if len(u) < 3 or len(lo) < 3:
        return {"split_ft": np.nan, "error": np.nan, "separation": np.nan, "n_upper": len(u), "n_lower": len(lo)}
    cand = np.unique(np.concatenate([u, lo]))
    cand = np.concatenate([[cand[0] - 1.0], (cand[:-1] + cand[1:]) / 2.0, [cand[-1] + 1.0]])
    us, ls = np.sort(u), np.sort(lo)
    err = (len(us) - np.searchsorted(us, cand, side="left")) + np.searchsorted(ls, cand, side="left")
    best = np.flatnonzero(err == err.min())
    t = float(np.median(cand[best]))
    error = float(err.min() / (len(u) + len(lo)))
    trivial = min(len(u), len(lo)) / (len(u) + len(lo))  # error of lumping both tags on one side
    return {"split_ft": t, "error": error, "separation": 1.0 - error / trivial, "n_upper": len(u), "n_lower": len(lo)}


# ----------------------------------------------------------------------------
# Picks needed — tagged wells with no pick nearby (2026-10-21)
# ----------------------------------------------------------------------------

PICK_CELL_FT = 5_280.0    # one-mile cells: the scale at which "pick a log here" is actionable
PICK_MIN_WELLS = 3        # a cell is listed when at least this many wells lack control within TRUST radius


def picks_needed(w: pd.DataFrame, trust_ft: float, cell_ft: float = PICK_CELL_FT, min_wells: int = PICK_MIN_WELLS) -> pd.DataFrame:
    """Where a surface needs picks: one-mile cells holding >= ``min_wells`` wells that land against the surface with
    no pick within ``trust_ft`` (NaN distance = no DIST grid there = no control). ``w``: x, y, dist (ft to the
    nearest pick of that surface), tag. Columns cx, cy, n_far, n_wells, dist_p50_ft, tags; most wells first."""
    cols = ["cx", "cy", "n_far", "n_wells", "dist_p50_ft", "tags"]
    if w.empty:
        return pd.DataFrame(columns=cols)
    d = w.assign(far=~(w["dist"].astype(float) <= trust_ft),
                 cx=(np.floor(w["x"].astype(float) / cell_ft) + 0.5) * cell_ft,
                 cy=(np.floor(w["y"].astype(float) / cell_ft) + 0.5) * cell_ft)
    g = d.groupby(["cx", "cy"])
    out = pd.DataFrame({"n_far": g["far"].sum().astype(int), "n_wells": g.size(),
                        "dist_p50_ft": g["dist"].median(),
                        "tags": g["tag"].agg(lambda t: ", ".join(f"{k} {v}" for k, v in t.value_counts().items()))}).reset_index()
    out = out[out["n_far"] >= min_wells]
    return out.sort_values(["n_far", "n_wells"], ascending=False, ignore_index=True)[cols]

