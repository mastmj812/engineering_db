# BOX step 5c — development-scenario factors (gate 5c summary)

Built 2026-10-11 on branch `claude/box-step5c-dev-factors`. Read-only against the warehouse. **Nothing stored**:
`box.risk_factor` DDL is step 5d (go-apply).

## 0. Re-run 2026-10-11 on the current 5b record (D37–D40, eng_db #115–#118)

The deliverable was regenerated after the 5b follow-ups:

- D37: ladder rung 3 retired.
- D38: water TC Di cap.
- D39: exact monthly volumes.
- D40: TC fits skip the downtime filter.
- Engine re-pinned to blueox-boxfit @ 3380317.

| Output | Result |
|---|---|
| Every factor table (record, pooled view, mean-ratio, selection ladder, shape, parent age, pooling, ladder) | **Bit-identical** to the #114 build |
| `wells.csv`, incl. the BS2_S per-well fits redone on the new engine | **Bit-identical** |
| `normalisation_WCA.csv` | Only `record_oil_eur_kft` / `ref_oil_eur_kft` move (the 5b TC re-fits: ≤ 1.5 %, median ref EUR 65,492 bbl/kft). The multipliers are unchanged (×0.946–1.025, median 0.993). |

Expected: 5c reads the per-well fits and calendar actuals, which D37–D40 did not change (D40 keeps the per-well
downtime filter). Only the TC area curves moved. **No number in §4–§7 changes.**

**Review surface:** `factors.html`. Open it directly, or serve it with `python -m http.server 8766 --directory docs/box` →
`/step5c-2026-10-11/factors.html`. The page has a forest plot per bench, the factor tables per stream, the
pooled-bench view, the selection-bias ladder, the shape, mean-ratio and parent-age checks, the per-bench vs
per-basin table, the proposed ladder, and the WCA area normalisation.

## 1. What exists

| File | What |
|---|---|
| `factors.html` | The review page. |
| `factors.csv` | Record view, in the shape of `box.risk_factor` (plan §4.2). Columns: basin, bench, stream, metric, dev_scenario, parent_bench, factor, 90 % CI, n_pairs, n_clusters. |
| `factors_pooled_view.csv` | Same model, but same-pool vertical parents (WCA_1↔WCA_2↔WCXY) are re-labelled as lateral infill (§5c below). |
| `selection_ladder.csv`, `shape.csv`, `factors_mean_ratio.csv`, `parent_age.csv` | Data behind the checks. |
| `pooling.csv` | Class-level factors, WCA vs BS2_S vs pooled, with the BS2_S/WCA ratio CI. |
| `ladder.csv` | The proposed factor of record per pair, with its rung stamped. |
| `normalisation_WCA.csv` | Per area: the scenario mix, and the multiplier from the record (mixed-cohort) curve to the reference curve. |
| `wells.csv` | Per well: class, nearest parent bench above/below, infill flag, parent ages, metrics. |
| `summary.json` | Run stamp and identities. |

Code: `box/dev_factor.py` (pure), `box/dev_factor_report.py`, `scripts/box_dev_factors.py`. The run takes about
14 min with 400 bootstrap draws, most of it the PPML bootstraps. Tests: `tests/test_box_dev_factor.py`, 14
DB-free tests (sql/50 replication cases, gate boundaries, shielding, recovery of known factors under location
selection for both estimators, ladder, normalisation).

## 2. Inputs

