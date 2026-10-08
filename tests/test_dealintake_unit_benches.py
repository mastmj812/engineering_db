"""Per-unit bench seeding: formation-phrase rights, edge tie-breaks, lateral classes."""

import pytest

pytest.importorskip("shapely")
pytest.importorskip("yaml")

from dealintake import strat, unit_benches
from dealintake.pipeline import lateral_classes

COL = strat.load()


def _b(text, basin="delaware"):
    return strat.parse_bound(text, COL, basin)


def test_top_of_bone_spring_to_top_of_wolfcamp_is_ava0_through_bs3s():
    # Michael, 2026-09-21: Avalon sits inside Bone Spring; WCXY is the top of Wolfcamp.
    got = strat.allowed_benches(_b("Top of Bone Spring Formation"), _b("Top of Wolfcamp Formation"), COL, "delaware")
    assert got == ["AVA_0", "AVA_1", "AVA_2", "BS1_S", "BS2_C", "BS2_S", "BS3_C", "BS3_S"]


def test_top_to_base_of_wolfcamp_and_open_ends():
    assert strat.allowed_benches(_b("Top of Wolfcamp Formation"), _b("Base of Wolfcamp Formation"), COL, "delaware") == [
        "WCXY", "WCA_1", "WCA_2", "WCB_1", "WCB_2", "WCC", "WCD"]
    # one formation bound + COE: open below
    assert strat.allowed_benches(_b("Base of Wolfcamp"), _b("COE"), COL, "delaware") == ["STRN", "BRNT", "MISS", "WDFD"]
    # purely numeric / open windows are NOT resolved by order
    assert strat.allowed_benches(_b("Surface"), _b("11,985"), COL, "delaware") is None


def test_bound_kinds():
    assert _b("COE").kind == "coe" and _b("Surface").kind == "surface" and _b(None).kind == "missing"
    assert _b("12,224'").depth_ft == 12224.0
    d = _b("Top of 3rd Bone Spring Sand")                     # digit in a formation phrase is not a depth
    assert (d.kind, d.edge, d.group) == ("strat", "top", "bs3")
    assert _b("Base of the Wolfcamp B").group == "wolfcamp_b"  # longest alias wins over "wolfcamp"
    assert _b("see lease").kind == "unknown"
    assert _b("Top of Spraberry", "midland").group == "spraberry"


def test_basin_inference_and_name_hint():
    assert strat.infer_basin(["BS3_S", "WCA_1", "WCB_1"]) == "delaware"
    assert strat.infer_basin(["LSSH", "WCA_1"]) == "midland"
    assert strat.infer_basin(["WCA_1", "WCB_1"]) is None
    assert strat.name_hint("2-11 (WCB)", COL, "delaware") == ("wolfcamp_b", ["WCB_1", "WCB_2"])
    assert strat.name_hint("44-45 N2 (Bone Spring)", COL, "delaware")[0] == "bone_spring"
    assert strat.name_hint("14-3", COL, "delaware") is None


def _row(bench, tvd, wells, status, margin=None, note=None):
    return {"bench": bench, "median_tvd_ft": tvd, "wells": wells, "status": status, "margin_ft": margin, "note": note}


def test_seed_numeric_window_uses_dsu_name_on_edge_benches():
    # VaULt "2-11 (WCB)", 12,224 ft -> COE
    rows = [_row("BS3_S", 11742, 13, "out", -482), _row("WCA_1", 12125, 23, "edge", -99),
            _row("WCB_1", 12394, 10, "edge", 170), _row("WCB_2", 12753, 4, "in_window", 529),
            _row("WDFD", 18000, 1, "in_window", 5776, "[thin control: 1 < 3 real-depth wells -> bench dropped]"),
            _row("OTHER", 2768, 2, "out", -9456)]
    seed = unit_benches.seed_unit("2-11 (WCB)", _b("12,224"), _b("COE"), rows, COL, "delaware")
    assert {b: v["evaluate"] for b, v in seed.items()} == {
        "BS3_S": False, "WCA_1": False, "WCB_1": True, "WCB_2": True, "WDFD": False}
    assert "DSU name -> wolfcamp_b" in seed["WCB_1"]["why"] and "thin control" in seed["WDFD"]["why"]


