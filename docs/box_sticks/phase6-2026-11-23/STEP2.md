# BOX sticks phase 6, step 2: the code, proven in the rehearsal container and on a pilot

Written 2026-11-23. **Nothing is applied on live.** Every write below went to the `box-rehearsal` container
(`scripts.box_rehearsal`: a throwaway database seeded read-only from live). Builds and measures read live, read-only.

Branches: engineering_db `claude/box-sticks-phase6`; erebor `claude/box-sticks-cutover`. **Neither may merge before the cutover
window** (see "Merge order").

## What changed

| Area | Change |
|---|---|
| Forecast universe | `box.production.universe(source="box_sticks")`: the basin's record stick set with the nightly status. A producing stick is not in it; a conflict or crowded stick is `not_covered_conflict` in either basin; every stored stick is in-extent, its inside share kept on the row |
| Harness locations | spacing and completed lateral from the generator (`spacing_source = generator`); no nearest-neighbour search |
| Build and store | `build --source box_sticks` (both builds). A BOX stick is its location (`stick_id = location_id`): no vintage crosswalk, no `box.location_source` row, `box.location` only read. The run records its stick set and refuses to store once another set is the record. A base store never becomes the record |
| Proximity | `box/stick_legs.py`: each leg measured on its own, the stick takes its more exposed leg (no forecast first, then the lower factor), stored links are that leg's. TVD = the stick's landing depth; a stick without one is refused. Realized / conflict / crowded from `curated.box_location_status` |
| Constraints | sql/79: three CHECKs on `box.pud_forecast` widened (`recon_status`, `spacing_source`, the conflict rule) |
| Locations for the apps | sql/22: the undrilled arm of `curated.erebor_locations` = the record BOX sticks (category `BOX`, one LineString per stick, DSU id, nightly status). sql/78: `curated.novi_stick_locations` keeps the Novi arm, column for column, and deal-intake reads it there |
| Pruner | a BOX-stick run awaiting the cutover is kept while its basin's record is on Novi sticks |
| erebor | BOX sticks are the locations: one gunbarrel point per leg with an axial frame, Highgrade grouped by DSU id on `raw_novi_intel.pads`, hover and texts, the workup on BOX ids, the preview removed |

Measured on `prox_study.pair_signed` before changing anything: taken as one line, a two-leg stick's gap and side come out as the
nearer leg's, but its overlap is halved. A producer alongside half of one leg reads 0.25, under the 0.30 threshold.

## Found on the way (not in the step 1 design)

1. **deal-intake reads Novi sticks from `curated.erebor_locations`.** Hence sql/78.
2. **The land team reads `curated.erebor_locations` directly in GIS** (sql/31 says so). After the cutover its undrilled rows are BOX
   sticks and the Novi-only columns on them are NULL (Novi NPV / PV / EUR, depletion tier, the offset-support family). A QGIS
   filter on those returns nothing. `curated.box_scout_locations` is unaffected.
3. **erebor's Highgrade grouped sticks through `curated.intel_pad_member`, keyed by Novi stick id.** BOX sticks are not in it, and
   `curated.intel_pad_geom` lacks 254 Midland DSUs (2,603 sticks) that never held a Novi stick. Hence the DSU id column and the
   polygons read from `raw_novi_intel.pads`.

## Rehearsal container

| Step | Result |
|---|---|
| Seed and mirror | 15 `box` tables and 13 curated / raw relations equal to live by row count |
| sql/79 | applied: 10 of 10 checks |
| Location swap (`apply_box_stick_locations --container`) | rehearsal 22 of 22 checks, then committed: 22 of 22, 8 seconds for the whole transaction |
| Undrilled rows after the swap | Delaware 46,032, Midland 33,106 = record sticks not producing, by identity |
| Producing-well rows | unchanged: 31,949 and 29,043 |
| `curated.novi_stick_locations` | 257,397 = the Novi PUD + RES sticks = the undrilled rows the relation carried before |
| Concurrent refresh; tile predicate | 2.9 s; uses `idx_erebor_locations_geom` |

