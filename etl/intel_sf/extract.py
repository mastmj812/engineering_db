"""Snowflake INTEL view -> raw_intel.* streaming COPY loads.

One transaction per (view, report_name) slice:
    DELETE FROM raw_intel.<t> WHERE report_name = %s
    COPY raw_intel.<t> (<shared cols>) FROM STDIN (FORMAT CSV)
    post-load hooks (WKT -> geom, stick_id_map upsert) + ANALYZE
so a mid-flight failure leaves that one slice absent and is fully repaired by
re-running the view (same idempotency contract as the old load_csvs.py).

basin_slug / report_version are applied via a per-load column DEFAULT (the
COPY column list omits them), mirroring the old loader's basin/report_version
trick. Global dimensions (operator / basin / source) carry no report_name in
the share and are loaded full-replace instead.

Column lists are the runtime intersection of the Snowflake view and the
raw_intel table (Snowflake GEOGRAPHY columns and loader-owned columns are
excluded automatically), so minor vendor-side column additions don't break
the load — they just don't land until sql/27 grows the column.

    python -m etl.intel_sf.extract --view WELL_MASTER            # all visible reports
    python -m etl.intel_sf.extract --view ARPS_FORECAST --report basin_research__Midland_Basin__2025Q3
"""

from __future__ import annotations

import csv
import io
import logging

from psycopg import sql

from etl.db import get_connection, log_etl_run
from etl.intel_sf.client import get_sf_connection

logger = logging.getLogger(__name__)

FETCH_BATCH = 50_000

# Views without report_name in the share -> full-replace load.
GLOBAL_VIEWS = {"OPERATOR", "BASIN", "SOURCE"}

# Loader-owned Postgres columns never present in the Snowflake SELECT.
_LOCAL_COLS = {"basin_slug", "report_version", "ingested_at", "geom"}


def parse_report_name(report_name: str) -> tuple[str, str]:
    """'basin_research__Delaware_Basin__2025Q3' -> ('delaware', '2025Q3')."""
    parts = report_name.split("__")
    if len(parts) != 3 or not parts[0] == "basin_research":
        raise ValueError(f"unexpected report_name format: {report_name!r}")
    family, version = parts[1], parts[2]
    slug = family.removesuffix("_Basin").lower()
    return slug, version


def visible_reports() -> list[str]:
    """Reports with actual (entitled) data — distinct report_name in WELL_MASTER.

    NOVI_INTEL.SOURCE lists every published collection, but the row-access
    policy only returns rows for entitled basins; WELL_MASTER is the ground
    truth for what we can actually pull.
    """
    sf = get_sf_connection()
    try:
        with sf.cursor() as cur:
            cur.execute("SELECT DISTINCT report_name FROM WELL_MASTER ORDER BY 1")
            return [str(r[0]) for r in cur.fetchall()]
    finally:
        sf.close()


def _pg_columns(cur, table: str) -> list[str]:
    cur.execute(
        "SELECT column_name FROM information_schema.columns "
        "WHERE table_schema = 'raw_intel' AND table_name = %s "
        "ORDER BY ordinal_position",
        (table,),
    )
    return [r[0] for r in cur.fetchall()]


def _sf_columns(sf_cur, view: str) -> list[str]:
    sf_cur.execute(f"SELECT * FROM {view} LIMIT 0")
    return [d[0].lower() for d in sf_cur.description]


def _shared_columns(sf_cur, pg_cur, view: str, table: str) -> list[str]:
    from etl.intel_sf.config import EXCLUDE_COLS
    pg_cols = set(_pg_columns(pg_cur, table)) - _LOCAL_COLS - EXCLUDE_COLS.get(view, frozenset())
    sf_cols = _sf_columns(sf_cur, view)
    shared = [c for c in sf_cols if c in pg_cols]
    skipped = [c for c in sf_cols if c not in pg_cols]
    if skipped:
        logger.info("%s: not mirrored (by design or drift): %s", view, skipped)
    return shared


def _stream_copy(sf_cur, pg_cur, table: str, cols: list[str], select_sql: str,
                 params: tuple = ()) -> int:
    """Snowflake SELECT -> psycopg COPY. Returns rows written."""
    col_list = ", ".join(f'"{c}"' for c in cols)
    copy_sql = f"COPY raw_intel.{table} ({col_list}) FROM STDIN WITH (FORMAT CSV)"
    sf_cur.execute(select_sql, params)
    n = 0
    with pg_cur.copy(copy_sql) as copy:
        while batch := sf_cur.fetchmany(FETCH_BATCH):
            buf = io.StringIO()
            csv.writer(buf).writerows(batch)
            copy.write(buf.getvalue())
            n += len(batch)
            if n % 1_000_000 < FETCH_BATCH:
                logger.info("  %s: %d rows streamed...", table, n)
    return n


# ---------------------------------------------------------------------------
# post-load hooks, applied inside the slice transaction
# ---------------------------------------------------------------------------

