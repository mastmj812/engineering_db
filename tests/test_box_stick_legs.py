"""BOX sticks in the PDP-proximity step (docs/box_sticks_plan.md phase 6, decision 3), DB-free.

Pins: a U-turn stick is measured leg by leg and takes its MORE EXPOSED leg; the stored links are that leg's, one per (stick,
producer); TVD is the stick's own landing depth and a stick without one is refused (never silently unexposed); realized and
not-drillable sticks come from the nightly status; a run on Novi sticks goes through exactly the code it did.
"""
import inspect

import pandas as pd
import pytest
from shapely.geometry import LineString, MultiLineString

from box import prox_study as ps
from box import stick_legs as sl
from scripts import box_record23 as r23

LEG1 = LineString([(0, 0), (0, 8000)])                 # heel south -> toe north
LEG2 = LineString([(1200, 8000), (1200, 0)])           # the return leg, 1,200 ft east, running south
UTURN = MultiLineString([LEG1, LEG2])
PARENT = LineString([(1500, 0), (1500, 8000)])         # a producer 300 ft east of the SECOND leg, alongside all of it


def test_why_one_line_is_wrong_and_a_leg_is_right():
    """Measured on box/prox_study.pair_signed, 2026-11-23: taken as one line, a two-leg stick's gap and side come out as the
    nearer leg's, but the OVERLAP is a share of both legs, so it is halved. A producer alongside half of one leg (0.5) reads 0.25
    and falls under MIN_OVERLAP (0.30): the stick would lose a parent it has."""
    ov, dh, dxy = ps.pair_signed(LEG2, PARENT)
    assert (ov, dh, dxy) == pytest.approx((1.0, 300.0, 300.0))                 # beside the second leg, all of it, 300 ft to its left
    assert ps.pair_signed(LEG1, PARENT)[:2] == pytest.approx((1.0, 1500.0))    # the far leg: 1,500 ft away
    ov_m, dh_m, _ = ps.pair_signed(UTURN, PARENT)                              # the stick as one "line"
    assert dh_m == pytest.approx(300.0) and ov_m == pytest.approx(0.5)         # right gap, HALF the overlap
    half = LineString([(1500, 0), (1500, 4000)])                               # a producer alongside half of the second leg
    leg_ov, stick_ov = ps.pair_signed(LEG2, half)[0], ps.pair_signed(UTURN, half)[0]
    assert leg_ov == pytest.approx(0.5) and leg_ov >= ps.MIN_OVERLAP
    assert stick_ov == pytest.approx(0.25) and stick_ov < ps.MIN_OVERLAP


def _p():
    return pd.DataFrame({"location_id": [10_000_001, 10_000_002], "stick_id": [10_000_001, 10_000_002], "formation_blueox": ["WCC", "WCC"],
                         "tvd_ft": [12550.0, 12560.0], "geom": [LineString([(5000, 0), (5000, 9900)]), UTURN]})


def test_expand_is_one_row_per_leg_with_the_first_leg_keeping_the_stick_key():
    e = sl.expand(_p())
    assert list(e["location_id"]) == ["10000001", "10000002", "10000002#2"] and list(e["leg_no"]) == [1, 1, 2]
    assert list(e["stick_location_id"]) == [10_000_001, 10_000_002, 10_000_002] and list(e["stick_id"]) == [10_000_001, 10_000_002, 10_000_002]
    assert e.iloc[1]["geom"].equals(LEG1) and e.iloc[2]["geom"].equals(LEG2) and e.iloc[0]["geom"].geom_type == "LineString"
    assert list(e["tvd_ft"]) == [12550.0, 12560.0, 12560.0]
    assert sl.stick_of("10000002#2") == 10_000_002 and sl.leg_key(10_000_002, 1) == "10000002" and sl.leg_key(10_000_002, 2) == "10000002#2"
    three = _p().assign(geom=[MultiLineString([LEG1, LEG2, PARENT]), UTURN])
    with pytest.raises(SystemExit, match="has 3 legs"):
        sl.expand(three)


