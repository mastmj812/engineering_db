"""BOX step 7c — production run of the frozen analog workup (box_v2_wf, D58) for the D67 universe.

    python -m scripts.box_pud_run build  [--out runs/box7c] [--workers N] [--benches WCA,BS2_S,WCXY_WCA1]
                                                                            read-only vs the warehouse; writes run.pkl
    python -m scripts.box_pud_run radius --views runs/box9a/bs2s --bench BS2_S   step 9c: the D69 radius-class ranges of a 9c bench
                                                                            from its 9a tuning views (committed under docs/box/step9c-*)
    python -m scripts.box_pud_run store  [--out runs/box7c] [--record]        writes run.pkl to the DB the DB_* env points at
    python -m scripts.box_pud_run render [--out runs/box7c] [--docs docs/box/step7c-2026-10-15]
    python -m scripts.box_pud_run rehaircut --from runs/box7c_r2 --out runs/box8_c1   re-applies the CURRENT haircut (D92) to an
                                                                                     existing build's raw months; nothing else changes

build mirrors the D53 harness's analog pool construction (box/backtest_report.run_fold + box/acceptance.add_analog_predictions_v2) at
a production cutoff = the month after the last full production month, with no holdout: gate-1 WCA well set (exclusions applied),
per-well boxfit fits at the cutoff, D56 completed laterals, D55 strike search, short-lateral Cui translation. Each covered location
gets the box_v2 P50 per stream (box/production.fit_location); an equivalence check re-runs the harness's own predict_location_v2 on a
sample and requires identical monthly volumes. F(k) is calibrated exactly as the harness does (seeded 500-well training sample,
as-of cohorts) and PUBLISHED, not applied (D63). The D62 haircut factors come from the stored tuning + holdout cells and are applied
to the rate by the D92 C1 shape (box/production.apply_haircut_c1); runs 4 and 6 used D62's linear cumulative factor.

store writes box.location / location_source (first run = seed; a re-run of the same vintage reuses its ids; a NEW vintage carries
locations forward by the D73 crosswalk from the most recent earlier vintage; an older vintage than one stored is refused), box.forecast_run, box.pud_forecast (every universe row), pud_forecast_stream,
pud_forecast_month (COPY), location_analog, all in ONE transaction, with identity checks before COMMIT (any failure rolls back).
--record makes the run the record (the previous record is superseded). !! A store against Supabase needs Michael's go.

Step 9c (`--benches`, default WCA = runs 4-7): one run covers several box.production.PRODUCTION_BENCHES groups, each built on its
own pool at the same production cutoff - WCA by the 7c path above; BS2_S and WCXY_WCA1 by the analog fold every 9a / 9b bench was
scored with (backtest_report.run_fold_analog: per-well fits inside the bench's extent of record, no TC areas), selection with the
bench's deal-intake label. Haircut per group (box.production9c.haircut_for: WCA D62, BS2_S D102, WCXY none per D97), F(k) and
disclosure per group. forecast_run.haircut / calendar_factor / disclosure keep the FIRST group's (WCA) keys at the top level - what
erebor reads today - and carry every group under "by_bench" (D103: run-level spec stays 'box_v2_wf', per-group spec in by_bench).
Identity: per group, covered + no_analogs = that group's in-extent universe, exactly.
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import pickle
import subprocess
import sys
import time
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
from psycopg.types.json import Jsonb

from box import acceptance as ac
from box import analog as an
from box import backtest_report as br
from box import dev_factor_report as dfr
from box import edge_gap_report as egr
from box import exclusions
from box import hindcast as hc
from box import hindcast_production as hp
from box import hindcast_report as hr
from box import production as pr
from box import production9c as p9
from box import tc_area_report as tar
from box import tc_curve_report as rep
from box import tc_record_report as trr
from box import tune9a_report as t9
from dealintake import config as di_config
from etl.db import get_connection
from scripts.box_tc_curves import boxfit_sha

ACC = Path("docs") / "box" / "acceptance"
SPREAD = Path("docs") / "box" / "step7a-2026-10-14" / "spread_by_radius.csv"
WELLS = Path("docs") / "box" / "step1-2026-10-06"
K_F = ac.K_MONTHS  # F(k) published for months 1..48 (the harness horizon)
N_EQUIV = 24


CODE_PATHS = ("box", "scripts", "dealintake", ".claude/skills/deal-intake/config", "requirements-dealintake.txt")


def _git_sha() -> str:
    """HEAD commit, '-dirty' when anything under the code paths is modified OR untracked (git describe ignores untracked files)."""
    head = subprocess.run(["git", "rev-parse", "HEAD"], capture_output=True, text=True, check=True).stdout.strip()
    dirty = subprocess.run(["git", "status", "--porcelain", "--", *CODE_PATHS], capture_output=True, text=True, check=True).stdout.strip()
    return head + ("-dirty" if dirty else "")


# ----------------------------------------------------------------------------
# build
# ----------------------------------------------------------------------------


def build_pool(conn: Any, workers: int, wells_dir: Path = WELLS, bench: str = "WCA") -> dict[str, Any]:
    """The harness's pool at a production cutoff (run_fold lines: areas -> curves -> factors -> trn / sp / t_act; then
    add_analog_predictions_v2: f_oil, build_pool, U-turn legs, completed laterals). Non-WCA benches: build_pool_analog."""
    if bench != "WCA":
        return build_pool_analog(conn, workers, wells_dir, bench)
    wells, excluded = exclusions.drop(egr.load_final_sets(wells_dir, ("WCA",)))
    last = rep.last_full_month(rep._read(conn, rep._MONTHS_SQL))
    cutoff = br._add_months(last, 1)
    asof = br._prev_month(cutoff)
    ar = hr.rebuild_areas(conn, wells, asof)
    cb = hr.rebuild_curves(conn, wells, ar, cutoff, asof, workers)
    fx = hr.rebuild_factors(conn, cb, wells, wells_dir, asof, workers)
    tabs = {s: trr.factor_table(fx["rf"], hr.POOL, s) for s in ("oil", "gas")}
    wca = fx["frames"][hr.POOL].reset_index(drop=True)
    trn = wca.join(hr.well_factors(wca, tabs))
    trn["lateral_ft"] = pd.to_numeric(trn["lateral_ft"], errors="coerce")
    trn = trn[(trn["lateral_ft"] > 0) & trn["area_no"].notna()].reset_index(drop=True)
    trn["area_no"] = trn["area_no"].astype(int)
    sp = br.spacing(conn, sorted(set(trn["api10"])))
    trn = br.prep(trn, sp)
    t_ids = list(trn["api10"])
    t_act = hp.monthly_matrix(cb["prod"][cb["prod"]["api10"].isin(set(t_ids))], t_ids, asof=asof, k=K_F)
    f_oil = dict(zip(trn["api10"], trn["f_oil"], strict=True))
    pool = an.build_pool(cb["frame"], cb["fits"], sp, f_oil)
    ut = an.uturn_leg_spacing(conn, sorted(set(pool["api10"]) | set(trn["api10"])))
    tvd = dict(zip(cb["frame"]["api10"], pd.to_numeric(cb["frame"]["tvd_ft"], errors="coerce"), strict=True))
    pool2 = an.with_completed_laterals(pool, ut, tvd)
    return {"wells": wells, "n_excluded": len(excluded), "last": last, "cutoff": cutoff, "asof": asof, "cb": cb, "trn": trn, "t_act": t_act,
            "ut": ut, "pool": pool, "pool2": pool2, "k_areas": len(ar["geoms"]), "label": "WCA", "extent_id": None}


def build_pool_analog(conn: Any, workers: int, wells_dir: Path, bench: str) -> dict[str, Any]:
    """Step 9c: the pool the 9a / 9b harness scored `bench` with (box.backtest_report.run_fold_analog's lines up to its scored
    wells, then add_analog_predictions_v2's pool lines), at the production cutoff: BENCH_SPECS well set + tags, per-well fits of
    every pre-cutoff well inside the bench's extent of record, the D9 12-mo training cohort (F(k) sample), f_oil = 1."""
    spec = ac.BENCH_SPECS[bench]
    wells, excluded, _ = ac.bench_wells(wells_dir, bench)
    last = rep.last_full_month(rep._read(conn, rep._MONTHS_SQL))
    cutoff = br._add_months(last, 1)
    asof = br._prev_month(cutoff)
    ext = tar.pull_extent(conn, spec["extent"])
    d4 = hr.cohort_frame(wells, ext["geom_ft"], asof)
    cb = hr.rebuild_curves(conn, wells, {"geoms": [ext["geom_ft"]], "frame": d4}, cutoff, asof, workers, area_curves=False)
    trn = hr.wca_factor_frame(conn, cb, wells, asof, pool=bench)
    trn["lateral_ft"] = pd.to_numeric(trn["lateral_ft"], errors="coerce")
    trn = trn[(trn["lateral_ft"] > 0) & trn["area_no"].notna()].reset_index(drop=True)
    trn["area_no"] = trn["area_no"].astype(int)
    trn["f_oil"], trn["f_gor"] = 1.0, 1.0
    sp = br.spacing(conn, sorted(set(trn["api10"])))
    trn["spacing_ft"] = trn["api10"].map(sp)
    t_ids = list(trn["api10"])
    t_act = hp.monthly_matrix(cb["prod"][cb["prod"]["api10"].isin(set(t_ids))], t_ids, asof=asof, k=K_F)
    pool = an.build_pool(cb["frame"], cb["fits"], sp, dict(zip(trn["api10"], trn["f_oil"], strict=True)))
    ut = an.uturn_leg_spacing(conn, sorted(set(pool["api10"]) | set(trn["api10"])))
    tvd = dict(zip(cb["frame"]["api10"], pd.to_numeric(cb["frame"]["tvd_ft"], errors="coerce"), strict=True))
    pool2 = an.with_completed_laterals(pool, ut, tvd)
    return {"wells": wells, "n_excluded": len(excluded), "last": last, "cutoff": cutoff, "asof": asof, "cb": cb, "trn": trn, "t_act": t_act,
            "ut": ut, "pool": pool, "pool2": pool2, "k_areas": 0, "label": spec["label"], "extent_id": ext["extent_id"], "extent_ft": ext["geom_ft"]}


def calendar_factor(P: dict[str, Any], workers: int) -> dict[str, Any]:
    """F(k) exactly as box.acceptance.add_analog_predictions_v2 calibrates box_v2 (seeded sample, as-of cohorts, leave-self-out)."""
    trn, t_act, ut = P["trn"], P["t_act"], P["ut"]
    xy = np.column_stack(br.dfr._xy(trn["mid_lon"], trn["mid_lat"]))
    rng = np.random.default_rng(ac.SEED)
    ti = np.sort(rng.choice(len(trn), size=min(ac.F_SAMPLE, len(trn)), replace=False))
    sub = trn.iloc[ti].reset_index(drop=True)
    locs = [{"api10": r.api10, "x": xy[ti][i, 0], "y": xy[ti][i, 1], "lateral_ft": float(r.lateral_ft),
             "lateral_eff": an.completed_lateral(r.api10, float(r.lateral_ft), ut), "spacing_ft": r.spacing_ft,
             "fp_max": pd.Timestamp(r.first_production_date).date()} for i, r in enumerate(sub.itertuples())]
    pt = an.predict_many_v2(locs, P["pool"], P["pool2"], P["cutoff"], K_F, workers, bench=P["label"])
    mt = an.monthly_arrays_v2(pt, K_F)
    out = {}
    for s in pr.STREAMS:
        F, n = hc.calendar_factor_curve(t_act[s][ti], mt["box_v2"][s])
        out[s] = {"F": [float(x) for x in F], "n_wells": [int(x) for x in n]}
    return out


def disclosure(cells: pd.DataFrame, hcut: dict[str, Any]) -> dict[str, Any]:
    hold = pd.read_csv(ACC / "cells_holdout_v2.csv")
    hold = hold[(hold.variant == ac.RECORD_V2) & (hold.n_packages >= ac.MIN_PACKAGES)]
    bias: dict[str, Any] = {}
    for s in pr.STREAMS:
        bias[s] = {}
        for k in pr.HORIZONS:
            x = hold[(hold.stream == s) & (hold.horizon == k)]
            w = x["n_packages"].to_numpy(float)
            bias[s][str(k)] = {"box_v2_pooled_bias": hcut[s][k]["bias"], "box_v2_pooled_packages": hcut[s][k]["n_packages"],
                               "box_v2_wf_holdout_bias": float(np.sum(w * x["pkg_bias"].to_numpy(float)) / w.sum()) if len(x) else None,
                               "box_v2_wf_holdout_packages": int(w.sum())}
    rr = pd.read_csv(SPREAD)
    ranges = {f"{r.radius_class}|cum-{int(r.horizon)}": {"p90_low": float(r.box_p90_low), "p10_high": float(r.box_p10_high), "packages": int(r.packages),
                                                          "bias": float(r.box_bias)} for r in rr.itertuples()}
    return {"hindcast_bias": bias, "radius_ranges": ranges, "error_convention": "actual / forecast - 1 (negative = forecast HIGH)",
            "source": "docs/box/acceptance cells (tuning + holdout), docs/box/step7a-2026-10-14/spread_by_radius.csv"}


def nearest_by_stick(conn: Any, u: pd.DataFrame, cand: pd.DataFrame) -> dict[int, tuple[float, str] | None]:
    """D64 nearest neighbour per candidate. Neighbours = the SAME formation only: a WCA_2 stick under a WCA_1 one is vertical
    staggering (~130 ft TVD apart), not lateral spacing; pooling them read 11-300 ft gaps (7c first build, 2026-10-15)."""
    out: dict[int, tuple[float, str] | None] = {}
    for form, t in cand.groupby("formation_blueox"):
        nb_u = u[u["formation_blueox"] == form]
        pdp = pr.pdp_sticks(conn, [form])
        nb_lines = pr.project_ft(list(nb_u["wkt"]) + list(pdp["wkt"]))
        nb_ids = [f"pud:{s}" for s in nb_u["stick_id"]] + [f"pdp:{x}" for x in pdp["api10"]]
        g = pr.nearest_gaps(pr.project_ft(list(t["wkt"])), nb_lines, [f"pud:{s}" for s in t["stick_id"]], nb_ids)
        out.update(dict(zip(t["stick_id"].astype(int), g, strict=True)))
    return out


def cmd_annotate(a: argparse.Namespace) -> int:
    """Add the D64 nearest-neighbour identity to an artifact built before locations() recorded it (read-only). Refuses unless every
    recomputed gap equals the stored planned spacing exactly: the annotation never changes a forecast input."""
    A = _load(a.out)
    u, locs = A["universe"], A["locs"]
    with get_connection() as conn:
        near = nearest_by_stick(conn, u, u[u["coverage"] == "covered"])
    bad = 0
    for loc in locs:
        nb = near[loc["stick_id"]]
        g = None if nb is None else float(nb[0])
        if (g is None) != (loc["spacing_ft"] is None) or (g is not None and g != loc["spacing_ft"]):
            bad += 1
        loc["nearest"] = None if nb is None else nb[1]
        loc["near_pdp_ft"] = g if nb is not None and str(nb[1]).startswith("pdp:") else None
    if bad:
        raise SystemExit(f"{bad} recomputed gaps differ from the stored planned spacing: not annotating")
    A["run"]["annotations"] = {"nearest_neighbour": {"code_sha": _git_sha(), "at": dt.datetime.now(tz=dt.UTC).isoformat(timespec="seconds")}}
    with open(a.out / "run.pkl", "wb") as fh:
        pickle.dump(A, fh)
    n = sum(loc["near_pdp_ft"] is not None and loc["near_pdp_ft"] < 500 for loc in locs)
    print(f"annotated {len(locs)} locations; every gap reproduced exactly; {n} within 500 ft of an existing same-formation producer")
    return 0


def locations(u: pd.DataFrame, conn: Any, bench: str | None = None) -> list[dict[str, Any]]:
    """Covered candidates as harness locations: midpoint xy (UTM 13N ft), Novi planned lateral (stick length if missing; Novi PUD
    sticks are straight, so the completed lateral = the lateral), D64 planned spacing. `bench` = one PRODUCTION_BENCHES group
    (None = every covered row, runs 4-7)."""
    cov = u["coverage"] == "covered"
    cand = u[cov & (u["prod_bench"] == bench) if bench is not None else cov].reset_index(drop=True)
    # D64 neighbours = the SAME formation only: a WCA_2 stick under a WCA_1 one is vertical staggering (~130 ft TVD apart), not
    # lateral spacing — pooling them read 11-300 ft "gaps" (7c first build, 2026-10-15)
    near = nearest_by_stick(conn, u, cand)
    gaps = [None if near[int(s)] is None else near[int(s)][0] for s in cand["stick_id"]]
    x, y = dfr._xy(cand["mid_lon"], cand["mid_lat"])
    out = []
    for i, r in enumerate(cand.itertuples()):
        lat = float(r.ll_ft) if np.isfinite(r.ll_ft) and r.ll_ft > 0 else float(r.stick_ft)
        g = gaps[i]
        out.append({"api10": f"pud{r.stick_id}", "stick_id": int(r.stick_id), "prod_bench": r.prod_bench, "x": float(x[i]), "y": float(y[i]), "lateral_ft": lat, "lateral_eff": lat,
                    "spacing_ft": float(g) if g is not None else None, "planned_spacing_ft": float(g) if g is not None else pr.GAP_DEFAULT_FT,
                    "spacing_source": "neighbour_gap" if g is not None else "default_880", "fp_max": None,
                    "nearest": None if near[int(r.stick_id)] is None else near[int(r.stick_id)][1],
                    "near_pdp_ft": float(g) if g is not None and str(near[int(r.stick_id)][1]).startswith("pdp:") else None})
    return out


def equivalence(P: dict[str, Any], locs: list[dict[str, Any]], res: list[dict[str, Any]]) -> dict[str, Any]:
    """Re-run the HARNESS's predict_location_v2 (k = 600) on a seeded sample and compare its box_v2 months to ours, exactly."""
    rng = np.random.default_rng(20261015)
    ok_i = [i for i, r in enumerate(res) if "oil" in r.get("streams", {})]
    pick = sorted(rng.choice(ok_i, size=min(N_EQUIV, len(ok_i)), replace=False).tolist())
    an._init({"pool": P["pool"], "pool2": P["pool2"], "cfg": di_config.load(), "k": pr.N_MONTHS, "cutoff": P["cutoff"], "bench": P["label"]})
    worst = 0.0
    for i in pick:
        h = an.predict_location_v2(locs[i])
        for s in pr.STREAMS:
            ours = res[i]["streams"].get(s, {}).get("months_raw")
            theirs = h.get("box_v2", {}).get(s)
            if ours is None or theirs is None:
                worst = max(worst, 0.0 if ours is None and (theirs is None or not np.isfinite(theirs).any()) else np.inf)
                continue
            worst = max(worst, float(np.nanmax(np.abs(np.asarray(ours) - np.asarray(theirs)) / np.maximum(np.abs(theirs), 1e-9))))
    return {"n": len(pick), "max_rel_diff": worst}


def build_bench(conn: Any, a: argparse.Namespace, u: pd.DataFrame, bench: str, cfg: Any, t0: float) -> dict[str, Any]:
    """One PRODUCTION_BENCHES group: pool, locations, fits, harness equivalence, F(k), haircut (applied), disclosure."""
    P = build_pool(conn, a.workers, a.wells, bench)
    print(f"[{bench}] pool {len(P['pool']['api10'])} wells at cutoff {P['cutoff']} (production through {P['asof']}) ({time.time() - t0:.0f} s)", flush=True)
    locs = locations(u, conn, bench)
    if a.limit:  # smoke only: the identity check refuses to store a limited build
        locs = locs[: a.limit]
    if bench == "BS2_S":  # D101: edge region of each covered BS2_S location vs the extent of record (workup text, no spec change)
        reg = t9.edge_classes(np.array([x["x"] for x in locs]), np.array([x["y"] for x in locs]), P["extent_ft"])
        for x, r, d in zip(locs, reg["region"], reg["edge_dist_mi"], strict=True):
            x["edge_region"], x["edge_dist_mi"] = str(r), float(d)
    res = pr.fit_many(locs, P["pool"], P["pool2"], cfg, a.workers, bench=P["label"])
    print(f"[{bench}] fitted {len(res)} locations ({time.time() - t0:.0f} s)", flush=True)
    eq = equivalence(P, locs, res)
    print(f"[{bench}] equivalence vs predict_location_v2: {eq}", flush=True)
    if not eq["max_rel_diff"] <= 1e-12:
        raise SystemExit(f"[{bench}] box_v2 path is NOT the harness's: {eq}")
    F = calendar_factor(P, a.workers)
    hcut = p9.haircut_for(bench)
    if bench == "WCA":
        cells = pd.concat([pd.read_csv(ACC / "cells_tuning_v2.csv"), pd.read_csv(ACC / "cells_holdout_v2.csv")], ignore_index=True)
        disc = disclosure(cells, hcut)
    else:
        disc = p9.bench_disclosure(bench, hcut)
    apply_haircut_all(res, hcut)
    for x, r in zip(locs, res, strict=True):  # caveat text travels with the row (pud_forecast.flags -> erebor's workup table)
        if x.get("edge_region") in ("south_edge", "other_edge"):
            r["flags"] = list(r["flags"]) + p9.edge_flags([x["edge_region"]])[0]
        if bench == "WCXY_WCA1":
            r["flags"] = list(r["flags"]) + [p9.WCXY_FLAG]
    rec = {"spec": p9.record_variant(bench), "label": P["label"], "extent_id": P["extent_id"], "n_pool": len(P["pool"]["api10"]),
           "n_excluded": P["n_excluded"], "k_areas": P["k_areas"], "haircut": haircut_record(hcut, res), "calendar_factor": F,
           "disclosure": disc, "equivalence": eq, "n_locations": len(locs), "n_forecast": sum("oil" in r.get("streams", {}) for r in res)}
    used = sorted({x["api10"] for r in res for x in r.get("analogs", [])})
    fr = P["cb"]["frame"].set_index("api10")
    keep = [c for c in ("well_name", "operator", "first_production_date", "lateral_ft", "tvd_ft", "mid_lon", "mid_lat") if c in fr.columns]
    meta = fr.loc[[x for x in used if x in fr.index], keep].reset_index()
    act = hp.monthly_matrix(P["cb"]["prod"][P["cb"]["prod"]["api10"].isin(set(used))], used, asof=P["asof"], k=K_F)
    lat = dict(zip(P["pool2"]["api10"], P["pool2"]["lateral"], strict=True))
    actual_kft = {s: {x: np.cumsum(act[s][i]) / (lat[x] / 1000.0) for i, x in enumerate(used)} for s in pr.STREAMS}
    return {"P": {k: P[k] for k in ("last", "cutoff", "asof")}, "record": rec, "locs": locs, "results": res, "meta": meta, "cum": actual_kft}


def cmd_build(a: argparse.Namespace) -> int:
    t0 = time.time()
    code_sha = _git_sha()  # at START: the code that runs, not whatever is checked out when the run ends
    print(f"code {code_sha}; benches {a.benches}; wells {a.wells}", flush=True)
    unknown = [b for b in a.benches if b not in pr.PRODUCTION_BENCHES]
    if unknown:
        raise SystemExit(f"unknown --benches {unknown}; known {sorted(pr.PRODUCTION_BENCHES)}")
    a.out.mkdir(parents=True, exist_ok=True)
    cfg = di_config.load()
    B: dict[str, dict[str, Any]] = {}
    with get_connection() as conn:
        u = pr.universe(conn, a.benches)
        n_in = {b: int(((u.coverage == "covered") & (u.prod_bench == b)).sum()) for b in a.benches}
        print(f"universe {len(u)}; in-extent candidates per group {n_in} ({time.time() - t0:.0f} s)", flush=True)
        for b in a.benches:
            B[b] = build_bench(conn, a, u, b, cfg, t0)
    cut = {b: (x["P"]["cutoff"], x["P"]["asof"]) for b, x in B.items()}
    if len(set(cut.values())) != 1:
        raise SystemExit(f"groups built at different cutoffs: {cut}")
    first = B[a.benches[0]]
    by_bench = {b: x["record"] for b, x in B.items()}
    r0 = by_bench[a.benches[0]]
    run = {"built_at": dt.datetime.now(tz=dt.UTC).isoformat(timespec="seconds"), "code_sha": code_sha, "engine_sha": boxfit_sha(),
           "dealintake_config": int(cfg.raw.get("config_version")), "report_version": sorted(set(u["report_version"])), "wells_dir": str(a.wells),
           "data_through": first["P"]["asof"], "cutoff": first["P"]["cutoff"], "k_areas": r0["k_areas"], "n_pool": r0["n_pool"], "n_excluded": r0["n_excluded"],
           # top level = the first group's (WCA) keys, what erebor reads; every group under by_bench (D103)
           "haircut": r0["haircut"], "calendar_factor": r0["calendar_factor"], "disclosure": r0["disclosure"], "equivalence": r0["equivalence"],
           "benches": list(a.benches), "by_bench": by_bench}
    locs = [x for b in a.benches for x in B[b]["locs"]]
    res = [r for b in a.benches for r in B[b]["results"]]
    meta = pd.concat([B[b]["meta"] for b in a.benches], ignore_index=True).drop_duplicates("api10").reset_index(drop=True)
    actual_kft = {s: {k: v for b in a.benches for k, v in B[b]["cum"][s].items()} for s in pr.STREAMS}
    with open(a.out / "run.pkl", "wb") as fh:
        pickle.dump({"run": run, "universe": u, "locs": locs, "results": res, "analog_meta": meta, "analog_cum_kft": actual_kft}, fh)
    for b in a.benches:
        print(f"[{b}] covered with forecast {by_bench[b]['n_forecast']} / {by_bench[b]['n_locations']} (in-extent {n_in[b]})", flush=True)
    print(f"wrote {a.out / 'run.pkl'} ({time.time() - t0:.0f} s)", flush=True)
    return 0


def apply_haircut_all(res: list[dict[str, Any]], hcut: dict[str, Any] | None) -> None:
    """D92: every covered stream's months = months_raw x the C1 rate factor fitted to the D62 table; the fit lands in params.
    hcut None = no haircut (D97, WCXY): months = months_raw, stated in params."""
    for r in res:
        for s, st in r.get("streams", {}).items():
            if hcut is None:
                st["months"], info = np.array(st["months_raw"], float), {"method": p9.HAIRCUT_METHOD_NONE, "eur_factor": 1.0}
            else:
                st["months"], info = pr.apply_haircut_c1(st["months_raw"], {k: hcut[s][k] for k in pr.HORIZONS})
            st["params"] = {**st["params"], "haircut": info}
            st["eur_raw"], st["eur"] = float(np.sum(st["months_raw"])), float(np.sum(st["months"]))


def haircut_record(hcut: dict[str, Any] | None, res: list[dict[str, Any]]) -> dict[str, Any]:
    """forecast_run.haircut: the D62 factor table (the targets) + the D92 method and, per stream, the realised cumulative factor at
    each horizon and the tail factor (median and P10-P90 across locations; P10 = the high value). hcut None (D97): factors 1.0."""
    if hcut is None:
        return {"method": p9.HAIRCUT_METHOD_NONE,
                **{s: {k: {"factor": 1.0, "bias": None, "n_packages": 0, "n_cells": 0, "cutoffs": [], "realised_median": 1.0,
                           "realised_p10_p90": [1.0, 1.0]} for k in pr.HORIZONS} | {"tail_factor_median": 1.0, "eur_factor_median": 1.0}
                   for s in pr.STREAMS}}
    out: dict[str, Any] = {"method": pr.HAIRCUT_METHOD}
    for s in pr.STREAMS:
        infos = [r["streams"][s]["params"]["haircut"] for r in res if s in r.get("streams", {})]
        out[s] = {k: dict(hcut[s][k]) for k in pr.HORIZONS}
        for k in pr.HORIZONS:
            x = np.array([i["realised"][str(k)] for i in infos])
            out[s][k]["realised_median"] = float(np.median(x))
            out[s][k]["realised_p10_p90"] = [float(np.percentile(x, 90)), float(np.percentile(x, 10))]
        t = np.array([i["g_tail"] for i in infos])
        out[s]["tail_factor_median"] = float(np.median(t))
        out[s]["eur_factor_median"] = float(np.median([i["eur_factor"] for i in infos]))
    return out


def cmd_rehaircut(a: argparse.Namespace) -> int:
    """Re-apply the CURRENT haircut to an existing build's raw months (same pool, fits, analogs, F(k), disclosure); the new artifact
    carries the current code SHA and records the build it came from. Used for D92 on record run 6's build."""
    code_sha = _git_sha()
    A = _load(a.src)
    run, res = A["run"], A["results"]
    tab = {s: {k: {kk: vv for kk, vv in run["haircut"][s][k].items() if kk in ("factor", "bias", "n_packages", "n_cells", "cutoffs")}
               for k in pr.HORIZONS} for s in pr.STREAMS}
    apply_haircut_all(res, tab)
    run["built_from"] = {"artifact": str(a.src), "code_sha": run["code_sha"], "built_at": run["built_at"]}
    run["code_sha"] = code_sha
    run["built_at"] = dt.datetime.now(tz=dt.UTC).isoformat(timespec="seconds")
    run["haircut"] = haircut_record(tab, res)
    a.out.mkdir(parents=True, exist_ok=True)
    with open(a.out / "run.pkl", "wb") as fh:
        pickle.dump(A, fh)
    h = run["haircut"]
    for s in pr.STREAMS:
        print(f"{s}: target {[round(h[s][k]['factor'], 3) for k in pr.HORIZONS]} realised median {[round(h[s][k]['realised_median'], 3) for k in pr.HORIZONS]} "
              f"tail {h[s]['tail_factor_median']:.3f} eur factor {h[s]['eur_factor_median']:.3f}")
    print(f"rehaircut {a.src} (built {run['built_from']['code_sha'][:7]}) -> {a.out / 'run.pkl'} at {code_sha[:7]}")
    return 0


# ----------------------------------------------------------------------------
# store
# ----------------------------------------------------------------------------


def _load(out: Path) -> dict[str, Any]:
    with open(out / "run.pkl", "rb") as fh:
        return pickle.load(fh)


def _jsonable(x: Any) -> Any:
    return json.loads(json.dumps(x, default=lambda v: v.isoformat() if hasattr(v, "isoformat") else float(v)))


def cmd_store(a: argparse.Namespace) -> int:
    t0 = time.time()
    A = _load(a.out)
    run, u, locs, res = A["run"], A["universe"], A["locs"], A["results"]
    if a.record and run["code_sha"].endswith("-dirty"):
        raise SystemExit(f"refusing --record: the run was built from uncommitted code ({run['code_sha']})")
    if len(run["report_version"]) != 1:
        raise SystemExit(f"universe spans several vintages {run['report_version']}")
    rv = run["report_version"][0]
    by_stick = {loc["stick_id"]: (loc, r) for loc, r in zip(locs, res, strict=True)}
    conn = get_connection()
    try:
        with conn.cursor() as cur:
            q = cur.execute
            print(f"target {q('select inet_server_addr(), inet_server_port(), current_database()').fetchone()}", flush=True)
            later = q("SELECT count(*) FROM box.location_source WHERE report_version > %s", (rv,)).fetchone()[0]
            if later:
                raise SystemExit(f"box.location already holds vintages after {rv}: refusing to store an older vintage")
            have = dict(q("SELECT stick_id, location_id FROM box.location_source WHERE report_version = %s", (rv,)).fetchall())
            prev_v = q("SELECT max(report_version) FROM box.location_source WHERE report_version < %s", (rv,)).fetchone()[0]
            new = u[~u["stick_id"].isin(have)]
            n_carried = 0
            if len(new) and prev_v is not None:
                # D73: carry locations forward from the most recent earlier vintage; the rest of `new` become 'new' locations
                prev = q("SELECT location_id, basin, formation_blueox, extensions.ST_AsText(geom) FROM box.location WHERE last_seen_vintage = %s",
                         (prev_v,)).fetchall()
                pl = pr.project_ft([w for *_, w in prev])
                nl = pr.project_ft(list(new["wkt"]))
                xw = pr.crosswalk([(int(p[0]), p[1], p[2], g) for p, g in zip(prev, pl, strict=True)],
                                  [(int(r.stick_id), r.basin, r.formation_blueox, g) for r, g in zip(new.itertuples(), nl, strict=True)])
                mv = new[new["stick_id"].astype(int).isin(xw)]
                cur.executemany("UPDATE box.location SET geom = extensions.ST_GeomFromText(%s, 4326), lateral_ft = %s, last_seen_vintage = %s WHERE location_id = %s",
                                [(r.wkt, float(r.ll_ft) if np.isfinite(r.ll_ft) else float(r.stick_ft), rv, xw[int(r.stick_id)][0]) for r in mv.itertuples()])
                cur.executemany("INSERT INTO box.location_source (location_id, report_version, stick_id, match_method, match_overlap, pad_name) "
                                "VALUES (%s, %s, %s, 'overlap', %s, %s)",
                                [(xw[int(r.stick_id)][0], rv, int(r.stick_id), xw[int(r.stick_id)][1], r.pad_name) for r in mv.itertuples()])
                have.update({int(s): xw[int(s)][0] for s in mv["stick_id"]})
                n_carried = len(mv)
                new = new[~new["stick_id"].astype(int).isin(xw)]
                print(f"crosswalk {prev_v} -> {rv}: {n_carried} carried of {len(prev)} previous locations; {len(new)} new", flush=True)
            method = "seed" if prev_v is None else "new"
            if len(new):
                cur.executemany(
                    "INSERT INTO box.location (basin, formation_blueox, geom, lateral_ft, first_seen_vintage, last_seen_vintage) "
                    "VALUES (%s, %s, extensions.ST_GeomFromText(%s, 4326), %s, %s, %s) RETURNING location_id",
                    [(r.basin, r.formation_blueox, r.wkt, float(r.ll_ft) if np.isfinite(r.ll_ft) else float(r.stick_ft), rv, rv) for r in new.itertuples()],
                    returning=True)
                ids = []
                while True:
                    ids.append(cur.fetchone()[0])
                    if not cur.nextset():
                        break
                cur.executemany("INSERT INTO box.location_source (location_id, report_version, stick_id, match_method, pad_name) VALUES (%s, %s, %s, %s, %s)",
                                [(lid, rv, int(r.stick_id), method, r.pad_name) for lid, r in zip(ids, new.itertuples(), strict=True)])
                have.update(dict(zip(new["stick_id"].astype(int), ids, strict=True)))
            print(f"locations: {len(have)} ({len(new)} {method}, {n_carried} carried) ({time.time() - t0:.0f} s)", flush=True)
            bb = run.get("by_bench")
            jb = {col: (Jsonb(_jsonable({**run[col], "by_bench": {b: x[col] for b, x in bb.items()}})) if bb else Jsonb(_jsonable(run[col])))
                  for col in ("haircut", "calendar_factor", "disclosure")}
            rid = q("INSERT INTO box.forecast_run (spec, code_sha, engine_sha, dealintake_config, report_version, data_through, haircut, calendar_factor, "
                    "disclosure, extents, counts, notes) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s) RETURNING run_id",
                    (pr.SPEC, run["code_sha"], run["engine_sha"], run["dealintake_config"], rv, run["data_through"],
                     jb["haircut"], jb["calendar_factor"], jb["disclosure"],
                     Jsonb(_jsonable({str(k): int(v) for k, v in u.groupby("bench")["extent_id"].first().dropna().items()})),
                     Jsonb({}), run_notes(run))).fetchone()[0]
            pf, st_rows, an_rows, months = [], [], [], []
            for r in u.itertuples():
                lid = have[int(r.stick_id)]
                cov, loc, fit = r.coverage, None, None
                if cov == "covered":
                    loc, fit = by_stick[int(r.stick_id)]
                    if "oil" not in fit.get("streams", {}):
                        cov = "not_covered_no_analogs"
                srch = loc is not None and fit is not None and (cov == "covered" or fit["n_analogs"] < 3)
                pf.append((rid, lid, int(r.stick_id), r.basin, r.bench, r.formation_blueox, r.recon_status, cov,
                           None if r.inside_extent is None else bool(r.inside_extent), None if pd.isna(r.extent_id) else int(r.extent_id), r.pad_name,
                           float(r.ll_ft) if np.isfinite(r.ll_ft) else None,
                           loc["lateral_ft"] if cov == "covered" else None, loc["planned_spacing_ft"] if cov == "covered" else None,
                           loc["spacing_source"] if cov == "covered" else None,
                           fit["search_mode"] if srch else None, fit["radius_mi"] if srch else None,
                           pr.radius_class(fit["radius_mi"]) if srch else None, fit["n_analogs"] if srch else None,
                           fit["short_lateral"] if cov == "covered" else None,
                           (list(fit["flags"]) + pr.bound_flags(fit.get("streams", {}), loc.get("near_pdp_ft") if loc else None)) if fit else [],
                           f"pad:{r.pad_name}" if cov == "covered" and r.pad_name else None))
                if cov != "covered":
                    continue
                for s, st in fit["streams"].items():
                    L = loc["lateral_ft"] / 1000.0
                    st_rows.append((rid, lid, s, Jsonb(st["params"]), fit["lateral_mult"], st["eur"] / st["eur_raw"], st["eur_raw"], st["eur"], st["eur"] / L,
                                    float(np.sum(st["months"][:12])), float(np.sum(st["months"][:24]))))
                    months.append((lid, s, st["months"]))
                for x in fit["analogs"]:
                    an_rows.append((rid, lid, x["api10"], x["rank"], x["dist_ft"], x["lateral_ft"], x["first_production"], bool(x["transfer"])))
            with cur.copy("COPY box.pud_forecast (run_id, location_id, stick_id, basin, bench, formation_blueox, recon_status, coverage, inside_extent, "
                          "extent_id, pad_name, lateral_ft, completed_lateral_ft, planned_spacing_ft, spacing_source, search_mode, radius_mi, radius_class, "
                          "n_analogs, short_lateral, flags, workup_ref) FROM STDIN") as cp:
                for row in pf:
                    cp.write_row(row)
            cur.executemany("INSERT INTO box.pud_forecast_stream (run_id, location_id, stream, params, lateral_mult, eur_haircut, eur_raw, eur, eur_per_kft, cum12, cum24) "
                            "VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)", st_rows)
            with cur.copy("COPY box.pud_forecast_month (run_id, location_id, stream, month_no, volume) FROM STDIN") as cp:
                for lid, s, v in months:
                    for m, x in enumerate(v, start=1):
                        cp.write_row((rid, lid, s, m, float(x)))
            with cur.copy("COPY box.location_analog (run_id, location_id, api10, rank, dist_ft, lateral_ft, first_production, transfer) FROM STDIN") as cp:
                for row in an_rows:
                    cp.write_row(row)
            for t in ("location", "location_source", "pud_forecast", "pud_forecast_stream", "pud_forecast_month", "location_analog"):
                q(f"ANALYZE box.{t}")  # fresh stats before the identity queries (bulk COPY leaves them stale)
            print(f"rows written + analyzed ({time.time() - t0:.0f} s); checking identity", flush=True)
            fails = identity(q, rid, u)
            counts = dict(q("SELECT coverage, count(*) FROM box.pud_forecast WHERE run_id = %s GROUP BY 1", (rid,)).fetchall())
            q("UPDATE box.forecast_run SET counts = %s WHERE run_id = %s", (Jsonb(counts), rid))
            if fails:
                conn.rollback()
                raise SystemExit(f"identity FAILED, rolled back: {fails}")
            if a.record:
                q("UPDATE box.forecast_run SET is_record = false, superseded_by = %s WHERE is_record", (rid,))
                q("UPDATE box.forecast_run SET is_record = true WHERE run_id = %s", (rid,))
        conn.commit()
    finally:
        conn.close()
    print(f"stored run_id {rid}{' as RECORD' if a.record else ''}: {counts} ({time.time() - t0:.0f} s)", flush=True)
    return 0


def run_notes(run: dict[str, Any]) -> str:
    bb = run.get("by_bench")
    if bb:  # step 9c: one clause per group (D103: run-level spec box_v2_wf; WCXY raw box_v2 per D97)
        per = "; ".join(f"{b}: {x['spec']}" + (" on its own D102 haircut" if b == "BS2_S" else " x D62 haircut" if x["spec"] == "box_v2_wf" else
                                                " raw, no haircut (D97)") for b, x in bb.items())
        return (f"covers {', '.join(bb)} ({per}); haircuts applied by the D92 C1 rate shape; uptime-free volumes; F(k) per group published "
                "not applied (D63); no water (D72); no economics; per-group haircut / F(k) / disclosure under by_bench")
    return (("uptime-free volumes x D62 haircut factors applied by the D92 C1 rate shape" if "method" in run["haircut"]
             else "uptime-free volumes x D62 haircut")
            + "; F(k) published not applied (D63); no water (D72); no economics"
            + (f"; re-haircut of build {run['built_from']['code_sha'][:7]}" if "built_from" in run else ""))


def identity(q: Any, rid: int, u: pd.DataFrame) -> list[str]:
    fails = []

    def chk(ok: bool, msg: str) -> None:
        print(f"    {'ok  ' if ok else 'FAIL'} {msg}", flush=True)
        if not ok:
            fails.append(msg)

    n = q("SELECT count(*) FROM box.pud_forecast WHERE run_id = %s", (rid,)).fetchone()[0]
    chk(n == len(u), f"pud_forecast rows {n} = universe {len(u)}")
    # per coverage group (step 9c): covered + no_analogs = that group's in-extent universe, exactly
    got = q("SELECT basin, bench, formation_blueox, coverage, count(*) FROM box.pud_forecast WHERE run_id = %s "
            "AND coverage IN ('covered', 'not_covered_no_analogs') GROUP BY 1, 2, 3, 4", (rid,)).fetchall()
    groups = sorted({g for g in u["prod_bench"].dropna()}) if "prod_bench" in u else ["WCA"]
    for g in groups:
        basin, bench, forms = pr.PRODUCTION_BENCHES[g]
        exp_g = int(((u.coverage == "covered") & (u["prod_bench"] == g)).sum()) if "prod_bench" in u else int((u.coverage == "covered").sum())
        cg = sum(c for b_, be, f, cv, c in got if b_ == basin and be == bench and f in forms and cv == "covered")
        ng = sum(c for b_, be, f, cv, c in got if b_ == basin and be == bench and f in forms and cv == "not_covered_no_analogs")
        chk(cg + ng == exp_g, f"[{g}] covered {cg} + no_analogs {ng} = in-extent {'/'.join(sorted(forms))} universe {exp_g}")
    exp_cov = int(((u.coverage == "covered")).sum())
    cov = q("SELECT count(*) FROM box.pud_forecast WHERE run_id = %s AND coverage = 'covered'", (rid,)).fetchone()[0]
    noa = q("SELECT count(*) FROM box.pud_forecast WHERE run_id = %s AND coverage = 'not_covered_no_analogs'", (rid,)).fetchone()[0]
    chk(cov + noa == exp_cov, f"covered {cov} + no_analogs {noa} = in-extent universe of every covered group {exp_cov}")
    print(f"    note no_analogs rows = {noa} (D74: reported, never dropped; covered falls short of the universe by this many)", flush=True)
    so = q("SELECT count(*) FROM box.pud_forecast_stream WHERE run_id = %s AND stream = 'oil'", (rid,)).fetchone()[0]
    chk(so == cov, f"oil stream rows {so} = covered {cov}")
    sg = q("SELECT count(*) FROM box.pud_forecast_stream WHERE run_id = %s AND stream = 'gas'", (rid,)).fetchone()[0]
    chk(sg == cov, f"gas stream rows {sg} = covered {cov}")
    # one grouped pass over this run's months (MATERIALIZED: aggregated once, then hash-joined — a nested loop that re-aggregated
    # per stream row ran 37 min on 4.6 M month rows in the 7c container rehearsal)
    grp, bad = q("""WITH m AS MATERIALIZED (
                        SELECT location_id, stream, count(*) AS n, sum(volume) AS v FROM box.pud_forecast_month WHERE run_id = %s GROUP BY 1, 2)
                    SELECT count(*), count(*) FILTER (WHERE m.n <> 600 OR abs(m.v - s.eur) > 1e-3 * s.eur)
                    FROM m JOIN box.pud_forecast_stream s ON s.run_id = %s AND s.location_id = m.location_id AND s.stream = m.stream""",
                 (rid, rid)).fetchone()
    chk(grp == so + sg and bad == 0, f"every stream has 600 months summing to its eur within 0.1 % ({grp} stream groups, {bad} off)")
    na = q("SELECT min(c), max(c) FROM (SELECT count(*) c FROM box.location_analog WHERE run_id = %s GROUP BY location_id) x", (rid,)).fetchone()
    chk(na[0] is not None and na[0] >= 3, f"every covered location has >= 3 named analogs (min {na[0]}, max {na[1]})")
    nl = q("SELECT count(DISTINCT location_id) FROM box.location_analog WHERE run_id = %s", (rid,)).fetchone()[0]
    chk(nl == cov, f"analog rows cover all {cov} covered locations ({nl})")
    return fails


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    for name in ("build", "annotate", "store", "render", "rehaircut", "radius"):
        p = sub.add_parser(name)
        p.add_argument("--out", type=Path, default=Path("runs") / "box7c")
        p.add_argument("--workers", type=int, default=7)
        p.add_argument("--record", action="store_true")
        p.add_argument("--docs", type=Path, default=Path("docs") / "box" / "step7c-2026-10-15")
        p.add_argument("--wells", type=Path, default=WELLS, help="analog-pool well set (gate-1 wells_final_*.csv dir)")
        p.add_argument("--limit", type=int, default=0, help="build: cap locations per group (smoke test only; never store)")
        p.add_argument("--benches", type=lambda v: [x.strip() for x in v.split(",") if x.strip()], default=["WCA"],
                       help="PRODUCTION_BENCHES groups, comma-separated, WCA first (step 9c: WCA,BS2_S,WCXY_WCA1); default WCA = runs 4-7")
        if name == "rehaircut":
            p.add_argument("--from", dest="src", type=Path, required=True, help="existing build artifact dir (run.pkl)")
        if name == "radius":
            p.add_argument("--views", type=Path, required=True, help="9a tuning views dir (view_*.csv.gz)")
            p.add_argument("--bench", required=True, help="BENCH_SPECS key (BS2_S | WCXY_WCA1)")
    a = ap.parse_args(argv)
    if a.cmd == "radius":
        views = {f.name: pd.read_csv(f, dtype={"api10": str, "package": str}) for f in sorted(a.views.glob("view_tuning_*.csv.gz"))}
        t = p9.radius_ranges_from_views(views, p9.record_variant(a.bench))
        a.docs.mkdir(parents=True, exist_ok=True)
        t.to_csv(a.docs / f"spread_by_radius_{a.bench}.csv", index=False)
        print(f"{len(views)} views -> {a.docs / f'spread_by_radius_{a.bench}.csv'}\n{t.to_string(index=False)}")
        return 0
    if a.cmd == "build":
        return cmd_build(a)
    if a.cmd == "store":
        return cmd_store(a)
    if a.cmd == "annotate":
        return cmd_annotate(a)
    if a.cmd == "rehaircut":
        return cmd_rehaircut(a)
    from box import production_pages as pp

    return pp.render(_load(a.out), a.out, a.docs)


if __name__ == "__main__":
    sys.exit(main())
