"""BOX sticks phase 3a, step 3: the review surface. One rendered card per DSU: plan view and gunbarrel (sign rule v2,
offsets plotted as stored) with existing wells, BOX sticks, rows not placed with their reason, and the remaining Novi
sticks; a per-bench table with spacing and its basis, landing depth and its rung, and counts BOX against Novi.
Planned-survey wells are drawn in plan view only, never on the gunbarrel.

Read-only: inputs are the phase 3 cache frame; outputs are PNG files and an index. Nothing is written to the warehouse.

    python -m scripts.box_sticks_phase3_cards --out docs/box_sticks/phase3a-2026-11-14/cards --cache <cache>
"""
from __future__ import annotations

import argparse
import html
from collections import Counter
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import shapely
from matplotlib.lines import Line2D
from narvi import placement as npl

from box.sticks import core, reads
from scripts import box_sticks_phase3_pilot as p3

FT = core.FT_PER_M
REASON_STYLE = {"envelope_same_landing": ("#dc2626", "same landing, within 400 ft"), "envelope_stacked": ("#ea580c", "stacked, within 300 ft"),
                "no_depth_neighbour": ("#9333ea", "well with no depth, same family"),
                "uturn_unpaired": ("#92400e", "U-turn leg with no partner"), "setback_clip": ("#111827", "outside the clear width"),
                "short_lateral": ("#6b7280", "under 7,000 ft"), "setback_fit": ("#111827", "row count reduced to fit")}
SHORT = {"envelope_same_landing": "same", "envelope_stacked": "stacked", "no_depth_neighbour": "no-depth", "uturn_unpaired": "unpaired",
         "setback_clip": "clip", "short_lateral": "short", "setback_fit": "fit"}
BENCH_WHY = {"sliver": "under 10 % of DSU in extent", "no_depth": "no landing depth", "wca_one_member": "one WCA row set (other member)",
             "wca_one_landing": "WCA surfaces under 75 ft apart", "reconciled_out": "depth conflict, less trusted", "no_window": "no drillable window",
             "no_rows": "no row fits"}
PALETTE = ["#0ea5e9", "#7c3aed", "#dc2626", "#16a34a", "#f59e0b", "#db2777", "#2563eb", "#65a30d", "#ea580c", "#0d9488", "#a3a3a3", "#be123c", "#4f46e5",
           "#854d0e"]
NAMED = {10785: "Ruthless 11 Federal COM", 11331: "NM pad on planned surveys", 10809: "U-turn; a carried WCA_1 depth knocks out BS3", 22309: "young LSSH + WCA_1 cube, DEAN",
         18898: "DEAN between LSSH and WCA_1 on different spacings", 22308: "two-landing WCA_1", 12620: "five spuds, permit depths", 12638: "co-developed WCA, wide spacing",
         12613: "BS3_C and BS3_S both developed", 12627: "near-square, neighbours not coherent", 12639: "sliver of the WCXY extent", 22314: "sliver of the WCB_2 extent"}


def xy_ft(g, o) -> np.ndarray:
    c = shapely.get_coordinates(g)
    return (c - np.array([o.x, o.y])) * FT