## Pilot: Delaware AVA_0 on BOX sticks, end to end

One bench, built from committed code (`8db8b7b`) against live (read-only), stored and flipped in the container.

| Stage | Result |
|---|---|
| Universe | 46,032 sticks; 477 on AVA_0 carry a forecast |
| Build | pool 256 wells, data through 2026-09; 477 locations fitted in 262 s on 7 workers; harness equivalence on 24 sampled locations: max relative difference 0.0. 629 s in all |
| Base store (run 33) | every identity check passes: 46,032 rows = universe; 477 oil and gas streams; every stream's 600 months sum to its EUR within 0.1 % |
| Water | 477 of 477 locations, 0 without water; store identities pass |
| Proximity measure | 477 sticks (63 U-turn, measured leg by leg): 183 unexposed, 85 single parent, 107 multi parent, 102 no drilled precedent; factor 0.842 to 1.046 |
| Derived store (run 34) | every identity passes: 375 forecast locations; oil 247.140 MMbbl = source x new / old; gas and water identical to the source |
| Flip | refused without `--allow-unpriced`; with it run 34 is the Delaware record. Land team's view: 0 -> 375 rows, econ on 0 of 375 |
| Pruner (dry run) | would prune the outgoing record and the base run; keeps both records |

AVA_0 in the pilot: 79 % of its inventory sticks carry a forecast (375 of 477). Bar P3 (80 %) is per basin and is scored in step 3.

## erebor against the container (branch `claude/box-sticks-cutover`)

144 backend tests pass (130 before); `tsc` clean. Over HTTP: tiles at zoom 7, 11 and 13 (carry `tvd` and `recon_status`); the
preview tile endpoint answers 404; gunbarrel under both rules (a U-turn stick as two points 1,235 ft apart); selection;
Highgrade pads (Delaware 4,401 pads, 46,032 sticks, 0 without a pad, 0 without a polygon; Midland 3,536 pads, 33,106 sticks, 0
and 0); the per-DSU gunbarrel; run metadata. In the browser: 77,981 Delaware locations (46,032 BOX sticks + 31,949 producing
wells), the legend on run 34's 375 forecast locations, the selection panel "not yet priced on BOX run 34", a gunbarrel of 145
points with "21 U-turn sticks drawn as 2 legs".

Not checked: the Accuracy tab and a producing well's production overlay (their tables are not in the container); Midland
forecasts (no Midland pilot was built).

## Merge order (both PRs are drafts until the cutover window)

Merging either one early breaks something on live:

- engineering_db: deal-intake would read `curated.novi_stick_locations`, which does not exist until the swap; and a quarterly
  `apply_erebor_locations` would do the swap on its own.
- erebor: Highgrade reads `el.pad_id`, a column the live relation does not have until the swap.

At the window: apply sql/79; store both runs (step 3 does the builds beforehand); `apply_box_stick_locations --go`; merge
engineering_db; flip both records unpriced; merge erebor and restart it; verify.

## For step 3 (the two full builds): choices to make first

- **Data through.** Runs 30 and 32 were built on production through 2026-08 and 2026-07. A build today reads through 2026-09 (the
  pilot did). Newer data is better for the record, but it mixes a data change into the comparison with runs 30 / 32 (bar P4).
- **Analog pools.** The pilot used the pool directories of the record (`docs/box/pool-2026-10-15` and the step-15 sets; Midland
  `pool-midland-2026-10-31`). The refresh chain's first step is a pool refresh that Michael confirms; reusing the record's pools
  skips it.
- Time: the pilot fitted 477 sticks in 262 s on 7 workers, which scales to about 7 hours for the Delaware's 45,776 and about 5
  for the Midland's 33,057, plus water and stores.
