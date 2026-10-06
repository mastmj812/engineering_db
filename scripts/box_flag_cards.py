"""BOX step 1b — consensus-flag calibration cards (read-only).

    python -m scripts.box_flag_cards [--out docs/box/step1-YYYY-MM-DD]

Re-pulls and re-scores the Delaware producing horizontals (box.bench_qc) and
writes cards.html + cards_sample.csv + flags_all.csv + cards_summary.json into
the step-1 folder. Nothing is written to the warehouse.
"""

from __future__ import annotations

import argparse
import datetime as dt
import sys
import time
from pathlib import Path

from box.bench_qc import PILOT_BENCHES, pull_delaware_producers, score_consensus
from box.flag_cards import build
from etl.db import get_connection


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--out", type=Path, default=Path("docs") / "box" / f"step1-{dt.datetime.now(tz=dt.UTC).astimezone():%Y-%m-%d}")
    ap.add_argument("--bench", nargs="*", default=list(PILOT_BENCHES))
    a = ap.parse_args(argv)
    t0 = time.time()
    with get_connection() as conn:
        df = score_consensus(pull_delaware_producers(conn))
    s = build(df, a.out, tuple(a.bench))
    print(f"flags in carded classes {s['n_flags_carded_classes']:,} | cards {s['n_cards']}")
    for c, n in s["classes"].items():
        print(f"  {c:>14}: {n}")
    print(f"wrote {a.out / 'cards.html'}  ({time.time() - t0:.0f} s)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
