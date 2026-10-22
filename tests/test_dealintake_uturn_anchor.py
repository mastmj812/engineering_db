"""U-turns, unit anchors and per-producer proximity exemptions (Michael 2026-10-22,
RIP Harambe: Boondoggle U-turns anchored to the east line, ignore 4238934075). DB-free."""

from __future__ import annotations

from typing import Any

import pytest
from shapely.geometry import MultiLineString, mapping

from dealintake import config as cfgmod
from dealintake import handoff, unit_benches
from dealintake.clients.narvi import wells
from dealintake.pipeline import gunbarrel_preview, leg_rows
from dealintake.proximity import ProximityRule
from tests._dealintake_fixtures import line_ft, rect_ft

PX = cfgmod.load().raw["pdp_proximity"]
UNIT = rect_ft(-2640, -5000, 2640, 5000)                 # N-S unit, +offset = east


def _feat(x: float, name: str, leg: int = 0, formation: str = "WCB_2", lateral: float = 9000.0) -> dict[str, Any]:
    return {"type": "Feature", "geometry": mapping(line_ft((x, -4600), (x, 4600))),
            "properties": {"kind": "leg", "formation": formation, "well_name": name, "leg_index": leg,
                           "gunbarrel_x_ft": x, "completed_lateral_ft": lateral}}


def _uturn_response(pairs: list[tuple[float, float]], formation: str = "WCB_2") -> dict[str, Any]:
    feats = []
    for i, (a, b) in enumerate(pairs, 1):
        feats += [_feat(a, f"U{i}", 0, formation, 18400.0), _feat(b, f"U{i}", 1, formation, 18400.0)]
    feats.append({"type": "Feature", "geometry": mapping(line_ft((0, 4700), (1320, 4700))),
                  "properties": {"kind": "turn", "well_name": "U1", "formation": formation}})
    return {"geojson": {"features": feats}}


def test_wells_groups_a_uturn_into_one_well():
    ws = wells(_uturn_response([(-660, 660), (1980, 3300)]))
    assert len(ws) == 2
    w = ws[0]
    assert w["n_legs"] == 2 and isinstance(w["geom"], MultiLineString)
    assert w["gunbarrel_xs"] == [-660.0, 660.0] and w["gunbarrel_x_ft"] == 0.0
    assert w["completed_lateral_ft"] == 18400.0                # the WELL's total, counted once
    assert w["turn_wkt"].startswith("LINESTRING") and ws[1]["turn_wkt"] is None   # arc kept for the map
    single = wells({"geojson": {"features": [_feat(100, "S1")]}})
    assert single[0]["n_legs"] == 1 and single[0]["gunbarrel_x_ft"] == 100


def _w(api10: str, x: float, tvd: float, bench: str = "WCA_1") -> dict[str, Any]:
    return {"api10": api10, "bench": bench, "tvd_ft": tvd, "wkt": line_ft((x, -4500), (x, 4500)).wkt}


def test_ignored_producer_is_listed_not_culled_and_others_still_cull():
    rule = ProximityRule(UNIT, 0.0, [_w("4238934075", 500, 10312), _w("4238935585", -400, 10355)], PX)
    ours = line_ft((0, -4600), (0, 4600))
    r = rule.check(ours, 10310.0, ignore=["4238934075"])
    assert [h["api10"] for h in r["cull"]] == ["4238935585"]
    assert [h["api10"] for h in r["ignored"]] == ["4238934075"]
    r = rule.check(ours, 10310.0, ignore=["4238934075", "4238935585"])
    assert r["cull"] == [] and len(r["ignored"]) == 2


def test_a_uturn_is_culled_when_either_leg_is_inside_the_envelope():
    rule = ProximityRule(UNIT, 0.0, [_w("A", 1900, 10312)], PX)        # beside the east leg only (off a round-100 permit TVD)
    uturn = MultiLineString([line_ft((0, -4600), (0, 4600)), line_ft((1320, -4600), (1320, 4600))])
    assert [h["api10"] for h in rule.check(uturn, 10310.0)["cull"]] == ["A"]
    from dealintake.geo import gunbarrel_frame
    project, _, _ = gunbarrel_frame(UNIT, 0.0)
    (row,) = leg_rows([{"geom": uturn, "completed_lateral_ft": 18400.0}], project, rule, 10310.0)
    assert row["lateral_ft"] == 18400 and len(row["leg_offsets_ft"]) == 2 and row["proximity"]["cull"]


