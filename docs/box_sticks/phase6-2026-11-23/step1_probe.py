"""BOX sticks phase 6 step 1: size the design choices on live. READ-ONLY (every query in a READ ONLY transaction, rolled back).

    python docs/box_sticks/phase6-2026-11-23/step1_probe.py        (from the repo root, PYTHONPATH=.)
"""
from __future__ import annotations

import pandas as pd

from etl.db import get_connection

pd.set_option("display.width", 250)
pd.set_option("display.max_rows", 200)
pd.set_option("display.max_columns", 40)


def ro(sql: str, params: tuple = ()) -> pd.DataFrame:
    with get_connection() as conn:
        conn.autocommit = False
        with conn.cursor() as cur:
            cur.execute("SET TRANSACTION READ ONLY")
            cur.execute("SET LOCAL statement_timeout = '900s'")
            cur.execute(sql, params)
            df = pd.DataFrame(cur.fetchall(), columns=[d.name for d in cur.description])
        conn.rollback()
    return df


def show(title: str, sql: str) -> None:
    print(f"\n== {title}", flush=True)
    try:
        print(ro(sql).to_string(index=False), flush=True)
    except Exception as exc:  # noqa: BLE001
        print("ERROR", type(exc).__name__, str(exc)[:300], flush=True)


REC = "box.location_stick k JOIN box.location_set t ON t.set_id = k.set_id AND t.is_record"

show("1. record sticks against box.bench_scope and the record extents (the 50 % rule, on the legs)", f"""
WITH x AS (
  SELECT k.basin, k.location_id, bs.bench AS pool, bs.in_scope, e.extent_id,
         CASE WHEN e.extent_id IS NULL THEN NULL ELSE
           extensions.ST_Length(extensions.ST_Intersection(k.legs_geom, e.geom)::extensions.geography)
           / NULLIF(extensions.ST_Length(k.legs_geom::extensions.geography), 0) END AS inside_share,
         s.status, s.crowded
  FROM {REC}
  LEFT JOIN box.bench_scope bs ON bs.basin = k.basin AND k.formation_blueox = ANY (bs.member_benches)
  LEFT JOIN box.extent e ON e.is_record AND e.basin = bs.basin AND e.bench = bs.bench
  LEFT JOIN curated.box_location_status s ON s.location_id = k.location_id AND s.set_id = k.set_id)
SELECT basin,
       count(*) AS sticks,
       count(*) FILTER (WHERE pool IS NULL) AS no_scope_row,
       count(*) FILTER (WHERE pool IS NOT NULL AND NOT in_scope) AS scope_out,
       count(*) FILTER (WHERE in_scope AND extent_id IS NULL) AS in_scope_no_extent,
       count(*) FILTER (WHERE in_scope AND inside_share >= 0.5) AS inside_ge_50,
       count(*) FILTER (WHERE in_scope AND inside_share > 0 AND inside_share < 0.5) AS inside_0_to_50,
       count(*) FILTER (WHERE in_scope AND extent_id IS NOT NULL AND COALESCE(inside_share, 0) = 0) AS inside_0,
       count(*) FILTER (WHERE in_scope AND inside_share >= 0.5 AND status IN ('open', 'permitted', 'pending') AND NOT crowded) AS inside_and_inventory
FROM x GROUP BY 1 ORDER BY 1""")

show("1b. the same by pool (in-scope pools only)", f"""
WITH x AS (
  SELECT k.basin, bs.bench AS pool, e.extent_id,
         CASE WHEN e.extent_id IS NULL THEN NULL ELSE
           extensions.ST_Length(extensions.ST_Intersection(k.legs_geom, e.geom)::extensions.geography)
           / NULLIF(extensions.ST_Length(k.legs_geom::extensions.geography), 0) END AS inside_share
  FROM {REC}
  JOIN box.bench_scope bs ON bs.basin = k.basin AND k.formation_blueox = ANY (bs.member_benches) AND bs.in_scope
  LEFT JOIN box.extent e ON e.is_record AND e.basin = bs.basin AND e.bench = bs.bench)
SELECT basin, pool, count(*) AS sticks, count(*) FILTER (WHERE extent_id IS NULL) AS no_extent,
       count(*) FILTER (WHERE inside_share >= 0.5) AS ge_50, count(*) FILTER (WHERE inside_share > 0 AND inside_share < 0.5) AS part,
       count(*) FILTER (WHERE extent_id IS NOT NULL AND COALESCE(inside_share, 0) = 0) AS outside
FROM x GROUP BY 1, 2 ORDER BY 1, 3 DESC""")

show("1c. benches of record sticks with no scope row, or scoped out", f"""
SELECT k.basin, k.formation_blueox, bs.bench AS pool, bs.in_scope, count(*) AS sticks
FROM {REC} LEFT JOIN box.bench_scope bs ON bs.basin = k.basin AND k.formation_blueox = ANY (bs.member_benches)
WHERE bs.bench IS NULL OR NOT bs.in_scope GROUP BY 1, 2, 3, 4 ORDER BY 1, 5 DESC""")

show("2. nightly status of the record sticks", """
SELECT basin, status, crowded, counts_as_inventory, count(*) AS sticks
FROM curated.box_location_status GROUP BY 1, 2, 3, 4 ORDER BY 1, 5 DESC""")

