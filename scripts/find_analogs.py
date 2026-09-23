"""Scenario-matched analog pull — API10 list + scenario detail + cum per kft.

Read-only against the oilgas warehouse. Reads curated.dev_scenario (sql/50),
the SAME view anduin's header sync consumes, so a filter here and the anduin
Development-scenario filter return the same wells.

Examples (repo root, venv):
    python -m scripts.find_analogs --bench WCB_2 --scenario underfill \\
        --near 31.304,-101.816 --radius-mi 8
    python -m scripts.find_analogs --bench LSSH --scenario topfill \\
        --parent-bench WCA_1 --min-parent-age-days 730 --fp-from 2019-01-01 \\
        --min-months 12 --csv out.csv
    python -m scripts.find_analogs --bench WCA_1 --scenario topfill sandwich \\
        --polygon unit.geojson

Semantics (all from sql/50 — see its header for the reasoning):
  --bench            subject bench = TVD-corrected formation_blueox, NULL ->
                     '(unmapped)' (codev_context.bench). Repeatable.
  --scenario         sandwich | topfill | underfill | codev_stack | standalone.
                     Vertical parent = other mapped bench, online > 180 d
                     before the subject, closest parent lateral midpoint
                     <= 660 ft from the subject lateral, |dTVD| <= 1,000 ft.
  --parent-bench     the subject has a qualifying vertical parent in that
                     bench (above or below). Repeatable (any-of).
  --min-parent-age-days N   youngest qualifying parent was online >= N days
                     before the subject's FP (i.e. ALL qualifying parents are
                     at least that old). --max-parent-age-days likewise on the
                     oldest.
  --near LAT,LON --radius-mi R   stick within R miles of the point
                     (geography ST_DWithin — a search area, not well matching).
  --polygon FILE     stick intersects the GeoJSON polygon (Geometry, Feature
                     or FeatureCollection; EPSG:4326).
  --min-months N     months from FP through last_reported_month >= N.
Rates are per 1,000 ft of lateral (lateral_length_ft); cum12/24 are Novi's
calendar cums from wells_enriched. child_censored wells (FP within 180 d of
the newest FP in the load) are included by default; their child columns read
short but the scenario class (parent-side) is not censored.
"""

from __future__ import annotations

import argparse
import csv
import json
import sys
from datetime import date
from pathlib import Path
from typing import Any

SCENARIOS = ("sandwich", "topfill", "underfill", "codev_stack", "standalone")
M_PER_MI = 1609.344

_SELECT = """
SELECT
    d.api10,
    we.well_name,
    we.current_operator                                         AS operator,
    d.bench,
    d.first_production_date                                     AS fp,
    d.tvd_ft,
    we.lateral_length_ft                                        AS lateral_ft,
    d.scenario_class,
    d.parent_benches_below,
    d.parent_benches_above,
    d.nearest_parent_below_dtvd_ft,
    d.nearest_parent_above_dtvd_ft,
    d.nearest_parent_offset_ft,
    d.youngest_parent_age_days,
    d.oldest_parent_age_days,
    d.has_same_bench_parent,
    d.child_censored,
    (EXTRACT(YEAR FROM age(we.last_reported_month, d.first_production_date)) * 12
     + EXTRACT(MONTH FROM age(we.last_reported_month, d.first_production_date)) + 1)::int
                                                                AS months_produced,
    round((we.cum_12m_oil_bbl * 1000.0 / NULLIF(we.lateral_length_ft, 0))::numeric, 0)
                                                                AS cum12_oil_bbl_per_kft,
    round((we.cum_24m_oil_bbl * 1000.0 / NULLIF(we.lateral_length_ft, 0))::numeric, 0)
                                                                AS cum24_oil_bbl_per_kft{dist}
FROM curated.dev_scenario d
JOIN curated.wells w            ON w.api10  = d.api10
JOIN curated.wells_enriched we  ON we.api10 = d.api10
WHERE d.scorable
"""


