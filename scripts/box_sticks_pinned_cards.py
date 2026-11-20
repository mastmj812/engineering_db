"""BOX sticks: review cards for sticks pinned on a same-tag producer that sits 150 to 500 ft off their depth
(docs/box_sticks/pinned-depth-2026-11-20/FINDINGS.md). One card per stick: a strike section orthogonal to the stick
(sign rule v2: reads W -> E for N-S laterals, S -> N for E-W) and a plan view.

READ-ONLY: every query runs in a READ ONLY transaction that is rolled back. Outputs are PNG files and an index.
Planned-survey wells and round-100 depths are never depth evidence: they are drawn in plan view only, never on the section.

    python -m scripts.box_sticks_pinned_cards --list docs/box_sticks/pinned-depth-2026-11-20/sticks_82.csv --out docs/box_sticks/pinned-depth-2026-11-20/cards
"""
from __future__ import annotations

import argparse
import html
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import shapely
from matplotlib.lines import Line2D

from etl.db import get_connection

FT = 3.280839895
HALF_WIDTH_FT = 2640.0          # the section shows wells within this far sideways of the stick
DEPTH_PAD_FT = 900.0
MIN_DEPTH_FT = 4000.0
N_CALIBRATION = 5               # class A and class B cards beside every class C stick
PALETTE = ["#0ea5e9", "#7c3aed", "#16a34a", "#f59e0b", "#db2777", "#2563eb", "#65a30d", "#ea580c", "#0d9488", "#be123c", "#4f46e5", "#a16207", "#0369a1", "#9d174d", "#3f6212", "#7e22ce", "#b45309", "#115e59", "#1e3a8a", "#831843"]

_STICKS = """
SELECT s.set_id, s.location_id, s.basin, s.pad_id, s.formation_blueox AS bench, s.target_tvd_ft, s.tvd_rung, s.flags, s.azimuth_deg, s.well_name,
       extensions.ST_AsText(extensions.ST_Transform(s.legs_geom, 3083)) AS wkt
FROM box.location_stick s JOIN box.location_set t USING (set_id)
WHERE t.is_record AND (s.location_id = ANY (%s) OR s.pad_id = ANY (%s))
"""
_BENCH = """
SELECT b.pad_id, b.formation_blueox AS bench, b.target_tvd_ft, b.tvd_rung, b.two_landings, b.sticks, b.bench_rank, b.no_row_reason
FROM box.location_set_bench b JOIN box.location_set t USING (set_id)
WHERE t.is_record AND b.pad_id = ANY (%s)
"""
_WELLS = """
SELECT DISTINCT ON (s.location_id, e.api10) s.location_id, e.api10::text AS api10, e.well_name, e.current_operator AS operator, e.formation_blueox AS code,
       e.first_production_date AS fp, e.well_status, COALESCE(e.directional_survey_is_planned, FALSE) AS planned, e.tvd_ft, sv.lat_tvd_p50_ft,
       extensions.ST_AsText(extensions.ST_Transform(e.wellstick_geom, 3083)) AS wkt
FROM box.location_stick s JOIN box.location_set t USING (set_id)
JOIN curated.wells_enriched e ON e.is_horizontal AND extensions.ST_GeometryType(e.wellstick_geom) = 'ST_LineString'
 AND extensions.ST_DWithin(e.wellstick_geom::extensions.geography, s.legs_geom::extensions.geography, 850)
LEFT JOIN curated.well_lateral_survey sv ON sv.api10 = e.api10
WHERE t.is_record AND s.location_id = ANY (%s)
"""
_PADS = """
SELECT DISTINCT ON (p.pad_id) p.pad_id, extensions.ST_AsText(extensions.ST_Transform(p.geom, 3083)) AS wkt
FROM raw_novi_intel.pads p JOIN box.location_set t ON t.is_record AND p.report_version = t.dsu_vintage
WHERE p.pad_id = ANY (%s)
"""


def _ro(sql: str, params: tuple) -> pd.DataFrame:
    with get_connection() as conn:
        conn.autocommit = False
        with conn.cursor() as cur:
            cur.execute("SET TRANSACTION READ ONLY")
            cur.execute("SET LOCAL statement_timeout = '600s'")
            cur.execute(sql, params)
            df = pd.DataFrame(cur.fetchall(), columns=[d.name for d in cur.description])
        conn.rollback()
    return df


def evidence_depth(planned: bool, survey_p50: float | None, tvd: float | None) -> float | None:
    """Depth evidence as the tag rule and the generator take it: never a planned survey; the survey lateral median, else
    the header TVD unless it is a round 100; at least 4,000 ft."""
    if planned:
        return None
    if survey_p50 is not None and not pd.isna(survey_p50):
        return float(survey_p50) if float(survey_p50) >= MIN_DEPTH_FT else None
    if tvd is None or pd.isna(tvd) or float(tvd) < MIN_DEPTH_FT or float(tvd) % 100 == 0:
        return None
    return float(tvd)


