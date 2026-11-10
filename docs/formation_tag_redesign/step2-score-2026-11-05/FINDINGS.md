# Rule v3 — the one score (step 2, 2026-11-05)

**Verdict: FAIL.** 6 of the 13 frozen criteria fail, including all three independent label tests (K1–K3). Per
RULE.md §3 a failed criterion is a fail, and nothing was re-tuned after the score.

- **Rule:** frozen at 1be65da, with revision 1 at 66bf9e8 (grid control on every interval boundary, fixed before
  any score).
- **Scoring code:** committed at 0fcd574, before the run.
- **Run:**

  ```
  python -m scripts.tag_rule_score --cache <scoreboard cache> --out <this folder>
  ```

  Read-only. Producers come from the scoreboard's 2026-11-05 pull; sticks, BOX, scout and recon were read live.

## Criteria

| # | Test | Result | Pass |
|---|---|---|---|
| K1 | Carded labels reproduced by `rule` (≥ 70 % each basin) | Delaware **38.9 %** (42/108), Midland **30.1 %** (31/103) | **FAIL** |
| K2 | Midland class-accepted (≥ 70 %) | **42.7 %** (97/227) | **FAIL** |
| K3 | 3 holds: none moved with high confidence | BELL LAKE UNIT NORTH #407H and BILBREY 34 27 #001H moved WCA_2→WCA_1, **high** | **FAIL** |
| K4 | Grid agreement, Delaware test fold, `final` ≥ live | 86.7 % vs 85.0 % | pass |
| K5 | Per bench (≥ 200 scored) not worse than live by > 1 pt | WCB_2 **−1.5 pt**; the other 12 benches +0.1 to +4.9 | **FAIL** |
| K6 | Controlled agreement excluding open boundaries, ≥ live + 0.5 | 92.7 % vs 89.9 % | pass |
| K7 | Band disagreement, test fold, below live | Delaware 6.0 vs 10.0 %; Midland 3.7 vs 5.2 % | pass |
| K8 | Close-pair inversions 2+ benches apart ≤ live | Delaware 0.58 vs 0.85 % pass; Midland **0.19 vs 0.12 %** | **FAIL** |
| K9 | Adjacent-pair inversions ≤ live | Delaware 3.10 vs 3.85 %; Midland 0.54 vs 0.84 % | pass |
| K10 | Protected / lithology / Lea-Ward XY moves = 0 | 0 / 0 / 0 | pass |
| K11 | Family moves ≤ 5 % | Delaware 2.7 %, Midland 2.5 % | pass |
| K12 | Pad 3240 Wolfcamp B sticks all WCB_1 | 4/4 WCB_1 (low confidence) | pass |
| K13 | Lea anomalous WCB sticks ≥ 50 % flagged | **47.7 %** (619/1,297) | **FAIL** |

The grid passes (K4 and K6) are partly by construction: the rule set the family by grid on 14,509 Delaware wells
and moved 502 of them.

## Why it fails: consistent with its neighbours, not with you

The rule raises self-consistency (K7, K9) and agreement with the grids it uses (K4, K6). It does **not** reproduce
the human calls. Here is how the labels it misses break down:

| Labelled wells | Reproduced | Rule kept the vendor code | Moved elsewhere |
|---|---|---|---|
| Delaware carded, sub-bench call (same family) | 34 | 32 | 0 |
| Delaware carded, family call (e.g. WCB_2→WCC, WCA→WCB) | 8 | 32 | 7 |
| Midland carded, sub-bench call | 20 | 10 | 0 |
| Midland carded, family call | 11 | 63 | 0 |
| Midland class-accepted, sub-bench call | 97 | 82 | 1 |
| Midland class-accepted, family call | 0 | 50 | 1 |

1. **Family calls are mostly out of reach.**
   - The thresholds (150 ft off its own band, 100 ft closer to the next) are too conservative for the family errors
     you found. Many of those are WCB_2↔WCC and WCB↔WCC at about 170–250 ft.
   - 47 Midland labels have vendor code OTHER (to WCD / WCC). The rule never touches an off-column code, by design.
2. **Sub-bench calls are anchored on the vendor's own errors.**
   - The local bands are built from neighbours' vendor codes. The errors your screens corrected were whole local
     classes: the step-20a Midland WCB_1/WCB_2 classes, and the Delaware WCB audit.
   - So the neighbours carry the same error, and the bands agree with the vendor: 12 Delaware and 36 Midland
     labelled wells were placed by local bands and still kept the vendor code.
   - Two passes don't get out of a locally coherent error.
   - This is the "consistent but wrong" failure the scoreboard was designed to catch, and it caught it.
3. **The two holds were moved the wrong way.** You judged both as "not WCA, but no deep neighbours to say what".
   The rule moved them shallower inside WCA, with high confidence, because the WCA bands around them are dense. A
   confident within-family call can't see that the family itself is wrong.
4. **K13 misses narrowly** (47.7 %). Why the other 52 % are unflagged (no grid control, no band, or below the
   thresholds) was not broken down. Multi-code-family sticks with a producer within 1.5 mi sit a median 0.12 mi from
   one; 8,074 have none within 1.5 mi.

## Blast radius (reported; moot unless a rule passes)

- **Producers:** Delaware 2,643 and Midland 1,165 wells change vs live.
- **BOX record oil pools:** 1,053 of 7,526 members change code; 10 leave their pool. The pools already lump the
  sub-benches.
- **BOX record sticks** (`blast_box_record_sticks.csv`, stored `formation_blueox`):
  - Delaware run 32: 3,907 of 48,148 covered sticks change (8.1 %).
  - Midland run 30: 420 of 28,801 (1.5 %).
  - The script's first pass compared against the BOX pool bench (`WCA`) and overcounted. That was fixed after the
    run, and this one table was recomputed.
- **Scout labels:** 4,052 of 76,949 (5.3 %).
- **Reconciliation:** 5,434 stick tags and 924 matched-well tags change.

## What this says about the design (for Gate 2)

What works: the families (vendor), the guards, and survey depth. What fails is reading sub-benches, and modest
family errors, off **neighbours' vendor codes**.

Your 15 rule-V verdicts point to what did work:
- position measured as an offset from a **reliable reference**: clean witnesses of the family above, with the
  depth placed on a ladder of median rungs;
- the rungs taken from wells where the vendors agree.

That is evidence the next revision should anchor position on depth below a reliable family band, not on
same-family vendor codes. The labels have now been seen, though, so a second score on them is no longer blind.