def test_seed_edge_without_name_hint_follows_the_side():
    rows = [_row("WCA_2", 11451, 18, "edge", -38), _row("WCB_1", 11640, 14, "edge", 152)]
    seed = unit_benches.seed_unit("14-3", _b("11,489"), _b("COE"), rows, COL, "delaware")
    assert (seed["WCA_2"]["evaluate"], seed["WCB_1"]["evaluate"]) == (False, True)


def test_seed_formation_phrase_rights():
    # VaULt "25-26-27 (Bone Spring)": Top of Bone Spring -> Top of Wolfcamp, no numeric window
    rows = [_row("BS1_S", 9872, 4, "no_window"), _row("BS3_S", 11508, 29, "no_window"),
            _row("WCA_1", 11696, 13, "no_window"), _row("BS2_S", 11106, 2, "no_window", None, "[thin control: 2 < 3]")]
    seed = unit_benches.seed_unit("25-26-27 (Bone Spring)", _b("Top of Bone Spring Formation"),
                                  _b("Top of Wolfcamp Formation"), rows, COL, "delaware")
    assert seed["BS1_S"]["evaluate"] and seed["BS3_S"]["evaluate"]
    assert not seed["WCA_1"]["evaluate"] and "stratigraphic order" in seed["WCA_1"]["why"]
    assert not seed["BS2_S"]["evaluate"]
    # allowed by order but never seen locally: listed, off
    assert seed["AVA_0"] == {"evaluate": False, "why": seed["AVA_0"]["why"]} and "no local offset" in seed["AVA_0"]["why"]


def _prop():
    return {"config_version": 4, "strat_version": 1, "units": [{
        "label": "u1", "dsu_name": "2-11 (WCB)", "rights": "12,224 ft -> COE (unbounded below)",
        "planned_lateral": {"median_ft": 9912.0, "min_ft": 3969.0, "max_ft": 9912.0, "azimuth_deg": 162.5,
                            "azimuth_source": "neighborhood grid"},
        "bench_seed": {"WCA_1": {"evaluate": False, "why": 'edge: "quoted" text'},
                       "WCB_1": {"evaluate": True, "why": "in"}}}]}


def test_benches_yaml_round_trip_and_reviewer_edit(tmp_path):
    prop = _prop()
    (tmp_path / unit_benches.FILENAME).write_text(unit_benches.render(prop), encoding="utf-8")
    plan = unit_benches.read(tmp_path, prop)
    assert plan["u1"] == {"benches": ["WCB_1"], "planned_lateral_ft": 9912.0, "seed_benches": ["WCB_1"], "edited": False,
                          "bench_opts": {"WCB_1": {}}, "min_leg_ft": None}

    text = (tmp_path / unit_benches.FILENAME).read_text(encoding="utf-8")
    text = text.replace("WCA_1:  {evaluate: false", "WCA_1:  {evaluate: true ").replace(
        "planned_lateral_ft: 9912", "planned_lateral_ft: 10200")
    (tmp_path / unit_benches.FILENAME).write_text(text, encoding="utf-8")
    plan = unit_benches.read(tmp_path, prop)
    assert plan["u1"]["benches"] == ["WCA_1", "WCB_1"] and plan["u1"]["planned_lateral_ft"] == 10200.0
    assert plan["u1"]["edited"] is True


def test_benches_yaml_rejects_unknown_unit_and_missing_file(tmp_path):
    prop = _prop()
    with pytest.raises(FileNotFoundError):
        unit_benches.read(tmp_path, prop)
    (tmp_path / unit_benches.FILENAME).write_text("units:\n  nope:\n    benches: {}\n", encoding="utf-8")
    with pytest.raises(ValueError, match="unknown unit"):
        unit_benches.read(tmp_path, prop)


