"""PDP-proximity cull (config v14, Michael 2026-10-19 — PROVISIONAL thresholds). DB-free."""

import copy
import json
from pathlib import Path

import pytest
from shapely import wkt
from shapely.geometry import shape

from dealintake import config as cfgmod
from dealintake import proximity
from dealintake.geo import apply_row_rules
from dealintake.pipeline import leg_rows, preview_and_seed, rule_counter
from dealintake.proximity import ProximityRule
from tests._dealintake_fixtures import line_ft, rect_ft

CFG = cfgmod.load()
PX = CFG.raw["pdp_proximity"]
UNIT = rect_ft(-2640, -5000, 2640, 5000)          # N-S unit, plan azimuth 0 -> +offset = east
OURS = line_ft((0, -4600), (0, 4600))              # our stick, 9,200 ft, landing 10,400 ft
FIXTURE = Path(__file__).resolve().parent / "fixtures" / "dealintake_chevron_proximity.json"


def _w(api10, x, y0, y1, tvd, bench="WCA_2", x1=None):
    return {"api10": api10, "bench": bench, "tvd_ft": tvd, "wkt": line_ft((x, y0), (x if x1 is None else x1, y1)).wkt}


def _check(*producers, tvd=10400.0):
    return ProximityRule(UNIT, 0.0, list(producers), PX).check(OURS, tvd)


def test_config_v14_is_provisional_and_validated():
    assert CFG.version >= 14
    assert (PX["enabled"], PX["vertical_ft"], PX["horizontal_ft"], PX["overlap_min_frac"]) == (True, 300, 800, 0.30)
    assert PX["near_miss_ratio"] == 1.25 and PX["permit_tvd_culls"] is False
    raw = copy.deepcopy(CFG.raw)
    del raw["pdp_proximity"]["horizontal_ft"]
    with pytest.raises(cfgmod.ConfigError, match="pdp_proximity.horizontal_ft"):
        cfgmod.validate(raw)
    text = cfgmod.DEFAULT_PATH.read_text(encoding="utf-8")
    block = text.split("pdp_proximity:", 1)[1].split("edge_trigger:", 1)[0]
    assert block.count("PROVISIONAL") >= 3


def test_parallel_producer_inside_the_envelope_culls():
    r = _check(_w("A", -500, -4500, 4500, 10610))                 # 500 ft hz, 210 ft vt, ~98 % alongside
    (h,) = r["cull"]
    assert (h["api10"], h["dh_ft"], h["dv_ft"]) == ("A", 500, 210) and h["overlap"] >= 0.95
    assert "500 ft hz / 210 ft vt" in h["text"] and r["near"] == [] and r["permit"] == []


def test_a_producer_past_the_end_of_our_stick_never_culls():
    """15-22 WCA_2 row -107: a WCA_2 producer ~100 ft away horizontally and 99 ft
    vertically, but barely touching the unit (1 % in it) — Michael kept the row."""
    r = _check(_w("B", 100, 4500, 9000, 10450))                   # shares 100 ft of our 9,200
    assert r == {"rule": r["rule"], "cull": [], "near": [], "permit": []}


def test_overlap_is_a_share_of_OUR_stick():
    short = _check(_w("S", 400, -4600, -1840, 10510))             # 2,760 of our 9,200 ft = 30 %
    assert short["cull"] and short["cull"][0]["overlap"] == 0.30
    shorter = _check(_w("S", 400, -4600, -2000, 10510))           # 28 %
    assert not shorter["cull"] and not shorter["near"]
    long_ = _check(_w("L", 400, -9000, 9000, 10510))              # producer longer than ours -> 100 %
    assert long_["cull"][0]["overlap"] == 1.0


def test_near_miss_band_flags_and_beyond_it_nothing():
    assert _check(_w("V", 300, -4600, 4600, 10740))["near"]       # 340 ft vt (<= 375): flag, not cull
    assert _check(_w("H", 900, -4600, 4600, 10510))["near"]       # 900 ft hz (<= 1,000)
    far = _check(_w("F", 1100, -4600, 4600, 10510), _w("D", 300, -4600, 4600, 10790))
    assert far["cull"] == far["near"] == []
    edge = _check(_w("E", 799, -4600, 4600, 10700.5))             # 799 ft / 300.5 ft: just outside vt -> near
    assert edge["cull"] == [] and edge["near"]
    assert _check(_w("E", 799, -4600, 4600, 10699.5))["cull"]      # 799 ft / 299.5 ft -> cull


