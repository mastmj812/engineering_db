"""DB-free tests for the step-4 PUD measurement (box/prox_pud.py)."""

from __future__ import annotations

import datetime as dt

import pandas as pd
import pytest
from shapely.geometry import LineString

from box import prox_pud as pp

REF = dt.date(2026, 7, 1)
PUD = {"api10": "L1", "bench": "BS3_S", "fp": REF, "tvd_ft": 9850.0, "geom": LineString([(0, 0), (0, 10000)])}


def _w(a, x, tvd, fp=dt.date(2020, 1, 1), bench="WCA_1"):
    return {"api10": a, "bench": bench, "fp": fp, "tvd_ft": tvd, "geom": LineString([(x, 0), (x, 10000)])}


def test_pud_links_no_shielding_and_permit_is_the_producers_depth() -> None:
    ks = pp.pud_links(PUD, [_w("P1", 400, 10200.0), _w("P2", -500, 10237.0), _w("C", 100, 10050.0, bench="BS3_C", fp=REF)])
    by = {k.parent: k for k in ks}
    assert by["P1"].permit and not by["P2"].permit                 # 10,200 is a round-100 producer TVD; 9,850 (PUD) is not
    assert not by["P1"].shielded and not by["P2"].shielded          # the co-dev BS3_C well would shield in step 1 - not for PUDs
    assert by["C"].rel == "codev" and by["P1"].rel == "parent" and by["P1"].cls == "topfill"


HAIR = {"k2:topfill|3+|F": 0.75, "k3:topfill|2": 0.88, "k2:same|2|S": 0.93, "k3:mixed|4+": 0.78, "k4:topfill": 0.90}
PREC = {"BS3_S>topfill>WCA": {"multi": 88, "package": 13}, "BS3_C>topfill>WCA": {"multi": 142, "package": 69},
        "WCA>same>WCA": {"multi": 567, "package": 391}, "BS2_C>topfill>BS2_S": {"multi": 20, "package": 5}, "WCA>mixed": {"multi": 300, "package": 20}}


def _row(cc, bench, n=0, fl=False, pb="WCA_1", tot=None):
    r = {"config_class": cc, "bench": bench, "n_parents_total": tot if tot is not None else n}
    for c in ("same", "topfill", "underfill"):
        r[f"n_{c}"], r[f"flanked_{c}"], r[f"pb_{c}"] = (n, fl, pb) if c == cc else (0, False, None)
    return r


@pytest.mark.parametrize(("row", "outcome", "factor"), [
    (_row(None, "BS3_S"), "as_is_unexposed", 1.0),
    (_row("topfill", "BS3_S", 1), "as_is_single_parent", 1.0),
    (_row("topfill", "BS3_S", 3, True), "no_forecast_package", 0.75),     # severe + 13 packages < 30
    (_row("topfill", "BS3_C", 3, True), "haircut", 0.75),                 # severe, 69 packages
    (_row("topfill", "BS3_S", 2, False), "haircut", 0.88),                # 2 one-sided -> k3 0.88, not severe: multi 88 >= 30 enough
    (_row("topfill", "BS2_C", 2, True, pb="BS2_S"), "no_forecast_precedent", 0.88),  # k2 key missing -> k3; 20 drilled < 30
    (_row("same", "WCXY", 2, False, pb="WCA_2"), "haircut", 0.93),        # WCXY pools with WCA
    (_row("mixed", "WCA_1", tot=5), "no_forecast_package", 0.78),         # mixed 4+ severe, 20 packages
])
def test_decide(row, outcome, factor) -> None:
    d = pp.decide(row, HAIR, PREC)
    assert d["outcome"] == outcome and d["factor"] == pytest.approx(factor)


def test_precedent_counts_multi_and_packages() -> None:
    cfg = pd.DataFrame([{**_row("topfill", "BS3_S", 3, True), "api10": "a"}, {**_row("topfill", "BS3_S", 2, False), "api10": "b"},
                        {**_row("topfill", "BS3_S", 1), "api10": "c"}, {**_row("mixed", "WCA_2", tot=4), "api10": "d"}])
    p = pp.precedent(cfg, pd.Series({"a": 2, "b": 1, "d": 3}))
    assert p == {"BS3_S>topfill>WCA": {"multi": 2, "package": 1}, "WCA>mixed": {"multi": 1, "package": 1}}


def test_eur_effect() -> None:
    d = pd.DataFrame({"outcome": ["as_is_unexposed", "haircut", "no_forecast_package"], "factor": [1.0, 0.75, 0.75], "oil_eur": [100.0, 100.0, 100.0]})
    assert pp.eur_effect(d).tolist() == [100.0, 75.0, 0.0]
