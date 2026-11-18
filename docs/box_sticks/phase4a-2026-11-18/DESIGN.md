# BOX sticks phase 4a: storage and identity, design for review

2026-11-18. Read-only. **No SQL applied, nothing written to the warehouse.** Plan: `docs/box_sticks_plan.md`, phase 4.
Branch `claude/box-sticks-phase4`, cut from main at `e7bc69c` (PR #247 merged 2026-11-18).

Files here: `ddl_draft.sql` (the draft DDL, not on the apply path), `crosswalk_*.csv|json` (the id scheme measured),
`box/sticks/identity.py` + `tests/test_box_sticks_identity.py` (the crosswalk, 10 tests),
`scripts/box_sticks_phase4_identity.py` (the measurement).

## 1. What is live today (read 2026-11-18)

| Object | State |
|---|---|
| `box.location` | 252,925 rows, all Novi 2026Q3 seeds (Delaware 167,070, Midland 85,855); `location_id` 4 to 252,947 |
| `box.location_source` | 252,925 rows, `match_method = 'seed'`; Novi `stick_id` 1,531,428 to 1,824,903 |
| `box.forecast_run` | 2 rows, both records: run 30 (Midland), run 32 (Delaware) |
| Foreign keys onto `box.location` | `location_source`, `pud_forecast` only. `box_econ` has no FK into `box` |
| `raw_novi_intel.pads` | 16,585 polygons at 2026Q3 (`pad_id` unique in the vintage); 9,040 at 3Q25 |
| Tag switch | ON since 2026-11-16 19:58 UTC; latest rule run 8 (2026-11-18 11:20 UTC) |

Every reader of `box.location` goes through `box.pud_forecast` (run-scoped), with one exception that matters:
`scripts/box_pud_run.py:759` carries Novi ids forward with `FROM box.location WHERE last_seen_vintage = <previous vintage> AND
basin = ...`. If our sticks carried a Novi vintage label, the next Novi-universe store would try to match Novi sticks onto
them. The draft keeps the vintage columns NULL on our rows and 4b adds `source = 'novi'` to that query.

## 2. Draft DDL (`ddl_draft.sql`)

Additive only. Five new tables, six new columns on `box.location`, nothing dropped or re-pointed.

| Object | Grain | Rows per stored pair of basins | Holds |
|---|---|---|---|
| `box.location_set` | one generation run per basin | 2 | generator version, code and narvi SHAs, DSU vintage, pull time, tag run, every threshold, input manifest with digests, counts, back-test verdicts (failures included), `is_record` (one per basin) |
| `box.location` (+6 columns) | one location, for good | about 80,500 new | `source`, `dsu_vintage`, `pad_id`, `slot_no`, `first_seen_set`, `last_seen_set` |
| `box.location_stick` | stick x set | 80,481 | legs and turn geometry, well type, completed and drilled lateral, azimuth (true and grid) + basis, gunbarrel offsets, target TVD, rung, anchor bench(es), held-out median and P90, reconciled shift, second-level TVD, spacing as placed + map value + basis, flags, how the id was matched |
| `box.location_set_dsu` | DSU x set | 9,457 | azimuth and basis, WCA class, well type, clear width, `drilled_across` |
| `box.location_set_bench` | DSU x bench x set | 49,554 | the generator's input per bench (depth, rung, anchors, errors, spacing basis) and its outcome (no-row reason, rows culled by reason, sticks) |
| `box.location_set_well` | well x set | about 64,400 | the wells the generator read: tag at the pull, depth evidence used, status, geometry |

Counts are the 0.10 run on the 2026-11-17 pull (Delaware 46,690 sticks / 54,964 legs, Midland 33,791 / 37,432).

What the plan asked for, and where it lands:

- **Source, generator version, DSU id, well type, legs and turn, TVD + basis, spacing + basis.** All present. They sit on
  `box.location_stick` (per set), not as columns on `box.location`: see question 1.
- **How the depth was reached.** `tvd_rung`, `tvd_anchor[]`, `tvd_err_median_ft`, `tvd_err_p90_ft`. The back-test ratios are
  in the column comment (pull 2026-11-17, cutoff 2023-01-01): thickness 1.56x, bracket 1.71x, offset 1.16x of the held-out
  median; thickness and bracket fail the 1.5x bar.
- **Flags travel with the stick.** `flags[]` (checked against the four known values) and `second_level_tvd_ft`.
- **`box.location_set`** with one `is_record` per basin, like `forecast_run` after sql/70.
- **App-facing `stick_id` positive.** `stick_id = location_id` for our sticks, with the id sequence restarted at 10,000,001
  so the number can never equal a Novi stick id or an existing location id. PDP `-(api10)` is untouched. Question 2.

Two gaps in the generator that 4b has to close before a stick can fill these columns (both add fields, neither moves a stick;
the version becomes `box_sticks_0.11`):

1. **Anchor benches are dropped.** The landing chain knows them (frame column `how`: `LSSH/WCA_1` for a bracket, one bench
   for thickness and offset) but `core.py` does not carry them onto the stick.
2. **The direct rung stores no expected error** (`held_out_median_ft = null` on 31,377 of 80,481 sticks). The plan says every
   stick stores its rung's held-out error. The direct hold-out exists per bench (phase 1); it needs passing through.

## 3. The id scheme

**Rule.** Inside one DSU and one bench, a stick of the new run is the same location as a stick of the previous run when its
legs run along the previous stick's legs: shared length at least 50 % of the shorter stick (D73 / D83), legs within 220 ft
sideways. Matching is 1:1, greedy by shared length, then by sideways offset. A carried stick keeps its `location_id` and its
`slot_no`. A new stick takes the next unused slot number of its DSU x bench; numbers are never reused. A previous stick with
no successor stops (`last_seen_set` stays where it was). Bench is part of identity (D73); depth is not.

**Why not the generator's own number.** `10665-AVA_1-03` is the third PLACED row counting across the DSU. Drill one well and
every row after it renumbers.

**Why 220 ft.** Half the tight cap (440 ft): two rows of one bench can never both be inside it. D83 used 250 ft on Novi sticks.

### 3a. Measured: the 0.9 run before the tag cutover against the 0.10 run after it

Grain: sticks. Previous = `box_sticks_0.9_pilot` on the 2026-11-14 pull (pre-cutover tags). New = `box_sticks_0.10_pilot` on
the 2026-11-17 pull (post-cutover; 1,313 wells re-tagged between the two). This is the hardest comparison available: a tag
cutover between the runs. 0.9 and 0.10 on the SAME pull differ in nothing but the flag.

| | Delaware | Midland |
|---|---|---|
| Previous sticks | 46,499 | 34,045 |
| New sticks | 46,690 | 33,791 |
| **Carried** (id kept) | **42,586 (91.2 % of new)** | **30,341 (89.8 %)** |
| New ids | 4,104 | 3,450 |
| Stopped ids | 3,913 | 3,704 |
| Carried within 1 ft of the old position | 27,675 | 17,189 |
| Sideways offset of the carried, median / P90 | 0.3 / 20.2 ft | 0.4 / 44.4 ft |
| Carried whose positional number changed | 819 | 844 |
| Carried whose target TVD moved > 50 ft / > 150 ft | 2,064 / 583 | 1,992 / 404 |
| Carried whose well type changed | 0 | 0 |
| New: bench new to the DSU / bench already there | 431 / 3,673 | 379 / 3,071 |
| DSU x bench whose stick count changed | 1,501 of 18,956 | 1,496 of 12,972 |

Corridor sensitivity (`crosswalk_by_corridor.csv`): carried share of new sticks at 50 / 100 / 150 / 220 / 250 / 330 ft is
86.0 / 88.4 / 89.8 / 91.2 / 91.8 / 93.0 % Delaware and 81.6 / 85.6 / 87.5 / 89.8 / 90.6 / 92.3 % Midland. No plateau: there is
no width at which the remainder is clearly "different rows". 220 ft is the widest that cannot confuse two rows.

**What turns ids over is the spacing map, not the wells in the DSU.** Most new and stopped ids sit in a DSU x bench that kept
its bench (3,673 of 4,104 new in the Delaware). An unpinned bench's grid is laid out from the blended spacing value; when
that value moves, every row moves and the outer rows leave the corridor.

### 3b. Real DSUs (`crosswalk_example_dsus.csv`; gunbarrel x in ft)

**Delaware pad 11132, WCC, pinned. Count 7 -> 8.** Spacing 579.5 -> 577.5 ft. All seven carry at 0.2 to 6.2 ft; the eighth
row is new and takes slot 8. This is the case the scheme is for.

| Slot | Status | Previous x | New x | Offset ft |
|---|---|---|---|---|
| 1 to 7 | carried | -1,750 ... 1,726 | -1,744 ... 1,721 | 0.2 to 6.2 |
| 8 | new | | 2,298 | |

**Delaware pad 10665, AVA_1, unpinned, offset rung. Count 6 -> 7.** Map spacing 917.2 -> 721.0 ft: the whole grid was re-laid.
Four carry (offsets 0, 196, 132, 64 ft), two stop, three are new. The generator would call the new rows `-03`, `-04`, `-07`;
they take slots 7, 8, 9. TVD moved 9,704.3 -> 9,683.1 ft on the carried four: same locations, new depth.

| Slot | Status | Previous x | New x | Offset ft |
|---|---|---|---|---|
| 1 | carried | -2,291 | -2,291 | 0.0 |
| 2 | carried | -1,374 | -1,570 | 196.2 |
| 3 | stopped | -457 | | |
| 4 | carried | 460 | 593 | 132.4 |
| 5 | carried | 1,378 | 1,314 | 63.9 |
| 6 | stopped | 2,295 | | |
| 7, 8, 9 | new | | -849, -128, 2,035 | |

**Delaware pad 10902, WCA family.** WCA_1 went from 0 to 4 sticks after the re-tag; WCA_2 kept its one stick (0.4 ft). The four
WCA_1 rows are new locations: a bench change is never a carry.

**Midland pad 23026, LSSH, pinned. Count 2 -> 1.** Slot 1 carries at 177.9 ft (the pinned grid re-phased); slot 2 stops.
DEAN on the same pad: 5 stop, 4 new, none carried.

**Midland pad 22871, DEAN, unpinned. Count 2 -> 3.** Spacing 1,011.1 -> 823.7 ft. One carries (83.7 ft), one stops, two new.

**Pilot pad 10600 (Lea).** 27 carried, 3 new, 3 stopped (BS2_S lost two rows; WCC re-laid).

### 3c. Same generator, consecutive pulls

Grain: sticks. Previous = 0.10 on the 2026-11-17 pull. New = 0.10 on a fresh read-only pull of 2026-11-18 (after tag rule
run 8; a new cache, nothing reused): Delaware 46,709 sticks (54,985 legs, 448.5 MM ft), Midland 33,829 (37,470 legs,
348.3 MM ft), 0 errors, 0 invariant violations. This is one night of warehouse movement, the normal case for a regeneration.
Files: `crosswalk_consecutive_*`.

| | Delaware | Midland |
|---|---|---|
| Previous / new sticks | 46,690 / 46,709 | 33,791 / 33,829 |
| **Carried** | **46,544 (99.65 % of new)** | **33,477 (98.96 %)** |
| New / stopped ids | 165 / 146 | 352 / 314 |
| Carried within 1 ft of the old position | 45,572 | 31,625 |
| Carried whose target TVD moved > 50 ft / > 150 ft | 5 / 0 | 61 / 5 |
| DSU x bench whose stick count changed | 33 of 18,733 | 56 of 12,707 |

One night turns over 0.3 % of Delaware ids and 1.0 % of Midland ids; the corridor width hardly matters here (99.52 % at 50 ft
to 99.70 % at 330 ft, Delaware). The 9 to 10 % of section 3a is the tag cutover, not the ordinary rate.

The run summaries stamp `pulled 2026-11-18` on BOTH runs (the older frame was rebuilt that day); the older one is the
2026-11-17 pull. That mislabel is hazard 3 of section 4.

### 3d. What the scheme does not do

- It does not make the unpinned grids hold still. About 9 to 10 % of ids turned over across the cutover and 0.3 to 1.0 % over
  one ordinary night. If econ is priced on
  a record set and the set is regenerated, that share of priced locations stops. That is a property of regenerating, and the
  reason regeneration stays a periodic explicit-go operation (plan, phase 5).
- A U-turn whose legs were re-paired one row over shares exactly one leg (50 %) with each old neighbour and carries one of
  them. Arguable either way; counted as a carry by the D73 threshold.
- Ids are only as stable as the DSU polygons. A new Novi pad vintage re-keys `pad_id`; the crosswalk would then have to run
  across DSUs. Not built (the plan freezes 2026Q3).

## 4. What a generation run reads

Today the chain reads the warehouse once into pickles and everything after runs from them. Nothing checks a pickle's age.

**Warehouse inputs that place sticks**

| Relation | Filter | Changes |
|---|---|---|
| `curated.wells_enriched` (+ `curated.well_lateral_survey`) | Delaware / Midland, horizontal, producing: tag, depth evidence, lateral geometry | nightly (tags since 11-16 by the rule) |
| same, not yet producing | `well_status IN ('Spud','DUC','Completed')`, line geometry | nightly |
| `box.extent` | `is_record` (23 extents) | on an explicit store |
| `raw_novi_intel.pads` | `report_version = '2026Q3'` (16,585) | frozen |

Read but not used for placement (Novi comparison and reports only): `curated.intel_locations`, `curated.intel_formation_blueox`,
`curated.reconciled_inventory`, `curated.formation_tag_rule`, the record BOX runs.

**File inputs that place sticks**

| File | What it decides |
|---|---|
| `docs/box_sticks/wcxy-extent-2026-11-12/extent_WCXY_edited.geojson` | the WCXY extent. **If the file is missing WCXY is silently dropped** |
| `docs/box_sticks/cutover-2026-11-17/phase1/holdout_thickness.csv`, `phase1b/holdout_far.csv` | the anchor rank order (thickness, bracket, offset). Paths are hard-coded |
| `.claude/skills/deal-intake/config/strat_column.yaml`, `thresholds.yaml` (`planned_spacing`) | bench order; spacing-gap and parallel tolerances |
| `requirements-dealintake.txt` | narvi pinned at `41e0844` |

**Why a run is not reproducible today**

1. Inputs are live and move nightly; a scratch cache is the only copy of what was read.
2. No pull has an `ORDER BY`. Several tie-breaks follow row order (nearest neighbour at equal distance, k-nearest cut-offs).
3. `pulled` is the date the frame was built, not when the SQL ran (phase 3e says `2026-11-18` for a 2026-11-17 pull).
4. A per-DSU exception is caught and the DSU drops out of the run (0 errors so far).

**Proposal: two levels.**

- **Exact, from the warehouse alone.** The generator proper (`generate_dsu`) takes, per DSU: the polygon, the azimuth, one row
  per bench (depth, rung, anchors, errors, spacing, flags) and the wells within 2,640 ft. The draft stores exactly those
  (`location_set_dsu`, `_bench`, `_well`). The store step then regenerates from the stored rows and refuses unless it gets
  the same sticks (same slots, legs within 0.1 ft). That check is the proof; it has not been run yet (4d dry-run).
- **As-of, pinned by a manifest.** The upstream derivation (landing chain, spacing map, envelope constants) is not stored
  step by step. `location_set.inputs` records each relation's row count and digest, the tag run id and policy digest, the
  extent ids, and the sha256 of every file above; `cfg` records every threshold; `code_sha` and `narvi_sha` the code.
  A re-derivation on a later night will differ, and the manifest says by how much the inputs moved.

4b changes to make that hold: one entry point that pulls into a fresh run directory (no reuse), `ORDER BY` on every pull, the
pull timestamp taken at the SQL, a hard failure on a missing WCXY file or any DSU error.

## 5. Questions

Recommendation first in each.

**Q1. Per-set stick rows, or columns on `box.location`?** *Recommend per-set rows (`box.location_stick`), as drafted.*
The plan says "`box.location` gains ... leg and turn geometry, target TVD ...". One row per location cannot hold two sets.
Pad 10665 AVA_1 slot 2: 196 ft sideways and 21 ft shallower in the next run, same id. With columns on `box.location` the
older set's stick is overwritten and a forecast run built on it can no longer be explained. `box.location` keeps identity;
`geom` / `lateral_ft` stay "as last seen" as today.

**Q2. `stick_id = location_id`, sequence restarted at 10,000,001?** *Recommend yes.* One number, positive, disjoint from Novi
stick ids (max 1,824,903) and from the 252,925 existing location ids by construction. The alternative, a separate
`stick_id`, is a second id to keep in step for no gain.

**Q3. Stored `well_name` uses the slot number** (`10665-AVA_1-07`), not the position in the row. *Recommend yes*: a name that
means the same stick next quarter. Cost: after churn the numbers are not in cross-section order.

**Q4. Is the first stored set `is_record`, and what reads it before phase 7?** *Recommend: store it NOT record; flip on a
separate go once both basins are stored and checked.* Nothing reads `box.location_set` before phase 5 (reconciliation
targets the record set) and phase 6 (`_UNIVERSE_SQL`); no app reads it before phase 7. So the flag changes no pad today.
It starts to matter at the first regeneration after something is keyed on the ids: on pad 10665 AVA_1, 3 of 7 ids are new
and 2 stop across one regeneration. A set that was never record can be pruned with its never-used ids; a record cannot.
New sets always carry ids from the RECORD set of the basin (from the latest stored set while no record exists).

**Q5. Store the row-level ledger (every culled row and its reason; 165,543 rows a pair)?** *Recommend no for now.*
`location_set_bench.rows_culled` keeps the count by reason per DSU x bench, and the ledger regenerates exactly from the
stored inputs. Phase 5's `crowded` flag or an erebor "why no stick here" layer would be the reason to add it.

**Q6. WCXY hand-drawn extent: stored with these writes?** *Recommend not in `box.extent` now; pin the committed file by sha256
in the set's manifest and fail hard if it is missing.* What storing it in `box.extent` touches:
- it needs a `box.bench_scope` row for WCXY. With `member_benches = '{}'` the forecast universe is unchanged
  (`_UNIVERSE_SQL` joins on `member_benches`); with `{WCXY}` every WCXY Novi stick joins twice (WCA pool and WCXY).
- a 24th record extent enters the nightly tag rule's inputs (`box/tag_rule_inputs.py:86`, `etl/tag_rule.py:103`; reporting
  columns only, but you said not to touch the rule), erebor's scope list (`api/box.py:395`) and the geology package.
