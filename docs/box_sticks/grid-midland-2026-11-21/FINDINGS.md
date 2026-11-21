# BOX sticks generator 0.14: the Midland grids, authored and scored

> **DECIDED 2026-11-21 (Michael: "Nothing for now").** The Midland table is NOT applied. This branch ships as a refactor with
> no change to any stick: `BASINS` holds the Delaware only, the Midland table stays in the module as `MIDLAND_TABLE` with the
> numbers below, the version is back to `box_sticks_0.13`, and only the Delaware grid files are inputs of a run. Section 8
> has the proof. Sections 1 to 7 describe the change as it was scored, before that decision.

2026-11-21. **Nothing applied, nothing stored, no record touched.** Files only: the cache of the pull that made sets 24
and 25 (2026-11-21 00:28 UTC) and the grid files. Bars: `BARS.md`, committed (`033abf0`) before the code and before the
hold-out was run. Branch `claude/box-sticks-grid-midland`, cut from main at `9fca1ac`.

**Two bars fail: M2 and M5.** M2 failing means the bound is not adopted for the Midland, as the bars said beforehand. M5
failing is a cost of the grid rung that the bars did not allow. Stated plainly below; nothing was tuned.

## 1. What was authored

| File | Change |
|---|---|
| `box/sticks/grid_rung.py` | A table per basin (`BASINS`): surfaces, the gridded interval of each bench, and what the hold-out admitted. The Delaware table is the 0.13 constants, unchanged. A Midland sampler reading `Grids/Midland/<newest dated folder>` |
| `scripts/box_sticks_phase3_pilot.py`, `box_sticks_phase3_backtest.py` | Pass a sampler per basin |
| `scripts/box_sticks_run.py` | The grid files of both basins are file inputs of a run, hashed in the manifest (0.13 did not record them) |
| `scripts/box_sticks_grid_rung.py` | `score --basin` |
| `box/sticks/core.py` | `VERSION = "box_sticks_0.14"` |
| `tests/test_box_sticks_grid_rung.py` | 3 new tests (11 in the file) |

Midland as built: the grid replaces the offset rung on **MS, JM, LSSH, DEAN and WCD**. WCA_1 keeps the offset rung. Nothing
is bounded and nothing is flagged. WCB_1, WCB_2, WCC and US are untouched (decided in the bars).

## 2. The bars

| Bar | Result | Verdict |
|---|---|---|
| M1 grid rung against the offset rung, held-out wells (5 miles removed) | grid wins on MS, JM, LSSH, DEAN, WCD; loses on WCA_1 | passes on 5 of 6; WCA_1 keeps the offset rung |
| M2 the bound, per rung | pulling to the grid makes every rung worse: bracket 78 to 378 ft median (18 % closer), offset 62 to 400 ft (21 %), thickness 39 to 440 ft (10 %) | **fails: no bound in the Midland** |
| M3 direct landings, both basins | 0 changed | passes |
| M4 Delaware on set 24's inputs | identical: 46,153 sticks, every depth, 0 landings changed | passes |
| M5 Midland benches dropped in a depth conflict | 202 before, 210 after | **fails** |
| M6 carried landings still outside where the bound applies | no bound, so nothing to check | n/a |
| M7 files-only regeneration of the Midland | 99.68 % of ids carried (33,016 of 33,122); 106 stop, 75 start; 33,091 sticks | passes |
| M8 grid missing or null, or a basin without a table | tests: chain unchanged, no error. `pytest -q` 1,198 passed, 53 skipped; ruff clean on touched files | passes |

M1, median absolute error in ft (90th percentile):

| Bench | Wells scored | Grid | Offset rung | |
|---|---|---|---|---|
| MS | 1,587 | 36 (99) | 39 (115) | grid |
| JM | 1,758 | 43 (135) | 45 (142) | grid |
| LSSH | 4,925 | 48 (139) | 54 (148) | grid |
| DEAN | 811 | 41 (138) | 45 (155) | grid |
| WCD | 855 | 43 (143) | 87 (239) | grid, by half |
| WCA_1 | 6,832 | 47 (167) | 47 (128) | offset stays |

## 3. Why the bound fails: the Wolfcamp A top in Borden and Howard

