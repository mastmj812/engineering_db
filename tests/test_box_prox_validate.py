"""DB-free tests for the walk-forward haircut validation (box/prox_validate.py)."""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from box import prox_validate as pv


def _cfg(rows):
    cols = ["config_class", "bench", "n_parents_total", "n_topfill", "flanked_topfill", "pb_topfill", "n_same", "flanked_same", "pb_same",
            "n_underfill", "flanked_underfill", "pb_underfill"]
    return pd.DataFrame([dict(zip(cols, r, strict=True)) for r in rows])


def test_ladder_keys() -> None:
    k = pv.ladder_keys(_cfg([
        ("topfill", "BS3_S", 3, 3, True, "WCA_2", 0, False, None, 0, False, None),
        ("same", "WCXY", 1, 0, False, None, 1, False, "WCA_1", 0, False, None),
        ("mixed", "WCA_1", 5, 2, False, "WCB_1", 3, False, "WCA_2", 0, False, None),
        (None, "BS2_S", 0, 0, False, None, 0, False, None, 0, False, None),
    ]))
    assert k.iloc[0].tolist() == ["BS3_S>topfill>WCA|3+", "topfill|3+|F", "topfill|3+", "topfill"]
    assert k.iloc[1].tolist() == ["WCA>same>WCA|1", "same|1|-", "same|1", "same"]
    assert pd.isna(k.iloc[2, 0]) and k.iloc[2, 1:].tolist() == ["mixed|4+", "mixed|4+", "mixed"]
    assert k.iloc[3].tolist() == ["none"] * 4


def _frame(seed=3):
    rng = np.random.default_rng(seed)
    rows = []
    for c in ("2019", "2020", "2021", "2022"):
        for i in range(400):
            cls = "topfill" if i % 4 == 0 else None
            n = 1 + (i % 3) if cls else 0
            hair = {0: 1.05, 1: 0.95, 2: 0.85, 3: 0.70}[n]
            rows.append({"api10": f"{c}-{i}", "cutoff": c, "bench_group": "BS3_S", "bench": "BS3_S", "block": i % 50,
                         "config_class": cls, "n_parents_total": n, "n_topfill": n, "flanked_topfill": n >= 2, "pb_topfill": "WCA_1" if cls else None,
                         "n_same": 0, "flanked_same": False, "pb_same": None, "n_underfill": 0, "flanked_underfill": False, "pb_underfill": None,
                         "l_oil24": np.log(hair * (0.9 if c == "2022" else 1.0)) + rng.normal(0, 0.1)})  # 2022: BOX fold bias -10 %
    return pd.DataFrame(rows)


def test_l_rel_removes_fold_bias_and_walk_forward_trains_on_earlier_folds() -> None:
    d = _frame()
    lr = pv.l_rel(d, "oil24")
    assert abs(lr[d["cutoff"] == "2022"].mean()) < 1e-12 and abs(lr[d["cutoff"] == "2019"].mean()) < 1e-12
    p = pv.walk_forward(d, "oil24", ("2021", "2022"))
    assert set(p["cutoff"]) == {"2021", "2022"} and (p["rung"] == "k1").all()
    s = pv.score(p, n_boot=100)
    assert s["P2"] and s["P3"] and s["P1"] and s["verdict"] == "PASS"
    assert s["P1_no_haircut"] < 0.9 < s["P1_resid"]   # the haircut removes the material cells' bias


def test_assign_falls_down_the_ladder_and_unfit_gets_one() -> None:
    keys = pd.DataFrame({"k1": ["a", "b", None], "k2": ["a2", "b2", "c2"], "k3": ["a3", "b3", "c3"], "k4": ["t", "t", "zz"]})
    table = {"k1": {"a": (-0.2, 40), "b": (-0.3, 5)}, "k2": {"b2": (-0.1, 31)}, "k3": {}, "k4": {"t": (-0.05, 500)}}
    a = pv.assign(keys, table)
    assert a["rung"].tolist() == ["k1", "k2", "unfit"] and a["ln_f"].tolist() == pytest.approx([-0.2, -0.1, 0.0])
