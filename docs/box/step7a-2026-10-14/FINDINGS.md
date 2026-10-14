# BOX step 7a: the 2023-cutoff oil spread misses (D59 condition 2), gate 7a

**Built 2026-10-14. Read-only. No rule, spec or code of record changed.**
Review page: `spread.html`. Data: `packages_oil_holdout.csv` (one row per held-out package × horizon),
`spread_bootstrap.csv`, `spread_by_radius.csv`, `summary.json`.
Builders: `scripts/box_spread_diag.py` (re-runs the frozen scoring per cutoff and keeps the per-package frames;
~1.7 h for four cutoffs) and `scripts/box_spread_diag_report.py` (DB-free, < 1 min).

## 1. Set-up

- Frozen spec `box_v2_wf` (D58, code d5c3ebd; boxfit 3380317), D52 holdout view, actuals through 2026-07-01: the same
  inputs as the one-time scoring. Walk-forward haircuts came from the tuning cells only, as frozen.
- Code drift since the freeze: `dealintake/` gained the SWD dossier section (config v10 → v11, `swd:` block
  reported only and never used for selection). It doesn't touch the selection path.
- **Identity:** every recomputed cell for 2021, 2022, 2023 and 2024 equals the scored record
  (`cells_holdout_v2.csv`). Package and well counts are exact, and the largest difference on any statistic is
  1.1e-16. These are the scored packages, not a re-draw.
- Grain = development package (D53). Error = Σ actual / Σ forecast − 1 (negative = forecast HIGH).
  Spread = scale-free P10–P90 (D58) = band / (1 + bias).

## 2. Answer: mostly sample size; the BOX-specific part is a few Eddy packages that beat their analogs

**(a) The test can't resolve 0.05 at these package counts.** A package bootstrap (2,000 draws) of the spread
gap (BOX − benchmark) gives a 90 % interval about 0.25–0.40 wide in every judged holdout cell:

| cutoff | horizon | packages | BOX sf | bench sf | gap | gap 90 % CI | P(gap > 0.05) |
|---|---|---|---|---|---|---|---|
| 2021 | 12 | 83 | 0.787 | 0.796 | −0.008 | −0.124 … +0.139 | 27 % |
| 2021 | 24 | 83 | 0.719 | 0.716 | +0.003 | −0.120 … +0.130 | 25 % |
| 2022 | 12 | 75 | 0.638 | 0.687 | −0.049 | −0.201 … +0.104 | 14 % |
| 2022 | 24 | 75 | 0.641 | 0.772 | −0.131 | −0.229 … +0.073 | 9 % |
| **2023** | **12** | **60** | **0.863** | **0.649** | **+0.214** | **−0.081 … +0.316** | **67 %** |
| **2023** | **24** | **43** | **0.764** | **0.587** | **+0.176** | **−0.108 … +0.315** | **88 %** |
| 2024 | 12 | 46 | 0.779 | 0.810 | −0.031 | −0.178 … +0.237 | 26 % |

2023 is the high draw, and the interval still includes zero. BOX leans wider there, but at 40–60 packages that
can't be told apart from noise. The other cutoffs land between −0.13 and +0.00, so pooled over the holdout,
BOX's spread equals or beats the benchmark's.

**(b) Two to four packages decide the verdict.** At 60 packages, the P10 and P90 are the 6th package from each
end, so a handful of tail packages moves the band. Removing the most gap-widening packages one at a time:

- cum-12 (60): removing 1 package leaves a gap of +0.117 (FAIL); removing 2 leaves +0.045 (**PASS**).
- cum-24 (43): removing 3 leaves +0.128 (FAIL); removing 4 leaves +0.045 (**PASS**).

**(c) The hard packages are hard for both methods.** Package error correlates 0.87–0.93 between BOX and the
benchmark in every cell. The low tail (forecast HIGH) is shared:

- Devon Lea: −82 % and −97 % (benchmark −79 % and −97 %).
- Permian Resources Culberson: −63 % (benchmark −68 %).
- Chevron Culberson: −53 % (benchmark −55 %).

Those packages widen both spreads equally, so they don't move the gap.

**(d) The part that is BOX-specific is the upside tail: early-2024 Eddy (NM) completions that beat the analogs.**
BOX under-forecast these by 40–110 %, while the local-offsets benchmark caught part of the beat:

| package | operator | wells | analog radius | BOX error | bench error |
|---|---|---|---|---|---|
| 3001554142 | Permian Resources | 4 | 15 mi | +61 % | +15 % |
| 3001553795 | Devon (15,100 ft) | 2 | 5 mi | +51 % | +1 % |
| 4238940532 | Perun (Reeves, 7,126 ft, Cui translation) | 1 | 5 mi | +49 % | +8 % |
| 3001553426 | Mewbourne | 1 | 5 mi | +109 % | +64 % |

