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


def test_wcb_split_cut_and_boundary():
    from box import wcb_split as ws

    rng = np.random.default_rng(3)
    rows = []
    for lon in (-102.0, -101.85):
        for lat in np.arange(31.2, 32.4, 0.01):
            for k in range(3):
                south = lat < 31.7
                bench = "WCB_2" if (south and k == 0) else "WCB_1"
                below = (520.0 if bench == "WCB_2" else 260.0) + rng.normal(0, 30)
                rows.append({"api10": f"{lon}{lat}{k}", "mid_lon": lon + 0.01, "mid_lat": lat, "box_bench": bench, "below_wca1": below})
    w = pd.DataFrame(rows)
    cut = ws.deep_cut(w)
    assert abs(cut["cut_ft"] - 390) < 15
    w["deep"] = w["below_wca1"] >= cut["cut_ft"]
    b = ws.boundary(w)
    assert len(b) == 2 and (b["boundary_lat"].between(31.65, 31.75)).all() and (b["deep_north"] == 0).all()
    ln = ws.line(b)
    assert ln[0][0] == -103.0 and ln[-1][0] == -100.5 and len(ln) == 4
    d = ws.landing_depth(pd.DataFrame({"tvd_ft": [8000.0, 8000.0], "cons_bands": [{"WCA_1": 7700.0}, None]}))
    assert d.iloc[0] == 300.0 and np.isnan(d.iloc[1])


def test_midland_ledger_swaps_in_its_carded_classes_only():
    from box import qc_rule as qr

    acc, rej = qr.ledger("midland")
    assert acc["WCA->WCB_1"] == 0.70 and "WCA->WCB_1" not in rej  # Delaware 0.40 rejected; Midland cards 7/10 = the gate
    assert rej["WCB_1->WCA"] == 0.50 and "WCB_1->WCA" not in acc  # Delaware 0.70 accepted; Midland cards 5/10
    assert acc["WCB_2->WCB_1"] == 1.00 and acc["WCB_2->WCC"] == 0.70 and acc["WCC->WCB_2"] == 0.70
    assert acc["WCC->WCA"] == qr.ACCEPTED_CLASSES["WCC->WCA"]  # uncarded classes keep the Delaware ledger
    d_acc, d_rej = qr.ledger(None)
    assert d_acc == qr.ACCEPTED_CLASSES and d_rej == qr.REJECTED_CLASSES
    row = pd.Series({"api10": "1", "formation_blueox": "WCA_1", "cons_status": "flag", "cons_suggest": "WCB_1", "sql23_nearest": "WCB_1",
                     "cons_gor_vote": "none", "cons_witness": True, "planned": False})
    assert qr.decide(row)[1] == "keep" and qr.decide(row, basin="midland")[:2] == ("WCB_1", "reassign")


def test_d136_reassigns_only_north_wcb2_at_wcb1_depth():
    from box import wcb_split as ws

    def r(api, tag, bench, lat, below):
        return {"api10": api, "formation_blueox": tag, "box_bench": bench, "box_action": "keep", "box_reason": "", "mid_lon": -102.0,
                "mid_lat": lat, "tvd_ft": 8000.0, "cons_bands": None if below is None else {"WCA_1": 8000.0 - below}}
    d = pd.DataFrame([
        r("1", "WCB_2", "WCB_2", 32.2, 250.0),   # north, WCB_1 depth -> WCB_1
        r("2", "WCB_2", "WCB_2", 32.2, 500.0),   # north, WCB_2 depth -> kept
        r("3", "WCB_2", "WCB_2", 32.2, None),    # north, no WCA_1 band -> kept (not measurable)
        r("4", "WCB_2", "WCB_2", 31.4, 250.0),   # south of the line -> kept
        r("5", "WCB_1", "WCB_1", 32.2, 250.0),   # not WCB_2-tagged
        r("6", "WCB_2", "WCC", 32.2, 250.0),     # already moved by the class rule
    ])
    o = ws.apply_d136(d).set_index("api10")
    assert o["box_bench"].to_dict() == {"1": "WCB_1", "2": "WCB_2", "3": "WCB_2", "4": "WCB_2", "5": "WCB_1", "6": "WCC"}
    assert o.at["1", "box_action"] == "reassign" and o.at["1", "box_reason"].startswith("D136")


