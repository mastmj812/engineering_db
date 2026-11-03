"""BOX step 23 — the production record runs, both basins. Plan: docs/box/step23-2026-11-03/RECORD_PLAN.md (box/record23).

READ-ONLY (gate 23a):
    python -m scripts.box_record23 pack                 Midland evidence pack: per group the SHIPPED treatment's tuning disclosure
                                                        (mid_r2 x D150 [x WCA_1 haircut]) from the 21b tuning views, the 21c holdout
                                                        lines, and gate question (a) = WCA_1's D102 table on both treatments
                                                        -> docs/box/step23-*/midland_pack.json (+ .sha256), d102_wca1.csv
    python -m scripts.box_record23 measure --basin delaware [--src-run 25]
                                                        D116 re-measure on the source run's sticks (forecast + no-precedent) at its
                                                        data date, live producers: incumbent gates (D114, table factor), the D150
                                                        factor, outcomes -> runs/step23/<basin>/outcomes.csv.gz + summary.json
    python -m scripts.box_record23 measure --basin midland [--from-cache]
                                                        the same on the Midland's drillable in-extent sticks (21a revision 4 / 5 rules;
                                                        --from-cache = the 21b stick cache, no DB)
    python -m scripts.box_record23 expect --basin delaware   expected identities + bench totals of the derived run vs runs 19 / 25

WRITES (each on its own explicit go; DB_* env points at the rehearsal container first):
    python -m scripts.box_record23 store --basin B --src-run N [--commit]
            derive the record candidate from run N (Delaware: run 25; Midland: the stored base run) in ONE transaction: oil rows x
            new / old factor, no-forecast sticks re-classed, D150 proximity rows, identities checked, ROLLED BACK unless --commit.
            Never makes a record (that is `flip`, its own go).
    python -m scripts.box_record23 flip --basin B --run N [--commit]
            make run N its basin's record. REFUSED unless Steven has priced run N (box_econ.box_pud_econ rows for every forecast
            location on every deck the outgoing record carries) — the 2026-10-30 blank-econ flip is never repeated.
"""

from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import math
import pickle
import subprocess
import sys
import time
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from box import acceptance as ac
from box import basin as bsn
from box import provisional as pv
from box import prox_cont as pc
from box import record23 as rc
from box import step21 as st21

RUNS = Path("runs")
OUT = RUNS / "step23"
SHIP = "mid_r2c"  # view column tag: mid_r2 x the D150 continuous factor (gas = mid_r2)
HORIZONS = (12, 24, 36, 48)

_failures: list[str] = []


def _check(ok: bool, msg: str) -> None:
    print(f"    {'ok  ' if ok else 'FAIL'} {msg}", flush=True)
    if not ok:
        _failures.append(msg)


def _git(*a: str) -> str:
    return subprocess.run(["git", *a], capture_output=True, text=True, check=False).stdout.strip()


def _jdump(o: Any) -> Any:
    if isinstance(o, (np.integer,)):
        return int(o)
    if isinstance(o, (np.floating,)):
        return None if not math.isfinite(float(o)) else float(o)
    if isinstance(o, (dt.date, pd.Timestamp)):
        return str(o)
    raise TypeError(type(o))


# ----------------------------------------------------------------------------
# pack: the Midland disclosure on the shipped treatment + gate question (a)
# ----------------------------------------------------------------------------


def _d150_drilled(v: pd.DataFrame, links: pd.DataFrame) -> pd.Series:
    """api10 -> level x F_R3 on the DRILLED side (21b / 21c / D150 validation; box/prospective21's treatment)."""
    model, rule = rc.d150(bsn.MIDLAND)
    d = v[["api10"]].drop_duplicates().reset_index(drop=True)
    rf = pc.rule_factor(d, pc.parents(links, drilled=True), model, rule)
    return pd.Series(model.level * rf["F_rule"].to_numpy(float), index=d["api10"].astype(str))


def _ship(views: dict[str, pd.DataFrame], fac: pd.Series, haircut: dict[int, float] | None, name: str) -> None:
    """In place: pred_<name>_<s><k> = mid_r2 x D150 (oil) [x the per-horizon haircut factor on oil]."""
    from box import step21b as sb

    sb.add_prox(views, fac.to_dict(), SHIP)
    for view in views.values():
        for s in ac.STREAMS:
            for k in HORIZONS:
                src = f"pred_{SHIP}_{s}{k}"
                if src not in view:
                    continue
                f = haircut[k] if (haircut and s == "oil") else 1.0
                view[f"pred_{name}_{s}{k}"] = view[src].to_numpy(float) * f
                view[f"{name}_err_{s}{k}"] = ac.hc.pct_error(view[f"actual_{s}{k}"].to_numpy(float), view[f"pred_{name}_{s}{k}"].to_numpy(float))


