---
name: novi-quarterly-reload
description: Run the quarterly Novi Intelligence reload from the Snowflake share — raw_intel load, curated CASCADE rebuild in the fixed order, verification. Use when the nightly intel_sf.report_check flags a new report, or the user asks to reload/refresh the Novi Intelligence vintage.
---

# Novi Intelligence quarterly reload (Snowflake share)

The intel data loads from the Novi INTEL Snowflake share into `raw_intel`
(sql/27 mirror), then the curated layer rebuilds via a CASCADE chain whose
order is load-bearing. The legacy file-drop path (`load_novi_intel`) is
retired — it now only loads the overlay geometries (step 6).

**Hard rules before starting:**
- Every step below that touches Supabase is DDL or a bulk write — get explicit
  user authorization for the reload as a whole AND run it off-hours: the
  CASCADE rebuild drops `erebor_locations` (erebor map goes dark until the
  final step) and the forecast load is ~50 min of heavy IO.
- Trigger is the nightly `intel_sf.report_check` warning (notify-only). The
  reload itself is always manual on user go-ahead.
- Snowflake creds: `SNOWFLAKE_*` in `.env` (PAT used as password — the reader
  account rejects the native PAT authenticator). If auth fails, the PAT likely
  expired; the user rotates it in the Novi reader account.

## 1. Profile the new vintage (read-only)

```powershell
python -m etl.intel_sf.profile
```

Review the report (`logs/intel_sf_profile_<date>.md`): forecast still monthly
30-day steps / P50-only; EUR horizon still `EUR_*_30YR` only; IRR units
(sql/29's slice-median calibration self-heals if Novi fixes the mixed-unit
bug); formation strings not in `ref.formation_crosswalk` (add or rely on
tier-2 inference before the rebuild); pad_name coverage (Delaware
BASE_CASE-only as of 2025Q3 — a known share gap raised with Novi).

## 2. Load the new report slices into raw_intel

```powershell
python -m scripts.load_intel_sf --all --report <report_name>   # core+ml+econ+arps, per report
```

Run once per new report (Delaware + Midland collections). Loads are
DELETE-slice-then-COPY per (view, report_name) — idempotent, resumable per
view. Verify per-view landed counts vs Snowflake in the load log /
`meta.etl_log`; a silently-short count can be the row-access policy hiding
rows (entitlement lapse), not missing data.

## 3. Drift gate (optional but recommended)

```powershell
python -m scripts.reconcile_intel_sf     # builds qa.intel_locations_sf (DDL in qa schema)
```

