"""Build curated.intel_formation_blueox on the warehouse (Supabase).

Steps:
  1. Reload ref.formation_crosswalk (sql/14) — adds Midland 'Lower Spraberry Sand' -> JM.
  2. REFRESH curated.formation_blueox CONCURRENTLY — picks up the few curated wells
     that now resolve via the new crosswalk row (cheap, ~90k rows).
  3. Build curated.intel_formation_blueox (sql/18) — tier-2 KNN over ~55k coarse
     sticks; CREATE populates WITH DATA, so no separate refresh.
  4. Validate: source distribution, NULL tail, inferred sub-bench split.

Run from repo root in the venv:
    python -m scripts.apply_intel_formation_blueox
"""

from __future__ import annotations

import time
from pathlib import Path

from etl.db import get_connection

REPO = Path(__file__).resolve().parent.parent
SQL = REPO / "sql"
SEEDS = REPO / "seeds"


def reload_crosswalk() -> None:
    text = (SQL / "14_formation_crosswalk.sql").read_text(encoding="utf-8")
    lines = text.splitlines()
    ci = next(i for i, ln in enumerate(lines) if ln.lstrip().startswith("\\copy"))
    pre, post = "\n".join(lines[:ci]), "\n".join(lines[ci + 1:])
    print("[1/4] reload ref.formation_crosswalk", flush=True)
    conn = get_connection()
    try:
        conn.autocommit = True
        with conn.cursor() as cur:
            cur.execute(pre)
            copy_sql = (
                "COPY ref.formation_crosswalk "
                "(basin, source, raw_value, canonical_code, notes) "
                "FROM STDIN WITH (FORMAT csv, HEADER true)"
            )
            with cur.copy(copy_sql) as cp, open(SEEDS / "formation_crosswalk.csv", "rb") as fh:
                while chunk := fh.read(65536):
                    cp.write(chunk)
            if post.strip():
                cur.execute(post)
            n = cur.execute("SELECT COUNT(*) FROM ref.formation_crosswalk").fetchone()[0]
            has = cur.execute(
                "SELECT canonical_code FROM ref.formation_crosswalk "
                "WHERE basin='midland' AND raw_value='LOWER SPRABERRY SAND'"
            ).fetchone()
        print(f"    {n} rows; LSS->{has[0] if has else 'MISSING'}", flush=True)
    finally:
        conn.close()


def refresh_formation_blueox() -> None:
    print("[2/4] REFRESH curated.formation_blueox", flush=True)
    t0 = time.monotonic()
    conn = get_connection()
    try:
        conn.autocommit = True
        with conn.cursor() as cur:
            cur.execute("REFRESH MATERIALIZED VIEW CONCURRENTLY curated.formation_blueox")
    finally:
        conn.close()
    print(f"    done in {time.monotonic()-t0:.0f}s", flush=True)


def _exec_sql(label: str, fname: str) -> None:
    t0 = time.monotonic()
    sql_text = (SQL / fname).read_text(encoding="utf-8")
    conn = get_connection()
    try:
        conn.autocommit = True
        with conn.cursor() as cur:
            cur.execute(sql_text)
    finally:
        conn.close()
    print(f"    {label} done in {time.monotonic()-t0:.0f}s", flush=True)


def build_bench_reference() -> None:
    print("[3/5] build curated.bench_reference (GiST-indexed candidate pool)", flush=True)
    _exec_sql("bench_reference", "18_bench_reference.sql")
    conn = get_connection()
    try:
        conn.autocommit = True
        with conn.cursor() as cur:
            n = cur.execute("SELECT COUNT(*) FROM curated.bench_reference").fetchone()[0]
        print(f"    {n} reference laterals", flush=True)
    finally:
        conn.close()


def build_intel() -> None:
    print("[4/5] build curated.intel_formation_blueox (fast KNN off bench_reference)", flush=True)
    _exec_sql("intel_formation_blueox", "19_intel_formation_blueox.sql")


def validate() -> None:
    print("[5/5] validation", flush=True)
    conn = get_connection()
    try:
        conn.autocommit = True
        with conn.cursor() as cur:
            print("  source distribution:", flush=True)
            for src, n in cur.execute(
                "SELECT COALESCE(formation_blueox_source,'(NULL)'), COUNT(*) "
                "FROM curated.intel_formation_blueox GROUP BY 1 ORDER BY 2 DESC"
            ).fetchall():
                print(f"    {src:12} {n}", flush=True)
            tail = cur.execute(
                "SELECT COUNT(*) FROM curated.intel_formation_blueox WHERE formation_blueox IS NULL"
            ).fetchone()[0]
            print(f"  NULL tail: {tail}", flush=True)
            print("  inferred sub-bench split (basin / code):", flush=True)
            for b, code, n in cur.execute(
                "SELECT basin_blueox, formation_blueox, COUNT(*) "
                "FROM curated.intel_formation_blueox WHERE formation_blueox_source='inferred' "
                "GROUP BY 1,2 ORDER BY 1,2"
            ).fetchall():
                print(f"    {b:9} {code:7} {n}", flush=True)
    finally:
        conn.close()


def main() -> None:
    t = time.monotonic()
    reload_crosswalk()
    refresh_formation_blueox()
    build_bench_reference()
    build_intel()
    validate()
    print(f"=== DONE in {time.monotonic()-t:.0f}s ===", flush=True)


if __name__ == "__main__":
    main()
