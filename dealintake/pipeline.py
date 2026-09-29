"""deal-intake v2 orchestration — two stages with a reviewer gate between them.

  propose   Gate 0-2 inputs: upload units to narvi, snapshot vintages, planned
            lateral per unit, bench PROPOSAL vs the depth window, Gate 2
            stick relation per (unit x bench). Writes proposal.json/.md and
            STOPS — the reviewer confirms benches, the correlated window and
            per-bench spacing (these are geology/land calls, never automatic).
  evaluate  Gates 2-7 on the confirmed inputs: location source, support,
            co-development-aware TC selection, anduin forecast + QC, TC split
            test, TC-vs-Novi comparison, dossier. Everything lands in the run
            directory (signals.json + CSVs + PNGs + dossier.md).

Writes nothing to the warehouse. narvi is called in PREVIEW mode only
(/api/generate persists nothing). anduin fits only wells with no forecast yet
(see clients.anduin.forecast) and TCs are computed as a PREVIEW — saving the
TC and the narvi scenario stay reviewer actions. The one exception is the
short-history cohort transfer — ON BY DEFAULT (config
type_curve.short_history_transfer_months; --no-short-history-transfer turns it
off) — which overwrites the short wells' unlocked anduin forecasts with
cohort-transfer rows (listed in the dossier).
"""

from __future__ import annotations

import json
import statistics
from collections import Counter
from collections.abc import Callable
from dataclasses import asdict, is_dataclass
from datetime import date, datetime
from decimal import Decimal
from itertools import pairwise
from pathlib import Path
from typing import Any

from shapely import wkt as shp_wkt
from shapely.geometry import mapping, shape
from shapely.ops import unary_union

from dealintake import benches as benchmod
from dealintake import cohort_qc, split_test, strat, unit_benches
from dealintake import warehouse as wh
from dealintake.clients.anduin import Anduin, AnduinError
from dealintake.clients.narvi import Narvi, legs
from dealintake.config import Config
from dealintake.decline import effective_from_nominal
from dealintake.geo import (
    LocalFrame,
    apply_row_rules,
    axial_diff,
    grid_convergence_deg,
    gunbarrel_frame,
    long_axis_azimuth,
    mean_axial_azimuth,
    planned_lateral,
    stick_azimuth,
    stick_length_ft,
    stick_relation,
    stick_spacing_ft,
    true_to_grid,
)
from dealintake.render.tables import p_value
from dealintake.select_wells import (
    adjacent_benches,
    bench_code,
    classify,
    codev_tier,
    fill,
    tier_medians,
    tier_order,
    vertical_parents,
)

# The vertical-parent offset gate is sql/50's literal; scripts.find_analogs holds the
# test-pinned copy — import it, never restate it (cross-repo contract).
from scripts.find_analogs import OFFSET_GATE_FT as PARENT_GATE_FT

DEFAULT_SPACING_FT = 880.0  # narvi's fallback when no in-unit de-facto gap exists
RADIUS_STEPS_MI = (5.0, 7.5, 10.0)


def _json_default(o: Any) -> Any:
    if isinstance(o, (date, datetime)):
        return o.isoformat()
    if isinstance(o, Decimal):                 # numeric columns (dev_scenario dtvd) arrive as Decimal
        return float(o)
    if is_dataclass(o):
        return asdict(o)
    if hasattr(o, "geom_type"):
        return mapping(o)
    raise TypeError(type(o))


def write_json(path: Path, obj: Any) -> None:
    path.write_text(json.dumps(obj, indent=2, default=_json_default), encoding="utf-8")


# =============================================================================
# Stage 1 — propose
# =============================================================================

def gunbarrel_preview(
    unit: Any, azimuth_deg: float, bench_proposal: list[dict[str, Any]], bench_seed: dict[str, dict[str, Any]],
    gate2: dict[str, dict[str, Any]], novi_sticks: list[dict[str, Any]], pdp_near: list[dict[str, Any]],
    narvi: Narvi, *, setback_ft: float, cross_margin_ft: float = 1320.0, along_margin_ft: float = 2640.0,
    bench_opts: dict[str, dict[str, Any]] | None = None, min_leg_ft: float | None = None,
) -> dict[str, Any]:
    """Cross-section data for the review page: existing producers and Novi
    BASE_CASE sticks near the unit, plus one narvi preview row-set per seeded
    bench (spacing = the bench's Novi de-facto spacing, else 880 ft; TVD = the
    unit's local median). Offsets in the rule-16 frame (ft), TVD in ft."""
    project, (c_lo, c_hi), (a_lo, a_hi) = gunbarrel_frame(unit, azimuth_deg)
    tvd_by = {bench_code(r["bench"]): r["median_tvd_ft"] for r in bench_proposal if r.get("median_tvd_ft") is not None}
    frame = LocalFrame.around(unit)
    unit_local = frame.to_local(unit)

    def near(g: Any) -> tuple[float, float] | None:
        off, along = project(g)
        return (off, along) if (c_lo - cross_margin_ft <= off <= c_hi + cross_margin_ft
                                and a_lo - along_margin_ft <= along <= a_hi + along_margin_ft) else None

    # Existing producers: only wells whose LATERAL overlaps the unit along the
    # laterals (a well entirely north/south of the unit is not in this cross-
    # section, however close its offset — the 2-11 "Mitchell wells" case,
    # 2026-09-28). `inside` = the house >=30% co-extent rule (rule 9); the rest
    # are drawn faded as side/partial neighbours.
    existing = []
    for w in pdp_near:
        g = shp_wkt.loads(w["wkt"])
        if w.get("tvd_ft") is None:
            continue
        off, _ = project(g)
        lo_a, hi_a = project.along_span(g)
        if not (c_lo - cross_margin_ft <= off <= c_hi + cross_margin_ft) or hi_a <= a_lo or lo_a >= a_hi:
            continue
        gl = frame.to_local(g)
        frac = gl.intersection(unit_local).length / gl.length if gl.length else 0.0
        existing.append({"api10": w["api10"], "bench": w["bench"], "offset_ft": round(off), "tvd_ft": float(w["tvd_ft"]),
                         "inside": frac >= 0.30, "in_unit_frac": round(frac, 2)})
    novi = []                                  # kept in the data (not drawn) for the record
    for st in novi_sticks:
        if st["category"] != "PUD":
            continue
        oa = near(st["geom"])
        if oa and st.get("tvd") is not None:
            novi.append({"stick_id": st["stick_id"], "bench": st["formation_blueox"] or "(unmapped)",
                         "offset_ft": round(oa[0]), "tvd_ft": float(st["tvd"]), "relation": st["relation"]})
    planned: dict[str, dict[str, Any]] = {}
    opts_all = bench_opts or {}
    for b, row in bench_seed.items():
        if not row["evaluate"]:
            continue
        opts = opts_all.get(b) or {}
        tvd = opts.get("tvd_ft", tvd_by.get(b))
        if tvd is None:
            continue
        g2 = gate2.get(b) or {}
        # The reviewer sets the pattern; Novi's de-facto spacing is a SUGGESTION
        # (36-37-38: Novi drew BS3_C at ~650 ft), 880 ft is the fallback.
        sp = float(opts.get("spacing_ft") or DEFAULT_SPACING_FT)
        sp_src = "reviewer" if opts.get("spacing_ft") else "880-ft fallback"
        try:
            gen = narvi.generate(unit, [{"formation": b, "target_tvd_ft": tvd, "spacing_ft": sp}],
                                 setback_ft=setback_ft, spacing_ft=sp,
                                 azimuth_deg=true_to_grid(azimuth_deg, unit.centroid.x, unit.centroid.y))
            rows = [{"offset_ft": round(project(leg["geom"])[0]),
                     "lateral_ft": round(float(leg.get("completed_lateral_ft") or 0))} for leg in legs(gen)]
        except Exception as e:  # noqa: BLE001 — a preview failure must not kill propose
            planned[b] = {"error": str(e)[:160]}
            continue
        kept, notes = apply_row_rules(
            rows, azimuth_deg, n_wells=opts.get("n_wells"), keep_side=opts.get("keep_side"),
            drop_rows={sd: opts[f"drop_{sd}_rows"] for sd in ("west", "east", "north", "south") if opts.get(f"drop_{sd}_rows")},
            min_leg_ft=min_leg_ft)
        planned[b] = {"tvd_ft": tvd, "tvd_source": "reviewer" if "tvd_ft" in opts else "local median",
                      "spacing_ft": sp, "spacing_source": sp_src,
                      "novi_spacing_ft": g2.get("novi_spacing_ft"),
                      "offsets_ft": [r["offset_ft"] for r in kept], "lateral_ft": [r["lateral_ft"] for r in kept],
                      "n_generated": len(rows), "rules": notes, "role": opts.get("role", "base")}
    return {"azimuth_deg": azimuth_deg, "cross_extent_ft": [round(c_lo), round(c_hi)],
            "bench_tvd_ft": tvd_by, "existing": existing, "novi": novi, "planned": planned}


def tract_check(
    tracts: list[dict[str, Any]], lo: strat.Bound, hi: strat.Bound, col: strat.Column, basin: str | None,
) -> list[dict[str, Any]]:
    """Each attached tract's declared window beside the DSU's. `disagrees` =
    the tract's bounds are not the same kind+value as the DSU's on either side
    (a tract that is broader — Surface -> COE under a formation-bounded DSU —
    is reported too: the reviewer decides which paper governs)."""
    out = []
    for t in tracts:
        a = {k.lower(): v for k, v in (t.get("attributes") or {}).items()}
        _, _, raw = benchmod.declared_window(a)
        tlo = strat.parse_bound(raw["Min_Depth"], col, basin)
        thi = strat.parse_bound(raw["Max_Depth"], col, basin)
        same = ((tlo.kind, tlo.depth_ft, tlo.group, tlo.edge) == (lo.kind, lo.depth_ft, lo.group, lo.edge)
                and (thi.kind, thi.depth_ft, thi.group, thi.edge) == (hi.kind, hi.depth_ft, hi.group, hi.edge))
        label = " ".join(str(a.get(k)) for k in ("section", "block", "aliquot") if a.get(k)) or t.get("label") or "?"
        out.append({"tract": label, "net_ac": a.get("net_ac"), "wi": a.get("tract_wi"),
                    "raw": raw, "rights": f"{tlo.describe()} -> {thi.describe()}", "disagrees": not same})
    return out


