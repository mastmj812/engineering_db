"""Pure-function tests for scripts/swd_exposure.py (no database)."""

from datetime import date
from pathlib import Path

import pytest

from scripts.swd_exposure import _add_months, _c4_dsn, score, spearman


def test_add_months_rolls_years():
    assert _add_months(date(2024, 11, 1), 2) == date(2025, 1, 1)
    assert _add_months(date(2024, 1, 1), 24) == date(2026, 1, 1)
    assert _add_months(date(2024, 3, 15), 0) == date(2024, 3, 1)


def test_c4_dsn_reads_database_url(tmp_path: Path):
    env = tmp_path / ".env"
    env.write_text("# comment\nPOSTGRES_PORT=5434\nDATABASE_URL=postgresql://u:p@localhost:5434/db\n")
    assert _c4_dsn(env) == "postgresql://u:p@localhost:5434/db"
    (tmp_path / "empty.env").write_text("POSTGRES_PORT=5434\n")
    with pytest.raises(SystemExit):
        _c4_dsn(tmp_path / "empty.env")


def test_spearman_needs_five_points_and_drops_nulls():
    res, n = spearman([1, 2, 3, None], [1, 2, 3, 4])
    assert res is None and n == 3
    res, n = spearman([1, 2, 3, 4, 5], [2, 4, 6, 8, 10])
    assert n == 5 and res is not None and res[0] == pytest.approx(1.0)


def _producer(**over):
    base = dict(
        api10="4230100000", well_name="W", operator="O", county="Loving", tvd_ft=9700,
        lateral_length_ft=10000, first_production_date=date(2023, 1, 15),
        lateral_closer_xy_ft=None, center_mi=1.0,
    )
    base.update(over)
    return base


def _permit(pid, top, bottom):
    return dict(id=pid, uic_number=f"UIC{pid}", lease_name="L", well_no_display=str(pid),
                operator="INJ", depth_class="straddles", injection_top_ft=top,
                injection_bottom_ft=bottom, permit_status="active",
                rrc_commercial_disposal_flag=False)


def test_score_windows_and_near_classification():
    """standoff = landing - interval bottom; 'near' = interval meets landing ± window;
    volumes split at first production and at +24 months."""
    prod = [_producer()]
    permits = [_permit(1, 4000, 7800), _permit(2, 4000, 5000)]  # 1,900 ft above; 4,700 ft above
    h10 = {
        1: [
            {"reporting_month": date(2022, 6, 1), "volume_injected_bbl": 100, "injection_pressure_avg_psi": 900},
            {"reporting_month": date(2023, 6, 1), "volume_injected_bbl": 200, "injection_pressure_avg_psi": 1100},
            {"reporting_month": date(2025, 6, 1), "volume_injected_bbl": 400, "injection_pressure_avg_psi": None},
        ],
        2: [{"reporting_month": date(2023, 6, 1), "volume_injected_bbl": 1000, "injection_pressure_avg_psi": 500}],
    }
    dists = {("4230100000", 1): 1609.34, ("4230100000", 2): 3218.68}  # 1 mi, 2 mi
    rows, pairs = score(prod, permits, h10, dists, vert_window_ft=2000)
    r = rows[0]
    assert r["n_inj_all"] == 2 and r["n_inj_near"] == 1 and r["n_inj_above"] == 2
    assert r["near_bbl_pre"] == 100 and r["near_bbl_w24"] == 200 and r["near_bbl_total"] == 600
    assert r["nearest_near_standoff_ft"] == 9700 - 7800
    assert r["nearest_near_psi"] == 1100  # only the in-window month with a reading
    assert r["near_wt_w24"] == pytest.approx(200 / 1.0)
    assert r["all_bbl_w24"] == 1200
    by_pid = {p["uic_number"]: p for p in pairs}
    assert by_pid["UIC2"]["near"] is False and by_pid["UIC2"]["standoff_ft"] == 4700
