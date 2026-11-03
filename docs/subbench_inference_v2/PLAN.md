# Sub-bench inference v2 — getting the coarse Novi stick tags right

Status: **step 1 DONE — rule frozen at f138eb0, scored ALL PASS; at gate 1**. Nothing here is applied to the warehouse. Owner: Michael. Opened 2026-11-03.

## 1. Problem

Novi Intelligence tags some sticks with a coarse parent — Delaware `Wolfcamp A`, `Wolfcamp B`, `Avalon`; Midland
`Wolfcamp B` — where our `formation_blueox` splits the parent (WCA_1/2, WCB_1/2, AVA_0/1/2). `sql/19` tier 2 infers
the sub-bench: take the 12 horizontally nearest same-parent laterals from `curated.bench_reference` (`sql/18`) and
copy the bench of the one nearest in landing TVD.

Measured 2026-11-03 (read-only, prototype):

* **The reference pool holds permits.** Delaware WCB: 1,564 of 4,695 laterals never produced, 648 carry round-100
  TVDs. Permits decided Pad 3240's picks (Rawhide State 404H, Cape Buffalo F 1304H).
* **k = 1 is fragile on sticks.** Dropping permits flips ~19 % of Delaware WCA/WCB picks and 2.6 % of Midland WCB;
  switching midpoint for lateral distance alone flips ~11 %. Leave-one-out on producers (~88 %) flatters it — a
  producer has a pad-mate at its own depth next door; a stick usually doesn't. Held out at a stick-like distance
  (1.66 mi) it scored Delaware WCB 77 %, Delaware WCA 62 %.
* **A frontier exists.** 54 % of Delaware WCA and 32 % of Delaware WCB coarse sticks have fewer than 4 same-parent
  producers within 5 mi; today they get a bench from wells however far away. None are in `box_scout_locations`.
* **Lea/Eddy:** 1,628 WCB sticks sit *above* the local WCA producers — the NM WCA/WCB producer tags are suspect
  (rule 15, planned surveys). That is a producer-tag question for the override path, out of scope here (§5).

Pad 3240 itself was a false alarm (gunbarrel lasso mixed Pad 3240, ~260 ft below WCA, with the southern 5k pads,
~170 ft below — one bench, dip).

## 2. Draft rule (FROZEN at the freeze commit; constants = `scripts/subbench_whatif.RULE`)

### 2.1 Reference pool
`curated.bench_reference` restricted to **producers**: `first_production_date IS NOT NULL` and TVD not a multiple of
100 (permit-round). Distances are true lateral-to-lateral distance in EPSG:3083 metres (not degrees, not midpoints).

### 2.2 Assignment, per coarse stick (same basin + parent)
1. **Frontier** — fewer than **4** same-parent producers within **5 mi** → weighted vote (2.2.3), path `frontier`.
2. **Local two-bench model** (Delaware WCA and WCB only) — the **30** nearest producers within **5 mi**, Gaussian
   distance weight (bandwidth **1.5 mi**). Needs both benches with **≥ 2** wells and the lower bench's weighted mean
   TVD **≥ 40 ft** below the upper's; otherwise fall through to the vote. Bench means = weighted mean TVD per bench;
   σ = pooled weighted residual scatter (floor **25 ft**); posterior of the stick's TVD against the two means, equal
   priors. Bench = the more probable; confidence = its posterior. Path `local_model`.
3. **Weighted vote** (Delaware Avalon, Midland WCB, and fall-through) — the **12** nearest producers; weight =
   Gaussian(TVD gap, σ **60 ft**) × Gaussian(distance, σ **1.5 mi**); bench = largest weight; confidence = its share.
   Path `vote`.

Why the split: in the prototype the local model beat the vote in the Delaware Wolfcamp (held-out WCB 85 vs 77 %,
WCA 77 vs 66 %) but not in the Midland WCB (87.6 vs 85.8 % on producers, worse on sticks) or on the three thin Avalon
benches. A dip plane (tvd ~ a + bx + cy + δ) added nothing in the Delaware and extrapolated badly at sticks off the
edge of their control; it is not in the rule.

### 2.3 Output (what `sql/19` would carry)
`formation_blueox` (the bench), `formation_blueox_confidence` (0.5–1.0), and the path (`local_model` / `vote` /
`frontier`) in `formation_blueox_source` or a new column (decided at step 2). Confidence bands for reporting:
**< 0.80**, **0.80–0.95**, **≥ 0.95**. Confidence is a flag only (§5 Q1): it is displayed, never acted on.

## 3. Acceptance criteria (FROZEN at the freeze commit, scored once after it)

Truth for producers = their live `formation_blueox` (Enverus interval + overrides) — itself noisy, so these are
relative tests. Hold-out radius = median true distance from a coarse stick to its nearest same-parent producer,
measured at scoring time; every producer within it (and the producer itself) is hidden from its own query.

