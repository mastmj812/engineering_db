# W1: the tag rule on live data, as the nightly would run it (2026-11-09)

**Read-only.** Nothing was written to Supabase. This is step W1 of `../WAREHOUSE_STEP.md`; Gate W1 is Michael's review
of this report.

## How it was run

1. **Inputs, vendor-only:** `python -m box.tag_rule_inputs --cache <live cache>`.
   - New committed module, replacing the snapshot's ad-hoc caches.
   - It reads vendor strings, depths and geometry from `curated.wells`, plus surveys, the crosswalk, the human-call
     overrides and the BOX record extents.
   - It reads nothing tag-derived from `formation_blueox` / `wells_enriched`. Today's tag is joined only as a
     report-only column.
2. **Steps 1 → 2 → 3:** run on the live cache with:
   - policy v1;
   - every class decision (v5 rounds 1–2, policy-v1 rounds 1–2), from a later round winning on a repeat;
   - the Step 2 cards (`v5_1-cards-2026-11-06`);
   - the Step 3 cards (`v5_2-cards-2026-11-08`, `policy-v1-cards-2026-11-09/step3`).

   Outputs are in `live/step1`, `live/step2`, `live/step3`.
3. **The reference:** the same chain was run on the reviewed snapshot (Nov 5 + the XY row), so the comparison is
   like for like.
4. **The report:** `python -m scripts.tag_w1_report`; outputs in `report/`. The **applied** tag is what the warehouse
   would carry after cutover:
   - a human call (override seed or any carded verdict);
   - else a Step 3 move in an accepted Step 3 class;
   - else a Step 1 class-accepted tag;
   - else the vendor tag.

**Fixes made on the way:**
- **ACCEPT as a code:** `accepted_tags` read only "agree", so a policy-v1 ACCEPT would have become a bench code named
  "ACCEPT". It now takes the proposal; REJECT is never taken as a code.
- **Class decisions by round:** class decisions now come from every round, not only the last folder.
- Tests for both are in `tests/test_tag_w1.py`.

## 1. The input pull reproduces today's sql/16 exactly

- **The same wells:** 60,832 producing horizontals (Delaware + Midland), the same set as `wells_enriched`.
  - That is 146 more than the Nov 5 snapshot.
- **The same code on every well:** the reconstructed sql/16 code (human call, else vendor) equals the live
  `formation_blueox_base` on **all 60,832** wells.
- **Fast:** the pull takes 32 s.

## 2. Reproduction: 99.94 % identical

On the 56,713 wells judged in both runs:

| | Wells |
|---|---|
| applied tag identical | **56,679** |
| differs, and the well's own inputs moved | 32 |
| differs on neighbour evidence only | 2 |

**The 32 with moved inputs:**
- **30** are vendor → vendor: their sql/16 tag changed because Novi re-tagged them (30 Novi string revisions, 1 Enverus).
  Most are Lea.
- **CONDOR STATE #001H** now falls in class BS3_C → BS2_S (its Novi string changed).
- **IRONHOUSE 24 STATE COM #004H** leaves BS3_S → BS2_S and keeps BS3_S. Its Novi string and depth changed.

**The 2 on neighbour evidence:**
- **COACHWHIP 26 FEDERAL #002H** (Lea) joins BS3_C → BS2_S;
- **JUNIPER WEST 3H** (Upton) leaves WCA_1 → WCB_1 and keeps WCA_1.

This is the expected nightly behaviour: a well follows its own inputs and its neighbours' evidence, under policy that
doesn't move. Detail is in `report/reproduction_differs.csv`.

## 3. Cutover diff: what would change against today's warehouse

**1,353 wells in the frame** change their tag: Delaware 585, Midland 768. 1,285 of them are inside the BOX record
extents.

| Applied basis | Wells |
|---|---|
| Step 1 class-accepted | 1,009 |
| carded Step 1 / 2 call | 124 |
| carded Step 3 call | 95 |
| Step 3 class-accepted (OTHER → AVA_0) | 28 |
| sql/23 flip reverts to the vendor tag | 97 |

**sql/23 retirement on live:** 239 wells carry a sql/23 flip today.
- **In the frame (161):**
  - 30 keep their tag because the rule agrees;
  - 31 are decided by Step 3 cards;
  - 3 are decided by Step 1;
  - **97 revert** to the vendor tag, with nothing confirming the flip either way.
- **Outside the frame (78):** planned survey, permit-round depth, < 4,000 ft or no depth. They revert to the vendor tag
  when sql/23 becomes a pass-through.

That is RULE_V5_2's frozen retirement design. On Nov 5 the counts were 36 kept / 24 overruled / 97 revert / 77
outside; today's numbers are the live version of it. The list is `report/cutover_changes.csv` plus
`live/step3/sql23_outside_frame.csv`.

## 4. New wells

- **195 wells entered the frame** since the snapshot (Delaware 105, Midland 90), by first production or by a new survey.
  - 8 take an accepted class's answer automatically (Q2);
  - 187 keep their vendor tag.
- **31 left the frame.**

## 5. Card queue: 11 wells, all single cards

No change class of 20 or more wells is undecided.

**Step 2, sub-bench changes nobody carded (4).** These keep the vendor sub-bench until carded.

| Well | County | Now | Rule says | Lead |
|---|---|---|---|---|
| MEZCAL 10 FEDERAL COM #124H | Eddy | BS2_S | BS2_C | 314 ft |
| PERMIT 76-44 LOV UNIT 4H | Loving | WCA_1 | WCXY | 190 ft |
| SMALL EYED 54-1-36-25 UNIT 15H | Loving | WCA_1 | WCXY | 130 ft |
| KUDU 53-2-6 LOV E UNIT 6H | Loving | WCA_1 | WCXY | 109 ft |

