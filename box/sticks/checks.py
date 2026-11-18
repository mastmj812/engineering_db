"""The generator invariants of docs/box_sticks/phase3a-2026-11-14/BARS.md (I1-I8), recomputed from a Result and the
inputs it was generated from. Each check returns a list of violation strings; an empty list is a pass. I9 (the same
inputs give the same file) is a test, not a check. The back-test slot match (T1) lives here too.
"""
from __future__ import annotations

import math
from itertools import pairwise

import numpy as np
from shapely.geometry import LineString

from dealintake import geo

from .core import (
    BENCH_REASONS,
    ROW_REASONS,
    WCA_MEMBERS,
    Cfg,
    Dsu,
    Result,
    family,
    well_legs,
)

FT_PER_M = geo.FT_PER_M
REQUIRED = ("pad_id", "bench", "generator_version", "lateral_azimuth_deg", "azimuth_basis", "tvd_basis", "spacing_basis", "well_type", "legs",
            "target_tvd_ft", "completed_lateral_ft")


def _legs(res: Result):
    for s in res.sticks:
        for leg in s["legs"]:
            yield s, leg, LineString([leg["heel_xy"], leg["toe_xy"]])


def i1_envelope(res: Result, d: Dsu, cfg: Cfg, link_fn) -> list[str]:
    legs = list(_legs(res))
    if not legs or not d.wells:
        return []
    wl = [(g, k) for k, w in enumerate(d.wells) for g in well_legs(w.line)]
    t = link_fn(np.array([g for _, _, g in legs], dtype=object), np.array([g for g, _ in wl], dtype=object), same=False)
    t = t[t["overlap"] >= cfg.min_overlap]
    bad = []
    codev = d.wca_class == "co-developed"
    assumed = {b["code"]: b["target_tvd_ft"] for b in res.benches if not b["no_row_reason"]}      # benches that kept a landing
    for i, j, dh in zip(t["i"].to_numpy(), t["j"].to_numpy(), t["dh_ft"].to_numpy()):
        s, w = legs[int(i)][0], d.wells[wl[int(j)][1]]
        z = w.depth_ft if w.depth_ft is not None else assumed.get(w.code or "")
        if z is None:
            hit = family(w.code) == family(s["bench"]) and dh <= cfg.same_dh_ft
        else:
            dz = z - s["target_tvd_ft"]
            cross = codev and {w.code, s["bench"]} == set(WCA_MEMBERS)
            hit = (abs(dz) <= cfg.same_dv_ft and dh <= cfg.same_dh_ft and not cross) or any(lo < dz <= hi and dh <= lim for lo, hi, lim in cfg.stacked)
        if hit:
            bad.append(f"I1 {s['well_name']} inside the envelope of {w.well_id} (dh {dh:.0f} ft)")
    return bad


def i2_stagger(res: Result, cfg: Cfg) -> list[str]:
    bad = []
    rows = [(s["bench"], leg["gunbarrel_x_ft"], s["target_tvd_ft"], s["well_name"]) for s, leg, _ in _legs(res)]
    by = {b["code"]: b for b in res.benches}
    for b in by.values():                    # (a): a staggered bench sits half a spacing off the grid of the bench it was set against
        ref = by.get(b.get("stagger_ref") or "")
        if not b.get("legs_placed") or ref is None or abs(ref["spacing_final_ft"] - b["spacing_final_ft"]) > 0.5:
            continue
        s = b["spacing_final_ft"]
        xa = [r["gunbarrel_x_ft"] for r in res.ledger if r["code"] == ref["code"] and r["gunbarrel_x_ft"] is not None]
        for r in rows:
            if r[0] == b["code"] and xa:
                off = min(abs((r[1] - x) % s - s / 2.0) for x in xa)
                if off > 1.0:
                    bad.append(f"I2a {r[3]} is {off:.1f} ft off the half-spacing stagger against {ref['code']}")
    return bad


def i3_order(res: Result, d: Dsu, cfg: Cfg) -> list[str]:
    rank = {b.code: b.rank for b in d.benches}
    z = sorted({(rank[s["bench"]], s["bench"], s["target_tvd_ft"]) for s in res.sticks})
    return [f"I3 {a[1]} at {a[2]:.0f} ft and {b[1]} at {b[2]:.0f} ft" for a, b in pairwise(z) if b[2] - a[2] < cfg.min_sep_ft - 0.2]


def i4_well_type(res: Result, cfg: Cfg) -> list[str]:
    bad = []
    for s in res.sticks:
        if s["well_type"] == "single":
            if res.meta["well_type"] != "single" or s["completed_lateral_ft"] < cfg.min_lateral_ft - 0.5:
                bad.append(f"I4 {s['well_name']} single at {s['completed_lateral_ft']:.0f} ft")
        else:
            sep = abs(s["legs"][0]["gunbarrel_x_ft"] - s["legs"][1]["gunbarrel_x_ft"])
            if res.meta["well_type"] != "uturn" or sep < cfg.uturn_leg_ft - 1.0 or s["completed_lateral_ft"] < cfg.min_lateral_ft - 0.5:
                bad.append(f"I4 {s['well_name']} U-turn legs {sep:.0f} ft apart, {s['completed_lateral_ft']:.0f} ft completed")
    return bad


