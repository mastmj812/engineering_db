-- =============================================================================
-- 32 — Wellstick degeneracy fix + Enverus BHL rescue (one-time migration)
--
-- Applies the sql/04 wellstick_geom change of 2026-07:
--
--   THE DEFECT (diagnosed read-only, 2026-07-14):
--   * 859 wellsticks in curated.wells were degenerate — every vertex
--     identical, ST_Length = 0, ST_LineMerge -> not a LineString. Origin is
--     the NOVI FEED, not Enverus and not the ETL: raw_novi."Wells" AND
--     "WellDetails" both carry BHL == MP == SHL exactly (a placeholder when
--     Novi has no real bottomhole; LP NULL on all 859). The old guard only
--     required >= 2 vertices PRESENT, not distinct. 77 of the 859 are
--     Delaware/Midland horizontals (66 producing); 226 sat inside
--     producing_reference, where a zero-length "corridor" is a 46 m disc at
--     the SHL that the >= 30%-overlap reconciliation can never realize a PUD
--     against.
--   * 2 further sticks (BOLL WEEVIL 27 34 FEDERAL COM #100H/#101H) were
--     SINGLE-VERTEX LINESTRINGs: the old precheck counted latitudes only,
--     while vertex construction needs lat AND lon (SHLLongitude NULL slipped
--     through).
--
--   THE FIX (sql/04, verified by read-only A/B against the live warehouse):
--   * Vertex precedence Novi WellDetails -> Novi Wells -> Enverus for SHL and
--     BHL (mirrors the surface_lat / bhl_lat header columns).
--   * A Novi BHL exactly equal to the Novi SHL is treated as the placeholder
--     it is: the vertex falls through to the Enverus BHL. A Novi MP equal to
--     the SHL is skipped (kept between a real LP and BHL it would zigzag the
--     stick back to surface). IS DISTINCT FROM, so a NULL coordinate never
--     discards a real vertex.
--   * NULL unless ST_MaxDistance(line, line) > 0 (the vertex-set diameter) —
--     catches both the all-identical and the single-vertex shapes;
--     ST_RemoveRepeatedPoints drops surviving consecutive duplicates.
--
--   A/B RESULT (2026-07-14, wells grain, whole matview):
--     old: 90,574 sticks / 92,908 wells, 859 degenerate
--     new: 92,544 sticks,                  0 degenerate
--     854 of 859 placeholder wells RESCUED via Enverus BHL (76 of the 77
--     Delaware/Midland horizontals, all 66 producing); 5 NULLed; 1,975
--     previously stickless wells gained sticks; 0 healthy sticks lost;
--     21 healthy sticks shortened slightly (their placeholder BHL was a
--     false final vertex doubling back to surface). 329 rescued sticks are
--     < 100 ft (true verticals with a trivially offset Enverus BHL) — kept:
--     the guard is topological, not a length floor.
--
-- CASCADE / REBUILD ORDER
-- curated.wells is a matview, so the definition change means
-- DROP ... CASCADE (inside sql/04) — and since sql/29 the cascade reaches the
-- ENTIRE curated schema except curated.production (raw-only sources):
-- production chain, formation chain, AND the intel chain
-- (curated.intel_locations LEFT JOINs curated.wells). Availability, not
-- memory, is the cost on the current 16 GB instance: each object is missing
-- until its step completes (production_forecast ~12 GB is the longest).
-- Run OFF-HOURS, outside the nightly ETL window, with explicit authorization.
--
-- CANONICAL APPLIER (validated, per-step timing, post-checks):
--     python -m scripts.apply_wellstick_fix
--
-- The psql equivalent below is the same topological order; prefer the Python
-- script (it reuses apply_intel_formation_blueox / apply_intel_pdp_support /
-- apply_erebor_locations, whose extra steps — crosswalk reload, refresh_all()
-- restore, sql/31 re-apply, validation queries — psql \ir cannot replicate).
-- =============================================================================

-- INDEX ORDERING IS LOAD-BEARING (learned on the 2026-07-14 first run): the
-- expression geography indexes must exist BEFORE any spatial builder that
-- filters with ST_DWithin(geom::geography, ...) or those builds seq-scan —
-- sql/23 ran 49 min instead of ~3 and sql/30 had to be cancelled after ~15 h
-- (it rebuilt in minutes once indexed). Hence the inline wells index right
-- after sql/04 (sql/26 can't run that early — it also indexes
-- intel_locations, which doesn't exist until sql/29), and sql/26 immediately
-- after sql/29, before every intel spatial builder.

\echo --- wells branch -------------------------------------------------------
\ir 04_curated.sql
CREATE INDEX IF NOT EXISTS idx_curated_wells_wellstick_geog
    ON curated.wells USING GIST ((wellstick_geom::geography));
ANALYZE curated.wells;
\ir 16_formation_blueox.sql
\ir 20_producing_reference.sql
\ir 23_formation_blueox_tvd.sql
\ir 06_curated_derived.sql
\ir 10_curated_forecast.sql

\echo --- intel branch (quarterly-reload step-5 order, indexes first) ---------
\ir 29_curated_intel_sf.sql
\ir 26_geography_indexes.sql
\ir 14_formation_crosswalk.sql
\ir 18_bench_reference.sql
\ir 19_intel_formation_blueox.sql
\ir 21_reconciled_inventory.sql
\ir 25_net_new_pdp.sql
\ir 30_intel_pdp_support.sql
\ir 22_erebor_locations.sql
\ir 31_comments.sql

-- =============================================================================
-- Sanity checks (scripts/apply_wellstick_fix.py runs these automatically):
--
--   -- 0 degenerate sticks:
--   SELECT COUNT(*) FROM curated.wells
--   WHERE wellstick_geom IS NOT NULL
--     AND ST_GeometryType(ST_LineMerge(wellstick_geom)) <> 'ST_LineString';
--
--   -- coverage (A/B baseline 2026-07: 92,544 sticks / 92,908 wells):
--   SELECT COUNT(*), COUNT(wellstick_geom) FROM curated.wells;
--
--   -- the poster children now carry real sticks:
--   SELECT api10, well_name, ST_AsText(wellstick_geom)
--   FROM curated.wells
--   WHERE api10 IN ('4247534648', '3002553735', '3002553736');
--
--   -- EXPLAIN the erebor tile query (pattern in apply_erebor_locations.py):
--   -- must hit the GiST/geography indexes, not seq-scan.
-- =============================================================================
