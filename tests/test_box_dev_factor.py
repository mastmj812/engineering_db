"""BOX step 5c — DB-free tests for the dev-scenario factor math (box/dev_factor.py)."""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from box import dev_factor as dfm


def _nb(n_parent: int = 0, off: float | None = None, dz: float | None = None, n_codev: int = 0, cdz: float | None = None, age: float | None = None) -> dict:
    return {"n": n_parent + n_codev, "n_parent": n_parent, "n_codev": n_codev, "n_child": 0, "parent_min_offset_ft": off,
            "parent_nearest_dtvd_ft": dz, "codev_nearest_dtvd_ft": cdz, "parent_min_age_days": age}


# ---------------------------------------------------------------- sql/50 replication


def test_classify_topfill_underfill_sandwich() -> None:
    assert dfm.classify("WCA_1", {"WCB_1": _nb(2, 300, 450)})["scenario_class"] == "topfill"
    r = dfm.classify("WCA_1", {"BS3_S": _nb(1, 500, -600)})
    assert (r["scenario_class"], r["parent_above"]) == ("underfill", "BS3_S")
    r = dfm.classify("WCA_1", {"WCB_1": _nb(1, 300, 450), "BS3_S": _nb(1, 500, -600)})
    assert (r["scenario_class"], r["parent_below"], r["parent_above"]) == ("sandwich", "WCB_1", "BS3_S")


def test_classify_gates_are_inclusive_at_660_and_1000() -> None:
    assert dfm.classify("WCA_1", {"WCB_1": _nb(1, 660, 1000)})["scenario_class"] == "topfill"
    assert dfm.classify("WCA_1", {"WCB_1": _nb(1, 661, 400)})["scenario_class"] == "standalone"
    assert dfm.classify("WCA_1", {"WCB_1": _nb(1, 300, 1001)})["scenario_class"] == "standalone"


def test_classify_nearest_parent_bench_and_ignored_keys() -> None:
    r = dfm.classify("WCA_1", {"WCC": _nb(1, 200, 900), "WCB_2": _nb(1, 400, 500), "(unmapped)": _nb(3, 10, 50), "WCA_1": _nb(1, 10, 20)})
    assert (r["scenario_class"], r["parent_below"]) == ("topfill", "WCB_2")
    # own-bench and unmapped parents never make a vertical class
    assert dfm.classify("WCA_1", {"WCA_1": _nb(1, 10, 20), "(unmapped)": _nb(1, 10, 50)})["scenario_class"] == "standalone"


def test_classify_shielding_and_codev_stack() -> None:
    # a co-developed WCA_2 well between subject and the WCB_1 parent shields the below side
    r = dfm.classify("WCA_1", {"WCB_1": _nb(1, 300, 600), "WCA_2": _nb(n_codev=1, cdz=200)})
    assert r["shielded_below"] and r["scenario_class"] == "codev_stack"
    # codev BEYOND the parent does not shield
    assert dfm.classify("WCA_1", {"WCB_1": _nb(1, 300, 400), "WCC": _nb(n_codev=1, cdz=800)})["scenario_class"] == "topfill"
    # mirrored above
    r = dfm.classify("WCA_1", {"BS3_S": _nb(1, 300, -700), "WCXY": _nb(n_codev=1, cdz=-150)})
    assert r["shielded_above"] and r["scenario_class"] == "codev_stack"
    assert dfm.classify("WCA_1", {"WCB_1": _nb(n_codev=2, cdz=500)})["scenario_class"] == "codev_stack"
    assert dfm.classify("WCA_1", {})["scenario_class"] == "standalone"
    assert dfm.classify("WCA_1", None)["scenario_class"] is None


def test_classify_infill_flag_and_age() -> None:
    r = dfm.classify("WCA_1", {"WCA_1": _nb(2, 100, 30, age=800)})
    assert r["infill"] and r["infill_parent_age_days"] == 800 and r["scenario_class"] == "standalone"
    assert dfm.classify("WCA_1", {"WCB_1": _nb(1, 300, 400)})["infill_parent_age_days"] is None


# ---------------------------------------------------------------- labels


def test_parent_bench_and_pair_labels() -> None:
    assert dfm.parent_bench("topfill", "WCB_1", None) == "WCB_1"
    assert dfm.parent_bench("underfill", None, "BS3_S") == "BS3_S"
    assert dfm.parent_bench("sandwich", "WCB_1", "BS3_S") == "WCB_1+BS3_S"
    assert dfm.parent_bench("codev_stack", None, None) is None
    cls = pd.Series(["topfill"] * 12 + ["topfill"] * 3 + ["sandwich", "codev_stack"])
    par = pd.Series(["WCB_1"] * 12 + ["WCD"] * 3 + ["a+b", None])
    lab = dfm.pair_labels(cls, par, min_wells=10)
    assert lab.iloc[0] == "topfill|WCB_1" and lab.iloc[12] == "topfill|other" and lab.iloc[15] == "sandwich|all" and lab.iloc[16] == "codev_stack"


