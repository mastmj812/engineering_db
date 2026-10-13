"""BOX acceptance of record (D53, Michael 2026-10-13) — package-level, Novi-agnostic, against a local-offsets benchmark,
with the D52 spatial holdout kept out of every tuning view.

Folds: rolling-origin cutoffs Dec 1 2019 … 2024 (box/backtest_report.run_fold: rebuild areas, curves, factors, F(k) from
wells first-producing before the cutoff, production through the month before it; score the next 12 months' gate-1 WCA wells).
Horizons cum-12 / 24 / 36 / 48 (cum-48 only where the data reach it — the 2019 / 2020 folds — to see whether the drift
compounds into EUR).

Grain = development PACKAGE: scored WCA wells linked as co-developed co-extent neighbours (first production within 180 d,
overlap >= 30 % — rule 9 / sql/47) on the 3-D spacing pairs (box/spacing3d; = curated.well_neighbors, sql/59), as
connected components; a lone well is a package of one. Package error = sum actual / sum predicted - 1 over its members that
reached the horizon. Bias = mean over packages; band = P10 - P90 over packages (P10 = high).

Benchmark = an engineer's quick look (backtest_report.local_offsets): median per-1,000-ft cum-k of the 15 nearest pre-cutoff
cohort wells whose cum-k was known at the cutoff, x lateral. Novi stays an exhibit (step-6 hindcast).

Verdict (D53): for the BOX model of record, each (fold, stream, horizon) cell with >= MIN_PACKAGES packages passes when
|package bias| <= 10 % AND BOX's package band <= the benchmark's + 0.05 (amendment 2026-10-13); BOX passes when every judged cell passes, oil AND gas.

Holdout (D52): a package is HELD OUT when any member's lateral midpoint lies in a holdout block (box/holdout). Held-out
packages are dropped BEFORE any statistic is computed and nothing about their errors is written; only their counts are.
`score_holdout=True` is the one-time final scoring after the model spec is frozen.
"""

from __future__ import annotations

import datetime as dt
import json
from collections.abc import Iterable, Mapping, Sequence
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from box import backtest_report as br
from box import edge_gap_report as egr
from box import exclusions
from box import hindcast as hc
from box import spacing3d as s3
from box import spacing3d_report as s3r
from box import tc_curve_report as rep
from box.edge_gap_report import _CSS, _table

CUTOFFS: tuple[dt.date, ...] = tuple(dt.date(y, 12, 1) for y in range(2019, 2025))
HORIZONS: tuple[int, ...] = (12, 24, 36, 48)
K_MONTHS = 48
STREAMS = ("oil", "gas")
RECORD = "lat"  # BOX model of record after D50 (Cui lateral efficiency)
REPORTED = ("base", "lat", "lat+s3d")
BIAS_TOL = 0.10
BAND_TOL = 0.05  # D53 amendment (Michael 2026-10-13): BOX band may exceed the benchmark's by this much (sampling noise)
MIN_PACKAGES = 30
PACKAGE_OVERLAP = 0.30
PACKAGE_CODEV_DAYS = s3.CODEV_DAYS


# ----------------------------------------------------------------------------
# Pure pieces
# ----------------------------------------------------------------------------


def packages(ids: Sequence[str], pairs: Mapping[str, Iterable[s3.Pair]], min_overlap: float = PACKAGE_OVERLAP, codev_days: int = PACKAGE_CODEV_DAYS) -> dict[str, str]:
    """api10 -> package id (the smallest api10 in its connected component). Edges = co-developed (|dfp| <= codev_days)
    co-extent pairs (overlap >= min_overlap in EITHER direction) between two wells of `ids`."""
    idset = set(ids)
    parent = {a: a for a in ids}

    def find(a: str) -> str:
        while parent[a] != a:
            parent[a] = parent[parent[a]]
            a = parent[a]
        return a

    for a in ids:
        for p in pairs.get(a, ()):
            if p.nbr in idset and abs(p.dfp_days) <= codev_days and p.overlap >= min_overlap:
                ra, rb = find(a), find(p.nbr)
                if ra != rb:
                    parent[max(ra, rb)] = min(ra, rb)
    return {a: find(a) for a in ids}


def package_errors(df: pd.DataFrame, pkg: str, actual: str, pred: str) -> pd.DataFrame:
    """Per package: members with both values, sum actual / sum predicted - 1."""
    ok = np.isfinite(df[actual].astype(float)) & np.isfinite(df[pred].astype(float)) & (df[pred].astype(float) > 0)
    g = df[ok].groupby(pkg).agg(n=(actual, "size"), a=(actual, "sum"), p=(pred, "sum"))
    g["err"] = g["a"] / g["p"] - 1.0
    return g.reset_index()


