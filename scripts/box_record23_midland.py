"""BOX step 23 — the Midland BASE run: the step-21 method on the production path (read-only build; store on its own go).

    python -m scripts.box_record23_midland build [--out runs/step23/midland_base] [--workers 14] [--groups MID_WCA_1,...] [--limit N]
    python -m scripts.box_record23_midland store [--out runs/step23/midland_base]      !! writes; the DB_* env picks the target

build: per MID_ group (box/production.PRODUCTION_BENCHES, D128 one pool + one extent each) the analog pool the 21b harness scored
(box/step21.POOL_DIR, the frozen pool-midland-2026-10-31 sets, exclusions.csv applied, measured spacing D119) at the production
cutoff, then every drillable in-extent stick (D145: conflict sticks are classed not_covered_conflict and never fitted) fitted with
the step-21 rules (box/step21.RULES: r2 selection, translate 5,000 ft .. inf, Cui Midland panel / Delaware panel when longer than the
cohort, D148; Df 0.06, D132). Equivalence: a seeded sample re-predicted by the HARNESS (box/analog.predict_location_v2, variant
mid_r2) must match to 1e-12. F(k) calibrated as the harness does and published, not applied (D63); the build REFUSES if the F(k)
training sample holds a well first producing in 2026 (21d stays blind). Haircut: WCA_1 oil x its D102 table (D151 (2)) by the D92
rate shape and the 9c guard (D106); every other stream raw. Disclosure, flags and spec label from the step-23 evidence pack
(scripts/box_record23 pack). The proximity layer is NOT here: the record is derived from this base run (scripts/box_record23 store).

store: box_pud_run's store (locations, run, rows, identities, ONE transaction) with --record forbidden: the base run is never a record.
"""

from __future__ import annotations

import argparse
import dataclasses
import datetime as dt
import hashlib
import json
import pickle
import sys
import time
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from box import acceptance as ac
from box import analog as an
from box import production as pr
from box import record23 as rc
from box import step16 as s16
from box import step21 as st21
from dealintake import config as di_config
from etl.db import get_connection
from scripts import box_pud_run as pud
from scripts.box_tc_curves import boxfit_sha

GROUPS: tuple[str, ...] = tuple(st21.GROUPS)
BLIND_FROM = dt.date(2026, 1, 1)  # 21d's cohort starts here: never in an F(k) training sample


def load_pack(path: Path) -> tuple[dict[str, Any], str]:
    raw = path.read_bytes().replace(b"\r\n", b"\n")
    sha = hashlib.sha256(raw).hexdigest()
    want = path.with_suffix(".sha256").read_text(encoding="utf-8").strip()
    if sha != want:
        raise SystemExit(f"{path}: sha256 {sha} != committed {want}")
    return json.loads(raw.decode("utf-8")), sha


def haircut_of(ev: dict[str, Any]) -> dict[str, Any] | None:
    h = ev.get("haircut")
    if not h:
        return None
    return {s: (None if t is None else {int(k): {"factor": float(v["factor"])} for k, v in t.items()}) for s, t in h.items()}


def method_none(group: str, tier: str) -> str:
    return f"none (D151 {tier}: no walk-forward haircut; months = the uptime-free analog P50 x lateral)"


def flags(group: str, disc: dict[str, Any]) -> list[str]:
    o = disc["hindcast_bias"]["oil"]["12"]
    t = disc["thin_control"]
    b, tc24 = o.get("disclosed_bias"), t.get("oil_cum24_bias")
    return [f"BOX step 23 ({disc['tier']}) {group}: tuning oil cum-12 {b:+.1%} ({o['disclosed_basis']})" if b is not None else f"BOX step 23 {group}",
            (f"thin-control caveat: where < 3 producers lie within 3 mi, tuning oil ran {tc24:+.1%} at cum-24 ({t['oil_cum24_wells']} packages); "
             "forecast NOT adjusted") if tc24 is not None else "thin-control caveat: too few packages to state",
            disc["latest_vintage_text"]]


