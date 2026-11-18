"""BOX sticks phase 5a: the reconciliation predicate's Python reference (scripts.box_sticks_phase5a.judge) on synthetic
rows, and static checks that the draft SQL states the same thresholds. DB-free."""
from __future__ import annotations

from pathlib import Path

import pandas as pd
import shapely
from shapely.geometry import LineString, MultiLineString

from scripts import box_sticks_phase5a as p5

ROOT = Path(__file__).resolve().parent.parent
DOC = ROOT / "docs" / "box_sticks" / "phase5a-2026-11-18"
FT = 0.3048
GEN = {b: {"same_dv_ft": 150.0, "same_dh_ft": 400.0, "min_overlap": 0.3, "stacked": [[-250.0, -150.0, 300.0], [150.0, 350.0, 300.0]]} for b in p5.BASINS}


def _line(x_ft: float, y0_ft: float = 0.0, y1_ft: float = 10000.0) -> LineString:
    return LineString([(x_ft * FT, y0_ft * FT), (x_ft * FT, y1_ft * FT)])


def _sticks(rows: list[dict]) -> pd.DataFrame:
    d = pd.DataFrame(rows)
    d["basin"], d["well_type"] = "delaware", ["uturn" if len(g.geoms) == 2 else "single" for g in d["geom"]]
    d["n_legs"] = [len(g.geoms) for g in d["geom"]]
    return d


def _wells(rows: list[dict]) -> pd.DataFrame:
    base = {"basin": "delaware", "state_code": 42, "well_status": "Active", "spud_date": "2020-01-01", "fp": "2020-06-01", "planned": False,
            "tvd_ft": 10050, "lat_tvd_p50_ft": None, "is_uturn": False, "code": "WCA_1"}
    d = pd.DataFrame([base | r for r in rows])
    d["wkt"] = shapely.to_wkt(d.pop("geom").to_numpy())
    return p5.classify(d)


def _status(sticks: pd.DataFrame, wells: pd.DataFrame, mirror: dict | None = None) -> pd.DataFrame:
    return p5.judge(sticks, wells, GEN, mirror)[0].set_index("key")


def test_classes_and_depth_evidence():
    w = _wells([
        {"api10": "p", "geom": _line(0)},
        {"api10": "spud", "geom": _line(0), "fp": None, "well_status": "Spud"},
        {"api10": "permit", "geom": _line(0), "fp": None, "spud_date": None, "well_status": "Permit Approved"},
        {"api10": "permit_spud", "geom": _line(0), "fp": None, "well_status": "Permit Approved"},
        {"api10": "cancelled", "geom": _line(0), "fp": None, "well_status": "Permit Cancelled"},
        {"api10": "inactive", "geom": _line(0), "fp": None, "well_status": "Inactive"},
        {"api10": "round", "geom": _line(0), "tvd_ft": 10000},
        {"api10": "planned", "geom": _line(0), "planned": True},
        {"api10": "survey", "geom": _line(0), "tvd_ft": 10000, "lat_tvd_p50_ft": 10012.5},
    ]).set_index("api10")
    assert pd.isna(w.loc["cancelled", "cls"])
    assert w["cls"].dropna().to_dict() == {"p": "producing", "spud": "drilled", "permit": "permit", "permit_spud": "drilled",
                                  "inactive": "drilled", "round": "producing", "planned": "producing", "survey": "producing"}
    assert w.loc["p", "depth_ft"] == 10050 and w.loc["survey", "depth_ft"] == 10012.5
    assert pd.isna(w.loc["round", "depth_ft"]) and pd.isna(w.loc["planned", "depth_ft"])      # never depth evidence


def test_match_conflict_and_open():
    s = _sticks([{"key": k, "pad_id": 1, "bench": "WCA_1", "target_tvd_ft": 10000.0, "geom": MultiLineString([_line(x)])}
                 for k, x in (("on", 0), ("half", 3000), ("far", 6000))])
    w = _wells([{"api10": "a", "geom": _line(50)},                                   # 50 ft from `on`, full length
                {"api10": "b", "geom": _line(3000, 0, 3000)},                        # covers about 30 % of `half`
                {"api10": "c", "geom": _line(6000 + 700)}])                          # 700 ft from `far`
    r = _status(s, w)
    assert r.loc["on", "status"] == "producing" and r.loc["on", "matched_api10"] == "a"
    assert r.loc["half", "status"] == "conflict"
    assert r.loc["far", "status"] == "open" and not r.loc["far", "crowded"]


def test_depth_rule_and_planned_basis():
    s = _sticks([{"key": "s", "pad_id": 1, "bench": "WCA_1", "target_tvd_ft": 10000.0, "geom": MultiLineString([_line(0)])}])
    same_code_far = _wells([{"api10": "a", "geom": _line(0), "tvd_ft": 10450}])                    # same code, 450 ft
    other_code_far = _wells([{"api10": "a", "geom": _line(0), "tvd_ft": 10450, "code": "WCB_1"}])  # other code, 450 ft
    other_code_near = _wells([{"api10": "a", "geom": _line(0), "tvd_ft": 10120, "code": "WCB_1"}])  # other code, 120 ft
    no_depth_family = _wells([{"api10": "a", "geom": _line(0), "planned": True, "code": "WCA_2"}])
    no_depth_other = _wells([{"api10": "a", "geom": _line(0), "planned": True, "code": "BS3_S"}])
    assert _status(s, same_code_far).loc["s", "status"] == "producing"
    assert _status(s, other_code_far).loc["s", "status"] == "open"
    assert _status(s, other_code_near).loc["s", "status"] == "producing"
    r = _status(s, no_depth_family).loc["s"]
    assert r["status"] == "producing" and r["match_basis"] == "planned"
    assert _status(s, no_depth_other).loc["s", "status"] == "open"


