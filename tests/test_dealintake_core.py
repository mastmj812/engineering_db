"""dealintake: config, decline conversions, unit geometry (DB-free)."""

import copy
import math

import pytest

pytest.importorskip("shapely")
pytest.importorskip("yaml")

from dealintake import config as cfgmod
from dealintake.decline import (
    effective_from_nominal,
    fmt_di,
    nominal_from_effective,
)
from dealintake.geo import (
    axial_diff,
    fold_azimuth,
    long_axis_azimuth,
    planned_lateral,
    stick_inside,
    stick_relation,
)
from tests._dealintake_fixtures import line_ft, rect_ft


def test_config_loads_v2():
    cfg = cfgmod.load()
    assert cfg.version >= 2
    assert cfg.lateral_tolerance("Delaware") == 0.25
    assert cfg.lateral_tolerance("MIDLAND") == 0.40
    assert cfg.lateral_tolerance(None) == 0.25


def test_config_rejects_codev_drift_from_sql46():
    raw = copy.deepcopy(cfgmod.load().raw)
    raw["codev"]["window_days"] = 90
    with pytest.raises(cfgmod.ConfigError, match="sql/47"):
        cfgmod.validate(raw)


def test_config_rejects_bad_tier_order():
    raw = copy.deepcopy(cfgmod.load().raw)
    raw["codev"]["tier_order_default"] = ["codev", "codev", "stack_standalone"]
    with pytest.raises(cfgmod.ConfigError):
        cfgmod.validate(raw)


@pytest.mark.parametrize("di,b,de", [(2.33, 1.0, 0.6997), (1.0, 1.0, 0.5), (3.0, 1.0, 0.75)])
def test_effective_matches_house_table(di, b, de):
    assert effective_from_nominal(di, b) == pytest.approx(de, abs=5e-4)


@pytest.mark.parametrize("b", [0.0, 0.9, 1.0, 1.2])
def test_nominal_effective_round_trip(b):
    for de in (0.5, 0.65, 0.75):
        assert effective_from_nominal(nominal_from_effective(de, b), b) == pytest.approx(de)


def test_exponential_limit():
    assert effective_from_nominal(0.5, 0.0) == pytest.approx(1 - math.exp(-0.5))


def test_fmt_di_states_both_conventions():
    s = fmt_di(2.33, 1.0)
    assert "/yr nom" in s and "% eff" in s


def test_axial_helpers():
    assert fold_azimuth(190) == pytest.approx(10)
    assert axial_diff(179, 1) == pytest.approx(2)


def test_planned_lateral_perfect_two_mile_dsu_is_9900():
    # 1 mi E-W x 2 mi N-S, N-S development, uniform 330-ft setback.
    unit = rect_ft(0, 0, 5280, 10560)
    assert axial_diff(long_axis_azimuth(unit), 0) < 0.5
    pl = planned_lateral(unit, 0.0, setback_ft=330)
    assert pl.median_ft == pytest.approx(9900, abs=10)
    assert pl.min_ft == pytest.approx(9900, abs=10)  # mitre joins: no rounded-corner shortening


def test_planned_lateral_follows_azimuth_not_long_axis():
    unit = rect_ft(0, 0, 10560, 5280)  # E-W long axis
    assert axial_diff(long_axis_azimuth(unit), 90) < 0.5
    assert planned_lateral(unit, 90.0).median_ft == pytest.approx(9900, abs=10)
    assert planned_lateral(unit, 0.0).median_ft == pytest.approx(5280 - 660, abs=10)


def test_planned_lateral_empty_when_unit_smaller_than_setbacks():
    assert planned_lateral(rect_ft(0, 0, 500, 500), 0.0).n_chords == 0


def test_stick_inside_tolerance():
    unit = rect_ft(0, 0, 5280, 10560)
    assert stick_inside(line_ft((2000, 100), (2000, 10460)), unit, 50)
    assert stick_inside(line_ft((2000, -40), (2000, 10460)), unit, 50)  # 40 ft out: slack
    assert not stick_inside(line_ft((2000, -200), (2000, 10460)), unit, 50)  # crosses: generate


def test_stick_relation_three_way():
    unit = rect_ft(0, 0, 5280, 10560)
    assert stick_relation(line_ft((2000, 100), (2000, 10460)), unit) == "inside"
    assert stick_relation(line_ft((2000, -3000), (2000, 5000)), unit) == "crossing"
    assert stick_relation(line_ft((6000, 100), (6000, 10460)), unit) == "outside"  # next DSU east
    assert stick_relation(line_ft((5300, 100), (5300, 10460)), unit) == "inside"   # 20 ft out: slack
    assert stick_relation(line_ft((5310, -9000), (5310, 20000)), unit) == "outside"  # grazes only


def test_parse_depth_and_proposal():
    from dealintake.benches import declared_window, parse_depth, propose

    assert parse_depth("9,515'") == 9515.0
    assert parse_depth("Surface") == 0.0
    assert parse_depth("10000 ft TVD") == 10000.0
    assert parse_depth("Base of Wolfcamp") is None
    lo, hi, raw = declared_window({"MIN_DEPTH": "Surface", "max_depth": "9,515'"})
    assert (lo, hi) == (0.0, 9515.0) and raw["Max_Depth"] == "9,515'"
    stats = [
        {"formation": "WCA_1", "median_tvd_ft": 9900.0, "wells": 12},
        {"formation": "BS3_S", "median_tvd_ft": 9400.0, "wells": 8},
        {"formation": "BS2_S", "median_tvd_ft": 8500.0, "wells": 5},
    ]
    rows = {r["bench"]: r["status"] for r in propose(stats, (0.0, 9515.0), 200)}
    assert rows == {"BS2_S": "in_window", "BS3_S": "edge", "WCA_1": "out"}
    assert all(r["status"] == "no_window" for r in propose(stats, None, 200))
