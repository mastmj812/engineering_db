-- =============================================================================
-- 39 — curated.enverus_lateral_lines  (standalone, Enverus survey-derived laterals)
--
-- Why: curated.wells.wellstick_geom (sql/04) is a fixed 4-point polyline over
-- Novi's SHL→LP→MP→BHL columns. For u-turn / horseshoe wells those four points
-- all cluster near the surface hole (Novi's MP is not a mid-lateral point — on
-- known horseshoes it sits 3–27 ft from the SHL, and the BHL genuinely returns
-- near surface), so the rendered stick degenerates to a short jagged line.
-- Enverus's LateralLine WKT traces the real path (81–93 vertices, full
-- ~12.7k-ft horseshoe on the Vanadium 32 poster wells) and covers 99.0% of
-- wells_enriched horizontals (84,312 / 85,128 as of 2026-08).
--
-- Standalone on purpose (the sql/16 factoring rationale): consuming apps
-- COALESCE this over wellstick_geom, so sql/04 stays untouched — no
-- DROP-CASCADE of the curated.wells chain to improve stick geometry.
--
-- Consumer: anduin backend/app/warehouse_client/wells.py
--   COALESCE(ST_AsText(ell.lateral_geom), ST_AsText(we.wellstick_geom))
-- sql/04's wellstick_geom remains the fallback of record for the ~1% of
-- horizontals with no usable Enverus line.
--
-- Dedupe mirrors sql/04's enverus_latest CTE (latest completion first via
-- completiondate DESC NULLS LAST, completionid DESC NULLS LAST) with one
-- DELIBERATE divergence: the LateralLine validity predicates sit INSIDE the
-- CTE's WHERE, so DISTINCT ON picks the latest completion THAT HAS a usable
-- LateralLine — a newer completion row lacking one must not null out the well.
--
-- Guards, cheapest first: non-NULL, <> 'NULL' (Enverus returns the literal
-- string "NULL" for missing text), LIKE 'LINESTRING%' (textual pre-filter so
-- ST_GeomFromText never sees garbage), then post-parse ST_NPoints >= 2 and
-- ST_IsValid. extensions.* is schema-qualified throughout: PG17 runs matview
-- CREATE/REFRESH under a restricted search_path.
--
-- No GiST index by design: the only access path is the api10 equi-join from
-- anduin's header fetch; no spatial predicate targets this matview. Add one
-- only when a spatial consumer appears.
--
-- Run order: after the raw_enverus load; nothing depends on it (the CASCADE
-- on the guard drop is inert — stated here so nobody fears it). Nightly via
-- etl/db.py:_CURATED_MATVIEWS (first entry: raw-only input, tiny, ~85k rows).
--   psql -d oilgas -f sql/39_enverus_lateral_lines.sql
-- =============================================================================


DROP MATERIALIZED VIEW IF EXISTS curated.enverus_lateral_lines CASCADE;


CREATE MATERIALIZED VIEW curated.enverus_lateral_lines AS
WITH latest_with_line AS (
    -- One row per wellbore: latest Enverus completion event that carries a
    -- parseable LateralLine (see header — deliberately NOT latest-overall).
    SELECT DISTINCT ON (LEFT(api_uwi_14_unformatted, 10))
        LEFT(api_uwi_14_unformatted, 10) AS api10,
        lateralline
    FROM raw_enverus.wells
    WHERE deleteddate IS NULL
      AND api_uwi_14_unformatted IS NOT NULL
      AND lateralline IS NOT NULL
      AND lateralline <> 'NULL'
      AND lateralline LIKE 'LINESTRING%'
    ORDER BY LEFT(api_uwi_14_unformatted, 10),
             completiondate DESC NULLS LAST,
             completionid DESC NULLS LAST
),
parsed AS (
    SELECT
        api10,
        extensions.ST_SetSRID(
            extensions.ST_GeomFromText(lateralline), 4326) AS lateral_geom
    FROM latest_with_line
)
SELECT api10, lateral_geom
FROM parsed
WHERE extensions.ST_NPoints(lateral_geom) >= 2
  AND extensions.ST_IsValid(lateral_geom)
;


-- Unique on api10 — required for REFRESH ... CONCURRENTLY (and the CI lint).
CREATE UNIQUE INDEX idx_curated_enverus_lateral_lines_api10
    ON curated.enverus_lateral_lines (api10);


COMMENT ON MATERIALIZED VIEW curated.enverus_lateral_lines IS
'Enverus survey-derived lateral path (LateralLine WKT parsed to LINESTRING 4326), one row per api10 — latest completion event that has a usable line (deliberately not latest-overall, so a newer completion row without a LateralLine cannot null out the well). Guards: literal-string ''NULL'' sentinel rejected, LINESTRING% textual pre-filter, ST_NPoints >= 2, ST_IsValid. Built to fix u-turn/horseshoe sticks: the 4-point Novi SHL/LP/MP/BHL wellstick_geom in curated.wells degenerates when the lateral doubles back. Consumer: anduin header sync COALESCEs this over wells_enriched.wellstick_geom. Nightly refresh; standalone so sql/04 never rebuilds for stick-geometry work.';
COMMENT ON COLUMN curated.enverus_lateral_lines.api10 IS
'10-digit API wellbore id (LEFT(Enverus api14, 10)); the universal well key. PK / unique index.';
COMMENT ON COLUMN curated.enverus_lateral_lines.lateral_geom IS
'Full lateral path as LINESTRING (SRID 4326) from Enverus LateralLine WKT; typically 60-120 vertices, traces u-turn/horseshoe geometry the 4-point wellstick cannot. Vertex direction (heel->toe vs reverse) is unspecified by Enverus — consumers must not depend on order.';
