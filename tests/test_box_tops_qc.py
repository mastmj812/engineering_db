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


def test_geology_rules():
    r = tq.apply_geology_rules
    assert r("AVA_1", "Reeves", "deep") == "no_surface"
    assert r("WCA_1", "Pecos", "shallow") == "masked"          # WOLFCAMP_A masked in Pecos
    assert r("WCXY", "Pecos", "deep") == "masked"              # base = WOLFCAMP_A masked
    assert r("BS3_S", "Pecos", "agree") == "agree"             # 3BSPGS -> WOLFCAMP_XY: picks exist
    assert r("AVA_2", "Pecos", "agree") == "masked"            # top = AVALON2
    assert r("AVA_0", "Pecos", "agree") == "masked"            # base = AVALON2
    assert r("WCC", "Reeves", "shallow") == "surface_suspect"  # top suspect
    assert r("WCB_2", "Reeves", "deep") == "surface_suspect"   # base suspect, deep call untrusted
    assert r("WCB_2", "Reeves", "shallow") == "shallow"        # top (B2) is fine
    assert r("WCA_1", "Reeves", "shallow") == "shallow"
    assert r("WDFD", None, "unmeasured") == "unmeasured"
    assert all(s in tq.STACK for ss in tq.MASKED_SURFACES_BY_COUNTY.values() for s in ss)
    assert tq.SUSPECT_SURFACES <= set(tq.STACK)


def test_classify_edge_and_gross():
    assert tq.classify("shallow", -20.0) == "edge"
    assert tq.classify("deep", 25.0) == "edge"          # inclusive at the tolerance
    assert tq.classify("deep", 26.0, edge_ft=25.0) == "deep"
    assert tq.classify("shallow", -301.0) == "gross"
    assert tq.classify("agree", 0.0) == "agree"
    assert tq.classify("masked", np.nan) == "masked"


def _attr_frame() -> pd.DataFrame:
    rows = []
    # west cluster (x ~ 0): six WCB_1 wells all ~80 ft above the B1 top -> structure
    for i in range(6):
        rows.append((f"W{i}", "WCB_1", 0.0 + 500 * i, 0.0, "shallow", -80.0 - i))
    # east (x ~ 50k): five agreeing WCB_1 wells + one lone well 90 ft high -> tag
    for i in range(5):
        rows.append((f"E{i}", "WCB_1", 50_000.0 + 500 * i, 0.0, "agree", 0.0))
    rows.append(("ELONE", "WCB_1", 51_000.0, 300.0, "shallow", -90.0))
    # far north: an isolated shallow well -> sparse
    rows.append(("N", "WCB_1", 0.0, 90_000.0, "shallow", -70.0))
    # mixed: neighbours sit deep, subject sits shallow
    for i in range(4):
        rows.append((f"M{i}", "WCA_2", 0.0 + 400 * i, 40_000.0, "deep", 60.0))
    rows.append(("MSUB", "WCA_2", 800.0, 40_200.0, "shallow", -60.0))
    d = pd.DataFrame(rows, columns=["api10", "tag", "x", "y", "cls", "miss"])
    d["witness"] = True
    return d.set_index("api10", drop=False)


def test_attribution_cluster_vs_lone_outlier():
    d = _attr_frame()
    a = tq.attribute(d)
    assert a.loc["W2", "attribution"] == "structure_suspect"
    assert a.loc["W2", "grid_offset_ft"] == pytest.approx(np.median([-80.0, -81.0, -83.0, -84.0, -85.0]))
    assert a.loc["ELONE", "attribution"] == "tag_suspect" and np.isnan(a.loc["ELONE", "grid_offset_ft"])
    assert a.loc["N", "attribution"] == "unresolved_sparse" and a.loc["N", "band_n"] == 0
    assert a.loc["MSUB", "attribution"] == "unresolved_mixed"
    assert a.loc["E0", "attribution"] is None  # agreeing wells are not attributed


def test_surface_residuals_and_offset_field():
    # WCA_2 wells (base = WOLFCAMP-B1) landing 40 ft BELOW the B1 top, and WCB_1 wells (top = B1) landing 60 ft
    # ABOVE it, in two separate places; both inform the WOLFCAMP-B1 surface.
    rows = [(f"A{i}", "WCA_2", 500.0 * i, 0.0, "deep", 0.0, -40.0) for i in range(5)]
    rows += [(f"B{i}", "WCB_1", 30_000.0 + 500 * i, 0.0, "shallow", -60.0, 120.0) for i in range(5)]
    rows += [(f"C{i}", "WCB_1", 60_000.0 + 500 * i, 0.0, "agree", 50.0, 100.0) for i in range(5)]
    w = pd.DataFrame(rows, columns=["api10", "tag", "x", "y", "cls", "ft_below_top", "ft_above_base"])
    w["witness"] = True
    res = tq.surface_residuals(w, "WOLFCAMP-B1")
    assert set(res.loc[res["side"] == "above", "api10"]) == {f"A{i}" for i in range(5)}
    assert res.loc[res["api10"] == "A0", "r"].iloc[0] == pytest.approx(40.0)   # B1 should go down 40 ft here
    assert res.loc[res["api10"] == "B0", "r"].iloc[0] == pytest.approx(-60.0)  # B1 should come up 60 ft here
    assert res.loc[res["api10"] == "C0", "r"].iloc[0] == 0.0
    f = tq.offset_field(res)
    assert not f.loc[(f["cx"] - 61_000.0).abs() < 3_000, "flagged"].any()
    f = f[f["flagged"]]
    near = lambda x: f.loc[(f["cx"] - x).abs() < 3_000, "offset_ft"]
    assert (near(1_000.0) > 25).all() and len(near(1_000.0))
    assert (near(31_000.0) < -25).all() and len(near(31_000.0))
    assert near(61_000.0).empty  # agreeing wells: no cell beyond the edge tolerance


def test_apply_rules_missing_verdict_is_unmeasured():
    from box import tops_qc_report as rep

    w = pd.DataFrame({"api10": ["A", "B"], "formation_blueox": ["WCB_1", "WCB_1"], "county": ["Reeves", None]})
    p = pd.DataFrame({"verdict": [np.nan, "shallow"]}, index=["A", "B"])
    out = rep.apply_rules(w, p)
    assert out.loc["A", "verdict"] == "unmeasured" and pd.isna(out.loc["A", "verdict_raw"])
    assert out.loc["B", "verdict"] == "shallow"
