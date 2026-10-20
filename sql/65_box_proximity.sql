-- sql/65 — BOX PDP-proximity layer (D112-D116, Michael 2026-10-20; study docs/box/prox-2026-10-19)
--
-- A PUD with several depleted parents around it (>= 12 months on production, >= 30 % alongside, inside the class envelope)
-- produces less than BOX's analog forecast says: drilled multi-parent children made 0.75-0.94 of it (walk-forward validated
-- for multi-parent configurations, option (a) of gate 2c). A configuration nobody has drilled has no evidence at all.
--   * multi-parent PUD with drilled precedent  -> oil volumes x the configuration factor (gas / water untouched), D113
--   * multi-parent PUD without precedent       -> no forecast: coverage not_covered_no_precedent, D114
--     (>= 30 drilled multi-parent wells of the bench pair; when the factor <= 0.80, >= 30 drilled PACKAGES)
--   * single-parent / unexposed PUD            -> BOX as-is (factor 1)
--
-- Changes (idempotent):
--   box.pud_forecast          coverage value not_covered_no_precedent; such a row keeps the analog SEARCH provenance (what BOX
--                             would have used) but carries no stream / month / analog rows (the child coverage CHECKs admit only
--                             covered / covered_provisional, so the FK refuses them)
--   box.pud_forecast_stream   + prox_factor (1 except on oil); eur = eur_raw x eur_haircut x prox_factor
--   box.pud_proximity         NEW: one row per forecast-universe PUD of a run that measured proximity: configuration,
--                             outcome, factor, precedent counts, flags, provenance of the table used
--   box.pud_proximity_parent  NEW: the named parents behind each configuration
-- Existing rows are untouched (prox_factor defaults to 1; runs before 11 have no pud_proximity rows).
--
-- Requires sql/60, sql/62, sql/63. Apply with: python -m scripts.apply_box_proximity (explicit "go apply" required).

-- 1. coverage value + the uncovered-row rule ------------------------------------------------------------------------------
ALTER TABLE box.pud_forecast DROP CONSTRAINT IF EXISTS box_pud_forecast_coverage_tier_ck;
ALTER TABLE box.pud_forecast ADD CONSTRAINT box_pud_forecast_coverage_tier_ck CHECK (coverage IN (
    'covered', 'covered_provisional', 'not_covered_emerging', 'not_covered_wcxy', 'not_covered_unvalidated',
    'not_covered_outside_extent', 'not_covered_no_analogs', 'not_covered_no_precedent'));

ALTER TABLE box.pud_forecast DROP CONSTRAINT IF EXISTS box_pud_forecast_uncovered_ck;
ALTER TABLE box.pud_forecast ADD CONSTRAINT box_pud_forecast_uncovered_ck CHECK (
    coverage IN ('covered', 'covered_provisional', 'not_covered_no_analogs', 'not_covered_no_precedent')
    OR (search_mode IS NULL AND radius_mi IS NULL AND radius_class IS NULL AND n_analogs IS NULL));

-- a no-precedent PUD is a fully searched location (inside the extent, >= 3 analogs) that we decline to forecast
ALTER TABLE box.pud_forecast DROP CONSTRAINT IF EXISTS box_pud_forecast_no_precedent_ck;
ALTER TABLE box.pud_forecast ADD CONSTRAINT box_pud_forecast_no_precedent_ck CHECK (
    coverage <> 'not_covered_no_precedent'
    OR (search_mode IS NOT NULL AND coalesce(n_analogs, 0) >= 3 AND inside_extent AND extent_id IS NOT NULL));

-- 2. stream factor ---------------------------------------------------------------------------------------------------------
ALTER TABLE box.pud_forecast_stream ADD COLUMN IF NOT EXISTS prox_factor double precision NOT NULL DEFAULT 1;
ALTER TABLE box.pud_forecast_stream DROP CONSTRAINT IF EXISTS box_pud_forecast_stream_prox_factor_ck;
ALTER TABLE box.pud_forecast_stream ADD CONSTRAINT box_pud_forecast_stream_prox_factor_ck CHECK (
    prox_factor > 0 AND prox_factor <= 1 AND (stream = 'oil' OR prox_factor = 1));
