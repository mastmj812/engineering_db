"""box.tag_scoreboard — pure core on synthetic frames (no DB, no grids on disk)."""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from box import tag_scoreboard as sb
from box import tops_qc as tq


def _frame(rows: list[dict]) -> pd.DataFrame:
    d = pd.DataFrame(rows)
    if "planned" not in d:
        d["planned"] = False
    if "lat_tvd_p50_ft" not in d:
        d["lat_tvd_p50_ft"] = np.nan
    d = sb.evidence_depth(d)
    return d.reset_index(drop=True)


def test_bench_order_reads_canonical_column():
    o = sb.bench_order()
    assert o["delaware"][8:11] == ["WCXY", "WCA_1", "WCA_2"]
    assert o["midland"].index("WCA_1") < o["midland"].index("WCB_1") < o["midland"].index("WCB_2")
    assert ("delaware", "WCA_1", "WCA_2") in sb.adjacent_pairs(o)


def test_evidence_depth_rules():
    d = pd.DataFrame({
        "planned": [False, True, False, False, False],
        "tvd_ft": [12_345, 12_345, 12_000, 12_000, 900],
        "lat_tvd_p50_ft": [np.nan, 12_300.0, np.nan, 12_050.0, np.nan],
    })
    best = sb.evidence_depth(d, "best")
    assert best["clean"].tolist() == [True, False, False, True, False]  # planned out; round-100 tvd_ft out; survey rescues; < 4,000 out
    assert best.loc[3, "depth_ft"] == 12_050.0 and best.loc[3, "depth_source"] == "survey"
    raw = sb.evidence_depth(d, "tvd_ft")
    assert raw.loc[3, "depth_ft"] == 12_000 and not raw.loc[3, "clean"]


def test_parse_points_and_fallback():
    assert sb.parse_points("MULTIPOINT((1 2),(3 4))") == [(1.0, 2.0), (3.0, 4.0)]
    assert sb.parse_points("MULTIPOINT(1 2,3 4)") == [(1.0, 2.0), (3.0, 4.0)]
    assert sb.parse_points(None, (5.0, 6.0)) == [(5.0, 6.0)]
    assert sb.parse_points(None) == []


def test_neighbour_pairs_same_basin_min_distance():
    df = pd.DataFrame({"basin": ["delaware", "delaware", "midland", "delaware"],
                       "pts": [[(0, 0), (1000, 0)], [(0, 100), (1000, 300)], [(0, 50)], [(50_000, 0)]]})
    pr = sb.neighbour_pairs(df, 500.0)
    got = {(i, j): d for i, j, d in pr.itertuples(index=False)}
    assert set(got) == {(0, 1), (1, 0)}  # midland well and the far well excluded
    assert got[(0, 1)] == pytest.approx(100.0)


def _stack(n_per=6, seed=0):
    """Delaware: n_per WCA_1 wells at ~12,000 ft and n_per WCA_2 at ~12,150 ft, all within 1 mi, plus one WCA_1-
    tagged well sitting at 12,160 ft (closer to the WCA_2 band)."""
    rng = np.random.default_rng(seed)
    rows = []
    for k in range(n_per):
        rows.append({"api10": f"a{k}", "basin": "delaware", "tag": "WCA_1", "tvd_ft": 12_001 + int(rng.integers(-20, 20)), "pts": [(k * 50.0, 0.0)]})
        rows.append({"api10": f"b{k}", "basin": "delaware", "tag": "WCA_2", "tvd_ft": 12_151 + int(rng.integers(-20, 20)), "pts": [(k * 50.0, 60.0)]})
    rows.append({"api10": "x", "basin": "delaware", "tag": "WCA_1", "tvd_ft": 12_163, "pts": [(10.0, 30.0)]})
    return _frame(rows)


def test_band_test_flags_the_misplaced_well():
    df = _stack()
    order = sb.bench_order()
    pairs = sb.neighbour_pairs(df, sb.M_PER_MI)
    bands = sb.local_bands(df, "tag", pairs, 3)
    bt = sb.band_test(df, "tag", bands, order, 25.0)
    x = df.index[df["api10"] == "x"][0]
    assert bt.loc[x, "band_status"] == "disagree" and bt.loc[x, "closer_bench"] == "WCA_2"
    assert (bt.drop(index=x)["band_status"] == "agree").all()


def test_band_test_off_column_and_untestable():
    df = _frame([{"api10": "o", "basin": "delaware", "tag": "OTHER", "tvd_ft": 9_001, "pts": [(0, 0)]},
                 {"api10": "u", "basin": "delaware", "tag": "WCC", "tvd_ft": 13_001, "pts": [(10, 0)]}])
    order = sb.bench_order()
    pairs = sb.neighbour_pairs(df, sb.M_PER_MI)
    bt = sb.band_test(df, "tag", sb.local_bands(df, "tag", pairs, 3), order, 25.0)
    assert bt["band_status"].tolist() == ["off_column", "untestable"]


