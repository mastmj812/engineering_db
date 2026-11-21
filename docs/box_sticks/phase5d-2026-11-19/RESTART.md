# Shadow week restarted on set 21

2026-11-20. Michael: the shadow nights should be relative to set 21 (generator 0.13), not set 16. Set 21 was made the
Delaware record at 22:15 UTC on his go ("Go flip set 21"); set 17 stays the Midland record.

- **Night 1 is the first nightly that judges sets 17 and 21** (expected: the nightly of 2026-11-21). Its Delaware log rows all
  say `set_change`: carried ids are re-judged on their new geometry, the 1,729 ids that stopped get a last row `stopped`, the
  1,799 new ids get a first row. A set change is not held by the circuit breaker.
- **Seven nights from there**, through the nightly of 2026-11-27.
- The nightly of 2026-11-20 on sets 16 and 17 (run 4) stays in this folder as a report (`night_run_4.md`,
  `night_1_notes.md`) and is counted in no bar. Runs 3 and 5 were already out of band.

How the bars of `BARS.md` read after the restart (the bars themselves are not edited):

| Bar | Reading |
|---|---|
| S1, S2 | 7 of 7 nights from the restart |
| S3 (night 1) | status rows = record sticks (79,270), one per location; producing or conflict and crowded each <= 0.5 % per basin. Its "all log rows `first_run`" clause was written for an empty table and does not apply: the Delaware rows are `set_change`, and the Midland changes nothing but ordinary well changes |
| S4, S5 | nights 2 to 7 from the restart; 198 locations is still 0.25 % |
| S6 to S8 | unchanged |

## Update, 2026-11-21 01:25 UTC: set 24 replaced set 21 before any night ran on it

Michael corrected 19 Delaware well tags on 2026-11-20 (seed reload finished 2026-11-21 00:10 UTC) and said to regenerate.
Set 24 (generator 0.13 on the corrected tags, 46,153 sticks, pull 2026-11-21 00:28 UTC) was stored and made the Delaware
record at 01:25 UTC, on his go. No nightly had judged set 21, so nothing restarts a second time: **night 1 is still the
nightly of 2026-11-21**, now on the record sets of that night.

The report script no longer names the sets. A night belongs to the week when it judged the same record sets as the latest
written night, so any later flip (the Midland, if Michael says go) restarts the count by itself and the report says so.
Where this file says "sets 17 and 21" or "79,270", read "the record sets of the night" (Delaware set 24: record sticks
79,291 while set 17 is the Midland record).

## Update, 2026-11-21 01:29 UTC: set 25 is the Midland record

On Michael's "Go Midland", the Midland set from the same pull as set 24 (33,122 sticks; 23 new and 39 stopped against set
17) was stored and made the record. Both flips were done before the nightly of 2026-11-21, so **night 1 is that nightly, on
sets 24 and 25** (79,275 record sticks), and its log is `set_change` for both basins. Set 24 became the Delaware record at
about 01:20 UTC, not 01:25 as written above.