def calendar_factor(P: dict[str, Any], workers: int) -> dict[str, Any]:
    """box_pud_run.calendar_factor with the step-21 harness variant (mid_r2) instead of r2; refuses a 2026 well in the sample."""
    trn, t_act, ut = P["trn"], P["t_act"], P["ut"]
    xy = np.column_stack(pud.br.dfr._xy(trn["mid_lon"], trn["mid_lat"]))
    rng = np.random.default_rng(ac.SEED)
    ti = np.sort(rng.choice(len(trn), size=min(ac.F_SAMPLE, len(trn)), replace=False))
    sub = trn.iloc[ti].reset_index(drop=True)
    fp = pd.to_datetime(sub["first_production_date"]).dt.date
    if (fp >= BLIND_FROM).any():
        raise SystemExit(f"F(k) sample holds {int((fp >= BLIND_FROM).sum())} wells first producing >= {BLIND_FROM}: 21d must stay blind")
    locs = [{"api10": r.api10, "x": xy[ti][i, 0], "y": xy[ti][i, 1], "lateral_ft": float(r.lateral_ft),
             "lateral_eff": an.completed_lateral(r.api10, float(r.lateral_ft), ut), "spacing_ft": r.spacing_ft,
             "fp_max": pd.Timestamp(r.first_production_date).date()} for i, r in enumerate(sub.itertuples())]
    pt = an.predict_many_v2(locs, P["pool"], P["pool2"], P["cutoff"], pud.K_F, workers, bench=P["label"],
                            extra_pools={s16.MEASURED: P["pool2"]}, variants16=st21.HARNESS_VARIANTS, basin=P["basin"])
    mt = an.monthly_arrays_v2(pt, pud.K_F, (*an.VARIANTS_V2, st21.RAW))
    out: dict[str, Any] = {"variant": st21.RAW, "sample_max_first_production": str(max(fp))}
    for s in pr.STREAMS:
        F, n = pud.hc.calendar_factor_curve(t_act[s][ti], mt[st21.RAW][s])
        out[s] = {"F": [float(x) for x in F], "n_wells": [int(x) for x in n]}
    return out


def equivalence(P: dict[str, Any], locs: list[dict[str, Any]], res: list[dict[str, Any]]) -> dict[str, Any]:
    """The HARNESS's predict_location_v2 (variant mid_r2, k = 600) on a seeded sample vs the production months, exactly."""
    rng = np.random.default_rng(20261015)
    ok_i = [i for i, r in enumerate(res) if "oil" in r.get("streams", {})]
    pick = sorted(rng.choice(ok_i, size=min(pud.N_EQUIV, len(ok_i)), replace=False).tolist()) if ok_i else []
    state: dict[str, Any] = {"pool": P["pool"], "pool2": P["pool2"], "cfg": di_config.load(), "k": pr.N_MONTHS, "cutoff": P["cutoff"],
                             "bench": P["label"], "basin": P["basin"], s16.MEASURED: P["pool2"], "variants16": st21.HARNESS_VARIANTS}
    an._init(state)
    worst = 0.0
    for i in pick:
        h = an.predict_location_v2(locs[i])
        for s in pr.STREAMS:
            ours, theirs = res[i]["streams"].get(s, {}).get("months_raw"), h.get(st21.RAW, {}).get(s)
            if ours is None or theirs is None:
                worst = max(worst, 0.0 if ours is None and (theirs is None or not np.isfinite(theirs).any()) else np.inf)
                continue
            worst = max(worst, float(np.nanmax(np.abs(np.asarray(ours) - np.asarray(theirs)) / np.maximum(np.abs(theirs), 1e-9))))
    return {"n": len(pick), "max_rel_diff": worst, "variant": st21.RAW}


def fit_group(conn: Any, a: argparse.Namespace, u: pd.DataFrame, group: str, cfg: Any, t0: float) -> dict[str, Any]:
    """The cached half: pool, locations, raw fits, equivalence, F(k), analog meta. Nothing here reads the evidence pack."""
    P = pud.build_pool_analog(conn, a.workers, st21.POOL_DIR, group, measured=True, last=a.data_through)
    print(f"[{group}] pool {len(P['pool']['api10'])} wells, cutoff {P['cutoff']} (through {P['asof']}) ({time.time() - t0:.0f} s)", flush=True)
    locs = pud.locations(u, conn, group)
    if a.limit:
        locs = locs[: a.limit]
    res = pr.fit_many(locs, P["pool"], P["pool2"], cfg, a.workers, bench=P["label"], rules=st21.RULES, basin=P["basin"])
    eq = equivalence(P, locs, res)
    print(f"[{group}] fitted {len(res)}; equivalence {eq} ({time.time() - t0:.0f} s)", flush=True)
    if not eq["max_rel_diff"] <= 1e-12:
        raise SystemExit(f"[{group}] production path is NOT the harness's: {eq}")
    F = calendar_factor(P, a.workers)
    used = sorted({x["api10"] for r in res for x in r.get("analogs", [])})
    fr = P["cb"]["frame"].set_index("api10")
    keep = [c for c in ("well_name", "operator", "first_production_date", "lateral_ft", "tvd_ft", "mid_lon", "mid_lat") if c in fr.columns]
    meta = fr.loc[[x for x in used if x in fr.index], keep].reset_index()
    act = pud.hp.monthly_matrix(P["cb"]["prod"][P["cb"]["prod"]["api10"].isin(set(used))], used, asof=P["asof"], k=pud.K_F)
    lat = dict(zip(P["pool2"]["api10"], P["pool2"]["lateral"], strict=True))
    cum = {s: {x: np.cumsum(act[s][i]) / (lat[x] / 1000.0) for i, x in enumerate(used)} for s in pr.STREAMS}
    fit = {"label": P["label"], "extent_id": P["extent_id"], "n_pool": len(P["pool"]["api10"]), "n_excluded": P["n_excluded"], "k_areas": P["k_areas"],
           "equivalence": eq, "calendar_factor": F}
    return {"P": {k: P[k] for k in ("last", "cutoff", "asof")}, "fit": fit, "locs": locs, "results": res, "meta": meta, "cum": cum}


