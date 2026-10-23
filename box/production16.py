"""BOX step 16d — the production pieces of the D121 selection of record (r2 on every bench).

  RULES / spec_label(group)     the r2 rules (box/step16.VARIANTS["box_v2s_r2"]) and each group's per-group spec under by_bench
                                (D103: forecast_run.spec stays 'box_v2_wf'); WCA and BS2_S keep a walk-forward haircut (D121 stack)
  evidence_pack(views, ...)     the frozen inputs the build reads (docs/box/step16d-2026-10-23/r2_evidence.json), built ONCE from the
                                16c tuning views: per group, r2 x the PDP-proximity factor exactly as production applies it (oil only,
                                box.prox_pud.decide), per-cutoff package cells, the WCA / BS2_S haircut table from those TUNING cells
                                (D120 §4), and the group's disclosure in the schema erebor reads (hindcast_bias / radius_ranges / tier
                                block) with the thin-control line
  flags(group, disc)            the workup text that travels with each row (pud_forecast.flags), replacing the pre-D121 tier / edge texts

Error convention everywhere: actual / forecast - 1 (negative = the forecast is HIGH). Pure, no DB.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any

import numpy as np
import pandas as pd

from box import acceptance as ac
from box import prox_pud as pp
from box import step16 as s16
from box import step16c as c16

SELECTION = "box_v2s_r2"
RULES = s16.VARIANTS[SELECTION][1]
HAIRCUT_GROUPS: tuple[str, ...] = ("WCA", "BS2_S")
VALIDATED: tuple[str, ...] = c16.VALIDATED
PROVISIONAL: tuple[str, ...] = c16.PROVISIONAL
RING_MI = 5.0
N_BOOT = 1000
SEED = 20261023
HORIZONS = (12, 24, 36, 48)


def spec_label(group: str) -> str:
    return f"{SELECTION}_wf" if group in HAIRCUT_GROUPS else SELECTION


def tier(group: str) -> str:
    return "validated" if group in VALIDATED else "provisional"


# ----------------------------------------------------------------------------
# proximity factor on backtest wells (production's own rule)
# ----------------------------------------------------------------------------


class _AllPrecedent(dict):  # type: ignore[type-arg]
    """Precedent is not a backtest question: every multi-parent backtest well is scored with its factor."""

    def get(self, key: Any, default: Any = None) -> dict[str, int]:
        return {"multi": 10**9, "package": 10**9}


def oil_factors(config_children: pd.DataFrame, factor_table: pd.DataFrame) -> pd.Series:
    """api10 -> the oil factor production applies (D113: multi-parent configurations only; others 1.0)."""
    cfg = config_children.reset_index(drop=True)
    d = pp.decide_all(cfg, pp.haircut_lookup(factor_table), _AllPrecedent())
    f = d["factor"].where(d["outcome"] == "haircut", 1.0).astype(float)
    return pd.Series(f.to_numpy(), index=cfg["api10"].astype(str))


def with_prox(v: pd.DataFrame, factors: pd.Series, base: str = SELECTION, name: str = "r2p") -> pd.DataFrame:
    """`name` predictions = `base` x the oil factor (gas unchanged), every horizon present."""
    v = v.copy()
    f = v["api10"].astype(str).map(factors).fillna(1.0).to_numpy(float)
    v["prox_factor"] = f
    for s in ac.STREAMS:
        for k in HORIZONS:
            col = f"pred_{base}_{s}{k}"
            if col in v:
                v[f"pred_{name}_{s}{k}"] = v[col] * (f if s == "oil" else 1.0)
                if f"actual_{s}{k}" in v:
                    v[f"{name}_err_{s}{k}"] = v[f"actual_{s}{k}"] / v[f"pred_{name}_{s}{k}"] - 1.0
    return v


def cutoff_cells(v: pd.DataFrame, variants: Sequence[str]) -> pd.DataFrame:
    return pd.concat([ac.score_fold(x, str(c), tuple(variants)) for c, x in v.groupby("cutoff")], ignore_index=True)


def walk_forward(v: pd.DataFrame, cells: pd.DataFrame, base: str, name: str) -> pd.DataFrame:
    """D57 on `base`: prediction x (1 + mean package bias at the same stream / horizon over >= 2 earlier cutoffs, >= 30 pkgs)."""
    from box import analog as an

    v = v.copy()
    for s in ac.STREAMS:
        for k in HORIZONS:
            col = f"pred_{base}_{s}{k}"
            if col not in v:
                continue
            hist = cells[(cells.variant == base) & (cells.stream == s) & (cells.horizon == k) & (cells.n_packages >= ac.MIN_PACKAGES)]
            hb = dict(zip(hist["cutoff"].astype(str), hist["pkg_bias"], strict=True))
            h = v["cutoff"].astype(str).map(lambda c, hb=hb: an.walk_forward(hb, c)).astype(float)
            v[f"pred_{name}_{s}{k}"] = v[col] * (1.0 + h)
            if f"actual_{s}{k}" in v:
                v[f"{name}_err_{s}{k}"] = v[f"actual_{s}{k}"] / v[f"pred_{name}_{s}{k}"] - 1.0
    return v


# ----------------------------------------------------------------------------
# disclosure (erebor's schema) + thin-control line
# ----------------------------------------------------------------------------


def _well_bias(v: pd.DataFrame, variant: str, s: str, k: int, mask: pd.Series | None = None) -> tuple[float | None, int]:
    a, p = v[f"actual_{s}{k}"].astype(float), v.get(f"pred_{variant}_{s}{k}")
    if p is None:
        return None, 0
    p = p.astype(float)
    ok = np.isfinite(a) & np.isfinite(p) & (p > 0)
    if mask is not None:
        ok &= mask
    return (float(a[ok].sum() / p[ok].sum() - 1.0) if ok.any() else None), int(ok.sum())


def _boot_range(v: pd.DataFrame, variant: str, s: str, k: int, mask: pd.Series | None, n_boot: int = N_BOOT,
                seed: int = SEED) -> list[float] | None:
    """95 % range of the well-level bias by a 3-mi-block bootstrap (blocks resampled with replacement; D52 blocks)."""
    a, p = v[f"actual_{s}{k}"].astype(float), v.get(f"pred_{variant}_{s}{k}")
    if p is None:
        return None
    p = p.astype(float)
    ok = np.isfinite(a) & np.isfinite(p) & (p > 0)
    if mask is not None:
        ok &= mask
    if ok.sum() < 30:
        return None
    blk = (v.loc[ok, "bx"].astype(str) + ":" + v.loc[ok, "by"].astype(str)).to_numpy()
    aa, pp_ = a[ok].to_numpy(float), p[ok].to_numpy(float)
    ub, inv = np.unique(blk, return_inverse=True)
    sa, sp = np.bincount(inv, aa, len(ub)), np.bincount(inv, pp_, len(ub))
    rng = np.random.default_rng(seed)
    draws = rng.integers(0, len(ub), size=(n_boot, len(ub)))
    b = sa[draws].sum(axis=1) / sp[draws].sum(axis=1) - 1.0
    return [float(np.percentile(b, 2.5)), float(np.percentile(b, 97.5))]


def radius_ranges(views: pd.DataFrame, variant: str, radius_col: str, horizons: Sequence[int] = (12, 24)) -> dict[str, Any]:
    """D69 per radius class (5 mi ring / past 5 mi, by the r2 radius a package's widest member reached): package errors pooled over
    every cutoff — P90 low / P10 high = the 10th / 90th percentile package error."""
    out: dict[str, Any] = {}
    for k in horizons:
        a, p = f"actual_oil{k}", f"pred_{variant}_oil{k}"
        if a not in views or p not in views:
            continue
        x = views.assign(_pkg=views["cutoff"].astype(str) + ":" + views["package"].astype(str))
        e = ac.package_errors(x, "_pkg", a, p)
        r = x.groupby("_pkg")[radius_col].max()
        e["rc"] = np.where(e["_pkg"].map(r) > RING_MI, "past 5 mi", "5 mi ring")
        for rc, g in e.groupby("rc"):
            out[f"{rc}|cum-{k}"] = {"p90_low": float(np.percentile(g["err"], 10)), "p10_high": float(np.percentile(g["err"], 90)),
                                    "packages": len(g), "bias": float(g["err"].mean())}
    return out


def group_evidence(group: str, v: pd.DataFrame, factors: pd.Series) -> dict[str, Any]:
    """One group's frozen evidence: haircut table (WCA / BS2_S), disclosure in erebor's schema, the thin-control line."""
    from box import production as pr

    v = with_prox(v, factors)
    cells = cutoff_cells(v, ("r2p",))
    hcut = None
    rec = "r2p"
    if group in HAIRCUT_GROUPS:
        hcut = pr.haircut_table(cells, variant="r2p")
        v = walk_forward(v, cells, "r2p", "r2p_wf")
        cells = pd.concat([cells, cutoff_cells(v, ("r2p_wf",))], ignore_index=True)
        rec = "r2p_wf"
    thin = pd.to_numeric(v["n_local"], errors="coerce") < s16.LOCAL_MIN_WELLS
    # D99 form (as D100's disclosed bias): every tuning package pooled across the cutoffs; the haircut table keeps D62's
    # per-cutoff >= 30 floor, but a thin group's disclosure must not drop to the one cutoff that clears it
    pooled = c16.pooled_cells(v, tuple(dict.fromkeys(("r2p", rec)))).set_index(["variant", "stream", "horizon"])

    def pooled_bias(var: str, s: str, k: int) -> tuple[float | None, int]:
        if (var, s, k) not in pooled.index:
            return None, 0
        r = pooled.loc[(var, s, k)]
        b = float(r["pkg_bias"])
        return (b if np.isfinite(b) else None), int(r["n_packages"])

    hb: dict[str, Any] = {}
    lines = []
    for s in ac.STREAMS:
        hb[s] = {}
        for k in (12, 24, 36, 48):
            raw_b, raw_n = pooled_bias("r2p", s, k)
            dis_b, dis_n = pooled_bias(rec, s, k)
            hb[s][str(k)] = {"record_variant": spec_label(group), "box_v2_pooled_bias": raw_b, "box_v2_pooled_packages": raw_n,
                             "haircut_factor": hcut[s][k]["factor"] if hcut else 1.0, "disclosed_bias": dis_b, "disclosed_packages": dis_n,
                             "disclosed_basis": "r2 selection x proximity factor" + (" x walk-forward haircut" if hcut else "")
                                                + ", tuning packages pooled over cutoffs 2019-2024 (step 16c)",
                             "holdout_bias": None, "holdout_packages": None, "d99_judged": dis_n >= ac.MIN_PACKAGES}
        for k in (12, 24, 36):
            for scope, m in (("all tuning wells", None), ("thin control (< 3 local wells within 3 mi)", thin)):
                b, n = _well_bias(v, rec, s, k, m)
                if b is not None:
                    lines.append({"label": "tuning (r2 + proximity" + (" + haircut" if hcut else "") + ")", "scope": scope, "stream": s,
                                  "horizon": f"cum-{k}", "packages": n, "bias": b, "range_95": _boot_range(v, rec, s, k, m)})
    latest = cells[(cells.variant == rec) & (cells.stream == "oil") & (cells.horizon == 12)].sort_values("cutoff")
    lv = latest.iloc[-1] if len(latest) else None
    lv_text = (f"latest vintage ({str(lv['cutoff'])[:4]} cutoff cohort, {int(lv['n_packages'])} packages): oil cum-12 "
               f"{float(lv['pkg_bias']):+.1%} vs forecast" if lv is not None else "latest vintage: no cell")
    t_b, t_n = _well_bias(v, rec, "oil", 24, thin)
    t12, t12_n = _well_bias(v, rec, "oil", 12, thin)
    disc = {"hindcast_bias": hb, "radius_ranges": radius_ranges(v, rec, f"{SELECTION}_radius_mi"),
            "radius_ranges_basis": "tuning packages, r2 + proximity" + (" + haircut" if hcut else "") + " (step 16c)",
            "tier": tier(group), "label": f"D121 r2 selection, {tier(group)}",
            "holdout": "none under r2 (D121: owner's-judgment selection; tuning-only evidence, the 2026 cohort is the confirmation)",
            "lead": {"label": "tuning (r2 + proximity)", "scope": "all tuning wells"}, "lines": lines, "latest_vintage_text": lv_text,
            "thin_control": {"oil_cum12_bias": t12, "oil_cum12_wells": t12_n, "oil_cum24_bias": t_b, "oil_cum24_wells": t_n},
            "selection": {"rules": "same bench > distance; lateral = Cui translation, analogs 5,000-15,000 ft; per ring give up the count "
                                   "(>= 5), then admit standalone wells; measured spacing (D119)", "decision": "D121"},
            "error_convention": "actual / forecast - 1 (negative = forecast HIGH)"}
    return {"group": group, "spec": spec_label(group), "tier": tier(group), "haircut": hcut, "disclosure": disc}


def flags(group: str, disc: Mapping[str, Any]) -> list[str]:
    """Per-row workup text (pud_forecast.flags): the tier + disclosed oil bias + the thin-control line. Per-location selection
    provenance (relaxations, Cui) travels in the row's own selection flags."""
    o = disc["hindcast_bias"]["oil"]["12"]
    t = disc["thin_control"]
    b = o.get("disclosed_bias")
    tc24 = t.get("oil_cum24_bias")
    return [f"D121 r2 selection ({tier(group)}) {group}: tuning oil cum-12 {b:+.1%} ({o['disclosed_basis']})" if b is not None
            else f"D121 r2 selection ({tier(group)}) {group}",
            (f"thin-control caveat: where < 3 producers lie within 3 mi, tuning oil ran {tc24:+.1%} at cum-24 "
             f"({t['oil_cum24_wells']} wells); forecast NOT adjusted") if tc24 is not None else "thin-control caveat: too few wells to state",
            disc["latest_vintage_text"]]
