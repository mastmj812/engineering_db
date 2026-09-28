"""The reviewer's Stage 2 picture: dossier.html rendered from signals.json.

Per (bench x lateral class): the map, the pool and its tiers, the split
test, and per TC group the RATE-TIME OVERLAY (anduin TC per 1,000 ft vs the
Novi representative-stick median, with the no-transfer curve when one
exists), the three-stream table, QC flags and the buildup table. A summary
table up top links every curve. Conventions as the markdown dossier: Di
nominal /yr with 1-yr effective beside it, EUR = raw 50-yr integral per
1,000 ft, Novi = MEDIAN of representative sticks (not a P50), no economics.
dossier.md stays as the plain-text record; this page is what Michael reads.
"""

from __future__ import annotations

import html
import io
import json
import math
from pathlib import Path
from typing import Any

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt

from dealintake.decline import effective_from_nominal
from dealintake.render.dossier import _slug, _stream_rows, _transfer_rows
from dealintake.render.tables import (
    BUILDUP_HEADERS,
    buildup_rows,
    di_pair,
    num,
    p_value,
    pct,
)

INK = "#111827"
STREAM_UNIT = {"oil": "bbl/d per 1,000 ft", "gas": "Mcf/d per 1,000 ft", "water": "bbl/d per 1,000 ft"}
DAYS_PER_MONTH = 365.25 / 12


class _Raw(str):
    """Pre-escaped HTML."""


def _esc(v: Any) -> str:
    return html.escape("—" if v is None else str(v))


def _cell(v: Any) -> str:
    if isinstance(v, _Raw):
        return v
    if isinstance(v, float):
        return html.escape(f"{v:,.2f}" if abs(v) < 100 else f"{v:,.0f}")
    return _esc(v)


def _table(headers: list[str], rows: list[list[Any]], cls: str = "") -> str:
    h = "".join(f"<th>{_esc(x)}</th>" for x in headers)
    body = "".join("<tr>" + "".join(f"<td>{_cell(c)}</td>" for c in r) + "</tr>" for r in rows)
    return f'<table class="{cls}"><thead><tr>{h}</tr></thead><tbody>{body}</tbody></table>'


def _chip(text: str, color: str) -> _Raw:
    return _Raw(f'<span class="chip" style="background:{color}">{html.escape(text)}</span>')


def _svg(fig) -> str:
    buf = io.StringIO()
    fig.savefig(buf, format="svg", bbox_inches="tight")
    plt.close(fig)
    body = buf.getvalue()
    return body[body.index("<svg"):]


def novi_curve(nv: dict[str, Any], months: int) -> list[float] | None:
    """Novi's 2-segment Arps from the representative-stick medians, per
    1,000 ft, monthly: segment 1 (Di1, b1) to seg1_days, then segment 2
    (Di2, b2) continuing from the segment-1 rate. Median-of-parameters, so a
    shape for comparison — not a stick's own forecast."""
    qi, d1, b1 = nv.get("qi_per_1000ft"), nv.get("di_nominal"), nv.get("b")
    if not qi or d1 is None or b1 is None:
        return None
    t1 = float(nv.get("seg1_days") or 540) / 365.25
    d2 = nv.get("seg2_di_nominal") if nv.get("seg2_di_nominal") is not None else d1
    b2 = nv.get("seg2_b") if nv.get("seg2_b") is not None else b1

    def arps(q0: float, d: float, b: float, t: float) -> float:
        return q0 * math.exp(-d * t) if abs(b) < 1e-6 else q0 / (1.0 + b * d * t) ** (1.0 / b)

    q_seam = arps(qi, d1, b1, t1)
    out = []
    for m in range(months):
        t = m / 12.0
        out.append(arps(qi, d1, b1, t) if t <= t1 else arps(q_seam, d2, b2, t - t1))
    return out


def cum_curve(rates: list[float]) -> list[float]:
    """Cumulative per 1,000 ft from monthly calendar-day rates (x days/month)."""
    out, acc = [], 0.0
    for r in rates:
        acc += r * DAYS_PER_MONTH
        out.append(acc)
    return out


