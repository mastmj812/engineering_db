"""The prospective cohort definition is frozen (D59 condition 1 / D70): any edit after 2026-10-15 fails here."""

from box import prospective as ps


def test_definition_matches_the_pinned_digest():
    assert ps.digest() == ps.DIGEST, "box/prospective.py DEFINITION changed after the freeze — that is tuning after the fact"


def test_definition_is_the_next_fold_and_the_delivered_method():
    d = ps.DEFINITION
    assert d["cutoff"] == "2025-12-01" and d["cohort"]["first_production_from"] == "2026-01-01"
    assert d["method"]["spec"] == "box_v2_wf" and d["method"]["haircut_source_run_id"] == 4
    assert d["verdict"] == {"bias_tol": 0.10, "band_tol": 0.05, "scale_free": True, "min_packages": 30, "streams": ["oil", "gas"],
                            "horizons_judged": [12, 24, 36], "horizons_reported": [6]}
