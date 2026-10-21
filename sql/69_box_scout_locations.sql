-- sql/69 — curated.box_scout_locations: one flat, land-facing row per stick location with its BOX
--          record-run forecast and Steven's default-deck econ (Michael 2026-10-21)
--
-- WHY: the BOX numbers live across box.pud_forecast (coverage), box.pud_forecast_stream (one row per
-- stream), box.pud_proximity and box_econ.box_pud_econ (one row per location x 16 decks x assumption set).
-- A GIS tool on analyst_ro would have to join, filter to the record run, pivot the streams and pick a
-- deck by hand — easy to get subtly wrong (mixing runs, reading "no forecast" as zero). This view does
-- it once, the same way erebor does (erebor app/box_locations.py), and stays current with no refresh.
--
-- GRAIN: one row per curated.erebor_locations stick location (category <> 'PDP'; PDP is producing
-- context, never forecast — rule 8). stick_id is unique. Geometry = the Novi stick (EPSG 4326).
-- Novi supplies geometry only (Michael 2026-10-21): Novi's PUD / RES tag, tiers and NPV are NOT here.
--
-- BOX: the record run (box.forecast_run.is_record — at most one, sql/60). Every location carries a
-- box_coverage class, mirroring erebor box_locations.map_coverage_sql (cross-repo contract):
--   covered / covered_provisional          BOX forecast (tier validated / PROVISIONAL, D105 — keep apart)
--   not_covered_*                          searched or classed by BOX, no forecast (reason in the name)
--   realized                               our reconciliation matched it to production (sql/20, sql/68)
--   not_screened                           on a BOX bench, no row in the record run (e.g. Novi-RES sticks, D117 step 3 parked)
--   bench_not_in_box                       its bench is in no box.bench_scope pool (all of Midland today)
-- A location without a forecast has NULL EUR — never zero. EUR = raw 50-yr technical integral incl. the
-- bench haircut and the D113 proximity oil factor (already inside the stored EUR; do not re-apply it).
-- Per-foot = stored eur_per_kft / 1000 (bbl/ft oil + water, mcf/ft gas).
--
-- ECON (display only, D13 — nothing here computes economics; econ never flows back into BOX): Steven's
-- box_econ.box_pud_econ for the RECORD run, deck wti70_hh3 (WTI $70 / HH $3), its most recently built
-- assumption set, with provenance columns. Other decks: query box_econ.box_pud_econ directly. Steven's
-- screen_pass / rejection_step are deliberately left out (his screen includes Novi's Tier-4 depletion cut,
-- which conflicts with BOX D90 — pending with him). The view lives in curated, not box: nothing in box
-- reads box_econ (D13).
--
-- DEPENDS ON: curated.erebor_locations (sql/22 matview), box.forecast_run / pud_forecast /
-- pud_forecast_stream / pud_proximity / bench_scope, box_econ.box_pud_econ. Plain VIEW: no storage, no
-- refresh, always current with the record run and Steven's latest push.
-- DROPPED BY: any DROP ... CASCADE of curated.erebor_locations (sql/22 — the quarterly reload, and the
-- one-off appliers that rebuild it). Every script that executes sql/22 re-runs this file right after
-- (scripts.apply_box_scout_locations.recreate; tests/test_box_scout_locations.py enforces it).
-- Comments live here (not sql/31) so recreating the view restores them.
--
-- RUN: python -m scripts.apply_box_scout_locations   (explicit go; --check validates read-only first)
-- Idempotent: DROP VIEW IF EXISTS + CREATE VIEW (so a later column change applies cleanly).

DROP VIEW IF EXISTS curated.box_scout_locations;