def finish_group(a: argparse.Namespace, group: str, built: dict[str, Any]) -> dict[str, Any]:
    """The pack half (re-applied on every build, never cached): D102 haircut by the D92 shape + the 9c guard, flags, record entry."""
    import copy

    ev = a.pack["groups"][group]
    tier = ev["tier"]
    hcut = haircut_of(ev)
    if hcut is not None:
        bad = pud.p9r.guard_table({s: t for s, t in hcut.items() if t is not None})
        if bad:
            raise SystemExit(f"[{group}] 9c guard REFUSES the D102 table: {bad}")
    res = copy.deepcopy(built["results"])
    fit = built["fit"]
    mn = method_none(group, tier)
    pud.apply_haircut_all(res, hcut, mn)
    guard: dict[str, Any] = {"applies": hcut is not None, **pud.p9r.GUARD}
    if hcut is not None:
        bad, guard["g48"] = pud.p9r.guard_tail({s: np.array([r["streams"][s]["params"]["haircut"]["g_tail"] for r in res if s in r.get("streams", {})])
                                                for s in pr.STREAMS if hcut.get(s) is not None})
        if bad:
            raise SystemExit(f"[{group}] 9c guard REFUSES the applied haircut: {bad}")
    guard["verdict"] = "pass" if hcut is not None else "not applicable (no haircut)"
    disc = ev["disclosure"]
    fl = flags(group, disc)
    for r in res:
        r["flags"] = list(r["flags"]) + fl
    rec = {"spec": ev["spec"], "tier": tier, "selection": {"decision": "D146-D149", "rules": dataclasses.asdict(st21.RULES) | {"translate_range": [
           st21.RULES.translate_range[0], "inf"]}, "evidence_sha256": a.pack_sha256, "definition_digest": st21.DIGEST},
           "coverage_class": pr.covered_class(group), "guard": guard, "wells_dir": str(st21.POOL_DIR), "label": fit["label"], "extent_id": fit["extent_id"],
           "n_pool": fit["n_pool"], "n_excluded": fit["n_excluded"], "k_areas": fit["k_areas"],
           "haircut": pud.haircut_record(hcut, res, mn), "calendar_factor": fit["calendar_factor"], "disclosure": disc, "equivalence": fit["equivalence"],
           "n_locations": len(built["locs"]), "n_forecast": sum("oil" in r.get("streams", {}) for r in res)}
    return {**built, "record": rec, "results": res}


