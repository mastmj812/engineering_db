"""dealintake.cohort_qc + split_test (DB-free)."""

import pytest

pytest.importorskip("scipy")
pytest.importorskip("shapely")

from dealintake import cohort_qc, split_test
from dealintake.config import load
from dealintake.decline import nominal_from_effective
from tests._dealintake_fixtures import point_lonlat_ft, rect_ft

CFG = load()


def row(api, de, stream="oil", b=1.0, eur=500_000.0, lat=10_000.0, peak=2):
    return {"api10": api, "stream": stream, "di_initial": nominal_from_effective(de, b), "b": b,
                "eur": eur, "well_lateral_ft": lat, "peak_index_months": peak, "fit_at_bound": False}


def test_consistent_cohort_not_flagged():
    rows = [row(f"w{i}", de) for i, de in enumerate([0.66, 0.68, 0.70, 0.71, 0.72, 0.69, 0.67, 0.73])]
    res = cohort_qc.run(rows, CFG)
    assert res.streams["oil"].cohort_flag is None
    assert not [f for f in res.well_flags if f["flag"] == "di_dispersion"]


def test_level_is_not_a_flag():
    # Uniformly ~58-61%: outside the typical 65-75% but tight -> not a flag.
    rows = [row(f"w{i}", 0.58 + 0.005 * i) for i in range(8)]
    assert cohort_qc.run(rows, CFG).streams["oil"].cohort_flag is None


def test_50_beside_70_is_flagged_with_both_conventions():
    rows = [row(f"w{i}", 0.70) for i in range(6)] + [row("low1", 0.50), row("low2", 0.52)]
    res = cohort_qc.run(rows, CFG)
    flagged = {f["api10"] for f in res.well_flags if f["flag"] == "di_dispersion"}
    assert flagged == {"low1", "low2"}
    f = next(f for f in res.well_flags if f["api10"] == "low1")
    assert "/yr nom" in f["value"] and "% eff" in f["value"]
    assert f["di_effective"] == pytest.approx(0.50)
    assert res.streams["oil"].cohort_flag.startswith("autoforecast reliability suspect")  # 25% >= 20%


def test_mixed_b_compared_in_effective_space():
    # Same 70% effective at b=0.9 and b=1.2 -> different nominal Di, NOT dispersion.
    rows = [row(f"a{i}", 0.70, b=0.9) for i in range(4)] + [row(f"c{i}", 0.70, b=1.2) for i in range(4)]
    res = cohort_qc.run(rows, CFG)
    assert res.streams["oil"].n_de_flagged == 0


def test_water_reported_not_flagged():
    rows = [row(f"w{i}", 0.70, stream="water") for i in range(6)] + [row("x", 0.40, stream="water")]
    res = cohort_qc.run(rows, CFG)
    assert not [f for f in res.well_flags if f["flag"] == "di_dispersion"]
    assert res.streams["water"].n_de_flagged == 1


def test_eur_per_ft_outlier():
    rows = [row(f"w{i}", 0.70, eur=500_000 + 5_000 * i) for i in range(8)]
    rows.append(row("big", 0.70, eur=1_500_000))
    res = cohort_qc.run(rows, CFG)
    assert {f["api10"] for f in res.well_flags if f["flag"] == "eur_per_1000ft_outlier"} == {"big"}


def _wells(x_center, n, value, jitter=1.0):
    out = []
    for i in range(n):
        lon, lat = point_lonlat_ft(x_center + 200 * i, 5000)
        out.append({"api10": f"{x_center}-{i}", "lon": lon, "lat": lat, "eur_per_1000ft": value + jitter * i})
    return out


UNITS = {"west": rect_ft(0, 0, 5280, 10560), "east": rect_ft(10560, 0, 15840, 10560)}


def test_two_populations_split():
    wells = _wells(1000, 7, 40.0) + _wells(11500, 7, 60.0)
    res = split_test.run(wells, UNITS, CFG)
    assert res.recommendation == "split_by_polygon"
    assert res.test == "mann_whitney" and res.p_value < 0.05 and res.median_ratio > 1.25


def test_uniform_is_single_tc():
    wells = _wells(1000, 7, 50.0, jitter=3.0) + _wells(11500, 7, 51.0, jitter=3.0)
    assert split_test.run(wells, UNITS, CFG).recommendation == "single_tc"


def test_small_groups_never_split():
    wells = _wells(1000, 4, 40.0) + _wells(11500, 4, 80.0)
    res = split_test.run(wells, UNITS, CFG)
    assert res.recommendation == "single_tc"
    assert any("never split" in n for n in res.notes)


def test_significant_but_small_ratio_escalates():
    wells = _wells(1000, 8, 50.0, jitter=0.1) + _wells(11500, 8, 55.0, jitter=0.1)
    assert split_test.run(wells, UNITS, CFG).recommendation == "escalate"


def test_single_polygon_reports_gradient():
    wells = _wells(0, 10, 0.0, 0.0)
    for i, w in enumerate(wells):
        w["eur_per_1000ft"] = 40.0 + 0.8 * i  # +0.8 per 200 ft along x
    res = split_test.run(wells, {"only": UNITS["west"]}, CFG)
    assert res.recommendation == "single_tc"
    assert res.gradient_r2 == pytest.approx(1.0, abs=1e-6)
    assert abs(res.gradient_per_mile) == pytest.approx(0.8 * 5280 / 200, rel=0.01)
