"""BOX sticks generator (box/sticks): the invariants of docs/box_sticks/phase3a-2026-11-14/BARS.md on synthetic DSUs,
the gunbarrel golden table on the function the generator uses, and the back-test slot match. DB-free."""
from __future__ import annotations

import json
import math

import pytest
from shapely.affinity import rotate
from shapely.geometry import LineString, box

from box.sticks import checks, core
from box.sticks.reads import default_cfg, link_fn

M = 1 / 3.280839895
X0, Y0 = 600_000.0, 3_500_000.0
CFG = default_cfg("delaware")
LINK = link_fn()


def rect(w_ft: float, h_ft: float, skew: float = 0.0):
    g = box(X0, Y0, X0 + w_ft * M, Y0 + h_ft * M)
    return rotate(g, -skew, origin="centroid") if skew else g


def bench(code, rank, tvd, s, **kw):
    return core.Bench(code=code, rank=rank, tvd_ft=tvd, rung=kw.pop("rung", "direct"), spacing_ft=s, inside_frac=kw.pop("inside", 1.0),
                      control=kw.pop("control", 10.0), **kw)


def well(wid, code, depth, x_ft, h_ft=10560.0, member=True):
    x = X0 + x_ft * M
    return core.Well(wid, code, depth, LineString([(x, Y0 + 400 * M), (x, Y0 + (h_ft - 400) * M)]), member)


def dsu(benches, wells=(), w=5280.0, h=10560.0, az=0.0, skew=0.0, **kw):
    return core.Dsu(pad_id=1, basin="delaware", polygon=rect(w, h, skew), az_grid_deg=az, az_true_deg=az, az_basis="test", benches=list(benches),
                    wells=list(wells), **kw)


def run(d, cfg=CFG):
    res = core.generate_dsu(d, cfg, LINK)
    bad = {k: v for k, v in checks.run_all(res, d, cfg, LINK).items() if v}
    assert not bad, bad
    return res


def xs(res, code):
    return sorted(leg["gunbarrel_x_ft"] for s in res.sticks if s["bench"] == code for leg in s["legs"])


def reasons(res, code):
    return [r["reason"] for r in res.ledger if r["code"] == code and r["status"] == "culled"]


def test_two_close_benches_on_one_spacing_alternate_and_keep_every_row():
    res = run(dsu([bench("BS3_S", 1, 11000, 880), bench("WCA_1", 2, 11200, 880)]))
    a, b = xs(res, "BS3_S"), xs(res, "WCA_1")
    assert len(a) == 6 and len(b) == 6                     # 4,620 ft clear: 6 rows at 880 ft leave 220 ft of slack
    off = (b[0] - a[0]) % 880                              # offset by the slack, not half a spacing: no row is lost to it
    assert 150 < min(off, 880 - off) < 221 and all(abs((y - a[0]) % 880 - off) < 1 for y in b)
    assert all(s["well_type"] == "single" and s["completed_lateral_ft"] >= 7000 for s in res.sticks)
    assert res.meta["well_type"] == "single"
    wide = run(dsu([bench("BS3_S", 1, 11000, 880), bench("WCA_1", 2, 11200, 880)], w=5280.0 + 340.0))
    a, b = xs(wide, "BS3_S"), xs(wide, "WCA_1")
    assert len(a) == len(b) == 6 and all(abs((y - a[0]) % 880 - 440) < 1 for y in b)      # 520 ft of slack: a true half spacing
    assert {r["code"]: r["grid"] for r in wide.benches} == {"BS3_S": "map_spacing", "WCA_1": "staggered"}


