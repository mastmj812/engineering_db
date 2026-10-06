"""BOX step 1b — consensus-flag calibration cards (read-only).

Gate 1 ratifies consensus flags BY CLASS, never well-by-well (Michael 2026-10-06):
for every (tagged bench -> suggested bench) swap class that touches the pilot
evidence sets, sample ~N wells across the flag-margin distribution and render a
gunbarrel card per well. Michael marks each card agree / reject; class precision
decides whether the class is accepted wholesale.

Pooling (D19/D20): WCA_1, WCA_2 and WCXY are one evidence pool `WCA` for
steps 2-4, so swaps inside the pool are moot and are not carded. A flag INTO
WCXY is never applied (D20) and is not carded either. Under option A a flagged
well leaves its tagged bench's evidence and joins the suggested bench's, so
both outbound and inbound classes of the pilot benches are carded.

Card = cross-section of the subject's 1.5-mi neighbourhood: witnesses by
east-west offset (ft) vs TVD, coloured by bench tag, dashed local band medians,
subject as the large marker; inset plan view; and the local 12-mo oil/ft of the
witnesses by bench (a performance tiebreak: does the well produce like its tag
or like the suggested bench?). All read-only.
"""

from __future__ import annotations

import base64
import datetime as _dt
import io
import json
import math
from pathlib import Path
from typing import Any

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

from box.bench_qc import (
    DEFAULT_PARAMS,
    NM_FIPS,
    PILOT_BENCHES,
    ConsensusParams,
    _esc,
    _fmt,
    _project_xy_ft,
    _table,
    local_bands,
)

WCA_POOL: frozenset[str] = frozenset({"WCA_1", "WCA_2", "WCXY"})  # D19 + D20
NEVER_INTO: frozenset[str] = frozenset({"WCXY"})  # D20: nothing is promoted into WCXY
CARDS_PER_CLASS = 10
MIN_CLASS_FOR_SAMPLING = 12  # smaller classes: card every well

_BENCH_COLORS = {
    "BS1_S": "#a16207", "BS1_C": "#ca8a04", "BS2_S": "#16a34a", "BS2_C": "#4ade80", "BS3_S": "#0891b2", "BS3_C": "#67e8f9",
    "WCXY": "#7c3aed", "WCA_1": "#2563eb", "WCA_2": "#1e3a8a", "WCB_1": "#dc2626", "WCB_2": "#7f1d1d", "WCC": "#f97316",
    "WCD": "#fb923c", "AVA_0": "#be185d", "AVA_1": "#db2777", "AVA_2": "#f472b6", "OTHER": "#6b7280", "WDFD": "#111827",
}


def pool(bench: str) -> str:
    return "WCA" if bench in WCA_POOL else bench


def flag_classes(df: pd.DataFrame, benches: tuple[str, ...] = PILOT_BENCHES) -> pd.DataFrame:
    """Flagged wells whose tagged OR suggested bench is a pilot bench, with the
    pooled class label; in-pool swaps and flags into WCXY are dropped."""
    f = df[(df["cons_status"] == "flag") & df["cons_suggest"].notna()].copy()
    pilot_pools = {pool(b) for b in benches}
    f["from_pool"] = f["formation_blueox"].map(pool)
    f["to_pool"] = f["cons_suggest"].map(pool)
    f = f[(f["from_pool"] != f["to_pool"]) & ~f["cons_suggest"].isin(NEVER_INTO)]
    f = f[f["from_pool"].isin(pilot_pools) | f["to_pool"].isin(pilot_pools)]
    f["swap_class"] = f["from_pool"] + "->" + f["to_pool"]
    # margin: how decisively it sits in the other band (own delta / nearest delta; inf when own absent)
    own = f["cons_own_delta"].astype(float)
    f["margin_ratio"] = np.where(own.isna(), np.inf, own / f["cons_nearest_delta"].astype(float).clip(lower=1))
    return f


def sample_class(cls: pd.DataFrame, n: int = CARDS_PER_CLASS) -> pd.DataFrame:
    """Deterministic stratified sample: evenly spaced quantiles of the margin
    distribution (weakest flags first), all rows when the class is small."""
    if len(cls) <= MIN_CLASS_FOR_SAMPLING:
        return cls.sort_values(["margin_ratio", "api10"])
    s = cls.sort_values(["margin_ratio", "api10"]).reset_index(drop=True)
    idx = np.unique(np.round(np.linspace(0, len(s) - 1, n)).astype(int))
    return s.iloc[idx]


