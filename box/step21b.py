"""BOX step 21b — Midland tuning-fold scoring under the FROZEN pre-registration (box/step21.DEFINITION digest 505439b9, frozen
SHA 501d799; docs/box/step21a-2026-10-31/PREREGISTRATION.md). Pure, DB-free. Written AFTER the freeze and checked against
PREREGISTRATION §4-§7 as written before it ran (the 16c pattern); every piece below names the paragraph it implements and
reuses the code of record it points at, unchanged.

  §4 proximity factor   children = the harness's scored TUNING wells (all six cutoffs; held-out packages were dropped by the
                        harness before anything was written), configuration from the drilled-child links (box/step21_prox
                        .by_depth, revision 3), l_rel = ln(actual oil24 / as-of mid_r2 oil24) minus the (group, cutoff) mean
                        (box/prox_validate.l_rel), fit per rung k1-k4 (box/prox_validate.fit's rule), factor = exp(mean
                        l_rel), usable at >= 30 children. APPLIED as production applies it (Michael 2026-11-01, 21b: the §4
                        ambiguity "first rung" vs "as in the step-16 level work" resolved to the latter): box/production16
                        .oil_factors = box/prox_pud.decide, class x count x flank -> class x count -> class (D113 option (a);
                        the bench-pair rung k1 is fitted and reported, never applied), multi-parent only, precedent ignored,
                        oil only, uniform scale. Scored wells and production sticks read the identical factor.
  §4 treatments         mid_r2p = mid_r2 x factor (oil; gas untouched); mid_r2p_wf = mid_r2p x the group's OWN walk-forward
                        haircut (box/acceptance.apply_walk_forward on mid_r2p's own cells, per stream, >= 2 earlier judged).
  §5 record treatment   box/step21.record_treatment on the EXPECTED SCORED holdout over the walk-forward cutoffs (21a holdout
                        COUNTS x the share of each cutoff's tuning packages mid_r2p_wf scored: box/tune15_report
                        .expected_holdout, the step-15 §2 correction); D106 guard per stream (box/production_run9.guard_table /
                        guard_tail on the D62-style table of the record base and the D92 g(48) of mid_r2's months).
  §6 D99                cells = horizons whose expected scored pooled holdout under the record treatment reaches 30; intervals
                        = box/rehearse9b.consistency (2,000 draws, seed 5) on the TUNING packages, frozen with a sha256.
Sensitivities (reported, never the record): the Delaware D113 table on the same wells; a nearest-gap rung (FINDINGS §5 Q1).
"""

from __future__ import annotations

import hashlib
from collections.abc import Mapping, Sequence
from typing import Any

import numpy as np
import pandas as pd

from box import acceptance as ac
from box import dev_factor_report as dfr
from box import holdout as ho
from box import prox_dose as pdz
from box import prox_validate as pv
from box import step21 as st
from box import step21_prox as sp

RAW, PROX, PROX_WF = st.RAW, st.PROX, st.PROX_WF
METRIC = "oil24"  # §4: cum-24
RUNGS = pv.RUNGS  # k1 bench pair x count, k2 class x count x flank, k3 class x count, k4 class
GAP_RUNG = "kg"  # sensitivity only: class x count x nearest-parent gap band (box/prox_dose.geom_band), tried before k2
CONFIG_COLS = ("config_class", "n_parents_total", "config", *(f"{p}_{c}" for c in pdz.ENVELOPE for p in ("n", "flanked", "pb", "dh", "dv", "band")))


# ----------------------------------------------------------------------------
# harness frames
# ----------------------------------------------------------------------------


def frames(views: Mapping[str, pd.DataFrame]) -> pd.DataFrame:
    """box/rehearse9b.load_frames on in-memory views: one frame, 3-mi block of each midpoint, pkg = '<cutoff>:<package>'."""
    v = pd.concat([x.assign(cutoff=c) for c, x in sorted(views.items())], ignore_index=True)
    x, y = dfr._xy(v["mid_lon"], v["mid_lat"])
    v["bx"], v["by"] = ho.blocks(np.asarray(x), np.asarray(y))
    v["pkg"] = v["cutoff"].astype(str) + ":" + v["package"].astype(str)
    return v