def test_lateral_classes_vault():
    ll = {"a": 9853, "b": 9912, "c": 9900, "d": 12535, "e": 12664, "f": 15144, "g": 17670, "h": 4620}
    assert lateral_classes(ll, 1.10) == [["h"], ["a", "c", "b"], ["d", "e"], ["f"], ["g"]]
    assert lateral_classes({"x": 9883, "y": 10488}, 1.10) == [["x", "y"]]
    assert lateral_classes({}, 1.10) == []


def test_review_page_renders_from_proposal(tmp_path):
    """review.html is the reviewer's surface: one panel per DSU, no DB needed."""
    import json

    pytest.importorskip("matplotlib")
    from dealintake.render import review

    poly = {"type": "Polygon", "coordinates": [[[-103.32, 31.73], [-103.30, 31.73], [-103.30, 31.76], [-103.32, 31.76], [-103.32, 31.73]]]}
    unit = {
        "label": "u1", "dsu_name": "2-11 (WCB)", "area_ac": 625.0, "geometry": poly, "basin": "delaware",
        "rights": "12,224 ft -> COE (unbounded below)", "declared_window_raw": {"Min_Depth": "12,224", "Max_Depth": "COE"},
        "bounds": {"min": {"kind": "depth", "depth_ft": 12224.0}, "max": {"kind": "coe"}},
        "planned_lateral": {"median_ft": 9912.0, "min_ft": 3969.0, "max_ft": 9912.0, "azimuth_deg": 162.5,
                            "azimuth_source": "neighborhood grid"},
        "bench_proposal": [{"bench": "WCA_1", "median_tvd_ft": 12125.0, "wells": 23, "status": "edge", "margin_ft": -99, "note": None},
                           {"bench": "WCB_1", "median_tvd_ft": 12394.0, "wells": 10, "status": "edge", "margin_ft": 170, "note": None}],
        "bench_seed": {"WCA_1": {"evaluate": False, "why": "edge: 99 ft OUTSIDE ..."},
                       "WCB_1": {"evaluate": True, "why": "edge: 170 ft inside ..."}},
        "gate2": {"WCB_1": {"pud_inside": 2, "pud_crossing": 0, "res_inside": 0, "res_crossing": 0, "source": "novi", "reason": "x"}},
        "pdp_in_unit": [{"bench": "WCA_1"}], "offset_pdp_3mi": {"WCA_1": 64, "WCB_1": 14},
    }
    twin = dict(unit, label="u2", dsu_name="2-11 (Bone Spring)", bench_seed={}, gate2={})
    prop = {"deal_file": "VaULt.gpkg", "config_version": 4, "strat_version": 1, "snapshot": {"intel_vintage_date": "2026-09-30"},
            "units": [unit, twin]}
    (tmp_path / "proposal.json").write_text(json.dumps(prop), encoding="utf-8")
    (tmp_path / "review_geoms.json").write_text(json.dumps({"u1": {
        "pdp": [{"api10": "1", "bench": "WCA_1", "wkt": "LINESTRING(-103.315 31.735, -103.312 31.755)"}],
        "novi": [{"stick_id": 5, "bench": "WCB_1", "category": "PUD", "relation": "inside",
                  "wkt": "LINESTRING(-103.31 31.735, -103.307 31.755)"}]}}), encoding="utf-8")
    unit["gunbarrel"] = {"azimuth_deg": 162.5, "cross_extent_ft": [-1300, 1300], "bench_tvd_ft": {"WCB_1": 12394.0},
                         "existing": [{"api10": "1", "bench": "WCA_1", "offset_ft": -400, "tvd_ft": 12125.0, "inside": True}],
                         "novi": [{"stick_id": 5, "bench": "WCB_1", "offset_ft": 200, "tvd_ft": 12390.0, "relation": "inside"}],
                         "planned": {"WCB_1": {"tvd_ft": 12394.0, "spacing_ft": 1320.0, "spacing_source": "Novi BASE_CASE",
                                               "offsets_ft": [-660, 660], "lateral_ft": [9900, 9900]}}}
    (tmp_path / "proposal.json").write_text(json.dumps(prop), encoding="utf-8")
    text = review.render(tmp_path).read_text(encoding="utf-8")
    assert text.count("<svg") == 6                       # overview + (map + strip) x 2 units + 1 gunbarrel
    assert "gunbarrel" in text and "2 sticks @ 1,320 ft" in text
    # Novi sticks are not drawn; the legend carries only existing benches + proposed rows
    assert "Novi BASE_CASE stick" not in text.split("gunbarrel", 1)[1][:20000]
    assert "same footprint as 2-11 (Bone Spring)" in text and "12,224' declared" in text
    assert "None" not in text and ">ON<" in text and ">off<" in text