def i5_inside(res: Result, d: Dsu, cfg: Cfg) -> list[str]:
    win = d.polygon.buffer(-(cfg.setback_ft - 1.0) / FT_PER_M, join_style=2)
    return [f"I5 {s['well_name']} leaves the setback window" for s, _, g in _legs(res) if not win.covers(g)]


def i6_provenance(res: Result) -> list[str]:
    bad = []
    for s in res.sticks:
        miss = [k for k in REQUIRED if s.get(k) in (None, "", [])]
        miss += [k for k in ("rung",) if not s["tvd_basis"].get(k)] + [k for k in ("map_ft", "final_ft", "grid") if not s["spacing_basis"].get(k)]
        if miss or any(leg.get("gunbarrel_x_ft") is None for leg in s["legs"]):
            bad.append(f"I6 {s['well_name']} missing {miss}")
    return bad


def i7_ledger(res: Result, d: Dsu) -> list[str]:
    bad = []
    seen = {b["code"] for b in res.benches}
    bad += [f"I7 bench {b.code} is not accounted for" for b in d.benches if b.code not in seen]
    for b in res.benches:
        rows = [r for r in res.ledger if r["code"] == b["code"]]
        placed = [r for r in rows if r["status"] == "placed"]
        culled = [r for r in rows if r["status"] == "culled"]
        if len(rows) != b["rows_considered"] or len(placed) != b["legs_placed"] or len(placed) + len(culled) != len(rows):
            bad.append(f"I7 {b['code']} rows {len(rows)} placed {len(placed)} culled {len(culled)} against the bench log")
        bad += [f"I7 {b['code']} row {r['row']} culled with reason '{r['reason']}'" for r in culled if r["reason"] not in ROW_REASONS]
        if not rows and b["no_row_reason"] not in BENCH_REASONS:
            bad.append(f"I7 {b['code']} has no row and no reason")
        legs = sum(len(s["legs"]) for s in res.sticks if s["bench"] == b["code"])
        if legs != len(placed):
            bad.append(f"I7 {b['code']} {legs} legs in sticks, {len(placed)} placed rows")
    return bad


def i8_gunbarrel(res: Result, d: Dsu) -> list[str]:
    """Every stored leg offset reproduced from its geometry with the engineering_db copy of sign rule v2
    (dealintake.geo.positive_offset_bearing), origin = the DSU centroid, azimuth at 0.1 deg."""
    az = res.meta["azimuth_grid_deg"]
    b = math.radians(geo.positive_offset_bearing(az))
    cx, cy, o = math.sin(b), math.cos(b), d.polygon.centroid
    bad = []
    for s, leg, g in _legs(res):
        m = g.interpolate(0.5, normalized=True)
        x = ((m.x - o.x) * cx + (m.y - o.y) * cy) * FT_PER_M
        if abs(x - leg["gunbarrel_x_ft"]) > 1.0 or s["lateral_azimuth_deg"] != az:
            bad.append(f"I8 {s['well_name']} stored {leg['gunbarrel_x_ft']} ft, geometry {x:.1f} ft")
    return bad


def run_all(res: Result, d: Dsu, cfg: Cfg, link_fn) -> dict[str, list[str]]:
    return {"I1": i1_envelope(res, d, cfg, link_fn), "I2": i2_stagger(res, cfg), "I3": i3_order(res, d, cfg), "I4": i4_well_type(res, cfg),
            "I5": i5_inside(res, d, cfg), "I6": i6_provenance(res), "I7": i7_ledger(res, d), "I8": i8_gunbarrel(res, d)}


# ----------------------------------------------------------------------------
# Back-test slot match (BARS.md T1): hidden wells against placed legs, one-to-one
# ----------------------------------------------------------------------------


def match_slots(pairs: list[dict]) -> dict[str, str]:
    """pairs: candidate (well, leg) rows with shared_frac (of the shorter), dh_ft, dz_ft (None = no depth evidence or
    the depth test is skipped), spacing_ft. Returns well -> leg, each used once, nearest sideways first."""
    ok = [p for p in pairs if p["shared_frac"] >= 0.5 and p["dh_ft"] <= min(330.0, p["spacing_ft"] / 2.0)
          and (p["dz_ft"] is None or abs(p["dz_ft"]) <= 150.0)]
    out: dict[str, str] = {}
    used: set[str] = set()
    for p in sorted(ok, key=lambda p: (p["dh_ft"], p["well"], p["leg"])):
        if p["well"] not in out and p["leg"] not in used:
            out[p["well"]] = p["leg"]
            used.add(p["leg"])
    return out
