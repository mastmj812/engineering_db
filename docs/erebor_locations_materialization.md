# Materializing `curated.erebor_locations`

**Status:** proposed — for review before applying to Supabase.
**Author:** drafted 2026-06-29.
**Trigger:** erebor map felt sluggish after the laptop → Supabase (AWS us-east-1) cutover.

## Problem

`curated.erebor_locations` is a plain `VIEW` — a 7-relation join
(`intel_locations` + `intel_formation_blueox` + `reconciled_inventory`
`UNION ALL` `wells_enriched` + `net_new_pdp`) — and erebor's vector-tile endpoint
hits it **once per tile**, dozens of tiles per pan/zoom. On the local laptop DB the
join was cheap over a unix socket; on hosted Postgres it is not.

Measured live against Supabase (us-east-1), Delaware basin:

| Query | Time | Note |
|---|---|---|
| `SELECT 1` | 36 ms | network round-trip floor, per tile |
| scan `intel_locations` (matview) | 48 ms | indexed base |
| scan `erebor_locations` (the view) | **656 ms** | the join adds ~600 ms |
| one map tile (current view + old predicate) | ~390–565 ms | × dozens/pan |
| one map tile (after the in-app predicate fix) | ~75–166 ms | already shipped¹ |

¹ A companion fix in erebor (`tiles.py`) stopped wrapping the geometry *column* in
`ST_Transform` (which defeated the GiST index); that alone took tiles from ~534 ms
to ~36–166 ms. Materializing removes the **remaining** join cost so the matview
scans like `intel_locations` (~40–75 ms/tile, all index hits).

`erebor_locations` has **no DB-side dependents** (only the erebor app reads it), and
`stick_id` is **unique across both arms** (Novi ids positive, PDP ids `-(api10)`;
verified 0 dupes / 0 nulls over 262,581 rows) — so it can carry a `UNIQUE` index and
refresh `CONCURRENTLY`.

## The change (3 files)

1. **`sql/22_erebor_locations.sql`** — `VIEW` → `MATERIALIZED VIEW`, same SELECT
   body, `WITH DATA`, plus indexes:
   - `UNIQUE (stick_id)` — required for `REFRESH … CONCURRENTLY`
   - `GIST (wellstick_geom)` — the per-tile AOI filter (the whole point)
   - `(basin, category)`, `(unique_id)`, `(basin, formation_blueox)`, `(basin, recon_status)`
   - A type-aware `DO` block drops the old VIEW on first apply (because
     `DROP MATERIALIZED VIEW IF EXISTS` does **not** suppress a wrong-type error),
     then `DROP MATERIALIZED VIEW IF EXISTS` makes re-runs idempotent.
2. **`sql/06_curated_derived.sql`** — append
   `REFRESH MATERIALIZED VIEW CONCURRENTLY curated.erebor_locations` as the **last**
   step of `curated.refresh_all()` (wrapped in a `BEGIN … EXCEPTION WHEN
   undefined_table` guard so a mid-quarterly-rebuild gap degrades to a notice).
3. **`scripts/apply_erebor_locations.py`** — runs (1), re-applies `refresh_all()`
   from (2), and validates (relkind, category counts, uniqueness, a `CONCURRENTLY`
   smoke test, and an `EXPLAIN` confirming the tile query rides the GiST index).

## Refresh orchestration — two cadences

`erebor_locations` spans two arms that move on **different** schedules:

- **PDP arm** (`wells_enriched`) changes **nightly** as wells come online.
- **PUD/RES arm** (`intel_*`, `reconciled_inventory`, `net_new_pdp`) changes
  **quarterly** with the Novi Intelligence reload.

So:

**Nightly** — `etl.refresh` → `curated.refresh_all()`. The appended
`REFRESH … CONCURRENTLY` re-runs the UNION against the just-refreshed wells side and
folds in new producers. `CONCURRENTLY` means the erebor app keeps reading during the
refresh. (Cost: re-runs the ~0.6 s join + writes 262 k rows + index diff — a few
seconds; negligible in the nightly window.)

**Quarterly** — the Novi reload runs
`DROP MATERIALIZED VIEW curated.intel_locations CASCADE`, which **drops
`erebor_locations` too** (it did with the view; it does with the matview). The
rebuild sequence must therefore **end** by recreating it:

```
python -m scripts.load_novi_intel --curated      # intel_locations
python -m scripts.apply_intel_formation_blueox    # intel_formation_blueox
python -m scripts.apply_reconciled_inventory      # producing_reference + reconciled_inventory
# (net_new_pdp rebuild)
python -m scripts.apply_erebor_locations          # <-- NEW canonical last step
```

> Note: this last step is **already required today** for the view (the CASCADE drop
> leaves `erebor_locations` gone until sql/22 is re-run) — it was just implicit. This
> change makes it an explicit, validated script.

## Rollback

Low-risk and fully reversible:

1. `git revert` the three files.
2. Re-run the old `sql/22` (recreates the plain VIEW) and the old `refresh_all()`
   from `sql/06` — e.g. `python -m scripts.apply_erebor_locations` after the revert,
   or apply the two blocks by hand. `DROP MATERIALIZED VIEW IF EXISTS … CASCADE`
   followed by `CREATE VIEW` is clean because nothing else depends on it.

The erebor app is unaffected either way — same object name, same columns, SELECT-only.

## Risks & considerations

- **Staleness window.** The map is no longer real-time against `wells_enriched`; new
  producers appear after the nightly refresh (≤ 24 h). Acceptable for an
  inventory/screening app; the data is otherwise quarterly. Flag if any workflow
  needs intraday PDP freshness.
- **`CONCURRENTLY` requires the unique index + an existing populated matview.** Both
  hold after sql/22. If the matview is dropped (quarterly CASCADE) and `refresh_all()`
  runs before `apply_erebor_locations`, the `EXCEPTION` guard skips it with a notice
  rather than failing the nightly run.
- **2 GB Supabase RAM is *not* the main lever.** Every measured query hit warm cache
  (shared hits, no disk reads); materializing helps far more than more RAM would. RAM
  still matters for cold-start resilience — worth bumping, but separately.
- **Further latency wins (out of scope here):** raise the tile `Cache-Control`
  max-age (tile data is static per vintage) and/or co-locate the erebor backend in
  us-east-1 so backend↔DB drops from 36 ms to ~1 ms.

## Go-live checklist

- [ ] Review the three diffs.
- [ ] `python -m scripts.apply_erebor_locations` against Supabase.
- [ ] Confirm validation output: `relkind='m'`, category counts ≈ PDP 58.7k / PUD
      131.5k / RES 72.4k, `duplicates=0 nulls=0`, CONCURRENTLY smoke test ok, tile
      query `uses GiST index: True`.
- [ ] Load the erebor map; confirm pan/zoom is snappy and sticks/legend/gun-barrel
      render unchanged.
- [ ] Run `python -m etl.refresh` once; confirm `refresh_all()` completes including
      `erebor_locations`.
- [ ] Add `apply_erebor_locations` as the final step of the quarterly Novi-reload
      runbook.