def test_uturn_benches_alternate_and_both_keep_their_pair():
    """DSU 10804: about 1,950 ft clear, two legs at 1,200 ft. The bench below sits 600 ft off the one above and keeps
    its U-turn (it used to be left with one leg at the centre and no stick)."""
    res = run(dsu([bench("AVA_0", 1, 9143, 937), bench("AVA_1", 2, 9350, 653), bench("AVA_2", 3, 9852, 858)], w=2640.0, h=5280.0))
    a, b, c = xs(res, "AVA_0"), xs(res, "AVA_1"), xs(res, "AVA_2")
    assert len(a) == len(b) == len(c) == 2 and len(res.sticks) == 3
    assert abs(abs(b[0] - a[0]) - 600) < 1 and abs(a[1] - a[0] - 1200) < 1
    assert not [r for r in res.ledger if r["status"] == "culled"]


def test_same_bench_well_pins_the_grid_and_closes_400_ft():
    w = [well("P1", "WCA_1", 11000, 1000), well("P2", "WCA_1", 11010, 1880)]
    res = run(dsu([bench("WCA_1", 1, 11000, 880)], w))
    got = xs(res, "WCA_1")                                 # gunbarrel origin = the DSU centroid (2,640 ft from the west line)
    assert all(abs((x - (1000 - 2640)) % 880) < 1 or abs((x - (1000 - 2640)) % 880 - 880) < 1 for x in got)
    assert all(abs(x - (1000 - 2640)) > 400 and abs(x - (1880 - 2640)) > 400 for x in got)
    assert reasons(res, "WCA_1").count("envelope_same_landing") == 2
    assert all("pinned" in s["flags"] for s in res.sticks)


def test_stacked_well_closes_the_row_above_it_and_not_a_far_one():
    w = [well("P1", "WCA_1", 11200, 2640 + 440)]           # 200 ft deeper than the BS3_S target, under the row at +440 ft
    res = run(dsu([bench("BS3_S", 1, 11000, 880)], w))
    assert reasons(res, "BS3_S") == ["envelope_stacked"]
    assert len(xs(res, "BS3_S")) == 5 and all(abs(x - 440) > 300 for x in xs(res, "BS3_S"))


def test_no_depth_well_closes_its_family_only_where_its_bench_has_no_landing():
    w = [well("P1", "WCA_2", None, 2640 + 440 + 100)]
    res = run(dsu([bench("WCA_1", 1, 11000, 880), bench("WCB_1", 2, 11500, 880)], w))
    assert reasons(res, "WCA_1") == ["no_depth_neighbour"]
    assert reasons(res, "WCB_1") == []


def test_no_depth_well_is_taken_at_its_benchs_landing_depth_in_the_dsu():
    """DSU 10600: a BS2_C spud with no depth evidence, BS2_C landing 430 ft above BS2_S. It closes its own bench's row
    as a same landing and leaves the BS2_S row beside it open (the family rule closed both)."""
    w = [well("P1", "BS2_C", None, 2640 + 440 + 100)]
    res = run(dsu([bench("BS2_C", 1, 10158, 880), bench("BS2_S", 2, 10588, 880)], w))
    assert "envelope_same_landing" in reasons(res, "BS2_C") and "no_depth_neighbour" not in reasons(res, "BS2_C")
    assert reasons(res, "BS2_S") == []
    close = run(dsu([bench("AVA_1", 1, 9133, 880), bench("AVA_2", 2, 9259, 600)], [well("P1", "AVA_1", None, 2640 + 440 + 100)]))
    assert "envelope_same_landing" in reasons(close, "AVA_2")         # landings 126 ft apart: one landing to the envelope


def test_uturn_dsu_legs_at_1200_ft_and_the_odd_leg_is_not_placed():
    res = run(dsu([bench("WCA_1", 1, 11000, 880)], w=6000.0, h=5280.0))
    assert res.meta["well_type"] == "uturn"
    assert {s["well_type"] for s in res.sticks} == {"uturn"}
    for s in res.sticks:
        assert abs(abs(s["legs"][0]["gunbarrel_x_ft"] - s["legs"][1]["gunbarrel_x_ft"]) - 1200) < 1
        assert s["spacing_basis"]["map_ft"] == 880 and s["spacing_basis"]["final_ft"] == 1200
    assert len(res.sticks) == 2 and reasons(res, "WCA_1") == ["uturn_unpaired"]      # 5 rows at 1,200 ft: two pairs and one odd leg


