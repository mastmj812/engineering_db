"""BOX step 15 — bench QC + the pooling evidence for a Delaware bench FAMILY (read-only).

Plan docs/box_type_curves_plan.md §5 step 15: per family, step-1 bench QC (consensus flags, the class rule of record,
gate) -> pooling decision (D19 / D33 pattern) -> step-3 extent. This module is the first half for one family (15a =
Bone Spring 3: BS3_S + BS3_C). It reuses the Phase 1 tooling unchanged:

  * box/bench_qc.py   — pull + the consensus detector + the per-bench QC page (one page per bench, as step 1);
  * box/qc_rule.py    — the class rule of record (class gate + sql/23 second vote + GOR veto + A-prime + never Bone
                        Spring -> Wolfcamp; Michael's gate-1 card verdicts outrank it per well);
  * the frozen pools  — the D84 pool directory (wells_final_WCA / BS2_S + universe.csv). A well a frozen pool holds
                        stays there (gate-1 judgment, D84: never re-decided), whatever its live tag is today.

Family membership (BOX-only, no warehouse change), per live producing horizontal:
  member            box_bench after the rule is a family bench, not held by a frozen pool, not excluded;
  frozen_elsewhere  the live tag is a family bench but a frozen pool holds it (e.g. BS3_S -> BS2_S, accepted 1.00 at gate 1);
  old_churn_kept    judged at gate 1 (in the universe), not in any frozen pool, and today's rule would move it out of the
                    family: gate 1 did not move it, so it stays a member (D84) — counted, listed;
  new_ruled_out     never judged, and the rule moves it out of the family (it belongs to the next refresh of the target pool);
  excluded          docs/box/exclusions.csv.
No accepted class points INTO a Bone Spring 3 bench, so nothing joins from other benches.

A BS3_S <-> BS3_C swap is a sand <-> carbonate swap inside one interval: the detector reports it as ``ambiguous_lith``
and never flags it (sql/23 guard 3). Family membership is therefore the same whether the two benches are pooled or
not; pooling only decides whether steps 2-4 / 9 see one bench or two. The pooling evidence (D19 pattern) is: local
depth separation where both bands are coherent, ambiguous_lith counts, co-location, and the D33-style within-location
differences (5-mi block FE + first-production-year FE) in 12-mo oil per 1,000 ft, 12-mo GOR and the cum-24 / cum-12
shape ratio, with a block-bootstrap 90 % CI.
"""

from __future__ import annotations

import html
import itertools
import json
import math
from pathlib import Path
from typing import Any

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

from box import basin as bsn
from box import bench_qc as bq
from box import qc_rule as qr
from box.flag_cards import NEVER_INTO, pool

FAMILIES: dict[str, tuple[str, ...]] = {
    "BS3": ("BS3_S", "BS3_C"),  # 15a
    "WCB": ("WCB_1", "WCB_2"),  # 15b (WCB_2 deep-TVD tagging problem, memory wcb2-deep-tvd-screening)
    "BS1": ("BS1_S",),  # 15c
    "WCC": ("WCC",),  # 15d
    "BS2C": ("BS2_C",),  # step-14 thin-bench candidates
    "AVA": ("AVA_0", "AVA_1", "AVA_2"),
    "WCD": ("WCD",),
}
BLOCK_FT = 5 * bq.FT_PER_MI  # location FE grain (step 5c used 5-mi blocks where a bench had no TC areas)
COLOC_FT = 1.5 * bq.FT_PER_MI  # the detector's neighbourhood radius
N_BOOT = 400
BOOT_SEED = 20261016


# ----------------------------------------------------------------------------
# Membership (pure)
# ----------------------------------------------------------------------------


def frozen_pools(pool_dir: Path | list[Path]) -> dict[str, str]:
    """api10 -> pool for every wells_final_<pool>.csv in the frozen pool directory (or directories)."""
    out: dict[str, str] = {}
    for f in _finals(pool_dir):
        name = f.stem.removeprefix("wells_final_")
        for a in pd.read_csv(f, dtype={"api10": str}, usecols=["api10"])["api10"]:
            if a in out and out[a] != name:
                raise ValueError(f"{a} is in two frozen pools ({out[a]}, {name})")
            out[a] = name
    return out


def _finals(pool_dir: Path | list[Path]) -> list[Path]:
    dirs = [pool_dir] if isinstance(pool_dir, Path) else list(pool_dir)
    return [f for d in dirs for f in sorted(d.glob("wells_final_*.csv"))]


