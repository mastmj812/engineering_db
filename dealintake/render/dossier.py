"""Assemble the dossier (markdown) + per-bench artefacts from a run directory.

Conventions stated in the document itself: Di nominal /yr AND 1-yr effective,
EUR = raw 50-yr technical integral (anduin) / Novi's own EUR, SPE P10 = HIGH,
per-1,000-ft values, Novi comparison = MEDIAN of representative sticks.
No economics.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from dealintake.render import maps
from dealintake.render.tables import (
    BUILDUP_HEADERS,
    buildup_rows,
    di_pair,
    md,
    pct,
    write_csv,
)


def proposal_md(prop: dict[str, Any]) -> str:
    s = [f"# Deal proposal — {Path(prop['deal_file']).name}", ""]
    s.append(f"config_version {prop['config_version']} · snapshot: " + ", ".join(
        f"{k} {v}" for k, v in prop["snapshot"].items()))
    for w in prop.get("warnings", []):
        s.append(f"\n> WARNING: {w}")
    s.append("\n**Reviewer confirms before `evaluate`: allowed benches, correlated window, per-bench spacing.** "
             "Declared land depths are NOT local depths (often a distant reference-log pick).\n")
    for u in prop["units"]:
        pl = u["planned_lateral"]
        s.append(f"## {u['label']} — {u['area_ac']:,.0f} ac")
        s.append(f"- Planned lateral: **{pl['median_ft']:,.0f} ft** median chord "
                 f"({pl['min_ft']:,.0f}–{pl['max_ft']:,.0f}), {pl['setback_ft']:.0f}-ft setback all sides, "
                 f"azimuth {pl['azimuth_deg']}° ({pl['azimuth_source']})")
        s.append(f"- Depth window: declared {u['declared_window_raw']} → used {u['window_used']} "
                 f"({u['window_source']})")
        iou = u.get("pad_iou_advisory")
        s.append(f"- Novi pad IoU (advisory): {'—' if not iou else f'{iou['iou']:.2f} ({iou['pad_name']})'}")
        pdp = sorted({p["bench"] for p in u["pdp_in_unit"]})
        s.append(f"- PDP already in unit (>=30% inside): {', '.join(pdp) or 'none'}\n")
        s.append(md(["Bench", "Local median TVD ft", "Wells", "Status vs window", "Margin ft", "Note"],
                    [[r["bench"], r["median_tvd_ft"], r["wells"], r["status"], r.get("margin_ft"), r.get("note")]
                     for r in u["bench_proposal"]]))
        s.append("\n**Gate 2 — location source per bench** (BASE_CASE = PUD; RES shown for context)\n")
        s.append(md(["Bench", "PUD inside", "PUD crossing", "RES inside", "RES crossing", "Source", "Why"],
                    [[b, g["pud_inside"], g["pud_crossing"], g["res_inside"], g["res_crossing"],
                      g["source"], g["reason"]] for b, g in u["gate2"].items()]))
        s.append("")
    return "\n".join(s)


def _stream_rows(B: dict[str, Any]) -> list[list[Any]]:
    rows = []
    for stream in ("oil", "gas", "water"):
        nv = (B.get("novi") or {}).get(stream)
        if nv:
            cap = nv.get("seg1_at_cap_frac")
            seg2 = nv.get("seg2_di_nominal")
            rows.append([stream, f"Novi (median of {nv['n']} sticks)", nv.get("qi_per_1000ft"),
                         (f"{nv['di_nominal']:.2f}" if nv.get("di_nominal") is not None else "—")
                         + (f" ({cap:.0%} at 3.65 cap)" if cap else "")
                         + (f"; seg-2 {seg2:.2f}" if seg2 is not None else ""),
                         pct(nv.get("di_effective")), nv.get("b"), nv.get("eur_per_1000ft")])
        tc = (B.get("tc_preview") or {}).get(stream)
        if tc:
            dn, de = di_pair(tc.get("Di"), tc.get("b"))
            rows.append([stream, f"anduin TC preview (n={B.get('tc_preview_n_wells')})", tc.get("qi"),
                         dn, de, tc.get("b"), tc.get("eur_per_unit")])
        gr = B.get("tc_preview_gas_ratio") if stream == "gas" else None
        if gr and gr.get("eur_per_unit") is not None:
            arps = ((B.get("tc_preview") or {}).get("gas") or {}).get("eur_per_unit")
            vs = f"; {gr['eur_per_unit'] / arps:.2f}x Arps EUR" if arps else ""
            fit = (f"GOR fit {gr.get('sub_mode')}, R² {gr['r2']:.2f}" if gr.get("r2") is not None
                   else f"GOR fit {gr.get('sub_mode')}")
            rows.append([stream, f"anduin TC — ratio to cum oil ({fit}{vs})", None,
                         "— (derived)", pct(gr.get("implied_effective_decline_yr1")), None,
                         gr["eur_per_unit"]])
    return rows


def render(run_dir: Path) -> Path:
    prop = json.loads((run_dir / "proposal.json").read_text(encoding="utf-8"))
    sig = json.loads((run_dir / "signals.json").read_text(encoding="utf-8"))
    s = [f"# Deal dossier — {Path(prop['deal_file']).stem}", ""]
    s.append("## Run snapshot (gate 0)\n")
    snap = [[k, v] for k, v in sig["snapshot"].items()]
    snap += [["config_version", sig["config_version"]], ["planned stack (shallow→deep)", ", ".join(sig["planned_stack"])],
             ["planned lateral (median of units)", f"{sig['planned_lateral_ft']:,.0f} ft"]]
    s.append(md(["Field", "Value"], snap))
    s.append("\nConventions: Di = nominal /yr with 1-yr effective beside it; EUR = raw 50-yr technical "
             "integral, per 1,000 ft of lateral; Novi figures are the MEDIAN of representative sticks "
             "(not a P50, not the erebor export's cohort mean); no economics.\n")
    for f in sig["flags"]:
        s.append(f"> FLAG: {f}")

    s.append("\n## Bench matrix (unit x bench)\n")
    rows = []
    for bench, B in sig["benches"].items():
        for label, ub in B["units"].items():
            g3 = ub["gate3"]
            rows.append([label, bench, f"{g3['n_locations']} ({ub['gate2']['source']})",
                         g3["pdp_count_3mi_median"], g3["status"], g3["tvd_excess_3mi_ft_max"],
                         "yes" if ub["has_pdp_in_adjacent_bench"] else "no",
                         next((G["name"] for G in B["tc_groups"] if label in G["units"]), "—"),
                         "yes" if B["edge_trigger"]["fired"] else "no"])
    s.append(md(["Unit", "Bench", "Locations (src)", "pdp_count_3mi med", "Gate 3", "TVD excess max ft",
                 "PDP in adjacent bench", "TC group", "Edge"], rows))

    for bench, B in sig["benches"].items():
        s.append(f"\n## {bench} — TVD {B['tvd_ft']:,.0f} ft, spacing {B['spacing_ft']:,.0f} ft ({B['spacing_source']}), basin {B.get('basin')}\n")
        maps.bench_map(run_dir / f"map_{bench}.png", bench, prop["units"], B)
        s.append(f"![{bench} map](map_{bench}.png)\n")
        pool = B["pool"]
        s.append(f"**Eligible pool:** {pool['n_eligible']} wells ({pool['n_excluded']} excluded: " + ", ".join(
            f"{k} {v}" for k, v in sorted(pool["exclusion_reasons"].items(), key=lambda kv: -kv[1])) + "). "
            f"Adjacent planned benches: {', '.join(pool['adjacent_planned']) or 'none'}; tier order "
            f"{' → '.join(pool['tier_order'])} ({pool['order_reason']}).")
        for f in pool["flags"]:
            s.append(f"\n> {f}")

        sp = B["split"]
        s.append(f"\n### TC granularity (gate 5b, run on the whole pool): **{sp['recommendation']}** "
                 f"— metric {sp['metric']}\n")
        if sp["groups"]:
            s.append(md(["Unit", "Pool wells", "Median /1,000 ft", "Eligible for own TC"],
                        [[g["unit"], g["n"], g["median"], g["eligible"]] for g in sp["groups"]]))
        s.append(f"\nMedian ratio {sp['median_ratio']}, {sp['test']} p {sp['p_value']}; gradient "
                 f"{sp['gradient_per_mile']} per mile along the cohort axis (R² {sp['gradient_r2']}).")
        for n in sp["notes"]:
            s.append(f"\n> {n}")
        ov = sp.get("reviewer_override")
        if ov:
            s.append(f"\n> **Reviewer grouping** (test said {ov['test_said']}): "
                     + " | ".join(" + ".join(c) for c in ov["groups"]))

        for G in B["tc_groups"]:
            s.append(f"\n### TC group: {G['name']} — units {', '.join(G['units'])}\n")
            if G.get("note"):
                s.append(f"> {G['note']}\n")
            s.append(md(["Tier", "TC wells", "Median Novi EUR/1,000 ft (group pool)"],
                        [[t, G["tier_counts"].get(t, 0), G["tier_medians_novi_eur_per_1000ft"].get(t)]
                         for t in pool["tier_order"]]))
            for f in G["flags"]:
                s.append(f"\n> {f}")
            slug = f"{bench}_{G['name']}".replace(" ", "_").replace("(", "").replace(")", "")
            write_csv(run_dir / f"buildup_{slug}.csv", G["tc_wells"])
            s.append("\n**Buildup table**\n")
            s.append(md(BUILDUP_HEADERS, buildup_rows(G["tc_wells"], G.get("anduin_oil") or {})))
            s.append("\n**Three-stream comparison — Novi vs anduin TC**\n")
            s.append("Novi Di = segment 1 (days 0-540; spans year 1, so its 1-yr effective compares directly); "
                     "Novi pins segment-1 Di at 3.65/yr on many sticks — the cap share is shown. "
                     "Segment-2 Di beside it.\n")
            s.append(md(["Stream", "Source", "qi /1,000 ft (cal-day)", "Di nom /yr", "Di eff yr-1", "b",
                         "EUR /1,000 ft"], _stream_rows(G)))
            qc = G.get("qc")
            s.append("\n**Autoforecast QC (flags only)**\n")
            if qc:
                s.append(md(["Stream", "n", "Median Di eff", "IQR eff", "Median Di nom", "Median b", "Cohort flag"],
                            [[k, v["n"], pct(v["de_median"]),
                              None if v["de_p25"] is None else f"{pct(v['de_p25'])}–{pct(v['de_p75'])}",
                              v["di_nominal_median"], v["b_median"],
                              v["cohort_flag"] or ("—" if v["flagged"] else "report-only")]
                             for k, v in qc["streams"].items()]))
                if qc["well_flags"]:
                    s.append("\n" + md(["api10", "Stream", "Flag", "Value", "Threshold"],
                                       [[f["api10"], f["stream"], f["flag"], f["value"], f["threshold"]]
                                        for f in qc["well_flags"]]))
            else:
                s.append("_anduin not run (--no-anduin)._")

    s.append("\n## Decision log\n")
    s.append(md(["#", "Gate", "Bench", "Signal", "Decision", "By"],
                [[i + 1, d["gate"], d.get("bench"), d["signal"], d["decision"], d["by"]]
                 for i, d in enumerate(sig.get("decision_log", []))]))
    s.append("\n## Handoff\n\n- anduin TC: preview only — save in anduin after review (`included_api10s` = buildup CSV)."
             "\n- narvi scenario: generated benches are previews — build + save the scenario in narvi."
             "\n- Forecast to finance: Michael's call per bench.")
    out = run_dir / "dossier.md"
    out.write_text("\n".join(s) + "\n", encoding="utf-8")
    return out
