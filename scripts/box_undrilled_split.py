"""BOX step 20 — undrilled Novi sticks inside vs outside each bench's extent, basin-wide (read-only).

    python -m scripts.box_undrilled_split --basin midland --out docs/box/step20b-YYYY-MM-DD/undrilled_split.csv \
        MS=<extents>/extent_MS_v1.geojson JM=... LSSH=... DEAN=... --no-extent US

The extent pages count sticks inside a box around each extent; this counts the bench's whole basin universe. Undrilled =
D117 (Novi PUD + RES; remaining_pud / conflict / not yet reconciled), inside = >= 50 % of the stick in the extent (rule 9),
the same test as box/extent_report.undrilled_counts. A bench listed under --no-extent (D2 emerging) has every stick outside:
it shows as not covered, never zero. Nothing is written to the warehouse.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import pandas as pd
from shapely.geometry import shape

from box import edge_gap as eg
from box import extent_report as er
from etl.db import get_connection

WORLD = (-180.0, -90.0, 180.0, 90.0)


def extent_ft(path: Path) -> object:
    gj = json.loads(path.read_text(encoding="utf-8"))
    feat = next(x for x in gj["features"] if x["properties"].get("layer", "extent") == "extent")
    return eg.to_ft([shape(feat["geometry"])])[0]


def split(conn: object, basin: str, extents: dict[str, object], no_extent: list[str]) -> pd.DataFrame:
    rows = []
    for bench in [*extents, *no_extent]:
        sticks = er.pull_sticks(conn, [bench], WORLD, basin)
        polys = {"inside": extents[bench]} if bench in extents else {}
        t = er.undrilled_counts(sticks, polys)
        if t.empty:
            rows.append({"bench": bench, "category": "PUD + RES", "undrilled": 0, "inside": 0, "outside": 0})
            continue
        u = t[t["status"].isin(["undrilled (D117)", "undrilled by category"])]
        for _, r in u.iterrows():
            inside = int(r["inside"]) if "inside" in r else 0
            rows.append({"bench": bench, "category": r["category"], "undrilled": int(r["n"]), "inside": inside, "outside": int(r["n"]) - inside})
    d = pd.DataFrame(rows)
    d["share_inside"] = (d["inside"] / d["undrilled"]).where(d["undrilled"] > 0)
    d["extent"] = d["bench"].map(lambda b: "D27 extent (proposed)" if b in extents else "none: D2 emerging, not covered")
    return d


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--basin", required=True)
    ap.add_argument("--out", type=Path, required=True)
    ap.add_argument("items", nargs="*", help="BENCH=<extent geojson>")
    ap.add_argument("--no-extent", nargs="*", default=[])
    a = ap.parse_args(argv)
    extents = {b: extent_ft(Path(p)) for b, p in (i.split("=", 1) for i in a.items)}
    with get_connection() as conn:
        d = split(conn, a.basin, extents, a.no_extent)
    a.out.parent.mkdir(parents=True, exist_ok=True)
    d.to_csv(a.out, index=False)
    print(d.to_string(index=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
