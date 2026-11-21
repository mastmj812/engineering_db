"""BOX sticks generator 0.13: the grid rung and the grid bound (box/sticks/grid_rung.py). DB-free and grid-file-free:
the sampler is a stand-in with flat surfaces."""
from __future__ import annotations

import numpy as np
import pandas as pd

from box.sticks import core, reads, store
from box.sticks import grid_rung as gr

MI = gr.MI
# flat surfaces: BS2_S 10,000 to 10,500 ft, BS3_C 10,500 to 11,100 ft, everything else null
FLAT = {"2BSPGS": 10_000.0, "3BSPGC": 10_500.0, "3BSPGS": 11_100.0}


def sample(x: np.ndarray, y: np.ndarray) -> dict[str, np.ndarray]:
    return {s: np.full(len(x), FLAT.get(s, np.nan)) for s in gr.SURFACES}


def wells(n: int, dist_mi: float, depth: float, code: str = "BS2_S") -> pd.DataFrame:
    ang = np.linspace(0, 2 * np.pi, n, endpoint=False)
    return pd.DataFrame({"basin": "delaware", "live": code, "x": dist_mi * MI * np.cos(ang), "y": dist_mi * MI * np.sin(ang), "depth_ft": depth})


def chain(rows: list[tuple]) -> pd.DataFrame:
    return pd.DataFrame([{"basin": b, "code": c, "pad_id": p, "z": z, "rung": r, "how": "x", "expected_median_ft": 90.0, "expected_p90_ft": 250.0,
                          "second_tvd_ft": np.nan, "second_share": np.nan} for b, c, p, z, r in rows])


PADS = pd.DataFrame({"pad_id": [1, 2, 3, 4, 5], "cx": 0.0, "cy": 0.0})


def test_the_decisions_of_record():
    assert gr.BASIN == "delaware" and gr.BOUND_FT == 150.0
    assert (gr.FAR_MIN_MI, gr.FAR_MAX_MI, gr.WIDE_MAX_MI, gr.MIN_WELLS) == (5.0, 15.0, 25.0, 10)
    assert set(gr.RUNG_BENCHES) <= set(gr.INTERVALS)
    assert gr.INTERVALS["BS3_S"] == ("3BSPGS", "WOLFCAMP_XY") and gr.INTERVALS["WCXY"][0] == "WOLFCAMP_XY"     # the XY top: depth only
    assert "WOLFCAMP-B2" not in gr.SURFACES and "WOLFCAMP-C" not in gr.SURFACES and "WOLFCAMP_D" not in gr.SURFACES
    assert core.VERSION == "box_sticks_0.14" and "grid" in store.RUNGS and "grid" in reads.CARRIED
    assert {"grid_bounded", "outside_grid"} <= set(store.STICK_FLAGS) and set(reads.GRID_FLAGS) == {"grid_bounded", "outside_grid"}


def test_fraction_comes_from_the_ring_and_never_from_wells_inside_five_miles():
    ring = wells(12, 8.0, 10_400.0)                       # fraction 0.8 in the 10,000 to 10,500 interval
    near = wells(12, 2.0, 10_050.0)                       # fraction 0.1, inside 5 miles: must not teach
    w = pd.concat([ring, near], ignore_index=True)
    wxy = w[["x", "y"]].to_numpy(float)
    g = sample(wxy[:, 0], wxy[:, 1])
    p = gr.predict("BS2_S", np.zeros((1, 2)), sample(np.zeros(1), np.zeros(1)), wxy, w["depth_ft"].to_numpy(float), g)
    assert p["basis"][0] == "5-15 mi" and abs(p["z"][0] - 10_400.0) < 1e-6 and (p["top"][0], p["base"][0]) == (10_000.0, 10_500.0)


def test_fraction_widens_to_25_miles_then_to_the_basin():
    far = wells(12, 20.0, 10_250.0)
    wxy = far[["x", "y"]].to_numpy(float)
    f = gr.well_fraction(far["depth_ft"].to_numpy(float), *gr.interval("BS2_S", sample(wxy[:, 0], wxy[:, 1])))
    assert gr.regional_fraction(np.zeros((1, 2)), wxy, f)[1][0] == "5-25 mi"
    out = wells(12, 60.0, 10_250.0)
    oxy = out[["x", "y"]].to_numpy(float)
    fr, basis = gr.regional_fraction(np.zeros((1, 2)), oxy, f)
    assert basis[0] == "basin" and abs(fr[0] - 0.5) < 1e-9
    assert gr.regional_fraction(np.zeros((1, 2)), oxy, np.full(12, np.nan))[1][0] == ""              # nobody can teach: no value


