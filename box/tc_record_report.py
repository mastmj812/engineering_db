"""BOX step 5d — build the type-curve + risk-factor record from the 5b / 5c evidence; review page.

DB-free by default: the record is built from the committed deliverables Michael reviewed, not a fresh pull.

  * curves: docs/box/step5b-2026-10-10 — the 35 WCA area curves of record (curves_WCA.csv), their members
    (members_WCA.csv) and per-well fits (well_fits_WCA.csv). Every area curve is RE-FITTED from the member
    fits with the installed blueox-boxfit (must equal the 5b SHA) and checked against the stored row; the
    stored values are the 5b CSV's (the reviewed numbers), the refit supplies the peak_ramp anchors.
  * factors: docs/box/step5c-2026-10-11/wells.csv (the 5c per-well frame: sql/50 class recomputed from
    bench_context, nearest parent bench, infill, cum-12 actuals, D30 local GOR) + midpoints from the
    gate-1 final sets. The frame is checked by identity first: the 5c record view (log-OLS) re-estimated
    from it must equal factors.csv. Then the factors of RECORD are estimated under D42 (pooled-bench view)
    + D47 (Poisson PML) with a 90 % cluster bootstrap, and resolved through the D45 ladder.
  * ref_mult per area x stream (D43): the as-built cohort-mean curve -> the reference-scenario curve.

`drift_check` (opt-in, read-only, minutes: curated.dev_scenario is a plain view) compares the live sql/50
class / infill flag with the frame, so the gate knows whether the stored factors still describe today's view.
"""

from __future__ import annotations

import datetime as dt
import json
import math
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from box import dev_factor as dfm
from box import dev_factor_report as dfr
from box import exclusions
from box import tc_curve as tc
from box import tc_curve_report as rep
from box import tc_record as tr
from box.edge_gap_report import _CSS, _table

BASIN = "delaware"
STEP5B = Path("docs") / "box" / "step5b-2026-10-10"
STEP5C = Path("docs") / "box" / "step5c-2026-10-11"
POOL_BENCHES = dfr.POOL_BENCHES
BENCHES = ("WCA", "BS2_S")
# factor of record per stream: oil / water cum-12 (D43 uniform scale), gas GOR vs the D30 local level (D46)
RECORD_METRIC = {"oil": "oil_cum12", "gas": "gor12_vs_local", "water": "water_cum12"}
WEIGHT_COL = {"oil": "oil12_kft", "water": "water12_kft"}  # ref_mult weights (actual cum-12 / kft)
FE_SPEC = {"WCA": "TC area of record (box.tc_area v1, extent 6) + first-prod year", "BS2_S": "5-mi block + first-prod year",
           tr.POOLED: "bench x location + bench x first-prod year"}
REFIT_TOL = 1e-7  # relative: re-fitted curve vs the stored 5b row (seen <= 5e-10; optimizer noise)
FRAME_TOL = 1e-9  # relative: 5c record view re-estimated from wells.csv vs factors.csv


# ----------------------------------------------------------------------------
# Factor frame (5c evidence)
# ----------------------------------------------------------------------------


def _bool(s: pd.Series) -> pd.Series:
    return s.astype(str).str.lower().eq("true")


def load_frame(wells_dir: Path) -> pd.DataFrame:
    w = pd.read_csv(STEP5C / "wells.csv", float_precision="round_trip", dtype={"api10": str, "loc": str, "parent_below": str, "parent_above": str, "parent_bench": str, "view_class": str})
    ll = pd.concat([pd.read_csv(wells_dir / f"wells_final_{b}.csv", dtype={"api10": str})[["api10", "mid_lon", "mid_lat"]].assign(bench_pool=b) for b in BENCHES])
    w = w.merge(ll, on=["api10", "bench_pool"], how="left")
    if w["mid_lon"].isna().any():
        raise RuntimeError(f"{int(w['mid_lon'].isna().sum())} frame wells have no midpoint in the gate-1 final sets")
    w["infill"] = _bool(w["infill"])
    w["own_bench_in_pool"] = _bool(w["own_bench_in_pool"])
    return add_pooled_view(w)


def add_pooled_view(w: pd.DataFrame) -> pd.DataFrame:
    """D42 columns on a 5c-shaped frame (view_class, parent_below / _above, bool infill, bench_pool, gor12,
    gor_local): p_class, p_parent, p_infill, same_pool, p_raw_pair, plus fpy and gor12_vs_local."""
    w = w.copy()
    w["scenario_class"] = w["view_class"]
    w["fpy"] = w["first_production_date"].astype(str).str[:4]
    w["gor12_vs_local"] = w["gor12"] / w["gor_local"]
    pooled = [tr.pooled_scenario(c, b, a, i, POOL_BENCHES[p]) for c, b, a, i, p in
              zip(w["view_class"], w["parent_below"], w["parent_above"], w["infill"], w["bench_pool"], strict=True)]
    w["p_class"] = [p[0] for p in pooled]
    w["p_parent"] = [p[1] for p in pooled]
    w["p_infill"] = [p[2] for p in pooled]
    w["same_pool"] = [p[3] for p in pooled]
    w["p_raw_pair"] = [tr.raw_pair(c, p) for c, p in zip(w["p_class"], w["p_parent"], strict=True)]
    return w


