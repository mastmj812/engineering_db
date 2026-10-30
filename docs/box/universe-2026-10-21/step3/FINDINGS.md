# D117 step 3: the BOX universe takes PUD + RES, rehearsed in a container. AT THE STEP-3 GATE (nothing written live)

2026-10-30. Plan: `../AUDIT.md` "Steps" row 3; decisions D1 / D67 (amended by D117), D116, D135, D137.
Trigger: gate 20a ask 6 (`docs/box/step20a-2026-10-26/FINDINGS.md` §4 item 6, §8.18). Michael, 2026-10-30: the BOX universe is
"every category, BASE_CASE or UPSIDE, as long as it's inside the BOX extent".

**Nothing was written to Supabase.** Every store below went into the throwaway `scripts.box_rehearsal` container (seeded
read-only from live `box`). Storing a record with RES rows live is step 4, on your explicit go.

## 1. The change

| file | before | now |
|---|---|---|
| `box/production._UNIVERSE_SQL` | `il.category = 'PUD'` | `il.category IN ('PUD', 'RES')` (never PDP); `il.category` is selected so runs can split by Novi tag |
| `box/production` module docstring | "D67: Novi PUD category (no RES)" | D67 / D117: PUD + RES; the extent, coverage classes and proximity layer decide coverage, not Novi's tag |

Unchanged on purpose: the reconciliation filter (`remaining_pud` / `conflict` / not yet reconciled), the basin filter, the
extent join and the ≥ 50 %-inside rule, the coverage precedence. A test pins all of these
(`tests/test_box_d117_universe.py`).

No DDL. `box.pud_forecast` has no category column; a row's Novi category is one join away (`stick_id` →
`curated.intel_locations.category`).

## 2. What the universe gains (live, read-only, 2026-10-30)

### Delaware (run 19's groups)

The universe grows from 117,542 rows (run 19, Delaware) to **166,843**: +49,301 RES. **6,219 of them are forecast candidates**,
all reconciled `remaining_pud` (6,154) or `conflict` (65):

| group | RES in extent (forecast) | class | RES outside extent | proximity re-measure (D116): unexposed / single / haircut / no-forecast | oil before → after proximity, MMbbl |
|---|---|---|---|---|---|
| WCXY_WCA1 (WCA extent, D95) | **5,055** | covered | 5,985 | 2,841 / 912 / 1,177 / 125 | 2,501.8 → 2,332.3 |
| WCC | 566 | covered | 5,944 | 398 / 105 / 0 / 63 | 245.5 → 214.2 |
| BS3_S | 495 | covered_provisional | 1,754 | 342 / 70 / 6 / 77 | 360.2 → 331.8 |
| BS3_C | 37 | covered_provisional | 3,034 | 3 / 6 / 24 / 4 | 13.8 → 10.4 |
| AVA_1 | 24 | covered_provisional | 3,511 | 17 / 4 / 0 / 3 | 15.7 → 13.9 |
| AVA_2 | 20 | covered_provisional | 814 | 12 / 3 / 0 / 5 | 13.0 → 9.4 |
| AVA_0 | 15 | covered_provisional | 1,389 | 8 / 1 / 0 / 6 | 9.1 → 5.6 |
| WCB_1 | 7 | covered | 2,297 | 5 / 1 / 1 / 0 | 4.1 → 4.1 |
| WCA (WCA_1 / WCA_2) | 0 | — | 3,057 | | |
| BS2_S, BS2_C, WCB_2 | 0 | — | 2,709 / 3,109 / 627 | | |
| WDFD, WCD (emerging, not in scope) | — | `not_covered_emerging` | 8,827 / 25 | | |
| **total** | **6,219** | | **34,230** (+ 8,852 emerging) | **3,626 / 1,102 / 1,208 / 283** | **3,163.3 → 2,921.6** |

- **No-analog RES: 0.** Every in-extent RES row found ≥ 4 named analogs (min 4, max 20).
- **Proximity:** 283 RES rows become `not_covered_no_precedent` (276 precedent + 7 package), 1,208 take an oil haircut.
- **Volumes:** EUR is the raw 50-yr technical integral × haircut (WCA / BS2_S only, D122) × proximity factor, uptime-free (D63).
- **Size of the addition:** RES adds **+2,921.6 MMbbl** of oil after proximity. That is +11.4 % on the record's 25,569.9 MMbbl
  in the rehearsal, or +12.9 % on run 19's 22,623.3. WCXY is 80 % of it.
- **WCXY RES are a different population from WCXY PUD:**
  - median oil EUR 61.5 k bbl / 1,000 ft vs 78.8 k on the 3,184 WCXY PUDs;
  - median planned spacing 881 ft (D64);
  - they sit under a planned WCA PUD in the same DSU (AUDIT §1).
