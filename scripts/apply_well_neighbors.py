"""Apply sql/59 curated.well_neighbors (3-D spacing pair table) + validate — or dry-run it read-only.

    python -m scripts.apply_well_neighbors --dry-run [--sample 200]   # READ ONLY: no DDL
    python -m scripts.apply_well_neighbors                            # !! DDL — explicit go-apply required

Dry run (read-only transaction, nothing written):
  * EXPLAIN of the matview body: idx_curated_wells_wellstick_geog must appear (sql/26; the 15-h seq-scan lesson);
  * the body as a SELECT for a seeded random sample of subjects: rows + wall time, extrapolated to every subject;
  * identity vs the Python prototype (box/spacing3d.pair_geometry on the same laterals): same pair set at the
    storage settings, overlap within 1e-4, dmin / dxy within 0.5 ft, dz exact.

Apply (house pattern, scripts/apply_codev_context.py): exec sql/59 on the 5432 session (statement_timeout=0), then
validate by identity, never by constant: relkind 'm'; 0 duplicate / NULL keys; every subject and neighbour is a
producing horizontal with a stick; storage bounds hold (overlap >= 0.10, dmin <= 3,960 ft); the Python identity on a
sample of the STORED rows; EXPLAIN index assertion; REFRESH ... CONCURRENTLY smoke with timing; sql/31 comments.
Not registered in the nightly (etl/db.py) — on-demand / quarterly until Michael decides.
"""

from __future__ import annotations

import argparse
import dataclasses
import math
import random
import re
import time
from pathlib import Path
from typing import Any

import shapely

from box import edge_gap as eg
from box import spacing3d as s3
from etl.db import get_connection

SQL = Path(__file__).resolve().parent.parent / "sql"
FILE = "59_well_neighbors.sql"
GEOG_INDEX = "idx_curated_wells_wellstick_geog"
STORE_GATE_FT = 3960.0
STORE_OVERLAP = 0.10
TOL_FT = 0.5
TOL_OVERLAP = 1e-4

_HZ = """COALESCE(w.novi_slant_calculated, w.enverus_trajectory) ILIKE '%%horizontal%%'
         AND w.first_production_date IS NOT NULL AND w.wellstick_geom IS NOT NULL"""
HZ1 = _HZ.replace("%%", "%")  # for queries run WITHOUT parameters (psycopg leaves % alone then)
_LAT_SQL = f"""
SELECT w.api10, w.first_production_date, w.tvd_ft, extensions.ST_AsText(CASE
    WHEN w.landing_point_lat IS NOT NULL AND w.landing_point_lon IS NOT NULL
     AND NOT extensions.ST_Equals(extensions.ST_SetSRID(extensions.ST_Point(w.landing_point_lon, w.landing_point_lat), 4326),
                                  extensions.ST_EndPoint(w.wellstick_geom))
    THEN extensions.ST_MakeLine(extensions.ST_SetSRID(extensions.ST_Point(w.landing_point_lon, w.landing_point_lat), 4326),
                                extensions.ST_EndPoint(w.wellstick_geom))
    ELSE w.wellstick_geom END)
FROM curated.wells w WHERE w.api10 = ANY(%(a)s) AND {_HZ}
"""


def body() -> str:
    return re.search(r"CREATE MATERIALIZED VIEW curated\.well_neighbors AS\n(.*?)\nWITH DATA;", (SQL / FILE).read_text(encoding="utf-8"), re.DOTALL).group(1)


def sampled_body(n_placeholder: str = "%(ids)s") -> str:
    b = body()
    anchor = "      AND w.wellstick_geom IS NOT NULL\n)"
    if b.count(anchor) != 1:
        raise RuntimeError("subj CTE anchor not found in sql/59 body")
    return b.replace(anchor, f"      AND w.wellstick_geom IS NOT NULL\n      AND w.api10 = ANY({n_placeholder})\n)").replace("%", "%%").replace("%%(ids)s", "%(ids)s")


def python_pairs(cur: Any, subjects: list[str], nbrs: list[str]) -> dict[tuple[str, str], s3.Pair]:
    """box/spacing3d.pair_geometry on the same laterals (EPSG:32613 ft), at the storage settings."""
    ids = sorted(set(subjects) | set(nbrs))
    rows = cur.execute(_LAT_SQL, {"a": ids}).fetchall()
    geo = {a: (fp, float(t) if t is not None else float("nan"), eg.to_ft([shapely.from_wkt(w)])[0]) for a, fp, t, w in rows}
    out = {}
    for a in subjects:
        if a not in geo:
            continue
        fp, tvd, g = geo[a]
        for b in nbrs:
            if b == a or b not in geo:
                continue
            fb, tb, h = geo[b]
            if g.distance(h) > STORE_GATE_FT:
                continue
            both_tvd = math.isfinite(tvd) and math.isfinite(tb)  # SQL keeps a pair with a missing TVD (dz NULL); so does this side
            p = s3.pair_geometry(g, h, tvd if both_tvd else 0.0, tb if both_tvd else 0.0, (fb - fp).days, b, STORE_OVERLAP)
            if p is not None:
                out[(a, b)] = p if both_tvd else dataclasses.replace(p, dz=float("nan"))
    return out


