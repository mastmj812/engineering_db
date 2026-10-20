"""Novi DSU pad polygons: the 2026Q3 loader contract (etl/novi_intel) + the sql/67
static invariants. Pure — no database; shapefiles are synthesized in tmp_path."""

from __future__ import annotations

import io
import re
import zipfile
from pathlib import Path

import shapefile

from etl.novi_intel import load_shapefiles, paths

SQL_DIR = Path(__file__).resolve().parents[1] / "sql"


def _pad_shapefile_zip(fields: list[str], records: list[list]) -> bytes:
    """A zip holding one polygon shapefile (one square per record)."""
    shp, shx, dbf = io.BytesIO(), io.BytesIO(), io.BytesIO()
    w = shapefile.Writer(shp=shp, shx=shx, dbf=dbf, shapeType=shapefile.POLYGON)
    for f in fields:
        w.field(f, "C" if f in ("padName", "Operator", "Pad Name") else "N", decimal=2)
    for i, rec in enumerate(records):
        x, y = -103.5 + i * 0.01, 32.0
        w.poly([[[x, y], [x, y + 0.01], [x + 0.01, y + 0.01], [x + 0.01, y], [x, y]]])
        w.record(*rec)
    w.close()
    out = io.BytesIO()
    with zipfile.ZipFile(out, "w") as z:
        z.writestr("Pads.shp", shp.getvalue())
        z.writestr("Pads.shx", shx.getvalue())
        z.writestr("Pads.dbf", dbf.getvalue())
    return out.getvalue()


# --- nested 2026Q3 layout ---------------------------------------------------------

def test_nested_pad_member_picks_mid_cycle_in_both_basin_layouts():
    delaware = [
        "Permian Delaware Basin Report Q3 2026 (Shapefile Download)/Field_Explainer.xlsx",
        "Permian Delaware Basin Report Q3 2026 (Shapefile Download)/Economic_Strip_NPV_Pad_Summary.zip",
        "Permian Delaware Basin Report Q3 2026 (Shapefile Download)/Economic_Mid_Cycle_NPV_Pad_Summary.zip",
        "Permian Delaware Basin Report Q3 2026 (Shapefile Download)/Sticks_Mid_Cycle.zip",
    ]
    midland = ["Field_Explainer.xlsx", "Pad_NPV_Summary_Mid_Cycle.zip", "Pad_NPV_Summary_Strip.zip",
               "Sticks_Mid_Cycle.zip", "Sticks_Strip.zip"]
    assert paths.nested_pad_member(delaware).endswith("Economic_Mid_Cycle_NPV_Pad_Summary.zip")
    assert paths.nested_pad_member(midland) == "Pad_NPV_Summary_Mid_Cycle.zip"
    assert paths.nested_pad_member(["Sticks_Mid_Cycle.zip", "Field_Explainer.xlsx"]) is None


def test_pad_source_reads_nested_zip_without_extracting(tmp_path):
    inner = _pad_shapefile_zip(
        ["padName", "Operator", "NPV5_Sum", "LL_Sum", "WellCnt"],
        [["Pad A", "Op", 1.0, 10000.0, 2], ["Pad B", "", 0.0, 0.0, 0], ["Pad C", "", 0.0, 0.0, 0]],
    )
    outer = tmp_path / "shapefiles-midland-basin-q3-2026.zip"
    with zipfile.ZipFile(outer, "w") as z:
        z.writestr("Pad_NPV_Summary_Strip.zip", inner)
        z.writestr("Pad_NPV_Summary_Mid_Cycle.zip", inner)
        z.writestr("Sticks_Mid_Cycle.zip", b"not read")
    src = paths.pad_source("midland", root=tmp_path)
    assert src == (outer, "Pad_NPV_Summary_Mid_Cycle.zip")
    reader = load_shapefiles._open_reader(*src)
    assert len(reader) == 3
    assert [p.name for p in tmp_path.iterdir()] == [outer.name]  # nothing extracted


def test_pad_source_falls_back_to_a_directly_shipped_pad_zip(tmp_path):
    direct = tmp_path / "sub" / "Delaware Pad Shapefile.zip"
    direct.parent.mkdir()
    direct.write_bytes(_pad_shapefile_zip(["Pad Name"], [["Pad A"]]))
    assert paths.pad_source("delaware", root=tmp_path) == (direct, None)


# --- DBF record -> raw_novi_intel.pads row ------------------------------------------

