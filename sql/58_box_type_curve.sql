-- =============================================================================
-- 58_box_type_curve.sql — BOX (Blue Ox) type-curve schema, step 5d: curves, members, risk factors
-- =============================================================================
-- docs/box_type_curves_plan.md §4.2 / §5 step 5d. App-owned like the rest of schema box (sql/54):
-- the ETL and refresh_all() never touch it. Writer = scripts/box_tc_record.py --store (postgres,
-- session pooler); apps read via analyst_ro.
--
--   box.type_curve   one row per (TC area, stream, version): the curve of record = the cohort MEAN per
--                    1,000 ft (D32), fitted by the shared engine (blueox-boxfit, D15). Oil / water =
--                    ramp + modified-hyperbolic Arps, nominal Di (rule 1), each stream on its own Di
--                    cap (D38); gas = GOR ratio mode vs cumulative oil (D30: ln R = alpha + beta * Np).
--                    The stored params are the AS-BUILT (mixed-scenario) cohort curve; ref_mult turns
--                    it into the reference-scenario curve (D43 uniform scale: qo and qi x ref_mult,
--                    Di / b unchanged). Relaxation ladder stamp per row (D10 / D37: rung 3 never
--                    emitted).
--   box.tc_member    the wells behind each curve: one row per (curve, well); included = the well
--                    carries a fit for the stream (n_wells = count of included rows). Carries the BOX
--                    pooled-bench scenario (D42) and the factor used to normalise it to the reference.
--   box.risk_factor  development-scenario factors of record (D41-D47): Poisson PML (D47) vs the
--                    reference codev_stack without a same-bench parent, location + vintage FE, 90 %
--                    cluster-bootstrap CI over 3-mi blocks; same-pool parents = lateral infill (D42);
--                    each row stamps its ladder rung (D45: 1 pair n >= 30 -> 2 class in bench ->
--                    3 class across benches). Oil and water = cum-12 factors applied as a uniform
--                    scale (D43); gas = a GOR-level factor through alpha (D46), on top of oil's factor.
--
-- Additive vs the §4.2 sketch: statistic, mode, relaxation_label, thin, eur_per_kft, cum12_kft,
-- ref_mult, engine_sha, data_asof, is_record, created_* on type_curve; infill / factor / weight /
-- lateral_ft on tc_member; metric, level, term, estimate + CI, rung, n_basis, estimator,
-- pud_applicable, params, is_record on risk_factor.
--
-- Requires sql/54 (schema box) + sql/57 (box.tc_area). No geometry (no spatial index needed). Not
-- exposed to the Supabase Data API. Idempotent.
-- =============================================================================

CREATE TABLE IF NOT EXISTS box.type_curve (
    tc_id               bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    area_id             bigint  NOT NULL REFERENCES box.tc_area (area_id),
    version             integer NOT NULL CHECK (version >= 1),
    stream              text    NOT NULL CHECK (stream IN ('oil', 'gas', 'water')),
    statistic           text    NOT NULL DEFAULT 'mean' CHECK (statistic = 'mean'),
    mode                text    NOT NULL CHECK (mode IN ('arps', 'ratio')),
    relaxation_step     smallint NOT NULL CHECK (relaxation_step IN (1, 2, 4, 5)),
    relaxation_label    text    NOT NULL,
    thin                boolean NOT NULL DEFAULT false,
    n_wells             integer NOT NULL CHECK (n_wells >= 1),
    anchors             jsonb   NOT NULL DEFAULT '{}'::jsonb,
    params              jsonb   NOT NULL,
    eur_per_kft         double precision NOT NULL CHECK (eur_per_kft > 0),
    cum12_kft           double precision,
    ref_mult            double precision CHECK (ref_mult > 0),
    fit_meta            jsonb   NOT NULL DEFAULT '{}'::jsonb,
    engine_sha          text    NOT NULL,
    data_asof           date    NOT NULL,
    generated_from_run  text,
    is_record           boolean NOT NULL DEFAULT false,
    created_at          timestamptz NOT NULL DEFAULT now(),
    created_by          text    NOT NULL DEFAULT current_user,
    CONSTRAINT box_type_curve_mode_ck CHECK ((stream = 'gas') = (mode = 'ratio')),
    CONSTRAINT box_type_curve_thin_ck CHECK (thin OR n_wells >= 10)
);

CREATE UNIQUE INDEX IF NOT EXISTS box_type_curve_version_uq ON box.type_curve (area_id, version, stream);
CREATE UNIQUE INDEX IF NOT EXISTS box_type_curve_record_uq  ON box.type_curve (area_id, stream) WHERE is_record;

CREATE TABLE IF NOT EXISTS box.tc_member (
    tc_id           bigint  NOT NULL REFERENCES box.type_curve (tc_id) ON DELETE CASCADE,
    api10           text    NOT NULL CHECK (api10 ~ '^[0-9]{10}$'),
    included        boolean NOT NULL,
    drop_reason     text,
    lateral_ft      double precision,
    dev_scenario    text,
    parent_bench    text,
    infill          boolean,
    factor          double precision,
    weight          double precision,
    PRIMARY KEY (tc_id, api10),
    CONSTRAINT box_tc_member_drop_ck CHECK (included OR drop_reason IS NOT NULL)
);

CREATE INDEX IF NOT EXISTS box_tc_member_api10_ix ON box.tc_member (api10);