def resolve_twin_tracts(units: list[dict[str, Any]]) -> None:
    """For DSUs sharing a footprint (depth-severed pairs), a tract whose
    declared window equals a twin DSU's declared window is re-labelled as
    that twin's tract (disagrees=False, twin=<dsu>)."""
    geoms = {u["label"]: shape(u["geometry"]) for u in units}
    for u in units:
        twins = [v for v in units if v is not u and geoms[u["label"]].equals(geoms[v["label"]])]
        for tw in u.get("tract_windows") or []:
            if not tw["disagrees"]:
                continue
            for v in twins:
                vr = v.get("declared_window_raw") or {}
                if (_norm_depth(tw["raw"].get("Min_Depth")), _norm_depth(tw["raw"].get("Max_Depth"))) == (
                        _norm_depth(vr.get("Min_Depth")), _norm_depth(vr.get("Max_Depth"))):
                    tw["disagrees"] = False
                    tw["twin"] = v.get("dsu_name") or v["label"]
                    break


def _norm_depth(v: Any) -> str:
    return "" if v is None else str(v).strip().lower().replace(",", "").replace("'", "").replace(" formation", "")


def gate2_decision(
    g: dict[str, Any],
    *,
    planned_azimuth_deg: float,
    planned_lateral_ft: float,
    azimuth_tol_deg: float,
    lateral_tol: float,
) -> dict[str, Any]:
    """Gate 2 (Michael, 2026-09-25): keep Novi BASE_CASE locations ONLY when
    every stick is inside the unit AND the sticks are oriented like our plan
    AND their lateral fits our planned lateral. Novi's guess at a unit's
    infill is often the wrong orientation or length (VaULt 44-45 S2: 5k E-W
    in the west, 5k/10k N-S in the east); the PRESENCE of BASE_CASE sticks is
    the signal that the bench gets infilled, so those benches are generated —
    and the generated sticks inherit the BASE_CASE bench's spacing."""
    n_in, n_x = g.get("pud_inside", 0), g.get("pud_crossing", 0)
    az_n, ll_n = g.get("novi_azimuth_deg"), g.get("novi_ll_ft")
    if n_in == 0 and n_x == 0:
        return {"source": "generate", "reason": "no BASE_CASE stick inside", "azimuth_diff_deg": None}
    if n_x:
        why = [f"{n_x} BASE_CASE stick(s) cross the unit line"]
    else:
        why = []
    dz = None if az_n is None else round(axial_diff(az_n, planned_azimuth_deg), 1)
    if dz is not None and dz > azimuth_tol_deg:
        why.append(f"BASE_CASE azimuth {az_n:.0f}° vs planned {planned_azimuth_deg:.0f}° ({dz:.0f}° off)")
    if ll_n is not None and planned_lateral_ft > 0 and abs(ll_n - planned_lateral_ft) > lateral_tol * planned_lateral_ft:
        why.append(f"BASE_CASE lateral {ll_n:,.0f} ft vs planned {planned_lateral_ft:,.0f} ft (±{lateral_tol:.0%})")
    if why:
        return {"source": "generate", "reason": "; ".join(why) + " — generate at the BASE_CASE spacing",
                "azimuth_diff_deg": dz}
    return {"source": "novi", "reason": "all BASE_CASE sticks inside, oriented and sized like the plan",
            "azimuth_diff_deg": dz}


def propose(
    deal_path: Path,
    run_dir: Path,
    cfg: Config,
    *,
    correlated_window: tuple[float | None, float | None] | None = None,
    window_basis: str | None = None,
    narvi: Narvi | None = None,
) -> dict[str, Any]:
    narvi = narvi or Narvi()
    run_dir.mkdir(parents=True, exist_ok=True)
    parcels = narvi.upload_parcels(deal_path)
    if not parcels:
        raise ValueError(f"narvi returned no parcels for {deal_path}")

    col = strat.load()
    reviewed = unit_benches.reviewed_benches(run_dir)          # {} on a first propose
    out: dict[str, Any] = {
        "deal_file": str(deal_path),
        "config_version": cfg.version,
        "strat_version": col.version,
        "config_path": str(cfg.path),
        "correlated_window": correlated_window,
        "window_basis": window_basis,
        "units": [],
    }
    tol = float(cfg["alignment"]["stick_inside_tolerance_ft"])
    review_geoms: dict[str, Any] = {}
    with wh.connect() as conn:
        out["snapshot"] = wh.snapshot(conn)
        for pc in parcels:
            u = pc["geom"]
            if u.geom_type == "MultiPolygon":
                # Gate 1: multipolygon units are split and reported, never merged silently.
                # (A gpkg layer typed MULTIPOLYGON wraps single-part units too — not a warning.)
                parts = sorted(u.geoms, key=lambda g: -g.area)
                if len(parts) > 1:
                    out.setdefault("warnings", []).append(
                        f"{pc['label']}: MultiPolygon with {len(parts)} parts — using the largest "
                        f"({parts[0].area / u.area:.0%} of the area); split the unit in the land file"
                    )
                u = parts[0]
            # Azimuth of record = the unit's LONG AXIS (Michael, 2026-09-26: sticks run
            # parallel to the long axis; a degree or two off is not how a unit is
            # planned). narvi's neighborhood grid is advisory and reported beside it;
            # a disagreement beyond the tolerance is a reviewer flag, never an
            # automatic override. Bearing conventions (verified in narvi's code,
            # 2026-09-26): /api/warehouse/azimuth is PostGIS ST_Azimuth on geography
            # = TRUE bearing; /api/generate lays rows in UTM 13N = GRID bearing
            # (~0.9 deg apart across the Delaware) — see true_to_grid at the
            # generate call.
            c0 = u.centroid
            az_deg, az_src = long_axis_azimuth(u), "unit long axis"
            az = narvi.azimuth(u)
            grid_true = None
            if az.get("azimuth_deg") is not None:
                grid_true = float(az["azimuth_deg"])                    # already a true bearing
                d = axial_diff(grid_true, az_deg)
                az_src = (f"unit long axis (neighborhood grid {grid_true:.1f}° true, "
                          f"{'R ' + str(az.get('coherence')) + ', ' if az.get('confident') else 'not coherent, '}{d:.1f}° off)")
                if az.get("confident") and d > float(cfg["alignment"]["grid_vs_long_axis_flag_deg"]):
                    out.setdefault("warnings", []).append(
                        f"{pc['label']}: coherent neighborhood grid {grid_true:.1f}° (true) is {d:.1f}° off the unit long axis "
                        f"{az_deg:.1f}° — planned at the long axis; reviewer confirms the development direction")
            pl = planned_lateral(
                u, az_deg,
                setback_ft=float(cfg["planned_lateral"]["setback_ft"]),
                chord_step_ft=float(cfg["planned_lateral"]["chord_step_ft"]),
                azimuth_source=az_src,
            )
            local = wh.local_benches(conn, u)
            basin = strat.infer_basin([b["bench"] for b in local])
            # Rights bounds: Surface / COE / a depth / a FORMATION PHRASE (resolved by
            # stratigraphic order, never into a depth). The numeric window only
            # ever comes from depth bounds.
            _, _, draw = benchmod.declared_window(pc["attributes"])
            if correlated_window:
                lo, hi = (strat.Bound("depth", None, v) if v is not None else strat.Bound("missing")
                          for v in correlated_window)
            else:
                lo = strat.parse_bound(draw["Min_Depth"], col, basin)
                hi = strat.parse_bound(draw["Max_Depth"], col, basin)
            for side, bd in (("Min_Depth", lo), ("Max_Depth", hi)):
                if bd.kind == "unknown":
                    out.setdefault("warnings", []).append(
                        f"{pc['label']}: {side} {bd.text!r} not understood (basin {basin}) — treated as open; reviewer resolves")
            dmin = lo.depth_ft if lo.kind == "depth" else 0.0 if lo.kind == "surface" else None
            dmax = hi.depth_ft if hi.kind == "depth" else None
            window = (dmin, dmax) if (dmin is not None or dmax is not None) else None
            zones = narvi.zones(u, [b["bench"] for b in local]) if local else {"stats": []}
            proposal = benchmod.propose(zones.get("stats", []), window, float(cfg["depth"]["edge_margin_ft"]))
            low_attrs = {k.lower(): v for k, v in (pc["attributes"] or {}).items()}
            dsu_name = low_attrs.get("dsu_num")
            # Rights come from the DSU row ONLY (Michael, 2026-09-26). The tracts
            # attached to it carry their own declared windows; they are compared
            # and FLAGGED when they disagree, never used to widen or narrow.
            tract_windows = tract_check(pc.get("tracts") or [], lo, hi, col, basin)
            bench_seed = unit_benches.seed_unit(dsu_name, lo, hi, proposal, col, basin)

            sticks = wh.novi_sticks(conn, u)
            rel: dict[str, Counter] = {}
            for s in sticks:
                s["relation"] = stick_relation(s["geom"], u, tol)
                rel.setdefault(s["formation_blueox"] or "(unmapped)", Counter())[(s["category"], s["relation"])] += 1
            # Review-page layers (display only): Novi sticks near the unit + offset PDP laterals.
            pdp_near = wh.pdp_laterals_near(conn, u)
            review_geoms[pc["label"]] = {
                "novi": [{"stick_id": s["stick_id"], "bench": s["formation_blueox"] or "(unmapped)",
                          "category": s["category"], "relation": s["relation"], "wkt": s["geom"].wkt} for s in sticks],
                "pdp": pdp_near,
            }
            gate2 = {}
            for b, c in sorted(rel.items()):
                puds = [s for s in sticks if (s["formation_blueox"] or "(unmapped)") == b
                        and s["category"] == "PUD" and s["relation"] in ("inside", "crossing")]
                az_n = mean_axial_azimuth([stick_azimuth(s["geom"]) for s in puds])
                ll_n = statistics.median([float(s["ll_ft"] or stick_length_ft(s["geom"])) for s in puds]) if puds else None
                gate2[b] = {
                    "pud_inside": c[("PUD", "inside")], "pud_crossing": c[("PUD", "crossing")],
                    "res_inside": c[("RES", "inside")], "res_crossing": c[("RES", "crossing")],
                    "novi_azimuth_deg": None if az_n is None else round(az_n, 1),
                    "novi_ll_ft": None if ll_n is None else round(ll_n, 0),
                    # de-facto spacing of the BASE_CASE bench: what our generated sticks inherit
                    "novi_spacing_ft": stick_spacing_ft([s["geom"] for s in puds], az_n) if az_n is not None else None,
                }
                gate2[b].update(gate2_decision(
                    gate2[b], planned_azimuth_deg=pl.azimuth_deg, planned_lateral_ft=pl.median_ft,
                    azimuth_tol_deg=float(cfg["alignment"]["azimuth_tolerance_deg"]),
                    lateral_tol=cfg.lateral_tolerance(basin),
                ))
            # Gunbarrel preview (Michael, 2026-09-28): how many infill sticks per
            # landing zone the seed implies, and where they sit against the
            # existing wells — so topfill/underfill calls are made on the review
            # page, never automatically. Sticks are narvi PREVIEWS at the seed's
            # benches; evaluate regenerates them with the class-level spacing.
            rv = reviewed.get(pc["label"]) if reviewed else None
            gun = gunbarrel_preview(
                u, pl.azimuth_deg, proposal,
                {b: {"evaluate": True} for b in rv["benches"]} if rv is not None else bench_seed,
                gate2, sticks, pdp_near, narvi, setback_ft=float(cfg["planned_lateral"]["setback_ft"]),
                bench_opts=rv["bench_opts"] if rv is not None else None,
                min_leg_ft=rv["min_leg_ft"] if rv is not None else None,
            )
            gun["benches_source"] = unit_benches.FILENAME if rv is not None else "seed"
            out["units"].append({
                "label": pc["label"],
                "gunbarrel": gun,
                "area_ac": pc["area_ac"],
                "geometry": mapping(u),
                "attributes": pc["attributes"],
                "basin": basin,
                "dsu_name": dsu_name,
                "declared_window_raw": draw,
                "declared_window": [dmin, dmax],
                "window_used": list(window) if window else None,
                "window_source": "correlated" if correlated_window else ("declared (NOT local — correlate)" if window else None),
                "bounds": {"min": asdict(lo), "max": asdict(hi)},
                "rights": f"{lo.describe()} -> {hi.describe()}"
                          + (" [correlated]" if correlated_window else
                             " [declared depths are NOT local]" if "depth" in (lo.kind, hi.kind) else ""),
                "bench_seed": bench_seed,
                "tract_windows": tract_windows,
                "offset_pdp_3mi": {b["bench"]: int(b["n_wells"]) for b in local},
                "planned_lateral": {**pl.as_dict(), "grid_azimuth_true_deg": None if grid_true is None else round(grid_true, 1),
                                    "grid_convergence_deg": round(grid_convergence_deg(c0.x, c0.y), 2)},
                "bench_proposal": proposal,
                "gate2": gate2,
                "pad_iou_advisory": wh.pad_iou(conn, u),
                "pdp_in_unit": wh.pdp_in_unit(conn, u),
            })
    # Stacked DSUs share one footprint, and narvi attaches every tract to the
    # first polygon it matches — a tract that declares the TWIN's window is not
    # a disagreement, it is the twin's paper. Resolve that before flagging.
    resolve_twin_tracts(out["units"])
    for u in out["units"]:
        for tw in u["tract_windows"]:
            if tw["disagrees"]:
                out.setdefault("warnings", []).append(
                    f"{u['label']}: tract {tw['tract']} declares {tw['rights']} vs the DSU's {u['rights']} "
                    "— DSU window used; reviewer confirms")
    write_json(run_dir / "proposal.json", out)
    write_json(run_dir / "review_geoms.json", review_geoms)
    # The reviewer's file is never overwritten: a re-propose writes the fresh
    # seed beside it for comparison.
    target = run_dir / unit_benches.FILENAME
    if target.exists():
        target = run_dir / "benches.seed.yaml"
        out.setdefault("warnings", []).append(
            f"{unit_benches.FILENAME} already exists (reviewer edits kept) — fresh seed written to {target.name}")
    target.write_text(unit_benches.render(out), encoding="utf-8")
    return out