def test_skewed_azimuth_fits_the_rows_to_the_clear_width():
    """Polygon sides off the azimuth: the side setbacks cut a wedge off the outer rows. 1 deg still fits 6 rows at 880 ft;
    3 deg tightens the spacing (under 10 %) to keep 6; 5 deg would need more than 10 %, so one row goes and 5 are spread."""
    got = {}
    for skew in (0.0, 1.0, 3.0, 5.0):
        res = run(dsu([bench("WCA_1", 1, 11000, 880)], skew=skew, az=0.0))
        lens = [st["completed_lateral_ft"] for st in res.sticks]
        assert max(lens) - min(lens) < 60, skew            # no row is cut short by a side setback
        got[skew] = (len(lens), res.sticks[0]["spacing_basis"]["grid"], res.sticks[0]["spacing_basis"]["final_ft"], reasons(res, "WCA_1"))
    assert got[0.0][:3] == (6, "map_spacing", 880.0) and got[1.0][:3] == (6, "map_spacing", 880.0)
    assert got[3.0][:2] == (6, "tightened") and 792 <= got[3.0][2] < 880
    assert got[5.0][:2] == (5, "row_dropped") and got[5.0][2] >= 880 and got[5.0][3] == ["setback_fit"]


def test_close_benches_keep_their_own_rows_and_their_own_spacing():
    """Rows of different benches are not tested against each other (Michael, 2026-11-15): each bench keeps every row its
    own spacing gives, however close the bench above or below lands."""
    res = run(dsu([bench("DEAN", 1, 8250, 827, control=5), bench("WCA_1", 2, 8500, 664, control=20)]))
    assert len(xs(res, "WCA_1")) == 7 and len(xs(res, "DEAN")) == 6 and reasons(res, "DEAN") == []
    near = run(dsu([bench("AVA_2", 1, 9770, 849), bench("BS1_S", 2, 9926, 1096)]))          # DSU 10785: 156 ft apart in TVD
    assert len(xs(near, "AVA_2")) == 6 and len(xs(near, "BS1_S")) == 5 and not reasons(near, "BS1_S")
    own = run(dsu([bench("LSSH", 1, 8300, 775, control=20), bench("DEAN", 2, 8400, 827, control=5)]))       # within 15 %: no sharing
    assert {s["bench"]: s["spacing_basis"]["final_ft"] for s in own.sticks} == {"LSSH": 775.0, "DEAN": 827.0}


def test_sliver_wca_rule_and_reconciliation_give_a_reason_per_bench():
    b = [bench("BS3_S", 1, 11000, 880, inside=0.05), bench("WCA_1", 2, 11300, 880), bench("WCA_2", 3, 11420, 880),
         bench("WCB_1", 4, 11450, 880, rung="offset", tvd_err_median_ft=80.0, tvd_err_p90_ft=20.0), bench("WCC", 5, None, 880, rung="none")]
    one = run(dsu(b, wca_class="one member", wca_dominant="WCA_2"))
    why = {r["code"]: r["no_row_reason"] for r in one.benches}
    assert why == {"BS3_S": "sliver", "WCA_1": "wca_one_member", "WCA_2": "", "WCB_1": "reconciled_out", "WCC": "no_depth"}
    both = run(dsu(b[:3], wca_class="co-developed"))
    assert xs(both, "WCA_1") and xs(both, "WCA_2")
    b[3] = bench("WCB_1", 4, 11450, 880, rung="offset", tvd_err_median_ft=80.0, tvd_err_p90_ft=200.0)
    moved = run(dsu(b, wca_class="one member", wca_dominant="WCA_2"))
    assert {s["target_tvd_ft"] for s in moved.sticks if s["bench"] == "WCB_1"} == {11495.0}


