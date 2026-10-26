"""BOX step 15 — turn Michael's hand edits (freeforms drawn over the visual-check PNGs in a .pptx) into edited extents.

    python -m scripts.box_family_extent_edits --pptx "<path>/bs3_extents.pptx" --slide 1=BS3_C --slide 2=BS3_S
                                              [--wells docs/box/step15a-2026-10-16] [--ext docs/box/step15a-2026-10-16/extents]

Read-only (laterals + D1 PUD counts). Writes <ext>/edited/: BOX_<pool>_extent_v1_edited.shp (geology round-trip format),
diff_<pool>_v1.html (step-3 diff page), the visual check redrawn on the edited extent, and summary.json. Nothing stored.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from box import family_extent as fe
from etl.db import get_connection
from scripts.box_family_extents import _git_sha


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--pptx", type=Path, required=True)
    ap.add_argument("--slide", action="append", default=None, help="N=POOL, e.g. 1=BS3_C")
    ap.add_argument("--manifest", type=Path, default=None, help="<deck>.manifest.json from scripts.box_extent_pptx (slide -> bench + extents dir)")
    ap.add_argument("--wells", type=Path, default=Path("docs") / "box" / "step15a-2026-10-16")
    ap.add_argument("--ext", type=Path, default=None)
    ap.add_argument("--basin", default="delaware", help="the basin of the edited extents (step 20a: midland)")
    a = ap.parse_args(argv)
    jobs: list[tuple[dict[int, str], Path, Path]] = []
    if a.manifest is not None:
        m = json.loads(a.manifest.read_text(encoding="utf-8"))["slides"]
        by_dir: dict[str, dict[int, str]] = {}
        for k, v in m.items():
            by_dir.setdefault(v["extents_dir"], {})[int(k)] = v["bench"]
        jobs = [(sp, Path(d).parent, Path(d)) for d, sp in by_dir.items()]
    else:
        jobs = [({int(s.split("=")[0]): s.split("=")[1] for s in a.slide}, a.wells, a.ext or a.wells / "extents")]
    pools: dict[str, dict] = {}
    with get_connection() as conn:
        for sp, wells, ext in jobs:
            pools |= fe.run_edits(conn, a.pptx, sp, wells, ext, git_sha=_git_sha(), basin=a.basin)["pools"]
    for p, s in pools.items():
        print(f"{p}: generated {s['generated_sqmi']:,.0f} -> edited {s['edited_sqmi']:,.0f} sq mi (+{s['added_sqmi']:,.0f} / -{s['removed_sqmi']:,.1f}), parts {s['n_parts']}; "
              f">=2016 laterals inside {s['inside_generated']:,} -> {s['inside_edited']:,} of {s['n_evidence']:,}; D1 PUDs {s['d1_in_generated']:,} -> {s['d1_in_edited']:,}; "
              f"outside {s['outside_by_county']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
