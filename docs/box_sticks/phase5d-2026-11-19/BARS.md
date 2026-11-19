# BOX sticks gate 5d: bars for the shadow week

Written 2026-11-19, **before the first shadow night** (the four sql/74 tables are live and empty; the hook reached main with
PR #260 at 13:04 UTC, after today's nightly). Committed on its own first. Branch `claude/box-sticks-phase5d`, cut from main at
`94766fd`. Record sets: set 16 (Delaware, 46,062 sticks) and set 17 (Midland, 33,138), generator `box_sticks_0.12`. Rule
`box_recon_1`.

Shadow means: the nightly computes and logs; **no count and no app reads the tables**. Nothing here is run by hand to fill
them: the only writer is the nightly hook. A night is one `etl-nightly` run that reached the curated refresh.

## Bars

| Bar | Measure (grain) | Passes when |
|---|---|---|
| S1 | The hook ran (nights) | 7 of 7 nights have exactly one `meta.box_recon_run` row, status `written`. A `failed` or `breaker` row fails the bar for that night and is reported with its cause |
| S2 | The nightly was never failed or lengthened past its window by the hook (nights) | every `etl-nightly` run green, or red for a cause shown to be outside the hook; hook `seconds` <= 300 every night |
| S3 | Night 1 (sticks) | status rows = record sticks, one per location; log rows = status rows, all `first_run`; producing or conflict <= 0.5 % and crowded <= 0.5 % of each basin's sticks |
| S4 | Nights 2 to 7, churn (locations changed per night) | <= 198 per night (0.25 % of 79,200), with no record flip in the week; no breaker trip |
| S5 | Flapping (locations) | of the locations that changed at least once in nights 2 to 7, <= 10 % return to a status they held earlier in the week |
| S6 | Identities, every night | status rows = record sticks; inventory = sticks not producing, not in conflict, not crowded; log rows of the run = its `changed`; `box.location_set`, `box.location_stick`, `box.location` row counts and the record sets unchanged by the hook |
| S7 | Nothing reads the tables (objects) | no view, matview or function depends on the four tables (`pg_depend`), every night |
| S8 | Every stick that goes to `producing` in nights 2 to 7 (sticks) | its well has a first production date, same-bench or within 150 ft, leg share >= 0.5: checked by an independent read of the well, 100 % |

## Reported, no bar (stated before the fact)

- **Against sql/68, per well.** For the wells behind the night's changes (night 1: every well that takes a stick out or crowds
  one), sql/68's own SELECT is evaluated read-only on that well against the Novi sticks: realizes a Novi stick (>= 0.5),
  conflict (0.2 to 0.5), or nothing. `curated.reconciled_inventory` is neither refreshed nor touched. No bar: the two judge
  different sticks on different rows, and 5a measured that a well can take out one and not the other.
- **One well, two sticks.** Wells that are the matching well of two or more sticks, split same DSU / different DSUs. No rule
  exists; the count decides whether one is needed.
- **Conflict queue** and **stale list**: size and movement each night.
- **Permit and pending flags**: movement each night (flags only; inventory does not move with them).

## What would stop the week early

A red nightly traced to the hook; a breaker trip; or status rows that are not one per record stick. Each is reported the
morning it happens, and nothing is tuned to clear it.
