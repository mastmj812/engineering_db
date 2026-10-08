"""dealintake.pipeline pure helpers: Novi multi-segment summary, edge trigger."""

import pytest

pytest.importorskip("shapely")
pytest.importorskip("yaml")

from dealintake.config import load
from dealintake.pipeline import _edge_fired, _novi_summary

CFG = load()


def _p(stick, stream, seg, d, b=1.2, q=1000.0, ll=10_000.0, oil=400_000.0, gas=2_000_000.0):
    return {"stick_id": stick, "stream": stream, "segment": seg, "d_nom": d, "b": b, "q_start": q,
                "day_start": 0 if seg == 1 else 540, "day_stop": 540 if seg == 1 else 6000,
                "ll_ft": ll, "oil_eur": oil, "gas_eur": gas}


def test_novi_summary_reports_cap_share_and_segment2():
    params = [
        _p(1, "oil", 1, 3.65), _p(1, "oil", 2, 0.60),
        _p(2, "oil", 1, 3.65), _p(2, "oil", 2, 0.55),
        _p(3, "oil", 1, 2.10), _p(3, "oil", 2, 0.50),
    ]
    s = _novi_summary(params)["oil"]
    assert s["n"] == 3
    assert s["seg1_at_cap_frac"] == pytest.approx(2 / 3)
    assert s["seg2_di_nominal"] == pytest.approx(0.55)
    assert s["eur_per_1000ft"] == pytest.approx(40_000.0)   # 400k bbl / 10k ft x 1,000
    assert s["qi_per_1000ft"] == pytest.approx(100.0)
    assert 0.0 < s["di_effective"] < 1.0


def test_novi_summary_skips_streams_without_segment1():
    assert _novi_summary([_p(1, "gas", 2, 0.5)]) == {}


def test_edge_trigger():
    far = [{"dist_nearest_ft": 20_000, "pdp_count_1mi": 0, "pdp_count_5mi": 3}]
    near = [{"dist_nearest_ft": 800, "pdp_count_1mi": 4, "pdp_count_5mi": 40}]
    assert _edge_fired(far, CFG)[0] is True
    fired, sig = _edge_fired(near, CFG)
    assert fired is False and sig["ring_decay"] == pytest.approx(0.1)


def test_tc_groups_cli_parsing():
    from dealintake.cli import _tc_groups

    assert _tc_groups(["WCA_2=toucan_1"]) == {"WCA_2": [["toucan_1"]]}
    assert _tc_groups(["WCA_1=a,b;c"]) == {"WCA_1": [["a", "b"], ["c"]]}
    with pytest.raises(SystemExit):
        _tc_groups(["WCA_2"])


def test_radius_cli_parsing():
    from dealintake.cli import _radius

    assert _radius(["BS2_S=10", "WCA_1=7.5"]) == {"BS2_S": 10.0, "WCA_1": 7.5}
    for bad in ("BS2_S", "BS2_S=ten", "BS2_S=0"):
        with pytest.raises(SystemExit):
            _radius([bad])


def _walk(edge, override=None, per_radius=None):
    """_select_pool over a fake warehouse: eligible-pool size per radius."""
    from dealintake.pipeline import _select_pool

    per_radius = per_radius or {5.0: 2, 7.5: 6, 10.0: 21}
    fetched: list[float] = []

    def fetch(r):
        fetched.append(r)
        return [{"api10": i} for i in range(per_radius[r])]

    radius, eligible, _, _ = _select_pool(fetch, lambda c: (c, [], []), min_wells=10, edge=edge,
                                          radius_override=override)
    return radius, len(eligible), fetched


def test_pool_radius_steps_until_min_wells():
    assert _walk(edge=False) == (10.0, 21, [5.0, 7.5, 10.0])


def test_pool_edge_trigger_blocks_extension():
    assert _walk(edge=True) == (5.0, 2, [5.0])


def test_pool_radius_override_bypasses_edge_block_and_steps():
    # the Toucan BS2_S case: emerging bench trips the edge proxy; reviewer sets 10 mi
    assert _walk(edge=True, override=10.0) == (10.0, 21, [10.0])
    # exact radius even when a smaller step would already satisfy min_wells
    assert _walk(edge=False, override=10.0, per_radius={5.0: 15, 10.0: 40}) == (10.0, 40, [10.0])


