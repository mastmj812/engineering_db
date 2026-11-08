# Rule v5.1 sub-bench cards — findings (marked 2026-11-08)

25 cards, a full review: each card decides its own well. Scored by `scripts/tag_v5_1_score.py`, which writes
`cards_scored.csv` and `score.json`. Nothing is applied.

**How verdicts are read.** "ACCEPT" (any case, comment allowed) applies the proposed sub-bench. Reject keeps the v5
code. A bench code is Michael's call. Any other text is a hold.

## Result: 23 of 25 applied

| Move | Cards | Agree | Reject |
|---|---|---|---|
| BS2_S → BS2_C (Lea) | 7 | 7 | 0 |
| BS3_S → BS3_C (Lea, Eddy) | 13 | 13 | 0 |
| WCA_1 → WCA_2 (OXBOW 23 23 W1EH FED COM #001H, Eddy) | 1 | 1 | 0 |
| WCA_1 → WCXY (Loving ×3, Reeves) | 4 | 2 | 2 |

- **Every Bone Spring sand → lime call held, 20 of 20.** The vendor strings here are generic (Novi "WOLFCAMP" /
  "BONE SPRING", Enverus "2ND / 3RD BONE SPRING"). Depth carried the call, with leads of 217–604 ft.
- **The plain-median pre-check called it.** It agreed on all 23 accepts. The one card it marked (MAKO, card 25) was
  rejected; it agreed on the other reject, card 24.

## The two rejects: both are WCA_1 → WCXY, in rule-v5 class 8

Both wells were moved into the WCA unit by **v5 class 8**, DE BS3_S → WCA_1 (pattern), accepted 8/10 in round 2. They
sit **above the WCXY reference**:

| Card | Well | Depth | WCXY ref | WCA_1 ref | BS3_S median (both vendors agree, ≤ 2 mi) |
|---|---|---|---|---|---|
| 24 | PERMIT 76-44 LOV UNIT 8H (Loving) | 11,798 | 11,918 | 12,096 | **11,786 (n=4): 12 ft away** |
| 25 | MAKO STATE 3-6 1H (Reeves) | 10,665 | 10,827 | 10,941 | none within 2 mi |

The two accepts sit closer to WCXY:
- SAN SABA 76 2932 112H: 103 ft below that BS3_S median and 76 ft above WCXY.
- BONGO 76-43 LOV UNIT 3H: 102 ft above WCXY.

Under the frozen reading, **reject keeps the v5 code, WCA_1**. By depth that is the *farthest* candidate for both wells.
Card 24 sits on the local BS3_S median, so the more likely truth there is the live tag, BS3_S. That is a class-8 unit
miss, which v5.1 cannot see: it only moves sub-benches inside the unit v5 chose.

**Open to Michael:** keep WCA_1, or write a code (BS3_S, the live tag) on cards 24 and 25. Until he answers, they
stay WCA_1, flagged.

## Card 12: the live tag moved after the snapshot

Michael noted: *"live is showing BS2_S rather than BS3_S."*

The card was right for the Nov 5 snapshot, and the warehouse has moved since. On CHILES 28 21 STATE COM #004H
(3002549588):
- **Snapshot (Nov 5):** `formation_blueox` = BS3_S, from Enverus.
- **Live (`curated.wells_enriched`, read 2026-11-08):** BS2_S, source `tvd_corrected`, with base BS3_S. sql/23's gross
  depth correction now lifts it a member.

His accept is BS3_C. That puts it at 10,898 ft against the local BS3_C reference of 10,877, so the sql/23 lift to BS2
is wrong here. It reads a BS3 lime well as "too shallow for BS3_S". This is the same blind spot v5.1 fixes, and it
shows on sql/23's side.

**Snapshot drift overall.** Of 56,744 producers in both the snapshot and live, 51 changed tag in three days, 50 of
them inside the BOX extents:
- most are Novi revisions in place, mainly Bone Spring lime ↔ sand and BS2 ↔ BS3;
- 5 are sql/23 changes.

The warehouse step must therefore rebuild from live at apply time. Carded calls (Michael's, by api10) stand whatever
the vendors do since.

## What applies (with the warehouse step only, on Michael's explicit go)

- **23 wells** get the proposed sub-bench, with `subbench_basis = human` (a carded call).
- **Cards 24 and 25:** WCA_1, pending his answer above.
- **The 447 rows still on the placeholder default** keep it, flagged `vendor default`.
- **The 21 rows with inverted references** (Delaware 3, Midland 18) keep it too, flagged as inverted.
