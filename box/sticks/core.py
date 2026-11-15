"""BOX sticks generator, pure core (phase 3a pilot). DB-free: one DSU's inputs in, sticks + a ledger out.

Rules of record: docs/box_sticks_plan.md (decision table) and docs/box_sticks/phase3a-2026-11-14/BARS.md.
Geometry is in narvi's work CRS (UTM 13N, metres); azimuths handed to this module are GRID bearings at 0.1 deg
(dealintake.geo.narvi_azimuth). Rows, legs, U-turn arcs and gunbarrel offsets come from narvi's engine, pinned by
commit in requirements-dealintake.txt; the rules about WHICH rows exist live here.

Per DSU: benches (sliver floor, WCA rule, stack reconciliation) -> well type -> spacing (U-turn floor, sharing
between close benches) -> row grids (pinned by same-bench wells, staggered, fitted to the clear width) -> culls
(setback, length, no-place envelope against existing wells) -> U-turn pairing. Rows of different benches are not
tested against each other (Michael, 2026-11-15): sticks are what is possible per bench, BOX precedence sorts the rest.
The generator does not forecast and holds no economics.
"""
from __future__ import annotations

import math
from dataclasses import asdict, dataclass, field
from itertools import pairwise

import numpy as np
from narvi import generate as ng
from narvi import placement as npl
from narvi.records import FT_PER_M, ScenarioParams
from shapely.affinity import rotate
from shapely.geometry import LineString
from shapely.geometry.base import BaseGeometry

VERSION = "box_sticks_0.3_pilot"
ROW_REASONS = ("setback_clip", "setback_fit", "short_lateral", "envelope_same_landing", "envelope_stacked", "no_depth_neighbour",
               "uturn_unpaired")
BENCH_REASONS = ("sliver", "no_depth", "wca_one_member", "wca_one_landing", "reconciled_out", "no_window", "no_rows")
WCA_MEMBERS = ("WCA_1", "WCA_2")


@dataclass(frozen=True)
class Cfg:
    setback_ft: float = 330.0
    min_lateral_ft: float = 7000.0        # no straight stick under this; a U-turn's two legs together reach it
    uturn_leg_ft: float = 1200.0          # rule 5
    tight_cap_ft: float = 440.0           # phase 2a: no spacing under this
    sliver_frac: float = 0.10             # rule 7
    min_sep_ft: float = 75.0              # stack reconciliation
    interzone_ft: float = 300.0           # benches closer than this in TVD with the same spacing sit half a spacing apart (I2)
    fit_tol: float = 0.10                 # setback fit: spacing may tighten by this share
    same_dv_ft: float = 150.0             # candidate D
    same_dh_ft: float = 400.0
    min_overlap: float = 0.30
    profile_step_m: float = 5.0
    ramp_reach_m: float = 15.0            # a row is on a setback ramp when a row this far inward is longer by > ramp_gain
    ramp_gain_ft: float = 25.0
    stacked: tuple = ()                   # ((dz lo, dz hi, sideways limit ft), ...), dz = well depth - stick TVD; from phase 2b


@dataclass
class Bench:
    code: str
    rank: int                             # stratigraphic order, shallow = low
    tvd_ft: float | None
    rung: str                             # direct / thickness / bracket / offset / none
    spacing_ft: float                     # the blended spacing map value
    inside_frac: float
    control: float = 0.0                  # effective number of gap measurements behind the spacing
    tvd_err_median_ft: float | None = None
    tvd_err_p90_ft: float | None = None
    spacing_basis: dict = field(default_factory=dict)
    flags: tuple = ()


@dataclass
class Well:
    well_id: str
    code: str | None
    depth_ft: float | None                # None = no depth evidence
    line: BaseGeometry                    # work CRS
    member: bool = True                   # >= 30 % of its line inside the DSU
    status: str = "producer"
    planned: bool = False                 # on a planned survey: never depth evidence, drawn in plan view only


