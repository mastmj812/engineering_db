"""DB-free tests for BOX step 20a (Midland Wolfcamp): pooled-label family membership, the multi-bench pooling contrast,
the Delaware-analogue swap-class test (box/swap_compare.py), the allocation screen (box/alloc_screen.py) and the D117
undrilled count (box/extent_report.undrilled_counts)."""

from __future__ import annotations

import datetime as dt
import math

import numpy as np
import pandas as pd
from shapely.geometry import LineString, Polygon

from box import alloc_screen as al
from box import extent_report as er
from box import family_qc as fq
from box import swap_compare as sc

MID = fq.FAMILIES["MID_WC"]


def _ruled(rows):
    cols = ["api10", "formation_blueox", "box_bench", "cons_status", "cons_suggest", "box_action", "cohort"]
    return pd.DataFrame(rows, columns=cols)


def test_midland_family_maps_the_wca_pool_label_back_to_wca_1():
    # the class rule writes the POOLED label (WCA_1 -> WCA); the Midland family counts it for WCA_1
    d = _ruled([
        ["1", "WCA_1", "WCA", "agree", None, "keep", True],
        ["2", "WCB_1", "WCA", "flag", "WCA_1", "reassign", True],   # accepted class WCB_1->WCA, applied
        ["3", "WCA_1", "WCA", "flag", "WCB_1", "keep", True],       # rejected class: tag kept
        ["4", "LSSH", "LSSH", "agree", None, "keep", True],         # not the family
    ])
    r = fq.family_membership(d, MID, frozen={}, seen_ids=set(), excluded_ids=set()).set_index("api10")
    assert "4" not in r.index
    assert (r["family_role"] == "member").all()
    assert r["family_bench"].tolist() == ["WCA_1", "WCA_1", "WCA_1"]


def test_delaware_family_membership_unchanged_by_label_map():
    # a Delaware family holds no WCA-pool bench: a WCA_1 well ruled to WCA is not a member of WCB
    d = _ruled([["1", "WCB_1", "WCA", "flag", "WCA_1", "reassign", True], ["2", "WCB_1", "WCB_1", "agree", None, "keep", True]])
    r = fq.family_membership(d, fq.FAMILIES["WCB"], frozen={}, seen_ids={"1"}, excluded_ids=set()).set_index("api10")
    assert r.at["1", "family_role"] == "old_churn_kept" and r.at["2", "family_role"] == "member"


def test_pooling_contrast_compares_only_the_pair():
    # three benches; c is 2x a, b = a. The b-vs-a contrast must ignore c (a 3+ bench family used to count c as `a`)
    rng = np.random.default_rng(1)
    rows, xy = [], []
    for blk in range(30):
        for bench, lvl in (("A", 1.0), ("B", 1.0), ("C", 2.0)):
            for _ in range(4):
                rows.append({"family_bench": bench, "cohort": True, "first_production_date": dt.date(2020, 1, 1),
                             "oil12_kft": lvl * math.exp(rng.normal(0, 0.02)), "gor12": 1000.0, "cum_24m_oil_bbl": 2.0, "cum_12m_oil_bbl": 1.0,
                             "tvd_ft": 9000.0, "lateral_length_ft": 10000.0, "state_code": 42})
                xy.append((blk * 30000.0 + 10.0, 10.0))
    m = pd.DataFrame(rows)
    pe = fq.pooling_evidence(m, "A", "B", np.asarray(xy))
    assert abs(pe["oil12_kft"]["ratio"] - 1.0) < 0.02
    assert pe["oil12_kft"]["n_a"] == pe["oil12_kft"]["n_b"] == 120


def _scored(rows):
    cols = ["api10", "formation_blueox", "cons_status", "cons_suggest", "sql23_nearest", "cons_gor_vote", "cons_own_delta",
            "cons_nearest_delta", "cohort", "planned"]
    return pd.DataFrame(rows, columns=cols)


def _basin(n_tag_a: int, n_flag: int, concur: float, own_delta: float) -> pd.DataFrame:
    rows = []
    for i in range(n_tag_a):
        flag = i < n_flag
        rows.append([f"a{i}", "WCB_2", "flag" if flag else "agree", "WCB_1" if flag else None,
                     "WCB_1" if flag and i < concur * n_flag else "WCB_2", "none", own_delta, 40.0, True, False])
    return _scored(rows)


