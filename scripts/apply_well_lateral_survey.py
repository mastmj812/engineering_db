"""Create + first-load raw_novi."DirectionalSurveys", build sql/64 curated.well_lateral_survey, validate.

    python -m scripts.apply_well_lateral_survey --dry-run     # READ ONLY: TSV profile + live state, no DDL
    python -m scripts.apply_well_lateral_survey               # !! DDL + 14M-row load — explicit go required

Dry run: profiles the local bulk TSV (rows, wells, deleted, ModifiedAt nulls), previews the per-well summary
(etl/novi/surveys.lateral_summary, the pure mirror of sql/64), and reads (read-only transaction) whether the raw
table / matview exist and how many producing horizontals per basin the TSV covers.

Apply (house pattern): [1] CREATE TABLE raw_novi."DirectionalSurveys" from sql/02 if absent; [2] full TRUNCATE+COPY
via etl.novi.load.load_table (logged to meta.etl_log as 'DirectionalSurveys'); [3] raw identity vs the TSV (rows +
wells, exact); [4] sql/64 exec; [5] sql/31 comments; [6] validate by identity — relkind 'm', 0 duplicate / NULL keys,
rows == distinct non-deleted API10, stored columns == lateral_summary() on a seeded sample of wells, lateral_geom
points == n_lat_stations; [7] REFRESH ... CONCURRENTLY smoke with timing. After this, the nightly loads the table
incrementally (ModifiedAt upsert + Path trim) and refreshes the matview when that load changed rows.
"""

from __future__ import annotations

import argparse
import re
import time
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from etl.db import get_connection
from etl.novi.load import load_table
from etl.novi.surveys import STATION_COLS, lateral_summary

ROOT = Path(__file__).resolve().parent.parent
SQL = ROOT / "sql"
FILE = "64_well_lateral_survey.sql"
TABLE = "DirectionalSurveys"
RAW = f'raw_novi."{TABLE}"'
DEFAULT_BULK = ROOT / "data" / "us-horizontals" / "All basins" / "All subbasins" / "Bulk"
CHECK_COLS = ["lateral_basis", "lat_start_md_ft", "lat_end_md_ft", "kb_elev_ft", "n_lat_stations", "lat_tvd_min_ft",
              "lat_tvd_max_ft", "lat_tvd_p50_ft", "heel_tvd_ft", "mid_tvd_ft", "toe_tvd_ft"]


def _tsv(bulk: Path) -> Path:
    return bulk / "Database" / f"{TABLE}.tsv"


def read_stations(bulk: Path) -> pd.DataFrame:
    d = pd.read_csv(_tsv(bulk), sep="\t", usecols=STATION_COLS + ["ModifiedAt", "DeletedAt"], dtype={"API10": str})
    return d


def raw_ddl() -> str:
    text = (SQL / "02_raw_novi_ddl.sql").read_text(encoding="utf-8")
    m = re.search(r'CREATE TABLE raw_novi\."DirectionalSurveys" \(.*?\n\);', text, re.DOTALL)
    if not m:
        raise RuntimeError("sql/02 has no raw_novi.DirectionalSurveys — regenerate it (scripts.generate_novi_ddl)")
    return m.group(0)


def _exists(cur: Any, regclass: str) -> bool:
    return cur.execute("SELECT to_regclass(%s) IS NOT NULL", (regclass,)).fetchone()[0]


def dry_run(bulk: Path) -> bool:
    t = time.monotonic()
    d = read_stations(bulk)
    live = d[d.DeletedAt.isna()]
    print(f"TSV {_tsv(bulk)}: rows={len(d):,} wells={d.API10.nunique():,} deleted={d.DeletedAt.notna().sum():,} "
          f"null ModifiedAt={d.ModifiedAt.isna().sum():,} ({time.monotonic() - t:.0f}s)", flush=True)
    s = lateral_summary(live)
    print(f"summary: wells={len(s):,} basis={s.lateral_basis.value_counts(dropna=False).to_dict()}")
    for c in ("n_lat_stations", "lat_tvd_range_ft", "toe_minus_heel_tvd_ft", "kb_elev_ft", "lat_interp_share"):
        print(f"  {c:24s} p5/p50/p95 = {np.nanpercentile(s[c].astype(float), [5, 50, 95]).round(2).tolist()}")
    with get_connection() as conn, conn.cursor() as cur:
        cur.execute("SET TRANSACTION READ ONLY")
        print(f"live: {RAW} exists={_exists(cur, RAW)} "
              f"curated.well_lateral_survey exists={_exists(cur, 'curated.well_lateral_survey')}")
        rows = cur.execute("""SELECT api10, basin_blueox FROM curated.wells_enriched
                              WHERE is_horizontal AND first_production_date IS NOT NULL""").fetchall()
        conn.rollback()
    w = pd.DataFrame(rows, columns=["api10", "basin"])
    w["covered"] = w.api10.isin(s.index[s.lateral_basis.notna()])
    print("producing-horizontal coverage by basin:\n" + w.groupby("basin", dropna=False).covered.agg(["size", "mean"]).round(3).to_string())
    return True