def frame_identity(w: pd.DataFrame) -> dict[str, Any]:
    """The 5c record view (log-OLS, sql/50 pairs, point estimates) re-estimated from the frame must equal
    the committed factors.csv on every term of the three record metrics, both benches."""
    fac = pd.read_csv(STEP5C / "factors.csv")
    worst, n_terms = 0.0, 0
    for b in BENCHES:
        e = dfr.est_frame(w[w.bench_pool == b])
        pair = dfm.pair_labels(e["scenario_class"], e["parent_bench"])
        for m in RECORD_METRIC.values():
            r = dfr.run_metric(e, m, pair, e["infill"], [e["loc"], e["fpy"]], 0).set_index("term")["factor"]
            ref = fac[(fac.bench == b) & (fac.metric == m)].set_index("term")["factor"]
            if set(r.index) != set(ref.index):
                raise RuntimeError(f"5c frame identity: {b} {m} terms differ: {sorted(set(r.index) ^ set(ref.index))}")
            worst = max(worst, float((r / ref.reindex(r.index) - 1).abs().max()))
            n_terms += len(r)
    if worst > FRAME_TOL:
        raise RuntimeError(f"5c frame identity failed: worst relative gap {worst:.2e} > {FRAME_TOL}")
    n_est = {b: len(dfr.est_frame(w[w.bench_pool == b])) for b in BENCHES}
    return {"n_terms": n_terms, "worst_rel": worst, "n_est": n_est}


# ----------------------------------------------------------------------------
# Factors of record (D42 + D45 + D47)
# ----------------------------------------------------------------------------


def _est_frame(w: pd.DataFrame, b: str) -> pd.DataFrame:
    e = dfr.est_frame(w[w.bench_pool == b])
    e["p_pair"] = dfm.pair_labels(e["p_class"], e["p_parent"])
    return e


def _fit(e: pd.DataFrame, metric: str, terms: pd.DataFrame, fes: list[pd.Series], n_boot: int, estimator: str = "ppml") -> pd.DataFrame:
    return dfr.run_metric(e, metric, None, None, fes, n_boot, estimator=estimator, terms=terms)  # type: ignore[arg-type]


def _ests(r: pd.DataFrame) -> dict[str, tr.Est]:
    return {t: tr.Est(float(f), _f(lo), _f(hi), int(n), int(nc) if pd.notna(nc) else None)
            for t, f, lo, hi, n, nc in zip(r["term"], r["factor"], r.get("ci_lo", r["factor"] * np.nan), r.get("ci_hi", r["factor"] * np.nan),
                                           r["n_wells"], r.get("n_clusters", r["n_wells"] * np.nan), strict=True)}


def _f(v: Any) -> float | None:
    return float(v) if v is not None and np.isfinite(v) else None


def estimate_record(w: pd.DataFrame, n_boot: int) -> dict[str, Any]:
    """Pair, class-in-bench and basin-class PPML models per record metric, bootstrapped; plus point-only
    diagnostics (log-OLS on the same pooled view; oil EUR PPML)."""
    es = {b: _est_frame(w, b) for b in BENCHES}
    st = pd.concat([e.assign(_b=b) for b, e in es.items()], ignore_index=True)
    out: dict[str, Any] = {"pair": {}, "class": {}, "basin": {}, "diag": {}, "n_est": {b: len(e) for b, e in es.items()},
                           "n_ref": {b: int(((e["p_class"] == dfm.REFERENCE) & ~e["p_infill"]).sum()) for b, e in es.items()}}
    out["n_ref"][tr.POOLED] = sum(out["n_ref"].values())
    for s, m in RECORD_METRIC.items():
        for b, e in es.items():
            fes = [e["loc"], e["fpy"]]
            out["pair"][(b, s)] = _fit(e, m, dfm.term_frame(e["p_pair"], e["p_infill"]), fes, n_boot)
            out["class"][(b, s)] = _fit(e, m, dfm.term_frame(e["p_class"], e["p_infill"]), fes, n_boot)
            out["diag"][(b, s, "ols")] = _fit(e, m, dfm.term_frame(e["p_pair"], e["p_infill"]), fes, 0, estimator="ols")
        out["basin"][s] = _fit(st, m, dfm.term_frame(st["p_class"], st["p_infill"]), [st["_b"] + ":" + st["loc"], st["_b"] + ":" + st["fpy"]], n_boot)
    for b, e in es.items():
        out["diag"][(b, "oil", "eur_ppml")] = _fit(e, "oil_eur", dfm.term_frame(e["p_pair"], e["p_infill"]), [e["loc"], e["fpy"]], 0)
    return out


