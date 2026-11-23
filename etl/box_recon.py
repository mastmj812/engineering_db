"""Nightly BOX sticks reconciliation (sql/74; docs/box_sticks_plan.md phase 5; docs/box_sticks/phase5b-2026-11-19).

Runs inside the curated refresh, after the matviews it reads (curated.wells, curated.well_lateral_survey,
curated.formation_blueox, curated.formation_blueox_tvd, through curated.wells_enriched). One pass, pure SQL:

  1. judge every stick of the RECORD box.location_set per basin against today's wells (JUDGE_SQL);
  2. list the DSU x bench holding a producing well of that bench that the record set never read (STALE_SQL);
  3. circuit breaker: more than max(200, 1 %) of locations changed against the previous night with the same record
     sets and the same predicate version writes nothing but the run row;
  4. write the log rows of what changed, replace curated.box_location_status and curated.box_dsu_bench_stale, and add the
     meta.box_recon_run row, in ONE transaction.

It READS schema box and never writes it. It forecasts nothing and holds no economics. Status is recomputed every night,
not latched; only `status_since` / `stale_since` are carried. It never moves, adds or removes a stick: regeneration is a
periodic, explicit-go operation and the stale list is its work list.

The rule (decisions of 2026-11-18, plan decision table):
  * only a PRODUCING well (first production date) takes a stick out. A matching well that is drilled but not producing
    sets `pending`; an approved permit sets `permitted`; both stay in inventory.
  * grain = stick LEG against well. Share of the leg inside the well's 150 ft (46 m) flat-ended corridor: one well at
    >= 0.5 = matched; two or more at >= 0.5, or the best in [0.3, 0.5) = conflict.
  * same bench = same code within 500 ft of the stick's target TVD, or within 150 ft whatever the tag; never WCA_1
    against WCA_2 in a DSU the set recorded as co-developed. A well with no depth evidence is taken at the DSU's landing
    of its tagged bench where that bench has a row, on its formation family otherwise (match_basis = 'planned').
  * crowded = an open / permitted / pending stick inside the record set's OWN no-place envelope (box.location_set.cfg ->
    generator) of a producing well: alongside >= min_overlap, and at least half of the alongside length inside the
    sideways limit (the generator's median distance).
  * the well line is the one generator 0.12 reads: a surface step-out dropped, a real U-turn on its survey path.

In the nightly the step is soft: any failure is logged, a `failed` run row is written if possible, and the previous
tables stay. Before sql/74 is applied, or while no basin has a record set, it is a no-op.

    python -m etl.box_recon --dry-run     # read-only: judge + stale, print the counts, write nothing
    python -m etl.box_recon --write       # what the nightly does
    python -m etl.box_recon --write --allow-breaker   # manual, after a reviewed change of rule or of record set
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
import time
from typing import Any

logger = logging.getLogger(__name__)

VERSION = "box_recon_1"
TABLES = ("meta.box_recon_run", "curated.box_location_status", "curated.box_location_status_log", "curated.box_dsu_bench_stale")
CORRIDOR_M = 46                     # +-150 ft (sql/20)
MATCH, CONFLICT = 0.5, 0.3          # 0.3: Michael 2026-11-18 (the generator places a row beside a well alongside under 30 %)
SAME_CODE_FT, ANY_TAG_FT = 500, 150  # sql/68
MIN_DEPTH_FT = 4000                 # box.tag_scoreboard.MIN_EVIDENCE_TVD_FT
STEP_OUT_DEG = 15                   # box.sticks.core.STEP_OUT_DEG
GATE_M = 804.672                    # 2,640 ft: the generator's pair gate; "alongside" is measured inside it
MEMBER = 0.30                       # rule 9: a well belongs to a DSU with >= 30 % of its line inside
BREAKER_MIN, BREAKER_SHARE = 200, 0.01
TIMEOUT = "600s"

PARAMS = {"min_depth": MIN_DEPTH_FT, "step_out": STEP_OUT_DEG, "corridor_m": CORRIDOR_M, "gate_m": GATE_M, "same_code_ft": SAME_CODE_FT,
          "any_tag_ft": ANY_TAG_FT, "match": MATCH, "conflict": CONFLICT, "member": MEMBER}

# The well line as generator 0.12 reads it. {e} = curated.wells_enriched alias, {sv} = curated.well_lateral_survey alias.
_LINE = """
CASE WHEN COALESCE({sv}.is_uturn, FALSE) AND {sv}.lateral_geom IS NOT NULL THEN {sv}.lateral_geom
     WHEN extensions.ST_NPoints({e}.wellstick_geom) >= 3
          AND NOT extensions.ST_Equals(extensions.ST_PointN({e}.wellstick_geom, 2), extensions.ST_EndPoint({e}.wellstick_geom))
          AND NOT extensions.ST_Equals(extensions.ST_PointN({e}.wellstick_geom, 1), extensions.ST_PointN({e}.wellstick_geom, 2))
          AND LEAST(
                mod((abs(degrees(extensions.ST_Azimuth(extensions.ST_PointN({e}.wellstick_geom, 1)::extensions.geography,
                                                       extensions.ST_PointN({e}.wellstick_geom, 2)::extensions.geography))
                       - degrees(extensions.ST_Azimuth(extensions.ST_PointN({e}.wellstick_geom, 2)::extensions.geography,
                                                       extensions.ST_EndPoint({e}.wellstick_geom)::extensions.geography))))::numeric, 180),
                180 - mod((abs(degrees(extensions.ST_Azimuth(extensions.ST_PointN({e}.wellstick_geom, 1)::extensions.geography,
                                                             extensions.ST_PointN({e}.wellstick_geom, 2)::extensions.geography))
                       - degrees(extensions.ST_Azimuth(extensions.ST_PointN({e}.wellstick_geom, 2)::extensions.geography,
                                                       extensions.ST_EndPoint({e}.wellstick_geom)::extensions.geography))))::numeric, 180)
              ) > %(step_out)s
          THEN extensions.ST_RemovePoint({e}.wellstick_geom, 0)
     ELSE {e}.wellstick_geom END
