"""SWD context for the dossier — saltwater-disposal injectors near the deal and
near the cohort, read from C4 (Phillip's SWD database). Reported, never
selected on.

Two layers (Michael, 2026-10-13):

  proximity   per planned stick: injectors within `swd.radius_mi` of the stick
              (lateral, injector surface point to the stick line), with the
              vertical standoff = landing TVD − permitted interval bottom
              (+ = the injector's interval sits ABOVE the landing) and a 'near'
              mark when the permitted interval comes within `swd.vert_window_ft`
              of the landing.
  evidence    the same exposure for every cohort well, plus H-10 volume injected
              before the well's first production and in its first 24 months.
              A cohort well is flagged `swd_suspect` when it is BOTH a poor
              performer in its cohort (<= `swd.poor_frac_of_median` × the cohort
              median EUR/1,000 ft) AND exposed (an injector within the radius
              with cumulative >= `swd.min_cum_mmbbl`). Shredder 33-59 2WA (BS2_C,
              9,244 ft; Pit Stop SWD 1 at 4,500–6,400 ft, 22 MMbbl, ~1 mi) is the
              calibration case: nothing overlaps, the well is terrible, and the
              reviewer wants to see it side by side.

Why a screen and not a multiplier: on Toucan (BS2_S, 46 wells, 2026-10-06)
exposure at any window or radius did not separate the suspected-impacted wells
from the rest (`scripts/swd_exposure.py`); vintage and parent-vs-child explained
more. The dossier shows the data; the reviewer judges.

Source: `SWD_DSN` in the environment (C4's DATABASE_URL), else the sibling
`c4/.env`. When neither resolves or the database is unreachable the section is
reported as unavailable and the run continues.
"""

from __future__ import annotations

import os
from collections import defaultdict
from contextlib import contextmanager
from datetime import date
from pathlib import Path
from typing import Any, Iterator

from shapely import wkt as _wkt
from shapely.geometry import Point
from shapely.geometry.base import BaseGeometry

from .geo import FT_PER_M, LocalFrame

M_PER_MI = 1609.344
STATEMENT_TIMEOUT = "60s"

DEFAULTS = {"radius_mi": 2.0, "vert_window_ft": 3000.0, "min_cum_mmbbl": 5.0, "poor_frac_of_median": 0.5}


# ----------------------------------------------------------------- connection
def resolve_dsn() -> str | None:
    """SWD_DSN wins; else the sibling c4 checkout's .env (this machine's layout)."""
    dsn = os.environ.get("SWD_DSN", "").strip()
    if dsn:
        return dsn
    env = Path(__file__).resolve().parents[2] / "c4" / ".env"
    if env.exists():
        for line in env.read_text(encoding="utf-8").splitlines():
            if line.startswith("DATABASE_URL="):
                return line.split("=", 1)[1].strip() or None
    return None


@contextmanager
def maybe_connect() -> Iterator[Any]:
    """Yield a read-only C4 connection, or None (with the reason on the
    generator object, see `last_error`) when the database is not available.
    Never raises: the SWD section is context, not a gate."""
    global last_error
    last_error = None
    dsn = resolve_dsn()
    if not dsn:
        last_error = "SWD_DSN not set and no sibling c4/.env"
        yield None
        return
    try:
        import psycopg
        conn = psycopg.connect(dsn, connect_timeout=10)
    except Exception as e:  # noqa: BLE001 — any failure = unavailable, by design
        last_error = f"C4 unreachable: {e}"
        yield None
        return
    try:
        conn.read_only = True
        with conn.transaction():
            conn.execute(f"SET LOCAL statement_timeout = '{STATEMENT_TIMEOUT}'")
            yield conn
    finally:
        conn.close()


last_error: str | None = None


def _rows(conn, sql: str, params: dict | tuple | None = None) -> list[dict[str, Any]]:
    cur = conn.execute(sql, params)
    cols = [d.name for d in cur.description]
    return [dict(zip(cols, r)) for r in cur.fetchall()]


