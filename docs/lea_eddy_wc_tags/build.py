"""Lea / Eddy Wolfcamp B anomaly — diagnosis + producer review cards (read-only; nothing written to the warehouse).

    python docs/lea_eddy_wc_tags/build.py --out docs/lea_eddy_wc_tags [--cache <scored.pkl>]

Symptom: curated.erebor_locations.wca_delta_ft (sql/30: stick TVD minus the median WCA_1/WCA_2 producing-horizontal TVD
within 3 mi) is < -100 ft on 1,297 of 3,217 Lea and 331 of 3,143 Eddy Novi 'Wolfcamp B' sticks. Three hypotheses are
tested here, each against evidence that does not come from the tag being tested:

  H1 producers  — the WCA producers are really WCB or deeper. Tested with the tag screen (box.tag_screen rules A / B on
                  the consensus-scored frame), the geologist's V5 structure grids (box.tops_qc, Grids_10-19-26) and a
                  sensitivity: the stick count again with every suspect WCA producer removed from the 3-mi median.
  H2 structure  — the 3-mi median spans dip. Tested with a robust local plane through the WCA producers evaluated at the
                  stick, and with Novi's own pad stack (WCB stick minus Novi's nearest Wolfcamp A stick within 1 mi:
                  dip cancels on a pad).
  H3 sticks     — Novi's 'Wolfcamp B' sticks sit shallow. Tested with the geologist grids at the stick midpoint and the
                  same pad-stack read.

H1 turns up one producer class the tag screen cannot see (box.tag_screen.other_vendor treats a coarse Novi value as no
vote, and sql/16 lists Novi 'WOLFCAMP B' as coarse): NM horizontals that Novi calls WOLFCAMP B, tagged WCA_1 / WCA_2 /
WCXY from Enverus. Rule V (fixed before any card was drawn): such a well, with >= 3 clean WCA_1/WCA_2 witnesses within
1.5 mi that are NOT in the class, is placed on the NM separation ladder (its TVD minus that witness median, nearest rung
of LADDER_FT); flagged when the nearest rung is a WCB / WCC bench, destination = that bench. Cards follow the tag screen
(5 per class, sequential gate at qc_rule.CLASS_GATE via box.tag_screen.decide). The seed this writes is a PROPOSAL for
review: proposed_override_seed.csv, outside seeds/, never loaded.

Planned surveys (Michael 2026-11-04): a well whose directional survey is the pre-drill plan
(directional_survey_is_planned) has a planned TVD AND a planned lateral path, so neither its depth nor its position
is evidence. Such wells are never judged (rule V subjects), never used as depth evidence (3-mi WCA medians, the WCA
plane, the producer grid table, the sensitivity) and never drawn on a card (GOONCH FEDERAL COM 0409 #234H, planned,
plotted on top of its stacked offset #214H). The live wca_delta_ft (sql/30) still counts them; the sensitivity table
shows what dropping them does.
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import math
import subprocess
import sys
from dataclasses import replace
from pathlib import Path

import numpy as np
import pandas as pd

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO))

from scipy.spatial import cKDTree

from box import extent_package as pkg
from box import flag_cards as fc
from box import geology_io as gio
from box import tag_screen as ts
from box import tops_qc as tq
from box.bench_qc import (
    DEFAULT_PARAMS,
    NM_FIPS,
    _esc,
    _fmt,
    _project_xy_ft,
    _table,
)

MI = 5280.0
WCA = ("WCA_1", "WCA_2")
GRID_SURF = ("3BSPGS", "WOLFCAMP_XY", "WOLFCAMP_A", "WOLFCAMP-B1", "WOLFCAMP-B2", "WOLFCAMP-C")
GRID_IV = ("above 3BSPGS", "3BSPGS -> XY", "XY -> A", "A -> B1", "B1 -> B2", "B2 -> C", "below C")
# NM separation below local WCA_1/WCA_2 clean witnesses (1.5 mi, >= 3), median of consensus-'agree' wells per tag,
# as-of 2026-09-01 (FINDINGS §3). WCA_1 -25 / WCA_2 +48 are one WCA rung for this rule (the sub-split is not the question).
LADDER_FT = {"WCA": 0.0, "WCB_1": 291.0, "WCB_2": 564.0, "WCC": 814.0}
RULE = "V"
COUNTIES = ("Lea", "Eddy", "Pecos", "Ward", "Reeves", "Loving", "Culberson", "Winkler")


def _git_sha() -> str:
    try:
        return subprocess.check_output(["git", "rev-parse", "--short", "HEAD"], cwd=REPO, text=True).strip()
    except Exception:  # noqa: BLE001
        return "unknown"


def _q(conn, sql: str, params: dict | None = None) -> pd.DataFrame:
    with conn.cursor() as cur:
        cur.execute("SET TRANSACTION READ ONLY")
        cur.execute(sql, params)
        cols = [c.name for c in cur.description]
        rows = cur.fetchall()
    conn.rollback()
    return pd.DataFrame(rows, columns=cols)


def grid_interval(lon, lat, tvd, stack, tr) -> tuple[np.ndarray, pd.DataFrame]:
    """Interval of the geologist's V5 stack holding each depth + depth relative to each surface (+ = below it)."""
    x, y = tr.transform(np.asarray(lon, float), np.asarray(lat, float))
    z = tq.sample_stack(stack, np.column_stack([x, y]), GRID_SURF)
    rel = np.asarray(tvd, float)[:, None] - z
    names = np.array(GRID_IV, dtype=object)
    iv = np.where(np.isnan(rel).any(axis=1), "no grid", names[(np.nan_to_num(rel, nan=-1.0) >= 0).sum(axis=1)])
    return iv, pd.DataFrame(rel, columns=[f"rel_{s}" for s in GRID_SURF])


