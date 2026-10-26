# Step 19 — basin parameterization (2026-10-26). Built; AT GATE 19.

Plan: `docs/box_type_curves_plan.md` §5 step 19 (difference 7, D130, D132). Code only: nothing was written to the warehouse.
sql/70 is container-validated, NOT applied live.

## 1. What changed

**One home for every basin literal: `box/basin.py`.** A build, pool refresh, bench QC, extent, water or proximity pass names its
basin and reads what differs from there:

| parameter | Delaware (= the pre-step-19 literal) | Midland |
|---|---|---|
| terminal Df, nominal /yr (every cohort P50 fit: oil, gas, water) | 0.08 | **0.06 (D132)** |
| state line (bench QC bins, map lines) | 32.0 N | none |
| D23 edge metric r / c | 2,640 / 3,960 ft | none: refuses until step 20a calibrates it |
| structure-grid folders (geology context) | `Grids/Delaware/Structure`, `Structure Grids/Delaware` | none |
| Novi report (hindcast) | `basin_research__Delaware_Basin__<v>` | `basin_research__Midland_Basin__<v>` |

**Threaded through the production path** (each defaults to Delaware, so every existing call is unchanged):

- **Analog build** (`box/analog.py`, `box/production.py`, `scripts/box_pud_run.py`, `box/acceptance.py`): Df; deal-intake's
  `classify(basin=…)`; the PDP-stick pull; the extent of record (`tc_area_report.pull_extent` now takes the basin — WCB_1 /
  WCB_2 / WCC exist in BOTH basins). `BENCH_SPECS` entries carry `basin` (all Delaware today).
- **A run is one basin (D130).** `production.run_basin` refuses groups from two basins; the universe is the run's basin only;
  `run.pkl` records the basin; `store` writes `forecast_run.basin`, scopes the D73 crosswalk to the basin and flips only that
  basin's record. `box_prox_record` copies the source run's basin; `box_water_run` stores on its basin's record;
  `box_prune_runs` keeps one record per basin (`--basin`); `box_refresh` / `refresh13` take `--basin`.
- **Pools + bench QC** (`box/bench_qc.py`, `box/family_qc.py`, `scripts/box_pool_refresh.py`, `scripts/box_family_qc.py`):
  `pull_producers(conn, basin)`; the state-line check and map lines only where the basin has one (Midland:
  `not_applicable`). `box_pool_refresh --basin midland` refuses: no Midland pools exist until step 20.
- **Extents** (`box/extent_report.py`, `box/family_extent.py`, `box/extent_package.py`, `box/extent_store.py`, the family
  extent / geology-package scripts): per-basin edge metric, PUD pull, labels, grid roots.
- **Water** (`box/water11.py`, `scripts/box_water11.py`, `scripts/box_water_run.py`): Df + classify basin.
- **Proximity** (`box/prox_study_report.py`, `box/prox_pud_report.py`, `scripts/box_step16d_prox.py`): producers of the
  basin's bounding box; the basin's record.
- **Hindcast** (`box/hindcast_production.py`): the Novi report name from basin + vintage.

**D130 — sql/70** (`sql/70_box_record_per_basin.sql`, `scripts/apply_box_run_basin.py`): `box.forecast_run.basin` (NOT
NULL, CHECK delaware | midland, DEFAULT 'delaware') and `UNIQUE (basin) WHERE is_record`, replacing sql/60's one-record index.

**Every record-run reader names the basin:**

- BOX scripts: the store / prox / water / prune / refresh paths above, plus the Delaware step tools that read "the" record
  (`box_eur_map`, `box_thin_bench`, `box_tune9a`, `box_water11`, `box_midland_scope`) now read the Delaware record by name.
  A test fails any new `forecast_run … is_record` read that names no basin.
- **sql/69** (`curated.box_scout_locations`): the econ case is picked PER record run and joined on its run_id.
- **erebor** (branch `claude/box-record-per-basin`): `record_run` / `record_run_id` take the request's basin (every endpoint
  already scopes by basin). A basin with no record of its own (Midland until step 23) reads the Delaware record — what erebor
  shows today.

