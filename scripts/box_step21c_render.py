"""BOX step 21c page: index.html from the files `scripts.box_step21c judge` wrote (no number is recomputed here).

    python -m scripts.box_step21c render [--docs docs/box/step21c-2026-11-02]
"""

from __future__ import annotations

import html
import json
from pathlib import Path

import numpy as np
import pandas as pd

from box.edge_gap_report import _CSS, _table

PCT = "+.1%"


def _fmt(cols: list[str]) -> dict[str, str]:
    return ({c: PCT for c in cols if "bias" in c or c in ("interval_lo", "interval_hi", "range_lo", "range_hi", "rel_diff")}
            | {c: ".3f" for c in cols if c.startswith(("factor", "g48")) or "band" in c} | {c: ".0%" for c in cols if "share" in c})


def _dots(pc: pd.DataFrame) -> str:
    """One row per judged cell: the frozen P2.5-P97.5 interval (bar), the tuning bias (tick) and the holdout bias (dot)."""
    if pc.empty:
        return ""
    lo = float(min(pc["interval_lo"].min(), pc["holdout_bias"].min(), -0.3))
    hi = float(max(pc["interval_hi"].max(), pc["holdout_bias"].max(), 0.3))
    w, left, rh = 560, 110, 22
    x = lambda b: left + (b - lo) / (hi - lo) * (w - left - 20)
    rows = []
    for i, r in enumerate(pc.itertuples()):
        y = 18 + i * rh
        col = "#16a34a" if r.inside_interval else "#dc2626"
        rows.append(f"<text x='4' y='{y + 4}' font-size='11'>{r.stream} cum-{r.horizon}</text>"
                    f"<line x1='{x(r.interval_lo):.1f}' x2='{x(r.interval_hi):.1f}' y1='{y}' y2='{y}' stroke='#9ca3af' stroke-width='6'/>"
                    f"<line x1='{x(r.tuning_bias):.1f}' x2='{x(r.tuning_bias):.1f}' y1='{y - 6}' y2='{y + 6}' stroke='#111827' stroke-width='2'/>"
                    f"<circle cx='{x(r.holdout_bias):.1f}' cy='{y}' r='5' fill='{col}'/>")
    h = 18 + len(pc) * rh
    zero = f"<line x1='{x(0):.1f}' x2='{x(0):.1f}' y1='6' y2='{h}' stroke='#d1d5db' stroke-dasharray='3 3'/>"
    ticks = "".join(f"<text x='{x(t):.1f}' y='{h + 12}' font-size='10' text-anchor='middle'>{t:+.0%}</text>"
                    for t in np.arange(np.ceil(lo * 10) / 10, hi + 1e-9, 0.1))
    return f"<svg width='{w}' height='{h + 18}' role='img'>{zero}{''.join(rows)}{ticks}</svg>"


