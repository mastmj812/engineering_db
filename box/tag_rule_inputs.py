"""Live inputs for the tag rule, vendor-only (read-only) — docs/formation_tag_redesign/WAREHOUSE_STEP.md, W1.

    python -m box.tag_rule_inputs --cache <dir>

Writes the cache the rule chain reads (wells.pkl, stations.pkl, vendors.pkl, extents.pkl) in the schema the Nov 5
snapshot used, but every DECISION input comes from vendor-side objects:
- curated.wells: vendor strings (Novi `formation`, Enverus `env_interval`), basin keys, depths, geometry, slant;
- curated.well_lateral_survey: survey depth and stations;
- ref.formation_crosswalk and ref.formation_tag_overrides (human calls);
- box.extent (record extents; reporting only).

Nothing tag-derived is read from formation_blueox / formation_blueox_tvd / wells_enriched, because once the rule lands it
feeds them (a feedback loop). sql/16's vendor resolution is reproduced here (`basin`, `vendor_raw`, `vendor`) and
`pre_sql23` = human call, else vendor — exactly sql/16's output today. `check_identity` asserts that against live.

Today's warehouse tag (`live`, `live_source`, `sql23_corrected`) is joined from wells_enriched as REPORT-ONLY columns:
the review classes were written against it, and the W1 report compares with it. W2 removes the remaining decision uses.
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path
from typing import Any

import pandas as pd

from box import tag_scoreboard as sb

# sql/16's coarse Novi values (defer to Enverus ENVInterval). Must match sql/16 exactly; check_identity catches drift.
SQL16_TRIGGERS = ("WOLFCAMP A", "WOLFCAMP A (XY)", "WOLFCAMP A (XY) SHELF", "WOLFCAMP B", "LOWER SPRABERRY SAND", "WOLFCAMP",
                  "BONE SPRING", "BONE SPRINGS", "SPRABERRY", "UNKNOWN", "SUB-WOODFORD")

_VENDOR_CTE = """
WITH b AS (
    SELECT w.*,
           CASE WHEN w.subbasin ILIKE '%%delaware%%'      THEN 'delaware'
                WHEN w.subbasin ILIKE '%%midland%%'       THEN 'midland'
                WHEN w.subbasin ILIKE '%%central basin%%' THEN 'cbp'
                WHEN w.env_basin = 'DELAWARE'             THEN 'delaware'
                WHEN w.env_basin = 'MIDLAND'              THEN 'midland' END AS basin_token,
           (w.formation = ANY(%(trig)s)) AS is_trigger,
           CASE WHEN COALESCE(w.novi_slant_calculated, w.enverus_trajectory) ILIKE '%%horizontal%%' THEN TRUE
                WHEN COALESCE(w.novi_slant_calculated, w.enverus_trajectory) IS NULL THEN NULL
                ELSE FALSE END AS is_horiz
    FROM curated.wells w
), v AS (
    SELECT b.*,
           CASE WHEN b.is_trigger THEN COALESCE(b.env_interval, b.formation)
                ELSE COALESCE(b.formation, b.env_interval) END AS raw_value
    FROM b
)
"""

WELLS_SQL = _VENDOR_CTE + """
SELECT v.api10, v.basin_token AS basin, v.state_code, v.county, v.current_operator AS operator, v.well_name,
       e.formation_blueox AS live,                                   -- REPORT ONLY
       COALESCE(o.corrected_code, fx.canonical_code) AS pre_sql23,  -- sql/16 today: human call, else vendor
       fx.canonical_code AS vendor, v.raw_value AS vendor_raw,
       e.formation_blueox_source AS live_source,                     -- REPORT ONLY
       e.formation_blueox_tvd_corrected AS sql23_corrected,          -- REPORT ONLY
       v.directional_survey_is_planned AS planned, v.tvd_ft, s.lat_tvd_p50_ft,
       v.first_production_date, v.lateral_length_ft, v.midpoint_lon, v.midpoint_lat,
       CASE WHEN extensions.ST_GeometryType(v.wellstick_geom) = 'ST_LineString'
            THEN extensions.ST_AsText(extensions.ST_LineInterpolatePoints(
                     extensions.ST_Transform(v.wellstick_geom, 3083), %(frac)s, true)) END AS pts_wkt,
       CASE WHEN v.midpoint_lon IS NOT NULL THEN extensions.ST_AsText(extensions.ST_Transform(
                 extensions.ST_SetSRID(extensions.ST_MakePoint(v.midpoint_lon, v.midpoint_lat), 4326), 3083)) END AS mid_wkt,
       v.formation AS novi_raw, v.env_interval AS env_raw, fn.canonical_code AS novi_code, fe.canonical_code AS env_code
FROM v
LEFT JOIN ref.formation_crosswalk fx ON fx.basin = v.basin_token AND fx.raw_value = v.raw_value
LEFT JOIN ref.formation_crosswalk fn ON fn.basin = v.basin_token AND fn.raw_value = v.formation
LEFT JOIN ref.formation_crosswalk fe ON fe.basin = v.basin_token AND fe.raw_value = v.env_interval
LEFT JOIN ref.formation_tag_overrides o ON o.api10 = v.api10
LEFT JOIN curated.well_lateral_survey s ON s.api10 = v.api10
LEFT JOIN curated.wells_enriched e ON e.api10 = v.api10
WHERE v.basin_token IN ('delaware', 'midland')
  AND v.is_horiz
  AND v.first_production_date IS NOT NULL
