"""BOX sticks, phase 2b: the no-place envelope, calibrated on where operators drilled children next to parents
(read-only) -- docs/box_sticks_plan.md, bars in docs/box_sticks/phase2b-2026-11-13/BARS.md (committed before the first run).

    python -m scripts.box_sticks_phase2b --out docs/box_sticks/phase2b-<date> --cache <phase 0 cache>
        [--prox-runs <main checkout>/runs] [--steps links,check,rates,envelopes,dean,stagger,d150,novi,figures]

Pair metric = box/prox_study.py's (child-relative overlap, median gap over the shared length, dz = parent - child),
computed with the phase 2a array method (`links`, parallel within the deal-intake tolerance) across ALL benches of a
basin; `metric_check` holds it to prox_study.pair_signed (bar B1). Children, parents, classes, the relative drilling
rate r and bars B1-B5 are defined in BARS.md. PROPOSED is the envelope put to Michael; it was written after the rate
profiles were read (the bars were not). Nothing is written to the warehouse.
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import pickle
from collections.abc import Callable
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import shapely

from box import prox_cont as pc
from box import prox_study as ps
from box import tag_scoreboard as sb
from scripts import box_sticks_phase0 as p0
from scripts import box_sticks_phase2a as p2a

FT_PER_M = p0.FT_PER_M
GATE_FT = ps.PAIR_GATE_FT           # 2,640 ft sideways
STORE_DV_FT = ps.STORE_DV_FT        # 1,500 ft vertically
STORE_OV = 0.05                     # links are stored from 5 % alongside; a qualifying link needs MIN_OV
MIN_OV = ps.MIN_OVERLAP             # 0.30
TOL_DEG = p2a.TOL_DEG
SAMPLES = p2a.SAMPLES
SAME_DV_FT = pc.SAME_DV_FT          # 150 ft: same landing by depth (D150 / 21a revision 3)
STAGGER_FT = p2a.STAGGER_FT         # 75 ft: two landings inside one tag (phase 2a)
REF_FT = (1000.0, 2000.0)           # the reference band of the relative drilling rate
RARE = 0.25                         # B2
MIN_EXPECTED = 30.0                 # B2
B3_BASIN_PCT, B3_BENCH_PCT, B3_BENCH_MIN = 2.0, 5.0, 200
B4_DF, B4_DLEVEL = 0.02, 0.01
B1_AGREE_PCT, B1_RECALL_PCT = 99.0, 97.0
DH_EDGES = np.arange(0.0, GATE_FT + 1, 100.0)
DZ_BANDS = [(-1050.0 + 100 * k, -950.0 + 100 * k) for k in range(9)] + [(-SAME_DV_FT, SAME_DV_FT)] + [(150.0 + 100 * k, 250.0 + 100 * k) for k in range(9)]
SEED = 20261113
FOCUS = p2a.FOCUS
RULE_OF_RECORD = {"delaware": "R2", "midland": "R3"}   # D150

_STATUS_SQL = "SELECT stick_id, status FROM curated.reconciled_inventory"
_RECORD_SQL = """
SELECT f.stick_id, f.run_id, f.coverage, p.outcome, p.factor, p.n_parents_total
FROM box.forecast_run r
JOIN box.pud_forecast f USING (run_id)
LEFT JOIN box.pud_proximity p ON p.run_id = f.run_id AND p.location_id = f.location_id
WHERE r.is_record
"""


# ----------------------------------------------------------------------------
# Envelopes: masks over qualifying links (overlap >= MIN_OV unless the envelope says otherwise)
# ----------------------------------------------------------------------------


def _same(q: pd.DataFrame, dv: float, dh: float, ov: float = MIN_OV) -> np.ndarray:
    return ((q["dz_ft"].abs() <= dv) & (q["dh_ft"] <= dh) & (q["overlap"] >= ov)).to_numpy()


def _vert(q: pd.DataFrame, top: float, under: float, dh: float, ov: float = MIN_OV) -> np.ndarray:
    dz = q["dz_ft"]
    return ((((dz > SAME_DV_FT) & (dz <= top)) | ((dz < -SAME_DV_FT) & (dz >= -under))) & (q["dh_ft"] <= dh) & (q["overlap"] >= ov)).to_numpy()


STARTING: dict[str, Callable[[pd.DataFrame], np.ndarray]] = {
    "21a floor (<=150 ft vt, <=400 ft hz)": lambda q: _same(q, 150.0, 400.0),
    "D112 vertical (topfill 800 / underfill 500 ft, <=1,400 ft hz)": lambda q: _vert(q, 800.0, 500.0, 1400.0),
    "D112 vertical at <=400 ft hz (extra, not in the bars)": lambda q: _vert(q, 800.0, 500.0, 400.0),
    "deal-intake v14 (<=300 ft vt, <=800 ft hz)": lambda q: _same(q, 300.0, 800.0),
}
# Candidates, per basin: (same-landing sideways limit ft, stacked rectangles [(dz lo, dz hi, sideways limit ft)], dz =
# parent depth - child depth). Written AFTER the rate profiles were read (the bars were not); see FINDINGS.md.
Spec = dict[str, tuple[float, list[tuple[float, float, float]]]]
_BOTH = ("delaware", "midland")
CANDIDATES: dict[str, Spec] = {
    "A same landing 400 ft": {b: (400.0, []) for b in _BOTH},
    "B same landing 600 ft": {b: (600.0, []) for b in _BOTH},
    "C same landing 600 ft + stacked 150-350 ft within 300 ft": {b: (600.0, [(-350.0, -150.0, 300.0), (150.0, 350.0, 300.0)]) for b in _BOTH},
    "D same landing 400 ft + stacked within 300 ft (B2 cells)": {"delaware": (400.0, [(-250.0, -150.0, 300.0), (150.0, 350.0, 300.0)]),
                                                                 "midland": (400.0, [(-350.0, -150.0, 300.0), (150.0, 350.0, 300.0)])},
    "E same landing 600 ft + every B2 stacked cell": {"delaware": (600.0, [(-250.0, -150.0, 300.0), (150.0, 350.0, 300.0)]),
                                                      "midland": (600.0, [(-550.0, -150.0, 300.0), (150.0, 350.0, 300.0)])},
}
RECOMMENDED = "D same landing 400 ft + stacked within 300 ft (B2 cells)"
PROPOSED: Spec = CANDIDATES[RECOMMENDED]


def spec_mask(Q: pd.DataFrame, spec: Spec) -> np.ndarray:
    m = np.zeros(len(Q), bool)
    for basin in spec:
        b = (Q["basin"] == basin).to_numpy()
        if b.any():
            m[b] = proposed_mask(Q[b], basin, spec)
    return m


def spec_region_r(Q: pd.DataFrame, spec: Spec, mask: np.ndarray) -> dict[str, float]:
    """r of a candidate as ONE region per basin: links inside it over the links its footprint holds at the reference level."""
    out = {}
    dz, far = Q["dz_ft"], ((Q["dh_ft"] >= REF_FT[0]) & (Q["dh_ft"] < REF_FT[1])).to_numpy()
    for basin, (dh_same, rects) in spec.items():
        b = (Q["basin"] == basin).to_numpy()
        exp = float((b & far & (dz.abs() <= SAME_DV_FT).to_numpy()).sum()) / 1000.0 * dh_same
        for lo, hi, w in rects:
            exp += float((b & far & ((dz > lo) & (dz <= hi)).to_numpy()).sum()) / 1000.0 * w
        out[basin] = float((mask & b).sum() / exp) if exp > 0 else np.nan
    return out


def proposed_mask(q: pd.DataFrame, basin: str, spec: dict | None = None) -> np.ndarray:
    dh_same, rects = (spec or PROPOSED)[basin]
    m = _same(q, SAME_DV_FT, dh_same).copy()
    for lo, hi, dh in rects:
        m |= ((q["dz_ft"] > lo) & (q["dz_ft"] <= hi) & (q["dh_ft"] <= dh) & (q["overlap"] >= MIN_OV)).to_numpy()
    return m


# ----------------------------------------------------------------------------
# The pair table
# ----------------------------------------------------------------------------


def _axis(g: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    first = shapely.get_coordinates(shapely.get_point(g, 0))
    last = shapely.get_coordinates(shapely.get_point(g, -1))
    dx, dy = last[:, 0] - first[:, 0], last[:, 1] - first[:, 1]
    return np.hypot(dx, dy) >= 1.0, np.degrees(np.arctan2(dx, dy)) % 180.0


def links(A: np.ndarray, B: np.ndarray, same: bool, search_ft: float = GATE_FT, overlap_min: float = STORE_OV) -> pd.DataFrame:
    """Directed links child i (in A) -> candidate j (in B): overlap = share of i's along-axis length that j spans,
    dh_ft = median distance from i's sample points inside the shared length to line j, side = +1 / -1 by the gunbarrel
    sign rule v2 (+ = the NE half). Lines in EPSG:3083 metres. `same` = A and B are the same array (i != j)."""
    okA, azA = _axis(A)
    okB, azB = _axis(B)
    ux, uy = np.sin(np.radians(azA)), np.cos(np.radians(azA))
    i, j = shapely.STRtree(B).query(shapely.buffer(A, search_ft / FT_PER_M))
    keep = okA[i] & okB[j]
    if same:
        keep &= i != j
    i, j = i[keep], j[keep]
    d = np.abs(azA[i] - azB[j])
    keep = np.minimum(d, 180.0 - d) <= TOL_DEG
    i, j = i[keep], j[keep]
    c, ci = shapely.get_coordinates(A, return_index=True)
    al = c[:, 0] * ux[ci] + c[:, 1] * uy[ci]
    lo, hi = np.full(len(A), np.inf), np.full(len(A), -np.inf)
    np.minimum.at(lo, ci, al)
    np.maximum.at(hi, ci, al)
    cross = ux[ci] * c[:, 1] - uy[ci] * c[:, 0]            # > 0 = left of the folded heading
    crossA = np.bincount(ci, cross, len(A)) / np.maximum(np.bincount(ci, minlength=len(A)), 1)
    parts = []
    fr = np.linspace(0.0, 1.0, SAMPLES)
    for a in range(0, len(i), 200_000):
        ii, jj = i[a:a + 200_000], j[a:a + 200_000]
        cj, pj = shapely.get_coordinates(B[jj], return_index=True)
        aj = cj[:, 0] * ux[ii][pj] + cj[:, 1] * uy[ii][pj]
        jlo, jhi = np.full(len(ii), np.inf), np.full(len(ii), -np.inf)
        np.minimum.at(jlo, pj, aj)
        np.maximum.at(jhi, pj, aj)
        cr = np.bincount(pj, ux[ii][pj] * cj[:, 1] - uy[ii][pj] * cj[:, 0], len(ii)) / np.maximum(np.bincount(pj, minlength=len(ii)), 1)
        olo, ohi = np.maximum(lo[ii], jlo), np.minimum(hi[ii], jhi)
        span = hi[ii] - lo[ii]
        frac = np.where(span > 0, (ohi - olo) / np.where(span > 0, span, 1.0), 0.0)
        k = (ohi > olo) & (frac >= overlap_min)
        ii, jj, olo, ohi, frac, cr = ii[k], jj[k], olo[k], ohi[k], frac[k], cr[k]
        pts = shapely.line_interpolate_point(A[ii][:, None], fr[None, :], normalized=True)
        pal = shapely.get_x(pts) * ux[ii][:, None] + shapely.get_y(pts) * uy[ii][:, None]
        dist = shapely.distance(pts, B[jj][:, None]) * FT_PER_M
        dist[(pal < olo[:, None] - 1e-6) | (pal > ohi[:, None] + 1e-6)] = np.nan
        with np.errstate(all="ignore"):
            dh = np.nanmedian(dist, axis=1)
        right = np.where(cr - crossA[ii] < 0, 1.0, -1.0)
        side = np.where(np.round(azA[ii], 1) <= 45.0, right, -right)   # rule 16 v2: + = a + 90 deg if a <= 45, else a - 90
        parts.append(pd.DataFrame({"i": ii, "j": jj, "dh_ft": dh, "overlap": np.minimum(frac, 1.0), "side": side}))
    t = pd.concat(parts, ignore_index=True) if parts else pd.DataFrame(columns=["i", "j", "dh_ft", "overlap", "side"])
    return t[t["dh_ft"].notna() & (t["dh_ft"] <= search_ft)].reset_index(drop=True)


def well_links(u: pd.DataFrame) -> pd.DataFrame:
    """Every link from a child (measured population) to another universe well of its basin, with age, depth and class."""
    parts = []
    for basin, g in u.groupby("basin"):
        ix = g.index.to_numpy()
        kid = np.flatnonzero(g["measured_pop"].to_numpy())
        t = links(g["geom"].to_numpy()[kid], g["geom"].to_numpy(), same=False)
        t["i"], t["j"] = ix[kid][t["i"].to_numpy()], ix[t["j"].to_numpy()]
        parts.append(t[t["i"] != t["j"]])
        print(f"  {basin}: {len(t):,} links", flush=True)
    L = pd.concat(parts, ignore_index=True)
    i, j = L["i"].to_numpy(), L["j"].to_numpy()
    fp = u["fp"].to_numpy()
    L["age_days"] = ((fp[i] - fp[j]) / np.timedelta64(1, "D")).astype(int)
    L["rel"] = np.where(L["age_days"] < -ps.CODEV_DAYS, "child", np.where(L["age_days"] <= ps.CODEV_DAYS, "codev", np.where(L["age_days"] >= ps.PARENT_MIN_DAYS, "parent", "young")))
    z = u["depth_ft"].to_numpy(float)
    L["judged"] = (u["clean"].to_numpy(bool) & (u["screen"].to_numpy() != "bad_depth"))[j]
    L["dz_ft"] = np.where(L["judged"], z[j] - z[i], np.nan)
    for c, src in (("basin", "basin"), ("child_bench", "live")):
        L[c] = u[src].to_numpy()[i]
    L["parent_bench"] = u["live"].to_numpy()[j]
    L["child"], L["parent"] = u["api10"].to_numpy()[i], u["api10"].to_numpy()[j]
    L["cls"] = np.where(L["dz_ft"].isna(), "unjudged", np.where(L["dz_ft"].abs() <= SAME_DV_FT, "same", np.where(L["dz_ft"] > 0, "topfill", "underfill")))
    return L[(L["dz_ft"].abs() <= STORE_DV_FT) | L["dz_ft"].isna()].reset_index(drop=True)


def qualifying(L: pd.DataFrame, min_ov: float = MIN_OV) -> pd.DataFrame:
    return L[(L["rel"] == "parent") & L["judged"] & (L["overlap"] >= min_ov)]


# ----------------------------------------------------------------------------
# B1: the array metric against prox_study.pair_signed
# ----------------------------------------------------------------------------


def _feet(g: shapely.Geometry) -> shapely.Geometry:
    return shapely.transform(g, lambda c: c * FT_PER_M)


def metric_check(u: pd.DataFrame, L_all: pd.DataFrame, n_links: int = 2000, n_children: int = 300) -> list[dict]:
    """Agreement on a sample of stored PARENT links; recall against EVERY stored link (the recall candidates carry no
    age filter). The first run compared recall against parent links only (a fault in this check, fixed; see FINDINGS)."""
    rng = np.random.default_rng(SEED)
    geom = u["geom"].to_numpy()
    rows = []
    for basin, g_all in L_all.groupby("basin"):
        g = g_all[g_all["rel"] == "parent"]
        s = g.iloc[rng.choice(len(g), size=min(n_links, len(g)), replace=False)]
        ref = [ps.pair_signed(_feet(geom[i]), _feet(geom[j])) for i, j in zip(s["i"], s["j"], strict=True)]
        ov = np.array([r[0] for r in ref], float)
        dh = np.array([np.nan if r[1] is None else r[1] for r in ref], float)
        ok = np.isfinite(dh) & (np.abs(dh - s["dh_ft"].to_numpy()) <= np.maximum(5.0, 0.005 * dh)) & (np.abs(ov - s["overlap"].to_numpy()) <= 0.02)
        ok_gap = np.isfinite(dh) & (np.abs(dh - s["dh_ft"].to_numpy()) <= np.maximum(5.0, 0.005 * dh))
        # recall: prox_study links of random children that the array table also holds
        ub = u[u["basin"] == basin]
        kids = rng.choice(ub.index[ub["measured_pop"].to_numpy()].to_numpy(), size=n_children, replace=False)
        tree = shapely.STRtree(ub["geom"].to_numpy())
        have = set(zip(g_all["i"], g_all["j"], strict=True))
        want = found = lost_parallel = 0
        _, az = _axis(geom)
        z, judged = u["depth_ft"].to_numpy(float), (u["clean"].to_numpy(bool) & (u["screen"].to_numpy() != "bad_depth"))
        for i in kids:
            cf = _feet(geom[i])
            for jj in tree.query(shapely.buffer(geom[i], 1400.0 / FT_PER_M)):
                j = ub.index[jj]
                if j == i or not judged[j] or abs(z[j] - z[i]) > 1000.0:
                    continue
                o, d, _ = ps.pair_signed(cf, _feet(geom[j]))
                if d is None or o < MIN_OV or d > 1400.0:
                    continue
                want += 1
                if (i, j) in have:
                    found += 1
                else:
                    dd = abs(az[i] - az[j])
                    lost_parallel += int(min(dd, 180 - dd) > TOL_DEG)
        both = np.isfinite(dh) & (s["overlap"].to_numpy() >= MIN_OV) & (ov >= MIN_OV)
        mine = s["dh_ft"].to_numpy()
        scale = {"same_side_of_30pct_alongside_pct": 100 * float(((s["overlap"].to_numpy() >= MIN_OV) == (ov >= MIN_OV)).mean()),
                 "qualifying_gap_within_25ft_pct": 100 * float((np.abs(mine - dh)[both] <= 25).mean()),
                 **{f"qualifying_same_side_of_{x}ft_pct": 100 * float(((mine <= x) == (dh <= x))[both].mean()) for x in (200, 300, 400, 600)},
                 "overlap_abs_diff_p95": float(np.nanquantile(np.abs(s["overlap"].to_numpy() - ov), .95)), "gap_abs_diff_p95_ft": float(np.nanquantile(np.abs(mine - dh), .95))}
        rows.append({"basin": basin, **scale, "links_sampled": len(s), "agree_pct": 100 * float(ok.mean()), "gap_agree_pct": 100 * float(ok_gap.mean()),
                     "median_gap_diff_ft": float(np.nanmedian(s["dh_ft"].to_numpy() - dh)), "median_overlap_diff": float(np.nanmedian(s["overlap"].to_numpy() - ov)),
                     "pass_agree": bool(100 * ok.mean() >= B1_AGREE_PCT), "recall_children": len(kids), "recall_links": want, "recall_pct": 100 * found / max(want, 1),
                     "recall_lost_not_parallel": lost_parallel, "pass_recall": bool(100 * found / max(want, 1) >= B1_RECALL_PCT)})
    return rows


# ----------------------------------------------------------------------------
# Relative drilling rate
# ----------------------------------------------------------------------------


def rate(dh: np.ndarray, edges: np.ndarray = DH_EDGES) -> pd.DataFrame:
    """Links per foot of sideways gap in each bin over the same at REF_FT (r); `expected` = links the bin would hold at
    the reference level."""
    n = np.histogram(dh, edges)[0]
    ref = float(((dh >= REF_FT[0]) & (dh < REF_FT[1])).sum()) / (REF_FT[1] - REF_FT[0])
    exp = ref * np.diff(edges)
    return pd.DataFrame({"dh_lo": edges[:-1], "dh_hi": edges[1:], "links": n, "expected": exp, "r": np.where(exp > 0, n / np.where(exp > 0, exp, 1.0), np.nan),
                         "resolved": exp >= MIN_EXPECTED})


def region_rate(q: pd.DataFrame, dh_max: float) -> tuple[int, float, float]:
    """(links inside dh_max, expected at the reference level, r) for one group of links taken as one region."""
    dh = q["dh_ft"].to_numpy()
    exp = float(((dh >= REF_FT[0]) & (dh < REF_FT[1])).sum()) / (REF_FT[1] - REF_FT[0]) * dh_max
    n = int((dh <= dh_max).sum())
    return n, exp, (n / exp if exp > 0 else np.nan)


def band_label(lo: float, hi: float) -> str:
    return "same landing" if lo == -SAME_DV_FT else (f"parent {lo:,.0f}-{hi:,.0f} ft deeper" if lo > 0 else f"parent {-hi:,.0f}-{-lo:,.0f} ft shallower")


def rate_tables(Q: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    """(profiles by basin x vertical band, by basin x bench pair x class, first-not-rare edge per basin x band)."""
    prof, edge = [], []
    for basin, g in Q.groupby("basin"):
        for lo, hi in DZ_BANDS:
            b = g[(g["dz_ft"] > lo) & (g["dz_ft"] <= hi)] if lo != -SAME_DV_FT else g[g["dz_ft"].abs() <= SAME_DV_FT]
            t = rate(b["dh_ft"].to_numpy())
            t.insert(0, "band", band_label(lo, hi))
            t.insert(0, "dz_hi", hi)
            t.insert(0, "dz_lo", lo)
            t.insert(0, "basin", basin)
            prof.append(t)
            ok = t[t["resolved"]]
            rare = ok[ok["r"] < RARE]
            first_ok = ok.loc[ok["r"] >= RARE, "dh_lo"].min() if (ok["r"] >= RARE).any() else np.nan
            edge.append({"basin": basin, "dz_lo": lo, "dz_hi": hi, "band": band_label(lo, hi), "links": len(b), "expected_per_100ft": float(t["expected"].iloc[0]),
                         "resolved": bool(len(ok)), "rare_bins": ", ".join(f"{int(a)}-{int(a) + 100}" for a in rare["dh_lo"]),
                         "first_not_rare_ft": first_ok, "r_0_200": region_rate(b, 200.0)[2], "r_0_400": region_rate(b, 400.0)[2], "r_400_800": float(t.loc[(t["dh_lo"] >= 400) & (t["dh_lo"] < 800), "r"].mean())})
    pair = []
    for (basin, cb, pb, cls), g in Q.groupby(["basin", "child_bench", "parent_bench", "cls"]):
        o = {"basin": basin, "child_bench": cb, "parent_bench": pb, "cls": cls, "children": g["child"].nunique(), "links": len(g), "median_dz_ft": float(g["dz_ft"].median()),
             "dz_p10_ft": float(g["dz_ft"].quantile(.1)), "dz_p90_ft": float(g["dz_ft"].quantile(.9)), "nearest_gap_p05_ft": float(g.groupby("child")["dh_ft"].min().quantile(.05)),
             "nearest_gap_median_ft": float(g.groupby("child")["dh_ft"].min().median())}
        for dh in (200.0, 300.0, 400.0, 800.0):
            n, exp, r = region_rate(g, dh)
            o |= {f"links_le_{int(dh)}": n, f"expected_le_{int(dh)}": exp, f"r_le_{int(dh)}": r}
        o["resolved_le_400"] = o["expected_le_400"] >= MIN_EXPECTED
        pair.append(o)
    return pd.concat(prof, ignore_index=True), pd.DataFrame(pair).sort_values(["basin", "children"], ascending=[True, False]), pd.DataFrame(edge)


def overlap_table(L: pd.DataFrame) -> pd.DataFrame:
    """The overlap dimension: same-landing parent links by share alongside, close in vs at the reference distance."""
    q = L[(L["rel"] == "parent") & L["judged"] & (L["dz_ft"].abs() <= SAME_DV_FT)]
    rows = []
    for basin, g in q.groupby("basin"):
        for lo, hi in ((0.05, 0.30), (0.30, 0.60), (0.60, 0.90), (0.90, 1.01)):
            b = g[(g["overlap"] >= lo) & (g["overlap"] < hi)]
            o = {"basin": basin, "overlap": f"{int(100 * lo)}-{min(int(100 * hi), 100)} %", "links": len(b)}
            for dh in (200.0, 400.0):
                n, exp, r = region_rate(b, dh)
                o |= {f"links_le_{int(dh)}": n, f"expected_le_{int(dh)}": exp, f"r_le_{int(dh)}": r}
            rows.append(o)
    return pd.DataFrame(rows)


# ----------------------------------------------------------------------------
# Envelope scoring (B3)
# ----------------------------------------------------------------------------


def envelope_region_rate(Q: pd.DataFrame, mask: np.ndarray, far: np.ndarray, area_ft: float) -> float:
    """r of an envelope as one region: links inside it over the links its footprint would hold at the reference level.
    `far` = the same vertical bands at REF_FT; area_ft = the envelope's sideways width in those bands."""
    exp = far.sum() / (REF_FT[1] - REF_FT[0]) * area_ft
    return float(mask.sum() / exp) if exp > 0 else np.nan