ALTER TABLE box.pud_forecast_stream DROP CONSTRAINT IF EXISTS box_pud_forecast_stream_eur_ck;
ALTER TABLE box.pud_forecast_stream ADD CONSTRAINT box_pud_forecast_stream_eur_ck CHECK (
    abs(eur - eur_raw * eur_haircut * prox_factor) <= 1e-6 * eur);

-- 3. per-PUD proximity record ----------------------------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS box.pud_proximity (
    run_id              bigint   NOT NULL,
    location_id         bigint   NOT NULL,
    coverage            text     NOT NULL,
    config_class        text     CHECK (config_class IN ('same', 'topfill', 'underfill', 'mixed')),
    n_same              smallint NOT NULL CHECK (n_same >= 0),
    n_topfill           smallint NOT NULL CHECK (n_topfill >= 0),
    n_underfill         smallint NOT NULL CHECK (n_underfill >= 0),
    n_parents_total     smallint NOT NULL CHECK (n_parents_total >= 0),
    flanked_same        boolean  NOT NULL DEFAULT false,
    flanked_topfill     boolean  NOT NULL DEFAULT false,
    flanked_underfill   boolean  NOT NULL DEFAULT false,
    outcome             text     NOT NULL CHECK (outcome IN ('as_is_unexposed', 'as_is_single_parent', 'haircut',
                                                             'no_forecast_precedent', 'no_forecast_package')),
    factor              double precision NOT NULL CHECK (factor > 0 AND factor <= 1),
    haircut_key         text,
    pair_key            text,
    prec_multi          integer  CHECK (prec_multi >= 0),
    prec_package        integer  CHECK (prec_package >= 0),
    label               text     CHECK (label IN ('validated_with_exception')),
    n_permit_parents    smallint NOT NULL DEFAULT 0 CHECK (n_permit_parents >= 0),
    n_recent_producers  smallint NOT NULL DEFAULT 0 CHECK (n_recent_producers >= 0),
    table_ref           text     NOT NULL,
    PRIMARY KEY (run_id, location_id),
    FOREIGN KEY (run_id, location_id, coverage) REFERENCES box.pud_forecast (run_id, location_id, coverage) ON DELETE CASCADE,
    -- the coverage the record carries follows the outcome
    CONSTRAINT box_pud_proximity_coverage_ck CHECK (
        (outcome IN ('no_forecast_precedent', 'no_forecast_package')) = (coverage = 'not_covered_no_precedent')
        AND (coverage IN ('covered', 'covered_provisional', 'not_covered_no_precedent'))),
    -- as-is rows carry no factor and no key; multi-parent rows carry the full lookup
    CONSTRAINT box_pud_proximity_as_is_ck CHECK (
        outcome NOT IN ('as_is_unexposed', 'as_is_single_parent') OR (factor = 1 AND haircut_key IS NULL AND label IS NULL)),
    CONSTRAINT box_pud_proximity_multi_ck CHECK (
        outcome IN ('as_is_unexposed', 'as_is_single_parent')
        OR (haircut_key IS NOT NULL AND pair_key IS NOT NULL AND prec_multi IS NOT NULL AND prec_package IS NOT NULL)),
    CONSTRAINT box_pud_proximity_label_ck CHECK ((outcome = 'haircut') = (label IS NOT NULL)),
    CONSTRAINT box_pud_proximity_unexposed_ck CHECK ((outcome = 'as_is_unexposed') = (config_class IS NULL))
);
CREATE INDEX IF NOT EXISTS box_pud_proximity_outcome_ix ON box.pud_proximity (run_id, outcome);

