"""BOX step 4 — type-curve areas: contiguity-constrained regionalization inside a bench extent (pure).

Plan §5 step 4 / D9. The extent of record is tiled with ~1-mi hexagonal cells; each D9 cohort well
(first prod >= 2016, lateral 6,000–13,000 ft, 12 full months) sits in the cell holding its lateral
midpoint. Areas are built by contiguity-constrained Ward agglomeration (the REDCAP / constrained-
hierarchical member of the max-p / SKATER family; a pure MST-cut SKATER was tried first and carved
a clean two-level step into chunks along the smoothed gradient):

  1. a smoothed performance field per cell: the median log(12-mo oil/ft) of the k nearest cohort
     wells to the cell centre — a light pseudo-observation, so empty cells join the neighbour they
     resemble;
  2. bottom-up merging of ADJACENT regions, cheapest Ward cost (the rise in within-area sum of
     squares of log(12-mo oil/ft), wells weigh 1) first; until every region holds >= min_wells
     cohort wells (D9: 10) only merges involving a sub-floor region are taken. Merges are nested,
     so one run yields the partitions for every k.

How many areas: spatially blocked K-fold cross-validation. Each fold rebuilds field + merges
from the training wells only and predicts the held-out wells by their area's training median; the
held-out blocks are 3-mi squares, so a prediction is always for ground the areas never saw (the
PUD case). The chosen k is the smallest whose CV error is within one standard error of the minimum
(the 1-SE rule) — more areas than that buy nothing a new well would notice.

Every area is contiguous (only edge-adjacent regions ever merge) and the areas tile
the extent exactly. Coordinates are UTM 13N feet (box.edge_gap.to_ft) throughout.
"""

from __future__ import annotations

import heapq
import math
from dataclasses import dataclass
from typing import Any

import numpy as np
import pandas as pd
import shapely
from scipy.sparse import coo_matrix
from scipy.sparse.csgraph import connected_components
from scipy.spatial import cKDTree
from shapely.geometry import Polygon

FT_PER_MI = 5280.0


@dataclass(frozen=True)
class AreaParams:
    cell_ft: float = FT_PER_MI  # hex centre spacing (1 mi; hex area 0.87 sq mi)
    knn: int = 15  # wells behind each cell's smoothed field value
    prior_w: float = 0.25  # weight of a cell's field pseudo-observation (wells weigh 1)
    min_wells: int = 10  # D9 minimum area cohort
    k_max: int = 60  # deepest partition explored
    folds: int = 5
    block_ft: float = 3 * FT_PER_MI  # CV hold-out block (square side)
    seed: int = 20261009


DEFAULT = AreaParams()


# ----------------------------------------------------------------------------
# Cells
# ----------------------------------------------------------------------------


def hex_cells(extent: Any, spacing_ft: float) -> tuple[list[Any], np.ndarray]:
    """Pointy-top hexagons on a lattice of centre spacing `spacing_ft`, clipped to the extent.
    Returns (clipped cell polygons, lattice centres [n, 2]). Cells with no area inside are dropped."""
    R = spacing_ft / math.sqrt(3.0)
    dy = 1.5 * R
    x0, y0, x1, y1 = extent.bounds
    ang = np.radians(30.0 + 60.0 * np.arange(6))
    ux, uy = R * np.cos(ang), R * np.sin(ang)
    centres, hexes = [], []
    for j, y in enumerate(np.arange(y0 - dy, y1 + dy, dy)):
        off = 0.5 * spacing_ft if j % 2 else 0.0
        for x in np.arange(x0 - spacing_ft + off, x1 + spacing_ft, spacing_ft):
            centres.append((x, y))
            hexes.append(Polygon(np.column_stack([x + ux, y + uy])))
    hexes_a = np.asarray(hexes, dtype=object)
    shapely.prepare(extent)
    hit = shapely.intersects(extent, hexes_a)
    clipped = shapely.intersection(hexes_a[hit], extent)
    keep = shapely.area(clipped) > 1.0
    return list(clipped[keep]), np.asarray(centres)[hit][keep]


