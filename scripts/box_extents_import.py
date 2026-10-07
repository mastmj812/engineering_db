"""BOX step 3 — read geology's edited extent shapefile back, diff it against the generated version.

    python -m scripts.box_extents_import --pool BS2_S --edited <path>/BOX_BS2_S_extent_v1_edited.shp
        [--generated docs/box/step3-2026-10-07/geology/BOX_BS2_S_extent_v1.shp] [--version 1]
        [--out docs/box/step3-2026-10-07/diff] [--puds] [--store [--record]]

Both shapefiles are read as NAD83 UTM 14N US-ft whatever their .prj says (GGX may ignore it); the
script refuses if the edited layer does not sit where the generated one does (wrong CRS/units).
Writes diff_<pool>_v<N>.html (map + added/removed pieces by side) and diff_<pool>_v<N>.geojson.

--puds   read-only count of D1 PUDs inside the generated vs the edited extent (session pooler).
--store  WRITE the edited extent to box.extent as source = geology_edited (parent = the stored
         generated version); --record also makes it the version of record. Needs sql/54 applied
         (explicit go-apply) and the generated version stored, plus Michael's go-ahead.
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import sys
from pathlib import Path

from shapely.geometry import Polygon, mapping

from box import edge_gap as eg
from box import extent as ex
from box import extent_pages as pages
from box import geology_io as gio

STEP3 = Path("docs") / "box" / "step3-2026-10-07"


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--pool", required=True, choices=["WCA", "BS2_S"])
    ap.add_argument("--edited", type=Path, required=True)
    ap.add_argument("--generated", type=Path)
    ap.add_argument("--version", type=int, default=1)
    ap.add_argument("--out", type=Path, default=STEP3 / "diff")
    ap.add_argument("--puds", action="store_true")
    ap.add_argument("--store", action="store_true")
    ap.add_argument("--record", action="store_true")
    a = ap.parse_args(argv)
    gen_path = a.generated or STEP3 / "geology" / f"BOX_{a.pool}_extent_v{a.version}.shp"
    gen_g = gio.read_extent(gen_path)
    edi_g = gio.read_extent(a.edited, bench=a.pool)
    msg = gio.check_frame(edi_g, gen_g)
    if msg:
        print(f"REFUSED: {msg}")
        return 2
    gen_ft, edi_ft = gio.geology_to_ft13([gen_g, edi_g])
    gen_ft, edi_ft = ex.as_multi(gen_ft.buffer(0)), ex.as_multi(edi_ft.buffer(0))
    d = ex.diff(gen_ft, edi_ft, gen_ft.centroid)
    built = dt.datetime.now(tz=dt.UTC).astimezone().isoformat(timespec="seconds")
    puds = None
    conn = None
    if a.puds or a.store:
        from etl.db import get_connection

        conn = get_connection()
    try:
        if a.puds:
            import shapely

            from box.extent_report import MEMBERS, pud_counts, pull_puds

            env = eg.to_lonlat([shapely.box(*gen_ft.union(edi_ft).bounds).buffer(eg.FT_PER_MI)])[0].bounds
            pu = pull_puds(conn, list(MEMBERS[a.pool]) + (["WCXY"] if a.pool == "WCA" else []), env)
            puds = pud_counts(pu, {"in generated": gen_ft, "in edited": edi_ft})
        a.out.mkdir(parents=True, exist_ok=True)
        stem = a.out / f"diff_{a.pool}_v{a.version}"
        stem.with_suffix(".html").write_text(pages.diff_page(a.pool, a.version, d, gen_ft, edi_ft, built, str(a.edited), puds), encoding="utf-8")
        feats = [{"type": "Feature", "properties": {"layer": k}, "geometry": mapping(eg.to_lonlat([g])[0])} for k, g in (("generated", gen_ft), ("edited", edi_ft))]
        feats += [{"type": "Feature", "properties": {"layer": p["kind"], "area_sqmi": p["area_sqmi"], "side": p["side"]}, "geometry": mapping(eg.to_lonlat([p["geom"]])[0])} for p in d["pieces"]]
        stem.with_suffix(".geojson").write_text(json.dumps({"type": "FeatureCollection", "features": feats}), encoding="utf-8")
        print(f"{a.pool} v{a.version}: generated {d['generated_sqmi']:,.1f} sq mi, edited {d['edited_sqmi']:,.1f}; added {d['added_sqmi']:,.2f}, removed {d['removed_sqmi']:,.2f} "
              f"({len(d['pieces'])} pieces >= 0.01 sq mi) -> {stem.with_suffix('.html')}")
        if a.store:
            from box.extent_store import store_edited

            stats = {k: v for k, v in d.items() if k != "pieces"} | {"n_pieces": len(d["pieces"]), "edited_file": str(a.edited)}
            eid = store_edited(conn, a.pool, a.version, edi_ft if not isinstance(edi_ft, Polygon) else ex.as_multi(edi_ft), stats, a.record)
            print(f"stored geology_edited {a.pool} v{a.version} as extent_id {eid}{' (version of record)' if a.record else ''}")
    finally:
        if conn is not None:
            conn.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