def render(ctx: reads.Context, pid: int, cases: list[str], out: Path, link, cfgs: dict) -> dict:
    d = ctx.dsu(pid)
    res = core.generate_dsu(d, cfgs[d.basin], link)
    az, o = res.meta["azimuth_grid_deg"], d.polygon.centroid
    order = sorted(d.benches, key=lambda b: b.rank)
    color = {b.code: PALETTE[k % len(PALETTE)] for k, b in enumerate(order)}

    def gb(g) -> float:
        m = g.interpolate(0.5, normalized=True)
        return npl.gunbarrel_offset_ft((m.x, m.y), az, (o.x, o.y))

    F = ctx.F
    sm = F["sm"][F["sm"]["pad_id"] == pid]
    novi = F["sticks"].iloc[sm["i"].to_numpy()]
    novi = novi[novi["remaining"].to_numpy(bool)]
    novi_g = [ctx.work(g) for g in novi["geom"]]

    fig = plt.figure(figsize=(17, 11.5))
    gs = fig.add_gridspec(2, 2, height_ratios=[2.15, 1.0], width_ratios=[1.0, 1.25], hspace=0.3, wspace=0.12)
    ax, bx, tx = fig.add_subplot(gs[0, 0]), fig.add_subplot(gs[0, 1]), fig.add_subplot(gs[1, :])

    # ---- plan view
    ax.plot(*xy_ft(d.polygon.exterior, o).T, color="k", lw=1.6)
    win = npl.drillable_window(d.polygon, cfgs[d.basin].setback_ft)
    for part in getattr(win, "geoms", [win]):
        if not part.is_empty:
            ax.plot(*xy_ft(part.exterior, o).T, color="#9ca3af", lw=0.8, ls="--")
    for g in novi_g:
        ax.plot(*xy_ft(g, o).T, color="#a16207", lw=0.9, ls=(0, (1, 2)), alpha=0.8)
    for w in d.wells:
        c = color.get(w.code, "#6b7280")
        ls = "--" if w.planned else (":" if w.status != "producer" else "-")
        ax.plot(*xy_ft(w.line, o).T, color=c, lw=1.1 if w.member else 0.7, ls=ls, alpha=0.95 if w.member else 0.45)
    for r in res.ledger:
        if r["status"] == "culled" and r["heel_xy"]:
            p = (np.array([r["heel_xy"], r["toe_xy"]]) - np.array([o.x, o.y])) * FT
            ax.plot(*p.T, color=REASON_STYLE[r["reason"]][0], lw=0.6, ls=(0, (4, 4)), alpha=0.55)
    for s in res.sticks:
        for leg in s["legs"]:
            p = (np.array([leg["heel_xy"], leg["toe_xy"]]) - np.array([o.x, o.y])) * FT
            ax.plot(*p.T, color=color[s["bench"]], lw=2.6, solid_capstyle="butt", path_effects=None)
        if s["turn"]:
            ax.plot(*((np.array(s["turn"]["arc_xy"]) - np.array([o.x, o.y])) * FT).T, color=color[s["bench"]], lw=1.4)
    ext = xy_ft(d.polygon.exterior, o)
    ax.set_xlim(ext[:, 0].min() - 900, ext[:, 0].max() + 900)
    ax.set_ylim(ext[:, 1].min() - 900, ext[:, 1].max() + 900)
    ax.set_aspect("equal")
    ax.set_title("Plan view (ft from the DSU centre, grid north up)", fontsize=10)
    ax.tick_params(labelsize=8)
    ax.legend(handles=[Line2D([], [], color="k", lw=2.6, label="BOX stick (bench colour)"), Line2D([], [], color="k", lw=1.1, label="producer"),
                       Line2D([], [], color="k", lw=1.1, ls="--", label="producer on a planned survey"), Line2D([], [], color="k", lw=1.1, ls=":", label="spud / DUC / completed"),
                       Line2D([], [], color="#a16207", lw=0.9, ls=(0, (1, 2)), label="Novi stick (remaining)"),
                       Line2D([], [], color="#6b7280", lw=0.6, ls=(0, (4, 4)), label="row not placed (reason colour)")], fontsize=7, loc="upper center", bbox_to_anchor=(0.5, -0.05), ncol=3, framealpha=0.9)

    # ---- gunbarrel
    ring = xy_ft(d.polygon.exterior, o) / FT + np.array([o.x, o.y])
    offs = [npl.gunbarrel_offset_ft(tuple(p), az, (o.x, o.y)) for p in ring]
    lo, hi = min(offs), max(offs)
    bx.axvspan(lo, hi, color="#f3f4f6", zorder=0)
    for v in (lo + 330, hi - 330):
        bx.axvline(v, color="#9ca3af", lw=0.8, ls="--", zorder=1)
    tv = {b["code"]: b["target_tvd_ft"] for b in res.benches if not pd.isna(b.get("target_tvd_ft", np.nan))}
    for code, z in tv.items():
        bx.axhline(z, color=color[code], lw=0.6, alpha=0.5, zorder=1)
        bx.text(hi + 60, z, code, color=color[code], fontsize=8, va="center")
    zs = list(tv.values())
    for w in d.wells:
        if w.depth_ft is None or w.planned:
            continue                                     # no depth evidence: plan view only
        x = gb(w.line)
        if lo - 800 <= x <= hi + 800:
            zs.append(w.depth_ft)
            bx.scatter(x, w.depth_ft, s=42 if w.member else 26, marker="o" if w.status == "producer" else "D",
                       facecolors=color.get(w.code, "#6b7280") if w.member else "none", edgecolors=color.get(w.code, "#6b7280"), linewidths=1.0, zorder=4)
    z_lo, z_hi = (min(zs) - 200, max(zs) + 200) if zs else (0.0, 1.0)
    off_scale = 0
    for g, z in zip(novi_g, novi["tvd"].to_numpy(float)):
        if np.isfinite(z) and not z_lo <= z <= z_hi:
            off_scale += 1
        elif np.isfinite(z):
            bx.scatter(gb(g), z, s=30, marker="^", facecolors="none", edgecolors="#a16207", linewidths=0.9, zorder=3)
    for r in res.ledger:
        if r["status"] == "culled" and r["gunbarrel_x_ft"] is not None:
            bx.scatter(r["gunbarrel_x_ft"], r["target_tvd_ft"], s=34, marker="x", color=REASON_STYLE[r["reason"]][0], linewidths=1.2, zorder=5)
    for s in res.sticks:
        xs_ = [leg["gunbarrel_x_ft"] for leg in s["legs"]]
        bx.scatter(xs_, [s["target_tvd_ft"]] * len(xs_), s=70, marker="s", facecolors=color[s["bench"]], edgecolors="k", linewidths=1.1, zorder=6)
        if len(xs_) == 2:
            bx.plot(xs_, [s["target_tvd_ft"]] * 2, color="k", lw=1.0, zorder=5)
    bx.set_ylim(z_hi, z_lo)
    if off_scale:
        bx.text(0.995, 0.005, f"{off_scale} Novi sticks off the depth scale", transform=bx.transAxes, ha="right", va="bottom", fontsize=7, color="#a16207")
    bx.set_xlim(lo - 400, hi + 700)
    plus = npl.plus_offset_bearing_deg(az)
    bx.set_xlabel(f"gunbarrel offset, ft (+ toward {plus:.0f} deg; sign rule v2)", fontsize=9)
    bx.set_ylabel("TVD, ft", fontsize=9)
    bx.set_title("Gunbarrel (wells with depth evidence only)", fontsize=10)
    bx.tick_params(labelsize=8)
    used = sorted({r["reason"] for r in res.ledger if r["status"] == "culled" and r["gunbarrel_x_ft"] is not None})
    bx.legend(handles=[Line2D([], [], marker="s", ls="", mfc="w", mec="k", ms=8, label="BOX leg (U-turn legs joined)"),
                       Line2D([], [], marker="o", ls="", mfc="k", mec="k", ms=6, label="producer in the DSU"),
                       Line2D([], [], marker="o", ls="", mfc="none", mec="k", ms=5, label="producer outside the DSU"),
                       Line2D([], [], marker="D", ls="", mfc="k", mec="k", ms=5, label="spud / DUC / completed"),
                       Line2D([], [], marker="^", ls="", mfc="none", mec="#a16207", ms=6, label="Novi stick (remaining)")]
              + [Line2D([], [], marker="x", ls="", color=REASON_STYLE[k][0], ms=6, label="not placed: " + REASON_STYLE[k][1]) for k in used],
              fontsize=7, loc="upper center", bbox_to_anchor=(0.5, -0.08), ncol=3, framealpha=0.9)

    # ---- per-bench table
    tx.axis("off")
    prod = Counter(w.code for w in d.wells if w.member and w.status == "producer")
    pre = Counter(w.code for w in d.wells if w.member and w.status != "producer")
    nov = Counter(novi["code"])
    binp = {b.code: b for b in d.benches}
    rows = []
    for b in sorted(res.benches, key=lambda r: binp[r["code"]].rank):
        code, bi = b["code"], binp[b["code"]]
        cul = Counter(r["reason"] for r in res.ledger if r["code"] == code and r["status"] == "culled")
        if b["no_row_reason"] and not b["rows_considered"]:
            rows.append([code, "-", "-", "-", "0", "-", str(nov.get(code, 0)), f"{prod.get(code, 0)} / {pre.get(code, 0)}", BENCH_WHY.get(b["no_row_reason"], b["no_row_reason"])])
            continue
        sb = bi.spacing_basis
        shift = f", moved {b['reconciled_shift_ft']:+.0f}" if abs(b["reconciled_shift_ft"]) > 0.5 else ""
        err = "" if bi.tvd_err_median_ft is None else f" (held-out {bi.tvd_err_median_ft:.0f} / P90 {bi.tvd_err_p90_ft:.0f})"
        sp = f"{b['spacing_map_ft']:.0f}" + ("" if abs(b["spacing_final_ft"] - b["spacing_map_ft"]) < 0.5 else f" -> {b['spacing_final_ft']:.0f}")
        basis = f"n_eff {sb.get('n_eff', 0):.0f}, {sb.get('band', '')}" + (f", as {b['shared_with']}" if b["shared_with"] else "")
        note = ", ".join(x.replace("_", " ") for x in (b["flags"] if isinstance(b["flags"], str) else "").split(";") if x)
        rows.append([code, f"{b['target_tvd_ft']:,.0f} {b['rung']}{shift}{err}", f"{sp}; {basis}", b["grid"] + (" (pinned)" if b["pinned"] and b["grid"] != "pinned" else ""),
                     f"{b['legs_placed']} / {b.get('sticks', 0)}", ", ".join(f"{n} {SHORT[k]}" for k, n in sorted(cul.items())) or "-", str(nov.get(code, 0)),
                     f"{prod.get(code, 0)} / {pre.get(code, 0)}", note])
    cols = ["Bench", "Landing TVD ft, rung (error ft)", "Spacing ft, map -> final; basis", "Row grid", "BOX legs/sticks", "Rows not placed", "Novi left", "Prod / not yet", "Note"]
    t = tx.table(cellText=rows, colLabels=cols, loc="upper center", cellLoc="left", colWidths=[0.045, 0.2, 0.16, 0.07, 0.065, 0.17, 0.045, 0.065, 0.18])
    t.auto_set_font_size(False)
    t.set_fontsize(7.5)
    t.scale(1, 1.18)
    for (i, _), cell in t.get_celld().items():
        cell.set_edgecolor("#d1d5db")
        if i == 0:
            cell.set_facecolor("#e5e7eb")
            cell.set_text_props(weight="bold")
    for i, r in enumerate(rows, 1):
        t[(i, 0)].get_text().set_color(color[r[0]])
        t[(i, 0)].get_text().set_weight("bold")

    n_legs = sum(s["n_legs"] for s in res.sticks)
    kind = "U-turn" if res.meta.get("well_type") == "uturn" else "straight"
    fig.suptitle(f"DSU {pid}  |  {d.basin}  |  {', '.join(cases)}\n"
                 f"{kind} (longest row {res.meta.get('straight_ft', 0):,.0f} ft)  |  azimuth {az:.1f} deg grid, {res.meta['azimuth_true_deg']:.1f} true, from {d.az_basis}"
                 f"  |  clear width {res.meta.get('clear_width_ft') or 0:,.0f} of {res.meta.get('window_width_ft', 0):,.0f} ft"
                 + (f"  |  WCA: {d.wca_class}" if d.wca_class else "")
                 + f"\nBOX {len(res.sticks)} sticks ({n_legs} legs, {sum(s['completed_lateral_ft'] for s in res.sticks):,.0f} ft)  vs  Novi {len(novi)} remaining sticks"
                 f" ({float(novi['ll_ft'].sum()):,.0f} ft)  |  producers in DSU {sum(prod.values())}, not yet producing {sum(pre.values())}"
                 f"  |  live tags pulled {ctx.F['pulled']}  |  {core.VERSION}", fontsize=10.5, y=0.985)
    name = f"card_{d.basin}_{pid}.png"
    fig.savefig(out / name, dpi=90, bbox_inches="tight")
    plt.close(fig)
    return {"pdp": pdp_list(ctx, d, pid), "area": ctx.area.get(pid, "outside the pilot blocks"),
            "card": name, "pad_id": pid, "basin": d.basin, "cases": "; ".join(cases), "well_type": kind, "box_sticks": len(res.sticks), "box_legs": n_legs,
            "novi_remaining": len(novi), "producers": int(sum(prod.values())), "benches_with_sticks": len({s["bench"] for s in res.sticks}),
            "benches_no_row": sum(1 for b in res.benches if not b["legs_placed"])}


