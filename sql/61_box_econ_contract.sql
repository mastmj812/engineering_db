-- =============================================================================
-- 61_box_econ_contract.sql — BOX step 7d: Steven's econ CONTRACT table, keyed on BOX locations
-- =============================================================================
-- docs/box_type_curves_plan.md §5 step 7d, D13 / D63 / D81. Designed from Steven's sandbox table
-- box_econ.pud_econ (sql/52 sandbox; Novi sticks x deck_id; pushed 2026-10-06, schema_version 1.0.0): same metric
-- names, same provenance block, re-keyed from Novi stick_id to the BOX run + location he priced.
--
--   box_econ.box_pud_econ   one row per (BOX forecast run, BOX location, deck, assumption set). Only COVERED locations of a
--                           run can be priced (FK on (run_id, location_id, coverage) with coverage fixed to 'covered').
--                           A priced run cannot be deleted from under the econ (FK, no cascade). downtime_basis is
--                           REQUIRED: the row states which downtime treatment priced the uptime-free BOX volumes (D63:
--                           his own factor OR BOX's published F(k), never both).
--   box_econ.box_pud_econ_tie  view: his echoed oil / gas EUR vs the BOX EUR he priced (the eur_tie check his sandbox
--                           carries as eur_tie_fail), so a mis-loaded curve shows before anyone screens on it.
--
-- D13: econ is display-only. Nothing in schema box reads box_econ; econ never flows back into a forecast or an extent.
-- Owner postgres; box_econ_writer (Steven) gets INSERT / UPDATE / DELETE / SELECT on the table only (no DDL on it);
-- analyst_ro reads. ETL and refresh_all() never touch it. Not exposed to the Supabase Data API. Idempotent.
--
-- Requires sql/52 (box_econ, box_econ_writer) + sql/60 (box.pud_forecast and its (run_id, location_id, coverage) key).
-- RUN: python -m scripts.apply_box_econ_contract      (!! go-apply required)
-- =============================================================================

CREATE TABLE IF NOT EXISTS box_econ.box_pud_econ (
    run_id              bigint  NOT NULL,
    location_id         bigint  NOT NULL,
    coverage            text    NOT NULL DEFAULT 'covered' CHECK (coverage = 'covered'),
    deck_id             text    NOT NULL,
    assumption_set_id   text    NOT NULL,
    downtime_basis      text    NOT NULL CHECK (downtime_basis IN ('steven_downtime_factor', 'box_calendar_factor')),
    wti                 double precision,
    hh                  double precision,
    pv0_mm              double precision,
    pv10_mm             double precision,
    pv15_mm             double precision,
    pv20_mm             double precision,
    pv25_mm             double precision,
    pv30_mm             double precision,
    irr_pct             double precision,
    roi                 double precision,
    payback_months      double precision,
    capex_mm            double precision,
    breakeven_wti_pv20  double precision,
    breakeven_reason    text,
    unpriced_reason     text,
    oil_eur             double precision,
    gas_eur             double precision,
    ll_ft               double precision,
    screen_pass         boolean,
    rejection_step      text,
    build_id            text    NOT NULL,
    schema_version      text    NOT NULL,
    git_sha             text,
    built_at            timestamptz NOT NULL,
    pushed_at           timestamptz NOT NULL DEFAULT now(),
    pushed_by           text    NOT NULL DEFAULT current_user,
    PRIMARY KEY (run_id, location_id, deck_id, assumption_set_id),
    FOREIGN KEY (run_id, location_id, coverage) REFERENCES box.pud_forecast (run_id, location_id, coverage)
);

CREATE INDEX IF NOT EXISTS box_pud_econ_location_ix ON box_econ.box_pud_econ (location_id);
CREATE INDEX IF NOT EXISTS box_pud_econ_deck_ix ON box_econ.box_pud_econ (run_id, deck_id);

GRANT SELECT, INSERT, UPDATE, DELETE ON box_econ.box_pud_econ TO box_econ_writer;
GRANT SELECT ON box_econ.box_pud_econ TO analyst_ro;

CREATE OR REPLACE VIEW box_econ.box_pud_econ_tie AS
SELECT e.run_id, e.location_id, e.deck_id, e.assumption_set_id,
       e.oil_eur AS priced_oil_eur, so.eur AS box_oil_eur, e.oil_eur / NULLIF(so.eur, 0) - 1 AS oil_eur_gap,
       e.gas_eur AS priced_gas_eur, sg.eur AS box_gas_eur, e.gas_eur / NULLIF(sg.eur, 0) - 1 AS gas_eur_gap,
       (abs(e.oil_eur / NULLIF(so.eur, 0) - 1) > 0.005 OR abs(e.gas_eur / NULLIF(sg.eur, 0) - 1) > 0.005) AS eur_tie_fail
FROM box_econ.box_pud_econ e
LEFT JOIN box.pud_forecast_stream so ON so.run_id = e.run_id AND so.location_id = e.location_id AND so.stream = 'oil'
LEFT JOIN box.pud_forecast_stream sg ON sg.run_id = e.run_id AND sg.location_id = e.location_id AND sg.stream = 'gas';

GRANT SELECT ON box_econ.box_pud_econ_tie TO analyst_ro, box_econ_writer;

COMMENT ON TABLE box_econ.box_pud_econ IS
    'Steven''s economics on BOX forecasts (contract table, plan step 7d; D13 display-only, never flows back). One row per (box.forecast_run, '
    'box.location, deck, assumption set); only covered locations of a run can be priced; a priced run cannot be deleted. Metric names and '
    'provenance mirror his sandbox box_econ.pud_econ (schema_version 1.0.0). downtime_basis states which downtime treatment priced the '
    'uptime-free BOX volumes (D63 / D81: his own factor or BOX''s published F(k), never both). oil_eur / gas_eur / ll_ft = what he priced, '
    'echoed for the tie-out view. A screen like Novi''s NPV columns, not authoritative economics inside this stack. See sql/61.';
COMMENT ON COLUMN box_econ.box_pud_econ.downtime_basis IS
    'steven_downtime_factor = BOX uptime-free volumes x his own downtime factor; box_calendar_factor = x box.forecast_run.calendar_factor F(k). '
    'Required: D63 forbids applying both and the row must say which.';
COMMENT ON COLUMN box_econ.box_pud_econ.oil_eur IS
    'The oil EUR (bbl) of the BOX curve as LOADED, before any downtime factor (a downtime factor scales volumes, not the curve); '
    'the tie-out view compares it with box.pud_forecast_stream.eur. Same for gas_eur (mcf).';
COMMENT ON VIEW box_econ.box_pud_econ_tie IS
    'Tie-out: the EUR Steven priced vs the BOX stream EUR of the same run + location (gap = priced / box - 1; eur_tie_fail beyond +-0.5 %). See sql/61.';
