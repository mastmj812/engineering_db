-- 37: Novi schema drift (2026-07-28) — LastRefracDate on Wells + WellDetails.
--
-- The 2026-07-28 Novi export added "LastRefracDate" (shipped type: date NULL)
-- to both the Wells and WellDetails TSVs — complements the existing Refrac
-- bool. Second additive drift in a week (IsSyntheticApi, sql/36); Novi is
-- actively iterating the bulk export schema. Caught by the load-time drift
-- preflight (etl/novi/load.py::check_schema_drift) before any table was
-- touched, so no tables went stale this time.
--
-- Idempotent: ADD COLUMN IF NOT EXISTS; safe to re-run. Purely additive —
-- no matview reads these yet, so no downstream rebuild is required.

ALTER TABLE raw_novi."Wells"
    ADD COLUMN IF NOT EXISTS "LastRefracDate" date;

ALTER TABLE raw_novi."WellDetails"
    ADD COLUMN IF NOT EXISTS "LastRefracDate" date;
