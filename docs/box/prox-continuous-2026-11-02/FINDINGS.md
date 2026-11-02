# BOX step 24 — continuous proximity factor: FINDINGS of record (Delaware, revision 4, scored 2026-11-02)

Scored once at the revision-4 freeze `55810294a5b77c00536b80e803b1ca12d7b09685` (§11; definition digest `8b76b94e`), 1,000-draw
bootstrap, the same folds and rows as revisions 2 and 3. Revision 4 changed one thing: the §5 cap is lifted (G3), so unexposed
sticks carry the `none` uplift. Earlier scores: `rev2/` (single-parent fit, FAIL), `rev3/` (joint fit, cap kept, P2 FAIL through
the capped unexposed cell). Inputs = the step-2 frame (14,545 harness children, 3,971 controls, 6,581 exposed, 4,778 with ≥ 2
parents) and `runs/prox/links.pkl`. Nothing stored; run 19 untouched; Midland unscored. `summary_delaware.json` is the record.

## 1. Verdict — PASS on oil cum-24 (the registered metric)

| test | result | number |
|---|---|---|
| P1 calibration where material (F_applied ≤ 0.90, 600 test children) | **PASS** | 1.018 [0.980, 1.055] |
| P2 skill (51 cells ≥ 30 children) | **PASS** | cell RMS **0.0406** vs 0.076 no haircut vs **0.0412 incumbent D113 ladder** |
| P3 cell calibration | **PASS** | 90 % of cells within ±10 % (5 of 51 outside) |
| C8 unexposed test children (2,395) | uplift carried | 1.004 [0.982, 1.027] in r; mean factor 1.043 |

Read P2 honestly: 0.0406 against 0.0412 is a tie in substance. Without the `none` cell it is 0.0514 against 0.0518 — the
continuous model is as sharp as the ladder on exposed cells and no sharper. Its case is coverage and form (§4), not sharper cells.

Residual by parent count after the factor (test folds pooled, oil cum-24):

| parents | n | factor applied | residual | no haircut | incumbent |
|---|---|---|---|---|---|
| 0 | 2,395 | 1.043 | 1.004 | 1.047 | 1.010 |
| 1 | 1,140 | 1.015 | 1.017 | 1.032 | 1.020 |
| 2 | 932 | 0.999 | 1.012 | 1.009 | 1.010 |
| 3 | 696 | 0.980 | 1.001 | 0.979 | 0.994 |
| 4+ | 1,743 | 0.924 | 0.999 | 0.920 | 0.988 |

Other horizons, reported never judged: oil cum-12 P1 pass, P2 0.041 vs 0.039 incumbent (fail), P3 pass; cum-36 P1 pass, P2
0.049 vs 0.049 (fail at the fourth decimal), P3 pass; gas cum-24 P1 1.082 (fail), P2 fail, P3 fail — the factor is fitted on
oil and D113 never haircut gas; gas needs its own fit if it is ever wanted.

## 2. The curve, the rule, the checks (unchanged from revision 3 — the fit does not see the cap)

**Contest (4,778 multi-parent children): R2 multiplicative wins outright**, gain over R1 0.0030 [0.0012, 0.0047]; R3 / R4 do
not separate from R1. Per walk-forward fold the training contest picked R3, R3, R2.

| rule | RMS | gain vs R1 | 90 % | F_min | d50 ft | a_below | a_above |
|---|---|---|---|---|---|---|---|
| R1 worst-only (= the step-2 dose) | 0.4010 | — | — | 0.795 | 1,019 | 0.50 | 2.50 |
| **R2 multiplicative** | **0.3981** | 0.0030 | [0.0012, 0.0047] | **0.908** | **1,188** | **0.91** | **2.97** |
| R3 per-side product | 0.4003 | 0.0007 | [−0.0007, 0.0021] | 0.837 | 950 | 0.50 | 1.70 |
| R4 drainage share | 0.4004 | 0.0006 | [−0.0009, 0.0021] | 0.843 | 968 | 0.50 | 1.67 |

**The curve of record (R2, one surface, oil cum-24):** F_min 0.908, d50 1,188 ft, k 3.6, a_below 0.91, a_above 2.97.

| parent | 100 ft | 300 | 500 | 800 | 1,000 | 1,400 | 2,000 | 2,600 |
|---|---|---|---|---|---|---|---|---|
| same depth, sideways | 0.908 | 0.909 | 0.912 | 0.926 | 0.940 | 0.967 | 0.988 | 0.995 |
| below the child, vertical gap | 0.908 | 0.909 | 0.911 | 0.922 | 0.934 | 0.960 | 0.984 | 0.993 |
| above the child, vertical gap | 0.909 | 0.932 | 0.972 | 0.993 | 0.997 | 0.999 | 1.000 | 1.000 |

A parent below counts nearly 1:1 with sideways distance and releases slowly; a parent above is ~3× farther per foot and is gone
by ~500 ft. Per-parent floor 0.91 under R2 because the rule stacks parents; the worst-parent curve (R1) floors at 0.795 and
matches the step-2 bins (0.765 / 0.871 / 0.906 / 0.977 / 1.014 at 0–400 … 2,000–2,640 ft on every exposed child's nearest
parent). Bands ±0.03 at the floor, ±0.01 past 1,000 ft (200 refits).