def frozen_tags(pool_dir: Path | list[Path]) -> dict[str, str]:
    """api10 -> the formation_blueox tag the frozen pool file recorded (to tell a gate-1 reassignment from a re-tag since)."""
    out: dict[str, str] = {}
    for f in _finals(pool_dir):
        d = pd.read_csv(f, dtype={"api10": str}, usecols=["api10", "formation_blueox"])
        out.update(zip(d["api10"], d["formation_blueox"]))
    return out


def family_membership(
    ruled: pd.DataFrame, family: tuple[str, ...], frozen: dict[str, str], seen_ids: set[str], excluded_ids: set[str]
) -> pd.DataFrame:
    """Rows touching the family (live tag or box_bench in it) with ``family_role`` and ``family_bench``.

    ``ruled`` = box.qc_rule.apply_rule output on the live scored frame. ``family_bench`` = the bench the member
    counts for (its box_bench, or its live tag for old_churn_kept)."""
    fam = set(family)
    d = ruled[ruled["formation_blueox"].isin(fam) | ruled["box_bench"].isin(fam)].copy()
    roles, benches = [], []
    for a, tag, bb in zip(d["api10"], d["formation_blueox"], d["box_bench"]):
        if a in excluded_ids:
            roles.append("excluded"); benches.append(None)
        elif a in frozen:
            roles.append("frozen_elsewhere"); benches.append(None)
        elif bb in fam:
            roles.append("member"); benches.append(bb)
        elif a in seen_ids:
            roles.append("old_churn_kept"); benches.append(tag)
        else:
            roles.append("new_ruled_out"); benches.append(None)
    d["family_role"] = roles
    d["family_bench"] = benches
    d["frozen_pool"] = d["api10"].map(frozen)
    return d.sort_values("api10").reset_index(drop=True)


def flag_ledger(ruled: pd.DataFrame, family: tuple[str, ...]) -> pd.DataFrame:
    """Consensus flags with the tagged or suggested bench in the family, by pooled swap class and rule disposition."""
    fam = set(family)
    f = ruled[(ruled["cons_status"] == "flag") & ruled["cons_suggest"].notna()].copy()
    f = f[f["formation_blueox"].isin(fam) | f["cons_suggest"].isin(fam)]
    if f.empty:
        return pd.DataFrame(columns=["swap_class", "direction", "standing", "box_action", "n", "n_cohort"])
    f["swap_class"] = f["formation_blueox"].map(pool) + "->" + f["cons_suggest"].map(pool)
    f["direction"] = np.where(f["formation_blueox"].isin(fam), "out of family", "into family")

    def standing(c: str, sug: str) -> str:
        # same order as qc_rule.decide: a flag into WCXY is never applied (D20) before any class test
        if sug in NEVER_INTO:
            return "into WCXY band (never applied, D20; witness kept)"
        if c in qr.ACCEPTED_CLASSES:
            return f"accepted ({qr.ACCEPTED_CLASSES[c]:.2f})"
        if c in qr.REJECTED_CLASSES:
            return f"rejected ({qr.REJECTED_CLASSES[c]:.2f})"
        if c in qr.HOLD_CLASSES:
            return f"hold ({qr.HOLD_CLASSES[c]:.2f})"
        a, b = c.split("->")
        if qr._is_bs_to_wc(a, b):
            return "Bone Spring -> Wolfcamp (never applied)"
        return "uncalibrated (tag kept)"

    f["standing"] = [standing(c, g) for c, g in zip(f["swap_class"], f["cons_suggest"])]
    g = (f.groupby(["swap_class", "direction", "standing", "box_action"])
         .agg(n=("api10", "size"), n_cohort=("cohort", "sum")).reset_index())
    return g.sort_values(["direction", "n"], ascending=[False, False]).reset_index(drop=True)


def sensitivity(ruled: pd.DataFrame, family: tuple[str, ...]) -> list[dict[str, Any]]:
    """Cohort median 12-mo oil/kft per family bench: tags as-is vs every consensus flag touching the bench applied
    (gate-1 sensitivity pattern — do the flags move the evidence-set statistics?)."""
    coh = ruled[ruled["cohort"]].copy()
    flagged = (coh["cons_status"] == "flag") & coh["cons_suggest"].notna()
    applied = np.where(flagged, coh["cons_suggest"], coh["formation_blueox"])
    out = []
    for b in family:
        a = coh.loc[coh["formation_blueox"] == b, "oil12_kft"]
        c = coh.loc[applied == b, "oil12_kft"]
        out.append({"bench": b, "n_tags": len(a), "med_tags": float(a.median()) if len(a) else math.nan,
                    "n_all_flags": len(c), "med_all_flags": float(c.median()) if len(c) else math.nan,
                    "rel_change": float(c.median() / a.median() - 1) if len(a) and len(c) else math.nan})
    return out