@dataclass
class Dsu:
    pad_id: int
    basin: str
    polygon: BaseGeometry                 # work CRS
    az_grid_deg: float
    az_true_deg: float
    az_basis: str
    benches: list[Bench]
    wells: list[Well]
    wca_class: str | None = None          # co-developed / one member / no control
    wca_dominant: str | None = None


@dataclass
class Result:
    pad_id: int
    meta: dict
    sticks: list[dict]
    ledger: list[dict]
    benches: list[dict]


def family(code: str | None) -> str:
    c = code or ""
    if c.startswith("WCA") or c == "WCXY":
        return "WCA"
    return c.split("_")[0]


# ----------------------------------------------------------------------------
# Azimuth (rule 8)
# ----------------------------------------------------------------------------


def axial_mean(a: list[float]) -> tuple[float, float]:
    r = np.radians(2 * np.asarray(a, float))
    c, s = np.cos(r).mean(), np.sin(r).mean()
    return float(np.degrees(np.arctan2(s, c)) / 2 % 180), float(np.hypot(c, s))


def axial_dist(a: float, b: float) -> float:
    d = abs(a - b) % 180.0
    return min(d, 180.0 - d)


def resolve_azimuth(in_dsu: list[float], long_side: float, aspect: float, cell: tuple[float, int] | None, county: float | None,
                    square_aspect: float = 1.15, min_r: float = 0.85, cell_min: int = 10, snap_deg: float = 5.0,
                    tie_deg: float = 20.0) -> tuple[float, str]:
    """True bearing and its basis. Wells inside the DSU, then (near-square only) the 6-mi cell, then the county, snapped
    to a polygon side; elongated DSUs with no wells take the long axis. Wells within snap_deg of a side take the side."""
    sides = (long_side % 180.0, (long_side + 90.0) % 180.0)
    if in_dsu:
        m, r = axial_mean(in_dsu)
        if len(in_dsu) == 1 or r >= min_r:
            near = min(sides, key=lambda s: axial_dist(s, m))
            return (near, "wells_in_dsu+side") if axial_dist(near, m) <= snap_deg else (m, "wells_in_dsu")
    if aspect >= square_aspect:
        return sides[0], "long_axis"
    ref, basis = (cell[0], "cell") if cell is not None and cell[1] >= cell_min else (county, "county")
    if ref is None or abs(axial_dist(sides[0], ref) - axial_dist(sides[1], ref)) < tie_deg:
        return sides[0], "long_axis+square_unresolved"
    return min(sides, key=lambda s: axial_dist(s, ref)), basis


# ----------------------------------------------------------------------------
# Rotated frame: the same construction as narvi.placement.laterals_rotated (laterals -> +x, cross-section = y)
# ----------------------------------------------------------------------------


class Frame:
    def __init__(self, window: BaseGeometry, az: float, step_m: float):
        self.window, self.az = window, az
        self.centroid = window.centroid
        self.phi = 90.0 - az
        self.rot = rotate(window, -self.phi, origin=self.centroid, use_radians=False)
        self.minx, self.miny, self.maxx, self.maxy = self.rot.bounds
        self.y_mid = (self.miny + self.maxy) / 2.0
        self.ys = np.arange(self.miny, self.maxy + step_m / 2, step_m)
        self.L = np.array([self.length_at(y) for y in self.ys])
        self.step = step_m
        # the width the unit would offer rows if its sides ran parallel to the azimuth (area over the longest row)
        self.width0 = min(self.maxy - self.miny, window.area / max(float(self.L.max()), 1.0))

    def length_at(self, y: float) -> float:
        seg = npl._longest_segment(LineString([(self.minx - 10.0, y), (self.maxx + 10.0, y)]).intersection(self.rot))
        return seg.length if seg is not None else 0.0

    def y_of(self, x: float, y: float) -> float:
        t = math.radians(-self.phi)
        return self.centroid.y + (x - self.centroid.x) * math.sin(t) + (y - self.centroid.y) * math.cos(t)

    def band(self, min_len_m: float, cfg: Cfg) -> tuple[float, float] | None:
        """The cross-section interval clear of both side setbacks along the whole lateral: from each side, the first
        row that is long enough and no longer gaining length as it moves inward (a row on a ramp is being cut by a
        side line that is not parallel to the azimuth)."""
        d = max(1, round(cfg.ramp_reach_m / self.step))
        gain = cfg.ramp_gain_ft / FT_PER_M
        n = len(self.ys)

        def edge(order: range, into: int) -> int | None:
            for i in order:
                j = i + into * d
                if self.L[i] >= min_len_m and not (0 <= j < n and self.L[j] - self.L[i] > gain):
                    return i
            return None

        lo, hi = edge(range(n), 1), edge(range(n - 1, -1, -1), -1)
        if lo is None or hi is None or hi <= lo:
            return None
        return float(self.ys[lo]), float(self.ys[hi])


