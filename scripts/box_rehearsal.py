"""BOX store rehearsal container (step 16d): a throwaway PostGIS seeded READ-ONLY from the live `box` state.

    python -m scripts.box_rehearsal up       # docker: postgis/postgis:16-3.4 as box-rehearsal on localhost:5437
    python -m scripts.box_rehearsal seed     # live box + box_econ SCHEMA (pg_dump --schema-only) + the small reference tables
    python -m scripts.box_rehearsal verify   # seeded row counts == live, per table
    python -m scripts.box_rehearsal env      # the DB_* lines that point the store scripts at the container
    python -m scripts.box_rehearsal down     # remove the container

Live is only READ (pg_dump runs in a read-only snapshot; counts are SELECTs). Seeded data: bench_scope, extent, extent_edge, tc_area,
type_curve, tc_member, risk_factor, location, location_source and forecast_run (the record run's header row) — what
`box_pud_run store`, `box_water_run store` and `box_prox_record store` read (the D73 crosswalk, the record flip, FKs). No PUD /
stream / month / analog rows and no box_econ rows are copied (the new runs write their own; Steven's priced rows stay live-only).
"""

from __future__ import annotations

import argparse
import os
import re
import subprocess
import sys
import tempfile
import time
from pathlib import Path

from etl.db import _db_kwargs, get_connection

NAME = "box-rehearsal"
IMAGE = "postgis/postgis:16-3.4"  # what the 2026-10-20 proximity rehearsal ran on; the dump's PG17-only SETs are stripped
PORT = 5437
PASSWORD = "rehearsal"  # throwaway container on localhost only
PG_BIN = Path(r"C:\Program Files\PostgreSQL\17\bin")
ROLES = ("analyst_ro", "box_econ_writer")
SEED_TABLES = ("bench_scope", "extent", "extent_edge", "tc_area", "type_curve", "tc_member", "risk_factor", "location", "location_source",
               "forecast_run")
PG17_ONLY = re.compile(r"^SET (transaction_timeout|idle_session_timeout)\b.*$", re.MULTILINE)


def _live_env() -> dict[str, str]:
    k = _db_kwargs()
    return {**os.environ, "PGHOST": k["host"], "PGPORT": str(k["port"]), "PGDATABASE": k["dbname"], "PGUSER": k["user"],
            "PGPASSWORD": k["password"], "PGSSLMODE": k["sslmode"]}


def _box_env() -> dict[str, str]:
    return {**os.environ, "PGHOST": "localhost", "PGPORT": str(PORT), "PGDATABASE": "postgres", "PGUSER": "postgres", "PGPASSWORD": PASSWORD,
            "PGSSLMODE": "disable"}


def _run(cmd: list[str], env: dict[str, str] | None = None, stdin: str | None = None) -> str:
    r = subprocess.run(cmd, env=env, input=stdin, capture_output=True, text=True, encoding="utf-8", check=False)
    if r.returncode:
        raise SystemExit(f"{' '.join(cmd[:3])} failed ({r.returncode}):\n{r.stderr[-3000:]}")
    return r.stdout


def cmd_up(_: argparse.Namespace) -> int:
    exists = subprocess.run(["docker", "inspect", NAME], capture_output=True, text=True, check=False).returncode == 0
    if not exists:
        _run(["docker", "run", "-d", "--name", NAME, "-e", f"POSTGRES_PASSWORD={PASSWORD}", "-p", f"{PORT}:5432", IMAGE])
    # PostGIS in `extensions`, as on live: the store SQL qualifies extensions.ST_* and the dumped DDL uses extensions.geometry
    # (the image installs PostGIS + topology / tiger into public at init; on a fresh, empty container move it: drop and re-create)
    sql = ("CREATE SCHEMA IF NOT EXISTS extensions;\n"
           "DO $$BEGIN IF NOT EXISTS (SELECT 1 FROM pg_extension e JOIN pg_namespace n ON n.oid = e.extnamespace "
           "WHERE e.extname = 'postgis' AND n.nspname = 'extensions') THEN "
           "DROP EXTENSION IF EXISTS postgis_tiger_geocoder CASCADE; DROP EXTENSION IF EXISTS postgis_topology CASCADE; "
           "DROP EXTENSION IF EXISTS postgis CASCADE; CREATE EXTENSION postgis SCHEMA extensions; END IF; END$$;\n"
           "ALTER DATABASE postgres SET search_path = \"$user\", public, extensions;\n"
           + "".join(f"DO $$BEGIN CREATE ROLE {r} NOLOGIN; EXCEPTION WHEN duplicate_object THEN NULL; END$$;\n" for r in ROLES))
    # the image's entrypoint runs a temporary server for initdb, then restarts it: retry until a real session succeeds
    for _i in range(60):
        r = subprocess.run([str(PG_BIN / "psql.exe"), "-v", "ON_ERROR_STOP=1", "-q"], env=_box_env(), input=sql, capture_output=True,
                           text=True, encoding="utf-8", check=False)
        if r.returncode == 0:
            break
        time.sleep(3)
    else:
        raise SystemExit(f"container did not accept a session: {r.stderr[-500:]}")
    print(f"{NAME} up on localhost:{PORT} ({IMAGE}); postgis + roles {ROLES} created")
    return 0


