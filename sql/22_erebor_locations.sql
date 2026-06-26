-- =============================================================================
-- 22 — curated.erebor_locations  (erebor display spine: §6 PDP-from-curated)
--
-- erebor's map/gun-barrel/selection read this instead of curated.intel_locations.
-- It flips the spine per §6: PUD/RES (the forward inventory) come from Novi
-- Intelligence; PDP (what physically EXISTS) comes from curated.wells — the
-- accurate, current, more-complete system of record — NOT the stale, error-prone
-- novi_intel PDP layer (which only remains as a reconciliation-QC input).
--
-- Plain VIEW (no refresh, always current). Two disjoint arms UNION ALL'd:
--   * PUD/RES  -> curated.intel_locations + curated.intel_formation_blueox
--   * PDP      -> curated.wells (producing) + curated.formation_blueox
--
-- PDP rows carry display columns (geom / formation_blueox / tvd / operator) and
-- NULL for Novi-only econ (npv/pv/eur/prices) — PDP is producing context, not
-- risked inventory value. stick_id for PDP is -(api10) so it never collides with
-- a Novi stick_id and the frontend's promoteId selection still works. pad_name is
-- NULL -> the gun-barrel's existing spatial DSU-pad assignment resolves it.
--
-- DEPENDS ON: curated.intel_locations (sql/12), curated.intel_formation_blueox
--   (sql/19), curated.wells (sql/04), curated.formation_blueox (sql/16),
--   curated.reconciled_inventory (sql/21), curated.net_new_pdp (sql/25).
-- =============================================================================


DROP VIEW IF EXISTS curated.erebor_locations CASCADE;


CREATE VIEW curated.erebor_locations AS
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
    -- realized_pud_to_pdp / remaining_pud / conflict; RES has no row -> NULL.
    ri.status                          AS recon_status,
    il.operator,
    il.pad_name,
    il.tvd,
    il.ll_ft,
    il.npv5, il.npv10, il.npv15, il.npv20, il.npv25,
    il.pv5,  il.pv10,  il.pv15,  il.pv20,  il.pv25,
    il.oil_eur, il.gas_eur,
    il.wti_price, il.hh_price, il.ngl_price, il.wti_diff, il.hh_diff,
    il.wellstick_geom
FROM curated.intel_locations il
LEFT JOIN curated.intel_formation_blueox fb ON fb.stick_id = il.stick_id
LEFT JOIN curated.reconciled_inventory ri ON ri.stick_id = il.stick_id
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
    we.wellstick_geom
FROM curated.wells_enriched we
LEFT JOIN curated.net_new_pdp nn ON nn.api10 = we.api10
WHERE we.first_production_date IS NOT NULL
  AND we.wellstick_geom IS NOT NULL
  AND we.is_horizontal IS TRUE
  AND we.api10 ~ '^[0-9]+$'
  AND we.basin_blueox IN ('delaware', 'midland')
;


COMMENT ON VIEW curated.erebor_locations IS
'erebor display spine (§6 PDP-from-curated): PUD/RES from curated.intel_locations + intel_formation_blueox; PDP from curated.wells (producing) + formation_blueox. Drop-in for curated.intel_locations in erebor''s map/gun-barrel/selection. PDP stick_id = -(api10); PDP econ columns NULL (producing context, not risked value). Replaces the stale novi_intel PDP display layer.';