def test_swap_compare_verdicts():
    fam = ("WCB_1", "WCB_2")
    dela = sc.class_signatures(_basin(1000, 40, 0.6, 270.0), fam)
    # same rate / concurrence / offset -> alike
    alike = sc.compare(sc.class_signatures(_basin(1000, 40, 0.6, 270.0), fam), dela)
    assert alike.at["WCB_2->WCB_1", "verdict"] == "alike"
    # 3x the rate -> unlike
    hi = sc.compare(sc.class_signatures(_basin(1000, 120, 0.6, 270.0), fam), dela)
    assert hi.at["WCB_2->WCB_1", "verdict"] == "unlike" and "flag rate" in hi.at["WCB_2->WCB_1", "why"]
    # concurrence +30 pts -> unlike; own-band offset 0.6x -> unlike
    assert "sql/23" in sc.compare(sc.class_signatures(_basin(1000, 40, 0.9, 270.0), fam), dela).at["WCB_2->WCB_1", "why"]
    assert "TVD" in sc.compare(sc.class_signatures(_basin(1000, 40, 0.6, 160.0), fam), dela).at["WCB_2->WCB_1", "why"]
    # too few Midland flags -> small; no Delaware analogue -> listed, not carded
    assert sc.compare(sc.class_signatures(_basin(1000, 10, 0.6, 270.0), fam), dela).at["WCB_2->WCB_1", "verdict"] == "small"
    none = sc.compare(sc.class_signatures(_basin(1000, 40, 0.6, 270.0), fam), sc.class_signatures(_basin(1000, 5, 0.6, 270.0), fam))
    assert none.at["WCB_2->WCB_1", "verdict"] == "no analogue"
    assert sc.unlike_classes(hi) == ["WCB_2->WCB_1"]


def _well(api, tag, line, tvd, fp, oil, gor):
    return {"api10": api, "well_name": api, "operator": "X", "formation_blueox": tag, "geom": LineString(line), "tvd_ft": tvd,
            "first_production_date": fp, "cum_12m_oil_bbl": oil, "gor12": gor, "has_production_sharing": False}


def test_twin_pairs_classes_and_split_signature():
    d0 = dt.date(2022, 1, 1)
    w = pd.DataFrame([
        _well("1", "WCA_1", [(0, 0), (0, 10000)], 9000, d0, 150000, 1500),   # twin of 2 with the El Campeon split
        _well("2", "WCA_1", [(20, 0), (20, 10000)], 9005, d0, 50000, 1550),
        _well("3", "WCB_1", [(5000, 0), (5000, 10000)], 9100, d0, 100000, 2000),  # stacked pair with 4 (two benches)
        _well("4", "WCA_1", [(5010, 0), (5010, 10000)], 9000, d0, 100000, 1500),
        _well("5", "WCB_1", [(9000, 0), (9000, 10000)], 9100, d0, np.nan, np.nan),  # re-drill of 6 (never 12 months)
        _well("6", "WCB_1", [(9030, 0), (9030, 9500)], 9110, dt.date(2023, 6, 1), 90000, 2000),
        _well("7", "WCB_1", [(20000, 0), (20000, 10000)], 9100, d0, 90000, 2000),    # alone
        _well("8", "WCB_1", [(20500, 0), (20500, 10000)], 9100, d0, 90000, 2000),    # 500 ft away: not a twin
    ])
    p = al.twin_pairs(w)
    got = {(a, b): c for a, b, c in zip(p["api10_a"], p["api10_b"], p["pair_class"])}
    assert got == {("1", "2"): "twin", ("3", "4"): "stacked pair", ("5", "6"): "re-drill"}
    assert p.loc[p["api10_a"] == "1", "split_signature"].item() is True
    assert al.recall(p, {"2", "9"}) == {"found": 1, "found_any_pair": 1, "split_signature": 1, "recorded": 2}


def test_undrilled_counts_d117_by_category():
    # sticks in lon/lat around (-102, 32); polygon in UTM 13N ft from the same transform
    from box import edge_gap as eg

    sticks = pd.DataFrame({
        "stick_id": [1, 2, 3, 4], "category": ["PUD", "RES", "PUD", "RES"], "formation_blueox": ["WCC"] * 4,
        "status": ["remaining_pud", None, "realized_phantom", "conflict"],
        "wkt": ["LINESTRING(-102.00 32.00, -102.00 32.02)", "LINESTRING(-102.01 32.00, -102.01 32.02)",
                "LINESTRING(-102.02 32.00, -102.02 32.02)", "LINESTRING(-102.50 32.00, -102.50 32.02)"],
    })
    poly = eg.to_ft([Polygon([(-102.03, 31.99), (-101.99, 31.99), (-101.99, 32.03), (-102.03, 32.03)])])[0]
    t = er.undrilled_counts(sticks, {"in extent": poly})
    tot = t[t["status"] == "undrilled (D117)"].iloc[0]
    assert tot["n"] == 3 and tot["in extent"] == 2  # 3 = realized_phantom out; stick 4 lies outside
    cat = t[t["status"] == "undrilled by category"].set_index("category")
    assert cat.at["PUD", "in extent"] == 1 and cat.at["RES", "in extent"] == 1 and cat.at["RES", "n"] == 2