def adjacency(cells: list[Any], centres: np.ndarray, spacing_ft: float) -> np.ndarray:
    """Edge-adjacent cell pairs [m, 2] (lattice neighbours whose clipped polygons share a boundary
    segment), with isolated slivers linked to their nearest cell so the graph is one component."""
    tree = cKDTree(centres)
    pairs = np.asarray(sorted(tree.query_pairs(spacing_ft * 1.01)), dtype=int).reshape(-1, 2)
    ca = np.asarray(cells, dtype=object)
    if len(pairs):
        # cells are built independently, so shared edges differ by float noise: test the overlap of a
        # 1-ft buffer instead of a boundary intersection (>= ~200 ft of common edge = adjacent)
        shared = shapely.area(shapely.intersection(shapely.buffer(ca[pairs[:, 0]], 1.0), ca[pairs[:, 1]]))
        pairs = pairs[shared > 200.0]
    n = len(cells)
    while True:
        g = coo_matrix((np.ones(len(pairs)), (pairs[:, 0], pairs[:, 1])), shape=(n, n)) if len(pairs) else coo_matrix((n, n))
        nc, lab = connected_components(g, directed=False)
        if nc <= 1:
            return pairs
        sizes = np.bincount(lab)
        small = int(np.argmin(sizes))
        inside = np.flatnonzero(lab == small)
        other = np.flatnonzero(lab != small)
        d, j = cKDTree(centres[other]).query(centres[inside])
        i = int(np.argmin(d))
        pairs = np.vstack([pairs, [inside[i], other[j[i]]]])


def cell_of(cells: list[Any], xy: np.ndarray) -> np.ndarray:
    """Index of the cell containing each point (-1 = outside every cell)."""
    out = np.full(len(xy), -1, dtype=int)
    if not len(xy):
        return out
    tree = shapely.STRtree(cells)
    pi, ci = tree.query(shapely.points(xy), predicate="within")
    out[pi] = ci
    # a point exactly on a shared boundary is 'within' neither: take an intersecting cell
    miss = np.flatnonzero(out < 0)
    if len(miss):
        pi2, ci2 = tree.query(shapely.points(xy[miss]), predicate="intersects")
        out[miss[pi2]] = ci2
    return out


# ----------------------------------------------------------------------------
# Field + contiguity-constrained Ward agglomeration
# ----------------------------------------------------------------------------


def knn_field(centres: np.ndarray, wxy: np.ndarray, y: np.ndarray, k: int) -> np.ndarray:
    """Median of y over the k nearest wells to each cell centre."""
    k = min(k, len(y))
    _, idx = cKDTree(wxy).query(centres, k=k)
    idx = idx.reshape(len(centres), -1)
    return np.median(y[idx], axis=1)


