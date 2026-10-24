# BOX step 16b — cohort-selection variants: PRE-REGISTRATION (written and committed before any step-16 variant is scored)

Written 2026-10-22, before `scripts.box_acceptance --step16` has run anywhere. The code these rules name is
`box/analog.Rules` + `select_cohort_v2(rules=...)` + `lateral_multiplier`, `box/step16.py` and the `step16` path of
`box/acceptance.py`. The commit that adds this file is the pre-registration timestamp, and gate 16b stamps the frozen SHA
below. Nothing below changes after a score is seen. A change needs Michael, and a later commit that says why.

**What has been read before this file (disclosed).** Step 16a (`docs/box/cohort-review-2026-10-22/`) read the PRODUCTION
selection of run 10 against local wells' actual year-1 (no variant, no tuning outcome). The first BS1_S pass (2026-10-22,
scratch, reported to Michael) also read the RECORD variant's existing tuning + holdout views by radius reached (BS1_S oil-12
−30 % at 5–7.5 mi, −12 % at 20 mi; other benches likewise) and ran a six-rule counterfactual on BS1_S production PUDs (EUR only,
no outcome). The revision below looked at Pad 1925's SELECTION under each variant (which wells, how far; no outcome). No tuning
or holdout outcome has been computed for any variant named here.

## Revisions (before any score)

| date | change | why |
|---|---|---|
| 2026-10-22 (eng_db #187) | first registration: variants `box_v2s`, `_lat`, `_lo`, `_r1`, `_r1lo` | — |
| 2026-10-22 (this commit) | **Lateral is a translation, not a filter** (Michael): new `box_v2s_tr`, candidates `box_v2s_r2` / `box_v2s_r2lo` (translate + ladder count → spacing); `box_v2s_r1` kept as the COMPARISON, never adopted; `box_v2s_lat` and `box_v2s_r1lo` dropped; the per-bench Cui-vs-linear check added (§6b) and made adoption condition 6 | Lateral length is correctable by the Cui & Cross relationship (D50); distance — the rock — is not. The record already trusts Cui for a 2× translation (10,000-ft analogs → 5,080-ft sticks) while excluding a 1.3× one (→ 7,720 ft) — the Pad 1925 case. Cui is a Wolfcamp A, 3-yr-cum relationship, so whether it holds on each bench is tested, not assumed. |

## 0. Kickoff (Michael 2026-10-22)

1. **D118** — diagnose every bench; selection-rule changes go to the provisional groups first; validated groups only on evidence
   with their own re-acceptance; short-history wells: TEST the level-only middle path, not adopt.
2. **D119 (gate 16a)** — the spacing fix applies on ALL benches, validated included; the validated groups' TUNING cells are
   re-scored with it.
3. The D52 holdouts are not scored again: validated groups' were scored once (D59 / D100 / step 15); provisional groups' failed
   (BS3_S, BS3_C, WCB_2, BS1_S) or never existed (AVA_0 / 1 / 2, BS2_C). Step 16 scores TUNING packages only (`run` refuses
   `step16` with `score_holdout`), then confirms prospectively.
4. **Lateral (Michael, gate-16b discussion):** lateral similarity is not a rule. Every cohort is translated to the location's
   completed lateral by Cui & Cross; analogs must have a completed lateral of 5,000–15,000 ft (the paper's Delaware points run
   5,000–12,500 ft; one extrapolated step beyond).

## 1. Priority order and the ladder

Highest first: **same bench > distance > spacing representativeness > count**; lateral length is translated, never relaxed.
It becomes the ladder of `box_v2s_r2`: at every ring, while it holds fewer than 10 eligible wells, give up the LOWEST-priority
rule first, cumulatively, before the radius grows — count (accept ≥ 5), then spacing (admit standalone). Same bench is never
relaxed.

## 2. Variants (`box/step16.VARIANTS`; every variant — and every linear twin — gets its own F(k), as the harness calibrates every variant)

| variant | pool spacing | rules | role |
|---|---|---|---|
| `box_v2` / `box_v2_wf` | training cohort only (the record) | record | the record variant of each group, re-scored on the same run for a same-data comparison |
| `box_v2s` | **measured, every pool well** (D119) | record | the new base, every group |
| `box_v2s_wf` | measured | record, × walk-forward haircut (D57) | the new base for the groups whose record carries a haircut (WCA, BS2_S) |
| `box_v2s_tr` | measured | lateral = translate | attribution only, never adopted |
| `box_v2s_lo` | measured | level-only | attribution only, never adopted |
| `box_v2s_r1` | measured | relax = (count, spacing, ± 40 % lateral band + Cui) | the COMPARISON (the first ladder), never adopted |
| `box_v2s_r2` | measured | lateral = translate; relax = (count, spacing) | adoption candidate (provisional groups) |
| `box_v2s_r2lo` | measured | r2 + level-only | adoption candidate (provisional groups) |
| `box_v2s_tr_lin`, `box_v2s_r2_lin` | measured | the same cohorts, scaled LINEARLY per ft | the Cui-vs-linear check (§6b), never adopted |

Rule details (`box/analog.Rules`; the defaults reproduce the record selection — pinned by tests and verified on all 50,963
run-10 PUDs, 0 differences, re-verified after this revision):
- **Measured spacing** = `curated.wells_enriched.lateral_closer_xy_ft` for every pool well; NULL stays NULL (standalone, as
  deal-intake reads it); ≥ 2,800 ft = the Novi no-neighbour sentinel (standalone).
- **translate** — the candidate's COMPLETED lateral (D56: reported minus the skipped curve for a U-turn) must lie in
  `translate_range` = **5,000–15,000 ft**, whatever the location's lateral; the cohort's per-1,000-ft P50 curve is scaled to the
  location's completed lateral L by L / 1,000 × E(L) / mean E(L_member) (Cui & Cross 2,000 lb / 60 bbl per ft, `box/lateral.py`;
  E flat below 5,000 ft, the last segment extended past 12,500 ft). Applies to short laterals too (they drop the record's
  7,500–12,500 ft band). Flag `lateral translated (Cui, range)`.
