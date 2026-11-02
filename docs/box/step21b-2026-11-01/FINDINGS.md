# BOX step 21b — Midland tuning-fold scoring (2026-11-01, re-run at revision 8 2026-11-02) — GATE 21b CLOSED (D149)

> **GATE 21b CLOSED 2026-11-02 (D149): Michael accepted every recommendation in §1** ("Accept all recs"). Record treatment as in the Q1 table with **LSSH moved to `mid_r2p`**; D99 `cf13af17…` and water `64e592b5…` frozen; Midland proximity table, no nearest-gap rung; no pattern-package gate; water provisional Midland-wide; revision 8 kept. Decision file: `GATE_21B.json`. Next: 21c (one-time holdout at `5ceadc2`) on Michael's go. The text below is the gate as presented.

Read-only. Nothing stored, no DDL, no record flip; the Delaware record stays on run 19 (D144) and nothing here reads or writes
the Delaware. Branch `claude/box-step21b-tuning`. The contract is the FROZEN pre-registration
(`docs/box/step21a-2026-10-31/PREREGISTRATION.md` + `box/step21.DEFINITION`) at **revision 8**: digest `9780f326`, frozen SHA
**`5ceadc2`** (D148, amends D147; revision 7 at `501d799` is superseded, its tuning outputs kept in `rev7/`).
**Tuning packages only: the D52 holdout packages are dropped before any statistic and only counted (21a `package_counts.csv`).
No holdout bias, error or forecast was read, at revision 7 or 8.**

- **Review surface:** `index.html` (summary, pooled oil-bias dot plots with the frozen intervals, the proximity tables, per-group
  sections, long laterals, §9, water, Pad C 233, run records).
- **Frozen at this gate (revision 8):** `frozen_d99.csv` sha256 **`cf13af179754c0cc2d1dac9fa6755c50aa275df74c2b43564c410665aa1e7d03`**;
  `frozen_water.csv` sha256 **`64e592b5326852d01de811352d5d57282d506397b51d80070e62d17f856c8ff9`** (canonical LF text, `%.12g`;
  the second full scorer run reproduced both byte for byte). Revision 7's `b50bcb71` / `5db6aeca` were never frozen.
- **Builder:** `python -m scripts.box_step21b runs | score | water | pad`, then `python -m scripts.box_step21b_render`;
  revision 7 vs 8 = `python -m scripts.box_step21b_rev8_compare` (→ `rev8_vs_rev7/`).
- Grain is stated per table: packages (D53), wells, or sticks. **Bias = Σ actual / Σ forecast − 1: negative = BOX over-forecasts.**

## 0. Revision 8 as run — what it did, against what I told you it would do

**The code does what you approved.** Well by well, against the revision-7 runs:
- **Raw `mid_r2` months.** For the 3,654 scored wells at or shorter than their cohort's mean lateral, the months are
  bit-identical to revision 7.
- **The 7,549 longer wells** each moved by one scalar, the Delaware-panel lateral multiplier: the month-to-month spread of
  new / old is ≤ 4.4e-16.
- **The twins.** `mid_r2_lin` and `mid_r2_cuide` are unchanged (max |diff| 0). `lat_ratio` is unchanged.

**But the realized level gain is about a third of what I projected.** The §8 diagnostic spliced the two revision-7 twins.
The harness then re-fits each variant's calendar factor F(k) on its seeded 500-well training sample (`box/acceptance`,
frozen behaviour since step 9). The Delaware panel lowers the long training wells' predictions, so F(k) rises 0.4–1.9 % per
cutoff and lifts every prediction, short targets included. The diagnostic didn't model that refit. That's my miss: the
"pooled −4.8 → −3.3 %" quoted in the revision-8 row and D148 was a projection. Realized
(`rev8_vs_rev7/`, raw `mid_r2` oil, tuning packages):

