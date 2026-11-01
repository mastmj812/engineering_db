"""BOX step 21a revision 1 — the Midland proximity rules (pure, no DB). The Delaware record (run 19) keeps box/prox_pud as is
(D144: the Delaware is revised later from what the Midland teaches; Michael 2026-10-31).

Two rules on top of D112-D116, from Michael's card-13 review (an MS stick between two producing MS wells, a JM 120 ft below and a
US above — "a stick that will never be drilled, and shouldn't be forecasted"):

  same-bench depth cap  a neighbour is SAME bench only when it carries the stick's BOX bench AND sits within 300 ft vertically;
                        a same-tag well farther off is classed by its depth — below (topfill) when deeper, above (underfill)
                        when shallower — and then needs that class's envelope (800 ft below / 500 ft above). The 1,000-ft
                        same-bench cap was a leftover of the exposure screen (drilled same-tag pairs: median 48 ft, p99 334 ft).
  neighbour pattern     a stick with 2+ neighbours is forecast only when >= 30 drilled Midland wells of ITS bench, also with 2+
                        neighbours, were drilled into the SAME pattern: same-bench neighbours on one side / both sides / none,
                        plus whether a neighbour sits above and whether one sits below. Added ON TOP of D114 (the bench-pair
                        precedent and its package tier still apply), so it never forecasts a stick D114 did not: the D114
                        'mixed' key is the bench alone, and 0 of the 82 MS>mixed precedents had a neighbour above. The
                        pattern's PACKAGE count is reported, not gated (a pattern package tier keyed on the interim Delaware
                        factor would have refused 1,751 more sticks; not approved).
Single-neighbour sticks stay forecast as-is (option (a)); unexposed sticks are untouched.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

import numpy as np
import pandas as pd

from box import prox_pud as pp
from box import prox_study as ps

SAME_DV_MAX_FT = 300.0
PATTERN_FLOOR = pp.PRECEDENT_FLOOR
OUTCOMES = (*pp.OUTCOMES, "no_forecast_pattern")
SIDES = ("none beside", "one side", "both sides")


def reclass_same(links: pd.DataFrame, dv_max: float = SAME_DV_MAX_FT) -> pd.DataFrame:
    """Same-tag links more than `dv_max` apart vertically become below (topfill, parent deeper: dz > 0) or above (underfill)."""
    x = links.copy()
    far = (x["cls"] == "same") & (x["dv_ft"] > dv_max)
    x.loc[far, "cls"] = np.where(x.loc[far, "dz_ft"] > 0, "topfill", "underfill")
    return x


def is_multi(cfg: pd.DataFrame) -> pd.Series:
    """2+ neighbours (prox_dose.configuration rows): a mixed configuration, or 2+ in its one class."""
    cc = cfg["config_class"]
    return cc.notna() & ((cc == "mixed") | (cfg["n_parents_total"] >= 2))


def pattern(cfg: pd.DataFrame) -> pd.Series:
    """'<sides>[+above][+below]' per configuration row; None where unexposed. Both sides = 2+ same-bench neighbours, flanked."""
    side = np.where((cfg["n_same"] >= 2) & cfg["flanked_same"].astype(bool), SIDES[2], np.where(cfg["n_same"] >= 1, SIDES[1], SIDES[0]))
    out = [f"{s}{'+above' if a > 0 else ''}{'+below' if b > 0 else ''}" for s, a, b in zip(side, cfg["n_underfill"], cfg["n_topfill"], strict=True)]
    return pd.Series([p if isinstance(c, str) else None for p, c in zip(out, cfg["config_class"], strict=True)], index=cfg.index)


def pattern_key(bench: str, pat: str) -> str:
    return f"{ps.pool(bench)}|{pat}"


def pattern_precedent(children_cfg: pd.DataFrame, sib: pd.Series) -> dict[str, dict[str, int]]:
    """Per bench x pattern: drilled 2+-neighbour wells and, of those, packages (>= 2 co-developed same-pool siblings).
    `children_cfg` = prox_dose.configuration for every drilled child + its `bench`."""
    c = children_cfg[is_multi(children_cfg)]
    keys = [pattern_key(b, p) for b, p in zip(c["bench"], pattern(c), strict=True)]
    out: dict[str, dict[str, int]] = {}
    for k, a in zip(keys, c["api10"], strict=True):
        d = out.setdefault(k, {"multi": 0, "package": 0})
        d["multi"] += 1
        d["package"] += int(sib.get(a, 0) >= 2)
    return out


def decide_all(cfg: pd.DataFrame, hair: Mapping[str, float], prec: Mapping[str, Mapping[str, int]],
               prec_pattern: Mapping[str, Mapping[str, int]]) -> pd.DataFrame:
    """box/prox_pud.decide_all (D114, unchanged), then the pattern test on every multi-neighbour stick D114 still forecasts.
    `cfg` = configuration rows + `bench`. Adds pattern, pattern_key, pattern_multi, pattern_package."""
    d = pp.decide_all(cfg, hair, prec)
    pat = pattern(cfg)
    multi = is_multi(cfg)
    rows: list[dict[str, Any]] = []
    for i in cfg.index:
        if not multi[i]:
            rows.append({"pattern": pat[i], "pattern_key": None, "pattern_multi": None, "pattern_package": None})
            continue
        k = pattern_key(cfg.at[i, "bench"], pat[i])
        p = prec_pattern.get(k, {"multi": 0, "package": 0})
        rows.append({"pattern": pat[i], "pattern_key": k, "pattern_multi": p["multi"], "pattern_package": p["package"]})
    out = d.join(pd.DataFrame(rows, index=cfg.index))
    out.loc[(out["outcome"] == "haircut") & (out["pattern_multi"].fillna(0) < PATTERN_FLOOR), "outcome"] = "no_forecast_pattern"
    return out
