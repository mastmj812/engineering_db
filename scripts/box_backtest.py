"""BOX step 6 (fail branch) — rolling-origin backtest vs actuals, Novi-agnostic; lateral + density variants (read-only).

    python -m scripts.box_backtest [--wells docs/box/step1-2026-10-06] [--out docs/box/step6-2026-10-12/backtest] [--workers N]
                                   [--cutoffs 2021-12-01,2022-12-01,2023-12-01,2024-12-01]

See box/backtest_report.py (folds, variants, page) and box/backtest.py (lateral efficiency, density term).
Reads the warehouse through the ETL session pooler inside READ ONLY transactions; writes nothing to it.
"""

from __future__ import annotations

import argparse
import datetime as dt
import sys
import time
from pathlib import Path

from box import backtest_report as br
from etl.db import get_connection
from scripts.box_tc_curves import boxfit_sha


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--wells", type=Path, default=Path("docs") / "box" / "step1-2026-10-06")
    ap.add_argument("--out", type=Path, default=Path("docs") / "box" / "step6-2026-10-12" / "backtest")
    ap.add_argument("--workers", type=int, default=None)
    ap.add_argument("--cutoffs", default=",".join(str(c) for c in br.CUTOFFS))
    a = ap.parse_args(argv)
    cut = tuple(dt.date.fromisoformat(c) for c in a.cutoffs.split(","))
    t0 = time.time()
    with get_connection() as conn:
        res = br.run(conn, a.wells, a.out, boxfit_sha(), a.workers, cut)
    sc = res["scores"]
    pv = sc[sc.horizon.isin([6, 12])].pivot_table(index=["stream", "horizon", "cutoff"], columns="variant", values="bias").reindex(columns=list(br.VARIANTS))
    print((pv * 100).round(1).to_string())
    print(f"wrote {a.out}  ({time.time() - t0:.0f} s)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
