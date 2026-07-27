-- 36: Novi WellDetails schema drift (2026-07-24) — IsSyntheticApi column.
--
-- The 2026-07-24 Novi export added "IsSyntheticApi" to the WellDetails TSV
-- (Wells has carried it since the sql/02 generation of 2026-05-30). The
-- loader builds its COPY column list from the TSV header, so nightly
-- novi.load has failed since 2026-07-24 with `column "IsSyntheticApi" of
-- relation "WellDetails" does not exist`, leaving WellDetails, WellSpacing,
-- and ForecastWellMonths stale at the 2026-07-23 export.
--
-- Shipped schema declares it `bool NOT NULL`; added nullable here because
-- the table is populated and the raw layer is TRUNCATE+COPY'd nightly, so
-- it is fully populated from the next successful load onward (same additive
-- convention as sql/33 for the Enverus drift).
-- Idempotent: ADD COLUMN IF NOT EXISTS; safe to re-run. Purely additive —
-- no matview reads this column, so no downstream rebuild is required.

ALTER TABLE raw_novi."WellDetails"
    ADD COLUMN IF NOT EXISTS "IsSyntheticApi" bool;
