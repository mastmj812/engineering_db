"""BOX acceptance of record (D53): package-level rolling-origin folds vs a local-offsets benchmark; D52 holdout excluded.

    python -m scripts.box_acceptance [--wells docs/box/step1-2026-10-06] [--out docs/box/acceptance] [--workers N]
                                     [--cutoffs 2019-12-01,...,2024-12-01] [--score-holdout]

--score-holdout is the ONE-TIME final scoring of the frozen D52 holdout, after the model spec and code SHA are frozen.
Read-only against the warehouse. See box/acceptance.py.
"""

from __future__ import annotations

import argparse
import datetime as dt
import sys
import time
from pathlib import Path

from box import acceptance as ac
from etl.db import get_connection
from scripts.box_tc_curves import boxfit_sha


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--wells", type=Path, default=Path("docs") / "box" / "step1-2026-10-06")
    ap.add_argument("--out", type=Path, default=Path("docs") / "box" / "acceptance")
    ap.add_argument("--workers", type=int, default=None)
    ap.add_argument("--cutoffs", default=",".join(str(c) for c in ac.CUTOFFS))
    ap.add_argument("--score-holdout", action="store_true", help="ONE-TIME final scoring of the frozen D52 holdout")
    a = ap.parse_args(argv)
    t0 = time.time()
    with get_connection() as conn:
        res = ac.run(conn, a.wells, a.out, boxfit_sha(), a.workers, tuple(dt.date.fromisoformat(c) for c in a.cutoffs.split(",")), a.score_holdout)
    c = res["cells"]
    rec = c[c.variant == ac.RECORD][["stream", "horizon", "cutoff", "n_packages", "pkg_bias", "pkg_band", "bench_bias", "bench_band", "verdict"]]
    print(rec.round(3).to_string())
    print(res["summary"]["verdict"])
    print(f"wrote {a.out}  ({time.time() - t0:.0f} s)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
