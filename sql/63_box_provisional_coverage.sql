-- sql/63 — BOX provisional coverage tier (D105, Michael 2026-10-17)
--
-- "I'd rather have a less robust forecast for AVA and BS2_C than simply null." Benches with too little development history for
-- the D53 / D99 out-of-time test (step 14 / step-15 tuning gate) still get the same analog workup (box_v2, deal-intake config
-- v10: same bench, first production >= 2016, >= 6 months, lateral band), with NO haircut and NO holdout, and the pooled
-- in-sample tuning bias + range disclosed. They are stored under their own coverage value so the distinction lives in the
-- data: coverage = 'covered' keeps meaning VALIDATED for every app, Steven's queries and the gate identities.
--
--   covered_provisional : in-scope bench marked provisional, >= 50 % of the stick inside the record extent, analogs found;
--                         fully described and with volumes exactly like 'covered' (same row constraints).
--
-- Changes (idempotent; the column CHECKs created inline by sql/60 / sql/61 carry generated names, so they are found by
-- definition, dropped and re-added under fixed names):
--   box.pud_forecast          coverage value list + covered / uncovered / inside constraints admit covered_provisional
--   box.pud_forecast_stream   coverage IN (covered, covered_provisional)   (FK (run, location, coverage) unchanged)
--   box.location_analog       coverage IN (covered, covered_provisional)
--   box_econ.box_pud_econ     coverage IN (covered, covered_provisional)   (Steven may price a provisional row; the tier rides along)
--   box.bench_scope           + validation text NOT NULL DEFAULT 'validated' CHECK IN (validated, provisional)
-- Child rows default coverage = 'covered'; a provisional location's stream / analog / econ rows must state it explicitly
-- (the FK to (run_id, location_id, coverage) refuses a mismatch either way).
--
-- Requires sql/54, sql/60, sql/61. Apply with: python -m scripts.apply_box_provisional (explicit "go apply" required).

DO $$
DECLARE
    r record;
BEGIN
    -- 1. drop the generated column CHECKs on coverage (identified by definition) in the four tables
    FOR r IN
        SELECT n.nspname, c.relname, k.conname
        FROM pg_constraint k JOIN pg_class c ON c.oid = k.conrelid JOIN pg_namespace n ON n.oid = c.relnamespace
        WHERE k.contype = 'c'
          AND ((n.nspname = 'box' AND c.relname IN ('pud_forecast', 'pud_forecast_stream', 'location_analog'))
               OR (n.nspname = 'box_econ' AND c.relname = 'box_pud_econ'))
          AND pg_get_constraintdef(k.oid) ~ '^CHECK \(\(?coverage (=|= ANY)'
          AND k.conname NOT LIKE 'box_%_coverage_tier_ck'
    LOOP
        EXECUTE format('ALTER TABLE %I.%I DROP CONSTRAINT %I', r.nspname, r.relname, r.conname);
    END LOOP;
END $$;

ALTER TABLE box.pud_forecast DROP CONSTRAINT IF EXISTS box_pud_forecast_coverage_tier_ck;
ALTER TABLE box.pud_forecast ADD CONSTRAINT box_pud_forecast_coverage_tier_ck CHECK (coverage IN (
    'covered', 'covered_provisional', 'not_covered_emerging', 'not_covered_wcxy', 'not_covered_unvalidated',
    'not_covered_outside_extent', 'not_covered_no_analogs'));

ALTER TABLE box.pud_forecast DROP CONSTRAINT IF EXISTS box_pud_forecast_covered_ck;
ALTER TABLE box.pud_forecast ADD CONSTRAINT box_pud_forecast_covered_ck CHECK (
    coverage NOT IN ('covered', 'covered_provisional')
    OR (search_mode IS NOT NULL AND radius_mi IS NOT NULL AND radius_class IS NOT NULL
        AND coalesce(n_analogs, 0) >= 3 AND planned_spacing_ft IS NOT NULL
        AND spacing_source IS NOT NULL AND completed_lateral_ft IS NOT NULL));

ALTER TABLE box.pud_forecast DROP CONSTRAINT IF EXISTS box_pud_forecast_uncovered_ck;
ALTER TABLE box.pud_forecast ADD CONSTRAINT box_pud_forecast_uncovered_ck CHECK (
    coverage IN ('covered', 'covered_provisional', 'not_covered_no_analogs')
    OR (search_mode IS NULL AND radius_mi IS NULL AND radius_class IS NULL AND n_analogs IS NULL));

ALTER TABLE box.pud_forecast DROP CONSTRAINT IF EXISTS box_pud_forecast_inside_ck;
ALTER TABLE box.pud_forecast ADD CONSTRAINT box_pud_forecast_inside_ck CHECK (
    coverage NOT IN ('covered', 'covered_provisional') OR (inside_extent AND extent_id IS NOT NULL));

ALTER TABLE box.pud_forecast_stream DROP CONSTRAINT IF EXISTS box_pud_forecast_stream_coverage_tier_ck;
ALTER TABLE box.pud_forecast_stream ADD CONSTRAINT box_pud_forecast_stream_coverage_tier_ck CHECK (coverage IN ('covered', 'covered_provisional'));

ALTER TABLE box.location_analog DROP CONSTRAINT IF EXISTS box_location_analog_coverage_tier_ck;
ALTER TABLE box.location_analog ADD CONSTRAINT box_location_analog_coverage_tier_ck CHECK (coverage IN ('covered', 'covered_provisional'));

ALTER TABLE box_econ.box_pud_econ DROP CONSTRAINT IF EXISTS box_pud_econ_coverage_tier_ck;
ALTER TABLE box_econ.box_pud_econ ADD CONSTRAINT box_pud_econ_coverage_tier_ck CHECK (coverage IN ('covered', 'covered_provisional'));

ALTER TABLE box.bench_scope ADD COLUMN IF NOT EXISTS validation text NOT NULL DEFAULT 'validated';
ALTER TABLE box.bench_scope DROP CONSTRAINT IF EXISTS box_bench_scope_validation_ck;
ALTER TABLE box.bench_scope ADD CONSTRAINT box_bench_scope_validation_ck CHECK (validation IN ('validated', 'provisional'));

COMMENT ON COLUMN box.bench_scope.validation IS
    'D105: validated = the frozen analog workup passed its own D53 tuning view and one-time D52 / D99 holdout on this bench; provisional = '
    'too little development history for the out-of-time test, forecast anyway (raw box_v2, no haircut, no holdout) with the pooled in-sample '
    'tuning bias + range disclosed. A provisional bench''s covered PUDs carry coverage = covered_provisional. Michael-owned. See sql/63.';
COMMENT ON TABLE box.pud_forecast IS
    'One row per (run, location) for the whole D67 universe: Novi PUD category (no RES), reconciled remaining_pud / conflict / not_reconciled, on every '
    'box.bench_scope bench. coverage: covered (in-scope bench pool, VALIDATED, >= 50 % of the stick inside the record extent, analogs found); '
    'covered_provisional (same, on a bench_scope.validation = provisional bench - forecast with disclosed in-sample bias, never out-of-time validated, '
    'D105 / sql/63); not_covered_emerging (bench out of scope, D2); not_covered_wcxy (D61); not_covered_unvalidated (in-scope bench the frozen spec was '
    'not accepted on, D60); not_covered_outside_extent (D1); not_covered_no_analogs (fewer than 3 analogs at the 20-mi cap - reported, never hidden). '
    'Not-covered rows carry no forecast and no volumes. Filter coverage = ''covered'' for validated forecasts only; IN (covered, covered_provisional) '
    'for every forecast. See sql/60, sql/63.';