def identity(cur: Any, rows: list[tuple[Any, ...]], subjects: list[str]) -> dict[str, Any]:
    sqlp = {(r[0], r[1]): r for r in rows}
    nbrs = sorted({r[1] for r in rows})
    # candidates the Python side must also consider: every horizontal near the subjects (superset of SQL's neighbours)
    near = [r[0] for r in cur.execute(f"""
        SELECT DISTINCT w.api10 FROM curated.wells w JOIN curated.wells s ON s.api10 = ANY(%(a)s)
        WHERE {_HZ} AND w.api10 <> s.api10
          AND extensions.ST_DWithin(w.wellstick_geom::extensions.geography, s.wellstick_geom::extensions.geography, 1207.008)
    """, {"a": subjects}).fetchall()]
    pyp = python_pairs(cur, subjects, sorted(set(nbrs) | set(near)))
    only_sql = set(sqlp) - set(pyp)
    only_py = set(pyp) - set(sqlp)
    both = set(sqlp) & set(pyp)
    d_ov = max((abs(sqlp[k][2] - pyp[k].overlap) for k in both), default=0.0)
    d_dmin = max((abs(sqlp[k][3] - pyp[k].dmin) for k in both), default=0.0)
    d_dxy = max((abs(sqlp[k][4] - pyp[k].dxy) for k in both), default=0.0)
    d_dz = max((abs(sqlp[k][5] - pyp[k].dz) for k in both if sqlp[k][5] is not None and math.isfinite(pyp[k].dz)), default=0.0)
    dz_null_mismatch = sum(1 for k in both if (sqlp[k][5] is None) != (not math.isfinite(pyp[k].dz)))
    # pairs that sit exactly on a storage boundary may legitimately differ by rounding: report them, don't fail on them
    edge = [k for k in only_sql | only_py if abs((sqlp.get(k) or (None, None, pyp[k].overlap))[2] - STORE_OVERLAP) < 1e-3
            or abs(((sqlp[k][3]) if k in sqlp else pyp[k].dmin) - STORE_GATE_FT) < 1.0]
    ok = (len(only_sql | only_py) - len(edge)) == 0 and d_ov <= TOL_OVERLAP and d_dmin <= TOL_FT and d_dxy <= TOL_FT and d_dz <= 1e-6 and dz_null_mismatch == 0
    return {"pairs_sql": len(sqlp), "pairs_python": len(pyp), "only_sql": len(only_sql), "only_python": len(only_py), "on_boundary": len(edge),
            "max_d_overlap": d_ov, "max_d_dmin_ft": d_dmin, "max_d_dxy_ft": d_dxy, "max_d_dz_ft": d_dz, "dz_null_mismatch": dz_null_mismatch, "pass": ok,
            "examples": sorted(only_sql | only_py)[:5]}


def explain_ok(cur: Any) -> bool:
    plan = "\n".join(r[0] for r in cur.execute("EXPLAIN " + body()).fetchall())  # no params: % stays literal
    hit = GEOG_INDEX in plan
    print(f"    EXPLAIN body uses {GEOG_INDEX}: {'YES' if hit else 'NO -- investigate'}", flush=True)
    return hit


def dry_run(sample: int, seed: int) -> bool:
    with get_connection() as conn:
        conn.read_only = True
        with conn.cursor() as cur:
            cur.execute("SET LOCAL statement_timeout = 0")
            ok = explain_ok(cur)
            all_ids = [r[0] for r in cur.execute(f"SELECT w.api10 FROM curated.wells w WHERE {HZ1}").fetchall()]
            n_all = len(all_ids)
            ids = sorted(random.Random(seed).sample(all_ids, min(sample, n_all)))
            t0 = time.monotonic()
            rows = cur.execute(sampled_body(), {"ids": ids}).fetchall()
            dt_s = time.monotonic() - t0
            per = dt_s / len(ids)
            print(f"    sample {len(ids)} of {n_all:,} subjects: {len(rows):,} pairs in {dt_s:.1f}s -> "
                  f"~{len(rows) / len(ids) * n_all:,.0f} rows, ~{per * n_all / 60:.0f} min single-threaded (EXPLAIN-served)", flush=True)
            idt = identity(cur, rows, ids)
            print(f"    identity vs box/spacing3d.pair_geometry: {idt}", flush=True)
            ok &= idt["pass"]
        conn.rollback()
    print(f"DRY RUN {'PASS' if ok else 'FAIL'} — nothing was written", flush=True)
    return ok


