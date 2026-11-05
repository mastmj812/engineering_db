"""box.tag_ladder — rule v4 on synthetic neighbourhoods (no DB, no grids on disk)."""

from __future__ import annotations

import numpy as np
import pandas as pd

from box import tag_ladder as tl
from box import tag_scoreboard as sb

ORDER = sb.bench_order()
LAD = tl.Ladder(rung_min_n=3)


def _wells(spec: list[tuple[str, int, int]], county: str = "Reeves", basin: str = "delaware", agree: bool = True) -> pd.DataFrame:
    """(vendor code, depth, count): wells 40 m apart on a line, all within 1 mi. Vendors agree unless agree=False."""
    rows, k = [], 0
    for code, z, n in spec:
        for _ in range(n):
            rows.append({"api10": f"w{k}", "basin": basin, "county": county, "state_code": 48, "vendor": code,
                         "novi_code": code if agree else None, "env_code": code, "depth_ft": float(z + (k % 5) * 3),
                         "evidence": True, "pts": [(k * 40.0, 0.0)]})
            k += 1
    return pd.DataFrame(rows)


def _run(df: pd.DataFrame, grid: pd.DataFrame | None = None, lad: tl.Ladder = LAD) -> pd.DataFrame:
    res, _ = tl.run_producers(df, sb.neighbour_pairs(df, 2.0 * sb.M_PER_MI), ORDER, grid, lad)
    return res


STACK = [("BS3_S", 11_800, 6), ("WCA_1", 12_000, 6), ("WCA_2", 12_130, 6), ("WCB_1", 12_300, 6), ("WCB_2", 12_560, 6), ("WCC", 12_800, 6)]


def test_family_agree():
    df = pd.DataFrame({"basin": ["delaware"] * 4, "vendor": ["WCA_1", "WCA_2", "WCA_2", "OTHER"],
                       "novi_code": ["WCA_1", "WCB_1", None, None], "env_code": ["WCA_2", "WCA_2", "WCA_2", None]})
    assert tl.family_agree(df).tolist() == [True, False, True, False]


def test_clusters_merge_thin_and_inverted():
    cl = tl.clusters([("WCXY", -60.0), ("WCA_1", 0.0), ("WCA_2", 120.0), ("WCB_1", 300.0), ("WCB_2", 560.0), ("WCC", 600.0)], 75.0)
    assert [c for c, _ in cl] == [["WCXY", "WCA_1"], ["WCA_2"], ["WCB_1"], ["WCB_2", "WCC"]]
    cl = tl.clusters([("WCA_1", 0.0), ("WCA_2", -20.0)], 75.0)
    assert [c for c, _ in cl] == [["WCA_1", "WCA_2"]]


def test_place_margin_and_bar():
    cl = [(["WCA_1"], 0.0), (["WCA_2"], 130.0), (["WCB_1"], 300.0)]
    k, m, ok = tl.place(140.0, cl, LAD)
    assert k == 1 and m == 75.0 and ok
    k, m, ok = tl.place(70.0, cl, LAD)
    assert k == 1 and m == 5.0 and not ok


def test_ladder_moves_a_family_error_with_support():
    df = _wells([*STACK, ("WCA_2", 12_310, 1)])
    x = _run(df).iloc[-1]
    assert x["code"] == "WCB_1" and x["basis"] == "ladder" and x["confidence"] == "high"


def test_ladder_keeps_vendor_inside_a_thin_cluster():
    df = _wells([("WCA_1", 12_000, 6), ("WCA_2", 12_040, 6), ("WCB_1", 12_300, 6)])
    out = _run(df)
    wca = out.iloc[:12]
    assert (wca["code"] == df.iloc[:12]["vendor"]).all() and (wca["confidence"] == "low").all()


def test_no_target_support_blocks_the_move():
    # the deeper family has no evidence wells nearby (its rung comes from a distant place in the same county)
    near = _wells([("WCA_1", 12_000, 6), ("WCA_2", 12_130, 6), ("WCA_2", 12_320, 1)])
    far = _wells([("WCA_1", 12_000, 6), ("WCB_1", 12_300, 6)])
    far["pts"] = [[(200_000.0 + k * 40.0, 0.0)] for k in range(len(far))]
    far["api10"] = [f"f{k}" for k in range(len(far))]
    df = pd.concat([near, far], ignore_index=True)
    x = _run(df).iloc[len(near) - 1]
    assert x["code"] == "WCA_2" and x["flag"] == "no_target_support"


