"""BOX — 3-D spacing knob sweep (read-only): which feature settings carry the most signal, and are the stored-pair
settings (gate, overlap floor) generous enough to hold the best ones? (Michael 2026-10-13: sweep, then author sql/59.)

Pairs are built ONCE at the generous storage settings (gate 3,960 ft on the stick-to-stick distance, overlap >= 10 %,
parents within 800 ft TVD carry their cum series); every variant re-derives features from them (box.spacing3d.Params),
exactly as features will be derived from the stored pair table after sql/59 is applied.

Score per variant, within TC area + first-production year + ln lateral (the controls the BOX model already has):
  * dR2 — gain in BLOCKED 5-fold CV R2 (3-mi blocks, seeded) from adding the spacing features
    (ln drainage cross-section, ln lateral spacing, ln(1 + parent cum per kft) [+ ellipse count when on]);
  * absorbed — share of the 2024-vs-2018 year effect removed by adding them (full sample).
Responses: ln 12-mo oil / kft (level), ln cum-24 / cum-6 (shape, peak-timing sensitive), ln rate months 19-24 / 4-6
(shape, past the median month-2 peak).
"""

from __future__ import annotations

import datetime as dt
import json
from dataclasses import asdict, replace
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from box import dev_factor as dfm
from box import edge_gap as eg
from box import edge_gap_report as egr
from box import exclusions
from box import shape_drift as sd
from box import spacing3d as s3
from box import spacing3d_report as sr
from box import tc_curve_report as rep
from box.edge_gap_report import _CSS, _table

STORE_GATE = 3960.0
STORE_OVERLAP = 0.10
STORE_PARENT_DZ = 800.0
RESPONSES = ("ln_oil12_kft", "ln_r24_6", "ln_rate_19_24_vs_4_6")
FOLDS = 5
SEED = 20261013

VARIANTS: dict[str, s3.Params] = {
    "default (A 2, same-dz 250, ellipse 660x300, parent-dz 500, gate 2,640, overlap 0.30)": s3.DEFAULT,
    "A 1": replace(s3.DEFAULT, aniso=1.0),
    "A 4": replace(s3.DEFAULT, aniso=4.0),
    "same-dz 150": replace(s3.DEFAULT, same_dz_ft=150.0),
    "same-dz 400": replace(s3.DEFAULT, same_dz_ft=400.0),
    "ellipse off": replace(s3.DEFAULT, ellipse_ft=None),
    "ellipse 1,320 x 500": replace(s3.DEFAULT, ellipse_ft=(1320.0, 500.0)),
    "parent-dz 300": replace(s3.DEFAULT, parent_dz_ft=300.0),
    "parent-dz 800": replace(s3.DEFAULT, parent_dz_ft=800.0),
    "A 0.5": replace(s3.DEFAULT, aniso=0.5),
    "same-dz 600": replace(s3.DEFAULT, same_dz_ft=600.0),
    "gate 1,320": replace(s3.DEFAULT, gate_ft=1320.0),
    "gate 1,980": replace(s3.DEFAULT, gate_ft=1980.0),
    "gate 3,960": replace(s3.DEFAULT, gate_ft=3960.0),
    "overlap 0.10": replace(s3.DEFAULT, min_overlap=0.10),
    "overlap 0.50": replace(s3.DEFAULT, min_overlap=0.50),
}