def test_codeveloped_wca_members_are_not_tested_against_each_other():
    w = [well("P1", "WCA_2", 11100, 2640 + 440)]
    b = [bench("WCA_1", 1, 11000, 880), bench("WCA_2", 2, 11100, 880)]
    co = run(dsu(b, w, wca_class="co-developed"))
    assert "envelope_same_landing" not in reasons(co, "WCA_1")
    assert "envelope_same_landing" in reasons(co, "WCA_2")


def test_same_inputs_give_the_same_bytes():
    d = dsu([bench("BS3_S", 1, 11000, 880), bench("WCA_1", 2, 11200, 700)], [well("P1", "WCA_1", 11190, 900)])
    a, b = (json.dumps(core.generate_dsu(d, CFG, LINK).sticks, sort_keys=True) for _ in range(2))
    assert a == b and len(a) > 100


def test_gunbarrel_golden_table_on_the_generators_function():
    from narvi.placement import plus_offset_bearing_deg

    from tests.test_dealintake_core import GOLDEN_PLUS_BEARING
    for az, want in GOLDEN_PLUS_BEARING:
        assert abs((plus_offset_bearing_deg(az) - want + 180.0) % 360.0 - 180.0) < 1e-6, az


@pytest.mark.parametrize("az", [0.0, 44.9, 45.1, 89.0, 135.0, 179.5])
def test_gunbarrel_offsets_reproduce_from_geometry(az):
    res = run(dsu([bench("WCA_1", 1, 11000, 880)], w=10560.0, h=10560.0, az=az))
    assert res.sticks or az not in (0.0, 89.0)
    b = math.radians(core.npl.plus_offset_bearing_deg(az))
    assert -45.0 < (math.degrees(b) + 180) % 360 - 180 <= 135.0


def test_resolve_azimuth_order():
    assert core.resolve_azimuth([163.7, 163.9], 0.0, 1.0, (0.0, 50), 0.0) == (pytest.approx(163.8), "wells_in_dsu")
    assert core.resolve_azimuth([2.0], 0.0, 1.0, None, None) == (0.0, "wells_in_dsu+side")
    assert core.resolve_azimuth([], 90.0, 2.0, (0.0, 50), 0.0) == (90.0, "long_axis")
    assert core.resolve_azimuth([], 90.0, 1.0, (178.0, 50), 90.0) == (0.0, "cell")
    assert core.resolve_azimuth([], 90.0, 1.0, (178.0, 3), 88.0) == (90.0, "county")
    assert core.resolve_azimuth([], 80.0, 1.0, None, 36.0) == (80.0, "long_axis+square_unresolved")


def test_match_slots_is_one_to_one_and_respects_the_gates():
    p = [{"well": "A", "leg": "L1", "shared_frac": 0.9, "dh_ft": 100.0, "dz_ft": 20.0, "spacing_ft": 880.0},
         {"well": "B", "leg": "L1", "shared_frac": 0.9, "dh_ft": 50.0, "dz_ft": 20.0, "spacing_ft": 880.0},
         {"well": "A", "leg": "L2", "shared_frac": 0.9, "dh_ft": 300.0, "dz_ft": None, "spacing_ft": 880.0},
         {"well": "C", "leg": "L3", "shared_frac": 0.9, "dh_ft": 250.0, "dz_ft": 0.0, "spacing_ft": 440.0},
         {"well": "D", "leg": "L4", "shared_frac": 0.9, "dh_ft": 10.0, "dz_ft": 160.0, "spacing_ft": 880.0},
         {"well": "E", "leg": "L5", "shared_frac": 0.4, "dh_ft": 10.0, "dz_ft": 0.0, "spacing_ft": 880.0}]
    assert checks.match_slots(p) == {"B": "L1", "A": "L2"}
