"""BOX step 15 — STORE a family's extents: bench_scope rows, generated v1, and the owner-edited v1 as the version of record.

    python -m scripts.box_family_extent_store --wells docs/box/step15a-2026-10-16 --pool BS3_S BS3_C [--dry-run]

WAREHOUSE WRITES (box.* is app-owned; no DDL). Needs Michael's explicit go-apply (given 2026-10-16 for BS3_S + BS3_C:
"go apply: add BS3_S + BS3_C to box.bench_scope, store generated v1, then store the edited v1 as the version of record").

Identity before any write: the generated extent is rebuilt with the record parameters and must equal the reviewed
generated v1 (extents/extent_<pool>_v1.geojson) to 0.01 sq mi; the edited geometry is the reviewed
extents/edited/extent_<pool>_v1_edited.geojson exactly. Refuses if box.extent already holds rows for the bench.
After the writes, a read-only check confirms one record per bench = the edited row, parent = the generated row.
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import sys
from pathlib import Path

from shapely.geometry import shape

from box import edge_gap as eg
from box import edge_gap_report as egr
from box import extent as ex
from box import extent_report as er
from box import family_extent as fe
from box.extent_store import BASIN, store_edited, store_generated
from etl.db import get_connection
from scripts.box_family_extents import _git_sha

SCOPE_ROW = {
    "BS3_S": ("{BS3_S}", "Bone Spring 3 sand: 2,365 modern producers; step 15a QC gate (not pooled with BS3_C); extent = owner hand edit of generated D27 v1"),
    "BS3_C": ("{BS3_C}", "Bone Spring 3 carbonate: 1,651 modern producers; step 15a QC gate (not pooled with BS3_S); extent = owner hand edit of generated D27 v1"),
    # step 15 remaining benches (2026-10-16): extent = owner pen loops (or the generated v1 where no loop was drawn)
    "WCB_1": ("{WCB_1}", "Wolfcamp B1: 1,664 modern producers; step 15 extent pass (owner loops)"),
    "WCB_2": ("{WCB_2}", "Wolfcamp B2: 1,090 modern producers; step 15 extent pass (owner loops); deep-TVD tagging caveat"),
    "BS1_S": ("{BS1_S}", "Bone Spring 1 sand: 962 modern producers; step 15 extent pass (owner loops)"),
    "WCC": ("{WCC}", "Wolfcamp C: 923 modern producers; step 15 extent pass (generated v1 accepted)"),
    "BS2_C": ("{BS2_C}", "Bone Spring 2 carbonate: 650 modern producers; step 15 extent pass (owner loops, two bodies)"),
    "AVA_0": ("{AVA_0}", "Avalon 0: 221 modern producers; step 15 extent pass (generated v1 accepted)"),
    "AVA_1": ("{AVA_1}", "Avalon 1: 493 modern producers; step 15 extent pass (generated v1 accepted)"),
    "AVA_2": ("{AVA_2}", "Avalon 2: 333 modern producers; step 15 extent pass (generated v1 accepted)"),
    "WCD": ("{WCD}", "Wolfcamp D: 150 modern producers; step 15 extent pass (generated v1 accepted)"),
}
DECISION_REF = "step 15a gates (docs/box/step15a-2026-10-16/FINDINGS.md §5, §8)"
DECISION_REF_15 = "step 15 extent pass (docs/box/step15-extents-2026-10-16/FINDINGS.md §4)"


def _extent_geojson(path: Path) -> object:
    gj = json.loads(path.read_text(encoding="utf-8"))
    feat = next(x for x in gj["features"] if x["properties"].get("layer") == "extent")
    return ex.as_multi(eg.to_ft([shape(feat["geometry"])])[0])


def _store_emerging(benches: list[str], dref: str, dry_run: bool) -> int:
    """D2 emerging bench: a bench_scope row with in_scope = false and no extent (the WDFD pattern). Refuses if the bench
    already has a scope row or any extent."""
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT bench FROM box.bench_scope WHERE basin = %s AND bench = ANY(%s) UNION SELECT bench FROM box.extent WHERE basin = %s AND bench = ANY(%s)",
                        (BASIN, benches, BASIN, benches))
            clash = sorted(r[0] for r in cur.fetchall())
        conn.rollback()
        if clash:
            print(f"REFUSED: scope row or extent already exists for {clash}")
            return 2
        for b in benches:
            print(f"{b}: bench_scope in_scope=false, reason 'emerging bench (D2)', no extent")
        if dry_run:
            print("dry run: nothing written")
            return 0
        with conn.cursor() as cur:
            for b in benches:
                cur.execute(
                    """INSERT INTO box.bench_scope (basin, bench, in_scope, member_benches, reason, decided_on, decision_ref)
                       VALUES (%s, %s, false, %s, %s, %s, %s)""",
                    (BASIN, b, "{" + b + "}", "emerging bench: too little development history for the BOX workflow; hand-worked per deal; shown as not covered, never zero (D2)",
                     dt.date(2026, 10, 16), dref),
                )
        conn.commit()
        with conn.cursor() as cur:
            cur.execute("SET TRANSACTION READ ONLY")
            cur.execute("SELECT basin, bench, in_scope, member_benches FROM box.bench_scope WHERE basin = %s AND bench = ANY(%s)", (BASIN, benches))
            for r in cur.fetchall():
                print("  live:", r)
        conn.rollback()
    return 0


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--wells", type=Path, default=None)
    ap.add_argument("--pool", nargs="*", default=[], choices=sorted(SCOPE_ROW))
    ap.add_argument("--emerging", nargs="*", default=[], help="benches recorded as D2 emerging: bench_scope row in_scope = false, NO extent (like WDFD)")
    ap.add_argument("--version", type=int, default=1)
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--out-of-scope", nargs="*", default=[], help="benches whose bench_scope row is in_scope = false (extent stored for reference; D2 / step 14 pending)")
    ap.add_argument("--decision-ref", default=None)
    a = ap.parse_args(argv)
    if a.emerging:
        return _store_emerging(a.emerging, a.decision_ref or DECISION_REF_15, a.dry_run)
    if not a.pool or a.wells is None:
        ap.error("--wells and --pool are required unless --emerging is given")
    ext_dir = a.wells / "extents"
    bp = fe.record_params()
    run_id = f"step15 {dt.date(2026, 10, 16)} {_git_sha()}"
    eds = json.loads((ext_dir / "edited" / "summary.json").read_text(encoding="utf-8"))
    dref = a.decision_ref or (DECISION_REF if set(a.pool) <= {"BS3_S", "BS3_C"} else DECISION_REF_15)
    with get_connection() as conn:
        # --- identity, read-only
        with conn.cursor() as cur:
            cur.execute("SELECT bench, count(*) FROM box.extent WHERE basin = %s AND bench = ANY(%s) GROUP BY bench", (BASIN, list(a.pool)))
            existing = dict(cur.fetchall())
        conn.rollback()
        if existing:
            print(f"REFUSED: box.extent already holds rows for {existing}")
            return 2
        df = egr.load_final_sets(a.wells, tuple(a.pool))
        df = egr.attach_geometry(df, egr.pull_laterals(conn, sorted(df["api10"].unique())))
        sopa = er.load_sopa()
        plan = {}
        for pool in a.pool:
            reviewed = _extent_geojson(ext_dir / f"extent_{pool}_v{a.version}.geojson")
            ep = eds["pools"][pool]
            owner_marks = int(ep.get("n_freeforms", 1)) + int(ep.get("n_ink_strokes", 0))
            edited = _extent_geojson(ext_dir / "edited" / f"extent_{pool}_v{a.version}_edited.geojson") if owner_marks else None
            b = er.build_pool(df[df.pool == pool], pool, bp, sopa, None)
            d_area = abs(b["extent"].area - reviewed.area) / eg.FT_PER_MI**2
            d_sym = b["extent"].symmetric_difference(reviewed).area / eg.FT_PER_MI**2
            print(f"{pool}: rebuilt generated {b['stats']['extent_sqmi']:,.2f} vs reviewed {reviewed.area / eg.FT_PER_MI**2:,.2f} sq mi "
                  f"(|d area| {d_area:.4f}, sym diff {d_sym:.4f}); "
                  + (f"owner edit {edited.area / eg.FT_PER_MI**2:,.2f} sq mi = record" if edited is not None else "no owner marks: generated v1 = record")
                  + f"; in_scope={pool not in a.out_of_scope}")
            if d_area > 0.01 or d_sym > 0.05:
                print(f"REFUSED: {pool} rebuilt generated extent differs from the reviewed one")
                return 3
            if edited is None:
                plan[pool] = (b, None, {})
                continue
            diff = ex.diff(b["extent"], edited, b["extent"].centroid)
            plan[pool] = (b, edited, {k: v for k, v in diff.items() if k != "pieces"} | {"source": f"owner hand edit ({Path(eds['source']).name}, Michael 2026-10-16)"})
        if a.dry_run:
            print("dry run: nothing written")
            return 0
        # --- writes
        with conn.cursor() as cur:
            for pool in a.pool:
                members, reason = SCOPE_ROW[pool]
                cur.execute(
                    """INSERT INTO box.bench_scope (basin, bench, in_scope, member_benches, reason, decided_on, decision_ref)
                       VALUES (%s, %s, %s, %s, %s, %s, %s) ON CONFLICT (basin, bench) DO NOTHING""",
                    (BASIN, pool, pool not in a.out_of_scope, members,
                     reason + ("; IN_SCOPE FALSE pending the step-14 D2 decision (extent stored for reference)" if pool in a.out_of_scope else ""),
                     dt.date(2026, 10, 16), dref),
                )
        conn.commit()
        for pool, (b, edited, dstats) in plan.items():
            gid = store_generated(conn, pool, a.version, b, bp, run_id, make_record=edited is None)
            if edited is None:
                print(f"stored {pool}: generated v{a.version} extent_id {gid} = version of record (no owner marks)")
                continue
            eid = store_edited(conn, pool, a.version, edited, dstats, make_record=True)
            print(f"stored {pool}: generated v{a.version} extent_id {gid}; edited v{a.version} extent_id {eid} = version of record")
        # --- verify, read-only
        with conn.cursor() as cur:
            cur.execute("SET TRANSACTION READ ONLY")
            cur.execute(
                """SELECT e.bench, e.extent_id, e.source, e.is_record, round(e.area_sqmi::numeric, 2), e.parent_extent_id,
                          round((extensions.ST_Area(e.geom::extensions.geography) / 2589988.110336)::numeric, 1),
                          (SELECT count(*) FROM box.extent_edge g WHERE g.extent_id = e.extent_id)
                   FROM box.extent e WHERE e.basin = %s AND e.bench = ANY(%s) ORDER BY e.extent_id""",
                (BASIN, list(a.pool)),
            )
            rows = cur.fetchall()
            cur.execute("SELECT bench, count(*) FILTER (WHERE is_record) FROM box.extent WHERE basin = %s GROUP BY bench ORDER BY bench", (BASIN,))
            rec = cur.fetchall()
        conn.rollback()
        for r in rows:
            print("  live:", r)
        print("  records per bench:", rec)
        bad = [r for r in rec if r[1] != 1]
        if bad:
            print(f"CHECK FAILED: benches without exactly one record: {bad}")
            return 4
    return 0


if __name__ == "__main__":
    sys.exit(main())