def test_dossier_shows_gas_arps_and_ratio_side_by_side():
    from dealintake.render.dossier import _stream_rows

    G = {
        "tc_preview_n_wells": 20,
        "tc_preview": {"gas": {"qi": 500.0, "Di": 1.2, "b": 1.0, "eur_per_unit": 400_000.0}},
        "tc_preview_gas_ratio": {"mode": "ratio", "sub_mode": "exp_cum", "r2": 0.71,
                                 "eur_per_unit": 600_000.0, "implied_effective_decline_yr1": 0.52},
    }
    rows = [r for r in _stream_rows(G) if r[0] == "gas"]
    assert [r[1].split(" (")[0] for r in rows] == ["anduin TC preview", "anduin TC — ratio to cum oil"]
    assert "1.50x Arps EUR" in rows[1][1] and "R² 0.71" in rows[1][1]
    assert rows[1][4] == "52.0%" and rows[1][6] == 600_000.0


def test_p_value_and_num_formatting():
    from dealintake.render.tables import num, p_value

    assert p_value(0.002373333787193668) == "0.00237"
    assert p_value(3e-7) == "<0.0001" and p_value(0.41) == "0.41" and p_value(None) == "—"
    assert num(None) == "—" and num(1.6234) == "1.62" and num(-926.63, "+,.0f") == "-927"


