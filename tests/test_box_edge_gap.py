"""DB-free tests for the pure edge-gap metric in box/edge_gap.py (outline, ring walk, sides,
edge performance, step-outs)."""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest
from shapely.geometry import LineString, Point, Polygon

from box import edge_gap as eg

MI = eg.FT_PER_MI
P = eg.EdgeParams(pin_radius_ft=1320.0, close_ft=2640.0, ring_step_ft=50.0)


def _unit(x0: float, y0: float, n: int = 6, spacing: float = 880.0, length: float = 10_000.0) -> list[LineString]:
    """n parallel N-S laterals starting at (x0, y0)."""
    return [LineString([(x0 + i * spacing, y0), (x0 + i * spacing, y0 + length)]) for i in range(n)]


def test_dense_block_is_one_body_fully_pinned():
    lines = _unit(0, 0) + _unit(0, 10_600)  # two units stacked N-S, 600 ft heel-toe gap
    o = eg.outline(lines, P)
    comps = eg.components(o, lines, P)
    assert len(comps) == 1 and comps.n_laterals.iloc[0] == 12 and comps.n_holes.iloc[0] == 0
    seg = eg.walk(o.geoms[0], lines, P)
    st = eg.gap_stats(seg)
    assert st["pinned_share"] > 0.97 and st["gap_max_ft"] < 300


def test_staircase_notch_reads_pinned_not_gap():
    # diagonal flank: three units stepping 1 mi east and 2 mi north each — the Delaunay-hull
    # artifact (v1) read the notch chords as 1.5-2.5 mi gaps
    lines = _unit(0, 0) + _unit(5280, 10_560) + _unit(10_560, 21_120)
    o = eg.outline(lines, eg.EdgeParams(pin_radius_ft=2640.0, close_ft=3960.0, ring_step_ft=50.0))
    seg = eg.walk(o.geoms[0], lines, eg.EdgeParams(pin_radius_ft=2640.0, close_ft=3960.0, ring_step_ft=50.0))
    assert eg.gap_stats(seg)["share_gap_gt_1_mi"] == 0.0


def test_bridged_opening_is_a_gap_between_the_flanking_wells():
    # two units 1 mi apart east-west (open ground between), bridged by a 1-mi closing
    a, b = _unit(0, 0, n=3), _unit(4400 + 5280, 0, n=3)
    lines = a + b
    p = eg.EdgeParams(pin_radius_ft=1320.0, close_ft=5280.0, ring_step_ft=50.0)
    o = eg.outline(lines, p)
    assert len(o.geoms) == 1
    seg = eg.walk(o.geoms[0], lines, p)
    gaps = seg[(seg.kind == "gap") & (seg.length_ft > 1000)]
    assert len(gaps) >= 2  # north and south mouths of the bridged opening
    for _, g in gaps.iterrows():
        assert {g.well_a, g.well_b} == {2, 3}  # the inner flank laterals
        assert 2000 < g.length_ft < 5280 + 1000


def test_no_bridge_leaves_a_stepout():
    lines = _unit(0, 0) + [LineString([(30_000, 0), (30_000, 10_000)])]
    o = eg.outline(lines, P)
    comps = eg.components(o, lines, P)
    assert len(comps) == 2 and comps.body.sum() == 1
    body = o.geoms[int(comps.comp.iloc[0])]
    so = eg.stepouts(body, lines)
    assert list(so.ix) == [6] and so.side.iloc[0] == "E" and so.dist_mi.iloc[0] == pytest.approx((30_000 - 4400 - 1320) / MI, rel=0.02)


