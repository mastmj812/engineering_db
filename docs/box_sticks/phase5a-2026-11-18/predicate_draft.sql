-- =============================================================================
-- DRAFT. BOX sticks phase 5a: the nightly reconciliation predicate against the RECORD sets of box.location_stick.
-- A single read-only SELECT: one row per record stick. NOT on the apply path; nothing here writes.
-- scripts/box_sticks_phase5a.py runs it inside SET TRANSACTION READ ONLY and compares it with the Python reference.
--
-- sql/68's rule, re-targeted: the share of a stick LEG inside a well's +-150 ft (46 m) corridor; >= 0.5 = match,
-- 0.2 to 0.5 = conflict; same code within 500 ft TVD, or within 150 ft whatever the tag. New against sql/68:
--   * legs (a U-turn stick has two), judged one by one;
--   * wells not yet producing (Spud / DUC / Completed or a spud date) and approved permits, as their own classes;
--   * a well with no depth evidence matches on formation family (match_basis = 'planned');
--   * the survey path for a real U-turn well (its wellstick is a short line across the legs);
--   * crowded: the record set's own envelope (box.location_set.cfg -> generator), corridor form.
-- Pair search = ST_DWithin on geography, served by box_location_stick_geog_gix (sql/73; the sql/26 rule).
-- =============================================================================
WITH rec AS (
    SELECT set_id, basin,
           (cfg #>> '{generator,same_dv_ft}')::float8  AS same_dv_ft,
           (cfg #>> '{generator,same_dh_ft}')::float8  AS same_dh_ft,
           (cfg #>> '{generator,min_overlap}')::float8 AS min_ov,
           cfg #>  '{generator,stacked}'               AS stacked
    FROM box.location_set
    WHERE is_record
),
w AS MATERIALIZED (
    SELECT e.api10, e.basin_blueox AS basin, e.formation_blueox AS code,
           CASE WHEN e.formation_blueox LIKE 'WCA%' OR e.formation_blueox = 'WCXY' THEN 'WCA'
                ELSE split_part(e.formation_blueox, '_', 1) END AS fam,
           CASE WHEN e.first_production_date IS NOT NULL THEN 'producing'
                WHEN e.well_status = 'Permit Cancelled' THEN NULL
                WHEN e.well_status IN ('Spud', 'DUC', 'Completed') OR e.spud_date IS NOT NULL THEN 'drilled'
                WHEN e.well_status = 'Permit Approved' THEN 'permit' END AS cls,
           -- depth evidence (box.tag_scoreboard.evidence_depth): never a planned survey; the survey lateral median,
           -- else tvd_ft unless it is a round 100; at least 4,000 ft.
           CASE WHEN COALESCE(e.directional_survey_is_planned, FALSE) THEN NULL
                WHEN sv.lat_tvd_p50_ft IS NOT NULL THEN CASE WHEN sv.lat_tvd_p50_ft >= 4000 THEN sv.lat_tvd_p50_ft END
                WHEN e.tvd_ft >= 4000 AND mod(e.tvd_ft, 100) <> 0 THEN e.tvd_ft::float8 END AS depth_ft,
           CASE WHEN COALESCE(sv.is_uturn, FALSE) AND sv.lateral_geom IS NOT NULL THEN sv.lateral_geom ELSE e.wellstick_geom END AS line
    FROM curated.wells_enriched e
    LEFT JOIN curated.well_lateral_survey sv ON sv.api10 = e.api10
    WHERE e.basin_blueox IN ('delaware', 'midland') AND e.is_horizontal
      AND extensions.ST_GeometryType(e.wellstick_geom) = 'ST_LineString'
),
pair AS MATERIALIZED (
    -- every (well, record stick) within the widest sideways limit; the leg split comes after the index search
    SELECT s.set_id, s.location_id, s.formation_blueox AS bench, s.target_tvd_ft, r.same_dv_ft, r.same_dh_ft, r.min_ov, r.stacked,
           CASE WHEN s.formation_blueox LIKE 'WCA%' OR s.formation_blueox = 'WCXY' THEN 'WCA'
                ELSE split_part(s.formation_blueox, '_', 1) END AS sfam,
           w.api10, w.cls, w.code, w.fam, w.depth_ft, w.line, d.path[1] AS leg_no, d.geom AS leg
    FROM w
    JOIN rec r ON r.basin = w.basin
    JOIN box.location_stick s
      ON s.set_id = r.set_id
     AND extensions.ST_DWithin(s.legs_geom::extensions.geography, w.line::extensions.geography, r.same_dh_ft * 0.3048)
    CROSS JOIN LATERAL extensions.ST_Dump(s.legs_geom) d
    WHERE w.cls IS NOT NULL
),
scored AS (
    SELECT p.*,
           p.depth_ft - p.target_tvd_ft AS dz,
           extensions.ST_Length(extensions.ST_Intersection(p.leg, extensions.ST_Buffer(p.line::extensions.geography, 46)::extensions.geometry)::extensions.geography)
             / NULLIF(extensions.ST_Length(p.leg::extensions.geography), 0) AS ov,
           extensions.ST_Length(extensions.ST_Intersection(p.leg, extensions.ST_Buffer(p.line::extensions.geography, p.same_dh_ft * 0.3048)::extensions.geometry)::extensions.geography)
             / NULLIF(extensions.ST_Length(p.leg::extensions.geography), 0) AS ov_same
    FROM pair p
),
judged AS (
    SELECT s.*,
           CASE WHEN s.depth_ft IS NULL THEN s.fam = s.sfam
                ELSE (s.code = s.bench AND abs(s.dz) <= 500) OR abs(s.dz) <= 150 END AS same_bench,
           s.cls IN ('producing', 'drilled') AND (
               CASE WHEN s.depth_ft IS NULL THEN s.fam = s.sfam AND s.ov_same >= s.min_ov
                    WHEN abs(s.dz) <= s.same_dv_ft THEN s.ov_same >= s.min_ov
                    ELSE EXISTS (
                        SELECT 1 FROM jsonb_array_elements(s.stacked) k
                        WHERE s.dz > (k ->> 0)::float8 AND s.dz <= (k ->> 1)::float8
                          AND extensions.ST_Length(extensions.ST_Intersection(s.leg, extensions.ST_Buffer(s.line::extensions.geography, (k ->> 2)::float8 * 0.3048)::extensions.geometry)::extensions.geography)
                                / NULLIF(extensions.ST_Length(s.leg::extensions.geography), 0) >= s.min_ov)
               END) AS in_envelope
    FROM scored s
),
leg AS (
    SELECT set_id, location_id, leg_no,
           max(ov) FILTER (WHERE same_bench AND cls <> 'permit')                                  AS best_ov,
           count(*) FILTER (WHERE same_bench AND cls <> 'permit' AND ov >= 0.5)                   AS n_strong,
           (array_agg(api10 ORDER BY ov DESC, api10) FILTER (WHERE same_bench AND cls <> 'permit'))[1]  AS best_api10,
           (array_agg(cls   ORDER BY ov DESC, api10) FILTER (WHERE same_bench AND cls <> 'permit'))[1]  AS best_cls,
           (array_agg(depth_ft IS NULL ORDER BY ov DESC, api10) FILTER (WHERE same_bench AND cls <> 'permit'))[1] AS best_planned,
           (array_agg(api10 ORDER BY ov DESC, api10) FILTER (WHERE same_bench AND cls = 'permit' AND ov >= 0.5))[1] AS permit_api10,
           (array_agg(api10 ORDER BY ov_same DESC, api10) FILTER (WHERE in_envelope))[1]          AS crowd_api10
    FROM judged
    GROUP BY 1, 2, 3
),
leg_status AS (
    SELECT l.*,
           CASE WHEN n_strong >= 2 THEN 'conflict'
                WHEN best_ov >= 0.5 THEN 'matched'
                WHEN best_ov >= 0.2 THEN 'conflict'
                ELSE 'open' END AS leg_state
    FROM leg l
),
stick AS (
    SELECT set_id, location_id,
           bool_or(leg_state = 'conflict')                                   AS any_conflict,
           count(*) FILTER (WHERE leg_state = 'matched')                     AS legs_matched,
           bool_and(best_cls = 'producing') FILTER (WHERE leg_state = 'matched') AS all_producing,
           bool_or(best_planned) FILTER (WHERE leg_state = 'matched')        AS any_planned,
           (array_agg(best_api10 ORDER BY best_ov DESC NULLS LAST, leg_no) FILTER (WHERE leg_state <> 'open'))[1] AS matched_api10,
           max(best_ov)                                                      AS best_ov,
           (array_agg(permit_api10 ORDER BY leg_no) FILTER (WHERE permit_api10 IS NOT NULL))[1] AS permit_api10,
           (array_agg(crowd_api10 ORDER BY leg_no) FILTER (WHERE crowd_api10 IS NOT NULL))[1]   AS crowd_api10
    FROM leg_status
    GROUP BY 1, 2
)
SELECT s.set_id, s.location_id, s.basin, s.pad_id, s.formation_blueox, s.n_legs,
       CASE WHEN k.any_conflict THEN 'conflict'
            WHEN k.legs_matched > 0 AND k.all_producing THEN 'producing'
            WHEN k.legs_matched > 0 THEN 'drilled'
            WHEN k.permit_api10 IS NOT NULL THEN 'permitted'
            ELSE 'open' END                                    AS status,
       COALESCE(k.legs_matched, 0)                             AS legs_matched,
       k.matched_api10,
       round(k.best_ov::numeric, 3)                            AS match_overlap,
       CASE WHEN k.legs_matched > 0 OR k.any_conflict THEN CASE WHEN k.any_planned THEN 'planned' ELSE 'depth' END END AS match_basis,
       k.permit_api10,
       k.crowd_api10 IS NOT NULL AND NOT COALESCE(k.any_conflict, FALSE) AND COALESCE(k.legs_matched, 0) = 0 AS crowded,
       k.crowd_api10
FROM box.location_stick s
JOIN rec r ON r.set_id = s.set_id
LEFT JOIN stick k ON k.set_id = s.set_id AND k.location_id = s.location_id
ORDER BY s.set_id, s.location_id
