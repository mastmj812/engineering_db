"""Hardened, one-time apply of the formation_blueox matview refactor (sql/17).

Rebuilds the curated chain so formation_blueox moves out of curated.wells into
its own matview (curated.formation_blueox), and lands the SUB-WOODFORD trigger +
CBP basin. Runs file-by-file in autocommit with a settle() (CHECKPOINT + pause)
between each heavy step, so the RAM-limited Supabase instance can flush WAL and
release memory instead of being driven into a restart by sustained load.

Why not just `psql -f sql/17`:
  * psql isn't installed here; we drive via psycopg (etl.db.get_connection,
    which sets statement_timeout=0 + keepalives — the pooler ignores ALTER ROLE).
  * the trailing refresh_all() in sql/17 is skipped: every CREATE MATERIALIZED
    VIEW ... AS populates WITH DATA on creation, so a second full refresh would
    just re-materialize 22M+17M+5M rows for nothing.

Each curated file self-drops its own objects (sql/04 drops curated.wells CASCADE,
etc.), so the in-order rebuild is clean. Order: 14 (crosswalk) -> 04 (wells) ->
16 (formation_blueox) -> 05 (production) -> 06 (wells_enriched + normalized +
cohorts) -> 10 (forecast) -> 12 (intel).

Usage (from repo root, in the engineering_db venv):
    python -m scripts.apply_formation_blueox_refactor
Env:
    ETL_SETTLE_SECONDS (default 20) — pause length between steps; 0 disables.
"""

from __future__ import annotations

import time
from pathlib import Path

from etl.db import get_connection, settle

REPO = Path(__file__).resolve().parent.parent
SQL = REPO / "sql"
SEEDS = REPO / "seeds"

# (file, friendly label, settle-after?) in dependency order. Heavy steps flagged.
STEPS = [
    ("04_curated.sql", "curated.wells", True),
    ("16_formation_blueox.sql", "curated.formation_blueox", True),
    ("05_curated_production.sql", "curated.production (~22M)", True),
    ("06_curated_derived.sql", "wells_enriched + production_normalized + cohorts (~5M)", True),
    ("10_curated_forecast.sql", "curated.production_forecast (~17M)", True),
    ("12_curated_intel.sql", "curated.intel_locations", False),
]


def _exec_file(label: str, path: Path) -> float:
    """Execute a whole .sql file in one autocommit session. Returns seconds."""
    sql_text = path.read_text(encoding="utf-8")
    t0 = time.monotonic()
    conn = get_connection()
    try:
        conn.autocommit = True
        with conn.cursor() as cur:
            cur.execute(sql_text)  # psycopg3 handles multi-statement + $$ bodies
    finally:
        conn.close()
    dt = time.monotonic() - t0
    print(f"    done {label} in {dt:.0f}s", flush=True)
    return dt


def _load_crosswalk() -> None:
    """Replicate sql/14: DDL + \\copy of the seed CSV (psql meta-command, so we
    run the COPY via psycopg's copy API)."""
    text = (SQL / "14_formation_crosswalk.sql").read_text(encoding="utf-8")
    lines = text.splitlines()
    copy_idx = next(i for i, ln in enumerate(lines) if ln.lstrip().startswith("\\copy"))
    pre = "\n".join(lines[:copy_idx])
    post = "\n".join(lines[copy_idx + 1 :])
    csv_path = SEEDS / "formation_crosswalk.csv"
    print("[1/7] ref.formation_crosswalk (reload seed CSV)", flush=True)
    conn = get_connection()
    try:
        conn.autocommit = True
        with conn.cursor() as cur:
            cur.execute(pre)  # CREATE SCHEMA / TABLE / TRUNCATE
            copy_sql = (
                "COPY ref.formation_crosswalk "
                "(basin, source, raw_value, canonical_code, notes) "
                "FROM STDIN WITH (FORMAT csv, HEADER true)"
            )
            with cur.copy(copy_sql) as cp, open(csv_path, "rb") as fh:
                while chunk := fh.read(65536):
                    cp.write(chunk)
            if post.strip():
                cur.execute(post)  # COMMENT ON TABLE ...
            cur.execute("SELECT COUNT(*) FROM ref.formation_crosswalk")
            n = cur.fetchone()[0]
        print(f"    loaded {n} crosswalk rows", flush=True)
    finally:
        conn.close()


def main() -> None:
    print("=== formation_blueox refactor apply (hardened) ===", flush=True)
    t_start = time.monotonic()
    _load_crosswalk()
    settle()
    for i, (fname, label, settle_after) in enumerate(STEPS, start=2):
        print(f"[{i}/7] {label}  ({fname})", flush=True)
        _exec_file(label, SQL / fname)
        if settle_after:
            print("    settle...", flush=True)
            settle()

    # Verify (no refresh_all — CREATEs already populated WITH DATA).
    conn = get_connection()
    try:
        conn.autocommit = True
        with conn.cursor() as cur:
            cur.execute("SELECT COUNT(*) FROM curated.wells")
            wells = cur.fetchone()[0]
            cur.execute("SELECT COUNT(*) FROM curated.formation_blueox")
            fb = cur.fetchone()[0]
            cur.execute(
                "SELECT COUNT(*) FROM curated.wells_enriched WHERE formation_blueox IS NOT NULL"
            )
            mapped = cur.fetchone()[0]
            cur.execute(
                "SELECT basin_blueox, COUNT(*) FROM curated.formation_blueox "
                "GROUP BY 1 ORDER BY 2 DESC NULLS LAST"
            )
            by_basin = cur.fetchall()
            # curated.wells must NO LONGER carry formation_blueox
            cur.execute(
                "SELECT COUNT(*) FROM information_schema.columns "
                "WHERE table_schema='curated' AND table_name='wells' "
                "AND column_name='formation_blueox'"
            )
            wells_has_fb = cur.fetchone()[0]
    finally:
        conn.close()

    print("=== verification ===", flush=True)
    print(f"  curated.wells rows ............... {wells}", flush=True)
    print(f"  curated.formation_blueox rows .... {fb}  (parity={wells == fb})", flush=True)
    print(f"  wells_enriched mapped formation .. {mapped}", flush=True)
    print(f"  formation_blueox column still on curated.wells? {bool(wells_has_fb)} (want False)", flush=True)
    print("  basin_blueox distribution:", flush=True)
    for basin, cnt in by_basin:
        print(f"    {basin or '(null)':10} {cnt}", flush=True)
    print(f"=== DONE in {time.monotonic() - t_start:.0f}s ===", flush=True)


if __name__ == "__main__":
    main()
