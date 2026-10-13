"""BOX frozen spatial holdout (D52, Michael 2026-10-13) — pure, deterministic, no stored list.

A 3-mile square block (UTM 13N ft, the step-4 / 5c block size) is in the holdout when a salted SHA-256 of its integer
block coordinates falls in the first SHARE of the hash space. Any well — past, present or a future well in a block
nobody has seen — is classified the same way forever, so nothing has to be stored or maintained. Holdout wells are
excluded from every tuning / decision view; they are scored ONCE, when the model spec is frozen (code SHA recorded),
alongside the prospective confirmation on wells that first produce after the freeze.

Changing SALT, BLOCK_FT or SHARE re-draws the holdout and voids it — never do that after a look at holdout results.
"""

from __future__ import annotations

import hashlib
from functools import cache

import numpy as np

SALT = "box-holdout-2026-10-13"
BLOCK_FT = 15_840.0  # 3 mi
SHARE = 0.20


@cache
def block_is_holdout(bx: int, by: int) -> bool:
    h = hashlib.sha256(f"{SALT}:{bx}:{by}".encode()).digest()
    return int.from_bytes(h[:8], "big") / 2**64 < SHARE


def blocks(x_ft: np.ndarray, y_ft: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    return np.floor(np.asarray(x_ft, float) / BLOCK_FT).astype(np.int64), np.floor(np.asarray(y_ft, float) / BLOCK_FT).astype(np.int64)


def is_holdout(x_ft: np.ndarray, y_ft: np.ndarray) -> np.ndarray:
    """True per point (lateral midpoint, UTM 13N ft) inside a holdout block."""
    bx, by = blocks(x_ft, y_ft)
    return np.array([block_is_holdout(int(a), int(b)) for a, b in zip(bx, by, strict=True)], dtype=bool)