Also: the `novi-quarterly-reload` skill §9 (one record per basin, `--basin delaware` prune), the data-dictionary consumer
line for `box.forecast_run`, `scripts/box_basin_dry_pull.py` (§3).

## 2. Equivalence (the gate-19 bar)

**Run-19 smoke equivalence (WCA / BS2_S / AVA_0, the 16d smoke set): bit-identical.**

What was run:
- `box_pud_run build --selection r2 --wells docs/box/pool-2026-10-15 --benches WCA,BS2_S,AVA_0 --limit 30`.
- The old code (07d2ca2) and the new code (ca2be90) ran **concurrently**, after the late nightly finished (18:16 UTC), so both
  read one warehouse snapshot. A first pair was stopped: it had overlapped the nightly load.
- Exact comparison of the two `run.pkl`: `smoke_equivalence.log`, script `compare_smoke.py`.

Results:
- Harness equivalence (production path vs `predict_location_v2`): max_rel_diff **0.0** on every group, both builds.
- **90 / 90 locations identical:** every stream's params, raw and haircut monthly volumes (180 month vectors), analogs, flags,
  radius / search provenance and planned spacing. The analog metadata and cum-per-kft tables are identical. The per-group F(k),
  haircut, guard and disclosure are identical.
- The run header differs only by the new `basin: delaware` key.
- **Universe: 117,542 (new) vs 121,696 (old).** The 4,154 rows only in the old build are all Midland BRNT
  `not_covered_emerging`. Every shared row is identical, and the new build has no extra row. This is D130's per-basin universe
  (§4 ask 1), not a forecast change.
- These builds are at production through 2026-08-01 (cutoff 2026-09-01), one month past run 19's 2026-07-01. So the
  comparison is old vs new code on today's data, not against run 19's stored values. Those can only be reproduced on run 19's
  data, which the warehouse no longer holds.

**13b pool refresh — byte-identical.** `box_pool_refresh --base docs/box/pool-2026-10-15`, old code (07d2ca2) and new code
run together into scratch:

- every `wells_final_<pool>.csv` (12), `universe.csv` and `new_wells.csv`: byte-identical;
- `refresh.json`: identical apart from `built_at` / `git_sha` / `out_dir`;
- `index.html`: differs only in its built timestamp.

Both differ from the committed `docs/box/pool-2026-10-26` for one reason: the warehouse moved after this morning's refresh
(the nightly ran late, 17:23–18:16 UTC). Live producing horizontals went 31,776 → 31,807, so 165 wells would be added instead of
134. That is data, not code. The confirmed pool directory stays as committed.

**Delaware extent rebuild — within 0.005 sq mi.** The generated records rebuilt with the new code (`box_family_extents`,
step-15 well sets) against the stored `box.extent` geometry:

| record | stored sq mi | rebuilt | symmetric difference |
|---|---|---|---|
| WCC (27) | 1,454.804 | 1,454.804 | 0.0020 sq mi |
| AVA_0 (28) | 259.135 | 259.135 | 0.0011 sq mi |
| AVA_1 (29) | 548.020 | 548.020 | 0.0012 sq mi |
| AVA_2 (30) | 623.645 | 623.645 | 0.0015 sq mi |

- New and old code give the IDENTICAL WCC polygon (`equals`, 0.0 sq mi).
- The step-3 regression (`--regress`, from the frozen gate-1 sets): WCA 6,168.65 → 6,168.65 (+2.7e-7).
- **BS2_S misses the bar:** 3,358.45 → 3,358.13 sq mi (−0.32 sq mi, −9.5e-5). The OLD code gives the same number on the same
  data. So this is live lateral geometry that changed since 2026-10-07, not step 19.
- The owner-edited records (BS1_S, BS2_C, BS3_S, BS3_C, WCB_1, WCB_2) are pen loops, not regenerable.

**eng_db suite green:** 743 passed, 46 skipped (9 new in `tests/test_box_basin.py`). ruff is clean on every touched file except `scripts/gen_data_dictionary.py` (a one-line text edit), whose 9 findings pre-date this branch (9 on main).

**erebor suite green:** 113 passed (1 new).

