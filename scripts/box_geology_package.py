"""BOX — the geology hand-off package: every extent OF RECORD + its context layers, one folder (read-only).

    python -m scripts.box_geology_package [--out docs/box/geology-package-YYYY-MM-DD]

Reads the version of record for each bench straight from box.extent (READ ONLY transaction; the warehouse is the source
of truth) and writes it as a shapefile in the geology frame (NAD83 / UTM 14N, US-survey ft; D7), plus, per bench, the
context layers already built for its review (laterals, flags), structure / isopach contours drawn fresh from the
geology grids (--grid-dir, default the current set) around the record extent, and the potash polygon.
README.txt says what each file is and how edits come back (D28: import -> diff -> new version of record -> re-run).
"""

from __future__ import annotations

import argparse
import datetime as dt
import shutil
import sys
from pathlib import Path

import shapely

from box import edge_gap as eg
from box import extent_package as pkg
from box import geology_io as gio
from etl.db import get_connection

# where each bench's review geology package (context layers) was built
CONTEXT_DIR = {
    "WCA": "step3-2026-10-07/geology", "BS2_S": "step3-2026-10-07/geology",
    "BS3_S": "step15a-2026-10-16/extents/geology", "BS3_C": "step15a-2026-10-16/extents/geology",
    "WCB_1": "step15-WCB-2026-10-16/extents/geology", "WCB_2": "step15-WCB-2026-10-16/extents/geology",
    "BS1_S": "step15-BS1-2026-10-16/extents/geology", "WCC": "step15-WCC-2026-10-16/extents/geology",
    "BS2_C": "step15-BS2C-2026-10-16/extents/geology",
    "AVA_0": "step15-AVA-2026-10-16/extents/geology", "AVA_1": "step15-AVA-2026-10-16/extents/geology", "AVA_2": "step15-AVA-2026-10-16/extents/geology",
}
CONTEXT_LAYERS = ("laterals", "flags")  # copied from the review folder; ctx_* contours are re-drawn from --grid-dir
SHP_EXT = (".shp", ".shx", ".dbf", ".prj", ".cpg")
RECORD_FIELDS = [("BENCH", "C", 12, 0), ("BASIN", "C", 12, 0), ("EXTENT_ID", "N", 8, 0), ("VERSION", "N", 4, 0), ("SOURCE", "C", 16, 0),
                 ("AREA_SQMI", "N", 12, 2), ("RECORD_OF", "C", 10, 0), ("NOTE", "C", 254, 0)]

