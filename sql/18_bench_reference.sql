-- =============================================================================
-- 18 — curated.bench_reference  (spatial reference for sub-bench inference)
--
-- The splitting-bench curated laterals, pre-joined to formation_blueox and
-- GiST-indexed, so the nearest-neighbour lookups in sql/19 (and, later, the §6
-- reconciliation matching) run off a small indexed table instead of the lossy
-- "KNN-then-join-then-filter" pattern over curated.wells + curated.formation_blueox.
--
-- That pattern was fine at LOO-sample scale but did not finish in 40+ min across
-- the full ~55k coarse sticks: the planner can't keep the geometry index hot when
-- every candidate has to be joined to formation_blueox and filtered to the same
-- parent. Materialising the candidate pool once (~30k rows) with its own GiST
-- index turns each KNN into a ~1 ms index probe.
--
-- Scope: only the parents that actually split (Delaware Avalon / Wolfcamp A /
-- Wolfcamp B; Midland Wolfcamp B). `parent` = left(code,3) (WCA/WCB/AVA).
--
-- DEPENDS ON: curated.wells (sql/04), curated.formation_blueox (sql/16).
-- REFRESH: alongside curated.formation_blueox (its source). Cheap (~30k rows).
--   REFRESH MATERIALIZED VIEW CONCURRENTLY curated.bench_reference;
-- =============================================================================


DROP MATERIALIZED VIEW IF EXISTS curated.bench_reference CASCADE;


CREATE MATERIALIZED VIEW curated.bench_reference AS
SELECT
    w.api10,
    w.wellstick_geom        AS geom,
    w.tvd_ft                AS tvd,
    fb.basin_blueox         AS basin,
    fb.formation_blueox     AS bench,
    left(fb.formation_blueox, 3) AS parent
FROM curated.wells w
JOIN curated.formation_blueox fb ON fb.api10 = w.api10
WHERE fb.formation_blueox IN ('WCA_1','WCA_2','WCB_1','WCB_2','AVA_0','AVA_1','AVA_2')
  AND fb.basin_blueox IN ('delaware','midland')
  AND w.wellstick_geom IS NOT NULL
  AND w.tvd_ft IS NOT NULL
;


-- Unique on api10 — required for REFRESH ... CONCURRENTLY.
CREATE UNIQUE INDEX idx_bench_reference_api10
    ON curated.bench_reference (api10);

-- KNN driver: <-> ordering on the lateral geometry.
CREATE INDEX idx_bench_reference_geom
    ON curated.bench_reference USING gist (geom);

-- Cheap recheck filter alongside the KNN.
CREATE INDEX idx_bench_reference_grp
    ON curated.bench_reference (basin, parent);


COMMENT ON MATERIALIZED VIEW curated.bench_reference IS
'Splitting-bench curated laterals (WCA_1/2, WCB_1/2, AVA_0/1/2; Delaware + Midland), pre-joined to formation_blueox and GiST-indexed on geom. Candidate pool for the TVD-aware sub-bench inference in curated.intel_formation_blueox (sql/19); reusable as the spatial reference for §6 reconciliation matching. Refresh with curated.formation_blueox.';
