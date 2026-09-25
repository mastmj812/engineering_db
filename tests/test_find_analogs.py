"""scripts/find_analogs.py — pure query builder + input parsing (DB-free)."""

from __future__ import annotations

import json
import re
from datetime import date

import pytest

from scripts.find_analogs import (
    OFFSET_GATE_FT,
    SCENARIOS,
    build_query,
    parse_near,
    polygon_geometry,
)


def test_no_filters_is_scorable_only_and_ordered():
    sql, p = build_query()
    assert p == {}
    assert "FROM curated.dev_scenario d" in sql
    assert "WHERE d.scorable" in sql
    assert sql.rstrip().endswith("ORDER BY d.first_production_date DESC, d.api10")


def test_values_are_bound_never_interpolated():
    sql, p = build_query(
        benches=["WCB_2"], scenarios=["underfill"], parent_benches=["WCA_1"],
        min_parent_age_days=730, near=(31.304, -101.816), radius_mi=8,
        fp_from=date(2019, 1, 1), min_months=12,
    )
    for literal in ("WCB_2", "underfill", "WCA_1", "730", "31.304", "101.816", "2019"):
        assert literal not in sql, literal
    assert p["benches"] == ["WCB_2"]
    assert p["scenarios"] == ["underfill"]
    assert p["parent_benches"] == ["WCA_1"]
    assert p["min_parent_age_days"] == 730
    assert (p["lat"], p["lon"]) == (31.304, -101.816)
    assert p["radius_m"] == pytest.approx(8 * 1609.344)
    assert p["min_months_m1"] == 11
    assert "dist_mi" in sql
    # every placeholder has a param and vice versa
    assert set(re.findall(r"%\((\w+)\)s", sql)) == set(p)


def test_aoi_geometry_mirrors_anduin_for_near_and_polygon():
    # anduin: wells.wellstick = COALESCE(Enverus lateral path, Novi stick,
    # straight SHL->BHL); lasso tests COALESCE(wellstick, sh_geom). Both AOI
    # forms here must use that same geometry, in that order.
    order = ["ell.lateral_geom", "w.wellstick_geom", "extensions.ST_MakeLine(", "ST_MakePoint(we.surface_lon"]
    for kw in ({"near": (31.3, -101.8), "radius_mi": 1}, {"polygon": "{}"}):
        sql, _ = build_query(**kw)
        assert "LEFT JOIN curated.enverus_lateral_lines ell ON ell.api10 = d.api10" in sql
        clause = sql.split("WHERE d.scorable", 1)[1]
        idx = [clause.index(tok) for tok in order]
        assert idx == sorted(idx), kw
        assert "COALESCE(" in clause
    near_sql, _ = build_query(near=(31.3, -101.8), radius_mi=1)
    assert "extensions.ST_DWithin((COALESCE(" in near_sql
    poly_sql, _ = build_query(polygon="{}")
    assert "extensions.ST_Intersects(COALESCE(" in poly_sql


def test_parent_bench_reads_bench_context_without_vertical_window():
    sql, p = build_query(parent_benches=["LSSH"], benches=["WCA_1"])
    assert "EXISTS (SELECT 1 FROM jsonb_each(d.bench_context) j WHERE" in sql
    assert "j.key = ANY(%(parent_benches)s)" in sql
    assert "parent_min_offset_ft')::numeric <= %(max_offset_ft)s" in sql
    assert p["max_offset_ft"] == OFFSET_GATE_FT
    # naming the pair IS the vertical spec: no dTVD cap, no side, not the gated arrays
    assert "max_dtvd_ft" not in p
    assert "parent_benches_below" not in sql.split("WHERE d.scorable")[1]
    assert "parent_nearest_dtvd_ft')::numeric >" not in sql


