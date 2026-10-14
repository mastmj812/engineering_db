"""BOX step 6 — DB-free tests for the hindcast prediction, statistics and §8 / D48 / D49 verdict (box/hindcast.py)."""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from box import hindcast as hc
from box import tc_curve as tc


def test_pct_error_sign_and_guards() -> None:
    e = hc.pct_error([110, 90, 5, np.nan], [100, 100, 0, 10])
    assert e[0] == pytest.approx(0.10)  # actual above forecast = forecast LOW = positive (sql/43)
    assert e[1] == pytest.approx(-0.10)
    assert np.isnan(e[2]) and np.isnan(e[3])


def test_stats_band_is_p10_high_minus_p90_low() -> None:
    s = hc.stats(np.linspace(-0.5, 0.5, 101))
    assert s["n"] == 101 and s["bias"] == pytest.approx(0.0, abs=1e-12)
    assert s["p10_high"] == pytest.approx(0.4) and s["p90_low"] == pytest.approx(-0.4)
    assert s["band"] == pytest.approx(0.8)
    assert hc.stats([np.nan])["n"] == 0


@pytest.mark.parametrize(("box", "novi", "want"), [
    ((0.05, 0.6), (-0.20, 0.8), (True, True)),
    ((0.12, 0.6), (-0.20, 0.8), (False, True)),   # outside +-10 %
    ((-0.08, 0.6), (0.05, 0.8), (False, True)),   # inside +-10 % but worse than Novi
    ((0.02, 0.9), (-0.20, 0.8), (True, False)),   # wider band
])
def test_judge(box, novi, want) -> None:
    j = hc.judge({"n": 20, "bias": box[0], "band": box[1]}, {"n": 20, "bias": novi[0], "band": novi[1]})
    assert (j["bias_ok"], j["band_ok"]) == want
    assert j["pass"] == all(want)


def test_area_test_is_count_majority_and_strict() -> None:
    rows = pd.DataFrame({"group": [1, 2, 3, 4], "n": [12, 30, 10, 4], "pass": [True, False, True, True]})
    t = hc.area_test(rows)
    assert t["n_qualifying"] == 3 and t["n_pass"] == 2 and t["verdict"] == hc.PASS
    assert t["n_wells_thin"] == 4
    tie = hc.area_test(pd.DataFrame({"group": [1, 2], "n": [10, 82], "pass": [True, False]}))
    assert tie["verdict"] == hc.FAIL  # 1 of 2 is not a majority; well counts do not weight it (D48)
    none = hc.area_test(pd.DataFrame({"group": [1], "n": [9], "pass": [True]}))
    assert none["verdict"] == hc.INCONCLUSIVE


def _frame(box_sd: float, novi_sd: float, n: int = 40) -> pd.DataFrame:
    rng = np.random.default_rng(1)
    d = pd.DataFrame({"area_no": np.repeat([1, 2], n // 2)})
    for s in hc.SCORED_STREAMS:
        for k in hc.HORIZONS:
            d[f"box_err_{s}{k}"] = rng.normal(0.0, box_sd, n)
            d[f"novi_err_{s}{k}"] = rng.normal(-0.25, novi_sd, n)
    return d


def test_verdict_pass_needs_every_cell_oil_and_gas() -> None:
    d = _frame(0.05, 0.30)
    v = hc.verdict(d)
    assert v["overall"] == hc.PASS and v["by_stream"] == {"oil": hc.PASS, "gas": hc.PASS}
    d["box_err_gas12"] = d["box_err_gas12"] + 0.2  # gas cum-12 biased: gas fails -> overall fails (D49)
    v = hc.verdict(d)
    assert v["by_stream"]["oil"] == hc.PASS and v["by_stream"]["gas"] == hc.FAIL and v["overall"] == hc.FAIL


def test_score_groups_uses_wells_scored_by_both() -> None:
    d = _frame(0.05, 0.3)
    d.loc[0, "novi_err_oil6"] = np.nan
    assert hc.score_groups(d, None, "oil", 6).iloc[0]["n"] == len(d) - 1


def test_predict_and_calendar_factor() -> None:
    cums = {"oil6": 6000.0, "oil12": 10000.0, "gas6": 9000.0, "gas12": 16000.0}
    p = hc.predict(cums, 10_000.0, 1.02, 0.9)
    assert p["oil6"] == pytest.approx(6000 * 10 * 1.02 * 0.9)
    assert p["gas12"] == pytest.approx(16000 * 10 * 1.02 * 0.9)
    F = {"oil": {6: 0.9, 12: 0.95}, "gas": {6: 1.0, 12: 1.1}}
    pf = hc.predict(cums, 10_000.0, 1.02, 0.9, F)
    assert pf["oil12"] == pytest.approx(p["oil12"] * 0.95) and pf["gas12"] == pytest.approx(p["gas12"] * 1.1)
    actual = pd.DataFrame({"oil6": [90.0, 45.0, np.nan], "oil12": [1.0] * 3, "gas6": [1.0] * 3, "gas12": [1.0] * 3})
    pred = pd.DataFrame({"oil6": [100.0, 50.0, 70.0], "oil12": [1.0] * 3, "gas6": [1.0] * 3, "gas12": [2.0] * 3})
    Fk = hc.calendar_factor(actual, pred)
    assert Fk["oil"][6]["F"] == pytest.approx(135 / 150) and Fk["oil"][6]["n"] == 2  # ratio of sums; the NaN well drops
    assert Fk["gas"][12]["F"] == pytest.approx(0.5)


def test_curve_cums_gas_level_shift() -> None:
    fit = {"qo": 0.0, "qi": 30.0, "peak_index": 2, "Di": 2.5, "b": 1.0, "Df": 0.08, "eur_per_unit": 1.0}
    ov = tc.monthly_volumes(fit)
    curve = {"fits": {"oil": {"mean": fit}}, "record": "mean", "gas_ratio": {"alpha": np.log(1.5), "beta": 1e-5}}
    base = hc.curve_cums(curve, None)
    assert base["oil12"] == pytest.approx(float(ov[:12].sum()))
    assert np.isnan(base["gas12"])
    gor12 = tc.window_gor(ov, tc.ratio_monthly_volumes(ov, np.log(1.5), 1e-5), 12)
    at = hc.curve_cums(curve, gor12)
    up = hc.curve_cums(curve, 2.0 * gor12)
    assert up["gas12"] == pytest.approx(2.0 * at["gas12"])  # the alpha shift scales the ratio uniformly
    assert 1000 * at["gas12"] / at["oil12"] == pytest.approx(gor12)


def test_calendar_factor_curve_matches_point_factor() -> None:
    a = np.array([[10.0, 8, 6, np.nan], [20, 15, 12, 10], [5, 4, np.nan, np.nan]])
    p = np.array([[12.0, 9, 7, 6], [22, 16, 12, 11], [6, 5, 4, 3]])
    F, n = hc.calendar_factor_curve(a, p)
    assert list(n) == [3, 3, 2, 1]
    assert F[1] == pytest.approx((18 + 35 + 9) / (21 + 38 + 11))
    assert F[3] == pytest.approx(57 / 61)  # only the well with 4 months
    k2 = hc.calendar_factor(pd.DataFrame({"oil6": a[:, :2].sum(1), "oil12": 1.0, "gas6": 1.0, "gas12": 1.0}),
                            pd.DataFrame({"oil6": p[:, :2].sum(1), "oil12": 1.0, "gas6": 1.0, "gas12": 1.0}))
    assert k2["oil"][6]["F"] == pytest.approx(F[1])
