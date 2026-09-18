"""Gate 5b: TC granularity — one type curve, or one per deal polygon?

Reviewer decision 2026-09-18: split ONLY when BOTH
  (a) max/min group median of the metric > split.median_ratio (1.25), and
  (b) a rank test is significant at split.alpha (Mann-Whitney for 2 groups,
      Kruskal-Wallis for > 2),
over groups with >= split.min_wells_per_group (6) wells. Exactly one of
(a)/(b) -> escalate. Neither -> single_tc. Groups under the minimum never
split: they borrow the pooled TC with a documented multiplier.

A gradient (metric vs distance along the cohort's principal axis, OLS slope +
R^2) is reported even for a single polygon — it sets expectations for edge
units. It complements Gate 4's dispersion flag on Novi inflation ratios
(Novi's own spatial dispersion); this one measures the ACTUALS.

Metric: EUR per 1,000 ft by default; callers pass cum-12 oil per 1,000 ft
for young cohorts and say so in `metric`.
"""

from __future__ import annotations

import math
import statistics
from dataclasses import dataclass, field
from typing import Any

from scipy import stats
from shapely.geometry import Point, Polygon
from shapely.ops import unary_union

from dealintake.config import Config
from dealintake.geo import FT_PER_M, LocalFrame


@dataclass
class SplitResult:
    recommendation: str                    # single_tc | split_by_polygon | escalate
    metric: str
    groups: list[dict[str, Any]] = field(default_factory=list)
    median_ratio: float | None = None
    test: str | None = None
    p_value: float | None = None
    gradient_per_mile: float | None = None
    gradient_r2: float | None = None
    notes: list[str] = field(default_factory=list)


def assign_units(wells: list[dict[str, Any]], units: dict[str, Polygon]) -> None:
    """Set w['unit'] (containing polygon, else nearest) and w['unit_dist_ft']."""
    frame = LocalFrame.around(unary_union(list(units.values())))
    local = {k: frame.to_local(v) for k, v in units.items()}
    for w in wells:
        p = frame.to_local(Point(w["lon"], w["lat"]))
        best, bd = None, math.inf
        for name, poly in local.items():
            d = 0.0 if poly.covers(p) else poly.distance(p)
            if d < bd:
                best, bd = name, d
        w["unit"], w["unit_dist_ft"] = best, round(bd * FT_PER_M, 0)


def gradient(wells: list[dict[str, Any]], metric: str) -> tuple[float | None, float | None]:
    """OLS of metric vs position (miles) along the well cloud's principal axis."""
    pts = [(w["lon"], w["lat"], w[metric]) for w in wells if w.get(metric) is not None]
    if len(pts) < 3:
        return None, None
    lon0 = statistics.fmean(p[0] for p in pts)
    lat0 = statistics.fmean(p[1] for p in pts)
    frame = LocalFrame(lon0, lat0)
    xy = []
    for lon, lat, _ in pts:
        q = frame.to_local(Point(lon, lat))
        xy.append((q.x, q.y))
    mx = statistics.fmean(x for x, _ in xy)
    my = statistics.fmean(y for _, y in xy)
    sxx = sum((x - mx) ** 2 for x, _ in xy)
    syy = sum((y - my) ** 2 for _, y in xy)
    sxy = sum((x - mx) * (y - my) for x, y in xy)
    theta = 0.5 * math.atan2(2 * sxy, sxx - syy)            # principal axis
    s = [((x - mx) * math.cos(theta) + (y - my) * math.sin(theta)) / 1609.344 for x, y in xy]
    if max(s) - min(s) < 1e-6:
        return None, None
    fit = stats.linregress(s, [p[2] for p in pts])
    return float(fit.slope), float(fit.rvalue ** 2)


def run(
    wells: list[dict[str, Any]],
    units: dict[str, Polygon],
    cfg: Config,
    *,
    metric: str = "eur_per_1000ft",
) -> SplitResult:
    sp = cfg["split"]
    min_n, ratio_thr, alpha = int(sp["min_wells_per_group"]), float(sp["median_ratio"]), float(sp["alpha"])
    usable = [w for w in wells if w.get(metric) is not None]
    res = SplitResult(recommendation="single_tc", metric=metric)
    res.gradient_per_mile, res.gradient_r2 = gradient(usable, metric)
    if len(units) < 2:
        res.notes.append("single polygon: split not applicable; gradient reported")
        return res

    assign_units(usable, units)
    for name in units:
        vals = [w[metric] for w in usable if w["unit"] == name]
        res.groups.append({
            "unit": name,
            "n": len(vals),
            "median": round(statistics.median(vals), 1) if vals else None,
            "eligible": len(vals) >= min_n,
        })
    elig = [g for g in res.groups if g["eligible"]]
    small = [g["unit"] for g in res.groups if not g["eligible"]]
    if small:
        res.notes.append(
            f"below {min_n} wells: {', '.join(small)} — never split; borrow the pooled TC "
            "with a documented multiplier if the reviewer sees a difference"
        )
    if len(elig) < 2:
        res.notes.append(f"fewer than 2 groups with >= {min_n} wells: single_tc")
        return res

    samples = [[w[metric] for w in usable if w["unit"] == g["unit"]] for g in elig]
    meds = [g["median"] for g in elig]
    res.median_ratio = round(max(meds) / min(meds), 3) if min(meds) > 0 else math.inf
    if len(samples) == 2:
        res.test = "mann_whitney"
        res.p_value = float(stats.mannwhitneyu(*samples, alternative="two-sided").pvalue)
    else:
        res.test = "kruskal_wallis"
        res.p_value = float(stats.kruskal(*samples).pvalue)

    big, sig = res.median_ratio > ratio_thr, res.p_value < alpha
    if big and sig:
        res.recommendation = "split_by_polygon"
    elif big or sig:
        res.recommendation = "escalate"
        res.notes.append(
            f"median ratio {res.median_ratio:.2f} {'>' if big else '<='} {ratio_thr}; "
            f"p {res.p_value:.3f} {'<' if sig else '>='} {alpha} — criteria disagree, reviewer call"
        )
    return res