def rate_time_chart(G: dict[str, Any], months: int = 120) -> str:
    """Rate vs time (log) on top, cumulative vs time below — oil and gas, per
    1,000 ft. anduin TC = smoothed_rate; Novi = 2-segment Arps from the
    representative-stick medians; own fits dotted when the transfer touched
    the cohort (Michael 2026-09-26: cum beside rate)."""
    streams = [st for st in ("oil", "gas") if (G.get("tc_preview") or {}).get(st)]
    if not streams:
        return ""
    fig, axes = plt.subplots(2, len(streams), figsize=(5.2 * len(streams), 6.6), dpi=100, squeeze=False)
    legend: dict[str, Any] = {}                 # label -> handle, across both streams
    for col, st in enumerate(streams):
        ax_r, ax_c = axes[0][col], axes[1][col]
        tc = G["tc_preview"][st]
        sr = list(tc.get("smoothed_rate") or [])[:months]
        dn, de = di_pair(tc.get("Di"), tc.get("b"))
        series: list[tuple[list[float], dict[str, Any], str]] = []
        if sr:
            series.append((sr, {"color": INK, "linewidth": 1.8},
                           (f"anduin TC (n={G.get('tc_preview_n_wells')}): qi {tc.get('qi', 0):,.0f}, Di {dn}/yr ({de}), "
                            f"b {tc.get('b', 0):.2f}, EUR {tc.get('eur_per_unit', 0):,.0f}")))
        wo = list(((G.get("tc_preview_no_transfer") or {}).get(st) or {}).get("smoothed_rate") or [])[:months]
        if wo:
            series.append((wo, {"color": "#6b7280", "linewidth": 1.2, "linestyle": ":"}, "own fits (without transfer)"))
        nv = (G.get("novi") or {}).get(st)
        cv = novi_curve(nv, months) if nv else None
        if cv:
            series.append((cv, {"color": "#7c3aed", "linewidth": 1.6, "linestyle": "--"},
                           f"Novi median of {nv['n']} sticks: qi {nv['qi_per_1000ft']:,.0f}, Di {nv['di_nominal']:.2f}/yr "
                           f"({pct(nv.get('di_effective'))}), b {nv['b']:.2f}; seg-2 Di {num(nv.get('seg2_di_nominal'))}"
                           + (f", EUR {nv['eur_per_1000ft']:,.0f}" if nv.get("eur_per_1000ft") else "")))
        for ys, style, label in series:
            ax_r.plot(range(len(ys)), ys, label=label, **style)
            ax_c.plot(range(len(ys)), [c / 1000.0 for c in cum_curve(ys)], label=label, **style)
        ax_r.set_yscale("log")
        ax_r.set_ylabel(STREAM_UNIT[st], fontsize=8)
        ax_r.set_title(f"{st} — rate", fontsize=9)
        ax_c.set_ylabel(("Mbbl" if st != "gas" else "MMcf") + " per 1,000 ft", fontsize=8)
        ax_c.set_title(f"{st} — cumulative", fontsize=9)
        ax_c.set_xlabel("months from first production", fontsize=8)
        for ax in (ax_r, ax_c):
            ax.set_xlim(0, months)
            ax.grid(True, which="both", linewidth=0.3, alpha=0.5)
            ax.tick_params(labelsize=7)
        for h, lab in zip(*ax_r.get_legend_handles_labels()):
            legend.setdefault(lab, h)
    if legend:
        fig.legend(list(legend.values()), list(legend), fontsize=6.5, loc="lower center",
                   bbox_to_anchor=(0.5, -0.02), frameon=False, ncol=1)
    fig.tight_layout(rect=(0, 0.08, 1, 1))
    return _svg(fig)


def _summary_rows(sig: dict[str, Any]) -> list[list[Any]]:
    rows = []
    for key, B in sig["benches"].items():
        anchor = _slug(key)
        for G in B["tc_groups"]:
            tc = G.get("tc_preview") or {}
            o, g = tc.get("oil") or {}, tc.get("gas") or {}
            nv = (G.get("novi") or {}).get("oil") or {}
            dn, de = di_pair(o.get("Di"), o.get("b"))
            oe, ne = o.get("eur_per_unit"), nv.get("eur_per_1000ft")
            delta = f"{oe / ne - 1:+.0%}" if oe and ne else "—"
            gas_ratio = (G.get("novi_vs_tc") or {}).get("gas")
            gas_cell = "—" if gas_ratio is None else (_chip(f"Novi {gas_ratio:.1f}x", "#dc2626") if gas_ratio > 1.5 or gas_ratio < 1 / 1.5
                                                       else f"Novi {gas_ratio:.1f}x")
            sp = B["split"]["recommendation"]
            rows.append([_Raw(f'<a href="#{anchor}">{_esc(key)}</a>'), G["name"] if G["name"] != "all units" else "all",
                         B["pool"]["n_eligible"], G.get("tc_preview_n_wells"),
                         oe, ne, nv.get("n"), delta, f"{dn} ({de})" if o else "—", o.get("b"), g.get("eur_per_unit"), gas_cell,
                         _chip(sp, {"single_tc": "#059669", "split_by_polygon": "#2563eb", "escalate": "#d97706"}.get(sp, "#9ca3af")),
                         len((G.get("qc") or {}).get("well_flags", []))])
    return rows


