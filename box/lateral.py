"""BOX lateral-length efficiency (D50): per-ft performance falls with lateral length (pure).

A per-1,000-ft area curve is the mean over its members, whose laterals differ. Under the efficiency model
q_i / L_i = base x E(L_i), the curve = base x mean E(L_member), so a well or PUD of lateral L is predicted as
    curve_per_kft x L / 1,000 x E(L) / mean E(L_member)
(`relative`), which keeps the area's own lateral mix as the reference. Curve of record = Cui & Cross (Novi Labs),
URTeC 3723784 (2022), Delaware Wolfcamp A, 2,000 lb / 60 bbl per ft (the WCA cohort completes at ~2,500 lb /
50 bbl per ft; 1,700 / 50 agrees within 0.3 pt in the step-6 backtest). Past the paper's 12,500-ft Delaware range
the last segment's slope is extended (flagged in docs/box/step6-2026-10-12/FINDINGS.md §5).

Each basin translates with its OWN panel of the paper's Figure 8 (step 21a revision 7, Michael 2026-11-01): the Midland panel
(Wolfcamp A, 5,000-15,000 ft) is near-flat and matches the observed Midland per-ft oil within ~2 % from 5,000 to 17,500 ft
(docs/box/step21a-2026-10-31/FINDINGS.md §2); the Delaware panel is unchanged and remains the default.
"""

from __future__ import annotations

import itertools
from collections.abc import Sequence

import numpy as np

from box import basin as bsn

RECORD_CURVE = "2000-60"

# Cui & Cross (Novi Labs), URTeC 3723784 (2022), Figure 8, Delaware Wolfcamp A: 3-yr oil per ft relative to a
# 5,000-ft lateral, by completion size (lb/ft - bbl/ft). 10,000-ft values are the paper's labels; 7,500 / 12,500
# read off the figure (+-0.005). docs/box/ref/3723784.pdf.
CUI_DELAWARE: dict[str, tuple[tuple[float, float], ...]] = {
    "1000-30": ((5000, 1.000), (7500, 1.000), (10000, 0.94), (12500, 0.896)),
    "1350-40": ((5000, 1.000), (7500, 0.949), (10000, 0.89), (12500, 0.851)),
    "1700-50": ((5000, 1.000), (7500, 0.910), (10000, 0.85), (12500, 0.820)),
    "2000-60": ((5000, 1.000), (7500, 0.888), (10000, 0.83), (12500, 0.801)),
}
# Same figure, Midland panel (Wolfcamp A, to 15,000 ft): read off the figure's pixels (+-0.003; 27.3 px per point of efficiency);
# the 10,000-ft values agree with the paper's labels 0.99 / 0.99 / 0.97 / 0.96. At 7,500 ft the 1350-40 and 1700-50 markers
# overlap (read as one 8-px group, split +-0.001).
CUI_MIDLAND: dict[str, tuple[tuple[float, float], ...]] = {
    "1000-30": ((5000, 1.000), (7500, 0.989), (10000, 0.992), (12500, 0.989), (15000, 0.989)),
    "1350-40": ((5000, 1.000), (7500, 0.985), (10000, 0.985), (12500, 0.982), (15000, 0.978)),
    "1700-50": ((5000, 1.000), (7500, 0.983), (10000, 0.972), (12500, 0.967), (15000, 0.965)),
    "2000-60": ((5000, 1.000), (7500, 0.977), (10000, 0.956), (12500, 0.954), (15000, 0.951)),
}
CUI: dict[str, dict[str, tuple[tuple[float, float], ...]]] = {bsn.DELAWARE: CUI_DELAWARE, bsn.MIDLAND: CUI_MIDLAND}
CUI_DE_TWIN = "_cuide"  # suffix of a twin prediction translated with the Delaware panel (non-Delaware runs, step 21a revision 7)


def paper_max_ft(basin: str = bsn.DELAWARE) -> float:
    """The paper's last lateral for the basin's panel; past it E(L) is the extended last segment (flagged)."""
    return float(CUI[basin][RECORD_CURVE][-1][0])


def lateral_efficiency(lateral_ft: float, curve: str = RECORD_CURVE, basin: str = bsn.DELAWARE) -> float:
    """Per-ft efficiency vs a 5,000-ft lateral on the basin's panel: linear between the paper's points, 1.0 below 5,000 ft,
    and the last segment's slope extended past the panel's range (12,500 ft Delaware, 15,000 ft Midland; flagged)."""
    pts = CUI[basin][curve]
    x = float(lateral_ft)
    if not np.isfinite(x):
        return float("nan")
    if x <= pts[0][0]:
        return pts[0][1]
    for (x0, y0), (x1, y1) in itertools.pairwise(pts):
        if x <= x1:
            return y0 + (y1 - y0) * (x - x0) / (x1 - x0)
    (x0, y0), (x1, y1) = pts[-2], pts[-1]
    return y1 + (y1 - y0) * (x - x1) / (x1 - x0)



# Step 21b revision 8 (Michael 2026-11-02): on the Midland a target LONGER than its cohort's mean lateral translates on the
# Delaware panel, any other on the Midland panel. The 21b tuning view: Midland per-ft oil falls going longer than the cohort
# (>= 15,000 ft -12.6 % on the Midland panel, -6.7 % on the Delaware one, cum-12) but short targets earn no per-ft bonus
# (5,000-7,500 ft -2.7 % Midland, -9.3 % Delaware). A basin not keyed here translates on its own panel (the Delaware, unchanged).
LONGER_PANEL: dict[str, str] = {bsn.MIDLAND: bsn.DELAWARE}


def panel(lateral_ft: float, member_laterals: Sequence[float], basin: str = bsn.DELAWARE) -> str:
    """The panel a target translates on: LONGER_PANEL[basin] when L > its members' mean lateral, else the basin's own."""
    ms = [float(x) for x in member_laterals if x is not None and np.isfinite(x) and x > 0]
    return LONGER_PANEL.get(basin, basin) if ms and float(lateral_ft) > float(np.mean(ms)) else basin


def relative(lateral_ft: float, member_laterals: Sequence[float], curve: str = RECORD_CURVE, basin: str = bsn.DELAWARE) -> float:
    """E(L) / mean E(L_member): the multiplier on (area curve per kft x L / 1,000) for a well or PUD of lateral L, on `panel`."""
    ms = [float(x) for x in member_laterals if x is not None and np.isfinite(x) and x > 0]
    if not ms:
        raise ValueError("no member laterals")
    p = panel(lateral_ft, ms, basin)
    return lateral_efficiency(lateral_ft, curve, p) / float(np.mean([lateral_efficiency(x, curve, p) for x in ms]))