# ---------------------------------------------------------------------- fetch
def fetch_injectors(conn, around: BaseGeometry, radius_mi: float) -> list[dict[str, Any]]:
    """Every UIC permit whose surface point lies within `radius_mi` of the
    geometry's bounding box, with its injection stats and H-10 months. C4 may
    run without PostGIS, so the filter is a lat/lon box; exact distances are
    computed in `exposure`."""
    minx, miny, maxx, maxy = around.bounds
    dlat = radius_mi * M_PER_MI / 111_320.0
    import math
    dlon = dlat / max(math.cos(math.radians((miny + maxy) / 2)), 0.2)
    permits = _rows(conn, """
        SELECT p.id, p.uic_number, p.lease_name, p.well_no_display, o.name AS operator,
               p.county_name, p.permit_status, p.depth_class,
               p.injection_top_ft::float AS injection_top_ft, p.injection_bottom_ft::float AS injection_bottom_ft,
               p.permitted_max_liquid_bpd::float AS permitted_bpd, p.permitted_max_liquid_psi::float AS permitted_psi,
               p.latitude, p.longitude,
               s.cumulative_volume_bbl::float AS cumulative_bbl, s.first_reported_month, s.latest_reported_month,
               s.trailing_12m_avg_bpd::float AS trailing_12m_bpd,
               s.latest_month_pressure_avg_psi::float AS latest_psi_avg,
               s.latest_month_pressure_max_psi::float AS latest_psi_max, s.pressure_trend_12m
          FROM uic_permits p
          LEFT JOIN operators o ON o.id = p.operator_id
          LEFT JOIN derived.permit_injection_stats s ON s.uic_permit_id = p.id
         WHERE p.latitude BETWEEN %(s)s AND %(n)s AND p.longitude BETWEEN %(w)s AND %(e)s
    """, {"s": miny - dlat, "n": maxy + dlat, "w": minx - dlon, "e": maxx + dlon})
    if not permits:
        return []
    months = _rows(conn, """
        SELECT uic_permit_id, reporting_month, volume_injected_bbl::float AS bbl
          FROM monthly_injection
         WHERE uic_permit_id = ANY(%(ids)s) AND volume_injected_bbl IS NOT NULL
    """, {"ids": [p["id"] for p in permits]})
    by_id: dict[int, list[tuple[date, float]]] = defaultdict(list)
    for m in months:
        by_id[m["uic_permit_id"]].append((m["reporting_month"], m["bbl"]))
    out = []
    for p in permits:
        p["months"] = sorted(by_id.get(p["id"], []))
        p["name"] = f"{p['lease_name'] or p['uic_number']} {p['well_no_display'] or ''}".strip()
        out.append(p)
    return out


# ------------------------------------------------------------------- geometry
def _as_date(v: Any) -> date | None:
    if v is None:
        return None
    if isinstance(v, date):
        return v
    try:
        return date.fromisoformat(str(v)[:10])
    except ValueError:
        return None


def _add_months(d: date, n: int) -> date:
    y, m = divmod(d.year * 12 + (d.month - 1) + n, 12)
    return date(y, m + 1, 1)


def exposure(geom: BaseGeometry, tvd_ft: float | None, injectors: list[dict[str, Any]],
             scfg: dict[str, Any], first_prod: Any = None) -> dict[str, Any]:
    """Injectors within `radius_mi` of `geom` (a stick line or a point, WGS84),
    nearest first, each with the lateral distance, the vertical standoff and
    the volume windows. Pure: no database."""
    radius_mi = float(scfg.get("radius_mi", DEFAULTS["radius_mi"]))
    window = float(scfg.get("vert_window_ft", DEFAULTS["vert_window_ft"]))
    min_cum = float(scfg.get("min_cum_mmbbl", DEFAULTS["min_cum_mmbbl"])) * 1e6
    frame = LocalFrame.around(geom)
    local = frame.to_local(geom)
    fp = _as_date(first_prod)
    fp_m = date(fp.year, fp.month, 1) if fp else None
    end24 = _add_months(fp_m, 24) if fp_m else None
    rows = []
    for inj in injectors:
        if inj.get("latitude") is None or inj.get("longitude") is None:
            continue
        pt = frame.to_local(Point(float(inj["longitude"]), float(inj["latitude"])))
        dist_mi = local.distance(pt) / M_PER_MI
        if dist_mi > radius_mi:
            continue
        top, bot = inj.get("injection_top_ft"), inj.get("injection_bottom_ft")
        standoff = (float(tvd_ft) - float(bot)) if (tvd_ft is not None and bot is not None) else None
        near = (tvd_ft is not None and top is not None and bot is not None
                and float(top) <= float(tvd_ft) + window and float(bot) >= float(tvd_ft) - window)
        pre = w24 = since = 0.0
        for mo, bbl in inj.get("months") or []:
            if fp_m is None:
                continue
            if mo < fp_m:
                pre += bbl
            else:
                since += bbl
                if mo < end24:
                    w24 += bbl
        cum = inj.get("cumulative_bbl") or 0.0
        rows.append({
            "uic": inj.get("uic_number"), "name": inj.get("name"), "operator": inj.get("operator"),
            "status": inj.get("permit_status"), "dist_mi": round(dist_mi, 2),
            "interval_ft": [top, bot], "standoff_ft": None if standoff is None else round(standoff),
            "near": bool(near), "cum_mmbbl": round(cum / 1e6, 1),
            "counts": cum >= min_cum,
            "pre_mmbbl": round(pre / 1e6, 1) if fp_m else None,
            "w24_mmbbl": round(w24 / 1e6, 1) if fp_m else None,
            "since_mmbbl": round(since / 1e6, 1) if fp_m else None,
            "trailing_12m_bpd": inj.get("trailing_12m_bpd"), "latest_psi_max": inj.get("latest_psi_max"),
            "pressure_trend": inj.get("pressure_trend_12m"), "latest_month": str(inj.get("latest_reported_month") or "")[:7] or None,
        })
    rows.sort(key=lambda r: r["dist_mi"])
    counted = [r for r in rows if r["counts"]]
    nearest = counted[0] if counted else (rows[0] if rows else None)
    biggest = max(counted, key=lambda r: r["cum_mmbbl"]) if counted else None
    return {
        "radius_mi": radius_mi, "vert_window_ft": window, "tvd_ft": tvd_ft,
        "n_within": len(rows), "n_counted": len(counted), "n_near": sum(1 for r in counted if r["near"]),
        "n_active": sum(1 for r in counted if r["status"] == "active"),
        "exposed": bool(counted), "nearest": nearest, "biggest": biggest,
        "max_latest_psi": max((r["latest_psi_max"] for r in counted if r["latest_psi_max"] is not None), default=None),
        "injectors": rows,
    }


