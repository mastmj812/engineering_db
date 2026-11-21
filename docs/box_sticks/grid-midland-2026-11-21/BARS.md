# BOX sticks generator 0.14: the Midland grids in the landing chain: bars

Written 2026-11-21, **before anything is authored or scored in the generator's hold-out**. Committed on its own first.
Branch `claude/box-sticks-grid-midland`, cut from main at `9fca1ac`. Michael: "start" (on building the Midland grids into
the generator).

What is already known, and was looked at before these bars: the exploratory evaluation of 2026-11-20
(`docs/box_sticks/grid-rung-2026-11-20/MIDLAND_GRIDS.md`). It used the same wells, so the bars below confirm it without
being independent of it. Its numbers set no threshold here; the thresholds are the Delaware's.

## The change proposed

The Delaware rules of generator 0.13, applied to the Midland with the grids delivered 2026-11-20
(`Grids/Midland/11-20-26`): a `grid` rung in place of the `offset` rung, and a bound that pulls a carried landing more than
150 ft outside its bench's gridded interval to the grid's prediction. Direct landings are never moved. Fraction from
same-bench wells 5 to 15 miles away, then 25 miles, then the basin.

| Bench | Interval | Grid rung | Bound |
|---|---|---|---|
| MS | Middle Spraberry to Jo Mill | candidate | candidate |
| JM | Jo Mill to Lower Spraberry Shale | candidate | candidate |
| LSSH | Lower Spraberry Shale to Dean | candidate | candidate |
| DEAN | Dean to Wolfcamp A | candidate | candidate |
| WCA_1 | Wolfcamp A to Wolfcamp B | candidate | candidate |
| WCD | Wolfcamp D to Strawn | candidate | candidate |
| WCB_1 | Wolfcamp B to (Wolfcamp B + 236 ft) | **no** | **no** |
| WCB_2 | (Wolfcamp B + 236 ft) to Wolfcamp C | **no** | **no** |
| WCC | Wolfcamp C to Wolfcamp D | **no** | **no** |
| US | | **no** (46 evidence wells) | **no** |

Decided here, before scoring, and stated as mine:

- **WCB_1, WCB_2 and WCC are left out entirely.** The geologist's Wolfcamp B Lower surface covers 10 % of the wells, so the
  WCB_1 / WCB_2 boundary would be a constant I derived (B + 236 ft), and the Wolfcamp C top falls above it at 11.8 % of
  wells. A depth must not be moved on a boundary nobody picked. They come in when the geologist delivers a usable surface
  or Michael adopts the constant.
- A candidate becomes part of the rung or the bound only by passing its bar, bench by bench; a bench or a bench x rung
  cell that fails keeps today's behaviour (the practice Michael confirmed for the Delaware on 2026-11-20).
- The Delaware is not changed by this: same tables, same constants, same code path.
- The grid files of both basins become file inputs of a run (hashed in the manifest), which 0.13 did not do.

## Bars

Hold-out as for 0.13: the generator's far-rung design, every well within 5 miles removed; evidence wells of the run's own
cache (pull 2026-11-21 00:28 UTC, the pull of sets 24 and 25).

| Bar | Measure (grain) | Passes when |
|---|---|---|
| M1 | Grid rung against the offset rung, same held-out wells, per candidate bench (wells) | grid median error <= offset median error, and grid 90th percentile <= offset 90th percentile + 10 ft. A bench that fails keeps the offset rung |
| M2 | The bound, on held-out wells whose carried prediction falls more than 150 ft outside the gridded interval, per rung (bracket, offset, thickness approximated) (wells) | pulling to the grid lowers the median error per rung, and at least 60 % of those wells move closer. Then per bench x rung cell: a cell where the median gets worse is left out and flagged `outside_grid` instead |
| M3 | Direct landings, both basins (DSU x bench) | 0 changed against sets 24 and 25 on their own inputs |
| M4 | **Delaware** (sticks) | a set regenerated on set 24's inputs is identical to set 24: same sticks, same depths, same flags |
| M5 | Benches dropped in a depth conflict, Midland (DSU x bench) | no increase against set 25's generation (reported with the count) |
| M6 | Carried landings more than 150 ft outside their gridded interval after the change, where the bound applies (DSU x bench) | 0 |
| M7 | Files-only regeneration of the Midland on set 25's inputs (sticks) | at least 95 % of ids carried; sticks added and stopped reported |
| M8 | Grid files missing, a surface null at a DSU, or a basin with no grid table | the chain is returned unchanged for that DSU or basin; never a failure, never an invented depth. `pytest -q` green; ruff clean on touched files |

M1 decides the rung per bench and M2 the bound. If neither admits anything, the change is reported as not worth making
and nothing ships.

## Reported, no bar

- Landing depth change per Midland bench and rung (median and 90th percentile of the shift).
- The 1,066 sticks of set 17 found more than 150 ft outside their gridded interval: how many remain on set 25's inputs.

## Not in this change

Anything live. The schema already accepts the `grid` rung and its flags (sql/77). A store and a record flip are each their
own explicit go, and a flip restarts the shadow count.