def test_a_well_far_outside_its_interval_does_not_teach():
    f = gr.well_fraction(np.array([10_250.0, 9_000.0, 12_000.0, 10_540.0]), np.full(4, 10_000.0), np.full(4, 500.0))
    assert np.isfinite(f).tolist() == [True, False, False, True]


def test_grid_replaces_offset_bounds_carried_and_only_notes_direct():
    ev = wells(12, 8.0, 10_400.0)
    ch = chain([("delaware", "BS2_S", 1, 10_300.0, "offset"),        # offset -> grid rung
                ("delaware", "BS2_S", 2, 10_900.0, "thickness"),     # 400 ft below the base -> pulled
                ("delaware", "BS2_S", 3, 10_600.0, "thickness"),     # 100 ft below the base -> left alone
                ("delaware", "BS2_S", 4, 10_900.0, "direct"),        # direct: never moved, noted
                ("midland", "BS2_S", 5, 10_900.0, "offset")])        # another basin: untouched
    out = gr.apply_to_chain(ch, ev, PADS, sample, rung_benches={"BS2_S": (60.0, 190.0)})
    assert out["rung"].tolist() == ["grid", "grid", "thickness", "direct", "offset"]
    assert out["grid_note"].tolist() == ["grid_rung", "grid_bounded", "", "outside_grid", ""]
    assert np.allclose(out["z"], [10_400.0, 10_400.0, 10_600.0, 10_900.0, 10_900.0]) and np.allclose(out["z_before"], ch["z"])
    assert out["how"].tolist()[:2] == ["grid 5-15 mi", "grid 5-15 mi (bound on thickness)"]
    assert out["expected_median_ft"].tolist()[:2] == [60.0, 60.0] and out["expected_median_ft"][2] == 90.0


def test_a_bench_that_failed_g1_keeps_its_offset_rung_but_is_still_bounded():
    ev = wells(12, 8.0, 10_400.0)
    ch = chain([("delaware", "BS2_S", 1, 10_300.0, "offset"), ("delaware", "BS2_S", 2, 10_900.0, "offset")])
    out = gr.apply_to_chain(ch, ev, PADS, sample, rung_benches={})
    assert out["rung"].tolist() == ["offset", "grid"] and out["grid_note"].tolist() == ["", "grid_bounded"]


def test_skipped_cells_are_noted_and_not_moved():
    assert ("BS3_C", "thickness") in gr.BOUND_SKIP and ("BS3_C", "bracket") in gr.BOUND_SKIP and ("BS1_S", "thickness") in gr.BOUND_SKIP
    ev = wells(12, 8.0, 10_800.0, code="BS3_C")
    ch = chain([("delaware", "BS3_C", 1, 11_500.0, "thickness")])
    out = gr.apply_to_chain(ch, ev, PADS, sample, rung_benches={})
    assert out["rung"][0] == "thickness" and out["z"][0] == 11_500.0 and out["grid_note"][0] == "outside_grid"


def test_no_grid_means_no_change_and_no_failure():
    ch = chain([("delaware", "BS2_S", 1, 10_300.0, "offset"), ("delaware", "WCB_1", 2, 12_000.0, "offset")])
    out = gr.apply_to_chain(ch, wells(12, 8.0, 10_400.0), PADS, None)
    assert out["rung"].tolist() == ["offset", "offset"] and out["grid_note"].tolist() == ["", ""] and np.allclose(out["z"], ch["z"])
    null = gr.apply_to_chain(ch, wells(12, 8.0, 10_400.0), PADS, lambda x, y: {s: np.full(len(x), np.nan) for s in gr.SURFACES}, rung_benches={"BS2_S": (1.0, 2.0)})
    assert null["rung"].tolist() == ["offset", "offset"] and np.allclose(null["z"], ch["z"])       # a null surface: the chain stands
    assert "WCB_1" not in gr.INTERVALS                                                                 # no trusted surface pair: never touched


