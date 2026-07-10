-- =============================================================================
-- 22 — curated.erebor_locations  (erebor display spine: §6 PDP-from-curated)
--
-- erebor's map/gun-barrel/selection read this instead of curated.intel_locations.
-- It flips the spine per §6: PUD/RES (the forward inventory) come from Novi
-- Intelligence; PDP (what physically EXISTS) comes from curated.wells — the
-- accurate, current, more-complete system of record — NOT the stale, error-prone
-- novi_intel PDP layer (which only remains as a reconciliation-QC input).
--
-- MATERIALIZED (was a plain VIEW through 2026-06). The view re-ran a 7-way join
-- (intel_locations + intel_formation_blueox + reconciled_inventory UNION ALL
-- wells_enriched + net_new_pdp) on EVERY map tile. Against hosted Postgres
-- (Supabase, us-east-1) that was ~390-650 ms/tile of pure join cost, dozens of
-- tiles per pan. Materializing collapses it to a single GiST/btree-indexed scan
-- (~40-75 ms/tile, matching curated.intel_locations). See
-- docs/erebor_locations_materialization.md for the measured before/after.
--
-- Two disjoint arms UNION ALL'd (unchanged from the view):
--   * PUD/RES  -> curated.intel_locations + curated.intel_formation_blueox
--   * PDP      -> curated.wells_enriched (producing) + curated.net_new_pdp
--
-- PDP rows carry display columns (geom / formation_blueox / tvd / operator) and
-- NULL for Novi-only econ (npv/pv/eur/prices) — PDP is producing context, not
-- risked inventory value. stick_id for PDP is -(api10) so it never collides with
-- a Novi stick_id and the frontend's promoteId selection still works. pad_name is
-- NULL -> the gun-barrel's existing spatial DSU-pad assignment resolves it.
--
-- stick_id is UNIQUE across both arms (Novi ids are positive, PDP ids are
-- -(api10); verified 0 dupes / 0 nulls over 262,581 rows) -> a UNIQUE index makes
-- REFRESH ... CONCURRENTLY possible, so the nightly refresh never blocks the app.
--
-- REFRESH ORCHESTRATION (two cadences — see the docs file):
--   * NIGHTLY  : appended to curated.refresh_all() (sql/06). The PDP arm
--     (wells_enriched) changes nightly as wells come online; CONCURRENTLY refresh
--     picks them up after wells/producing_reference/formation_blueox_tvd refresh.
--   * QUARTERLY: the Novi reload DROPs curated.intel_locations CASCADE, which
--     drops THIS matview too. The intel/reconciliation rebuild sequence must end
--     by re-running this file (scripts/apply_erebor_locations.py) to recreate it
--     WITH DATA + indexes.
--
-- DEPENDS ON: curated.intel_locations (sql/12), curated.intel_formation_blueox
--   (sql/19), curated.wells_enriched (sql/06), curated.reconciled_inventory
--   (sql/21), curated.net_new_pdp (sql/25), curated.intel_pdp_support (sql/30 —
--   the offset-support scores on the PUD/RES arm; must be built BEFORE this file,
--   so apply_intel_pdp_support precedes apply_erebor_locations in the runbook).
-- Idempotent: type-aware drop (handles the one-time VIEW -> MATERIALIZED VIEW
-- transition and re-runs) then CREATE ... WITH DATA.
-- =============================================================================


-- Type-aware drop: IF EXISTS does NOT suppress a wrong-object-type error, so a
-- bare DROP MATERIALIZED VIEW would fail while the object is still the old VIEW
-- (and DROP VIEW would fail once it is a matview). Branch on relkind.
DO $$
BEGIN
    IF EXISTS (
        SELECT 1 FROM pg_class c
        JOIN pg_namespace n ON n.oid = c.relnamespace
        WHERE n.nspname = 'curated' AND c.relname = 'erebor_locations' AND c.relkind = 'v'
    ) THEN
        DROP VIEW curated.erebor_locations CASCADE;
    END IF;
END $$;

DROP MATERIALIZED VIEW IF EXISTS curated.erebor_locations CASCADE;


