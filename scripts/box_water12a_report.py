"""BOX step 12a — water identity guard + one-time holdout verdict tables (DB-free; reads the runs, writes the deliverable).

    python -m scripts.box_water12a_report --runs runs/step12a --out docs/box/step12a-2026-10-19
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import pandas as pd

from box import acceptance as ac
from box import water11 as w
from box import water11_report as wr
from box import water12a as wa
from box.edge_gap_report import _CSS, _table
from scripts.box_water11_report import tuning_frame

STEP11 = Path("docs") / "box" / "step11-2026-10-19"


def _fmt(cols: list[str], f: str) -> dict[str, str]:
    return dict.fromkeys(cols, f)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--runs", type=Path, default=Path("runs") / "step12a")
    ap.add_argument("--tuning-inputs", type=Path, default=Path("runs") / "step11_inputs")
    ap.add_argument("--holdout-inputs", type=Path, default=Path("runs") / "step12a_inputs")
    ap.add_argument("--out", type=Path, default=Path("docs") / "box" / "step12a-2026-10-19")
    a = ap.parse_args(argv)
    out = a.out
    out.mkdir(parents=True, exist_ok=True)
    iv_path = STEP11 / "intervals_water.csv"
    if wa.sha256(iv_path) != wa.INTERVALS_SHA256:
        raise RuntimeError("intervals_water.csv differs from the frozen digest")
    intervals = pd.read_csv(iv_path)
    summ: dict = {"intervals_sha256": wa.INTERVALS_SHA256}
    # identity
    old = pd.read_csv(STEP11 / "cells_pooled.csv")
    t = tuning_frame(a.runs / "tuning", a.tuning_inputs)
    new = wr.cells(t, ("group",))
    new.to_csv(out / "cells_tuning_rescore.csv", index=False)
    idt = wa.identity(old, new)
    idt.to_csv(out / "identity.csv", index=False)
    summ["identity"] = {"cells": len(idt), "identical": int(idt["identical"].sum()), "max_abs_diff": float(idt["max_abs_diff"].max())}
    # holdout
    hold = None
    if any((a.runs / "holdout" / f"holdout_{g}.csv.gz").exists() for g in w.GROUPS):
        h = tuning_frame_side(a.runs / "holdout", a.holdout_inputs)
        hold = wa.holdout_cells(h, intervals)
        hold.to_csv(out / "holdout_cells.csv", index=False)
        summ["holdout_rows"] = len(h)
        summ["holdout_sources"] = h["source"].value_counts().to_dict()
        wr.cells(h, ("group", "state"), ("ratio",)).to_csv(out / "holdout_cells_by_state.csv", index=False)
        wr.cells(h, ("group", "cutoff"), ("ratio",)).to_csv(out / "holdout_cells_per_cutoff.csv", index=False)
        # D105-style disclosure lines: tuning / holdout / tuning + holdout pooled (packages keyed by side so none merge across sides)
        both = pd.concat([t.assign(package="t" + t["package"].astype(str)), h.assign(package="h" + h["package"].astype(str))], ignore_index=True)
        pooled = wr.cells(both, ("group",), ("ratio",)).set_index(["group", "horizon"])
        tun = new[new["method"] == "ratio"].set_index(["group", "horizon"])
        ho = hold.set_index(["group", "horizon"])
        disc = pd.DataFrame({"tuning_bias": tun["pkg_bias"], "tuning_packages": tun["pkg_n_packages"],
                             "holdout_bias": ho["holdout_bias"], "holdout_packages": ho["packages"],
                             "pooled_bias": pooled["pkg_bias"], "pooled_packages": pooled["pkg_n_packages"]}).reset_index()
        disc.to_csv(out / "disclosure_water.csv", index=False)
    tiers = pd.DataFrame([wa.tier(g, not ac.BENCH_SPECS[g].get("provisional", False), old, hold if (hold is not None and g in set(hold["group"])) else None)
                          for g in w.GROUPS])
    tiers.to_csv(out / "water_tiers.csv", index=False)
    summ["tiers"] = tiers.set_index("group")["water_tier"].to_dict()
    (out / "summary.json").write_text(json.dumps(summ, indent=2, default=float), encoding="utf-8")
    (out / "index.html").write_text(render(idt, hold, tiers, summ), encoding="utf-8")
    print(json.dumps(summ, indent=2, default=float))
    return 0


def tuning_frame_side(runs: Path, inputs: Path) -> pd.DataFrame:
    """tuning_frame for the holdout files (holdout_<g>.csv.gz + the holdout views' coordinates)."""
    import glob

    import numpy as np

    from box.dev_factor_report import _xy

    frames = []
    for g in w.GROUPS:
        p = runs / f"holdout_{g}.csv.gz"
        if not p.exists():
            continue
        t = pd.read_csv(p, dtype={"api10": str, "package": str, "state_code": str})
        tag = w.HOLDOUT_TAG[g]
        v = pd.concat([pd.read_csv(f, dtype={"api10": str}, usecols=["api10", "cutoff", "mid_lon", "mid_lat"])
                       for f in sorted(glob.glob(str(inputs / g / f"view_{tag}_20*.csv.gz")))], ignore_index=True)
        v["cutoff"] = v["cutoff"].astype(str)
        t = t.merge(v, on=["api10", "cutoff"], how="left")
        t["x"], t["y"] = _xy(t["mid_lon"], t["mid_lat"])
        frames.append(t)
    t = pd.concat(frames, ignore_index=True)
    t["state"] = np.where(t["state_code"].astype(str).str.startswith("30"), "NM", "TX")
    return t


def render(idt: pd.DataFrame, hold: pd.DataFrame | None, tiers: pd.DataFrame, summ: dict) -> str:
    i = summ["identity"]
    parts = [
        "<!doctype html><html><head><meta charset=utf-8><meta name=viewport content='width=device-width,initial-scale=1'><title>BOX water step 12a</title>",
        f"<style>{_CSS} body{{overflow-x:hidden}} table{{display:block;overflow-x:auto;max-width:100%}}</style></head><body>",
        "<h1>BOX step 12a — water: identity guard + one-time holdout score</h1>",
        ("<div class=meta>Rule D109 (frozen at gate 11), method D107 ratio on raw box_v2 oil (D108) · intervals_water.csv sha256 "
        f"{summ['intervals_sha256'][:12]}… · production through 2026-07-01 · error = actual / forecast − 1 · full text: FINDINGS.md</div>"),
        (f"<div class='flag {'ok' if i['identical'] == i['cells'] else 'bad'}'><b>Tuning identity:</b> {i['identical']} / {i['cells']} pooled ratio cells "
        f"reproduce step 11 within 1e-9 (max |diff| {i['max_abs_diff']:.2e}).</div>"),
        "<h2>1. Water tier per group (D109)</h2>", _table(tiers),
    ]
    if hold is not None:
        parts += ["<h2>2. Holdout cells (ratio, pooled, scored once)</h2>",
                  _table(hold, _fmt(["holdout_bias", "interval_lo", "interval_hi", "bench_bias"], "+.1%") | _fmt(["band_sf", "bench_band_sf"], ".2f"))]
    disc_path = Path("docs") / "box" / "step12a-2026-10-19" / "disclosure_water.csv"
    if disc_path.exists():
        d = pd.read_csv(disc_path)
        parts += ["<h2>3. Disclosure lines (D105 pattern: tuning / holdout / pooled, never the pooled figure alone)</h2>",
                  _table(d, _fmt(["tuning_bias", "holdout_bias", "pooled_bias"], "+.1%"))]
    parts += ["<h2>4. Identity detail</h2>", _table(idt, {"max_abs_diff": ".2e"}), "</body></html>"]
    return "\n".join(parts)


if __name__ == "__main__":
    sys.exit(main())
