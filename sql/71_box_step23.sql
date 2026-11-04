-- sql/71 — BOX step 23: the record runs under D150 (continuous proximity factor) and D145 (conflict sticks not drillable)
--
-- AUTHORED AT GATE 23a. Container-validated at 23b. APPLIED LIVE 2026-11-03 at 23c (Michael "Go apply sql/71"): one transaction,
-- 1.8 s, file sha256 644339f6825d58e3 as applied; 0 violating rows on runs 19 / 25 beforehand, 11/11 constraints validated after
-- (docs/box/step23-2026-11-03/live23c/sql71_*.txt). Byte changes to this header only after the apply.
--
-- What sql/65 / sql/63 cannot hold (docs/box/step23-2026-11-03/RECORD_PLAN.md §5):
--   * D150 factor = level x F_rule on EVERY forecast stick. The fitted levels (Delaware 1.046, Midland 1.067) put the factor of
--     an unexposed or lightly exposed stick ABOVE 1. sql/65 caps prox_factor and pud_proximity.factor at 1.
--   * D150 retires D113's words: a forecast stick is level_unexposed / factor_single_parent / factor_multi_parent (it carries a
--     factor whatever its parent count), never 'as_is' (factor 1) or 'haircut' (a table key). D113 rows of runs 19 / 25 stay
--     valid as they are: every constraint below admits the old vocabulary unchanged.
--   * Midland precedent (21a revisions 1 / 5): no_forecast_pattern and no_forecast_spacing, like D114's two, carry coverage
--     not_covered_no_precedent (searched, in-extent, declined).
--   * Midland stick side (21a revision 4): every existing producer is a parent, whatever its months on, so a named parent's
--     age_days can be < 365 (it stays >= 0).
--   * D145 (Midland): a reconciliation CONFLICT stick is not a drillable location: coverage not_covered_conflict, no search, no
--     forecast (box/production.classify).
-- Nothing else changes; no row is rewritten. Idempotent. Requires sql/60, sql/62, sql/63, sql/65, sql/70.
-- Apply with: python -m scripts.load_intel_sf ... run_sql_file('71_box_step23.sql') on "go apply" (the 23b container first).

-- 1. coverage: + not_covered_conflict (D145) ------------------------------------------------------------------------------
ALTER TABLE box.pud_forecast DROP CONSTRAINT IF EXISTS box_pud_forecast_coverage_tier_ck;
ALTER TABLE box.pud_forecast ADD CONSTRAINT box_pud_forecast_coverage_tier_ck CHECK (coverage IN (
    'covered', 'covered_provisional', 'not_covered_emerging', 'not_covered_wcxy', 'not_covered_unvalidated',
    'not_covered_outside_extent', 'not_covered_no_analogs', 'not_covered_no_precedent', 'not_covered_conflict'));
ALTER TABLE box.pud_forecast DROP CONSTRAINT IF EXISTS box_pud_forecast_conflict_ck;
ALTER TABLE box.pud_forecast ADD CONSTRAINT box_pud_forecast_conflict_ck CHECK (
    coverage <> 'not_covered_conflict' OR recon_status = 'conflict');

-- 2. the oil factor may exceed 1 (D150 level); gas / water stay 1 --------------------------------------------------------------
ALTER TABLE box.pud_forecast_stream DROP CONSTRAINT IF EXISTS box_pud_forecast_stream_prox_factor_ck;
ALTER TABLE box.pud_forecast_stream ADD CONSTRAINT box_pud_forecast_stream_prox_factor_ck CHECK (
    prox_factor > 0 AND prox_factor <= 1.5 AND (stream = 'oil' OR prox_factor = 1));

-- 3. box.pud_proximity: D150 outcomes, factor > 1, the D113 rules scoped to the D113 words ---------------------------------
ALTER TABLE box.pud_proximity DROP CONSTRAINT IF EXISTS pud_proximity_outcome_check;
ALTER TABLE box.pud_proximity DROP CONSTRAINT IF EXISTS box_pud_proximity_outcome_ck;
ALTER TABLE box.pud_proximity ADD CONSTRAINT box_pud_proximity_outcome_ck CHECK (outcome IN (
    'as_is_unexposed', 'as_is_single_parent', 'haircut',                                  -- D113 (runs 11-25)
    'level_unexposed', 'factor_single_parent', 'factor_multi_parent',                    -- D150 (step 23)
    'no_forecast_precedent', 'no_forecast_package', 'no_forecast_pattern', 'no_forecast_spacing'));
