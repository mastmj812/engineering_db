"""Assemble the dossier (markdown) + per-bench artefacts from a run directory.

Conventions stated in the document itself: Di nominal /yr AND 1-yr effective,
EUR = raw 50-yr technical integral (anduin) / Novi's own EUR, SPE P10 = HIGH,
per-1,000-ft values, Novi comparison = MEDIAN of representative sticks.
No economics.
"""

from __future__ import annotations

import json
import re
import zlib
from pathlib import Path
from typing import Any

from dealintake.decline import effective_from_nominal
from dealintake.render import maps
from dealintake.render.tables import (
    BUILDUP_HEADERS,
    buildup_rows,
    di_pair,
    md,
    num,
    p_value,
    pct,
    write_csv,
)
from dealintake.select_wells import bench_code


def proposal_md(prop: dict[str, Any]) -> str:
    s = [f"# Deal proposal — {Path(prop['deal_file']).name}", ""]
    s.append(f"config_version {prop['config_version']} · snapshot: " + ", ".join(
        f"{k} {v}" for k, v in prop["snapshot"].items()))
    for w in prop.get("warnings", []):
        s.append(f"\n> WARNING: {w}")
    s.append("\n**Reviewer confirms before `evaluate`: the per-unit bench list and planned laterals in "
             "`benches.yaml` (seeded below — edit that file), the correlated window, per-bench spacing.** "
             "Declared land depths are NOT local depths (often a distant reference-log pick); formation "
             "phrases are resolved by stratigraphic order, never into a depth.\n")
    if any("bench_seed" in u for u in prop["units"]):
        s.append(md(["Unit", "DSU", "Rights", "Planned lateral ft", "Seeded ON", "Needs a look (edge / thin)"],
                    [[u["label"], u.get("dsu_name"), u.get("rights"), f"{u['planned_lateral']['median_ft']:,.0f}",
                      ", ".join(b for b, r in u["bench_seed"].items() if r["evaluate"]) or "—",
                      ", ".join(b for b, r in u["bench_seed"].items()
                                if r["why"].startswith(("edge", "thin"))) or "—"]
                     for u in prop["units"]]))
        s.append("")
    for u in prop["units"]:
        pl = u["planned_lateral"]
        s.append(f"## {u['label']} — {u['area_ac']:,.0f} ac" + (f" — DSU {u['dsu_name']}" if u.get("dsu_name") else ""))
        s.append(f"- Planned lateral: **{pl['median_ft']:,.0f} ft** median chord "
                 f"({pl['min_ft']:,.0f}–{pl['max_ft']:,.0f}), {pl['setback_ft']:.0f}-ft setback all sides, "
                 f"azimuth {pl['azimuth_deg']}° ({pl['azimuth_source']})")
        raw = u.get("declared_window_raw") or {}
        if u.get("rights"):
            s.append(f"- Rights: land file Min `{raw.get('Min_Depth')}` / Max `{raw.get('Max_Depth')}` → "
                     f"**{u['rights']}** (basin {u.get('basin')})")
        elif u.get("window_used"):
            s.append(f"- Depth window: declared {raw} → used {u['window_used']} ({u['window_source']})")
        else:
            s.append("- Depth window: no declared depths in the land file — no window applied")
        iou = u.get("pad_iou_advisory")
        s.append(f"- Novi pad IoU (advisory): {'—' if not iou else f'{iou['iou']:.2f} ({iou['pad_name']})'}")
        pdp = sorted({p["bench"] for p in u["pdp_in_unit"]})
        s.append(f"- PDP already in unit (>=30% inside): {', '.join(pdp) or 'none'}\n")
        seed = u.get("bench_seed") or {}
        if seed:
            seen = {bench_code(r["bench"]) for r in u["bench_proposal"]}
            s.append(md(["Bench", "Local median TVD ft", "Wells", "Status vs window", "Seed", "Why"],
                        [[r["bench"], r["median_tvd_ft"], r["wells"], r["status"],
                          "ON" if seed.get(bench_code(r["bench"]), {}).get("evaluate") else "off",
                          seed.get(bench_code(r["bench"]), {}).get("why", "not a target bench")]
                         for r in u["bench_proposal"]]
                        + [[b, None, 0, "—", "off", v["why"]] for b, v in seed.items() if b not in seen]))
        else:
            s.append(md(["Bench", "Local median TVD ft", "Wells", "Status vs window", "Margin ft", "Note"],
                        [[r["bench"], r["median_tvd_ft"], r["wells"], r["status"], r.get("margin_ft"), r.get("note")]
                         for r in u["bench_proposal"]]))
        s.append("\n**Gate 2 — location source per bench** (BASE_CASE = PUD; RES shown for context)\n")
        s.append(md(["Bench", "PUD inside", "PUD crossing", "RES inside", "RES crossing", "Source", "Why"],
                    [[b, g["pud_inside"], g["pud_crossing"], g["res_inside"], g["res_crossing"],
                      g["source"], g["reason"]] for b, g in u["gate2"].items()]))
        s.append("")
    return "\n".join(s)