def test_runs_cyclic_handover_and_wrap():
    # ring of 20 samples: owners 0 0 0 1 1 -1 -1 -1 2 2 2 ... 2 0 (wraps into run 0)
    own = np.array([0, 0, 0, 1, 1, -1, -1, -1] + [2] * 11 + [0])
    s = np.arange(20) * 10.0
    runs = eg.runs_from_owners(s, own, 200.0)
    kinds = [r["kind"] for r in runs]
    assert kinds.count("gap") == 1 and kinds.count("pinned") == 3
    g = next(r for r in runs if r["kind"] == "gap")
    assert g["length_ft"] == pytest.approx(30.0) and (g["well_a"], g["well_b"]) == (1, 2)
    p0 = next(r for r in runs if r["kind"] == "pinned" and r["well_a"] == 0)
    assert p0["length_ft"] == pytest.approx(40.0)  # the wrapped sample joins run 0
    assert sum(r["length_ft"] for r in runs) == pytest.approx(200.0)


def test_runs_degenerate_rings():
    s = np.arange(10) * 1.0
    assert eg.runs_from_owners(s, np.full(10, -1), 10.0)[0]["kind"] == "gap"
    r = eg.runs_from_owners(s, np.full(10, 4), 10.0)
    assert len(r) == 1 and r[0]["kind"] == "pinned" and r[0]["length_ft"] == 10.0


def test_ring_piece_wraps_origin():
    ring = Polygon([(0, 0), (100, 0), (100, 100), (0, 100)]).exterior
    piece = eg.ring_piece(ring, 350.0, 50.0)
    assert piece.length == pytest.approx(100.0)


def test_side_sector_compass():
    c = Point(0, 0)
    assert eg.side_sector(Point(0, 10), c) == "N"
    assert eg.side_sector(Point(10, -10), c) == "SE"
    assert eg.side_sector(Point(-10, 0), c) == "W"


@pytest.mark.parametrize(("ratio", "cls"), [(0.85, "strong"), (1.3, "strong"), (0.84, "unknown"), (0.70, "unknown"), (0.69, "rolled"), (float("nan"), "unknown"), (None, "unknown")])
def test_perf_class_thresholds(ratio, cls):
    assert eg.perf_class(ratio) == cls


def test_gap_class_bins():
    assert eg.gap_class(0) == "< 1/4 mi"
    assert eg.gap_class(2640) == "1/2-1 mi"
    assert eg.gap_class(20_000) == "> 2 mi"


def test_edge_evidence_ratio_and_negative_evidence():
    # three stacked rows of 12 laterals; the west-flank lateral of each row rolls over
    lines = _unit(0, 0, n=12) + _unit(0, 10_600, n=12) + _unit(0, 21_200, n=12)
    p = eg.EdgeParams(pin_radius_ft=1320.0, close_ft=2640.0, ring_step_ft=100.0, interior_depth_ft=500.0, edge_reach_ft=400.0)  # reach isolates the flank lateral
    body = eg.outline(lines, p).geoms[0]
    oil = np.array(([10.0] + [20.0] * 11) * 3)
    coh = np.ones(36, dtype=bool)
    im = eg.interior_mask(body, lines, p)  # whole lateral >= r + depth inside the edge
    assert im[12 + 5] and not im[12] and not im[5]
    old = [LineString([(-3000, 5000), (-3000, 15_000)])]  # pre-2016 test just west, outside
    seg = eg.walk(body, lines, p)
    seg = eg.attach_edge_evidence(seg, lines, oil, coh, 20.0, old, body, p)
    west = seg[(seg.kind == "pinned") & seg.well_a.isin([0, 12])]
    assert len(west) and (west.perf_class == "rolled").all() and (west.n_pre2016_outside >= 1).all()
    east = seg[(seg.kind == "pinned") & seg.well_a.isin([11, 23, 35])]
    assert (east.perf_class == "strong").all()


def test_tune_close_picks_smallest_one_body():
    sw = pd.DataFrame({"r_mi": [0.5] * 4, "c_mi": [0.5, 0.75, 1.0, 1.5], "n_bodies": [4, 1, 1, 1]})
    assert eg.tune_close(sw, 0.5) == pytest.approx(0.75 * MI)
    with pytest.raises(ValueError):
        eg.tune_close(sw.assign(n_bodies=2), 0.5)
