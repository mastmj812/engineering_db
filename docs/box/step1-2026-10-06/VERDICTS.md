# BOX step 1 — card verdicts (Michael, 2026-10-07) and the resulting class rule

Source: `cards_sample.csv`, column `verdict` (142 cards): 84 AGREE, 37 REJECT, 4 "REJECT, TVD wrong
but it is a BS2_S", 17 inconclusive with comments. Precision below = agree ÷ (agree + reject);
inconclusive cards are excluded from the ratio but listed.

## 1. Precision by swap class

| class | cards | agree | reject | inconclusive | precision | disposition |
|---|---|---|---|---|---|---|
| BS3_S→BS2_S | 7 | 7 | 0 | 0 | 1.00 | **accept** |
| BS3_C→BS2_S | 10 | 9 | 1 | 0 | 0.90 | **accept** |
| OTHER→WCA | 9 | 7 | 0 | 2 | 1.00 | **accept** (see McGary duplicate below) |
| WCD→WCA | 4 | 4 | 0 | 0 | 1.00 | accept (small) |
| WCC→WCA | 10 | 7 | 2 | 1 | 0.78 | **accept** |
| WCB_1→WCA | 10 | 7 | 3 | 0 | 0.70 | **accept** |
| WCB_2→WCA | 10 | 7 | 3 | 0 | 0.70 | **accept** |
| WCA→WCB_2 | 10 | 3 | 0 | 7 | 1.00 of judged | accept for real-survey wells; planned-survey cards all read "TVD wrong, tag right" |
| WCA→WCC | 6 | 2 | 0 | 4 | 1.00 of judged | same as above |
| BS2_S→BS1_S | 5 | 3 | 2 | 0 | 0.60 | hold (thin) |
| BS2_S→BS3_S | 5 | 3 | 2 | 0 | 0.60 | hold (thin) |
| WCA→BS3_S | 10 | 4 | 6 | 0 | 0.40 | **reject** |
| BS3_S→WCA | 10 | 4 | 6 | 0 | 0.40 | **reject** |
| WCA→WCB_1 | 10 | 4 | 6 | 0 | 0.40 | **reject** |
| BS2_S→BS3_C | 10 | 3 | 6 | 1 | 0.33 | **reject** |
| BS2_S→WCA | 6 | 1 | 4 | 1 | 0.20 | **reject** — all four rejects: "TVD wrong, it is a BS2_S" |
| one- and two-card classes (BS1_S→WCA, AVA_1→WCA, BS2_S→WCB_1, BS1_S→BS2_S, WCA→BS3_C, WCA→BS2_S, BS3_C→WCA, WDFD→WCA) | 10 | 9 | 0 | 1 | — | accept individually; too thin for a class rule |

Reading: flags **into** the pilot pools from deeper or coarser tags (WCB, WCC, WCD, OTHER → WCA;
BS3 → BS2_S) are reliable; flags **across the thin boundaries** (WCA↔BS3_S, WCA→WCB_1, BS2_S→BS3_C)
are coin flips, and flags that move a Bone Spring well into the Wolfcamp are wrong — the TVD is
wrong, not the tag.

## 2. What separates agree from reject (judged cards, n = 125)

| subset | n | precision |
|---|---|---|
| all judged | 125 | 0.67 |
| real survey | 105 | 0.72 |
| planned survey | 20 | 0.40 |
| sql/23 nearest band concurs with the suggestion | 70 | 0.76 |
| sql/23 does not concur | 55 | 0.56 |
| into a pilot pool | 79 | 0.76 |
| out of a pilot pool | 46 | 0.52 |
| real survey AND sql/23 concurs | 59 | 0.80 |
| into pilot AND real survey AND sql/23 concurs | 40 | 0.88 |

Two second votes raise precision: the live sql/23 band audit concurring, and a real (not planned)
survey. Nearest-band distance (≤ 50 ft: 0.74 vs > 50 ft: 0.59) helps less than either.

## 3. Rule of record proposed from the verdicts (BOX-only; no warehouse change)

1. **Class gate:** apply a consensus flag only in an accepted class (precision ≥ 0.70 above). Rejected
   classes keep their tag. Hold classes (0.60, n = 5) keep their tag until a second sample.
2. **Second vote:** within an accepted class, apply the flag only when sql/23's nearest band concurs
   with the suggestion (0.76 → 0.80–0.88). Non-concurring flags are listed, not applied.
3. **Planned-survey subjects (the A refinement, "A′"):** a consensus flag on a planned-survey well means
   *TVD suspect*, not *tag wrong*. Keep the tag as bench evidence for extents and cohorts; drop the
   well as a depth witness and from any TVD statistic. This is what every planned-survey comment
   says (Poker Lake, Goonch, Cicada: "GOR looks like a WCA, TVD is wrong").
4. **Bone Spring → Wolfcamp flags are never applied** (BS2_S→WCA 0.20; the sand/carbonate lith guard
   already blocks BS2_S↔BS2_C). A Bone Spring well sitting at a Wolfcamp depth is a TVD defect.
5. **GOR as a tiebreak:** Michael used the GOR trend vs neighbours to resolve the questionable cards.
   Proposed for cards v2 and as a detector score: 12-mo GOR (cum_12m_gas ÷ cum_12m_oil) of the subject
   vs the local cohort GOR of its tagged bench and of the suggested bench; a flag that also moves the
   well toward the bench whose GOR it matches is "GOR-consistent". Not yet implemented.

Effect on the evidence sets (from the step-1 sensitivity): applying every flag moved the WCA cohort
median 12-mo oil/ft by −0.3 % and BS2_S by 0.0 %, so the rule above matters for extent edges and
bench membership of individual wells, not for the cohort statistics.

