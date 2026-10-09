"""BOX step 3 — write extents to box.extent / box.extent_edge (sql/54).

WAREHOUSE WRITES. Only called by scripts/box_extents_export.py --store and
scripts/box_extents_import.py --store, after sql/54 has been applied (explicit go-apply) and with
Michael's go-ahead for the write itself. Session pooler (5432) like the other batch jobs.
"""

from __future__ import annotations

import json
import math
from typing import Any

from box import edge_gap as eg

BASIN = "delaware"


def _clean(o: Any) -> Any:
    return json.loads(json.dumps(o, default=lambda x: None if isinstance(x, float) and not math.isfinite(x) else str(x)))


def _wkt_ll(g_ft13: Any) -> str:
    return eg.to_lonlat([g_ft13])[0].wkt


def store_generated(conn: Any, pool: str, version: int, b: dict[str, Any], bp: Any, run_id: str, make_record: bool = False) -> int:
    """Store a generated extent + its edges; make_record also makes it the version of record (the
    previous record, if any, is marked superseded) — plan D28: generated extents are adopted without
    waiting for geology; a later geology edit supersedes them through store_edited."""
    from dataclasses import asdict

    from box.extent_report import EDGE

    with conn.cursor() as cur:
        cur.execute(
            """INSERT INTO box.extent (basin, bench, version, source, geom, area_sqmi, params, edge_gap_stats, generated_from_run)
               VALUES (%s, %s, %s, 'generated', extensions.ST_Multi(extensions.ST_GeomFromText(%s, 4326)), %s, %s, %s, %s)
               RETURNING extent_id""",
            (BASIN, pool, version, _wkt_ll(b["extent"]), b["stats"]["extent_sqmi"], json.dumps(_clean({"buffer": asdict(bp), "edge": asdict(EDGE)})),
             json.dumps(_clean(b["stats"])), run_id),
        )
        eid = int(cur.fetchone()[0])
        rows = []
        for r, g in zip(b["edges"].itertuples(), eg.to_lonlat(list(b["edges"].geom))):
            rows.append((eid, int(r.edge_no), int(r.seg_no), g.wkt, r.side or None, None if not math.isfinite(r.gap_ft) else float(r.gap_ft), float(r.buffer_ft),
                         r.edge_class, r.perf_class or None, None if not math.isfinite(r.perf_ratio) else float(r.perf_ratio), r.rule, r.flag or None))
        cur.executemany(
            """INSERT INTO box.extent_edge (extent_id, edge_no, seg_no, geom, side, gap_ft, buffer_ft, edge_class, perf_class, perf_ratio, rule, explanation)
               VALUES (%s, %s, %s, extensions.ST_GeomFromText(%s, 4326), %s, %s, %s, %s, %s, %s, %s, %s)""",
            rows,
        )
        if make_record:
            cur.execute("UPDATE box.extent SET is_record = false, superseded_by = %s WHERE basin = %s AND bench = %s AND is_record", (eid, BASIN, pool))
            cur.execute("UPDATE box.extent SET is_record = true WHERE extent_id = %s", (eid,))
    conn.commit()
    return eid


def store_edited(conn: Any, pool: str, version: int, edited_ft13: Any, diff_stats: dict[str, Any], make_record: bool) -> int:
    """Store geology's edit of generated v<version> (must already be stored); optionally make it the
    version of record (the previous record, if any, is marked superseded)."""
    with conn.cursor() as cur:
        cur.execute("SELECT extent_id FROM box.extent WHERE basin = %s AND bench = %s AND version = %s AND source = 'generated'", (BASIN, pool, version))
        row = cur.fetchone()
        if row is None:
            raise RuntimeError(f"generated {pool} v{version} is not stored yet — run box_extents_export --store first")
        parent = int(row[0])
        cur.execute(
            """INSERT INTO box.extent (basin, bench, version, source, geom, area_sqmi, parent_extent_id, diff_stats)
               VALUES (%s, %s, %s, 'geology_edited', extensions.ST_Multi(extensions.ST_GeomFromText(%s, 4326)), %s, %s, %s)
               RETURNING extent_id""",
            (BASIN, pool, version, _wkt_ll(edited_ft13), edited_ft13.area / eg.FT_PER_MI**2, parent, json.dumps(_clean(diff_stats))),
        )
        eid = int(cur.fetchone()[0])
        if make_record:
            cur.execute("UPDATE box.extent SET is_record = false, superseded_by = %s WHERE basin = %s AND bench = %s AND is_record", (eid, BASIN, pool))
            cur.execute("UPDATE box.extent SET is_record = true WHERE extent_id = %s", (eid,))
    conn.commit()
    return eid
