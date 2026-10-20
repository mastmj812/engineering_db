"""sql/64 mirror (etl/novi/surveys.lateral_summary) + the DirectionalSurveys load contract."""

from __future__ import annotations

import pandas as pd

from etl.novi import load as novi_load
from etl.novi.surveys import lateral_summary
from scripts import generate_novi_ddl


def _well(api: str, rows: list[tuple[int, int, int, int]], kb: int = 3000, interp: set[int] = frozenset()) -> list[dict]:
    """rows = (path, md, tvd, location_type)."""
    return [
        {"API10": api, "Path": p, "MD": md, "TVD": tvd, "SubSeaTVD": tvd - kb, "LocationType": lt,
         "Interpolated": "t" if p in interp else "f"}
        for p, md, tvd, lt in rows
    ]


def _frame() -> pd.DataFrame:
    # A: perfs present -> span = perf top (9500) .. perf bottom (11500); toe-down well
    a = _well("A", [(1, 0, 0, 1), (2, 8000, 7990, 3), (3, 9300, 9200, 4), (4, 9500, 9210, 5),
                    (5, 10000, 9220, 0), (6, 10500, 9230, 0), (7, 11000, 9240, 0), (8, 11500, 9250, 6),
                    (9, 12000, 9260, 2)], interp={6})
    # B: no perfs -> landing point .. bottom hole; toe-up
    b = _well("B", [(1, 0, 0, 1), (2, 9000, 8900, 4), (3, 9600, 8890, 0), (4, 10200, 8870, 2)], kb=2800)
    # C: perfs inverted (bottom <= top) -> falls back to lp_bhl
    c = _well("C", [(1, 0, 0, 1), (2, 9000, 9000, 4), (3, 9500, 9010, 6), (4, 9800, 9015, 5), (5, 10000, 9020, 2)])
    # D: no landing point and no perfs -> no span
    dd = _well("D", [(1, 0, 0, 1), (2, 5000, 4990, 2)])
    return pd.DataFrame(a + b + c + dd)


def test_span_basis_and_endpoints():
    s = lateral_summary(_frame())
    assert s.loc["A", "lateral_basis"] == "perfs"
    assert (s.loc["A", "lat_start_md_ft"], s.loc["A", "lat_end_md_ft"]) == (9500, 11500)
    assert s.loc["B", "lateral_basis"] == "lp_bhl"
    assert s.loc["C", "lateral_basis"] == "lp_bhl"
    assert pd.isna(s.loc["D", "lateral_basis"])
    assert pd.isna(s.loc["D", "heel_tvd_ft"])


def test_heel_mid_toe_and_spread():
    s = lateral_summary(_frame())
    a = s.loc["A"]
    assert (a.heel_tvd_ft, a.mid_tvd_ft, a.toe_tvd_ft) == (9210, 9230, 9250)
    assert a.toe_minus_heel_tvd_ft == 40 and a.lat_tvd_range_ft == 40
    assert a.n_lat_stations == 5 and a.lat_tvd_p50_ft == 9230
    assert abs(a.lat_interp_share - 0.2) < 1e-9
    b = s.loc["B"]
    assert b.toe_minus_heel_tvd_ft == -30  # toe-up
    assert b.mid_tvd_ft == 8890            # MD 9600 is the span midpoint exactly


def test_kb_elevation():
    s = lateral_summary(_frame())
    assert s.loc["A", "kb_elev_ft"] == 3000 and s.loc["B", "kb_elev_ft"] == 2800


def test_mvp_tables_match_generator():
    # loader and DDL generator must agree, or sql/02 and the nightly drift apart
    assert set(novi_load.MVP_TABLES) == generate_novi_ddl.MVP_TABLES
    assert "DirectionalSurveys" in novi_load._INCREMENTAL_KEYS
    assert novi_load._SEQ_TRIM["DirectionalSurveys"] == ("API10", "Path")


def test_upsert_pass_records_snapshot_max_sequence(tmp_path):
    cols = ["API10", "Path", "MD", "ModifiedAt"]
    tsv = tmp_path / "DirectionalSurveys.tsv"
    lines = ["\t".join(cols), "A\t1\t0\t2026-01-01 00:00:00", "A\t2\t100\t2026-10-01 00:00:00",
             "B\t1\t0\t2026-01-01 00:00:00", "A\t3\t200\t2026-01-01 00:00:00"]
    tsv.write_text("\n".join(lines) + "\n", encoding="utf-8")

    class _Copy:
        def __init__(self):
            self.lines = []

        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

        def write(self, line):
            self.lines.append(line)

    class _Cur:
        def __init__(self):
            self.sql, self.cp = [], _Copy()

        def execute(self, q, *a):
            self.sql.append(q)

        def copy(self, q):
            return self.cp

    from datetime import datetime

    seq: dict[str, int] = {}
    cur = _Cur()
    n_new, n_skip = novi_load._upsert_newer(cur, "DirectionalSurveys", cols, ["API10", "Path"], tsv,
                                            datetime(2026, 6, 1), seq, ("API10", "Path"))  # noqa: DTZ001 (Novi ModifiedAt is naive)
    assert (n_new, n_skip) == (1, 0)
    assert seq == {"A": 3, "B": 1}
