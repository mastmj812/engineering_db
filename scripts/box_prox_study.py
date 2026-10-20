"""PDP-proximity study (read-only): step 1 pair table + precedent atlas, step 2 dose-response, step 2b configuration.

    python -m scripts.box_prox_study [atlas] [--out docs/box/prox-2026-10-19] [--runs runs/prox]
    python -m scripts.box_prox_study dose [--views runs/prox/views] [--boot 500]     (DB-free; needs atlas's runs/ files)
    python -m scripts.box_prox_study config [--views runs/prox/views] [--boot 500]   (step 2b, DB-free)
    python -m scripts.box_prox_study validate [--views runs/prox/views]              (step 2c, pre-registered, DB-free)

See box/prox_study.py (pair metric = deal-intake v14's, classes, atlas) and box/prox_study_report.py (pull, page).
Reads curated.wells / wells_enriched / production / dev_scenario inside READ ONLY transactions; writes nothing to
the warehouse.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from box import prox_config_report as pcr
from box import prox_dose_report as pdr
from box import prox_study_report as pr
from box import prox_validate_report as pvr
from etl.db import get_connection


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("step", nargs="?", choices=("atlas", "dose", "config", "validate"), default="atlas")
    ap.add_argument("--views", type=Path, default=Path("runs") / "prox" / "views")
    ap.add_argument("--boot", type=int, default=500)
    ap.add_argument("--out", type=Path, default=Path("docs") / "box" / "prox-2026-10-19")
    ap.add_argument("--runs", type=Path, default=Path("runs") / "prox")
    a = ap.parse_args(argv)
    if a.step == "validate":
        res = pvr.run(a.views, a.runs, a.out)
        print({k: v for k, v in res["meta"].items() if k not in ("digests", "by_group", "by_split", "groups")})
        for m, r in res["res"].items():
            print(f"== {m}: {r['verdict']}  P1 {r['P1_resid']:.3f} [{r['P1_lo']:.3f}-{r['P1_hi']:.3f}] (no haircut {r['P1_no_haircut']:.3f})  "
                  f"P2 rms {r['P2_rms']:.3f} vs {r['P2_rms_no_haircut']:.3f}  P3 {r['P3_share']:.2f} of {r['n_cells']} cells")
        print(f"wrote {a.out}")
        return 0
    if a.step == "config":
        res = pcr.run(a.views, a.runs, a.out, n_boot=a.boot)
        for k, t in res["tables"].items():
            print(f"== {k}")
            print(t.round(2).to_string(index=False))
        print(f"wrote {a.out}")
        return 0
    if a.step == "dose":
        res = pdr.run(a.views, a.runs, a.out, n_boot=a.boot)
        print({k: v for k, v in res["meta"].items() if k != "digests"})
        print(pdr.slim(res["tables"]["headline"]).round(3).to_string())
        print(f"wrote {a.out}")
        return 0
    with get_connection() as conn:
        res = pr.run(conn, a.out, a.runs)
    print(res["summary"])
    print(res["atlas"]["by_bench"].to_string())
    print(res["reconcile"].to_string())
    print(f"wrote {a.out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