def test_the_stick_takes_its_more_exposed_leg():
    idx = ["10000001", "10000002", "10000002#2", "10000003", "10000003#2", "10000004", "10000004#2"]
    keep = pd.Series([True, True, True, True, False, True, True], index=idx)
    factor = pd.Series([1.046, 1.046, 0.870, 0.900, 1.046, 0.950, 0.950], index=idx)
    ch = sl.choose(keep, factor)
    assert ch == {10_000_001: "10000001",          # one leg
                  10_000_002: "10000002#2",        # the lower factor
                  10_000_003: "10000003#2",        # a leg with no forecast outranks any factor
                  10_000_004: "10000004"}          # a tie goes to the first leg
    d = pd.DataFrame({"location_id": idx, "keep": keep, "factor": factor, "outcome": ["a", "b", "c", "d", "e", "f", "g"]}, index=pd.Index(idx, name="key"))
    f = sl.fold(d, ch)
    assert list(f.index) == ["10000001", "10000002", "10000003", "10000004"] and f.index.name == "key"
    assert list(f["location_id"]) == [10_000_001, 10_000_002, 10_000_003, 10_000_004]
    assert list(f["outcome"]) == ["a", "c", "e", "f"] and list(f["factor"]) == [1.046, 0.870, 1.046, 0.950]
    assert list(f["n_legs"]) == [1, 2, 2, 2] and list(f["exposed_leg"]) == [1, 2, 2, 1] and list(f["keep"]) == [True, True, False, True]


def test_stored_links_are_the_chosen_legs_one_per_stick_and_producer():
    L = pd.DataFrame({"child": ["10000002", "10000002#2", "10000002#2", "10000001", "10000003"], "parent": ["A", "A", "B", "C", "D"], "dh_ft": [1500.0, 300.0, 600.0, 400.0, 500.0]})
    out = sl.relabel(L, {10_000_001: "10000001", 10_000_002: "10000002#2", 10_000_003: "10000003#2"})
    assert out[["child", "parent", "dh_ft"]].to_dict("records") == [{"child": "10000002", "parent": "A", "dh_ft": 300.0}, {"child": "10000002", "parent": "B", "dh_ft": 600.0},
                                                                     {"child": "10000001", "parent": "C", "dh_ft": 400.0}]
    assert not out.duplicated(["child", "parent"]).any()                 # box.pud_proximity_parent's key
    assert out["child"].astype("int64").tolist() == [10_000_002, 10_000_002, 10_000_001]     # named_parents casts the child to int
    assert len(sl.relabel(L.iloc[0:0], {})) == 0


def test_fold_legs_end_to_end_on_the_measure_frame():
    pm = sl.expand(_p())
    ids = [str(x) for x in pm["location_id"]]
    d = pm.drop(columns=["geom"]).assign(key=ids).set_index("key")
    d["keep"], d["factor"] = [True, True, True], [1.046, 1.046, 0.87]
    L = pd.DataFrame({"child": ["10000002#2"], "parent": ["3002512345"]})
    f, (L2,) = r23.fold_legs(d, L)
    assert list(f.index) == ["10000001", "10000002"] and list(f["factor"]) == [1.046, 0.87] and "leg_no" not in f and "stick_location_id" not in f
    assert L2.to_dict("records") == [{"child": "10000002", "parent": "3002512345"}]
    r = f.reset_index()
    assert list(r.columns[:2]) == ["key", "location_id"] and r["location_id"].dtype.kind == "i"       # what the outcomes CSV and the store read


def test_is_box_run_and_the_tvd_refusal():
    assert sl.is_box_run([10_000_001, 10_000_002], [10_000_001, 10_000_002]) is True
    assert sl.is_box_run([1_600_001, 1_600_002], [4, 5]) is False                                     # a Novi run: its own location ids
    with pytest.raises(SystemExit, match="mixes BOX sticks and Novi sticks"):
        sl.is_box_run([10_000_001, 1_600_002], [10_000_001, 5])
    with pytest.raises(SystemExit, match="not its location_id"):
        sl.is_box_run([10_000_001], [10_000_009])
    p = _p().drop(columns="tvd_ft")
    assert list(sl.with_stick_tvd(p, {10_000_001: 12550.0, 10_000_002: 12560.0})["tvd_ft"]) == [12550.0, 12560.0]
    with pytest.raises(SystemExit, match="1 of 2 BOX sticks have no landing TVD"):
        sl.with_stick_tvd(p, {10_000_001: 12550.0})                                                   # never silently unexposed


