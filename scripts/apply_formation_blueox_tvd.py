"""Build curated.formation_blueox_tvd (TVD-sanity audit + recolor) on Supabase.

  1. formation_blueox_tvd (sql/23) — per-well 40-NN local depth profile + flip
     decision (heavy KNN over ~59k producing horizontals).
  2. Validate: how many flip, what flips to what, how many rest on permit-suspect
     depths, and the two anchored spot-checks (3002550278 -> WCA_1; 3002550282 stays).

Run from repo root in the venv:
    python -m scripts.apply_formation_blueox_tvd
"""

from __future__ import annotations

import time
from pathlib import Path

from etl.db import get_connection

SQL = Path(__file__).resolve().parent.parent / "sql"


def main() -> None:
    t = time.monotonic()
    print("[1/2] build curated.formation_blueox_tvd (40-NN depth profile — heavy)", flush=True)
    text = (SQL / "23_formation_blueox_tvd.sql").read_text(encoding="utf-8")
    conn = get_connection()
    try:
        conn.autocommit = True
        with conn.cursor() as cur:
            cur.execute(text)
        print(f"    built in {time.monotonic() - t:.0f}s", flush=True)
    finally:
        conn.close()

    print("[2/2] validation", flush=True)
    conn = get_connection()
    try:
        conn.autocommit = True
        with conn.cursor() as cur:
            total, flips = cur.execute(
                "SELECT COUNT(*), COUNT(*) FILTER (WHERE corrected) FROM curated.formation_blueox_tvd"
            ).fetchone()
            print(f"  {flips} / {total} producing horizontals recolored "
                  f"({100.0 * flips / total:.2f}%)", flush=True)

            print("  flips by basin:", flush=True)
            for b, n in cur.execute(
                "SELECT basin, COUNT(*) FROM curated.formation_blueox_tvd "
                "WHERE corrected GROUP BY 1 ORDER BY 1"
            ).fetchall():
                print(f"    {b:9} {n}", flush=True)

            print("  flips by permit-suspect (provisional depth driving the flip):", flush=True)
            for ps, tr, n in cur.execute(
                "SELECT permit_suspect, tvd_round, COUNT(*) FROM curated.formation_blueox_tvd "
                "WHERE corrected GROUP BY 1,2 ORDER BY 1,2"
            ).fetchall():
                print(f"    permit_suspect={str(ps):5} tvd_round={str(tr):5} {n}", flush=True)

            print("  top flip transitions (assigned -> corrected):", flush=True)
            for ac, cc, b, n in cur.execute(
                "SELECT assigned_code, corrected_code, basin, COUNT(*) "
                "FROM curated.formation_blueox_tvd WHERE corrected "
                "GROUP BY 1,2,3 ORDER BY 4 DESC LIMIT 20"
            ).fetchall():
                print(f"    {b:9} {ac:6} -> {cc:6}  {n}", flush=True)

            print("  WDFD/BRNT/MISS or sand<->carb still flipping? (should be 0):", flush=True)
            bad = cur.execute(
                "SELECT COUNT(*) FROM curated.formation_blueox_tvd WHERE corrected AND ("
                "assigned_code IN ('WDFD','BRNT','MISS') OR corrected_code IN ('WDFD','BRNT','MISS') "
                "OR (left(assigned_code,3)=left(corrected_code,3) AND right(assigned_code,1) IN ('S','C') "
                "AND right(corrected_code,1) IN ('S','C') AND right(assigned_code,1)<>right(corrected_code,1)))"
            ).fetchone()[0]
            print(f"    {bad}", flush=True)

            print("  spot-checks (incl. band support n):", flush=True)
            for api in ("3002550278", "3002550282"):
                row = cur.execute(
                    "SELECT assigned_code, corrected_code, corrected, ROUND(tvd)::int, "
                    "ROUND(assigned_med)::int, assigned_gap, assigned_n, nearest_code, nearest_gap, "
                    "nearest_n, tvd_round, survey_planned "
                    "FROM curated.formation_blueox_tvd WHERE api10=%s", (api,)
                ).fetchone()
                if row is None:
                    print(f"    {api}: (not in producing_reference)", flush=True)
                    continue
                ac, cc, corr, tvd, amed, agap, an, nc, ngap, nn, tr, sp = row
                print(f"    {api}: {ac}(n={an}) -> {cc}  corrected={corr}  tvd={tvd} "
                      f"assigned_med={amed} (gap {agap})  nearest={nc}(n={nn}, gap {ngap})  "
                      f"round={tr} planned={sp}", flush=True)
    finally:
        conn.close()
    print(f"=== DONE in {time.monotonic() - t:.0f}s ===", flush=True)


if __name__ == "__main__":
    main()