README = """BOX bench extents of record — geology hand-off package ({built})

Frame: NAD83 / UTM zone 14N, US-survey feet (coordinates already projected; the .prj is written from the exact
definition). Read straight from the warehouse records (box.extent, is_record) on {built}.

THE EXTENTS (edit these)
  BOX_<bench>_extent_RECORD.shp   one per bench, the version of record today:
{records}
  SOURCE = generated: built by the BOX development-envelope rule (D27) from >= 2016 laterals.
  SOURCE = geology_edited: drawn by Michael over structure + laterals (owner edit, 2026-10-16).

CONTEXT (read only — for judging the edits)
  <bench>/BOX_<bench>_laterals     every bench lateral: ROLE, TVD_FT, OIL12KFT (12-mo oil, bbl per 1,000 ft), QC_NOTE
  <bench>/BOX_<bench>_ctx_struct   your HCA structure grid of the bench top, contoured (context only, D25)
  <bench>/BOX_<bench>_ctx_isopach  bench isopach from your grids (context only)
      grids: {grids}; within 10 mi of each record extent's bounding box
  <bench>/BOX_<bench>_flags        step-out tests left out, voids/holes filled — the questions behind the edge
  BOX_potash_SOPA                  BLM Secretary's Potash Area (surface constraint, not geology)

Benches not here: WCXY (decided with step 9), Delaware WDFD and WCD (emerging, worked by hand per deal),
Midland (later phase).

HOW TO RETURN EDITS
  Edit a BOX_<bench>_extent_RECORD shape (move the edge, add or cut area; multiple parts are fine), save it as
  BOX_<bench>_extent_edited.shp (same frame), and send the set back to Michael. Each returned bench is imported,
  diffed against the record (added / removed area by side, PUDs and laterals affected), reviewed, and stored as the
  new version of record; everything downstream is re-run on it. Your edit never silently overwrites anything: the
  current record stays in the history.
"""


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--out", type=Path, default=Path("docs") / "box" / f"geology-package-{dt.datetime.now(tz=dt.UTC).astimezone():%Y-%m-%d}")
    ap.add_argument("--grid-dir", type=Path, default=pkg.GRID_DIR, help=f"structure grid folder (default {pkg.GRID_DIR.name}; September set: {pkg.ORIGINAL_GRID_DIR})")
    a = ap.parse_args(argv)
    built = dt.datetime.now(tz=dt.UTC).astimezone().isoformat(timespec="seconds")
    with get_connection() as conn, conn.cursor() as cur:
        cur.execute("SET TRANSACTION READ ONLY")
        cur.execute(
            """SELECT e.bench, e.extent_id, e.version, e.source, e.area_sqmi, extensions.ST_AsText(e.geom)
               FROM box.extent e JOIN box.bench_scope s USING (basin, bench)
               WHERE e.is_record AND s.in_scope AND e.basin = 'delaware' ORDER BY e.bench"""
        )
        rows = cur.fetchall()
        conn.rollback()
    a.out.mkdir(parents=True, exist_ok=True)
    lines = []
    for bench, eid, ver, src, area, wkt in rows:
        g13 = eg.to_ft([shapely.from_wkt(wkt)])[0]
        geo = gio.ft13_to_geology([g13])[0]
        note = "owner edit 2026-10-16" if src == "geology_edited" else "BOX D27 envelope"
        gio.write_layer(a.out / f"BOX_{bench}_extent_RECORD", "polygon", [geo], RECORD_FIELDS,
                        [[bench, "delaware", eid, ver, src, float(area), built[:10], note]])
        back = gio.read_extent(a.out / f"BOX_{bench}_extent_RECORD.shp")
        rt = gio.geology_to_ft13([back])[0]
        err = rt.symmetric_difference(g13).area / eg.FT_PER_MI**2
        if err > 0.01:
            raise RuntimeError(f"{bench}: written shapefile does not round-trip ({err:.4f} sq mi)")
        lines.append(f"    {bench:<6} extent_id {eid:<3} {src:<15} {float(area):>8,.1f} sq mi")
        sub = a.out / bench
        sub.mkdir(exist_ok=True)
        src_dir = Path("docs") / "box" / CONTEXT_DIR[bench]
        for layer in CONTEXT_LAYERS:
            for ext in SHP_EXT:
                f = src_dir / f"BOX_{bench}_{layer}{ext}"
                if f.exists():
                    shutil.copy2(f, sub / f.name)
        clip = gio.ft13_to_geology([shapely.box(*g13.bounds).buffer(10 * eg.FT_PER_MI)])[0]
        cont = pkg.context_contours(bench, clip, grid_dir=a.grid_dir)
        if not cont:
            raise RuntimeError(f"{bench}: no structure grids in {a.grid_dir}")
        pkg.write_contours(sub, bench, cont)
        n = ", ".join(f"{len(v):,} {k}" for k, v in cont.items())
        print(f"{bench}: extent_id {eid} {src} {float(area):,.1f} sq mi (round-trip {err:.5f} sq mi); contours {n}")
    from box import extent_report as er

    pkg.write_sopa(a.out, er.load_sopa())
    (a.out / "README.txt").write_text(README.format(built=built, grids=a.grid_dir.name, records="\n".join(lines)), encoding="utf-8")
    print(f"wrote {a.out} ({len(rows)} benches)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