def parse_near(s: str) -> tuple[float, float]:
    """'LAT,LON' -> (lat, lon), range-checked."""
    try:
        lat_s, lon_s = s.split(",")
        lat, lon = float(lat_s), float(lon_s)
    except ValueError as e:
        raise ValueError(f"--near expects LAT,LON, got {s!r}") from e
    if not (-90 <= lat <= 90 and -180 <= lon <= 180):
        raise ValueError(f"--near out of range: {s!r} (LAT first, then LON)")
    return lat, lon


def polygon_geometry(doc: dict[str, Any]) -> str:
    """GeoJSON Geometry/Feature/FeatureCollection -> one geometry JSON string.

    Multiple features are merged into a GeometryCollection; only (Multi)Polygon
    members are accepted — a point or line is not a search area."""
    if doc.get("type") == "FeatureCollection":
        geoms = [f["geometry"] for f in doc.get("features", []) if f.get("geometry")]
    elif doc.get("type") == "Feature":
        geoms = [doc["geometry"]] if doc.get("geometry") else []
    else:
        geoms = [doc]
    if not geoms:
        raise ValueError("GeoJSON has no geometry")
    bad = [g.get("type") for g in geoms if g.get("type") not in ("Polygon", "MultiPolygon")]
    if bad:
        raise ValueError(f"--polygon accepts Polygon/MultiPolygon only, got {bad}")
    geom = geoms[0] if len(geoms) == 1 else {"type": "GeometryCollection", "geometries": geoms}
    return json.dumps(geom)


def build_query(
    *,
    benches: list[str] | None = None,
    scenarios: list[str] | None = None,
    parent_benches: list[str] | None = None,
    min_parent_age_days: int | None = None,
    max_parent_age_days: int | None = None,
    near: tuple[float, float] | None = None,
    radius_mi: float | None = None,
    polygon: str | None = None,
    fp_from: date | None = None,
    fp_to: date | None = None,
    min_months: int | None = None,
) -> tuple[str, dict[str, Any]]:
    """Pure: filters -> (SQL, bind params). No value is ever interpolated."""
    if scenarios:
        unknown = sorted(set(scenarios) - set(SCENARIOS))
        if unknown:
            raise ValueError(f"unknown scenario(s) {unknown}; choose from {SCENARIOS}")
    if near is not None and polygon is not None:
        raise ValueError("--near and --polygon are mutually exclusive")
    if (near is None) != (radius_mi is None):
        raise ValueError("--near and --radius-mi go together")
    if radius_mi is not None and radius_mi <= 0:
        raise ValueError("--radius-mi must be > 0")

    where: list[str] = []
    p: dict[str, Any] = {}
    dist = ""
    if benches:
        where.append("d.bench = ANY(%(benches)s)")
        p["benches"] = list(benches)
    if scenarios:
        where.append("d.scenario_class = ANY(%(scenarios)s)")
        p["scenarios"] = list(scenarios)
    if parent_benches:
        where.append("(d.parent_benches_below && %(parent_benches)s::text[]"
                     " OR d.parent_benches_above && %(parent_benches)s::text[])")
        p["parent_benches"] = list(parent_benches)
    if min_parent_age_days is not None:
        where.append("d.youngest_parent_age_days >= %(min_parent_age_days)s")
        p["min_parent_age_days"] = int(min_parent_age_days)
    if max_parent_age_days is not None:
        where.append("d.oldest_parent_age_days <= %(max_parent_age_days)s")
        p["max_parent_age_days"] = int(max_parent_age_days)
    if near is not None:
        # Same text as the sql/26 expression index -> index-served.
        pt = ("extensions.ST_SetSRID(extensions.ST_Point(%(lon)s, %(lat)s), 4326)"
              "::extensions.geography")
        where.append(f"extensions.ST_DWithin(w.wellstick_geom::extensions.geography, {pt}, %(radius_m)s)")
        dist = (",\n    round((extensions.ST_Distance(w.wellstick_geom::extensions.geography, "
                f"{pt}) / {M_PER_MI})::numeric, 2) AS dist_mi")
        p.update(lat=near[0], lon=near[1], radius_m=float(radius_mi) * M_PER_MI)
    if polygon is not None:
        where.append("extensions.ST_Intersects(w.wellstick_geom, "
                     "extensions.ST_SetSRID(extensions.ST_GeomFromGeoJSON(%(polygon)s), 4326))")
        p["polygon"] = polygon
    if fp_from is not None:
        where.append("d.first_production_date >= %(fp_from)s")
        p["fp_from"] = fp_from
    if fp_to is not None:
        where.append("d.first_production_date <= %(fp_to)s")
        p["fp_to"] = fp_to
    if min_months is not None:
        where.append("we.last_reported_month >= (d.first_production_date"
                     " + make_interval(months => %(min_months_m1)s))")
        p["min_months_m1"] = int(min_months) - 1

    sql = _SELECT.format(dist=dist)
    for clause in where:
        sql += f"  AND {clause}\n"
    sql += "ORDER BY d.first_production_date DESC, d.api10\n"
    return sql, p


