# BOX sticks phase 5a, third measurement: day 0 on a generator with the well-input findings fixed

Written 2026-11-18 after Michael's "Yes, generator first". **Written before generator `box_sticks_0.12` was run on anything
but its unit tests.** Committed on its own first. `BARS.md` and `BARS_2.md` and their verdicts stand.

## What changed in the generator (0.11 -> 0.12)

Only what a well looks like to the generator; no threshold, no placement rule.

1. **The lateral, not the whole stored line.** `curated.wells.wellstick_geom` runs surface location, landing point,
   midpoint, bottom hole. A first segment more than 15 degrees off the rest of the line is dropped before the well pins a
   row or is tested by the envelope.
2. **Real U-turn wells on their survey path**, split into two legs (467 wells), each leg pinning and closing its own row.
3. **Every drilled status is read.** Not yet producing = Spud / DUC / Completed / Inactive / Active, or Permit Approved
   with a spud date. Still not read: Permit Cancelled, and P&A / Abandoned wells that never produced (a plugged hole that
   never produced has drained nothing; Michael's call if he wants them in).

Not changed: the spacing measurement and the landing evidence of phases 1 and 2 still read the whole stored line.

## The measurement

A fresh pull, generator 0.12, both basins, files only. **Nothing is stored and sets 6 and 7 stay the records.** Then the
day-0 predicate of `BARS_2.md` (variant B) against the wells of the same pull.

| Bar | Measure | Passes when |
|---|---|---|
| R1 | Sticks drilled, producing or in conflict on day 0, trigger T1 (producing wells only), per basin | <= 0.5 % of the basin's sticks |
| R2 | Open sticks flagged crowded on day 0, trigger T1, per basin | <= 0.5 % |
| R3 | The generator's own invariants on the new run | 0 violations, 0 DSU errors |

Reference, same trigger and variant on the record sets (generator 0.11): R1 0.76 % Delaware, 0.35 % Midland; R2 0.53 %,
0.49 %.

Reported, no bar: stick, leg and footage counts against sets 6 and 7; rows culled by reason against the 0.11 run; what is
left under R1 and R2 by cause; the same day 0 with every drilled well counted (the first measurement's trigger).
Not measured here: how many location ids a store of this run would carry from sets 6 and 7 (that is the store's dry run).
