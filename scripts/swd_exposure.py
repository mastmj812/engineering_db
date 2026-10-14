"""SWD exposure vs. producer performance around a point (read-only, two databases).

Joins oilgas (curated.wells_enriched + curated.production_combined actuals) with
Phillip's C4 database (RRC UIC permits + H-10 monthly injection) to score every
producer of one bench within --radius-mi of a point by its proximity to
injection, then relates that exposure to cum-12 / cum-24 oil per 1,000 ft.

Conventions
  * Producer geometry is the wellstick; injector geometry is the permit surface
    point (SWDs are vertical, so surface == bottom-hole to within the lateral
    distances that matter here).
  * standoff_ft = producer landing TVD - injector interval BOTTOM. Positive means
    the injector's interval sits ABOVE the landing. Permit intervals are measured
    depth below rig floor; landing TVD is sub-KB. Treat as +/-100 ft.
  * "near" injector = its permitted interval intersects the band
    [landing - vert_window, landing + vert_window].
  * Volume windows are anchored on the producer's first production month:
    pre  = all H-10 volume before first production (history starts 2015-02),
    w24  = first 24 months of the producer's life, total = all months since.
  * Performance = cum-12 / cum-24 oil per 1,000 ft of lateral from ACTUAL months
    (is_forecast = false). NULL when the well lacks the months or the lateral.

Usage
  python -m scripts.swd_exposure --lat 31.73 --lon -103.77 --bench BS2_S \
      [--radius-mi 10] [--swd-radius-mi 3] [--vert-window-ft 2000] \
      [--c4-env ../c4/.env] [--out-dir <dir>]

Never writes to either database.
"""

from __future__ import annotations

import argparse
import csv
import math
import os
import sys
from collections import defaultdict
from datetime import date
from pathlib import Path

import psycopg
from psycopg.rows import dict_row

from etl.db import get_connection

MI_M = 1609.34


def _c4_dsn(env_path: Path) -> str:
    for line in env_path.read_text(encoding="utf-8").splitlines():
        if line.startswith("DATABASE_URL="):
            return line.split("=", 1)[1].strip()
    raise SystemExit(f"DATABASE_URL not found in {env_path}")


def _add_months(d: date, n: int) -> date:
    y, m = divmod(d.year * 12 + (d.month - 1) + n, 12)
    return date(y, m + 1, 1)


# --------------------------------------------------------------------------- C4
def load_injectors(dsn: str, lat: float, lon: float, radius_m: float) -> tuple[list[dict], dict[str, list]]:
    """Permits with a surface point inside radius_m, plus their H-10 months."""
    with psycopg.connect(dsn, row_factory=dict_row) as conn:
        conn.execute("SET TRANSACTION READ ONLY")
        permits = conn.execute(
            """
            SELECT p.id, p.uic_number, p.lease_name, p.well_no_display, p.county_name,
                   o.name AS operator, p.depth_class, p.injection_top_ft, p.injection_bottom_ft,
                   p.permitted_max_liquid_bpd, p.permitted_max_liquid_psi, p.permit_status,
                   p.rrc_commercial_disposal_flag, p.latitude, p.longitude
              FROM uic_permits p
              LEFT JOIN operators o ON o.id = p.operator_id
             WHERE p.latitude IS NOT NULL
               AND earth_distance(ll_to_earth(%s, %s), ll_to_earth(p.latitude, p.longitude)) <= %s
            """,
            (lat, lon, radius_m),
        ).fetchall()
        ids = [p["id"] for p in permits]
        months = conn.execute(
            """
            SELECT uic_permit_id, reporting_month, volume_injected_bbl, injection_pressure_avg_psi
              FROM monthly_injection
             WHERE uic_permit_id = ANY(%s) AND volume_injected_bbl IS NOT NULL
            """,
            (ids,),
        ).fetchall()
    by_permit: dict[str, list] = defaultdict(list)
    for m in months:
        by_permit[m["uic_permit_id"]].append(m)
    return permits, by_permit


