"""BOX record run 11 = run 10 + the PDP-proximity layer (D112-D116, sql/65). Plan: docs/box/prox-2026-10-19/RECORD_PLAN.md.

    python -m scripts.box_prox_record store                 # build run 11 inside ONE transaction, check identities, ROLL BACK
    python -m scripts.box_prox_record store --commit        # ... and COMMIT (run 11 stored, NOT record)
    python -m scripts.box_prox_record store --commit --record   # ... and flip the record: run 10 superseded_by 11, kept (priced, D82/D104)

No refit: every row is copied from the source record run inside the database and transformed:
  * multi-parent PUD with precedent  -> oil stream prox_factor = factor; oil eur / eur_per_kft / cum12 / cum24 and every oil month x factor;
                                        gas / water rows and months byte-identical
  * multi-parent PUD w/o precedent   -> coverage not_covered_no_precedent (search provenance kept); no stream / month / analog rows
  * single-parent / unexposed PUD    -> identical to the source run
  * pud_proximity + pud_proximity_parent rows from box.prox_record.prepare (gate-4 outcomes + PUD links, digest-stamped)
Identities are checked before COMMIT; any failure rolls back. !! Writing to the shared warehouse needs an explicit go ("go store");
DB_* environment variables point it at the rehearsal container instead.
"""

from __future__ import annotations

import argparse
import datetime as dt
import math
import pickle
import subprocess
import sys
import time
from pathlib import Path
from typing import Any

import pandas as pd
from psycopg.types.json import Jsonb

from box import prox_record as prc
from etl.db import get_connection

DOCS = Path("docs") / "box" / "prox-2026-10-19"
OUTCOMES = DOCS / "pud_outcomes.csv.gz"
HAIRCUT = DOCS / "haircut_table_candidate.csv"
CODE = ["box/prox_record.py", "box/prox_pud.py", "box/prox_dose.py", "box/prox_study.py", "scripts/box_prox_record.py", "sql/65_box_proximity.sql"]
REL_TOL = 1e-9

_failures: list[str] = []


def _check(ok: bool, msg: str) -> None:
    print(f"    {'ok  ' if ok else 'FAIL'} {msg}", flush=True)
    if not ok:
        _failures.append(msg)


def _git(*a: str) -> str:
    return subprocess.run(["git", *a], capture_output=True, text=True, check=False).stdout.strip()


def _cols(q: Any, t: str) -> list[str]:
    return [r[0] for r in q("SELECT column_name FROM information_schema.columns WHERE table_schema = 'box' AND table_name = %s ORDER BY ordinal_position",
                            (t,)).fetchall()]


def _none(v: Any) -> Any:
    return None if v is None or v is pd.NA or (isinstance(v, float) and math.isnan(v)) else v


def _copy(cur: Any, table: str, cols: list[str], df: pd.DataFrame) -> None:
    with cur.copy(f"COPY {table} ({', '.join(cols)}) FROM STDIN") as cp:
        for row in df[cols].itertuples(index=False):
            cp.write_row([_none(v) for v in row])


