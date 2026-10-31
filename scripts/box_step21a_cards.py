"""BOX step 21a — proximity example cards for Michael's review (READ ONLY; nothing stored).

    python -m scripts.box_step21a_cards [--n-per 6] [--seed 20261031]

Reads the 21a evidence (docs/box/step21a-2026-10-31/sticks.csv.gz) and its links (runs/step21a/pud_links.pkl, written by
`scripts.box_step21a evidence`), draws a seeded stratified sample of in-extent undrilled sticks and renders one card each:
  * strike section through the stick midpoint, square to the stick (sign rule v2: + = E for N-S-ish laterals, N for E-W-ish,
    45-deg seam), TVD vs offset, the three class envelopes as boxes; depth axis held to the stick's band +/- 1,100 ft
  * plan view of the stick and every producer linked to it inside the 2,640-ft pair gate
  * the decision: outcome, configuration, bench-pair key, D114 precedent, factor (Delaware D113 table = INTERIM), DEAN part,
    the warehouse-tag outcome, and the parent table (api10, name, bench, tag, first production, months on, dz, gap, overlap)
Counting parent = >= 12 months on production at the reference date, >= 30 % alongside, inside its class envelope; a permit-round
TVD is counted and flagged (D115; box/prox_pud_report passes permit=False to configuration, no shielding exemption).
Writes prox_cards/cards.html + cards_sample.csv (verdict column for accept / reject).
"""

from __future__ import annotations

import argparse
import base64
import datetime as dt
import io
import json
import sys
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
import shapely

from box import edge_gap as eg
from box import production as prod
from box import prox_dose as pdz
from box import prox_study as ps
from box import prox_study_report as psr
from box import step21 as st
from box.edge_gap_report import _CSS
from box.tc_curve_report import _read

OUT = st.DOCS / "prox_cards"
RUNS = Path("runs") / "step21a"
REF = dt.date.fromisoformat(st.DEFINITION["folds"]["actuals_through"])
_NAME_SQL = "SELECT api10, well_name, current_operator FROM curated.wells WHERE api10 = ANY(%(a)s)"
COL = {"same": "#1d4ed8", "topfill": "#b91c1c", "underfill": "#047857"}
OUTCOME_TXT = {"as_is_unexposed": "forecast as-is (no depleting parent in an envelope)",
               "as_is_single_parent": "forecast as-is (single parent: no factor, D113 option a)",
               "haircut": "forecast × proximity factor (multi-parent, precedent met)",
               "no_forecast_precedent": "NO FORECAST — < 30 drilled multi-parent wells of this bench pair (D114)",
               "no_forecast_package": "NO FORECAST — factor ≤ 0.80 and < 30 drilled packages (D114 tier 2)"}


def plus_bearing(az: float) -> float:
    """Sign rule v2 (CLAUDE.md rule 16): a = folded azimuth rounded to 0.1 deg; + = a + 90 if a <= 45 else a - 90."""
    a = round(az % 180.0, 1)
    return a + 90.0 if a <= 45.0 else a - 90.0


def grid_azimuth(g: Any) -> float:
    (x0, y0), (x1, y1) = g.coords[0], g.coords[-1]
    return float(np.degrees(np.arctan2(x1 - x0, y1 - y0)) % 180.0)


def edge_ids(L: pd.DataFrame) -> set[str]:
    """Sticks with a depleting, >= 30 %-alongside parent within 150 ft of the 1,400-ft gap limit or 60 ft of its class's vertical
    limit, on either side: where the envelope edge decides the outcome."""
    q = L[(L["rel"] == "parent") & (L["overlap"] >= ps.MIN_OVERLAP)]
    hit = np.zeros(len(q), bool)
    for c, (vmax, hmax) in pdz.ENVELOPE.items():
        k = (q["cls"] == c).to_numpy()
        near_h = (np.abs(q["dh_ft"] - hmax) <= 150).to_numpy() & (q["dv_ft"] <= vmax).to_numpy()
        near_v = (np.abs(q["dv_ft"] - vmax) <= 60).to_numpy() & (q["dh_ft"] <= hmax).to_numpy()
        hit |= k & (near_h | near_v)
    return set(q.loc[hit, "child"])