def test_benches_yaml_keys():
    o = unit_benches.bench_options({"evaluate": True, "well_type": "uturn", "pdp_proximity_ignore": [4238934075]}, "u.b")
    assert o == {"well_type": "uturn", "pdp_proximity_ignore": ["4238934075"]}
    with pytest.raises(ValueError, match="well_type"):
        unit_benches.bench_options({"evaluate": True, "well_type": "horseshoe"}, "u.b")
    with pytest.raises(ValueError, match="api10"):
        unit_benches.bench_options({"evaluate": True, "pdp_proximity_ignore": ["42389"]}, "u.b")
    assert unit_benches.unit_anchor({"anchor": "east"}, "u") == "east"
    assert unit_benches.unit_anchor({}, "u") is None
    with pytest.raises(ValueError, match="anchor"):
        unit_benches.unit_anchor({"anchor": "northeast"}, "u")


class _UNarvi:
    def __init__(self) -> None:
        self.calls: list[tuple[list[dict[str, Any]], dict[str, Any]]] = []

    def generate(self, parcel, zones, **kw):
        self.calls.append((zones, kw))
        z = zones[0]
        if z.get("well_type") == "uturn":
            return _uturn_response([(-1980, -660), (660, 1980)], z["formation"])
        return {"geojson": {"features": [_feat(x, f"S{i}", formation=z["formation"]) for i, x in enumerate((-1320, 0, 1320))]}}


def test_preview_sends_anchor_and_uturn_and_counts_wells():
    nv = _UNarvi()
    prop = [{"bench": "WCB_2", "median_tvd_ft": 10744.0}]
    gb = gunbarrel_preview(UNIT, 0.0, prop, {"WCB_2": {"evaluate": True, "why": "x"}}, {}, [], [], nv, setback_ft=330,
                           bench_opts={"WCB_2": {"well_type": "uturn", "spacing_ft": 1320.0}}, anchor="east")
    zones, kw = nv.calls[0]
    assert zones[0]["well_type"] == "uturn" and kw["anchor"] == "east"
    pl = gb["planned"]["WCB_2"]
    assert pl["well_type"] == "uturn" and len(pl["offsets_ft"]) == 2 and len(pl["leg_offsets_ft"]) == 4
    assert pl["winerack"] is False                              # a U-turn bench is placed on its own


def test_handoff_saves_the_anchor_and_uturn_recipe_and_matches_wells():
    nv = _UNarvi()
    ws = wells(_uturn_response([(-1980, -660), (660, 1980)]))
    ub = {"gate2": {"source": "generate"}, "tvd_ft": 10744.0, "spacing_ft": 1320.0, "row_rules": [],
          "well_type": "uturn", "anchor": "east",
          "locations": [{"id": f"gen-{i}", "wkt": w["geom"].wkt} for i, w in enumerate(ws)]}
    unit = {"label": "rip_harambe_dsu_boondoggle_wcb", "dsu_name": "Boondoggle (WCB)", "geometry": mapping(UNIT),
            "planned_lateral": {"azimuth_deg": 12.3}, "window_used": [None, None], "window_source": None,
            "rights": "Top of Wolfcamp B -> Base of Wolfcamp B", "attributes": {"Type": "DSU"}}
    u = handoff.plan_unit(nv, unit, {"WCB_2": ub}, 330.0)
    assert u["issues"] == [] and u["body"]["culled_wells"] == []
    assert [r["status"] for r in u["rows"]] == ["kept", "kept"]           # two WELLS, not four legs
    assert u["body"]["params"]["anchor"] == "east" and u["body"]["zones"][0]["well_type"] == "uturn"


@pytest.mark.parametrize("row_anchor", [None, "east"])
def test_stagger_sends_the_units_row_anchor_never_the_anchor_bench(row_anchor):
    """Regression (RIP Harambe 15-22, 2026-10-22): winerack_legs' anchor BENCH once
    shadowed the unit's row anchor and narvi got anchor='WCB_1' (422)."""
    from dealintake.pipeline import winerack_legs

    nv = _UNarvi()
    winerack_legs(nv, UNIT, 0.0, {"WCA_2": (10444.0, 1320.0), "WCB_1": (10691.0, 1320.0)}, setback_ft=330,
                  row_anchor=row_anchor)
    assert len(nv.calls) == 3 and {kw.get("anchor") for _, kw in nv.calls} == {row_anchor}