"""


def _share(dist: str) -> str:
    """Share of the leg inside the well's flat-ended corridor of half-width `dist` (metres, a SQL expression)."""
    return ("extensions.ST_Length(extensions.ST_Intersection(p.leg, extensions.ST_Buffer(p.line::extensions.geography, "
            f"{dist}, 'endcap=flat')::extensions.geometry)::extensions.geography) / NULLIF(p.leg_m, 0)")


_FAM = "CASE WHEN {c} LIKE 'WCA%%' OR {c} = 'WCXY' THEN 'WCA' ELSE split_part({c}, '_', 1) END"

# One row per stick of the record sets. Read-only. %(name)s = this module's constants, rendered below.
_JUDGE = f"""
WITH rec AS (
    SELECT set_id, basin,
           (cfg #>> '{{generator,same_dv_ft}}')::float8  AS same_dv_ft,
           (cfg #>> '{{generator,same_dh_ft}}')::float8  AS same_dh_ft,
           (cfg #>> '{{generator,min_overlap}}')::float8 AS min_ov,
           cfg #>  '{{generator,stacked}}'               AS stacked
    FROM box.location_set
    WHERE is_record
),
w AS MATERIALIZED (
    SELECT e.api10, e.basin_blueox AS basin, e.formation_blueox AS code,
           {_FAM.format(c="e.formation_blueox")} AS fam,
           CASE WHEN e.first_production_date IS NOT NULL THEN 'producing'
                WHEN e.well_status = 'Permit Cancelled' THEN NULL
                WHEN e.well_status IN ('Spud', 'DUC', 'Completed') OR e.spud_date IS NOT NULL THEN 'pending'
                WHEN e.well_status = 'Permit Approved' THEN 'permit' END AS cls,
           -- depth evidence (box.tag_scoreboard.evidence_depth): never a planned survey; the survey lateral median, else
           -- tvd_ft unless it is a round 100; at least 4,000 ft
           CASE WHEN COALESCE(e.directional_survey_is_planned, FALSE) THEN NULL
                WHEN sv.lat_tvd_p50_ft IS NOT NULL THEN CASE WHEN sv.lat_tvd_p50_ft >= %(min_depth)s THEN sv.lat_tvd_p50_ft END
                WHEN e.tvd_ft >= %(min_depth)s AND mod(e.tvd_ft, 100) <> 0 THEN e.tvd_ft::float8 END AS depth_ft,
           {_LINE.format(e="e", sv="sv")} AS line
    FROM curated.wells_enriched e
    LEFT JOIN curated.well_lateral_survey sv ON sv.api10 = e.api10
    WHERE e.basin_blueox IN ('delaware', 'midland') AND e.is_horizontal
      AND extensions.ST_GeometryType(e.wellstick_geom) = 'ST_LineString'
),
pair AS MATERIALIZED (
    -- every (well, record stick) within the same-landing sideways limit; legs are split after the index search
    SELECT s.set_id, s.location_id, s.formation_blueox AS bench, s.target_tvd_ft,
           {_FAM.format(c="s.formation_blueox")} AS sfam,
           r.same_dv_ft, r.same_dh_ft, r.min_ov, r.stacked,
           COALESCE(d.wca_class = 'co-developed'
             AND ((w.code = 'WCA_1' AND s.formation_blueox = 'WCA_2') OR (w.code = 'WCA_2' AND s.formation_blueox = 'WCA_1')), FALSE) AS wca_cross,
           w.api10, w.cls, w.code, w.fam, w.depth_ft IS NULL AS planned_basis,
           COALESCE(w.depth_ft, b.target_tvd_ft) AS depth_ft,          -- no depth evidence: its tagged bench's landing in this DSU
           w.line, g.path[1] AS leg_no, g.geom AS leg, extensions.ST_Length(g.geom::extensions.geography) AS leg_m
    FROM w
    JOIN rec r ON r.basin = w.basin
    JOIN box.location_stick s
      -- `+ 0` keeps the set filter out of the index choice. Written as a plain equality, the planner ANDs the spatial probe
      -- with a bitmap of the whole record set (location_stick_pkey, ~40,000 rows) once per well: 168 s of a 227 s run with
      -- seven sets stored (2026-11-23). The spatial index alone returns ~48 candidates per well.
      ON s.set_id + 0 = r.set_id
     AND extensions.ST_DWithin(s.legs_geom::extensions.geography, w.line::extensions.geography, r.same_dh_ft * 0.3048)
    LEFT JOIN box.location_set_dsu d ON d.set_id = s.set_id AND d.pad_id = s.pad_id
    LEFT JOIN box.location_set_bench b
      ON b.set_id = s.set_id AND b.pad_id = s.pad_id AND b.formation_blueox = w.code AND b.no_row_reason = '' AND b.target_tvd_ft IS NOT NULL
    CROSS JOIN LATERAL extensions.ST_Dump(s.legs_geom) g
    WHERE w.cls IS NOT NULL
),
scored AS (
    SELECT p.*, p.depth_ft - p.target_tvd_ft AS dz,
           {_share("%(corridor_m)s")} AS ov,
           {_share("p.same_dh_ft * 0.3048")} AS ov_same,
           {_share("%(gate_m)s")} AS ov_gate
    FROM pair p
),
judged AS (
    SELECT p.*,
           NOT p.wca_cross AND CASE WHEN p.depth_ft IS NULL THEN p.fam = p.sfam
                                    ELSE (p.code = p.bench AND abs(p.dz) <= %(same_code_ft)s) OR abs(p.dz) <= %(any_tag_ft)s END AS same_bench,
           p.cls = 'producing' AND p.ov_gate >= p.min_ov AND
               CASE WHEN p.depth_ft IS NULL THEN p.fam = p.sfam AND p.ov_same >= 0.5 * p.ov_gate
                    WHEN abs(p.dz) <= p.same_dv_ft THEN NOT p.wca_cross AND p.ov_same >= 0.5 * p.ov_gate
                    ELSE EXISTS (
                        SELECT 1 FROM jsonb_array_elements(p.stacked) k
                        WHERE p.dz > (k ->> 0)::float8 AND p.dz <= (k ->> 1)::float8
                          AND {_share("(k ->> 2)::float8 * 0.3048")} >= 0.5 * p.ov_gate)
               END AS in_envelope
    FROM scored p
),
leg AS (
    SELECT set_id, location_id, leg_no,
           max(ov) FILTER (WHERE same_bench AND cls = 'producing')                                      AS best_ov,
           count(*) FILTER (WHERE same_bench AND cls = 'producing' AND ov >= %(match)s)                 AS n_strong,
           (array_agg(api10 ORDER BY ov DESC, api10) FILTER (WHERE same_bench AND cls = 'producing'))[1] AS best_api10,
           (array_agg(planned_basis ORDER BY ov DESC, api10) FILTER (WHERE same_bench AND cls = 'producing'))[1] AS best_planned,
           (array_agg(api10 ORDER BY ov DESC, api10) FILTER (WHERE same_bench AND cls = 'pending' AND ov >= %(match)s))[1] AS pending_api10,
           (array_agg(api10 ORDER BY ov DESC, api10) FILTER (WHERE same_bench AND cls = 'permit' AND ov >= %(match)s))[1]  AS permit_api10,
           (array_agg(api10 ORDER BY ov_same DESC, api10) FILTER (WHERE in_envelope))[1]                AS crowd_api10
    FROM judged
    GROUP BY 1, 2, 3
),
leg_state AS (
    SELECT l.*,
           CASE WHEN n_strong >= 2 THEN 'two_wells'
                WHEN best_ov >= %(match)s THEN 'matched'
                WHEN best_ov >= %(conflict)s THEN 'partial_overlap' END AS st
    FROM leg l
),
stick AS (
    SELECT set_id, location_id,
           count(*) FILTER (WHERE st = 'matched')                                                 AS legs_matched,
           (array_agg(st ORDER BY leg_no) FILTER (WHERE st IN ('two_wells', 'partial_overlap')))[1] AS conflict_reason,
           (array_agg(best_api10 ORDER BY best_ov DESC NULLS LAST, leg_no) FILTER (WHERE st IS NOT NULL))[1] AS matched_api10,
           max(best_ov) FILTER (WHERE st IS NOT NULL)                                             AS match_overlap,
           bool_or(best_planned) FILTER (WHERE st IS NOT NULL)                                    AS any_planned,
           (array_agg(pending_api10 ORDER BY leg_no) FILTER (WHERE pending_api10 IS NOT NULL))[1] AS pending_api10,
           (array_agg(permit_api10 ORDER BY leg_no) FILTER (WHERE permit_api10 IS NOT NULL))[1]   AS permit_api10,
           (array_agg(crowd_api10 ORDER BY leg_no) FILTER (WHERE crowd_api10 IS NOT NULL))[1]     AS crowd_api10
    FROM leg_state
    GROUP BY 1, 2
),
out AS (
    SELECT s.set_id, s.location_id, s.basin, s.pad_id, s.formation_blueox, s.n_legs,
           CASE WHEN k.conflict_reason IS NOT NULL THEN 'conflict'
                WHEN k.legs_matched > 0 THEN 'producing'
                WHEN k.pending_api10 IS NOT NULL THEN 'pending'
                WHEN k.permit_api10 IS NOT NULL THEN 'permitted'
                ELSE 'open' END AS status,
           COALESCE(k.legs_matched, 0)::smallint AS legs_matched, k.conflict_reason, k.matched_api10,
           round(k.match_overlap::numeric, 3) AS match_overlap, k.any_planned, k.pending_api10, k.permit_api10, k.crowd_api10
    FROM box.location_stick s
    JOIN rec r ON r.set_id = s.set_id
    LEFT JOIN stick k ON k.set_id = s.set_id AND k.location_id = s.location_id
)
SELECT o.set_id, o.location_id, o.basin, o.pad_id, o.formation_blueox, o.n_legs, o.status,
       o.status IN ('open', 'pending', 'permitted') AND o.crowd_api10 IS NULL AS counts_as_inventory,
       CASE WHEN o.status = 'producing' THEN o.legs_matched ELSE 0 END::smallint AS legs_matched,
       CASE WHEN o.status IN ('producing', 'conflict') THEN o.matched_api10 END AS matched_api10,
       CASE WHEN o.status IN ('producing', 'conflict') THEN o.match_overlap END AS match_overlap,
       CASE WHEN o.status IN ('producing', 'conflict') THEN CASE WHEN o.any_planned THEN 'planned' ELSE 'depth' END END AS match_basis,
       CASE WHEN o.status = 'conflict' THEN o.conflict_reason END AS conflict_reason,
       o.pending_api10, o.permit_api10,
       o.status IN ('open', 'pending', 'permitted') AND o.crowd_api10 IS NOT NULL AS crowded,
       CASE WHEN o.status IN ('open', 'pending', 'permitted') THEN o.crowd_api10 END AS crowd_api10
FROM out o
"""

