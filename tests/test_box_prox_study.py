"""DB-free tests for the PDP-proximity study geometry + atlas (box/prox_study.py)."""

from __future__ import annotations

import datetime as dt
import json
import math
from pathlib import Path

import pandas as pd
import pytest
from shapely import wkt
from shapely.geometry import LineString, MultiLineString, shape

from box import edge_gap as eg
from box import prox_study as ps

D0 = dt.date(2020, 1, 1)
CHILD = LineString([(0, 0), (0, 10000)])


def _w(api10, x, y0, y1, tvd, bench="WCA_1", fp=dt.date(2018, 1, 1)):
    return {"api10": api10, "bench": bench, "fp": fp, "tvd_ft": tvd, "geom": LineString([(x, y0), (x, y1)])}


def test_pair_overlap_is_share_of_child_and_gap_is_median() -> None:
    ov, dh = ps.pair(CHILD, LineString([(500, -2000), (500, 12000)]))
    assert ov == pytest.approx(1.0) and dh == pytest.approx(500)
    ov, dh = ps.pair(CHILD, LineString([(700, 5000), (700, 20000)]))
    assert ov == pytest.approx(0.5) and dh == pytest.approx(700)
    # skewed parent: median of the sampled gaps, not the closest approach
    ov, dh = ps.pair(CHILD, LineString([(200, 0), (1200, 10000)]))
    assert ov == pytest.approx(1.0) and dh == pytest.approx(700 * math.cos(math.atan(0.1)), abs=1)  # point-to-line, skew 5.7 deg
    # past the end of the child shares nothing
    assert ps.pair(CHILD, LineString([(100, 10500), (100, 15000)])) == (0.0, None)
    # multipart parent spans by all of its coordinates
    ov, _ = ps.pair(CHILD, MultiLineString([[(300, 1000), (300, 3000)], [(300, 3000), (300, 6000)]]))
    assert ov == pytest.approx(0.5)


def test_relation_windows_and_pool_classes() -> None:
    assert [ps.relation(a) for a in (-181, -180, 180, 181, 364, 365)] == ["child", "codev", "codev", "young", "young", "parent"]
    assert ps.pair_class("WCXY", "WCA_1", 120.0) == "same"            # D42 pool
    assert ps.pair_class("BS3_S", "WCA_1", 300.0) == "topfill"         # parent deeper
    assert ps.pair_class("WCB_2", "WCA_1", -500.0) == "underfill"


def test_links_skip_children_far_vertical_and_low_overlap() -> None:
    child = {"api10": "C", "bench": "BS3_S", "fp": D0, "tvd_ft": 9850.0, "geom": CHILD}
    cands = [
        _w("P", 400, 0, 10000, 10120),                                # WCA parent 270 ft below, 2 yr older
        _w("K", 600, 0, 10000, 10100, fp=dt.date(2021, 6, 1)),         # younger than the child -> its child, skipped
        _w("F", 300, 0, 10000, 11500),                                 # 1,650 ft below -> not stored
        _w("S", 300, 0, 2000, 10100),                                  # 20 % alongside -> below the overlap floor
    ]
    (k,) = ps.links_for_child(child, cands)
    assert (k.parent, k.cls, k.rel, k.dz_ft, k.dh_ft, k.permit, k.shielded) == ("P", "topfill", "parent", 270.0, 400.0, False, False)
    assert k.age_days == (D0 - dt.date(2018, 1, 1)).days


def test_shielding_needs_a_codev_other_pool_well_in_between() -> None:
    child = {"api10": "C", "bench": "BS3_S", "fp": D0, "tvd_ft": 9850.0, "geom": CHILD}
    parent = _w("P", 400, 0, 10000, 10250)
    between = _w("B", 100, 0, 10000, 10050, bench="BS3_C", fp=D0)      # co-developed, 200 ft below the child
    beyond = _w("X", 100, 0, 10000, 10400, bench="WCB_1", fp=D0)       # co-developed but deeper than the parent
    got = {k.parent: k for k in ps.links_for_child(child, [parent, between])}
    assert got["P"].shielded and got["B"].rel == "codev"
    assert not {k.parent: k for k in ps.links_for_child(child, [parent, beyond])}["P"].shielded


def test_permit_round_tvd_is_flagged() -> None:
    child = {"api10": "C", "bench": "BS3_S", "fp": D0, "tvd_ft": 9850.0, "geom": CHILD}
    (k,) = ps.links_for_child(child, [_w("P", 400, 0, 10000, 10100)])
    assert k.permit


def _links(rows):
    cols = ["child", "parent", "child_bench", "parent_bench", "cls", "rel", "age_days", "dz_ft", "dv_ft", "dh_ft", "overlap", "permit", "shielded"]
    return pd.DataFrame([dict(zip(cols, r)) for r in rows])


