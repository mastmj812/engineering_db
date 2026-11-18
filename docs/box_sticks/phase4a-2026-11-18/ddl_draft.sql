-- =============================================================================
-- DRAFT, gate 4a. NOT a numbered sql/NN file, NOT applied, not on the apply path.
-- BOX sticks storage and identity (docs/box_sticks_plan.md, phase 4). Becomes sql/NN at gate 4b
-- (next free number checked against main AND open PRs at that time), with its apply script, tests
-- and sql/31 comments. Open choices are marked  -- Q<n>  and listed in DESIGN.md.
--
-- App-owned like the rest of schema box: the ETL and refresh_all() never touch it. Additive only:
-- no existing object is dropped or re-pointed. Existing box.location rows (252,925 Novi 2026Q3 seeds,
-- read 2026-11-18) keep every value they have.
-- =============================================================================

-- ---------------------------------------------------------------------------
-- 1. box.location_set: one generation run per basin (the forecast_run pattern, sql/60 + sql/70)
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS box.location_set (
    set_id              bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    basin               text    NOT NULL CHECK (basin IN ('delaware', 'midland')),
    generator_version   text    NOT NULL,                  -- box.sticks.core.VERSION
    code_sha            text    NOT NULL,                  -- engineering_db commit the run was built from
    narvi_sha           text    NOT NULL,                  -- the pinned narvi engine commit
    dsu_vintage         text    NOT NULL,                  -- raw_novi_intel.pads.report_version ('2026Q3')
    pulled_at           timestamptz NOT NULL,              -- when the warehouse inputs were read (one snapshot)
    tag_run_id          bigint  NOT NULL,                  -- meta.formation_tag_run.run_id live at the pull
    tag_policy_digest   text    NOT NULL,
    cfg                 jsonb   NOT NULL,                  -- every threshold the run used (Cfg + chain / spacing / envelope constants)
    inputs              jsonb   NOT NULL,                  -- manifest: per input relation the row count and digest; extent ids; file sha256s
    counts              jsonb   NOT NULL DEFAULT '{}'::jsonb,   -- DSUs, DSU x bench, sticks, legs, ft, by rung / reason; invariant violations (must be 0)
    backtest            jsonb   NOT NULL DEFAULT '{}'::jsonb,   -- the bars as written and each verdict, failures included
    prev_set_id         bigint  REFERENCES box.location_set (set_id),   -- the set ids were carried from
    crosswalk           jsonb   NOT NULL DEFAULT '{}'::jsonb,   -- carried / new / stopped, corridor and share used
    notes               text,
    is_record           boolean NOT NULL DEFAULT false,
    superseded_by       bigint  REFERENCES box.location_set (set_id),
    created_at          timestamptz NOT NULL DEFAULT now(),
    created_by          text    NOT NULL DEFAULT current_user,
    CONSTRAINT box_location_set_inputs_ck CHECK (inputs ? 'relations' AND inputs ? 'extents' AND inputs ? 'files')
);
CREATE UNIQUE INDEX IF NOT EXISTS box_location_set_record_basin_uq ON box.location_set (basin) WHERE is_record;

-- ---------------------------------------------------------------------------
-- 2. box.location: identity columns for our own sticks (D14: source + source_ref)
-- ---------------------------------------------------------------------------
ALTER TABLE box.location ADD COLUMN IF NOT EXISTS source text NOT NULL DEFAULT 'novi';       -- metadata-only on PG 11+
ALTER TABLE box.location ADD COLUMN IF NOT EXISTS dsu_vintage text;
ALTER TABLE box.location ADD COLUMN IF NOT EXISTS pad_id bigint;                              -- raw_novi_intel.pads.pad_id of dsu_vintage
ALTER TABLE box.location ADD COLUMN IF NOT EXISTS slot_no integer;                            -- never reused inside a DSU x bench
ALTER TABLE box.location ADD COLUMN IF NOT EXISTS first_seen_set bigint REFERENCES box.location_set (set_id);
ALTER TABLE box.location ADD COLUMN IF NOT EXISTS last_seen_set  bigint REFERENCES box.location_set (set_id);
-- Novi vintages do not apply to our own sticks:
ALTER TABLE box.location ALTER COLUMN first_seen_vintage DROP NOT NULL;
ALTER TABLE box.location ALTER COLUMN last_seen_vintage  DROP NOT NULL;
-- (as DO-blocks guarded on pg_constraint in the real file)
ALTER TABLE box.location ADD CONSTRAINT box_location_source_ck CHECK (source IN ('novi', 'box_sticks'));
ALTER TABLE box.location ADD CONSTRAINT box_location_source_shape_ck CHECK (
    (source = 'novi' AND first_seen_vintage IS NOT NULL AND last_seen_vintage IS NOT NULL
        AND pad_id IS NULL AND slot_no IS NULL AND first_seen_set IS NULL AND last_seen_set IS NULL)
 OR (source = 'box_sticks' AND first_seen_vintage IS NULL AND last_seen_vintage IS NULL
        AND dsu_vintage IS NOT NULL AND pad_id IS NOT NULL AND slot_no >= 1
        AND first_seen_set IS NOT NULL AND last_seen_set IS NOT NULL AND first_seen_set <= last_seen_set));