# =============================================================================
# Stage 2 — evaluate
# =============================================================================

def _median(vals: list[float]) -> float | None:
    vals = [v for v in vals if v is not None]
    return statistics.median(vals) if vals else None


def _edge_fired(support_rows: list[dict[str, Any]], cfg: Config) -> tuple[bool, dict[str, Any]]:
    et = cfg["edge_trigger"]
    dn = _median([r.get("dist_nearest_ft") for r in support_rows])
    c1 = _median([r.get("pdp_count_1mi") for r in support_rows])
    c5 = _median([r.get("pdp_count_5mi") for r in support_rows])
    decay = (c1 / c5) if c1 is not None and c5 else None
    fired = (dn is not None and dn > float(et["dist_nearest_ft_max"])) or (
        decay is not None and decay < float(et["ring_decay_min"]))
    return fired, {"dist_nearest_ft_median": dn, "ring_decay": decay}


def _fmt(v: float | None, spec: str) -> str:
    return "n/a" if v is None else format(v, spec)


def _select_pool(
    fetch: Callable[[float], list[dict[str, Any]]],
    classify_fn: Callable[[list[dict[str, Any]]], tuple[list, list, list]],
    *, min_wells: int, edge: bool, radius_override: float | None = None,
) -> tuple[float, list, list, list]:
    """Gate 5a radius walk. Default: step RADIUS_STEPS_MI until the pool reaches
    min_wells; a fired edge trigger stops at the first step (strike-biased set
    is the reviewer's call). radius_override = REVIEWER decision: exactly that
    concentric radius, edge block bypassed (an emerging bench trips the edge
    proxy on thin development, not basin position)."""
    steps = (radius_override,) if radius_override is not None else RADIUS_STEPS_MI
    for radius in steps:
        eligible, excluded, adjacent = classify_fn(fetch(radius))
        if radius_override is None and (len(eligible) >= min_wells or edge):
            break
    return radius, eligible, excluded, adjacent


def planned_standoff(unit_geom: Any, azimuth_deg: float, locations: list[dict[str, Any]],
                     existing: list[dict[str, Any]], bench: str, tvd_ft: float,
                     gate_ft: float, band_ft: float, same_landing_ft: float = 0.0) -> dict[str, Any]:
    """Where do OUR sticks sit against the producers already in the unit? Per
    planned stick: the nearest other-bench producer inside the vertical-parent
    gate (|cross offset| <= gate_ft, 0 < |dTVD| <= band_ft) in the rule-16
    gunbarrel plane. dtvd_ft > 0 = the producer is BELOW (our stick is a
    topfill); < 0 = above (underfill). Same-bench producers are neighbours,
    not vertical parents — and so is an other-bench producer within
    `same_landing_ft` vertically (same landing, the bench TAG differs: counted
    apart as n_same_landing for the reviewer). Diagnostic only — nothing
    selects on it."""
    from shapely import wkt as _wkt

    project, _, _ = gunbarrel_frame(unit_geom, azimuth_deg)
    prods = [e for e in existing if e.get("inside") and e.get("offset_ft") is not None
             and e.get("tvd_ft") is not None and e.get("bench") not in ("(unmapped)", bench)]
    rows = []
    for loc in locations:
        off = project(_wkt.loads(loc["wkt"]))[0]
        tv = float(loc.get("tvd") or tvd_ft)
        near = sorted(((abs(e["tvd_ft"] - tv), e) for e in prods
                       if abs(e["offset_ft"] - off) <= gate_ft and same_landing_ft < abs(e["tvd_ft"] - tv) <= band_ft),
                      key=lambda t: t[0])
        e = near[0][1] if near else None
        same = [e2["bench"] for e2 in prods
                if abs(e2["offset_ft"] - off) <= gate_ft and abs(e2["tvd_ft"] - tv) <= same_landing_ft]
        rows.append({"id": loc["id"], "offset_ft": round(off), "same_landing": sorted(set(same)),
                     "parent_bench": e["bench"] if e else None,
                     "dtvd_ft": round(e["tvd_ft"] - tv) if e else None,
                     "dx_ft": round(e["offset_ft"] - off) if e else None})
    hit = [r for r in rows if r["parent_bench"]]
    closest = min(hit, key=lambda r: abs(r["dtvd_ft"])) if hit else None
    return {"n_sticks": len(rows), "n_with_parent": len(hit), "gate_ft": gate_ft, "band_ft": band_ft,
            "n_same_landing": sum(1 for r in rows if r["same_landing"]),
            "same_landing_benches": sorted({b for r in rows for b in r["same_landing"]}),
            "nearest_bench": closest["parent_bench"] if closest else None,
            "nearest_dtvd_ft": closest["dtvd_ft"] if closest else None,
            "median_abs_dtvd_ft": _median([abs(r["dtvd_ft"]) for r in hit]), "sticks": rows}


def cohort_standoff(cohort: list[dict[str, Any]]) -> dict[str, Any]:
    """The cohort's own history: how many wells came on over/under an
    unshielded vertical parent (dev_scenario rule, sql/50) and at what
    vertical standoff (nearest parent per well)."""
    vals = []
    for c in cohort:
        bc = c.get("bench_context") or {}
        d = [abs(float(bc[b]["parent_nearest_dtvd_ft"])) for b in vertical_parents(c)
             if (bc.get(b) or {}).get("parent_nearest_dtvd_ft") is not None]
        if d:
            vals.append(min(d))
    return {"n": len(cohort), "n_with_parent": len(vals), "median_abs_dtvd_ft": _median(vals),
            "min_abs_dtvd_ft": min(vals) if vals else None, "max_abs_dtvd_ft": max(vals) if vals else None}


