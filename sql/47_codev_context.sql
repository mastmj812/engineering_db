-- =============================================================================
-- 47 — curated.codev_context  (per-well adjacent-bench development context
--      at first production — deal-intake v2 co-development-aware TC selection)
--
-- PURPOSE: for every producing horizontal (api10), describe WHICH benches were
-- developed alongside it and WHEN relative to its own first production, so the
-- deal-intake runner (dealintake/select_wells.py) can tier type-curve
-- candidates by how representative they are of a planned co-developed stack:
--   codev              adjacent planned bench came online within the window
--   stack_standalone   no other-bench neighbor at all
--   topfill_underfill  adjacent bench was a PARENT (online earlier) or a later
--                      infill CHILD
-- The TIERING (which benches are "adjacent", order, when the order flips) is
-- deal-specific and lives in Python + config/thresholds.yaml. This matview
-- only records neutral facts per (well x neighbor bench).
--
-- NEIGHBOR RULE (co-extent, never bare min-distance — workspace rule 9):
--   * candidate gate  ST_DWithin(stick, stick, 402.336 m = 1,320 ft), geography.
--                     Text matches sql/26's idx_curated_wells_wellstick_geog;
--                     EXPLAIN must show that index, never a Seq Scan.
--   * co-extent       the neighbor's LATERAL, projected onto the subject's
--                     lateral, must cover >= 30% of the subject lateral
--                     (ST_LineLocatePoint span; same 30% threshold as narvi's
--                     in-unit membership). This drops toe-to-heel laterals in
--                     the next section that merely clip the 1,320-ft gate.
--   * lateral line    LP -> stick end point (BHL) when Novi ships a landing
--                     point distinct from the end point; otherwise the whole
--                     stick (SHL -> ... -> BHL). ~77% of producing horizontals
--                     carry an LP (2026-09). SHL-inclusive fallback slightly
--                     inflates the subject's length and so the denominator of
--                     the overlap fraction — conservative (fewer neighbors).
--   * neighbor        any producing horizontal (sql/40 is_horizontal
--                     semantics), ANY bench, first_production_date NOT NULL,
--                     api10 <> subject.
--   Planar fractions on SRID 4326 are fine for co-extent: lateral lengths are
--   <= ~3 mi, where degree distortion along a near-straight line is <<1%.
--
-- BENCH: TVD-corrected formation_blueox (COALESCE(t.corrected_code,
--   fb.formation_blueox)), NULL -> '(unmapped)' — the same key server- and
--   client-side (workspace rule 7).
--
-- TIMING (per neighbor): dfp_days = neighbor.first_production_date -
--   subject.first_production_date.
--     |dfp_days| <= 180  -> codev   (window BAKED here; config
--                                    codev.window_days must equal it — the
--                                    runner asserts)
--     dfp_days  < -180   -> parent  (neighbor online earlier)
--     dfp_days  >  180   -> child   (neighbor online later)
--   A bench can carry more than one relation (e.g. a codev pad-mate AND an
--   older parent). Arrays below list each bench once per relation.
--   Child counts are RIGHT-CENSORED: a well online < 180 d before the last
--   load cannot have a child yet. Young wells therefore read as codev /
--   standalone more often than they will once infill arrives; the runner
--   reports months-on-production next to the tier.
--
-- COLUMNS:
--   api10, bench, first_production_date, tvd_ft
--   scorable          FALSE when the subject has no stick geometry (context
--                     columns are then NULL — "no basis", not "no neighbors")
--   n_neighbors       neighbors passing the rule (all benches)
--   bench_context     jsonb {bench: {n, n_codev, n_parent, n_child,
--                     min_abs_dfp_days, median_dist_ft, median_dtvd_ft}},
--                     dtvd = neighbor.tvd - subject.tvd (negative = shallower)
--   codev_benches     text[] benches with >= 1 codev neighbor (incl. own bench)
--   parent_benches    text[] benches with >= 1 parent neighbor
--   child_benches     text[] benches with >= 1 child neighbor
--   n_codev_same_bench, n_codev_other_bench, n_parent_other_bench,
--   n_child_other_bench   helper counts ("other" = bench <> own bench)
--
-- Every array is empty (not NULL) on a scorable well with no neighbors: that
-- well IS stack-standalone, which is a result, not a gap.
--
-- current_date is not used: content depends only on the base tables, so a
-- REFRESH is deterministic given the nightly load.
--
-- REFRESH CADENCE: NIGHTLY (registered in etl/db.py:_CURATED_MATVIEWS after
--   curated.formation_blueox_tvd, its last input). A new well changes its
--   neighbors' child counts, so it cannot go quarterly. REFRESH CONCURRENTLY
--   via the UNIQUE index on api10.
--
-- DEPENDS ON: curated.wells (sql/04), curated.formation_blueox (sql/16),
--   curated.formation_blueox_tvd (sql/23), sql/26 expression GiST index.
--   Base tables deliberately, not curated.wells_enriched (view inlining).
--   CASCADE VICTIM of two rebuilds:
--     * quarterly: sql/20 -> sql/23 (formation_blueox_tvd) drops it;
--       scripts/apply_reconciled_inventory.py step 1d recreates it. Listed in
--       etl/db.py:_OPTIONAL_MATVIEWS so an interrupted quarterly degrades the
--       nightly to a warning, not a red run.
--     * sql/04 wells rebuild: re-run this file after sql/26
--       (scripts/apply_wellstick_fix.py docstring note).
--
-- PostGIS references schema-qualified (extensions.*): PG17 runs matview
--   CREATE/REFRESH under a restricted search_path.
--
-- RUN: python -m scripts.apply_codev_context  (exec + validate). Idempotent:
--   DROP ... IF EXISTS CASCADE then CREATE ... WITH DATA.
-- =============================================================================

