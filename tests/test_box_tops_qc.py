"""box/tops_qc — grid sampling, interval assignment, signed miss, per-well verdicts (synthetic grids, DB-free)."""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from box import extent_package as pkg
from box import tops_qc as tq

XS = np.arange(0.0, 50_001.0, 5_000.0)
YS = np.arange(0.0, 50_001.0, 5_000.0)


def _plane(z0: float, dzdx: float = 0.01) -> np.ndarray:
    X, _ = np.meshgrid(XS, YS)
    return z0 + dzdx * X


def _stack(gap: float = 100.0) -> dict[str, tq.Grid]:
    # every surface a tilted plane, `gap` ft below the one above it; top of stack at 8,000 ft at x = 0
    return {s: tq.Grid(s, XS, YS, _plane(8_000.0 + i * gap)) for i, s in enumerate(tq.STACK)}


def test_tag_tops_are_adjacent_stack_pairs_matching_extent_grids():
    for tag, top in tq.TAG_TOP.items():
        assert top in tq.STACK and tq.tag_base(tag) == tq.STACK[tq.STACK.index(top) + 1]
    for pool, (top, base) in pkg.GRIDS.items():
        if pool in tq.TAG_TOP:
            assert (tq.TAG_TOP[pool], tq.tag_base(pool)) == (top, base), pool
    assert tq.TAG_TOP["WCA_1"] == tq.TAG_TOP["WCA_2"] == pkg.GRIDS["WCA"][0]


def test_bilinear_sampling_is_exact_on_a_plane():
    g = tq.Grid("S", XS, YS, _plane(9_000.0, 0.02))
    xy = np.array([[12_345.0, 6_789.0], [0.0, 0.0], [50_000.0, 50_000.0]])
    np.testing.assert_allclose(g.sample(xy), 9_000.0 + 0.02 * xy[:, 0])
    assert np.isnan(g.sample(np.array([[60_000.0, 1_000.0]])))[0]  # off-lattice


def test_null_node_poisons_its_cells_only():
    z = _plane(9_000.0)
    z[2, 2] = np.nan
    g = tq.Grid("S", XS, YS, z)
    assert np.isnan(g.sample(np.array([[11_000.0, 11_000.0]])))[0]
    assert np.isfinite(g.sample(np.array([[31_000.0, 31_000.0]])))[0]


def test_interval_index_and_labels():
    d = np.array([[100.0, 200.0, 300.0]])
    assert tq.interval_index(d, np.array([50.0]))[0] == 0
    assert tq.interval_index(d, np.array([100.0]))[0] == 1  # on a surface -> below it
    assert tq.interval_index(d, np.array([250.0]))[0] == 2
    assert tq.interval_index(d, np.array([999.0]))[0] == 3
    assert tq.interval_index(np.array([[100.0, np.nan, 300.0]]), np.array([250.0]))[0] == 1  # NaN surface skipped
    assert tq.INTERVALS[0] == "ABOVE_BELL_CANYON" and tq.INTERVALS[1] == "BELL_CANYON"


def test_signed_miss():
    m = tq.signed_miss(np.array([90.0, 100.0, 150.0, 200.0, 230.0, 150.0]),
                       np.array([100.0] * 5 + [np.nan]), np.array([200.0] * 6))
    np.testing.assert_allclose(m[:5], [-10.0, 0.0, 0.0, 0.0, 30.0])
    assert np.isnan(m[5])


def _stations(api: str, tag: str, x: float, tvds: list[float]) -> pd.DataFrame:
    n = len(tvds)
    return pd.DataFrame({"api10": api, "tag": tag, "x": np.linspace(x, x + 9_000.0, n), "y": 20_000.0, "tvd": tvds})


def test_station_frame_and_well_verdicts():
    stack = _stack(gap=100.0)
    top_wcb1 = 8_000.0 + tq.STACK.index("WOLFCAMP-B1") * 100.0  # at x = 0; plane rises 0.01 ft/ft eastward
    st = pd.concat([
        # A: WCB_1 riding 50 ft below its own top along a dipping lateral -> agree, frac 0.5
        _stations("A", "WCB_1", 10_000.0, [top_wcb1 + 0.01 * x + 50.0 for x in np.linspace(10_000.0, 19_000.0, 10)]),
        # B: tagged WCB_1 but 30 ft above the WCB1 top (in the WCA interval) -> shallow, miss -30
        _stations("B", "WCB_1", 10_000.0, [top_wcb1 + 0.01 * x - 30.0 for x in np.linspace(10_000.0, 19_000.0, 10)]),
        # C: tagged WCA_1 but 20 ft below the WCB1 top -> deep, miss +20
        _stations("C", "WCA_1", 10_000.0, [top_wcb1 + 0.01 * x + 20.0 for x in np.linspace(10_000.0, 19_000.0, 10)]),
        # D: porpoises: 4 of 10 stations above the top -> still agree (60 % in), pct_above 0.4
        _stations("D", "WCB_1", 10_000.0, [top_wcb1 + 0.01 * x + (-10.0 if i < 4 else 40.0)
                                           for i, x in enumerate(np.linspace(10_000.0, 19_000.0, 10))]),
        # E: unknown tag -> unmeasured
        _stations("E", "WDFD", 10_000.0, [top_wcb1 + 0.01 * x for x in np.linspace(10_000.0, 19_000.0, 10)]),
    ], ignore_index=True)
    sf = tq.station_frame(st, stack)
    w = tq.well_summary(sf)
    assert w.loc["A", "verdict"] == "agree" and w.loc["A", "pct_in_tag"] == 1.0
    assert w.loc["A", "frac_p50"] == pytest.approx(0.5) and w.loc["A", "ft_below_top_p50"] == pytest.approx(50.0)
    assert w.loc["A", "dom_interval"] == "WOLFCAMP-B1"
    assert w.loc["B", "verdict"] == "shallow" and w.loc["B", "miss_p50"] == pytest.approx(-30.0)
    assert w.loc["B", "dom_interval"] == "WOLFCAMP_A"
    assert w.loc["C", "verdict"] == "deep" and w.loc["C", "miss_p50"] == pytest.approx(20.0)
    assert w.loc["D", "verdict"] == "agree" and w.loc["D", "pct_above_top"] == pytest.approx(0.4)
    assert w.loc["E", "verdict"] == "unmeasured"


def test_surface_crossings():
    stack = _stack(gap=100.0)
    z = stack["WOLFCAMP-B2"].z.copy()
    z[0, :] = stack["WOLFCAMP-B1"].z[0, :] - 10.0  # one row of nodes where B2 sits above B1
    stack["WOLFCAMP-B2"] = tq.Grid("WOLFCAMP-B2", XS, YS, z)
    c = tq.surface_crossings(stack).set_index("top")
    assert c.loc["WOLFCAMP-B1", "pct_crossing"] == pytest.approx(1 / len(YS))
    assert c.loc["WOLFCAMP_A", "pct_crossing"] == 0.0
    assert c.loc["WOLFCAMP_A", "iso_p50_ft"] == pytest.approx(100.0)