def test_stick_inputs_reads_box_tables_for_box_sticks_and_the_old_ones_for_novi(monkeypatch):
    import box.tc_curve_report as tcr

    calls = []

    def fake(conn, sql, params=None):
        calls.append((conn, sql))
        if sql == sl.TVD_SQL:
            return [(10_000_001, 12550.0), (10_000_002, 12560.0)]
        if sql == sl.STATUS_SQL:
            return [(10_000_001, "open"), (10_000_002, "crowded")]
        if sql == "EREBOR":
            return [(1_600_001, 11000.0, "Tier-1", "Op")]
        return [(1_600_001, "remaining_pud")]

    monkeypatch.setattr(tcr, "_read", fake)
    p, recon, box = r23.stick_inputs(_p().drop(columns=["tvd_ft", "geom"]), "BOXCONN", "LIVE", "EREBOR")
    assert box is True and list(p["tvd_ft"]) == [12550.0, 12560.0] and recon == {10_000_001: "open", 10_000_002: "crowded"}
    assert calls == [("BOXCONN", sl.TVD_SQL), ("LIVE", sl.STATUS_SQL)]                                 # box rows where the run lives; curated from live
    assert "is_record" in sl.TVD_SQL and "box.location_stick" in sl.TVD_SQL and "curated.box_location_status" in sl.STATUS_SQL
    calls.clear()
    novi = pd.DataFrame({"location_id": [4], "stick_id": [1_600_001], "formation_blueox": ["WCC"]})
    p2, recon2, box2 = r23.stick_inputs(novi, "BOXCONN", "LIVE", "EREBOR")
    assert box2 is False and list(p2["tvd_ft"]) == [11000.0] and recon2 == {1_600_001: "remaining_pud"}
    assert calls == [("LIVE", "EREBOR"), ("LIVE", r23._RECON_SQL)]                                     # exactly the two reads a Novi run always made


def test_both_measures_expand_then_fold_and_a_novi_run_takes_neither_step():
    for fn, links in ((r23.measure_delaware, "(L,)"), (r23.measure_midland_run, "(Lp, bd)")):
        src = inspect.getsource(fn)
        assert "p, recon, box_run = stick_inputs(p, box, conn, sdp._EREBOR_SQL)" in src
        assert "pm = sl.expand(p) if box_run else p" in src and f"d, {links} = fold_legs(d, " in src and "if box_run:" in src
        assert src.index("fold_legs(") < src.index('open(out / "pud_links.pkl", "wb")')              # the stored links are the folded ones
        assert src.index("pm = sl.expand(p) if box_run else p") < src.index("ppr.pud_links(")


def test_the_derived_store_takes_realized_and_not_drillable_from_the_nightly_for_a_box_run():
    src = inspect.getsource(r23.cmd_store)
    assert "FROM box.pud_forecast WHERE run_id = %s AND stick_id >= %s" in src and "q(_BOX_REAL_SQL, (S,))" in src and "q(_BOX_CONF_SQL, (S,))" in src
    assert "s.status = 'producing'" in r23._BOX_REAL_SQL and "(s.status = 'conflict' OR s.crowded)" in r23._BOX_CONF_SQL
    assert "curated.box_location_status" in r23._BOX_REAL_SQL and "reconciled_inventory" not in r23._BOX_REAL_SQL + r23._BOX_CONF_SQL
    assert "ri.status LIKE 'realized%%'" in src and "elif a.d145:" in src                              # the Novi reads are still there, unchanged
    assert "(SELECT k.status FROM tmp_conf k WHERE k.location_id = p.location_id)" in src            # a crowded stick is stored as crowded
    assert sl.NOT_DRILLABLE == ("conflict", "crowded") and sl.REALIZED == "producing" and sl.BOX_ID_MIN == 10_000_001


def test_summarise_counts_a_box_stick_that_went_producing_as_realized():
    assert '(d["recon_now"] == sl.REALIZED)' in inspect.getsource(r23.summarise)
