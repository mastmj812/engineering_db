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