CREATE VIEW curated.box_scout_locations AS
WITH run AS (
    SELECT run_id, data_through FROM box.forecast_run WHERE is_record
),
econ_case AS (
    -- the default deck's most recently built assumption set on the record run (erebor pick_econ_case)
    SELECT e.deck_id, e.assumption_set_id
    FROM box_econ.box_pud_econ e JOIN run ON e.run_id = run.run_id
    WHERE e.deck_id = 'wti70_hh3'
    GROUP BY e.deck_id, e.assumption_set_id
    ORDER BY max(e.built_at) DESC NULLS LAST, e.assumption_set_id DESC
    LIMIT 1
),
pool AS (
    SELECT DISTINCT basin, unnest(member_benches) AS bench FROM box.bench_scope
)
SELECT
    el.stick_id,
    el.unique_id                                       AS location_name,
    el.basin,
    el.formation_blueox                                AS bench,
    el.pad_name,
    el.recon_status,
    el.ll_ft                                           AS stick_lateral_ft,
    el.wellstick_geom                                  AS geom,
    -- BOX record run
    run.run_id                                         AS box_run_id,
    run.data_through                                   AS box_data_through,
    CASE WHEN bp.coverage IS NOT NULL THEN bp.coverage
         WHEN el.recon_status IN ('realized_drift', 'realized_phantom') THEN 'realized'
         WHEN pool.bench IS NOT NULL THEN 'not_screened'
         ELSE 'bench_not_in_box' END                   AS box_coverage,
    CASE bp.coverage WHEN 'covered' THEN 'validated'
                     WHEN 'covered_provisional' THEN 'provisional' END AS box_tier,
    bp.lateral_ft                                      AS box_lateral_ft,
    bso.eur                                            AS oil_eur_bbl,
    bso.eur_per_kft / 1000.0                           AS oil_eur_bbl_per_ft,
    bsg.eur                                            AS gas_eur_mcf,
    bsg.eur_per_kft / 1000.0                           AS gas_eur_mcf_per_ft,
    bsw.eur                                            AS water_eur_bbl,
    bsw.eur_per_kft / 1000.0                           AS water_eur_bbl_per_ft,
    bsw.tier                                           AS water_tier,
    bpp.outcome                                        AS prox_outcome,
    bso.prox_factor                                    AS prox_oil_factor,
    -- Steven's econ, default deck (display only, D13)
    be.deck_id                                         AS econ_deck_id,
    be.assumption_set_id                               AS econ_assumption_set_id,
    be.wti                                             AS econ_wti,
    be.hh                                              AS econ_hh,
    be.downtime_basis                                  AS econ_downtime_basis,
    be.pv0_mm, be.pv10_mm, be.pv15_mm, be.pv20_mm, be.pv25_mm, be.pv30_mm,
    be.irr_pct,
    be.breakeven_wti_pv20,
    be.capex_mm,
    be.unpriced_reason                                 AS econ_unpriced_reason,
    be.built_at                                        AS econ_built_at,
    be.pushed_at                                       AS econ_pushed_at,
    be.pushed_by                                       AS econ_pushed_by
FROM curated.erebor_locations el
CROSS JOIN run
LEFT JOIN box.pud_forecast bp
       ON bp.run_id = run.run_id AND bp.stick_id = el.stick_id
LEFT JOIN box.pud_forecast_stream bso
       ON bso.run_id = bp.run_id AND bso.location_id = bp.location_id AND bso.stream = 'oil'
LEFT JOIN box.pud_forecast_stream bsg
       ON bsg.run_id = bp.run_id AND bsg.location_id = bp.location_id AND bsg.stream = 'gas'
LEFT JOIN box.pud_forecast_stream bsw
       ON bsw.run_id = bp.run_id AND bsw.location_id = bp.location_id AND bsw.stream = 'water'
LEFT JOIN box.pud_proximity bpp
       ON bpp.run_id = bp.run_id AND bpp.location_id = bp.location_id
LEFT JOIN pool
       ON pool.basin = el.basin AND pool.bench = el.formation_blueox
LEFT JOIN econ_case ON true
LEFT JOIN box_econ.box_pud_econ be
       ON be.run_id = bp.run_id AND be.location_id = bp.location_id
      AND be.deck_id = econ_case.deck_id AND be.assumption_set_id = econ_case.assumption_set_id
WHERE el.category <> 'PDP';

GRANT SELECT ON curated.box_scout_locations TO analyst_ro;

