"""Nightly tag-rule step (sql/72; docs/formation_tag_redesign/WAREHOUSE_STEP.md).

Runs between the curated.wells (+ well_lateral_survey) refresh and the curated.formation_blueox refresh
(etl.db.refresh_curated hook). One pass:

  1. pull the vendor-only inputs (box.tag_rule_inputs, no survey stations);
  2. read policy + human calls from ref.formation_tag_policy / _class / _depth_exclusions / _overrides;
  3. run Steps 1 -> 2 -> 3 (box.tag_rule_run);
  4. circuit breaker (D3): applied-code changes vs the previous run on wells whose own inputs did not move,
     limit max(200, 1 % of judged wells); a trip writes nothing but the run row;
  5. replace curated.formation_tag_rule and add the meta.formation_tag_run row in ONE transaction.

Standing authorization (Michael 2026-11-09, D1): exactly these two tables, every night, behind the breaker. Policy
and human calls are read, never written. In the nightly the step is soft: any failure is logged and the previous
table stays (sql/16's staleness guard drops rows whose inputs moved). Before sql/72 is applied the step is a no-op.

    python -m etl.tag_rule --dry-run [--from-seeds]   # read-only: run + report, write nothing
    python -m etl.tag_rule --write                    # what the nightly does
    python -m etl.tag_rule --write --allow-breaker    # manual, after a reviewed policy / crosswalk change
"""

from __future__ import annotations

import argparse
import json
import logging
import math
import sys
import time
from datetime import datetime, timezone
from typing import Any

import pandas as pd

logger = logging.getLogger(__name__)

TABLES = ("ref.formation_tag_policy", "ref.formation_tag_class", "ref.formation_tag_depth_exclusions",
          "ref.formation_tag_switch", "ref.formation_tag_overrides", "curated.formation_tag_rule", "meta.formation_tag_run")


def _clean(x: Any) -> Any:
    """JSON-safe: NaN / inf -> None, numpy scalars -> Python, containers recursed."""
    if isinstance(x, dict):
        return {str(k): _clean(v) for k, v in x.items()}
    if isinstance(x, list | tuple):
        return [_clean(v) for v in x]
    if hasattr(x, "item") and not isinstance(x, str):
        x = x.item()
    if isinstance(x, float) and not math.isfinite(x):
        return None
    return x


def missing_tables(conn: Any) -> list[str]:
    with conn.cursor() as cur:
        return [t for t in TABLES if cur.execute("SELECT to_regclass(%s)", (t,)).fetchone()[0] is None]


def load_policy(conn: Any):
    from box import tag_rule_run as tr

    def q(sql: str) -> pd.DataFrame:
        with conn.cursor() as cur:
            cur.execute(sql)
            return pd.DataFrame(cur.fetchall(), columns=[c.name for c in cur.description])

    pol = q("SELECT * FROM ref.formation_tag_policy")
    version = int(pol["policy_version"].max())
    pol = pol[pol["policy_version"] == version].drop(columns="policy_version")
    pol["novi_share"] = pol["novi_share"].astype(float)
    ex = q("SELECT api10, depth_ft, depth_source FROM ref.formation_tag_depth_exclusions")
    ex["depth_ft"] = ex["depth_ft"].astype(float)
    return tr.Policy(patterns=pol, classes=q("SELECT * FROM ref.formation_tag_class"),
                     overrides=q("SELECT api10, corrected_code FROM ref.formation_tag_overrides"), exclusions=ex,
                     version=version)


def previous(conn: Any) -> pd.DataFrame:
    with conn.cursor() as cur:
        cur.execute("SELECT api10, applied_code, novi_raw, env_raw, tvd_ft, planned, human_call FROM curated.formation_tag_rule")
        d = pd.DataFrame(cur.fetchall(), columns=[c.name for c in cur.description])
    d["tvd_ft"] = pd.to_numeric(d["tvd_ft"], errors="coerce")
    return d