def fit_rows(fr: Frame, s_m: float, min_s_m: float, min_len_m: float, cfg: Cfg) -> tuple[float, float, int, str, tuple | None]:
    """Spacing and first-row position for an unpinned bench: (spacing m, base y, rows dropped, note, band)."""
    n0 = math.floor(fr.width0 / s_m + 1e-9) + 1
    band = fr.band(min_len_m, cfg)
    if band is None or (band[1] - band[0] < s_m and n0 > 2):
        return s_m, fr.y_mid - (n0 - 1) / 2.0 * s_m, 0, "no_clear_band", None
    ya, yb = band
    w = yb - ya
    n = math.floor(w / s_m + 1e-9) + 1
    if n >= n0:
        return s_m, (ya + yb) / 2.0 - (n - 1) / 2.0 * s_m, 0, "map_spacing", band
    for m in range(n0, 1, -1):
        sm = w / (m - 1)
        if sm >= max((1.0 - cfg.fit_tol) * s_m, min_s_m) - 1e-9:
            return sm, ya, n0 - m, "tightened" if m == n0 else "row_dropped", band
    return s_m, (ya + yb) / 2.0, n0 - 1, "row_dropped", band


def pinned_base(ys: list[float], s_m: float) -> float:
    """Grid phase that best lines the rows up with existing same-bench wells (circular mean of their positions)."""
    a = 2 * np.pi * (np.asarray(ys, float) % s_m) / s_m
    return float((np.arctan2(np.sin(a).mean(), np.cos(a).mean()) % (2 * np.pi)) / (2 * np.pi) * s_m)


# ----------------------------------------------------------------------------
# Benches: sliver floor, WCA rule, stack reconciliation
# ----------------------------------------------------------------------------


@dataclass
class _B:
    b: Bench
    tvd: float
    s_ft: float = 0.0
    s_pre: float = 0.0                    # spacing before any setback fit (ft)
    s_m: float = 0.0
    base: float = 0.0
    pinned: bool = False
    stagger_ref: str | None = None        # the bench this one's rows were set half a spacing off
    fit: str = ""
    fit_dropped: int = 0
    shift_ft: float = 0.0
    rows: list = field(default_factory=list)

    @property
    def trust(self) -> tuple:
        return (1 if self.b.rung == "direct" else 0, -(self.b.tvd_err_median_ft or 0.0), self.b.control, -self.b.rank)


