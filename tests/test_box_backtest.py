"""BOX step 6 backtest — DB-free tests for the lateral-efficiency curve, density bins / fit and near-neighbour count."""

from __future__ import annotations

import itertools

import numpy as np
import pandas as pd
import pytest

from box import backtest as bt
from box import dev_factor as dfm


def test_lateral_efficiency_points_interp_and_extension() -> None:
    assert bt.lateral_efficiency(5000) == 1.0 and bt.lateral_efficiency(3000) == 1.0
    assert bt.lateral_efficiency(10000) == pytest.approx(0.83)  # paper label, 2,000 lb / 60 bbl
    assert bt.lateral_efficiency(10000, "1700-50") == pytest.approx(0.85)
    assert bt.lateral_efficiency(8750) == pytest.approx((0.888 + 0.83) / 2)
    assert bt.lateral_efficiency(15000) == pytest.approx(0.801 + (0.801 - 0.83))  # last slope extended
    for c in bt.CUI_DELAWARE:
        ys = [bt.lateral_efficiency(x, c) for x in range(5000, 15001, 500)]
        assert all(b <= a + 1e-12 for a, b in itertools.pairwise(ys))  # never increases with length


def test_bins() -> None:
    assert bt.spacing_bin(2800.0) == bt.NO_NEIGHBOUR and bt.spacing_bin(np.nan) == bt.NO_NEIGHBOUR
    assert bt.spacing_bin(500) == "<660" and bt.spacing_bin(660) == "660-880" and bt.spacing_bin(1500) == ">=1320"
    assert bt.near_bin(0) == "0-1" and bt.near_bin(3) == "2-3" and bt.near_bin(9) == "6+" and bt.near_bin(None) is None
    assert bt.lateral_bin(15000) == ">=13.5k"


def test_ppml_offset_recovers_multipliers() -> None:
    rng = np.random.default_rng(3)
    n = 4000
    d = pd.DataFrame({"near": rng.choice(["0-1", "2-3", "6+"], n), "spacing": rng.choice(["<660", "880-1320"], n)})
    pred = rng.uniform(50, 150, n)
    true = {"near=0-1": 1.1, "near=6+": 0.7, "spacing=<660": 0.8}
    m = bt.density_multiplier(d, true, ("near", "spacing"), {"near": "2-3", "spacing": "880-1320"})
    d["pred"], d["act"] = pred, pred * m * 0.9 * rng.gamma(50, 1 / 50, n)
    f = bt.fit_density(d, "act", "pred", ("near", "spacing"), {"near": "2-3", "spacing": "880-1320"})
    for k, v in true.items():
        assert f[k] == pytest.approx(v, rel=0.03)
    mm = bt.density_multiplier(d, f, ("near", "spacing"), {"near": "2-3", "spacing": "880-1320"})
    k = bt.normaliser(pred, mm)
    assert (pred * mm * k).sum() == pytest.approx(pred.sum())


def test_near_neighbours_counts_within_window_parents_and_codev_only() -> None:
    ctx = {
        "WCA_1": {"n_codev": 2, "n_parent": 0, "n_child": 5, "codev_nearest_dtvd_ft": 90, "median_dtvd_ft": 100},
        "BS3_S": {"n_codev": 2, "n_parent": 1, "codev_nearest_dtvd_ft": -230, "parent_nearest_dtvd_ft": -700, "median_dtvd_ft": -250},
        "WCB_1": {"n_codev": 1, "n_parent": 0, "codev_nearest_dtvd_ft": None, "median_dtvd_ft": 340},
        "BS1_S": {"n_codev": 0, "n_parent": 2, "parent_nearest_dtvd_ft": -2500},
    }
    assert dfm.near_neighbours(ctx) == 2 + 2 + 1  # children never count; the 700-ft parent and 2,500-ft BS1_S are outside 500 ft
    assert dfm.near_neighbours(ctx, 800) == 6


def test_lateral_relative_keeps_area_mix_as_reference() -> None:
    from box import lateral as lat

    members = [7500.0, 10000.0, 12500.0]
    e = [lat.lateral_efficiency(x) for x in members]
    assert lat.relative(10000.0, members) == pytest.approx(0.83 / np.mean(e))
    assert np.mean([lat.relative(x, members) for x in members]) == pytest.approx(1.0)
    assert lat.RECORD_CURVE == "2000-60"
