"""Markdown + CSV tables for the dossier. Di always nominal AND effective."""

from __future__ import annotations

import csv
from pathlib import Path
from typing import Any

from dealintake.decline import effective_from_nominal


def md(headers: list[str], rows: list[list[Any]]) -> str:
    def cell(v: Any) -> str:
        if v is None:
            return "—"
        if isinstance(v, float):
            return f"{v:,.2f}" if abs(v) < 100 else f"{v:,.0f}"
        return str(v).replace("|", "\\|")

    out = ["| " + " | ".join(headers) + " |", "|" + "---|" * len(headers)]
    out += ["| " + " | ".join(cell(v) for v in r) + " |" for r in rows]
    return "\n".join(out)


def pct(v: float | None) -> str:
    return "—" if v is None else f"{v * 100:.1f}%"


def num(v: float | None, spec: str = ",.2f") -> str:
    return "—" if v is None else format(v, spec)


def p_value(p: float | None) -> str:
    """3 significant figures; tiny values as '<0.0001' (never 0.002373333787193668)."""
    if p is None:
        return "—"
    return "<0.0001" if p < 1e-4 else f"{p:.3g}"


def di_pair(di_nom: float | None, b: float | None) -> tuple[str, str]:
    if di_nom is None or b is None:
        return "—", "—"
    return f"{di_nom:.2f}", pct(effective_from_nominal(float(di_nom), float(b)))


BUILDUP_COLS = [
    "api10", "well_name", "operator", "first_production_date", "lateral_length_ft", "bench", "tvd_ft",
    "standoff_ft", "standoff_ref_tvd_ft", "spacing_class",
    "tier", "scenario_class", "months_produced", "eur_per_1000ft", "anduin_oil_eur_per_1000ft",
    "proppant_lbs_per_ft", "dist_ft", "codev_benches", "parent_benches_below", "parent_benches_above",
    "child_benches",
]


def buildup_rows(wells: list[dict[str, Any]], qc_rows: dict[str, dict[str, Any]] | None = None) -> list[list[Any]]:
    """One row per TC well. qc_rows: api10 -> anduin oil forecast row (Di/b/peak)."""
    out = []
    for w in wells:
        f = (qc_rows or {}).get(w["api10"], {})
        di_n, di_e = di_pair(f.get("di_initial"), f.get("b"))
        out.append([
            w["api10"], w.get("well_name"), w.get("operator"), w.get("first_production_date"), w.get("lateral_length_ft"),
            w.get("bench"), w.get("tvd_ft"),
            None if w.get("standoff_ft") is None else round(w["standoff_ft"]), w.get("spacing_class"), w.get("tier"), w.get("scenario_class"), w.get("months_produced"),
            w.get("eur_per_1000ft"), w.get("anduin_oil_eur_per_1000ft"), di_n, di_e,
            f.get("b"), f.get("peak_index_months"), w.get("proppant_lbs_per_ft"),
        ])
    return out


BUILDUP_HEADERS = [
    "api10", "Well", "Operator", "First prod", "Lateral ft", "Bench", "TVD ft", "Below ref ft", "Spacing", "Codev tier", "Scenario", "Months",
    "Novi EUR/1,000 ft (screen)", "anduin oil EUR/1,000 ft", "Di nom /yr", "Di eff yr-1", "b",
    "Peak mo", "Proppant lb/ft",
]


def write_csv(path: Path, wells: list[dict[str, Any]], cols: list[str] = BUILDUP_COLS) -> None:
    with path.open("w", newline="", encoding="utf-8") as fh:
        w = csv.writer(fh)
        w.writerow(cols)
        for r in wells:
            w.writerow([";".join(r[c]) if isinstance(r.get(c), list) else r.get(c) for c in cols])


NORMALIZE_INTRO = (
    "PROTOTYPE, report-only (config v17) — BOX's own definitions read on this bench; the curve, cohort and handoff above "
    "are unchanged. Factor = D150 proximity factor (level × F_rule): the stick's from every producer ≥ 12 months on at "
    "the data date, an analog's from the producers ≥ 12 months on at its own first production. Cui = Cui & Cross "
    "lateral efficiency of the unit vs the cohort's laterals (D50). A = the curve of record × (stick factor ÷ mean "
    "analog factor) × Cui. B = the nearest wells of the pool rule WITHOUT its scenario selection, analogs 5,000–15,000 ft "
    "(BOX's window, translated not band-filtered), same ratio + Cui; B per well = the same translation done well by well "
    "(median). EUR = raw 50-yr oil per 1,000 ft.")
NORMALIZE_HEADERS = ["DSU", "Sticks", "Stick factor (range)", "Parents / stick", "Curve of record /1,000 ft",
                     "A: cohort factor", "A: ratio", "A: Cui", "A: EUR /1,000 ft", "B: TC /1,000 ft", "B: cohort factor",
                     "B: ratio", "B: Cui", "B: EUR /1,000 ft", "B per well /1,000 ft"]
