# BOX step 16b — cohort-selection variants: PRE-REGISTRATION (written and committed before any step-16 variant is scored)

Written 2026-10-22, before `scripts.box_acceptance --step16` has run anywhere. The code these rules name is
`box/analog.Rules` + `select_cohort_v2(rules=...)` + `lateral_multiplier`, `box/step16.py` and the `step16` path of
`box/acceptance.py`. The commit that adds this file is the pre-registration timestamp, and gate 16b stamps the frozen SHA
below. Nothing below changes after a score is seen. A change needs Michael, and a later commit that says why.

**What has been read before this file (disclosed).** Step 16a (`docs/box/cohort-review-2026-10-22/`) read the PRODUCTION
selection of run 10 against local wells' actual year-1 (no variant, no tuning outcome). The first BS1_S pass (2026-10-22,
scratch, reported to Michael) also read the RECORD variant's existing tuning + holdout views by radius reached (BS1_S oil-12
−30 % at 5–7.5 mi, −12 % at 20 mi; other benches likewise) and ran a six-rule counterfactual on BS1_S production PUDs (EUR only,
no outcome). No tuning or holdout outcome has been computed for any variant named here.

## 0. Kickoff (Michael 2026-10-22)

1. **D118** — diagnose every bench; selection-rule changes go to the provisional groups first; validated groups only on evidence
   with their own re-acceptance; short-history wells: TEST the level-only middle path, not adopt.
2. **D119 (gate 16a)** — the spacing fix applies on ALL benches, validated included; the validated groups' TUNING cells are
   re-scored with it.
3. The D52 holdouts are not scored again: validated groups' were scored once (D59 / D100 / step 15); provisional groups' failed
   (BS3_S, BS3_C, WCB_2, BS1_S) or never existed (AVA_0 / 1 / 2, BS2_C). Step 16 scores TUNING packages only (`run` refuses
   `step16` with `score_holdout`), then confirms prospectively.

## 1. Candidate priority order (Michael ranks at gate 16b)

Highest first: **same bench > distance > lateral similarity > spacing representativeness > count.** It becomes the ladder of
`box_v2s_r1`: at every ring, while it holds fewer than 10 eligible wells, give up the LOWEST-priority rule first, cumulatively,
before the radius grows — count (accept ≥ 5), then spacing (admit standalone), then lateral (± 40 % band + Cui translation). Same
bench is never relaxed. A different order from Michael changes only `box_v2s_r1`'s `relax` tuple (and `box_v2s_r1lo`'s).

## 2. Variants (`box/step16.VARIANTS`; every variant gets its own F(k), as the harness calibrates every variant)

| variant | pool spacing | rules | role |
|---|---|---|---|
| `box_v2` / `box_v2_wf` | training cohort only (the record) | record | the record variant of each group, re-scored on the same run for a same-data comparison |
| `box_v2s` | **measured, every pool well** (D119) | record | the new base, every group |
| `box_v2s_wf` | measured | record, × walk-forward haircut (D57) | the new base for the groups whose record carries a haircut (WCA, BS2_S) |
| `box_v2s_lat` | measured | relax = (lateral) | attribution only, never adopted |
| `box_v2s_lo` | measured | level-only | attribution only, never adopted |
| `box_v2s_r1` | measured | relax = (count, spacing, lateral) | adoption candidate (provisional groups) |
| `box_v2s_r1lo` | measured | r1 + level-only | adoption candidate (provisional groups) |

Rule details (`box/analog.Rules`, defaults pinned by tests to reproduce the record selection; verified on all 50,963 run-10
PUDs, 0 differences):
- **Measured spacing** = `curated.wells_enriched.lateral_closer_xy_ft` for every pool well; NULL stays NULL (standalone, as
  deal-intake reads it); ≥ 2,800 ft = the Novi no-neighbour sentinel (standalone).
- **count** — the ring is accepted at ≥ `count_floor` = **5** eligible wells (flag `relaxed: count (n < 10)`).
- **spacing** — standalone wells are admitted; tight wells (< 0.65 × planned spacing) stay out.
- **lateral** — completed laterals ≥ 7,500 ft: band ± `wide_tol` = **40 %** (the existing long-lateral tolerance) and the
  cohort is translated to the location's lateral by Cui & Cross (D50, as the short-lateral path); shorter laterals keep the
  7,500–12,500 ft band (already translated).
- **level-only** — a well under the 6-month floor is admitted when its oil peak is ≥ **3 calendar months** behind it (onset +
  peak index); its own qi and the cohort's long-well (≥ 9 months after peak) median Di / b (the D57 short-history transfer).
  Counted toward the cohort size, flagged `level_only: k`. If a cohort holds no long well, the short well keeps its own fit —
  flagged by the existing transfer path, reported.

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
holdout merge cannot be reproduced without a second holdout look). Michael confirms at gate 16b.

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
- the **level-only hindcast** (§6).

A candidate (`box_v2s_r1`, `box_v2s_r1lo`) passes against `box_v2s` when ALL hold: (1) it fails no more judged cells;
(2) its median |pooled package bias| over judged cells is ≤ the base's + 1 point; (3) its far-with-local |bias| ≤ the base's;
(4) its off-local share ≤ the base's; (5) a level-only candidate also has |hindcast bias| ≤ 15 %. Any NaN fails its check.
Among passing candidates the lower median |bias| wins; a tie goes to the one without level-only. **None passing → `box_v2s` is
the provisional record** (the spacing fix alone). Validated groups' r1 / r1lo numbers are reported, never adopted (D118, 16e).

## 6. Level-only hindcast (the D118 middle-path test)

At each tuning cutoff, every pool well with 3–5 calendar months after its oil peak (and ≥ 9-month long wells in its own
`box_v2s_r1` cohort as donors): predict its NEXT 12 months of oil from its own qi and the donors' median Di / b
(`members_with_transfer`), and compare with actual. Pooled bias = Σ actual / Σ predicted − 1 over all provisional groups.
For reference, the 2026-09-21 deal-intake hindcast at 9 months after peak was +6 to +11 % (forecast high). The code lands in 16c
BEFORE this hindcast runs and is checked against this paragraph; its definition here does not change.

## 7. Reported, never judged

Attribution variants; median |package error| and share > 25 % off (`step16.abs_error_stats`) for every variant; per-cutoff
cells; per group; radius-class distribution per variant; the PUD-level EUR change per variant on run 10's production universe;
the BS1_S curve-construction offset (the record P50's month 1–12 vs its own cohort's actual cum-12, +13 to +16 % on BS1_S),
diagnosed on every group.

## 8. Open for gate 16b (Michael)

1. The priority order of §1 (it sets `box_v2s_r1`).
2. `count_floor` 5 and `wide_tol` 40 %.
3. The WCA / BS2_S haircut source (§4: `box_v2s` tuning cells only).
4. The validated keep-rule of §4 and the one-variant-for-all-provisional rule of §5.

Frozen SHA (stamped at gate 16b): _pending_.