def test_permit_only_flags_and_never_conflicts():
    s = _sticks([{"key": "s", "pad_id": 1, "bench": "WCA_1", "target_tvd_ft": 10000.0, "geom": MultiLineString([_line(0)])}])
    permit = {"api10": "p", "geom": _line(0), "fp": None, "spud_date": None, "well_status": "Permit Approved"}
    r = _status(s, _wells([permit, permit | {"api10": "p2"}])).loc["s"]
    assert r["status"] == "permitted" and r["permit_api10"] in ("p", "p2") and not r["crowded"]
    r = _status(s, _wells([permit, {"api10": "w", "geom": _line(20)}])).loc["s"]
    assert r["status"] == "producing"                                                 # a real well outranks the permit


def test_uturn_legs_are_judged_one_by_one():
    s = _sticks([{"key": "u", "pad_id": 1, "bench": "WCA_1", "target_tvd_ft": 10000.0, "geom": MultiLineString([_line(0, 0, 5000), _line(1200, 0, 5000)])}])
    one = _status(s, _wells([{"api10": "a", "geom": _line(0, 0, 5000)}])).loc["u"]
    assert one["status"] == "producing" and one["legs_matched"] == 1                  # one leg takes the stick out
    both = _status(s, _wells([{"api10": "a", "geom": _line(0, 0, 5000)}, {"api10": "b", "geom": _line(1200, 0, 5000), "fp": None, "well_status": "Spud"}])).loc["u"]
    assert both["legs_matched"] == 2 and both["status"] == "drilled"                  # producing only when every matched leg produces


def test_crowded_follows_the_set_envelope():
    s = _sticks([{"key": k, "pad_id": 1, "bench": "WCA_1", "target_tvd_ft": 10000.0, "geom": MultiLineString([_line(x)])} for k, x in (("s", 0),)])
    for x_ft, tvd, code, crowded in ((350, 10050, "WCA_1", True),       # same landing, inside 400 ft
                                     (450, 10050, "WCA_1", False),      # same landing, outside 400 ft
                                     (250, 10301, "WCB_1", True),       # stacked 150 to 350 ft deeper, inside 300 ft
                                     (350, 10301, "WCB_1", False),      # stacked, outside 300 ft
                                     (250, 10601, "WCB_1", False)):     # deeper than every rectangle
        for mirror in (None, {"codev": set(), "landing": {}}):
            r = _status(s, _wells([{"api10": "w", "geom": _line(x_ft), "tvd_ft": tvd, "code": code}]), mirror).loc["s"]
            assert r["status"] == "open" and bool(r["crowded"]) is crowded, (x_ft, tvd, mirror)


def test_variant_b_mirrors_the_generator():
    s = _sticks([{"key": "s", "pad_id": 7, "bench": "WCA_1", "target_tvd_ft": 10000.0, "geom": MultiLineString([_line(0)])}])
    wca2 = _wells([{"api10": "a", "geom": _line(0), "tvd_ft": 10090, "code": "WCA_2"}])
    assert _status(s, wca2).loc["s", "status"] == "producing"                                         # A: within 150 ft whatever the tag
    assert _status(s, wca2, {"codev": {7}, "landing": {}}).loc["s", "status"] == "open"               # B: co-developed DSU, no test between the members
    assert _status(s, wca2, {"codev": set(), "landing": {}}).loc["s", "status"] == "producing"        # B elsewhere: unchanged
    no_depth = _wells([{"api10": "a", "geom": _line(0), "planned": True, "code": "WCA_2"}])
    assert _status(s, no_depth, {"codev": set(), "landing": {(7, "WCA_2"): 10400.0}}).loc["s", "status"] == "open"   # taken at its own bench's landing
    assert _status(s, no_depth, {"codev": set(), "landing": {}}).loc["s", "status"] == "producing"                   # no landing there: family


def test_draft_sql_states_the_same_thresholds():
    sql = (DOC / "predicate_draft.sql").read_text(encoding="utf-8")
    assert ", 46)" in sql and p5.CORRIDOR_M == 46.0
    assert "<= 500" in sql and "<= 150" in sql and (p5.SAME_CODE_FT, p5.ANY_TAG_FT) == (500.0, 150.0)
    assert ">= 0.5" in sql and ">= 0.2" in sql and (p5.MATCH, p5.CONFLICT) == (0.5, 0.2)
    assert "box_location_stick" not in sql.split("WITH rec", 1)[1].replace("box.location_stick", "")   # reads the table, names no index
    for word in ("INSERT", "UPDATE ", "DELETE", "CREATE ", "DROP ", "REFRESH"):
        assert word not in sql.split("=====\nWITH", 1)[-1], word                      # one read-only SELECT
    ddl = (DOC / "ddl_draft.sql").read_text(encoding="utf-8")
    assert "box." not in "".join(ln for ln in ddl.splitlines() if ln.lstrip().upper().startswith(("CREATE", "ALTER", "INSERT", "GRANT")))
