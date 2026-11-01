"""BOX step 21b — the gate-21b review page (DB-free; reads the tables `score` / `pad` wrote).

    python -m scripts.box_step21b_render [--docs docs/box/step21b-2026-11-01]
"""

from __future__ import annotations

import argparse
import html
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

from box import step21 as st
from box.edge_gap_report import _table

CSS = """
:root{--surface:#fcfcfb;--ink:#0b0b0b;--ink2:#52514e;--muted:#898781;--grid:#e1e0d9;--s1:#2a78d6;--s2:#eb6834;--band:#d9d7cf;--bg:#ffffff}
@media (prefers-color-scheme: dark){:root:not([data-theme="light"]){--surface:#1a1a19;--ink:#f0efec;--ink2:#c3c2b7;--muted:#898781;--grid:#2c2c2a;--s1:#3987e5;--s2:#d95926;--band:#3a3a37;--bg:#111110}}
:root[data-theme="dark"]{--surface:#1a1a19;--ink:#f0efec;--ink2:#c3c2b7;--muted:#898781;--grid:#2c2c2a;--s1:#3987e5;--s2:#d95926;--band:#3a3a37;--bg:#111110}
body{background:var(--bg);color:var(--ink);font:14px/1.45 system-ui,-apple-system,Segoe UI,sans-serif;margin:0 auto;max-width:1280px;padding:16px;overflow-x:hidden}
h1{font-size:22px}h2{font-size:18px;margin-top:28px;border-bottom:1px solid var(--grid)}h3{font-size:15px}
table{border-collapse:collapse;display:block;overflow-x:auto;max-width:100%;font-size:12.5px;margin:6px 0 12px}
th,td{border:1px solid var(--grid);padding:3px 6px;text-align:right;white-space:nowrap}th{background:var(--surface);color:var(--ink2)}
td:first-child,th:first-child{text-align:left}.meta{color:var(--ink2);font-size:12.5px;margin:4px 0 8px}
.flag{border-left:4px solid var(--s2);padding:6px 10px;background:var(--surface);margin:8px 0}
.toc a{margin-right:10px}svg text{fill:var(--ink2);font-size:11px}.viz{background:var(--surface);border-radius:6px;padding:8px;margin:8px 0;overflow-x:auto}
.legend span{display:inline-block;margin-right:14px;color:var(--ink2);font-size:12px}.legend i{display:inline-block;width:10px;height:10px;border-radius:50%;margin-right:4px;vertical-align:-1px}
"""


def _fmt(df: pd.DataFrame) -> dict[str, str]:
    f: dict[str, str] = {}
    for c in df.columns:
        lc = str(c).lower()
        if any(x in lc for x in ("bias", "interval", "share", "pass_rate", "catches", "passes")):
            f[c] = "+.1%" if "bias" in lc or "interval" in lc else ".0%"
        elif "band" in lc or lc in ("factor", "factor_interim", "factor_midland", "factor_gap", "factor_de") or "g48" in lc:
            f[c] = ".3f"
        elif "kft" in lc or lc.endswith("_ft") or "radius" in lc:
            f[c] = ",.0f" if "kft" in lc or lc.endswith("_ft") else ".1f"
    return f


def t(df: pd.DataFrame) -> str:
    return _table(df, _fmt(df)) if len(df) else "<p class=meta>(none)</p>"


