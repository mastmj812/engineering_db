"""BOX step 15 — bench QC + pooling evidence for a Delaware bench family (read-only).

    python -m scripts.box_family_qc --family BS3 [--out docs/box/step15a-YYYY-MM-DD] [--pool-dir docs/box/pool-2026-10-15]
                                    [--cache <scratch.pkl>] [--asks <asks.json>]

Pulls the Delaware producing horizontals (box.bench_qc, READ ONLY transaction), scores the consensus detector,
applies the class rule of record with Michael's gate-1 card verdicts, reconciles against the frozen D84 pools and
writes per-bench step-1 QC pages, the family page (index.html), wells_final_<bench>.csv, family_roles.csv and
summary.json. ``--cache`` keeps the scored frame so a re-render does not re-pull. Nothing is written to the warehouse.
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import subprocess
import sys
import time
from pathlib import Path

import pandas as pd

from box import exclusions
from box import family_qc as fq
from box.bench_qc import pull_producers, score_consensus
from box.qc_rule import load_verdicts

GATE1_CARDS = Path("docs") / "box" / "step1-2026-10-06" / "cards_sample.csv"


def _git_sha() -> str:
    sha = subprocess.run(["git", "rev-parse", "--short", "HEAD"], capture_output=True, text=True, check=False).stdout.strip()
    dirty = subprocess.run(["git", "status", "--porcelain", "--untracked-files=no"], capture_output=True, text=True, check=False).stdout.strip()
    return sha + ("+dirty" if dirty else "")


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--family", choices=sorted(fq.FAMILIES), required=True)
    ap.add_argument("--out", type=Path, default=None)
    ap.add_argument("--pool-dir", type=Path, nargs="+", default=[Path("docs") / "box" / "pool-2026-10-15", Path("docs") / "box" / "step15a-2026-10-16"],
                    help="frozen pool dirs (wells_final_*.csv); the first with universe.csv gives the judged universe")
    ap.add_argument("--verdicts", type=Path, action="append", default=None)
    ap.add_argument("--cache", type=Path, default=None, help="pickle of the scored frame; read if present, else written")
    ap.add_argument("--asks", type=Path, default=None, help="JSON list of gate-ask strings (HTML) for the page")
    ap.add_argument("--basin", default="delaware", help="the basin pulled and scored (step 19)")
    a = ap.parse_args(argv)
    out = a.out or Path("docs") / "box" / f"step15a-{dt.datetime.now(tz=dt.UTC).astimezone():%Y-%m-%d}"
    t0 = time.time()
    if a.cache and a.cache.exists():
        scored = pd.read_pickle(a.cache)
    else:
        from etl.db import get_connection

        with get_connection() as conn:
            scored = score_consensus(pull_producers(conn, a.basin))
        if a.cache:
            scored.to_pickle(a.cache)
    verdicts: dict[str, str] = {}
    for p in a.verdicts or [GATE1_CARDS]:
        verdicts.update(load_verdicts(p))
    excluded = set(exclusions.load()["api10"])
    meta = {
        "built_at": dt.datetime.now(tz=dt.UTC).astimezone().isoformat(timespec="seconds"), "git_sha": _git_sha(),
        "asof": str(scored.attrs.get("asof")), "n_delaware_prod_hz": len(scored), "n_witness": int(scored["cons_witness"].sum()),
        "verdicts": {"agree": sum(v == "AGREE" for v in verdicts.values()), "reject": sum(v == "REJECT" for v in verdicts.values())},
        "asks": json.loads(a.asks.read_text(encoding="utf-8")) if a.asks else [],
    }
    s = fq.build(scored, a.family, out, a.pool_dir, verdicts, excluded, meta, basin=a.basin)
    for b in s["benches"]:
        r = s["set"][b]
        print(f"{b}: tagged {r['tagged_live']:,} -> final {r['final']:,} (member {r['member']:,}, churn kept {r['old_churn_kept']}, "
              f"frozen elsewhere {r['frozen_elsewhere']} {r['frozen_to']}, new out {r['new_ruled_out']} {r['new_ruled_out_to']}, excluded {r['excluded']}); "
              f"cohort {r['final_cohort']:,}")
    for pr in s["pairs"]:
        pe = pr["pooling"]
        for k in ("oil12_kft", "gor12", "cum24_over_cum12"):
            print(f"  {pe['b']}/{pe['a']} {k}: {pe[k]['ratio']:.3f} [{pe[k]['ci90'][0]:.3f}-{pe[k]['ci90'][1]:.3f}] blocks {pe[k]['n_blocks_both']}")
    print(f"uncalibrated flags {s['uncalibrated_flags']} in {s['uncalibrated_classes']}")
    print(f"wrote {out / 'index.html'}  ({time.time() - t0:.0f} s)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
