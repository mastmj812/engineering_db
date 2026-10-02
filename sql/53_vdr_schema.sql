-- =============================================================================
-- 53_vdr_schema.sql — seller VDR production data (deal-scoped, raw)
-- =============================================================================
-- Data-room production packages (seller reserves databases + production
-- updates) landed verbatim, one `vdr_id` per data room. First source: the
-- alchemist ARIES project (AC_PROPERTY / AC_DAILY / AC_PRODUCT / section-4
-- AC_ECONOMIC) — REAL daily wellhead volumes, unlike the monthly allocated
-- Novi production (whose TX water is a fixed 0.970 x gas allocation).
--
-- Grain + rules:
--   * Keys are the seller's own property ids (`propnum`); `vdr.property.api10`
--     maps to the suite well key where the seller carries a real API (PDP/PDNP).
--     Seller PUD rows carry placeholder APIs -> api10 NULL by design.
--   * Volumes stored AS REPORTED, negatives included (seller allocation
--     corrections). Consumers decide how to treat them; nothing is cleaned here.
--   * Later files win: a production update revises earlier days (alchemist
--     2026.07.03 update re-allocated 418 oil / 3,107 water days already in the
--     base project). scripts.load_vdr applies files in load_order, last wins.
--   * PRODUCTION ONLY. Seller price decks, expenses, ownership (WI/NRI) and
--     every other economics section are deliberately NOT landed (scope rule:
--     no economics in this stack). seller_forecast_line keeps ARIES section 4
--     (production forecast) lines only.
--
-- DEPENDS ON: nothing (no curated dependency; nothing depends on it yet).
-- REFRESH:    none — loaded on demand per data room:
--               python -m scripts.load_vdr --vdr-id <id> --deal <codename> --path <dir>
--             A re-load replaces every row for that vdr_id in one transaction.
-- RUN:        python -m scripts.apply_vdr_schema   (idempotent)
-- Consumers:  anduin daily-production PDP forecasting (planned).
-- =============================================================================

CREATE SCHEMA IF NOT EXISTS vdr AUTHORIZATION postgres;

CREATE TABLE IF NOT EXISTS vdr.source (
    vdr_id         text PRIMARY KEY CHECK (vdr_id ~ '^[a-z0-9_]+$'),
    deal           text        NOT NULL,
    vendor_format  text        NOT NULL CHECK (vendor_format IN ('aries_accdb')),
    root_path      text        NOT NULL,
    loaded_at      timestamptz NOT NULL DEFAULT now(),
    notes          text
);

CREATE TABLE IF NOT EXISTS vdr.load_file (
    vdr_id        text        NOT NULL REFERENCES vdr.source (vdr_id) ON DELETE CASCADE,
    file_name     text        NOT NULL,
    file_role     text        NOT NULL CHECK (file_role IN ('aries_project', 'daily_update')),
    load_order    integer     NOT NULL,
    file_sha256   text        NOT NULL,
    row_counts    jsonb       NOT NULL,
    data_through  date,
    loaded_at     timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (vdr_id, file_name),
    UNIQUE (vdr_id, load_order)
);

CREATE TABLE IF NOT EXISTS vdr.property (
    vdr_id             text NOT NULL REFERENCES vdr.source (vdr_id) ON DELETE CASCADE,
    propnum            text NOT NULL,
    api14              text,
    api10              text CHECK (api10 ~ '^[0-9]{10}$'),
    well_name          text,
    lease              text,
    well_num           text,
    reserve_category   text,
    status             text,
    land_zone          text,
    county             text,
    state              text,
    operator           text,
    hole_direction     text,
    lateral_length_ft  double precision,
    measured_depth_ft  double precision,
    tvd_ft             double precision,
    upper_perf_ft      double precision,
    lower_perf_ft      double precision,
    surface_lat        double precision,
    surface_lon        double precision,
    bh_lat             double precision,
    bh_lon             double precision,
    spud_date          date,
    frac_date          date,
    first_prod_date    date,
    seller_type_curve  text,
    raw                jsonb NOT NULL,
    PRIMARY KEY (vdr_id, propnum)
);
CREATE INDEX IF NOT EXISTS vdr_property_api10_idx ON vdr.property (api10);

