# BOX sticks phase 5a, third measurement: generator 0.12 (well inputs fixed), day 0

2026-11-18. Files only. **Nothing stored; sets 6 and 7 (generator 0.11) are still the records.** Bars: `BARS_3.md`,
committed (`2966bc6`) before the run. Generator change: `59fbc06`.

## 1. What changed (0.11 -> 0.12)

Only what a well looks like to the generator. No threshold and no placement rule moved.

| Fix | Before | Now |
|---|---|---|
| The lateral, not the whole stored line | A well's line ran surface location, landing point, midpoint, bottom hole. On 29,060 of 54,688 four-point producers the first segment is more than 30 degrees off the lateral; on 364 it swings the whole line more than 15 degrees, and the envelope never tested those wells | A first segment more than 15 degrees off the rest is dropped (`core.well_legs`) |
| Real U-turn wells | Read as their wellstick, about 2,900 ft across the legs | Read on the survey path and split into two legs; each leg pins and closes a row (467 wells) |
| Drilled wells not yet producing | Spud / DUC / Completed: 3,516 wells | Plus Inactive / Active, and Permit Approved with a spud date: 5,020 wells |

Still not read: Permit Cancelled, and P&A / Abandoned wells that never produced. Phases 1 and 2 (spacing measurement,
landing evidence) still read the whole stored line; not touched here.

## 2. The run

Pull 2026-11-18 22:37 UTC, tag run 8 (no nightly between this pull and the record sets' pull of 18:26 UTC, so the
difference is the generator).

| | Delaware 0.11 (set 6) | Delaware 0.12 | Midland 0.11 (set 7) | Midland 0.12 |
|---|---|---|---|---|
| Sticks | 46,709 | 46,062 (-647, -1.4 %) | 33,829 | 33,138 (-691, -2.0 %) |
| Legs | 54,985 | 54,167 | 37,470 | 36,715 |
| Completed lateral, MM ft | 448.5 | 442.4 | 348.3 | 339.9 |
| Wells read | 32,376 | 33,133 | 30,004 | 30,697 |
| Rows culled, same landing | 23,145 | 23,742 | 23,118 | 23,634 |
| Rows culled, stacked | 8,122 | 8,314 | 12,035 | 12,240 |
| Sticks flagged `dsu_drilled_across` | 1,463 | 1,164 | 492 | 492 |
| Invariant violations / DSU errors | 0 / 0 | 0 / 0 | 0 / 0 | 0 / 0 |

## 3. Day 0 against the bars (producing wells only, variant B)

| Bar | Delaware | Midland | Verdict |
|---|---|---|---|
| R1 drilled + producing + conflict <= 0.5 % | **0.63 %** (288 sticks: 73 producing, 215 conflict); was 0.76 % on set 6 | 0.22 % (74: 16, 58); was 0.35 % | **FAILS Delaware**, passes Midland |
| R2 crowded <= 0.5 % | 0.41 % (188); was 0.53 % | 0.39 % (129); was 0.49 % | passes both |
| R3 invariants | 0 violations, 0 errors | 0, 0 | passes |

With every drilled well counted (the first measurement's trigger): Delaware 0.78 % and 0.52 %, Midland 0.36 % and 0.49 %
(they were 1.37 % / 1.13 % and 1.26 % / 1.53 % on sets 6 and 7).

## 4. What is left in R1

| Cause | Delaware sticks | Midland sticks |
|---|---|---|
| Conflict, a producer alongside 20 to 30 % of the stick | 168 | 52 |
| Conflict, alongside 30 to 50 % | 47 | 6 |
| Producing, same code 150 to 500 ft above or below (a second landing in the slot) | 69 | 13 |
| Producing, other | 4 | 3 |

1. **Most of it is two thresholds that disagree.** The generator places a row beside a well that runs along under 30 % of
   it (decided 2026-11-15, DSU 10600). The predicate, from sql/68, calls 20 to 50 % a conflict. 168 of the 215 Delaware
   conflicts and 52 of the 58 Midland ones sit in the 20 to 30 % band. With the conflict floor at 30 % R1 would read 0.26 %
   Delaware and 0.07 % Midland. Not changed here: 0.2 is in the plan as decided.
2. **A second landing in the slot** (finding 4 of DESIGN.md, not one of the three fixes): 69 Delaware and 13 Midland
   sticks lie under or over a same-code producer 150 to 500 ft away.
3. The real U-turn and stepped-out wells are gone from the list but for 6 Delaware and 3 Midland sticks.

## 5. Where this leaves phase 5

- The well-input fixes do what they were meant to: about 650 to 700 sticks per basin that sat on or beside a well are no
  longer generated, and day 0 on producing wells is inside the bar in the Midland and 0.13 points over it in the Delaware.
- They do not change the back-test finding of `FINDINGS_2.md`: a new producer lands on or beside a particular stick about
  83 % of the time in the Midland and 60 % in the Delaware, because of row spacing. That is the generator's phase and
  spacing, and no input fix moves it.
- Storing a 0.12 set and making it the record is a `box.*` write and its own explicit go (the store's dry run measures how
  many location ids carry from sets 6 and 7). Not done, not proposed without that go.
