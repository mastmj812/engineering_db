"""DB-free tests for the step-9b D99 judge (box/holdout9b.py)."""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from box import holdout9b as h
from box import rehearse9b as r

FROZEN = Path("docs") / "box" / "pre9b-2026-10-16"


def _frame(errs: list[float]) -> pd.DataFrame:
    rows = []
    for i, e in enumerate(errs):
        rows.append({"api10": f"a{i}", "cutoff": "2022-12-01", "package": f"p{i}", "bx": i, "by": 0,
                     **{f"actual_{s}{k}": 100.0 * (1 + e) for s in ("oil", "gas") for k in r.HORIZONS},
                     **{f"pred_box_v2_{s}{k}": 100.0 for s in ("oil", "gas") for k in r.HORIZONS},
                     **{f"bench_{s}{k}": 100.0 for s in ("oil", "gas") for k in r.HORIZONS}})
    v = pd.DataFrame(rows)
    v["pkg"] = v["cutoff"] + ":" + v["package"]
    return v


def _iv(lo: float, hi: float) -> pd.DataFrame:
    return pd.DataFrame([{"stream": s, "horizon": 12, "tuning_bias": 0.0, "interval_lo": lo, "interval_hi": hi} for s in ("oil", "gas")])


def test_holdout_bias_is_the_rehearsal_statistic_and_inside_decides() -> None:
    v = _frame([-0.2, 0.0, 0.1, 0.05])
    c = h.pooled_cells(v, "box_v2", _iv(-0.05, 0.05))
    t = r.package_table(v, "box_v2")
    b_reh = r.judge(np.ones(4, dtype=bool), t, "oil", 12, bias_only=True)[2]
    assert c.loc[0, "holdout_bias"] == pytest.approx(b_reh) == pytest.approx(np.mean([-0.2, 0.0, 0.1, 0.05]))
    assert c["inside_interval"].all() and h.verdict(c)["overall"] == "PASS"
    c2 = h.pooled_cells(v, "box_v2", _iv(0.0, 0.05))  # -1.25 % sits below the interval
    vd = h.verdict(c2)
    assert vd["overall"] == "FAIL" and vd["n_outside"] == 2 and vd["outside"] == ["oil cum-12", "gas cum-12"]


def test_bias_and_spread_are_reported_not_gating() -> None:
    v = _frame([-0.3, 0.3, -0.3, 0.3])  # mean 0, wide spread
    for s in ("oil", "gas"):
        v[f"bench_{s}12"] = v[f"actual_{s}12"]  # a perfect benchmark: zero spread
    c = h.pooled_cells(v, "box_v2", _iv(-0.05, 0.05))
    assert h.verdict(c)["overall"] == "PASS"
    assert not c["spread_ok"].any() and not c["judged_d53_size"].any()  # 4 packages < 30, spread worse than the zero-error benchmark


def test_frozen_intervals_cover_every_d99_cell() -> None:
    for spec in h.BENCHES.values():
        iv = h.load_intervals(FROZEN / spec["intervals"], spec["cells"])
        assert len(iv) == len(spec["cells"]) and (iv["interval_lo"] < iv["tuning_bias"]).all() and (iv["tuning_bias"] < iv["interval_hi"]).all()
    with pytest.raises(ValueError):
        h.load_intervals(FROZEN / "intervals_BS2_S.csv", (("oil", 36),))  # BS2_S cum-36 is not a D99 cell


def test_walk_forward_identity() -> None:
    log = [{"cutoff": "2022-12-01", "variant": "box_v2", "stream": "oil", "horizon": 12, "haircut": -0.1},
           {"cutoff": "2021-12-01", "variant": "box_v2", "stream": "oil", "horizon": 12, "haircut": None}]
    assert h.walk_forward_identity(log, log, "box_v2")["identical"].all()
    bad = [dict(log[0], haircut=-0.09), log[1]]
    assert not h.walk_forward_identity(bad, log, "box_v2")["identical"].all()
