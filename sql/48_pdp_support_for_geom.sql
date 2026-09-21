-- =============================================================================
-- 48 — curated.pdp_support_for_geom(geom, bench, tvd)  (sql/30 offset-PDP
--      support scores for an ARBITRARY stick — deal-intake Gate 3 for
--      narvi-generated locations)
--
-- PURPOSE: curated.intel_pdp_support (sql/30) scores only Novi PUD/RES sticks.
-- Gate 3 of the deal-intake skill needs the SAME score family for sticks narvi
-- generates (no stick_id, not in the matview). This function is the sql/30
-- predicate set wrapped around a caller-supplied geometry, so a generated
-- stick and a Novi stick at the same place, bench and TVD score identically.
--
-- PREDICATES — must track sql/30 line for line (the sql/30 header is the
-- authority; change both or neither):
--   guarded offset set (counts, distances, EUR medians, offset_median_tvd):
--     within 5 mi (8045 m) geography, horizontal (sql/40 ILIKE '%horizontal%'),
--     same TVD-corrected formation_blueox, |tvd - subject_tvd| <= 500 ft,
--     first_production_date <= current_date - 6 months, lateral_length_ft > 0.
--   depth-context set (tvd_excess_3mi_ft, wca_delta_ft): within 3 mi (4827 m),
--     horizontal, bench IN (subject, WCA_1, WCA_2), ever produced, tvd NOT NULL.
--
-- SEMANTICS (identical to sql/30):
--   * any of geom / bench / tvd NULL -> every score NULL ("not scorable"),
--     never count 0. 0 = scored and genuinely unsupported.
--   * dist_3rd_nearest_ft NULL with count > 0 = fewer than 3 offsets.
--   * current_date makes results call-date dependent (as sql/30's content is
--     refresh-date dependent). Compare to intel_pdp_support same-day only.
--   * inflation_ratio is NOT returned: it needs a Novi forecast, which a
--     generated stick does not have. offset_median_eur_ft is returned so a
--     caller holding its own EUR/ft can form the ratio.
--
-- DIFFERENCE vs the matview (deliberate): this is LIVE — it sees producers
-- that came online since the last quarterly intel_pdp_support rebuild. A
-- generated stick therefore can score slightly HIGHER support than a Novi
-- stick next to it until the next quarterly refresh.
--
-- PERFORMANCE: LANGUAGE sql STABLE, single SELECT -> the planner inlines the
-- body at the call site. ST_DWithin text matches sql/26's
-- idx_curated_wells_wellstick_geog (wellstick_geom::geography); EXPLAIN on a
-- call with a constant geometry must show that index, never a Seq Scan on
-- curated.wells (scripts/apply_pdp_support_for_geom.py asserts it).
-- PostGIS references schema-qualified (extensions.*) so the function stays
-- safe to call from a matview body under PG17's restricted search_path.
--
-- DEPENDS ON: curated.wells (sql/04), curated.formation_blueox (sql/16),
--   curated.formation_blueox_tvd (sql/23), sql/26 expression index. Plain
--   function: survives refreshes; after a sql/04 DROP CASCADE it stays
--   defined and errors until curated.wells is recreated.
--
-- Idempotent: CREATE OR REPLACE.
-- =============================================================================