def store(a: argparse.Namespace) -> int:
    t0 = time.time()
    dirty = _git("status", "--porcelain", "--", *CODE, str(OUTCOMES), str(HAIRCUT))
    if dirty and not a.allow_dirty:
        sys.exit(f"code / inputs not committed:\n{dirty}")
    code_sha = _git("rev-parse", "HEAD")
    links_pkl = a.runs / "pud_links.pkl"
    dig = {"outcomes": prc.sha256(OUTCOMES), "haircut_table": prc.sha256(HAIRCUT), "pud_links": prc.sha256(links_pkl)}
    table_ref = f"haircut_table sha256:{dig['haircut_table'][:16]} prereg:{prc.PREREG_COMMIT} outcomes sha256:{dig['outcomes'][:16]}"
    with open(links_pkl, "rb") as f:
        links = pickle.load(f)
    P = prc.prepare(pd.read_csv(OUTCOMES), links, table_ref)
    prox, parents, exp = P["prox"], P["parents"], P["expected"]
    print(f"prepared {len(prox):,} proximity rows, {len(parents):,} parents ({time.time() - t0:.0f} s); digests {dig}", flush=True)

    conn = get_connection()
    try:
        with conn.cursor() as cur:
            q = cur.execute
            src = q("SELECT run_id, data_through FROM box.forecast_run WHERE is_record").fetchone()
            _check(src is not None and src[0] == a.src_run, f"source run {a.src_run} is the record ({src})")
            if _failures:
                raise RuntimeError("source run check failed")
            S = a.src_run
            # ---- temp table of every forecast-universe PUD: factor (1 = as-is), keep (has a forecast in the new run)
            q("CREATE TEMP TABLE tmp_px (location_id bigint PRIMARY KEY, factor double precision NOT NULL, keep boolean NOT NULL) ON COMMIT DROP")
            tp = pd.DataFrame({"location_id": prox["location_id"].astype("int64"), "factor": prox["factor"].astype(float),
                               "keep": ~prox["outcome"].isin(prc.NO_FORECAST)})
            _copy(cur, "tmp_px", ["location_id", "factor", "keep"], tp)
            n_src = q("SELECT count(*) FROM box.pud_forecast WHERE run_id = %s AND coverage IN ('covered', 'covered_provisional')", (S,)).fetchone()[0]
            n_join = q("SELECT count(*) FROM box.pud_forecast p JOIN tmp_px t USING (location_id) WHERE p.run_id = %s "
                       "AND p.coverage IN ('covered', 'covered_provisional')", (S,)).fetchone()[0]
            _check(n_src == len(tp) == n_join, f"proximity universe = run {S} forecast PUDs by identity ({len(tp):,} / {n_src:,} / {n_join:,})")
            if _failures:
                raise RuntimeError("universe identity failed")
            # ---- 1. forecast_run
            oil_before = q("SELECT sum(eur) FROM box.pud_forecast_stream WHERE run_id = %s AND stream = 'oil'", (S,)).fetchone()[0]
            oil_after = q("SELECT sum(s.eur * t.factor) FROM box.pud_forecast_stream s JOIN tmp_px t USING (location_id) "
                          "WHERE s.run_id = %s AND s.stream = 'oil' AND t.keep", (S,)).fetchone()[0]
            disc = prc.disclosure(exp, table_ref, oil_before / 1e6, oil_after / 1e6)
            disc["inputs"] = {**dig, "code_sha": code_sha, "source_run": S}
            note = (f"; run {{new}} = run {S} + PDP-proximity layer (D112-D116, sql/65): oil x configuration factor on {exp['outcomes'].get('haircut', 0):,} "
                    f"multi-parent PUDs, {sum(exp['outcomes'].get(k, 0) for k in prc.NO_FORECAST):,} not_covered_no_precedent; gas / water / analogs "
                    f"identical; no refit")
            new = q("""INSERT INTO box.forecast_run (spec, code_sha, engine_sha, dealintake_config, report_version, data_through, volumes_basis,
                           horizon_months, haircut, calendar_factor, disclosure, extents, counts, notes, is_record)
                       SELECT spec, %s, engine_sha, dealintake_config, report_version, data_through, volumes_basis, horizon_months, haircut,
                              calendar_factor, disclosure || jsonb_build_object('proximity', %s::jsonb), extents, counts, notes, false
                       FROM box.forecast_run WHERE run_id = %s RETURNING run_id""", (code_sha, Jsonb(disc), S)).fetchone()[0]
            q("UPDATE box.forecast_run SET notes = notes || %s WHERE run_id = %s", (note.format(new=new), new))
            print(f"run {new} created from run {S} ({time.time() - t0:.0f} s)", flush=True)
            # ---- 2. pud_forecast (whole universe; no-forecast PUDs re-classed)
            pc = _cols(q, "pud_forecast")
            sel = ", ".join("%(new)s" if c == "run_id" else
                            "CASE WHEN t.keep IS FALSE THEN 'not_covered_no_precedent' ELSE p.coverage END" if c == "coverage" else f"p.{c}" for c in pc)
            q(f"INSERT INTO box.pud_forecast ({', '.join(pc)}) SELECT {sel} FROM box.pud_forecast p LEFT JOIN tmp_px t USING (location_id) "
              "WHERE p.run_id = %(src)s", {"new": new, "src": S})
            # ---- 3. streams (survivors; oil scaled)
            sc = [c for c in _cols(q, "pud_forecast_stream")]
            scaled = {"eur", "eur_per_kft", "cum12", "cum24"}
            sel = ", ".join("%(new)s" if c == "run_id" else
                            "CASE WHEN s.stream = 'oil' THEN t.factor ELSE 1 END" if c == "prox_factor" else
                            f"CASE WHEN s.stream = 'oil' AND t.factor <> 1 THEN s.{c} * t.factor ELSE s.{c} END" if c in scaled else f"s.{c}" for c in sc)
            q(f"INSERT INTO box.pud_forecast_stream ({', '.join(sc)}) SELECT {sel} FROM box.pud_forecast_stream s JOIN tmp_px t USING (location_id) "
              "WHERE s.run_id = %(src)s AND t.keep", {"new": new, "src": S})
            print(f"  pud_forecast + streams ({time.time() - t0:.0f} s)", flush=True)
            # ---- 4. months (survivors; oil scaled)
            q("""INSERT INTO box.pud_forecast_month (run_id, location_id, stream, month_no, volume)
                 SELECT %(new)s, m.location_id, m.stream, m.month_no,
                        CASE WHEN m.stream = 'oil' AND t.factor <> 1 THEN m.volume * t.factor ELSE m.volume END
                 FROM box.pud_forecast_month m JOIN tmp_px t USING (location_id) WHERE m.run_id = %(src)s AND t.keep""", {"new": new, "src": S})
            print(f"  months ({time.time() - t0:.0f} s)", flush=True)
            # ---- 5. analogs (survivors)
            for t in ("location_analog", "location_water_analog"):
                ac = _cols(q, t)
                sel = ", ".join("%(new)s" if c == "run_id" else f"a.{c}" for c in ac)
                q(f"INSERT INTO box.{t} ({', '.join(ac)}) SELECT {sel} FROM box.{t} a JOIN tmp_px x USING (location_id) "
                  "WHERE a.run_id = %(src)s AND x.keep", {"new": new, "src": S})
            # ---- 6. proximity rows
            _copy(cur, "box.pud_proximity", ["run_id", *prc.PROX_COLS], prox.assign(run_id=new))
            _copy(cur, "box.pud_proximity_parent", ["run_id", *prc.PARENT_COLS], parents.assign(run_id=new))
            # ---- 7. counts
            q("""UPDATE box.forecast_run SET counts = (SELECT jsonb_object_agg(coverage, n) FROM (SELECT coverage, count(*) n FROM box.pud_forecast
                 WHERE run_id = %(new)s GROUP BY 1) c) || jsonb_build_object('proximity', %(px)s::jsonb) WHERE run_id = %(new)s""",
              {"new": new, "px": Jsonb(exp["outcomes"])})
            print(f"  analogs + proximity + counts ({time.time() - t0:.0f} s)", flush=True)
            identity(q, S, new, exp, len(parents))
            if not _failures and a.record:
                q("UPDATE box.forecast_run SET is_record = false, superseded_by = %s WHERE run_id = %s", (new, S))
                q("UPDATE box.forecast_run SET is_record = true WHERE run_id = %s", (new,))
                _check(q("SELECT run_id FROM box.forecast_run WHERE is_record").fetchall() == [(new,)], f"run {new} is the one record")
        if _failures:
            conn.rollback()
            print(f"ROLLED BACK: {len(_failures)} identity check(s) failed", flush=True)
            return 1
        if a.commit:
            conn.commit()
            with conn.cursor() as cur:
                for t in ("pud_forecast", "pud_forecast_stream", "pud_forecast_month", "location_analog", "location_water_analog", "pud_proximity",
                          "pud_proximity_parent"):
                    cur.execute(f"ANALYZE box.{t}")
            conn.commit()
            print(f"COMMITTED run {new}{' as RECORD' if a.record else ''} ({time.time() - t0:.0f} s)", flush=True)
        else:
            conn.rollback()
            print(f"rehearsal OK — rolled back (pass --commit to store) ({time.time() - t0:.0f} s)", flush=True)
    finally:
        conn.close()
    return 0


