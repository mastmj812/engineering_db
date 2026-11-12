# BOX sticks, phase 1b: landing depth far from a bench's own wells (2026-11-12)

Read-only, live tags. `python -m scripts.box_sticks_phase1b --out docs/box_sticks/phase1b-2026-11-12`.
Follows `../phase1-2026-11-12/FINDINGS.md`, which left 35.5 % of the 52,712 DSU x bench pairs with no depth.

## What was tested

Depths that need no same-bench well nearby, only OTHER benches' direct surfaces at the location:

- **offset**: one neighbour's surface + the thickness to the bench (every other bench tried);
- **bracket** (Michael): the bench sits in the window between a bench above and a bench below,
  depth = upper + f x (lower - upper) (every above x below pair tried).

The thickness / fraction f is learned from the 30 nearest same-bench wells beyond the held-out distance ("nearest")
or as one extent-wide number ("regional"). Held-out test: every same-bench well within 1, 5 or 10 mi is removed.

## Result 1: the gap closes from 35.5 % to 6.7 %

| DSU x bench pairs | Direct | Carried by bracket | Carried by offset | None |
|---|---|---|---|---|
| All (52,712) | 48.2 % | 13.0 % | 32.1 % | 6.7 % |
| Delaware (32,877) | 44.6 % | 13.8 % | 34.8 % | 6.7 % |
| Midland (19,835) | 54.2 % | 11.6 % | 27.7 % | 6.6 % |

About 1.9 points of the remaining "none" are edge polygons whose centroid lies outside the extent. Each DSU takes
the best-ranked method (held-out median at 5 mi) whose neighbour surfaces exist at its centroid. Per-bench table:
`coverage_chain.csv`. (In this table the far methods replace phase 1's local thickness everywhere there is no
direct depth; a surface of record would still use local thickness first where it applies.)

## Result 2: the bracket works where the bench has dense neighbours on both sides

**Midland DEAN, between LSSH and WCA_1** (the case Michael described):

| Held out within | Bracket LSSH / WCA_1, median / P90 | Best single neighbour, median / P90 |
|---|---|---|
| 5 mi | 40 / 135 ft | 47 / 153 ft (WCA_1) |
| 10 mi | 45 / 150 ft | 54 / 169 ft (WCA_1) |

- That is as good as phase 1's local thickness (41 / 124 ft) with no DEAN well within 5 mi, and it barely degrades
  at 10 mi. One regional fraction for the whole extent is nearly as good (42 / 140 ft).
- 72 % of DEAN wells have both neighbours resolved. At the DSUs: 24 % direct, 58 % bracket, 7 % offset, 10 % none
  (down from 47 % none).

Median error at 5 mi, best method of each kind (full table `best_by_kind.csv`):

| Bench | Bracket | Offset | | Bench | Bracket | Offset |
|---|---|---|---|---|---|---|
| Delaware AVA_2 | 44 ft | 69 ft | | Midland DEAN | 40 ft | 47 ft |
| Delaware BS1_S | 34 ft (17 % of wells) | 63 ft | | Midland WCA_1 | 41 ft | 51 ft |
| Delaware BS2_C | 42 ft | 61 ft | | Midland WCB_1 | 47 ft | 49 ft |
| Delaware BS3_S | 51 ft | 62 ft | | Midland WCB_2 | 43 ft | 55 ft |
| Delaware WCB_1 | 50 ft | 72 ft | | Midland JM | 50 ft | 50 ft |
| Delaware WCXY | 47 ft | 58 ft | | Midland LSSH | 54 ft | 57 ft |
| Delaware BS2_S | 71 ft | 79 ft | | Midland MS | none above | 41 ft |
| Delaware BS3_C | 74 ft | 87 ft | | Midland WCD | none below | 82 ft |
| Delaware AVA_1 | 102 ft | 107 ft | | Midland WCC | none below | 140 ft |

The bracket beats or ties the single-neighbour offset on every bench that has one.

## Result 3: where it is weak

- **Delaware BS1_S.** The only benches above it are the Avalons, which exist over part of its extent, so the good
  bracket (AVA_0 / BS2_C, 34 ft) applies to 17 % of wells. Most BS1_S DSUs fall back to an offset from the WCA
  family about 2,500 ft below: expected 87 ft median, 262 ft P90. That is no better than the Novi BS1_S bust
  measured in phase 0 (median 87 ft absolute).
- **Top and bottom of the column** have no bracket: Midland MS is fine on an offset (41 ft); Midland WCD (82 ft,
  134 ft at 10 mi) and WCC (140 ft) and Delaware WCC (86 ft) are not.
- **Delaware Bone Spring generally** carries at 60-95 ft median, P90 200-280 ft; Midland carries at 40-60 ft,
  P90 115-185 ft.
- **Bracket tails.** A narrow or noisy window blows up the tail (Delaware BS3_S bracket P90 927 ft). The fraction
  needs a guard: minimum window thickness and a clamp to the window.

## Caveats

- Many methods were tried per bench and ranked on the same held-out wells, so the best numbers are a little
  optimistic. The held-out wells also sit where drilling exists; true fringe may be worse.
- Neighbour surfaces are direct only. Nothing here stacks a carried depth on a carried depth.
- Live tags. A bracket inherits tag errors in three benches instead of one.

## Proposed landing-depth chain (for Gate 1)

1. **direct**: the bench's own wells (>= 3 within 2 mi, nearest within 1 mi);
2. **local thickness**: phase 1 method, own wells within 5 mi, best anchor per bench;
3. **bracket**: both neighbours direct at the location; fraction from the nearest samples, regional as fallback,
   clamped to the window;
4. **offset**: one neighbour direct + regional thickness;
5. **none**: no stick.

Every stick records which rung it used and that rung's held-out error, so confidence is visible downstream.
Open decision: an error ceiling above which a carried depth is "low confidence" or not placed at all
(candidates: Delaware BS1_S / BS3_C / BS2_S / AVA_1 offsets, Midland WCC / WCD offsets).
