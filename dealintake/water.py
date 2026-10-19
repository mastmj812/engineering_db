"""Screen-curve water from MEASURED-water analogs (BOX D107 carried into the deal-intake SCREEN drop; Michael 2026-10-19,
Option A).

A deal-intake screen curve's water used to be anduin's independent Arps fit of the oil cohort — on TX deals mostly
vendor-calculated water (a frozen filing WOR, sql/41). Here, per TC group:

  1. the measured-water cohort: same-bench horizontals whose water is MEASURED (sql/41 measured; NM unless insufficient;
     seller VDR daily water, >= 6 months) around the group's units, selected exactly as BOX's water selection
     (box/water11.select_water: deal-intake classify + tier-blind fill, D54 ladder 5 -> 20 mi then 30 / 40 / 50 mi until
     10 eligible; < 3 measured at 50 mi -> the whole bench pool, flagged calculated_fallback);
  2. anduin fits any of those wells without a forecast (only_missing);
  3. the curve's water = WOR vs cumulative oil fitted on that cohort x the curve's OWN oil (anduin ratio_cohorts, #99).

Tier (D110): validated where BOX validated water (Delaware WCA_1 / WCA_2 / BS2_S), provisional everywhere else (incl. all
Midland: BOX never tested it). The screen drop carries the tier; Michael's manual drop is untouched (his own TCs).
"""

from __future__ import annotations

import datetime as dt
from collections.abc import Sequence
from typing import Any

import numpy as np
import pandas as pd
from scipy.spatial import cKDTree
from shapely.geometry.base import BaseGeometry

from box import water11 as w
from box.dev_factor_report import _xy
from dealintake import warehouse as wh

POOL_RADIUS_MI = 52.0  # the 50-mi water cap + a margin for stick-midpoint vs unit-centroid distance

_POOL_SQL = f"""
SELECT w.api10, we.state_code, w.first_production_date, w.last_reported_month, w.lateral_length_ft,
       we.lateral_closer_xy_ft,
       extensions.ST_X(extensions.ST_LineInterpolatePoint(extensions.ST_LineMerge(w.wellstick_geom), 0.5)) AS lon,
       extensions.ST_Y(extensions.ST_LineInterpolatePoint(extensions.ST_LineMerge(w.wellstick_geom), 0.5)) AS lat
FROM curated.wells w
JOIN curated.wells_enriched we ON we.api10 = w.api10
CROSS JOIN (SELECT extensions.ST_GeomFromText(%(u)s, 4326) AS g) u
WHERE extensions.ST_DWithin(w.wellstick_geom::extensions.geography, u.g::extensions.geography, %(r)s)
  AND {wh._HZ}
  AND w.first_production_date IS NOT NULL
  AND we.formation_blueox = %(bench)s
"""
_CLS_SQL = """
SELECT api10, prod_date, oil_per_month_bbl AS oil, water_per_month_bbl AS water, COALESCE(is_water_proprietary, FALSE) AS prop
FROM curated.production
WHERE api10 = ANY(%(a)s) AND months_on_production BETWEEN 1 AND 24 AND oil_per_month_bbl > 0 AND water_per_month_bbl > 0
"""
_VDR_SQL = """
SELECT api10, date_trunc('month', prod_date)::date AS month, sum(water_bbl) AS water FROM vdr.well_daily
WHERE api10 = ANY(%(a)s) GROUP BY 1, 2
"""


def tier(bench: str, basin: str | None, validated_benches: Sequence[str]) -> str:
    """D110: BOX validated water on Delaware WCA_1 / WCA_2 / BS2_S only."""
    return "validated" if (basin or "").lower() == "delaware" and bench in set(validated_benches) else "provisional"


def pool_frame(conn: Any, area: BaseGeometry, bench: str) -> pd.DataFrame:
    """Same-bench horizontals within POOL_RADIUS_MI of `area`, with their BOX-water label (all data; NM rule; VDR)."""
    rows = wh._rows(conn, _POOL_SQL, {"u": area.wkt, "r": POOL_RADIUS_MI * wh.M_PER_MI, "bench": bench})
    p = pd.DataFrame(rows, columns=["api10", "state_code", "first_production_date", "last_reported_month", "lateral_length_ft",
                                    "lateral_closer_xy_ft", "lon", "lat"])
    if p.empty:
        return p
    p = p.dropna(subset=["lon", "lat"]).drop_duplicates("api10").reset_index(drop=True)
    p["x"], p["y"] = _xy(p["lon"], p["lat"])
    p["lateral"] = pd.to_numeric(p["lateral_length_ft"], errors="coerce")
    p["spacing"] = pd.to_numeric(p["lateral_closer_xy_ft"], errors="coerce")
    p["state_code"] = p["state_code"].astype(str).str.replace(".0", "", regex=False)
    p["months"] = [w.month_index(f.replace(day=1), l) + 1 if l is not None else 0
                   for f, l in zip(p["first_production_date"], p["last_reported_month"], strict=True)]
    ids = list(p["api10"])
    cls = pd.DataFrame(wh._rows(conn, _CLS_SQL, {"a": ids}), columns=["api10", "prod_date", "oil", "water", "prop"])
    vdr = pd.DataFrame(wh._rows(conn, _VDR_SQL, {"a": ids}), columns=["api10", "month", "water"])
    vdr["water"] = vdr["water"].astype(float)
    p["label"] = p["api10"].map(w.labels_asof(p, cls, None, w.vdr_months_asof(vdr, None)))
    return p[p["lateral"] > 0].reset_index(drop=True)


