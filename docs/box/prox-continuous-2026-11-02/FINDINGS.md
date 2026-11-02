# BOX step 24 — continuous proximity factor: FINDINGS, revision 3 (Delaware, scored 2026-11-02)

Scored once at the revision-3 freeze `ffc042fa3366883e0aea16f0a23c5b48e3d72cbc` (§11; definition digest `47b2898a`), 1,000-draw
bootstrap, same folds as the rev-2 score (`rev2/FINDINGS.md`). Inputs = the step-2 frame (14,545 harness children, 3,971 controls,
6,581 exposed of which 4,778 carry ≥ 2 parents) and `runs/prox/links.pkl`. Nothing stored; run 19 untouched; Midland unscored.
`summary_delaware.json` is the record.

## 1. Verdict — FAIL on P2 alone (oil cum-24): P1 pass, P2 fail against the incumbent, P3 pass

| test | result | number |
|---|---|---|
| P1 calibration where material (F_applied ≤ 0.90, 600 test children) | **PASS** | 1.018 [0.980, 1.055] |
| P2 skill (51 cells ≥ 30 children) | **FAIL** | cell RMS 0.055 vs 0.076 no haircut vs **0.041 incumbent D113 ladder** |
| P3 cell calibration | **PASS** | 88 % of cells within ±10 % |
| C8 unexposed test children (2,395) | uplift REAL | **1.047 [1.024, 1.071]**, above 1 in every fold, interval excludes 1 |

The exposed side is calibrated now. Test children by parent count (rev 2 in brackets):

| parents | n | factor applied | residual after it | no haircut | incumbent |
|---|---|---|---|---|---|
| 0 | 2,395 | 1.000 | **1.047** | 1.047 | 1.010 |
| 1 | 1,140 | 0.990 | 1.042 (0.981) | 1.032 | 1.020 |
| 2 | 932 | 0.982 | 1.028 (0.975) | 1.009 | 1.010 |
| 3 | 696 | 0.969 | 1.011 (0.951) | 0.979 | 0.994 |
| 4+ | 1,743 | 0.921 | **1.002** (0.915) | 0.920 | 0.988 |

(The rev-2 numbers were scored on the control-normalised log-ratio, revision 3 corrected that — see the revision row; the
comparison is indicative.)

**Why P2 fails: the cap.** The largest cell is `none` (2,395 unexposed children) and it sits at 1.047 because the §5 cap holds
unexposed sticks at BOX as-is while the incumbent ladder carries its `none` rung (1.04). That one cell dominates the n-weighted
RMS. Post hoc, on the same rows with the cap lifted (factor = F / F_mix, nothing else changed): P1 1.018, **P2 0.0406 vs 0.0412
incumbent**, P3 0.902 — every test passes, by a hair on P2. Without the `none` cell the incumbent's cells are tighter (0.052 vs
0.059): on exposed children the two methods are close and the ladder is slightly sharper cell by cell; the continuous model's
advantages are elsewhere (§4). The C8 clause registered in §7 is met, so **G3 is reopened on evidence**: the uplift is real,
+4.7 % on unexposed wells.

## 2. The curve, the rule, the checks

**Contest (4,778 multi-parent children): R2 multiplicative wins outright** — gain over R1 0.0030 [0.0012, 0.0047]; R3 / R4 do
not exclude zero. In the walk-forward folds R3 won 2021 and 2022, R2 won 2023 (gains small; the rule is chosen per fold as
registered). Michael's "0.8 × 0.8 = 0.64" is what the data pick when every parent is in the fit. Free regression on the
exactly-two children (R3 curve): β_nearer 0.50, β_farther 0.92 overall; flanked (n = 67) 1.46 / 3.05.

**The curve of record (R2, surface, oil cum-24):** F_min 0.908, d50 1,188 ft, k 3.6, a_below 0.91, a_above 2.97.

| parent | 100 ft | 300 | 500 | 800 | 1,000 | 1,400 | 2,000 | 2,600 |
|---|---|---|---|---|---|---|---|---|
| same depth, sideways | 0.908 | 0.909 | 0.912 | 0.926 | 0.940 | 0.967 | 0.988 | 0.995 |
| BELOW the child, vertical gap | 0.908 | 0.909 | 0.911 | 0.922 | 0.934 | 0.960 | 0.984 | 0.993 |
| ABOVE the child, vertical gap | 0.909 | 0.932 | 0.972 | 0.993 | 0.997 | 0.999 | 1.000 | 1.000 |

Bands (200 block-bootstrap refits) are ±0.03 at the floor and ±0.01 past 1,000 ft. Read: a parent BELOW counts almost 1:1 with
sideways distance (a_below 0.91) and releases slowly; a parent ABOVE is three times "farther" per foot (a_above 2.97) and is
gone by ~500 ft — Michael's ~500-ft anecdote holds for parents above, not below. Per-parent floor 0.91 under R2, because the
multiplicative rule stacks several parents; the worst-parent curve (R1, the step-2 dose) has floor 0.795, d50 1,019 ft, and
matches the step-2 bins built on every exposed child's nearest parent (0.765 / 0.871 / 0.906 / 0.977 / 1.014 at 0–400 … 2,000–
2,640 ft, n 69 / 279 / 1,024 / 759 / 562).

- **C2** — the three-curve form is WORSE out of sample (gain −0.003 [−0.005, −0.002]): the surface holds, with evidence this
  time. Three stack curves are not needed; the anisotropy pair carries the asymmetry.
- **C1** reads FAIL (20 % / 0 % / 25 %) by construction under R2: the bins are the TOTAL effect at the nearest parent, the R2
  curve is a per-parent factor. The check compares like with like only for R1 (whose curve matches the bins above). A revision
  should state C1 on the R1 curve or on the rule's total prediction per bin.
