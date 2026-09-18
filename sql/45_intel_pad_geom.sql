-- =============================================================================
-- 45 — curated.intel_pad_geom  (Novi pad/DSU polygons derived from member sticks)
--
-- WHY. erebor's Highgrade choropleth + per-DSU gunbarrel join pad_name to a pad
-- POLYGON. The only polygons we ever had are the legacy overlay shapefile
-- (raw_novi_intel.pads), whose names match the 2025Q3 vintage only. The
-- Snowflake share ships no pad polygons at all: raw_intel.pad is name-only
-- (latitude/longitude are NULL on every row, verified 2026-09-18), and Novi
-- regenerates pad names every vintage. After the 2026Q3 reload, 0 of 4,773
-- Midland pad_names matched a legacy polygon -> Highgrade rendered nothing.
--
-- WHAT. One polygon per (basin, pad_name) over the LATEST vintage (inherits
-- sql/29's latest-report filter via curated.intel_locations): the convex hull of
-- every member stick (PUD + RES — pad membership is Novi's, class-agnostic),
-- buffered 330 ft geodesically.
--
-- BUFFER CALIBRATION (2026-09-18, read-only). Against the 4,585 Delaware 2025Q3
-- pads that DO have a legacy Novi polygon (same-name match, 100%):
--     buffer   median area ratio (hull / Novi)   P10-P90      median IoU
--       0 ft        0.80                          0.58-0.84     0.80
--     165 ft        0.91                          0.75-0.95     0.84
--     330 ft        1.02                          0.91-1.08     0.86   <- chosen
--     440 ft        1.08                          0.99-1.16     0.86
--     660 ft        1.23                          1.12-1.35     0.81
-- So acres (hence erebor's per-acre $) track Novi's own DSU acreage to ~2% at
-- the median. Still an APPROXIMATION — geom_source says so.
--
-- STACKED PADS ARE NOVI'S MODEL, NOT HULL BLEED. 2026Q3 Midland defines pads
-- per bench set over shared acreage (e.g. BRNT-only '2 Mile A nnn' under a
-- JM..WCB 'Undeveloped Pad A nnn'). Unbuffered hulls: 911 pad pairs overlap
-- >10% of the smaller pad; 906 have DISJOINT bench sets (vertical stacking),
-- 5 share a bench. Legacy shapefile polygons overlapped ~1-2%. Consumers that
-- pick "the pad under a point" must expect several. The 330 ft rim also makes
-- side-by-side neighbours share a thin edge sliver — cosmetic, acres unaffected.
-- ~150 names carry a ' copy' suffix (Novi QC residue) — kept verbatim.
--
-- COVERAGE follows the share's pad_name gap: 2026Q3 ships pad_name for Midland
-- only (Delaware 0 — raised with Novi; 2025Q3 was the reverse). A basin with no
-- pad_name produces no rows here; consumers must say so rather than render blank.
--
-- DEPENDS ON: curated.intel_locations (sql/29) — DROP-CASCADEs with it, so it is
--   a QUARTERLY step: scripts/apply_intel_pad_geom.py, anywhere after
--   `load_intel_sf --curated` (no dependency on the reconciliation chain).
-- REFRESH: quarterly only (NOT in etl/db.py:_CURATED_MATVIEWS) — intel_locations
--   itself only changes on a reload.
-- RUN:    python -m scripts.apply_intel_pad_geom
-- SANITY: rows == COUNT(DISTINCT (basin, pad_name)) in intel_locations;
--         0 dup/NULL keys; every geom a valid POLYGON; median acres ~ Novi's
--         (~950 ac Delaware 2025Q3 legacy median).
-- =============================================================================

DO $$
BEGIN
    IF EXISTS (
        SELECT 1 FROM pg_class c
        JOIN pg_namespace n ON n.oid = c.relnamespace
        WHERE n.nspname = 'curated' AND c.relname = 'intel_pad_geom' AND c.relkind = 'v'
    ) THEN
        EXECUTE 'DROP VIEW curated.intel_pad_geom CASCADE';
    ELSIF EXISTS (
        SELECT 1 FROM pg_class c
        JOIN pg_namespace n ON n.oid = c.relnamespace
        WHERE n.nspname = 'curated' AND c.relname = 'intel_pad_geom' AND c.relkind = 'm'
    ) THEN
        EXECUTE 'DROP MATERIALIZED VIEW curated.intel_pad_geom CASCADE';
    END IF;
END $$;

CREATE MATERIALIZED VIEW curated.intel_pad_geom AS
WITH hull AS (
    SELECT il.basin,
           il.pad_name,
           COUNT(*)                                         AS n_sticks,
           COUNT(*) FILTER (WHERE il.category = 'PUD')      AS n_pud,
           COUNT(*) FILTER (WHERE il.category = 'RES')      AS n_res,
           extensions.ST_ConvexHull(extensions.ST_Collect(il.wellstick_geom)) AS hull
    FROM curated.intel_locations il
    WHERE il.pad_name IS NOT NULL
      AND il.pad_name <> ''
      AND il.wellstick_geom IS NOT NULL
    GROUP BY il.basin, il.pad_name
),
buffered AS (
    -- 330 ft = 100.584 m, geodesic (geography buffer) so TX + NM need no zone.
    SELECT h.*,
           extensions.ST_Buffer(h.hull::extensions.geography, 100.584) AS geog
    FROM hull h
)
SELECT basin,
       pad_name,
       n_sticks,
       n_pud,
       n_res,
       extensions.ST_Area(geog) / 4046.8564224              AS acres,
       'stick_hull_330ft'::text                             AS geom_source,
       geog::extensions.geometry                            AS geom
FROM buffered
WITH DATA;

CREATE UNIQUE INDEX idx_intel_pad_geom_pk   ON curated.intel_pad_geom (basin, pad_name);
CREATE INDEX        idx_intel_pad_geom_geom ON curated.intel_pad_geom USING GIST (geom);

COMMENT ON MATERIALIZED VIEW curated.intel_pad_geom IS
'Novi Intelligence pad/DSU polygons DERIVED from member sticks: one row per (basin, pad_name) over the latest vintage (curated.intel_locations), convex hull of every member stick (PUD + RES) buffered 330 ft geodesically. The Snowflake share ships no pad polygons (raw_intel.pad lat/lon all NULL) and Novi renames pads every vintage, so the legacy raw_novi_intel.pads shapefile no longer matches. 330 ft calibrated against 4,585 Delaware 2025Q3 legacy polygons: median area ratio 1.02 (P10-P90 0.91-1.08), median IoU 0.86. Novi stacks pads per bench set over shared acreage, so polygons overlap by design. Coverage follows the share''s pad_name gap (2026Q3: Midland only). Quarterly only; DROP-CASCADEs with intel_locations; rebuilt by scripts.apply_intel_pad_geom. sql/45.';
COMMENT ON COLUMN curated.intel_pad_geom.acres IS
'Geodesic area of geom in acres. Approximation of Novi''s DSU acreage (median ratio 1.02 vs legacy polygons) — erebor Highgrade per-acre $ divides by this.';
COMMENT ON COLUMN curated.intel_pad_geom.n_sticks IS
'Member sticks (PUD + RES) with geometry that built the hull; n_pud + n_res.';
COMMENT ON COLUMN curated.intel_pad_geom.geom_source IS
'Provenance of geom: stick_hull_330ft (derived, not a Novi-drawn polygon).';
