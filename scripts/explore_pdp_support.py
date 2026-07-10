"""Phase-1 exploration: PDP offset-support scores for Loving+Winkler novi_intel PUDs.

Read-only sibling of scripts/apply_reconciled_inventory.py (same skeleton:
etl.db.get_connection() on the 5432 session, statement_timeout=0, timed steps).
It computes the per-PUD offset-support attribute family for PUD sticks in
Loving+Winkler against the BASIN-WIDE qualifying-PDP universe (the PDP side is
NEVER county-filtered — a county-line PUD must see support across the border),
materializes it to a session TEMP table, and emits the review-gate artifacts:

  1. distribution table per county x formation_blueox + fixed-bucket histograms
  2. per-PUD CSV -> data/pdp_support_loving_winkler.csv
  3. --watch <file>  known-bad stick_id/unique_id percentile ranks within slice
  4. halo view: dist_nearest_ft distribution per formation_blueox
  5. EXPLAIN of the lateral body, asserting idx_curated_wells_wellstick_geog is hit

The offset-support attribute (curated.intel_pdp_support, keyed on stick_id) is a
VERIFIABILITY screen, not a quality screen: heavily depleted areas score high
support. `pdp_count_* = 0` means scored-and-unsupported; NULL scores mean
not-scorable (unmapped bench / missing TVD). See the handoff plan for the full
column contract.

No sql/NN file yet — the SQL lives inline here and graduates to sql/30 in Phase 2
with the county filter removed and category IN ('PUD','RES'). This is a stepped
build: this script produces the review-gate artifacts, then STOPS for the user to
tune the gate predicates / breakpoints and approve Phase 2.

Run from repo root in the venv (read-only; ~3 min for Loving+Winkler):
    python -m scripts.explore_pdp_support [--watch path/to/known_bad_ids.txt]
"""

from __future__ import annotations

import argparse
import csv
import statistics
import time
from pathlib import Path

from etl.db import get_connection

CSV_OUT = Path(__file__).resolve().parent.parent / "data" / "pdp_support_loving_winkler.csv"

