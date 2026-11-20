# BOX sticks generator 0.13: the grids in the landing chain, authored and scored

2026-11-20. **Nothing applied on live, nothing stored, no record touched.** Files only: the scoring and the regeneration
read the cache of the run that made sets 16 and 17 (pull 2026-11-19 01:00 UTC) and the grid files. Bars: `BARS.md`
(draft `94abe3e`, revision 1 `e2b5347`, both before any code). Branch `claude/box-sticks-grid-rung`, cut from main at `3b101ed`.

All eight bars pass as written. Three things I did that the bars did not spell out are in section 4; read those before
agreeing.

## 1. What was authored

| File | What it is |
|---|---|
| `box/sticks/grid_rung.py` | The grid rung and the grid bound. Pure but for the grid sampler; a missing grid or a null surface leaves the chain as it was |
| `scripts/box_sticks_phase3_pilot.py` | One line after the landing chain is built: `grid_rung.apply_to_chain(...)`; the frame carries `grid_note` |
| `box/sticks/reads.py`, `store.py`, `core.py` | `grid` is a carried rung; stick flags `grid_bounded` and `outside_grid`; `VERSION = "box_sticks_0.13"` |
| `sql/77_box_sticks_grid_rung.sql`, `scripts/apply_box_sticks_grid_rung.py` | Three CHECK constraints of sql/73 widened for the new rung and flags. **Authored only.** A 0.13 set cannot be stored until this is applied, on its own go |
| `scripts/box_sticks_grid_rung.py` | The scoring (`score`) and the set comparison (`compare`) |
| `tests/test_box_sticks_grid_rung.py`, `tests/test_box_sticks_store.py` | 8 new tests; the store test now reads sql/77 for the widened checks |

The rule as built (Delaware only): the fraction is the distance-weighted median fractional position of same-bench evidence
wells 5 to 15 miles from the DSU (at least 10), widened to 25 miles, then the basin median. Wells inside 5 miles never
teach it, because that is the situation it was tested in.

## 2. The bars

| Bar | Result | Verdict |
|---|---|---|
| G1 grid rung against the offset rung, same held-out wells (5 miles removed), per bench | grid wins on all eight; table below | passes |
| G2 the bound, on held-out wells predicted more than 150 ft outside the interval | bracket 266 to 74 ft median, 80 % closer (322 wells); offset 244 to 81 ft, 77 % (1,059); thickness 234 to 103 ft, 70 % (675; approximated, section 4) | passes |
| G3 direct landings | 0 changed of 14,352 | passes |
| G4 Midland | identical: 33,138 sticks, every depth | passes |
| G5 benches dropped in a depth conflict, Delaware | 580 before, 545 after | passes |
| G6 carried landings still more than 150 ft outside, where the bound applies | 0 | passes |
| G7 files-only regeneration on set 16's own inputs | 99.28 % of ids carried (45,730 of 46,062); 332 sticks stop, 333 start; 46,063 sticks | passes |
| G8 grid missing or null | tests: the chain is returned unchanged, no error. `pytest -q` 1,193 passed, 53 skipped; ruff clean on touched files | passes |

G1, median absolute error in ft (90th percentile), evidence wells of each bench:

| Bench | Wells scored | Grid | Offset rung |
|---|---|---|---|
| BS1_S | 989 | 60 (182) | 66 (223) |
| BS2_C | 575 | 76 (224) | 80 (246) |
| BS2_S | 3,617 | 65 (195) | 98 (257) |
| BS3_C | 1,416 | 72 (217) | 80 (218) |
| BS3_S | 2,396 | 48 (154) | 66 (200) |
| WCXY | 1,820 | 46 (126) | 73 (195) |
| WCA_1 | 4,980 | 56 (137) | 65 (199) |
| WCA_2 | 3,915 | 53 (145) | 68 (209) |

The two carbonates pass narrowly (4 and 7 ft on the median); the others by 6 to 34 ft.

## 3. What the regeneration does (Delaware, files only)

| Landing rung (DSU x bench) | Set 16's generation | Generator 0.13 |
|---|---|---|
| direct | 14,352 | 14,352 |
| thickness | 9,043 | 8,754 |
| bracket | 1,258 | 1,225 |
| offset | 3,440 | 753 |
| grid | 0 | 3,009 |
| none | 1,626 | 1,626 |

- 2,687 landings move from the offset rung to the grid rung; 322 carried landings are pulled in by the bound (thickness
  289, bracket 33; every offset landing on a covered bench already went to the grid rung); 320 landings carry `outside_grid` and are not
  moved (266 direct, 54 in the skipped cells of section 4).
- The 753 landings left on the offset rung are benches with no trusted surface pair (Avalon, WCB_1, WCB_2, WCC, WCD) or
  DSUs where the grid is null.
- Basis of the 3,009 grid landings: wells 5 to 15 miles away 2,842; widened to 25 miles 164; basin median 3.
- 2,363 DSU x bench change landing depth: median shift 90 ft, 90th percentile 323 ft.
- 92 of those change depth without changing rung (thickness 77, bracket 9, offset 6). Not traced; the likely cause is the
  stack reconciliation shifting a bench against a neighbour that moved.
- Sticks: 46,062 to 46,063. 86 % of carried sticks keep their depth exactly (39,806 of 45,730).
- The off-depth pinned sticks are untouched by this change, as expected: of the 69 in the Delaware, 64 are still there and
  63 are still 150 to 500 ft from their well. Their cause is two landings in one bench, not a carried depth.

## 4. Three things beyond the bars, stated

1. **Three bench x rung cells are left out of the bound.** G2 passes per rung, as written. Broken down by bench
   (`g2_by_bench_rung.csv`) the pull makes three cells worse in the hold-out: BS1_S thickness (52 to 319 ft median, 54
   wells), BS3_C thickness (248 to 387 ft, 23 wells) and BS3_C bracket (180 to 506 ft, 10 wells). I left those three
   unbounded (`BOUND_SKIP`); they carry `outside_grid` instead (54 DSU x bench). This was decided after seeing the result.
   The alternative is to bound everything as the bar reads; say which.
2. **The thickness rung in G2 is approximated.** Its own hold-out lives in another design (phase 1); here it is the ranked
   anchor with the nearest same-bench wells beyond 1 mile. Bracket and offset use the generator's own far-rung hold-out.
3. **No county step in the fallback.** The bars said 15 miles, then 25, then the county, then the basin. The evidence frame
   has no county; the code goes 15, 25, basin. Three of 3,009 landings reach the basin step.

Also: the basis was chosen on an exploratory test of the same wells (stated in the bars), so G1 confirms it without being
independent of it.

## 5. What is needed before any of this is live

Each its own explicit go, in this order:

1. `python -m scripts.apply_box_sticks_grid_rung` (sql/77): three CHECK constraints on `box.location_stick` and
   `box.location_set_bench`. A brief lock on each table while 159,738 stick rows are re-validated; no row changes.
2. A fresh pull, generate, and `store` of a 0.13 Delaware set (stored NOT record).
3. The record flip. The nightly reconciliation then re-judges on the new set, logged as `set_change`.

The Midland is unchanged by 0.13 and needs no new set. BOX forecasts are not touched by any of this.

## 6. Not done

- WCB_1, WCB_2, WCC, WCD and the Avalon benches: no trusted surface pair, so they keep the offset rung (753 landings).
- The same-tag question and the tag corrections: separate track.
- The data dictionary is not regenerated (it reads live; sql/77 is not applied).