def risk_rows(est: dict[str, Any], n_boot: int, built: str, version: int = 1) -> pd.DataFrame:
    """box.risk_factor rows: reference + pair + class per bench, basin class across benches, per stream."""
    rows: list[dict[str, Any]] = []
    for s, m in RECORD_METRIC.items():
        basin = _ests(est["basin"][s])
        common = {"version": version, "basin": BASIN, "stream": s, "metric": m, "applies_to": "both", "estimator": "ppml", "generated_from_run": built}
        prm = {"ci": dfr.CI, "n_boot": n_boot, "cluster_block_ft": dfm.BLOCK_FT, "reference": f"{dfm.REFERENCE}, no same-bench parent",
               "same_pool_parents": "lateral infill (D42)", "min_pair_wells": dfm.MIN_PAIR_WELLS, "ladder_min_n": tr.LADDER_MIN_N,
               "source": f"{STEP5C.as_posix()}/wells.csv", "application": "uniform scale (D43)" if s != "gas" else "alpha shift on top of the oil factor (D46)"}
        for b in (*BENCHES, tr.POOLED):
            rows.append({**common, "bench": b, "level": "reference", "term": dfm.REFERENCE, "dev_scenario": dfm.REFERENCE, "parent_bench": None,
                         "estimate": 1.0, "ci_lo": None, "ci_hi": None, "n_pairs": est["n_ref"][b], "n_clusters": None, "factor": 1.0, "rung": 0,
                         "rung_label": tr.RUNG_LABEL[0], "n_basis": est["n_ref"][b], "pud_applicable": True,
                         "params": {**prm, "fe": FE_SPEC[b], "model": "reference"}})
        for b in BENCHES:
            cls = _ests(est["class"][(b, s)])
            for t, e in _ests(est["pair"][(b, s)]).items():
                f, rung, nb = tr.resolve(t, e, cls, basin)
                rows.append(_row(common, b, "pair", t, e, f, rung, nb, {**prm, "fe": FE_SPEC[b], "model": "pair x infill"}))
            for t, e in cls.items():
                f, rung, nb = tr.resolve_class(t, e, basin)
                rows.append(_row(common, b, "class", t, e, f, rung, nb, {**prm, "fe": FE_SPEC[b], "model": "class x infill"}))
        for t, e in basin.items():
            rows.append(_row(common, tr.POOLED, "basin_class", t, e, e.estimate, 3, e.n, {**prm, "fe": FE_SPEC[tr.POOLED], "model": "class x infill, WCA + BS2_S stacked"}))
    return pd.DataFrame(rows)


def _row(common: dict[str, Any], bench: str, level: str, term: str, e: tr.Est, factor: float, rung: int, n_basis: int, params: dict[str, Any]) -> dict[str, Any]:
    cls = tr.term_class(term)
    return {**common, "bench": bench, "level": level, "term": term, "dev_scenario": cls, "parent_bench": term.split("|")[1] if "|" in term else None,
            "estimate": e.estimate, "ci_lo": e.ci_lo, "ci_hi": e.ci_hi, "n_pairs": e.n, "n_clusters": e.n_clusters, "factor": float(factor), "rung": rung,
            "rung_label": tr.RUNG_LABEL[rung], "n_basis": int(n_basis), "pud_applicable": cls not in tr.SCORING_ONLY, "params": params}


def factor_table(rf: pd.DataFrame, bench: str, stream: str) -> dict[tuple[str, str], float]:
    """(level, term) -> factor of record for one bench + the basin-class fallbacks (tc_record.lookup input)."""
    r = rf[(rf.stream == stream) & ((rf.bench == bench) | (rf.level == "basin_class"))]
    return {(lv, t): float(f) for lv, t, f in zip(r["level"], r["term"], r["factor"], strict=True) if lv != "reference"}


# ----------------------------------------------------------------------------
# Curves (5b record) + ref_mult
# ----------------------------------------------------------------------------


def _params(wf: pd.DataFrame, a: str, s: str) -> dict[str, Any] | None:
    r = wf.loc[a]
    if pd.isna(r[f"{s}_qi"]):
        return None
    p = {k: r[f"{s}_{k}"] for k in ("qo", "qi", "Di", "b", "Df", "peak_index_months", "onset_index_months")}
    return {k: (None if isinstance(v, float) and math.isnan(v) else float(v)) for k, v in p.items()}


