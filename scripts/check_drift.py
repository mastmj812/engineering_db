"""Report-only drift checker: repo sql/ declarations vs the live warehouse,
plus basic GitHub estate hygiene.

Mechanizes the "verify live, not repo or memory" rule (CLAUDE.md): the
recurring failure class here is repo-state != live-state — an apply script
committed but never run against Supabase, or a memory claiming an object is
unapplied when it is actually live. This tool compares the objects the
numbered sql/NN files declare against what the live catalogs report, and
lists estate smells (orphan remote branches, stale open PRs) across the four
suite repos.

Usage:
    python -m scripts.check_drift          # full report to stdout

The same report is appended to the nightly summary email via
``drift_email_section()`` (called from etl/notify.py). That entry point NEVER
raises — every failure degrades to a "... errored: <msg>" report line, so a
broken drift check can never fail or perturb the nightly.

READ-ONLY without exception: the live side is catalog SELECTs only
(pg_matviews / pg_views / pg_tables / pg_proc / pg_indexes), run in a
READ ONLY transaction with a bounded statement_timeout. No DDL, no writes,
no remediation. GitHub access is read-only ``gh api`` REST calls.

Deliberate limitations (keep the logic simple and honest):
  * Name-level only. Column drift, index definitions, matview bodies, and
    function signatures are NOT compared — an object counts as "live" if a
    same-named object of the same kind exists in the same schema.
  * DROP semantics are not parsed. The checker compares the UNION of every
    object ever declared in sql/ against live; a later file that
    drops/replaces an earlier object is handled by ``KNOWN_RETIRED``
    (explicit whitelist), not by parsing DROP chains.
  * Scope is the ``curated`` and ``meta`` schemas. Raw vendor schemas
    (raw_novi, raw_enverus, raw_intel, raw_novi_intel, ref) track vendor
    drift through their own loaders; ``narvi.*`` is app-owned (its DDL lives
    in the narvi repo) and is out of scope entirely.
  * Dollar-quoted function bodies are not excluded from parsing (none of the
    current bodies contain CREATE statements) and quoted mixed-case
    identifiers are lowercased (none exist in curated/meta).
  * The reverse direction (live-but-undeclared) is informational, not a
    failure: apply scripts legitimately create a few objects that have no
    numbered sql/NN mirror. Auto-generated ``*_pkey`` indexes are ignored.
"""

from __future__ import annotations

import json
import re
import subprocess
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Callable, Iterable, Mapping

SQL_DIR = Path(__file__).resolve().parents[1] / "sql"

# Schemas the declared-vs-live comparison covers (see module docstring).
CHECKED_SCHEMAS: tuple[str, ...] = ("curated", "meta")

# Objects declared somewhere in sql/ that are KNOWN to be retired/superseded
# live (a later file or apply script dropped or replaced them). Add entries
# here — with the reason — instead of teaching the parser DROP semantics.
# Format: (kind, "schema.name").
KNOWN_RETIRED: frozenset[tuple[str, str]] = frozenset(
    {
        # (none currently — sql/12 and sql/13 were emptied to comment-only
        # stubs when the Snowflake migration retired their objects, so
        # nothing retired is still *declared* in sql/.)
    }
)

# The four suite repos (CLAUDE.md table). Note the GitHub repo for anduin is
# `permiantypecurve` (no underscores), unlike its local folder name.
REPOS: tuple[str, ...] = (
    "mastmj812/engineering_db",
    "mastmj812/permiantypecurve",
    "mastmj812/erebor",
    "mastmj812/narvi",
)

STALE_PR_DAYS = 7
# A no-PR branch younger than this is called out as likely in-flight work
# rather than an orphan (all four repos either auto-delete merged branches or
# merge via PR, so any surviving branch without an open PR is noteworthy).
ORPHAN_MIN_AGE_HOURS = 24

_GH_TIMEOUT_S = 60
_DB_STATEMENT_TIMEOUT = "120s"

KINDS: tuple[str, ...] = ("matview", "view", "table", "function", "index")


# ---------------------------------------------------------------------------
# sql/ parsing (pure)
# ---------------------------------------------------------------------------

# Schema-qualified or bare identifier (optionally double-quoted) — same
# convention as tests/test_sql_unique_index.py.
_IDENT = r'[A-Za-z0-9_."]+'

