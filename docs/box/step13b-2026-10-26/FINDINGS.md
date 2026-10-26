# Step 13b — refresh tooling (2026-10-26). Tooling done; the container rehearsal waits on two calls from Michael.

This implements the D126 contract (`docs/box/step13a-2026-10-26/CONTRACT.md`). Nothing has been written to the database.

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

## 3. The container rehearsal (13b's acceptance), not yet run

**What it is:** `box_refresh build --pool docs/box/pool-2026-10-26 --out runs/box13b`, about 8 h read-only. Then the store
chain in the `scripts.box_rehearsal` container (base → water → proximity measure → proximity record), about 3 h.

**What it must show:**
- **The method is identical to run 19:** spec labels, rules, evidence-pack digest, haircut tables, and harness equivalence 0.0
  on every group.
- **Every per-group change in coverage, EUR and analogs is explained** by the two data movements:
  - production through 2026-10-01 instead of 2026-07-01;
  - the 134 new pool wells.
- **The run notes carry the D126 stamp.**

**Nothing reaches live from the rehearsal.** The live refresh is 13c, on the next vintage.

## 4. Your calls before the rehearsal

1. **Confirm the 134 added pool wells** (D84 gate). The pool directory is committed as proposed; the build refuses an
   uncommitted pool.
2. **A window for the ~8 h build** (laptop up and plugged in). The build resumes per group if it is interrupted.
