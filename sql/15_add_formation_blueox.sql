-- =============================================================================
-- 15 — Add formation_blueox to curated.wells
--
-- One-time migration to apply the five new columns added to sql/04_curated.sql:
--
--   formation_blueox_raw         source-selected raw string (pre-standardization)
--   formation_blueox_source      'novi' | 'enverus' | NULL (which source won)
--   basin_blueox                 'delaware' | 'midland' | NULL
--   formation_blueox             Blue Ox canonical code (NULL when unmapped)
--   formation_blueox_is_mapped   bool: did the crosswalk resolve a code?
--
-- formation_blueox is populated by joining ref.formation_crosswalk (sql/14), so
-- that reference table must exist first — hence the \ir 14 below.
--
-- Same drop-and-rebuild dance as sql/08 — curated.wells is a MATERIALIZED VIEW
-- (no ALTER ADD COLUMN). DROP ... CASCADE also drops everything downstream:
-- wells_enriched / production_normalized / type_curve_cohorts (sql/06),
-- production_forecast / production_combined (sql/10), and intel_locations
-- (sql/12). The \ir chain rebuilds them in dependency order; sql/12 restores
-- the complete curated.refresh_all().
--
-- Run order: after sql/04 has been updated; from the PROJECT ROOT (the \copy in
-- sql/14 is path-relative):
--   psql -d oilgas -f sql/15_add_formation_blueox.sql
-- =============================================================================


\echo
\echo --- 1. (Re)load the formation crosswalk reference table ---
\ir 14_formation_crosswalk.sql


\echo
\echo --- 2. Drop curated.wells CASCADE ---
DROP MATERIALIZED VIEW IF EXISTS curated.wells CASCADE;


\echo
\echo --- 3. Re-build curated.wells with formation_blueox ---
\ir 04_curated.sql


\echo
\echo --- 4. Re-build curated.production ---
\ir 05_curated_production.sql


\echo
\echo --- 5. Re-build wells_enriched + production_normalized + cohorts ---
\ir 06_curated_derived.sql


\echo
\echo --- 6. Re-build production_forecast + production_combined ---
\ir 10_curated_forecast.sql


\echo
\echo --- 7. Re-build intel_locations (restores full refresh_all) ---
\ir 12_curated_intel.sql


-- =============================================================================
-- DONE. Sanity checks (psql / pgAdmin):
--
--   -- Row-count parity (wells_enriched is a plain view over wells):
--   SELECT (SELECT COUNT(*) FROM curated.wells)          AS wells,
--          (SELECT COUNT(*) FROM curated.wells_enriched) AS enriched;
--
--   -- Precedence spot-check — trigger formations now carry the Enverus value:
--   SELECT formation, env_interval, formation_blueox_raw,
--          formation_blueox_source, formation_blueox
--   FROM curated.wells
--   WHERE formation IN ('WOLFCAMP A','WOLFCAMP A (XY)','WOLFCAMP A (XY) SHELF',
--                       'WOLFCAMP B','LOWER SPRABERRY SAND')
--   LIMIT 30;
--
--   -- Distribution of the standardized code:
--   SELECT formation_blueox, COUNT(*)
--   FROM curated.wells GROUP BY 1 ORDER BY 2 DESC;
--
--   -- Crosswalk-gap audit (drives CSV completion):
--   SELECT basin_blueox, formation_blueox_source, formation_blueox_raw, COUNT(*)
--   FROM curated.wells
--   WHERE formation_blueox IS NULL AND formation_blueox_raw IS NOT NULL
--   GROUP BY 1,2,3 ORDER BY 4 DESC;
-- =============================================================================
