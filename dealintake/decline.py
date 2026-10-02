"""Arps decline conversions. Di is NOMINAL per year everywhere in the suite.

Same formula as anduin forecasting/metrics.py:effective_decline_first_year
(and exports/param_row.py) — keep them identical:
    b ~ 0 : De = 1 - exp(-Di)
    b > 0 : De = 1 - (1 + b*Di) ** (-1/b)      (b = 1 -> Di / (1 + Di))
"""

from __future__ import annotations

import math

_B_EPS = 1e-9


def effective_from_nominal(di_nominal: float, b: float) -> float:
    """1-yr effective decline (fraction 0-1) from nominal Di (/yr) and b."""
    if di_nominal is None or b is None:
        raise ValueError("Di and b required")
    if abs(b) < _B_EPS:
        return 1.0 - math.exp(-di_nominal)
    return 1.0 - (1.0 + b * di_nominal) ** (-1.0 / b)


def nominal_from_effective(de: float, b: float) -> float:
    """Inverse of effective_from_nominal. de is a fraction in [0, 1)."""
    if not 0.0 <= de < 1.0:
        raise ValueError(f"effective decline must be in [0, 1): {de}")
    if abs(b) < _B_EPS:
        return -math.log(1.0 - de)
    return ((1.0 - de) ** (-b) - 1.0) / b


def fmt_di(di_nominal: float | None, b: float | None) -> str:
    """'2.33 /yr nom (70.0% eff yr-1)' — the house two-convention format."""
    if di_nominal is None or b is None:
        return "n/a"
    return f"{di_nominal:.2f} /yr nom ({effective_from_nominal(di_nominal, b) * 100:.1f}% eff yr-1)"