CREATE TABLE IF NOT EXISTS vdr.daily (
    vdr_id     text NOT NULL,
    propnum    text NOT NULL,
    prod_date  date NOT NULL,
    oil_bbl    double precision,
    gas_mcf    double precision,
    water_bbl  double precision,
    hours_on   double precision,
    tbg_psi    double precision,
    csg_psi    double precision,
    choke      double precision,
    bhp_psi    double precision,
    file_name  text NOT NULL,
    PRIMARY KEY (vdr_id, propnum, prod_date),
    FOREIGN KEY (vdr_id, propnum) REFERENCES vdr.property (vdr_id, propnum) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS vdr.monthly (
    vdr_id      text NOT NULL,
    propnum     text NOT NULL,
    prod_month  date NOT NULL CHECK (EXTRACT(day FROM prod_month) = 1),
    oil_bbl     double precision,
    gas_mcf     double precision,
    water_bbl   double precision,
    days_on     integer,
    well_count  double precision,
    file_name   text NOT NULL,
    PRIMARY KEY (vdr_id, propnum, prod_month),
    FOREIGN KEY (vdr_id, propnum) REFERENCES vdr.property (vdr_id, propnum) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS vdr.seller_forecast_line (
    vdr_id      text     NOT NULL REFERENCES vdr.source (vdr_id) ON DELETE CASCADE,
    owner_kind  text     NOT NULL CHECK (owner_kind IN ('property', 'sidefile')),
    owner_key   text     NOT NULL,
    qualifier   text     NOT NULL DEFAULT '',
    sequence    integer  NOT NULL,
    keyword     text     NOT NULL,
    expression  text,
    file_name   text     NOT NULL,
    PRIMARY KEY (vdr_id, owner_kind, owner_key, qualifier, sequence)
);

-- Convenience: daily volumes on the suite well key (real-API wells only).
CREATE OR REPLACE VIEW vdr.well_daily AS
SELECT d.vdr_id, p.api10, d.propnum, p.well_name, p.reserve_category,
       d.prod_date, d.oil_bbl, d.gas_mcf, d.water_bbl, d.hours_on,
       d.tbg_psi, d.csg_psi, d.choke, d.bhp_psi
FROM vdr.daily d
JOIN vdr.property p USING (vdr_id, propnum)
WHERE p.api10 IS NOT NULL;

-- Grants: readable by the analyst role (apps + agent); off the Data API.
GRANT USAGE ON SCHEMA vdr TO analyst_ro;
GRANT SELECT ON ALL TABLES IN SCHEMA vdr TO analyst_ro;
ALTER DEFAULT PRIVILEGES FOR ROLE postgres IN SCHEMA vdr
    GRANT SELECT ON TABLES TO analyst_ro;
REVOKE ALL ON SCHEMA vdr FROM PUBLIC, anon, authenticated;

-- Comments (plain tables keep them; no sql/31 re-apply needed).
COMMENT ON SCHEMA vdr IS
    'Seller data-room (VDR) production packages, deal-scoped, raw. Loaded on demand by '
    'scripts.load_vdr; production only — no seller economics or ownership. See sql/53.';
COMMENT ON TABLE vdr.source IS
    'One row per data room (vdr_id). deal = Blue Ox codename; vendor_format = loader adapter used.';
COMMENT ON TABLE vdr.load_file IS
    'Every file loaded for a vdr_id, in load_order (later files win on overlapping keys), with '
    'sha256, per-table row counts and the last production date the file carries.';
COMMENT ON TABLE vdr.property IS
    'Seller property list (ARIES AC_PROPERTY), one row per seller propnum. api10 = suite well key '
    '(NULL for seller PUD placeholders). raw = the full source row minus commercial columns '
    '(WI/NRI/payout/LOS group are excluded by the loader).';
COMMENT ON COLUMN vdr.property.reserve_category IS
    'Seller reserve category verbatim (ARIES RSV_CAT, e.g. 1PDP / 2PDNP / 4PUD). Seller opinion, not ours.';
COMMENT ON COLUMN vdr.property.seller_type_curve IS
    'Seller type-curve sidefile name (ARIES TYPE_CURVE); joins vdr.seller_forecast_line owner_kind=sidefile.';
COMMENT ON TABLE vdr.daily IS
    'Seller daily wellhead production (ARIES AC_DAILY), AS REPORTED: negatives (allocation '
    'corrections) kept, no downtime cleaning. hours_on is often empty — infer downtime from volumes. '
    'file_name = the file that supplied the surviving row.';
COMMENT ON COLUMN vdr.daily.choke IS 'Choke as reported by the seller (ARIES CHOKE; typically 64ths of an inch).';
COMMENT ON TABLE vdr.monthly IS
    'Seller monthly production (ARIES AC_PRODUCT). prod_month normalized to the first of the month '
    '(ARIES stores month-end dates).';
COMMENT ON TABLE vdr.seller_forecast_line IS
    'Seller ARIES production-forecast lines verbatim: section 4 of AC_ECONOMIC (owner_kind=property, '
    'owner_key=propnum) and of AR_SIDEFILE (owner_kind=sidefile, owner_key=sidefile name). ARIES '
    'syntax, unparsed. A comparison basis only — never an input to our forecasts.';
COMMENT ON VIEW vdr.well_daily IS
    'vdr.daily joined to vdr.property on the suite well key (api10 NOT NULL rows only).';
