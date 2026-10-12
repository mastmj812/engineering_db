"""BOX step 5d — the type-curve and risk-factor RECORD: pure rules (no DB, no I/O).

Plan §5 step 5d. What gets stored (sql/58) is fixed by decisions of record; this module holds the rules
that turn the 5b / 5c evidence into rows:

  * D42 pooled-bench view: a vertical parent inside the BOX pool (WCA = WCA_1 / WCA_2 / WCXY) is the same
    bench — the well is lateral infill, not a topfill / underfill pair. Applied to the RAW (class, parent
    bench) before rare pairs are collapsed, and to both sides of a sandwich (one same-pool side leaves a
    one-sided relation on the other side).
  * D45 factor ladder, stamped per factor: (1) the term's own bench estimate when it has >= 30 subject
    wells -> (2) the class within the bench -> (3) the class pooled across benches (terminal, whatever n).
  * D41 / D44 lookup for one well or PUD: pair factor x infill factor; an unknown pair falls to its class,
    then the basin class; the reference (codev_stack, no same-bench parent) is 1.00.
  * D43 reference curve: a uniform scale of the as-built cohort-mean curve — qo and qi x ref_mult, nominal
    Di and b unchanged, so EUR and every monthly volume scale by exactly ref_mult.
"""

from __future__ import annotations

import math
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from typing import Any

from box import dev_factor as dfm

LADDER_MIN_N = 30  # D45
PARENTED = ("topfill", "underfill")
CLASS_TERMS = ("infill", "standalone", "topfill", "underfill", "sandwich")
SCORING_ONLY = {"standalone"}  # D44: an unparented PUD gets the reference, never standalone
RUNG_LABEL = {0: "reference", 1: "own estimate (n >= 30)", 2: "class in bench", 3: "class across benches"}
POOLED = "*"  # bench label of the basin-pooled (across benches) rows


# ----------------------------------------------------------------------------
# D42 pooled-bench view
# ----------------------------------------------------------------------------


def _blank(v: Any) -> str | None:
    if v is None or (isinstance(v, float) and math.isnan(v)):
        return None
    s = str(v)
    return s if s and s.lower() != "nan" else None


def pooled_scenario(cls: Any, below: Any, above: Any, infill: Any, pool: Iterable[str]) -> tuple[str | None, str | None, bool, bool]:
    """(class, parent bench, infill, same_pool) under D42. A same-pool parent is lateral infill on the
    reference class; a sandwich with one same-pool side keeps the other side's one-sided relation."""
    c, b, a = _blank(cls), _blank(below), _blank(above)
    inf = bool(infill) if infill is not None and not (isinstance(infill, float) and math.isnan(infill)) else False
    p = set(pool)
    if c == "topfill" and b in p:
        return dfm.REFERENCE, None, True, True
    if c == "underfill" and a in p:
        return dfm.REFERENCE, None, True, True
    if c == "sandwich":
        b_in, a_in = b in p, a in p
        if b_in and a_in:
            return dfm.REFERENCE, None, True, True
        if b_in:
            return "underfill", a, True, True
        if a_in:
            return "topfill", b, True, True
    return c, dfm.parent_bench(c, b, a), inf, False


def raw_pair(cls: str | None, parent: str | None) -> str | None:
    """The estimation label before rare-pair pooling: '<class>|<parent>' for topfill / underfill,
    'sandwich|all', the bare class otherwise (dev_factor.pair_labels without the count collapse)."""
    if cls is None:
        return None
    if cls in PARENTED:
        return f"{cls}|{parent}"
    return "sandwich|all" if cls == "sandwich" else cls


# ----------------------------------------------------------------------------
# D45 ladder
# ----------------------------------------------------------------------------


@dataclass(frozen=True)
class Est:
    """One term's own estimate (factor = exp(beta)), its CI and the subject wells carrying it."""

    estimate: float
    ci_lo: float | None
    ci_hi: float | None
    n: int
    n_clusters: int | None = None