def test_grid_is_cumulative_one_count_per_child() -> None:
    L = _links([
        ("a", "p1", "BS3_S", "WCA_1", "topfill", "parent", 900, 250, 250, 500, 0.9, False, False),
        ("a", "p2", "BS3_S", "WCA_1", "topfill", "parent", 900, 150, 150, 300, 0.9, False, False),   # same child twice
        ("b", "p3", "BS3_S", "WCA_1", "topfill", "parent", 900, 550, 550, 1300, 0.9, False, False),
        ("c", "p4", "BS3_S", "WCA_1", "topfill", "codev", 30, 200, 200, 300, 0.9, False, False),      # codev: never counts
        ("d", "p5", "BS3_S", "WCA_1", "topfill", "parent", 900, 200, 200, 300, 0.9, True, False),     # permit TVD: dropped
        ("e", "p6", "BS3_S", "WCA_1", "topfill", "parent", 900, 200, 200, 300, 0.9, False, True),     # shielded: dropped
    ])
    g = ps.grid(L, z_grid=(200, 300, 600), x_grid=(400, 800, 1400))
    assert g.loc[200].tolist() == [1, 1, 1] and g.loc[300].tolist() == [1, 1, 1] and g.loc[600].tolist() == [1, 1, 2]
    assert ps.exposed(L, 300, 800) == {"a"}
    assert ps.exposed(L, 300, 800, drop_permit=False, drop_shielded=False) == {"a", "d", "e"}
    sh = ps.share_table(pd.DataFrame({"api10": ["a", "b", "z"], "bench": ["BS3_S"] * 3}), L)
    assert sh.loc[0, ["n_children", "n_topfill", "n_any"]].tolist() == [3, 1, 1]


def test_uptake_counts_parents_with_opportunity_only() -> None:
    L = _links([("a", "p1", "BS3_S", "WCA_1", "topfill", "parent", 900, 250, 250, 500, 0.9, False, False)])
    opp = {("WCA_1", "BS3_S"): {f"p{i}" for i in range(1, 41)}, ("WCA_1", "WCB_1"): {"p1"}}
    u = ps.uptake(pd.DataFrame(), L, opp)
    assert len(u) == 1 and u.loc[0, ["n_opportunity", "n_infilled"]].tolist() == [40, 1] and not u.loc[0, "same_pool"]


# ----------------------------------------------------------------------------
# One definition: the basin metric reproduces deal-intake's v14 rule on the Chevron acceptance fixture
# ----------------------------------------------------------------------------

FIXTURE = Path(__file__).resolve().parent / "fixtures" / "dealintake_chevron_proximity.json"


def test_matches_dealintake_rule_on_chevron_fixture() -> None:
    from dealintake import config as cfgmod
    from dealintake.proximity import ProximityRule

    px = cfgmod.load().raw["pdp_proximity"]
    v_ft, h_ft, frac = float(px["vertical_ft"]), float(px["horizontal_ft"]), float(px["overlap_min_frac"])
    units = json.loads(FIXTURE.read_text(encoding="utf-8"))["units"]
    n_checked = n_hits = 0
    for u in units.values():
        unit = shape(u["geometry"])
        rule = ProximityRule(unit, u["azimuth_deg"], u["pdp"], px)
        pdp = [w for w in u["pdp"] if w.get("tvd_ft") is not None]
        pdp_ft = eg.to_ft([wkt.loads(w["wkt"]) for w in pdp])
        for spacing in u["legs"].values():
            for bench, legs in spacing.items():
                tvd = u["tvd_ft"][bench]
                for leg in legs:
                    g = wkt.loads(leg["wkt"])
                    r = rule.check(g, tvd)
                    theirs = {h["api10"]: h for h in r["cull"] + r["permit"]}
                    (g_ft,) = eg.to_ft([g])
                    mine = {}
                    for w, wf in zip(pdp, pdp_ft):
                        ov, dh = ps.pair(g_ft, wf)
                        if ov >= frac and dh is not None and dh <= h_ft and abs(float(w["tvd_ft"]) - tvd) <= v_ft:
                            mine[w["api10"]] = (ov, dh)
                    assert set(mine) == set(theirs), (bench, leg["wkt"][:40])
                    for a, (ov, dh) in mine.items():
                        assert dh == pytest.approx(theirs[a]["dh_ft"], abs=15) and ov == pytest.approx(theirs[a]["overlap"], abs=0.03)
                    n_checked += 1
                    n_hits += len(mine)
    assert n_checked > 50 and n_hits > 0


def test_signed_offset_gives_the_side() -> None:
    _, dh, s = ps.pair_signed(CHILD, LineString([(-600, 0), (-600, 10000)]))   # child heads north: west = left = +
    assert dh == pytest.approx(600) and s == pytest.approx(600)
    _, _, s = ps.pair_signed(CHILD, LineString([(450, 0), (450, 10000)]))
    assert s == pytest.approx(-450)
    child = {"api10": "C", "bench": "BS3_S", "fp": D0, "tvd_ft": 9850.0, "geom": CHILD}
    (k,) = ps.links_for_child(child, [_w("P", 400, 0, 10000, 10120)])
    assert k.dxy_ft == pytest.approx(-400) and k.dh_ft == pytest.approx(400)