def _neighbourhood(df: pd.DataFrame, xy: np.ndarray, i: int, p: ConsensusParams) -> pd.DataFrame:
    d = np.hypot(xy[:, 0] - xy[i, 0], xy[:, 1] - xy[i, 1])
    m = (d <= p.radius_ft) & np.isfinite(d)
    m[i] = False
    nb = df.loc[m].copy()
    nb["dx_ft"] = xy[m, 0] - xy[i, 0]
    nb["dy_ft"] = xy[m, 1] - xy[i, 1]
    nb["dist_ft"] = d[m]
    return nb


def _png(fig: Any, dpi: int = 85) -> str:
    buf = io.BytesIO()
    fig.savefig(buf, format="png", dpi=dpi, bbox_inches="tight")
    plt.close(fig)
    return "data:image/png;base64," + base64.b64encode(buf.getvalue()).decode("ascii")


def card_figure(subj: pd.Series, nb: pd.DataFrame, p: ConsensusParams) -> tuple[str, dict[str, Any]]:
    wit = nb[nb["cons_witness"]]
    bands = local_bands({b: g["tvd_ft"].values for b, g in wit.groupby("formation_blueox")}, p)
    fig = plt.figure(figsize=(9.2, 4.6))
    gs = fig.add_gridspec(1, 3, width_ratios=[2.2, 1.0, 1.0], wspace=0.35)
    ax = fig.add_subplot(gs[0, 0])
    for b, g in nb.groupby("formation_blueox"):
        c = _BENCH_COLORS.get(str(b), "#9ca3af")
        clean = g[g["cons_witness"]]
        dirty = g[~g["cons_witness"]]
        ax.scatter(clean["dx_ft"], clean["tvd_ft"], s=16, c=c, label=f"{b} (n={len(g)})", linewidths=0)
        ax.scatter(dirty["dx_ft"], dirty["tvd_ft"], s=16, facecolors="none", edgecolors=c, linewidths=0.8)
    for b, (med, n, iqr) in sorted(bands.items(), key=lambda kv: kv[1][0]):
        ax.axhline(med, color=_BENCH_COLORS.get(b, "#9ca3af"), ls="--", lw=0.8)
        ax.text(p.radius_ft * 1.02, med, f"{b} {med:,.0f} (n={n}, IQR {iqr:.0f})", fontsize=7, va="center")
    ax.scatter([0], [subj["tvd_ft"]], s=140, marker="*", c=_BENCH_COLORS.get(subj["formation_blueox"], "#000"), edgecolors="k", linewidths=0.8, zorder=5)
    ax.set_xlim(-p.radius_ft, p.radius_ft)
    ax.invert_yaxis()
    ax.set_xlabel("east-west offset from subject, ft (hollow = not clean evidence)")
    ax.set_ylabel("TVD, ft")
    ax.grid(alpha=0.25)
    ax.legend(fontsize=6, loc="lower left", ncol=2)
    # plan view
    ax2 = fig.add_subplot(gs[0, 1])
    for b, g in nb.groupby("formation_blueox"):
        ax2.scatter(g["dx_ft"], g["dy_ft"], s=8, c=_BENCH_COLORS.get(str(b), "#9ca3af"), linewidths=0)
    ax2.scatter([0], [0], s=90, marker="*", c=_BENCH_COLORS.get(subj["formation_blueox"], "#000"), edgecolors="k", linewidths=0.8, zorder=5)
    ax2.set_aspect("equal")
    ax2.set_title("plan, ft", fontsize=8)
    ax2.tick_params(labelsize=6)
    # performance by bench among cohort witnesses
    ax3 = fig.add_subplot(gs[0, 2])
    coh = wit[wit["cohort"]]
    perf = {}
    for b, g in coh.groupby("formation_blueox"):
        if len(g) >= 3:
            perf[str(b)] = (float(g["oil12_kft"].median()), len(g))
    if perf:
        order = sorted(perf, key=lambda b: perf[b][0])
        ax3.barh(order, [perf[b][0] for b in order], color=[_BENCH_COLORS.get(b, "#9ca3af") for b in order])
        for k, b in enumerate(order):
            ax3.text(perf[b][0], k, f" n={perf[b][1]}", fontsize=6, va="center")
    if subj["cohort"] and not math.isnan(float(subj["oil12_kft"])):
        ax3.axvline(subj["oil12_kft"], color="k", ls="--", lw=0.9)
    ax3.set_title("12-mo oil, bbl/1,000 ft\n(cohort witnesses; dashed = subject)", fontsize=7)
    ax3.tick_params(labelsize=6)
    meta = {"bands": {b: {"med": v[0], "n": v[1], "iqr": v[2]} for b, v in bands.items()}, "perf": perf, "n_nb": len(nb), "n_wit": len(wit)}
    return _png(fig), meta


