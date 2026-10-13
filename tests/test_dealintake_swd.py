"""SWD context (dealintake/swd.py): pure exposure maths, the suspect rule, the
flags, and the renderers tolerating signals with and without the section."""

from datetime import date

import pytest

pytest.importorskip("shapely")

from shapely.geometry import box

from dealintake import swd
from tests._dealintake_fixtures import line_ft, point_lonlat_ft

SCFG = {"radius_mi": 2.0, "vert_window_ft": 3000, "min_cum_mmbbl": 5.0, "poor_frac_of_median": 0.5}


def _inj(name, x_ft, y_ft, top, bottom, cum_mmbbl, months=(), status="active"):
    lon, lat = point_lonlat_ft(x_ft, y_ft)
    return {"id": hash(name) & 0xFFFF, "uic_number": f"U-{name}", "name": name, "operator": "LAYNE", "permit_status": status,
            "injection_top_ft": top, "injection_bottom_ft": bottom, "latitude": lat, "longitude": lon,
            "cumulative_bbl": cum_mmbbl * 1e6, "trailing_12m_bpd": 10000, "latest_psi_max": 1667,
            "pressure_trend_12m": "falling", "latest_reported_month": date(2025, 11, 1),
            "months": [(date(y, m, 1), v) for (y, m, v) in months]}


def test_exposure_measures_from_the_stick_and_splits_volume_at_first_production():
    """Shredder-shaped case: a 9,000 ft lateral at 9,244 ft with an injector
    ~1 mi off the heel, interval 4,500–6,400 (2,844 ft above, inside a 3,000 ft
    window), 22 MMbbl, and one far injector outside the radius."""
    stick = line_ft((0, 0), (9000, 0))
    pit_stop = _inj("PIT STOP SWD 1", 0, 5280, 4500, 6400, 22.1,
                    months=[(2021, 6, 300_000), (2022, 6, 400_000), (2024, 6, 500_000)])
    far = _inj("FAR SWD", 0, 5280 * 3, 4500, 6400, 50)
    e = swd.exposure(stick, 9244, [pit_stop, far], SCFG, first_prod=date(2021, 11, 23))
    assert e["n_within"] == 1 and e["n_counted"] == 1 and e["exposed"]
    r = e["injectors"][0]
    assert r["name"] == "PIT STOP SWD 1" and r["dist_mi"] == pytest.approx(1.0, abs=0.02)
    assert r["standoff_ft"] == 9244 - 6400 and r["near"] is True
    assert r["pre_mmbbl"] == 0.3 and r["w24_mmbbl"] == 0.4 and r["since_mmbbl"] == 0.9
    assert e["nearest"]["name"] == "PIT STOP SWD 1" and e["max_latest_psi"] == 1667


def test_exposure_near_window_and_minimum_volume():
    stick = line_ft((0, 0), (5000, 0))
    deep_gap = _inj("DEEP GAP", 0, 2000, 3000, 5000, 30)      # bottom 4,244 ft above a 9,244 landing: not near at 3,000
    small = _inj("SMALL", 0, 2000, 6000, 8000, 1.0)            # near, but under min_cum: does not count as exposure
    e = swd.exposure(stick, 9244, [deep_gap, small], SCFG)
    assert e["n_within"] == 2 and e["n_counted"] == 1 and e["n_near"] == 0
    assert e["nearest"]["name"] == "DEEP GAP" and e["biggest"]["name"] == "DEEP GAP"
    assert [r["counts"] for r in e["injectors"]] == [True, False]


def test_cohort_context_flags_poor_and_exposed_only():
    inj = [_inj("PIT STOP SWD 1", 0, 5280, 4500, 6400, 22.1)]
    sticks = {"A": line_ft((0, 0), (9000, 0)).wkt, "B": line_ft((0, 0), (9000, 0)).wkt, "C": line_ft((0, 30000), (9000, 30000)).wkt}
    cohort = [
        {"api10": "A", "well_name": "SHREDDER 2WA", "tvd_ft": 9244, "anduin_oil_eur_per_1000ft": 8_000, "first_production_date": "2021-11-23"},
        {"api10": "B", "well_name": "GOOD EXPOSED", "tvd_ft": 9244, "anduin_oil_eur_per_1000ft": 60_000, "first_production_date": "2022-01-01"},
        {"api10": "C", "well_name": "POOR FAR", "tvd_ft": 9244, "anduin_oil_eur_per_1000ft": 9_000, "first_production_date": "2022-01-01"},
        {"api10": "D", "well_name": "NO GEOM", "tvd_ft": 9244, "anduin_oil_eur_per_1000ft": 50_000},
    ]
    g = swd.cohort_context(cohort, sticks, inj, SCFG)
    assert g["n"] == 3 and g["perf_metric"].startswith("anduin")
    by = {r["api10"]: r for r in g["wells"]}
    assert by["A"]["suspect"] and by["A"]["poor"] and by["A"]["exposed"]
    assert by["B"]["exposed"] and not by["B"]["poor"] and not by["B"]["suspect"]
    assert by["C"]["poor"] and not by["C"]["exposed"] and not by["C"]["suspect"]
    # the cohort median is over all four wells (8k, 9k, 50k, 60k -> 29.5k), geometry or not
    assert g["n_suspect"] == 1 and g["n_exposed"] == 2 and g["poor_cutoff"] == pytest.approx(0.5 * 29_500)
    assert g["exposed_median"] == pytest.approx(34_000) and g["clear_median"] == 9_000