def sample(s: pd.DataFrame, n_per: int, seed: int, edges: set[str] | None = None) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    picks: list[pd.DataFrame] = []
    used_pads: set[str] = set()

    def take(df: pd.DataFrame, n: int, why: str) -> None:
        df = df[~df["stick_id"].isin(set().union(*[set(p["stick_id"]) for p in picks]) if picks else set())]
        df = df.sample(frac=1.0, random_state=int(rng.integers(1 << 31)))
        rows = []
        for _, r in df.iterrows():
            pad = str(r["pad_name"])
            if pad != "nan" and pad in used_pads:
                continue
            rows.append(r)
            used_pads.add(pad)
            if len(rows) >= n:
                break
        if rows:
            picks.append(pd.DataFrame(rows).assign(why=why))

    # per outcome, spread over groups (round-robin by group)
    for o, n in (("as_is_unexposed", n_per - 2), ("as_is_single_parent", n_per - 2), ("haircut", n_per + 4),
                 ("no_forecast_precedent", n_per + 2), ("no_forecast_package", 3)):
        sub = s[s["outcome"] == o]
        groups = sub["group"].value_counts().index.tolist()
        for i in range(n):
            g = groups[i % len(groups)] if groups else None
            if g is not None:
                take(sub[sub["group"] == g], 1, f"outcome: {o}")
    take(s[(s["group"] == "MID_DEAN") & (s["part"] == "addition") & (s["pair_key"] == "DEAN>mixed")], 4, "D143: DEAN loop addition via DEAN>mixed")
    take(s[(s["group"] == "MID_DEAN") & (s["part"] == "addition") & (s["outcome"] == "no_forecast_precedent")], 2, "D143: DEAN loop addition, no precedent")
    take(s[(s["group"] == "MID_DEAN") & (s["part"] == "body")], 2, "D143: DEAN generated body")
    take(s[(s["group"] == "MID_WCC") & (s["outcome"] == "no_forecast_precedent")], 2, "WCC: 46 % no precedent")
    take(s[s["outcome"] != s["outcome_wh_tag"]], 3, "bench label: outcome changes with the warehouse tag")
    if edges:
        e = s[s["stick_id"].astype(str).isin(edges)]
        for o in ("as_is_unexposed", "as_is_single_parent", "haircut", "no_forecast_precedent"):
            take(e[e["outcome"] == o], 1, "envelope edge: a parent within 150 ft (gap) / 60 ft (vertical) of a limit")
    return pd.concat(picks, ignore_index=True)


def counting(L: pd.DataFrame) -> pd.Series:
    q = (L["rel"] == "parent") & (L["overlap"] >= ps.MIN_OVERLAP)  # PUDs: permit TVDs counted + flagged (D115)
    hit = np.zeros(len(L), bool)
    for c, (vmax, hmax) in pdz.ENVELOPE.items():
        hit |= ((L["cls"] == c) & (L["dv_ft"] <= vmax) & (L["dh_ft"] <= hmax)).to_numpy()
    return pd.Series(q.to_numpy() & hit, index=L.index)


