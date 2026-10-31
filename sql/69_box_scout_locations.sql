-- sql/69 — curated.box_scout_locations: the land team's ONE table for BOX locations — every stick that
--          carries a BOX forecast AND Steven's econ, nothing else (Michael 2026-10-21)
--
-- WHY: the BOX numbers live across box.pud_forecast, box.pud_forecast_stream (one row per stream) and
-- box_econ.box_pud_econ (one row per location x 16 decks x assumption set). This view joins them once,
-- for analyst_ro / QGIS, and keeps it as simple as possible.
--
-- v2 (Michael 2026-10-21, "the land guys are confused"): the first version carried every Novi stick
-- (257k rows) with a coverage class + recon_status explaining why most had no forecast. Now it carries
-- ONLY priced BOX locations, and only the columns a land user needs:
--   rows    = a BOX record-run forecast (covered / covered_provisional) AND a priced default-deck econ
--             row, MINUS sticks our reconciliation says are already drilled (realized_drift / _phantom;
--             same population as erebor Highgrade). No PDP, no not-covered / not-screened sticks.
--   columns = location (stick, name, bench, Novi DSU pad name, geometry, BOX lateral), the BOX forecast
--             (tier + oil / gas / water EUR and per ft), Steven's PV10 / PV20 / IRR / breakeven / capex,
--             and a deck label + run + push time as provenance.
-- Novi supplies geometry + names only: no Novi tag, tier or NPV. Steven's screen_pass / rejection_step
-- stay out (his screen includes Novi's Tier-4 cut, which conflicts with BOX D90 — pending with him).
--
-- v3 (land team ask, 2026-10-30): + tvd_ft, the stick's planned landing TVD (ft) — Novi's own TVD for the stick
-- (erebor_locations.tvd = raw_intel tvd_td). BOX stores no TVD of its own: its proximity study (sql/65) reads this
-- same column, so this is the depth BOX's forecast was screened at. It is NOT an offset-well median (rule 10 governs
-- how WE derive a landing TVD for a new location; this column reports the depth of Novi's planned stick as-is).
--
-- BOX: the record runs (box.forecast_run.is_record — one PER BASIN since D130 / sql/70; each stick's row comes from its
-- own basin's record, and the econ case is picked per record run). EUR = raw 50-yr technical integral incl. the bench
-- haircut and the D113 proximity oil factor. box_tier keeps validated and PROVISIONAL apart (D105).
-- ECON: Steven's box_econ.box_pud_econ for the record run, deck wti70_hh3 (WTI $70 / HH $3), its most
-- recently built assumption set — display only (D13: nothing here computes economics; econ never flows
-- back into BOX). The view lives in curated, not box: nothing in box reads box_econ.
--
-- DEPENDS ON: curated.erebor_locations (sql/22 matview: geometry + name + reconciliation), box.forecast_run
-- / pud_forecast / pud_forecast_stream, box_econ.box_pud_econ. Plain VIEW: no storage, no refresh, always
-- current with the record run and Steven's latest push.
-- DROPPED BY: any DROP ... CASCADE of curated.erebor_locations (sql/22). Every script that executes sql/22
-- re-runs this file right after (scripts.apply_box_scout_locations.recreate; a test enforces it).
-- Comments live here (not sql/31) so recreating the view restores them.
--
-- RUN: python -m scripts.apply_box_scout_locations   (explicit go; --dry-run validates read-only first)
-- Idempotent: DROP VIEW IF EXISTS + CREATE VIEW (column set changes apply cleanly).

DROP VIEW IF EXISTS curated.box_scout_locations;

CREATE VIEW curated.box_scout_locations AS
WITH run AS (
    SELECT run_id FROM box.forecast_run WHERE is_record  -- one per basin (D130, sql/70)
),
econ_case AS (
    -- per record run: the default deck's most recently built assumption set (erebor pick_econ_case)
    SELECT DISTINCT ON (g.run_id) g.run_id, g.deck_id, g.assumption_set_id
    FROM (SELECT e.run_id, e.deck_id, e.assumption_set_id, max(e.built_at) AS built_at
          FROM box_econ.box_pud_econ e JOIN run ON e.run_id = run.run_id
          WHERE e.deck_id = 'wti70_hh3'
          GROUP BY e.run_id, e.deck_id, e.assumption_set_id) g
    ORDER BY g.run_id, g.built_at DESC NULLS LAST, g.assumption_set_id DESC
)
SELECT
    el.stick_id,
    el.unique_id                                       AS location_name,
    el.basin,
    el.formation_blueox                                AS bench,
    el.pad_name,
    el.wellstick_geom                                  AS geom,
    bp.lateral_ft,
    el.tvd                                             AS tvd_ft,
    -- BOX forecast (record run)
    CASE bp.coverage WHEN 'covered' THEN 'validated' ELSE 'provisional' END AS box_tier,
    bso.eur                                            AS oil_eur_bbl,
    bso.eur_per_kft / 1000.0                           AS oil_eur_bbl_per_ft,
    bsg.eur                                            AS gas_eur_mcf,
    bsg.eur_per_kft / 1000.0                           AS gas_eur_mcf_per_ft,
    bsw.eur                                            AS water_eur_bbl,
    bsw.eur_per_kft / 1000.0                           AS water_eur_bbl_per_ft,
    -- Steven's econ, default deck (display only, D13)
    be.pv10_mm,
    be.pv20_mm,
    be.irr_pct,
    be.breakeven_wti_pv20,
    be.capex_mm,
    -- provenance
    'WTI $' || rtrim(to_char(be.wti, 'FM999990.##'), '.')
        || ' / HH $' || rtrim(to_char(be.hh, 'FM990.##'), '.')  AS econ_deck,
    bp.run_id                                          AS box_run_id,
    be.pushed_at                                       AS econ_pushed_at
FROM run
JOIN box.pud_forecast bp
  ON bp.run_id = run.run_id AND bp.coverage IN ('covered', 'covered_provisional')
JOIN curated.erebor_locations el
  ON el.stick_id = bp.stick_id AND el.category <> 'PDP'
JOIN econ_case ON econ_case.run_id = bp.run_id
JOIN box_econ.box_pud_econ be
  ON be.run_id = bp.run_id AND be.location_id = bp.location_id
 AND be.deck_id = econ_case.deck_id AND be.assumption_set_id = econ_case.assumption_set_id
 AND be.pv10_mm IS NOT NULL
LEFT JOIN box.pud_forecast_stream bso
  ON bso.run_id = bp.run_id AND bso.location_id = bp.location_id AND bso.stream = 'oil'
LEFT JOIN box.pud_forecast_stream bsg
  ON bsg.run_id = bp.run_id AND bsg.location_id = bp.location_id AND bsg.stream = 'gas'
LEFT JOIN box.pud_forecast_stream bsw
  ON bsw.run_id = bp.run_id AND bsw.location_id = bp.location_id AND bsw.stream = 'water'
WHERE el.recon_status IS DISTINCT FROM 'realized_drift'
  AND el.recon_status IS DISTINCT FROM 'realized_phantom';

GRANT SELECT ON curated.box_scout_locations TO analyst_ro;

COMMENT ON VIEW curated.box_scout_locations IS
'Land team''s BOX locations (sql/69): one row per undrilled stick location that has a BOX record-run forecast AND Steven''s default-deck econ (WTI $70 / HH $3) — nothing else. geom = the stick, EPSG 4326 LineString. box_tier: validated or provisional (report apart). EUR = raw 50-yr technical integral. Econ is Steven''s, display only (D13). Plain view: always current with the latest BOX record run and Steven''s latest push.';
COMMENT ON COLUMN curated.box_scout_locations.stick_id IS 'Location key (unique in this view).';
COMMENT ON COLUMN curated.box_scout_locations.location_name IS 'Stick name.';
COMMENT ON COLUMN curated.box_scout_locations.basin IS 'delaware / midland.';
COMMENT ON COLUMN curated.box_scout_locations.bench IS 'Landing bench (Blue Ox code, e.g. WCA_1, BS2_S).';
COMMENT ON COLUMN curated.box_scout_locations.pad_name IS 'Novi DSU / pad name the stick belongs to.';
COMMENT ON COLUMN curated.box_scout_locations.geom IS 'Stick linestring, EPSG 4326 (in QGIS: LineString / EPSG:4326).';
COMMENT ON COLUMN curated.box_scout_locations.lateral_ft IS 'Lateral length BOX forecast on, ft.';
COMMENT ON COLUMN curated.box_scout_locations.tvd_ft IS 'Planned landing TVD of the stick, ft (Novi''s stick TVD; the depth BOX screened it at). A planned depth, not an offset-well median: check it against local producers before relying on it.';
COMMENT ON COLUMN curated.box_scout_locations.box_tier IS 'validated = bench passed BOX''s out-of-time test; provisional = not yet (D105). Keep the two apart in any total.';
COMMENT ON COLUMN curated.box_scout_locations.oil_eur_bbl IS 'BOX oil EUR, bbl (50-yr technical, no economic limit).';
COMMENT ON COLUMN curated.box_scout_locations.oil_eur_bbl_per_ft IS 'BOX oil EUR per lateral foot, bbl/ft. To total a group: SUM(oil_eur_bbl) / SUM(lateral_ft), not an average of this column.';
COMMENT ON COLUMN curated.box_scout_locations.gas_eur_mcf IS 'BOX gas EUR, mcf.';
COMMENT ON COLUMN curated.box_scout_locations.gas_eur_mcf_per_ft IS 'BOX gas EUR per lateral foot, mcf/ft.';
COMMENT ON COLUMN curated.box_scout_locations.water_eur_bbl IS 'BOX water EUR, bbl.';
COMMENT ON COLUMN curated.box_scout_locations.water_eur_bbl_per_ft IS 'BOX water EUR per lateral foot, bbl/ft.';
COMMENT ON COLUMN curated.box_scout_locations.pv10_mm IS 'Steven''s PV10 at the econ_deck prices, $MM (display only).';
COMMENT ON COLUMN curated.box_scout_locations.pv20_mm IS 'Steven''s PV20 at the econ_deck prices, $MM (display only).';
COMMENT ON COLUMN curated.box_scout_locations.irr_pct IS 'Steven''s IRR, %; blank where he reports none. Summarise with a median, never a sum or mean.';
COMMENT ON COLUMN curated.box_scout_locations.breakeven_wti_pv20 IS 'Steven''s breakeven WTI price at PV20, $/bbl (lower = better).';
COMMENT ON COLUMN curated.box_scout_locations.capex_mm IS 'Steven''s capex, $MM.';
COMMENT ON COLUMN curated.box_scout_locations.econ_deck IS 'Price deck of the econ columns (Steven''s default: WTI $70 / HH $3).';
COMMENT ON COLUMN curated.box_scout_locations.box_run_id IS 'BOX record run the forecast comes from (its basin''s record: one record run per basin, D130).';
COMMENT ON COLUMN curated.box_scout_locations.econ_pushed_at IS 'When Steven pushed these econ numbers.';
