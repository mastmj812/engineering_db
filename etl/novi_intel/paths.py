"""Resolve Novi Intelligence 3Q25 source files on disk.

Delaware nests files under descriptive subfolders; Midland is flatter. Rather than
hardcode the (differing) full filenames, we walk each basin root and match by token,
so a re-drop with slightly different names still resolves. When the Snowflake API
lands this module is replaced by a Snowflake connection config.
"""

from __future__ import annotations

import os
from pathlib import Path

REPORT_VERSION = "3Q25"

BASIN_DIRS: dict[str, Path] = {
    "delaware": Path(
        r"C:\Users\MichaelMast\Blue Ox Resources\Engineering - General"
        r"\Novi Intelligence\Delaware\3Q25"
    ),
    "midland": Path(
        r"C:\Users\MichaelMast\Blue Ox Resources\Engineering - General"
        r"\Novi Intelligence\Midland\3Q25"
    ),
}

# Stick categories -> predicate on the lowercased zip filename. `startswith`
# avoids matching Other_ML_PDP_Oil.zip / Other_ML_PUD_Oil.zip (no economics).
STICK_ZIP_PRED = {
    "PDP": lambda n: n.startswith("pdp_oil"),
    "PUD": lambda n: n.startswith("pud_oil"),
    "RES": lambda n: n.startswith("resource"),
}
PAD_ZIP_PRED = lambda n: ("pad shapefile" in n) or ("pad)" in n)
GRID_ZIP_PRED = lambda n: "land grid" in n
OUTLINE_ZIP_PRED = lambda n: "outline" in n

# PUD ML-attribute shapefiles (geometry identical to PUD_Oil sticks; attrs only).
# `other_ml` -> spacing/depletion/completion score+tier; `rock_quality` -> RQ score+tier.
PUD_ATTR_ZIP_PRED = {
    "other_ml": lambda n: n.startswith("other_ml_pud_oil"),
    "rock_quality": lambda n: n.startswith("undrilled_rock_quality"),
}


def _find(root: Path, pred, suffix: str) -> Path | None:
    for dirpath, _dirs, files in os.walk(root):
        for f in files:
            if f.lower().endswith(suffix) and pred(f.lower()):
                return Path(dirpath) / f
    return None


def stick_zip(basin: str, category: str) -> Path | None:
    return _find(BASIN_DIRS[basin], STICK_ZIP_PRED[category], ".zip")


def pad_zip(basin: str) -> Path | None:
    return _find(BASIN_DIRS[basin], PAD_ZIP_PRED, ".zip")


def grid_zip(basin: str) -> Path | None:
    return _find(BASIN_DIRS[basin], GRID_ZIP_PRED, ".zip")


def outline_zip(basin: str) -> Path | None:
    return _find(BASIN_DIRS[basin], OUTLINE_ZIP_PRED, ".zip")


def pud_attr_zip(basin: str, kind: str) -> Path | None:
    """kind in {'other_ml','rock_quality'} -> the matching PUD ML-attribute .zip."""
    return _find(BASIN_DIRS[basin], PUD_ATTR_ZIP_PRED[kind], ".zip")


def csv_path(basin: str, kind: str) -> Path | None:
    """kind in {'analytics','arps','forecast'} -> the matching .csv."""
    return _find(BASIN_DIRS[basin], lambda n: kind in n, ".csv")