def score_envelope(name: str, u: pd.DataFrame, Q: pd.DataFrame, mask: np.ndarray, r_region: dict[str, float]) -> tuple[list[dict], pd.DataFrame]:
    kids = u[u["measured_pop"]]
    hit = Q[mask]
    out_ids = set(hit["child"])
    rows, bench_rows = [], []
    for basin, g in kids.groupby("basin"):
        ex = g["api10"].isin(out_ids)
        bb = g.assign(ex=ex).groupby("live").agg(children=("ex", "size"), excluded=("ex", "sum")).reset_index().rename(columns={"live": "bench"})
        bb["excluded_pct"] = 100 * bb["excluded"] / bb["children"]
        bb.insert(0, "envelope", name)
        bb.insert(0, "basin", basin)
        bench_rows.append(bb)
        big = bb[bb["children"] >= B3_BENCH_MIN]
        worst = big.sort_values("excluded_pct", ascending=False).iloc[0]
        r = r_region.get(basin, np.nan)
        rows.append({"envelope": name, "basin": basin, "children": len(g), "excluded": int(ex.sum()), "excluded_pct": 100 * float(ex.mean()),
                     "worst_bench": worst["bench"], "worst_bench_pct": float(worst["excluded_pct"]), "region_r": r,
                     "rare": bool(r < RARE), "pass_basin": bool(100 * ex.mean() <= B3_BASIN_PCT), "pass_bench": bool(worst["excluded_pct"] <= B3_BENCH_PCT),
                     "B3": bool(r < RARE and 100 * ex.mean() <= B3_BASIN_PCT and worst["excluded_pct"] <= B3_BENCH_PCT)})
    return rows, pd.concat(bench_rows, ignore_index=True)


