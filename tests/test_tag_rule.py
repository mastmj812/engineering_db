"""box.tag_rule — the v3 rule on synthetic neighbourhoods (no DB, no grids on disk)."""

from __future__ import annotations

import numpy as np
import pandas as pd

from box import tag_rule as tr
from box import tag_scoreboard as sb

ORDER = sb.bench_order()


def _wells(spec: list[tuple[str, int, int]], basin: str = "delaware", county: str = "Reeves") -> pd.DataFrame:
    """spec = (vendor code, depth ft, count); wells laid 40 m apart on a line, all inside 1 mi."""
    rows, k = [], 0
    for code, z, n in spec:
        for _ in range(n):
            rows.append({"api10": f"w{k}", "basin": basin, "county": county, "vendor": code, "depth_ft": float(z + (k % 5) * 4),
                         "evidence": True, "pts": [(k * 40.0, 0.0)]})
            k += 1
    return pd.DataFrame(rows)


def _run(df: pd.DataFrame, grid: pd.DataFrame | None = None) -> pd.DataFrame:
    return tr.assign_producers(df, sb.neighbour_pairs(df, 2.5 * sb.M_PER_MI), ORDER, grid)


def test_families():
    assert tr.family("delaware", "WCA_2") == "WCA" and tr.family("midland", "WCA_1") == "WCA_1"
    assert tr.family_codes(ORDER)[("delaware", "WCA")] == ["WCXY", "WCA_1", "WCA_2"]
    fo = tr.family_order(ORDER)["delaware"]
    assert fo.index("BS3_S") + 1 == fo.index("WCA") and fo.index("WCA") + 1 == fo.index("WCB")
    assert tr.family_span("delaware", "WCB", ORDER) == ("WOLFCAMP-B1", "WOLFCAMP-C")
    assert tr.family_span("delaware", "WCA", ORDER) == ("WOLFCAMP_XY", "WOLFCAMP-B1")


def test_position_resolves_and_abstains():
    codes = ["WCXY", "WCA_1", "WCA_2"]
    code, m, hi = tr.position(12_160.0, {"WCA_1": (12_000.0, 6), "WCA_2": (12_150.0, 6)}, codes)
    assert code == "WCA_2" and m == 85.0 and hi
    code, _, hi = tr.position(12_080.0, {"WCA_1": (12_000.0, 6), "WCA_2": (12_150.0, 6)}, codes)
    assert code == "WCA_2" and not hi  # 5 ft past the boundary: low confidence
    assert tr.position(12_000.0, {"WCA_1": (12_000.0, 6), "WCA_2": (12_050.0, 6)}, codes)[0] is None  # 50 ft < 75
    assert tr.position(12_000.0, {"WCA_1": (12_150.0, 6), "WCA_2": (12_000.0, 6)}, codes)[0] is None  # out of order
    assert tr.position(12_000.0, {"WCA_1": (12_000.0, 6)}, codes)[0] is None


def test_misplaced_subbench_moves_with_high_confidence():
    df = _wells([("WCA_1", 12_000, 8), ("WCA_2", 12_150, 8), ("WCA_1", 12_175, 1)])
    out = _run(df)
    x = out.iloc[-1]
    assert x["code"] == "WCA_2" and x["position_basis"] == "local_band" and x["confidence"] == "high"
    assert (out.iloc[:16]["code"] == df.iloc[:16]["vendor"]).all()


def test_thin_split_keeps_vendor_low_confidence():
    df = _wells([("WCA_1", 12_000, 8), ("WCA_2", 12_040, 8)])
    out = _run(df)
    assert (out["code"] == df["vendor"]).all()
    assert (out["confidence"] == "low").all() and (out["position_basis"] == "vendor").all()


def test_family_moves_on_local_bands_then_positions():
    df = _wells([("WCA_1", 12_000, 8), ("WCA_2", 12_120, 8), ("WCB_1", 12_400, 8), ("WCB_2", 12_650, 8), ("WCA_2", 12_410, 1)])
    out = _run(df)
    x = out.iloc[-1]
    assert x["family"] == "WCB" and x["family_basis"] == "local_band" and x["code"] == "WCB_1"


def test_protected_and_lithology_blocks():
    df = _wells([("WCB_1", 12_400, 8), ("WCC", 12_900, 8), ("WDFD", 12_410, 1)])
    out = _run(df)
    assert out.iloc[-1]["code"] == "WDFD"  # protected bench never moves (it has no own band here, so no move either)
    df = _wells([("BS2_C", 9_500, 8), ("BS2_S", 9_950, 8), ("BS2_C", 9_960, 1)])
    out = _run(df)
    assert out.iloc[-1]["code"] == "BS2_C" and out.iloc[-1]["family_flag"] == "lithology"


