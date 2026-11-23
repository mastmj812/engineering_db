"""The BOX sticks cutover, warehouse half (docs/box_sticks_plan.md phase 6): sql/22, sql/78 and their apply script, DB-free.

Pins: the undrilled arm of curated.erebor_locations is the RECORD BOX stick set, never a Novi relation; a producing stick is
not a row; ids keep the sign convention; the Novi sticks survive column for column in curated.novi_stick_locations for
deal-intake; the swap is one transaction that re-creates the land team's view and checks counts by identity.
"""
import re
from pathlib import Path

from scripts import apply_box_stick_locations as app

ROOT = Path(__file__).resolve().parent.parent
SQL22 = (ROOT / "sql" / "22_erebor_locations.sql").read_text(encoding="utf-8")
SQL78 = (ROOT / "sql" / "78_novi_stick_locations.sql").read_text(encoding="utf-8")
BODY = SQL22[SQL22.index("CREATE MATERIALIZED VIEW curated.erebor_locations AS"):SQL22.index("WITH DATA;")]
BOX_ARM, PDP_ARM = BODY.split("UNION ALL")


def _cols(arm: str) -> list[str]:
    sel = arm[arm.index("SELECT") + 6:arm.rindex("\nFROM ")]
    sel = re.sub(r"--[^\n]*", "", sel)
    out, depth, cur = [], 0, ""
    for ch in sel:
        depth += ch == "("
        depth -= ch == ")"
        if ch == "," and depth == 0:
            out.append(cur)
            cur = ""
        else:
            cur += ch
    out.append(cur)
    return [re.split(r"\bAS\b", c)[-1].strip().split(".")[-1].split()[-1] for c in out if c.strip()]


def test_the_undrilled_arm_is_the_record_box_stick_set():
    assert "FROM box.location_stick k" in BOX_ARM and "JOIN box.location_set t ON t.set_id = k.set_id AND t.is_record" in BOX_ARM
    assert "LEFT JOIN curated.box_location_status s ON s.location_id = k.location_id AND s.set_id = k.set_id" in BOX_ARM
    for novi in ("intel_locations", "intel_formation_blueox", "reconciled_inventory", "intel_pdp_support"):
        assert novi not in BOX_ARM, novi
    assert "WHERE COALESCE(s.status, 'open') <> 'producing'" in BOX_ARM                 # a producing stick is a well, not a location
    assert "k.location_id                      AS stick_id" in BOX_ARM and "'BOX'::text                        AS category" in BOX_ARM
    assert "CASE WHEN s.crowded THEN 'crowded' ELSE s.status END AS recon_status" in BOX_ARM
    assert "k.target_tvd_ft                    AS tvd" in BOX_ARM and "k.completed_lateral_ft             AS ll_ft" in BOX_ARM


def test_a_stick_is_one_linestring_with_its_turn_arc():
    assert "extensions.ST_LineMerge(extensions.ST_Collect(k.legs_geom, k.turn_geom))" in BOX_ARM
    assert "::extensions.geometry(LineString, 4326) AS wellstick_geom" in BOX_ARM
    assert "ST_" not in re.sub(r"extensions\.ST_", "", BOX_ARM)                         # PG17: every PostGIS call schema-qualified


def test_both_arms_have_the_same_columns_in_the_same_order():
    box, pdp = _cols(BOX_ARM), _cols(PDP_ARM)
    assert box == pdp and len(box) == 49 and box[0] == "stick_id" and box[-2:] == ["pad_id", "wellstick_geom"]
    assert "k.pad_id," in BOX_ARM and "NULL::bigint                       AS pad_id" in PDP_ARM          # Highgrade groups BOX sticks by DSU id
    assert "-(we.api10::bigint)                AS stick_id" in PDP_ARM and "'PDP'::text                        AS category" in PDP_ARM


def test_the_novi_sticks_move_column_for_column_and_deal_intake_reads_them_there():
    novi = SQL78[SQL78.index("CREATE MATERIALIZED VIEW curated.novi_stick_locations AS"):SQL78.index("WITH DATA;")]
    assert _cols(novi) == [c for c in _cols(PDP_ARM) if c != "pad_id"]                 # the shape erebor_locations had before the cutover
    assert "FROM curated.intel_locations il" in novi and "WHERE il.category IN ('PUD', 'RES')" in novi
    assert "CREATE UNIQUE INDEX idx_novi_stick_locations_pk" in SQL78
    assert "USING GIST ((wellstick_geom::extensions.geography))" in SQL78               # deal-intake's ST_DWithin on geography
    di = (ROOT / "dealintake" / "warehouse.py").read_text(encoding="utf-8")
    assert di.count("FROM curated.novi_stick_locations el") == 1 and di.count("JOIN curated.novi_stick_locations el") == 1
    assert "FROM curated.erebor_locations" not in di and "JOIN curated.erebor_locations" not in di


def test_the_quarterly_rebuild_recreates_the_novi_table_before_sql22():
    src = (ROOT / "scripts" / "apply_erebor_locations.py").read_text(encoding="utf-8")
    assert src.index("cur.execute(novi)") < src.index("cur.execute(erebor)") and "78_novi_stick_locations.sql" in src


def test_the_swap_is_one_transaction_in_order_and_recreates_the_land_teams_view():
    assert app.FILES == ("78_novi_stick_locations.sql", "22_erebor_locations.sql", "26_geography_indexes.sql", "31_comments.sql")
    src = Path(app.__file__).read_text(encoding="utf-8")
    assert "conn.autocommit = False" in src and src.index("recreate_box_scout(cur)") > src.index("for i, name in enumerate(FILES[:2], start=2):")
    assert "if ck.bad or not a.go:" in src and src.index("conn.rollback()") < src.index("conn.commit()")
    assert "REFRESH MATERIALIZED VIEW CONCURRENTLY curated.erebor_locations" in src[src.index("conn.commit()"):]   # only after the commit


class _Cur:
    """Answers the preflight only."""

    def __init__(self, rec, expect, odd=0, low=10_046_716):
        self.answers = [rec, expect, [(odd,)], [(low,)], [("PUD", 5), ("RES", 2), ("PDP", 3)], [(7,)], [("delaware", 2), ("midland", 1)]]

    def execute(self, sql, params=None):
        self.rows = self.answers.pop(0)
        return self

    def fetchall(self):
        return self.rows

    def fetchone(self):
        return self.rows[0]


def test_preflight_refuses_a_missing_record_set_an_unjudged_stick_and_a_broken_path():
    ok = app.Checks()
    before = app.preflight(_Cur([("delaware", 24), ("midland", 25)], [("delaware", 9, 10, 0), ("midland", 4, 4, 0)]).execute, ok)
    assert not ok.bad and before["expect"] == {"delaware": (9, 10, 0), "midland": (4, 4, 0)} and before["novi"] == 7
    for kw, word in (({"rec": [("delaware", 24)]}, "one record BOX stick set per basin"), ({"expect": [("delaware", 9, 10, 3), ("midland", 4, 4, 0)]}, "nightly status row"),
                     ({"odd": 2}, "one LineString"), ({"low": 1_600_000}, "never a Novi id")):
        ck = app.Checks()
        args = {"rec": [("delaware", 24), ("midland", 25)], "expect": [("delaware", 9, 10, 0), ("midland", 4, 4, 0)], **kw}
        app.preflight(_Cur(**args).execute, ck)
        assert len(ck.bad) == 1 and word in ck.bad[0], (kw, ck.bad)
