"""BOX step 12b — water on a stored record run (pure pieces; scripts/box_water_run.py does the DB work).

Water at a covered location (D107 / D108 / D110): the measured-water cohort of box/water11 (selection as of the run's data-through),
its WOR-vs-cum-oil ratio (boxfit ratio mode on the cohort's per-1,000-ft mean oil + water), applied month by month to the
location's RAW box_v2 oil months (run.pkl `months_raw`, 600 months, uptime-free, x lateral multiplier) — never the haircut oil.
No water haircut, no F(k) applied (D63: volumes uptime-free). Tier per group (D110): validated on WCA and BS2_S `covered` rows,
provisional everywhere else; never above the location's coverage.
"""

from __future__ import annotations

import math
from collections.abc import Mapping, Sequence
from typing import Any

import numpy as np

from box import water11 as w

VALIDATED_WATER_GROUPS: tuple[str, ...] = ("WCA", "BS2_S")  # D110
METHOD = "ratio_wor_vs_cum_oil (D107)"
OIL_BASIS = "raw box_v2 oil months, before any haircut (D108)"
N_MONTHS = 600


def water_tier(group: str, coverage: str) -> str:
    return "validated" if group in VALIDATED_WATER_GROUPS and coverage == "covered" else "provisional"


def water_months(oil_months_raw: Sequence[float], lateral_ft: float, ratio: Mapping[str, Any]) -> np.ndarray:
    """600 water months = WOR(Np per 1,000 ft) x the raw oil months (water11.ratio_water on the full horizon)."""
    m = np.asarray(oil_months_raw, float)
    if len(m) != N_MONTHS:
        raise ValueError(f"expected {N_MONTHS} oil months, got {len(m)}")
    return w.ratio_water(m, lateral_ft, ratio)


def stream_row(months: np.ndarray, lateral_ft: float, lateral_mult: float) -> dict[str, float]:
    """eur = the exact sum of the stored months (D39: rows sum to the EUR); no haircut on water."""
    eur = float(np.sum(months))
    return {"lateral_mult": float(lateral_mult), "eur_haircut": 1.0, "eur_raw": eur, "eur": eur, "eur_per_kft": eur / (lateral_ft / 1000.0),
            "cum12": float(np.sum(months[:12])), "cum24": float(np.sum(months[:24]))}


def params(ratio: Mapping[str, Any], sel: Mapping[str, Any]) -> dict[str, Any]:
    return {"method": METHOD, "oil_basis": OIL_BASIS, "alpha": float(ratio["alpha"]), "beta": float(ratio["beta"]),
            "sub_mode": ratio.get("sub_mode"), "r2": ratio.get("r2"), "n_months_fit": ratio.get("n_months"),
            "source": sel["source"], "search": "circle", "radius_mi": float(sel["radius_mi"]), "thin": bool(sel["thin"]),
            "n_analogs": len(sel["api10s"]), "n_eligible": int(sel["n_eligible"]),
            "nm_share": None if not math.isfinite(sel["nm_share"]) else float(sel["nm_share"])}


def flags(sel: Mapping[str, Any]) -> list[str]:
    f = []
    if sel["source"] == "calculated_fallback":
        f.append("water: calculated-water fallback (fewer than 3 measured analogs at 50 mi)")
    if sel["thin"]:
        f.append("water: thin measured cohort (< 10 analogs)")
    if sel["radius_mi"] > w.LADDER_MI[-1]:
        f.append(f"water: measured analogs reached {sel['radius_mi']:.0f} mi (water extension past the D54 20-mi cap)")
    return f


def analog_rows(loc: Mapping[str, Any], api10s: Sequence[str], pool: Mapping[str, Mapping[str, Any]]) -> list[dict[str, Any]]:
    """Ranked water analogs (selection order) with distance (lateral midpoints, ft), state, label, first production."""
    out = []
    for k, a in enumerate(api10s, start=1):
        p = pool[a]
        out.append({"api10": a, "rank": k, "dist_ft": float(math.hypot(p["x"] - loc["x"], p["y"] - loc["y"])), "state_code": p["state_code"],
                    "water_label": p["label"], "first_production": p["first_production_date"]})
    return out