def test_d136_clip_stops_wcb2_at_the_line():
    from box import edge_gap as eg
    from box import extent as ex
    from box import wcb_split as ws

    gen = ex.as_multi(eg.to_ft([Polygon([(-102.1, 31.4), (-101.9, 31.4), (-101.9, 32.2), (-102.1, 32.2)])])[0])
    b = {"extent": gen, "stats": {"extent_sqmi": gen.area / eg.FT_PER_MI**2, "n_parts": 1}}
    ws.clip_d136(b)
    assert b["stats"]["d136_unclipped_sqmi"] > b["stats"]["extent_sqmi"] > 0
    lat_max = eg.to_lonlat([b["extent"]])[0].bounds[3]
    assert lat_max < 31.86  # the line crosses -102.1..-101.9 between 31.70 and 31.85


def test_owner_assignment_outranks_the_rule_and_joins_the_family():
    from box import qc_rule as qr

    d = _ruled([["1", "OTHER", "OTHER", "off_band", None, "keep", False], ["2", "WCC", "WCC", "agree", None, "keep", True]])
    d["box_reason"] = ""
    o = qr.apply_owner(d, {"1": "WCD"})
    assert o.set_index("api10")["box_bench"].to_dict() == {"1": "WCD", "2": "WCC"}
    r = fq.family_membership(o, MID, frozen={}, seen_ids=set(), excluded_ids=set()).set_index("api10")
    assert r.at["1", "family_role"] == "member" and r.at["1", "family_bench"] == "WCD"


def test_fe_contrast_equals_explicit_block_dummies():
    # within-block demeaning (Frisch-Waugh) must give the dummy-per-block OLS coefficient exactly
    rng = np.random.default_rng(7)
    n = 300
    block = rng.integers(0, 12, n).astype(str)
    year = rng.integers(2016, 2024, n)
    is_b = rng.integers(0, 2, n)
    y = rng.normal(0, 1, n) + 0.25 * is_b + block.astype(int) * 0.1 + (year - 2016) * 0.03
    X = pd.get_dummies(pd.DataFrame({"blk": block, "yr": year.astype(str)}), dtype=float)
    X = X.drop(columns=[c for c in X.columns if c.startswith("yr_")][:1])
    X["is_b"] = is_b.astype(float)
    ref = np.linalg.lstsq(X.values, y, rcond=None)[0][-1]
    assert abs(fq.fe_contrast(y, is_b, block, year) - ref) < 1e-10


# --- tag screen (box/tag_screen.py) -------------------------------------------------------------------------------


def _screen_frame(rows):
    cols = ["api10", "formation_blueox", "cons_status", "cons_suggest", "sql23_nearest", "cons_gor_vote", "cons_own_delta",
            "cons_nearest_delta", "cohort", "tag_source", "novi_formation", "novi_code", "env_code"]
    d = pd.DataFrame(rows, columns=cols)
    lab = d[["api10", "tag_source", "novi_formation", "novi_code", "env_code"]]
    return d.drop(columns=["tag_source", "novi_formation", "novi_code", "env_code"]), lab


def test_tag_screen_novi_coarse_list_matches_sql16():
    from pathlib import Path

    from box import tag_screen as ts

    sql = Path("sql/16_formation_blueox.sql").read_text(encoding="utf-8")
    block = sql[sql.index("(w.formation IN ("):sql.index("AS is_trigger")]
    import re

    assert set(re.findall(r"'([^']+)'", block)) == ts.NOVI_COARSE