ALTER TABLE box.pud_proximity DROP CONSTRAINT IF EXISTS pud_proximity_factor_check;
ALTER TABLE box.pud_proximity DROP CONSTRAINT IF EXISTS box_pud_proximity_factor_ck;
ALTER TABLE box.pud_proximity ADD CONSTRAINT box_pud_proximity_factor_ck CHECK (factor > 0 AND factor <= 1.5);
ALTER TABLE box.pud_proximity DROP CONSTRAINT IF EXISTS box_pud_proximity_coverage_ck;
ALTER TABLE box.pud_proximity ADD CONSTRAINT box_pud_proximity_coverage_ck CHECK (
    (outcome LIKE 'no_forecast_%') = (coverage = 'not_covered_no_precedent')
    AND coverage IN ('covered', 'covered_provisional', 'not_covered_no_precedent'));
ALTER TABLE box.pud_proximity DROP CONSTRAINT IF EXISTS box_pud_proximity_as_is_ck;
ALTER TABLE box.pud_proximity ADD CONSTRAINT box_pud_proximity_as_is_ck CHECK (
    outcome NOT IN ('as_is_unexposed', 'as_is_single_parent') OR (factor = 1 AND haircut_key IS NULL AND label IS NULL));
ALTER TABLE box.pud_proximity DROP CONSTRAINT IF EXISTS box_pud_proximity_multi_ck;
ALTER TABLE box.pud_proximity ADD CONSTRAINT box_pud_proximity_multi_ck CHECK (
    outcome NOT IN ('haircut', 'no_forecast_precedent', 'no_forecast_package')
    OR (haircut_key IS NOT NULL AND pair_key IS NOT NULL AND prec_multi IS NOT NULL AND prec_package IS NOT NULL));
ALTER TABLE box.pud_proximity DROP CONSTRAINT IF EXISTS box_pud_proximity_label_ck;
ALTER TABLE box.pud_proximity ADD CONSTRAINT box_pud_proximity_label_ck CHECK ((outcome = 'haircut') = (label IS NOT NULL));
ALTER TABLE box.pud_proximity DROP CONSTRAINT IF EXISTS box_pud_proximity_unexposed_ck;
ALTER TABLE box.pud_proximity ADD CONSTRAINT box_pud_proximity_unexposed_ck CHECK (
    outcome NOT IN ('as_is_unexposed', 'as_is_single_parent', 'haircut') OR ((outcome = 'as_is_unexposed') = (config_class IS NULL)));

-- 4. named parents: every existing producer on the Midland stick side ----------------------------------------------------------
ALTER TABLE box.pud_proximity_parent DROP CONSTRAINT IF EXISTS pud_proximity_parent_age_days_check;
ALTER TABLE box.pud_proximity_parent DROP CONSTRAINT IF EXISTS box_pud_proximity_parent_age_ck;
ALTER TABLE box.pud_proximity_parent ADD CONSTRAINT box_pud_proximity_parent_age_ck CHECK (age_days >= 0);

COMMENT ON COLUMN box.pud_forecast_stream.prox_factor IS
    'Oil multiplier of the PDP-proximity layer (1 on gas / water). D113 runs (11-25): the table factor, <= 1 (1 = as-is). D150 runs '
    '(step 23 on): level x F_rule on every forecast location, level = the basin''s fitted unexposed level (Delaware 1.046, Midland '
    '1.067), so an unexposed location carries the level (> 1). eur = eur_raw x eur_haircut x prox_factor. See sql/65, sql/71.';
COMMENT ON COLUMN box.pud_proximity.outcome IS
    'D113 (runs 11-25): as_is_unexposed / as_is_single_parent / haircut / no_forecast_precedent / no_forecast_package. D150 (step 23 '
    'on): level_unexposed / factor_single_parent / factor_multi_parent (by the D150 counting parents) and the no_forecast_* gates '
    '(D114 precedent + package; Midland also pattern + spacing, 21a revisions 1 / 5). See sql/65, sql/71.';
COMMENT ON COLUMN box.pud_proximity_parent.age_days IS
    'Days on production at the run''s data date. Delaware: >= 365 (D115). Midland stick side: every existing producer counts '
    '(21a revision 4), so >= 0. See sql/71.';
