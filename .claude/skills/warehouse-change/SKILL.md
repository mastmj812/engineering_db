---
name: warehouse-change
description: Author, apply, and verify a change to the oilgas curated layer — the numbered sql/NN + apply-script ritual with cascade blast-radius mapping, index ordering, refresh-order updates, comments/data-dictionary regen, and downstream propagation across anduin/erebor/narvi. Use for any new or changed matview, view, function, index, or column in the warehouse.
---

# Warehouse change — sql/NN → authorize → apply → verify → propagate

Every warehouse change follows the same ritual. Skipping a step has a named incident attached
(15-hour seq-scan build, cancelled sql/30, unapplied-but-committed apply script, stale data
dictionary).

**Hard rules:**
- **Explicit authorization before any DDL/write hits Supabase oilgas** — a phase-level "yes" to a
  plan is not authorization for the statement. Ask with the specific object and blast radius.
- Anything that drops `erebor_locations` or the geography indexes runs **off-hours**, outside the
  nightly window (cron 11:15 UTC).
- `psql` is not installed here. Apply via `python -m scripts.apply_*` or
  `python -c "from scripts.load_intel_sf import run_sql_file; run_sql_file('NN_file.sql')"` —
  both use `etl.db.get_connection()` (5432 session pooler, `statement_timeout=0`,
  `search_path public, extensions`).
- `narvi.*` is app-owned — never touch it from warehouse work.

## 1. Author the numbered SQL

- New file `sql/NN_<name>.sql`, next number (gaps 15/24 stay gaps; numbers are never reused —
  retired files become "DO NOT RUN" tombstones pointing at the successor, per sql/12/13).
- Header genre (see `sql/38` or `sql/22` as exemplars): purpose, DEPENDS ON, REFRESH cadence, RUN
  command, sanity checks.
- Idempotent matview pattern: type-aware `DO $$ … relkind` guard + `DROP … CASCADE` +
  `CREATE MATERIALIZED VIEW … AS` (`sql/22:54-66`). `CREATE OR REPLACE MATERIALIZED VIEW` does
  not exist. Plain views may use `CREATE OR REPLACE VIEW` (sql/34 precedent).
- **Same-file `CREATE UNIQUE INDEX`** on every matview — required for `REFRESH … CONCURRENTLY`
  and enforced by the CI SQL lint (`tests/test_sql_unique_index.py`); PR goes red without it.
- **Schema-qualify `extensions.*`** (`extensions.geography`, `extensions.ST_*`) in any SQL
  function or expression inlined into a matview body — PG17 runs matview CREATE/REFRESH under a
  restricted search_path.
- Raw layers mirror vendor casing (`raw_novi."WellMonths"`); curated is snake_case. Generated
  files (sql/02, sql/03) are regenerated, never hand-edited.

## 2. Map the CASCADE blast radius — before asking to apply

- `DROP … CASCADE` on anything upstream of `curated.wells` reaches nearly the entire curated
  schema (production, formation, AND intel chains — `intel_locations` LEFT JOINs `curated.wells`).
  The cost is **availability**: objects don't exist until each `CREATE … WITH DATA` + index build
  finishes; `production_forecast` is the multi-hour one. Full rebuild order of record:
  `scripts/apply_wellstick_fix.py` (14 steps).
- sql/29 CASCADE-drops the whole intel chain incl. `erebor_locations`; sql/20 additionally kills
  sql/23 + `wells_enriched`. Quarterly chain of record: sql/29 →
  `apply_intel_formation_blueox` → `apply_reconciled_inventory` (20 → 23 → wells_enriched → 21) →
  sql/25 → `apply_intel_pdp_support` (must precede erebor_locations) →
  `apply_intel_forecast_accuracy` → `apply_erebor_locations` (FINAL) → sql/26.
- Check dependencies live if unsure: `pg_depend`/`pg_rewrite` (the data-dictionary generator has
  the query pattern).