_OBJECT_RES: tuple[tuple[str, re.Pattern[str]], ...] = (
    (
        "matview",
        re.compile(
            rf"CREATE\s+MATERIALIZED\s+VIEW\s+(?:IF\s+NOT\s+EXISTS\s+)?({_IDENT})",
            re.IGNORECASE,
        ),
    ),
    (
        "view",
        re.compile(
            rf"CREATE\s+(?:OR\s+REPLACE\s+)?VIEW\s+(?:IF\s+NOT\s+EXISTS\s+)?({_IDENT})",
            re.IGNORECASE,
        ),
    ),
    (
        "table",
        re.compile(
            rf"CREATE\s+TABLE\s+(?:IF\s+NOT\s+EXISTS\s+)?({_IDENT})",
            re.IGNORECASE,
        ),
    ),
    (
        "function",
        re.compile(
            rf"CREATE\s+(?:OR\s+REPLACE\s+)?FUNCTION\s+({_IDENT})\s*\(",
            re.IGNORECASE,
        ),
    ),
)

# Index names are unqualified in our sql/; the index lives in the schema of
# its target table, so capture both (name, target).
_INDEX_RE = re.compile(
    rf"CREATE\s+(?:UNIQUE\s+)?INDEX\s+(?:CONCURRENTLY\s+)?(?:IF\s+NOT\s+EXISTS\s+)?"
    rf"({_IDENT})\s+ON\s+(?:ONLY\s+)?({_IDENT})",
    re.IGNORECASE,
)


def _strip_line_comments(text: str) -> str:
    """Drop ``-- ...`` to end of line so DDL mentioned in comments (e.g. the
    retired sql/12 and sql/13 stubs) is not mistaken for a declaration."""
    return "\n".join(line.split("--", 1)[0] for line in text.splitlines())


def _norm(identifier: str) -> str:
    return identifier.replace('"', "").lower()


def _schema_of(qualified: str) -> str:
    """Schema of a normalized name; unqualified names map to 'public' (which
    is outside CHECKED_SCHEMAS and therefore dropped from scope)."""
    return qualified.split(".", 1)[0] if "." in qualified else "public"


def parse_sql_objects(text: str) -> list[tuple[str, str]]:
    """Extract (kind, schema.name) pairs declared by one sql file's text.

    Name-level only; indexes are qualified with their target table's schema.
    No scope filtering here — that happens in ``collect_declared``.
    """
    body = _strip_line_comments(text)
    found: list[tuple[str, str]] = []
    for kind, pattern in _OBJECT_RES:
        for match in pattern.findall(body):
            found.append((kind, _norm(match)))
    for name, target in _INDEX_RE.findall(body):
        target_norm = _norm(target)
        schema = _schema_of(target_norm)
        found.append(("index", f"{schema}.{_norm(name)}"))
    return found


def collect_declared(
    sql_dir: Path = SQL_DIR, schemas: Iterable[str] = CHECKED_SCHEMAS
) -> dict[tuple[str, str], set[str]]:
    """Union of in-scope objects declared across all sql/NN files.

    Returns {(kind, "schema.name"): {declaring file names}}.
    """
    scope = set(schemas)
    declared: dict[tuple[str, str], set[str]] = {}
    for path in sorted(sql_dir.glob("*.sql")):
        for kind, name in parse_sql_objects(path.read_text(encoding="utf-8")):
            if _schema_of(name) in scope:
                declared.setdefault((kind, name), set()).add(path.name)
    return declared


# ---------------------------------------------------------------------------
# Live catalogs (read-only)
# ---------------------------------------------------------------------------

_CATALOG_QUERIES: Mapping[str, str] = {
    "matview": (
        "SELECT schemaname || '.' || matviewname FROM pg_matviews "
        "WHERE schemaname = ANY(%s)"
    ),
    "view": (
        "SELECT schemaname || '.' || viewname FROM pg_views "
        "WHERE schemaname = ANY(%s)"
    ),
    "table": (
        "SELECT schemaname || '.' || tablename FROM pg_tables "
        "WHERE schemaname = ANY(%s)"
    ),
    "function": (
        "SELECT DISTINCT n.nspname || '.' || p.proname "
        "FROM pg_proc p JOIN pg_namespace n ON n.oid = p.pronamespace "
        "WHERE n.nspname = ANY(%s)"
    ),
    "index": (
        "SELECT schemaname || '.' || indexname FROM pg_indexes "
        "WHERE schemaname = ANY(%s)"
    ),
}


def fetch_live_objects(
    schemas: Iterable[str] = CHECKED_SCHEMAS,
) -> dict[str, set[str]]:
    """Read live object names per kind from the catalogs, read-only.

    Connects the way the ETL does (etl.db.get_connection — session pooler is
    fine for reads). The whole fetch runs inside a single READ ONLY
    transaction with a bounded statement_timeout (etl sessions default to
    timeout=0, which is wrong for an ancillary check like this).
    """
    from etl.db import get_connection  # lazy: keep module import DB-free

    conn = get_connection()
    try:
        with conn.cursor() as cur:
            # First statement in the (implicit) transaction, so READ ONLY is
            # accepted; SET statement_timeout takes effect immediately.
            cur.execute("SET TRANSACTION READ ONLY")
            cur.execute(f"SET LOCAL statement_timeout = '{_DB_STATEMENT_TIMEOUT}'")
            live: dict[str, set[str]] = {}
            for kind, query in _CATALOG_QUERIES.items():
                cur.execute(query, (list(schemas),))
                live[kind] = {row[0] for row in cur.fetchall()}
        conn.rollback()
        return live
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# Comparison + report formatting (pure)
# ---------------------------------------------------------------------------

