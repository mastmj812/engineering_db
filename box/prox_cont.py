"""BOX step 24 — continuous proximity factor (pure, no DB). Pre-registered in
docs/box/prox-continuous-2026-11-02/PREREGISTRATION.md (merged 2026-11-02, eng_db #213 = the timestamp); this module is the
DEFINITION the freeze (gate 24a, §11) pins. Nothing here reads the warehouse; the script feeds it the §1 caches.

Model (§2). A parent at (dh, dz) on side s — same (|dz| <= 150 ft), below (dz > 150: parent deeper) or above — has
    d_eff = sqrt(dh^2 + (a_s * dz)^2)   (a_same = 0; a_below, a_above fitted)
    F(d)  = F_min + (1 - F_min) / (1 + (d50 / d)^k)   log-logistic, monotone, F -> 1 as d -> inf, F(0) = F_min.
Fitted in stages on SINGLE-parent children: A lateral (same side) -> B stack (below / above separately, dh <= 400 ft, on dv)
-> C one surface (a_below, a_above with stage A's curve held). Check C2 says whether the surface or three curves carry.

Combination (§3), scored on TWO-parent children: R1 worst-only, R2 multiplicative, R3 per-side product (nearest on each of
left / right / above / below), R4 drainage share. R4 is the half-space reading that reproduces the §3 table (single parent
-> F, flanked at F each -> 2F - 1): per axis (lateral, vertical) the mean over its two sides of h = max(2F_side - 1, 0),
unbounded side h = 1, axes multiplied. (The §3 prose "mean over sides of F" taken literally would give 0.9 for a single
parent at 0.8 and contradict its own table; the table is the registered intent — disclosed in the 24a report.)

Level (§5): factor = F_rule / F_mix per (basin, bench group), capped at 1.0 (G3 default). Validation (§4): the 2c rule, P2
also against the incumbent ladder. Checks C1-C8 are computed here, judged nowhere (§7).
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from itertools import pairwise
from typing import Any

import numpy as np
import pandas as pd
from scipy.optimize import least_squares

from box import prox_dose as pdz
from box import prox_study as ps

# ---- registered constants (§1-§5, §9) -------------------------------------------------------------------------------
SAME_DV_FT = 150.0                 # side by depth (21a revision 3, both basins)
UNIVERSE_DV_FT = 1000.0            # step-2 exposure envelope: beyond it F = 1
UNIVERSE_DH_FT = 2640.0
MIN_OVERLAP = ps.MIN_OVERLAP       # 0.30 alongside
PARENT_AGE_DAYS = 365              # drilled side: depleting parent = >= 12 months on at the child's first production
STACK_DH_MAX_FT = 400.0            # stage B population
BOUNDS = {"f_min": (0.3, 1.0), "d50": (100.0, 3000.0), "k": (0.5, 8.0), "a": (0.5, 6.0)}
INIT = {"f_min": 0.8, "d50": 1000.0, "k": 3.0, "a": 2.0}
MIN_CTRL = pdz.MIN_CTRL            # 10: control-mean fallback (bench group, cutoff) -> bench group -> basin
L_CLIP = pdz.L_CLIP
N_BOOT = 1000
SEED = 20261102
CI = (5.0, 95.0)                   # 90 % block-bootstrap interval
MIN_FIT = 30                       # a stage / contest population below this is reported, not fitted
RULES = ("R1", "R2", "R3", "R4")
RULE_DEFAULT = "R3"                # G2: per-side product on a tie
CAP = 1.0                          # G3: the §5 cap kept in v1
METRIC = "oil24"
TEST_CUTOFFS = {"oil24": ("2021-12-01", "2022-12-01", "2023-12-01"),
                "oil12": ("2021-12-01", "2022-12-01", "2023-12-01", "2024-12-01"),
                "oil36": ("2021-12-01", "2022-12-01"), "gas24": ("2021-12-01", "2022-12-01", "2023-12-01")}
MATERIAL = 0.90
P1_BAND = (0.95, 1.05)
P3_TOL = 0.10
P3_SHARE = 0.80
CELL_MIN = 30
CELL_EDGES_FT = (0.0, 400.0, 800.0, 1200.0, 1600.0, 2000.0, 2400.0, np.inf)
C1_SHARE = 0.80
G4_PRECEDENT_FLOOR = 30
G4_PERCENTILE = 2.0
SIDES = ("same", "below", "above")
AXIS_SIDES = ("left", "right", "above", "below")

DEFINITION: dict[str, Any] = {
    "step": "24 continuous proximity factor (docs/box/prox-continuous-2026-11-02/PREREGISTRATION.md, merged eng_db #213)",
    "side_by_depth_ft": SAME_DV_FT, "universe_ft": {"dv": UNIVERSE_DV_FT, "dh": UNIVERSE_DH_FT}, "min_overlap": MIN_OVERLAP,
    "parent_age_days_drilled_side": PARENT_AGE_DAYS, "permit_tvd": "excluded on the drilled side, counted and flagged on the stick side",
    "shielding": "no exemption on either side", "codev": "|age| <= 180 d is never a dose",
    "normalisation": {"reference": "control", "min_ctrl": MIN_CTRL, "fallback": "(bench group, cutoff) -> bench group -> basin",
                      "clip": [float(L_CLIP[0]), float(L_CLIP[1])]},
    "model": {"d_eff": "sqrt(dh^2 + (a_side*dz)^2), a_same = 0", "F": "F_min + (1-F_min)/(1+(d50/d)^k)", "bounds": BOUNDS, "init": INIT,
              "stages": {"A": "single parent, side same -> F_h(dh)", "B": f"single parent, below / above, dh <= {STACK_DH_MAX_FT:.0f} -> F_below(dv), F_above(dv)",
                         "C": "single parent, any -> a_below, a_above with stage A held"},
              "min_fit": MIN_FIT, "fit": "scipy least_squares on l_rel vs ln F, bounded"},
    "rules": {"R1": "worst-only min F", "R2": "product of all F", "R3": "product over left/right/above/below of the nearest parent's F",
              "R4": "drainage share: per axis mean over sides of max(2F-1, 0), unbounded side 1, axes multiplied"},
    "contest": {"population": "exactly two depleting parents in the universe", "statistic": "RMS of l_rel - ln F_rule",
                "winner": "lowest RMS when its improvement over R1 excludes zero at 90 %, else R3", "default": RULE_DEFAULT},
    "level": {"factor": "F_rule / F_mix per basin x BOX bench", "cap": CAP},
    "c2": {"cross_validation": "blocked, K folds", "k_folds": 5},
    "validation": {"metric": METRIC, "test_cutoffs": TEST_CUTOFFS, "P1": {"material": MATERIAL, "band": P1_BAND},
                   "P2": {"cells": "side pattern x 400-ft bin of nearest d_eff", "cell_min": CELL_MIN, "edges": list(CELL_EDGES_FT[:-1]),
                          "beats": ["no haircut", "incumbent ladder"]},
                   "P3": {"tol": P3_TOL, "share": P3_SHARE}, "verdict": "P1 and P2 and P3 per basin"},
    "bootstrap": {"blocks_ft": "3-mi (box.dev_factor.blocks)", "n": N_BOOT, "seed": SEED, "ci": CI},
    "checks": {"C1": f"{C1_SHARE:.0%} of >= {MIN_FIT}-child bins inside the P5-P95 band", "C2": "three curves vs surface RMS improvement excludes zero at 90 %",
               "C3": "bench-pair residuals (>= 30 children) outside +-10 % named", "C4": "F_min, d50 at cum-12 / 24 / 36",
               "C5": "residual by parent age / cum bins", "C6": "Delaware vs Midland parameters", "C7": "Pad C 233 factors",
               "C8": "walk-forward residual on unexposed test children (F_applied = 1)"},
    "gate_defaults": {"G1": "whatever C2 says", "G2": RULE_DEFAULT, "G3": "cap kept", "G4": "incumbent precedent; geometry key reported",
                      "G5": "no bench-pair offset", "G6": "score now, adopt at step 23"},
    "g4_candidate": {"floor": G4_PRECEDENT_FLOOR, "percentile": G4_PERCENTILE, "key": "side pattern (sides present, flanked)"},
}


DIGEST = "4c140f6de592db3e754e0479d04d592388a5019832b1f38eea226629d9c3d91d"  # registered 2026-11-02 (draft, pre-freeze); gate 24a stamps the SHA


def canonical() -> str:
    return json.dumps(DEFINITION, sort_keys=True, separators=(",", ":"), default=float)


def digest() -> str:
    return hashlib.sha256(canonical().encode("utf-8")).hexdigest()


# ---- geometry ------------------------------------------------------------------------------------------------------
def side_of(dz_ft: np.ndarray, same_dv: float = SAME_DV_FT) -> np.ndarray:
    """same within `same_dv` vertically, below when the parent is deeper (dz > 0), else above."""
    dz = np.asarray(dz_ft, float)
    return np.where(np.abs(dz) <= same_dv, "same", np.where(dz > 0, "below", "above"))


def axis_side(side: np.ndarray, dxy_ft: np.ndarray) -> np.ndarray:
    """The R3 / R4 side: a same-depth parent is left (dxy > 0) or right; a stack parent is above or below."""
    s = np.asarray(side, dtype=object)
    lat = np.where(np.asarray(dxy_ft, float) > 0, "left", "right")
    return np.where(s == "same", lat, s).astype(object)


def d_eff(dh_ft: np.ndarray, dz_ft: np.ndarray, side: np.ndarray, a_below: float, a_above: float) -> np.ndarray:
    dh, dz = np.asarray(dh_ft, float), np.asarray(dz_ft, float)
    a = np.where(side == "below", a_below, np.where(side == "above", a_above, 0.0))
    return np.hypot(dh, a * dz)


def F(d: np.ndarray, f_min: float, d50: float, k: float) -> np.ndarray:
    d = np.asarray(d, float)
    with np.errstate(divide="ignore", over="ignore"):
        ratio = np.where(d > 0, (d50 / np.where(d > 0, d, 1.0)) ** k, np.inf)
    return f_min + (1.0 - f_min) / (1.0 + ratio)


@dataclass(frozen=True)
class Curve:
    f_min: float
    d50: float
    k: float

    def __call__(self, d: np.ndarray) -> np.ndarray:
        return F(d, self.f_min, self.d50, self.k)


@dataclass(frozen=True)
class Model:
    """`surface`: one curve in d_eff with a_below / a_above. Otherwise three curves, each side on its own (same on dh,
    below / above on dv) — the C2-fail representation."""
    curve: Curve
    a_below: float = 1.0
    a_above: float = 1.0
    below: Curve | None = None
    above: Curve | None = None

    @property
    def surface(self) -> bool:
        return self.below is None and self.above is None

    def distance(self, dh_ft: np.ndarray, dz_ft: np.ndarray, side: np.ndarray) -> np.ndarray:
        if self.surface:
            return d_eff(dh_ft, dz_ft, side, self.a_below, self.a_above)
        return np.where(side == "same", np.asarray(dh_ft, float), np.abs(np.asarray(dz_ft, float)))

    def factor(self, dh_ft: np.ndarray, dz_ft: np.ndarray, side: np.ndarray) -> np.ndarray:
        d = self.distance(dh_ft, dz_ft, side)
        if self.surface:
            return self.curve(d)
        assert self.below is not None and self.above is not None
        return np.where(side == "same", self.curve(d), np.where(side == "below", self.below(d), self.above(d)))

    def as_dict(self) -> dict[str, Any]:
        out: dict[str, Any] = {"surface": self.surface, "f_min": self.curve.f_min, "d50": self.curve.d50, "k": self.curve.k,
                               "a_below": self.a_below, "a_above": self.a_above}
        for n, c in (("below", self.below), ("above", self.above)):
            if c is not None:
                out |= {f"{n}_f_min": c.f_min, f"{n}_d50": c.d50, f"{n}_k": c.k}
        return out


# ---- frames --------------------------------------------------------------------------------------------------------
def parents(links: pd.DataFrame, drilled: bool = True) -> pd.DataFrame:
    """The parents that count (§1): rel 'parent', >= 30 % alongside, inside the universe; drilled side drops permit TVDs
    (counted + flagged on the stick side); no shielding exemption. Adds side, axis side, dv."""
    q = links[(links["rel"] == "parent") & (links["overlap"] >= MIN_OVERLAP)]
    if drilled:
        q = q[(q["age_days"] >= PARENT_AGE_DAYS) & ~q["permit"].astype(bool)]
    q = q[(q["dv_ft"] <= UNIVERSE_DV_FT) & (q["dh_ft"] <= UNIVERSE_DH_FT)].copy()
    q["side"] = side_of(q["dz_ft"].to_numpy())
    q["axis_side"] = axis_side(q["side"].to_numpy(), q["dxy_ft"].to_numpy())
    return q


def l_rel(d: pd.DataFrame, metric: str, control: np.ndarray) -> pd.Series:
    """l minus the CONTROL mean of its (bench group, cutoff), falling back by MIN_CTRL to bench group, then all controls."""
    l = d[f"l_{metric}"]
    ok = l.notna().to_numpy() & np.asarray(control, bool)
    m_gc = l[ok].groupby([d.loc[ok, "bench_group"], d.loc[ok, "cutoff"]]).agg(["mean", "size"])
    m_g = l[ok].groupby(d.loc[ok, "bench_group"]).agg(["mean", "size"])
    m_all = float(l[ok].mean()) if ok.any() else 0.0
    base = []
    for g, c in zip(d["bench_group"], d["cutoff"], strict=True):
        if (g, c) in m_gc.index and m_gc.at[(g, c), "size"] >= MIN_CTRL:
            base.append(m_gc.at[(g, c), "mean"])
        elif g in m_g.index and m_g.at[g, "size"] >= MIN_CTRL:
            base.append(m_g.at[g, "mean"])
        else:
            base.append(m_all)
    return l - np.array(base, float)


def control_mask(d: pd.DataFrame, links: pd.DataFrame) -> np.ndarray:
    """Control = no depleting, young, permit or shielded parent inside the universe (step 2's definition)."""
    near = links[(links["dv_ft"] <= UNIVERSE_DV_FT) & (links["dh_ft"] <= UNIVERSE_DH_FT) & (links["overlap"] >= MIN_OVERLAP)]
    touched = set(near.loc[near["rel"].isin(["parent", "young"]), "child"])
    return ~d["api10"].isin(touched).to_numpy()


def count_parents(d: pd.DataFrame, par: pd.DataFrame) -> pd.Series:
    n = par.groupby("child")["parent"].nunique()
    return n.reindex(d["api10"]).fillna(0).astype(int).set_axis(d.index)


def single_frame(d: pd.DataFrame, par: pd.DataFrame, lr: pd.Series) -> pd.DataFrame:
    """Children with exactly one counting parent: its geometry + the child's l_rel and block."""
    n = count_parents(d, par)
    one = d[(n == 1).to_numpy() & lr.notna().to_numpy()]
    p = par.drop_duplicates("child").set_index("child").reindex(one["api10"])
    return pd.DataFrame({"api10": one["api10"].to_numpy(), "bench_group": one["bench_group"].to_numpy(), "block": one["block"].to_numpy(),
                         "l_rel": lr[one.index].to_numpy(), "dh_ft": p["dh_ft"].to_numpy(), "dz_ft": p["dz_ft"].to_numpy(),
                         "dv_ft": p["dv_ft"].to_numpy(), "side": p["side"].to_numpy(), "axis_side": p["axis_side"].to_numpy(),
                         "parent_bench": p["parent_bench"].to_numpy(), "age_days": p["age_days"].to_numpy(),
                         "parent_cum_bbl_per_kft": p["parent_cum_bbl_per_kft"].to_numpy() if "parent_cum_bbl_per_kft" in p else np.nan})


# ---- fitting -------------------------------------------------------------------------------------------------------
def _ls(fun, x0: Sequence[float], lo: Sequence[float], hi: Sequence[float], w: np.ndarray | None):
    sw = np.sqrt(w) if w is not None else None
    return least_squares(lambda th: (fun(th) if sw is None else sw * fun(th)), x0=np.asarray(x0, float), bounds=(list(lo), list(hi)), method="trf")


def fit_curve(dist: np.ndarray, lrel: np.ndarray, w: np.ndarray | None = None) -> Curve:
    """Stage A / B: l_rel ~ ln F(d; F_min, d50, k), bounded, weighted by `w` (bootstrap row weights; None = ones)."""
    dist, lrel = np.asarray(dist, float), np.asarray(lrel, float)
    lo = [BOUNDS["f_min"][0], BOUNDS["d50"][0], BOUNDS["k"][0]]
    hi = [BOUNDS["f_min"][1], BOUNDS["d50"][1], BOUNDS["k"][1]]
    res = _ls(lambda th: lrel - np.log(F(dist, *th)), [INIT["f_min"], INIT["d50"], INIT["k"]], lo, hi, w)
    return Curve(*(float(v) for v in res.x))


def fit_aniso(sp: pd.DataFrame, curve: Curve, w: np.ndarray | None = None) -> tuple[float, float]:
    """Stage C: a_below, a_above on every single-parent child with the stage-A curve held."""
    dh, dz, side, lrel = sp["dh_ft"].to_numpy(float), sp["dz_ft"].to_numpy(float), sp["side"].to_numpy(), sp["l_rel"].to_numpy(float)
    res = _ls(lambda th: lrel - np.log(curve(d_eff(dh, dz, side, th[0], th[1]))), [INIT["a"], INIT["a"]],
              [BOUNDS["a"][0]] * 2, [BOUNDS["a"][1]] * 2, w)
    return float(res.x[0]), float(res.x[1])


def fit_stages(sp: pd.DataFrame, w: np.ndarray | None = None) -> dict[str, Any]:
    """A -> B -> C on one single-parent frame (weights optional). Returns the surface Model, the three-curve Model, the
    stage populations, and None curves where a stage is under MIN_FIT."""
    m = {"same": (sp["side"] == "same").to_numpy(), "below": ((sp["side"] == "below") & (sp["dh_ft"] <= STACK_DH_MAX_FT)).to_numpy(),
         "above": ((sp["side"] == "above") & (sp["dh_ft"] <= STACK_DH_MAX_FT)).to_numpy()}
    n = {k: int(v.sum()) for k, v in m.items()}
    ww = (lambda mask: None if w is None else w[mask])
    a = fit_curve(sp.loc[m["same"], "dh_ft"], sp.loc[m["same"], "l_rel"], ww(m["same"])) if n["same"] >= MIN_FIT else None
    b = fit_curve(sp.loc[m["below"], "dv_ft"], sp.loc[m["below"], "l_rel"], ww(m["below"])) if n["below"] >= MIN_FIT else None
    c = fit_curve(sp.loc[m["above"], "dv_ft"], sp.loc[m["above"], "l_rel"], ww(m["above"])) if n["above"] >= MIN_FIT else None
    out: dict[str, Any] = {"n": n, "curve_same": a, "curve_below": b, "curve_above": c, "surface": None, "three": None}
    if a is None:
        return out
    ab, aa = fit_aniso(sp, a, w) if len(sp) >= MIN_FIT else (INIT["a"], INIT["a"])
    out["surface"] = Model(a, ab, aa)
    out["three"] = Model(a, ab, aa, below=b if b is not None else a, above=c if c is not None else a)
    return out


def rms(resid: np.ndarray, w: np.ndarray | None = None) -> float:
    r = np.asarray(resid, float)
    w = np.ones_like(r) if w is None else np.asarray(w, float)
    return float(np.sqrt((w * r * r).sum() / w.sum()))


K_FOLDS = 5                        # C2: blocked cross-validation folds (blocks assigned by seed)


def check_c2(sp: pd.DataFrame, n_boot: int = N_BOOT, seed: int = SEED, k_folds: int = K_FOLDS) -> dict[str, Any]:
    """C2: RMS(surface) - RMS(three curves) on the single-parent frame, OUT OF SAMPLE — blocks split into `k_folds`,
    both models fitted on the other folds, residuals on the held-out fold; the 90 % interval is a block bootstrap of
    those held-out residuals. In-sample the nine-parameter model always wins, so this is the fair reading of §7 C2.
    Surface FAILS when the interval excludes zero (three curves carry). Returns the full-data point fits too."""
    dh, dz, side, lrel = sp["dh_ft"].to_numpy(float), sp["dz_ft"].to_numpy(float), sp["side"].to_numpy(), sp["l_rel"].to_numpy(float)
    blocks = sp["block"].to_numpy()
    ub = np.unique(blocks)
    fold_of = dict(zip(ub, np.random.default_rng(seed).permutation(len(ub)) % k_folds, strict=True))
    folds = np.array([fold_of[b] for b in blocks])
    r_s, r_t = np.full(len(sp), np.nan), np.full(len(sp), np.nan)
    for k in range(k_folds):
        tr, te = folds != k, folds == k
        if te.sum() == 0 or tr.sum() < MIN_FIT:
            continue
        f = fit_stages(sp[tr].reset_index(drop=True))
        if f["surface"] is None:
            continue
        r_s[te] = lrel[te] - np.log(f["surface"].factor(dh[te], dz[te], side[te]))
        r_t[te] = lrel[te] - np.log(f["three"].factor(dh[te], dz[te], side[te]))
    ok = np.isfinite(r_s) & np.isfinite(r_t)
    fits = fit_stages(sp)
    if ok.sum() < MIN_FIT:
        return {"gain": np.nan, "lo": np.nan, "hi": np.nan, "surface_fails": False, "n_cv": int(ok.sum()), "fits": fits}
    W = pdz.boot_weights(blocks[ok], n_boot=n_boot, seed=seed)
    gain = np.array([rms(r_s[ok], W[i]) - rms(r_t[ok], W[i]) for i in range(W.shape[0])])
    lo, hi = np.percentile(gain[1:], CI)
    return {"gain": float(gain[0]), "lo": float(lo), "hi": float(hi), "surface_fails": bool(lo > 0.0), "n_cv": int(ok.sum()), "fits": fits}


def curve_band(sp: pd.DataFrame, which: str, grid: np.ndarray, n_boot: int = N_BOOT, seed: int = SEED) -> pd.DataFrame:
    """P5-P95 band of a stage curve (which = same / below / above) on `grid` ft, refitted per block draw."""
    if which == "same":
        m, col = (sp["side"] == "same").to_numpy(), "dh_ft"
    else:
        m, col = ((sp["side"] == which) & (sp["dh_ft"] <= STACK_DH_MAX_FT)).to_numpy(), "dv_ft"
    x, y = sp.loc[m, col].to_numpy(float), sp.loc[m, "l_rel"].to_numpy(float)
    W = pdz.boot_weights(sp.loc[m, "block"].to_numpy(), n_boot=n_boot, seed=seed)
    curves = np.array([fit_curve(x, y, W[i])(grid) for i in range(W.shape[0])])
    lo, hi = np.percentile(curves[1:], CI, axis=0)
    return pd.DataFrame({"d_ft": grid, "F": curves[0], "lo": lo, "hi": hi, "n": int(m.sum())})


def check_c1(band: pd.DataFrame, bins: pd.DataFrame) -> dict[str, Any]:
    """bins: columns lo_ft, hi_ft, n, effect (exp mean l_rel). Inside = the band at the bin midpoint covers the effect."""
    big = bins[bins["n"] >= MIN_FIT]
    if not len(big):
        return {"n_bins": 0, "share_inside": np.nan, "pass": False}
    mid = ((big["lo_ft"] + big["hi_ft"].clip(upper=UNIVERSE_DH_FT)) / 2).to_numpy(float)
    lo, hi = np.interp(mid, band["d_ft"], band["lo"]), np.interp(mid, band["d_ft"], band["hi"])
    inside = (big["effect"].to_numpy(float) >= lo) & (big["effect"].to_numpy(float) <= hi)
    return {"n_bins": len(big), "share_inside": float(inside.mean()), "pass": bool(inside.mean() >= C1_SHARE)}


# ---- combination rules (§3) ----------------------------------------------------------------------------------------
def combine(f: np.ndarray, axis_side: np.ndarray, rule: str) -> float:
    """One child's parents (F per parent, its left/right/above/below side) -> the child's F under `rule`."""
    f = np.asarray(f, float)
    if len(f) == 0:
        return 1.0
    if rule == "R1":
        return float(f.min())
    if rule == "R2":
        return float(f.prod())
    s = np.asarray(axis_side, dtype=object)
    per_side = {k: float(f[s == k].min()) for k in AXIS_SIDES if (s == k).any()}
    if rule == "R3":
        return float(np.prod(list(per_side.values())))
    if rule == "R4":
        h = {k: max(2.0 * v - 1.0, 0.0) for k, v in per_side.items()}
        lat = (h.get("left", 1.0) + h.get("right", 1.0)) / 2.0
        ver = (h.get("above", 1.0) + h.get("below", 1.0)) / 2.0
        return float(max(lat * ver, 1e-3))
    raise ValueError(rule)


def child_factors(par: pd.DataFrame, model: Model, rules: Sequence[str] = RULES) -> pd.DataFrame:
    """Per child: n parents, nearest d_eff, side pattern, and F under each rule."""
    p = par.copy()
    p["F"] = model.factor(p["dh_ft"].to_numpy(), p["dz_ft"].to_numpy(), p["side"].to_numpy())
    p["d_eff"] = model.distance(p["dh_ft"].to_numpy(), p["dz_ft"].to_numpy(), p["side"].to_numpy())
    rows = []
    for child, g in p.groupby("child", sort=False):
        f, s = g["F"].to_numpy(), g["axis_side"].to_numpy()
        present = sorted(set(s), key=AXIS_SIDES.index)
        row = {"child": child, "n_parents": int(g["parent"].nunique()), "nearest_d_eff": float(g["d_eff"].min()),
               "nearest_F": float(f.min()), "pattern": "+".join(present), "flanked": ("left" in present and "right" in present)}
        for r in rules:
            row[f"F_{r}"] = combine(f, s, r)
        rows.append(row)
    return pd.DataFrame(rows, columns=["child", "n_parents", "nearest_d_eff", "nearest_F", "pattern", "flanked", *[f"F_{r}" for r in rules]])


def contest(two: pd.DataFrame, n_boot: int = N_BOOT, seed: int = SEED) -> dict[str, Any]:
    """`two`: two-parent children with l_rel, block and F_R1..F_R4. RMS per rule, the 90 % interval of each rule's gain
    over R1, the free regression (beta_nearer, beta_farther) and the decision."""
    if len(two) < MIN_FIT:
        return {"n": len(two), "winner": RULE_DEFAULT, "reason": f"fewer than {MIN_FIT} two-parent children; default", "table": pd.DataFrame()}
    W = pdz.boot_weights(two["block"].to_numpy(), n_boot=n_boot, seed=seed)
    lrel = two["l_rel"].to_numpy(float)
    res = {r: lrel - np.log(two[f"F_{r}"].to_numpy(float)) for r in RULES}
    rows = []
    for r in RULES:
        gain = np.array([rms(res["R1"], W[i]) - rms(res[r], W[i]) for i in range(W.shape[0])])
        lo, hi = np.percentile(gain[1:], CI)
        rows.append({"rule": r, "n": len(two), "rms": rms(res[r]), "gain_vs_R1": float(gain[0]), "gain_lo": float(lo), "gain_hi": float(hi),
                     "excludes_zero": bool(lo > 0.0)})
    t = pd.DataFrame(rows)
    best = t.sort_values("rms").iloc[0]
    # §3 as registered: the lowest-RMS rule wins only when its gain over R1 excludes zero; otherwise R3. Read literally, R1
    # itself can never win (its gain over R1 is zero) — reported as such; an amendment is Michael's call (24a report).
    if best["rule"] != "R1" and bool(best["excludes_zero"]):
        winner, reason = str(best["rule"]), f"lowest RMS {best['rule']} with the gain over R1 excluding zero"
    else:
        winner, reason = RULE_DEFAULT, f"lowest RMS {best['rule']}; gain over R1 not resolved at 90 % (or R1 itself), default {RULE_DEFAULT}"
    return {"n": len(two), "winner": winner, "reason": reason, "table": t, "beta": free_regression(two)}


def free_regression(two: pd.DataFrame) -> dict[str, Any]:
    """l_rel = b1 ln F_nearer + b2 ln F_farther (no intercept), all / flanked / same-side."""
    out = {}
    for name, m in (("all", np.ones(len(two), bool)), ("flanked", two["flanked"].to_numpy(bool)), ("same_side", ~two["flanked"].to_numpy(bool))):
        x = np.column_stack([np.log(two.loc[m, "F_near"].to_numpy(float)), np.log(two.loc[m, "F_far"].to_numpy(float))])
        y = two.loc[m, "l_rel"].to_numpy(float)
        if m.sum() < MIN_FIT or not np.isfinite(x).all() or np.linalg.matrix_rank(x) < 2:
            out[name] = {"n": int(m.sum()), "b_near": np.nan, "b_far": np.nan}
            continue
        b, *_ = np.linalg.lstsq(x, y, rcond=None)
        out[name] = {"n": int(m.sum()), "b_near": float(b[0]), "b_far": float(b[1])}
    return out


def two_parent_frame(d: pd.DataFrame, par: pd.DataFrame, lr: pd.Series, model: Model) -> pd.DataFrame:
    n = count_parents(d, par)
    two = d[(n == 2).to_numpy() & lr.notna().to_numpy()]
    cf = child_factors(par[par["child"].isin(two["api10"])], model).set_index("child")
    p = par[par["child"].isin(two["api10"])].copy()
    p["F"] = model.factor(p["dh_ft"].to_numpy(), p["dz_ft"].to_numpy(), p["side"].to_numpy())
    srt = p.sort_values(["child", "F"], ascending=[True, False])  # nearer = lower F
    near = srt.groupby("child")["F"].min()
    far = srt.groupby("child")["F"].max()
    out = cf.reindex(two["api10"].to_numpy()).rename_axis("child").reset_index()
    out["l_rel"], out["block"], out["bench_group"] = lr[two.index].to_numpy(), two["block"].to_numpy(), two["bench_group"].to_numpy()
    out["F_near"], out["F_far"] = near.reindex(out["child"]).to_numpy(), far.reindex(out["child"]).to_numpy()
    return out


# ---- level (§5) and walk-forward (§4) ------------------------------------------------------------------------------
MIX_KEY = "bench"                  # F_mix per basin x BOX bench (the stick side carries a bench, not a harness group)


def f_mix(groups: np.ndarray, f_rule: np.ndarray) -> dict[str, float]:
    """exp(mean ln F_rule) per group over the scored drilled children (unexposed F = 1 included)."""
    x = np.log(np.asarray(f_rule, float))
    return {str(g): float(np.exp(m)) for g, m in pd.Series(x).groupby(np.asarray(groups)).mean().items()}


def applied(f_rule: np.ndarray, groups: np.ndarray, mix: Mapping[str, float], cap: float | None = CAP) -> np.ndarray:
    out = np.asarray(f_rule, float) / np.array([mix.get(str(g), 1.0) for g in groups], float)
    return np.minimum(out, cap) if cap is not None else out


def rule_factor(d: pd.DataFrame, par: pd.DataFrame, model: Model, rule: str) -> pd.DataFrame:
    """Per child of `d`: F under `rule` (1 when unexposed), n parents, nearest d_eff, pattern."""
    cf = child_factors(par[par["child"].isin(d["api10"])], model, rules=(rule,)).set_index("child").reindex(d["api10"])
    out = pd.DataFrame({"F_rule": cf[f"F_{rule}"].fillna(1.0).to_numpy(), "n_parents": cf["n_parents"].fillna(0).astype(int).to_numpy(),
                        "nearest_d_eff": cf["nearest_d_eff"].to_numpy(), "pattern": cf["pattern"].fillna("none").to_numpy()}, index=d.index)
    return out


def cell_of(pattern: np.ndarray, nearest: np.ndarray) -> np.ndarray:
    b = np.digitize(np.nan_to_num(np.asarray(nearest, float), nan=np.inf), CELL_EDGES_FT[1:-1])
    labels = [f"{int(lo)}-{int(hi)}" if np.isfinite(hi) else f"{int(lo)}+" for lo, hi in pairwise(CELL_EDGES_FT)]
    return np.array([f"{p}|{labels[i]}" if p != "none" else "none" for p, i in zip(pattern, b, strict=True)])


def walk_forward(d: pd.DataFrame, links: pd.DataFrame, metric: str, test_cutoffs: Sequence[str], ln_f_inc: pd.Series | None = None,
                 rule: str | None = None, n_boot: int = N_BOOT, seed: int = SEED) -> tuple[pd.DataFrame, list[dict[str, Any]]]:
    """Per test cutoff: fit stages + choose the rule (or use `rule`) on strictly earlier cutoffs, F_mix from them, apply to
    the test children. Returns the test rows (l_rel, r, r0, r_inc, f, cell) and the per-fold fits."""
    par = parents(links, drilled=True)
    ctrl = control_mask(d, links)
    lr = l_rel(d, metric, ctrl)
    parts, fits = [], []
    for c in test_cutoffs:
        tr, te = (d["cutoff"] < c).to_numpy(), ((d["cutoff"] == c).to_numpy() & lr.notna().to_numpy())
        if not te.any() or tr.sum() < MIN_FIT:
            continue
        dtr = d[tr]
        sp = single_frame(dtr, par, lr[tr])
        st = fit_stages(sp)
        if st["surface"] is None:
            continue
        c2 = check_c2(sp, n_boot=max(50, n_boot // 10), seed=seed)
        model = st["three"] if c2["surface_fails"] else st["surface"]
        chosen = rule or contest(two_parent_frame(dtr, par, lr[tr], model), n_boot=max(50, n_boot // 10), seed=seed)["winner"]
        rf_tr = rule_factor(dtr, par, model, chosen)
        mix = f_mix(dtr[MIX_KEY].to_numpy(), rf_tr["F_rule"].to_numpy())
        dte = d[te]
        rf = rule_factor(dte, par, model, chosen)
        f_app = applied(rf["F_rule"].to_numpy(), dte[MIX_KEY].to_numpy(), mix)
        p = pd.DataFrame({"api10": dte["api10"].to_numpy(), "cutoff": c, "block": dte["block"].to_numpy(), "bench_group": dte["bench_group"].to_numpy(),
                          "l_rel": lr[te].to_numpy(), "f": f_app, "F_rule": rf["F_rule"].to_numpy(), "n_parents": rf["n_parents"].to_numpy(),
                          "cell": cell_of(rf["pattern"].to_numpy(), rf["nearest_d_eff"].to_numpy()), "unexposed": (rf["n_parents"].to_numpy() == 0)})
        p["r"], p["r0"] = p["l_rel"] - np.log(p["f"]), p["l_rel"]
        p["r_inc"] = p["l_rel"] - (ln_f_inc.reindex(dte.index).fillna(0.0).to_numpy() if ln_f_inc is not None else 0.0)
        parts.append(p)
        fits.append({"cutoff": c, "n_train": int(tr.sum()), "n_single": len(sp), "rule": chosen, "surface_fails": c2["surface_fails"], **model.as_dict(), "f_mix": mix})
    return (pd.concat(parts, ignore_index=True) if parts else pd.DataFrame()), fits


def _boot_mean(x: np.ndarray, blocks: np.ndarray, n_boot: int, seed: int) -> tuple[float, float, float]:
    W = pdz.boot_weights(blocks, n_boot=n_boot, seed=seed)
    m = (W @ x) / W.sum(axis=1)
    lo, hi = np.percentile(m[1:], CI)
    return float(m[0]), float(lo), float(hi)


def score(p: pd.DataFrame, n_boot: int = N_BOOT, seed: int = SEED) -> dict[str, Any]:
    """P1 / P2 / P3 on the walk-forward rows; P2 against r0 AND r_inc. Also C8 (unexposed test children)."""
    mat = p[p["f"] <= MATERIAL]
    if len(mat):
        m, lo, hi = _boot_mean(mat["r"].to_numpy(float), mat["block"].to_numpy(), n_boot, seed)
        p1_eff, p1_lo, p1_hi = float(np.exp(m)), float(np.exp(lo)), float(np.exp(hi))
        p1 = bool(P1_BAND[0] <= p1_eff <= P1_BAND[1] or p1_lo <= 1.0 <= p1_hi)
    else:
        p1_eff = p1_lo = p1_hi = np.nan
        p1 = False
    cells = p.groupby("cell").agg(n=("r", "size"), f=("f", "mean"), mean_r=("r", "mean"), mean_r0=("r0", "mean"), mean_r_inc=("r_inc", "mean")).reset_index()
    cells["resid"] = np.exp(cells["mean_r"])
    big = cells[cells["n"] >= CELL_MIN]
    w = big["n"].to_numpy(float)
    rms_, rms0, rmsi = (tuple(float(np.sqrt((w * big[c] ** 2).sum() / w.sum())) for c in ("mean_r", "mean_r0", "mean_r_inc")) if len(big) else (np.nan,) * 3)
    p2 = bool(len(big) and rms_ < rms0 and rms_ < rmsi)
    ok3 = (np.abs(big["resid"] - 1.0) <= P3_TOL) if len(big) else pd.Series(dtype=bool)
    p3_share = float(ok3.mean()) if len(big) else np.nan
    p3 = bool(len(big) and p3_share >= P3_SHARE)
    un = p[p["unexposed"]]
    c8 = {}
    if len(un):
        m, lo, hi = _boot_mean(un["r"].to_numpy(float), un["block"].to_numpy(), n_boot, seed)
        c8 = {"n": len(un), "resid": float(np.exp(m)), "lo": float(np.exp(lo)), "hi": float(np.exp(hi)),
              "by_fold": {c: float(np.exp(g["r"].mean())) for c, g in un.groupby("cutoff")}, "above_one_every_fold": bool(all(g["r"].mean() > 0 for _, g in un.groupby("cutoff"))),
              "interval_excludes_one": bool(np.exp(lo) > 1.0 or np.exp(hi) < 1.0)}
    return {"n_test": len(p), "n_material": len(mat), "P1_resid": p1_eff, "P1_lo": p1_lo, "P1_hi": p1_hi, "P1": p1, "P2_rms": rms_, "P2_rms_no_haircut": rms0,
            "P2_rms_incumbent": rmsi, "P2": p2, "n_cells": len(big), "P3_share": p3_share, "P3": p3,
            "verdict": "PASS" if (p1 and p2 and p3) else "FAIL", "C8": c8, "cells": cells.sort_values("n", ascending=False)}


# ---- stick side (§6) -----------------------------------------------------------------------------------------------
def sticks(pud_links: pd.DataFrame, model: Model, rule: str, mix: Mapping[str, float], groups: Mapping[str, str], cap: float | None = CAP) -> pd.DataFrame:
    """Per stick: F under the rule, the capped and uncapped applied factor, n parents, nearest d_eff, pattern, permit flag.
    `pud_links` already carries the basin's stick-side parent rule (Delaware >= 12 mo; Midland every existing producer);
    `groups` maps stick -> bench group for F_mix."""
    par = parents(pud_links, drilled=False)
    cf = child_factors(par, model, rules=(rule,)).set_index("child")
    ids = pd.Index(sorted(set(pud_links["child"])))
    cf = cf.reindex(ids)
    g = np.array([groups.get(str(i), "") for i in ids])
    f_rule = cf[f"F_{rule}"].fillna(1.0).to_numpy()
    permit = par[par["permit"].astype(bool)].groupby("child").size().reindex(ids).fillna(0).astype(int)
    return pd.DataFrame({"stick": ids, "bench_group": g, "n_parents": cf["n_parents"].fillna(0).astype(int).to_numpy(), "nearest_d_eff": cf["nearest_d_eff"].to_numpy(),
                         "pattern": cf["pattern"].fillna("none").to_numpy(), "F_rule": f_rule, "factor": applied(f_rule, g, mix, cap),
                         "factor_uncapped": applied(f_rule, g, mix, None), "permit_parents": permit.to_numpy()})


def g4_support(drilled: pd.DataFrame) -> pd.DataFrame:
    """Per side pattern (drilled children with >= 1 parent): n and the 2nd percentile of nearest d_eff — the G4 candidate's
    support table (reported only)."""
    x = drilled[drilled["n_parents"] > 0]
    t = x.groupby("pattern").agg(n=("nearest_d_eff", "size"), p2_d_eff=("nearest_d_eff", lambda v: float(np.percentile(v, G4_PERCENTILE)))).reset_index()
    t["precedent"] = t["n"] >= G4_PRECEDENT_FLOOR
    return t


def g4_outcome(st: pd.DataFrame, support: pd.DataFrame) -> pd.Series:
    """'forecast' when the stick's pattern has >= 30 drilled children and its nearest d_eff >= their 2nd percentile; unexposed
    sticks are always 'forecast'; else 'no_forecast_geometry'."""
    s = support.set_index("pattern")
    out = []
    for p, d in zip(st["pattern"], st["nearest_d_eff"], strict=True):
        if p == "none" or p in s.index and bool(s.at[p, "precedent"]) and d >= float(s.at[p, "p2_d_eff"]):
            out.append("forecast")
        else:
            out.append("no_forecast_geometry")
    return pd.Series(out, index=st.index)