def standoff_flags(units: dict[str, dict[str, Any]], cohort: dict[str, Any]) -> list[str]:
    """ONE flag per TC group: the units whose sticks sit over/under a producer
    MORE than the cohort did — a larger share of parented sticks, or a tighter
    standoff than any cohort well — plus any stick landing at the depth of a
    producer tagged to another bench. The curve carries neither; the reviewer
    reads the standoff table and risks by hand."""
    c_share = cohort["n_with_parent"] / cohort["n"] if cohort["n"] else 0.0
    more = []
    for label, s in units.items():
        if not s or not s["n_with_parent"]:
            continue
        tighter = cohort["min_abs_dtvd_ft"] is None or abs(s["nearest_dtvd_ft"]) < cohort["min_abs_dtvd_ft"]
        if s["n_with_parent"] / s["n_sticks"] > c_share or tighter:
            more.append(f"{label} ({s['n_with_parent']}/{s['n_sticks']} sticks, nearest {s['nearest_bench']} "
                        f"{abs(s['nearest_dtvd_ft']):,.0f} ft {'below' if s['nearest_dtvd_ft'] > 0 else 'above'})")
    out = []
    if more:
        out.append(
            f"standoff: {len(more)} unit(s) are more parented than the cohort ({cohort['n_with_parent']} of {cohort['n']} "
            "cohort wells came on over/under a producer"
            + (f", median standoff {cohort['median_abs_dtvd_ft']:,.0f} ft" if cohort["n_with_parent"] else "")
            + f"): {'; '.join(more)} — the curve does not carry this; reviewer risks by hand")
    same = [f"{label} ({s['n_same_landing']} stick(s) at the depth of {', '.join(s['same_landing_benches'])})"
            for label, s in units.items() if s and s.get("n_same_landing")]
    if same:
        out.append("same landing, different tag: " + "; ".join(same)
                   + " — a producer tagged to another bench sits at our landing depth inside the gate; check the tag or the placement")
    return out


def scenario_groups(units: list[str], existing_by_unit: dict[str, dict[str, list[str]]]) -> list[dict[str, Any]]:
    """Split a TC group's units by FIRST-ORDER scenario (Michael, 2026-09-29):
      infill      units with producers within the vertical band of this bench —
                  topfill/underfill tier first, parent test = THOSE units' benches
      greenfield  units with none — pad-mates (codev) first, no parent test
    A bench-wide majority vote put a topfill/underfill curve on greenfield
    units (VaULt BS3_C: 36.8k vs a 54.5k codev tier). At most two per group;
    a group whose units share one scenario stays whole."""
    infill = [u for u in units if existing_by_unit.get(u, {}).get("above") or existing_by_unit.get(u, {}).get("below")]
    green = [u for u in units if u not in infill]
    out: list[dict[str, Any]] = []
    if infill:
        ex = sorted({b for u in infill for k in ("above", "below") for b in existing_by_unit[u][k]})
        out.append({"scenario": "infill", "units": infill, "existing": ex, "flip": True})
    if green:
        out.append({"scenario": "greenfield", "units": green, "existing": [], "flip": False})
    return out


def group_pool(eligible: list[dict[str, Any]], cl: list[str], whole: bool) -> list[dict[str, Any]]:
    """Pool wells for a reviewer TC group: the whole eligible pool when the
    group spans the class, else the wells the split test assigned to those
    units (their `unit` tag; None when the split test never ran)."""
    return list(eligible) if whole else [c for c in eligible if c.get("unit") in cl]


def shared_offsets(pool: list[dict[str, Any]], units: dict[str, Any], radius_ft: float) -> dict[str, int]:
    """Per unit: pool wells whose mid-lateral point lies within `radius_ft` of
    the unit polygon — NOT exclusive (a well counts for every unit it is near)."""
    from shapely.geometry import Point

    from dealintake.geo import M_PER_FT, LocalFrame
    out: dict[str, int] = {}
    for label, poly in units.items():
        frame = LocalFrame.around(poly)
        local = frame.to_local(poly)
        out[label] = sum(1 for c in pool if c.get("lon") is not None
                         and local.distance(frame.to_local(Point(c["lon"], c["lat"]))) <= radius_ft * M_PER_FT)
    return out


def pool_lateral_band(lls: list[float], cfg: Config, basin: str | None) -> tuple[float, float]:
    """One pool per bench: the band SPANS the units' planned laterals — the
    shortest unit's lower bound to the longest unit's upper bound, each at its
    own tolerance (basin band; long-lateral tolerance at/above long_lateral.min_ft)."""
    lo, hi = min(lls), max(lls)
    return lo * (1 - cfg.lateral_tolerance(basin, lo)), hi * (1 + cfg.lateral_tolerance(basin, hi))


def length_check(pool: list[dict[str, Any]], metric: str, cfg: Config) -> dict[str, Any]:
    """Does per-1,000-ft performance move with lateral length INSIDE this pool?
    Median of `metric` per length bucket vs the pool median; a bucket with
    enough wells that sits outside flag_ratio is flagged. A check on the linear
    per-1,000-ft scaling that one-pool-per-bench relies on — never a filter."""
    lc = cfg["planned_lateral"]["length_check"]
    edges = [float(e) for e in lc["bucket_edges_ft"]]
    min_n, ratio = int(lc["min_wells"]), float(lc["flag_ratio"])
    rows = [(float(c["lateral_length_ft"]), float(c[metric])) for c in pool
            if c.get("lateral_length_ft") and c.get(metric)]
    pool_med = _median([v for _, v in rows])
    bounds = [0.0, *edges, float("inf")]
    buckets, flags = [], []
    for lo, hi in pairwise(bounds):
        vals = [(ll, v) for ll, v in rows if lo <= ll < hi]
        if not vals:
            continue
        label = (f"< {hi:,.0f} ft" if lo == 0 else f">= {lo:,.0f} ft" if hi == float("inf")
                 else f"{lo:,.0f}-{hi:,.0f} ft")
        med = _median([v for _, v in vals])
        vs = med / pool_med if med and pool_med else None
        judged = len(vals) >= min_n and vs is not None
        flagged = bool(judged and (vs > ratio or vs < 1 / ratio))
        buckets.append({"bucket": label, "n": len(vals), "median_lateral_ft": _median([ll for ll, _ in vals]),
                        "median_per_1000ft": med, "vs_pool": vs, "judged": judged, "flagged": flagged})
        if flagged:
            flags.append(f"length check: {label} wells (n {len(vals)}) run {vs - 1:+.0%} vs the pool median per 1,000 ft "
                         f"— beyond {ratio:g}x; linear scaling across lengths is suspect for this bench")
    return {"metric": metric, "pool_median_per_1000ft": pool_med, "n": len(rows), "min_wells": min_n,
            "flag_ratio": ratio, "buckets": buckets, "flags": flags}


def lateral_support(cohort: list[dict[str, Any]], ll_by_unit: dict[str, float], cfg: Config,
                    basin: str | None) -> tuple[list[dict[str, Any]], list[str]]:
    """Per unit: is its planned lateral INSIDE the cohort's observed lateral
    range, and how many cohort wells sit within the unit's own band? Outside
    the range = the curve is a linear EXTRAPOLATION for that unit — flagged."""
    lls = sorted(float(c["lateral_length_ft"]) for c in cohort if c.get("lateral_length_ft"))
    min_n = int(cfg["planned_lateral"]["length_check"]["min_wells_near_planned"])
    rows, flags = [], []
    for label, ll in ll_by_unit.items():
        tol = cfg.lateral_tolerance(basin, ll)
        near = sum(1 for v in lls if ll * (1 - tol) <= v <= ll * (1 + tol))
        outside = bool(lls) and not lls[0] <= ll <= lls[-1]
        rows.append({"unit": label, "planned_lateral_ft": ll, "n_within_band": near, "band_tol": tol,
                     "cohort_min_ft": lls[0] if lls else None, "cohort_max_ft": lls[-1] if lls else None,
                     "extrapolated": outside, "thin": near < min_n})
        if outside:
            flags.append(f"{label}: planned lateral {ll:,.0f} ft is OUTSIDE the cohort's lateral range "
                         f"({lls[0]:,.0f}-{lls[-1]:,.0f} ft) — the per-1,000-ft curve is a linear extrapolation here")
        elif lls and near < min_n:
            flags.append(f"{label}: only {near} cohort well(s) within +/-{tol:.0%} of the planned {ll:,.0f} ft lateral "
                         "— length scaling rests on the rest of the pool")
    return rows, flags


def lateral_classes(ll_by_unit: dict[str, float], ratio: float) -> list[list[str]]:
    """Group units by planned lateral, shortest first: a unit joins the current
    class while its lateral is within `ratio` of the class's SHORTEST member,
    else it opens a new class. One pool / split test / type curve per (bench x
    class), lateral band centered on the class median — a 3-mile unit is not
    type-curved from a band centered on 2-mile wells (Michael, 2026-09-21)."""
    out: list[list[str]] = []
    base = 0.0
    for label, ll in sorted(ll_by_unit.items(), key=lambda kv: (kv[1], kv[0])):
        if out and ll <= base * ratio:
            out[-1].append(label)
        else:
            out.append([label])
            base = ll
    return out


