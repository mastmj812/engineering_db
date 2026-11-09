"""box.tag_grossmiss — rule v5.2 (the gross-miss step) on synthetic wells (no DB)."""

from __future__ import annotations

import numpy as np
import pandas as pd

from box import tag_grossmiss as gm
from box import tag_precedence as tp

MI = 1609.344
BS2 = ("SECOND BONE SPRING", "BS2_S", "2ND BONE SPRING SAND", "BS2_S")
BS3 = ("THIRD BONE SPRING", "BS3_S", "3RD BONE SPRING SAND", "BS3_S")
WCA1 = ("WOLFCAMP A", "WCA_1", "WOLFCAMP A UPPER", "WCA_1")
WCA2 = ("WOLFCAMP A", "WCA_1", "WOLFCAMP A LOWER", "WCA_2")
WDFD = ("WOODFORD", "WDFD", "WOODFORD", "WDFD")


def _ring(v: tuple, z: float, n: int = 6, rad: float = 0.6) -> list:
    return [(*v, z + k, rad * np.cos(2 * np.pi * k / n), rad * np.sin(2 * np.pi * k / n), v[1]) for k in range(n)]


def _d(rows: list, county: str = "Reeves") -> pd.DataFrame:
    """(novi_raw, novi_code, env_raw, env_code, depth, x_mi, y_mi, tag)"""
    d = pd.DataFrame(rows, columns=["novi_raw", "novi_code", "env_raw", "env_code", "depth_ft", "x", "y", "tag"])
    d["x"], d["y"] = d["x"] * MI, d["y"] * MI
    d["basin"], d["county"], d["evidence"], d["src"] = "delaware", county, True, None
    return d


def _column(bs2=9_000, bs3=9_500, wca1=10_000, wca2=10_200) -> list:
    return _ring(BS2, bs2) + _ring(BS3, bs3) + _ring(WCA1, wca1) + _ring(WCA2, wca2)


def test_constants_are_pinned():
    assert gm.RULE.miss_ft == 600.0
    assert (tp.RULE.r_mi, tp.RULE.n_min, tp.RULE.margin_ft, tp.RULE.far_ft, tp.RULE.other_match_ft) == (2.0, 3, 100.0, 300.0, 150.0)


def test_both_vendors_agree_on_the_wrong_unit_moves_by_depth():
    # both vendors say BS2_S (a case-B witness itself, left out of its own reference) but it lands in the WCA_1 band
    out = gm.assign(_d(_column() + [(*BS2, 10_020, 0, 0, "BS2_S")]), "tag").iloc[-1]
    assert out["gm_basis"] == "gm_move" and out["gm_code"] == "WCA_1" and out["gm_sub"] == "depth"
    assert out["gm_own_gap_ft"] > 600


def test_within_the_miss_threshold_is_left_alone():
    out = gm.assign(_d(_column() + [(*BS2, 9_520, 0, 0, "BS2_S")]), "tag").iloc[-1]
    assert out["gm_basis"] == "gm_ok" and out["gm_code"] == "BS2_S"


def test_human_calls_are_never_judged():
    d = _d(_column() + [(*BS2, 10_020, 0, 0, "BS2_S")])
    d.loc[d.index[-1], "src"] = "carded_call"
    out = gm.assign(d, "tag").iloc[-1]
    assert out["gm_basis"] is None and out["gm_code"] == "BS2_S"


def test_a_miss_with_no_unit_close_enough_is_kept_and_flagged():
    out = gm.assign(_d(_column() + [(*BS2, 10_700, 0, 0, "BS2_S")]), "tag").iloc[-1]
    assert out["gm_basis"] == "gm_unplaced" and out["gm_code"] == "BS2_S"


def test_inverted_references_withdraw_the_move():
    # WCA witnesses shallower than BS3 between the tag and the target: no move
    rows = _ring(BS2, 8_500) + _ring(BS3, 9_500) + _ring(WCA1, 9_300) + [(*BS2, 9_280, 0, 0, "BS2_S")]
    out = gm.assign(_d(rows), "tag").iloc[-1]
    assert out["gm_basis"] == "gm_inverted" and out["gm_code"] == "BS2_S"


def test_protected_units_are_guarded():
    rows = _ring(WCA1, 10_000) + _ring(WDFD, 11_000) + [(*WCA1, 11_010, 0, 0, "WCA_1")]
    out = gm.assign(_d(rows), "tag").iloc[-1]
    assert out["gm_target"] == "WDFD" and out["gm_basis"] == "gm_guard" and out["gm_code"] == "WCA_1"


def test_rule_b_counties_guard_bs3_wca():
    rows = _ring(BS3, 9_500) + _ring(WCA1, 10_200) + [(*BS3, 10_210, 0, 0, "BS3_S")]
    assert gm.assign(_d(rows, county="Lea"), "tag").iloc[-1]["gm_basis"] == "gm_guard"
    assert gm.assign(_d(rows, county="Reeves"), "tag").iloc[-1]["gm_basis"] == "gm_move"


def test_other_tag_placed_only_within_150_ft():
    rows = _column()
    near = gm.assign(_d(rows + [("CHERRY CANYON", "OTHER", None, None, 9_120, 0, 0, "OTHER")]), "tag").iloc[-1]
    far = gm.assign(_d(rows + [("CHERRY CANYON", "OTHER", None, None, 9_250, 0, 0, "OTHER")]), "tag").iloc[-1]
    assert near["gm_basis"] == "gm_move" and near["gm_code"] == "BS2_S" and near["gm_sub"] == "nearest"
    assert far["gm_basis"] == "gm_other_kept" and far["gm_code"] == "OTHER"


def test_no_own_reference_is_reported_not_moved():
    out = gm.assign(_d(_ring(BS3, 9_500) + [(*BS2, 10_020, 0, 0, "BS2_S")]), "tag").iloc[-1]
    assert out["gm_basis"] == "gm_no_control" and out["gm_code"] == "BS2_S"