def section_axis(azimuth_deg: float, direction: np.ndarray) -> tuple[np.ndarray, str]:
    """Unit vector of the + offset direction and the axis label (sign rule v2): for a folded azimuth a <= 45 the section
    reads W -> E, otherwise S -> N. `direction` is the stick's heel -> toe vector in the work CRS."""
    d = direction / np.linalg.norm(direction)
    u = np.array([d[1], -d[0]])                                   # 90 degrees clockwise of the stick
    a = float(azimuth_deg) % 180.0
    if a <= 45.0:
        return (u if u[0] > 0 else -u), "W  ->  E"
    return (u if u[1] > 0 else -u), "S  ->  N"


def offset_ft(line: shapely.LineString, stick: shapely.LineString, mid: np.ndarray, u: np.ndarray) -> float | None:
    """Sideways offset of a well from the stick, measured where the well runs beside it; None when it does not."""
    piece = line.intersection(stick.buffer(HALF_WIDTH_FT / FT, cap_style="flat"))
    if piece.is_empty or piece.length < 0.3 * min(line.length, stick.length):
        return None
    c = piece.centroid
    return float(np.dot(np.array([c.x, c.y]) - mid, u) * FT)


def render(row: pd.Series, n: int, S: pd.DataFrame, B: pd.DataFrame, W: pd.DataFrame, P: dict, out: Path) -> dict:
    me = S[S["location_id"] == row["location_id"]].iloc[0]
    geom = shapely.from_wkt(me["wkt"])
    wells = W[W["location_id"] == me["location_id"]].copy()
    pin = wells[wells["api10"] == str(row["api10"])]
    pin_line = shapely.from_wkt(pin.iloc[0]["wkt"]) if len(pin) else None
    # the section is drawn on the leg the well lies along (a U-turn stick has two)
    stick = min(geom.geoms, key=lambda g: g.distance(pin_line)) if pin_line is not None else max(geom.geoms, key=lambda g: g.length)
    xy = np.array(stick.coords)
    mid = xy.mean(axis=0)
    u, axis = section_axis(me["azimuth_deg"], xy[-1] - xy[0])
    bench = B[B["pad_id"] == me["pad_id"]].dropna(subset=["target_tvd_ft"]).sort_values("target_tvd_ft")
    codes = sorted(set(bench["bench"]) | {me["bench"]} | {c for c in wells["code"] if isinstance(c, str)})   # every tag on the card gets a colour
    col = {c: PALETTE[i % len(PALETTE)] for i, c in enumerate(codes)}
    target = float(me["target_tvd_ft"])
    fig, (ax, pl) = plt.subplots(1, 2, figsize=(15, 7.2), gridspec_kw={"width_ratios": [1.45, 1]})

    # ---- strike section
    ax.axhspan(target - 150, target + 150, color=col[me["bench"]], alpha=0.10, lw=0)
    for b in bench.itertuples():
        if abs(float(b.target_tvd_ft) - target) > DEPTH_PAD_FT - 20:      # outside the section's depth window
            continue
        ax.axhline(float(b.target_tvd_ft), color=col.get(b.bench, "#9ca3af"), lw=1.0, ls="--", alpha=0.8)
        ax.text(HALF_WIDTH_FT * 0.99, float(b.target_tvd_ft) - 12, f"{b.bench} landing {float(b.target_tvd_ft):,.0f} ({b.tvd_rung}, {int(b.sticks)} sticks)",
                ha="right", va="bottom", fontsize=7.5, color=col.get(b.bench, "#6b7280"))
        if b.bench == me["bench"] and b.two_landings is not None:
            for lv in b.two_landings:
                ax.axhline(float(lv), color=col[me["bench"]], lw=0.8, ls=":")
    drawn, plan_only = 0, 0
    subj = None
    for w in wells.itertuples():
        line = shapely.from_wkt(w.wkt)
        x = offset_ft(line, stick, mid, u)
        z = evidence_depth(bool(w.planned), w.lat_tvd_p50_ft, w.tvd_ft)
        is_subj = w.api10 == str(row["api10"])
        c = col.get(w.code, "#9ca3af")
        pl.plot(*np.array(line.coords).T, color="#111827" if is_subj else c, lw=2.4 if is_subj else 1.0, alpha=1.0 if is_subj else 0.75,
                ls="-" if z is not None else ":", zorder=5 if is_subj else 2)
        if x is None or abs(x) > HALF_WIDTH_FT:
            continue
        if z is None:
            plan_only += 1
            continue
        if abs(z - target) > DEPTH_PAD_FT - 20:
            continue
        drawn += 1
        ax.text(x, z - 28, str(w.code), ha="center", va="bottom", fontsize=6.5, color=c, clip_on=True)
        prod = w.fp is not None and not pd.isna(w.fp)
        ax.scatter([x], [z], s=150 if is_subj else 46, marker="o", facecolor=c if prod else "white", edgecolor="#111827" if is_subj else c,
                   linewidth=2.2 if is_subj else 1.2, zorder=6 if is_subj else 3)
        if is_subj:
            subj = (x, z, w)
    others = S[(S["pad_id"] == me["pad_id"]) & (S["location_id"] != me["location_id"])]
    for o in others.itertuples():
        g = shapely.from_wkt(o.wkt)
        for leg in g.geoms:
            pl.plot(*np.array(leg.coords).T, color=col.get(o.bench, "#9ca3af"), lw=0.9, ls="--", alpha=0.6, zorder=1)
            x = offset_ft(leg, stick, mid, u)
            if x is not None and abs(x) <= HALF_WIDTH_FT and abs(float(o.target_tvd_ft) - target) <= DEPTH_PAD_FT - 20:
                ax.scatter([x], [float(o.target_tvd_ft)], s=60, marker="D", facecolor="none", edgecolor=col.get(o.bench, "#9ca3af"), linewidth=1.3, zorder=2)
    ax.scatter([0], [target], s=330, marker="*", facecolor="#facc15", edgecolor="#111827", linewidth=1.4, zorder=7)
    for leg in geom.geoms:                                         # the other leg of a U-turn stick
        if leg is not stick:
            x = offset_ft(leg, stick, mid, u)
            if x is not None and abs(x) <= HALF_WIDTH_FT:
                ax.scatter([x], [target], s=170, marker="*", facecolor="#fde68a", edgecolor="#111827", linewidth=1.0, zorder=6)
    if subj is not None:
        ax.annotate(f"{subj[1] - target:+,.0f} ft", xy=(subj[0], subj[1]), xytext=(subj[0] + 160, (subj[1] + target) / 2), fontsize=10, weight="bold",
                    arrowprops={"arrowstyle": "-", "color": "#111827", "lw": 0.8})
        ax.plot([subj[0], 0], [subj[1], target], color="#111827", lw=0.8, ls=":")
    lo, hi = target - DEPTH_PAD_FT, target + DEPTH_PAD_FT
    ax.set_xlim(-HALF_WIDTH_FT, HALF_WIDTH_FT)
    ax.set_ylim(hi, lo)
    ax.set_xlabel(f"offset from the stick, ft   ({axis})")
    ax.set_ylabel("TVD, ft")
    ax.grid(alpha=0.25)
    ax.set_title("Strike section: wells with depth evidence beside the stick", fontsize=10, loc="left")
    ax.legend(handles=[Line2D([], [], marker="*", ls="", markerfacecolor="#facc15", markeredgecolor="#111827", markersize=15, label="the stick under review (small star: its other leg, U-turn)"),
                       Line2D([], [], marker="o", ls="", markerfacecolor="#9ca3af", markeredgecolor="#111827", markeredgewidth=2, markersize=11, label="the well it is pinned on"),
                       Line2D([], [], marker="o", ls="", markerfacecolor="#9ca3af", markeredgecolor="#9ca3af", markersize=7, label="producing well (colour = its tag)"),
                       Line2D([], [], marker="o", ls="", markerfacecolor="white", markeredgecolor="#9ca3af", markersize=7, label="not yet producing"),
                       Line2D([], [], marker="D", ls="", markerfacecolor="none", markeredgecolor="#9ca3af", markersize=7, label="other BOX stick in the DSU"),
                       Line2D([], [], color="#9ca3af", ls="--", label="bench landing in this DSU"),
                       Line2D([], [], color="#9ca3af", ls=":", label="two landings recorded (this bench)")],
              fontsize=7.5, loc="lower left", framealpha=0.9)

    # ---- plan view
    pad = P.get(int(me["pad_id"]))
    if pad is not None:
        for poly in getattr(pad, "geoms", [pad]):
            pl.plot(*np.array(poly.exterior.coords).T, color="#111827", lw=1.2)
    for leg in geom.geoms:
        pl.plot(*np.array(leg.coords).T, color="#facc15", lw=4.5, solid_capstyle="butt", zorder=4)
        pl.plot(*np.array(leg.coords).T, color="#111827", lw=1.0, ls="--", zorder=6)
    pl.set_aspect("equal")
    pl.set_xticks([])
    pl.set_yticks([])
    pl.set_title("Plan view, north up: stick yellow, its well black", fontsize=10, loc="left")
    pl.legend(handles=[Line2D([], [], color=col[c], lw=2, label=c) for c in codes], fontsize=7.5, loc="best", ncol=2, framealpha=0.9)

    w = subj[2] if subj is not None else None
    name = "" if w is None else f"{w.well_name} ({w.operator}), first production {str(w.fp)[:10]}"
    fig.suptitle(f"Card {n:02d}  |  class {row['class'][0]}  |  location {int(me['location_id'])}  {me['well_name']}  |  {me['basin'].title()}  DSU {int(me['pad_id'])}  |  "
                 f"{me['bench']} at {target:,.0f} ft TVD ({me['tvd_rung']} rung{', U-turn stick' if len(geom.geoms) > 1 else ''})\n"
                 f"Pinned on well {row['api10']}  {name}  |  tagged {me['bench']}, depth {float(row['depth_ft']):,.0f} ft = {float(row['dz']):+,.0f} ft from the stick"
                 + (f"\nNearest other landing: {row['b2']} at {float(row['t2']):,.0f} ft ({float(row['d2']):,.0f} ft from the well)" if row["b2"] != me["bench"] else ""),
                 fontsize=10.5, x=0.01, ha="left")
    fig.subplots_adjust(left=0.06, right=0.99, top=0.83, bottom=0.08, wspace=0.08)
    f = out / f"card_{n:02d}.png"
    fig.savefig(f, dpi=110)
    plt.close(fig)
    return {"card": n, "file": f.name, "class": row["class"], "location_id": int(me["location_id"]), "basin": me["basin"], "pad_id": int(me["pad_id"]),
            "bench": me["bench"], "target_tvd_ft": round(target, 1), "tvd_rung": me["tvd_rung"], "api10": str(row["api10"]), "well_depth_ft": float(row["depth_ft"]),
            "dz_ft": round(float(row["dz"]), 1), "nearest_other_bench": row["b2"], "stick_legs": len(geom.geoms), "wells_on_section": drawn, "wells_plan_only_no_depth": plan_only,
            "subject_on_section": subj is not None}


