"""BOX step 15 — turn Michael's hand edits (freeforms drawn over the visual-check PNGs in a .pptx) into edited extents.

    python -m scripts.box_family_extent_edits --pptx "<path>/bs3_extents.pptx" --slide 1=BS3_C --slide 2=BS3_S
                                              [--wells docs/box/step15a-2026-10-16] [--ext docs/box/step15a-2026-10-16/extents]

Read-only (laterals + D1 PUD counts). Writes <ext>/edited/: BOX_<pool>_extent_v1_edited.shp (geology round-trip format),
diff_<pool>_v1.html (step-3 diff page), the visual check redrawn on the edited extent, and summary.json. Nothing stored.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from box import family_extent as fe
from etl.db import get_connection
from scripts.box_family_extents import _git_sha


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--pptx", type=Path, required=True)
    ap.add_argument("--slide", action="append", required=True, help="N=POOL, e.g. 1=BS3_C")
    ap.add_argument("--wells", type=Path, default=Path("docs") / "box" / "step15a-2026-10-16")
    ap.add_argument("--ext", type=Path, default=None)
    a = ap.parse_args(argv)
    sp = {int(s.split("=")[0]): s.split("=")[1] for s in a.slide}
    with get_connection() as conn:
        r = fe.run_edits(conn, a.pptx, sp, a.wells, a.ext or a.wells / "extents", git_sha=_git_sha())
    for p, s in r["pools"].items():
        print(f"{p}: generated {s['generated_sqmi']:,.0f} -> edited {s['edited_sqmi']:,.0f} sq mi (+{s['added_sqmi']:,.0f} / -{s['removed_sqmi']:,.1f}), parts {s['n_parts']}; "
              f">=2016 laterals inside {s['inside_generated']:,} -> {s['inside_edited']:,} of {s['n_evidence']:,}; D1 PUDs {s['d1_in_generated']:,} -> {s['d1_in_edited']:,}; "
              f"outside {s['outside_by_county']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