def test_rendered_dossier_has_no_none_or_raw_floats(tmp_path, monkeypatch):
    """Re-render a minimal signals.json: a bench with no short wells and an
    escalated split must not print 'None' or an unrounded p-value."""
    import json

    from dealintake.render import dossier, maps

    unit = {"label": "u1", "geometry": {"type": "Polygon", "coordinates": [[[0, 0], [0, 1], [1, 1], [1, 0], [0, 0]]]}}
    (tmp_path / "proposal.json").write_text(json.dumps({"deal_file": "deal.gpkg", "units": [unit]}), encoding="utf-8")
    bench = {
        "tvd_ft": 9584.0, "spacing_ft": 880.0, "spacing_source": "default", "basin": "delaware",
        "units": {}, "edge_trigger": {"fired": False}, "tc_groups": [],
        "pool": {"n_eligible": 10, "n_excluded": 0, "exclusion_reasons": {}, "adjacent_planned": [],
                 "tier_order": ["codev"], "order_reason": "default", "flags": []},
        "short_history_transfer": {
            "cutoff_months": 9, "n_long": 10, "n_short": 0, "written": [], "skipped_locked": [],
            "skipped_no_peak": [], "long_fp_year_median": 2022.7, "short_fp_year_median": None,
            "long_proppant_lbs_ft_median": 2542.4, "short_proppant_lbs_ft_median": None,
            "donors": [{"stream": "oil", "donor_count": 10, "cohort_di": 3.04, "cohort_b": 1.0}]},
        "split": {"recommendation": "escalate", "metric": "anduin_oil_eur_per_1000ft", "groups": [],
                  "median_ratio": 1.62, "test": "kruskal_wallis", "p_value": 0.002373333787193668,
                  "gradient_per_mile": -926.6301958235966, "gradient_r2": 0.1375425664671187, "notes": []},
    }
    (tmp_path / "signals.json").write_text(json.dumps({
        "snapshot": {}, "config_version": 3, "planned_stack": ["BS2_S"], "planned_lateral_ft": 9998.0,
        "flags": [], "benches": {"BS2_S": bench}, "decision_log": []}), encoding="utf-8")
    monkeypatch.setattr(maps, "bench_map", lambda *a, **k: None)   # text check only, no matplotlib
    text = dossier.render(tmp_path).read_text(encoding="utf-8")
    assert "None" not in text and "0.00237" in text and "0.0023733" not in text
    assert "No short wells in the pool" in text and "-927" in text and "R² 0.14" in text

    # the HTML dossier renders the same signals with a rate-time overlay per TC group
    from dealintake.render import dossier_html

    sig = json.loads((tmp_path / "signals.json").read_text(encoding="utf-8"))
    sr = [40.0] + [80.0 / (1 + 1.0 * 2.8 * m / 12) for m in range(600)]
    sig["benches"]["BS2_S"]["tc_groups"] = [{
        "name": "all units", "units": ["u1"], "note": None, "tier_counts": {"codev": 10},
        "tier_medians_novi_eur_per_1000ft": {"codev": 60000.0}, "flags": [], "tc_wells": [],
        "tc_preview_n_wells": 10,
        "tc_preview": {"oil": {"qi": 80.0, "Di": 2.8, "b": 1.0, "eur_per_unit": 66146.0, "smoothed_rate": sr},
                       "gas": {"qi": 300.0, "Di": 2.4, "b": 1.01, "eur_per_unit": 219125.0, "smoothed_rate": [s * 4 for s in sr]}},
        "novi": {"oil": {"n": 63, "b": 0.94, "di_nominal": 4.62, "di_effective": 0.832, "seg1_at_cap_frac": 0.17,
                         "seg1_days": 540, "seg2_di_nominal": 0.59, "seg2_b": 1.1, "qi_per_1000ft": 190.0,
                         "eur_per_1000ft": 68908.0}},
        "qc": {"streams": {"oil": {"stream": "oil", "n": 10, "de_median": 0.75, "de_p25": 0.72, "de_p75": 0.78,
                                   "di_nominal_median": 3.0, "b_median": 1.0, "n_de_flagged": 0, "cohort_flag": None,
                                   "eur_per_1000ft_median": 63342.0, "flagged": True, "outliers_flagged": True}},
               "well_flags": [{"api10": "4230136694", "stream": "oil", "flag": "fit_at_bound",
                               "value": "Di at lower bound (0.5)", "threshold": "anduin bound check"}]},
    }]
    sig["unit_plan"] = {"u1": {"benches": ["BS2_S"], "planned_lateral_ft": 9998.0, "seed_benches": ["BS2_S"], "edited": False}}
    (tmp_path / "signals.json").write_text(json.dumps(sig), encoding="utf-8")
    page = dossier_html.render(tmp_path).read_text(encoding="utf-8")
    assert page.count("<svg") == 1 and "Novi median of 63 sticks" in page and "anduin TC (n=10)" in page
    assert "cumulative" in page and "Mbbl per 1,000 ft" in page and "MMcf per 1,000 ft" in page
    from dealintake.render.dossier_html import cum_curve

    assert cum_curve([10.0, 10.0])[-1] == pytest.approx(2 * 10.0 * 365.25 / 12)
    assert "None" not in page and "0.00237" in page and "4230136694" in page


class _FakeAnduin:
    def __init__(self, resp=None, err=None):
        self.resp, self.err, self.calls = resp, err, []

    def transfer_cohort(self, api10s, cutoff):
        self.calls.append((list(api10s), cutoff))
        if self.err:
            from dealintake.clients.anduin import AnduinError
            raise AnduinError(self.err)
        return self.resp


def _pool():
    from datetime import date
    old = [{"api10": f"L{i}", "first_production_date": date(2021, 6, 1), "proppant_lbs_per_ft": 2000.0} for i in range(6)]
    new = [{"api10": f"S{i}", "first_production_date": date(2025, 3, 1), "proppant_lbs_per_ft": 2800.0} for i in range(2)]
    return old + new


def test_transfer_summary_uses_whole_pool_and_flags_vintage_gap():
    from dealintake.pipeline import _transfer

    fake = _FakeAnduin(resp={
        "written_api10s": ["S0", "S1"], "skipped_locked": [], "skipped_no_peak": [],
        "long_api10s": [f"L{i}" for i in range(6)], "short_api10s": ["S0", "S1"],
        "donors": [{"stream": "oil", "donor_count": 6, "cohort_di": 2.8, "cohort_b": 1.0}],
    })
    out = _transfer(fake, _pool(), 9)
    assert fake.calls == [([c["api10"] for c in _pool()], 9)]       # one batch = one donor pool
    assert (out["n_long"], out["n_short"], out["written"]) == (6, 2, ["S0", "S1"])
    assert out["long_proppant_lbs_ft_median"] == 2000.0 and out["short_proppant_lbs_ft_median"] == 2800.0
    assert "yr gap" in out["flag"]                                   # 2021.4 vs 2025.2 >= 3 yr


