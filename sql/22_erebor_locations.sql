-- =============================================================================
-- 22 — curated.erebor_locations  (erebor display spine)
--
-- What erebor's map / gun-barrel / selection / Highgrade read, and what the land
-- team's view (curated.box_scout_locations, sql/69) is built on. Two disjoint
-- arms UNION ALL'd:
--
--   * BOX  -> the RECORD BOX stick set of each basin (box.location_stick where
--             box.location_set.is_record, sql/73): the undrilled locations.
--             Since the BOX sticks cutover (docs/box_sticks_plan.md, phase 6;
--             Michael 2026-11-23). Until then this arm was the Novi PUD / RES
--             sticks; those now live in curated.intel_locations (sql/29)
--             for the readers still on Novi sticks (deal-intake).
--   * PDP  -> curated.wells_enriched (producing horizontals): what physically
--             EXISTS, from the system of record.
--
-- NO NOVI INTELLIGENCE RELATION IS READ HERE (docs/box_sticks_plan.md phase 7,
-- item 2; Michael 2026-11-24: Novi Intelligence is for comparison only, nothing
-- downstream is derived from it). Until then the PDP arm joined
-- curated.net_new_pdp (a tag that had been empty since 2026-10) and
-- curated.intel_locations (Novi's rock-quality scores of drilled wells), which
-- made every quarterly Novi reload drop this matview. The one Novi input left is
-- the DSU NAME of a BOX stick, from the raw table raw_novi_intel.pads (geometry
-- of record for the stick sets; a reload does not drop a raw table).
--
-- THE BOX ARM, column by column:
--   stick_id      = box.location.location_id (10,000,001 and up). Positive, as
--                   the sign convention requires; never a Novi stick id (about
--                   1.5 to 1.8 million) and never a PDP id (-(api10)).
--   unique_id     = the stick's name '<DSU id>-<bench>-<slot>' (stable across sets).
--   category / inventory_class = 'BOX'. Every reader tests `category <> 'PDP'`
--                   or `= 'PDP'`; nothing may test for 'PUD' / 'RES' here any more.
--   formation     = the bench code (a BOX stick has no Novi free-text formation).
--   recon_status  = the nightly reconciliation (curated.box_location_status,
--                   sql/74): open / permitted / pending / conflict, 'crowded'
--                   when the crowded flag is set, NULL when the nightly has not
--                   judged the stick yet. A PRODUCING stick is NOT a row: it is a
--                   well, and the PDP arm carries the well.
--   tvd           = the stick's landing TVD (generator; from offset producers, grids
--                   where control is thin). ll_ft = completed lateral (both legs of
--                   a U-turn stick, no turn arc).
--   wellstick_geom = the drilled path as ONE LineString: the leg, or leg + turn arc
--                   + leg for a U-turn stick (every record U-turn stick joins into
--                   one line; the apply script asserts it). The legs alone are in
--                   box.location_stick.legs_geom.
--   pad_name / pad_id = the Novi DSU the stick was generated in (raw_novi_intel.pads of the
--                   set's vintage): its name, and its id (what Highgrade groups by).
--   Novi-only columns (deplet_t, rqs, rqt, operator, NPV / PV / EUR / prices, the
--   offset-support family) are NULL: they describe a Novi stick, not a BOX stick.
--
-- PDP rows: stick_id = -(api10); display columns only; recon_status and every
-- Novi-only column NULL (rqs / rqt included: kept for shape, never filled).
--
-- stick_id is UNIQUE across both arms -> a UNIQUE index -> REFRESH ... CONCURRENTLY,
-- so the nightly refresh never blocks the app.
--
-- REFRESH:
--   * NIGHTLY (etl/db.py:_CURATED_MATVIEWS): both arms move nightly. The PDP arm
--     as wells come online; the BOX arm as the reconciliation hook (etl/box_recon,
--     which runs earlier in the same refresh) changes a stick's status, and as a
--     producing stick leaves. A record flip of a stick set shows at the next refresh
--     (or run REFRESH ... CONCURRENTLY by hand right after the flip).
--   * QUARTERLY: nothing. The Novi reload DROPs curated.intel_locations CASCADE,
--     and this matview no longer hangs off it. It still hangs off
--     curated.wells_enriched: a script that rebuilds curated.producing_reference
--     (sql/20) or curated.wells (sql/04) from scratch drops it, and must end with
--     scripts/apply_erebor_locations.py.
--
-- DEPENDS ON: box.location_stick, box.location_set (sql/73), curated.box_location_status
--   (sql/74), raw_novi_intel.pads (sql/11); curated.wells_enriched (sql/06).
-- CASCADE: dropping this drops curated.box_scout_locations (sql/69); every script
--   that runs this file calls scripts.apply_box_scout_locations.recreate (a test
--   enforces it).
-- SANITY: BOX rows = record sticks whose nightly status is not 'producing' (by
--   identity, per basin); 0 duplicate / NULL stick_id; every geometry a LineString.
-- Idempotent: type-aware drop, then CREATE ... WITH DATA.
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
-- ---- BOX: the record BOX stick set (the undrilled locations) ----
SELECT
    k.location_id                      AS stick_id,
    k.well_name                        AS unique_id,
    'BOX'::text                        AS category,
    'BOX'::text                        AS inventory_class,
    k.basin,
    k.formation_blueox                 AS formation,
    k.formation_blueox,
    k.basin                            AS basin_blueox,
    'box_sticks'::text                 AS formation_blueox_source,
    -- the nightly reconciliation (sql/74); NULL = not judged yet. 'producing' never
    -- reaches here (WHERE below).
    CASE WHEN s.crowded THEN 'crowded' ELSE s.status END AS recon_status,
    NULL::text                         AS deplet_t,
    NULL::double precision             AS rqs,    -- Novi rock quality: kept for shape, NULL on every row
    NULL::text                         AS rqt,
    NULL::text                         AS operator,
    p.pad_name,
    k.target_tvd_ft                    AS tvd,
    k.completed_lateral_ft             AS ll_ft,
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
    NULL::bigint AS pdp_count_1mi, NULL::bigint AS pdp_count_3mi,
    NULL::bigint AS pdp_count_5mi,
    NULL::double precision AS dist_nearest_ft, NULL::double precision AS dist_3rd_nearest_ft,
    NULL::bigint AS support_lateral_ft_5mi, NULL::bigint AS n_offsets_5mi,
    NULL::double precision AS offset_median_eur_ft,
    NULL::double precision AS inflation_ratio,
    NULL::double precision AS offset_median_tvd, NULL::double precision AS tvd_delta_ft,
    NULL::double precision AS tvd_excess_3mi_ft, NULL::double precision AS wca_delta_ft,
    -- the Novi DSU the stick was generated in (raw_novi_intel.pads.pad_id of the set's vintage): what erebor's
    -- Highgrade groups sticks by. pad_name alone is not enough: curated.intel_pad_geom only knows DSUs that held a
    -- Novi stick (254 Midland DSUs with BOX sticks are not in it).
    k.pad_id,
    -- the drilled path as ONE line: leg, or leg + turn arc + leg (U-turn)
    (CASE WHEN k.turn_geom IS NULL THEN extensions.ST_GeometryN(k.legs_geom, 1)
          ELSE extensions.ST_LineMerge(extensions.ST_Collect(k.legs_geom, k.turn_geom))
     END)::extensions.geometry(LineString, 4326) AS wellstick_geom
FROM box.location_stick k
JOIN box.location_set t ON t.set_id = k.set_id AND t.is_record
LEFT JOIN curated.box_location_status s ON s.location_id = k.location_id AND s.set_id = k.set_id
LEFT JOIN LATERAL (
    SELECT q.pad_name FROM raw_novi_intel.pads q
    WHERE q.report_version = t.dsu_vintage AND q.pad_id = k.pad_id AND q.basin = k.basin
    ORDER BY q.pad_name LIMIT 1
) p ON TRUE
WHERE COALESCE(s.status, 'open') <> 'producing'

UNION ALL

-- ---- PDP: producing curated HORIZONTAL wells (what exists) ----
-- wells_enriched carries formation_blueox + is_horizontal. Horizontal-only so
-- the layer matches the Novi laterals (curated.wells also holds shallow vertical
-- conventional producers — Grayburg/San Andres — that don't belong on a
-- lateral map / gun-barrel cross-section).
SELECT
    -(we.api10::bigint)                AS stick_id,    -- never collides with a BOX stick id
    we.api10                           AS unique_id,
    'PDP'::text                        AS category,
    'PDP'::text                        AS inventory_class,   -- native == legacy for PDP
    we.basin_blueox                    AS basin,
    we.formation,
    we.formation_blueox,
    we.basin_blueox,
    we.formation_blueox_source,
    -- A producing well carries no reconciliation tag. (Until phase 7 item 2:
    -- 'net_new_pdp' from curated.net_new_pdp, sql/25 — empty since 2026-10.)
    NULL::text                         AS recon_status,
    NULL::text                         AS deplet_t,   -- a Novi stick score; NULL on every row since the cutover
    -- Novi rock quality of drilled wells: no longer joined (phase 7 item 2). The
    -- scores are in curated.intel_locations (category 'PDP') for comparison.
    NULL::double precision             AS rqs,
    NULL::text                         AS rqt,
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
    -- offset-support scores: a Novi stick family, NULL on every row since the cutover
    -- (types kept: counts/footage bigint, distances/medians double precision)
    NULL::bigint AS pdp_count_1mi, NULL::bigint AS pdp_count_3mi,
    NULL::bigint AS pdp_count_5mi,
    NULL::double precision AS dist_nearest_ft, NULL::double precision AS dist_3rd_nearest_ft,
    NULL::bigint AS support_lateral_ft_5mi, NULL::bigint AS n_offsets_5mi,
    NULL::double precision AS offset_median_eur_ft,
    NULL::double precision AS inflation_ratio,
    NULL::double precision AS offset_median_tvd, NULL::double precision AS tvd_delta_ft,
    NULL::double precision AS tvd_excess_3mi_ft, NULL::double precision AS wca_delta_ft,
    NULL::bigint                       AS pad_id,     -- a producing well belongs to no DSU here
    we.wellstick_geom
FROM curated.wells_enriched we
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
-- Selection / production overlay look a row up by unique_id (the stick name, or the api10 of a PDP row).
CREATE INDEX idx_erebor_locations_uid         ON curated.erebor_locations (unique_id);
-- Blue Ox bench rollup (ResultsPanel cull, production curves) + §6 status legend.
CREATE INDEX idx_erebor_locations_blueox      ON curated.erebor_locations (basin, formation_blueox);
CREATE INDEX idx_erebor_locations_recon       ON curated.erebor_locations (basin, recon_status);


COMMENT ON MATERIALIZED VIEW curated.erebor_locations IS
'erebor display spine and the base of the land team''s view (sql/69). Undrilled locations = the RECORD BOX stick set of each basin (category BOX; stick_id = box.location.location_id, 10,000,001 and up; one LineString per stick, a U-turn stick including its turn arc; tvd = the stick''s landing TVD; recon_status = the nightly reconciliation of sql/74; a producing stick is not a row). Producing wells = curated.wells_enriched horizontals (category PDP; stick_id = -(api10)). Novi sticks are no longer here: see curated.intel_locations (sql/29). No Novi Intelligence relation is read (phase 7 item 2): the Novi-only columns (deplet_t, rqs, rqt, operator on BOX rows, NPV / PV / EUR / prices, the offset-support family) are kept for shape and are NULL; the only Novi input is a BOX stick''s DSU name and id (raw_novi_intel.pads). UNIQUE(stick_id) enables CONCURRENTLY refresh; refreshed nightly; a quarterly Novi reload does not drop it.';

COMMENT ON COLUMN curated.erebor_locations.stick_id IS
'Location key. BOX stick: box.location.location_id (10,000,001 and up). Producing well: -(api10). The sign is load-bearing (promoteId, culls, PDP tests): never abs() it.';
COMMENT ON COLUMN curated.erebor_locations.category IS
'BOX (an undrilled BOX stick) or PDP (a producing horizontal well). Readers test = ''PDP'' or <> ''PDP''.';
COMMENT ON COLUMN curated.erebor_locations.inventory_class IS
'Same as category since the BOX sticks cutover (BOX / PDP). Was Novi''s native tier (PDP / BASE_CASE / EMERGING) while the undrilled arm was Novi sticks.';
COMMENT ON COLUMN curated.erebor_locations.recon_status IS
'BOX row: the nightly reconciliation of the stick (curated.box_location_status, sql/74): open / permitted / pending / conflict, or crowded when a producer sits inside the stick''s envelope at another landing; NULL = not judged yet. conflict and crowded sticks carry no BOX forecast. PDP row: NULL.';
COMMENT ON COLUMN curated.erebor_locations.tvd IS
'BOX row: the stick''s landing TVD, ft (box.location_stick.target_tvd_ft: same-bench producers first, the geologist''s grids where control is thin). PDP row: the well''s TVD (wells_enriched.tvd_ft).';
COMMENT ON COLUMN curated.erebor_locations.ll_ft IS
'BOX row: completed lateral, ft (both legs of a U-turn stick, without the turn arc). PDP row: the well''s lateral length.';
COMMENT ON COLUMN curated.erebor_locations.wellstick_geom IS
'EPSG 4326 LineString. BOX row: the drilled path (a U-turn stick: leg + turn arc + leg, so longer than ll_ft). PDP row: the wellstick.';
COMMENT ON COLUMN curated.erebor_locations.pad_name IS
'BOX row: the name of the Novi DSU the stick was generated in. PDP row: NULL.';
COMMENT ON COLUMN curated.erebor_locations.pad_id IS
'BOX row: raw_novi_intel.pads.pad_id of the Novi DSU the stick was generated in (the vintage is box.location_set.dsu_vintage of the record set). PDP row: NULL.';
