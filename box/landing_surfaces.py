"""Landing surfaces per BOX extent and formation_blueox code, and where they cross — formation_tag_redesign step A.

Pure core (no DB, no files). Michael's idea (2026-11-06): grid the landing TVD of every code inside its BOX extent,
stack the surfaces in stratigraphic order, and look where one surface meets or crosses another. Those are the places
whose tags need investigating.

Surface at a lattice node (method from surface-density-2026-11-06 and surface-fringe-2026-11-06; estimator rev 1,
2026-11-06: estimate() = distance-weighted median unless >= 6 wells SURROUND the node with a plausible dip, and
thickness only where the target bench has samples on more than one side. The first version fit tilted planes through
a few one-sided wells and swung hundreds of feet. Michael's check of ART SMITH STATE #130H caught it: 61 of 67 cards
rested on such surfaces):
  * direct     the code's own evidence wells: robust plane through those within R_MI (>= N_MIN), used only where
               the nearest one is within DIRECT_MAX_MI;
  * thickness  where the code's nearest well is DIRECT_MAX_MI .. THICK_MAX_MI away: the plane of a thick, well-drilled
               anchor bench at the node (>= N_MIN within R_MI), plus the median thickness from that anchor to the code,
               measured at code wells within THICK_MAX_MI (>= N_MIN samples);
  * none       beyond that: no surface, and the vendor tag stands there.
Surfaces are built from LIVE tags, so they inherit tag errors. The robust fit resists a few bad wells, and a locally
coherent error is exactly what shows up as a crossing. This step only finds those places; it re-tags nothing.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd
from scipy.spatial import cKDTree

M_PER_MI = 1609.344
WCA_FAM = ("WCXY", "WCA_1", "WCA_2")
EXTENT_CODES = {("delaware", "WCA"): WCA_FAM}
ANCHOR = {
    "delaware": {"AVA_0": ("BS2_S",), "AVA_1": ("BS2_S",), "AVA_2": ("BS2_S",), "BS1_S": ("BS2_S",), "BS2_C": ("BS2_S",),
                 "BS2_S": ("BS3_C",), "BS3_C": ("BS2_S",), "BS3_S": WCA_FAM, "WCB_1": WCA_FAM, "WCB_2": WCA_FAM, "WCC": WCA_FAM},
    "midland": {"MS": ("LSSH",), "JM": ("LSSH",), "DEAN": ("LSSH",), "LSSH": ("JM",), "WCA_1": ("LSSH",),
                "WCB_1": ("WCA_1",), "WCB_2": ("WCA_1",), "WCC": ("WCA_1",), "WCD": ("WCA_1",)},
}


@dataclass(frozen=True)
class SurfaceParams:
    node_mi: float = 0.25
    r_mi: float = 2.0
    n_min: int = 3
    direct_max_mi: float = 1.0
    thick_max_mi: float = 5.0
    merge_ft: float = 50.0
    fringe_mi: float = 1.0
    # rev 1 (2026-11-06, Michael's ART SMITH STATE #130H check): a tilted plane only where it can be trusted
    plane_min_n: int = 6             # wells needed to fit a plane at all
    max_dip_ft_per_mi: float = 300.0  # a steeper fitted dip is an artefact here (Delaware WCA dips ran 71-225 ft/mi)
    plane_max_dev_ft: float = 150.0   # a plane more than this off the local weighted median is rejected
    wmed_sigma_mi: float = 1.0       # Gaussian distance weight of the weighted median


PARAMS = SurfaceParams()


def extent_codes(basin: str, bench: str) -> tuple[str, ...]:
    return EXTENT_CODES.get((basin, bench), (bench,))


def robust_plane(xy: np.ndarray, z: np.ndarray, at: np.ndarray) -> float:
    """Robust local plane at ``at`` (2.5-sigma MAD rejection, one refit); the median below 4 points."""
    if len(z) < 4:
        return float(np.median(z))
    X = np.column_stack([np.ones(len(z)), (xy[:, 0] - at[0]) / M_PER_MI, (xy[:, 1] - at[1]) / M_PER_MI])
    c, *_ = np.linalg.lstsq(X, z, rcond=None)
    r = z - X @ c
    mad = np.median(np.abs(r - np.median(r))) or 1.0
    ok = np.abs(r) <= 2.5 * 1.4826 * mad
    if 4 <= ok.sum() < len(z):
        c, *_ = np.linalg.lstsq(X[ok], z[ok], rcond=None)
    return float(c[0])


def _plane_fit(xy: np.ndarray, z: np.ndarray, at: np.ndarray) -> tuple[float, float, float]:
    """(value at ``at``, dz/dx, dz/dy in ft per mi) of a robust plane (2.5-sigma MAD rejection, one refit)."""
    X = np.column_stack([np.ones(len(z)), (xy[:, 0] - at[0]) / M_PER_MI, (xy[:, 1] - at[1]) / M_PER_MI])
    c, *_ = np.linalg.lstsq(X, z, rcond=None)
    r = z - X @ c
    mad = np.median(np.abs(r - np.median(r))) or 1.0
    ok = np.abs(r) <= 2.5 * 1.4826 * mad
    if 4 <= ok.sum() < len(z):
        c, *_ = np.linalg.lstsq(X[ok], z[ok], rcond=None)
    return float(c[0]), float(c[1]), float(c[2])


def weighted_median(z: np.ndarray, w: np.ndarray) -> float:
    o = np.argsort(z)
    cw = np.cumsum(w[o])
    return float(z[o][np.searchsorted(cw, 0.5 * cw[-1])])


def max_angular_gap_deg(xy: np.ndarray, at: np.ndarray) -> float:
    """Largest empty sector (deg) around ``at``; < 180 means the points surround it (it lies inside their hull)."""
    a = np.sort(np.degrees(np.arctan2(xy[:, 1] - at[1], xy[:, 0] - at[0])) % 360.0)
    if len(a) < 2:
        return 360.0
    return float(max(np.max(np.diff(a)), 360.0 - a[-1] + a[0]))


def estimate(xy: np.ndarray, z: np.ndarray, at: np.ndarray, p: SurfaceParams = PARAMS) -> tuple[float, str]:
    """Rev 1 estimator: the Gaussian-distance-weighted median of the wells, replaced by a robust plane only when
    >= plane_min_n wells SURROUND the point, the fitted dip is <= max_dip_ft_per_mi, and the plane stays within
    plane_max_dev_ft of the weighted median. Returns (value, 'plane' | 'wmedian')."""
    d = np.hypot(xy[:, 0] - at[0], xy[:, 1] - at[1]) / M_PER_MI
    wm = weighted_median(z, np.exp(-0.5 * (d / p.wmed_sigma_mi) ** 2) + 1e-9)
    if len(z) >= p.plane_min_n and max_angular_gap_deg(xy, at) < 180.0:
        v, gx, gy = _plane_fit(xy, z, at)
        if np.hypot(gx, gy) <= p.max_dip_ft_per_mi and abs(v - wm) <= p.plane_max_dev_ft:
            return v, "plane"
    return wm, "wmedian"


def lattice(bounds: tuple[float, float, float, float], step_m: float) -> tuple[np.ndarray, np.ndarray]:
    """Basin-wide aligned lattice over ``bounds``: integer keys (ix, iy) and node xy. Nodes sit at multiples of the
    step, so the surfaces of different extents share nodes."""
    minx, miny, maxx, maxy = bounds
    ix = np.arange(np.ceil(minx / step_m), np.floor(maxx / step_m) + 1).astype(int)
    iy = np.arange(np.ceil(miny / step_m), np.floor(maxy / step_m) + 1).astype(int)
    gx, gy = np.meshgrid(ix, iy)
    keys = np.column_stack([gx.ravel(), gy.ravel()])
    return keys, keys.astype(float) * step_m


def surface(nodes: np.ndarray, code_xy: np.ndarray, code_z: np.ndarray, anchor_xy: np.ndarray | None,
            anchor_z: np.ndarray | None, p: SurfaceParams = PARAMS) -> pd.DataFrame:
    """z, basis ('direct' / 'thickness' / None) and nearest same-code well distance (mi) at each node."""
    n = len(nodes)
    out_z, basis = np.full(n, np.nan), np.full(n, None, dtype=object)
    if len(code_z) == 0:
        return pd.DataFrame({"z": out_z, "basis": basis, "near_mi": np.full(n, np.inf)})
    r, dmax, tmax = p.r_mi * M_PER_MI, p.direct_max_mi * M_PER_MI, p.thick_max_mi * M_PER_MI
    tree = cKDTree(code_xy)
    near, _ = tree.query(nodes, k=1)
    atree = cKDTree(anchor_xy) if anchor_xy is not None and len(anchor_xy) >= p.n_min else None
    A_at_code = None
    if atree is not None:
        A_at_code = np.full(len(code_z), np.nan)
        for k, js in enumerate(atree.query_ball_point(code_xy, r)):
            if len(js) >= p.n_min:
                A_at_code[k] = estimate(anchor_xy[js], anchor_z[js], code_xy[k], p)[0]
    direct_idx = np.where(near <= dmax)[0]
    for i, js in zip(direct_idx, tree.query_ball_point(nodes[direct_idx], r), strict=True):
        if len(js) >= p.n_min:
            out_z[i], basis[i] = estimate(code_xy[js], code_z[js], nodes[i], p)[0], "direct"
    if atree is not None:
        t_idx = np.where(np.isnan(out_z) & (near <= tmax))[0]
        if len(t_idx):
            a_nb = atree.query_ball_point(nodes[t_idx], r)
            c_nb = tree.query_ball_point(nodes[t_idx], tmax)
            for i, ajs, cjs in zip(t_idx, a_nb, c_nb, strict=True):
                if len(ajs) < p.n_min:
                    continue
                cjs = np.asarray(cjs, int)
                cjs = cjs[np.isfinite(A_at_code[cjs])]
                # rev 1: thickness only where the target bench's samples sit on more than one side of the node
                if len(cjs) < p.n_min or max_angular_gap_deg(code_xy[cjs], nodes[i]) >= 180.0:
                    continue
                dk = np.hypot(code_xy[cjs, 0] - nodes[i][0], code_xy[cjs, 1] - nodes[i][1]) / M_PER_MI
                t = weighted_median(code_z[cjs] - A_at_code[cjs], np.exp(-0.5 * (dk / (2 * p.wmed_sigma_mi)) ** 2) + 1e-9)
                out_z[i] = estimate(anchor_xy[ajs], anchor_z[ajs], nodes[i], p)[0] + t
                basis[i] = "thickness"
    return pd.DataFrame({"z": out_z, "basis": basis, "near_mi": near / M_PER_MI})


def compare(upper: pd.DataFrame, lower: pd.DataFrame, merge_ft: float) -> pd.DataFrame:
    """Two code surfaces indexed by node key (ix, iy), ``upper`` shallower in the strat column. Returns the shared
    nodes with gap = lower - upper (ft, + = in order) and state 'crossing' (gap <= 0), 'merged' (gap < merge_ft) or
    'separated'."""
    j = upper[["z"]].join(lower[["z"]], how="inner", lsuffix="_u", rsuffix="_l").dropna()
    j["gap_ft"] = j["z_l"] - j["z_u"]
    j["state"] = np.where(j["gap_ft"] <= 0, "crossing", np.where(j["gap_ft"] < merge_ft, "merged", "separated"))
    return j
