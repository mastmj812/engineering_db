-- =============================================================================
-- 80 — retire the three relations that made Novi sticks usable as locations,
--      and the Novi vintage date PER BASIN  (BOX sticks phase 8, step 3)
--
-- docs/box_sticks_plan.md, phase 8 (Michael, 2026-11-25, "Yes, all five"). Since
-- the BOX sticks cutover (2026-11-24) the undrilled locations of erebor, narvi
-- and deal-intake are BOX sticks; Novi Intelligence is comparison only. Three
-- matviews had no comparison role left:
--
--   curated.novi_stick_locations  (sql/78)  the Novi sticks in the old erebor shape
--   curated.intel_pdp_support     (sql/30)  offset-PDP support per Novi stick
--                                           (100 of the 111 rebuild minutes of a reload)
--   curated.net_new_pdp           (sql/25)  wells online after the vintage with no Novi stick
--
-- Checked on live before the drop (2026-11-25): nothing depends on them but
-- novi_stick_locations -> intel_pdp_support; no code reads them for output
-- (deal-intake's last read moved to curated.intel_locations, PR 285); the land
-- team's role (analyst_ro) has never queried one (pg_stat_statements since
-- 2026-10-20). No CASCADE below: a dependent nobody knew of makes this file FAIL
-- rather than disappear. sql/25, sql/30 and sql/78 are tombstones — never re-run.
-- curated.pdp_support_for_geom (sql/48), the score of record, is untouched.
--
-- PART 2. curated.intel_vintage_date() (sql/29) is ONE date, the newest report
-- loaded. The basins now reload on their own schedule (Delaware 2026Q3, Midland
-- 2026Q4 since 2026-11-25), so the drift / phantom split of sql/68 reads the date
-- of the stick's OWN basin from the function below. The no-argument function
-- stays for the apps that print one vintage date.
--
-- IDEMPOTENT. scripts/apply_reconciled_inventory runs this file before sql/68
-- (sql/68 calls the function), so a reload or a reprovision always has it.
-- Apply on live: python -m scripts.apply_retire_novi_sticks [--go]
-- =============================================================================

-- ---- Part 1: the retired matviews (order: the reader first) ------------------
DROP MATERIALIZED VIEW IF EXISTS curated.novi_stick_locations;
DROP MATERIALIZED VIEW IF EXISTS curated.intel_pdp_support;
DROP MATERIALIZED VIEW IF EXISTS curated.net_new_pdp;

-- ---- Part 2: the loaded Novi vintage per basin --------------------------------
-- Same quarter-end formula as curated.intel_vintage_date() (sql/29): '2026Q3' ->
-- 2026-09-30. curated.intel_locations holds one report per basin (the loaded one).
CREATE OR REPLACE FUNCTION curated.intel_vintage_date_by_basin()
RETURNS TABLE (basin text, report_version text, vintage_date date)
LANGUAGE sql STABLE AS $$
    SELECT il.basin::text,
           max(il.report_version)::text,
           max((make_date(substring(il.report_version, 1, 4)::int,
                          substring(il.report_version, 6, 1)::int * 3, 1)
                + interval '1 month' - interval '1 day')::date)
    FROM curated.intel_locations il
    GROUP BY il.basin
$$;

COMMENT ON FUNCTION curated.intel_vintage_date_by_basin() IS
'Loaded Novi Intelligence vintage per basin: basin, report_version, vintage_date (the quarter end, e.g. 2026Q3 -> 2026-09-30; same formula as curated.intel_vintage_date(), which returns only the newest across basins). The basins reload on their own schedule, so sql/68 splits realized_drift / realized_phantom at the date of the stick''s own basin. Comparison only (BOX sticks are the locations).';
