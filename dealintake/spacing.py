"""Row spacing for GENERATED benches (config v18, 2026-11-25; v15 Michael 2026-10-22).

A generated bench takes its row spacing from the locations of the same bench
near the parcel. Since the BOX sticks replaced Novi sticks as the locations
(Novi Intelligence is comparison only), "the locations" are BOX sticks, and a
BOX stick CARRIES its planned leg-to-leg spacing (`spacing_ft`, set by the
stick generator from producing-well spacing around it): the chain reads that
number instead of measuring gaps between drawn lines. A bench with no
defensible number is FLAGGED for the reviewer, never filled silently.

Chain (first that yields >= `min_gaps` values wins; the reviewer's `spacing_ft`
in benches.yaml / --spacing outranks all of it):

  1. BOX sticks of the SAME bench within 1 -> 2 -> 3 mi of the unit: the median
     of their planned spacing. The text names the distance band the sticks'
     spacing came from when most of it is the generator's widest band;
  2. offset PDP of the same bench: `wells_enriched.lateral_closer_xy_ft`
     (same-zone, AS-OF-FIRST-PRODUCTION; NULL and the 2,800-ft sentinel out);
  3. nothing -> spacing_ft None, `needs_reviewer` (the bench needs a spacing_ft).

`neighbour_gaps_ft` (a stick's gap = the median perpendicular distance to its
nearest parallel neighbour, measured in its own frame) is kept for the BOX stick
generator, which measures producing-well spacing with it.
"""

from __future__ import annotations

import math
import statistics
from collections import Counter
from collections.abc import Sequence
from typing import Any

from shapely.geometry.base import BaseGeometry
from shapely.strtree import STRtree

from dealintake.geo import FT_PER_M, LocalFrame, axial_diff, stick_azimuth
from dealintake.select_wells import bench_code

FT_PER_MI = 5280.0
FAR_BAND = "10+ mi"          # the stick generator's widest spacing band: thin local control

SOURCE_LABEL = {"box": "BOX sticks", "pdp": "offset PDP closer-XY"}


# The neighbour-gap measurement below is no longer part of the deal-intake chain (a BOX
# stick carries its spacing). It stays because the BOX stick generator measures PRODUCER
# spacing by this method and checks itself against this function
# (scripts/box_sticks_phase2a.py), with the four gap knobs of planned_spacing: in the
# thresholds file. Changing it changes how BOX sticks are spaced.
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


def _result(source: str, radius_mi: float | None, n: int, vals: list[float], ps: dict[str, Any],
            note: str = "") -> dict[str, Any]:
    st = _stats(vals)
    spread = (st["p75_ft"] - st["p25_ft"]) / st["median_ft"] if st["median_ft"] else 0.0
    where = f" ≤{radius_mi:g} mi" if radius_mi is not None else f" ≤{float(ps['pdp_radius_mi']):g} mi"
    basis = (f"{len(vals)} bounded of {n} wells" if source == "pdp" else f"{len(vals)} sticks")
    return {"spacing_ft": float(st["median_ft"]), "source": source, "radius_mi": radius_mi,
            "n": n, "n_gaps": len(vals), **st, "spread_frac": round(spread, 3),
            "mixed": spread > float(ps["spread_flag_frac"]), "needs_reviewer": False,
            "text": (f"{SOURCE_LABEL[source]}{where}: {st['median_ft']:,} ft from {basis} "
                     f"(IQR {st['p25_ft']:,}–{st['p75_ft']:,}){note}")}


def resolve(
    unit: BaseGeometry, box: list[dict[str, Any]], pdp_closer_xy: list[float | None], ps: dict[str, Any],
    *, sentinel_ft: float,
) -> dict[str, Any]:
    """One bench's spacing for one unit. `box` = that bench's BOX sticks
    ({geom, spacing_ft, spacing_band}) out to the largest radius;
    `pdp_closer_xy` = that bench's offset producers' closer-XY values."""
    frame = LocalFrame.around(unit)
    ul = frame.to_local(unit)
    min_gaps = int(ps["min_gaps"])
    radii = [float(r) for r in ps["radius_steps_mi"]]
    tried: list[str] = []
    pool = [s for s in box if s.get("spacing_ft")]
    if not pool:
        tried.append(f"{SOURCE_LABEL['box']}: none within {radii[-1]:g} mi")
    else:
        dist = [frame.to_local(s["geom"]).distance(ul) * FT_PER_M for s in pool]
        inr: list[int] = []
        for r in radii:
            inr = [i for i, d in enumerate(dist) if d <= r * FT_PER_MI]
            if len(inr) >= min_gaps:
                bands = Counter(pool[i].get("spacing_band") for i in inr)
                far = bands.get(FAR_BAND, 0)
                note = (f"; {far} of {len(inr)} set from wells {FAR_BAND} away" if far * 2 > len(inr) else "")
                return {**_result("box", r, len(inr), [float(pool[i]["spacing_ft"]) for i in inr], ps, note),
                        "far_band": far * 2 > len(inr), "tried": tried}
        tried.append(f"{SOURCE_LABEL['box']}: {len(inr)} within {radii[-1]:g} mi (< {min_gaps})")
    vals = [float(v) for v in pdp_closer_xy if v is not None and 0 < float(v) < sentinel_ft]
    if len(vals) >= min_gaps:
        return {**_result("pdp", None, len(pdp_closer_xy), vals, ps), "tried": tried}
    tried.append(f"{SOURCE_LABEL['pdp']}: {len(vals)} bounded wells within {float(ps['pdp_radius_mi']):g} mi (< {min_gaps})")
    return {"spacing_ft": None, "source": None, "needs_reviewer": True, "mixed": False, "tried": tried,
            "text": "no spacing: " + "; ".join(tried) + " — set spacing_ft"}


def resolve_unit(
    conn: Any, unit: BaseGeometry, benches: Sequence[str], cfg_raw: dict[str, Any],
) -> dict[str, dict[str, Any]]:
    """{bench: resolve(...)} for one unit — one BOX stick and one PDP query."""
    from dealintake import (
        warehouse as wh,  # keeps the pure functions importable without a DB driver
    )

    ps = cfg_raw["planned_spacing"]
    reach_ft = max(float(r) for r in ps["radius_steps_mi"]) * FT_PER_MI
    sticks = wh.box_sticks(conn, unit, buffer_ft=reach_ft)
    pdp = wh.pdp_closer_xy(conn, unit, float(ps["pdp_radius_mi"]), str(cfg_raw["type_curve"]["first_prod_after"]))
    sentinel = float(cfg_raw["spacing"]["sentinel_ft"])
    out: dict[str, dict[str, Any]] = {}
    for b in dict.fromkeys(bench_code(x) for x in benches):
        nb = [s for s in sticks if bench_code(s["formation_blueox"] or "(unmapped)") == b]
        out[b] = resolve(unit, nb, pdp.get(b, []), ps, sentinel_ft=sentinel)
    return out


def short_text(s: dict[str, Any] | None) -> str:
    """'BOX sticks ≤1 mi, IQR 1,200–1,270' — the gunbarrel label / table cell."""
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
