-- =============================================================================
-- 57_box_tc_area.sql — BOX (Blue Ox) type-curve schema, step 4: TC areas
-- =============================================================================
-- docs/box_type_curves_plan.md §4.2 / §5 step 4. App-owned like the rest of schema box
-- (sql/54): the ETL and refresh_all() never touch it. Writer = scripts/box_tc_areas.py --store
-- (postgres, session pooler); apps read via analyst_ro.
--
--   box.tc_area   one row per type-curve area: a contiguous piece of an extent (version of
--                 record), built by box/tc_area.py (contiguity-constrained Ward agglomeration of
--                 1-mi hex cells on log 12-mo oil/ft; k by blocked cross-validation). The areas of
--                 one (extent_id, version) tile that extent. Exactly one area set per extent is the
--                 version of record (partial unique index on is_record).
--
-- Additive vs the §4.2 sketch: version, area_sqmi, response, params, generated_from_run, is_record,
-- created_at / created_by. n_wells = the 12-mo D9 cohort behind the area (CHECK >= 10, D9 floor).
--
-- Requires sql/54 (schema box, box.extent). Not exposed to the Supabase Data API. Idempotent.
-- No matviews; geography expression index created with the table, before any spatial reader runs
-- (sql/26 rule).
-- =============================================================================

CREATE TABLE IF NOT EXISTS box.tc_area (
    area_id             bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    extent_id           bigint  NOT NULL REFERENCES box.extent (extent_id),
    version             integer NOT NULL CHECK (version >= 1),
    area_no             integer NOT NULL CHECK (area_no >= 1),
    geom                extensions.geometry(MultiPolygon, 4326) NOT NULL,
    area_sqmi           double precision,
    n_wells             integer NOT NULL CHECK (n_wells >= 10),
    response            text    NOT NULL DEFAULT 'oil12_per_ft',
    cohort_stats        jsonb   NOT NULL DEFAULT '{}'::jsonb,
    params              jsonb   NOT NULL DEFAULT '{}'::jsonb,
    generated_from_run  text,
    is_record           boolean NOT NULL DEFAULT false,
    created_at          timestamptz NOT NULL DEFAULT now(),
    created_by          text    NOT NULL DEFAULT current_user
);

CREATE UNIQUE INDEX IF NOT EXISTS box_tc_area_version_uq ON box.tc_area (extent_id, version, area_no);
CREATE UNIQUE INDEX IF NOT EXISTS box_tc_area_record_uq  ON box.tc_area (extent_id, area_no) WHERE is_record;
CREATE INDEX IF NOT EXISTS box_tc_area_geom_gix ON box.tc_area USING gist (geom);
CREATE INDEX IF NOT EXISTS box_tc_area_geog_gix ON box.tc_area USING gist ((geom::extensions.geography));

GRANT SELECT ON box.tc_area TO analyst_ro;

COMMENT ON TABLE box.tc_area IS
    'BOX type-curve areas (plan step 4, D9): contiguous pieces of an extent of record, built by box/tc_area.py '
    '(contiguity-constrained Ward agglomeration of 1-mi hex cells on log 12-mo oil/ft of the D9 cohort, k by 5-fold CV on 3-mi blocks, '
    'paired 1-SE rule). The areas of one (extent_id, version) tile the extent. is_record marks the area set of record per extent. '
    'n_wells = 12-mo D9 cohort wells (fp >= 2016, lateral 6,000-13,000 ft, 12 full months) inside the area. Vintage normalized by filter only; '
    'operator/completion confounding accepted for v1. See sql/57.';
COMMENT ON COLUMN box.tc_area.cohort_stats IS
    'Per-area responses in bbl per lateral ft: 12-mo / 24-mo oil P50 (SPE: P10 = HIGH) with their own n, Novi 30-yr oil EUR/ft (vendor horizon, '
    'a screen), member tags (WCA_1 / WCA_2 / WCXY one-way, D19/D20), median first-prod year, top operator share, D1 PUD counts.';
COMMENT ON COLUMN box.tc_area.params IS
    'Method knobs (cell size, field kNN, D9 floor, CV folds/blocks/seed), the CV pick (k_1se, k_min, held-out R2) and the input well set.';
