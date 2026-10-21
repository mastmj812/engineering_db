"""Tops-vs-tag QC — step 1 report: sample both grid sets along every lateral, check the datum, measure agreement.

READ ONLY against the warehouse. Writes docs/box/tops-qc-<date>/{step1.html, wells_step1.csv, summary.json}.
Pure scoring lives in box/tops_qc.py; this module pulls, runs it per grid set, and renders.
"""

from __future__ import annotations

import datetime as _dt
import html
import json
import subprocess
from datetime import timedelta
from pathlib import Path
from typing import Any

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

from box import bench_qc as bq
from box import extent_package as pkg
from box import geology_io as gio
from box import tops_qc as tq
from box.edge_gap_report import _CSS, _png, _table

ROOT = Path(__file__).resolve().parent.parent
GRID_SETS = {"new": pkg.GRID_DIR, "orig": pkg.ORIGINAL_GRID_DIR}
# A scored-bench landing shallower than this is a data error (tvd_ft of 9 ft / 597 ft seen 2026-10-20), not
# evidence about the grid: 631 wells (292 midpoint tvd_ft, 339 survey lateral medians) at the first run.
MIN_EVIDENCE_TVD_FT = 4_000.0
GROSS_MISS_FT = 300.0  # a miss this large is a data / grid-extrapolation problem until shown otherwise

_STATIONS_SQL = """
SELECT s.api10, (s.dp).path[1] AS i,
       extensions.ST_X((s.dp).geom) AS lon, extensions.ST_Y((s.dp).geom) AS lat, extensions.ST_Z((s.dp).geom) AS tvd,
       s.kb_elev_ft
FROM (SELECT api10, kb_elev_ft, extensions.ST_DumpPoints(lateral_geom) AS dp
      FROM curated.well_lateral_survey
      WHERE api10 = ANY(%(a)s) AND lateral_geom IS NOT NULL) s
"""
_SURVEY_SQL = """
SELECT api10, lateral_basis, kb_elev_ft, lat_tvd_p50_ft, lat_tvd_range_ft, toe_minus_heel_tvd_ft, lat_interp_share
FROM curated.well_lateral_survey WHERE api10 = ANY(%(a)s)
"""


# ----------------------------------------------------------------------------
# Pull (read-only)
# ----------------------------------------------------------------------------


def _read(conn: Any, sql: str, params: dict[str, Any]) -> pd.DataFrame:
    with conn.cursor() as cur:
        cur.execute("SET TRANSACTION READ ONLY")
        cur.execute(sql, params)
        cols = [c.name for c in cur.description]
        rows = cur.fetchall()
    conn.rollback()
    return pd.DataFrame(rows, columns=cols)


def box_bench_map(root: Path = ROOT) -> pd.Series:
    """Latest box_bench per api10 across the committed wells_final_<pool>.csv files (newest folder date wins)."""
    files = sorted(root.glob("docs/box/*/wells_final_*.csv"))
    parts = []
    for f in files:
        d = pd.read_csv(f, usecols=["api10", "box_bench"], dtype={"api10": str})
        d["_date"] = "-".join(f.parent.name.rsplit("-", 3)[-3:])
        parts.append(d)
    if not parts:
        return pd.Series(dtype=object)
    allb = pd.concat(parts).sort_values("_date", kind="stable")
    return allb.drop_duplicates("api10", keep="last").set_index("api10")["box_bench"]


