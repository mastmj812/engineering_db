"""BOX step 6 — hindcast vs Novi 2025Q3 (acceptance): rebuild steps 4-5 at the cutoff, score the holdout (read-only).

    python -m scripts.box_hindcast [--wells docs/box/step1-2026-10-06] [--out docs/box/step6-YYYY-MM-DD] [--workers N] [--asof YYYY-MM-DD]

Rebuilds the WCA TC areas, area curves, risk factors and the D36 calendar factor from wells first-producing
before the 2025Q3 recognition cliff with production through --asof (default 2025-06-01), predicts every
sql/43 2025Q3 holdout well in the gate-1 WCA set, and scores BOX vs Novi under plan §8 + D48 + D49.
Reads the warehouse through the ETL session pooler inside READ ONLY transactions; writes nothing to it.
See box/hindcast.py (prediction, statistics, verdict) and box/hindcast_report.py (rebuild + page).
"""

from __future__ import annotations

import argparse
import datetime as dt
import sys
import time
from pathlib import Path

from box import hindcast_report as hr
from etl.db import get_connection
from scripts.box_tc_curves import boxfit_sha


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--wells", type=Path, default=Path("docs") / "box" / "step1-2026-10-06")
    ap.add_argument("--out", type=Path, default=Path("docs") / "box" / f"step6-{dt.datetime.now(tz=dt.UTC).astimezone():%Y-%m-%d}")
    ap.add_argument("--workers", type=int, default=None)
    ap.add_argument("--asof", type=dt.date.fromisoformat, default=hr.PROD_ASOF, help="last production month BOX may see")
    a = ap.parse_args(argv)
    t0 = time.time()
    with get_connection() as conn:
        res = hr.run(conn, a.wells, a.out, boxfit_sha(), a.workers, a.asof)
    s = res["summary"]
    v = s["verdict"]
    sys.stdout.reconfigure(errors="replace")  # type: ignore[union-attr]
    print(f"hindcast areas k = {s['areas']['k']} (record {s['areas']['record_k']}); F(k) oil {s['F']['oil']}; gas {s['F']['gas']}")
    for c in v["cells"]:
        b, ar = c["bench"], c["area"]
        print(f"  {c['stream']} cum-{c['horizon']}: area {ar['verdict']} ({ar['n_pass']}/{ar['n_qualifying']}), bench {b['verdict']} "
              f"(n {int(b['n'])}, BOX {b['box_bias']:+.1%} / band {b['box_band']:.2f} vs Novi {b['novi_bias']:+.1%} / {b['novi_band']:.2f})")
    print(f"VERDICT {v['overall']} (oil {v['by_stream']['oil']}, gas {v['by_stream']['gas']})")
    print(f"wrote {a.out}  ({time.time() - t0:.0f} s)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
