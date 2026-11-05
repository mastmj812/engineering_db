# formation_blueox rule v3 — rule and criteria (step 1)

**Status:** DRAFT. These become FROZEN at the commit that adds this file. They are scored once, in step 2. Nothing is
applied.

- Code: `box/tag_rule.py`, constants in `RULE`, record via `rule_record()`. Tests: `tests/test_tag_rule.py`.
- Development run: `scripts/tag_rule_dev.py`. It reports churn plus the band test on the development fold only.

## 1. The rule in plain terms

For every producing horizontal (and, with one difference, every Novi stick):

0. **Evidence.**
   - Planned surveys are never evidence. Neither is a round-100 `tvd_ft` without a survey, nor a depth under
     4,000 ft.
   - Such a well is never a neighbour and never re-positioned; it keeps its vendor code with confidence low.
   - Depth = the lateral median survey TVD (sql/64) where the well has one, else `tvd_ft`.
1. **Family.** Families group the codes depth may split:
   - Delaware AVA = AVA_0 / AVA_1 / AVA_2; WCA = WCXY / WCA_1 / WCA_2; WCB = WCB_1 / WCB_2.
   - Midland WCB = WCB_1 / WCB_2.
   - Every other code is its own family. Sand vs carbonate is a lithology call, so BS2_C and BS2_S stay separate.

   The vendor family is kept unless depth is decisive:

   a. **Delaware, where the geologist's grid controls the well's interval.**
      - Controlled means at least half the lateral is in one interval, and both bounding surfaces have a pick
        within 1 mi.
      - Keep the vendor family if that interval holds it, or if the well is within 50 ft of the family's span.
      - Otherwise move to the interval's family.
      - His B2→C interval holds both WCB_2 and WCC, so that choice falls to the local bands, or no move.

   b. **Everywhere else (Midland; Delaware without control): local family bands.**
      - The median depth of each family among evidence neighbours within 1.5 mi, from their vendor codes.
      - Move to the adjacent family only when all of these hold:
        - the well is at least 100 ft closer to that band;
        - it is at least 150 ft off its own band;
        - both bands have 5 or more wells;
        - the two bands are at least 150 ft apart.

   **Never moved:**
   - into or out of WDFD / BRNT / MISS (the sql/23 guard);
   - a BS2_C↔BS2_S or BS3_C↔BS3_S swap;
   - across the XY top in Lea or Ward (rule B pending);
   - by the grid where the surface has no control (Pecos Wolfcamp), or into the held / suspect intervals (WCD,
     WOLFCAMP_D).

   A blocked or unplaceable move keeps the vendor code and is **flagged** (`family_flag`).
2. **Position, inside a multi-code family.**
   - Local code bands from evidence neighbours within 1 mi, widened to 1.5 mi when thin. Each code needs 3 or more
     wells.
   - Adjacent bands must be in the right order and at least **75 ft** apart. Otherwise depth cannot resolve them
     there, and the well **keeps its vendor code with confidence low** (Gate 0 Q1 (a)).
   - Boundaries are the midpoints between band medians, and the well takes the band its depth falls in.
   - **Confidence high** when its margin to the boundary is at least max(30 ft, a quarter of the gap); otherwise
     low. Low confidence is a flag only (Q3).
   - Two passes on producers, so mis-tagged wells stop anchoring the bands.
3. **Ratified overrides win**, applied after the rule (Q4). The rule never reads overrides, not even as neighbour
   evidence, so scoring the labelled set is not leaked.

**Sticks** use step 2 against the producers' final codes. A stick never changes family: a grid or band family
conflict is a flag, which is the Lea WCB case.

### Why these constants

None was tuned against a score:
- the 150 ft family gap and offset sit below every adjacent-family median gap in the baseline. The smallest are
  171 ft (Delaware BS3_S/WCXY and Midland WCB_2/WCC), and most are 190–570 ft;
- 75 ft sits below the median of every within-family split (104–250 ft): a local band pair closer than that is
  treated as unresolved;