**sql/70 container-validated.** `scripts.box_rehearsal` container, seeded read-only from live and verified equal by count
(`docs/box/step19-2026-10-26/sql70_container.log`). Two passes, 11/11 checks each, idempotent:

- every run reads basin 'delaware';
- record run_ids and row counts unchanged;
- the old index is gone and EXPLAIN uses `box_forecast_run_record_basin_uq`;
- smoke (rolled back): a Midland record sits next to the Delaware one; the per-basin flip touches only the Midland record; a
  second Delaware record and an unknown basin are refused.

Against the same container: `box_prune_runs` (dry run) lists one record per basin. erebor's `record_run` resolves
delaware → 19 and midland → 19 (fallback). With a Midland record inserted (rolled back), midland resolves to its own run and
delaware stays 19.

**sql/69 rewrite, read-only on live:** `apply_box_scout_locations --dry-run` passes every check (42,970 rows, oil
22,623.315 MMbbl tie). The new body is row-for-row identical to the live view (ordered md5
`9e2f1ebbb5087ca2931c7d973386ec2d`).

## 3. Midland dry pull (read-only; counts only — nothing Midland is reviewed here)

`python -m scripts.box_basin_dry_pull` → `dry_pull_midland.json`. Every path opens:

- **Bench QC pull:** 28,859 producing horizontals (WCA_1 7,721 / WCB_1 6,164 / LSSH 5,812 / …). Consensus scoring runs
  (1,244 flags). The WCA_1 summary has no state-line check (`not_applicable`).
- **Universe:** 4,154 rows, all BRNT `not_covered_emerging` — exactly the Midland rows run 19 carries today (§4 ask 1).
- **WCA_1:** 7,709 PDP sticks; 11,068 PUD sticks in the pull box.
- **Proximity producers in the basin box:** 31,041.
- **Water sample:** 85 % calculated (cf. D133).
- **Novi report:** `basin_research__Midland_Basin__2025Q3` has rows.
- **Refuse by name, as they should:**
  - the D23 edge metric (step 20a);
  - the extent of record (none until step 20);
  - the record-run groups (step 23);
  - `box_refresh check`, which needs sql/70 live.

## 4. Gate 19 — your calls

1. **Per-basin universe (D130 consequence).** Run 19, the Delaware record, carries 4,154 Midland BRNT `not_covered_emerging`
   rows. That is because the universe used to be every basin's.
   - From now on a run's universe is its basin's. The next Delaware record (13c) drops those rows, and they return with the
     first Midland record (step 23).
   - Between those two, erebor shows those Midland PUD sticks as `not_screened` (a BOX bench, no row in the record run)
     instead of `not_covered_emerging`. Forecasts are unaffected.
   - Rec: accept.
   - Alternative: derive `not_covered_emerging` from `box.bench_scope.in_scope = false` in erebor. That also relabels
     Delaware RES sticks on WDFD / WCD, which read `not_screened` today.
2. **sql/70 keeps `DEFAULT 'delaware'`** on `forecast_run.basin`, so the sql/60–65 apply smokes and any pre-step-19 writer
   still insert. Every step-19 writer names its basin.
   - Rec: keep.
   - Alternative: drop the default now. Those smokes would then need editing.
3. **Order of the live tail (each an explicit go).**
   1. `python -m scripts.apply_box_run_basin` (sql/70; the smoke burns ~4 run ids, as earlier smokes did).
   2. Merge eng_db (the readers need the column: `box_refresh check` fails before sql/70).
   3. `python -m scripts.apply_box_scout_locations` (sql/69, row-identical today).
   4. Dictionary regen.
   5. Merge erebor (it reads `forecast_run.basin`; before sql/70 it would error).
4. **Midland group keys (for step 21a).** `PRODUCTION_BENCHES`, `BENCH_SPECS` and the water `GROUPS` are keyed by group name,
   and the Delaware already owns WCB_1 / WCB_2 / WCC.
   - Rec: Midland groups get distinct keys (e.g. `MID_WCB_1`), each with `basin: "midland"` in its entry.
5. **Phase 3 simplification — proposed plan amendment (§5 below).** You asked on 2026-10-26: Phase 3 transfers a refined
   method, so trim what is re-derivation rather than validation.
   - Rec: adopt A–D.
   - Keep E unchanged.