def subjects(conn: Any, wells_dir: Path) -> pd.DataFrame:
    wells, _ = exclusions.drop(egr.load_final_sets(wells_dir, ("WCA",)))
    wells["lateral_ft"] = pd.to_numeric(wells["lateral_length_ft"], errors="coerce")
    w = wells[np.array([f >= dt.date(2016, 1, 1) for f in wells["first_production_date"]]) & (wells["lateral_ft"] > 0).to_numpy()].reset_index(drop=True)
    areas = rep.pull_areas(conn)
    x, y = eg._transformer().transform(w["mid_lon"].to_numpy(float), w["mid_lat"].to_numpy(float))
    w["x"], w["y"] = np.asarray(x) * eg._M_TO_FT, np.asarray(y) * eg._M_TO_FT
    w["area_no"] = rep.assign_area(np.column_stack([w["x"], w["y"]]), areas["geoms"])
    w = w[w["area_no"] > 0].reset_index(drop=True)
    asof = rep.last_full_month(rep._read(conn, rep._MONTHS_SQL))
    m = sd.monthly(rep.pull_production(conn, list(w["api10"]), asof), list(w["api10"]), asof)
    d = pd.concat([w, sd.shape_metrics(m)], axis=1)
    d["fpy"] = [str(f.year) for f in d["first_production_date"]]
    d["ln_lat"] = np.log(d["lateral_ft"])
    d["ln_oil12_kft"] = np.log(pd.to_numeric(d["oil12_kft"], errors="coerce").where(lambda v: v > 0))
    d["ln_r24_6"] = np.log(d["r24_6"].where(d["r24_6"] > 0))
    d["ln_rate_19_24_vs_4_6"] = np.log(d["cal_rate_ratio_19_24_vs_4_6"].where(d["cal_rate_ratio_19_24_vs_4_6"] > 0))
    resp = list(RESPONSES)
    d[resp] = d[resp].replace([np.inf, -np.inf], np.nan)  # cum-6 = 0 makes a ratio infinite: not a shape, drop it
    d.attrs["asof"] = asof
    return d


def design(d: pd.DataFrame, num: list[str]) -> np.ndarray:
    X = [np.ones(len(d)), d["ln_lat"].to_numpy(float)]
    X += [c.to_numpy(float) for _, c in pd.get_dummies(d["fpy"], drop_first=True).items()]
    X += [c.to_numpy(float) for _, c in pd.get_dummies(d["area_no"].astype(str), drop_first=True).items()]
    X += [d[c].to_numpy(float) for c in num]
    return np.column_stack(X)


def cv_r2(d: pd.DataFrame, y: str, num: list[str], fold: np.ndarray) -> float:
    X, yv = design(d, num), d[y].to_numpy(float)
    pred = np.full(len(yv), np.nan)
    for f in range(FOLDS):
        te = fold == f
        b, *_ = np.linalg.lstsq(X[~te], yv[~te], rcond=None)
        pred[te] = X[te] @ b
    return float(1 - np.sum((yv - pred) ** 2) / np.sum((yv - yv.mean()) ** 2))


def score(d: pd.DataFrame, feats: pd.DataFrame, prm: s3.Params) -> list[dict[str, Any]]:
    num = ["ln_xsec", "ln_lat_spacing", "ln1p_parent_cum"] + (["n_ellipse"] if prm.ellipse_ft else [])
    x = d.merge(feats[["api10", *num]], on="api10", how="left")
    rows = []
    for y in RESPONSES:
        pop = x.dropna(subset=[y, "ln_lat", *num]).reset_index(drop=True)
        blk = dfm.blocks(pop["x"].to_numpy(), pop["y"].to_numpy())
        u, inv = np.unique(blk, return_inverse=True)
        fold = (np.random.default_rng(SEED).permutation(len(u)) % FOLDS)[inv]
        r0, r1 = cv_r2(pop, y, [], fold), cv_r2(pop, y, num, fold)
        e0 = sd.fe_ols(pop, y, ["ln_lat"], ["area_no"]).get("2024", np.nan)
        e1 = sd.fe_ols(pop, y, ["ln_lat", *num], ["area_no"]).get("2024", np.nan)
        rows.append({"response": y, "n": len(pop), "cv_r2_base": r0, "cv_r2_with": r1, "d_r2_pts": 100 * (r1 - r0),
                     "yr2024_base": float(np.expm1(e0)), "yr2024_with": float(np.expm1(e1)), "absorbed": float(1 - e1 / e0) if e0 else np.nan})
    return rows


