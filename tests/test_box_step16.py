"""box/analog.Rules + box/step16 — the pre-registered step-16 selection variants, local evidence and the adoption rule (DB-free)."""

from __future__ import annotations

import datetime as dt

import numpy as np
import pandas as pd
import pytest
from scipy.spatial import cKDTree

from box import analog as an
from box import step16 as s16
from dealintake import config as di_config

MI = an.MI
P = {"Di": 2.0, "b": 1.0, "qi": 50.0, "qo": 0.0, "peak_index_months": 1, "onset_index_months": 0, "Df": 0.08}


def _pool(rows: list[tuple[float, float, float, float]]) -> dict:
    """rows = (x mi, lateral ft, months, spacing ft); y = 0, every well a 2020 well with a flat TVD."""
    a = np.array(rows, dtype=float)
    n = len(rows)
    ids = np.array([f"w{i}" for i in range(n)])
    return {"api10": ids, "x": a[:, 0] * MI, "y": np.zeros(n), "fp": [dt.date(2020, 1, 1)] * n, "lateral": a[:, 1],
            "months": a[:, 2], "spacing": a[:, 3], "tvd": np.full(n, 10_000.0), "oil12_kft": np.full(n, 20_000.0),
            "f_oil": np.ones(n), "params": {w: {"oil": dict(P), "gas": dict(P), "water": None} for w in ids}}


def _sel(pool: dict, rules: an.Rules = an.RECORD_RULES, lateral: float = 7_720.0) -> tuple[list[int], float, list[str], str]:
    tree = cKDTree(np.column_stack([pool["x"], pool["y"]]))
    loc = {"api10": "pud", "x": 0.0, "y": 0.0, "lateral_ft": lateral, "spacing_ft": 1_000.0}
    return an.select_cohort_v2(pool, tree, di_config.load(), loc, bench="BS1_S", rules=rules)


def _pad1925() -> dict:
    # five 10,000-ft wells at 1.7-2.6 mi (outside the 7,720-ft +/-25 % band), two standalone (NaN) 8,000-ft wells at 3 mi,
    # and 10 in-band wells at 18 mi: the record reaches 20 mi
    near = [(1.7 + 0.2 * i, 10_000.0, 16.0, 1_100.0) for i in range(5)]
    alone = [(3.0, 8_000.0, 30.0, np.nan), (3.2, 8_000.0, 30.0, np.nan)]
    far = [(18.0 + 0.1 * i, 7_800.0, 40.0, 1_000.0) for i in range(10)]
    return _pool(near + alone + far)


def test_rules_reject_unknown_or_repeated_steps():
    with pytest.raises(ValueError):
        an.Rules(relax=("distance",))
    with pytest.raises(ValueError):
        an.Rules(relax=("lateral", "lateral"))


def test_record_rules_reach_the_far_cohort():
    idx, r, flags, _ = _sel(_pad1925())
    assert r == 20.0
    assert sorted(idx) == list(range(7, 17)) and not any("relaxed" in f for f in flags)


def test_ranked_ladder_closes_on_the_near_wells_with_count_and_cui_flags():
    idx, r, flags, _ = _sel(_pad1925(), an.Rules(relax=("count", "spacing", "lateral")))
    assert r == 5.0
    # spacing relaxed admits the two standalone 8,000-ft wells (in band), lateral relaxed admits the five 10,000-ft wells
    assert sorted(idx) == list(range(7))
    assert "relaxed: lateral+spacing" in flags and an.LATERAL_RELAXED in flags and "relaxed: count (7 < 10)" in flags


def test_lateral_only_and_spacing_only():
    pool = _pad1925()
    idx, r, flags, _ = _sel(pool, an.Rules(relax=("spacing",)))
    assert r > 5.0  # 2 standalone wells are far below 10: the ring still expands
    idx, r, flags, _ = _sel(pool, an.Rules(relax=("count", "lateral")))
    assert r == 5.0 and sorted(idx) == list(range(5)) and an.LATERAL_RELAXED in flags