def pdp_list(ctx: reads.Context, d: core.Dsu, pid: int) -> list[dict]:
    """Existing producers to look the area up by (api10): every producer in the DSU, or the nearest one outside it."""
    u = ctx.F["u"]
    name = dict(zip(u["api10"].astype(str), u["well_name"].fillna("")))
    got = [{"api10": w.well_id, "bench": w.code or "", "well_name": name.get(w.well_id, ""), "where": "in the DSU",
            "planned": w.planned} for w in d.wells if w.member and w.status == "producer"]
    if got:
        return sorted(got, key=lambda r: (r["bench"], r["api10"]))
    ix, tree = ctx.tree[("producer", d.basin)]
    poly = ctx.pads.loc[pid, "geom"]
    i = ix[tree.nearest(poly)]
    dist = shapely.distance(poly, u["geom"].to_numpy()[i]) * FT
    return [{"api10": str(u["api10"].to_numpy()[i]), "bench": str(u["live"].to_numpy()[i]), "well_name": str(u["well_name"].to_numpy()[i]),
             "where": (f"nearest producer, {dist:,.0f} ft outside the DSU" if dist >= 1.0 else "nearest producer, crosses the DSU with under 30 % of its lateral inside"),
             "planned": False}]


CSS = """
:root{--bg:#f8fafc;--fg:#0f172a;--mut:#475569;--card:#ffffff;--line:#cbd5e1;--acc:#1d4ed8}
@media (prefers-color-scheme: dark){:root{--bg:#0b1220;--fg:#e2e8f0;--mut:#94a3b8;--card:#111a2e;--line:#334155;--acc:#93c5fd}}
*{box-sizing:border-box}body{margin:0;padding:16px;background:var(--bg);color:var(--fg);font:15px/1.45 system-ui,Segoe UI,sans-serif}
main{max-width:1500px;margin:0 auto}h1{font-size:22px;margin:0 0 4px}h2{font-size:17px;margin:0 0 4px}p{margin:4px 0}
.mut{color:var(--mut)}a{color:var(--acc)}table{border-collapse:collapse;width:100%;font-size:13.5px}
th,td{border-bottom:1px solid var(--line);padding:4px 8px;text-align:left;vertical-align:top}.wrap{overflow-x:auto}
section{background:var(--card);border:1px solid var(--line);border-radius:8px;padding:14px;margin:18px 0}
section img{width:100%;height:auto;background:#fff;border-radius:4px;margin-top:8px}
code{font:13px ui-monospace,Consolas,monospace;user-select:all}.api{display:flex;flex-wrap:wrap;gap:4px 18px;margin:6px 0}
details{margin:4px 0}summary{cursor:pointer;color:var(--acc)}
"""