- 30 ft is close to the band-test margin of record (25 ft);
- the radii are the scoreboard's.

There is one computational change. The widened ring is 1.5 mi, not the drafted 2.0 mi, because a 2-mi ring is
billions of lateral point pairs basin-wide. The rule's neighbour search uses 5 points per lateral; the scoreboard
keeps 10.

## 2. Development protocol

- **Fold:** a 6-mi checkerboard on the lateral's first point (EPSG:3083). Even cells are development, odd cells
  are test.
- **Before the freeze:** I look only at churn (all wells) and the band test on development-fold wells.
- **Not computed before the freeze:** the labelled-set score, grid agreement, and any test-fold number.

## 3. Acceptance criteria (FROZEN; scored once in step 2)

Candidates scored in step 2:
- `rule`: the rule's code, no overrides.
- `final`: the override where one exists, else `rule`.

They are compared with `live` (today) and `vendor`. The scoreboard params of record are those in
`box.tag_scoreboard.DEFAULT`, on survey depth (basis `best`). "Test fold" = odd cells.

**Labels** (never seen by the rule):

| # | Test | Pass |
|---|---|---|
| K1 | Carded labels, `rule` reproduction, per basin | ≥ 70 % in Delaware and in Midland (the class gate of record; `vendor` scores 1 % / 12 %) |
| K2 | Class-accepted labels (Midland), `rule` reproduction | ≥ 70 % |
| K3 | The 3 #230 holds | none moved with high confidence (each keeps its vendor code, or is low confidence) |

**Grid** (Delaware, test fold, `final` vs `live`). This is partly **by construction** where the rule used the grid;
step 2 reports how many wells had `family_basis = grid`.

| # | Test | Pass |
|---|---|---|
| K4 | Overall agreement | ≥ live |
| K5 | Per bench with ≥ 200 scored | not worse than live by more than 1.0 pt |
| K6 | Controlled agreement, all benches except the open boundaries | above live by ≥ 0.5 pt |

The open boundaries are the WCB_2 bench, and BS3_S and WCXY in Lea and Ward. They get the K5 guard only.

**Self-consistency** (test fold, 1 mi, `final` vs `live`):

| # | Test | Pass |
|---|---|---|
| K7 | Band disagreement, per basin | below live |
| K8 | Close-pair inversions 2+ benches apart, per basin | ≤ live |
| K9 | Adjacent-pair inversions, per basin | ≤ live |

**Guards** (all wells, `rule`):

| # | Test | Pass |
|---|---|---|
| K10 | Moves into / out of WDFD, BRNT, MISS; BS2/BS3 sand↔carbonate swaps; XY crossings in Lea / Ward | zero |
| K11 | Family moves | ≤ 5 % of producers per basin |

**Sticks:**

| # | Test | Pass |
|---|---|---|
| K12 | Pad 3240's Wolfcamp B sticks (`pad_name = 'Delaware Pad 3240'`, the v2 C4 set) | all WCB_1 |
| K13 | Lea's anomalous Novi Wolfcamp B sticks (#230 `sticks_anomalous.csv`) | ≥ 50 % flagged `family_conflict` |

**Reported, not gated:**
- churn by from→to and by basis;
- confidence by family (expected to be weak on the WCA family);
- the dev-fold numbers;
- stick churn, coarse-tag vs specific-tag sticks;
- held-out stick-like producer accuracy (v2 C1 method; the truth is the noisy `final` producer codes);
- BOX record pool flips (run 32 / run 30), scout labels, reconciliation re-matches.

A failed criterion is reported as a fail. There is no re-tuning after the score without a written, numbered
revision in §5.

## 4. What step 2 adds

- A scoring script that runs the scoreboard on `rule` / `final` and evaluates K1–K13.
- The stick pull: `curated.intel_locations` and its midpoint TVD.
- The blast-radius tables.

## 5. Revisions

| # | Date | Change | Why |
|---|---|---|---|
| — | — | — | — |
