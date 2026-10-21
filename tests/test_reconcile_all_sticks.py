"""D117 step 2 (sql/68): reconciliation over every Novi stick — static pins, no database.

sql/68 must keep sql/21's match rule byte for byte (only the stick filter and the
`category` column change), sql/21 is retired, and every consumer that encoded
"PUD only" moved with it (sql/25 net_new_pdp, sql/43 vintage accuracy, the apply
scripts' identities).
"""

from __future__ import annotations

import re
import subprocess
from pathlib import Path

import pytest

from scripts import apply_reconcile_all_sticks as a

ROOT = Path(__file__).resolve().parents[1]
SQL = ROOT / "sql"


def _read(name: str) -> str:
    return (SQL / name).read_text(encoding="utf-8")


def _strip_comments(sql: str) -> str:
    return "\n".join(ln.split("--", 1)[0].rstrip() for ln in sql.splitlines() if ln.split("--", 1)[0].strip())


def test_sql68_reconciles_pud_and_res_and_carries_category():
    body = a.select_body(_read("68_reconcile_all_sticks.sql"))
    assert "WHERE il.category IN ('PUD', 'RES')" in body
    assert "pud.category                            AS category" in body
    assert "idx_reconciled_inventory_category" in _read("68_reconcile_all_sticks.sql")


def test_sql68_match_rule_is_sql21s():
    # sql/21's last real body (commit 37e91f9) vs sql/68: identical apart from the
    # stick filter and the category column.
    got = subprocess.run(["git", "show", "37e91f9:sql/21_reconciled_inventory.sql"], cwd=ROOT,
                         capture_output=True, text=True, encoding="utf-8")
    if got.returncode != 0:  # shallow CI checkout: the history is not there
        pytest.skip("commit 37e91f9 not available (shallow clone)")
    old = got.stdout
    old_body = _strip_comments(a.select_body(old))
    new_body = _strip_comments(a.select_body(_read("68_reconcile_all_sticks.sql")))
    new_body = (new_body.replace("WHERE il.category IN ('PUD', 'RES')", "WHERE il.category = 'PUD'")
                .replace("        il.category,\n", "")
                .replace("    END                                     AS status,\n    pud.category                            AS category",
                         "    END                                     AS status"))
    assert new_body == old_body


def test_sql21_is_retired():
    text = _read("21_reconciled_inventory.sql")
    assert "RETIRED" in text and "DO NOT RUN" in text and "68_reconcile_all_sticks.sql" in text
    assert not re.search(r"^\s*(CREATE|DROP)\b", _strip_comments(text), re.M | re.I)


def test_net_new_and_vintage_accuracy_match_every_stick():
    assert "WHERE il.category IN ('PUD', 'RES')" in a.net_new_select(_read("25_net_new_pdp.sql"))
    sql43 = next(SQL.glob("43_*.sql")).read_text(encoding="utf-8")
    assert "wm.inventory_class IN ('BASE_CASE', 'EMERGING')" in sql43
    assert "wm.inventory_class = 'BASE_CASE'" not in sql43


def test_nothing_still_runs_sql21():
    for path in [*(ROOT / "scripts").glob("*.py"), SQL / "32_wellstick_degenerate_fix.sql"]:
        assert '"21_reconciled_inventory.sql"' not in path.read_text(encoding="utf-8"), path
        assert "\\ir 21_reconciled_inventory.sql" not in path.read_text(encoding="utf-8"), path


def test_wellstick_identity_counts_pud_and_res():
    text = (ROOT / "scripts" / "apply_wellstick_fix.py").read_text(encoding="utf-8")
    assert "il.category IN ('PUD', 'RES')" in text
    assert a.STICK_UNIVERSE_SQL.count("il.category IN ('PUD', 'RES')") == 1