def test_transfer_thin_donors_is_recorded_not_fatal():
    from dealintake.pipeline import _transfer

    out = _transfer(_FakeAnduin(err="POST ... -> 422: insufficient_donor_cohort"), _pool(), 9)
    assert "NOT applied" in out["flag"] and "422" in out["error"]


def test_short_history_transfer_on_by_default():
    import argparse

    from dealintake.cli import _transfer_cutoff

    ns = lambda n=None, off=False: argparse.Namespace(short_history_transfer=n, no_short_history_transfer=off)
    assert _transfer_cutoff(ns(), CFG) == CFG["type_curve"]["short_history_transfer_months"] == 9
    assert _transfer_cutoff(ns(12), CFG) == 12
    assert _transfer_cutoff(ns(12, off=True), CFG) is None


class _CompareAnduin:
    """Records the with/without sequence: refit -> compute -> transfer re-run."""

    def __init__(self, donors_after):
        self.log = []
        self.donors_after = donors_after

    def forecast(self, api10s, only_missing=True):
        self.log.append(("forecast", sorted(api10s), only_missing))
        return {}

    def compute_type_curve(self, api10s, **kw):
        self.log.append(("compute", sorted(api10s)))
        return {"streams": {"oil": {"fitted": {"qi": 100.0, "Di": 2.5, "b": 1.0, "eur_per_unit": 50_000.0}}}}

    def transfer_cohort(self, api10s, cutoff):
        self.log.append(("transfer", len(api10s), cutoff))
        return {"long_api10s": [], "short_api10s": ["S0", "S1"], "written_api10s": ["S0", "S1"],
                "donors": self.donors_after}


_DONORS = [{"stream": "oil", "donor_count": 6, "cohort_di": 2.6, "cohort_b": 1.0}]


def _bench():
    return {
        "short_history_transfer": {"written": ["S0", "S1"], "donors": _DONORS},
        "tc_groups": [
            {"name": "g1", "tc_wells": [{"api10": "L0"}, {"api10": "S0"}]},
            {"name": "g2", "tc_wells": [{"api10": "L1"}, {"api10": "L2"}]},   # no transferred wells
        ],
    }


def test_with_without_refits_only_cohort_shorts_and_restores_transfer():
    from dealintake.pipeline import _compare_without_transfer

    B, fake = _bench(), _CompareAnduin(_DONORS)
    out = _compare_without_transfer(fake, B, _pool(), 9)
    assert fake.log[0] == ("forecast", ["S0"], False)          # S1 not in any cohort: untouched
    assert fake.log[1] == ("compute", ["L0", "S0"])            # only the affected group
    assert fake.log[-1] == ("transfer", len(_pool()), 9)       # restored on the whole pool
    assert "tc_preview_no_transfer" in B["tc_groups"][0] and "tc_preview_no_transfer" not in B["tc_groups"][1]
    assert out["restored"] and "flag" not in out


def test_with_without_flags_when_donor_medians_change():
    from dealintake.pipeline import _compare_without_transfer

    changed = [{"stream": "oil", "donor_count": 6, "cohort_di": 2.9, "cohort_b": 1.0}]
    out = _compare_without_transfer(_CompareAnduin(changed), _bench(), _pool(), 9)
    assert "did not reproduce" in out["flag"]


def test_transfer_rows_show_eur_delta():
    from dealintake.render.dossier import _transfer_rows

    G = {"tc_preview": {"oil": {"qi": 100.0, "Di": 2.5, "b": 1.0, "eur_per_unit": 55_000.0}},
         "tc_preview_no_transfer": {"oil": {"qi": 100.0, "Di": 2.2, "b": 1.0, "eur_per_unit": 50_000.0}}}
    rows = _transfer_rows(G)
    assert [r[1] for r in rows] == ["with transfer (default)", "own fits (without)"]
    assert rows[0][7] == "+10.0%" and rows[1][7] == "—"