# One row per DSU x bench of the record sets holding a producing well of that bench the set never read.
# {src} = a relation with JUDGE_SQL's columns, aliased j (the nightly's temp table, or JUDGE_SQL itself as a subquery).
_STALE = f"""
WITH rec AS (
    SELECT set_id, basin, dsu_vintage FROM box.location_set WHERE is_record
),
newp AS MATERIALIZED (
    SELECT r.set_id, r.basin, r.dsu_vintage, e.api10, e.formation_blueox AS code,
           {_LINE.format(e="e", sv="sv")} AS line
    FROM curated.wells_enriched e
    JOIN rec r ON r.basin = e.basin_blueox
    LEFT JOIN curated.well_lateral_survey sv ON sv.api10 = e.api10
    WHERE e.is_horizontal AND e.first_production_date IS NOT NULL AND e.formation_blueox IS NOT NULL
      AND extensions.ST_GeometryType(e.wellstick_geom) = 'ST_LineString'
      AND NOT EXISTS (SELECT 1 FROM box.location_set_well k WHERE k.set_id = r.set_id AND k.api10 = e.api10)
),
mem AS (
    SELECT n.set_id, n.basin, b.pad_id, n.code, n.api10
    FROM newp n
    JOIN box.location_set_bench b ON b.set_id = n.set_id AND b.formation_blueox = n.code AND b.sticks > 0
    JOIN raw_novi_intel.pads p ON p.report_version = n.dsu_vintage AND p.pad_id = b.pad_id
    WHERE extensions.ST_Intersects(p.geom, n.line)
      AND extensions.ST_Length(extensions.ST_Intersection(n.line, p.geom)::extensions.geography)
            >= %(member)s * extensions.ST_Length(n.line::extensions.geography)
),
agg AS (
    SELECT set_id, basin, pad_id, code, count(*)::int AS new_producers, array_agg(api10 ORDER BY api10) AS new_api10
    FROM mem GROUP BY 1, 2, 3, 4
),
st AS (
    -- sticks_out = the sticks these new producers took out tonight (status or crowded), not every stick that is out
    SELECT a.set_id, a.pad_id, a.code, count(*)::int AS sticks,
           (count(*) FILTER (WHERE NOT j.counts_as_inventory AND COALESCE(j.matched_api10, j.crowd_api10) = ANY (a.new_api10)))::int AS sticks_out
    FROM agg a
    JOIN {{src}} ON j.set_id = a.set_id AND j.pad_id = a.pad_id AND j.formation_blueox = a.code
    GROUP BY 1, 2, 3
)
SELECT a.set_id, a.basin, a.pad_id, a.code AS formation_blueox, a.new_producers, a.new_api10, st.sticks, st.sticks_out,
       LEAST(st.sticks - st.sticks_out, GREATEST(st.sticks - a.new_producers, 0)) AS est_sticks
FROM agg a
JOIN st ON st.set_id = a.set_id AND st.pad_id = a.pad_id AND st.code = a.code
"""