def curves_record(w: pd.DataFrame, rf: pd.DataFrame) -> dict[str, Any]:
    """Per area x stream: the stored 5b record row, the refit check, anchors, members with their factor of
    record and weight, and ref_mult."""
    cur = pd.read_csv(STEP5B / "curves_WCA.csv", float_precision="round_trip")
    cur = cur[cur.area_no.astype(str) != "pool"].copy()
    cur["area_no"] = cur["area_no"].astype(int)
    mem = pd.read_csv(STEP5B / "members_WCA.csv", float_precision="round_trip", dtype={"api10": str})
    wf = pd.read_csv(STEP5B / "well_fits_WCA.csv", float_precision="round_trip", dtype={"api10": str}).set_index("api10")
    ex = set(exclusions.load()["api10"])
    if mem["api10"].isin(ex).any():
        raise RuntimeError(f"{int(mem['api10'].isin(ex).sum())} 5b members are now in exclusions.csv — re-run 5b before storing")
    fr = w[w.bench_pool == "WCA"].set_index("api10")
    if set(mem["api10"]) - set(fr.index):
        raise RuntimeError("5b members missing from the 5c frame")
    tabs = {s: factor_table(rf, "WCA", s) for s in WEIGHT_COL}
    rows, members, worst = [], [], 0.0
    for a, g in mem.groupby("area_no"):
        c = tc.fit_curve([tc.Member(api10=x.api10, lateral_ft=float(x.lateral_ft), params={s: _params(wf, x.api10, s) for s in tc.STREAMS}) for x in g.itertuples()])
        ca = cur[cur.area_no == a]
        for s in tc.STREAMS:
            rec = ca[(ca.stream == s) & (ca.record.astype(str).str.lower() == "true")]
            if len(rec) != 1:
                raise RuntimeError(f"area {a} {s}: expected one record row in curves_WCA.csv, found {len(rec)}")
            rec = rec.iloc[0]
            if int(rec.rung) != 1:
                raise RuntimeError(f"area {a} {s}: rung {rec.rung} — only rung-1 pools are rebuilt here")
            new = tc.gas_ratio_row(c) if s == "gas" else tc.curve_row(c, s, tc.RECORD_STAT)
            keys = ("alpha", "beta", "eur_per_kft") if s == "gas" else ("qo", "qi", "Di_nominal", "b", "eur_per_kft")
            gap = max(abs(float(new[k]) / float(rec[k]) - 1.0) if float(rec[k]) else abs(float(new[k])) for k in keys)
            worst = max(worst, gap)
            if gap > REFIT_TOL or int(new["n_wells"]) != int(rec.n_wells):
                raise RuntimeError(f"area {a} {s}: refit differs from the 5b record (rel {gap:.2e}, n {new['n_wells']} vs {rec.n_wells})")
            fit_ok = g[f"fit_{s}"].astype(str).str.lower().eq("true") & (g["lateral_ft"] > 0)
            mrows = []
            for x, ok in zip(g.itertuples(), fit_ok, strict=True):
                f_ = fr.loc[x.api10]
                pair = f_["p_raw_pair"] if isinstance(f_["p_raw_pair"], str) else None
                fac = tr.lookup(tabs[s], "WCA", pair, bool(f_["p_infill"])) if s in tabs else None
                wt = float(f_[WEIGHT_COL[s]]) if s in WEIGHT_COL and pd.notna(f_[WEIGHT_COL[s]]) else None
                mrows.append({"area_no": int(a), "stream": s, "api10": x.api10, "included": bool(ok), "drop_reason": None if ok else f"no {s} fit",
                              "lateral_ft": float(x.lateral_ft), "dev_scenario": f_["p_class"] if isinstance(f_["p_class"], str) else None,
                              "parent_bench": f_["p_parent"] if isinstance(f_["p_parent"], str) else None, "infill": bool(f_["p_infill"]),
                              "factor": fac, "weight": wt})
            inc = [r_ for r_ in mrows if r_["included"]]
            if len(inc) != int(rec.n_wells):
                raise RuntimeError(f"area {a} {s}: {len(inc)} included members vs n_wells {rec.n_wells}")
            ref_mult = None
            if s in WEIGHT_COL:
                ref_mult = tr.weighted_ref_mult([r_["weight"] if r_["weight"] is not None else np.nan for r_ in inc], [r_["factor"] for r_ in inc])
            members += mrows
            rows.append(_tc_row(int(a), s, rec, ca, c, ref_mult))
    return {"type_curves": pd.DataFrame(rows), "members": pd.DataFrame(members), "refit_worst_rel": worst}


def _tc_row(a: int, s: str, rec: pd.Series, ca: pd.DataFrame, c: dict[str, Any], ref_mult: float | None) -> dict[str, Any]:
    num = lambda v: None if v is None or (isinstance(v, float) and not math.isfinite(v)) else float(v)
    if s == "gas":
        params = {"mode": "ratio", "alpha": num(rec.alpha), "beta": num(rec.beta), "sub_mode": rec.sub_mode, "ratio_unit": "mcf/bbl", "np_unit": "bbl per 1,000 ft"}
        diag = ca[(ca.stream == "gas") & (ca["mode"] == "arps (diagnostic)") & (ca.stat == "mean")]
        meta = {"r2": num(rec.r2), "gor12_scf_bbl": num(rec.gor12_scf_bbl), "gor24_scf_bbl": num(rec.gor24_scf_bbl), "Di_eff_1yr_implied": num(rec.Di_eff_1yr),
                "eur_per_kft_trapezoid": num(rec.eur_per_kft_trapezoid), "arps_diagnostic_eur_per_kft": num(diag.iloc[0].eur_per_kft) if len(diag) else None}
    else:
        params = {"qo": num(rec.qo), "qi": num(rec.qi), "peak_index_months": int(rec.peak_index), "Di_nominal": num(rec.Di_nominal), "Di_eff_1yr": num(rec.Di_eff_1yr),
                  "b": num(rec.b), "Df": num(rec.Df)}
        p50 = ca[(ca.stream == s) & (ca.stat == "p50") & (ca["mode"] == "arps")]
        meta = {"r2": num(rec.r2), "reconcile": num(rec.reconcile), "trapezoid_gap": num(rec.trapezoid_gap),
                "p50": {k: num(p50.iloc[0][k]) for k in ("qi", "Di_nominal", "b", "eur_per_kft")} if len(p50) else None}
    meta.update({"cum6_kft": num(rec.cum6_kft), "cum24_kft": num(rec.cum24_kft), "actual_mean_cum12_kft": num(rec.actual_mean_cum12_kft),
                 "curve_vs_actual_cum12": num(rec.curve_vs_actual_cum12), "actual_n12": int(rec.actual_n12)})
    return {"area_no": a, "stream": s, "mode": "ratio" if s == "gas" else "arps", "relaxation_step": int(rec.rung), "relaxation_label": rec.rung_label,
            "thin": str(rec.thin).lower() == "true", "n_wells": int(rec.n_wells), "anchors": {"stream": int(c["anchors"][s]), "all": {k: int(v) for k, v in c["anchors"].items()}},
            "params": params, "eur_per_kft": float(rec.eur_per_kft), "cum12_kft": float(rec.cum12_kft), "ref_mult": ref_mult, "fit_meta": meta}


