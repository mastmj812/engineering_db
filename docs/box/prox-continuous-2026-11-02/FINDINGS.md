# BOX step 24 — continuous proximity factor: FINDINGS of record (revision 5, both basins, scored 2026-11-02)

Scored once per basin at the revision-5 freeze `77d50a7f69b807f0c710c148f071fd9e4c44ee4d` (§11; definition digest `2e8bb5a7`),
1,000-draw bootstrap, the same folds and rows as revisions 2–4. Revision 5 changed one thing: the level is **fitted** with the
curve (a free intercept in the joint fit, every scored child in the fit, unexposed at F = 1), and the factor is level × F_rule;
the mix factor F_mix is retired. Earlier scores: `rev2/` (single-parent fit, FAIL), `rev3/` (joint fit, cap kept, P2 FAIL through
the capped unexposed cell), `rev4/` (cap lifted: Delaware PASS, Midland FAIL on P1 — the score that motivated this revision).
Nothing stored; run 19 untouched; Midland D52 holdout unread. `summary_delaware.json` / `summary_midland.json` are the record.

## 1. Verdicts

| basin, oil cum-24 | P1 calibration where material | P2 cell RMS vs incumbent | P3 cells within ±10 % | verdict |
|---|---|---|---|---|
| **Delaware** (6,906 test children, 593 material, 51 cells) | PASS 1.015 [0.979, 1.053] | **FAIL 0.0439 vs 0.0437** (0.075 no haircut) | PASS 94 % (3 of 51 outside) | **FAIL, by 0.0002** |
| **Midland** (5,805 test children, 733 material, 51 cells) | PASS 1.037 [0.994, 1.081] | PASS 0.0453 vs **0.0583** (0.074 no haircut) | PASS 92 % (4 of 51 outside) | **PASS** |

The two basins swapped. Read each honestly:

