"""Read-only profiling of the Novi INTEL Snowflake share.

Originally the phase-1 migration gate; retained as the pre-load sanity check
for each new quarterly report (run it before scripts/load_intel_sf on a fresh
collection). Sections:
  1. session context (proves PAT auth + reader-account wiring)
  2. visible collections (entitled basins / vintages)
  3. per-view row counts
  4. PRODUCTION_FORECAST grain (daily vs 30-day vs calendar-month) + volume
  5. WELL.UWI_API length histogram (api10 vs api14 truncation check)
  6. ARPS_FORECAST stream/segment coverage
  7. formation strings vs ref.formation_crosswalk (sql/19 tier-3 coverage)
  8. key semantics: EUR/PV columns, IRR units, price decks, PAD lat/lon
  9. trajectory geometry sanity (WKT type / CRS)

The comparisons against the legacy raw_novi_intel file-drop tables were removed
2026-07-10 when those tables were dropped (phase 8); the phase-1 answers they
produced live in logs/intel_sf_profile_20260708.md and the migration plan.

Read-only on BOTH sides (Snowflake share + Postgres warehouse). Emits a
markdown report to stdout and logs/intel_sf_profile_<date>.md.

RUN: python -m etl.intel_sf.profile
"""

from __future__ import annotations

import datetime as dt
import logging
from pathlib import Path
from typing import Callable

from etl.db import get_connection
from etl.intel_sf.client import get_sf_connection

logger = logging.getLogger(__name__)

# Historical row counts of the retired static-drop raw layer (both basins,
# 3Q25) — kept as an order-of-magnitude yardstick in section 3.
_STATIC_COUNTS = {
    "sticks": 248_000,
    "pud_attrs": 131_000,
    "analytics": 23_000,
    "arps": 200_000,
    "forecast": 74_000_000,
}

_ALL_VIEWS = (
    "ARPS_FORECAST", "BASIN", "ECON_PRICE_ASSUMPTION", "INVENTORY_FORECAST",
    "ML_SCORE", "OPERATOR", "PAD", "PLANNED_WELL",
    "PRODUCTION_ARPS_SEGMENT_PARAMETER", "PRODUCTION_FORECAST", "SOURCE",
    "SURFACE_LOCATION", "WELL", "WELLBORE", "WELLBORE_TRAJECTORY",
    "WELL_COMPLETION", "WELL_COST_SUMMARY", "WELL_ECONOMICS",
    "WELL_ECONOMICS_SUMMARY", "WELL_MASTER", "WELL_ML_SCORE",
    "WELL_ROCK_QUALITY",
)


def _md_table(headers: list[str], rows: list[tuple]) -> list[str]:
    out = ["| " + " | ".join(headers) + " |",
           "|" + "|".join("---" for _ in headers) + "|"]
    for r in rows:
        out.append("| " + " | ".join("" if v is None else str(v) for v in r) + " |")
    return out


def _sf(cur, sql: str) -> list[tuple]:
    cur.execute(sql)
    return cur.fetchall()


def _pg(conn, sql: str, params: tuple = ()) -> list[tuple]:
    with conn.cursor() as cur:
        cur.execute(sql, params)
        return cur.fetchall()


# --------------------------------------------------------------------------
# sections — each returns markdown lines
# --------------------------------------------------------------------------

def section_session(cur, pg) -> list[str]:
    rows = _sf(cur, "SELECT current_account(), current_role(), "
                    "current_warehouse(), current_database(), current_schema()")
    a, r, w, d, s = rows[0]
    return [f"- account: `{a}`  role: `{r}`  warehouse: `{w}`",
            f"- database: `{d}`  schema: `{s}`"]


def section_collections(cur, pg) -> list[str]:
    rows = _sf(cur, "SELECT DISTINCT collection FROM SOURCE ORDER BY 1")
    out = [f"- {len(rows)} visible collection(s):"]
    out += [f"  - `{r[0]}`" for r in rows]
    has_3q25 = any("2025Q3" in str(r[0]) for r in rows)
    out.append(f"- **3Q25-matching vintage visible: {'YES - exact reconciliation possible' if has_3q25 else 'NO - phase-5 reconciliation will be drift analysis vs a newer vintage'}**")
    return out


def section_row_counts(cur, pg) -> list[str]:
    rows = []
    for v in _ALL_VIEWS:
        try:
            n = _sf(cur, f"SELECT count(*) FROM {v}")[0][0]
        except Exception as exc:  # entitlement gaps show up here
            n = f"ERROR: {exc}"
        rows.append((v, n))
    out = _md_table(["view", "rows"], rows)
    out.append("")
    out.append("Retired static-drop reference (both basins, 3Q25; historical yardstick): "
               + ", ".join(f"{k} ~{v:,}" for k, v in _STATIC_COUNTS.items()))
    out.append("")
    out.append("WELL_MASTER by report / inventory class:")
    wm = _sf(cur, "SELECT report_name, inventory_class, count(*) "
                  "FROM WELL_MASTER GROUP BY 1, 2 ORDER BY 1, 2")
    out += _md_table(["report_name", "inventory_class", "rows"], wm)
    return out