def test_rule_b_blocks_xy_crossing_in_lea():
    df = _wells([("BS3_S", 11_800, 8), ("WCXY", 12_000, 8), ("WCA_1", 12_100, 8), ("BS3_S", 12_105, 1)], county="Lea")
    out = _run(df)
    assert out.iloc[-1]["family"] == "BS3_S" and out.iloc[-1]["family_flag"] == "rule_b_pending"


def test_grid_moves_family_and_ambiguous_interval_flags():
    df = _wells([("WCA_2", 12_300, 1), ("WCA_2", 12_700, 1)])
    df["pts"] = [[(0.0, 0.0)], [(90_000.0, 0.0)]]  # far apart: no bands at all
    grid = pd.DataFrame({"dom_interval": ["WOLFCAMP-B1", "WOLFCAMP-B2"], "dom_share": [0.9, 0.9], "controlled": [True, True],
                         "no_control": [False, False], "fam_miss_ft": [180.0, 560.0]})
    out = _run(df, grid)
    # grid says WCB, but with no bands depth cannot place a WCB code: abstain = keep the vendor code, flagged
    assert out.iloc[0]["code"] == "WCA_2" and out.iloc[0]["position_basis"] == "abstain"
    assert out.iloc[0]["family"] == "WCA" and out.iloc[0]["family_flag"] == "family_conflict"
    assert out.iloc[1]["family"] == "WCA" and out.iloc[1]["family_flag"] == "family_conflict"  # B2 -> C: WCB or WCC


def test_grid_move_with_bands_places_the_code():
    df = _wells([("WCB_1", 12_400, 6), ("WCB_2", 12_650, 6), ("WCA_2", 12_390, 1)])
    grid = pd.DataFrame({"dom_interval": [None] * 12 + ["WOLFCAMP-B1"], "dom_share": [np.nan] * 12 + [0.9],
                         "controlled": [False] * 12 + [True], "no_control": [False] * 13, "fam_miss_ft": [np.nan] * 12 + [150.0]})
    x = _run(df, grid).iloc[-1]
    assert x["family"] == "WCB" and x["family_basis"] == "grid" and x["code"] == "WCB_1"


def test_grid_near_boundary_keeps_vendor():
    df = _wells([("WCA_2", 12_300, 1)])
    grid = pd.DataFrame({"dom_interval": ["WOLFCAMP-B1"], "dom_share": [0.6], "controlled": [True], "no_control": [False],
                         "fam_miss_ft": [30.0]})
    assert _run(df, grid).iloc[0]["family"] == "WCA"


def test_no_depth_keeps_vendor():
    df = _wells([("WCA_1", 12_000, 8), ("WCA_2", 12_150, 8), ("WCA_1", 12_175, 1)])
    df.loc[df.index[-1], "evidence"] = False
    out = _run(df)
    assert out.iloc[-1]["code"] == "WCA_1" and out.iloc[-1]["position_basis"] == "no_depth"


def test_stick_family_conflict_is_a_flag():
    prod = _wells([("WCA_1", 12_000, 8), ("WCA_2", 12_120, 8), ("WCB_1", 12_400, 8), ("WCB_2", 12_650, 8)])
    pout = _run(prod)
    sticks = pd.DataFrame({"basin": ["delaware", "delaware"], "county": ["Lea", "Lea"], "vendor": ["WCB_1", "WCB_2"],
                           "depth_ft": [12_010.0, 12_640.0], "evidence": [True, True], "pts": [[(100.0, 50.0)], [(200.0, 50.0)]]})
    pairs = _cross(sticks, prod, 2.5 * sb.M_PER_MI)
    s = tr.assign_sticks(sticks, prod, pout["code"].to_numpy(object), pairs, ORDER)
    assert s.iloc[0]["family"] == "WCB" and s.iloc[0]["family_flag"] == "family_conflict"
    assert s.iloc[1]["code"] == "WCB_2" and pd.isna(s.iloc[1]["family_flag"])


def _cross(a: pd.DataFrame, b: pd.DataFrame, r_m: float) -> pd.DataFrame:
    rows = []
    for i, pa in enumerate(a["pts"]):
        for j, pb in enumerate(b["pts"]):
            d = min(np.hypot(x1 - x2, y1 - y2) for x1, y1 in pa for x2, y2 in pb)
            if d <= r_m and a["basin"].iat[i] == b["basin"].iat[j]:
                rows.append((i, j, d))
    return pd.DataFrame(rows, columns=["i", "j", "d"])