def test_flags_name_the_suspect_and_the_unit_proximity():
    unit = box(-103.5, 31.57, -103.49, 31.58)
    inj = [_inj("PIT STOP SWD 1", 0, 5280, 4500, 6400, 22.1)]
    cohort = [{"api10": "A", "well_name": "SHREDDER 2WA", "tvd_ft": 9244, "eur_per_1000ft": 4_000},
              {"api10": "B", "well_name": "GOOD", "tvd_ft": 9244, "eur_per_1000ft": 40_000}]
    sticks = {"A": line_ft((0, 0), (9000, 0)).wkt, "B": line_ft((0, 40000), (9000, 40000)).wkt}
    g = swd.cohort_context(cohort, sticks, inj, SCFG)
    u = {"n_injectors": 1, "n_near": 1, "n_active": 1, "radius_mi": 2.0, "vert_window_ft": 3000,
         "nearest": g["wells"][0]["nearest"], "biggest": None, "max_latest_psi": 1667, "n_sticks": 2, "n_sticks_exposed": 2}
    out = swd.flags(g, {"DSU 33": u, "DSU 34": None})
    assert len(out) == 2
    assert out[0].startswith("SWD proximity: DSU 33 (1 injector(s) within 2 mi, 1 within 3,000 ft of the landing; nearest PIT STOP SWD 1 1")
    assert "2,844 ft above" in out[0]
    assert "SWD evidence: 1 of 2 cohort wells are BOTH poor" in out[1] and "SHREDDER 2WA" in out[1] and "Toucan" in out[1]
    assert swd.flags({"n": 0}, {"x": None}) == []


def test_resolve_dsn_prefers_env(monkeypatch):
    monkeypatch.setenv("SWD_DSN", "postgresql://x@localhost:5434/swd")
    assert swd.resolve_dsn() == "postgresql://x@localhost:5434/swd"
    monkeypatch.setenv("SWD_DSN", "")
    assert swd.resolve_dsn() is None or swd.resolve_dsn().startswith("postgresql://")  # sibling c4/.env may or may not exist


def test_maybe_connect_yields_none_when_unavailable(monkeypatch):
    monkeypatch.setenv("SWD_DSN", "postgresql://nobody@127.0.0.1:1/none?connect_timeout=1")
    with swd.maybe_connect() as conn:
        assert conn is None
    assert swd.last_error and swd.last_error.startswith("C4 unreachable")