# ---- generator 0.14: the Midland table (docs/box_sticks/grid-midland-2026-11-21)

MID = {"JO_MILL": 8_000.0, "LOWER_SPRABERRY_SHALE": 8_400.0, "WOLFCAMP_A": 9_000.0, "WOLFCAMP_B": 9_300.0}


def mid_sample(x: np.ndarray, y: np.ndarray) -> dict[str, np.ndarray]:
    return {s: np.full(len(x), MID.get(s, np.nan)) for s in gr.MIDLAND_SURFACES}


def test_the_midland_table_is_what_the_bars_admitted():
    t = gr.BASINS["midland"]
    assert set(t.rung) == {"MS", "JM", "LSSH", "DEAN", "WCD"} and "WCA_1" not in t.rung          # M1: WCA_1 keeps the offset rung
    assert t.bound == frozenset() and t.bound_skip == frozenset()                                  # M2 failed: nothing is bounded
    assert not {"WCB_1", "WCB_2", "WCC", "US"} & set(t.intervals)                                  # no picked boundary: left out
    assert "WOLFCAMP_B_LOWER" not in t.surfaces and "WOLFCAMP_C" not in t.surfaces
    d = gr.BASINS["delaware"]
    assert d.intervals is gr.INTERVALS and d.rung is gr.RUNG_BENCHES and d.bound == frozenset(gr.INTERVALS) and d.bound_skip == gr.BOUND_SKIP


def test_midland_grid_replaces_offset_and_bounds_nothing():
    ev = wells(12, 8.0, 8_300.0, code="JM").assign(basin="midland")           # fraction 0.75 in the 8,000 to 8,400 interval
    ev = pd.concat([ev, wells(12, 8.0, 9_100.0, code="WCA_1").assign(basin="midland")], ignore_index=True)
    ch = chain([("midland", "JM", 1, 8_150.0, "offset"),          # offset -> grid rung
                ("midland", "JM", 2, 8_900.0, "thickness"),       # 500 ft below the base: NOT pulled, NOT flagged (no bound in the Midland)
                ("midland", "WCA_1", 3, 9_200.0, "offset"),       # WCA_1 failed M1: keeps the offset rung
                ("midland", "WCA_1", 4, 9_900.0, "direct"),       # direct, far outside: not flagged
                ("midland", "WCB_1", 5, 9_500.0, "offset")])      # no interval: untouched
    out = gr.apply_to_chain(ch, ev, PADS, {"midland": mid_sample, "delaware": None})
    assert out["rung"].tolist() == ["grid", "thickness", "offset", "direct", "offset"]
    assert out["grid_note"].tolist() == ["grid_rung", "", "", "", ""]
    assert np.allclose(out["z"], [8_300.0, 8_900.0, 9_200.0, 9_900.0, 9_500.0])
    assert out["expected_median_ft"][0] == gr.MIDLAND_RUNG["JM"][0] and out["how"][0] == "grid 5-15 mi"


def test_each_basin_reads_only_its_own_grids():
    ev = pd.concat([wells(12, 8.0, 10_400.0), wells(12, 8.0, 8_300.0, code="JM").assign(basin="midland")], ignore_index=True)
    ch = chain([("delaware", "BS2_S", 1, 10_300.0, "offset"), ("midland", "JM", 2, 8_150.0, "offset")])
    both = gr.apply_to_chain(ch, ev, PADS, {"delaware": sample, "midland": mid_sample})
    assert both["rung"].tolist() == ["grid", "grid"] and np.allclose(both["z"], [10_400.0, 8_300.0])
    only_d = gr.apply_to_chain(ch, ev, PADS, {"delaware": sample, "midland": None})                 # Midland grids missing: its chain stands
    assert only_d["rung"].tolist() == ["grid", "offset"] and only_d["z"][1] == 8_150.0
    bare = gr.apply_to_chain(ch, ev, PADS, sample)                                                  # a bare sampler is the Delaware's
    assert bare["rung"].tolist() == ["grid", "offset"]
    assert gr.apply_to_chain(ch, ev, PADS, {"delaware": sample, "midland": mid_sample}, tables={"delaware": gr.BASINS["delaware"]})["rung"].tolist() == ["grid", "offset"]
