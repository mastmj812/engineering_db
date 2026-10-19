# BOX step 11 — water: PRE-REGISTRATION (written and committed before any water forecast is scored)

Written 2026-10-19, before the tuning comparison (`scripts.box_water11 tune`) has run. Up to this commit, the only water numbers
read are the measured / calculated labels, the well counts and the location reach (part a). No water volume of a scored well
has been compared with any prediction. The commit that adds this file is the pre-registration timestamp. Nothing below changes
after a score is seen. A change needs Michael, and a later commit that says why.

## 0. Kickoff (Michael 2026-10-19), with the amendment made before scoring

1. Every location is forecast from MEASURED-water analogs. The search reaches past the D54 ladder when needed, and the reach is
   recorded. Only where no measured analogs are found does it fall back to vendor-calculated water, flagged. No location goes to
   a provisional water tier just for lack of measured analogs.
2. Measured = sql/41 `water_source = 'measured'`, plus seller VDR daily water where loaded (≥ 6 months with water > 0).
   `indeterminate` does not count. **Amended 2026-10-19 (Michael, before scoring): NM water counts as measured unless sql/41
   would call it `insufficient`; TX keeps the sql/41 label only.** NM C-115 water is reported, and sql/41's 0.05 CV floor marks
   steady real NM water as calculated (15 wells) or leaves it indeterminate (972).
3. Water is a low-reliability stream, so the tolerance is wider than oil's and is set here, before scoring.

## 1. Selection (`box/water11.py`)

- **Pool.** The group's own analog well set: the same file and tags as record run 10 (`water11.GROUP_WELLS`, BENCH_SPECS tags,
  `exclusions.csv`). For water the pool is not clipped to the extent: a reach past the extent is allowed and recorded.
- **Labels as of the cutoff.** In a tuning fold, an analog's label is recomputed on months reported through the fold's as-of
  month, so the fold never reads post-cutoff production. A scored well's own label uses all data through 2026-07-01 (its
  outcome side).
- **Rules.** box_v2's first-ring rules as written: deal-intake config v10 classify + tier-blind fill, completed laterals (D56),
  and the 7,500–12,500 ft band for short completed laterals. Circles only, no D55 ellipse.
- **Radius ladder.** D54 5 / 7.5 / 10 / 15 / 20 mi, then the **water extension 30 / 40 / 50 mi**. The search stops at the first
  radius with ≥ 10 eligible measured wells.
- **At 50 mi.**
  - ≥ 3 measured analogs: they are used, flagged `thin`.
  - Fewer than 3: **calculated fallback**. The same selection runs on the whole pool (any label) over the D54 ladder, flagged
    `calculated_fallback`.

## 2. Methods compared (step 11, TUNING packages only; D52 salt, blocks and share unchanged)

| method | water at the location |
|---|---|
| `ratio` (the lean) | boxfit ratio mode: ln WOR = α + β·Np, fitted on the measured cohort's aggregated per-1,000-ft MEAN oil + water, post oil peak (β bounded as in boxfit). It is applied month by month (midpoint Np per 1,000 ft) to the location's **BOX oil months**, i.e. the tuning run's raw box_v2 uptime-free months for every group. Cum-k is × F_oil(k). |
| `arps` | independent water Arps P50 of the measured cohort (water Di cap 12/yr nominal, D38) × completed lateral / 1,000. Cum-k is × F_oil(k). |
| `ratio_actual_oil` | **diagnostic only, never chosen.** The same WOR curve applied to the scored well's ACTUAL oil months. It measures the WOR's own skill with the oil error removed. |
| benchmark | D53 local offsets on measured wells: median per-1,000-ft water cum-k of the 15 nearest measured pool wells (first production ≥ 2016, before the cutoff) whose cum-k was known at the cutoff, × lateral. |

- F_oil(k) is the tuning fold's own oil calendar factor. The tuning runs calibrated no water factor, and downtime takes oil and
  water together.