def select_benches(d: Dsu, cfg: Cfg) -> tuple[list[_B], list[tuple[Bench, str]]]:
    out: list[tuple[Bench, str]] = []
    live: list[_B] = []
    for b in sorted(d.benches, key=lambda b: b.rank):
        if b.inside_frac < cfg.sliver_frac:
            out.append((b, "sliver"))
        elif b.tvd_ft is None or b.rung == "none":
            out.append((b, "no_depth"))
        else:
            live.append(_B(b, float(b.tvd_ft)))

    def drop(w: _B, why: str) -> None:
        live.remove(w)
        out.append((w.b, why))

    wca = [w for w in live if w.b.code in WCA_MEMBERS]
    if len(wca) == 2:
        if d.wca_class != "co-developed":                                    # rule 4: one WCA row set
            keep = d.wca_dominant if d.wca_dominant in WCA_MEMBERS else max(wca, key=lambda w: w.trust).b.code
            drop(next(w for w in wca if w.b.code != keep), "wca_one_member")
        elif wca[1].tvd - wca[0].tvd < cfg.min_sep_ft:                       # plan: one WCA landing under the floor
            drop(min(wca, key=lambda w: w.trust), "wca_one_landing")
    for _ in range(4 * len(live) + 4):                                       # stack reconciliation
        live.sort(key=lambda w: w.b.rank)
        bad = next(((a, c) for a, c in pairwise(live) if c.tvd - a.tvd < cfg.min_sep_ft - 1e-6), None)
        if bad is None:
            break
        a, c = bad
        loser, winner = (a, c) if a.trust < c.trust else (c, a)
        target = winner.tvd - cfg.min_sep_ft if loser is a else winner.tvd + cfg.min_sep_ft
        if abs(target - float(loser.b.tvd_ft)) <= (loser.b.tvd_err_p90_ft or 0.0):
            loser.shift_ft, loser.tvd = target - float(loser.b.tvd_ft), target
        else:
            drop(loser, "reconciled_out")
    else:
        for a, c in zip(list(live), list(live)[1:]):
            if c in live and a in live and c.tvd - a.tvd < cfg.min_sep_ft - 1e-6:
                drop(min((a, c), key=lambda w: w.trust), "reconciled_out")
    return live, out


# ----------------------------------------------------------------------------
# The DSU
# ----------------------------------------------------------------------------


def _leg_line(fr: Frame, y: float, x0: float, x1: float) -> LineString:
    return LineString([npl.unrotate(x0, y, fr.centroid, fr.phi), npl.unrotate(x1, y, fr.centroid, fr.phi)])


def envelope_hits(lines: list[LineString], tvd: float, code: str, d: Dsu, cfg: Cfg, link_fn) -> dict[int, tuple[str, str]]:
    """Row index -> (reason, detail) for rows inside the no-place envelope of an existing well (candidate D, the
    phase 2b pair metric), or within 400 ft sideways of a same-family well with no depth evidence (rule 2)."""
    if not lines or not d.wells:
        return {}
    t = link_fn(np.array(lines, dtype=object), np.array([w.line for w in d.wells], dtype=object), same=False)
    t = t[t["overlap"] >= cfg.min_overlap]
    hits: dict[int, tuple[str, str]] = {}
    codev = d.wca_class == "co-developed"
    for i, j, dh in zip(t["i"].to_numpy(), t["j"].to_numpy(), t["dh_ft"].to_numpy()):
        w = d.wells[int(j)]
        why = None
        if w.depth_ft is None:
            if family(w.code) == family(code) and dh <= cfg.same_dh_ft:
                why = "no_depth_neighbour"
        else:
            dz = w.depth_ft - tvd
            cross = codev and {w.code, code} == set(WCA_MEMBERS)             # rule 4: no test between the two members
            if abs(dz) <= cfg.same_dv_ft and dh <= cfg.same_dh_ft and not cross:
                why = "envelope_same_landing"
            elif any(lo < dz <= hi and dh <= lim for lo, hi, lim in cfg.stacked):
                why = "envelope_stacked"
        if why and int(i) not in hits:
            hits[int(i)] = (why, f"{w.well_id} dh {dh:.0f} ft" + ("" if w.depth_ft is None else f" dz {w.depth_ft - tvd:+.0f} ft"))
    return hits


