"""BOX step 4 — TC-area regionalization (box/tc_area.py). DB-free."""

from __future__ import annotations

import datetime as dt

import numpy as np
import pandas as pd
import shapely
from scipy.sparse import coo_matrix
from scipy.sparse.csgraph import connected_components
from shapely.geometry import LineString
from shapely.geometry import box as rect

from box import edge_gap as eg
from box import tc_area as ta
from box import tc_area_report as tr

MI = ta.FT_PER_MI


def _world(seed: int = 1, n: int = 600, step: float = 0.8):
    """20 x 10 mi extent; west half log-response 0, east half +step; light noise."""
    ext = rect(0, 0, 20 * MI, 10 * MI)
    rng = np.random.default_rng(seed)
    xy = np.column_stack([rng.uniform(0, 20 * MI, n), rng.uniform(0, 10 * MI, n)])
    y = np.where(xy[:, 0] > 10 * MI, step, 0.0) + rng.normal(0, 0.15, n)
    return ext, xy, y


def _setup(ext, xy, p):
    cells, centres = ta.hex_cells(ext, p.cell_ft)
    pairs = ta.adjacency(cells, centres, p.cell_ft)
    wcell = ta.cell_of(cells, xy)
    return cells, centres, pairs, wcell


def test_hex_cells_tile_the_extent():
    ext = shapely.Polygon([(0, 0), (12 * MI, 0), (12 * MI, 3 * MI), (4 * MI, 3 * MI), (4 * MI, 9 * MI), (0, 9 * MI)])
    cells, centres = ta.hex_cells(ext, MI)
    assert abs(sum(c.area for c in cells) - ext.area) < 1.0
    assert shapely.union_all(cells).symmetric_difference(ext).area < 1.0
    pairs = ta.adjacency(cells, centres, MI)
    n = len(cells)
    nc, _ = connected_components(coo_matrix((np.ones(len(pairs)), (pairs[:, 0], pairs[:, 1])), shape=(n, n)), directed=False)
    assert nc == 1


def test_cell_of_every_inside_point_is_assigned():
    ext, xy, _ = _world()
    cells, _ = ta.hex_cells(ext, MI)
    wc = ta.cell_of(cells, xy)
    assert (wc >= 0).all()
    assert ta.cell_of(cells, np.asarray([[-5 * MI, -5 * MI]]))[0] == -1


def test_skater_partitions_are_nested_contiguous_and_respect_min_wells():
    p = ta.AreaParams(k_max=8)
    ext, xy, y = _world()
    cells, centres, pairs, wcell = _setup(ext, xy, p)
    parts = ta.build(centres, pairs, wcell, xy, y, p)
    assert len(parts) >= 2
    n = len(cells)
    for k, lab in enumerate(parts, start=1):
        assert lab.max() + 1 == k
        counts = np.bincount(lab[wcell], minlength=k)
        assert counts.min() >= p.min_wells
        for a in range(k):
            m = np.flatnonzero(lab == a)
            idx = np.isin(pairs[:, 0], m) & np.isin(pairs[:, 1], m)
            sub = pairs[idx]
            remap = {c: i for i, c in enumerate(m)}
            g = coo_matrix((np.ones(len(sub)), ([remap[c] for c in sub[:, 0]], [remap[c] for c in sub[:, 1]])), shape=(len(m), len(m)))
            assert connected_components(g, directed=False)[0] == 1, f"area {a} of k={k} not contiguous"
        if k > 1:  # nested: every k area lies inside one (k-1) area
            prev = parts[k - 2]
            for a in range(k):
                assert len(set(prev[lab == a])) == 1
    assert n == len(parts[0])


def test_first_cut_finds_the_step():
    p = ta.AreaParams(k_max=4)
    ext, xy, y = _world()
    _, centres, pairs, wcell = _setup(ext, xy, p)
    lab = ta.build(centres, pairs, wcell, xy, y, p)[1]
    wl = lab[wcell]
    east = xy[:, 0] > 10 * MI
    # the two areas are (almost) the two halves
    agree = max(np.mean(wl == east.astype(int)), np.mean(wl == (~east).astype(int)))
    assert agree > 0.95


def test_cv_picks_two_areas_for_a_two_block_world():
    p = ta.AreaParams(k_max=12, folds=5, block_ft=2 * MI)
    ext, xy, y = _world(n=900)
    _, centres, pairs, wcell = _setup(ext, xy, p)
    res = ta.cross_validate(centres, pairs, wcell, xy, y, p)
    pick = ta.choose_k(res["cv"])
    assert 2 <= pick["k_1se"] <= 4
    assert res["cv"].loc[res["cv"].k == 2, "mse"].iloc[0] < 0.5 * res["cv"].loc[res["cv"].k == 1, "mse"].iloc[0]


def test_no_signal_world_stays_one_area():
    p = ta.AreaParams(k_max=10, block_ft=2 * MI)
    ext, xy, _ = _world(n=800)
    y = np.random.default_rng(7).normal(0, 0.3, len(xy))
    _, centres, pairs, wcell = _setup(ext, xy, p)
    pick = ta.choose_k(ta.cross_validate(centres, pairs, wcell, xy, y, p)["cv"])
    assert pick["k_1se"] <= 2


