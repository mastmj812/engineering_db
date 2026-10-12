"""BOX step 5c — development-scenario factors, pooled per bench across the basin (pure).

Plan §5 step 5c, D11. A factor says how a well in one vertical development scenario performs relative
to the REFERENCE scenario in the same ground and the same completion vintage:

    ln y_i = location FE + first-prod-year FE + sum_pair beta_pair * 1[pair_i] + gamma * infill_i + e_i
    factor_pair = exp(beta_pair)

  * y is a per-1,000-ft performance measure (12-mo cum oil, per-well fitted qi / EUR, gas, water, GOR);
  * location FE = the TC area of record (WCA) or a square block (a bench with no areas yet, BS2_S);
  * pair = (sql/50 scenario class, parent bench): the class is the curated.dev_scenario rule of
    record, recomputed here from bench_context so the nearest unshielded parent bench is known
    ("match on parent bench, not just scenario" — D11). Rare pairs collapse to "<class>|other";
  * infill = has_same_bench_parent (a same-bench parent within the co-extent rule: lateral infill).
    sql/50 keeps it as a flag, not a class; BOX estimates it as its own additive term;
  * reference = codev_stack without a same-bench parent (the modal Delaware class).

CIs are a cluster bootstrap over square spatial blocks (pad- and section-scale correlation): the
block, not the well, is the resampling unit. Factors are multiplicative; normalising an area's mixed
cohort to the reference divides each member's forecast by its factor (a uniform scale of the panel,
so the mean curve's shape is unchanged and its EUR scales by `normalisation_multiplier`).
"""

from __future__ import annotations

import math
from collections.abc import Mapping, Sequence
from typing import Any

import numpy as np
import pandas as pd

# sql/50 literals (the view of record bakes them; tests pin the replication against them)
OFFSET_GATE_FT = 660.0
VERTICAL_BAND_FT = 1000.0
UNMAPPED = "(unmapped)"
CLASSES: tuple[str, ...] = ("sandwich", "topfill", "underfill", "codev_stack", "standalone")
REFERENCE = "codev_stack"
MIN_PAIR_WELLS = 10  # a (class, parent bench) pair with fewer wells collapses to "<class>|other"
BLOCK_FT = 15_840.0  # 3-mi bootstrap clusters (the step-4 CV block)


# ----------------------------------------------------------------------------
# Scenario class + parent bench (replicates sql/50 from codev_context.bench_context)
# ----------------------------------------------------------------------------


def _num(v: Any) -> float | None:
    if v is None:
        return None
    try:
        f = float(v)
    except (TypeError, ValueError):
        return None
    return f if math.isfinite(f) else None


def classify(bench: str, ctx: Mapping[str, Mapping[str, Any]] | None) -> dict[str, Any]:
    """sql/50 scenario class for one well plus the NEAREST qualifying parent bench on each side.

    Vertical parent bench k: k != own bench, k != '(unmapped)', n_parent > 0, parent_min_offset_ft <= 660,
    |parent_nearest_dtvd_ft| <= 1000 (dtvd = neighbour - subject: > 0 below, < 0 above). A side is
    shielded when a co-developed other-bench well sits strictly between subject and that side's
    nearest parent. Ties on dtvd break alphabetically (array order in sql/50)."""
    if ctx is None:
        return {"scenario_class": None, "parent_below": None, "parent_above": None, "infill": None,
                "shielded_below": None, "shielded_above": None, "infill_parent_age_days": None}
    below: list[tuple[float, str]] = []
    above: list[tuple[float, str]] = []
    cod_b: list[float] = []
    cod_a: list[float] = []
    codev_other = False
    for k in sorted(ctx):
        v = ctx[k] or {}
        if k == bench or k == UNMAPPED:
            continue
        n_codev = int(v.get("n_codev") or 0)
        if n_codev > 0:
            codev_other = True
            cdz = _num(v.get("codev_nearest_dtvd_ft"))
            if cdz is not None and cdz > 0:
                cod_b.append(cdz)
            elif cdz is not None and cdz < 0:
                cod_a.append(cdz)
        off, dz = _num(v.get("parent_min_offset_ft")), _num(v.get("parent_nearest_dtvd_ft"))
        if int(v.get("n_parent") or 0) > 0 and off is not None and dz is not None and off <= OFFSET_GATE_FT and abs(dz) <= VERTICAL_BAND_FT:
            if dz > 0:
                below.append((dz, k))
            elif dz < 0:
                above.append((-dz, k))
    pb = min(below) if below else None  # (|dz|, bench), nearest first, alphabetical on ties
    pa = min(above) if above else None
    sh_b = pb is not None and bool(cod_b) and min(cod_b) < pb[0]
    sh_a = pa is not None and bool(cod_a) and -max(cod_a) < pa[0]
    live_b, live_a = pb is not None and not sh_b, pa is not None and not sh_a
    if live_b and live_a:
        cls = "sandwich"
    elif live_b:
        cls = "topfill"
    elif live_a:
        cls = "underfill"
    elif codev_other:
        cls = "codev_stack"
    else:
        cls = "standalone"
    own = ctx.get(bench) or {}
    return {"scenario_class": cls, "parent_below": pb[1] if pb else None, "parent_above": pa[1] if pa else None,
            "infill": int(own.get("n_parent") or 0) > 0, "shielded_below": sh_b, "shielded_above": sh_a,
            "infill_parent_age_days": _num(own.get("parent_min_age_days")) if int(own.get("n_parent") or 0) > 0 else None}