def measured_cohort(conn: Any, cfg: Any, area: BaseGeometry, bench: str, basin: str | None, planned_lateral_ft: float,
                    planned_spacing_ft: float | None, validated_benches: Sequence[str]) -> dict[str, Any]:
    """The group's water cohort (selection + provenance + tier). api10s empty only when the bench has < 3 wells at all."""
    pf = pool_frame(conn, area, bench)
    c = area.centroid
    x, y = _xy([c.x], [c.y])
    loc = {"api10": "deal", "x": float(x[0]), "y": float(y[0]), "lateral_ft": float(planned_lateral_ft),
           "spacing_ft": planned_spacing_ft, "fp_max": None}
    out: dict[str, Any] = {"tier": tier(bench, basin, validated_benches), "method": "WOR vs cum oil on measured-water analogs (D107)",
                           "pool_wells": len(pf), "pool_measured": int((pf["label"] == "measured").sum()) if len(pf) else 0}
    if pf.empty:
        return {**out, "source": "none", "api10s": [], "radius_mi": None, "thin": True, "nm_share": None, "n_eligible": 0}
    pm = w.make_pool(pf[pf["label"] == "measured"].reset_index(drop=True))
    pa = w.make_pool(pf)
    b = basin or "delaware"

    def sel(pool: dict[str, Any], radii: Sequence[float]) -> tuple[list[int], float, int]:
        if not len(pool["x"]):
            return [], float(radii[-1]), 0
        return w.select_water(pool, cKDTree(np.column_stack([pool["x"], pool["y"]])), cfg, loc, radii, bench, basin=b)

    ch = w.choose(sel(pm, w.WATER_RADII_MI), lambda: sel(pa, w.LADDER_MI))
    pool = pm if ch["source"] == "measured" else pa
    ids = [str(pool["api10"][i]) for i in ch["idx"]]
    labels = dict(zip(pf["api10"], pf["label"], strict=True))
    return {**out, "source": ch["source"], "api10s": ids, "radius_mi": ch["radius_mi"], "thin": bool(ch["thin"]),
            "n_eligible": int(ch["n_eligible"]),
            "nm_share": float(np.mean([pool["state"][i] == w.NM for i in ch["idx"]])) if ch["idx"] else None,
            "labels": {k: sum(1 for a in ids if labels.get(a) == k) for k in ("measured", "calculated", "indeterminate", "insufficient")},
            "built": dt.datetime.now(dt.UTC).date().isoformat()}


def summary(fitted: dict[str, Any] | None) -> dict[str, Any] | None:
    """The bits of anduin's ratio-mode water block the dossier + handoff state."""
    if not fitted:
        return None
    return {k: fitted.get(k) for k in ("mode", "sub_mode", "alpha", "beta", "r2", "n_months", "eur_per_unit",
                                       "implied_effective_decline_yr1", "ratio_cohort")}


def flags(wc: dict[str, Any]) -> list[str]:
    f = []
    if wc.get("source") == "calculated_fallback":
        f.append("water: no 3 measured-water wells within 50 mi -> WOR from the bench's calculated / mixed water (flagged)")
    elif wc.get("source") == "none":
        f.append("water: no same-bench wells for a water cohort -> water stays the cohort's Arps fit")
    if wc.get("thin") and wc.get("source") == "measured":
        f.append(f"water: thin measured cohort ({len(wc.get('api10s') or [])} wells at {wc.get('radius_mi'):.0f} mi)")
    if wc.get("radius_mi") and wc["radius_mi"] > w.LADDER_MI[-1] and wc.get("source") == "measured":
        f.append(f"water: measured analogs reached {wc['radius_mi']:.0f} mi (past the D54 20-mi cap)")
    return f