def test_pair_inversions_direction_and_gap():
    df = _frame([{"api10": "s", "basin": "delaware", "tag": "WCA_1", "tvd_ft": 12_301, "pts": [(0, 0)]},
                 {"api10": "d", "basin": "delaware", "tag": "WCB_1", "tvd_ft": 12_201, "pts": [(100, 0)]},
                 {"api10": "e", "basin": "delaware", "tag": "WCA_2", "tvd_ft": 12_281, "pts": [(150, 0)]}])
    order = sb.bench_order()
    inv = sb.pair_inversions(df, "tag", sb.neighbour_pairs(df, 1000.0), order, 400.0, 50.0)
    sd = inv[(inv["tag_i"] == "WCA_1") & (inv["tag_j"] == "WCB_1")].iloc[0]
    assert sd["inverted"] and sd["rank_gap"] == 2 and sd["dz_ft"] == pytest.approx(100.0)
    se = inv[(inv["tag_i"] == "WCA_1") & (inv["tag_j"] == "WCA_2")].iloc[0]
    assert not se["inverted"]  # 20 ft deeper: inside the 50-ft tolerance
    assert len(inv) == 3


def test_band_separation_reports_the_gap():
    df = _stack(n_per=8)
    order = sb.bench_order()
    pairs = sb.neighbour_pairs(df, sb.M_PER_MI)
    sep = sb.band_separation(df, sb.local_bands(df, "tag", pairs, 3), order, min_n=5)
    row = sep[(sep["upper"] == "WCA_1") & (sep["lower"] == "WCA_2")].iloc[0]
    assert 100 < row["median_gap_ft"] < 200 and row["inverted_pct"] == 0


def test_labelled_set_tiers(tmp_path: Path):
    (tmp_path / "seeds").mkdir()
    pd.DataFrame({"api10": ["1", "2"], "corrected_code": ["WCB_1", "WCA_1"], "was": ["WCA_2", "WCB_1"],
                  "note": ["carded 2026-10-28 ...; ratified by MM", "class-accepted X 5/5 cards"]}).to_csv(tmp_path / "seeds" / "formation_tag_overrides.csv", index=False)
    le = tmp_path / "docs" / "lea_eddy_wc_tags"
    le.mkdir(parents=True)
    pd.DataFrame({"api10": ["3", "1"], "corrected_code": ["WCC", "WCB_2"], "was": ["WCA_2", "WCA_2"],
                  "note": ["carded 2026-11-05 ...; ratified by MM; NOT applied"] * 2}).to_csv(le / "proposed_override_seed.csv", index=False)
    pd.DataFrame({"api10": ["3", "4", "5"], "verdict": ["WCC", "lacking deep neighbors for comparison", ""]}).to_csv(le / "cards_sample.csv", index=False)
    lab = sb.labelled_set(tmp_path).set_index("api10")
    assert lab.loc["1", "label"] == "WCB_1"  # the seed row wins over a later source
    assert lab.loc["2", "tier"] == "class_accepted" and lab.loc["3", "tier"] == "carded"
    assert lab.loc["4", "tier"] == "hold" and "5" not in lab.index


def test_label_score_counts_holds_without_scoring():
    df = pd.DataFrame({"api10": ["1", "2", "4"], "basin": ["delaware"] * 3, "t": ["WCB_1", "WCA_2", "WCA_2"]})
    lab = pd.DataFrame({"api10": ["1", "2", "4"], "label": ["WCB_1", "WCA_1", None], "tier": ["carded", "carded", "hold"], "source": ["s"] * 3})
    ls = sb.label_score(df, "t", lab).set_index("tier")
    assert ls.loc["carded", "n"] == 2 and ls.loc["carded", "reproduced"] == 1
    assert ls.loc["hold", "n"] == 1 and pd.isna(ls.loc["hold", "reproduced"])


def test_grid_verdicts_majority_and_rules():
    k = {s: i for i, s in enumerate(tq.STACK)}
    # flat stack: surface k at 10,000 + 100 * k ft
    base = 10_000.0 + 100.0 * np.arange(len(tq.STACK))
    st = pd.DataFrame({"api10": ["w1"] * 3 + ["w2"] * 2 + ["w3"],
                       "tvd": [base[k["WOLFCAMP_XY"]] + 10, base[k["WOLFCAMP_XY"]] + 20, base[k["WOLFCAMP-B1"]] + 5,
                               base[k["WOLFCAMP-B1"]] + 30, base[k["WOLFCAMP-B1"]] + 40, base[k["AVALON1"]] + 5]})
    depths = np.tile(base, (len(st), 1))
    tags = pd.Series({"w1": "WCA_2", "w2": "WCA_1", "w3": "AVA_1"})
    county = pd.Series({"w1": "Reeves", "w2": "Reeves", "w3": "Reeves"})
    gv = sb.grid_verdicts(st, depths, tags, county)
    assert gv.loc["w1", "grid_verdict"] == "agree"   # 2 of 3 stations inside XY -> B1
    assert gv.loc["w2", "grid_verdict"] == "deep"    # below B1
    assert gv.loc["w3", "grid_verdict"] == "no_surface"  # AVA_1 has no surface (tops_qc rule)
