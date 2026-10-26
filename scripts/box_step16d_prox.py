"""BOX step 16d — D116's proximity re-measure on a NEW base run (READ ONLY). Kept in scripts/ so a build's resume key (box/) is untouched.

    python -m scripts.box_step16d prox-measure --run-id N [--box-db rehearsal|live]

The step-4 measurement of box/prox_pud_report.run, unchanged in substance, for a named run: its box rows (pud_forecast, location
geometry, oil / gas EUR) from the database that holds the run (the rehearsal container, later live), curated (erebor_locations TVD /
depletion / operator, the producer universe) from live — no cross-schema join. Precedent = the study's drilled children
(runs/prox links.pkl + children.pkl, data through the same 2026-07-01). Writes pud_outcomes.csv.gz + pud_summary.json to --out and
pud_links.pkl to --links-out; the run-10 reviewed files in docs/box/prox-2026-10-19 and runs/prox are never written.
"""

from __future__ import annotations

import datetime as dt
import json
import pickle
import time
from pathlib import Path
from typing import Any

import pandas as pd
import shapely

from box import edge_gap as eg
from box import prox_dose as pdz
from box import prox_pud as pp
from box import prox_pud_report as ppr
from box import prox_study_report as psr
from box.tc_curve_report import _read

_RUN_ID_SQL = "SELECT run_id, data_through, report_version, basin FROM box.forecast_run WHERE run_id = %(run)s"
_PUD_BOX_SQL = """
SELECT pf.location_id, pf.stick_id, pf.formation_blueox, pf.bench AS bench_group, pf.coverage, pf.pad_name, {ext}ST_AsText(l.geom),
       so.eur AS oil_eur, so.eur_per_kft AS oil_eur_per_kft, sg.eur AS gas_eur
FROM box.pud_forecast pf
JOIN box.location l ON l.location_id = pf.location_id
LEFT JOIN box.pud_forecast_stream so ON so.run_id = pf.run_id AND so.location_id = pf.location_id AND so.stream = 'oil'
LEFT JOIN box.pud_forecast_stream sg ON sg.run_id = pf.run_id AND sg.location_id = pf.location_id AND sg.stream = 'gas'
WHERE pf.run_id = %(run)s AND pf.basin = %(basin)s AND pf.coverage IN ('covered', 'covered_provisional')
"""
_EREBOR_SQL = "SELECT stick_id, tvd, deplet_t, operator FROM curated.erebor_locations WHERE stick_id = ANY(%(ids)s)"
COLS = ["location_id", "stick_id", "formation_blueox", "bench_group", "coverage", "pad_name", "tvd_ft", "deplet_t", "operator", "wkt",
        "oil_eur", "oil_eur_per_kft", "gas_eur"]


def _ext(conn: Any) -> str:
    """Where PostGIS lives on `conn` (live: extensions.; a rehearsal container: public.)."""
    r = _read(conn, "SELECT n.nspname FROM pg_extension e JOIN pg_namespace n ON n.oid = e.extnamespace WHERE e.extname = 'postgis'")
    return f"{r[0][0]}." if r else "extensions."


def pull(box: Any, live: Any, run_id: int) -> tuple[dict[str, Any], pd.DataFrame, pd.DataFrame]:
    run, through, rv, basin = _read(box, _RUN_ID_SQL, {"run": run_id})[0]
    b = pd.DataFrame(_read(box, _PUD_BOX_SQL.format(ext=_ext(box)), {"run": run, "basin": basin}),
                     columns=[c for c in COLS if c not in ("tvd_ft", "deplet_t", "operator")])
    e = pd.DataFrame(_read(live, _EREBOR_SQL, {"ids": [int(x) for x in b["stick_id"]]}), columns=["stick_id", "tvd_ft", "deplet_t", "operator"])
    p = b.merge(e, on="stick_id", how="left")[COLS]
    p["tvd_ft"] = pd.to_numeric(p["tvd_ft"], errors="coerce")
    for c in ("oil_eur", "oil_eur_per_kft", "gas_eur"):
        p[c] = pd.to_numeric(p[c], errors="coerce")
    p["geom"] = eg.to_ft([shapely.from_wkt(w) for w in p["wkt"]])
    n_id, eur_id = _read(box, ppr._ID_SQL, {"run": run, "basin": basin})[0]
    meta = {"run_id": run, "data_through": str(through), "report_version": rv, "identity_n": int(n_id), "identity_oil_eur": float(eur_id),
            "basin": basin}
    return meta, p.drop(columns="wkt"), psr.pull_universe(live, basin)