def pull(conn: Any) -> tuple[pd.DataFrame, pd.DataFrame]:
    """(wells, stations). wells = bench_qc Delaware producers + survey summary + evidence flag; stations = every
    lateral-span survey station of those wells (lon, lat, tvd ft)."""
    w = bq.pull_delaware_producers(conn)
    ids = w["api10"].tolist()
    sv = _read(conn, _SURVEY_SQL, {"a": ids})
    st = _read(conn, _STATIONS_SQL, {"a": ids})
    w = w.merge(sv, on="api10", how="left")
    for c in ("kb_elev_ft", "lat_tvd_p50_ft", "lat_tvd_range_ft", "toe_minus_heel_tvd_ft", "lat_interp_share"):
        w[c] = pd.to_numeric(w[c], errors="coerce")
    has_st = set(st["api10"].unique())
    w["tvd_source"] = np.where(w["api10"].isin(has_st), "survey", np.where(w["tvd_ft"].notna() & w["mid_lon"].notna(), "midpoint", "none"))
    asof = w.attrs.get("asof") or _dt.datetime.now(tz=_dt.UTC).date()
    seasoned = pd.Series([fp <= asof - timedelta(days=bq.SEASONING_DAYS) for fp in w["first_production_date"]], index=w.index)
    depth = np.where(w["tvd_source"] == "survey", w["lat_tvd_p50_ft"], w["tvd_ft"]).astype(float)
    w["evidence"] = (
        w["formation_blueox"].isin(tq.TAG_TOP)
        & ~w["planned"]
        & seasoned
        & ((w["tvd_source"] == "survey") | ((w["tvd_source"] == "midpoint") & ~w["tvd_round"]))
        & (depth >= MIN_EVIDENCE_TVD_FT)
    )
    w["box_bench"] = w["api10"].map(box_bench_map())
    for c in ("lon", "lat", "tvd", "kb_elev_ft"):
        st[c] = pd.to_numeric(st[c], errors="coerce")
    return w, st


# ----------------------------------------------------------------------------
# Scoring
# ----------------------------------------------------------------------------