def _median_within(tree, pxy, ptvd, qxy, r_ft, keep=None, min_n=1, exclude_self=False):
    out = np.full(len(qxy), np.nan)
    n = np.zeros(len(qxy), int)
    for k, j in enumerate(tree.query_ball_point(qxy, r_ft)):
        j = np.asarray(j, int)
        if exclude_self:
            j = j[j != k]
        if keep is not None:
            j = j[keep[j]]
        n[k] = len(j)
        if len(j) >= min_n:
            out[k] = np.median(ptvd[j])
    return out, n


def _plane(tree, pxy, ptvd, qxy, r_ft, min_n=6):
    """Robust plane through the producers within r_ft, evaluated at each query point; returns (depth, gradient ft/mi)."""
    z, g = np.full(len(qxy), np.nan), np.full(len(qxy), np.nan)
    for k, j in enumerate(tree.query_ball_point(qxy, r_ft)):
        j = np.asarray(j, int)
        if len(j) < min_n:
            continue
        X = np.column_stack([np.ones(len(j)), (pxy[j, 0] - qxy[k, 0]) / MI, (pxy[j, 1] - qxy[k, 1]) / MI])
        c, *_ = np.linalg.lstsq(X, ptvd[j], rcond=None)
        r = ptvd[j] - X @ c
        mad = np.median(np.abs(r - np.median(r))) or 1.0
        ok = np.abs(r) <= 2.5 * 1.4826 * mad
        if ok.sum() >= min_n:
            c, *_ = np.linalg.lstsq(X[ok], ptvd[j][ok], rcond=None)
        z[k], g[k] = c[0], float(np.hypot(c[1], c[2]))
    return z, g


