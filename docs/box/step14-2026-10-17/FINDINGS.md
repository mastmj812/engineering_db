# BOX step 14 — thin benches: D2 build-vs-emerging evidence (decision only)

2026-10-17. Read-only; nothing stored. Review surface: `index.html` (evidence table, judgeability per horizon, package counts per
cutoff). Built by `python -m scripts.box_thin_bench` (`box/thin_bench.py`, 6 DB-free tests; ~1.5 min). Actuals through 2026-07-01
(= the live last full month today, and step 9a's data date). Re-render the page DB-free with `--render`.

**Question for gate 14:** which of BS2_C, AVA_0, AVA_1, AVA_2 (and WCD, already emerging) join the step-9 chain, and which go
to D2 emerging (`box.bench_scope.in_scope = false`, shown as not covered, worked by hand per deal)?

## 1. How the evidence was built

- **Producers** = the step-15 QC set for each bench (`wells_final_<bench>.csv`, gate-1 rule + class verdicts, `exclusions.csv`
  applied), first production ≥ 2016, real lateral, midpoint inside the extent of record.
- **Drillable PUDs** = the record run's `box.pud_forecast` rows for the bench with `inside_extent` (D67 universe: remaining_pud ∪
  NULL ∪ conflict, no RES). WCD has no extent, so all 2,579 WCD PUDs count.
- **Analog reach** = distance from each in-extent PUD midpoint to its 1st and 10th nearest same-bench producer with ≥ 6 months
  (deal-intake min_wells = 10; box/analog radius ladder 5 / 7.5 / 10 / 15 / 20 mi). Circle only — the D55 strike ellipse and the
  lateral band are ignored, so the real search reaches at least this far.
- **Packages** = exactly `box/acceptance.run`'s development packages: next-12-months wells per cutoff (Dec 2019 … Dec 2024) inside
  the extent, co-developed co-extent components (≥ 30 % overlap, first production within 180 d). A package is HOLDOUT when any
  member's midpoint is in a D52 block (salt `box-holdout-2026-10-13`, 20 % of 3-mi blocks). **Counts only** — no forecast and no
  error was computed for any package, tuning or holdout.
- **Calibration (BS2_S, the bench accepted at gate 9b):** tuning packages per cutoff at cum-12 reproduce step 9a
  (`cells_tuning_BS2_S.csv`) at 60 / 98 / 104 / 114 / 82 vs 60 / 97 / 104 / 114 / 82; 2019 is 44 vs 40. Holdout counts are within
  0–4 packages of the step-9b cells. Residual = wells the harness drops for a missing prediction.
- **Early long horizons:** the analog fold scored no 2019 cum-36 and no 2019/2020 cum-48 on BS2_S (F(k) needs 2016-vintage
  training wells, whose analogs must predate them). Every bench here has a thinner 2016 base than BS2_S, so those cells are zeroed
  for all of them.

What the counts allow (rules of record):

