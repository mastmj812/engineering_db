"""DB-free tests for the bench-family QC (box/family_qc.py)."""

from __future__ import annotations

import math

import numpy as np
import pandas as pd

from box import family_qc as fq

FAM = ("BS3_S", "BS3_C")


def _ruled(rows):
    cols = ["api10", "formation_blueox", "box_bench", "cons_status", "cons_suggest", "box_action", "cohort"]
    return pd.DataFrame(rows, columns=cols)


def test_membership_roles():
    d = _ruled([
        ["1", "BS3_S", "BS3_S", "agree", None, "keep", True],      # member
        ["2", "BS3_S", "BS2_S", "flag", "BS2_S", "reassign", True],  # frozen pool holds it
        ["3", "BS3_C", "BS2_S", "flag", "BS2_S", "reassign", True],  # old, not frozen, rule moves it -> kept on gate-1 judgment
        ["4", "BS3_C", "BS2_S", "flag", "BS2_S", "reassign", True],  # new, rule moves it -> out
        ["5", "BS3_S", "BS3_S", "agree", None, "keep", True],      # excluded
        ["6", "WCA_1", "BS3_S", "flag", "BS3_S", "reassign", True],  # ruled in (card verdict) -> member of BS3_S
        ["7", "WCA_1", "WCA", "agree", None, "keep", True],        # untouched
    ])
    r = fq.family_membership(d, FAM, frozen={"2": "BS2_S"}, seen_ids={"1", "2", "3", "5", "6", "7"}, excluded_ids={"5"}).set_index("api10")
    assert "7" not in r.index
    assert r.loc[["1", "2", "3", "4", "5", "6"], "family_role"].tolist() == [
        "member", "frozen_elsewhere", "old_churn_kept", "new_ruled_out", "excluded", "member"]
    assert r.at["3", "family_bench"] == "BS3_C" and r.at["6", "family_bench"] == "BS3_S"


def test_flag_ledger_wcxy_before_class():
    d = _ruled([
        ["1", "BS3_S", "BS3_S", "flag", "WCXY", "keep", True],
        ["2", "BS3_S", "BS3_S", "flag", "WCA_1", "tvd_suspect", False],
        ["3", "BS1_S", "BS1_S", "flag", "BS3_C", "keep", True],
        ["4", "WCA_2", "WCA", "flag", "WCB_1", "keep", True],  # not touching the family
    ])
    g = fq.flag_ledger(d, FAM)
    st = dict(zip(g["box_action"] + "|" + g["swap_class"], g["standing"]))
    assert st["keep|BS3_S->WCA"].startswith("into WCXY")
    assert st["tvd_suspect|BS3_S->WCA"].startswith("rejected")
    assert st["keep|BS1_S->BS3_C"].startswith("uncalibrated")
    assert len(g) == 3


def test_fe_contrast_recovers_level_shift():
    rng = np.random.default_rng(0)
    n_blk, per = 40, 12
    block = np.repeat([f"b{i}" for i in range(n_blk)], per)
    loc = np.repeat(rng.normal(0, 0.5, n_blk), per)
    is_b = np.tile(np.r_[np.zeros(per // 2), np.ones(per // 2)], n_blk).astype(int)
    year = rng.integers(2016, 2025, len(block))
    y = loc + math.log(0.9) * is_b + 0.02 * (year - 2016) + rng.normal(0, 0.05, len(block))
    est = fq.fe_contrast(y, is_b, block, year)
    assert abs(math.exp(est) - 0.9) < 0.01
    r = fq.fe_with_ci(y, is_b, block, year, n_boot=60)
    assert r["ci90"][0] < 0.9 < r["ci90"][1] and r["n_blocks_both"] == n_blk


def test_fe_contrast_ignores_single_bench_blocks():
    block = np.array(["a"] * 6 + ["b"] * 6 + ["c"] * 6)
    is_b = np.array([0, 0, 0, 1, 1, 1] * 2 + [1] * 6)
    year = np.full(18, 2020)
    y = np.r_[np.zeros(3), np.full(3, -0.1), np.zeros(3), np.full(3, -0.1), np.full(6, 5.0)]
    assert abs(fq.fe_contrast(y, is_b, block, year) - (-0.1)) < 1e-9
