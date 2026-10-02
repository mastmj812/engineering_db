-- =============================================================================
-- 52_box_econ_schema.sql — writable sandbox schema for Steven's economics
-- =============================================================================
-- box_econ holds econ results produced OUTSIDE this stack (Steven's tool) so the
-- apps can screen/color/aggregate on them, the way erebor uses Novi's NPV
-- columns. Nothing in oilgas computes economics; this schema only STORES them.
--
-- Ownership model (ETL never touches box_econ — like narvi.*):
--   box_econ_writer  NOLOGIN group role: USAGE + CREATE on box_econ, plus
--                    membership in analyst_ro (read curated). Writers create
--                    and own their own tables (sandbox phase — no contract DDL
--                    yet; a keyed contract table comes with BOX forecasts).
--   <login>          per-person LOGIN role, created by Michael with a password
--                    (never in the repo), then wired by
--                    scripts/apply_box_econ_schema.py --writer <login>, which
--                    grants box_econ_writer and sets default privileges so
--                    every table the writer creates is readable by analyst_ro
--                    and postgres (apps + agent).
--
-- Not exposed to the Supabase Data API: anon/authenticated get nothing here.
-- Idempotent.
-- =============================================================================

CREATE SCHEMA IF NOT EXISTS box_econ AUTHORIZATION postgres;

DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'box_econ_writer') THEN
        CREATE ROLE box_econ_writer NOLOGIN;
    END IF;
END
$$;

GRANT USAGE, CREATE ON SCHEMA box_econ TO box_econ_writer;
GRANT analyst_ro TO box_econ_writer;

-- Readers: the analyst role sees everything written here.
GRANT USAGE ON SCHEMA box_econ TO analyst_ro;
GRANT SELECT ON ALL TABLES IN SCHEMA box_econ TO analyst_ro;
ALTER DEFAULT PRIVILEGES FOR ROLE postgres IN SCHEMA box_econ
    GRANT SELECT ON TABLES TO analyst_ro;

-- Belt-and-braces: keep the schema off the Data API roles.
REVOKE ALL ON SCHEMA box_econ FROM PUBLIC, anon, authenticated;

COMMENT ON SCHEMA box_econ IS
    'Externally produced economics (Steven) for screening in the apps. Stored, '
    'never computed here; never feeds forecasts. Writers = box_econ_writer members; '
    'ETL and refresh_all() never touch this schema. See sql/52.';
