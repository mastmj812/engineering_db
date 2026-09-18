"""Read-only warehouse access for the deal-intake runner (Supabase oilgas).

Every connection is READ ONLY (psycopg `read_only`) with a per-transaction
statement_timeout — the pipeline never writes to the warehouse. Geometry
crosses the boundary as WKT in EPSG:4326. Every spatial predicate uses the
`wellstick_geom::geography` expression text that sql/26's GiST indexes serve.

No economics: the Novi NPV/PV/price columns of curated.erebor_locations are
deliberately never selected.
"""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from typing import Any

from shapely import wkt as shp_wkt
from shapely.geometry.base import BaseGeometry

from etl.db import get_connection

STATEMENT_TIMEOUT = "300s"
M_PER_MI = 1609.344

_HZ = "COALESCE(w.novi_slant_calculated, w.enverus_trajectory) ILIKE '%%horizontal%%'"


@contextmanager
def connect() -> Iterator[Any]:
    conn = get_connection()
    try:
        conn.read_only = True
        with conn.transaction():
            conn.execute(f"SET LOCAL statement_timeout = '{STATEMENT_TIMEOUT}'")
            yield conn
    finally:
        conn.close()


def _rows(conn, sql: str, params: dict | tuple | None = None) -> list[dict[str, Any]]:
    cur = conn.execute(sql, params)
    cols = [d.name for d in cur.description]
    return [dict(zip(cols, r)) for r in cur.fetchall()]


def snapshot(conn) -> dict[str, Any]:
    """Gate 0 vintages: production load, intel vintage, WellSpacing snapshot."""
    prod = conn.execute(
        "SELECT max(run_finished_at) FROM meta.etl_log "
        "WHERE status = 'success' AND table_name NOT LIKE 'curated.%%'"
    ).fetchone()[0]
    intel = conn.execute("SELECT curated.intel_vintage_date()").fetchone()[0]
    ws = conn.execute("SELECT max(wellspacing_vintage) FROM curated.wells_enriched").fetchone()[0]
    codev = conn.execute(
        "SELECT max(run_finished_at) FROM meta.etl_log "
        "WHERE status = 'success' AND table_name = 'curated.codev_context'"
    ).fetchone()[0]
    return {
        "production_vintage": prod,
        "intel_vintage_date": intel,
        "wellspacing_vintage": ws,
        "codev_context_refreshed": codev,
    }


def novi_sticks(conn, unit: BaseGeometry, buffer_ft: float = 1320.0) -> list[dict[str, Any]]:
    """Novi PUD (BASE_CASE) + RES (EMERGING) sticks touching the unit grown by
    `buffer_ft` — enough to see sticks that CROSS the boundary (Gate 2)."""
    rows = _rows(conn, """
        SELECT el.stick_id, el.unique_id, el.category, el.inventory_class,
               el.formation_blueox, el.basin_blueox, el.tvd, el.ll_ft, el.recon_status,
               el.oil_eur, el.gas_eur,
               el.pdp_count_1mi, el.pdp_count_3mi, el.pdp_count_5mi,
               el.dist_nearest_ft, el.offset_median_eur_ft, el.inflation_ratio,
               el.offset_median_tvd, el.tvd_excess_3mi_ft, el.wca_delta_ft,
               extensions.ST_AsText(el.wellstick_geom) AS wkt
        FROM curated.erebor_locations el
        WHERE el.category IN ('PUD', 'RES')
          AND el.wellstick_geom IS NOT NULL
          AND extensions.ST_DWithin(el.wellstick_geom::extensions.geography,
                                    extensions.ST_GeomFromText(%(u)s, 4326)::extensions.geography,
                                    %(buf)s)
    """, {"u": unit.wkt, "buf": buffer_ft / 3.280839895})
    for r in rows:
        r["geom"] = shp_wkt.loads(r.pop("wkt"))
    return rows


