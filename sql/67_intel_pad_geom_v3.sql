-- =============================================================================
-- 67 — curated.intel_pad_member + curated.intel_pad_geom v3 (Novi DSU polygons)
--
-- Supersedes sql/46 (now a do-not-run note). Same objects, same key columns, so
-- consumers (erebor Highgrade, dealintake.warehouse.pad_iou) keep working.
--
-- WHY. sql/45/46 DERIVED pad polygons (hull of member sticks + 330 ft) because
-- the Snowflake share ships no pad geometry and the official Delaware pad
-- shapefile had not shipped. Novi's official 2026Q3 drop now carries DSU pad
-- polygons for both basins, loaded into raw_novi_intel.pads at report_version
-- '2026Q3' (sql/66 + etl/novi_intel/load_shapefiles). Michael (2026-10-20):
-- aggregate on Novi's drawn DSUs — they are also the geometry the planned
-- BOX-derived locations will infill (narvi-style).
--
-- RULE (Michael, 2026-10-20: "name + inside polygon"):
--   1. A stick belongs to its named Novi polygon when the polygon is from the
--      SAME vintage (pads.report_version = intel_locations.report_version) and
--      the stick's midpoint lies within the polygon or 330 ft of it (geodesic).
--      pad_key = pad_name; geometry = Novi's polygon (geom_source
--      'novi_polygon').
--   2. Same-name sticks outside that polygon (Novi reuses Delaware pad names:
--      the strays are almost all WDFD groups miles away) keep sql/46's 1-mile
--      single-linkage split: pad_key = pad_name || ' [stray k/n]', geometry =
--      hull + 330 ft (geom_source 'stick_hull_330ft').
--   3. A name with NO polygon in that vintage (e.g. the quarterly rebuild ran
--      before the pads were loaded) is exactly sql/46: pad_key = pad_name, or
--      pad_name || ' [k/n]' when it spans > 1 group; hull + 330 ft.
-- Every padded stick with geometry lands in exactly one pad_key.
--
-- MEASURED before writing (read-only, 2026-10-20, Delaware 2026Q3): all 7,778
-- live pad_names have a 3Q26 polygon; 94% of named sticks have their midpoint
-- inside their own polygon; every stick > 1 mi outside is WDFD (9,201). Derived
-- hulls vs Novi polygons: best-part IoU median 0.88.
-- Exact counts for this rule: PR description + apply_intel_pad_geom output.
--
-- STACKED PADS ARE NOVI'S MODEL: Midland pads are drawn per bench set over
-- shared acreage, so polygons overlap by design. Membership is by NAME first,
-- so overlap never reassigns a stick.
--
-- PROJECTION. DBSCAN needs planar metres: EPSG:32613 (UTM 13N), as sql/46.
-- The 330 ft (100.584 m) tolerance is geodesic (geography), so TX + NM need no
-- zone.
--
-- GEOMETRY. Novi polygons are forced 2D; an invalid one is repaired with
-- ST_MakeValid and its polygonal part kept, so a pad may be a MULTIPOLYGON.
--
-- DEPENDS ON: curated.intel_locations (sql/29) and raw_novi_intel.pads (sql/11
--   + sql/66). DROP-CASCADEs with intel_locations (quarterly) AND with a
--   `load_novi_intel --ddl` rebuild of raw_novi_intel (sql/11) — re-run the
--   apply after either. A pad LOAD (DELETE + INSERT) does not drop these;
--   re-run the apply so they pick the new polygons up.
-- REFRESH: quarterly only (NOT in etl/db.py:_CURATED_MATVIEWS).
-- RUN:    python -m scripts.apply_intel_pad_geom [--load-pads]
-- =============================================================================

DO $$
DECLARE
    obj text;
