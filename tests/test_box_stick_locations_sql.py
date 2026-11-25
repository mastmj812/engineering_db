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
    # phase 7 item 4 (2026-11-25): deal-intake's LOCATIONS are BOX sticks. Phase 8 step 1: the comparison join reads
    # the Novi decline parameters from curated.intel_locations + intel_formation_blueox, so the Novi stick table
    # (sql/78) has no reader left in deal-intake and can be retired.
    assert "FROM curated.novi_stick_locations" not in di and "JOIN curated.novi_stick_locations" not in di
    assert "JOIN curated.intel_locations il ON il.stick_id = a.stick_id" in di
    assert "JOIN curated.intel_formation_blueox fb ON fb.stick_id = a.stick_id" in di
    assert "FROM box.location_stick s" in di and "ls.is_record" in di and "st.counts_as_inventory" in di
    assert "def novi_sticks(" not in di
    assert "FROM curated.erebor_locations" not in di and "JOIN curated.erebor_locations" not in di


def test_no_chain_script_builds_a_retired_novi_relation():
    """BOX sticks phase 8 step 2: sql/25, sql/30 and sql/78 are built by no script of the quarterly or the tag chain, and
    sql/31 comments none of them (so it applies whether or not they still stand on live)."""
    from scripts import apply_formation_tag_overrides as afo
    from scripts import apply_formation_tag_rule as atr

    assert set(afo.RETIRED) == {"curated.net_new_pdp", "curated.intel_pdp_support", "curated.novi_stick_locations"}
    assert not set(afo.RETIRED) & set(afo.CHAIN) and not set(afo.RETIRED) & set(atr.RECREATED_BY)
    tail = " ".join(" ".join(c) for c in atr.TAIL)
    for name in ("25_net_new_pdp", "apply_intel_pdp_support", "78_novi_stick_locations", "novi-sticks-only"):
        assert name not in tail, name
    for script in ("apply_erebor_locations.py", "apply_box_stick_locations.py"):
        src = (ROOT / "scripts" / script).read_text(encoding="utf-8")
        assert "78_novi_stick_locations.sql" not in src and "FROM curated.novi_stick_locations" not in src, script
    comments = (ROOT / "sql" / "31_comments.sql").read_text(encoding="utf-8")
    for rel in afo.RETIRED:
        assert f"COMMENT ON COLUMN {rel}." not in comments and f"COMMENT ON MATERIALIZED VIEW {rel} " not in comments, rel
    skill = (ROOT / ".claude" / "skills" / "novi-quarterly-reload" / "SKILL.md").read_text(encoding="utf-8")
    block = skill[skill.index("python -m scripts.load_intel_sf --curated"):skill.index("26_geography_indexes.sql")]
    assert "25_net_new_pdp" not in block and "apply_intel_pdp_support" not in block and "--after-reload" in block


def test_a_retired_matview_still_on_live_does_not_block_the_tag_chain():
    """From the 2026-11-24 cutover the seed reload's preflight refused: curated.novi_stick_locations sat below
    formation_blueox and was not in CHAIN. A retired matview is neither refreshed nor required."""
    from scripts import apply_formation_tag_overrides as afo
    from scripts import apply_formation_tag_rule as atr

    parents = {m: set() for m in afo.CHAIN} | {r: {"curated.intel_formation_blueox"} for r in afo.RETIRED}
    assert afo.chain_problems(afo.CHAIN, parents) == []
    assert afo.chain_problems(afo.CHAIN, parents | {"curated.some_new_matview": set()}) == [
        "live matview missing from CHAIN: curated.some_new_matview"]
    closure = {o: "m" for o in atr.RECREATED_BY} | {r: "m" for r in afo.RETIRED}
    assert atr.cascade_problems(closure)[0] == []


# ---- phase 7 item 2: nothing here is derived from Novi Intelligence, and a quarterly reload drops nothing an app reads ----
NOVI_RELATIONS = ("intel_locations", "intel_formation_blueox", "reconciled_inventory", "intel_pdp_support", "net_new_pdp",
                  "novi_stick_locations", "raw_intel.")


def test_no_arm_reads_a_novi_intelligence_relation():
    code = re.sub(r"--[^\n]*", "", BODY)                                             # comments may name what was removed
    for novi in NOVI_RELATIONS:
        assert novi not in code, novi
    assert re.findall(r"(?:FROM|JOIN)\s+((?:curated|box|raw_novi_intel)\.\w+)", code) == [
        "box.location_stick", "box.location_set", "curated.box_location_status", "raw_novi_intel.pads", "curated.wells_enriched"]


def test_the_shape_is_unchanged_and_the_novi_columns_are_typed_nulls():
    assert _cols(BOX_ARM) == _cols(PDP_ARM) and len(_cols(PDP_ARM)) == 49
    for arm in (BOX_ARM, PDP_ARM):
        assert re.search(r"NULL::double precision\s+AS rqs,", arm) and re.search(r"NULL::text\s+AS rqt,", arm)
    assert re.search(r"NULL::text\s+AS recon_status,", PDP_ARM)                       # a producing well carries no tag


def test_the_quarterly_chain_keeps_the_producer_objects_and_ends_on_the_comments():
    from scripts import apply_erebor_locations as ael
    from scripts import apply_formation_tag_rule as atr
    from scripts import apply_reconciled_inventory as ari

    ok = [(r, "v" if r in ("wells_enriched", "dev_scenario") else "m", True) for r in ari.REFERENCE]
    assert ari.reference_problems(ok) == []
    assert ari.reference_problems(ok[1:]) == ["curated.producing_reference is missing"]
    assert ari.reference_problems([("producing_reference", "m", False), *ok[1:]]) == ["curated.producing_reference is not populated"]
    src = Path(ari.__file__).read_text(encoding="utf-8")
    main = src[src.index("def main("):]
    assert "20_producing_reference.sql" not in main and "rebuild_reference()" in main and "check_reference()" in main
    assert main.index("if a.rebuild_reference:") < main.index("check_reference()") < main.index("68_reconcile_all_sticks.sql")
    only = Path(ael.__file__).read_text(encoding="utf-8")
    only = only[only.index("def after_reload("):only.index("def main(")]
    assert "31_comments.sql" in only and "22_erebor_locations.sql" not in only and "recreate_box_scout" not in only
    assert "curated.erebor_locations is missing or empty" in only
    # a structural rebuild (sql/16 dropped the reference) still rebuilds it, and still ends with the full apply
    assert [atr.PY, "-m", "scripts.apply_reconciled_inventory", "--rebuild-reference"] in atr.TAIL
    assert [atr.PY, "-m", "scripts.apply_erebor_locations"] in atr.TAIL


def test_the_applier_checks_the_catalogue_for_novi_reads():
    src = Path(app.__file__).read_text(encoding="utf-8")
    assert "the relation reads no Novi Intelligence relation" in src and "q(READS_SQL)" in src
    assert "curated.net_new_pdp" in app.NOVI_DERIVED and "pg_depend" in app.READS_SQL


def test_the_swap_is_one_transaction_in_order_and_recreates_the_land_teams_view():
    assert app.FILES == ("22_erebor_locations.sql", "26_geography_indexes.sql", "31_comments.sql")
    src = Path(app.__file__).read_text(encoding="utf-8")
    assert "conn.autocommit = False" in src and src.index("recreate_box_scout(cur)") > src.index("for i, name in enumerate(FILES[:1], start=2):")
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
