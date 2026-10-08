"""Gate 8 handoff plan: narvi recipe + row match, pins, curve/zone specs. DB-free
(a fake narvi stands in for /api/generate)."""

from __future__ import annotations

from typing import Any

from shapely.geometry import LineString, box, mapping

from dealintake import handoff

LON0, LAT0 = -103.5, 32.0
DLON_PER_FT = 1 / 309_000          # ~ft per degree of longitude at 32 N


def _line(x_ft: float) -> LineString:
    x = LON0 + x_ft * DLON_PER_FT
    return LineString([(x, LAT0 + 0.0125), (x, LAT0 - 0.0125)])


def _unit(**kw: Any) -> dict[str, Any]:
    return {"label": "rally_caps_dsu_1_12", "dsu_name": "1-12",
            "geometry": mapping(box(LON0 - 0.02, LAT0 - 0.015, LON0 + 0.02, LAT0 + 0.015)),
            "planned_lateral": {"azimuth_deg": 0.3}, "window_used": [12277.0, None],
            "window_source": "declared (NOT local — correlate)", "rights": "12,277 ft -> COE",
            "attributes": {"Type": "DSU"}, **kw}


class FakeNarvi:
    """Rows on a lattice: `xs[bench]` per call; offset_ft pins shift that bench."""

    def __init__(self, xs: dict[str, list[float]], save_xs: dict[str, list[float]] | None = None) -> None:
        self.xs, self.save_xs, self.calls = xs, save_xs, []

    def generate(self, parcel, zones, *, setback_ft, spacing_ft, azimuth_deg):
        self.calls.append(zones)
        src = self.save_xs if (self.save_xs and len(self.calls) > 1 and len(zones) > 1) else self.xs
        feats = []
        for z in zones:
            for i, x in enumerate(src[z["formation"]], 1):
                feats.append({"type": "Feature", "geometry": mapping(_line(x)),
                              "properties": {"kind": "leg", "formation": z["formation"],
                                             "well_name": f"{z['formation']}-{i:02d}", "gunbarrel_x_ft": x,
                                             "completed_lateral_ft": 9000.0}})
        return {"geojson": {"features": feats}}


def _ub(xs: list[float], tvd: float, sp: float = 1320.0, rules: list[str] | None = None) -> dict[str, Any]:
    return {"gate2": {"source": "generate"}, "tvd_ft": tvd, "spacing_ft": sp, "row_rules": rules or [],
            "locations": [{"id": f"gen-{i}", "wkt": _line(x).wkt} for i, x in enumerate(xs)]}


def test_slug_matches_narvi_deal_id():
    assert handoff.slug("rally_caps_dsu_35_26") == "rally_caps_dsu_35_26"
    assert handoff.slug("VaULt 2.0 DSU 2-11 (Bone Spring)") == "vault_2_0_dsu_2_11_bone_spring"
    assert handoff.scenario_key("Rally Caps DSU 1-12") == {"deal_id": "rally_caps_dsu_1_12",
                                                           "scenario_id": "plan_rally_caps_dsu_1_12"}


def test_single_bench_row_rules_become_culls():
    nv = FakeNarvi({"WCB_2": [-2200, -1320, -440, 440, 1320, 2200]})
    u = handoff.plan_unit(nv, _unit(), {"WCB_2": _ub([440, 1320, 2200], 12867.0, 880.0, ["3 west-most row(s) dropped"])},
                          330.0)
    assert u["issues"] == [] and u["pins"] == {}
    assert u["body"]["culled_wells"] == ["WCB_2-01", "WCB_2-02", "WCB_2-03"]
    assert [r["status"] for r in u["rows"]].count("kept") == 3
    assert len(nv.calls) == 1                                   # one call: no pin preview needed
    b = u["body"]
    assert b["bench_sources"] == {"WCB_2": "generate"} and b["source_azimuth"] is False
    assert b["categories"] == ["pdp", "pud"] and b["category_overrides"] == {}
    assert b["deal_id"] == "rally_caps_dsu_1_12" and b["scenario_id"] == "plan_rally_caps_dsu_1_12"
    assert b["deal_terms"]["basis"].startswith("land file declared")          # narvi: not yet correlated
    from dealintake.geo import axial_diff
    assert axial_diff(b["params"]["azimuth_deg"], 0.3) < 2.0     # GRID, folded: 0.3 true -> ~179.5


