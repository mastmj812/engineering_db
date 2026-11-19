# BOX sticks phase 5a, fourth measurement: two decisions applied, and the DSU-level signal

2026-11-18. Files only; nothing stored, nothing applied. Bars: `BARS_4.md` (`0748555`, corrected to generator 0.12 in
`30517c1`, both before any run).

## 1. Decisions applied (Michael, 2026-11-18; in the plan's decision table)

- **Drop trigger: producing only.** A stick leaves undrilled counts when a matching well has a first production date.
  Spud / DUC / completed-not-producing wells and permits only flag.
- **Conflict floor: 30 %**, not sql/68's 20 %, to agree with the generator's 30 % placement rule.

Day 0 on generator 0.12 (pull 2026-11-18 22:37 UTC, files only), producing wells, variant B:

| | Delaware (46,062 sticks) | Midland (33,138 sticks) |
|---|---|---|
| Matched or conflict, floor 20 % (`FINDINGS_3.md`) | 0.63 % (288) | 0.22 % (74) |
| **Matched or conflict, floor 30 %** | **0.26 %** (73 producing, 47 conflict) | **0.07 %** (16, 6) |
| Crowded, floor 30 % | 0.63 % (291) | 0.50 % (166) |
| Crowded, flat-ended corridors (side check, not adopted) | 0.40 % (183) | 0.34 % (114) |

Against `BARS_3.md` (0.5 %): matched-or-conflict now passes in both basins. Crowded went UP, over the bar in the Delaware:
the sticks that stopped being conflicts are open again and are now tested for crowding, and the corridor's rounded ends count
up to 2,640 ft beyond each end of a well as "alongside". With flat ends both basins are inside the bar on both measures.
**For 5b: build the corridors with flat ends.** Not adopted here because it was looked at after the result.

## 2. The DSU-level signal

**Signal.** Per DSU x bench: `new_producers` = producing wells the set did not know as producers, tagged that bench, with
>= 30 % of the lateral inside the DSU. Estimated sticks = sticks - new_producers, never below 0.

**Test.** Before = generator 0.12 as of 2026-01-01 (745 producers and 3,868 not-yet-producing wells spudded after it
hidden): Delaware 47,767 sticks, Midland 35,248. Truth = the same inputs regenerated with the 745 producers put back:
47,552 and 34,881. Judged on the DSU x bench that hold sticks before and at least one new producer of that bench:
156 in each basin, holding 450 (Delaware) and 534 (Midland) sticks before and 178 and 192 after the regeneration.

| Bar | Delaware | Midland | Verdict |
|---|---|---|---|
| G1 total sticks, DSU signal against regenerated, within +-10 % | 179 against 178 = **+0.6 %** | 253 against 192 = **+31.8 %** | passes Delaware, **FAILS Midland** |
| G2 mean abs error per DSU x bench, DSU signal lower than stick level | 0.57 against 0.69 | 0.72 against 0.62 | passes Delaware, **FAILS Midland** |
| G3 DSU signal exactly right, >= 50 % of DSU x bench | 55.8 % | 49.4 % | passes Delaware, **FAILS Midland** |
| G4 new producers that fire it on sticks of their own code, >= 70 % | 72.3 % | 84.4 % | passes both |

The three estimates side by side (touched DSU x bench only):

| Estimate of the regenerated count | Delaware total (truth 178) | mean abs error | exact | Midland total (truth 192) | mean abs error | exact |
|---|---|---|---|---|---|---|
| Nothing (the count before) | 450 (+153 %) | 1.76 | 12 % | 534 (+178 %) | 2.24 | 5 % |
| Stick-level status | 272 (+53 %) | 0.69 | 56 % | 253 (+32 %) | 0.62 | 55 % |
| DSU signal | 179 (+0.6 %) | 0.57 | 56 % | 253 (+32 %) | 0.72 | 49 % |
| The lower of the two (looked at afterwards, no bar) | 165 (-7 %) | 0.51 | 58 % | 207 (+8 %) | 0.47 | 64 % |

## 3. What it says

1. **The flag is right; the subtraction is right only in the Delaware.** Where a new producer comes on, a regeneration
   removes 60 % of that DSU x bench's sticks (Delaware) and 64 % (Midland), and 61 and 65 of the 156 end with none. So
   "stale" marks the right places. One stick per well is the right arithmetic at Delaware spacing (0.89 sticks lost per
   new producer). In the Midland a regeneration removes 1.16 per well: rows are tighter, and re-laying a pinned grid costs
   a neighbour too.
2. **The two signals fail in different places.** The stick status misses wells that land between rows; the subtraction
   misses the neighbour a tight grid loses. Taking the lower of the two is within 8 % of the regenerated total in both
   basins and exactly right on 58 % / 64 % of DSU x bench. That was seen after scoring: it is a proposal for 5b, to be
   put against its own bar, not a result.
3. **Outside the touched DSU x bench the regeneration barely moves**: 3.6 % (Delaware) and 4.6 % (Midland) of the DSU x
   bench with no new producer change their count, net +56 of 47,317 sticks and -29 of 34,714.
4. **Size of the whole problem.** Ten and a half months of new producers (2026-01-01 to 2026-11-18) make 312 DSU x bench
   stale, holding 984 of about 83,000 sticks. Doing nothing overstates inventory by 272 sticks in the Delaware (0.57 %)
   and 342 in the Midland (0.97 %). The stick status alone leaves +94 (0.20 %) and +61 (0.17 %); the DSU signal +1 and
   +61. Every bar failure in this folder is inside that 0.2 % of basin inventory once only producing wells count.

## 4. Proposed shape for 5b (for Michael's decision; nothing built)

- Stick status as designed (`DESIGN.md` section 2), with: producing-only trigger, 30 % floor, variant B's three rules,
  flat-ended corridors.
- One more nightly row per stale DSU x bench: `new_producers`, the api10s, sticks taken out by status, and an estimated
  count (the lower of the two), marked as an estimate until the next regeneration.
- Regeneration stays periodic and explicit-go; the stale list is its work list.
- Before 5b: whether a generator 0.12 set is stored and made the record first (a `box.*` write; its own go), so that
  reconciliation is authored against the sticks it will run on.