6. **FYI, no decision.** Passing the basin into deal-intake's `classify` means the NON-record variants (di_p50, pre-r2 v2) read
   the per-basin lateral tolerance: Midland 0.40 vs Delaware 0.25 (ledger §9).
   - The record r2 selection passes its explicit 5,000–15,000-ft band, so it never reads the tolerance.
   - D129's widened Midland band stays step 21a's.

## 5. Proposed Phase 3 amendment — transfer, don't re-derive (for your decision at gate 19)

**Principle.** Phase 3 applies the Delaware method of record (run 19: r2 selection, D53 / D99 acceptance, D105 tier, proximity
layer, D107 water). A Midland step should only:
- **measure** what the method needs per basin, or
- **validate** each group out of time.

Re-calibrating a knob the Delaware already settled is cut unless the Midland evidence visibly breaks it. Nothing below changes a
decision of record; each cut removes work the plan currently schedules.

| | Plan as drafted | Proposed | Why it is safe | Saves |
|---|---|---|---|---|
| **A. Edge metric (20a)** | Repeat step 2 on Midland WCA_1: calibrate r and c, the step-out table, re-check D27's 8-mi bridge / ≥ 3-lateral cluster constants | **Adopt the Delaware D23 r = 2,640 / c = 3,960 ft and D27 constants as the Midland values** (box/basin.py). Judge the extents on the rendered maps + your pen loops, as for the step-15 benches | Since D27 an extent is a development envelope, not a performance screen; r / c only shape the first-pass outline, which you edit anyway. A visible failure (e.g. WCA_1 not one body) reopens it, then and only then | ~1 session |
| **B. Bench-QC cards (20a / 20b)** | Calibration cards per swap class; class rule ratified per class from verdicts | **Apply the Delaware class rule of record (box/qc_rule) as written.** Card only a swap class whose flag rate or GOR / TVD signature is clearly unlike its Delaware analogue. The flag ledger and sensitivity tables still render. D128 (no pooling) already removes the pooling analysis | The rule encodes general tag mechanics (consensus + sql/23 second vote + GOR tiebreak + never BS→WC), not Delaware geology; step-1 sensitivity showed flags barely move cohort statistics (≤ 0.3 %) | ~1–2 sessions |
| **C. Long laterals (21a, D129)** | Pre-register a widened Midland analog band, score it against the r2 band with its own acceptance | **No second variant.** Admit > 15,000-ft producers to the pool (D129: never excluded by length), translate every cohort by Cui & Cross (extrapolated past 12,500 ft, flagged), and DISCLOSE the long-lateral cells: the D120 condition-6 length classes are reported in 21b's tuning tables, not judged | D129's substance (long laterals testify; Cui translates) stays; what goes is the head-to-head variant scoring. Reported cells still show if long-lateral PUDs read high / low | ~1 session; a fold re-run per group |
| **D. Water (step 22)** | Its own step: size the cohort, score D109, compare routes | **Fold into 21:** D107 as written (D133), scored the D109 way inside 21b / 21c from the same folds; reach + operator concentration reported per group | D133 already fixed the route; step 22 would only re-measure what the 21 runs produce anyway | ~1 session |
| **E. Tuning + one-time holdout (21b / 21c)** | As drafted | **Unchanged** | This is what earns a validated tier; Delaware validation does not transfer to a Midland bench. Thin groups go provisional (D105) | — |

**Net.**
- Phase 3 goes from ≈ 10–14 sessions to ≈ 7–9.
- New order: 19 → 20 (a + b, extents + QC by family, one gate each) → 21 (a pre-registration incl. water, b tuning, c holdout) → 23
  (record run). Step 22 is retired into 21.
- Step-20 deliverables keep: FINDINGS, QC pages, extent maps, the undrilled-inside-vs-outside counts and the geology package.

**If adopted, the plan edits are:**
- step 20 text: A + B;
- step 21a / 21b text: C + D;
- step 22 marked "folded into 21 (D134)";
- §10 order;
- `box/basin.py` Midland `pin_radius_ft` / `closing_ft` = 2,640 / 3,960 with the decision cited.

All in one docs PR before step 20.
