-- =============================================================================
-- 42 — vintage-parameterized Novi Intelligence readers (by report_name)
--
-- PURPOSE: read a NAMED intel vintage from raw_intel, bypassing the curated
-- views' latest-report-per-family filter (sql/29, added 2026-09-16). raw_intel
-- deliberately retains superseded vintage slices (old collections leave the
-- share and backups exclude forecast rows — they are irreplaceable), which
-- makes vintage-over-vintage comparison possible at all.
--
-- Consumer of record: anduin's dossier "previous vintage" overlay — the
-- TC-vs-Novi comparison panel plots the persisted narvi novi_rep stick set
-- (selected at scenario-save time, under the then-current vintage) against its
-- OWN vintage's forecasts, beside a fresh selection from the current vintage.
-- Novi renumbers planned wells between vintages, so old stick_ids never join
-- the current curated views; these functions are how their curves stay
-- reachable. Also usable by vintage-parameterized accuracy work (sql/38 line).
--
-- SEMANTICS:
--   * stick_id resolves through raw_intel.stick_id_map (append-only) — the
--     same ids narvi persisted in detail->'novi_rep'. Planned wells only
--     (well_ref 'PW-%'); PDP has no ML forecast in any vintage.
--   * Rows come back only for sticks that exist in the requested report —
--     callers detect membership loss by comparing returned stick_ids to the
--     requested array (same drop-and-log discipline as anduin's median
--     series builder; never zero-fill).
--   * intel_available_reports() enumerates what raw_intel actually holds;
--     vintage_date uses the same report_version -> quarter-end formula as
--     curated.intel_vintage_date() (sql/29).
--   * Output shapes mirror the curated objects anduin already reads
--     (intel_locations meta subset / intel_forecast / intel_arps) so the
--     by-report path is a drop-in second source, not a second contract.
--
-- PERFORMANCE: plain LANGUAGE sql STABLE table functions; forecast reads hit
-- idx_ri_forecast_planned / idx_ri_forecast_report on
-- raw_intel.production_forecast (sql/27 load rebuilds them). No PostGIS.
--
-- DEPENDS ON: raw_intel.stick_id_map / well_master / planned_well /
--   production_forecast / arps_forecast (sql/27 mirror). No matview — plain
--   functions, no CASCADE exposure, no refresh cadence, out of the nightly.
--
-- RUN: python -c "from scripts.load_intel_sf import run_sql_file; run_sql_file('42_intel_by_report.sql')"
-- Idempotent: CREATE OR REPLACE throughout.
-- =============================================================================

-- -----------------------------------------------------------------------------
-- Which vintages does raw_intel hold?
-- -----------------------------------------------------------------------------
CREATE OR REPLACE FUNCTION curated.intel_available_reports()
RETURNS TABLE (
    report_name    text,
    basin_slug     text,
    report_version text,
    vintage_date   date,
    is_latest      boolean
) AS $$
    SELECT DISTINCT
        wm.report_name,
        wm.basin_slug,
        wm.report_version,
        (make_date(substring(wm.report_version, 1, 4)::int,
                   substring(wm.report_version, 6, 1)::int * 3, 1)
         + interval '1 month' - interval '1 day')::date  AS vintage_date,
        wm.report_name = max(wm.report_name)
            OVER (PARTITION BY split_part(wm.report_name, '__', 2)) AS is_latest
    FROM raw_intel.well_master wm
$$ LANGUAGE sql STABLE;

COMMENT ON FUNCTION curated.intel_available_reports() IS
'Vintages present in raw_intel per basin family: report_name, basin_slug, report_version, quarter-end vintage_date (same formula as curated.intel_vintage_date), is_latest per family. Superseded vintages are retained on purpose (irreplaceable; vintage-over-vintage comparison input). sql/42.';

-- -----------------------------------------------------------------------------
-- Stick metadata for a named vintage (planned sticks only — the classes that
-- carry an ML forecast). Mirrors the intel_locations columns anduin''s
-- median-series builder reads.
-- -----------------------------------------------------------------------------
CREATE OR REPLACE FUNCTION curated.intel_stick_meta_by_report(
    p_report_name text,
    p_stick_ids   bigint[]
) RETURNS TABLE (
    stick_id  bigint,
    unique_id text,
    category  text,
    ll_ft     numeric,
    basin     text
) AS $$
    SELECT
        m.stick_id,
        wm.name                                   AS unique_id,   -- = novi_wellname
        CASE wm.inventory_class
            WHEN 'BASE_CASE' THEN 'PUD'
            WHEN 'EMERGING'  THEN 'RES'
        END                                       AS category,
        wm.lateral_length::numeric                AS ll_ft,
        wm.basin_slug                             AS basin
    FROM raw_intel.stick_id_map m
    JOIN raw_intel.well_master wm
      ON wm.well_ref = m.well_ref AND wm.report_name = p_report_name
    WHERE m.stick_id = ANY (p_stick_ids)
      AND wm.inventory_class IN ('BASE_CASE', 'EMERGING')