def dot_plot(pooled: pd.DataFrame, frozen: pd.DataFrame, k: int) -> str:
    """Rows = groups; x = pooled package oil bias at cum-k; grey = frozen D99 interval (record, oil); blue = mid_r2, orange = record."""
    groups = [g for g in st.GROUPS if g in set(pooled["group"])]
    W, rowh, left, right = 620, 26, 92, 20
    H = 30 + rowh * len(groups) + 24
    lo, hi = -0.5, 0.5
    xs = lambda v: left + (min(max(v, lo), hi) - lo) / (hi - lo) * (W - left - right)
    out = [f"<svg viewBox='0 0 {W} {H}' width='{W}' role='img' aria-label='pooled oil package bias at cum-{k}'>"]
    for v in np.arange(lo, hi + 1e-9, 0.1):
        x = xs(v)
        out.append(f"<line x1='{x:.1f}' x2='{x:.1f}' y1='22' y2='{H - 22}' stroke='var(--grid)' stroke-width='{1.5 if abs(v) < 1e-9 else 1}'/>")
        out.append(f"<text x='{x:.1f}' y='{H - 8}' text-anchor='middle'>{v:+.0%}</text>")
    out.append(f"<text x='{left}' y='14'>cum-{k} oil: Σ actual / Σ forecast − 1 per package, tuning packages pooled (negative = forecast HIGH)</text>")
    for i, g in enumerate(groups):
        y = 34 + i * rowh
        out.append(f"<text x='{left - 8}' y='{y + 4}' text-anchor='end'>{g.replace('MID_', '')}</text>")
        f = frozen[(frozen.group == g) & (frozen.stream == "oil") & (frozen.horizon == k)]
        if len(f) and np.isfinite(f["interval_lo"].iloc[0]):
            a, b = xs(float(f["interval_lo"].iloc[0])), xs(float(f["interval_hi"].iloc[0]))
            cell = "D99 cell" if bool(f["d99_cell"].iloc[0]) else "not a D99 cell"
            out.append(f"<rect x='{a:.1f}' y='{y - 5}' width='{max(b - a, 1):.1f}' height='10' rx='4' fill='var(--band)'><title>{g} cum-{k} frozen interval "
                       f"{float(f['interval_lo'].iloc[0]):+.1%} … {float(f['interval_hi'].iloc[0]):+.1%} ({cell})</title></rect>")
        for var, col, dy in (("mid_r2", "var(--s1)", -0), ("record", "var(--s2)", 0)):
            r = pooled[(pooled.group == g) & (pooled.variant == var) & (pooled.stream == "oil") & (pooled.horizon == k)]
            if not len(r) or not np.isfinite(r["pkg_bias"].iloc[0]):
                continue
            b, n = float(r["pkg_bias"].iloc[0]), int(r["n_packages"].iloc[0])
            out.append(f"<circle cx='{xs(b):.1f}' cy='{y + dy}' r='5' fill='{col}' stroke='var(--surface)' stroke-width='2'><title>{g} {var} cum-{k}: "
                       f"{b:+.1%} over {n} packages</title></circle>")
        r = pooled[(pooled.group == g) & (pooled.variant == "record") & (pooled.stream == "oil") & (pooled.horizon == k)]
        if len(r) and np.isfinite(r["pkg_bias"].iloc[0]):
            out.append(f"<text x='{W - right}' y='{y + 4}' text-anchor='end'>{float(r['pkg_bias'].iloc[0]):+.1%} · n {int(r['n_packages'].iloc[0])}</text>")
    out.append("</svg>")
    return "".join(out)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--docs", type=Path, default=Path("docs") / "box" / "step21b-2026-11-01")
    a = ap.parse_args(argv)
    d = a.docs
    r = lambda n: pd.read_csv(d / f"{n}.csv") if (d / f"{n}.csv").exists() and (d / f"{n}.csv").stat().st_size > 2 else pd.DataFrame()
    meta = json.loads((d / "score_meta.json").read_text(encoding="utf-8"))
    summ, pooled, frozen = r("summary_table"), r("pooled"), pd.read_csv(d / "frozen_d99.csv")
    tab, cells, wf, guard, eh = r("prox_factor_table"), r("cells"), r("walk_forward"), r("guard_d106"), r("expected_holdout")
    sticks = pd.read_csv(d / "sticks_midland_table.csv.gz")
    cards, pad = r("cards_q1"), r("pad_c233")
    s: list[str] = []
    s += ["<!doctype html><html><head><meta charset=utf-8><meta name=viewport content='width=device-width,initial-scale=1'>",
          f"<title>BOX 21b Midland tuning</title><style>{CSS}</style></head><body>",
          "<h1>BOX step 21b — Midland tuning-fold scoring (gate 21b)</h1>",
          (f"<div class=meta>built {html.escape(meta['built_at'])} · pre-registration digest {meta['definition_digest'][:8]} (frozen SHA 501d799; every run's "
           f"frozen-file check below) · tuning blocks only (D52 holdout dropped by the harness, counted only) · actuals through "
           f"{st.DEFINITION['folds']['actuals_through']} · D99 draws {meta['n_draws']} · read-only, nothing stored</div>"),
          (f"<div class=flag><b>Frozen at gate 21b:</b> D99 intervals <code>frozen_d99.csv</code> sha256 <code>{meta['frozen_d99_sha256']}</code>; water "
           f"<code>frozen_water.csv</code> sha256 <code>{meta.get('frozen_water_sha256')}</code>. Observer proof (MID_WCC plain vs observed): "
           f"<b>{html.escape(str(meta['proof'].get('status')))}</b>.</div>"),
          ("<div class=toc><a href='#summary'>summary</a><a href='#prox'>proximity factor</a><a href='#groups'>per group</a><a href='#ll'>long laterals</a>"
           "<a href='#s9'>reported</a><a href='#water'>water</a><a href='#pad'>Pad C 233</a></div>"),
          "<h2 id=summary>1. Record treatment per group</h2>",
          "<div class=meta>Grain: development packages (D53), tuning cutoffs pooled (D99 form). Record rule = PREREG §5 on SCORED counts; D106 guard per stream.</div>",
          t(summ),
          ("<div class=legend><span><i style='background:var(--s1)'></i>mid_r2 (raw)</span><span><i style='background:var(--s2)'></i>record treatment</span>"
           "<span><i style='background:var(--band);border-radius:2px'></i>frozen D99 interval (record, oil)</span></div>"),
          f"<div class=viz>{dot_plot(pooled, frozen[frozen.role == 'record'], 12)}</div><div class=viz>{dot_plot(pooled, frozen[frozen.role == 'record'], 24)}</div>"]
    # proximity
    use = tab[tab["usable"].astype(bool)].copy()
    sx = pd.crosstab(sticks["outcome_interim"], sticks["outcome"], margins=True).reset_index()
    by_g = pd.crosstab(sticks["group"], sticks["outcome"]).reset_index()
    hc = sticks[sticks["outcome"] == "haircut"]
    fac_g = hc.groupby("group").agg(sticks=("factor", "size"), factor_p50=("factor", "median"), interim_p50=("factor_interim", "median"),
                                     gap_sensitivity_p50=("factor_gap", "median")).reset_index()
    s += ["<h2 id=prox>2. The Midland proximity factor (§4; applied as production applies it — Michael 2026-11-01)</h2>",
          (f"<div class=meta>Fit on {meta['n_children']:,} scored TUNING children (all cutoffs), {meta['n_children_multi']:,} multi-parent, "
           f"{meta['n_children_multi_scored_oil24']:,} with a cum-24 outcome; l_rel = ln(actual / as-of mid_r2) minus the (group, cutoff) mean; factor = "
           "exp(mean l_rel), usable at ≥ 30 children. Applied rungs k2 (class × count × flank) → k3 (class × count) → k4 (class); k1 (bench pair) fitted and "
           "reported, never applied. Level is partly in-sample (the factor is applied to the wells it was fit on) — stated with every number.</div>"),
          "<h3>Usable rows (applied rungs first)</h3>", t(use.sort_values(["rung", "n_train"], ascending=[True, False])),
          "<h3>The five cards you read as too light (FINDINGS §5 Q1): interim → Midland, + the nearest-gap-rung sensitivity</h3>", t(cards),
          "<h3>Haircut sticks by group: factor (median)</h3>", t(fac_g),
          "<h3>Stick outcomes: interim (21a r7, Delaware table) × Midland table</h3>", t(sx), t(by_g),
          "<h3>DEAN undrilled sticks by outcome: generated body vs loop addition (D143)</h3>",
          t(pd.crosstab(sticks.loc[sticks.group == "MID_DEAN", "part"], sticks.loc[sticks.group == "MID_DEAN", "outcome"]).reset_index())]
    gt = r("prox_factor_table_gap_sensitivity")
    if len(gt):
        s += ["<h3>Nearest-gap rung (sensitivity, not the record): keys with ≥ 30 children</h3>",
              t(gt[(gt.rung == "kg") & gt["usable"].astype(bool)].sort_values("n_train", ascending=False))]
    # per group
    s.append("<h2 id=groups>3. Per group</h2>")
    for g in st.GROUPS:
        if g not in set(summ.get("group", [])):
            continue
        p = pooled[pooled.group == g]
        piv = p.pivot_table(index=["stream", "horizon"], columns="variant", values="pkg_bias").reset_index()
        npk = p[p.variant == "record"][["stream", "horizon", "n_packages", "sf band", "sf band bench", "verdict"]]
        c = cells[(cells.group == g) & (cells.variant.isin([st.PROX, st.PROX_WF, st.RAW])) & (cells.n_packages > 0)]
        c = c.pivot_table(index=["stream", "horizon", "cutoff"], columns="variant", values="pkg_bias").reset_index()
        cn = cells[(cells.group == g) & (cells.variant == st.PROX)][["stream", "horizon", "cutoff", "n_packages"]]
        c = c.merge(cn, on=["stream", "horizon", "cutoff"], how="left")
        w = wf[(wf.group == g)].pivot_table(index=["stream", "cutoff"], columns="horizon", values="haircut").reset_index() if len(wf) else pd.DataFrame()
        s += [f"<h3 id={g}>{g} — bench {st.GROUPS[g][0]}, extent {st.GROUPS[g][1]}</h3>",
              "<div class=meta>Pooled package bias by treatment (tuning packages, all cutoffs):</div>", t(piv), t(npk),
              "<div class=meta>Per cutoff (n = mid_r2p packages):</div>", t(c),
              "<div class=meta>Walk-forward haircut on mid_r2p (mean earlier package bias, D57 / D94):</div>", t(w),
              "<div class=meta>D106 guard (D62-style tuning table of mid_r2p; D92 g(48) of mid_r2's months):</div>", t(guard[guard.group == g]),
              "<div class=meta>Expected scored holdout (21a holdout COUNTS × scored share; no holdout read):</div>", t(eh[eh.group == g]),
              "<div class=meta>Frozen D99 intervals (P2.5–P97.5 over 2,000 20 % block draws of the tuning packages, seed 5):</div>",
              t(frozen[frozen.group == g])]
    s += ["<h2 id=ll>4. Long laterals (§8, reported, never judged)</h2>",
          "<div class=meta>Package bias on the subset (packages = the subset's members). mid_r2 = Cui Midland panel; _lin = linear per ft; _cuide = Delaware panel; same cohort.</div>",
          t(r("long_laterals")),
          "<h2 id=s9>5. Reported, never judged (§9)</h2>", "<h3>Thin-control (< 3 local wells within 3 mi at the cutoff)</h3>", t(r("thin_control")),
          "<h3>Production-sharing vs not</h3>", t(r("sharing")), "<h3>Edges (within 5 mi, by compass side; mid_r2 selection columns)</h3>", t(r("edge_regions")),
          "<h2 id=water>6. Water (§7, D107 ratio on raw mid_r2 oil; D109)</h2>", t(r("water_cells")), "<h3>Frozen water intervals</h3>", t(r("water_intervals")),
          "<h3>Reach and operator concentration (D133)</h3>", t(r("water_reach")),
          "<h2 id=pad>7. Pad C 233 (named check, reported, never judged)</h2>", t(pad),
          "<h2>8. Run records</h2>", t(r("f_identity").groupby(["group"]).agg(max_rel_spread=("max_rel_spread", "max"), cells=("F", "size")).reset_index()),
          "</body></html>"]
    (d / "index.html").write_text("\n".join(s), encoding="utf-8")
    print(f"wrote {d / 'index.html'}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