BEGIN
    -- geom first: it depends on member.
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
-- intel_pad_member: one row per padded stick -> its pad
-- ---------------------------------------------------------------------------
CREATE MATERIALIZED VIEW curated.intel_pad_member AS
WITH novi_pad AS (
    -- One polygon per (basin, report_version, pad_name). Novi ships unique
    -- names per drop; DISTINCT ON only guards a duplicate (largest wins).
    -- KEEP IDENTICAL to the novi_pad CTE in intel_pad_geom below.
    SELECT DISTINCT ON (p.basin, p.report_version, p.pad_name)
           p.basin, p.report_version, p.pad_name,
           CASE WHEN extensions.ST_IsValid(p.geom)
                THEN extensions.ST_Force2D(p.geom)
                ELSE extensions.ST_CollectionExtract(
                         extensions.ST_MakeValid(extensions.ST_Force2D(p.geom)), 3)
           END AS geom
    FROM raw_novi_intel.pads p
    WHERE p.pad_name IS NOT NULL AND p.pad_name <> '' AND p.geom IS NOT NULL
    ORDER BY p.basin, p.report_version, p.pad_name,
             extensions.ST_Area(p.geom) DESC, p.pad_id
),
padded AS (
    SELECT il.stick_id,
           il.basin,
           il.pad_name,
           il.wellstick_geom,
           np.pad_name IS NOT NULL                          AS has_polygon,
           COALESCE(extensions.ST_DWithin(
               (CASE WHEN extensions.GeometryType(il.wellstick_geom) = 'LINESTRING'
                     THEN extensions.ST_LineInterpolatePoint(il.wellstick_geom, 0.5)
                     ELSE extensions.ST_PointOnSurface(il.wellstick_geom)
                END)::extensions.geography,
               np.geom::extensions.geography,
               100.584                                      -- 330 ft
           ), false)                                        AS in_polygon
    FROM curated.intel_locations il
    LEFT JOIN novi_pad np
           ON np.basin = il.basin
          AND np.report_version = il.report_version
          AND np.pad_name = il.pad_name
    WHERE il.pad_name IS NOT NULL
      AND il.pad_name <> ''
      AND il.wellstick_geom IS NOT NULL
),
clustered AS (
    -- Sticks not inside their named polygon: sql/46's 1-mile single-linkage
    -- split (1 mile = 1609.344 m in UTM 13N).
    SELECT p.stick_id,
           p.basin,
           p.pad_name,
           p.has_polygon,
           extensions.ST_ClusterDBSCAN(
               extensions.ST_Transform(p.wellstick_geom, 32613), 1609.344, 1
           ) OVER (PARTITION BY p.basin, p.pad_name)        AS cid
    FROM padded p
    WHERE NOT p.in_polygon
),
parts AS (
    -- Deterministic group numbers: biggest first, ties -> lowest stick_id.
    SELECT basin, pad_name, cid,
           ROW_NUMBER() OVER (PARTITION BY basin, pad_name
                              ORDER BY COUNT(*) DESC, MIN(stick_id)) AS part,
           COUNT(*) OVER (PARTITION BY basin, pad_name)              AS n_groups
    FROM clustered
    GROUP BY basin, pad_name, cid
),
name_shape AS (
    -- Per name: does it have in-polygon sticks, and how many stray groups.
    SELECT p.basin, p.pad_name,
           bool_or(p.in_polygon)                            AS has_inside,
           COALESCE(MAX(s.n_groups), 0)                     AS n_groups
    FROM padded p
    LEFT JOIN parts s USING (basin, pad_name)
    GROUP BY p.basin, p.pad_name
)
SELECT p.stick_id,
       p.basin,
       p.pad_name,
       p.pad_name                                           AS pad_key,
       1                                                    AS pad_part,
       (1 + ns.n_groups)::int                               AS n_parts,
       'in_novi_polygon'::text                              AS member_rule
FROM padded p
JOIN name_shape ns USING (basin, pad_name)
WHERE p.in_polygon
UNION ALL
SELECT c.stick_id,
       c.basin,
       c.pad_name,
       CASE WHEN c.has_polygon
                THEN c.pad_name || ' [stray ' || pt.part || '/' || pt.n_groups || ']'
            WHEN pt.n_groups = 1
                THEN c.pad_name
            ELSE c.pad_name || ' [' || pt.part || '/' || pt.n_groups || ']'
       END                                                  AS pad_key,
       (pt.part + CASE WHEN ns.has_inside THEN 1 ELSE 0 END)::int     AS pad_part,
       (pt.n_groups + CASE WHEN ns.has_inside THEN 1 ELSE 0 END)::int AS n_parts,
       CASE WHEN c.has_polygon THEN 'stray_cluster'
            ELSE 'no_polygon_cluster' END                   AS member_rule
FROM clustered c
JOIN parts pt USING (basin, pad_name, cid)
JOIN name_shape ns USING (basin, pad_name)
WITH DATA;

CREATE UNIQUE INDEX idx_intel_pad_member_pk  ON curated.intel_pad_member (stick_id);
CREATE INDEX        idx_intel_pad_member_key ON curated.intel_pad_member (basin, pad_key);