NEAR_DTVD_FT = 500.0  # step-6 density measure: a neighbour bench within this TVD shares the drainage volume


def near_neighbours(ctx: Mapping[str, Mapping[str, Any]], dtvd_ft: float = NEAR_DTVD_FT) -> int:
    """Package density at first production: co-extent neighbour laterals (sql/47 rule: within 1,320 ft and
    covering >= 30 % of the subject lateral) that were online before it (parents) or came on with it (codev,
    +-180 d), on any bench, whose TVD is within `dtvd_ft` of the subject. Later children are excluded (they
    are future to the subject). A bench's vertical position = its nearest codev / parent dtvd, else the
    bench median dtvd (sql/47 keeps per-bench facts only)."""
    n = 0
    for v in ctx.values():
        v = v or {}
        med = _num(v.get("median_dtvd_ft"))
        cd = _num(v.get("codev_nearest_dtvd_ft"))
        pd_ = _num(v.get("parent_nearest_dtvd_ft"))
        cd = med if cd is None else cd
        pd_ = med if pd_ is None else pd_
        if int(v.get("n_codev") or 0) and cd is not None and abs(cd) <= dtvd_ft:
            n += int(v["n_codev"])
        if int(v.get("n_parent") or 0) and pd_ is not None and abs(pd_) <= dtvd_ft:
            n += int(v["n_parent"])
    return n


def parent_bench(cls: str | None, below: str | None, above: str | None) -> str | None:
    """The parent bench a class is matched on: topfill -> below, underfill -> above, sandwich ->
    'below+above'; None for the parentless classes."""
    if cls == "topfill":
        return below
    if cls == "underfill":
        return above
    if cls == "sandwich":
        return f"{below}+{above}"
    return None


def pair_labels(cls: pd.Series, parent: pd.Series, min_wells: int = MIN_PAIR_WELLS) -> pd.Series:
    """'<class>|<parent bench>' for parented classes ('<class>|other' when the pair is rarer than
    `min_wells`; sandwich always pools to 'sandwich|all'), the bare class otherwise."""
    raw = pd.Series([f"{c}|{p}" if c in ("topfill", "underfill") else ("sandwich|all" if c == "sandwich" else c)
                     for c, p in zip(cls, parent, strict=True)], index=cls.index)
    counts = raw.value_counts()
    return pd.Series([r if ("|" not in r or r.endswith("|all") or counts[r] >= min_wells) else r.split("|")[0] + "|other" for r in raw], index=cls.index)


def pool_view(pair: pd.Series, infill: pd.Series, pool_benches: Sequence[str]) -> tuple[pd.Series, pd.Series]:
    """BOX pooled-bench view (D19/D33): a topfill/underfill whose parent bench is inside the BOX pool
    (e.g. WCA_1 over WCA_2) is a same-pool parent — re-labelled as lateral infill on the reference
    class. Returns (pair, infill)."""
    pool = set(pool_benches)
    intra = pd.Series([("|" in p) and p.split("|")[0] in ("topfill", "underfill") and p.split("|")[1] in pool for p in pair], index=pair.index)
    return pair.where(~intra, REFERENCE), infill | intra


# ----------------------------------------------------------------------------
# Estimation
# ----------------------------------------------------------------------------


def blocks(x_ft: np.ndarray, y_ft: np.ndarray, size_ft: float = BLOCK_FT) -> np.ndarray:
    """Square spatial block id per point (projected feet)."""
    bx, by = np.floor(np.asarray(x_ft) / size_ft).astype(np.int64), np.floor(np.asarray(y_ft) / size_ft).astype(np.int64)
    return bx * 1_000_003 + by