**Delaware.** P2 is a tie that fell on the wrong side of the line. The cell is pattern × the nearest parent's d_eff under the
*fitted* anisotropy, and revision 5 moved a_below from 0.91 to 1.49, so the stack-nearest children re-binned (above|400–800 ft
went from 26 to 71 children, above|800–1,200 from 115 to 140, and so on). Inside the revision-5 cells the incumbent ladder reads
0.0437 (0.0412 inside revision 4's) and the model 0.0439 (0.0406). The gap is 0.4 % of the RMS; revision 4's "pass" was a 1.4 %
gap the other way. Three revisions in a row the continuous model and the D113 ladder are within 1.5 % of each other on exposed
cells, with the sign set by the binning. The registered P2 has no resolution at this scale — a disclosure, not a re-score.
Meanwhile **oil cum-12 and cum-36, which failed P2 under revision 4, pass under revision 5** (cum-12: P1 1.043 [1.011, 1.077],
P2 0.0346 vs 0.0364, P3 92 %; cum-36: P1 0.998 [0.955, 1.039], P2 0.0457 vs 0.0468, P3 89 %). Gas cum-24 fails P1 (1.066) and
P2 as before — oil-fitted factor, never haircut by D113.

**Midland.** Passes the registered tests, with the tilt revision 4 found halved rather than removed: where material the factor
still cuts 3.7 % too deep (revision 4: 5.0 %) and the interval now covers 1; the unexposed test wells sit at 0.983 [0.959, 1.008]
against the applied level (revision 4: 0.971), i.e. the fitted level 1.067 is 1.7 % above what the unexposed test wells did
(1.058). By fold C8 reads 1.000 / 0.985 / 0.960 at the 2021 / 2022 / 2023 cutoffs — the later folds over-shoot more, because the
level fitted on the growing training set stays at 1.073–1.081 while the unexposed test wells came in flat to falling. A watch
item for step 23, not a failure under the registered rule.

Residual by parent count after the factor (test folds pooled, oil cum-24; residual = exp mean of l_mix − ln factor):

| parents | Delaware n | factor | residual | no haircut | incumbent | Midland n | factor | residual | no haircut | incumbent |
|---|---|---|---|---|---|---|---|---|---|---|
| 0 | 2,395 | 1.046 | 1.002 | 1.047 | 1.010 | 1,992 | 1.076 | 0.983 | 1.058 | 1.058 |
| 1 | 1,140 | 1.016 | 1.016 | 1.032 | 1.020 | 542 | 1.043 | 0.999 | 1.042 | 1.042 |
| 2 | 932 | 0.998 | 1.012 | 1.009 | 1.010 | 587 | 1.021 | 0.994 | 1.015 | 1.019 |
| 3 | 696 | 0.979 | 1.000 | 0.979 | 0.994 | 488 | 1.009 | 0.999 | 1.008 | 1.020 |
| 4+ | 1,743 | 0.923 | 0.997 | 0.920 | 0.988 | 2,196 | 0.929 | 1.007 | 0.935 | 0.987 |

Per bench group the Midland residual runs 0.960 (WCD) to 1.017 (LSSH) against an incumbent of 1.00–1.04 everywhere; the
Delaware 0.99–1.02 on every bench with n > 70.

## 2. The curve, the rule, the checks

**Delaware — contest (4,778 multi-parent children): R2 multiplicative wins outright again**, gain over R1 0.0024
[0.0007, 0.0040]; R3 0.0010 [−0.0003, 0.0022] and R4 0.0009 [−0.0004, 0.0022] do not separate. Folds picked R3, R3, R2 as in
revision 4. **Midland — unresolved → R3 by default**: R2 has the lowest RMS (0.3687 vs R1 0.3712) with a gain of 0.0025
[−0.0002, 0.0052] that misses zero by a hair; R3 and R4 sit on R1. Folds picked R3, R2, R3 (revision 4: R3 ×3).

| basin | rule | RMS | gain vs R1 (90 %) | F_min | d50 ft | k | a_below | a_above | level |
|---|---|---|---|---|---|---|---|---|---|
| Delaware | R1 worst-only | 0.3848 | — | 0.840 | 1,261 | 6.6 | 1.39 | 2.33 | 1.048 |
| Delaware | **R2 multiplicative** | **0.3825** | 0.0024 [0.0007, 0.0040] | **0.912** | **1,259** | **4.8** | **1.49** | **2.63** | **1.046** |
| Delaware | R3 per-side product | 0.3839 | 0.0010 [−0.0003, 0.0022] | 0.873 | 1,199 | 4.6 | 1.29 | 1.64 | 1.050 |
| Delaware | R4 drainage share | 0.3839 | 0.0009 [−0.0004, 0.0022] | 0.877 | 1,223 | 4.9 | 1.33 | 1.63 | 1.049 |
| Midland | R1 worst-only | 0.3712 | — | 0.662 | 744 | 2.6 | 1.16 | 0.82 | 1.069 |
| Midland | R2 multiplicative | 0.3687 | 0.0025 [−0.0002, 0.0052] | 0.896 | 925 | 4.0 | 1.20 | 1.11 | 1.057 |
| Midland | **R3 per-side product** (default) | **0.3712** | 0.0000 [−0.0019, 0.0019] | **0.720** | **485** | **2.0** | **0.50** | **0.50** | **1.067** |
| Midland | R4 drainage share | 0.3713 | −0.0002 [−0.0022, 0.0018] | 0.735 | 495 | 1.9 | 0.50 | 0.50 | 1.066 |

Level bands (200 refits): Delaware 1.046 [1.030, 1.060]; Midland 1.067 [1.047, 1.082]. The Delaware fitted level lands on
what revision 4's mix factor implied (1.043) — the control anchor was right there. The Midland's lands 2 % below revision 4's
implied 1.090, which is the whole of the Midland's improvement.

**Curves of record** (per-parent factor before the level; d = sideways gap, or vertical gap with the parent directly over /
under the child):

| basin | parent | 100 ft | 300 | 500 | 800 | 1,000 | 1,400 | 2,000 | 2,600 |
|---|---|---|---|---|---|---|---|---|---|
| Delaware R2 | same depth, sideways | 0.912 | 0.912 | 0.913 | 0.921 | 0.934 | 0.967 | 0.991 | 0.997 |
| Delaware R2 | below the child | 0.912 | 0.913 | 0.919 | 0.950 | 0.973 | 0.993 | 0.999 | 1.000 |
| Delaware R2 | above the child | 0.912 | 0.921 | 0.961 | 0.993 | 0.998 | 0.999 | 1.000 | 1.000 |
| Midland R3 | same depth, sideways | 0.732 | 0.798 | 0.864 | 0.923 | 0.945 | 0.969 | 0.983 | 0.990 |
| Midland R3 | below = above (a = 0.50) | 0.723 | 0.745 | 0.780 | 0.834 | 0.864 | 0.908 | 0.945 | 0.964 |

What moved on the Delaware between revisions 4 and 5 is the stack: a parent below now releases by ~800 ft of vertical gap
(revision 4: ~1,400 ft) and a parent above by ~500 ft as before. The sideways curve is the revision-4 curve to the third
decimal past 1,000 ft, slightly steeper near the floor (k 4.8 vs 3.6). The Midland is unchanged in shape: a vertical foot counts
half a sideways foot in both directions, both at the bound, severe and symmetric.

- **C2** surface holds in both basins with evidence: three curves are worse out of sample (Delaware −0.0014 [−0.0022, −0.0005];
  Midland −0.0037 [−0.0055, −0.0019]).
- **C1** reads FAIL by construction under a stacking rule, as at revision 4 (bins are the total effect, the curve is per parent).
  Delaware same-depth bins 0.772 / 0.871 / 0.900 / 0.980 / 1.015 (0–400 … 2,000–2,640 ft, n 70 / 282 / 1,057 / 774 / 568);
  Midland 0.764 / 0.806 / 0.869 / 0.926 / 0.978 (n 41 / 252 / 696 / 488 / 340) — the Midland sideways effect is deeper at every
  range. Midland stack bins 0.59–0.86 out to 1,000 ft on both sides; Delaware above-parent bins back at 0.96–1.04 by 500–800 ft.
- **C4** (Delaware, the 2022-12-01 fold common to all three horizons): F_min 0.862 / 0.881 / 0.888 and d50 1,272 / 1,354 / 1,351
  ft at cum-12 / 24 / 36 — slight easing with time, no reversal.
- **C3** Delaware: 13 bench pairs with n ≥ 30 outside ±10 %, signs mixed; the n > 100 one is BS3_S over a WCA_1 parent at 0.885
  (n 111) with its mirror WCA_1 over BS3_S at 0.892 (n 89) — the WCXY/WCA_1 landing seam, under-penalised both ways, where the
  D114 key and the ±150 ft "same" band disagree about what is a neighbour. WCA_1 over WCB_1 1.119 (n 68) is the barrier-below
  pair from revision 4, still over-penalised. Midland: WCA_1 over WCB_2 1.106 (n 75), WCB_2 / WCB_2 0.895 (68), WCD / WCD 0.835
  (42), LSSH over JM 1.120 (39), JM / JM 1.145 (39).
- **C5** Delaware: nearest parent's cum per kft 0–20 → ≥ 60 kbbl/kft: 0.903 → 0.985 → 0.999 → 1.078, monotone (n 359 / 1,587 /
  1,431 / 1,134), the revision-4 finding intact — rock quality read through the parent, the strongest structure left. Parent
  age 1.007 / 0.945 / 1.035 at 1–2 / 2–4 / ≥ 4 yr. Midland age 1.021 / 1.002 / 0.994 (flat; no parent-cum column in the 21a
  links).
