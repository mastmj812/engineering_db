-- =============================================================================
-- 40 — U-turn is_horizontal fix (one-time migration)
--
-- Applies the sql/06 is_horizontal change of 2026-08-11:
--
--   THE DEFECT (diagnosed live while verifying the sql/39 wellstick fix):
--   * Novi codes horseshoe wells as SlantCalculated = 'U-Turn (Horizontal)'.
--     The is_horizontal derivation tested ILIKE 'H%' — a PREFIX match — so
--     every u-turn well evaluated FALSE even though Enverus says HORIZONTAL
--     (the COALESCE prefers Novi). Live vocabulary at fix time:
--     Horizontal 85,128 / Vertical 8,104 / U-Turn (Horizontal) 263.
--   * Blast radius: all four is_horizontal consumers silently dropped the
--     263 u-turn wells (159 producing, first prod 2019-06 → 2026-05):
--     anduin's header-sync scope (invisible on the map), curated.
--     erebor_locations (missing PDP rows), curated.intel_pdp_support, and
--     narvi's warehouse queries.
--
--   THE FIX (canonical in sql/06; this file is the frozen apply record):
--   * ILIKE '%horizontal%' — substring, not prefix. Catches 'Horizontal',
--     'U-Turn (Horizontal)', and the Enverus fallback 'HORIZONTAL';
--     'Vertical' (and any future 'Directional') stay FALSE; NULL-both
--     stays NULL.
--
-- CREATE OR REPLACE (no DROP): wells_enriched is a plain view and the
-- column list is unchanged, so dependent matviews (erebor_locations,
-- intel_pdp_support) survive untouched — they pick the new flag up at
-- their next REFRESH (erebor_locations nightly; intel_pdp_support
-- quarterly). The view body below is a verbatim copy of sql/06's — if
-- the two ever diverge, sql/06 is the truth.
--
-- Apply: python -m scripts.apply_uturn_is_horizontal
--   (runs this file, validates the flag flip, then
--    REFRESH MATERIALIZED VIEW CONCURRENTLY curated.erebor_locations)
-- =============================================================================