def test_relax_steps_stop_once_the_ring_is_full():
    rows = [(1.0 + 0.05 * i, 7_700.0, 30.0, 1_000.0) for i in range(10)] + [(1.5, 10_000.0, 30.0, 1_000.0)]
    idx, r, flags, _ = _sel(_pool(rows), an.Rules(relax=("count", "spacing", "lateral")))
    assert r == 5.0 and len(idx) == 10 and not any("relaxed" in f for f in flags)  # the record rules already filled the ring


def test_level_only_admits_post_peak_wells_only():
    rows = [(1.0 + 0.05 * i, 7_700.0, 30.0, 1_000.0) for i in range(8)] + [(2.0, 7_700.0, 4.0, 1_000.0), (2.1, 7_700.0, 4.0, 1_000.0)]
    pool = _pool(rows)
    pool["params"]["w9"]["oil"] = {**P, "peak_index_months": 3}  # 4 months, peak at 3 -> 1 month after peak: stays out
    idx, _, flags, _ = _sel(pool, an.Rules(relax=("count",), level_only=True))
    assert 8 in idx and 9 not in idx and "level_only: 1" in flags
    idx, _, _, _ = _sel(pool, an.Rules(relax=("count",)))
    assert 8 not in idx  # without level_only the 6-month floor holds


def test_lateral_multiplier_translates_only_short_or_relaxed():
    assert an.lateral_multiplier(10_360.0, [10_000.0, 10_500.0], ()) == pytest.approx(10.36)
    assert an.lateral_multiplier(7_720.0, [10_000.0], [an.LATERAL_RELAXED]) > 7.72  # shorter lateral: higher per-ft efficiency
    assert an.lateral_multiplier(5_080.0, [10_000.0], ()) > 5.08


def test_measured_pool_and_local_evidence():
    pool = _pool([(1.0, 10_000.0, 30.0, np.nan), (2.0, 10_000.0, 8.0, np.nan), (4.0, 10_000.0, 30.0, np.nan)])
    pool["fp"][0] = dt.date(2015, 6, 1)
    m = s16.measured_pool(pool, {"w0": 900.0, "w2": 1_200.0})
    assert m["spacing"][0] == 900.0 and np.isnan(m["spacing"][1]) and m["spacing"][2] == 1_200.0
    tree = cKDTree(np.column_stack([pool["x"], pool["y"]]))
    assert s16.local_evidence(pool, tree, 0.0, 0.0)[0] == 0  # w0 pre-2016, w1 < 12 months, w2 beyond 3 mi
    pool["fp"][0] = dt.date(2018, 1, 1)
    assert s16.local_evidence(pool, tree, 0.0, 0.0) == (1, 20_000.0)


def test_variants_are_preregistered_on_the_measured_pool():
    assert set(s16.VARIANTS) == {"box_v2s", "box_v2s_lat", "box_v2s_lo", "box_v2s_r1", "box_v2s_r1lo"}
    assert all(k == s16.MEASURED for k, _ in s16.VARIANTS.values())
    assert s16.VARIANTS[s16.BASE][1] == an.RECORD_RULES
    assert set(s16.CANDIDATES) | set(s16.ATTRIBUTION) | {s16.BASE} == set(s16.VARIANTS)


def _cells(fails: dict[str, int], bias: dict[str, float]) -> pd.DataFrame:
    rows = []
    for v in (s16.BASE, *s16.CANDIDATES):
        for i in range(6):
            rows.append({"variant": v, "verdict": "FAIL" if i < fails[v] else "PASS", "pkg_bias": bias[v] * (1 if i % 2 else -1)})
    return pd.DataFrame(rows)