def cmd_pack(a: argparse.Namespace) -> int:
    from box import production16 as p16
    from box import step21b as sb
    from box import step21c as s21c
    from scripts import box_step21b_score as sc
    from scripts import box_step21c as h21

    t0 = time.time()
    links = pd.read_pickle(RUNS / "step21a" / "links.pkl")
    groups = rc.midland_groups()
    d102_21c = rc.d102_as_delivered()
    pack: dict[str, Any] = {"step": "23", "written_on": dt.datetime.now(dt.UTC).date().isoformat(), "decisions": ["D149", "D150", "D151", "D152"],
                            "treatment": "mid_r2 x D150 Midland R3 (level 1.067; drilled-side configuration, as 21b / 21c / D150 scored) "
                                         "x WCA_1's D102 oil haircut; gas = mid_r2",
                            "sources": {"tuning_views": "runs/step21b (tuning_views.sha256 of step 21d)", "holdout_views": "runs/step21c",
                                        "links": "runs/step21a/links.pkl"}, "groups": {}}
    d102_rows = []
    for g, meta in groups.items():
        tv = sc.load_group(RUNS / "step21b", g)
        views = tv["views"]
        v0 = sb.frames(views)
        fac = _d150_drilled(v0, links)
        _ship(views, fac, None, "c")  # pred_c = mid_r2 x D150 (no haircut): the D102 base on the shipped treatment
        tc_c = sb.score(views, [st21.RAW, "c"])
        hv = None
        if g in h21.GROUPS:
            h = h21.load_views(RUNS / "step21c" / g, g, h21.htag(g))
            hv = h["views"]
            hfac = _d150_drilled(sb.frames(hv), links)
            _ship(hv, hfac, None, "c")
            hc_c = sb.score(hv, [st21.RAW, "c"])
            new = s21c.d102_table(tc_c, hc_c, variant="c")
            d102_rows.append(new.assign(group=g, treatment="D150 (mid_r2 x level x F_R3)"))
        hcut = None
        if meta["haircut_streams"]:
            hcut = d102_21c if a.haircut == "as_delivered" else {int(r.horizon): float(r.factor) for r in d102_rows[-1].itertuples()
                                                                  if r.stream == "oil"}
        _ship(views, fac, hcut, "ship")
        if hv is not None:
            _ship(hv, hfac, hcut, "ship")
        v = sb.frames(views)
        pk = pv.package_frame(v, "ship")
        disc_t = pv.disclosure(pk, g)
        pooled = {(r.stream, int(r.horizon)): r for r in disc_t.itertuples()}
        lines = []
        for r in disc_t.itertuples():
            lines.append({"label": "tuning (shipped: mid_r2 x D150" + (" x haircut" if hcut else "") + ")", "scope": "all tuning wells",
                          "stream": r.stream, "horizon": f"cum-{int(r.horizon)}", "packages": int(r.n_packages), "bias": float(r.bias),
                          "range_95": [float(r.range_lo), float(r.range_hi)]})
        h_b: dict[tuple[str, int], tuple[float, int]] = {}
        if hv is not None:
            vh = sb.frames(hv)
            disc_h = pv.disclosure(pv.package_frame(vh, "ship"), g)
            for r in disc_h.itertuples():
                h_b[(r.stream, int(r.horizon))] = (float(r.bias), int(r.n_packages))
                lines.append({"label": "holdout (one-time 21c set, re-read on the shipped treatment)", "scope": "holdout packages",
                              "stream": r.stream, "horizon": f"cum-{int(r.horizon)}", "packages": int(r.n_packages), "bias": float(r.bias),
                              "range_95": [float(r.range_lo), float(r.range_hi)]})
        thin = pd.to_numeric(v["n_local"], errors="coerce") < 3
        tb = pv.disclosure(pv.package_frame(v[thin.to_numpy()], "ship"), g)
        t12 = tb[(tb.stream == "oil") & (tb.horizon == 12)]
        t24 = tb[(tb.stream == "oil") & (tb.horizon == 24)]
        vint = pv.by_vintage(pk, g)
        lv = vint[(vint.stream == "oil") & (vint.horizon == 12)].sort_values("cutoff")
        lv = lv.iloc[-1] if len(lv) else None
        spec = f"mid_r2c{'_wf' if hcut else ''}"
        hb = {s: {str(k): {"record_variant": spec,
                           "box_v2_pooled_bias": float(pooled[(s, k)].bias) if (s, k) in pooled else None,
                           "box_v2_pooled_packages": int(pooled[(s, k)].n_packages) if (s, k) in pooled else 0,
                           "haircut_factor": (hcut[k] if (hcut and s == "oil") else 1.0),
                           "disclosed_bias": float(pooled[(s, k)].bias) if (s, k) in pooled else None,
                           "disclosed_packages": int(pooled[(s, k)].n_packages) if (s, k) in pooled else 0,
                           "disclosed_basis": "mid_r2 x D150" + (" x D102 haircut" if (hcut and s == "oil") else "") + ", tuning packages "
                                              "pooled over cutoffs 2019-2024 (step 21b views, re-read on the shipped treatment)",
                           "holdout_bias": h_b.get((s, k), (None, None))[0], "holdout_packages": h_b.get((s, k), (None, None))[1],
                           "d99_judged": None} for k in HORIZONS} for s in ac.STREAMS}
        disc = {"hindcast_bias": hb, "radius_ranges": p16.radius_ranges(v, "ship", f"{st21.RAW}_radius_mi"),
                "radius_ranges_basis": "tuning packages, mid_r2 x D150" + (" x haircut" if hcut else "") + " (step 21b views)",
                "tier": meta["tier"], "label": f"D151 {meta['tier']} (step 21), D150 continuous proximity",
                "holdout": ("one-time D52 holdout scored at 21c on the 21 table treatment (D151); the lines here re-read it on the shipped "
                            "treatment" if hv is not None else "none: no D99 cell (provisional by construction)"),
                "lead": {"label": lines[0]["label"] if lines else None, "scope": "all tuning wells"}, "lines": lines,
                "latest_vintage_text": (f"latest vintage ({str(lv['cutoff'])[:4]} cutoff cohort, {int(lv['n_packages'])} packages): oil cum-12 "
                                        f"{float(lv['bias']):+.1%} vs forecast" if lv is not None else "latest vintage: no cell"),
                "thin_control": {"oil_cum12_bias": float(t12["bias"].iloc[0]) if len(t12) else None,
                                 "oil_cum12_wells": int(t12["n_packages"].iloc[0]) if len(t12) else 0,
                                 "oil_cum24_bias": float(t24["bias"].iloc[0]) if len(t24) else None,
                                 "oil_cum24_wells": int(t24["n_packages"].iloc[0]) if len(t24) else 0},
                "selection": {"rules": "same bench > distance; lateral = Cui translation, Midland panel (Delaware panel when longer than the "
                                       "cohort, rev 8), analogs >= 5,000 ft, no upper bound; measured spacing (D119)", "decision": "D146-D149"},
                "error_convention": "actual / forecast - 1 (negative = forecast HIGH)"}
        haircut = None if not hcut else {"oil": {str(k): {"factor": hcut[k], "basis": a.haircut} for k in HORIZONS}, "gas": None}
        pack["groups"][g] = {"group": g, "spec": spec, "tier": meta["tier"], "haircut": haircut, "disclosure": disc,
                             "d150_factor_mean_tuning": float(fac.mean()), "n_tuning_wells": int(v["api10"].nunique())}
        print(f"[{g}] {meta['tier']}, oil cum-12 shipped {hb['oil']['12']['disclosed_bias']:+.3f} ({time.time() - t0:.0f} s)", flush=True)
    a.docs.mkdir(parents=True, exist_ok=True)
    d102 = pd.concat(d102_rows, ignore_index=True)
    d21 = pd.read_csv(Path("docs") / "box" / "step21c-2026-11-02" / "d102.csv")
    d102 = d102.merge(d21[["group", "stream", "horizon", "factor"]].rename(columns={"factor": "factor_21_table"}), on=["group", "stream", "horizon"],
                      how="left")
    d102.to_csv(a.docs / "d102_d150.csv", index=False)
    raw = json.dumps(pack, indent=1, sort_keys=True, default=_jdump).replace("\r\n", "\n").encode("utf-8")
    (a.docs / f"midland_pack_{a.haircut}.json").write_bytes(raw)
    (a.docs / f"midland_pack_{a.haircut}.sha256").write_text(hashlib.sha256(raw).hexdigest() + "\n", encoding="utf-8")
    print(f"wrote {a.docs} ({time.time() - t0:.0f} s)")
    return 0


# ----------------------------------------------------------------------------
# measure: the D116 re-measure + D150 outcomes (read-only)
# ----------------------------------------------------------------------------