def test_same_bench_producer_culls_and_permit_tvd_only_flags():
    assert _check(_w("SB", -700, -4600, 4600, 10410, bench="WCB_1"), tvd=10400.0)["cull"]
    r = _check(_w("PT", 300, -4600, 4600, 10500.0))              # round-100 TVD = permit depth (rule 10)
    assert r["cull"] == [] and r["permit"][0]["permit"] and "(permit TVD)" in r["permit"][0]["text"]


def test_skewed_producer_uses_the_median_perpendicular_gap():
    """A producer crossing our plan at an angle: the median gap over the shared
    length, not the midpoint offset."""
    r = _check(_w("K", -1500, -4000, 4000, 10510, x1=500))         # x = -500 + 0.25 y
    assert r["cull"] and 470 <= r["cull"][0]["dh_ft"] <= 500


def test_row_rules_cull_before_the_reviewer_caps():
    rows = [{"offset_ft": o, "lateral_ft": 9000} for o in (-1980, -660, 660, 1980)]
    hit = {"rule": "R", "cull": [{"text": "X WCB_1 123 ft hz / 66 ft vt / 75%"}], "near": [], "permit": []}
    rows[0]["proximity"] = hit
    kept, notes = apply_row_rules(rows, 0.0, n_wells=2)
    assert [r["offset_ft"] for r in kept] == [660, 1980]           # n_wells trims the SURVIVORS (3 -> 2)
    assert notes[0].startswith("1 row(s) culled by PDP proximity (R): row -1,980 ft <- X WCB_1")
    kept, _ = apply_row_rules(rows, 0.0, drop_rows={"west": 1})
    assert [r["offset_ft"] for r in kept] == [660, 1980]           # the reviewer's drop acts after the cull
    kept, notes = apply_row_rules(rows, 0.0, cull_pdp=False)
    assert len(kept) == 4 and notes == []


def test_summary_and_flags():
    hit = {"rule": "R", "cull": [{"api10": "X", "bench": "WCB_1", "dh_ft": 1, "dv_ft": 2, "overlap": 0.9, "text": "X"}],
           "near": [], "permit": []}
    nearh = {"rule": "R", "cull": [], "near": [{"api10": "N", "bench": "WCA_2", "dh_ft": 900, "dv_ft": 1, "overlap": 1.0,
                                                 "text": "N"}], "permit": []}
    rows = [{"offset_ft": -100, "proximity": hit}, {"offset_ft": 100, "proximity": nearh}]
    s = proximity.summarize(rows, rows[1:], enabled=True)
    assert (s["n_rows"], s["n_culled"], len(s["near"]), s["would_cull"]) == (2, 1, 1, [])
    assert s["culled"][0]["offset_ft"] == -100
    fl = proximity.flags("u1 WCB_1", s, manual_drops=["drop_west_rows"])
    assert any("near-miss" in f for f in fl) and any("double drop" in f for f in fl)
    off = proximity.summarize(rows, rows, enabled=False)
    assert off["n_culled"] == 0 and len(off["would_cull"]) == 1
    assert any("OVERRIDDEN" in f for f in proximity.flags("u1 WCB_1", off))
    assert any("never culled" in f for f in proximity.flags("u1 WCB_1", off, source="novi"))
    all_gone = proximity.summarize(rows[:1], [], enabled=True)
    assert any("every one of 1 rows culled" in f for f in proximity.flags("u1 WCB_1", all_gone))
    assert proximity.summarize([{"offset_ft": 0}], [], enabled=True) is None
    raw = copy.deepcopy(CFG.raw)
    raw["pdp_proximity"]["enabled"] = False
    assert ProximityRule.build(UNIT, 0.0, [], raw) is None