# ----------------------------------------------------------------------------
# Pooling evidence (pure)
# ----------------------------------------------------------------------------


def _blocks(xy: np.ndarray, size: float = BLOCK_FT) -> np.ndarray:
    ij = np.floor(xy / size).astype(np.int64)
    return np.array([f"{i}_{j}" for i, j in ij])


def fe_contrast(y: np.ndarray, is_b: np.ndarray, block: np.ndarray, year: np.ndarray) -> float:
    """OLS coefficient on is_b in y ~ block FE + year FE + is_b, using only blocks holding both benches."""
    both = pd.Series(is_b).groupby(block).agg(["min", "max"])
    keep_blocks = set(both.index[(both["min"] == 0) & (both["max"] == 1)])
    m = np.array([b in keep_blocks for b in block])
    if m.sum() < 10 or is_b[m].sum() < 5 or (1 - is_b[m]).sum() < 5:
        return math.nan
    X = pd.get_dummies(pd.DataFrame({"blk": block[m], "yr": year[m].astype(str)}), drop_first=False, dtype=float)
    # drop one year dummy to avoid collinearity with the full block set
    yr_cols = [c for c in X.columns if c.startswith("yr_")]
    X = X.drop(columns=yr_cols[:1])
    X["is_b"] = is_b[m].astype(float)
    beta, *_ = np.linalg.lstsq(X.values, y[m], rcond=None)
    return float(beta[-1])


def fe_with_ci(y: np.ndarray, is_b: np.ndarray, block: np.ndarray, year: np.ndarray,
               n_boot: int = N_BOOT, seed: int = BOOT_SEED) -> dict[str, Any]:
    ok = np.isfinite(y)
    y, is_b, block, year = y[ok], is_b[ok], block[ok], year[ok]
    est = fe_contrast(y, is_b, block, year)
    rng = np.random.default_rng(seed)
    ub = np.unique(block)
    idx_by = {b: np.where(block == b)[0] for b in ub}
    boots = []
    for _ in range(n_boot):
        pick = rng.choice(ub, size=len(ub), replace=True)
        ii = np.concatenate([idx_by[b] for b in pick])
        # relabel duplicated blocks so each draw is its own FE
        lab = np.concatenate([np.full(len(idx_by[b]), f"{b}#{k}") for k, b in enumerate(pick)])
        v = fe_contrast(y[ii], is_b[ii], lab, year[ii])
        if math.isfinite(v):
            boots.append(v)
    lo, hi = (np.percentile(boots, [5, 95]) if len(boots) >= 50 else (math.nan, math.nan))
    both = pd.Series(is_b).groupby(block).agg(["min", "max"])
    nb = int(((both["min"] == 0) & (both["max"] == 1)).sum())
    inb = np.isin(block, both.index[(both["min"] == 0) & (both["max"] == 1)])
    return {"coef": est, "ratio": math.exp(est) if math.isfinite(est) else math.nan,
            "ci90": [math.exp(lo) if math.isfinite(lo) else math.nan, math.exp(hi) if math.isfinite(hi) else math.nan],
            "n_blocks_both": nb, "n_a": int(((1 - is_b) * inb).sum()), "n_b": int((is_b * inb).sum()), "n_boot_ok": len(boots)}


