# BOX step 6 — hindcast vs Novi 2025Q3 (acceptance) — gate 6

**Verdict: FAIL** (oil FAIL, gas FAIL) under §8 + D48 + D49. Review surface: `acceptance.html`.
Production plots: `production.html` — actual vs Novi 2025Q3 (scaled to the drilled lateral) vs BOX (of record × F(k), and
uptime-free), monthly or cumulative, per holdout well and as bench / area averages; F(k) fitted for every month 1–24 on the
training cohort (oil 0.59 in month 1 → 0.90 at 6 → 0.91 at 12 → 0.94 at 24). Each line reconciles to the scored numbers
(BOX monthly × F summed = scored prediction to 4e-15; Novi monthly = sql/43 cums to 5e-15; actual sums = sql/43 on 99.9 %).
Serve with `python -m http.server 8766 --directory docs/box` (the file is 1.5 MB).
Builder: `python -m scripts.box_hindcast --out docs/box/step6-2026-10-12` (read-only, ~9 min; `box/hindcast.py`
pure, `box/hindcast_report.py` rebuild + page; 9 DB-free tests in `tests/test_box_hindcast.py`). Nothing stored.

## 1. Set-up (decided before scoring)

- **D48** (Michael 2026-10-12): per stream × horizon, an **area test** (strict majority by area COUNT of areas with
  ≥ 10 Novi-matched holdout wells) AND a **bench test** (all matched wells pooled). **D49**: gas = oil's thresholds;
  pass = oil AND gas.
- Cutoff: 2025Q3 Delaware recognition cliff **2024-12-01** (sql/43). BOX sees wells first-producing before it and
  production through **2025-06** (one quarter before the 2025-09-30 vintage date; Novi's own data date is not
  recoverable — the trimmed 2025Q3 slices hold no PDP forecasts). Same extent of record (plan).
- Rebuilt at the cutoff with the record methods, nothing re-tuned: step 4 (6,668 D9 cohort wells → the D29 rule picks
  **k = 15**, CV-min 41, held-out R² 0.19; record = 35), step 5b (10,874 wells fitted, all 15 areas rung 1, area oil
  EUR/kft median 73,632 bbl, 38,562–127,695; oil Di nominal median 2.88/yr = 74 % 1-yr effective; rule 6 worst
  0.03 %), 5c/5d factors (PPML, D42/D45; WCA infill oil 0.922, GOR 1.026; ref_mult oil 0.995–1.017), D36 F(k) on the
  training cohort: **oil 0.898 (cum-6) / 0.914 (cum-12), gas 0.863 / 0.925** (n 6,668).
- Holdout: 1,364 sql/43 2025Q3 wells in the gate-1 WCA set; 257 Novi-matched (`direct`), 1,106 unmatched (BOX only).
  Scored vs Novi: **174 at cum-6, 56 at cum-12.** Actuals = sql/43's for both (its mop cums equal BOX's calendar-month
  cums on 99.7–99.8 % of wells — checked).

## 2. Result (Novi-matched wells; error = actual / forecast − 1, + = forecast LOW; band = P10 − P90, P10 = high)

| cell | area test | bench: BOX bias / band | bench: Novi bias / band | bench |
|---|---|---|---|---|
| oil cum-6 | FAIL 1/6 | −9.4 % / 0.75 | −13.7 % / 0.67 | FAIL (band wider) |
| oil cum-12 | FAIL 1/2 | −14.6 % / 0.52 | −12.2 % / 0.57 | FAIL (bias > 10 %, worse than Novi) |
| gas cum-6 | FAIL 1/6 | −3.8 % / 0.81 | −17.2 % / 0.92 | PASS |
| gas cum-12 | FAIL 1/2 | −10.6 % / 0.63 | −22.2 % / 0.77 | FAIL (bias just over 10 %) |

BOX is **too high** on the 2025 wells, like Novi: same sign, similar size on oil, about half Novi's on gas. BOX on
every holdout well (incl. 1,106 Novi-unmatched): oil cum-6 −7.6 % (n 1,053), cum-12 −8.9 % (n 602); gas −0.9 % / −2.6 %.
Qualifying areas at k = 15: 6 at cum-6 (only area 9 passes oil; area 6, 57 wells, passes gas), 2 at cum-12.

## 3. Diagnosis (for the fail branch — reported, nothing changed)

