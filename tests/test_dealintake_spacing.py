"""Generated-bench row spacing from NEARBY Novi sticks (config v15, Michael 2026-10-22). DB-free."""

import pytest

from dealintake import config as cfgmod
from dealintake.pipeline import row_spacing
from dealintake.spacing import flag_text, neighbour_gaps_ft, resolve, short_text
from tests._dealintake_fixtures import FRAME, line_ft, rect_ft

PS = cfgmod.load().raw["planned_spacing"]
KW = {"parallel_tol_deg": 15.0, "overlap_min_frac": 0.30, "same_slot_ft": 300.0, "search_ft": 3000.0}
UNIT = rect_ft(0, 0, 5280, 10560)                      # 1 x 2 mi, N-S


def ns_row(xs, y0=0.0, y1=9900.0):
    return [line_ft((x, y0), (x, y1)) for x in xs]


def sticks(geoms, cat="PUD"):
    return [{"category": cat, "geom": g} for g in geoms]


def test_regular_pattern_gives_its_spacing():
    gaps = neighbour_gaps_ft(ns_row([0, 1320, 2640, 3960]), FRAME, **KW)
    assert gaps == pytest.approx([1320.0] * 4, abs=2)


def test_pattern_orientation_does_not_matter():
    ew = [line_ft((0, y), (9900, y)) for y in (0, 880, 1760)]
    assert neighbour_gaps_ft(ew, FRAME, **KW) == pytest.approx([880.0] * 3, abs=2)


def test_same_slot_end_to_end_and_crossing_sticks_are_not_neighbours():
    g = ns_row([0, 133, 1320])                           # 133 ft off a slot = the same slot
    gaps = neighbour_gaps_ft(g, FRAME, **KW)
    assert gaps[0] == pytest.approx(1320.0, abs=2) and gaps[1] == pytest.approx(1187.0, abs=2)
    # end-to-end in the next section row: no co-extent -> no neighbour
    assert neighbour_gaps_ft([line_ft((0, 0), (0, 5000)), line_ft((0, 5400), (0, 10000))], FRAME, **KW) == [None, None]
    # an E-W stick 500 ft off is not parallel to a N-S one
    assert neighbour_gaps_ft([line_ft((0, 0), (0, 9900)), line_ft((500, 4000), (9000, 4000))], FRAME, **KW) == [None, None]


def test_chain_nearest_radius_first():
    near = sticks(ns_row([660 + 1320 * i for i in range(8)]))            # inside the unit footprint, 1,320
    got = resolve(UNIT, near, [], PS, sentinel_ft=2800)
    assert got["source"] == "novi_pud" and got["radius_mi"] == 1 and got["spacing_ft"] == pytest.approx(1320, abs=2)
    assert not got["mixed"] and not got["needs_reviewer"]
    # only a pattern 1-2 mi east of the unit -> the 2-mi step (6 of its 8 sticks within 2 mi)
    far = sticks(ns_row([5280 + 5500 + 880 * i for i in range(8)]))
    got = resolve(UNIT, far, [], PS, sentinel_ft=2800)
    assert got["radius_mi"] == 2 and got["spacing_ft"] == pytest.approx(880, abs=2)
    assert "Novi PUD ≤2 mi" in got["text"] and short_text(got).startswith("Novi PUD ≤2 mi, IQR")


def test_chain_falls_to_res_then_pdp_then_reviewer():
    res = sticks(ns_row([660 + 1056 * i for i in range(8)]), cat="RES")
    got = resolve(UNIT, res, [], PS, sentinel_ft=2800)
    assert got["source"] == "novi_res" and got["spacing_ft"] == pytest.approx(1056, abs=2)
    assert any("Novi PUD: none" in t for t in got["tried"])
    pdp = [1100.0, 1050.0, None, 2800.0, 1200.0, 1000.0, 1150.0, 2800.0, 1080.0]   # NULL + sentinel out -> 6 bounded
    got = resolve(UNIT, [], pdp, PS, sentinel_ft=2800)
    assert got["source"] == "pdp" and got["n_gaps"] == 6 and got["spacing_ft"] == pytest.approx(1090, abs=1)
    got = resolve(UNIT, sticks(ns_row([660, 1980])), pdp[:4], PS, sentinel_ft=2800)  # 2 gaps, 2 bounded wells
    assert got["spacing_ft"] is None and got["needs_reviewer"]
    assert flag_text("WCA_1", got) == "WCA_1 (spacing: none nearby — set spacing_ft)"


def test_mixed_pattern_is_flagged():
    # two patterns side by side (RIP Harambe WCB_1: 4- and 5-per-section areas): 1,320 and 1,058
    xs = [1320.0 * i for i in range(5)] + [7000.0 + 1058 * i for i in range(4)]
    got = resolve(UNIT, sticks(ns_row(xs)), [], PS, sentinel_ft=2800)
    assert got["mixed"] and "mixed pattern" in flag_text("WCB_1", got)


def _prop(spacings):
    return {"units": [{"label": lb, "dsu_name": lb, "spacing": {"WCB_1": s} if s else {}} for lb, s in spacings.items()]}


def _plan(revs):
    return {lb: {"bench_opts": {"WCB_1": {"spacing_ft": v}} if v else {}} for lb, v in revs.items()}


def test_row_spacing_order_and_borrowing():
    found = {"spacing_ft": 1320.0, "text": "Novi PUD ≤1 mi: 1,320 ft"}
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
                  "WCB_1": {"spacing_ft": 1320.0, "text": "Novi PUD ≤1 mi: 1,320 ft"},
                  "WCB_2": {"spacing_ft": None, "needs_reviewer": True, "text": "no spacing: … — set spacing_ft"}}
    opts = {b: {"winerack": False} for b in seed} | {"WCA_1": {"winerack": False, "spacing_ft": 1000.0}}
    gb = gunbarrel_preview(UNIT, 0.0, prop, seed, {}, [], [], _Narvi(), setback_ft=330,
                           bench_opts=opts, spacing_by=spacing_by)
    assert gb["planned"]["WCA_1"]["spacing_ft"] == 1000.0 and gb["planned"]["WCA_1"]["spacing_source"] == "reviewer"
    assert gb["planned"]["WCB_1"]["spacing_ft"] == 1320.0
    assert gb["planned"]["WCB_1"]["spacing_source"].startswith("Novi PUD")
    assert gb["planned"]["WCB_2"]["spacing_needed"] and "set spacing_ft" in gb["planned"]["WCB_2"]["error"]
    assert sorted(kw["spacing_ft"] for _, kw in calls) == [1000.0, 1320.0]          # WCB_2 never generated
