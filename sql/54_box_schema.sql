-- =============================================================================
-- 54_box_schema.sql — BOX (Blue Ox) type-curve schema, step 3: scope + extents
-- =============================================================================
-- docs/box_type_curves_plan.md §4.2 / §5 step 3. App-owned like narvi.*: the ETL
-- and refresh_all() never touch schema box. Writers are the BOX batch scripts
-- (scripts/box_extents_export.py --store, scripts/box_extents_import.py --store)
-- running as postgres on the session pooler; apps read via analyst_ro.
--
--   box.bench_scope   basin × bench in/out of BOX scope (D2 list; Michael-owned,
--                     seeded once — re-applying never overwrites his edits)
--   box.extent        one row per extent version: generated (the buffer rule)
--                     or geology_edited (the shapefile round-trip, D7). Exactly
--                     one is_record row per basin × bench (partial unique index).
--   box.extent_edge   the generated extent's boundary split by the walked
--                     segment that set its buffer (the 2×2 per segment)
--
-- Additive vs the §4.2 sketch: bench_scope.member_benches (D19/D20 pooling),
-- extent.is_record / parent_extent_id / diff_stats / area_sqmi, extent_edge
-- side / rule / perf_ratio and edge_class 'hole'.
--
-- Not exposed to the Supabase Data API. Idempotent. No matviews (nothing to
-- REFRESH); geography expression index created with the table, before any
-- spatial reader runs (sql/26 rule).
-- =============================================================================

CREATE SCHEMA IF NOT EXISTS box AUTHORIZATION postgres;
REVOKE ALL ON SCHEMA box FROM PUBLIC;
DO $$
BEGIN
    IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'anon') THEN
        EXECUTE 'REVOKE ALL ON SCHEMA box FROM anon';
    END IF;
    IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'authenticated') THEN
        EXECUTE 'REVOKE ALL ON SCHEMA box FROM authenticated';
    END IF;
END
$$;
GRANT USAGE ON SCHEMA box TO analyst_ro;

-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS box.bench_scope (
    basin           text    NOT NULL CHECK (basin IN ('delaware', 'midland')),
    bench           text    NOT NULL,
    in_scope        boolean NOT NULL,
    member_benches  text[]  NOT NULL DEFAULT '{}',
    reason          text    NOT NULL,
    decided_on      date    NOT NULL,
    decision_ref    text,
    PRIMARY KEY (basin, bench)
);

INSERT INTO box.bench_scope (basin, bench, in_scope, member_benches, reason, decided_on, decision_ref) VALUES
    ('delaware', 'WCA',   true,  '{WCA_1,WCA_2,WCXY}',
     'pilot pool: WCA_1 + WCA_2 pooled for extents and TC areas, split at the curve step (D19); WCXY counts as WCA evidence one-way, never the reverse (D20)',
     '2026-10-06', 'D4, D19, D20'),
    ('delaware', 'BS2_S', true,  '{BS2_S}',  'proven bench; second extent test (D3)', '2026-10-01', 'D3, D4'),
    ('delaware', 'WDFD',  false, '{WDFD}',   'emerging bench: hand-worked in narvi + anduin per deal; shown as not covered, never zero (D2)', '2026-10-06', 'D2'),
    ('midland',  'MISS',  false, '{MISS}',   'emerging bench (D2)', '2026-10-06', 'D2'),
    ('midland',  'BRNT',  false, '{BRNT}',   'emerging bench (D2)', '2026-10-06', 'D2'),
    ('midland',  'MRMC',  false, '{MRMC}',   'emerging bench (D2)', '2026-10-06', 'D2'),
    ('midland',  'WDFD',  false, '{WDFD}',   'emerging bench (D2)', '2026-10-06', 'D2')
ON CONFLICT (basin, bench) DO NOTHING;

