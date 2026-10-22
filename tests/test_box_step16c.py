"""box/step16c — the 16c scoring pieces: level-only hindcast, off-local share, validated keep-rule (DB-free)."""

from __future__ import annotations

import datetime as dt

import numpy as np
import pandas as pd
import pytest
from boxfit.ramp_arps import model_cum_at_t
from scipy.spatial import cKDTree

from box import analog as an
from box import step16 as s16
from box import step16c as c16
from dealintake import config as di_config

MI = an.MI
P = {"Di": 2.0, "b": 1.0, "qi": 500.0, "qo": 0.0, "peak_index_months": 1, "onset_index_months": 0, "Df": 0.08}


def _pool(n_long: int = 6, n_short: int = 2) -> dict:
    n = n_long + n_short
    ids = np.array([f"w{i}" for i in range(n)])
    months = np.r_[np.full(n_long, 30.0), np.full(n_short, 5.0)]  # short wells: 5 months, peak at 1 -> 4 months after peak
    params = {}
    for i, a in enumerate(ids):
        p = dict(P) if i < n_long else {**P, "Di": 3.8, "b": 1.2}
        params[a] = {"oil": p, "gas": dict(P), "water": None}
    return {"api10": ids, "x": np.linspace(1.0, 2.0, n) * MI, "y": np.zeros(n), "fp": [dt.date(2020, 1, 1)] * n_long + [dt.date(2024, 6, 1)] * n_short,
            "lateral": np.full(n, 10_000.0), "months": months, "spacing": np.full(n, 1_000.0), "tvd": np.full(n, 10_000.0),
            "oil12_kft": np.full(n, 20_000.0), "f_oil": np.ones(n), "params": params}


def test_next_k_oil_is_the_model_cum_difference_from_onset():
    p = {**P, "onset_index_months": 2}
    want = model_cum_at_t(qo=0.0, peak_index_months=1, qi=500.0, Di=2.0, b=1.0, Df=0.08, t_years=(10 + 12 - 2) / 12) - \
        model_cum_at_t(qo=0.0, peak_index_months=1, qi=500.0, Di=2.0, b=1.0, Df=0.08, t_years=(10 - 2) / 12)
    assert c16.next_k_oil(p, 10.0) == pytest.approx(want)
    assert c16.next_k_oil(P, 10.0) > c16.next_k_oil(P, 20.0) > 0  # declining


def test_subjects_are_3_to_5_months_after_peak():
    p = _pool()
    assert c16.hindcast_subjects(p) == [6, 7]  # 5 months, peak index 1 -> 4 after peak; long wells 29 after peak


def test_hindcast_takes_the_cohort_long_well_decline_and_own_qi():
    p = _pool()
    tree = cKDTree(np.column_stack([p["x"], p["y"]]))
    rows = c16.hindcast_rows(p, tree, di_config.load(), "BS1_S", [6], {"w6": 1.0e5})
    r = rows[0]
    assert r["n_donors"] == 6 and r["n_cohort"] == 6  # as-of: the other short well (same fp) is not an analog; self left out
    transferred = c16.next_k_oil({**P, "qi": 500.0}, 5.0)  # own qi, long wells' Di 2.0 / b 1.0
    assert r["pred_next12"] == pytest.approx(transferred)
    assert r["own_next12"] == pytest.approx(c16.next_k_oil({**P, "Di": 3.8, "b": 1.2}, 5.0))
    assert r["actual_next12"] == 1.0e5
    h = pd.DataFrame(rows)
    b, n = c16.hindcast_bias(h)
    assert n == 1 and b == pytest.approx(1.0e5 / transferred - 1.0)


def test_off_local_share_uses_the_base_set_and_counts_missing_as_off():
    d = pd.DataFrame({"box_v2s_radius_mi": [20.0, 20.0, 5.0, 20.0], "n_local": [4, 4, 4, 1], "local_y1_kft": [20_000.0] * 4,
                      "box_v2s_cohort_y1_kft": [30_000.0, 21_000.0, 20_000.0, 50_000.0],
                      "box_v2s_r2_cohort_y1_kft": [21_000.0, np.nan, 20_000.0, 20_000.0]})
    s = c16.off_local_share(d, ["box_v2s", "box_v2s_r2"]).set_index("variant")
    assert s.loc["box_v2s", "n_far_with_local"] == 2  # rows 0-1 only: row 2 closed at 5 mi, row 3 has 1 local well
    assert s.loc["box_v2s", "share_off"] == 0.5 and s.loc["box_v2s_r2", "share_off"] == 0.5  # r2's NaN row is off


def test_keep_validated_rule():
    def cells(biases: list[float], verdicts: list[str]) -> pd.DataFrame:
        return pd.DataFrame({"pkg_bias": biases, "verdict": verdicts})
    rec = cells([0.05, -0.12, 0.02], ["PASS", "FAIL", "not judged"])
    assert c16.keep_validated(cells([0.04, -0.09], ["PASS", "PASS"]), rec)["keeps_validated"]
    assert not c16.keep_validated(cells([0.04, -0.11], ["PASS", "FAIL"]), cells([0.04, -0.05], ["PASS", "PASS"]))["keeps_validated"]
    assert not c16.keep_validated(cells([0.04, -0.11], ["PASS", "FAIL"]), rec)["keeps_validated"]  # one cell past 10 %


def test_stratum_and_cui_tables_read_the_views():
    n = 12
    v = pd.DataFrame({"box_v2s_radius_mi": [20.0] * n, "n_local": [5] * n, "actual_oil12": [100.0] * n,
                      "pred_box_v2s_oil12": [125.0] * n, "pred_box_v2s_r2_oil12": [100.0] * n,
                      "pred_box_v2s_r2_lin_oil12": [90.0] * n, "box_v2s_r2_lat_ratio": [0.7] * n})
    st = c16.stratum_table(v, ["box_v2s", "box_v2s_r2"]).set_index("variant")
    assert st.loc["box_v2s", "bias"] == pytest.approx(-0.2) and st.loc["box_v2s_r2", "bias"] == pytest.approx(0.0)
    ct = c16.cui_table(v, horizons=(12,))
    sh = ct[(ct.mismatch == "shorter") & (ct.stream == "oil")].iloc[0]
    assert sh.n_wells == n and sh.bias_cui == pytest.approx(0.0) and sh.bias_linear == pytest.approx(100 / 90 - 1)
    assert s16.cui_holds(pd.concat([ct, ct.assign(horizon=24)]))