def test_tag_screen_rules():
    from box import tag_screen as ts

    s, lab = _screen_frame([
        # A: depth flag + sql/23 agrees
        ["1", "WCC", "flag", "WCB_2", "WCB_2", "none", 200.0, 30.0, True, "novi", "WOLFCAMP C", "WCC", "WCC"],
        # depth flag but no independent vote: not flagged
        ["2", "WCC", "flag", "WCB_2", "WCC", "own", 200.0, 30.0, True, "novi", "WOLFCAMP C", "WCC", "WCC"],
        # B: vendors disagree, off band
        ["3", "WCC", "off_band", None, None, "none", np.nan, 300.0, True, "novi", "WOLFCAMP C", "WCC", "WCD"],
        # vendors disagree but the well sits in its own band: counted, not flagged
        ["4", "WCC", "agree", None, None, "none", 10.0, 10.0, True, "novi", "WOLFCAMP C", "WCC", "WCB_2"],
        # coarse Novi value is no vote: an Enverus-sourced tag with Novi 'WOLFCAMP B' has no second label
        ["5", "WCB_1", "off_band", None, None, "none", np.nan, 300.0, True, "enverus", "WOLFCAMP B", "WCB_1", "WCB_1"],
    ])
    d = ts.screen(s, lab).set_index("api10")
    assert d.loc["1", "screen_class"] == "WCC->WCB_2 (A)"
    assert d.loc["2", "screen_rule"] == ""
    assert d.loc["3", "screen_class"] == "WCC->WCD (B)"
    assert d.loc["4", "screen_rule"] == "" and bool(d.loc["4", "conflict_agree"])
    assert pd.isna(d.loc["5", "other_vendor"]) and d.loc["5", "screen_rule"] == ""


def test_tag_screen_sequential_decision():
    from box import tag_screen as ts

    assert ts.decide(5, 5, 40) == "accept"
    assert ts.decide(1, 5, 40) == "reject"  # 1 + 5 more < 7
    assert ts.decide(2, 5, 40) == "round 2"
    assert ts.decide(7, 10, 40) == "accept"
    assert ts.decide(6, 10, 40) == "reject"
    assert ts.decide(3, 4, 4) == "accept"  # carded in full: precision 0.75
    assert ts.decide(0, 0, 40) == "pending"


def test_tag_screen_card_target():
    from box import tag_screen as ts

    assert ts.card_target("full review", 18) == 18  # every flagged well, whatever the sample said
    assert [ts.card_target(s, 40) for s in ("accept", "reject", "parked")] == [0, 0, 0]
    assert ts.card_target("round 2", 40) == ts.CARDS_PER_CLASS
    assert ts.card_target("pending", 40) == ts.ROUND1


def test_tag_screen_whatif_coarse_is_not_in_sql16():
    """The Midland WOLFCAMP C trigger was dropped (FINDINGS §8.7): the live screen assumes sql/16 has no basin trigger."""
    from pathlib import Path

    from box import tag_screen as ts

    sql = Path("sql/16_formation_blueox.sql").read_text(encoding="utf-8")
    assert "defer_to_enverus" not in sql and "trig AS (" not in sql
    trigger_list = sql[sql.index("(w.formation IN ("):sql.index("AS is_trigger")]
    for values in ts.NOVI_COARSE_BY_BASIN.values():
        for v in values:
            assert f"'{v}'" not in trigger_list


def test_tag_screen_whatif_retag():
    from box import tag_screen as ts

    prod = pd.DataFrame({"api10": ["1", "2", "3", "4", "5"], "formation_blueox": ["WCC", "WCC", "WCC", "WCC", "WCB_1"],
                         "formation_blueox_tvd_corrected": [False, False, True, False, False]})
    lab = pd.DataFrame({"api10": ["1", "2", "3", "4", "5"],
                        "novi_formation": ["WOLFCAMP C", "WOLFCAMP C", "WOLFCAMP C", "WOLFCAMP C", "WOLFCAMP B"],
                        "env_interval": ["WOLFCAMP B LOWER", None, "WOLFCAMP B LOWER", "WOLFCAMP C AND ABOVE", "WOLFCAMP B UPPER"],
                        "tag_source": ["novi", "novi", "novi", "novi", "enverus"], "env_code": ["WCB_2", None, "WCB_2", "OTHER", "WCB_1"]})
    p, lb = ts.whatif_retag(prod, lab, "midland")
    p = p.set_index("api10")
    assert p.loc["1", "formation_blueox"] == "WCB_2" and p.loc["1", "whatif_changed"]
    assert p.loc["2", "formation_blueox"] == "WCC"  # no Enverus value: sql/16 falls back to Novi
    assert p.loc["3", "formation_blueox"] == "WCC"  # sql/23-corrected row kept (not re-simulated)
    assert p.loc["4", "formation_blueox"] == "OTHER"
    assert lb.set_index("api10").loc["1", "tag_source"] == "enverus"
    q, _ = ts.whatif_retag(prod, lab, "delaware")
    assert (q["formation_blueox"] == prod["formation_blueox"]).all()