_CSS = """
body{font:13px/1.45 -apple-system,Segoe UI,Roboto,sans-serif;color:#111827;background:#fff;margin:0 24px 48px;max-width:1500px}
h1{font-size:20px;margin:18px 0 4px} h2{font-size:16px;margin:36px 0 6px;border-top:2px solid #e5e7eb;padding-top:14px}
h3{font-size:13px;margin:14px 0 2px} .meta{color:#6b7280;font-size:12px}
table{border-collapse:collapse;font-size:12px;margin:8px 0} th,td{border:1px solid #e5e7eb;padding:3px 7px;text-align:left;vertical-align:top} th{background:#f9fafb}
.card{border:1px solid #e5e7eb;border-radius:6px;padding:8px 10px;margin:10px 0} .card img{max-width:100%;height:auto}
.kv{font-size:12px;color:#374151} .kv b{color:#111827} .toc a{margin-right:10px;font-size:12px}
"""


def sensitivity(df: pd.DataFrame, benches: tuple[str, ...]) -> list[list[Any]]:
    """Cohort median 12-mo oil/ft and TVD IQR per pooled pilot bench, as tagged
    vs with every carded-class flag applied (option A, pooled)."""
    f = flag_classes(df, benches)
    moved_out = set(f["api10"])
    join = f.groupby("to_pool")["api10"].apply(list).to_dict()
    df = df.copy()
    df["pool"] = df["formation_blueox"].map(pool)
    rows = []
    for pb in sorted({pool(b) for b in benches}):
        cur = df[(df["pool"] == pb)]
        new = pd.concat([cur[~cur["api10"].isin(moved_out)], df[df["api10"].isin(join.get(pb, []))]])
        for name, g in (("as tagged", cur), ("flags applied (A)", new)):
            c = g[g["cohort"]]
            rows.append([pb, name, _fmt(len(g)), _fmt(len(c)), _fmt(c["oil12_kft"].median(), 0),
                         f"{_fmt(c['oil12_kft'].quantile(0.25), 0)}–{_fmt(c['oil12_kft'].quantile(0.75), 0)}",
                         _fmt(g["tvd_ft"].quantile(0.75) - g["tvd_ft"].quantile(0.25), 0)])
    return rows