def _hook_geom(pg_cur, table: str, report_name: str) -> None:
    pg_cur.execute(
        sql.SQL(
            "UPDATE raw_intel.{} SET geom = "
            "ST_Force2D(ST_SetSRID(ST_GeomFromText(geometry_wkt), 4326)) "
            "WHERE report_name = %s AND geometry_wkt IS NOT NULL"
        ).format(sql.Identifier(table)),
        (report_name,),
    )
    logger.info("  %s: geom populated on %d rows", table, pg_cur.rowcount)


def _hook_stick_id_map(pg_cur, report_name: str) -> None:
    pg_cur.execute(
        "INSERT INTO raw_intel.stick_id_map (well_ref) "
        "SELECT DISTINCT well_ref FROM raw_intel.well_master "
        "WHERE report_name = %s "
        "ON CONFLICT (well_ref) DO NOTHING",
        (report_name,),
    )
    logger.info("  stick_id_map: %d new well_refs", pg_cur.rowcount)


_HOOKS = {
    "wellbore_trajectory": [_hook_geom],
    "well_master": [_hook_geom, lambda cur, table, rn: _hook_stick_id_map(cur, rn)],
}


# ---------------------------------------------------------------------------
# public entry points
# ---------------------------------------------------------------------------

def copy_view(view: str, report_name: str, sf=None) -> int:
    """Load one report slice of one INTEL view into raw_intel. Returns rows."""
    table = view.lower()
    slug, version = parse_report_name(report_name)
    own_sf = sf is None
    if own_sf:
        sf = get_sf_connection()
    try:
        with log_etl_run("intel_sf", f"{table}:{report_name}") as run, \
                sf.cursor() as sf_cur, \
                get_connection() as conn, conn.cursor() as cur:
            cols = _shared_columns(sf_cur, cur, view, table)
            cur.execute(
                sql.SQL("DELETE FROM raw_intel.{} WHERE report_name = %s")
                .format(sql.Identifier(table)),
                (report_name,),
            )
            run.rows_deleted = cur.rowcount
            cur.execute(
                sql.SQL(
                    "ALTER TABLE raw_intel.{} "
                    "ALTER COLUMN basin_slug SET DEFAULT {}, "
                    "ALTER COLUMN report_version SET DEFAULT {}"
                ).format(sql.Identifier(table), sql.Literal(slug), sql.Literal(version))
            )
            n = _stream_copy(
                sf_cur, cur, table, cols,
                f"SELECT {', '.join(cols)} FROM {view} WHERE report_name = %s",
                (report_name,),
            )
            cur.execute(
                sql.SQL(
                    "ALTER TABLE raw_intel.{} "
                    "ALTER COLUMN basin_slug DROP DEFAULT, "
                    "ALTER COLUMN report_version DROP DEFAULT"
                ).format(sql.Identifier(table))
            )
            for hook in _HOOKS.get(table, ()):
                hook(cur, table, report_name)
            cur.execute(sql.SQL("ANALYZE raw_intel.{}").format(sql.Identifier(table)))
            conn.commit()
            run.rows_inserted = n
        logger.info("%s [%s]: %d rows", table, report_name, n)
        return n
    finally:
        if own_sf:
            sf.close()


def copy_global_view(view: str, sf=None) -> int:
    """Full-replace load of a global dimension (no report_name in the share)."""
    table = view.lower()
    own_sf = sf is None
    if own_sf:
        sf = get_sf_connection()
    try:
        with log_etl_run("intel_sf", table) as run, \
                sf.cursor() as sf_cur, \
                get_connection() as conn, conn.cursor() as cur:
            cols = _shared_columns(sf_cur, cur, view, table)
            cur.execute(sql.SQL("DELETE FROM raw_intel.{}").format(sql.Identifier(table)))
            run.rows_deleted = cur.rowcount
            n = _stream_copy(sf_cur, cur, table, cols,
                             f"SELECT {', '.join(cols)} FROM {view}")
            cur.execute(sql.SQL("ANALYZE raw_intel.{}").format(sql.Identifier(table)))
            conn.commit()
            run.rows_inserted = n
        logger.info("%s [global]: %d rows", table, n)
        return n
    finally:
        if own_sf:
            sf.close()


def load_views(views: list[str], reports: list[str] | None = None) -> dict[str, int]:
    """Load a list of views for the given reports (default: all visible).

    One Snowflake connection is reused across the whole run.
    """
    if reports is None:
        reports = visible_reports()
        logger.info("visible reports: %s", reports)
    counts: dict[str, int] = {}
    sf = get_sf_connection()
    try:
        for view in views:
            if view in GLOBAL_VIEWS:
                counts[view.lower()] = copy_global_view(view, sf=sf)
            else:
                total = 0
                for report in reports:
                    total += copy_view(view, report, sf=sf)
                counts[view.lower()] = total
    finally:
        sf.close()
    return counts


def main() -> None:
    import argparse
    ap = argparse.ArgumentParser(description="Load INTEL share views into raw_intel.")
    ap.add_argument("--view", required=True, help="secure view name, e.g. WELL_MASTER")
    ap.add_argument("--report", default=None, help="restrict to one report_name")
    args = ap.parse_args()
    load_views([args.view.upper()], [args.report] if args.report else None)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
    main()