def f_from_view(view: pd.DataFrame, months: np.ndarray, stream: str, k: int, tol: float = 1e-9) -> tuple[float, float]:
    """F(k) of a cutoff recovered from the harness: pred_mid_r2_<s><k> / cumsum(observed months)[k-1] over the wells with both.
    Returns (F, max relative spread across wells). The spread is the observer's identity check: it must be ~0."""
    c = np.cumsum(np.asarray(months, float), axis=1)[:, k - 1]
    p = view[f"pred_{RAW}_{stream}{k}"].to_numpy(float)
    ok = np.isfinite(c) & np.isfinite(p) & (c > 0)
    if not ok.any():
        return float("nan"), float("nan")
    r = p[ok] / c[ok]
    f = float(np.median(r))
    spread = float(np.max(np.abs(r / f - 1.0)))
    if spread > tol:
        raise ValueError(f"{stream}{k}: F(k) differs across wells by {spread:.2e} — observed months are not the harness's")
    return f, spread


# ----------------------------------------------------------------------------
# §4 proximity factor
# ----------------------------------------------------------------------------


def child_frame(v: pd.DataFrame, cfg: pd.DataFrame, group: str) -> pd.DataFrame:
    """Scored tuning wells of one group (every cutoff) + their drilled-child configuration (cfg indexed by api10: box/prox_dose
    .configuration on by-depth links + bench). l_oil24 = ln(actual / mid_r2), clipped as box/prox_dose.log_ratios clips."""
    d = v[["api10", "cutoff", "package", "pkg", "bx", "by", "lateral_ft", *[c for c in v.columns if c.startswith(("actual_oil", f"pred_{RAW}_oil"))]]].copy()
    d["bench_group"] = group
    d["block"] = d["bx"].astype(str) + ":" + d["by"].astype(str)
    a, p = d[f"actual_{METRIC}"].astype(float), d[f"pred_{RAW}_{METRIC}"].astype(float)
    ok = (a > 0) & (p > 0)
    d[f"l_{METRIC}"] = np.where(ok, np.log(a.where(ok) / p.where(ok)), np.nan)
    d[f"l_{METRIC}"] = d[f"l_{METRIC}"].clip(*pdz.L_CLIP)
    cols = [c for c in CONFIG_COLS if c in cfg.columns] + ["bench"]
    d = d.join(cfg[cols], on="api10")
    d["has_config_row"] = d["api10"].isin(cfg.index)
    return d


def ladder(d: pd.DataFrame, gap_rung: bool = False) -> pd.DataFrame:
    """box/prox_validate.ladder_keys; with `gap_rung`, the sensitivity rung kg = '<class>|<count>|<nearest-gap band>' for a
    single-class configuration (box/prox_dose's `config`), None for mixed / single / unexposed."""
    k = pv.ladder_keys(d)
    if gap_rung:
        multi = sp.is_multi(d) & (d["config_class"] != "mixed")
        k.insert(0, GAP_RUNG, [c if m and isinstance(c, str) else None for c, m in zip(d["config"], multi, strict=True)])
    return k


def fit_table(d: pd.DataFrame, gap_rung: bool = False, min_n: int = pv.RUNG_MIN) -> pd.DataFrame:
    """The Midland factor table: one row per rung x key with n_train, factor = exp(mean l_rel), usable = n_train >= min_n (the
    columns of docs/box/prox-2026-10-19/haircut_table_candidate.csv, so box/prox_pud.haircut_lookup reads it)."""
    keys = ladder(d, gap_rung)
    lr = pv.l_rel(d, METRIC)
    ok = lr.notna()
    rows = []
    for rung in keys.columns:
        g = lr[ok].groupby(keys.loc[ok, rung]).agg(["mean", "size"])
        for key, r in g.iterrows():
            rows.append({"rung": rung, "key": key, "n_train": int(r["size"]), "factor": float(np.exp(r["mean"])), "usable": bool(r["size"] >= min_n)})
    return pd.DataFrame(rows, columns=["rung", "key", "n_train", "factor", "usable"])


def assign(d: pd.DataFrame, table: pd.DataFrame, rungs: Sequence[str] = RUNGS, gap_rung: bool = False, multi_only: bool = True) -> pd.DataFrame:
    """Per scored well: factor, key, rung — the first usable rung in `rungs` order (box/prox_validate.assign's rule); option (a):
    a well that is not multi-parent carries 1.0 (rung 'not multi'); a multi-parent well with no usable rung carries 1.0 ('unfit')."""
    keys = ladder(d, gap_rung)
    order = ([GAP_RUNG] if gap_rung else []) + list(rungs)
    use = {(r.rung, r.key): r.factor for r in table[table["usable"].astype(bool)].itertuples()}
    multi = sp.is_multi(d)
    out = []
    for i in d.index:
        if multi_only and not multi[i]:
            out.append((1.0, None, "not multi"))
            continue
        got = (1.0, None, "unfit")
        for r in order:
            key = keys.at[i, r]
            if isinstance(key, str) and (r, key) in use:
                got = (use[(r, key)], key, r)
                break
        out.append(got)
    return pd.DataFrame(out, columns=["factor", "key", "rung"], index=d.index)