CREATE MATERIALIZED VIEW curated.erebor_locations AS
-- ---- PUD / RES: the Novi forward inventory ----
SELECT
    il.stick_id,
    il.unique_id,
    il.category,
    il.basin,
    il.formation,
    fb.formation_blueox,
    fb.basin_blueox,
    fb.formation_blueox_source,
    -- §6 reconciliation tag (curated.reconciled_inventory, sql/21): PUDs carry
    -- realized_drift / realized_phantom / remaining_pud / conflict; RES has no
    -- row -> NULL.
    ri.status                          AS recon_status,
    -- Novi PUD-quality depletion tier (Tier-1..4; Tier-4 = offset-depleted /
    -- drained). Drives the map's depletion filter + color mode. RES/PUD only;
    -- PDP arm is NULL (producing wells aren't scored).
    il.deplet_t,
    il.operator,
    il.pad_name,
    il.tvd,
    il.ll_ft,
    il.npv5, il.npv10, il.npv15, il.npv20, il.npv25,
    il.pv5,  il.pv10,  il.pv15,  il.pv20,  il.pv25,
    il.oil_eur, il.gas_eur,
    il.wti_price, il.hh_price, il.ngl_price, il.wti_diff, il.hh_diff,
    -- ---- PDP offset-support score family (curated.intel_pdp_support, sql/30) ----
    -- Refines the raw Novi PUD population into a realistic developable set — the
    -- land team's leasing apps consume THIS layer directly, so the FULL family is
    -- carried and filterable here (not a two-column subset). A VERIFIABILITY
    -- screen, not a quality screen: pair with deplet_t. See per-column COMMENTs
    -- below for the qualifying-PDP gate + 0/NULL semantics. PDP arm is NULL (N/A).
    sup.pdp_count_1mi, sup.pdp_count_3mi, sup.pdp_count_5mi,
    sup.dist_nearest_ft, sup.dist_3rd_nearest_ft,
    sup.support_lateral_ft_5mi, sup.n_offsets_5mi,
    sup.offset_median_eur_ft,
    round(sup.inflation_ratio::numeric, 2)::double precision AS inflation_ratio,
    il.wellstick_geom
FROM curated.intel_locations il
LEFT JOIN curated.intel_formation_blueox fb ON fb.stick_id = il.stick_id
LEFT JOIN curated.reconciled_inventory ri ON ri.stick_id = il.stick_id
LEFT JOIN curated.intel_pdp_support sup ON sup.stick_id = il.stick_id
WHERE il.category IN ('PUD', 'RES')

UNION ALL

-- ---- PDP: producing curated HORIZONTAL wells (what exists) ----
-- wells_enriched carries formation_blueox + is_horizontal. Horizontal-only so
-- the layer matches the Novi laterals (curated.wells also holds shallow vertical
-- conventional producers — Grayburg/San Andres — that don't belong on a
-- lateral map / gun-barrel cross-section).
SELECT
    -(we.api10::bigint)                AS stick_id,    -- never collides with Novi ids
    we.api10                           AS unique_id,
    'PDP'::text                        AS category,
    we.basin_blueox                    AS basin,
    we.formation,
    we.formation_blueox,
    we.basin_blueox,
    we.formation_blueox_source,
    -- PDP reconciliation tag: 'net_new_pdp' if this producer realized no PUD
    -- (curated.net_new_pdp, sql/25) — Novi missed the location; else NULL.
    CASE WHEN nn.api10 IS NOT NULL THEN 'net_new_pdp' END AS recon_status,
    NULL::text                         AS deplet_t,   -- producing wells aren't depletion-scored
    we.current_operator                AS operator,
    NULL::text                         AS pad_name,
    we.tvd_ft                          AS tvd,
    we.lateral_length_ft::double precision AS ll_ft,
    NULL::double precision AS npv5, NULL::double precision AS npv10,
    NULL::double precision AS npv15, NULL::double precision AS npv20,
    NULL::double precision AS npv25,
    NULL::double precision AS pv5,  NULL::double precision AS pv10,
    NULL::double precision AS pv15, NULL::double precision AS pv20,
    NULL::double precision AS pv25,
    NULL::double precision AS oil_eur, NULL::double precision AS gas_eur,
    NULL::double precision AS wti_price, NULL::double precision AS hh_price,
    NULL::double precision AS ngl_price, NULL::double precision AS wti_diff,
    NULL::double precision AS hh_diff,
    -- offset-support scores are N/A for producing wells (types must match the
    -- PUD/RES arm: counts/footage are bigint, distances/medians double precision)
    NULL::bigint AS pdp_count_1mi, NULL::bigint AS pdp_count_3mi,
    NULL::bigint AS pdp_count_5mi,
    NULL::double precision AS dist_nearest_ft, NULL::double precision AS dist_3rd_nearest_ft,
    NULL::bigint AS support_lateral_ft_5mi, NULL::bigint AS n_offsets_5mi,
    NULL::double precision AS offset_median_eur_ft,
    NULL::double precision AS inflation_ratio,
    we.wellstick_geom
FROM curated.wells_enriched we
LEFT JOIN curated.net_new_pdp nn ON nn.api10 = we.api10
WHERE we.first_production_date IS NOT NULL
  AND we.wellstick_geom IS NOT NULL
  AND we.is_horizontal IS TRUE
  AND we.api10 ~ '^[0-9]+$'
  AND we.basin_blueox IN ('delaware', 'midland')
WITH DATA;


-- Unique key on stick_id REQUIRED for REFRESH ... CONCURRENTLY (non-blocking
-- nightly refresh). Unique across both arms — see the header note.
CREATE UNIQUE INDEX idx_erebor_locations_pk   ON curated.erebor_locations (stick_id);
-- The hot path: per-tile AOI spatial filter (tiles.py / production.py / select.py
-- all do `basin = :basin AND ST_Intersects(wellstick_geom, <env|aoi>)`).
CREATE INDEX idx_erebor_locations_geom        ON curated.erebor_locations USING GIST (wellstick_geom);
CREATE INDEX idx_erebor_locations_basin_cat   ON curated.erebor_locations (basin, category);
-- Forecast/selection joins key on unique_id (= novi_wellname for PUD/RES).
CREATE INDEX idx_erebor_locations_uid         ON curated.erebor_locations (unique_id);
-- Blue Ox bench rollup (ResultsPanel cull, production curves) + §6 status legend.
CREATE INDEX idx_erebor_locations_blueox      ON curated.erebor_locations (basin, formation_blueox);
CREATE INDEX idx_erebor_locations_recon       ON curated.erebor_locations (basin, recon_status);


COMMENT ON MATERIALIZED VIEW curated.erebor_locations IS
'erebor display spine (§6 PDP-from-curated), MATERIALIZED for per-tile read latency on hosted Postgres: PUD/RES from curated.intel_locations + intel_formation_blueox + reconciled_inventory; PDP from curated.wells_enriched (producing) + net_new_pdp. Drop-in for curated.intel_locations in erebor''s map/gun-barrel/selection. PDP stick_id = -(api10); PDP econ columns NULL (producing context, not risked value). UNIQUE(stick_id) enables CONCURRENTLY refresh. Refresh: nightly via curated.refresh_all() (PDP arm) + recreate after the quarterly Novi reload (scripts/apply_erebor_locations.py). PUD/RES rows also carry the offset-PDP support score family (curated.intel_pdp_support, sql/30) — see per-column COMMENTs; PDP rows are NULL there (not applicable).';

-- -----------------------------------------------------------------------------
-- Offset-support score family (curated.intel_pdp_support, sql/30) — documented
-- per column because the land team's leasing apps consume this layer directly
-- and filter on these programmatically. Qualifying PDP offset = horizontal +
-- same TVD-corrected formation_blueox + TVD +/-500 ft + >=6 mo produced + within
-- the stated radius; the PDP universe is never county/basin-scoped.
-- Semantics: 0 = scored and genuinely unsupported; NULL on a PUD/RES row = not
-- scorable (unmapped bench or missing TVD/geometry); NULL on a PDP row = N/A
-- (producing wells are not scored).
-- -----------------------------------------------------------------------------
COMMENT ON COLUMN curated.erebor_locations.pdp_count_1mi IS
'Qualifying PDP offsets within 1 mi. 0 = scored & unsupported; NULL(PUD/RES) = not scorable; NULL(PDP) = N/A. Gate: horizontal + same TVD-corrected formation_blueox + TVD +/-500 ft + >=6 mo produced. curated.intel_pdp_support (sql/30).';
COMMENT ON COLUMN curated.erebor_locations.pdp_count_3mi IS
'Qualifying PDP offsets within 3 mi (primary support tier). 0 = scored & unsupported; NULL(PUD/RES) = not scorable; NULL(PDP) = N/A. Same gate as pdp_count_1mi.';
COMMENT ON COLUMN curated.erebor_locations.pdp_count_5mi IS
'Qualifying PDP offsets within 5 mi (the full neighbor set). 0 = scored & unsupported; NULL(PUD/RES) = not scorable; NULL(PDP) = N/A. Same gate as pdp_count_1mi.';
COMMENT ON COLUMN curated.erebor_locations.dist_nearest_ft IS
'Feet to the nearest qualifying PDP offset. NULL on a scored PUD/RES = no qualifying offset within 5 mi (the credible-extent halo edge); NULL(PDP) = N/A.';
COMMENT ON COLUMN curated.erebor_locations.dist_3rd_nearest_ft IS
'Feet to the 3rd-nearest qualifying PDP offset; NULL when <3 offsets (thin support is signal). NULL(PDP) = N/A.';
COMMENT ON COLUMN curated.erebor_locations.support_lateral_ft_5mi IS
'Sum of qualifying PDP offsets'' lateral_length_ft within 5 mi (developed footage supporting the stick). NULL(PDP) = N/A.';
COMMENT ON COLUMN curated.erebor_locations.n_offsets_5mi IS
'Count of 5-mi qualifying offsets carrying a non-null EUR — the sample size behind offset_median_eur_ft / inflation_ratio. NULL(PDP) = N/A.';
COMMENT ON COLUMN curated.erebor_locations.offset_median_eur_ft IS
'Median qualifying-offset Novi 30-yr oil EUR per lateral ft within 5 mi (bbl/ft) — history-matched offset productivity. NULL(PDP) = N/A.';
COMMENT ON COLUMN curated.erebor_locations.inflation_ratio IS
'Novi PUD oil EUR/ft / offset_median_eur_ft (rounded 2 dp): the PUD forecast vs its history-matched offsets. >1 = PUD forecasts above offset history; NULL = no offset basis or not scorable; NULL(PDP) = N/A.';
