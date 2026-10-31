"""BOX step 21a — Midland pre-registration evidence (READ ONLY; nothing is forecast, scored or stored).

    python -m scripts.box_step21a pool        # copy the step-20 sets of record into box/step21.POOL_DIR + MANIFEST.json
    python -m scripts.box_step21a evidence    # counts, reach, lateral classes, proximity, water reach -> docs/box/step21a-2026-10-31
    python -m scripts.box_step21a render      # re-render index.html from the written files (DB-free)

Evidence for box/step21.DEFINITION (docs/box/step21a-2026-10-31/PREREGISTRATION.md):
  1. D53 / D52 PACKAGE COUNTS per group x cutoff x horizon, tuning vs holdout (the step-14 counter, scripts.box_thin_bench
     .bench_counts, unchanged) and what they allow: the record treatment (box/step21.record_treatment), the D99 cells, the
     tier route. Counts only — no forecast and no error is computed for any package.
  2. Measured-water PACKAGES per horizon (a package with >= 1 measured-water member that reached k; scripts/box_water11's rule).
  3. Undrilled sticks in each record extent (D117 universe: PUD + RES; remaining_pud / conflict / not reconciled; >= 50 % inside).
  4. Oil and measured-water analog REACH from those sticks (circle: lower bound on the real search); water top-operator share.
  5. Long laterals: pool producers > 15,000 ft (now analogs, D129), sticks by length class, and the observed per-ft-vs-length
     ratio on producers in TUNING blocks only (block x first-production-year cells) next to the Cui & Cross curve.
  6. Proximity on Midland producers (D112-D116 pattern): drilled-children links + configuration -> D114 precedent per bench
     pair, the ladder rungs a Midland factor table could fill, and every in-extent stick's configuration -> outcome (precedent
     Midland's; factor = the Delaware D113 table, INTERIM until 21b fits the Midland one); DEAN body vs loop addition (D143);
     the warehouse-tag bench label as a sensitivity.
  7. Production-sharing share of each group's modern producers (20b section 3 asks for the split in 21b; counts here).
Reads curated / box inside READ ONLY transactions.
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import shutil
import subprocess
import sys
import time
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
import shapely
from shapely.geometry import shape

from box import dev_factor_report as dfr
from box import edge_gap as eg
from box import edge_gap_report as egr
from box import exclusions
from box import holdout as ho
from box import production as prod
from box import prox_dose as pdz
from box import prox_pud as pp
from box import prox_pud_report as ppr
from box import prox_study as ps
from box import prox_study_report as psr
from box import prox_validate as pv
from box import spacing3d_report as s3r
from box import step21 as st
from box import step21_evidence as ev
from box import tc_area_report as tar
from box import tc_curve_report as rep
from box import thin_bench as tb
from box.edge_gap_report import _CSS, _table
from box.tc_curve_report import _read

OUT = st.DOCS
RUNS = Path("runs") / "step21a"
ACTUALS = dt.date.fromisoformat(st.DEFINITION["folds"]["actuals_through"])
BASIN = "midland"
WC, SPR = ("WCA_1", "WCB_1", "WCB_2", "WCC", "WCD"), ("MS", "JM", "LSSH", "DEAN")

_LABEL_SQL = """
SELECT we.api10, q.water_source, COALESCE(we.has_production_sharing, false)
FROM curated.wells_enriched we LEFT JOIN curated.water_data_quality q ON q.api10 = we.api10
WHERE we.api10 = ANY(%(a)s)
"""
_TVD_SQL = "SELECT stick_id, tvd FROM curated.erebor_locations WHERE stick_id = ANY(%(ids)s)"


def _git(*a: str) -> str:
    return subprocess.run(["git", *a], capture_output=True, text=True, check=True).stdout.strip()


def _sha() -> str:
    dirty = _git("status", "--porcelain", "--untracked-files=no")
    return _git("rev-parse", "HEAD") + ("+dirty" if dirty else "")


def _add_months(d: dt.date, n: int) -> dt.date:
    m = d.month - 1 + n
    return dt.date(d.year + m // 12, m % 12 + 1, 1)


def _pct(v: np.ndarray, q: tuple[float, ...] = (10, 50, 90)) -> dict[str, float] | None:
    v = np.asarray(v, float)
    v = v[np.isfinite(v)]
    return dict(zip(("p10", "p50", "p90"), np.percentile(v, q).round(2).tolist(), strict=True)) if len(v) else None


# ----------------------------------------------------------------------------
# 0. pool
# ----------------------------------------------------------------------------


def make_pool() -> dict[str, Any]:
    st.POOL_DIR.mkdir(parents=True, exist_ok=True)
    entries, seen = [], {}
    for g, (b, e, src) in st.GROUPS.items():
        dst = st.POOL_DIR / f"wells_final_{b}.csv"
        shutil.copyfile(src, dst)
        d = pd.read_csv(dst, dtype={"api10": str})
        if set(d["box_bench"]) != {b}:
            raise ValueError(f"{src}: box_bench is not {b} on every row")
        for a in d["api10"]:
            if a in seen:
                raise ValueError(f"{a} sits in both {seen[a]} and {g}")
            seen[a] = g
        entries.append({"group": g, "bench": b, "extent_id": e, "source": src, "source_commit": _git("log", "-1", "--format=%H", "--", src),
                        "file": dst.as_posix(), "sha256_lf": st.sha256_file(dst), "rows": len(d)})
    man = {"built_at": dt.datetime.now(tz=dt.UTC).astimezone().isoformat(timespec="seconds"), "code_sha": _sha(), "basin": BASIN,
           "rule": st.DEFINITION["pools"]["rule"], "files": entries, "n_wells": len(seen)}
    (st.POOL_DIR / "MANIFEST.json").write_text(json.dumps(man, indent=1), encoding="utf-8")
    return man


def load_pools() -> dict[str, pd.DataFrame]:
    man = json.loads((st.POOL_DIR / "MANIFEST.json").read_text(encoding="utf-8"))
    out = {}
    for e in man["files"]:
        if st.sha256_file(Path(e["file"])) != e["sha256_lf"]:
            raise RuntimeError(f"{e['file']} differs from its manifest")
        w, _ = exclusions.drop(egr.load_final_sets(st.POOL_DIR, (e["bench"],)))
        out[e["group"]] = w
    return out


# ----------------------------------------------------------------------------
# 1-2. package counts
# ----------------------------------------------------------------------------


def counts_for(conn: Any, pools: dict[str, pd.DataFrame], ext: dict[str, dict[str, Any]], labels: pd.DataFrame) -> dict[str, Any]:
    from scripts.box_thin_bench import bench_counts

    allw = pd.concat(pools.values(), ignore_index=True)
    modern = allw[np.array([f >= dt.date(2016, 1, 1) for f in allw["first_production_date"]])]
    u = s3r.pull_universe(conn, modern)
    meas = set(labels.loc[labels["water_source"] == "measured", "api10"])
    counts_all, judge_all, water_rows, route = [], [], [], {}
    for g, w in pools.items():
        t0 = time.time()
        counts, frame = bench_counts(conn, w, ext[g]["geom_ft"], u, ACTUALS)
        j = tb.judgeability(counts)
        counts_all.append(counts.assign(group=g))
        judge_all.append(j.assign(group=g))
        jj = j.set_index("horizon")
        raw = {int(k): int(jj.at[k, "pooled_holdout_raw"]) for k in jj.index}
        wf = {int(k): int(jj.at[k, "pooled_holdout_wf"]) for k in jj.index}
        treat = st.record_treatment(wf)
        cells = st.d99_horizons(wf if treat == st.PROX_WF else raw)
        route[g] = {"record_treatment": treat, "d99_horizons": list(cells), "tier_route": st.tier_route(wf if treat == st.PROX_WF else raw),
                    "pooled_holdout_raw": raw, "pooled_holdout_wf": wf, "verdict_class_step14": tb.verdict_class(j)}
        if len(frame):
            frame["measured"] = frame["api10"].isin(meas)
            for (c, held), s in frame.groupby(["cutoff", "held_out"]):
                m = s[s["measured"]]
                r = {"group": g, "cutoff": c, "side": "holdout" if held else "tuning", "n_wells": len(s), "n_measured_wells": len(m)}
                for k in (12, 24, 36):
                    if (c, k) in tb.UNSCORED_EARLY:
                        r[f"pk_w{k}"] = 0
                    else:
                        r[f"pk_w{k}"] = int(m.loc[m[f"reached_{k}"], "package"].nunique())
                water_rows.append(r)
        print(f"[counts] {g}: {treat}, D99 {cells}, {time.time() - t0:.0f} s", flush=True)
    wp = pd.DataFrame(water_rows)
    wpool = wp.groupby(["group", "side"])[["n_wells", "n_measured_wells", "pk_w12", "pk_w24", "pk_w36"]].sum().reset_index()
    return {"counts": pd.concat(counts_all, ignore_index=True), "judge": pd.concat(judge_all, ignore_index=True), "route": route,
            "water_packages": wp, "water_pooled": wpool}


# ----------------------------------------------------------------------------
# 3-5. sticks, reach, lateral
# ----------------------------------------------------------------------------


def sticks_in_extents(conn: Any) -> pd.DataFrame:
    U = prod.universe(conn, basins=[BASIN])
    benches = {b: g for g, (b, _, _) in st.GROUPS.items()}
    U = U[U["bench"].isin(benches) & U["in_scope"].astype(bool)].copy()
    U["group"] = U["bench"].map(benches)
    U["inside"] = U["inside_extent"].fillna(False).astype(bool)
    U["x"], U["y"] = dfr._xy(U["mid_lon"], U["mid_lat"])
    return U


def pool_xy(w: pd.DataFrame, cap_ft: float | None = None, label_ok: set[str] | None = None) -> pd.DataFrame:
    """Analog-eligible pool wells at the actuals date: first production >= 2016, >= 6 months produced, lateral >= 5,000 ft
    (r2's lower bound; `cap_ft` restores an upper bound for the comparison)."""
    six = _add_months(ACTUALS, -5)
    lat_ft = pd.to_numeric(w["lateral_length_ft"], errors="coerce")
    ok = np.array([dt.date(2016, 1, 1) <= f <= six for f in w["first_production_date"]]) & (lat_ft >= 5_000).to_numpy()
    if cap_ft is not None:
        ok &= (lat_ft <= cap_ft).to_numpy()
    if label_ok is not None:
        ok &= w["api10"].isin(label_ok).to_numpy()
    p = w[ok].copy()
    p["x"], p["y"] = dfr._xy(p["mid_lon"], p["mid_lat"])
    return p


def reach_tables(U: pd.DataFrame, pools: dict[str, pd.DataFrame], labels: pd.DataFrame) -> dict[str, Any]:
    meas = set(labels.loc[labels["water_source"] == "measured", "api10"])
    share = labels.set_index("api10")["sharing"]
    rows, wrows, lrows, stick_rows = [], [], [], []
    for g, w in pools.items():
        s = U[(U["group"] == g) & U["inside"]]
        sxy = s[["x", "y"]].to_numpy(float)
        p = pool_xy(w)
        pc = pool_xy(w, cap_ft=15_000.0)
        r = ev.reach(sxy, p[["x", "y"]].to_numpy(float), ev.OIL_RINGS_MI)
        rc = ev.reach(sxy, pc[["x", "y"]].to_numpy(float), ev.OIL_RINGS_MI)
        rows.append({"group": g, "sticks_in_extent": len(s), "pool_eligible": len(p), "pool_gt_15k": int((pd.to_numeric(p["lateral_length_ft"]) > 15_000).sum()),
                     "d10_mi": _pct(r["d10_mi"]), "ring10": r["ring"].value_counts(normalize=True).round(3).to_dict(),
                     "ring_moves_vs_15k_cap": int((r["ring"].to_numpy() != rc["ring"].to_numpy()).sum()),
                     "d10_gain_mi_vs_15k_cap": _pct((rc["d10_mi"] - r["d10_mi"]).to_numpy())})
        pm = pool_xy(w, label_ok=meas)
        rw = ev.reach(sxy, pm[["x", "y"]].to_numpy(float), ev.WATER_RINGS_MI)
        wc = np.array([ev.water_class(a, b) for a, b in zip(rw["d3_mi"], rw["d10_mi"], strict=True)])
        top = ev.top_operator_share(sxy, pm[["x", "y"]].to_numpy(float), pm["operator"].fillna("?").tolist())
        ops = pm["operator"].fillna("?").value_counts(normalize=True)
        wrows.append({"group": g, "sticks_in_extent": len(s), "measured_pool": len(pm), "pool_eligible": len(p),
                      "measured_share_of_pool": round(len(pm) / len(p), 3) if len(p) else None,
                      "d10_mi": _pct(rw["d10_mi"]), "ring10": rw["ring"].value_counts(normalize=True).round(3).to_dict(),
                      "thin": int((wc == "thin").sum()), "fallback": int((wc == "fallback").sum()),
                      "top_operator_share_p50": float(np.nanmedian(top)) if np.isfinite(top).any() else None,
                      "sticks_one_operator_ge_half": int(np.nansum(top >= 0.5)),
                      "pool_top_operator": ops.index[0] if len(ops) else None, "pool_top_operator_share": round(float(ops.iloc[0]), 3) if len(ops) else None})
        ll = pd.to_numeric(s["ll_ft"], errors="coerce").fillna(pd.to_numeric(s["stick_ft"], errors="coerce"))
        cls = pd.Series([ev.length_class(x) or "<5k" for x in ll])
        lrows.append({"group": g, "sticks_in_extent": len(s), **{f"sticks_{k}": int(v) for k, v in cls.value_counts().items()},
                      "share_gt_12_5k": round(float((ll > 12_500).mean()), 3) if len(ll) else None,
                      "share_gt_15k": round(float((ll > 15_000).mean()), 3) if len(ll) else None,
                      "cui_at_p90_len": round(float(ev.lat.lateral_efficiency(float(np.nanpercentile(ll, 90)))), 3) if len(ll) else None})
        m = pool_xy(w)
        stick_rows.append(s.assign(d10_oil_mi=r["d10_mi"].to_numpy(), ring_oil=r["ring"].to_numpy(), d10_water_mi=rw["d10_mi"].to_numpy(),
                                   water_class=wc, water_top_op_share=top, length_ft=ll.to_numpy())[
            ["stick_id", "group", "bench", "category", "recon_status", "pad_name", "mid_lon", "mid_lat", "length_ft", "d10_oil_mi", "ring_oil",
             "d10_water_mi", "water_class", "water_top_op_share"]])
        sh = m["api10"].map(share).fillna(False).astype(bool)
        rows[-1]["sharing_share_of_pool"] = round(float(sh.mean()), 3) if len(sh) else None
    return {"oil": pd.DataFrame(rows), "water": pd.DataFrame(wrows), "length": pd.DataFrame(lrows).fillna(0),
            "sticks": pd.concat(stick_rows, ignore_index=True)}


def per_ft_tables(pools: dict[str, pd.DataFrame]) -> pd.DataFrame:
    """D129: oil12 per kft by lateral class, producers first-producing 2016-01 ... 2025-07 (12 months by the actuals date) in
    TUNING blocks only."""
    last_fp = _add_months(ACTUALS, -12)
    frames = []
    for g, w in pools.items():
        d = w[np.array([dt.date(2016, 1, 1) <= f < last_fp for f in w["first_production_date"]])].copy()
        x, y = dfr._xy(d["mid_lon"], d["mid_lat"])
        d = d[~ho.is_holdout(x, y)].copy()
        bx, by = ho.blocks(*dfr._xy(d["mid_lon"], d["mid_lat"]))
        d["block"] = list(zip(bx.tolist(), by.tolist(), strict=True))
        d["fp_year"] = [f.year for f in d["first_production_date"]]
        d["lateral_ft"] = pd.to_numeric(d["lateral_length_ft"], errors="coerce")
        d["oil12_kft"] = pd.to_numeric(d["oil12_kft"], errors="coerce")
        frames.append(d.assign(group=g)[["group", "block", "fp_year", "lateral_ft", "oil12_kft"]])
    allp = pd.concat(frames, ignore_index=True)
    sets = {**{g: [g] for g in st.GROUPS}, "Midland Wolfcamp (5)": [f"MID_{b}" for b in WC], "Midland Spraberry (4)": [f"MID_{b}" for b in SPR],
            "Midland all (9)": list(st.GROUPS)}
    out = []
    for name, gs in sets.items():
        sub = allp[allp["group"].isin(gs)].copy()
        sub["block"] = [(g_, b_) for g_, b_ in zip(sub["group"], sub["block"], strict=True)]  # cells never mix benches
        out.append(ev.per_ft_by_length(sub).assign(set=name))
    return pd.concat(out, ignore_index=True)


# ----------------------------------------------------------------------------
# 6. proximity
# ----------------------------------------------------------------------------


def box_bench_map(pools: dict[str, pd.DataFrame]) -> dict[str, str]:
    return {a: b for w in pools.values() for a, b in zip(w["api10"], w["box_bench"], strict=True)}


def proximity(conn: Any, pools: dict[str, pd.DataFrame], U: pd.DataFrame, ext: dict[str, dict[str, Any]]) -> dict[str, Any]:
    t0 = time.time()
    RUNS.mkdir(parents=True, exist_ok=True)
    u = psr.pull_universe(conn, BASIN)
    tag = dict(zip(u["api10"], u["bench"], strict=True))
    bb = box_bench_map(pools)
    moved = [a for a in u["api10"] if a in bb and bb[a] != tag[a]]
    u["bench"] = [bb.get(a, b) for a, b in zip(u["api10"], u["bench"], strict=True)]
    kids = psr.children_of(u, BASIN)
    print(f"[prox] universe {len(u):,}, children {len(kids):,}, box_bench relabels {len(moved):,} ({time.time() - t0:.0f} s)", flush=True)
    lk = RUNS / "links.pkl"
    if lk.exists():
        L = pd.read_pickle(lk)
    else:
        L = psr.build_links(u, kids)
        L.to_pickle(lk)
    kids.to_pickle(RUNS / "children.pkl")
    print(f"[prox] child links {len(L):,} ({time.time() - t0:.0f} s)", flush=True)
    kc = pdz.configuration(list(kids["api10"]), L).merge(kids[["api10", "bench", "fp", "geom"]], on="api10", how="left")
    prec = pp.precedent(kc, pp.siblings(L))
    # ladder fill on children that a tuning fold could score (fp in the fold windows, in the group's extent, tuning block)
    lo, hi = dt.date(2019, 12, 1), dt.date(2025, 12, 1)
    mid = [g.interpolate(0.5, normalized=True) for g in kc["geom"]]
    kc["mx"], kc["my"] = [p.x for p in mid], [p.y for p in mid]
    fill_rows = []
    for g, (b, _, _) in st.GROUPS.items():
        e = ext[g]["geom_ft"]
        sel = kc[(kc["bench"] == b) & np.array([lo <= f < hi for f in kc["fp"]])]
        inside = np.array([e.contains(shapely.Point(x, y)) for x, y in zip(sel["mx"], sel["my"], strict=True)], bool) if len(sel) else np.zeros(0, bool)
        sel = sel[inside]
        sel = sel[~ho.is_holdout(sel["mx"].to_numpy(float), sel["my"].to_numpy(float))]
        f = ev.ladder_fill(pv.ladder_keys(sel)) if len(sel) else pd.DataFrame(columns=["rung", "key", "n_children", "fills"])
        multi = sel[sel["config_class"].notna() & ((sel["config_class"] == "mixed") | (sel["n_parents_total"] >= 2))]
        fill_rows.append(f.assign(group=g, n_tuning_children=len(sel), n_multi=len(multi)))
    fill = pd.concat(fill_rows, ignore_index=True)

    # PUD side: every in-extent undrilled stick, D115 (no shielding exemption), reference date = the actuals date
    s = U[U["inside"]].copy()
    tvd = pd.DataFrame(_read(conn, _TVD_SQL, {"ids": [int(x) for x in s["stick_id"]]}), columns=["stick_id", "tvd_ft"])
    conn.rollback()
    s = s.merge(tvd, on="stick_id", how="left")
    s["tvd_ft"] = pd.to_numeric(s["tvd_ft"], errors="coerce")
    s["geom"] = eg.to_ft([shapely.from_wkt(w) for w in s["wkt"]])
    p = pd.DataFrame({"location_id": s["stick_id"].astype(str), "formation_blueox": s["bench"], "tvd_ft": s["tvd_ft"], "geom": s["geom"]})
    lp = RUNS / "pud_links.pkl"
    if lp.exists():
        Lp = pd.read_pickle(lp)
    else:
        Lp = ppr.pud_links(p, u, ACTUALS)
        Lp.to_pickle(lp)
    print(f"[prox] stick links {len(Lp):,} ({time.time() - t0:.0f} s)", flush=True)
    ids = list(p["location_id"])
    hair = pp.haircut_lookup(pd.read_csv(ppr.HAIRCUT_TABLE))

    def outcomes(links: pd.DataFrame, prec_: dict[str, dict[str, int]]) -> pd.DataFrame:
        cfg = pdz.configuration(ids, links.assign(permit=False)).set_index("api10")
        cfg["bench"] = p.set_index("location_id")["formation_blueox"].reindex(cfg.index)
        return cfg.join(pp.decide_all(cfg, hair, prec_))

    d = outcomes(Lp, prec)
    s = s.drop(columns=["geom", "wkt"]).assign(location_id=s["stick_id"].astype(str)).merge(d.drop(columns="bench"), left_on="location_id", right_index=True, how="left")
    s["recent_producers"] = s["location_id"].map(ppr.recent_flags(Lp)).fillna(0).astype(int)
    s["permit_parents"] = s["location_id"].map(ppr.permit_flags(Lp)).fillna(0).astype(int)

    # sensitivity: the warehouse tag as the bench label (classes recomputed from the stored dz; shielding not re-stamped)
    def retag(links: pd.DataFrame, child_tag: dict[str, str]) -> pd.DataFrame:
        x = links.copy()
        x["child_bench"] = [child_tag.get(c, b) for c, b in zip(x["child"], x["child_bench"], strict=True)]
        x["parent_bench"] = [tag.get(a, b) for a, b in zip(x["parent"], x["parent_bench"], strict=True)]
        x["cls"] = [ps.pair_class(c, q, z) for c, q, z in zip(x["child_bench"], x["parent_bench"], x["dz_ft"], strict=True)]
        return x

    Lw = retag(L, tag)
    kcw = pdz.configuration(list(kids["api10"]), Lw).merge(pd.DataFrame({"api10": kids["api10"], "bench": [tag[a] for a in kids["api10"]]}), on="api10")
    precw = pp.precedent(kcw, pp.siblings(Lw))
    dw = outcomes(retag(Lp, {}), precw)
    s["outcome_wh_tag"] = s["location_id"].map(dw["outcome"])

    # DEAN: body (20b generated v1) vs loop addition
    gj = json.loads(Path(st.DEAN_BODY_GEOJSON).read_text(encoding="utf-8"))
    feat = next(x for x in gj["features"] if x["properties"].get("layer", "extent") == "extent")
    body = eg.to_ft([shape(feat["geometry"])])[0]
    dean = U[(U["group"] == "MID_DEAN") & U["inside"]].copy()
    dg = eg.to_ft([shapely.from_wkt(w) for w in dean["wkt"]])
    dean["body_share"] = [float(g.intersection(body).length / g.length) if g.length > 0 else np.nan for g in dg]
    dean["part"] = [ev.body_or_addition(v) for v in dean["body_share"]]
    s = s.merge(dean[["stick_id", "part"]], on="stick_id", how="left")
    meta = {"n_universe": len(u), "n_children": len(kids), "n_child_links": len(L), "n_stick_links": len(Lp), "n_sticks": len(s),
            "box_bench_relabels": len(moved), "n_precedent_pairs": len(prec), "seconds": round(time.time() - t0),
            "haircut_table": str(ppr.HAIRCUT_TABLE), "haircut_table_sha256": st.sha256_file(ppr.HAIRCUT_TABLE),
            "reference_date": str(ACTUALS)}
    prec_df = pd.DataFrame([{"pair_key": k, "multi": v["multi"], "package": v["package"]} for k, v in prec.items()]).sort_values("multi", ascending=False)
    return {"sticks": s, "fill": fill, "precedent": prec_df, "meta": meta, "dean_geom": (body, dg, dean)}


def prox_tables(s: pd.DataFrame) -> dict[str, pd.DataFrame]:
    out = {}
    t = pd.crosstab(s["group"], s["outcome"]).reindex(columns=list(pp.OUTCOMES), fill_value=0)
    t["sticks"] = t.sum(axis=1)
    t["no_forecast_pct"] = (100 * (t["no_forecast_precedent"] + t["no_forecast_package"]) / t["sticks"]).round(1)
    t["multi_parent_pct"] = (100 * (t["haircut"] + t["no_forecast_precedent"] + t["no_forecast_package"]) / t["sticks"]).round(1)
    t.loc["ALL"] = t.sum(numeric_only=True)
    a = t.loc["ALL"]
    t.loc["ALL", "no_forecast_pct"] = round(100 * (a["no_forecast_precedent"] + a["no_forecast_package"]) / a["sticks"], 1)
    t.loc["ALL", "multi_parent_pct"] = round(100 * (a["haircut"] + a["no_forecast_precedent"] + a["no_forecast_package"]) / a["sticks"], 1)
    out["by_group"] = t.reset_index()
    cc = pd.crosstab(s["group"], s["config_class"].fillna("unexposed"))
    out["config"] = cc.reset_index()
    out["pairs"] = (s[s["pair_key"].notna()].groupby(["group", "pair_key", "outcome"])
                    .agg(sticks=("stick_id", "size"), prec_multi=("prec_multi", "first"), prec_package=("prec_package", "first"),
                         factor=("factor", "first")).reset_index().sort_values("sticks", ascending=False))
    dn = s[s["group"] == "MID_DEAN"]
    dt_ = pd.crosstab(dn["part"], dn["outcome"]).reindex(columns=list(pp.OUTCOMES), fill_value=0)
    dt_["sticks"] = dt_.sum(axis=1)
    dt_["forecast"] = dt_["as_is_unexposed"] + dt_["as_is_single_parent"] + dt_["haircut"]
    dt_["forecast_pct"] = (100 * dt_["forecast"] / dt_["sticks"]).round(1)
    out["dean"] = dt_.reset_index()
    dpar = dn[dn["config_class"].notna()].assign(parents=dn["pb_topfill"].fillna("") + "/" + dn["pb_underfill"].fillna("") + "/" + dn["pb_same"].fillna(""))
    out["dean_parents"] = (pd.crosstab([dpar["part"], dpar["config_class"]], dpar["outcome"]).reset_index())
    sw = pd.crosstab(s["outcome"], s["outcome_wh_tag"].fillna("(none)"))
    out["sensitivity_tag"] = sw.reset_index()
    return out


def dean_png(geom: tuple[Any, Any, pd.DataFrame], s: pd.DataFrame, path: Path) -> None:
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    body, dg, dean = geom
    o = dict(zip(s["stick_id"], s["outcome"], strict=False))
    colors = {"as_is_unexposed": "#2a9d8f", "as_is_single_parent": "#8ab17d", "haircut": "#e9c46a", "no_forecast_precedent": "#e76f51",
              "no_forecast_package": "#9b2226"}
    fig, ax = plt.subplots(figsize=(9, 9), dpi=110)
    for part in getattr(body, "geoms", [body]):
        x, y = part.exterior.xy
        ax.fill(np.array(x) / 5280, np.array(y) / 5280, color="#dddddd", zorder=0, label=None)
    for g, sid in zip(dg, dean["stick_id"], strict=True):
        x, y = g.xy
        ax.plot(np.array(x) / 5280, np.array(y) / 5280, color=colors.get(o.get(sid), "#555555"), lw=1.2)
    for k, c in colors.items():
        ax.plot([], [], color=c, lw=3, label=f"{k} ({sum(1 for v in o.values() if v == k and v is not None)})")
    ax.set_aspect("equal")
    ax.set_title("Midland DEAN undrilled sticks in the stored extent (49): grey = generated body, outside grey = owner-loop addition")
    ax.set_xlabel("UTM 13N, mi")
    ax.legend(loc="center left", bbox_to_anchor=(1.0, 0.5), fontsize=8, frameon=False)
    fig.tight_layout()
    fig.savefig(path, bbox_inches="tight")
    plt.close(fig)


# ----------------------------------------------------------------------------
# run + render
# ----------------------------------------------------------------------------


def evidence() -> int:
    from etl.db import get_connection

    OUT.mkdir(parents=True, exist_ok=True)
    t0 = time.time()
    pools = load_pools()
    with get_connection() as conn:
        live_last = rep.last_full_month(rep._read(conn, rep._MONTHS_SQL))
        if live_last < ACTUALS:
            raise RuntimeError(f"live last full month {live_last} is before the pinned actuals {ACTUALS}")
        ext = {g: tar.pull_extent(conn, b, BASIN) for g, (b, _, _) in st.GROUPS.items()}
        for g, (_, e, _) in st.GROUPS.items():
            if ext[g]["extent_id"] != e:
                raise RuntimeError(f"{g}: record extent is {ext[g]['extent_id']}, the pre-registration names {e}")
        api = sorted({a for w in pools.values() for a in w["api10"]})
        labels = pd.DataFrame(_read(conn, _LABEL_SQL, {"a": api}), columns=["api10", "water_source", "sharing"])
        conn.rollback()
        U = sticks_in_extents(conn)
        RUNS.mkdir(parents=True, exist_ok=True)
        ck = RUNS / "counts.pkl"  # cache of the slowest pure-read stage (git-ignored); delete it to recount
        if ck.exists():
            c = pd.read_pickle(ck)
        else:
            c = counts_for(conn, pools, ext, labels)
            pd.to_pickle(c, ck)
        r = reach_tables(U, pools, labels)
        pf = per_ft_tables(pools)
        px = proximity(conn, pools, U, ext)
    T = prox_tables(px["sticks"])
    c["counts"].to_csv(OUT / "package_counts.csv", index=False)
    c["judge"].to_csv(OUT / "judgeability.csv", index=False)
    c["water_packages"].to_csv(OUT / "water_package_counts.csv", index=False)
    c["water_pooled"].to_csv(OUT / "water_packages_pooled.csv", index=False)
    r["oil"].to_csv(OUT / "reach_oil.csv", index=False)
    r["water"].to_csv(OUT / "reach_water.csv", index=False)
    r["length"].to_csv(OUT / "sticks_by_length.csv", index=False)
    pf.to_csv(OUT / "per_ft_by_length.csv", index=False)
    px["fill"].to_csv(OUT / "prox_ladder_fill.csv", index=False)
    px["precedent"].to_csv(OUT / "prox_precedent.csv", index=False)
    for k, t in T.items():
        t.to_csv(OUT / f"prox_{k}.csv", index=False)
    keep = ["stick_id", "group", "bench", "category", "recon_status", "pad_name", "config_class", "n_parents_total", "n_same", "n_topfill",
            "n_underfill", "pb_same", "pb_topfill", "pb_underfill", "outcome", "factor", "pair_key", "prec_multi", "prec_package",
            "recent_producers", "permit_parents", "outcome_wh_tag", "part"]
    st_ = px["sticks"][keep].merge(r["sticks"].drop(columns=["group", "bench", "category", "recon_status", "pad_name"]), on="stick_id", how="left")
    st_.to_csv(OUT / "sticks.csv.gz", index=False, compression="gzip")
    dean_png(px["dean_geom"], px["sticks"], OUT / "dean_outcomes.png")
    inside = U.groupby(["group", "inside", "category"]).size().unstack(["inside", "category"], fill_value=0)
    inside.columns = [f"{'inside' if a else 'outside'}_{b}" for a, b in inside.columns]
    inside = inside.reset_index()
    inside.to_csv(OUT / "sticks_inside_outside.csv", index=False)
    meta = {"built_at": dt.datetime.now(tz=dt.UTC).astimezone().isoformat(timespec="seconds"), "code_sha": _sha(), "definition_digest": st.digest(),
            "actuals_through": str(ACTUALS), "live_last_full_month": str(live_last), "holdout_salt": ho.SALT, "holdout_share": ho.SHARE,
            "min_packages": tb.MIN_PACKAGES, "seconds": round(time.time() - t0),
            "extents": {g: {"extent_id": x["extent_id"], "version": x["version"], "area_sqmi": round(x["area_sqmi"], 2)} for g, x in ext.items()},
            "pools": {g: len(w) for g, w in pools.items()}, "route": c["route"], "prox": px["meta"],
            "labels": labels["water_source"].fillna("(none)").value_counts().to_dict()}
    (OUT / "summary.json").write_text(json.dumps(meta, indent=1, default=str), encoding="utf-8")
    render()
    print(json.dumps({k: v for k, v in meta.items() if k != "route"}, indent=1, default=str))
    return 0


def _fmt_d(d: Any) -> str:
    if isinstance(d, str):
        try:
            d = json.loads(d.replace("'", '"'))
        except ValueError:
            return d
    if isinstance(d, dict) and {"p10", "p50", "p90"} <= set(d):
        return f"{d['p10']:.1f} / {d['p50']:.1f} / {d['p90']:.1f}"
    return str(d)


def render() -> str:
    meta = json.loads((OUT / "summary.json").read_text(encoding="utf-8"))
    j = pd.read_csv(OUT / "judgeability.csv")
    counts = pd.read_csv(OUT / "package_counts.csv")
    wpool = pd.read_csv(OUT / "water_packages_pooled.csv")
    oil, water, length = pd.read_csv(OUT / "reach_oil.csv"), pd.read_csv(OUT / "reach_water.csv"), pd.read_csv(OUT / "sticks_by_length.csv")
    pf = pd.read_csv(OUT / "per_ft_by_length.csv")
    byg, dean = pd.read_csv(OUT / "prox_by_group.csv"), pd.read_csv(OUT / "prox_dean.csv")
    fill, sens = pd.read_csv(OUT / "prox_ladder_fill.csv"), pd.read_csv(OUT / "prox_sensitivity_tag.csv")
    pairs = pd.read_csv(OUT / "prox_pairs.csv")
    inside = pd.read_csv(OUT / "sticks_inside_outside.csv")
    route = pd.DataFrame([{"group": g, **{k: (", ".join(map(str, v)) if isinstance(v, list) else v) for k, v in r.items()
                                          if k in ("record_treatment", "d99_horizons", "tier_route", "verdict_class_step14")},
                           **{f"holdout_raw_{k}": v for k, v in r["pooled_holdout_raw"].items()},
                           **{f"holdout_wf_{k}": v for k, v in r["pooled_holdout_wf"].items()}} for g, r in meta["route"].items()])
    for col in ("d10_mi",):
        oil[col] = [_fmt_d(x) for x in oil[col]]
        water[col] = [_fmt_d(x) for x in water[col]]
    oil["d10_gain_mi_vs_15k_cap"] = [_fmt_d(x) for x in oil["d10_gain_mi_vs_15k_cap"]]
    cpiv = counts.pivot_table(index=["group", "cutoff"], columns="horizon", values=["n_tuning", "n_holdout"], aggfunc="sum")
    cpiv.columns = [f"{a}_{b}" for a, b in cpiv.columns]
    cpiv = cpiv.reset_index()
    fill_s = (fill.groupby(["group", "rung"]).agg(keys=("key", "size"), keys_fill=("fills", "sum"), children=("n_children", "sum")).reset_index()
              if len(fill) else fill)
    fill_t = fill.drop_duplicates("group")[["group", "n_tuning_children", "n_multi"]] if len(fill) else fill
    pf_show = pf[pf["set"].isin(["Midland all (9)", "Midland Wolfcamp (5)", "Midland Spraberry (4)"])]
    px = meta["prox"]
    p = [("<!doctype html><html lang=en><head><meta charset=utf-8><meta name=viewport content='width=device-width,initial-scale=1'>"
          f"<title>BOX step 21a evidence</title><style>{_CSS} body{{overflow-x:hidden;max-width:1200px;margin:auto;padding:0 16px}} "
          "table{display:block;overflow-x:auto;max-width:100%} img{max-width:100%}</style></head><body>"),
         "<h1>BOX step 21a — Midland pre-registration evidence (read-only; nothing forecast, scored or stored)</h1>",
         (f"<div class=meta>built {meta['built_at']} · code {meta['code_sha'][:12]} · definition digest {meta['definition_digest'][:12]} · "
          f"actuals through {meta['actuals_through']} (live {meta['live_last_full_month']}) · D52 holdout salt {meta['holdout_salt']} share "
          f"{meta['holdout_share']:.0%} · ≥ {meta['min_packages']} packages per judged cell · {meta['seconds']:,} s</div>"),
         ("<p>Grain is stated per table: <b>packages</b> (D53: co-developed co-extent pool wells, first production within 180 d, "
          "overlap ≥ 30 %), <b>wells</b>, or <b>sticks</b> (Novi undrilled sticks, D117 universe: PUD + RES, remaining_pud / conflict / "
          "not reconciled, ≥ 50 % inside the record extent). Holdout packages are COUNTED only — no forecast or error exists for any "
          "package. Reach is circle-only (a lower bound: the strike ellipse is ignored).</p>"),
         "<h2>1. What the counts allow (record treatment, D99 cells, tier route — the pre-registered rules applied to 21a counts)</h2>",
         ("<p>Final values are fixed from the 21b tuning run's SCORED counts (the harness drops wells with no prediction at early "
          "cutoffs — step-15 §2), before any holdout is read. Pooled holdout = packages over every scoreable cutoff (raw) or over the "
          "cutoffs that carry a walk-forward haircut (wf).</p>"),
         _table(route), "<h3>Judgeability per group × horizon</h3>", _table(j[["group", "horizon", "d53_cells", "wf_cutoffs", "pooled_tuning",
                                                                                  "pooled_holdout_raw", "pooled_holdout_wf", "d102_cutoffs"]]),
         "<h3>Packages per cutoff (tuning / holdout)</h3>", _table(cpiv, max_rows=80),
         "<h2>2. Undrilled sticks inside / outside each record extent</h2>", _table(inside),
         "<h2>3. Oil analog reach (10th nearest analog-eligible producer, mi P10 / P50 / P90; ring = D54 ladder)</h2>",
         ("<p>Eligible = first production ≥ 2016, ≥ 6 months by the actuals date, lateral ≥ 5,000 ft, NO upper bound (D129). "
          "'ring moves vs 15k cap' = sticks whose ring changes when > 15,000-ft producers are excluded again (the r2 band).</p>"), _table(oil),
         "<h2>4. Long laterals</h2>", _table(length),
         ("<h3>Observed 12-month oil per 1,000 ft by lateral class vs the 7,500–10,000 ft class (TUNING blocks only; within 3-mi block × "
          "first-production-year cells; 90 % block-bootstrap interval) next to Cui &amp; Cross</h3><p>Lateral = reported lateral length. "
          "A ratio above Cui = per-ft degradation flatter than the Delaware curve (D129: the translation then reads LOW on long PUDs).</p>"),
         _table(pf_show, {"observed": ".3f", "lo90": ".3f", "hi90": ".3f", "cui": ".3f"}),
         "<h2>5. Proximity on Midland producers (D112–D116 pattern)</h2>",
         (f"<div class=meta>producer universe {px['n_universe']:,} (horizontals in the Midland bbox + 0.05°) · drilled children {px['n_children']:,} · "
          f"child links {px['n_child_links']:,} · stick links {px['n_stick_links']:,} · BOX-membership relabels {px['box_bench_relabels']:,} · "
          f"bench pairs with precedent {px['n_precedent_pairs']:,} · reference date {px['reference_date']}</div>"),
         ("<p>Outcomes use MIDLAND precedent (D114: ≥ 30 drilled multi-parent wells of the bench pair; ≥ 30 packages where the factor ≤ 0.80) "
          "and the DELAWARE D113 factor table as an interim stand-in (it decides only whether the package tier applies). Sticks, not "
          "forecasts: no BOX volume exists yet.</p>"), _table(byg),
         "<h3>DEAN: generated body vs the owner loop's addition (D143)</h3>", _table(dean), "<img src=dean_outcomes.png alt='DEAN outcome map'>",
         "<h3>Bench pairs of the multi-parent sticks (top 60)</h3>", _table(pairs, {"factor": ".3f"}, max_rows=60),
         "<h3>Ladder rungs a Midland factor table could fill (tuning-window children in extent, tuning blocks; ≥ 30 per key)</h3>",
         _table(fill_t), _table(fill_s),
         "<h3>Sensitivity: BOX membership (rows) vs warehouse tag (columns) as the bench label</h3>", _table(sens),
         "<h2>6. Measured water (D107 / D133)</h2>",
         ("<p>Measured = curated.water_data_quality 'measured' (Texas: the sql/41 label). Reach rings add 30 / 40 / 50 mi; thin = 3–9 "
          "measured within 50 mi; fallback = &lt; 3. Top-operator share = the largest operator among a stick's 10 nearest measured analogs.</p>"),
         _table(water), "<h3>Measured-water packages (a package with ≥ 1 measured member that reached k), pooled over cutoffs</h3>", _table(wpool),
         "</body></html>"]
    html = "\n".join(p)
    (OUT / "index.html").write_text(html, encoding="utf-8")
    return html


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("step", choices=("pool", "evidence", "render"))
    a = ap.parse_args(argv)
    if a.step == "pool":
        print(json.dumps(make_pool(), indent=1))
        return 0
    if a.step == "render":
        render()
        return 0
    return evidence()


if __name__ == "__main__":
    sys.exit(main())
