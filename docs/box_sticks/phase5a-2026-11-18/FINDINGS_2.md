# BOX sticks phase 5a, second measurement: the producing-well trigger

2026-11-18. Read-only; nothing applied, nothing stored. Bars: `BARS_2.md`, committed (`efb184b`) before the hindcast was
generated. Run after Michael's review of `DESIGN.md`: reconciling against wells that are not producing yet rests on tags
and depths that are still permit data.

## 1. Why the trigger

Grain: horizontals with a line, read 2026-11-18 20:00 UTC. "No depth" = a planned survey, or a round-100 TVD with no survey.

| Stage | NM wells | NM tag OTHER / none | NM no depth | TX wells | TX tag OTHER / none | TX no depth |
|---|---|---|---|---|---|---|
| Permit | 4,250 | 12.2 % | 64.7 % | 1,217 | 29.3 % | 67.1 % |
| Spud | 812 | 7.9 % | 57.0 % | 1,638 | 19.6 % | 39.3 % |
| DUC | 15 | | | 284 | 1.1 % | 0.7 % |
| Completed, not producing | 380 | 7.1 % | 55.3 % | 387 | 1.8 % | 0.3 % |
| Producing, first production in 2026 | 1,391 | 2.9 % | 22.9 % | 2,368 | 0.3 % | 0.6 % |

Spud to first production (wells with first production since 2025): median 196 days NM, 220 days TX; P90 351 and 395 days.

Two triggers were scored. **T1:** a well with a first production date takes a stick out. **T2:** T1, plus a DUC or
Completed well with depth evidence. Everything earlier only flags. The predicate judged is variant B of `DESIGN.md` 4c.

## 2. Day 0 on the record sets (set 6 Delaware, set 7 Midland; pull 2026-11-18 18:26 UTC)

| Wells that count | Delaware matched or conflict | Delaware crowded | Midland matched or conflict | Midland crowded |
|---|---|---|---|---|
| First measurement (producing + every drilled well) | 1.37 % | 1.13 % | 1.26 % | 1.53 % |
| T1 producing | 0.76 % (355 sticks) | 0.53 % (248) | 0.35 % (118) | 0.49 % (164) |

## 3. Back-test as of 2026-01-01

Hidden from the generator: every well with a spud date after 2026-01-01 (745 producers, 3,040 not yet producing). Hindcast
sets: Delaware 47,988 sticks, Midland 35,514; 0 errors, 0 invariant violations. Test wells = the hidden wells that pass the
trigger today. W = those in a DSU holding a hindcast stick of their formation family.

| Bar (variant B) | T1 Delaware | T1 Midland | T2 Delaware | T2 Midland |
|---|---|---|---|---|
| Test wells / W | 412 / 326 | 333 / 289 | 695 / 554 | 720 / 586 |
| P1 wells taking a stick out, >= 80 % | **60.4 % fails** | 83.4 % passes | **65.7 % fails** | 85.8 % passes |
| P2 sticks out per well, 0.8 to 1.3 | **0.74 fails** | 1.27 passes | 0.83 passes | **1.32 fails** |
| P3 clean match, >= 40 % | **22.7 % fails** | **35.6 % fails** | **24.5 % fails** | **36.5 % fails** |
| P4 conflicts / sticks out, <= 15 % | 13.7 % passes | 11.5 % passes | 13.7 % passes | 12.4 % passes |
| P5 not open before the wells are shown, <= 0.5 % | **1.24 % fails** | **0.80 % fails** | **1.28 % fails** | **0.80 % fails** |

How the sticks went out under T1: Delaware 75 drilled, 33 conflict, 133 crowded (241 sticks for 326 wells); Midland 111, 42,
213 (366 for 289). Clean matches with depth evidence sit a median 62 ft (Delaware) and 60 ft (Midland) from the stick's
target TVD. Planned basis: 17.5 % of Delaware W (New Mexico), 0 % of Midland. Variant A, not judged: T1 P1 64.7 % / 85.8 %,
P2 0.80 / 1.35, P3 23.3 % / 35.3 %, P4 13.7 % / 10.8 %, P5 4.75 % / 3.39 % (files `backtest2_*`).

## 4. What it says

1. **The conflict problem was the pre-production wells.** Conflicts fall from about 30 % of sticks taken out to 11 to 14 %,
   and P4 passes in both basins under both triggers.
2. **Midland behaves as row spacing predicts.** A well landing at a random position across rows `s` apart falls inside the
   400 ft envelope of a row with probability 800 / s and inside a 150 ft corridor with probability 300 / s. With the
   hindcast spacing next to each test well (median 863 ft) that predicts 87.1 % taking a stick out and 34.0 % clean;
   observed 83.4 % and 35.6 %.
3. **The Delaware is bounded lower by the same arithmetic, and comes in under it.** Median hindcast spacing next to the test
   wells is 1,193 ft, which predicts 73.4 % and 28.0 %; observed 60.4 % and 22.7 %. Where spacing is 1,100 to 1,320 ft (193
   of 326 wells) 54.9 % take a stick out. Of the 129 Delaware wells that take nothing out, 109 come within 400 ft of
   a same-family stick at some point: 91 of those run within 15 degrees of it yet share under 5 % of its corridor (in the
   pairs read one by one the lateral lies between two rows and only the well's surface-to-heel segment touches the stick);
   15 cross the rows at more than 45 degrees (the DSU azimuth is wrong there). The gap between 73 % and 60 % is not
   explained.
4. **So P3 at 40 % cannot be met in either basin, and P1 at 80 % cannot be met in the Delaware, by any rule that needs the
   new well to land on or beside a particular stick,** while rows hang where the spacing map puts them. The bars stand as
   written and fail; this is what they were set against.
5. **P5** is the generator findings of `DESIGN.md` section 7 (real U-turn wells, the stepped-out surface location defect, a
   second landing in the slot), now 0.8 to 1.3 % of the hindcast sticks.
6. **T2 adds wells without changing the picture** (Delaware P1 65.7 %, Midland 85.8 %); it buys lead time in Texas only.

## 5. What follows for the design

A stick-by-stick nightly status is right when it fires and silent for 1 new producing well in 6 in the Midland and 2 in 5
in the Delaware. What actually re-lays the rows around a new well is the generator: a regenerated DSU pins its grid on the
wells in it. Two things for Michael to weigh before any 5b:

- **A DSU-level signal next to the stick status:** "a producing well of this bench has come on in this DSU since the set was
  generated". It needs no stick identity, so it fires for every new well (membership by the 30 % rule), and it marks the
  DSU x bench whose stick count is stale until the next regeneration.
- **Fix the three generator input findings and regenerate first**, then re-measure day 0. They are most of P5.

Not decided here: the drop trigger of 2026-11-12 ("Spud / DUC removes a location") still stands in the plan's table until
Michael changes it.