def test_uturn_bench_pools_on_its_completed_lateral():
    """Michael 2026-10-22: a U-turn's pool is drawn on its COMPLETED lateral (sum of
    legs, curve excluded) — not the unit's planned chord. Straight benches unchanged."""
    from dealintake.pipeline import bench_laterals

    plan = {"bw": {"benches": ["WCA_1"], "planned_lateral_ft": 7234.0,
                   "bench_opts": {"WCA_1": {"well_type": "uturn"}}},
            "s": {"benches": ["WCA_1"], "planned_lateral_ft": 9900.0, "bench_opts": {"WCA_1": {}}}}
    prop = {"units": [
        {"label": "bw", "gunbarrel": {"planned": {"WCA_1": {"well_type": "uturn", "lateral_ft": [13104, 13160]}}}},
        {"label": "s", "gunbarrel": {"planned": {}}}]}
    got = bench_laterals(plan, prop)
    assert got[("bw", "WCA_1")][0] == 13132.0 and "curve excluded" in got[("bw", "WCA_1")][1]
    assert got[("s", "WCA_1")] == (9900.0, "planned lateral")
    prop["units"][0]["gunbarrel"]["planned"]["WCA_1"]["well_type"] = "single"      # preview predates the call
    with pytest.raises(ValueError, match="re-run propose"):
        bench_laterals(plan, prop)


def test_stagger_lead_keeps_its_layout_against_the_count_rule():
    """RIP Harambe 15-22: WCB_1 leads (keeps its lattice) although WCA_2 keeps more rows alone."""
    from dealintake.pipeline import winerack_legs

    zones = {"WCA_2": (10444.0, 1320.0), "WCB_1": (10691.0, 1320.0)}
    counts = {"WCA_2": 3, "WCB_1": 2}
    _, pins = winerack_legs(_UNarvi(), UNIT, 0.0, zones, setback_ft=330, kept=lambda b, lg: counts[b])
    assert pins["WCA_2"] == -1320.0 and pins["WCB_1"] != -1320.0          # count rule: WCA_2 leads
    _, pins = winerack_legs(_UNarvi(), UNIT, 0.0, zones, setback_ft=330, kept=lambda b, lg: counts[b], lead="WCB_1")
    assert pins["WCB_1"] == -1320.0 and pins["WCA_2"] == -660.0           # WCB_1 leads, WCA_2 shifted half a spacing


def test_only_one_stagger_lead_per_unit(tmp_path):
    prop = {"units": [{"label": "u1", "planned_lateral": {"median_ft": 7358.0}, "bench_seed": {}}]}
    (tmp_path / unit_benches.FILENAME).write_text(
        "units:\n  u1:\n    benches:\n      WCA_2: {evaluate: true, stagger_lead: true}\n"
        "      WCB_1: {evaluate: true, stagger_lead: true}\n", encoding="utf-8")
    with pytest.raises(ValueError, match="stagger_lead"):
        unit_benches.read(tmp_path, prop)


def test_pinned_bench_sends_its_offset_and_is_not_staggered():
    """RIP Harambe blob (Michael's mockup): WCA_2 at -1,320 / 0 / +1,320 = pin 0 @ 1,320."""
    o = unit_benches.bench_options({"evaluate": True, "pin_offset_ft": 0, "spacing_ft": 1320}, "u.b")
    assert o == {"pin_offset_ft": 0.0, "spacing_ft": 1320.0}
    with pytest.raises(ValueError, match="pin_offset_ft"):
        unit_benches.bench_options({"evaluate": True, "pin_offset_ft": "center"}, "u.b")
    nv = _UNarvi()
    prop = [{"bench": "WCA_2", "median_tvd_ft": 10478.0}]
    gb = gunbarrel_preview(UNIT, 0.0, prop, {"WCA_2": {"evaluate": True, "why": "x"}}, {}, [], [], nv, setback_ft=330,
                           bench_opts={"WCA_2": {"pin_offset_ft": 0.0, "spacing_ft": 1320.0}})
    zones, _ = nv.calls[0]
    assert len(nv.calls) == 1 and zones[0]["offset_ft"] == 0.0
    assert gb["planned"]["WCA_2"]["winerack"] is False and gb["planned"]["WCA_2"]["pin_offset_ft"] == 0.0


def test_handoff_page_draws_a_uturn_row():
    """Regression (RIP Harambe handoff dry run 2026-10-22): the page called .xy on a
    U-turn's MultiLineString. Plan view, + side and cross-section take both legs."""
    from dealintake.render import handoff_html

    ws = wells(_uturn_response([(-1980, -660), (660, 1980)]))
    rows = [{"bench": "WCB_2", "status": "kept" if i == 0 else "culled", "tvd_ft": 10744.0,
             "offset_ft": w["gunbarrel_x_ft"], "leg_offsets_ft": w["gunbarrel_xs"], "wkt": w["geom"].wkt}
            for i, w in enumerate(ws)]
    u = {"label": "bw", "dsu": "Boondoggle (WCB)", "body": {"parcel": mapping(UNIT)}, "rows": rows}
    colors = {("bw", "WCB_2"): "#db2777"}
    assert "<svg" in handoff_html._unit_map(u, colors)
    assert "<svg" in handoff_html._gunbarrel(u, colors)
    assert handoff_html._plus_side(u) == "E"