def validate(cur: Any, live: pd.DataFrame, sample: int, seed: int) -> bool:
    ok = True
    kind = cur.execute("SELECT c.relkind FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace "
                       "WHERE n.nspname = 'curated' AND c.relname = 'well_lateral_survey'").fetchone()
    print(f"    relkind={kind and kind[0]!r} (expect 'm')", flush=True)
    ok &= bool(kind) and kind[0] == "m"
    n, dups, nulls = cur.execute("""
        SELECT (SELECT count(*) FROM curated.well_lateral_survey),
               (SELECT count(*) FROM (SELECT 1 FROM curated.well_lateral_survey GROUP BY api10 HAVING count(*) > 1) x),
               (SELECT count(*) FROM curated.well_lateral_survey WHERE api10 IS NULL)""").fetchone()
    want = live.API10.nunique()
    print(f"    rows={n:,} (identity: distinct non-deleted API10 in TSV = {want:,}) duplicate keys={dups} NULL keys={nulls}", flush=True)
    ok &= n == want and dups == 0 and nulls == 0
    bad_geom = cur.execute("""SELECT count(*) FROM curated.well_lateral_survey
                              WHERE lateral_geom IS NOT NULL AND extensions.ST_NPoints(lateral_geom) <> n_lat_stations""").fetchone()[0]
    print(f"    lateral_geom points != n_lat_stations: {bad_geom} (must be 0)", flush=True)
    ok &= bad_geom == 0
    rng = np.random.default_rng(seed)
    ids = sorted(rng.choice(live.API10.unique(), size=min(sample, live.API10.nunique()), replace=False).tolist())
    py = lateral_summary(live[live.API10.isin(ids)])
    cols = ", ".join(CHECK_COLS)
    db = pd.DataFrame(cur.execute(f"SELECT api10, {cols} FROM curated.well_lateral_survey WHERE api10 = ANY(%(a)s)",
                                  {"a": ids}).fetchall(), columns=["API10", *CHECK_COLS]).set_index("API10")
    bad = 0
    for c in CHECK_COLS:
        a, b = db[c].reindex(py.index), py[c]
        if c == "lateral_basis":
            mism = ~((a == b) | (a.isna() & b.isna()))
        else:
            a, b = pd.to_numeric(a, errors="coerce").astype(float), pd.to_numeric(b, errors="coerce").astype(float)
            mism = ~(np.isclose(a, b, atol=0.01) | (a.isna() & b.isna()))
        if mism.any():
            print(f"    MISMATCH {c}: {int(mism.sum())} wells, e.g. {mism[mism].index[:3].tolist()}", flush=True)
            bad += int(mism.sum())
    print(f"    stored vs etl/novi/surveys.lateral_summary on {len(ids)} wells: {bad} mismatches (must be 0)", flush=True)
    ok &= bad == 0
    return ok


def apply(bulk: Path, sample: int, seed: int) -> bool:
    d = read_stations(bulk)
    live = d[d.DeletedAt.isna()]
    with get_connection() as conn:
        conn.autocommit = True
        with conn.cursor() as cur:
            cur.execute("SET statement_timeout = 0")
            if _exists(cur, RAW):
                print(f"[1/7] {RAW} already exists — keep", flush=True)
            else:
                print(f"[1/7] CREATE TABLE {RAW} (sql/02)", flush=True)
                cur.execute(raw_ddl())
    print(f"[2/7] full load {_tsv(bulk)} (TRUNCATE + COPY, {len(d):,} rows)", flush=True)
    t = time.monotonic()
    n_loaded = load_table(bulk, TABLE)
    print(f"    loaded {n_loaded:,} rows in {(time.monotonic() - t) / 60:.1f} min", flush=True)
    ok = True
    with get_connection() as conn:
        conn.autocommit = True
        with conn.cursor() as cur:
            cur.execute("SET statement_timeout = 0")
            n_raw, w_raw = cur.execute(f'SELECT count(*), count(DISTINCT "API10") FROM {RAW}').fetchone()
            print(f"[3/7] raw identity: rows {n_raw:,} vs TSV {len(d):,}; wells {w_raw:,} vs TSV {d.API10.nunique():,}", flush=True)
            ok &= n_raw == len(d) and w_raw == d.API10.nunique()
            print("[4/7] sql/64 — curated.well_lateral_survey (DROP + CREATE MATERIALIZED VIEW WITH DATA)", flush=True)
            t = time.monotonic()
            cur.execute((SQL / FILE).read_text(encoding="utf-8"))
            print(f"    built in {(time.monotonic() - t) / 60:.1f} min", flush=True)
            print("[5/7] sql/31 — comment catalog", flush=True)
            cur.execute((SQL / "31_comments.sql").read_text(encoding="utf-8"))
            print("[6/7] validate", flush=True)
            ok &= validate(cur, live, sample, seed)
            print("[7/7] REFRESH ... CONCURRENTLY smoke", flush=True)
            t = time.monotonic()
            cur.execute("REFRESH MATERIALIZED VIEW CONCURRENTLY curated.well_lateral_survey")
            print(f"    refreshed in {(time.monotonic() - t) / 60:.1f} min", flush=True)
    print(f"APPLY {'PASS' if ok else 'FAIL'}", flush=True)
    return ok


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--dry-run", action="store_true", help="read-only: TSV profile + live state + coverage")
    ap.add_argument("--bulk-dir", type=Path, default=DEFAULT_BULK)
    ap.add_argument("--sample", type=int, default=400)
    ap.add_argument("--seed", type=int, default=64)
    a = ap.parse_args(argv)
    ok = dry_run(a.bulk_dir) if a.dry_run else apply(a.bulk_dir, a.sample, a.seed)
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