def unit_context(conn, unit_geom: BaseGeometry, locations: list[dict[str, Any]], tvd_ft: float,
                 scfg: dict[str, Any]) -> dict[str, Any]:
    """Proximity layer for one (unit × bench): every planned stick scored, plus
    the unit roll-up the dossier table shows."""
    radius = float(scfg.get("radius_mi", DEFAULTS["radius_mi"]))
    inj = fetch_injectors(conn, unit_geom, radius + 0.5)
    sticks = []
    for loc in locations:
        g = _wkt.loads(loc["wkt"])
        e = exposure(g, float(loc.get("tvd") or tvd_ft), inj, scfg)
        sticks.append({"id": loc["id"], "n_counted": e["n_counted"], "n_near": e["n_near"],
                       "nearest": e["nearest"], "exposed": e["exposed"]})
    unit_e = exposure(unit_geom, tvd_ft, inj, scfg)
    return {
        "n_sticks": len(sticks), "n_sticks_exposed": sum(1 for s in sticks if s["exposed"]),
        "n_injectors": unit_e["n_counted"], "n_near": unit_e["n_near"], "n_active": unit_e["n_active"],
        "nearest": unit_e["nearest"], "biggest": unit_e["biggest"], "max_latest_psi": unit_e["max_latest_psi"],
        "radius_mi": radius, "vert_window_ft": unit_e["vert_window_ft"], "sticks": sticks,
        "injectors": unit_e["injectors"],
    }


def _perf(w: dict[str, Any]) -> float | None:
    for k in ("anduin_oil_eur_per_1000ft", "eur_per_1000ft"):
        v = w.get(k)
        if v is not None:
            return float(v)
    return None