def test_tract_windows_are_flagged_never_used():
    from dealintake.pipeline import tract_check

    lo, hi = _b("Top of Bone Spring Formation"), _b("Top of Wolfcamp Formation")      # the DSU row (44-45 S2)
    tracts = [{"attributes": {"Section": "44", "Block": "20", "Aliquot": "N2N2S2", "Min_Depth": "Surface", "Max_Depth": "COE", "Net_Ac": 150.2}},
              {"attributes": {"Section": "44", "Block": "20", "Aliquot": "S2S2", "Min_Depth": "Surface", "Max_Depth": "11,950'", "Net_Ac": 170.2}},
              {"attributes": {"Section": "45", "Block": "20", "Aliquot": "SW", "Min_Depth": "Top of Bone Spring", "Max_Depth": "Top of Wolfcamp"}}]
    out = tract_check(tracts, lo, hi, COL, "delaware")
    assert [t["disagrees"] for t in out] == [True, True, False]
    assert out[1]["rights"] == "Surface -> 11,950 ft" and out[0]["tract"] == "44 20 N2N2S2"


def test_twin_dsu_tracts_are_not_disagreements():
    from dealintake.pipeline import resolve_twin_tracts

    poly = {"type": "Polygon", "coordinates": [[[0, 0], [1, 0], [1, 1], [0, 1], [0, 0]]]}
    upper = {"label": "bs", "dsu_name": "2-11 (Bone Spring)", "geometry": poly, "rights": "Surface -> 11,985 ft",
             "declared_window_raw": {"Min_Depth": "Surface", "Max_Depth": "11,985"},
             "tract_windows": [{"tract": "a", "raw": {"Min_Depth": "12,224'", "Max_Depth": "COE"}, "rights": "12,224 ft -> COE", "disagrees": True},
                               {"tract": "b", "raw": {"Min_Depth": "Surface", "Max_Depth": "11,827'"}, "rights": "Surface -> 11,827 ft", "disagrees": True}]}
    lower = {"label": "wcb", "dsu_name": "2-11 (WCB)", "geometry": poly, "rights": "12,224 ft -> COE",
             "declared_window_raw": {"Min_Depth": "12,224", "Max_Depth": "COE"}, "tract_windows": []}
    resolve_twin_tracts([upper, lower])
    a, b = upper["tract_windows"]
    assert a["disagrees"] is False and a["twin"] == "2-11 (WCB)"      # the twin's paper, not a conflict
    assert b["disagrees"] is True and "twin" not in b                   # a genuinely different window


def test_reviewed_benches_reads_the_reviewer_file(tmp_path):
    assert unit_benches.reviewed_benches(tmp_path) == {}
    prop = _prop()
    (tmp_path / unit_benches.FILENAME).write_text(unit_benches.render(prop), encoding="utf-8")
    assert unit_benches.reviewed_benches(tmp_path) == {"u1": {"benches": ["WCB_1"], "bench_opts": {"WCB_1": {}}, "min_leg_ft": None}}