def test_tag_screen_clear_verdict():
    from box import tag_screen as ts

    assert ts.clear_verdict("agree") == "agree"
    assert ts.clear_verdict("reject. Canyon sands, out of scope") == "reject"
    assert ts.clear_verdict("WCD", "WCB_1") == "reject" and ts.clear_verdict("WCD", "WCD") == "agree"
    assert ts.clear_verdict("bad tvd") == "" and ts.clear_verdict("Lets discuss") == "" and ts.clear_verdict(np.nan) == ""
    known = {"WCB_2", "WCC", "OTHER"}
    assert ts.unknown_bench_codes(["WCC", "WCB2", "agree", "reject", "bad tvd", np.nan, "OTHER", "WCB2"], known) == ["WCB2"]


def test_tag_screen_parked_names_are_class_names():
    """A typo in a parked class name parks nothing, silently: pin the 'FROM->TO (A|B)' shape and real bench codes."""
    import re

    from box import tag_screen as ts
    codes = {"WCA_1", "WCB_1", "WCB_2", "WCC", "WCD", "DEAN", "LSSH", "MS", "OTHER", "(unmapped)"}
    for basin, parked in ts.PARKED.items():
        assert basin in ("midland", "delaware")
        for name, why in parked.items():
            m = re.fullmatch(r"(\S+)->(\S+) \(([AB])\)", name)
            assert m and m[1] in codes and m[2] in codes, name
            assert why.startswith("parked 20")


def test_wc_rule_depth_call():
    """Local jury band first; the WCA_1 ladder only where the new tag has no local band; the Novi-WC rung = WC slot."""
    from scripts.box_wc_rule_depth_check import depth_call

    rung = {"WCA_1": 0.0, "WCB_1": 259.0, "WCB_2": 457.0, "WCD": 1429.0, "WC slot": 768.0}

    def r(verdict, new, off_new, off_wca1):
        return pd.Series({"verdict": verdict, "new_tag": new, "off_new_ft": off_new, "off_wca1_ft": off_wca1})

    assert depth_call(r("new", "WCB_2", 10.0, 470.0), rung) == ("new tag (local band)", "WCB_2")
    assert depth_call(r("off band", "WCB_2", np.nan, 450.0), rung) == ("new tag (WCA_1 ladder)", "WCB_2")
    assert depth_call(r("off band", "WCB_2", 250.0, 760.0), rung) == ("WC slot (stays WCC)", "WC slot")
    assert depth_call(r("off band", "WCD", -650.0, 790.0), rung) == ("WC slot (stays WCC)", "WC slot")
    assert depth_call(r("off band", "WCB_2", 300.0, 470.0), rung) == ("contradicted locally, ladder says new", "WCB_2")
    assert depth_call(r("off band", "WCB_2", 300.0, np.nan), rung) == ("not the new tag (local band)", None)
    assert depth_call(r("off band", "WCB_2", np.nan, np.nan), rung) == ("undecided", None)
    assert depth_call(r("no jury", "OTHER", np.nan, np.nan), rung) == ("undecided", None)
    assert depth_call(r("off band", "WCB_1", np.nan, 440.0), rung) == ("other rung", "WCB_2")