SWEEP_BANDS = [("same landing", -SAME_DV_FT, SAME_DV_FT)] \
    + [(f"parent {a}-{b} ft deeper", float(a), float(b)) for a, b in ((150, 250), (250, 350), (350, 450), (150, 350), (150, 450))] \
    + [(f"parent {a}-{b} ft shallower", -float(b), -float(a)) for a, b in ((150, 250), (250, 350), (350, 450), (450, 550), (150, 350), (150, 450), (150, 550))]


def sweep(u: pd.DataFrame, Q: pd.DataFrame) -> pd.DataFrame:
    """Rectangles one at a time: children excluded and the rectangle's r as one region. Same landing by sideways limit;
    signed vertical bands by sideways limit."""
    n_kids = u[u["measured_pop"]].groupby("basin").size()
    nb = u[u["measured_pop"]].groupby(["basin", "live"]).size()
    rows = []
    for basin, g in Q.groupby("basin"):
        for label, lo, hi in SWEEP_BANDS:
            b = g[(g["dz_ft"] > lo) & (g["dz_ft"] <= hi)] if label != "same landing" else g[g["dz_ft"].abs() <= SAME_DV_FT]
            for dh in (100.0, 200.0, 300.0, 400.0, 500.0, 600.0, 800.0):
                n, exp, r = region_rate(b, dh)
                inside = b[b["dh_ft"] <= dh]
                per_bench = inside.groupby("child_bench")["child"].nunique()
                size = nb[basin].reindex(per_bench.index)
                share = (100 * per_bench / size)[size >= B3_BENCH_MIN]
                rows.append({"basin": basin, "band": label, "dh_le_ft": dh, "links": n, "expected": exp, "r": r, "rare": bool(r < RARE), "children_excluded": inside["child"].nunique(),
                             "excluded_pct": 100 * inside["child"].nunique() / n_kids[basin], "worst_bench": share.idxmax() if len(share) else None,
                             "worst_bench_pct": float(share.max()) if len(share) else np.nan})
    return pd.DataFrame(rows)