_SRC_SQL = """
SELECT pf.location_id, pf.stick_id, pf.formation_blueox, pf.bench, pf.coverage, pf.recon_status, {ext}ST_AsText(l.geom),
       so.eur, so.prox_factor, sg.eur, sw.eur
FROM box.pud_forecast pf JOIN box.location l ON l.location_id = pf.location_id
LEFT JOIN box.pud_forecast_stream so ON so.run_id = pf.run_id AND so.location_id = pf.location_id AND so.stream = 'oil'
LEFT JOIN box.pud_forecast_stream sg ON sg.run_id = pf.run_id AND sg.location_id = pf.location_id AND sg.stream = 'gas'
LEFT JOIN box.pud_forecast_stream sw ON sw.run_id = pf.run_id AND sw.location_id = pf.location_id AND sw.stream = 'water'
WHERE pf.run_id = %(run)s AND pf.coverage IN ('covered', 'covered_provisional', 'not_covered_no_precedent')
"""
_RECON_SQL = "SELECT stick_id, status FROM curated.reconciled_inventory WHERE stick_id = ANY(%(ids)s)"


def measure_delaware(a: argparse.Namespace) -> int:
    import shapely

    from box import edge_gap as eg
    from box import prox_dose as pdz
    from box import prox_pud as pp
    from box import prox_pud_report as ppr
    from box import prox_study_report as psr
    from box.tc_curve_report import _read
    from etl.db import get_connection
    from scripts import box_step16d_prox as sdp

    t0 = time.time()
    out = a.out or OUT / "delaware"
    out.mkdir(parents=True, exist_ok=True)
    conn = get_connection()
    box = _box_conn(a, conn)
    try:
        run, through, _rv, basin = _read(box, sdp._RUN_ID_SQL, {"run": a.src_run})[0]
        if basin != bsn.DELAWARE:
            raise SystemExit(f"run {a.src_run} is {basin}")
        cols = ["location_id", "stick_id", "formation_blueox", "bench", "coverage", "recon_status", "wkt", "oil_eur", "prox_factor", "gas_eur", "water_eur"]
        p = pd.DataFrame(_read(box, _SRC_SQL.format(ext=sdp._ext(box)), {"run": run}), columns=cols)
        e = pd.DataFrame(_read(conn, sdp._EREBOR_SQL, {"ids": [int(x) for x in p["stick_id"]]}), columns=["stick_id", "tvd_ft", "deplet_t", "operator"])
        recon = dict(_read(conn, _RECON_SQL, {"ids": [int(x) for x in p["stick_id"]]}))
        p = p.merge(e, on="stick_id", how="left")
        p["tvd_ft"] = pd.to_numeric(p["tvd_ft"], errors="coerce")
        p["geom"] = eg.to_ft([shapely.from_wkt(w) for w in p["wkt"]])
        u = psr.pull_universe(conn, basin)
        print(f"run {run} ({basin}, data through {through}): {len(p):,} sticks (forecast + no-precedent), producers {len(u):,} "
              f"({time.time() - t0:.0f} s)", flush=True)
        prior = pd.DataFrame(_read(box, "SELECT location_id, outcome, factor FROM box.pud_proximity WHERE run_id = %(run)s", {"run": run}),
                             columns=["location_id", "outcome_src", "factor_src"])
    finally:
        if box is not conn:
            box.close()
        conn.close()
    ref = through  # D115 / D116: producers >= 12 months on at the run's data date
    L = ppr.pud_links(p, u, ref)
    with open(out / "pud_links.pkl", "wb") as f:
        pickle.dump(L, f)
    ids = [str(x) for x in p["location_id"]]
    cfg = pdz.configuration(ids, L.assign(permit=False)).set_index("api10")
    cfg["bench"] = p.set_index(p["location_id"].astype(str))["formation_blueox"].reindex(cfg.index)
    with open(a.prec_runs / "links.pkl", "rb") as f:
        cl = pickle.load(f)
    with open(a.prec_runs / "children.pkl", "rb") as f:
        kids = pickle.load(f)
    kc = pdz.configuration(list(kids["api10"]), cl).merge(kids[["api10", "bench"]], on="api10", how="left")
    prec = pp.precedent(kc, pp.siblings(cl))
    inc = pp.decide_all(cfg, pp.haircut_lookup(pd.read_csv(ppr.HAIRCUT_TABLE)), prec)
    fac = rc.stick_factors(L, bsn.DELAWARE, ids)
    oc = rc.outcomes(inc, fac)
    d = p.drop(columns=["geom", "wkt"]).assign(key=ids).set_index("key").join(oc).join(cfg.drop(columns="bench"))
    d = d.join(inc[["haircut_key", "pair_key", "prec_multi", "prec_package"]].rename(columns={"factor": "factor_table"}))
    d["factor_table"] = inc["factor"].reindex(d.index)
    d = d.reset_index().merge(prior, on="location_id", how="left")
    d["recon_now"] = d["stick_id"].map(recon).fillna("not_reconciled")
    d["src_forecast"] = d["coverage"].isin(["covered", "covered_provisional"])
    d["n_recent_producers"] = d["key"].map(ppr.recent_flags(L)).fillna(0).astype(int)
    d["n_permit_parents"] = d["key"].map(ppr.permit_flags(L)).fillna(0).astype(int)
    d.to_csv(out / "outcomes.csv.gz", index=False, compression="gzip")
    s = summarise(d, run, through)
    s |= {"n_links": len(L), "seconds": round(time.time() - t0), "precedent_source": str(a.prec_runs), "code_sha": _git("rev-parse", "HEAD")}
    (out / "summary.json").write_text(json.dumps(s, indent=1, default=_jdump), encoding="utf-8")
    print(json.dumps(s, indent=1, default=_jdump))
    return 0


def summarise(d: pd.DataFrame, run: int, through: Any) -> dict[str, Any]:
    """The re-measure against the source run: moves in the keep set, realized-since, and expected oil by bench."""
    real = d["recon_now"].str.startswith("realized")
    keep = d["keep"].astype(bool)
    src_f = d["src_forecast"].astype(bool)
    dropped = src_f & ~keep
    readmit = ~src_f & keep
    exp = d[src_f & keep & ~real].copy()
    exp["oil_new"] = exp["oil_eur"].astype(float) * rc.rescale(exp["prox_factor"].astype(float), exp["factor"].astype(float))
    by = exp.groupby("formation_blueox").agg(n=("oil_new", "size"), oil_src_mmbbl=("oil_eur", lambda x: x.sum() / 1e6),
                                              oil_new_mmbbl=("oil_new", lambda x: x.sum() / 1e6), gas_bcf=("gas_eur", lambda x: x.sum() / 1e6),
                                              water_mmbbl=("water_eur", lambda x: x.sum() / 1e6))
    return {"source_run": run, "data_through": str(through), "n_sticks": len(d), "src_forecast": int(src_f.sum()),
            "outcomes": d["outcome"].value_counts().to_dict(), "incumbent_outcomes_now": d["incumbent_outcome"].value_counts().to_dict(),
            "incumbent_moved_vs_source": int((d["incumbent_outcome"] != d["outcome_src"]).sum()),
            "dropped_no_precedent_now": int(dropped.sum()), "readmitted_needs_source_rows": int(readmit.sum()),
            "realized_since_source": int((src_f & real).sum()), "conflict_now_forecast": int((src_f & keep & (d["recon_now"] == "conflict")).sum()),
            "factor": {"mean": float(exp["factor"].mean()), "min": float(exp["factor"].min()), "max": float(exp["factor"].max()),
                       "share_gt_1": float((exp["factor"] > 1).mean())},
            "expected_forecast": len(exp), "oil_src_mmbbl": float(exp["oil_eur"].sum() / 1e6), "oil_new_mmbbl": float(exp["oil_new"].sum() / 1e6),
            "by_bench": by.reset_index().to_dict("records")}