def choose(listed: pd.DataFrame) -> pd.DataFrame:
    """Every class C stick, and the first N_CALIBRATION class A and class B sticks by location id, in location-id order."""
    k = listed["class"].str[0]
    pick = pd.concat([listed[k == "C"], listed[k == "A"].sort_values("location_id").head(N_CALIBRATION),
                      listed[k == "B"].sort_values("location_id").head(N_CALIBRATION)])
    return pick.sort_values("location_id").reset_index(drop=True)


def write_index(rows: list[dict], out: Path) -> None:
    body = "".join(
        f"<section id='c{r['card']}'><h2>Card {r['card']:02d} &middot; class {html.escape(r['class'][0])} &middot; {html.escape(r['bench'])} &middot; "
        f"location {r['location_id']} &middot; well {r['dz_ft']:+,.0f} ft</h2><img src='{r['file']}' alt='card {r['card']}'></section>" for r in rows)
    (out / "index.html").write_text(
        "<!doctype html><meta charset='utf-8'><title>Pinned-depth cards</title><style>body{font:14px system-ui;margin:16px;max-width:1700px}"
        "img{width:100%;border:1px solid #d1d5db}h2{font-size:15px;margin:22px 0 6px}</style>"
        "<h1>Sticks pinned on a same-tag producer 150 to 500 ft off their depth</h1>"
        "<p>For each card: is the yellow stick a real, undrilled location? <b>KEEP</b> = yes. <b>REMOVE</b> = no: it is really the well it is pinned on (same well), or the operator's staggered pattern leaves that slot empty on purpose (slot taken). "
        "Class A = two landings recorded in the DSU; B = the well sits at another bench's landing; C = neither.</p>" + body, encoding="utf-8")


def run(listed: pd.DataFrame, out: Path) -> pd.DataFrame:
    out.mkdir(parents=True, exist_ok=True)
    pick = choose(listed)
    ids, pads = [int(x) for x in pick["location_id"]], sorted({int(x) for x in pick["pad_id"]})
    S = _ro(_STICKS, (ids, pads))
    B = _ro(_BENCH, (pads,))
    W = _ro(_WELLS, (ids,))
    P = {int(r.pad_id): shapely.from_wkt(r.wkt) for r in _ro(_PADS, (pads,)).itertuples()}
    rows = [render(r, i + 1, S, B, W, P, out) for i, r in pick.iterrows()]
    idx = pd.DataFrame(rows)
    idx.to_csv(out / "cards.csv", index=False)
    write_index(rows, out)
    return idx


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--list", type=Path, required=True)
    ap.add_argument("--out", type=Path, required=True)
    a = ap.parse_args(argv)
    idx = run(pd.read_csv(a.list, dtype={"api10": str}), a.out)
    print(idx.groupby("class").size().to_string(), f"\n{len(idx)} cards; subject on section {int(idx['subject_on_section'].sum())}", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
