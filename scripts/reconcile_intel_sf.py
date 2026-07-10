"""Reconcile a freshly loaded intel vintage against the curated layer in prod.

Builds qa.intel_locations_sf (the exact SELECT from sql/29, extracted between
its BEGIN/END markers) WITHOUT touching curated.intel_locations, then diffs
the two and writes a markdown report to logs/intel_sf_reconcile_<date>.md.

Originally the phase-5 migration gate (same-vintage: everything reconciled
EXACT, 2026-07-08). Retained as the quarterly pre-cutover drift check: after
`load_intel_sf --all --report <new>` lands a new vintage in raw_intel, run this
BEFORE `--curated` — qa (new vintage) vs curated.intel_locations (live vintage)
is then a quarter-over-quarter drift report, reviewed at the reload gate.
The phase-5 sections that compared against the legacy raw_novi_intel tables
(Arps params, forecast spot-check) were removed 2026-07-10 when those tables
were dropped; their exact-match results are recorded in the migration plan.

NOTE: build_qa executes DDL in the qa schema (CREATE SCHEMA / matview) —
Supabase writes need the usual authorization. Drop the qa schema when done.

    python -m scripts.reconcile_intel_sf              # build qa + full report
    python -m scripts.reconcile_intel_sf --skip-build # re-report on existing qa
"""

from __future__ import annotations

import argparse
import datetime as dt
import logging
import re
from pathlib import Path

from etl.db import get_connection

logger = logging.getLogger(__name__)
SQL_DIR = Path(__file__).resolve().parents[1] / "sql"

CATS = ("PDP", "PUD", "RES")


def _md(headers: list[str], rows: list[tuple]) -> list[str]:
    out = ["| " + " | ".join(headers) + " |",
           "|" + "|".join("---" for _ in headers) + "|"]
    for r in rows:
        out.append("| " + " | ".join("" if v is None else str(v) for v in r) + " |")
    return out


def _select_from_sql29() -> str:
    text = (SQL_DIR / "29_curated_intel_sf.sql").read_text(encoding="utf-8")
    m = re.search(
        r"-- BEGIN INTEL_LOCATIONS_SELECT.*?\n(.*)-- END INTEL_LOCATIONS_SELECT",
        text, re.DOTALL,
    )
    if not m:
        raise RuntimeError("SELECT markers not found in sql/29_curated_intel_sf.sql")
    return m.group(1)


def build_qa(cur) -> None:
    logger.info("building qa.intel_locations_sf (this is the heavy step)...")
    cur.execute("CREATE SCHEMA IF NOT EXISTS qa")
    cur.execute("DROP MATERIALIZED VIEW IF EXISTS qa.intel_locations_sf")
    cur.execute(f"CREATE MATERIALIZED VIEW qa.intel_locations_sf AS\n{_select_from_sql29()}")
    cur.execute("CREATE UNIQUE INDEX ON qa.intel_locations_sf (stick_id)")
    cur.execute("CREATE INDEX ON qa.intel_locations_sf (basin, category, unique_id)")
    cur.execute("ANALYZE qa.intel_locations_sf")
    logger.info("qa.intel_locations_sf built")


def q(cur, sql: str, params: tuple = ()) -> list[tuple]:
    cur.execute(sql, params)
    return cur.fetchall()


def sec_counts(cur) -> list[str]:
    rows = q(cur, """
        SELECT COALESCE(o.basin, n.basin) AS basin,
               COALESCE(o.category, n.category) AS category,
               o.n AS old_n, n.n AS new_n,
               COALESCE(n.n, 0) - COALESCE(o.n, 0) AS delta
        FROM (SELECT basin, category, count(*) n FROM curated.intel_locations GROUP BY 1,2) o
        FULL JOIN (SELECT basin, category, count(*) n FROM qa.intel_locations_sf GROUP BY 1,2) n
          USING (basin, category)
        ORDER BY 1, 2""")
    return _md(["basin", "category", "old", "new", "delta"], rows)