def generate_dsu(d: Dsu, cfg: Cfg, link_fn) -> Result:
    az = round(d.az_grid_deg, 1) % 180.0
    gb = (az, (d.polygon.centroid.x, d.polygon.centroid.y))
    window = npl.drillable_window(d.polygon, cfg.setback_ft)
    live, out = select_benches(d, cfg)
    meta = {"pad_id": d.pad_id, "basin": d.basin, "generator_version": VERSION, "azimuth_grid_deg": az, "azimuth_true_deg": round(d.az_true_deg, 1),
            "azimuth_basis": d.az_basis, "wca_class": d.wca_class}
    blog = [{"pad_id": d.pad_id, "code": b.code, "no_row_reason": why, "rows_considered": 0, "legs_placed": 0, "rows_culled": 0} for b, why in out]
    if window.is_empty or not live:
        blog += [{"pad_id": d.pad_id, "code": w.b.code, "no_row_reason": "no_window", "rows_considered": 0, "legs_placed": 0, "rows_culled": 0} for w in live]
        return Result(d.pad_id, meta | {"well_type": None}, [], [], blog)
    fr = Frame(window, az, cfg.profile_step_m)
    straight_ft = float(fr.L.max()) * FT_PER_M
    uturn = straight_ft < cfg.min_lateral_ft
    min_len_m = (cfg.min_lateral_ft if not uturn else cfg.min_lateral_ft / 2.0) / FT_PER_M
    min_s_ft = cfg.uturn_leg_ft if uturn else cfg.tight_cap_ft
    band0 = fr.band(min_len_m, cfg)
    meta |= {"well_type": "uturn" if uturn else "single", "straight_ft": round(straight_ft, 0),
             "clear_width_ft": None if band0 is None else round((band0[1] - band0[0]) * FT_PER_M, 0),
             "window_width_ft": round(fr.width0 * FT_PER_M, 0)}

    # spacing: each bench its own map spacing (U-turn floor only); no sharing between benches (Michael, 2026-11-15)
    for w in live:
        w.s_ft = max(w.b.spacing_ft, min_s_ft)
        mids = [wl.line.interpolate(0.5, normalized=True) for wl in d.wells if wl.member and wl.code == w.b.code]
        w.rows = [fr.y_of(p.x, p.y) for p in mids]                           # pin positions, replaced by rows below
        w.pinned = bool(w.rows)
    live.sort(key=lambda w: w.tvd)
    groups: list[list[_B]] = []
    for w in live:
        p = groups[-1][-1] if groups else None
        if p is not None and w.tvd - p.tvd < cfg.interzone_ft and abs(w.s_ft - p.s_ft) < 0.5:
            groups[-1].append(w)
        else:
            groups.append([w])
    for g in groups:
        prev: _B | None = None
        for w in g:                                                          # row grids, shallow to deep
            w.s_pre, w.s_m = w.s_ft, w.s_ft / FT_PER_M
            if w.pinned:
                w.base, w.fit = pinned_base(w.rows, w.s_m), "pinned"
            elif prev is not None and abs(prev.s_pre - w.s_pre) < 0.5:
                w.s_m, w.s_ft = prev.s_m, prev.s_m * FT_PER_M                # the bench above's setback fit carries down
                w.base, w.fit, w.stagger_ref = prev.base + w.s_m / 2.0, "staggered", prev.b.code
            else:
                w.s_m, w.base, w.fit_dropped, w.fit, _ = fit_rows(fr, w.s_m, min_s_ft / FT_PER_M, min_len_m, cfg)
                w.s_ft = w.s_m * FT_PER_M
            prev = w

    sticks: list[dict] = []
    ledger: list[dict] = []
    turn_high: bool | None = None
    for w in sorted(live, key=lambda w: (not w.pinned, -w.b.control, w.b.rank)):   # trust order
        code, tvd = w.b.code, round(w.tvd, 1)
        p = ScenarioParams(formation=code, target_tvd_ft=tvd, spacing_ft=round(w.s_ft, 1), setback_ft=cfg.setback_ft, azimuth_deg=az,
                           well_type="uturn" if uturn else "single", min_lateral_ft=cfg.min_lateral_ft, uturn_min_leg_to_leg_ft=cfg.uturn_leg_ft,
                           scenario_id=f"box-{d.pad_id}", deal_id="box_sticks")
        legs = npl.laterals_rotated(window, az, w.s_ft, 1.0, (w.base - fr.y_mid) * FT_PER_M, "center")[0]
        rows = [{"y": y, "x0": x0, "x1": x1, "len_ft": (x1 - x0) * FT_PER_M, "reason": None, "detail": "", "stick": None} for y, x0, x1 in legs]
        for r in rows:
            if band0 is not None and not (band0[0] - 0.5 <= r["y"] <= band0[1] + 0.5):
                r["reason"], r["detail"] = "setback_clip", f"row {r['len_ft']:.0f} ft, outside the clear width"
            elif not uturn and r["len_ft"] < cfg.min_lateral_ft:
                r["reason"], r["detail"] = "short_lateral", f"{r['len_ft']:.0f} ft"
        open_ = [r for r in rows if r["reason"] is None]
        for k, hit in envelope_hits([_leg_line(fr, r["y"], r["x0"], r["x1"]) for r in open_], tvd, code, d, cfg, link_fn).items():
            open_[k]["reason"], open_[k]["detail"] = hit

        wells = []                                                           # (InventoryWell, rows it uses)
        open_ = [r for r in rows if r["reason"] is None]
        if not uturn:
            wells = [(ng._single_well(ng._make_leg(r["y"], r["x0"], r["x1"], fr.centroid, fr.phi, gb), p, 0), [r]) for r in open_]
        else:
            runs: list[list[dict]] = []
            for r in open_:
                if runs and abs(r["y"] - runs[-1][-1]["y"] - w.s_m) < 1.0:
                    runs[-1].append(r)
                else:
                    runs.append([r])

            def pair(high: bool, runs: list = runs, w: _B = w, p: ScenarioParams = p) -> list:
                got = []
                for run in runs:
                    k = 0
                    for iw in ng._place_uturns([(r["y"], r["x0"], r["x1"]) for r in run], w.s_m, fr.centroid, fr.phi, gb, p, high):
                        n = len(iw.legs)
                        got.append((iw, run[k:k + n]))
                        k += n
                return got

            def kept(ws: list) -> float:
                return sum(iw.completed_lateral_ft for iw, _ in ws if iw.well_type == "uturn" and iw.completed_lateral_ft >= cfg.min_lateral_ft)

            if turn_high is None:
                a, b = pair(True), pair(False)
                if kept(a) > 0 or kept(b) > 0:
                    turn_high = kept(a) >= kept(b)
                cand = a if kept(a) >= kept(b) else b
            else:
                cand = pair(turn_high)
            for iw, rs in cand:
                if iw.well_type != "uturn":
                    rs[0]["reason"], rs[0]["detail"] = "uturn_unpaired", "no adjacent open row to pair with"
                elif iw.completed_lateral_ft < cfg.min_lateral_ft:
                    for r in rs:
                        r["reason"], r["detail"] = "short_lateral", f"U-turn {iw.completed_lateral_ft:.0f} ft completed"
                else:
                    wells.append((iw, rs))
        # the envelope again on the final leg geometry (a U-turn leg is trimmed for its turn, which changes the shared length)
        final = [(iw, rs, leg) for iw, rs in wells for leg in iw.legs]
        bad = envelope_hits([LineString([leg.heel_xy, leg.toe_xy]) for _, _, leg in final], tvd, code, d, cfg, link_fn)
        for k, hit in bad.items():
            for r in final[k][1]:
                if r["reason"] is None:
                    r["reason"], r["detail"] = hit
        wells = [(iw, rs) for iw, rs in wells if all(r["reason"] is None for r in rs)]

        for n, (iw, rs) in enumerate(sorted(wells, key=lambda t: t[1][0]["y"]), 1):
            iw.well_name = f"{d.pad_id}-{code}-{n:02d}"
            iw.lateral_azimuth_deg = az
            for r in rs:
                r["stick"] = iw.well_name
            rec = asdict(iw)
            for k in ("category", "novi_wellname", "edited", "context", "recon_status", "pdp_count_3mi", "inflation_ratio", "handoff_category",
                      "stick_id", "pdp_gap_ft", "pdp_gap_horiz_ft", "pdp_gap_dtvd_ft", "pdp_gap_well", "novi_rep", "scenario_id", "deal_id"):
                rec.pop(k)
            rec |= {"pad_id": d.pad_id, "basin": d.basin, "bench": code, "generator_version": VERSION, "n_legs": len(iw.legs),
                    "azimuth_true_deg": round(d.az_true_deg, 1), "azimuth_basis": d.az_basis,
                    "tvd_basis": {"rung": w.b.rung, "held_out_median_ft": w.b.tvd_err_median_ft, "held_out_p90_ft": w.b.tvd_err_p90_ft,
                                  "reconciled_shift_ft": round(w.shift_ft, 1)},
                    "spacing_basis": dict(w.b.spacing_basis) | {"map_ft": round(w.b.spacing_ft, 1), "final_ft": round(w.s_ft, 1),
                                                                "grid": w.fit},
                    "flags": sorted(set(w.b.flags) | ({"pinned"} if w.pinned else set()))}
            sticks.append(rec)
        for k, r in enumerate(rows):
            mid = npl.unrotate((r["x0"] + r["x1"]) / 2.0, r["y"], fr.centroid, fr.phi)
            ledger.append({"pad_id": d.pad_id, "code": code, "row": k, "gunbarrel_x_ft": round(npl.gunbarrel_offset_ft(mid, az, gb[1]), 1),
                           "row_length_ft": round(r["len_ft"], 0), "status": "placed" if r["reason"] is None else "culled",
                           "reason": r["reason"] or "", "detail": r["detail"], "stick": r["stick"] or "", "target_tvd_ft": tvd,
                           "heel_xy": [round(v, 1) for v in npl.unrotate(r["x0"], r["y"], fr.centroid, fr.phi)],
                           "toe_xy": [round(v, 1) for v in npl.unrotate(r["x1"], r["y"], fr.centroid, fr.phi)]})
        for k in range(w.fit_dropped):
            ledger.append({"pad_id": d.pad_id, "code": code, "row": len(rows) + k, "gunbarrel_x_ft": None, "row_length_ft": None, "status": "culled",
                           "reason": "setback_fit", "detail": "row count reduced to fit the clear width", "stick": "", "target_tvd_ft": tvd,
                           "heel_xy": None, "toe_xy": None})
        n_placed = sum(r["reason"] is None for r in rows)
        blog.append({"pad_id": d.pad_id, "code": code, "no_row_reason": "" if rows or w.fit_dropped else "no_rows", "rows_considered": len(rows) + w.fit_dropped,
                     "legs_placed": n_placed, "rows_culled": len(rows) + w.fit_dropped - n_placed, "sticks": sum(1 for s in sticks if s["bench"] == code),
                     "target_tvd_ft": tvd, "rung": w.b.rung, "reconciled_shift_ft": round(w.shift_ft, 1), "spacing_map_ft": round(w.b.spacing_ft, 1),
                     "spacing_final_ft": round(w.s_ft, 1), "grid": w.fit, "stagger_ref": w.stagger_ref or "", "pinned": w.pinned,
                     "flags": ";".join(sorted(w.b.flags))})
    order = {b.code: b.rank for b in d.benches}
    sticks.sort(key=lambda s: (order[s["bench"]], s["well_name"]))
    ledger.sort(key=lambda r: (order[r["code"]], r["row"]))
    blog.sort(key=lambda r: order[r["code"]])
    return Result(d.pad_id, meta | {"turn_at_high": turn_high}, sticks, ledger, blog)
