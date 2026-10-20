"""Tops-vs-tag QC (plan ~/.claude/plans/my-geologist-has-exported-buzzing-sketch.md). READ ONLY.

    python -m scripts.box_tops_qc                 # step 1: sample both grid sets, datum check, agreement table
    python -m scripts.box_tops_qc --step 2        # step 2: classify, attribute, per-bench maps, GGX package
    python -m scripts.box_tops_qc --step 3        # step 3: landing position around each interface, candidate splits
    python -m scripts.box_tops_qc --out docs/box/tops-qc-2026-10-20

Step 1 writes step1.html, wells_step1.csv, summary.json; step 2 writes step2*.html, wells_step2.csv, ggx/, summary_step2.json. Grid folders come from box.extent_package
(GRID_DIR = Grids_10-19-26, ORIGINAL_GRID_DIR = Original).
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from box import tops_qc_report as rep
from box import tops_qc_step2 as rep2
from box import tops_qc_step3 as rep3
from etl.db import get_connection


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--out", type=Path, default=Path("docs/box/tops-qc-2026-10-20"))
    ap.add_argument("--step", type=int, choices=(1, 2, 3), default=1)
    a = ap.parse_args(argv)
    sys.stdout.reconfigure(encoding="utf-8")  # type: ignore[union-attr]
    if a.step == 3:
        with get_connection() as conn:
            r = rep3.run(conn, a.out)
        print(r["splits"].to_string(index=False, float_format=lambda v: f"{v:.2f}"))
        print(f"wrote {a.out}")
        return 0
    if a.step == 2:
        with get_connection() as conn:
            r = rep2.run(conn, a.out)
        for k in ("classes", "sensitivity", "offsets"):
            print(r[k].to_string(index=False, float_format=lambda v: f"{v:.3f}"))
        print(f"wrote {a.out}")
        return 0
    with get_connection() as conn:
        ctx = rep.run(conn, a.out)
    print(ctx["datum_verdict"])
    print(ctx["agreement"].to_string(index=False, float_format=lambda v: f"{v:.3f}"))
    print(f"wrote {a.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