def write_html(rows: list[dict], out: Path, ctx: reads.Context) -> None:
    e = html.escape

    def first_per_bench(pdp: list[dict]) -> list[dict]:
        seen, keep = set(), []
        for r in pdp:
            if r["bench"] not in seen:
                seen.add(r["bench"])
                keep.append(r)
        return keep

    def api(r: dict) -> str:
        return (f"<span><code>{e(r['api10'])}</code> {e(r['bench'])} <span class='mut'>{e(r['well_name'])}"
                + (" (planned survey)" if r["planned"] else "") + "</span></span>")

    toc, body = [], []
    for r in rows:
        lead = first_per_bench(r["pdp"])
        where = r["pdp"][0]["where"]
        toc.append(f"<tr><td><a href='#d{r['pad_id']}'>{r['pad_id']}</a></td><td>{e(r['area'])}</td><td>{e(r['cases'])}</td><td>{r['well_type']}</td>"
                   f"<td>{r['box_sticks']} ({r['box_legs']})</td><td>{r['novi_remaining']}</td><td>{r['producers']}</td><td><code>{e(lead[0]['api10'])}</code></td></tr>")
        more = (f"<details><summary>All {len(r['pdp'])} producers in the DSU</summary><div class='api'>{''.join(api(x) for x in r['pdp'])}</div></details>"
                if len(r["pdp"]) > len(lead) else "")
        body.append(f"<section id='d{r['pad_id']}'><h2>DSU {r['pad_id']} &middot; {e(r['basin'])} &middot; {e(r['cases'])}</h2>"
                    f"<p class='mut'>{e(r['area'])} &middot; {r['well_type']} &middot; BOX {r['box_sticks']} sticks ({r['box_legs']} legs) against "
                    f"{r['novi_remaining']} remaining Novi sticks &middot; {r['producers']} producers in the DSU</p>"
                    f"<p><b>Existing PDP to look up in anduin (API 10)</b>, {e(where)}"
                    + (", one per bench" if len(lead) > 1 else "") + f":</p><div class='api'>{''.join(api(x) for x in lead)}</div>{more}"
                    f"<a href='{e(r['card'])}'><img loading='lazy' src='{e(r['card'])}' alt='Review card for DSU {r['pad_id']}'></a>"
                    "<p><a href='#top'>Back to the list</a></p></section>")
    page = (f"<!doctype html><html lang='en'><head><meta charset='utf-8'><meta name='viewport' content='width=device-width,initial-scale=1'>"
            f"<title>BOX sticks review cards</title><style>{CSS}</style></head><body><main id='top'><h1>BOX sticks phase 3a: review cards</h1>"
            f"<p class='mut'>{len(rows)} DSUs &middot; live tags pulled {e(str(ctx.F['pulled']))} &middot; generator {e(core.VERSION)} &middot; nothing here is stored "
            "in the warehouse. Each card names existing producers by API 10 so the area can be opened in anduin. Click a card to open it full size.</p>"
            "<div class='wrap'><table><thead><tr><th>DSU</th><th>Area</th><th>Case</th><th>Well type</th><th>BOX sticks (legs)</th><th>Novi remaining</th>"
            f"<th>Producers</th><th>A PDP API 10</th></tr></thead><tbody>{''.join(toc)}</tbody></table></div>{''.join(body)}</main></body></html>")
    (out / "index.html").write_text(page, encoding="utf-8", newline=chr(10))