def test_renderers_show_the_swd_section_and_tolerate_its_absence(tmp_path, monkeypatch):
    import json

    from dealintake.render import dossier, dossier_html, maps

    unit = {"label": "u1", "geometry": {"type": "Polygon", "coordinates": [[[0, 0], [0, 1], [1, 1], [1, 0], [0, 0]]]}}
    (tmp_path / "proposal.json").write_text(json.dumps({"deal_file": "deal.gpkg", "units": [unit]}), encoding="utf-8")
    nearest = {"uic": "000105174", "name": "PIT STOP SWD 1", "operator": "LAYNE SWD, LLC", "status": "active", "dist_mi": 1.0,
               "interval_ft": [4500, 6400], "standoff_ft": 2844, "near": True, "cum_mmbbl": 22.1, "counts": True,
               "pre_mmbbl": 10.0, "w24_mmbbl": 4.0, "since_mmbbl": 12.1, "trailing_12m_bpd": 11168, "latest_psi_max": 1667,
               "pressure_trend": "falling", "latest_month": "2025-11"}
    unit_swd = {"n_sticks": 2, "n_sticks_exposed": 2, "n_injectors": 1, "n_near": 1, "n_active": 1, "nearest": nearest,
                "biggest": nearest, "max_latest_psi": 1667, "radius_mi": 2.0, "vert_window_ft": 3000, "sticks": [], "injectors": [nearest]}
    group_swd = {"n": 2, "n_exposed": 1, "n_poor": 1, "n_suspect": 1, "perf_metric": "anduin oil EUR/1,000 ft",
                 "perf_median": 30000.0, "poor_cutoff": 15000.0, "exposed_median": 4359.0, "n_exposed_scored": 1,
                 "clear_median": 30000.0, "n_clear_scored": 1,
                 "wells": [{"api10": "4247538191", "well_name": "SHREDDER 33-59 2WA", "first_production_date": "2021-11-23",
                            "tvd_ft": 9244, "perf_per_1000ft": 4359.0, "poor": True, "exposed": True, "suspect": True,
                            "n_injectors": 1, "n_near": 1, "nearest": nearest, "biggest": nearest, "max_latest_psi": 1667,
                            "geom_source": "stick"},
                           {"api10": "4247538167", "well_name": "SHREDDER 33-59 1WA", "first_production_date": "2021-05-12",
                            "tvd_ft": 10784, "perf_per_1000ft": 30000.0, "poor": False, "exposed": False, "suspect": False,
                            "n_injectors": 0, "n_near": 0, "nearest": None, "biggest": None, "max_latest_psi": None,
                            "geom_source": "midpoint"}]}
    bench = {
        "tvd_ft": 9244.0, "spacing_ft": 880.0, "spacing_source": "default", "basin": "delaware",
        "units": {"u1": {"locations": [], "tvd_ft": 9244.0, "spacing_ft": 880.0, "gate2": {"source": "novi"}, "swd": unit_swd,
                         "gate3": {"n_locations": 2, "pdp_count_3mi_median": 12, "status": "pass", "tvd_excess_3mi_ft_max": 40},
                         "has_pdp_in_adjacent_bench": False, "standoff": None}},
        "edge_trigger": {"fired": False},
        "pool": {"n_eligible": 2, "n_excluded": 0, "exclusion_reasons": {}, "adjacent_planned": [],
                 "tier_order": ["codev"], "order_reason": "default", "flags": []},
        "short_history_transfer": {"cutoff_months": 9, "n_long": 2, "n_short": 0, "written": [], "skipped_locked": [],
                                   "skipped_no_peak": [], "long_fp_year_median": 2021.0, "short_fp_year_median": None,
                                   "long_proppant_lbs_ft_median": 2000.0, "short_proppant_lbs_ft_median": None, "donors": []},
        "split": {"recommendation": "single_tc", "metric": "anduin_oil_eur_per_1000ft", "groups": [], "median_ratio": 1.0,
                  "test": None, "p_value": None, "gradient_per_mile": 0.0, "gradient_r2": 0.0, "notes": []},
        "tc_groups": [{"name": "all units", "units": ["u1"], "note": None, "tier_counts": {"codev": 2},
                       "tier_medians_novi_eur_per_1000ft": {"codev": 30000.0}, "flags": [], "tc_wells": [],
                       "tc_preview_n_wells": 2, "tc_preview": {}, "novi": {}, "swd": group_swd,
                       "standoff": {"cohort": {"n": 2, "n_with_parent": 0, "median_abs_dtvd_ft": None, "min_abs_dtvd_ft": None,
                                               "max_abs_dtvd_ft": None}, "units": {"u1": None}}}],
    }
    sig = {"snapshot": {}, "config_version": 11, "planned_stack": ["BS2_C"], "planned_lateral_ft": 9000.0, "flags": [],
           "benches": {"BS2_C": bench}, "decision_log": [], "swd": {"available": True, "radius_mi": 2.0, "vert_window_ft": 3000}, "plan_source": "benches.yaml",
           "unit_plan": {"u1": {"benches": ["BS2_C"], "planned_lateral_ft": 9000.0, "seed_benches": ["BS2_C"], "edited": False}}}
    (tmp_path / "signals.json").write_text(json.dumps(sig), encoding="utf-8")
    monkeypatch.setattr(maps, "bench_map", lambda *a, **k: None)
    md = dossier.render(tmp_path).read_text(encoding="utf-8")
    page = dossier_html.render(tmp_path).read_text(encoding="utf-8")
    for text in (md, page):
        assert "PIT STOP SWD 1" in text and "SHREDDER 33-59 2WA" in text and "2,844" in text and "22.1" in text
        assert "None" not in text

    # older signals.json without the section, and a run where C4 was unavailable
    sig["benches"]["BS2_C"]["units"]["u1"].pop("swd")
    sig["benches"]["BS2_C"]["tc_groups"][0].pop("swd")
    sig["swd"] = {"available": False, "reason": "SWD_DSN not set"}
    (tmp_path / "signals.json").write_text(json.dumps(sig), encoding="utf-8")
    page = dossier_html.render(tmp_path).read_text(encoding="utf-8")
    md = dossier.render(tmp_path).read_text(encoding="utf-8")
    assert "SWD context unavailable" in page and "SWD_DSN not set" in page and "None" not in page
    assert "SWD context unavailable" in md
    sig.pop("swd")
    (tmp_path / "signals.json").write_text(json.dumps(sig), encoding="utf-8")
    assert "None" not in dossier_html.render(tmp_path).read_text(encoding="utf-8")