APPLIED_RUNGS = ("k2", "k3", "k4")  # box/prox_pud.decide's ladder


def record_factor(d: pd.DataFrame, table: pd.DataFrame) -> pd.Series:
    """§4 as production applies it: box/production16.oil_factors (box/prox_pud.decide on `table`, precedent ignored, multi-parent
    only; others 1.0), keyed by api10. `d` = child_frame rows (one per scored well)."""
    from box import production16 as p16

    cfg = d.drop_duplicates("api10").reset_index(drop=True)
    unfit = unfit_mask(cfg, table)
    out = pd.Series(1.0, index=cfg["api10"].astype(str))
    if (~unfit).any():
        out.update(p16.oil_factors(cfg[~unfit.to_numpy()].reset_index(drop=True), table))
    return out


def unfit_mask(cfg: pd.DataFrame, table: pd.DataFrame) -> pd.Series:
    """Multi-parent rows with NO usable key on production's ladder (box/prox_pud.decide would raise): reported as 'unfit', factor
    1.0, never silently fitted — a table that leaves any is a gate item."""
    a = assign(cfg, table, rungs=APPLIED_RUNGS)
    return (a["rung"] == "unfit").reindex(cfg.index)


def record_rung(d: pd.DataFrame, table: pd.DataFrame) -> pd.DataFrame:
    """The key / rung box/prox_pud.decide picks per scored well (for the tables; the factor itself comes from record_factor)."""
    return assign(d, table, rungs=APPLIED_RUNGS)


def delaware_factor(d: pd.DataFrame, delaware_table: pd.DataFrame) -> pd.Series:
    """Sensitivity: the Delaware D113 table on the same wells, the same production lookup."""
    return record_factor(d, delaware_table)


# ----------------------------------------------------------------------------
# §4 treatments + cells
# ----------------------------------------------------------------------------


def add_prox(views: Mapping[str, pd.DataFrame], factor: Mapping[str, float], name: str = PROX) -> None:
    """In place: pred_<name>_oil<k> = pred_mid_r2_oil<k> x factor(api10) (1.0 when absent); gas = mid_r2's (D113: untouched)."""
    for view in views.values():
        f = view["api10"].map(factor).fillna(1.0).to_numpy(float)
        for s in ac.STREAMS:
            for k in ac.HORIZONS:
                col = f"pred_{RAW}_{s}{k}"
                if col not in view or f"actual_{s}{k}" not in view:
                    continue
                pred = view[col].to_numpy(float) * (f if s == "oil" else 1.0)
                view[f"pred_{name}_{s}{k}"] = pred
                view[f"{name}_err_{s}{k}"] = ac.hc.pct_error(view[f"actual_{s}{k}"].to_numpy(float), pred)


def score(views: Mapping[str, pd.DataFrame], variants: Sequence[str]) -> pd.DataFrame:
    """Per-cutoff D53 cells (box/acceptance.score_fold, unchanged) for `variants`."""
    return pd.concat([ac.score_fold(v, c, tuple(variants)) for c, v in sorted(views.items())], ignore_index=True)


def walk_forward(cells: pd.DataFrame, views: Mapping[str, pd.DataFrame], base: str = PROX) -> tuple[pd.DataFrame, list[dict[str, Any]]]:
    """<base>_wf: box/acceptance.apply_walk_forward on base's own tuning cells (D57 / D94). Returns (wf cells, haircut log)."""
    log: list[dict[str, Any]] = []
    out = ac.apply_walk_forward(cells, dict(views), None, log=log, bases=(base,))
    return pd.concat(out, ignore_index=True), log


# ----------------------------------------------------------------------------
# §5 record treatment, D106 guard
# ----------------------------------------------------------------------------


def expected_holdout(cells: pd.DataFrame, variant: str, counts: pd.DataFrame) -> pd.DataFrame:
    """box/tune15_report.expected_holdout (unchanged) on the 21a package COUNTS of one group (cutoff, horizon, n_tuning, n_holdout)."""
    from box import tune15_report as t15

    return t15.expected_holdout(cells, variant, counts)