_CSS = """
body{font:13px/1.45 -apple-system,Segoe UI,Roboto,sans-serif;color:#111827;margin:0 24px 48px;max-width:1500px}
h1{font-size:20px;margin:18px 0 4px} h2{font-size:16px;margin:36px 0 6px;border-top:2px solid #e5e7eb;padding-top:14px}
h3{font-size:14px;margin:18px 0 4px} .meta{color:#6b7280;font-size:12px}
.flag{background:#fffbeb;border-left:4px solid #d97706;padding:4px 10px;margin:4px 0} .bad{background:#fef2f2;border-left-color:#dc2626}
.row{display:flex;gap:18px;align-items:flex-start;flex-wrap:wrap} .row img{max-width:520px;height:auto} svg{max-width:100%;height:auto}
table{border-collapse:collapse;font-size:12px;margin:8px 0} th,td{border:1px solid #e5e7eb;padding:3px 7px;text-align:left;vertical-align:top}
th{background:#f9fafb} .chip{display:inline-block;color:#fff;border-radius:3px;padding:0 6px;font-weight:600;font-size:11px}
details{margin:6px 0} summary{cursor:pointer;color:#374151;font-size:12px} .toc a{margin-right:10px;font-size:12px}
"""


def render(run_dir: Path) -> Path:
    prop = json.loads((run_dir / "proposal.json").read_text(encoding="utf-8"))
    sig = json.loads((run_dir / "signals.json").read_text(encoding="utf-8"))
    name = {u["label"]: u.get("dsu_name") or u["label"] for u in prop["units"]}
    title = _esc(Path(prop["deal_file"]).stem)
    p: list[str] = [(f'<!doctype html><html><head><meta charset="utf-8"><title>Deal dossier — {title}</title>'
                     f"<style>{_CSS}</style></head><body>"),
                    f"<h1>Deal dossier — {title}</h1>",
                    '<div class="meta">' + " · ".join(f"{_esc(k)} {_esc(v)}" for k, v in sig["snapshot"].items())
                    + f" · config v{_esc(sig['config_version'])} · planned stack {_esc(', '.join(sig['planned_stack']))}</div>",
                    ("<p>Di = nominal /yr with 1-yr effective beside it; EUR = raw 50-yr technical integral per 1,000 ft of "
                     "lateral (calendar-day rates); Novi figures are the MEDIAN of representative sticks (not a P50, not the "
                     "erebor export's cohort mean); no economics. Curves are previews — nothing is saved in anduin or narvi.</p>")]
    for f in sig.get("flags", []):
        p.append(f'<div class="flag">{_esc(f)}</div>')

    # ---- unit plan + summary of every curve ------------------------------------
    plan = sig.get("unit_plan") or {}
    if plan:
        cls_of = {u: c["planned_lateral_ft"] for c in sig.get("lateral_classes", []) for u in c["units"]}
        p.append("<h2>Unit plan (reviewer)</h2>")
        p.append(_table(["DSU", "Benches evaluated", "Planned lateral ft", "Lateral class ft", "Edited vs seed"],
                        [[name.get(lb, lb), ", ".join(v["benches"]) or "NOT EVALUATED", f"{v['planned_lateral_ft']:,.0f}",
                          f"{cls_of[lb]:,.0f}" if lb in cls_of else "—", "yes" if v["edited"] else "no"]
                         for lb, v in plan.items()]))
    p.append("<h2>Type curves — every bench × lateral class</h2>")
    p.append(_table(["Bench @ class", "TC group", "Pool", "n", "Oil EUR/1,000 ft", "Novi", "Novi n", "TC vs Novi",
                     "Di nom (eff)", "b", "Gas EUR/1,000 ft", "Gas: Novi/TC", "Split test", "QC flags"], _summary_rows(sig)))

    # ---- bench matrix ---------------------------------------------------------
    rows = []
    for key, B in sig["benches"].items():
        for lb, ub in B["units"].items():
            g3 = ub["gate3"]
            loc = f"{g3['n_locations']} ({ub['gate2']['source']})" + (" UPSIDE" if ub.get("role") == "upside" else "")
            if ub.get("row_rules"):
                loc += " · " + "; ".join(ub["row_rules"])
            rows.append([name.get(lb, lb), key, loc, g3["pdp_count_3mi_median"],
                         g3["status"], g3["tvd_excess_3mi_ft_max"], "yes" if ub["has_pdp_in_adjacent_bench"] else "no",
                         next((G["name"] for G in B["tc_groups"] if lb in G["units"]), "—"),
                         "yes" if B["edge_trigger"]["fired"] else "no"])
    p.append("<details><summary>Bench matrix (unit × bench): locations, support, edge</summary>"
             + _table(["Unit", "Bench @ class", "Locations (src)", "pdp_count_3mi med", "Gate 3", "TVD excess max ft",
                       "PDP in adjacent bench", "TC group", "Edge"], rows) + "</details>")
    p.append('<div class="toc">' + " ".join(f'<a href="#{_slug(k)}">{_esc(k)}</a>' for k in sig["benches"]) + "</div>")

    # ---- per bench x class -------------------------------------------------------
    for key, B in sig["benches"].items():
        pool = B["pool"]
        p.append(f'<h2 id="{_slug(key)}">{_esc(key)} <span class="meta">TVD {B["tvd_ft"]:,.0f} ft · spacing {B["spacing_ft"]:,.0f} ft '
                 f'({_esc(B["spacing_source"])}) · basin {_esc(B.get("basin"))}</span></h2>')
        if B.get("class_units"):
            p.append(f'<div class="meta">Units: {_esc(", ".join(name.get(u, u) for u in B["class_units"]))} — planned lateral '
                     f'{B["planned_lateral_ft"]:,.0f} ft centres the lateral band.</div>')
        excl = ", ".join(f"{k} {v}" for k, v in sorted(pool["exclusion_reasons"].items(), key=lambda kv: -kv[1]))
        p.append(f"<div><b>Eligible pool</b> {pool['n_eligible']} wells ({pool['n_excluded']} excluded: {_esc(excl)}). "
                 f"Adjacent planned benches: {_esc(', '.join(pool['adjacent_planned']) or 'none')}; tier order "
                 f"{_esc(' → '.join(pool['tier_order']))} ({_esc(pool['order_reason'])}).</div>")
        for f in pool["flags"]:
            p.append(f'<div class="flag">{_esc(f)}</div>')
        tr = B.get("short_history_transfer")
        if tr:
            if tr.get("error"):
                p.append(f'<div class="flag">Short-history transfer NOT applied: {_esc(tr["error"][:160])}</div>')
            else:
                donors = "; ".join(f"{d['stream']} Di {d['cohort_di']:.2f}/yr ({pct(effective_from_nominal(d['cohort_di'], d['cohort_b']))}) "
                                   f"b {d['cohort_b']:.2f} from {d['donor_count']}" for d in tr["donors"])
                p.append(f"<div class=\"meta\">Short-history transfer (cutoff {tr['cutoff_months']} post-peak months): "
                         f"{tr['n_long']} long wells lent to {tr['n_short']} short ({len(tr['written'])} rewritten, "
                         f"{len(tr['skipped_locked'])} locked kept). Lenders: {_esc(donors)}.</div>")
                if tr.get("flag"):
                    p.append(f'<div class="flag">{_esc(tr["flag"])}</div>')
        cmp_ = B.get("transfer_compare") or {}
        if cmp_.get("flag"):
            p.append(f'<div class="flag bad"><b>{_esc(cmp_["flag"])}</b></div>')
        sp = B["split"]
        p.append(f"<h3>TC granularity: {_esc(sp['recommendation'])} <span class=\"meta\">metric {_esc(sp['metric'])}; "
                 f"median ratio {num(sp['median_ratio'])}, "
                 f"{(_esc(sp['test']) + ' p ' + p_value(sp['p_value'])) if sp.get('test') else 'no rank test'}; "
                 f"gradient {num(sp['gradient_per_mile'], '+,.0f')} per mile (R² {num(sp['gradient_r2'])})</span></h3>")
        if sp["groups"]:
            p.append(_table(["Unit", "Pool wells (assigned to nearest unit)", "Offsets ≤ 1 mi (shared, not exclusive)",
                             "Median EUR/1,000 ft", "Eligible for own TC"],
                            [[name.get(g["unit"], g["unit"]), g["n"], g.get("n_within_1mi"), g["median"], g["eligible"]]
                             for g in sp["groups"]]))
        for n in sp["notes"]:
            p.append(f'<div class="flag">{_esc(n)}</div>')
        if sp.get("reviewer_override"):
            ov = sp["reviewer_override"]
            p.append(f'<div class="flag"><b>Reviewer grouping</b> (test said {_esc(ov["test_said"])}): '
                     f'{_esc(" | ".join(" + ".join(name.get(u, u) for u in c) for c in ov["groups"]))}</div>')
        p.append(f'<div class="row"><img src="map_{_slug(key)}.png" alt="map"></div>')

        for G in B["tc_groups"]:
            gname = G["name"] if G["name"] != "all units" else "all units"
            p.append(f"<h3>TC group: {_esc(', '.join(name.get(u, u) for u in G['units']) if G['name'] != 'all units' else 'all units')}</h3>")
            if G.get("note"):
                p.append(f'<div class="flag">{_esc(G["note"])}</div>')
            p.append(_table(["Tier", "TC wells", "Median Novi EUR/1,000 ft (group pool)"],
                            [[t, G["tier_counts"].get(t, 0), G["tier_medians_novi_eur_per_1000ft"].get(t)] for t in pool["tier_order"]]))
            for f in G["flags"]:
                p.append(f'<div class="flag">{_esc(f)}</div>')
            chart = rate_time_chart(G)
            if chart:
                p.append(chart)
                p.append('<div class="meta">anduin TC = peak_ramp cohort curve per 1,000 ft (smoothed rate incl. terminal decline); '
                         "Novi = 2-segment Arps from the representative-stick MEDIAN parameters (a shape for comparison, "
                         "not a stick's own forecast); terminal decline not shown for Novi.</div>")
            p.append(_table(["Stream", "Source", "qi /1,000 ft (cal-day)", "Di nom /yr", "Di eff yr-1", "b", "EUR /1,000 ft"],
                            _stream_rows(G)))
            wo = _transfer_rows(G)
            if wo:
                p.append(f"<div><b>With vs without short-history transfer</b> — {G.get('n_transferred_in_cohort')} of "
                         f"{len(G['tc_wells'])} cohort wells carry borrowed Di/b (default = with)</div>")
                p.append(_table(["Stream", "TC", "qi /1,000 ft", "Di nom /yr", "Di eff yr-1", "b", "EUR /1,000 ft", "EUR vs without"], wo))
            qc = G.get("qc")
            if qc:
                p.append("<details><summary>Autoforecast QC — cohort per stream + "
                         f"{len(qc['well_flags'])} well flags (flags only, never auto-drop)</summary>")
                p.append(_table(["Stream", "n", "Median Di eff", "IQR eff", "Median Di nom", "Median b", "Cohort flag"],
                                [[k, v["n"], pct(v["de_median"]),
                                  None if v["de_p25"] is None else f"{pct(v['de_p25'])}–{pct(v['de_p75'])}",
                                  v["di_nominal_median"], v["b_median"], v["cohort_flag"] or ("—" if v["flagged"] else "report-only")]
                                 for k, v in qc["streams"].items()]))
                if qc["well_flags"]:
                    p.append(_table(["api10", "Stream", "Flag", "Value", "Threshold"],
                                    [[f["api10"], f["stream"], f["flag"], f["value"], f["threshold"]] for f in qc["well_flags"]]))
                p.append("</details>")
            csv = f"buildup_{_slug(f'{key}_{G['name']}')}.csv"
            p.append(f'<details><summary>Buildup table — {len(G["tc_wells"])} wells (<a href="{_esc(csv)}">{_esc(csv)}</a>)</summary>')
            p.append(_table(BUILDUP_HEADERS, buildup_rows(G["tc_wells"], G.get("anduin_oil") or {})))
            p.append("</details>")
            _ = gname

    # ---- decision log + handoff ---------------------------------------------------
    p.append("<h2>Decision log</h2>")
    p.append(_table(["#", "Gate", "Bench / unit", "Signal", "Decision", "By"],
                    [[i + 1, d["gate"], name.get(d.get("bench"), d.get("bench")), d["signal"], d["decision"], d["by"]]
                     for i, d in enumerate(sig.get("decision_log", []))]))
    p.append("<h2>Handoff</h2><ul><li>anduin TC: preview only — save in anduin after review (the buildup CSV is "
             "<code>included_api10s</code>, minus any wells you cull).</li><li>narvi scenario: generated benches are previews — "
             "build + save the scenario in narvi.</li><li>Forecast to finance: Michael's call per bench.</li></ul>")
    p.append("</body></html>")
    out = run_dir / "dossier.html"
    out.write_text("\n".join(p), encoding="utf-8")
    return out