- Frequently-edited derivations get factored into their own small matview instead of riding a big
  one (that's why `formation_blueox` is standalone, ~90k rows).

## 3. Ask, then apply

State: the object(s), what drops via CASCADE, expected rebuild time, and whether erebor/narvi go
dark meanwhile. On explicit go-ahead:

- Prefer writing/extending a `scripts/apply_<name>.py` in the house pattern (get_connection on
  5432, autocommit, timed steps, validation block at the end) over a bare file run — the appliers
  carry the extra steps (crosswalk reload, `refresh_all()` restore, sql/31 re-apply, validation)
  that a bare run misses.
- **Index ordering is load-bearing:** expression geography GiST indexes (`sql/26`) must exist
  BEFORE any spatial builder that filters `ST_DWithin(geom::geography, …)` — sql/30 ran ~15 h
  un-indexed and was cancelled; minutes once indexed. Re-run sql/26 after ANY matview
  drop-recreate; it's idempotent.
- Re-apply `sql/31_comments.sql` after any drop-recreate (comments die with the object).
- Know that `apply_erebor_locations.py` reinstalls sql/06's `refresh_all()` — which omits
  `production_forecast` and the intel views. The nightly truth is `etl/db.py:_CURATED_MATVIEWS`,
  not `refresh_all()`.

## 4. Verify live (the repo is not the database)

- Row-count sanity **by identity, not constant**: e.g. `reconciled_inventory` = exactly one row
  per mapped PUD with non-null `formation_blueox`; `wells_enriched` count == `curated.wells`.
  Remembered constants (~183k) have been wrong before.
- Key integrity: 0 duplicate / 0 NULL unique-key rows (CONCURRENTLY precondition), then a live
  `REFRESH … CONCURRENTLY` smoke with timing (`apply_erebor_locations.py:81-106` pattern).
- **EXPLAIN as an assertion**: run the real hot predicate (tile envelope / DWithin) and assert the
  named index appears — no Seq Scan. The apply scripts do this programmatically; keep the pattern.
- If a column was added for an app: `information_schema.columns` confirms it live. A committed
  apply script is NOT an applied one — this exact gap (lateral_closer_xy committed 07-14, never
  run, discovered 08-06) is the incident of record.

## 5. Propagate

- **Refresh order**: update `etl/db.py:_CURATED_MATVIEWS` if the dependency graph changed;
  quarterly-owned matviews stay OUT of the nightly list; `_OPTIONAL_MATVIEWS` and
  `_GATED_REFRESH` reviewed if the new object is optional/expensive.
- **Quarterly chain**: update the apply scripts + the `novi-quarterly-reload` skill if the
  CASCADE graph changed.
- **Comments + dictionary**: add `COMMENT ON` for new relations/columns in sql/31, then
  `python -m scripts.gen_data_dictionary --html docs/data_dictionary.html`; check the generator's
  `_QUARTERLY` set and hand-maintained `_CONSUMERS` map still match reality.
- **Downstream consumers**, checked by name:
  - anduin `warehouse_client/` (wells, production, novi_forecast, intel_forecast DTOs — new
    header columns need DTO + migration + sync),
  - erebor `backend/app` (matview references in tiles/select/highgrade/accuracy/exports),
  - narvi `src/narvi/warehouse.py` (bench menus, spacing, handoff gate, novi_rep).
  Cross-repo contract constants (per-basin rep tolerance, sql/35 semantics) change in every copy
  or none.
- **Nightly rehearsal**: `python -m etl.refresh` (add `--force` if the change bypassed the gate)
  must run green before calling it done.

## 6. Land it

- Commit on a `claude/<slug>` branch: the sql/NN file, apply-script changes, `_CURATED_MATVIEWS`
  edit, sql/31 additions, regenerated dictionary. Conventional prefix (`feat(curated):`,
  `fix(etl):`).
- `gh pr create --body-file <scratchpad>` (PS 5.1 quoting); the `etl` check must go green (it
  runs the UNIQUE-index lint). Hand Michael the PR link; he merges.
- Summary states: what changed, what was dropped/rebuilt and how long apps were dark, the
  verification evidence (counts + EXPLAIN), and the downstream tail (what must re-sync/re-save —
  e.g. anduin dev header sync, narvi scenario re-saves, Blue Ox config re-pins).

## Traps

Committed ≠ applied (verify live) · un-indexed spatial builders (15-h incident) · four competing
`refresh_all()` bodies · CASCADE killing `wells_enriched` invisibly (sql/20) · matview comments
lost on drop-recreate · `REFRESH CONCURRENTLY` on a never-populated matview (needs WITH DATA
first) · renaming `meta.etl_log` labels (breaks the refresh gate + Enverus cursor) · deletions
never trip the refresh gate (`--force`) · editing generated sql/02/03 by hand · touching
`narvi.*` · running the apply during the nightly window · declaring done from repo state.
