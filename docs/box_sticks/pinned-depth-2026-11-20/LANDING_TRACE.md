# Why the "same well" sticks sit off their well, and what the grids can arbitrate

2026-11-20, read-only (record set 16, live wells after the v4 cutover, the geologist's V5 grids). Nothing changed: no
generator rule, no tag, no stick. Asked by Michael: trace the 26 "REMOVE, same well" sticks; and should the grids be raised
from witness to arbiter, especially where PDP depth control is weak.

## 1. How a landing is set

A bench's `direct` landing in a DSU is not taken from the DSU's own wells. It is the bench's **landing surface** at the DSU
(`box/landing_surfaces.py`): the distance-weighted median (1-mile Gaussian) of the depths of same-tag evidence wells within
2 miles, or a plane through them where at least 6 surround the point; used where the nearest such well is within 1 mile.
One value per bench per DSU. The row grid is then pinned through the map positions of the bench's wells, and a row is
culled only where a well is within 150 ft of that one value (or in a stacked band).

## 2. The trace

`landing_trace.csv`: one row per carded stick, with the same-tag evidence wells within 2 miles that the set itself kept
(`box.location_set_well`, screen `keep`), their weighted median, how many sit within 150 ft of the stick and of its well,
and where the stick and the well fall in the bench's gridded interval (0 = top, 1 = base).

On the 27 REMOVE cards that have a gridded interval (BS1_S to BS3_S):

| | Median |
|---|---|
| Position of the pinned well in the gridded interval | 0.18 |
| Position of the stick in the gridded interval | 0.81 |
| Cards with both the well and the stick inside the interval | 15 of 27 |

On the direct-rung cards the 2-mile weighted median reproduces the stick's depth, and the wells at the stick's depth
outnumber the wells at the pinned well's depth: for example card 17 (22 wells at the stick's level, 2 at the well's), card
16 (26 and 7), card 23 (16 and 3), card 04 (23 and 3).

**So the common cause is two landings inside one bench.** The neighbourhood's majority is on the lower landing (about 0.6
to 0.9 of the way down the interval), the DSU's own well is on the upper one (about 0.1 to 0.25), the surface takes the
majority, and the row drawn through the well's map position lands 250 to 450 ft under it. The depth cull, built for one
landing, lets it stand. This is not a tag problem and not a grid problem. It is the generator treating a two-landing bench
as one level.

The carried rungs (thickness, offset) show the other cause: with one or two same-tag wells in 2 miles (cards 31, 32, 36,
37, 39, 41) or none (43, 44), the depth comes from far away and misses the only local well by 250 to 500 ft.

## 3. What follows for the generator (not changed here)

Michael's 45 verdicts match one rule: **a row that runs directly along a producer of the same tag within 500 ft of depth
is that well's slot**, whichever landing the well is on (33 REMOVE), unless the well's tag is wrong (12 KEEP). That is
exactly what the nightly's rule 1 already applies after the fact. The same test inside the generator's cull would stop
these 82 sticks being generated. It would be an amendment to candidate D, with bars, and takes effect at a regeneration.

## 4. The grids as an arbiter

### 4a. Of whether a well is in its tagged bench

Test: "the grid puts the pinned well outside its tagged interval" should predict KEEP (a wrong tag). On the 37 carded
sticks with a gridded interval it agrees with Michael on 28 (76 %): it catches 9 of the 10 KEEPs and also calls 8 of the
27 REMOVEs wrong-tag. Useful as a screen, not reliable enough to decide a tag alone.

### 4b. Of landing depth

Test: predict each producing well's landing from the grid alone (top plus the bench's median fractional position times the
gridded thickness; the fraction learned with the well's own 10-mile cell held out), and compare the error with the
held-out error the generator records for each of its rungs (set 16).

Median absolute error, ft (90th percentile in brackets):

| Bench | Grid | direct | thickness | bracket | offset |
|---|---|---|---|---|---|
| BS1_S | 66 (275) | 44 (155) | 55 (186) | 56 (249) | 87 (256) |
| BS2_C | 102 (236) | 43 (175) | 62 (185) | 59 (235) | 94 (239) |
| BS2_S | 64 (224) | 56 (178) | 70 (218) | 103 (264) | 98 (278) |
| BS3_C | 94 (270) | 49 (176) | 57 (189) | 73 (217) | 82 (217) |
| BS3_S | 56 (180) | 42 (146) | 52 (189) | 63 (372) | 86 (274) |
| WCXY | 46 (127) | 36 (107) | 59 (171) | 58 (186) | 80 (220) |
| WCA_1 | 57 (149) | 33 (100) | 50 (158) | 64 (184) | 71 (216) |
| WCA_2 | 57 (158) | 39 (116) | 55 (191) | 72 (220) | 74 (237) |

The two error sets come from different hold-out designs (mine by 10-mile cell; the rungs' from phase 1c), so differences
of 10 ft mean nothing.

- **Against direct control the grid loses on every bench.** Where there are same-tag wells within a mile, the wells are the
  better evidence. No arbiter role there.
- **Against the offset rung the grid wins on 6 of 8 benches** (BS2_S 64 against 98 ft, BS3_S 56 against 86, WCXY 46
  against 80, WCA 57 against 71 to 74, BS1_S 66 against 87) and loses on BS3_C and BS2_C, the two thick carbonate benches
  where a single fractional position is a poor guess.
- **Against thickness and bracket it is roughly level**, better on WCXY and BS2_S, worse on the carbonates.

### 4c. Of whether a landing is believable

Share of the record set's Delaware Bone Spring landings (9,169 DSU x bench, 23,117 sticks) that fall outside their own
gridded interval:

| Rung | DSU x bench | Outside by more than 50 ft | Outside by more than 150 ft | Sticks outside by more than 150 ft |
|---|---|---|---|---|
| direct | 3,102 | 7.2 % | 2.5 % | 180 |
| bracket | 731 | 8.3 % | 1.8 % | 37 |
| thickness | 3,649 | 9.5 % | 3.6 % | 359 |
| offset | 1,687 | 18.3 % | 9.3 % | 437 |

381 DSU x bench (1,013 sticks) sit more than 150 ft outside the gridded interval of their own bench; the offset rung is
three to four times worse than the others. List: `landing_outside_grid_set16.csv`.

## 5. Answer to the arbiter question

Not above wells: with direct control the wells are better. **Yes where control is weak**, in two specific places:

1. **In place of the offset rung** (and ahead of it everywhere except BS3_C and BS2_C): the grid predicts landing at least
   as well, and the offset rung is where one landing in ten is more than 150 ft outside its own bench.
2. **As a bound on every carried landing**: a thickness, bracket or offset landing that falls more than 150 ft outside the
   gridded interval is flagged, or pulled to the grid's prediction.

Both would be generator changes, to be tested in the generator's own hold-out before adoption. The XY top stays out of any
arbiter role (2 of 2 "WCXY" grid calls on the tag cards were wrong), and the grids cover the Delaware only.

## 6. Not done

- No generator change, no regeneration, no seed.
- The two-landing recognition itself (why the set recorded two landings on only 14 of these 82 DSU x bench) was not traced.
- Midland has no grids in this analysis.
