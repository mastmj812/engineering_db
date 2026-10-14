-- =============================================================================
-- 59 — curated.well_neighbors  (3-D well-to-well spacing PAIR table: one row per
--      producing horizontal x co-extent neighbour lateral, any bench)
--
-- PURPOSE: the raw geometry behind BOX's 3-D spacing measure
-- (docs/box/step6-2026-10-12/SPACING_3D_SCOPE.md, FINDINGS §7–§9). sql/47
-- (codev_context) computes neighbour pairs but keeps only per-BENCH aggregates
-- (nearest dtvd, median distance), too coarse to see a stacked cube (Burton Flat
-- 3 1). This matview keeps every pair with the facts the per-well features are
-- derived from; the FEATURES (lateral spacing left / right, gunbarrel drainage
-- cross-section, parent depletion) are computed downstream in box/spacing3d.py so
-- their knobs (anisotropy, TVD windows, gate, overlap floor) stay tunable without
-- DDL. Storage settings are deliberately GENEROUS (a narrower gate / higher
-- overlap floor is a filter downstream; a wider one would be a rebuild).
--
-- PAIR RULE (rule 9 co-extent, never bare min-distance; mirrors sql/47):
--   * lateral line  LP -> BHL when Novi ships a landing point distinct from the
--                   stick end point; else the whole stick (sql/47's rule).
--   * candidate     ST_DWithin(stick, stick, 1,207.008 m = 3,960 ft), geography —
--                   served by sql/26's idx_curated_wells_wellstick_geog (EXPLAIN-
--                   asserted by scripts/apply_well_neighbors.py).
--   * overlap_frac  |locate(nbr.start) - locate(nbr.end)| along the subject
--                   lateral (normalised, ST_LineLocatePoint); stored when >= 0.10.
--   * dmin_ft       lateral-to-lateral closest distance (planar, EPSG:32613);
--                   stored when <= 3,960 ft.
--   * dxy_ft        SIGNED mean perpendicular offset of the neighbour lateral over
--                   the overlapped span: 11 points evenly spaced on the subject
--                   lateral between the two locate() values, each to its closest
--                   point on the neighbour (ST_ClosestPoint); sign = side of the
--                   subject's local LP -> BHL heading (+ = left). Gunbarrel
--                   offset, not closest approach. Planar in UTM 13N (EPSG:32613),
--                   ft = m x 3.280839895 — the frame box/spacing3d.py uses, so the
--                   Python features reproduce from this table exactly.
--   * dz_ft         neighbour TVD - subject TVD (negative = shallower); one TVD
--                   per well (v1). NULL when either TVD is missing.
--   * dfp_days      neighbour first production - subject first production
--                   (relation downstream: < -180 parent, |..| <= 180 codev,
--                   > 180 child — sql/47's window). Children are STORED; features
--                   as of first production exclude them.
--   Subject / neighbour universe: producing horizontals with a stick (sql/40
--   is_horizontal semantics via COALESCE(novi_slant_calculated,
--   enverus_trajectory)), first_production_date NOT NULL, any bench.
--   EPSG:32613 is the Delaware zone; across the Midland its scale error is
--   ~0.1 % (spacing only, no area accumulates it).
--
-- GRAIN: (api10, nbr_api10), directed (both directions stored; overlap and the
--   offset sign are subject-relative).
--
-- DEPENDS ON: curated.wells (sql/04), sql/26 geography index. Base table only
--   (no formation join: bench is a property of either well, joined downstream).
--   CASCADE VICTIM of a sql/04 wells rebuild (re-run after sql/26).
-- REFRESH: on demand / quarterly with the curve refresh (not in the nightly
--   list yet — build time recorded by the apply script; registering it nightly is
--   a separate decision). UNIQUE (api10, nbr_api10) supports CONCURRENTLY.
-- RUN: python -m scripts.apply_well_neighbors   (exec + validate). Idempotent:
--   type-aware DROP ... CASCADE then CREATE ... WITH DATA.
-- =============================================================================

DO $$
BEGIN
    IF EXISTS (SELECT 1 FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace
               WHERE n.nspname = 'curated' AND c.relname = 'well_neighbors' AND c.relkind = 'm') THEN
        EXECUTE 'DROP MATERIALIZED VIEW curated.well_neighbors CASCADE';
    ELSIF EXISTS (SELECT 1 FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace
                  WHERE n.nspname = 'curated' AND c.relname = 'well_neighbors' AND c.relkind = 'v') THEN
        EXECUTE 'DROP VIEW curated.well_neighbors CASCADE';
    END IF;
END $$;

CREATE MATERIALIZED VIEW curated.well_neighbors AS
WITH subj AS (
    SELECT
        w.api10,
        w.first_production_date                                         AS fp,
        w.tvd_ft,
        w.wellstick_geom                                                AS g,
        extensions.ST_Transform(CASE
            WHEN w.landing_point_lat IS NOT NULL
             AND w.landing_point_lon IS NOT NULL
             AND NOT extensions.ST_Equals(
                     extensions.ST_SetSRID(extensions.ST_Point(w.landing_point_lon, w.landing_point_lat), 4326),
                     extensions.ST_EndPoint(w.wellstick_geom))
            THEN extensions.ST_MakeLine(
                     extensions.ST_SetSRID(extensions.ST_Point(w.landing_point_lon, w.landing_point_lat), 4326),
                     extensions.ST_EndPoint(w.wellstick_geom))
            ELSE w.wellstick_geom
        END, 32613)                                                     AS lat
    FROM curated.wells w
    WHERE COALESCE(w.novi_slant_calculated, w.enverus_trajectory) ILIKE '%horizontal%'
      AND w.first_production_date IS NOT NULL
      AND w.wellstick_geom IS NOT NULL
)
-- One LATERAL per subject reading curated.wells directly (sql/47's shape: a
-- CTE-to-CTE join let the planner misestimate and go quadratic).
SELECT
    s.api10,
    nb.api10                                                    AS nbr_api10,
    round(loc.overlap::numeric, 4)::float8                      AS overlap_frac,
    round((extensions.ST_Distance(s.lat, nb.nlat) * 3.280839895)::numeric, 1)::float8 AS dmin_ft,
    round(off.dxy_ft::numeric, 1)::float8                       AS dxy_ft,
    (nb.tvd_ft - s.tvd_ft)::float8                              AS dz_ft,
    (nb.fp - s.fp)                                              AS dfp_days
FROM subj s
CROSS JOIN LATERAL (
    SELECT
        w2.api10,
        w2.first_production_date                                AS fp,
        w2.tvd_ft,
        extensions.ST_Transform(CASE
            WHEN w2.landing_point_lat IS NOT NULL
             AND w2.landing_point_lon IS NOT NULL
             AND NOT extensions.ST_Equals(
                     extensions.ST_SetSRID(extensions.ST_Point(w2.landing_point_lon, w2.landing_point_lat), 4326),
                     extensions.ST_EndPoint(w2.wellstick_geom))
            THEN extensions.ST_MakeLine(
                     extensions.ST_SetSRID(extensions.ST_Point(w2.landing_point_lon, w2.landing_point_lat), 4326),
                     extensions.ST_EndPoint(w2.wellstick_geom))
            ELSE w2.wellstick_geom
        END, 32613)                                             AS nlat
    FROM curated.wells w2
    WHERE extensions.ST_DWithin(w2.wellstick_geom::extensions.geography,
                                s.g::extensions.geography, 1207.008)          -- BAKED 3,960 ft candidate gate
      AND w2.api10 <> s.api10
      AND COALESCE(w2.novi_slant_calculated, w2.enverus_trajectory) ILIKE '%horizontal%'
      AND w2.first_production_date IS NOT NULL
) nb
CROSS JOIN LATERAL (
    SELECT least(a, b) AS lo, greatest(a, b) AS hi, abs(a - b) AS overlap
    FROM (SELECT extensions.ST_LineLocatePoint(s.lat, extensions.ST_StartPoint(nb.nlat)) AS a,
                 extensions.ST_LineLocatePoint(s.lat, extensions.ST_EndPoint(nb.nlat))   AS b) ab
) loc
CROSS JOIN LATERAL (
    SELECT avg(
               extensions.ST_Distance(pt.p, pt.q) * 3.280839895
               * CASE WHEN (extensions.ST_X(pt.p2) - extensions.ST_X(pt.p1)) * (extensions.ST_Y(pt.q) - extensions.ST_Y(pt.p))
                         - (extensions.ST_Y(pt.p2) - extensions.ST_Y(pt.p1)) * (extensions.ST_X(pt.q) - extensions.ST_X(pt.p)) < 0
                      THEN -1 ELSE 1 END
           ) AS dxy_ft
    FROM generate_series(0, 10) k
    -- clamp: lo + (hi - lo) * 10 / 10 can round a hair past 1 (shapely clamps the same way)
    CROSS JOIN LATERAL (SELECT greatest(0.0, least(1.0, loc.lo + (loc.hi - loc.lo) * k / 10.0)) AS t) tt
    CROSS JOIN LATERAL (
        SELECT extensions.ST_LineInterpolatePoint(s.lat, tt.t)                      AS p,
               extensions.ST_ClosestPoint(nb.nlat, extensions.ST_LineInterpolatePoint(s.lat, tt.t)) AS q,
               extensions.ST_LineInterpolatePoint(s.lat, greatest(0.0, tt.t - 0.001)) AS p1,
               extensions.ST_LineInterpolatePoint(s.lat, least(1.0, tt.t + 0.001))    AS p2
    ) pt
) off
WHERE loc.overlap >= 0.10                                                         -- BAKED storage floor
  AND extensions.ST_Length(s.lat) > 0 AND extensions.ST_Length(nb.nlat) > 0
  AND extensions.ST_Distance(s.lat, nb.nlat) * 3.280839895 <= 3960.0
WITH DATA;

-- UNIQUE: REQUIRED for REFRESH ... CONCURRENTLY (and the CI SQL lint).
CREATE UNIQUE INDEX idx_well_neighbors_pk
    ON curated.well_neighbors (api10, nbr_api10);
-- Reverse lookups (which subjects see a given neighbour — e.g. a parent's influence).
CREATE INDEX idx_well_neighbors_nbr
    ON curated.well_neighbors (nbr_api10);
