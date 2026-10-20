# Step 2c — walk-forward validation of the configuration haircut (PRE-REGISTERED)

Written 2026-10-20 and committed BEFORE any score is computed. Scored once by
`python -m scripts.box_prox_study validate`. The rule below is not changed after scoring.

## Why
Michael (2026-10-20) switched the design: PUDs get BOX × a configuration haircut and Steven's econ does the
culling. Configurations with no drilled precedent get no forecast. A haircut that becomes a forecast term must
predict out of sample, so this step validates it the way BOX validates itself.

## What is validated
- **Data:** the step-2 frame. That is the harness's per-well `box_v2` views (tuning + holdout), 14,545 Delaware children, joined to the step-2b configuration (`box.prox_dose.configuration`).
- **Relative log-ratio of a child:** `l_rel = ln(actual / as-of box_v2) − mean of the same over ALL scored children of its (bench group, cutoff)`. If that cell has fewer than 10 children, fall back to the bench group, then to all children.
  - This takes BOX's own fold-level bias out of the test.
  - That bias is the walk-forward haircut's job, already validated (D58/D99).
  - **What is validated here is the RELATIVE haircut**, which is what gets multiplied onto a calibrated BOX forecast.

**Configuration key ladder** (most specific first; a rung is used when it has ≥ 30 TRAINING children with the metric):

| rung | key |
|---|---|
| 1 | bench pair × parent count: `pool(child bench) > class > pool(nearest parent bench) \| 1/2/3+` |
| 2 | class × parent count × flank: `class \| 2 or 3+ \| F (flanked) or S (one side)`; `class \| 1 \| -` for one parent |
| 3 | class × parent count: `class \| 1/2/3+` |
| 4 | class: `topfill`, `same`, `underfill` |

- Children with parents in 2+ classes use `mixed | 2/3/4+` (by total parent count) at rungs 2–3 and `mixed` at rung 4.
- Children with no qualifying parent in any class envelope use `none`. That gets its own factor; on BOX's mix scale it is expected above 1.

**Factor:** `f(key) = exp(mean l_rel)` over the training children carrying the key.

**Walk-forward:** test fold c = the children of harness cutoff c. Training = all children of strictly earlier cutoffs (both splits).

| horizon | test cutoffs |
|---|---|
| oil cum-24 (primary) | 2021-12, 2022-12, 2023-12 |
| oil cum-12 | 2021–2024 |
| oil cum-36 | 2021, 2022 |
| gas cum-24 | 2021–2023 |

**Residual of a test child:** `r = l_rel − ln f(assigned key)`. Without a haircut: `r0 = l_rel` (factor 1).

## Pass rule (oil cum-24, test folds pooled; 90 % 3-mi block-bootstrap, 1,000 draws, seed 20261020)
- **P1 — calibration where it matters.** Take the test children assigned f ≤ 0.90 (the "material" haircuts). PASS if `exp(mean r)` lies in [0.95, 1.05], OR its 90 % interval contains 1.00.
- **P2 — skill.** Take the assigned-key cells with ≥ 30 test children. PASS if the n-weighted RMS of the cell mean of r is below the same RMS for r0.
- **P3 — cell calibration.** PASS if ≥ 80 % of the cells in P2 have `|exp(mean r) − 1| ≤ 0.10`.

**VERDICT = P1 AND P2 AND P3.** cum-12, cum-36 and gas are reported but never gate.

## Disclosed before scoring
- **The configuration definitions were chosen after seeing in-sample results over ALL folds** (steps 2 and 2b): the envelopes, the 1/2/3+ bins and flanking. So this split is walk-forward in TIME but not blind in DESIGN. Only the 2026 prospective cohort is fully blind.
- **The spatial holdout blocks (D52) were already used in steps 2/2b.** They are not used as a separate test here.
- **Survivorship:** every child is an operator-selected well. A validated haircut predicts drilled-well outcomes; for undrilled PUDs it remains an upper bound.
- **Defaults taken with Michael's "yes" (2026-10-20):**
  - mean haircut, not a conservative bound, with survivorship disclosed;
  - cum-24 primary;
  - the `none` factor included;
  - the precedent unit (parent configuration vs package) is decided at gate 2c.
