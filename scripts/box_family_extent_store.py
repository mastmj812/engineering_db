"""BOX step 15 — STORE a family's extents: bench_scope rows, generated v1, and the owner-edited v1 as the version of record.

    python -m scripts.box_family_extent_store --wells docs/box/step15a-2026-10-16 --pool BS3_S BS3_C [--dry-run]
    python -m scripts.box_family_extent_store --wells docs/box/step20b-2026-10-30 --pool MS JM LSSH DEAN --basin midland --step 20b \
        --decided-on <go date> [--loop-date <deck date>] [--dry-run]                    # step 20b, on Michael's go only
    python -m scripts.box_family_extent_store --emerging US --basin midland --step 20b [--dry-run]   # D127: in_scope false, no extent

WAREHOUSE WRITES (box.* is app-owned; no DDL). Needs Michael's explicit go-apply (step 20a Midland r3: "go ahead on the r3 store",
2026-10-30, `--wells docs/box/step20a-2026-10-26/r3 --basin midland`; given 2026-10-16 for BS3_S + BS3_C:
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

from shapely import wkt
from shapely.geometry import shape

from box import basin as bsn
from box import edge_gap as eg
from box import edge_gap_report as egr
from box import extent as ex
from box import extent_report as er
from box import family_extent as fe
from box import wcb_split as ws
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

# Step 20a (Midland Wolfcamp, r3 on the corrected tags; store go 2026-10-30): one row per bench (D128), in scope with the
# tier provisional until step 21's counts (D131). Counts = r3 final sets, modern = first production 2016+.
MIDLAND_SCOPE_ROW = {
    "WCA_1": ("{WCA_1}", "Midland Wolfcamp A: 6,838 modern producers; step 20a r3 (not pooled, D128); generated v1 accepted; tier provisional until step 21 (D131)"),
    "WCB_1": ("{WCB_1}", "Midland Wolfcamp B1: 4,974 modern producers; step 20a r3 (D128; D136 one WCB landing north of the split line); generated v1 accepted; tier provisional until step 21 (D131)"),
    "WCB_2": ("{WCB_2}", "Midland Wolfcamp B2: 1,658 modern producers; step 20a r3 (D128); generated v1 clipped at the D136 WCB split line; tier provisional until step 21 (D131)"),
    "WCC": ("{WCC}", "Midland Wolfcamp C: 438 modern producers; step 20a r3 (D128); generated v1 (owner loop withdrawn); provisional target (D131)"),
    "WCD": ("{WCD}", "Midland Wolfcamp D: 823 modern producers; step 20a r3 (D128); extent = owner pen loop (deck slide 5); provisional target (D131)"),
}
STEP20A = {"decided_on": dt.date(2026, 10, 30), "loop_date": "2026-10-26",
           "decision_ref": "gate 20a store (docs/box/step20a-2026-10-26/FINDINGS.md §4 item 5, §7, §8.15-8.16; D128, D131, D134, D136)"}
# Step 20b (Midland Spraberry + Dean): same shape as 20a. Counts = the step-20b final sets (docs/box/step20b-2026-10-30), modern =
# first production 2016+. "{extent}" is filled at store time from the reviewed deck (owner loop or generated v1). decided_on = the
# store go's date (--decided-on); loop_date = the date of the deck the loops were read from (--loop-date).
MIDLAND_SCOPE_ROW_20B = {
    "MS": ("{MS}", "Midland Middle Spraberry: 1,615 modern producers; step 20b (not pooled, D128); {extent}; tier provisional until step 21 (D131)"),
    "JM": ("{JM}", "Midland Jo Mill: 1,612 modern producers; step 20b (not pooled, D128); {extent}; tier provisional until step 21 (D131)"),
    "LSSH": ("{LSSH}", "Midland Lower Spraberry Shale: 5,498 modern producers; step 20b (not pooled, D128); {extent}; tier provisional until step 21 (D131)"),
    "DEAN": ("{DEAN}", "Midland Dean: 908 modern producers; step 20b (not pooled, D128); {extent}; tier from step 21's counts (D131)"),
}
STEP20B_REF = "gate 20b store (docs/box/step20b-2026-10-30/FINDINGS.md; D127, D128, D131, D134, D141)"
# D127 (gate 18, 2026-10-26): Midland US is D2 emerging - a scope row with in_scope = false and no extent, stored at step 20b
EMERGING_REASON = {
    "midland": (("emerging bench (D2 / D127): Midland Upper Spraberry, 70 modern producers at gate 18, two operators 90 %; hand-worked "
                 "per deal; shown as not covered, never zero"), dt.date(2026, 10, 26)),
}


def _extent_geojson(path: Path) -> object:
    gj = json.loads(path.read_text(encoding="utf-8"))
    feat = next(x for x in gj["features"] if x["properties"].get("layer") == "extent")
    return ex.as_multi(eg.to_ft([shape(feat["geometry"])])[0])


def _store_emerging(benches: list[str], dref: str, dry_run: bool, basin: str = BASIN) -> int:
    """D2 emerging bench: a bench_scope row with in_scope = false and no extent (the WDFD pattern). Refuses if the bench
    already has a scope row or any extent."""
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT bench FROM box.bench_scope WHERE basin = %s AND bench = ANY(%s) UNION SELECT bench FROM box.extent WHERE basin = %s AND bench = ANY(%s)",
                        (basin, benches, basin, benches))
            clash = sorted(r[0] for r in cur.fetchall())
        conn.rollback()
        if clash:
            print(f"REFUSED: scope row or extent already exists for {clash}")
            return 2
        reason, decided = EMERGING_REASON.get(basin, (
            "emerging bench: too little development history for the BOX workflow; hand-worked per deal; shown as not covered, never zero (D2)",
            dt.date(2026, 10, 16)))
        for b in benches:
            print(f"{basin} {b}: bench_scope in_scope=false, no extent, decided_on {decided}, reason {reason!r}")
        if dry_run:
            print("dry run: nothing written")
            return 0
        with conn.cursor() as cur:
            for b in benches:
                cur.execute(
                    """INSERT INTO box.bench_scope (basin, bench, in_scope, member_benches, reason, decided_on, decision_ref)
                       VALUES (%s, %s, false, %s, %s, %s, %s)""",
                    (basin, b, "{" + b + "}", reason, decided, dref),
                )
        conn.commit()
        with conn.cursor() as cur:
            cur.execute("SET TRANSACTION READ ONLY")
            cur.execute("SELECT basin, bench, in_scope, member_benches FROM box.bench_scope WHERE basin = %s AND bench = ANY(%s)", (basin, benches))
            for r in cur.fetchall():
                print("  live:", r)
        conn.rollback()
    return 0


def _store_revision(pool: str, path: Path, version: int, parent_version: int, basin: str, dry_run: bool) -> int:
    """A revised owner edit of a stored generated extent: edited v<version> (parent = generated v<parent_version>) becomes
    the version of record and supersedes the current record. Refuses unless the bench has exactly one record and no edited
    v<version> yet. Step 20a WCD (Michael 2026-10-30): the slide-5 loop extended to take in 4246139575."""
    edited = _extent_geojson(path)
    note = json.loads(path.read_text(encoding="utf-8"))["features"][0]["properties"].get("source", "")
    with get_connection() as conn:
        with conn.cursor() as cur:
            recs = cur.execute("SELECT extent_id, source, version, area_sqmi FROM box.extent WHERE basin = %s AND bench = %s AND is_record",
                               (basin, pool)).fetchall()
            taken = cur.execute("SELECT count(*) FROM box.extent WHERE basin = %s AND bench = %s AND version = %s AND source = 'geology_edited'",
                                (basin, pool, version)).fetchone()[0]
            gen = cur.execute("SELECT extent_id, extensions.ST_AsText(geom) FROM box.extent WHERE basin = %s AND bench = %s AND version = %s AND source = 'generated'",
                              (basin, pool, parent_version)).fetchone()
        conn.rollback()
        if len(recs) != 1 or taken or gen is None:
            print(f"REFUSED: records {recs}, edited v{version} rows {taken}, generated v{parent_version} {'missing' if gen is None else gen[0]}")
            return 2
        generated = ex.as_multi(eg.to_ft([wkt.loads(gen[1])])[0])
        diff = ex.diff(generated, edited, generated.centroid)
        dstats = {k: v for k, v in diff.items() if k != "pieces"} | {"source": note}
        print(f"{pool}: record now extent {recs[0][0]} ({recs[0][1]} v{recs[0][2]}, {float(recs[0][3]):,.2f} sq mi) -> edited v{version} "
              f"{edited.area / eg.FT_PER_MI**2:,.2f} sq mi, parent generated v{parent_version} (extent {gen[0]})")
        if dry_run:
            print("dry run: nothing written")
            return 0
        eid = store_edited(conn, pool, version, edited, dstats, make_record=True, basin=basin, parent_version=parent_version)
        with conn.cursor() as cur:
            cur.execute("SET TRANSACTION READ ONLY")
            for r in cur.execute("SELECT extent_id, source, version, is_record, round(area_sqmi::numeric, 2), parent_extent_id, superseded_by "
                                 "FROM box.extent WHERE basin = %s AND bench = %s ORDER BY extent_id", (basin, pool)).fetchall():
                print("  live:", r)
        conn.rollback()
        print(f"stored {pool}: edited v{version} extent_id {eid} = version of record")
    return 0


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--revise", nargs=2, metavar=("POOL", "GEOJSON"), default=None,
                    help="store a revised owner edit (edited v<--version>, parent generated v<--parent-version>) as the record")
    ap.add_argument("--parent-version", type=int, default=1)
    ap.add_argument("--wells", type=Path, default=None)
    ap.add_argument("--pool", nargs="*", default=[], choices=sorted(set(SCOPE_ROW) | set(MIDLAND_SCOPE_ROW) | set(MIDLAND_SCOPE_ROW_20B)))
    ap.add_argument("--emerging", nargs="*", default=[], help="benches recorded as D2 emerging: bench_scope row in_scope = false, NO extent (like WDFD)")
    ap.add_argument("--version", type=int, default=1)
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--out-of-scope", nargs="*", default=[], help="benches whose bench_scope row is in_scope = false (extent stored for reference; D2 / step 14 pending)")
    ap.add_argument("--decision-ref", default=None)
    ap.add_argument("--basin", default=BASIN, help="the basin the rows are stored under (step 19)")
    ap.add_argument("--step", default="20a", choices=["20a", "20b"], help="Midland only: which step-20 family's scope rows and decision text")
    ap.add_argument("--decided-on", type=dt.date.fromisoformat, default=None, help="step 20b: the store go's date (required there)")
    ap.add_argument("--loop-date", default=None, help="step 20b: the date of the reviewed deck the owner loops came from")
    a = ap.parse_args(argv)
    if a.revise:
        return _store_revision(a.revise[0], Path(a.revise[1]), a.version, a.parent_version, a.basin, a.dry_run)
    if a.emerging:
        dref_e = a.decision_ref or (STEP20B_REF if a.basin == bsn.MIDLAND and a.step == "20b" else DECISION_REF_15)
        return _store_emerging(a.emerging, dref_e, a.dry_run, a.basin)
    if not a.pool or a.wells is None:
        ap.error("--wells and --pool are required unless --emerging is given")
    ext_dir = a.wells / "extents"
    bp = fe.record_params()
    midland = a.basin == bsn.MIDLAND
    step20b = midland and a.step == "20b"
    if step20b and a.decided_on is None:
        ap.error("--step 20b needs --decided-on (the store go's date)")
    scope_rows = MIDLAND_SCOPE_ROW_20B if step20b else MIDLAND_SCOPE_ROW if midland else SCOPE_ROW
    if missing := sorted(set(a.pool) - set(scope_rows)):
        ap.error(f"no {a.basin} bench_scope row defined for {missing}")
    decided_on = a.decided_on if step20b else STEP20A["decided_on"] if midland else dt.date(2026, 10, 16)
    loop_date = (a.loop_date or "") if step20b else STEP20A["loop_date"] if midland else "2026-10-16"
    edge = er.edge_params(a.basin)  # the basin's D23 metric, as the reviewed extents were built (family_extent.run)
    run_id = f"step{'20b' if step20b else '20a r3' if midland else '15'} {decided_on} {_git_sha()}"
    # no edited/ folder = no deck came back with loops (step 20b may accept every bench as generated)
    eds_path = ext_dir / "edited" / "summary.json"
    eds = json.loads(eds_path.read_text(encoding="utf-8")) if eds_path.exists() or not midland else {"pools": {}, "source": ""}
    dref = a.decision_ref or (STEP20B_REF if step20b else STEP20A["decision_ref"] if midland else DECISION_REF if set(a.pool) <= {"BS3_S", "BS3_C"} else DECISION_REF_15)
    with get_connection() as conn:
        # --- identity, read-only
        with conn.cursor() as cur:
            cur.execute("SELECT bench, count(*) FROM box.extent WHERE basin = %s AND bench = ANY(%s) GROUP BY bench", (a.basin, list(a.pool)))
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
            ep = eds["pools"].get(pool) if midland else eds["pools"][pool]  # step 20a: only looped benches are listed
            owner_marks = 0 if ep is None else int(ep.get("n_freeforms", 1)) + int(ep.get("n_ink_strokes", 0))
            edited = _extent_geojson(ext_dir / "edited" / f"extent_{pool}_v{a.version}_edited.geojson") if owner_marks else None
            b = er.build_pool(df[df.pool == pool], pool, bp, sopa, None, edge)
            if midland and pool == "WCB_2":  # D136: the Midland WCB_2 extent stops at the WCB split line
                ws.clip_d136(b)
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
            plan[pool] = (b, edited, {k: v for k, v in diff.items() if k != "pieces"}
                          | {"source": f"owner hand edit ({Path(eds['source']).name}, Michael {loop_date})"})
        if a.dry_run:
            print("dry run: nothing written")
            return 0
        # --- writes
        with conn.cursor() as cur:
            for pool in a.pool:
                members, reason = scope_rows[pool]
                if step20b:
                    reason = reason.format(extent="extent = owner pen loop" if plan[pool][1] is not None else "generated v1 accepted")
                cur.execute(
                    """INSERT INTO box.bench_scope (basin, bench, in_scope, member_benches, reason, decided_on, decision_ref)
                       VALUES (%s, %s, %s, %s, %s, %s, %s) ON CONFLICT (basin, bench) DO NOTHING""",
                    (a.basin, pool, pool not in a.out_of_scope, members,
                     reason + ("; IN_SCOPE FALSE pending the step-14 D2 decision (extent stored for reference)" if pool in a.out_of_scope else ""),
                     decided_on, dref),
                )
        conn.commit()
        for pool, (b, edited, dstats) in plan.items():
            gid = store_generated(conn, pool, a.version, b, bp, run_id, make_record=edited is None, basin=a.basin)
            if edited is None:
                print(f"stored {pool}: generated v{a.version} extent_id {gid} = version of record (no owner marks)")
                continue
            eid = store_edited(conn, pool, a.version, edited, dstats, make_record=True, basin=a.basin)
            print(f"stored {pool}: generated v{a.version} extent_id {gid}; edited v{a.version} extent_id {eid} = version of record")
        # --- verify, read-only
        with conn.cursor() as cur:
            cur.execute("SET TRANSACTION READ ONLY")
            cur.execute(
                """SELECT e.bench, e.extent_id, e.source, e.is_record, round(e.area_sqmi::numeric, 2), e.parent_extent_id,
                          round((extensions.ST_Area(e.geom::extensions.geography) / 2589988.110336)::numeric, 1),
                          (SELECT count(*) FROM box.extent_edge g WHERE g.extent_id = e.extent_id)
                   FROM box.extent e WHERE e.basin = %s AND e.bench = ANY(%s) ORDER BY e.extent_id""",
                (a.basin, list(a.pool)),
            )
            rows = cur.fetchall()
            cur.execute("SELECT bench, count(*) FILTER (WHERE is_record) FROM box.extent WHERE basin = %s GROUP BY bench ORDER BY bench", (a.basin,))
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