def pooling_evidence(members: pd.DataFrame, a: str, b: str, xy: np.ndarray) -> dict[str, Any]:
    """D19 / D33-style evidence for pooling bench a with bench b. ``members`` = family members (family_bench in {a, b})
    with the bench_qc columns; ``xy`` = their projected midpoints, ft (same row order)."""
    from scipy.spatial import cKDTree

    is_b = (members["family_bench"].values == b).astype(int)
    coh = members["cohort"].values.astype(bool)
    year = np.array([fp.year for fp in members["first_production_date"]])
    block = _blocks(xy)
    out: dict[str, Any] = {"a": a, "b": b}
    # co-location: share of each bench's cohort wells with a cohort well of the other bench within 1.5 mi
    for x, y_ in ((a, b), (b, a)):
        mx = coh & (members["family_bench"].values == x)
        my = coh & (members["family_bench"].values == y_)
        if mx.sum() and my.sum():
            t = cKDTree(xy[my])
            d, _ = t.query(xy[mx], k=1)
            out[f"coloc_{x}"] = {"n": int(mx.sum()), "share_within_1p5mi": float((d <= COLOC_FT).mean()), "median_nn_mi": float(np.median(d) / bq.FT_PER_MI)}
    # within-location contrasts, cohort only (b relative to a)
    m = coh
    oil = members["oil12_kft"].values.astype(float)
    lo = np.log(np.where(oil > 0, oil, np.nan))
    gor = members["gor12"].values.astype(float)
    lg = np.where(gor > 0, np.log(np.where(gor > 0, gor, 1.0)), np.nan)
    c24 = pd.to_numeric(members["cum_24m_oil_bbl"], errors="coerce").values
    c12 = members["cum_12m_oil_bbl"].values.astype(float)
    shape = np.where((c24 > 0) & (c12 > 0), np.log(np.where(c24 > 0, c24, 1.0) / np.where(c12 > 0, c12, 1.0)), np.nan)
    out["oil12_kft"] = fe_with_ci(lo[m], is_b[m], block[m], year[m])
    out["gor12"] = fe_with_ci(lg[m], is_b[m], block[m], year[m])
    out["cum24_over_cum12"] = fe_with_ci(shape[m], is_b[m], block[m], year[m])
    # raw medians for the record
    raw = {}
    for x in (a, b):
        g = members[coh & (members["family_bench"] == x)]
        raw[x] = {"n_cohort": len(g), "med_oil12_kft": float(g["oil12_kft"].median()), "med_gor12": float(g["gor12"].median()),
                  "med_tvd_ft": float(g["tvd_ft"].median()), "med_lateral_ft": float(g["lateral_length_ft"].median()),
                  "share_nm": float((g["state_code"] == bq.NM_FIPS).mean())}
    out["raw"] = raw
    return out


# ----------------------------------------------------------------------------
# Rendering
# ----------------------------------------------------------------------------


def _esc(v: Any) -> str:
    return html.escape("" if v is None else str(v))


def family_map(ctx: pd.DataFrame, members: pd.DataFrame, family: tuple[str, ...], state_line_lat: float | None = bq.STATE_LINE_LAT) -> str:
    fig, axes = plt.subplots(1, len(family), figsize=(8 * len(family), 8))
    from box.flag_cards import _BENCH_COLORS as cols
    for ax, bench in zip(np.atleast_1d(axes), family):
        bq._basemap(ax, ctx, members, state_line_lat)
        for other in family:
            if other == bench:
                continue
            o = members[members["family_bench"] == other]
            ax.scatter(o["mid_lon"], o["mid_lat"], s=2, c="#9ca3af", alpha=0.5, linewidths=0, rasterized=True)
        g = members[members["family_bench"] == bench]
        c = g[g["cohort"]]
        nc = g[~g["cohort"]]
        ax.scatter(nc["mid_lon"], nc["mid_lat"], s=3, c=cols.get(bench, "#2563eb"), alpha=0.35, linewidths=0, rasterized=True,
                   label=f"{bench} not in D9 cohort (n={len(nc):,})")
        ax.scatter(c["mid_lon"], c["mid_lat"], s=5, c=cols.get(bench, "#2563eb"), alpha=0.9, linewidths=0, rasterized=True,
                   label=f"{bench} D9 cohort (n={len(c):,})")
        churn = g[g["family_role"] == "old_churn_kept"]
        ax.scatter(churn["mid_lon"], churn["mid_lat"], s=16, facecolors="none", edgecolors="#dc2626", linewidths=0.8,
                   label=f"kept on gate-1 judgment, rule would now move (n={len(churn)})")
        ax.legend(loc="lower left", fontsize=8, markerscale=2)
        ax.set_title(f"{bench} family members (n={len(g):,}); grey dots = the other family bench, light grey = all other Delaware hz", fontsize=9)
    fig.tight_layout()
    return bq._png(fig)


