# Step 13d — 2026 prospective test of the run-19 method, all 13 groups (PRE-REGISTRATION, 2026-10-25)

**Status: FROZEN 2026-10-25 at gate 13d (D125), as written.** The definition did not change at the gate, so the pinned digest stands; the merge of this file's PR is the freeze. Nothing is scored. No 2026 well's production volume has been read; the
only 2026 facts used are well identities, tags, first-production dates and states (`cohort_at_freeze.csv`).

- Definition of record: `box/prospective16.py` `DEFINITION`, SHA-256 `6bc67994…` pinned in `DIGEST`; `tests/test_box_prospective16.py`
  fails on any edit.
- Commands: `python -m scripts.box_prospective16 status | snapshot | score` (`score` refuses until it is built; §7).
- Decisions: D124 (step 13 approved), D105 (tiers), D99 (consistency rule), D121 / D122 (run-19 method).

## 1. Why this test

- **It is the only way a group changes tier (D124).** Every holdout is spent. Under D121 even the validated groups carry
  tuning-only evidence. Re-testing on data we have already seen is not validation.
- **D85 stays.** D85 (`box/prospective.py`, frozen 2026-10-15) covers WCA only, on the run-4 method that is no longer delivered.
  It is scored alongside, for information only, and never decides a tier.

## 2. The cohort

**Definition:**
- Delaware wells first producing 2026-01-01 … 2026-12-31.
- Real lateral.
- Lateral midpoint inside the group's record extent (the run-19 extents).

**Freeze snapshot** (first production Jan–Aug 2026 so far; warehouse production through 2026-10-01):

| group | tier at freeze | extent | wells now |
|---|---|---|---|
| WCA (WCA_1 + WCA_2) | validated | 6 | 343 |
| WCXY_WCA1 (WCXY targets) | validated | 6 | 60 |
| BS2_S | validated | 7 | 353 |
| WCB_1 | validated | 22 | 70 |
| WCC | validated | 27 | 80 |
| AVA_0 | provisional | 28 | 13 |
| AVA_1 | provisional | 29 | 45 |
| AVA_2 | provisional | 30 | 38 |
| BS1_S | provisional | 26 | 145 |
| BS2_C | provisional | 20 | 96 |
| BS3_C | provisional | 18 | 216 |
| BS3_S | provisional | 16 | 163 |
| WCB_2 | provisional | 24 | 93 |
| **total** | | | **1,715** (validated 906, provisional 809) |

The cohort keeps growing through December. A cell is judged on **packages**, and a group has at most as many packages as wells.

## 3. Which tags govern (the 13d rule, D124)

- **The verdict uses the tags current at SCORING time:** `curated.formation_blueox` then, with its 13e tag-release id stamped
  on the score. This applies to both sides of the test:
  - which group each 2026 well tests;
  - the analog pools the hindcast forecasts it from.
- **The freeze-time tags are a sensitivity, never the verdict:** this file's snapshot, and the pools as frozen in run 19.
- **A release that merges or splits groups** (e.g. rule A: WCXY + WCA_1 + WCA_2 as one bench) changes the test's units. The
  affected groups are re-defined by an amendment committed BEFORE any score is read, never after.

## 4. The method (run 19, exactly)

- **Fold:** the next rolling-origin fold of the 16c harness at cutoff **2025-12-01**. Analogs, fits, F(k) and the proximity
  configuration all come from data before the cutoff.
- **Selection:** r2 (`box_v2s_r2`, D121), `Rules(relax=('count','spacing'), count_floor=5, lateral='translate',
  translate_range=(5000, 15000))`. Measured spacing (D119); Cui & Cross translation.
- **Proximity:** the D113 oil factor (`box.prox_pud.decide`, tables `prox-2026-10-19`, digests pinned). A multi-parent well
  without precedent gets no forecast (D114). It is excluded from the verdict and counted.
- **Haircut:** walk-forward on WCA oil and BS2_S oil + gas only (gas on WCA none, D122). The factors come from
  `r2_evidence.json` (LF digest `90da3c56…`).
- **Volumes:** uptime-free (D63).
- **Code:** main `06fe42c`.
- **Grain:** D53 development packages (co-developed within 180 d, overlap ≥ 30 %). Error = Σ actual ÷ Σ forecast − 1
  (negative = forecast HIGH).

## 5. Verdict, tier consequence and schedule

**Cell rule (D99 consistency, as BS2_S, WCXY and the step-15 groups earned their tier).** A cell passes when the cohort's
package bias lies inside **P2.5–P97.5 of the group's own tuning package bias drawn at the cohort's size**:
- 2,000 draws of 3-mi blocks (the D52 holdout shape), block share = cohort packages ÷ tuning packages, seed 20261025;
- drawn from the 16c tuning packages pooled over cutoffs 2019–2024, under the production treatment (r2 + proximity, plus the
  haircut where run 19 has one);
