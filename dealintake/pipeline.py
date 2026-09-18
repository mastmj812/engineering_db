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
TC and the narvi scenario stay reviewer actions.
"""

from __future__ import annotations

import json
import statistics
from collections import Counter
from dataclasses import asdict, is_dataclass
from datetime import date, datetime
from pathlib import Path
from typing import Any

from shapely.geometry import mapping, shape
from shapely.ops import unary_union

from dealintake import benches as benchmod
from dealintake import cohort_qc, split_test
from dealintake import warehouse as wh
from dealintake.clients.anduin import Anduin, AnduinError
from dealintake.clients.narvi import Narvi, legs
from dealintake.config import Config
from dealintake.decline import effective_from_nominal
from dealintake.geo import long_axis_azimuth, planned_lateral, stick_relation
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

    out: dict[str, Any] = {
        "deal_file": str(deal_path),
        "config_version": cfg.version,
        "config_path": str(cfg.path),
        "correlated_window": correlated_window,
        "window_basis": window_basis,
        "units": [],
    }
    tol = float(cfg["alignment"]["stick_inside_tolerance_ft"])
    with wh.connect() as conn:
        out["snapshot"] = wh.snapshot(conn)
        for pc in parcels:
            u = pc["geom"]
            if u.geom_type == "MultiPolygon":
                # Gate 1: multipolygon units are split and reported, never merged silently.
                parts = sorted(u.geoms, key=lambda g: -g.area)
                out.setdefault("warnings", []).append(
                    f"{pc['label']}: MultiPolygon with {len(parts)} parts — using the largest; split the unit in the land file"
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
            dmin, dmax, draw = benchmod.declared_window(pc["attributes"])
            window = correlated_window or ((dmin, dmax) if (dmin is not None or dmax is not None) else None)
            local = wh.local_benches(conn, u)
            zones = narvi.zones(u, [b["bench"] for b in local]) if local else {"stats": []}
            proposal = benchmod.propose(zones.get("stats", []), window, float(cfg["depth"]["edge_margin_ft"]))

            sticks = wh.novi_sticks(conn, u)
            rel: dict[str, Counter] = {}
            for s in sticks:
                s["relation"] = stick_relation(s["geom"], u, tol)
                rel.setdefault(s["formation_blueox"] or "(unmapped)", Counter())[(s["category"], s["relation"])] += 1
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
                "declared_window_raw": draw,
                "declared_window": [dmin, dmax],
                "window_used": list(window) if window else None,
                "window_source": "correlated" if correlated_window else ("declared (NOT local — correlate)" if window else None),
                "planned_lateral": pl.as_dict(),
                "bench_proposal": proposal,
                "gate2": gate2,
                "pad_iou_advisory": wh.pad_iou(conn, u),
                "pdp_in_unit": wh.pdp_in_unit(conn, u),
            })
    write_json(run_dir / "proposal.json", out)
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


def evaluate(
    run_dir: Path,
    cfg: Config,
    *,
    benches: list[str],
    spacing_ft: dict[str, float] | None = None,
    use_anduin: bool = True,
    narvi: Narvi | None = None,
    anduin: Anduin | None = None,
) -> dict[str, Any]:
    prop = json.loads((run_dir / "proposal.json").read_text(encoding="utf-8"))
    narvi = narvi or Narvi()
    spacing_ft = spacing_ft or {}
    units = {u["label"]: shape(u["geometry"]) for u in prop["units"]}
    union = unary_union(list(units.values()))
    benches = [bench_code(b) for b in benches]

    # Planned stack order (shallow -> deep) from the units' local bench medians.
    tvd_by_bench: dict[str, list[float]] = {}
    for u in prop["units"]:
        for r in u["bench_proposal"]:
            if r["median_tvd_ft"] is not None:
                tvd_by_bench.setdefault(bench_code(r["bench"]), []).append(r["median_tvd_ft"])
    missing = [b for b in benches if b not in tvd_by_bench]
    if missing:
        raise ValueError(f"no local median TVD for {missing} — not in any unit's bench proposal")
    stack = sorted(benches, key=lambda b: statistics.median(tvd_by_bench[b]))
    bench_tvd = {b: statistics.median(tvd_by_bench[b]) for b in stack}

    planned_ll = _median([u["planned_lateral"]["median_ft"] for u in prop["units"]]) or 0.0
    lls = [u["planned_lateral"]["median_ft"] for u in prop["units"]]
    res: dict[str, Any] = {
        "run_dir": str(run_dir), "config_version": cfg.version, "snapshot": prop["snapshot"],
        "planned_stack": stack, "bench_tvd_ft": bench_tvd, "planned_lateral_ft": planned_ll,
        "flags": [], "benches": {}, "decision_log": [],
    }
    if lls and min(lls) > 0 and max(lls) / min(lls) > 1.25:
        res["flags"].append(f"unit planned laterals differ >25% ({min(lls):,.0f}-{max(lls):,.0f} ft): consider per-unit TC bands")

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

    with wh.connect() as conn:
        for bench in stack:
            B: dict[str, Any] = {"bench": bench, "units": {}, "tvd_ft": bench_tvd[bench]}
            res["benches"][bench] = B
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
            for radius in RADIUS_STEPS_MI:
                cands = cands0 if radius == RADIUS_STEPS_MI[0] else wh.candidates(conn, union, bench, radius)
                eligible, excluded, adjacent = classify(
                    cands, cfg, bench=bench, planned_stack=stack, planned_lateral_ft=planned_ll,
                    basin=basin, planned_spacing_ft=sp,
                )
                if len(eligible) >= min_wells or edge:
                    break
            pool_flags.append(f"radius {radius} mi, basin {basin}, lateral tol {tol:.0%}, eligible pool {len(eligible)}")
            if edge and len(eligible) < min_wells:
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
            for cl in (sr.clusters or [list(units)]):
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
                ids = sorted({i for u in g["units"] for i in B["units"][u]["novi_ids"]})
                G["novi"] = _novi_summary(wh.novi_params(conn, ids))
                G["novi"]["n_sticks"] = len(ids)
                B["tc_groups"].append(G)
            B["eligible_pool"] = eligible
    write_json(run_dir / "signals.json", res)
    return res


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