def block_ratio_map(ctx: pd.DataFrame, members: pd.DataFrame, xy: np.ndarray, a: str, b: str, min_each: int = 3,
                    state_line_lat: float | None = bq.STATE_LINE_LAT) -> tuple[str, int]:
    coh = members["cohort"].values.astype(bool)
    blk = _blocks(xy)
    d = pd.DataFrame({"blk": blk, "bench": members["family_bench"].values, "oil": members["oil12_kft"].values,
                      "lon": members["mid_lon"].values, "lat": members["mid_lat"].values})[coh]
    g = d.groupby(["blk", "bench"]).agg(n=("oil", "size"), med=("oil", "median"), lon=("lon", "mean"), lat=("lat", "mean")).reset_index()
    w = g.pivot(index="blk", columns="bench", values=["n", "med", "lon", "lat"])
    if (a, b) and ("n", a) in w.columns and ("n", b) in w.columns:
        w = w[(w[("n", a)] >= min_each) & (w[("n", b)] >= min_each)]
    else:
        w = w.iloc[0:0]
    fig, ax = plt.subplots(figsize=(8.5, 8))
    bq._basemap(ax, ctx, members, state_line_lat)
    if len(w):
        ratio = (w[("med", b)] / w[("med", a)]).astype(float)
        lon = ((w[("lon", a)] + w[("lon", b)]) / 2).astype(float)
        lat = ((w[("lat", a)] + w[("lat", b)]) / 2).astype(float)
        sc = ax.scatter(lon, lat, s=60, c=np.log2(ratio.clip(0.25, 4)), cmap="RdBu_r", vmin=-1, vmax=1, marker="s", edgecolors="#374151", linewidths=0.4)
        cb = fig.colorbar(sc, ax=ax, shrink=0.6)
        cb.set_ticks([-1, -0.5, 0, 0.5, 1])
        cb.set_ticklabels(["0.5x", "0.71x", "1x", "1.41x", "2x"])
        cb.set_label(f"{b} / {a} median 12-mo oil per 1,000 ft, same 5-mi block")
    ax.set_title(f"5-mi blocks with >= {min_each} D9 cohort wells of each bench (n blocks = {len(w)})", fontsize=10)
    return bq._png(fig), len(w)