$$ LANGUAGE sql STABLE;

COMMENT ON FUNCTION curated.intel_stick_meta_by_report(text, bigint[]) IS
'PUD/RES stick metadata (unique_id=name, category, ll_ft, basin) for a NAMED vintage in raw_intel, keyed by stable stick_id (raw_intel.stick_id_map). Sticks absent from that report return no row — callers detect membership loss, never zero-fill. sql/42.';

-- -----------------------------------------------------------------------------
-- Monthly production forecast for a named vintage — shape of
-- curated.intel_forecast (sql/29) plus stick_id.
-- -----------------------------------------------------------------------------
CREATE OR REPLACE FUNCTION curated.intel_forecast_by_report(
    p_report_name text,
    p_stick_ids   bigint[]
) RETURNS TABLE (
    stick_id      bigint,
    novi_wellname text,
    ip_day        integer,
    mop           integer,
    oil           double precision,
    gas           double precision,
    water         double precision
) AS $$
    SELECT
        m.stick_id,
        pw.name                          AS novi_wellname,
        pf.forecast_day                  AS ip_day,
        (pf.forecast_day / 30)::int      AS mop,
        pf.oil_per_day                   AS oil,
        pf.gas_per_day                   AS gas,
        pf.water_per_day                 AS water
    FROM raw_intel.stick_id_map m
    JOIN raw_intel.planned_well pw
      ON 'PW-' || pw.planned_well_id::text = m.well_ref
     AND pw.report_name = p_report_name
    JOIN raw_intel.production_forecast pf
      ON pf.planned_well_id = pw.planned_well_id
     AND pf.report_name = pw.report_name
    WHERE m.stick_id = ANY (p_stick_ids)
$$ LANGUAGE sql STABLE;

COMMENT ON FUNCTION curated.intel_forecast_by_report(text, bigint[]) IS
'Monthly P50 production forecast (30-day mop grid, per-day rates) for a NAMED vintage in raw_intel, keyed by stable stick_id. Same shape as curated.intel_forecast plus stick_id/ip_day. sql/42.';

-- -----------------------------------------------------------------------------
-- Arps segments for a named vintage — shape of curated.intel_arps (sql/29)
-- (used for the >last_mop tail continuation in series builders).
-- -----------------------------------------------------------------------------
CREATE OR REPLACE FUNCTION curated.intel_arps_by_report(
    p_report_name text,
    p_stick_ids   bigint[]
) RETURNS TABLE (
    stick_id           bigint,
    novi_wellname      text,
    production_stream  text,
    segment            integer,
    segment_curve_type text,
    b                  double precision,
    d_nom              double precision,
    q_start            double precision,
    q_stop             double precision,
    day_start          integer,
    day_stop           integer
) AS $$
    SELECT
        m.stick_id,
        pw.name                           AS novi_wellname,
        af.stream                         AS production_stream,
        af.segment_number                 AS segment,
        af.segment_curve_type,
        af.b_factor                       AS b,
        af.nominal_decline_rate           AS d_nom,
        af.segment_start_rate             AS q_start,
        af.segment_end_rate               AS q_stop,
        af.day_start,
        af.day_stop
    FROM raw_intel.stick_id_map m
    JOIN raw_intel.planned_well pw
      ON 'PW-' || pw.planned_well_id::text = m.well_ref
     AND pw.report_name = p_report_name
    JOIN raw_intel.arps_forecast af
      ON af.well_ref = m.well_ref
     AND af.report_name = pw.report_name
    WHERE m.stick_id = ANY (p_stick_ids)
$$ LANGUAGE sql STABLE;

COMMENT ON FUNCTION curated.intel_arps_by_report(text, bigint[]) IS
'Segmented Arps decline parameters (per stream, nominal declines) for a NAMED vintage in raw_intel, keyed by stable stick_id. Same shape as curated.intel_arps plus stick_id/q_stop. sql/42.';

-- Verification:
--
--   SELECT * FROM curated.intel_available_reports() ORDER BY report_name;
--   -- expect 4 rows post-2026Q3 reload: {Delaware,Midland} x {2025Q3, 2026Q3},
--   -- is_latest true on the 2026Q3 pair.
--
--   -- Round-trip a persisted narvi novi_rep set (2025Q3-era save):
--   --   meta rows return for the OLD report_name and none for the new one;
--   --   forecast rows land on the 30-day mop grid.
