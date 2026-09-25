"""Gate 5.1-5.2b: type-curve candidate filtering, spacing class, codev tiering.

Pure logic over candidate dicts (built by dealintake.warehouse from
curated.wells_enriched + curated.codev_context). Nothing here drops a well
silently: every exclusion carries a reason, every inclusion a tier.

TIERS (reviewer decisions 2026-09-18), relative to the ADJACENT PLANNED
benches of the candidate's bench (the benches immediately above/below it in
the deal's planned stack, ordered by landing TVD):
  codev              an adjacent planned bench came online within +/-180 d
                     AND no adjacent planned bench was already producing
                     (> 180 d earlier). Later infill (child) is ignored here:
                     the original development was co-developed, and child
                     counts are right-censored anyway.
  stack_standalone   no adjacent-planned-bench neighbor at all.
  topfill_underfill  an adjacent planned bench was an UNSHIELDED VERTICAL
                     PARENT by the house rule of record (curated.dev_scenario,
                     sql/50: online > 180 d earlier, lateral midpoint within
                     660 ft, TVD within 1,000 ft, not shielded by a codev
                     well in between — Michael 2026-09-23), OR was only a
                     later CHILD (infilled from that bench afterwards). A
                     parent beyond the gate does not make a topfill.
A single-bench plan has no adjacent bench: every candidate is tier
`stack_standalone` and tiering is reported as not applicable.

ORDER: default codev -> stack_standalone -> topfill_underfill; flips to
topfill_underfill -> codev -> stack_standalone when the DSU already has PDP
in an adjacent bench (the planned sticks ARE topfill/underfill then).
ORDER OF OPERATIONS (Michael, 2026-09-18): classify the whole eligible pool
FIRST, run the TC split test on it, THEN fill a cohort per TC group. Filling
before splitting starved remote units of wells and hid a real split (Toucan).
FILL (Michael, 2026-09-18): the FIRST tier contributes its nearest wells
(by distance to the unit) up to type_curve.max_wells; each later tier only
tops up, nearest first, until min_wells is reached. Wells beyond the cap stay
in eligible_not_selected (they still feed the tier medians).
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import date
from typing import Any

from dealintake.config import Config

_BENCH_SUFFIX = re.compile(r"_b$")


def bench_code(code: str) -> str:
    """Strip narvi's bimodal-split `_b` suffix before any warehouse lookup."""
    return _BENCH_SUFFIX.sub("", code)


def adjacent_benches(bench: str, planned_stack: list[str]) -> list[str]:
    """Benches immediately above/below `bench` in the planned stack (ordered
    shallow -> deep by landing TVD). Empty for a single-bench plan."""
    stack = []
    for b in (bench_code(x) for x in planned_stack):
        if b not in stack:
            stack.append(b)
    b = bench_code(bench)
    if b not in stack:
        return []
    i = stack.index(b)
    return [stack[j] for j in (i - 1, i + 1) if 0 <= j < len(stack)]


def spacing_class(lateral_closer_xy_ft: float | None, planned_spacing_ft: float, cfg: Config) -> str:
    """standalone (NULL or >= 2800 sentinel) / tight (< frac x planned) / representative."""
    sp = cfg["spacing"]
    if lateral_closer_xy_ft is None or lateral_closer_xy_ft >= float(sp["sentinel_ft"]):
        return "standalone"
    if lateral_closer_xy_ft < float(sp["tight_below_frac"]) * planned_spacing_ft:
        return "tight"
    return "representative"


def vertical_parents(c: dict[str, Any]) -> set[str]:
    """Benches that acted as an UNSHIELDED vertical parent to this well, per
    the house rule of record (curated.dev_scenario, sql/50): a parent online
    > 180 d earlier whose lateral midpoint is within 660 ft and whose TVD is
    within 1,000 ft. The gate is applied IN the view (parent_benches_below /
    _above) — no threshold is copied here. Shielding is re-read per bench
    from bench_context: a co-developed other-bench well strictly between the
    subject and that bench's nearest parent hides it (Hellfire East E 8HU)."""
    bc = c.get("bench_context") or {}
    cb, ca = c.get("nearest_codev_below_dtvd_ft"), c.get("nearest_codev_above_dtvd_ft")
    out: set[str] = set()
    for b in c.get("parent_benches_below") or []:
        dz = (bc.get(b) or {}).get("parent_nearest_dtvd_ft")
        if not (cb is not None and dz is not None and float(cb) < float(dz)):
            out.add(b)
    for b in c.get("parent_benches_above") or []:
        dz = (bc.get(b) or {}).get("parent_nearest_dtvd_ft")
        if not (ca is not None and dz is not None and float(ca) > float(dz)):
            out.add(b)
    return out


