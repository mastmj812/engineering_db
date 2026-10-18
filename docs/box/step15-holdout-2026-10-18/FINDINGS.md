# BOX step 15 — one-time D52 holdout of the six accepted step-15 benches — AT THE HOLDOUT GATE

2026-10-18 (runs 03:01–04:37 UTC). Read-only; nothing stored. **Each holdout was scored exactly once** and judged against the FROZEN
D99 rule (`docs/box/step15-tuning-2026-10-17/frozen_d99.csv`). No interval was redrawn and nothing was re-tuned.

- **Review surface:** `index.html`. **Machine verdict:** `verdict.json`. Small CSVs per bench (pooled cells, packages by cutoff,
  per-cutoff D53 cells, edges holdout + tuning, BS3_S walk-forward identity).
- **Builder:** `python -m scripts.box_holdout15 --tuning-runs <step-15 tuning runs>` (`box/holdout15.py`, 5 DB-free tests). It judges with
  `box/holdout9b.pooled_cells` / `verdict`, unchanged — the statistic the intervals were drawn with.
- **Scoring:** `python -m scripts.box_acceptance --bench <B> --fold analog --score-holdout --holdout-once --wells <step-15 folder>
  --history docs/box/step15-tuning-2026-10-17/cells_<B>.csv --workers 6 --actuals-through 2026-07-01`, into `runs/box15h/<B>/`
  (git-ignored). Code = 06acc37 (PR #152 merge; box/acceptance.py differs from the 691e964 pre-registration only in BENCH_SPECS);
  blueox-boxfit @ 3380317; 20–66 min per bench, three in parallel.

**Sign convention (every D53 table):** bias = Σ actual / Σ forecast − 1, so **+ = forecast LOW** (conservative), **− = forecast HIGH**.

## 1. Verdicts (D99: every frozen cell's pooled holdout bias inside its frozen P2.5–P97.5 interval)

| bench (record) | verdict | outside | oil holdout cum-12 / 24 / 36 | gas holdout cum-12 / 24 / 36 | packages (oil) | rule catches a 15 %-high forecast |
|---|---|---|---|---|---|---|
| BS3_S (`box_v2_wf`) | **FAIL** | oil cum-12 (+12.1 % vs ≤ +9.9 %) | **+12.1** / +15.1 | −4.4 / −2.3 | 119 / 89 | 84 % |
| BS3_C (raw) | **FAIL** | gas cum-12 (−14.9 vs ≥ −9.1), gas cum-24 (−11.3 vs ≥ −7.7) | −14.1 / −9.7 / +3.2 | **−14.9 / −11.3** / −4.7 | 96 / 66 / 32 | 78 % |
| WCB_1 (raw) | **PASS** | — | +1.0 / −2.9 / −13.2 | +12.3 / +21.2 / +34.4 | 137 / 110 / 90 | 92 % |
| WCB_2 (raw) | **FAIL** | gas cum-12 (+20.6 vs ≤ +10.5), gas cum-24 (+26.4 vs ≤ +14.7) | +7.1 / +3.6 | **+20.6 / +26.4** | 60 / 43 | 88 % |
| BS1_S (raw) | **FAIL** | gas cum-12 (−15.8 vs ≥ −12.2) | −20.9 / −11.3 | **−15.8** / −3.8 | 48 / 31 | 56 % |
| WCC (raw) | **PASS** | — | −1.4 / −8.1 | −10.7 / −10.6 | 45 / 31 | 54 % |

Counts match the corrected tuning FINDINGS §2 expectations: BS3_S 119 / 89 vs 120 / 90; BS3_C 96 / 66 / 32 exactly; WCB_1 137 / 110 / 90
vs 132 / 105 / 65; WCB_2 60 / 43 vs 62 / 46; BS1_S 48 / 31 vs 49 / 32; WCC 45 / 31 vs 48 / 34.

**Rule power (from the frozen tuning draws).** On BS1_S and WCC the rule catches a 15 % miss only **56 % / 54 %** of the time. **WCC's PASS
is therefore weak evidence:** a forecast 15 % high would pass about half the time. BS1_S's FAIL is a thin-sample result in the
same sense; the holdout holds 48 / 31 packages.

### Reported, not gating (D99): ±10 % bias and the D58 scale-free spread

| bench | cells with \|bias\| > 10 % | spread fails (scale-free band > benchmark + 0.05) |
|---|---|---|
| BS3_S | oil 12 (+12.1), oil 24 (+15.1) | oil 24 (0.98 vs 0.89) |
| BS3_C | oil 12 (−14.1), gas 12, gas 24 | oil 12, gas 12, gas 36 |
| WCB_1 | oil 36 (−13.2, disclosed −13.3 in tuning), gas 12 / 24 / 36 (LOW, disclosed) | oil 36, gas 12 / 24 / 36 |
| WCB_2 | gas 12, gas 24 | gas 12 |
| BS1_S | oil 12 (−20.9), oil 24 (−11.3), gas 12 | oil 24, gas 12 |
| WCC | gas 12 (−10.7), gas 24 (−10.6) | oil 12, oil 24, gas 24 |

## 2. The two passes

- **WCB_1 PASS, 6 / 6.** Every holdout cell lands on its tuning bias: oil +1.0 / −2.9 / −13.2 % against tuning −2.5 / −3.1 / −13.3 %. Gas
  is LOW at +12 / +21 / +34 % against tuning +11 / +19 / +35 %. This is the strongest result in the set: 137 packages, and the rule
  catches a 15 % miss 92 % of the time. The tuning-gate disclosures hold as written: oil cum-36 is ~13 % HIGH; gas runs LOW.
- **WCC PASS, 4 / 4, weak evidence.** Oil holdout is −1.4 / −8.1 % against tuning −3.6 / −12.2 %. Gas is −10.7 / −10.6 % against tuning
  −5.1 / −7.5 %, so gas sits slightly past the ±10 % line and is HIGH. Rule power is 54 %. The pad-level edge caveats stay (§4).

## 3. The four FAILs — first-pass diagnosis (7a pattern; nothing re-tuned)

**BS3_S — oil cum-12 +12.1 % (forecast LOW, conservative); the walk-forward haircut drove it.**
- On the same holdout packages, raw `box_v2` is **+5.4 % oil-12 / +8.1 % oil-24** at the haircut cutoffs (2021–24). The D94
  haircut is applied as tuned: it is identical to the tuning table at all 48 (cutoff, stream, horizon) entries. It
  multiplies the oil forecast by ~0.93–0.95, which turns +5 % into +12 %.
- The local-offsets benchmark is +0.9 % here, so the holdout wells are not unusually strong for their neighbours. On this
  geography BOX raw was already slightly low, and the haircut assumed it would be ~6 % high.
- By cutoff (oil-12): 2021 +19.7 %, 2022 +3.9 %, 2023 +16.7 %, 2024 +4.5 %. 2021 and 2023 carry it. Interior +14.9 % (83 packages).
- Gas passes (−4.4 / −2.3 %).
- **The failure is in the conservative direction** (forecast LOW).
- Reading: the haircut is not stable out of sample on BS3_S, although the tuning view called it the best-behaved haircut of the set.
- **Not done (D99):** switching to raw now would be choosing a variant after the look. That is your call, not a diagnosis
  outcome. The raw number is given only to locate the failure.

**BS3_C — gas cum-12 / 24 −14.9 / −11.3 % (forecast HIGH); mostly shared with the benchmark.**
- Benchmark gas on the same packages: −8.9 / −7.9 %. Oil-12 (−14.1 %, inside its interval) has benchmark −12.8 %. BOX tracks
  the local offsets within 2–6 pt.
- The holdout blocks are poorer than the tuning blocks on both streams:
  - The 2021–23 cutoffs run −23…−26 % gas-12 (benchmark −14…−20 %).
  - The 2020 cutoff runs +37 % (8 packages).
- Tuning had gas LOW (+6 / +12 %). The holdout flips it to HIGH. **The tuning-gate disclosure "BS3_C gas runs LOW" is not supported
  out of sample.**
- Oil interior is −12.1 % (benchmark −11.1 %); W / N edges −27 / −18 %.
- Diagnosis lead: a geographic property of the holdout blocks, shared with the benchmark. BOX adds ~6 pt of gas over-forecast on top.

**WCB_2 — gas cum-12 / 24 +20.6 / +26.4 % (forecast LOW, conservative); the benchmark is worse.**
- Benchmark gas on the same packages: +24.1 / +32.5 %. So the holdout wells make more gas than any offset set predicts. This is
  the GOR-rise watch item (tuning §7 item 8) appearing on WCB_2's holdout. Tuning gas was −3.7 / −2.5 %.
- By cutoff (gas-12): 2023 +44 % (14 packages), 2021 +33 %, 2022 +18 %; gas-24 2023 +90 % (9 packages).
- Oil is fine: +7.1 / +3.6 %, inside, |bias| ≤ 10 %. The S-edge oil caveat repeats: −7.7 % (24 packages), tuning −12.6 %.
- Diagnosis lead: the deal-intake gas Arps P50 (D57) misses the GOR rise. It is shared and conservative. A gas method change would
  carry its own acceptance (tuning §7 item 8); it is not proposed here.

**BS1_S — gas cum-12 −15.8 % (forecast HIGH, just past ≥ −12.2 %); oil −20.9 % inside its wide interval.**
- Benchmark gas-12 −14.2 %, so the gas miss is shared.
- Oil-12 −20.9 % against benchmark −11.2 % is not shared. It is **twice the disclosed ~10 % oil over-forecast**; tuning was −10.1 %. Oil-24
  −11.3 % matches tuning −10.3 %.
- By cutoff (oil-12): 2024 −33 % (14 packages; benchmark −34 %, shared), 2021 −24 %, 2022 −20 % (benchmark +2 %, not shared).
- Interior −17.7 % (benchmark −6.0 %); N / E edges −29 / −56 % (7 / 2 packages).
- Thin: 48 / 31 packages, and the rule power is 56 %.
- Diagnosis lead: the method over-forecasts BS1_S oil-12 by more than disclosed, and the gas fail is shared and borderline. The
  evidence is thin either way.

## 4. Edges (D101 pattern; within 5 mi of the extent boundary; oil, record variant, holdout vs tuning)

| bench | interior oil-12 holdout / tuning | edges that over-forecast on the holdout (oil-12, packages) | tuning, same edge |
|---|---|---|---|
| BS3_S | +14.9 / +2.3 % (83) | S −21.4 % (5); E −2.9 % (7) | S −19.7 %; E −2.7 % |
| BS3_C | −12.1 / −3.2 % (67) | W −26.8 % (8), S −22.4 % (4), N −17.9 % (13) | W −9.2, S −5.3, N −10.6 % |
| WCB_1 | +3.1 / +3.1 % (100) | S −18.4 % (13), E −3.0 % (6) | S −24.2, E −14.6 % |
| WCB_2 | +15.2 / +8.1 % (31) | S −7.7 % (24) | S −12.6 % |
| BS1_S | −17.7 / −7.1 % (39) | N −28.9 % (7), E −55.7 % (2) | N −19.8, E −20.3 % |
| WCC | −0.6 / +9.2 % (26) | N −22.8 % (9), S −36.0 % (2) | N −14.4, S −32.9 % |

The D101 pattern recurs, though holdout edge cells are small (2–24 packages):
- The S edge over-forecasts wherever it has packages: BS3_S, WCB_1, WCB_2, WCC.
- On BS3_S / WCB_2 the interior runs LOW.
- The benchmark shares the edge misses: BS3_S S −23 %, WCB_1 S −18 %, WCB_2 S −15 %, WCC N −18 %.

Two exceptions:
- **WCC's E edge** reversed: holdout +21 % on 9 packages, against tuning −23 %; benchmark +26 %.
- **BS3_C** is low or flat in the interior and over-forecasts everywhere, consistent with its poorer holdout blocks (§3).

The tuning edge tables here are recomputed from the tuning frames for the frozen variant. This gives a like-for-like comparison for
BS3_C / WCB_1, whose tuning page tabulated `box_v2_wf`.

## 5. Integrity

- **Frozen intervals:** all six source files match `frozen_d99.csv` by SHA-256 (LF) and by value. `box/holdout15.load_frozen` refuses to
  judge otherwise (test pins it).
- **BS3_S walk-forward:** the holdout haircuts equal the tuning table at 48 / 48 entries. Only the 2021–24 cutoffs score; 2019 / 2020
  have no haircut, hence no prediction (`packages_by_cutoff_BS3_S.csv`).
- **ETL:** no `meta.etl_log` row overlaps 03:01–04:37 UTC. The last refresh finished 2026-10-17 15:26 UTC, and actuals are capped at 2026-07-01
  regardless.
- **One aborted launch, nothing scored.** The first launch of the five raw benches omitted `--history`. The harness reads walk-forward
  history from `<out>/cells_tuning_v2.csv` by default, which doesn't exist in a fresh out folder, so they would have died at the end
  of scoring. They were stopped 1–4 min in, before any fold finished and before any file was written. Logs are in
  `runs/box15h/aborted/`, and the out folders were deleted empty. They were relaunched with `--history` = each bench's tuning cells.
  For a raw record this only feeds the non-record `box_v2_wf` column. The single holdout score per bench is the one reported here.
  - Tooling note for run 9 / future holdouts: pass `--history` for every bench, raw included.

## 6. Holdout-gate asks (Michael) — per bench

1. **WCB_1 → accept** (PASS 6 / 6, strongest evidence). Disclosures as frozen: tuning bias per cell; oil cum-36 −13 % (HIGH); gas
   LOW +11 / +19 / +35 %. Enters run 9.
2. **WCC → accept with the weak-evidence caveat** (PASS 4 / 4, rule power 54 %). Disclosures as frozen: tuning bias plus pad-level edge caveat
   with that side's number. Add: gas ~−11 % on the holdout, which is HIGH and just past ±10 %. The E-edge reversal (+21 %, 9 packages) is reported, not a caveat.
3. **BS3_S → diagnose** (FAIL on oil cum-12, forecast LOW by 12 %; the haircut is the driver, §3). The rule says diagnose, never
   re-tune. Your call is between: (a) a deeper 7a-style dig into why the 2021 / 2023 holdout cutoffs run high, before deciding; (b) a
   decision on the record. Raw `box_v2` or a different haircut would be a post-look variant change, which D99 forbids as a
   diagnosis outcome. The D105 provisional tier is the existing route for a bench forecast without a passed holdout.
4. **BS3_C → diagnose** (FAIL on gas cum-12 / 24, forecast HIGH ~11–15 %, mostly shared with the benchmark). At minimum the "gas runs
   LOW" disclosure is wrong out of sample and cannot ship as written.
5. **WCB_2 → diagnose** (FAIL on gas cum-12 / 24, forecast LOW +21 / +26 %, benchmark +24 / +33 %; oil excellent). This is the GOR-rise watch
   item, and conservative. Your call: diagnose the gas method (its own acceptance), or decide the bench's standing with oil passing.
6. **BS1_S → diagnose** (FAIL on gas cum-12, borderline and shared; oil-12 −21 % is twice the disclosed over-forecast; thin, rule power
   56 %).

Until you decide, run 9 can include only WCB_1 and WCC from this gate.

## 7. Holdout gate — DECIDED 2026-10-18 (Michael)

"accept these four as fails" → **option 2: the D105 provisional tier**, not null.

| bench | standing | record for run 9 | coverage |
|---|---|---|---|
| WCB_1 | **validated** (PASS 6 / 6) | raw `box_v2` | `covered` |
| WCC | **validated** (PASS 4 / 4; weak-evidence caveat, rule power 54 %) | raw `box_v2` | `covered` |
| BS3_S | **FAIL → provisional** | raw `box_v2`, no haircut (leaves `box_v2_wf` by tier change, not as a variant picked after the look) | `covered_provisional` |
| BS3_C | **FAIL → provisional** | raw `box_v2` | `covered_provisional` |
| WCB_2 | **FAIL → provisional** | raw `box_v2` | `covered_provisional` |
| BS1_S | **FAIL → provisional** | raw `box_v2` | `covered_provisional` |

- **No re-tune, no redraw.** The FAILs stand as scored. `box/tune15_report.FROZEN` keeps the variant each holdout was scored on.
  `box/acceptance.BENCH_SPECS` now marks the four `provisional: True`, `record = box_v2`, and the tests pin both.
- **Disclosure** (`provisional/`, `python -m scripts.box_provisional_disclosure --set holdout15`). This uses the D105 method, raw `box_v2`
  (pooled package bias, 95 % 3-mi-block cluster bootstrap, by vintage), measured three ways: tuning, holdout, and both pooled. Unlike the
  D105 benches, these four HAVE an out-of-time number and it failed, so a workup must not show the pooled figure alone. The pooling
  dilutes the holdout miss: WCB_2 gas-12 reads +1.8 % pooled vs **+20.6 %** on the holdout.
  - **Proposed workup line** (to confirm with run 9): pooled bias + range, then the holdout line, then the latest-vintage line.

  | bench | oil cum-12 / 24: tuning · holdout · pooled | gas cum-12 / 24: tuning · holdout · pooled |
  |---|---|---|
  | BS3_S (raw) | −6.2 / −3.2 · **+5.5 / +6.6** · −3.2 / −0.7 % | +5.2 / +10.5 · +6.4 / +7.5 · +5.5 / +9.7 % |
  | BS3_C | −5.0 / −2.9 · **−14.1 / −9.7** · −7.0 / −4.4 % | +6.4 / +11.8 · **−14.9 / −11.3** · +1.8 / +6.6 % |
  | WCB_2 | +1.2 / +0.6 · +7.1 / +3.6 · +2.5 / +1.2 % | −3.7 / −2.5 · **+20.6 / +26.4** · +1.8 / +3.9 % |
  | BS1_S | −10.1 / −10.3 · **−20.9 / −11.3** · −12.4 / −10.5 % | +4.4 / +15.1 · **−15.8 / −3.8** · +0.3 / +10.9 % |

  BS3_S raw on the holdout counts every scored cutoff (160 / 130 packages), not only the four that had a haircut.
- **Live write — APPLIED 2026-10-18 (Michael's go):** `box.bench_scope.validation = 'provisional'` for BS3_S, BS3_C, WCB_2, BS1_S
  (`bench_scope_provisional.sql`; four rows, one transaction, before/after asserts passed). Verified live read-only: 8 provisional
  (AVA_0 / 1 / 2, BS2_C, BS3_S, BS3_C, WCB_2, BS1_S) / 10 validated, WCB_1 + WCC unchanged.
- **Run 9** then carries:
  - validated: WCA, BS2_S, WCXY, WCB_1, WCC;
  - provisional: AVA_0 / 1 / 2, BS2_C, BS3_S, BS3_C, WCB_2, BS1_S;
  - the 9c haircut guard, which now has no step-15 wf bench to guard.
