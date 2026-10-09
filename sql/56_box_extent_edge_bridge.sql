-- =============================================================================
-- 56_box_extent_edge_bridge.sql — allow edge_class 'bridge' on box.extent_edge
-- (authored as sql/55; renumbered 2026-10-09 — sql/55 is 55_novi_reportedwelltype.sql, merged first)
-- =============================================================================
-- sql/54 predates plan D27 (2026-10-09, the development envelope). D27 places some
-- extent edge where the envelope BRIDGED a gap between development trends; those
-- boundary pieces carry edge_class = 'bridge' (box/extent_report.edges_frame) so
-- geology can see where a bridge, not a well, set the line. sql/54's CHECK only
-- allowed pinned / gap / hole, so the first --store of the D27 extents was refused
-- (rolled back, nothing written).
--
-- DEPENDS ON: sql/54. Idempotent (drop-if-exists + add). No data rewritten.
-- RUN: python -m scripts.apply_box_schema   (applies sql/54 then sql/56, validates)
-- =============================================================================

ALTER TABLE box.extent_edge DROP CONSTRAINT IF EXISTS extent_edge_edge_class_check;
ALTER TABLE box.extent_edge ADD CONSTRAINT extent_edge_edge_class_check
    CHECK (edge_class IN ('pinned', 'gap', 'hole', 'bridge'));

COMMENT ON TABLE box.extent_edge IS
    'Boundary of a generated extent split by the walked step-2 ring segment whose sector it lies in: edge_class pinned/gap/hole, '
    'or bridge where the D27 development envelope bridged a gap between development trends; perf_class (12-mo oil/ft of the edge '
    'wells vs the interior median, >=0.85 strong, <0.70 rolled), buffer_ft and the rule that set it, explanation = the geology flag '
    'text. seg_no = -1 for hole rings. See sql/54, sql/56.';