def stick_diagnosis(sticks: pd.DataFrame, prod: pd.DataFrame, stack, tr) -> pd.DataFrame:
    """Every Delaware Novi 'Wolfcamp B' stick with the H1 / H2 / H3 reads."""
    w = sticks[(sticks["formation"] == "Wolfcamp B") & sticks["midpoint_lon"].notna() & sticks["tvd"].notna()].reset_index(drop=True)
    sxy = _project_xy_ft(w["midpoint_lon"].values, w["midpoint_lat"].values)
    p = prod[prod["mid_lon"].notna() & prod["tvd_ft"].notna()].reset_index(drop=True)
    pxy = _project_xy_ft(p["mid_lon"].values, p["mid_lat"].values)
    t = cKDTree(pxy)
    ptvd, tag = p["tvd_ft"].values, p["formation_blueox"].values
    for b, codes in {"wca": WCA, "wcb1": ("WCB_1",), "wcb2": ("WCB_2",)}.items():
        w[f"med_{b}_3mi"], w[f"n_{b}_3mi"] = _median_within(t, pxy, ptvd, sxy, 3 * MI, keep=np.isin(tag, codes))
    w["anom"] = w["wca_delta_ft"] < -100
    # H2a: robust plane through WCA producers (TVD >= 2,500 ft) within 3 mi
    a = p[np.isin(tag, WCA) & (ptvd >= 2500)]
    axy = _project_xy_ft(a["mid_lon"].values, a["mid_lat"].values)
    w["wca_plane"], w["wca_grad_ft_mi"] = _plane(cKDTree(axy), axy, a["tvd_ft"].values, sxy, 3 * MI)
    w["delta_plane_ft"] = w["tvd"] - w["wca_plane"]
    # H2b / H3: Novi's own stack - nearest Novi Wolfcamp A / A XY stick within 1 mi
    na = sticks[sticks["formation"].isin(["Wolfcamp A", "Wolfcamp A XY"]) & sticks["midpoint_lon"].notna() & sticks["tvd"].notna()]
    nxy = _project_xy_ft(na["midpoint_lon"].values, na["midpoint_lat"].values)
    dist, idx = cKDTree(nxy).query(sxy, k=1)
    w["novi_wca_stick_tvd"] = np.where(dist <= MI, na["tvd"].values[idx], np.nan)
    w["wcb_minus_novi_wca_ft"] = w["tvd"] - w["novi_wca_stick_tvd"]
    # H3: geologist grids at the stick midpoint
    iv, rel = grid_interval(w["midpoint_lon"], w["midpoint_lat"], w["tvd"], stack, tr)
    w["grid_interval"] = iv
    w = pd.concat([w, rel], axis=1)
    w["grid_call"] = np.where(iv == "no grid", "no grid",
                              np.where(np.isin(iv, GRID_IV[:4]), "above B1 (WCA depth or shallower)", "in / below B1"))
    return w


def sensitivity(w: pd.DataFrame, prod: pd.DataFrame, drop: dict[str, set[str]]) -> pd.DataFrame:
    """Sticks < -100 ft per county when the WCA median is recomputed (midpoint geometry) without each producer set."""
    p = prod[prod["mid_lon"].notna() & prod["tvd_ft"].notna() & prod["formation_blueox"].isin(WCA)].reset_index(drop=True)
    pxy = _project_xy_ft(p["mid_lon"].values, p["mid_lat"].values)
    t = cKDTree(pxy)
    sxy = _project_xy_ft(w["midpoint_lon"].values, w["midpoint_lat"].values)
    api = p["api10"].astype(str).values
    out = {"live wca_delta_ft": w.groupby("county")["wca_delta_ft"].apply(lambda s: int((s < -100).sum()))}
    for name, s in {"recomputed (midpoints)": set(), **drop}.items():
        m, _ = _median_within(t, pxy, p["tvd_ft"].values, sxy, 3 * MI, keep=~np.isin(api, list(s)))
        out[name] = (w["tvd"] - m < -100).groupby(w["county"]).sum().astype(int)
    return pd.DataFrame(out).reindex(list(COUNTIES)).fillna(0).astype(int)


