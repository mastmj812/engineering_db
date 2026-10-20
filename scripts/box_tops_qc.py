"""Tops-vs-tag QC (plan ~/.claude/plans/my-geologist-has-exported-buzzing-sketch.md). READ ONLY.

    python -m scripts.box_tops_qc                 # step 1: sample both grid sets, datum check, agreement table
    python -m scripts.box_tops_qc --out docs/box/tops-qc-2026-10-20

Writes step1.html, wells_step1.csv, summary.json to --out. Grid folders come from box.extent_package
(GRID_DIR = Grids_10-19-26, ORIGINAL_GRID_DIR = Original).
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from box import tops_qc_report as rep
from etl.db import get_connection


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--out", type=Path, default=Path("docs/box/tops-qc-2026-10-20"))
    a = ap.parse_args(argv)
    sys.stdout.reconfigure(encoding="utf-8")  # type: ignore[union-attr]
    with get_connection() as conn:
        ctx = rep.run(conn, a.out)
    print(ctx["datum_verdict"])
    print(ctx["agreement"].to_string(index=False, float_format=lambda v: f"{v:.3f}"))
    print(f"wrote {a.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
