"""BOX D84 / D126 — the analog-pool refresh, every group's well set (read-only against the warehouse).

    python -m scripts.box_pool_refresh [--base <dir>] [--out docs/box/pool-YYYY-MM-DD] [--dry-run]

Re-pulls and re-scores the Delaware producing horizontals exactly as step 1 did (box.bench_qc consensus detector), applies
the class rule of record (box.qc_rule) with NO card verdicts, and appends each well never judged before to the pool its
rule-decided bench names. Writes ONE directory: wells_final_<pool>.csv for all twelve pools (base bytes + appended rows,
identity-checked per file), new_wells.csv, universe.csv, refresh.json and the review page index.html.

Bases: the judged universe and the WCA / BS2_S sets come from --base (default: the newest docs/box/pool-* refresh). A pool
whose file --base does not hold (the first all-pool refresh) takes its step-15 set (box/production_run9 wells_dir). Feed the
result to `python -m scripts.box_pud_run build --wells <out>`: every group then reads its set from <out>. Nothing is written
to the warehouse; no BOX store runs here.
"""

from __future__ import annotations

import argparse
import datetime as dt
import subprocess
import sys
import time
from dataclasses import asdict
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from box import flag_cards as fc
from box import pool_refresh as pr
from box import production_run9 as p9r
from box.bench_qc import ConsensusParams, pull_delaware_producers, score_consensus
from box.qc_rule import apply_rule
from etl.db import get_connection

BOX_DOCS = Path("docs") / "box"
_EXTENT_SQL = """
SELECT extent_id, version, extensions.ST_AsText(geom) FROM box.extent
WHERE basin = 'delaware' AND bench = %(bench)s AND is_record
"""
CODE_PATHS = ["box/pool_refresh.py", "box/bench_qc.py", "box/qc_rule.py", "box/flag_cards.py", "box/production_run9.py",
              "scripts/box_pool_refresh.py"]
_POOL_COLOR = {"WCA": "#2563eb", "WCB_1": "#dc2626", "WCB_2": "#7f1d1d"}


def _git_sha() -> str:
    head = subprocess.run(["git", "rev-parse", "HEAD"], capture_output=True, text=True, check=True).stdout.strip()
    dirty = subprocess.run(["git", "status", "--porcelain", "--", *CODE_PATHS], capture_output=True, text=True, check=True).stdout.strip()
    return head + ("-dirty" if dirty else "")


def default_base() -> Path:
    refreshes = sorted(p for p in BOX_DOCS.glob("pool-*") if (p / pr.MANIFEST).exists())
    return refreshes[-1] if refreshes else pr.GATE1_DIR


def base_files(base_dir: Path) -> dict[str, Path]:
    """pool -> its base wells_final file: --base when it holds it, else the group's step-15 set (production_run9)."""
    out = {}
    for p in pr.POOLS:
        f = base_dir / pr.final_name(p)
        out[p] = f if f.exists() else p9r.wells_dir(p, base_dir) / pr.final_name(p)
        if not out[p].exists():
            raise SystemExit(f"no base well set for pool {p}: {out[p]}")
    return out


def record_extent(conn: Any, bench: str) -> tuple[int | None, Any]:
    """The bench's extent of record (shapely geometry), read-only; (None, None) if there is none."""
    from shapely import wkt

    with conn.cursor() as cur:
        cur.execute("SET TRANSACTION READ ONLY")
        cur.execute(_EXTENT_SQL, {"bench": bench})
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
    ap.add_argument("--base", type=Path, default=None, help="base refresh dir (default: newest docs/box/pool-* refresh)")
    ap.add_argument("--out", type=Path, default=BOX_DOCS / f"pool-{dt.datetime.now(tz=dt.UTC).astimezone():%Y-%m-%d}")
    ap.add_argument("--dry-run", action="store_true", help="classify and print; write nothing")
    a = ap.parse_args(argv)
    base_dir = a.base or default_base()
    files = base_files(base_dir)
    t0 = time.time()
    with get_connection() as conn:
        live = pull_delaware_producers(conn)
        extents = {p: record_extent(conn, p) for p in pr.POOLS}
    live = apply_rule(score_consensus(live), verdicts=None)  # D84: no calibration cards
    bases = {p: pd.read_csv(f, dtype={"api10": str}, low_memory=False) for p, f in files.items()}
    seen, seen_meta = pr.reconstruct_seen(base_dir, live)
    # a step-15 set judged after the base universe was recorded: its wells count as judged too
    extra = sorted(set().union(*(set(b["api10"]) for b in bases.values())) - set(seen["api10"]))
    if extra:
        seen = pd.concat([seen, pd.DataFrame({"api10": extra, "first_judged": "step15-2026-10-16"})], ignore_index=True)
    seen_meta = seen_meta | {"n_step15_only": len(extra), "n": len(seen)}
    mask = {p: in_extent(live, g) for p, (_, g) in extents.items()}
    parts = pr.classify_pools(live, bases, set(seen["api10"]), pr.load_exclusions(), mask)
    summ = pr.summarize_pools(parts)
    universe = pr.next_universe(seen, live, a.out.name)
    print(f"base {base_dir} | live Delaware producing hz {len(live):,}, data through {live.attrs.get('asof')} | judged universe "
          f"{seen_meta['method']} {seen_meta['n']:,} (+{len(extra)} step-15 only)")
    print(f"new (never judged) any bench {summ['n_new_any_bench']:,} | added {summ['added_total']} | new in no pool {summ['new_unpooled']}")
    for p, v in summ["pools"].items():
        print(f"  {p:6s} base {len(bases[p]):6,} | added {v['added']:4d} (in extent {v['added_in_extent']}, excluded {v['added_excluded']}) "
              f"{v['added_by_tag']} | ruled out {v['rule_out']} | not re-decided {v['not_rejudged']} | drift {v['drift']}")
    if a.dry_run:
        print(f"dry run: nothing written ({time.time() - t0:.0f} s)")
        return 0
    meta = {
        "label": a.out.name, "base_dir": str(base_dir), "base_note": f"{base_dir} (+ step-15 sets for pools it lacks)",
        "base_files": {p: str(f) for p, f in files.items()}, "out_dir": str(a.out),
        "built_at": dt.datetime.now(tz=dt.UTC).astimezone().isoformat(timespec="seconds"), "git_sha": _git_sha(),
        "asof": str(live.attrs.get("asof")), "n_live": len(live), "decision": "D84 / D126", "card_verdicts": "none (D84)",
        "consensus_params": asdict(ConsensusParams()), "extent_ids": {p: e for p, (e, _) in extents.items()}, "seen": seen_meta,
        "n_universe": len(universe), "summary": summ,
    }
    man = pr.write_refresh_pools(a.out, files, parts, universe, meta)
    colors = {p: _POOL_COLOR.get(p) or fc._BENCH_COLORS.get(p, "#6b7280") for p in pr.POOLS}
    page = pr.render_pools_page(a.out, parts, man, {p: extent_rings(g) for p, (_, g) in extents.items()}, colors)
    for p, i in man["identity"].items():
        print(f"identity OK {p}: {i['n_base_rows']:,} base rows byte-identical + {i['n_appended']} appended = {i['n_rows']:,}")
    print(f"wrote {a.out} ({page.name}, {pr.NEW_WELLS}, {pr.UNIVERSE}, {pr.MANIFEST})  ({time.time() - t0:.0f} s)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