-- ---------------------------------------------------------------------------
-- intel_pad_geom: one polygon per (basin, pad_key)
-- ---------------------------------------------------------------------------
CREATE MATERIALIZED VIEW curated.intel_pad_geom AS
WITH novi_pad AS (
    -- KEEP IDENTICAL to the novi_pad CTE in intel_pad_member above.
    SELECT DISTINCT ON (p.basin, p.report_version, p.pad_name)
           p.basin, p.report_version, p.pad_name,
           CASE WHEN extensions.ST_IsValid(p.geom)
                THEN extensions.ST_Force2D(p.geom)
                ELSE extensions.ST_CollectionExtract(
                         extensions.ST_MakeValid(extensions.ST_Force2D(p.geom)), 3)
           END AS geom
    FROM raw_novi_intel.pads p
    WHERE p.pad_name IS NOT NULL AND p.pad_name <> '' AND p.geom IS NOT NULL
    ORDER BY p.basin, p.report_version, p.pad_name,
             extensions.ST_Area(p.geom) DESC, p.pad_id
),
grp AS (
    SELECT pm.basin,
           pm.pad_key,
           pm.pad_name,
           pm.pad_part,
           pm.n_parts,
           pm.member_rule,
           MIN(il.report_version)                           AS report_version,
           COUNT(*)                                         AS n_sticks,
           COUNT(*) FILTER (WHERE il.category = 'PUD')      AS n_pud,
           COUNT(*) FILTER (WHERE il.category = 'RES')      AS n_res,
           extensions.ST_ConvexHull(extensions.ST_Collect(il.wellstick_geom)) AS hull
    FROM curated.intel_pad_member pm
    JOIN curated.intel_locations il ON il.stick_id = pm.stick_id
    GROUP BY pm.basin, pm.pad_key, pm.pad_name, pm.pad_part, pm.n_parts, pm.member_rule
),
shaped AS (
    SELECT g.*,
           CASE WHEN g.member_rule = 'in_novi_polygon'
                THEN np.geom::extensions.geography
                -- 330 ft = 100.584 m, geodesic (unchanged from sql/45/46).
                ELSE extensions.ST_Buffer(g.hull::extensions.geography, 100.584)
           END                                              AS geog
    FROM grp g
    LEFT JOIN novi_pad np
           ON np.basin = g.basin
          AND np.report_version = g.report_version
          AND np.pad_name = g.pad_name
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
       CASE WHEN member_rule = 'in_novi_polygon' THEN 'novi_polygon'
            ELSE 'stick_hull_330ft' END                     AS geom_source,
       report_version,
       geog::extensions.geometry                            AS geom
FROM shaped
WITH DATA;

CREATE UNIQUE INDEX idx_intel_pad_geom_pk   ON curated.intel_pad_geom (basin, pad_key);
CREATE INDEX        idx_intel_pad_geom_geom ON curated.intel_pad_geom USING GIST (geom);

COMMENT ON MATERIALIZED VIEW curated.intel_pad_member IS
'Padded Novi Intelligence sticks (latest vintage, PUD + RES with geometry) mapped to a pad. Rule (sql/67, Michael 2026-10-20): a stick whose midpoint lies within its named Novi DSU polygon of the same vintage (raw_novi_intel.pads, +330 ft geodesic) -> pad_key = pad_name; same-name sticks outside it (Novi reuses Delaware names, mostly WDFD groups) -> 1-mile single-linkage groups keyed pad_name || '' [stray k/n]''; names with no polygon in the vintage -> sql/46 keys (pad_name, or pad_name || '' [k/n]''). Quarterly only; DROP-CASCADEs with intel_locations and with a sql/11 rebuild; rebuilt by scripts.apply_intel_pad_geom. sql/67 (supersedes sql/46).';
COMMENT ON COLUMN curated.intel_pad_member.pad_key IS
'Pad identifier, unique per basin: pad_name for sticks inside Novi''s polygon; pad_name || '' [stray k/n]'' for same-name sticks outside it; sql/46 keys when the name has no polygon. Join key to curated.intel_pad_geom (basin, pad_key).';
COMMENT ON COLUMN curated.intel_pad_member.pad_part IS
'Group number within pad_name: 1 = the in-polygon pad when there is one, then stray groups by size (ties -> lowest stick_id).';
COMMENT ON COLUMN curated.intel_pad_member.n_parts IS
'Number of separate groups Novi''s pad_name spans (in-polygon pad + stray groups); > 1 means Novi reused the name.';
COMMENT ON COLUMN curated.intel_pad_member.member_rule IS
'in_novi_polygon | stray_cluster (name has a polygon, stick outside it) | no_polygon_cluster (no polygon for the name in this vintage — sql/46 fallback).';

COMMENT ON MATERIALIZED VIEW curated.intel_pad_geom IS
'Novi Intelligence pad/DSU polygons, one row per (basin, pad_key) from curated.intel_pad_member. In-polygon pads carry Novi''s own drawn DSU polygon (raw_novi_intel.pads, same vintage; geom_source novi_polygon); stray groups and names without a polygon carry the member-stick convex hull + 330 ft geodesic (stick_hull_330ft, sql/45 calibration: median area ratio 1.02 vs legacy Novi polygons). Novi stacks pads per bench set over shared acreage, so polygons overlap by design. Only pads with at least one stick — every Novi DSU polygon, stick or not, stays in raw_novi_intel.pads. Quarterly only; DROP-CASCADEs with intel_locations and with a sql/11 rebuild; rebuilt by scripts.apply_intel_pad_geom. sql/67 (supersedes sql/46).';
COMMENT ON COLUMN curated.intel_pad_geom.pad_key IS
'Pad identifier (see curated.intel_pad_member.pad_key). Unique per basin.';
COMMENT ON COLUMN curated.intel_pad_geom.acres IS
'Geodesic area of geom in acres (Novi''s polygon, or the derived hull + 330 ft) — erebor Highgrade per-acre values divide by this.';
COMMENT ON COLUMN curated.intel_pad_geom.n_sticks IS
'Member sticks (PUD + RES) with geometry; n_pud + n_res.';
COMMENT ON COLUMN curated.intel_pad_geom.geom_source IS
'Provenance of geom: novi_polygon (Novi-drawn DSU polygon of report_version) or stick_hull_330ft (derived: member-stick hull + 330 ft).';
COMMENT ON COLUMN curated.intel_pad_geom.report_version IS
'Novi vintage of the member sticks (and of the polygon when geom_source = novi_polygon).';