def missing_live_lines(
    declared: Mapping[tuple[str, str], set[str]],
    live: Mapping[str, set[str]],
    whitelist: frozenset[tuple[str, str]] = KNOWN_RETIRED,
) -> tuple[list[str], int]:
    """Declared-in-sql/ objects absent from the live warehouse.

    Returns (report lines, count of whitelisted known-retired objects
    skipped). An object present live under a *different* kind is still a
    finding, reported with the kind it actually has.
    """
    lines: list[str] = []
    skipped = 0
    for (kind, name), files in sorted(declared.items()):
        if name in live.get(kind, set()):
            continue
        if (kind, name) in whitelist:
            skipped += 1
            continue
        where = ", ".join(sorted(files))
        other_kinds = sorted(k for k, names in live.items() if name in names)
        if other_kinds:
            lines.append(
                f"    {kind} {name} — declared in {where}; exists live but as "
                f"a {other_kinds[0]}"
            )
        else:
            lines.append(f"    {kind} {name} — declared in {where}; ABSENT live")
    return lines, skipped


def undeclared_live_lines(
    declared: Mapping[tuple[str, str], set[str]],
    live: Mapping[str, set[str]],
) -> list[str]:
    """Live curated/meta objects with no declaration in any sql/NN file.

    Informational: apply scripts create a few objects without a numbered
    mirror. Auto-generated ``*_pkey`` constraint indexes are ignored.
    """
    declared_by_kind: dict[str, set[str]] = {}
    for kind, name in declared:
        declared_by_kind.setdefault(kind, set()).add(name)
    lines: list[str] = []
    for kind in KINDS:
        extra = live.get(kind, set()) - declared_by_kind.get(kind, set())
        for name in sorted(extra):
            if kind == "index" and name.endswith("_pkey"):
                continue
            lines.append(f"    {kind} {name}")
    return lines


def build_drift_lines(
    declared: Mapping[tuple[str, str], set[str]],
    live: Mapping[str, set[str]],
    whitelist: frozenset[tuple[str, str]] = KNOWN_RETIRED,
) -> list[str]:
    """Format the declared-vs-live comparison as indented report lines."""
    plural = {
        "matview": "matviews",
        "view": "views",
        "table": "tables",
        "function": "functions",
        "index": "indexes",
    }
    counts = {kind: sum(1 for k, _ in declared if k == kind) for kind in KINDS}
    summary = ", ".join(f"{counts[k]} {plural[k]}" for k in KINDS if counts[k])
    lines = [f"  declared in sql/ (schemas {', '.join(CHECKED_SCHEMAS)}): {summary}"]

    missing, skipped = missing_live_lines(declared, live, whitelist)
    if missing:
        lines.append("  MISSING LIVE (declared in sql/, absent from warehouse):")
        lines.extend(missing)
    else:
        lines.append("  no drift: every declared object verified live")
    if skipped:
        lines.append(f"  known-retired objects skipped (whitelist): {skipped}")

    extra = undeclared_live_lines(declared, live)
    if extra:
        lines.append("  live but undeclared in sql/ (info — apply-script or ad hoc):")
        lines.extend(extra)
    return lines


# ---------------------------------------------------------------------------
# Estate hygiene via `gh api` (REST)
# ---------------------------------------------------------------------------

def _run_gh(path: str) -> Any:
    """One `gh api <path>` REST call; raises RuntimeError with a short
    message on any failure (missing binary, no token, HTTP error)."""
    try:
        # encoding pinned to utf-8: gh emits UTF-8 JSON, but text=True alone
        # decodes with the Windows ANSI codepage (cp1252) and a non-cp1252
        # byte in a commit message crashes the reader thread.
        proc = subprocess.run(
            ["gh", "api", path],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=_GH_TIMEOUT_S,
        )
    except FileNotFoundError as exc:
        raise RuntimeError("gh CLI not installed") from exc
    except subprocess.TimeoutExpired as exc:
        raise RuntimeError(f"gh api timed out after {_GH_TIMEOUT_S}s") from exc
    if proc.returncode != 0:
        detail = (proc.stderr or proc.stdout or "").strip().splitlines()
        raise RuntimeError(detail[0][:160] if detail else f"gh exited {proc.returncode}")
    return json.loads(proc.stdout)