CREATE OR REPLACE VIEW curated.wells_enriched AS
SELECT
    w.*,

    -- ------------------------------------------------------------------
    -- Blue Ox standardized formation (curated.formation_blueox, sql/16), with
    -- the TVD-sanity correction (curated.formation_blueox_tvd, sql/23) applied
    -- ON TOP: for the ~0.4% of producing horizontals whose tag is a gross depth
    -- outlier (e.g. an Enverus-substitution mis-tag — Wolfcamp landed in the
    -- "2nd Bone Spring" band), formation_blueox becomes the depth-nearest bench
    -- and the source becomes 'tvd_corrected'. The pre-correction value is kept as
    -- formation_blueox_base for audit; non-producing wells and non-flips pass the
    -- base through unchanged. Joined here (not baked into curated.wells) so the
    -- whole mapping re-derives with a cheap REFRESH, not a DROP-CASCADE rebuild.
    -- ------------------------------------------------------------------
    CASE WHEN fbt.corrected THEN fbt.corrected_code
         ELSE fb.formation_blueox END               AS formation_blueox,
    fb.formation_blueox                             AS formation_blueox_base,
    fb.formation_blueox_raw,
    CASE WHEN fbt.corrected THEN 'tvd_corrected'
         ELSE fb.formation_blueox_source END        AS formation_blueox_source,
    fb.basin_blueox,
    fb.formation_blueox_is_mapped,
    COALESCE(fbt.corrected, FALSE)                  AS formation_blueox_tvd_corrected,

    -- ------------------------------------------------------------------
    -- Vintage
    -- ------------------------------------------------------------------
    EXTRACT(YEAR FROM w.first_completion_date)::int    AS first_completion_year,
    EXTRACT(QUARTER FROM w.first_completion_date)::int AS first_completion_quarter,
    EXTRACT(YEAR FROM w.first_production_date)::int    AS first_production_year,
    CASE
        WHEN w.first_completion_date IS NULL              THEN NULL
        WHEN w.first_completion_date <  DATE '2017-01-01' THEN 'pre-2017'
        WHEN w.first_completion_date <  DATE '2020-01-01' THEN '2017-2019'
        WHEN w.first_completion_date <  DATE '2023-01-01' THEN '2020-2022'
        ELSE                                                   '2023+'
    END                                                AS completion_vintage_bucket,

    -- ------------------------------------------------------------------
    -- Lateral length classification
    -- ------------------------------------------------------------------
    CASE
        WHEN w.lateral_length_ft IS NULL OR w.lateral_length_ft <= 0 THEN NULL
        WHEN w.lateral_length_ft <  5000                             THEN '<5000'
        WHEN w.lateral_length_ft <  7500                             THEN '5000-7499'
        WHEN w.lateral_length_ft < 10000                             THEN '7500-9999'
        WHEN w.lateral_length_ft < 15000                             THEN '10000-14999'
        ELSE                                                              '15000+'
    END                                                AS lateral_length_class,

    -- ------------------------------------------------------------------
    -- Horizontal flag (Novi SlantCalculated preferred; Enverus trajectory
    -- fallback). Substring match, NOT prefix: Novi codes horseshoe wells
    -- as 'U-Turn (Horizontal)' — the old ILIKE 'H%' flagged all 263 of
    -- them non-horizontal and every is_horizontal consumer (anduin sync,
    -- erebor_locations, intel_pdp_support, narvi) dropped them (sql/40,
    -- 2026-08-11). Live vocabulary: Horizontal / Vertical /
    -- U-Turn (Horizontal); Enverus fallback HORIZONTAL/DIRECTIONAL/etc.
    -- ------------------------------------------------------------------
    CASE
        WHEN COALESCE(w.novi_slant_calculated, w.enverus_trajectory) ILIKE '%horizontal%' THEN TRUE
        WHEN COALESCE(w.novi_slant_calculated, w.enverus_trajectory) IS NULL              THEN NULL
        ELSE FALSE
    END                                                AS is_horizontal,

    -- ------------------------------------------------------------------
    -- Per-stage / per-1000-ft completion intensity
    -- (curated.wells already exposes proppant_lbs_per_ft and fluid_bbl_per_ft
    --  from Enverus; these complement those with stage-frequency views.)
    -- ------------------------------------------------------------------
    CASE
        WHEN w.lateral_length_ft IS NULL OR w.lateral_length_ft <= 0
          OR w.frac_stages IS NULL OR w.frac_stages <= 0
        THEN NULL
        ELSE (w.frac_stages::numeric * 1000.0 / w.lateral_length_ft)
    END                                                AS stages_per_1000ft,
    CASE
        WHEN w.frac_stages IS NULL OR w.frac_stages <= 0 THEN NULL
        ELSE (w.proppant_lbs::numeric / w.frac_stages)
    END                                                AS proppant_lbs_per_stage,
    CASE
        WHEN w.frac_stages IS NULL OR w.frac_stages <= 0 THEN NULL
        ELSE (w.fluid_bbl::numeric / w.frac_stages)
    END                                                AS fluid_bbl_per_stage,

    -- ------------------------------------------------------------------
    -- Completion-intensity completeness flag — useful for type-curve cohort
    -- filtering ("only include wells with reported completion intensity").
    -- ------------------------------------------------------------------
    (w.proppant_lbs IS NOT NULL
       AND w.fluid_bbl IS NOT NULL
       AND w.frac_stages IS NOT NULL
       AND w.lateral_length_ft IS NOT NULL
       AND w.lateral_length_ft > 0)                    AS has_completion_intensity,

    -- ------------------------------------------------------------------
    -- Novi WellSpacing: same-zone lateral offset distance (ft, XY plane).
    -- Joined here (not baked into curated.wells) so surfacing it never
    -- forces the curated.wells DROP-CASCADE (production_forecast rebuild).
    -- Temporal semantics: AS-OF-FIRST-PRODUCTION (confirmed with Novi
    -- 2026-07-14); do NOT treat as current spacing. NULL = well absent
    -- from WellSpacing (standalone candidate). SENTINEL: exactly 2800.0
    -- (also the column max, ~12% of rows) is Novi's default/cap when no
    -- same-zone neighbor exists at first production — not real spacing.
    -- Standalone/tight/representative classification happens at runtime
    -- against each deal's planned spacing — never precomputed here.
    -- wellspacing_vintage = ingested_at of the nightly TRUNCATE+COPY
    -- snapshot (uniform per load).
    -- ------------------------------------------------------------------
    ws."LateralCloserXY"                               AS lateral_closer_xy_ft,
    ws.ingested_at                                     AS wellspacing_vintage

FROM curated.wells w
LEFT JOIN curated.formation_blueox fb
       ON fb.api10 = w.api10
LEFT JOIN curated.formation_blueox_tvd fbt
       ON fbt.api10 = w.api10
LEFT JOIN raw_novi."WellSpacing" ws
       ON ws."API10" = w.api10
      AND ws."DeletedAt" IS NULL;