DROP MATERIALIZED VIEW IF EXISTS curated.codev_context CASCADE;

CREATE MATERIALIZED VIEW curated.codev_context AS
WITH subj AS (
    SELECT
        w.api10,
        COALESCE(t.corrected_code, fb.formation_blueox, '(unmapped)')   AS bench,
        w.first_production_date                                         AS fp,
        w.tvd_ft,
        w.wellstick_geom                                                AS g,
        CASE
            WHEN w.landing_point_lat IS NOT NULL
             AND w.landing_point_lon IS NOT NULL
             AND w.wellstick_geom IS NOT NULL
             AND NOT extensions.ST_Equals(
                     extensions.ST_SetSRID(extensions.ST_Point(w.landing_point_lon, w.landing_point_lat), 4326),
                     extensions.ST_EndPoint(w.wellstick_geom))
            THEN extensions.ST_MakeLine(
                     extensions.ST_SetSRID(extensions.ST_Point(w.landing_point_lon, w.landing_point_lat), 4326),
                     extensions.ST_EndPoint(w.wellstick_geom))
            ELSE w.wellstick_geom
        END                                                             AS lat
    FROM curated.wells w
    LEFT JOIN curated.formation_blueox fb      ON fb.api10 = w.api10
    LEFT JOIN curated.formation_blueox_tvd t   ON t.api10  = w.api10
    WHERE COALESCE(w.novi_slant_calculated, w.enverus_trajectory) ILIKE '%horizontal%'
      AND w.first_production_date IS NOT NULL
)
-- One LATERAL per subject: neighbors -> per-bench group -> per-well roll-up,
-- all evaluated for THIS subject. Deliberately no CTE-to-CTE join: with
-- separate pairs/agg CTEs the planner misestimated subj at 1 row and
-- re-ran the aggregate once per output row (quadratic; ~3.9 h extrapolated
-- on the 1% dry run vs minutes for this shape).
SELECT
    s.api10,
    s.bench,
    s.fp                                                                     AS first_production_date,
    s.tvd_ft,
    (s.g IS NOT NULL)                                                        AS scorable,
    CASE WHEN s.g IS NOT NULL THEN COALESCE(a.n_neighbors, 0) END            AS n_neighbors,
    CASE WHEN s.g IS NOT NULL THEN COALESCE(a.bench_context, '{}'::jsonb) END AS bench_context,
    CASE WHEN s.g IS NOT NULL THEN COALESCE(a.codev_benches,  '{}'::text[]) END AS codev_benches,
    CASE WHEN s.g IS NOT NULL THEN COALESCE(a.parent_benches, '{}'::text[]) END AS parent_benches,
    CASE WHEN s.g IS NOT NULL THEN COALESCE(a.child_benches,  '{}'::text[]) END AS child_benches,
    CASE WHEN s.g IS NOT NULL THEN COALESCE(a.n_codev_same_bench,   0) END  AS n_codev_same_bench,
    CASE WHEN s.g IS NOT NULL THEN COALESCE(a.n_codev_other_bench,  0) END  AS n_codev_other_bench,
    CASE WHEN s.g IS NOT NULL THEN COALESCE(a.n_parent_other_bench, 0) END  AS n_parent_other_bench,
    CASE WHEN s.g IS NOT NULL THEN COALESCE(a.n_child_other_bench,  0) END  AS n_child_other_bench