def test_benches_placed_alone_are_pinned_where_reviewed():
    # dossier: each bench generated ALONE; narvi's joint save would stagger WCB_2
    alone = {"WCB_1": [-1320, 0, 1320], "WCB_2": [-1320, 0, 1320]}
    staggered = {"WCB_1": [-1320, 0, 1320], "WCB_2": [-660, 660, 1980]}
    nv = FakeNarvi(alone)
    u = handoff.plan_unit(nv, _unit(), {"WCB_1": _ub([-1320, 0, 1320], 11600.0),
                                        "WCB_2": _ub([-1320, 0, 1320], 12175.0)}, 330.0)
    assert u["issues"] == []
    assert set(u["pins"]) == {"WCB_1", "WCB_2"}
    assert all("offset_ft" in z for z in u["body"]["zones"])
    assert len(nv.calls) == 3                                   # two pin previews + the save recipe
    # without the pin the joint recipe would not reproduce the dossier -> BLOCKED, never silent
    nv2 = FakeNarvi(alone, save_xs=staggered)
    u2 = handoff.plan_unit(nv2, _unit(), {"WCB_1": _ub([-1320, 0, 1320], 11600.0),
                                          "WCB_2": _ub([-1320, 0, 1320], 12175.0)}, 330.0)
    assert any("not in the save recipe" in i for i in u2["issues"])
    assert any(r["status"] == "MISSING" for r in u2["rows"])


def test_match_tolerance():
    from shapely.geometry import shape

    from dealintake.geo import LocalFrame
    fr = LocalFrame.around(shape(_unit()["geometry"]))
    t = [{"wkt": _line(0).wkt}]
    hit, extra, miss = handoff.match_legs(t, [{"geom": _line(30), "well_name": "A"}], fr)
    assert 0 in hit and not miss
    hit, extra, miss = handoff.match_legs(t, [{"geom": _line(200), "well_name": "A"}], fr)
    assert miss == [0] and len(extra) == 1


def _sig() -> tuple[dict[str, Any], dict[str, Any]]:
    def unit(lb, lat):
        return {"label": lb, "dsu_name": lb[-4:], "geometry": mapping(box(LON0, lat, LON0 + 0.01, lat + 0.01))}
    prop = {"units": [unit("u_north", 32.2), unit("u_south", 31.8), unit("u_up", 32.0)]}
    grp = lambda us, n: {"name": " + ".join(us), "units": us, "order_reason": "nearest",
                         "tc_wells": [{"api10": f"42{i:08d}"} for i in range(n)],
                         "tc_preview": {"oil": {"qi": 90.0, "Di": 2.3, "b": 1.1, "Df": 0.08, "eur_per_unit": 60000.0}}}
    sig = {"config_version": 10, "benches": {
        "WCB_2": {"key": "WCB_2", "bench": "WCB_2", "tvd_ft": 12100.0,
                  "units": {"u_north": {"role": "base"}, "u_south": {"role": "base"}},
                  "tc_groups": [grp(["u_north"], 12), grp(["u_south"], 20)]},
        "WCB_1": {"key": "WCB_1", "bench": "WCB_1", "tvd_ft": 11600.0,
                  "units": {"u_up": {"role": "upside"}}, "tc_groups": [grp(["u_up"], 8)]},
    }}
    return sig, prop


def test_curves_zones_tab_order_and_scope(tmp_path):
    sig, prop = _sig()
    cs = handoff.plan_curves(sig, prop, tmp_path)
    assert [c["name"] for c in cs] == ["WCB_1", "WCB_2_North", "WCB_2_South"]     # shallow -> deep
    north = cs[1]
    assert north["zone"] == {"zone_name": "WCB_2_North", "reserve_category": "PUD", "benches": ["WCB_2"],
                             "scenario_scope": [{"deal_id": "u_north", "scenario_id": "plan_u_north"}]}
    sb = north["save_body"]
    assert sb["alignment_method"] == "peak_ramp" and sb["normalization_basis"] == "per_lateral_ft"
    assert "stream_modes" not in sb                                    # Arps on every stream
    assert len(sb["included_api10s"]) == 12 and sb["provenance"]["formations"] == ["WCB_2"]
    assert cs[0]["reserve_category"] == "UPSIDE"


def test_mixed_roles_block_the_curve(tmp_path):
    sig, prop = _sig()
    B = sig["benches"]["WCB_2"]
    B["units"]["u_south"]["role"] = "upside"
    B["tc_groups"] = [{**B["tc_groups"][0], "units": ["u_north", "u_south"]}]
    (c,) = [c for c in handoff.plan_curves(sig, prop, tmp_path) if c["bench"] == "WCB_2"]
    assert c["issues"] and "roles" in c["issues"][0]
