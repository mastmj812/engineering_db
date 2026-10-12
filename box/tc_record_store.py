"""BOX step 5d — write the type-curve + risk-factor record to box.type_curve / tc_member / risk_factor (sql/58).

WAREHOUSE WRITES. Only called by scripts/box_tc_record.py --store, after sql/58 has been applied (explicit
go-apply) and with Michael's go-ahead for the write itself. Session pooler (5432) like the other batch jobs.
One transaction; checked by identity before commit:
  * every curve's area is an area of record on the WCA extent of record, and all 35 are covered;
  * rows written = rows built (curves, members, factors); per curve, included members = n_wells;
  * stored EUR per curve = the built value (no float drift through jsonb / double precision).
"""

from __future__ import annotations

import json
import math
from typing import Any

from box.extent_store import _clean

EUR_TOL = 1e-12


def _j(v: Any) -> str:
    return json.dumps(_clean(v))


def store_record(conn: Any, res: dict[str, Any], version: int, make_record: bool = False) -> dict[str, int]:
    tcs, mem, rf, s = res["type_curves"], res["members"], res["risk"], res["summary"]
    with conn.cursor() as cur:
        q = cur.execute
        areas = dict(q("""SELECT a.area_no, a.area_id FROM box.tc_area a JOIN box.extent e USING (extent_id)
                          WHERE e.basin = 'delaware' AND e.bench = 'WCA' AND e.is_record AND a.is_record""").fetchall())
        need = {int(a) for a in tcs["area_no"]}
        if set(areas) != need:
            conn.rollback()
            raise RuntimeError(f"areas of record {sorted(areas)} != curve areas {sorted(need)}")
        run = f"step5d {s['built_at']} (5b curves + 5c frame, blueox-boxfit {s['engine_sha'][:7]})"
        tc_ids: dict[tuple[int, str], int] = {}
        for r in tcs.to_dict("records"):
            tc_ids[(int(r["area_no"]), r["stream"])] = q(
                """INSERT INTO box.type_curve (area_id, version, stream, mode, relaxation_step, relaxation_label, thin, n_wells, anchors, params,
                                               eur_per_kft, cum12_kft, ref_mult, fit_meta, engine_sha, data_asof, generated_from_run)
                   VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s) RETURNING tc_id""",
                (areas[int(r["area_no"])], version, r["stream"], r["mode"], int(r["relaxation_step"]), r["relaxation_label"], bool(r["thin"]), int(r["n_wells"]),
                 _j(r["anchors"]), _j(r["params"]), float(r["eur_per_kft"]), float(r["cum12_kft"]), _num(r["ref_mult"]),
                 _j(r["fit_meta"]), s["engine_sha"], s["data_asof"], run)).fetchone()[0]
        mrows = [(tc_ids[(int(m["area_no"]), m["stream"])], m["api10"], bool(m["included"]), m["drop_reason"], m["lateral_ft"], m["dev_scenario"], m["parent_bench"],
                  bool(m["infill"]), _num(m["factor"]), _num(m["weight"])) for m in mem.to_dict("records")]
        cur.executemany("""INSERT INTO box.tc_member (tc_id, api10, included, drop_reason, lateral_ft, dev_scenario, parent_bench, infill, factor, weight)
                           VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)""", mrows)
        frows = [(version, r["basin"], r["bench"], r["stream"], r["metric"], r["level"], r["term"], r["dev_scenario"], r["parent_bench"], _num(r["estimate"]),
                  _num(r["ci_lo"]), _num(r["ci_hi"]), int(r["n_pairs"]), None if _num(r["n_clusters"]) is None else int(r["n_clusters"]), float(r["factor"]), int(r["rung"]),
                  r["rung_label"], int(r["n_basis"]), r["applies_to"], r["estimator"], bool(r["pud_applicable"]), _j(r["params"]), r["generated_from_run"])
                 for r in rf.to_dict("records")]
        cur.executemany("""INSERT INTO box.risk_factor (version, basin, bench, stream, metric, level, term, dev_scenario, parent_bench, estimate, ci_lo, ci_hi,
                                                        n_pairs, n_clusters, factor, rung, rung_label, n_basis, applies_to, estimator, pud_applicable, params, generated_from_run)
                           VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)""", frows)
        ids = list(tc_ids.values())
        n_tc = q("SELECT count(*) FROM box.type_curve WHERE tc_id = ANY(%s)", (ids,)).fetchone()[0]
        n_m = q("SELECT count(*) FROM box.tc_member WHERE tc_id = ANY(%s)", (ids,)).fetchone()[0]
        n_rf = q("SELECT count(*) FROM box.risk_factor WHERE version = %s", (version,)).fetchone()[0]
        bad_n = q("""SELECT count(*) FROM box.type_curve t
                     WHERE t.tc_id = ANY(%s) AND t.n_wells <> (SELECT count(*) FROM box.tc_member m WHERE m.tc_id = t.tc_id AND m.included)""", (ids,)).fetchone()[0]
        eur = {(int(a), st): float(e) for a, st, e in q(
            "SELECT a.area_no, t.stream, t.eur_per_kft FROM box.type_curve t JOIN box.tc_area a USING (area_id) WHERE t.tc_id = ANY(%s)", (ids,)).fetchall()}
        worst = max(abs(eur[(int(r["area_no"]), r["stream"])] / float(r["eur_per_kft"]) - 1.0) for r in tcs.to_dict("records"))
        problems = []
        if n_tc != len(tcs) or n_m != len(mem) or n_rf != len(rf):
            problems.append(f"rows {n_tc}/{len(tcs)} curves, {n_m}/{len(mem)} members, {n_rf}/{len(rf)} factors")
        if bad_n:
            problems.append(f"{bad_n} curves whose n_wells != included members")
        if worst > EUR_TOL:
            problems.append(f"stored EUR drift {worst:.1e}")
        if problems:
            conn.rollback()
            raise RuntimeError("identity check failed: " + "; ".join(problems))
        if make_record:
            q("UPDATE box.type_curve SET is_record = false WHERE is_record AND area_id = ANY(%s)", (list(areas.values()),))
            q("UPDATE box.type_curve SET is_record = true WHERE tc_id = ANY(%s)", (ids,))
            q("UPDATE box.risk_factor SET is_record = false WHERE is_record AND basin = 'delaware' AND bench = ANY(%s)", (sorted(set(rf["bench"])),))
            q("UPDATE box.risk_factor SET is_record = true WHERE version = %s", (version,))
    conn.commit()
    return {"type_curve": n_tc, "tc_member": n_m, "risk_factor": n_rf}


def _num(v: Any) -> float | None:
    try:
        f = float(v)
    except (TypeError, ValueError):
        return None
    return f if math.isfinite(f) else None