- **C7** not produced.

## 3. Sticks (what-if, nothing stored) and oil

**Delaware.** 41,875 run-19 sticks carry ≥ 1 link; under R2 with level 1.046: mean factor 0.924 (capped 0.910); the 25,881
sticks with 3+ parents average 0.86 with 7,412 below 0.80; every one of the 6,181 linked-but-unexposed sticks sits above 1.00.

Joined to run 19's PUD oil (`docs/box/prox-2026-10-19/pud_outcomes.csv.gz`, 50,963 sticks, 29,560 MMbbl before any haircut;
the incumbent leaves 23,300 MMbbl, of which 5,423 MMbbl is the two no-forecast gates):

| population (incumbent outcome) | sticks | oil before | incumbent after | revision 5 | revision 4 |
|---|---|---|---|---|---|
| unexposed, as-is | 25,789 | 14,506 | 14,506 | **14,802** (+296; the 9,088 unlinked sticks held at 1.0 here — at the level they add **+231** more) | 14,940 (+434 / +327) |
| single parent, as-is | 6,980 | 3,845 | 3,845 | 3,714 (−131, −3.4 %) | 3,754 (−91) |
| multi-parent, haircut | 9,706 | 5,786 | 4,949 | 4,823 (−126, −2.5 %) | 4,896 (−53) |
| no forecast, precedent | 3,927 | 2,351 | 0 | (1,904 if forecast) | (1,891) |
| no forecast, package | 4,561 | 3,072 | 0 | (2,240 if forecast) | (2,184) |

With the incumbent precedent gates kept: **23,338 MMbbl, +0.2 % vs the incumbent; +1.2 % (≈ 23,569) once the unlinked
unexposed sticks carry the level too** (revision 4: +1.2 % / +2.6 %). Revision 5 is the more conservative Delaware answer:
the unexposed gain shrinks by a third, the singles and the haircut population each give up another ~2 %. The G4 geometry key
would forecast 6,576 of the 8,488 refused sticks (≈ 4,184 MMbbl) and refuse 1,649 the incumbent forecasts — the policy lever,
reported only, cards still to draw.

