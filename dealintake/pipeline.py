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
from pathlib import Path
from typing import Any

from shapely.geometry import mapping, shape
from shapely.ops import unary_union

from dealintake import benches as benchmod
from dealintake import cohort_qc, split_test, strat, unit_benches
from dealintake import warehouse as wh
from dealintake.clients.anduin import Anduin, AnduinError
from dealintake.clients.narvi import Narvi, legs
from dealintake.config import Config
from dealintake.decline import effective_from_nominal
from dealintake.geo import long_axis_azimuth, planned_lateral, stick_relation
from dealintake.render.tables import p_value
from dealintake.select_wells import (
    adjacent_benches,
    bench_code,
    classify,
    fill,
    tier_medians,
    tier_order,
)

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
            az = narvi.azimuth(u)
            if az.get("confident") and az.get("azimuth_deg") is not None:
                az_deg, az_src = float(az["azimuth_deg"]), f"neighborhood grid (R {az.get('coherence')})"
            else:
                az_deg, az_src = long_axis_azimuth(u), "unit long axis"
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
            bench_seed = unit_benches.seed_unit(dsu_name, lo, hi, proposal, col, basin)

            sticks = wh.novi_sticks(conn, u)
            rel: dict[str, Counter] = {}
            for s in sticks:
                s["relation"] = stick_relation(s["geom"], u, tol)
                rel.setdefault(s["formation_blueox"] or "(unmapped)", Counter())[(s["category"], s["relation"])] += 1
            # Review-page layers (display only): Novi sticks near the unit + offset PDP laterals.
            review_geoms[pc["label"]] = {
                "novi": [{"stick_id": s["stick_id"], "bench": s["formation_blueox"] or "(unmapped)",
                          "category": s["category"], "relation": s["relation"], "wkt": s["geom"].wkt} for s in sticks],
                "pdp": wh.pdp_laterals_near(conn, u),
            }
            gate2 = {}
            for b, c in sorted(rel.items()):
                pud_in, pud_x = c[("PUD", "inside")], c[("PUD", "crossing")]
                gate2[b] = {
                    "pud_inside": pud_in, "pud_crossing": pud_x,
                    "res_inside": c[("RES", "inside")], "res_crossing": c[("RES", "crossing")],
                    "source": "novi" if pud_in > 0 and pud_x == 0 else "generate",
                    "reason": ("all BASE_CASE sticks inside" if pud_in > 0 and pud_x == 0
                               else f"{pud_x} BASE_CASE stick(s) cross the unit line" if pud_x
                               else "no BASE_CASE stick inside"),
                }
            out["units"].append({
                "label": pc["label"],
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
                "offset_pdp_3mi": {b["bench"]: int(b["n_wells"]) for b in local},
                "planned_lateral": pl.as_dict(),
                "bench_proposal": proposal,
                "gate2": gate2,
                "pad_iou_advisory": wh.pad_iou(conn, u),
                "pdp_in_unit": wh.pdp_in_unit(conn, u),
            })
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
    narvi: Narvi | None = None,
    anduin: Anduin | None = None,
) -> dict[str, Any]:
    """radius_overrides: {bench: miles} — REVIEWER decision: the eligible pool
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
                             "seed_benches": deal_wide, "edited": False} for u in prop["units"]}
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
        for r in u["bench_proposal"]:
            b = bench_code(r["bench"])
            if r["median_tvd_ft"] is not None and b in plan[u["label"]]["benches"]:
                tvd_by_bench.setdefault(b, []).append(r["median_tvd_ft"])
    missing = [b for b in benches if b not in tvd_by_bench]
    if missing:
        raise ValueError(f"no local median TVD for {missing} in the units that enable them ({plan_source})")
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
    res: dict[str, Any] = {
        "run_dir": str(run_dir), "config_version": cfg.version, "snapshot": prop["snapshot"],
        "planned_stack": stack, "bench_tvd_ft": bench_tvd,
        "planned_lateral_ft": _median(list(ll_by_unit.values())) or 0.0,
        "lateral_classes": [{"units": c, "planned_lateral_ft": _median([ll_by_unit[u] for u in c])}
                            for c in lateral_classes(ll_by_unit, class_ratio)],
        "unit_plan": plan, "plan_source": plan_source,
        "flags": [], "benches": {}, "decision_log": [],
    }
    if len(res["lateral_classes"]) > 1:
        res["flags"].append(
            "planned laterals fall into " + str(len(res["lateral_classes"])) + " classes ("
            + ", ".join(f"{c['planned_lateral_ft']:,.0f} ft x{len(c['units'])}" for c in res["lateral_classes"])
            + f"; units within {class_ratio - 1:.0%} share a class): each bench is pooled, split-tested and "
              "type-curved PER CLASS, with the lateral band centered on the class")
    for lb, p in plan.items():
        res["decision_log"].append({
            "gate": "1 unit benches + lateral", "bench": lb,
            "signal": f"seed: {', '.join(p['seed_benches']) or 'none'}",
            "decision": (f"{', '.join(p['benches']) or 'NOT EVALUATED'}; planned lateral {p['planned_lateral_ft']:,.0f} ft"
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
        classes = lateral_classes(ll_b, class_ratio)
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
            sp = float(spacing_ft.get(bench, DEFAULT_SPACING_FT))
            B["spacing_ft"] = sp
            B["spacing_source"] = "reviewer" if bench in spacing_ft else f"default {DEFAULT_SPACING_FT:.0f} ft (narvi fallback)"
            support_all: list[dict[str, Any]] = []
            adj = adjacent_benches(bench, stack)
            # Basin (per-basin lateral tolerance, ledger §9) = majority basin of the
            # in-bench producers within the first selection radius.
            cands0 = wh.candidates(conn, union, bench, RADIUS_STEPS_MI[0])
            bc = Counter(c["basin"] for c in cands0 if c["basin"]).most_common(1)
            basin = bc[0][0] if bc else None
            B["basin"] = basin
            tol = cfg.lateral_tolerance(basin)

            for u in prop["units"]:
                if u["label"] not in units:
                    continue
                label, geom = u["label"], units[u["label"]]
                # Landing TVD = THIS unit's local offset median (units can sit
                # >1,000 ft apart structurally — Toucan WCA_1 9,735 vs 10,852 ft);
                # the cross-unit median only orders the stack / is the fallback.
                local_tvd = next((r["median_tvd_ft"] for r in u["bench_proposal"]
                                  if bench_code(r["bench"]) == bench and r["median_tvd_ft"] is not None), None)
                tvd_u = float(local_tvd if local_tvd is not None else bench_tvd[bench])
                g2 = u["gate2"].get(bench) or {"source": "generate", "reason": "no Novi sticks in bench",
                                               "pud_inside": 0, "pud_crossing": 0}
                unit_novi: list[int] = []
                UB: dict[str, Any] = {"gate2": g2, "tvd_ft": tvd_u,
                                      "tvd_source": "unit local median" if local_tvd is not None else "cross-unit median (no local control)"}
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
                    gen = narvi.generate(
                        geom, [{"formation": bench, "target_tvd_ft": tvd_u, "spacing_ft": sp}],
                        setback_ft=float(cfg["planned_lateral"]["setback_ft"]), spacing_ft=sp,
                        azimuth_deg=u["planned_lateral"]["azimuth_deg"],
                    )
                    lg = legs(gen)
                    UB["locations"] = [{"id": f"gen-{i}", "src": "narvi_preview",
                                        "ll_ft": leg.get("completed_lateral_ft"), "tvd": tvd_u,
                                        "wkt": leg["geom"].wkt} for i, leg in enumerate(lg)]
                    sup = [wh.pdp_support(conn, leg["geom"], bench, tvd_u) for leg in lg]
                    for leg in lg:
                        unit_novi += wh.representative_sticks(
                            conn, leg["geom"], bench, float(leg.get("completed_lateral_ft") or planned_ll), tol)
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
            pdp_adj_units = [lb for lb, ub in B["units"].items() if ub["has_pdp_in_adjacent_bench"]]
            # Tier-order flip by STRICT MAJORITY of units (Michael, 2026-09-18); tie -> default.
            flip = len(pdp_adj_units) * 2 > len(B["units"])
            min_wells = int(cfg["type_curve"]["min_wells"])
            pool_flags: list[str] = []
            r_over = radius_overrides.get(bench)
            radius, eligible, excluded, adjacent = _select_pool(
                lambda r, _b=bench, _c=cands0, _un=union: (
                    _c if r == RADIUS_STEPS_MI[0] else wh.candidates(conn, _un, _b, r)),
                lambda cands, _b=bench, _bn=basin, _sp=sp, _ll=planned_ll: classify(
                    cands, cfg, bench=_b, planned_stack=stack, planned_lateral_ft=_ll,
                    basin=_bn, planned_spacing_ft=_sp),
                min_wells=min_wells, edge=edge, radius_override=r_over,
            )
            pool_flags.append(f"radius {radius} mi{' (REVIEWER override)' if r_over is not None else ''}, "
                              f"basin {basin}, lateral tol {tol:.0%}, eligible pool {len(eligible)}")
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
            if pdp_adj_units and len(pdp_adj_units) < len(B["units"]):
                pool_flags.append(
                    f"adjacent-bench PDP in {len(pdp_adj_units)}/{len(B['units'])} units "
                    f"({', '.join(pdp_adj_units)}): {'majority -> order flipped' if flip else 'no majority -> default order'}")
            order, order_reason = tier_order(cfg, adjacent, flip)
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

            # ---- Gate 5b: split test on the POOL, before any cohort is filled -----
            sr = split_test.run(eligible, units, cfg, metric=metric)   # tags c["unit"], c["unit_dist_ft"]
            B["split"] = asdict(sr)
            if metric == "eur_per_1000ft":
                B["split"]["notes"].append("metric = Novi 30-yr EUR/1,000 ft SCREEN (anduin fits unavailable)")

            # ---- TC groups ---------------------------------------------------------
            # One TC per cluster (split_test merges indistinguishable units and
            # attaches under-sampled units to the nearest cluster — borrowed).
            own = {g["unit"] for g in sr.groups if g["eligible"]}
            groups = []
            override = (tc_group_overrides or {}).get(bench)
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
                    "note": "reviewer grouping replaces the split test for this bench",
                }
                res["decision_log"].append({
                    "gate": "5b TC granularity", "bench": key,
                    "signal": f"{sr.recommendation} (ratio {_fmt(sr.median_ratio, '.2f')}, p {p_value(sr.p_value)})",
                    "decision": " | ".join(" + ".join(c) for c in clusters), "by": "reviewer",
                })
                for cl in clusters:
                    small = [u for u in cl if u not in own]
                    groups.append({
                        "name": " + ".join(cl), "units": cl,
                        "pool": [c for c in eligible if c.get("unit") in cl],
                        "dist_key": "unit_dist_ft",
                        "note": "reviewer grouping" + (
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
            B["tc_groups"] = []
            for g in groups:
                sel = fill(g["pool"], cfg, bench=bench, adjacent=adjacent, order=order,
                           order_reason=order_reason, dist_key=g["dist_key"])
                G: dict[str, Any] = {
                    "name": g["name"], "units": g["units"], "note": g.get("note"),
                    "tier_counts": sel.tier_counts(), "tier_medians_novi_eur_per_1000ft": tier_medians(sel),
                    "flags": sel.flags, "tc_wells": sel.selected,
                }
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