def run(box: Any, live: Any, run_id: int, prec_runs: Path, out: Path, links_out: Path) -> dict[str, Any]:
    """box/prox_pud_report.run's measurement on `run_id` (same links, configuration, precedent, decision and outcome columns)."""
    t0 = time.time()
    meta, p, u = pull(box, live, run_id)
    ref = dt.date.fromisoformat(meta["data_through"])
    print(f"PUDs {len(p):,}, producers {len(u):,} ({time.time() - t0:.0f} s)", flush=True)
    L = ppr.pud_links(p, u, ref)
    print(f"PUD links {len(L):,} ({time.time() - t0:.0f} s)", flush=True)
    ids = [str(x) for x in p["location_id"]]
    cfg = pdz.configuration(ids, L.assign(permit=False)).set_index("api10")
    cfg["bench"] = p.set_index(p["location_id"].astype(str))["formation_blueox"].reindex(cfg.index)
    with open(prec_runs / "links.pkl", "rb") as f:
        cl = pickle.load(f)
    with open(prec_runs / "children.pkl", "rb") as f:
        kids = pickle.load(f)
    kc = pdz.configuration(list(kids["api10"]), cl).merge(kids[["api10", "bench"]], on="api10", how="left")
    prec = pp.precedent(kc, pp.siblings(cl))
    dec = pp.decide_all(cfg, pp.haircut_lookup(pd.read_csv(ppr.HAIRCUT_TABLE)), prec)
    d = p.drop(columns="geom").assign(api10=ids).merge(cfg.drop(columns="bench").join(dec), left_on="api10", right_index=True, how="left")
    d["oil_eur_after"] = pp.eur_effect(d)
    d["n_recent_producers"] = d["api10"].map(ppr.recent_flags(L)).fillna(0).astype(int)
    d["n_permit_parents"] = d["api10"].map(ppr.permit_flags(L)).fillna(0).astype(int)
    ok = meta["identity_n"] == len(d) and abs(meta["identity_oil_eur"] - float(d["oil_eur"].sum())) <= 1e-6 * meta["identity_oil_eur"]
    meta |= {"built": dt.datetime.now(dt.UTC).strftime("%Y-%m-%d %H:%M UTC"), "n_puds": len(d), "n_links": len(L), "identity_ok": bool(ok),
             "n_precedent_pairs": len(prec), "seconds": round(time.time() - t0), "outcomes": d["outcome"].value_counts().to_dict(),
             "oil_mmbbl_before": float(d["oil_eur"].sum() / 1e6), "oil_mmbbl_after": float(d["oil_eur_after"].sum() / 1e6),
             "precedent_source": str(prec_runs), "measurement": "box/prox_pud_report step 4 on a named run (scripts/box_step16d_prox.py)"}
    out.mkdir(parents=True, exist_ok=True)
    keep = ["location_id", "stick_id", "pad_name", "operator", "formation_blueox", "bench_group", "coverage", "tvd_ft", "deplet_t", "config_class",
            "n_parents_total", "n_same", "n_topfill", "n_underfill", "flanked_topfill", "pb_topfill", "dv_topfill", "dh_topfill", "outcome", "factor",
            "haircut_key", "pair_key", "prec_multi", "prec_package", "oil_eur", "oil_eur_after", "gas_eur", "n_recent_producers", "n_permit_parents"]
    d[keep].to_csv(out / "pud_outcomes.csv.gz", index=False, compression="gzip")
    (out / "pud_summary.json").write_text(json.dumps(meta, indent=2, default=str), encoding="utf-8")
    links_out.mkdir(parents=True, exist_ok=True)
    with open(links_out / "pud_links.pkl", "wb") as f:
        pickle.dump(L, f)
    return {"meta": meta}