def cmd_seed(_: argparse.Namespace) -> int:
    with tempfile.TemporaryDirectory() as td:
        schema = Path(td) / "schema.sql"
        _run([str(PG_BIN / "pg_dump.exe"), "--schema-only", "--no-owner", "--no-privileges", "-n", "box", "-n", "box_econ", "-f", str(schema)],
             env=_live_env())
        ddl = PG17_ONLY.sub("", schema.read_text(encoding="utf-8"))
        ddl = re.sub(r"^CREATE SCHEMA (box|box_econ);$", r"CREATE SCHEMA IF NOT EXISTS \1;", ddl, flags=re.MULTILINE)
        _run([str(PG_BIN / "psql.exe"), "-v", "ON_ERROR_STOP=1", "-q"], env=_box_env(), stdin=ddl)
        data = Path(td) / "data.sql"
        tabs = [a for t in SEED_TABLES for a in ("-t", f"box.{t}")]
        _run([str(PG_BIN / "pg_dump.exe"), "--data-only", "--no-owner", "--no-privileges", *tabs, "-f", str(data)], env=_live_env())
        dat = PG17_ONLY.sub("", data.read_text(encoding="utf-8"))
        _run([str(PG_BIN / "psql.exe"), "-v", "ON_ERROR_STOP=1", "-q", "-c", "SET session_replication_role = replica", "-f", "-"],
             env=_box_env(), stdin=dat)
    print("seeded: box + box_econ schema; data for " + ", ".join(SEED_TABLES))
    return cmd_verify(_)


def _counts(conn_env: dict[str, str]) -> dict[str, int]:
    sql = " UNION ALL ".join(f"SELECT '{t}', count(*) FROM box.{t}" for t in SEED_TABLES) + ";"
    out = _run([str(PG_BIN / "psql.exe"), "-At", "-F", "|", "-c", sql], env=conn_env)
    return {a: int(b) for a, b in (ln.split("|") for ln in out.strip().splitlines())}


def cmd_verify(_: argparse.Namespace) -> int:
    with get_connection() as conn:  # live, read-only
        cur = conn.cursor()
        cur.execute("SET TRANSACTION READ ONLY")
        live = {}
        for t in SEED_TABLES:
            cur.execute(f"SELECT count(*) FROM box.{t}")  # fixed table list
            live[t] = int(cur.fetchone()[0])
        cur.execute("SELECT last_value FROM box.forecast_run_run_id_seq")
        live_seq = int(cur.fetchone()[0])
        conn.rollback()
    box = _counts(_box_env())
    seq = int(_run([str(PG_BIN / "psql.exe"), "-At", "-c", "SELECT last_value FROM box.forecast_run_run_id_seq"], env=_box_env()).strip())
    bad = [t for t in SEED_TABLES if live[t] != box.get(t)]
    for t in SEED_TABLES:
        print(f"  {'ok ' if t not in bad else 'BAD'} {t}: live {live[t]} / container {box.get(t)}")
    print(f"  {'ok ' if seq == live_seq else 'BAD'} forecast_run_run_id_seq: live {live_seq} / container {seq}")
    return 1 if bad or seq != live_seq else 0


def cmd_env(_: argparse.Namespace) -> int:
    print(f"DB_HOST=localhost\nDB_PORT={PORT}\nDB_NAME=postgres\nDB_USER=postgres\nDB_PASSWORD={PASSWORD}\nDB_SSLMODE=disable")
    return 0


def cmd_down(_: argparse.Namespace) -> int:
    _run(["docker", "rm", "-f", NAME])
    print(f"{NAME} removed")
    return 0


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    for n in ("up", "seed", "verify", "env", "down"):
        sub.add_parser(n)
    a = ap.parse_args(argv)
    sys.stdout.reconfigure(encoding="utf-8")  # type: ignore[union-attr]
    return {"up": cmd_up, "seed": cmd_seed, "verify": cmd_verify, "env": cmd_env, "down": cmd_down}[a.cmd](a)


if __name__ == "__main__":
    raise SystemExit(main())
