# BOX step 24 — continuous proximity factor, both basins: PRE-REGISTRATION (DRAFT for Michael's review)

Written 2026-11-02 from the brainstorm of the same day (Michael: score the neighbours a stick actually has, not the class it
falls in; a sigmoid in distance; lateral first, then stack; one pooled relationship applied whatever the bench). **Status:
DRAFT.** Nothing here is frozen. The commit Michael accepts becomes the pre-registration timestamp and gate 24a stamps its SHA
in §11; from then on nothing below changes after a score is seen without a dated row in the revision table saying why.
"Step 24" is a proposed slot (22 folded into 21, 23 = production); the plan assigns the number.

**What this step is.** A replacement for the D113 configuration haircut: a factor that is a *function of each neighbour's
distance* rather than a lookup by class × count × flank per bench pair, plus a pre-registered test of how neighbours combine.
It is measured on the drilled children both basins already hold, validated walk-forward the 2c way, and applied to the sticks
as a reported what-if. **It changes no record.** Run 19 (Delaware) and the Midland path through 21c keep D112–D116 and the 21a
revisions until a later gate adopts this.

**What it is not.** Not a precedent rule. "How much does this spacing hurt" (this step) and "do operators drill this" (D114,
the 21a pattern precedent, the 400-ft floor) stay separate questions; §6 reports what a geometry-keyed precedent would do to the
no-forecast population, and that is a gate question, not a result of this step.

## Revisions (before any score)

| date | change | why |
|---|---|---|
| 2026-11-02 | draft for review | — |
| 2026-11-02 (revision 1, before acceptance) | §7 check C8 added (walk-forward residual on UNEXPOSED test children, the evidence G3 waits on); §9 rewritten with registered defaults: G2 tie-break = R3 per-side product, G3 cap kept in v1, G4 incumbent precedent kept (geometry key reported, cards drawn), G5 no bench-pair offset, G6 score now, adopt at step 23 for both basins | Michael, 2026-11-02 gate-question review: "i agree" to the six defaults as recommended |

## 0. Disclosed before this file (what has been read)

- **Delaware, in-sample over ALL folds** (`docs/box/prox-2026-10-19/`, steps 2 / 2b / 2c): the worst-parent dose tables by class
  × horizontal bin and class × vertical bin, the parent cum / age bins, the configuration ladder, the D113 table, and the 2c
  walk-forward verdict. The brainstorm quoted them (same-bench cum-24: 0.80 / 0.87 / 0.90 / 0.98 / 1.00 across 0–400 / 400–800 /
  800–1,400 / 1,400–2,000 / 2,000–2,640 ft; parent below ~0.78–0.84 flat to 800 ft, releasing at 800–1,000; parent above milder
  and noisier). **The functional form, the 150-ft same-depth band, the universe and the candidate combination rules in this file
  were chosen after seeing those tables.** The Delaware test is therefore walk-forward in TIME, not blind in DESIGN (as 2c said
  of itself). The D52 Delaware holdout blocks were already used in steps 2 / 2b and are not a separate test here.
- **Midland, tuning only** (`docs/box/step21b-2026-11-01/`): the 21b D113-style factor table on 11,203 tuning children (1,793
  multi-parent, 1,449 scored at cum-24). No Midland dose-by-distance table has been built. **The D52 Midland holdout blocks are
  unread and stay unread here** (salt `box-holdout-2026-10-13`, 20 %, 3-mi blocks): every Midland statistic in this step is on
  tuning children only.
- Step 6 (`docs/box/step6-2026-10-12/`): the 3-D spacing prototype (`box/spacing3d.py`) and its PPML backtest — the Voronoi
  cross-section was ×0.99–1.01 per SD once nearest spacing and parent depletion were in, the whole term worth ~1.5 of a ~9–10
  pt cum-24 miss, and a narrower gate predicted better. Read as: the near neighbour carries the signal, the halo does not.

## 1. Data (nothing new measured against the warehouse)

