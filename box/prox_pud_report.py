"""PDP-proximity study, step 4 — measure every forecast PUD of the BOX record run (READ ONLY) + page.

Universe = box.pud_forecast rows of the record run with coverage covered / covered_provisional (the PUDs that carry
a BOX forecast). PUD geometry = box.location.geom (the Novi stick), landing TVD = the Novi stick's TVD
(curated.erebor_locations.tvd by stick_id), bench = pud_forecast.formation_blueox, oil / gas EUR = the record's
pud_forecast_stream rows. Producers = the step-1 candidate universe (prox_study_report.pull_universe). Reference date =
the run's data_through. Nothing is written to the warehouse.
"""

from __future__ import annotations

import datetime as dt
import json
import pickle
import time
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
import shapely

from box import edge_gap as eg
from box import prox_dose as pdz
from box import prox_pud as pp
from box import prox_study as ps
from box import prox_study_report as psr
from box.edge_gap_report import _CSS, _table
from box.tc_curve_report import _read

HAIRCUT_TABLE = Path("docs") / "box" / "prox-2026-10-19" / "haircut_table_candidate.csv"

_RUN_SQL = "SELECT run_id, data_through, report_version FROM box.forecast_run WHERE is_record"
_PUD_SQL = """
SELECT pf.location_id, pf.stick_id, pf.formation_blueox, pf.bench AS bench_group, pf.coverage, pf.pad_name,
       el.tvd, el.deplet_t, el.operator, extensions.ST_AsText(l.geom),
       so.eur AS oil_eur, so.eur_per_kft AS oil_eur_per_kft, sg.eur AS gas_eur
FROM box.pud_forecast pf
JOIN box.location l ON l.location_id = pf.location_id
LEFT JOIN curated.erebor_locations el ON el.stick_id = pf.stick_id
LEFT JOIN box.pud_forecast_stream so ON so.run_id = pf.run_id AND so.location_id = pf.location_id AND so.stream = 'oil'
LEFT JOIN box.pud_forecast_stream sg ON sg.run_id = pf.run_id AND sg.location_id = pf.location_id AND sg.stream = 'gas'
WHERE pf.run_id = %(run)s AND pf.basin = 'delaware' AND pf.coverage IN ('covered', 'covered_provisional')
"""
_ID_SQL = """
SELECT count(*), sum(so.eur) FROM box.pud_forecast pf
JOIN box.pud_forecast_stream so ON so.run_id = pf.run_id AND so.location_id = pf.location_id AND so.stream = 'oil'
WHERE pf.run_id = %(run)s AND pf.basin = 'delaware' AND pf.coverage IN ('covered', 'covered_provisional')
"""


def pull(conn: Any) -> tuple[dict[str, Any], pd.DataFrame, pd.DataFrame]:
    run_id, through, rv = _read(conn, _RUN_SQL)[0]
    cols = ["location_id", "stick_id", "formation_blueox", "bench_group", "coverage", "pad_name", "tvd_ft", "deplet_t", "operator", "wkt",
            "oil_eur", "oil_eur_per_kft", "gas_eur"]
    p = pd.DataFrame(_read(conn, _PUD_SQL, {"run": run_id}), columns=cols)
    p["tvd_ft"] = pd.to_numeric(p["tvd_ft"], errors="coerce")
    for c in ("oil_eur", "oil_eur_per_kft", "gas_eur"):
        p[c] = pd.to_numeric(p[c], errors="coerce")
    p["geom"] = eg.to_ft([shapely.from_wkt(w) for w in p["wkt"]])
    n_id, eur_id = _read(conn, _ID_SQL, {"run": run_id})[0]
    meta = {"run_id": run_id, "data_through": str(through), "report_version": rv, "identity_n": int(n_id), "identity_oil_eur": float(eur_id)}
    return meta, p.drop(columns="wkt"), psr.pull_universe(conn)


def pud_links(p: pd.DataFrame, u: pd.DataFrame, ref: dt.date, log_every: int = 5000) -> pd.DataFrame:
    cand = u[u["tvd_ft"].notna() & (u["lat_ft"] > 0)].reset_index(drop=True)
    recs = cand[["api10", "bench", "fp", "tvd_ft", "geom"]].to_dict("records")
    tree = shapely.STRtree(list(cand["geom"]))
    out: list[ps.Link] = []
    t0 = time.time()
    for n, r in enumerate(p.itertuples()):
        if not np.isfinite(r.tvd_ft) or r.geom.length <= 0:
            continue
        me = {"api10": str(r.location_id), "bench": r.formation_blueox, "fp": ref, "tvd_ft": float(r.tvd_ft), "geom": r.geom}
        idx = tree.query(r.geom, predicate="dwithin", distance=ps.PAIR_GATE_FT)
        out.extend(pp.pud_links(me, (recs[j] for j in idx)))
        if log_every and n and n % log_every == 0:
            print(f"  PUD pairs: {n:,}/{len(p):,}, {len(out):,} links, {time.time() - t0:.0f} s", flush=True)
    return pp.links_frame(out)