COMMENT ON VIEW curated.box_scout_locations IS
'Land-facing flat view (sql/69): one row per stick location (curated.erebor_locations minus PDP; stick_id unique; geom = Novi stick, EPSG 4326) with its BOX RECORD-run forecast and Steven''s default-deck econ. box_coverage says why a location has no forecast (never zero); box_tier keeps validated and PROVISIONAL apart (D105). EUR = raw 50-yr technical integral incl. the bench haircut and D113 proximity factor. Econ = box_econ.box_pud_econ, deck wti70_hh3, newest assumption set, display only (D13); other decks: query box_econ directly. Novi tags / NPV are not carried. Plain view: always current, no refresh.';
COMMENT ON COLUMN curated.box_scout_locations.stick_id IS 'Stable stick key (positive Novi stick_id); unique in this view. Joins curated.erebor_locations / intel_locations / box.pud_forecast.stick_id.';
COMMENT ON COLUMN curated.box_scout_locations.location_name IS 'Novi stick name (erebor_locations.unique_id).';
COMMENT ON COLUMN curated.box_scout_locations.bench IS 'Blue Ox bench (formation_blueox) — always group by this, never raw formation.';
COMMENT ON COLUMN curated.box_scout_locations.recon_status IS 'Our reconciliation (sql/20, sql/68: every Novi stick): remaining_pud / conflict / realized_drift / realized_phantom; realized = already drilled.';
COMMENT ON COLUMN curated.box_scout_locations.stick_lateral_ft IS 'Lateral length of the Novi stick geometry, ft.';
COMMENT ON COLUMN curated.box_scout_locations.geom IS 'Novi stick linestring, EPSG 4326 (rides the curated.erebor_locations GiST index for bbox filters).';
COMMENT ON COLUMN curated.box_scout_locations.box_run_id IS 'BOX record run (box.forecast_run.is_record) every BOX value in the row comes from.';
COMMENT ON COLUMN curated.box_scout_locations.box_data_through IS 'Last production month the record run saw.';
COMMENT ON COLUMN curated.box_scout_locations.box_coverage IS 'covered / covered_provisional = BOX forecast; not_covered_* = classed by BOX without a forecast (reason in the name); realized = matched to production; not_screened = on a BOX bench but not in the record run; bench_not_in_box = bench outside every BOX pool. Mirrors erebor box_locations.map_coverage_sql.';
COMMENT ON COLUMN curated.box_scout_locations.box_tier IS 'validated (covered) or provisional (covered_provisional, D105); NULL = no forecast. Report the two apart, never silently summed.';
COMMENT ON COLUMN curated.box_scout_locations.box_lateral_ft IS 'Lateral BOX forecast on (box.pud_forecast.lateral_ft); the basis of the per-ft values.';
COMMENT ON COLUMN curated.box_scout_locations.oil_eur_bbl IS 'BOX oil EUR, bbl: raw 50-yr technical integral incl. bench haircut and D113 proximity factor; NULL = no forecast (never zero).';
COMMENT ON COLUMN curated.box_scout_locations.oil_eur_bbl_per_ft IS 'BOX oil EUR per lateral foot, bbl/ft (stored eur_per_kft / 1000). Aggregate as SUM(eur) / SUM(eur / per_ft), not an average of ratios.';
COMMENT ON COLUMN curated.box_scout_locations.gas_eur_mcf IS 'BOX gas EUR, mcf; NULL = no forecast.';
COMMENT ON COLUMN curated.box_scout_locations.gas_eur_mcf_per_ft IS 'BOX gas EUR per lateral foot, mcf/ft.';
COMMENT ON COLUMN curated.box_scout_locations.water_eur_bbl IS 'BOX water EUR, bbl (WOR vs cum oil on measured-water analogs, sql/62); NULL = no forecast.';
COMMENT ON COLUMN curated.box_scout_locations.water_eur_bbl_per_ft IS 'BOX water EUR per lateral foot, bbl/ft.';
COMMENT ON COLUMN curated.box_scout_locations.water_tier IS 'Water stream tier (validated / provisional, D110), never above the location''s own tier.';
COMMENT ON COLUMN curated.box_scout_locations.prox_outcome IS 'PDP-proximity outcome (box.pud_proximity, D112-D116): as_is_unexposed / as_is_single_parent / haircut / no_forecast_*; NULL = not measured.';
COMMENT ON COLUMN curated.box_scout_locations.prox_oil_factor IS 'D113 oil factor already applied inside oil_eur_bbl (1 = as-is; 0.75-0.94 = multi-parent haircut). Informational — do not re-apply.';
COMMENT ON COLUMN curated.box_scout_locations.econ_deck_id IS 'Steven''s price deck of the econ columns (wti70_hh3 = WTI $70 / HH $3); NULL = location not priced / no forecast.';
COMMENT ON COLUMN curated.box_scout_locations.econ_assumption_set_id IS 'Steven''s assumption set (the most recently built one for the deck on the record run).';
COMMENT ON COLUMN curated.box_scout_locations.econ_downtime_basis IS 'How Steven applied downtime to BOX''s uptime-free volumes (required provenance, D13).';
COMMENT ON COLUMN curated.box_scout_locations.pv10_mm IS 'Steven''s PV10, $MM, display only (D13). pv0/15/20/25/30_mm likewise.';
COMMENT ON COLUMN curated.box_scout_locations.irr_pct IS 'Steven''s IRR, %; NULL where he reports none. Use a median, never a sum or mean, across locations.';
COMMENT ON COLUMN curated.box_scout_locations.breakeven_wti_pv20 IS 'Steven''s breakeven WTI at PV20, $/bbl (lower = better).';
COMMENT ON COLUMN curated.box_scout_locations.capex_mm IS 'Steven''s capex, $MM.';
COMMENT ON COLUMN curated.box_scout_locations.econ_pushed_at IS 'When Steven pushed this econ case (provenance).';