def evaluate(
    run_dir: Path,
    cfg: Config,
    *,
    benches: list[str] | None = None,
    spacing_ft: dict[str, float] | None = None,
    use_anduin: bool = True,
    tc_group_overrides: dict[str, list[list[str]]] | None = None,
    short_history_transfer: int | None = None,
    radius_overrides: dict[str, float] | None = None,
    tc_single: list[str] | None = None,
    narvi: Narvi | None = None,
    anduin: Anduin | None = None,
) -> dict[str, Any]:
    """tc_single: benches the REVIEWER pools into one TC per class regardless of
    the split test (an escalated gradient with no clean break; a split he
    chose to pool without a multiplier) — decision-logged like --tc-groups.
    radius_overrides: {bench: miles} — REVIEWER decision: the eligible pool
    is drawn at exactly that concentric radius, bypassing the radius steps and
    the edge-trigger block. Recorded in the pool flags + decision log.
    tc_group_overrides: {bench: [[unit, ...], ...]} — REVIEWER decision that
    replaces the split test's grouping for that bench (e.g. an escalated
    gradient).
    short_history_transfer: post-peak-month cutoff; the CLI passes the config default (9) unless disabled.
    Runs anduin's cohort transfer on each bench's whole eligible pool: wells
    with fewer post-peak months get the long wells' median Di/b + their own
    peak rate. WRITES/overwrites those wells' unlocked anduin rows — the
    dossier lists them. Units not named form one remaining group. Recorded in
    signals.json + the dossier decision log; the split test still runs and is
    reported beside it."""
    prop = json.loads((run_dir / "proposal.json").read_text(encoding="utf-8"))
    narvi = narvi or Narvi()
    spacing_ft = spacing_ft or {}
    all_units = {u["label"]: shape(u["geometry"]) for u in prop["units"]}

    # Per-unit plan: which benches each unit evaluates + its planned lateral.
    # --benches = one deal-wide list (simple deals); otherwise the reviewer's
    # benches.yaml (depth-severed stacked DSUs need a list per unit).
    if benches:
        deal_wide = [bench_code(b) for b in benches]
        plan = {u["label"]: {"benches": deal_wide, "planned_lateral_ft": float(u["planned_lateral"]["median_ft"]),
                             "seed_benches": deal_wide, "edited": False, "bench_opts": {}, "min_leg_ft": None}
                for u in prop["units"]}
        plan_source = "--benches (deal-wide)"
    else:
        plan = unit_benches.read(run_dir, prop)
        plan_source = unit_benches.FILENAME
    benches = list(dict.fromkeys(b for p in plan.values() for b in p["benches"]))
    if not benches:
        raise ValueError(f"no bench enabled in any unit ({plan_source})")

    # Planned stack order (shallow -> deep) from the local medians of the units
    # that actually plan each bench.
    tvd_by_bench: dict[str, list[float]] = {}
    for u in prop["units"]:
        pu = plan[u["label"]]
        for r in u["bench_proposal"]:
            b = bench_code(r["bench"])
            if r["median_tvd_ft"] is not None and b in pu["benches"] and "tvd_ft" not in (pu["bench_opts"].get(b) or {}):
                tvd_by_bench.setdefault(b, []).append(r["median_tvd_ft"])
        for b, o in pu["bench_opts"].items():          # reviewer-supplied TVDs (thin / no local control)
            if "tvd_ft" in o:
                tvd_by_bench.setdefault(b, []).append(o["tvd_ft"])
    missing = [b for b in benches if b not in tvd_by_bench]
    if missing:
        raise ValueError(f"no local median TVD for {missing} in the units that enable them ({plan_source}) "
                         "— give the bench a reviewer tvd_ft in benches.yaml")
    tc_single = [bench_code(b) for b in (tc_single or [])]
    radius_overrides = {bench_code(b): float(r) for b, r in (radius_overrides or {}).items()}
    stray = [b for b in radius_overrides if b not in benches]
    if stray:
        raise ValueError(f"--radius names {stray}, not in the evaluated benches {benches}")
    if any(r <= 0 for r in radius_overrides.values()):
        raise ValueError(f"--radius must be > 0 mi, got {radius_overrides}")
    stack = sorted(benches, key=lambda b: statistics.median(tvd_by_bench[b]))
    bench_tvd = {b: statistics.median(tvd_by_bench[b]) for b in stack}

    ll_by_unit = {lb: p["planned_lateral_ft"] for lb, p in plan.items() if p["benches"]}
    class_ratio = float(cfg["planned_lateral"].get("class_ratio", 1.10))
    # Michael 2026-09-28: ONE POOL PER BENCH, per 1,000 ft, scaled linearly to each
    # unit's planned lateral (25 mi of VaULt: 3-mile vs 2-mile 30-yr EUR/1,000 ft
    # within -13%/+8%, mixed sign; per-class pools were thinner than the effect).
    # `class` keeps the v4-v7 per-lateral-class pools.
    pooling = str(cfg["planned_lateral"].get("pooling", "bench"))
    if pooling not in ("bench", "class"):
        raise ValueError(f"planned_lateral.pooling must be bench|class, got {pooling!r}")
    res: dict[str, Any] = {
        "run_dir": str(run_dir), "config_version": cfg.version, "snapshot": prop["snapshot"],
        "planned_stack": stack, "bench_tvd_ft": bench_tvd,
        "planned_lateral_ft": _median(list(ll_by_unit.values())) or 0.0,
        "pooling": pooling,
        "lateral_classes": ([{"units": c, "planned_lateral_ft": _median([ll_by_unit[u] for u in c])}
                             for c in lateral_classes(ll_by_unit, class_ratio)] if pooling == "class" else []),
        "unit_plan": plan, "plan_source": plan_source,
        "flags": [], "benches": {}, "decision_log": [],
    }
    if len(res["lateral_classes"]) > 1:
        res["flags"].append(
            "planned laterals fall into " + str(len(res["lateral_classes"])) + " classes ("
            + ", ".join(f"{c['planned_lateral_ft']:,.0f} ft x{len(c['units'])}" for c in res["lateral_classes"])
            + f"; units within {class_ratio - 1:.0%} share a class): each bench is pooled, split-tested and "
              "type-curved PER CLASS, with the lateral band centered on the class")
    elif pooling == "bench" and ll_by_unit and max(ll_by_unit.values()) > min(ll_by_unit.values()) * class_ratio:
        res["flags"].append(
            f"planned laterals span {min(ll_by_unit.values()):,.0f}-{max(ll_by_unit.values()):,.0f} ft: ONE pool and one "
            "type curve per bench, per 1,000 ft, scaled LINEARLY to each unit's lateral. Each bench carries a length "
            "check (per-1,000-ft by length bucket) and a flag where a unit's lateral is outside the cohort's range")
    for lb, p in plan.items():
        res["decision_log"].append({
            "gate": "1 unit benches + lateral", "bench": lb,
            "signal": f"seed: {', '.join(p['seed_benches']) or 'none'}",
            "decision": (f"{', '.join(p['benches']) or 'NOT EVALUATED'}; planned lateral {p['planned_lateral_ft']:,.0f} ft"
                         + "".join(f"; {b} " + ", ".join(f"{k} {v}" for k, v in o.items())
                                   for b, o in p.get("bench_opts", {}).items() if o)
                         + (f"; min leg {p['min_leg_ft']:,.0f} ft" if p.get("min_leg_ft") else "")
                         + (" (edited vs seed)" if p["edited"] else "")),
            "by": f"reviewer ({plan_source})",
        })

    # anduin requested -> it must work. A silent degrade made a run with no
    # forecast/QC/TC look successful (2026-09-18); only --no-anduin skips it.
    ad: Anduin | None = None
    if use_anduin:
        ad = anduin or Anduin()
        try:
            ad.login()
        except AnduinError as e:
            raise AnduinError(f"{e} (or pass --no-anduin to run warehouse-only signals)") from e
    else:
        res["flags"].append("anduin not run (--no-anduin): no forecast, Di QC or TC preview; "
                            "split test uses the Novi EUR screen")

    # One job per (bench x lateral class of the units that plan that bench).
    jobs: list[tuple[str, list[str], str]] = []
    for bench in stack:
        ll_b = {lb: ll_by_unit[lb] for lb, p in plan.items() if bench in p["benches"]}
        classes = lateral_classes(ll_b, class_ratio) if pooling == "class" else [sorted(ll_b, key=lambda u: (ll_b[u], u))]
        for cl in classes:
            ll_c = _median([ll_b[u] for u in cl])
            jobs.append((bench, cl, bench if len(classes) == 1 else f"{bench} @ {ll_c:,.0f} ft"))
    known_units = set(all_units)

    with wh.connect() as conn:
        for bench, class_units, key in jobs:
            units = {lb: all_units[lb] for lb in class_units}
            union = unary_union(list(units.values()))
            planned_ll = _median([ll_by_unit[lb] for lb in class_units]) or 0.0
            local_tvds = [r["median_tvd_ft"] for u in prop["units"] if u["label"] in units
                          for r in u["bench_proposal"]
                          if bench_code(r["bench"]) == bench and r["median_tvd_ft"] is not None]
            B: dict[str, Any] = {"bench": bench, "key": key, "units": {}, "class_units": class_units,
                                 "planned_lateral_ft": planned_ll,
                                 "tvd_ft": _median(local_tvds) or bench_tvd[bench]}
            res["benches"][key] = B
            novi_sp = _median([
                g.get("novi_spacing_ft")
                for u in prop["units"] if u["label"] in units
                for b, g in (u.get("gate2") or {}).items() if bench_code(b) == bench
            ])
            unit_sp = {lb: (plan[lb]["bench_opts"].get(bench) or {}).get("spacing_ft") for lb in class_units}
            rev_sp = _median([v for v in unit_sp.values() if v])
            if bench in spacing_ft:
                sp, sp_src = float(spacing_ft[bench]), "reviewer (--spacing)"
            elif rev_sp:
                sp, sp_src = float(rev_sp), "reviewer (benches.yaml, median over the class units)"
            else:
                sp, sp_src = DEFAULT_SPACING_FT, f"default {DEFAULT_SPACING_FT:.0f} ft (narvi fallback)"
            B["spacing_ft"] = sp
            B["spacing_source"] = sp_src + (f"; Novi de-facto pattern {novi_sp:,.0f} ft (suggestion only)" if novi_sp else "")
            B["novi_spacing_ft"] = novi_sp
            support_all: list[dict[str, Any]] = []
            adj = adjacent_benches(bench, stack)
            # Basin (per-basin lateral tolerance, ledger §9) = majority basin of the
            # in-bench producers within the first selection radius.
            cands0 = wh.candidates(conn, union, bench, RADIUS_STEPS_MI[0])
            bc = Counter(c["basin"] for c in cands0 if c["basin"]).most_common(1)
            basin = bc[0][0] if bc else None
            B["basin"] = basin
            tol = cfg.lateral_tolerance(basin)
            band_ll = (pool_lateral_band([ll_by_unit[lb] for lb in class_units], cfg, basin)
                       if pooling == "bench" else None)
            B["lateral_band_ft"] = list(band_ll) if band_ll else [
                planned_ll * (1 - cfg.lateral_tolerance(basin, planned_ll)),
                planned_ll * (1 + cfg.lateral_tolerance(basin, planned_ll))]

            for u in prop["units"]:
                if u["label"] not in units:
                    continue
                label, geom = u["label"], units[u["label"]]
                # Landing TVD = THIS unit's local offset median (units can sit
                # >1,000 ft apart structurally — Toucan WCA_1 9,735 vs 10,852 ft);
                # the cross-unit median only orders the stack / is the fallback.
                local_tvd = next((r["median_tvd_ft"] for r in u["bench_proposal"]
                                  if bench_code(r["bench"]) == bench and r["median_tvd_ft"] is not None), None)
                opts = plan[label]["bench_opts"].get(bench) or {}
                if "tvd_ft" in opts:
                    tvd_u, tvd_src = float(opts["tvd_ft"]), "reviewer (benches.yaml)"
                else:
                    tvd_u = float(local_tvd if local_tvd is not None else bench_tvd[bench])
                    tvd_src = "unit local median" if local_tvd is not None else "cross-unit median (no local control)"
                sp_u = float(opts.get("spacing_ft") or sp)
                g2 = u["gate2"].get(bench) or {"source": "generate", "reason": "no Novi sticks in bench",
                                               "pud_inside": 0, "pud_crossing": 0}
                unit_novi: list[int] = []
                UB: dict[str, Any] = {"gate2": g2, "tvd_ft": tvd_u, "tvd_source": tvd_src,
                                      "spacing_ft": sp_u, "role": opts.get("role", "base"), "row_rules": []}
                if g2["source"] == "novi":
                    sticks = [s for s in wh.novi_sticks(conn, geom)
                              if s["formation_blueox"] == bench and s["category"] == "PUD"
                              and stick_relation(s["geom"], geom, float(cfg["alignment"]["stick_inside_tolerance_ft"])) == "inside"]
                    UB["locations"] = [{"id": s["stick_id"], "src": "novi", "ll_ft": s["ll_ft"],
                                        "tvd": s["tvd"], "wkt": s["geom"].wkt} for s in sticks]
                    sup = [{k: s.get(k) for k in ("pdp_count_1mi", "pdp_count_3mi", "pdp_count_5mi",
                                                  "dist_nearest_ft", "offset_median_eur_ft",
                                                  "tvd_excess_3mi_ft", "wca_delta_ft")} for s in sticks]
                    unit_novi += [s["stick_id"] for s in sticks]
                else:
                    # narvi takes a UTM-13N GRID bearing; the plan is a TRUE bearing.
                    gen = narvi.generate(
                        geom, [{"formation": bench, "target_tvd_ft": tvd_u, "spacing_ft": sp_u}],
                        setback_ft=float(cfg["planned_lateral"]["setback_ft"]), spacing_ft=sp_u,
                        azimuth_deg=true_to_grid(u["planned_lateral"]["azimuth_deg"], geom.centroid.x, geom.centroid.y),
                    )
                    lg = legs(gen)
                    # Reviewer row rules (n_wells / keep_side / drop_<side>_rows / min_leg_ft).
                    project, _, _ = gunbarrel_frame(geom, u["planned_lateral"]["azimuth_deg"])
                    rows = [{"offset_ft": round(project(leg["geom"])[0]),
                             "lateral_ft": round(float(leg.get("completed_lateral_ft") or 0)), "leg": leg} for leg in lg]
                    kept, notes = apply_row_rules(
                        rows, u["planned_lateral"]["azimuth_deg"], n_wells=opts.get("n_wells"),
                        keep_side=opts.get("keep_side"),
                        drop_rows={sd: opts[f"drop_{sd}_rows"] for sd in ("west", "east", "north", "south")
                                   if opts.get(f"drop_{sd}_rows")},
                        min_leg_ft=plan[label]["min_leg_ft"])
                    lg = [r["leg"] for r in kept]
                    UB["row_rules"] = notes
                    UB["n_generated"] = len(rows)
                    UB["locations"] = [{"id": f"gen-{i}", "src": "narvi_preview",
                                        "ll_ft": leg.get("completed_lateral_ft"), "tvd": tvd_u,
                                        "wkt": leg["geom"].wkt} for i, leg in enumerate(lg)]
                    sup = [wh.pdp_support(conn, leg["geom"], bench, tvd_u) for leg in lg]
                    for leg in lg:
                        leg_ft = float(leg.get("completed_lateral_ft") or planned_ll)
                        # Long generated legs (>= long_lateral.min_ft) use the wider tolerance for
                        # the Novi representative pull too (Michael 2026-09-28; ledger s9 note):
                        # Novi's 5,080-ft sticks fell outside +/-25% of 15,144-ft legs.
                        unit_novi += wh.representative_sticks(
                            conn, leg["geom"], bench, leg_ft, cfg.lateral_tolerance(basin, leg_ft))
                UB["standoff"] = planned_standoff(
                    geom, u["planned_lateral"]["azimuth_deg"], UB["locations"],
                    (u.get("gunbarrel") or {}).get("existing", []), bench, tvd_u,
                    float(PARENT_GATE_FT), float(cfg["codev"]["scenario_band_ft"]),
                    float(cfg["codev"].get("same_landing_ft", 0.0)))
                c3 = [r.get("pdp_count_3mi") for r in sup if r.get("pdp_count_3mi") is not None]
                UB["gate3"] = {
                    "n_locations": len(sup),
                    "pdp_count_3mi_min": min(c3) if c3 else None,
                    "pdp_count_3mi_median": _median(c3),
                    "pdp_count_3mi_max": max(c3) if c3 else None,
                    "n_unscorable": sum(1 for r in sup if r.get("pdp_count_3mi") is None),
                    "tvd_excess_3mi_ft_max": max((r["tvd_excess_3mi_ft"] for r in sup
                                                  if r.get("tvd_excess_3mi_ft") is not None), default=None),
                }
                med = UB["gate3"]["pdp_count_3mi_median"]
                thr = int(cfg["bench_inclusion"]["pdp_count_3mi_min"])
                UB["gate3"]["status"] = ("escalate (unscorable)" if med is None
                                         else "pass" if med >= thr else "escalate (marginal: live re-count before excluding)")
                UB["has_pdp_in_adjacent_bench"] = any(p["bench"] in adj for p in u["pdp_in_unit"])
                UB["novi_ids"] = sorted(set(unit_novi))
                support_all += sup
                B["units"][label] = UB

            # ---- Gate 5a: eligible POOL (no cap yet) ------------------------------
            edge, edge_sig = _edge_fired(support_all, cfg)
            B["edge_trigger"] = {"fired": edge, **edge_sig}
            # First-order scenario (Michael, 2026-09-28): what is PRODUCING in each
            # unit within the vertical band of this bench — those benches are the
            # parent test for the cohort, and a strict majority of units with such
            # producers puts the topfill/underfill tier first.
            band = float(cfg["codev"]["scenario_band_ft"])
            existing_by_unit: dict[str, dict[str, list[str]]] = {}
            for u in prop["units"]:
                if u["label"] not in units:
                    continue
                tvd_here = B["units"][u["label"]]["tvd_ft"]
                above = sorted({e["bench"] for e in (u.get("gunbarrel") or {}).get("existing", [])
                                if e["inside"] and 0 < tvd_here - e["tvd_ft"] <= band and e["bench"] != "(unmapped)"})
                below = sorted({e["bench"] for e in (u.get("gunbarrel") or {}).get("existing", [])
                                if e["inside"] and 0 < e["tvd_ft"] - tvd_here <= band and e["bench"] != "(unmapped)"})
                existing_by_unit[u["label"]] = {"above": above, "below": below}
                B["units"][u["label"]]["existing_above"] = above
                B["units"][u["label"]]["existing_below"] = below
            existing_benches = sorted({b for v in existing_by_unit.values() for b in v["above"] + v["below"]})
            B["existing_benches_in_band"] = existing_benches
            pdp_adj_units = [lb for lb, v in existing_by_unit.items() if v["above"] or v["below"]]
            tier_scope = str(cfg["codev"].get("tier_order_scope", "none"))
            if tier_scope not in ("none", "unit", "bench"):
                raise ValueError(f"codev.tier_order_scope must be none|unit|bench, got {tier_scope!r}")
            flip = len(pdp_adj_units) * 2 > len(B["units"])
            min_wells = int(cfg["type_curve"]["min_wells"])
            pool_flags: list[str] = []
            r_over = radius_overrides.get(bench)
            radius, eligible, excluded, adjacent = _select_pool(
                lambda r, _b=bench, _c=cands0, _un=union: (
                    _c if r == RADIUS_STEPS_MI[0] else wh.candidates(conn, _un, _b, r)),
                lambda cands, _b=bench, _bn=basin, _sp=sp, _ll=planned_ll, _ex=existing_benches, _bd=band_ll: classify(
                    cands, cfg, bench=_b, planned_stack=stack, planned_lateral_ft=_ll,
                    basin=_bn, planned_spacing_ft=_sp, existing_benches=_ex, lateral_band_ft=_bd),
                min_wells=min_wells, edge=edge, radius_override=r_over,
            )
            pool_tol = cfg.lateral_tolerance(basin, planned_ll)
            pool_flags.append(f"radius {radius} mi{' (REVIEWER override)' if r_over is not None else ''}, basin {basin}, "
                              + (f"lateral band {band_ll[0]:,.0f}-{band_ll[1]:,.0f} ft (spans the units' planned laterals)"
                                 if band_ll else
                                 f"lateral tol {pool_tol:.0%}{' (long-lateral class)' if pool_tol > tol else ''}")
                              + f", eligible pool {len(eligible)}")
            if r_over is not None:
                if edge:
                    pool_flags.append("EDGE trigger fired — bypassed by the reviewer radius override (concentric pool)")
                res["decision_log"].append({
                    "gate": "5a pool radius", "bench": key,
                    "signal": (f"edge trigger {'FIRED' if edge else 'not fired'} (median dist to nearest PDP "
                               f"{_fmt(edge_sig['dist_nearest_ft_median'], ',.0f')} ft, ring decay "
                               f"{_fmt(edge_sig['ring_decay'], '.2f')}); "
                               f"auto steps {'/'.join(f'{s:g}' for s in RADIUS_STEPS_MI)} mi"),
                    "decision": f"{r_over:g} mi concentric, eligible pool {len(eligible)}", "by": "reviewer",
                })
            elif edge and len(eligible) < min_wells:
                pool_flags.append("EDGE trigger fired: no concentric extension — propose strike-biased set (reviewer confirms)")
            if existing_benches:
                pool_flags.append(
                    f"producers within {band:,.0f} ft of this bench in {len(pdp_adj_units)}/{len(B['units'])} units "
                    f"({', '.join(existing_benches)}): "
                    + ("reported only — the cohort is the nearest wells of the pool whatever their scenario; each TC "
                       "group carries a standoff table (our sticks vs the cohort's parents)"
                       if tier_scope == "none" else
                       "tier order is decided PER UNIT — infill units get a topfill/underfill-first cohort (parent test = "
                       "their own in-band benches), greenfield units a pad-mates-first cohort, from this same pool"
                       if tier_scope == "unit" else
                       f"{'majority -> topfill/underfill tier first' if flip else 'no majority -> pad-mates first'}; "
                       "cohort parent test = these benches (first-order)"))
            order, order_reason = tier_order(cfg, adjacent, flip)
            if tier_scope == "unit":
                order_reason = "bench-wide vote shown for the pool only; each TC group states its own order"
            elif tier_scope == "none":
                order, _ = tier_order(cfg, adjacent, False)
                order_reason = "tier-blind cohort: nearest wells of the pool; scenario is reported, not selected on"
            B["pool"] = {
                "n_eligible": len(eligible), "n_excluded": len(excluded), "flags": pool_flags,
                "adjacent_planned": adjacent, "tier_order": order, "order_reason": order_reason,
                "exclusion_reasons": Counter(r for c in excluded for r in c["exclusion"].split(";")),
            }

            # ---- Gate 5.5: anduin fits for the WHOLE pool (split test needs them) --
            rows_all: list[dict[str, Any]] = []
            if ad and eligible:
                B["anduin_forecast"] = ad.forecast([c["api10"] for c in eligible])
                if short_history_transfer:
                    B["short_history_transfer"] = _transfer(ad, eligible, short_history_transfer)
                rows_all = ad.forecasts([c["api10"] for c in eligible])
                eur_ft = {r["api10"]: float(r["eur"]) / float(r["well_lateral_ft"]) * 1000.0
                          for r in rows_all if r["stream"] == "oil" and r.get("eur") and r.get("well_lateral_ft")}
                for c in eligible:
                    c["anduin_oil_eur_per_1000ft"] = eur_ft.get(c["api10"])
                metric = "anduin_oil_eur_per_1000ft"
            else:
                metric = "eur_per_1000ft"

            B["length_check"] = length_check(eligible, metric, cfg)
            pool_flags += B["length_check"]["flags"]

            # ---- Gate 5b: split test on the POOL, before any cohort is filled -----
            sr = split_test.run(eligible, units, cfg, metric=metric)   # tags c["unit"], c["unit_dist_ft"]
            B["split"] = asdict(sr)
            # The split test assigns each pool well to ONE unit (containing, else
            # nearest) — adjacent units can read "0" while sharing the same offsets
            # (VaULt 44-45 N2 vs S2). Report the SHARED count too: pool wells within
            # 1 mi of each unit, no exclusivity.
            shared = shared_offsets(eligible, units, 5280.0)
            for grp in B["split"]["groups"]:
                grp["n_within_1mi"] = shared.get(grp["unit"], 0)
            if metric == "eur_per_1000ft":
                B["split"]["notes"].append("metric = Novi 30-yr EUR/1,000 ft SCREEN (anduin fits unavailable)")

            # ---- TC groups ---------------------------------------------------------
            # One TC per cluster (split_test merges indistinguishable units and
            # attaches under-sampled units to the nearest cluster — borrowed).
            own = {g["unit"] for g in sr.groups if g["eligible"]}
            groups = []
            override = (tc_group_overrides or {}).get(bench)
            if bench in (tc_single or ()) and not override:
                override = [list(units)]                      # one group of every unit in the class
            if override:
                named = [u for grp in override for u in grp]
                unknown = sorted(set(named) - known_units)
                if unknown:
                    raise ValueError(f"--tc-groups {bench}: unknown unit(s) {unknown}; units are {sorted(known_units)}")
                # a reviewer group may name units outside this lateral class — keep the ones in it
                override = [[u for u in grp if u in units] for grp in override]
                override = [grp for grp in override if grp]
            if override:
                named = [u for grp in override for u in grp]
                rest = [u for u in units if u not in named]
                clusters = [list(grp) for grp in override] + ([rest] if rest else [])
                B["split"]["reviewer_override"] = {
                    "groups": clusters, "test_said": sr.recommendation,
                    "note": ("reviewer: ONE TC for this bench (gradient noted, no multiplier)" if bench in (tc_single or ())
                             and not (tc_group_overrides or {}).get(bench) else
                             "reviewer grouping replaces the split test for this bench"),
                }
                res["decision_log"].append({
                    "gate": "5b TC granularity", "bench": key,
                    "signal": f"{sr.recommendation} (ratio {_fmt(sr.median_ratio, '.2f')}, p {p_value(sr.p_value)})",
                    "decision": " | ".join(" + ".join(c) for c in clusters), "by": "reviewer",
                })
                for cl in clusters:
                    # A group covering every unit in the class takes the WHOLE pool — the
                    # per-well `unit` tags only exist when the split test ran (>= 2 units);
                    # a one-unit class + --tc-single left the cohort empty (VaULt 2026-09-28).
                    whole = set(cl) >= set(units)
                    small = [] if whole else [u for u in cl if u not in own]
                    groups.append({
                        "name": " + ".join(cl), "units": cl,
                        "pool": group_pool(eligible, cl, whole),
                        "dist_key": "dist_ft" if whole else "unit_dist_ft",
                        "note": ("reviewer: one TC for the class" if whole else "reviewer grouping") + (
                            f"; {', '.join(small)} below {cfg['split']['min_wells_per_group']} pool wells "
                            "(borrow this group's TC)" if small else ""),
                    })
            for cl in ([] if override else (sr.clusters or [list(units)])):
                borrowed = [u for u in cl if u not in own] if sr.recommendation == "split_by_polygon" else []
                multi = sr.recommendation == "split_by_polygon"
                groups.append({
                    "name": " + ".join(cl) if multi else "all units",
                    "units": cl,
                    "pool": [c for c in eligible if c.get("unit") in cl] if multi else eligible,
                    "dist_key": "unit_dist_ft" if multi else "dist_ft",
                    "note": (f"{', '.join(borrowed)}: below {cfg['split']['min_wells_per_group']} pool wells — "
                             "borrows this group's TC (document a multiplier if the reviewer sees a difference)")
                            if borrowed else None,
                })
            if tier_scope == "unit":
                by_scn: list[dict[str, Any]] = []
                for g in groups:
                    scns = scenario_groups(g["units"], existing_by_unit)
                    for sc in scns:
                        g_order, _ = tier_order(cfg, adjacent, sc["flip"])
                        label = ("infill under/over " + ", ".join(sc["existing"])) if sc["flip"] else "greenfield"
                        by_scn.append({
                            **g, "units": sc["units"], "scenario": sc["scenario"], "existing": sc["existing"],
                            "name": g["name"] if len(scns) == 1 else (
                                (g["name"] if g["name"] != "all units" else bench) + f" — {label}"),
                            # re-tier THIS group's pool against its own units' in-band benches
                            "pool": [{**c, "tier": codev_tier(c, adjacent, sc["existing"])} for c in g["pool"]],
                            "order": g_order,
                            "order_reason": (f"{sc['scenario']}: {len(sc['units'])} unit(s) "
                                             + (f"with producers in {', '.join(sc['existing'])} within {band:,.0f} ft"
                                                if sc["flip"] else f"with no producer within {band:,.0f} ft")
                                             + f" -> {g_order[0]} first"),
                        })
                        res["decision_log"].append({
                            "gate": "5.2b tier order", "bench": key,
                            "signal": f"{', '.join(sc['units'])}: " + (f"in-band producers {', '.join(sc['existing'])}"
                                                                      if sc["flip"] else "no in-band producer"),
                            "decision": f"{sc['scenario']} cohort, {' > '.join(g_order)}", "by": "rule (per unit)",
                        })
                groups = by_scn
            if tier_scope == "none":
                # Scenario tag = the WELL'S OWN history (any unshielded vertical parent),
                # for the tier table only — it no longer depends on our units.
                groups = [{**g, "tier_blind": True,
                           "pool": [{**c, "tier": codev_tier(c, adjacent, sorted(vertical_parents(c)))} for c in g["pool"]]}
                          for g in groups]
            B["tc_groups"] = []
            for g in groups:
                sel = fill(g["pool"], cfg, bench=bench, adjacent=adjacent, order=g.get("order", order),
                           order_reason=g.get("order_reason", order_reason), dist_key=g["dist_key"],
                           tier_blind=g.get("tier_blind", False))
                G: dict[str, Any] = {
                    "name": g["name"], "units": g["units"], "note": g.get("note"),
                    "scenario": g.get("scenario"), "existing_benches": g.get("existing"),
                    "tier_order": sel.tier_order, "order_reason": sel.order_reason,
                    "tier_counts": sel.tier_counts(), "tier_medians_novi_eur_per_1000ft": tier_medians(sel),
                    "flags": sel.flags, "tc_wells": sel.selected,
                }
                G["lateral_support"], ls_flags = lateral_support(
                    sel.selected, {u: ll_by_unit[u] for u in g["units"]}, cfg, basin)
                G["flags"] = list(G["flags"]) + ls_flags
                G["standoff"] = {"cohort": cohort_standoff(sel.selected),
                                 "units": {u: B["units"][u].get("standoff") for u in g["units"]}}
                G["flags"] += standoff_flags(G["standoff"]["units"], G["standoff"]["cohort"])
                api10s = [c["api10"] for c in sel.selected]
                if ad and api10s:
                    rows = [r for r in rows_all if r["api10"] in set(api10s)]
                    qc = cohort_qc.run(rows, cfg)
                    G["qc"] = {"streams": {k: asdict(v) for k, v in qc.streams.items()}, "well_flags": qc.well_flags}
                    G["anduin_oil"] = {
                        r["api10"]: {k: r.get(k) for k in ("di_initial", "b", "di_effective", "peak_index_months",
                                                          "fit_at_bound", "eur", "well_lateral_ft")}
                        for r in rows if r["stream"] == "oil"
                    }
                    tc = ad.compute_type_curve(api10s)
                    G["tc_preview"] = {st: v.get("fitted") for st, v in (tc.get("streams") or {}).items()}
                    G["tc_preview_n_wells"] = tc.get("n_wells")
                    # Side-by-side gas: same cohort, gas as ratio-to-cum-oil on
                    # this TC's oil curve (Michael, 2026-09-21 — evaluate on a
                    # few deals before choosing a default; Arps stays default).
                    tcr = ad.compute_type_curve(api10s, stream_modes={"gas": "ratio"})
                    gr = ((tcr.get("streams") or {}).get("gas") or {}).get("fitted") or {}
                    G["tc_preview_gas_ratio"] = {
                        k: gr.get(k) for k in ("mode", "sub_mode", "alpha", "beta", "r2", "n_months",
                                               "r_const", "eur_per_unit", "implied_effective_decline_yr1")
                    } if gr else None
                ids = sorted({i for u in g["units"] for i in B["units"][u]["novi_ids"]})
                G["novi"] = _novi_summary(wh.novi_params(conn, ids))
                G["novi"]["n_sticks"] = len(ids)
                # Gas basis = anduin (Michael 2026-09-28); any stream where Novi and the
                # TC disagree by more than stream_gap_flag_ratio is called out, not buried.
                gap = float(cfg["qc_flags"].get("stream_gap_flag_ratio", 1.5))
                G["novi_vs_tc"] = {}
                for st in ("oil", "gas"):
                    nv_eur = (G["novi"].get(st) or {}).get("eur_per_1000ft")
                    tc_eur = ((G.get("tc_preview") or {}).get(st) or {}).get("eur_per_unit")
                    if nv_eur and tc_eur:
                        ratio = nv_eur / tc_eur
                        G["novi_vs_tc"][st] = round(ratio, 2)
                        if ratio > gap or ratio < 1 / gap:
                            G["flags"].append(f"{st}: Novi EUR is {ratio:.1f}x the anduin TC ({nv_eur:,.0f} vs {tc_eur:,.0f} per 1,000 ft) "
                                              f"— beyond the {gap:g}x gap flag; anduin is the basis, reviewer decides")
                B["tc_groups"].append(G)
            B["eligible_pool"] = eligible
            if ad and B.get("short_history_transfer", {}).get("written"):
                B["transfer_compare"] = _compare_without_transfer(
                    ad, B, eligible, short_history_transfer)
    write_json(run_dir / "signals.json", res)
    return res


