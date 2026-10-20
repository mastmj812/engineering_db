"""PDP-proximity study (read-only): step 1 pair table + precedent atlas, step 2 dose-response.

    python -m scripts.box_prox_study [atlas] [--out docs/box/prox-2026-10-19] [--runs runs/prox]
    python -m scripts.box_prox_study dose [--views runs/prox/views] [--boot 500]     (DB-free; needs atlas's runs/ files)

See box/prox_study.py (pair metric = deal-intake v14's, classes, atlas) and box/prox_study_report.py (pull, page).
Reads curated.wells / wells_enriched / production / dev_scenario inside READ ONLY transactions; writes nothing to
the warehouse.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from box import prox_dose_report as pdr
from box import prox_study_report as pr
from etl.db import get_connection


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("step", nargs="?", choices=("atlas", "dose"), default="atlas")
    ap.add_argument("--views", type=Path, default=Path("runs") / "prox" / "views")
    ap.add_argument("--boot", type=int, default=500)
    ap.add_argument("--out", type=Path, default=Path("docs") / "box" / "prox-2026-10-19")
    ap.add_argument("--runs", type=Path, default=Path("runs") / "prox")
    a = ap.parse_args(argv)
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
