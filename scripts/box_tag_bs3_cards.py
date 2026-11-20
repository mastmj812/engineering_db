"""Review cards for the Delaware Bone Spring mistag classes (docs/box_sticks/pinned-depth-2026-11-20/TAG_TWO_WITNESS.md).
One card per well: a strike section orthogonal to its lateral (sign rule v2) with the neighbouring wells by tag, the
geologist's gridded tops at the well, and the local WCA_1 control; and a plan view.

READ-ONLY: every query runs in a READ ONLY transaction that is rolled back. Nothing is re-tagged here; the tag rule, its
tables and its seeds are not read for writing or touched. Planned-survey wells and round-100 depths are never drawn on the
section. The grids are a witness, not a verdict (Michael 2026-11-20).

    python -m scripts.box_tag_bs3_cards --list docs/box_sticks/pinned-depth-2026-11-20/tag_two_witness_delaware.csv --out docs/box_sticks/pinned-depth-2026-11-20/tag_cards
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

from scripts.box_sticks_pinned_cards import (
    HALF_WIDTH_FT,
    PALETTE,
    _ro,
    evidence_depth,
    offset_ft,
    section_axis,
)

DEPTH_PAD_FT = 1100.0
SURFACES = (("g_2BSPGS", "grid: top BS2_S"), ("g_3BSPGC", "grid: top BS3_C"), ("g_3BSPGS", "grid: top BS3_S"), ("g_WOLFCAMP_XY", "grid: top WCXY"),
            ("g_WOLFCAMP_A", "grid: top WCA"))
INTERVAL = {"BS2_S": ("g_2BSPGS", "g_3BSPGC"), "BS3_C": ("g_3BSPGC", "g_3BSPGS"), "BS3_S": ("g_3BSPGS", "g_WOLFCAMP_XY")}
# (group label, filter on the list, cards): the strong class first, then the two groups where the witnesses disagree
GROUPS = (("S: BS3_S tag, both witnesses say BS3_C", lambda d: (d["cls"] == "both witnesses, same answer") & (d["tag"] == "BS3_S") & (d["g_int"] == "BS3_C"), 24),
          ("H: BS2_S tag, height says lower, grid says BS2_S", lambda d: (d["cls"] == "height only") & (d["tag"] == "BS2_S"), 6),
          ("G: BS3_S tag, grid says another bench, height says BS3_S", lambda d: (d["cls"] == "grid only") & (d["tag"] == "BS3_S"), 6))

_SUBJ = """
SELECT e.api10::text AS api10, e.well_name, e.current_operator AS operator, e.county, e.first_production_date AS fp, e.formation_blueox AS code,
       extensions.ST_AsText(extensions.ST_Transform(e.wellstick_geom, 3083)) AS wkt
FROM curated.wells_enriched e WHERE e.api10::text = ANY (%s)
"""
_NEAR = """
SELECT DISTINCT ON (s.api10, e.api10) s.api10::text AS subject, e.api10::text AS api10, e.well_name, e.formation_blueox AS code, e.first_production_date AS fp,
       COALESCE(e.directional_survey_is_planned, FALSE) AS planned, e.tvd_ft, sv.lat_tvd_p50_ft,
       extensions.ST_AsText(extensions.ST_Transform(e.wellstick_geom, 3083)) AS wkt
FROM curated.wells_enriched s
JOIN curated.wells_enriched e ON e.is_horizontal AND extensions.ST_GeometryType(e.wellstick_geom) = 'ST_LineString'
 AND extensions.ST_DWithin(e.wellstick_geom::extensions.geography, s.wellstick_geom::extensions.geography, 850)