- **WCXY co-development caveat (D117).** The proximity layer counts PRODUCING parents only. WCXY RES planned under planned WCA is
  not haircut, and the run disclosure must say so. That text is not built yet: it is part of step 4.
- Machine-readable: `additions.csv` (the compare, §3a), `prox/pud_outcomes.csv.gz` (every PUD, RES included).

### Midland (stored records 36–39 and 41; no Midland run yet)

`midland_universe.csv`. Inside the five stored Midland records the change adds **80 RES sticks**: WCA_1 2, WCB_1 2,
**WCD 76**. All are `remaining_pud`. With them the undrilled count is 15,982 (PUD 15,902), which matches §8.17 of the 20a
FINDINGS exactly. Today they class `not_covered_unvalidated` because no Midland production group exists until step 21.
They join the first Midland record (step 23) with everything else.

## 3. The rehearsal (container, `scripts.box_rehearsal`)

**Why a derived build and not a re-build.** Run 19 cannot be rebuilt row-for-row today, whatever the universe code:
- **Spacing:** Novi rewrites `lateral_closer_xy_ft` nightly (D137).
- **Tags:** the 10-29 override refresh re-tagged Delaware sticks and producers.
- **PDP neighbours:** new producers change D64 gaps.

So the rehearsal is built the way D116 built the proximity record: **derived from the record's own build, no refit of its
rows.** `box_pud_run augment --from runs/box16d` (run 19's build artifact):
- **Run 19's rows:** carried verbatim. Only the Delaware's are kept; run 19's 4,154 Midland BRNT rows drop per D135.
- **RES rows:** appended. They are fitted on each group's pool rebuilt at run 19's data-through (2026-07-01, cutoff 2026-08-01),
  with the same well sets, r2 selection and evidence pack (sha256 `90da3c56…`).
- **Water:** `box_water_run build --carry` reuses a run-19 water row only where its raw oil is bit-identical (51,419 of 51,419).
  It builds the 6,219 new ones (0 ratio failures, 49 calculated-fallback locations in the whole run, as before).
- **Proximity:** re-measured on the whole run (D116), then the proximity record.

| step | result |
|---|---|
| `box_pud_run augment` (read-only vs live; `runs/box_d117s3`, 8,120 s) | 9 groups refitted; **harness equivalence 0.0 on every group** (24 sampled locations each); 6,219 RES fitted; pools rebuilt at the 2026-07-01 data-through |
| `box_pud_run store --record` → container **run 24** | pud_forecast 166,843 = universe; covered 24,258 + covered_provisional 33,380 = 57,638 = in-extent universe (51,419 + 6,219), 0 no_analogs; every stream 600 months = its EUR; every location ≥ 4 named analogs. 915 s |
| `box_water_run store --run-id 24` | 57,638 water streams (validated 9,310 = WCA + BS2_S, provisional 48,328); oil / gas rows md5-unchanged; ≥ 3 water analogs each. 584 s |
| `box_step16d prox-measure --run-id 24` | 57,638 PUDs, 349,571 links, identity True; oil 31,673.5 → 25,569.9 MMbbl. `prox/` |
| `box_prox_record store --src-run 24 … --commit --record` → container **run 25** | coverage = source with 8,693 no-precedent moves (run 19: 8,449; +276 RES precedent / +7 package, plus the re-measure's net moves on run 19's rows); 48,945 forecast PUDs per stream; oil 25,569.904 MMbbl = source × factor; gas / water rows identical to the source; 88,101,000 month rows; 78,950 named parents; run 25 the one Delaware record. 1,598 s |

### 3a. Does every run-19 row reproduce? (`box_d117_step3 compare`, container run 25 vs live run 19)

`compare.json`, `differences.csv`, `additions.csv`. Read-only on both sides. Floats are compared as shortest-exact text
(`extra_float_digits = 3`): the live session prints 15 digits by default, and that alone read as 120 k false differences on the
first pass.

| table | live run-19 rows | reproduced exactly | differ | missing in the container | container-only (additions) |
|---|---|---|---|---|---|
| pud_forecast | 121,696 | 117,305 | 237 (coverage) | 4,154 (Midland BRNT, D135) | 49,301 = all RES |
| pud_forecast_stream | 128,910 | 128,230 | 383 | 297 | 18,222 |
| pud_forecast_month (md5 per location × stream) | 128,910 | 128,230 | 383 | 297 | 18,222 |
| location_analog (per location) | 42,970 | 42,871 | 0 | 99 | 6,074 |
| location_water_analog (per location) | 42,970 | 42,871 | 0 | 99 | 6,074 |
| pud_proximity | 51,419 | 0 | 51,419 | 0 | 6,219 |
| pud_proximity_parent (per location) | 25,230 | 20,414 | 4,722 | 94 | 2,708 |

**Attribution (`--prox-before / --prox-after`): every forecast-table difference is explained, 0 unexplained.**

| table | locations differing or missing | D116 re-measure moved the outcome / factor | other basin (D135) | unexplained |
|---|---|---|---|---|
| pud_forecast | 4,391 | 237 | 4,154 | **0** |
| pud_forecast_stream / month | 482 | 482 | 0 | **0** |
| location_analog / water analog | 99 | 99 | 0 | **0** |

- **How the 482 break down.**
  - 99 run-19 PUDs move INTO no-forecast (`not_covered_no_precedent`): their 3 streams and analogs leave.
  - 138 move OUT of it: they show as container-only streams and are counted under additions in the table above.
  - 383 streams change their proximity factor: the haircut moves, or a haircut appears or disappears.
- **On `pud_proximity`, all 51,419 rows differ because `table_ref` differs.** It carries the outcomes digest, which a
  re-measure changes by construction. The measured columns differ only where the parents moved.
- **On `pud_proximity_parent`,** 4,722 per-location parent sets differ: tag, TVD or geometry changes of producing parents.
- **The RES rows cannot cause any of this.** Proximity counts producing parents only (`curated.wells` with
  `first_production_date`), and RES are planned sticks.
- **Net oil on run 19's own rows: 22,623.3 → 22,648.3 MMbbl (+25.0, +0.11 %)** from the re-measure.
- **What this means:** with the re-measure set aside, run 19 reproduces exactly. Every pud_forecast row matches, and every
  stream, month and analog set matches bit for bit. The container record = run 19's rows (Delaware) + 49,301 RES universe
  rows, 6,219 of them forecast candidates.

## 4. Things that are NOT exactly "additions only" (flagged, not resolved)

1. **D64: 93 run-19 PUDs get a narrower planned gap from a new RES neighbour.**
   - D64 measures the gap to the nearest same-formation planned or producing stick. With D117 a RES stick is a planned
     location, so a fresh build would narrow these 93 gaps: 84 narrower, 9 from the 880-ft default to a measured gap.
     Median ratio 0.74.
   - Where they are: AVA_2 38, WCXY 26, BS3_S 14, WCC 6, AVA_1 4, BS3_C 3, BS2_C 1, WCB_1 1.
   - The rehearsal **carries them verbatim**. The refit is recorded in `gap_changed.csv`: oil EUR median 0.0 %, IQR −1.6 % to
     0.0 %, range −32 % to +27 %. That refit runs on today's pool, so pool drift is mixed in.
   - `augment --refit-gap-changed` takes the refits instead.
   - **DECIDED 2026-10-30 (Michael): carry the 93.** Step 4 runs `augment` without `--refit-gap-changed`, so run 19's rows
     stay untouched. Their D64 gaps catch up at the next refresh (13c), along with the drift in item 3.
2. **The analog pools drifted since run 19 (D137).** The RES rows are fitted on pools rebuilt today at run 19's cutoff, and those
   pools are not run 19's:
   - pool sizes: WCC 858 → 862, AVA_1 473 → 474, AVA_2 360 → 363, BS3_C 1,601 → 1,602;
   - 24 carried rows per group were refitted on the rebuilt pool. The augment's own pass reported a max relative difference in a
     single month of 0.14–2.5 by group.
   - In EUR terms (`reference_refit.csv`, `refit_reference.py`; WCC, BS3_S and WCXY, which hold 98 % of the RES rows; the
     full re-run died on a dropped Supabase connection, read-only, nothing written):

     | group | rebuilt / source pool | bit-identical | same analog set | raw oil EUR change: median / range |
     |---|---|---|---|---|
     | WCXY_WCA1 | 7,588 / 7,588 | 9 / 24 | 13 / 24 | 0.0 % / −8.8 to +13.6 % |
     | WCC | 862 / 858 | 16 / 24 | 18 / 24 | 0.0 % / −5.2 to +14.2 % |
     | BS3_S | 2,844 / 2,844 | 9 / 24 | 17 / 24 | 0.0 % / −19.2 to +7.5 % |

     Overall, 52 of 72 rows land within ±1 % on oil.
   - So the RES rows are on a pool about one week newer than the PUD rows beside them. Same method, same well sets, same
     cutoff; different live spacing and tags.
3. **Live drift in run 19's own universe (counted, not applied).** Today's live universe differs from run 19's on PUD rows:
   - 282 run-19 PUDs are no longer in the universe (realized or re-tagged off the bench);
   - 109 live PUDs are not in run 19;
   - 1,348 are re-classed: tag, bench, reconciliation status or coverage. 1,129 are tag swaps from the 2026-10-29 override
     refresh (WCB_1 ↔ WCB_2 732, WCA_1 ↔ WCA_2 397).
   - The derived run keeps run 19's universe rows as built, and the next refresh (13c) absorbs this drift. A record "built
     today" would not.
4. **Proximity re-measure on run 19's PUDs moves 601 outcomes** (factor on 792, final oil on 620).
   - Proximity counts producing parents only, so this is not the RES rows. It is live drift in the parents: the 10-29
     override refresh re-tagged parent benches (e.g. BS3_S → BS3_C, WCA_1 ↔ WCA_2), plus nightly tag drift.
   - D116 says re-measure on every record run. The step-4 record therefore changes these run-19 rows **because of D116, not
     D117**. The alternative is to carry run 19's committed outcomes for its own rows; that needs a small change to
     `box_prox_record` and is not built.
   - **DECIDED 2026-10-30 (Michael): re-measure per D116.** Step 4 runs `box_prox_record` as rehearsed (run 25): all
     run-19 rows are re-measured on today's parent tags. That is 601 outcome moves and +25.0 MMbbl on run 19's rows
     (22,623.3 → 22,648.3). The step-4 provenance and Steven's note must attribute this to D116, not D117. No code change.
5. **Step 4 shape (your call):**
   - **(a) the derived record rehearsed here:** run 19 + RES, about 2 h of build plus about 2 h of store;
   - **(b) a full 13c-style refresh** at the current data-through: about 8 h build. It absorbs items 1–4 and moves every
     group by about ±2 % (13b).
   - Recommendation: **(a)**. It isolates D117, keeps Steven's price on run 19's rows meaningful row for row, and leaves
     the drift to 13c, where the refresh tooling reports it.

## 5. The two other PUD-only spots (decided; say if you want either reverted)

- **`box/family_extent` Delaware extent pages: now count the D117 undrilled universe (PUD + RES, by category), like the Midland's.**
  - Before, the Delaware pages counted D1 PUDs only. That number is now stale as a statement of what BOX forecasts.
  - Two places changed: the run's summary and the loop-edit diff pages. The default heading now says D117.
  - Not changed: `box/extent_report.pull_puds / pud_counts / _PUD_SQL` and `scripts/box_extents_import`. They are the
    step-3/4-era Delaware tooling behind pages of record, and nothing current calls them for new work. Their "D1 universe"
    label is historical.
- **`scripts/box_update_deck`: accepts PUD + RES, still refuses anything else (PDP).**
  - Read-only check: Novi publishes a forecast for RES sticks through the same `planned_well → production_forecast` join
    (40 of 40 sampled covered RES sticks).
  - So the deck compares any BOX location with Novi's forecast of the same stick. `frame.csv` carries the category for a
    BASE_CASE / UPSIDE split.
  - On a run-9 artifact the output is unchanged (every row is PUD).

## 6. Other flags

- **Two §2 rows are numbered D117** in `docs/box_type_curves_plan.md`: the run-10 prune (2026-10-21) and the universe
  decision. Not renumbered here, because only one session edits §2. Suggest the prune row become D117a, or take the next free
  number.
- **erebor:** once a record carries RES rows, RES sticks inside BOX extents on BOX benches read their BOX class instead of
  `not_screened`. This is the D117 intent. Nothing in erebor changes code-wise (it keys on location / stick).
  `curated.box_scout_locations` (sql/69) picks them up when Steven prices them.
- **Steven** re-prices after step 4. That run has about +6.2 k forecast locations.

## 7. How to verify / reproduce

```
python -m pytest -q tests/test_box_d117_universe.py            # universe SQL, augment merge, water carry, compare (DB-free)
python -m scripts.box_d117_step3 midland                         # Midland RES inside the stored records (read-only)
python -m scripts.box_rehearsal up && python -m scripts.box_rehearsal seed
python -m scripts.box_pud_run augment --from runs/box16d --out runs/box_d117s3 --workers 14          # read-only, ~2.3 h
# DB_* -> the container (scripts.box_rehearsal env) for the four stores:
python -m scripts.box_pud_run store --out runs/box_d117s3 --record
python -m scripts.box_water_run build --run-pkl runs/box_d117s3/run.pkl --out runs/box_d117s3_water --carry runs/box16d_water --carry-run runs/box16d
python -m scripts.box_water_run store --out runs/box_d117s3_water --run-id <base>
python -m scripts.box_step16d prox-measure --run-id <base> --prec-runs <abs path>/runs/prox --out docs/box/universe-2026-10-21/step3/prox --links-out runs/box_d117s3_prox
python -m scripts.box_prox_record store --src-run <base> --outcomes docs/box/universe-2026-10-21/step3/prox/pud_outcomes.csv.gz --runs runs/box_d117s3_prox --commit --record
python -m scripts.box_d117_step3 compare --run-id <record>       # container vs live run 19, read-only both sides
```

- Tests: full suite 784 passed, 46 skipped (`tests/test_box_d117_universe.py`: 10 new).
- Ruff: clean on every touched file.