| # | Test | Groups | Pass |
|---|---|---|---|
| C1 | Held-out producer accuracy, draft vs the current rule (re-implemented on the full pool, true distance) | Delaware WCA, Delaware WCB, Midland WCB | draft ≥ current, every group |
| C2 | Texas WCB sticks (Lea/Eddy excluded, `wca_delta_ft` known): agreement with "≥ 400 ft below local WCA = WCB_2" | Delaware WCB, Midland WCB | draft ≥ live tags, every group |
| C3 | Calibration on held-out producers: accuracy rises across the bands < 0.80 → 0.80–0.95 → ≥ 0.95 | Delaware WCB, Midland WCB | strictly increasing |
| C4 | Pad 3240's four WCB sticks | — | all WCB_1 |

Reported, not gated: Delaware WCA calibration (WCA_1/WCA_2 are ~132 ft apart — expect weak confidence), Avalon
held-out accuracy (no coarse Avalon sticks in 2026Q3), flips by path, flips in `box_scout_locations`, frontier size,
the review-sized count (confidence < 0.80, non-frontier), and how often the re-implemented current rule reproduces the
live tag (it uses degree distance in SQL; ours uses metres).

A failed criterion is reported as a fail. No re-tuning after the score without a written, numbered revision here.

## 4. Sequence after step 1

* **Step 2 — warehouse (after Steven prices the step-23 Midland + Delaware records; explicit go).** New `sql/NN`
  revisions of `sql/18` (producer pool) + `sql/19` (the rule in SQL: lateral aggregate over the KNN neighbourhood) via
  the `warehouse-change` skill. Snapshot `intel_formation_blueox` first. Applied off-hours in the quarterly-reload
  cascade order (`sql/19` → reconciliation `sql/68` → … → `erebor_locations` last → `sql/26`). Verify live: row-count
  identity, the tag diff equals the frozen what-if (SQL port parity with `scripts/subbench_whatif`), Pad 3240 WCB_1.
* **Step 3 — re-sync.** Reconciliation status changes (same-`formation_blueox` matching) → report the count;
  erebor / `box_scout_locations` tags move; the priced BOX record keeps its stored benches until the next BOX run
  (suggest riding 13c on the next vintage rather than an extra pricing cycle — decided at that gate); narvi scenarios
  and deal-intake runs keep benches until re-saved — list the live ones.
* The next Novi quarterly reload rebuilds `sql/19`; the v2 rule must be in the repo before it.

## 5. Open questions (Michael)

1. ~~**What low confidence does**~~ — **DECIDED 2026-11-03: flag only.** Confidence and path are carried on the
   stick and shown; they change nothing downstream (no BOX tier change, no exclusion, no review queue).
2. ~~**Frontier sticks**~~ — **DECIDED 2026-11-03: vote + flag** (the frozen draft, §2.2 step 1). The geologist's
   structure grids are not used for frontier sticks.
3. **Lea/Eddy producer tags** — investigate in parallel through the override path (not this rule).

## 6. Record

| Date | Event |
|---|---|
| 2026-11-03 | Prototype + draft (this document §1–§3); rule and criteria frozen at `f138eb0`; scored once → `score-2026-11-03/` |
| 2026-11-03 | **Score at f138eb0: ALL PASS (C1–C4).** Held-out producers (hold-out radius 0.74 mi, true lateral distance): Delaware WCA 74.5 vs 65.2 %, Delaware WCB 84.2 vs 78.7 %, Midland WCB 88.5 vs 85.5 %. Texas WCB vs depth below WCA: Delaware 77.1 vs live 70.3 %, Midland 84.3 vs 82.8 %. Calibration Delaware WCB 71.9 / 89.4 / 93.3 %, Midland WCB 66.7 / 87.5 / 95.9 %. Pad 3240 all WCB_1. Ungated: Delaware WCA calibration 69.8 / 85.0 / 84.7 % (flat above 0.80 — WCA_1/WCA_2 too close for the top band to mean more); Avalon 77.3 vs 75.0 %. Flips vs live: Delaware WCA 1,999, Delaware WCB 4,178 (1,145 in `box_scout_locations`; WCA 566), Midland WCB 1,181; frontier 3,152 / 4,474 / 1,932, none in `box_scout_locations`. Re-implemented current rule reproduces the live tag on 95.6 %. Gate 1 → Michael (§5 questions). |
| 2026-11-03 | §5 Q1 decided (Michael): low confidence = **flag only** — no BOX provisional marking, no exclusion, no review queue. |
| 2026-11-03 | §5 Q2 decided (Michael): frontier sticks = **vote + flag** as frozen; no structure-grid path. |