def _transfer_rows(G: dict[str, Any]) -> list[list[Any]]:
    """Oil + gas TC with (default) vs without the short-history transfer."""
    wo_all = G.get("tc_preview_no_transfer") or {}
    rows = []
    for stream in ("oil", "gas"):
        w, wo = (G.get("tc_preview") or {}).get(stream), wo_all.get(stream)
        if not w or not wo:
            continue
        for label, p in (("with transfer (default)", w), ("own fits (without)", wo)):
            dn, de = di_pair(p.get("Di"), p.get("b"))
            delta = None
            if label.startswith("with") and wo.get("eur_per_unit"):
                delta = f"{w['eur_per_unit'] / wo['eur_per_unit'] - 1:+.1%}"
            rows.append([stream, label, p.get("qi"), dn, de, p.get("b"), p.get("eur_per_unit"),
                         delta if delta is not None else "—"])
    return rows


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


def _slug(text: str) -> str:
    """File-name-safe key: 'WCB_1 @ 12,620 ft' -> 'WCB_1_12620ft'. Long group
    names (many units joined by ' + ') are capped — Windows paths are finite."""
    out = re.sub(r"[^A-Za-z0-9_+-]+", "_", text.replace(",", "").replace(" ft", "ft").replace("@", "")).strip("_")
    out = re.sub(r"_+", "_", out)
    return out if len(out) <= 80 else f"{out[:64]}_{zlib.crc32(out.encode()):08x}"


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

    plan = sig.get("unit_plan")
    if plan:
        by = {u["label"]: u for u in prop["units"]}
        cls_of = {u: c["planned_lateral_ft"] for c in sig.get("lateral_classes", []) for u in c["units"]}
        s.append(f"\n## Unit plan (reviewer — {sig.get('plan_source')})\n")
        s.append(md(["Unit", "DSU", "Rights", "Benches evaluated", "Planned lateral ft", "Lateral class ft", "Edited vs seed"],
                    [[lb, by.get(lb, {}).get("dsu_name"), by.get(lb, {}).get("rights"),
                      ", ".join(p["benches"]) or "NOT EVALUATED", f"{p['planned_lateral_ft']:,.0f}",
                      f"{cls_of[lb]:,.0f}" if lb in cls_of else "—", "yes" if p["edited"] else "no"]
                     for lb, p in plan.items()]))

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

    for bench, B in sig["benches"].items():            # key: "WCB_1" or "WCB_1 @ 12,620 ft" (lateral class)
        s.append(f"\n## {bench} — TVD {B['tvd_ft']:,.0f} ft, spacing {B['spacing_ft']:,.0f} ft ({B['spacing_source']}), basin {B.get('basin')}\n")
        cls = B.get("class_units")
        if cls:
            s.append(f"Units: {', '.join(cls)} — planned lateral {B['planned_lateral_ft']:,.0f} ft "
                     "(centers the lateral band for this pool).\n")
        png = f"map_{_slug(bench)}.png"
        maps.bench_map(run_dir / png, bench, [u for u in prop["units"] if not cls or u["label"] in cls], B)
        s.append(f"![{bench} map]({png})\n")
        pool = B["pool"]
        s.append(f"**Eligible pool:** {pool['n_eligible']} wells ({pool['n_excluded']} excluded: " + ", ".join(
            f"{k} {v}" for k, v in sorted(pool["exclusion_reasons"].items(), key=lambda kv: -kv[1])) + "). "
            f"Adjacent planned benches: {', '.join(pool['adjacent_planned']) or 'none'}; tier order "
            f"{' → '.join(pool['tier_order'])} ({pool['order_reason']}).")
        for f in pool["flags"]:
            s.append(f"\n> {f}")

        tr = B.get("short_history_transfer")
        if tr:
            s.append(f"\n### Short-history cohort transfer (default on, cutoff {tr['cutoff_months']} post-peak months)\n")
            if tr.get("error"):
                s.append(f"> {tr['flag']}: {tr['error']}")
            else:
                donors = "; ".join(
                    f"{d['stream']} Di {d['cohort_di']:.2f}/yr ({pct(effective_from_nominal(d['cohort_di'], d['cohort_b']))} eff) "
                    f"b {d['cohort_b']:.2f} from {d['donor_count']} wells" for d in tr["donors"])
                s.append(f"{tr['n_long']} long wells lent median decline to {tr['n_short']} short wells "
                         f"({len(tr['written'])} anduin forecasts rewritten; {len(tr['skipped_locked'])} locked rows "
                         f"kept; {len(tr['skipped_no_peak'])} with no peak). Lender medians: {donors}.")
                if tr["n_short"]:
                    s.append(f"\nVintage: lenders' median first prod {num(tr['long_fp_year_median'], '.1f')} vs "
                             f"short wells {num(tr['short_fp_year_median'], '.1f')}; proppant "
                             f"{num(tr['long_proppant_lbs_ft_median'], ',.0f')} vs "
                             f"{num(tr['short_proppant_lbs_ft_median'], ',.0f')} lb/ft.")
                else:
                    s.append("\nNo short wells in the pool — nothing borrowed, nothing rewritten.")
                if tr.get("flag"):
                    s.append(f"\n> {tr['flag']}")
                if tr["written"]:
                    s.append(f"\nRewritten: {', '.join(tr['written'])}")
            cmp_ = B.get("transfer_compare") or {}
            if cmp_.get("note"):
                s.append(f"\n> With/without: {cmp_['note']}.")
            if cmp_.get("flag"):
                s.append(f"\n> **{cmp_['flag']}**")

        sp = B["split"]
        s.append(f"\n### TC granularity (gate 5b, run on the whole pool): **{sp['recommendation']}** "
                 f"— metric {sp['metric']}\n")
        if sp["groups"]:
            s.append(md(["Unit", "Pool wells", "Median /1,000 ft", "Eligible for own TC"],
                        [[g["unit"], g["n"], g["median"], g["eligible"]] for g in sp["groups"]]))
        test = f"{sp['test']} p {p_value(sp['p_value'])}" if sp.get("test") else "no rank test (< 2 eligible groups)"
        s.append(f"\nMedian ratio {num(sp['median_ratio'])}, {test}; gradient "
                 f"{num(sp['gradient_per_mile'], '+,.0f')} bbl/1,000 ft per mile along the cohort axis "
                 f"(R² {num(sp['gradient_r2'])}).")
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
            write_csv(run_dir / f"buildup_{_slug(f'{bench}_{G['name']}')}.csv", G["tc_wells"])
            s.append("\n**Buildup table**\n")
            s.append(md(BUILDUP_HEADERS, buildup_rows(G["tc_wells"], G.get("anduin_oil") or {})))
            s.append("\n**Three-stream comparison — Novi vs anduin TC**\n")
            s.append("Novi Di = segment 1 (days 0-540; spans year 1, so its 1-yr effective compares directly); "
                     "Novi pins segment-1 Di at 3.65/yr on many sticks — the cap share is shown. "
                     "Segment-2 Di beside it.\n")
            s.append(md(["Stream", "Source", "qi /1,000 ft (cal-day)", "Di nom /yr", "Di eff yr-1", "b",
                         "EUR /1,000 ft"], _stream_rows(G)))
            wo = _transfer_rows(G)
            if wo:
                s.append(f"\n**With vs without short-history transfer** — {G['n_transferred_in_cohort']} of "
                         f"{len(G['tc_wells'])} cohort wells carry borrowed Di/b (default = with)\n")
                s.append(md(["Stream", "TC", "qi /1,000 ft (cal-day)", "Di nom /yr", "Di eff yr-1", "b",
                             "EUR /1,000 ft", "EUR vs without"], wo))
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
