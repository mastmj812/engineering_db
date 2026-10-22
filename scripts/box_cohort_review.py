"""BOX cohort-selection review (box/cohort_review.py). READ ONLY vs the warehouse; writes local files only.

    python -m scripts.box_cohort_review pools  --run runs/box9/run.pkl --pools runs/cohort_review [--groups BS1_S,WCA]
    python -m scripts.box_cohort_review review --run runs/box9/run.pkl --pools runs/cohort_review --out docs/box/cohort-review-2026-10-22

`pools` rebuilds each group's analog pool exactly as `box_pud_run build` did for the run (scripts.box_pud_run.build_pool on the
group's well set, production cutoff pinned to the run's), one pickle per group. `review` classifies every covered PUD of the run's
build against its near pool wells (box.cohort_review.pud_row), re-runs the record selection with measured spacing (read-only
wells_enriched read), checks the record reproduces, and writes pud_review.csv.gz, summary_by_group.csv, closure_by_lateral.csv. The run's build artifact (run.pkl) is run 10's; run 14 = run 10 + the proximity layer, same selection.
"""

from __future__ import annotations

import argparse
import datetime as dt
import pickle
import sys
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from box import cohort_review as cr

_ST: dict[str, Any] = {}


def _load_run(path: Path) -> dict[str, Any]:
    with open(path, "rb") as fh:
        A = pickle.load(fh)
    return {"run": A["run"], "pairs": [(lo, r) for lo, r in zip(A["locs"], A["results"], strict=True)]}


def cmd_pools(a: argparse.Namespace) -> int:
    import scripts.box_pud_run as bpr
    from box import production_run9 as p9r
    from etl.db import get_connection

    run = _load_run(a.run)["run"]
    cut = run["cutoff"] if isinstance(run["cutoff"], dt.date) else dt.date.fromisoformat(str(run["cutoff"]))
    last = dt.date(cut.year - (cut.month == 1), (cut.month - 2) % 12 + 1, 1)
    bpr.rep.last_full_month = lambda _rows: last  # pin the cutoff to the run's (production since then must not move the pool)
    a.pools.mkdir(parents=True, exist_ok=True)
    for g in a.groups or list(run["benches"]):
        out = a.pools / f"pool_{g}.pkl"
        if out.exists():
            print(f"{g}: exists, skipped")
            continue
        with get_connection() as conn:
            P = bpr.build_pool(conn, a.workers, p9r.wells_dir(g, Path(run["wells_dir"])), g)
        with open(out, "wb") as fh:
            pickle.dump({k: P.get(k) for k in ("pool", "pool2", "cutoff", "asof", "label", "extent_id")}, fh)
        print(f"{g}: {len(P['pool']['api10'])} pool wells, cutoff {P['cutoff']}")
    return 0


def _init(state: dict[str, Any]) -> None:
    import logging

    from scipy.spatial import cKDTree

    from dealintake import config as di_config

    _ST.update(state)
    _ST["tree"] = cKDTree(np.column_stack([state["pool"]["x"], state["pool"]["y"]]))
    _ST["cfg"] = di_config.load()
    logging.getLogger().setLevel(logging.CRITICAL)


def _one(pair: tuple[dict[str, Any], dict[str, Any]]) -> dict[str, Any]:
    lo, r = pair
    return cr.pud_row(lo, r, _ST["pool"], _ST["tree"], _ST["cfg"], _ST["label"], pool_fix=_ST.get("pool_fix"))


_SPACING_SQL = "SELECT api10, lateral_closer_xy_ft FROM curated.wells_enriched WHERE api10 = ANY(%(a)s)"


def measured_spacing(conn: Any, pool: dict[str, Any]) -> dict[str, Any]:
    """The pool with every well's curated.wells_enriched.lateral_closer_xy_ft (NULL stays NaN = standalone, as deal-intake reads it)."""
    with conn.cursor() as cur:
        cur.execute("SET TRANSACTION READ ONLY")
        cur.execute(_SPACING_SQL, {"a": [str(a) for a in pool["api10"]]})
        we = {a: v for a, v in cur.fetchall()}
    conn.rollback()
    return {**pool, "spacing": np.array([np.nan if we.get(str(a)) is None else float(we[str(a)]) for a in pool["api10"]])}



def cmd_review(a: argparse.Namespace) -> int:
    from box import production_run9 as p9r
    from etl.db import get_connection

    R = _load_run(a.run)
    run = R["run"]
    frames = []
    for g in a.groups or list(run["benches"]):
        with open(a.pools / f"pool_{g}.pkl", "rb") as fh:
            P = pickle.load(fh)
        pairs = [(lo, r) for lo, r in R["pairs"] if lo["prod_bench"] == g and int(r.get("n_analogs") or 0) >= 3 and r.get("streams")]
        with get_connection() as conn:
            fix = measured_spacing(conn, P["pool2"])
        state = {"pool": P["pool2"], "pool_fix": fix, "label": P["label"]}
        with ProcessPoolExecutor(max_workers=a.workers, initializer=_init, initargs=(state,)) as ex:
            rows = list(ex.map(_one, pairs, chunksize=64))
        d = pd.DataFrame(rows).assign(group=g, tier=p9r.tier(g))
        frames.append(d)
        print(f"{g}: {len(d)} covered PUDs, far-with-local {int(d['far_with_local'].sum())}, record reproduced "
              f"{100 * d['repro_ok'].mean():.1f} %", flush=True)
    d = pd.concat(frames, ignore_index=True)
    a.out.mkdir(parents=True, exist_ok=True)
    d.to_csv(a.out / "pud_review.csv.gz", index=False)
    s = cr.summarize(d)
    s.to_csv(a.out / "summary_by_group.csv", index=False)
    cr.closure_by_lateral(d).to_csv(a.out / "closure_by_lateral.csv", index=False)
    print(s.to_string(index=False, float_format=lambda v: f"{v:.1f}"))
    print(f"wrote {a.out}")
    return 0


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    for name in ("pools", "review"):
        p = sub.add_parser(name)
        p.add_argument("--run", type=Path, default=Path("runs") / "box9" / "run.pkl", help="the record build's run.pkl")
        p.add_argument("--pools", type=Path, default=Path("runs") / "cohort_review")
        p.add_argument("--groups", type=lambda v: [x.strip() for x in v.split(",") if x.strip()], default=None)
        p.add_argument("--workers", type=int, default=14)
        if name == "review":
            p.add_argument("--out", type=Path, default=Path("docs") / "box" / "cohort-review-2026-10-22")
    a = ap.parse_args(argv)
    sys.stdout.reconfigure(encoding="utf-8")  # type: ignore[union-attr]
    return cmd_pools(a) if a.cmd == "pools" else cmd_review(a)


if __name__ == "__main__":
    raise SystemExit(main())