def test_reviewer_bench_options_round_trip(tmp_path):
    """The VaULt walkthrough keys: tvd_ft, spacing_ft, n_wells, keep_side, drop_<side>_rows, role, min_leg_ft."""
    prop = _prop()
    text = unit_benches.render(prop).replace(
        'WCA_1:  {evaluate: false',
        'WCA_1:  {evaluate: true , tvd_ft: 10333, spacing_ft: 1320, n_wells: 4, keep_side: west, drop_east_rows: 2, role: upside')
    text = text.replace("planned_lateral_ft: 9912", "min_leg_ft: 7000\n    planned_lateral_ft: 9900")
    (tmp_path / unit_benches.FILENAME).write_text(text, encoding="utf-8")
    plan = unit_benches.read(tmp_path, prop)
    assert plan["u1"]["benches"] == ["WCA_1", "WCB_1"] and plan["u1"]["min_leg_ft"] == 7000.0 and plan["u1"]["edited"]
    assert plan["u1"]["bench_opts"]["WCA_1"] == {"tvd_ft": 10333.0, "spacing_ft": 1320.0, "n_wells": 4, "keep_side": "west",
                                                 "drop_east_rows": 2, "role": "upside"}
    assert plan["u1"]["bench_opts"]["WCB_1"] == {}
    rv = unit_benches.reviewed_benches(tmp_path)
    assert rv["u1"]["benches"] == ["WCA_1", "WCB_1"] and rv["u1"]["bench_opts"]["WCA_1"]["tvd_ft"] == 10333.0

    for bad in ("tvd_ft: -5", "n_wells: 2.5", "keep_side: up", "role: maybe", "drop_east_rows: -1"):
        (tmp_path / unit_benches.FILENAME).write_text(
            unit_benches.render(prop).replace("WCB_1:  {evaluate: true ", f"WCB_1:  {{evaluate: true , {bad}"), encoding="utf-8")
        with pytest.raises(ValueError):
            unit_benches.read(tmp_path, prop)


def test_row_rules_on_a_162_deg_plan():
    from dealintake.geo import apply_row_rules, side_sign

    az = 162.3                                   # VaULt: +offset points 72 deg (ENE) -> east is + (rule v2)
    assert side_sign("east", az) == 1 and side_sign("west", az) == -1
    assert side_sign("north", 72.2) == 1         # a 72 deg plan: +offset points 342 deg (NNW) -> north is +
    assert side_sign("east", 72.2) == -1
    rows = [{"offset_ft": o, "lateral_ft": 12500} for o in (-1741, -421, 899, 2219)]
    kept, notes = apply_row_rules(rows, az, drop_rows={"east": 3})
    assert [r["offset_ft"] for r in kept] == [-1741] and "3 east-most" in notes[0]
    kept, _ = apply_row_rules(rows, az, keep_side="west")
    assert [r["offset_ft"] for r in kept] == [-1741, -421]
    kept, _ = apply_row_rules(rows, az, n_wells=2)
    assert [r["offset_ft"] for r in kept] == [-421, 899]           # outermost trimmed alternately
    rows[0]["lateral_ft"] = 4620
    kept, notes = apply_row_rules(rows, az, min_leg_ft=7000)
    assert len(kept) == 3 and "shorter than 7,000 ft" in notes[0]


def test_winerack_key(tmp_path):
    prop = _prop()
    (tmp_path / unit_benches.FILENAME).write_text(
        unit_benches.render(prop).replace("WCB_1:  {evaluate: true ", "WCB_1:  {evaluate: true , winerack: true, spacing_ft: 1320"),
        encoding="utf-8")
    assert unit_benches.read(tmp_path, prop)["u1"]["bench_opts"]["WCB_1"] == {"spacing_ft": 1320.0, "winerack": True}
    (tmp_path / unit_benches.FILENAME).write_text(
        unit_benches.render(prop).replace("WCB_1:  {evaluate: true ", "WCB_1:  {evaluate: true , winerack: yes please"),
        encoding="utf-8")
    with pytest.raises(ValueError):
        unit_benches.read(tmp_path, prop)