def test_dissolve_tiles_and_numbers_north_to_south():
    p = ta.AreaParams(k_max=3)
    ext, xy, y = _world()
    cells, centres, pairs, wcell = _setup(ext, xy, p)
    lab = ta.build(centres, pairs, wcell, xy, y, p)[1]
    geoms, cell_no = ta.dissolve(cells, lab, centres)
    assert sorted(set(cell_no.tolist())) == [1, 2]
    assert abs(sum(g.area for g in geoms) - ext.area) < 10.0
    assert shapely.union_all(geoms).symmetric_difference(ext).area < 10.0


def test_adjacency_is_the_hex_lattice_inside_a_big_rectangle():
    ext = rect(0, 0, 30 * MI, 20 * MI)
    cells, centres = ta.hex_cells(ext, MI)
    pairs = ta.adjacency(cells, centres, MI)
    deg = np.bincount(pairs.ravel(), minlength=len(cells))
    interior = (centres[:, 0] > 2 * MI) & (centres[:, 0] < 28 * MI) & (centres[:, 1] > 2 * MI) & (centres[:, 1] < 18 * MI)
    assert (deg[interior] == 6).all()


# ----------------------------------------------------------------------------
# report helpers (pure parts of box/tc_area_report.py)
# ----------------------------------------------------------------------------


def _frame():
    lon, lat = -103.6, 32.1
    wells = pd.DataFrame({
        "api10": ["1", "2", "3", "4"],
        "mid_lon": [lon, lon, lon, -101.0],
        "mid_lat": [lat, lat, lat, lat],
        "first_production_date": [dt.date(2020, 1, 1), dt.date(2015, 6, 1), dt.date(2025, 6, 1), dt.date(2020, 1, 1)],
        "lateral_length_ft": [10000.0, 10000.0, 10000.0, 10000.0],
        "cum_12m_oil_bbl": [200000.0, 150000.0, 0.0, 200000.0],
        "cohort": [True, False, False, True],
    })
    extra = pd.DataFrame({"api10": ["1", "2", "3", "4"], "cum_24m_oil_bbl": [300000.0, 250000.0, None, 300000.0],
                          "eur_30yr_oil_bbl": [800000.0, None, None, 800000.0], "cum_life_oil_bbl": [600000.0, 500000.0, 20000.0, 600000.0],
                          "last_reported_month": [dt.date(2026, 8, 1)] * 4})
    x, y = eg._transformer().transform(lon, lat)
    ext = shapely.Point(x * eg._M_TO_FT, y * eg._M_TO_FT).buffer(5 * MI)
    return tr.prepare(wells, extra, ext), ext


def test_prepare_cohorts_follow_d9_and_the_extent():
    d, _ = _frame()
    assert d["c12"].tolist() == [True, False, False, False]  # 2 = pre-2016, 3 = no 12-mo, 4 = outside the extent
    assert d["c24"].tolist() == [True, False, False, False]
    assert d["ceur"].tolist() == [True, False, True, False]  # 3 has no Novi EUR -> cum-to-date fallback
    assert d.loc[2, "eur_src"] == "cum_to_date"
    assert abs(d.loc[0, "oil12_ft"] - 20.0) < 1e-9 and abs(d.loc[0, "bo_ft"] - 80.0) < 1e-9


def test_area_stats_percentiles_are_spe_p10_high():
    d = pd.DataFrame({"area_no": [1] * 10, "c12": True, "c24": False, "ceur": False, "oil12_ft": np.arange(1.0, 11.0), "oil24_ft": np.nan,
                      "bo_ft": np.nan, "eur_src": "", "operator": "X", "formation_blueox": "WCA_1",
                      "first_production_date": [dt.date(2020, 1, 1)] * 10, "lateral_length_ft": 10000.0})
    s = tr.area_stats(d, [rect(0, 0, MI, MI)], None).iloc[0]
    assert s["oil12_p10_high"] > s["oil12_p50"] > s["oil12_p90_low"]
    assert s["n12"] == 10 and s["area_sqmi"] == 1.0


def test_pud_areas_co_extent_overlap_not_distance():
    ext = rect(0, 0, 10 * MI, 5 * MI)
    a1, a2 = rect(0, 0, 5 * MI, 5 * MI), rect(5 * MI, 0, 10 * MI, 5 * MI)
    sticks = [LineString([(1 * MI, 1 * MI), (4.5 * MI, 1 * MI)]),   # all in area 1
              LineString([(4 * MI, 2 * MI), (8 * MI, 2 * MI)]),       # 1 mi in a1, 3 mi in a2 -> area 2
              LineString([(9 * MI, 4 * MI), (14 * MI, 4 * MI)])]      # 1 of 5 mi inside -> outside the extent
    ll = eg.to_lonlat(sticks)
    puds = pd.DataFrame({"stick_id": [1, 2, 3], "formation_blueox": ["WCA_1", "WCXY", "WCA_2"], "status": [None, "remaining_pud", "conflict"],
                         "wkt": [g.wkt for g in ll]})
    out = tr.pud_areas(puds, ext, [a1, a2])  # sticks round-trip lon/lat -> UTM 13N ft inside
    assert out["area_no"].tolist() == [1, 2, 0]
    assert out["bench_grp"].tolist() == ["WCA_1+2", "WCXY", "WCA_1+2"]