**Midland.** 27,051 of the 32,541 drillable sticks carry ≥ 1 link; 18,674 have 4+ parents (6,197 below 0.80). Under R3 with
level 1.067: mean factor 0.888 (capped 0.878). Against the 21b incumbent outcomes: the 11,134 incumbent-haircut sticks average
**0.840 under revision 5 vs 0.837 incumbent** — the same haircut, reached by a curve instead of a table; the 3,404 single-parent
sticks 0.958 (incumbent 1.0); the 8,312 linked unexposed 1.015 (5,959 more unlinked would carry 1.067); the 913 spacing-floor
sticks 0.642, the 2,221 pattern-refused 0.718, the 596 precedent-refused 0.845 — the curve agrees the floor and pattern gates
catch the worst-placed sticks. The G4 key would refuse 5,168 (3,109 of them incumbent-haircut) and forecast 2,213 of the 3,732
the incumbent refuses. No Midland stick oil exists yet (21c has not run), so no MMbbl comparison.

## 4. Read, for gate 24a

- **G1** adopt the surface — yes in both basins (C2, both with evidence).
- **G2** rule: Delaware R2 multiplicative, outright for the third time. Midland unresolved → R3 by the registered default; R2
  is 0.0002 from winning there too, and the 2022 fold chose it. If one rule per design is wanted, R2 in both is defensible and
  the Midland R2 curve (F_min 0.896, d50 925 ft, a ≈ 1.1–1.2) is the Delaware's shape with the stack anisotropy near 1.
- **G3** decided (revision 4): the uplift is carried, now as a fitted level: Delaware 1.046, Midland 1.067. The walkthrough
  sentence stands with smaller numbers on the Delaware: ≈ +530 MMbbl on the unexposed inventory once every unexposed stick
  carries it (+296 linked, +231 unlinked).
- **G4** incumbent gates kept by default; the geometry key is a ~4,200-MMbbl Delaware policy question with cards.
- **G5** no bench-pair offset; the WCXY/WCA_1 seam (0.885 / 0.892, n 200 both ways) joins WCA over WCB_1 as the pairs to look at
  if one is ever wanted. It is the same seam named at item 5 of the revision-2 walk-through.
- **G6** the Midland is scored on the same design and passes. Adopt at step 23 for both basins with a D116-style re-measure
  (sticks: every existing producer per each basin's rule; level per basin from that basin's fit).
- **The decision this leaves Michael:** the Delaware is a FAIL by the letter of P2 (0.0439 vs 0.0437) and a tie in substance,
  passing on cum-12 and cum-36 where revision 4 failed. The honest options: (a) adopt revision 5 as the one design in both
  basins, with the Delaware P2 stated as a tie that fell 0.4 % the wrong way; (b) keep revision 4 on the Delaware (its PASS)
  and revision 5 on the Midland — two designs, two freezes, the mix factor in one and the fitted level in the other, not
  recommended; (c) adopt nothing. A revision 6 that gives P2 a bootstrap interval would resolve the letter, but it would be
  the fourth design change after a score and would not change what the numbers say.
- **What this does not do:** it does not sharpen exposed cells beyond the ladder in either basin (Delaware tie; Midland 0.045
  vs 0.058 is real skill, but the 21b table is one revision old and interim); it does not replace precedent; it does not
  touch gas. What it does: one five-parameter curve plus a fitted level per basin, a factor for the single-parent sticks
  (6,980 Delaware, 3,404 Midland), the near end measured, a measured stack asymmetry (Delaware) or symmetry (Midland), no
  30-analog floor on the factor, and the unexposed uplift the ladder's `none` rung carried but D113 never applied.

## 5. Disclosed

Revision 5 was designed after the Midland revision-4 score (the fourth such change; the walk-forward is blind in time, not in
design, the 2c disclosure). Its predictions in `rev4/FINDINGS.md` §5 were: leave the Delaware where it is, pull the Midland's
floor up by ~3–5 %. Scored: the Delaware did **not** stay put — the joint fit on every scored child moved the stack anisotropy
(a_below 0.91 → 1.49), re-binned the cells and flipped the P2 sign; the Midland's over-cut moved 1.3 points (1.050 → 1.037),
less than predicted, with the level 2 % below the mix-implied one rather than 3–5 %. Both are misses against the stated
prediction and are recorded as such. The score is deterministic given the freeze; no card was drawn; the stick what-if applies
the level to linked sticks only (§3 states the remainder). Every number above was read after the one registered revision-5
score per basin.