# ---------------------------------------------------------------------- oilgas
def load_producers(conn, lat: float, lon: float, radius_m: float, bench: str) -> list[dict]:
    with conn.cursor(row_factory=dict_row) as cur:
        cur.execute(
            """
            SELECT column_name FROM information_schema.columns
             WHERE table_schema='curated' AND table_name='wells_enriched' AND column_name ILIKE '%%operator%%'
            """
        )
        ops = [r["column_name"] for r in cur.fetchall()]
        opcol = ops[0] if ops else "NULL"
        cur.execute(
            f"""
            SELECT api10, well_name, {opcol} AS operator, county, tvd_ft, lateral_length_ft,
                   first_production_date, formation, formation_blueox_tvd_corrected,
                   lateral_closer_xy_ft,
                   round((extensions.ST_Distance(wellstick_geom::extensions.geography,
                          extensions.ST_SetSRID(extensions.ST_MakePoint(%(lon)s, %(lat)s), 4326)::extensions.geography)
                          / {MI_M})::numeric, 2) AS center_mi
              FROM curated.wells_enriched
             WHERE formation_blueox = %(bench)s
               AND wellstick_geom IS NOT NULL
               AND extensions.ST_DWithin(wellstick_geom::extensions.geography,
                     extensions.ST_SetSRID(extensions.ST_MakePoint(%(lon)s, %(lat)s), 4326)::extensions.geography,
                     %(r)s)
             ORDER BY center_mi
            """,
            {"lat": lat, "lon": lon, "bench": bench, "r": radius_m},
        )
        return cur.fetchall()