def _compare_without_transfer(
    ad: Anduin, B: dict[str, Any], eligible: list[dict[str, Any]], cutoff: int
) -> dict[str, Any]:
    """With/without short-history transfer, per TC group (Michael, 2026-09-21).

    The transfer OVERWRITES the short wells' own fits in anduin, so the
    'without' TC needs them back. Sequence (anduin ends in the default,
    transferred state):
      1. refit ONLY the transferred wells that sit in a TC cohort (own fits),
      2. compute each affected group's TC preview -> G['tc_preview_no_transfer'],
      3. re-run the transfer on the same bench pool. Lenders are untouched, so
         the donor medians must reproduce; a mismatch is recorded as a flag.
    Groups with no transferred wells get no comparison (identical by
    construction).
    """
    written = set(B["short_history_transfer"]["written"])
    in_cohorts = sorted({c["api10"] for G in B["tc_groups"] for c in G["tc_wells"] if c["api10"] in written})
    out: dict[str, Any] = {"refit_wells": in_cohorts, "groups": {}}
    if not in_cohorts:
        out["note"] = "no transferred wells in any TC cohort — with/without identical"
        return out
    before = {(d["stream"], round(d["cohort_di"], 6), round(d["cohort_b"], 6))
              for d in B["short_history_transfer"].get("donors", [])}
    try:
        ad.forecast(in_cohorts, only_missing=False)            # 1. own fits back
        for G in B["tc_groups"]:
            api10s = [c["api10"] for c in G["tc_wells"]]
            shorts = [a for a in api10s if a in written]
            if not shorts:
                continue
            tc = ad.compute_type_curve(api10s)                     # 2. without
            G["tc_preview_no_transfer"] = {st: v.get("fitted") for st, v in (tc.get("streams") or {}).items()}
            G["n_transferred_in_cohort"] = len(shorts)
            out["groups"][G["name"]] = shorts
    finally:
        again = _transfer(ad, eligible, cutoff)                    # 3. restore default
        after = {(d["stream"], round(d["cohort_di"], 6), round(d["cohort_b"], 6))
                 for d in again.get("donors", [])}
        out["restored"] = "error" not in again
        if again.get("error") or before != after:
            out["flag"] = ("transfer re-run did not reproduce the donor medians — anduin may NOT be in the "
                           f"default state: {again.get('error') or 'medians changed'}")
    return out