JUDGE_SQL = _JUDGE % PARAMS                 # literal SQL: the constants rendered once, no bind parameters (CREATE TABLE AS takes none)
STALE_SQL = _STALE % PARAMS                 # still has {src}
STATUS_COLS = ("set_id", "location_id", "basin", "pad_id", "formation_blueox", "n_legs", "status", "counts_as_inventory", "legs_matched",
               "matched_api10", "match_overlap", "match_basis", "conflict_reason", "pending_api10", "permit_api10", "crowded", "crowd_api10")
STALE_COLS = ("set_id", "basin", "pad_id", "formation_blueox", "new_producers", "new_api10", "sticks", "sticks_out", "est_sticks")

_COUNTS_SQL = """
SELECT basin, status, count(*) AS n, count(*) FILTER (WHERE crowded) AS crowded, count(*) FILTER (WHERE counts_as_inventory) AS inventory
FROM {src} GROUP BY 1, 2 ORDER BY 1, 2
"""
# what differs between tonight ({new}) and the stored table: a location's status, crowded flag, realizing well or set
_DIFF = ("c.location_id IS NULL OR n.location_id IS NULL OR c.set_id <> n.set_id OR c.status <> n.status OR c.crowded <> n.crowded "
         "OR c.matched_api10 IS DISTINCT FROM n.matched_api10")


