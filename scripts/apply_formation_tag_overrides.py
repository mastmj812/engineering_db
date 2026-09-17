"""Load ref.formation_tag_overrides (sql/44) + rebuild curated.formation_blueox
(sql/16) + verify every override landed (Supabase oilgas).

⚠ sql/16 is DROP ... CASCADE: it takes the whole tag-consumer chain with it
(wells_enriched view, producing_reference, formation_blueox_tvd, bench_reference,
reconciled_inventory, the intel chain, erebor_locations). This script deliberately
rebuilds ONLY the seed table + formation_blueox and then STOPS — run it as a step
INSIDE a chain-rebuild window (the quarterly runbook order), followed by:
    apply_intel_formation_blueox -> apply_reconciled_inventory ->
    apply_intel_pdp_support -> apply_erebor_locations (FINAL) -> sql/26 -> sql/31
Standalone use outside a window leaves the apps dark until that tail runs.

Run from repo root in the venv:
    python -m scripts.apply_formation_tag_overrides
"""

from __future__ import annotations

import csv
import time
from pathlib import Path

from etl.db import get_connection

REPO = Path(__file__).resolve().parent.parent
SQL = REPO / "sql"
SEED = REPO / "seeds" / "formation_tag_overrides.csv"


def _run_sql_with_copy(cur, sql_path: Path, table: str, columns: str, csv_path: Path) -> None:
    """Execute a sql file whose one \\copy meta-command we replay via psycopg."""
    lines = sql_path.read_text(encoding="utf-8").splitlines()
    copy_idx = next(i for i, ln in enumerate(lines) if ln.lstrip().startswith("\\copy"))
    cur.execute("\n".join(lines[:copy_idx]))
    with cur.copy(
        f"COPY {table} ({columns}) FROM STDIN WITH (FORMAT csv, HEADER true)"
    ) as cp, open(csv_path, "rb") as fh:
        while data := fh.read(65536):
            cp.write(data)
    cur.execute("\n".join(lines[copy_idx + 1:]))


def main() -> None:
    expected = list(csv.DictReader(open(SEED, encoding="utf-8")))
    t0 = time.monotonic()
    conn = get_connection()
    try:
        conn.autocommit = True
        with conn.cursor() as cur:
            print(f"[1/3] load ref.formation_tag_overrides ({len(expected)} rows, sql/44)", flush=True)
            _run_sql_with_copy(cur, SQL / "44_formation_tag_overrides.sql",
                               "ref.formation_tag_overrides",
                               "api10, corrected_code, was, note", SEED)
            n = cur.execute("SELECT COUNT(*) FROM ref.formation_tag_overrides").fetchone()[0]
            ok = "OK" if n == len(expected) else "MISMATCH"
            print(f"    loaded {n} rows (csv {len(expected)}) [{ok}]", flush=True)

            print("[2/3] rebuild curated.formation_blueox (sql/16, DROP CASCADE — see header)", flush=True)
            t = time.monotonic()
            cur.execute((SQL / "16_formation_blueox.sql").read_text(encoding="utf-8"))
            print(f"    built in {time.monotonic() - t:.0f}s", flush=True)

            print("[3/3] verify every override landed", flush=True)
            rows = cur.execute("""
                SELECT o.api10, o.corrected_code, fb.formation_blueox, fb.formation_blueox_source
                FROM ref.formation_tag_overrides o
                LEFT JOIN curated.formation_blueox fb USING (api10)
            """).fetchall()
            bad = [r for r in rows
                   if r[2] != r[1] or r[3] != 'ratified_override']
            print(f"    overrides applied: {len(rows) - len(bad)}/{len(rows)}"
                  f"  [{'OK' if not bad else 'MISMATCH'}]", flush=True)
            for api, want, got, src in bad:
                print(f"      {api}: want {want}, got {got} (source {src})", flush=True)
            n_src = cur.execute(
                "SELECT COUNT(*) FROM curated.formation_blueox "
                "WHERE formation_blueox_source = 'ratified_override'"
            ).fetchone()[0]
            print(f"    rows with source=ratified_override: {n_src} (identity: = override rows "
                  f"whose api10 exists in curated.wells)", flush=True)
    finally:
        conn.close()
    print(f"=== DONE in {time.monotonic() - t0:.0f}s — now run the downstream chain "
          f"(see module docstring) ===", flush=True)


if __name__ == "__main__":
    main()