def ward_contiguous(pairs: np.ndarray, cell_n: np.ndarray, cell_s: np.ndarray, field: np.ndarray, prior_w: float, min_wells: int, k_max: int) -> list[np.ndarray]:
    """Bottom-up merging of ADJACENT regions, cheapest Ward cost first, from single cells to one area.

    Each cell carries its wells (count, sum of log response) plus a pseudo-observation of the
    smoothed field with weight prior_w, so empty cells join the neighbour they resemble instead of
    gluing on arbitrarily. While any region holds < min_wells real wells, only merges involving such
    a region are taken (the D9 floor is met before any free merge). Merges are nested; the labels of
    every partition with k <= k_max regions (all at the floor) are returned, index 0 = k 1.
    Ward cost of merging A and B = W_A W_B / (W_A + W_B) × (mean_A − mean_B)²."""
    n = len(cell_n)
    W = cell_n.astype(float) + prior_w
    S = cell_s.astype(float) + prior_w * field
    N = cell_n.astype(float).copy()
    ver = np.zeros(n, dtype=int)
    alive = np.ones(n, dtype=bool)
    members: list[list[int]] = [[i] for i in range(n)]
    nbr: list[set[int]] = [set() for _ in range(n)]
    for a, b in pairs.tolist():
        if a != b:
            nbr[a].add(b)
            nbr[b].add(a)

    def key(a: int, b: int) -> tuple[int, float]:
        small = N[a] < min_wells or N[b] < min_wells
        d = S[a] / W[a] - S[b] / W[b]
        return (0 if small else 1, W[a] * W[b] / (W[a] + W[b]) * d * d)

    heap: list[tuple[int, float, int, int, int, int]] = []
    for a in range(n):
        for b in nbr[a]:
            if a < b:
                c, cost = key(a, b)
                heap.append((c, cost, a, b, 0, 0))
    heapq.heapify(heap)
    n_small = int(np.sum(N < min_wells))
    regions = n
    out: dict[int, np.ndarray] = {}

    def snapshot() -> np.ndarray:
        lab = np.empty(n, dtype=int)
        for i, r in enumerate(np.flatnonzero(alive)):
            lab[members[r]] = i
        return lab

    while regions > 1 and heap:
        c, _, a, b, va, vb = heapq.heappop(heap)
        if not (alive[a] and alive[b]) or ver[a] != va or ver[b] != vb:
            continue
        if len(members[a]) < len(members[b]):
            a, b = b, a
        n_small -= int(N[a] < min_wells) + int(N[b] < min_wells)
        W[a] += W[b]
        S[a] += S[b]
        N[a] += N[b]
        n_small += int(N[a] < min_wells)
        members[a].extend(members[b])
        members[b] = []
        alive[b] = False
        ver[a] += 1
        for x in nbr[b]:
            nbr[x].discard(b)
            if x != a:
                nbr[x].add(a)
                nbr[a].add(x)
        nbr[a].discard(b)
        nbr[b] = set()
        for x in nbr[a]:
            cc, cost = key(a, x)
            lo, hi = (a, x) if a < x else (x, a)
            heapq.heappush(heap, (cc, cost, lo, hi, ver[lo], ver[hi]))
        regions -= 1
        if regions <= k_max and n_small == 0:
            out[regions] = snapshot()
    # keys stay exact: a region's sub-floor status changes only when it merges, and every merge
    # re-pushes all of the merged region's pairs (older entries die on the version check)
    return [out[k] for k in sorted(out)]


# ----------------------------------------------------------------------------
# Build + cross-validation
# ----------------------------------------------------------------------------


def build(centres: np.ndarray, pairs: np.ndarray, wcell: np.ndarray, wxy: np.ndarray, y: np.ndarray, p: AreaParams) -> list[np.ndarray]:
    """Partitions k = 1..K of the cells from the wells (wcell = cell index per well, y = log response)."""
    n = len(centres)
    field = knn_field(centres, wxy, y, p.knn)
    cn = np.bincount(wcell, minlength=n).astype(float)
    cs = np.bincount(wcell, weights=y, minlength=n)
    return ward_contiguous(pairs, cn, cs, field, p.prior_w, p.min_wells, p.k_max)


def area_medians(labels: np.ndarray, wcell: np.ndarray, y: np.ndarray) -> np.ndarray:
    k = int(labels.max()) + 1
    wl = labels[wcell]
    return np.asarray([np.median(y[wl == a]) if np.any(wl == a) else np.nan for a in range(k)])


def blocks(wxy: np.ndarray, p: AreaParams) -> np.ndarray:
    """3-mi square block id per well."""
    bx = np.floor(wxy[:, 0] / p.block_ft).astype(np.int64)
    by = np.floor(wxy[:, 1] / p.block_ft).astype(np.int64)
    _, inv = np.unique(np.column_stack([bx, by]), axis=0, return_inverse=True)
    return inv.ravel()


