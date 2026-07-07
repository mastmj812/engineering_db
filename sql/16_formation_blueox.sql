-- =============================================================================
-- 16 — curated.formation_blueox  (standalone, refreshable formation mapping)
--
-- Blue Ox standardized formation, factored OUT of curated.wells into its own
-- thin matview keyed by api10. Rationale: the mapping logic (precedence triggers
-- + ref.formation_crosswalk + basin resolution) is iterated frequently — every
-- crosswalk edit, and eventually the geologist's manual relands. When it lived
-- inside curated.wells, changing it meant DROP curated.wells CASCADE, which
-- re-materialized the 22M-row production_forecast / production_normalized chain
-- (which don't even reference formation_blueox — pure cascade collateral).
--
-- Now:
--   * Crosswalk CONTENT change  -> reload sql/14, then
--       REFRESH MATERIALIZED VIEW CONCURRENTLY curated.formation_blueox;
--     (the crosswalk is a JOINed table, so REFRESH re-runs the mapping — no DROP)
--   * Mapping LOGIC change (this file) -> DROP + re-create THIS matview only.
--     Nothing heavy depends on it; only curated.wells_enriched (a plain VIEW)
--     joins it, and that rebuilds for free.
--
-- Inputs all come from curated.wells columns, whose definitions are byte-identical
-- to what the old inline `bx` LATERAL read from the raw tables:
--   formation   = COALESCE(wd."Formation",  n."Formation")     (04_curated.sql:198)
--   subbasin    = COALESCE(wd."Subbasin",   n."Subbasin")      (04_curated.sql:114)
--   env_interval = e.envinterval                               (04_curated.sql:120)
--   env_basin    = e.envbasin                                  (04_curated.sql:117)
-- so this reproduces the prior formation_blueox values exactly.
--
-- Source precedence: prefer the Novi formation, EXCEPT for a set of coarse /
-- unreliable Novi values that defer to Enverus ENVInterval (finer Wolfcamp/
-- Spraberry benches; generic/unknown values; and SUB-WOODFORD, which Enverus
-- usually resolves to WOODFORD — a core step-out target). Either branch falls
-- back to the other source when the preferred value is NULL. The selected raw
-- string is standardized via ref.formation_crosswalk on (basin, raw_value).
--
-- Basin resolves from Novi Subbasin, falling back to Enverus ENVBasin. Three
-- basins carry a nomenclature: 'delaware', 'midland', and 'cbp' (Central Basin
-- Platform — scoped to its deep unconventional targets only; its conventional
-- shelf defaults to OTHER). Wells in none of the three stay NULL.
--
-- Unmapped -> formation_blueox NULL (delaware/midland: a crosswalk gap to review)
-- or OTHER (cbp: conventional shelf, intentionally bucketed). formation_blueox_raw
-- and formation_blueox_is_mapped are retained for traceability.
--
-- Run order: after sql/04 (needs curated.wells) and sql/14 (needs the crosswalk),
-- before sql/06 (curated.wells_enriched joins this).
--   psql -d oilgas -f sql/16_formation_blueox.sql
-- =============================================================================


DROP MATERIALIZED VIEW IF EXISTS curated.formation_blueox CASCADE;


CREATE MATERIALIZED VIEW curated.formation_blueox AS
SELECT
    w.api10,
    bx.raw_value                                               AS formation_blueox_raw,
    bx.source                                                  AS formation_blueox_source,
    bx.basin_token                                             AS basin_blueox,
    -- Delaware/Midland: unmapped -> NULL so crosswalk gaps surface for review.
    -- CBP: unmapped -> OTHER by design — we only crosswalk its deep unconventional
    -- targets (Woodford/Barnett/Mississippian); the conventional shelf is
    -- deliberately bucketed to OTHER, not treated as a gap to chase.
    CASE WHEN bx.basin_token = 'cbp' THEN COALESCE(fx.canonical_code, 'OTHER')
         ELSE fx.canonical_code
    END                                                        AS formation_blueox,
    (fx.canonical_code IS NOT NULL)                            AS formation_blueox_is_mapped
FROM curated.wells w
LEFT JOIN LATERAL (
    WITH base AS (
        SELECT
            w.formation     AS novi_formation,
            w.env_interval  AS env_interval,
            -- Basin: Novi Subbasin first; fall back to Enverus ENVBasin when Novi
            -- places the well outside Delaware/Midland. CBP is keyed on Novi
            -- Subbasin (Enverus lumps it under ENVBasin='PERMIAN OTHER').
            CASE
                WHEN w.subbasin ILIKE '%delaware%'      THEN 'delaware'
                WHEN w.subbasin ILIKE '%midland%'       THEN 'midland'
                WHEN w.subbasin ILIKE '%central basin%' THEN 'cbp'
                WHEN w.env_basin = 'DELAWARE'           THEN 'delaware'
                WHEN w.env_basin = 'MIDLAND'            THEN 'midland'
            END             AS basin_token,
            -- Coarse / unreliable Novi formation values where Enverus ENVInterval
            -- is preferred (finer benches, or Novi has no useful call at all).
            (w.formation IN (
                'WOLFCAMP A','WOLFCAMP A (XY)','WOLFCAMP A (XY) SHELF','WOLFCAMP B',
                'LOWER SPRABERRY SAND',
                'WOLFCAMP','BONE SPRING','BONE SPRINGS','SPRABERRY','UNKNOWN',
                -- SUB-WOODFORD: a vague Novi catch-all that Enverus resolves to
                -- WOODFORD for most modern horizontals — a core step-out target.
                'SUB-WOODFORD'
            ))              AS is_trigger
    )
    SELECT
        base.basin_token,
        CASE WHEN base.is_trigger
             THEN COALESCE(base.env_interval, base.novi_formation)
             ELSE COALESCE(base.novi_formation, base.env_interval)
        END AS raw_value,
        CASE WHEN base.is_trigger
             THEN CASE WHEN base.env_interval IS NOT NULL THEN 'enverus' ELSE 'novi' END
             ELSE CASE WHEN base.novi_formation IS NOT NULL THEN 'novi'
                       WHEN base.env_interval   IS NOT NULL THEN 'enverus'
                       ELSE NULL END
        END AS source
    FROM base
) bx ON TRUE
LEFT JOIN ref.formation_crosswalk fx
       ON fx.basin     = bx.basin_token
      AND fx.raw_value = bx.raw_value
;


-- Unique on api10 — required for REFRESH ... CONCURRENTLY.
CREATE UNIQUE INDEX idx_curated_formation_blueox_api10
    ON curated.formation_blueox (api10);

CREATE INDEX idx_curated_formation_blueox_code
    ON curated.formation_blueox (formation_blueox);


COMMENT ON MATERIALIZED VIEW curated.formation_blueox IS
'Blue Ox standardized formation, keyed by api10. Factored out of curated.wells so the mapping can be iterated (crosswalk edits / geologist relands) with a ~90k-row REFRESH instead of a DROP-CASCADE rebuild of the production chain. Precedence: Novi formation, except coarse/unreliable Novi values (WOLFCAMP A / A(XY) / A(XY) SHELF / B / LOWER SPRABERRY SAND; generic WOLFCAMP / BONE SPRING(S) / SPRABERRY / UNKNOWN; SUB-WOODFORD) that defer to Enverus ENVInterval. Raw string mapped via ref.formation_crosswalk on (basin_blueox, raw_value). Basin from Novi Subbasin -> Enverus ENVBasin; basins delaware/midland/cbp. NULL when unmapped (delaware/midland gap), OTHER for unmapped cbp (conventional shelf). Join into curated.wells_enriched.';
