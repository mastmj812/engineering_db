"""scripts.delete_superseded_vintage: a full delete is refused for a latest vintage, defaults to a dry run, and never names
the tables that must survive (pure checks; no database)."""
from pathlib import Path

from scripts import delete_superseded_vintage as dsv

SRC = Path(dsv.__file__).read_text(encoding="utf-8")
AVAILABLE = [("basin_research__Midland_Basin__2026Q3", False), ("basin_research__Midland_Basin__2026Q4", True),
             ("basin_research__Delaware_Basin__2026Q3", True)]


def test_only_a_superseded_report_can_be_deleted():
    assert dsv.refusal("basin_research__Midland_Basin__2026Q3", AVAILABLE) is None
    assert "LATEST" in dsv.refusal("basin_research__Midland_Basin__2026Q4", AVAILABLE)
    assert "LATEST" in dsv.refusal("basin_research__Delaware_Basin__2026Q3", AVAILABLE)   # the live Delaware vintage
    assert "not a report" in dsv.refusal("basin_research__Midland_Basin__2024Q1", AVAILABLE)


def test_it_is_a_dry_run_unless_go_and_refuses_before_any_delete():
    main = SRC[SRC.index("def main("):]
    assert main.index("if why:") < main.index("if not a.go:") < main.index("DELETE FROM")
    assert 'ap.add_argument("--go", action="store_true"' in SRC


def test_the_dsu_polygons_and_the_stick_id_map_are_never_deleted():
    deletes = [ln for ln in SRC.splitlines() if "DELETE FROM" in ln and not ln.lstrip().startswith(("#", "*"))]
    assert deletes and all('raw_intel."{' in ln and "report_name = %s" in ln for ln in deletes)
    assert "raw_novi_intel.pads" in dsv._KEPT_SQL and "stick_id_map" in dsv._KEPT_SQL             # counted before and after instead
    assert "c.column_name = 'report_name'" in dsv._TABLES_SQL                                      # stick_id_map has no report_name
