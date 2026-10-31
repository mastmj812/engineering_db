# BOX step 21a — Midland tuning + holdout: PRE-REGISTRATION (written and committed before any Midland BOX forecast is scored)

Written 2026-10-31. Phase 3 transfers the run-19 method of record (D134); this file states how the nine Midland groups are scored
in 21b (tuning folds) and 21c (one-time holdout), and what moves a group between tiers. The record is
**`box/step21.DEFINITION`** (digest-pinned by `tests/test_box_step21.py`); this text explains it. The commit that adds both is the
pre-registration timestamp; gate 21a stamps the frozen SHA in §11. Nothing below changes after a score is seen. A change needs
Michael and a later commit that says why (the revision table).

**Code this names.** Frozen at the SHA (it produces every forecast): `box/analog.py` (selection, `Rules`), `box/lateral.py` (Cui),
`box/acceptance.py` (folds, packages, the `--step16` path, which predicts `mid_r2` for a `MID_` group), `box/step16.py`,
`box/step21.py`, `box/prox_*` (pair metric, configuration, precedent, `decide`), `box/holdout.py`, `box/rehearse9b.py`,
`dealintake/`. Written in 21b / 21c AFTER the freeze and checked against §4–§7 as written here before it runs (the 16c pattern):
the Midland proximity factor fit, the treatment scorer (`mid_r2p`, `mid_r2p_wf`), the D99 interval draw, the 21c holdout judge,
the water scorer wiring. A 21b / 21c run whose `box/`, `scripts/` or `dealintake/` frozen files differ from the SHA is not a score.

**What has been read before this file (disclosed).**
- Step 18: Novi 2025Q3 Midland per-ft bias and per-bench medians over all modern producers (no BOX forecast).
- Steps 20a / 20b: production summaries over all wells (oil / 1,000 ft by region, sharing vs non-sharing) for the extents and
  the cards (no BOX forecast).
- This step (`index.html`, `FINDINGS.md`): package COUNTS (no forecast, no error, for tuning or holdout), analog and measured-water
  reach from the undrilled sticks, the in-extent sticks' proximity configuration and outcomes (precedent and geometry only), and
  the observed per-ft-vs-length ratio on producers in TUNING blocks only (the D52 holdout blocks unread).
- No Midland BOX forecast exists. No Midland tuning or holdout outcome has been computed for any treatment named here.

## Revisions (before any score)

| date | change | why |
|---|---|---|
| 2026-10-31 (this commit) | first registration | — |

## 0. Transferred as decided (D134: the Delaware method, not re-derived)

- Selection of record r2 (D121), measured spacing for every pool well (D119), Cui & Cross translation of every cohort (D50 / D120),
  uptime-free volumes (D63), per-variant F(k) (D58), the D57 short-history transfer.
- Midland terminal Df 0.06 /yr (D132); one record run per basin (D130); group keys `MID_<bench>`, basin `midland` (D135).
- Groups: one extent and one pool per bench, no pooling (D128); WCD and WCC build to a provisional target, DEAN tier from step 21's
  counts, US emerging (D127 / D131); validated where data allow (D131).
- Acceptance: D53 package grain + folds, D58 scale-free spread, D52 holdout as frozen, D99 consistency holdout; D105 provisional
  tier; validation does not transfer across basins (D134 E).
- Proximity: D112 pair metric and envelopes, D113 option (a), D114 two-tier precedent, D115 no shielding exemption, D116 derived
  record (re-measured per run).
- Water: D107 ratio on raw oil (D108), D109 scoring, folded into step 21 (D133 / D134 D).
- Long laterals: D129 as amended by **D134 C** — ONE variant, > 15,000-ft producers in the pool, classes reported, not judged.

## 1. Groups and pools (`box/step21.GROUPS`, `box/acceptance.BENCH_SPECS["MID_*"]`)

| group | bench | record extent | pool file (copy of the set of record) | rows |
|---|---|---|---|---|
| MID_WCA_1 | WCA_1 | 36 | `step20a-2026-10-26/r3/wells_final_WCA_1.csv` | 7,575 |
| MID_WCB_1 | WCB_1 | 37 | `…/r3/wells_final_WCB_1.csv` (D136 + ask-3 verdicts) | 6,646 |
| MID_WCB_2 | WCB_2 | 38 | `…/r3/wells_final_WCB_2.csv` | 2,157 |
| MID_WCC | WCC | 39 | `…/r3/wells_final_WCC.csv` | 614 |
| MID_WCD | WCD | 42 | `…/r3/wells_final_WCD.csv` | 996 |
| MID_MS | MS | 44 | `step20b-2026-10-30/wells_final_MS.csv` | 1,681 |
| MID_JM | JM | 45 | `…/wells_final_JM.csv` (LSSH → JM accepted, D142) | 1,702 |
| MID_LSSH | LSSH | 47 | `…/wells_final_LSSH.csv` | 5,680 |
| MID_DEAN | DEAN | 49 | `…/wells_final_DEAN.csv` | 929 |