CREATE TABLE IF NOT EXISTS box.risk_factor (
    risk_factor_id      bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    version             integer NOT NULL CHECK (version >= 1),
    basin               text    NOT NULL,
    bench               text    NOT NULL,
    stream              text    NOT NULL CHECK (stream IN ('oil', 'gas', 'water')),
    metric              text    NOT NULL,
    level               text    NOT NULL CHECK (level IN ('reference', 'pair', 'class', 'basin_class')),
    term                text    NOT NULL,
    dev_scenario        text    NOT NULL,
    parent_bench        text,
    estimate            double precision,
    ci_lo               double precision,
    ci_hi               double precision,
    n_pairs             integer NOT NULL CHECK (n_pairs >= 0),
    n_clusters          integer,
    factor              double precision NOT NULL CHECK (factor > 0),
    rung                smallint NOT NULL CHECK (rung IN (0, 1, 2, 3)),
    rung_label          text    NOT NULL,
    n_basis             integer NOT NULL CHECK (n_basis >= 0),
    applies_to          text    NOT NULL DEFAULT 'both' CHECK (applies_to IN ('eur', 'qi', 'both')),
    estimator           text    NOT NULL DEFAULT 'ppml' CHECK (estimator IN ('ppml', 'ols')),
    pud_applicable      boolean NOT NULL DEFAULT true,
    params              jsonb   NOT NULL DEFAULT '{}'::jsonb,
    generated_from_run  text,
    is_record           boolean NOT NULL DEFAULT false,
    created_at          timestamptz NOT NULL DEFAULT now(),
    created_by          text    NOT NULL DEFAULT current_user,
    CONSTRAINT box_risk_factor_ref_ck CHECK ((level = 'reference') = (rung = 0))
);

CREATE UNIQUE INDEX IF NOT EXISTS box_risk_factor_version_uq ON box.risk_factor (version, basin, bench, stream, level, term);
CREATE UNIQUE INDEX IF NOT EXISTS box_risk_factor_record_uq  ON box.risk_factor (basin, bench, stream, level, term) WHERE is_record;

GRANT SELECT ON box.type_curve, box.tc_member, box.risk_factor TO analyst_ro;

COMMENT ON TABLE box.type_curve IS
    'BOX type curves (plan step 5, D10/D15/D30/D32/D38-D40): one row per TC area of record x stream x version. Curve of record = the cohort MEAN '
    'per 1,000 ft of lateral (labelled mean, never P50) of the members'' peak_ramp-aligned per-well forecasts, fitted by blueox-boxfit @ engine_sha. '
    'Oil / water: ramp + modified-hyperbolic Arps, Di NOMINAL per year, own Di cap per stream (oil 4.0, water 12.0), Df 0.08 (Delaware). Gas: ratio mode '
    'ln R = alpha + beta * Np (R mcf/bbl, Np cumulative oil bbl per 1,000 ft) on the oil curve; a location''s local 12-mo GOR shifts alpha (D30). '
    'params = the AS-BUILT mixed-scenario cohort curve; reference-scenario curve = qo and qi x ref_mult (D43 uniform scale). EUR = raw 50-yr integral '
    '(no economic limit). Monthly volumes are exact per-month integrals of params (D39). See sql/58.';
COMMENT ON COLUMN box.type_curve.params IS
    'Arps rows: qo / qi (calendar-day rate per 1,000 ft at the ramp start / peak), peak_index_months, Di_nominal (/yr), Di_eff_1yr, b, Df. '
    'Ratio row (gas): alpha, beta (per bbl/kft of cumulative oil), sub_mode, ratio units mcf/bbl.';
COMMENT ON COLUMN box.type_curve.ref_mult IS
    'Reference-scenario multiplier (D43): sum(w/f)/sum(w) over the included members, w = actual cum-12 per 1,000 ft, f = the member''s factor of record '
    '(box.risk_factor, same stream). NULL for gas: the gas level is set per location (D30 local GOR + D46 factor).';
COMMENT ON COLUMN box.type_curve.relaxation_step IS
    'D10 ladder rung that built the curve: 1 strict, 2 relax lateral, 4 borrow neighbouring areas, 5 parent bench. 3 (relax vintage) is retired (D37) and refused.';
COMMENT ON COLUMN box.type_curve.fit_meta IS
    'Fit diagnostics: r2, rule-6 reconcile (exact months vs stored), trapezoid gap, cum-6/12/24 per kft, P50 fit (diagnostic), curve vs actual cohort mean cum-12/24.';
COMMENT ON TABLE box.tc_member IS
    'Wells behind each BOX type curve (one row per curve x well). included = the well has a fit for the curve''s stream; n_wells on box.type_curve = included rows. '
    'dev_scenario / parent_bench / infill = the BOX pooled-bench scenario (D42: same-pool vertical parents count as lateral infill); factor = the risk factor of record '
    'used for ref_mult; weight = actual cum-12 per 1,000 ft. See sql/58.';
COMMENT ON TABLE box.risk_factor IS
    'BOX development-scenario factors of record (D41-D47). Estimator Poisson PML (ratio of arithmetic means), location FE (TC area; 5-mi block where a bench has no areas) '
    '+ first-prod-year FE, reference = codev_stack with no same-bench parent (level reference, factor 1), 90 % cluster-bootstrap CI over 3-mi blocks. '
    'estimate = the term''s own estimate; factor = the factor of record after the D45 ladder (rung 1 pair n >= 30, 2 class in bench, 3 class across benches; '
    'n_basis = wells behind the factor used). Oil / water metric = cum-12 per 1,000 ft, applied as a uniform scale of the reference curve (D43, applies_to both). '
    'Gas metric = 12-mo GOR / the D30 local level, applied through alpha on top of the oil factor (D46). Factors combine: pair x infill. '
    'pud_applicable = false for standalone (scoring actual wells only; an unparented PUD gets the reference, D44). bench ''*'' = pooled across benches. See sql/58.';
