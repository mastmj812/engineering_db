"""box.landing_surfaces — synthetic surfaces (no DB)."""

from __future__ import annotations

import numpy as np
import pandas as pd

from box import landing_surfaces as ls

MI = ls.M_PER_MI


def _grid_wells(z0: float, dip_ft_per_mi: float = 0.0, n: int = 6, spacing_mi: float = 0.5, x0_mi: float = 0.0):
    xs = (x0_mi + np.arange(n) * spacing_mi) * MI
    gx, gy = np.meshgrid(xs, np.arange(n) * spacing_mi * MI)
    xy = np.column_stack([gx.ravel(), gy.ravel()])
    return xy, z0 + dip_ft_per_mi * xy[:, 0] / MI


def test_lattice_is_aligned_across_bounds():
    k1, _ = ls.lattice((0.0, 0.0, 1000.0, 1000.0), 400.0)
    k2, _ = ls.lattice((390.0, 390.0, 1300.0, 900.0), 400.0)
    assert {tuple(k) for k in k2} <= {tuple(k) for k in k1} | {(3, 1), (3, 2)}
    assert (1, 1) in {tuple(k) for k in k2}


def test_robust_plane_recovers_dip_and_rejects_an_outlier():
    xy, z = _grid_wells(10_000.0, dip_ft_per_mi=50.0)
    z = z.copy()
    z[3] += 400.0  # one mis-tagged well
    at = np.array([1.0 * MI, 1.0 * MI])
    assert abs(ls.robust_plane(xy, z, at) - 10_050.0) < 5.0


def test_surface_direct_then_thickness_then_none():
    code_xy, code_z = _grid_wells(10_300.0, n=3, spacing_mi=0.5)          # sparse bench, west
    anc_xy, anc_z = _grid_wells(10_000.0, n=12, spacing_mi=0.5)           # thick anchor bench everywhere
    nodes = np.array([[0.5 * MI, 0.5 * MI], [3.0 * MI, 1.0 * MI], [20.0 * MI, 1.0 * MI]])
    s = ls.surface(nodes, code_xy, code_z, anc_xy, anc_z)
    assert s.loc[0, "basis"] == "direct" and abs(s.loc[0, "z"] - 10_300.0) < 1
    assert s.loc[1, "basis"] == "thickness" and abs(s.loc[1, "z"] - 10_300.0) < 1  # anchor 10,000 + thickness 300
    assert pd.isna(s.loc[2, "basis"]) and np.isnan(s.loc[2, "z"])


def test_compare_states():
    idx = pd.MultiIndex.from_tuples([(0, 0), (1, 0), (2, 0), (3, 0)], names=["ix", "iy"])
    up = pd.DataFrame({"z": [10_000.0, 10_000.0, 10_000.0, 10_000.0]}, index=idx)
    lo = pd.DataFrame({"z": [10_200.0, 10_030.0, 9_990.0, np.nan]}, index=idx)
    c = ls.compare(up, lo, 50.0)
    assert c["state"].tolist() == ["separated", "merged", "crossing"]
    assert c["gap_ft"].tolist() == [200.0, 30.0, -10.0]


def test_extent_codes():
    assert ls.extent_codes("delaware", "WCA") == ("WCXY", "WCA_1", "WCA_2")
    assert ls.extent_codes("midland", "WCB_1") == ("WCB_1",)