# ---------------------------------------------------------------------------
# The one-pass neighbor scan. Materialized to a TEMP table so the downstream
# distribution / halo / watch / CSV passes all read the ~14k-row result instead
# of re-running the ~3 min scan. TEMP tables are session-local (pg_temp) — this
# writes nothing to any persistent/curated object, so the run stays read-only.
#
# Qualifying-PDP gate (EVERY predicate visible + TUNABLE — this is the review
# surface). Provenance:
#   is_horizontal      -> COALESCE(novi_slant_calculated, enverus_trajectory) ILIKE 'H%'
#                         (copied from sql/06_curated_derived.sql:108-112)
#   same formation     -> COALESCE(t.corrected_code, fb2.formation_blueox) = pud.code
#                         (TVD-corrected blueox convention, sql/21_reconciled_inventory.sql:121)
#   ST_DWithin text    -> w.wellstick_geom::geography, to match sql/26's expression
#                         GiST index idx_curated_wells_wellstick_geog (no seq scan)
# Radii: 1609 / 4827 / 8045 m ~= 1 / 3 / 5 mi (5 mi is the outer gate).
# ---------------------------------------------------------------------------
SCAN_SQL = """
CREATE TEMP TABLE pdp_support ON COMMIT PRESERVE ROWS AS
WITH pud AS (
    SELECT
        il.stick_id,
        il.unique_id,
        il.basin,
        il.county,
        fb.formation_blueox              AS code,        -- intel_formation_blueox (sql/19)
        il.tvd                           AS tvd,
        il.oil_eur                       AS oil_eur,
        il.ll_ft                         AS ll_ft,
        il.wellstick_geom::geography     AS g
    FROM curated.intel_locations il
    JOIN curated.intel_formation_blueox fb USING (stick_id)
    WHERE il.category = 'PUD'
      AND il.county IN ('Loving', 'Winkler')            -- title-case; Phase-1 PUD side ONLY
)
SELECT
    pud.stick_id,
    pud.unique_id,
    pud.basin,
    pud.county,
    pud.code                             AS formation_blueox,
    pud.tvd,
    pud.oil_eur,
    pud.ll_ft,
    agg.pdp_count_1mi,
    agg.pdp_count_3mi,
    agg.pdp_count_5mi,
    agg.dist_nearest_ft,
    agg.dist_3rd_nearest_ft,
    agg.support_lateral_ft_5mi,
    agg.n_offsets_5mi,
    agg.offset_median_eur_ft,
    agg.offset_median_cum12m_oil_per_ft,
    -- Novi PUD forecast per-ft vs the median of Novi's history-matched offsets.
    -- NULLIF guards both numerator (ll_ft) and denominator (offset median). NULL
    -- score when the bench/TVD is unknown (defensive; 0 such rows in L+W today).
    CASE
        WHEN pud.code IS NULL OR pud.tvd IS NULL THEN NULL
        ELSE (pud.oil_eur / NULLIF(pud.ll_ft, 0))
             / NULLIF(agg.offset_median_eur_ft, 0)
    END                                  AS inflation_ratio
FROM pud
LEFT JOIN LATERAL (
    SELECT
        count(*)                                                   AS pdp_count_5mi,
        count(*) FILTER (WHERE o.d <= 1609)                        AS pdp_count_1mi,
        count(*) FILTER (WHERE o.d <= 4827)                        AS pdp_count_3mi,
        min(o.d) * 3.28084                                         AS dist_nearest_ft,
        (array_agg(o.d ORDER BY o.d))[3] * 3.28084                 AS dist_3rd_nearest_ft,
        sum(o.ll)                                                  AS support_lateral_ft_5mi,
        count(*) FILTER (WHERE o.eur_ft IS NOT NULL)               AS n_offsets_5mi,
        percentile_cont(0.5) WITHIN GROUP (ORDER BY o.eur_ft)      AS offset_median_eur_ft,
        percentile_cont(0.5) WITHIN GROUP (ORDER BY o.cum12_ft)    AS offset_median_cum12m_oil_per_ft
    FROM (
        SELECT
            ST_Distance(w.wellstick_geom::geography, pud.g)         AS d,
            w.lateral_length_ft                                     AS ll,
            -- EUR gaps (~500 wells) -> NULL eur_ft: they still count as physical
            -- support (pdp_count_*) but drop out of the median (percentile_cont
            -- ignores NULL); n_offsets_5mi records the median's true sample size.
            w.eur_30yr_oil_bbl / NULLIF(w.lateral_length_ft, 0)     AS eur_ft,
            w.cum_12m_oil_bbl  / NULLIF(w.lateral_length_ft, 0)     AS cum12_ft
        FROM curated.wells w
        JOIN curated.formation_blueox fb2        ON fb2.api10 = w.api10
        LEFT JOIN curated.formation_blueox_tvd t ON t.api10   = w.api10
        WHERE ST_DWithin(w.wellstick_geom::geography, pud.g, 8045)                 -- TUNABLE: 5 mi outer gate
          AND COALESCE(w.novi_slant_calculated, w.enverus_trajectory) ILIKE 'H%'  -- TUNABLE: horizontal
          AND COALESCE(t.corrected_code, fb2.formation_blueox) = pud.code          -- TUNABLE: same formation_blueox
          AND abs(w.tvd_ft - pud.tvd) <= 500                                       -- TUNABLE: TVD guard +/- 500 ft
          AND w.first_production_date <= current_date - interval '12 months'       -- TUNABLE: >=12 mo since first prod
          AND w.lateral_length_ft > 0
    ) o
) agg ON TRUE
;
"""

