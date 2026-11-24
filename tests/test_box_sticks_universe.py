"""BOX forecasts on BOX sticks (docs/box_sticks_plan.md phase 6): the universe and the harness locations, DB-free.

Pins the five decisions of 2026-11-23 (docs/box_sticks/phase6-2026-11-23/DESIGN.md) where this layer carries them: the record
stick set only; a producing stick is never in the universe; a conflict or crowded stick carries no forecast in either basin;
every stored stick is in-extent; spacing and completed lateral are the generator's; a U-turn stick is one row.
"""
from types import SimpleNamespace

import pytest

from box import production as pr
from scripts import box_pud_run as bpr

SQL = pr._UNIVERSE_BOX_SQL
NOVI_COLS = ["stick_id", "report_version", "category", "basin", "bench", "in_scope", "formation_blueox", "recon_status", "pad_name", "ll_ft", "wkt",
             "mid_lon", "mid_lat", "stick_ft", "extent_id", "inside_share"]


def test_the_box_universe_reads_the_record_set_and_no_novi_stick_relation():
    assert "JOIN box.location_set t ON t.set_id = k.set_id AND t.is_record" in SQL
    assert "LEFT JOIN curated.box_location_status s ON s.location_id = k.location_id AND s.set_id = k.set_id" in SQL
    for novi in ("intel_locations", "intel_formation_blueox", "reconciled_inventory", "erebor_locations", "il.stick_id"):
        assert novi not in SQL, novi
    assert "k.basin = ANY (%(basins)s)" in SQL and "k.location_id AS stick_id" in SQL
    assert not any(w in SQL.upper() for w in ("INSERT ", "UPDATE ", "DELETE ", "CREATE ", "DROP "))
    for c in NOVI_COLS:                                              # the frame every reader of universe() already takes
        assert f" {c}" in SQL or f".{c}" in SQL or f"AS {c}" in SQL, c
    assert pr._UNIVERSE_SQL.count("curated.intel_locations il") == 1  # the Novi universe is untouched


def test_status_mapping_in_the_sql_decision_1():
    assert "WHERE COALESCE(s.status, 'open') <> 'producing'" in SQL            # a producing stick is not a location
    assert "CASE WHEN s.status IS NULL THEN 'not_reconciled' WHEN s.crowded THEN 'crowded' ELSE s.status END AS recon_status" in SQL
    assert pr.BOX_NOT_DRILLABLE == {"conflict", "crowded"}
    assert set(pr.BOX_RECON_STATUSES) == {"open", "permitted", "pending", "conflict", "crowded", "not_reconciled"}


def test_a_stick_is_one_line_one_midpoint_and_the_generators_lateral():
    assert "extensions.ST_LineMerge(extensions.ST_Collect(k.legs_geom, k.turn_geom))" in SQL      # legs + arc, one path
    assert "extensions.ST_AsText(k.legs_geom) AS legs_wkt" in SQL                                  # the legs, for proximity
    assert "k.completed_lateral_ft AS ll_ft, k.completed_lateral_ft AS stick_ft, k.spacing_ft, k.target_tvd_ft" in SQL
    # decision 3: a U-turn stick's point is midway between its two legs' midpoints, never heel to toe
    assert SQL.count("extensions.ST_LineInterpolatePoint(extensions.ST_GeometryN(k.legs_geom, 1), 0.5)") == 2
    assert "extensions.ST_LineInterpolatePoint(extensions.ST_GeometryN(k.legs_geom, 2), 0.5)), 0.5)" in SQL


def _row(**kw):
    base = {"category": "BOX", "in_scope": True, "basin": "delaware", "bench": "WCC", "formation_blueox": "WCC", "inside_extent": True,
            "recon_status": "open"}
    return SimpleNamespace(**{**base, **kw})


@pytest.mark.parametrize(("basin", "bench", "group"), [("delaware", "WCC", "WCC"), ("midland", "WCD", "MID_WCD")])
def test_conflict_and_crowded_box_sticks_carry_no_forecast_in_either_basin(basin, bench, group):
    covered = pr.classify(_row(basin=basin, bench=bench, formation_blueox=bench), (group,))
    assert covered in pr.COVERED
    for st in ("open", "permitted", "pending", "not_reconciled"):
        assert pr.classify(_row(basin=basin, bench=bench, formation_blueox=bench, recon_status=st), (group,)) == covered
    for st in ("conflict", "crowded"):
        assert pr.classify(_row(basin=basin, bench=bench, formation_blueox=bench, recon_status=st), (group,)) == pr.NOT_COVERED_CONFLICT


def test_a_novi_delaware_conflict_stick_is_classified_as_before():
    assert pr.classify(_row(category="PUD", recon_status="conflict"), ("WCC",)) == "covered"       # D1 stands for Novi sticks
    assert pr.classify(_row(category="PUD", recon_status="crowded"), ("WCC",)) == "covered"        # not a Novi status: no effect


class _Conn:
    def __init__(self, cols, rows):
        self.cols, self.rows, self.sql = cols, rows, []

    def cursor(self):
        conn = self

        class Cur:
            def __init__(self):
                self.description = [SimpleNamespace(name=c) for c in conn.cols]

            def __enter__(self):
                return self

            def __exit__(self, *a):
                return False

            def execute(self, sql, params=None):
                conn.sql.append(sql)

            def fetchall(self):
                return conn.rows

        return Cur()

    def rollback(self):
        pass


BOX_COLS = ["stick_id", "set_id", "report_version", "category", "basin", "bench", "in_scope", "formation_blueox", "recon_status", "pad_name",
            "pad_id", "well_name", "well_type", "n_legs", "ll_ft", "stick_ft", "spacing_ft", "target_tvd_ft", "wkt", "legs_wkt", "mid_lon", "mid_lat",
            "extent_id", "inside_share"]