def recent_flags(L: pd.DataFrame) -> pd.Series:
    """PUDs with a producer < 12 months old inside a class envelope (it becomes a parent within the year)."""
    rec = L[L["rel"].isin(["young", "codev"]) & (L["overlap"] >= ps.MIN_OVERLAP)]
    hit = np.zeros(len(rec), bool)
    for c, (vmax, hmax) in pdz.ENVELOPE.items():
        hit |= ((rec["cls"] == c) & (rec["dv_ft"] <= vmax) & (rec["dh_ft"] <= hmax)).to_numpy()
    return rec[hit].groupby("child")["parent"].nunique()


def permit_flags(L: pd.DataFrame) -> pd.Series:
    par = L[(L["rel"] == "parent") & (L["overlap"] >= ps.MIN_OVERLAP) & L["permit"]]
    hit = np.zeros(len(par), bool)
    for c, (vmax, hmax) in pdz.ENVELOPE.items():
        hit |= ((par["cls"] == c) & (par["dv_ft"] <= vmax) & (par["dh_ft"] <= hmax)).to_numpy()
    return par[hit].groupby("child")["parent"].nunique()


def tables(d: pd.DataFrame) -> dict[str, pd.DataFrame]:
    out: dict[str, pd.DataFrame] = {}
    d = d.assign(oil_mmbbl=d["oil_eur"] / 1e6, oil_after_mmbbl=d["oil_eur_after"] / 1e6)
    g = d.groupby(["formation_blueox", "coverage"])
    t = g.agg(n_puds=("location_id", "size"), oil_mmbbl=("oil_mmbbl", "sum"), oil_after_mmbbl=("oil_after_mmbbl", "sum"))
    for o in pp.OUTCOMES:
        t[o] = g["outcome"].apply(lambda s, o=o: int((s == o).sum()))
    t["oil_change_pct"] = 100.0 * (t["oil_after_mmbbl"] / t["oil_mmbbl"] - 1.0)
    t["no_forecast_pct"] = 100.0 * (t["no_forecast_precedent"] + t["no_forecast_package"]) / t["n_puds"]
    tot = t.sum(numeric_only=True)
    tot["oil_change_pct"] = 100.0 * (tot["oil_after_mmbbl"] / tot["oil_mmbbl"] - 1.0)
    tot["no_forecast_pct"] = 100.0 * (tot["no_forecast_precedent"] + tot["no_forecast_package"]) / tot["n_puds"]
    t = t.reset_index()
    t.loc[len(t)] = {"formation_blueox": "ALL", "coverage": "", **tot.to_dict()}
    out["by_bench"] = t
    out["by_outcome"] = (d.groupby("outcome").agg(n_puds=("location_id", "size"), oil_mmbbl=("oil_mmbbl", "sum"),
                                                  oil_after_mmbbl=("oil_after_mmbbl", "sum")).reindex(list(pp.OUTCOMES)).fillna(0).reset_index())
    out["by_config"] = (d[d["haircut_key"].notna()].groupby(["haircut_key", "outcome"])
                        .agg(n_puds=("location_id", "size"), factor=("factor", "first")).reset_index().sort_values("n_puds", ascending=False))
    out["by_pair"] = (d[d["pair_key"].notna()].groupby(["pair_key", "outcome"])
                      .agg(n_puds=("location_id", "size"), prec_multi=("prec_multi", "first"), prec_package=("prec_package", "first"),
                           oil_mmbbl=("oil_mmbbl", "sum")).reset_index().sort_values("n_puds", ascending=False))
    tier = d["deplet_t"].fillna("(none)")
    out["tier4"] = pd.crosstab(d["outcome"], tier, margins=True).reset_index()
    out["bs3s"] = (d[d["formation_blueox"] == "BS3_S"].groupby(["outcome", d["haircut_key"].fillna("-")])
                   .agg(n_puds=("location_id", "size"), oil_mmbbl=("oil_mmbbl", "sum"), oil_after_mmbbl=("oil_after_mmbbl", "sum"))
                   .reset_index().sort_values("n_puds", ascending=False))
    return out


