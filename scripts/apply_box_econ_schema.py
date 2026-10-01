"""Apply sql/52 (box_econ sandbox schema) and wire an econ writer login.

  1. sql/52 — schema box_econ, NOLOGIN group role box_econ_writer (USAGE +
     CREATE on box_econ, member of analyst_ro), analyst_ro read grants.
  2. --writer <login> (optional; the LOGIN role must already exist — Michael
     creates it and sets the password himself, it never touches the repo):
       - GRANT box_econ_writer TO <login>
       - GRANT <login> TO postgres WITH INHERIT FALSE, SET TRUE — required on
         PG16+ so postgres may ALTER DEFAULT PRIVILEGES FOR ROLE <login>
       - default privileges: tables <login> creates in box_econ are SELECTable
         by analyst_ro and postgres (apps + agent)
       - re-grant SELECT on tables <login> already owns there
       - role settings: statement_timeout 300s, idle-in-transaction 60s,
         connection limit 5
  3. validate by privilege identity (has_*_privilege), then a smoke test as
     <login> inside a transaction that is ROLLED BACK: create + insert a table
     in box_econ (must work, must be readable by analyst_ro + postgres), and
     CREATE TABLE in curated (must be refused).

!! DDL on the shared warehouse — explicit authorization required. From repo
root in the venv:
    python -m scripts.apply_box_econ_schema [--writer <login>]
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

from psycopg import errors, sql

from etl.db import get_connection

SQL = Path(__file__).resolve().parent.parent / "sql"
SCHEMA = "box_econ"
GROUP = "box_econ_writer"
READERS = ("analyst_ro", "postgres")
# Schemas a writer must NOT be able to create in.
LOCKED_SCHEMAS = ("curated", "raw_intel", "raw_novi", "raw_enverus", "meta", "narvi", "ref", "public")

_failures: list[str] = []


def _check(ok: bool, msg: str) -> None:
    print(f"    {'ok  ' if ok else 'FAIL'} {msg}", flush=True)
    if not ok:
        _failures.append(msg)


def apply_schema(conn) -> None:
    print("[1/3] sql/52 — box_econ schema + box_econ_writer", flush=True)
    with conn.cursor() as cur:
        cur.execute((SQL / "52_box_econ_schema.sql").read_text(encoding="utf-8"))
    conn.commit()


def wire_writer(conn, login: str) -> None:
    print(f"[2/3] wire writer {login!r}", flush=True)
    with conn.cursor() as cur:
        row = cur.execute(
            "SELECT rolcanlogin, rolsuper, rolbypassrls FROM pg_roles WHERE rolname = %s",
            (login,),
        ).fetchone()
        if row is None:
            sys.exit(f"role {login!r} does not exist — create it first (see the PR body)")
        canlogin, superuser, bypassrls = row
        if not canlogin or superuser or bypassrls:
            sys.exit(f"role {login!r} must be LOGIN, non-superuser, non-BYPASSRLS; got {row}")

        r = sql.Identifier(login)
        s = sql.Identifier(SCHEMA)
        readers = sql.SQL(", ").join(sql.Identifier(x) for x in READERS)
        cur.execute(sql.SQL("GRANT {} TO {}").format(sql.Identifier(GROUP), r))
        cur.execute(sql.SQL("GRANT {} TO postgres WITH INHERIT FALSE, SET TRUE").format(r))
        cur.execute(
            sql.SQL("ALTER DEFAULT PRIVILEGES FOR ROLE {} IN SCHEMA {} GRANT SELECT ON TABLES TO {}")
            .format(r, s, readers)
        )
        owned = cur.execute(
            "SELECT c.relname FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace "
            "WHERE n.nspname = %s AND c.relkind IN ('r','p','v','m') AND pg_get_userbyid(c.relowner) = %s",
            (SCHEMA, login),
        ).fetchall()
        if owned:
            cur.execute(sql.SQL("SET ROLE {}").format(r))
            for (name,) in owned:
                cur.execute(
                    sql.SQL("GRANT SELECT ON {}.{} TO {}").format(s, sql.Identifier(name), readers)
                )
            cur.execute("RESET ROLE")
        print(f"    re-granted SELECT on {len(owned)} existing table(s)", flush=True)
        cur.execute(sql.SQL("ALTER ROLE {} SET statement_timeout = '300s'").format(r))
        cur.execute(sql.SQL("ALTER ROLE {} SET idle_in_transaction_session_timeout = '60s'").format(r))
        cur.execute(sql.SQL("ALTER ROLE {} CONNECTION LIMIT 5").format(r))
    conn.commit()


def validate(conn, login: str | None) -> None:
    print("[3/3] validate", flush=True)
    with conn.cursor() as cur:
        q = cur.execute
        _check(q("SELECT to_regnamespace(%s) IS NOT NULL", (SCHEMA,)).fetchone()[0], "schema box_econ exists")
        _check(q("SELECT has_schema_privilege(%s, %s, 'CREATE')", (GROUP, SCHEMA)).fetchone()[0],
               "box_econ_writer can CREATE in box_econ")
        _check(q("SELECT has_schema_privilege('analyst_ro', %s, 'USAGE')", (SCHEMA,)).fetchone()[0],
               "analyst_ro can USE box_econ")
        for api_role in ("anon", "authenticated"):
            _check(not q("SELECT has_schema_privilege(%s, %s, 'USAGE')", (api_role, SCHEMA)).fetchone()[0],
                   f"{api_role} (Data API) has no USAGE on box_econ")
        if login is None:
            return

        for nsp in LOCKED_SCHEMAS:
            _check(not q("SELECT has_schema_privilege(%s, %s, 'CREATE')", (login, nsp)).fetchone()[0],
                   f"{login} cannot CREATE in {nsp}")
        writable = q(
            "SELECT count(*) FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace "
            "WHERE n.nspname <> %s AND n.nspname = ANY(%s) AND c.relkind IN ('r','p') "
            "AND (has_table_privilege(%s, c.oid, 'INSERT') OR has_table_privilege(%s, c.oid, 'UPDATE') "
            "  OR has_table_privilege(%s, c.oid, 'DELETE') OR has_table_privilege(%s, c.oid, 'TRUNCATE'))",
            (SCHEMA, list(LOCKED_SCHEMAS), login, login, login, login),
        ).fetchone()[0]
        _check(writable == 0, f"{login} can write 0 tables outside box_econ (got {writable})")
        _check(q("SELECT has_table_privilege(%s, 'curated.erebor_locations', 'SELECT')", (login,)).fetchone()[0],
               f"{login} can read curated (via analyst_ro)")
        cfg = q("SELECT rolconfig, rolconnlimit FROM pg_roles WHERE rolname = %s", (login,)).fetchone()
        _check(any(re.match(r"statement_timeout=", c) for c in (cfg[0] or [])) and cfg[1] == 5,
               f"{login} role settings {cfg}")

        # Smoke as the writer — everything below is rolled back.
        r = sql.Identifier(login)
        try:
            cur.execute(sql.SQL("SET ROLE {}").format(r))
            cur.execute("CREATE TABLE box_econ._apply_smoke (location_key text, npv10_usd numeric)")
            cur.execute("INSERT INTO box_econ._apply_smoke VALUES ('smoke', 0)")
            cur.execute("RESET ROLE")
            for reader in READERS:
                _check(q("SELECT has_table_privilege(%s, 'box_econ._apply_smoke', 'SELECT')", (reader,)).fetchone()[0],
                       f"{reader} can read a table {login} creates")
            _check(q("SELECT count(*) FROM box_econ._apply_smoke").fetchone()[0] == 1,
                   "postgres reads the writer's row")
            cur.execute(sql.SQL("SET ROLE {}").format(r))
            cur.execute("SAVEPOINT s")
            try:
                cur.execute("CREATE TABLE curated._apply_smoke (x int)")
                _check(False, f"{login} was ALLOWED to create in curated")
            except errors.InsufficientPrivilege:
                cur.execute("ROLLBACK TO SAVEPOINT s")
                _check(True, f"{login} refused CREATE in curated")
        finally:
            conn.rollback()


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--writer", help="existing LOGIN role to wire as a box_econ writer")
    args = ap.parse_args()

    conn = get_connection()
    try:
        apply_schema(conn)
        if args.writer:
            wire_writer(conn, args.writer)
        validate(conn, args.writer)
    finally:
        conn.close()
    if _failures:
        sys.exit(f"{len(_failures)} check(s) FAILED")
    print("all checks passed", flush=True)


if __name__ == "__main__":
    main()