@pytest.mark.parametrize("side, frag", [("above", "::numeric < 0"), ("below", "::numeric > 0")])
def test_parent_side_and_dtvd_cap(side, frag):
    sql, p = build_query(parent_benches=["LSSH"], parent_side=side, max_dtvd_ft=700)
    assert f"(j.value ->> 'parent_nearest_dtvd_ft'){frag}" in sql
    assert "abs((j.value ->> 'parent_nearest_dtvd_ft')::numeric) <= %(max_dtvd_ft)s" in sql
    assert p["max_dtvd_ft"] == 700.0
    assert set(re.findall(r"%\((\w+)\)s", sql)) == set(p)


def test_parent_age_scopes_to_named_bench_or_class():
    sql, _ = build_query(parent_benches=["LSSH"], min_parent_age_days=730)
    assert "(j.value ->> 'parent_min_age_days')::int >= %(min_parent_age_days)s" in sql
    assert "d.youngest_parent_age_days" not in sql.split("WHERE d.scorable")[1]
    sql, _ = build_query(min_parent_age_days=730, max_parent_age_days=3000)
    assert "d.youngest_parent_age_days >= %(min_parent_age_days)s" in sql
    assert "d.oldest_parent_age_days <= %(max_parent_age_days)s" in sql


def test_offset_gate_constant_matches_sql50():
    from pathlib import Path

    body = (Path(__file__).resolve().parent.parent / "sql" / "50_dev_scenario.sql").read_text(encoding="utf-8")
    assert re.search(rf"parent_min_offset_ft'\)::numeric <= {OFFSET_GATE_FT}\s", body)


@pytest.mark.parametrize("kw, msg", [
    ({"scenarios": ["infill"]}, "unknown scenario"),
    ({"near": (31.3, -101.8)}, "go together"),
    ({"radius_mi": 5.0}, "go together"),
    ({"near": (31.3, -101.8), "radius_mi": 0}, "> 0"),
    ({"near": (31.3, -101.8), "radius_mi": 5, "polygon": "{}"}, "mutually exclusive"),
    ({"parent_side": "beside"}, "parent_side must be"),
    ({"parent_side": "above"}, "need --parent-bench"),
    ({"max_dtvd_ft": 700}, "need --parent-bench"),
])
def test_bad_filter_combinations_raise(kw, msg):
    with pytest.raises(ValueError, match=msg):
        build_query(**kw)


def test_scenario_whitelist_matches_sql50_classes():
    from pathlib import Path

    body = (Path(__file__).resolve().parent.parent / "sql" / "50_dev_scenario.sql").read_text(encoding="utf-8")
    classes = set(re.findall(r"THEN '(\w+)'", body)) | set(re.findall(r"ELSE '(\w+)'", body))
    assert classes == set(SCENARIOS)


def test_parse_near_order_and_range():
    assert parse_near("31.304,-101.816") == (31.304, -101.816)
    with pytest.raises(ValueError, match="out of range"):
        parse_near("-101.816,31.304")  # LON,LAT swapped
    with pytest.raises(ValueError, match="LAT,LON"):
        parse_near("31.3")


SQUARE = {"type": "Polygon", "coordinates": [[[-102, 31], [-101, 31], [-101, 32], [-102, 32], [-102, 31]]]}


def test_polygon_geometry_accepts_geometry_feature_collection():
    assert json.loads(polygon_geometry(SQUARE)) == SQUARE
    assert json.loads(polygon_geometry({"type": "Feature", "geometry": SQUARE, "properties": {}})) == SQUARE
    fc = {"type": "FeatureCollection", "features": [
        {"type": "Feature", "geometry": SQUARE}, {"type": "Feature", "geometry": SQUARE}]}
    g = json.loads(polygon_geometry(fc))
    assert g["type"] == "GeometryCollection" and len(g["geometries"]) == 2


def test_polygon_geometry_rejects_non_areas():
    with pytest.raises(ValueError, match="Polygon/MultiPolygon only"):
        polygon_geometry({"type": "Point", "coordinates": [-101.8, 31.3]})
    with pytest.raises(ValueError, match="no geometry"):
        polygon_geometry({"type": "FeatureCollection", "features": []})