NORMALIZE_COHORT_HEADERS = ["api10", "Well", "Operator", "Tag", "Scenario", "Distance mi", "Lateral ft", "Below ref ft",
                            "anduin oil EUR /1,000 ft", "Parents", "Factor", "Pattern"]


def normalize_rows(nz: dict[str, Any], name: dict[str, str] | None = None) -> tuple[list[list[Any]], list[list[Any]]]:
    """(per-unit readings, cohort B wells) for the v17 prototype section."""
    name = name or {}

    def f(v: Any, spec: str) -> str:
        return "—" if v is None else format(v, spec)

    units = []
    for u, r in (nz.get("units") or {}).items():
        a, b = r.get("A") or {}, r.get("B") or {}
        rng = r.get("stick_factor_range")
        npar = r.get("n_parents") or []
        units.append([name.get(u, u), r["n_sticks"],
                      f"{f(r.get('stick_factor'), '.3f')} ({rng[0]:.3f}–{rng[1]:.3f})" if rng else "—",
                      f"{min(npar)}–{max(npar)}" if npar else "—", f(r.get("tc_a_oil_eur_per_1000ft"), ",.0f"),
                      f(a.get("mean_analog_factor"), ".3f"), f(a.get("ratio"), ".3f"), f(a.get("cui"), ".3f"),
                      f(a.get("eur_per_1000ft"), ",.0f") + (f" ({a['vs_tc']:+.1%})" if a.get("vs_tc") is not None else ""),
                      f(nz.get("tc_b_oil_eur_per_1000ft"), ",.0f"), f(b.get("mean_analog_factor"), ".3f"),
                      f(b.get("ratio"), ".3f"), f(b.get("cui"), ".3f"),
                      f(b.get("eur_per_1000ft"), ",.0f"), f(r.get("B_per_well"), ",.0f")])
    wells = [[w["api10"], w.get("well_name"), w.get("operator"), w.get("bench"), w.get("scenario_class"),
              f(w.get("dist_mi"), ".1f"), f(w.get("lateral_length_ft"), ",.0f"), f(w.get("standoff_ft"), ",.0f"),
              f(w.get("anduin_oil_eur_per_1000ft"), ",.0f"), f(w.get("n_parents"), ".0f"), f(w.get("factor"), ".3f"),
              w.get("pattern") or "—"] for w in nz.get("cohort_b") or []]
    return units, wells


COHORT_HEADERS = ["Well", "Operator", "api10", "First prod", "Lateral ft", "Nearest unit", "Distance mi",
                  "anduin oil EUR/1,000 ft", "Came on"]


def cohort_rows(wells: list[dict[str, Any]], names: dict[str, str]) -> list[list[Any]]:
    """The wells that BUILD one curve, nearest first — what the reviewer reads to
    judge the cohort (full detail stays in the buildup table / CSV)."""
    def dist(w: dict[str, Any]) -> float | None:
        d = w.get("unit_dist_ft") if w.get("unit_dist_ft") is not None else w.get("dist_ft")
        return None if d is None else float(d)

    def came_on(w: dict[str, Any]) -> str:
        par = sorted(set((w.get("parent_benches_below") or []) + (w.get("parent_benches_above") or [])))
        if w.get("tier") == "topfill_underfill" and par:
            return "over/under " + ", ".join(par)
        co = [b for b in (w.get("codev_benches") or []) if b != w.get("bench")]
        return ("co-developed with " + ", ".join(sorted(set(co)))) if co else "alone"

    out = []
    for w in sorted(wells, key=lambda w: (dist(w) is None, dist(w) or 0.0)):
        d = dist(w)
        out.append([w.get("well_name") or "—", w.get("operator"), w["api10"], str(w.get("first_production_date") or "")[:7],
                    num(w.get("lateral_length_ft"), ",.0f"), names.get(w.get("unit"), w.get("unit") or "—"),
                    "—" if d is None else f"{d / 5280.0:.1f}", num(w.get("anduin_oil_eur_per_1000ft"), ",.0f"), came_on(w)])
    return out


PROXIMITY_HEADERS = ["Unit", "Bench", "Source", "Rows", "Culled", "Culled rows ft", "Near-miss kept",
                     "Permit-TVD (kept)", "Overridden / flag-only", "Nearest producer (hz / vt / alongside)"]


def proximity_rows(sig: dict[str, Any]) -> list[list[Any]]:
    """One row per unit x bench the PDP-proximity rule touched (config v14)."""
    out = []
    for key, B in sig.get("benches", {}).items():
        for label, ub in B["units"].items():
            s = ub.get("pdp_proximity")
            if not s or not (s["culled"] or s["would_cull"] or s["near"] or s["permit"]):
                continue
            first = (s["culled"] or s["would_cull"] or s["near"] or s["permit"])[0]
            out.append([label, key, ub["gate2"]["source"], s["n_rows"], s["n_culled"],
                        ", ".join(f"{c['offset_ft']:+,.0f}" for c in s["culled"]) or "—",
                        len(s["near"]), len(s["permit"]), len(s["would_cull"]), first["text"]])
    return out