def run(write: bool, from_seeds: bool = False, allow_breaker: bool = False) -> dict[str, Any]:
    from box import tag_rule_inputs as ti
    from box import tag_rule_run as tr
    from etl.db import get_connection

    started = datetime.now(timezone.utc)
    t0 = time.monotonic()
    conn = get_connection()
    try:
        missing = missing_tables(conn)
        conn.rollback()
        if missing and (write or not from_seeds):
            logger.info("tag rule: tables not applied yet (%s) - skipped", ", ".join(missing))
            return {"status": "absent", "missing": missing}
        p = ti.pull(conn, stations=False)
        policy = tr.policy_from_seeds() if from_seeds else load_policy(conn)
        conn.rollback()
        w = tr.frame(p["wells"], p["vendors"], p["extents"], policy.exclusions)
        d, learned = tr.run(w, policy)
        rows = tr.rule_rows(d)
        prev = pd.DataFrame() if missing else previous(conn)
        conn.rollback()
        moved: set[str] = set()
        human_moved: list[str] = []
        if not prev.empty:
            ok = tr.inputs_match(prev, p["wells"], p["vendors"])
            moved = set(prev.loc[~ok.to_numpy(), "api10"])
            human_moved = sorted(set(prev.loc[prev["human_call"].notna(), "api10"]) & moved)
        brk = tr.breaker(prev, rows, moved)
        s = tr.summary(d, w, learned, policy)
        s.update({"breaker": brk, "inputs_moved_overnight": len(moved), "human_calls_inputs_moved": human_moved,
                  "new_wells": int((~rows["api10"].isin(prev["api10"])).sum()) if not prev.empty else len(rows),
                  "runtime_s": round(time.monotonic() - t0, 1)})
        status = "dry_run" if not write else ("tripped" if brk["tripped"] and not allow_breaker else "written")
        s["status"] = status
        if brk["tripped"]:
            logger.warning("tag rule: circuit breaker %s (%d applied-code changes > limit %d)",
                           "OVERRIDDEN" if allow_breaker else "TRIPPED - nothing written", brk["changed"], brk["limit"])
        if not write:
            return _clean(s)
        run_row = (started, status, status == "written", s["judged"], s["applied"], brk["changed"], brk["limit"],
                   policy.version, s["policy_digest"], s["rule_sha"], json.dumps(_clean(s)))
        with conn.transaction(), conn.cursor() as cur:
            run_id = cur.execute(
                "INSERT INTO meta.formation_tag_run (started_at, status, wrote, judged, applied, changed_vs_prev, breaker_limit,"
                " policy_version, policy_digest, rule_sha, summary) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s) RETURNING run_id",
                run_row).fetchone()[0]
            if status == "written":
                cur.execute("TRUNCATE curated.formation_tag_rule")
                cols = [*tr.RULE_COLUMNS, "run_id"]
                with cur.copy(f"COPY curated.formation_tag_rule ({', '.join(cols)}) FROM STDIN") as cp:
                    for r in rows.itertuples(index=False, name=None):
                        cp.write_row([*r, run_id])
                n = cur.execute("SELECT count(*) FROM curated.formation_tag_rule").fetchone()[0]
                if n != len(rows):
                    raise RuntimeError(f"tag rule: wrote {n} rows, expected {len(rows)} - rolled back")
        s["run_id"] = run_id
        logger.info("tag rule: %s run %s - %d judged, %d applied, %d changed vs previous, %.0fs",
                    status, run_id, s["judged"], s["applied"], brk["changed"], s["runtime_s"])
        return _clean(s)
    finally:
        conn.close()


def nightly_hook() -> None:
    """etl.db.refresh_curated hook before curated.formation_blueox: never raises (the nightly carries on with the
    previous rule table; sql/16's staleness guard covers wells whose inputs moved)."""
    try:
        run(write=True)
    except Exception:
        logger.exception("tag rule step failed - previous curated.formation_tag_rule kept")
        try:
            from etl.db import get_connection

            with get_connection() as conn, conn.cursor() as cur:
                if cur.execute("SELECT to_regclass('meta.formation_tag_run')").fetchone()[0] is not None:
                    cur.execute("INSERT INTO meta.formation_tag_run (started_at, status, wrote) VALUES (now(), 'failed', FALSE)")
                    conn.commit()
        except Exception:
            logger.exception("could not record the failed tag-rule run")


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    g = ap.add_mutually_exclusive_group(required=True)
    g.add_argument("--dry-run", action="store_true")
    g.add_argument("--write", action="store_true")
    ap.add_argument("--from-seeds", action="store_true", help="policy from seeds/ (before sql/72 is applied; dry run only)")
    ap.add_argument("--allow-breaker", action="store_true", help="write even if the circuit breaker trips (manual runs)")
    a = ap.parse_args(argv)
    if a.from_seeds and a.write:
        ap.error("--from-seeds is for --dry-run")
    s = run(write=a.write, from_seeds=a.from_seeds, allow_breaker=a.allow_breaker)
    print(json.dumps(s, indent=1, default=str))
    return 0 if s.get("status") in ("written", "dry_run", "absent") else 1


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
    sys.exit(main())
