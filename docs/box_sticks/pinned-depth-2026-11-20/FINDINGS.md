# Sticks pinned on a same-tag producer that sits off their depth: the whole population

2026-11-20, read-only on live. Asked by Michael ("generator first") after `box_recon_2` failed its deciding bar
(`docs/box_sticks/recon2-2026-11-20/FINDINGS.md`, draft PR #265). Nothing changed: no generator rule, no nightly rule, no
table, no stick. No bars: this is a count and a classification, not a test.

## The number

Grain: record sticks of set 16 (Delaware, 46,062) and set 17 (Midland, 33,138), each against every producer **the set
itself read with depth evidence** (`box.location_set_well`), kept when the well runs along at least 50 % of a stick leg
inside a flat-ended 150 ft corridor.

| | sticks |
|---|---|
| Sticks with a same-tag producer along them, 150 to 500 ft off the stick's depth | **82** (Delaware 69, Midland 13) = 0.10 % of 79,200 |
| of those inside one of the set's stacked bands | 0 |
| Sticks with a producer along them within 150 ft, different tag | 338, every one WCA_1 against WCA_2 (the co-developed rule, as designed) |
| Sticks with a producer along them within 150 ft, same tag | 2 (locations 10132195 and 10132738; the generator's own rule should have culled them; not traced) |

All 82 are on a **pinned** grid. So the question "is a row pinned on a same-tag producer 250 to 500 ft off a real
location?" is a question about 82 sticks, not about the generator at large. They are the same sticks the nightly takes out
today under rule 1 (the 89 producing = these 82, 5 matched with no depth evidence, and the 2 above).

## What the 82 are

Each stick was classed from what the set recorded about its own DSU (`box.location_set_bench`):

| Class | What the set shows | Delaware | Midland | landing rung of the stick |
|---|---|---|---|---|
| **A** | The DSU's wells show **two landings** in this bench (recorded by the generator); the stick is at one, the well within 150 ft of the other | 13 | 1 | direct 13, bracket 1 |
| **B** | Not A, and the well sits within 150 ft of **another bench's landing** in the same DSU | 23 | 10 | direct 20, thickness 7, offset 4, bracket 2 |
| **C** | Neither: one same-tag well 250 to 500 ft off its bench's landing, at no other bench's landing | 33 | 2 | direct 22, thickness 7, offset 6 |

Median depth offset in all three classes is about 290 to 325 ft with the well shallower than the stick; the well runs along
97 to 99 % of the stick.

Reading, mine:

- **A (14)**: a real second landing. The stick is a location at the DSU's main landing with a well of the other landing
  directly over or under it. Real operators offset the two landings sideways; these rows are directly under because the
  grid is pinned through every same-bench well, whichever landing it is in.
- **B (33)**: the well's depth says it is in the neighbouring bench, its tag says this one (BS3_C wells at the BS2_S
  landing 6, WCC at WCB_2 4, AVA_1 at AVA_2 3, WCA_2 at BS3_S 3, WCB_2 at WCB_1 3, ...). By depth, this bench is open under
  that well and the stick looks real. The grid is still pinned on a well that is arguably not this bench's.
- **C (35)**: cannot be told from the tables. Either a one-well second landing (stick real) or the bench's landing in this
  DSU is 250 to 500 ft off (13 of 35 carry their depth from a non-direct rung) and the stick is that well. BS2_S 13,
  BS3_C 8, BS3_S 6.

## What follows

1. **This does not justify a generator rule on its own evidence.** A cull of "rows pinned on a same-tag producer within
   500 ft" would remove 82 sticks, of which about 47 (A and B) look like real locations. A cull of nothing leaves about 35
   doubtful sticks (0.04 % of inventory).
2. **It does not settle the nightly rule either.** Rule 1 takes all 82 out (wrong for about 47 by the reading above);
   rule 2 puts all 82 back (wrong for some of C). Neither is right for all three classes.
3. The honest size of the disagreement between the generator and the nightly is **82 sticks**, plus the 22 conflicts of the
   same kind.

## Options (yours)

- **Cards for class C** (35 sticks, strike section per DSU: the stick, the well, the bench's other wells, the adjacent
  bench bands), a handful of A and B for calibration. Your verdicts decide whether C is "that well" or "a second
  location", and the rule follows the verdicts.
- **Send the class to review instead of out**: the nightly marks a same-tag match 150 to 500 ft off as `conflict`
  (not inventory, in the review queue) rather than `producing`. Still a rule change, with bars, after 11-26.
- **Leave it**: rule 1 as it runs, the 82 stated as a known over-removal of about 0.06 to 0.10 % of sticks.

List: `sticks_82.csv` (location, DSU, bench, target TVD, rung, well, well depth, offset, class, nearest other bench).