# ----------------------------------------------------------------------------
# Drift check (opt-in, read-only)
# ----------------------------------------------------------------------------


def drift_check(conn: Any, w: pd.DataFrame) -> dict[str, Any]:
    rows = rep._read(conn, "SELECT api10, scenario_class, has_same_bench_parent FROM curated.dev_scenario WHERE api10 = ANY(%(a)s)", {"a": sorted(w["api10"])})
    live = pd.DataFrame(rows, columns=["api10", "live_class", "live_infill"])
    d = w.merge(live, on="api10", how="left")
    sc = d["view_class"].notna()
    cls = sc & (d["live_class"].astype(object) != d["view_class"].astype(object))
    inf = sc & (d["live_infill"].astype(object) != d["infill"].astype(object))
    return {"checked_at": dt.datetime.now(tz=dt.UTC).astimezone().isoformat(timespec="seconds"), "n": int(sc.sum()), "n_missing_live": int(d["live_class"].isna().sum()),
            "n_class_changed": int(cls.sum()), "n_infill_changed": int(inf.sum()), "examples": list(d.loc[cls | inf, "api10"][:10])}


# ----------------------------------------------------------------------------
# Page
# ----------------------------------------------------------------------------


def _ci(f: Any, lo: Any, hi: Any) -> str:
    if f is None or not np.isfinite(f):
        return "–"
    ok = lo is not None and hi is not None and np.isfinite(lo) and np.isfinite(hi)
    return f"{f:.3f} [{lo:.2f}–{hi:.2f}]" if ok else f"{f:.3f}"


def factor_view(rf: pd.DataFrame, bench: str, level: str) -> pd.DataFrame:
    """One row per term, the three streams side by side: own estimate [CI] and the factor of record (rung)."""
    r = rf[(rf.bench == bench) & (rf.level == level)]
    terms = list(dict.fromkeys(r.loc[r.stream == "oil", "term"]))
    out = pd.DataFrame({"term": terms})
    o = r[r.stream == "oil"].set_index("term").reindex(terms)
    out["n wells"] = o["n_pairs"].to_numpy()
    out["n blocks"] = o["n_clusters"].to_numpy()
    for s, lab in (("oil", "oil cum-12"), ("gas", "GOR vs local"), ("water", "water cum-12")):
        x = r[r.stream == s].set_index("term").reindex(terms)
        out[f"{lab}: estimate"] = [_ci(f, lo, hi) for f, lo, hi in zip(x["estimate"], x["ci_lo"], x["ci_hi"], strict=True)]
        out[f"{lab}: RECORD"] = [f"{f:.3f} (rung {int(g)})" for f, g in zip(x["factor"], x["rung"], strict=True)]
    out["PUD use"] = ["yes" if p else "scoring only (D44)" for p in o["pud_applicable"]]
    return out


def compare_5c(rf: pd.DataFrame, est: dict[str, Any]) -> pd.DataFrame:
    """Record (PPML, pooled view) vs the 5c evidence (log-OLS record view; log-OLS pooled view) for oil cum-12."""
    fac = pd.read_csv(STEP5C / "factors.csv")
    pv = pd.read_csv(STEP5C / "factors_pooled_view.csv")
    rows = []
    for b in BENCHES:
        r = rf[(rf.bench == b) & (rf.level == "pair") & (rf.stream == "oil")]
        ols = est["diag"][(b, "oil", "ols")].set_index("term")["factor"]
        eurp = est["diag"][(b, "oil", "eur_ppml")].set_index("term")["factor"]
        f5 = fac[(fac.bench == b) & (fac.metric == "oil_cum12")].set_index("term")["factor"]
        p5 = pv[(pv.bench == b) & (pv.metric == "oil_cum12")].set_index("term")["factor"]
        for t, e, f, rung, n in zip(r["term"], r["estimate"], r["factor"], r["rung"], r["n_pairs"], strict=True):
            rows.append({"bench": b, "term": t, "n": int(n), "5c record view (log-OLS)": f5.get(t, np.nan), "5c pooled view (log-OLS)": p5.get(t, np.nan),
                         "5d pooled view, log-OLS": ols.get(t, np.nan), "5d PPML estimate": e, "5d factor of record": f, "rung": int(rung),
                         "oil EUR, PPML (diagnostic)": eurp.get(t, np.nan)})
    return pd.DataFrame(rows)


