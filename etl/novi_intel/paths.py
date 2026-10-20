"""Resolve Novi Intelligence overlay shapefiles (pads / land grid / outline) on disk.

Delaware nests files under descriptive subfolders; Midland is flatter. Rather than
hardcode the (differing) full filenames, we walk each basin root and match by token,
so a re-drop with slightly different names still resolves. Only the overlay
geometries are sourced from the file drop — everything else comes from the
Snowflake share (etl/intel_sf).

VINTAGES ARE PER LAYER (2026-10-20). Novi's 2026Q3 drop ships DSU pad polygons
but no land grid or basin outline, so:
  * pads              -> PADS_REPORT_VERSION / PADS_BASIN_DIRS (2026Q3)
  * land grid/outline -> REPORT_VERSION / BASIN_DIRS (frozen at the 3Q25 drop)
PADS_REPORT_VERSION uses the share's label ('2026Q3') on purpose: sql/67 joins
raw_novi_intel.pads to curated.intel_locations ON report_version, so a pad load
only takes effect for the vintage it was drawn for.
`scripts.apply_intel_pad_geom --load-pads` refuses when the two labels disagree.

The 2026Q3 pad polygons arrive NESTED: an outer shapefile zip holds a
"...Pad...Summary..." zip in a Strip and a Mid-Cycle flavour (same polygons,
different NPV deck). We load the Mid-Cycle one. The 3Q25 drop shipped the pad
zip directly; pad_source() resolves both layouts.
"""

from __future__ import annotations

import os
import zipfile
from pathlib import Path

_ROOT = Path(r"C:\Users\MichaelMast\Blue Ox Resources\Engineering - General\Novi Intelligence")

# Land grid / basin outline: frozen at the 3Q25 drop (2026Q3 shipped neither).
REPORT_VERSION = "3Q25"

BASIN_DIRS: dict[str, Path] = {
    "delaware": _ROOT / "Delaware" / "3Q25",
    "midland": _ROOT / "Midland" / "3Q25",
}

# DSU pad polygons. Must equal curated.intel_locations.report_version.
PADS_REPORT_VERSION = "2026Q3"

PADS_BASIN_DIRS: dict[str, Path] = {
    "delaware": _ROOT / "Delaware" / "3Q26",
    "midland": _ROOT / "Midland" / "3Q26",
}

PAD_ZIP_PRED = lambda n: ("pad shapefile" in n) or ("pad)" in n)
GRID_ZIP_PRED = lambda n: "land grid" in n
OUTLINE_ZIP_PRED = lambda n: "outline" in n
# 2026Q3 outer drop: "shapefile-download-delaware-..." / "shapefiles-midland-...".
OUTER_SHAPEFILE_PRED = lambda n: "shapefile" in n


def nested_pad_member(names: list[str]) -> str | None:
    """The Mid-Cycle pad-summary zip inside a 2026Q3 outer shapefile zip.

    Delaware: '<folder>/Economic_Mid_Cycle_NPV_Pad_Summary.zip';
    Midland:  'Pad_NPV_Summary_Mid_Cycle.zip'. Strip carries identical polygons.
    """
    for n in names:
        low = n.lower().rsplit("/", 1)[-1]
        if low.endswith(".zip") and "pad" in low and "summary" in low and "mid_cycle" in low:
            return n
    return None


def _find(root: Path, pred, suffix: str) -> Path | None:
    for dirpath, _dirs, files in os.walk(root):
        for f in files:
            if f.lower().endswith(suffix) and pred(f.lower()):
                return Path(dirpath) / f
    return None


def pad_source(basin: str, root: Path | None = None) -> tuple[Path, str | None] | None:
    """(zip on disk, nested member or None) holding the basin's DSU pad polygons.

    Prefers the 2026Q3 nested layout (outer shapefile zip -> Mid-Cycle pad
    summary zip); falls back to a directly shipped pad zip (3Q25 layout).
    """
    root = root if root is not None else PADS_BASIN_DIRS[basin]
    for dirpath, _dirs, files in os.walk(root):
        for f in sorted(files):
            low = f.lower()
            if not (low.endswith(".zip") and OUTER_SHAPEFILE_PRED(low)):
                continue
            outer = Path(dirpath) / f
            with zipfile.ZipFile(outer) as z:
                member = nested_pad_member(z.namelist())
            if member:
                return outer, member
    direct = _find(root, PAD_ZIP_PRED, ".zip")
    return (direct, None) if direct else None


def grid_zip(basin: str) -> Path | None:
    return _find(BASIN_DIRS[basin], GRID_ZIP_PRED, ".zip")


def outline_zip(basin: str) -> Path | None:
    return _find(BASIN_DIRS[basin], OUTLINE_ZIP_PRED, ".zip")
