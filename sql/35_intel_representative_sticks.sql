-- =============================================================================
-- 35 — curated.intel_representative_sticks  (representative novi_intel set
--      for a planned location — the Blue Ox TC-vs-Novi comparison selector)
--
-- PURPOSE: given one planned location (a narvi GENERATED stick), return the
-- novi_intel PUD/RES sticks whose ML forecasts are a fair benchmark for it:
--   * same formation_blueox bench      (curated.intel_formation_blueox)
--   * within radius_m stick-to-stick   (geography; default 1609 m = 1 mi)
--   * intel ll_ft within +/- lateral_tol of the subject's completed lateral
--     (default 0.25)
--   * category PUD/RES only — the only classes carrying an intel ML forecast
--     (curated.intel_forecast covers planned wells, never PDP).
--
-- This function is the SINGLE source of truth for the selection rule.
-- Consumers:
--   * narvi — at scenario save, per generated well; persists the resulting
--     stick_ids into narvi.inventory_well.detail->'novi_rep'
--     (mode='neighborhood'). Curated pud/res passthrough wells DO NOT call
--     this — their representative set is themselves (mode='self').
--   * anduin — fallback at Blue Ox drop/dossier build for legacy scenarios
--     saved before narvi persisted novi_rep.
--
-- SEMANTICS / EDGES:
--   * n < 3 is the caller's LOW-N flag threshold. The function never widens
--     the radius on its own — report thinness, don't hide it.
--   * subject_lateral_ft NULL or <= 0 -> the lateral band is SKIPPED (broader
--     set). Callers should pass a real completed lateral; the skip exists so
--     a missing lateral degrades to spatial+bench selection instead of an
--     empty set that reads as "no analogs here".
--   * Ordered nearest-first so LIMITed previews stay stable.
--   * stick_id is stable across quarterly reloads (raw_intel.stick_id_map is
--     append-only), but membership/forecasts are vintage-dependent — callers
--     record curated.intel_vintage_date() beside any persisted result.
--
-- PERFORMANCE: the ST_DWithin text matches sql/26's expression index
--   idx_intel_locations_wellstick_geog (wellstick_geom::geography). LANGUAGE
--   sql STABLE so the planner inlines the body; EXPLAIN on a call must show
--   that index, never a Seq Scan of curated.intel_locations.
--
-- DEPENDS ON: curated.intel_locations (sql/29), curated.intel_formation_blueox
--   (sql/19), sql/26 expression index. Plain function — survives matview
--   refreshes; after a quarterly DROP CASCADE of intel_locations it remains
--   defined and simply errors until the matview is recreated (no rebuild-order
--   change needed).
--
-- Idempotent: CREATE OR REPLACE.
-- =============================================================================

CREATE OR REPLACE FUNCTION curated.intel_representative_sticks(
    subject_geom       geometry,                 -- planned location sticks/legs, SRID 4326
    subject_bench      text,                     -- formation_blueox code, e.g. 'BS1_S'
    subject_lateral_ft numeric,                  -- completed lateral of the planned well
    radius_m           numeric DEFAULT 1609,     -- 1 mi
    lateral_tol        numeric DEFAULT 0.25      -- +/- fraction of subject lateral
) RETURNS TABLE (
    stick_id  bigint,
    unique_id text,
    category  text,
    ll_ft     numeric,
    dist_m    numeric
) AS $$
    SELECT
        il.stick_id,
        il.unique_id,
        il.category,
        il.ll_ft::numeric,
        ST_Distance(il.wellstick_geom::geography, subject_geom::geography)::numeric AS dist_m
    FROM curated.intel_locations il
    JOIN curated.intel_formation_blueox fb USING (stick_id)
    WHERE il.category IN ('PUD', 'RES')
      AND fb.formation_blueox = subject_bench
      AND il.wellstick_geom IS NOT NULL
      AND ST_DWithin(il.wellstick_geom::geography, subject_geom::geography, radius_m)
      AND (
            COALESCE(subject_lateral_ft, 0) <= 0     -- no lateral -> skip the band (documented)
            OR (il.ll_ft IS NOT NULL
                AND il.ll_ft BETWEEN subject_lateral_ft * (1 - lateral_tol)
                                 AND subject_lateral_ft * (1 + lateral_tol))
          )
    ORDER BY dist_m
$$ LANGUAGE sql STABLE;

COMMENT ON FUNCTION curated.intel_representative_sticks(geometry, text, numeric, numeric, numeric) IS
'Representative novi_intel PUD/RES sticks for one planned location: same formation_blueox bench, within radius_m (geography, default 1 mi), intel ll_ft within +/- lateral_tol (default 25%) of subject_lateral_ft (band skipped when subject lateral is NULL/<=0). Nearest-first. Single source of truth for the Blue Ox TC-vs-Novi comparison selection: narvi persists results per generated well at scenario save (detail->novi_rep, mode=neighborhood; curated pud/res sticks are their own set, mode=self); anduin calls it as a legacy fallback. n<3 = caller-side low-n flag; the function never widens the radius. Record curated.intel_vintage_date() beside persisted results. sql/35.';

-- Verification (EXPLAIN must show idx_intel_locations_wellstick_geog):
--
--   EXPLAIN (ANALYZE, BUFFERS)
--   SELECT * FROM curated.intel_representative_sticks(
--       (SELECT wellstick_geom FROM curated.intel_locations
--         WHERE category = 'PUD' AND wellstick_geom IS NOT NULL LIMIT 1),
--       'BS1_S', 10000);