def judge_cell(box: Mapping[str, float], bench: Mapping[str, float], n_pkg: int, tol: float = BIAS_TOL, min_pkg: int = MIN_PACKAGES,
               band_tol: float = BAND_TOL) -> str:
    if n_pkg < min_pkg or not np.isfinite(box["bias"]):
        return "not judged"
    ok = abs(box["bias"]) <= tol and (not np.isfinite(bench["band"]) or box["band"] <= bench["band"] + band_tol)
    return "PASS" if ok else "FAIL"


def verdict(cells: pd.DataFrame) -> dict[str, Any]:
    """Overall: every judged cell of the record model passes, oil AND gas."""
    rec = cells[cells["variant"] == RECORD]
    judged = rec[rec["verdict"] != "not judged"]
    by_stream = {s: ("PASS" if (judged[judged.stream == s]["verdict"] == "PASS").all() and (judged.stream == s).any() else "FAIL") for s in STREAMS}
    overall = "PASS" if all(v == "PASS" for v in by_stream.values()) else "FAIL"
    return {"overall": overall, "by_stream": by_stream, "n_judged": len(judged), "n_failed": int((judged["verdict"] == "FAIL").sum())}


# ----------------------------------------------------------------------------
# Run
# ----------------------------------------------------------------------------


def score_fold(hs: pd.DataFrame, cutoff: str) -> pd.DataFrame:
    rows = []
    for s in STREAMS:
        for k in HORIZONS:
            if f"actual_{s}{k}" not in hs:
                continue
            bp = package_errors(hs, "package", f"actual_{s}{k}", f"bench_{s}{k}")
            bstat = hc.stats(bp["err"])
            for v in REPORTED:
                pp = package_errors(hs, "package", f"actual_{s}{k}", f"pred_{v}_{s}{k}")
                st = hc.stats(pp["err"])
                wst = hc.stats(hs[f"{v}_err_{s}{k}"])
                rows.append({"cutoff": cutoff, "stream": s, "horizon": k, "variant": v, "n_packages": st["n"], "n_wells": int(pp["n"].sum()),
                             "pkg_bias": st["bias"], "pkg_median": st["median"], "pkg_band": st["band"],
                             "bench_bias": bstat["bias"], "bench_band": bstat["band"], "well_bias": wst["bias"], "well_band": wst["band"],
                             "verdict": judge_cell({"bias": st["bias"], "band": st["band"]}, {"band": bstat["band"]}, st["n"])})
    return pd.DataFrame(rows)


def run(conn: Any, wells_dir: Path, out: Path, engine_sha: str, workers: int | None = None, cutoffs: tuple[dt.date, ...] = CUTOFFS,
        score_holdout: bool = False) -> dict[str, Any]:
    out.mkdir(parents=True, exist_ok=True)
    wells, excluded = exclusions.drop(egr.load_final_sets(wells_dir, ("WCA",)))
    last = rep.last_full_month(rep._read(conn, rep._MONTHS_SQL))
    subj = wells[np.array([f >= dt.date(2016, 1, 1) for f in wells["first_production_date"]]) & (pd.to_numeric(wells["lateral_length_ft"], errors="coerce") > 0).to_numpy()]
    P = s3r.build_pairs(conn, subj.reset_index(drop=True))
    cells, fold_meta = [], []
    for c in cutoffs:
        f = br.run_fold(conn, wells, wells_dir, c, workers, last, P, horizons=HORIZONS, k_months=K_MONTHS, keep_pred=True)
        hs = f["hold"]
        hs["package"] = hs["api10"].map(packages(list(hs["api10"]), P["pairs"]))
        held = set(hs.loc[hs["holdout_block"], "package"])
        hs["package_held_out"] = hs["package"].isin(held)
        view = hs[hs["package_held_out"] == score_holdout].copy()  # tuning view excludes held-out packages entirely
        cells.append(score_fold(view, str(c)))
        sizes = hs.drop_duplicates("package")["package"].map(hs["package"].value_counts())
        fold_meta.append({"cutoff": str(c), "asof": str(f["asof"]), "k_areas": f["k_areas"], "n_train": f["n_train"], "n_scored_wells": len(hs),
                          "n_packages": int(hs["package"].nunique()), "median_package_wells": float(sizes.median()), "max_package_wells": int(sizes.max()),
                          "n_packages_held_out": len(held), "n_wells_held_out": int(hs["package_held_out"].sum()),
                          "n_factor_no_estimate": int(hs["factor_no_estimate"].sum()) if "factor_no_estimate" in hs else 0,
                          "F_oil_12_36": [f["F"][RECORD]["oil"][11], f["F"][RECORD]["oil"][35]]})
    cells = pd.concat(cells, ignore_index=True)
    v = verdict(cells)
    built = dt.datetime.now(tz=dt.UTC).astimezone().isoformat(timespec="seconds")
    summ = {"built_at": built, "engine_sha": engine_sha, "actuals_through": str(last), "view": "HOLDOUT (final scoring)" if score_holdout else "tuning (holdout excluded)",
            "record_variant": RECORD, "bias_tol": BIAS_TOL, "min_packages": MIN_PACKAGES, "folds": fold_meta, "verdict": v, "n_excluded": len(excluded)}
    tag = "holdout" if score_holdout else "tuning"
    (out / f"acceptance_{tag}.html").write_text(render(summ, cells), encoding="utf-8")
    cells.to_csv(out / f"cells_{tag}.csv", index=False)
    (out / f"summary_{tag}.json").write_text(json.dumps(rep._clean(summ), indent=2, default=rep._json), encoding="utf-8")
    return {"summary": summ, "cells": cells}


