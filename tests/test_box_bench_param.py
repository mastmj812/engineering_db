"""DB-free tests for the step-9a bench parameter (box/acceptance.BENCH_SPECS, box/analog bench label, walk-forward variants)."""

from __future__ import annotations

import datetime as dt
from pathlib import Path

import numpy as np
import pandas as pd
import pytest
from scipy.spatial import cKDTree

from box import acceptance as ac
from box import analog as an
from dealintake import config as di_config

_COLS = ["api10", "formation_blueox", "planned", "tvd_round", "cohort", "first_production_date", "lateral_length_ft", "mid_lon", "mid_lat"]


def _wells_dir(tmp_path: Path) -> Path:
    rows = [("4200000001", "WCA_1"), ("4200000002", "WCA_2"), ("4200000003", "WCXY"), ("4200000004", "WCXY"), ("4200000005", "WCB_1")]
    d = pd.DataFrame([{"api10": a, "formation_blueox": t, "planned": "False", "tvd_round": "False", "cohort": "True",
                       "first_production_date": "2020-01-01", "lateral_length_ft": 10000.0, "mid_lon": -103.5, "mid_lat": 31.8} for a, t in rows], columns=_COLS)
    d.to_csv(tmp_path / "wells_final_WCA.csv", index=False)
    return tmp_path


def test_wcxy_pool_is_wcxy_tagged_only_d20(tmp_path: Path) -> None:
    wd = _wells_dir(tmp_path)
    w, _, t = ac.bench_wells(wd, "WCXY")
    assert sorted(w["formation_blueox"]) == ["WCXY", "WCXY"]  # WCA_1 never WCXY evidence (D20); a reassigned WCB_1 neither
    assert t == {"4200000003", "4200000004"}
    w2, _, t2 = ac.bench_wells(wd, "WCXY_on_WCA")  # sensitivity: whole WCA pool, WCXY targets
    assert len(w2) == 5 and t2 == t
    w4, _, t4 = ac.bench_wells(wd, "WCXY_WCA1")  # pre-registered pool: WCXY + WCA_1, never WCA_2
    assert sorted(w4["formation_blueox"]) == ["WCA_1", "WCXY", "WCXY"] and t4 == t
    w3, _, t3 = ac.bench_wells(wd, "WCA")  # WCA unchanged: every row, every row scored
    assert len(w3) == 5 and t3 is None


def test_full_fold_is_wca_only() -> None:
    with pytest.raises(ValueError):
        ac.run(None, Path("."), Path("."), "sha", bench="BS2_S", fold="full")
    with pytest.raises(ValueError):
        ac.run(None, Path("."), Path("."), "sha", bench="BS2_S", fold="analog", mode="v1")


def _pool(n: int, ring_ft: float) -> dict:
    ang = np.linspace(0, 2 * np.pi, n, endpoint=False)
    p = {"Di": 2.0, "b": 1.0, "qi": 50.0, "qo": 0.0, "peak_index_months": 2, "onset_index_months": 0, "Df": 0.08}
    return {"api10": np.array([f"w{i}" for i in range(n)]), "x": ring_ft * np.cos(ang), "y": ring_ft * np.sin(ang), "fp": [dt.date(2020, 1, 1)] * n,
            "lateral": np.full(n, 10000.0), "months": np.full(n, 24.0), "spacing": np.full(n, 900.0), "oil12_kft": np.full(n, 20000.0),
            "f_oil": np.ones(n), "tvd": 9000.0 + np.arange(n, dtype=float), "params": {f"w{i}": {"oil": dict(p), "gas": dict(p), "water": None} for i in range(n)}}


def test_bench_label_never_changes_selection() -> None:
    cfg = di_config.load()
    pool = _pool(30, 6.0 * an.MI)
    tree = cKDTree(np.column_stack([pool["x"], pool["y"]]))
    loc = {"api10": "x", "x": 0.0, "y": 0.0, "lateral_ft": 10000.0, "spacing_ft": 900.0}
    ref = an.select_cohort(pool, tree, cfg, loc)
    ref2 = an.select_cohort_v2(pool, tree, cfg, loc)
    for b in ("BS2_S", "WCXY"):
        assert an.select_cohort(pool, tree, cfg, loc, bench=b) == ref
        diag: dict = {}
        assert an.select_cohort_v2(pool, tree, cfg, loc, bench=b, diag=diag) == ref2
        assert set(diag) == {"strike_az_deg", "strike_r2", "strike_n", "strike_dip_ft_mi"}


def _view(bias: float) -> pd.DataFrame:
    v = pd.DataFrame({"api10": [f"a{i}" for i in range(40)], "package": [f"p{i}" for i in range(40)]})
    for s in ac.STREAMS:
        for k in ac.HORIZONS:
            v[f"actual_{s}{k}"] = 100.0
            v[f"bench_{s}{k}"] = 100.0
            for b in ac.VARIANTS_ANALOG_BASE:
                v[f"pred_{b}_{s}{k}"] = 100.0 / (1.0 + bias)
                v[f"{b}_err_{s}{k}"] = bias
    return v


def test_walk_forward_suffix_and_history() -> None:
    cuts = ("2019-12-01", "2020-12-01", "2021-12-01")
    views = {c: _view(-0.10) for c in cuts}
    cells = pd.concat([ac.score_fold(v, c, ac.VARIANTS_ANALOG_BASE) for c, v in views.items()], ignore_index=True)
    own = pd.concat(ac.apply_walk_forward(cells, views), ignore_index=True)
    assert set(own.variant) == {"di_p50_wf", "box_v2_wf"} and len(ac.WF_LOG) > 0
    r = own[(own.cutoff == "2021-12-01") & (own.variant == "box_v2_wf")]
    assert np.allclose(r["pkg_bias"], 0.0)  # own haircut (-10 % twice) removes the -10 % bias exactly
    hist = cells.assign(pkg_bias=0.05)  # another bench's history: +5 % -> its haircut overcorrects
    n_log = len(ac.WF_LOG)
    log: list = []
    oth = pd.concat(ac.apply_walk_forward(cells, {c: _view(-0.10) for c in cuts}, hist, suffix=ac.WCA_WF, log=log), ignore_index=True)
    assert set(oth.variant) == {"di_p50_wf_wca", "box_v2_wf_wca"} and len(ac.WF_LOG) == n_log and log
    r = oth[(oth.cutoff == "2021-12-01") & (oth.variant == "box_v2_wf_wca")]
    assert np.allclose(r["pkg_bias"], (1 - 0.10) / (1 + 0.05) - 1)