def block_folds(wxy: np.ndarray, p: AreaParams) -> np.ndarray:
    """Fold id per well: 3-mi square blocks dealt round-robin to folds in a seeded random order."""
    blk = blocks(wxy, p)
    perm = np.random.default_rng(p.seed).permutation(int(blk.max()) + 1)
    return (perm % p.folds)[blk]


def cross_validate(centres: np.ndarray, pairs: np.ndarray, wcell: np.ndarray, wxy: np.ndarray, y: np.ndarray, p: AreaParams) -> dict[str, Any]:
    """Blocked CV of the area-median predictor for every k, plus two references: k = 1 (one pool
    median) and the local kNN median of the training wells (what a no-areas local estimate gets)."""
    fold = block_folds(wxy, p)
    sq = np.full((p.k_max, len(y)), np.nan)
    knn_sq = np.full(len(y), np.nan)
    for f in range(p.folds):
        te = fold == f
        tr = ~te
        parts = build(centres, pairs, wcell[tr], wxy[tr], y[tr], p)
        for k in range(p.k_max):
            lab = parts[min(k, len(parts) - 1)]
            med = area_medians(lab, wcell[tr], y[tr])
            sq[k, te] = (y[te] - med[lab[wcell[te]]]) ** 2
        kk = min(p.knn, int(tr.sum()))
        _, idx = cKDTree(wxy[tr]).query(wxy[te], k=kk)
        knn_sq[te] = (y[te] - np.median(y[tr][idx.reshape(int(te.sum()), -1)], axis=1)) ** 2
    cv = pd.DataFrame({"k": np.arange(1, p.k_max + 1), "mse": np.nanmean(sq, axis=1)})
    # PAIRED standard error vs the CV minimum: the same held-out wells scored at k and at k_min,
    # differences summed per 3-mi block (neighbouring wells are not independent), SE over blocks.
    # The fold-to-fold spread is NOT the yardstick: folds differ in how hard their ground is, which
    # is the same for every k and would swamp the k-to-k difference.
    blk = blocks(wxy, p)
    nb = int(blk.max()) + 1
    i_min = int(np.nanargmin(cv["mse"].to_numpy()))
    se = []
    for k in range(p.k_max):
        dsum = np.bincount(blk, weights=sq[k] - sq[i_min], minlength=nb)
        cnt = np.bincount(blk, minlength=nb)
        se.append(float(np.std(dsum[cnt > 0], ddof=1) * math.sqrt(int(np.sum(cnt > 0))) / len(y)))
    cv["se_paired"] = se
    var = float(np.var(y))
    cv["r2"] = 1.0 - cv["mse"] / var
    return {"cv": cv, "knn_mse": float(np.mean(knn_sq)), "var": var, "fold": fold}


def choose_k(cv: pd.DataFrame) -> dict[str, int]:
    """k_min = argmin CV error; k_1se = smallest k whose CV error is within one PAIRED standard
    error of the minimum's (mse_k - mse_min <= se_paired_k) — the pick."""
    i = int(cv["mse"].idxmin())
    ok = (cv["mse"] - cv.loc[i, "mse"]) <= cv["se_paired"]
    return {"k_min": int(cv.loc[i, "k"]), "k_1se": int(cv.loc[ok, "k"].min())}


def dissolve(cells: list[Any], labels: np.ndarray, centres: np.ndarray) -> tuple[list[Any], np.ndarray]:
    """Union cells per label; areas renumbered 1..k north → south (by centroid y, then x).
    Returns (area polygons in area_no order, cell → area_no)."""
    k = int(labels.max()) + 1
    ca = np.asarray(cells, dtype=object)
    geoms = [shapely.union_all(ca[labels == a]) for a in range(k)]
    cy = [g.centroid.y for g in geoms]
    cx = [g.centroid.x for g in geoms]
    order = sorted(range(k), key=lambda a: (-round(cy[a] / 2640.0), cx[a]))
    remap = np.empty(k, dtype=int)
    for no, a in enumerate(order, start=1):
        remap[a] = no
    return [geoms[a] for a in order], remap[labels]
