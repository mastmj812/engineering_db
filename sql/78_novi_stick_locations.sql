-- =============================================================================
-- 78 — curated.novi_stick_locations  (the Novi PUD / RES sticks, kept for the
--      readers that still work on Novi sticks)
--
-- WHY: from the BOX sticks cutover (docs/box_sticks_plan.md, phase 6) the
-- undrilled arm of curated.erebor_locations (sql/22) is the record BOX stick set,
-- not the Novi sticks. deal-intake still compares a unit against the Novi sticks
-- (dealintake/warehouse.py: novi_sticks, novi_params) until its own cutover
-- (phase 7). This matview is the Novi arm sql/22 carried until then, column for
-- column, so those readers move by changing one relation name.
--
-- One row per Novi PUD / RES stick of the live vintage: Novi's own columns
-- (name, tier, TVD, lateral, NPV / PV / EUR, prices), our bench mapping
-- (intel_formation_blueox), our reconciliation status (reconciled_inventory,
-- sql/68) and the offset-support score family (intel_pdp_support, sql/30).
-- No producing wells here: those stay in curated.erebor_locations.
--
-- stick_id is the Novi stick id (positive, about 1.5 to 1.8 million). It never
-- collides with a BOX stick's location_id (10,000,001 and up).
--
-- DEPENDS ON: curated.intel_locations (sql/29), curated.intel_formation_blueox
--   (sql/19), curated.reconciled_inventory (sql/68), curated.intel_pdp_support
--   (sql/30).
-- REFRESH: QUARTERLY only. Every input is quarterly-owned; nothing here moves
--   nightly, so it is NOT in etl/db.py:_CURATED_MATVIEWS. The Novi reload
--   DROP-CASCADEs it with curated.intel_locations; scripts/apply_erebor_locations.py
--   recreates it (before sql/22), and sql/26 follows.
-- RUN:  python -m scripts.apply_box_stick_locations   (the cutover; --dry-run first)
--       python -m scripts.apply_erebor_locations      (after a quarterly reload)
-- SANITY: rows = curated.intel_locations rows with category IN ('PUD', 'RES');
--         0 duplicate / NULL stick_id.
-- Idempotent: type-aware drop, then CREATE ... WITH DATA.
-- =============================================================================

DO $$
BEGIN
    IF EXISTS (
        SELECT 1 FROM pg_class c
        JOIN pg_namespace n ON n.oid = c.relnamespace
        WHERE n.nspname = 'curated' AND c.relname = 'novi_stick_locations' AND c.relkind = 'v'
    ) THEN
        DROP VIEW curated.novi_stick_locations CASCADE;
    END IF;
END $$;

DROP MATERIALIZED VIEW IF EXISTS curated.novi_stick_locations CASCADE;

CREATE MATERIALIZED VIEW curated.novi_stick_locations AS
SELECT
    il.stick_id,
    il.unique_id,
    il.category,
    CASE il.category WHEN 'PUD' THEN 'BASE_CASE' WHEN 'RES' THEN 'EMERGING'
         ELSE il.category END          AS inventory_class,
    il.basin,
    il.formation,
    fb.formation_blueox,
    fb.basin_blueox,
    fb.formation_blueox_source,
    ri.status                          AS recon_status,
    il.deplet_t,
    il.rqs,
    il.rqt,
    il.operator,
    il.pad_name,
    il.tvd,
    il.ll_ft,
    il.npv5, il.npv10, il.npv15, il.npv20, il.npv25,
    il.pv5,  il.pv10,  il.pv15,  il.pv20,  il.pv25,
    il.oil_eur, il.gas_eur,
    il.wti_price, il.hh_price, il.ngl_price, il.wti_diff, il.hh_diff,
    sup.pdp_count_1mi, sup.pdp_count_3mi, sup.pdp_count_5mi,
    sup.dist_nearest_ft, sup.dist_3rd_nearest_ft,
    sup.support_lateral_ft_5mi, sup.n_offsets_5mi,
    sup.offset_median_eur_ft,
    round(sup.inflation_ratio::numeric, 2)::double precision AS inflation_ratio,
    sup.offset_median_tvd, sup.tvd_delta_ft,
    sup.tvd_excess_3mi_ft, sup.wca_delta_ft,
    il.wellstick_geom
FROM curated.intel_locations il
LEFT JOIN curated.intel_formation_blueox fb ON fb.stick_id = il.stick_id
LEFT JOIN curated.reconciled_inventory ri ON ri.stick_id = il.stick_id
LEFT JOIN curated.intel_pdp_support sup ON sup.stick_id = il.stick_id
WHERE il.category IN ('PUD', 'RES')
WITH DATA;

CREATE UNIQUE INDEX idx_novi_stick_locations_pk     ON curated.novi_stick_locations (stick_id);
CREATE INDEX idx_novi_stick_locations_geom          ON curated.novi_stick_locations USING GIST (wellstick_geom);
-- deal-intake's unit search is ST_DWithin(wellstick_geom::geography, unit, buffer): the expression index it needs
CREATE INDEX idx_novi_stick_locations_geog          ON curated.novi_stick_locations
    USING GIST ((wellstick_geom::extensions.geography));
CREATE INDEX idx_novi_stick_locations_blueox        ON curated.novi_stick_locations (basin, formation_blueox);

GRANT SELECT ON curated.novi_stick_locations TO analyst_ro;

COMMENT ON MATERIALIZED VIEW curated.novi_stick_locations IS
'Novi Intelligence PUD / RES sticks of the live vintage with our bench mapping, reconciliation status (sql/68) and offset-support scores (sql/30): the arm curated.erebor_locations carried until the BOX sticks cutover (sql/22, docs/box_sticks_plan.md phase 6). Read by deal-intake until its own cutover; erebor and the land team''s view read BOX sticks from curated.erebor_locations. Quarterly only (every input is quarterly-owned); DROP-CASCADEs with curated.intel_locations and is recreated by scripts.apply_erebor_locations. sql/78.';
COMMENT ON COLUMN curated.novi_stick_locations.stick_id IS 'Novi stick id (positive; never a BOX stick id, which start at 10,000,001).';
COMMENT ON COLUMN curated.novi_stick_locations.recon_status IS 'Our reconciliation of the Novi stick (curated.reconciled_inventory, sql/68): remaining_pud / conflict / realized_drift / realized_phantom; NULL = no bench or geometry.';
COMMENT ON COLUMN curated.novi_stick_locations.tvd IS 'Novi''s planned landing TVD of the stick, ft. Known to run deep on some benches (Delaware WCC median +846 ft against producers): the reason BOX sticks replaced these.';