def sec_formations(cur) -> list[str]:
    rows = q(cur, """
        SELECT COALESCE(o.formation, n.formation) AS formation,
               o.n AS old_n, n.n AS new_n
        FROM (SELECT UPPER(formation) formation, count(*) n
              FROM curated.intel_locations WHERE category != 'PDP' GROUP BY 1) o
        FULL JOIN (SELECT UPPER(formation) formation, count(*) n
                   FROM qa.intel_locations_sf WHERE category != 'PDP' GROUP BY 1) n
          USING (formation)
        WHERE COALESCE(o.n, 0) != COALESCE(n.n, 0)
        ORDER BY abs(COALESCE(n.n, 0) - COALESCE(o.n, 0)) DESC LIMIT 25""")
    if not rows:
        return ["- formation distributions identical (PUD/RES)"]
    return ["Formations with count differences (PUD/RES only):"] + \
        _md(["formation", "old", "new"], rows)


_VALUE_COLS = ("oil_eur", "gas_eur", "npv10", "npv25", "irr_pct", "tvd", "ll_ft",
               "pp_months", "ttpt", "dc_cost", "oil_ip")


def sec_values(cur) -> list[str]:
    out = ["Relative deviation |new-old|/|old| on sticks joined by (basin, category, unique_id):", ""]
    rows = []
    for col in _VALUE_COLS:
        r = q(cur, f"""
            SELECT %s AS col, count(*) AS joined,
                   count(*) FILTER (WHERE o.{col} IS NOT NULL AND n.{col} IS NOT NULL) AS both_nn,
                   round(percentile_cont(0.5) WITHIN GROUP (
                       ORDER BY abs(n.{col} - o.{col}) / NULLIF(abs(o.{col}), 0))::numeric, 6) AS p50,
                   round(percentile_cont(0.9) WITHIN GROUP (
                       ORDER BY abs(n.{col} - o.{col}) / NULLIF(abs(o.{col}), 0))::numeric, 6) AS p90,
                   round(max(abs(n.{col} - o.{col}) / NULLIF(abs(o.{col}), 0))::numeric, 4) AS max
            FROM curated.intel_locations o
            JOIN qa.intel_locations_sf n
              ON n.basin = o.basin AND n.category = o.category AND n.unique_id = o.unique_id
            WHERE o.{col} IS NOT NULL AND n.{col} IS NOT NULL""", (col,))
        rows.append(r[0])
    out += _md(["column", "joined", "both non-null", "p50 rel dev", "p90 rel dev", "max"], rows)
    return out


def sec_geometry(cur) -> list[str]:
    rows = q(cur, """
        SELECT count(*),
               count(*) FILTER (WHERE h_m < 10) AS under_10m,
               round(max(h_m)::numeric, 1) AS max_m
        FROM (
            SELECT ST_HausdorffDistance(o.wellstick_geom, n.wellstick_geom) * 111000 AS h_m
            FROM curated.intel_locations o
            JOIN qa.intel_locations_sf n
              ON n.basin = o.basin AND n.category = o.category AND n.unique_id = o.unique_id
            WHERE o.wellstick_geom IS NOT NULL AND n.wellstick_geom IS NOT NULL
            LIMIT 1000
        ) s""")
    n, ok, mx = rows[0]
    return [f"- 1,000-stick sample: {ok}/{n} within 10 m Hausdorff; max {mx} m (approx, 111 km/deg)"]