def choose(ctx: reads.Context) -> dict[int, list[str]]:
    """About 30 pilot DSUs covering the cases of the brief, then six single DSUs outside the blocks."""
    F = ctx.F
    t = p3.dsu_table(F).set_index("pad_id")
    area = {int(p): name for name, a in p3.AREAS.items() for p in p3.area_pads(F, a)}
    bw = p3.bench_wells(F).pivot_table(index="pad_id", columns="code", values="wells", aggfunc="sum").fillna(0)
    two = {p for p, _ in ctx.two}
    db = F["db"]
    carried = db[db["rung"].isin(["thickness", "bracket", "offset"])].groupby("pad_id").size()
    picks: dict[int, list[str]] = {}

    def add(pid: int, case: str) -> None:
        picks.setdefault(int(pid), [])
        if case not in picks[int(pid)]:
            picks[int(pid)].append(case)

    for pid, why in NAMED.items():
        add(pid, why)
    for name in p3.AREAS:
        g = t.loc[[p for p in area if area[p] == name]].sort_index()
        short = name.split("_")[1].upper() if name.startswith("delaware") else "Midland"

        def take(mask, case, n, g=g, short=short):
            for pid in [p for p in g.index[mask] if p not in picks][:n]:
                add(pid, f"{short}: {case}")

        take((g["producers"] == 0) & (g["preprod"] == 0), "clean undeveloped", 2)
        take((g["producers"] >= 1) & (g["producers"] <= 4), "partly developed", 2)
        take(g["well_type"] == "uturn", "U-turn", 1)
        take(g["square"], "near-square", 1)
        take(g.index.isin(two), "two-landing bench", 1)
        take(g.index.map(lambda p: carried.get(p, 0)) >= 0.5 * g["benches"], "mostly carried landing depths", 1)
        if name.startswith("midland"):
            cube = (g.index.map(lambda p: bw["LSSH"].get(p, 0)) >= 2) & (g.index.map(lambda p: bw["WCA_1"].get(p, 0)) >= 2) & (g.index.map(lambda p: bw["DEAN"].get(p, 0)) == 0)
            take(cube, "developed LSSH + WCA_1 cube, no DEAN well", 2)
        if "nm" in name:
            take(g["producers_planned"] >= 3, "producers on planned surveys", 1)
    # six outside the blocks: cards only, not counted in any bar
    out_ = t[~t.index.isin(area)]
    out_ = out_[(out_["benches"] - out_["no_depth"]) >= 3]                    # a card with no landing depth on any bench shows nothing
    size = ctx.rg.CELL_MI * ctx.rg.MI
    gz, tree = ctx.az_tree["delaware"]

    def county(r) -> str:
        return str(gz["county"].to_numpy()[tree.nearest(shapely.Point(r["cx"], r["cy"]))])

    ew = [p for p, r in out_[(out_["basin"] == "delaware") & out_["square"] & (out_["producers"] == 0) & (out_["benches"] >= 3)].iterrows()
          if (c := ctx.cell.get(("delaware", int(np.floor(r["cx"] / size)), int(np.floor(r["cy"] / size))))) and c[1] >= 10 and core.axial_dist(c[0], 90.0) <= 22.5 and county(r) == "Eddy"]
    for pid in ew[:2]:
        add(pid, "extra: Eddy near-square in the E-W area")
    for pid in [p for p in out_.index if ctx.wca.get(p, {}).get("cls") == "no control" and out_.loc[p, "benches"] >= 4][:2]:
        add(pid, "extra: WCA no-control fringe")
    for pid in out_[(out_["basin"] == "midland") & (out_["well_type"] == "uturn") & (out_["producers"] >= 1) & (out_["benches"] >= 4)].index[:2]:
        add(pid, "extra: Midland U-turn")
    return picks