Frozen as `docs/box/pool-midland-2026-10-31/wells_final_<bench>.csv` with `MANIFEST.json` (sha256 of each file, LF-normalised,
and the commit of its source); a test holds the copies and the sources to the manifest. Membership = `box_bench` (BOX-only
reassignments: the D136 WCB line, card verdicts, owner benches), so no tag filter; `exclusions.csv` applies in the harness. No
api10 sits in two groups. Out of scope: US (D127), BRNT / MISS / MRMC / WDFD (D2) — not covered, never zero.

## 2. Method (`box/step21.RULES`; one variant)

`Rules(relax=('count', 'spacing'), count_floor=5, wide_tol=0.4, lateral='translate', translate_range=(5000.0, inf), …)` = run 19's
r2 rules with **no upper bound on the analog's completed lateral** (D129 / D134 C). The 5,000-ft floor stays. Every cohort's
per-1,000-ft P50 is scaled to the location's completed lateral by Cui & Cross 2,000 lb / 60 bbl per ft (`box/lateral.py`), the
last segment extended past 12,500 ft (flagged; §8 reports the share). The harness predicts it as **`mid_r2`** plus its
linear-per-ft twin `mid_r2_lin` (same cohort; §8 only).

## 3. Folds, grain, holdout

- Cutoffs 2019-12-01 … 2024-12-01; scored wells = the next 12 months' pool wells, lateral midpoint inside the record extent,
  lateral > 0 (`acceptance.run`, fold `analog`); horizons cum-12 / 24 / 36 / 48 (cum-48 reported, never judged).
