"""Row spacing for GENERATED benches (config v15, Michael 2026-10-22).

"When we're generating sticks rather than using Novi sticks, generate the
spacing from the spacing of Novi locations in the respective bench near the
parcel." The 880-ft narvi fallback is retired: a bench with no defensible
number is FLAGGED for the reviewer, never filled silently.

Chain (first that yields >= `min_gaps` gaps wins; the reviewer's `spacing_ft`
in benches.yaml / --spacing outranks all of it):

  1. Novi BASE_CASE (PUD) sticks of the SAME bench within 1 -> 2 -> 3 mi of the unit;
  2. Novi EMERGING (RES) sticks of the same bench, same radii;
  3. offset PDP of the same bench: `wells_enriched.lateral_closer_xy_ft`
     (same-zone, AS-OF-FIRST-PRODUCTION; NULL and the 2,800-ft sentinel out);
  4. nothing -> spacing_ft None, `needs_reviewer` (the bench needs a spacing_ft).

A stick's gap is the median perpendicular distance to its NEAREST parallel
neighbour of the same set (axial azimuth within `parallel_tol_deg`, alongside
for >= `overlap_min_frac` of the stick, measured over the shared length); a
neighbour closer than `same_slot_ft` is the same slot (stacked/staggered or
digitizing), not a spacing. Each stick is measured in its OWN frame, so the
pattern's orientation does not matter — only how far apart its rows sit
(the old in-unit midpoint projection mixed rows of differently oriented
sticks: RIP Harambe blob BS3_S read 749 ft where the pattern is 1,320).
"""

from __future__ import annotations

import math
import statistics
from collections.abc import Sequence
from typing import Any

from shapely.geometry.base import BaseGeometry
from shapely.strtree import STRtree

from dealintake.geo import FT_PER_M, LocalFrame, axial_diff, stick_azimuth
from dealintake.select_wells import bench_code

FT_PER_MI = 5280.0

SOURCE_LABEL = {"novi_pud": "Novi PUD", "novi_res": "Novi RES", "pdp": "offset PDP closer-XY"}


def _coords(g: BaseGeometry) -> list[tuple[float, float]]:
    return list(g.coords) if g.geom_type == "LineString" else [c for p in g.geoms for c in p.coords]


def neighbour_gaps_ft(
    sticks: Sequence[BaseGeometry], frame: LocalFrame, *, parallel_tol_deg: float, overlap_min_frac: float,
    same_slot_ft: float, search_ft: float, samples: int = 21,
) -> list[float | None]:
    """Per stick (same order): gap ft to its nearest parallel neighbour, None
    when it has none (an edge stick, a lone stick)."""
    loc = [frame.to_local(s) for s in sticks]
    az = [stick_azimuth(s) for s in sticks]
    tree = STRtree(loc)
    out: list[float | None] = []
    for i, g in enumerate(loc):
        if az[i] is None or g.length == 0:
            out.append(None)
            continue
        a = math.radians(az[i])

        def along(x: float, y: float, _ux: float = math.sin(a), _uy: float = math.cos(a)) -> float:
            return x * _ux + y * _uy
        al = [along(x, y) for x, y in _coords(g)]
        lo, hi = min(al), max(al)
        pts = [g.interpolate(k / (samples - 1), normalized=True) for k in range(samples)]
        best: float | None = None
        for j in tree.query(g.buffer(search_ft / FT_PER_M)):
            j = int(j)
            if j == i or az[j] is None or axial_diff(az[i], az[j]) > parallel_tol_deg:
                continue
            at = [along(x, y) for x, y in _coords(loc[j])]
            olo, ohi = max(lo, min(at)), min(hi, max(at))
            if ohi <= olo or (ohi - olo) / (hi - lo) < overlap_min_frac:
                continue
            ds = [p.distance(loc[j]) * FT_PER_M for p in pts if olo - 1e-6 <= along(p.x, p.y) <= ohi + 1e-6]
            if not ds:
                continue
            d = statistics.median(ds)
            if d >= same_slot_ft and (best is None or d < best):
                best = d
        out.append(best)
    return out


def _stats(vals: list[float]) -> dict[str, float]:
    q = statistics.quantiles(vals, n=4) if len(vals) >= 2 else [vals[0]] * 3
    return {"median_ft": round(statistics.median(vals)), "p25_ft": round(q[0]), "p75_ft": round(q[2])}


def _result(source: str, radius_mi: float | None, n: int, vals: list[float], ps: dict[str, Any]) -> dict[str, Any]:
    st = _stats(vals)
    spread = (st["p75_ft"] - st["p25_ft"]) / st["median_ft"] if st["median_ft"] else 0.0
    where = f" ≤{radius_mi:g} mi" if radius_mi is not None else f" ≤{float(ps['pdp_radius_mi']):g} mi"
    basis = (f"{len(vals)} bounded of {n} wells" if source == "pdp" else f"{len(vals)} gaps / {n} sticks")
    return {"spacing_ft": float(st["median_ft"]), "source": source, "radius_mi": radius_mi,
            "n": n, "n_gaps": len(vals), **st, "spread_frac": round(spread, 3),
            "mixed": spread > float(ps["spread_flag_frac"]), "needs_reviewer": False,
            "text": (f"{SOURCE_LABEL[source]}{where}: {st['median_ft']:,} ft from {basis} "
                     f"(IQR {st['p25_ft']:,}–{st['p75_ft']:,})")}