def record_treatment(cells: pd.DataFrame, counts: pd.DataFrame) -> dict[str, Any]:
    """§5: box/step21.record_treatment on mid_r2p_wf's expected scored holdout at cum-12 / cum-24 (its cells exist only at the
    cutoffs that carry a walk-forward haircut, so the sum runs over exactly those)."""
    eh = expected_holdout(cells, PROX_WF, counts)
    pooled = {int(r.horizon): float(r.expected_holdout_scored) for r in eh.itertuples()}
    return {"record": st.record_treatment({k: int(np.floor(v + 1e-9)) for k, v in pooled.items()}), "expected_wf": pooled, "table": eh}


def d62_table(cells: pd.DataFrame, variant: str) -> pd.DataFrame:
    """box/tune9a_report.haircut_table on `variant` (package-weighted mean bias over judged tuning cells, per stream x horizon)."""
    from box import tune9a_report as t9

    return t9.haircut_table(cells, variant=variant)


def guard(tab: pd.DataFrame, months: Mapping[str, np.ndarray]) -> dict[str, Any]:
    """D106 per stream on a D62-style table: box/production_run9.guard_table (cum-k factors monotone within 0.01) and guard_tail
    (the MEDIAN location's D92 g(48) in [0.6, 1.2]) on the uptime-free months (`months[stream]`: [locations, >= 48])."""
    from box import production as pr
    from box import production_run9 as p9

    out: dict[str, Any] = {}
    for s in ac.STREAMS:
        t = tab[(tab.stream == s) & np.isfinite(tab.factor.astype(float))]
        if len(t) < 2:
            out[s] = {"refused": True, "reasons": ["fewer than two judged horizons"], "factors": {}, "g48": None}
            continue
        knots = {int(k): {"factor": float(f)} for k, f in zip(t.horizon, t.factor, strict=True)}
        reasons = p9.guard_table({s: knots})
        g = []
        for m in np.asarray(months[s], float):
            if not np.isfinite(m[:48]).all() or m[:48].sum() <= 0:
                continue
            try:
                _, info = pr.apply_haircut_c1(m[:48], knots)
            except ValueError:
                continue
            g.append(info["g_tail"])
        r2, stat = p9.guard_tail({s: np.array(g)}) if g else ([f"{s}: no location to evaluate g(48)"], {s: None})
        reasons += r2
        out[s] = {"refused": bool(reasons), "reasons": reasons, "factors": {k: v["factor"] for k, v in knots.items()}, "g48": stat[s]}
    return out


# ----------------------------------------------------------------------------
# §6 D99
# ----------------------------------------------------------------------------


def d99(v: pd.DataFrame, variant: str, horizons: Sequence[int], n_draws: int = 2000, seed: int = 5) -> dict[str, Any]:
    """§6: box/rehearse9b.consistency on the TUNING packages of `variant` for the (stream, k) cells at `horizons` (oil AND gas),
    plus every scoreable 12 / 24 / 36 cell for reference. Returns interval tables and the pass-rate-by-scale table."""
    from box import rehearse9b as r9
    from box import tune15_report as t15

    t = r9.package_table(v, variant)
    cand = [(s, k) for s in ac.STREAMS for k in st.HORIZONS_JUDGEABLE if "box_a" in t["sums"].get((s, k), {}) and np.isfinite(t["sums"][(s, k)]["box_a"]).any()]
    ivl, _ = r9.consistency(t, cand, n_draws=n_draws, seed=seed) if cand else (pd.DataFrame(columns=["stream", "horizon", "tuning_bias", "interval_lo", "interval_hi"]), None)
    ivl["d99_cell"] = ivl["horizon"].isin(list(horizons))
    rate = (r9.consistency(t, [(s, k) for s in ac.STREAMS for k in horizons], n_draws=n_draws, seed=seed)[1] if horizons
            else pd.DataFrame({"scale": [0.85, 0.90, 1.0, 1.10, 1.15], "pass_rate": np.nan}))
    return {"table": t, "pooled": t15.pooled(t), "intervals": ivl, "pass_rate": rate}


def sha256_text(s: str) -> str:
    return hashlib.sha256(s.encode("utf-8")).hexdigest()


def frozen_intervals_csv(rows: pd.DataFrame) -> str:
    """Canonical CSV text of the frozen D99 intervals (LF, fixed column order, 12 significant digits) — the bytes the sha256 pins."""
    cols = ["group", "treatment", "role", "stream", "horizon", "d99_cell", "tuning_bias", "interval_lo", "interval_hi"]
    r = rows[cols].sort_values(["group", "role", "stream", "horizon"]).reset_index(drop=True)
    return r.to_csv(index=False, lineterminator="\n", float_format="%.12g")
