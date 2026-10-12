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