def resolve(
    unit: BaseGeometry, novi: list[dict[str, Any]], pdp_closer_xy: list[float | None], ps: dict[str, Any],
    *, sentinel_ft: float,
) -> dict[str, Any]:
    """One bench's spacing for one unit. `novi` = that bench's Novi sticks
    ({category, geom}) out to the largest radius + the neighbour search;
    `pdp_closer_xy` = that bench's offset producers' closer-XY values."""
    frame = LocalFrame.around(unit)
    ul = frame.to_local(unit)
    min_gaps = int(ps["min_gaps"])
    radii = [float(r) for r in ps["radius_steps_mi"]]
    tried: list[str] = []
    for cat, source in (("PUD", "novi_pud"), ("RES", "novi_res")):
        pool = [s for s in novi if s["category"] == cat]
        if not pool:
            tried.append(f"{SOURCE_LABEL[source]}: none within {radii[-1]:g} mi")
            continue
        gaps = neighbour_gaps_ft([s["geom"] for s in pool], frame,
                                 parallel_tol_deg=float(ps["parallel_tol_deg"]),
                                 overlap_min_frac=float(ps["overlap_min_frac"]),
                                 same_slot_ft=float(ps["same_slot_ft"]), search_ft=float(ps["neighbour_search_ft"]))
        dist = [frame.to_local(s["geom"]).distance(ul) * FT_PER_M for s in pool]
        for r in radii:
            inr = [i for i, d in enumerate(dist) if d <= r * FT_PER_MI]
            vals = [g for i in inr if (g := gaps[i]) is not None]
            if len(vals) >= min_gaps:
                return {**_result(source, r, len(inr), vals, ps), "tried": tried}
        tried.append(f"{SOURCE_LABEL[source]}: {len(vals)} gaps within {radii[-1]:g} mi (< {min_gaps})")
    vals = [float(v) for v in pdp_closer_xy if v is not None and 0 < float(v) < sentinel_ft]
    if len(vals) >= min_gaps:
        return {**_result("pdp", None, len(pdp_closer_xy), vals, ps), "tried": tried}
    tried.append(f"{SOURCE_LABEL['pdp']}: {len(vals)} bounded wells within {float(ps['pdp_radius_mi']):g} mi (< {min_gaps})")
    return {"spacing_ft": None, "source": None, "needs_reviewer": True, "mixed": False, "tried": tried,
            "text": "no spacing: " + "; ".join(tried) + " — set spacing_ft"}


def resolve_unit(
    conn: Any, unit: BaseGeometry, benches: Sequence[str], cfg_raw: dict[str, Any],
) -> dict[str, dict[str, Any]]:
    """{bench: resolve(...)} for one unit — one Novi and one PDP query."""
    from dealintake import (
        warehouse as wh,  # keeps the pure functions importable without a DB driver
    )

    ps = cfg_raw["planned_spacing"]
    reach_ft = max(float(r) for r in ps["radius_steps_mi"]) * FT_PER_MI + float(ps["neighbour_search_ft"])
    sticks = wh.novi_sticks(conn, unit, buffer_ft=reach_ft)
    pdp = wh.pdp_closer_xy(conn, unit, float(ps["pdp_radius_mi"]), str(cfg_raw["type_curve"]["first_prod_after"]))
    sentinel = float(cfg_raw["spacing"]["sentinel_ft"])
    out: dict[str, dict[str, Any]] = {}
    for b in dict.fromkeys(bench_code(x) for x in benches):
        nb = [s for s in sticks if bench_code(s["formation_blueox"] or "(unmapped)") == b]
        out[b] = resolve(unit, nb, pdp.get(b, []), ps, sentinel_ft=sentinel)
    return out


def short_text(s: dict[str, Any] | None) -> str:
    """'Novi PUD ≤1 mi, IQR 1,317–1,320' — the gunbarrel label / table cell."""
    if not s:
        return "not resolved"
    if s.get("needs_reviewer"):
        return "none nearby"
    where = (f"≤{s['radius_mi']:g} mi" if s.get("radius_mi") is not None else "")
    return (f"{SOURCE_LABEL[s['source']]} {where}".rstrip() + f", IQR {s['p25_ft']:,}–{s['p75_ft']:,}"
            + (" MIXED" if s.get("mixed") else ""))


def flag_text(bench: str, s: dict[str, Any] | None) -> str | None:
    """'Needs a look' entry for a bench's resolved spacing, or None."""
    if not s:
        return None
    if s.get("needs_reviewer"):
        return f"{bench} (spacing: none nearby — set spacing_ft)"
    if s.get("mixed"):
        return f"{bench} (spacing: mixed pattern, IQR {s['p25_ft']:,}–{s['p75_ft']:,})"
    return None