def cmd_build(a: argparse.Namespace) -> int:
    t0 = time.time()
    code_sha = pud._git_sha()
    a.pack, a.pack_sha256 = load_pack(a.pack_path)
    h = haircut_of(a.pack["groups"]["MID_WCA_1"]) or {}
    got = {k: v["factor"] for k, v in (h.get("oil") or {}).items()}
    want = rc.d102_shipped()
    same = set(got) == set(want) and all(abs(got[k] - want[k]) <= 1e-12 * want[k] for k in want)
    if not same and not a.allow_other_haircut:
        raise SystemExit(f"pack WCA_1 haircut {got} != the haircut of record {rc.d102_shipped()} (D154 (a)); --allow-other-haircut for a sensitivity")
    a.out.mkdir(parents=True, exist_ok=True)
    cfg = di_config.load()
    B: dict[str, dict[str, Any]] = {}
    with get_connection() as conn:
        u = pr.universe(conn, a.groups)
        n_in = {g: int((u.coverage.isin(pr.COVERED) & (u.prod_bench == g)).sum()) for g in a.groups}
        print(f"code {code_sha}; universe {len(u):,} ({u['coverage'].value_counts().to_dict()}); in-extent per group {n_in}", flush=True)
        meta = {"code_key": pud.code_key(), "limit": int(a.limit), "data_through": str(a.data_through),
                "universe_sha256": hashlib.sha256(u.sort_values("stick_id")[["stick_id", "coverage", "prod_bench"]].astype(str).to_csv(index=False)
                                                  .encode("utf-8")).hexdigest()}
        for g in a.groups:
            c = pud.load_bench_cache(a.out, g, meta)
            if c is None:
                c = fit_group(conn, a, u, g, cfg, t0)
                pud.save_bench_cache(a.out, g, meta, c)
            B[g] = finish_group(a, g, c)
    cut = {g: (x["P"]["cutoff"], x["P"]["asof"]) for g, x in B.items()}
    if len(set(cut.values())) != 1:
        raise SystemExit(f"groups built at different cutoffs: {cut}")
    by = {g: x["record"] for g, x in B.items()}
    r0 = by[a.groups[0]]
    first = B[a.groups[0]]
    run = {"built_at": dt.datetime.now(tz=dt.UTC).isoformat(timespec="seconds"), "basin": pr.run_basin(a.groups), "code_sha": code_sha,
           "engine_sha": boxfit_sha(), "dealintake_config": int(cfg.raw.get("config_version")), "report_version": sorted(set(u["report_version"])),
           "wells_dir": str(st21.POOL_DIR), "data_through": first["P"]["asof"], "cutoff": first["P"]["cutoff"], "k_areas": 0,
           "n_pool": r0["n_pool"], "n_excluded": r0["n_excluded"], "haircut": r0["haircut"], "calendar_factor": r0["calendar_factor"],
           "disclosure": {**r0["disclosure"], "method_23_base": rc.method_block() | {"note": "base run: proximity applied by the derived record"}},
           "equivalence": r0["equivalence"], "benches": list(a.groups), "by_bench": by,
           "selection": {"name": "step21_rev8", "decision": "D146-D149", "evidence": str(a.pack_path), "evidence_sha256": a.pack_sha256}}
    with open(a.out / "run.pkl", "wb") as fh:
        pickle.dump({"run": run, "universe": u, "locs": [x for g in a.groups for x in B[g]["locs"]],
                     "results": [r for g in a.groups for r in B[g]["results"]],
                     "analog_meta": pd.concat([B[g]["meta"] for g in a.groups], ignore_index=True).drop_duplicates("api10").reset_index(drop=True),
                     "analog_cum_kft": {s: {k: v for g in a.groups for k, v in B[g]["cum"][s].items()} for s in pr.STREAMS}}, fh)
    summ = {g: {"tier": by[g]["tier"], "spec": by[g]["spec"], "in_extent": n_in[g], "forecast": by[g]["n_forecast"], "equivalence": by[g]["equivalence"],
                "oil_mmbbl": float(sum(r["streams"]["oil"]["eur"] for r in B[g]["results"] if "oil" in r.get("streams", {})) / 1e6),
                "gas_bcf": float(sum(r["streams"]["gas"]["eur"] for r in B[g]["results"] if "gas" in r.get("streams", {})) / 1e6)} for g in a.groups}
    (a.out / "summary.json").write_text(json.dumps({"code_sha": code_sha, "data_through": str(run["data_through"]), "groups": summ}, indent=1, default=str),
                                        encoding="utf-8")
    print(json.dumps(summ, indent=1, default=str))
    print(f"wrote {a.out / 'run.pkl'} ({time.time() - t0:.0f} s)", flush=True)
    return 0


def cmd_store(a: argparse.Namespace) -> int:
    return pud.cmd_store(argparse.Namespace(out=a.out, record=False))


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    b = sub.add_parser("build")
    b.add_argument("--out", type=Path, default=Path("runs") / "step23" / "midland_base")
    b.add_argument("--workers", type=int, default=14)
    b.add_argument("--groups", type=lambda v: [x.strip() for x in v.split(",") if x.strip()], default=list(GROUPS))
    b.add_argument("--limit", type=int, default=0, help="smoke only: cap locations per group (never stored)")
    b.add_argument("--pack-path", type=Path, default=rc.DOCS / "midland_pack_recomputed.json")  # D154 (a)
    b.add_argument("--data-through", type=dt.date.fromisoformat, default=None, help="pin the last full month (default: the live one)")
    b.add_argument("--allow-other-haircut", action="store_true", help="sensitivity only: a pack whose WCA_1 haircut is not D154's")
    s = sub.add_parser("store")
    s.add_argument("--out", type=Path, default=Path("runs") / "step23" / "midland_base")
    a = ap.parse_args(argv)
    return cmd_build(a) if a.cmd == "build" else cmd_store(a)


if __name__ == "__main__":
    sys.exit(main())