CREATE UNIQUE INDEX IF NOT EXISTS box_location_slot_uq
    ON box.location (dsu_vintage, pad_id, formation_blueox, slot_no) WHERE source = 'box_sticks';
CREATE INDEX IF NOT EXISTS box_location_source_ix ON box.location (source, basin);

-- Q2. App-facing stick_id = location_id for our sticks. To keep that number space apart from Novi stick ids
-- (1,531,428 to 1,824,903 at 2026Q3) and from the Novi-seeded location ids (4 to 252,947) by construction:
ALTER TABLE box.location ALTER COLUMN location_id RESTART WITH 10000001;

-- ---------------------------------------------------------------------------
-- 3. box.location_stick: the stick as generated in one set (Q1: per-set rows, not columns on box.location)
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS box.location_stick (
    set_id              bigint  NOT NULL REFERENCES box.location_set (set_id) ON DELETE CASCADE,
    location_id         bigint  NOT NULL REFERENCES box.location (location_id),
    basin               text    NOT NULL,
    pad_id              bigint  NOT NULL,
    formation_blueox    text    NOT NULL,
    slot_no             integer NOT NULL CHECK (slot_no >= 1),
    well_name           text    NOT NULL,                  -- '<pad_id>-<bench>-<slot_no>': stable, not the position in the row (Q3)
    well_type           text    NOT NULL CHECK (well_type IN ('single', 'uturn')),
    n_legs              smallint NOT NULL CHECK (n_legs IN (1, 2)),
    legs_geom           extensions.geometry(MultiLineString, 4326) NOT NULL,   -- producing legs, heel -> toe
    turn_geom           extensions.geometry(LineString, 4326),                 -- non-producing arc; NULL for single
    completed_lateral_ft double precision NOT NULL CHECK (completed_lateral_ft > 0),  -- sum of legs (D56)
    drilled_lateral_ft  double precision NOT NULL CHECK (drilled_lateral_ft > 0),     -- legs + turn arc
    turn_radius_ft      double precision,
    turn_dls_deg_per_100ft double precision,
    turn_arc_ft         double precision,
    azimuth_deg         double precision NOT NULL CHECK (azimuth_deg >= 0 AND azimuth_deg < 180),   -- TRUE bearing, axial
    azimuth_grid_deg    double precision NOT NULL CHECK (azimuth_grid_deg >= 0 AND azimuth_grid_deg < 180),  -- UTM 13N grid, 0.1 deg
    azimuth_basis       text    NOT NULL,
    gunbarrel_x_ft      double precision[] NOT NULL,       -- per leg; sign rule v2, origin = DSU centroid
    setback_ft          double precision NOT NULL,
    -- landing depth and how far to trust it
    target_tvd_ft       double precision NOT NULL CHECK (target_tvd_ft > 0),
    tvd_rung            text    NOT NULL CHECK (tvd_rung IN ('direct', 'thickness', 'bracket', 'offset')),
    tvd_anchor          text[]  NOT NULL DEFAULT '{}',     -- bench(es) a carried depth came from; empty for direct
    tvd_err_median_ft   double precision,                  -- held-out expected error of this rung for this bench
    tvd_err_p90_ft      double precision,
    tvd_reconciled_shift_ft double precision NOT NULL DEFAULT 0,
    second_level_tvd_ft double precision,                  -- with flag second_level_nearby; thickness rung only (Q7)
    -- spacing
    spacing_ft          double precision NOT NULL CHECK (spacing_ft > 0),   -- as placed
    spacing_map_ft      double precision NOT NULL,                          -- the blended map value before U-turn floor / setback fit
    spacing_grid        text    NOT NULL,                  -- pinned / map_spacing / staggered / offset / tightened / row_dropped / no_clear_band
    spacing_n_eff       double precision,
    spacing_weighted_median_ft double precision,
    spacing_band        text,
    spacing_band_ft     double precision,
    flags               text[]  NOT NULL DEFAULT '{}'
        CHECK (flags <@ ARRAY['pinned', 'two_landings_observed', 'second_level_nearby', 'dsu_drilled_across']),
    -- identity provenance (the location_source pattern)
    match_method        text    NOT NULL CHECK (match_method IN ('seed', 'overlap', 'new')),
    match_share         double precision CHECK (match_share BETWEEN 0 AND 1),
    match_offset_ft     double precision CHECK (match_offset_ft >= 0),
    detail              jsonb   NOT NULL,                  -- the generator's full record, for exact reload
    PRIMARY KEY (set_id, location_id),
    CONSTRAINT box_location_stick_match_ck CHECK ((match_method = 'overlap') = (match_share IS NOT NULL)),
    CONSTRAINT box_location_stick_turn_ck CHECK ((well_type = 'uturn') = (turn_geom IS NOT NULL) AND (well_type = 'uturn') = (n_legs = 2)),
    CONSTRAINT box_location_stick_second_ck CHECK ((second_level_tvd_ft IS NOT NULL) = ('second_level_nearby' = ANY (flags))),
    CONSTRAINT box_location_stick_anchor_ck CHECK ((tvd_rung = 'direct') = (cardinality(tvd_anchor) = 0))
);
CREATE UNIQUE INDEX IF NOT EXISTS box_location_stick_slot_uq ON box.location_stick (set_id, pad_id, formation_blueox, slot_no);
CREATE INDEX IF NOT EXISTS box_location_stick_location_ix ON box.location_stick (location_id);
CREATE INDEX IF NOT EXISTS box_location_stick_geom_gix ON box.location_stick USING gist (legs_geom);
CREATE INDEX IF NOT EXISTS box_location_stick_geog_gix ON box.location_stick USING gist ((legs_geom::extensions.geography));  -- before any spatial reader (sql/26 rule)