def sec_pad_npv(cur) -> list[str]:
    rows = q(cur, """
        SELECT count(*) AS pads_joined,
               round(percentile_cont(0.5) WITHIN GROUP (
                   ORDER BY abs(n.pad_npv25 - o.pad_npv25) / NULLIF(abs(o.pad_npv25), 0))::numeric, 4) AS p50,
               round(percentile_cont(0.9) WITHIN GROUP (
                   ORDER BY abs(n.pad_npv25 - o.pad_npv25) / NULLIF(abs(o.pad_npv25), 0))::numeric, 4) AS p90
        FROM (SELECT basin, pad_name, max(pad_npv25) pad_npv25
              FROM curated.intel_locations WHERE pad_npv25 IS NOT NULL GROUP BY 1,2) o
        JOIN (SELECT basin, pad_name, max(pad_npv25) pad_npv25
              FROM qa.intel_locations_sf WHERE pad_npv25 IS NOT NULL GROUP BY 1,2) n
          USING (basin, pad_name)""")
    cov = q(cur, """
        SELECT basin, category, count(pad_name) AS with_pad, count(*) AS total
        FROM qa.intel_locations_sf GROUP BY 1,2 ORDER BY 1,2""")
    out = ["pad_npv25 old (shapefile rollup) vs new (SUM of member sticks), joined pads:"]
    out += _md(["pads joined", "p50 rel dev", "p90 rel dev"], rows)
    out += ["", "pad_name coverage in new layer (share gap: Delaware BASE_CASE only):"]
    out += _md(["basin", "category", "with pad_name", "total"], cov)
    return out


def sec_ml_tiers(cur) -> list[str]:
    rows = q(cur, """
        SELECT COALESCE(o.t, n.t) AS tier, o.n AS old_n, n.n AS new_n
        FROM (SELECT rqt t, count(*) n FROM curated.intel_locations
              WHERE rqt IS NOT NULL GROUP BY 1) o
        FULL JOIN (SELECT rqt t, count(*) n FROM qa.intel_locations_sf
                   WHERE rqt IS NOT NULL GROUP BY 1) n USING (t)
        ORDER BY 1""")
    out = ["Rock-quality tier distribution (old vs new, all categories):"]
    out += _md(["tier", "old", "new"], rows)
    rows2 = q(cur, """
        SELECT COALESCE(o.t, n.t) AS tier, o.n AS old_n, n.n AS new_n
        FROM (SELECT spacing_t t, count(*) n FROM curated.intel_locations
              WHERE spacing_t IS NOT NULL GROUP BY 1) o
        FULL JOIN (SELECT spacing_t t, count(*) n FROM qa.intel_locations_sf
                   WHERE spacing_t IS NOT NULL GROUP BY 1) n USING (t)
        ORDER BY 1""")
    out += ["", "Spacing tier distribution:"]
    out += _md(["tier", "old", "new"], rows2)
    return out


def main() -> None:
    ap = argparse.ArgumentParser(description="Reconcile qa.intel_locations_sf vs production.")
    ap.add_argument("--skip-build", action="store_true", help="reuse existing qa matview")
    args = ap.parse_args()

    lines = [f"# intel_sf reconciliation - {dt.date.today().isoformat()}",
             "", "Old = curated.intel_locations (live vintage in prod). "
                 "New = qa.intel_locations_sf (sql/29 SELECT over current raw_intel).", ""]
    sections = (
        ("1. Row counts per (basin, category)", sec_counts),
        ("2. Formation distribution (PUD/RES)", sec_formations),
        ("3. Value deviations on joined sticks", sec_values),
        ("4. Geometry sample", sec_geometry),
        ("5. pad_npv25 + pad coverage", sec_pad_npv),
        ("6. ML tier distributions", sec_ml_tiers),
    )
    with get_connection() as conn, conn.cursor() as cur:
        if not args.skip_build:
            build_qa(cur)
            conn.commit()
        for title, fn in sections:
            lines += [f"## {title}", ""]
            try:
                lines += fn(cur)
            except Exception as exc:
                logger.exception("section failed: %s", title)
                lines.append(f"**SECTION FAILED:** `{exc}`")
                conn.rollback()
            lines.append("")

    report = "\n".join(lines)
    out = Path("logs") / f"intel_sf_reconcile_{dt.date.today():%Y%m%d}.md"
    out.parent.mkdir(exist_ok=True)
    out.write_text(report, encoding="utf-8")
    print(report)
    print(f"\n[written to {out}]")


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
    main()