def test_seed_turns_an_all_culled_bench_off_and_redraws():
    calls = []

    def preview(seed):
        on = [b for b, v in seed.items() if v["evaluate"]]
        calls.append(on)
        s_all = {"rule": "R", "n_rows": 2, "n_culled": 2, "culled": [{"api10": "X", "bench": "BS3_S", "offset_ft": o,
                                                                         "text": "X BS3_S"} for o in (-500, 500)],
                 "would_cull": [], "near": [], "permit": []}
        s_one = {**s_all, "n_culled": 1, "culled": s_all["culled"][:1]}
        planned = {}
        if "WCA_2" in on:
            planned["WCA_2"] = {"tvd_ft": 10690.0, "spacing_ft": 880.0, "offsets_ft": [], "n_generated": 2, "proximity": s_all}
        if "BS2_C" in on:
            planned["BS2_C"] = {"tvd_ft": 9497.0, "spacing_ft": 880.0, "offsets_ft": [500], "n_generated": 2,
                                "proximity": s_one}
        return {"planned": planned}

    seed = {"WCA_2": {"evaluate": True, "why": "local median 10,690 ft"},
            "BS2_C": {"evaluate": True, "why": "local median 9,497 ft"}}
    gun = preview_and_seed(preview, seed, apply_to_seed=True)
    assert calls == [["WCA_2", "BS2_C"], ["BS2_C"]]                # redrawn without the culled bench
    assert seed["WCA_2"]["evaluate"] is False
    assert seed["WCA_2"]["why"].startswith("PDP proximity: all 2 rows within R of X BS3_S (seed: local median")
    assert seed["BS2_C"]["evaluate"] and "PDP proximity culled 1 of 2 rows" in seed["BS2_C"]["why"]
    assert set(gun["culled_benches"]) == {"WCA_2"} and gun["culled_benches"]["WCA_2"]["tvd_ft"] == 10690.0
    seed2 = {"WCA_2": {"evaluate": True, "why": "x"}}
    preview_and_seed(preview, seed2, apply_to_seed=False)          # a reviewer benches.yaml is never touched
    assert seed2 == {"WCA_2": {"evaluate": True, "why": "x"}}


def test_bench_option_validates(tmp_path):
    from dealintake import unit_benches
    assert unit_benches.bench_options({"evaluate": True, "pdp_proximity": False}, "u.B") == {"pdp_proximity": False}
    with pytest.raises(ValueError, match="pdp_proximity must be true or false"):
        unit_benches.bench_options({"evaluate": True, "pdp_proximity": "no"}, "u.B")


# --- Chevron Farmouts 2026-10-19: the rule against Michael's hand calls -----------------

def _chevron():
    return json.loads(FIXTURE.read_text(encoding="utf-8"))["units"]


def _run(u, spacing):
    from dealintake.geo import gunbarrel_frame
    unit = shape(u["geometry"])
    rule = ProximityRule(unit, u["azimuth_deg"], u["pdp"], PX)
    project, _, _ = gunbarrel_frame(unit, u["azimuth_deg"])
    out = {}
    for b, lg in u["legs"][spacing].items():
        legs = [{"geom": wkt.loads(x["wkt"]), "completed_lateral_ft": x["completed_lateral_ft"]} for x in lg]
        rows = leg_rows(legs, project, rule, u["tvd_ft"][b])
        kept, _ = apply_row_rules(rows, u["azimuth_deg"])
        out[b] = (len(rows), [r for r in rows if r not in kept], proximity.summarize(rows, kept, enabled=True))
    return out


def test_chevron_15_22_culls_exactly_the_two_west_rows_michael_dropped():
    """WCA_2 + WCB_1 at 1,320 ft winerack: he dropped the west row of each — 782 ft
    and 122 ft from WCB_1 PDP 4238935214."""
    got = _run(_chevron()["u15_22"], "1320")
    wca2, wcb1 = got["WCA_2"][1], got["WCB_1"][1]
    assert [r["offset_ft"] for r in wca2] == [-1427] and [r["offset_ft"] for r in wcb1] == [-2087]
    h = wca2[0]["proximity"]["cull"][0]
    assert h["api10"] == "4238935214" and 775 <= h["dh_ft"] <= 790 and h["dv_ft"] == 181
    assert wcb1[0]["proximity"]["cull"][0]["dh_ft"] <= 130
    assert all(len(v[1]) <= 1 for v in got.values())               # nothing else in the unit is culled


@pytest.mark.parametrize("spacing", ["880", "1320"])
@pytest.mark.parametrize("unit", ["u6_7", "u49_50_5"])
def test_chevron_depletion_units_keep_only_bs2_c(unit, spacing):
    """6-7 and 49-50-5: Michael dropped every seeded bench but BS2_C for depletion.
    At 300 ft vertical the rule agrees except 49-50-5 BS3_C, which lands 332-358 ft
    over the BS3_S producers: kept, every row a near-miss (the flag band)."""
    got = _run(_chevron()[unit], spacing)
    n, culled, s = got["BS2_C"]
    assert culled == [] and n >= 3 and not s["near"]
    for b, (n, culled, s) in got.items():
        if b == "BS2_C":
            continue
        if unit == "u49_50_5" and b == "BS3_C":
            assert culled == [] and len(s["near"]) == n and all(330 <= x["dv_ft"] <= 360 for x in s["near"])
        else:
            assert len(culled) == n, (unit, b)