def prox_sensitivity(u: pd.DataFrame, Q: pd.DataFrame) -> list[dict]:
    """The proposed envelope's excluded children when the close-in links are re-measured with prox_study.pair_signed."""
    geom = u["geom"].to_numpy()
    near = Q[(Q["dh_ft"] <= 900.0) & (Q["dz_ft"].abs() <= 600.0)].copy()
    ref = [ps.pair_signed(_feet(geom[i]), _feet(geom[j])) for i, j in zip(near["i"], near["j"], strict=True)]
    alt = near.assign(overlap=[r[0] for r in ref], dh_ft=[np.nan if r[1] is None else r[1] for r in ref])
    rows = []
    for basin in near["basin"].unique():
        a, b = near[near["basin"] == basin], alt[alt["basin"] == basin]
        mine, theirs = set(a.loc[proposed_mask(a, basin), "child"]), set(b.loc[proposed_mask(b, basin), "child"])
        rows.append({"basin": basin, "links_remeasured": len(a), "excluded_array_metric": len(mine), "excluded_prox_study_metric": len(theirs), "in_both": len(mine & theirs)})
    return rows


def region_r_for(Q: pd.DataFrame, name: str, mask: np.ndarray) -> dict[str, float]:
    """The reference count for each envelope's own vertical footprint."""
    out = {}
    dz, dh = Q["dz_ft"], Q["dh_ft"]
    far = (dh >= REF_FT[0]) & (dh < REF_FT[1])
    for basin in Q["basin"].unique():
        b = (Q["basin"] == basin).to_numpy()
        if name.startswith("21a"):
            band, w = dz.abs() <= 150.0, 400.0
        elif name.startswith("deal-intake"):
            band, w = dz.abs() <= 300.0, 800.0
        elif name.startswith("D112"):
            band, w = ((dz > SAME_DV_FT) & (dz <= 800.0)) | ((dz < -SAME_DV_FT) & (dz >= -500.0)), 400.0 if "400" in name else 1400.0
        else:
            raise ValueError(name)
        out[basin] = envelope_region_rate(Q, mask & b, (b & far & band).to_numpy(), w)
    return out


