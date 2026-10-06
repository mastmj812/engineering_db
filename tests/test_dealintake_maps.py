"""Dossier curve maps: one per tc_group, overview only for multi-curve benches,
well colour from anduin's own fit (never Novi)."""

from __future__ import annotations

from dealintake.pipeline import map_api10s
from dealintake.render import maps

_SQ = {"type": "Polygon", "coordinates": [[[-103.6, 31.6], [-103.59, 31.6], [-103.59, 31.62], [-103.6, 31.62], [-103.6, 31.6]]]}
_SQ2 = {"type": "Polygon", "coordinates": [[[-103.5, 31.6], [-103.49, 31.6], [-103.49, 31.62], [-103.5, 31.62], [-103.5, 31.6]]]}


def _well(api, lon, eur=None, **k):
    return {"api10": api, "lon": lon, "lat": 31.55, "anduin_oil_eur_per_1000ft": eur, "eur_per_1000ft": 99999.0, **k}


def _bench(n_groups):
    loc = {"id": "gen-0", "src": "narvi_preview", "ll_ft": 7500.0, "tvd": 9000.0,
           "wkt": "LINESTRING (-103.595 31.601, -103.595 31.619)"}
    groups = [{"name": f"g{i}", "units": [f"u{i}"],
               "tc_wells": [_well(f"420000000{i}", -103.6 + 0.1 * i, 55000.0), _well(f"430000000{i}", -103.58 + 0.1 * i)]}
              for i in range(n_groups)]
    return {"tc_groups": groups, "units": {f"u{i}": {"locations": [loc]} for i in range(n_groups)},
            "eligible_pool": [_well("4400000000", -103.55)]}


def test_single_curve_writes_curve_map_only(tmp_path):
    B = _bench(1)
    out = maps.bench_map(tmp_path / "map_X.png", "X", [{"label": "u0", "geometry": _SQ}], B,
                         sticks={"4200000000": "LINESTRING (-103.6 31.54, -103.6 31.56)"})
    assert out == [tmp_path / "map_X_curve_a.png"]
    assert out[0].stat().st_size > 0 and not (tmp_path / "map_X.png").exists()


def test_multi_curve_adds_overview(tmp_path):
    B = _bench(2)
    units = [{"label": "u0", "geometry": _SQ}, {"label": "u1", "geometry": _SQ2}]
    out = maps.bench_map(tmp_path / "map_X.png", "X", units, B)
    assert {p.name for p in out} == {"map_X_curve_a.png", "map_X_curve_b.png", "map_X.png"}


def test_colour_is_anduin_per_ft_never_novi():
    assert maps.eur_ft(_well("1", 0.0, 61642.7)) == 61.6427
    assert maps.eur_ft(_well("1", 0.0)) is None          # no anduin fit -> grey, not Novi's 99,999


def test_map_api10s_covers_pool_and_cohorts():
    assert map_api10s({"benches": {"X": _bench(2)}}) == [
        "4200000000", "4200000001", "4300000000", "4300000001", "4400000000"]
