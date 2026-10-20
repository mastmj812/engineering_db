"""Pure-pandas mirror of sql/64 curated.well_lateral_survey (one row per api10).

Used by scripts/apply_well_lateral_survey.py as the identity check (the stored
matview vs this function on the same TSV stations) and as the dry-run preview.
Keep the span / heel / mid / toe rules byte-for-byte with sql/64.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

# Novi LocationType codes (schema.json); 7 is undocumented and unused.
WELLHEAD, BOTTOM_HOLE, KICKOFF, LANDING, PERF_TOP, PERF_BTM, UTURN = 1, 2, 3, 4, 5, 6, -1

STATION_COLS = ["API10", "Path", "MD", "TVD", "SubSeaTVD", "LocationType", "Interpolated"]


def lateral_summary(st: pd.DataFrame) -> pd.DataFrame:
    """Per-well lateral summary from survey stations (DeletedAt rows already
    excluded). `Interpolated` may be bool or Novi's 't'/'f'. Index = API10."""
    d = st[STATION_COLS].copy()
    if d["Interpolated"].dtype != bool:
        d["Interpolated"] = d["Interpolated"].astype(str).str.lower().isin(("t", "true", "1"))
    d = d.sort_values(["API10", "Path"])

    def first_md(lt: int) -> pd.Series:
        return d[d.LocationType == lt].groupby("API10").MD.max()

    k = pd.DataFrame(index=pd.Index(d.API10.unique(), name="API10"))
    k["kb_elev_ft"] = (d.TVD - d.SubSeaTVD).groupby(d.API10).max()
    k["lp_md"], k["ptop"], k["pbot"], k["bhl_md"] = first_md(LANDING), first_md(PERF_TOP), first_md(PERF_BTM), first_md(BOTTOM_HOLE)
    perfs = k.ptop.notna() & (k.pbot > k.ptop)
    lpbhl = ~perfs & k.lp_md.notna() & (k.bhl_md > k.lp_md)
    k["lateral_basis"] = np.where(perfs, "perfs", np.where(lpbhl, "lp_bhl", None))
    k["lat_start_md_ft"] = np.where(perfs, k.ptop, np.where(lpbhl, k.lp_md, np.nan))
    k["lat_end_md_ft"] = np.where(perfs, k.pbot, np.where(lpbhl, k.bhl_md, np.nan))

    j = d.join(k[["lat_start_md_ft", "lat_end_md_ft"]], on="API10")
    lat = j[(j.MD >= j.lat_start_md_ft) & (j.MD <= j.lat_end_md_ft)].copy()
    g = lat.groupby("API10")
    out = k[["lateral_basis", "lat_start_md_ft", "lat_end_md_ft", "kb_elev_ft"]].copy()
    out["n_lat_stations"] = g.size()
    out["lat_interp_share"] = g.Interpolated.mean()
    out["lat_tvd_min_ft"] = g.TVD.min()
    out["lat_tvd_max_ft"] = g.TVD.max()
    out["lat_tvd_p50_ft"] = g.TVD.median()
    out["heel_tvd_ft"] = g.TVD.first()
    out["toe_tvd_ft"] = g.TVD.last()
    lat["_dmid"] = (lat.MD - (lat.lat_start_md_ft + lat.lat_end_md_ft) / 2.0).abs()
    mid = lat.sort_values(["API10", "_dmid", "Path"]).groupby("API10").TVD.first()
    out["mid_tvd_ft"] = mid
    out["toe_minus_heel_tvd_ft"] = out.toe_tvd_ft - out.heel_tvd_ft
    out["lat_tvd_range_ft"] = out.lat_tvd_max_ft - out.lat_tvd_min_ft
    return out