- **count** — the ring is accepted at ≥ `count_floor` = **5** eligible wells (flag `relaxed: count (n < 10)`).
- **spacing** — standalone wells are admitted; tight wells (< 0.65 × planned spacing) stay out.
- **lateral band** (`box_v2s_r1` only) — completed laterals ≥ 7,500 ft: band ± `wide_tol` = 40 % and Cui translation; shorter
  laterals keep the 7,500–12,500 ft band.
- **level-only** — a well under the 6-month floor is admitted when its oil peak is ≥ **3 calendar months** behind it (onset +
  peak index); its own qi and the cohort's long-well (≥ 9 months after peak) median Di / b (the D57 short-history transfer).
  Counted toward the cohort size, flagged `level_only: k`. If a cohort holds no long well, the short well keeps its own fit —
  flagged by the existing transfer path, reported.

Pad 1925 (BS1_S, 7,720 ft), selection only: record 6 wells at 14–19 mi; `box_v2s` 9 wells at 9–19 mi; `box_v2s_tr` 13 wells at
1.7–6.9 mi (7.5-mi ring, Cui × 1.049); `box_v2s_r1` and `box_v2s_r2` the five QUINN wells at 1.7–2.6 mi (5-mi ring, count given up,
Cui × 1.063).

## 3. Runs (step 16c)

- `python -m scripts.box_acceptance --fold analog --bench <G> --step16 --actuals-through 2026-07-01` for each of the 13
  production groups, with the well set and tags of record (`production_run9.wells_dir`, `BENCH_SPECS`; WCA also on `--fold full`
  as accepted), cutoffs 2019-12-01 … 2024-12-01, D52 salt / blocks unchanged. Actuals pinned to 2026-07-01 (run 10's data
  through); the D98 guard applies to the record variant: re-scored `box_v2` cells vs the cells of record = code identical + data
  drift explained.
- Scored per (group × stream × horizon) on the D53 package grain; per-cutoff cells and pooled (D99-form) cells both written.

## 4. Validated groups (D119): re-score rule

WCA (`box_v2s_wf`, per-cutoff D53 cells as accepted, D58 / D59), BS2_S (`box_v2s_wf`, pooled D99-form), WCXY_WCA1, WCB_1, WCC
(`box_v2s`, raw, pooled D99-form). A validated group **stays validated** when, on the same run:
1. every judged cell of its new base has |package bias| ≤ 10 %, AND
2. its new base fails no more judged cells than its re-scored record variant.

Otherwise the group goes to Michael with the cells — no automatic demotion, and no reverting the fix (D119 decided it).
**Walk-forward haircut (WCA D62, BS2_S D102):** proposed = recomputed from the `box_v2s` TUNING cells only (D102's tuning +
holdout merge cannot be reproduced without a second holdout look). Michael confirms at gate 16b. The Cui-vs-linear check (§6b)
is reported for the validated groups too; any flag goes to Michael (16e).

## 5. Provisional groups: adoption rule (`box/step16.adopt`; ONE variant for all eight groups, no per-group choice)

Inputs, pooled over AVA_0, AVA_1, AVA_2, BS2_C, BS3_S, BS3_C, WCB_2, BS1_S:
- the pooled (D99-form) tuning cells, oil + gas, cum-12 / 24 / 36, judged at ≥ 30 packages;
- the **far-with-local stratum**: scored wells whose selection reached ≥ 15 mi while ≥ 3 local wells existed at the cutoff
  (local = pool wells within 3 mi, ≥ 12 months, first production ≥ 2016, any lateral / spacing — `step16.local_evidence`);
  well-level Σ actual / Σ predicted − 1, oil cum-12 (`step16.stratum_bias`). The stratum is ONE fixed set of scored wells,
  defined by the base `box_v2s` selection (`box_v2s_radius_mi` ≥ 15 and `n_local` ≥ 3), and every variant is scored on that
  same set;
