# BOX pre-9b — rehearsing the 9b holdout rule on tuning data (read-only)

Michael 2026-10-16, after gate 9a: test whether the 9b rules are informative BEFORE the one-time holdout is spent.
Review surface: `index.html`. Built by `python -m scripts.box_rehearse9b` (`box/rehearse9b.py`, DB-free) from the step-9a tuning frames in
`runs/box9a/` (BS2_S box_v2_wf under D94; WCXY raw box_v2 on the D93 pool under D97). It draws 2,000 random 20 % subsets of 3-mi blocks of
the TUNING packages, which is the D52 holdout's shape. No holdout well was read. Nothing stored.

## 1. The rule as written cannot judge the BS2_S / WCXY holdouts

At holdout size a per-cutoff cell holds 16–25 BS2_S packages and 5–14 WCXY packages, while D53 judges only from 30.
- Median cells judged: 0 on both benches.
- `acceptance.verdict` reads "nothing judged" as FAIL, so 9b would fail both benches by construction.
- WCA's holdout had 43–60 packages per cutoff; these benches' holdouts are 3–4× smaller.

## 2. What each candidate rule does (pass rate over draws)

"Good" = the forecast is as good as in tuning; "10 % high" / "15 % high" = predictions deliberately scaled up.

| rule | good (BS2_S / WCXY) | 10 % high | 15 % high |
|---|---|---|---|
| as written: per cutoff, bias + spread | 4 % / 0 % | 1 % / 0 % | 0 % / 0 % |
| pooled across cutoffs, bias + spread | 16 % / 17 % | 3 % / 1 % | 0 % / 0 % |
| pooled, bias only (±10 %) | 50 % / 49 % | 8 % / 2 % | 1 % / 0 % |
| **pooled, consistent with tuning** (each cell inside its P2.5–P97.5 interval) | **87 % / 85 %** | 39 % / 23 % | 14 % / 3 % |

At holdout size (60–90 packages) a single pooled cell's bias swings about ±8 pts (P5–P95) around its tuning value.
A fixed ±10 % test on that bias is therefore a coin flip for a good forecast, and the spread test passes a good forecast only 60–90 % of the time per cell.

## 3. Proposed D99 (Michael's call, before 9b)

**Scoring.** Each bench's holdout is scored POOLED across cutoffs, per stream × horizon:
- BS2_S: oil + gas at cum-12 and cum-24 (cum-36 reaches 30 packages in 0.3 % of draws);
- WCXY: oil + gas at cum-12, 24 and 36.

**Pass rule.** A bench passes when every cell's holdout package bias lies inside its FROZEN interval
(`intervals_BS2_S.csv`, `intervals_WCXY_WCA1.csv`): the holdout is consistent with tuning, so the tuning bias is the disclosed bias (D59 cond. 3).
|bias| ≤ 10 % and the scale-free spread are reported per cell, not gating. A FAIL means diagnose (7a pattern), never re-tune.

**Scope.** WCA (D58 / D59) and the prospective 2026 test (D70) are unchanged.

**Caveat.** The rule asks "is the holdout different from tuning?", not "is it within ±10 %?". WCXY's tuning oil cum-36 bias is −9.2 %, near the
tolerance; it would be stated on every WCXY workup.

| frozen interval | BS2_S | WCXY |
|---|---|---|
| oil cum-12 | −10.8 … +9.1 % | −9.2 … +7.2 % |
| oil cum-24 | −9.3 … +16.0 % | −13.6 … +3.4 % |
| oil cum-36 | — | −18.7 … +0.3 % |
| gas cum-12 | −17.8 … +3.1 % | −10.3 … +10.4 % |
| gas cum-24 | −18.2 … +8.3 % | −13.1 … +8.1 % |
| gas cum-36 | — | −14.9 … +4.3 % |
