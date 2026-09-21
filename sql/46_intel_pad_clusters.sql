-- =============================================================================
-- 46 — curated.intel_pad_member + curated.intel_pad_geom  (pads split by space)
--
-- Supersedes sql/45 (now a DO-NOT-RUN tombstone). sql/45 drew one convex hull
-- per (basin, pad_name). That was right for 2026Q3 Midland and wrong for
-- 2026Q3 Delaware, whose pad_name backfill landed after sql/45 shipped.
--
-- WHY. Novi reuses pad names across unrelated groups of sticks in Delaware.
-- Measured live 2026-09-21 (read-only): 2,663 of 7,778 Delaware pad_names
-- (34%) are two spatially separate groups; 5,527 of the ~5,700 sticks outside
-- their pad's main group are Woodford, typically a ~2-stick Woodford group
-- sharing a name with an ~18-stick multi-bench pad elsewhere. Example:
-- 'Delaware Pad 7890' = 24 sticks in Eddy Co. NM + 2 Woodford RES sticks in
-- Pecos Co. TX, ~150 mi apart. The sql/45 hull over both was a 227,109-acre
-- sliver; Delaware pad P90 was 64,290 ac (Midland P90: 1,746 ac). That broke
-- the Highgrade map and every per-acre $ value on the affected pads, and merged
-- two unrelated pads' sums. Raised with Novi; this is the warehouse-side guard.
--
-- WHAT. Within each (basin, pad_name), member sticks are clustered with
-- ST_ClusterDBSCAN: eps = 1 mile, minpoints = 1, which is single-linkage (a
-- stick joins a group if it lies within 1 mi of any member). Each group is its
-- own pad:
--   pad_key = pad_name                          when the name forms 1 group
--   pad_key = pad_name || ' [k/n]'              when it forms n > 1 groups
-- Groups are numbered by size (largest = 1), with ties broken by the lowest
-- stick_id, so the key is deterministic across rebuilds. The hull + 330 ft
-- geodesic buffer is unchanged from sql/45 (calibration below).
--
-- EPS CALIBRATION (2026-09-21, read-only, 2026Q3):
--     eps     Delaware names split   Midland names split   Delaware part acres P99 / max
--   0.25 mi        4,304                 1,589                 2,275 / 4,286
--   0.5  mi        3,431                     6                 2,592 / 5,227
--   1    mi        2,663                     0                 2,988 / 5,227   <- chosen
--   2    mi        2,298                     0                 3,684 / 8,206
--   5    mi        1,895                     0                 6,126 / 13,904
-- Midland (no known collisions) is stable from 1 mi up, so gaps between sticks
-- inside a real pad are under 1 mi. Delaware keeps splitting at every eps,
-- which is what name collisions look like. Collisions placed < 1 mi apart
-- still merge (at most the 365 names that merge between 1 and 2 mi, a bounded
-- and small-hull residue).
--
-- PROJECTION. DBSCAN needs planar metres: EPSG:32613 (UTM 13N) for both basins.
-- Midland sits ~4.5 deg east of the zone's central meridian; scale error there
-- is ~0.2%, i.e. ~3 m on a 1-mile eps.
--
-- BUFFER CALIBRATION (sql/45, 2026-09-18, unchanged): against 4,585 Delaware
-- 2025Q3 legacy Novi polygons, hull + 330 ft gave median area ratio 1.02
-- (P10-P90 0.91-1.08), median IoU 0.86.
--
-- STACKED PADS ARE NOVI'S MODEL (unchanged from sql/45): Midland pads are
-- defined per bench set over shared acreage, so polygons overlap by design.
--
-- CONSUMERS: erebor Highgrade aggregates by pad_key via intel_pad_member
-- (stick_id -> pad_key) and draws/looks up intel_pad_geom by (basin, pad_key).
--
-- DEPENDS ON: curated.intel_locations (sql/29). Both objects DROP-CASCADE with
--   it, so this is a QUARTERLY step anywhere after `load_intel_sf --curated`.
--   intel_pad_geom depends on intel_pad_member (member first).
-- REFRESH: quarterly only (NOT in etl/db.py:_CURATED_MATVIEWS).
-- RUN:    python -m scripts.apply_intel_pad_geom
-- SANITY: member rows == padded sticks with geometry in intel_locations;
--         geom rows == distinct (basin, pad_key) in member; SUM(n_sticks) ==
--         member rows; 0 dup/NULL keys; every geom a valid POLYGON.
-- =============================================================================