# EXPLAIN of the lateral body for a single PUD (geom pinned via scalar subquery,
# which the planner folds to a constant just like the LATERAL param). Asserts the
# geography expression index — no seq scan of the 90k-row curated.wells.
EXPLAIN_SQL = """
EXPLAIN
SELECT count(*)
FROM curated.wells w
JOIN curated.formation_blueox fb2        ON fb2.api10 = w.api10
LEFT JOIN curated.formation_blueox_tvd t ON t.api10   = w.api10
WHERE ST_DWithin(
        w.wellstick_geom::geography,
        (SELECT il.wellstick_geom::geography FROM curated.intel_locations il WHERE il.stick_id = %s),
        8045)
  AND COALESCE(w.novi_slant_calculated, w.enverus_trajectory) ILIKE 'H%%'
  AND abs(w.tvd_ft - (SELECT il.tvd FROM curated.intel_locations il WHERE il.stick_id = %s)) <= 500
  AND w.first_production_date <= current_date - interval '12 months'
  AND w.lateral_length_ft > 0
;
"""

# Column order for the per-PUD CSV / in-memory rows.
COLS = [
    "stick_id", "unique_id", "basin", "county", "formation_blueox", "tvd",
    "oil_eur", "ll_ft", "pdp_count_1mi", "pdp_count_3mi", "pdp_count_5mi",
    "dist_nearest_ft", "dist_3rd_nearest_ft", "support_lateral_ft_5mi",
    "n_offsets_5mi", "offset_median_eur_ft", "offset_median_cum12m_oil_per_ft",
    "inflation_ratio",
]


def _pctile(values: list[float], q: float) -> float | None:
    """Linear-interpolated percentile of a non-empty sorted-or-unsorted list."""
    xs = sorted(v for v in values if v is not None)
    if not xs:
        return None
    if len(xs) == 1:
        return xs[0]
    pos = q * (len(xs) - 1)
    lo = int(pos)
    frac = pos - lo
    if lo + 1 >= len(xs):
        return xs[-1]
    return xs[lo] + frac * (xs[lo + 1] - xs[lo])


def _fmt(v: object, nd: int = 1) -> str:
    if v is None:
        return "  -  "
    if isinstance(v, float):
        return f"{v:,.{nd}f}"
    return str(v)


def build_temp_table(conn) -> int:
    """Run the neighbor scan into TEMP pdp_support; return row count."""
    t0 = time.monotonic()
    with conn.cursor() as cur:
        cur.execute("DROP TABLE IF EXISTS pdp_support")
        cur.execute(SCAN_SQL)
        n = cur.execute("SELECT count(*) FROM pdp_support").fetchone()[0]
    print(f"    scanned {n} Loving+Winkler PUDs in {time.monotonic() - t0:.0f}s", flush=True)
    return n


def fetch_rows(conn) -> list[dict]:
    with conn.cursor() as cur:
        cur.execute(f"SELECT {', '.join(COLS)} FROM pdp_support")
        return [dict(zip(COLS, r)) for r in cur.fetchall()]