def measure_midland(a: argparse.Namespace) -> int:
    """The Midland stick outcomes from the 21b stick cache (configuration as measured 2026-11-01 for the 21 / 24 scores; the live
    re-measure runs at the build): 21b incumbent decisions (box/step21_prox + the 21b table) + D150 factors (every existing producer)."""
    from box import prox_pud as pp
    from box import step21_prox as sp
    from box import step21b as sb

    out = OUT / "midland"
    out.mkdir(parents=True, exist_ok=True)
    with open(RUNS / "step21b" / "prox.pkl", "rb") as f:
        prox = pickle.load(f)
    cfg = prox["cfg"]
    table = pd.read_csv(rc.MIDLAND_TABLE)
    hair = pp.haircut_lookup(table)
    unfit = sb.unfit_mask(cfg, table)
    inc = sp.decide_all(cfg[~unfit], hair, prox["prec"], prox["prec_pat"], prox["near_same"]).reindex(cfg.index)
    inc.loc[unfit, "outcome"] = "unfit_no_usable_rung"
    ns = prox["near_same"].reindex(cfg.index)
    inc.loc[unfit & (ns <= sp.SPACING_FLOOR_FT), "outcome"] = "no_forecast_spacing"
    Lp = sp.existing_as_parents(sp.by_depth(pd.read_pickle(RUNS / "step21a" / "pud_links.pkl")))
    ids = [str(x) for x in cfg.index]
    fac = rc.stick_factors(Lp, bsn.MIDLAND, ids)
    oc = rc.outcomes(inc.assign(outcome=inc["outcome"].replace({"unfit_no_usable_rung": "haircut"})), fac)
    oc["bench"] = cfg["bench"].reindex(oc.index).to_numpy()
    oc["incumbent_raw"] = inc["outcome"].reindex(oc.index).to_numpy()
    oc.to_csv(out / "outcomes_from_cache.csv.gz", compression="gzip")
    t = oc.groupby(["bench", "outcome"]).size().unstack(fill_value=0)
    fstat = oc[oc["keep"]].groupby("bench")["factor"].agg(["size", "mean", "min", "max"])
    s = {"source": "runs/step21b/prox.pkl (21b, built 2026-11-01) + runs/step21a/pud_links.pkl", "n_sticks": len(oc),
         "outcomes": oc["outcome"].value_counts().to_dict(), "unfit": int(unfit.sum()), "forecast": int(oc["keep"].sum()),
         "by_bench_outcome": t.reset_index().to_dict("records"), "factor_by_bench": fstat.reset_index().to_dict("records")}
    (out / "summary_from_cache.json").write_text(json.dumps(s, indent=1, default=_jdump), encoding="utf-8")
    print(json.dumps(s, indent=1, default=_jdump))
    return 0


def _box_conn(a: argparse.Namespace, live: Any) -> Any:
    """Where the run's box rows live: `--box-db rehearsal` = the scripts.box_rehearsal container (23b), else live. Curated is
    always read from live (the step-16d prox-measure pattern)."""
    if a.box_db != "rehearsal":
        return live
    from scripts import box_rehearsal as reh

    return reh._box_conn()


def measure_midland_run(a: argparse.Namespace) -> int:
    """D116 on the stored Midland base run (23b / 23c): the 21a stick-side links re-measured live at the run's data date (by-depth
    class, every existing producer a parent), the 21b incumbent decisions (21b table, unfit -> spacing / D150 factor, pattern and
    400-ft floor, the drilled-side precedent of runs/step21b/prox.pkl) and the D150 R3 factors. Read-only on both databases."""
    import shapely

    from box import edge_gap as eg
    from box import prox_dose as pdz
    from box import prox_pud as pp
    from box import prox_pud_report as ppr
    from box import prox_study_report as psr
    from box import step21_prox as sp
    from box import step21b as sb
    from box.tc_curve_report import _read
    from etl.db import get_connection
    from scripts import box_step16d_prox as sdp

    t0 = time.time()
    out = a.out or OUT / "midland"
    out.mkdir(parents=True, exist_ok=True)
    conn = get_connection()
    box = _box_conn(a, conn)
    try:
        run, through, _rv, basin = _read(box, sdp._RUN_ID_SQL, {"run": a.src_run})[0]
        if basin != bsn.MIDLAND:
            raise SystemExit(f"run {a.src_run} is {basin}")
        cols = ["location_id", "stick_id", "formation_blueox", "bench", "coverage", "recon_status", "wkt", "oil_eur", "prox_factor", "gas_eur", "water_eur"]
        p = pd.DataFrame(_read(box, _SRC_SQL.format(ext=sdp._ext(box)), {"run": run}), columns=cols)
        e = pd.DataFrame(_read(conn, sdp._EREBOR_SQL, {"ids": [int(x) for x in p["stick_id"]]}), columns=["stick_id", "tvd_ft", "deplet_t", "operator"])
        recon = dict(_read(conn, _RECON_SQL, {"ids": [int(x) for x in p["stick_id"]]}))
        u = psr.pull_universe(conn, basin)
    finally:
        if box is not conn:
            box.close()
        conn.close()
    p = p.merge(e, on="stick_id", how="left")
    p["tvd_ft"] = pd.to_numeric(p["tvd_ft"], errors="coerce")
    p["geom"] = eg.to_ft([shapely.from_wkt(w) for w in p["wkt"]])
    print(f"run {run} ({basin}, data through {through}): {len(p):,} forecast sticks, producers {len(u):,} ({time.time() - t0:.0f} s)", flush=True)
    bd = sp.by_depth(ppr.pud_links(p.assign(location_id=p["location_id"].astype(str)), u, through))  # 21a revision 3
    Lp = sp.existing_as_parents(bd)  # revision 4: every existing producer a parent; what the store's named parents read
    with open(out / "pud_links.pkl", "wb") as f:
        pickle.dump(Lp, f)
    ids = [str(x) for x in p["location_id"]]
    cfg = pdz.configuration(ids, Lp.assign(permit=False)).set_index("api10")
    cfg["bench"] = p.set_index(p["location_id"].astype(str))["formation_blueox"].reindex(cfg.index)
    with open(RUNS / "step21b" / "prox.pkl", "rb") as f:
        prox = pickle.load(f)
    table = pd.read_csv(rc.MIDLAND_TABLE)
    unfit = sb.unfit_mask(cfg, table)
    near = sp.nearest_same_ft(Lp)
    inc = sp.decide_all(cfg[~unfit], pp.haircut_lookup(table), prox["prec"], prox["prec_pat"], near).reindex(cfg.index)
    inc.loc[unfit, "outcome"] = "unfit_no_usable_rung"
    inc.loc[unfit & (near.reindex(cfg.index) <= sp.SPACING_FLOOR_FT), "outcome"] = "no_forecast_spacing"
    fac = rc.stick_factors(Lp, bsn.MIDLAND, ids)
    oc = rc.outcomes(inc.assign(outcome=inc["outcome"].replace({"unfit_no_usable_rung": "haircut"})), fac)
    d = p.drop(columns=["geom", "wkt"]).assign(key=ids).set_index("key").join(oc)
    d["incumbent_raw"] = inc["outcome"].reindex(d.index)
    d["factor_table"] = inc["factor"].reindex(d.index)
    d = d.reset_index()
    d["recon_now"] = d["stick_id"].map(recon).fillna("not_reconciled")
    d["src_forecast"] = d["coverage"].isin(["covered", "covered_provisional"])
    d["outcome_src"] = np.nan  # a base run has no proximity rows: old factor = 1 (pud_forecast_stream.prox_factor default)
    d["n_recent_producers"] = d["key"].map(ppr.recent_flags(bd)).fillna(0).astype(int)
    d["n_permit_parents"] = d["key"].map(ppr.permit_flags(Lp)).fillna(0).astype(int)
    d.to_csv(out / "outcomes.csv.gz", index=False, compression="gzip")
    s = summarise(d, run, through)
    s |= {"n_links": len(Lp), "seconds": round(time.time() - t0), "precedent_source": "runs/step21b/prox.pkl", "code_sha": _git("rev-parse", "HEAD"),
          "box_db": a.box_db}
    (out / "summary.json").write_text(json.dumps(s, indent=1, default=_jdump), encoding="utf-8")
    print(json.dumps(s, indent=1, default=_jdump))
    return 0