def run(conn: Any, wells_dir: Path, out: Path) -> dict[str, Any]:
    out.mkdir(parents=True, exist_ok=True)
    d = subjects(conn, wells_dir)
    P = sr.build_pairs(conn, d[["api10", "mid_lon", "mid_lat"]], gate_ft=STORE_GATE, min_overlap=STORE_OVERLAP, parent_dz_ft=STORE_PARENT_DZ)
    rows = []
    for name, prm in VARIANTS.items():
        f = sr.features_table(P, d["api10"], prm=prm)
        for r in score(d, f, prm):
            rows.append({"variant": name, **r, "median_xsec_ft2": float(f["xsec_ft2"].median()), "median_lat_spacing_ft": float(f["lat_spacing_ft"].median())})
    t = pd.DataFrame(rows)
    # how far the stored pairs reach: share of pairs a default feature would use, by gate / overlap
    allp = [p for ps in P["pairs"].values() for p in ps if p.relation != "child"]
    reach = {"n_pairs_stored": len(allp), "share_dmin_gt_2640": float(np.mean([p.dmin > 2640 for p in allp])),
             "share_overlap_lt_0.30": float(np.mean([p.overlap < 0.30 for p in allp])), "pairs_per_subject": len(allp) / max(1, len(P["pairs"]))}
    built = dt.datetime.now(tz=dt.UTC).astimezone().isoformat(timespec="seconds")
    summ = {"built_at": built, "asof": str(d.attrs["asof"]), "store": {"gate_ft": STORE_GATE, "min_overlap": STORE_OVERLAP, "parent_dz_ft": STORE_PARENT_DZ},
            "meta": P["meta"], "reach": reach, "variants": {k: asdict(v) for k, v in VARIANTS.items()}}
    (out / "sweep.html").write_text(render(summ, t), encoding="utf-8")
    t.to_csv(out / "sweep.csv", index=False)
    (out / "sweep_summary.json").write_text(json.dumps(summ, indent=2, default=str), encoding="utf-8")
    return {"summary": summ, "table": t}


def render(s: dict[str, Any], t: pd.DataFrame) -> str:
    parts = ["<!doctype html><html><head><meta charset=utf-8><meta name=viewport content='width=device-width,initial-scale=1'><title>BOX 3-D spacing sweep</title>",
             f"<style>{_CSS} body{{overflow-x:hidden}} table{{display:block;overflow-x:auto;max-width:100%}}</style></head><body>",
             "<h1>BOX — 3-D spacing knob sweep (feature settings over one stored pair set)</h1>",
             (f"<div class=meta>built {s['built_at']} · pairs built once at gate {s['store']['gate_ft']:,.0f} ft (stick-to-stick), overlap ≥ {s['store']['min_overlap']:.0%}, "
              f"parent cum within {s['store']['parent_dz_ft']:,.0f} ft TVD — the proposed sql/59 storage settings · {s['meta']['n_subjects_with_geometry']:,} WCA wells, "
              f"{s['reach']['n_pairs_stored']:,} non-child pairs ({s['reach']['pairs_per_subject']:.1f} per well; {s['reach']['share_dmin_gt_2640']:.0%} beyond 2,640 ft, "
              f"{s['reach']['share_overlap_lt_0.30']:.0%} under 30 % overlap) · production through {s['asof']} · read-only</div>"),
             ("<div class=flag>dR² = gain in blocked 5-fold CV R² (3-mi blocks) from adding ln drainage cross-section, ln lateral spacing, ln(1 + parent cum per kft) "
              "[+ ellipse count] to area + year + ln lateral. absorbed = share of the within-area 2024-vs-2018 year effect removed by the same features (full sample). "
              "One knob moved at a time from the default; a best value at the edge of its range means the range (and the stored settings) should widen.</div>")]
    for y in RESPONSES:
        parts += [f"<h2>{y}</h2>", _table(t[t.response == y].drop(columns="response"),
                                          {"cv_r2_base": ".3f", "cv_r2_with": ".3f", "d_r2_pts": "+.2f", "yr2024_base": "+.1%", "yr2024_with": "+.1%", "absorbed": ".0%",
                                           "median_xsec_ft2": ",.0f", "median_lat_spacing_ft": ",.0f"})]
    parts.append("</body></html>")
    return "\n".join(parts)