DO $$
DECLARE
    obj text;
BEGIN
    -- geom first: it depends on member. sql/45's intel_pad_geom has no member.
    FOREACH obj IN ARRAY ARRAY['intel_pad_geom', 'intel_pad_member'] LOOP
        IF EXISTS (
            SELECT 1 FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace
            WHERE n.nspname = 'curated' AND c.relname = obj AND c.relkind = 'v'
        ) THEN
            EXECUTE format('DROP VIEW curated.%I CASCADE', obj);
        ELSIF EXISTS (
            SELECT 1 FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace
            WHERE n.nspname = 'curated' AND c.relname = obj AND c.relkind = 'm'
        ) THEN
            EXECUTE format('DROP MATERIALIZED VIEW curated.%I CASCADE', obj);
        END IF;
    END LOOP;
END $$;

-- ---------------------------------------------------------------------------
-- intel_pad_member: one row per padded stick -> its spatial pad group
-- ---------------------------------------------------------------------------
CREATE MATERIALIZED VIEW curated.intel_pad_member AS
WITH clustered AS (
    SELECT il.stick_id,
           il.basin,
           il.pad_name,
           -- 1 mile = 1609.344 m in UTM 13N (see PROJECTION above)
           extensions.ST_ClusterDBSCAN(
               extensions.ST_Transform(il.wellstick_geom, 32613), 1609.344, 1
           ) OVER (PARTITION BY il.basin, il.pad_name)      AS cid
    FROM curated.intel_locations il
    WHERE il.pad_name IS NOT NULL
      AND il.pad_name <> ''
      AND il.wellstick_geom IS NOT NULL
),
parts AS (
    -- Deterministic part numbers: biggest group first, ties -> lowest stick_id.
    SELECT basin, pad_name, cid,
           ROW_NUMBER() OVER (PARTITION BY basin, pad_name
                              ORDER BY COUNT(*) DESC, MIN(stick_id)) AS pad_part,
           COUNT(*) OVER (PARTITION BY basin, pad_name)              AS n_parts
    FROM clustered
    GROUP BY basin, pad_name, cid
)
SELECT c.stick_id,
       c.basin,
       c.pad_name,
       CASE WHEN p.n_parts = 1 THEN c.pad_name
            ELSE c.pad_name || ' [' || p.pad_part || '/' || p.n_parts || ']'
       END                                                  AS pad_key,
       p.pad_part::int                                      AS pad_part,
       p.n_parts::int                                       AS n_parts
FROM clustered c
JOIN parts p USING (basin, pad_name, cid)
WITH DATA;

CREATE UNIQUE INDEX idx_intel_pad_member_pk  ON curated.intel_pad_member (stick_id);
CREATE INDEX        idx_intel_pad_member_key ON curated.intel_pad_member (basin, pad_key);

