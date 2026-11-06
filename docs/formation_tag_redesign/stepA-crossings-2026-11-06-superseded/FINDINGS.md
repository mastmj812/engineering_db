# Step A — landing-surface crossings in the BOX record extents (2026-11-06, read-only)

```
python -m scripts.tag_landing_crossings --cache <scoreboard cache> --out <this folder>
```

Code: `box/landing_surfaces.py` (tests: `tests/test_landing_surfaces.py`). Maps: `crossings.html`.

**How the surfaces are built.** One landing surface per BOX record extent and code, on a ¼-mi lattice, from live-tagged
evidence wells:
- the code's own wells within 2 mi (3 or more) where its nearest well is within 1 mi;
- otherwise, structure from a thick anchor bench plus local thickness, out to 5 mi;
- nothing beyond that.

Every pair of codes is compared in stratigraphic order wherever both surfaces exist:
- **crossing:** the deeper code's surface is at or above the shallower one;
- **merged:** within 50 ft.

**Pool sets.** The record runs' analog pools are the committed docs/box sets:
- Delaware run 32: `pool-2026-10-15` plus the step-15 / 15a sets;
- Midland run 30: `pool-midland-2026-10-31`.

`box.tc_member` holds only the Delaware WCA pool. The step-2 blast-radius pool counts therefore covered WCA only, which
does not change v3's verdict.

## Scoreboard number (the "before")

| Adjacent pairs | Shared area | Crossing | Merged (< 50 ft) | Non-adjacent crossing |
|---|---|---|---|---|
| Delaware | 18,207 sq mi | **722 sq mi (4.0 %)** | 792 sq mi (4.3 %) | 642 sq mi |
| Midland | 16,323 sq mi | **328 sq mi (2.0 %)** | 314 sq mi (1.9 %) | 184 sq mi |

Every later tag change can be scored against this: crossing area should fall.

**Fringe (outer mile of the extents) against the interior**, adjacent-pair crossing share:
- Delaware: 3.8 % vs 4.0 %;
- Midland: **4.6 % vs 1.8 %**.

Per pair, the fringe crosses 2–3× more often for Midland DEAN|WCA_1 (10.2 vs 3.3 %), WCB_2|WCC (11.1 vs 3.9 %) and
WCA_1|WCB_1 (4.7 vs 1.3 %), and for Delaware WCB_1|WCB_2 (5.7 vs 2.5 %).

## Where (pairs.csv; the map per pair is in crossings.html)

**Delaware, adjacent pairs:**

| Pair | Shared | Median gap | Crossing | Merged |
|---|---|---|---|---|
| WCXY \| WCA_1 | 1,286 sq mi | 111 ft | 6.1 % | 13.5 % |
| WCA_1 \| WCA_2 | 2,908 | 122 | 5.7 % | 9.5 % |
| WCB_2 \| WCC | 999 | 186 | 6.2 % | 4.4 % |
| BS1_S \| BS2_C | 859 | 271 | 5.8 % | 1.7 % |
| BS3_C \| BS3_S | 2,025 | **591** | **4.8 %** | 2.1 % |
| AVA_1 \| AVA_2 | 464 | 267 | 4.5 % | 0.8 % |
| BS3_S \| WCXY | 1,157 | 153 | 3.9 % | 4.6 % |
| WCB_1 \| WCB_2 | 2,489 | 295 | 2.8 % | 2.5 % |
| WCA_2 \| WCB_1 | 2,716 | 184 | 2.3 % | 2.9 % |
| BS2_S \| BS3_C | 1,793 | 503 | 1.7 % | 1.6 % |

The thin WCA splits cross and merge most, as expected. A 591-ft median gap crossing 4.8 % of the time (BS3_C | BS3_S)
is not thin-bed noise. It is a naming problem: the BS3_C → BS2_S class the blind cards upheld (Novi "THIRD BONE SPRING
LIME" on wells that sit at 2nd Bone Spring Sand depth).

**Midland, adjacent pairs:** WCB_2 | WCC 5.3 %, DEAN | WCA_1 3.7 %, WCB_1 | WCB_2 2.6 %, the rest ≤ 1.5 %.

**Largest non-adjacent crossings:** Delaware BS3_S | WCA_1 (53 sq mi) and BS3_S | WCA_2 (36 sq mi), BS1_S | BS2_S
(35), BS2_S | BS3_S (30); Midland DEAN | WCB_1 (28).

## The investigation list (`wells_in_zones.csv`)

**Delaware:** 2,740 wells sit in a crossing or merging node; **861 of them** are closer to the other bench's surface
than to their own (`suspect = this well`). **Midland:** 870 wells; **256** closer to the other surface. For the rest
(`other bench here`), the well sits on its own surface and the suspect is the other bench's control nearby.

The list is ranked fringe first, then likely mis-tags, then crossings before merges, then the deepest crossings.

Likely mis-tags (`this well`):
- **Delaware:** WCA_1→WCA_2 147, WCA_1→WCXY 130, WCA_2→WCA_1 125, WCXY→WCA_1 74, WCA_2→WCB_1 46, BS3_C→BS3_S 35,
  WCA_1→BS3_S 23, BS3_S→WCXY 23, BS2_S→BS3_C 21.
- **Midland:** WCA_1→DEAN 51, WCB_1→WCB_2 43, WCB_2→WCB_1 23, DEAN→WCA_1 23, WCB_2→WCC 20.
- **In the fringe (0–1 mi):** 27 Delaware and 54 Midland likely mis-tags, the top of the list.

## Caveats

- **The surfaces are built from live tags.** A crossing says the tags and the depths disagree there; it does not say
  which well is wrong. The `suspect` column is a pointer, not a verdict.
- **Fringe surfaces are often extrapolated** (structure plus thickness). Some fringe crossings are surface error, not
  tag error, which is why the list is for review.
- Nothing is re-tagged. Step B, or a class review, is the next decision.