- **off-local share** on the production PUDs of run 10 (the 16a review re-run per variant): among far-with-local PUDs, the
  share whose cohort year-1 is > 25 % from its local wells';
- the **level-only hindcast** (§6) and the **Cui-vs-linear check** (§6b).

A candidate (`box_v2s_r2`, `box_v2s_r2lo`) passes against `box_v2s` when ALL hold: (1) it fails no more judged cells;
(2) its median |pooled package bias| over judged cells is ≤ the base's + 1 point; (3) its far-with-local |bias| ≤ the base's;
(4) its off-local share ≤ the base's; (5) a level-only candidate also has |hindcast bias| ≤ 15 %; (6) the Cui translation holds
(§6b, `step16.cui_holds` on `box_v2s_r2`; both candidates share its translation). Any NaN, or a check not run, fails.
Among passing candidates the lower median |bias| wins; a tie goes to the one without level-only. **None passing → `box_v2s` is
the provisional record** (the spacing fix alone). `box_v2s_r1` is reported beside them and never adopted; validated groups'
candidate numbers are reported, never adopted (D118, 16e).

## 6. Level-only hindcast (the D118 middle-path test)

At each tuning cutoff, every pool well with 3–5 calendar months after its oil peak (and ≥ 9-month long wells in its own
`box_v2s_r2` cohort as donors): predict its NEXT 12 months of oil from its own qi and the donors' median Di / b
(`members_with_transfer`), and compare with actual. Pooled bias = Σ actual / Σ predicted − 1 over all provisional groups.
For reference, the 2026-09-21 deal-intake hindcast found the transferred forecast 6–11 % high at 9 months after peak. The code
lands in 16c BEFORE this hindcast runs and is checked against this paragraph; its definition here does not change.

## 6b. Cui-vs-linear check (per bench; `step16.cui_vs_linear`, `cui_holds`, `cui_flags`)

For `box_v2s_tr` and `box_v2s_r2`, each scored well is predicted twice from the SAME cohort: Cui-translated (the variant) and
linearly per ft (its `_lin` twin). Length mismatch = the well's completed lateral ÷ its cohort's mean completed lateral:
**shorter** < 0.80, **near** 0.80–1.25, **longer** ≥ 1.25. Per class, well-level Σ actual / Σ predicted − 1 for both, oil + gas,
cum-12 / 24 / 36, per group and pooled.
- **Condition 6 (adoption):** pooled over the provisional groups, `box_v2s_r2`, oil, at cum-12 AND cum-24: the Cui |bias| summed
  over the shorter and longer classes (each used only with ≥ 10 scored wells) is ≤ the linear twin's. The classes are judged
  separately because linear scaling errs in opposite directions on shorter and longer laterals, which cancel when pooled.
  A horizon with no usable class fails.
- **Flags (any group, any tier):** a group where the Cui sum exceeds the linear sum by more than 5 points at cum-12 or cum-24 is
  listed for Michael with its numbers — not changed automatically.
- Each twin carries its own F(k), so the check reads how the length-scaling bends with mismatch, not a uniform level difference
  F(k) absorbs.

## 7. Reported, never judged

Attribution and comparison variants; median |package error| and share > 25 % off (`step16.abs_error_stats`) for every variant;
per-cutoff cells; per group; radius-class distribution per variant; the Cui translation factor distribution per variant; the
PUD-level EUR change per variant on run 10's production universe; the BS1_S curve-construction offset (the record P50's month
1–12 vs its own cohort's actual cum-12, +13 to +16 % on BS1_S), diagnosed on every group.

## 8. Gate 16b — CLOSED 2026-10-22 (Michael, D120)

Settled in the revision: the priority order (§1), the translate rule and its 5,000–15,000 ft range (§2), the Cui-vs-linear check
as condition 6 (§6b). Confirmed at the gate: `count_floor` 5; the WCA / BS2_S walk-forward haircut from the `box_v2s` TUNING cells
only (§4); the validated keep-rule (§4) and one variant for all eight provisional groups (§5).

**Frozen SHA: `109f80540284426fde3c5fa0f44c2788d18e605c`** (main, merge of eng_db #188). Every 16c run records its own SHA; a run
whose `box/`, `scripts/` or `dealintake/` differ from this SHA is not a 16c score. The §6 hindcast and the §5 off-local inputs are
code written in 16c after the freeze, checked against §5 / §6 as written here, before they run.