def cmd_measure(a: argparse.Namespace) -> int:
    if a.basin == bsn.DELAWARE:
        return measure_delaware(a)
    if a.from_cache:
        return measure_midland(a)
    if a.src_run == rc.DELAWARE_SOURCE_RUN:
        raise SystemExit("--src-run: the stored Midland base run")
    return measure_midland_run(a)


# ----------------------------------------------------------------------------
# store (derive) and flip — each on its own explicit go
# ----------------------------------------------------------------------------


def _cols(q: Any, t: str) -> list[str]:
    return [r[0] for r in q("SELECT column_name FROM information_schema.columns WHERE table_schema = 'box' AND table_name = %s "
                            "ORDER BY ordinal_position", (t,)).fetchall()]


def _copy(cur: Any, table: str, cols: list[str], df: pd.DataFrame) -> None:
    with cur.copy(f"COPY {table} ({', '.join(cols)}) FROM STDIN") as cp:
        for row in df[cols].itertuples(index=False):
            cp.write_row([None if (v is None or (isinstance(v, float) and math.isnan(v)) or v is pd.NA) else v for v in row])


PROX_COLS = ["location_id", "coverage", "config_class", "n_same", "n_topfill", "n_underfill", "n_parents_total", "flanked_same", "flanked_topfill",
             "flanked_underfill", "outcome", "factor", "haircut_key", "pair_key", "prec_multi", "prec_package", "label", "n_permit_parents",
             "n_recent_producers", "table_ref"]
PROX_INT_COLS = ("n_same", "n_topfill", "n_underfill", "n_parents_total", "prec_multi", "prec_package", "n_permit_parents", "n_recent_producers")


PARENT_COLS = ["location_id", "api10", "cls", "parent_bench", "dv_ft", "dh_ft", "dxy_ft", "overlap", "age_days", "permit"]
SIDE_CLS = {"same": "same", "below": "topfill", "above": "underfill"}  # D150 side (parent deeper = below) -> the sql/65 class words


def named_parents(pud_links: pd.DataFrame, basin: str) -> pd.DataFrame:
    """The D150 counting parents of every stick (box/prox_cont.parents, stick side) as box.pud_proximity_parent rows. Midland
    links carry every existing producer (21a revision 4): age_days may be < 365 there (sql/71 relaxes the CHECK)."""
    q = pc.parents(pud_links, drilled=False)
    return pd.DataFrame({"location_id": q["child"].astype("int64").to_numpy(), "api10": q["parent"].astype(str).to_numpy(),
                         "cls": q["side"].map(SIDE_CLS).to_numpy(), "parent_bench": q["parent_bench"].to_numpy(), "dv_ft": q["dv_ft"].to_numpy(float),
                         "dh_ft": q["dh_ft"].to_numpy(float), "dxy_ft": q["dxy_ft"].to_numpy(float), "overlap": q["overlap"].to_numpy(float),
                         "age_days": q["age_days"].fillna(0).astype(int).clip(lower=0).to_numpy(), "permit": q["permit"].astype(bool).to_numpy()})


