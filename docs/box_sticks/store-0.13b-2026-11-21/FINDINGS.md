# BOX sticks: sets 24 and 25 are the records (generator 0.13 on the corrected tags)

2026-11-21. Michael's "go ahead" on a new pull, store and record flip after the 19 tag corrections of 2026-11-20 (seed
reload finished 00:10 UTC, PR #269). **Set 24 is the Delaware record and set 25 the Midland record** (the Midland on his "Go Midland"); sets 21 and 17 are
superseded and kept. The forecast records (run 32 Delaware, run 30 Midland) are untouched.

Files here: `manifest.json` (the pull), `summary_<basin>.json`, `backtest_summary.json`, `store_delaware.log`,
`record_flip_24.log`, `rehearsal_midland.log`.

## What was stored

Generator `box_sticks_0.13` from `c03b7f5` (main after PR #269; clean tree), narvi `bfc7955` (pinned = installed). One pull
for both basins, 2026-11-21 00:28:57 UTC, tag rule run 12, with the 19 human calls in force.

| | Set 24, Delaware |
|---|---|
| Stored / made record (UTC) | 2026-11-21 01:11 to 01:18 / about 01:20 |
| Sticks / legs | 46,153 / 54,281 |
| DSUs / DSU x bench / wells read | 5,072 / 29,719 / 33,166 |
| Ids carried from set 21 | 45,585 of 46,132 (98.8 %) |
| New ids / ids of set 21 that stop | 568 / 547 |
| Store checks | 10 of 10 ok; 5,072 DSUs regenerated from the stored rows, 0 differences |
| Record flip checks | 7 of 7 ok (dry run first) |

Sticks by landing rung: direct 16,523; thickness 19,240; grid 5,896; bracket 2,553; offset 1,941.

547 sticks stop and 568 start against set 21, from 18 well tags moving. That is more than the wells themselves: a tag
feeds the 2-mile landing surfaces and the row grids around it. It was not broken down by well.

## Back-test stored with the set (pilot areas, cutoff 2023-01-01)

Unchanged in substance from set 21: T1 59.9 % (fails by 0.1 point), T2 4.2 % (passes), T3 63.5 % (fails), T4 36.4 %
(fails), direct rung 55.1 ft and 83.2 % within 150 ft (passes), grid rung 34.5 ft on 23 pairs (passes), offset 1.33 x
(passes), thickness 1.53 x and bracket 2.04 x (fail).

## Live, verified from a second read-only connection

| | Before | After |
|---|---|---|
| `box.location_set` | 5 rows; records 21 and 17 | 6 rows; records **24** and 17; 21 superseded by 24 |
| `box.location_stick` | 205,870 | 252,023 (= + 46,153) |
| `box.location` | 337,151 | 337,719 (= + 568); Novi rows unchanged (252,925) |
| Record sticks | 79,270 | 79,291 |
| Forecast records | runs 30 and 32 | the same |

Set ids 22 and 23 were used up by the rolled-back rehearsals.

## The Midland: set 25, stored and made the record ("Go Midland")

From the same pull as set 24. Generator 0.13 does not change the Midland; the small movement is the inputs having moved
since the 2026-11-19 pull (Novi v4, tag-rule runs).

| | Set 25, Midland |
|---|---|
| Stored / made record (UTC) | 2026-11-21 01:23 to 01:28 / 01:29 |
| Sticks / legs | 33,122 / 36,695 (33,138 sticks in set 17) |
| DSUs / DSU x bench / wells read | 4,385 / 19,835 / 30,713 |
| Ids carried from set 17 | 33,099 of 33,138 (99.9 %) |
| New ids / ids of set 17 that stop | 23 / 39 |
| Store checks | 10 of 10 ok (rehearsed first); 4,385 DSUs regenerated from the stored rows, 0 differences |
| Record flip checks | 7 of 7 ok (dry run first) |

Sticks by landing rung: direct 14,261; thickness 11,788; offset 5,732; bracket 1,341. No grid rung: the Midland grids are
not in the generator.

Live after both flips, from a second read-only connection: 7 sets, records **24 and 25**; 285,145 stick rows
(= 252,023 + 33,122); 337,742 locations (= 337,719 + 23), Novi rows unchanged (252,925); record sticks 79,275;
forecast records still runs 30 and 32.

## Shadow week

No nightly had judged set 21, and both flips were done before the nightly of 2026-11-21, so the count does not restart
again: night 1 is that nightly, on sets 24 and 25. `docs/box_sticks/phase5d-2026-11-19/RESTART.md` (draft PR #261) has the note.