- the tuning views are pinned in `tuning_views.sha256` (78 files).

**Cells:** oil and gas × cum-12 and cum-24. A cell needs ≥ 30 packages to be judged.

| group result | condition | tier consequence |
|---|---|---|
| PASS | every judged cell passes, and at least one oil cell is judged | provisional → proposed for validated at its own gate |
| FAIL | any judged cell fails | validated → provisional (D105); diagnose, never re-tune |
| NOT JUDGED | no oil cell reaches 30 packages | tier unchanged |

**Reported, never gating:**
- |package bias| ≤ 10 % per cell (D53 accuracy);
- scale-free spread vs the benchmark (D58);
- the thin-control line (< 3 local wells within 3 mi; the step-17a check);
- NM vs TX;
- the freeze-time-tag sensitivity;
- the no-precedent count.

**Schedule: one judgment per horizon, on a date fixed now.** This rules out stopping early when a read looks good.

| read | when | status |
|---|---|---|
| cum-6 | wells with ≥ 7 reported months, any time | reported, never judged |
| cum-12 on wells first producing Jan–Jun 2026 | production through 2027-08-01 (~2027-Q3) | reported, never judged |
| **cum-12, full cohort** | the first build with production through ≥ **2028-01-01** (~2028-Q1) | **judged once** |
| **cum-24, full cohort** | the first build with production through ≥ **2029-01-01** | **judged once** |

**Watch items** (reported):
- **The 2022–23 vintage episode:** provisional cutoff bias was −10 / −11 %. Does 2026 read like 2023–24, within ~2 %?
- **WCA gas:** the newest cohort trends high (D122).
- **WCC and BS2_S cum-24:** disclosed at −17 % and −10 %.

## 6. What this forbids

- No edit to `DEFINITION` after the freeze. The digest test fails. The tag-rule amendments of §3 are the only sanctioned path,
  and they are written before a score.
- No re-tune, no redrawn interval, no moved judgment date. A FAIL means diagnose.
- **A step-17 correction does not change this test.** It scores the run-19 method as frozen. A corrected method needs its own
  prospective cohort (2027).

## 7. The scorer (built later, before it is run)

`score` is not built: the first judged read is about 2028-Q1. When it is built:
1. Commit it before its run (the 16c pattern).
2. Check it on a past cutoff first: the 2024-12-01 fold must reproduce the 16c tuning cells for every group.
3. Then run it once at 2025-12-01 on the judgment date.

**Early reads** use the same scorer and are labelled "not judged".

## 8. Gate 13d — the calls (DECIDED 2026-10-25, Michael; D125)

1. **Verdict rule.** Proposed: D99 consistency. It tests "the disclosed bias is honest", which is how every current validated
   group earned its tier.
   - Consequence: a provisional group that is consistently 14 % high (BS3_C) would be promoted as "validated, −14 %".
   - The alternative adds |bias| ≤ 10 % as a promotion condition.
   - Recommendation: D99, with the size of the bias handled by step 17, not by the tier.
2. **Judgment date.** Proposed: the full cohort at about 2028-Q1, with an H1-2026 cum-12 read reported at about 2027-Q3.
   - The alternative judges the H1 wells at about 2027-Q3: half a year sooner, but on fewer packages, so the thin groups
     are unlikely to be judged.
3. **Thin groups.** AVA_0 (13 wells so far) will almost surely be NOT JUDGED, and AVA_1, AVA_2 and WCXY_WCA1 are borderline.
   Accept "tier unchanged", or leave the door open to pool them with a 2027 cohort under a later pre-registration?
4. **Durability.** The 78 tuning views (29 MB) live only in `runs/step16c` on this laptop and are pinned by hash.
   Recommendation: copy them to the OneDrive share now. Without them the intervals cannot be drawn in 2028.

**Answers (Michael, gate 13d):** "verdict = D99 consistency alone; full-cohort judgment ~2028-Q1 with the H1 read reported; thin
groups stay tier unchanged; I'll copy the 78 views to OneDrive. Freeze as written."
1. Verdict = **D99 consistency alone**. |bias| <= 10 % stays reported, never gating; the size of the bias is step 17's.
2. Judgment = **the full cohort, once, with production through >= 2028-01-01**. The H1-2026 cum-12 read (~2027-Q3) is reported, not judged.
3. Thin groups that do not reach 30 packages are **NOT JUDGED, tier unchanged**. No pooled 2027 cohort is pre-committed.
4. Michael copies the 78 tuning views (`runs/step16c`, hashes in `tuning_views.sha256`) to the OneDrive share.