Mewbourne's eight 2023-cutoff packages average BOX +22 % against benchmark +15 %.

**There is a modest NM signal at cum-12 that runs past 2023.** Scale-free spread, NM packages versus TX:

| cutoff | NM packages | NM BOX / bench | TX packages | TX BOX / bench |
|---|---|---|---|---|
| 2021 | 39 | 0.81 / 0.82 | 44 | 0.70 / 0.77 |
| 2022 | 28 | 0.67 / 0.64 | 47 | 0.67 / 0.69 |
| 2023 | 28 | **0.92 / 0.60** | 32 | 0.70 / 0.67 |
| 2024 | 14 | 0.71 / 0.50 | 32 | 0.75 / 0.88 |
| pooled cum-12 | 109 | **0.84 / 0.72** | 155 | 0.77 / 0.82 |
| pooled cum-24 | 90 | 0.74 / 0.79 | 111 | 0.79 / 0.77 |

At cum-12, the NM spread from BOX has been wider than the local offsets' at every cutoff since 2022. The
newest NM vintages, mostly Eddy, beat their analogs more unevenly than the nearest offsets suggest. In TX, BOX
is tighter. By cum-24 the NM gap closes. It's the first year that varies, not the decline. Cells are small (14–28
NM packages), and the holdout is spent, so **any change to selection now would be tuning after the fact.**
Recommendation: a watch item for the prospective 2026 cohort (NM cum-12 spread, reported separately), and no
spec change.

**(e) The benchmark was not unusually tight.** FINDINGS §14 and D59 describe the miss as the benchmark being
"unusually tight" at 2023. On the same cutoff, the tuning view's spreads are BOX 0.686 and benchmark 0.688. On
the held-out 2023 packages, the benchmark moves only to 0.649, while BOX widens to 0.863. **Most of the gap is
BOX widening on the 60 held-out packages (+0.18), not the benchmark tightening (−0.04).** The raw-band numbers
recorded in D59 are correct; the explanation attached to them is wrong. This corrects that explanation, and
D59's decision stands.

## 3. The lesson that belongs in the workup (proposed text, for the gate)

The one systematic pattern across all cutoffs is that **spread grows with the analog radius reached.** It
grows for both methods, so this is local data density, not a defect in the method. Pooled over every judged
holdout cell:

| horizon | analog radius | packages | BOX bias | BOX sf | bench sf | 80 % of packages within (P90 … P10) |
|---|---|---|---|---|---|---|
| cum-12 | 5-mi ring | 190 | −1.0 % | 0.69 | 0.73 | −34 % … +35 % |
| cum-12 | past 5 mi | 74 | +2.8 % | 0.98 | 0.87 | −45 % … +56 % |
| cum-24 | 5-mi ring | 136 | +0.1 % | 0.70 | 0.77 | −32 % … +37 % |
| cum-24 | past 5 mi | 65 | +5.0 % | 0.84 | 0.84 | −40 % … +49 % |

**Proposed:** every workup states the radius its analog search reached, plus the measured package range for
that radius class. Example: "analogs found within 5 mi; on held-out ground, 80 % of comparable packages landed
within −34 % … +35 % of this method's 12-month oil". This would sit next to the D59 condition-3 statement
(measured bias by horizon plus the haircut applied).

This is disclosure only. It changes neither the forecast nor any rule. Past the ring, BOX's bias is still
within ±5 %; only the range is wider, and saying so is what makes the workup defensible.

## 4. Asks for gate 7a

1. **Accept the diagnosis.** The 2023 failures are sample-size-limited (the gap's CI includes zero, and the
   verdict flips on 2–4 packages). The BOX-specific part is a cluster of Eddy outperformers on top of a modest
   NM year-1 spread signal since the 2022 cutoff (§2d). Recommendation: no rule or spec change, consistent with
   D59, and NM cum-12 spread becomes a named watch item in the prospective 2026 read.
2. **Adopt the §3 radius-class range statement** in every workup, built in 7c. Recommendation: yes.
3. **Record the §2(e) correction** in the plan Status line. D59's decision is unchanged.
4. **Flag, for your call:** the D59 prospective confirmation (2026 cohort) is to be scored under the same frozen
   rules, including the spread test. At the package counts a single cohort year gives (≈ 40–80 held-out-sized
   cells), the spread test has a ±0.15–0.20 resolution against a 0.05 tolerance. Either keep it as written and
   read a spread FAIL there knowing this, or decide now, before any 2026 data exist, to report the spread with
   its bootstrap interval. Changing it later would be tuning after the fact. No recommendation; it's an owner's
   call on the record.