def test_pool_view_relabels_same_pool_parents_as_infill() -> None:
    pair = pd.Series(["topfill|WCA_2", "topfill|WCB_1", "underfill|WCXY", "standalone"])
    inf = pd.Series([False, False, True, False])
    p2, i2 = dfm.pool_view(pair, inf, ("WCA_1", "WCA_2", "WCXY"))
    assert list(p2) == ["codev_stack", "topfill|WCB_1", "codev_stack", "standalone"]
    assert list(i2) == [True, False, True, False]


# ---------------------------------------------------------------- estimation


def _synthetic(n: int = 3000, seed: int = 1) -> tuple[pd.DataFrame, dict[str, float]]:
    """Areas differ 3x in level; topfills sit in the POOR areas (selection), infill is everywhere."""
    rng = np.random.default_rng(seed)
    area = rng.integers(0, 20, n)
    level = np.exp(np.linspace(-0.6, 0.6, 20))[area]
    p_top = np.where(area < 6, 0.35, 0.02)
    cls = np.where(rng.random(n) < p_top, "topfill|WCB_1", np.where(rng.random(n) < 0.2, "standalone", "codev_stack"))
    inf = rng.random(n) < 0.25
    truth = {"topfill|WCB_1": 0.85, "standalone": 1.05, "infill": 0.93}
    f = np.array([truth.get(c, 1.0) for c in cls]) * np.where(inf, truth["infill"], 1.0)
    y = 20_000 * level * f * np.exp(rng.normal(0, 0.3, n) - 0.045)
    x = rng.uniform(0, 30 * 5280, n)
    d = pd.DataFrame({"area": area, "pair": cls, "infill": inf, "y": y, "x": x, "yy": rng.uniform(0, 30 * 5280, n)})
    return d, truth


@pytest.mark.parametrize("estimator", ["ols", "ppml"])
def test_estimate_recovers_factors_under_location_selection(estimator: str) -> None:
    d, truth = _synthetic()
    t = dfm.term_frame(d["pair"], d["infill"])
    y = np.log(d["y"]) if estimator == "ols" else d["y"]
    res = dfm.estimate(y, t, [d["area"]], cluster=dfm.blocks(d["x"], d["yy"], 26_400), n_boot=60, ci=0.99, estimator=estimator).set_index("term")
    for k, v in truth.items():
        assert res.at[k, "factor"] == pytest.approx(v, rel=0.04)
        assert res.at[k, "ci_lo"] < v < res.at[k, "ci_hi"]
    # without the location FE the selection biases the topfill factor low (the step-5c 'raw' row)
    raw = dfm.estimate(np.log(d["y"]), t, []).set_index("term")
    assert raw.at["topfill|WCB_1", "factor"] < 0.80


def test_unsupported_term_is_nan() -> None:
    X = np.column_stack([np.ones(5), np.zeros(5), np.arange(5.0)])
    assert np.isnan(dfm.ols(X, np.arange(5.0), 2)[0])


def test_blocks_are_square_cells() -> None:
    b = dfm.blocks(np.array([0.0, 100.0, 15_900.0]), np.array([0.0, 15_000.0, 0.0]), 15_840.0)
    assert b[0] == b[1] != b[2]


# ---------------------------------------------------------------- application


def test_factor_of_and_normalisation() -> None:
    tab = {"topfill|WCB_1": 0.9, "infill": 0.95}
    assert dfm.factor_of("codev_stack", False, tab) == 1.0
    assert dfm.factor_of("topfill|WCB_1", True, tab) == pytest.approx(0.855)
    assert dfm.factor_of("underfill|XYZ", False, tab) == 1.0
    # an area of reference wells plus one infill well: the reference curve sits above the mixed mean
    m = dfm.normalisation_multiplier([100.0, 100.0, 95.0], [1.0, 1.0, 0.95])
    assert m == pytest.approx(300.0 / 295.0)


def test_factor_ladder_rungs() -> None:
    rows = pd.DataFrame({"term": ["topfill|WCB_1", "topfill|WCD", "sandwich|all", "infill"], "factor": [0.95, 0.70, 0.60, 0.93], "n_wells": [56, 9, 7, 1500]})
    lad = dfm.factor_ladder(rows, {"topfill": (0.94, 275), "sandwich": (0.7, 7)}, {"sandwich": (0.73, 16)}, min_n=30).set_index("term")
    assert lad.loc["topfill|WCB_1", ["rung", "factor"]].tolist() == [1, 0.95]
    assert lad.loc["topfill|WCD", ["rung", "factor"]].tolist() == [2, 0.94]
    assert lad.loc["sandwich|all", ["rung", "factor"]].tolist() == [3, 0.73]
    assert lad.at["infill", "rung"] == 1


def test_age_terms_buckets() -> None:
    pair = pd.Series(["topfill|WCB_1", "topfill|WCC", "codev_stack", "standalone"])
    t = dfm.age_terms(pair, pd.Series([False, False, True, False]), pd.Series([100.0, 2000.0, np.nan, np.nan]), pd.Series([np.nan, np.nan, 400.0, np.nan]))
    assert t["topfill <1y"].tolist() == [1, 0, 0, 0] and t["topfill >=3y"].tolist() == [0, 1, 0, 0]
    assert t["infill 1-3y"].tolist() == [0, 0, 1, 0] and t["standalone"].tolist() == [0, 0, 0, 1]