def _parse_gh_ts(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def stale_pr_lines(prs: Iterable[Mapping[str, Any]], now: datetime) -> list[str]:
    """Open PRs older than STALE_PR_DAYS, formatted. Pure."""
    lines: list[str] = []
    for pr in prs:
        age_days = (now - _parse_gh_ts(pr["created_at"])).days
        if age_days >= STALE_PR_DAYS:
            title = str(pr.get("title", ""))[:60]
            lines.append(f"PR #{pr['number']} open {age_days}d: {title}")
    return lines


def orphan_branch_line(
    name: str, last_commit: datetime | None, now: datetime
) -> str:
    """Format one no-open-PR branch; younger than ORPHAN_MIN_AGE_HOURS is
    labeled in-flight rather than orphan. Pure."""
    if last_commit is None:
        return f"orphan branch {name} (no open PR, last commit date unknown)"
    if now - last_commit < timedelta(hours=ORPHAN_MIN_AGE_HOURS):
        return f"branch {name} has no open PR (pushed <{ORPHAN_MIN_AGE_HOURS}h ago — likely in-flight)"
    return f"orphan branch {name} (no open PR, last commit {last_commit.date().isoformat()})"


def collect_repo_hygiene(
    repo: str,
    now: datetime,
    run_gh: Callable[[str], Any] = _run_gh,
) -> list[str]:
    """Hygiene findings for one repo: stale open PRs + orphan branches."""
    default_branch = run_gh(f"repos/{repo}")["default_branch"]
    prs = run_gh(f"repos/{repo}/pulls?state=open&per_page=100")
    branches = run_gh(f"repos/{repo}/branches?per_page=100")

    lines = stale_pr_lines(prs, now)
    open_heads = {pr["head"]["ref"] for pr in prs}
    candidates = [
        b for b in branches
        if b["name"] != default_branch and b["name"] not in open_heads
    ]
    for branch in candidates[:20]:  # bound the per-branch commit lookups
        last_commit: datetime | None = None
        try:
            commit = run_gh(f"repos/{repo}/commits/{branch['commit']['sha']}")
            last_commit = _parse_gh_ts(commit["commit"]["committer"]["date"])
        except Exception:
            pass  # date stays unknown; still reported as orphan
        lines.append(orphan_branch_line(branch["name"], last_commit, now))
    return lines


def hygiene_lines(
    repos: Iterable[str] = REPOS,
    now: datetime | None = None,
    run_gh: Callable[[str], Any] = _run_gh,
) -> list[str]:
    """Estate hygiene across all repos; per-repo failures degrade to a line.

    If EVERY repo errors (no gh binary / no token, e.g. on the Actions
    runner), collapse to a single "gh unavailable" line instead of one error
    per repo.
    """
    now = now or datetime.now(timezone.utc)
    repos = list(repos)
    findings: list[str] = []
    errors: list[tuple[str, str]] = []
    clean = 0
    for repo in repos:
        try:
            repo_lines = collect_repo_hygiene(repo, now, run_gh)
        except Exception as exc:
            errors.append((repo, str(exc)))
            continue
        if repo_lines:
            findings.extend(f"  {repo}: {line}" for line in repo_lines)
        else:
            clean += 1
    if errors and len(errors) == len(repos):
        return [f"  gh unavailable: {errors[0][1]}"]
    lines = findings
    if clean:
        lines.append(
            f"  clean: {clean} repo(s) with no orphan branches and no PRs "
            f"open >= {STALE_PR_DAYS}d"
        )
    for repo, msg in errors:
        lines.append(f"  {repo}: check errored ({msg})")
    return lines


# ---------------------------------------------------------------------------
# Entry points
# ---------------------------------------------------------------------------

def drift_email_section() -> list[str]:
    """The full drift report as plain-text lines for the nightly email.

    NEVER raises: each half (warehouse drift, estate hygiene) independently
    degrades to an "... errored: <msg>" line on any failure.
    """
    lines = ["Drift check (repo sql/ vs live warehouse):"]
    try:
        declared = collect_declared()
        live = fetch_live_objects()
        lines.extend(build_drift_lines(declared, live))
    except Exception as exc:  # noqa: BLE001 — degrade, never fail the nightly
        lines.append(f"  drift check errored: {exc}")
    lines.append("Estate hygiene (GitHub):")
    try:
        lines.extend(hygiene_lines())
    except Exception as exc:  # noqa: BLE001
        lines.append(f"  hygiene check errored: {exc}")
    return lines


def main() -> int:
    """CLI: print the report. Report-only — always exits 0."""
    print("\n".join(drift_email_section()))
    return 0


if __name__ == "__main__":
    sys.exit(main())
