"""BOX step 11 — build the deliverable tables from the runs (DB-free).

    python -m scripts.box_water11_report --runs runs/step11 --inputs runs/step11_inputs --out docs/box/step11-2026-10-19
"""

from __future__ import annotations

import argparse
import glob
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

from box import water11 as w
from box import water11_report as wr
from box.dev_factor_report import _xy


def tuning_frame(runs: Path, inputs: Path) -> pd.DataFrame:
    frames = []
    for g in w.GROUPS:
        p = runs / f"tune_{g}.csv.gz"
        if not p.exists():
            continue
        t = pd.read_csv(p, dtype={"api10": str, "package": str, "state_code": str})
        tag = w.TUNING_TAG[g]
        v = pd.concat([pd.read_csv(f, dtype={"api10": str}, usecols=["api10", "cutoff", "mid_lon", "mid_lat"])
                       for f in sorted(glob.glob(str(inputs / g / f"view_{tag}_20*.csv.gz")))], ignore_index=True)
        v["cutoff"] = v["cutoff"].astype(str)
        t = t.merge(v, on=["api10", "cutoff"], how="left")
        t["x"], t["y"] = _xy(t["mid_lon"], t["mid_lat"])
        frames.append(t)
    t = pd.concat(frames, ignore_index=True)
    t["state"] = np.where(t["state_code"].astype(str).str.startswith("30"), "NM", "TX")
    return t


# WCA D62 / BS2_S D102 oil cum factors at 12 / 24 / 36 (the haircut their DELIVERED oil carries; plan §2)
HAIRCUT = {"WCA": {12: 0.943, 24: 0.929, 36: 0.916}, "BS2_S": {12: 0.891, 24: 0.873, 36: 0.832}}


def haircut_sensitivity(t: pd.DataFrame) -> pd.DataFrame:
    """Ratio water x the group's oil cum haircut factor (first order: ignores the WOR's own Np shift, which lowers it further)
    vs ratio water on the raw box_v2 oil it was scored on."""
    rows = []
    for g, f in HAIRCUT.items():
        d = t[t["group"] == g].copy()
        d["package"] = d["cutoff"].astype(str) + ":" + d["package"].astype(str)
        for k in w.HORIZONS:
            d[f"h_w{k}"] = d[f"ratio_w{k}"] * f[k]
            a, b = w.package_stats(d, f"actual_w{k}", f"ratio_w{k}"), w.package_stats(d, f"actual_w{k}", f"h_w{k}")
            rows.append({"group": g, "horizon": k, "oil_cum_factor": f[k], "n_packages": a["n_packages"],
                         "bias_on_raw_oil": a["bias"], "bias_on_haircut_oil": b["bias"]})
    return pd.DataFrame(rows)


def wide_cells(c: pd.DataFrame) -> pd.DataFrame:
    rows = []
    for (g, k), d in c.groupby(["group", "horizon"]):
        r = {"group": g, "cum": k, "packages": int(d["pkg_n_packages"].max())}
        for _, x in d.iterrows():
            r[f"{x.method} bias"] = x.pkg_bias
            r[f"{x.method} band_sf"] = x.pkg_band_sf
            r[f"{x.method}"] = x.verdict
        r["bench bias"], r["bench band_sf"] = d["bench_bias"].iloc[0], d["bench_band_sf"].iloc[0]
        rows.append(r)
    return pd.DataFrame(rows)


def _fmt(cols: list[str], f: str) -> dict[str, str]:
    return dict.fromkeys(cols, f)


