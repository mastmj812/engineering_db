# BOX step 21b — Midland tuning-fold scoring (2026-11-01) — AT GATE 21b

Read-only. Nothing stored, no DDL, no record flip; the Delaware record stays on run 19 (D144) and nothing here reads or writes
the Delaware. Branch `claude/box-step21b-tuning`. The contract is the FROZEN pre-registration
(`docs/box/step21a-2026-10-31/PREREGISTRATION.md` + `box/step21.DEFINITION`, digest `505439b9`, frozen SHA `501d799`, D146 / D147).
**Tuning packages only: the D52 holdout packages are dropped before any statistic and only counted (21a `package_counts.csv`).
No holdout bias, error or forecast was read.**

- **Review surface:** `index.html` (summary, pooled oil-bias dot plots with the frozen intervals, the proximity tables, per-group
  sections, long laterals, §9, water, Pad C 233, run records).
- **Frozen at this gate:** `frozen_d99.csv` sha256 **`b50bcb71698d8133b4243c07eead17a5c7425fa74b802bade2f0c8906d115691`**;
  `frozen_water.csv` sha256 **`5db6aeca42934d12db00f9182e99090ada3973625354abed9a5490be530dc42d`** (canonical LF text, `%.12g`;
  a second full scorer run reproduced both hashes byte for byte).
- **Builder:** `python -m scripts.box_step21b runs | score | water | pad` then `python -m scripts.box_step21b_render`
  (new files only: `box/step21b.py`, `scripts/box_step21b*.py`, `tests/test_box_step21b.py`; 6 tests pass).
- Grain is stated per table: packages (D53), wells, or sticks. **Bias = Σ actual / Σ forecast − 1: negative = BOX over-forecasts.**

## 1. Gate 21b — your calls (recommendation first)

1. **Record treatment per group (§5).** The rule (scored walk-forward holdout ≥ 30 at cum-12 AND cum-24), then the D106 guard per
   stream, gives the "rule" column. The tuning gate lets you move `mid_r2p_wf → mid_r2p` or a group to provisional (never the
   other way, never after a holdout look).

   | group | rule → after D106 | tuning oil bias cum-12 / 24 / 36 (record) | alternative oil | rec |
   |---|---|---|---|---|
   | WCA_1 | wf → **wf oil / r2p gas** (gas g(48) 1.42) | −1.5 / −1.6 / −0.1 % | r2p −2.9 / −3.2 / −5.0 % | **keep** |
   | WCB_1 | wf → **wf oil / r2p gas** (gas g(48) 1.21) | +2.5 / +3.2 / +0.3 % | r2p −1.9 / −2.6 / −4.7 % | **keep** |
   | LSSH | wf → **wf** | −6.6 / −6.1 / −10.1 % (cum-36 FAILS) | r2p −2.8 / −3.6 / −3.0 % (all six cells PASS) | **move to `mid_r2p`** |
   | MS | wf → **wf** | −4.1 / −4.0 / −0.8 % | r2p −4.6 / −7.4 / −8.4 % (cum-36 FAILS) | **keep** |
   | JM | wf → **r2p both streams** (oil g(48) 1.96, gas 1.51) | +3.1 / **+12.5 / +16.3 %** (cum-24 / 36 FAIL) | — (wf refused) | **move to provisional** |
   | WCB_2 | r2p (wf holdout 41 / **29.7** < 30) | −6.8 / −9.5 / −13.3 % (cum-36 not a D99 cell) | — | keep |
   | WCD | r2p (20 / 10) | −8.5 / −8.9 / −11.2 %; gas cum-12 / 24 FAIL (spread) | — | keep |
   | DEAN | r2p (24 / 9) | −2.8 / +0.2 / −3.1 %; **gas cum-24 +25.9 %** (FAILS) | — | keep, flagged |
   | WCC | r2p, **no D99 cell** → provisional by construction | −8.2 / −16.0 / −21.5 % | — | provisional (as registered) |

   - **LSSH** is the step-15 BS3_C / WCB_1 pattern: the walk-forward haircut (oil D62 factors 0.972 / 0.964 / 0.970 / 0.942)
     makes every oil horizon worse than no haircut and fails cum-36; `mid_r2p` passes all six pooled cells.
   - **JM** under-forecasts oil by 12.5 % at cum-24 and 16.3 % at cum-36, both D99 horizons, and gas by 14.7 % at cum-36. The
     correction the method allows (walk-forward) is refused by D106 because its own tail is non-physical (median g(48) 1.96).
     A D99 PASS would only say the holdout matches tuning, so a validated JM would carry a known 12–16 % miss. Provisional
     discloses it (D105). Alternative: keep `mid_r2p` and let D99 judge, with the bias disclosed.
   - **DEAN gas** cum-24 +25.9 % sits in a D99 cell (interval +1.6…+62 %: wide, 46-package cell). Oil is clean. I'd keep it
     and let D99 judge, but provisional is defensible on the same grounds as JM.
   - WCA_1 gas cum-36 under-forecasts +14.3 % (FAIL) under `mid_r2p` gas, because D106 refused the gas walk-forward. Oil is
     clean, so I'd keep it and disclose. Same reasoning, smaller miss, on the secondary stream.