CREATE OR REPLACE FUNCTION curated.pdp_support_for_geom(
    subject_geom  geometry,           -- planned stick/legs, SRID 4326
    subject_bench text,               -- formation_blueox code, e.g. 'WCA_2'
    subject_tvd   double precision    -- planned landing TVD, ft
) RETURNS TABLE (
    pdp_count_1mi                   bigint,
    pdp_count_3mi                   bigint,
    pdp_count_5mi                   bigint,
    dist_nearest_ft                 double precision,
    dist_3rd_nearest_ft             double precision,
    support_lateral_ft_5mi          double precision,
    n_offsets_5mi                   bigint,
    offset_median_eur_ft            double precision,
    offset_median_cum12m_oil_per_ft double precision,
    offset_median_tvd               double precision,
    tvd_delta_ft                    double precision,
    tvd_excess_3mi_ft               double precision,
    wca_delta_ft                    double precision
) AS $$
    SELECT
        CASE WHEN sub.scorable THEN agg.pdp_count_1mi          END,
        CASE WHEN sub.scorable THEN agg.pdp_count_3mi          END,
        CASE WHEN sub.scorable THEN agg.pdp_count_5mi          END,
        CASE WHEN sub.scorable THEN agg.dist_nearest_ft        END,
        CASE WHEN sub.scorable THEN agg.dist_3rd_nearest_ft    END,
        CASE WHEN sub.scorable THEN agg.support_lateral_ft_5mi END,
        CASE WHEN sub.scorable THEN agg.n_offsets_5mi          END,
        CASE WHEN sub.scorable THEN agg.offset_median_eur_ft   END,
        CASE WHEN sub.scorable THEN agg.offset_median_cum12m_oil_per_ft END,
        CASE WHEN sub.scorable THEN agg.offset_median_tvd      END,
        CASE WHEN sub.scorable THEN sub.tvd - agg.offset_median_tvd   END,
        CASE WHEN sub.scorable THEN sub.tvd - ctx.bench_max_tvd_3mi   END,
        CASE WHEN sub.scorable THEN sub.tvd - ctx.wca_median_tvd_3mi  END
    FROM (
        SELECT
            subject_geom::extensions.geography            AS g,
            subject_bench                                 AS code,
            subject_tvd                                   AS tvd,
            (subject_geom IS NOT NULL
             AND subject_bench IS NOT NULL
             AND subject_tvd IS NOT NULL)                 AS scorable
    ) sub
    LEFT JOIN LATERAL (
        SELECT
            count(*)                                                   AS pdp_count_5mi,
            count(*) FILTER (WHERE o.d <= 1609)                        AS pdp_count_1mi,
            count(*) FILTER (WHERE o.d <= 4827)                        AS pdp_count_3mi,
            min(o.d) * 3.28084                                         AS dist_nearest_ft,
            (array_agg(o.d ORDER BY o.d))[3] * 3.28084                 AS dist_3rd_nearest_ft,
            sum(o.ll)                                                  AS support_lateral_ft_5mi,
            count(*) FILTER (WHERE o.eur_ft IS NOT NULL)               AS n_offsets_5mi,
            percentile_cont(0.5) WITHIN GROUP (ORDER BY o.eur_ft)      AS offset_median_eur_ft,
            percentile_cont(0.5) WITHIN GROUP (ORDER BY o.cum12_ft)    AS offset_median_cum12m_oil_per_ft,
            percentile_cont(0.5) WITHIN GROUP (ORDER BY o.tvd)         AS offset_median_tvd
        FROM (
            SELECT
                extensions.ST_Distance(w.wellstick_geom::extensions.geography, sub.g) AS d,
                w.lateral_length_ft                                      AS ll,
                w.tvd_ft                                                 AS tvd,
                w.eur_30yr_oil_bbl / NULLIF(w.lateral_length_ft, 0)      AS eur_ft,
                w.cum_12m_oil_bbl  / NULLIF(w.lateral_length_ft, 0)      AS cum12_ft
            FROM curated.wells w
            JOIN curated.formation_blueox fb2        ON fb2.api10 = w.api10
            LEFT JOIN curated.formation_blueox_tvd t ON t.api10   = w.api10
            WHERE extensions.ST_DWithin(w.wellstick_geom::extensions.geography, sub.g, 8045)
              AND COALESCE(w.novi_slant_calculated, w.enverus_trajectory) ILIKE '%horizontal%'
              AND COALESCE(t.corrected_code, fb2.formation_blueox) = sub.code
              AND abs(w.tvd_ft - sub.tvd) <= 500
              AND w.first_production_date <= current_date - interval '6 months'
              AND w.lateral_length_ft > 0
        ) o
    ) agg ON TRUE
    LEFT JOIN LATERAL (
        SELECT
            max(c.tvd_ft)  FILTER (WHERE c.code = sub.code)             AS bench_max_tvd_3mi,
            percentile_cont(0.5) WITHIN GROUP (ORDER BY c.tvd_ft)
                FILTER (WHERE c.code IN ('WCA_1', 'WCA_2'))             AS wca_median_tvd_3mi
        FROM (
            SELECT
                w.tvd_ft,
                COALESCE(t.corrected_code, fb2.formation_blueox)         AS code
            FROM curated.wells w
            JOIN curated.formation_blueox fb2        ON fb2.api10 = w.api10
            LEFT JOIN curated.formation_blueox_tvd t ON t.api10   = w.api10
            WHERE extensions.ST_DWithin(w.wellstick_geom::extensions.geography, sub.g, 4827)
              AND COALESCE(w.novi_slant_calculated, w.enverus_trajectory) ILIKE '%horizontal%'
              AND COALESCE(t.corrected_code, fb2.formation_blueox)
                  IN (sub.code, 'WCA_1', 'WCA_2')
              AND w.first_production_date IS NOT NULL
              AND w.tvd_ft IS NOT NULL
        ) c
    ) ctx ON TRUE
$$ LANGUAGE sql STABLE;

COMMENT ON FUNCTION curated.pdp_support_for_geom(geometry, text, double precision) IS
'sql/30 offset-PDP support score family for an arbitrary stick geometry (deal-intake Gate 3 for narvi-generated locations): pdp_count_1/3/5mi, dist_nearest/3rd_nearest_ft, support_lateral_ft_5mi, n_offsets_5mi, offset_median_eur_ft, offset_median_cum12m_oil_per_ft, offset_median_tvd, tvd_delta_ft, tvd_excess_3mi_ft, wca_delta_ft. Same predicates as curated.intel_pdp_support (horizontal, same TVD-corrected formation_blueox, TVD +/-500 ft, >=6 mo produced, ll>0, 5-mi outer gate; unguarded 3-mi depth context). Any NULL input -> all scores NULL (not scorable); count 0 = scored and unsupported. LIVE against curated.wells (the matview is quarterly), so it can read slightly higher than intel_pdp_support between vintages. No inflation_ratio (needs a Novi forecast). sql/48.';

-- Verification (EXPLAIN must show idx_curated_wells_wellstick_geog):
--
--   EXPLAIN (ANALYZE, BUFFERS)
--   SELECT * FROM curated.pdp_support_for_geom(
--       (SELECT wellstick_geom FROM curated.intel_locations
--         WHERE category = 'PUD' AND wellstick_geom IS NOT NULL LIMIT 1),
--       'WCA_1', 9500);