**Step 3, depth-check moves not covered by an accepted class or a card (5).**

| Well | County | Now | Rule says |
|---|---|---|---|
| JAMES RANCH UNIT DI 7 SAWTOOTH FEDERAL C #804H | Eddy | BS2_S | BS3_C |
| VACA 24 FEDERAL COM #507H | Lea | BS2_S | BS3_C |
| JAMES 29 32 FEDERAL COM #024H | Lea | BS2_S | BS3_C |
| STARLIGHT 56-1-36-25 F 15H | Loving | OTHER | WCA_1 |
| TETON 56-2-35-23 G 14H | Reeves | OTHER | WCXY |

**Class identity (2), below.**

## 6. Class identity: the baseline matters for 5 wells

The reviewed classes were written from **today's tag**, which includes sql/23 flips. The nightly starts from the
**vendor tag**. Of the 99 sql/23-flip wells where the rule moves the well off its vendor tag, the gate gives the same
answer either way for 94, and differs for 5.

| Well | County | Vendor | Today | Rule | Today's class | Vendor class |
|---|---|---|---|---|---|---|
| POKER LAKE UNIT 30 BS #110H | Eddy | BS3_C | BS2_S | BS2_S | none (unchanged) | BS3_C → BS2_S (depth), **accepted** |
| POKER LAKE UNIT 27 BD #509H | Eddy | BS3_C | BS2_S | BS2_S | none | BS3_C → BS2_S (depth), **accepted** |
| MAHOGANY 24-13Q-56-1 32 323H | Loving | BS3_C | BS2_S | BS2_S | none | BS3_C → BS2_S (depth), **accepted** |
| FRODERICK 33 FEDERAL COM #501H | Lea | BS1_S | WCA_2 | WCB_1 | WCA_2 → WCB_1, **accepted** | BS1_S → WCB_1, never reviewed |
| GARDNER UNIT 15-10 3MH | Howard | MS | WCA_1 | WCB_1 | WCA_1 → WCB_1, **accepted** | MS → WCB_1, never reviewed |

**Recommendation: gate on the vendor tag, as designed.**
- The three Bone Spring wells then keep BS2_S, which both sql/23 and the rule support. Gated on today's tag, they would
  fall back to BS3_C.
- FRODERICK and GARDNER jump several benches from their vendor tag. They should be carded, not ride a class reviewed
  from a different starting point.

## 7. Human calls whose inputs moved since the card: 10 of 281 carded wells

Every call still stands. These are flagged for a look.

**Mostly survey depth that is new since the card** (the survey p50 was missing and now exists), within about 50 ft of
the vendor TVD.

**Worth a look:**
- **IRONHOUSE 19 STATE COM #003H** (policy-v1 card 27, called BS3_C): vendor TVD 9,384 → **9,744 ft (+360)**, with a
  new survey p50 of 9,579 ft.
- **POKER LAKE UNIT 23 DTD FEDERAL COM #178H** (v5.2 card 114, called WCB_2): today's warehouse tag moved WCB_2 → WCA_1
  since the card. The call wins at cutover.
- **ROCAZOLLER STATE 54-1-12 LOV 7H** (v5.2 card 113, SUSPECT TVD exclusion): Novi re-tagged it WOLFCAMP → CANYON, so
  its vendor tag is now OTHER. The depth is unchanged, so the exclusion holds.

**Novi now agrees with your call:**
- ROAD RUNNER FEDERAL COM #003H → BS2_S;
- CORAL PWU 28 #005H → BS1_S.

The list is `report/human_calls_inputs_moved.csv`.

## 8. Policy drift: 2 string pairs would gain a winner (report only)

The live data would teach Step 1 two winners that policy v1 doesn't have. Both are Delaware, Novi, at the small-sample
threshold (pairs two or more units apart).

| Novi string | Enverus string | Novi share |
|---|---|---|
| SECOND BONE SPRING | LOWER AVALON | 5 / 5 decided |
| WOLFCAMP A | MIDDLE AVALON | 4 / 5 decided |

The frozen policy ignores them: those conflicts stay unresolved, on the vendor tag. Adding them would be a policy v2 with
cards; nothing is proposed now.

## 9. Runtime

- **Pull:** 32 s.
- **Chain:** 15.0 min. Step 1 5 s, Step 2 5.8 min, Step 3 9.1 min.

  That was on the laptop with the reference chain running alongside, so a lone run should be no slower. It fits the
  nightly window (05:00 dispatch, done ~06:30 CT). W2 times it on an Actions runner before the shadow period.

## What W2 still has to change in the code

These are the known gaps between the dev chain and the nightly design. None affects the numbers above.
- **Depth exclusions aren't wired into the rule.** The 12 are held only by their card verdicts (input code kept). The
  nightly must also switch them off as witnesses (Q5), and let an exclusion lapse when the depth changes.
- **Class labels still read today's tag.** Gating moves to the vendor tag (section 6), and the class list moves to
  `ref.formation_tag_class`.
- **Card folders become seeded tables.** The calls go to the overrides seed; the classes, policy and exclusions go to
  their `ref` tables. The nightly reads tables, not docs folders.
- **The dev scripts' report-only uses of `live`** (sql/23 outcome tables, crossing areas) move into the run report.