def _args(argv: list[str] | None) -> argparse.Namespace:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--bench", nargs="+")
    ap.add_argument("--scenario", nargs="+", choices=SCENARIOS)
    ap.add_argument("--parent-bench", nargs="+")
    ap.add_argument("--min-parent-age-days", type=int)
    ap.add_argument("--max-parent-age-days", type=int)
    ap.add_argument("--near", type=parse_near, metavar="LAT,LON")
    ap.add_argument("--radius-mi", type=float)
    ap.add_argument("--polygon", type=Path, metavar="FILE.geojson")
    ap.add_argument("--fp-from", type=date.fromisoformat)
    ap.add_argument("--fp-to", type=date.fromisoformat)
    ap.add_argument("--min-months", type=int)
    ap.add_argument("--csv", type=Path, help="write all columns here")
    ap.add_argument("--api-only", action="store_true", help="print API10s only, one per line")
    return ap.parse_args(argv)


def main(argv: list[str] | None = None) -> None:
    a = _args(argv)
    polygon = None
    if a.polygon is not None:
        polygon = polygon_geometry(json.loads(a.polygon.read_text(encoding="utf-8")))
    sql, params = build_query(
        benches=a.bench, scenarios=a.scenario, parent_benches=a.parent_bench,
        min_parent_age_days=a.min_parent_age_days, max_parent_age_days=a.max_parent_age_days,
        near=a.near, radius_mi=a.radius_mi, polygon=polygon,
        fp_from=a.fp_from, fp_to=a.fp_to, min_months=a.min_months,
    )
    from etl.db import get_connection  # lazy: tests import this module DB-free

    conn = get_connection()
    try:
        with conn.cursor() as cur:
            cur.execute("SET TRANSACTION READ ONLY")
            cur.execute("SET LOCAL statement_timeout = '300s'")
            cur.execute(sql, params)
            cols = [d.name for d in cur.description]
            rows = cur.fetchall()
        conn.rollback()
    finally:
        conn.close()

    if a.csv:
        with a.csv.open("w", newline="", encoding="utf-8") as f:
            w = csv.writer(f)
            w.writerow(cols)
            w.writerows(rows)
    if a.api_only:
        print("\n".join(r[0] for r in rows))
    else:
        show = ["api10", "well_name", "operator", "bench", "fp", "scenario_class",
                "parent_benches_below", "parent_benches_above", "youngest_parent_age_days",
                "cum12_oil_bbl_per_kft", "cum24_oil_bbl_per_kft"] + (["dist_mi"] if a.near else [])
        idx = [cols.index(c) for c in show]
        print("\t".join(show))
        for r in rows:
            print("\t".join("" if r[i] is None else str(r[i]) for i in idx))
    from collections import Counter

    by = Counter(r[cols.index("scenario_class")] for r in rows)
    print(f"# {len(rows)} wells  " + "  ".join(f"{k}={v}" for k, v in sorted(by.items())),
          file=sys.stderr)
    if a.csv:
        print(f"# wrote {a.csv}", file=sys.stderr)


if __name__ == "__main__":
    main()