def test_disagreeing_vendors_are_not_witnesses():
    df = _wells(STACK)
    df.loc[df["vendor"] == "WCA_1", "novi_code"] = "WCB_1"  # every WCA_1 well disputed
    df.loc[df["vendor"] == "WCA_2", "novi_code"] = "WCB_2"
    res = _run(df)
    assert res["anchor_used"].isna().all() or (res["anchor_used"] != "primary").all()


def test_guards_and_unmapped():
    df = _wells([("BS2_C", 9_500, 6), ("BS2_S", 9_950, 6), ("WCA_1", 12_000, 6), ("BS2_C", 9_960, 1), ("OTHER", 12_300, 1)])
    out = _run(df)
    assert out.iloc[-2]["code"] == "BS2_C" and out.iloc[-2]["flag"] == "lithology"
    assert out.iloc[-1]["code"] == "OTHER" and out.iloc[-1]["basis"] == "unmapped"


def test_grid_decides_when_it_excludes_the_vendor_family():
    df = _wells([*STACK, ("WCA_2", 12_200, 1)])  # ladder alone: between WCA_2 and WCB_1, near the boundary
    g = pd.DataFrame({"dom_interval": [None] * 36 + ["WOLFCAMP-B1"], "dom_share": [np.nan] * 36 + [0.9],
                      "controlled": [False] * 36 + [True], "no_control": [False] * 37, "fam_miss_ft": [np.nan] * 36 + [120.0]})
    x = _run(df, g).iloc[-1]
    assert x["code"] == "WCB_1" and x["basis"] == "grid"


def test_grid_vetoes_a_ladder_move_out_of_an_allowed_family():
    df = _wells([*STACK, ("WCA_2", 12_310, 1)])
    g = pd.DataFrame({"dom_interval": [None] * 36 + ["WOLFCAMP_A"], "dom_share": [np.nan] * 36 + [0.9],
                      "controlled": [False] * 36 + [True], "no_control": [False] * 37, "fam_miss_ft": [np.nan] * 36 + [0.0]})
    x = _run(df, g).iloc[-1]
    assert x["code"] == "WCA_2" and x["flag"] == "grid_conflict"


def test_sticks_flag_family_conflicts():
    prod = _wells(STACK)
    res, rungs = tl.run_producers(prod, sb.neighbour_pairs(prod, 2.0 * sb.M_PER_MI), ORDER, None, LAD)
    sticks = pd.DataFrame({"basin": ["delaware"] * 2, "county": ["Reeves"] * 2, "state_code": [48, 48], "vendor": ["WCB_1", "WCB_1"],
                           "depth_ft": [12_005.0, 12_565.0], "evidence": [True, True], "pts": [[(50.0, 30.0)], [(60.0, 30.0)]]})
    pairs = pd.DataFrame([(i, j, abs(i * 10 + 50 - j * 40.0) + 30) for i in range(2) for j in range(len(prod))], columns=["i", "j", "d"])
    s = tl.run_sticks(sticks, pairs, prod, res["witness"].to_numpy(bool), rungs, ORDER, None, LAD)
    assert s.iloc[0]["code"] == "WCB_1" and s.iloc[0]["flag"] == "family_conflict"
    assert s.iloc[1]["code"] == "WCB_2"


def test_xy_guard_covers_every_family_across_the_xy_top():
    assert tl.crosses_xy("delaware", "BS3_S", "WCB", ORDER) and tl.crosses_xy("delaware", "WCC", "BS2_S", ORDER)
    assert not tl.crosses_xy("delaware", "WCA", "WCB", ORDER) and not tl.crosses_xy("delaware", "BS2_S", "BS3_S", ORDER)
    assert not tl.crosses_xy("midland", "LSSH", "WCA_1", ORDER)


def test_input_code_keeps_sql23_but_not_overrides():
    df = pd.DataFrame({"vendor": ["OTHER", "WCA_2", "WCA_1"], "live": ["BS1_S", "WCB_1", "WCA_1"],
                       "live_source": ["tvd_corrected", "ratified_override", "enverus"]})
    assert tl.input_code(df).tolist() == ["BS1_S", "WCA_2", "WCA_1"]