def test_reviewer_group_spanning_the_class_takes_the_whole_pool():
    from dealintake.pipeline import group_pool

    pool = [{"api10": "a", "unit": None}, {"api10": "b", "unit": None}]     # one-unit class: split test never tagged
    assert group_pool(pool, ["u1"], whole=True) == pool
    assert group_pool(pool, ["u1"], whole=False) == []                    # the old behaviour: empty cohort
    tagged = [{"api10": "a", "unit": "u1"}, {"api10": "b", "unit": "u2"}]
    assert [c["api10"] for c in group_pool(tagged, ["u2"], whole=False)] == ["b"]


def test_pool_lateral_band_spans_the_units():
    from dealintake.pipeline import pool_lateral_band

    cfg = load()
    lo, hi = pool_lateral_band([9900.0, 12576.0, 17670.0], cfg, "delaware")
    assert lo == pytest.approx(9900.0 * 0.75)            # shortest unit, basin band
    assert hi == pytest.approx(17670.0 * 1.40)           # longest unit, long-lateral tolerance
    lo, hi = pool_lateral_band([9900.0], cfg, "delaware")
    assert (lo, hi) == (pytest.approx(7425.0), pytest.approx(12375.0))   # one unit = the old band


def test_length_check_flags_only_judged_buckets():
    from dealintake.pipeline import length_check

    cfg = load()
    pool = ([{"lateral_length_ft": 10000.0, "m": 60000.0}] * 8
            + [{"lateral_length_ft": 15000.0, "m": 45000.0}] * 5       # -25% on 5 wells -> flagged
            + [{"lateral_length_ft": 12000.0, "m": 90000.0}] * 2)      # +50% but 2 wells -> shown, not judged
    lc = length_check(pool, "m", cfg)
    by = {b["bucket"]: b for b in lc["buckets"]}
    assert lc["pool_median_per_1000ft"] == 60000.0
    assert by[">= 13,500 ft"]["flagged"] and by[">= 13,500 ft"]["vs_pool"] == pytest.approx(0.75)
    assert not by["11,000-13,500 ft"]["judged"] and not by["11,000-13,500 ft"]["flagged"]
    assert not by["8,500-11,000 ft"]["flagged"]
    assert len(lc["flags"]) == 1 and "-25%" in lc["flags"][0]
    assert length_check([], "m", cfg)["buckets"] == []


def test_lateral_support_flags_extrapolation_and_thin():
    from dealintake.pipeline import lateral_support

    cfg = load()
    cohort = [{"lateral_length_ft": v} for v in (9800.0, 10000.0, 10100.0, 10300.0, 12400.0)]
    rows, flags = lateral_support(cohort, {"two": 9900.0, "two_half": 12576.0, "three_half": 17670.0}, cfg, "delaware")
    by = {r["unit"]: r for r in rows}
    assert by["two"]["n_within_band"] == 4 and not by["two"]["extrapolated"] and not by["two"]["thin"]
    assert by["two_half"]["extrapolated"]                       # 12,576 > the cohort's longest 12,400
    assert by["three_half"]["extrapolated"] and by["three_half"]["n_within_band"] == 1   # 12,400 in 17,670 -40%
    assert sum("OUTSIDE" in f for f in flags) == 2
    gappy = [{"lateral_length_ft": v} for v in (7000.0, 7100.0, 7200.0, 12400.0, 12500.0)]
    rows, flags = lateral_support(gappy, {"u": 11000.0}, cfg, "delaware")      # inside the range, 2 wells in band
    assert rows[0]["thin"] and not rows[0]["extrapolated"] and "only 2 cohort well(s)" in flags[0]
    assert lateral_support([], {"u": 9900.0}, cfg, "delaware")[1] == []


