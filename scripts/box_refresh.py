"""BOX steady-state refresh (step 13b, D126) — one entry point for the quarterly / on-demand refresh. Read-only.

    python -m scripts.box_refresh check                      is a refresh due (vintage, 4-month lag), the extent trigger per group
    python -m scripts.box_refresh plan  --pool <dir> --out runs/<label> [--workers 14]
                                                             the ordered chain; every store is printed, never run (each its own go)
    python -m scripts.box_refresh build --pool <dir> --out runs/<label> [--workers 14]
                                                             runs the read-only build + water build of a confirmed, committed pool

Nothing here writes to the database. The stores, the proximity record and the D123 prune are run by hand on Michael's go, in
the order `plan` prints (and the novi-quarterly-reload skill §9 states).
"""

from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path

from box import refresh13 as r13
from etl.db import get_connection


def check() -> int:
    with get_connection() as conn:
        cur = conn.cursor()
        cur.execute("SET TRANSACTION READ ONLY")
        cur.execute(r13.STATE_SQL)
        row = cur.fetchone()
        if row is None:
            raise SystemExit("no record run")
        run_id, rv, through, live_v, live_through = row
        counts = {}
        for g, (forms, bench) in r13.GROUPS.items():
            cur.execute(r13.EXTENT_SQL, {"bench": bench, "forms": list(forms), "x_m": r13.EXTENT_X_MI * r13.MI_M})
            counts[g] = int(cur.fetchone()[0])
        conn.rollback()
    is_due, why = r13.due(rv, live_v, through, live_through)
    print(f"record run {run_id}: Novi {rv}, production through {through} | warehouse: Novi {live_v}, production through {live_through}")
    print(("REFRESH DUE: " + "; ".join(why)) if is_due else "no refresh due (vintage unchanged, lag within the safety net); on demand stays open")
    trig = r13.extent_trigger(counts)
    print(f"extent trigger (>= {r13.EXTENT_N} producers first producing after the extent was stored, outside it within {r13.EXTENT_X_MI:g} mi):")
    print("  " + ", ".join(f"{g} {c}" for g, c in counts.items()))
    print(("  RE-REVIEW DUE: " + ", ".join(trig)) if trig else "  none due")
    return 0


def plan(pool: str, out: str, workers: int) -> int:
    for i, s in enumerate(r13.chain(pool, out, workers), 1):
        print(f"{i}. {'[GO] ' if s['go'] else ''}{s['step']}\n     {s['cmd']}")
    return 0


def build(pool: Path, out: str, workers: int) -> int:
    if not (pool / "refresh.json").exists():
        raise SystemExit(f"{pool} is not a pool refresh directory (no refresh.json)")
    if subprocess.run(["git", "status", "--porcelain", "--", str(pool)], capture_output=True, text=True, check=True).stdout.strip():
        raise SystemExit(f"{pool} is not committed: commit the confirmed pool refresh before building from it")
    steps = [s for s in r13.chain(str(pool), out, workers) if s["step"].startswith(("build", "water build"))]
    for s in steps:
        print(f"== {s['step']}\n   {s['cmd']}", flush=True)
        rc = subprocess.run([sys.executable, "-m", *s["cmd"].split()[2:]], check=False).returncode
        if rc:
            raise SystemExit(f"{s['step']} failed ({rc})")
    print("read-only builds done; the stores are next, each on its own go (python -m scripts.box_refresh plan ...)")
    return 0


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("cmd", choices=("check", "plan", "build"))
    ap.add_argument("--pool", type=Path, help="the confirmed, committed pool refresh directory (docs/box/pool-YYYY-MM-DD)")
    ap.add_argument("--out", help="the run output directory (runs/<label>)")
    ap.add_argument("--workers", type=int, default=14)
    a = ap.parse_args(argv)
    if a.cmd == "check":
        return check()
    if not a.pool or not a.out:
        raise SystemExit("--pool and --out are required")
    if a.cmd == "plan":
        return plan(a.pool.as_posix(), a.out, a.workers)
    return build(a.pool, a.out, a.workers)


if __name__ == "__main__":
    sys.exit(main())