def test_pad_row_2026q3_delaware_fields():
    rec = {"padName": " Delaware Pad 893 ", "Operator": "", "NPV0_Sum": 1.5, "NPV5_Sum": 2.0,
           "NPV10_Sum": 3.0, "NPV15_Sum": 4.0, "NPV20_Sum": 5.0, "NPV25_Sum": 6.0,
           "LL_Sum": 20000.0, "WellCnt": 2}
    row = load_shapefiles.pad_row("delaware", "2026Q3", rec)
    assert dict(zip(load_shapefiles.PAD_COLS, row)) == {
        "basin": "delaware", "report_version": "2026Q3", "pad_name": "Delaware Pad 893",
        "operator": None, "npv0": 1.5, "npv5": 2.0, "npv10": 3.0, "npv15": 4.0, "npv20": 5.0,
        "npv25": 6.0, "ll_sum_ft": 20000.0, "well_cnt": 2,
    }


def test_pad_row_2026q3_midland_has_no_npv0():
    rec = {"padName": "Undeveloped Pad C 1", "Operator": "White Rock Oil & Gas", "NPV5_Sum": 0.0,
           "NPV10_Sum": 0.0, "NPV15_Sum": 0.0, "NPV20_Sum": 0.0, "NPV25_Sum": 0.0,
           "LL_Sum": 3450.0, "WellCnt": 1}
    row = dict(zip(load_shapefiles.PAD_COLS, load_shapefiles.pad_row("midland", "2026Q3", rec)))
    assert row["npv0"] is None
    assert row["operator"] == "White Rock Oil & Gas"
    assert (row["ll_sum_ft"], row["well_cnt"]) == (3450.0, 1)


def test_pad_row_3q25_legacy_fields_still_map():
    rec = {"Pad Name": "Pad 1", "NPV5": 1.0, "NPV10": "", "SUM_NPV25": 9.0}
    row = dict(zip(load_shapefiles.PAD_COLS, load_shapefiles.pad_row("delaware", "3Q25", rec)))
    assert row["pad_name"] == "Pad 1"
    assert (row["npv5"], row["npv10"], row["npv25"]) == (1.0, None, 9.0)
    assert row["well_cnt"] is None and row["ll_sum_ft"] is None


def test_pads_vintage_uses_the_share_label():
    # sql/67 joins pads to curated.intel_locations ON report_version ('2026Q3').
    assert re.fullmatch(r"\d{4}Q[1-4]", paths.PADS_REPORT_VERSION)
    assert paths.REPORT_VERSION == "3Q25"  # land grid / outline stay frozen


# --- sql/67 static invariants ---------------------------------------------------------

def _sql67() -> str:
    return (SQL_DIR / "67_intel_pad_geom_v3.sql").read_text(encoding="utf-8")


def _novi_pad_cte(body: str) -> str:
    m = re.search(r"WITH novi_pad AS \((.*?)\n\),", body, re.S)
    assert m, "novi_pad CTE not found"
    lines = [ln.split("--", 1)[0].rstrip() for ln in m.group(1).splitlines()]
    return "\n".join(ln for ln in lines if ln.strip())


def test_sql67_novi_pad_cte_identical_in_both_matviews():
    sql = _sql67()
    member = sql[sql.index("CREATE MATERIALIZED VIEW curated.intel_pad_member"):
                 sql.index("CREATE MATERIALIZED VIEW curated.intel_pad_geom")]
    geom = sql[sql.index("CREATE MATERIALIZED VIEW curated.intel_pad_geom"):]
    assert _novi_pad_cte(member) == _novi_pad_cte(geom)


def test_sql67_joins_polygons_on_the_same_vintage_and_keeps_330ft():
    sql = _sql67()
    assert sql.count("np.report_version = il.report_version") == 1
    assert sql.count("np.report_version = g.report_version") == 1
    # 330 ft geodesic tolerance (membership) and hull buffer (fallback).
    assert sql.count("100.584") >= 2
    # sql/46 1-mile split for strays / names without a polygon.
    assert "1609.344" in sql


def test_sql46_is_retired():
    text = (SQL_DIR / "46_intel_pad_clusters.sql").read_text(encoding="utf-8")
    assert "RETIRED" in text and "DO NOT RUN" in text
    assert "CREATE" not in "\n".join(ln for ln in text.splitlines() if not ln.startswith("--"))