def missing_tables(conn: Any) -> list[str]:
    with conn.cursor() as cur:
        return [t for t in TABLES if cur.execute("SELECT to_regclass(%s)", (t,)).fetchone()[0] is None]


def _counts(cur: Any, src: str) -> dict:
    out: dict[str, dict] = {}
    for basin, status, n, crowded, inv in cur.execute(_COUNTS_SQL.format(src=src)).fetchall():
        b = out.setdefault(basin, {"sticks": 0, "crowded": 0, "inventory": 0})
        b[status] = int(n)
        b["sticks"] += int(n)
        b["crowded"] += int(crowded)
        b["inventory"] += int(inv)
    return out


def breaker_limit(n_locations: int) -> int:
    return max(BREAKER_MIN, int(BREAKER_SHARE * n_locations))


def log_cause(first_run: bool, sets_changed: bool, version_changed: bool) -> str:
    """Why a night's log rows exist. A change of record set or of rule explains every row of that night."""
    return "first_run" if first_run else "set_change" if sets_changed else "rule_change" if version_changed else "well"


def run(write: bool, allow_breaker: bool = False, conn: Any = None) -> dict:
    """One pass. write=False is read-only (the judge and the stale list are evaluated, nothing is written)."""
    from etl.db import get_connection

    own = conn is None
    conn = conn or get_connection()
    t0 = time.monotonic()
    try:
        conn.autocommit = False
        missing = missing_tables(conn)
        conn.rollback()
        with conn.cursor() as cur:
            has_sets = cur.execute("SELECT to_regclass('box.location_set')").fetchone()[0] is not None
            sets = [int(r[0]) for r in cur.execute("SELECT set_id FROM box.location_set WHERE is_record ORDER BY set_id").fetchall()] if has_sets else []
        conn.rollback()
        if write and missing:
            return {"status": "absent", "missing": missing}
        if not sets:
            return {"status": "no_record_set"}
        if not write:
            return _dry_run(conn, sets, t0)
        return _write(conn, sets, allow_breaker, t0)
    finally:
        if own:
            conn.close()