def rule_v(d: pd.DataFrame) -> pd.DataFrame:
    """Rule V on the screened frame: NM, Novi WOLFCAMP B, tag from Enverus in the WCA family, placed on the ladder."""
    cls = (d["state_code"] == NM_FIPS) & (d["novi_formation"] == "WOLFCAMP B") & (d["tag_source"] == "enverus") \
        & d["formation_blueox"].isin([*WCA, "WCXY"])
    pos = d["mid_lon"].notna() & d["tvd_ft"].notna()
    wit = d["cons_witness"].fillna(False).astype(bool) & d["formation_blueox"].isin(WCA) & ~cls & pos
    wxy = _project_xy_ft(d.loc[wit, "mid_lon"].values, d.loc[wit, "mid_lat"].values)
    t = cKDTree(wxy)
    c = d.loc[cls & pos]
    cxy = _project_xy_ft(c["mid_lon"].values, c["mid_lat"].values)
    med, n = _median_within(t, wxy, d.loc[wit, "tvd_ft"].values, cxy, DEFAULT_PARAMS.radius_ft, min_n=3)
    v = d.loc[cls].copy()
    v["v_below_wca_ft"] = pd.Series(c["tvd_ft"].values - med, index=c.index)
    v["v_n_wca_wit"] = pd.Series(n, index=c.index)
    rungs = np.array(list(LADDER_FT.values()))
    names = np.array(list(LADDER_FT), dtype=object)
    b = v["v_below_wca_ft"].values
    near = np.where(np.isnan(b), "no depth evidence", names[np.argmin(np.abs(np.nan_to_num(b)[:, None] - rungs[None, :]), axis=1)])
    v["v_rung"] = near
    v["screen_rule"] = np.where(pd.Series(near, index=v.index).isin(["WCB_1", "WCB_2", "WCC"]) & ~v["planned"], RULE, "")
    v.loc[v["planned"], "v_rung"] = "planned survey: not judged"
    v["screen_dest"] = np.where(v["screen_rule"] == RULE, v["v_rung"], None)
    v["screen_class"] = np.where(v["screen_rule"] == RULE, v["formation_blueox"] + "->" + v["screen_dest"].astype(str) + f" ({RULE})", "")
    v["screen_margin"] = v["v_below_wca_ft"]
    return v


