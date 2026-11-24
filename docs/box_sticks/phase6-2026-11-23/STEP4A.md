# BOX sticks phase 6, step 4, stage A: sql/79 applied and both basins stored on live, not record

Written 2026-11-24, on Michael's "Go, stage A". **No reader sees a change:** the records are still runs 30 and 32,
`curated.erebor_locations` still carries the Novi sticks, the land team's view has the same rows. Stage B (the swap, the two
flips, the two merges) has not started and needs its own go.

## What was applied

| Go | Result |
|---|---|
| A1, sql/79 (`apply_box_pud_forecast_box_sticks --go`), 14:05 UTC, after the nightly finished green at 11:49 UTC | 11 of 11 checks: three CHECK constraints widened, 252,410 rows of `box.pud_forecast` unchanged (same fingerprint), records unchanged |
| A2, Delaware | base run **33** (45,776 forecast, 256 conflict; 1,257 s), water on it (45,776 streams, 9 calculated fallback; 1,612 s), measure on live (293,174 links; 375 s), derived run **36**, not record (2,057 s) |
| A2, Midland | base run **37** (33,057 forecast, 49 conflict; 991 s), water (33,057 streams; 807 s), measure on live (267,631 links; 404 s), derived run **38**, not record (1,502 s) |

Every identity of every store passes. **Live ids: Delaware derived = 36, Midland derived = 38** (the rehearsal container has them
the other way round: Delaware 38, Midland 36). Run ids 34 and 35 hold nothing (below). Code `349ce81` (docs-only commits after
`6620691`).

## Two things that went wrong, neither left anything on live

1. **The first Delaware derived store lost its connection** four minutes in, during the monthly-volume insert
   (`server closed the connection unexpectedly`). The store is one transaction: it rolled back. The server had not restarted
   (up since 2026-10-20). Cause not found. The second attempt committed.
2. **My first retry script was wrong** and started the Delaware base store a second time. Stopped after about a minute, before
   its commit; live was re-read and holds no second base run. The log of the real run 33 base store was overwritten by that
   attempt; its check lines are in `runs/live/first_chain_run33.out`.

## Live runs against the rehearsal's (stick by stick)

| | Delaware, live 36 vs rehearsal 38 | Midland, live 38 vs rehearsal 36 |
|---|---|---|
| Rows | 46,022 vs 46,032 (10 sticks turned producing) | 33,094 vs 33,106 (12 turned producing) |
| Forecast locations | 40,632 vs 40,685 | 28,668 vs 28,711 |
| Oil, forecast locations | 22,495.072 vs 22,518.625 MMbbl (-0.10 %) | 11,343.644 vs 11,357.345 MMbbl (-0.12 %) |
| Conflict or crowded | 313 vs 256: 53 sticks newly crowded, 4 newly conflict | 119 vs 49: 65 newly crowded, 5 newly conflict |
| Forecast to no-precedent / back | 14 lost a forecast, 13 gained one | 10 lost, 8 gained |
| Proximity factor moved, same class | 2,198 sticks | 821 sticks |

The differences are one night of data: the rehearsal read the status and producers of the 2026-11-23 nightly, the live stores
those of 2026-11-24. Delaware factor moves across both measures: 2,734 sticks, 450 by more than 1 %, 59 by more than 5 %, 3 by
more than 10 %; mean change on the moved sticks +0.06 %. The Midland split by size was not tabulated.

The step 3 bars were scored on the rehearsal runs. They were not re-scored on the live runs; the totals above move by 0.1 %.

## Reader-facing state after stage A (read back from live)

- Records: Delaware run 32, Midland run 30. Runs 33, 36, 37, 38 are not record.
- Land team's view: Delaware 48,077 rows (48,077 priced), Midland 28,754 (24,882 priced), as before.
- `curated.erebor_locations`: PDP 60,995, PUD 182,695, RES 74,702 (Novi sticks, as before).
- No row of the four new runs is outside the record stick sets 24 / 25.
- Database 155 GB, `box.pud_forecast_month` 69 GB: no growth yet (the new rows reused the space of the rolled-back attempt
  and earlier pruned runs). The disk limit is not visible from SQL.

## erebor against the two full runs (rehearsal container only, records flipped there)

Every undrilled stick on the map has a row of the record run (46,032 of 46,032; 33,106 of 33,106). The land team's view there:
40,685 and 28,711 rows, econ blank. Tiles, selection, gunbarrel, Highgrade and run metadata return HTTP 200 on both basins; the
Midland map draws 28,711 forecast locations. Not looked into: one empty Midland gunbarrel under the midpoint rule; an uncaught
`Source "ov-outline" already exists` console error on a basin switch (overlay code, not touched by erebor PR 33).

## Stage B, when Michael gives each go (off-hours, before the 05:00 CT nightly)

1. `python -m scripts.apply_box_stick_locations --go`
2. PR 275 ready; Michael merges
3. `box_record23 flip --basin delaware --run 36 --allow-unpriced --commit`; `--basin midland --run 38 ...`
4. erebor PR 33 ready; Michael merges; restart erebor; verify C1 to C4; data dictionary. C5 = the next nightly.

If stage B runs after another nightly, sticks that turn producing or crowded in between stay in runs 36 / 38 with the status
stored today; the swapped relation drops the producing ones.