def render_family_page(out: Path, family_name: str, family: tuple[str, ...], s: dict[str, Any], imgs: dict[str, str]) -> Path:
    f = bq._fmt
    p: list[str] = [
        f"<!doctype html><html><head><meta charset=\"utf-8\"><title>BOX 15a — {family_name} bench QC</title><style>{bq._CSS}</style></head><body>",
        f"<h1>BOX step 15a — {family_name} family ({' + '.join(family)}): bench QC + pooling evidence</h1>",
        (f"<div class=meta>Grain: Delaware producing horizontals (one row per api10), curated.wells_enriched, TVD-corrected formation_blueox; "
        f"warehouse as-of {_esc(s['asof'])}; built {_esc(s['built_at'])} at {_esc(s['git_sha'])}. Read-only; nothing written to the warehouse. "
        f"Frozen pools: {_esc(s['pool_dir'])}. Plan: docs/box_type_curves_plan.md §5 step 15 (15a pulled forward by Michael 2026-10-16, in parallel with step 9).</div>"),
        "<div class=toc>" + "".join(f"<a href=qc_{b}.html>{b} QC page</a>" for b in family)
        + "<a href=#set>well set</a><a href=#flags>flags</a><a href=#sens>sensitivity</a><a href=#pool>pooling</a><a href=#asks>gate asks</a></div>",
    ]
    # --- set
    p.append("<h2 id=set>1. The QC'd well set per bench (proposed for the gate)</h2>")
    p.append("<p>Role per live producing horizontal tagged into the family (or ruled into it). <b>member</b> = evidence for this bench; "
             "<b>frozen_elsewhere</b> = a frozen Phase 1 pool already holds it (gate-1 judgment stands, D84); <b>old_churn_kept</b> = judged at gate 1, not moved then, "
             "today's rule would move it — it stays (D84) and is counted in the member set; <b>new_ruled_out</b> = never judged, the rule moves it to another bench; "
             "<b>excluded</b> = docs/box/exclusions.csv. Depth witness = usable as TVD evidence (A-prime / Bone Spring→Wolfcamp flags drop the witness, keep the tag).</p>")
    rows = []
    for b in family:
        r = s["set"][b]
        rows.append([b, f(r["tagged_live"]), f(r["member"]), f(r["old_churn_kept"]), f(r["frozen_elsewhere"]), f"{_esc(r['frozen_to'])}", f"{f(r['frozen_retagged_since'])} {_esc(r['frozen_retagged_from'])}",
                     f(r["new_ruled_out"]), f(r["excluded"]), f(r["final"]), f(r["final_fp_ge_2016"]), f(r["final_cohort"]),
                     f(r["final_tvd_suspect"]), f(r["final_witness"]), f"TX {f(r['final_tx'])} / NM {f(r['final_nm'])}"])
    p.append(bq._table(["bench", "tagged live", "member (rule)", "+ old churn kept", "frozen elsewhere", "→ pool", "of which re-tagged since gate 1 (gate-1 tag)", "new ruled out", "excluded",
                        "FINAL set", "final fp ≥ 2016", "final D9 cohort", "tvd_suspect", "depth witnesses", "final by state"], rows))
    p.append(f"<p>Pooled {family_name} final set: <b>{f(s['pooled_final'])}</b> wells (fp ≥ 2016: {f(s['pooled_fp_ge_2016'])}; D9 cohort {f(s['pooled_cohort'])}). "
             f"Files: " + ", ".join(f"<code>wells_final_{b}.csv</code>" for b in family) + " (+ <code>family_roles.csv</code> with every role row).</p>")
    p.append(f"<img src=\"{imgs['map']}\" style='max-width:100%'>")
    # --- flags
    p.append("<h2 id=flags>2. Consensus flags touching the family, by swap class and how the rule of record treats them</h2>")
    p.append("<p>Class standing is the gate-1 card ledger (box/qc_rule.py). Accepted classes into the family are applied per the rule. "
             "Uncalibrated classes keep their tag (rule default) — the gate decides whether any needs calibration cards.</p>")
    fl = s["flags"]
    p.append(bq._table(["swap class", "direction", "standing", "rule action", "flags", "of which D9 cohort"],
                       [[r["swap_class"], r["direction"], r["standing"], r["box_action"], f(r["n"]), f(r["n_cohort"])] for r in fl]))
    p.append("<p>Within-family sand↔carbonate swaps are never flags (detector guard): <b>ambiguous_lith</b> counts " + ", ".join(
        f"{b} {f(s['lith'][b]['n'])} (→ {_esc(s['lith'][b]['to'])})" for b in family) + ".</p>")
    # --- sensitivity
    p.append("<h2 id=sens>3. Do the flags move the evidence? (gate-1 sensitivity pattern)</h2>")
    p.append(bq._table(["bench", "cohort n, tags as-is", "median 12-mo oil / kft", "cohort n, every flag applied", "median", "change"],
                       [[r["bench"], f(r["n_tags"]), f(r["med_tags"], 0), f(r["n_all_flags"]), f(r["med_all_flags"], 0), f(r["rel_change"], pct=True)] for r in s["sensitivity"]]))
    # --- pooling (one section per adjacent pair; none for a one-bench family)
    if not s["poolings"]:
        p.append("<h2 id=pool>4. Pooling evidence</h2><p>One-bench family: nothing to pool.</p>")
    for pe, ps, ratio_img in s["poolings"]:
        a, b = pe["a"], pe["b"]
        p.append(f"<h2 id=pool>4. Pooling evidence: {a} vs {b} (D19 / D33 pattern)</h2>")
        if ps:
            p.append(f"<p><b>Local depth separation</b> where both bands are coherent in the same 1.5-mi neighbourhood ({b} band − {a} band; + = {b} deeper): "
                     f"median {f(ps['med_sep_ft'], 0)} ft (IQR {f(ps['p25_sep_ft'], 0)} … {f(ps['p75_sep_ft'], 0)}), {f(ps['n_hoods'])} neighbourhoods; "
                     f"merged (&lt; 100 ft) in {f(ps['share_within_100ft'], pct=True)}; stack order inverted in {f(ps['share_inverted'], pct=True)}. "
                     f"TX {f(ps['n_tx'])} / median {f(ps['med_sep_ft_tx'], 0)} ft / merged {f(ps['share_within_100ft_tx'], pct=True)}; "
                     f"NM {f(ps['n_nm'])} / {f(ps['med_sep_ft_nm'], 0)} ft / {f(ps['share_within_100ft_nm'], pct=True)}.</p>")
        else:
            p.append("<p>Local depth separation: fewer than 30 neighbourhoods with both bands coherent.</p>")
        rw = pe["raw"]
        p.append(bq._table(["D9 cohort", "n", "median 12-mo oil / kft", "median 12-mo GOR scf/bbl", "median TVD ft", "median lateral ft", "NM share",
                            "share with other bench's cohort well ≤ 1.5 mi", "median nearest other-bench well, mi"],
                           [[x, f(rw[x]["n_cohort"]), f(rw[x]["med_oil12_kft"], 0), f(rw[x]["med_gor12"], 0), f(rw[x]["med_tvd_ft"], 0), f(rw[x]["med_lateral_ft"], 0),
                             f(rw[x]["share_nm"], pct=True), f(pe.get(f"coloc_{x}", {}).get("share_within_1p5mi"), pct=True), f(pe.get(f"coloc_{x}", {}).get("median_nn_mi"), 2)] for x in (a, b)]))
        p.append(f"<p><b>Within-location contrasts</b> ({b} relative to {a}), D9 cohort, 5-mi block FE + first-production-year FE, only blocks holding both benches; "
                 f"90 % CI = bootstrap over blocks ({N_BOOT} draws). This is the D33 test: a difference inside area-to-area noise argues for one pool.</p>")
        p.append(bq._table(["measure", f"{b} / {a}", "90 % CI", "blocks with both", f"n {a}", f"n {b}"],
                           [[lab, f(pe[k]["ratio"], 3), f"{f(pe[k]['ci90'][0], 3)} … {f(pe[k]['ci90'][1], 3)}", f(pe[k]["n_blocks_both"]), f(pe[k]["n_a"]), f(pe[k]["n_b"])]
                            for k, lab in (("oil12_kft", "12-mo oil per 1,000 ft"), ("gor12", "12-mo GOR"), ("cum24_over_cum12", "cum-24 / cum-12 oil (shape)"))]))
        p.append(f"<img src=\"{ratio_img}\" style='max-width:700px'>")
    # --- asks
    p.append("<h2 id=asks>5. Gate asks</h2><ol>" + "".join(f"<li>{x}</li>" for x in s["asks"]) + "</ol>")
    p.append("</body></html>")
    out.write_text("".join(p), encoding="utf-8")
    return out