-- ---------------------------------------------------------------------------
-- 4. What the generator was given, per set, so generate_dsu() re-runs from the warehouse alone
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS box.location_set_dsu (
    set_id              bigint  NOT NULL REFERENCES box.location_set (set_id) ON DELETE CASCADE,
    pad_id              bigint  NOT NULL,
    azimuth_deg         double precision NOT NULL,
    azimuth_grid_deg    double precision NOT NULL,
    azimuth_basis       text    NOT NULL,
    wca_class           text,
    wca_dominant        text,
    well_type           text    CHECK (well_type IN ('single', 'uturn')),   -- NULL: no drillable window or no bench
    straight_ft         double precision,
    clear_width_ft      double precision,
    long_wells          integer,
    drilled_across      boolean,
    turn_at_high        boolean,
    wells_read          integer NOT NULL,
    sticks              integer NOT NULL,
    legs                integer NOT NULL,
    PRIMARY KEY (set_id, pad_id)
);

CREATE TABLE IF NOT EXISTS box.location_set_bench (
    set_id              bigint  NOT NULL REFERENCES box.location_set (set_id) ON DELETE CASCADE,
    pad_id              bigint  NOT NULL,
    formation_blueox    text    NOT NULL,
    -- input (box.sticks.core.Bench)
    inside_frac         double precision NOT NULL,
    tvd_in_ft           double precision,                  -- the landing chain's depth before stack reconciliation
    tvd_rung            text    NOT NULL CHECK (tvd_rung IN ('direct', 'thickness', 'bracket', 'offset', 'none')),
    tvd_anchor          text[]  NOT NULL DEFAULT '{}',
    tvd_err_median_ft   double precision,
    tvd_err_p90_ft      double precision,
    second_level_tvd_ft double precision,
    second_level_share  double precision,
    two_landings        double precision[],                -- upper / lower where the DSU's own wells show two
    spacing_map_ft      double precision NOT NULL,
    spacing_basis       jsonb   NOT NULL,                  -- n_eff, weighted median, band, band value
    -- outcome
    no_row_reason       text    NOT NULL DEFAULT '',       -- sliver / no_depth / wca_one_member / wca_one_landing / reconciled_out / no_window / no_rows
    target_tvd_ft       double precision,
    reconciled_shift_ft double precision,
    spacing_final_ft    double precision,
    grid                text,
    pinned              boolean,
    rows_considered     integer NOT NULL DEFAULT 0,
    legs_placed         integer NOT NULL DEFAULT 0,
    rows_culled         jsonb   NOT NULL DEFAULT '{}'::jsonb,   -- reason -> rows (Q5: the row-level ledger itself is not stored)
    sticks              integer NOT NULL DEFAULT 0,
    PRIMARY KEY (set_id, pad_id, formation_blueox),
    FOREIGN KEY (set_id, pad_id) REFERENCES box.location_set_dsu (set_id, pad_id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS box.location_set_well (
    set_id              bigint  NOT NULL REFERENCES box.location_set (set_id) ON DELETE CASCADE,
    api10               text    NOT NULL,
    formation_blueox    text,                              -- the live tag at the pull
    depth_ft            double precision,                  -- depth evidence used; NULL = none (planned survey, permit depth, screened out)
    status              text    NOT NULL CHECK (status IN ('producer', 'preprod')),
    planned             boolean NOT NULL,
    screen              text,                              -- keep / mistag / bad_depth (evidence screen)
    geom                extensions.geometry(LineString, 4326) NOT NULL,
    PRIMARY KEY (set_id, api10)
);
CREATE INDEX IF NOT EXISTS box_location_set_well_geog_gix ON box.location_set_well USING gist ((geom::extensions.geography));

GRANT SELECT ON box.location_set, box.location_stick, box.location_set_dsu, box.location_set_bench, box.location_set_well TO analyst_ro;

-- ---------------------------------------------------------------------------
-- 5. Comments (sql/31 mirrors these at 4b). The depth-confidence ones carry the back-test ratios.
-- ---------------------------------------------------------------------------
COMMENT ON TABLE box.location_set IS
    'BOX sticks generation runs (docs/box_sticks_plan.md phase 4): one row per basin per run of box.sticks. is_record = the set downstream reads '
    '(at most one per basin). inputs = what was read and its digests; cfg = every threshold; backtest = the bars as written with each verdict, '
    'failures included. A set is rebuilt exactly from box.location_set_dsu / _bench / _well + the DSU polygons of dsu_vintage.';
COMMENT ON COLUMN box.location.source IS
    'novi = a Novi Intelligence stick carried by vintage (box.location_source, D73 / D83). box_sticks = our own generated location: identity is '
    '(dsu_vintage, pad_id, formation_blueox, slot_no), carried between sets by co-extent overlap (>= 50 % of the shorter stick within 220 ft, 1:1). '
    'Depth is not part of identity; bench is.';
COMMENT ON COLUMN box.location_stick.tvd_rung IS
    'How the landing depth was reached: direct (same-bench producers within 1 mi) > thickness (carried from an anchor bench by local thickness, to 5 mi) '
    '> bracket (between a bench above and one below) > offset (single neighbour). No error ceiling: weak rungs are placed.';
COMMENT ON COLUMN box.location_stick.tvd_err_median_ft IS
    'Held-out median error (ft) of this rung for this bench. Read it with the 2023-01-01 back-test (707 hidden producers, pull 2026-11-17): carried '
    'depths missed by more than their held-out median: thickness 1.56x (221 pairs), bracket 1.71x (25), offset 1.16x (38). Thickness and bracket fail '
    'the 1.5x bar; stated, the bar stands. Direct rung: 55.1 ft median, 82.6 % within 150 ft (121 pairs). '
    'tvd_err_p90_ft = the same hold-out at P90.';
COMMENT ON COLUMN box.location_stick.second_level_tvd_ft IS
    'Thickness rung only: the neighbouring same-bench wells sit at two levels and this is the other one (flag second_level_nearby). Trust the depth '
    'less: flagged depths miss 87.1 ft (Delaware) / 74.1 ft (Midland) median on the hold-out against 50.0 / 39.2 ft unflagged. It does not say the other '
    'level is right. NULL on the bracket and offset rungs means NOT MEASURED, not "one level".';
COMMENT ON COLUMN box.location_stick.flags IS
    'pinned: rows fixed by existing same-bench wells. two_landings_observed: the DSU''s own wells of this bench land at two levels (one landing is placed). '
    'second_level_nearby: see second_level_tvd_ft. dsu_drilled_across: a U-turn DSU whose own wells run >= 1.3x its longest row (a shapefile artifact; '
    'the stick is kept).';
