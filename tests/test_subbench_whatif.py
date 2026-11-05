"""Pure-function tests for the sub-bench inference v2 rule (scripts.subbench_whatif). No DB."""

import numpy as np

from scripts.subbench_whatif import RULE, conf_band, current_pick, draft_pick, model_pick, vote_pick

MI = 1609.344
WCB = ["WCB_1", "WCB_2"]


def _hood(n_up=10, n_lo=10, up=11000.0, lo=11250.0, d=0.5 * MI):
    t = np.r_[np.full(n_up, up), np.full(n_lo, lo)]
    b = np.array(["WCB_1"] * n_up + ["WCB_2"] * n_lo)
    return np.full(len(t), d), t, b


def test_current_pick_copies_tvd_nearest_of_first_n():
    d = np.arange(14.0)
    t = np.array([11000.0] * 12 + [10950.0, 10950.0])
    b = np.array(["WCB_2"] * 12 + ["WCB_1"] * 2)
    assert current_pick(10950.0, t, b) == "WCB_2"        # the 13th/14th laterals are outside the 12
    assert current_pick(10950.0, t, b, n=14) == "WCB_1"
    assert current_pick(10950.0, t[:0], b[:0]) is None


def test_model_assigns_nearer_bench_mean_with_confidence():
    d, t, b = _hood()
    bench, c = model_pick(11010.0, d, t, b, WCB)
    assert bench == "WCB_1" and c > 0.99
    bench, c = model_pick(11240.0, d, t, b, WCB)
    assert bench == "WCB_2" and c > 0.99
    bench, c = model_pick(11125.0, d, t, b, WCB)        # midway: a coin flip
    assert abs(c - 0.5) < 1e-6


def test_model_declines_single_bench_unseparated_or_far():
    d, t, b = _hood(n_lo=1)
    assert model_pick(11000.0, d, t, b, WCB)[0] is None   # WCB_2 has < 2 wells
    d, t, b = _hood(lo=11020.0)
    assert model_pick(11000.0, d, t, b, WCB)[0] is None   # means < 40 ft apart
    d, t, b = _hood(d=6 * MI)
    assert model_pick(11000.0, d, t, b, WCB)[0] is None   # nothing within 5 mi


def test_vote_weights_tvd_and_distance():
    d = np.array([0.2 * MI, 3.0 * MI])
    t = np.array([11000.0, 11240.0])
    b = np.array(["WCB_1", "WCB_2"])
    assert vote_pick(11010.0, d, t, b, WCB)[0] == "WCB_1"
    bench, c = vote_pick(11235.0, d, t, b, WCB)
    assert bench == "WCB_2" and 0.5 < c <= 1.0


def test_draft_paths():
    d, t, b = _hood()
    assert draft_pick("delaware", "WCB", 11010.0, d, t, b)[2] == "local_model"
    assert draft_pick("midland", "WCB", 11010.0, d, t, b)[2] == "vote"
    far = np.full(len(t), 6 * MI)
    bench, _, path = draft_pick("delaware", "WCB", 11010.0, far, t, b)
    assert path == "frontier" and bench == "WCB_1"
    d1, t1, b1 = _hood(n_lo=1)
    assert draft_pick("delaware", "WCB", 11010.0, d1, t1, b1)[2] == "vote"   # model can't run -> vote


def test_conf_band_edges():
    assert conf_band(float("nan")) == "<0.80"
    assert conf_band(0.7999) == "<0.80"
    assert conf_band(0.80) == "0.80-0.95"
    assert conf_band(0.95) == ">=0.95"
    assert RULE["conf_bands"] == [0.80, 0.95]
