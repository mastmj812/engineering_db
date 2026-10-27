# Step 13b — refresh tooling + container rehearsal (2026-10-26/27). AT GATE 13b.

This implements the D126 contract (`docs/box/step13a-2026-10-26/CONTRACT.md`). The tooling merged as eng_db #197. The rehearsal
(§3) stored only into the throwaway `scripts.box_rehearsal` container. **Nothing has been written to the live database.**

## 1. What changed

| piece | before | now |
|---|---|---|
| analog-pool refresh (`scripts.box_pool_refresh`, `box/pool_refresh.py`) | WCA pool only; BS2_S copied; 11 groups frozen at their step-15 sets | **all 12 pool files in ONE directory**. Each = its base file byte-for-byte + the wells never judged before that the class rule puts in that pool (identity-checked per file); a step-15 file's new rows carry `family_role = member` |
| which set the build reads (`production_run9.wells_dir`) | `--wells` for WCA / BS2_S / WCXY; hard-coded step-15 directories for the rest | `--wells` for every group whose file it holds. A WCA-only directory (run 19's `pool-2026-10-15`) still falls back to the step-15 sets, so run 19 is reproducible as built |
| water (`scripts.box_water_run`) | refused any run whose data-through ≠ the pinned 2026-07-01; hard-coded its own copy of the well-set directories | follows the run: its data-through and each group's well set come from the run artifact. It refuses only a run OLDER than the water spec's scored data-through |
| run notes (`box_pud_run.run_notes`) | haircut / tier clauses | plus the analog-pool set(s) each group read and the evidence-pack digest (D126 stamp) |
| driver (`scripts.box_refresh`, `box/refresh13.py`) | — | `check`: is a refresh due (new vintage, or more than 4 months of lag) + the extent trigger per group (N = 10, X = 2 mi, wells first producing after the extent was stored). `plan`: the ordered chain, every write marked [GO]. `build`: runs the two read-only builds from a committed pool directory |
| skill `novi-quarterly-reload` §9 | WCA-only run-7 chain | the 13-group chain: check → pools → builds → store base → water → proximity re-measure → proximity record → verify → prune (D123) → Steven → prospective tests |

Tests: 722 passed, 45 skipped (13 new). ruff is clean on the touched files.

## 2. First run of the tools on live data (read-only)

**`box_refresh check`:**
- Record run 19: Novi 2026Q3, production through 2026-07-01.
- Warehouse: Novi 2026Q3, production through 2026-10-01. That is 3 months of lag, so **no refresh is due**.
- Extent trigger: 0 on every group (no producer has first produced since the extents were stored, 2026-10-09 / 10-16).

**`box_pool_refresh` → `docs/box/pool-2026-10-26`** (live producers through 2026-08-01; base = `pool-2026-10-15` + the step-15 sets):

| pool | base rows | added | added in extent |
|---|---|---|---|
| WCA | 12,307 | 33 (WCA_1 16, WCA_2 16, OTHER → WCA 1) | 27 |
| BS2_S | 4,359 | 29 | 26 |
| WCB_1 | 1,820 | 9 | 4 |
| WCB_2 | 1,181 | 12 | 12 |
| WCC | 1,118 | 0 | 0 |
| BS1_S | 1,158 | 12 | 11 |
| BS2_C | 708 | 9 | 6 |
| BS3_S | 3,041 | 12 | 12 |
| BS3_C | 1,818 | 10 | 10 |
| AVA_0 | 480 | 0 | 0 |
| AVA_1 | 652 | 1 | 0 |
| AVA_2 | 538 | 7 | 6 |
| **total** | | **134** | **114** |

- 141 new wells on any bench. The 7 that no pool takes are counted only: OTHER 5, WCD 2.
- The identity check is OK on every file.
- The judged universe is the recorded 2026-10-15 one, plus 13 wells that only the step-15 sets had judged.
- The review page is `docs/box/pool-2026-10-26/index.html`: a table per pool, a map of the added wells, and the per-pool
  tables.

**Re-tags already present (reported, not acted on).** Every pool's base rows show live drift: wells whose `formation_blueox`
changed since the set was judged.

| pool | re-tagged | rule would now decide otherwise |
|---|---|---|
| WCA | 131 | 164 |
| BS2_S | 139 | 122 |
| BS3_C | 120 | 127 |
| BS2_C | 61 | 61 |
| AVA_2 | 46 | 46 |
| BS3_S | 40 | 41 |
| BS1_S | 28 | 30 |

Under D84 these are not re-decided. They are the drift a 13e tag release would formalize; the counts are recorded in each
refresh's `refresh.json`.

## 3. The container rehearsal (13b's acceptance), run 2026-10-26/27

**What ran** (code `ef7c083`, the #197 head; nothing live was written):

| step | where | result |
|---|---|---|
| `box_refresh build` (pool-2026-10-26, all 13 groups, 14 workers) | read-only vs live | 8 h 14 min, rc 0 |
| water build | read-only | 38 min, 51,419 locations, 0 ratio failures |
| store base `--record` | container | run 24: 18,630 covered + 32,789 provisional (= run 19's 51,419 forecast universe exactly) |
| store water on run 24 | container | every identity check OK (oil/gas rows md5-unchanged, 600 months per stream summing to EUR) |
| proximity re-measure (D116) | box rows from the container, curated read-only from live | 331,383 PUD links, identity True |
| proximity record: rollback rehearsal, then `--commit --record` | container | run 26 = the container's one record; every identity OK |

Logs: `rehearsal_build.log`, `rehearsal_store.log`. One driver snag: `prox-measure` defaults `--prec-runs runs/prox`, which resolves
against the working directory, so from a worktree it misses the precedent inputs. I re-ran it with the absolute path. The
live chain runs from the main checkout, where the default resolves.

**Data-through correction.** §2 says the warehouse holds production through 2026-10-01. The build uses the last FULL month
(rule of record, `box_pud_run` line 13), which is **2026-08-01**. Run 19 used 2026-07-01, so the rehearsal moves production
by ONE month, not three.

### 3a. Method: identical to run 19

- **Harness equivalence:** `max_rel_diff` 0.0 on all 13 groups, 24 locations each, production vs `predict_location_v2`.
- **Run notes:** run 26's notes equal run 19's clause for clause, plus the D126 stamp:
  "analog pools docs/box/pool-2026-10-26 (D84 / D126); evidence pack 90da3c56cb9d (D120 / D126)".
- **Spec labels, tiers, haircut tables and the evidence pack are unchanged.** WCA oil keeps its haircut and its gas has none
  (D122). BS2_S keeps oil + gas. The mean haircut factors per group match (WCA 0.79, BS2_S 0.78, the rest 1.00). The g(48)
  guard passes, with 0 rows outside on WCA oil and 0.03 % on BS2_S gas.
- **Coverage:** every covered location forecast, 0 without water, 0 no-analog rows.

Step 19 (D130 / D135, merged during the rehearsal) basin-parameterized this tooling. D135's smoke test proves Delaware
bit-identical across that change, so 13c runs on post-19 code with the same method.

### 3b. What moved (run 26 vs live run 19)

**Totals, final EUR (after haircut and proximity):**
- oil 22,623.3 → 22,489.8 MMbbl (**−0.59 %**);
- gas 136,817 → 136,813 Bcf (−0.00 %);
- water −0.50 %.

Forecast PUDs 42,970 → 42,927.

| group | forecast 19 → 26 | oil Δ | gas Δ | water Δ | same analog set | raw oil EUR per location, p05 / p95 Δ |
|---|---|---|---|---|---|---|
| WCA | 1,877 → 1,877 | +1.47 % | +0.59 % | −1.32 % | 56 % | −5 / +13 % |
| BS2_S | 7,078 → 7,073 | −0.38 % | +1.11 % | −0.49 % | 40 % | −8 / +8 % |
| WCXY_WCA1 | 3,149 → 3,149 | −0.37 % | −0.27 % | −0.53 % | 68 % | −5 / +4 % |
| WCB_1 | 3,991 → 3,991 | −0.55 % | −0.39 % | −0.08 % | 83 % | −5 / +4 % |
| WCC | 1,773 → 1,768 | −0.44 % | −0.01 % | +0.16 % | 76 % | −5 / +5 % |
| AVA_0 | 350 → 354 | +2.33 % | +0.02 % | +3.56 % | 40 % | −5 / +9 % |
| AVA_1 | 951 → 942 | +1.13 % | +0.00 % | +3.28 % | 13 % | −7 / +16 % |
| AVA_2 | 1,765 → 1,760 | −1.41 % | −2.21 % | −3.96 % | 43 % | −10 / +6 % |
| BS2_C | 2,148 → 2,140 | −1.77 % | −1.08 % | +1.76 % | 65 % | −10 / +6 % |
| BS3_S | 5,580 → 5,567 | −1.89 % | −0.25 % | −3.88 % | 61 % | −13 / +7 % |
| BS3_C | 7,167 → 7,166 | −0.22 % | +1.19 % | +0.55 % | 64 % | −7 / +10 % |
| WCB_2 | 2,315 → 2,314 | −1.33 % | +0.16 % | −1.23 % | 75 % | −8 / +4 % |
| BS1_S | 4,826 → 4,826 | −0.18 % | −0.52 % | +1.34 % | 43 % | −20 / +28 % |

No group moves more than ±2.4 % on oil. Machine-readable: `rehearsal_by_group.csv`.

### 3c. Attribution: the −133.5 MMbbl oil, by cause

Each matched location is put in ONE class, in this order.

| cause | locations | oil Δ MMbbl |
|---|---|---|
| **production +1 month, analog set unchanged** (per-well refits) | 24,872 | +24.5 |
| **production +1 month, 184 wells crossed the 6-month analog floor** (`min_months_data` = 6) and entered these sets, pushing the farthest analogs out | 6,946 | −91.0 |
| **proximity re-measure** (D116, new producers): moved INTO `not_covered_no_precedent` / back out of it | 153 / 110 | −93.6 / +64.3 |
| **Novi spacing revisions** (below), and the farther analogs they pushed out | 10,999 | −37.6 |
| total | | −133.5 |

- **The newest producers are weaker than the older, farther wells they replace.** Read that as a signal, not noise.
- **The 134 added pool wells moved nothing.** 0 of the 134 appear in any analog set:
  - 128 first produced in 2026-08, so they have 1 month at this data-through, under the 6-month floor;
  - the other 6 are too far, too old, or under the floor.

  They enter selection about two vintages later. This is the floor of record working as designed, not a defect. Per refresh,
  added wells move nothing until roughly 6 months after their first production.
- **A third input moved that the contract does not name: Novi's `lateral_closer_xy_ft`.**
  - **What it is:** the pool's measured spacing (D119) is read LIVE from `curated.wells_enriched` at build time.
    `raw_novi."WellSpacing"` is TRUNCATE + COPY every night, so Novi's values replace ours in place.
  - **How big:** I compared the step-16c tuning views (pulled 2026-10-22/23) with today's values. **1,024 of 10,671 wells
    (9.6 %) changed in about 4 days:**
    - 376 went from NULL (standalone) to a value;
    - 646 changed value (median −140 ft; 10–90 % range −1,261 / +180 ft);
    - 2 went from a value to NULL.
  - **Every vintage is touched** (6–13 % of wells per first-production year, 2019–2025). That makes it Novi reprocessing, not
    co-development neighbours arriving.
  - **Link to the analog churn:** 60 % of the wells that newly entered analog sets had a revised spacing. The changed-set
    locations show it directly. Every newly selected well now classes `representative`; 1,752 dropped slots now class
    `tight` / `standalone`, with the planned spacing unchanged. Evidence: `spacing_revisions.csv`.

**Acceptance against §3's bar.**
- Method identical: YES.
- Run notes stamped: YES.
- Every change explained: YES, by four movements, not the two §3 named:
  - the production month;
  - the proximity re-measure;
  - Novi spacing revisions;
  - zero from the 134 added wells.

## 4. Your calls (gate 13b)

1. **Novi spacing revisions between refreshes.** D126 freezes the measured-spacing METHOD. It is silent on the VALUES, which
   Novi rewrites nightly. So a re-build of the same pool a week later selects different analogs (here −37.6 MMbbl,
   −0.17 %). The options:
   - **(a) Recommended: snapshot the values in the pool directory.** The pool refresh writes `spacing.csv` (api10 →
     `lateral_closer_xy_ft`, read with the pull) and the build reads it. Each refresh then takes Novi's then-current values,
     so corrections still flow in quarterly, and the refresh reports revisions next to re-tags (as with the §2 drift table).
     The cost is a small tooling PR, plus one test that a build reproduces bit-identically from a committed pool.
   - **(b) Accept live values.** Builds stay as they are and are not reproducible between refreshes. Record the revision count
     in the run notes.
2. **Close gate 13b?** The tooling works end to end in the container. With (a), 13c on the next Novi vintage is the first
   live refresh, and every store is its own go.
3. **Remove the rehearsal container?** It holds runs 19 (header only), 24 and 26.
   `python -m scripts.box_rehearsal down` removes it; I'd keep it until you have read this.

