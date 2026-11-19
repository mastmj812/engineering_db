# Generator 0.12: store dry run on live (rolled back)

2026-11-19 00:18 to 00:31 UTC, on Michael's "dry run the store". `python -m scripts.box_sticks_run store --run <0.12 run>
--basin <b>` with no `--go`: one transaction per basin that writes the set, checks it, and **rolls back**. Nightly idle, no
other session holding a lock in `box`.

Run stored-and-rolled-back: generator `box_sticks_0.12` from `59fbc06`, pull 2026-11-18 22:37 UTC, tag run 8.

| | Delaware | Midland |
|---|---|---|
| Sticks in the 0.12 run | 46,062 | 33,138 |
| Ids carried from the record set | **44,788 from set 6 (97.2 % of the new sticks)** | **32,523 from set 7 (98.1 %)** |
| New ids | 1,274 | 615 |
| Ids of the record set that stop | 1,921 of 46,709 (4.1 %) | 1,306 of 33,829 (3.9 %) |
| The ten store checks | all ok | all ok |
| DSUs regenerated from the STORED rows against the stored sticks | 5,072 DSUs, 0 differences (336 s) | 4,385 DSUs, 0 differences (279 s) |

For scale: one ordinary night carried 99.65 % / 98.96 %, and the tag cutover 91.2 % / 89.8 % (gate 4a). The ids that stop are
mostly what the fixes were for: sticks that sat on or beside a well the 0.11 generator could not see.

## Live state before and after (second read-only connection)

| | Before (00:18 UTC) | After (00:31 UTC) |
|---|---|---|
| `box.location_set` rows / records | 2 / set 6 Delaware, set 7 Midland | 2 / the same |
| `box.location_stick` rows | 80,538 | 80,538 |
| `box.location` rows | 333,463 | 333,463 |
| Location id sequence | 10,127,259 | 10,129,148 |

Two things a rollback does not give back, both harmless and both the same as in gate 4c / 4d: the location id sequence moved
on by 1,889 (the 1,274 + 615 new ids), and set ids 12 and 13 are used up (8 to 11 went to earlier rolled-back attempts). The
next stored sets will carry higher numbers; no row refers to the skipped ones.

## What a real store would still need

- A fresh pull from a CLEAN checkout of main after PR #258 merges (this run's manifest says the tree was dirty, and the
  store refuses `--go` on that), and the back-test summary of 0.12 on that pull (`--backtest`, required with `--go`).
- Michael's explicit go for the store, per basin, and a separate go for the record flip. Not requested here.
- Nothing downstream changes on a flip today: nothing reads `box.location_set` yet, and the forecast records (run 32
  Delaware, run 30 Midland) stand on the Novi sticks.
