"""BOX sticks storage rows (phase 4; sql/73). Pure and DB-free: the generator's output and inputs as table rows, and
the way back (stored rows -> the Dsu the generator was given), so a stored set re-runs from the warehouse alone.

The writer is scripts.box_sticks_run; nothing here connects to anything.
"""
from __future__ import annotations

import math
from collections import Counter

from . import identity as idn
from .core import SECOND_LEVEL, Bench, Dsu, Result, Well

TWO_LANDINGS = "two_landings_observed"
STICK_FLAGS = ("pinned", TWO_LANDINGS, SECOND_LEVEL, "dsu_drilled_across", "grid_bounded", "outside_grid")
RUNGS = ("direct", "thickness", "bracket", "offset", "grid")
SAME_FT = 0.1                                  # a regenerated leg end within this of the stored one is the same leg


def _f(v: object) -> float | None:
    return None if v is None or (isinstance(v, float) and math.isnan(v)) else float(v)  # type: ignore[arg-type]


def _line_wkt(pts: list) -> str:
    return "LINESTRING (" + ", ".join(f"{x:.7f} {y:.7f}" for x, y in pts) + ")"


def identity_stick(s: dict, key: str | None = None, slot: int | None = None) -> idn.Stick:
    return idn.Stick(key or s["well_name"], int(s["pad_id"]), s["bench"], tuple((tuple(leg["heel_xy"]), tuple(leg["toe_xy"])) for leg in s["legs"]), slot)


def stick_row(s: dict, slot: int, method: str, share: float | None = None, offset_ft: float | None = None) -> dict:
    """One box.location_stick row (ids added by the writer) from a generator stick record."""
    tb, sp, turn = s["tvd_basis"], s["spacing_basis"], s.get("turn")
    unknown = set(s["flags"]) - set(STICK_FLAGS)
    if unknown or tb["rung"] not in RUNGS:
        raise ValueError(f"{s['well_name']}: unknown flag {sorted(unknown)} or rung {tb['rung']!r}")
    return {
        "basin": s["basin"], "pad_id": int(s["pad_id"]), "formation_blueox": s["bench"], "slot_no": int(slot),
        "well_name": f"{s['pad_id']}-{s['bench']}-{slot:02d}", "well_type": s["well_type"], "n_legs": int(s["n_legs"]),
        "legs_wkt": "MULTILINESTRING (" + ", ".join(_line_wkt([leg["heel_lonlat"], leg["toe_lonlat"]])[len("LINESTRING "):] for leg in s["legs"]) + ")",
        "turn_wkt": _line_wkt(turn["arc_lonlat"]) if turn else None,
        "completed_lateral_ft": float(s["completed_lateral_ft"]), "drilled_lateral_ft": float(s["drilled_lateral_ft"]),
        "turn_radius_ft": _f(turn["radius_ft"]) if turn else None, "turn_dls_deg_per_100ft": _f(turn["dls_deg_per_100ft"]) if turn else None,
        "turn_arc_ft": _f(turn["arc_ft"]) if turn else None,
        "azimuth_deg": float(s["azimuth_true_deg"]) % 180.0, "azimuth_grid_deg": float(s["lateral_azimuth_deg"]) % 180.0, "azimuth_basis": s["azimuth_basis"],
        "gunbarrel_x_ft": [float(leg["gunbarrel_x_ft"]) for leg in s["legs"]], "setback_ft": float(s["setback_ft"]),
        "target_tvd_ft": float(s["target_tvd_ft"]), "tvd_rung": tb["rung"], "tvd_anchor": list(tb.get("anchors") or []),
        "tvd_err_median_ft": _f(tb.get("held_out_median_ft")), "tvd_err_p90_ft": _f(tb.get("held_out_p90_ft")),
        "tvd_reconciled_shift_ft": float(tb.get("reconciled_shift_ft") or 0.0), "second_level_tvd_ft": _f(tb.get("second_level_tvd_ft")),
        "spacing_ft": float(sp["final_ft"]), "spacing_map_ft": float(sp["map_ft"]), "spacing_grid": sp["grid"], "spacing_n_eff": _f(sp.get("n_eff")),
        "spacing_weighted_median_ft": _f(sp.get("weighted_median_ft")), "spacing_band": sp.get("band"), "spacing_band_ft": _f(sp.get("band_ft")),
        "flags": sorted(s["flags"]), "match_method": method, "match_share": share, "match_offset_ft": offset_ft, "detail": s,
    }


def dsu_row(d: Dsu, res: Result) -> dict:
    m = res.meta
    return {"pad_id": int(d.pad_id), "azimuth_deg": float(d.az_true_deg), "azimuth_grid_deg": float(m["azimuth_grid_deg"]), "azimuth_basis": d.az_basis,
            "wca_class": d.wca_class, "wca_dominant": d.wca_dominant, "well_type": m.get("well_type"), "straight_ft": _f(m.get("straight_ft")),
            "clear_width_ft": _f(m.get("clear_width_ft")), "long_wells": m.get("long_wells"), "drilled_across": m.get("drilled_across"),
            "turn_at_high": m.get("turn_at_high"), "wells_read": len(d.wells), "well_api10": [w.well_id for w in d.wells],
            "well_member": [bool(w.member) for w in d.wells], "sticks": len(res.sticks), "legs": sum(int(s["n_legs"]) for s in res.sticks)}