-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS box.extent (
    extent_id           bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    basin               text    NOT NULL,
    bench               text    NOT NULL,
    version             integer NOT NULL CHECK (version >= 1),
    source              text    NOT NULL CHECK (source IN ('generated', 'geology_edited')),
    geom                extensions.geometry(MultiPolygon, 4326) NOT NULL,
    area_sqmi           double precision,
    params              jsonb   NOT NULL DEFAULT '{}'::jsonb,
    edge_gap_stats      jsonb   NOT NULL DEFAULT '{}'::jsonb,
    generated_from_run  text,
    parent_extent_id    bigint  REFERENCES box.extent (extent_id),
    diff_stats          jsonb,
    is_record           boolean NOT NULL DEFAULT false,
    superseded_by       bigint  REFERENCES box.extent (extent_id),
    created_at          timestamptz NOT NULL DEFAULT now(),
    created_by          text    NOT NULL DEFAULT current_user,
    FOREIGN KEY (basin, bench) REFERENCES box.bench_scope (basin, bench),
    CHECK (source = 'generated' OR parent_extent_id IS NOT NULL)
);

CREATE UNIQUE INDEX IF NOT EXISTS box_extent_version_uq ON box.extent (basin, bench, version, source);
CREATE UNIQUE INDEX IF NOT EXISTS box_extent_record_uq  ON box.extent (basin, bench) WHERE is_record;
CREATE INDEX IF NOT EXISTS box_extent_geom_gix ON box.extent USING gist (geom);
CREATE INDEX IF NOT EXISTS box_extent_geog_gix ON box.extent USING gist ((geom::extensions.geography));

-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS box.extent_edge (
    extent_id    bigint  NOT NULL REFERENCES box.extent (extent_id) ON DELETE CASCADE,
    edge_no      integer NOT NULL,
    seg_no       integer NOT NULL,
    geom         extensions.geometry(LineString, 4326) NOT NULL,
    side         text,
    gap_ft       double precision,
    buffer_ft    double precision NOT NULL,
    edge_class   text NOT NULL CHECK (edge_class IN ('pinned', 'gap', 'hole')),
    perf_class   text CHECK (perf_class IN ('strong', 'rolled', 'unknown')),
    perf_ratio   double precision,
    rule         text NOT NULL,
    explanation  text,
    PRIMARY KEY (extent_id, edge_no)
);

CREATE INDEX IF NOT EXISTS box_extent_edge_geom_gix ON box.extent_edge USING gist (geom);

-- ---------------------------------------------------------------------------
GRANT SELECT ON ALL TABLES IN SCHEMA box TO analyst_ro;
ALTER DEFAULT PRIVILEGES FOR ROLE postgres IN SCHEMA box GRANT SELECT ON TABLES TO analyst_ro;

COMMENT ON SCHEMA box IS
    'BOX (Blue Ox) basin-wide type curves: scope, extents (later: areas, curves, risk factors, locations, '
    'forecasts). App-owned like narvi.*; ETL and refresh_all() never touch it. Plan: docs/box_type_curves_plan.md. See sql/54.';
COMMENT ON TABLE box.bench_scope IS
    'Basin x bench in/out of BOX scope (plan D2). member_benches = the formation_blueox codes pooled into the bench '
    '(WCA = WCA_1 + WCA_2, with WCXY as one-way evidence, D19/D20). Michael-owned: sql/54 seeds with ON CONFLICT DO NOTHING.';
COMMENT ON TABLE box.extent IS
    'BOX bench extents, one row per version x source. generated = lateral lines + variable buffer (D21, box/extent.py); '
    'geology_edited = the geologist''s shapefile edit of a generated version (D7, parent_extent_id), with diff_stats. '
    'is_record marks the single version of record per basin x bench. geom EPSG:4326; area_sqmi planar (UTM 13N ft).';
COMMENT ON TABLE box.extent_edge IS
    'Boundary of a generated extent split by the walked step-2 ring segment whose sector it lies in: edge_class pinned/gap/hole, '
    'perf_class (12-mo oil/ft of the edge wells vs the interior median, >=0.85 strong, <0.70 rolled), buffer_ft and the rule that set it, '
    'explanation = the geology flag text. seg_no = -1 for hole rings.';