def test_adopt_picks_the_passing_candidate_and_needs_the_hindcast_for_level_only():
    cells = _cells({"box_v2s": 2, "box_v2s_r1": 1, "box_v2s_r1lo": 1}, {"box_v2s": 0.08, "box_v2s_r1": 0.06, "box_v2s_r1lo": 0.05})
    strat = pd.DataFrame({"variant": ["box_v2s", "box_v2s_r1", "box_v2s_r1lo"], "bias": [-0.20, -0.08, -0.07]})
    off = pd.DataFrame({"variant": ["box_v2s", "box_v2s_r1", "box_v2s_r1lo"], "share_off": [0.30, 0.15, 0.14]})
    assert s16.adopt(cells, strat, off, hindcast_bias=0.10)["adopted"] == "box_v2s_r1lo"
    r = s16.adopt(cells, strat, off, hindcast_bias=None)  # level-only never adopted without its hindcast
    assert r["adopted"] == "box_v2s_r1" and not r["checks"]["box_v2s_r1lo"]["hindcast"]
    worse = pd.DataFrame({"variant": ["box_v2s", "box_v2s_r1", "box_v2s_r1lo"], "bias": [-0.05, -0.08, -0.07]})
    assert s16.adopt(cells, worse, off, hindcast_bias=0.10)["adopted"] == s16.BASE  # far-with-local stratum got worse


def test_stratum_is_fixed_by_the_base_selection():
    v = pd.DataFrame({"box_v2s_radius_mi": [20.0, 15.0, 5.0, 20.0], "box_v2s_r1_radius_mi": [5.0, 5.0, 5.0, 5.0], "n_local": [3, 5, 9, 2],
                      "actual_oil12": [100.0, 100.0, 100.0, 100.0], "pred_box_v2s_oil12": [125.0, 125.0, 80.0, 50.0],
                      "pred_box_v2s_r1_oil12": [100.0, 100.0, 100.0, 100.0]})
    m = s16.stratum_mask(v)
    assert list(m) == [True, True, False, False]  # the r1 radius never redefines the set
    assert s16.stratum_bias(v, "box_v2s", "oil", 12, m) == (pytest.approx(-0.2), 2)
    assert s16.stratum_bias(v, "box_v2s_r1", "oil", 12, m) == (pytest.approx(0.0), 2)
    assert s16.abs_error_stats([0.1, -0.3, 0.0])["share_gt25"] == pytest.approx(1 / 3)


def test_prediction_path_carries_the_variants_and_leaves_box_v2_unchanged():
    # the harness path (predict_many_v2 -> predict_location_v2 -> monthly_arrays_v2) on a synthetic pool, in-process
    rows = [(1.0 + 0.1 * i, 10_000.0, 30.0, np.nan) for i in range(12)]  # measured spacing missing in the record pool
    pool = _pool(rows)
    pm = s16.measured_pool(pool, {f"w{i}": 1_000.0 for i in range(12)})
    loc = {"api10": "pud", "x": 0.0, "y": 0.0, "lateral_ft": 10_360.0, "lateral_eff": 10_360.0, "spacing_ft": 1_000.0}
    k = 24
    base = an.predict_many_v2([loc], pool, pool, dt.date(2024, 12, 1), k, workers=1, bench="BS1_S")
    with16 = an.predict_many_v2([loc], pool, pool, dt.date(2024, 12, 1), k, workers=1, bench="BS1_S",
                                extra_pools={s16.MEASURED: pm}, variants16=s16.VARIANTS)
    assert "box_v2" not in base[0]  # every record-pool well is standalone: no cohort
    assert with16[0]["box_v2s_n"] == 12 and with16[0]["box_v2s_radius_mi"] == 5.0
    arr = an.monthly_arrays_v2(with16, k, (*an.VARIANTS_V2, *s16.VARIANTS))
    assert np.isfinite(arr["box_v2s"]["oil"]).all() and np.isnan(arr["box_v2"]["oil"]).all()
    assert with16[0].get("box_v2") == base[0].get("box_v2")