## 4. Data defects surfaced by the cards (vendor data, not tags)

- **Diez Unit 10 2H (4238937383), Reeves.** Michael drilled it: TVD 10,383 ft. Warehouse TVD 10,896 ft
  comes from Novi (WellDetails and Wells both 10,896, MD 20,548); Enverus has TVD 10,430 ft, MD 18,926,
  lateral 8,112. The Novi record is wrong (and its MD suggests a different wellbore). The local WCA_1
  band median is 10,383 ft — exactly his number — so the tag is right and the TVD is a Novi defect.
  Precedence rule (sql/04: Novi WellDetails > Novi Wells > Enverus) carries it through. Raise with Novi;
  candidate for a per-well TVD override table if more appear.
- **McGary-Tudor West 4H / East 5H, Reeves: duplicate wellbores.** Two api10s each at the same surface
  location: 4238939884 / 4238941440 (West 4H, Upcurve Energy vs Perun Energy, first prod 2024-10-01 /
  2024-10-21) and 4238939885 / 4238941441 (East 5H). The Upcurve records carry Enverus interval
  "LOWER PENNSYLVANIAN" → OTHER; the Perun records WOLFCAMP A UPPER → WCA_1. Same well, re-permitted
  under a new API after an operator change, and both carry production. Raise with Novi/Enverus; for
  BOX, the OTHER-tagged duplicate must not count as a second well (volumes would double).
- **"Can't find" ×3:** Oatmeal 8 Federal Com #002H (3001534505, Eddy, 2007 vintage, BS2_S), Forge
  Federal Com #703H (3002551417, Lea, 2024, planned survey), Cimarex University 18-41 'B' 1H
  (4247535273, Ward, 2008, WCXY). All three exist in `curated.wells_enriched`; the anduin sync has no
  vintage filter that would drop them. Question for Michael: searched by name or api10? (the 2008
  Cimarex well's api14 suffix is -02-00, a sidetrack, and the two old wells may sit outside the
  anduin map's default date range).

## 6. Decisions (Michael, 2026-10-07) and what was applied

1. **Rule accepted** (§3) and implemented in `box/qc_rule.py`; applied by `scripts/box_apply_rule.py`,
   which also loads the card verdicts: **a per-card AGREE / REJECT outranks the class rule for that
   well** (84 agree / 41 reject loaded).
2. **Hold classes:** a second sample of 10 was requested, but BS2_S→BS1_S and BS2_S→BS3_S have exactly
   5 flags each in the whole population and all 10 were in the first sample. The classes are
   exhausted; they resolve per well on the existing verdicts (3 agree / 2 reject each).
3. **GOR formalised:** `gor12` (Novi cum_12m_gas × 1000 ÷ cum_12m_oil, scf/bbl) on every well; the
   detector now carries the local cohort median GOR per bench among the 1.5-mi witnesses and a
   `cons_gor_vote` (own / suggest / none; none when the two benches' GOR are within 25 % or either
   side is missing). The rule uses it as a veto (GOR says "own" → flag not applied); the cards carry
   a fourth panel (12-mo GOR by bench, subject dashed) from the next build on.
4. **Diez TVD and the McGary-Tudor duplicates:** batched with the next Novi vintage query.
5. **"Can't find" in anduin:** searched by api10. Not geometry — all three have valid sticks in the
   warehouse. Forge Federal Com #703H (3002551417) IS in anduin's wells table with geometry, so that
   one is a map-search or default-filter miss; Oatmeal 8 Federal (2007, 2,305-ft lateral) and Cimarex
   University 18-41 'B' 1H (2008, 3,164 ft, api14 sidetrack suffix -02) are NOT in anduin's synced
   universe — the sync drops them (old short laterals). Logged as an anduin follow-up, not a step-1 item.

**Final well sets** (`wells_final_WCA.csv`, `wells_final_BS2_S.csv`; `rule_summary.json`), pulled
2026-10-07 (production as-of 2026-08-01; tagged counts differ from the 2026-10-06 build by a handful
of wells after a nightly tag refresh):

| pool | tagged | after rule | reassigned out | reassigned in | TVD-suspect (tag kept, not a depth witness) | depth witnesses | D9 cohort |
|---|---|---|---|---|---|---|---|
| WCA | 12,182 | 12,306 | 14 | 138 | 32 | 11,076 | 7,562 |
| BS2_S | 4,306 | 4,359 | 10 | 63 | 12 | 3,490 | 1,898 |

Flags kept by reason (WCA): 932 in-pool swaps (moot), 218 into WCXY (D20), 113 WCA→WCB_1 and 110
WCA→BS3_S class-rejected, 12 card REJECTs, 5 accepted-class flags without sql/23 concurrence, 1 GOR
veto. BS2_S: 30 BS2_S→BS3_C class-rejected, 10 card REJECTs. Columns per well: `box_bench`,
`box_action` (keep / reassign / tvd_suspect), `box_depth_witness`, `box_reason`.

## 5. Open questions for Michael (answered 2026-10-07 — see §6)

1. Accept the class dispositions in §1 and the rule in §3 as the step-1 output (class gate +
   sql/23 second vote + A′ for planned-survey wells + no Bone Spring → Wolfcamp)?
2. Hold classes BS2_S→BS1_S and BS2_S→BS3_S (0.60, n = 5 each): keep the tag, or second sample?
3. GOR tiebreak: worth formalising into the detector and cards v2, or leave as a reviewer's tool?
4. Diez and the McGary duplicates: raise with Novi now, or batch with the next vintage query?
5. The three "can't find" wells: how were they searched (name vs api10)?