def curve_view(tcs: pd.DataFrame) -> pd.DataFrame:
    rows = []
    for a, g in tcs.groupby("area_no"):
        o, gs, wt = (g[g.stream == s].iloc[0] for s in ("oil", "gas", "water"))
        po, pw = o.params, wt.params
        rows.append({"area": int(a), "n oil": int(o.n_wells), "n gas": int(gs.n_wells), "n water": int(wt.n_wells), "rung": int(o.relaxation_step),
                     "oil qi bopd/kft": po["qi"], "oil Di nominal /yr": po["Di_nominal"], "oil Di 1-yr eff": po["Di_eff_1yr"], "oil b": po["b"],
                     "oil EUR bbl/kft (as built)": o.eur_per_kft, "oil ref_mult": o.ref_mult, "oil EUR bbl/kft (reference)": o.eur_per_kft * o.ref_mult,
                     "gas EUR mcf/kft (area level)": gs.eur_per_kft, "gas beta e-6": gs.params["beta"] * 1e6,
                     "water Di nominal /yr": pw["Di_nominal"], "water EUR bbl/kft": wt.eur_per_kft, "water ref_mult": wt.ref_mult})
    return pd.DataFrame(rows)


_CURVE_FMT = {"oil qi bopd/kft": ".1f", "oil Di nominal /yr": ".2f", "oil Di 1-yr eff": ".0%", "oil b": ".3f", "oil EUR bbl/kft (as built)": ",.0f", "oil ref_mult": ".3f",
              "oil EUR bbl/kft (reference)": ",.0f", "gas EUR mcf/kft (area level)": ",.0f", "gas beta e-6": ".2f", "water Di nominal /yr": ".2f",
              "water EUR bbl/kft": ",.0f", "water ref_mult": ".3f"}


def render_page(ctx: dict[str, Any]) -> str:
    s = ctx["summary"]
    rf, tcs = ctx["risk"], ctx["type_curves"]
    rel = s["relabel"]
    p = [
        "<!doctype html><html><head><meta charset=utf-8><meta name=viewport content='width=device-width,initial-scale=1'><title>BOX curve record</title>",
        f"<style>{_CSS} body{{overflow-x:hidden}} table{{display:block;overflow-x:auto;max-width:100%}}</style></head><body>",
        "<h1>BOX step 5d — type-curve + risk-factor record (what sql/58 will hold)</h1>",
        (f"<div class=meta>built {s['built_at']} · curves = the step-5b record ({STEP5B.as_posix()}, blueox-boxfit @ {s['engine_sha'][:7]}, production through {s['data_asof']}); "
         f"factors = the step-5c frame ({STEP5C.as_posix()}/wells.csv) under D42 + D45 + D47 · {s['n_boot']} bootstrap draws · nothing is written to the warehouse by this build</div>"),
        "<h2>1. Identity checks (the record = what was reviewed)</h2>",
        _table(pd.DataFrame(s["checks"]), {}),
        "<h2>2. Risk factors of record</h2>",
        ("<div class='flag'>Factor = exp(β), Poisson PML (D47: ratio of arithmetic means, consistent with the D32 mean curve). Location FE (WCA: TC area; BS2_S: 5-mi block) "
         "+ first-prod-year FE. Reference = <b>codev_stack with no same-bench parent</b> (1.000). Same-pool vertical parents (WCA_1 / WCA_2 / WCXY) are lateral infill (D42). "
         f"90 % cluster bootstrap over 3-mi blocks. <b>RECORD</b> = after the D45 ladder: rung 1 = own estimate (n ≥ {tr.LADDER_MIN_N}), 2 = class in bench, "
         "3 = class across benches. Oil / water = cum-12 per 1,000 ft, applied as a uniform scale (D43). Gas = 12-mo GOR / D30 local level, applied through α on top of "
         "the oil factor (D46). Factors combine: pair × infill.</div>"),
        (f"<div class=meta>D42 relabel: WCA {rel['WCA']['same_pool']:,} wells with a same-pool parent → infill on the reference class "
         f"(of which {rel['WCA']['sandwich']} sandwich wells); BS2_S {rel['BS2_S']['same_pool']}. Estimation wells: WCA {s['n_est']['WCA']:,}, BS2_S {s['n_est']['BS2_S']:,}.</div>"),
    ]
    for b in BENCHES:
        p += [f"<h3>{b} — pairs (what a well or PUD is looked up on)</h3>", _table(factor_view(rf, b, "pair"), {"n blocks": ".0f"}),
              f"<h3>{b} — class within the bench (rung-2 fallback)</h3>", _table(factor_view(rf, b, "class"), {"n blocks": ".0f"})]
    p += ["<h3>Across benches (rung 3, terminal)</h3>", _table(factor_view(rf, tr.POOLED, "basin_class"), {"n blocks": ".0f"}),
          "<h3>Record vs the 5c evidence (oil cum-12)</h3>",
          ("<div class=meta>The 5c record view keeps sql/50 same-pool pairs separate (log-OLS). The 5d pooled view folds them into infill (D42). "
           "The 5d log-OLS column isolates the estimator change (D47) from the view change (D42).</div>"),
          _table(ctx["compare"], {c: ".3f" for c in ctx["compare"].columns if c not in ("bench", "term", "n", "rung")})]
    p += ["<h2>3. Type curves of record (WCA, 35 areas × oil / gas / water)</h2>",
          ("<div class='flag'>Stored params = the step-5b cohort-MEAN curve per 1,000 ft (D32), as built from the area's mixed scenarios. "
           "Reference-scenario curve = qo and qi × ref_mult (D43 uniform scale; Di / b unchanged), so its EUR = as-built EUR × ref_mult. "
           "ref_mult = Σ(w / f) / Σ w over the included members, w = actual cum-12 per kft, f = the member's factor of record. "
           "Gas has no ref_mult: its level is set per location (D30 local GOR + D46). Di is nominal per year, 1-yr effective alongside. EUR = raw 50-yr integral.</div>"),
          _table(curve_view(tcs), _CURVE_FMT),
          "<h2>4. What --store writes (after go-apply)</h2>", _table(pd.DataFrame(s["store_plan"]), {}),
          "<h2>5. Flags</h2>", "<ul>" + "".join(f"<li>{f}</li>" for f in ctx["flags"]) + "</ul>",
          "</body></html>"]
    return "\n".join(p)