| rule | what it needs |
|---|---|
| D53 tuning cell | ≥ 30 packages in one cutoff × horizon |
| D57 walk-forward haircut (`box_v2_wf`) | ≥ 2 EARLIER cutoffs with a judged tuning cell at that horizon |
| D99 one-time holdout | the pooled holdout cell reaches ~30 packages (the pre-9b rehearsal's floor; BS2_S cum-36 at 17 was dropped) |
| D102 production haircut | cutoffs whose tuning + holdout merge reaches 30 |

## 2. Evidence table — step-14 benches (BS2_S = calibration row)

| bench | extent sq mi | producers in extent | PUDs in extent | PUDs / producer | producers fp 2016-19 / 20-22 / 23+ | 10th-nearest analog, mi P10 / P50 / P90 | 10th within 5 mi | past 10 mi |
|---|---|---|---|---|---|---|---|---|
| BS2_S (calib.) | 3,358 | 3,086 | 7,409 | 2.4 | 747 / 812 / 1,579 | 1.5 / 2.7 / 4.7 | 93 % | 0 % |
| **BS2_C** | 1,525 | 547 | 3,005 | 5.5 | 74 / 155 / 421 | 2.2 / 3.8 / 5.9 | 80 % | 0.4 % |
| **AVA_0** | 259 | 202 | 607 | 3.0 | 107 / 54 / 60 | 1.4 / 2.3 / 3.7 | 99 % | 0 % |
| **AVA_1** | 548 | 409 | 1,365 | 3.3 | 138 / 143 / 212 | 1.6 / 2.7 / 4.2 | 96 % | 0 % |
| **AVA_2** | 624 | 297 | 2,851 | 9.6 | 80 / 72 / 181 | 1.9 / 3.0 / 5.0 | 91 % | 0 % |
| AVA 0+1+2 pooled (sensitivity) | 1,431 | 919 | 4,823 | 5.2 | 325 / 269 / 453 | 0.9 / 1.8 / 3.0 | 99 % | 0 % |
| **WCD** (emerging; no extent) | — | 150 | 2,579 (all) | 17.2 | 66 / 37 / 47 | 7.0 / 14.1 / 18.7 | 3 % | 75 % (4 % past the 20-mi cap) |

Package counts (tuning / holdout) and what they allow:

| bench | tuning pkgs pooled, cum-12 / 24 | judged D53 cells, cum-12 / 24 | walk-forward cutoffs, cum-12 / 24 | holdout pooled, all cutoffs, cum-12 / 24 | holdout pooled, wf cutoffs, cum-12 / 24 | D102 cutoffs, cum-12 / 24 / 36 / 48 | can be judged |
|---|---|---|---|---|---|---|---|
| BS2_S (calib.) | 502 / 381 | 6 / 5 | 4 / 4 | 162 / 131 | 123 / 92 | 6 / 5 / 3 / 1 | yes, as accepted (`box_v2_wf`, D99 cum-12 + 24) |
| **BS2_C** | 163 / 111 | 3 / 2 | 2 / 2 | **46 / 34** | 19 / 7 | 4 / 2 / 1 / 0 | **only as a raw `box_v2` record (D97 pattern), cum-12 + cum-24; cum-24 cell is marginal** |
| **AVA_0** | 37 / 29 | 0 / 0 | 0 / 0 | 7 / 5 | 0 / 0 | 0 / 0 / 0 / 0 | no |
| **AVA_1** | 58 / 42 | 0 / 0 | 0 / 0 | 21 / 15 | 0 / 0 | 0 / 0 / 0 / 0 | no |
| **AVA_2** | 71 / 54 | 0 / 0 | 0 / 0 | 10 / 6 | 0 / 0 | 0 / 0 / 0 / 0 | no |
| AVA pooled (sens.) | 116 / 86 | 0 / 0 | 0 / 0 | 23 / 17 | 0 / 0 | 1 / 0 / 0 / 0 | no (even pooled) |
| **WCD** | 34 / 24 | 0 / 0 | 0 / 0 | 10 / 7 | 0 / 0 | 0 / 0 / 0 / 0 | no |

## 3. Reading

- **Distance is not the constraint; development history is.** Every candidate except WCD closes its 10-analog cohort inside the
  5-mi ring for 80–99 % of in-extent PUDs, about as well as BS2_S (93 %). The workups would look as well supported as BS2_S's.
  But the step-9 chain cannot measure their bias: the D53 / D99 rules need packages that first produced 2019–2025, and the AVA
  benches have 4–20 per cutoff.
- **AVA_0 / AVA_1 / AVA_2 cannot be judged under any rule of record, separately or pooled.** Pooled AVA reaches 23 / 17 holdout
  packages at cum-12 / 24 and no tuning cell reaches 30, so there is no walk-forward haircut and no production haircut either
  (one cutoff at cum-12). Coverage would ship a forecast with no measured bias, which D60 / D59 cond. 3 do not allow. Pooling
  AVA_0/1/2 is also a D19-type decision the step-15 QC gate deferred ("separate for now").
  - Rough time to judgeable: pooled AVA adds ~20–27 packages per cutoff year, ~4–5 of them holdout, so the pooled cum-12 holdout
    cell reaches ~30 after 1–2 more cutoffs (Dec 2025 / Dec 2026 cohorts, readable at cum-12 in 2027–2028). Cum-24 takes about
    a year longer.
- **BS2_C can be judged, narrowly, and only as a raw `box_v2` record** (no walk-forward haircut, D97 pattern as WCXY):
  - pooled holdout 46 packages at cum-12 and 34 at cum-24, against the ~30 floor;
  - the walk-forward haircut exists at two cutoffs only, and its holdout pool is 19 / 7, so `box_v2_wf` cannot be judged.
  - Production haircut (D102): 4 cutoffs at cum-12, 2 at cum-24, 1 at cum-36, **0 at cum-48** — so the D92 rate shape has no
    cum-48 knot. A raw record (D97) avoids that question.
  - It is the fastest-growing candidate: 421 of its 650 modern producers came on in 2023+.
  - Its holdout is 22 % of packages, close to the 20 % design; BS2_S's was 24–26 %.
- **WCD stays emerging** (confirms the step-15 QC gate): no extent, 17 PUDs per producer, median 10th-analog distance 14 mi, 75 %
  of PUDs past 10 mi, ≤ 12 packages per cutoff.

## 4. The same lens on the stage-2 "build" benches (they are already decided; this changes how they are scored)

| bench | holdout pooled, all cutoffs, cum-12 / 24 | walk-forward cutoffs, cum-12 / 24 | holdout pooled, wf cutoffs, cum-12 / 24 | D102 cum-48 cutoffs | can be judged |
|---|---|---|---|---|---|
| BS3_S | 166 / 136 | 4 / 4 | 120 / 90 | 1 | as BS2_S (`box_v2_wf`) |
| BS3_C | 107 / 78 | 4 / 4 | 92 / 63 | 1 | as BS2_S (`box_v2_wf`) |
| WCB_1 | 138 / 111 | 4 / 4 | 84 / 57 | 1 | as BS2_S (`box_v2_wf`) |
| **WCB_2** | 74 / 57 | 3 / 3 | 44 / **27** | 1 | `box_v2_wf` holdout judgeable at cum-12 only; raw `box_v2` at cum-12 + 24 |
| **BS1_S** | 58 / 42 | 2 / 2 | **28 / 12** | 0 | raw `box_v2` only (cum-12 + 24) |
| **WCC** | 49 / 35 | **0 / 0** | 0 / 0 | 0 | raw `box_v2` only (cum-12 + 24); only ONE per-cutoff tuning cell reaches 30 (2023 cum-12, 32) |

Consequences for the stage-2 tuning pass (to pre-register before scoring, D52 / D93 pattern):
- **Record variant per bench.** `box_v2_wf` (D94 own haircut) for BS3_S, BS3_C, WCB_1. For WCB_2, BS1_S and WCC — plus BS2_C if
  built — the walk-forward record cannot be judged on its own holdout. The rules allow a raw `box_v2` record (D97, as WCXY was
  accepted); the alternative is a borrowed haircut (e.g. WCA's or a family's), which would be a new decision.
- **Tuning view.** Per-cutoff D53 cells mostly cannot be judged on WCC / BS1_S / BS2_C (≤ 30 packages). The tuning report for
  those benches would be POOLED across cutoffs, in the same form as the D99 cells, plus the 2,000-draw consistency intervals.
- **D92 haircut shape.** With 0–1 cum-48 cutoffs on every thin bench, the D62 / D92 haircut has no measured cum-48 knot. BS2_S had
  one, which carried its −23 % oil EUR tail effect. A raw record avoids this. A haircut record needs a rule for the tail.

## 5. Gate 14 — asks (Michael decides; nothing stored until a separate go)

1. **AVA_0, AVA_1, AVA_2 → emerging (D2).** Recommended: no rule of record can judge them, even pooled. Revisit after the Dec 2025
   / Dec 2026 cohorts reach cum-12 (2027–2028); pooling them would be its own QC decision then.
2. **BS2_C → build or emerging?** Recommendation: **build as a raw `box_v2` record (D97 pattern)**, joining the stage-2 tuning
   pass. Its D99 cells would be cum-12 (46 holdout packages) and cum-24 (34 — marginal: the pre-9b rehearsal measured about ±8 pts of swing at 60–90 packages, wider at 34).
   Emerging is defensible if you want more margin than that.
3. **WCD → stays emerging** (no change; confirms the step-15 QC gate).
4. **Stage-2 pre-registration** (§4), so the tuning pass can run in one go:
   - (a) record variant per bench (`box_v2_wf` for BS3_S / BS3_C / WCB_1; raw `box_v2` for WCB_2 / BS1_S / WCC [/ BS2_C]);
   - (b) pooled tuning cells for the thin benches;
   - (c) D99 cells per bench = the pooled holdout cells that reach 30 packages (cum-12 + cum-24 for all six or seven; cum-36 for
     BS3_S / BS3_C / WCB_1 / WCB_2 only on the raw variant).

   This can instead wait for the tuning gate; the counts above show what that gate will face.

**Storage on a "emerging" answer** (needs your explicit go, not part of this session's read-only scope): `box.bench_scope` set
`in_scope = false` with a D2 reason for each emerging bench. Their extents (28 / 29 / 30) stay stored as context. The next
production run then rows those PUDs `not_covered_emerging` instead of `not_covered_unvalidated`.

Not done here: the `OTHER` / unmapped tag the plan's step-14 text mentions (not in the session brief; it has no
`box.bench_scope` row).

## 6. Gate 14 — DECIDED 2026-10-17 (Michael)

"accept — AVA_0/1/2 emerging, BS2_C build as raw box_v2, WCD stays emerging. Pre-register stage 2 as proposed in FINDINGS §4 and
run the tuning pass."

- **AVA_0, AVA_1, AVA_2 → emerging (D2).** WCD stays emerging. The `box.bench_scope` write (`in_scope = false`) is a live store and
  waits for its own go; the record run keeps rowing them `not_covered_unvalidated` until then.
- **BS2_C → build**, record = raw `box_v2` (D97 pattern).
- **Stage 2 pre-registered** (`box/acceptance.BENCH_SPECS`, committed before any scoring): BS3_S / BS3_C / WCB_1 record
  `box_v2_wf` (D94 own haircut); WCB_2 / BS1_S / WCC / BS2_C record raw `box_v2`. Pool = the step-15 QC set, extent of record,
  no pooling across benches. Thin benches get pooled tuning cells; D99 cells = pooled holdout cells reaching 30 packages
  (from §4), frozen with their consistency intervals at the tuning gate.