def _dry_run(conn: Any, sets: list[int], t0: float) -> dict:
    with conn.cursor() as cur:
        cur.execute("SET TRANSACTION READ ONLY")
        cur.execute(f"SET LOCAL statement_timeout = '{TIMEOUT}'")
        rows = cur.execute(JUDGE_SQL).fetchall()
        stale = cur.execute(STALE_SQL.replace("{src}", f"({JUDGE_SQL}) j")).fetchall()
    conn.rollback()
    counts: dict[str, dict] = {}
    i = {c: k for k, c in enumerate(STATUS_COLS)}
    for r in rows:
        b = counts.setdefault(r[i["basin"]], {"sticks": 0, "crowded": 0, "inventory": 0})
        b[r[i["status"]]] = b.get(r[i["status"]], 0) + 1
        b["sticks"] += 1
        b["crowded"] += int(bool(r[i["crowded"]]))
        b["inventory"] += int(bool(r[i["counts_as_inventory"]]))
    return {"status": "dry_run", "predicate_version": VERSION, "set_ids": sets, "counts": counts, "stale_dsu_bench": len(stale),
            "rows": rows, "stale_rows": stale, "seconds": round(time.monotonic() - t0, 1)}


def _write(conn: Any, sets: list[int], allow_breaker: bool, t0: float) -> dict:
    with conn.transaction(), conn.cursor() as cur:
        cur.execute(f"SET LOCAL statement_timeout = '{TIMEOUT}'")
        cur.execute("CREATE TEMP TABLE _recon ON COMMIT DROP AS " + JUDGE_SQL)
        cur.execute("CREATE TEMP TABLE _stale ON COMMIT DROP AS " + STALE_SQL.replace("{src}", "_recon j"))
        n = cur.execute("SELECT count(*), count(DISTINCT location_id) FROM _recon").fetchone()
        want = cur.execute("SELECT count(*) FROM box.location_stick s JOIN box.location_set t USING (set_id) WHERE t.is_record").fetchone()[0]
        if not (n[0] == n[1] == want):
            raise RuntimeError(f"box recon: judged {n[0]} rows / {n[1]} locations for {want} record sticks")
        counts = _counts(cur, "_recon")
        prev = cur.execute("SELECT run_id, set_ids, predicate_version FROM meta.box_recon_run WHERE wrote ORDER BY run_id DESC LIMIT 1").fetchone()
        first = prev is None
        sets_changed = not first and sorted(prev[1] or []) != sets
        version_changed = not first and prev[2] != VERSION
        cause = log_cause(first, sets_changed, version_changed)
        changed = cur.execute(f"SELECT count(*) FROM curated.box_location_status c FULL JOIN _recon n USING (location_id) WHERE {_DIFF}").fetchone()[0]
        limit = breaker_limit(int(want))
        tripped = cause == "well" and changed > limit
        status = "breaker" if tripped and not allow_breaker else "written"
        wells = cur.execute("SELECT count(*) FROM curated.wells_enriched WHERE basin_blueox IN ('delaware', 'midland') AND is_horizontal").fetchone()[0]
        if tripped:
            logger.warning("box recon: circuit breaker %s (%d locations changed > limit %d)",
                           "OVERRIDDEN" if allow_breaker else "TRIPPED - nothing written", changed, limit)
        run_id = cur.execute(
            "INSERT INTO meta.box_recon_run (status, wrote, predicate_version, set_ids, wells_read, counts, changed, breaker_limit, stale_dsu_bench)"
            " VALUES (%s, %s, %s, %s, %s, %s, %s, %s, (SELECT count(*) FROM _stale)) RETURNING run_id",
            (status, status == "written", VERSION, sets, wells, json.dumps(counts), changed, limit)).fetchone()[0]
        if status == "written":
            cur.execute(
                f"""INSERT INTO curated.box_location_status_log
                        (run_id, location_id, set_id, cause, old_status, new_status, old_crowded, new_crowded, old_api10, new_api10, match_overlap, match_basis)
                    SELECT %s, COALESCE(n.location_id, c.location_id), COALESCE(n.set_id, c.set_id), %s, c.status, COALESCE(n.status, 'stopped'),
                           c.crowded, COALESCE(n.crowded, FALSE), c.matched_api10, n.matched_api10, n.match_overlap, n.match_basis
                    FROM curated.box_location_status c FULL JOIN _recon n USING (location_id)
                    WHERE {_DIFF}""", (run_id, cause))
            cur.execute("CREATE TEMP TABLE _since ON COMMIT DROP AS SELECT location_id, status, status_since FROM curated.box_location_status")
            cur.execute("DELETE FROM curated.box_location_status")
            cur.execute(
                f"""INSERT INTO curated.box_location_status ({', '.join(STATUS_COLS)}, status_since, run_id)
                    SELECT {', '.join('n.' + c for c in STATUS_COLS)}, COALESCE(s.status_since, current_date), %s
                    FROM _recon n LEFT JOIN _since s ON s.location_id = n.location_id AND s.status = n.status""", (run_id,))
            cur.execute("CREATE TEMP TABLE _ssince ON COMMIT DROP AS SELECT set_id, pad_id, formation_blueox, stale_since FROM curated.box_dsu_bench_stale")
            cur.execute("DELETE FROM curated.box_dsu_bench_stale")
            cur.execute(
                f"""INSERT INTO curated.box_dsu_bench_stale ({', '.join(STALE_COLS)}, stale_since, run_id)
                    SELECT {', '.join('n.' + c for c in STALE_COLS)}, COALESCE(s.stale_since, current_date), %s
                    FROM _stale n LEFT JOIN _ssince s ON s.set_id = n.set_id AND s.pad_id = n.pad_id AND s.formation_blueox = n.formation_blueox""", (run_id,))
            got = cur.execute("SELECT count(*) FROM curated.box_location_status").fetchone()[0]
            if got != want:
                raise RuntimeError(f"box recon: wrote {got} status rows for {want} record sticks - rolled back")
        secs = round(time.monotonic() - t0, 1)
        cur.execute("UPDATE meta.box_recon_run SET finished_at = clock_timestamp(), seconds = %s WHERE run_id = %s", (secs, run_id))
    logger.info("box recon: %s run %s (%s) - %d record sticks, %d changed (limit %d), %.0fs", status, run_id, cause, want, changed, limit, secs)
    return {"status": status, "run_id": run_id, "cause": cause, "predicate_version": VERSION, "set_ids": sets, "counts": counts, "changed": changed,
            "breaker_limit": limit, "seconds": secs}


