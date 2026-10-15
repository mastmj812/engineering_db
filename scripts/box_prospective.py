"""BOX prospective confirmation (D59 condition 1, D70) — the frozen 2026 cohort.

    python -m scripts.box_prospective status     read-only: cohort size now, months reported, when each horizon can be judged
    python -m scripts.box_prospective score      the one scoring of the frozen definition (box/prospective.py)

The definition is frozen and digest-pinned in box/prospective.py; this script refuses to run if the digest does not match.
`score` is deliberately not built yet: the earliest judged horizon (cum-12) needs >= 30 packages with 12 reported months, which
the 2026 cohort cannot reach before ~2027-Q2. It will run the D53 harness at the frozen cutoff with the D62 factors as delivered.
"""

from __future__ import annotations

import argparse
import datetime as dt
import sys
from collections import Counter

from box import prospective as ps
from etl.db import get_connection


def _guard() -> None:
    if ps.digest() != ps.DIGEST:
        raise SystemExit(f"box/prospective.py DEFINITION changed after the freeze (digest {ps.digest()[:12]} != pinned {ps.DIGEST[:12]})")


def status() -> int:
    _guard()
    with get_connection() as conn:
        rows = ps.cohort(conn)
    print(f"frozen {ps.DEFINITION['frozen_on']} · digest {ps.DIGEST[:12]} · cutoff {ps.DEFINITION['cutoff']} · as of {dt.datetime.now(tz=dt.UTC).date()}")
    print(f"cohort wells first-producing 2026 inside extent {ps.DEFINITION['cohort']['midpoint_inside_extent_id']}: {len(rows)}")
    by_form = Counter(r[1] for r in rows)
    print("  by formation: " + ", ".join(f"{k} {v}" for k, v in sorted(by_form.items())))
    for k in (6, *ps.DEFINITION["verdict"]["horizons_judged"]):
        n = sum(1 for r in rows if (r[4] or 0) >= k + 1)  # newest month dropped as in the harness
        tag = "reported" if k in ps.DEFINITION["verdict"]["horizons_reported"] else "judged at >= 30 packages"
        print(f"  cum-{k} ({tag}): {n} wells with >= {k + 1} reported months")
    return 0


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("cmd", choices=("status", "score"))
    a = ap.parse_args(argv)
    if a.cmd == "status":
        return status()
    _guard()
    raise SystemExit("score is not built yet: no judged horizon can have >= 30 packages before ~2027-Q2 (see the module docstring)")


if __name__ == "__main__":
    sys.exit(main())
