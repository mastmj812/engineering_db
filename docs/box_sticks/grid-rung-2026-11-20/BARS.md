# BOX sticks generator: the geologist's grids in the landing chain: bars

Written 2026-11-20, **before anything is authored or run**. Committed on its own first. Branch
`claude/box-sticks-grid-rung`, cut from main at `3b101ed`. A DRAFT for Michael's review: nothing below is built until he
agrees the changes and the bars.

Decided 2026-11-20 (plan decision table; basis `docs/box_sticks/pinned-depth-2026-11-20/LANDING_TRACE.md`, PR #267): the
grids are a witness against wells and an arbiter where control is weak. Direct control always outranks the grid; the XY top
has no arbiter role; Delaware only.

**Not in this change:** the same-tag 500 ft test (open; Michael withdrew it as a generator rule), any tag work, the nightly
reconciliation, any regeneration or record flip (each its own explicit go).

## The two changes proposed

**1. A `grid` rung in place of the `offset` rung.** Where a Delaware bench in a DSU would take its landing from the offset
rung, it takes it from the grid: the bench's gridded top plus the bench's fractional position times the gridded
thickness there. The fraction is learned per bench from producing wells with depth evidence whose tag sits in its own
gridded interval, **regionally** (revision 1, below). Grids: `Grids_10-19-26` (V5).

| Bench | Interval | In the grid rung |
|---|---|---|
| BS1_S | `1BSPGS` to `2BSPGC` | yes |
| BS2_S | `2BSPGS` to `3BSPGC` | yes |
| WCA_1, WCA_2 | `WOLFCAMP_A` to `WOLFCAMP-B1` | yes |
| BS3_C, BS2_C | `3BSPGC` to `3BSPGS`; `2BSPGC` to `2BSPGS` | **candidates** (revision 1): with a basin-wide fraction the grid lost to the offset rung; with the regional fraction it did not. G1 decides per bench |
| BS3_S, WCXY | `3BSPGS` to `WOLFCAMP_XY`; `WOLFCAMP_XY` to `WOLFCAMP_A` | **yes, for depth only** (Michael 2026-11-20). The XY top still decides no tag and no bench membership |
| Avalon, WCB_1, WCB_2, WCC, WCD | no trusted surface pair | no |

**2. A bound on every carried landing.** A thickness, bracket or offset landing that falls more than 150 ft outside its
bench's gridded interval is **pulled to the grid's prediction** (Michael 2026-11-20: pull, not flag only) and flagged `grid_bounded` on the bench and its sticks. The
same benches as the table, plus BS3_C and BS2_C (the interval is trusted there even where a single fraction is not). Direct
landings are never bounded; a direct landing outside the interval is only flagged `outside_grid`.

Unchanged: the direct and thickness rungs themselves, the bracket rung, stack reconciliation, row grids, spacing, culls,
identity, everything in the Midland.

## Bars

Hold-out design is the generator's own (phase 1b / 1c): a well's landing is predicted with every well within the
exclusion radius removed (5 miles for the far rungs), and the error is the absolute difference to the well's depth
evidence. Producing wells only; permits and planned surveys are never depth evidence.

| Bar | Measure (grain) | Passes when |
|---|---|---|
| G1 | Grid rung against the offset rung, same held-out wells, per bench adopted (wells) | grid median error <= offset median error, and grid 90th percentile <= offset 90th percentile + 10 ft, on **each** of BS1_S, BS2_S, WCA_1, WCA_2. A bench that fails keeps the offset rung, and is reported as failed, not dropped quietly |
| G2 | The bound, on held-out wells whose carried prediction falls more than 150 ft outside the gridded interval (wells) | pulling to the grid lowers the median error per rung (thickness, bracket, offset), and at least 60 % of those wells move closer to their true depth |
| G3 | Direct landings (DSU x bench) | 0 changed against set 16's generator on the same inputs |
| G4 | Midland (sticks) | set regenerated on the same inputs is identical: same sticks, same depths |
| G5 | Stack order in the Delaware (DSU x bench) | benches dropped in a depth conflict (`reconciled_out`) do not increase against the same inputs without the change (580 on set 16) |
| G6 | Landings more than 150 ft outside their gridded interval, carried rungs, after the change (DSU x bench) | 0 on the benches the bound covers (it is the bound's definition; a non-zero count is a bug) |
| G7 | A files-only regeneration on set 16's own inputs (sticks) | reported, no bar on the count: sticks added, sticks stopped, ids carried; **at least 95 % of ids carried** |
| G8 | Grid files missing or a surface null at a DSU | the generator falls back to today's rung and says so; it never fails and never invents a depth. `pytest -q` green; ruff clean on touched files |

G1 decides change 1; G2 decides change 2. If one fails, it is reported as failed and only the other goes forward.

## Reported, no bar

- Landing depth change per bench and rung (median and 90th percentile of the shift), and a map of where.
- The 1,013 sticks of set 16 that sit more than 150 ft outside their gridded interval: where they end up.
- The 82 off-depth pinned sticks: how many remain after the change.

## Revision 1 (2026-11-20, after Michael's answers; still before anything is authored)

Decided by Michael: BS3_S and WCXY are **in, for depth only**; an out-of-interval carried landing is **pulled** to the
grid's prediction. He asked for a more regional basis for the fraction than basin or county.

**The fraction** is where in the gridded bench wells land: 0 at the top, 1 at the base. It differs by area (BS3_C county
medians run 0.46 to 0.84; WCA_2 0.28 to 0.67; BS2_C 0.21 to 0.74), so one basin value is a poor guess for some benches.

Tested (`fraction_basis_test.csv`; producing wells, every well within 5 miles removed before predicting it): median
absolute error in ft.

| Bench | Basin | County | Wells 5 to 10 mi away | 5 to 15 mi | 5 to 25 mi | Offset rung today |
|---|---|---|---|---|---|---|
| BS1_S | 63 | 58 | 56 | 58 | 62 | 87 |
| BS2_C | 102 | 73 | 73 | 72 | 75 | 94 |
| BS2_S | 64 | 68 | 69 | 67 | 65 | 98 |
| BS3_C | 94 | 83 | 67 | 71 | 82 | 82 |
| BS3_S | 57 | 54 | 49 | 49 | 51 | 86 |
| WCXY | 46 | 45 | 46 | 45 | 44 | 80 |
| WCA_1 | 63 | 64 | 53 | 55 | 57 | 71 |
| WCA_2 | 58 | 57 | 52 | 52 | 53 | 74 |

**Basis proposed: the distance-weighted median fraction of same-tag producers 5 to 15 miles away** (Gaussian weight,
7.5-mile scale, at least 10 wells); where there are fewer, widen to 25 miles, then the county, then the basin. It predicts
99 % or more of wells on every bench but BS1_S and BS2_C (94 to 96 %), is level with or better than the basin value on 7
of 8 benches, and brings the two carbonates under the offset rung, which is why they are candidates again.

Stated plainly: this basis was chosen by looking at this test. G1 is run in the generator's own hold-out and is the
confirmation, but it is the same wells, so it is not an independent test of the choice.

G1 as revised: the benches are BS1_S, BS2_S, BS3_S, WCXY, WCA_1, WCA_2, and the candidates BS3_C and BS2_C; each passes or
keeps the offset rung on its own.

## Questions for Michael (answered 2026-11-20; kept for the record)

1. **BS3_S and WCXY.** Both intervals are bounded by the XY top, which you ruled out as an arbiter because it misjudged
   bench membership on the tag cards. For landing depth alone they were the grid's best benches (BS3_S 56 ft against the
   offset rung's 86; WCXY 46 against 80). As drafted they are left out. Include them for depth only?
2. **Pull or flag.** As drafted an out-of-interval carried landing is pulled to the grid and flagged. The alternative is
   flag only, and you review the list (381 DSU x bench today).
3. **The fraction.** One median fraction per bench basin-wide, or per county? Basin-wide is what was tested.
