-- =============================================================================
-- 30 — curated.intel_pdp_support  (per-PUD/RES offset-PDP support attributes)
--
-- PURPOSE: refine the raw novi_intel PUD/RES population into a realistic
-- developable set by attaching, to every stick, a family of OFFSET-SUPPORT
-- scores measured against the surrounding qualifying producing (PDP) wells in
-- the SAME bench. It is a VERIFIABILITY screen, not a quality screen: heavily
-- depleted areas score HIGH support (deplet_t covers that other tail — show them
-- side by side, don't treat high support as monotonically good). The credible
-- PUD extent per formation ~= the PDP extent plus a modest halo; dist_nearest_ft
-- is literally that halo width.
--
-- Keyed on stick_id; one row per PUD/RES stick (the LEFT JOIN LATERAL keeps every
-- stick). Consumed by: erebor Highgrade (filters + map color + xlsx export), the
-- land team's direct GIS read of curated.erebor_locations (sql/22 folds the full
-- score family in at Phase 3), and later narvi.
--
-- SCORE SEMANTICS (carried into erebor_locations COMMENT ON COLUMN at Phase 3):
--   pdp_count_* = 0   -> scored AND genuinely unsupported: a real, located stick
--                        in a known bench with NO qualifying in-bench offset in
--                        that radius. This is the flag population.
--   score IS NULL     -> NOT scorable: unmapped bench (formation_blueox NULL),
--                        missing landing TVD, or missing geometry. We emit NULL
--                        rather than formation-agnostic counts — agnostic offsets
--                        would FABRICATE support exactly where the bench is
--                        unknown. NULL means "no basis", 0 means "checked, none".
--   dist_3rd_nearest_ft NULL (but count>0) -> <3 qualifying offsets; that thinness
--                        is itself signal.
--
-- TUNABLE qualifying-PDP gate (every predicate visible below; these values were
-- tuned + validated at the Phase-1 Loving+Winkler review gate):
--   * within 5 mi   -> ST_DWithin(w.wellstick_geom::geography, pud.g, 8045)
--                      Text MUST match sql/26's idx_curated_wells_wellstick_geog
--                      expression index; EXPLAIN must show that index scan, never
--                      a Seq Scan of curated.wells.
--   * horizontal    -> COALESCE(novi_slant_calculated, enverus_trajectory) ILIKE '%horizontal%'
--                      (the sql/40 is_horizontal semantics — substring, not the old
--                      'H%' prefix, so 'U-Turn (Horizontal)' wells count. This file
--                      reads base tables, so the expression is inlined here and must
--                      track sql/40, not wells_enriched.)
--   * same bench    -> COALESCE(t.corrected_code, fb2.formation_blueox) = pud.code
--                      (TVD-corrected formation_blueox, sql/21_reconciled_inventory.sql:121)
--   * TVD guard     -> abs(w.tvd_ft - pud.tvd) <= 500 ft
--   * >= 6 mo prod  -> first_production_date <= current_date - interval '6 months'
--                      Past flowback; tracks the developable edge without
--                      misflagging PUDs next to genuine-but-young producers
--                      (Phase-1: 6mo vs 12mo moved unsupported@3mi only 11.1%->10.7%
--                      but is correct on the young-offset tail).
--   * ll_ft > 0
-- The PDP universe is NEVER county/basin-scoped — a basin-line PUD must see
-- support across the border.
--
-- DEPTH CONTEXT (added 2026-09 after the WCB_2 deep-TVD screening audit): the
-- ±500 ft TVD guard is a SIMILARITY gate, not a plausibility gate — a stick
-- Novi landed anomalously deep either matches the deepest local fringe within
-- 500 ft or scores NULL, and nothing above says how deep its comparison set
-- was. The audit found ~1,000 Delaware WCB_2 PUDs >200 ft deeper than ANY
-- same-bench producer within 3 mi (canonical case: South TX 657, Reeves Co. —
-- sticks at 11,634-11,678 ft vs adjacent WCB_2 PDP at ~11,050 ft, ratio
-- computed from 5 wells 3.6-4.9 mi away). Four columns make depth auditable:
--   * offset_median_tvd  -> median tvd_ft of the SAME guarded offset set that
--                           feeds offset_median_eur_ft / inflation_ratio: the
--                           depth the ratio was actually computed against.
--   * tvd_delta_ft       -> pud.tvd - offset_median_tvd (audit companion).
--   * tvd_excess_3mi_ft  -> pud.tvd - max(same-bench producer tvd_ft within
--                           3 mi), UNGUARDED (no ±500, no 6-mo gate — any
--                           producing horizontal ever). Positive = deeper than
--                           anything ever produced in this bench locally;
--                           >200 ft is the agreed anomaly line (app-side
--                           threshold, not baked in here). NULL = no same-bench
--                           producer within 3 mi at all (frontier — also
--                           suspect, distinguishable from 0-ish values).
--   * wca_delta_ft       -> pud.tvd - median(WCA_1/WCA_2 producer tvd_ft
--                           within 3 mi), unguarded. Screens the WCB_2 landing
--                           convention: measured PDP separation below WCA is
--                           med 516 ft (IQR 424-634) Delaware / 460 (377-549)
--                           Midland, so the land-team band is [400, 700] for
--                           WCB_2 (applied app-side). Computed for every bench
--                           (a WCA stick's own value ~0 — interpretable);
--                           NULL = no WCA producer within 3 mi.
-- The 3-mi depth-context gate deliberately drops the ±500/6-mo predicates:
-- same TVD-corrected bench + horizontal (sql/40 semantics) + ever-produced +
-- tvd_ft NOT NULL, radius 4827 m. One extra lateral scan; expect the build
-- ~1.5x the previous 25-45 min.
--
-- The current_date term makes matview CONTENT refresh-date dependent: it is
-- deterministic per refresh, but any diff of this matview against a re-scan
-- (e.g. the Phase-1 exploration) must be run SAME-DAY.
--
-- DEPENDS ON: curated.intel_locations (sql/29), curated.intel_formation_blueox
--   (sql/19), and — as the offset BASE tables — curated.wells (sql/04) +
--   curated.formation_blueox (sql/16) + curated.formation_blueox_tvd (sql/23),
--   plus the sql/26 expression GiST index idx_curated_wells_wellstick_geog.
--   Base tables deliberately, NOT curated.wells_enriched (view-inlining risk) and
--   NOT curated.producing_reference (lacks EUR/cum/is_horizontal and has no
--   geography expression index).
--
-- REFRESH CADENCE: QUARTERLY-ONLY, on demand. Deliberately NOT added to
--   etl/db.py:_CURATED_MATVIEWS (the nightly refresh set): a ~25-45 min basin-wide
--   rebuild buys <=1 quarter of freshness on a screen attribute, and staleness is
--   CONSERVATIVE — a newly-online well only ever ADDS support, so a stale matview
--   UNDER-states support, never over-states. On-demand path (works because of the
--   UNIQUE index + WITH DATA below):
--       REFRESH MATERIALIZED VIEW CONCURRENTLY curated.intel_pdp_support;
--
-- QUARTERLY REBUILD ORDER — this matview DROP-CASCADEs with intel_locations; once
--   sql/22 joins it (Phase 3), curated.erebor_locations drops with it too, so:
--       load_intel_sf --curated -> apply_intel_formation_blueox ->
--       apply_reconciled_inventory -> apply_intel_pdp_support (THIS, NEW) ->
--       apply_erebor_locations (stays FINAL). Re-run sql/26 after any matview drop.
--
-- RUN: scripts/apply_intel_pdp_support.py  (exec + validate). Idempotent:
--   DROP ... IF EXISTS CASCADE then CREATE ... WITH DATA.
-- =============================================================================

DROP MATERIALIZED VIEW IF EXISTS curated.intel_pdp_support CASCADE;

CREATE MATERIALIZED VIEW curated.intel_pdp_support AS
WITH pud AS (
    SELECT
        il.stick_id,
        fb.formation_blueox                     AS code,
        il.tvd,
        il.oil_eur,
        il.ll_ft,
        il.wellstick_geom::geography            AS g,
        -- scorable = a real, located stick in a KNOWN bench. NULL bench / TVD /
        -- geometry -> emit NULL scores (below), so pdp_count_* = 0 unambiguously
        -- means "scored and unsupported", never "we couldn't score it".
        (fb.formation_blueox IS NOT NULL
         AND il.tvd IS NOT NULL
         AND il.wellstick_geom IS NOT NULL)     AS scorable
    FROM curated.intel_locations il
    JOIN curated.intel_formation_blueox fb USING (stick_id)
    WHERE il.category IN ('PUD', 'RES')          -- BASE_CASE + EMERGING; NO county filter
)
SELECT
    pud.stick_id,
    -- Route unscorable rows to NULL for EVERY score. A bare pass-through would
    -- report count 0 (aggregate over the empty offset set) and conflate
    -- "unscorable" with "genuinely unsupported".
    CASE WHEN pud.scorable THEN agg.pdp_count_1mi           END AS pdp_count_1mi,
    CASE WHEN pud.scorable THEN agg.pdp_count_3mi           END AS pdp_count_3mi,
    CASE WHEN pud.scorable THEN agg.pdp_count_5mi           END AS pdp_count_5mi,
    CASE WHEN pud.scorable THEN agg.dist_nearest_ft         END AS dist_nearest_ft,
    CASE WHEN pud.scorable THEN agg.dist_3rd_nearest_ft     END AS dist_3rd_nearest_ft,
    CASE WHEN pud.scorable THEN agg.support_lateral_ft_5mi  END AS support_lateral_ft_5mi,
    CASE WHEN pud.scorable THEN agg.n_offsets_5mi           END AS n_offsets_5mi,
    CASE WHEN pud.scorable THEN agg.offset_median_eur_ft    END AS offset_median_eur_ft,
    CASE WHEN pud.scorable THEN agg.offset_median_cum12m_oil_per_ft
                                                            END AS offset_median_cum12m_oil_per_ft,
    -- Novi PUD forecast per-ft vs the median of Novi's history-matched offsets.
    -- NULLIF guards both numerator (ll_ft) and denominator (offset median).
    CASE
        WHEN NOT pud.scorable THEN NULL
        ELSE (pud.oil_eur / NULLIF(pud.ll_ft, 0))
             / NULLIF(agg.offset_median_eur_ft, 0)
    END                                                     AS inflation_ratio,
    -- Depth context (see header): the guarded set's median depth + delta, then
    -- the UNGUARDED local plausibility measures from the ctx lateral.
    CASE WHEN pud.scorable THEN agg.offset_median_tvd       END AS offset_median_tvd,
    CASE WHEN pud.scorable THEN pud.tvd - agg.offset_median_tvd
                                                            END AS tvd_delta_ft,
    CASE WHEN pud.scorable THEN pud.tvd - ctx.bench_max_tvd_3mi
                                                            END AS tvd_excess_3mi_ft,
    CASE WHEN pud.scorable THEN pud.tvd - ctx.wca_median_tvd_3mi
                                                            END AS wca_delta_ft
FROM pud
LEFT JOIN LATERAL (
    SELECT
        count(*)                                                   AS pdp_count_5mi,
        count(*) FILTER (WHERE o.d <= 1609)                        AS pdp_count_1mi,   -- 1 mi
        count(*) FILTER (WHERE o.d <= 4827)                        AS pdp_count_3mi,   -- 3 mi
        min(o.d) * 3.28084                                         AS dist_nearest_ft,
        (array_agg(o.d ORDER BY o.d))[3] * 3.28084                 AS dist_3rd_nearest_ft,  -- NULL when <3
        sum(o.ll)                                                  AS support_lateral_ft_5mi,
        count(*) FILTER (WHERE o.eur_ft IS NOT NULL)               AS n_offsets_5mi,   -- the median's true n
        percentile_cont(0.5) WITHIN GROUP (ORDER BY o.eur_ft)      AS offset_median_eur_ft,
        percentile_cont(0.5) WITHIN GROUP (ORDER BY o.cum12_ft)    AS offset_median_cum12m_oil_per_ft,
        -- The depth the EUR median / inflation_ratio were computed against.
        percentile_cont(0.5) WITHIN GROUP (ORDER BY o.tvd)         AS offset_median_tvd
    FROM (
        SELECT
            ST_Distance(w.wellstick_geom::geography, pud.g)          AS d,
            w.lateral_length_ft                                      AS ll,
            w.tvd_ft                                                 AS tvd,
            -- EUR gaps (~500 qualifying PDPs) -> NULL eur_ft: still count as
            -- physical support (pdp_count_*) but drop out of the median
            -- (percentile_cont ignores NULL); n_offsets_5mi records the sample.
            w.eur_30yr_oil_bbl / NULLIF(w.lateral_length_ft, 0)      AS eur_ft,
            -- Mature-well ACTUALS cross-check only (Novi Cum12MOil = FIRST-12-mo
            -- oil, NOT trailing). The 6-12 mo wells admitted by the 6-mo gate
            -- carry NULL Cum12MOil and self-exclude from this median (option a):
            -- it stays a settled-well yardstick even as the gate reaches younger.
            w.cum_12m_oil_bbl  / NULLIF(w.lateral_length_ft, 0)      AS cum12_ft
        FROM curated.wells w
        JOIN curated.formation_blueox fb2        ON fb2.api10 = w.api10
        LEFT JOIN curated.formation_blueox_tvd t ON t.api10   = w.api10
        WHERE ST_DWithin(w.wellstick_geom::geography, pud.g, 8045)                 -- TUNABLE: 5 mi outer gate
          AND COALESCE(w.novi_slant_calculated, w.enverus_trajectory)
              ILIKE '%horizontal%'                                                 -- TUNABLE: horizontal (sql/40 semantics)
          AND COALESCE(t.corrected_code, fb2.formation_blueox) = pud.code          -- TUNABLE: same formation_blueox
          AND abs(w.tvd_ft - pud.tvd) <= 500                                       -- TUNABLE: TVD guard +/- 500 ft
          AND w.first_production_date <= current_date - interval '6 months'        -- TUNABLE: >= 6 mo since first prod
          AND w.lateral_length_ft > 0
    ) o
) agg ON TRUE
-- Depth-context lateral (see header): UNGUARDED local depth field within 3 mi —
-- deliberately no ±500 TVD guard and no 6-month gate, because its whole job is
-- to see the producers the guard hides. One pass serves both measures via
-- FILTER: same-bench max depth + WCA median depth.
LEFT JOIN LATERAL (
    SELECT
        max(c.tvd_ft)  FILTER (WHERE c.code = pud.code)             AS bench_max_tvd_3mi,
        percentile_cont(0.5) WITHIN GROUP (ORDER BY c.tvd_ft)
            FILTER (WHERE c.code IN ('WCA_1', 'WCA_2'))             AS wca_median_tvd_3mi
    FROM (
        SELECT
            w.tvd_ft,
            COALESCE(t.corrected_code, fb2.formation_blueox)         AS code
        FROM curated.wells w
        JOIN curated.formation_blueox fb2        ON fb2.api10 = w.api10
        LEFT JOIN curated.formation_blueox_tvd t ON t.api10   = w.api10
        WHERE ST_DWithin(w.wellstick_geom::geography, pud.g, 4827)                 -- 3 mi
          AND COALESCE(w.novi_slant_calculated, w.enverus_trajectory)
              ILIKE '%horizontal%'                                                 -- sql/40 semantics
          AND COALESCE(t.corrected_code, fb2.formation_blueox)
              IN (pud.code, 'WCA_1', 'WCA_2')
          AND w.first_production_date IS NOT NULL                                  -- ever produced (no 6-mo gate)
          AND w.tvd_ft IS NOT NULL
    ) c
) ctx ON TRUE
WITH DATA;

-- Only index needed: attribute table, no geometry, ~204k rows. UNIQUE on stick_id
-- is REQUIRED for REFRESH ... CONCURRENTLY (the on-demand path in the header).
CREATE UNIQUE INDEX idx_intel_pdp_support_stick
    ON curated.intel_pdp_support (stick_id);

COMMENT ON MATERIALIZED VIEW curated.intel_pdp_support IS
'Per-PUD/RES offset-PDP support scores for novi_intel sticks (curated.intel_locations), keyed on stick_id. A VERIFIABILITY screen (not quality): tiered qualifying-PDP counts (1/3/5 mi), nearest/3rd-nearest distance (the halo width), support lateral footage, offset EUR/ft median, and inflation_ratio (Novi PUD forecast /ft vs the median of history-matched in-bench offsets). Qualifying offset = horizontal (sql/40 semantics) + same TVD-corrected formation_blueox + TVD +/-500 ft + >=6 mo produced + within 5 mi (PDP universe never county-scoped). Depth-context columns (2026-09, WCB_2 deep-TVD audit): offset_median_tvd / tvd_delta_ft audit the depth of the ratio''s own comparison set; tvd_excess_3mi_ft (stick TVD minus UNGUARDED same-bench producer max within 3 mi; positive = deeper than anything ever produced in-bench locally, >200 ft = anomaly line) and wca_delta_ft (stick TVD minus unguarded WCA producer median within 3 mi; WCB_2 land-screen band [400,700] ft) catch anomalously deep Novi landings the +/-500 guard cannot. pdp_count_* = 0 means scored-and-unsupported; NULL scores mean not-scorable (unmapped bench / missing TVD or geometry); NULL tvd_excess_3mi_ft on a scored stick = no same-bench producer within 3 mi (frontier). Quarterly refresh only (NOT nightly); staleness under-states support, never over-states. sql/30.';
