"""DB-free tests for the run-11 row preparation (box/prox_record.py)."""

from __future__ import annotations

import datetime as dt

import pandas as pd
import pytest
from shapely.geometry import LineString

from box import prox_pud as pp
from box import prox_record as prc

REF = dt.date(2026, 7, 1)


def _links():
    pud = {"api10": "101", "bench": "BS3_S", "fp": REF, "tvd_ft": 9850.0, "geom": LineString([(0, 0), (0, 10000)])}
    w = [{"api10": f"42389000{i:02d}", "bench": "WCA_1", "fp": dt.date(2020, 1, 1), "tvd_ft": 10190.0 + i, "geom": LineString([(x, 0), (x, 10000)])}
         for i, x in enumerate((450, -500, 1300))]
    lone = {"api10": "102", "bench": "BS3_S", "fp": REF, "tvd_ft": 9850.0, "geom": LineString([(9000, 0), (9000, 10000)])}
    return pp.links_frame(pp.pud_links(pud, w) + pp.pud_links(lone, w))


def _outcomes():
    return pd.DataFrame([
        {"location_id": 101, "coverage": "covered_provisional", "config_class": "topfill", "n_same": 0, "n_topfill": 3, "n_underfill": 0,
         "n_parents_total": 3, "flanked_topfill": True, "outcome": "no_forecast_package", "factor": 0.748, "haircut_key": "k2:topfill|3+|F",
         "pair_key": "BS3_S>topfill>WCA", "prec_multi": 88, "prec_package": 13, "n_permit_parents": 0, "n_recent_producers": 0},
        {"location_id": 102, "coverage": "covered", "config_class": None, "n_same": 0, "n_topfill": 0, "n_underfill": 0, "n_parents_total": 0,
         "flanked_topfill": False, "outcome": "as_is_unexposed", "factor": 1.0, "haircut_key": None, "pair_key": None, "prec_multi": None,
         "prec_package": None, "n_permit_parents": 0, "n_recent_producers": 0}])


def test_prepare_rows_and_coverage_move() -> None:
    r = prc.prepare(_outcomes(), _links(), "ref")
    p = r["prox"].set_index("location_id")
    assert p.at[101, "coverage"] == "not_covered_no_precedent" and p.at[102, "coverage"] == "covered"
    assert p.at[101, "label"] is None and bool(p.at[101, "flanked_topfill"])
    assert len(r["parents"]) == 3 and set(r["parents"]["cls"]) == {"topfill"} and (r["parents"]["age_days"] >= 365).all()
    assert r["expected"]["moved_to_no_precedent"] == {"covered_provisional": 1}


def test_prepare_refuses_a_configuration_that_does_not_match_the_reviewed_outcomes() -> None:
    o = _outcomes()
    o.loc[0, "n_topfill"] = 2
    with pytest.raises(RuntimeError, match="differs from the reviewed outcomes"):
        prc.prepare(o, _links(), "ref")


def test_haircut_rows_get_the_label_and_disclosure_names_the_exception() -> None:
    o = _outcomes()
    o.loc[0, ["outcome", "prec_package"]] = ["haircut", 69]
    r = prc.prepare(o, _links(), "ref")
    assert r["prox"].set_index("location_id").at[101, "label"] == prc.LABEL
    d = prc.disclosure(r["expected"], "ref", 100.0, 90.0)
    assert "FAIL" in d["validation"]["verdict_as_written"] and d["oil_eur_mmbbl"] == {"before": 100.0, "after": 90.0}
