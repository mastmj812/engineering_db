# Rule v5.1 sub-bench cards — findings (marked 2026-11-08)

25 cards, a full review (every v5.1 change, not a sample). Each card decides its own well. Scored by
`scripts/tag_v5_1_score.py`, which writes `cards_scored.csv` and `score.json`. Nothing is applied.

**Reading of verdicts:**
- "ACCEPT" (any case, comment allowed) applies the proposed sub-bench.
- A reject keeps the v5 code.
- A bench code is Michael's call.
- Any other text is a hold.

`clarifications.csv` records what Michael said he meant on two cards. `cards_sample.csv` stays as he marked it, and the
`verdict_marked` column keeps the original.

## Result: 24 of 25 agree with the proposal; one is Michael's own call

| Move | Cards | Agree | Michael's call |
|---|---|---|---|
| BS2_S → BS2_C (Lea) | 7 | 7 | — |
| BS3_S → BS3_C (Lea, Eddy) | 13 | 13 | — |
| WCA_1 → WCA_2 (OXBOW 23 23 W1EH FED COM #001H, Eddy) | 1 | 1 | — |
| WCA_1 → WCXY (Loving ×3, Reeves) | 4 | 3 | 1 → BS3_S |

- **Every Bone Spring sand → lime call held, 20 of 20.** The vendor strings here are generic (Novi "WOLFCAMP" /
  "BONE SPRING", Enverus "2ND / 3RD BONE SPRING"). Depth carried the call, with leads of 217–604 ft.
- **The plain-median pre-check matched Michael on all 25.** It agreed on the 24 agrees. The one card it marked (MAKO,
  card 25) is the one he kept off WCXY.

## Cards 24 and 25: marked REJECT, clarified 2026-11-08

Both wells were moved from BS3_S into the WCA unit by **v5 class 8**, DE BS3_S → WCA_1 (pattern), accepted 8/10 in
round 2. Each card showed today's tag, then v5's code, then v5.1's proposal.

- **Card 24, PERMIT 76-44 LOV UNIT 8H (Loving): WCXY.** Michael's REJECT was aimed at v5's WCA_1. The well reads in
  line with the offset WCXY wells: depth 11,798 ft, WCXY reference 11,918 ft, WCA_1 reference 12,096 ft.
  - Class 8 was right that BS3_S is wrong here, and v5.1 resolved the sub-bench correctly. This counts as an agree.
- **Card 25, MAKO STATE 3-6 1H (Reeves): BS3_S, his call.** It sits just too shallow against the offset WCXY wells:
  depth 10,665 ft, WCXY reference 10,827 ft. Offset control is thinner here: no both-vendor BS3_S well within 2 mi.
  - This is a **class-8 unit miss**: the well stays in the Bone Spring.
  - v5.1 cannot see it, because it only moves sub-benches inside the unit v5 chose.
  - The class decision (8/10, made on its own cards) stands. This well is a carded call.

**Lesson for future cards.** With three tags on a card, a bare REJECT is ambiguous: it can reject the proposal or
v5's move. Ask the reviewer to write a bench code whenever the answer is neither the proposal nor v5's code.

## Card 12: the live tag moved after the snapshot

Michael noted: *"live is showing BS2_S rather than BS3_S."*

The card was right for the Nov 5 snapshot, and the warehouse has moved since. On CHILES 28 21 STATE COM #004H
(3002549588):
- **Snapshot (Nov 5):** `formation_blueox` = BS3_S, from Enverus.
- **Live (`curated.wells_enriched`, read 2026-11-08):** BS2_S, source `tvd_corrected`, with base BS3_S. sql/23's gross
  depth correction now lifts it a member.

His accept is BS3_C, at 10,898 ft against the local BS3_C reference of 10,877 ft, so the lift to BS2 is wrong here.
sql/23 reads a BS3 lime well as "too shallow for BS3_S". That is the blind spot v5.1 addresses, and it shows on
sql/23's side.

**Snapshot drift.** Of the 56,744 producers present in both the snapshot and live, 51 changed tag in three days. 50 of
the 51 are inside the BOX extents.
- Most are Novi revisions in place, mainly Bone Spring lime ↔ sand and BS2 ↔ BS3.
- 5 are sql/23 changes.

The warehouse step must therefore rebuild from live at apply time. Carded calls (Michael's, by api10) stand whatever
the vendors do since.

## What applies (with the warehouse step only, on Michael's explicit go)

- **24 wells** get the proposed sub-bench.
- **Card 25** gets BS3_S, his call.
- All 25 carry `subbench_basis = human` (a carded call).
- **The 447 rows on the placeholder default** keep it, flagged `vendor default`.
- **The 21 rows with inverted references** (Delaware 3, Midland 18) keep it too, flagged as inverted.
