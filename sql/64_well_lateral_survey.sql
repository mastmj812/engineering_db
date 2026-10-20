-- =============================================================================
-- 64 — curated.well_lateral_survey  (one row per api10: the lateral's TVD path
--      from Novi DirectionalSurveys — heel / mid / toe TVD, lateral TVD spread,
--      KB elevation, and the station path as a 3-D line)
--
-- PURPOSE: per-station landing evidence. wells_enriched.tvd_ft is ONE number
-- and sits a median ~32 ft DEEPER than the lateral's median survey TVD in the
-- Delaware (P95 +123 ft; Midland +25 / +79), and Delaware laterals span a
-- median 80 ft of TVD heel->toe (P75 132, P95 252) — a large share of a bench.
-- The tops-vs-tag QC (box/tops_qc.py) samples the structure grids at every
-- station (lateral_geom) instead of at one midpoint; KB elevation answers the
-- grid-datum question (TVD vs subsea) directly. Measured 2026-10-20 on the
-- 10-20 bulk export.
--
-- SOURCE: raw_novi."DirectionalSurveys" (sql/02; loaded incrementally by
--   etl/novi/load.py, key (API10, Path)). Path = station order surface ->
--   bottom hole. LocationType (Novi schema.json): 1 wellhead, 2 bottom hole,
--   3 kickoff point, 4 landing point, 5 perforation top, 6 perforation bottom,
--   -1 far point of a U-turn lateral, 0 any other station; 7 is undocumented
--   (one per well, mid-lateral MD — not used here). ~97 % of stations are
--   measured (Interpolated = f); lateral station spacing median 94 ft MD
--   (MWD-per-stand), i.e. the surveys are NOT resampled.
--
-- LATERAL SPAN (stations with MD in [a, b], inclusive):
--   * basis 'perfs'  — perforation top (5) -> perforation bottom (6) when both
--                      exist and bottom > top: the COMPLETED lateral;
--   * basis 'lp_bhl' — landing point (4) -> bottom hole (2) otherwise;
--   * NULL           — neither span exists: row kept, lateral columns NULL.
--   heel/toe = first/last station in span by Path; mid = station nearest the
--   span's MD midpoint; p10/p50/p90 are over STATIONS (near-uniform ~94 ft MD
--   spacing, so station-weighted ~ MD-weighted).
-- KB: kb_elev_ft = TVD - SubSeaTVD (constant per well on 100 % of wells, 10-20).
-- PLANNED SURVEYS: a well with wells_enriched.directional_survey_is_planned
--   carries its PLAN here (NM; Delaware planned laterals span a median 18 ft —
--   flat lines). Rule 15 still applies: join the flag downstream; this view is
--   source-faithful and does not filter.
-- lateral_geom: LINESTRING Z, SRID 4326, X/Y = lon/lat degrees, Z = TVD in FEET
--   (mixed units by design — Z is a depth attribute, not a coordinate; never
--   ST_3DLength it). NULL when the span has < 2 stations.
--
-- GRAIN: api10 (every non-deleted surveyed well, Permian-wide, ~62k).
-- DEPENDS ON: raw_novi."DirectionalSurveys" only — NOT on curated.wells, so a
--   sql/04 rebuild does not CASCADE it and it CASCADEs nothing.
-- REFRESH: nightly, gated on DirectionalSurveys% loads (etl/db.py
--   _GATED_REFRESH). UNIQUE (api10) supports CONCURRENTLY.
-- RUN: python -m scripts.apply_well_lateral_survey   (raw create + load + exec
--   + validate). Idempotent: type-aware DROP ... CASCADE then CREATE ... WITH DATA.
-- =============================================================================

DO $$
BEGIN
    IF EXISTS (SELECT 1 FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace
               WHERE n.nspname = 'curated' AND c.relname = 'well_lateral_survey' AND c.relkind = 'm') THEN
        EXECUTE 'DROP MATERIALIZED VIEW curated.well_lateral_survey CASCADE';
    ELSIF EXISTS (SELECT 1 FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace
                  WHERE n.nspname = 'curated' AND c.relname = 'well_lateral_survey' AND c.relkind = 'v') THEN
        EXECUTE 'DROP VIEW curated.well_lateral_survey CASCADE';
    END IF;
END $$;

