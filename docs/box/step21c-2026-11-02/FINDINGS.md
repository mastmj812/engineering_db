# BOX step 21c — Midland one-time D52 holdout, FINDINGS (AT GATE 21c)

> **Gate answer, Q1 (Michael, 2026-11-03): "LSSH validated".** Reading (b): a `mid_r2p_wf` → `mid_r2p` move at the tuning gate
> is judged on its holdout (the §5 / step-15 WCB_1 precedent). LSSH = validated on `mid_r2p`, no haircut. Q2–Q5 are still open.

Scored once on 2026-11-02/03 under the frozen pre-registration: `docs/box/step21a-2026-10-31/PREREGISTRATION.md` +
`box/step21.DEFINITION`, revision 8, digest `9780f326`, frozen SHA `5ceadc2` (D148). Record treatments come from gate 21b (D149,
`docs/box/step21b-2026-11-01/GATE_21B.json`). Both frozen interval files hashed equal to GATE_21B.json before use:
`frozen_d99.csv` `cf13af17…`, `frozen_water.csv` `64e592b5…`.

Bias = Σ actual / Σ forecast − 1, so **negative = BOX over-forecasts**. Grain = D53 packages pooled over the cutoffs 2019–2024.
Production is through 2026-08-01.

**Nothing was stored.** No run was flipped, nothing touched the Delaware (it stays on run 19, D144), and nothing wrote
`box.bench_scope.validation` (that's step 23). The warehouse was only read.

- **Page:** `index.html`. It shows every judged cell as a dot against its frozen interval, plus every table below.
- **Builder:** `python -m scripts.box_step21c runs | reproduce | water | judge | render`, then
  `python -m scripts.box_step21c_diag [--d105-raw]`.
- **Code check:** `CODE_CHECK.md`, committed e2b0b47 before any holdout run.

## 1. Result

| group | record oil / gas (D149) | judged cells | D99 | outside its frozen interval | tier as computed | water (D109) |
|---|---|---|---|---|---|---|
| MID_WCA_1 | `mid_r2p_wf` / `mid_r2p` | oil + gas 12 / 24 / 36 | **PASS** 6 / 6 | — | **validated** | provisional; holdout 3 / 3 consistent |
| MID_WCB_1 | `mid_r2p_wf` / `mid_r2p` | 12 / 24 / 36 | **FAIL** | gas 12: −2.4 % vs [−2.2, +8.7] | provisional | provisional; 3 / 3 |
| MID_LSSH | `mid_r2p` / `mid_r2p` (moved at 21b) | 12 / 24 / 36 | **PASS** 6 / 6 | — | ★ **validated or provisional: Q1** | provisional; 3 / 3 |
| MID_WCB_2 | `mid_r2p` | 12 / 24 / 36 | **FAIL** | oil 12 / 24 / 36: +5.1 / +1.8 / +2.4 % vs intervals topping out at +2.6 / +1.5 / −1.9 % | provisional | provisional; no cell ≥ 10 pkgs |
| MID_JM | `mid_r2p` | 12 / 24 / 36 | **FAIL** | gas 12: −9.6 % vs [−8.4, +10.5] | provisional | provisional; 3 / 3 |
| MID_MS | `mid_r2p_wf` both | 12 / 24 / 36 | **FAIL** | gas 12: −8.4 % vs [−6.6, +17.2] | provisional | provisional; 3 / 3 |
| MID_WCD | `mid_r2p` | 12 / 24 | **PASS** 4 / 4 | — | **validated** | provisional; no cell ≥ 10 pkgs |
| MID_DEAN | `mid_r2p` | 12 / 24 | **FAIL** | oil 12 / 24: +21.8 / +23.2 % vs [−11.4, +9.0] / [−11.3, +14.1]; gas 12: +29.3 % vs [−10.9, +23.0] | provisional | provisional; 2 / 2 |
| MID_WCC | — | none | not scored | — | provisional by construction | provisional |

- **One tier covers both streams.** §6 judges oil AND gas at every horizon, so a group's tier applies to oil and gas together.
- **Water is provisional on every group.** That comes from the tuning half (D149 (5): 3 of 22 tuning cells pass). Every water
  holdout cell with ≥ 10 measured packages sits inside its frozen interval (17 / 17). WCB_2 and WCD have no such cell.
- **Holdout biases on the validated groups:**
  - WCA_1: oil −2.0 / −0.4 / −0.5 %, gas +5.9 / +11.1 / +13.8 %.
  - LSSH: oil −0.4 / −1.4 / −1.5 %, gas −1.6 / −3.3 / −1.2 %.
  - WCD: oil −1.2 / −5.2 %, gas +2.1 / +15.4 %.
  - WCA_1 gas reads +11 % at cum-24. That's over the ±10 % line, which D53 reports but never gates.

## 2. Gate 21c questions (recommendation first)

**Q1 ★ LSSH tier: validated (recommended) or provisional.** LSSH passes 6 / 6 on its record `mid_r2p`, judged against the
`mid_r2p` alternative rows frozen at 21b for exactly this move. The pre-registration reads two ways:

- **(a) §6 as written → provisional.** "Provisional = FAIL, no judgeable cell, or moved at the tuning gate."
- **(b) §5 and the step-15 precedent → validated.** §5 lets Michael move a group `mid_r2p_wf` → `mid_r2p` "on tuning evidence
  (step-15 BS3_C / WCB_1)", or move it to provisional "(step-15 BS2_C)". The text treats these as two different moves. Step-15
  WCB_1 made the first kind of move before its holdout, was judged on that holdout (PASS 6 / 6), and went to run 9 as
  validated (`docs/box/step15-holdout-2026-10-18/FINDINGS.md`). Under this reading, §6's "moved" means moved to provisional.

**Recommendation: (b), validated.** §5 cites WCB_1 as the precedent for exactly this move. The move came before any holdout
look and was a downgrade (D149 (1)). The alternative intervals exist only to judge it.

Reported only, not used for the tier: LSSH's original `mid_r2p_wf` also lands 6 / 6 inside its own frozen record intervals
(oil −1.9 / −1.2 / −7.4 %, gas +3.0 / −1.3 / −7.9 %). Neither treatment fails on the holdout.

If (b) is accepted, step 23 should carry a one-line text fix to §6: "moved to provisional at the tuning gate".

**Q2 Accept the tiers as scored: recommended.**

- **Validated:** WCA_1, WCD, and LSSH (per Q1).
- **Provisional:** WCB_1, WCB_2, JM, MS, DEAN, plus WCC by construction. These ship raw `mid_r2p` with no haircut and carry
  D105 lines (§4). Water is provisional on all nine.
- No re-tune. §5 of this file diagnoses the FAILs.
- What it costs, in plain numbers:
  - **WCB_1** loses an oil haircut of 0.99–0.97. Raw `mid_r2p` is near unbiased there (tuning + holdout oil −0.7 / −1.1 /
    −2.7 %).
  - **MS** loses its walk-forward oil and gas haircut (oil factors 0.94 / 0.92 / 0.91 / 0.85 at cum-12 / 24 / 36 / 48). Raw
    `mid_r2p` over-forecasts MS:
    - oil: tuning −4.2 / −7.0 / −7.8 %, holdout −12.8 / −9.7 / −13.0 %, pooled −6.2 / −7.6 / −8.9 %;
    - gas: pooled −1.7 / −2.1 / −7.1 %.
  - So MS ships about 6–9 % high on oil, with that line disclosed. That is §6 as written (the D105 convention since run 9);
    it's flagged here so it isn't a surprise at step 23.

**Q3 Step-23 haircut of record: WCA_1 oil only — recommended.** The D102 table merges tuning + holdout `mid_r2p` per cutoff,
then applies the ≥ 30 floor:

| horizon | factor | packages | cutoffs |
|---|---|---|---|
| cum-12 | 0.979 | 1,281 | 6 |
| cum-24 | 0.975 | 1,092 | 5 |
| cum-36 | 0.954 | 865 | 4 |
| cum-48 | 0.950 | 408 | 2 |

- The D106 guard passes: factors are monotone, and the median D92 g(48) is 0.884 with 0 % of locations outside [0.6, 1.2].
- Every other stream carries none:
  - WCA_1 gas: the record is `mid_r2p`, and D106 still refuses it on tuning + holdout (g(48) 1.38).
  - LSSH, WCD: the record is `mid_r2p`.
  - The provisional groups: raw.
- `d102.csv` and `guard_d106.csv` have every group's table for reference.

**Q4 WCB_2 cum-36 judged on its actual count: recommended (no decision rides on it).**

- §6 judges a horizon whose pooled holdout cell reaches 30 packages. WCB_2 scored 39 at cum-36; 21b's expectation said 28
  (`d99_cell` False).
- The gap has a cause. The 21a counts skip (2019 cutoff, cum-36) by `box/thin_bench.UNSCORED_EARLY`, a step-9a assumption about
  thin 2016 bases. The Midland pools score that cell on both halves, and the frozen interval was drawn on the same cutoffs,
  2019 included (21b `cells.csv`: 32 WCB_2 tuning packages at 2019 cum-36).
- LSSH cum-36 got the same lift (146 vs 116 expected) and sits inside either way.
- WCB_2 FAILs on cum-12 and cum-24 alone, so its tier doesn't depend on this.

**Q5 FAIL diagnosis: accept, as text watch items.** Details in §5.

- **DEAN:** workups state the holdout under-forecast as text (D101 pattern): oil +22 / +23 % at cum-12 / 24, gas +29 / +52 %.
  The gas miss is BOX's own (§5).
- **WCB_2:** the holdout is close to unbiased (oil +5 / +2 / +2 %), while tuning over-forecast (−6 / −9 / −13 %). Its D105 line
  shows both.
- **WCB_1, JM, MS:** a holdout gas cum-12 low (BOX high) that the local-offsets benchmark shares.

**Next (informing, nothing to decide here):**

- Step 23 (Midland record run, `box.bench_scope.validation` per bench) on your go.
- The water read-only diagnosis D149 (5) asked for after 21c: the sql/41 Texas `measured` label in the Midland, and operator
  concentration (top operator holds 58–77 % of the 10 nearest measured analogs). It's a separate task. 21c doesn't start it.

## 3. Haircut tables and the 9c guard (D102 / D106)

`d102.csv` has every group. It is marked *applies* only for a wf stream of a validated group, which leaves WCA_1 oil alone (Q3).

`guard_d106.csv` per group and stream, on tuning + holdout:

- WCA_1 oil passes.
- Refused: WCA_1 gas (g48 1.38), WCB_1 gas (1.21), JM oil / gas (2.03 / 1.56), WCB_2 gas (reversal 0.012), WCD oil (reversal
  0.026), DEAN gas (no location to evaluate).
- These are reported only. None of these streams carries a walk-forward record in a validated group.

## 4. D105 disclosure lines (provisional groups; 95 % 3-mi-block bootstrap)

Lines are for the treatment each group ships:

- raw `mid_r2p` for WCB_1 and MS (`disclosure_provisional_r2p.csv`);
- the record `mid_r2p` for WCB_2, JM and DEAN (`disclosure.csv`; that file also has the tuning + holdout lines and the
  validated groups).

By vintage: `vintage.csv`. Never quote the pooled figure alone (D105).

| group | stream | tuning cum-12 / 24 / 36 | holdout cum-12 / 24 / 36 |
|---|---|---|---|
| WCB_1 | oil | −1.4 / −2.0 / −4.2 % | +1.6 / +1.9 / +2.6 % |
| WCB_1 | gas | +2.9 / +4.3 / +7.9 % | −2.4 / −1.2 / +4.0 % |
| WCB_2 | oil | −6.2 / −8.9 / −13.0 % | +5.1 / +1.8 / +2.4 % |
| WCB_2 | gas | +2.9 / +4.4 / +7.2 % | +4.7 / +2.6 / +4.6 % |
| JM | oil | +3.7 / +13.0 / +16.9 % | −7.0 / +1.0 / +20.2 % |
| JM | gas | +1.3 / +6.9 / +15.3 % | −9.6 / −1.1 / +12.2 % |
| MS | oil | −4.2 / −7.0 / −7.8 % | −12.8 / −9.7 / −13.0 % |
| MS | gas | +1.1 / −0.4 / −5.5 % | −11.0 / −8.1 / −12.9 % |
| DEAN | oil | −1.8 / +0.6 / −3.7 % | +21.8 / +23.2 / +3.3 % |
| DEAN | gas | +4.3 / +26.0 / +81.8 % | +29.3 / +51.7 / +118.8 % |

- DEAN cum-36 is outside the D99 cells (23 holdout packages) and is shown for disclosure only.
- The 21b DEAN gas flag stands: gas at cum-36 runs +82 to +119 %.

## 5. FAIL diagnosis (7a pattern; reported only, nothing re-tuned)

**More FAILs than chance.**

- The frozen interval is the spread of 20 % block draws of the tuning packages. 21b reported per group the share of those
  draws passing every judged cell: 0.81–0.88.
- Treating groups as independent, a holdout like tuning would give 1.3 FAILs of 8. We got 5. P(≥ 5) = 0.4 %.
- One caveat on that number. The draws are subsets of tuning, so the interval leaves out the tuning mean's own sampling error.
  For an independent holdout of this size, about 8 % of cells land outside by chance, not 5 %. With that correction, chance
  alone gives about 2.0 FAILs, and P(≥ 5) ≈ 3 %.
- The design property is as pre-registered (`rehearse9b.consistency`, frozen), so it is reported, not acted on.
  `diag_null_group.csv`.

**What moves is mostly the packages, not BOX.** `diag_shift.csv` puts the holdout-minus-tuning shift of BOX next to the same
shift of the local-offsets benchmark:

| FAIL cell | BOX shift | benchmark shift | read |
|---|---|---|---|
| WCB_2 oil 12 / 24 / 36 | +11 / +11 / +15 pt | +10 / +10 / +14 pt | shared: the holdout packages under-perform the analogs less than tuning did |
| DEAN oil 12 / 24 | +24 / +23 pt | +18 / +24 pt | shared: the holdout DEAN packages beat both BOX and the local offsets |
| DEAN gas 12 | +25 pt | +5 pt | **BOX-specific** (also gas 24: +26 vs +13); fits the 21b DEAN gas flag |
| JM gas 12 | −11 pt | −8 pt | mostly shared |
| MS gas 12 | −14 pt | −17 pt | shared |
| WCB_1 gas 12 | −5 pt | −4 pt | shared; missed the interval edge by 0.2 pt |

- Four of the five FAILs are the D52 holdout blocks carrying packages unlike tuning's, beyond what the block draws capture.
  The local-offsets benchmark makes the same miss. That's the 7a finding again: BOX and benchmark errors move together.
- DEAN gas is the one BOX-specific miss.
- Neither reading changes a tier. §6 says FAIL means diagnose, never re-tune.

## 6. Integrity and disclosures

- **Every 21c run used the frozen files.** For all 8 groups, at both start and end, every `box/`, `scripts/` and `dealintake/`
  file that exists at `5ceadc2` was identical. 21c only adds files, and each `run.json` lists them. Run head e2b0b47 throughout;
  definition digest `9780f326`.

  | group | started (UTC) | finished (UTC) | rc |
  |---|---|---|---|
  | WCA_1 | 11-02 21:12 | 23:28 | 0 |
  | WCB_1 | 11-02 21:12 | 23:24 | 0 |
  | LSSH | 11-02 21:12 | 23:13 | 0 |
  | WCB_2 | 11-02 23:13 | 11-03 00:50 | 0 |
  | JM | 11-02 23:24 | 11-03 00:29 | 0 |
  | MS | 11-02 23:28 | 11-03 00:49 | 0 |
  | WCD | 11-03 00:29 | 01:00 | 0 |
  | DEAN | 11-03 00:49 | 01:19 | 0 |

  `runs.csv` has the full records (SHA, frozen check, nightly state at start and end).
- **The guard lift (option A, Michael 2026-11-02).** The frozen `run()` refuses `step16` + `score_holdout` (D118, a Delaware
  guard), and the 21b runs carry no holdout packages. So `scripts/box_step21c_harness.py` runs the frozen `run()` compiled from
  its own source minus exactly those two lines. The source sha256 is pinned (`4bcad48c…`), the removed lines are recorded in
  every `run.json`, and the change is pinned by `tests/test_box_step21c.py`.
- **The scorer reproduces 21b before the read.** The 21b scorer on the 21b runs gives the committed 21b tables byte for byte:
  12 / 12 files, both frozen sha256 included (`reproduce.json`).
- **Same data as 21b.** F(k) on the holdout run equals 21b's on all 354 (cutoff, stream, horizon) cells (max |diff| 2e-16). The
  F training sample is drawn from the fold, so equal F means the same pool and actuals.
- **Walk-forward haircuts come from tuning cells only (D58).** All 384 holdout haircuts equal the 21b tuning log
  (`wf_identity.csv`). The harness's own holdout `mid_r2_wf` (history = holdout cells in the step-16 branch) is never read.
- **Counts vs the 21b expectation** (`counts.csv`): within ±1.2 packages everywhere except LSSH and WCB_2 at cum-36 (Q4).
  Gas cells take the oil record treatment's horizons, the same rule the 21b frozen file used.
- **The nightly.** Today's scheduled nightly fired 9.5 h late, at 20:47 UTC, right after a manual catch-up. Both finished green
  (21:11) before any group started. During the runs, two `workflow_dispatch` tests of the new 05:00 CT trigger (PR #218) ran
  at 21:57 and 22:01 UTC. Each skipped the ETL in 9 s because the day's run had already succeeded. Nothing was written, and
  every group saw no nightly running at its start and end checks.
- **Not opened.** The harness `log.txt` files print `box_v2` holdout cells; they were not opened (every rc = 0).
- **WCC skipped.** It has no D99 cell, so it was not run or scored, by construction.
- **Proximity coverage** (`coverage.csv`): every holdout well has a drilled-child config row. 146 / 74 / 124 / 10 / 35 / 38 / 1 /
  24 holdout wells carry a factor < 1 (WCA_1 … DEAN).