VINTAGE_GAP_FLAG_YEARS = 3  # lenders this much older than the short wells -> flag


def _transfer(ad: Anduin, eligible: list[dict[str, Any]], cutoff: int) -> dict[str, Any]:
    """Run anduin's short-history cohort transfer on the bench's eligible POOL
    (widest same-bench lender set, not the 20-well cohort) and summarize who
    lent and who was rewritten. Lender vs short vintage + proppant/ft are
    compared: long wells are older by construction, and in emerging benches an
    earlier completion generation can decline differently."""
    api10s = [c["api10"] for c in eligible]
    try:
        r = ad.transfer_cohort(api10s, cutoff)
    except AnduinError as e:
        return {"cutoff_months": cutoff, "error": str(e),
                "flag": "transfer NOT applied (see error) — short wells keep their own fits"}
    by = {c["api10"]: c for c in eligible}

    def med(ids: list[str], key: str) -> float | None:
        vals = [by[a][key] for a in ids if a in by and by[a].get(key) is not None]
        if key == "first_production_date":
            vals = [v.year + (v.month - 1) / 12 for v in vals]
        return round(statistics.median(vals), 1) if vals else None

    long_ids, short_ids = list(r.get("long_api10s") or []), list(r.get("short_api10s") or [])
    out = {
        "cutoff_months": cutoff,
        "n_long": len(long_ids), "n_short": len(short_ids),
        "written": list(r.get("written_api10s") or []),
        "skipped_locked": r.get("skipped_locked") or [],
        "skipped_no_peak": r.get("skipped_no_peak") or [],
        "donors": r.get("donors") or [],
        "long_fp_year_median": med(long_ids, "first_production_date"),
        "short_fp_year_median": med(short_ids, "first_production_date"),
        "long_proppant_lbs_ft_median": med(long_ids, "proppant_lbs_per_ft"),
        "short_proppant_lbs_ft_median": med(short_ids, "proppant_lbs_per_ft"),
    }
    ly, sy = out["long_fp_year_median"], out["short_fp_year_median"]
    if ly and sy and sy - ly >= VINTAGE_GAP_FLAG_YEARS:
        out["flag"] = (f"lenders median first prod {ly:.0f} vs short wells {sy:.0f} "
                       f"({sy - ly:.1f} yr gap): borrowed Di/b may reflect an older completion design")
    return out