def pdp_in_unit(conn, unit: BaseGeometry, min_overlap: float = 0.30) -> list[dict[str, Any]]:
    """Producing horizontals IN the unit by the >=30% co-extent rule (share of
    the stick's geodesic length inside the unit), with their TVD-corrected bench.
    Drives `deal_has_pdp_in_adjacent_bench` (codev tier-order flip)."""
    rows = _rows(conn, f"""
        SELECT w.api10, COALESCE(we.formation_blueox, '(unmapped)') AS bench,
               w.first_production_date, w.tvd_ft,
               extensions.ST_Length(extensions.ST_Intersection(w.wellstick_geom, u.g)::extensions.geography)
                 / NULLIF(extensions.ST_Length(w.wellstick_geom::extensions.geography), 0) AS inside_frac
        FROM curated.wells w
        CROSS JOIN (SELECT extensions.ST_GeomFromText(%(u)s, 4326) AS g) u
        JOIN curated.wells_enriched we ON we.api10 = w.api10
        WHERE extensions.ST_Intersects(w.wellstick_geom, u.g)    -- geometry GiST
          AND {_HZ}
          AND w.first_production_date IS NOT NULL
    """, {"u": unit.wkt})
    return [r for r in rows if (r["inside_frac"] or 0) >= min_overlap]


def candidates(
    conn,
    unit: BaseGeometry,
    bench: str,
    radius_mi: float,
) -> list[dict[str, Any]]:
    """TC candidates for one bench: producing horizontals in the TVD-corrected
    bench within `radius_mi` of the unit (stick-to-unit geography), joined to
    curated.codev_context. Raw — filtering/tiering is select_wells' job."""
    rows = _rows(conn, f"""
        SELECT w.api10, we.current_operator AS operator, we.formation_blueox AS bench,
               we.basin_blueox AS basin, w.first_production_date, w.last_reported_month,
               w.lateral_length_ft, w.tvd_ft, we.lateral_closer_xy_ft,
               we.stack_closer_z_ft, we.parent_days_online, we.is_child,
               we.proppant_lbs_per_ft, w.eur_30yr_oil_bbl, w.eur_50yr_oil_bbl, w.cum_12m_oil_bbl,
               (date_part('year', age(w.last_reported_month, w.first_production_date)) * 12
                + date_part('month', age(w.last_reported_month, w.first_production_date)) + 1)::int
                                                                        AS months_produced,
               extensions.ST_Distance(w.wellstick_geom::extensions.geography,
                                      u.g::extensions.geography) * 3.280839895 AS dist_ft,
               extensions.ST_X(extensions.ST_LineInterpolatePoint(
                   extensions.ST_LineMerge(w.wellstick_geom), 0.5))    AS lon,
               extensions.ST_Y(extensions.ST_LineInterpolatePoint(
                   extensions.ST_LineMerge(w.wellstick_geom), 0.5))    AS lat,
               cc.scorable AS codev_scorable, cc.codev_benches, cc.parent_benches,
               cc.child_benches, cc.bench_context
        FROM curated.wells w
        CROSS JOIN (SELECT extensions.ST_GeomFromText(%(u)s, 4326) AS g) u
        JOIN curated.wells_enriched we ON we.api10 = w.api10
        LEFT JOIN curated.codev_context cc ON cc.api10 = w.api10
        WHERE extensions.ST_DWithin(w.wellstick_geom::extensions.geography,
                                    u.g::extensions.geography, %(r)s)
          AND {_HZ}
          AND w.first_production_date IS NOT NULL
          AND we.formation_blueox = %(bench)s
    """, {"u": unit.wkt, "r": radius_mi * M_PER_MI, "bench": bench})
    for r in rows:
        r["codev_scorable"] = bool(r["codev_scorable"])
        ll = r["lateral_length_ft"]
        # Screen value only (Novi 30-yr EUR per 1,000 ft) for tier medians and
        # the split test; the TC itself comes from anduin's own fits.
        r["eur_per_1000ft"] = (r["eur_30yr_oil_bbl"] / ll * 1000.0) if r["eur_30yr_oil_bbl"] and ll else None
        r["cum12_oil_per_1000ft"] = (r["cum_12m_oil_bbl"] / ll * 1000.0) if r["cum_12m_oil_bbl"] and ll else None
    return rows