- the generator would then see WCXY twice (the table and the file) until its read is changed.
Pad 10665 has 5 WCXY sticks (959 in the Delaware at 0.10, pull 2026-11-17) that exist only because of that file; with the file pinned by hash they
are reproducible from the repo + warehouse, not from the warehouse alone. That is the one input left outside it. Store it in
`box.extent` when phase 6 settles the WCXY forecast pool.

**Q7. The private narvi functions.** There are FOUR, not three: `placement._longest_segment`, `generate._make_leg`,
`generate._single_well`, `generate._place_uturns` (`box/sticks/core.py:175, 455, 469`). *Recommend a small narvi PR that
exposes them under public names with no behaviour change, then bump the pin; no engine copy.* Until it merges: keep the pin
at `41e0844` and add a test that fails if any of the four is missing. It changes no stick on any pad; it decides whether a
set of record rests on another repo's private names. `narvi_sha` is stored with every set either way.

**Q8. Second-level measure for the bracket and offset rungs before storing?** *Recommend store without it; NULL there means
"not measured" and the column comment says so.* 17,321 of 80,481 sticks are on those rungs (Delaware 7,534 offset + 2,625
bracket; Midland 5,792 + 1,370). The flag moves no stick and is no part of identity (0.9 -> 0.10 on one pull: 0 sticks
changed), so adding it later is a new set with every id carried. Those rungs already carry their own warning: bracket
misses 1.71x its held-out median. Pad 9042 BS3_C (offset rung): expected 81 ft median, 211 ft P90, no second-level reading.
No pad's sticks change with the answer; what changes is whether a consumer can tell "one level" from "not looked".

**Q9. Direct-rung expected error** (section 2, gap 2): fill it from the phase 1 hold-out per bench? *Recommend yes*, so every
stick has a number.