- **C2** surface holds with evidence: the three-curve form is worse out of sample (−0.003 [−0.005, −0.002]).
- **C1** reads FAIL by construction under R2 (bins are the total effect, the R2 curve is per parent); like-for-like on R1 it
  holds. A later revision should state C1 on the rule's total prediction per bin.
- **C4** F_min 0.899 / 0.908 / 0.921, d50 1,233 / 1,188 / 1,380 ft at cum-12 / 24 / 36: no reversal, slight easing with time.
- **C3** 14 bench pairs with ≥ 36 children outside ±10 %, signs mixed, most inside the 2-σ band (±11 % at n ≈ 50); the one
  with a story and n = 141 is WCA_1 / WCA_2 over a WCB_1 parent at 1.10–1.14 (over-penalised: a barrier below the WCA).
- **C5** nearest parent's cum per kft 0–20 → ≥ 60 kbbl/kft: 0.916 → 0.996 → 1.016 → 1.092, monotone (n 356 / 1,594 / 1,428 /
  1,133). Rock quality read through the parent, a level covariate; the strongest structure left in the residuals.
- **C7** not produced (Pad C 233 is Midland).

## 3. Sticks (what-if, nothing stored) and oil

41,875 run-19 sticks carry ≥ 1 link. Under R2 uncapped: mean factor 0.932; the 24,881 sticks with 3+ parents average 0.858,
7,513 of them below 0.80; the 6,181 linked-but-unexposed sticks carry 1.03–1.14 (= 1 / F_mix of their bench; F_mix runs 0.88
on BS3_C to 0.976 on WCD).

Joined to run 19's PUD oil (`docs/box/prox-2026-10-19/pud_outcomes.csv.gz`, 50,963 sticks, 29,560 MMbbl before any haircut;
the incumbent leaves 23,300 MMbbl, of which 5,423 MMbbl is the two no-forecast gates):

| population (incumbent outcome) | sticks | oil before | incumbent after | revision 4 |
|---|---|---|---|---|
| unexposed, as-is | 25,789 | 14,506 | 14,506 | **14,940** (+434; the 9,088 sticks with no link at all are held at 1.0 here — applied, they add **+327** more) |
| single parent, as-is | 6,980 | 3,845 | 3,845 | 3,754 (−91) |
| multi-parent, haircut | 9,706 | 5,786 | 4,949 | 4,896 (−53) |
| no forecast, precedent | 3,927 | 2,351 | 0 | (1,891 if forecast) |
| no forecast, package | 4,561 | 3,072 | 0 | (2,184 if forecast) |

With the incumbent precedent gates kept: **23,590 MMbbl, +1.2 % vs the incumbent; +2.6 % (≈ 23,917) once the unlinked
unexposed sticks carry their uplift too.** The multi-parent haircut population is within 1 % of the incumbent; the single-parent
sticks lose 2.4 %; the unexposed inventory gains ~5 %. The G4 geometry key would forecast 6,310 of the 8,488 refused sticks
(≈ 4,070 MMbbl) and refuse 1,702 the incumbent forecasts — the policy lever, reported only, 20 cards still to draw.

## 4. Read, for gate 24a

- **G1** adopt the surface — yes (C2).
- **G2** adopt R2 multiplicative — the registered winner, outright on the full set; R3 twice in the folds with gains that do
  not separate. Either is defensible; R2 is what the data pick when every parent is in the fit.
- **G3** decided (revision 4): the uplift is carried. Cost stated: ≈ +760 MMbbl on the unexposed Delaware inventory once
  applied to every unexposed stick (+434 linked, +327 unlinked) — BOX forecasts its unexposed sticks ~5 % above a level that
  was calibrated on a mix carrying spacing damage. That is the walkthrough sentence.
- **G4** incumbent gates kept by default; the geometry key is a ~4,000-MMbbl policy question with cards.
- **G5** no bench-pair offset; WCA over WCB_1 is the one pair worth a look if a barrier term is ever wanted.
- **G6** score the Midland on this design (tuning children only; no design change pending); adopt at step 23 for both basins
  with a D116-style re-measure (sticks: every existing producer per each basin's rule, F_mix per bench from that basin's fit).
- **What this does not do:** it does not sharpen exposed cells beyond the ladder; it does not replace precedent; it does not
  touch gas. What it does: one five-parameter curve for 214 keys, a factor for the 6,980 single-parent sticks, the near end
  measured from 6,581 children, a measured stack asymmetry, no 30-analog floor on the factor, and the unexposed uplift the
  ladder's `none` rung already carried but D113 never applied.

## 5. Disclosed

Revision 3 (joint fit, mix-normalised residual) and revision 4 (cap lifted) were both designed after a score — the walk-forward
is blind in time, not in design, the 2c disclosure. The revision-4 score is deterministic given revision 3's; its numbers were
predicted in `rev3/FINDINGS.md` §1 and matched. The stick what-if applies the uplift to linked sticks only (a script limit, §3
states the remainder). No card was drawn. Every number above was read after the one registered revision-4 score.