def describe_excluded(u: pd.DataFrame, Q: pd.DataFrame, mask: np.ndarray, L: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    """One row per excluded child (its nearest excluding parent), and the summary by basin."""
    hit = Q[mask].sort_values("dh_ft").drop_duplicates("child")
    uu = u.set_index("api10")
    x = hit[["basin", "child", "parent", "child_bench", "parent_bench", "cls", "dh_ft", "dz_ft", "overlap", "age_days"]].copy()
    for c in ("well_name", "operator", "county", "lateral_length_ft"):
        x[f"child_{c}"] = uu[c].reindex(x["child"]).to_numpy()
    x["parent_well_name"], x["parent_operator"] = uu["well_name"].reindex(x["parent"]).to_numpy(), uu["operator"].reindex(x["parent"]).to_numpy()
    x["child_fp"], x["parent_fp"] = uu["fp"].reindex(x["child"]).to_numpy(), uu["fp"].reindex(x["parent"]).to_numpy()
    x["parent_pre_2012"] = pd.to_datetime(x["parent_fp"]).dt.year < 2012
    x["same_operator"] = x["child_operator"] == x["parent_operator"]
    x["same_tag"] = x["child_bench"] == x["parent_bench"]
    sib = L[(L["rel"] == "codev") & (L["overlap"] >= MIN_OV)].groupby("child")["parent"].nunique()
    x["codev_siblings"] = sib.reindex(x["child"]).fillna(0).astype(int).to_numpy()
    par_len = uu["lateral_length_ft"].reindex(x["parent"]).to_numpy()
    x["parent_lateral_ft"] = par_len
    rows = []
    for basin, g in x.groupby("basin"):
        rows.append({"basin": basin, "excluded_children": len(g), "median_gap_ft": float(g["dh_ft"].median()), "median_abs_dz_ft": float(g["dz_ft"].abs().median()),
                     "median_overlap": float(g["overlap"].median()), "median_parent_age_yr": float(g["age_days"].median() / 365.25),
                     "parent_pre_2012_pct": 100 * float(g["parent_pre_2012"].mean()), "parent_lateral_under_5000_pct": 100 * float((g["parent_lateral_ft"] < 5000).mean()),
                     "same_operator_pct": 100 * float(g["same_operator"].mean()), "same_tag_pct": 100 * float(g["same_tag"].mean()),
                     "with_2plus_codev_siblings_pct": 100 * float((g["codev_siblings"] >= 2).mean()),
                     "top_counties": ", ".join(f"{k} {v}" for k, v in g["child_county"].value_counts().head(4).items()),
                     "top_pairs": ", ".join(f"{a} by {b} {n}" for (a, b), n in g.groupby(["child_bench", "parent_bench"]).size().nlargest(4).items())})
    return x, pd.DataFrame(rows)


# ----------------------------------------------------------------------------
# DEAN (topfill / underfill / sandwich) and the same-bench stagger
# ----------------------------------------------------------------------------


def config_table(u: pd.DataFrame, Q: pd.DataFrame, basin: str, bench: str, dh_max: float = 1400.0, dv_max: float = 1000.0) -> pd.DataFrame:
    kids = u[u["measured_pop"] & (u["basin"] == basin) & (u["live"] == bench)]
    q = Q[(Q["basin"] == basin) & (Q["child_bench"] == bench) & (Q["dh_ft"] <= dh_max) & (Q["dz_ft"].abs() <= dv_max)]
    has = {c: set(q.loc[q["cls"] == c, "child"]) for c in ("same", "topfill", "underfill")}
    lab = []
    for a in kids["api10"]:
        s, t, un = a in has["same"], a in has["topfill"], a in has["underfill"]
        lab.append("none" if not (s or t or un) else "sandwich (parent above and below)" if t and un else
                   ("same landing only" if s and not (t or un) else "parent below only (topfill)" if t else "parent above only (underfill)" if un else "same"))
    k = kids.assign(config=lab)
    k["with_same_landing_parent"] = k["api10"].isin(has["same"])
    out = k.groupby("config").agg(children=("api10", "size"), also_same_landing_parent=("with_same_landing_parent", "sum")).reset_index()
    out["pct"] = 100 * out["children"] / len(k)
    return out.sort_values("children", ascending=False)


def sandwich_uptake(u: pd.DataFrame, pads: pd.DataFrame, extents: pd.DataFrame, asof: pd.Timestamp, basin: str = "midland", mid: str = "DEAN",
                    above: str = "LSSH", below: str = "WCA_1") -> pd.DataFrame:
    """Revealed preference at DSU grain: of the 2026Q3 polygons inside the `mid` extent, by what was already developed
    above / below (>= 12 months before the cache date), the share that hold a `mid` well, and whether it came with the
    neighbours (within 12 months of the later of them) or >= 12 months after. Wells by lateral midpoint; polygons overlap."""
    from box import landing_surfaces as ls

    eg = shapely.union_all([shapely.make_valid(shapely.from_wkt(e.wkt)) for e in extents[extents["basin"] == basin].itertuples() if mid in ls.extent_codes(basin, e.bench)])
    pb = pads[pads["basin"] == basin]
    geoms = pb["geom"].to_numpy()
    geoms = geoms[np.sort(shapely.STRtree(geoms).query(eg, predicate="intersects"))]
    w = u[(u["basin"] == basin) & u["live"].isin([mid, above, below])]
    a, b = shapely.STRtree(geoms).query(shapely.points(w["x"].to_numpy(), w["y"].to_numpy()), predicate="within")
    t = pd.DataFrame({"pad": b, "bench": w["live"].to_numpy()[a], "fp": w["fp"].to_numpy()[a]})
    first = t.groupby(["pad", "bench"])["fp"].min().unstack()
    for c in (mid, above, below):
        if c not in first:
            first[c] = pd.NaT
    first = first.reindex(range(len(geoms)))
    old = asof - pd.Timedelta(days=365)
    ha, hb = (first[above] <= old).to_numpy(), (first[below] <= old).to_numpy()
    state = np.where(ha & hb, f"{above} above and {below} below", np.where(ha, f"{above} above only", np.where(hb, f"{below} below only", "neither")))
    t0 = pd.concat([first[above].where(ha), first[below].where(hb)], axis=1).max(axis=1)
    lag = (first[mid] - t0).dt.days.to_numpy()
    timing = np.where(first[mid].isna(), f"no {mid} well", np.where(t0.isna(), f"{mid}, nothing older beside it",
                      np.where(lag >= 365, f"{mid} >= 12 months after", np.where(lag > -365, f"{mid} within 12 months", f"{mid} first"))))
    out = pd.crosstab(pd.Series(state, name="developed_12_months_ago"), pd.Series(timing, name="timing"))
    out["dsu"] = out.sum(axis=1)
    col = f"{mid} >= 12 months after"
    out["infilled_later_pct"] = 100 * (out.get(col, 0)) / out["dsu"]
    return out.reset_index()


def examples(u: pd.DataFrame, L: pd.DataFrame, Q: pd.DataFrame) -> list[tuple[str, str, str]]:
    """Real wells where the choice of envelope changes the answer: (api10, title, file name)."""
    out = []
    nlinks = L[L["judged"] & (L["overlap"] >= MIN_OV)].groupby("child").size()

    def pick(q: pd.DataFrame) -> pd.Series | None:
        if not len(q):
            return None
        q = q.assign(n=nlinks.reindex(q["child"]).to_numpy())
        return q.sort_values("n", ascending=False).iloc[0]

    a = pick(Q[(Q["basin"] == "delaware") & (Q["child_bench"] == "BS3_C") & (Q["parent_bench"] == "WCA_1") & (Q["dh_ft"] <= 100) & Q["dz_ft"].between(600, 1000) & (Q["overlap"] >= 0.8)])
    if a is not None:
        out.append((a["child"], (f"Delaware BS3_C drilled {a['dz_ft']:,.0f} ft above a WCA_1 parent, {a['dh_ft']:,.0f} ft sideways: the D112 vertical rule would not place it; "
                    "every candidate would (r about 0.95 for this pair)"), "pad_delaware_BS3C_over_WCA1.png"))
    dn = Q[(Q["basin"] == "midland") & (Q["child_bench"] == "DEAN")]
    ab = dn[(dn["dz_ft"] < -150) & (dn["dz_ft"] >= -450)].groupby("child")["dh_ft"].min()
    be = dn[(dn["dz_ft"] > 150) & (dn["dz_ft"] <= 450)].groupby("child")["dh_ft"].min()
    both = pd.concat([ab, be], axis=1, keys=["a", "b"]).dropna()
    both = both[(both["a"] <= 660) & (both["b"] <= 660)]
    if len(both):
        k = both.assign(n=nlinks.reindex(both.index)).sort_values("n", ascending=False).index[0]
        n_dean = int((u["measured_pop"] & (u["basin"] == "midland") & (u["live"] == "DEAN")).sum())
        out.append((k, (f"Midland DEAN drilled as a sandwich: nearest parent above {both.at[k, 'a']:,.0f} ft sideways, nearest below {both.at[k, 'b']:,.0f} ft "
                    f"(one of {len(both)} such DEAN wells out of {n_dean})"), "pad_midland_DEAN_sandwich.png"))
    m = pick(Q[(Q["basin"] == "midland") & (Q["cls"] == "same") & Q["dh_ft"].between(420, 580) & (Q["overlap"] >= 0.8) & (Q["child_bench"] == Q["parent_bench"])])
    if m is not None:
        out.append((m["child"], f"Midland {m['child_bench']} drilled {m['dh_ft']:,.0f} ft from a same-landing parent: a 600 ft limit would not place it, a 400 ft limit would", "pad_midland_same_landing_400_600.png"))
    st = pick(Q[(Q["basin"] == "delaware") & (Q["dh_ft"] <= 250) & Q["dz_ft"].between(160, 340) & (Q["overlap"] >= 0.8)])
    if st is not None:
        out.append((st["child"], (f"Delaware {st['child_bench']} drilled {st['dz_ft']:,.0f} ft above a {st['parent_bench']} parent, {st['dh_ft']:,.0f} ft sideways: inside the stacked tier; "
                    "a same-landing-only envelope would place it"), "pad_delaware_stacked_tier.png"))
    r = u[u["well_name"].fillna("").str.upper().str.contains("RUTHLESS 11 FED") & (u["live"] == "BS2_S")].sort_values("depth_ft")
    if len(r):
        k = r.iloc[len(r) // 2]["api10"]
        out.append((k, f"Ruthless 11 Federal COM (Lea): {len(r)} BS2_S wells at two landings, all co-developed. No well is a parent of another, so no envelope touches the pad", "pad_ruthless_11.png"))
    return out


def stagger_table(L: pd.DataFrame) -> pd.DataFrame:
    """Same-tag links by vertical gap band: parent links (rate r close in) beside the co-developed count."""
    s = L[L["judged"] & (L["child_bench"] == L["parent_bench"]) & (L["overlap"] >= MIN_OV)]
    rows = []
    for basin, g in s.groupby("basin"):
        for lo, hi in ((0.0, 75.0), (75.0, 150.0), (150.0, 300.0), (300.0, 500.0)):
            b = g[(g["dz_ft"].abs() > lo) & (g["dz_ft"].abs() <= hi)] if lo > 0 else g[g["dz_ft"].abs() <= hi]
            par, cod = b[b["rel"] == "parent"], b[b["rel"] == "codev"]
            o = {"basin": basin, "vertical_gap": f"{int(lo)}-{int(hi)} ft", "parent_links": len(par), "children": par["child"].nunique(),
                 "codev_links_le_660": int((cod["dh_ft"] <= 660).sum())}
            for dh in (200.0, 300.0, 400.0, 660.0):
                n, exp, r = region_rate(par, dh)
                o |= {f"links_le_{int(dh)}": n, f"expected_le_{int(dh)}": exp, f"r_le_{int(dh)}": r}
            rows.append(o)
    return pd.DataFrame(rows)


# ----------------------------------------------------------------------------
# B4: the D150 fit with and without the children inside the envelope
# ----------------------------------------------------------------------------


def d150_frames(prox_runs: Path) -> dict[str, tuple[pd.DataFrame, pd.DataFrame]]:
    from scripts import box_prox_cont as bpc

    d, links_d, _, _ = bpc.load_delaware(prox_runs / "prox" / "views", prox_runs / "prox")
    m, links_m, _, _ = bpc.load_midland(Path("docs") / "box" / "step21b-2026-11-01" / "prox_children.csv.gz", prox_runs / "step21a")
    return {"delaware": (d, links_d), "midland": (m, links_m)}


def d150_check(basin: str, d: pd.DataFrame, lk: pd.DataFrame, spec: dict | None = None, metric: str = pc.METRIC) -> tuple[dict, pd.DataFrame]:
    rule = RULE_OF_RECORD[basin]
    par = pc.parents(lk, drilled=True)
    inside = set(par.loc[proposed_mask(par, basin, spec), "child"])
    d = d.reset_index(drop=True)

    def fit(frame: pd.DataFrame) -> tuple[pc.Model, pc.Padded, np.ndarray, np.ndarray]:
        lm = pc.l_mix(frame, metric)
        P, lmix, _, idx = pc.scored_frame(frame, par, lm)
        return pc.fit_joint(P, lmix, rule, intercept=True), P, lmix, idx

    full, P, lmix, idx = fit(d)
    keep = ~d["api10"].isin(inside)
    red, _, _, _ = fit(d[keep].reset_index(drop=True))
    red2 = None
    try:   # the same refit started from the record's parameters (a different start must not change the answer)
        dk = d[keep].reset_index(drop=True)
        lm = pc.l_mix(dk, metric)
        Pk, lk_, _, _ = pc.scored_frame(dk, par, lm)
        red2 = pc.fit_joint(Pk, lk_, rule, intercept=True, x0=pc.model_theta(full, True))
    except Exception as e:  # noqa: BLE001
        print("  warm-start refit failed:", e, flush=True)
    dh_same, rects = (spec or PROPOSED)[basin]
    grid = np.arange(50.0, 2650.0, 50.0)
    rows = []
    for which in ("same", "below", "above"):
        side = np.full(len(grid), which, dtype=object)
        dh = grid if which == "same" else np.zeros(len(grid))
        dz = np.zeros(len(grid)) if which == "same" else (grid if which == "below" else -grid)
        ok = grid <= pc.UNIVERSE_DH_FT if which == "same" else (grid > SAME_DV_FT) & (grid <= pc.UNIVERSE_DV_FT)
        outside = grid > dh_same if which == "same" else ~np.array([any(lo < z <= hi for lo, hi, _ in rects) for z in dz])
        rows.append(pd.DataFrame({"basin": basin, "side": which, "d_ft": grid, "F_record_fit": full.factor(dh, dz, side), "F_without_envelope_children": red.factor(dh, dz, side),
                                  "F_without_warm_start": red2.factor(dh, dz, side) if red2 is not None else np.nan, "in_universe": ok, "outside_envelope": outside}))
    cur = pd.concat(rows, ignore_index=True)
    j = cur[cur["in_universe"] & cur["outside_envelope"]]
    dF = float((j["F_without_envelope_children"] - j["F_record_fit"]).abs().max())
    dF2 = float((j["F_without_warm_start"] - j["F_record_fit"]).abs().max()) if red2 is not None else np.nan
    # residual after the factor, children inside the envelope vs the rest
    Fr = pc.rule_vector(pc.f_matrix(P, full), P, rule)
    resid = lmix - np.log(full.level) - np.log(Fr)
    ids = d["api10"].to_numpy()[idx]
    ins = np.isin(ids, list(inside))
    exposed = P.n_parents >= 1

    def cell(m: np.ndarray) -> dict:
        return {"n": int(m.sum()), "factor": float(np.exp(np.log(full.level * Fr[m]).mean())) if m.any() else np.nan,
                "actual_vs_mix": float(np.exp(lmix[m].mean())) if m.any() else np.nan, "residual_after_factor": float(np.exp(resid[m].mean())) if m.any() else np.nan}

    res = {"basin": basin, "rule": rule, "children_scored": len(lmix), "children_inside_envelope": int(ins.sum()),
           "record_fit": full.as_dict(), "without_envelope_children": red.as_dict(), "without_warm_start": red2.as_dict() if red2 is not None else None,
           "max_dF_outside": dF, "max_dF_outside_warm_start": dF2, "d_level": float(red.level - full.level),
           "pass_F": bool(dF <= B4_DF), "pass_level": bool(abs(red.level - full.level) <= B4_DLEVEL), "B4": bool(dF <= B4_DF and abs(red.level - full.level) <= B4_DLEVEL),
           "inside_envelope": cell(ins), "exposed_outside_envelope": cell(exposed & ~ins), "unexposed": cell(~exposed)}
    return res, cur


# ----------------------------------------------------------------------------
# Novi sticks
# ----------------------------------------------------------------------------


def pull_stick_status(cache: Path) -> tuple[pd.DataFrame, pd.DataFrame]:
    f1, f2 = cache / "p2b_stick_status.pkl", cache / "p2b_record.pkl"
    if f1.exists() and f2.exists():
        return pd.read_pickle(f1), pd.read_pickle(f2)
    from etl.db import get_connection

    with get_connection() as conn:
        st, rec = sb._read(conn, _STATUS_SQL, {}), sb._read(conn, _RECORD_SQL, {})
    st.to_pickle(f1)
    rec.to_pickle(f2)
    return st, rec


def stick_links(d: dict, sg: pd.DataFrame, u: pd.DataFrame, status: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    s = d["sticks"].dropna(subset=["x", "y", "code"]).merge(sg, on="stick_id", how="inner").merge(status, on="stick_id", how="left").reset_index(drop=True)
    s["geom"] = shapely.from_wkt(s["wkt"].to_numpy())
    s = s[shapely.length(s["geom"].to_numpy()) > 1.0].reset_index(drop=True)
    s["remaining"] = s["status"].isna() | s["status"].isin(["remaining_pud", "conflict"])
    parts = []
    for basin, g in s.groupby("basin"):
        ub = u[(u["basin"] == basin) & u["clean"] & (u["screen"] != "bad_depth")]
        t = links(g["geom"].to_numpy(), ub["geom"].to_numpy(), same=False, overlap_min=MIN_OV)
        gi, uj = g.index.to_numpy()[t["i"].to_numpy()], ub.index.to_numpy()[t["j"].to_numpy()]
        t["child"], t["basin"], t["child_bench"] = s["stick_id"].to_numpy()[gi], basin, s["code"].to_numpy()[gi]
        t["parent"], t["parent_bench"], t["parent_fp"] = u["api10"].to_numpy()[uj], u["live"].to_numpy()[uj], u["fp"].to_numpy()[uj]
        t["dz_ft"] = u["depth_ft"].to_numpy(float)[uj] - s["tvd"].to_numpy(float)[gi]
        parts.append(t.drop(columns=["i", "j"]))
        print(f"  {basin}: {len(t):,} stick links", flush=True)
    return s, pd.concat(parts, ignore_index=True)


def novi_cull(s: pd.DataFrame, SL: pd.DataFrame, rec: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    rem = s[s["remaining"]]
    sl = SL[SL["child"].isin(set(rem["stick_id"])) & SL["dz_ft"].notna()]
    envs: dict[str, np.ndarray] = {k: f(sl) for k, f in STARTING.items() if "extra" not in k}
    for name, spec in CANDIDATES.items():
        envs[name] = spec_mask(sl, spec)
    envs["proposed"] = envs[RECOMMENDED].copy()
    # the tag reading of the same-landing test: same pool, sideways only (Novi's TVD not used)
    pool_same = np.array([ps.pool(a) == ps.pool(b) for a, b in zip(sl["child_bench"], sl["parent_bench"], strict=True)])
    for basin in sl["basin"].unique():
        envs.setdefault("proposed, by tag instead of Novi TVD", np.zeros(len(sl), bool))
        b = (sl["basin"] == basin).to_numpy()
        envs["proposed, by tag instead of Novi TVD"][b] = (pool_same & (sl["dh_ft"] <= PROPOSED[basin][0]).to_numpy())[b]
    flags = pd.DataFrame({"stick_id": rem["stick_id"].to_numpy(), "basin": rem["basin"].to_numpy(), "code": rem["code"].to_numpy(), "category": rem["category"].to_numpy()})
    for k, m in envs.items():
        flags[k] = flags["stick_id"].isin(set(sl.loc[m, "child"]))
    r = rec.drop_duplicates("stick_id").set_index("stick_id")
    flags["record_coverage"] = r["coverage"].reindex(flags["stick_id"]).to_numpy()
    flags["record_outcome"] = r["outcome"].reindex(flags["stick_id"]).to_numpy()
    flags["record_factor"] = pd.to_numeric(r["factor"].reindex(flags["stick_id"]), errors="coerce").to_numpy()
    names = list(envs)
    by_basin = flags.groupby("basin")[names].agg(["sum", "mean"])
    tot = pd.DataFrame([{"basin": b, "remaining_sticks": int((flags["basin"] == b).sum()), **{k: int(flags.loc[flags["basin"] == b, k].sum()) for k in names},
                         **{f"{k} %": 100 * float(flags.loc[flags["basin"] == b, k].mean()) for k in names}} for b in sorted(flags["basin"].unique())])
    del by_basin
    by_bench = flags.groupby(["basin", "code"]).agg(remaining_sticks=("stick_id", "size"), **{k: (k, "sum") for k in names}).reset_index()
    by_bench["proposed_pct"] = 100 * by_bench["proposed"] / by_bench["remaining_sticks"]
    c = flags[flags["proposed"]].copy()
    c["record_state"] = np.where(c["record_coverage"].isna(), "not in a record run", np.where(c["record_coverage"] != "covered", c["record_coverage"], c["record_outcome"].fillna("covered, no proximity row")))
    vs = c.groupby(["basin", "record_state"]).agg(sticks=("stick_id", "size"), mean_record_factor=("record_factor", "mean")).reset_index()
    return tot, by_bench, vs, flags


# ----------------------------------------------------------------------------
# Figures
# ----------------------------------------------------------------------------


def fig_rates(prof: pd.DataFrame, out: Path) -> str:
    fig, axes = plt.subplots(2, 3, figsize=(19, 9.5), sharey=True)
    groups = (("same landing (within 150 ft)", [(-150.0, 150.0)]), ("parent deeper (child is a topfill)", [(150.0, 250.0), (250.0, 350.0), (350.0, 450.0), (450.0, 550.0), (650.0, 750.0)]),
              ("parent shallower (child is an underfill)", [(-250.0, -150.0), (-350.0, -250.0), (-450.0, -350.0), (-550.0, -450.0), (-750.0, -650.0)]))
    for r_, basin in enumerate(("delaware", "midland")):
        for c_, (title, bands) in enumerate(groups):
            ax = axes[r_, c_]
            for k, (lo, hi) in enumerate(bands):
                t = prof[(prof["basin"] == basin) & (prof["dz_lo"] == lo)]
                ax.step(t["dh_lo"], t["r"], where="post", lw=1.6 if len(bands) == 1 else 1.1, color=plt.cm.viridis(k / max(len(bands) - 1, 1)) if len(bands) > 1 else "#1d4ed8",
                        label=f"{min(abs(lo), abs(hi)):,.0f}-{max(abs(lo), abs(hi)):,.0f} ft" if len(bands) > 1 else f"{int(t['links'].sum()):,} links")
            ax.axhline(RARE, color="#dc2626", lw=0.8, ls="--")
            ax.axhline(1.0, color="#6b7280", lw=0.6)
            ax.set_ylim(0, 2.2)
            ax.set_xlim(0, 2600)
            ax.set_title(f"{basin}: {title}", fontsize=10)
            ax.set_xlabel("sideways gap to the parent, ft")
            ax.legend(fontsize=7, title="vertical gap" if len(bands) > 1 else None, title_fontsize=7)
        axes[r_, 0].set_ylabel("relative drilling rate r (1 = the rate at 1,000-2,000 ft)")
    fig.suptitle("Where children were drilled next to a parent >= 12 months on production (dashed = the 0.25 'rare' bar)", fontsize=12)
    f = out / "rate_profiles.png"
    p2a.save_fig(fig, f)
    plt.close(fig)
    return f.name


def fig_heat(Q: pd.DataFrame, out: Path) -> str:
    fig, axes = plt.subplots(1, 2, figsize=(17, 8))
    xe, ze = np.arange(0, 2700, 100.0), np.arange(-1050, 1051, 100.0)
    for ax, basin in zip(axes, ("delaware", "midland"), strict=True):
        g = Q[Q["basin"] == basin]
        H = np.histogram2d(g["dz_ft"], g["dh_ft"], bins=[ze, xe])[0]
        ref = H[:, (xe[:-1] >= REF_FT[0]) & (xe[:-1] < REF_FT[1])].mean(axis=1, keepdims=True)
        R = np.where(ref * 1.0 >= MIN_EXPECTED, H / np.where(ref > 0, ref, 1.0), np.nan)
        im = ax.pcolormesh(xe, ze, R, cmap="RdYlBu", vmin=0, vmax=2)
        ax.invert_yaxis()
        ax.axhline(150, color="k", lw=0.5, ls=":")
        ax.axhline(-150, color="k", lw=0.5, ls=":")
        dh_same, rects = PROPOSED[basin]
        ax.add_patch(plt.Rectangle((0, -150), dh_same, 300, fill=False, ec="k", lw=2))
        for lo, hi, w in rects:
            ax.add_patch(plt.Rectangle((0, lo), w, hi - lo, fill=False, ec="k", lw=2))
        ax.add_patch(plt.Rectangle((0, -150), 400, 300, fill=False, ec="#7c3aed", lw=1.2, ls="--"))
        ax.add_patch(plt.Rectangle((0, -300), 800, 600, fill=False, ec="#059669", lw=1.2, ls="--"))
        ax.add_patch(plt.Rectangle((0, -500), 1400, 1300, fill=False, ec="#6b7280", lw=1.2, ls="--"))
        ax.set_title(f"{basin}: relative drilling rate by parent position, {len(g):,} links\n(blank = fewer than 30 expected links per cell)", fontsize=10)
        ax.set_xlabel("sideways gap, ft")
        ax.set_ylabel("parent depth minus child depth, ft (down = parent deeper = topfill)")
        fig.colorbar(im, ax=ax, shrink=0.7).set_label("r (1 = the rate at 1,000-2,000 ft in the same row)")
    fig.suptitle("Solid black = proposed envelope; dashed purple = 21a floor, green = deal-intake v14, grey = D112 vertical", fontsize=11)
    f = out / "rate_heatmap.png"
    p2a.save_fig(fig, f)
    plt.close(fig)
    return f.name


def fig_focus(Q: pd.DataFrame, out: Path) -> list[str]:
    files = []
    for basin, bench in FOCUS:
        g = Q[(Q["basin"] == basin) & (Q["child_bench"] == bench) & (Q["dz_ft"].abs() <= 1050)]
        fig, ax = plt.subplots(figsize=(13, 8))
        top = g["parent_bench"].value_counts().head(7).index.tolist()
        cm = plt.cm.tab10
        for k, pb in enumerate(top):
            b = g[g["parent_bench"] == pb]
            ax.scatter(b["dh_ft"] * b["side"], b["dz_ft"], s=5, color=cm(k), alpha=0.55, linewidths=0, label=f"{pb} ({len(b):,})")
        o = g[~g["parent_bench"].isin(top)]
        ax.scatter(o["dh_ft"] * o["side"], o["dz_ft"], s=4, color="#9ca3af", alpha=0.4, linewidths=0, label=f"other ({len(o):,})")
        dh_same, rects = PROPOSED[basin]
        ax.add_patch(plt.Rectangle((-dh_same, -150), 2 * dh_same, 300, fill=False, ec="k", lw=2, label="proposed envelope"))
        for lo, hi, w in rects:
            ax.add_patch(plt.Rectangle((-w, lo), 2 * w, hi - lo, fill=False, ec="k", lw=2))
        ax.add_patch(plt.Rectangle((-400, -150), 800, 300, fill=False, ec="#7c3aed", lw=1.1, ls="--", label="21a floor"))
        ax.add_patch(plt.Rectangle((-800, -300), 1600, 600, fill=False, ec="#059669", lw=1.1, ls="--", label="deal-intake v14"))
        ax.add_patch(plt.Rectangle((-1400, -500), 2800, 1300, fill=False, ec="#6b7280", lw=1.1, ls="--", label="D112 vertical"))
        ax.scatter([0], [0], marker="*", s=220, color="k", zorder=5)
        ax.invert_yaxis()
        ax.set_xlim(-2640, 2640)
        ax.set_ylim(1050, -1050)
        ax.set_xlabel("parent position sideways of the child, ft (+ = east for N-S laterals, north for E-W)")
        ax.set_ylabel("parent depth minus child depth, ft (down = parent deeper)")
        ax.set_title(f"{basin} {bench}: every parent (>= 12 months on production, >= 30 % alongside) of {g['child'].nunique():,} drilled children, child at the star\n"
                     f"{len(g):,} links, coloured by the parent's bench", fontsize=11)
        ax.legend(fontsize=8, loc="upper right", ncol=2)
        f = out / f"gunbarrel_parents_{basin}_{bench}.png"
        p2a.save_fig(fig, f)
        plt.close(fig)
        files.append(f.name)
    return files


def fig_maps(u: pd.DataFrame, Q: pd.DataFrame, flags: pd.DataFrame | None, s: pd.DataFrame | None, extents: pd.DataFrame, out: Path) -> list[str]:
    from box import landing_surfaces as ls

    files = []
    MI = ls.M_PER_MI
    for basin, bench in FOCUS:
        kids = u[u["measured_pop"] & (u["basin"] == basin) & (u["live"] == bench)]
        q = Q[(Q["basin"] == basin) & (Q["child_bench"] == bench)]
        ex = set(q.loc[proposed_mask(q, basin), "child"])
        exposed = set(q.loc[(q["dh_ft"] <= 1400) & (q["dz_ft"].abs() <= 1000), "child"])
        fig, axes = plt.subplots(1, 2, figsize=(18, 9))
        ax = axes[0]
        a = kids[~kids["api10"].isin(exposed)]
        b = kids[kids["api10"].isin(exposed) & ~kids["api10"].isin(ex)]
        c = kids[kids["api10"].isin(ex)]
        ax.scatter(a["x"] / MI, a["y"] / MI, s=4, color="#9ca3af", linewidths=0, label=f"no parent within 1,400 ft ({len(a):,})")
        ax.scatter(b["x"] / MI, b["y"] / MI, s=5, color="#2563eb", linewidths=0, label=f"parent nearby, outside the envelope ({len(b):,})")
        ax.scatter(c["x"] / MI, c["y"] / MI, s=22, color="#dc2626", linewidths=0, label=f"inside the proposed envelope ({len(c):,})")
        ax.set_title(f"{basin} {bench}: {len(kids):,} drilled children (first production >= 2016)", fontsize=10)
        ax2 = axes[1]
        if flags is not None and s is not None:
            fs = flags[(flags["basin"] == basin) & (flags["code"] == bench)].merge(s[["stick_id", "x", "y"]], on="stick_id")
            k, cu = fs[~fs["proposed"]], fs[fs["proposed"]]
            ax2.scatter(k["x"] / MI, k["y"] / MI, s=1.5, color="#9ca3af", linewidths=0, label=f"kept ({len(k):,})", rasterized=True)
            ax2.scatter(cu["x"] / MI, cu["y"] / MI, s=7, color="#dc2626", linewidths=0, label=f"inside the proposed envelope ({len(cu):,})", rasterized=True)
            ax2.set_title(f"Remaining Novi {bench} sticks: what the envelope would cull (Novi TVD)", fontsize=10)
        for axx in axes:
            for e in extents[extents["basin"] == basin].itertuples():
                if bench in ls.extent_codes(basin, e.bench):
                    for poly in shapely.get_parts(shapely.make_valid(shapely.from_wkt(e.wkt))):
                        if poly.geom_type == "Polygon":
                            xx, yy = poly.exterior.xy
                            axx.plot(np.asarray(xx) / MI, np.asarray(yy) / MI, color="#111827", lw=0.8)
            axx.set_aspect("equal")
            axx.set_xticks([])
            axx.set_yticks([])
            axx.legend(fontsize=8, loc="lower left", markerscale=2)
        f = out / f"map_{basin}_{bench}.png"
        p2a.save_fig(fig, f)
        plt.close(fig)
        files.append(f.name)
    return files


def fig_pad(u: pd.DataFrame, L: pd.DataFrame, api10: str, title: str, out: Path, name: str, radius_ft: float = 2640.0) -> str:
    """Gunbarrel around one child: every universe well alongside it, offset by rule v2 against depth."""
    k = L[(L["child"] == api10) & (L["overlap"] >= STORE_OV) & L["judged"]]
    uu = u.set_index("api10")
    me = uu.loc[api10]
    fig, ax = plt.subplots(figsize=(12, 7))
    col = {"parent": "#dc2626", "young": "#f59e0b", "codev": "#2563eb", "child": "#9ca3af"}
    lab = {"parent": "on production >= 12 months before it", "young": "6-12 months before it", "codev": "co-developed (within 6 months)", "child": "drilled later"}
    for rel, g in k.groupby("rel"):
        ax.scatter(g["dh_ft"] * g["side"], uu["depth_ft"].reindex(g["parent"]).to_numpy(), s=60, color=col[rel], label=lab[rel], zorder=3, edgecolors="k", linewidths=0.4)
        for r in g.itertuples():
            ax.annotate(f"{r.parent_bench}\n{pd.Timestamp(uu.at[r.parent, 'fp']).year}", (r.dh_ft * r.side, uu.at[r.parent, "depth_ft"]), fontsize=6.5, xytext=(4, 4), textcoords="offset points")
    ax.scatter([0], [me["depth_ft"]], marker="*", s=320, color="k", zorder=4, label=f"{me['well_name']} ({me['live']}, {pd.Timestamp(me['fp']).year})")
    dh_same, rects = PROPOSED[me["basin"]]
    ax.add_patch(plt.Rectangle((-dh_same, me["depth_ft"] - 150), 2 * dh_same, 300, fill=False, ec="k", lw=1.8, label="proposed envelope around the well"))
    for lo, hi, w in rects:
        ax.add_patch(plt.Rectangle((-w, me["depth_ft"] + lo), 2 * w, hi - lo, fill=False, ec="k", lw=1.8))
    ax.add_patch(plt.Rectangle((-400, me["depth_ft"] - 150), 800, 300, fill=False, ec="#7c3aed", lw=1, ls="--", label="21a floor"))
    ax.add_patch(plt.Rectangle((-800, me["depth_ft"] - 300), 1600, 600, fill=False, ec="#059669", lw=1, ls="--", label="deal-intake v14"))
    ax.add_patch(plt.Rectangle((-1400, me["depth_ft"] - 500), 2800, 1300, fill=False, ec="#6b7280", lw=1, ls="--", label="D112 vertical"))
    ax.set_xlim(-radius_ft, radius_ft)
    ax.set_ylim(me["depth_ft"] + 1100, me["depth_ft"] - 1100)
    ax.set_xlabel("ft sideways of the well (+ = east for N-S laterals, north for E-W)")
    ax.set_ylabel("landing depth, ft TVD")
    ax.set_title(title, fontsize=10)
    ax.legend(fontsize=7.5, loc="lower right")
    f = out / name
    p2a.save_fig(fig, f)
    plt.close(fig)
    return f.name


# ----------------------------------------------------------------------------


def run(out: Path, cache: Path, prox_runs: Path | None, steps: set[str]) -> dict:
    out.mkdir(parents=True, exist_ok=True)
    d = p0.pull(cache)
    wg, sg = p2a.pull_geoms(cache)
    u = p2a.universe(d, wg, cache)
    print(f"universe {len(u):,}; children {int(u['measured_pop'].sum()):,}", flush=True)
    fL = cache / "p2b_links.pkl"
    if fL.exists() and "links" not in steps:
        L = pd.read_pickle(fL)
    else:
        L = well_links(u)
        L.to_pickle(fL)
    Q = qualifying(L)
    summary: dict = {"generated": dt.datetime.now(dt.UTC).isoformat(timespec="seconds"), "code_sha": p0._git_sha(), "tags": "live",
                     "params": {"gate_ft": GATE_FT, "store_dv_ft": STORE_DV_FT, "min_overlap": MIN_OV, "parallel_tol_deg": TOL_DEG, "same_dv_ft": SAME_DV_FT,
                                "parent_min_days": ps.PARENT_MIN_DAYS, "codev_days": ps.CODEV_DAYS, "ref_ft": REF_FT, "rare": RARE, "min_expected": MIN_EXPECTED},
                     "proposed": {b: {"same_landing_dh_ft": v[0], "vertical_rects": v[1]} for b, v in PROPOSED.items()}}
    kids = u[u["measured_pop"]]
    unj = L[(L["rel"] == "parent") & ~L["judged"] & (L["overlap"] >= MIN_OV)]
    summary["population"] = {}
    for basin, g in kids.groupby("basin"):
        q = Q[Q["basin"] == basin]
        box = q[(q["dh_ft"] <= GATE_FT) & (q["dz_ft"].abs() <= 1000)]
        summary["population"][basin] = {
            "children": len(g), "links_stored": int((L["basin"] == basin).sum()), "qualifying_parent_links": len(q), "children_with_parent_2640_1000": int(box["child"].nunique()),
            "children_with_parent_1400_1000": int(box.loc[box["dh_ft"] <= 1400, "child"].nunique()),
            "children_with_unjudged_older_neighbour_le_400": int(unj.loc[(unj["basin"] == basin) & (unj["dh_ft"] <= 400), "child"].nunique()),
            "children_with_unjudged_older_neighbour_le_1400": int(unj.loc[(unj["basin"] == basin) & (unj["dh_ft"] <= 1400), "child"].nunique()),
            "by_class_links": q["cls"].value_counts().to_dict(), "by_class_children": q.groupby("cls")["child"].nunique().to_dict()}
    if "check" in steps:
        summary["B1"] = metric_check(u, L)
        print(json.dumps(summary["B1"], indent=1), flush=True)
    prof, pair, edge = rate_tables(Q)
    if "rates" in steps:
        prof.to_csv(out / "rate_profiles.csv", index=False)
        pair.to_csv(out / "bench_pairs.csv", index=False)
        edge.to_csv(out / "rate_edges_by_band.csv", index=False)
        overlap_table(L).to_csv(out / "overlap_dimension.csv", index=False)
        # fine profile close in, same landing, 50-ft bins
        fine = []
        for basin, g in Q[Q["cls"] == "same"].groupby("basin"):
            t = rate(g["dh_ft"].to_numpy(), np.arange(0.0, 1001.0, 50.0))
            t.insert(0, "basin", basin)
            fine.append(t)
        pd.concat(fine).to_csv(out / "rate_same_landing_50ft.csv", index=False)
        print(edge.round(2).to_string(), flush=True)
    if "envelopes" in steps:
        rows, benches = [], []
        masks = {k: f(Q) for k, f in STARTING.items()}
        for name, m in masks.items():
            r, bb = score_envelope(name, u, Q, m, region_r_for(Q, name, m))
            rows += r
            benches.append(bb)
        for name, spec in CANDIDATES.items():
            m = spec_mask(Q, spec)
            masks[name] = m
            r, bb = score_envelope(name, u, Q, m, spec_region_r(Q, spec, m))
            rows += r
            benches.append(bb)
        pm = masks[RECOMMENDED]
        env = pd.DataFrame(rows)
        sw = sweep(u, Q)
        sw.to_csv(out / "envelope_sweep.csv", index=False)
        print(sw[sw["dh_le_ft"].isin([200.0, 300.0, 400.0, 600.0])].round(2).to_string(), flush=True)
        summary["B1_envelope_sensitivity"] = prox_sensitivity(u, Q)
        print(summary["B1_envelope_sensitivity"], flush=True)
        env.to_csv(out / "envelope_scores.csv", index=False)
        pd.concat(benches, ignore_index=True).to_csv(out / "envelope_by_bench.csv", index=False)
        x, xs = describe_excluded(u, Q, pm, L)
        x.to_csv(out / "excluded_children_proposed.csv", index=False)
        xs.to_csv(out / "excluded_children_summary.csv", index=False)
        for name in ("21a floor (<=150 ft vt, <=400 ft hz)", "D112 vertical (topfill 800 / underfill 500 ft, <=1,400 ft hz)", "deal-intake v14 (<=300 ft vt, <=800 ft hz)"):
            describe_excluded(u, Q, masks[name], L)[1].assign(envelope=name).to_csv(out / f"excluded_summary_{name.split(' ')[0].replace('-', '_')}.csv", index=False)
        summary["envelopes"] = env.to_dict("records")
        print(env.round(2).to_string(), flush=True)
        print(xs.round(1).to_string(), flush=True)
    if "dean" in steps:
        for basin, bench in FOCUS:
            config_table(u, Q, basin, bench).to_csv(out / f"config_{basin}_{bench}.csv", index=False)
        dn = pair[(pair["basin"] == "midland") & (pair["child_bench"] == "DEAN")]
        dn.to_csv(out / "dean_pairs.csv", index=False)
        up = sandwich_uptake(u, p0.pad_frame(d["pads"]), d["extents"], pd.Timestamp(u["fp"].max()))
        up.to_csv(out / "dean_sandwich_uptake_by_dsu.csv", index=False)
        print(up.round(1).to_string(), flush=True)
        print(config_table(u, Q, "midland", "DEAN").round(1).to_string(), flush=True)
        print(dn.round(2).to_string(), flush=True)
    if "stagger" in steps:
        st = stagger_table(L)
        st.to_csv(out / "same_bench_other_landing.csv", index=False)
        rows = []
        for basin, g in L[L["judged"] & (L["overlap"] >= MIN_OV) & L["rel"].isin(["parent", "codev"])].groupby("basin"):
            for label, lo, hi in (("same landing", 0.0, SAME_DV_FT), ("stacked 150-350 ft", 150.0, 350.0), ("stacked 350-550 ft", 350.0, 550.0)):
                b = g[(g["dz_ft"].abs() > lo) & (g["dz_ft"].abs() <= hi)] if lo > 0 else g[g["dz_ft"].abs() <= hi]
                for rel, h in b.groupby("rel"):
                    o = {"basin": basin, "band": label, "neighbour": "co-developed (within 6 months)" if rel == "codev" else "parent (>= 12 months older)", "links": len(h)}
                    for dh in (200.0, 300.0, 400.0, 600.0):
                        o[f"r_le_{int(dh)}"] = region_rate(h, dh)[2]
                    rows.append(o)
        cv = pd.DataFrame(rows)
        cv.to_csv(out / "parent_vs_codev.csv", index=False)
        print(cv.round(2).to_string(), flush=True)
        print(st.round(2).to_string(), flush=True)
    if "d150" in steps and prox_runs is not None:
        frames = d150_frames(prox_runs)
        res, curves = [], []
        for name, spec in CANDIDATES.items():
            for basin, (dd, lk) in frames.items():
                r, c = d150_check(basin, dd, lk, spec)
                res.append({"candidate": name, **r})
                curves.append(c.assign(candidate=name))
                print(name, basin, {k: r[k] for k in ("children_inside_envelope", "max_dF_outside", "d_level", "B4", "inside_envelope", "exposed_outside_envelope", "unexposed")}, flush=True)
        pd.concat(curves, ignore_index=True).to_csv(out / "d150_refit_curves.csv", index=False)
        summary["B4"] = res
    flags = s = None
    if "novi" in steps:
        status, rec = pull_stick_status(cache)
        fS = cache / "p2b_stick_links.pkl"
        if fS.exists():
            with open(fS, "rb") as fh:
                s, SL = pickle.load(fh)
        else:
            s, SL = stick_links(d, sg, u, status)
            with open(fS, "wb") as fh:
                pickle.dump((s.drop(columns=["wkt"]), SL), fh)
        tot, by_bench, vs, flags = novi_cull(s, SL, rec)
        tot.to_csv(out / "novi_cull_by_basin.csv", index=False)
        by_bench.to_csv(out / "novi_cull_by_bench.csv", index=False)
        vs.to_csv(out / "novi_cull_vs_record.csv", index=False)
        summary["novi"] = {"sticks": len(s), "remaining": int(s["remaining"].sum()), "by_basin": tot.to_dict("records")}
        print(tot.round(2).T.to_string(), flush=True)
        print(vs.round(3).to_string(), flush=True)
    if "figures" in steps:
        summary["figures"] = [fig_rates(prof, out), fig_heat(Q, out)] + fig_focus(Q, out) + fig_maps(u, Q, flags, s, d["extents"], out)
        ex = examples(u, L, Q)
        names = u.set_index("api10")["well_name"]
        summary["examples"] = [{"api10": a, "well": names.get(a), "title": t, "file": f} for a, t, f in ex]
        summary["figures"] += [fig_pad(u, L, a, t, out, f) for a, t, f in ex]
        print(json.dumps(summary["examples"], indent=1), flush=True)
    name = "summary.json" if steps >= {"check", "rates", "envelopes", "d150", "novi"} else f"summary_{'_'.join(sorted(steps))}.json"
    (out / name).write_text(json.dumps(summary, indent=2, default=str), encoding="utf-8")
    return summary


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--out", type=Path, required=True)
    ap.add_argument("--cache", type=Path, required=True)
    ap.add_argument("--prox-runs", type=Path, default=None, help="the runs/ folder holding the step 24 inputs (prox/, step21a/)")
    ap.add_argument("--steps", default="check,rates,envelopes,dean,stagger,d150,novi,figures")
    a = ap.parse_args(argv)
    run(a.out, a.cache, a.prox_runs, set(a.steps.split(",")))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
