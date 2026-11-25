"""Generated-bench row spacing from NEARBY BOX sticks (config v18; v15 Michael 2026-10-22). DB-free."""

import pytest

from dealintake import config as cfgmod
from dealintake.pipeline import row_spacing
from dealintake.spacing import flag_text, resolve, short_text
from tests._dealintake_fixtures import line_ft, rect_ft

PS = cfgmod.load().raw["planned_spacing"]
UNIT = rect_ft(0, 0, 5280, 10560)                      # 1 x 2 mi, N-S


def ns_row(xs, y0=0.0, y1=9900.0):
    return [line_ft((x, y0), (x, y1)) for x in xs]


def sticks(geoms, spacing_ft=1320.0, band="0-2 mi"):
    """BOX sticks as warehouse.box_sticks returns them: each CARRIES its planned spacing."""
    return [{"geom": g, "spacing_ft": spacing_ft, "spacing_band": band} for g in geoms]


def test_the_sticks_own_planned_spacing_is_read_not_measured():
    # drawn 1,320 ft apart but planned at 1,200: the stick's number wins (no gap measurement)
    got = resolve(UNIT, sticks(ns_row([660 + 1320 * i for i in range(8)]), spacing_ft=1200.0), [], PS, sentinel_ft=2800)
    assert got["source"] == "box" and got["radius_mi"] == 1 and got["spacing_ft"] == 1200.0
    assert not got["mixed"] and not got["needs_reviewer"] and not got["far_band"]
    assert "BOX sticks ≤1 mi: 1,200 ft from 8 sticks" in got["text"]
    # the gap-measurement knobs stay in the config: the BOX stick generator reads them
    assert {"parallel_tol_deg", "overlap_min_frac", "same_slot_ft", "neighbour_search_ft"} <= set(PS)


def test_neighbour_gap_method_is_kept_for_the_box_stick_generator():
    """scripts/box_sticks_phase2a.py measures producer spacing by this method and checks itself against it."""
    from dealintake.spacing import neighbour_gaps_ft
    from tests._dealintake_fixtures import FRAME

    kw = {"parallel_tol_deg": float(PS["parallel_tol_deg"]), "overlap_min_frac": float(PS["overlap_min_frac"]),
          "same_slot_ft": float(PS["same_slot_ft"]), "search_ft": float(PS["neighbour_search_ft"])}
    assert neighbour_gaps_ft(ns_row([0, 1320, 2640, 3960]), FRAME, **kw) == pytest.approx([1320.0] * 4, abs=2)
    g = ns_row([0, 133, 1320])                           # 133 ft off a slot = the same slot
    gaps = neighbour_gaps_ft(g, FRAME, **kw)
    assert gaps[0] == pytest.approx(1320.0, abs=2) and gaps[1] == pytest.approx(1187.0, abs=2)
    assert neighbour_gaps_ft([line_ft((0, 0), (0, 5000)), line_ft((0, 5400), (0, 10000))], FRAME, **kw) == [None, None]


def test_chain_nearest_radius_first():
    # only sticks 1-2 mi east of the unit -> the 2-mi step (6 of its 8 sticks within 2 mi)
    far = sticks(ns_row([5280 + 5500 + 880 * i for i in range(8)]), spacing_ft=880.0)
    got = resolve(UNIT, far, [], PS, sentinel_ft=2800)
    assert got["radius_mi"] == 2 and got["spacing_ft"] == 880.0 and got["n_gaps"] == 6
    assert "BOX sticks ≤2 mi" in got["text"] and short_text(got).startswith("BOX sticks ≤2 mi, IQR")


def test_chain_falls_to_pdp_then_reviewer():
    pdp = [1100.0, 1050.0, None, 2800.0, 1200.0, 1000.0, 1150.0, 2800.0, 1080.0]   # NULL + sentinel out -> 6 bounded
    got = resolve(UNIT, [], pdp, PS, sentinel_ft=2800)
    assert got["source"] == "pdp" and got["n_gaps"] == 6 and got["spacing_ft"] == pytest.approx(1090, abs=1)
    assert any("BOX sticks: none" in t for t in got["tried"])
    got = resolve(UNIT, sticks(ns_row([660, 1980])), pdp[:4], PS, sentinel_ft=2800)  # 2 sticks, 2 bounded wells
    assert got["spacing_ft"] is None and got["needs_reviewer"]
    assert any("BOX sticks: 2 within 3 mi (< 6)" in t for t in got["tried"])
    assert flag_text("WCA_1", got) == "WCA_1 (spacing: none nearby — set spacing_ft)"
    # a stick without a planned spacing does not count
    assert resolve(UNIT, sticks(ns_row([660 * i for i in range(1, 8)]), spacing_ft=None), [], PS, sentinel_ft=2800)["needs_reviewer"]


def test_mixed_pattern_is_flagged():
    # two planned patterns side by side: 1,320 and 1,058
    xs = [660.0 + 500 * i for i in range(9)]
    mixed = sticks(ns_row(xs[:5]), spacing_ft=1320.0) + sticks(ns_row(xs[5:]), spacing_ft=1058.0)
    got = resolve(UNIT, mixed, [], PS, sentinel_ft=2800)
    assert got["mixed"] and "mixed pattern" in flag_text("WCB_1", got)