def render(out: Path, summ: dict) -> str:
    from box.edge_gap_report import _CSS, _table

    rt = pd.read_csv(out / "reach_by_group_state.csv")
    pl = pd.read_csv(out / "pool_labels.csv")
    wc = wide_cells(pd.read_csv(out / "cells_pooled.csv"))
    al = pd.read_csv(out / "cells_all_groups.csv")[["horizon", "method", "pkg_n_packages", "pkg_bias", "pkg_median", "pkg_band_sf", "bench_bias", "bench_band_sf", "verdict"]]
    sb = pd.read_csv(out / "cells_by_state.csv")
    st = sb[sb.method.isin(["ratio", "arps"])].pivot_table(index=["group", "state", "horizon"], columns="method", values="pkg_bias").reset_index()
    st = st.merge(sb[sb.method == "ratio"][["group", "state", "horizon", "pkg_n_packages", "bench_bias"]], on=["group", "state", "horizon"])
    iv = pd.read_csv(out / "intervals_water.csv")
    pw = pd.read_csv(out / "intervals_power.csv").pivot_table(index=["group", "horizon"], columns="scale", values="pass_rate").reset_index()
    pw.columns = [f"pass @ x{c:.2f}" if isinstance(c, float) else c for c in pw.columns]
    iv = iv.merge(pw, on=["group", "horizon"]).drop(columns=["method"])
    jc = pd.read_csv(out / "judgeable_counts.csv")
    hs = pd.read_csv(out / "haircut_oil_sensitivity.csv")
    ch = summ.get("choice", {})
    cr, ca = ch.get("ratio", {}), ch.get("arps", {})
    rc = [c for c in rt.columns if c.endswith("mi") or "extension" in c]
    rc = [c for c in rc if not c.startswith(("median", "p90"))]
    return "\n".join([
        "<!doctype html><html><head><meta charset=utf-8><meta name=viewport content='width=device-width,initial-scale=1'><title>BOX water step 11</title>",
        f"<style>{_CSS} body{{overflow-x:hidden}} table{{display:block;overflow-x:auto;max-width:100%}}</style></head><body>",
        "<h1>BOX step 11 — water method + pre-registered acceptance (read-only)</h1>",
        ("<div class=meta>Record run 10, 13 groups, 50,963 covered + covered_provisional locations · production through 2026-07-01 · tuning packages only "
        "(D52 salt unchanged; no holdout water read) · pre-registration committed 51d589c before any score · error = actual / forecast − 1 "
        "(negative = forecast HIGH) · full text: FINDINGS.md</div>"),
        (f"<div class='flag ok'><b>Method (pre-registered §4 rule): {ch.get('chosen', '?')}</b> — ratio passes {cr.get('passed')} / {cr.get('judged')} judged cells, "
        f"median |bias| {cr.get('median_abs_bias', float('nan')):.1%}; arps {ca.get('passed')} / {ca.get('judged')}, median |bias| "
        f"{ca.get('median_abs_bias', float('nan')):.1%}. Arps passes more cells but is not less biased, so ratio stands.</div>"),
        "<h2>(a) Measured-water reach per location</h2>",
        ("<div class=meta>Share of locations whose measured-water cohort closes in each radius class (D54 ladder, then the 30 / 40 / 50 mi water extension); "
        "fallback = fewer than 3 measured analogs at 50 mi → calculated-water analogs, flagged. TX columns: share with any NM analog / mean NM share / NM majority.</div>"),
        _table(rt, _fmt([*rc, "thin_share", "fallback_share", "any_nm_analog_share", "mean_nm_analog_share", "majority_nm_share"], ".0%")
               | {"median_radius_mi": ".1f", "p90_radius_mi": ".1f", "median_analogs": ".0f"}),
        "<h3>Pool labels (first production ≥ 2016, as of 2026-07-01; NM amendment applied)</h3>", _table(pl, {"measured_share": ".0%"}),
        "<h2>(b) Method comparison — tuning packages, pooled across cutoffs</h2>",
        ("<div class=meta>Water cell test (pre-registered): judged at ≥ 30 packages; PASS when |package bias| ≤ 20 % AND scale-free band ≤ the measured "
        "benchmark's + 0.10. ratio_actoil = the WOR on the scored well's ACTUAL oil (diagnostic only).</div>"),
        _table(al, _fmt(["pkg_bias", "pkg_median", "bench_bias"], "+.1%") | _fmt(["pkg_band_sf", "bench_band_sf"], ".2f")),
        _table(wc, _fmt([c for c in wc.columns if c.endswith("bias")], "+.1%") | _fmt([c for c in wc.columns if c.endswith("band_sf")], ".2f")),
        "<h3>By state (reported, never judged)</h3>", _table(st, _fmt(["arps", "ratio", "bench_bias"], "+.1%")),
        "<h3>WCA / BS2_S: ratio on the raw box_v2 oil it was scored on vs on the haircut oil they deliver</h3>",
        _table(hs, _fmt(["bias_on_raw_oil", "bias_on_haircut_oil"], "+.1%") | {"oil_cum_factor": ".3f"}),
        "<h2>(c) Frozen gate-12a consistency intervals (ratio, tuning only) + power</h2>",
        ("<div class=meta>P2.5–P97.5 of the pooled package bias over 2,000 random 20 % draws of 3-mi blocks (seed 20261019), draws with ≥ 10 packages; "
        "pass @ xs = share of draws inside the interval when the forecast is s × as large (x1.00 = as good as tuning).</div>"),
        _table(iv, _fmt(["tuning_bias", "interval_lo", "interval_hi"], "+.1%") | {"share_draws_judged": ".0%", "draw_packages_p50": ".0f"}
               | _fmt([c for c in iv.columns if c.startswith("pass")], ".0%")),
        "<h3>Judgeable cells (counts only; holdout side = labels + months on production, no volumes)</h3>", _table(jc),
        "</body></html>"])


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--runs", type=Path, default=Path("runs") / "step11")
    ap.add_argument("--inputs", type=Path, default=Path("runs") / "step11_inputs")
    ap.add_argument("--out", type=Path, default=Path("docs") / "box" / "step11-2026-10-19")
    a = ap.parse_args(argv)
    out = a.out
    out.mkdir(parents=True, exist_ok=True)
    summ: dict = {}
    # (a)
    r = pd.read_csv(a.runs / "reach_locations.csv.gz")
    p = pd.read_csv(a.runs / "reach_pools.csv.gz", dtype={"api10": str, "state_code": str})
    rt = wr.reach_table(r)
    rt.to_csv(out / "reach_by_group_state.csv", index=False)
    wr.pool_table(p).to_csv(out / "pool_labels.csv", index=False)
    r.groupby(["group", "state", "source", "radius_mi"]).size().rename("locations").reset_index().to_csv(out / "reach_radius_counts.csv", index=False)
    summ["reach"] = {"locations": len(r), "by_source": r["source"].value_counts().to_dict(),
                     "radius_counts": {str(k): int(v) for k, v in r[r.source == "measured"]["radius_mi"].value_counts().sort_index().items()},
                     "tx_locations": int((r.state == "TX").sum()), "tx_with_nm_analog": int(((r.state == "TX") & (r.nm_share > 0)).sum()),
                     "tx_majority_nm": int(((r.state == "TX") & (r.nm_share > 0.5)).sum())}
    # (b)
    if any((a.runs / f"tune_{g}.csv.gz").exists() for g in w.GROUPS):
        t = tuning_frame(a.runs, a.inputs)
        c = wr.cells(t, ("group",))
        c.to_csv(out / "cells_pooled.csv", index=False)
        wr.cells(t, ("group", "cutoff")).to_csv(out / "cells_per_cutoff.csv", index=False)
        wr.cells(t, ("group", "state")).to_csv(out / "cells_by_state.csv", index=False)
        all_ = wr.cells(t.assign(all="all"), ("all",))
        all_.to_csv(out / "cells_all_groups.csv", index=False)
        ch = wr.choose_method(c)
        summ["choice"] = ch
        summ["tuning_rows"] = len(t)
        summ["tuning_sources"] = t["source"].value_counts().to_dict()
        # frozen intervals + power for the chosen method, per group
        iv, pw = [], []
        for g, d in t.groupby("group"):
            s = wr.package_sums(d, ch["chosen"])
            tab, rate = wr.consistency(s)
            iv.append(tab.assign(group=g, method=ch["chosen"]))
            pw.append(rate.assign(group=g, method=ch["chosen"]))
        pd.concat(iv, ignore_index=True).to_csv(out / "intervals_water.csv", index=False)
        pd.concat(pw, ignore_index=True).to_csv(out / "intervals_power.csv", index=False)
    # (c)
    if (a.runs / "counts.csv").exists():
        cn = pd.read_csv(a.runs / "counts.csv")
        wr.holdout_counts(cn).to_csv(out / "judgeable_counts.csv", index=False)
        haircut_sensitivity(t).to_csv(out / "haircut_oil_sensitivity.csv", index=False)
    (out / "summary.json").write_text(json.dumps(summ, indent=2, default=float), encoding="utf-8")
    (out / "index.html").write_text(render(out, summ), encoding="utf-8")
    print(json.dumps(summ, indent=2, default=float)[:3000])
    return 0


if __name__ == "__main__":
    sys.exit(main())