show("3. U-turn sticks: count, whether legs + arc merge into ONE line, leg separation", f"""
SELECT k.basin, count(*) AS uturn_sticks,
       count(*) FILTER (WHERE extensions.ST_GeometryType(extensions.ST_LineMerge(extensions.ST_Collect(k.legs_geom, k.turn_geom))) = 'ST_LineString') AS merge_to_one_line,
       round(percentile_cont(0.5) WITHIN GROUP (ORDER BY extensions.ST_Distance(
           extensions.ST_LineInterpolatePoint(extensions.ST_GeometryN(k.legs_geom, 1), 0.5)::extensions.geography,
           extensions.ST_LineInterpolatePoint(extensions.ST_GeometryN(k.legs_geom, 2), 0.5)::extensions.geography) * 3.28084)::numeric) AS leg_gap_ft_p50,
       round(max(extensions.ST_Distance(
           extensions.ST_LineInterpolatePoint(extensions.ST_GeometryN(k.legs_geom, 1), 0.5)::extensions.geography,
           extensions.ST_LineInterpolatePoint(extensions.ST_GeometryN(k.legs_geom, 2), 0.5)::extensions.geography) * 3.28084)::numeric) AS leg_gap_ft_max,
       round(percentile_cont(0.5) WITHIN GROUP (ORDER BY k.completed_lateral_ft)::numeric) AS completed_ft_p50
FROM {REC} WHERE k.well_type = 'uturn' GROUP BY 1 ORDER BY 1""")

show("3b. single sticks: lateral length", f"""
SELECT k.basin, count(*) AS single_sticks, round(percentile_cont(0.5) WITHIN GROUP (ORDER BY k.completed_lateral_ft)::numeric) AS completed_ft_p50,
       round(percentile_cont(0.1) WITHIN GROUP (ORDER BY k.completed_lateral_ft)::numeric) AS p10, round(percentile_cont(0.9) WITHIN GROUP (ORDER BY k.completed_lateral_ft)::numeric) AS p90
FROM {REC} WHERE k.well_type = 'single' GROUP BY 1 ORDER BY 1""")

show("4. spacing: the generator's on BOX sticks", f"""
SELECT k.basin, round(percentile_cont(0.1) WITHIN GROUP (ORDER BY k.spacing_ft)::numeric) AS p10, round(percentile_cont(0.5) WITHIN GROUP (ORDER BY k.spacing_ft)::numeric) AS p50,
       round(percentile_cont(0.9) WITHIN GROUP (ORDER BY k.spacing_ft)::numeric) AS p90, count(*) FILTER (WHERE k.spacing_ft = 880) AS exactly_880
FROM {REC} GROUP BY 1 ORDER BY 1""")

show("4b. spacing: D64 on the record forecast runs (forecast-carrying rows)", """
SELECT r.basin, r.run_id, count(*) AS forecast_rows,
       round(percentile_cont(0.1) WITHIN GROUP (ORDER BY p.planned_spacing_ft)::numeric) AS p10, round(percentile_cont(0.5) WITHIN GROUP (ORDER BY p.planned_spacing_ft)::numeric) AS p50,
       round(percentile_cont(0.9) WITHIN GROUP (ORDER BY p.planned_spacing_ft)::numeric) AS p90,
       count(*) FILTER (WHERE p.spacing_source = 'default_880') AS default_880,
       round(percentile_cont(0.5) WITHIN GROUP (ORDER BY p.completed_lateral_ft)::numeric) AS completed_ft_p50
FROM box.pud_forecast p JOIN box.forecast_run r ON r.run_id = p.run_id AND r.is_record
WHERE p.coverage IN ('covered', 'covered_provisional') GROUP BY 1, 2 ORDER BY 1""")

show("5. the record forecast runs by coverage class", """
SELECT r.basin, r.run_id, p.coverage, count(*) AS rows
FROM box.pud_forecast p JOIN box.forecast_run r ON r.run_id = p.run_id AND r.is_record GROUP BY 1, 2, 3 ORDER BY 1, 4 DESC""")

show("6. curated.erebor_locations today", """
SELECT basin, category, extensions.ST_GeometryType(wellstick_geom) AS geom_type, count(*) AS rows, count(tvd) AS with_tvd
FROM curated.erebor_locations GROUP BY 1, 2, 3 ORDER BY 1, 2""")

show("6b. objects that depend on curated.erebor_locations", """
SELECT DISTINCT v.relkind, n.nspname || '.' || v.relname AS dependent
FROM pg_depend d JOIN pg_rewrite r ON r.oid = d.objid JOIN pg_class v ON v.oid = r.ev_class JOIN pg_namespace n ON n.oid = v.relnamespace
WHERE d.refobjid = 'curated.erebor_locations'::regclass AND v.oid <> d.refobjid ORDER BY 2""")

show("6c. curated.erebor_locations columns", """
SELECT string_agg(a.attname, ', ' ORDER BY a.attnum) AS columns FROM pg_attribute a
WHERE a.attrelid = 'curated.erebor_locations'::regclass AND a.attnum > 0 AND NOT a.attisdropped""")

show("7. land team's view today", """
SELECT basin, count(*) AS rows FROM curated.box_scout_locations GROUP BY 1 ORDER BY 1""")