def test_rule_counter_counts_after_proximity():
    """The winerack anchor is the bench keeping the most rows AFTER the cull."""
    u = _chevron()["u6_7"]
    unit = shape(u["geometry"])
    rule = ProximityRule(unit, u["azimuth_deg"], u["pdp"], PX)
    zones = {b: (t, 1320.0) for b, t in u["tvd_ft"].items()}
    legs = {b: [{"geom": wkt.loads(x["wkt"]), "completed_lateral_ft": x["completed_lateral_ft"]} for x in lg]
            for b, lg in u["legs"]["1320"].items()}
    kept = rule_counter(unit, u["azimuth_deg"], {}, None, rule, zones)
    assert kept("WCA_2", legs["WCA_2"]) == 0 and kept("BS2_C", legs["BS2_C"]) == len(legs["BS2_C"])
    assert rule_counter(unit, u["azimuth_deg"], {"WCA_2": {"pdp_proximity": False}}, None, rule, zones)(
        "WCA_2", legs["WCA_2"]) == len(legs["WCA_2"])
    assert rule_counter(unit, u["azimuth_deg"], {}, None)("WCA_2", legs["WCA_2"]) == len(legs["WCA_2"])


def test_review_and_dossier_show_the_culls():
    from dealintake.render import review
    from dealintake.render.tables import proximity_rows

    hit = {"api10": "4238935214", "bench": "WCB_1", "dh_ft": 123, "dv_ft": 66, "overlap": 0.75, "permit": False}
    cull = {"rule": "R", "cull": [{**hit, "text": proximity.hit_text(hit)}], "near": [], "permit": []}
    clear = {"rule": "R", "cull": [], "near": [], "permit": []}
    rows = [{"offset_ft": -2087, "proximity": cull}, {"offset_ft": -767, "proximity": clear},
            {"offset_ft": 553, "proximity": clear}]
    s = proximity.summarize(rows, rows[1:], enabled=True)
    gb = {"azimuth_deg": 179.7, "cross_extent_ft": [-2445, 2837],
          "existing": [{"api10": "4238935214", "bench": "WCB_1", "offset_ft": -2209, "tvd_ft": 10625.0, "inside": True}],
          "planned": {"WCB_1": {"tvd_ft": 10691.0, "spacing_ft": 1320.0, "spacing_source": "reviewer",
                                "offsets_ft": [-767, 553], "rules": ["1 row(s) culled by PDP proximity (R): ..."],
                                "proximity": s}},
          "culled_benches": {"WCA_2": {**proximity.summarize([rows[0]], [], enabled=True), "tvd_ft": 10444.0,
                                       "spacing_ft": 1320.0}}}
    svg = review.gunbarrel({"label": "u15_22", "gunbarrel": gb})
    assert "1 culled by PDP proximity" in svg and "all 1 rows culled by PDP proximity" in svg and "R of a producer" in svg
    assert review.proximity_cell("WCB_1", gb).startswith("1 of 3 culled · nearest 4238935214 WCB_1 123 ft hz / 66 ft vt / 75%")
    assert review.proximity_cell("WCA_2", gb).startswith("1 of 1 culled") and review.proximity_cell("BS2_C", gb) == "—"
    assert review.proximity_look(gb) == []
    gb["planned"]["WCB_1"]["proximity"] = {**s, "near": [{"offset_ft": 553, "text": "N"}]}
    assert review.proximity_look(gb) == ["WCB_1"]

    sig = {"benches": {"WCB_1": {"units": {"u15_22": {"gate2": {"source": "generate"}, "pdp_proximity": s},
                                           "u6_7": {"gate2": {"source": "generate"}, "pdp_proximity": None}}}}}
    (row,) = proximity_rows(sig)
    assert row[:6] == ["u15_22", "WCB_1", "generate", 3, 1, "-2,087"] and row[-1].startswith("4238935214 WCB_1 123 ft hz")
