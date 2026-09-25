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
    "api10", "operator", "first_production_date", "lateral_length_ft", "bench", "spacing_class",
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
            w["api10"], w.get("operator"), w.get("first_production_date"), w.get("lateral_length_ft"),
            w.get("bench"), w.get("spacing_class"), w.get("tier"), w.get("scenario_class"), w.get("months_produced"),
            w.get("eur_per_1000ft"), w.get("anduin_oil_eur_per_1000ft"), di_n, di_e,
            f.get("b"), f.get("peak_index_months"), w.get("proppant_lbs_per_ft"),
        ])
    return out


BUILDUP_HEADERS = [
    "api10", "Operator", "First prod", "Lateral ft", "Bench", "Spacing", "Codev tier", "Scenario", "Months",
    "Novi EUR/1,000 ft (screen)", "anduin oil EUR/1,000 ft", "Di nom /yr", "Di eff yr-1", "b",
    "Peak mo", "Proppant lb/ft",
]


def write_csv(path: Path, wells: list[dict[str, Any]], cols: list[str] = BUILDUP_COLS) -> None:
    with path.open("w", newline="", encoding="utf-8") as fh:
        w = csv.writer(fh)
        w.writerow(cols)
        for r in wells:
            w.writerow([";".join(r[c]) if isinstance(r.get(c), list) else r.get(c) for c in cols])
