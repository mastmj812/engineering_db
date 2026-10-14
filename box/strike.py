"""BOX D55 — local structural strike from the producing wells' own TVDs, and the strike-aligned (elliptical) analog
distance used when an analog search must reach beyond its first ring (pure).

Strike: within `radius_ft` of a location, fit TVD = a + b·x + c·y (least squares) to the bench's producing wells (lateral
midpoint, one TVD per well). The dip direction is the gradient (b, c) — TVD increases down-dip — and strike is
perpendicular to it. Azimuths are axial, folded to [0, 180) (rule 16), measured clockwise from grid north in the projected
frame (UTM 13N ft). The fit is trusted only with >= MIN_WELLS wells and a plane R² >= MIN_R2; a flat or noisy
neighbourhood has no strike (circle search then).

Elliptical distance: offsets are rotated into (along-strike, across-strike) and the across component is stretched by
ASPECT, so an analog 2 mi along strike counts like 1 mi across it (aspect 2).

Holden's structure grids are a CROSS-CHECK only (D55): `angle_diff` compares two axial azimuths.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

import numpy as np

RADIUS_FT = 3 * 5280.0
MIN_WELLS = 8
MIN_R2 = 0.30
ASPECT = 2.0


@dataclass(frozen=True)
class Strike:
    azimuth_deg: float  # axial strike, [0, 180), clockwise from grid north
    dip_ft_per_mi: float
    r2: float
    n: int


def fold(az: float) -> float:
    return float(az % 180.0)


def angle_diff(a: float, b: float) -> float:
    """Axial angular distance in [0, 90] (rule 16: never abs(a - b))."""
    d = abs(fold(a) - fold(b)) % 180.0
    return min(d, 180.0 - d)


def local_strike(x: np.ndarray, y: np.ndarray, tvd: np.ndarray, x0: float, y0: float, radius_ft: float = RADIUS_FT,
                 min_wells: int = MIN_WELLS, min_r2: float = MIN_R2) -> Strike | None:
    x, y, z = np.asarray(x, float), np.asarray(y, float), np.asarray(tvd, float)
    m = np.isfinite(z) & (np.hypot(x - x0, y - y0) <= radius_ft)
    if m.sum() < min_wells:
        return None
    X = np.column_stack([np.ones(m.sum()), x[m] - x0, y[m] - y0])
    coef, *_ = np.linalg.lstsq(X, z[m], rcond=None)
    resid = z[m] - X @ coef
    ss = float(np.sum((z[m] - z[m].mean()) ** 2))
    r2 = 1.0 - float(resid @ resid) / ss if ss > 0 else 0.0
    gx, gy = float(coef[1]), float(coef[2])
    g = math.hypot(gx, gy)
    if g == 0 or r2 < min_r2:
        return None
    dip_az = math.degrees(math.atan2(gx, gy))  # bearing of increasing TVD (down-dip), clockwise from north
    return Strike(azimuth_deg=fold(dip_az + 90.0), dip_ft_per_mi=g * 5280.0, r2=r2, n=int(m.sum()))


def ellipse_distance(dx: np.ndarray, dy: np.ndarray, strike_az_deg: float, aspect: float = ASPECT) -> np.ndarray:
    """Distance with the across-strike component stretched by `aspect` (offsets dx = east, dy = north, ft)."""
    t = math.radians(strike_az_deg)
    ux, uy = math.sin(t), math.cos(t)  # unit vector along strike
    along = np.asarray(dx) * ux + np.asarray(dy) * uy
    across = -np.asarray(dx) * uy + np.asarray(dy) * ux
    return np.hypot(along, aspect * across)
