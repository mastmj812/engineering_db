"""BOX step 21c driver: the Midland one-time D52 holdout under the FROZEN pre-registration (revision 8, digest 9780f326, frozen SHA
5ceadc2) and the gate-21b record (D149, GATE_21B.json). Order is enforced:

    python -m scripts.box_step21c runs      [--lanes 3] [--workers 6] [--groups ...]   # §10 harness on the HOLDOUT view
    python -m scripts.box_step21c reproduce                                            # 21b scorer on the 21b runs = 21b docs
    python -m scripts.box_step21c water     [--workers 14]                             # §7 water frames on the holdout views
    python -m scripts.box_step21c judge                                                # the ONE read: D99 + tiers + D102 + D105
    python -m scripts.box_step21c render                                               # re-render the page from judge's files

`runs` writes <main checkout>/runs/step21c/<group>/ through scripts.box_step21c_harness (frozen run() minus the step-16 holdout
guard; Michael 2026-11-02 option A) with --history = the group's 21b tuning cells (box_v2_wf on a holdout reads them; reported
only). A group is run once: a completed run.json is never re-run. Every command re-checks the frozen files against 5ceadc2
(scripts.box_step21b.frozen_check: added files pass, any modified frozen file refuses) and records it; `runs` / `water` refuse
while an etl-nightly is in progress or red. `reproduce` re-runs scripts.box_step21b_score.run_score on <main>/runs/step21b into
runs/step21c/reproduce_docs and requires byte-identity with the committed 21b tables (both frozen sha256 included) before
`judge` will read a holdout number. `judge` refuses if its verdict file exists (read once). Read-only against the warehouse;
nothing stored; the Delaware is not read.
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import pickle
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from box import step21 as st
from box import step21c as s21c
from scripts import box_step21b as b21

GROUPS: tuple[str, ...] = ("MID_WCA_1", "MID_WCB_1", "MID_LSSH", "MID_WCB_2", "MID_JM", "MID_MS", "MID_WCD", "MID_DEAN")  # WCC: no D99 cell
SKIPPED = {"MID_WCC": "no D99 cell (PREREGISTRATION §6: provisional by construction, no holdout scored; GATE_21B.json)"}
DOCS = Path("docs") / "box" / "step21c-2026-11-02"
REPRO_FILES = ("frozen_d99.csv", "frozen_water.csv", "prox_factor_table.csv", "cells.csv", "walk_forward.csv", "guard_d106.csv",
               "expected_holdout.csv", "pooled.csv", "intervals_all.csv", "water_cells.csv", "water_intervals.csv", "summary_table.csv")


def main_checkout() -> Path:
    return Path(b21._git("rev-parse", "--path-format=absolute", "--git-common-dir")).parent


def run_root() -> Path:
    return main_checkout() / "runs" / "step21c"


def tuning_root() -> Path:
    return main_checkout() / "runs" / "step21b"


def htag(group: str) -> str:
    return f"holdout_v2_{group}_analog"


# ----------------------------------------------------------------------------
# runs
# ----------------------------------------------------------------------------


def one(group: str, out: Path, workers: int) -> dict[str, Any]:
    d = out / group
    done = d / "run.json"
    if done.exists() and json.loads(done.read_text(encoding="utf-8")).get("returncode") == 0:
        print(f"{group}: holdout already run, never re-run", flush=True)
        return json.loads(done.read_text(encoding="utf-8"))
    fc, ns = b21.guard(need_idle=True)
    hist = tuning_root() / group / f"cells_tuning_v2_{group}_analog.csv"
    if not hist.exists():
        raise SystemExit(f"{group}: 21b tuning cells missing ({hist})")
    d.mkdir(parents=True, exist_ok=True)
    cmd = [sys.executable, "-W", "ignore", "-m", "scripts.box_step21c_harness", "--fold", "analog", "--bench", group, "--step16",
           "--wells", str(st.POOL_DIR), "--actuals-through", str(b21.ACTUALS_THROUGH), "--out", str(d), "--workers", str(workers),
           "--score-holdout", "--holdout-once", "--history", str(hist)]
    meta: dict[str, Any] = {"group": group, "view": "HOLDOUT", "cmd": cmd, "head": b21.head_sha(), "frozen_sha": b21.FROZEN_SHA,
                            "frozen_check": fc, "run_source_sha256": s21c.RUN_SOURCE_SHA256, "guard_removed": s21c.source_diff(),
                            "nightly_at_start": ns, "definition_digest": st.digest(),
                            "started_utc": dt.datetime.now(dt.UTC).isoformat(timespec="seconds")}
    with open(d / "log.txt", "w", encoding="utf-8") as fh:  # the harness prints its box_v2 holdout cells here: not read unless rc != 0
        rc = subprocess.run(cmd, stdout=fh, stderr=subprocess.STDOUT, env={**os.environ, "PYTHONWARNINGS": "ignore"}, check=False).returncode
    meta.update({"finished_utc": dt.datetime.now(dt.UTC).isoformat(timespec="seconds"), "returncode": rc,
                 "frozen_check_at_end": b21.frozen_check(), "nightly_at_end": b21.nightly_state()})
    (d / "run.json").write_text(json.dumps(meta, indent=2), encoding="utf-8")
    print(f"{group}: rc={rc} {meta['started_utc']} -> {meta['finished_utc']} frozen_identical={meta['frozen_check_at_end']['identical']}", flush=True)
    return meta


def cmd_runs(a: argparse.Namespace) -> int:
    b21.guard(need_idle=True)
    s21c.check_frozen()
    out = run_root()
    out.mkdir(parents=True, exist_ok=True)
    jobs = [g for g in GROUPS if a.groups is None or g in a.groups]
    with ThreadPoolExecutor(max_workers=a.lanes) as ex:
        res = list(ex.map(lambda g: one(g, out, a.workers), jobs))
    return 0 if all(m["returncode"] == 0 for m in res) else 1


# ----------------------------------------------------------------------------
# reproduce: the 21b scorer on the 21b runs must give the committed 21b tables
# ----------------------------------------------------------------------------


def _norm(p: Path) -> bytes:
    return p.read_bytes().replace(b"\r\n", b"\n")


def cmd_reproduce(a: argparse.Namespace) -> int:
    from scripts import box_step21b_score as sc

    fc, _ = b21.guard(need_idle=False)
    s21c.check_frozen()
    out = run_root() / "reproduce_docs"
    res = sc.run_score(tuning_root(), out, list(st.GROUPS), None)
    rows = []
    for f in REPRO_FILES:
        new, old = out / f, s21c.DOCS_21B / f
        same = new.exists() and old.exists() and _norm(new) == _norm(old)
        maxdiff = None
        if not same and new.exists() and old.exists():
            x, y = pd.read_csv(new), pd.read_csv(old)
            num = [c for c in x.columns if c in y.columns and pd.api.types.is_numeric_dtype(x[c]) and pd.api.types.is_numeric_dtype(y[c])]
            maxdiff = float(np.nanmax(np.abs(x[num].to_numpy(float) - y[num].to_numpy(float)))) if len(x) == len(y) and num else None
        rows.append({"file": f, "byte_identical": bool(same), "max_abs_numeric_diff": maxdiff})
    rep = {"built_utc": dt.datetime.now(dt.UTC).isoformat(timespec="seconds"), "head": b21.head_sha(), "frozen_check": fc,
           "frozen_d99_sha256": res["meta"]["frozen_d99_sha256"], "frozen_water_sha256": res["meta"]["frozen_water_sha256"],
           "files": rows, "all_identical": all(r["byte_identical"] for r in rows)}
    (run_root() / "reproduce.json").write_text(json.dumps(rep, indent=2), encoding="utf-8")
    print(pd.DataFrame(rows).to_string())
    print(f"frozen_d99 {rep['frozen_d99_sha256'][:8]}  frozen_water {rep['frozen_water_sha256'][:8]}  all identical: {rep['all_identical']}")
    return 0 if rep["all_identical"] else 1


# ----------------------------------------------------------------------------
# water (§7) on the holdout views
# ----------------------------------------------------------------------------


def cmd_water(a: argparse.Namespace) -> int:
    from etl.db import get_connection
    from scripts import box_step21c_water as cw

    b21.guard(need_idle=True)
    for g in GROUPS:
        _require_run(g)
    with get_connection() as conn:
        cw.run(conn, run_root(), list(GROUPS), a.workers)
    return 0


# ----------------------------------------------------------------------------
# judge: the one read
# ----------------------------------------------------------------------------


def _require_run(g: str) -> dict[str, Any]:
    p = run_root() / g / "run.json"
    if not p.exists():
        raise SystemExit(f"{g}: no holdout run")
    m = json.loads(p.read_text(encoding="utf-8"))
    if m.get("returncode") != 0 or not m["frozen_check"]["identical"] or not m.get("frozen_check_at_end", {}).get("identical"):
        raise SystemExit(f"{g}: holdout run not complete on the frozen files — not a score")
    return m


def load_views(d: Path, group: str, tag: str) -> dict[str, Any]:
    """scripts.box_step21b_score.load_group for any tag: views (cutoff -> frame), observed mid_r2 months, F(k) per cutoff."""
    from box import acceptance as ac
    from box import step21b as sb

    z = np.load(d / "months_mid_r2.npz")
    views, months, fchk = {}, {}, []
    for f in sorted(d.glob(f"view_{tag}_*.csv.gz")):
        y = f.name.split("_")[-1][:4]
        v = pd.read_csv(f, dtype={"api10": str, "package": str})
        c = f"{y}-12-01"
        v["cutoff"] = c
        if f"{y}_api10" not in z.files:
            if len(v):
                raise RuntimeError(f"{group} {y}: scored wells but no observed months")
            continue
        if not np.array_equal(z[f"{y}_api10"].astype(str), v["api10"].to_numpy(str)):
            raise RuntimeError(f"{group} {y}: observed months not in view order")
        months[c] = {s: z[f"{y}_{s}"] for s in ac.STREAMS}
        for s in ac.STREAMS:
            for k in ac.HORIZONS:
                if f"pred_{st.RAW}_{s}{k}" in v and v[f"pred_{st.RAW}_{s}{k}"].notna().any():
                    F, spread = sb.f_from_view(v, months[c][s], s, k)
                    fchk.append({"group": group, "cutoff": c, "stream": s, "horizon": k, "F": F, "max_rel_spread": spread})
        views[c] = v
    return {"views": views, "months": months, "fcheck": pd.DataFrame(fchk),
            "summary": json.loads((d / f"summary_{tag}.json").read_text(encoding="utf-8")),
            "harness_cells": pd.read_csv(d / f"cells_{tag}.csv")}


def cmd_judge(a: argparse.Namespace) -> int:
    from box import acceptance as ac
    from box import holdout9b as h9
    from box import provisional as pv
    from box import rehearse9b as r9
    from box import step21b as sb
    from box import tune15_report as t15
    from scripts import box_step21b_score as sc

    docs = a.docs
    if (docs / "verdicts.json").exists():
        raise SystemExit(f"{docs / 'verdicts.json'} exists: the holdout is read ONCE (use `render` to redraw the page)")
    fc, _ = b21.guard(need_idle=False)
    frozen_chk = s21c.check_frozen()
    rp = json.loads((run_root() / "reproduce.json").read_text(encoding="utf-8")) if (run_root() / "reproduce.json").exists() else {}
    if not rp.get("all_identical"):
        raise SystemExit("run `reproduce` first: the scorer must reproduce 21b's tuning numbers before the holdout is read")
    runs_meta = {g: _require_run(g) for g in GROUPS}
    gt = s21c.gate()
    rdocs = run_root() / "reproduce_docs"
    frozen = pd.read_csv(s21c.DOCS_21B / "frozen_d99.csv")
    frozen_w = pd.read_csv(s21c.DOCS_21B / "frozen_water.csv")
    table = pd.read_csv(rdocs / "prox_factor_table.csv")
    tcells = pd.read_csv(rdocs / "cells.csv")
    twf = pd.read_csv(rdocs / "walk_forward.csv")
    tpooled = pd.read_csv(rdocs / "pooled.csv")
    tfid = pd.read_csv(rdocs / "f_identity.csv")
    exp_h = pd.read_csv(rdocs / "expected_holdout.csv")
    with open(tuning_root() / "prox.pkl", "rb") as fh:
        kc = pickle.load(fh)["kc"]
    docs.mkdir(parents=True, exist_ok=True)

    verdicts: dict[str, Any] = {}
    out: dict[str, list[pd.DataFrame]] = {k: [] for k in ("cells", "pooled_cells", "per_cutoff", "wf_identity", "f_drift", "counts",
                                                          "pooled_variants", "d102", "guard", "disclosure", "vintage", "coverage")}
    guard_rows = []
    for g in GROUPS:
        rec = s21c.record(gt, g)
        h = load_views(run_root() / g, g, htag(g))
        views = h["views"]
        allv = pd.concat(views.values(), ignore_index=True)
        if not allv["package_held_out"].astype(bool).all():
            raise RuntimeError(f"{g}: a holdout view carries a tuning package")
        # F(k) drift vs 21b (the training sample is drawn from the fold, not the view: same data -> same F)
        fd = h["fcheck"].merge(tfid[tfid.group == g][["cutoff", "stream", "horizon", "F"]], on=["cutoff", "stream", "horizon"],
                               how="left", suffixes=("_holdout_run", "_21b"))
        fd["rel_diff"] = fd["F_holdout_run"] / fd["F_21b"] - 1.0
        out["f_drift"].append(fd)
        # §4 factor, frozen table, production's lookup
        ch = sb.child_frame(sb.frames(views), kc, g)
        fac = sb.record_factor(ch, table)
        out["coverage"].append(pd.DataFrame([{"group": g, "holdout wells": len(ch), "with drilled-child config row": int(ch["has_config_row"].sum()),
                                              "multi-parent": int(sp_multi(ch).sum()), "factor < 1": int((fac < 1).sum())}]))
        # §5 treatments (tuning haircuts, D58)
        tc = tcells[tcells.group == g]
        cells_h, log = s21c.holdout_treatments(views, fac.to_dict(), tc, rec)
        out["cells"].append(cells_h.assign(group=g))
        wfi = h9.walk_forward_identity(log, twf[twf.group == g].to_dict("records"), st.PROX)
        out["wf_identity"].append(wfi.assign(group=g))
        v = sb.frames(views)
        # §6 cells + verdict
        counts = s21c.oil_counts(v)
        cells = s21c.judged_cells(counts)
        fg = s21c.frozen_rows(frozen, g, rec["oil"])
        pc, vd = s21c.judge(v, fg, cells)
        e = exp_h[(exp_h.group == g) & (exp_h.role == "record" if fg["role_used"].iloc[0] == "record" else exp_h.treatment == rec["oil"])]
        out["counts"].append(pd.DataFrame([{"group": g, "horizon": k, "holdout_packages_scored": counts[k],
                                            "expected_21b": float(e.loc[e.horizon == k, "expected_holdout_scored"].iloc[0]) if (e.horizon == k).any() else np.nan,
                                            "judged": any(kk == k for _, kk in cells),
                                            "frozen_expected_d99_cell": bool(e.loc[e.horizon == k, "d99_cell"].iloc[0]) if (e.horizon == k).any() else None}
                                           for k in st.HORIZONS_JUDGEABLE]))
        if len(pc):
            out["pooled_cells"].append(pc.assign(group=g, treatment=f"{rec['oil']} oil / {rec['gas']} gas", frozen_role=fg["role_used"].iloc[0]))
        out["per_cutoff"].append(h9.per_cutoff(cells_h, "record", st.HORIZONS_JUDGEABLE).assign(group=g))
        for var in (st.RAW, st.PROX, st.PROX_WF, "record"):
            if any(c.startswith(f"pred_{var}_") for c in v.columns):
                out["pooled_variants"].append(t15.pooled(r9.package_table(v, var)).assign(group=g, variant=var, side="holdout"))
        verdicts[g] = {"record": rec, "frozen_rows": fg["role_used"].iloc[0], "cells": [f"{s} cum-{k}" for s, k in cells],
                       "verdict": vd, "tier": s21c.tier(vd), "gate21b_basis": gt["record_treatment"][g]["basis"],
                       "run": {k: runs_meta[g][k] for k in ("head", "started_utc", "finished_utc", "returncode")},
                       "frozen_identical_start_end": [runs_meta[g]["frozen_check"]["identical"], runs_meta[g]["frozen_check_at_end"]["identical"]]}
        # D105 disclosure lines on the record treatment: tuning, holdout, tuning + holdout (block bootstrap 95 %), by vintage
        tv = sc.load_group(tuning_root(), g)
        tviews = tv["views"]
        tfac = sb.record_factor(sb.child_frame(sb.frames(tviews), kc, g), table)
        sb.add_prox(tviews, tfac.to_dict(), st.PROX)
        sb.walk_forward(sb.score(tviews, [st.RAW, st.PROX]), tviews, st.PROX)
        for view in tviews.values():
            for s in ac.STREAMS:
                for k in ac.HORIZONS:
                    if f"pred_{rec[s]}_{s}{k}" in view:
                        view[f"pred_record_{s}{k}"] = view[f"pred_{rec[s]}_{s}{k}"]
        vt = sb.frames(tviews)
        pk_t, pk_h = pv.package_frame(vt, "record"), pv.package_frame(v, "record")
        pk_b = pd.concat([pk_t.assign(pkg="t:" + pk_t["pkg"]), pk_h.assign(pkg="h:" + pk_h["pkg"])], ignore_index=True)
        for side, pk in (("tuning", pk_t), ("holdout", pk_h), ("tuning + holdout", pk_b)):
            out["disclosure"].append(pv.disclosure(pk, g).assign(side=side))
        out["vintage"].append(pv.by_vintage(pk_b, g))
        # step-23 haircut table (D102) + 9c guard on every group's mid_r2p (applied only where the record carries wf AND validated)
        d102 = s21c.d102_table(tc, cells_h)
        months = {s: np.concatenate([*(m[s] for m in tv["months"].values()), *(m[s] for m in h["months"].values())]) for s in ac.STREAMS}
        gd = s21c.guard_d106(d102, months)
        wf_streams = [s for s in ac.STREAMS if rec[s] == st.PROX_WF]
        out["d102"].append(d102.assign(group=g, applies=d102["stream"].isin(wf_streams) & (s21c.tier(vd) == "validated")))
        for s in ac.STREAMS:
            guard_rows.append({"group": g, "stream": s, "record": rec[s], "refused": gd[s]["refused"], "reasons": "; ".join(gd[s]["reasons"]),
                               "factors 12/24/36/48": " / ".join(f"{gd[s]['factors'][k]:.3f}" for k in sorted(gd[s]["factors"])),
                               "g48_median": (gd[s]["g48"] or {}).get("median"), "g48_share_outside": (gd[s]["g48"] or {}).get("share_outside"),
                               "applies (wf record AND validated)": s in wf_streams and s21c.tier(vd) == "validated"})
        verdicts[g]["haircut_d102"] = {s: ("applies" if s in wf_streams and s21c.tier(vd) == "validated" and not gd[s]["refused"]
                                           else "refused by D106" if s in wf_streams and s21c.tier(vd) == "validated"
                                           else "none (record mid_r2p)" if s not in wf_streams else "none (provisional: raw mid_r2p, D105)")
                                       for s in ac.STREAMS}
        print(f"[judge] {g}: {vd['overall']} ({vd['n_cells']} cells, outside {vd['outside']}) -> {verdicts[g]['tier']}", flush=True)

    # water (§7): judged once on the holdout water frames
    wrows = []
    for g in GROUPS:
        f = run_root() / g / "water_holdout.csv.gz"
        t = pd.read_csv(f, dtype={"api10": str, "package": str}) if f.exists() else pd.DataFrame()
        wj = s21c.water_judge(t, frozen_w, g)
        wrows.append(wj)
        verdicts[g]["water"] = {"holdout_judged": int(wj["judged"].sum()), "consistent": int((wj["consistent"] == True).sum()),
                                "tier": "provisional (tuning cells fail, GATE_21B water; D109)", "water_frame": f.exists()}
    meta = {"built_utc": dt.datetime.now(dt.UTC).isoformat(timespec="seconds"), "head": b21.head_sha(), "frozen_check": fc,
            "frozen_intervals": frozen_chk, "reproduce": {k: rp[k] for k in ("built_utc", "all_identical", "frozen_d99_sha256", "frozen_water_sha256")},
            "definition_digest": st.digest(), "skipped": SKIPPED}
    for name, frames in out.items():
        if frames:
            pd.concat(frames, ignore_index=True).to_csv(docs / f"{name}.csv", index=False)
    pd.DataFrame(guard_rows).to_csv(docs / "guard_d106.csv", index=False)
    pd.concat(wrows, ignore_index=True).to_csv(docs / "water_holdout.csv", index=False)
    tpooled[tpooled.variant.isin([st.RAW, st.PROX, st.PROX_WF, "record"])].to_csv(docs / "pooled_tuning_21b.csv", index=False)
    (docs / "verdicts.json").write_text(json.dumps({"meta": meta, "groups": verdicts}, indent=1, default=str), encoding="utf-8")
    return 0


def sp_multi(ch: pd.DataFrame) -> pd.Series:
    from box import step21_prox as sp

    return sp.is_multi(ch)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    for name in ("runs", "reproduce", "water", "judge", "render"):
        p = sub.add_parser(name)
        p.add_argument("--groups", type=lambda v: [x.strip() for x in v.split(",") if x.strip()], default=None)
        p.add_argument("--docs", type=Path, default=DOCS)
        if name == "runs":
            p.add_argument("--lanes", type=int, default=3)
            p.add_argument("--workers", type=int, default=6)
        if name == "water":
            p.add_argument("--workers", type=int, default=14)
    a = ap.parse_args(argv)
    if a.cmd == "render":
        from scripts import box_step21c_render as rr

        return rr.main(a.docs)
    return {"runs": cmd_runs, "reproduce": cmd_reproduce, "water": cmd_water, "judge": cmd_judge}[a.cmd](a)


if __name__ == "__main__":
    sys.exit(main())
