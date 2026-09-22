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
    assert plan["u1"] == {"benches": ["WCB_1"], "planned_lateral_ft": 9912.0, "seed_benches": ["WCB_1"], "edited": False}

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
    text = review.render(tmp_path).read_text(encoding="utf-8")
    assert text.count("<svg") == 5                       # overview + (map + strip) x 2 units
    assert "same footprint as 2-11 (Bone Spring)" in text and "12,224' declared" in text
    assert "None" not in text and ">ON<" in text and ">off<" in text