def pair_distances(conn, apis: list[str], permits: list[dict], swd_radius_m: float) -> dict[tuple[str, int], float]:
    """Stick-to-point distance (m) for every producer/injector pair within swd_radius_m."""
    ids = [p["id"] for p in permits]
    lons = [float(p["longitude"]) for p in permits]
    lats = [float(p["latitude"]) for p in permits]
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT w.api10, p.pid,
                   extensions.ST_Distance(w.wellstick_geom::extensions.geography,
                       extensions.ST_SetSRID(extensions.ST_MakePoint(p.lon, p.lat), 4326)::extensions.geography) AS dist_m
              FROM curated.wells_enriched w
              CROSS JOIN unnest(%s::bigint[], %s::float8[], %s::float8[]) AS p(pid, lon, lat)
             WHERE w.api10 = ANY(%s)
               AND extensions.ST_DWithin(w.wellstick_geom::extensions.geography,
                     extensions.ST_SetSRID(extensions.ST_MakePoint(p.lon, p.lat), 4326)::extensions.geography, %s)
            """,
            (ids, lons, lats, apis, swd_radius_m),
        )
        return {(api, pid): float(d) for api, pid, d in cur.fetchall()}


def load_performance(conn, apis: list[str]) -> dict[str, dict]:
    """cum-12 / cum-24 oil per 1,000 ft from actual months only."""
    with conn.cursor(row_factory=dict_row) as cur:
        cur.execute(
            """
            SELECT api10,
                   count(*) FILTER (WHERE months_on_production <= 12) AS n12,
                   count(*) FILTER (WHERE months_on_production <= 24) AS n24,
                   sum(oil_per_month_bbl) FILTER (WHERE months_on_production <= 12) AS oil12,
                   sum(oil_per_month_bbl) FILTER (WHERE months_on_production <= 24) AS oil24,
                   max(months_on_production) AS months_actual,
                   max(lateral_length_ft) AS ll
              FROM curated.production_combined
             WHERE api10 = ANY(%s) AND NOT is_forecast
             GROUP BY api10
            """,
            (apis,),
        )
        out = {}
        for r in cur.fetchall():
            ll = float(r["ll"]) if r["ll"] else None
            per = lambda v, n, need: (float(v) / ll * 1000.0) if (ll and v is not None and n >= need) else None
            out[r["api10"]] = {
                "months_actual": r["months_actual"],
                "cum12_per_1000ft": per(r["oil12"], r["n12"], 12),
                "cum24_per_1000ft": per(r["oil24"], r["n24"], 24),
            }
        return out


# --------------------------------------------------------------------- metrics
def score(producers, permits, h10, dists, vert_window_ft, min_dist_mi=0.5):
    pmap = {p["id"]: p for p in permits}
    rows, pairs = [], []
    for w in producers:
        api = w["api10"]
        tvd = float(w["tvd_ft"]) if w["tvd_ft"] is not None else None
        fp = w["first_production_date"]
        fp_m = date(fp.year, fp.month, 1) if fp else None
        end24 = _add_months(fp_m, 24) if fp_m else None

        m = dict(
            n_inj_all=0, n_inj_near=0, n_inj_above=0,
            all_bbl_w24=0.0, all_wt_w24=0.0,
            near_bbl_pre=0.0, near_bbl_w24=0.0, near_bbl_total=0.0, near_wt_w24=0.0,
            nearest_near_mi=None, nearest_near_standoff_ft=None, nearest_near_bbl_w24=None,
            nearest_near_psi=None, nearest_near_uic=None, nearest_near_name=None,
            nearest_any_mi=None,
        )
        for (a, pid), dist_m in dists.items():
            if a != api:
                continue
            p = pmap[pid]
            dist_mi = dist_m / MI_M
            bot = float(p["injection_bottom_ft"]) if p["injection_bottom_ft"] is not None else None
            top = float(p["injection_top_ft"]) if p["injection_top_ft"] is not None else None
            standoff = (tvd - bot) if (tvd is not None and bot is not None) else None
            near = (
                tvd is not None and top is not None and bot is not None
                and top <= tvd + vert_window_ft and bot >= tvd - vert_window_ft
            )
            above = bot is not None and tvd is not None and bot < tvd

            pre = w24 = total = 0.0
            psi_n = psi_sum = 0.0
            for mo in h10.get(pid, []):
                v = float(mo["volume_injected_bbl"] or 0)
                rm = mo["reporting_month"]
                if fp_m is None:
                    total += v
                    continue
                if rm < fp_m:
                    pre += v
                else:
                    total += v
                    if rm < end24:
                        w24 += v
                        if mo["injection_pressure_avg_psi"] is not None:
                            psi_sum += float(mo["injection_pressure_avg_psi"])
                            psi_n += 1
            psi = psi_sum / psi_n if psi_n else None
            wt = w24 / max(dist_mi, min_dist_mi)

            m["n_inj_all"] += 1
            m["all_bbl_w24"] += w24
            m["all_wt_w24"] += wt
            if m["nearest_any_mi"] is None or dist_mi < m["nearest_any_mi"]:
                m["nearest_any_mi"] = dist_mi
            if above:
                m["n_inj_above"] += 1
            if near:
                m["n_inj_near"] += 1
                m["near_bbl_pre"] += pre
                m["near_bbl_w24"] += w24
                m["near_bbl_total"] += total
                m["near_wt_w24"] += wt
                if m["nearest_near_mi"] is None or dist_mi < m["nearest_near_mi"]:
                    m.update(
                        nearest_near_mi=dist_mi, nearest_near_standoff_ft=standoff,
                        nearest_near_bbl_w24=w24, nearest_near_psi=psi,
                        nearest_near_uic=p["uic_number"],
                        nearest_near_name=f"{p['lease_name']} {p['well_no_display'] or ''}".strip(),
                    )
            pairs.append(dict(
                api10=api, well_name=w["well_name"], uic_number=p["uic_number"],
                injector=f"{p['lease_name']} {p['well_no_display'] or ''}".strip(),
                inj_operator=p["operator"], depth_class=p["depth_class"],
                dist_mi=round(dist_mi, 2), inj_top_ft=top, inj_bottom_ft=bot,
                standoff_ft=standoff, near=near, above=above,
                bbl_pre=round(pre), bbl_w24=round(w24), bbl_total=round(total),
                avg_psi_w24=round(psi) if psi is not None else None,
                permit_status=p["permit_status"], commercial=p["rrc_commercial_disposal_flag"],
            ))
        rows.append({**{k: w[k] for k in (
            "api10", "well_name", "operator", "county", "tvd_ft", "lateral_length_ft",
            "first_production_date", "lateral_closer_xy_ft", "center_mi")}, **m})
    return rows, pairs


def spearman(xs, ys):
    pts = [(x, y) for x, y in zip(xs, ys) if x is not None and y is not None]
    if len(pts) < 5:
        return None, len(pts)
    try:
        from scipy.stats import spearmanr
        r, p = spearmanr([a for a, _ in pts], [b for _, b in pts])
        return (float(r), float(p)), len(pts)
    except ImportError:
        return None, len(pts)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--lat", type=float, required=True)
    ap.add_argument("--lon", type=float, required=True)
    ap.add_argument("--bench", required=True, help="formation_blueox code, e.g. BS2_S")
    ap.add_argument("--radius-mi", type=float, default=10.0)
    ap.add_argument("--swd-radius-mi", type=float, default=3.0)
    ap.add_argument("--vert-window-ft", type=float, default=2000.0)
    ap.add_argument("--min-vintage", type=int, default=2017, help="first-production year floor for the correlation pass")
    ap.add_argument("--c4-env", default=str(Path(__file__).resolve().parents[2] / "c4" / ".env"))
    ap.add_argument("--out-dir", default=os.environ.get("SWD_EXPOSURE_OUT", "."))
    ap.add_argument("--exclude-api10", nargs="*", default=[], help="producers to drop (bad TVD etc.)")
    args = ap.parse_args(argv)

    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    dsn = _c4_dsn(Path(args.c4_env))
    r_m, swd_m = args.radius_mi * MI_M, args.swd_radius_mi * MI_M

    permits, h10 = load_injectors(dsn, args.lat, args.lon, r_m + swd_m)
    print(f"C4: {len(permits)} permits within {args.radius_mi + args.swd_radius_mi:.0f} mi, "
          f"{sum(len(v) for v in h10.values()):,} H-10 months")

    conn = get_connection()
    try:
        with conn.cursor() as cur:
            cur.execute("SET TRANSACTION READ ONLY; SET LOCAL statement_timeout='300s'")
        producers = [w for w in load_producers(conn, args.lat, args.lon, r_m, args.bench)
                     if w["api10"] not in set(args.exclude_api10)]
        apis = [w["api10"] for w in producers]
        print(f"oilgas: {len(producers)} {args.bench} producers within {args.radius_mi:.0f} mi")
        dists = pair_distances(conn, apis, permits, swd_m)
        perf = load_performance(conn, apis)
        conn.rollback()
    finally:
        conn.close()

    rows, pairs = score(producers, permits, h10, dists, args.vert_window_ft)
    for r in rows:
        r.update(perf.get(r["api10"], {"months_actual": None, "cum12_per_1000ft": None, "cum24_per_1000ft": None}))

    wells_csv = out_dir / f"swd_exposure_{args.bench}_wells.csv"
    pairs_csv = out_dir / f"swd_exposure_{args.bench}_pairs.csv"
    with wells_csv.open("w", newline="", encoding="utf-8") as f:
        wr = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        wr.writeheader(); wr.writerows(rows)
    with pairs_csv.open("w", newline="", encoding="utf-8") as f:
        wr = csv.DictWriter(f, fieldnames=list(pairs[0].keys()))
        wr.writeheader(); wr.writerows(pairs)

    # ---- console table
    print()
    hdr = f"{'api10':<11}{'well':<34}{'cnty':<9}{'tvd':>6}{'fp':>11}{'cum24/kft':>10}{'nInj':>5}{'near':>5}{'nrst_mi':>8}{'stand_ft':>9}{'near_w24 MMbbl':>15}{'near_wt':>9}"
    print(hdr)
    for r in sorted(rows, key=lambda r: (r["cum24_per_1000ft"] is None, -(r["cum24_per_1000ft"] or 0))):
        print(f"{r['api10']:<11}{(r['well_name'] or '')[:33]:<34}{(r['county'] or '')[:8]:<9}"
              f"{r['tvd_ft'] or '':>6}{str(r['first_production_date'] or ''):>11}"
              f"{(f'{r['cum24_per_1000ft']:,.0f}' if r['cum24_per_1000ft'] else '-'):>10}"
              f"{r['n_inj_all']:>5}{r['n_inj_near']:>5}"
              f"{(f'{r['nearest_near_mi']:.2f}' if r['nearest_near_mi'] is not None else '-'):>8}"
              f"{(f'{r['nearest_near_standoff_ft']:,.0f}' if r['nearest_near_standoff_ft'] is not None else '-'):>9}"
              f"{r['near_bbl_w24']/1e6:>15.2f}{r['near_wt_w24']/1e6:>9.2f}")

    # ---- correlations
    print(f"\nSpearman rank correlation vs cum-24 oil per 1,000 ft "
          f"(first production >= {args.min_vintage}, actual months >= 24):")
    sub = [r for r in rows if r["cum24_per_1000ft"] is not None
           and r["first_production_date"] and r["first_production_date"].year >= args.min_vintage]
    y = [r["cum24_per_1000ft"] for r in sub]
    for k in ("near_wt_w24", "near_bbl_w24", "near_bbl_pre", "n_inj_near", "nearest_near_mi",
              "nearest_near_standoff_ft", "all_wt_w24", "all_bbl_w24", "n_inj_all",
              "lateral_length_ft", "lateral_closer_xy_ft"):
        res, n = spearman([r[k] for r in sub], y)
        if res:
            print(f"  {k:<26} rho={res[0]:+.2f}  p={res[1]:.3f}  n={n}")
        else:
            print(f"  {k:<26} n={n} (too few)")

    print(f"\nwrote {wells_csv}\nwrote {pairs_csv}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
