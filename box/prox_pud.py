"""PDP-proximity study, step 4 — PUD-side measurement under the gate decisions (pure, no DB).

Decisions applied (FINDINGS §19-§20, Michael 2026-10-20):
  * gate 2c option (a): only MULTI-PARENT configurations get a haircut (class x count >= 2 x flank, mixed 2/3/4+), oil
    only, from docs/box/prox-2026-10-19/haircut_table_candidate.csv (cum-24, BOX's calibrated level); single-parent and
    unexposed PUDs stay at BOX as-is.
  * two-tier precedent: a multi-parent PUD needs >= 30 drilled multi-parent wells of its own bench pair (mixed: its own
    bench); when its haircut is severe (<= 0.80) those 30 must also be PACKAGES (>= 2 co-developed same-pool siblings).
    Short of either -> no forecast.
  * PUDs count EVERY existing producer >= 12 months on production at the run's data date: no shielding exemption; a
    permit-round producer TVD (rule 10) is counted and flagged.
The PUD is a "child" whose first production is the reference date, so the step-1 pair metric applies unchanged
(overlap = share of the PUD stick, median gap, dz = producer TVD - PUD TVD).
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import asdict, replace
from typing import Any

import numpy as np
import pandas as pd

from box import prox_dose as pdz
from box import prox_study as ps

SEVERE = 0.80
PRECEDENT_FLOOR = pdz.PRECEDENT_FLOOR
SIB_DH_FT = ps.PAIR_GATE_FT
OUTCOMES = ("as_is_unexposed", "as_is_single_parent", "haircut", "no_forecast_precedent", "no_forecast_package")


def pud_links(pud: dict[str, Any], cands: Iterable[dict[str, Any]]) -> list[ps.Link]:
    """Links from one PUD (its fp = the reference date) to existing producers; shielding off, permit = the PRODUCER's TVD
    is a round 100 (the PUD's own planned TVD is not a measurement either way)."""
    out = []
    for k in ps.links_for_child(pud, cands):
        prod_tvd = float(pud["tvd_ft"]) + k.dz_ft
        out.append(replace(k, shielded=False, permit=prod_tvd % 100 == 0))
    return out


def links_frame(links: list[ps.Link]) -> pd.DataFrame:
    cols = [f for f in ps.Link.__dataclass_fields__]
    return pd.DataFrame([asdict(k) for k in links], columns=cols)


def siblings(links: pd.DataFrame) -> pd.Series:
    """Drilled children: co-developed same-pool siblings (>= 30 % alongside, within the pair gate)."""
    s = links[(links["rel"] == "codev") & (links["cls"] == "same") & (links["overlap"] >= ps.MIN_OVERLAP) & (links["dh_ft"] <= SIB_DH_FT)]
    return s.groupby("child")["parent"].nunique()


def pair_key(cfg_class: str, bench: str, pb: str | None) -> str:
    return f"{ps.pool(bench)}>mixed" if cfg_class == "mixed" else f"{ps.pool(bench)}>{cfg_class}>{ps.pool(pb)}"


def precedent(children_cfg: pd.DataFrame, sib: pd.Series) -> dict[str, dict[str, int]]:
    """Per bench-pair key: drilled multi-parent wells and, of those, packages (>= 2 siblings). `children_cfg` =
    prox_dose.configuration for every drilled child + its `bench`."""
    out: dict[str, dict[str, int]] = {}
    for _, r in children_cfg.iterrows():
        cc = r["config_class"]
        if not isinstance(cc, str):
            continue
        if cc != "mixed" and int(r[f"n_{cc}"]) < 2:
            continue
        key = pair_key(cc, r["bench"], None if cc == "mixed" else r[f"pb_{cc}"])
        d = out.setdefault(key, {"multi": 0, "package": 0})
        d["multi"] += 1
        d["package"] += int(sib.get(r["api10"], 0) >= 2)
    return out


def haircut_lookup(table: pd.DataFrame) -> dict[str, float]:
    t = table[table["usable"].astype(bool)]
    return {f"{r.rung}:{r.key}": float(r.factor) for r in t.itertuples()}


def decide(r: Mapping[str, Any], hair: Mapping[str, float], prec: Mapping[str, Mapping[str, int]]) -> dict[str, Any]:
    """One PUD's outcome from its configuration row (prox_dose.configuration + bench)."""
    cc = r["config_class"]
    if not isinstance(cc, str):
        return {"outcome": "as_is_unexposed", "factor": 1.0, "haircut_key": None, "pair_key": None, "prec_multi": None, "prec_package": None}
    if cc != "mixed" and int(r[f"n_{cc}"]) < 2:
        return {"outcome": "as_is_single_parent", "factor": 1.0, "haircut_key": None, "pair_key": None, "prec_multi": None, "prec_package": None}
    if cc == "mixed":
        t = int(r["n_parents_total"])
        nb = "4+" if t >= 4 else str(t)
        ladder = [f"k2:mixed|{nb}", f"k3:mixed|{nb}", "k4:mixed"]
        pk = pair_key(cc, r["bench"], None)
    else:
        n = pdz.npar_bin(int(r[f"n_{cc}"]))
        fl = "F" if bool(r[f"flanked_{cc}"]) else "S"
        ladder = [f"k2:{cc}|{n}|{fl}", f"k3:{cc}|{n}", f"k4:{cc}"]
        pk = pair_key(cc, r["bench"], r[f"pb_{cc}"])
    key = next(k for k in ladder if k in hair)
    f = hair[key]
    p = prec.get(pk, {"multi": 0, "package": 0})
    if p["multi"] < PRECEDENT_FLOOR:
        out = "no_forecast_precedent"
    elif f <= SEVERE and p["package"] < PRECEDENT_FLOOR:
        out = "no_forecast_package"
    else:
        out = "haircut"
    return {"outcome": out, "factor": f, "haircut_key": key, "pair_key": pk, "prec_multi": p["multi"], "prec_package": p["package"]}


def decide_all(cfg: pd.DataFrame, hair: Mapping[str, float], prec: Mapping[str, Mapping[str, int]]) -> pd.DataFrame:
    rows = [decide(r, hair, prec) for _, r in cfg.iterrows()]
    return pd.DataFrame(rows, index=cfg.index)


def eur_effect(d: pd.DataFrame) -> pd.Series:
    """Oil EUR after the decision: as-is x1, haircut x factor, no-forecast 0."""
    f = np.where(d["outcome"].isin(["as_is_unexposed", "as_is_single_parent"]), 1.0,
                 np.where(d["outcome"] == "haircut", d["factor"].astype(float), 0.0))
    return d["oil_eur"].astype(float) * f
