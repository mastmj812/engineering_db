# BOX sticks phase 6, step 4, stage B: the cutover is live

Written 2026-11-24. Each step on Michael's explicit go ("Run it now", in working hours by his choice; "Go, flip both").
**The BOX forecasts of record now run on BOX sticks in both basins.** Econ is blank until Steven prices runs 36 and 38.

## What was done, in order (UTC)

| Time | Step | Result |
|---|---|---|
| 17:17:05 to 17:17:29 | B1 `apply_box_stick_locations --go` | COMMITTED in 20 s, 22 of 22 checks. sql/78 9 s, sql/22 4 s. Concurrent refresh 2.6 s; the tile predicate uses `idx_erebor_locations_geom` |
| 17:18:27 | B2 engineering_db PR 275 merged (Michael) | main carries sql/22 (BOX sticks), sql/78, sql/79, the batch on BOX sticks; deal-intake reads `curated.novi_stick_locations` |
| 17:18:34 | B4 erebor PR 33 merged (Michael) | the running erebor (`--reload`) picked the code up after a pull of its main checkout |
| 17:18:57, 17:19:02 | B3 `box_record23 flip --allow-unpriced --commit`, Delaware run 36, Midland run 38 | both COMMITTED; the land team's view filled as each flip landed |

The land team's view was empty from 17:17:29 to 17:18:57 (Delaware) and 17:19:02 (Midland): about a minute and a half.

## Cutover bars (DESIGN.md), read back from live

| Bar | Result |
|---|---|
| C1 locations | **Pass.** Undrilled rows = record sticks not producing: Delaware 46,022 = 46,022; Midland 33,094 = 33,094. Producing-well rows unchanged: 31,949 and 29,046. `stick_id` unique. The geography indexes rebuilt and used (EXPLAIN). `curated.novi_stick_locations` = 257,397 = the Novi PUD + RES rows the relation carried before |
| C2 records | **Pass.** Delaware run 36, Midland run 38. Runs 30 and 32 kept, not record (also the base runs 33 and 37) |
| C3 land team's view | **Pass.** Delaware 40,632 rows, Midland 28,668 = the records' forecast rows on undrilled sticks; econ NULL on every row. `analyst_ro` can read all three relations |
| C4 erebor | **Pass on what was checked.** Every BOX stick has a row of the record run (0 without). Coverage on the map: Delaware 17,972 validated, 22,660 provisional, 5,077 no forecast, 313 conflict or crowded; Midland 14,615 / 14,053 / 4,308 / 118. A 2-mile box per basin through the running app equals an independent SQL count (Delaware 443 locations + 343 wells; Midland 210 + 210); the app reports run 36 / 38 and `econ: null`. Tiles, gunbarrel, Highgrade (valued 40,632 and 28,668) return on both basins |
| C5 nightly | **Open** until the 2026-11-25 nightly (05:00 CT) is green and refreshes the relation |

Not checked: the econ panel's "not yet priced" wording in the browser on live (checked on the pilot in step 2; the API returns
`econ: null`). The console error `Source "ov-outline" already exists` on a basin switch is still there (overlay code, not
part of this change; the map draws).

## What a reader sees now

| | Before (runs 32 / 30, Novi sticks) | Now (runs 36 / 38, BOX sticks) |
|---|---|---|
| Delaware forecast locations | 48,148 | 40,632 |
| Delaware oil, forecast locations | 25,421 MMbbl | 22,495 MMbbl |
| Midland forecast locations | 28,801 | 28,668 |
| Midland oil, forecast locations | 11,078 MMbbl | 11,344 MMbbl |
| Land team's view | 48,077 + 28,754 rows, 72,959 priced | 40,632 + 28,668 rows, none priced |

50-year technical EUR, production data through 2026-09. Stick ids are new (10,000,001 and up): a saved list of Novi stick ids
matches nothing in the new relation; the Novi sticks are in `curated.novi_stick_locations`.

## Left to do

- C5: read the 2026-11-25 nightly.
- Tell Steven the two runs need pricing (runs 36 and 38, deck `wti70_hh3`); a post to #eng-updates needs Michael's go.
- On a later go: prune the base runs 33 and 37 (about a third of the rows stage A added), then runs 30 and 32.
- Going back, if ever needed: flip to runs 32 / 30, revert PR 275 and erebor PR 33, re-apply the old sql/22.
- Housekeeping: PR 274 (docs) open; PR 261 (shadow reports) conflicts with main; the rehearsal container is still up.
- The data dictionary is regenerated in this commit.
