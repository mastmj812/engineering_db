"""BOX step 4 — write TC areas to box.tc_area (sql/57).

WAREHOUSE WRITES. Only called by scripts/box_tc_areas.py --store, after sql/57 has been applied
(explicit go-apply) and with Michael's go-ahead for the write itself. Session pooler (5432) like the
other batch jobs. The stored set is checked by identity before commit: one row per area, and the
areas tile the extent of record (area within 0.1 %).
"""

from __future__ import annotations

import json
from typing import Any

from box import edge_gap as eg
from box.extent_store import _clean

TILE_TOL = 0.001


def store_areas(conn: Any, res: dict[str, Any], version: int, make_record: bool = False) -> int:
    ext, s, summ = res["extent"], res["stats"], res["summary"]
    geoms = res["r"]["geoms"]
    params = {"method": "contiguity-constrained Ward, 1-mi hex cells, log 12-mo oil/ft", **summ["params"], "pick": summ["pick"],
              "cv_r2_pick": summ["cv_r2_pick"], "cv_r2_k1": summ["cv_r2_k1"], "knn_local_cv_r2": summ["knn_local_cv_r2"],
              "well_set": "docs/box/step1-2026-10-06/wells_final_WCA.csv minus docs/box/exclusions.csv",
              "excluded_api10": summ["excluded_api10"], "data_asof": summ["asof"]}
    rows = []
    for g, r in zip(eg.to_lonlat(geoms), s.to_dict("records")):
        stats = {k: v for k, v in r.items() if k not in ("area_no", "area_sqmi", "n12")}
        rows.append((ext["extent_id"], version, int(r["area_no"]), g.wkt, float(r["area_sqmi"]), int(r["n12"]),
                     json.dumps(_clean(stats)), json.dumps(_clean(params)), summ["built_at"]))
    with conn.cursor() as cur:
        cur.executemany(
            """INSERT INTO box.tc_area (extent_id, version, area_no, geom, area_sqmi, n_wells, cohort_stats, params, generated_from_run)
               VALUES (%s, %s, %s, extensions.ST_Multi(extensions.ST_GeomFromText(%s, 4326)), %s, %s, %s, %s, %s)""",
            rows,
        )
        n, a = cur.execute(
            """SELECT count(*), sum(extensions.ST_Area(geom::extensions.geography)) FROM box.tc_area WHERE extent_id = %s AND version = %s""",
            (ext["extent_id"], version),
        ).fetchone()
        ea = cur.execute("SELECT extensions.ST_Area(geom::extensions.geography) FROM box.extent WHERE extent_id = %s", (ext["extent_id"],)).fetchone()[0]
        if int(n) != len(rows) or abs(float(a) / float(ea) - 1.0) > TILE_TOL:
            conn.rollback()
            raise RuntimeError(f"identity check failed: {n} rows vs {len(rows)} areas; area ratio {float(a) / float(ea):.5f} (tolerance {TILE_TOL})")
        if make_record:
            cur.execute("UPDATE box.tc_area SET is_record = false WHERE extent_id = %s AND is_record", (ext["extent_id"],))
            cur.execute("UPDATE box.tc_area SET is_record = true WHERE extent_id = %s AND version = %s", (ext["extent_id"], version))
    conn.commit()
    return len(rows)