def _median(vals: list[float]) -> float | None:
    s = sorted(vals)
    if not s:
        return None
    n = len(s)
    return s[n // 2] if n % 2 else (s[n // 2 - 1] + s[n // 2]) / 2


def cohort_context(cohort: list[dict[str, Any]], sticks_wkt: dict[str, str],
                   injectors: list[dict[str, Any]], scfg: dict[str, Any]) -> dict[str, Any]:
    """Evidence layer: every cohort well's exposure beside its performance.
    `sticks_wkt` maps api10 -> lateral WKT (falls back to the lon/lat midpoint).
    Pure: injectors already fetched."""
    poor_frac = float(scfg.get("poor_frac_of_median", DEFAULTS["poor_frac_of_median"]))
    perf = {w["api10"]: _perf(w) for w in cohort}
    med = _median([v for v in perf.values() if v is not None])
    rows = []
    for w in cohort:
        wk = sticks_wkt.get(w["api10"])
        geom = _wkt.loads(wk) if wk else (Point(float(w["lon"]), float(w["lat"]))
                                          if w.get("lon") is not None and w.get("lat") is not None else None)
        if geom is None:
            continue
        e = exposure(geom, w.get("tvd_ft"), injectors, scfg, w.get("first_production_date"))
        v = perf[w["api10"]]
        poor = v is not None and med is not None and v <= poor_frac * med
        rows.append({
            "api10": w["api10"], "well_name": w.get("well_name"), "first_production_date": str(w.get("first_production_date") or "")[:10] or None,
            "tvd_ft": w.get("tvd_ft"), "perf_per_1000ft": v, "poor": poor, "exposed": e["exposed"],
            "suspect": bool(poor and e["exposed"]), "n_injectors": e["n_counted"], "n_near": e["n_near"],
            "nearest": e["nearest"], "biggest": e["biggest"], "max_latest_psi": e["max_latest_psi"],
            "geom_source": "stick" if wk else "midpoint",
        })
    exposed = [r["perf_per_1000ft"] for r in rows if r["exposed"] and r["perf_per_1000ft"] is not None]
    clear = [r["perf_per_1000ft"] for r in rows if not r["exposed"] and r["perf_per_1000ft"] is not None]
    return {
        "n": len(rows), "n_exposed": sum(1 for r in rows if r["exposed"]),
        "n_poor": sum(1 for r in rows if r["poor"]), "n_suspect": sum(1 for r in rows if r["suspect"]),
        "perf_metric": "anduin oil EUR/1,000 ft" if any(w.get("anduin_oil_eur_per_1000ft") is not None for w in cohort)
                       else "Novi EUR/1,000 ft (screen)",
        "perf_median": med, "poor_cutoff": None if med is None else poor_frac * med,
        "exposed_median": _median(exposed), "n_exposed_scored": len(exposed),
        "clear_median": _median(clear), "n_clear_scored": len(clear),
        "wells": rows,
    }


def bounds_for(cohort: list[dict[str, Any]], sticks_wkt: dict[str, str], units: list[BaseGeometry]) -> BaseGeometry | None:
    """One geometry whose bounding box covers the units and every cohort well,
    so the injector fetch happens once per group."""
    from shapely.geometry import GeometryCollection
    parts: list[BaseGeometry] = list(units)
    for w in cohort:
        wk = sticks_wkt.get(w["api10"])
        if wk:
            parts.append(_wkt.loads(wk))
        elif w.get("lon") is not None and w.get("lat") is not None:
            parts.append(Point(float(w["lon"]), float(w["lat"])))
    return GeometryCollection(parts) if parts else None


def flags(group: dict[str, Any] | None, units: dict[str, dict[str, Any] | None]) -> list[str]:
    """ONE or two flags per TC group. Screen language by design (Toucan null)."""
    out: list[str] = []
    near_units = []
    for label, u in units.items():
        if not u or not u.get("n_injectors"):
            continue
        n = u["nearest"]
        near_units.append(f"{label} ({u['n_injectors']} injector(s) within {u['radius_mi']:g} mi"
                          + (f", {u['n_near']} within {u['vert_window_ft']:,.0f} ft of the landing" if u["n_near"] else "")
                          + f"; nearest {n['name']} {n['dist_mi']:g} mi, "
                          + ("standoff n/a" if n["standoff_ft"] is None else f"interval bottom {abs(n['standoff_ft']):,.0f} ft {'above' if n['standoff_ft'] > 0 else 'below'}")
                          + f", {n['cum_mmbbl']:g} MMbbl, {n['status']})")
    if near_units:
        out.append("SWD proximity: " + "; ".join(near_units)
                   + " — context for the reviewer; the curve carries nothing for it")
    if group and group["n"]:
        if group["n_suspect"]:
            names = ", ".join(f"{r['well_name']} ({r['perf_per_1000ft']:,.0f} vs cohort median {group['perf_median']:,.0f}"
                              + (f"; nearest {r['nearest']['name']} {r['nearest']['dist_mi']:g} mi, {r['nearest']['cum_mmbbl']:g} MMbbl" if r["nearest"] else "") + ")"
                              for r in group["wells"] if r["suspect"])
            out.append(f"SWD evidence: {group['n_suspect']} of {group['n']} cohort wells are BOTH poor (<= {group['poor_cutoff']:,.0f} "
                       f"per 1,000 ft) AND exposed: {names} — suspicious, not proven (Toucan 2026-10-06: exposure did not "
                       "predict performance); reviewer reads the table")
        elif group["n_exposed"]:
            out.append(f"SWD evidence: {group['n_exposed']} of {group['n']} cohort wells are exposed, none of them poor "
                       f"(exposed median {group['exposed_median']:,.0f} vs clear {group['clear_median']:,.0f} per 1,000 ft)"
                       if group["exposed_median"] is not None and group["clear_median"] is not None else
                       f"SWD evidence: {group['n_exposed']} of {group['n']} cohort wells are exposed, none of them poor")
    return out
