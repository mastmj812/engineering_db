# BOX step 9b — BS2_S + WCXY holdout, scored ONCE under D99 (read-only) — GATE 9b CLOSED 2026-10-17

Review surface: `index.html` (this folder). Scored by `scripts.box_acceptance --fold analog --score-holdout --holdout-once` (frames in `runs/box9b/`,
git-ignored); judged and rendered by `python -m scripts.box_holdout9b` (`box/holdout9b.py`, DB-free judge; `tests/test_box_holdout9b.py`).
Nothing stored; no DDL; no sql number used. Code at 617e3b5 (frozen scoring code = step 9a's; only the D97 `record` field and the D99 judge are new);
blueox-boxfit @ 3380317; pool `docs/box/pool-2026-10-15`; actuals `curated.production` through 2026-07-01 (= the live last full month);
D52 salt unchanged. Runs 2026-10-17 10:25–12:20 UTC; no `meta.etl_log` row overlaps that window (no nightly revision mid-run).

## 1. Verdict (D99)

**BS2_S PASS · WCXY PASS.** Every pooled cell's holdout package bias lies inside its frozen P2.5–P97.5 interval, oil AND gas.
Under D99 the tuning bias therefore stands as the disclosed bias (D59 condition 3).

Error = Σ actual / Σ predicted − 1 per package, mean over packages; **negative = forecast HIGH**.

| bench | cell | holdout pkgs | tuning bias | frozen interval | **holdout bias** | \|bias\| ≤ 10 % | scale-free spread vs bench + 0.05 |
|---|---|---|---|---|---|---|---|
| BS2_S (box_v2_wf, D94) | oil cum-12 | 119 | −1.6 % | −10.8 … +9.1 | **+1.0 %** | yes | 0.80 vs 0.78 ok |
| | oil cum-24 | 88 | +1.8 % | −9.3 … +16.0 | **+4.5 %** | yes | 0.77 vs 0.78 ok |
| | gas cum-12 | 119 | −7.3 % | −17.8 … +3.1 | **−1.7 %** | yes | 0.92 vs 0.98 ok |
| | gas cum-24 | 88 | −5.9 % | −18.2 … +8.3 | **+2.3 %** | yes | 0.85 vs 0.94 ok |
| WCXY (raw box_v2, D93 pool, D97) | oil cum-12 | 108 | −1.0 % | −9.2 … +7.2 | **−5.8 %** | yes | 0.81 vs 0.79 ok |
| | oil cum-24 | 95 | −5.1 % | −13.6 … +3.4 | **−8.7 %** | yes | 0.77 vs 0.80 ok |
| | oil cum-36 | 80 | −9.2 % | −18.7 … +0.3 | **−7.8 %** | yes | **0.74 vs 0.65 — fails (reported only)** |
| | gas cum-12 | 108 | −0.8 % | −10.3 … +10.4 | **−3.5 %** | yes | 0.84 vs 0.84 ok |
| | gas cum-24 | 95 | −3.3 % | −13.1 … +8.1 | **−3.7 %** | yes | 0.76 vs 0.78 ok |
| | gas cum-36 | 80 | −5.4 % | −14.9 … +4.3 | **−1.9 %** | yes | 0.83 vs 0.82 ok |

The reported-only tests: every cell's bias is within ±10 %. One cell fails the D58 spread test: WCXY oil cum-36, where BOX's 0.74 exceeds the benchmark's 0.65 + 0.05.

## 2. Integrity checks

- **Frozen intervals untouched.** `intervals_BS2_S.csv` and `intervals_WCXY_WCA1.csv` are byte-identical to their freezing commit 22650ce. The script refuses to judge otherwise. SHA-256 values are in `frozen_intervals_check.csv`.
- **Same statistic as the intervals.** The holdout bias is computed by `rehearse9b.judge` / `_stats`, the exact function the intervals were drawn with. A test pins this.
- **BS2_S haircuts come from tuning only (D58 / D94).** The holdout's walk-forward haircut equals the step-9a own-bench tuning haircut at every cutoff × stream × horizon (|diff| = 0.0). Example: oil cum-12 −9.4 / −9.9 / −10.8 / −11.1 % at the 2021–24 cutoffs. Table: `walk_forward_identity_BS2_S.csv`.
- **WCXY carries no haircut**, per D97 (`record = box_v2`).
- **No data revision during the runs.** `etl_during_runs.csv` is empty.

## 3. Things to know before reading the verdict

1. **The holdout is bigger than the rehearsal assumed.** The rehearsal drew 20 % of the TUNING packages: BS2_S 87 / 62, WCXY 68 / 58 / 47 at cum-12 / 24 / 36. The actual holdout holds 119 / 88 and 108 / 95 / 80, i.e. 24–26 % of each bench's packages. The salted block hash is geographic, not per bench.
   - Consequence: the frozen intervals are somewhat generous for this sample size.
   - Sensitivity (not the rule): shrinking each interval about its tuning bias by √(n holdout / n rehearsal), a factor of 1.17–1.30, keeps **all 10 cells inside**. The verdict does not depend on the generosity.
2. **The rule as written would have judged almost nothing.** Under the per-cutoff D53 cells (reported only, D99 replaced them):
   - BS2_S: 6 cells judged, 2 fail, both on spread (2022 oil and gas cum-12).
   - WCXY: 0 cells judged (10–25 packages per cutoff).
   - This matches the rehearsal's finding.
3. **WCXY oil runs high.** It is HIGH in every holdout oil cell (−5.8 / −8.7 / −7.8 %), consistent with tuning's −1.0 / −5.1 / −9.2 %. The disclosed WCXY oil cum-36 bias of −9.2 % is near the 10 % tolerance; it is stated on every WCXY workup (pre-9b caveat).
4. **D96 south-edge watch item: confirmed, still thin.** BS2_S holdout, box_v2_wf oil, packages restricted to the region's members:

| region | holdout oil cum-12 (pkgs) | holdout oil cum-24 (pkgs) | benchmark cum-12 / 24 | tuning cum-12 / 24 (9a) |
|---|---|---|---|---|
| south edge (≤ 5 mi, bearing 135–225°) | −30.5 % (9) | −56.3 % (6) | −29.1 / −35.3 % | −25.6 / −24.4 % |
| other edges | +19.9 % (25) | +32.4 % (18) | +22.3 / +18.0 % | +12.6 / +19.1 % |
| interior | −1.2 % (89) | +1.6 % (67) | −8.3 / −8.0 % | −5.4 / −2.6 % |

   - The south edge over-forecasts in both views, and the benchmark does too, so this is a property of the offsets rather than the method.
   - The other edges under-forecast (+13…+32 %) in both views. That is a new, mirror-image observation, and it is why the pooled bench bias is small.
   - Search behaviour matches 9a: strike fires on 49 % of south-edge locations, the ellipse runs ~11° from the local edge (along it), and 88 % reach past 5 mi.

## 4. Gate-9b asks (recommendations)

1. **Accept both benches** (D99 PASS). BS2_S stays on box_v2_wf with its own haircut; WCXY stays on raw box_v2 with the D93 pool. Disclosed bias = the tuning bias per cell (§1), stated on every workup with the D69 radius-class range. → Proceed to 9c.
2. **D96 south edge: keep "no spec change".** The workup caveat for south-edge BS2_S pads should quote the measured numbers: oil cum-12 about −26 % tuning / −31 % holdout, n 29 / 9 packages, benchmark similar. **Your call:** whether the mirror-image "other edges +13…+32 % LOW" also becomes a named watch item and caveat. My recommendation is yes, as text only.
3. **For 9c (not decided here):** BS2_S's production haircut table. WCA's D62 pooled tuning + holdout packages across all cutoffs, and the holdout is now spent, so the same pooling is available for BS2_S (D94: from BS2_S's own packages). WCXY has none (D97). Confirm at the 9c kickoff.

No conflict with §2 found. D99 was applied exactly as recorded: pooled cells, frozen intervals, ±10 % and spread reported only.

## 5. Gate 9b outcome (Michael 2026-10-17)

**D100:** both benches accepted. They enter 9c with disclosed bias = the tuning bias per cell.

**D101:** the D96 south-edge caveat carries the measured numbers (oil cum-12 −26 % tuning / −31 % holdout). The other-edge under-forecast (oil cum-12 +13 % / +20 %) becomes a named watch item and a workup caveat, as text only.

**Next = 9c.** BS2_S's production haircut pooling is to be confirmed at the 9c kickoff.