def codev_tier(c: dict[str, Any], adjacent: list[str]) -> str:
    """Tier vs the ADJACENT PLANNED benches. topfill_underfill = an adjacent
    bench was an unshielded vertical parent (dev_scenario rule, see
    vertical_parents) OR only a later child; codev = an adjacent bench came
    on within +-180 d; else stack_standalone. A parent beyond the 660-ft /
    1,000-ft gate is NOT a parent here (it diluted the Midland topfill
    hindcast signal — Michael, 2026-09-23)."""
    if not adjacent:
        return "stack_standalone"
    adj = set(adjacent)
    if adj & vertical_parents(c):
        return "topfill_underfill"
    if adj & set(c.get("codev_benches") or []):
        return "codev"
    if adj & set(c.get("child_benches") or []):
        return "topfill_underfill"
    return "stack_standalone"


def exclusion_reasons(
    c: dict[str, Any],
    cfg: Config,
    *,
    planned_lateral_ft: float,
    lateral_tol: float,
    planned_spacing_ft: float,
) -> list[str]:
    tc = cfg["type_curve"]
    reasons: list[str] = []
    fp = c.get("first_production_date")
    floor = tc["first_prod_after"]
    floor = floor if isinstance(floor, date) else date.fromisoformat(str(floor))
    if fp is None or fp < floor:
        reasons.append(f"first_prod<{floor}")
    ll = c.get("lateral_length_ft")
    lo, hi = planned_lateral_ft * (1 - lateral_tol), planned_lateral_ft * (1 + lateral_tol)
    if ll is None or not lo <= ll <= hi:
        reasons.append(f"lateral_outside_{lo:.0f}-{hi:.0f}")
    if (c.get("months_produced") or 0) < int(tc["min_months_data"]):
        reasons.append(f"months<{tc['min_months_data']}")
    sc = spacing_class(c.get("lateral_closer_xy_ft"), planned_spacing_ft, cfg)
    if sc != "representative":
        reasons.append(f"spacing_{sc}")
    if not c.get("codev_scorable", True):
        reasons.append("no_codev_context")
    return reasons


@dataclass
class Selection:
    bench: str
    adjacent: list[str]
    tier_order: list[str]
    order_reason: str
    selected: list[dict[str, Any]] = field(default_factory=list)
    eligible_not_selected: list[dict[str, Any]] = field(default_factory=list)
    excluded: list[dict[str, Any]] = field(default_factory=list)
    flags: list[str] = field(default_factory=list)

    def tier_counts(self) -> dict[str, int]:
        out = {t: 0 for t in self.tier_order}
        for c in self.selected:
            out[c["tier"]] += 1
        return out

    def first_tier_frac(self) -> float | None:
        if not self.selected:
            return None
        return self.tier_counts()[self.tier_order[0]] / len(self.selected)


def tier_order(cfg: Config, adjacent: list[str], flip: bool) -> tuple[list[str], str]:
    cx = cfg["codev"]
    if flip and adjacent:
        return list(cx["tier_order_when_pdp_adjacent"]), "majority of deal units already have PDP in an adjacent bench"
    return list(cx["tier_order_default"]), "default"


