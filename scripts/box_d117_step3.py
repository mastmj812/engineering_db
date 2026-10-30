"""D117 step 3 — does the rehearsed record reproduce the live record row for row? READ-ONLY on both databases.

    python -m scripts.box_d117_step3 compare --run-id N [--live-run 19] --out docs/box/universe-2026-10-21/step3
        Run N in the `scripts.box_rehearsal` container vs run --live-run on live, keyed by location_id (the container is seeded from
        live box.location, so a carried stick keeps its id). Per table, every column of every row the live run holds is compared;
        months by an exact per-(location, stream) md5 of the volumes in month order. Rows only the container holds are the D117
        additions; they are counted by category, bench and coverage. Writes compare.json + additions.csv (+ differences.csv when any).
    python -m scripts.box_d117_step3 midland --out docs/box/universe-2026-10-21/step3
        The Midland universe under the D117 SQL: RES sticks inside the stored Midland records, per bench (no Midland run exists yet).
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path
from typing import Any

import pandas as pd
import psycopg

from box import production as pr
from etl.db import get_connection

# keyed row images (every column but run_id). Fixed SQL; the run id is the only parameter.
TABLES: dict[str, tuple[str, tuple[str, ...]]] = {
    "pud_forecast": ("SELECT location_id, (to_jsonb(t) - 'run_id')::text FROM box.pud_forecast t WHERE run_id = %s", ("location_id",)),
    "pud_forecast_stream": ("SELECT location_id, stream, (to_jsonb(t) - 'run_id')::text FROM box.pud_forecast_stream t WHERE run_id = %s",
                            ("location_id", "stream")),
    "pud_forecast_month": (("SELECT location_id, stream, count(*)::text || ':' || md5(string_agg(volume::text, ',' ORDER BY month_no)) "
                            "FROM box.pud_forecast_month WHERE run_id = %s GROUP BY 1, 2"), ("location_id", "stream")),
    "location_analog": (("SELECT location_id, md5(string_agg((to_jsonb(t) - 'run_id')::text, ',' ORDER BY api10)) FROM box.location_analog t "
                         "WHERE run_id = %s GROUP BY 1"), ("location_id",)),
    "location_water_analog": (("SELECT location_id, md5(string_agg((to_jsonb(t) - 'run_id')::text, ',' ORDER BY api10)) "
                               "FROM box.location_water_analog t WHERE run_id = %s GROUP BY 1"), ("location_id",)),
    "pud_proximity": ("SELECT location_id, (to_jsonb(t) - 'run_id')::text FROM box.pud_proximity t WHERE run_id = %s", ("location_id",)),
    "pud_proximity_parent": (("SELECT location_id, md5(string_agg((to_jsonb(t) - 'run_id')::text, ',' ORDER BY api10)) "
                              "FROM box.pud_proximity_parent t WHERE run_id = %s GROUP BY 1"), ("location_id",)),
}
JSON_TABLES = ("pud_forecast", "pud_forecast_stream", "pud_proximity")


def pull(conn: Any, run_id: int) -> dict[str, pd.DataFrame]:
    out = {}
    with conn.cursor() as cur:
        for name, (sql, keys) in TABLES.items():
            t0 = time.time()
            cur.execute("SET TRANSACTION READ ONLY")
            cur.execute("SET LOCAL statement_timeout = '3600s'")
            cur.execute("SET LOCAL extra_float_digits = 3")  # shortest-exact float text on both servers (live defaults to 15 digits)
            rows = cur.execute(sql, (run_id,)).fetchall()
            conn.rollback()
            out[name] = pd.DataFrame(rows, columns=[*keys, "image"])
            print(f"  {name}: {len(rows):,} rows ({time.time() - t0:.0f} s)", flush=True)
    return out


def differing_columns(a: str, b: str) -> list[str]:
    """The keys whose values differ between two row images (jsonb text)."""
    x, y = json.loads(a), json.loads(b)
    return sorted(k for k in set(x) | set(y) if x.get(k) != y.get(k))


def compare(live: dict[str, pd.DataFrame], box: dict[str, pd.DataFrame]) -> tuple[dict[str, Any], pd.DataFrame]:
    """Per table: live rows reproduced exactly / differing / missing in the container, and container-only rows (additions)."""
    summ, diffs = {}, []
    for name, (_, keys) in TABLES.items():
        m = live[name].merge(box[name], on=list(keys), how="outer", suffixes=("_live", "_box"), indicator=True)
        both = m[m["_merge"] == "both"]
        bad = both[both["image_live"] != both["image_box"]]
        cols: dict[str, int] = {}
        for r in bad.itertuples():
            for c in (differing_columns(r.image_live, r.image_box) if name in JSON_TABLES else ["image"]):
                cols[c] = cols.get(c, 0) + 1
            diffs.append({"table": name, "kind": "differ", **{k: getattr(r, k) for k in keys}})
        diffs += [{"table": name, "kind": "missing", **{k: getattr(r, k) for k in keys}} for r in m[m["_merge"] == "left_only"].itertuples()]
        summ[name] = {"live_rows": len(live[name]), "reproduced": int(len(both) - len(bad)), "differ": len(bad), "differ_columns": cols,
                      "missing_in_container": int((m["_merge"] == "left_only").sum()), "container_only": int((m["_merge"] == "right_only").sum())}
    return summ, pd.DataFrame(diffs, columns=["table", "kind", "location_id", "stream"])


FORECAST_TABLES = ("pud_forecast", "pud_forecast_stream", "pud_forecast_month", "location_analog", "location_water_analog")
PROX_MOVES = ("outcome", "factor")


def proximity_moved(before: pd.DataFrame, after: pd.DataFrame) -> set[int]:
    """Locations whose D116 outcome or factor differs between two proximity measurements (pud_outcomes files)."""
    m = before.merge(after, on="location_id", suffixes=("_a", "_b"))
    moved = (m["outcome_a"].astype(str) != m["outcome_b"].astype(str)) | ((m["factor_a"] - m["factor_b"]).abs() > 1e-12)
    return set(m.loc[moved, "location_id"].astype(int))


def attribute(diffs: pd.DataFrame, live_pf: pd.DataFrame, basin: str, moved: set[int]) -> dict[str, dict[str, int]]:
    """Each forecast-table difference / missing row is on a location whose proximity outcome moved, or a row of another basin
    (D135); anything else is unexplained."""
    other = {int(r.location_id) for r in live_pf.itertuples() if json.loads(r.image)["basin"] != basin}
    out = {}
    for t in FORECAST_TABLES:
        ids = set(diffs.loc[diffs["table"] == t, "location_id"].astype(int)) if len(diffs) else set()
        out[t] = {"locations": len(ids), "proximity_moved": len(ids & moved), "other_basin": len(ids & other - moved),
                  "unexplained": len(ids - moved - other)}
    return out


def additions(conn: Any, live_pf: pd.DataFrame, box_pf: pd.DataFrame) -> pd.DataFrame:
    """Container-only pud_forecast rows with their Novi category (curated.intel_locations, read-only), by category x bench x coverage."""
    add = box_pf[~box_pf["location_id"].isin(live_pf["location_id"])]
    img = pd.DataFrame([json.loads(s) for s in add["image"]])
    if img.empty:
        return pd.DataFrame()
    with conn.cursor() as cur:
        cur.execute("SET TRANSACTION READ ONLY")
        cat = dict(cur.execute("SELECT stick_id, category FROM curated.intel_locations WHERE stick_id = ANY(%s)",
                               ([int(s) for s in img["stick_id"]],)).fetchall())
        conn.rollback()
    img["category"] = img["stick_id"].map(cat)
    return img.groupby(["category", "bench", "formation_blueox", "coverage"]).size().rename("locations").reset_index()


def cmd_compare(a: argparse.Namespace) -> int:
    from scripts import box_rehearsal as reh

    t0 = time.time()
    e = reh._box_env()
    print(f"live run {a.live_run}:", flush=True)
    with get_connection() as conn:
        live = pull(conn, a.live_run)
        print(f"container run {a.run_id}:", flush=True)
        with psycopg.connect(host=e["PGHOST"], port=int(e["PGPORT"]), dbname=e["PGDATABASE"], user=e["PGUSER"], password=e["PGPASSWORD"]) as bx:
            box = pull(bx, a.run_id)
        summ, diffs = compare(live, box)
        add = additions(conn, live["pud_forecast"], box["pud_forecast"])
    a.out.mkdir(parents=True, exist_ok=True)
    res: dict[str, Any] = {"live_run": a.live_run, "container_run": a.run_id, "tables": summ, "seconds": round(time.time() - t0)}
    if a.prox_before and a.prox_after:
        moved = proximity_moved(pd.read_csv(a.prox_before), pd.read_csv(a.prox_after))
        res["attribution"] = {"proximity_moved_locations": len(moved), "basin": a.basin,
                              "tables": attribute(diffs, live["pud_forecast"], a.basin, moved)}
    (a.out / "compare.json").write_text(json.dumps(res, indent=1), encoding="utf-8")
    add.to_csv(a.out / "additions.csv", index=False)
    if len(diffs):
        diffs.to_csv(a.out / "differences.csv", index=False)
    for name, s in summ.items():
        print(f"{name:>22}: live {s['live_rows']:,} reproduced {s['reproduced']:,} differ {s['differ']:,} {s['differ_columns'] or ''} "
              f"missing {s['missing_in_container']:,}; container-only {s['container_only']:,}")
    ok = all(s["differ"] == 0 and s["missing_in_container"] == 0 for s in summ.values())
    print(f"every live run-{a.live_run} row reproduced exactly: {ok} ({time.time() - t0:.0f} s)")
    if "attribution" in res:
        at = res["attribution"]
        for t, x in at["tables"].items():
            print(f"{t:>22}: {x['locations']:,} locations differ or missing = proximity re-measure {x['proximity_moved']:,} + other basin "
                  f"{x['other_basin']:,} + unexplained {x['unexplained']:,}")
        ok = all(x["unexplained"] == 0 for x in at["tables"].values())
        print(f"every forecast-table difference explained by the D116 re-measure or D135: {ok}")
    return 0 if ok else 1


def cmd_midland(a: argparse.Namespace) -> int:
    with get_connection() as conn:
        u = pr.universe(conn, (), basins=["midland"])
    t = u.groupby(["bench", "category", "inside_extent", "recon_status", "coverage"], dropna=False).size().rename("sticks").reset_index()
    a.out.mkdir(parents=True, exist_ok=True)
    t.to_csv(a.out / "midland_universe.csv", index=False)
    ins = u[u["inside_extent"].eq(True)]
    print(pd.crosstab(ins["bench"], ins["category"], margins=True).to_string())
    return 0


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    c = sub.add_parser("compare")
    c.add_argument("--run-id", type=int, required=True, help="the rehearsed record in the container")
    c.add_argument("--live-run", type=int, default=19)
    c.add_argument("--basin", default="delaware")
    c.add_argument("--prox-before", type=Path, default=None, help="the live run's proximity outcomes (pud_outcomes.csv.gz)")
    c.add_argument("--prox-after", type=Path, default=None, help="the rehearsal's re-measured outcomes")
    c.add_argument("--out", type=Path, default=Path("docs") / "box" / "universe-2026-10-21" / "step3")
    m = sub.add_parser("midland")
    m.add_argument("--out", type=Path, default=Path("docs") / "box" / "universe-2026-10-21" / "step3")
    a = ap.parse_args(argv)
    return cmd_compare(a) if a.cmd == "compare" else cmd_midland(a)


if __name__ == "__main__":
    sys.exit(main())