def test_spacing_set_from_far_wells_is_said():
    """A BOX stick's spacing can come from wells 10+ miles away (20,809 of 79,275 record sticks, 2026-11-25): when
    most of the sticks behind a number are that band, the text says so."""
    xs = [660 + 600 * i for i in range(8)]
    got = resolve(UNIT, sticks(ns_row(xs[:5]), band="10+ mi") + sticks(ns_row(xs[5:]), band="2-5 mi"), [], PS, sentinel_ft=2800)
    assert got["far_band"] and "5 of 8 set from wells 10+ mi away" in got["text"]
    got = resolve(UNIT, sticks(ns_row(xs[:3]), band="10+ mi") + sticks(ns_row(xs[3:]), band="2-5 mi"), [], PS, sentinel_ft=2800)
    assert not got["far_band"] and "10+ mi" not in got["text"]


def test_a_uturn_stick_counts_once_and_is_placed_by_its_legs():
    from shapely.geometry import MultiLineString

    u = [MultiLineString([line_ft((x, 0), (x, 5000)), line_ft((x + 1200, 0), (x + 1200, 5000))]) for x in (300, 2700)]
    got = resolve(UNIT, sticks(u + ns_row([660 * i for i in range(1, 5)]), spacing_ft=1200.0), [], PS, sentinel_ft=2800)
    assert got["n_gaps"] == 6 and got["spacing_ft"] == 1200.0


def _prop(spacings):
    return {"units": [{"label": lb, "dsu_name": lb, "spacing": {"WCB_1": s} if s else {}} for lb, s in spacings.items()]}


def _plan(revs):
    return {lb: {"bench_opts": {"WCB_1": {"spacing_ft": v}} if v else {}} for lb, v in revs.items()}


def test_row_spacing_order_and_borrowing():
    found = {"spacing_ft": 1320.0, "text": "BOX sticks ≤1 mi: 1,320 ft"}
    jobs = [("WCB_1", ["a", "b"], "WCB_1")]
    cls, per = row_spacing(jobs, _prop({"a": found, "b": None}), _plan({"a": None, "b": None}), {}, 15)
    assert cls["WCB_1"][0] == 1320.0 and per[("a", "WCB_1")] == (1320.0, found["text"])
    assert per[("b", "WCB_1")][0] == 1320.0 and per[("b", "WCB_1")][1].startswith("borrowed 1,320 ft")
    cls, per = row_spacing(jobs, _prop({"a": found, "b": None}), _plan({"a": None, "b": 880}), {}, 15)
    assert per[("b", "WCB_1")] == (880.0, "reviewer (benches.yaml)") and cls["WCB_1"][1].startswith("reviewer")
    cls, per = row_spacing(jobs, _prop({"a": found, "b": None}), _plan({"a": None, "b": None}), {"WCB_1": 1000.0}, 15)
    assert per[("a", "WCB_1")] == (1000.0, "reviewer (--spacing)")


def test_row_spacing_refuses_a_bench_with_no_number():
    with pytest.raises(ValueError, match="no row spacing for a WCB_1"):
        row_spacing([("WCB_1", ["a"], "WCB_1")], _prop({"a": None}), _plan({"a": None}), {}, 15)


def test_gunbarrel_preview_uses_nearby_spacing_and_skips_a_bench_with_none():
    from shapely.geometry import mapping

    from dealintake.pipeline import gunbarrel_preview

    calls = []

    class _Narvi:
        def generate(self, parcel, zones, **kw):
            calls.append((zones, kw))
            feats = [{"type": "Feature", "geometry": mapping(line_ft((x, 300), (x, 10200))),
                      "properties": {"kind": "leg", "formation": zones[0]["formation"], "completed_lateral_ft": 9900,
                                     "gunbarrel_x_ft": float(x)}} for x in (1320, 2640)]
            return {"geojson": {"features": feats}}

    prop = [{"bench": b, "median_tvd_ft": t} for b, t in (("WCA_1", 10400.0), ("WCB_1", 10700.0), ("WCB_2", 10900.0))]
    seed = {b: {"evaluate": True, "why": "x"} for b in ("WCA_1", "WCB_1", "WCB_2")}
    spacing_by = {"WCA_1": {"spacing_ft": 901.0, "text": "offset PDP closer-XY ≤3 mi: 901 ft"},
                  "WCB_1": {"spacing_ft": 1320.0, "text": "BOX sticks ≤1 mi: 1,320 ft"},
                  "WCB_2": {"spacing_ft": None, "needs_reviewer": True, "text": "no spacing: … — set spacing_ft"}}
    opts = {b: {"winerack": False} for b in seed} | {"WCA_1": {"winerack": False, "spacing_ft": 1000.0}}
    gb = gunbarrel_preview(UNIT, 0.0, prop, seed, {}, [], [], _Narvi(), setback_ft=330,
                           bench_opts=opts, spacing_by=spacing_by)
    assert gb["planned"]["WCA_1"]["spacing_ft"] == 1000.0 and gb["planned"]["WCA_1"]["spacing_source"] == "reviewer"
    assert gb["planned"]["WCB_1"]["spacing_ft"] == 1320.0
    assert gb["planned"]["WCB_1"]["spacing_source"].startswith("BOX sticks")
    assert gb["planned"]["WCB_2"]["spacing_needed"] and "set spacing_ft" in gb["planned"]["WCB_2"]["error"]
    assert sorted(kw["spacing_ft"] for _, kw in calls) == [1000.0, 1320.0]          # WCB_2 never generated