def section_forecast_grain(cur, pg) -> list[str]:
    out = ["PRODUCTION_FORECAST by granularity / scenario:"]
    g = _sf(cur, """
        SELECT period_granularity, scenario, count(*) AS n_rows,
               count(DISTINCT coalesce(well_id, planned_well_id)) AS wells,
               round(count(*) / nullif(count(DISTINCT coalesce(well_id, planned_well_id)), 0), 1) AS rows_per_well
        FROM PRODUCTION_FORECAST GROUP BY 1, 2 ORDER BY 1, 2""")
    out += _md_table(["granularity", "scenario", "rows", "wells", "rows/well"], g)

    out += ["", "FORECAST_DAY step distribution (100-well sample):"]
    steps = _sf(cur, """
        WITH sample_wells AS (
            SELECT DISTINCT coalesce(well_id, planned_well_id) AS wid
            FROM PRODUCTION_FORECAST LIMIT 100
        ), diffs AS (
            SELECT pf.forecast_day
                   - lag(pf.forecast_day) OVER (
                       PARTITION BY coalesce(pf.well_id, pf.planned_well_id),
                                    pf.period_granularity, pf.scenario
                       ORDER BY pf.forecast_day) AS step
            FROM PRODUCTION_FORECAST pf
            JOIN sample_wells s ON s.wid = coalesce(pf.well_id, pf.planned_well_id)
        )
        SELECT step, count(*) FROM diffs WHERE step IS NOT NULL
        GROUP BY 1 ORDER BY 2 DESC LIMIT 10""")
    out += _md_table(["day step", "occurrences"], steps)
    if steps:
        top = steps[0][0]
        verdict = {1: "TRULY DAILY", 30: "30-day steps (matches old ip_day semantics)"}.get(
            top, f"dominant step = {top} days")
        out.append(f"- **verdict: {verdict}**")

    out += ["", "INVENTORY_FORECAST by granularity / scenario:"]
    inv = _sf(cur, """
        SELECT period_granularity, scenario, count(*) AS n_rows,
               count(DISTINCT well_ref) AS wells
        FROM INVENTORY_FORECAST GROUP BY 1, 2 ORDER BY 1, 2""")
    out += _md_table(["granularity", "scenario", "rows", "wells"], inv)
    return out


def section_uwi_length(cur, pg) -> list[str]:
    rows = _sf(cur, "SELECT length(uwi_api), count(*) FROM WELL GROUP BY 1 ORDER BY 1")
    out = _md_table(["length(UWI_API)", "wells"], rows)
    lens = {r[0] for r in rows if r[0] is not None}
    if lens == {10}:
        out.append("- **all api10: no truncation needed in the crosswalk join**")
    elif 14 in lens or any(isinstance(x, int) and x > 10 for x in lens):
        out.append("- **lengths >10 present: use LEFT(uwi_api, 10) for the api10 crosswalk**")
    return out


def section_arps_coverage(cur, pg) -> list[str]:
    rows = _sf(cur, """
        SELECT inventory_class, stream, count(*) AS segments,
               count(DISTINCT well_ref) AS wells,
               round(count(*) / nullif(count(DISTINCT well_ref), 0), 2) AS seg_per_well
        FROM ARPS_FORECAST GROUP BY 1, 2 ORDER BY 1, 2""")
    return _md_table(["inventory_class", "stream", "segments", "wells", "seg/well"], rows)


def section_formations(cur, pg) -> list[str]:
    sf_forms = {str(r[0]) for r in _sf(
        cur, "SELECT DISTINCT upper(target_formation) FROM PLANNED_WELL "
             "WHERE target_formation IS NOT NULL")}
    sf_forms |= {str(r[0]) for r in _sf(
        cur, "SELECT DISTINCT upper(formation) FROM WELLBORE "
             "WHERE formation IS NOT NULL")}
    cx = {str(r[0]) for r in _pg(
        pg, "SELECT DISTINCT raw_value FROM ref.formation_crosswalk")}
    missing = sorted(sf_forms - cx)
    out = [f"- {len(sf_forms)} distinct formation strings in the share; "
           f"{len(sf_forms & cx)} covered by ref.formation_crosswalk"]
    if missing:
        out.append(f"- **{len(missing)} NOT in the crosswalk** (sql/19 tier-3 gaps; "
                   "spatial inference or crosswalk additions needed):")
        out += [f"  - `{m}`" for m in missing[:40]]
        if len(missing) > 40:
            out.append(f"  - ... and {len(missing) - 40} more")
    else:
        out.append("- full crosswalk coverage")
    return out


