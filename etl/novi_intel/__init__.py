"""Novi Intelligence overlay-geometry ingestion (raw_novi_intel pads / land_grid / basin_outline).

OVERLAYS ONLY. The quarterly Novi Intelligence data itself moved to the
Snowflake share (etl/intel_sf -> raw_intel, 2026-07); the file-drop loaders for
sticks / pud_attrs / analytics / arps / forecast were retired with the tables
they fed (dropped 2026-07-10). What remains here is the ingest route for the
DSU pad / land-grid / basin-outline shapefiles, which the share does NOT ship —
Novi is expected to keep delivering those outside the share, so this module
(and its pyshp dependency) stays until Novi's geometry channel changes.
"""
