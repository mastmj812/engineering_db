# Re-run of v5 / v5.1 / v5.2 with the WOLFCAMP A (XY) crosswalk row (2026-11-09)

**What changed in the input.** PR #234 (merged; applied live on 2026-11-09) maps Delaware Novi Insights `WOLFCAMP A (XY)`
to WCXY. The rule maps both vendor strings through the crosswalk. Until now it read Novi as having no opinion on the
2,545 producers carrying that string; it now reads Novi as WCXY.

**How the run was made.**
- The input is a copy of the Nov 5 snapshot cache, with Novi's code set to WCXY on those 2,545 producers. sql/16's code
  became WCXY on the 3 that have no Enverus interval.
- The chain was run unchanged: `tag_precedence_dev` → `tag_subbench_dev` → `tag_grossmiss_dev`, with the same card
  folders. Outputs are in `v5/`, `v5_1/` and `v5_2/`. It is read-only; no constant changed.
- It is compared well by well with the reviewed runs (`v5-dev-2026-11-06` → `v5_1r1` → `v5_2r1-dev-2026-11-08`).

## The 2,545 XY producers

| Enverus says | Wells | v5 case | What happens |
|---|---|---|---|
| WCXY | 1,293 | B, both agree | No change. These wells become **WCXY witnesses**: Delaware WCXY sub-bench witnesses go from 500 to 1,793. |
| WCA_1 / WCA_2 | 953 | C, same unit, different sub-bench | Kept on Enverus's sub-bench (v5 `subbench_vendor`). v5.1 decides only placeholders, so **no step judges WCXY vs WCA_1 by depth on these wells.** |
| BS3_S / other units | 292 | D, unit conflict | v5 makes 60 depth calls to WCXY on these wells (55 from BS3_S). The class **BS3_S → WCXY (depth)** grows from 12 to **75 wells** across all wells, so it needs 10 cards. The rest are unresolved or guarded. |
| none | 3 (+4 'O') | A | sql/16 now gives WCXY (the 2 live NULLs are fixed). |

## The new row also changes wells that don't carry the XY string

v5 makes two population-level calculations, and the new wells feed both:

1. **The learned precedence table is keyed on UNIT pairs.** Novi `WOLFCAMP A` and Novi `WOLFCAMP A (XY)` both map to the
   WCA unit, so their conflicts with Enverus 3rd Bone Spring pool together.
   - The WCA-vs-BS3 pair grows from 134 to 412 conflicts. Novi's depth-decided share falls from 0.83 to 0.69, and the
     pattern loses its learned winner (Novi).
   - **20 wells that were class-accepted BS3_S → WCA_1 on that pattern** (Novi `WOLFCAMP A` + Enverus `3RD BONE SPRING
     (SAND)`; Pecos, Loving, Reeves, Eddy) **fall back to BS3_S**:
     - 18 are now unresolved;
     - 1 is a depth call for BS3_S;
     - 1 is still WCA_1 by depth, but on a basis that is no longer in an accepted class.
2. **Unit references blend sub-benches.** v5's WCA reference is unit-level. 1,293 new WCXY witnesses pull it shallower,
   e.g. 11,567 → 11,428 ft at one Eddy well.
   - **9 wells** (Novi `WOLFCAMP B` + Enverus `WOLFCAMP A LOWER`; Reeves, Loving, Eddy) go from "cannot tell" to a depth
     call for WCB_1, in a class you accepted.
   - This is the same blend that v5.2 rev 1 removed by using code-level references. v5 still has it.

In total, v5 changes its code on 85 non-XY wells. Only these 29 reach an accepted tag; the rest sit in classes that
were never applied.

## v5.2 and the reviewed cards

- **Move set:** 125 before, 125 now. One move is new and one dropped out.
- **New:** HARACZ AMO FEDERAL #009H (Eddy, 3001537153), AVA_0 → WCXY. Novi XY, Enverus UPPER AVALON; 2,944 ft off
  AVA_0, 29 ft from WCXY. Not carded.
- **No longer proposed:** card 11, SQUINTS 4 5 FEE #715H. Its input is now WCXY (sql/16, via the new row), and v5.2
  finds that within 600 ft of the WCA unit. **Your call is WCA_1, and the live warehouse now shows WCXY.** Your call
  wins once the rule lands, so confirm which you want.
- **Different proposal:** card 50, SALADO DRAW 9 16 W0BO FEDERAL COM #002H (Lea). It was OTHER → WCA_1 and you
  accepted; it is now OTHER → WCXY. Your accept stands as a call on WCA_1, but the evidence has moved.
- **Everything else** in the 140-well final set is unaffected. The class-accepted AVA_0 wells and the depth exclusions
  are unchanged.

## What this means for the warehouse step

1. **Freeze the learned precedence table as a reviewed artifact.** One crosswalk row flipped 20 accepted decisions
   through the learned table. In the nightly design, re-learning that table every night would let any population shift
   (new wells, a vendor re-tag) silently reverse decisions you reviewed.
   - The table should be part of the rule, versioned and changed only on review.
   - References (witness depths) should keep updating, because they are evidence.
2. **v5's unit-level references have the blend flaw v5.2 rev 1 fixed.** The 9 WCB_1 moves come from it. A v5 rev to
   code-level references would make v5 and v5.2 consistent. That reopens v5 and needs your call.
3. **Sub-bench vendor conflicts are not adjudicated anywhere.** That covers the 953 XY vs WCA_1 / WCA_2 wells, plus
   whatever other same-unit pairs exist. Today they keep Enverus's code. A depth decision for them would be a
   v5.1 extension.
4. **New cards** if the frozen acceptance is kept as is:
   - class BS3_S → WCXY (75 wells): 10 cards, accepted at 7/10;
   - class BS3_S → WCA_1 by depth crosses 20 wells (19 → 23): 10 cards;
   - HARACZ AMO #009H: 1 card;
   - card 50: a re-card;
   - SQUINTS: a confirmation.

**Correction (same day):** the BS3_S → WCXY class is 75 wells in all (55 of them XY wells), not 55. BS3_S → WCA_1 by
depth also crosses the 20-well bar. The string-keyed follow-up is `../string-key-dev-2026-11-09/`.