def test_classify_takes_an_explicit_lateral_band():
    from datetime import date

    from dealintake.select_wells import exclusion_reasons

    cfg = load()
    c = {"first_production_date": date(2022, 1, 1), "lateral_length_ft": 15000.0, "months_produced": 24,
         "lateral_closer_xy_ft": 1000.0, "codev_scorable": True}
    kw = {"planned_lateral_ft": 9900.0, "lateral_tol": 0.25, "planned_spacing_ft": 1320.0}
    assert any(r.startswith("lateral_outside") for r in exclusion_reasons(c, cfg, **kw))
    assert exclusion_reasons(c, cfg, lateral_band_ft=(7425.0, 24738.0), **kw) == []


def test_scenario_groups_split_infill_from_greenfield():
    from dealintake.pipeline import scenario_groups

    ex = {"a": {"above": ["WCA_1"], "below": []}, "b": {"above": [], "below": []},
          "c": {"above": [], "below": ["WCC"]}}
    out = scenario_groups(["a", "b", "c"], ex)
    assert [(g["scenario"], g["units"], g["existing"], g["flip"]) for g in out] == [
        ("infill", ["a", "c"], ["WCA_1", "WCC"], True), ("greenfield", ["b"], [], False)]
    assert [g["scenario"] for g in scenario_groups(["b"], ex)] == ["greenfield"]      # one scenario: group stays whole
    assert [g["scenario"] for g in scenario_groups(["a"], ex)] == ["infill"]
    assert scenario_groups(["z"], {})[0]["scenario"] == "greenfield"                  # unknown unit = no producers


def test_greenfield_cohort_never_tiers_topfill():
    from dealintake.select_wells import codev_tier

    c = {"parent_benches_above": ["WCA_1"], "bench_context": {}, "codev_benches": ["WCB_1"]}
    assert codev_tier(c, ["WCB_1"], ["WCA_1"]) == "topfill_underfill"     # infill unit under WCA_1
    assert codev_tier(c, ["WCB_1"], []) == "codev"                        # greenfield unit: same well, pad-mate tier


def test_tier_blind_fill_takes_the_nearest_whatever_the_tier():
    from dealintake.select_wells import fill

    cfg = load()
    pool = [{"api10": f"w{i:02d}", "tier": "topfill_underfill" if i % 5 == 0 else "codev", "dist_ft": 100.0 * i}
            for i in range(30)]
    sel = fill(pool, cfg, bench="BS3_C", adjacent=["BS3_S"], order=["codev", "stack_standalone", "topfill_underfill"],
               order_reason="x", tier_blind=True)
    assert [c["api10"] for c in sel.selected] == [f"w{i:02d}" for i in range(20)]       # nearest 20, tiers mixed
    assert sel.tier_counts() == {"codev": 16, "stack_standalone": 0, "topfill_underfill": 4}
    assert sel.flags == ["cohort capped: 20 nearest of 30 pool wells"]
    assert "under_count" in fill(pool[:3], cfg, bench="BS3_C", adjacent=[], order=["codev"], order_reason="x",
                                 tier_blind=True).flags[0]


def test_planned_standoff_uses_the_parent_gate_and_skips_same_bench():
    from shapely.geometry import LineString, box

    from dealintake.pipeline import PARENT_GATE_FT, planned_standoff

    unit = box(-103.30, 31.60, -103.28, 31.63)                       # N-S laterals: +offset = east
    stick = LineString([(-103.29, 31.602), (-103.29, 31.628)])       # on the unit centre line, offset ~0
    existing = [
        {"inside": True, "bench": "BS3_S", "tvd_ft": 11500.0, "offset_ft": 200.0},      # in gate, 400 ft below
        {"inside": True, "bench": "WCA_1", "tvd_ft": 11300.0, "offset_ft": 1500.0},     # nearer vertically, outside the gate
        {"inside": True, "bench": "BS3_C", "tvd_ft": 11150.0, "offset_ft": 100.0},      # same bench: a neighbour
        {"inside": False, "bench": "BS3_S", "tvd_ft": 11200.0, "offset_ft": 0.0},       # not in the unit
    ]
    s = planned_standoff(unit, 0.0, [{"id": "gen-0", "wkt": stick.wkt, "tvd": 11100.0}], existing, "BS3_C", 11100.0,
                         float(PARENT_GATE_FT), 1000.0)
    assert PARENT_GATE_FT == 660
    assert (s["n_sticks"], s["n_with_parent"], s["nearest_bench"], s["nearest_dtvd_ft"]) == (1, 1, "BS3_S", 400)
    none = planned_standoff(unit, 0.0, [{"id": "gen-0", "wkt": stick.wkt, "tvd": 11100.0}], existing[1:], "BS3_C",
                            11100.0, 660.0, 1000.0)
    assert none["n_with_parent"] == 0 and none["nearest_bench"] is None