"""

EXTENTS_SQL = """
SELECT extent_id, basin, bench, area_sqmi, extensions.ST_AsText(extensions.ST_Transform(geom, 3083)) AS wkt
FROM box.extent WHERE is_record ORDER BY basin, bench
"""

# sql/16's own output for the same wells: must equal pre_sql23 row for row (and the frame must equal the live frame).
IDENTITY_SQL = """
SELECT e.api10, e.formation_blueox_base AS sql16
FROM curated.wells_enriched e
WHERE e.basin_blueox IN ('delaware', 'midland') AND e.is_horizontal AND e.first_production_date IS NOT NULL
"""

VENDOR_COLS = ["api10", "novi_raw", "env_raw", "basin", "novi_code", "env_code"]

# Survey stations (the dev scoreboard's cache; the rule itself never reads them).
STATIONS_SQL = """
SELECT s.api10, (s.dp).path[1] AS i,
       extensions.ST_X((s.dp).geom) AS lon, extensions.ST_Y((s.dp).geom) AS lat, extensions.ST_Z((s.dp).geom) AS tvd,
       s.kb_elev_ft
FROM (SELECT api10, kb_elev_ft, extensions.ST_DumpPoints(lateral_geom) AS dp
      FROM curated.well_lateral_survey
      WHERE api10 = ANY(%(a)s) AND lateral_geom IS NOT NULL) s
"""


def _read(conn: Any, sql: str, params: dict[str, Any]) -> pd.DataFrame:
    """One read-only transaction (box.tops_qc_report's pattern, without its plotting imports)."""
    with conn.cursor() as cur:
        cur.execute("SET TRANSACTION READ ONLY")
        cur.execute(sql, params)
        cols = [c.name for c in cur.description]
        rows = cur.fetchall()
    conn.rollback()
    return pd.DataFrame(rows, columns=cols)


def pull(conn: Any, stations: bool = True) -> dict[str, pd.DataFrame]:
    d = _read(conn, WELLS_SQL, {"frac": 1.0 / sb.NPTS, "trig": list(SQL16_TRIGGERS)})
    for c in ("tvd_ft", "lat_tvd_p50_ft", "lateral_length_ft", "midpoint_lon", "midpoint_lat"):
        d[c] = pd.to_numeric(d[c], errors="coerce")
    d["api10"] = d["api10"].astype(str)
    d["sql23_corrected"] = d["sql23_corrected"].fillna(False).astype(bool)
    mids = [sb.parse_points(m) for m in d["mid_wkt"]]
    d["pts"] = [sb.parse_points(w, m[0] if m else None) for w, m in zip(d["pts_wkt"], mids, strict=True)]
    vendors = d[VENDOR_COLS].copy()
    wells = d.drop(columns=["pts_wkt", "mid_wkt", "novi_raw", "env_raw", "novi_code", "env_code"])
    st = pd.DataFrame(columns=["api10", "i", "lon", "lat", "tvd", "kb_elev_ft"])
    if stations:
        ids = wells.loc[(wells["basin"] == "delaware") & wells["lat_tvd_p50_ft"].notna(), "api10"].tolist()
        st = _read(conn, STATIONS_SQL, {"a": ids})
        for c in ("lon", "lat", "tvd"):
            st[c] = pd.to_numeric(st[c], errors="coerce")
        st["api10"] = st["api10"].astype(str)
    ex = _read(conn, EXTENTS_SQL, {})
    ex["area_sqmi"] = ex["area_sqmi"].astype(float)
    ident = _read(conn, IDENTITY_SQL, {}).assign(api10=lambda x: x["api10"].astype(str))
    return {"wells": wells, "stations": st, "vendors": vendors, "extents": ex, "identity": ident}


def check_identity(wells: pd.DataFrame, ident: pd.DataFrame) -> dict[str, int]:
    """The vendor-only frame must be today's frame (same wells) and pre_sql23 must be sql/16's code on every well."""
    m = wells[["api10", "pre_sql23"]].merge(ident, on="api10", how="outer", indicator=True)
    both = m[m["_merge"] == "both"]
    differ = both["pre_sql23"].fillna("~") != both["sql16"].fillna("~")
    return {"wells": len(wells), "only_vendor_frame": int((m["_merge"] == "left_only").sum()),
            "only_enriched_frame": int((m["_merge"] == "right_only").sum()), "pre_sql23_differs_from_sql16": int(differ.sum())}


def run(cache: Path) -> dict[str, Any]:
    from etl.db import get_connection

    t0 = time.time()
    with get_connection() as conn:
        p = pull(conn)
    cache.mkdir(parents=True, exist_ok=True)
    for k in ("wells", "stations", "vendors", "extents"):
        p[k].to_pickle(cache / f"{k}.pkl")
    s = {"identity": check_identity(p["wells"], p["identity"]), "stations": len(p["stations"]), "extents": len(p["extents"]),
         "pulled_seconds": round(time.time() - t0, 1)}
    (cache / "pull.json").write_text(json.dumps(s, indent=1), encoding="utf-8")
    return s


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--cache", type=Path, required=True)
    s = run(ap.parse_args(argv).cache)
    print(json.dumps(s, indent=1))
    i = s["identity"]
    return 0 if i["only_vendor_frame"] == i["only_enriched_frame"] == i["pre_sql23_differs_from_sql16"] == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
