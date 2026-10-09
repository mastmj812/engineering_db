"""BOX well exclusions — wells kept out of every BOX evidence set (areas, curves, factors, hindcast).

docs/box/exclusions.csv is the record: one row per api10 with the pool, the reason, who decided and
when. Michael-owned; add rows, never edit history. Applied at load time on top of the gate-1 final
well sets (which stay frozen as the gate-1 record). Extents of record are not regenerated for an
exclusion: D27 fills the developed interior, so an interior well never moves an edge.
"""

from __future__ import annotations

from pathlib import Path

import pandas as pd

PATH = Path("docs") / "box" / "exclusions.csv"


def load(path: Path = PATH) -> pd.DataFrame:
    return pd.read_csv(path, dtype={"api10": str})


def drop(wells: pd.DataFrame, path: Path = PATH) -> tuple[pd.DataFrame, pd.DataFrame]:
    """(wells without the excluded api10s, the excluded rows that were present)."""
    ex = load(path)
    hit = wells["api10"].isin(set(ex["api10"]))
    return wells[~hit].reset_index(drop=True), wells[hit].reset_index(drop=True)