def test_standoff_flags_only_when_we_are_more_parented_than_the_cohort():
    from dealintake.pipeline import cohort_standoff, standoff_flags

    cohort = [{"parent_benches_below": ["BS3_S"], "bench_context": {"BS3_S": {"parent_nearest_dtvd_ft": 400}}},
              {"parent_benches_below": [], "bench_context": {}}]
    c = cohort_standoff(cohort)
    assert (c["n"], c["n_with_parent"], c["median_abs_dtvd_ft"]) == (2, 1, 400)
    u = {"n_sticks": 4, "n_with_parent": 1, "nearest_dtvd_ft": 450, "nearest_bench": "BS3_S", "gate_ft": 660.0}
    assert standoff_flags({"a": u}, c) == []                                   # 25% parented at 450 ft vs 50% at 400
    tight = {**u, "nearest_dtvd_ft": 250}
    one = standoff_flags({"a": tight, "b": tight, "c": u}, c)
    assert len(one) == 1 and "2 unit(s)" in one[0] and "nearest BS3_S 250 ft below" in one[0]   # one flag per group
    assert len(standoff_flags({"a": u}, cohort_standoff(cohort[1:]))) == 1     # cohort has no parented well
    assert standoff_flags({"a": {**u, "n_with_parent": 0, "nearest_dtvd_ft": None}}, c) == []
    tag = {**u, "n_with_parent": 0, "nearest_dtvd_ft": None, "n_same_landing": 1, "same_landing_benches": ["WCA_2"]}
    assert standoff_flags({"a": tag}, c)[0].startswith("same landing, different tag: a (1 stick(s) at the depth of WCA_2)")


def test_same_landing_producer_is_a_neighbour_not_a_parent():
    from shapely.geometry import LineString, box

    from dealintake.pipeline import planned_standoff

    unit = box(-103.30, 31.60, -103.28, 31.63)
    stick = LineString([(-103.29, 31.602), (-103.29, 31.628)])
    existing = [{"inside": True, "bench": "WCA_2", "tvd_ft": 11111.0, "offset_ft": 50.0},     # 11 ft: same landing
                {"inside": True, "bench": "WCB_1", "tvd_ft": 11500.0, "offset_ft": 50.0}]
    s = planned_standoff(unit, 0.0, [{"id": "g", "wkt": stick.wkt, "tvd": 11100.0}], existing, "WCA_1", 11100.0,
                         660.0, 1000.0, 150.0)
    assert (s["n_with_parent"], s["nearest_bench"], s["nearest_dtvd_ft"]) == (1, "WCB_1", 400)
    assert (s["n_same_landing"], s["same_landing_benches"]) == (1, ["WCA_2"])