def write_csv(rows: list[dict]) -> None:
    CSV_OUT.parent.mkdir(parents=True, exist_ok=True)
    with CSV_OUT.open("w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=COLS)
        w.writeheader()
        w.writerows(rows)
    print(f"    wrote {len(rows)} rows -> {CSV_OUT}", flush=True)


def print_distribution(conn) -> None:
    """Per county x formation_blueox: n + p10/p50/p90 of the headline metrics."""
    print("\n=== [1a] distribution per county x formation_blueox ===", flush=True)
    hdr = (f"{'county':8} {'blueox':10} {'n':>5} | "
           f"{'cnt5 p10/p50/p90':>20} | {'nearest_ft p10/50/90':>24} | "
           f"{'suppLL_ft p10/50/90':>27} | {'infl p10/50/90':>20}")
    print(hdr, flush=True)
    print("-" * len(hdr), flush=True)
    with conn.cursor() as cur:
        rows = cur.execute("""
            SELECT county, formation_blueox, count(*) AS n,
                   percentile_cont(0.10) WITHIN GROUP (ORDER BY pdp_count_5mi),
                   percentile_cont(0.50) WITHIN GROUP (ORDER BY pdp_count_5mi),
                   percentile_cont(0.90) WITHIN GROUP (ORDER BY pdp_count_5mi),
                   percentile_cont(0.10) WITHIN GROUP (ORDER BY dist_nearest_ft),
                   percentile_cont(0.50) WITHIN GROUP (ORDER BY dist_nearest_ft),
                   percentile_cont(0.90) WITHIN GROUP (ORDER BY dist_nearest_ft),
                   percentile_cont(0.10) WITHIN GROUP (ORDER BY support_lateral_ft_5mi),
                   percentile_cont(0.50) WITHIN GROUP (ORDER BY support_lateral_ft_5mi),
                   percentile_cont(0.90) WITHIN GROUP (ORDER BY support_lateral_ft_5mi),
                   percentile_cont(0.10) WITHIN GROUP (ORDER BY inflation_ratio),
                   percentile_cont(0.50) WITHIN GROUP (ORDER BY inflation_ratio),
                   percentile_cont(0.90) WITHIN GROUP (ORDER BY inflation_ratio)
            FROM pdp_support
            GROUP BY county, formation_blueox
            ORDER BY county, formation_blueox
        """).fetchall()
    for r in rows:
        (county, blueox, n, c10, c50, c90, d10, d50, d90,
         s10, s50, s90, i10, i50, i90) = r
        print(
            f"{county:8} {str(blueox):10} {n:>5} | "
            f"{_fmt(c10,0):>6}/{_fmt(c50,0):>6}/{_fmt(c90,0):>6} | "
            f"{_fmt(d10,0):>7}/{_fmt(d50,0):>7}/{_fmt(d90,0):>7} | "
            f"{_fmt(s10,0):>8}/{_fmt(s50,0):>8}/{_fmt(s90,0):>8} | "
            f"{_fmt(i10,2):>6}/{_fmt(i50,2):>6}/{_fmt(i90,2):>6}",
            flush=True,
        )


def print_histograms(conn) -> None:
    """Fixed-bucket histograms — the Phase-3 color-ramp candidates."""
    print("\n=== [1b] inflation_ratio histogram (color-ramp candidate) ===", flush=True)
    with conn.cursor() as cur:
        r = cur.execute("""
            SELECT
              count(*) FILTER (WHERE inflation_ratio < 0.5),
              count(*) FILTER (WHERE inflation_ratio >= 0.5  AND inflation_ratio < 0.8),
              count(*) FILTER (WHERE inflation_ratio >= 0.8  AND inflation_ratio < 1.25),
              count(*) FILTER (WHERE inflation_ratio >= 1.25 AND inflation_ratio < 1.75),
              count(*) FILTER (WHERE inflation_ratio >= 1.75),
              count(*) FILTER (WHERE inflation_ratio IS NULL)
            FROM pdp_support
        """).fetchone()
    labels = ["<0.5", "0.5-0.8", "0.8-1.25", "1.25-1.75", ">=1.75", "NULL"]
    for lab, cnt in zip(labels, r):
        print(f"    {lab:>10}: {cnt}", flush=True)

    print("\n=== [1c] pdp_count_3mi histogram (color-ramp candidate) ===", flush=True)
    with conn.cursor() as cur:
        r = cur.execute("""
            SELECT
              count(*) FILTER (WHERE pdp_count_3mi = 0),
              count(*) FILTER (WHERE pdp_count_3mi BETWEEN 1 AND 2),
              count(*) FILTER (WHERE pdp_count_3mi BETWEEN 3 AND 7),
              count(*) FILTER (WHERE pdp_count_3mi >= 8)
            FROM pdp_support
        """).fetchone()
    for lab, cnt in zip(["0 (unsupported)", "1-2", "3-7", "8+"], r):
        print(f"    {lab:>15}: {cnt}", flush=True)


def print_halo(conn) -> None:
    """Per formation_blueox dist_nearest_ft distribution — tests the halo model:
    credible PUD extent ~= PDP extent + a modest bench-dependent halo."""
    print("\n=== [4] halo view: dist_nearest_ft per formation_blueox ===", flush=True)
    hdr = (f"{'blueox':10} {'n':>5} {'nNULL':>6} | "
           f"{'p50':>8} {'p75':>8} {'p90':>8} {'p95':>8} {'max':>8}  "
           f"| histogram <1320/-2640/-5280/-10560/>= (ft)")
    print(hdr, flush=True)
    print("-" * len(hdr), flush=True)
    with conn.cursor() as cur:
        rows = cur.execute("""
            SELECT formation_blueox, count(*) AS n,
                   count(*) FILTER (WHERE dist_nearest_ft IS NULL) AS n_null,
                   percentile_cont(0.50) WITHIN GROUP (ORDER BY dist_nearest_ft),
                   percentile_cont(0.75) WITHIN GROUP (ORDER BY dist_nearest_ft),
                   percentile_cont(0.90) WITHIN GROUP (ORDER BY dist_nearest_ft),
                   percentile_cont(0.95) WITHIN GROUP (ORDER BY dist_nearest_ft),
                   max(dist_nearest_ft),
                   count(*) FILTER (WHERE dist_nearest_ft < 1320),
                   count(*) FILTER (WHERE dist_nearest_ft >= 1320 AND dist_nearest_ft < 2640),
                   count(*) FILTER (WHERE dist_nearest_ft >= 2640 AND dist_nearest_ft < 5280),
                   count(*) FILTER (WHERE dist_nearest_ft >= 5280 AND dist_nearest_ft < 10560),
                   count(*) FILTER (WHERE dist_nearest_ft >= 10560)
            FROM pdp_support
            GROUP BY formation_blueox
            ORDER BY formation_blueox
        """).fetchall()
    for r in rows:
        (blueox, n, n_null, p50, p75, p90, p95, mx, h1, h2, h3, h4, h5) = r
        print(
            f"{str(blueox):10} {n:>5} {n_null:>6} | "
            f"{_fmt(p50,0):>8} {_fmt(p75,0):>8} {_fmt(p90,0):>8} {_fmt(p95,0):>8} {_fmt(mx,0):>8}  "
            f"| {h1}/{h2}/{h3}/{h4}/{h5}",
            flush=True,
        )


def print_watch(rows: list[dict], watch_path: Path) -> None:
    """For each known-bad id, report its scores + percentile rank of inflation_ratio
    and pdp_count_3mi within its own county x formation_blueox slice. Success =
    known-bads cluster in low-count / high-ratio / NULL-ratio territory."""
    tokens = [
        ln.strip() for ln in watch_path.read_text(encoding="utf-8").splitlines()
        if ln.strip() and not ln.strip().startswith("#")
    ]
    if not tokens:
        print(f"\n=== [3] --watch: no ids in {watch_path} ===", flush=True)
        return

    by_stick = {str(r["stick_id"]): r for r in rows}
    by_uid = {str(r["unique_id"]): r for r in rows}
    # slice -> lists for ranking
    slices: dict[tuple, list[dict]] = {}
    for r in rows:
        slices.setdefault((r["county"], r["formation_blueox"]), []).append(r)

    print(f"\n=== [3] --watch known-bad ranks ({len(tokens)} ids) ===", flush=True)
    print("    (ratio pctile: fraction of slice at/below this ratio — HIGH = suspicious)", flush=True)
    print("    (count pctile: fraction of slice at/below this pdp_count_3mi — LOW = suspicious)", flush=True)
    for tok in tokens:
        r = by_stick.get(tok) or by_uid.get(tok)
        if r is None:
            print(f"  {tok:>18}: NOT FOUND in Loving+Winkler PUD set", flush=True)
            continue
        sl = slices[(r["county"], r["formation_blueox"])]
        # count percentile within slice
        cnts = [x["pdp_count_3mi"] for x in sl]
        cnt_pct = sum(1 for c in cnts if c <= r["pdp_count_3mi"]) / len(cnts)
        # ratio percentile within slice (over non-null ratios)
        ratios = [x["inflation_ratio"] for x in sl if x["inflation_ratio"] is not None]
        if r["inflation_ratio"] is None:
            ratio_pct_s = "NULL(no basis)"
        elif ratios:
            ratio_pct_s = f"{sum(1 for v in ratios if v <= r['inflation_ratio']) / len(ratios):.0%}"
        else:
            ratio_pct_s = "  -  "
        print(
            f"  {tok:>18} [{r['county']}/{r['formation_blueox']}, n_slice={len(sl)}]: "
            f"pdp_count_3mi={r['pdp_count_3mi']} (pctile {cnt_pct:.0%}), "
            f"nearest_ft={_fmt(r['dist_nearest_ft'],0)}, "
            f"inflation_ratio={_fmt(r['inflation_ratio'],2)} (pctile {ratio_pct_s})",
            flush=True,
        )


def assert_index(conn) -> None:
    """EXPLAIN the lateral body for one PUD; assert the geog expression index."""
    print("\n=== [5] EXPLAIN lateral body (index assertion) ===", flush=True)
    with conn.cursor() as cur:
        stick = cur.execute("SELECT stick_id FROM pdp_support ORDER BY pdp_count_5mi DESC LIMIT 1").fetchone()[0]
        plan = "\n".join(row[0] for row in cur.execute(EXPLAIN_SQL, (stick, stick)).fetchall())
    hit = "idx_curated_wells_wellstick_geog" in plan
    for line in plan.splitlines():
        print(f"    {line}", flush=True)
    print(f"\n    -> idx_curated_wells_wellstick_geog used: "
          f"{'YES' if hit else 'NO -- SEQ SCAN, investigate before Phase 2'}", flush=True)
    if not hit:
        print("    WARNING: geography expression index NOT engaged for stick_id "
              f"{stick}; the basin-wide build would seq-scan curated.wells.", flush=True)


def print_overall(rows: list[dict]) -> None:
    """Headline one-liners for quick eyeballing at the gate."""
    n = len(rows)
    zero3 = sum(1 for r in rows if r["pdp_count_3mi"] == 0)
    null_ratio = sum(1 for r in rows if r["inflation_ratio"] is None)
    lt3 = sum(1 for r in rows if r["dist_3rd_nearest_ft"] is None)
    ratios = [r["inflation_ratio"] for r in rows if r["inflation_ratio"] is not None]
    print("\n=== [0] overall (Loving+Winkler PUDs) ===", flush=True)
    print(f"    total PUDs scored: {n}", flush=True)
    print(f"    pdp_count_3mi == 0 (unsupported in-bench @3mi): {zero3} ({zero3/n:.1%})", flush=True)
    print(f"    <3 qualifying offsets (dist_3rd NULL): {lt3} ({lt3/n:.1%})", flush=True)
    print(f"    inflation_ratio NULL (no offset median): {null_ratio} ({null_ratio/n:.1%})", flush=True)
    if ratios:
        print(f"    inflation_ratio median/mean: "
              f"{statistics.median(ratios):.2f} / {statistics.fmean(ratios):.2f} "
              f"(n={len(ratios)})", flush=True)


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--watch", type=Path, default=None,
                    help="file of known-bad stick_id/unique_id (one per line) to rank")
    args = ap.parse_args()

    t = time.monotonic()
    conn = get_connection()  # 5432 session, statement_timeout=0, keepalives
    try:
        conn.autocommit = True  # keep the TEMP table alive across statements
        print("[1/3] neighbor scan -> TEMP pdp_support (Loving+Winkler, ~3 min)", flush=True)
        build_temp_table(conn)

        print("[2/3] fetch + CSV", flush=True)
        rows = fetch_rows(conn)
        write_csv(rows)

        print("[3/3] review-gate artifacts", flush=True)
        print_overall(rows)
        print_distribution(conn)
        print_histograms(conn)
        print_halo(conn)
        if args.watch is not None:
            print_watch(rows, args.watch)
        else:
            print("\n=== [3] --watch skipped (no --watch file given) ===", flush=True)
        assert_index(conn)
    finally:
        conn.close()
    print(f"\n=== DONE in {time.monotonic() - t:.0f}s. HARD STOP -- review + approve Phase 2. ===", flush=True)


if __name__ == "__main__":
    main()