def _to_geology(lon: np.ndarray, lat: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    tr = gio._tr("EPSG:4269", gio.GEOLOGY_CRS)
    return tr.transform(np.asarray(lon, float), np.asarray(lat, float))


def station_inputs(w: pd.DataFrame, st: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    """(survey stations, midpoint pseudo-stations) in the geology frame, both with columns api10, tag, x, y, tvd."""
    tag = w.set_index("api10")["formation_blueox"]
    s = st.copy()
    s["x"], s["y"] = _to_geology(s["lon"].to_numpy(), s["lat"].to_numpy())
    s["tag"] = s["api10"].map(tag)
    s["subsea"] = s["tvd"] - s["kb_elev_ft"]
    m = w[w["tvd_ft"].notna() & w["mid_lon"].notna()][["api10", "formation_blueox", "mid_lon", "mid_lat", "tvd_ft"]].copy()
    m["x"], m["y"] = _to_geology(m["mid_lon"].to_numpy(), m["mid_lat"].to_numpy())
    m = m.rename(columns={"formation_blueox": "tag", "tvd_ft": "tvd"})
    return s, m


def score_set(stack: dict[str, tq.Grid], s: pd.DataFrame, m: pd.DataFrame) -> dict[str, pd.DataFrame]:
    """Per-well summaries for one grid set: survey stations ('survey'), the single midpoint tvd_ft ('midpoint'),
    and the survey stations against SUBSEA depth ('subsea' — the datum alternative)."""
    return {
        "survey": tq.well_summary(tq.station_frame(s, stack)),
        "midpoint": tq.well_summary(tq.station_frame(m, stack)),
        "subsea": tq.well_summary(tq.station_frame(s, stack, tvd_col="subsea")),
    }


def primary(w: pd.DataFrame, res: dict[str, pd.DataFrame]) -> pd.DataFrame:
    """Survey summary where the well has stations, else the midpoint one; indexed like w['api10']."""
    has = w["tvd_source"].eq("survey")
    parts = [res["survey"].reindex(w.loc[has, "api10"]), res["midpoint"].reindex(w.loc[~has, "api10"])]
    return pd.concat(parts).reindex(w["api10"])


def apply_rules(w: pd.DataFrame, p: pd.DataFrame) -> pd.DataFrame:
    """Keep the geometric verdict as verdict_raw and apply the geology decisions (tops_qc.apply_geology_rules)."""
    info = w.set_index("api10")[["formation_blueox", "county"]].reindex(p.index)
    out = p.copy()
    out["verdict_raw"] = out["verdict"]
    out["verdict"] = [tq.apply_geology_rules(str(t), c if isinstance(c, str) else None, v if isinstance(v, str) else "unmeasured")
                      for t, c, v in zip(info["formation_blueox"], info["county"], out["verdict"], strict=True)]
    return out


def agreement_table(w: pd.DataFrame, p_new: pd.DataFrame, p_orig: pd.DataFrame, mid_new: pd.DataFrame,
                    dist_top: pd.Series) -> pd.DataFrame:
    ev = w[w["evidence"]].set_index("api10")
    rows = []
    for tag in [t for t in tq.TAG_TOP if t in set(ev["formation_blueox"])]:
        ids = ev.index[ev["formation_blueox"] == tag]
        a, o, md = p_new.loc[ids], p_orig.loc[ids], mid_new.reindex(ids)
        meas = a["verdict"].isin(tq.SCORED_VERDICTS)
        trusted = (dist_top.reindex(ids) <= pkg.TRUST_MAX_FT).to_numpy()
        aa = a["verdict"].eq("agree").to_numpy()
        mis = a[a["verdict"].isin(["shallow", "deep"])]
        gross = (meas & (a["miss_p50"].abs() > GROSS_MISS_FT)).to_numpy()
        mn = meas.to_numpy()
        rows.append({
            "tag": tag, "interval": f"{tq.TAG_TOP[tag]} → {tq.tag_base(tag)}", "n": len(ids),
            "survey %": float((ev.loc[ids, "tvd_source"] == "survey").mean()),
            "agree new": float(a.loc[meas, "verdict"].eq("agree").mean()) if mn.any() else np.nan,
            "agree Sept": float(o.loc[o["verdict"].isin(tq.SCORED_VERDICTS), "verdict"].eq("agree").mean()),
            "agree new, tvd_ft only": float(md.loc[md["verdict"].isin(tq.SCORED_VERDICTS), "verdict"].eq("agree").mean()),
            "shallow new": float(a.loc[meas, "verdict"].eq("shallow").mean()) if mn.any() else np.nan,
            "deep new": float(a.loc[meas, "verdict"].eq("deep").mean()) if mn.any() else np.nan,
            "agree ≤1 mi control": float(aa[trusted & meas.to_numpy()].mean()) if (trusted & meas.to_numpy()).any() else np.nan,
            "agree >1 mi control": float(aa[~trusted & meas.to_numpy()].mean()) if (~trusted & meas.to_numpy()).any() else np.nan,
            "≤1 mi control %": float(trusted[mn].mean()) if mn.any() else np.nan,
            "median miss (ft)": float(mis["miss_p50"].median()) if len(mis) else np.nan,
            "misses ≤25 ft %": float((mis["miss_p50"].abs() <= 25).mean()) if len(mis) else np.nan,
            "misses ≤50 ft %": float((mis["miss_p50"].abs() <= 50).mean()) if len(mis) else np.nan,
            f"gross >{GROSS_MISS_FT:.0f} ft": int(gross.sum()),
            "dist to control p50 (ft)": float(np.nanmedian(dist_top.reindex(ids))),
            "gross: dist to control p50 (ft)": float(np.nanmedian(dist_top.reindex(ids)[gross])) if gross.any() else np.nan,
            "no control": int(a["verdict"].eq("no_control").sum()),
            "surface suspect": int(a["verdict"].eq("surface_suspect").sum()),
            "no surface": int(a["verdict"].eq("no_surface").sum()),
            "unmeasured": int(a["verdict"].eq("unmeasured").sum()),
        })
    return pd.DataFrame(rows)


def datum_table(w: pd.DataFrame, res: dict[str, dict[str, pd.DataFrame]]) -> pd.DataFrame:
    ev = w[w["evidence"] & w["tvd_source"].eq("survey")].set_index("api10")
    rows = []
    for name, r in res.items():
        for mode in ("survey", "subsea"):
            a = r[mode].reindex(ev.index)
            meas = a["verdict"] != "unmeasured"
            rows.append({"grid set": name, "depth compared": "TVD below KB" if mode == "survey" else "subsea (TVD − KB)",
                         "wells": int(meas.sum()), "agree": float(a.loc[meas, "verdict"].eq("agree").mean()),
                         "median ft below tag top": float(a.loc[meas, "ft_below_top_p50"].median()),
                         "median |miss| of misses (ft)": float(a.loc[meas & (a["verdict"] != "agree"), "miss_p50"].abs().median())})
    return pd.DataFrame(rows)


def grid_change(w: pd.DataFrame, s_new: dict[str, tq.Grid], s_orig: dict[str, tq.Grid]) -> pd.DataFrame:
    ev = w[w["evidence"] & w["mid_lon"].notna()]
    x, y = _to_geology(ev["mid_lon"].to_numpy(), ev["mid_lat"].to_numpy())
    xy = np.column_stack([x, y])
    rows = []
    for srf in tq.STACK:
        d = s_new[srf].sample(xy) - s_orig[srf].sample(xy)
        d = d[np.isfinite(d)]
        if not len(d):
            continue
        rows.append({"surface": srf, "wells sampled": len(d), "new − Sept p10 (ft)": float(np.percentile(d, 10)),
                     "p50": float(np.median(d)), "p90": float(np.percentile(d, 90)),
                     "|Δ| > 50 ft %": float((np.abs(d) > 50).mean()), "|Δ| > 100 ft %": float((np.abs(d) > 100).mean())})
    return pd.DataFrame(rows)


# ----------------------------------------------------------------------------
# Render
# ----------------------------------------------------------------------------


def agreement_png(t: pd.DataFrame) -> str:
    fig, ax = plt.subplots(figsize=(10, 3.6))
    xi = np.arange(len(t))
    for k, (c, col) in enumerate([("agree Sept", "#9ca3af"), ("agree new, tvd_ft only", "#93c5fd"), ("agree new", "#1d4ed8")]):
        ax.bar(xi + (k - 1) * 0.27, t[c] * 100, width=0.27, label=c, color=col)
    ax.set_xticks(xi, t["tag"], rotation=0, fontsize=8)
    ax.set_ylabel("% of evidence wells in tag interval")
    ax.set_ylim(0, 100)
    ax.legend(fontsize=8, ncol=3, loc="lower left")
    ax.grid(axis="y", alpha=0.3)
    return _png(fig, dpi=110)


def miss_png(w: pd.DataFrame, p_new: pd.DataFrame) -> str:
    ev = w[w["evidence"]].set_index("api10")
    tags = [t for t in tq.TAG_TOP if t in set(ev["formation_blueox"])]
    data = []
    for t in tags:
        a = p_new.loc[ev.index[ev["formation_blueox"] == t]]
        data.append(a.loc[a["verdict"].isin(["shallow", "deep"]), "miss_p50"].dropna().clip(-400, 400).to_numpy())
    fig, ax = plt.subplots(figsize=(10, 3.6))
    ax.boxplot(data, tick_labels=tags, showfliers=False)
    ax.axhline(0, color="#111827", lw=0.8)
    ax.set_ylabel("median miss of disagreeing wells (ft)\n− above tag top, + below tag base")
    ax.tick_params(axis="x", labelsize=8)
    ax.grid(axis="y", alpha=0.3)
    return _png(fig, dpi=110)


def _pct(df: pd.DataFrame, cols: list[str]) -> pd.DataFrame:
    d = df.copy()
    for c in cols:
        d[c] = (d[c] * 100).round(1)
    return d


def render(ctx: dict[str, Any]) -> str:
    t = ctx["agreement"]
    pct_cols = ["survey %", "agree new", "agree Sept", "agree new, tvd_ft only", "shallow new", "deep new",
                "agree ≤1 mi control", "agree >1 mi control", "≤1 mi control %", "misses ≤25 ft %", "misses ≤50 ft %"]
    parts = [
        f"<meta charset=utf-8><meta name=viewport content='width=device-width, initial-scale=1'><title>Tops vs Tags · Step 1</title><style>{_CSS}</style>",
        "<h1>Tops vs tags — step 1: sampling, datum, agreement</h1>",
        (f"<div class=meta>built {html.escape(ctx['built'])} · git {html.escape(ctx['sha'])} · grids: new = "
         f"{html.escape(str(pkg.GRID_DIR))}, Sept = {html.escape(str(pkg.ORIGINAL_GRID_DIR))} · READ ONLY</div>"),
        ("<p>Each Delaware producing horizontal's <b>formation_blueox</b> tag is scored against the grid interval it should "
         "sit in (tag top → next surface down). Wells with a Novi survey are scored at <b>every lateral station</b> "
         "(sql/64), the rest at the midpoint <code>tvd_ft</code>. <b>agree</b> = majority of the lateral inside the tag "
         "interval. A disagreement means the tag OR the grid is wrong; step 2 attributes which. "
         "Evidence wells only: not a planned survey, ≥ 6 mo online, (survey or non-round tvd_ft), and landing depth "
         f"≥ {MIN_EVIDENCE_TVD_FT:,.0f} ft (shallower = a data error on a scored bench).</p>"),
        ("<div class=flag><b>Geology decisions applied (2026-10-20):</b> WOLFCAMP-C and WOLFCAMP_D are suspect "
         "(to be relabelled / re-picked) — WCC and WCD are <i>surface_suspect</i>, and a WCB_2 'deep' call (base = C top) "
         "is too. AVA_1 = Middle Avalon (operator tops ~110 ft above AVALON2) has no surface — <i>no_surface</i> until one "
         "is built; AVALON1 = top Upper Avalon, AVALON2 = top Lower Avalon. Pecos County: Wolfcamp A–D and AVALON2 have "
         "zero picks — <i>no_control</i> (kept out of agreement, shown on the step-2 maps and counted in its picks-needed "
         "table: revised 2026-10-21); XY, Bone Springs and Bell/Cherry/Brushy stay scored there with caution. "
         "Agreement shares are over agree / shallow / deep only; the raw geometric verdict is kept as verdict_raw "
         "in the CSV.</div>"),
        "<h2>1 · Datum check</h2>",
        ("<p>If grid Z were subsea, comparing it to TVD-below-KB would put nearly every well ~KB (≈ 2,600–3,700 ft) below "
         "its tag; the right datum is the one that agrees.</p>"),
        _table(_pct(ctx["datum"], ["agree"]), {"median ft below tag top": ".0f", "median |miss| of misses (ft)": ".0f"}),
        f"<div class='flag {'ok' if ctx['datum_ok'] else 'bad'}'>{html.escape(ctx['datum_verdict'])}</div>",
        "<h2>2 · Agreement by tag (evidence wells)</h2>",
        f"<img src='{agreement_png(t)}'>",
        _table(_pct(t, pct_cols), {"median miss (ft)": ".0f", "dist to control p50 (ft)": ",.0f",
                                   "gross: dist to control p50 (ft)": ",.0f"}),
        ("<div class=meta>agree new, tvd_ft only = the same wells scored at one point with wells_enriched.tvd_ft "
         "(what we had before sql/64). ≤1 mi control = the tag-top surface's DIST_TO_CONTROL grid ≤ 5,280 ft at the "
         "lateral midpoint (provisional trust radius, extent_package.TRUST_MAX_FT). Miss = a disagreeing well's median "
         "station miss, ft (− above the tag top, + below the tag base); misses ≤25 / ≤50 ft = the share of misses within "
         "that distance of a surface (the 'edge' candidates of step 2). Gross = |miss| > 300 ft (data error or grid "
         "extrapolation until shown otherwise), with its median distance to control.</div>"),
        f"<img src='{miss_png(ctx['wells'], ctx['p_new'])}'>",
        "<h2>3 · How far the 10-19 update moved each surface (at evidence-well midpoints)</h2>",
        _table(_pct(ctx["change"], ["|Δ| > 50 ft %", "|Δ| > 100 ft %"]), {"new − Sept p10 (ft)": ".0f", "p50": ".0f", "p90": ".0f"}),
        "<h2>4 · Surface order (grid nodes)</h2>",
        ("<p>Share of nodes where the deeper surface sits ABOVE the shallower one (negative isopach). Interval assignment "
         "counts surfaces above a station, so a crossing makes a station's interval ambiguous there.</p>"),
        ("<div class=row><div><h3>new (10-19)</h3>" + _table(_pct(ctx["cross_new"], ["pct_crossing"]), {"iso_p05_ft": ".0f", "iso_p50_ft": ".0f"}) + "</div>"
         "<div><h3>Sept (Original)</h3>" + _table(_pct(ctx["cross_orig"], ["pct_crossing"]), {"iso_p05_ft": ".0f", "iso_p50_ft": ".0f"}) + "</div></div>"),
        "<h2>5 · Universe</h2>",
        _table(ctx["universe"]),
        ("<div class=meta>Per-well detail: wells_step1.csv (UTM 14N US-ft x/y for GGX, both grid sets, survey and "
         "tvd_ft-only verdicts, box_bench).</div>"),
    ]
    return "\n".join(parts)


def universe_table(w: pd.DataFrame) -> pd.DataFrame:
    g = w.assign(scored_tag=w["formation_blueox"].isin(tq.TAG_TOP))
    return pd.DataFrame([
        {"set": "Delaware producing horizontals", "wells": len(g)},
        {"set": "tag has a grid interval", "wells": int(g["scored_tag"].sum())},
        {"set": "  with a survey", "wells": int((g["scored_tag"] & g["tvd_source"].eq("survey")).sum())},
        {"set": "  midpoint tvd_ft only", "wells": int((g["scored_tag"] & g["tvd_source"].eq("midpoint")).sum())},
        {"set": "  planned survey (excluded)", "wells": int((g["scored_tag"] & g["planned"]).sum())},
        {"set": "evidence wells", "wells": int(g["evidence"].sum())},
        {"set": "tags without a grid interval (not scored)", "wells": int((~g["scored_tag"]).sum())},
        {"set": f"evidence wells in caution counties ({', '.join(sorted(tq.CAUTION_COUNTIES))})",
         "wells": int((g["evidence"] & g["county"].isin(tq.CAUTION_COUNTIES)).sum())},
    ])


WELL_COLS = ["api10", "well_name", "operator", "county", "state_code", "formation_blueox", "box_bench", "evidence",
             "planned", "tvd_source", "tvd_ft", "lat_tvd_p50_ft", "lat_tvd_range_ft", "toe_minus_heel_tvd_ft",
             "kb_elev_ft", "first_production_date", "mid_lon", "mid_lat"]
SCORE_COLS = ["verdict", "verdict_raw", "pct_in_tag", "pct_above_top", "pct_below_base", "dom_interval", "miss_p50",
              "ft_below_top_p50", "ft_above_base_p50", "frac_p50", "top_p50", "base_p50"]


def wells_csv(w: pd.DataFrame, p_new: pd.DataFrame, p_orig: pd.DataFrame, mid_new: pd.DataFrame,
              dist_top: pd.Series, dist_base: pd.Series) -> pd.DataFrame:
    out = w[WELL_COLS].copy().reset_index(drop=True)
    ok = out["mid_lon"].notna()
    out["x_utm14_usft"], out["y_utm14_usft"] = np.nan, np.nan
    x, y = _to_geology(out.loc[ok, "mid_lon"].to_numpy(), out.loc[ok, "mid_lat"].to_numpy())
    out.loc[ok, "x_utm14_usft"], out.loc[ok, "y_utm14_usft"] = x, y
    ids = out["api10"]
    for c in SCORE_COLS:
        out[f"new_{c}"] = p_new[c].reindex(ids).to_numpy()
    for c in ("verdict", "pct_in_tag", "miss_p50"):
        out[f"sept_{c}"] = p_orig[c].reindex(ids).to_numpy()
    out["new_tvdft_only_verdict"] = mid_new["verdict"].reindex(ids).to_numpy()
    out["caution_county"] = out["county"].isin(tq.CAUTION_COUNTIES)
    out["dist_to_control_top_ft"] = dist_top.reindex(ids).to_numpy()
    out["dist_to_control_base_ft"] = dist_base.reindex(ids).to_numpy()
    return out


def run(conn: Any, out: Path) -> dict[str, Any]:
    out.mkdir(parents=True, exist_ok=True)
    w, st = pull(conn)
    s, m = station_inputs(w, st)
    stacks = {k: tq.load_stack(d) for k, d in GRID_SETS.items()}
    res = {k: score_set(stk, s, m) for k, stk in stacks.items()}
    p_new, p_orig = primary(w, res["new"]), primary(w, res["orig"])
    p_new.index, p_orig.index = w["api10"].to_numpy(), w["api10"].to_numpy()
    p_new, p_orig = apply_rules(w, p_new), apply_rules(w, p_orig)
    mid_new = apply_rules(w, res["new"]["midpoint"])
    # distance to control at the lateral midpoint, for the tag's top and base surfaces (10-19 grids only)
    mm = m.set_index("api10")
    dist_top, dist_base = pd.Series(np.nan, index=mm.index), pd.Series(np.nan, index=mm.index)
    for tag in tq.TAG_TOP:
        ids = mm.index[mm["tag"] == tag]
        if len(ids):
            xy = mm.loc[ids, ["x", "y"]].to_numpy(float)
            dist_top.loc[ids] = pkg.dist_to_control(tq.TAG_TOP[tag], xy)
            dist_base.loc[ids] = pkg.dist_to_control(tq.tag_base(tag), xy)
    datum = datum_table(w, res)
    surv = datum[datum["depth compared"].str.startswith("TVD")].set_index("grid set")["agree"]
    sub = datum[~datum["depth compared"].str.startswith("TVD")].set_index("grid set")["agree"]
    datum_ok = bool((surv > sub + 0.25).all())
    verdict = (f"PASS — grid Z behaves as depth below KB: TVD agreement {surv['new']:.0%} (new) / {surv['orig']:.0%} (Sept) "
               f"vs subsea {sub['new']:.0%} / {sub['orig']:.0%}." if datum_ok else
               f"CHECK — TVD agreement {surv['new']:.0%} / {surv['orig']:.0%} vs subsea {sub['new']:.0%} / {sub['orig']:.0%}: "
               "the datum is not clearly KB-relative. Stop before step 2.")
    ctx = {
        "built": _dt.datetime.now(tz=_dt.UTC).strftime("%Y-%m-%d %H:%M UTC"),
        "sha": subprocess.run(["git", "rev-parse", "--short", "HEAD"], capture_output=True, text=True, cwd=ROOT, check=False).stdout.strip(),
        "wells": w, "p_new": p_new,
        "datum": datum, "datum_ok": datum_ok, "datum_verdict": verdict,
        "agreement": agreement_table(w, p_new, p_orig, mid_new, dist_top),
        "change": grid_change(w, stacks["new"], stacks["orig"]),
        "cross_new": tq.surface_crossings(stacks["new"]), "cross_orig": tq.surface_crossings(stacks["orig"]),
        "universe": universe_table(w),
    }
    (out / "step1.html").write_text(render(ctx), encoding="utf-8")
    wells_csv(w, p_new, p_orig, mid_new, dist_top, dist_base).to_csv(out / "wells_step1.csv", index=False)
    summary = {
        "built": ctx["built"], "git": ctx["sha"], "grid_dirs": {k: str(v) for k, v in GRID_SETS.items()},
        "datum_ok": datum_ok, "datum_verdict": verdict,
        "agreement": ctx["agreement"].to_dict(orient="records"),
        "universe": ctx["universe"].to_dict(orient="records"),
        "stations": len(s), "trust_max_ft": pkg.TRUST_MAX_FT,
    }
    (out / "summary.json").write_text(json.dumps(summary, indent=2, default=str), encoding="utf-8")
    return ctx
