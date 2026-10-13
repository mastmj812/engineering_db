"""DB-free tests for the 3-D spacing geometry (box/spacing3d.py)."""

from __future__ import annotations

import pytest
from shapely.geometry import LineString

from box import spacing3d as s3


def test_pair_geometry_offset_sign_overlap() -> None:
    s = LineString([(0, 0), (0, 10000)])  # heading north
    west = LineString([(-880, 0), (-880, 10000)])
    east_half = LineString([(660, 5000), (660, 10000)])
    short = LineString([(500, 0), (500, 2000)])
    p = s3.pair_geometry(s, west, 9000, 9100, -400, "w")
    assert p is not None and p.dxy == pytest.approx(880) and p.dz == 100 and p.relation == "parent"  # west = left of a north heading
    q = s3.pair_geometry(s, east_half, 9000, 9000, 10, "e")
    assert q is not None and q.dxy == pytest.approx(-660) and q.overlap == pytest.approx(0.5) and q.relation == "codev"
    assert s3.pair_geometry(s, short, 9000, 9000, 0, "x") is None  # 20 % overlap < 30 %


def test_voronoi_xsec() -> None:
    assert s3.voronoi_xsec([]) == pytest.approx((2 * s3.GATE) ** 2 / s3.ANISO)
    two = [s3.Pair("a", 1, 880, 0, 0), s3.Pair("b", 1, -880, 0, 0)]
    # horizontal cell width = 880 ft (bisectors at +-440), height = 2 x GATE in scaled units -> / A
    assert s3.voronoi_xsec(two) == pytest.approx(880 * 2 * s3.GATE / s3.ANISO)


def test_features_children_excluded_and_unbounded_side() -> None:
    ps = [s3.Pair("l", 1, 700, 50, -400), s3.Pair("c", 1, -300, 10, 900), s3.Pair("up", 1, 0, -250, 0)]
    f = s3.features(ps, 10000.0, {"l": 200000.0}, [ps[1]])
    assert f["nn_left_ft"] == pytest.approx(700) and f["nn_right_ft"] is None  # the child on the right is ignored
    assert f["lat_spacing_ft"] == pytest.approx((700 + s3.GATE) / 2)
    assert f["parent_cum_kbbl_per_kft"] == pytest.approx(200.0 / 10)
    assert f["n_child_24mo"] == 1 and f["n_ellipse"] == 1  # "up" (0, -250) is inside 660 x 300; "l" at 700 ft is not


def test_params_filter_stored_pairs_by_gate_and_overlap() -> None:
    from dataclasses import replace

    near = s3.Pair("n", 0.9, 700, 0, -400, dmin=650)
    far = s3.Pair("f", 0.9, -3000, 0, -400, dmin=2900)  # stored at the 3,960-ft gate, outside the default 2,640
    thin = s3.Pair("t", 0.15, -900, 0, -400, dmin=850)  # stored at the 10 % floor, under the default 30 %
    f = s3.features([near, far, thin], 10000.0)
    assert f["n_pairs"] == 1 and f["nn_right_ft"] is None
    g = s3.features([near, far, thin], 10000.0, prm=replace(s3.DEFAULT, gate_ft=3960.0, min_overlap=0.10))
    assert g["n_pairs"] == 3 and g["nn_right_ft"] == pytest.approx(900)  # nearest right among the stored pairs