- The scored oil is raw box_v2 for every group. ~~In production, water rides on the DELIVERED oil, which carries the D62 / D92
  haircut for WCA and BS2_S. Gate 12a reports that difference; it does not score it separately.~~
- **Amended at gate 11 (Michael 2026-10-19, after the tuning score; FINDINGS §3.4 / §8): in production the WOR rides on the
  RAW box_v2 oil months, exactly what was scored**, for every group. For 11 of 13 groups that is also the delivered oil. For
  WCA and BS2_S the delivered oil keeps its D62 / D102 haircut, but water does not inherit it: on the haircut oil BS2_S water
  would run +14 / +17 / +21 % low. This changes which oil production multiplies, not the scored spec, the tolerance or the
  12a rule.

## 3. Scoring grain and cell test

- **Package.** The D53 package of the group's tuning view, restricted to members whose own water is measured. A member counts
  at horizon k when its water cum-k is known (newest reported month dropped, as the oil actuals).
- **Package error.** Σ actual / Σ predicted − 1 (negative = forecast HIGH).
- **Cells.** One cell per **group × horizon (cum-12 / 24 / 36 water), POOLED across the six cutoffs** (D99: per-cutoff cells hold
  too few packages; per-cutoff and per-state numbers are reported, never judged). A cell is judged with ≥ 30 packages.
- **Water cell test (pre-registered tolerance).** |package bias| ≤ **20 %** AND scale-free band ≤ the measured benchmark's
  scale-free band + **0.10**.
  - Oil's figures are ±10 % and + 0.05. Water's are double, set before scoring. Reasons: per-well water varies more than oil;
    water is not an NPV driver of oil's order; Steven's use is LOE / disposal sizing.
  - Where the benchmark band is undefined, the spread half passes, as in `acceptance.judge_cell`.

## 4. Method choice (step 11)

- **One method for every group** (no per-group switching after the look).
- `ratio` is chosen **unless** `arps` passes strictly more judged cells (across all groups × horizons) AND has a lower median
  |bias| over the judged cells of both methods.
- `ratio_actual_oil` is reported and never chosen.

## 5. Frozen acceptance rule for gate 12a (applied in 12a under a frozen spec + code SHA, D58 pattern)

1. **Spec.** The method chosen in §4 + the §1 selection, code SHA frozen at gate 11.
2. **Tuning identity.** 12a re-scores the tuning view first. It must reproduce the step-11 tuning cells of the chosen method
   within 1e-9 on the same data; otherwise the code-identical + data-drift-explained guard applies (D98).
3. **Consistency intervals.** Computed in step 11 from TUNING packages only and frozen in `intervals_water.csv`, never redrawn
   after a look at the holdout. Each is the P2.5–P97.5 of the pooled package bias over 2,000 random 20 % draws of 3-mi blocks
   (seed 20261019, the rehearse9b method), per group × horizon.
4. **Holdout, scored ONCE.** Held-out measured-water packages, pooled per group × horizon.
   - A holdout cell with ≥ 10 packages is judged. It is CONSISTENT when its package bias lies inside its frozen interval.
   - The ±20 % and spread tests are reported per cell, not gating (D99).
5. **Water tier per group.**
   - **Validated** water requires all three:
     - (i) the group's oil is validated (`covered`);
     - (ii) every judged pooled TUNING cell passes the §3 water cell test;
     - (iii) every judged holdout cell is consistent, with at least one judged.
   - Otherwise water is **provisional**: the same forecast, disclosed D105-style (tuning, holdout and pooled bias, never the pooled
     figure alone).
   - Water never ranks above its group's oil tier. Provisional-oil groups carry provisional water, with water's measured bias
     disclosed.
6. **A failure** means diagnose (7a pattern), never re-tune. Water is never dropped and never zeroed (kickoff 1).
7. **Disclosure per workup.** Water method, measured-analog reach (radius + `thin` / `calculated_fallback` flags), the share of
   NM analogs for TX locations, and the tuning bias by horizon. Oil and gas forecasts are untouched by water (kickoff: Michael
   refines them separately).
