"""BOX step 7a report (D59 condition 2): why the frozen spec's oil spread failed at the 2023 holdout cutoff.

    python -m scripts.box_spread_diag_report [--runs runs/box7a] [--out docs/box/step7a-2026-10-14]

Reads the per-well holdout frames written by scripts.box_spread_diag (identity-checked against the scored record) and the
stored tuning / holdout cells. DB-free. Package error = sum actual / sum predicted - 1 (negative = forecast HIGH); spread =
scale-free P10-P90 band (D58) = band / (1 + bias).
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

from box import acceptance as ac
from box import hindcast as hc
from box.edge_gap_report import _CSS, _table

REC = "box_v2_wf"
B = 2000
SEED = 20261014


def sf(err: np.ndarray) -> float:
    s = hc.stats(err)
    return ac.scale_free(s["band"], s["bias"]) if s["n"] else float("nan")


def pkg_frame(v: pd.DataFrame, k: int, stream: str = "oil") -> pd.DataFrame:
    a = f"actual_{stream}{k}"
    box = ac.package_errors(v, "package", a, f"pred_{REC}_{stream}{k}").rename(columns={"err": "err_box", "p": "p_box"})
    ben = ac.package_errors(v, "package", a, f"bench_{stream}{k}")[["package", "p", "err"]].rename(columns={"err": "err_bench", "p": "p_bench"})
    nwf = ac.package_errors(v, "package", a, f"pred_box_v2_{stream}{k}")[["package", "err"]].rename(columns={"err": "err_box_nowf"})
    ok = v[np.isfinite(v[a].astype(float))]
    att = ok.groupby("package").agg(
        operator=("operator", lambda s: s.mode().iat[0] if len(s.mode()) else ""), n_operators=("operator", "nunique"),
        state=("state_code", lambda s: "/".join(sorted(set(map(str, s))))), county=("county", lambda s: s.mode().iat[0] if len(s.mode()) else ""),
        lateral_ft=("lateral_ft", "mean"), tvd_ft=("tvd_ft", "median"), fp=("first_production_date", "min"),
        v2_mode=("v2_mode", lambda s: "strike" if (s == "strike").any() else "circle"), v2_radius_mi=("v2_radius_mi", "max"),
        v2_n_min=("v2_n", "min"), short=("v2_short", "any"), uturn=("v2_uturn", "any"), infill_share=("infill", "mean"),
        lat_spacing_ft=("lat_spacing_ft", "median"), mid_lon=("mid_lon", "mean"), mid_lat=("mid_lat", "mean"),
        wells=("api10", lambda s: ";".join(s)), names=("well_name", lambda s: "; ".join(map(str, s))[:160]))
    return box.merge(ben, on="package").merge(nwf, on="package", how="left").merge(att, left_on="package", right_index=True)


def influence(p: pd.DataFrame) -> pd.DataFrame:
    """Leave-one-package-out change in each spread and in the gap (BOX - benchmark); + = the package widens BOX vs bench."""
    p = p.drop(columns=["d_box", "d_bench", "d_gap"], errors="ignore").reset_index(drop=True)
    full_b, full_r = sf(p["err_box"].to_numpy()), sf(p["err_bench"].to_numpy())
    rows = []
    for i in range(len(p)):
        m = np.ones(len(p), bool)
        m[i] = False
        b, r = sf(p["err_box"].to_numpy()[m]), sf(p["err_bench"].to_numpy()[m])
        rows.append({"package": p["package"].iat[i], "d_box": full_b - b, "d_bench": full_r - r, "d_gap": (full_b - full_r) - (b - r)})
    return p.merge(pd.DataFrame(rows), on="package").sort_values("d_gap", ascending=False)


def trimmed_gap(p: pd.DataFrame, m_max: int = 6) -> pd.DataFrame:
    """Gap after removing the m most gap-widening packages (greedy, recomputed each step)."""
    q, rows = p.copy(), []
    for m in range(m_max + 1):
        rows.append({"removed": m, "n": len(q), "box_sf": sf(q["err_box"].to_numpy()), "bench_sf": sf(q["err_bench"].to_numpy())})
        if m < m_max:
            q = q[q["package"] != influence(q)["package"].iat[0]]
    t = pd.DataFrame(rows)
    t["gap"] = t["box_sf"] - t["bench_sf"]
    t["verdict"] = np.where(t["gap"] <= ac.BAND_TOL, "PASS", "FAIL")
    return t


def bootstrap_gap(p: pd.DataFrame, rng: np.random.Generator) -> dict[str, float]:
    eb, er = p["err_box"].to_numpy(), p["err_bench"].to_numpy()
    g = np.array([sf(eb[j]) - sf(er[j]) for j in (rng.integers(0, len(p), len(p)) for _ in range(B))])
    return {"gap": sf(eb) - sf(er), "gap_p05": float(np.percentile(g, 5)), "gap_p95": float(np.percentile(g, 95)), "p_gap_gt_tol": float((g > ac.BAND_TOL).mean())}


def breakdown(p: pd.DataFrame, by: str) -> pd.DataFrame:
    rows = []
    for g, x in p.groupby(by, dropna=False):
        rows.append({by: g, "packages": len(x), "wells": int(x["n"].sum()), "box_bias": x["err_box"].mean(), "box_sd": x["err_box"].std(),
                     "bench_bias": x["err_bench"].mean(), "bench_sd": x["err_bench"].std(),
                     "box_tail_share": float(x["tail"].mean())})
    return pd.DataFrame(rows).sort_values("packages", ascending=False)


def scatter_svg(p: pd.DataFrame, title: str) -> str:
    """Package error BOX (y) vs benchmark (x); dot area ~ wells; tails ringed."""
    W, H, pad = 420, 420, 44
    lo, hi = -0.8, 1.6

    def X(e: float) -> float:
        return pad + (min(max(e, lo), hi) - lo) / (hi - lo) * (W - 2 * pad)

    def Y(e: float) -> float:
        return H - pad - (min(max(e, lo), hi) - lo) / (hi - lo) * (H - 2 * pad)

    out = [f"<svg viewBox='0 0 {W} {H}' width='100%' style='max-width:{W}px' role=img aria-label='{title}'>",
           f"<line x1={X(lo)} y1={Y(lo)} x2={X(hi)} y2={Y(hi)} stroke='currentColor' stroke-opacity=.25 />",
           f"<line x1={X(0)} y1={Y(lo)} x2={X(0)} y2={Y(hi)} stroke='currentColor' stroke-opacity=.15 /><line x1={X(lo)} y1={Y(0)} x2={X(hi)} y2={Y(0)} stroke='currentColor' stroke-opacity=.15 />"]
    for t in (-0.5, 0, 0.5, 1.0, 1.5):
        out.append(f"<text x={X(t)} y={H - pad + 16} font-size=10 text-anchor=middle fill='currentColor'>{t:+.0%}</text>")
        out.append(f"<text x={pad - 6} y={Y(t) + 3} font-size=10 text-anchor=end fill='currentColor'>{t:+.0%}</text>")
    for r in p.itertuples():
        col = "#c0392b" if r.v2_mode == "strike" else "#2c6fbb"
        ring = " stroke='currentColor' stroke-width=1.5" if r.tail else ""
        out.append(f"<circle cx={X(r.err_bench):.1f} cy={Y(r.err_box):.1f} r={2.5 + 1.5 * np.sqrt(r.n):.1f} fill='{col}' fill-opacity=.55{ring}>"
                   f"<title>{r.package} · {r.operator} · {r.n} wells · BOX {r.err_box:+.0%} · bench {r.err_bench:+.0%}</title></circle>")
    out.append(f"<text x={W / 2} y={H - 6} font-size=11 text-anchor=middle fill='currentColor'>benchmark package error (actual / forecast − 1)</text>")
    out.append(f"<text x=12 y={H / 2} font-size=11 text-anchor=middle fill='currentColor' transform='rotate(-90 12 {H / 2})'>BOX box_v2_wf package error</text>")
    out.append("</svg>")
    return "".join(out)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--runs", type=Path, default=Path("runs") / "box7a")
    ap.add_argument("--out", type=Path, default=Path("docs") / "box" / "step7a-2026-10-14")
    a = ap.parse_args(argv)
    a.out.mkdir(parents=True, exist_ok=True)
    rng = np.random.default_rng(SEED)
    views = {f.stem.split("_")[1].split(".")[0]: pd.read_csv(f, dtype={"api10": str, "package": str}) for f in sorted(a.runs.glob("view_*.csv.gz"))}
    metas = {k: json.loads((a.runs / f"meta_{k}.json").read_text(encoding="utf-8")) for k in views}
    summ: dict[str, object] = {"identity": {k: m["identity_max_abs_diff"] for k, m in metas.items()}, "actuals_through": {k: m["actuals_through"] for k, m in metas.items()}}
    boot, html_parts, pk_all = [], [], []
    for yr, v in sorted(views.items()):
        for k in (12, 24):
            if f"actual_oil{k}" not in v:
                continue
            p = pkg_frame(v, k)
            if len(p) < ac.MIN_PACKAGES:
                continue
            hi, lo = np.percentile(p["err_box"], [90, 10])
            p["tail"] = (p["err_box"] >= hi) | (p["err_box"] <= lo)
            p = influence(p)
            pk_all.append(p.assign(cutoff=yr, horizon=k))
            boot.append({"cutoff": yr, "horizon": k, "packages": len(p), "box_sf": sf(p["err_box"].to_numpy()), "bench_sf": sf(p["err_bench"].to_numpy()), **bootstrap_gap(p, rng)})
    pk = pd.concat(pk_all, ignore_index=True)
    bt = pd.DataFrame(boot)
    pk.to_csv(a.out / "packages_oil_holdout.csv", index=False)
    bt.to_csv(a.out / "spread_bootstrap.csv", index=False)
    summ["bootstrap"] = bt.to_dict("records")
    # Workup lesson (D59 condition 2): spread by analog radius reached, every judged holdout cell pooled
    pk["radius_class"] = np.where(pk["v2_radius_mi"] > 5, "past 5 mi", "5 mi ring")
    rad = []
    for (k, rc), x in pk.groupby(["horizon", "radius_class"]):
        rad.append({"horizon": k, "radius_class": rc, "packages": len(x), "box_bias": x["err_box"].mean(), "box_sf": sf(x["err_box"].to_numpy()),
                    "bench_sf": sf(x["err_bench"].to_numpy()), "box_p90_low": float(np.percentile(x["err_box"], 10)), "box_p10_high": float(np.percentile(x["err_box"], 90))})
    rad_t = pd.DataFrame(rad)
    rad_t.to_csv(a.out / "spread_by_radius.csv", index=False)
    summ["by_radius"] = rad_t.to_dict("records")
    pk["nm"] = np.where(pk["state"].astype(str).str.contains("30"), "NM", "TX")
    st = []
    for keys, x in [*pk.groupby(["cutoff", "horizon", "nm"]), *((("pooled", k, s), x) for (k, s), x in pk.groupby(["horizon", "nm"]))]:
        st.append({"cutoff": keys[0], "horizon": keys[1], "state": keys[2], "packages": len(x), "box_sf": sf(x["err_box"].to_numpy()), "bench_sf": sf(x["err_bench"].to_numpy())})
    st_t = pd.DataFrame(st)
    st_t.to_csv(a.out / "spread_by_state.csv", index=False)
    summ["by_state"] = st_t.to_dict("records")
    html_parts += ["<h2>NM vs TX scale-free spread by cell (watch item, §2d)</h2>", _table(st_t, {"box_sf": ".3f", "bench_sf": ".3f"})]
    corr = pk.groupby(["cutoff", "horizon"]).apply(lambda x: x["err_box"].corr(x["err_bench"]), include_groups=False)
    summ["corr_box_bench"] = {f"{c}_{k}": float(v_) for (c, k), v_ in corr.items()}
    html_parts += ["<h2>Workup lesson: spread by analog radius reached (all judged holdout cells pooled)</h2>",
                   _table(rad_t, {"box_bias": "+.1%", "box_sf": ".3f", "bench_sf": ".3f", "box_p90_low": "+.0%", "box_p10_high": "+.0%"}),
                   ("<div class=meta>P90 (low) / P10 (high) = the 10th / 90th percentile of package actual / forecast − 1. "
                    f"Package error correlation BOX vs benchmark per cell: {', '.join(f'{k} {v_:.2f}' for k, v_ in summ['corr_box_bench'].items())}.</div>")]
    for yr, k in (("2023", 12), ("2023", 24)):
        p = pk[(pk.cutoff == yr) & (pk.horizon == k)].drop(columns=["cutoff", "horizon"])
        if p.empty:
            continue
        tg = trimmed_gap(p)
        summ[f"trim_{yr}_{k}"] = tg.to_dict("records")
        top = p.head(8)[["package", "n", "operator", "state", "county", "lateral_ft", "v2_mode", "v2_radius_mi", "v2_n_min", "short", "uturn",
                         "err_box", "err_box_nowf", "err_bench", "d_gap", "names"]]
        cols = {"err_box": "+.0%", "err_box_nowf": "+.0%", "err_bench": "+.0%", "d_gap": "+.3f", "lateral_ft": ",.0f", "v2_radius_mi": ".0f"}
        html_parts += [f"<h2>Oil cum-{k}, 2023 cutoff — {len(p)} held-out packages</h2>", scatter_svg(p, f"2023 cum-{k}"),
                       ("<div class=meta>Blue = circular search; red = D55 strike ellipse; ringed = BOX tail package (outside its own P10–P90). "
                        "Off the diagonal = BOX and the benchmark disagree on that package.</div>"),
                       "<h3>Packages that widen BOX's spread most vs the benchmark (leave-one-out)</h3>", _table(top, cols),
                       "<h3>Gap after removing the m most gap-widening packages</h3>", _table(tg, {"box_sf": ".3f", "bench_sf": ".3f", "gap": "+.3f"})]
        p = p.assign(radius_class=np.where(p["v2_radius_mi"] > 5, "past 5 mi", "5 mi ring"),
                     size_class=pd.cut(p["n"], [0, 1, 3, 6, np.inf], labels=["1", "2-3", "4-6", "7+"]).astype(str))
        for by in ("v2_mode", "radius_class", "size_class", "state", "short", "uturn"):
            html_parts += [f"<h3>By {by}</h3>", _table(breakdown(p, by), {"box_bias": "+.1%", "box_sd": ".2f", "bench_bias": "+.1%", "bench_sd": ".2f", "box_tail_share": ".0%"})]
    page = "\n".join([
        "<!doctype html><html><head><meta charset=utf-8><meta name=viewport content='width=device-width,initial-scale=1'><title>BOX 2023 spread</title>",
        f"<style>{_CSS} body{{overflow-x:hidden}} table{{display:block;overflow-x:auto;max-width:100%}}</style></head><body>",
        "<h1>BOX step 7a — the 2023-cutoff oil spread misses (D59 condition 2)</h1>",
        (f"<div class=meta>Frozen spec box_v2_wf (code d5c3ebd) re-run per cutoff on the D52 holdout; recomputed cells identical to the scored record "
         f"(max |diff| {json.dumps(summ['identity'])}). Read-only. Package error = Σ actual / Σ forecast − 1 (negative = forecast HIGH); "
         "spread = scale-free P10–P90 (D58).</div>"),
        "<h2>Is 2023 outside the noise? Package bootstrap of the spread gap (BOX − benchmark), every judged holdout cell</h2>",
        _table(bt, {"box_sf": ".3f", "bench_sf": ".3f", "gap": "+.3f", "gap_p05": "+.3f", "gap_p95": "+.3f", "p_gap_gt_tol": ".0%"}),
        *html_parts, "</body></html>"])
    (a.out / "spread.html").write_text(page, encoding="utf-8")
    (a.out / "summary.json").write_text(json.dumps(summ, indent=2, default=str), encoding="utf-8")
    print(bt.round(3).to_string(index=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
