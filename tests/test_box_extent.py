"""DB-free tests for BOX step 3: the buffer rule + extent assembly (box/extent.py) and the geology
shapefile round-trip (box/geology_io.py)."""

from __future__ import annotations

from dataclasses import replace

import numpy as np
import pandas as pd
import pytest
import shapely
from shapely.geometry import LineString, Point, Polygon

from box import edge_gap as eg
from box import extent as ex
from box import geology_io as gio

MI = eg.FT_PER_MI
BP = replace(ex.DEFAULT, k=0.5, cap_ft=5280.0, floor_ft=880.0)


def _seg(rows: list[dict]) -> pd.DataFrame:
    base = {"kind": "pinned", "length_ft": 1000.0, "perf_class": "unknown", "perf_class_local": "unknown", "n_pre2016_outside": 0, "side": "N",
            "geom": LineString([(0, 0), (1000, 0)])}
    return pd.DataFrame([{**base, **r} for r in rows])


# ---------------------------------------------------------------------------- buffer rule


def test_pinned_floor_by_perf_class():
    sb = ex.segment_buffers(_seg([{"perf_class": "rolled"}, {"perf_class": "unknown"}, {"perf_class": "strong"}]), BP)
    assert list(sb.buffer_ft) == [880.0, 1320.0, 1760.0]
    assert set(sb.rule) == {"pinned: floor"}


def test_gap_scales_with_length_and_perf_then_caps():
    sb = ex.segment_buffers(_seg([
        {"kind": "gap", "length_ft": 4000.0, "perf_class": "strong"},  # 0.5 * 4000 * 1.0 = 2000
        {"kind": "gap", "length_ft": 4000.0, "perf_class": "rolled"},  # 0.5 * 4000 * 0.5 = 1000
        {"kind": "gap", "length_ft": 1000.0, "perf_class": "strong"},  # 500 -> floor 1760
        {"kind": "gap", "length_ft": 40000.0, "perf_class": "strong"},  # 20000 -> cap 5280
    ]), BP)
    assert list(sb.buffer_ft) == [2000.0, 1000.0, 1760.0, 5280.0]
    assert sb.rule.iloc[3] == "gap: capped"


def test_pre2016_tightens_a_gap_to_its_floor():
    sb = ex.segment_buffers(_seg([{"kind": "gap", "length_ft": 8000.0, "perf_class": "strong", "n_pre2016_outside": 2}]), BP)
    assert sb.buffer_ft.iloc[0] == 1760.0 and "pre-2016" in sb.rule.iloc[0]


def test_live_front_side_goes_to_cap_and_potash_overrides_everything():
    seg = _seg([{"side": "W"}, {"side": "W", "geom": LineString([(50_000, 0), (51_000, 0)])}, {"side": "E", "kind": "gap", "length_ft": 9000.0}])
    sopa = shapely.box(49_000, -500, 52_000, 500)
    sb = ex.segment_buffers(seg, BP, fronts={"W": {}}, sopa=sopa)
    assert sb.buffer_ft.iloc[0] == 5280.0 and sb.rule.iloc[0].startswith("live front")
    assert sb.buffer_ft.iloc[1] == 1320.0 and sb.rule.iloc[1].startswith("potash")  # front side, but inside the potash polygon
    assert sb.buffer_ft.iloc[2] == 0.5 * 9000 * 0.75


def test_local_reference_switches_the_class_used():
    seg = _seg([{"perf_class": "rolled", "perf_class_local": "strong"}])
    assert ex.segment_buffers(seg, BP).buffer_ft.iloc[0] == 880.0
    assert ex.segment_buffers(seg, replace(BP, perf_ref="local")).buffer_ft.iloc[0] == 1760.0


def test_uniform_baseline_ignores_everything():
    seg = _seg([{"kind": "gap", "length_ft": 9000.0, "perf_class": "strong", "side": "W"}])
    sb = ex.segment_buffers(seg, replace(BP, uniform=True, floor_ft=2000.0), fronts={"W": {}})
    assert sb.buffer_ft.iloc[0] == 2000.0


def test_cap_below_floor_never_undercuts_the_floor():
    sb = ex.segment_buffers(_seg([{"kind": "gap", "length_ft": 40000.0, "perf_class": "strong"}]), replace(BP, cap_ft=1000.0))
    assert sb.buffer_ft.iloc[0] == 1760.0


# ---------------------------------------------------------------------------- step-outs / fronts


def _so(side: str, cls: list[str], dist: float = 2.0) -> pd.DataFrame:
    pr = {"ok": 0.9, "rolled": 0.3, "no12": np.nan}
    return pd.DataFrame([{"side": side, "dist_mi": dist, "perf_ratio": pr[c], "cohort": c != "no12"} for c in cls])