qa (new vintage per sql/29's latest-report logic) vs `curated.intel_locations`
(live vintage) = quarter-over-quarter drift report. Review with the user
before cutover; drop the `qa` schema afterward.

## 4. Forecast load (big — off-hours)

```powershell
python -m scripts.load_intel_sf --forecast --report <report_name>
```

~73M rows / ~50 min. **Disk check first:** `raw_intel.production_forecast` is
~16 GB per vintage. Retention policy of record (Michael, 2026-09-18): the
superseded vintage is TRIMMED, not deleted — step 8 below keeps its accuracy
core (all core/arps slices + forecast mop <= 24, ~1 GB) so
`curated.intel_forecast_accuracy_vintage` (sql/43) keeps scoring it as actuals
accrue, and drops the long-horizon bulk so the database stops growing
vintage-over-vintage. Full deletion of a vintage remains irreplaceable and
Michael-only (removes it from the accuracy record permanently).

## 5. Curated CASCADE rebuild — FIXED ORDER (see memory: quarterly-rebuild-cascade-order)

sql/29 CASCADE-drops the whole intel matview chain (`intel_formation_blueox`,
`reconciled_inventory`, `net_new_pdp`, `intel_pdp_support`,
`intel_forecast_accuracy`, `intel_pad_geom`, `erebor_locations`); sql/20 inside
apply_reconciled_inventory additionally kills sql/23 + `wells_enriched` +
`codev_context` (sql/46) + `intel_forecast_accuracy_vintage` (sql/43; restored
by apply_intel_forecast_accuracy below) — the script rebuilds sql/23 +
wells_enriched + codev_context in order (keep that if it's ever refactored).

```powershell
python -m scripts.load_intel_sf --curated              # sql/29: intel_locations/arps/forecast
python -m scripts.apply_intel_pad_geom                 # sql/45: pad polygons from stick hulls (erebor Highgrade)
python -m scripts.apply_intel_formation_blueox         # sql/19
python -m scripts.apply_reconciled_inventory           # sql/20 -> sql/23 -> wells_enriched -> sql/46 -> sql/21
python -c "from scripts.load_intel_sf import run_sql_file; run_sql_file('25_net_new_pdp.sql')"
python -m scripts.apply_intel_pdp_support              # sql/30 — must precede erebor_locations
python -m scripts.apply_intel_forecast_accuracy        # sql/38 + sql/43 (self-applies sql/26 first)
python -m scripts.apply_erebor_locations               # FINAL step; restores refresh_all()
python -c "from scripts.load_intel_sf import run_sql_file; run_sql_file('26_geography_indexes.sql')"
```

sql/26 is non-negotiable after any matview drop-recreate: without the
expression geography indexes, `ST_DWithin(geom::geography, ...)` seq-scans and
erebor/narvi go multi-second per query. It is safe (idempotent) to run sql/26
immediately after `--curated` instead of last — and if `curated.wells` was
ALSO dropped (not the quarterly case; see sql/32), its geography index MUST be
recreated before sql/23 / sql/30 run, or those builds seq-scan for hours
(sql/30 was cancelled at ~15 h on 2026-07-14; minutes once indexed).

## 6. Overlay geometries (only if Novi shipped new shapefiles)

The share carries no DSU pad / land grid / basin outline geometry. If Novi
delivered updated shapefiles (outside the share): update `REPORT_VERSION` +
`BASIN_DIRS` in `etl/novi_intel/paths.py`, then

```powershell
python -m scripts.load_novi_intel --shapefiles
```

Otherwise the frozen 3Q25 trio in `raw_novi_intel` stays.

## 7. Verify

- `python -m etl.refresh --force` green (includes `erebor_locations`).
- Row-count sanity: `intel_locations` ~252k (grows with vintage),
  `reconciled_inventory` = the mapped-PUD universe exactly (~131k as of
  2026-07; one row per PUD with non-null formation_blueox — verify the
  identity, not the constant), `erebor_locations` ~262k, `intel_pdp_support`
  ~204k (= PUD+RES universe).
- EXPLAIN the erebor tile query (pattern in `apply_erebor_locations.py`) —
  must show the GiST/geography index, not a seq scan.
- Load the erebor map + narvi inventory page against the live warehouse.
- Next nightly `intel_sf.report_check` auto-acknowledges the watermark once
  the report_name appears in `raw_intel.well_master` — the alert clears
  itself; no manual ack.

## 8. Trim the superseded vintage (retention policy, after verification)

```powershell
python -m scripts.trim_superseded_vintage --all-superseded --dry-run   # counts first
python -m scripts.trim_superseded_vintage --all-superseded
```

Deletes the superseded vintage's forecast rows with mop > 24 (chunked, with
settle() pauses; verifies the sql/43 accuracy grain is untouched by refreshing
it and comparing per-vintage direct-well counts; plain VACUUM at the end makes
the freed pages reusable for the NEXT reload instead of growing provisioned
disk). Everything else (core slices, arps, forecast mop <= 24) stays, so the
vintage keeps scoring in `intel_forecast_accuracy_vintage`. Known effect: the
anduin dossier prior-vintage overlay for a TRIMMED vintage shows 24 months of
forecast + the anchored Arps tail (levels right, shape approximate past 2 yr).