def _box_rows(**over):
    def r(i, **kw):
        d = {"stick_id": 10_000_000 + i, "set_id": 24, "report_version": "2026Q3", "category": "BOX", "basin": "delaware", "bench": "WCC",
             "in_scope": True, "formation_blueox": "WCC", "recon_status": "open", "pad_name": "Unit 1", "pad_id": 10701, "well_name": f"10701-WCC-{i:02d}",
             "well_type": "single", "n_legs": 1, "ll_ft": 9900.0, "stick_ft": 9900.0, "spacing_ft": 1170.0, "target_tvd_ft": 12550.0,
             "wkt": "LINESTRING(-103.7 32.0, -103.7 32.03)", "legs_wkt": "MULTILINESTRING((-103.7 32.0, -103.7 32.03))", "mid_lon": -103.7,
             "mid_lat": 32.015, "extent_id": 27, "inside_share": 1.0, **kw}
        return tuple(d[c] for c in BOX_COLS)

    rows = [r(1), r(2, inside_share=0.2), r(3, inside_share=0.0), r(4, recon_status="crowded"), r(5, recon_status="conflict"),
            r(6, recon_status="permitted", well_type="uturn", n_legs=2, ll_ft=8030.0, stick_ft=8030.0)]
    return [r(1, **over)] + rows[1:] if over else rows


def test_every_stored_stick_is_in_extent_and_the_novi_rule_is_untouched():
    conn = _Conn(BOX_COLS, _box_rows())
    u = pr.universe(conn, covered=("WCC",), basins=["delaware"], source=pr.SOURCE_BOX)
    assert conn.sql == ["SET TRANSACTION READ ONLY", pr._UNIVERSE_BOX_SQL]
    assert list(u["inside_extent"]) == [True] * 6                                # decision 2: 0.2 and 0.0 inside are in-extent
    assert list(u["inside_share"]) == [1.0, 0.2, 0.0, 1.0, 1.0, 1.0]            # and the share stays on the row
    assert list(u["coverage"]) == ["covered", "covered", "covered", pr.NOT_COVERED_CONFLICT, pr.NOT_COVERED_CONFLICT, "covered"]
    assert pr.INSIDE_SHARE == 0.5                                                # the Novi universe keeps the 50 % rule
    with pytest.raises(ValueError, match="unknown universe source"):
        pr.universe(conn, covered=("WCC",), basins=["delaware"], source="sticks")


@pytest.mark.parametrize(("over", "msg"), [
    ({"stick_id": 1_600_001}, "Novi id"), ({"extent_id": None}, "no record extent"), ({"spacing_ft": None}, "no spacing"),
    ({"target_tvd_ft": None}, "no landing TVD"), ({"recon_status": "producing"}, "unknown status"), ({"in_scope": False}, "out of BOX scope"),
    ({"wkt": "MULTILINESTRING((0 0, 0 1), (1 1, 1 0))"}, "do not join into one line"), ({"set_id": 21}, "more than one record set")])
def test_a_universe_that_is_not_the_design_is_refused(over, msg):
    with pytest.raises(ValueError, match=msg):
        pr.universe(_Conn(BOX_COLS, _box_rows(**over)), covered=("WCC",), basins=["delaware"], source=pr.SOURCE_BOX)


def test_a_duplicated_stick_is_refused():
    rows = _box_rows()
    with pytest.raises(ValueError, match="duplicated stick ids"):
        pr.universe(_Conn(BOX_COLS, [*rows, rows[0]]), covered=("WCC",), basins=["delaware"], source=pr.SOURCE_BOX)


def test_locations_take_spacing_and_lateral_from_the_generator_and_search_no_neighbour(monkeypatch):
    u = pr.universe(_Conn(BOX_COLS, _box_rows()), covered=("WCC",), basins=["delaware"], source=pr.SOURCE_BOX)
    monkeypatch.setattr(bpr, "nearest_by_stick", lambda *a: pytest.fail("no D64 neighbour search on BOX sticks"))
    locs = bpr.locations(u, None, "WCC")
    assert [x["stick_id"] for x in locs] == [10_000_001, 10_000_002, 10_000_003, 10_000_006]      # the conflict and crowded sticks are out
    for x in locs:
        assert x["spacing_source"] == pr.SPACING_GENERATOR == "generator" and x["planned_spacing_ft"] == x["spacing_ft"] == 1170.0
        assert x["lateral_eff"] == x["lateral_ft"] and x["nearest"] is None and x["near_pdp_ft"] is None
        assert x["api10"] == f"pud{x['stick_id']}" and x["target_tvd_ft"] == 12550.0
    assert locs[-1]["n_legs"] == 2 and locs[-1]["lateral_ft"] == 8030.0                            # a U-turn stick: one location, both legs
    assert locs[0]["x"] == locs[1]["x"] and locs[0]["y"] == locs[1]["y"]


def test_a_mixed_universe_and_a_bad_number_are_refused():
    u = pr.universe(_Conn(BOX_COLS, _box_rows()), covered=("WCC",), basins=["delaware"], source=pr.SOURCE_BOX)
    mixed = u.copy()
    mixed.loc[0, "category"] = "PUD"
    with pytest.raises(SystemExit, match="mixes BOX sticks and Novi sticks"):
        bpr.locations(mixed, None, "WCC")
    bad = u.copy()
    bad.loc[1, "spacing_ft"] = 0.0
    with pytest.raises(SystemExit, match="not a positive number"):
        bpr.locations(bad, None, "WCC")