- **C4** — F_min 0.899 / 0.908 / 0.921 and d50 1,233 / 1,188 / 1,380 ft at cum-12 / 24 / 36: the haircut eases slightly with
  horizon; no reversal.
- **C3** — 14 bench pairs with ≥ 36 children sit outside ±10 %: WCA_1 / WCA_2 children over a WCB_1 parent (parent below)
  1.10–1.14 (over-penalised), BS2_S over BS3_C 0.77, WCA_1 over BS3_S 0.89, BS2_S over BS3_S 1.21, WCXY / WCXY 1.18, WCB_2 /
  WCB_2 0.85. At n ≈ 50 the 2-σ band is ±11 %, so most are at the edge of noise and the signs mix; a bench-pair offset (G5)
  has weak evidence. The WCA-over-WCB_1 reading is the one with a story (a frac barrier below the WCA) and 141 children.
- **C5** — nearest parent's cum per kft: 0–20 kbbl/kft 0.916 → 20–40 0.996 → 40–60 1.016 → ≥ 60 **1.092** (n 356 / 1,594 /
  1,428 / 1,133), monotone; parent age 2–4 yr 0.958, ≥ 4 yr 1.049. A child beside a good parent out-performs the factor, beside
  a poor one under-performs it. That is rock quality read through the parent, not depletion (depletion would run the other
  way). It is the strongest residual structure left and it is a *level* covariate (where the child sits), not a proximity term.
- **Single-parent reference** (rev 2's fit on the same data): F_min 0.954, k at its bound — the thin-near-end artefact, kept
  for the record.

## 3. Sticks (what-if, nothing stored) and oil

41,875 run-19 sticks carry ≥ 1 link (the 9,088 with none are unexposed by any definition). Under R2: mean factor 0.910
(uncapped 0.932), 35 % below 0.90; the 24,881 sticks with 3+ parents average 0.858 and 7,513 of them sit below 0.80.

Joined to run 19's PUD oil (`docs/box/prox-2026-10-19/pud_outcomes.csv.gz`, 50,963 sticks, 29,560 MMbbl before any haircut;
the incumbent leaves 23,300 MMbbl, −21.2 %, of which 5,423 MMbbl is the two no-forecast gates):

| population (incumbent outcome) | sticks | oil before | incumbent after | rev 3 capped | rev 3 uncapped |
|---|---|---|---|---|---|
| unexposed, as-is | 25,789 | 14,506 | 14,506 | 14,467 | **14,940** |
| single parent, as-is | 6,980 | 3,845 | 3,845 | 3,716 | 3,754 |
| multi-parent, haircut | 9,706 | 5,786 | 4,949 | 4,893 | 4,896 |
| no forecast, precedent | 3,927 | 2,351 | 0 | (1,890) | (1,891) |
| no forecast, package | 4,561 | 3,072 | 0 | (2,184) | (2,184) |

With the incumbent precedent gates kept (G4 default), the continuous factor lands within ±1.2 % of the incumbent in total:
capped 23,076 MMbbl (−1.0 %), uncapped 23,590 (+1.2 %). The pieces move more than the total: the 6,980 single-parent sticks
lose 3.3 %, the 9,706 incumbent-haircut sticks are within 1 %, and lifting the cap adds +434 MMbbl on the unexposed sticks.
The G4 geometry key would forecast 6,310 of the incumbent's 8,488 refused sticks (about 4,070 MMbbl at these factors) and
refuse 1,702 the incumbent forecasts — the policy lever, reported only.

## 4. Read, for gate 24a

- **G1** adopt the surface: yes on the C2 evidence.
- **G2** adopt R2 multiplicative: the contest picks it outright on the full training set; per fold it is R3 twice, R2 once,
  with gains that do not separate. Either is defensible; R2 is the registered winner.
- **G3** the cap: the registered C8 clause is met — unexposed wells sit +4.7 % above BOX's mix-calibrated level in every fold.
  Lifting the cap is what makes the model pass P2 (post hoc, by a hair) and it raises the unexposed inventory by ~434 MMbbl.
  The investor walkthrough question stands: BOX would then forecast its unexposed sticks above its own calibrated level,
  because that level was calibrated on a mix that includes spacing damage. The data say that is the right correction; the
  decision is whether to carry it. If lifted, it is revision 4 and a re-score (deterministic: same seed, same rows — the
  numbers above are what it will show).
- **G4** precedent: the incumbent gates keep the total within 1 %; the geometry key is a 4,000-MMbbl policy question with
  cards still to draw.
- **G5** no bench-pair offset: the evidence is at noise level except WCA over WCB_1.
- **G6** the Midland can be scored on this design as registered (no design change pending except the cap); its tuning
  children only.
- **The honest comparison with the incumbent on exposed children:** the ladder's cells are slightly tighter (0.052 vs 0.059 RMS
  without the `none` cell). The continuous model's case is not sharper cells; it is one curve instead of 214 keys, a factor
  for the 6,980 single-parent sticks, the near-end measured from 6,581 children instead of ladder cells of 30, a measured
  stack asymmetry, and no 30-analog floor on the factor itself. C5 says the next real gain is a rock-quality covariate, not a
  better distance curve.

## 5. Disclosed

The rev-2 score's residual was taken on the control-normalised log-ratio (revision row); its C8 ≈ 1 was an artefact and is
withdrawn. Everything in §1–§3 was read after the one registered revision-3 score. The uncapped numbers in §1 and §3 are post
hoc on the same rows, not a score. No card was drawn.
