"""PDP-proximity study, step 1 — pure geometry + precedent atlas (no DB).

Question (Michael 2026-10-19): which PUDs sit so close to an existing producer that they will never
realistically be drilled (so BOX should not forecast them)? Step 1 measures PRECEDENT: how often operators
have actually drilled a new horizontal at a given 3-D distance from an older producer.

Pair metric = deal-intake's (dealintake/proximity.py, config v14) applied basin-wide, child-relative:
  overlap  share of the CHILD's lateral that the parent spans (parent coords projected onto the child line)
  dh_ft    MEDIAN distance from the child's lateral to the parent line over that shared span (21 samples on
           the child, the ones inside the span) — not the midpoint offset (sql/50) or the mean (spacing3d)
  dz_ft    parent TVD - child TVD (> 0 = parent deeper = the child is a TOPFILL); dv_ft = |dz_ft|
The deal-intake rule reads the along-axis span in a unit frame; for straight parallel sticks the two agree,
and tests/test_box_prox_study.py holds them to the Chevron acceptance fixture.

Relation by age = child first production - parent first production:
  codev     |age| <= 180 d   (sql/47's window)
  young     180 < age < 365  (reported, not a depleting parent)
  parent    age >= 365 d     (DEPLETING parent — decision 2026-10-19: >= 12 months producing)
Class by bench POOL (D42: WCA_1 / WCA_2 / WCXY are one pool for infill purposes):
  same      same pool (the horizontal-spacing case)
  topfill   other pool, parent deeper
  underfill other pool, parent shallower
Side: each link also stores the median SIGNED offset (dxy_ft, + = left of the child's heading) for flanking.
Shielding (sql/50's rule, vertical classes only): a co-developed other-pool well with dh <= 660 ft sits between
the child and that parent (same side, strictly closer vertically).
"""

from __future__ import annotations

import statistics
from collections.abc import Iterable, Sequence
from dataclasses import asdict, dataclass

import numpy as np
import pandas as pd
from shapely.geometry import Point
from shapely.geometry.base import BaseGeometry

N_SAMPLES = 21            # dealintake.proximity.N_SAMPLES
CODEV_DAYS = 180
PARENT_MIN_DAYS = 365
MIN_OVERLAP = 0.30
PAIR_GATE_FT = 2640.0     # stick-to-stick candidate gate; the X grid tops out here
STORE_DV_FT = 1500.0      # links beyond this vertical gap are not stored
SHIELD_DH_FT = 660.0
Z_GRID = (100, 200, 300, 400, 500, 600, 800, 1000)
X_GRID = (200, 400, 600, 800, 1000, 1200, 1400, 1600, 2000, 2640)
RULE_V14 = (300.0, 800.0)  # deal-intake v14 (vertical, horizontal) — PROVISIONAL, the thing being tested
POOL = {"WCA_1": "WCA", "WCA_2": "WCA", "WCXY": "WCA"}


def pool(bench: str | None) -> str:
    b = bench or "(unmapped)"
    return POOL.get(b, b)


def _coords(g: BaseGeometry) -> list[tuple[float, float]]:
    return [c for part in getattr(g, "geoms", [g]) for c in part.coords]


def pair_signed(child: BaseGeometry, parent: BaseGeometry) -> tuple[float, float | None, float | None]:
    """(overlap share of the child, median gap ft, median SIGNED offset ft) over the shared span. Sign = side of the
    child's local heading (first -> last vertex): + = parent to the LEFT, - = to the RIGHT. Geometries in projected FEET."""
    if child.length <= 0 or parent.length <= 0:
        return 0.0, None, None
    ts = [child.project(Point(c), normalized=True) for c in _coords(parent)]
    lo, hi = min(ts), max(ts)
    if hi <= lo:
        return 0.0, None, None
    ds, sg = [], []
    for i in range(N_SAMPLES):
        t = i / (N_SAMPLES - 1)
        if lo - 1e-9 <= t <= hi + 1e-9:
            p = child.interpolate(t, normalized=True)
            q = parent.interpolate(parent.project(p))
            p1, p2 = child.interpolate(max(0.0, t - 1e-3), normalized=True), child.interpolate(min(1.0, t + 1e-3), normalized=True)
            cross = (p2.x - p1.x) * (q.y - p.y) - (p2.y - p1.y) * (q.x - p.x)
            d = p.distance(parent)
            ds.append(d)
            sg.append(d if cross >= 0 else -d)
    if not ds:
        return hi - lo, None, None
    return hi - lo, statistics.median(ds), statistics.median(sg)


