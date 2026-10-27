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
                                                      #   + re-creates curated.box_scout_locations (sql/69 view, CASCADE victim of sql/22)
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

## 9. BOX refresh (after step 7 verifies; plan step 13, D123 / D124 / D125 / D126)

BOX (schemas `box` / `box_econ`, app-owned; the ETL never touches them) forecasts every in-extent Delaware PUD of the 13
record groups (WCA, BS2_S, WCXY_WCA1, WCB_1, WCC, AVA_0/1/2, BS1_S, BS2_C, BS3_C, BS3_S, WCB_2) with the r2 analog workup
(D121), the proximity layer (D113 / D116) and water (D107-D110). A new Novi vintage changes the PUD universe and the stick ids,
so BOX produces ONE new record run on top of the reloaded `intel_locations` / `reconciled_inventory`. The refresh contract is
D126 (`docs/box/step13a-2026-10-26/CONTRACT.md`). **Every write below needs its own explicit go, separate from the reload's.**
One record run PER BASIN (D130, sql/70): the chain below refreshes the Delaware record (`--basin delaware`, the default); it never
reads or touches another basin's record. The Midland record joins this chain at BOX step 23.

0. **Is it due? (read-only)** `python -m scripts.box_refresh check`: a new vintage, or the record's production-through lagging the
   warehouse by more than 4 months (D126 safety net), plus the extent re-review trigger per group (>= 10 producers first
   producing after the extent was stored, outside it within 2 mi). A due extent re-review is its own step (step-3 method +
   geology, D28), before the build. `python -m scripts.box_refresh plan --pool <dir> --out runs/<label>` prints the chain below
   with the exact commands.
1. **Analog pools, all 13 groups (read-only, ~1 min; D84 / D126):**
   ```powershell
   python -m scripts.box_pool_refresh --dry-run      # classify + print per pool, write nothing
   python -m scripts.box_pool_refresh                # writes docs/box/pool-YYYY-MM-DD/
   ```
   - ONE directory holds all twelve `wells_final_<pool>.csv` (WCXY rides WCA): each = its base file byte-for-byte + the wells
     never judged before that the class rule puts in that pool. Old wells are never re-decided: a tag change on an existing
     well reaches BOX only through a 13e tag release (warehouse first, then a diff applied to every pool).
   - Base = the newest `docs/box/pool-*` refresh; a pool it lacks (the first all-pool refresh) starts from its step-15 set.
   - The log must say `identity OK` for every pool. Review `index.html` (per-pool table, map of the added wells, the
     not-re-decided and drift counts) and get Michael's confirmation of the added wells. Then commit the directory.
2. **Builds (read-only, ~8 h, resumes per group):** from a clean, committed checkout,
   ```powershell
   python -m scripts.box_refresh build --pool docs/box/pool-YYYY-MM-DD --out runs/<label> [--workers 14]
   ```
   It runs `box_pud_run build --selection r2 --wells <pool> --benches <13 groups>` (every group reads its set from the pool
   directory) and then `box_water_run build` (water follows the run's data-through and well sets; no pin to bump). Check:
   universe = the vintage's PUD count; harness equivalence 0.0 on every group; any `not_covered_no_analogs` reported.
   The evidence pack (haircut, disclosure) is the frozen `r2_evidence.json` between annual re-scores (D126: each Q1).
   Spacing (`wells_enriched.lateral_closer_xy_ft`) is read LIVE at build time (D137): Novi rewrites it nightly, so report in
   the refresh findings how many pool wells' values changed since the previous refresh (method: 13b FINDINGS §3c).
3. **Store the base run as record (WRITE, go):** `python -m scripts.box_pud_run store --out runs/<label> --record`. The D73 /
   D83 crosswalk carries locations forward (the log prints carried / new / stopped). Identity checks run before COMMIT.
4. **Water on it (WRITE, go):** `python -m scripts.box_water_run store --out runs/<label>_water --run-id <base>`.
5. **Proximity re-measure (read-only, D116):**
   `python -m scripts.box_step16d prox-measure --run-id <base> --box-db live --out runs/<label>_prox --links-out runs/<label>_prox_links`.
6. **Proximity record (WRITE, go):** `python -m scripts.box_prox_record store --src-run <base> --outcomes
   runs/<label>_prox/pud_outcomes.csv.gz --runs runs/<label>_prox_links` (rollback rehearsal), then the same with
   `--commit --record`. The derived run becomes the record.
7. **Verify live, read-only:** one `is_record` run per basin (the new Delaware one); per-stream counts and oil MMbbl as the log; `analyst_ro` reads; erebor
   shows the new run.
8. **Prune (WRITE, go; D123 / D130):** `python -m scripts.box_prune_runs --apply --include-priced --basin delaware` keeps ONLY the
   basin's record run and
   deletes a priced run's `box_econ.box_pud_econ` rows first, in one transaction.
9. **Steven:** post the new record run_id to #eng-updates (its own go; no email) so he re-prices; check
   `box_econ.box_pud_econ_tie` and `downtime_basis` (D63 / D81) after he loads.
10. **Prospective tests (never re-tuned):** D125 (`box/prospective16.py`, 13 groups) is judged ONCE when production runs
    through >= 2028-01-01 (cum-12) / 2029-01-01 (cum-24); early reads are reported only. D85 (`box/prospective.py`, WCA) is
    informational. `python -m scripts.box_prospective16 status`.
