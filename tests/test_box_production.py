"""BOX step 7c pure pieces (box/production.py): coverage precedence, D62 haircut table / curve / application, D64 gap geometry."""

from __future__ import annotations

from types import SimpleNamespace

import numpy as np
import pandas as pd
import pytest
from shapely.geometry import LineString

from box import production as pr


def _row(**kw):
    base = {"in_scope": True, "formation_blueox": "WCA_1", "basin": "delaware", "bench": "WCA", "inside_extent": True}
    return SimpleNamespace(**{**base, **kw})


@pytest.mark.parametrize(("kw", "want"), [
    ({}, "covered"),
    ({"inside_extent": False}, "not_covered_outside_extent"),
    ({"formation_blueox": "WCXY"}, "not_covered_wcxy"),
    ({"formation_blueox": "WCXY", "inside_extent": False}, "not_covered_wcxy"),
    ({"bench": "BS2_S", "formation_blueox": "BS2_S"}, "not_covered_unvalidated"),
    ({"bench": "BS2_S", "formation_blueox": "BS2_S", "inside_extent": False}, "not_covered_unvalidated"),
    ({"in_scope": False, "bench": "WDFD", "formation_blueox": "WDFD", "inside_extent": None}, "not_covered_emerging"),
    ({"in_scope": False, "basin": "midland", "bench": "BRNT", "formation_blueox": "BRNT", "inside_extent": None}, "not_covered_emerging"),
])
def test_classify_precedence(kw, want):
    assert pr.classify(_row(**kw)) == want


def _cells():
    rows = []
    for s in ("oil", "gas"):
        for k in pr.HORIZONS:
            rows += [{"variant": "box_v2", "stream": s, "horizon": k, "cutoff": "2021-12-01", "n_packages": 100, "pkg_bias": -0.10},
                     {"variant": "box_v2", "stream": s, "horizon": k, "cutoff": "2022-12-01", "n_packages": 300, "pkg_bias": -0.02},
                     {"variant": "box_v2", "stream": s, "horizon": k, "cutoff": "2024-12-01", "n_packages": 1, "pkg_bias": -0.99},  # thin: ignored
                     {"variant": "di_p50", "stream": s, "horizon": k, "cutoff": "2022-12-01", "n_packages": 300, "pkg_bias": 0.5}]  # other variant
    return pd.DataFrame(rows)


def test_haircut_table_package_weighted_and_filtered():
    t = pr.haircut_table(_cells())
    for s in ("oil", "gas"):
        for k in pr.HORIZONS:
            assert t[s][k]["bias"] == pytest.approx((100 * -0.10 + 300 * -0.02) / 400)
            assert t[s][k]["factor"] == pytest.approx(1 + t[s][k]["bias"])
            assert t[s][k]["n_packages"] == 400 and t[s][k]["n_cells"] == 2


def test_haircut_table_refuses_a_missing_horizon():
    c = _cells()
    with pytest.raises(ValueError):
        pr.haircut_table(c[~((c.stream == "gas") & (c.horizon == 48))])


def test_haircut_curve_holds_ends_and_interpolates():
    tab = {12: {"factor": 0.96}, 24: {"factor": 0.92}, 36: {"factor": 0.90}, 48: {"factor": 0.88}}
    f = pr.haircut_curve(tab)
    assert len(f) == pr.N_MONTHS
    assert f[0] == pytest.approx(0.96) and f[11] == pytest.approx(0.96)
    assert f[17] == pytest.approx(0.94)  # month 18: halfway 12 -> 24
    assert f[47] == pytest.approx(0.88) and f[-1] == pytest.approx(0.88)


def test_apply_haircut_matches_cumulative_at_every_month():
    rng = np.random.default_rng(0)
    raw = np.sort(rng.uniform(10, 1000, pr.N_MONTHS))[::-1]
    f = pr.haircut_curve({12: {"factor": 0.95}, 24: {"factor": 0.93}, 36: {"factor": 0.92}, 48: {"factor": 0.90}})
    v = pr.apply_haircut(raw, f)
    assert (v >= 0).all()
    assert np.allclose(np.cumsum(v), np.cumsum(raw) * f)
    assert v.sum() == pytest.approx(raw.sum() * 0.90)


def test_apply_haircut_never_negative_when_factor_falls_fast():
    raw = np.r_[1000.0, np.full(pr.N_MONTHS - 1, 1.0)]
    f = np.r_[1.0, np.full(pr.N_MONTHS - 1, 0.5)]
    v = pr.apply_haircut(raw, f)
    assert (v >= 0).all() and v.sum() == pytest.approx(raw.sum() * 0.5)