| item | Delaware | Midland |
|---|---|---|
| children | the step-2 frame: 14,545 harness children (`runs/prox/children.pkl`, `docs/box/prox-2026-10-19/dose_children.csv.gz`) | the 21b frame: 11,203 TUNING children (`docs/box/step21b-2026-11-01/prox_children.csv.gz`; cache `runs/step21a`) |
| as-of prediction | `box_v2` harness views at the fold cutoff (Dec 1 before first production; the child is never its own analog) | `mid_r2` views, same construction (21b, frozen SHA 5ceadc2) |
| pair table | `runs/prox/links.pkl` (step 1: every co-extent link, child → older-or-codev well) | `runs/step21a/links.pkl` (21a, sha256 in `score_meta.json`) |
| stick side (§6) | `runs/prox/pud_links.pkl` (run 19's 50,963 sticks) | `runs/step21a/pud_links.pkl` (32,541 drillable sticks, revision 2) |
| actuals | as stored in the frames (the step-2 and 21b pins) | through 2026-08-01 (21a pin) |

The pair metric is D112 unchanged (`box/prox_study.links_for_child`): `overlap` = share of the child's lateral the parent
spans, `dh_ft` = median gap over the shared span, `dz_ft` = parent TVD − child TVD (> 0 = parent DEEPER = parent below the
child), `dxy_ft` = signed side (+ = parent left of the child's heading), `age_days`. The frames carry per-child `l_<metric>` =
ln(actual / as-of prediction), clipped to ln 0.1 … ln 10.

**Parent, for the drilled side:** a well ≥ 365 days on production at the child's first production (D112's "depleting
parent"), ≥ 30 % alongside. Co-developed wells (|age| ≤ 180 d) are normal development, never a dose (the control definition of
step 2). Young parents (180–365 d) are reported, never a dose, never control. **Permit-round TVDs (rule 10) are excluded from the
drilled side** as in step 2. **No shielding exemption on either side** — a difference from step 2's exposure screen, disclosed:
under every rule in §3 a shielded parent is farther in d_eff and counts less, so the rule handles it instead of a flag (D115
already counts every producer on the stick side).

**Side of a parent, by depth not tag (21a revision 3, applied to BOTH basins here):** |dz| ≤ 150 ft → *same*; dz > 150 ft →
*below*; dz < −150 ft → *above*. A difference from the step-2 Delaware frame, which classed by bench pool (D42); disclosed. The
child's own BOX bench still picks its prediction and its normalisation cell.

**Normalisation (the prox_dose convention, not 2c's):** `l_rel` = l − mean l over the CONTROL children of the same (bench
group, cutoff); a cell with < 10 controls falls back to the bench group, then to all controls of the basin. Control = no
depleting, young, permit or shielded parent inside 1,000 ft vertically / 2,640 ft horizontally. This makes F(∞) = 1 mean "an
unexposed well of the same bench and vintage" — the physical reading. §5 states how that maps onto BOX's mix-calibrated level.

**Metric:** oil cum-24 primary, as D113. Oil cum-12 / cum-36 and gas cum-24 are fitted and reported, never judged (§7 C4).

**Universe of a dose:** parents inside |dz| ≤ 1,000 ft and dh ≤ 2,640 ft (step 2's exposure envelope). Beyond it F = 1 by
construction. Basins are fitted separately throughout; benches are pooled within a basin.

## 2. The single-neighbour model (lateral first, then stack, then one surface)

**Effective distance.** For a parent at (dh, dz) on side s ∈ {same, below, above}:

    d_eff = sqrt(dh² + (a_s · dz)²),   a_same ≡ 0 (within the 150-ft band depth is ignored), a_below, a_above fitted.

**Factor.** A three-parameter log-logistic in d_eff, monotone by construction, F → 1 as d_eff → ∞:

    F(d) = F_min + (1 − F_min) / (1 + (d50 / d)^k)

F_min = the floor at zero distance, d50 = the distance of half recovery, k = the steepness. Bounds: F_min ∈ [0.3, 1.0],
d50 ∈ [100, 3,000] ft, k ∈ [0.5, 8], a_s ∈ [0.5, 6]. Michael's shoulder at 1,400–1,600 ft is a prior, not a constraint.

**Fitting, in three stages (each stage's parameters are frozen before the next):**

| stage | children | fits | what it answers |
|---|---|---|---|
| A — lateral | exactly one depleting parent, side *same* | F_min, d50, k of F_h(dh) | the lateral_closer curve |
| B — stack | exactly one depleting parent, side *below* or *above*, dh ≤ 400 ft | F_below(dv), F_above(dv), each its own (F_min, d50, k) | stack_below vs stack_above, separately |
| C — surface | exactly one depleting parent, any (dh, dz) in the universe | a_below, a_above, with (F_min, d50, k) held at stage A | whether the stack curves are the lateral curve stretched, i.e. whether ONE surface in d_eff serves (check C2) |

Fit = nonlinear least squares of `l_rel` on ln F per child, bounded, scipy `least_squares`. Children are correlated within
packages and areas, so every interval is a **3-mi block bootstrap** (`box.dev_factor.blocks`, 1,000 draws, seed 20261102), the
control normalisation re-estimated inside each draw, parameters re-fitted per draw. Reported per stage: the point fit, the
P5–P95 band of F(d) on a 100-ft grid, n, and the step-2 bins overlaid (check C1).

**Why single-parent children define the curve:** the two-parent children are reserved for §3, where they TEST a combination
rule instead of fitting a second relationship — Michael's "one piece at a time".

**Shielding, same side:** two parents on the same side of the child, the nearer between the child and the farther, is the
case every rule in §3 must state. The single-parent stages never see it.

## 3. The combination rule — a pre-registered contest, not an assumption

Population: children with **exactly two** depleting parents in the universe (both basins, pooled within basin). With the §2
surface frozen, each parent has F_i = F(d_eff,i). Four candidate rules, each a function of the parents a child has:

| rule | F_child for two parents | two parents each at a "0.8 distance" | shielding (same side) |
|---|---|---|---|
| R1 worst-only (prox_dose's exposure) | min(F_1, F_2) | 0.80 | native (only the nearest counts) |
| R2 multiplicative, all parents | F_1 · F_2 | 0.64 | counts both |
| R3 per-side product | Π over sides {left, right, above, below} of the NEAREST parent's F on that side | 0.64 flanked, 0.80 same-side | native |
| R4 drainage share (1-D Voronoi) | mean over sides of F on that side (unbounded side = 1), left/right from `dxy_ft`, above/below from dz | 0.60 flanked, 0.80 same-side | native |

R2 is Michael's "0.64 makes sense"; R3 is the same thing with shielding built in; R4 is the geometric reading (each neighbour
takes half the rock between it and the child). R1 is the incumbent exposure definition.

**Scoring:** residual `r = l_rel − ln F_rule` per child; statistic = RMS of r over the two-parent children, with a 90 % block
bootstrap interval of the DIFFERENCE from R1 (same draws for every rule). Also reported: the free regression
`l_rel = β1 ln F_nearer + β2 ln F_farther` (β ≈ (1, 0) says R1, (1, 1) says R2, in between says saturating), by flanked vs
same-side.

**Decision rule (per basin, then reconciled):** the rule with the lowest RMS wins **when its improvement over R1 excludes zero
at 90 %**; otherwise **R3 wins by default** (Michael's stated prior that crowding never helps, with shielding, and the one
that generalises to 3+ parents without a new assumption). The chosen rule is applied unchanged to 3+ parents. If the two
basins pick different rules, each keeps its own and §7 C6 says whether the difference is outside the bootstrap.

**A fifth candidate, conditional:** a 2-D Voronoi share in the (dh, a·dz) plane bounded at d_sat (the d_eff where F = 0.99),
mapped back to an equivalent single-parent distance so F_single applies. It enters the contest **only if C2 passes** (one
surface), because its construction needs it; otherwise it is dropped and said so.

## 4. Walk-forward validation (the 2c rule, re-used)

Per basin. Fit the §2 surface and apply the §3 rule on children of strictly earlier cutoffs; test on fold c.

| horizon | test cutoffs |
|---|---|
| oil cum-24 (primary) | 2021-12, 2022-12, 2023-12 |
| oil cum-12 | 2021–2024 |
| oil cum-36 | 2021, 2022 |
| gas cum-24 | 2021–2023 |

Residual of a test child `r = l_rel − ln F_applied`; `r0 = l_rel` (factor 1); `r_inc = l_rel − ln f_incumbent` where the
incumbent is the D113 ladder (Delaware) / the 21b Midland table, fitted on the same training children.

- **P1 — calibration where it matters.** Test children with F_applied ≤ 0.90: PASS if exp(mean r) ∈ [0.95, 1.05] or its 90 %
  block-bootstrap interval contains 1.00.
- **P2 — skill.** Cells = side pattern × 400-ft d_eff bin of the nearest parent, cells with ≥ 30 test children. PASS if the
  n-weighted RMS of the cell means of r is below the same RMS for r0 AND below it for r_inc. (Beating "no haircut" is not
  enough; it must beat the table it would replace.)
- **P3 — cell calibration.** PASS if ≥ 80 % of the P2 cells have |exp(mean r) − 1| ≤ 0.10.

**VERDICT = P1 AND P2 AND P3, per basin**, oil cum-24, test folds pooled, 1,000 block-bootstrap draws, seed 20261102. Other
horizons and gas are reported, never gate. Midland test folds use tuning children only.

## 5. Level: control-relative F onto a mix-calibrated forecast

BOX's level is calibrated on every scored well, exposed ones included (D58 / the walk-forward haircut), so a factor relative to
*unexposed* wells cannot be multiplied on as-is without penalising exposed sticks twice. Define per (basin, bench group)
`F_mix` = exp(mean ln F_rule over its scored drilled children). The factor applied to a stick is

    factor = F_rule(stick) / F_mix,   capped at 1.0 (D113: unexposed and lightly exposed sticks stay at BOX as-is)

The uncapped version (unexposed sticks get the ~1.04 "none" uplift 2c measured) is reported beside it. **Whether to lift the
cap is gate question G3**, not a result.

## 6. Stick side — reported what-if, nothing stored

For every stick of both populations (§1), every producer existing at the data date is a candidate parent (Delaware: ≥ 12 months
on, D112; Midland: any age, revision 4 — each basin's rule of record), d_eff per parent, F per the chosen rule, factor per §5.
Reported, per basin and per BOX bench:

- sticks by {unexposed, single parent, 2, 3+} × {factor ≥ 0.95, 0.90–0.95, 0.80–0.90, < 0.80}; oil before / after vs the
  incumbent (run 19's D116 measurement; 21a's revision-5 table);
- the single-parent sticks specifically (Delaware: 6,980 sticks, 3,845 MMbbl at as-is today): what the curve gives them;
- the no-forecast populations under the incumbent gates (Delaware 3,927 precedent + 4,561 package; Midland per
  `prox_revision1.csv`), unchanged by this step, with the factor they WOULD carry;
- **G4 candidate, geometry-keyed precedent (reported only):** a stick has precedent when ≥ 30 drilled children of its basin
  share its side pattern (same / below / above present, flanked or not) AND its nearest d_eff is ≥ the 2nd percentile of those
  children's nearest d_eff. The 21a 400-ft same-bench floor (revision 5) and the D145 conflict exclusion apply regardless.
  Sticks that move between forecast / no forecast under G4 vs the incumbent are counted and 20 are drawn as cards for Michael
  (the step-21a card format: own tag + proposed + adjacent bands, strike section, verdict accept / reject).

## 7. Named checks (reported with the verdict; none of them gates)

- **C1 bins within band.** ≥ 80 % of the step-2 bins (and the same bins built on the Midland) with ≥ 30 children lie inside
  the fitted curve's P5–P95 band.
- **C2 one surface.** Stage-B curves vs stage-A stretched by a_s: if the separate-curve fit's RMS improvement over the single
  surface excludes zero at 90 %, the surface FAILS; the step then carries three curves (F_h, F_below, F_above), each side's
  parent scored on its own curve, the §3 rule unchanged, the 2-D Voronoi candidate dropped. Expected from the Delaware bins:
  the *below* curve is flat to ~800 ft and may not be a stretch of the lateral curve.
- **C3 bench-pair residuals.** For child-bench × parent-bench pairs with ≥ 30 children, exp(mean r) under the chosen rule;
  pairs outside ±10 % are named. Expected: pairs that straddle a frac barrier (a gate question, G5, whether to carry a
  bench-pair offset — not fitted here).
- **C4 horizon.** F_min, d50 at cum-12 / cum-24 / cum-36: whether the haircut deepens, holds or recovers with time (the D106
  reversal guard's question for a proximity factor).
- **C5 parent age / cum.** Residual r by parent age (1–2 / 2–4 / ≥ 4 yr) and parent cum per kft bins; step 2's bins were
  non-monotone, so the expectation is noise, stated as such.
- **C6 basins.** Delaware vs Midland (F_min, d50, k, a_s, chosen rule) with bootstrap intervals: whether one relationship could
  serve both (the pooling Michael asked about, one level up).
- **C7 Pad C 233** (21a revision 6): the 15 sticks' factors under this model beside the 21b Midland factor and the interim
  Delaware factor; reported, never judged.
- **C8 the unexposed level (the evidence G3 waits on).** Walk-forward (§4 folds), test children with F_applied = 1 under the
  §5 cap: exp(mean r) per fold and pooled, 90 % block-bootstrap interval. If it sits above 1.00 in every test fold and the
  pooled interval excludes 1.00, the "none" uplift is real and G3 reopens with that evidence; if the interval contains 1.00,
  the cap costs nothing and stays. Expected from 2c: ~1.04 against the mix. Reported per basin.

## 8. Decisions of record this step touches, and what happens to each

| decision | here |
|---|---|
| D112 pair metric, envelopes | metric unchanged; envelopes replaced by the universe + d_eff (gate 24a) |
| D113 option (a): multi-parent only, cum-24, oil | horizon and stream kept; "multi-parent only" replaced by the curve (single parents get F; §5 cap keeps unexposed as-is) — gate 24a |
| D114 two-tier precedent, 21a pattern precedent, revision-5 floor | untouched; G4 reported only |
| D115 every producer, no shielding exemption (stick side) | kept; extended to the drilled side (§1) |
| D116 derived record, re-measured per run | kept; adoption = a re-measure of run 19 (Delaware) and the Midland record at step 23 |
| gunbarrel sign rule v2 (rule 16) | `dxy_ft` sides are relative to the child's heading, not the v2 frame; used only to tell left from right, never persisted |

## 9. Gate 24a — the questions this step hands Michael, with the defaults registered 2026-11-02 (revision 1)

Each default holds unless the named evidence moves it; a change at the gate is a dated decision in the plan, not a re-fit.

- **G1** adopt the §2 surface, or the three curves if C2 fails, in place of the class envelopes. **Default: whatever C2 says.**
  Three curves is a legitimate outcome of the step, not a failure of it (expected from the Delaware bins: a parent below
  holds ~0.78–0.84 to 800 ft, a plateau rather than a stretched lateral curve).
- **G2** adopt the §3 winning rule. **Default on a tie: R3 per-side product** (crowding never helps; shielding native; extends
  to 3+ parents with no new assumption). R4 drainage share is the more punitive tie-break and has a survivorship argument;
  it is adopted only when it wins the contest outright.
- **G3** lift the §5 cap. **Default: cap kept in v1**; the uncapped number is reported. Lifting it raises every unexposed
  stick (~25,800 Delaware sticks, ~+3–4 %, order +500 MMbbl — more than the single-parent haircut removes), so the record's
  oil would rise and most of the inventory would sit above BOX's own calibrated level. G3 reopens only on C8's evidence.
- **G4** re-key precedent on geometry (§6). **Default: the incumbent precedent stays** (D114 bench pair + package tier on the
  Delaware; 21a pattern precedent + 400-ft floor on the Midland); the geometry key is reported with its moved-stick counts and
  20 cards. Precedent is the one guard against survivorship, and the per-bench reading of operator behaviour is the owner's
  policy (21a revisions 1 / 5). If the cards read drillable, the half-step to propose is the geometry key on the *mixed* rung
  only, where the incumbent is weakest.
- **G5** carry a bench-pair offset where C3 names one. **Default: no.** An offset per pair is the class table returning with
  its 30-analog floor. Carried only for a pair with ≥ 30 children, outside the bootstrap, and a physical reason (a known frac
  barrier); otherwise C3 stays a reported diagnostic.
- **G6** schedule. **Default: score now, adopt at step 23 for both basins.** The step touches no record; Midland fitting on
  tuning children cannot contaminate the 21c holdout. Adoption waits for step 23's one record run (D130) so the Delaware stays
  on run 19 until the Midland record is ready to price (D144, one re-price for Steven, not a third) and both basins carry one
  proximity method at one SHA.

## 10. Code (written AFTER Michael's acceptance, before any score; frozen with the SHA)

- `box/prox_cont.py` — pure, DB-free: `d_eff`, `F`, the stage A/B/C fits, the four rules, the walk-forward scorer, the stick
  application; a `DEFINITION` dict digest-pinned by `tests/test_box_prox_cont.py` (the step-21 pattern); golden tests on a
  synthetic gunbarrel (a child with one parent at known (dh, dz) → known d_eff; two parents → each rule's F by hand).
- `scripts/box_prox_cont.py` — reads the §1 caches and views only (no warehouse); writes
  `docs/box/prox-continuous-2026-11-02/` (`fit_<basin>.csv`, `rules_<basin>.csv`, `validate_<basin>.csv`,
  `sticks_<basin>.csv.gz`, `checks.json`, `index.html`, `FINDINGS.md`). Delaware ~5 min, Midland ~3 min, bootstrap ~20 min.
- Nothing in `sql/`, nothing in `box.*`, no apply script. Effort ≈ 2 sessions (fit + contest + validation; stick side + cards).

## 11. Frozen SHA

Stamped at gate 24a: `<sha>` (the commit that adds `box/prox_cont.DEFINITION` and its test). A run whose `box/` or
`scripts/` frozen files differ from it is not a score.
