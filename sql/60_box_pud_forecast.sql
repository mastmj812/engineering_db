-- =============================================================================
-- 60_box_pud_forecast.sql — BOX (Blue Ox) production schema, step 7b: locations, runs, analog workups
-- =============================================================================
-- docs/box_type_curves_plan.md §5 step 7 (rewritten 2026-10-14) + D54-D70. App-owned like the rest of
-- schema box (sql/54): the ETL and refresh_all() never touch it. Writer = the step-7c production run
-- (postgres, session pooler); apps and Steven read via analyst_ro.
--
-- The method of record is the frozen analog workup `box_v2_wf` (D58): deal-intake analog selection at every
-- location, P50 per stream, walk-forward haircut (D62), accepted at gate 6 (D59). The step-4/5 area-curve
-- tables stay as the record of the retired method (D66; comments re-stamped at the end of this file).
--
--   box.location             OUR location id. A location outlives Novi's stick ids, which do not carry
--                            across vintages; Steven's econ (box_econ, step 7d) keys on location_id.
--   box.location_source      the quarterly crosswalk: which Novi stick (report_version, stick_id) a
--                            location was in each vintage, and how it was matched.
--   box.forecast_run         one row per production run: frozen spec + code / engine SHAs, the Novi vintage
--                            and data-through date, the D62 haircut table, the D63 calendar factor
--                            (published, not applied), and the D59 / D69 disclosure numbers. One record run.
--   box.pud_forecast         one row per (run, location) for EVERY location of the D67 universe (Novi PUD
--                            category; reconciled remaining_pud / conflict / not-yet-reconciled; every
--                            box.bench_scope bench incl. emerging), coverage-classed: not-covered rows are
--                            counted, never zero, and carry no volumes.
--   box.pud_forecast_stream  covered rows only: per stream (oil, gas) the analog P50 curve per 1,000 ft, the
--                            lateral multiplier, the haircut, EUR (raw 50-yr integral x haircut; rule 6).
--   box.pud_forecast_month   derived: monthly volumes, months 1-600, uptime-free (D63), haircut applied,
--                            exact per-month integrals (D39). Regenerated from the stream rows.
--   box.location_analog      the named analogs behind each covered location (the workup's provenance).
--
-- Requires sql/54 (schema box, bench_scope, extent). Geometry on box.location only: plain + geography GiST
-- indexes created with the table, before any spatial reader (sql/26 rule). No matviews (nothing to
-- REFRESH). Not exposed to the Supabase Data API. Idempotent.
--
-- RUN: python -m scripts.apply_box_pud_forecast      (!! go-apply required)
-- =============================================================================

-- ---------------------------------------------------------------------------
-- box.location + box.location_source — our ids and the Novi crosswalk
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS box.location (
    location_id         bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    basin               text    NOT NULL CHECK (basin IN ('delaware', 'midland')),
    formation_blueox    text    NOT NULL,
    geom                extensions.geometry(Geometry, 4326) NOT NULL,
    lateral_ft          double precision CHECK (lateral_ft > 0),
    first_seen_vintage  text    NOT NULL,
    last_seen_vintage   text    NOT NULL,
    created_at          timestamptz NOT NULL DEFAULT now(),
    created_by          text    NOT NULL DEFAULT current_user,
    CONSTRAINT box_location_vintage_ck CHECK (first_seen_vintage <= last_seen_vintage)
);

CREATE INDEX IF NOT EXISTS box_location_geom_gix ON box.location USING gist (geom);
CREATE INDEX IF NOT EXISTS box_location_geog_gix ON box.location USING gist ((geom::extensions.geography));
CREATE INDEX IF NOT EXISTS box_location_bench_ix ON box.location (basin, formation_blueox);

CREATE TABLE IF NOT EXISTS box.location_source (
    location_id         bigint  NOT NULL REFERENCES box.location (location_id) ON DELETE CASCADE,
    report_version      text    NOT NULL,
    stick_id            bigint  NOT NULL,
    match_method        text    NOT NULL CHECK (match_method IN ('seed', 'overlap', 'new')),
    match_overlap       double precision CHECK (match_overlap BETWEEN 0 AND 1),
    pad_name            text,
    PRIMARY KEY (location_id, report_version),
    CONSTRAINT box_location_source_overlap_ck CHECK ((match_method = 'overlap') = (match_overlap IS NOT NULL))
);

CREATE UNIQUE INDEX IF NOT EXISTS box_location_source_stick_uq ON box.location_source (report_version, stick_id);

-- ---------------------------------------------------------------------------
-- box.forecast_run — one row per production run
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS box.forecast_run (
    run_id              bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    spec                text    NOT NULL CHECK (spec = 'box_v2_wf'),
    code_sha            text    NOT NULL,
    engine_sha          text    NOT NULL,
    dealintake_config   integer NOT NULL,
    report_version      text    NOT NULL,
    data_through        date    NOT NULL,
    volumes_basis       text    NOT NULL DEFAULT 'uptime_free' CHECK (volumes_basis = 'uptime_free'),
    horizon_months      smallint NOT NULL DEFAULT 600 CHECK (horizon_months = 600),
    haircut             jsonb   NOT NULL,
    calendar_factor     jsonb   NOT NULL,
    disclosure          jsonb   NOT NULL,
    extents             jsonb   NOT NULL DEFAULT '{}'::jsonb,
    counts              jsonb   NOT NULL DEFAULT '{}'::jsonb,
    notes               text,
    is_record           boolean NOT NULL DEFAULT false,
    superseded_by       bigint  REFERENCES box.forecast_run (run_id),
    created_at          timestamptz NOT NULL DEFAULT now(),
    created_by          text    NOT NULL DEFAULT current_user,
    CONSTRAINT box_forecast_run_haircut_ck CHECK (haircut ? 'oil' AND haircut ? 'gas'),
    CONSTRAINT box_forecast_run_cf_ck CHECK (calendar_factor ? 'oil' AND calendar_factor ? 'gas'),
    CONSTRAINT box_forecast_run_disclosure_ck CHECK (disclosure ? 'hindcast_bias' AND disclosure ? 'radius_ranges')
);

CREATE UNIQUE INDEX IF NOT EXISTS box_forecast_run_record_uq ON box.forecast_run ((is_record)) WHERE is_record;

-- ---------------------------------------------------------------------------
-- box.pud_forecast — every location of the D67 universe, coverage-classed
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS box.pud_forecast (
    run_id              bigint  NOT NULL REFERENCES box.forecast_run (run_id) ON DELETE CASCADE,
    location_id         bigint  NOT NULL REFERENCES box.location (location_id),
    stick_id            bigint  NOT NULL,
    basin               text    NOT NULL,
    bench               text    NOT NULL,
    formation_blueox    text    NOT NULL,
    recon_status        text    NOT NULL CHECK (recon_status IN ('remaining_pud', 'conflict', 'not_reconciled')),
    coverage            text    NOT NULL CHECK (coverage IN ('covered', 'not_covered_emerging', 'not_covered_wcxy',
                                                             'not_covered_unvalidated', 'not_covered_outside_extent',
                                                             'not_covered_no_analogs')),
    inside_extent       boolean,
    extent_id           bigint  REFERENCES box.extent (extent_id),
    pad_name            text,
    lateral_ft          double precision CHECK (lateral_ft > 0),
    completed_lateral_ft double precision CHECK (completed_lateral_ft > 0),
    planned_spacing_ft  double precision CHECK (planned_spacing_ft > 0),
    spacing_source      text    CHECK (spacing_source IN ('neighbour_gap', 'default_880')),
    search_mode         text    CHECK (search_mode IN ('circle', 'strike')),
    radius_mi           double precision CHECK (radius_mi > 0),
    radius_class        text    CHECK (radius_class IN ('5 mi ring', 'past 5 mi')),
    n_analogs           integer CHECK (n_analogs >= 0),
    short_lateral       boolean,
    flags               text[]  NOT NULL DEFAULT '{}',
    workup_ref          text,
    PRIMARY KEY (run_id, location_id),
    FOREIGN KEY (basin, bench) REFERENCES box.bench_scope (basin, bench),
    -- a covered row is fully described; a not-covered row carries no forecast description (D67). Written as two
    -- implications (a NULL inside one equality would let the CHECK pass).
    CONSTRAINT box_pud_forecast_covered_ck CHECK (
        coverage <> 'covered' OR (search_mode IS NOT NULL AND radius_mi IS NOT NULL AND radius_class IS NOT NULL
                                  AND coalesce(n_analogs, 0) >= 3 AND planned_spacing_ft IS NOT NULL
                                  AND spacing_source IS NOT NULL AND completed_lateral_ft IS NOT NULL)),
    -- a no-analogs row may say how far it searched; every other not-covered row carries no search at all
    CONSTRAINT box_pud_forecast_uncovered_ck CHECK (
        coverage IN ('covered', 'not_covered_no_analogs')
        OR (search_mode IS NULL AND radius_mi IS NULL AND radius_class IS NULL AND n_analogs IS NULL)),
    CONSTRAINT box_pud_forecast_no_analogs_ck CHECK (coverage <> 'not_covered_no_analogs' OR coalesce(n_analogs, 0) < 3),
    CONSTRAINT box_pud_forecast_inside_ck CHECK (coverage <> 'covered' OR (inside_extent AND extent_id IS NOT NULL)),
    CONSTRAINT box_pud_forecast_radius_ck CHECK (radius_class IS NULL OR (radius_class = '5 mi ring') = (radius_mi <= 5))
);

CREATE UNIQUE INDEX IF NOT EXISTS box_pud_forecast_stick_uq ON box.pud_forecast (run_id, stick_id);
-- FK target that lets child tables require coverage = 'covered' (stream / month / analog rows only exist for covered locations)
CREATE UNIQUE INDEX IF NOT EXISTS box_pud_forecast_cov_uq ON box.pud_forecast (run_id, location_id, coverage);
CREATE INDEX IF NOT EXISTS box_pud_forecast_location_ix ON box.pud_forecast (location_id);
CREATE INDEX IF NOT EXISTS box_pud_forecast_coverage_ix ON box.pud_forecast (run_id, coverage);

-- ---------------------------------------------------------------------------
-- box.pud_forecast_stream — covered rows, per stream
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS box.pud_forecast_stream (
    run_id              bigint  NOT NULL,
    location_id         bigint  NOT NULL,
    stream              text    NOT NULL CHECK (stream IN ('oil', 'gas')),
    params              jsonb   NOT NULL,
    lateral_mult        double precision NOT NULL CHECK (lateral_mult > 0),
    eur_haircut         double precision NOT NULL CHECK (eur_haircut > 0),
    eur_raw             double precision NOT NULL CHECK (eur_raw > 0),
    eur                 double precision NOT NULL CHECK (eur > 0),
    eur_per_kft         double precision NOT NULL CHECK (eur_per_kft > 0),
    cum12               double precision CHECK (cum12 >= 0),
    cum24               double precision CHECK (cum24 >= 0),
    coverage            text    NOT NULL DEFAULT 'covered' CHECK (coverage = 'covered'),
    PRIMARY KEY (run_id, location_id, stream),
    FOREIGN KEY (run_id, location_id, coverage) REFERENCES box.pud_forecast (run_id, location_id, coverage) ON DELETE CASCADE,
    CONSTRAINT box_pud_forecast_stream_eur_ck CHECK (abs(eur - eur_raw * eur_haircut) <= 1e-6 * eur)
);

-- ---------------------------------------------------------------------------
-- box.pud_forecast_month — derived monthly volumes (regenerated from the stream rows)
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS box.pud_forecast_month (
    run_id              bigint   NOT NULL,
    location_id         bigint   NOT NULL,
    stream              text     NOT NULL,
    month_no            smallint NOT NULL CHECK (month_no BETWEEN 1 AND 600),
    volume              double precision NOT NULL CHECK (volume >= 0),
    PRIMARY KEY (run_id, location_id, stream, month_no),
    FOREIGN KEY (run_id, location_id, stream) REFERENCES box.pud_forecast_stream (run_id, location_id, stream) ON DELETE CASCADE
);

-- ---------------------------------------------------------------------------
-- box.location_analog — named analogs behind each covered location
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS box.location_analog (
    run_id              bigint   NOT NULL,
    location_id         bigint   NOT NULL,
    api10               text     NOT NULL CHECK (api10 ~ '^[0-9]{10}$'),
    rank                smallint NOT NULL CHECK (rank >= 1),
    dist_ft             double precision CHECK (dist_ft >= 0),
    lateral_ft          double precision,
    first_production    date,
    transfer            boolean  NOT NULL DEFAULT false,
    coverage            text     NOT NULL DEFAULT 'covered' CHECK (coverage = 'covered'),
    PRIMARY KEY (run_id, location_id, api10),
    FOREIGN KEY (run_id, location_id, coverage) REFERENCES box.pud_forecast (run_id, location_id, coverage) ON DELETE CASCADE
);

CREATE UNIQUE INDEX IF NOT EXISTS box_location_analog_rank_uq ON box.location_analog (run_id, location_id, rank);
CREATE INDEX IF NOT EXISTS box_location_analog_api10_ix ON box.location_analog (api10);

GRANT SELECT ON box.location, box.location_source, box.forecast_run, box.pud_forecast, box.pud_forecast_stream,
    box.pud_forecast_month, box.location_analog TO analyst_ro;

-- ---------------------------------------------------------------------------
-- Comments
-- ---------------------------------------------------------------------------
COMMENT ON TABLE box.location IS
    'BOX location ids (plan step 7, D67): one row per drillable location, outliving Novi stick ids (which do not carry across vintages). '
    'geom / lateral_ft = the stick as last seen; formation_blueox is part of identity (a re-benched stick becomes a new location). '
    'box_econ (Steven) keys on location_id. See sql/60.';
COMMENT ON TABLE box.location_source IS
    'Quarterly crosswalk: the Novi stick (report_version, stick_id) a BOX location was in each vintage. match_method seed = first load; '
    'overlap = carried from the previous vintage by co-extent overlap (rule 9; match_overlap = the share of the shorter stick); new = no '
    'predecessor. One location per stick per vintage (unique). See sql/60.';
COMMENT ON TABLE box.forecast_run IS
    'BOX production runs (step 7, D58/D59/D62/D63/D69): the frozen analog workup box_v2_wf at code_sha, blueox-boxfit @ engine_sha, deal-intake '
    'config version, Novi report_version, actuals through data_through. haircut = D62 walk-forward factors per stream per horizon (cum-12/24/36/48, '
    'pooled over every cutoff 2019-2024, tuning + holdout; linear between horizons, cum-48 held flat to month 600, so EUR scales by the cum-48 factor). '
    'calendar_factor = F(k) PUBLISHED, NOT APPLIED (D63: volumes are uptime-free; Steven keeps his downtime factor). disclosure = the measured hindcast '
    'bias by horizon (D59 condition 3) and the radius-class package ranges (D69) every workup states. Exactly one is_record run. See sql/60.';
COMMENT ON TABLE box.pud_forecast IS
    'One row per (run, location) for the whole D67 universe: Novi PUD category (no RES), reconciled remaining_pud / conflict / not_reconciled, on every '
    'box.bench_scope bench. coverage: covered (in-scope bench pool, validated, >= 50 % of the stick inside the record extent, analogs found); '
    'not_covered_emerging (bench out of scope, D2); not_covered_wcxy (D61); not_covered_unvalidated (in-scope bench the frozen spec was not accepted '
    'on, D60 - BS2_S in v1); not_covered_outside_extent (D1); not_covered_no_analogs (fewer than 3 analogs at the 20-mi cap - reported, never hidden). '
    'Not-covered rows carry no forecast and no volumes. Gate 7 identity: covered rows = the in-extent WCA_1 + WCA_2 universe exactly. See sql/60.';
COMMENT ON COLUMN box.pud_forecast.planned_spacing_ft IS
    'D64: in-bench perpendicular gap to the nearest same-bench sticks (PUD or PDP) in the as-planned inventory; spacing_source default_880 when none. '
    'Feeds the deal-intake representative-spacing analog filter.';
COMMENT ON COLUMN box.pud_forecast.radius_class IS
    'D69: 5 mi ring (analogs found within the first 5-mi ring) or past 5 mi (search expanded; D55 strike ellipse where local strike is trusted). '
    'The workup states the measured package range of the class (box.forecast_run.disclosure).';
COMMENT ON COLUMN box.pud_forecast.workup_ref IS 'D65: the per-pad workup page this location is rendered on.';
COMMENT ON TABLE box.pud_forecast_stream IS
    'Covered locations, per stream (oil bbl, gas mcf): params = the analog cohort P50 curve per 1,000 ft of lateral (D57: deal-intake P50, labelled P50; '
    'ramp + modified-hyperbolic Arps, Di NOMINAL per year, oil / gas Di cap 4.0, Df 0.08 Delaware). lateral_mult = completed lateral / 1,000 x the D50 '
    'Cui & Cross relative efficiency when the lateral is under 7,500 ft (else 1). eur_raw = the raw 50-yr integral of params x lateral_mult (rule 6, '
    'no economic limit); eur = eur_raw x eur_haircut (the cum-48 D62 factor). cum12 / cum24 haircut-applied, uptime-free. See sql/60.';
COMMENT ON TABLE box.pud_forecast_month IS
    'Derived monthly volumes per covered location x stream, months 1-600: exact per-month integrals (D39) of params x lateral_mult, times the D62 haircut '
    'interpolated by month. UPTIME-FREE (D63): apply F(k) from box.forecast_run.calendar_factor OR a downtime factor, never both. Sum of months = eur '
    'within 0.1 %. Regenerated from box.pud_forecast_stream. See sql/60.';
COMMENT ON TABLE box.location_analog IS
    'The named analog wells behind each covered location (the workup''s provenance, D54): rank in selection order, distance (ellipse distance on a '
    'strike search), lateral, first production, transfer = carried by the short-history transfer. See sql/60.';

-- ---------------------------------------------------------------------------
-- D66: the step-4/5 area-curve tables are the record of the RETIRED method. Prefix their comments once.
-- ---------------------------------------------------------------------------
DO $$
DECLARE
    t text;
    c text;
    tag constant text := 'SUPERSEDED (D54/D57/D66, 2026-10-14): record of the retired area-curve + factor-chain method; the production forecast is '
                         'box.pud_forecast (sql/60). Kept, never read by apps. ';
BEGIN
    FOREACH t IN ARRAY ARRAY['box.tc_area', 'box.type_curve', 'box.tc_member', 'box.risk_factor'] LOOP
        IF to_regclass(t) IS NOT NULL THEN
            c := coalesce(obj_description(t::regclass, 'pg_class'), '');
            IF position('SUPERSEDED (D54/D57/D66' IN c) = 0 THEN
                EXECUTE format('COMMENT ON TABLE %s IS %L', t, tag || c);
            END IF;
        END IF;
    END LOOP;
END
$$;
