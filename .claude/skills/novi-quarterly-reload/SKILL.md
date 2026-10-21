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
`intel_forecast_accuracy`, `intel_pad_member`, `intel_pad_geom`, `erebor_locations`); sql/20 inside
apply_reconciled_inventory additionally kills sql/23 + `wells_enriched` +
`codev_context` (sql/47) + its `dev_scenario` view (sql/50) + `intel_forecast_accuracy_vintage` (sql/43; restored
by apply_intel_forecast_accuracy below) — the script rebuilds sql/23 +
wells_enriched + codev_context + dev_scenario in order (keep that if it's ever refactored).

```powershell
python -m scripts.load_intel_sf --curated              # sql/29: intel_locations/arps/forecast
python -m scripts.apply_intel_pad_geom                 # sql/67: pads = Novi DSU polygons of this vintage (+stray hulls); erebor Highgrade
python -m scripts.apply_intel_formation_blueox         # sql/19
python -m scripts.apply_reconciled_inventory           # sql/20 -> sql/23 -> wells_enriched -> sql/47 -> sql/50 -> sql/68 (every Novi stick, D117; sql/21 retired)
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

The share carries no DSU pad / land grid / basin outline geometry; Novi ships
them as shapefiles outside it.

**DSU pad polygons — every vintage.** sql/67 takes a pad's polygon only from
`raw_novi_intel.pads` rows whose `report_version` equals the share's
(`curated.intel_locations.report_version`, e.g. '2026Q3'). Until the new
vintage's pads are loaded, every pad falls back to derived stick hulls
(`member_rule = no_polygon_cluster`) — Highgrade still works, on hulls. Once the
drop is on SharePoint (`Novi Intelligence\<Basin>\<NQYY>`, outer
`shapefile*` zip holding a `*Pad*Summary*Mid_Cycle*.zip`):

1. Point `PADS_REPORT_VERSION` + `PADS_BASIN_DIRS` in `etl/novi_intel/paths.py`
   at it (commit on a branch).
2. Run (DB write — explicit go):

```powershell
python -m scripts.apply_intel_pad_geom --load-pads   # sql/66 + load ALL polygons + sql/67 rebuild + validate
```

It refuses when the pad label != the share's vintage, and checks loaded rows ==
shapefile records. All polygons load (WellCnt = 0 included — Novi's Pad Summary
counts only NPV25 >= 0 wells): `raw_novi_intel.pads` is the DSU geometry of
record. Expect strays to be off-scope benches (2026Q3: Delaware WDFD name
reuse; Midland BRNT names without a polygon) — new benches in that list are a
finding to raise with Novi.

**Land grid / basin outline** (only if Novi re-ships them): update
`REPORT_VERSION` + `BASIN_DIRS`, then `python -m scripts.load_novi_intel
--shapefiles` (also reloads pads; re-run `apply_intel_pad_geom` after).
Otherwise the 3Q25 land grid + outline stay.

## 7. Verify

- `python -m etl.refresh --force` green (includes `erebor_locations`).
- Row-count sanity: `intel_locations` ~252k (grows with vintage),
  `reconciled_inventory` = the mapped Novi STICK universe exactly — PUD + RES
  since D117 / sql/68 (2026-10-21), one row per stick with geometry and a
  non-null formation_blueox; verify the identity, not a constant, `erebor_locations` ~262k, `intel_pdp_support`
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

## 9. BOX refresh (after step 7 verifies; plan step 7, D58 / D67 / D73 / D76)

BOX (schema `box`, app-owned; the ETL never touches it) forecasts every in-extent WCA PUD with the frozen analog
workup `box_v2_wf`. A new Novi vintage means new stick ids and new PUDs, so BOX re-runs on top of the reloaded
`intel_locations` / `reconciled_inventory`. Every write below needs its own explicit go, separate from the reload's.

1. **Analog pool well set — D84 refresh (read-only, ~1 min).** `build` reads a `wells_final_WCA.csv` directory. New
   producers enter the pool only through a refreshed set: bench QC + the class rule of record
   (`box/bench_qc.py` consensus detector, `box/qc_rule.py`) **on wells never judged before, no calibration cards**:
   ```powershell
   python -m scripts.box_pool_refresh --dry-run      # classify + print, write nothing
   python -m scripts.box_pool_refresh                # writes docs/box/pool-YYYY-MM-DD/
   ```
   - Base defaults to the newest `docs/box/pool-*` refresh, else the gate-1 set (`docs/box/step1-2026-10-06`).
     "New" = not in the base's `universe.csv` (the gate-1 universe was not recorded, so the first refresh reconstructs
     it once; see `box/pool_refresh.py`). Never re-run `box_apply_rule` over the whole set: re-deciding old wells
     churns ~1 % each way and re-litigates gate 1.
   - The log must say `identity OK` (the base file is a byte-identical prefix of the new one; BS2_S copied unchanged).
   - Review `docs/box/pool-YYYY-MM-DD/index.html` (map of the added wells + flag classes; ruled-out and not-re-decided
     wells listed) and get Michael's confirmation of the added wells before the build. Watch for new
     `uncalibrated` classes (tag kept, no cards) and new rows already in `docs/box/exclusions.csv` (dropped at load).
   - Commit the directory, then build with `--wells docs/box/pool-YYYY-MM-DD`. The run stamps `wells_dir`.
2. **Build (read-only, ~40 min):** from a clean, committed checkout (the run stamps the HEAD SHA; `--record` refuses a
   dirty build):
   ```powershell
   python -m scripts.box_pud_run build [--wells <dir>]
   ```
   Check the log:
   - `universe` = the D67 count for the new vintage;
   - the harness equivalence `max_rel_diff` is 0.0 (the build refuses otherwise);
   - `covered with forecast` vs candidates — any shortfall is `not_covered_no_analogs` (D74), and it gets reported.
3. **Store (WRITE to Supabase, explicit go):**
   ```powershell
   python -m scripts.box_pud_run store --record
   ```
   - The D73 crosswalk carries locations forward from the most recent earlier vintage: same basin + formation_blueox,
     ≥ 50 % of the shorter stick within 250 ft, 1:1, greedy by share. The log prints `carried` / `new`.
   - Storing an older vintage than one already stored is refused.
   - Identity checks run before COMMIT: rows = universe; covered + no_analogs = the in-extent WCA_1 + WCA_2 universe;
     600 months per stream summing to EUR.
3b. **Water on the new record run (D107 / D108 / D110; sql/62).** `box_pud_run store` writes oil + gas only. Add the water
   stream, built from the same run artifact (read-only build, then a WRITE on the explicit go):
   ```powershell
   python -m scripts.box_water_run build --run-pkl runs/<run>/run.pkl --out runs/<run>_water
   python -m scripts.box_water_run store --out runs/<run>_water
   ```
   - The build refuses a run whose data-through differs from the water spec's `water11.LAST`. On a new vintage that pin
     moves with the run: bump it in a reviewed commit, never silently.
   - The store's identity checks run before COMMIT:
     - oil / gas rows unchanged (ordered md5);
     - one water row per covered + covered_provisional location;
     - 600 months summing to EUR;
     - validated water = the WCA + BS2_S `covered` rows;
     - ≥ 3 named water analogs per location.
4. **Verify live, read-only:**
   - one `is_record` run;
   - coverage counts match the log;
   - `analyst_ro` reads `box.pud_forecast_month`.
5. **Render** the review pages (`python -m scripts.box_pud_run render`). The DB is the record; pages are renders (D80).
6. **Steven:** the record `run_id` changed, so his `box_econ.box_pud_econ` rows for the old run stay attached to it. That
   run can't be deleted while priced. Tell him the new run_id, and before first pricing confirm `downtime_basis` (D63 / D81).
   Check `box_econ.box_pud_econ_tie` after he loads.
7. **Prospective confirmation (D59 condition 1 / D70):** when the frozen cohort's horizons have data, score it with
   `python -m scripts.box_prospective score` (definition frozen in `box/prospective.py`). Rules unchanged.