def classify(
    candidates: list[dict[str, Any]],
    cfg: Config,
    *,
    bench: str,
    planned_stack: list[str],
    planned_lateral_ft: float,
    basin: str | None,
    planned_spacing_ft: float,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], list[str]]:
    """Tag every candidate with spacing class + codev tier and split into
    (eligible, excluded-with-reasons, adjacent planned benches). No capping —
    the eligible POOL feeds the split test before any cohort is filled."""
    adjacent = adjacent_benches(bench, planned_stack)
    tol = cfg.lateral_tolerance(basin)
    eligible, excluded = [], []
    for c in candidates:
        c = dict(c)
        c["spacing_class"] = spacing_class(c.get("lateral_closer_xy_ft"), planned_spacing_ft, cfg)
        c["tier"] = codev_tier(c, adjacent)
        reasons = exclusion_reasons(
            c, cfg, planned_lateral_ft=planned_lateral_ft, lateral_tol=tol,
            planned_spacing_ft=planned_spacing_ft,
        )
        if reasons:
            c["exclusion"] = ";".join(reasons)
            excluded.append(c)
        else:
            eligible.append(c)
    return eligible, excluded, adjacent


def fill(
    eligible: list[dict[str, Any]],
    cfg: Config,
    *,
    bench: str,
    adjacent: list[str],
    order: list[str],
    order_reason: str,
    dist_key: str = "dist_ft",
) -> Selection:
    """Fill one TC cohort from an eligible pool (see FILL in the module doc).
    `dist_key` = distance used for nearest-first (to the whole deal for a
    pooled TC, to the unit itself for a per-polygon TC)."""
    sel = Selection(bench=bench_code(bench), adjacent=adjacent, tier_order=order, order_reason=order_reason)
    if not adjacent:
        sel.flags.append("single_bench_plan: codev tiering not applicable")
    min_wells = int(cfg["type_curve"]["min_wells"])
    max_wells = int(cfg["type_curve"]["max_wells"])
    for t in order:
        tier_wells = sorted(
            (c for c in eligible if c["tier"] == t),
            key=lambda c: (c.get(dist_key) is None, c.get(dist_key) or 0.0, c["api10"]),
        )
        target = max_wells if t == order[0] else min_wells
        take = max(0, target - len(sel.selected))
        sel.selected.extend(tier_wells[:take])
        sel.eligible_not_selected.extend(tier_wells[take:])
    first = sum(1 for c in eligible if c["tier"] == order[0])
    if first > max_wells:
        sel.flags.append(f"first tier capped: {max_wells} nearest of {first} {order[0]} wells")
    if len(sel.selected) < min_wells:
        sel.flags.append(f"under_count: {len(sel.selected)} < min_wells {min_wells} (extend radius / strike-biased — reviewer)")
    frac = sel.first_tier_frac()
    cx = cfg["codev"]
    if adjacent and frac is not None and frac < float(cx["min_tier1_frac_warn"]):
        sel.flags.append(f"first_tier_share {frac:.0%} < {float(cx['min_tier1_frac_warn']):.0%} ({order[0]})")
    return sel


def select(
    candidates: list[dict[str, Any]],
    cfg: Config,
    *,
    bench: str,
    planned_stack: list[str],
    planned_lateral_ft: float,
    basin: str | None,
    planned_spacing_ft: float,
    deal_has_pdp_in_adjacent_bench: bool,
) -> Selection:
    """classify + fill in one call (single pooled cohort)."""
    eligible, excluded, adjacent = classify(
        candidates, cfg, bench=bench, planned_stack=planned_stack, planned_lateral_ft=planned_lateral_ft,
        basin=basin, planned_spacing_ft=planned_spacing_ft,
    )
    order, why = tier_order(cfg, adjacent, deal_has_pdp_in_adjacent_bench)
    sel = fill(eligible, cfg, bench=bench, adjacent=adjacent, order=order, order_reason=why)
    sel.excluded = excluded
    return sel


def tier_medians(sel: Selection, key: str = "eur_per_1000ft") -> dict[str, float | None]:
    """Per-tier median of `key` over selected + eligible wells — makes the bias
    direction of the tier mix visible in the dossier."""
    import statistics

    pool = sel.selected + sel.eligible_not_selected
    out: dict[str, float | None] = {}
    for t in sel.tier_order:
        vals = [c[key] for c in pool if c["tier"] == t and c.get(key) is not None]
        out[t] = round(statistics.median(vals), 1) if vals else None
    return out
