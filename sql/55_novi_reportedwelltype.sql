-- 55: Novi Wells + WellDetails schema drift (2026-10-06) — ReportedWellType.
--
-- The 2026-10-06 Novi export added one column to both the Wells and the
-- WellDetails TSVs (shipped type: varchar(255) NULL):
--   ReportedWellType  (state-reported well type; live values 'O' / 'G' / NULL)
-- The nightly's reconcile_schema_drift() auto-added it live (GitHub Actions
-- run 37501657889, 2026-10-06 17:13:36 UTC — "Novi schema drift: auto-added
-- raw_novi.Wells.ReportedWellType" and "...WellDetails.ReportedWellType"),
-- so this file is the repo MIRROR of DDL that already exists; it changes
-- nothing on the live DB. sql/02 was regenerated from the 2026-10-09 shipped
-- schema.postgres.sql in this commit (ReportedWellType is the only delta).
--
-- Live column order differs from sql/02 (ALTER appends at the end; Novi ships
-- it after WellType). Harmless: the loader's COPY column list comes from the
-- TSV header, not ordinal position.
--
-- Idempotent: ADD COLUMN IF NOT EXISTS; safe to re-run. Purely additive —
-- no matview reads it yet, so no downstream rebuild is required.

ALTER TABLE raw_novi."Wells"
    ADD COLUMN IF NOT EXISTS "ReportedWellType" varchar(255);

ALTER TABLE raw_novi."WellDetails"
    ADD COLUMN IF NOT EXISTS "ReportedWellType" varchar(255);