def card_png(stick: Any, tvd: float, links: pd.DataFrame, geoms: dict[str, Any], tvds: dict[str, float], title: str) -> str:
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    az = grid_azimuth(stick)
    b = np.radians(plus_bearing(az))
    pvec = np.array([np.sin(b), np.cos(b)])
    mid = stick.interpolate(0.5, normalized=True)
    m = np.array([mid.x, mid.y])
    strike = shapely.LineString([tuple(m - pvec * 9_000), tuple(m + pvec * 9_000)])
    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(13, 5.6), dpi=100, gridspec_kw={"width_ratios": [1.35, 1]})
    # strike section
    ax1.axhspan(tvd - 1_100, tvd + 1_100, color="none")
    for c, (vmax, hmax), top, bot in (("same", pdz.ENVELOPE["same"], tvd - pdz.ENVELOPE["same"][0], tvd + pdz.ENVELOPE["same"][0]),
                                      ("topfill", pdz.ENVELOPE["topfill"], tvd, tvd + pdz.ENVELOPE["topfill"][0]),
                                      ("underfill", pdz.ENVELOPE["underfill"], tvd - pdz.ENVELOPE["underfill"][0], tvd)):
        ax1.add_patch(plt.Rectangle((-hmax, top), 2 * hmax, bot - top, fill=False, ls="--", lw=1.0, ec=COL[c], alpha=0.7))
    ax1.plot([0], [tvd], marker="*", ms=18, color="black", zorder=5)
    ax1.annotate("PUD stick", (0, tvd), xytext=(6, -14), textcoords="offset points", fontsize=8)
    for r in links.itertuples():
        g = geoms.get(r.parent)
        if g is None:
            continue
        hit = g.intersection(strike)
        if not hit.is_empty:
            pt = hit if hit.geom_type == "Point" else hit.centroid
            off, proj = float(np.dot(np.array([pt.x, pt.y]) - m, pvec)), False
        else:
            near = g.interpolate(g.project(mid))
            off, proj = float(np.dot(np.array([near.x, near.y]) - m, pvec)), True
        y = tvds.get(r.parent, tvd + r.dz_ft)
        if not (tvd - 1_100 <= y <= tvd + 1_100):
            continue
        c = COL.get(r.cls, "#6b7280")
        if r.counts:
            ax1.scatter(off, y, s=70, color=c, edgecolor="black", zorder=4, marker="s" if proj else "o")
        else:
            ax1.scatter(off, y, s=55, facecolor="white", edgecolor="#9ca3af", zorder=3, marker="s" if proj else "o")
        ax1.annotate(f"{r.parent_bench} {r.fp_year}\n…{r.parent[-5:]}", (off, y), xytext=(5, 3), textcoords="offset points", fontsize=7,
                     color=c if r.counts else "#6b7280")
    ax1.set_ylim(tvd + 1_100, tvd - 1_100)
    ax1.set_xlim(-2_700, 2_700)
    ax1.axvline(0, color="#d1d5db", lw=0.8)
    ax1.set_xlabel(f"offset along the strike, ft  (+ toward {plus_bearing(az) % 360:.0f}° grid; stick azimuth {az:.1f}°)")
    ax1.set_ylabel("TVD, ft")
    ax1.set_title("Strike section (filled = counting parent; open = linked but not counted; square = off-section, projected)", fontsize=8)
    # plan
    sx, sy = stick.xy
    ax2.plot(np.array(sx) / 5280, np.array(sy) / 5280, color="black", lw=3, zorder=5)
    ax2.plot(np.array(strike.xy[0]) / 5280, np.array(strike.xy[1]) / 5280, color="#9ca3af", ls=":", lw=1)
    for r in links.itertuples():
        g = geoms.get(r.parent)
        if g is None:
            continue
        x, y = g.xy
        ax2.plot(np.array(x) / 5280, np.array(y) / 5280, color=COL.get(r.cls, "#6b7280") if r.counts else "#d1d5db", lw=2 if r.counts else 1)
    ax2.set_aspect("equal")
    w = 1.6
    ax2.set_xlim(m[0] / 5280 - w, m[0] / 5280 + w)
    ax2.set_ylim(m[1] / 5280 - w, m[1] / 5280 + w)
    ax2.set_title("Plan, UTM 13N mi (black = PUD; blue same / red topfill / green underfill)", fontsize=8)
    fig.suptitle(title, fontsize=10)
    fig.tight_layout()
    buf = io.BytesIO()
    fig.savefig(buf, format="png")
    plt.close(fig)
    return base64.b64encode(buf.getvalue()).decode()


