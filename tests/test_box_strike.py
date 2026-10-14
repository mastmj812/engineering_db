"""DB-free tests for D55 local strike + elliptical distance (box/strike.py)."""

from __future__ import annotations

import numpy as np
import pytest

from box import strike as st


def test_strike_perpendicular_to_dip() -> None:
    rng = np.random.default_rng(1)
    x, y = rng.uniform(-10000, 10000, 60), rng.uniform(-10000, 10000, 60)
    tvd = 9000 + 0.02 * x + rng.normal(0, 5, 60)  # deepens to the EAST: dip az 90 -> strike N-S (0)
    s = st.local_strike(x, y, tvd, 0.0, 0.0)
    assert s is not None and st.angle_diff(s.azimuth_deg, 0.0) < 2.0
    assert s.dip_ft_per_mi == pytest.approx(0.02 * 5280, rel=0.05)


def test_no_strike_when_flat_or_thin() -> None:
    rng = np.random.default_rng(2)
    x, y = rng.uniform(-5000, 5000, 40), rng.uniform(-5000, 5000, 40)
    assert st.local_strike(x, y, 9000 + rng.normal(0, 30, 40), 0, 0) is None  # noise only: R2 too low
    assert st.local_strike(x[:5], y[:5], 9000 + 0.02 * x[:5], 0, 0) is None  # too few wells


def test_ellipse_distance_and_axial_diff() -> None:
    # strike N-S: 2 mi north (along) counts 2 mi; 1 mi east (across) counts 2 mi at aspect 2
    d = st.ellipse_distance(np.array([0.0, 5280.0]), np.array([10560.0, 0.0]), 0.0)
    assert d[0] == pytest.approx(10560.0) and d[1] == pytest.approx(10560.0)
    assert st.angle_diff(179.0, 1.0) == pytest.approx(2.0)
    assert st.angle_diff(45.0, 135.0) == pytest.approx(90.0)