def nightly_hook() -> None:
    """etl.db.refresh_curated hook: never raises. On a failure the previous tables stay and a `failed` run row is written."""
    try:
        s = run(write=True)
        if s.get("status") in ("absent", "no_record_set"):
            logger.info("box recon: skipped (%s)", s["status"])
    except Exception as exc:
        logger.exception("box recon step failed - previous curated.box_location_status kept")
        try:
            from etl.db import get_connection

            with get_connection() as conn, conn.cursor() as cur:
                if cur.execute("SELECT to_regclass('meta.box_recon_run')").fetchone()[0] is not None:
                    cur.execute("INSERT INTO meta.box_recon_run (status, wrote, predicate_version, finished_at, error) VALUES ('failed', FALSE, %s, now(), %s)",
                                (VERSION, f"{type(exc).__name__}: {exc}"[:2000]))
                    conn.commit()
        except Exception:
            logger.exception("could not record the failed box recon run")


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    g = ap.add_mutually_exclusive_group(required=True)
    g.add_argument("--dry-run", action="store_true")
    g.add_argument("--write", action="store_true")
    ap.add_argument("--allow-breaker", action="store_true", help="write even if the circuit breaker trips (manual runs)")
    a = ap.parse_args(argv)
    s = run(write=a.write, allow_breaker=a.allow_breaker)
    print(json.dumps({k: v for k, v in s.items() if k not in ("rows", "stale_rows")}, indent=1, default=str))
    return 0 if s.get("status") in ("written", "dry_run", "absent", "no_record_set") else 1


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
    sys.exit(main())