def cmd_store(a: argparse.Namespace) -> int:
    """Derive the step-23 run from `--src-run` (identities before COMMIT; rollback without --commit). Requires sql/71 applied."""
    from psycopg.types.json import Jsonb

    from etl.db import get_connection

    t0 = time.time()
    oc = pd.read_csv(a.outcomes, dtype={"key": str}, low_memory=False)
    if "key" not in oc.columns:
        oc = oc.rename(columns={oc.columns[0]: "key"})
    oc["location_id"] = oc["location_id"].astype("int64") if "location_id" in oc else oc["key"].astype("int64")
    dirty = _git("status", "--porcelain", "--", "box/record23.py", "scripts/box_record23.py", "box/prox_cont.py", "sql/71_box_step23.sql")
    if dirty and not a.allow_dirty:
        raise SystemExit(f"code not committed:\n{dirty}")
    code_sha = _git("rev-parse", "HEAD")
    model, rule = rc.d150(a.basin)
    table_ref = f"D150 {a.basin} {rule} level {model.level:.4f} prox_cont {pc.DIGEST[:16]} @ {rc.gate_24a()['frozen_sha'][:7]}"
    conn = get_connection()
    try:
        with conn.cursor() as cur:
            q = cur.execute
            src = q("SELECT run_id, basin, is_record, data_through FROM box.forecast_run WHERE run_id = %s", (a.src_run,)).fetchone()
            _check(src is not None and src[1] == a.basin, f"source run {a.src_run} is a stored {a.basin} run ({src})")
            if _failures:
                raise RuntimeError("source")
            S = a.src_run
            real = {int(r[0]) for r in q("SELECT pf.location_id FROM box.pud_forecast pf JOIN curated.reconciled_inventory ri ON ri.stick_id = pf.stick_id "
                                          "WHERE pf.run_id = %s AND ri.status LIKE 'realized%%'", (S,)).fetchall()}
            q("CREATE TEMP TABLE tmp_real (location_id bigint PRIMARY KEY) ON COMMIT DROP")
            _copy(cur, "tmp_real", ["location_id"], pd.DataFrame({"location_id": sorted(real)}))
            # gate 23a (f): D145 extended to this basin — a stick reconciled as CONFLICT now is not drillable (not_covered_conflict)
            conf: set[int] = set()
            if a.d145:
                conf = {int(r[0]) for r in q("SELECT pf.location_id FROM box.pud_forecast pf JOIN curated.reconciled_inventory ri ON ri.stick_id = pf.stick_id "
                                             "WHERE pf.run_id = %s AND ri.status = 'conflict'", (S,)).fetchall()}
            q("CREATE TEMP TABLE tmp_conf (location_id bigint PRIMARY KEY) ON COMMIT DROP")
            _copy(cur, "tmp_conf", ["location_id"], pd.DataFrame({"location_id": sorted(conf)}))
            q("CREATE TEMP TABLE tmp_px (location_id bigint PRIMARY KEY, old double precision NOT NULL, new double precision NOT NULL, "
              "keep boolean NOT NULL, drop_realized boolean NOT NULL) ON COMMIT DROP")
            src_oil = dict(q("SELECT location_id, prox_factor FROM box.pud_forecast_stream WHERE run_id = %s AND stream = 'oil'", (S,)).fetchall())
            ra = oc["keep"].astype(bool) & ~oc["location_id"].isin(src_oil)
            carried: set[int] = set()
            if a.readmitted == "carry-refusal" and ra.any():  # gate 23a (d): a stick the source refused stays refused (no source rows)
                oc.loc[ra, "outcome"] = oc.loc[ra, "outcome_src"]
                oc.loc[ra, "keep"] = False
                # its proximity row is the SOURCE run's (the configuration + D114 keys that refused it), copied verbatim below —
                # never the refusal word on today's re-measured configuration, which carries no D114 keys (sql/71 multi_ck)
                carried = {int(x) for x in oc.loc[ra, "location_id"]} - real - conf
                print(f"    note {int(ra.sum())} re-admitted sticks carry the source run's refusal ({oc.loc[ra, 'outcome'].value_counts().to_dict()})", flush=True)
            o = oc[oc["location_id"].isin(src_oil)].copy()
            o["old"] = o["location_id"].map(src_oil).astype(float)
            o["drop_realized"] = o["location_id"].isin(real)
            _check(len(o) == len(src_oil), f"every source forecast location has an outcome ({len(o):,} / {len(src_oil):,})")
            readmit = oc[~oc["location_id"].isin(src_oil) & oc["keep"].astype(bool)]
            _check(len(readmit) == 0, f"no re-admitted stick without source rows ({len(readmit)})")
            if _failures:
                raise RuntimeError("universe")
            o["new"] = o["factor"].astype(float)
            o["keep"] = o["keep"].astype(bool) & ~o["drop_realized"] & ~o["location_id"].isin(conf)
            _copy(cur, "tmp_px", ["location_id", "old", "new", "keep", "drop_realized"], o)
            disc = {"decisions": "D150 (step 24 rev 5), D153 (Delaware derivation)" if a.basin == bsn.DELAWARE else "D150, D151, D152",
                    "table_ref": table_ref, "source_run": S, "code_sha": code_sha, "outcomes_sha256": hashlib.sha256(Path(a.outcomes).read_bytes()).hexdigest(),
                    "counts": o.loc[o["keep"], "outcome"].value_counts().to_dict(), "dropped_realized": int(o["drop_realized"].sum()),
                    "d145_conflict": {"applied": bool(a.d145), "sticks": len(conf)},
                    "readmitted_carried_refusal": {"sticks": len(carried), "proximity_rows": f"copied from run {S} (its own table_ref)"}}
            if a.basin == bsn.MIDLAND:
                disc["method_23"] = json.loads(Path(a.method_block).read_text(encoding="utf-8")) if a.method_block else rc.method_block()
                bad = rc.check_method(disc["method_23"])
                _check(not bad, f"Midland method block = the 21d definition ({bad})")
            new = q("""INSERT INTO box.forecast_run (basin, spec, code_sha, engine_sha, dealintake_config, report_version, data_through, volumes_basis,
                           horizon_months, haircut, calendar_factor, disclosure, extents, counts, notes, is_record)
                       SELECT basin, spec, %s, engine_sha, dealintake_config, report_version, data_through, volumes_basis, horizon_months, haircut,
                              calendar_factor, (disclosure - 'proximity') || jsonb_build_object('proximity', %s::jsonb), extents, counts,
                              notes || %s, false
                       FROM box.forecast_run WHERE run_id = %s RETURNING run_id""",
                    (code_sha, Jsonb(json.loads(json.dumps(disc, default=_jdump))),
                     (f"; step 23 (D150{', D153' if a.basin == bsn.DELAWARE else ''}): derived from run {S}, oil x level x F_{rule} on every forecast stick "
                     f"(source prox_factor divided out), incumbent precedent gates, gas / water / analogs identical, no refit"), S)).fetchone()[0]
            pc_ = _cols(q, "pud_forecast")
            cf = "EXISTS (SELECT 1 FROM tmp_conf k WHERE k.location_id = p.location_id)"
            search = {"search_mode", "radius_mi", "radius_class", "n_analogs"}  # sql/65 uncovered_ck: a not-searched class carries none

            def col(c: str) -> str:
                if c == "run_id":
                    return "%(new)s"
                if c == "coverage":
                    return f"CASE WHEN {cf} THEN 'not_covered_conflict' WHEN t.keep IS FALSE THEN 'not_covered_no_precedent' ELSE p.coverage END"
                if c == "recon_status":
                    return f"CASE WHEN {cf} THEN 'conflict' ELSE p.recon_status END"
                if c in search:
                    return f"CASE WHEN {cf} THEN NULL ELSE p.{c} END"
                return f"p.{c}"

            sel = ", ".join(col(c) for c in pc_)
            # a stick reconciled as drilled since the source run leaves the universe (erebor then classes it `realized` itself)
            q(f"INSERT INTO box.pud_forecast ({', '.join(pc_)}) SELECT {sel} FROM box.pud_forecast p LEFT JOIN tmp_px t USING (location_id) "
              "WHERE p.run_id = %(src)s AND NOT EXISTS (SELECT 1 FROM tmp_real r WHERE r.location_id = p.location_id)", {"new": new, "src": S})
            n_univ = q("SELECT (SELECT count(*) FROM box.pud_forecast WHERE run_id = %s), (SELECT count(*) FROM box.pud_forecast WHERE run_id = %s)",
                       (S, new)).fetchone()
            _check(n_univ[1] == n_univ[0] - len(real), f"universe {n_univ[1]:,} = source {n_univ[0]:,} - realized since {len(real):,}")
            # proximity first: its CHECKs (sql/71) fail in seconds, before the slow stream / month copy
            px = oc[~oc["location_id"].isin(real | conf | carried)].copy()
            px = px[px["location_id"].isin(set(src_oil) | set(oc.loc[~oc["keep"].astype(bool), "location_id"]))]
            px["coverage"] = np.where(px["keep"].astype(bool), px.get("coverage_src", px.get("coverage")), "not_covered_no_precedent")
            px["label"] = None
            px["table_ref"] = table_ref
            px["factor"] = px["factor"].astype(float)
            for c in PROX_INT_COLS:  # read back from CSV as float where any value is NULL ("78.0" refused by an integer column)
                if c in px:
                    px[c] = pd.to_numeric(px[c]).round().astype("Int64")
            for c in PROX_COLS:
                if c not in px:
                    px[c] = None
            _copy(cur, "box.pud_proximity", ["run_id", *PROX_COLS], px.assign(run_id=new))
            if carried:
                pcols = ", ".join(PROX_COLS)
                q(f"INSERT INTO box.pud_proximity (run_id, {pcols}) SELECT %(new)s, {pcols} FROM box.pud_proximity "
                  "WHERE run_id = %(src)s AND location_id = ANY(%(ids)s)", {"new": new, "src": S, "ids": sorted(carried)})
                got = q("SELECT count(*) FROM box.pud_proximity WHERE run_id = %s AND location_id = ANY(%s) AND table_ref IS DISTINCT FROM %s",
                        (new, sorted(carried), table_ref)).fetchone()[0]
                _check(got == len(carried), f"{len(carried)} carried refusals keep run {S}'s proximity rows verbatim ({got:,})")
            par = named_parents(pd.read_pickle(a.links), a.basin)
            par = par[par["location_id"].isin(set(o.loc[o["keep"], "location_id"]))]
            _copy(cur, "box.pud_proximity_parent", ["run_id", *PARENT_COLS], par.assign(run_id=new))
            n_par = len(par)
            sc_ = _cols(q, "pud_forecast_stream")
            scaled = {"eur", "eur_per_kft", "cum12", "cum24"}
            sel = ", ".join("%(new)s" if c == "run_id" else "CASE WHEN s.stream = 'oil' THEN t.new ELSE 1 END" if c == "prox_factor" else
                            f"CASE WHEN s.stream = 'oil' THEN s.{c} * t.new / t.old ELSE s.{c} END" if c in scaled else f"s.{c}" for c in sc_)
            q(f"INSERT INTO box.pud_forecast_stream ({', '.join(sc_)}) SELECT {sel} FROM box.pud_forecast_stream s JOIN tmp_px t USING (location_id) "
              "WHERE s.run_id = %(src)s AND t.keep", {"new": new, "src": S})
            q("""INSERT INTO box.pud_forecast_month (run_id, location_id, stream, month_no, volume)
                 SELECT %(new)s, m.location_id, m.stream, m.month_no, CASE WHEN m.stream = 'oil' THEN m.volume * t.new / t.old ELSE m.volume END
                 FROM box.pud_forecast_month m JOIN tmp_px t USING (location_id) WHERE m.run_id = %(src)s AND t.keep""", {"new": new, "src": S})
            for t in ("location_analog", "location_water_analog"):
                ac_ = _cols(q, t)
                sel = ", ".join("%(new)s" if c == "run_id" else f"a.{c}" for c in ac_)
                q(f"INSERT INTO box.{t} ({', '.join(ac_)}) SELECT {sel} FROM box.{t} a JOIN tmp_px x USING (location_id) "
                  "WHERE a.run_id = %(src)s AND x.keep", {"new": new, "src": S})
            q("""UPDATE box.forecast_run SET counts = (SELECT jsonb_object_agg(coverage, n) FROM (SELECT coverage, count(*) n FROM box.pud_forecast
                 WHERE run_id = %(new)s GROUP BY 1) c) WHERE run_id = %(new)s""", {"new": new})
            identity(q, S, new)
            got = q("SELECT count(*) FROM box.pud_proximity_parent WHERE run_id = %s", (new,)).fetchone()[0]
            _check(got == n_par, f"{n_par:,} named D150 parents of kept locations ({got:,})")
            _check(q("SELECT is_record FROM box.forecast_run WHERE run_id = %s AND basin = %s", (new, a.basin)).fetchone()[0] is False, f"run {new} is NOT a record")
        if _failures:
            conn.rollback()
            print(f"ROLLED BACK: {len(_failures)} check(s) failed", flush=True)
            return 1
        if a.commit:
            conn.commit()
            print(f"COMMITTED run {new} (not record) ({time.time() - t0:.0f} s)", flush=True)
        else:
            conn.rollback()
            print(f"rehearsal OK — rolled back (pass --commit to store) ({time.time() - t0:.0f} s)", flush=True)
    finally:
        conn.close()
    return 0