def main(docs: Path) -> int:
    V = json.loads((docs / "verdicts.json").read_text(encoding="utf-8"))
    rd = {n: pd.read_csv(docs / f"{n}.csv") for n in ("pooled_cells", "counts", "wf_identity", "f_drift", "d102", "guard_d106", "disclosure",
                                                      "vintage", "water_holdout", "pooled_variants", "pooled_tuning_21b", "coverage", "per_cutoff",
                                                      "diag_shift", "diag_null_group", "disclosure_provisional_r2p")
          if (docs / f"{n}.csv").exists()}
    G = V["groups"]
    summ = pd.DataFrame([{"group": g, "record oil / gas": f"{x['record']['oil']} / {x['record']['gas']}", "cells": ", ".join(x["cells"]) or "none",
                          "D99": x["verdict"]["overall"], "outside": ", ".join(x["verdict"]["outside"]) or "—", "tier (§6 as computed)": x["tier"],
                          "haircut oil / gas (step 23)": f"{x['haircut_d102']['oil']} / {x['haircut_d102']['gas']}",
                          "water holdout judged / consistent": f"{x['water']['holdout_judged']} / {x['water']['consistent']}"} for g, x in G.items()])
    parts = [f"<!doctype html><html><head><meta charset='utf-8'><title>BOX step 21c holdout</title><style>{_CSS}</style></head><body>",
             "<h1>BOX step 21c — Midland one-time D52 holdout (revision 8, frozen SHA 5ceadc2)</h1>",
             (f"<div class=meta>Built {html.escape(V['meta']['built_utc'])} at HEAD {V['meta']['head'][:7]}; definition digest "
             f"{V['meta']['definition_digest'][:8]}; frozen intervals {V['meta']['frozen_intervals']['got']['frozen_d99.csv'][:8]} / "
             f"{V['meta']['frozen_intervals']['got']['frozen_water.csv'][:8]} (= GATE_21B.json). Bias = Σ actual / Σ forecast − 1: "
             "<b>negative = BOX over-forecasts</b>. Grain = D53 packages pooled over cutoffs. MID_WCC: no D99 cell, not scored.</div>"),
             "<h2>1. Verdicts</h2>", _table(summ)]
    pc = rd.get("pooled_cells", pd.DataFrame())
    parts.append("<h2>2. Judged cells (bar = frozen P2.5–P97.5 tuning interval, tick = tuning bias, dot = holdout bias)</h2>")
    for g in G:
        x = pc[pc["group"] == g]
        parts.append(f"<h3>{g} — {G[g]['verdict']['overall']}</h3>")
        if len(x):
            parts.append(_dots(x))
            cols = ["stream", "horizon", "packages", "tuning_bias", "interval_lo", "interval_hi", "holdout_bias", "inside_interval", "bias_ok_10pct",
                    "band_scale_free", "bench_band_scale_free", "spread_ok", "bench_bias", "frozen_expected_d99_cell"]
            parts.append(_table(x[cols], _fmt(cols)))
        else:
            parts.append("<div class=flag>No judged cell.</div>")
    for name, title in (("counts", "3. Holdout packages scored vs the 21b expectation"), ("pooled_variants", "4. Pooled holdout cells per treatment (reported)"),
                        ("pooled_tuning_21b", "4b. The same cells on the tuning packages (21b, reproduced)"),
                        ("d102", "5. Step-23 haircut table (D102: tuning + holdout mid_r2p merged per cutoff, ≥ 30 floor)"),
                        ("guard_d106", "5b. 9c guard (D106) on the D102 table"), ("disclosure", "6. D105 disclosure lines (record treatment; 95 % 3-mi-block bootstrap)"),
                        ("disclosure_provisional_r2p", "6a. D105 lines on raw mid_r2p (what a provisional group ships) where the record carried wf"),
                        ("vintage", "6b. By vintage (tuning + holdout)"),
                        ("diag_shift", "7a-diag. FAIL diagnosis: holdout − tuning shift, BOX vs the local-offsets benchmark (reported only)"),
                        ("diag_null_group", "7b-diag. FAILs a holdout like tuning would give (21b pass rate of a good forecast)"), ("water_holdout", "7. Water holdout (D109: ≥ 10 measured packages, frozen interval)"),
                        ("per_cutoff", "8. Per-cutoff D53 cells, record (reported, never gating)"), ("coverage", "9. Proximity coverage of the holdout wells"),
                        ("wf_identity", "10. Walk-forward identity (holdout haircuts = tuning haircuts)"), ("f_drift", "11. F(k) drift: holdout run vs 21b")):
        if name in rd:
            d = rd[name]
            parts.append(f"<h2>{html.escape(title)}</h2>" + _table(d, _fmt(list(d.columns)), max_rows=400))
    parts.append("</body></html>")
    (docs / "index.html").write_text("\n".join(parts), encoding="utf-8")
    print(f"wrote {docs / 'index.html'}")
    return 0