def build(df: pd.DataFrame, out_dir: Path, benches: tuple[str, ...] = PILOT_BENCHES, p: ConsensusParams = DEFAULT_PARAMS) -> dict[str, Any]:
    out_dir.mkdir(parents=True, exist_ok=True)
    pos_ok = df["mid_lon"].notna() & df["mid_lat"].notna()
    xy = np.full((len(df), 2), np.nan)
    xy[pos_ok.values] = _project_xy_ft(df.loc[pos_ok, "mid_lon"].values, df.loc[pos_ok, "mid_lat"].values)
    df = df.reset_index(drop=True)
    f = flag_classes(df, benches)
    classes = f.groupby("swap_class").size().sort_values(ascending=False)
    sampled: list[pd.DataFrame] = []
    sections: list[str] = []
    for cls, n_cls in classes.items():
        g = f[f["swap_class"] == cls]
        s = sample_class(g)
        s = s.assign(swap_class=cls)
        cards = []
        for _, subj in s.iterrows():
            i = int(df.index[df["api10"] == subj["api10"]][0])
            nb = _neighbourhood(df, xy, i, p)
            png, meta = card_figure(subj, nb, p)
            own = meta["bands"].get(subj["formation_blueox"])
            sug = meta["bands"].get(subj["cons_suggest"])
            kv = (
                f"<b>{_esc(subj['api10'])}</b> {_esc(subj['well_name'])} · {_esc(subj['operator'])} · {'NM' if subj['state_code'] == NM_FIPS else 'TX'} {_esc(subj['county'])} · "
                f"fp {_esc(subj['first_production_date'])} · lateral {_fmt(subj['lateral_length_ft'], 0)} ft · TVD <b>{_fmt(subj['tvd_ft'], 0)}</b>"
                f"{' · <b>planned survey</b>' if subj['planned'] else ''}{' · <b>permit-round TVD</b>' if subj['tvd_round'] else ''}<br>"
                f"tag <b>{_esc(subj['formation_blueox'])}</b> (source {_esc(subj['formation_blueox_source'])}; own band {_fmt(own['med'] if own else None, 0)}, n={_fmt(own['n'] if own else 0)}, Δ {_fmt(subj['cons_own_delta'], 0)} ft) → "
                f"suggest <b>{_esc(subj['cons_suggest'])}</b> (band {_fmt(sug['med'] if sug else None, 0)}, n={_fmt(sug['n'] if sug else 0)}, Δ {_fmt(subj['cons_nearest_delta'], 0)} ft) · "
                f"margin ratio {('∞' if math.isinf(subj['margin_ratio']) else _fmt(subj['margin_ratio'], 1))} · witnesses {meta['n_wit']} of {meta['n_nb']} wells in 1.5 mi · "
                f"sql/23 nearest {_esc(subj['sql23_nearest'])} · 12-mo oil {_fmt(subj['oil12_kft'], 0)} bbl/kft{'' if subj['cohort'] else ' (not cohort)'}"
            )
            cards.append(f"<div class=card id=\"w{_esc(subj['api10'])}\"><div class=kv>{kv}</div><img src=\"{png}\"></div>")
        sampled.append(s)
        sections.append(f"<h2 id=\"c{_esc(cls)}\">{_esc(cls)} — {n_cls} flagged, {len(s)} carded</h2>" + "".join(cards))
    sample = pd.concat(sampled) if sampled else f.iloc[0:0]
    cols = ["swap_class", "api10", "well_name", "operator", "state_code", "county", "formation_blueox", "cons_suggest", "tvd_ft", "planned", "tvd_round",
            "cons_own_delta", "cons_nearest_delta", "margin_ratio", "cons_n_witness", "sql23_nearest", "oil12_kft", "cohort"]
    sample = sample[cols].copy()
    sample["verdict"] = ""
    sample.to_csv(out_dir / "cards_sample.csv", index=False)
    f[cols].to_csv(out_dir / "flags_all.csv", index=False)
    built = _dt.datetime.now(tz=_dt.UTC).astimezone().isoformat(timespec="seconds")
    sens = sensitivity(df, benches)
    page = [
        f"<!doctype html><html><head><meta charset=\"utf-8\"><title>BOX step 1 — flag calibration cards</title><style>{_CSS}</style></head><body>",
        "<h1>BOX step 1 — consensus-flag calibration cards</h1>",
        f"<div class=meta>Built {built}, read-only. Classes are pooled per D19/D20 (WCA_1 + WCA_2 + WCXY = WCA; nothing is promoted into WCXY). "
        + f"Sample = {CARDS_PER_CLASS} wells per class at evenly spaced quantiles of the margin ratio (own-band Δ ÷ suggested-band Δ; ∞ = own band absent), weakest flags first; classes of ≤ {MIN_CLASS_FOR_SAMPLING} are carded in full. "
        + "Mark each card agree / reject (reply in chat by api10, or fill <code>cards_sample.csv</code> column <code>verdict</code>); a class is accepted or rejected wholesale on its precision. "
        + "Star = subject; dots = wells within 1.5 mi coloured by tag, hollow = not clean evidence (planned survey, round TVD, &lt; 6 mo, unmapped); dashed = coherent local band medians.</div>",
        "<div class=toc>" + "".join(f"<a href=\"#c{_esc(c)}\">{_esc(c)} ({n})</a>" for c, n in classes.items()) + "</div>",
        "<h2>Sensitivity — what applying every carded flag (option A, pooled) does to the pilot evidence sets</h2>",
        _table(["pool", "set", "producing hz", "D9 cohort", "cohort median 12-mo oil, bbl/1,000 ft", "IQR", "TVD IQR, ft (all wells)"], sens),
        "<h2>Classes</h2>",
        _table(["class", "flagged", "carded", "TX", "NM", "planned-survey share", "median margin ratio"],
               [[c, _fmt(n), _fmt(len(sample[sample['swap_class'] == c])), _fmt(int((f[f['swap_class'] == c]['state_code'] != NM_FIPS).sum())), _fmt(int((f[f['swap_class'] == c]['state_code'] == NM_FIPS).sum())),
                 _fmt(float(f[f['swap_class'] == c]['planned'].mean()), pct=True), _fmt(float(np.median(np.minimum(f[f['swap_class'] == c]['margin_ratio'], 99))), 1)] for c, n in classes.items()]),
        *sections,
        "</body></html>",
    ]
    (out_dir / "cards.html").write_text("".join(page), encoding="utf-8")
    summary = {"built_at": built, "n_flags_carded_classes": len(f), "classes": {c: int(n) for c, n in classes.items()}, "n_cards": len(sample), "sensitivity": sens}
    (out_dir / "cards_summary.json").write_text(json.dumps(summary, indent=1, default=str), encoding="utf-8")
    return summary
