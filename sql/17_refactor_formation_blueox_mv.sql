-- =============================================================================
-- 17 — Refactor formation_blueox out of curated.wells into its own matview
--
-- Supersedes the structure created by sql/15. Previously the Blue Ox formation
-- mapping (precedence triggers + ref.formation_crosswalk + basin resolution) was
-- computed INSIDE curated.wells, so every crosswalk / precedence edit required
-- DROP curated.wells CASCADE — which re-materialized the 22M-row production_*
-- chain even though none of it references formation_blueox.
--
-- After this migration the mapping lives in curated.formation_blueox (sql/16),
-- keyed by api10, and is joined into curated.wells_enriched (sql/06). Future
-- mapping changes cost a ~90k-row REFRESH (crosswalk content) or a tiny
-- DROP+CREATE of just that matview (logic) — the production chain is untouched.
--
-- This file performs the ONE-TIME heavy rebuild needed to move the columns off
-- curated.wells (a matview column-set change still requires DROP ... CASCADE).
--
-- Run from the PROJECT ROOT (the \copy in sql/14 is path-relative):
--   psql "<warehouse url>" -f sql/17_refactor_formation_blueox_mv.sql
-- On Supabase, prepend  SET statement_timeout=0;  for the session (pooler
-- ignores ALTER ROLE), and prefer the hardened ETL refresh afterward.
-- =============================================================================


\echo
\echo --- 1. (Re)load the formation crosswalk reference table (needed by sql/16) ---
\ir 14_formation_crosswalk.sql


\echo
\echo --- 2. Drop curated.wells CASCADE (takes formation_blueox + the production chain) ---
DROP MATERIALIZED VIEW IF EXISTS curated.wells CASCADE;


\echo
\echo --- 3. Rebuild curated.wells WITHOUT formation_blueox ---
\ir 04_curated.sql


\echo
\echo --- 4. Build curated.formation_blueox (reads curated.wells + ref.formation_crosswalk) ---
\ir 16_formation_blueox.sql


\echo
\echo --- 5. Rebuild the production chain + wells_enriched (now joins formation_blueox) ---
\ir 05_curated_production.sql
\ir 06_curated_derived.sql
\ir 10_curated_forecast.sql
\ir 12_curated_intel.sql


\echo
\echo --- 6. Refresh everything (or run the hardened per-matview ETL refresh) ---
SELECT curated.refresh_all();


\echo
\echo --- DONE. Verify: ---
\echo '  SELECT COUNT(*) FROM curated.formation_blueox;            -- ~ curated.wells'
\echo '  SELECT COUNT(*) FROM curated.wells_enriched WHERE formation_blueox IS NOT NULL;'
\echo '  -- curated.wells should NO LONGER have a formation_blueox column:'
\echo '  SELECT 1 FROM curated.wells LIMIT 0;  -- \\d curated.wells to confirm'
