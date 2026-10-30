"""Step 19 (basin parameterization, D130 / D132): DB-free checks that every basin literal now comes from box/basin.py, that the
Delaware values are the ones the Delaware record was built with, and that the Midland refuses what step 20 / 21 still measures."""

from __future__ import annotations

from pathlib import Path

import pytest

from box import analog as an
from box import basin as bsn
from box import bench_qc as bq
from box import extent_package as pkg
from box import extent_report as er
from box import hindcast_production as hp
from box import production as pr
from box import refresh13 as r13
from scripts import box_prune_runs as prune

ROOT = Path(__file__).resolve().parents[1]
_ENG = Path("C:/Users/MichaelMast/Blue Ox Resources/Engineering - General")


def test_delaware_values_are_the_pre_step19_literals():
    d = bsn.get("delaware")
    assert an.DF_DELAWARE == d.df_terminal == 0.08
    assert bq.STATE_LINE_LAT == d.state_line_lat == 32.0
    assert (er.EDGE.pin_radius_ft, er.EDGE.close_ft) == (2640.0, 3960.0)  # D23
    assert hp.NOVI_REPORT_NAME == "basin_research__Delaware_Basin__2025Q3"
    assert pkg.GRID_ROOTS == (_ENG / "Grids" / "Delaware" / "Structure", _ENG / "Structure Grids" / "Delaware")
    assert an.BASIN == bq.BASIN == "delaware"


def test_midland_is_the_gate18_decisions_and_refuses_the_unmeasured():
    m = bsn.get("midland")
    assert m.df_terminal == 0.06  # D132
    assert m.state_line_lat is None and pkg.grid_roots("midland") == () and pkg.grid_root("midland") is None
    assert bsn.novi_report("midland", "2025Q3") == "basin_research__Midland_Basin__2025Q3"
    me = er.edge_params("midland")  # D134 A: the Midland adopts the Delaware D23 r / c
    assert (me.pin_radius_ft, me.close_ft) == (er.EDGE.pin_radius_ft, er.EDGE.close_ft)
    with pytest.raises(ValueError, match="step 20a"):
        bsn.require(None, "midland", "a parameter", "step 20a")  # an unset parameter still refuses by name
    with pytest.raises(ValueError, match="unknown basin"):
        bsn.get("permian")


def test_a_run_is_one_basin():
    assert pr.run_basin(["WCA", "BS2_S", "AVA_0"]) == "delaware"
    pr.PRODUCTION_BENCHES["_MID_TEST"] = ("midland", "WCA_1", frozenset({"WCA_1"}))
    try:
        with pytest.raises(ValueError, match="D130"):
            pr.run_basin(["WCA", "_MID_TEST"])
        assert pr.group_basin("_MID_TEST") == "midland"
    finally:
        del pr.PRODUCTION_BENCHES["_MID_TEST"]
    assert "il.basin = ANY (%(basins)s)" in pr._UNIVERSE_SQL  # the universe is the run's basin's
    assert "f.basin_blueox = %(basin)s" in pr._PDP_SQL


def test_prune_keeps_one_record_per_basin():
    # (run_id, is_record, superseded_by, n_pud, n_month, n_priced, basin)
    runs = [(19, True, None, 1, 1, 0, "delaware"), (20, False, None, 1, 1, 0, "delaware"),
            (21, True, None, 1, 1, 0, "midland"), (22, False, None, 1, 1, 3, "midland")]
    assert prune.records_by_basin(runs) == {"delaware": [19], "midland": [21]}
    assert prune.select_prune(runs) == [20]
    assert prune.select_prune(runs, include_priced=True) == [20, 22]
    assert prune.select_prune(runs, include_priced=True, basin="midland") == [22]


def test_refresh_is_one_basin():
    c = r13.chain("docs/box/pool-x", "runs/x", 14, "delaware")
    assert any("--basin delaware" in s["cmd"] and "prune" in s["cmd"] for s in c)
    assert "%(basin)s" in r13.STATE_SQL and "r.basin = %(basin)s" in r13.STATE_SQL
    assert r13.EXTENT_SQL.count("%(basin)s") == 2
    with pytest.raises(ValueError, match="step 23"):
        r13.groups_for("midland")


def test_midland_bench_summary_skips_the_state_line():
    from tests.test_box_bench_qc import _frame

    d = bq.score_consensus(bq.prepare(_frame(30, 0, 50, 50)))
    s = bq.bench_summary(d, "WCA_1", "midland")
    assert s["border_step"]["verdict"] == "not_applicable" and s["state_line"] == [] and s["state_mismatch_n"] is None
    dl = bq.bench_summary(d, "WCA_1")  # the Delaware default is unchanged
    assert dl["border_step"]["verdict"] != "not_applicable" and dl["state_line"]


def test_sql70_is_one_record_per_basin():
    s = (ROOT / "sql" / "70_box_record_per_basin.sql").read_text(encoding="utf-8")
    assert "CREATE UNIQUE INDEX IF NOT EXISTS box_forecast_run_record_basin_uq ON box.forecast_run (basin) WHERE is_record;" in s
    assert "DROP INDEX IF EXISTS box.box_forecast_run_record_uq;" in s
    assert "CHECK (basin IN ('delaware', 'midland'))" in s


def test_no_record_reader_assumes_one_record():
    """Every `WHERE is_record` read of box.forecast_run in box/ and scripts/ names a basin, or is a per-basin flip / identity."""
    allowed = {"apply_box_pud_forecast.py", "apply_box_scout_locations.py", "box_prox_record.py", "box_prune_runs.py", "box_pud_run.py",
               "gen_data_dictionary.py", "apply_box_run_basin.py"}
    bad = []
    for p in [*(ROOT / "box").glob("*.py"), *(ROOT / "scripts").glob("*.py")]:
        if p.name in allowed:
            continue
        for i, line in enumerate(p.read_text(encoding="utf-8").splitlines(), 1):
            if "forecast_run" in line and "is_record" in line and "basin" not in line:
                bad.append(f"{p.name}:{i}")
    assert not bad, bad


def test_a_basin_without_grids_never_borrows_the_delaware_ones(tmp_path, monkeypatch):
    # step 19 refused the visual check outside the Delaware; step 20a draws it grid-free. Either way the Midland WCC map
    # must never read the Delaware WCC grid.
    import datetime as dt

    import pandas as pd
    from shapely.geometry import LineString, Polygon

    from box import family_extent as fe

    def no_grid(*a, **k):
        raise AssertionError("a Midland map read a structure grid")

    monkeypatch.setattr(pkg, "require_grid", no_grid)
    wells = pd.DataFrame({"geom": [LineString([(0, 0), (0, 10000)]), LineString([(3000, 0), (3000, 10000)])], "evidence": [True, False],
                          "oil12_kft": [20000.0, None], "first_production_date": [dt.date(2020, 1, 1), dt.date(2012, 1, 1)]})
    ext = Polygon([(-2000, -2000), (5000, -2000), (5000, 12000), (-2000, 12000)])
    v = fe.visual_check_png("WCC", wells, ext, ext, tmp_path / "x.png", basin="midland")
    assert (tmp_path / "x.png").exists() and v["n_inside"] == 1