def test_front_needs_performing_stepouts_outnumbering_rolled():
    so = pd.concat([_so("W", ["ok"] * 8 + ["rolled"] + ["no12"] * 18), _so("SW", ["rolled"] * 2 + ["no12"] * 7), _so("SE", ["ok"] * 3, dist=30.0)], ignore_index=True)
    fr = ex.front_sides(so)
    assert list(fr) == ["W"] and fr["W"]["ok"] == 8  # SE tests are beyond reach
    roles = ex.stepout_roles(so, fr)
    assert (roles[so.side == "W"] == "island").sum() == 26  # performing + too-new on the front; the rolled one is out
    assert set(roles[so.side == "SW"]) == {"excluded: rolled step-out", "excluded: no 12-mo yet, not a front side"}
    assert set(roles[so.side == "SE"]) == {"excluded: isolated test > reach"}


def test_stepout_class_uses_any_12mo_not_only_cohort():
    so = pd.DataFrame([{"side": "N", "dist_mi": 1.0, "perf_ratio": 0.93, "cohort": False}, {"side": "N", "dist_mi": 1.0, "perf_ratio": np.nan, "cohort": False}])
    assert list(ex.stepout_class(so)) == ["ok", "no12"]


def test_front_ratio_rule():
    assert ex.front_sides(_so("N", ["ok"] * 3 + ["rolled"] * 2)) == {}  # 3 ok < 2 x 2 rolled
    assert list(ex.front_sides(_so("N", ["ok"] * 4 + ["rolled"] * 2))) == ["N"]


# ---------------------------------------------------------------------------- core + polygon


def _block() -> tuple[Polygon, list[LineString], pd.DataFrame]:
    """A 3 x 2 mi block of N-S laterals, walked with the real step-2 metric."""
    lines = [LineString([(x, 0), (x, 2 * MI)]) for x in np.arange(0, 3 * MI + 1, 880.0)]
    p = eg.EdgeParams(pin_radius_ft=1320.0, close_ft=2640.0, ring_step_ft=100.0)
    body = eg.outline(lines, p).geoms[0]
    seg = eg.walk(body, lines, p)
    seg["perf_class"] = seg["perf_class_local"] = "unknown"
    seg["n_pre2016_outside"] = 0
    return body, lines, seg


def test_core_hugs_the_laterals_not_the_measuring_outline():
    body, lines, _ = _block()
    core = ex.core(body, lines, [], 1320.0)
    assert all(core.buffer(1.0).contains(ln) for ln in lines)
    assert core.area < body.area  # the r-dilated outline is never the extent (D21)
    assert abs(core.bounds[0] - 0.0) < 120 and abs(core.bounds[2] - 3 * MI) < 120


def test_extent_buffer_follows_the_sector_and_potash_holds_the_floor():
    body, lines, seg = _block()
    core = ex.core(body, lines, [], 1320.0)
    east = seg.side.isin(["E", "NE", "SE"])
    seg.loc[east, "kind"] = "gap"
    seg.loc[east, "length_ft"] = 8000.0  # 0.5 * 8000 * 0.75 = 3000 ft on the east
    sb = ex.segment_buffers(seg, BP)
    xy, six = ex.ring_samples(seg, body, 100.0)
    b, f = ex.sample_buffers(six, sb, BP.floor_ft)
    ext, _ = ex.build_extent(core, xy, b, f, None, BP)
    x0, _, x1, _ = ext.bounds
    assert x1 - 3 * MI == pytest.approx(3000.0, abs=200.0)
    assert -x0 == pytest.approx(1320.0, abs=200.0)
    assert ext.contains(core.buffer(-1.0))
    # the same rule with a potash polygon over the east side: held to the floor there
    sopa = shapely.box(3 * MI - 100, -MI, 5 * MI, 3 * MI)
    sb2 = ex.segment_buffers(seg, BP, sopa=sopa)
    b2, f2 = ex.sample_buffers(six, sb2, BP.floor_ft)
    ext2, _ = ex.build_extent(core, xy, b2, f2, sopa, BP)
    assert ext2.bounds[2] - 3 * MI == pytest.approx(1320.0, abs=200.0)