def identity(q: Any, S: int, new: int) -> None:
    print("identities", flush=True)
    keep = q("SELECT count(*) FROM tmp_px WHERE keep").fetchone()[0]
    for st in ("oil", "gas", "water"):
        n = q("SELECT count(*) FROM box.pud_forecast_stream WHERE run_id = %s AND stream = %s", (new, st)).fetchone()[0]
        _check(n == keep, f"{st} stream rows {n:,} = kept source locations {keep:,}")
    r = q("""SELECT sum(s1.eur), sum(s0.eur * t.new / t.old) FROM box.pud_forecast_stream s1 JOIN box.pud_forecast_stream s0
             ON s0.run_id = %s AND s0.location_id = s1.location_id AND s0.stream = s1.stream JOIN tmp_px t ON t.location_id = s1.location_id
             WHERE s1.run_id = %s AND s1.stream = 'oil'""", (S, new)).fetchone()
    _check(abs(r[0] - r[1]) <= REL_TOL * r[1], f"oil EUR {r[0] / 1e6:,.3f} MMbbl = source x new / old {r[1] / 1e6:,.3f}")
    for st in ("gas", "water"):
        d = q("""SELECT count(*) FILTER (WHERE s1.eur IS DISTINCT FROM s0.eur OR s1.params IS DISTINCT FROM s0.params OR s1.prox_factor <> 1)
                 FROM box.pud_forecast_stream s1 JOIN box.pud_forecast_stream s0 ON s0.run_id = %s AND s0.location_id = s1.location_id
                 AND s0.stream = s1.stream WHERE s1.run_id = %s AND s1.stream = %s""", (S, new, st)).fetchone()[0]
        _check(d == 0, f"{st} rows identical to the source ({d} differ)")
    g = q("""WITH m AS MATERIALIZED (SELECT location_id, stream, count(*) n, sum(volume) v FROM box.pud_forecast_month WHERE run_id = %s GROUP BY 1, 2)
             SELECT count(*), count(*) FILTER (WHERE m.n <> 600 OR abs(m.v - s.eur) > 1e-3 * s.eur) FROM m JOIN box.pud_forecast_stream s
             ON s.run_id = %s AND s.location_id = m.location_id AND s.stream = m.stream""", (new, new)).fetchone()
    _check(g[1] == 0 and g[0] == 3 * keep, f"every stream: 600 months summing to its EUR within 0.1 % ({g[0]:,} groups, {g[1]} off)")
    bad = q("""SELECT count(*) FROM box.pud_proximity x JOIN box.pud_forecast_stream s ON s.run_id = x.run_id AND s.location_id = x.location_id
               AND s.stream = 'oil' WHERE x.run_id = %s AND abs(s.prox_factor - x.factor) > 1e-12""", (new,)).fetchone()[0]
    _check(bad == 0, "oil prox_factor = pud_proximity.factor on every forecast location")
    orph = q("""SELECT (SELECT count(*) FROM box.pud_forecast_stream s WHERE s.run_id = %(n)s AND NOT EXISTS (SELECT 1 FROM box.pud_forecast p
                        WHERE p.run_id = s.run_id AND p.location_id = s.location_id AND p.coverage IN ('covered', 'covered_provisional')))
                     + (SELECT count(*) FROM box.location_analog a WHERE a.run_id = %(n)s AND NOT EXISTS (SELECT 1 FROM box.pud_forecast_stream s
                        WHERE s.run_id = a.run_id AND s.location_id = a.location_id))""", {"n": new}).fetchone()[0]
    _check(orph == 0, f"no orphan stream / analog rows ({orph})")
    _check(q("SELECT count(*) FROM box.pud_forecast_stream WHERE run_id = %s", (S,)).fetchone()[0] > 0, f"run {S} untouched")


