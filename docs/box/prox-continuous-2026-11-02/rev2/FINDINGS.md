# BOX step 24 — continuous proximity factor: FINDINGS (Delaware, scored 2026-11-02 at the frozen SHA)

Scored once, as registered: `python -m scripts.box_prox_cont run --basin delaware --boot 1000`, frozen SHA
`7ce61fb640c83d73242608dd5567772f06e04c4f` (§11), definition digest `87b3f603`. Inputs = the step-2 frame (14,545 harness children,
3,971 controls) and `runs/prox/links.pkl`; outputs beside this file (`summary_delaware.json` is the record). The Midland is not
scored. Nothing stored; run 19 untouched.

## 1. Verdict — FAIL (oil cum-24): P1 fail, P2 pass, P3 fail

| test | result | number |
|---|---|---|
| P1 calibration where material (F_applied ≤ 0.90, 367 test children) | **FAIL** | residual 0.939 [0.889, 0.992]; the band is [0.95, 1.05] and the interval misses 1.00 |
| P2 skill (53 cells ≥ 30 children) | PASS | cell RMS 0.071 vs 0.098 with no haircut vs **0.077 with the incumbent D113 ladder** |
| P3 cell calibration | **FAIL** | 68 % of cells within ±10 % (needs 80 %) |
| C8 unexposed test children (2,395) | — | 0.991 [0.969, 1.014], below 1 in every fold: **the §5 cap costs nothing (G3 closes: keep it)** |

Other horizons, reported only: cum-12 P1 pass / P2 fail (loses to the incumbent, 0.075 vs 0.072) / P3 fail; cum-36 P1 fail
(0.81 on 52 children); gas cum-24 P1 pass / P2 fail / P3 fail. Nothing passes.

**The direction of the miss is one-sided.** Residuals below 1 everywhere a parent is close mean the factor is **too mild**, not
wrong-shaped. Test children by parent count (oil cum-24, test folds pooled):

| parents | n | factor applied | residual after it | no haircut | incumbent ladder |
|---|---|---|---|---|---|
| 0 | 2,395 | 1.000 | 0.991 | 0.991 | 0.955 |
| 1 | 1,140 | 0.991 | 0.981 | 0.973 | 0.961 |
| 2 | 932 | 0.981 | 0.975 | 0.956 | 0.957 |
| 3 | 696 | 0.970 | 0.951 | 0.922 | 0.936 |
| 4+ | 1,743 | 0.940 | 0.915 | 0.858 | 0.921 |

A four-plus-parent child needs ~0.86; the curve gives it 0.94. The incumbent gives 0.92 and is better calibrated there, which
is why P2 is a narrow pass and P1 fails.

## 2. Why: the registered design fits the curve where there is no signal

§2 fits the single-neighbour curve on children with **exactly one** depleting parent. In the Delaware those children are far
from their parent by construction — a child with a close same-depth parent on one side is in a developed section and almost
always has other parents too:

| nearest same-depth parent | 0–400 ft | 400–800 | 800–1,400 | 1,400–2,000 | 2,000–2,640 |
|---|---|---|---|---|---|
| single-parent children (stage A) | **9** | 45 | 182 | 239 | 355 |
| children with 4+ parents | 110 | 260 | 498 | 165 | 14 |

So stage A (830 children) sees 54 children inside 800 ft and fits F_min = 0.954, d50 = 1,461 ft, k pinned at the 8.0 bound: a
step from 0.95 to 1.00 near 1,400 ft, with no information below it (band at 300 ft: [0.86, 1.00]). Stage B is worse: 33
children below, 36 above (dh ≤ 400 ft). Check C2 is uninformative (gain 0.000 [−0.003, +0.003]) and the surface "passes" by
absence of evidence; a_above sits at its 0.5 bound.

The step-2 dose table, which took every exposed child's WORST parent (8,818 children), had the near end: 161 children at
0–400 ft at **0.80**, 594 at 400–800 at 0.87, 1,698 at 800–1,400 at 0.90, flattening by 1,400–2,000. That signal is real and
it lives in the multi-parent children this design set aside for the contest.