def pair(child: BaseGeometry, parent: BaseGeometry) -> tuple[float, float | None]:
    """(overlap share of the child, median gap ft over the shared span). Geometries in projected FEET."""
    ov, dh, _ = pair_signed(child, parent)
    return ov, dh


def relation(age_days: int) -> str:
    if age_days < -CODEV_DAYS:
        return "child"
    if age_days <= CODEV_DAYS:
        return "codev"
    return "parent" if age_days >= PARENT_MIN_DAYS else "young"


def pair_class(child_bench: str | None, parent_bench: str | None, dz_ft: float) -> str:
    if pool(child_bench) == pool(parent_bench):
        return "same"
    return "topfill" if dz_ft > 0 else "underfill"


@dataclass(frozen=True)
class Link:
    child: str
    parent: str
    child_bench: str
    parent_bench: str
    cls: str
    rel: str
    age_days: int
    dz_ft: float
    dv_ft: float
    dh_ft: float
    overlap: float
    permit: bool       # either TVD is a round 100 (permit depth, rule 10)
    shielded: bool = False
    dxy_ft: float = 0.0  # median SIGNED offset (+ = parent left of the child's heading); |dxy_ft| ~ dh_ft


def links_for_child(child: dict, cands: Iterable[dict], min_overlap: float = MIN_OVERLAP, store_dv: float = STORE_DV_FT) -> list[Link]:
    """Every co-extent link from one child to OLDER-or-codev wells (`cands` = dicts with api10, bench, fp, tvd_ft,
    geom in feet). Children of the child (age < -180 d) are skipped; shielding is stamped afterwards."""
    out = []
    for w in cands:
        if w["api10"] == child["api10"]:
            continue
        age = (child["fp"] - w["fp"]).days
        rel = relation(age)
        if rel == "child":
            continue
        dz = float(w["tvd_ft"]) - float(child["tvd_ft"])
        if abs(dz) > store_dv:
            continue
        ov, dh, dxy = pair_signed(child["geom"], w["geom"])
        if ov < min_overlap or dh is None or dxy is None:
            continue
        cb, pb = child["bench"] or "(unmapped)", w["bench"] or "(unmapped)"
        out.append(Link(child["api10"], w["api10"], cb, pb, pair_class(cb, pb, dz), rel, int(age), dz, abs(dz), float(dh), float(ov),
                        float(w["tvd_ft"]) % 100 == 0 or float(child["tvd_ft"]) % 100 == 0, dxy_ft=float(dxy)))
    return stamp_shielding(out)


def stamp_shielding(links: Sequence[Link], shield_dh: float = SHIELD_DH_FT) -> list[Link]:
    codev = [k for k in links if k.rel == "codev" and k.cls != "same" and k.dh_ft <= shield_dh]
    out = []
    for k in links:
        sh = False
        if k.rel in ("parent", "young") and k.cls != "same":
            sh = any(c.dz_ft * k.dz_ft > 0 and abs(c.dz_ft) < abs(k.dz_ft) for c in codev)
        out.append(Link(**{**asdict(k), "shielded": sh}))
    return out


# ----------------------------------------------------------------------------
# Atlas (DataFrame of links, one row per Link + child attrs)
# ----------------------------------------------------------------------------


def qualifying(links: pd.DataFrame, *, rel: str = "parent", cls: str | Sequence[str] | None = None, min_overlap: float = MIN_OVERLAP,
               drop_permit: bool = True, drop_shielded: bool = True) -> pd.DataFrame:
    d = links[(links["rel"] == rel) & (links["overlap"] >= min_overlap)]
    if cls is not None:
        d = d[d["cls"].isin([cls] if isinstance(cls, str) else list(cls))]
    if drop_permit:
        d = d[~d["permit"]]
    if drop_shielded:
        d = d[~d["shielded"]]
    return d