- **Actuals pinned to production through 2026-08-01** (the live last full month at 21a; each well's newest month dropped).
- Package = co-developed co-extent group wells (first production within 180 d, overlap ≥ 30 %), connected components; error
  = Σ actual / Σ forecast − 1 (negative = forecast HIGH); ≥ 30 packages to judge a cell.
- D52 holdout as frozen (salt `box-holdout-2026-10-13`, 3-mi blocks, 20 %). Held-out packages are dropped before any statistic
  in 21b and only counted.

## 4. Treatments scored in 21b

| name | what | notes |
|---|---|---|
| `mid_r2` | the harness prediction under §2 | raw |
| `mid_r2p` | `mid_r2` × the Midland proximity oil factor | gas / water untouched (D113) |
| `mid_r2p_wf` | `mid_r2p` × the group's OWN walk-forward haircut | D57 / D94: mean package bias at the same horizon over ≥ 2 earlier judged tuning cutoffs, per stream |

**Proximity factor (gate question 1).** Form = D113 option (a): only multi-parent configurations get a factor, oil, cum-24, a
uniform scale. Ladder bench pair × count → class × count × flank → class × count → class, at the first rung with ≥ 30 children
(`box/prox_validate.fit`); factor = exp(mean l_rel) with l_rel = ln(actual / as-of `mid_r2`) minus the (group, cutoff) mean.
**Source = Midland TUNING children only, all six tuning cutoffs** — held-out packages never enter. The factor is applied to
every multi-parent scored well (precedent ignored, as in the step-16 level work), so the treatment's level is partly in-sample;
stated with every number. The Delaware D113 table on the same wells is reported as a sensitivity.

**Bench label for proximity classes (gate question 2).** BOX membership (`box_bench`) for a producer in a Midland set of record,
else its `formation_blueox` tag. The Delaware study read warehouse tags; on the Midland the BOX sets relabel 580 producers of the
proximity universe (the D136 WCB line is the largest share), and a parent's class should match the bench its forecast uses. The
warehouse-tag reading is reported as a sensitivity (`index.html` §5).

## 5. Record treatment and haircut per group

- **Rule (`box/step21.record_treatment`, the step-14 / D97 pattern):** `mid_r2p_wf` where the group's pooled holdout over the
  cutoffs that carry a walk-forward haircut reaches 30 packages at cum-12 AND cum-24; otherwise `mid_r2p` (no haircut). Applied
  to the 21b tuning run's SCORED counts (the harness drops wells with no prediction at early cutoffs — step-15 §2), before any
  holdout is read. The 21a expectation from raw counts is in `FINDINGS.md` §1.
- **Guard (D106, per stream):** a stream's haircut is refused when its cum-k factors reverse by > 0.01 or the median location's
  D92 g(48) leaves [0.6, 1.2]; that stream then carries none (the D122 representation, months exactly raw).
- **Tuning gate (21b):** Michael may move a group `mid_r2p_wf` → `mid_r2p` on tuning evidence (step-15 BS3_C / WCB_1), or to
  provisional (step-15 BS2_C). Never `mid_r2p` → `mid_r2p_wf`, never toward validated, never after a holdout look.
- **Holdout time:** walk-forward factors from TUNING cells only (D58). **Production (step 23):** D102 — tuning + holdout cells
  merged per cutoff, then the ≥ 30 floor; the D92 rate shape; the 9c guard.

## 6. One-time holdout (D99) and tiers

- **Cells:** per group, the horizons (12 / 24 / 36) whose pooled holdout cell under the record treatment reaches 30 packages;
  oil AND gas at each. A group with no such cell is provisional by construction and no holdout is scored for it.
- **Intervals:** P2.5–P97.5 of the pooled tuning package bias over 2,000 random 20 % draws of 3-mi blocks of the TUNING packages
  (`box/rehearse9b.consistency`, seed 5), drawn in 21b, frozen at gate 21b with a sha256, never redrawn. The pass rates of a
  forecast as good as tuning and of a ±15 % miss are reported per group with the intervals (the pre-9b / step-15 §6 read).
- **Pass:** every judged cell's holdout package bias inside its interval, ≥ 1 oil cell judged. The ±10 % bias test (D53), the
  scale-free spread test (D58) and per-cutoff cells are reported, never gating. A FAIL means diagnose (7a), never re-tune.
- **Tiers (D131 / D105):** validated = D99 PASS on the record treatment. Provisional = FAIL, no judgeable cell, or moved at the
  tuning gate: raw `mid_r2p`, no haircut, D105 disclosure (tuning + holdout lines where a holdout failed, never the pooled figure
  alone). `box.bench_scope.validation` is written per Midland bench at step 23 on go (today every Midland row reads the column
  default `validated`; nothing reads it until a Midland record run exists).

## 7. Water (D107 / D109, D133 / D134 D)

D107 `ratio` (ln WOR = a + b·Np) on the measured-water cohort's per-1,000-ft mean oil + water, applied to raw `mid_r2` oil (D108).
Measured = `curated.water_data_quality` `measured` (Texas: the sql/41 label stands) + seller VDR daily water ≥ 6 months
(`box/water11` as built). Selection = the oil first-ring rules on circles over the D54 ladder, then 30 / 40 / 50 mi to ≥ 10
measured analogs (reach recorded); 3–9 at 50 mi = thin; < 3 = vendor-calculated fallback, flagged. D109 cells: pooled group ×
horizon on measured-water packages; tuning |bias| ≤ 20 % AND scale-free band ≤ measured local-offsets benchmark + 0.10 (≥ 30
packages); holdout once, a cell with ≥ 10 packages consistent inside its frozen P2.5–P97.5 tuning interval. Validated water =
validated oil + every judged tuning cell passes + every judged holdout cell consistent; else provisional. Reach and the top
operator's share of the 10 nearest measured analogs are reported per group (D133).

## 8. Long laterals (reported in 21b, never judged — D134 C)

- The D120 condition-6 mismatch classes (well completed lateral / cohort mean: < 0.80 / 0.80–1.25 / ≥ 1.25), oil + gas, cum-12 /
  24 / 36, `mid_r2` vs `mid_r2_lin` from the same cohort, per group and pooled.
- Absolute completed-lateral classes 5,000 … ≥ 20,000 ft; the share of locations whose translation extrapolates past 12,500 ft
  and past 15,000 ft.
- Context (21a, tuning blocks only): the observed per-ft ratio by length class vs Cui (`index.html` §4). D129's reading: if the
  Midland curve is flatter than Cui, the translation reads LOW on long PUDs — disclosed, not corrected.

## 9. Reported, never judged

Thin-control wells (< 3 modern local wells within 3 mi at the cutoff), oil cum-12 / 24; edges within 5 mi of the extent by
compass side (step-15 §5); radius reached and the share of each cohort drawn from OUTSIDE the group's extent (20a: every MID_WCC
location); production-sharing vs non-sharing scored wells per group (20b §3); DEAN undrilled sticks by proximity outcome, generated
body vs loop addition (D143); the proximity sensitivities of §4; Novi 2025Q3 Midland per-ft bias as the exhibit.

## 10. Runs (21b)

```
python -m scripts.box_acceptance --fold analog --bench MID_<bench> --step16 --wells docs/box/pool-midland-2026-10-31 \
    --actuals-through 2026-08-01 --out runs/step21b/MID_<bench>
```

for the nine groups, at the frozen SHA, recorded per run (with the nightly checked first: never build across a running ETL, the
2026-10-26 trap). Then the 21b scorer: Midland proximity factor table (§4) → `mid_r2p` / `mid_r2p_wf` cells → record treatments
(§5) → D99 cells + intervals (§6) → water cells (§7) → the §8 / §9 reports. Gate 21b = the tuning view + frozen intervals.

## 11. Gate 21a

Questions for Michael (`FINDINGS.md` §5 has the evidence and a recommendation for each): (1) proximity factor source, (2) the
bench label, (3) the record-treatment rule as stated, (4) the actuals pin, (5) the lateral translation on the Midland (Cui as
D129 / D134 C decided, or the linear-per-ft twin as record — the 21a evidence shows Midland per-ft oil flat within ~2 % to
17,500 ft). Any answer that changes this file or `DEFINITION` lands as a revision row, and the digest is re-stamped in the same
commit.

**Definition digest (as registered):** `3299259e86d157aeeb157d8b2d66393585a40e889f42e1a4fb7b46fad0af59de`.
**Frozen SHA:** _stamped at the gate_.
