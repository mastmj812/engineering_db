import numpy as np
import pandas as pd

from box import provisional as pv


def _view():
    # two cutoffs, three packages; package b has two members; one member without a forecast is ignored
    return pd.DataFrame({"pkg": ["a", "b", "b", "c", "c"], "cutoff": ["2021-12-01", "2021-12-01", "2021-12-01", "2022-12-01", "2022-12-01"],
                         "bx": [0, 1, 1, 2, 2], "by": [0, 0, 0, 0, 0],
                         "actual_oil12": [90.0, 50.0, 70.0, 110.0, 5.0], "pred_box_v2_oil12": [100.0, 60.0, 60.0, 100.0, np.nan],
                         "actual_gas12": [1.0] * 5, "pred_box_v2_gas12": [1.0] * 5})


def test_package_frame_sums_members_with_both_values():
    pk = pv.package_frame(_view(), horizons=(12,))
    o = pk[pk.stream == "oil"].set_index("pkg")
    assert np.isclose(o.loc["a", "err"], -0.10) and np.isclose(o.loc["b", "err"], 0.0) and np.isclose(o.loc["c", "err"], 0.10)
    assert o.loc["c", "p"] == 100.0  # the member with no forecast drops from numerator and denominator


def test_disclosure_and_vintage():
    pk = pv.package_frame(_view(), horizons=(12,))
    d = pv.disclosure(pk, "X").set_index("stream")
    assert d.loc["oil", "n_packages"] == 3 and np.isclose(d.loc["oil", "bias"], 0.0) and d.loc["oil", "n_blocks"] == 3
    assert d.loc["oil", "range_lo"] <= 0.0 <= d.loc["oil", "range_hi"]
    v = pv.by_vintage(pk, "X")
    o = v[v.stream == "oil"].set_index("cutoff")
    assert np.isclose(o.loc["2021-12-01", "bias"], -0.05) and o.loc["2022-12-01", "n_packages"] == 1


def test_bootstrap_degenerate_and_constant():
    lo, hi = pv.bootstrap_bias(np.array([0.1, 0.2]), np.array(["a", "a"]))
    assert np.isnan(lo) and np.isnan(hi)
    lo, hi = pv.bootstrap_bias(np.array([0.1, 0.1, 0.1]), np.array(["a", "b", "c"]))
    assert np.isclose(lo, 0.1) and np.isclose(hi, 0.1)
