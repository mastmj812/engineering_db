"""BOX step 13d — the 13-group r2 prospective test (box/prospective16.py). Read-only.

    python -m scripts.box_prospective16 snapshot   once, at the freeze: cohort_at_freeze.csv (identities + tags, NO volumes) and
                                                   tuning_views.sha256 (the 16c tuning views the verdict intervals come from)
    python -m scripts.box_prospective16 status     cohort per group now (identities only) + when each horizon is judged
    python -m scripts.box_prospective16 score      refuses: not built. The scorer is written and committed BEFORE its one run,
                                                   and is first checked on a past cutoff (2024-12-01 must reproduce the 16c cells)

Nothing here reads a 2026 well's production volume. The definition is digest-pinned; every command refuses if it moved.
"""

from __future__ import annotations

import argparse
import csv
import datetime as dt
import sys
from collections import Counter
from pathlib import Path

from box import prospective16 as p16
from etl.db import get_connection

COHORT_FILE = p16.DOCS / "cohort_at_freeze.csv"
VIEWS_FILE = p16.DOCS / "tuning_views.sha256"


def _guard() -> None:
    if p16.digest() != p16.DIGEST:
        raise SystemExit(f"box/prospective16.py DEFINITION changed after the freeze (digest {p16.digest()[:12]} != pinned {p16.DIGEST[:12]})")


def _views(root: Path) -> list[Path]:
    """The tuning views each group's evidence was built from (WCA: the full fold, as run 19's evidence pack)."""
    out = []
    for g in p16.GROUPS:
        d = root / ("WCA_full" if g == "WCA" else g)
        files = sorted(d.glob("view_tuning_v2_*.csv.gz"))
        if not files:
            raise SystemExit(f"no tuning views under {d}")
        out += files
    return out


def snapshot(runs_root: Path) -> int:
    _guard()
    if COHORT_FILE.exists() or VIEWS_FILE.exists():
        raise SystemExit(f"{p16.DOCS} already holds a freeze snapshot; it is written once")
    p16.DOCS.mkdir(parents=True, exist_ok=True)
    rows = []
    with get_connection() as conn:
        for g in p16.GROUPS:
            rows += [(g, *r) for r in p16.cohort(conn, g)]
    with open(COHORT_FILE, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f, lineterminator="\n")
        w.writerow(["group", "api10", "formation_blueox", "first_production_date", "state_code"])
        w.writerows(rows)
    lines = [f"{p16.sha256_file(v)}  {v.relative_to(runs_root.parent).as_posix()}" for v in _views(runs_root)]
    VIEWS_FILE.write_bytes(("\n".join(lines) + "\n").encode("utf-8"))
    print(f"wrote {COHORT_FILE} ({len(rows)} wells) and {VIEWS_FILE} ({len(lines)} views); definition digest {p16.DIGEST[:12]}")
    return 0


def status() -> int:
    _guard()
    print(f"definition {p16.DEFINITION['name']} · digest {p16.DIGEST[:12]} · cutoff {p16.DEFINITION['cutoff']} · as of {dt.datetime.now(tz=dt.UTC).date()}")
    tot = Counter()
    with get_connection() as conn:
        for g, (_, ext, tier) in p16.GROUPS.items():
            rows = p16.cohort(conn, g)
            tot[tier] += len(rows)
            print(f"  {g:10s} {tier:11s} extent {ext:2d}  wells {len(rows):4d}")
    print(f"  total {sum(tot.values())} (validated {tot['validated']}, provisional {tot['provisional']}); packages <= wells")
    for k, v in p16.DEFINITION["schedule"].items():
        print(f"  {k}: {v}")
    return 0


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("cmd", choices=("snapshot", "status", "score"))
    ap.add_argument("--runs", type=Path, default=p16.TUNING_RUNS, help="the 16c tuning runs root (default runs/step16c)")
    a = ap.parse_args(argv)
    if a.cmd == "snapshot":
        return snapshot(a.runs)
    if a.cmd == "status":
        return status()
    _guard()
    raise SystemExit("score is not built yet: cum-12 is judged once, with production through >= 2028-01-01 (PREREGISTRATION §5)")


if __name__ == "__main__":
    sys.exit(main())