| oil bias, cum-12 / 24 / 36 | revision 7 (Midland panel) | revision 8 projected | **revision 8 realized** |
|---|---|---|---|
| pooled, all lengths (4,059 / 3,373 / 2,531 pkgs) | −4.8 / −4.8 / −6.2 % | −3.3 / −3.4 / −4.8 % | **−4.3 / −4.3 / −5.7 %** |
| < 7,500 ft (the diagnostic's "5,000–7,500" class; 95 wells < 5,000) | −2.7 / −3.0 / −5.7 % | −2.7 / −3.0 / −5.7 % | **−4.5 / −4.9 / −7.5 %** |
| 7,500–10,000 ft | −2.6 / −4.1 / −6.4 % | −2.4 / −3.9 / −6.1 % | **−3.7 / −5.1 / −7.3 %** |
| 10,000–12,500 ft | −4.2 / −4.6 / −5.5 % | −3.4 / −3.8 / −4.6 % | **−4.2 / −4.6 / −5.4 %** |
| 12,500–15,000 ft | −6.3 / −6.5 / −7.6 % | −2.8 / −2.8 / −3.7 % | **−3.3 / −3.4 / −4.3 %** |
| 15,000–17,500 ft | −12.6 / −10.8 / −10.9 % | −6.7 / −4.7 / −4.7 % | **−7.2 / −5.2 / −5.3 %** |
| stick-weighted class spread (PUD mix) | 2.2 / 1.7 / 1.2 pt | 1.0 / 0.5 / 0.6 pt | **0.8 / 0.5 / 0.9 pt** |
| stick-weighted ≥ 15,000 ft | −13.7 / −12.0 / −11.4 % | −7.4 / −5.5 / −4.7 % | **−7.9 / −6.0 / −5.3 %** |

**Read.** The shape fix is real. Long laterals are about 5–6 pt better, the class spread on the PUD mix is down to roughly a
third, and the length effect is now mostly gone. The level isn't fixed. F(k) re-levels the predictions, so revision 8 mostly
moves error between length classes: short targets are 1–2 pt worse, long ones 3–6 pt better. The general ~−4 % over-forecast
is what the record treatments (proximity factor, walk-forward) were always there to address. After them, the record moves
0.3–1.1 pt toward zero on most groups (§1 Q1). **Rec: keep revision 8 as run.** Reverting would be a second post-score change
for a smaller long-lateral disclosure problem, and the holdout still tests it.

## 1. Gate 21b — your calls (recommendation first)

1. **Record treatment per group (§5).** The "rule" column applies the rule (scored walk-forward holdout ≥ 30 at cum-12 AND
   cum-24), then the D106 guard per stream. Every rule pick and every D106 decision is the same as at revision 7. At this
   gate you may move a group from `mid_r2p_wf` to `mid_r2p`, or to provisional (never the other way, never after a holdout look).

   | group | rule → after D106 | tuning oil bias cum-12 / 24 / 36 (record) | alternative oil | rec |
   |---|---|---|---|---|
   | WCA_1 | wf → **wf oil / r2p gas** (gas g(48) 1.41) | −1.2 / −1.1 / +0.3 % | r2p −2.3 / −2.7 / −4.6 % | **keep** |
   | WCB_1 | wf → **wf oil / r2p gas** (gas g(48) 1.21) | +3.0 / +3.8 / +1.0 % | r2p −1.4 / −2.0 / −4.2 % | **keep** |
   | LSSH | wf → **wf** | −6.2 / −5.7 / −9.9 % (all PASS; cum-36 by 0.1 pt) | r2p **−2.2 / −3.2 / −2.5 %** (all PASS) | **move to `mid_r2p`** |
   | MS | wf → **wf** | −4.1 / −4.3 / −1.5 % | r2p −4.2 / −7.0 / −7.8 % (all PASS now) | **keep** |
   | JM | wf → **r2p both streams** (oil g(48) 1.98, gas 1.52) | +3.7 / **+13.0 / +16.9 %** (cum-24 / 36 FAIL) | — (wf refused) | **keep** (early cutoffs, below) |
   | WCB_2 | r2p (wf holdout 41 / **29.7** < 30) | −6.2 / −8.9 / −13.0 % (cum-36 not a D99 cell) | — | keep |
   | WCD | r2p (20 / 10) | −7.4 / −7.7 / −10.3 %; gas cum-24 +11.8 % FAILS (gas cum-12 now passes) | — | keep |
   | DEAN | r2p (24 / 9) | −1.8 / +0.6 / −3.7 % (cum-24 fails on spread, not level); **gas cum-24 +26.0 %** (FAILS) | — | keep, flagged |
   | WCC | r2p, **no D99 cell** → provisional by construction | −8.4 / −16.3 / −21.7 % | — | provisional (as registered) |

   - **LSSH: rec unchanged, reason restated.** Revision 8 lifted LSSH's walk-forward cum-36 from −10.1 % (FAIL) to −9.9 %
     (PASS by 0.1 pt). The walk-forward haircut (oil D62 factors 0.978 / 0.968 / 0.975 / 0.944) still makes every oil horizon
     worse than no haircut, by 4.0 / 2.5 / 7.4 pt. `mid_r2p` is the better forecast; the pass is a tenth of a point.
   - **JM — keep `mid_r2p`.** The pooled +13.0 % at cum-24 comes from the early cutoffs. Oil cum-24 package bias by cutoff:
     - 2019 **+72 %** (39 pkgs, median +49 %)
     - 2020 +18 %
     - 2021 +5 %
     - 2022 −4 %
     - 2023 +4 %

     Without 2019 the pooled cum-24 is **+4.5 %**. The walk-forward factor (1.04 / 1.13 / 1.17 / 1.41; > 1 is a RAISE) pools
     every cutoff, so it would inflate today's JM forecast by 13–41 % to fix a miss the recent cutoffs no longer show. D106
     refuses it (median g(48) 1.98), correctly. Disclose the per-cutoff lines (D105 style), not the pooled figure alone.
   - **DEAN gas** cum-24 +26.0 % has the same shape. By cutoff:
     - 2019 **+135 %** (20 pkgs, median +150 %)
     - 2020 +3 %
     - 2021 +30 % (median +11 %)
     - 2022 +9 %
     - 2023 +1 %

     Without 2019 the pooled cum-24 is +10.3 %. Keep it, disclose per cutoff, let D99 judge.
   - **WCA_1 gas.** Cum-36 under-forecasts by +14.7 % (FAIL) under `mid_r2p` gas, because D106 refused the gas walk-forward.
     Oil is clean, so keep it and disclose. Same reasoning, smaller miss, on the secondary stream.

2. **Freeze the D99 intervals as drawn — rec: yes** (`frozen_d99.csv`, sha256 above). The file carries the record treatment
   AND the alternative per group, so a move at Q1 needs no redraw (LSSH's `mid_r2p` rows are there). A move to provisional
   just leaves that group's rows unused. Pass rates (a forecast as good as tuning passes / a ±15 % miss is caught):

   | | WCA_1 | WCB_1 | WCB_2 | WCD | MS | JM | LSSH | DEAN |
   |---|---|---|---|---|---|---|---|---|
   | good forecast passes | 0.83 | 0.83 | 0.87 | 0.88 | 0.82 | 0.82 | 0.81 | 0.86 |
   | catches +15 % / −15 % | 1.00 / 1.00 | 1.00 / 1.00 | 0.98 / 1.00 | **0.62 / 0.80** | 0.92 / 0.98 | 0.94 / 0.98 | 1.00 / 1.00 | 0.83 / 0.91 |

   WCD's test is weak: it catches a 15 % high miss only 62 % of the time. That's disclosure for 21c, not a change.

3. **Proximity factor table (§4) — rec: adopt the Midland table as fitted, with no nearest-gap rung.**
   - **Fit.** 11,203 Midland tuning children in the scored views: 1,793 multi-parent of 21a's 1,884 (the harness dropped the
     rest at early cutoffs), 1,449 of them with a scored oil cum-24. Production's lookup (your §4 answer): k2 class × count ×
     flank → k3 → k4, multi-parent only. Every class reaches a usable k4, so **no stick is unfit**.
   - **Revision 8 barely touches it.** The 45 usable keys move by −0.009…+0.010 (median −0.0005), and no key changes
     usability.
   - **Outcomes.** Unchanged: 32,541 sticks, identical class by class. Only factors move. The median haircut lightens
     **0.777 → 0.798** vs the interim table.

   The five cards you flagged as too light:

   | card | stick | config | your note | interim (Delaware) | **Midland** (rung, n) | nearest-gap sensitivity |
   |---|---|---|---|---|---|---|
   | 9 | LSSH 1570956 | topfill, 3 | "hard to believe 0.74" | 0.748 | **0.762** (k2 topfill\|3+\|F) | 0.784 (dv300-800\|dh<800) |
   | 11 | WCB_1 1536795 | underfill, 4 | "hard to believe 0.94" | 0.940 | **0.913** (k4 underfill; k2 / k3 < 30) | — (no supported band) |
   | 12 | JM 1602030 | topfill, 2 | "hard to believe 0.96" | 0.856 | **0.908** (k2 topfill\|2\|F) | 0.948 |
   | 33 | DEAN 1617415 | mixed, 4 | "extremely aggressive" | 0.777 | **0.798** (k2 mixed\|4+) | — |
   | 45 | WCB_1 1571061 | same, 2 (533 / 1,145 ft) | "haircut seems light" | 0.923 | **0.831** (k2 same\|2\|F) | 0.826 (dh400-800) |

   - **Read.** The Midland children agree with you on #45 (0.92 → 0.83) and partly on #11. They read lighter than the interim
     on #9, #12 and #33. On cards 9 and 33 you said "worse"; the Midland data say about as bad as the Delaware did, slightly
     better.
   - **Nearest-gap rung: not supported.**
     - Only 4 of 22 gap keys reach 30 children (`prox_factor_table_gap_sensitivity.csv`).
     - Each class has at most one populated band, except same\|2: dh 400–800 ft 0.826 vs 800–1,400 ft 0.858, a 3-pt dose.
     - No card moves by more than 0.04.
     - The Delaware single-pair dose (0.80 → 0.98 over 0–2,000 ft) doesn't reproduce at the Midland's sample sizes.
   - **Where the lever is.** If the cards' "much worse" is the target, this table isn't it. The levers are the spacing floor
     (rev 5, 400 ft) or the precedent rules, and those are 21a decisions.

4. **Pattern-package gate (21a Q6) — rec: don't gate; keep it reported.**
   - 2,294 haircut sticks have a pattern package count < 30.
   - D114's package rule applied to the pattern (factor ≤ 0.80 AND packages < 30) would refuse **837** more on the interim
     table and **788** on the Midland table. Both counts are unchanged at revision 8.
   - The same evidence that leaves card 33 at 0.80 would remove about 790 sticks' forecasts. That's a population decision,
     not a factor one.

5. **Water (§7) — mechanical result: provisional on every Midland group** (unchanged at revision 8).
   - **The rule.** Validated water needs every judged tuning cell to pass. 3 of 22 judged cells pass (WCA_1 cum-12 / 36,
     WCB_2 cum-36).
   - **The miss.** The D107 ratio **under-forecasts** water on measured packages by +16 to +46 % on six groups, about 1 pt
     more than at revision 7, because raw oil moved:

     | group | water bias cum-12 / 24 / 36 |
     |---|---|
     | JM | +43 / +46 / +40 % |
     | MS | +38 / +32 / +29 % |
     | DEAN | +32 / +29 % |
     | LSSH | +25 / +21 / +23 % |
     | WCD | +24 / +29 % |
     | WCB_1 | +16 / +20 / +24 % |

     WCA_1 reads +8 to +11 %. WCB_2 is the only one high (−6 to −10 %).
   - **Reach and concentration.** Reach is fine: median 5–7.5 mi on the big benches, and no vendor fallback except 1 DEAN
     target. But **the top operator holds a median 58–77 % of each target's 10 nearest measured analogs**.
   - **Rec.** Accept water as provisional Midland-wide (that's the rule, not a choice). Still score the water holdout once at
     21c as registered. After 21c, open a separate read-only diagnosis of two questions: whether the sql/41 Texas `measured`
     label is genuine in the Midland, and operator concentration. No re-tune.

6. **Long laterals (§8, reported, never judged) — inform the step-23 disclosure.** Pooled over the nine groups (oil;
   revision-8 record `mid_r2` / linear twin / Delaware-panel twin; the scorer's classes):

   | completed lateral | pkgs cum-12 | cum-12 | cum-24 | cum-36 |
   |---|---|---|---|---|
   | 7,500–10,000 ft | 1,520 | −3.7 / −2.1 / −4.2 % | −5.1 / −3.6 / −5.5 % | −7.3 / −6.1 / −7.5 % |
   | 10,000–12,500 ft | 1,993 | −4.2 / −4.4 / −3.8 % | −4.5 / −4.9 / −4.1 % | −5.3 / −5.8 / −4.8 % |
   | 12,500–15,000 ft | 669 | −3.3 / −6.7 / −2.8 % | −3.4 / −6.9 / −2.8 % | −4.3 / −8.2 / −3.7 % |
   | **15,000–17,500 ft** | 504 | **−7.2** / −13.1 / −6.7 % | **−5.2** / −11.3 / −4.6 % | **−5.3** / −11.6 / −4.6 % |
   | 17,500–20,000 ft | 32 | −12.0 / −21.0 / −11.4 % | (10 pkgs) | (5 pkgs) |

   - 25.3 % of scored wells are > 12,500 ft, and 11.4 % are > 15,000 ft (past the Midland panel's last point).
   - By mismatch: targets ≥ 1.25× their cohort's mean lateral now miss −4.2 / −3.3 / −4.4 % (revision 7: −8.7 / −7.7 /
     −8.6 %). Targets < 0.8× read +1.3 / +1.4 / −2.1 % (revision 7: +3.2 / +3.3 / −0.1 %).
   - **For step 23:** the > 15,000-ft disclosure is now about 5–7 %, not 11–13 %.

7. **Revision 8 itself — rec: keep it as run** (§0). Your "yes" was given on a projected pooled gain of 1.5 pt. Realized, it's
   0.5 pt pooled, with the long-lateral and class-spread fix intact. **Alternative:** revert to revision 7. That's a second
   post-score change, and it brings the 11–13 % long-lateral miss back.

## 2. What ran (every run on the frozen files)

| group | started → finished (UTC, 2026-11-02) | branch HEAD | box/ scripts/ dealintake/ vs 5ceadc2 at start / end | scored tuning wells |
|---|---|---|---|---|
| MID_LSSH | 02:56 → 05:34 | 92a4abb | identical / identical | 2,597 |
| MID_WCB_1 | 02:56 → 05:34 | 92a4abb | identical / identical | 2,072 |
| MID_WCA_1 | 02:56 → 05:51 | 92a4abb | identical / identical | 2,946 |
| MID_WCB_2 | 05:34 → 07:11 | 92a4abb | identical / identical | 575 |
| MID_JM | 05:34 → 06:52 | 92a4abb | identical / identical | 973 |
| MID_MS | 05:51 → 07:21 | 92a4abb | identical / identical | 866 |
| MID_WCD | 06:52 → 07:31 | 92a4abb | identical / identical | 496 |
| MID_DEAN | 07:11 → 07:53 | 92a4abb | identical / identical | 560 |
| MID_WCC | 07:21 → 07:52 | 92a4abb | identical / identical | 118 |
| MID_WCC (plain §10 command) | 07:31 → 07:59 | 92a4abb | identical / identical | — (the proof run) |

- **Run records.** Each run's `run.json` records:
  - HEAD (92a4abb = the freeze commit 5ceadc2 plus the docs-only stamp of the frozen SHA);
  - the frozen check at start and end (changed = none);
  - the nightly state (idle: the 2026-11-01 run finished 18:32 UTC; the 11-02 cron is 11:15 UTC);
  - the definition digest `9780f326`;
  - rc 0.

  Engine `boxfit` 3380317 throughout. The scorer refuses any group whose run isn't rc 0 and identical at both ends.
- **The `mid_r2` months observer** (`scripts/box_step21b_harness.py`). The frozen harness doesn't save `mid_r2` monthly
  volumes, which the walk-forward / D106 guard need. The wrapper records them as the frozen harness computes them and changes
  nothing. **Proof, re-run at revision 8:** the plain §10 command on MID_WCC and the observed run are identical on all 10
  outputs. The per-well F(k) recovered from the views agrees to ≤ 6.9e-16. Harness cells vs the scorer's re-derivation agree
  to ≤ 8.9e-16 on every group.
- **Revision 7 history.** The revision-7 runs (2026-11-01, 501d799, including the Windows restart at 22:59 UTC that killed
  and re-ran MS / WCB_2 / WCD) are superseded. Their tuning outputs are in `rev7/`; the run directories were kept locally
  (`runs/step21b_r7`) for the identity check in §0.
- **Proximity caches.** Proximity links reuse the 21a revision-7 caches (sha256 in `score_meta.json`; revision 8 doesn't
  touch them). A re-decision of all 32,541 sticks under the interim table reproduces 21a's `sticks.csv.gz` with 0 differences.

## 3. Proximity detail (`prox_factor_table.csv`, `sticks_midland_table.csv.gz`)

- **Applied rungs** (k2 / k3 / k4): 12 / 12 / 5 usable keys of 19 / 13 / 5.
  - k2 same\|3+, topfill\|3+\|S and underfill\|2–3+ fall to k3 or k4.
  - k1 bench pairs are fitted, never applied: 16 of 150 usable. LSSH>topfill>WCA\|3+ 0.714 (n 68).
- **Midland haircut median by group** (interim → Midland):
  - WCA_1 0.795 → 0.812
  - LSSH / JM / DEAN 0.777 → 0.798
  - MS 0.748 → 0.762
  - WCB_1 / WCB_2 0.918 → 0.913

  Factor keys on sticks (all outcomes): k2 13,087, k3 825, k4 914.
- **Sensitivities.** `mid_r2p_de` (the Delaware D113 table on the same children) and `mid_r2p_gap` (the gap-rung sensitivity)
  are scored beside the record in `pooled.csv`. The Delaware table moves no pooled verdict. At revision 8 the gap rung moves
  none either: MS oil cum-36 now passes without it.
- **DEAN (D143), sticks:**
  - loop addition 1,047 = haircut 179 (median 0.798) / as-is 511 / no forecast 357 (pattern 195, precedent 92, spacing 70);
  - generated body 280 = haircut 12 / as-is 212 / no forecast 56.

## 4. Water detail (`water_cells.csv`, `water_intervals.csv`, `water_reach.csv`, `frozen_water.csv`)

- **Method.** D107 ratio on raw `mid_r2` oil, measured-water packages, D109 thresholds (|bias| ≤ 20 % AND scale-free
  band ≤ local-offsets benchmark + 0.10, ≥ 30 packages). Water intervals use `box/water11` / `rehearse9b.consistency` as built
  (2,000 draws, seed 5).
- **Not judged:** WCC (14 packages), WCD cum-36 and DEAN cum-36. WCC's water interval is degenerate, so it's in the frozen
  file for completeness only.
- **Sensitivity.** `ratio_actoil` (the ratio on ACTUAL oil) is reported beside it; its |bias| is larger in every judged cell.

## 5. §9 reports (never judged)

- **Thin control** (< 3 modern local wells in 3 mi; `thin_control.csv`): 1,822 of 7,586 oil package counts (cum-12 + cum-24
  summed over groups). WCA_1 thin reads −12.5 / −7.0 % (`mid_r2` cum-12 / 24) vs −4.0 / −5.1 % with control. Elsewhere the
  sign is mixed.
- **Edges** (within 5 mi of the extent, by compass side, oil cum-24; `edge_regions.csv`):
  - The big benches' interiors are within ±5 %, except JM (+19.2 %) and WCB_2 (−13.3 %).
  - Edge cells hold 5–38 packages. The largest misses:
    - WCA_1 S edge +33 % (14)
    - JM W edge +31 % (7)
    - WCC N edge −29 % (6)
    - MS S edge −27 % (14)
    - WCD E edge −27 % (20)
- **Production sharing** (`curated.wells_enriched.has_production_sharing`; `sharing.csv`): sharing wells read about 0–6 pt
  different from non-sharing, mixed sign. WCB_2 sharing reads −12 / −14 % vs −4 / −7 % not sharing.
- **Novi exhibit:** Novi 2025Q3 Midland per-ft oil bias −5.4 % cum-6 / +4.3 % cum-12 (D131, from 21a §2a; not recomputed:
  21b adds no Novi score).

## 6. Pad C 233 (named check, reported, never judged — `pad_c233.csv`)

This check runs the production machinery of record at the 2026-08-01 data date, read-only, on each stick's Midland pool
(box/production `fit_many`, `box/step21.RULES`, basin `midland`; revision 8 translation).
- **Columns.** BOX columns are **raw `mid_r2`**, before any walk-forward or D92 shape. The "after proximity" column applies
  the Midland factor where the outcome is a haircut. Novi is the live-vintage stick forecast (`curated.intel_forecast`; its
  30-yr sum reproduces `erebor_locations.oil_eur` to 0.1 %).
- **Units.** bbl per 1,000 ft. All 15 sticks are 10,560 ft.
- **What revision 8 changed.** The WCA, LSSH and WCC volumes fell 1.8–2.5 %: each 10,560-ft stick is longer than its
  cohort's mean lateral, so it now translates on the Delaware panel. WCD (7 analogs) is unchanged, and so is every shape
  (Di, b, EUR30 / cum-24).

| stick | outcome (Midland) | factor interim → Midland | Novi implied haircut (audit, 21a §3.11) | BOX cum-12 | after proximity | Novi cum-12 | BOX EUR30 | Novi EUR30 | EUR30 / cum-24 BOX / Novi | oil Di nominal (1-yr eff), b |
|---|---|---|---|---|---|---|---|---|---|---|
| WCA 1 | haircut k2 topfill\|3+\|F | 0.748 → 0.762 | −13 % | 13,229 | 10,080 | 11,662 | 49,184 | 37,682 | 2.55 / 2.29 | 2.14 (67 %), 1.05 |
| WCA 2 | haircut k2 topfill\|3+\|F | 0.748 → 0.762 | −19 % | 13,631 | 10,387 | 10,951 | 49,571 | 38,827 | 2.51 / 2.48 | 2.28 (69 %), 1.05 |
| WCA 3 | haircut k2 mixed\|4+ | 0.777 → 0.798 | −34 % | 13,815 | 11,022 | 7,873 | 49,349 | 28,352 | 2.47 / 2.53 | 2.22 (69 %), 1.03 |
| LSSH 1 | as-is (unexposed) | 1.000 | +2 to +3 % | 8,484 | 8,484 | 11,510 | 24,961 | 32,739 | 2.08 / 2.02 | 2.30 (71 %), 0.90 |
| LSSH 2 | as-is (unexposed) | 1.000 | +2 to +3 % | 8,484 | 8,484 | 11,579 | 24,961 | 34,740 | 2.08 / 2.11 | same |
| LSSH 3 | as-is (single neighbour) | 1.000 | +2 to +3 % | 8,484 | 8,484 | 11,155 | 24,961 | 31,796 | 2.08 / 2.02 | same |
| LSSH 4 | haircut k2 topfill\|3+\|F | 0.748 → 0.762 | −13 % | 8,484 | 6,465 | 9,246 | 24,961 | 29,558 | 2.08 / 2.22 | same |
| LSSH 5 | haircut k2 topfill\|3+\|F | 0.748 → 0.762 | −9 % | 8,484 | 6,465 | 9,659 | 24,961 | 28,887 | 2.08 / 2.10 | same |
| LSSH 6 | haircut k2 topfill\|2\|F | 0.856 → 0.908 | −14 % | 8,484 | 7,700 | 8,928 | 24,961 | 26,812 | 2.08 / 2.11 | same |
| WCC 1–3 | **no forecast** (precedent) | (0.94 / 0.87 / 0.84 → 0.91 / 0.87 / 0.89, unused) | −8 / −8 / −19 % | 15,744 | — | 9,075–10,394 | 46,510 | 29,206–32,923 | 2.13 / 2.10–2.26 | 2.70 (74 %), 0.93 |
| WCD 1–3 | as-is (unexposed) | 1.000 | ≈ 0 | 17,415–17,740 | same | 12,495–13,043 | 51,931–52,663 | 36,136–41,536 | 2.17 / 2.10–2.28 | 3.54 (78 %), 1.01 |

Against the audit's yardsticks (reported, never judged):
- **WCA_1 over WCB_1.** The audit measured −35 % (rock-controlled cum-12, n = 28). BOX's Midland haircut is −24 % on WCA 1–2
  and −20 % on WCA 3. After proximity, BOX sits 14 % under Novi on WCA 1 and 5 % under on WCA 2. It's **40 % over** on WCA 3,
  where Novi's own haircut is −34 %.
- **LSSH.** BOX's raw level is **5–27 % below Novi** on cum-12, the direction the audit read ("Novi LSSH hot"). But the cohort
  is thin: 7 analogs at 5 mi (`under_count`, count and spacing relaxed), and the pad has 0–2 pool wells within 3 mi.
- **WCC.** No forecast under the precedent rule (as at 21a), so the audit's −21 % underfill read isn't exercised.
- **WCD.** As-is. BOX is 36–42 % over Novi on cum-12, on a 6–7-analog cohort (1 local analog in the audit).
- **Tails: BOX does NOT fix the audit's flat-tail finding.**
  - EUR30 / cum-24 is 2.08–2.55 for BOX vs 2.02–2.53 for Novi, against the audit's producing 1.3–2.0×.
  - These are raw `mid_r2` months. The D92 haircut shape (WCA_1 oil median g(48) 0.89) trims the late months on walk-forward
    groups only.
  - This is the pad's open question for step 23, not a 21b change.
- **Rock read** (BOX: pool wells within 3 mi ÷ the cohort's mean year-1 oil per 1,000 ft, the audit's direction), unchanged:

  | bench | BOX | audit |
  |---|---|---|
  | WCA_1 | 0.95–0.97 | 0.98–1.06 |
  | WCC | 0.95 | 1.04–1.29 |
  | WCD | 0.97–1.03 | 1.18–1.40 |
  | LSSH | 0.53, on ONE local well | 0.65–0.71 |

  LSSH reads in the same direction; the deeper benches read flatter than the audit's. The audit's local set isn't BOX's pool,
  so these are comparable in direction only.

## 7. Disclosures and flags

- **§4 ambiguity, asked and answered before any fit:** the ladder applied is production's lookup (k2 → k3 → k4,
  `prox_pud.decide` via `production16.oil_factors`); k1 is fitted and reported only (Michael 2026-11-01).
- **Revision 8 is the one post-score change** (D148). It was designed on the tuning view; its projected pooled gain
  overstated the realized one because the projection skipped the frozen F(k) refit (§0). The holdout is still unread and is
  its test.
- **WCB_2** sits at 29.7 expected walk-forward holdout packages at cum-24, so the rule gives `mid_r2p`.
- **JM's alternative rows equal its record** in `frozen_d99.csv`. D106 refused both walk-forward streams, so the rule's pick
  has no admissible alternative. The same applies to WCA_1 / WCB_1 gas. Harmless; stated so the duplicates aren't read as an
  error.
- **Process slips caught before scoring:**
  - revision 7: a first scorer launch on a non-venv Python (import error, nothing written); the observer proof first failed
    on string arrays in the npz (fixed in 42b55ab); a Pad C 233 run first wrote NaN Di (wrong key).
  - revision 8: none.

  None touches a frozen file or a scored number.
- **Delaware:** untouched. Run 19 is the record (D144). No store, no flip, and no Delaware read beyond the D113 table used as
  the `mid_r2p_de` sensitivity. Revision 8 changes only the Midland's `LONGER_PANEL` key; the Delaware default is unchanged.

## 8. Long-lateral diagnostic (Michael 2026-11-02; read-only, tuning views only — `lateral_diag/`, `scripts/box_step21b_lateral_diag.py`)

**Run on the REVISION-7 views.** This is the analysis that led to revision 8, kept as written. Its "hybrid" column is the
projection §0 compares against; the realized numbers are in §0 and `rev8_vs_rev7/`.

The question: why did revision-7 `mid_r2` over-forecast ≥ 15,000-ft laterals by 11–13 % when 21a read per-ft oil as flat
with length, and what would each option do on the PUD mix? 11,203 tuning wells, 4,221 packages. The script refuses any row
flagged as D52 holdout (none were present).

- **"Long laterals sit in better rock" (my first explanation): NOT supported.** Local rock (mean year-1 oil per 1,000 ft
  within 3 mi) is flat to slightly lower for long laterals: 15.7k bbl at 15,000–17,500 ft vs 15.8k at 10,000–12,500 ft
  (`rock_by_length.csv`). Only the thin ≥ 17,500-ft class (91 wells) sits in better rock.
- **Per-ft does fall with length in this population.** Scored wells (first production 2020–2025):
  - Median actual cum-12 oil per 1,000 ft is 15.1k bbl at 5,000–7,500 ft, 14.3k at 10,000–12,500 and 13.4k at
    15,000–17,500 (−11 % end to end).
  - The log-log slope is −0.10 basin-wide (bench × cutoff FE) and −0.15 within 3-mi blocks.
  - 21a's flat read (all tuning-block producers 2016–2025, within block × first-year cells, reported lateral) **isn't
    reproduced here, and the gap isn't reconciled.** Candidate causes: the population (21a includes 2016–2019 wells) and
    reported vs completed lateral.
- **The miss follows the length gap to the cohort** (`by_lat_ratio.csv`).
  - In the 12,500–15,000 and 15,000–17,500-ft classes, targets ≥ 1.5× their cohort's mean lateral miss −7.2 / −10.8 % on the
    Midland panel and −0.5 / −3.8 % on the Delaware panel (cum-12).
  - Targets near their cohort's length don't need the steeper curve.
  - One thin exception: 15,000–17,500-ft targets whose cohort is already about 13,000 ft miss −22 % on BOTH panels (31
    packages), unexplained.
- **A smooth fitted law doesn't work.**
  - A power law E(L) = (L / 5,000)^e, cross-fitted on alternate 3-mi blocks, is unstable (e = −0.13 vs −0.04 between halves
    at cum-12) and leaves ≥ 15,000 ft at −9.9 %.
  - The effect is one-sided (longer than the cohort), not a smooth curve.
  - The emulator behind the fitted option reproduces the exact twins to a median 0.3 % (Midland) / 1.2 % (Delaware)
    (`emulator_check.csv`).
- **The options, revision 7, on the PUD mix** (21a `sticks_by_length.csv`; projections: see §0 for what revision 8 realized)
  are in `options_by_class.csv` / `options_weighted.csv`.

**Gate 21b** = your answers to:
- **Q1:** record treatment per group;
- **Q2:** the frozen intervals (`cf13af17` / `64e592b5`);
- **Q3:** the Midland proximity table;
- **Q7:** keep revision 8 as run.

Q4–Q6 inform. Then 21c scores the D52 holdout once against `frozen_d99.csv` / `frozen_water.csv`, at 5ceadc2.