def design(terms: pd.DataFrame, fes: Sequence[pd.Series]) -> tuple[np.ndarray, list[str]]:
    """[intercept | term columns | drop-first dummies of each FE]."""
    cols = [np.ones(len(terms))]
    names = ["_c"]
    for c in terms.columns:
        cols.append(terms[c].to_numpy(float))
        names.append(c)
    for i, f in enumerate(fes):
        d = pd.get_dummies(pd.Series(np.asarray(f)).astype(str), drop_first=True)
        for c in d.columns:
            cols.append(d[c].to_numpy(float))
            names.append(f"_fe{i}:{c}")
    return np.column_stack(cols), names


def ols(X: np.ndarray, y: np.ndarray, n_terms: int) -> np.ndarray:
    """Coefficients of the first n_terms term columns (after the intercept); NaN for a term with
    no support in this sample."""
    b, *_ = np.linalg.lstsq(X, y, rcond=None)
    out = b[1 : 1 + n_terms].copy()
    support = X[:, 1 : 1 + n_terms].sum(axis=0)
    out[support == 0] = np.nan
    return out


def ppml(X: np.ndarray, y: np.ndarray, n_terms: int, iters: int = 100, tol: float = 1e-10) -> np.ndarray:
    """Poisson pseudo-ML (IRLS) for E[y | X] = exp(X b) on LEVELS: exp(b) is a ratio of conditional
    MEANS (the D32 curve statistic), where log-OLS gives a ratio of geometric means. Consistent for any
    positive y (no Poisson assumption on the variance). NaN for a term with no support."""
    mu = np.full(len(y), max(float(np.mean(y)), 1e-12))
    eta = np.log(mu)
    b = np.zeros(X.shape[1])
    for _ in range(iters):
        z = eta + (y - mu) / mu
        sw = np.sqrt(mu)
        b_new, *_ = np.linalg.lstsq(X * sw[:, None], z * sw, rcond=None)
        eta = np.clip(X @ b_new, -50, 50)
        mu = np.exp(eta)
        if np.max(np.abs(b_new - b)) < tol:
            b = b_new
            break
        b = b_new
    out = b[1 : 1 + n_terms].copy()
    out[X[:, 1 : 1 + n_terms].sum(axis=0) == 0] = np.nan
    return out


def term_frame(pair: pd.Series, infill: pd.Series | None, reference: str = REFERENCE) -> pd.DataFrame:
    """0/1 columns per non-reference pair (+ 'infill')."""
    levels = sorted(set(pair) - {reference})
    t = pd.DataFrame({lv: (pair == lv).astype(float).to_numpy() for lv in levels}, index=pair.index)
    if infill is not None:
        t["infill"] = infill.astype(float).to_numpy()
    return t


def estimate(y: pd.Series, terms: pd.DataFrame, fes: Sequence[pd.Series], cluster: np.ndarray | None = None, n_boot: int = 0,
             seed: int = 5, ci: float = 0.90, estimator: str = "ols") -> pd.DataFrame:
    """Factor per term = exp(beta) with a cluster-bootstrap CI (percentile, `ci` two-sided). Rows with a
    non-finite y are dropped. estimator 'ols' = log-OLS (y is ln metric; geometric-mean ratio), 'ppml'
    = Poisson PML (y is the positive LEVEL; arithmetic-mean ratio). Returns term, factor, ci_lo, ci_hi,
    n_wells (term = 1), n_clusters."""
    solve = ols if estimator == "ols" else ppml
    ok = np.isfinite(y.to_numpy(float))
    yv = y.to_numpy(float)[ok]
    T = terms[ok].reset_index(drop=True)
    F = [pd.Series(np.asarray(f)[ok]) for f in fes]
    X, _ = design(T, F)
    beta = solve(X, yv, T.shape[1])
    rows = pd.DataFrame({"term": list(T.columns), "factor": np.exp(beta), "n_wells": T.sum(axis=0).astype(int).to_numpy()})
    if cluster is not None:
        cl = np.asarray(cluster)[ok]
        rows["n_clusters"] = [len(set(cl[T[c].to_numpy() > 0])) for c in T.columns]
    if n_boot and cluster is not None:
        rng = np.random.default_rng(seed)
        cl = np.asarray(cluster)[ok]
        uniq, inv = np.unique(cl, return_inverse=True)
        members = [np.flatnonzero(inv == k) for k in range(len(uniq))]
        draws = np.full((n_boot, T.shape[1]), np.nan)
        for bi in range(n_boot):
            pick = rng.integers(0, len(uniq), len(uniq))
            idx = np.concatenate([members[k] for k in pick])
            draws[bi] = solve(X[idx], yv[idx], T.shape[1])
        a = (1 - ci) / 2
        with np.errstate(all="ignore"):
            rows["ci_lo"] = np.exp(np.nanquantile(draws, a, axis=0))
            rows["ci_hi"] = np.exp(np.nanquantile(draws, 1 - a, axis=0))
            rows["boot_ok"] = np.isfinite(draws).mean(axis=0)
        rows.attrs["draws"] = draws
    return rows


