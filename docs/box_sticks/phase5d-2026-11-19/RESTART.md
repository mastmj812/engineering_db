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