def main(argv: list[str] | None = None) -> int:
    from etl.db import get_connection

    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--n-per", type=int, default=6)
    ap.add_argument("--seed", type=int, default=20261031)
    a = ap.parse_args(argv)
    s = pd.read_csv(st.DOCS / "sticks.csv.gz")
    Lp = pd.read_pickle(RUNS / "pud_links.pkl")
    Lp["counts"] = counting(Lp)
    pick = sample(s, a.n_per, a.seed, edge_ids(Lp))
    with get_connection() as conn:
        U = prod.universe(conn, basins=["midland"])
        u = psr.pull_universe(conn, "midland")
        parents = sorted(set(Lp.loc[Lp["child"].isin(pick["stick_id"].astype(str)), "parent"]))
        names = pd.DataFrame(_read(conn, _NAME_SQL, {"a": parents}), columns=["api10", "well_name", "operator"]).set_index("api10")
        tvd = pd.DataFrame(_read(conn, "SELECT stick_id, tvd FROM curated.erebor_locations WHERE stick_id = ANY(%(i)s)",
                                 {"i": [int(x) for x in pick["stick_id"]]}), columns=["stick_id", "tvd"]).set_index("stick_id")["tvd"]
        conn.rollback()
    tag = dict(zip(u["api10"], u["bench"], strict=True))
    geoms = dict(zip(u["api10"], u["geom"], strict=True))
    fp = dict(zip(u["api10"], u["fp"], strict=True))
    tvds = dict(zip(u["api10"], u["tvd_ft"], strict=True))
    wkt = U.set_index("stick_id")["wkt"]
    OUT.mkdir(parents=True, exist_ok=True)
    cards, rows = [], []
    for n, r in enumerate(pick.itertuples(), 1):
        sid = int(r.stick_id)
        g = eg.to_ft([shapely.from_wkt(wkt[sid])])[0]
        t = float(tvd.get(sid, np.nan))
        L = Lp[Lp["child"] == str(sid)].copy()
        L["fp_year"] = [fp[p].year if p in fp else "?" for p in L["parent"]]
        L = L.sort_values(["counts", "dh_ft"], ascending=[False, True])
        title = f"#{n} {r.group} stick {sid} ({r.category}, pad {r.pad_name}) — {r.outcome}"
        png = card_png(g, t, L, geoms, tvds, title)
        cnt = L[L["counts"]]
        tab = "".join(
            f"<tr><td>{p.parent}</td><td>{names.at[p.parent, 'well_name'] if p.parent in names.index else ''}</td>"
            f"<td>{names.at[p.parent, 'operator'] if p.parent in names.index else ''}</td><td>{p.parent_bench}</td><td>{tag.get(p.parent, '')}</td>"
            f"<td>{fp.get(p.parent, '')}</td><td class=num>{(REF - fp[p.parent]).days // 30 if p.parent in fp else ''}</td><td>{p.cls}</td>"
            f"<td class=num>{p.dz_ft:+.0f}</td><td class=num>{p.dh_ft:.0f}</td><td class=num>{p.overlap:.0%}</td>"
            f"<td>{('counts' + (' (permit TVD)' if p.permit else '')) if p.counts else ('young/codev' if p.rel != 'parent' else ('< 30 % alongside' if p.overlap < ps.MIN_OVERLAP else 'outside envelope'))}</td></tr>"
            for p in L.itertuples())
        prec = "" if pd.isna(r.pair_key) else f"bench pair <b>{r.pair_key}</b>: {int(r.prec_multi)} drilled multi-parent wells, {int(r.prec_package)} packages (floor 30)"
        fac = "" if pd.isna(r.factor) or r.outcome in ("as_is_unexposed", "as_is_single_parent") else f" · factor {r.factor:.3f} (Delaware D113 table, INTERIM)"
        part = f" · DEAN {r.part}" if isinstance(r.part, str) else ""
        cards.append(
            f"<section class=card id=c{n}><h2>{title}</h2>"
            f"<div class=meta>{r.why} · stick TVD {t:,.0f} ft · length {r.length_ft:,.0f} ft · Novi status {r.recon_status}{part}</div>"
            f"<p><b>{OUTCOME_TXT.get(r.outcome, r.outcome)}</b>. Configuration {r.config_class if isinstance(r.config_class, str) else 'none'} "
            f"(counting parents: same {int(r.n_same)}, topfill {int(r.n_topfill)}, underfill {int(r.n_underfill)}){fac}. {prec}. "
            f"Warehouse-tag reading: {r.outcome_wh_tag}. Producers &lt; 12 months nearby: {int(r.recent_producers)}; permit-TVD parents: {int(r.permit_parents)}.</p>"
            f"<img src='data:image/png;base64,{png}' alt='card {n}'>"
            "<table><tr><th>api10</th><th>well</th><th>operator</th><th>BOX bench</th><th>tag</th><th>first prod</th><th>months on</th><th>class</th>"
            f"<th>dz ft (+ parent deeper)</th><th>gap ft</th><th>alongside</th><th>status</th></tr>{tab}</table>"
            f"<p class=meta>{len(cnt)} counting of {len(L)} linked producers.</p></section>")
        rows.append({"card": n, "stick_id": sid, "group": r.group, "pad_name": r.pad_name, "why": r.why, "outcome": r.outcome,
                     "config_class": r.config_class, "pair_key": r.pair_key, "prec_multi": r.prec_multi, "factor_interim": r.factor,
                     "dean_part": r.part, "outcome_wh_tag": r.outcome_wh_tag, "counting_parents": ";".join(cnt["parent"]), "verdict": "", "note": ""})
    head = (f"<!doctype html><html lang=en><head><meta charset=utf-8><meta name=viewport content='width=device-width,initial-scale=1'>"
            f"<title>BOX 21a proximity cards</title><style>{_CSS} body{{max-width:1300px;margin:auto;padding:0 16px;overflow-x:hidden}} "
            ".card{border-top:2px solid #9ca3af;margin-top:24px} img{max-width:100%} table{display:block;overflow-x:auto;max-width:100%}</style></head><body>"
            f"<h1>BOX step 21a — Midland proximity examples ({len(rows)} cards, seed {a.seed})</h1>"
            f"<div class=meta>built {dt.datetime.now(tz=dt.UTC).astimezone().isoformat(timespec='seconds')} · reference date {REF} · in-extent undrilled "
            "sticks (D117) · envelopes same 1,000 vt × 1,400 hz, topfill 800 × 1,400 (parent deeper), underfill 500 × 1,400 (parent shallower) · "
            "counting parent = ≥ 12 months producing, ≥ 30 % alongside, inside its envelope (permit TVDs counted, flagged) · precedent = Midland drilled children · "
            "factor = Delaware D113 table (INTERIM until 21b) · read-only</div>"
            "<p>Verdicts go in <code>cards_sample.csv</code> (<b>accept</b> = the outcome feels right for this location; <b>reject</b> = it doesn't; "
            "a note on why helps). Open the api10s in anduin for the gunbarrel you normally draw.</p>")
    (OUT / "cards.html").write_text(head + "\n".join(cards) + "</body></html>", encoding="utf-8")
    pd.DataFrame(rows).to_csv(OUT / "cards_sample.csv", index=False)
    (OUT / "cards_summary.json").write_text(json.dumps({"n": len(rows), "seed": a.seed, "by_why": pd.DataFrame(rows)["why"].value_counts().to_dict()}, indent=1),
                                           encoding="utf-8")
    print(pd.DataFrame(rows)[["card", "group", "why", "outcome", "pair_key"]].to_string(index=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