NOVI_SEG1_DI_CAP = 3.65  # /yr (0.01/day) — Novi's segment-1 Di cap (see warehouse.novi_params)


def _novi_summary(params: list[dict[str, Any]]) -> dict[str, Any]:
    """Per stream MEDIAN over the representative Novi sticks. Segment 1 (days
    0-540) gives b, nominal Di, 1-yr effective (house formula), qi per 1,000
    ft; segment 2 Di beside it; the share of sticks pinned at Novi's 3.65/yr
    segment-1 cap is reported so a capped "Di" is never read as a fit. A median
    of sticks — NOT a P50, and not the erebor export's cohort mean."""
    out: dict[str, Any] = {}
    for stream in ("oil", "gas", "water"):
        s1 = [r for r in params if r["stream"] == stream and r["segment"] == 1 and r.get("ll_ft")]
        s2 = [r for r in params if r["stream"] == stream and r["segment"] == 2]
        if not s1:
            continue
        eur_key = {"oil": "oil_eur", "gas": "gas_eur"}.get(stream)
        fit = [r for r in s1 if r["d_nom"] is not None and r["b"] is not None]
        out[stream] = {
            "n": len(s1),
            "b": _median([r["b"] for r in s1]),
            "di_nominal": _median([r["d_nom"] for r in s1]),
            "di_effective": _median([effective_from_nominal(r["d_nom"], r["b"]) for r in fit]),
            "seg1_at_cap_frac": (sum(1 for r in fit if round(r["d_nom"], 2) == NOVI_SEG1_DI_CAP) / len(fit)) if fit else None,
            "seg1_days": _median([r["day_stop"] for r in s1]),
            "seg2_di_nominal": _median([r["d_nom"] for r in s2]),
            "seg2_b": _median([r["b"] for r in s2]),
            "qi_per_1000ft": _median([r["q_start"] / float(r["ll_ft"]) * 1000 for r in s1 if r.get("q_start")]),
            "eur_per_1000ft": _median([float(r[eur_key]) / float(r["ll_ft"]) * 1000 for r in s1
                                       if eur_key and r.get(eur_key)]) if eur_key else None,
        }
    return out