def pdp_support(conn, stick: BaseGeometry, bench: str, tvd_ft: float) -> dict[str, Any]:
    """sql/47 score family for a generated stick (live, not quarterly)."""
    rows = _rows(conn, "SELECT * FROM curated.pdp_support_for_geom(%s::geometry, %s, %s)",
                 (f"SRID=4326;{stick.wkt}", bench, tvd_ft))
    return rows[0] if rows else {}


def local_benches(conn, unit: BaseGeometry, radius_mi: float = 3.0) -> list[dict[str, Any]]:
    """Benches with producing horizontals within `radius_mi` of the unit —
    the formation list handed to narvi's zones endpoint for bench proposal."""
    return _rows(conn, f"""
        SELECT we.formation_blueox AS bench, count(*) AS n_wells
        FROM curated.wells w
        CROSS JOIN (SELECT extensions.ST_GeomFromText(%(u)s, 4326) AS g) u
        JOIN curated.wells_enriched we ON we.api10 = w.api10
        WHERE extensions.ST_DWithin(w.wellstick_geom::extensions.geography,
                                    u.g::extensions.geography, %(r)s)
          AND {_HZ}
          AND w.first_production_date IS NOT NULL
          AND we.formation_blueox IS NOT NULL
        GROUP BY 1 ORDER BY 2 DESC
    """, {"u": unit.wkt, "r": radius_mi * M_PER_MI})


def pad_iou(conn, unit: BaseGeometry) -> dict[str, Any] | None:
    """ADVISORY Gate 2 signal: best IoU of the unit vs a derived Novi pad hull
    (curated.intel_pad_geom; 2026Q3 covers Midland only). None = no pad."""
    rows = _rows(conn, """
        WITH u AS (SELECT extensions.ST_GeomFromText(%(u)s, 4326) AS g)
        SELECT p.basin, p.pad_name,
               extensions.ST_Area(extensions.ST_Intersection(p.geom, u.g)::extensions.geography)
                 / NULLIF(extensions.ST_Area(extensions.ST_Union(p.geom, u.g)::extensions.geography), 0) AS iou
        FROM curated.intel_pad_geom p, u
        WHERE extensions.ST_Intersects(p.geom, u.g)
        ORDER BY 3 DESC NULLS LAST LIMIT 1
    """, {"u": unit.wkt})
    return rows[0] if rows else None


def representative_sticks(
    conn, leg: BaseGeometry, bench: str, lateral_ft: float, lateral_tol: float
) -> list[int]:
    """sql/35 — the single source of truth for which Novi sticks benchmark a
    GENERATED location (same bench, 1 mi, per-basin lateral tolerance)."""
    return [r["stick_id"] for r in _rows(
        conn,
        "SELECT stick_id FROM curated.intel_representative_sticks(%s::geometry, %s, %s, 1609, %s)",
        (f"SRID=4326;{leg.wkt}", bench, lateral_ft, lateral_tol),
    )]


def novi_params(conn, stick_ids: list[int]) -> list[dict[str, Any]]:
    """Per stick x stream x segment (1 and 2): Novi Arps (d_nom NOMINAL /yr, b,
    q_start, day_start/day_stop) plus the stick's EUR and lateral from
    erebor_locations. No price/NPV columns.

    Novi's model is multi-segment (verified 2026-09-18): segment 1 = days
    0-540 with Di pinned at 3.65/yr (0.01/day — a cap) on ~98% of gas and ~52%
    of oil/water sticks, b 1.2; segment 2 = day 540 to ~5,000-6,000, Di
    ~0.5-0.6/yr; segment 3 = terminal. Segment 1 spans the first year, so its
    1-yr effective decline IS Novi's first-year decline and compares directly
    with anduin's; segment 2 is shown beside it."""
    if not stick_ids:
        return []
    return _rows(conn, """
        SELECT a.stick_id, a.production_stream AS stream, a.segment, a.b, a.d_nom,
               a.d_eff_secant, a.q_start, a.day_start, a.day_stop,
               el.ll_ft, el.oil_eur, el.gas_eur, el.formation_blueox AS bench
        FROM curated.intel_arps a
        JOIN curated.erebor_locations el ON el.stick_id = a.stick_id
        WHERE a.stick_id = ANY(%(ids)s) AND a.segment IN (1, 2)
    """, {"ids": list(stick_ids)})