REL_TOL = 1e-9


def priced(q: Any, run: int, basin: str) -> dict[str, Any]:
    """Is `run` priced like the basin's current record? Every forecast location x every deck the outgoing record carries (or, with no
    priced record yet, >= 1 deck covering every forecast location)."""
    n = q("SELECT count(*) FROM box.pud_forecast WHERE run_id = %s AND coverage IN ('covered', 'covered_provisional')", (run,)).fetchone()[0]
    rec = q("SELECT run_id FROM box.forecast_run WHERE basin = %s AND is_record", (basin,)).fetchone()
    decks_rec = {r[0] for r in q("SELECT DISTINCT deck_id FROM box_econ.box_pud_econ WHERE run_id = %s", (rec[0],)).fetchall()} if rec else set()
    have = dict(q("SELECT deck_id, count(DISTINCT location_id) FROM box_econ.box_pud_econ WHERE run_id = %s GROUP BY 1", (run,)).fetchall())
    need = decks_rec or set(have)
    ok = bool(need) and all(have.get(dk, 0) == n for dk in need)
    return {"forecast_locations": n, "outgoing_record": rec[0] if rec else None, "decks_required": sorted(need), "priced_by_deck": have, "ok": ok}


def cmd_flip(a: argparse.Namespace) -> int:
    from etl.db import get_connection

    conn = get_connection()
    try:
        with conn.cursor() as cur:
            q = cur.execute
            b = q("SELECT basin, is_record FROM box.forecast_run WHERE run_id = %s", (a.run,)).fetchone()
            if b is None or b[0] != a.basin:
                raise SystemExit(f"run {a.run} is not a stored {a.basin} run ({b})")
            p = priced(q, a.run, a.basin)
            print(json.dumps(p, indent=1))
            if not p["ok"]:
                raise SystemExit(f"REFUSED: run {a.run} is not priced like the {a.basin} record — flipping now would blank erebor's econ and "
                                 "curated.box_scout_locations (2026-10-30). Wait for Steven.")
            before = q("SELECT count(*) FROM curated.box_scout_locations").fetchone()[0]
            q("UPDATE box.forecast_run SET is_record = false, superseded_by = %s WHERE basin = %s AND is_record", (a.run, a.basin))
            q("UPDATE box.forecast_run SET is_record = true WHERE run_id = %s AND basin = %s", (a.run, a.basin))
            recs = q("SELECT basin, run_id FROM box.forecast_run WHERE is_record ORDER BY 1").fetchall()
            after = q("SELECT count(*) FROM curated.box_scout_locations").fetchone()[0]
            print(f"records {recs}; box_scout_locations {before:,} -> {after:,}")
            if after == 0:
                conn.rollback()
                raise SystemExit("box_scout_locations would be EMPTY after the flip: rolled back")
        if a.commit:
            conn.commit()
            print(f"COMMITTED: run {a.run} is the {a.basin} record")
        else:
            conn.rollback()
            print("rehearsal — rolled back (pass --commit)")
    finally:
        conn.close()
    return 0


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("pack")
    p.add_argument("--docs", type=Path, default=rc.DOCS)
    p.add_argument("--haircut", choices=("as_delivered", "recomputed"), default="as_delivered")
    m = sub.add_parser("measure")
    m.add_argument("--basin", choices=(bsn.DELAWARE, bsn.MIDLAND), required=True)
    m.add_argument("--src-run", type=int, default=rc.DELAWARE_SOURCE_RUN)
    m.add_argument("--prec-runs", type=Path, default=RUNS / "prox")
    m.add_argument("--from-cache", action="store_true")
    m.add_argument("--box-db", choices=("live", "rehearsal"), default="live", help="where the source run's box rows are (curated: live)")
    m.add_argument("--out", type=Path, default=None, help="default runs/step23/<basin>")
    s = sub.add_parser("store")
    s.add_argument("--basin", choices=(bsn.DELAWARE, bsn.MIDLAND), required=True)
    s.add_argument("--src-run", type=int, required=True)
    s.add_argument("--outcomes", type=Path, required=True)
    s.add_argument("--links", type=Path, required=True, help="the measure's pud_links.pkl (named D150 parents)")
    s.add_argument("--no-d145", dest="d145", action="store_false",
                   help="D154 (f) extends D145 to the Delaware (conflict sticks -> not_covered_conflict); this flag turns it off")
    s.add_argument("--readmitted", choices=("refuse", "carry-refusal"), default="carry-refusal",  # D154 (d)
                   help="a stick the source refused that the re-measure would forecast (no source rows): refuse the store, or keep its refusal")
    s.add_argument("--method-block", type=Path, default=None, help="Midland: the stored method block (default box/record23.method_block())")
    s.add_argument("--commit", action="store_true")
    s.add_argument("--allow-dirty", action="store_true")
    f = sub.add_parser("flip")
    f.add_argument("--basin", choices=(bsn.DELAWARE, bsn.MIDLAND), required=True)
    f.add_argument("--run", type=int, required=True)
    f.add_argument("--commit", action="store_true")
    a = ap.parse_args(argv)
    rc_ = {"pack": cmd_pack, "measure": cmd_measure, "store": cmd_store, "flip": cmd_flip}[a.cmd](a)
    return rc_ or (1 if _failures else 0)


if __name__ == "__main__":
    sys.exit(main())