def render(T: dict[str, pd.DataFrame], meta: dict[str, Any]) -> str:
    fmt = {"oil_mmbbl": ",.1f", "oil_after_mmbbl": ",.1f", "oil_change_pct": ".1f", "no_forecast_pct": ".1f", "factor": ".3f"}
    p = [(f"<!doctype html><html><head><meta charset=utf-8><title>PDP proximity PUDs</title><style>{_CSS} body{{overflow-x:hidden}} "
          "table{display:block;overflow-x:auto;max-width:100%}</style></head><body>"),
         "<h1>PDP-proximity study — step 4: every BOX PUD measured (read-only)</h1>",
         (f"<div class=meta>{meta['built']} · BOX record run {meta['run_id']} (data through {meta['data_through']}, Novi {meta['report_version']}) · "
          f"{meta['n_puds']:,} forecast PUDs · identity {'OK' if meta['identity_ok'] else 'FAILED'} · nothing written</div>"),
         ("<p>Each PUD is measured against every producer ≥ 12 months on production at the data date, with the step-1 metric "
          "and no shielding exemption. Permit-round producer TVDs are counted and flagged. Option (a): only multi-parent "
          "configurations get the oil haircut (cum-24, BOX's calibrated level); single-parent and unexposed PUDs stay as-is. "
          f"Two-tier precedent: ≥ {pp.PRECEDENT_FLOOR} drilled multi-parent wells of the PUD's bench pair, and ≥ {pp.PRECEDENT_FLOOR} "
          f"drilled packages where the haircut ≤ {pp.SEVERE:.2f}; short of either means no forecast. Oil EUR = the record's 50-yr raw EUR "
          "(MMbbl). 'After' = as-is ×1, haircut × factor, no forecast 0. Gas is untouched except where there's no forecast.</p>"),
         "<h2>By outcome</h2>", _table(T["by_outcome"], fmt),
         "<h2>By bench</h2>", _table(T["by_bench"], fmt),
         "<h2>BS3_S</h2>", _table(T["bs3s"], fmt),
         "<h2>By bench pair (multi-parent PUDs)</h2>", _table(T["by_pair"], fmt, max_rows=80),
         "<h2>By haircut configuration</h2>", _table(T["by_config"], fmt, max_rows=60),
         "<h2>Outcome × Novi depletion tier</h2>", _table(T["tier4"]),
         "</body></html>"]
    return "\n".join(p)


def run(conn: Any, runs: Path, out: Path) -> dict[str, Any]:
    t0 = time.time()
    meta, p, u = pull(conn)
    ref = dt.date.fromisoformat(meta["data_through"])
    print(f"PUDs {len(p):,}, producers {len(u):,} ({time.time() - t0:.0f} s)", flush=True)
    L = pud_links(p, u, ref)
    print(f"PUD links {len(L):,} ({time.time() - t0:.0f} s)", flush=True)
    ids = [str(x) for x in p["location_id"]]
    cfg = pdz.configuration(ids, L.assign(permit=False)).set_index("api10")
    cfg["bench"] = p.set_index(p["location_id"].astype(str))["formation_blueox"].reindex(cfg.index)
    with open(runs / "links.pkl", "rb") as f:
        cl = pickle.load(f)
    with open(runs / "children.pkl", "rb") as f:
        kids = pickle.load(f)
    kc = pdz.configuration(list(kids["api10"]), cl).merge(kids[["api10", "bench"]], on="api10", how="left")
    prec = pp.precedent(kc, pp.siblings(cl))
    hair = pp.haircut_lookup(pd.read_csv(HAIRCUT_TABLE))
    dec = pp.decide_all(cfg, hair, prec)
    d = p.drop(columns="geom").assign(api10=ids).merge(cfg.drop(columns="bench").join(dec), left_on="api10", right_index=True, how="left")
    d["oil_eur_after"] = pp.eur_effect(d)
    d["n_recent_producers"] = d["api10"].map(recent_flags(L)).fillna(0).astype(int)
    d["n_permit_parents"] = d["api10"].map(permit_flags(L)).fillna(0).astype(int)
    T = tables(d)
    ok = meta["identity_n"] == len(d) and abs(meta["identity_oil_eur"] - float(d["oil_eur"].sum())) <= 1e-6 * meta["identity_oil_eur"]
    meta |= {"built": dt.datetime.now(dt.UTC).strftime("%Y-%m-%d %H:%M UTC"), "n_puds": len(d), "n_links": len(L), "identity_ok": bool(ok),
             "n_precedent_pairs": len(prec), "severe": pp.SEVERE, "floor": pp.PRECEDENT_FLOOR, "seconds": round(time.time() - t0),
             "outcomes": d["outcome"].value_counts().to_dict(),
             "oil_mmbbl_before": float(d["oil_eur"].sum() / 1e6), "oil_mmbbl_after": float(d["oil_eur_after"].sum() / 1e6)}
    out.mkdir(parents=True, exist_ok=True)
    keep = ["location_id", "stick_id", "pad_name", "operator", "formation_blueox", "bench_group", "coverage", "tvd_ft", "deplet_t", "config_class",
            "n_parents_total", "n_same", "n_topfill", "n_underfill", "flanked_topfill", "pb_topfill", "dv_topfill", "dh_topfill", "outcome", "factor",
            "haircut_key", "pair_key", "prec_multi", "prec_package", "oil_eur", "oil_eur_after", "gas_eur", "n_recent_producers", "n_permit_parents"]
    d[keep].to_csv(out / "pud_outcomes.csv.gz", index=False, compression="gzip")
    for k, t in T.items():
        t.to_csv(out / f"pud_{k}.csv", index=False)
    (out / "pud_summary.json").write_text(json.dumps(meta, indent=2, default=str), encoding="utf-8")
    (out / "pud.html").write_text(render(T, meta), encoding="utf-8")
    with open(runs / "pud_links.pkl", "wb") as f:
        pickle.dump(L, f)
    return {"meta": meta, "tables": T}
