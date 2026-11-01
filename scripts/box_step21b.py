"""BOX step 21b driver: the Midland tuning-fold scoring of the FROZEN pre-registration
(docs/box/step21a-2026-10-31/PREREGISTRATION.md, box/step21.DEFINITION digest 505439b9, frozen SHA 501d799).

    python -m scripts.box_step21b runs  --out runs/step21b [--lanes 3] [--workers 6] [--groups MID_WCA_1,MID_MS]
    python -m scripts.box_step21b prox  --out runs/step21b            # drilled-child + stick proximity links (read-only, cached)
    python -m scripts.box_step21b score --out runs/step21b --docs docs/box/step21b-2026-11-01

`runs`: PREREGISTRATION §10 exactly — one `scripts.box_acceptance --fold analog --bench MID_<bench> --step16 --wells
docs/box/pool-midland-2026-10-31 --actuals-through 2026-08-01` per group; each writes --out/<group>/ and a run.json with the HEAD
SHA, the frozen SHA, the frozen-file check, the last nightly's state and timestamps. Every command refuses to start when a file of
box/, scripts/ or dealintake/ that exists at the frozen SHA differs from it (files ADDED after the freeze are this step's new
scorer code and are listed in run.json), and `runs` / `prox` refuse while an etl-nightly run is in progress (the 2026-10-26 trap).
Read-only against the warehouse.
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Any

from box import step21 as st

FROZEN_SHA = "501d79910b2537ee7579cbbc43352666fda2ef82"
FROZEN_PATHS = ("box", "scripts", "dealintake")
ACTUALS_THROUGH = dt.date.fromisoformat(st.DEFINITION["folds"]["actuals_through"])
# heaviest pool first so the lanes finish together (pool rows: PREREGISTRATION §1)
ORDER: tuple[str, ...] = ("MID_WCA_1", "MID_WCB_1", "MID_LSSH", "MID_WCB_2", "MID_JM", "MID_MS", "MID_WCD", "MID_DEAN", "MID_WCC")
PROOF_GROUP = "MID_WCC"  # smallest pool: also run as the bare §10 command, outputs compared with the observed run


def _git(*a: str) -> str:
    return subprocess.run(["git", *a], capture_output=True, text=True, check=True).stdout.strip()


def head_sha() -> str:
    return _git("rev-parse", "HEAD")


def frozen_check() -> dict[str, Any]:
    """Frozen files = every path under box/, scripts/, dealintake/ that exists at FROZEN_SHA. Working tree vs the SHA: any
    Modified / Deleted / Renamed file there fails; Added files (this step's new code) pass and are listed. Untracked files are
    new by definition (git diff does not show them) and are listed too."""
    ns = _git("diff", "--name-status", FROZEN_SHA, "--", *FROZEN_PATHS)
    rows = [ln.split("\t") for ln in ns.splitlines() if ln.strip()]
    changed = [r for r in rows if r[0] != "A"]
    added = [r[-1] for r in rows if r[0] == "A"]
    untracked = [p for p in _git("ls-files", "--others", "--exclude-standard", "--", *FROZEN_PATHS).splitlines() if p.strip()]
    return {"frozen_sha": FROZEN_SHA, "identical": not changed, "changed": ["\t".join(r) for r in changed], "added": added,
            "untracked": untracked}


def nightly_state() -> dict[str, Any]:
    """The newest etl-nightly run (gh). in_progress / queued = a build must not start."""
    out = subprocess.run(["gh", "run", "list", "--workflow", "etl-nightly.yml", "-L", "1", "--json",
                          "databaseId,status,conclusion,createdAt,updatedAt"], capture_output=True, text=True, check=True).stdout
    r = (json.loads(out) or [{}])[0]
    r["busy"] = r.get("status") in ("in_progress", "queued", "waiting", "requested", "pending")
    return r


def guard(need_idle: bool) -> tuple[dict[str, Any], dict[str, Any] | None]:
    fc = frozen_check()
    if not fc["identical"]:
        raise SystemExit(f"frozen files differ from {FROZEN_SHA[:7]}: {fc['changed']} — not a score; refusing")
    ns = None
    if need_idle:
        ns = nightly_state()
        if ns["busy"]:
            raise SystemExit(f"etl-nightly {ns.get('databaseId')} is {ns.get('status')} (started {ns.get('createdAt')}); refusing to build")
        if ns.get("conclusion") != "success":  # a red night may leave the curated layer half-refreshed: ask, don't build
            raise SystemExit(f"etl-nightly {ns.get('databaseId')} concluded {ns.get('conclusion')!r}; refusing to build")
    return fc, ns


# ----------------------------------------------------------------------------
# runs (§10)
# ----------------------------------------------------------------------------


def one(group: str, out: Path, workers: int, plain: bool = False) -> dict[str, Any]:
    """One §10 run. Default: through scripts.box_step21b_harness (the same command, mid_r2 months observed); `plain` = the bare
    scripts.box_acceptance command into <group>_plain (the equivalence proof)."""
    d = out / (f"{group}_plain" if plain else group)
    done = d / "run.json"
    if done.exists() and json.loads(done.read_text(encoding="utf-8")).get("returncode") == 0:
        print(f"{group}: already complete, skipped", flush=True)  # resume after an interruption: finished runs are kept
        return json.loads(done.read_text(encoding="utf-8"))
    fc, ns = guard(need_idle=True)  # re-checked per run: a lane may start hours after the first
    d.mkdir(parents=True, exist_ok=True)
    mod = "scripts.box_acceptance" if plain else "scripts.box_step21b_harness"
    cmd = [sys.executable, "-W", "ignore", "-m", mod, "--fold", "analog", "--bench", group, "--step16",
           "--wells", str(st.POOL_DIR), "--actuals-through", str(ACTUALS_THROUGH), "--out", str(d), "--workers", str(workers)]
    meta: dict[str, Any] = {"group": group, "plain": plain, "cmd": cmd, "head": head_sha(), "frozen_sha": FROZEN_SHA, "frozen_check": fc,
                            "nightly_at_start": ns, "definition_digest": st.digest(),
                            "started_utc": dt.datetime.now(dt.UTC).isoformat(timespec="seconds")}
    with open(d / "log.txt", "w", encoding="utf-8") as fh:
        rc = subprocess.run(cmd, stdout=fh, stderr=subprocess.STDOUT, env={**os.environ, "PYTHONWARNINGS": "ignore"}, check=False).returncode
    fc_end = frozen_check()
    meta.update({"finished_utc": dt.datetime.now(dt.UTC).isoformat(timespec="seconds"), "returncode": rc,
                 "frozen_check_at_end": fc_end, "nightly_at_end": nightly_state()})
    (d / "run.json").write_text(json.dumps(meta, indent=2), encoding="utf-8")
    print(f"{d.name}: rc={rc} {meta['started_utc']} -> {meta['finished_utc']} frozen_identical={fc_end['identical']}", flush=True)
    return meta


def cmd_runs(a: argparse.Namespace) -> int:
    guard(need_idle=True)
    jobs = [(g, False) for g in ORDER if a.groups is None or g in a.groups]
    if a.groups is None or PROOF_GROUP in a.groups:
        jobs.append((PROOF_GROUP, True))  # the wrapper's equivalence proof (plain §10 command, compared by `score`)
    with ThreadPoolExecutor(max_workers=a.lanes) as ex:
        res = list(ex.map(lambda j: one(j[0], a.out, a.workers, j[1]), jobs))
    return 0 if all(m["returncode"] == 0 for m in res) else 1


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    for name in ("runs", "prox", "score"):
        p = sub.add_parser(name)
        p.add_argument("--out", type=Path, default=Path("runs") / "step21b")
        p.add_argument("--groups", type=lambda v: [x.strip() for x in v.split(",") if x.strip()], default=None)
        if name == "runs":
            p.add_argument("--lanes", type=int, default=3)
            p.add_argument("--workers", type=int, default=6)
        if name == "score":
            p.add_argument("--docs", type=Path, default=Path("docs") / "box" / "step21b-2026-11-01")
    a = ap.parse_args(argv)
    a.out.mkdir(parents=True, exist_ok=True)
    if a.cmd == "runs":
        return cmd_runs(a)
    raise SystemExit(f"{a.cmd}: not written yet")


if __name__ == "__main__":
    sys.exit(main())
