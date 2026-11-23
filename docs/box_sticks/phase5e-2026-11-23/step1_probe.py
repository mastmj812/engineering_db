"""Phase 5e step 1, read-only: can erebor's own connection read the BOX stick tables, and how do the preview queries run?
Run from erebor/backend with erebor's venv: uses app.db.engine (READ ONLY transaction, 300 s timeout, transaction pooler)."""
import json
import math
import re
import time

from sqlalchemy import text

from app.db import engine

TABLES = ("box.location_stick", "box.location_set", "curated.box_location_status")

TILE = """
WITH bounds AS (SELECT ST_TileEnvelope(:z, :x, :y) AS env)
, mvtgeom AS (
  SELECT k.location_id AS stick_id, k.formation_blueox, k.pad_id, k.well_type, k.target_tvd_ft, k.tvd_rung, k.tvd_err_median_ft,
         k.spacing_ft, k.completed_lateral_ft, array_to_string(k.flags, ',') AS flags,
         s.status, s.crowded, s.matched_api10,
         ST_AsMVTGeom(ST_Transform(k.legs_geom, 3857), (SELECT env FROM bounds), 4096, 64, true) AS geom
  FROM box.location_stick k
  JOIN box.location_set t ON t.set_id = k.set_id AND t.is_record AND t.basin = :basin
  LEFT JOIN curated.box_location_status s ON s.location_id = k.location_id AND s.set_id = k.set_id
  WHERE ST_Intersects(k.legs_geom, ST_Transform((SELECT env FROM bounds), 4326))
)
SELECT ST_AsMVT(mvtgeom.*, 'box_sticks', 4096, 'geom') FROM mvtgeom WHERE geom IS NOT NULL
"""

GUN = """
SELECT k.location_id AS stick_id, k.formation_blueox, k.pad_id, k.target_tvd_ft AS tvd, k.tvd_rung, k.completed_lateral_ft AS ll_ft,
       s.status, s.crowded, s.matched_api10, g.path[1] AS leg_no,
       ST_X(ST_LineInterpolatePoint(g.geom, 0.5)) AS mx, ST_Y(ST_LineInterpolatePoint(g.geom, 0.5)) AS my,
       ST_X(ST_StartPoint(g.geom)) AS sx, ST_Y(ST_StartPoint(g.geom)) AS sy, ST_X(ST_EndPoint(g.geom)) AS ex, ST_Y(ST_EndPoint(g.geom)) AS ey
FROM box.location_stick k
JOIN box.location_set t ON t.set_id = k.set_id AND t.is_record AND t.basin = :basin
LEFT JOIN curated.box_location_status s ON s.location_id = k.location_id AND s.set_id = k.set_id
CROSS JOIN LATERAL ST_Dump(k.legs_geom) g
WHERE ST_Intersects(k.legs_geom, ST_SetSRID(ST_GeomFromGeoJSON(:aoi), 4326))
"""


def tile_xy(lon: float, lat: float, z: int) -> tuple[int, int]:
    n = 2 ** z
    return int((lon + 180) / 360 * n), int((1 - math.asinh(math.tan(math.radians(lat))) / math.pi) / 2 * n)


def explain(conn, sql: str, params: dict) -> tuple[float, list[str]]:
    plan = [r[0] for r in conn.execute(text("EXPLAIN (ANALYZE, BUFFERS) " + sql), params)]
    ms = float(re.search(r"Execution Time: ([0-9.]+)", plan[-1]).group(1))
    idx = sorted({m for line in plan for m in re.findall(r"using (\w+)", line)} | {m for line in plan for m in re.findall(r"Bitmap Index Scan on (\w+)", line)})
    seq = sorted({m for line in plan for m in re.findall(r"Seq Scan on (\w+)", line)})
    return ms, idx + [f"SEQ:{s}" for s in seq]


with engine.connect() as conn:
    print("role:", conn.execute(text("SELECT current_user")).scalar(), "| read only:", conn.execute(text("SHOW transaction_read_only")).scalar())
    for t in TABLES:
        ok = conn.execute(text("SELECT has_table_privilege(current_user, :t, 'SELECT')"), {"t": t}).scalar()
        n = conn.execute(text(f"SELECT count(*) FROM {t}")).scalar() if ok else None
        print(f"  {t}: select={ok} rows={n}")
    for basin in ("delaware", "midland"):
        # the densest 0.05-degree cell of the basin's record sticks: the worst case for a tile and for a gunbarrel
        lon, lat, n = conn.execute(text("""
            SELECT round(ST_X(ST_Centroid(k.legs_geom))::numeric * 20) / 20, round(ST_Y(ST_Centroid(k.legs_geom))::numeric * 20) / 20, count(*)
            FROM box.location_stick k JOIN box.location_set t ON t.set_id = k.set_id AND t.is_record AND t.basin = :b
            GROUP BY 1, 2 ORDER BY 3 DESC LIMIT 1"""), {"b": basin}).one()
        lon, lat = float(lon), float(lat)
        print(f"\n{basin}: densest cell near ({lon}, {lat}), {n} sticks in 0.05 deg")
        for z in (7, 8, 9, 10, 11, 12, 13):
            x, y = tile_xy(lon, lat, z)
            p = {"z": z, "x": x, "y": y, "basin": basin}
            ms, idx = explain(conn, TILE, p)
            t0 = time.monotonic()
            blob = conn.execute(text(TILE), p).scalar()
            wall = (time.monotonic() - t0) * 1000
            feats = conn.execute(text("""SELECT count(*) FROM box.location_stick k JOIN box.location_set t ON t.set_id = k.set_id AND t.is_record AND t.basin = :basin
                                         WHERE ST_Intersects(k.legs_geom, ST_Transform(ST_TileEnvelope(:z, :x, :y), 4326))"""), p).scalar()
            print(f"  z{z}: {feats:>6} sticks | exec {ms:8.1f} ms | wall {wall:8.1f} ms | {len(bytes(blob)) / 1024:8.1f} KiB | {idx}")
        for half_mi in (0.5, 1.5):
            dlat = half_mi * 5280 / 364567.2
            dlon = dlat / math.cos(math.radians(lat))
            ring = [[lon - dlon, lat - dlat], [lon + dlon, lat - dlat], [lon + dlon, lat + dlat], [lon - dlon, lat + dlat], [lon - dlon, lat - dlat]]
            p = {"basin": basin, "aoi": json.dumps({"type": "Polygon", "coordinates": [ring]})}
            ms, idx = explain(conn, GUN, p)
            rows = conn.execute(text(GUN), p).all()
            print(f"  gunbarrel {2 * half_mi:.0f} x {2 * half_mi:.0f} mi: {len(rows)} leg rows, {len({r.stick_id for r in rows})} sticks, benches {sorted({r.formation_blueox for r in rows})} | exec {ms:.1f} ms | {idx}")
            print("    statuses:", {s: sum(1 for r in rows if r.status == s) for s in sorted({str(r.status) for r in rows})}, "| crowded legs:", sum(1 for r in rows if r.crowded))