# ----------------------------------------------------------------------------
# Orchestration
# ----------------------------------------------------------------------------


def build(scored: pd.DataFrame, family_name: str, out_dir: Path, pool_dir: Path | list[Path], verdicts: dict[str, str],
          excluded_ids: set[str], meta: dict[str, Any], basin: str = bq.BASIN) -> dict[str, Any]:
    """Everything after the pull + consensus scoring (pure apart from file writes). `basin` (step 19): the bench pages' state-line
    check and map lines follow it (the Midland has no state line)."""
    family = FAMILIES[family_name]
    out_dir.mkdir(parents=True, exist_ok=True)
    scored = bq.assign_roles(scored)
    # per-bench step-1 pages, unchanged tooling
    bench_summaries = {}
    for bench in family:
        bs = bq.bench_summary(scored, bench, basin)
        bq.render_bench_page(scored, bs, out_dir / f"qc_{bench}.html")
        scored.loc[scored["formation_blueox"] == bench, bq.WELL_COLS].sort_values("api10").to_csv(out_dir / f"wells_{bench}.csv", index=False)
        bench_summaries[bench] = bs
    ruled = qr.apply_rule(scored, verdicts)
    frozen = frozen_pools(pool_dir)
    udir = next(d for d in ([pool_dir] if isinstance(pool_dir, Path) else pool_dir) if (d / "universe.csv").exists())
    universe = pd.read_csv(udir / "universe.csv", dtype={"api10": str})
    seen_ids = set(universe["api10"])
    roles = family_membership(ruled, family, frozen, seen_ids, excluded_ids)
    roles["frozen_tag"] = roles["api10"].map(frozen_tags(pool_dir))
    final = roles[roles["family_role"].isin(["member", "old_churn_kept"])].copy()
    final["box_bench"] = final["family_bench"]
    cols = [c for c in qr.FINAL_COLS if c in final.columns] + ["family_role"]
    for bench in family:
        final[final["box_bench"] == bench].sort_values("api10")[cols].to_csv(out_dir / f"wells_final_{bench}.csv", index=False)
    roles[["api10", "well_name", "operator", "state_code", "formation_blueox", "box_bench", "box_action", "box_reason", "family_role",
           "family_bench", "frozen_pool", "frozen_tag", "first_production_date", "cohort"]].to_csv(out_dir / "family_roles.csv", index=False)

    set_s: dict[str, Any] = {}
    for bench in family:
        t = roles[roles["formation_blueox"] == bench]
        fb = final[final["box_bench"] == bench]
        set_s[bench] = {
            "tagged_live": len(t),
            "member": int(((roles["family_role"] == "member") & (roles["family_bench"] == bench)).sum()),
            "old_churn_kept": int(((roles["family_role"] == "old_churn_kept") & (roles["family_bench"] == bench)).sum()),
            "frozen_elsewhere": int((t["family_role"] == "frozen_elsewhere").sum()),
            "frozen_to": t.loc[t["family_role"] == "frozen_elsewhere", "frozen_pool"].value_counts().to_dict(),
            "frozen_retagged_since": int(((t["family_role"] == "frozen_elsewhere") & (t["frozen_tag"] != t["formation_blueox"])).sum()),
            "frozen_retagged_from": t.loc[(t["family_role"] == "frozen_elsewhere") & (t["frozen_tag"] != t["formation_blueox"]), "frozen_tag"].value_counts().to_dict(),
            "new_ruled_out": int((t["family_role"] == "new_ruled_out").sum()),
            "new_ruled_out_to": t.loc[t["family_role"] == "new_ruled_out", "box_bench"].value_counts().to_dict(),
            "excluded": int((t["family_role"] == "excluded").sum()),
            "joined_from_other_tags": int(((roles["family_role"] == "member") & (roles["family_bench"] == bench) & (roles["formation_blueox"] != bench)).sum()),
            "final": len(fb),
            "final_fp_ge_2016": int(sum(fp >= bq.COHORT_FP_MIN for fp in fb["first_production_date"])),
            "final_cohort": int(fb["cohort"].sum()),
            "final_tvd_suspect": int((fb["box_action"] == "tvd_suspect").sum()),
            "final_witness": int(fb["box_depth_witness"].sum()),
            "final_tx": int((fb["state_code"] == bq.TX_FIPS).sum()),
            "final_nm": int((fb["state_code"] == bq.NM_FIPS).sum()),
        }
    lith = {}
    for bench in family:
        b = scored[(scored["formation_blueox"] == bench) & (scored["cons_status"] == "ambiguous_lith")]
        lith[bench] = {"n": len(b), "to": b["cons_suggest"].value_counts().to_dict()}
    fam_members = final.reset_index(drop=True)
    xy = bq._project_xy_ft(fam_members["mid_lon"].values, fam_members["mid_lat"].values)
    ctx = scored[~scored["formation_blueox"].isin(family) & scored["mid_lon"].notna()]
    poolings, pool_json = [], []
    for a, b in itertools.pairwise(family):
        pe = pooling_evidence(fam_members, a, b, xy)
        ps = next((r for r in bench_summaries[a]["pair_separation"] if r["other"] == b), None)
        ratio_png, n_rb = block_ratio_map(ctx, fam_members, xy, a, b, state_line_lat=bsn.get(basin).state_line_lat)
        pe["n_ratio_blocks"] = n_rb
        poolings.append((pe, ps, ratio_png))
        pool_json.append({"pooling": pe, "pair_sep": ps})
    imgs = {"map": family_map(ctx, fam_members, family, bsn.get(basin).state_line_lat)}
    flags = flag_ledger(ruled, family)
    unc = flags[flags["standing"].str.startswith("uncalibrated")]
    s: dict[str, Any] = {
        **meta, "family": family_name, "benches": list(family), "pool_dir": str(pool_dir) if isinstance(pool_dir, Path) else [str(d) for d in pool_dir], "set": set_s,
        "pooled_final": len(final), "pooled_fp_ge_2016": int(sum(fp >= bq.COHORT_FP_MIN for fp in final["first_production_date"])),
        "pooled_cohort": int(final["cohort"].sum()), "flags": flags.to_dict(orient="records"), "lith": lith,
        "sensitivity": sensitivity(ruled, family), "pairs": pool_json,
        **({"pooling": pool_json[0]["pooling"], "pair_sep": pool_json[0]["pair_sep"], "n_ratio_blocks": pool_json[0]["pooling"]["n_ratio_blocks"]} if pool_json else {}),
        "uncalibrated_flags": int(unc["n"].sum()), "uncalibrated_classes": sorted(set(unc["swap_class"])),
        "bench_summaries": {k: {kk: v[kk] for kk in ("n_prod_hz", "n_tx", "n_nm", "n_cohort", "planned_share", "planned_share_nm", "round_tvd_share",
                                                     "sql23_disagree_share", "cons_flag_n", "cons_flag_share", "cons_lith_n", "cohort_med_oil12_kft", "border_step")}
                            for k, v in bench_summaries.items()},
        "asks": meta.get("asks", []),
    }
    render_family_page(out_dir / "index.html", family_name, family, {**s, "poolings": poolings}, imgs)
    (out_dir / "summary.json").write_text(json.dumps(s, indent=1, default=str), encoding="utf-8")
    return s