# ----------------------------------------------------------------------------
# Orchestration
# ----------------------------------------------------------------------------


def run(wells_dir: Path, out: Path, engine_sha: str, n_boot: int = dfr.N_BOOT, drift: dict[str, Any] | None = None) -> dict[str, Any]:
    out.mkdir(parents=True, exist_ok=True)
    s5b = json.loads((STEP5B / "summary.json").read_text(encoding="utf-8"))
    s5c = json.loads((STEP5C / "summary.json").read_text(encoding="utf-8"))
    if s5b["boxfit_sha"] != engine_sha or s5c["boxfit_sha"] != engine_sha:
        raise RuntimeError(f"installed blueox-boxfit {engine_sha[:7]} != the 5b / 5c record ({s5b['boxfit_sha'][:7]} / {s5c['boxfit_sha'][:7]})")
    if s5b["prod_asof"] != s5c["prod_asof"]:
        raise RuntimeError("5b and 5c as-of months differ")
    built = dt.datetime.now(tz=dt.UTC).astimezone().isoformat(timespec="seconds")
    w = load_frame(wells_dir)
    fid = frame_identity(w)
    est = estimate_record(w, n_boot)
    rf = risk_rows(est, n_boot, built)
    cr = curves_record(w, rf)
    tcs, mem = cr["type_curves"], cr["members"]
    relabel = {b: {"same_pool": int(w.loc[w.bench_pool == b, "same_pool"].sum()),
                   "sandwich": int((w.bench_pool.eq(b) & w.same_pool & w.view_class.eq("sandwich")).sum())} for b in BENCHES}
    infill = rf[(rf.level == "pair") & (rf.term == "infill")].set_index(["bench", "stream"])["factor"]
    n5c = s5c["benches"]
    checks = [
        {"check": "installed blueox-boxfit = the 5b and 5c record SHA", "result": engine_sha[:7], "pass": True},
        {"check": "5c frame re-estimates the committed factors.csv (log-OLS record view, 3 record metrics × 2 benches)",
         "result": f"{fid['n_terms']} terms, worst rel {fid['worst_rel']:.1e}", "pass": True},
        {"check": "estimation wells = 5c n_est", "result": f"WCA {fid['n_est']['WCA']:,} / BS2_S {fid['n_est']['BS2_S']:,} (5c {n5c['WCA']['n_est']:,} / {n5c['BS2_S']['n_est']:,})",
         "pass": fid["n_est"]["WCA"] == n5c["WCA"]["n_est"] and fid["n_est"]["BS2_S"] == n5c["BS2_S"]["n_est"]},
        {"check": "each area curve re-fitted from its members' fits = the 5b stored row (oil / water qo, qi, Di, b, EUR; gas α, β, EUR)",
         "result": f"{len(tcs)} rows, worst rel {cr['refit_worst_rel']:.1e} (tol {REFIT_TOL:.0e})", "pass": True},
        {"check": "members = the 5b strict cohort; included per curve = n_wells", "result": f"{mem['api10'].nunique():,} wells × 3 streams = {len(mem):,} rows (5b cohort {s5b['n_cohort']:,})",
         "pass": mem["api10"].nunique() == s5b["n_cohort"]},
        {"check": "no member in docs/box/exclusions.csv", "result": "0", "pass": True},
        {"check": "relaxation rungs stored (rung 3 never emitted, D37)", "result": str(sorted(set(tcs["relaxation_step"]))), "pass": set(tcs["relaxation_step"]) <= {1, 2, 4, 5}},
    ]
    if drift is not None:
        checks.append({"check": "live curated.dev_scenario vs the 5c frame (class, infill flag)",
                       "result": f"{drift['n']:,} scored: {drift['n_class_changed']} class / {drift['n_infill_changed']} infill changed, {drift['n_missing_live']} missing",
                       "pass": drift["n_class_changed"] == 0 and drift["n_infill_changed"] == 0})
    store_plan = [{"table": "box.type_curve", "rows": len(tcs), "key": "35 areas of record (extent 6, areas v1) × oil / gas / water, version 1"},
                  {"table": "box.tc_member", "rows": len(mem), "key": f"{mem['api10'].nunique():,} wells × 3 curves; included {int(mem['included'].sum()):,}"},
                  {"table": "box.risk_factor", "rows": len(rf), "key": "3 streams × (reference + pair + class per bench; class across benches), version 1"}]
    e_wca = dfr.est_frame(w[w.bench_pool == "WCA"])
    ref_gor = e_wca.loc[(e_wca["p_class"] == dfm.REFERENCE) & ~e_wca["p_infill"], "gor12_vs_local"]
    summ = {"built_at": built, "engine_sha": engine_sha, "data_asof": s5b["prod_asof"], "n_boot": n_boot, "n_est": fid["n_est"], "relabel": relabel, "checks": checks,
            "store_plan": store_plan, "frame_identity": fid, "refit_worst_rel": cr["refit_worst_rel"], "drift": drift,
            "infill_record": {f"{b}/{s}": float(v) for (b, s), v in infill.items()},
            "ref_mult": {s: {"median": float(tcs.loc[tcs.stream == s, "ref_mult"].median()), "min": float(tcs.loc[tcs.stream == s, "ref_mult"].min()),
                             "max": float(tcs.loc[tcs.stream == s, "ref_mult"].max())} for s in WEIGHT_COL},
            "wca_reference_gor_vs_local": {"mean": float(ref_gor.mean()), "median": float(ref_gor.median()), "n": int(ref_gor.notna().sum())},
            "rungs": rf[rf.level == "pair"].groupby(["bench", "stream"])["rung"].value_counts().rename("n").reset_index().to_dict("records")}
    ctx = {"summary": summ, "risk": rf, "type_curves": tcs, "compare": compare_5c(rf, est), "flags": build_flags(rf, relabel, summ)}
    (out / "record.html").write_text(render_page(ctx), encoding="utf-8")
    rf.assign(params=rf["params"].map(json.dumps)).to_csv(out / "risk_factor.csv", index=False)
    tcs.assign(**{c: tcs[c].map(json.dumps) for c in ("anchors", "params", "fit_meta")}).to_csv(out / "type_curve.csv", index=False)
    mem.to_csv(out / "tc_member.csv", index=False)
    ctx["compare"].to_csv(out / "compare_5c.csv", index=False)
    (out / "summary.json").write_text(json.dumps(rep._clean(summ), indent=2, default=rep._json), encoding="utf-8")
    return {"summary": summ, "risk": rf, "type_curves": tcs, "members": mem, "flags": ctx["flags"]}


