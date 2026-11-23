"""Nightly BOX sticks reconciliation (etl/box_recon.py, sql/74): static checks that the module, the DDL, the apply script
and the refresh wiring agree, and that the hook is soft. DB-free; the SQL itself is checked against the Python reference
and in the rehearsal container (docs/box_sticks/phase5b-2026-11-19)."""
from __future__ import annotations

import re
from pathlib import Path

import pytest

from etl import box_recon as br
from etl import db, refresh

ROOT = Path(__file__).resolve().parent.parent
DDL = (ROOT / "sql" / "74_box_recon.sql").read_text(encoding="utf-8")
SRC = (ROOT / "etl" / "box_recon.py").read_text(encoding="utf-8")
WRITE_WORDS = ("INSERT ", "UPDATE ", "DELETE ", "TRUNCATE", "CREATE ", "DROP ", "ALTER ", "REFRESH ", "GRANT ")


def _columns(table: str) -> set[str]:
    body = DDL.split(f"CREATE TABLE IF NOT EXISTS {table} (", 1)[1].split("\n);", 1)[0]
    return {m.group(1) for m in re.finditer(r"^\s{4}([a-z_0-9]+)\s", body, flags=re.MULTILINE)} - {"CONSTRAINT", "PRIMARY"}


def test_the_rule_constants_are_the_decisions_of_record():
    assert (br.MATCH, br.CONFLICT) == (0.5, 0.3)                       # 0.3: Michael 2026-11-18, not sql/68's 0.2
    assert (br.CORRIDOR_M, br.SAME_CODE_FT, br.ANY_TAG_FT, br.MEMBER) == (46, 500, 150, 0.30)
    assert br.STEP_OUT_DEG == 15 and br.MIN_DEPTH_FT == 4000
    from box.sticks import core
    from box.tag_scoreboard import MIN_EVIDENCE_TVD_FT

    assert core.STEP_OUT_DEG == br.STEP_OUT_DEG and br.MIN_DEPTH_FT == MIN_EVIDENCE_TVD_FT   # the generator's and the tag rule's own values


def test_judge_and_stale_are_single_read_only_selects_with_the_constants_rendered():
    for sql in (br.JUDGE_SQL, br.STALE_SQL):
        assert "%(" not in sql and "%%" not in sql                                   # literal SQL: CREATE TABLE AS takes no bind parameter
        assert not any(w in sql.upper().replace("CREATE TEMP", "") for w in WRITE_WORDS), sql[:80]
        assert sql.lstrip().upper().startswith("WITH")
    j = br.JUDGE_SQL
    assert ">= 0.5" in j and ">= 0.3" in j and ">= 0.2" not in j
    assert j.count("'endcap=flat'") == 4                                             # match, same landing, gate, stacked: all flat-ended
    assert ", 46, 'endcap=flat'" in j and "<= 500" in j and "<= 150" in j and "804.672" in j
    assert "WHEN k.legs_matched > 0 THEN 'producing'" in j                           # only a producing well takes a stick out
    assert "cls = 'producing' AND ov >= 0.5" in j and "cls = 'pending' AND ov >= 0.5" in j and "cls = 'permit' AND ov >= 0.5" in j
    assert "p.cls = 'producing' AND p.ov_gate >= p.min_ov" in j                      # crowded: producing wells only, median form
    assert "0.5 * p.ov_gate" in j and "wca_class = 'co-developed'" in j
    assert "is_record" in j and "cfg #>" in j                                        # the record set's own envelope, no constant copied
    assert "= ANY (a.new_api10)" in br.STALE_SQL                                     # sticks_out = what the new producers took out
    assert "{src}" in br.STALE_SQL and "NOT EXISTS (SELECT 1 FROM box.location_set_well" in br.STALE_SQL
    assert "LEAST(st.sticks - st.sticks_out, GREATEST(st.sticks - a.new_producers, 0))" in br.STALE_SQL


def test_the_stick_join_keeps_the_set_filter_out_of_the_index_choice():
    # A plain `s.set_id = r.set_id` lets the planner AND the spatial probe with a bitmap of the whole record set once per
    # well (227 s against 51 s on 2026-11-23, rows identical). The filter must stay, but not as an indexable equality.
    j = br.JUDGE_SQL
    assert "ON s.set_id + 0 = r.set_id" in j and "ON s.set_id = r.set_id" not in j
    assert j.index("ON s.set_id + 0 = r.set_id") < j.index("extensions.ST_DWithin(s.legs_geom::extensions.geography, w.line::extensions.geography")


def test_the_module_never_writes_schema_box_and_writes_only_its_four_tables():
    targets = set(re.findall(r"(?:INSERT INTO|DELETE FROM|UPDATE|TRUNCATE)\s+([a-z_]+\.[a-z_0-9]+)", SRC))
    assert targets == set(br.TABLES)
    assert not re.search(r"(INSERT INTO|DELETE FROM|UPDATE|TRUNCATE|ALTER TABLE|DROP TABLE)\s+box\.", SRC)
    temps = set(re.findall(r"CREATE TEMP TABLE (\w+) ON COMMIT DROP", SRC))
    assert temps == {"_recon", "_stale", "_since", "_ssince"}