FROM subj s
LEFT JOIN LATERAL (
    SELECT
        sum(b.n)::int                                                        AS n_neighbors,
        jsonb_object_agg(b.nbr_bench, jsonb_build_object(
            'n',                b.n,
            'n_codev',          b.n_codev,
            'n_parent',         b.n_parent,
            'n_child',          b.n_child,
            'min_abs_dfp_days', b.min_abs_dfp_days,
            'median_dist_ft',   round(b.median_dist_ft::numeric, 0),
            'median_dtvd_ft',   round(b.median_dtvd_ft::numeric, 0)))       AS bench_context,
        array_agg(b.nbr_bench ORDER BY b.nbr_bench) FILTER (WHERE b.n_codev  > 0) AS codev_benches,
        array_agg(b.nbr_bench ORDER BY b.nbr_bench) FILTER (WHERE b.n_parent > 0) AS parent_benches,
        array_agg(b.nbr_bench ORDER BY b.nbr_bench) FILTER (WHERE b.n_child  > 0) AS child_benches,
        sum(b.n_codev)  FILTER (WHERE b.nbr_bench =  s.bench)::int           AS n_codev_same_bench,
        sum(b.n_codev)  FILTER (WHERE b.nbr_bench <> s.bench)::int           AS n_codev_other_bench,
        sum(b.n_parent) FILTER (WHERE b.nbr_bench <> s.bench)::int           AS n_parent_other_bench,
        sum(b.n_child)  FILTER (WHERE b.nbr_bench <> s.bench)::int           AS n_child_other_bench
    FROM (
        SELECT
            nb.bench                                                 AS nbr_bench,
            count(*)                                                 AS n,
            count(*) FILTER (WHERE abs(nb.dfp_days) <= 180)          AS n_codev,    -- BAKED window
            count(*) FILTER (WHERE nb.dfp_days < -180)               AS n_parent,
            count(*) FILTER (WHERE nb.dfp_days >  180)               AS n_child,
            min(abs(nb.dfp_days))                                    AS min_abs_dfp_days,
            percentile_cont(0.5) WITHIN GROUP (ORDER BY nb.dist_ft)  AS median_dist_ft,
            percentile_cont(0.5) WITHIN GROUP (ORDER BY nb.dtvd_ft)  AS median_dtvd_ft
        FROM (
            SELECT
                COALESCE(t2.corrected_code, fb2.formation_blueox, '(unmapped)')  AS bench,
                (w2.first_production_date - s.fp)                                AS dfp_days,
                extensions.ST_Distance(w2.wellstick_geom::extensions.geography,
                                       s.g::extensions.geography) * 3.28084      AS dist_ft,
                w2.tvd_ft - s.tvd_ft                                             AS dtvd_ft,
                CASE
                    WHEN w2.landing_point_lat IS NOT NULL
                     AND w2.landing_point_lon IS NOT NULL
                     AND NOT extensions.ST_Equals(
                             extensions.ST_SetSRID(extensions.ST_Point(w2.landing_point_lon, w2.landing_point_lat), 4326),
                             extensions.ST_EndPoint(w2.wellstick_geom))
                    THEN extensions.ST_MakeLine(
                             extensions.ST_SetSRID(extensions.ST_Point(w2.landing_point_lon, w2.landing_point_lat), 4326),
                             extensions.ST_EndPoint(w2.wellstick_geom))
                    ELSE w2.wellstick_geom
                END                                                              AS nlat
            FROM curated.wells w2
            LEFT JOIN curated.formation_blueox fb2     ON fb2.api10 = w2.api10
            LEFT JOIN curated.formation_blueox_tvd t2  ON t2.api10  = w2.api10
            WHERE extensions.ST_DWithin(w2.wellstick_geom::extensions.geography,
                                        s.g::extensions.geography, 402.336)       -- BAKED 1,320 ft gate
              AND w2.api10 <> s.api10
              AND COALESCE(w2.novi_slant_calculated, w2.enverus_trajectory) ILIKE '%horizontal%'
              AND w2.first_production_date IS NOT NULL
        ) nb
        -- co-extent: neighbor lateral projected onto the subject lateral covers >= 30% (BAKED)
        WHERE abs(extensions.ST_LineLocatePoint(s.lat, extensions.ST_StartPoint(nb.nlat))
                - extensions.ST_LineLocatePoint(s.lat, extensions.ST_EndPoint(nb.nlat))) >= 0.30
        GROUP BY nb.bench
    ) b
) a ON s.g IS NOT NULL
WITH DATA;

-- UNIQUE on api10: REQUIRED for the nightly REFRESH ... CONCURRENTLY.
CREATE UNIQUE INDEX idx_codev_context_api10
    ON curated.codev_context (api10);
-- Array containment lookups from the runner (codev_benches @> ARRAY[...]).
CREATE INDEX idx_codev_context_codev_benches
    ON curated.codev_context USING GIN (codev_benches);

COMMENT ON MATERIALIZED VIEW curated.codev_context IS
'Per producing horizontal (api10): adjacent-bench development context at first production, for deal-intake v2 co-development-aware type-curve selection. Neighbor = any producing horizontal (any TVD-corrected formation_blueox bench, NULL -> ''(unmapped)'') whose stick is within 1,320 ft (geography) AND whose lateral covers >= 30% of the subject lateral when projected onto it (co-extent, not min-distance). Per neighbor bench (bench_context jsonb): counts of codev (|dfp| <= 180 d), parent (neighbor online > 180 d earlier) and child (> 180 d later) neighbors, min |dfp| days, median stick distance ft, median TVD delta ft (neighbor minus subject). Arrays codev_/parent_/child_benches list benches per relation; helper counts split same vs other bench. Constants (1,320 ft, 180 d, 30%) are baked; the runner asserts its config matches. Empty arrays on a scorable well = genuinely no neighbors (stack standalone); scorable=FALSE (no stick geometry) -> NULL context. Tiering into codev / stack_standalone / topfill_underfill is deal-specific and done by dealintake, not here. Nightly refresh. sql/47.';