def bench_rows(d: Dsu, res: Result) -> list[dict]:
    log = {b["code"]: b for b in res.benches}
    culled: dict[str, Counter] = {}
    for r in res.ledger:
        if r["status"] == "culled":
            culled.setdefault(r["code"], Counter())[r["reason"]] += 1
    out = []
    for b in d.benches:
        g = log.get(b.code, {})
        err = (b.tvd_err_median_ft, b.tvd_err_p90_ft) if b.tvd_err_median_ft is not None else (b.report_err or (None, None))
        out.append({
            "pad_id": int(d.pad_id), "formation_blueox": b.code, "bench_rank": int(b.rank), "inside_frac": float(b.inside_frac), "tvd_in_ft": _f(b.tvd_ft),
            "tvd_rung": b.rung, "tvd_anchor": list(b.anchors), "tvd_err_median_ft": _f(err[0]), "tvd_err_p90_ft": _f(err[1]),
            "second_level_tvd_ft": _f(b.second_tvd_ft), "two_landings": list(b.levels) if b.levels else None,
            "spacing_map_ft": float(b.spacing_ft), "spacing_basis": dict(b.spacing_basis) | {"control": float(b.control)},
            "no_row_reason": g.get("no_row_reason", ""), "target_tvd_ft": _f(g.get("target_tvd_ft")), "reconciled_shift_ft": _f(g.get("reconciled_shift_ft")),
            "spacing_final_ft": _f(g.get("spacing_final_ft")), "grid": g.get("grid"), "pinned": g.get("pinned"),
            "rows_considered": int(g.get("rows_considered", 0)), "legs_placed": int(g.get("legs_placed", 0)),
            "rows_culled": dict(culled.get(b.code, {})), "sticks": int(g.get("sticks", 0) or 0)})
    return out


def well_rows(d: Dsu) -> list[dict]:
    """Per well read for this DSU; `line` stays in the work CRS (the writer converts and de-duplicates by api10)."""
    return [{"api10": w.well_id, "formation_blueox": w.code, "depth_ft": _f(w.depth_ft), "status": w.status, "planned": bool(w.planned), "line": w.line}
            for w in d.wells]


def rebuild_dsu(basin: str, polygon, drow: dict, brows: list[dict], wells: dict[str, dict]) -> Dsu:
    """The Dsu the generator was given, from stored rows. `polygon` and each well's `line` are in the work CRS."""
    benches = []
    for b in sorted(brows, key=lambda r: r["bench_rank"]):
        direct = b["tvd_rung"] == "direct"
        err = (_f(b["tvd_err_median_ft"]), _f(b["tvd_err_p90_ft"]))
        basis = dict(b["spacing_basis"])
        control = float(basis.pop("control"))
        lv = tuple(float(v) for v in b["two_landings"]) if b.get("two_landings") else None
        sec = _f(b.get("second_level_tvd_ft"))
        flags = ((TWO_LANDINGS,) if lv else ()) + ((SECOND_LEVEL,) if sec is not None else ())
        benches.append(Bench(code=b["formation_blueox"], rank=int(b["bench_rank"]), tvd_ft=_f(b["tvd_in_ft"]), rung=b["tvd_rung"],
                             spacing_ft=float(b["spacing_map_ft"]), inside_frac=float(b["inside_frac"]), control=control,
                             tvd_err_median_ft=None if direct else err[0], tvd_err_p90_ft=None if direct else err[1], spacing_basis=basis,
                             flags=flags, levels=lv, second_tvd_ft=sec, anchors=tuple(b["tvd_anchor"]),  # type: ignore[arg-type]
                             report_err=(err[0], err[1]) if direct and err[0] is not None else None))  # type: ignore[arg-type]
    ws = []
    for api, mem in zip(drow["well_api10"], drow["well_member"], strict=True):
        w = wells[api]
        ws.append(Well(api, w["formation_blueox"], _f(w["depth_ft"]), w["line"], bool(mem), w["status"], bool(w["planned"])))
    return Dsu(pad_id=int(drow["pad_id"]), basin=basin, polygon=polygon, az_grid_deg=float(drow["azimuth_grid_deg"]), az_true_deg=float(drow["azimuth_deg"]),
               az_basis=drow["azimuth_basis"], benches=benches, wells=ws, wca_class=drow["wca_class"], wca_dominant=drow["wca_dominant"])


def diff_sticks(a: list[dict], b: list[dict], tol_ft: float = SAME_FT) -> list[str]:
    """Differences between two generator outputs of one DSU (names, legs within tol_ft, TVD, rung, flags); empty = the same sticks."""
    out = []
    A, B = {s["well_name"]: s for s in a}, {s["well_name"]: s for s in b}
    for k in sorted(set(A) ^ set(B)):
        out.append(f"{k}: only in {'first' if k in A else 'second'}")
    for k in sorted(set(A) & set(B)):
        x, y = A[k], B[k]
        if len(x["legs"]) != len(y["legs"]):
            out.append(f"{k}: legs {len(x['legs'])} != {len(y['legs'])}")
            continue
        far = max(math.dist(p, q) for lx, ly in zip(x["legs"], y["legs"], strict=True) for p, q in ((lx["heel_xy"], ly["heel_xy"]), (lx["toe_xy"], ly["toe_xy"])))
        if far * idn.FT_PER_M > tol_ft:
            out.append(f"{k}: legs differ by {far * idn.FT_PER_M:.2f} ft")
        for f in ("target_tvd_ft", "well_type", "flags"):
            if x[f] != y[f]:
                out.append(f"{k}: {f} {x[f]!r} != {y[f]!r}")
        if x["tvd_basis"] != y["tvd_basis"]:
            out.append(f"{k}: tvd_basis differs")
    return out