2. **Freeze the D99 intervals as drawn — rec: yes** (`frozen_d99.csv`, sha256 above). The file carries the record treatment AND
   the alternative per group, so a move at Q1 needs no redraw (LSSH's `mid_r2p` rows are there). Moves to provisional simply
   leave a group's rows unused. Pass rates (a forecast as good as tuning passes / a ±15 % miss is caught):

   | | WCA_1 | WCB_1 | WCB_2 | WCD | MS | JM | LSSH | DEAN |
   |---|---|---|---|---|---|---|---|---|
   | good forecast passes | 0.83 | 0.82 | 0.88 | 0.88 | 0.82 | 0.81 | 0.81 | 0.86 |
   | catches +15 % / −15 % | 1.00 / 1.00 | 1.00 / 1.00 | 0.98 / 1.00 | **0.64 / 0.80** | 0.92 / 0.98 | 0.94 / 0.98 | 1.00 / 1.00 | 0.84 / 0.91 |

   WCD's test is weak (it catches a 15 % high miss only 64 % of the time). That's disclosure for 21c, not a change.

3. **Proximity factor table (§4) — rec: adopt the Midland table as fitted, no nearest-gap rung.** Fitted on 11,203 Midland
   tuning children in the scored views (1,793 multi-parent of 21a's 1,884, the rest dropped by the harness at early cutoffs;
   1,449 with a scored oil cum-24), production's lookup (your §4 answer): k2 class × count
   × flank → k3 → k4, multi-parent only; every class reaches a usable k4, so **no stick is unfit**. Outcomes are unchanged
   (32,541 sticks, identical class by class); only factors move. The median haircut lightens **0.777 → 0.798** (interquartile
   shift +0.018…+0.022). The five cards you flagged as too light:

   | card | stick | config | your note | interim (Delaware) | **Midland** (rung, n) | nearest-gap sensitivity |
   |---|---|---|---|---|---|---|
   | 9 | LSSH 1570956 | topfill, 3 | "hard to believe 0.74" | 0.748 | **0.766** (k2 topfill\|3+\|F, 209) | 0.788 (dv300-800\|dh<800, 178) |
   | 11 | WCB_1 1536795 | underfill, 4 | "hard to believe 0.94" | 0.940 | **0.915** (k4 underfill, 226; k2 / k3 < 30) | — (no supported band) |
   | 12 | JM 1602030 | topfill, 2 | "hard to believe 0.96" | 0.856 | **0.909** (k2 topfill\|2\|F, 63) | 0.949 (84) |
   | 33 | DEAN 1617415 | mixed, 4 | "extremely aggressive" | 0.777 | **0.798** (k2 mixed\|4+, 221) | — |
   | 45 | WCB_1 1571061 | same, 2 (533 / 1,145 ft) | "haircut seems light" | 0.923 | **0.834** (k2 same\|2\|F, 40) | 0.826 (dh400-800, 77) |

   **Read:** the Midland children agree with you on #45 (0.92 → 0.83) and somewhat on #11, and read lighter than the interim on
   #9, #12 and #33. On cards 9 and 33 the cards say "worse" and the Midland data say "about as bad as the Delaware said, slightly
   better". **Nearest-gap rung: not supported.** Only 4 of 22 gap keys reach 30 children (`prox_factor_table_gap_sensitivity
   .csv`), each class has at most one populated band except same\|2 (dh 400–800 ft 0.826 vs 800–1,400 ft 0.858, a 3-pt dose),
   and none moves a card by more than 0.04. The Delaware single-pair dose (0.80 → 0.98 over 0–2,000 ft) does not reproduce at
   the Midland's sample sizes. If the cards' "much worse" is the target, the lever is not this table. It is the spacing floor
   (rev 5, 400 ft) or the precedent rules, which are 21a decisions.

4. **Pattern-package gate (21a Q6) — rec: don't gate; keep it reported.** At revision 7, 2,294 haircut sticks have a pattern
   package count < 30. Applying D114's package rule to the pattern (factor ≤ 0.80 AND packages < 30) would refuse **837** more
   on the interim table and **788** on the Midland table. (21a's 1,751 was measured at revision 1, before revisions 2–7, and
   isn't reproduced here.) The same evidence that leaves card 33 at 0.80 would remove ~790 sticks a forecast. That's a
   population decision, not a factor one.

5. **Water (§7) — mechanical result: provisional on every Midland group.** Validated water needs every judged tuning cell to
   pass, and 3 of 22 judged cells pass (WCA_1 cum-12 / 36, WCB_2 cum-36). The D107 ratio **under-forecasts** water on measured
   packages by +15…+44 % on six groups (JM +42 / +44 / +38 %, MS +37 / +31 / +29 %, DEAN +30 / +29 %, LSSH +24 / +20 / +22 %,
   WCD +23 / +27 %, WCB_1 +15 / +19 / +23 %); WCA_1 reads +7…+10 % and WCB_2 is the only one high (−6…−10 %). Reach is fine (median 5–7.5 mi on the big
   benches, no vendor fallback except 1 DEAN target), but **the top operator holds a median 58–77 % of each target's 10
   nearest measured analogs**. **Rec:** accept water as provisional Midland-wide (the rule, not a choice), still score the
   water holdout once at 21c as registered, and open a separate read-only diagnosis after 21c: whether the sql/41 Texas
   `measured` label is genuine in the Midland, and operator concentration. No re-tune.

6. **Long laterals (§8, reported, never judged) — inform the step-23 disclosure.** Pooled over the nine groups (oil, `mid_r2` on
   the Midland Cui panel / linear twin / Delaware-panel twin):

   | completed lateral | pkgs cum-12 | cum-12 | cum-24 | cum-36 |
   |---|---|---|---|---|
   | 7,500–10,000 ft | 1,520 | −2.6 / −2.1 / −4.2 % | −4.1 / −3.6 / −5.5 % | −6.4 / −6.1 / −7.5 % |
   | 10,000–12,500 ft | 1,993 | −4.2 / −4.4 / −3.8 % | −4.6 / −4.9 / −4.1 % | −5.5 / −5.8 / −4.8 % |
   | 12,500–15,000 ft | 669 | −6.3 / −6.7 / −2.8 % | −6.5 / −6.9 / −2.8 % | −7.6 / −8.2 / −3.7 % |
   | **15,000–17,500 ft** | 504 | **−12.6** / −13.1 / −6.7 % | **−10.8** / −11.3 / −4.6 % | **−10.9** / −11.6 / −4.6 % |
   | 17,500–20,000 ft | 32 | −20.3 / −21.0 / −11.4 % | (10 pkgs) | (5 pkgs) |

   25.3 % of scored wells are > 12,500 ft and 11.4 % > 15,000 ft (past the Midland panel's last point). In the scored forecast,
   the Midland panel (and linear) over-forecast laterals past 15,000 ft by ~11–13 %; the Delaware panel halves that and costs
   ~5 pt on 5,000–7,500 ft. That doesn't contradict 21a's observed flat per-ft. 21a measured raw per-ft by length class; here
   the cohort's per-ft is translated to the target's length, and long targets draw cohorts of shorter wells. **No change at 21b**
   (D134 C, one variant, revision 7 is your answer). This is the size of the disclosure step 23 needs for > 15,000-ft PUDs.

## 2. What ran (every run on the frozen files)

| group | started → finished (UTC) | branch HEAD | box/ scripts/ dealintake/ vs 501d799 at start / end | scored tuning wells |
|---|---|---|---|---|
| MID_LSSH | 11-01 18:33 → 21:20 | 6728bc7 | identical / identical | 2,597 |
| MID_WCB_1 | 18:33 → 21:21 | 6728bc7 | identical / identical | 2,072 |
| MID_WCA_1 | 18:33 → 21:37 | 6728bc7 | identical / identical | 2,946 |
| MID_JM | 21:21 → 22:41 | 6728bc7 | identical / identical | 973 |
| MID_WCD | 23:05 → 23:45 | abe5104 | identical / identical | 496 |
| MID_DEAN | 23:46 → 11-02 00:32 | abe5104 | identical / identical | 560 |
| MID_MS | 23:05 → 00:35 | abe5104 | identical / identical | 866 |
| MID_WCB_2 | 23:05 → 00:42 | abe5104 | identical / identical | 575 |
| MID_WCC | 00:32 → 00:59 | abe5104 | identical / identical | 118 |
| MID_WCC (plain §10 command) | 00:35 → 01:02 | abe5104 | identical / identical | — (the proof run) |

- Every run's `run.json` records HEAD, the frozen check at start and end (changed = none, every difference an ADDED 21b file),
  the nightly state at start and end, the definition digest, and rc 0. The branch moved 6728bc7 → abe5104 between batches by
  adding 21b-only files. The frozen check passes both. Engine `boxfit` 3380317 throughout.
- **Nightly:** the 2026-11-01 nightly ran late (17:07–18:32 UTC). The driver waited it out and started at 18:33. Every later
  step checked again; twice the GitHub API timed out (TLS) and the guard refused to start until it answered.
- **Windows restart at 22:59:59 UTC** killed MS / WCB_2 / WCD mid-run. The four finished runs were intact (rc 0, outputs
  complete), and the three were re-run from scratch at 23:05 with the same check. Nothing partial was scored.
- **The `mid_r2` months observer** (`scripts/box_step21b_harness.py`): the frozen harness doesn't save `mid_r2` monthly
  volumes, which the walk-forward / D106 guard need. The wrapper records them as the frozen harness computes them and changes
  nothing. **Proof:** the plain §10 command on MID_WCC and the observed run are identical on all 10 outputs (6 views, cells,
  months npz, summary JSON without its timestamp, provenance). Per-well calendar factor F(k) recovered from the views agrees to
  ≤ 4.4e-16; harness cells vs the scorer's re-derivation ≤ 6.7e-16 on every group.
- Proximity links reuse the 21a revision-7 caches (sha256 in `score_meta.json`); a re-decision of all 32,541 sticks under the
  interim table reproduces 21a's `sticks.csv.gz` with 0 differences.

## 3. Proximity detail (`prox_factor_table.csv`, `sticks_midland_table.csv.gz`)

- Applied rungs (k2 / k3 / k4): 12 / 12 / 5 usable keys of 19 / 13 / 5. k2 same\|3+ (18 + 18), topfill\|3+\|S (16) and
  underfill\|2–3+ fall to k3 or k4. k1 bench pairs (fitted, never applied): 16 of 150 usable. LSSH>same>LSSH\|1 0.915 (n 167),
  \|2 0.829 (38); LSSH>topfill>WCA\|3+ 0.723 (68).
- Midland haircut median by group (interim → Midland): WCA_1 0.795 → 0.803, LSSH / JM / DEAN 0.777 → 0.798, MS 0.748 → 0.766,
  WCB_1 / WCB_2 0.918 → 0.915. Factor keys on sticks (all outcomes): k2 13,087, k3 825, k4 914.
- `mid_r2p_de` (the Delaware D113 table on the same children) and `mid_r2p_gap` (the gap-rung sensitivity) are scored beside the
  record in `pooled.csv`. The Delaware table moves no pooled verdict; the gap rung moves one (MS oil cum-36 FAIL → PASS).
- **DEAN (D143), sticks:** loop addition 1,047 = haircut 179 (median 0.798) / as-is 511 / no forecast 357 (pattern 195,
  precedent 92, spacing 70); generated body 280 = haircut 12 (0.890) / as-is 212 / no forecast 56.

## 4. Water detail (`water_cells.csv`, `water_intervals.csv`, `water_reach.csv`, `frozen_water.csv`)

D107 ratio on raw `mid_r2` oil, measured-water packages, D109 thresholds (|bias| ≤ 20 % AND scale-free band ≤ local-offsets
benchmark + 0.10, ≥ 30 packages). Water intervals use `box/water11` / `rehearse9b.consistency` as built (2,000 draws, seed 5).
WCC (14 packages) and WCD cum-36 / DEAN cum-36 are not judged. WCC's water interval is degenerate (0.05 % of draws judged), so
it's in the frozen file for completeness only. `ratio_actoil` (ratio on ACTUAL oil) is reported beside it; its |bias| is larger
in every judged cell.

## 5. §9 reports (never judged)

- **Thin control** (< 3 modern local wells in 3 mi): 1,822 of 7,586 oil package counts (cum-12 + cum-24 summed over groups). WCA_1 thin −12.7 / −7.1 % (mid_r2
  cum-12 / 24) vs −4.6 / −5.6 % with control; elsewhere mixed sign (`thin_control.csv`).
- **Edges** (within 5 mi of the extent, by compass side, oil cum-24): the big benches' interiors are within ±6 % except JM
  (+18.7 %) and WCB_2 (−14.0 %). Edge cells are 5–38 packages; the largest misses are WCA_1 S edge +32 % (14), WCD E edge
  −29 % (20), MS S edge −28 % (14), WCC N edge −31 % (6) (`edge_regions.csv`).
- **Production sharing** (`curated.wells_enriched.has_production_sharing`): sharing wells read ~0–6 pt different from
  non-sharing, mixed sign; WCB_2 sharing −12 / −15 % vs −4 / −7 % (`sharing.csv`).
- **Novi exhibit:** Novi 2025Q3 Midland per-ft oil bias −5.4 % cum-6 / +4.3 % cum-12 (D131, from 21a §2a; not recomputed: 21b
  adds no Novi score).

## 6. Pad C 233 (named check, reported, never judged — `pad_c233.csv`)

The production machinery of record at the 2026-08-01 data date, read-only, on each stick's Midland pool (box/production
`fit_many`, `box/step21.RULES`, basin `midland`). BOX columns are **raw `mid_r2`** (before any walk-forward / D92 shape). The
"after proximity" column multiplies by the Midland factor where the outcome is a haircut. Novi = the live-vintage stick
forecast (`curated.intel_forecast`; its 30-yr sum reproduces `erebor_locations.oil_eur` to 0.1 %). Per 1,000 ft, bbl; all 15
sticks are 10,560 ft.

| stick | outcome (Midland) | factor interim → Midland | Novi implied haircut (audit, 21a §3.11) | BOX cum-12 | after proximity | Novi cum-12 | BOX EUR30 | Novi EUR30 | EUR30 / cum-24 BOX / Novi | oil Di nominal (1-yr eff), b |
|---|---|---|---|---|---|---|---|---|---|---|
| WCA 1 | haircut k2 topfill\|3+\|F | 0.748 → 0.766 | −13 % | 13,493 | 10,329 | 11,662 | 50,167 | 37,682 | 2.55 / 2.29 | 2.14 (67 %), 1.05 |
| WCA 2 | haircut k2 topfill\|3+\|F | 0.748 → 0.766 | −19 % | 13,945 | 10,675 | 10,951 | 50,711 | 38,827 | 2.51 / 2.48 | 2.28 (69 %), 1.05 |
| WCA 3 | haircut k2 mixed\|4+ | 0.777 → 0.798 | −34 % | 14,174 | 11,311 | 7,873 | 50,631 | 28,352 | 2.47 / 2.53 | 2.22 (69 %), 1.03 |
| LSSH 1 | as-is (unexposed) | 1.000 | +2 to +3 % | 8,636 | 8,636 | 11,510 | 25,407 | 32,739 | 2.08 / 2.02 | 2.30 (71 %), 0.90 |
| LSSH 2 | as-is (unexposed) | 1.000 | +2 to +3 % | 8,636 | 8,636 | 11,579 | 25,407 | 34,740 | 2.08 / 2.11 | same |
| LSSH 3 | as-is (single neighbour) | 1.000 | +2 to +3 % | 8,636 | 8,636 | 11,155 | 25,407 | 31,796 | 2.08 / 2.02 | same |
| LSSH 4 | haircut k2 topfill\|3+\|F | 0.748 → 0.766 | −13 % | 8,636 | 6,611 | 9,246 | 25,407 | 29,558 | 2.08 / 2.22 | same |
| LSSH 5 | haircut k2 topfill\|3+\|F | 0.748 → 0.766 | −9 % | 8,636 | 6,611 | 9,659 | 25,407 | 28,887 | 2.08 / 2.10 | same |
| LSSH 6 | haircut k2 topfill\|2\|F | 0.856 → 0.909 | −14 % | 8,636 | 7,846 | 8,928 | 25,407 | 26,812 | 2.08 / 2.11 | same |
| WCC 1–3 | **no forecast** (precedent) | (0.94 / 0.87 / 0.84 → 0.91 / 0.88 / 0.89, unused) | −8 / −8 / −19 % | 16,056 | — | 9,075–10,394 | 47,431 | 29,207–32,923 | 2.13 / 2.10–2.26 | 2.70 (74 %), 0.93 |
| WCD 1–3 | as-is (unexposed) | 1.000 | ≈ 0 | 17,415–17,740 | same | 12,495–13,043 | 51,931–52,663 | 36,136–41,536 | 2.17 / 2.10–2.28 | 3.54 (78 %), 1.01 |

Against the audit's yardsticks (reported, never judged):
- **WCA_1 over WCB_1:** the audit measured −35 % (rock-controlled cum-12, n = 28). BOX's Midland haircut is −23 % (WCA 1–2) /
  −20 % (WCA 3). After proximity BOX sits 11 % (WCA 1) and 3 % (WCA 2) under Novi and **44 % over** on WCA 3, where Novi's own
  haircut is −34 %.
- **LSSH:** BOX's level is **3–25 % below Novi** before any haircut, the direction the audit read ("Novi LSSH hot"). But the
  cohort is thin: 7 analogs at 5 mi (`under_count`, count and spacing relaxed), and the pad has 0–2 pool wells within 3 mi.
- **WCC:** no forecast under the precedent rule (as at 21a), so the audit's −21 % underfill read isn't exercised.
- **WCD:** as-is. BOX 36–42 % over Novi on cum-12 on a 6–7-analog cohort (1 local analog in the audit).
- **Tails: BOX does NOT fix the audit's flat-tail finding.** EUR30 / cum-24 is 2.08–2.55 for BOX vs 2.02–2.53 for Novi, against
  the audit's producing 1.3–2.0×. These are raw `mid_r2` months; the D92 haircut shape (WCA_1 oil median g(48) 0.90) trims
  the late months on walk-forward groups only. This is the pad's open question for step 23, not a 21b change.
- **Rock read** (BOX: pool wells within 3 mi ÷ the cohort's mean year-1 oil per 1,000 ft, the audit's direction): WCA_1
  0.95–0.97 (audit 0.98–1.06), WCC 0.95 (1.04–1.29), WCD 0.97–1.03 (1.18–1.40), LSSH 0.53 on ONE local well (0.65–0.71). Same
  direction on LSSH; the deeper benches read flatter than the audit's. The audit's local set isn't BOX's pool, so these are
  comparable in direction only.

## 7. Disclosures and flags

- **§4 ambiguity, asked and answered before any fit:** the ladder applied is production's lookup (k2 → k3 → k4,
  `prox_pud.decide` via `production16.oil_factors`); k1 is fitted and reported only (Michael 2026-11-01).
- **WCB_2** sits at 29.7 expected walk-forward holdout packages at cum-24 (the summary rounds to 30): `mid_r2p` by the rule.
- **JM's alternative rows equal its record** in `frozen_d99.csv`: D106 refused both walk-forward streams, so the rule's pick has
  no admissible alternative. The same applies to WCA_1 / WCB_1 gas. Harmless, stated so the duplicates aren't read as an error.
- **Process slips caught before scoring:** a first scorer launch ran on a non-venv Python (import error, nothing written); the
  observer proof first failed on string arrays in the npz (fixed in 42b55ab, proof re-run identical); a Pad C 233 run first
  wrote NaN Di (wrong key), fixed and re-run. None touches a frozen file or a scored number.
- **Delaware:** untouched. Run 19 is the record (D144); no store, no flip, no Delaware read beyond the D113 table used as the
  `mid_r2p_de` sensitivity.

**Gate 21b** = your answers to Q1 (record treatment per group), Q2 (the frozen intervals) and Q3 (the Midland proximity table);
Q4–Q6 inform. Then 21c scores the D52 holdout once against `frozen_d99.csv` / `frozen_water.csv`.
