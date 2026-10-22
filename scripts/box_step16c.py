"""BOX step 16c driver: the pre-registered scoring (docs/box/step16b-2026-10-22/PREREGISTRATION.md), frozen SHA 109f805.

    python -m scripts.box_step16c runs     --out runs/step16c [--lanes 3] [--workers 6] [--groups WCA,BS1_S]
    python -m scripts.box_step16c hindcast --out runs/step16c [--workers 14]                          # §6, provisional groups
    python -m scripts.box_step16c offlocal --out runs/step16c --run runs/box9/run.pkl --pools DIR     # §5 input 3
    python -m scripts.box_step16c score    --out runs/step16c --docs docs/box/step16c-2026-10-22      # §4, §5, §6b, D98 guard

`runs`: one `scripts.box_acceptance --step16 --actuals-through 2026-07-01` per production group on the analog fold with the
group's well set of record (production_run9.wells_dir; the run-10 default docs/box/pool-2026-10-15), plus WCA on the full fold
(as accepted); each writes --out/<group>[_full]/ and a run.json with its SHA and timestamps. `hindcast`: §6 per provisional group
x tuning cutoff. `offlocal`: §5's off-local share on run 10's production PUDs, on the pools `scripts.box_cohort_review pools`
rebuilt at run 10's cutoff. `score`: everything the adoption rule and the validated keep-rule read, plus the D98 identity of each
re-scored record against its cells of record. Read-only against the warehouse. Any command refuses to start when the scored
code (box/ except this step's scoring module, scripts/box_acceptance.py, dealintake/) differs from the frozen SHA.
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import pickle
import subprocess
import sys
from concurrent.futures import ProcessPoolExecutor, ThreadPoolExecutor
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from box import acceptance as ac
from box import production_run9 as p9r
from box import step16 as s16
from box import step16c as c16
from box import tune9a_report as t9

FROZEN_SHA = "109f80540284426fde3c5fa0f44c2788d18e605c"
ACTUALS_THROUGH = dt.date(2026, 7, 1)
RUN10_WELLS = Path("docs") / "box" / "pool-2026-10-15"
# heaviest first so the lanes finish together
ORDER: tuple[tuple[str, str], ...] = (("WCA", "full"), ("WCA", "analog"), ("BS2_S", "analog"), ("WCXY_WCA1", "analog"),
                                       ("BS3_S", "analog"), ("BS3_C", "analog"), ("WCB_1", "analog"), ("BS1_S", "analog"),
                                       ("WCB_2", "analog"), ("WCC", "analog"), ("BS2_C", "analog"), ("AVA_2", "analog"),
                                       ("AVA_1", "analog"), ("AVA_0", "analog"))
# the cells each group's record was scored and stored as (D98 guard); AVA_0/1/2 have none committed
RECORD_CELLS: dict[str, Path] = {"WCA": Path("docs/box/acceptance/cells_tuning_v2.csv"),
                                 "BS2_S": Path("docs/box/step9a-2026-10-16/cells_tuning_BS2_S.csv"),
                                 "WCXY_WCA1": Path("docs/box/step9a-2026-10-16/cells_tuning_WCXY_WCA1.csv"),
                                 **{g: Path(f"docs/box/step15-tuning-2026-10-17/cells_{g}.csv")
                                    for g in ("WCB_1", "WCB_2", "WCC", "BS3_S", "BS3_C", "BS1_S", "BS2_C")}}
OFFLOCAL_VARIANTS: tuple[str, ...] = (s16.BASE, *s16.CANDIDATES, *s16.COMPARISON)


def code_matches_frozen() -> bool:
    d = subprocess.run(["git", "diff", "--quiet", FROZEN_SHA, "--", "box", ":!box/step16c.py", "scripts/box_acceptance.py", "dealintake"],
                       check=False)
    return d.returncode == 0


def head_sha() -> str:
    return subprocess.run(["git", "rev-parse", "HEAD"], capture_output=True, text=True, check=True).stdout.strip()


# ----------------------------------------------------------------------------
# runs
# ----------------------------------------------------------------------------


def one(group: str, fold: str, out: Path, workers: int) -> dict[str, object]:
    name = group if fold == "analog" else f"{group}_{fold}"
    d = out / name
    done = d / "run.json"
    if done.exists() and json.loads(done.read_text(encoding="utf-8")).get("returncode") == 0:
        print(f"{name}: already complete, skipped", flush=True)  # resume after an interruption: finished runs are kept
        return json.loads(done.read_text(encoding="utf-8"))
    d.mkdir(parents=True, exist_ok=True)
    cmd = [sys.executable, "-W", "ignore", "-m", "scripts.box_acceptance", "--bench", group, "--fold", fold, "--step16",
           "--actuals-through", str(ACTUALS_THROUGH), "--wells", str(p9r.wells_dir(group, RUN10_WELLS)), "--out", str(d),
           "--workers", str(workers)]
    meta: dict[str, object] = {"group": group, "fold": fold, "cmd": cmd, "head": head_sha(), "frozen_sha": FROZEN_SHA,
                               "started_utc": dt.datetime.now(dt.UTC).isoformat(timespec="seconds")}
    with open(d / "log.txt", "w", encoding="utf-8") as fh:
        rc = subprocess.run(cmd, stdout=fh, stderr=subprocess.STDOUT, env={**os.environ, "PYTHONWARNINGS": "ignore"}, check=False).returncode
    meta.update({"finished_utc": dt.datetime.now(dt.UTC).isoformat(timespec="seconds"), "returncode": rc})
    (d / "run.json").write_text(json.dumps(meta, indent=2), encoding="utf-8")
    print(f"{name}: rc={rc} {meta['started_utc']} -> {meta['finished_utc']}", flush=True)
    return meta


def cmd_runs(a: argparse.Namespace) -> int:
    jobs = [(g, f) for g, f in ORDER if a.groups is None or g in a.groups]
    with ThreadPoolExecutor(max_workers=a.lanes) as ex:
        res = list(ex.map(lambda j: one(j[0], j[1], a.out, a.workers), jobs))
    return 0 if all(m["returncode"] == 0 for m in res) else 1


# ----------------------------------------------------------------------------
# hindcast (§6)
# ----------------------------------------------------------------------------


def cmd_hindcast(a: argparse.Namespace) -> int:
    from etl.db import get_connection

    frames = []
    for g in a.groups or c16.PROVISIONAL:
        for c in ac.CUTOFFS:
            with get_connection() as conn:
                h = c16.hindcast_fold(conn, g, p9r.wells_dir(g, RUN10_WELLS), c, ACTUALS_THROUGH, a.workers)
            frames.append(h)
            _, n = c16.hindcast_bias(h)
            print(f"{g} {c}: {len(h)} subjects, {n} scored", flush=True)
    d = pd.concat(frames, ignore_index=True)
    d.to_csv(a.out / "hindcast_level_only.csv", index=False)
    print(f"wrote {a.out / 'hindcast_level_only.csv'} ({len(d)} rows)")
    return 0


# ----------------------------------------------------------------------------
# off-local (§5 input 3)
# ----------------------------------------------------------------------------

_OL: dict[str, Any] = {}


def _ol_init(state: dict[str, Any]) -> None:
    import logging

    from dealintake import config as di_config

    logging.disable(logging.CRITICAL)
    _OL.update(state)
    _OL["cfg"] = di_config.load()


def _ol_chunk(locs: list[dict[str, Any]]) -> pd.DataFrame:
    return c16.off_local_rows(_OL["pool2"], _OL["pool_m"], locs, _OL["cfg"], _OL["label"], OFFLOCAL_VARIANTS)


def cmd_offlocal(a: argparse.Namespace) -> int:
    from box import backtest_report as br
    from etl.db import get_connection

    with open(a.run, "rb") as fh:
        A = pickle.load(fh)
    frames = []
    for g in a.groups or c16.PROVISIONAL:
        with open(a.pools / f"pool_{g}.pkl", "rb") as fh:
            P = pickle.load(fh)
        pool2 = P["pool2"]
        with get_connection() as conn:
            sp = br.spacing(conn, sorted({str(x) for x in pool2["api10"]}))
        pool_m = s16.measured_pool(pool2, {str(k): v for k, v in sp.items()})
        locs = [lo for lo, r in zip(A["locs"], A["results"], strict=True) if lo["prod_bench"] == g and int(r.get("n_analogs") or 0) >= 3 and r.get("streams")]
        chunks = [locs[i:i + 64] for i in range(0, len(locs), 64)]
        with ProcessPoolExecutor(max_workers=a.workers, initializer=_ol_init, initargs=({"pool2": pool2, "pool_m": pool_m, "label": P["label"]},)) as ex:
            d = pd.concat(list(ex.map(_ol_chunk, chunks)), ignore_index=True).assign(group=g)
        frames.append(d)
        print(f"{g}: {len(d)} PUDs", flush=True)
    out = pd.concat(frames, ignore_index=True)
    out.to_csv(a.out / "offlocal_pud.csv.gz", index=False)
    print(c16.off_local_share(out, OFFLOCAL_VARIANTS).to_string(index=False))
    return 0


# ----------------------------------------------------------------------------
# score
# ----------------------------------------------------------------------------


def _cells(run_dir: Path, group: str, fold: str) -> pd.DataFrame:
    return pd.read_csv(run_dir / f"cells_{c16.run_tag(group, fold)}.csv")


def cmd_score(a: argparse.Namespace) -> int:
    a.docs.mkdir(parents=True, exist_ok=True)
    variants = (*s16.SCORED, f"{s16.BASE}_wf", "box_v2", "box_v2_wf")
    views, pooled, keep, ident, cui_by_group = {}, [], [], [], []
    for g, fold in ORDER:
        run_dir = a.out / (g if fold == "analog" else f"{g}_{fold}")
        if not (run_dir / "run.json").exists():
            print(f"{g} {fold}: no run", flush=True)
            continue
        meta = json.loads((run_dir / "run.json").read_text(encoding="utf-8"))
        cells = _cells(run_dir, g, fold)
        v = c16.load_views(run_dir, g, fold)
        if fold == "analog":
            views[g] = v
            pc = c16.pooled_cells(v, variants).assign(group=g)
            pooled.append(pc)
            ct = c16.cui_table(v)
            if not ct.empty:
                cui_by_group.append(ct.assign(group=g))
        rec_path = RECORD_CELLS.get(g)
        if rec_path is not None and rec_path.exists():
            rec = pd.read_csv(rec_path)
            idt = t9.identity(cells, rec, variants=("box_v2", "box_v2_wf"))
            ident.append(idt.assign(group=g, fold=fold, head=meta["head"]))
        if g in c16.VALIDATED_FORM:
            new_v, rec_v, form = c16.VALIDATED_FORM[g]
            if (form == "per_cutoff" and fold == "full") or (form == "pooled" and fold == "analog"):
                if form == "per_cutoff":
                    new_c, rec_c = cells[cells.variant == new_v], cells[cells.variant == rec_v]
                else:
                    new_c, rec_c = pc[pc.variant == new_v], pc[pc.variant == rec_v]
                keep.append({"group": g, "fold": fold, "form": form, "new_base": new_v, "record": rec_v, **c16.keep_validated(new_c, rec_c)})
    pooled_df = pd.concat(pooled, ignore_index=True)
    pooled_df.to_csv(a.docs / "pooled_cells.csv", index=False)
    pd.DataFrame(keep).to_csv(a.docs / "validated_keep.csv", index=False)
    if ident:
        pd.concat(ident, ignore_index=True).to_csv(a.docs / "record_identity.csv", index=False)
    cui_g = pd.concat(cui_by_group, ignore_index=True) if cui_by_group else pd.DataFrame()
    cui_g.to_csv(a.docs / "cui_vs_linear_by_group.csv", index=False)
    # §5 — provisional inputs pooled over the eight groups
    prov_views = pd.concat([views[g] for g in c16.PROVISIONAL if g in views], ignore_index=True)
    prov_cells = pooled_df[pooled_df.group.isin(c16.PROVISIONAL)]
    strat = c16.stratum_table(prov_views, (s16.BASE, *s16.CANDIDATES, *s16.COMPARISON))
    cui_pool = c16.cui_table(prov_views)
    hpath, opath = a.out / "hindcast_level_only.csv", a.out / "offlocal_pud.csv.gz"
    hb, hn = c16.hindcast_bias(pd.read_csv(hpath)) if hpath.exists() else (None, 0)
    off = c16.off_local_share(pd.read_csv(opath), OFFLOCAL_VARIANTS) if opath.exists() else pd.DataFrame(columns=["variant", "share_off"])
    res = s16.adopt(prov_cells, strat, off, None if hb is None or not np.isfinite(hb) else hb,
                    cui_ok=s16.cui_holds(cui_pool) if not cui_pool.empty else None)
    strat.to_csv(a.docs / "stratum_far_with_local.csv", index=False)
    cui_pool.to_csv(a.docs / "cui_vs_linear_provisional.csv", index=False)
    off.to_csv(a.docs / "offlocal_share.csv", index=False)
    summary = {"built_utc": dt.datetime.now(dt.UTC).isoformat(timespec="seconds"), "frozen_sha": FROZEN_SHA, "head": head_sha(),
               "adoption": res, "hindcast_bias": hb, "hindcast_n": hn, "cui_flags": s16.cui_flags(cui_g) if not cui_g.empty else [],
               "validated_keep": keep, "groups_scored": sorted(views)}
    (a.docs / "summary.json").write_text(json.dumps(summary, indent=2, default=lambda o: o.item() if hasattr(o, "item") else str(o)),
                                         encoding="utf-8")
    print(json.dumps({"adopted": res["adopted"], "checks": res["checks"], "hindcast": hb, "cui_flags": summary["cui_flags"]},
                     indent=1, default=str))
    print(pd.DataFrame(keep).to_string(index=False))
    return 0


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    for name in ("runs", "hindcast", "offlocal", "score"):
        p = sub.add_parser(name)
        p.add_argument("--out", type=Path, default=Path("runs") / "step16c")
        p.add_argument("--groups", type=lambda v: [x.strip() for x in v.split(",") if x.strip()], default=None)
        p.add_argument("--workers", type=int, default=6 if name == "runs" else 14)
        if name == "runs":
            p.add_argument("--lanes", type=int, default=3)
        if name == "offlocal":
            p.add_argument("--run", type=Path, default=Path("runs") / "box9" / "run.pkl")
            p.add_argument("--pools", type=Path, default=Path("runs") / "cohort_review")
        if name == "score":
            p.add_argument("--docs", type=Path, default=Path("docs") / "box" / "step16c-2026-10-22")
    a = ap.parse_args(argv)
    sys.stdout.reconfigure(encoding="utf-8")  # type: ignore[union-attr]
    if not code_matches_frozen():
        print(f"the scored code differs from the frozen SHA {FROZEN_SHA}: not a 16c score", file=sys.stderr)
        return 2
    a.out.mkdir(parents=True, exist_ok=True)
    return {"runs": cmd_runs, "hindcast": cmd_hindcast, "offlocal": cmd_offlocal, "score": cmd_score}[a.cmd](a)


if __name__ == "__main__":
    raise SystemExit(main())