def section_key_semantics(cur, pg) -> list[str]:
    out: list[str] = []

    # Column inventory (the live view drifts from the PDF dictionary).
    cols = [str(r[0]) for r in _sf(cur, """
        SELECT column_name FROM NOVI_DATA_ACCESS.INFORMATION_SCHEMA.COLUMNS
        WHERE table_schema = 'NOVI_INTEL' AND table_name = 'WELL_ECONOMICS_SUMMARY'
        ORDER BY ordinal_position""")]
    pv_cols = [c for c in cols if c.startswith("PV")]
    eur_oil_cols = [c for c in cols if c.startswith("EUR_OIL")]
    out += ["", f"- WELL_ECONOMICS_SUMMARY: {len(cols)} columns: {', '.join(cols)}",
            f"- PV columns present: {pv_cols or 'NONE - pv5..pv25 will carry NULLs'}",
            f"- EUR oil columns present: {eur_oil_cols or 'NONE'} "
            "(sql/29 maps EUR_*_30YR — the only horizon shipped as of 2025Q3; "
            "a new/vanished horizon here means sql/29 needs a look)"]

    # IRR units (share bug as of 2025Q3: unit inconsistent by slice — sql/29
    # keeps a slice-median calibration that self-heals if Novi fixes it)
    irr = _sf(cur, "SELECT median(abs(irr)), min(irr), max(irr), count(irr) "
                   "FROM WELL_ECONOMICS_SUMMARY")[0]
    unit = "FRACTION (multiply by 100 for irr_pct)" if irr[0] is not None and float(irr[0]) < 5 \
        else "PERCENT (pass through)"
    out += ["", f"- IRR: median|irr|={irr[0]}, range [{irr[1]}, {irr[2]}], n={irr[3]} "
                f"- **{unit}** (global median; sql/29 calibrates per slice)"]

    # price decks
    decks = _sf(cur, """
        SELECT DISTINCT price_deck_id, name, oil_price, gas_price, ngl_price,
               oil_price_differential, gas_price_differential
        FROM ECON_PRICE_ASSUMPTION LIMIT 20""")
    out += ["", "Price decks (old static drop assumed flat $75 WTI / $3 HH):"]
    out += _md_table(["deck_id", "name", "oil", "gas", "ngl", "oil diff", "gas diff"], decks)

    # PAD population
    pad = _sf(cur, "SELECT count(*), count(latitude), count(longitude) FROM PAD")[0]
    out.append(f"- PAD: {pad[0]} rows, latitude populated on {pad[1]}, longitude on {pad[2]} "
               "(expected 0 - frozen legacy polygons stay)")
    return out


def section_geometry(cur, pg) -> list[str]:
    sample = _sf(cur, """
        SELECT w.uwi_api, t.geometry_wkt, t.crs
        FROM WELLBORE_TRAJECTORY t
        JOIN WELLBORE wb ON wb.wellbore_id = t.wellbore_id
        JOIN WELL w ON w.well_id = wb.well_id
        WHERE t.geometry_wkt IS NOT NULL LIMIT 20""")
    if not sample:
        return ["- no PDP trajectories returned - check entitlement/joins"]
    out = [f"- sample of {len(sample)} PDP trajectories; CRS values: "
           f"{sorted({str(r[2]) for r in sample})}"]
    kinds = {str(r[1]).split("(")[0].strip().upper() for r in sample}
    out.append(f"- WKT geometry types: {sorted(kinds)} "
               "(expect LINESTRING, EPSG:4326 — anything else breaks the sql/27 WKT->geom hook)")
    return out


_SECTIONS: tuple[tuple[str, Callable], ...] = (
    ("1. Session context", section_session),
    ("2. Visible collections", section_collections),
    ("3. Row counts (all 22 views)", section_row_counts),
    ("4. PRODUCTION_FORECAST grain", section_forecast_grain),
    ("5. UWI_API length", section_uwi_length),
    ("6. ARPS_FORECAST coverage", section_arps_coverage),
    ("7. Formation crosswalk coverage", section_formations),
    ("8. Key semantics (EUR/PV columns, IRR units, decks, PAD)", section_key_semantics),
    ("9. Trajectory geometry sanity", section_geometry),
)


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    lines = [f"# Novi INTEL share profiling - {dt.date.today().isoformat()}", ""]
    sf = get_sf_connection()
    pg = get_connection()
    try:
        with sf.cursor() as cur:
            for title, fn in _SECTIONS:
                lines += [f"## {title}", ""]
                try:
                    lines += fn(cur, pg)
                except Exception as exc:
                    logger.exception("profiling section failed: %s", title)
                    lines.append(f"**SECTION FAILED:** `{exc}`")
                    pg.rollback()  # clear any aborted PG transaction
                lines.append("")
    finally:
        sf.close()
        pg.close()

    report = "\n".join(lines)
    out_dir = Path("logs")
    out_dir.mkdir(exist_ok=True)
    out_path = out_dir / f"intel_sf_profile_{dt.date.today():%Y%m%d}.md"
    out_path.write_text(report, encoding="utf-8")
    print(report)
    print(f"\n[written to {out_path}]")


if __name__ == "__main__":
    main()