def apply() -> bool:
    with get_connection() as conn:
        conn.autocommit = True
        with conn.cursor() as cur:
            cur.execute("SET statement_timeout = 0")
            print("[1/4] sql/59 — curated.well_neighbors (DROP + CREATE MATERIALIZED VIEW WITH DATA)", flush=True)
            t = time.monotonic()
            cur.execute((SQL / FILE).read_text(encoding="utf-8"))
            print(f"    built in {(time.monotonic() - t) / 60:.1f} min", flush=True)
            print("[2/4] sql/31 — comment catalog", flush=True)
            cur.execute((SQL / "31_comments.sql").read_text(encoding="utf-8"))
            print("[3/4] validate", flush=True)
            ok = validate(cur)
            print("[4/4] REFRESH ... CONCURRENTLY smoke", flush=True)
            t = time.monotonic()
            cur.execute("REFRESH MATERIALIZED VIEW CONCURRENTLY curated.well_neighbors")
            print(f"    refreshed in {(time.monotonic() - t) / 60:.1f} min", flush=True)
    print(f"APPLY {'PASS' if ok else 'FAIL'}", flush=True)
    return ok


def validate(cur: Any) -> bool:
    ok = True
    kind = cur.execute("SELECT c.relkind FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace "
                       "WHERE n.nspname = 'curated' AND c.relname = 'well_neighbors'").fetchone()
    print(f"    relkind={kind and kind[0]!r} (expect 'm')", flush=True)
    ok &= bool(kind) and kind[0] == "m"
    n, dups, nulls = cur.execute("""
        SELECT (SELECT count(*) FROM curated.well_neighbors),
               (SELECT count(*) FROM (SELECT 1 FROM curated.well_neighbors GROUP BY api10, nbr_api10 HAVING count(*) > 1) x),
               (SELECT count(*) FROM curated.well_neighbors WHERE api10 IS NULL OR nbr_api10 IS NULL)""").fetchone()
    print(f"    rows={n:,} duplicate keys={dups} NULL keys={nulls} (both must be 0)", flush=True)
    ok &= dups == 0 and nulls == 0
    bad_hz, bad_bounds, self_pairs = cur.execute(f"""
        SELECT (SELECT count(*) FROM curated.well_neighbors p WHERE NOT EXISTS (SELECT 1 FROM curated.wells w WHERE w.api10 = p.api10 AND {HZ1})
                                                              OR NOT EXISTS (SELECT 1 FROM curated.wells w WHERE w.api10 = p.nbr_api10 AND {HZ1})),
               (SELECT count(*) FROM curated.well_neighbors WHERE overlap_frac < {STORE_OVERLAP} OR dmin_ft > {STORE_GATE_FT}),
               (SELECT count(*) FROM curated.well_neighbors WHERE api10 = nbr_api10)""").fetchone()
    print(f"    non-horizontal endpoints={bad_hz} out-of-bounds rows={bad_bounds} self pairs={self_pairs} (all must be 0)", flush=True)
    ok &= bad_hz == 0 and bad_bounds == 0 and self_pairs == 0
    subj = [r[0] for r in cur.execute("SELECT api10 FROM (SELECT DISTINCT api10 FROM curated.well_neighbors) x ORDER BY md5(api10) LIMIT 100").fetchall()]
    rows = cur.execute("SELECT api10, nbr_api10, overlap_frac, dmin_ft, dxy_ft, dz_ft, dfp_days FROM curated.well_neighbors WHERE api10 = ANY(%(a)s)", {"a": subj}).fetchall()
    idt = identity(cur, rows, subj)
    print(f"    stored rows vs box/spacing3d.pair_geometry (100 subjects): {idt}", flush=True)
    ok &= idt["pass"]
    ok &= explain_ok(cur)
    return ok


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--dry-run", action="store_true", help="read-only: EXPLAIN, sampled timing, identity vs Python")
    ap.add_argument("--sample", type=int, default=200)
    ap.add_argument("--seed", type=int, default=59)
    a = ap.parse_args(argv)
    return 0 if (dry_run(a.sample, a.seed) if a.dry_run else apply()) else 1


if __name__ == "__main__":
    raise SystemExit(main())