def age_terms(pair: pd.Series, infill: pd.Series, vert_age_days: pd.Series, infill_age_days: pd.Series,
              cuts_days: Sequence[float] = (365.0, 1095.0), reference: str = REFERENCE) -> pd.DataFrame:
    """Diagnostic: class-level vertical terms and the infill term split by the YOUNGEST parent's age at
    the subject's first production (< 1 yr, 1–3 yr, >= 3 yr). Depletion time is what a future PUD
    differs on: its PDP parents are old."""
    def bucket(a: float | None) -> str:
        if a is None or not np.isfinite(a):
            return "age?"
        return "<1y" if a < cuts_days[0] else ("1-3y" if a < cuts_days[1] else ">=3y")
    cls = [p.split("|")[0] for p in pair]
    cols: dict[str, np.ndarray] = {}
    for c in ("topfill", "underfill", "sandwich"):
        for bk in ("<1y", "1-3y", ">=3y", "age?"):
            cols[f"{c} {bk}"] = np.array([float(k == c and bucket(a) == bk) for k, a in zip(cls, vert_age_days, strict=True)])
    if "standalone" in set(cls):
        cols["standalone"] = np.array([float(k == "standalone") for k in cls])
    for bk in ("<1y", "1-3y", ">=3y", "age?"):
        cols[f"infill {bk}"] = np.array([float(bool(i) and bucket(a) == bk) for i, a in zip(infill, infill_age_days, strict=True)])
    t = pd.DataFrame(cols, index=pair.index)
    return t.loc[:, t.sum(axis=0) > 0]


def factor_ladder(pair_rows: pd.DataFrame, class_bench: Mapping[str, tuple[float, int]], class_basin: Mapping[str, tuple[float, int]],
                  min_n: int = 30) -> pd.DataFrame:
    """Proposed factor of record per pair (D10-style, stamped): rung 1 = the (class, parent bench) pair
    when it has >= min_n subject wells; rung 2 = the class within the bench; rung 3 = the class pooled
    across benches (per basin). `pair_rows` needs term, factor, n_wells; class maps give (factor, n)."""
    out = []
    for r in pair_rows.itertuples():
        cls = r.term.split("|")[0]
        if r.n_wells >= min_n:
            out.append((r.term, r.factor, 1, "pair", int(r.n_wells)))
        elif cls in class_bench and class_bench[cls][1] >= min_n:
            out.append((r.term, class_bench[cls][0], 2, "class in bench", int(class_bench[cls][1])))
        else:
            f, n = class_basin.get(cls, (float("nan"), 0))
            out.append((r.term, f, 3, "class across benches", int(n)))
    return pd.DataFrame(out, columns=["term", "factor", "rung", "rung_label", "n_basis"])


def factor_of(pair: str, infill: bool, table: Mapping[str, float]) -> float:
    """A well's multiplicative factor vs the reference: pair factor x infill factor (1 when absent)."""
    f = 1.0 if pair == REFERENCE else float(table.get(pair, 1.0))
    if infill:
        f *= float(table.get("infill", 1.0))
    return f


def normalisation_multiplier(weights: Sequence[float], factors: Sequence[float]) -> float:
    """Reference-equivalent / as-built mean for one area: sum(w_i / f_i) / sum(w_i). With w = each
    member's per-kft forecast EUR (or cum) and f its factor, the area's reference curve = record curve x
    this multiplier (uniform scale of the panel, so qi scales and Di / b do not move)."""
    w = np.asarray(weights, float)
    f = np.asarray(factors, float)
    ok = np.isfinite(w) & np.isfinite(f) & (f > 0)
    return float((w[ok] / f[ok]).sum() / w[ok].sum()) if ok.any() and w[ok].sum() > 0 else float("nan")