def test_perpendicular_gap_parallel_overlapping_sticks():
    a = LineString([(0, 0), (10000, 0)])
    b = LineString([(2000, 660), (12000, 660)])
    assert pr.perpendicular_gap(a, b) == pytest.approx(660)
    assert pr.perpendicular_gap(b, a) == pytest.approx(660)


def test_perpendicular_gap_needs_overlap():
    a = LineString([(0, 0), (10000, 0)])
    assert pr.perpendicular_gap(a, LineString([(9000, 500), (19000, 500)])) is None  # 10 % shared span < 30 %
    assert pr.perpendicular_gap(a, LineString([(6000, 500), (16000, 500)])) == pytest.approx(500)  # 40 %


def test_planned_gaps_nearest_excludes_self_and_range():
    t = [LineString([(0, 0), (10000, 0)])]
    nb = [t[0], LineString([(0, 880), (10000, 880)]), LineString([(0, -400), (10000, -400)]), LineString([(0, 5000), (10000, 5000)])]
    assert pr.planned_gaps(t, nb, ["pud:1"], ["pud:1", "pud:2", "pdp:3", "pud:4"]) == [pytest.approx(400)]
    assert pr.planned_gaps(t, nb[:1] + nb[3:], ["pud:1"], ["pud:1", "pud:4"]) == [None]


def test_de_eff_and_radius_class():
    assert pr.de_eff_1yr(3.0, 1.0) == pytest.approx(0.75)
    assert pr.de_eff_1yr(1.0, 0.0) == pytest.approx(1 - np.exp(-1))
    assert pr.radius_class(5.0) == "5 mi ring" and pr.radius_class(7.5) == "past 5 mi"


def test_nearest_gaps_reports_the_neighbour():
    t = [LineString([(0, 0), (10000, 0)])]
    nb = [LineString([(0, 880), (10000, 880)]), LineString([(0, -150), (10000, -150)])]
    assert pr.nearest_gaps(t, nb, ["pud:1"], ["pud:2", "pdp:3000000001"]) == [(pytest.approx(150), "pdp:3000000001")]


def test_bound_flags_never_change_the_fit():
    st = {"oil": {"params": {"Di_nominal": 4.0, "Di_eff_1yr": 0.817, "b": 1.05}}, "gas": {"params": {"Di_nominal": 2.5, "Di_eff_1yr": 0.7, "b": 1.2}}}
    f = pr.bound_flags(st, near_pdp_ft=150.0)
    assert any(x.startswith("oil Di at bound 4.0") for x in f) and any(x.startswith("gas b at bound") for x in f)
    assert any("possible realized PUD" in x for x in f)
    assert pr.bound_flags({"oil": {"params": {"Di_nominal": 3.0, "Di_eff_1yr": 0.75, "b": 1.0}}}, near_pdp_ft=600.0) == []


def test_crosswalk_carries_coextent_sticks_one_to_one():
    prev = [(1, "delaware", "WCA_1", LineString([(0, 0), (10000, 0)])),
            (2, "delaware", "WCA_1", LineString([(0, 880), (10000, 880)])),
            (3, "delaware", "WCA_2", LineString([(0, 0), (10000, 0)]))]
    new = [(101, "delaware", "WCA_1", LineString([(500, 60), (10500, 60)])),     # re-issued #1, shifted 60 ft + 500 ft along: carried
           (102, "delaware", "WCA_1", LineString([(0, 440), (10000, 440)])),     # halfway between 1 and 2: > 250 ft from both, new
           (103, "delaware", "WCA_2", LineString([(0, 10), (6000, 10)])),        # shorter re-issue of #3 (same formation): carried
           (104, "delaware", "WCA_1", LineString([(0, 880), (2000, 880)])),      # only 20 % of #2's length but it is the SHORTER stick: carried
           (105, "midland", "WCA_1", LineString([(0, 0), (10000, 0)]))]          # other basin: new
    xw = pr.crosswalk(prev, new)
    assert set(xw) == {101, 103, 104}
    assert xw[101][0] == 1 and xw[103][0] == 3 and xw[104][0] == 2
    assert xw[101][1] == pytest.approx((10000 + (250**2 - 60**2) ** 0.5 - 500) / 10000, rel=1e-3)  # round (polygonal) buffer cap at the far end


def test_crosswalk_is_greedy_by_share():
    prev = [(1, "delaware", "WCA_1", LineString([(0, 0), (10000, 0)]))]
    new = [(201, "delaware", "WCA_1", LineString([(0, 50), (10000, 50)])),
           (202, "delaware", "WCA_1", LineString([(4000, 100), (10000, 100)]))]  # also qualifies, but #201 shares more
    xw = pr.crosswalk(prev, new)
    assert xw == {201: (1, pytest.approx(1.0))}