def run(out: Path, cache: Path, pads: list[int] | None) -> pd.DataFrame:
    ctx = reads.Context(cache)
    link = reads.link_fn()
    cfgs = {b: reads.default_cfg(b) for b in ("delaware", "midland")}
    ctx.area = {int(p): name for name, a in p3.AREAS.items() for p in p3.area_pads(ctx.F, a)}
    picks = choose(ctx) if not pads else {p: [NAMED.get(p, "requested")] for p in pads}
    out.mkdir(parents=True, exist_ok=True)
    rows = [render(ctx, pid, cases, out, link, cfgs) for pid, cases in sorted(picks.items())]
    idx = pd.DataFrame(rows)
    idx["pdp_api10"] = [" ".join(sorted({x["api10"] for x in r["pdp"]})) for r in rows]
    idx["pdp_where"] = [r["pdp"][0]["where"] for r in rows]
    idx = idx.drop(columns="pdp")
    if not pads:
        write_html(sorted(rows, key=lambda r: (r["area"], r["pad_id"])), out, ctx)
        idx.to_csv(out / "cards_index.csv", index=False)
        lines = ["# BOX sticks phase 3a: review cards", "",
                 f"{len(idx)} cards. Live tags pulled {ctx.F['pulled']}; generator {core.VERSION}. Cards marked `extra` are outside the pilot blocks and count in no bar.", "",
                 "| Card | Basin | DSU | Cases | Well type | BOX sticks (legs) | Novi remaining | Producers |", "|---|---|---|---|---|---|---|---|"]
        lines += [f"| [{r.card}]({r.card}) | {r.basin} | {r.pad_id} | {r.cases} | {r.well_type} | {r.box_sticks} ({r.box_legs}) | {r.novi_remaining} | {r.producers} |" for r in idx.itertuples()]
        (out / "README.md").write_text("\n".join(lines) + "\n", encoding="utf-8", newline="\n")
    print(idx.to_string(index=False))
    return idx


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", required=True, type=Path)
    ap.add_argument("--cache", required=True, type=Path)
    ap.add_argument("--pads", default="")
    a = ap.parse_args(argv)
    run(a.out, a.cache, [int(x) for x in a.pads.split(",") if x] or None)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