def term_class(term: str) -> str:
    """'topfill|WCB_1' -> 'topfill'; 'sandwich|all' -> 'sandwich'; 'infill' / 'standalone' unchanged."""
    return term.split("|")[0]


def resolve(term: str, own: Est | None, bench_class: Mapping[str, Est], basin_class: Mapping[str, Est],
            min_n: int = LADDER_MIN_N) -> tuple[float, int, int]:
    """(factor of record, rung, n_basis) for one bench term. Rung 1 = its own estimate (n >= min_n); 2 =
    the class within the bench (n >= min_n); 3 = the class across benches, terminal whatever its n."""
    if own is not None and own.n >= min_n and _ok(own.estimate):
        return own.estimate, 1, own.n
    c = bench_class.get(term_class(term))
    if c is not None and c.n >= min_n and _ok(c.estimate):
        return c.estimate, 2, c.n
    bc = basin_class.get(term_class(term))
    if bc is None or not _ok(bc.estimate):
        raise ValueError(f"no basin-class factor for {term!r} (ladder rung 3 is terminal)")
    return bc.estimate, 3, bc.n


def resolve_class(cls: str, own: Est, basin_class: Mapping[str, Est], min_n: int = LADDER_MIN_N) -> tuple[float, int, int]:
    """A class-in-bench row: its own estimate when n >= min_n (rung 2), else the basin class (rung 3)."""
    if own.n >= min_n and _ok(own.estimate):
        return own.estimate, 2, own.n
    bc = basin_class[cls]
    return bc.estimate, 3, bc.n


def _ok(v: float | None) -> bool:
    return v is not None and math.isfinite(v) and v > 0


# ----------------------------------------------------------------------------
# Lookup (D41 x D44): one well / PUD
# ----------------------------------------------------------------------------


def lookup(table: Mapping[tuple[str, str], float], bench: str, pair: str | None, infill: bool, *, pud: bool = False) -> float:
    """Factor of a well vs the reference: pair factor x infill factor. `table` maps (level, term) ->
    factor of record for ONE bench, plus ('basin_class', class) rows. An unknown pair falls to the
    class in the bench, then to the basin class. pud=True applies D44 (standalone -> reference)."""
    f = 1.0
    if pair and pair != dfm.REFERENCE:
        cls = term_class(pair)
        if pud and cls in SCORING_ONLY:
            f = 1.0
        elif ("pair", pair) in table:
            f = table[("pair", pair)]
        elif ("pair", f"{cls}|other") in table:  # a pair rarer than dev_factor.MIN_PAIR_WELLS was estimated pooled
            f = table[("pair", f"{cls}|other")]
        elif ("class", cls) in table:
            f = table[("class", cls)]
        elif ("basin_class", cls) in table:
            f = table[("basin_class", cls)]
        else:
            raise KeyError(f"no factor for {bench} {pair!r}")
    if infill:
        f *= table.get(("pair", "infill"), table.get(("class", "infill"), table.get(("basin_class", "infill"), 1.0)))
    return f


# ----------------------------------------------------------------------------
# D43 reference curve
# ----------------------------------------------------------------------------


def reference_params(params: Mapping[str, Any], ref_mult: float) -> dict[str, Any]:
    """The reference-scenario curve: the as-built cohort-mean curve scaled uniformly (qo, qi x ref_mult;
    Di, b, Df and the ramp length unchanged), so EUR and each month's volume scale by ref_mult."""
    if not (ref_mult and math.isfinite(ref_mult) and ref_mult > 0):
        raise ValueError(f"bad ref_mult {ref_mult!r}")
    out = dict(params)
    for k in ("qo", "qi"):
        if out.get(k) is not None:
            out[k] = float(out[k]) * ref_mult
    return out


def weighted_ref_mult(weights: Sequence[float], factors: Sequence[float]) -> float:
    """sum(w / f) / sum(w) (dev_factor.normalisation_multiplier): the reference-equivalent mean of a mixed cohort."""
    return dfm.normalisation_multiplier(weights, factors)
