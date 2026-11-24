-- =============================================================================
-- 79 — box.pud_forecast accepts a run on BOX sticks  (docs/box_sticks_plan.md, phase 6)
--
-- A BOX forecast run whose locations are the record BOX stick set (not Novi sticks)
-- writes three values the constraints of sql/60 and sql/71 do not allow yet:
--
--   * recon_status: the NIGHTLY reconciliation status of a BOX stick
--     (curated.box_location_status, sql/74): open / permitted / pending / conflict,
--     and 'crowded' when the nightly's crowded flag is set. A Novi-stick run keeps
--     remaining_pud / conflict / not_reconciled (sql/68). A producing BOX stick is
--     never a row of a run.
--   * spacing_source 'generator': the planned spacing is the one the stick was
--     placed at (box.location_stick.spacing_ft), not the D64 nearest-neighbour guess.
--   * not_covered_conflict on a 'crowded' stick as well as a 'conflict' one
--     (decision 1 of 2026-11-23: neither is a drillable location, in either basin).
--
-- Three CHECK constraints are replaced by wider ones. No row is rewritten and no
-- existing row can fail: every new constraint admits every value the old one did.
-- box.* is app-owned (the BOX batch); the nightly ETL never writes it.
--
-- DEPENDS ON: sql/60, sql/63, sql/71.
-- RUN:  python -m scripts.apply_box_pud_forecast_box_sticks            (rehearsal: rolled back)
--       python -m scripts.apply_box_pud_forecast_box_sticks --go       (explicit go only)
-- Idempotent.
-- =============================================================================

-- 1. recon_status (sql/60's inline CHECK is named by PostgreSQL: pud_forecast_recon_status_check)
ALTER TABLE box.pud_forecast DROP CONSTRAINT IF EXISTS pud_forecast_recon_status_check;
ALTER TABLE box.pud_forecast DROP CONSTRAINT IF EXISTS box_pud_forecast_recon_status_ck;
ALTER TABLE box.pud_forecast ADD CONSTRAINT box_pud_forecast_recon_status_ck CHECK (recon_status IN (
    'remaining_pud', 'conflict', 'not_reconciled',                 -- a Novi stick (sql/68)
    'open', 'permitted', 'pending', 'crowded'));                   -- a BOX stick (sql/74); 'conflict' and 'not_reconciled' are shared

-- 2. spacing_source
ALTER TABLE box.pud_forecast DROP CONSTRAINT IF EXISTS pud_forecast_spacing_source_check;
ALTER TABLE box.pud_forecast DROP CONSTRAINT IF EXISTS box_pud_forecast_spacing_source_ck;
ALTER TABLE box.pud_forecast ADD CONSTRAINT box_pud_forecast_spacing_source_ck CHECK (
    spacing_source IN ('neighbour_gap', 'default_880', 'generator'));

-- 3. not_covered_conflict: a conflict stick (D145) or a crowded BOX stick
ALTER TABLE box.pud_forecast DROP CONSTRAINT IF EXISTS box_pud_forecast_conflict_ck;
ALTER TABLE box.pud_forecast ADD CONSTRAINT box_pud_forecast_conflict_ck CHECK (
    coverage <> 'not_covered_conflict' OR recon_status IN ('conflict', 'crowded'));

COMMENT ON COLUMN box.pud_forecast.recon_status IS
    'Reconciliation status of the location when the run was built. Run on Novi sticks (through runs 30 / 32): remaining_pud / conflict / not_reconciled (curated.reconciled_inventory, sql/68). Run on BOX sticks: the nightly status of the stick (curated.box_location_status, sql/74): open / permitted / pending / conflict, crowded when the crowded flag was set, not_reconciled when the nightly had not judged it. conflict and crowded BOX sticks are not_covered_conflict; a producing stick is not in the run.';
COMMENT ON COLUMN box.pud_forecast.spacing_source IS
    'Where planned_spacing_ft comes from. neighbour_gap / default_880: the D64 nearest same-bench neighbour of a Novi stick, or 880 ft when it has none. generator: the spacing a BOX stick was placed at (box.location_stick.spacing_ft).';
COMMENT ON COLUMN box.pud_forecast.stick_id IS
    'The location''s stick id as the apps know it (UNIQUE per run). Run on Novi sticks: the Novi stick_id. Run on BOX sticks: the same number as location_id (10,000,001 and up).';
