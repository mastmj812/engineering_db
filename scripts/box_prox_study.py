"""PDP-proximity study, step 1 (read-only): pair table + precedent atlas for Delaware producing horizontals.

    python -m scripts.box_prox_study [--out docs/box/prox-2026-10-19] [--runs runs/prox]

See box/prox_study.py (pair metric = deal-intake v14's, classes, atlas) and box/prox_study_report.py (pull, page).
Reads curated.wells / wells_enriched / production / dev_scenario inside READ ONLY transactions; writes nothing to
the warehouse.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from box import prox_study_report as pr
from etl.db import get_connection


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--out", type=Path, default=Path("docs") / "box" / "prox-2026-10-19")
    ap.add_argument("--runs", type=Path, default=Path("runs") / "prox")
    a = ap.parse_args(argv)
    with get_connection() as conn:
        res = pr.run(conn, a.out, a.runs)
    print(res["summary"])
    print(res["atlas"]["by_bench"].to_string())
    print(res["reconcile"].to_string())
    print(f"wrote {a.out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