def exposed(links: pd.DataFrame, z_ft: float, x_ft: float, **kw: object) -> set[str]:
    """Children with >= 1 qualifying link inside dv <= z AND dh <= x (the rectangle rule's violators)."""
    d = qualifying(links, **kw)  # type: ignore[arg-type]
    return set(d.loc[(d["dv_ft"] <= z_ft) & (d["dh_ft"] <= x_ft), "child"])


def grid(links: pd.DataFrame, z_grid: Sequence[float] = Z_GRID, x_grid: Sequence[float] = X_GRID, **kw: object) -> pd.DataFrame:
    """Cumulative child counts N(Z, X): rows = vertical limit, cols = horizontal limit."""
    d = qualifying(links, **kw)  # type: ignore[arg-type]
    # per child, for each z the min dh among links with dv <= z  ->  counts by x
    rows = {}
    for z in z_grid:
        m = d[d["dv_ft"] <= z].groupby("child")["dh_ft"].min().to_numpy()
        rows[int(z)] = [int((m <= x).sum()) for x in x_grid]
    return pd.DataFrame.from_dict(rows, orient="index", columns=[int(x) for x in x_grid]).rename_axis("dv_le_ft")


def nearest_by_child(links: pd.DataFrame, z_ft: float, **kw: object) -> pd.Series:
    """Per child: min dh among qualifying links within dv <= z (NaN-free; children without one are absent)."""
    d = qualifying(links, **kw)  # type: ignore[arg-type]
    return d[d["dv_ft"] <= z_ft].groupby("child")["dh_ft"].min()


def share_table(children: pd.DataFrame, links: pd.DataFrame, rule: tuple[float, float] = RULE_V14, by: str = "bench") -> pd.DataFrame:
    """Per `by` group of drilled children: n children, and how many violate the rule per class (and any class)."""
    z, x = rule
    sets = {c: exposed(links, z, x, cls=c) for c in ("same", "topfill", "underfill")}
    sets["any"] = set().union(*sets.values())
    g = children.groupby(by)["api10"].apply(set)
    rows = []
    for k, ids in g.items():
        r = {by: k, "n_children": len(ids)}
        for c, s in sets.items():
            r[f"n_{c}"] = len(ids & s)
        r["pct_any"] = 100.0 * r["n_any"] / len(ids) if ids else np.nan
        rows.append(r)
    return pd.DataFrame(rows).sort_values("n_children", ascending=False).reset_index(drop=True)


def uptake(parents: pd.DataFrame, links: pd.DataFrame, opportunity: dict[tuple[str, str], set[str]], rule: tuple[float, float] = RULE_V14,
           min_pairs: int = 30) -> pd.DataFrame:
    """Revealed preference: of the parents that HAD the opportunity (child bench developed nearby, parent old enough
    to have been infilled), the share that later received a depleting-relation child of that bench inside the rule.

    `opportunity[(parent_bench, child_bench)]` = parent api10s with that opportunity (built by the report from
    geometry); `parents` carries api10 -> bench (unused beyond validation)."""
    z, x = rule
    q = qualifying(links)
    q = q[(q["dv_ft"] <= z) & (q["dh_ft"] <= x)]
    got = q.groupby(["parent_bench", "child_bench"])["parent"].apply(set).to_dict()
    rows = []
    for (pb, cb), ids in opportunity.items():
        if len(ids) < min_pairs:
            continue
        hit = got.get((pb, cb), set()) & ids
        rows.append({"parent_bench": pb, "child_bench": cb, "same_pool": pool(cb) == pool(pb),
                     "n_opportunity": len(ids), "n_infilled": len(hit), "pct_infilled": 100.0 * len(hit) / len(ids)})
    return pd.DataFrame(rows).sort_values(["n_opportunity"], ascending=False).reset_index(drop=True)