def test_tag_screen_reuse_verdict():
    """A card counts only for its own move; a bench-code verdict is a well call that answers any move."""
    from box import tag_screen as ts

    known = {"WCB_1", "WCB_2", "WCC", "WCD"}
    assert ts.reuse_verdict("agree", "WCB_2", "WCB_2", known) == "agree"
    assert ts.reuse_verdict("agree", "WCB_2", "WCB_1", known) == ""  # drawn for another move
    assert ts.reuse_verdict("reject", "WCC", "WCB_2", known) == ""
    assert ts.reuse_verdict("WCC", "WCC", "WCB_2", known) == "reject"  # Sequitur: the well is WCC, whatever is proposed
    assert ts.reuse_verdict("WCD", "WCB_1", "WCD", known) == "agree"
    assert ts.reuse_verdict("agree", "WCB_2", None, known) == ""  # not flagged now
    assert ts.reuse_verdict("bad tvd", "WCB_2", "WCB_2", known) == ""


def test_tag_screen_override_seed():
    import pandas as pd

    from box import tag_screen as ts

    flags = pd.DataFrame({"api10": list("abcdefg"), "screen_class": ["X (A)"] * 4 + ["Y (B)"] * 3,
                          "screen_dest": ["WCB_1"] * 4 + ["WCD"] * 3, "formation_blueox": ["WCA_1"] * 4 + ["WCC"] * 3})
    cards = flags[flags["api10"].isin(list("abef"))].assign(verdict=["agree", "reject", "WCB_2", "hold: thin"],
                                                            verdict_source="round 1")
    calls = pd.DataFrame({"api10": ["z", "a"], "live_tag": ["WCC", "WCA_1"], "call": ["WCB_1", "WCB_1"],
                          "source": ["Michael in chat", "Michael in chat"], "date": ["2026-10-27"] * 2, "note": ["depth", "same"]})
    states = {"X (A)": {"state_before": "accept", "prior_agree": 1, "prior_judged": 2},
              "Y (B)": {"state_before": "reject", "prior_agree": 0, "prior_judged": 2}}
    s = ts.override_seed(flags, cards, calls, states, {"round 1": "2026-10-27"}, "2026-10-28").set_index("api10")
    # a: carded agree; b: own reject never moved by its accepted class; c, d: uncarded in an accepted class
    # e: own-bench call in a rejected class lands; f: hold; g: uncarded in a rejected class; z: chat call
    assert sorted(s.index) == ["a", "c", "d", "e", "z"]
    assert s.loc["c", "note"].startswith("class-accepted X (A) 1/2 cards 2026-10-28")
    assert s.loc["a", "note"].startswith("carded 2026-10-27") and s.loc["e", "corrected_code"] == "WCB_2"
    assert all(n.endswith(ts.SEED_TAG) for n in s["note"])
    # an inspection call replaces a class-accepted row, even with a different bench
    c2 = pd.concat([calls, pd.DataFrame({"api10": ["c"], "live_tag": ["WCA_1"], "call": ["WCB_2"],
                                         "source": ["Michael in anduin"], "date": ["2026-10-29"], "note": ["looked"]})])
    s2 = ts.override_seed(flags, cards, c2, states, {"round 1": "2026-10-27"}, "2026-10-28").set_index("api10")
    assert s2.loc["c", "corrected_code"] == "WCB_2" and s2.loc["c", "note"].startswith("Michael in anduin 2026-10-29")
    calls.loc[1, "call"] = "WCB_2"
    import pytest

    with pytest.raises(ValueError):  # a card and a chat call that disagree never land silently
        ts.override_seed(flags, cards, calls, states, {"round 1": "2026-10-27"}, "2026-10-28")


def test_seed_20a_block_matches_the_screen():
    """The committed seed's 20a block is exactly what the finished screen builds (re-run box_tag_seed --write if not)."""
    import csv

    from box import tag_screen as ts
    from scripts.box_tag_seed import SEED, build

    with open(SEED, encoding="utf-8") as fh:
        block = [r for r in csv.DictReader(fh) if ts.SEED_TAG in r["note"]]
    new = build(SEED.parent.parent / "docs/box/step20a-2026-10-26/tag_screen", "2026-10-28")
    assert [tuple(r.values()) for r in block] == list(new.itertuples(index=False, name=None))