CREATE MATERIALIZED VIEW curated.well_lateral_survey AS
WITH s AS (
    SELECT "API10" AS api10, "Path" AS path, "Subbasin" AS subbasin, "MD" AS md,
           "TVD" AS tvd, "SubSeaTVD" AS sstvd, "LocationType" AS lt,
           "Latitude" AS lat, "Longitude" AS lon, "Interpolated" AS interp,
           "ModifiedAt" AS modified_at
    FROM raw_novi."DirectionalSurveys"
    WHERE "DeletedAt" IS NULL
),
k AS (
    SELECT api10,
           max(subbasin)                                  AS subbasin,
           count(*)                                       AS n_stations,
           max(md)                                        AS md_max_ft,
           max(tvd)                                       AS tvd_max_ft,
           max(tvd - sstvd)                               AS kb_elev_ft,
           max(md)  FILTER (WHERE lt = 3)                 AS kop_md_ft,
           max(md)  FILTER (WHERE lt = 4)                 AS lp_md_ft,
           max(tvd) FILTER (WHERE lt = 4)                 AS lp_tvd_ft,
           max(md)  FILTER (WHERE lt = 5)                 AS perf_top_md_ft,
           max(md)  FILTER (WHERE lt = 6)                 AS perf_btm_md_ft,
           max(md)  FILTER (WHERE lt = 2)                 AS bhl_md_ft,
           max(tvd) FILTER (WHERE lt = 2)                 AS bhl_tvd_ft,
           bool_or(lt = -1)                               AS is_uturn,
           max(modified_at)                               AS survey_modified_at
    FROM s
    GROUP BY api10
),
span AS (
    SELECT k.*,
           CASE WHEN perf_top_md_ft IS NOT NULL AND perf_btm_md_ft > perf_top_md_ft THEN 'perfs'
                WHEN lp_md_ft IS NOT NULL AND bhl_md_ft > lp_md_ft THEN 'lp_bhl' END   AS lateral_basis,
           CASE WHEN perf_top_md_ft IS NOT NULL AND perf_btm_md_ft > perf_top_md_ft THEN perf_top_md_ft
                WHEN lp_md_ft IS NOT NULL AND bhl_md_ft > lp_md_ft THEN lp_md_ft END   AS a_md,
           CASE WHEN perf_top_md_ft IS NOT NULL AND perf_btm_md_ft > perf_top_md_ft THEN perf_btm_md_ft
                WHEN lp_md_ft IS NOT NULL AND bhl_md_ft > lp_md_ft THEN bhl_md_ft END  AS b_md
    FROM k
),
lat AS (
    SELECT s.api10,
           count(*)                                                        AS n_lat_stations,
           avg(CASE WHEN s.interp THEN 1.0 ELSE 0.0 END)                   AS lat_interp_share,
           min(s.tvd)                                                      AS lat_tvd_min_ft,
           max(s.tvd)                                                      AS lat_tvd_max_ft,
           percentile_cont(0.1) WITHIN GROUP (ORDER BY s.tvd)              AS lat_tvd_p10_ft,
           percentile_cont(0.5) WITHIN GROUP (ORDER BY s.tvd)              AS lat_tvd_p50_ft,
           percentile_cont(0.9) WITHIN GROUP (ORDER BY s.tvd)              AS lat_tvd_p90_ft,
           (array_agg(s.tvd ORDER BY s.path))[1]                           AS heel_tvd_ft,
           (array_agg(s.tvd ORDER BY s.path DESC))[1]                      AS toe_tvd_ft,
           (array_agg(s.tvd ORDER BY abs(s.md - (p.a_md + p.b_md) / 2.0), s.path))[1] AS mid_tvd_ft,
           CASE WHEN count(*) >= 2 THEN
               extensions.ST_SetSRID(
                   extensions.ST_MakeLine(extensions.ST_MakePoint(s.lon, s.lat, s.tvd) ORDER BY s.path),
                   4326) END                                               AS lateral_geom
    FROM s
    JOIN span p ON p.api10 = s.api10 AND p.lateral_basis IS NOT NULL
               AND s.md BETWEEN p.a_md AND p.b_md
    GROUP BY s.api10
)
SELECT
    p.api10,
    p.subbasin,
    p.lateral_basis,
    p.a_md                                       AS lat_start_md_ft,
    p.b_md                                       AS lat_end_md_ft,
    (p.b_md - p.a_md)                            AS lat_md_ft,
    p.kb_elev_ft,
    p.kop_md_ft, p.lp_md_ft, p.lp_tvd_ft,
    p.perf_top_md_ft, p.perf_btm_md_ft,
    p.bhl_md_ft, p.bhl_tvd_ft,
    p.md_max_ft, p.tvd_max_ft,
    l.heel_tvd_ft, l.mid_tvd_ft, l.toe_tvd_ft,
    (l.toe_tvd_ft - l.heel_tvd_ft)               AS toe_minus_heel_tvd_ft,
    l.lat_tvd_min_ft, l.lat_tvd_max_ft,
    (l.lat_tvd_max_ft - l.lat_tvd_min_ft)        AS lat_tvd_range_ft,
    l.lat_tvd_p10_ft, l.lat_tvd_p50_ft, l.lat_tvd_p90_ft,
    p.n_stations,
    l.n_lat_stations,
    l.lat_interp_share,
    p.is_uturn,
    p.survey_modified_at,
    l.lateral_geom
FROM span p
LEFT JOIN lat l ON l.api10 = p.api10
WITH DATA;

CREATE UNIQUE INDEX IF NOT EXISTS uq_well_lateral_survey_api10
    ON curated.well_lateral_survey (api10);
