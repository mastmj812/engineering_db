"""BOX step 20a follow-up — where the Midland develops TWO Wolfcamp B landings and where only one (read-only, pure).

Michael (2026-10-26): WCB_1 + WCB_2 are developed toward the south of the basin, a single WCB landing toward the north; the
extents should not plan or forecast a second WCB where only one is developed. This module measures that on PDP data,
independent of the WCB_1 / WCB_2 tags (which mix: a single landing carries either tag):

  * landing depth = lateral TVD - the local WCA_1 band median (consensus detector, 1.5-mi neighbourhood), so structure
    drops out; the WCB_2 landing = depth >= DEEP_CUT_FT below WCA_1. DEEP_CUT_FT is the midpoint of the southern
    population's tag medians (WCB_1 / WCB_2), measured, not chosen.
  * the demarcation = per longitude strip, the north edge of the northernmost latitude bin in which >= DEEP_SHARE of the
    WCB laterals land at WCB_2 depth (bins with >= MIN_BIN laterals); flat continuation past the data.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

SOUTH_REF_LAT = 31.6  # the reference population for the depth cut: laterals south of this (two landings, by the profile)
DEEP_SHARE = 0.20
LAT_BIN = 0.05
LON_STRIP = 0.15
MIN_BIN = 10
MIN_STRIP = 60


def landing_depth(wells: pd.DataFrame) -> pd.Series:
    """TVD below the local WCA_1 band (ft, + = deeper); NaN where the neighbourhood has no coherent WCA_1 band."""
    ref = [b.get("WCA_1") if isinstance(b, dict) else np.nan for b in wells["cons_bands"]]
    return wells["tvd_ft"].astype(float) - np.asarray(ref, dtype=float)


def deep_cut(wells: pd.DataFrame) -> dict[str, float]:
    """Midpoint of the southern WCB_1 / WCB_2 tag medians of landing depth."""
    s = wells[(wells["mid_lat"] < SOUTH_REF_LAT) & wells["below_wca1"].notna()]
    m1 = float(s.loc[s["box_bench"] == "WCB_1", "below_wca1"].median())
    m2 = float(s.loc[s["box_bench"] == "WCB_2", "below_wca1"].median())
    return {"wcb1_median_ft": m1, "wcb2_median_ft": m2, "cut_ft": (m1 + m2) / 2}


def lat_profile(wells: pd.DataFrame, step: float = 0.1) -> pd.DataFrame:
    """Share landed at WCB_2 depth and share tagged WCB_2, by latitude band."""
    w = wells[wells["below_wca1"].notna()]
    g = w.groupby(pd.cut(w["mid_lat"], np.arange(30.85, 32.75 + 1e-9, step)), observed=True).agg(
        n=("api10", "size"), deep=("deep", "mean"), tagged_wcb2=("box_bench", lambda s: float((s == "WCB_2").mean())),
        median_below_wca1_ft=("below_wca1", "median"))
    g.index = [f"{iv.left:.2f}-{iv.right:.2f}" for iv in g.index]
    return g


def boundary(wells: pd.DataFrame) -> pd.DataFrame:
    """Per LON_STRIP strip: the demarcation latitude (north edge of the last >= DEEP_SHARE bin) and what lies north of it."""
    w = wells[wells["below_wca1"].notna()]
    rows = []
    for a in np.arange(-102.45, -100.95, LON_STRIP):
        g = w[(w["mid_lon"] >= a) & (w["mid_lon"] < a + LON_STRIP)]
        if len(g) < MIN_STRIP:
            continue
        t = g.groupby(pd.cut(g["mid_lat"], np.arange(30.8, 32.8, LAT_BIN)), observed=True)["deep"].agg(["mean", "size"])
        t = t[t["size"] >= MIN_BIN]
        hits = [iv.left for iv, v in zip(t.index, t["mean"]) if v >= DEEP_SHARE]
        if not hits:
            continue
        edge = max(hits) + LAT_BIN
        n = g[g["mid_lat"] >= edge]
        rows.append({"lon": round(a + LON_STRIP / 2, 3), "n": len(g), "boundary_lat": round(edge, 3), "n_north": len(n),
                     "deep_north": int(n["deep"].sum()), "deep_share_north": float(n["deep"].mean()) if len(n) else np.nan})
    return pd.DataFrame(rows)


def line(bnd: pd.DataFrame, west: float = -103.0, east: float = -100.5) -> list[tuple[float, float]]:
    """The demarcation as a lon / lat polyline, held flat past the first and last strip."""
    pts = [(float(r.lon), float(r.boundary_lat)) for r in bnd.itertuples()]
    return [(west, pts[0][1]), *pts, (east, pts[-1][1])]
