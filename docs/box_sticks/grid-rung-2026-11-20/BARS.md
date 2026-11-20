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
rung, it takes it from the grid: the bench's gridded top plus the bench's median fractional position times the gridded
thickness there. The fraction is learned per bench from producing wells with depth evidence whose tag sits in its own
gridded interval. Grids: `Grids_10-19-26` (V5).

| Bench | Interval | In the grid rung |
|---|---|---|
| BS1_S | `1BSPGS` to `2BSPGC` | yes |
| BS2_S | `2BSPGS` to `3BSPGC` | yes |
| WCA_1, WCA_2 | `WOLFCAMP_A` to `WOLFCAMP-B1` | yes |
| BS3_C, BS2_C | | **no** (the grid lost to the offset rung there); they keep the offset rung |
| BS3_S, WCXY | bounded by the XY top | **no**, because the XY top has no arbiter role. See question 1 |
| Avalon, WCB_1, WCB_2, WCC, WCD | no trusted surface pair | no |

**2. A bound on every carried landing.** A thickness, bracket or offset landing that falls more than 150 ft outside its
bench's gridded interval is **pulled to the grid's prediction** and flagged `grid_bounded` on the bench and its sticks. The
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

## Questions for Michael before anything is authored

1. **BS3_S and WCXY.** Both intervals are bounded by the XY top, which you ruled out as an arbiter because it misjudged
   bench membership on the tag cards. For landing depth alone they were the grid's best benches (BS3_S 56 ft against the
   offset rung's 86; WCXY 46 against 80). As drafted they are left out. Include them for depth only?
2. **Pull or flag.** As drafted an out-of-interval carried landing is pulled to the grid and flagged. The alternative is
   flag only, and you review the list (381 DSU x bench today).
3. **The fraction.** One median fraction per bench basin-wide, or per county? Basin-wide is what was tested.
