# D117 step 4: the derived record stored live (2026-10-30)

> **RECORD FLAG REVERTED 2026-10-30 (Michael's go): the Delaware record is the 16d record (run 19) again.** The D117 record
> (run 25) stays stored, verified and un-priced, with `is_record = false`.
> - **Why:** making it the record blanked erebor's econ screen and `curated.box_scout_locations` (42,833 → 0). Both show econ
>   for the record run only, and Steven had not priced run 25. That should have been a stop-and-ask before the flip, not a note.
> - **Michael's framing:** this work is BOX for the Midland. D117 applies to the Delaware too, but whether and when the Delaware
>   record takes it is open.
> - **Done in one transaction:** run 25 `is_record` false, then run 19 true. The view was checked at 42,833 rows before
>   COMMIT (`record_back_to_16d_LIVE.log`). Steven's 687,520 econ rows were never touched.
> - **To make the D117 record current later:** flip the flag (two updates), ideally once Steven has priced run 25 so the
>   screens don't blank.
> - **D144 (Michael 2026-10-31): the Delaware stays on the 16d record (run 19) until the Midland record is ready to price.**
>   Then the Delaware's D117 move is decided, so Steven prices both together. Run 19 is not pruned while it is the record.
> - Everything below describes the store as it happened.

On Michael's "go apply" (2026-10-30), after his three step-3 gate calls:
- carry the 93 D64-gap rows;
- re-measure proximity on run 19's rows (D116);
- store the derived record.

**Live Delaware record = run 25.** It is run 19's build plus the D117 RES rows, with proximity re-measured. The 16d record (run 19) is kept,
superseded; the base run (run 24) was pruned.

## What ran (Supabase, branch `claude/box-d117-step3-universe`)

The live chain stored the same artifacts the step-3 rehearsal verified. Nothing was rebuilt.

| step | command | result |
|---|---|---|
| base | `box_pud_run store --out runs/box_d117s3 --record` | **run 24**: pud_forecast 166,843 = universe; covered 24,258 + covered_provisional 33,380 = 57,638 in-extent, 0 no_analogs; every stream 600 months = EUR; ≥ 4 named analogs. 2,052 s. `store_LIVE.log` |
| water | `box_water_run store --out runs/box_d117s3_water --run-id 24` | 57,638 water streams (validated 9,310, provisional 48,328); oil / gas rows and months unchanged; ≥ 3 water analogs. 1,372 s. `water_store_LIVE.log` |
| proximity measure | `box_step16d prox-measure --run-id 24 --box-db live` | 57,638 PUDs, 349,571 links, identity True; oil 31,673.5 → 25,569.9 MMbbl. **Outcomes and factors identical to the rehearsal's on every location** (0 moved); the file differs only in float printing of three informational EUR columns (relative ≤ 5 × 10⁻¹⁵). `prox/`, `prox_measure_LIVE.log` |
| proximity record | `box_prox_record store --src-run 24 … --commit --record` | **run 25 = the one Delaware record**. Every identity green. 8,693 no-precedent moves; 48,945 forecast PUDs per stream; oil 25,569.904 MMbbl = source × factor; 88,101,000 month rows; 78,950 named parents; run 24 untouched. 5,146 s. `prox_store_LIVE.log` |

## Verification: live run 25 vs container run 25 (`box_d117_step3 compare`, read-only both sides)

`verify/compare.json`:

| table | rows | reproduced exactly |
|---|---|---|
| pud_forecast | 166,843 | 166,843 |
| pud_forecast_stream | 146,835 | 146,835 |
| pud_forecast_month (md5 per location × stream) | 146,835 | 146,835 |
| location_analog (per location) | 48,945 | 48,945 |
| location_water_analog (per location) | 48,945 | 48,945 |
| pud_proximity_parent (per location) | 27,844 | 27,844 |
| pud_proximity | 57,638 | every column but `table_ref` |

`table_ref` embeds the sha256 of the outcomes file, and the live file's bytes differ as described above. Nothing is
container-only or missing. The live record is therefore the rehearsed record, and step 3's attribution against run 19 carries
over unchanged: 0 unexplained differences.

## The record by category (live, Novi category from `curated.intel_locations`)

| category | universe rows | forecast | oil after proximity |
|---|---|---|---|
| PUD (BASE_CASE) | 117,542 | 43,009 | 22,648.3 MMbbl (run 19: 22,623.3; +25.0 from the D116 re-measure) |
| RES (UPSIDE) | 49,301 | 5,936 (covered 5,440, provisional 496; 283 no-precedent) | 2,921.6 MMbbl |
| total | 166,843 | 48,945 | **25,569.9 MMbbl** |

## Consequences and what is left

- **Steven:** `curated.box_scout_locations` and erebor's econ screen follow the record. Run 25 has no `box_econ` rows yet, so
  the view returns 0 rows until he prices it. It showed 42,833 on run 19. Run 19's 687,520 econ rows are untouched.
  - The re-price note must split the change: +2,921.6 MMbbl RES (D117) and +25.0 MMbbl on run 19's PUDs (D116 re-measure,
    parent-tag drift).
- **Prune (D123):** the D117 base run (run 24, unpriced) was PRUNED 2026-10-30 on Michael's go. Checks passed: no orphan rows,
  kept runs' rows unchanged, the record unchanged (`prune_base_LIVE.log`; a first attempt lost its connection on the opening
  read, before any delete). The 16d record (run 19) is kept while it carries Steven's 687,520 econ rows. Its `superseded_by`
  is now NULL, because it pointed at the pruned base. Pruning it (`--include-priced`) waits on Michael's go, after Steven
  prices the D117 record (run 25) and it becomes the record.
- **WCXY co-development disclosure text** (D117): still to write.
- **Midland:** the 80 RES join the first Midland record (step 23).
- **erebor:** no code change. RES sticks on BOX benches inside BOX extents now read their BOX class instead of
  `not_screened`.