def test_sql74_creates_exactly_the_modules_tables_and_touches_nothing_else():
    created = set(re.findall(r"CREATE TABLE IF NOT EXISTS ([a-z_.0-9]+)", DDL))
    assert created == set(br.TABLES)
    body = "\n".join(ln for ln in DDL.splitlines() if not ln.lstrip().startswith("--"))
    assert "MATERIALIZED" not in body and "DROP " not in body and "ALTER " not in body and "TRUNCATE" not in body
    assert not re.search(r"\b(ON|TABLE|INTO|GRANT SELECT ON)\s+box\.", body)        # reads box in the writer only; no DDL or grant on it
    assert "TO analyst_ro" in body
    for t in br.TABLES:
        assert f"COMMENT ON TABLE {t} IS" in DDL


def test_the_writer_and_the_ddl_agree_on_columns_and_values():
    assert set(br.STATUS_COLS) | {"status_since", "run_id"} == _columns("curated.box_location_status")
    assert set(br.STALE_COLS) | {"stale_since", "run_id"} == _columns("curated.box_dsu_bench_stale")
    run_cols = _columns("meta.box_recon_run")
    for c in re.search(r"INSERT INTO meta\.box_recon_run \(([^)]*)\)", SRC).group(1).split(","):
        assert c.strip() in run_cols, c
    log_cols = _columns("curated.box_location_status_log")
    for c in re.search(r"INSERT INTO curated\.box_location_status_log\s*\(([^)]*)\)", SRC).group(1).split(","):
        assert c.strip() in log_cols, c
    for s in ("open", "permitted", "pending", "producing", "conflict"):
        assert f"'{s}'" in DDL and f"'{s}'" in br.JUDGE_SQL
    for cause in ("first_run", "well", "set_change", "rule_change"):
        assert f"'{cause}'" in DDL
    assert "'stopped'" in DDL and "'stopped'" in SRC
    for s in ("written", "breaker", "failed"):
        assert f"'{s}'" in DDL


def test_apply_script_names_exist_in_the_ddl():
    from scripts import apply_box_recon as ab

    assert ab.TABLES == br.TABLES and ab.SQL.name == "74_box_recon.sql"
    for name in (*ab.CONSTRAINTS, *(i for i in ab.INDEXES if not i.endswith("_pkey"))):
        assert name in DDL, name
    assert ab.STICK_INDEX in (ROOT / "sql" / "73_box_location_set.sql").read_text(encoding="utf-8")


def test_breaker_limit_and_log_cause():
    assert br.breaker_limit(79_200) == 792 and br.breaker_limit(5_000) == 200
    assert br.log_cause(True, False, False) == "first_run"
    assert br.log_cause(False, True, True) == "set_change"                           # a new record set explains the whole night
    assert br.log_cause(False, False, True) == "rule_change"
    assert br.log_cause(False, False, False) == "well"


class _Cur:
    def __init__(self, conn):
        self.conn, self.connection, self._row = conn, conn, None

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False

    def execute(self, sql, params=None):
        self.conn.seen.append(" ".join(str(sql).split())[:60])
        self._row = (None,) if "to_regclass" in sql else (0,)
        return self

    def fetchone(self):
        return self._row

    def fetchall(self):
        return []


class _Conn:
    def __init__(self):
        self.seen, self.autocommit, self.closed = [], True, False

    def cursor(self):
        return _Cur(self)

    def rollback(self):
        pass

    def close(self):
        self.closed = True


def test_before_sql74_is_applied_the_step_reads_and_returns():
    c = _Conn()
    out = br.run(write=True, conn=c)
    assert out["status"] == "absent" and set(out["missing"]) == set(br.TABLES)
    assert all(s.startswith("SELECT to_regclass") for s in c.seen), c.seen           # nothing but existence checks
    assert not c.closed                                                              # a caller's connection is the caller's to close


def test_the_hook_never_raises(monkeypatch):
    def boom(**kw):
        raise RuntimeError("judge failed")

    monkeypatch.setattr(br, "run", boom)
    monkeypatch.setattr(db, "get_connection", lambda: (_ for _ in ()).throw(RuntimeError("no database")))
    br.nightly_hook()                                                                # neither failure escapes


def test_the_hook_skips_quietly_when_absent(monkeypatch):
    monkeypatch.setattr(br, "run", lambda **kw: {"status": "absent", "missing": list(br.TABLES)})
    br.nightly_hook()


def test_refresh_wires_the_hook_after_everything_it_reads():
    hooks = refresh.build_hooks()
    assert hooks[refresh.BOX_RECON_BEFORE] is br.nightly_hook and "curated.formation_blueox" in hooks
    order = list(db._CURATED_MATVIEWS)
    at = order.index(refresh.BOX_RECON_BEFORE)
    for read in ("curated.wells", "curated.well_lateral_survey", "curated.formation_blueox", "curated.formation_blueox_tvd"):
        assert order.index(read) < at, read
    assert refresh.BOX_RECON_BEFORE not in refresh.build_hooks(box=False)
    assert refresh.build_hooks(tag=False, box=False) is None
    for t in br.TABLES:
        assert t not in order                                                        # tables, not matviews: nothing to REFRESH


@pytest.mark.parametrize("flag", ["--no-box-recon", "--no-tag-rule"])
def test_refresh_flags_drop_one_hook_each(monkeypatch, flag):
    got = {}
    monkeypatch.setattr(refresh, "refresh_curated", lambda force, hooks: got.update(hooks=hooks))
    refresh.main([flag])
    dropped = refresh.BOX_RECON_BEFORE if flag == "--no-box-recon" else "curated.formation_blueox"
    assert dropped not in got["hooks"] and len(got["hooks"]) == 1