def test_point_rule_matches_polygon():
    body, lines, seg = _block()
    core = ex.core(body, lines, [], 1320.0)
    sb = ex.segment_buffers(seg, BP)
    xy, six = ex.ring_samples(seg, body, 100.0)
    b, f = ex.sample_buffers(six, sb, BP.floor_ft)
    ext, _ = ex.build_extent(core, xy, b, f, None, BP)
    rng = np.random.default_rng(0)
    pts = np.column_stack([rng.uniform(-MI, 4 * MI, 3000), rng.uniform(-MI, 3 * MI, 3000)])
    d = ex.CoreDistance(core).distance(pts, 5 * MI)
    from scipy.spatial import cKDTree

    nn = cKDTree(xy).query(pts)[1]
    inside_rule = d <= ex.point_buffer(nn, np.zeros(len(pts), bool), b, f)
    inside_poly = shapely.contains_xy(ext, pts[:, 0], pts[:, 1])
    near_edge = np.abs(d - ex.point_buffer(nn, np.zeros(len(pts), bool), b, f)) < 400  # smoothing + quantisation band
    assert (inside_rule == inside_poly)[~near_edge].all()


def test_ring_samples_are_distinct_sites():
    body, _, seg = _block()
    xy, six = ex.ring_samples(seg, body, 100.0)
    assert len(np.unique(np.round(xy, 1), axis=0)) == len(xy) and (six >= 0).all()


def test_edge_runs_cover_the_extent_boundary():
    body, lines, seg = _block()
    core = ex.core(body, lines, [], 1320.0)
    sb = ex.segment_buffers(seg, BP)
    xy, six = ex.ring_samples(seg, body, 100.0)
    b, f = ex.sample_buffers(six, sb, BP.floor_ft)
    ext, _ = ex.build_extent(core, xy, b, f, None, BP)
    runs = ex.edge_runs(ext, xy, six)
    assert sum(r["geom"].length for r in runs) == pytest.approx(ext.length, rel=0.02)
    assert {r["seg"] for r in runs} <= set(seg.index)


def test_capture_and_score():
    frac = ex.well_inside_fraction(np.array([0, 0, 1, 1, 2]), np.array([True, True, True, False, False]), 3)
    assert list(frac) == [1.0, 0.5, 0.0]
    cap = ex.captured(frac)
    s = ex.score(np.array([True, True, False]), np.array([False, False, True]), cap)
    assert s["tpr"] == 1.0 and s["fpr"] == 0.0 and s["j"] == 1.0


def test_diff_pieces_and_sides():
    gen = ex.as_multi(shapely.box(0, 0, 10 * MI, 10 * MI))
    edi = ex.as_multi(gen.union(shapely.box(10 * MI, 4 * MI, 12 * MI, 6 * MI)).difference(shapely.box(4 * MI, 0, 6 * MI, 1 * MI)))
    d = ex.diff(gen, edi, gen.centroid)
    assert d["added_sqmi"] == pytest.approx(4.0) and d["removed_sqmi"] == pytest.approx(2.0)
    sides = {p["kind"]: p["side"] for p in d["pieces"]}
    assert sides == {"added": "E", "removed": "S"}


# ---------------------------------------------------------------------------- geology round-trip


def test_prj_is_utm14n_us_feet():
    from pyproj import CRS

    ref = CRS.from_proj4("+proj=utm +zone=14 +datum=NAD83 +units=us-ft +no_defs")
    assert gio.GEOLOGY_CRS.equals(ref, ignore_axis_order=True)
    assert gio.GEOLOGY_CRS.axis_info[0].unit_name in ("US survey foot", "Foot_US")


def test_known_point_lands_in_the_ggx_frame():
    # a Delaware point: GGX grid easting is negative west of ~-104.4 (false easting included)
    p = gio.lonlat_to_geology([Point(-104.3, 31.9)])[0]
    assert p.x == pytest.approx(-4834.8, abs=1.0) and p.y == pytest.approx(11_619_496.5, abs=1.0)


def test_shapefile_round_trip_with_hole(tmp_path):
    outer = shapely.box(0, 0, 20_000, 20_000)
    poly = ex.as_multi(outer.difference(shapely.box(5_000, 5_000, 8_000, 8_000)))
    ll = eg.to_lonlat([shapely.affinity.translate(poly, 1_800_000, 11_600_000)])[0]
    g = gio.lonlat_to_geology([ll])[0]
    files = gio.write_layer(tmp_path / "BOX_T_extent_v1", "polygon", [g], [("BENCH", "C", 12, 0)], [["T"]])
    assert (tmp_path / "BOX_T_extent_v1.prj").read_text() == gio.ESRI_WKT and all(f.exists() for f in files)
    back = gio.read_extent(tmp_path / "BOX_T_extent_v1.shp", bench="T")
    assert back.symmetric_difference(g).area < 1.0 and len(back.geoms[0].interiors) == 1
    assert gio.read_extent(tmp_path / "BOX_T_extent_v1.shp", bench="OTHER").is_empty
    assert gio.check_frame(back, g) == ""
    assert "wrong CRS" in gio.check_frame(shapely.affinity.scale(back, 0.3048, 0.3048, origin=(0, 0)), g)