def build_flags(rf: pd.DataFrame, relabel: dict[str, Any], summ: dict[str, Any]) -> list[str]:
    """Things the gate should see; none is resolved here."""
    out = []
    thin3 = rf[(rf.level == "basin_class") & (rf.stream == "oil") & (rf.n_pairs < tr.LADDER_MIN_N)]
    for r in thin3.itertuples():
        out.append(f"Rung 3 is terminal whatever its n (D45): the across-benches <b>{r.term}</b> factor rests on {r.n_pairs} wells (oil {r.factor:.3f}).")
    if relabel["WCA"]["sandwich"]:
        out.append(f"D42 on sandwiches: {relabel['WCA']['sandwich']} WCA sandwich wells have a same-pool side. That side became infill and the other side's one-sided "
                   "relation (topfill / underfill) was kept. D42's text names topfill / underfill only; this is my reading for sandwiches.")
    out.append("The D42 relabel runs on the RAW (class, parent bench) before rare pairs pool to '&lt;class&gt;|other'. 5c's pooled view relabelled after pooling, so a rare "
               "same-pool pair could hide inside '|other'. That ordering is one source of the 5c-vs-5d pooled-view differences in §2.")
    out.append("ref_mult (D43) uses the factors of record with ACTUAL cum-12 weights (5c's mult_cum12 convention). The stored params stay the reviewed as-built curve, and the "
               "reference curve is derived from them (qo, qi × ref_mult). The alternative is to store the reference curve itself. Your call.")
    g = summ["wca_reference_gor_vs_local"]
    out.append(f"The gas GOR factors are relative to the reference class, but the D30 local level is the median of mixed-scenario neighbours. In WCA, reference-class wells "
               f"run {g['mean']:.3f}× (mean) / {g['median']:.3f}× (median) their local level (n {g['n']:,}). α_PUD = α_local + ln f_GOR (D46 as written) leaves that offset in. "
               "Reported, not changed.")
    out.append("BS2_S has factors but no TC areas and no curves (the D4 pilot is WCA), so box.type_curve holds WCA only.")
    return out
