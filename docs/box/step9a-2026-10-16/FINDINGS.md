# BOX step 9a — BS2_S + WCXY tuning view (read-only) — GATE 9a CLOSED 2026-10-16

Review surface: `index.html` (this folder). Built by `python -m scripts.box_tune9a` from the `scripts.box_acceptance --fold analog` runs in
`runs/box9a/` (git-ignored; per-location frames + monthly arrays). Nothing stored; no DDL; no sql number used. Frozen spec `box_v2_wf` (D58)
unchanged; blueox-boxfit @ 3380317; actuals pinned to 2026-07-01 (the scored WCA record's); tuning blocks only, D52 salt unchanged.

## 1. What was built

- **Bench parameter** through the D53 harness: `box/acceptance.BENCH_SPECS` (WCA, BS2_S, WCXY, WCXY_on_WCA sensitivity), `bench=` / `fold=`
  on `acceptance.run`, the deal-intake bench label in `box/analog.select_cohort[_v2]` / `predict_many_v2` (default `WCA`; production code
  untouched), strike diagnostics (`diag=`) as read-only provenance.
- **`backtest_report.run_fold_analog`**: the fold every bench uses — exactly what the v2 analog variants read from `run_fold` (per-well fits of
  pre-cutoff wells inside the extent, D9 training cohort for F(k) + benchmark, next-12-months scored wells), without the retired TC-area / factor
  chain (D66). One "area" = the extent (the D29 areas tile it).
- `--holdout-once` required before `--score-holdout` on any bench other than WCA (9b only).
- Extra variant `box_v2_wf_wca` = box_v2 corrected by WCA's walk-forward haircuts (decision 1).
- `box/tune9a_report.py` + `scripts/box_tune9a.py` (page); `tests/test_box_bench_param.py` (4 DB-free tests).

## 2. Regression guard (plan: "WCA's scored cells reproduce bit-identically")

- **Code: identical.** On the same data, WCA through `fold="analog"` equals the unchanged step-6 `fold="full"` with |diff| = 0.0 on the 2020
  and 2021 tuning cutoffs and the 2021 holdout. The 2020 holdout comparison is not like-for-like: 8 TX wells had `curated.production`
  revised between the two runs (the same afternoon).
- **Record: not bit-identical, because the data moved.** Package and well counts are equal in every cell. Statistics differ by up to 0.003 on
  bias and up to 0.11 on band, and three 2021 holdout spread verdicts flip (box_v2, box_v2_wf, di_p50_wf).
  Cause: `curated.production` revised after 2026-10-14. Against the 7a frames, 13–20 scored wells per cutoff changed cum-12 / cum-24 oil by up to
  4–10 % (laterals and spacing identical). Bit-identity to the 10-14 record is not reachable on revised data.
  **Ask:** accept "code identical + data-drift explained" as the guard, or have me rerun on a dated snapshot.

## 3. Results (box_v2_wf, own walk-forward haircut; tuning view)

| bench | judged cells failing | why |
|---|---|---|
| BS2_S (4,340 wells, extent 7) | 9 / 16 | 8 spread, 1 bias (gas cum-12 2022 −13 %); oil bias −4.1…+3.9 % after the haircut |
| BS2_S with WCA's haircut | 15 / 18 | raw box_v2 is 10–16 % high on BS2_S oil vs WCA's 5–9 % |
| WCXY, WCXY-only analogs (D20) | 9 / 16 | 4 bias, 5 spread; raw box_v2 +10–16 % LOW at 2019–22; radius 15–20 mi common |
| **WCXY on WCXY + WCA_1 (pre-registered 2026-10-16)** | **8 / 16** | 3 bias (all +10–12 %, walk-forward over-correction), 5 spread; raw box_v2 7 / 16 with 0 bias fails (max \|bias\| 7.6 %) |
| WCXY on the whole WCA pool (sensitivity) | 4 / 16 | 3 bias (all from 2021); bands mostly tighter than the benchmark's |

D62-style tables (tuning only, factor = 1 + package-weighted bias) at cum-12/24/36/48:
- BS2_S: oil 0.890 / 0.872 / 0.838 / 0.831; gas 0.926 / 0.899 / 0.879 / 0.816.
- WCA record: oil 0.943 / 0.929 / 0.916 / 0.876.
- D92 C1 realised factors meet the BS2_S targets within ~0.01. The rate factor runs from g(1) ≈ 1.00 to g(48) ≈ 0.70 for oil.

## 4. BS2_S south edge (D55)

The strike search works as designed. On the south edge (within 5 mi of the boundary, bearing 135–225° from the centroid; 74 location-cutoffs):
- it fires on 35 % of locations and reaches past 5 mi on 84 % (median 15 mi);
- the ellipse runs about 29° from the local edge, i.e. along the edge, not across it.

The performance miss remains: south-edge packages come in about 25 % below box_v2_wf at cum-12 (29 packages, thin); the benchmark is −19 % there.
Other edges run +13…+23 % above forecast; the interior is −5 %.

## 5. Gate-9a decisions (recommendations; detail in index.html §5)

1. **Haircut:** per bench (BS2_S its own table).
2. **WCXY analog pool:** adopt the pre-registered WCXY + WCA_1 pool as **D93** (selection only; D20 still governs extents / cohorts; BS3_S after
   15a). It fixes the WCXY-only pool's bias (raw within ±7.6 % everywhere). Not switching to the whole-WCA pool (4 / 16): it was seen before the
   pool was declared. **Open before 9b:** whether WCXY keeps the walk-forward haircut — on this pool the raw curve is unbiased and the haircut
   causes all 3 bias failures; dropping it for WCXY is a spec change.
3. **WCXY extent:** the WCA extent as is. 1,678 / 1,679 WCXY producers and 3,188 / 3,385 WCXY PUDs are inside it; median 1.8 mi to a WCXY producer.
4. **BS2_S south edge:** no spec change. Make the south-edge over-forecast a named watch item for 9b and a stated workup caveat.

Flag for 9b: BS2_S fails the spread test as tuned, so its one-time holdout is likely to fail as written (D59 pattern applies).

## 6. Gate 9a outcome (Michael 2026-10-16)

D93 WCXY analogs = WCXY + WCA_1 (selection only) · D94 per-bench walk-forward haircut (BS2_S its own) · D95 WCXY extent = WCA extent ·
D96 no spec change at the BS2_S south edge (watch item for 9b + workup caveat) · D97 WCXY record = raw box_v2, no walk-forward haircut
(`BENCH_SPECS["WCXY_WCA1"]["record"]`) · D98 guard accepted as code identical + data drift explained. Next: 9b, holdouts scored once —
`--bench BS2_S` (box_v2_wf) and `--bench WCXY_WCA1` (box_v2), both with `--holdout-once`. BS2_S's haircuts must come from its OWN tuning cells (D94):
`--history docs/box/step9a-2026-10-16/cells_tuning_BS2_S.csv` (the default would read WCA's). Same `--wells docs/box/pool-2026-10-15`,
`--fold analog`; pin `--actuals-through` and state it.
