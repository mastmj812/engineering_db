import numpy as np
import pandas as pd

from box import thin_bench as tb


def test_ring_reached_labels_and_cap():
    lab = tb.ring_reached(np.array([0.5, 5.0, 5.01, 9.9, 14.0, 20.0, 20.5]))
    assert list(lab) == ["<=5", "<=5", "<=7.5", "<=10", "<=15", "<=20", ">20 (cap)"]
    s = tb.ring_shares(np.array([1.0, 6.0, 30.0, 30.0]))
    assert s["<=5"] == 0.25 and s["<=7.5"] == 0.25 and s[">20 (cap)"] == 0.5
    assert abs(sum(s.values()) - 1.0) < 1e-12


def test_knn_distances_miles_and_short_pool():
    pool = np.array([[i * 5280.0, 0.0] for i in range(1, 11)])  # 1..10 mi east
    d1, d10 = tb.knn_distances_mi(np.array([[0.0, 0.0]]), pool)
    assert np.isclose(d1[0], 1.0) and np.isclose(d10[0], 10.0)
    d1, d10 = tb.knn_distances_mi(np.array([[0.0, 0.0]]), pool[:3])
    assert np.isclose(d1[0], 1.0) and np.isnan(d10[0])
    d1, d10 = tb.knn_distances_mi(np.array([[0.0, 0.0]]), pool[:1])
    assert np.isclose(d1[0], 1.0) and np.isnan(d10[0])


def test_package_counts_any_member_reached():
    s = pd.DataFrame({"package": ["a", "a", "b", "c"], "held_out": [False, False, False, True],
                      "reached_12": [True, False, True, True], "reached_24": [False, False, True, False]})
    pc = tb.package_counts(s, (12, 24)).set_index("horizon")
    assert pc.loc[12, "n_tuning"] == 2 and pc.loc[12, "n_holdout"] == 1 and pc.loc[12, "n_wells_tuning"] == 2
    assert pc.loc[24, "n_tuning"] == 1 and pc.loc[24, "n_holdout"] == 0


def _counts(tuning, holdout, horizon=12):
    cut = [f"{y}-12-01" for y in range(2019, 2019 + len(tuning))]
    return pd.DataFrame({"cutoff": cut, "horizon": horizon, "n_tuning": tuning, "n_holdout": holdout})


def test_judgeability_walk_forward_needs_two_earlier_judged_cutoffs():
    # BS2_S-like: every tuning cell judged -> wf from the 3rd cutoff
    j = tb.judgeability(_counts([40, 60, 97, 104, 114, 82], [10, 15, 25, 25, 25, 20])).iloc[0]
    assert j["d53_cells"] == 6 and j["wf_cutoffs"] == 4
    assert j["pooled_holdout_wf"] == 95 and j["pooled_holdout_raw"] == 120 and j["d99_wf"] and j["d99_raw"]
    assert j["d102_cutoffs"] == 6
    # thin: only one judged cutoff -> no walk-forward haircut anywhere
    j = tb.judgeability(_counts([12, 18, 31, 25, 22, 15], [3, 5, 8, 6, 7, 4])).iloc[0]
    assert j["d53_cells"] == 1 and j["wf_cutoffs"] == 0 and j["pooled_holdout_wf"] == 0 and not j["d99_wf"]
    assert j["pooled_holdout_raw"] == 33 and j["d99_raw"] and j["d102_cutoffs"] == 2


def test_verdict_class():
    good = pd.concat([_counts([40, 60, 97, 104, 114, 82], [10, 15, 25, 25, 25, 20], h) for h in (12, 24)])
    assert tb.verdict_class(tb.judgeability(good)).startswith("judgeable as BS2_S")
    thin = pd.concat([_counts([12, 18, 31, 25, 22, 15], [3, 5, 8, 6, 7, 4], 12), _counts([12, 18, 20, 0, 0, 0], [3, 5, 8, 0, 0, 0], 24)])
    assert tb.verdict_class(tb.judgeability(thin)).startswith("cum-12 only")
    none = pd.concat([_counts([2, 3, 4, 5, 6, 7], [0, 1, 0, 1, 0, 1], h) for h in (12, 24)])
    assert tb.verdict_class(tb.judgeability(none)) == "not judgeable under any rule of record"


def test_unscored_early_cells_zeroed():
    c = pd.concat([_counts([40, 60, 97], [10, 15, 25], 36), _counts([40, 60, 97], [10, 15, 25], 48)])
    j = tb.judgeability(c).set_index("horizon")
    assert j.loc[36, "pooled_tuning"] == 157 and j.loc[48, "pooled_tuning"] == 97
    assert j.loc[36, "wf_cutoffs"] == 0  # only 2020 + 2021 judged at cum-36 -> no third cutoff
