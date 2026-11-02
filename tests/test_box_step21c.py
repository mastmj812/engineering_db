"""Step 21c (DB-free): the holdout harness lifts exactly the frozen run()'s step-16 guard; the judge reads the frozen intervals of
the gate-21b record treatment; the D102 table merges tuning + holdout per cutoff before the floor."""

from __future__ import annotations

import hashlib

import numpy as np
import pandas as pd
import pytest

from box import acceptance as ac
from box import step21 as st
from box import step21c as c


def test_run_source_is_the_frozen_one():
    assert hashlib.sha256(c.run_source().encode("utf-8")).hexdigest() == c.RUN_SOURCE_SHA256


def test_lift_removes_exactly_the_guard():
    d = c.source_diff()
    assert d == ["- " + ln for ln in c.GUARD.splitlines(keepends=True)]


def test_lifted_run_passes_the_guard_and_keeps_the_next_check():
    with pytest.raises(ValueError, match="D118"):
        ac.run(None, None, None, None, score_holdout=True, step16=True, fold="bogus")
    run = c.unguarded_run()
    with pytest.raises(ValueError, match="^bogus$"):  # the fold check, the first line after the guard
        run(None, None, None, None, score_holdout=True, step16=True, fold="bogus")
    assert run.__globals__ is ac.__dict__  # resolves names (and the 21b observer's patches) in box/acceptance


def test_lift_refuses_a_changed_run():
    with pytest.raises(RuntimeError):
        c.unguarded_source(c.run_source().replace(c.GUARD, ""))


def test_frozen_files_match_gate_21b():
    assert c.check_frozen()["identical"]


def test_record_and_frozen_rows():
    g = c.gate()
    assert c.record(g, "MID_LSSH") == {"oil": st.PROX, "gas": st.PROX}
    assert c.record(g, "MID_WCA_1") == {"oil": st.PROX_WF, "gas": st.PROX}
    fr = pd.read_csv(c.DOCS_21B / "frozen_d99.csv")
    assert c.frozen_rows(fr, "MID_WCA_1", st.PROX_WF)["role_used"].iloc[0] == "record"
    lssh = c.frozen_rows(fr, "MID_LSSH", st.PROX)
    assert lssh["role_used"].iloc[0] == "alternative" and set(lssh["treatment"]) == {st.PROX}
    with pytest.raises(RuntimeError):
        c.frozen_rows(fr, "MID_WCC", st.PROX_WF)


def test_judged_cells():
    assert c.judged_cells({12: 31, 24: 30, 36: 29}) == [("oil", 12), ("oil", 24), ("gas", 12), ("gas", 24)]
    assert c.judged_cells({12: 29}) == []


def test_d102_merges_before_the_floor():
    def cell(cut, n, b, side_variant=st.PROX):
        return {"variant": side_variant, "cutoff": cut, "stream": "oil", "horizon": 12, "n_packages": n, "pkg_bias": b}
    tun = pd.DataFrame([cell("2021-12-01", 20, -0.10), cell("2022-12-01", 40, -0.05)])
    hol = pd.DataFrame([cell("2021-12-01", 15, -0.20), cell("2022-12-01", 5, 0.0)])
    t = c.d102_table(tun, hol)
    r = t[(t.stream == "oil") & (t.horizon == 12)].iloc[0]
    # 2021 merged = 35 packages (clears the floor only merged), 2022 = 45
    b21 = (20 * -0.10 + 15 * -0.20) / 35
    b22 = (40 * -0.05 + 5 * 0.0) / 45
    assert r["n_packages"] == 80
    assert r["bias"] == pytest.approx((35 * b21 + 45 * b22) / 80)
    assert np.isnan(t[(t.stream == "gas") & (t.horizon == 12)]["factor"].iloc[0])