CREATE TABLE IF NOT EXISTS box.pud_proximity_parent (
    run_id              bigint   NOT NULL,
    location_id         bigint   NOT NULL,
    api10               text     NOT NULL CHECK (api10 ~ '^[0-9]{10}$'),
    cls                 text     NOT NULL CHECK (cls IN ('same', 'topfill', 'underfill')),
    parent_bench        text     NOT NULL,
    dv_ft               double precision NOT NULL CHECK (dv_ft >= 0),
    dh_ft               double precision NOT NULL CHECK (dh_ft >= 0),
    dxy_ft              double precision NOT NULL,
    overlap             double precision NOT NULL CHECK (overlap > 0 AND overlap <= 1),
    age_days            integer  NOT NULL CHECK (age_days >= 365),
    permit              boolean  NOT NULL DEFAULT false,
    PRIMARY KEY (run_id, location_id, api10),
    FOREIGN KEY (run_id, location_id) REFERENCES box.pud_proximity (run_id, location_id) ON DELETE CASCADE
);
CREATE INDEX IF NOT EXISTS box_pud_proximity_parent_api10_ix ON box.pud_proximity_parent (api10);

GRANT SELECT ON box.pud_proximity, box.pud_proximity_parent TO analyst_ro;

-- 4. comments -------------------------------------------------------------------------------------------------------------
COMMENT ON COLUMN box.pud_forecast_stream.prox_factor IS
    'D113 PDP-proximity factor on the OIL stream (1 on gas / water and on every PUD that is not multi-parent): the configuration haircut from '
    'box.pud_proximity.factor, applied as a uniform scale to the oil monthly volumes, eur and cum12 / cum24 (Di / b unchanged, params untouched). '
    'eur = eur_raw x eur_haircut x prox_factor. See sql/65.';
COMMENT ON TABLE box.pud_proximity IS
    'D112-D116 (study docs/box/prox-2026-10-19): one row per forecast-universe PUD of a run that measured PDP proximity. Parents = existing '
    'producing horizontals >= 12 months on production at the run''s data date, >= 30 % alongside the PUD stick, inside the class envelope '
    '(same pool 1,400 ft hz; topfill 800 ft vt / 1,400 ft hz; underfill 500 ft vt / 1,400 ft hz); no shielding exemption; permit-round producer '
    'TVDs counted and flagged. outcome: as_is_unexposed / as_is_single_parent (BOX as-is, factor 1); haircut (multi-parent with drilled precedent: '
    'oil x factor, label validated_with_exception - the pre-registered walk-forward failed as written, multi-parent cells held within +-5 %, '
    'to be confirmed on the 2026 prospective cohort); no_forecast_precedent (< 30 drilled multi-parent wells of the bench pair) and '
    'no_forecast_package (factor <= 0.80 and < 30 drilled packages) -> coverage not_covered_no_precedent. factor = what the configuration''s '
    'cum-24 table gives (stored on no-forecast rows too). table_ref = sha256 of the haircut table + the pre-registration commit. See sql/65.';
COMMENT ON TABLE box.pud_proximity_parent IS
    'The named parents behind box.pud_proximity: one row per counted parent (class, bench, vertical / horizontal gap ft, signed offset ft '
    '+ = left of the PUD stick''s heading, share of the PUD stick alongside, age at the data date, permit-round TVD flag). See sql/65.';
COMMENT ON TABLE box.pud_forecast IS
    'One row per (run, location) for the whole D67 universe: Novi PUD category (no RES), reconciled remaining_pud / conflict / not_reconciled, on every '
    'box.bench_scope bench. coverage: covered (in-scope bench pool, VALIDATED, >= 50 % of the stick inside the record extent, analogs found); '
    'covered_provisional (same, on a bench_scope.validation = provisional bench - forecast with disclosed in-sample bias, never out-of-time validated, '
    'D105 / sql/63); not_covered_emerging (bench out of scope, D2); not_covered_wcxy (D61); not_covered_unvalidated (in-scope bench the frozen spec was '
    'not accepted on, D60); not_covered_outside_extent (D1); not_covered_no_analogs (fewer than 3 analogs at the 20-mi cap - reported, never hidden); '
    'not_covered_no_precedent (a searched in-extent PUD whose PDP-proximity configuration has no drilled precedent, D114 / sql/65 - search provenance '
    'kept, no forecast). Not-covered rows carry no forecast and no volumes. Filter coverage = ''covered'' for validated forecasts only; '
    'IN (covered, covered_provisional) for every forecast. See sql/60, sql/63, sql/65.';
