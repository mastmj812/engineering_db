"""BOX step 1b — consensus-flag calibration cards (read-only).

    python -m scripts.box_flag_cards [--out docs/box/step1-YYYY-MM-DD]
    python -m scripts.box_flag_cards --only-class BS2_S->BS1_S BS2_S->BS3_S \
        --exclude-from docs/box/step1-2026-10-06/cards_sample.csv --stem cards_round2 \
        --title "BOX step 1 — hold-class second sample"

Re-pulls and re-scores the Delaware producing horizontals (box.bench_qc) and
writes <stem>.html + <stem>_sample.csv + <stem>_summary.json (and flags_all.csv
for the default stem) into the step-1 folder. ``--only-class`` restricts to
those pooled swap classes; ``--exclude-from`` drops api10s already carded so a
second sample is disjoint. Nothing is written to the warehouse.
"""

from __future__ import annotations

import argparse
import datetime as dt
import sys
import time
from pathlib import Path

import pandas as pd

from box.bench_qc import PILOT_BENCHES, pull_delaware_producers, score_consensus
from box.flag_cards import build
from etl.db import get_connection


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--out", type=Path, default=Path("docs") / "box" / f"step1-{dt.datetime.now(tz=dt.UTC).astimezone():%Y-%m-%d}")
    ap.add_argument("--bench", nargs="*", default=list(PILOT_BENCHES))
    ap.add_argument("--only-class", nargs="*", default=None, help="pooled swap classes to card, e.g. BS2_S->BS1_S")
    ap.add_argument("--exclude-from", type=Path, action="append", default=[], help="CSV(s) with an api10 column to exclude (earlier samples)")
    ap.add_argument("--stem", default="cards")
    ap.add_argument("--title", default="BOX step 1 — consensus-flag calibration cards")
    a = ap.parse_args(argv)
    t0 = time.time()
    exclude: set[str] = set()
    for pth in a.exclude_from:
        exclude |= set(pd.read_csv(pth, dtype={"api10": str})["api10"])
    with get_connection() as conn:
        df = score_consensus(pull_delaware_producers(conn))
    s = build(df, a.out, tuple(a.bench), only_classes=tuple(a.only_class) if a.only_class else None,
              exclude_api10=exclude or None, stem=a.stem, title=a.title)
    print(f"flags in carded classes {s['n_flags_carded_classes']:,} | cards {s['n_cards']} | excluded {len(exclude)}")
    for c, n in s["classes"].items():
        print(f"  {c:>14}: {n}")
    print(f"wrote {a.out / (a.stem + '.html')}  ({time.time() - t0:.0f} s)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
