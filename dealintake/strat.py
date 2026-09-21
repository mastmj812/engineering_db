"""Gate 1: land-file depth bounds that are FORMATION PHRASES, not depths.

Current-SOP land packages state some rights stratigraphically ("Top of Bone
Spring Formation" -> "Top of Wolfcamp Formation"). That is not a depth and is
never turned into one; it is a position in the basin's stratigraphic column
(config/strat_column.yaml, a mirror of Engineering's nomenclature.xlsx), so
the allowed benches follow by order (Michael, 2026-09-21):

    Top of Bone Spring -> Top of Wolfcamp  =  AVA_0 .. BS3_S   (delaware)

`Surface` and `COE` ("center of earth" = unbounded below) are open ends. A
numeric bound stays a depth and is handled by dealintake.benches against
local offset medians. Everything here is a PROPOSAL for the reviewer.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml

DEFAULT_PATH = (
    Path(__file__).resolve().parent.parent
    / ".claude" / "skills" / "deal-intake" / "config" / "strat_column.yaml"
)

_NUM = re.compile(r"-?\d[\d,]*(?:\.\d+)?")
_SURFACE = re.compile(r"\bsurface\b", re.IGNORECASE)
_COE = re.compile(r"\b(coe|center of (the )?earth|centre of (the )?earth)\b", re.IGNORECASE)
_EDGE = re.compile(r"\b(top|base|bottom)\b", re.IGNORECASE)

# Codes that exist in only one basin's column — enough to tell the basin from
# a unit's local bench list without a warehouse round-trip.
_DELAWARE_ONLY = {"AVA_0", "AVA_1", "AVA_2", "BS1_S", "BS2_C", "BS2_S", "BS3_C", "BS3_S", "WCXY", "WCA_2"}
_MIDLAND_ONLY = {"US", "MS", "JM", "LSSH", "DEAN", "MRMC"}


class StratError(ValueError):
    pass


@dataclass(frozen=True)
class Bound:
    kind: str                    # surface | coe | depth | strat | unknown | missing
    text: str | None = None
    depth_ft: float | None = None
    edge: str | None = None      # top | base          (kind == strat)
    group: str | None = None     # strat_column group  (kind == strat)

    def describe(self) -> str:
        if self.kind == "depth":
            return f"{self.depth_ft:,.0f} ft"
        if self.kind == "strat":
            return f"{self.edge.title()} of {self.group.replace('_', ' ').title()}"
        return {"surface": "Surface", "coe": "COE (unbounded below)", "missing": "—"}.get(
            self.kind, f"UNRESOLVED {self.text!r}")


@dataclass(frozen=True)
class Column:
    raw: dict[str, Any]

    @property
    def version(self) -> int:
        return int(self.raw["strat_version"])

    def benches(self, basin: str) -> list[str]:
        return list(self.raw["column"][basin])

    def group_for(self, text: str, basin: str) -> str | None:
        """Longest alias found in `text` as a whole word/phrase."""
        low = text.lower()
        best: tuple[int, str] | None = None
        for name, g in self.raw["groups"].get(basin, {}).items():
            for alias in g["aliases"]:
                if re.search(rf"(?<![a-z0-9]){re.escape(alias)}(?![a-z0-9])", low) and (
                        best is None or len(alias) > best[0]):
                    best = (len(alias), name)
        return best[1] if best else None

    def group_benches(self, group: str, basin: str) -> list[str]:
        return list(self.raw["groups"][basin][group]["benches"])


def load(path: str | Path | None = None) -> Column:
    raw = yaml.safe_load(Path(path or DEFAULT_PATH).read_text(encoding="utf-8"))
    for basin, col in raw["column"].items():
        for name, g in raw["groups"].get(basin, {}).items():
            idx = [col.index(b) for b in g["benches"]]          # ValueError = bench not in column
            if idx != list(range(idx[0], idx[0] + len(idx))):
                raise StratError(f"{basin}.{name}: benches must be contiguous in the column")
    return Column(raw)


def infer_basin(bench_codes: list[str]) -> str | None:
    codes = set(bench_codes)
    d, m = len(codes & _DELAWARE_ONLY), len(codes & _MIDLAND_ONLY)
    if d == m:
        return None
    return "delaware" if d > m else "midland"


def parse_bound(text: Any, col: Column, basin: str | None) -> Bound:
    if text is None or not str(text).strip():
        return Bound("missing")
    if isinstance(text, (int, float)):
        return Bound("depth", str(text), float(text))
    s = str(text).strip()
    if _COE.search(s):
        return Bound("coe", s)
    # Formation phrase BEFORE the number test: "Top of 3rd Bone Spring" has a digit.
    e = _EDGE.search(s)
    group = col.group_for(s, basin) if basin else None
    if e and group:
        return Bound("strat", s, edge="base" if e.group(1).lower() in ("base", "bottom") else "top", group=group)
    m = _NUM.search(s)
    if m:
        return Bound("depth", s, float(m.group(0).replace(",", "")))
    if _SURFACE.search(s):
        return Bound("surface", s)
    return Bound("unknown", s)


def allowed_benches(lo: Bound, hi: Bound, col: Column, basin: str) -> list[str] | None:
    """Benches between two bounds BY STRATIGRAPHIC ORDER, shallow -> deep.
    None when neither bound is a formation phrase (a purely numeric window is
    judged against local depths instead). A numeric/open bound on one side
    leaves that side open here — the depth test still applies to it."""
    if "strat" not in (lo.kind, hi.kind):
        return None
    column = col.benches(basin)
    start, stop = 0, len(column)
    if lo.kind == "strat":
        g = col.group_benches(lo.group, basin)
        start = column.index(g[0]) if lo.edge == "top" else column.index(g[-1]) + 1
    if hi.kind == "strat":
        g = col.group_benches(hi.group, basin)
        stop = column.index(g[0]) if hi.edge == "top" else column.index(g[-1]) + 1
    return column[start:stop]


def name_hint(unit_name: str | None, col: Column, basin: str | None) -> tuple[str, list[str]] | None:
    """A formation named in the DSU name ("2-11 (WCB)") -> (group, benches).
    Used ONLY to break ties on benches sitting at a numeric window's edge."""
    if not unit_name or not basin:
        return None
    g = col.group_for(unit_name, basin)
    return (g, col.group_benches(g, basin)) if g else None