1. **Lateral scaling is the biggest lead.** BOX = per-1,000-ft curve × lateral (linear), and the D9 curve cohort is
   6,000–13,000 ft. Oil cum-6 error by lateral, all holdout wells: < 8,000 ft **+9.4 %** (n 180), 8–11k −7.6 % (609),
   11–13.5k −12.1 % (108), **> 13,500 ft −23.9 %** (156); Novi on matched wells shows the same gradient (> 13.5k −26 %).
   27 % of holdout wells are > 11,000 ft. This bears on the lateral-length pooling decision of record (one pool per
   bench, eng_db #78/#80) — **Michael's call**, not changed here.
2. **Not vintage:** cohort median 12-mo oil/kft is flat 2016–2025 (20.3k–23.0k bbl/kft).
3. **F(k) halves the miss but doesn't close it:** layer 1 (area mean curve × lateral) −19.2 % oil cum-6 → layer 2
   (+ ref_mult, factors, local GOR) −18.6 % → layer 3 (+ F(k)) −9.4 %. Scenario factors move oil little (ref_mult ≈ 1;
   codev_stack carries 121 of 174 wells). Gas: the D30 local-GOR level is worth ~18 pts (−34.8 % → −17.0 %).
4. **Band:** BOX's oil band is wider than Novi's at cum-6 (0.75 vs 0.67) — partly the lateral gradient (it spreads
   errors by lateral), so (1) bears on §8.2 too.
5. Scale caveats: cum-12 rests on 56 wells; 2 qualifying areas at cum-12.

## 4. Flags / asks for gate 6

a. Accept the verdict FAIL (as pre-registered under D48/D49).
b. Diagnose-and-re-run direction: lateral-length treatment (nonlinear lateral scaling or lateral-class curves) is the
   lead; it touches the eng_db #78/#80 pooling decision — your call before any change.
c. k = 15 at the cutoff vs 35 on the record (the D29 rule on less data; the CV curve is flat past ~14). Scoring is on
   the hindcast areas; the per-record-area view isn't built.
d. Post-cutoff information still inside the rebuild (stated on the page): the extent, gate-1 bench sets, live sql/50
   classes, revised volumes.
e. Production as-of 2025-06 is an assumption (Novi's actual data date isn't recoverable from the trimmed slices).
f. No `box.hindcast_run / hindcast_score` DDL authored (plan §4.2 lists them for step 8's Accuracy tab) — needs a
   go-apply when wanted.

## 5. Fail-branch follow-up (Michael 2026-10-12): rolling-origin backtest, lateral efficiency, density

Review surface: `backtest/backtest.html` (`python -m scripts.box_backtest`, ~55 min, read-only; `box/backtest*.py`, 4 tests).
Folds: cutoffs Dec 1 2021 / 2022 / 2023 / 2024, each rebuilt with the step-6 methods from wells first-producing before
the cutoff, production through the month before it (no vendor lag); holdout = the next 12 months' gate-1 WCA wells
(1,138 / 1,158 / 1,009 / 912), scored against actuals. Novi plays no part. Variants pre-registered (see page).

**a. BOX as built, oil bias by fold** (− = BOX high): cum-6 +3.5 / −0.8 / −1.2 / −6.4 %; cum-12 −2.9 / −5.6 / −5.9 / −8.2 %;
cum-24 −8.9 / −10.2 / −10.4 % (2024 fold has no cum-24). Inside ±10 % at cum-6 and cum-12 in every fold. **The miss
grows with months on production in every fold, and with cutoff year** — a SHAPE drift (newer wells decline faster
after month ~6 than the 2016+ cohort the curve averages), not a level miss; F(k) is calibrated per month on the
training wells, so this is out-of-sample drift. (The earlier "not vintage" note was about 12-mo level only.) The
step-6 Novi-matched subset (−9.4 % oil cum-6) was a harder draw than its full fold (−6.4 %, no-lag build). Gas:
cum-6 +1.5…+7.5 %, cum-12 −1.3…+2.3 %, cum-24 −0.5…−4.2 %. Oil P10–P90 band 0.84–0.92 (cum-6), 0.75–0.80 (cum-12).

**b. Lateral efficiency (Cui & Cross 2022, Delaware WCA, docs/box/ref/3723784.pdf) works.** All folds, oil cum-6:
< 8k ft +7.6 → −1.5 %; 8–11k −2.3 → −0.1 %; 11–13.5k −9.8 → −4.4 %; ≥ 13.5k −10.7 → −1.2 % (358 wells, curve
extended past 12,500 ft). Overall bias barely moves (the mix is mostly 8–11k); 2,000/60 vs 1,700/50 within 0.3 pt.
Recommendation: adopt as a decision of record (per-well lateral scaling, normalised to each area curve's lateral mix).

**c. The density term as specified does NOT earn its place.** Training multipliers are stable across folds (6+ near
neighbours 0.92–0.94, 4–5 0.96–0.97, 0–1 1.03–1.06; no same-bench neighbour 0.93–0.95; same-bench < 660 ft ≈ 1.00–1.04,
i.e. NO tight-spacing penalty in the data), but next year they over-correct (6+ neighbours −3.9 → +3.3 %), push overall
bias ~3 pts the other way and widen bands. sql/47 keeps per-bench aggregates only (nearest dtvd per bench), too coarse to
see a Burton-type cube. A real test needs well-to-well 3-D geometry (new warehouse SQL) — Michael's call.

**d. k is unstable at the cutoffs:** the D29 rule picks 53 / 14 / 14 / 22 areas (record 35; step-6 build 15) — the CV
curve is flat, so the 1-SE pick wanders. Worth a decision before areas are rebuilt quarterly (D17).

**Asks:** (1) adopt the backtest as the acceptance basis (replacing D18 / §8) and set its thresholds; (2) adopt Cui lateral
efficiency (touches eng_db #78/#80); (3) density: drop, or fund the 3-D geometry measure; (4) next diagnosis = the
post-month-6 shape drift; (5) k stability.

## 6. Follow-up 2 (Michael 2026-10-12): Cui adopted (D50), 3-D spacing scoped, shape drift dug

- **D50 recorded** (plan §2): lateral efficiency replaces linear per-ft scaling — Cui & Cross Delaware WCA, 2,000 lb /
  60 bbl curve, relative to each area curve's own member mix; code `box/lateral.py` (the backtest imports it).
- **3-D spacing scope:** `SPACING_3D_SCOPE.md` — pair table + per-well features (gunbarrel offsets, drainage cross-section
  area, parent depletion at first production), PUD side at planned spacing, test plan, effort. Nothing built (new SQL =
  go-apply). Novi's `raw_novi."WellSpacing"` carries 11 as-of-first-production features (only 3 passed through today).
- **Shape drift** (`shape/shape.html`, `python -m scripts.box_shape_drift`, 25 s, read-only; 8,456 WCA wells with 24 months,
  fp ≥ 2016, inside an area of record):
  - Raw: median cum-24 / cum-6 falls 2.42 (2016) → 2.20 (2018) → 2.01 (2024); cum-12 / cum-6 1.61 → 1.47; calendar rate in
    months 19–24 over months 4–6 0.36 → 0.29. Peak month median 2 in every vintage; uptime months 7–24 ~0.95–0.98, not falling.
  - Inside a TC area, 2024 vs 2018: **−15.5 %** in cum-24 / cum-6 (2021–23 −13…−15 %). Lateral + completion size: −17.6 %;
    + Novi spacing: −18.5 %; + operator: −18.4 % — **none of them absorbs it**. + early-time behaviour (peak month,
    month-1 share) + GOR: **−8.6 %** — about half the drift travels with how wells come on (peak month alone: +30 % on
    the ratio per 1 SD). Uptime adds nothing; the producing-day rate ratio drifts too (−12.7 %), so it is decline, not downtime.
  - Implication for BOX: an area curve averaged over 2016+ wells carries older, shallower post-month-6 decline; newer wells
    fall below it — exactly the backtest's growing-with-time miss. Remedies to test in the backtest (not built): (a)
    recency-weighted / last-N-years curve cohort (shape from recent vintages, level from the area), (b) a vintage term on
    the shape; (c) the 3-D spacing + parent-depletion features may carry part of the unexplained half.

## 7. 3-D spacing prototype (Michael 2026-10-12: "spacing regime of the average well getting worse explains the steeper declines")

`spacing3d/spacing3d.html` — `python -m scripts.box_spacing3d` (206 s, read-only; `box/spacing3d.py` geometry + features,
3 tests). 11,100 WCA wells (fp ≥ 2016, in an area of record), 33,289 Delaware horizontals as the neighbour universe (any
bench), 149,190 co-extent pairs. Features as of first production per SPACING_3D_SCOPE.md (A = 2, gate 2,640 ft, one TVD/well).

- **The regime did tighten — a lot.** Median lateral spacing (nearest left/right within ±250 ft TVD) 2,255 ft (2016) →
  1,470 (2018) → 885 (2020) → 847 (2024) → 806 (2026): horizontal spacing plateaus after 2020. The **drainage
  cross-section** keeps shrinking — 8.6 M ft² (2016) → 3.7 M (2018) → 1.67 M (2024) → 1.27 M (2026) — stacking keeps
  tightening after the horizontal plateau. Parent depletion (median parent cum per kft at first production) 10 → 45 kbbl.
  Within area, 2024 vs 2018: cross-section ×0.44, lateral spacing ×0.74, parent depletion ≈ ×3.6.
- **Tighter → steeper, as expected — but it explains only part of the shape drift.** ln(cum-24 / cum-6), within area, 2024 vs
  2018: −16.3 % (+ lateral) → **−13.2 %** with the 3-D features → −13.7 % with parent depletion: ~3 of ~16 points (≈ 20 %).
  Cross-section is the carrier (+3.4 % on the ratio per 1 SD; horizontal spacing alone ~0). Novi WellSpacing head-to-head
  explains none of it (−17.5 %). Children arriving within 24 months: nothing. Early-time behaviour still takes the drift to
  −6.0 % — possibly partly a *consequence* of tighter spacing (not tested yet: mediation).
- **Level (12-mo oil / kft) is where spacing bites harder:** within-area 2024 vs 2018 −10.1 % (+ lateral) → −7.5 % (3-D) →
  −5.8 % (+ parent depletion), ≈ 40 % of the level drift; our features beat Novi's (−8.5 %). Per 1 SD: lateral spacing
  +3.1 %, parent depletion −4.6 %.
- **Burton Flat 3 1:** the cube shows in the cross-section, not in lateral spacing — 626H 0.58 M ft² (2024 median 1.67 M),
  339H 1.09 M, 624H 1.38 M with a 360-ft right neighbour; lateral spacing alone reads a normal ~1,200–1,400 ft.
- Caveats: v1 one TVD per well; A = 2 not calibrated; the 660 × 300 ft ellipse is too small (median 0 neighbours — drop or
  widen); "children within 24 months" is right-censored on young wells.

Next (proposed): (1) backtest variant with cross-section + lateral spacing + parent depletion as of first production (the
prototype computes per fold without warehouse writes); (2) mediation check — does spacing drive the early-time shift;
(3) only if (1) earns it: sql/59 `well_neighbors` / `well_spacing_3d` (go-apply), which PUD forecasting at planned spacing
needs regardless.

## 8. Backtest variant with 3-D spacing + mediation check (Michael 2026-10-12)

**Backtest** (`backtest/backtest.html`, re-run with two new variants; 35 min). `s3d` = BOX × exp(b · features) on ln drainage
cross-section, ln lateral spacing, ln(1 + parent cum per kft), all as of first production, PPML with the base prediction as
offset, training wells only; a holdout well's parent depletion read at the cutoff. `lat+s3d` = on top of D50.
- Fitted multipliers are small and stable across folds (per 1 SD): lateral spacing ×1.03–1.05, parent depletion ×0.98–0.99,
  cross-section ×0.99–1.01 (it adds nothing beyond lateral spacing + depletion once the area / scenario model is in).
- Oil, mean |bias| over 4 folds — cum-6 / 12 / 24: base 3.0 / 5.6 / 9.8 %; lat 2.7 / 5.6 / 9.7; **s3d 2.7 / 4.3 / 8.3;
  lat+s3d 2.2 / 4.5 / 8.4**; dens 3.4 / 2.9 / 6.8. Per fold, s3d moves every oil cell ~+1.3–1.5 pt (cum-24: −8.9 → −7.4,
  −10.1 → −8.6, −10.4 → −8.9 %): newer (holdout) wells are tighter than the training mix, so the term lowers them — the
  mechanism Michael proposed, worth ~1.5 of the ~9–10 pt cum-24 miss. P10–P90 bands unchanged (oil cum-12 0.76–0.80 base vs
  0.76–0.79 s3d): it shifts the vintage level, it does not sharpen well-to-well prediction. Residual oil cum-6 bias by
  cross-section band is already flat in base (−3.0 … +1.2 %).
- `dens` scores better at cum-12/24 only by shifting the level ~+3 pt (it makes cum-6 and gas worse) — still not recommended.

**Mediation** (`spacing3d/spacing3d.html` §4; 9,490 wells, within area, classical SEs):
- Peak month moved earlier: 2021–24 wells peak ~0.5 month earlier than 2018. Spacing absorbs ~16 % of that (2024: −0.56 →
  −0.47 month); its link to peak month is weak (cross-section t ≈ 1.8). Month-1 share has no year trend.
- Spacing acts on decline mostly directly: cross-section's effect on ln(cum-24 / cum-6) is ~40 % mediated by early time,
  60 % direct (t 2.8); parent depletion ~6 % mediated (t 4.1 direct); lateral spacing alone not significant.
- Metric caveat: cum-24 / cum-6 is partly mechanical in peak timing (an earlier peak lowers it with identical decline), so
  "early time absorbs half" (§6) overstates early time. The peak-free measure — rate in months 19–24 / months 4–6, both
  past the median month-2 peak — still falls 0.336 → 0.286 from 2018 to 2024 (−15 %): the steeper decline is real.

**Read:** the spacing regime did tighten and it does steepen decline and lower level, but as measured it explains ~15–20 %
of the late-time miss. Most of the shape drift is a time trend the geometry doesn't carry (earlier peaks — likely
flowback / choke / lift practice — and an unexplained remainder). Next lever: recency-weighted area curves / a vintage
shape term (§6 a/b); keep s3d as a candidate term on top. sql/59 remains justified for PUD forecasting at planned
spacing, not by forecast skill alone.
