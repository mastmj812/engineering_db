"""The thickness rung's anchor rule: first-in-order (of record) and the median of every eligible anchor (built, not adopted)."""

import numpy as np

from box import landing_surfaces as ls
from scripts import box_sticks_phase1c as p1c

MI = ls.M_PER_MI


def _case():
    # four own wells 2 mi out on every side (too far for a direct depth), all at 1,000 ft
    cxy = np.array([[2 * MI, 0.0], [-2 * MI, 0.0], [0.0, 2 * MI], [0.0, -2 * MI]])
    cz = np.full(4, 1000.0)
    pts = np.array([[0.0, 0.0]])
    # anchor surface at the own wells / at the point: each anchor gives a different carried depth
    Fc = {"A": np.full(4, 900.0), "B": np.full(4, 500.0), "C": np.full(4, 1200.0)}
    Fp = {"A": np.array([910.0]), "B": np.array([560.0]), "C": np.array([1230.0])}   # -> 1,010 / 1,060 / 1,030 ft
    rank = [("B", 40.0, 120.0), ("A", 41.0, 121.0), ("C", 42.0, 122.0)]
    return pts, cxy, cz, Fc, Fp, rank


def test_rank_rule_takes_the_first_anchor_in_order():
    pts, cxy, cz, Fc, Fp, rank = _case()
    r = p1c.chain_for_code(False, pts, cxy, cz, Fc, Fp, rank, []).iloc[0]
    assert (r["rung"], r["how"], r["z"], r["expected_median_ft"]) == ("thickness", "B", 1060.0, 40.0)


def test_median_rule_does_not_depend_on_the_order():
    pts, cxy, cz, Fc, Fp, rank = _case()
    for order in (rank, rank[::-1]):
        r = p1c.chain_for_code(False, pts, cxy, cz, Fc, Fp, order, [], (33.0, 99.0)).iloc[0]
        assert (r["rung"], r["z"], r["expected_median_ft"], r["expected_p90_ft"]) == ("thickness", 1030.0, 33.0, 99.0)
        assert sorted(r["how"].split("+")) == ["A", "B", "C"]


def test_median_rule_with_one_anchor_is_that_anchor():
    pts, cxy, cz, Fc, Fp, rank = _case()
    Fp = Fp | {"A": np.array([np.nan]), "C": np.array([np.nan])}
    r = p1c.chain_for_code(False, pts, cxy, cz, Fc, Fp, rank, [], (33.0, 99.0)).iloc[0]
    assert (r["how"], r["z"]) == ("B", 1060.0)


def test_expected_error_table_covers_the_chain_benches():
    exp = p1c.thick_expected("median")
    assert ("midland", "WCD") in exp and all(0 < m < p for m, p in exp.values())
    assert p1c.THICK_RULE == "rank" and p1c.thick_expected() == {}   # the rule of record until Michael decides
