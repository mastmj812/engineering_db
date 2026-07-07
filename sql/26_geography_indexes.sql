-- =============================================================================
-- 26 — geography expression indexes for AOI ST_DWithin predicates
--
-- narvi's warehouse queries (inventory, azimuth stats, bench discovery) filter
-- with ST_DWithin(wellstick_geom::geography, ST_GeogFromText(aoi), meters) so
-- the buffer is in real meters, not degrees. The ::geography cast means the
-- existing GEOMETRY GiST indexes (idx_curated_wells_wellstick_geom,
-- idx_intel_locations_geom) CANNOT serve the predicate — every such query
-- seq-scans the table (through the wells_enriched view join for curated.wells),
-- and /parcels/inventory issues ~7 of them sequentially per parcel selection /
-- curate-scenario load. Over the Supabase WAN that is the whole "slow load".
--
-- Fix: expression GiST indexes on the geography cast. The planner matches
-- geom::geography in the query text against these directly. Geometry indexes
-- stay — anything filtering in 4326 degrees (e.g. && bbox joins) still uses
-- them.
-- =============================================================================

CREATE INDEX IF NOT EXISTS idx_curated_wells_wellstick_geog
    ON curated.wells USING GIST ((wellstick_geom::geography));

CREATE INDEX IF NOT EXISTS idx_intel_locations_wellstick_geog
    ON curated.intel_locations USING GIST ((wellstick_geom::geography));

ANALYZE curated.wells;
ANALYZE curated.intel_locations;

-- Verification (narvi's exact predicate shape; expect an Index Scan on the new
-- geog index, not a Seq Scan):
--
--   EXPLAIN (ANALYZE, BUFFERS)
--   SELECT count(*)
--   FROM curated.wells_enriched
--   WHERE wellstick_geom IS NOT NULL
--     AND ST_DWithin(wellstick_geom::geography,
--                    ST_GeogFromText('SRID=4326;POINT(-103.8 31.9)'), 1609.34);