- **WCA:** the step-5b record. The strict D9 cohort is 7,527 wells (`members_WCA.csv`, area of record per well). The
  per-well fits come from `well_fits_WCA.csv` (the run refuses an installed blueox-boxfit SHA different from the 5b
  record's; re-run on @ 3380317, see §0). Actuals were re-cut from `curated.production` at the 5b as-of month (2026-07-01). The re-cut 12-mo oil
  matches 5b on 100 % of wells.
- **BS2_S:** the gate-1 final set minus `exclusions.csv` (19 wells). Kept: D9 cohort flag, lateral midpoint inside
  the BS2_S extent of record (extent 7), and 12 full months by 2026-07-01. That leaves **1,865 wells**, fitted
  here with the same engine and the same defaults as 5b. BS2_S has no TC areas, so location is controlled with
  5-mi block fixed effects. On WCA, swapping 5-mi blocks in for the areas moves the large-n factors by ≤ 4 %
  (selection ladder, "location robustness" row).
- **Scenario:** `curated.dev_scenario` (sql/50, the rule of record, D11). The class is recomputed from
  `bench_context` (`dfm.classify`) so that the nearest unshielded parent bench is known ("match on parent
  bench"). The recomputation equals the view's `scenario_class` and `has_same_bench_parent` on **all 9,391
  scored wells (0 mismatches)**. The run refuses on any mismatch.
- **Not used to estimate factors:** wells whose warehouse bench is outside the BOX pool (consensus-moved wells:
  101 WCA, 61 BS2_S). sql/50 computed their relations on their old bench. They are still normalised with their
  class's factor.

## 3. Method

ln(metric per 1,000 ft) = location FE + first-prod-year FE + β·(class, parent bench) + γ·infill. Then:

- **factor** = exp(β).
- **Reference** = `codev_stack` with no same-bench parent. It is the modal class: 72 % of the WCA cohort, 57 % of
  BS2_S.
- **Pairs** with fewer than 10 wells pool to `<class>|other`; sandwich always pools to `sandwich|all`.
- **infill** = `has_same_bench_parent`: an older same-bench well inside the co-extent rule, i.e. lateral infill.
  sql/50 keeps it as a flag, not a class. BOX estimates it as its own multiplicative term, so factors combine
  (pair × infill).
- **CI:** 90 % percentile cluster bootstrap over 3-mi blocks, 400 draws. The block is the resampling unit, which
  covers pad- and section-scale correlation.
- **n_pairs** = subject wells carrying the term (each is one subject–parent relation).

Metrics:

- oil qi (per-well fit), oil cum-6 / 12 / 24 (actual, calendar months from first report), oil EUR (per-well fit,
  raw 50-yr);
- gas cum-12 / EUR, and 12-mo GOR, both raw and relative to the D30 local level (15 nearest other cohort wells);
- water cum-12 / EUR.

## 4. Results — factors vs the reference (location + vintage FE; 90 % CI)

**WCA** (7,425 wells identify the factors):

| Term | n | Oil cum-12 | Oil EUR | Gas cum-12 | GOR vs local level | Water cum-12 |
|---|---|---|---|---|---|---|
| **infill** (same-bench parent) | 1,545 | **0.935** [0.92–0.95] | 0.938 [0.92–0.95] | 0.960 [0.93–0.99] | **1.024** [1.01–1.04] | 0.942 [0.92–0.96] |
| standalone | 1,592 | 1.034 [1.01–1.06] | 1.084 [1.06–1.11] | 0.980 | 0.992 | 1.030 |
| topfill \| WCC | 65 | 1.006 [0.96–1.05] | 1.036 | 1.314 [1.16–1.45] | 1.070 | 1.170 |
| topfill \| WCB_1 | 56 | 0.955 [0.89–1.03] | 0.953 | 1.011 | 0.994 | 1.083 |
| topfill \| WCB_2 | 53 | 0.976 [0.91–1.04] | 0.987 | 1.010 | 0.987 | 1.055 |
| underfill \| BS3_S | 85 | 0.887 [0.80–0.97] | 0.984 | 0.748 [0.65–0.87] | 1.058 | 0.900 |
| underfill \| BS3_C | 42 | 0.949 [0.87–1.03] | 0.882 [0.82–0.95] | 0.892 | 0.971 | 1.047 |
| topfill \| WCA_2 *(same pool)* | 62 | 0.893 [0.83–0.96] | 0.992 | 0.950 | 0.988 | 1.039 |
| topfill \| WCA_1 *(same pool)* | 28 | 0.825 [0.74–0.91] | 0.987 | 0.844 | 1.004 | 0.971 |
| underfill \| WCA_1 *(same pool)* | 49 | 0.876 [0.83–0.93] | 0.886 | 0.999 | 1.096 | 0.900 |
| underfill \| WCXY *(same pool)* | 33 | 0.968 [0.90–1.04] | 1.096 | 0.880 | 0.964 | 0.839 |
| sandwich \| all | 7 | 0.706 [0.40–1.04] | 0.775 | 0.540 | 0.890 | 0.609 |

**BS2_S** (1,804 wells):

| Term | n | Oil cum-12 | Oil EUR | Gas cum-12 | GOR vs local level | Water cum-12 |
|---|---|---|---|---|---|---|
| **infill** | 486 | **0.909** [0.88–0.94] | 0.930 [0.90–0.96] | 0.965 | **1.063** [1.04–1.09] | 0.935 |
| standalone | 618 | 1.055 [1.00–1.10] | 1.066 | 1.029 | 1.005 | 0.988 |
| topfill \| BS3_S | 57 | 1.087 [1.01–1.22] | 1.067 | 1.090 | 1.042 | 1.061 |
| topfill \| BS3_C | 48 | **0.694** [0.53–0.89] | 0.802 | 0.689 | 1.006 | 0.965 |
| underfill \| BS1_S | 23 | 0.942 [0.87–1.11] | 0.965 | 0.864 | 1.043 | 0.929 |
| sandwich \| all | 9 | 0.764 [0.66–0.99] | 0.776 | 0.992 | 1.301 | 0.878 |

**Plain read:**

- **Lateral infill is the factor that carries the weight.**
  - It is −6.5 % oil cum-12 in WCA and −9 % in BS2_S, on 21 % / 27 % of wells.
  - It is a level shift: EUR and cum-12 factors agree (EUR/cum-12 = 1.009 [1.00–1.02] in WCA).
  - It is the same in both benches (BS2_S/WCA 0.974 [0.93–1.01]).
- **Vertical parents on another bench matter much less in WCA.** At class level, topfill is 0.94 [0.91–0.97] and
  underfill 0.92 [0.88–0.96] on cum-12, and both are ≈ 0.96–0.99 on EUR. Under a 3BS sand parent, a WCA
  underfill loses 11 % early, but its EUR does not move.
- **Parent bench matters more than bench** (D11 "match on parent bench" is confirmed). A BS2_S topfill over
  BS3_C is 0.69 [0.53–0.89]; over BS3_S it is 1.09 [1.01–1.22]. In WCA, a topfill over WCC is 1.01 while over
  WCB_1 it is 0.955.
- **Standalone beats codev_stack by 3–5 % at cum-12 and 6–8 % on EUR, in both benches.** A well with no
  co-developed stack has less interference. This matters for how a PUD is classed (gate ask 4).
- **Sandwich** has 7 + 9 wells, at about 0.73 pooled. It is too thin to stand alone.

## 5. Checks behind the gate questions

**a. Selection bias** (plan: "topfill = newer completions + better rock"). Measured, and in WCA it runs the
*other* way. Oil cum-12 factors under each set of controls:

| WCA term | raw | + location FE | + vintage FE (record) | + operator FE (top 25) |
|---|---|---|---|---|
| standalone | 0.911 | 1.059 | 1.034 | 1.033 |
| topfill \| WCB_1 | 0.820 | 0.954 | 0.955 | 0.946 |
| topfill \| WCB_2 | 0.837 | 0.986 | 0.976 | 0.972 |
| underfill \| BS3_S | 0.794 | 0.891 | 0.887 | 0.885 |
| infill | 0.951 | 0.930 | 0.935 | 0.936 |

- Raw, the WCA topfills and standalones look **worse**. They sit in weaker WCA ground (edges, and areas where WCB
  was the first target). Location control does almost all of the correcting. Vintage moves factors ≤ 3 %;
  operator ≤ 1 %.
- What controls cannot remove is the within-area choice. Operators child-drill where they expect it to work, so
  factors estimated from drilled children may read optimistic for undrilled PUDs. Step 6 is the test of that.

**b. Estimator.** D32 makes the curve a mean, while log-OLS gives a geometric-mean ratio. A Poisson-PML
(arithmetic-mean ratio) re-estimate of the same model differs by a median of −0.5 % on oil cum-12 across the 14
terms with n ≥ 30. Exceptions above 3 %:

| Pair | log-OLS | PPML |
|---|---|---|
| BS2_S topfill \| BS3_C | 0.694 | 0.780 |
| WCA underfill \| BS3_C | 0.949 | 0.918 |
| WCA underfill \| WCA_1 | 0.876 | 0.844 |

On the infill and standalone terms the two agree within 1 %.

**c. Shape / EUR-vs-qi.** Same wells with 24 months:

| Term | qi | cum-6 | cum-12 | cum-24 | EUR | EUR / cum-12 |
|---|---|---|---|---|---|---|
| WCA infill | 0.939 | 0.932 | 0.937 | 0.939 | 0.946 | 1.009 [1.00–1.02] |
| BS2_S infill | 0.905 | 0.924 | 0.920 | 0.930 | 0.945 | 1.028 [1.00–1.05] |
| WCA standalone | 1.008 | 1.017 | 1.029 | 1.053 | 1.085 | **1.054** [1.03–1.08] |
| WCA same-pool topfills | 0.73–0.85 | | 0.82–0.91 | | 1.00–1.02 | **1.12–1.22** |
| WCA underfill \| BS3_C | | | 1.007 | | 0.898 | 0.89 |

- For the classes that matter, a uniform scale works. Applied on qi it scales EUR too, with Di and b unchanged.
- The exceptions: standalone, and the same-pool topfills, which take an early hit and recover on EUR. Treat that
  EUR with care. It is extrapolated, and 37 % of the fits are pinned at Di 4.0 (D34).

**d. Depletion time** (youngest parent's age at the subject's first production; future PUDs' parents are mostly
≥ 3 yr old):

| Term | < 1 yr | 1–3 yr | ≥ 3 yr |
|---|---|---|---|
| WCA infill | 0.941 | 0.930 | 0.936 |
| BS2_S infill | 0.983 | 0.880 | 0.899 |
| WCA topfill (other bench) | 0.882 | 0.910 | 0.988 |
| WCA underfill (other bench) | 0.968 | 0.932 | 0.903 |

- WCA infill is flat in parent age, so it transfers to PUDs.
- BS2_S infill is near zero only for young parents. For old parents it is about 0.89–0.90, slightly harsher than
  the 0.909 average.

**e. Per-bench vs per-basin (D11).** Class-level factors on the stacked frame, with a joint bootstrap:

| Class | WCA | BS2_S | BS2_S / WCA | Pooled |
|---|---|---|---|---|
| infill | 0.935 | 0.910 | 0.974 [0.93–1.01] | 0.930 [0.91–0.95] |
| standalone | 1.034 | 1.049 | 1.014 [0.96–1.07] | 1.038 |
| topfill | 0.940 | 0.899 | 0.957 [0.80–1.10] | 0.931 |
| underfill | 0.923 | 0.948 | 1.027 [0.96–1.18] | 0.926 |

- **No oil class differs between the benches** (every ratio CI spans 1, cum-12 and EUR).
- The one clear difference is gas. The infill **GOR** shift is larger in BS2_S: 1.063 vs 1.025, ratio 1.037
  [1.01–1.07].
- So pooling at class level across benches is supported for oil. Pairs stay bench-specific by construction:
  different benches have different parent benches.

**f. Gas: inherit oil's factor through the ratio, or carry its own?** Against the D30 local GOR level:

- children run higher GOR: **infill +2.5 % WCA / +6.3 % BS2_S** (CIs exclude 1); underfill +3 % (CI ≈ 1);
- topfill +1 %; standalone 0.

Inheriting through the ratio at the local level would under-predict infill gas by 2.5–6 %. Gas cum-12 infill is
0.96 against oil 0.935.

**g. WCA area normalisation.** Normalising each area's mixed cohort to the reference moves the area EUR by a
median of ×0.993 (range 0.946–1.025), and cum-12 by ×1.009 (0.976–1.044).

- The reference curve = the record curve × the multiplier. That is a uniform scale: qi moves, nominal Di and b do
  not.
- The mixes are mostly codev_stack (median 71 %) and standalone (22 %), with infill at 19 %. That is why the
  multipliers sit near 1.

## 6. Flags (decisions of record that conflict or are not covered)

a. **Lateral infill is not a sql/50 class.** D11 names "dev-scenario factors per (scenario, parent bench)". The
   largest and best-determined effect is the same-bench parent flag, which sql/50 keeps outside the class.
   I estimated it as its own term. Whether it is part of BOX risking is your call (ask 1).

b. **D33 vs sql/50 on same-pool parents.** About a third of WCA "topfill / underfill" have a WCA_1 / WCA_2 / WCXY
   parent: 172 of 503. Under D33 that is the same bench. These pairs run 0.83–0.97 at cum-12, harsher than
   lateral infill (0.935). The pooled view folds them into infill (WCA infill 0.929 [0.91–0.95], n 1,661). A
   factor keyed on WCA_1-vs-WCA_2 tags inherits the tag noise that D19/D33 pooled away (ask 2).

c. **PUD class vs PDP class (step 7, but it sets the table).** Classed against PDP only, a PUD can never be
   `codev_stack`, because co-development is with other PUDs. An unparented PUD would therefore read as
   `standalone` (+3–8 %), when a pad-developed PUD is codev. **My read:** an unparented PUD = reference (1.00),
   and `standalone` is used only for scoring actual wells (step 6) (ask 4).

d. **The plan's selection-bias premise is wrong for WCA** (§5a). It is reported as measured. Nothing in the method
   depends on it.

e. **Sandwich has too few wells to estimate:** 16 across both benches.

f. **Two items reported, not chased:** BS2_S topfill | BS3_C at 0.69 (48 wells / 27 blocks; raw 0.59, PPML 0.78),
   and the WCA topfill | WCC gas uplift (+31 %; GOR vs local level only +7 %, so most of it is neighbourhood GOR).

g. Carried from 5b (§9), not touched here: the reconcile tolerance, the TC water fit on the oil Di bound, and D10
   rung 3 vs D26.

## 7. Gate-5c asks (gate 5 decisions with the pilot numbers in hand)

1. **Infill in risking?** Lateral infill (same-bench parent) as a BOX factor term next to the sql/50 classes.
   **Rec: yes.** It is the largest, best-determined effect.
2. **Same-pool parents:** keep the sql/50 view (WCA_1↔WCA_2 parents as separate pairs) or use the BOX pooled view
   (they count as infill). **Rec: pooled view, consistent with D33.**
3. **EUR-vs-qi application (plan gate 5).** **Rec: a uniform scale of the reference curve by the cum-12 factor.**
   It is observed rather than extrapolated, and it is what step 6 scores. For the large classes it equals the
   EUR factor within 1–3 %. The alternative is the EUR factor; the shape table shows what changes.
4. **Unparented PUDs** = reference (1.00), not standalone (flag c). **Rec: reference.**
5. **Per-bench vs per-basin pooling (plan gate 5).** **Rec: the ladder in `ladder.csv`, stamped per factor:**
   - (1) the bench pair when n ≥ 30;
   - (2) the bench class;
   - (3) the class pooled across benches (sandwich lands here).

   Oil shows no bench difference at class level.
6. **Gas (§9 item).** **Rec: gas carries its own GOR-level factor through the ratio.** That is
   α_PUD = α_local + ln f_GOR(class), applied on top of oil's factor. In practice only infill differs from 1
   (WCA 1.024 / BS2_S 1.063). The alternative is inherit-only (gas infill under-predicted 2.5–6 %).
7. **Estimator:** log-OLS (current) or PPML. **Rec: PPML as the factor of record, for consistency with D32.** It
   agrees within 1 % on the terms that carry the weight.

Water carries its own factors (independent Arps), from the same table. Next after the gate: **5d** (box.type_curve /
tc_member / risk_factor DDL, go-apply), then step 6.

## 8. Gate 5c outcome (Michael, 2026-10-11)

Every §7 recommendation was accepted and is recorded in plan §2 as D41–D47:

| Ask | Decision |
|---|---|
| 1 | **D41:** lateral infill is a risking term. |
| 2 | **D42:** same-pool parents count as infill. |
| 3 | **D43:** factors apply as a cum-12 uniform scale. |
| 4 | **D44:** an unparented PUD gets the reference factor (1.00). |
| 5 | **D45:** the pair → bench class → basin class ladder, n ≥ 30. |
| 6 | **D46:** gas carries its own GOR-level factor through α. |
| 7 | **D47:** PPML is the estimator. |

**What this deliverable is now:** the evidence for those decisions. It is not yet the factor table of record:

- `factors.csv` is the log-OLS record view, with sql/50 same-pool pairs kept separate.
- `ladder.csv` is built on that view.

5d regenerates the factors of record under D42 (pooled view) + D45 (ladder) + D47 (PPML), and stores them in
`box.risk_factor` on go-apply. Expected values: WCA infill ≈ 0.93 (pooled-view log-OLS 0.929; the PPML estimate of the
record-view infill term is 0.930).