def test_curve_labels_and_cohort_rows():
    from dealintake.render.maps import curve_labels
    from dealintake.render.tables import COHORT_HEADERS, cohort_rows

    assert curve_labels("BS3_C", {"tc_groups": [{"units": ["a"]}]}) == ["BS3_C"]

    def sq(label: str, x: float, y: float, name: str) -> dict:
        ring = [[x, y], [x + 0.01, y], [x + 0.01, y + 0.01], [x, y + 0.01], [x, y]]
        return {"label": label, "dsu_name": name, "geometry": {"type": "Polygon", "coordinates": [ring]}}

    two = {"tc_groups": [{"units": ["a"]}, {"units": ["b"]}]}
    # no letters, no spaces (Michael 2026-10-08); 2 groups -> 4-point rose
    assert curve_labels("BS3_C", two, [sq("a", -103.5, 31.9, "1-12"), sq("b", -103.5, 31.6, "4-5")]) \
        == ["BS3_C_North", "BS3_C_South"]
    assert curve_labels("BS3_C", two) == ["BS3_C_a", "BS3_C_b"]            # no geometry -> DSU fallback
    assert curve_labels("WCB_2 @ 10,000 ft", {"tc_groups": [{"units": ["a"]}]}) == ["WCB_2_10000ft"]
    # Rally Caps WCB_2 shape: N / NE / NW / SW / SE need the 8-point rose
    five = {"tc_groups": [{"units": [u]} for u in "abcde"]}
    units = [sq("a", -103.55, 32.1, "1-12"), sq("b", -103.25, 32.05, "35-26"), sq("c", -103.75, 32.05, "2-47"),
             sq("d", -103.75, 31.7, "13-18"), sq("e", -103.35, 31.7, "4-5")]
    assert curve_labels("WCB_2", five, units) == [
        "WCB_2_North", "WCB_2_Northeast", "WCB_2_Northwest", "WCB_2_Southwest", "WCB_2_Southeast"]
    # interleaved groups that share a direction on both roses fall back to the DSU name
    units3 = [sq("a", -103.5, 32.0, "1-12"), sq("b", -103.5, 32.1, "2-47"), sq("c", -103.5, 31.5, "4-5")]
    assert curve_labels("WCB_2", {"tc_groups": [{"units": [u]} for u in "abc"]}, units3) == [
        "WCB_2_1-12", "WCB_2_2-47", "WCB_2_South"]
    wells = [
        {"api10": "2", "well_name": "FAR 2H", "operator": "Op", "first_production_date": "2024-07-01", "lateral_length_ft": 10000.0,
         "unit": "u1", "unit_dist_ft": 10560.0, "dist_ft": 5.0, "anduin_oil_eur_per_1000ft": 50000.0, "bench": "BS3_C",
         "tier": "codev", "codev_benches": ["BS3_C", "WCA_1"]},
        {"api10": "1", "well_name": "NEAR 1H", "operator": "Op", "first_production_date": "2025-12-01", "lateral_length_ft": 9968.0,
         "unit": None, "dist_ft": 528.0, "anduin_oil_eur_per_1000ft": 30000.0, "bench": "BS3_C",
         "tier": "topfill_underfill", "parent_benches_below": ["BS3_S"]},
    ]
    rows = cohort_rows(wells, {"u1": "32-33"})
    assert len(rows[0]) == len(COHORT_HEADERS)
    assert [r[0] for r in rows] == ["NEAR 1H", "FAR 2H"]                       # nearest first
    assert rows[0][6] == "0.1" and rows[0][8] == "over/under BS3_S" and rows[0][3] == "2025-12"
    assert rows[1][5] == "32-33" and rows[1][6] == "2.0" and rows[1][8] == "co-developed with WCA_1"


def test_reviewer_cohort_size_replaces_the_cap():
    from dealintake.cli import _cohort
    from dealintake.select_wells import fill

    cfg = load()
    pool = [{"api10": f"w{i:02d}", "tier": "codev", "dist_ft": 100.0 * i} for i in range(30)]
    kw = {"bench": "BS3_C", "adjacent": [], "order": ["codev"], "order_reason": "x", "tier_blind": True}
    whole = fill(pool, cfg, cohort_size=0, **kw)
    assert len(whole.selected) == 30 and whole.flags == ["cohort = the whole pool of 30 wells (REVIEWER cohort size)"]
    some = fill(pool, cfg, cohort_size=25, **kw)
    assert [c["api10"] for c in some.selected] == [f"w{i:02d}" for i in range(25)]
    assert some.flags == ["cohort capped: 25 nearest of 30 pool wells (REVIEWER cohort size)"]
    assert len(fill(pool, cfg, **kw).selected) == 20                                   # default unchanged
    assert _cohort(["BS3_C=pool", "WCB_1=40"]) == {"BS3_C": 0, "WCB_1": 40}
    for bad in ("BS3_C=0", "BS3_C=-3", "BS3_C=lots"):
        with pytest.raises(SystemExit):
            _cohort([bad])
