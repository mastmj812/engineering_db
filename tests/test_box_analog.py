"""DB-free tests for the D54 analog candidate (box/analog.py): radius ladder, leave-self-out, short-history transfer."""

from __future__ import annotations

import datetime as dt

import numpy as np
from scipy.spatial import cKDTree

from box import analog as an
from dealintake import config as di_config


def _pool(n: int, ring_ft: float, months: float = 24.0) -> dict:
    ang = np.linspace(0, 2 * np.pi, n, endpoint=False)
    x, y = ring_ft * np.cos(ang), ring_ft * np.sin(ang)
    p = {"Di": 2.0, "b": 1.0, "qi": 50.0, "qo": 0.0, "peak_index_months": 2, "onset_index_months": 0, "Df": 0.08}
    return {"api10": np.array([f"w{i}" for i in range(n)]), "x": x, "y": y, "fp": [dt.date(2020, 1, 1)] * n,
            "lateral": np.full(n, 10000.0), "months": np.full(n, months), "spacing": np.full(n, 900.0),
            "oil12_kft": np.full(n, 20000.0), "f_oil": np.ones(n), "params": {f"w{i}": {"oil": dict(p), "gas": dict(p), "water": None} for i in range(n)}}


def test_radius_expands_until_min_wells_and_leaves_self_out() -> None:
    cfg = di_config.load()
    pool = _pool(12, 6.0 * an.MI)  # every analog 6 mi away: 5-mi ring empty, 7.5-mi ring holds them
    tree = cKDTree(np.column_stack([pool["x"], pool["y"]]))
    loc = {"api10": "w0", "x": 0.0, "y": 0.0, "lateral_ft": 10000.0, "spacing_ft": 900.0}
    idx, r, _ = an.select_cohort(pool, tree, cfg, loc)
    assert r == 7.5 and len(idx) == 11 and 0 not in idx  # w0 is the location itself


def test_short_history_transfer_takes_pool_median() -> None:
    pool = _pool(12, 1000.0)
    pool["months"][:3] = 5.0  # 5 months -> 3 post-peak < 9
    for a in ("w0", "w1", "w2"):
        pool["params"][a]["oil"] = {**pool["params"][a]["oil"], "Di": 3.9, "b": 1.2}
    m = an.members_with_transfer(pool, list(range(12)))
    assert m[0].params["oil"]["Di"] == 2.0 and m[0].params["oil"]["b"] == 1.0  # replaced by the long wells' median
    assert m[0].params["oil"]["qi"] == 50.0
    assert m[5].params["oil"]["Di"] == 2.0


def test_as_of_rule_excludes_later_wells() -> None:
    cfg = di_config.load()
    pool = _pool(12, 1000.0)
    pool["fp"] = [dt.date(2019, 1, 1)] * 6 + [dt.date(2021, 1, 1)] * 6
    tree = cKDTree(np.column_stack([pool["x"], pool["y"]]))
    loc = {"api10": "x", "x": 0.0, "y": 0.0, "lateral_ft": 10000.0, "spacing_ft": 900.0, "fp_max": dt.date(2020, 6, 1)}
    idx, _, flags = an.select_cohort(pool, tree, cfg, loc)
    assert sorted(idx) == list(range(6)) and any("under_count" in f for f in flags)


def test_walk_forward_uses_only_earlier_cutoffs() -> None:
    hist = {"2019-12-01": -0.10, "2020-12-01": -0.20, "2021-12-01": -0.40, "2022-12-01": 0.50}
    assert an.walk_forward(hist, "2020-12-01") is None  # one earlier cutoff only
    assert abs(an.walk_forward(hist, "2021-12-01") - (-0.15)) < 1e-12  # mean of 2019 + 2020; 2021 and later never used
    assert abs(an.walk_forward(hist, "2022-12-01") - (-0.70 / 3)) < 1e-12


def test_completed_lateral_d56() -> None:
    ut = {"u": 1200.0}
    assert an.completed_lateral("u", 10000.0, ut) == 8800.0
    assert an.completed_lateral("s", 10000.0, ut) == 10000.0
    assert an.completed_lateral("u", 1500.0, ut) == 1000.0  # floored