-- ---------------------------------------------------------------------------
-- intel_pad_geom: one polygon per (basin, pad_key)
-- ---------------------------------------------------------------------------
CREATE MATERIALIZED VIEW curated.intel_pad_geom AS
WITH hull AS (
    SELECT pm.basin,
           pm.pad_key,
           pm.pad_name,
           pm.pad_part,
           pm.n_parts,
           COUNT(*)                                         AS n_sticks,
           COUNT(*) FILTER (WHERE il.category = 'PUD')      AS n_pud,
           COUNT(*) FILTER (WHERE il.category = 'RES')      AS n_res,
           extensions.ST_ConvexHull(extensions.ST_Collect(il.wellstick_geom)) AS hull
    FROM curated.intel_pad_member pm
    JOIN curated.intel_locations il ON il.stick_id = pm.stick_id
    GROUP BY pm.basin, pm.pad_key, pm.pad_name, pm.pad_part, pm.n_parts
),
buffered AS (
    -- 330 ft = 100.584 m, geodesic (geography buffer) so TX + NM need no zone.
    SELECT h.*,
           extensions.ST_Buffer(h.hull::extensions.geography, 100.584) AS geog
    FROM hull h
)
SELECT basin,
       pad_key,
       pad_name,
       pad_part,
       n_parts,
       n_sticks,
       n_pud,
       n_res,
       extensions.ST_Area(geog) / 4046.8564224              AS acres,
       'stick_hull_330ft'::text                             AS geom_source,
       geog::extensions.geometry                            AS geom
FROM buffered
WITH DATA;

CREATE UNIQUE INDEX idx_intel_pad_geom_pk   ON curated.intel_pad_geom (basin, pad_key);
CREATE INDEX        idx_intel_pad_geom_geom ON curated.intel_pad_geom USING GIST (geom);

COMMENT ON MATERIALIZED VIEW curated.intel_pad_member IS
'Padded Novi Intelligence sticks (latest vintage, PUD + RES with geometry) mapped to a SPATIAL pad group: within each (basin, pad_name), sticks are single-linkage clustered at 1 mile (ST_ClusterDBSCAN, UTM 13N). Novi reuses pad names across unrelated groups in Delaware (2026Q3: 34% of names, mostly Woodford groups), so pad_name alone is not a pad. pad_key = pad_name when the name is one group, else pad_name || '' [k/n]'' (k = 1 for the largest group). Quarterly only; DROP-CASCADEs with intel_locations; rebuilt by scripts.apply_intel_pad_geom. sql/46.';
COMMENT ON COLUMN curated.intel_pad_member.pad_key IS
'Spatial pad identifier, unique per basin: pad_name when Novi''s name forms one 1-mile group, else pad_name || '' [k/n]''. Join key to curated.intel_pad_geom (basin, pad_key).';
COMMENT ON COLUMN curated.intel_pad_member.pad_part IS
'Group number within pad_name, 1 = largest (ties -> lowest stick_id).';
COMMENT ON COLUMN curated.intel_pad_member.n_parts IS
'Number of separate 1-mile groups Novi''s pad_name spans; > 1 means Novi reused the name.';

COMMENT ON MATERIALIZED VIEW curated.intel_pad_geom IS
'Novi Intelligence pad/DSU polygons DERIVED from member sticks: one row per (basin, pad_key) from curated.intel_pad_member, i.e. per spatial group of a Novi pad_name, not per name. Convex hull of member sticks (PUD + RES) buffered 330 ft geodesically. The Snowflake share ships no pad polygons (raw_intel.pad lat/lon all NULL). 330 ft calibrated against 4,585 Delaware 2025Q3 legacy polygons: median area ratio 1.02 (P10-P90 0.91-1.08), median IoU 0.86. Novi stacks pads per bench set over shared acreage, so polygons overlap by design. Quarterly only; DROP-CASCADEs with intel_locations; rebuilt by scripts.apply_intel_pad_geom. sql/46 (supersedes sql/45).';
COMMENT ON COLUMN curated.intel_pad_geom.pad_key IS
'Spatial pad identifier (see curated.intel_pad_member.pad_key). Unique per basin.';
COMMENT ON COLUMN curated.intel_pad_geom.acres IS
'Geodesic area of geom in acres. Approximation of Novi''s DSU acreage (median ratio 1.02 vs legacy polygons) — erebor Highgrade per-acre $ divides by this.';
COMMENT ON COLUMN curated.intel_pad_geom.n_sticks IS
'Member sticks (PUD + RES) with geometry that built the hull; n_pud + n_res.';
COMMENT ON COLUMN curated.intel_pad_geom.geom_source IS
'Provenance of geom: stick_hull_330ft (derived, not a Novi-drawn polygon).';
