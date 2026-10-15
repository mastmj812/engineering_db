"""BOX D84 — quarterly analog-pool refresh (read-only against the warehouse).

    python -m scripts.box_pool_refresh [--base <dir>] [--out docs/box/pool-YYYY-MM-DD] [--dry-run]

Re-pulls and re-scores the Delaware producing horizontals exactly as step 1 did (box.bench_qc consensus detector), applies
the class rule of record (box.qc_rule) with NO card verdicts, and appends the wells never judged before that land in the
WCA pool to the base set. Writes <out>/wells_final_WCA.csv (base bytes + appended rows, identity-checked),
wells_final_BS2_S.csv (copied), new_wells.csv, universe.csv, refresh.json and the review page index.html.

Default base = the newest docs/box/pool-* refresh, else the gate-1 set (docs/box/step1-2026-10-06). Feed the result to
`python -m scripts.box_pud_run build --wells <out>`. Nothing is written to the warehouse; no BOX store runs here.
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import subprocess
import sys
import time
from dataclasses import asdict
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from box import pool_refresh as pr
from box.bench_qc import ConsensusParams, pull_delaware_producers, score_consensus
from box.qc_rule import apply_rule
from etl.db import get_connection

BOX_DOCS = Path("docs") / "box"
_EXTENT_SQL = """
SELECT extent_id, version, extensions.ST_AsText(geom) FROM box.extent
WHERE basin = 'delaware' AND bench = %(bench)s AND is_record
"""
CODE_PATHS = ["box/pool_refresh.py", "box/bench_qc.py", "box/qc_rule.py", "box/flag_cards.py", "scripts/box_pool_refresh.py"]


def _git_sha() -> str:
    head = subprocess.run(["git", "rev-parse", "HEAD"], capture_output=True, text=True, check=True).stdout.strip()
    dirty = subprocess.run(["git", "status", "--porcelain", "--", *CODE_PATHS], capture_output=True, text=True, check=True).stdout.strip()
    return head + ("-dirty" if dirty else "")


def default_base() -> Path:
    refreshes = sorted(p for p in BOX_DOCS.glob("pool-*") if (p / pr.MANIFEST).exists())
    return refreshes[-1] if refreshes else pr.GATE1_DIR


def record_extent(conn: Any) -> tuple[int | None, Any]:
    """The WCA extent of record (shapely geometry), read-only; (None, None) if there is none."""
    from shapely import wkt

    with conn.cursor() as cur:
        cur.execute("SET TRANSACTION READ ONLY")
        cur.execute(_EXTENT_SQL, {"bench": pr.POOL})
        row = cur.fetchone()
    conn.rollback()
    return (None, None) if row is None else (int(row[0]), wkt.loads(row[2]))


def in_extent(df: pd.DataFrame, geom: Any) -> np.ndarray:
    if geom is None:
        return np.zeros(len(df), dtype=bool)
    from shapely import contains_xy

    ok = df["mid_lon"].notna() & df["mid_lat"].notna()
    out = np.zeros(len(df), dtype=bool)
    out[ok.to_numpy()] = contains_xy(geom, df.loc[ok, "mid_lon"].to_numpy(float), df.loc[ok, "mid_lat"].to_numpy(float))
    return out


def extent_rings(geom: Any, tol_deg: float = 0.002) -> list[list[list[list[float]]]]:
    if geom is None:
        return []
    g = geom.simplify(tol_deg, preserve_topology=True)
    polys = list(g.geoms) if hasattr(g, "geoms") else [g]
    return [[[[round(x, 4), round(y, 4)] for x, y in ring.coords] for ring in [p.exterior, *p.interiors]] for p in polys]


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--base", type=Path, default=None, help="base well-set dir (default: newest docs/box/pool-* refresh, else the gate-1 set)")
    ap.add_argument("--out", type=Path, default=BOX_DOCS / f"pool-{dt.datetime.now(tz=dt.UTC).astimezone():%Y-%m-%d}")
    ap.add_argument("--dry-run", action="store_true", help="classify and print; write nothing")
    a = ap.parse_args(argv)
    base_dir = a.base or default_base()
    t0 = time.time()
    with get_connection() as conn:
        live = pull_delaware_producers(conn)
        extent_id, geom = record_extent(conn)
    live = apply_rule(score_consensus(live), verdicts=None)  # D84: no calibration cards
    live["in_extent"] = in_extent(live, geom)
    base = pd.read_csv(base_dir / pr.final_name(pr.POOL), dtype={"api10": str})
    base["in_extent"] = in_extent(base, geom)
    seen, seen_meta = pr.reconstruct_seen(base_dir, live)
    if seen_meta["method"] == "reconstructed" and (base_dir / "summary.json").exists():
        seen_meta["gate1_recorded_n"] = json.loads((base_dir / "summary.json").read_text(encoding="utf-8"))["meta"].get("n_delaware_prod_hz")
    parts = pr.classify(live, base, set(seen["api10"]), pr.load_exclusions())
    summ = pr.summarize(parts)
    label = a.out.name
    universe = pr.next_universe(seen, live, label)
    print(f"base {base_dir} ({len(base):,} rows) | live Delaware producing hz {len(live):,}, data through {live.attrs.get('asof')} | "
          f"judged universe {seen_meta['method']} {seen_meta['n']:,}")
    print(f"new (never judged) any bench {summ['n_new_any_bench']:,} | ADDED to WCA {summ['added']} {summ['added_by_tag']} "
          f"actions {summ['added_by_action']} | in extent {summ['added_in_extent']} | excluded {summ['added_excluded']}")
    print(f"new but ruled out of WCA {summ['rule_out']} {summ['rule_out_to']} | not re-decided (judged before) {summ['not_rejudged']} | "
          f"base drift (reported, unchanged) {summ['drift']}")
    if summ["uncalibrated_classes_new"]:
        print("uncalibrated classes among new wells (tag kept):", ", ".join(summ["uncalibrated_classes_new"]))
    for _, r in parts["added"].iterrows():
        print(f"  + {r['api10']} {str(r['well_name'])[:34]:34} {r['first_production_date']} {r['formation_blueox']:>6} -> {r['box_bench']} "
              f"{r['box_action']:<11} {r['flag_class'] or '-':<12} {r['class_status']}")
    if a.dry_run:
        print(f"dry run: nothing written ({time.time() - t0:.0f} s)")
        return 0
    meta = {
        "label": label, "base_dir": str(base_dir), "out_dir": str(a.out), "built_at": dt.datetime.now(tz=dt.UTC).astimezone().isoformat(timespec="seconds"),
        "git_sha": _git_sha(), "asof": str(live.attrs.get("asof")), "n_live": len(live), "decision": "D84", "card_verdicts": "none (D84)",
        "consensus_params": asdict(ConsensusParams()), "extent_id": extent_id, "seen": seen_meta, "n_universe": len(universe), "summary": summ,
    }
    man = pr.write_refresh(a.out, base_dir, parts, universe, meta)
    page = pr.render_page(a.out, base, parts, man, extent_rings(geom))
    ident = man["identity"][pr.POOL]
    print(f"identity OK: base {ident['n_base_rows']:,} rows byte-identical prefix + {ident['n_appended']} appended = {ident['n_rows']:,}")
    print(f"wrote {a.out} ({page.name}, {pr.NEW_WELLS}, {pr.UNIVERSE}, {pr.MANIFEST})  ({time.time() - t0:.0f} s)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