def render(s: dict[str, Any], cells: pd.DataFrame) -> str:
    v = s["verdict"]
    cls = "ok" if v["overall"] == "PASS" else "bad"
    piv = cells.pivot_table(index=["stream", "horizon", "cutoff"], columns="variant", values="pkg_bias").reindex(columns=list(REPORTED))
    bench = cells[cells.variant == RECORD].set_index(["stream", "horizon", "cutoff"])
    tab = piv.join(bench[["n_packages", "n_wells", "pkg_band", "bench_bias", "bench_band", "verdict"]]).reset_index()
    tab = tab.rename(columns={v_: f"{v_} pkg bias" for v_ in REPORTED} | {"pkg_band": f"{RECORD} pkg band"})
    folds = pd.DataFrame(s["folds"])
    pct = {f"{v_} pkg bias": "+.1%" for v_ in REPORTED} | {"bench_bias": "+.1%", f"{RECORD} pkg band": ".2f", "bench_band": ".2f"}
    return "\n".join([
        "<!doctype html><html><head><meta charset=utf-8><meta name=viewport content='width=device-width,initial-scale=1'><title>BOX acceptance (D53)</title>",
        f"<style>{_CSS} body{{overflow-x:hidden}} table{{display:block;overflow-x:auto;max-width:100%}}</style></head><body>",
        f"<h1>BOX acceptance of record (D53) — {s['view']}</h1>",
        (f"<div class=meta>built {s['built_at']} · Delaware WCA · rolling-origin folds (cutoff Dec 1; rebuilt from pre-cutoff data; next 12 months' wells scored) · "
         f"actuals curated.production through {s['actuals_through']} (each well's newest month dropped) · blueox-boxfit @ {s['engine_sha'][:7]} · read-only</div>"),
        (f"<div class='flag {cls}'><b>Verdict ({s['view']}): {v['overall']}</b> — oil {v['by_stream']['oil']}, gas {v['by_stream']['gas']}; "
         f"{v['n_failed']} of {v['n_judged']} judged cells fail. A cell (fold × stream × horizon) is judged when it has ≥ {s['min_packages']} packages and passes when "
         f"|package bias| ≤ {s['bias_tol']:.0%} AND the {RECORD} package band ≤ the local-offsets benchmark's + {BAND_TOL:.2f} (D53 amendment). Record model = <b>{RECORD}</b> (D50).</div>"),
        ("<div class=meta>Package = co-developed co-extent WCA wells (first production within 180 d, overlap ≥ 30 %), connected components; error = Σ actual / Σ predicted − 1 "
         "(negative = forecast HIGH). Benchmark = median per-1,000-ft cum-k of the 15 nearest pre-cutoff cohort wells whose cum-k was known at the cutoff × lateral. "
         "Held-out packages (any member in a D52 holdout block) are excluded before any statistic is computed; only their counts appear below.</div>"),
        "<h2>1. Package bias and band by fold</h2>", _table(tab, pct),
        "<h2>2. Folds</h2>", _table(folds, {"median_package_wells": ".1f"}),
        "</body></html>"])


def regrade(cells: pd.DataFrame, band_tol: float = BAND_TOL) -> pd.DataFrame:
    """Re-judge stored cells under a band tolerance (no recomputation of any statistic)."""
    c = cells.copy()
    c["verdict"] = [judge_cell({"bias": b, "band": w}, {"band": bb}, int(n), band_tol=band_tol)
                    for b, w, bb, n in zip(c["pkg_bias"], c["pkg_band"], c["bench_band"], c["n_packages"], strict=True)]
    return c
