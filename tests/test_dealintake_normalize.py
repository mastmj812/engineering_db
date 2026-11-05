"""v17 PROTOTYPE (report-only): BOX's D150 proximity factor + Cui lateral translation read on a deal-intake bench.
DB-free: a synthetic universe in UTM-13N feet."""

import datetime as dt

import numpy as np
import pytest

pytest.importorskip("shapely")
pytest.importorskip("pyproj")

import pandas as pd
import shapely
from shapely import affinity

from box import edge_gap as eg
from box import lateral as lat
from box import record23 as rc
from dealintake import normalize as nz
from dealintake.config import load
from dealintake.render.tables import (
    NORMALIZE_COHORT_HEADERS,
    NORMALIZE_HEADERS,
    normalize_rows,
)

STICK_LL = "LINESTRING (-103.33 31.287, -103.33 31.260)"          # ~9,900 ft N-S, Reeves
AS_OF = dt.date(2026, 11, 4)


def _universe(rows):
    """rows = [(api10, bench, fp, tvd, dx_ft)] — each a copy of the stick shifted dx_ft east, in feet."""
    base = eg.to_ft([shapely.from_wkt(STICK_LL)])[0]
    return pd.DataFrame([{"api10": a, "bench": b, "fp": fp, "tvd_ft": float(t), "geom": affinity.translate(base, dx, 0)}
                         for a, b, fp, t, dx in rows])


def test_config_v17_prototype_settings():
    cfg = load()
    assert cfg.version >= 17
    n = cfg["normalize"]
    assert n["enabled"] is True and [float(x) for x in n["lateral_window_ft"]] == [5000.0, 15000.0]
    assert int(n["cohort_size"]) == int(cfg["type_curve"]["max_wells"])


def test_stick_factor_matches_the_d150_surface():
    # one WCA producer 400 ft above, 200 ft east, 6 years on: level x F(hypot(200, a_above * 400))
    idx = nz._Index(_universe([("4200000001", "WCA_1", dt.date(2020, 1, 1), 10750, 200.0)]))
    sf = nz.stick_factors(idx, [{"id": "s1", "wkt": STICK_LL, "tvd_ft": 11150}], "WCB_2", AS_OF, "delaware")
    model, _ = rc.d150("delaware")
    want = model.level * float(model.curve(np.hypot(200.0, model.a_above * 400.0)))
    assert int(sf.loc["s1", "n_parents"]) == 1
    assert sf.loc["s1", "factor"] == pytest.approx(want, rel=1e-3)          # median gap on the sampled span ~ 200 ft


def test_stick_side_counts_only_producers_a_year_on_and_unexposed_gets_the_level():
    model, _ = rc.d150("delaware")
    young = _universe([("4200000002", "WCA_1", AS_OF - dt.timedelta(days=200), 10750, 200.0)])
    sf = nz.stick_factors(nz._Index(young), [{"id": "s1", "wkt": STICK_LL, "tvd_ft": 11150}], "WCB_2", AS_OF, "delaware")
    assert int(sf.loc["s1", "n_parents"]) == 0 and sf.loc["s1", "factor"] == pytest.approx(model.level)
    far = _universe([("4200000003", "WCA_1", dt.date(2020, 1, 1), 10750, 3000.0)])      # beyond the 2,640-ft pair gate
    sf = nz.stick_factors(nz._Index(far), [{"id": "s1", "wkt": STICK_LL, "tvd_ft": 11150}], "WCB_2", AS_OF, "delaware")
    assert int(sf.loc["s1", "n_parents"]) == 0 and sf.loc["s1", "factor"] == pytest.approx(model.level)


def test_analog_factor_drilled_side():
    model, _ = rc.d150("delaware")
    u = _universe([
        ("4200000010", "WCB_2", dt.date(2023, 1, 1), 11150, 0.0),      # the analog
        ("4200000011", "WCA_1", dt.date(2020, 1, 1), 10750, 300.0),    # parent: 3 yr on at the analog's first production
        ("4200000012", "WCA_2", dt.date(2022, 6, 1), 10790, -300.0),   # young (7 months): not a drilled-side parent
        ("4200000013", "WCA_1", dt.date(2019, 1, 1), 10800, 600.0),    # permit TVD (round 100): out on the drilled side
    ])
    fa = nz.analog_factors(nz._Index(u), ["4200000010", "4299999999"], "delaware")
    assert int(fa.loc["4200000010", "n_parents"]) == 1
    want = model.level * float(model.curve(np.hypot(300.0, model.a_above * 400.0)))
    assert fa.loc["4200000010", "factor"] == pytest.approx(want, rel=1e-3)
    assert np.isnan(fa.loc["4299999999", "factor"])                  # not in the universe -> no reading, not 1.0


def test_reading_and_per_well():
    r = nz.reading(50000.0, 0.80, [1.0, 0.9], 9900.0, [9900.0, 9900.0], "delaware")
    assert r["ratio"] == pytest.approx(0.8 / 0.95)
    assert r["cui"] == pytest.approx(1.0)
    assert r["eur_per_1000ft"] == pytest.approx(50000.0 * 0.8 / 0.95)
    r = nz.reading(50000.0, 0.80, [0.8], 9900.0, [7500.0], "delaware")        # longer than the cohort: Cui < 1
    assert r["cui"] == pytest.approx(lat.lateral_efficiency(9900.0) / lat.lateral_efficiency(7500.0))
    assert nz.reading(None, 0.8, [0.9], 9900.0, [9900.0], "delaware")["eur_per_1000ft"] is None
    fac = pd.DataFrame({"factor": [1.0, 0.5]}, index=["a", "b"])
    wells = [{"api10": "a", "anduin_oil_eur_per_1000ft": 40000.0, "lateral_length_ft": 9900.0},
             {"api10": "b", "anduin_oil_eur_per_1000ft": 20000.0, "lateral_length_ft": 9900.0}]
    assert nz.per_well(wells, fac, 0.9, 9900.0, "delaware") == pytest.approx(36000.0)   # both normalize to 40k x 0.9


def test_render_rows():
    sig = {"units": {"u1": {"n_sticks": 3, "stick_factor": 0.75, "stick_factor_range": [0.70, 0.78], "n_parents": [14, 16],
                            "tc_a_oil_eur_per_1000ft": 46957.0,
                            "A": {"mean_analog_factor": 0.95, "ratio": 0.789, "cui": 0.986, "eur_per_1000ft": 36530.0, "vs_tc": -0.222},
                            "B": {"mean_analog_factor": 0.97, "ratio": 0.773, "cui": 0.99, "eur_per_1000ft": 38000.0},
                            "B_per_well": 37000.0}},
           "tc_b_oil_eur_per_1000ft": 49600.0,
           "cohort_b": [{"api10": "4238941445", "well_name": "MARIINSKY STATE I 333H", "bench": "WCB_2",
                         "scenario_class": "codev_stack", "dist_mi": 0.3, "lateral_length_ft": 14988.0, "standoff_ft": 434.0,
                         "anduin_oil_eur_per_1000ft": None, "n_parents": 0.0, "factor": 1.046, "pattern": "none"}]}
    urows, wrows = normalize_rows(sig, {"u1": "9-16"})
    assert len(urows[0]) == len(NORMALIZE_HEADERS) and urows[0][0] == "9-16" and "-22.2%" in urows[0][8]
    assert len(wrows[0]) == len(NORMALIZE_COHORT_HEADERS) and wrows[0][8] == "—"
