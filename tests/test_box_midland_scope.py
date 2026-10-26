"""Step 18 evidence pack: the pure arithmetic in box/midland_scope (DB-free)."""

from __future__ import annotations

import datetime as dt
import re
from pathlib import Path

import numpy as np
import pytest

from box import midland_scope as ms

D = dt.date


def test_bench_order_and_pairs() -> None:
    assert ms.BENCHES == ("US", "MS", "JM", "LSSH", "DEAN", "WCA_1", "WCB_1", "WCB_2", "WCC", "WCD")
    assert ms.ADJACENT[0] == ("US", "MS") and ms.ADJACENT[-1] == ("WCC", "WCD") and len(ms.ADJACENT) == 9
    assert not set(ms.BENCHES) & set(ms.EMERGING_D2)


def test_modern_mask_band_and_vintage() -> None:
    fp = [D(2016, 1, 1), D(2015, 12, 31), D(2020, 5, 1), D(2020, 5, 1), D(2020, 5, 1), None]
    lat = [5000, 10000, 15000, 15001, 4999, 10000]
    assert ms.modern_mask(fp, lat).tolist() == [True, False, True, False, False, False]


def test_per_kft_and_gor() -> None:
    assert ms.per_kft([150_000, 0, None], [10_000, 10_000, 10_000])[0] == pytest.approx(15_000.0)
    assert np.isnan(ms.per_kft([150_000, 0, None], [10_000, 10_000, 10_000])[1:]).all()
    assert ms.gor([300_000], [150_000])[0] == pytest.approx(2_000.0)


def test_operator_mix_hhi() -> None:
    mix = ms.operator_mix(["A"] * 50 + ["B"] * 50)
    assert mix["n_operators"] == 2 and mix["hhi"] == pytest.approx(5_000.0)
    assert ms.operator_mix(["A"] * 10)["hhi"] == pytest.approx(10_000.0)
    assert ms.operator_mix([None, ""])["top"][0]["operator"] == "(unknown)"


def test_fold_counts_window() -> None:
    fp = [D(2019, 12, 1), D(2020, 11, 30), D(2020, 12, 1), D(2019, 11, 30)]
    got = ms.fold_counts(fp, cutoffs=(D(2019, 12, 1), D(2020, 12, 1)))
    assert got == {"2019-12-01": 2, "2020-12-01": 1}


def test_analog_reach_kth_distance() -> None:
    mi = ms.FT_PER_MI
    prod = np.array([[i * mi, 0.0] for i in range(1, 11)])  # producers 1..10 mi east
    sticks = np.array([[0.0, 0.0]])
    r = ms.analog_reach(sticks, prod, ks=(5, 10))
    assert r["k5"]["p50_mi"] == pytest.approx(5.0)
    assert r["k10"]["p50_mi"] == pytest.approx(10.0)
    assert r["k5"]["share_within"]["5.0"] == 1.0 and r["k10"]["share_within"]["7.5"] == 0.0
    few = ms.analog_reach(sticks, prod[:3], ks=(5,))
    assert np.isnan(few["k5"]["p50_mi"]) and few["k5"]["share_within"]["20.0"] == 0.0


def test_local_separation_offset_and_merge() -> None:
    rng = np.random.default_rng(1)
    xy = rng.uniform(0, 2_000, size=(20, 2))
    t = np.full(20, 8_000.0)
    deep = ms.local_separation(xy, t, xy + 10, t + 250.0)
    assert deep["median_ft"] == pytest.approx(250.0) and deep["share_merged"] == 0.0 and deep["share_inverted"] == 0.0
    near = ms.local_separation(xy, t, xy + 10, t - 50.0)
    assert near["share_merged"] == 1.0 and near["share_inverted"] == 1.0
    far = ms.local_separation(xy, t, xy + 100 * ms.FT_PER_MI, t + 250.0)
    assert far == {"n_hoods": 0}


def test_colocation() -> None:
    a = np.array([[0.0, 0.0], [10 * ms.FT_PER_MI, 0.0]])
    b = np.array([[100.0, 0.0]])
    c = ms.colocation(a, b)
    assert c == {"a_with_b": 0.5, "b_with_a": 1.0}


def test_spacing_sentinel_is_unbounded() -> None:
    s = ms.spacing_stats([600, 800, 1000, 2800, None])
    assert s["share_unbounded"] == pytest.approx(0.4) and s["median_ft"] == pytest.approx(800.0)


def test_length_shares() -> None:
    s = ms.length_shares([10_000, 12_500, 15_000, 21_000, None, 0])
    assert s == {"ge_12500": 0.75, "ge_15000": 0.5, "ge_20000": 0.25, "n": 4}


def test_df_eur_ratio_direction() -> None:
    p = [{"qi": 100.0, "Di_nominal": 2.5, "b": 1.0}, {"qi": 80.0, "Di_nominal": 3.5, "b": 1.1}]
    same = ms.df_eur_ratio(p, 0.08, 0.08)
    assert same["median"] == pytest.approx(1.0)
    lower = ms.df_eur_ratio(p, 0.06, 0.08)
    assert lower["n"] == 2 and lower["p10"] > 1.0  # a slower terminal decline can only add volume


def test_plan_table_matches_plan_doc() -> None:
    """The identity check compares the live build against the table written into the plan — keep the copy honest."""
    from scripts.box_midland_scope import PLAN_TABLE

    text = Path("docs/box_type_curves_plan.md").read_text(encoding="utf-8")
    rows = re.findall(r"^\| (\w+) \| ([\d,]+) \| ([\d,]+) \| ([\d,]+) \| ([\d,]+) \(([\d,]+)\) \|$", text, flags=re.MULTILINE)
    parsed = {r[0]: tuple(int(x.replace(",", "")) for x in r[1:]) for r in rows}
    assert parsed == PLAN_TABLE