def identity(q: Any, S: int, new: int, exp: dict[str, Any], n_parents: int) -> None:
    print("identities", flush=True)
    src = dict(q("SELECT coverage, count(*) FROM box.pud_forecast WHERE run_id = %s GROUP BY 1", (S,)).fetchall())
    got = dict(q("SELECT coverage, count(*) FROM box.pud_forecast WHERE run_id = %s GROUP BY 1", (new,)).fetchall())
    want = dict(src)
    for cov, n in exp["moved_to_no_precedent"].items():
        want[cov] -= n
    want["not_covered_no_precedent"] = sum(exp["moved_to_no_precedent"].values())
    _check(got == want, f"pud_forecast coverage counts = source with the no-precedent moves ({got})")
    n_drop = want["not_covered_no_precedent"]
    for st, n in q("SELECT stream, count(*) FROM box.pud_forecast_stream WHERE run_id = %s GROUP BY 1", (S,)).fetchall():
        m = q("SELECT count(*) FROM box.pud_forecast_stream WHERE run_id = %s AND stream = %s", (new, st)).fetchone()[0]
        _check(m == n - n_drop, f"{st} stream rows {m:,} = {n:,} - {n_drop:,}")
    r = q("""SELECT sum(s1.eur), sum(s0.eur * t.factor) FROM box.pud_forecast_stream s1
             JOIN box.pud_forecast_stream s0 ON s0.run_id = %s AND s0.location_id = s1.location_id AND s0.stream = s1.stream
             JOIN tmp_px t ON t.location_id = s1.location_id WHERE s1.run_id = %s AND s1.stream = 'oil'""", (S, new)).fetchone()
    _check(abs(r[0] - r[1]) <= REL_TOL * r[1], f"oil EUR {r[0] / 1e6:,.3f} MMbbl = source x factor {r[1] / 1e6:,.3f}")
    for st in ("gas", "water"):
        r = q("""SELECT count(*) FILTER (WHERE s1.eur IS DISTINCT FROM s0.eur OR s1.params IS DISTINCT FROM s0.params OR s1.prox_factor <> 1)
                 FROM box.pud_forecast_stream s1 JOIN box.pud_forecast_stream s0 ON s0.run_id = %s AND s0.location_id = s1.location_id
                 AND s0.stream = s1.stream WHERE s1.run_id = %s AND s1.stream = %s""", (S, new, st)).fetchone()[0]
        _check(r == 0, f"{st} stream rows identical to the source ({r} differ)")
    n0 = q("SELECT count(*) FROM box.pud_forecast_month m JOIN tmp_px t USING (location_id) WHERE m.run_id = %s AND t.keep", (S,)).fetchone()[0]
    n1 = q("SELECT count(*) FROM box.pud_forecast_month WHERE run_id = %s", (new,)).fetchone()[0]
    _check(n0 == n1, f"month rows {n1:,} = source survivors {n0:,}")
    h = """SELECT md5(string_agg(hh, '' ORDER BY location_id, stream)) FROM (
             SELECT m.location_id, m.stream, md5(string_agg(m.volume::text, ',' ORDER BY m.month_no)) hh
             FROM box.pud_forecast_month m JOIN tmp_px t USING (location_id)
             WHERE m.run_id = %s AND t.keep AND (m.stream <> 'oil' OR t.factor = 1) GROUP BY 1, 2) x"""
    a0, a1 = q(h, (S,)).fetchone()[0], q(h, (new,)).fetchone()[0]
    _check(a0 == a1, "gas / water months + as-is oil months: ordered md5 identical to the source")
    r = q("""SELECT sum(m1.volume), sum(m0.volume * t.factor), count(*) FILTER (WHERE abs(m1.volume - m0.volume * t.factor) > 1e-9 * greatest(m0.volume, 1))
             FROM box.pud_forecast_month m1 JOIN box.pud_forecast_month m0 ON m0.run_id = %s AND m0.location_id = m1.location_id
             AND m0.stream = m1.stream AND m0.month_no = m1.month_no JOIN tmp_px t ON t.location_id = m1.location_id
             WHERE m1.run_id = %s AND m1.stream = 'oil' AND t.factor <> 1""", (S, new)).fetchone()
    _check(r[2] == 0 and (r[0] is None or abs(r[0] - r[1]) <= REL_TOL * r[1]), f"haircut oil months = source x factor ({r[2]} rows off)")
    for t in ("location_analog", "location_water_analog"):
        n0 = q(f"SELECT count(*) FROM box.{t} a JOIN tmp_px x USING (location_id) WHERE a.run_id = %s AND x.keep", (S,)).fetchone()[0]
        n1 = q(f"SELECT count(*) FROM box.{t} WHERE run_id = %s", (new,)).fetchone()[0]
        _check(n0 == n1, f"{t} {n1:,} = source survivors {n0:,}")
    oc = dict(q("SELECT outcome, count(*) FROM box.pud_proximity WHERE run_id = %s GROUP BY 1", (new,)).fetchall())
    _check(oc == exp["outcomes"], f"pud_proximity outcomes = gate-4 measurement ({oc})")
    _check(q("SELECT count(*) FROM box.pud_proximity_parent WHERE run_id = %s", (new,)).fetchone()[0] == n_parents, f"{n_parents:,} named parents")
    bad = q("""SELECT count(*) FROM box.pud_proximity x JOIN box.pud_forecast_stream s ON s.run_id = x.run_id AND s.location_id = x.location_id
               AND s.stream = 'oil' WHERE x.run_id = %s AND abs(s.prox_factor - x.factor) > 1e-12""", (new,)).fetchone()[0]
    _check(bad == 0, "oil prox_factor = pud_proximity.factor on every forecast PUD")
    _check(q("SELECT count(*) FROM box.pud_forecast_stream WHERE run_id = %s AND prox_factor <> 1", (S,)).fetchone()[0] == 0, f"run {S} untouched")


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    s = sub.add_parser("store")
    s.add_argument("--src-run", type=int, default=10)
    s.add_argument("--runs", type=Path, default=Path("runs") / "prox")
    s.add_argument("--commit", action="store_true")
    s.add_argument("--record", action="store_true")
    s.add_argument("--allow-dirty", action="store_true", help="rehearsal only: allow uncommitted code / inputs")
    a = ap.parse_args(argv)
    if a.record and not a.commit:
        ap.error("--record needs --commit")
    rc = store(a)
    print(f"[{dt.datetime.now(dt.UTC):%Y-%m-%d %H:%M} UTC] {'FAILED' if _failures or rc else 'done'}")
    return rc or (1 if _failures else 0)


if __name__ == "__main__":
    sys.exit(main())