**The contest confirms it from the other side.** On 1,454 two-parent children the four rules are indistinguishable (RMS
0.3826 / 0.3823 / 0.3822 / 0.3822; no gain over R1 excludes zero; R3 by default). The free regression says why: β_nearer =
1.96, β_farther = −0.36 overall (flanked, n = 67: 4.2 / 2.2). A coefficient of ~2 on ln F_nearer means the data want roughly
twice the log-haircut the curve assigns to the nearest parent. With a curve this mild the rules cannot be told apart, because
they differ only in how they combine a correction that is itself too small.

## 3. What else the score says

- **C4 horizon.** F_min 0.939 / 0.954 / 0.964 at cum-12 / 24 / 36, d50 1,388 / 1,461 / 1,252 ft: flat with time, all mild for
  the reason in §2.
- **Parent below at long range.** Cells `below|2000–2400` (n = 103) and `below|1200–1600` (n = 135) sit at 0.87–0.90 after a
  factor of ~1.0. A parent 2,000 ft sideways and a bench deeper is not interference; a child drilled ABOVE an existing producer
  is a later-vintage topfill in a developed section, and its bench-group controls do not share that setting. This is the
  exposure-correlates-with-setting confound, visible here because the factor removes nothing at that range. Step 2 saw the
  same (topfill "outside v14" at 0.87). Worth a named check in any revision; not a distance effect.
- **C1.** Same side 3 of 4 populated bins inside the band (75 %, below the 80 % rule); the stack sides have no bin with 30
  children. The 0–400 bin has 9 children.
- **C3 / C5 / C7** not produced by this run (the script writes the fit, contest, validation and stick files; the bench-pair,
  parent-age and Pad C 233 tables are a report-step gap to close with the revision, not a scoring defect).
- **Sticks (G4 and the what-if).** 41,875 run-19 sticks carry at least one link; mean factor 0.970 (uncapped 0.977), 8 % below
  0.90, 3+-parent sticks at 0.955 on average. The incumbent haircut averaged 0.855 on its 9,706 sticks. Read with §1: this
  what-if is **not credible as a replacement** — it is the mild curve applied 41,875 times. The G4 geometry key would refuse
  3,038 of the 41,875 (every side pattern has ≥ 30 drilled children; 2nd-percentile nearest d_eff from 31 ft for
  `left+right+above` to 595 ft for `below`), against the incumbent's 8,488 — reported only, as registered.

## 4. Recommendation (for gate 24a; a design change = revision 3 + a re-score on the same folds)

Keep the model and the contest; change **what the curve is fitted on**. Two candidates, both honest under the §4 walk-forward
(fitting stays on training folds):

- **(a) joint fit on every exposed child.** Fit (F_min, d50, k, a_below, a_above) by least squares of `l_rel` on
  ln F_rule(all parents) with the rule fixed (R3 by default), then re-run the contest with each rule carrying its own jointly
  fitted curve. Uses ~8,800 children instead of 1,803 and puts the near end where the data are. The contest becomes a fair
  comparison of rule + curve pairs.
- **(b) worst-parent dose** for stage A (the step-2 definition: every exposed child, its nearest parent in d_eff), the contest
  unchanged. Simpler; it reproduces the step-2 bins by construction and tests whether the second parent adds anything.

I would register (a) with (b) reported as the comparison. Either way disclose that the revision was designed after this score:
the walk-forward stays blind in time, not in design (the 2c disclosure, again). G3 is settled by C8 (cap kept). G1 / G2 / G4 /
G5 wait for the re-score. The Midland should not be scored on the registered design: the same thinness applies and its
single-parent counts will be smaller.

## 5. Disclosed

Everything above was read after the one registered score. No parameter, population or rule was changed and nothing was
re-run. The stick-side what-if and the G4 counts were read; no card was drawn (the 20 cards wait for a design that passes).