Of the held-out wells whose carried landing falls more than 150 ft outside the gridded interval, most are WCA_1 (337 of
420 on the offset rung), and there the carried landing was **right** (49 ft median error) and the grid wrong (442 ft).

Those wells sit above the gridded Wolfcamp A top: 381 of 7,216 WCA_1 evidence wells are more than 150 ft above it (median
350 ft), and they are in two counties.

| County | WCA_1 wells | More than 150 ft above the gridded Wolfcamp A top |
|---|---|---|
| Borden | 226 | 145 (64 %) |
| Howard | 1,654 | 231 (14 %) |
| Reagan | 857 | 5 |

Either the Wolfcamp A top is gridded about 350 ft too deep on that side of the basin, or those wells are tagged WCA_1 and
land in what the geologist calls Dean or Lower Spraberry. That is a question for the geologist (and possibly a tag class);
list in `wca_wells_above_gridded_top.csv`. Until it is settled the Midland grids cannot be allowed to overrule a landing.

In the small cells where the bound would have helped (JM 9 wells, LSSH 38, WCD 38, about 250 to 450 ft down to about 30
to 120 ft) it is not adopted either: the bar was per rung, and it failed.

## 4. What the regeneration does to the Midland (files only, set 25's inputs)

- 1,565 DSU x bench move from the offset rung to the grid rung (1,445 with sticks): MS 325, JM 129, LSSH 206, DEAN 137,
  WCD 768. Sticks on the grid rung: 4,294.
- Depth shift of those landings: median 47 to 74 ft by bench; 90th percentile 107 ft (JM) to 449 ft (DEAN).
- Sticks: 33,122 to 33,091. 86.9 % of carried sticks keep their depth exactly.
- **M5: 9 DSU x bench newly dropped in a depth conflict and 1 restored.** DEAN 3 (5 sticks lost) and LSSH 1 (2) on the grid
  rung itself; LSSH 3 (17), LSSH 1 on thickness (6) and WCA_1 1 (2) are neighbours that now conflict with a moved landing.
  32 sticks lost, 3 gained.

## 5. Reading

- The Delaware is untouched by this change (M4), and the refactor is safe to merge on that count.
- For the Midland the grid rung is a small gain on four benches (2 to 6 ft on the median) and a large one on WCD (87 to 43
  ft), at the price of 8 more benches dropped in depth conflicts, which the bars did not allow.
- The bound, which looked like the most useful part before the hold-out, is not usable: the Wolfcamp A grid disagrees with
  the wells in Borden and Howard.

## 6. Choices (Michael's)

1. **WCD only.** Keep the grid rung where the gain is real and leave MS, JM, LSSH and DEAN on the offset rung. All 9 newly
   dropped benches are LSSH, DEAN or their neighbours, so this should avoid them, but it has not been run; it needs one
   more files-only regeneration to check M5.
2. **All five benches as built**, accepting M5 as failed (8 benches, about 29 sticks net).
3. **Nothing for the Midland now.** Merge only the refactor (Delaware identical) or drop the branch, and return when the
   geologist has looked at the Wolfcamp A top in Borden and Howard and delivered a usable Wolfcamp B Lower.

## 7. Not done

- Nothing live: no store, no flip. The schema already accepts the rung (sql/77).
- The 20 offset landings that changed depth without changing rung were not traced (stack reconciliation, as in 0.13).
- No back-test was run on 0.14 (a store needs one).

## 8. As shipped: nothing changes (after "Nothing for now")

The landing frame was rebuilt with the shipped code on the inputs of sets 24 and 25 and compared with the frame that made
them: 49,554 DSU x bench rows, the same in both, and **0 differences** in landing depth, rung, anchor, expected error,
spacing, second level and grid note. The Midland has no grid landing (rungs: direct 10,886, thickness 4,726, offset 2,108,
bracket 822, none 1,293), the Delaware its 2,980. So a regeneration with this code gives sets 24 and 25 again.

What is kept for when the Midland comes back: the table and its hold-out numbers in `box/sticks/grid_rung.py`, `score
--basin midland`, the tests that run the table explicitly, this evaluation, and the list of Wolfcamp A wells above the
gridded top in Borden and Howard for the geologist.