def _card(df: pd.DataFrame, xy: np.ndarray, subj: pd.Series) -> str:
    i = int(df.index[df["api10"] == subj["api10"]][0])
    wide = fc._neighbourhood(df, xy, i, replace(DEFAULT_PARAMS, radius_ft=fc.SECTION_PREFILTER_FT))
    png, meta = fc.card_figure(subj, fc._neighbourhood(df, xy, i, DEFAULT_PARAMS), DEFAULT_PARAMS, dest=subj["screen_dest"],
                               section=fc.strike_section(subj, wide))
    own, dst = meta["bands"].get(subj["formation_blueox"]), meta["bands"].get(subj["screen_dest"])
    kv = (
        f"<b>{_esc(subj['api10'])}</b> {_esc(subj['well_name'])} · {_esc(subj['operator'])} · NM {_esc(subj['county'])} · "
        f"fp {_esc(subj['first_production_date'])} · lateral {_fmt(subj['lateral_length_ft'], 0)} ft · TVD <b>{_fmt(subj['tvd_ft'], 0)}</b>"
        f"{' · <b>planned survey</b>' if subj['planned'] else ''}{' · <b>permit-round TVD</b>' if subj['tvd_round'] else ''}<br>"
        f"tag <b>{_esc(subj['formation_blueox'])}</b> from Enverus <b>{_esc(subj['env_interval'])}</b>{' (via the sql/23 TVD correction)' if bool(subj.get('formation_blueox_tvd_corrected')) else ''} · Novi <b>{_esc(subj['novi_formation'])}</b> "
        f"→ proposed <b>{_esc(subj['screen_dest'])}</b> (rule V: {_fmt(subj['v_below_wca_ft'], 0)} ft below the median of "
        f"{_fmt(subj['v_n_wca_wit'])} clean WCA_1/WCA_2 witnesses within 1.5 mi; NM ladder WCB_1 +291 / WCB_2 +564 / WCC +814)<br>"
        f"geologist V5 grid: <b>{_esc(subj['grid_interval'])}</b> ({_fmt(subj.get('rel_WOLFCAMP-B1'), 0)} ft vs his B1 top, "
        f"{_fmt(subj.get('rel_WOLFCAMP-B2'), 0)} ft vs B2; + = below) · own band {_fmt(own['med'] if own else None, 0)} (n={_fmt(own['n'] if own else 0)}) · "
        f"{_esc(subj['screen_dest'])} band {_fmt(dst['med'] if dst else None, 0)} (n={_fmt(dst['n'] if dst else 0)}) · consensus {_esc(subj['cons_status'])} · "
        f"12-mo oil {_fmt(subj['oil12_kft'], 0)} bbl/kft{'' if subj['cohort'] else ' (not cohort)'} · GOR {_fmt(subj.get('gor12'), 0)} scf/bbl"
    )
    return f"<div class=card id=\"w{_esc(subj['api10'])}\"><div class=kv>{kv}</div><img src=\"{png}\"></div>"


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--out", type=Path, required=True)
    ap.add_argument("--cache", type=Path, default=None, help="pickle of the consensus-scored Delaware frame")
    a = ap.parse_args(argv)
    a.out.mkdir(parents=True, exist_ok=True)
    from pyproj import Transformer

    from etl.db import get_connection
    from scripts.box_family_qc import _scored

    scored = _scored("delaware", a.cache).reset_index(drop=True)
    scored["api10"] = scored["api10"].astype(str)
    with get_connection() as conn:
        labels = ts.pull_labels(conn, "delaware", scored["api10"].tolist())
        sticks = _q(conn, """
            SELECT il.stick_id, il.category, il.county, il.formation, il.operator, il.pad_name, il.tvd,
                   il.midpoint_lon, il.midpoint_lat, ifb.formation_blueox AS stick_blueox, el.wca_delta_ft
            FROM curated.intel_locations il JOIN curated.erebor_locations el USING (stick_id)
            LEFT JOIN curated.intel_formation_blueox ifb USING (stick_id)
            WHERE il.basin = 'delaware'""")
        rec = _q(conn, """
            SELECT pf.stick_id, pf.coverage, fr.run_id FROM box.pud_forecast pf JOIN box.forecast_run fr USING (run_id)
            WHERE fr.is_record AND fr.basin = 'delaware'""")
        mem = _q(conn, """
            SELECT m.api10, a.basin, a.bench, m.included FROM box.tc_member m JOIN box.type_curve tc USING (tc_id)
            JOIN box.tc_area ta USING (area_id) JOIN box.extent a USING (extent_id)
            WHERE tc.is_record AND tc.stream = 'oil' AND a.basin = 'delaware'""")
    for c in ("tvd", "midpoint_lon", "midpoint_lat", "wca_delta_ft"):
        sticks[c] = pd.to_numeric(sticks[c], errors="coerce")
    stack = tq.load_stack(pkg.GRID_DIR, GRID_SURF)
    tr = Transformer.from_crs("EPSG:4326", gio.GEOLOGY_CRS, always_xy=True)

    d = ts.screen(scored, labels)
    d["st"] = np.where(d["state_code"] == NM_FIPS, "NM", "TX")
    pos = d["mid_lon"].notna() & d["tvd_ft"].notna()
    d["grid_interval"] = "no position"
    iv, rel = grid_interval(d.loc[pos, "mid_lon"], d.loc[pos, "mid_lat"], d.loc[pos, "tvd_ft"], stack, tr)
    d.loc[pos, "grid_interval"] = iv
    for col in rel.columns:
        d.loc[pos, col] = rel[col].values

    # ---- stick side --------------------------------------------------------------------------------------------
    real = d[~d["planned"]]  # planned surveys are no evidence (module docstring)
    w = stick_diagnosis(sticks, real, stack, tr)
    w = w.merge(rec[["stick_id", "coverage"]], on="stick_id", how="left")
    w["coverage"] = w["coverage"].fillna("not in record run")
    an = w[w["anom"]]
    by_cty = pd.DataFrame({
        "wcb_sticks": w.groupby("county").size(), "anomalous": an.groupby("county").size(),
        "anom_median_wca_delta_ft": an.groupby("county")["wca_delta_ft"].median(),
        "anom_median_delta_vs_wca_plane_ft": an.groupby("county")["delta_plane_ft"].median(),
        "anom_median_wca_gradient_ft_per_mi": an.groupby("county")["wca_grad_ft_mi"].median(),
        "anom_median_wcb_minus_novi_wca_stick_ft": an.groupby("county")["wcb_minus_novi_wca_ft"].median(),
        "anom_shallower_than_novi_wca_stick": an.groupby("county")["wcb_minus_novi_wca_ft"].apply(lambda s: int((s < 0).sum())),
        "normal_median_wcb_minus_novi_wca_stick_ft": w[~w["anom"]].groupby("county")["wcb_minus_novi_wca_ft"].median(),
        "anom_grid_above_B1": an.groupby("county")["grid_call"].apply(lambda s: int((s == "above B1 (WCA depth or shallower)").sum())),
        "anom_grid_in_below_B1": an.groupby("county")["grid_call"].apply(lambda s: int((s == "in / below B1").sum())),
        "anom_no_grid": an.groupby("county")["grid_call"].apply(lambda s: int((s == "no grid").sum())),
        "anom_median_ft_below_XY_top": an.groupby("county")["rel_WOLFCAMP_XY"].median(),
        "anom_median_ft_below_B1_top": an.groupby("county")["rel_WOLFCAMP-B1"].median(),
        "anom_box_record_covered": an.groupby("county")["coverage"].apply(lambda s: int(s.str.startswith("covered").sum())),
    }).reindex(list(COUNTIES)).round(0)
    by_cty.to_csv(a.out / "sticks_by_county.csv")
    pd.crosstab(an["county"], an["grid_interval"]).reindex(list(COUNTIES)).fillna(0).astype(int).to_csv(a.out / "sticks_anomalous_grid_interval.csv")
    pd.crosstab(an["grid_call"], an["coverage"]).to_csv(a.out / "sticks_anomalous_box_coverage.csv")
    an[["stick_id", "category", "county", "operator", "pad_name", "tvd", "stick_blueox", "wca_delta_ft", "delta_plane_ft",
        "wcb_minus_novi_wca_ft", "grid_interval", "rel_WOLFCAMP_XY", "rel_WOLFCAMP-B1", "coverage", "midpoint_lon", "midpoint_lat"]] \
        .sort_values(["county", "stick_id"]).to_csv(a.out / "sticks_anomalous.csv", index=False)

    # ---- producer side -----------------------------------------------------------------------------------------
    nm_wc = real[(real["st"] == "NM") & real["formation_blueox"].isin(["WCXY", "WCA_1", "WCA_2", "WCB_1", "WCB_2", "WCC"])]
    prod_grid = pd.crosstab([nm_wc["county"], nm_wc["formation_blueox"]], nm_wc["grid_interval"])
    prod_grid.to_csv(a.out / "producers_nm_grid_interval.csv")
    nm_wca = real[(real["st"] == "NM") & real["formation_blueox"].isin(WCA)]
    screen_deep = set(real.loc[real["formation_blueox"].isin(WCA) & real["screen_dest"].isin(["WCB_1", "WCB_2", "WCC", "WCD"]), "api10"])
    v = rule_v(d)
    flagged = v[v["screen_rule"] == RULE]
    grid_deep = set(nm_wca.loc[nm_wca["grid_interval"].isin(GRID_IV[4:]), "api10"])
    sens = sensitivity(w, d, {"real surveys only (planned dropped)": set(d.loc[d["planned"], "api10"])})
    sens = sens.join(sensitivity(w, real, {"real only, minus screen-flagged WCA->deeper": screen_deep,
                                           "real only, minus rule-V flags": set(flagged["api10"]),
                                           "real only, minus grid-deep NM WCA (upper bound)": grid_deep | screen_deep | set(flagged["api10"])})
                     .drop(columns=["live wca_delta_ft", "recomputed (midpoints)"]))
    sens.to_csv(a.out / "sensitivity_wca_median.csv")

    cols = ["screen_class", "api10", "well_name", "operator", "county", "formation_blueox", "screen_dest", "novi_formation", "env_interval",
            "tvd_ft", "v_below_wca_ft", "v_n_wca_wit", "grid_interval", "rel_WOLFCAMP-B1", "rel_WOLFCAMP-B2", "cons_status", "cons_suggest",
            "formation_blueox_tvd_corrected", "planned", "first_production_date", "cohort", "oil12_kft", "gor12", "mid_lon", "mid_lat"]
    v.sort_values(["screen_class", "api10"])[cols].to_csv(a.out / "rule_v_class.csv", index=False)
    in_pool = mem[mem["api10"].isin(flagged["api10"]) & mem["included"]]
    cls = flagged.groupby("screen_class").agg(n=("api10", "size"), n_cohort=("cohort", "sum"),
                                              median_below_wca_ft=("v_below_wca_ft", "median"),
                                              grid_B1_or_deeper=("grid_interval", lambda s: int(s.isin(GRID_IV[4:]).sum())),
                                              grid_above_B1=("grid_interval", lambda s: int(s.isin(GRID_IV[:4]).sum())))
    cls["in_box_record_pool"] = [int(in_pool["api10"].isin(flagged.loc[flagged["screen_class"] == c, "api10"]).sum()) for c in cls.index]
    cls.to_csv(a.out / "classes.csv")

    # cards: round 1 = ts.ROUND1 per class, cohort first, even across the margin (ts.sample)
    dd = real.copy().reset_index(drop=True)  # cards never draw a planned-survey well
    rp = dd["mid_lon"].notna() & dd["tvd_ft"].notna()
    xy = np.full((len(dd), 2), np.nan)
    xy[rp.values] = _project_xy_ft(dd.loc[rp, "mid_lon"].values, dd.loc[rp, "mid_lat"].values)
    vr = v.set_index("api10")
    for c in ("v_below_wca_ft", "v_n_wca_wit", "screen_rule", "screen_dest", "screen_class", "screen_margin"):
        dd[c] = dd["api10"].map(vr[c])
    rows, sections = [], []
    for name, g in flagged.groupby("screen_class"):
        g = dd[dd["api10"].isin(g["api10"])]
        pick = ts.sample(g, ts.ROUND1)
        sections.append(f"<h2 id=\"c{_esc(name)}\">{_esc(name)} — {len(g)} flagged ({int(g['cohort'].sum())} cohort); {len(pick)} cards</h2>"
                        + "".join(_card(dd, xy, s) for _, s in pick.iterrows()))
        rows += [{**{k: s.get(k) for k in cols}, "verdict": "", "verdict_source": ""} for _, s in pick.iterrows()]
    sample_path = a.out / "cards_sample.csv"
    if sample_path.exists():
        fc.guard_verdict_file(sample_path)
    pd.DataFrame(rows).to_csv(sample_path, index=False)

    # proposed seed: every flagged well to its rule-V destination; re-derived from the verdicts with ts.override_seed
    seed = flagged[["api10", "screen_dest", "formation_blueox", "screen_class"]].rename(columns={"screen_dest": "corrected_code", "formation_blueox": "was"})
    seed["note"] = "PROPOSED " + dt.datetime.now(tz=dt.UTC).astimezone().date().isoformat() + " (Lea/Eddy WC screen, " + seed["screen_class"] + \
        "): Novi WOLFCAMP B, Enverus WCA; depth on the NM ladder; NOT ratified, NOT applied"
    seed[["api10", "corrected_code", "was", "note"]].sort_values("api10").to_csv(a.out / "proposed_override_seed.csv", index=False, lineterminator="\n")

    built = dt.datetime.now(tz=dt.UTC).astimezone().isoformat(timespec="seconds")
    page = [
        f"<!doctype html><html><head><meta charset=\"utf-8\"><title>Lea Eddy WCB cards</title><style>{fc._CSS}</style></head><body>",
        "<h1>Lea / Eddy Wolfcamp — producer review cards (rule V, round 1)</h1>",
        (f"<div class=meta>Built {built}, git {_git_sha()}, read-only; {len(d):,} Delaware producing horizontals as of {_esc(scored.attrs.get('asof'))}. "
        "Rule V: NM wells Novi calls WOLFCAMP B whose tag came from Enverus as WCA_1 / WCA_2 / WCXY (sql/16 treats Novi WOLFCAMP B as coarse, so "
        "the tag screen counts it as no vote). Placed by TVD minus the median of clean WCA_1/WCA_2 witnesses within 1.5 mi (class wells excluded), "
        "nearest rung of the NM ladder (WCA 0 / WCB_1 +291 / WCB_2 +564 / WCC +814 ft). Mark each card <b>accept</b> or <b>reject</b> in "
        "<code>cards_sample.csv</code> (column <code>verdict</code>; a bench code = your own call on the well). Sequential gate as the tag screen: "
        "5/5 accept takes the class, 0–1/5 rejects it, otherwise 5 more cards and 7/10. Planned-survey wells are neither judged nor drawn (their TVD and lateral path are the pre-drill plan). Nothing here is applied: "
        "accepted wells go to ref.formation_tag_overrides only on your separate go; an apply moves them out of the Delaware BOX record's pools at its "
        "next build.</div>"),
        _table(["class", "flagged", "cohort", "median ft below local WCA", "grid B1 or deeper", "grid above B1", "in a BOX record oil pool"],
               [[n, _fmt(int(r.n)), _fmt(int(r.n_cohort)), _fmt(r.median_below_wca_ft, 0), _fmt(int(r.grid_B1_or_deeper)), _fmt(int(r.grid_above_B1)),
                 _fmt(int(r.in_box_record_pool))] for n, r in cls.iterrows()]),
        *sections, "</body></html>",
    ]
    (a.out / "cards.html").write_text("".join(page), encoding="utf-8")

    def _int(x):
        return {str(k): int(v) for k, v in x.items()}

    summary = {
        "built_at": built, "git_sha": _git_sha(), "asof": str(scored.attrs.get("asof")), "n_producers": len(d),
        "sticks": {"wcb_by_county": _int(w.groupby("county").size()), "anomalous_by_county": _int(an.groupby("county").size()),
                   "anomalous_grid_call": _int(an["grid_call"].value_counts()),
                   "anomalous_box_record_covered": int(an["coverage"].str.startswith("covered").sum())},
        "producers": {"nm_wca": len(nm_wca), "nm_wca_cons_status": _int(nm_wca["cons_status"].value_counts()),
                      "screen_wca_to_deeper_delaware": len(screen_deep),
                      "screen_wca_to_deeper_nm": int(nm_wca["screen_dest"].isin(["WCB_1", "WCB_2", "WCC", "WCD"]).sum()),
                      "nm_wca_grid_B1_or_deeper": len(grid_deep),
                      "rule_v_class": len(v), "rule_v_planned_not_judged": int(v["planned"].sum()),
                      "rule_v_rungs": _int(v["v_rung"].value_counts()), "rule_v_flagged": len(flagged),
                      "rule_v_flagged_in_box_record_pool": int(in_pool["api10"].nunique())},
        "ladder_ft": LADDER_FT, "cards": len(rows), "classes": _int(flagged["screen_class"].value_counts()),
    }
    (a.out / "summary.json").write_text(json.dumps(summary, indent=1, default=lambda x: None if isinstance(x, float) and not math.isfinite(x) else str(x)),
                                        encoding="utf-8")
    print(json.dumps(summary, indent=1, default=str))
    print(by_cty.to_string())
    print(sens.to_string())
    print(cls.to_string())
    return 0


if __name__ == "__main__":
    sys.exit(main())