def test_winerack_legs_anchor_then_pinned_shift():
    """Staggered benches: each placed alone first; the bench keeping the most rows
    anchors (tie -> deeper), the other is PINNED half a spacing off the anchor's
    lattice (Michael 2026-10-08, Rally Caps 1-12) — not narvi's shallow-leads stagger."""
    from shapely.geometry import LineString, box, mapping

    from dealintake.pipeline import winerack_legs

    calls = []

    class _Narvi:
        def generate(self, parcel, zones, **kw):
            calls.append((zones, kw))
            feats = [{"type": "Feature", "geometry": mapping(LineString([(x, 0), (x, 1)])),
                      "properties": {"kind": "leg", "formation": z["formation"], "completed_lateral_ft": 9900,
                                     "gunbarrel_x_ft": 100.0 * x}}
                     for i, z in enumerate(zones) for x in (i, i + 0.5)]
            return {"geojson": {"features": feats}}

    unit = box(-103.5, 31.5, -103.49, 31.53)
    got, pins = winerack_legs(_Narvi(), unit, 41.3, {"WCB_2": (11650.0, 1320.0), "WCB_1": (11863.0, 1320.0)},
                              setback_ft=330)
    assert all(len(z) == 1 for z, _ in calls) and len(calls) == 3      # two alone + one pinned
    assert calls[0][1]["spacing_ft"] == 1320.0 and calls[0][1]["setback_ft"] == 330
    assert set(pins) == {"WCB_1", "WCB_2"} and pins["WCB_2"] - pins["WCB_1"] == 660.0   # deeper WCB_1 anchors
    assert calls[-1][0][0]["formation"] == "WCB_2" and calls[-1][0][0]["offset_ft"] == pins["WCB_2"]
    assert {b: len(v) for b, v in got.items()} == {"WCB_2": 2, "WCB_1": 2}


def test_gunbarrel_reads_west_to_east():
    from dealintake.render.review import cross_section_ends

    # sign rule v2: the frame itself reads W->E / S->N, so nothing ever flips
    assert cross_section_ends(0.3) == (False, "W", "E")      # +offset = east
    assert cross_section_ends(162.2) == (False, "W", "E")    # +offset = ENE (36-37 now drawn W->E as stored)
    assert cross_section_ends(41.3) == (False, "W", "E")     # +offset = SE -> east-ish
    assert cross_section_ends(90.0) == (False, "S", "N")     # E-W plan: +offset = north
    assert cross_section_ends(270.0) == (False, "S", "N")
    assert cross_section_ends(72.2) == (False, "S", "N")     # VaULt: +offset = NNW


def test_reviewer_pattern_overrides_novi_location_source():
    """Rally Caps 2-44: a reviewer pattern on a bench Gate 2 would source from
    Novi means GENERATE; no pattern keeps Novi; a generate bench is untouched."""
    from dealintake.pipeline import location_source

    novi = {"source": "novi", "reason": "all BASE_CASE sticks inside, oriented and sized like the plan", "pud_inside": 1}
    got = location_source(novi, {"tvd_ft": 11150.0, "spacing_ft": 1320.0, "n_wells": 4})
    assert got["source"] == "generate" and "tvd_ft, spacing_ft, n_wells" in got["reason"]
    assert got["novi_reason"] == novi["reason"]
    assert location_source(novi, {}) is novi
    assert location_source(novi, {"role": "upside"}) is novi           # role is not a pattern
    gen = {"source": "generate", "reason": "no BASE_CASE stick inside"}
    assert location_source(gen, {"n_wells": 4}) is gen
