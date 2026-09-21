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
