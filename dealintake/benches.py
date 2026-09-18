"""Gate 1: bench PROPOSAL from a depth window — a starting point, never the decision.

Declared land-file depths (Min_Depth / Max_Depth) are frequently
stratigraphic picks on a reference log miles away (Toucan: declared 9,515 ft
~ 9,950 ft correlated on-parcel). They are parsed and echoed verbatim; the
engineer's CORRELATED window (entered in narvi's deal-terms card, passed here
as `correlated_window`) takes precedence and is what the proposal uses when
given. Local bench depth = narvi /api/warehouse/zones median_tvd_ft (offset-
well medians with the permit-round filter — workspace rule 10), never tops.
"""

from __future__ import annotations

import re
from typing import Any

_NUM = re.compile(r"(-?\d[\d,]*(?:\.\d+)?)")
_SURFACE = re.compile(r"\bsurface\b", re.IGNORECASE)


def parse_depth(text: Any) -> float | None:
    """'9,515'' -> 9515.0; 'Surface' -> 0.0; '10000 ft TVD' -> 10000.0;
    'Base of Wolfcamp' / '' / None -> None (non-numeric: reviewer resolves)."""
    if text is None:
        return None
    if isinstance(text, (int, float)):
        return float(text)
    s = str(text).strip()
    if not s:
        return None
    if _SURFACE.search(s) and not _NUM.search(s):
        return 0.0
    m = _NUM.search(s)
    return float(m.group(1).replace(",", "")) if m else None


def declared_window(attributes: dict[str, Any]) -> tuple[float | None, float | None, dict[str, Any]]:
    """(min, max, raw) from gpkg attributes, key match case-insensitive."""
    low = {k.lower(): v for k, v in (attributes or {}).items()}
    raw = {"Min_Depth": low.get("min_depth"), "Max_Depth": low.get("max_depth")}
    return parse_depth(raw["Min_Depth"]), parse_depth(raw["Max_Depth"]), raw


def propose(
    zone_stats: list[dict[str, Any]],
    window: tuple[float | None, float | None] | None,
    edge_margin_ft: float,
) -> list[dict[str, Any]]:
    """Classify each bench's local median TVD against the window.

    status: in_window | edge (inside or outside, within edge_margin_ft of a
    window boundary) | out | no_window | no_depth. Sorted shallow -> deep.
    """
    lo, hi = window if window else (None, None)
    out = []
    for z in zone_stats:
        tvd = z.get("median_tvd_ft")
        row = {
            "bench": z["formation"],
            "median_tvd_ft": tvd,
            "wells": z.get("wells"),
            "multimodal": z.get("multimodal"),
            "note": z.get("note"),
        }
        if tvd is None:
            row.update(status="no_depth", margin_ft=None)
        elif lo is None and hi is None:
            row.update(status="no_window", margin_ft=None)
        else:
            lo_ = lo if lo is not None else float("-inf")
            hi_ = hi if hi is not None else float("inf")
            margin = min(tvd - lo_, hi_ - tvd)  # negative = outside
            row["margin_ft"] = None if margin in (float("inf"), float("-inf")) else round(margin, 0)
            if abs(margin) <= edge_margin_ft:
                row["status"] = "edge"
            elif margin > 0:
                row["status"] = "in_window"
            else:
                row["status"] = "out"
        out.append(row)
    return sorted(out, key=lambda r: (r["median_tvd_ft"] is None, r["median_tvd_ft"] or 0))