LEFT JOIN curated.well_lateral_survey sv ON sv.api10 = e.api10
WHERE s.api10::text = ANY (%s)
"""


def choose(listed: pd.DataFrame) -> pd.DataFrame:
    """Evenly spaced through each group ordered by county then API: no hand-picking."""
    out = []
    for label, test, n in GROUPS:
        g = listed[test(listed)].sort_values(["county", "api10"]).reset_index(drop=True)
        idx = sorted({round(float(i)) for i in np.linspace(0, len(g) - 1, min(n, len(g)))})
        out.append(g.iloc[idx].assign(group=label, group_size=len(g)))
    return pd.concat(out, ignore_index=True)


def lateral(line: shapely.LineString) -> shapely.LineString:
    """The well line without a surface step-out first vertex (three or more points)."""
    c = list(line.coords)
    return shapely.LineString(c[1:]) if len(c) >= 3 else line


def proposed(row: pd.Series) -> str:
    g, h = row["g_int"], row["h_lvl"]
    if row["cls"] == "both witnesses, same answer":
        return g
    if row["cls"] == "height only":
        return {"BS3_C": "BS3_C", "BS3_S": "BS3_S", "BS2": "BS2_S", "WC": "Wolfcamp", "BS1+": "BS1_S or above"}.get(h, str(h))
    return g


def render(row: pd.Series, n: int, subj: pd.Series, near: pd.DataFrame, out: Path) -> dict:
    line = lateral(shapely.from_wkt(subj["wkt"]))
    xy = np.array(line.coords)
    mid = xy.mean(axis=0)
    d = xy[-1] - xy[0]
    az = float(np.degrees(np.arctan2(d[0], d[1])) % 180.0)
    u, axis = section_axis(az, d)
    z0 = float(row["z"])
    codes = sorted({c for c in near["code"] if isinstance(c, str)} | {row["tag"]})
    col = {c: PALETTE[i % len(PALETTE)] for i, c in enumerate(codes)}
    fig, (ax, pl) = plt.subplots(1, 2, figsize=(15, 7.4), gridspec_kw={"width_ratios": [1.5, 1]})
    prop = proposed(row)
    if prop in INTERVAL and all(pd.notna(row[k]) for k in INTERVAL[prop]):
        ax.axhspan(float(row[INTERVAL[prop][0]]), float(row[INTERVAL[prop][1]]), color="#facc15", alpha=0.13, lw=0)
    for key, label in SURFACES:
        if pd.notna(row[key]) and abs(float(row[key]) - z0) <= DEPTH_PAD_FT - 20:
            ax.axhline(float(row[key]), color="#374151", lw=1.1, ls="-")
            ax.text(-HALF_WIDTH_FT * 0.99, float(row[key]) - 10, f"{label} {float(row[key]):,.0f}", ha="left", va="bottom", fontsize=8, color="#374151")
    if pd.notna(row["h"]):
        wca = z0 + float(row["h"])
        if abs(wca - z0) <= DEPTH_PAD_FT - 20:
            ax.axhline(wca, color="#b91c1c", lw=1.1, ls="--")
            ax.text(HALF_WIDTH_FT * 0.99, wca - 10, f"local WCA_1 wells, median {wca:,.0f}", ha="right", va="bottom", fontsize=8, color="#b91c1c")
    drawn = plan_only = 0
    for w in near.itertuples():
        g = shapely.from_wkt(w.wkt)
        z = evidence_depth(bool(w.planned), w.lat_tvd_p50_ft, w.tvd_ft)
        me = w.api10 == row["api10"]
        c = col.get(w.code, "#9ca3af")
        pl.plot(*np.array(g.coords).T, color="#111827" if me else c, lw=2.6 if me else 1.0, alpha=1.0 if me else 0.75, ls="-" if z is not None else ":", zorder=5 if me else 2)
        x = 0.0 if me else offset_ft(g, line, mid, u)
        if x is None or abs(x) > HALF_WIDTH_FT:
            continue
        if z is None:
            plan_only += 1
            continue
        if abs(z - z0) > DEPTH_PAD_FT - 20:
            continue
        drawn += 1
        prod = w.fp is not None and not pd.isna(w.fp)
        ax.scatter([x], [z], s=190 if me else 46, marker="o", facecolor=c if prod else "white", edgecolor="#111827" if me else c, linewidth=2.4 if me else 1.2,
                   zorder=6 if me else 3)
        ax.text(x, z - 32, str(w.code), ha="center", va="bottom", fontsize=6.5 if not me else 8.5, color=c, weight="bold" if me else "normal", clip_on=True)
    ax.set_xlim(-HALF_WIDTH_FT, HALF_WIDTH_FT)
    ax.set_ylim(z0 + DEPTH_PAD_FT, z0 - DEPTH_PAD_FT)
    ax.set_xlabel(f"offset from the well, ft   ({axis})")
    ax.set_ylabel("TVD, ft")
    ax.grid(alpha=0.25)
    ax.set_title("Strike section: wells with depth evidence beside the well; gridded tops and WCA_1 control at the well", fontsize=10, loc="left")
    ax.legend(handles=[Line2D([], [], marker="o", ls="", markerfacecolor="#9ca3af", markeredgecolor="#111827", markeredgewidth=2.2, markersize=12, label="the well under review"),
                       Line2D([], [], marker="o", ls="", markerfacecolor="#9ca3af", markeredgecolor="#9ca3af", markersize=7, label="producing well (colour and label = its tag)"),
                       Line2D([], [], marker="o", ls="", markerfacecolor="white", markeredgecolor="#9ca3af", markersize=7, label="not yet producing"),
                       Line2D([], [], color="#374151", label="geologist's gridded top at the well (a witness, not gospel)"),
                       Line2D([], [], color="#b91c1c", ls="--", label="median depth of WCA_1 wells within 3 mi"),
                       Line2D([], [], color="#facc15", lw=7, alpha=0.4, label="gridded interval of the proposed bench")],
              fontsize=7.5, loc="upper right", framealpha=0.9)
    pl.set_aspect("equal")
    pl.set_xticks([])
    pl.set_yticks([])
    pl.set_title("Plan view, north up: the well in black", fontsize=10, loc="left")
    pl.legend(handles=[Line2D([], [], color=col[c], lw=2, label=c) for c in codes], fontsize=7.5, loc="best", ncol=2, framealpha=0.9)
    h_txt = "no WCA_1 control" if pd.isna(row["h"]) else f"{float(row['h']):,.0f} ft above local WCA_1 = {row['h_lvl']} level"
    fp_txt = "not yet producing" if pd.isna(subj["fp"]) else "first production " + str(subj["fp"])[:10]
    vend = ", ".join(f"{k} " + ("not recorded by the tag rule" if pd.isna(row[c]) else f"'{row[c]}'") for k, c in (("Novi", "novi_raw"), ("Enverus", "env_raw")))
    fig.suptitle(f"Card {n:02d}  |  group {row['group'][0]}  |  {subj['well_name']} ({subj['operator']})  API {row['api10']}  |  {subj['county']} County  |  "
                 f"{fp_txt}\n"
                 f"Tagged {row['tag']} at {z0:,.0f} ft TVD.   Grid: in {row['g_int']}, {float(row['g_edge_ft']):,.0f} ft from the nearest top.   Height: {h_txt}.\n"
                 f"Proposed: {prop}.   Vendor names: {vend}",
                 fontsize=10.5, x=0.01, ha="left")
    fig.subplots_adjust(left=0.06, right=0.99, top=0.83, bottom=0.08, wspace=0.08)
    f = out / f"card_{n:02d}.png"
    fig.savefig(f, dpi=110)
    plt.close(fig)
    return {"card": n, "file": f.name, "group": row["group"], "group_size": int(row["group_size"]), "api10": row["api10"], "well_name": subj["well_name"],
            "operator": subj["operator"], "county": subj["county"], "tag": row["tag"], "tvd_ft": z0, "grid_interval": row["g_int"], "grid_edge_ft": float(row["g_edge_ft"]),
            "h_ft": None if pd.isna(row["h"]) else float(row["h"]), "h_level": row["h_lvl"], "proposed": prop, "wells_on_section": drawn, "wells_plan_only_no_depth": plan_only}


def write_index(rows: list[dict], out: Path) -> None:
    body = "".join(f"<section><h2>Card {r['card']:02d} &middot; group {html.escape(r['group'][0])} &middot; {html.escape(r['tag'])} &rarr; "
                   f"{html.escape(r['proposed'])} &middot; {html.escape(str(r['county']))}</h2><img src='{r['file']}' alt='card {r['card']}'></section>" for r in rows)
    (out / "index.html").write_text(
        "<!doctype html><meta charset='utf-8'><title>Bone Spring tag cards</title><style>body{font:14px system-ui;margin:16px;max-width:1700px}"
        "img{width:100%;border:1px solid #d1d5db}h2{font-size:15px;margin:22px 0 6px}</style><h1>Delaware Bone Spring tags: review cards</h1>"
        "<p>For each card: is the well's tag right? <b>AGREE</b> = retag to the proposed bench. <b>KEEP</b> = the tag is right as it is. "
        "Or name the bench it should be (for example <b>BS2_S</b>). The gridded tops are a witness, not gospel.</p>" + body, encoding="utf-8")


def run(listed: pd.DataFrame, out: Path) -> pd.DataFrame:
    out.mkdir(parents=True, exist_ok=True)
    pick = choose(listed)
    ids = list(pick["api10"])
    S = _ro(_SUBJ, (ids,)).set_index("api10")
    N = _ro(_NEAR, (ids,))
    rows = [render(r, i + 1, S.loc[r["api10"]], N[N["subject"] == r["api10"]], out) for i, r in pick.iterrows()]
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
    print(idx.groupby(["group", "proposed"]).size().to_string(), f"\n{len(idx)} cards", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
