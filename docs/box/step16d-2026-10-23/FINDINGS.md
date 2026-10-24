# Step 16d — r2 production build + container rehearsal (2026-10-23 / 24). NOTHING stored live.

Stack approved by Michael 2026-10-23 (D121 / D122):
- r2 selection on all 13 benches;
- measured spacing (D119);
- the proximity layer re-measured on the new run (D116);
- walk-forward haircut on WCA oil (gas none, D122) and BS2_S oil + gas, from the r2 + proximity tuning cells (D120 §4);
- thin-control disclosure.

## 1. Build (read-only; `runs/box16d`, 26,375 s)

`python -m scripts.box_pud_run build --selection r2 --wells docs/box/pool-2026-10-15 --benches <13 groups> --workers 14 --out runs/box16d`
at 379e2ad (clean); cutoff 2026-08-01, production through 2026-07-01, Novi 2026Q3.

- **Universe 121,696 PUDs** (run 10: 121,727; reconciliation since); **in-extent 51,419; every one forecast — 0
  `not_covered_no_analogs`** (run 10: 480).
- **Harness equivalence 0.0 on every bench** (24 sampled PUDs each): production r2 = the 16c harness's `box_v2s_r2` exactly.
- **9c haircut guard:**
  - table half: WCA oil 0.951 / 0.928 / 0.897 / 0.851; BS2_S oil 0.933 → 0.849, gas 0.987 → 1.075.
  - tail half (median rate factor from month 48 on): WCA oil 0.677; BS2_S oil 0.672, gas 1.146.
  - All pass.

## 2. Water (read-only build, `runs/box16d_water`, 2,522 s)

D107 method unchanged, on the new raw r2 oil (D108). 51,419 PUDs, 0 ratio failures.

## 3. Container rehearsal (`scripts.box_rehearsal`: throwaway PostGIS on :5437, seeded READ-ONLY from live box state)

| step | result |
|---|---|
| `box_pud_run store --record` → **run 17** (r2 base) | pud_forecast 121,696 = universe; per group covered (+ provisional) = in-extent universe, 0 no_analogs; 51,419 oil + 51,419 gas streams; every stream 600 months = its EUR (≤ 0.1 %); every PUD ≥ 4 named analogs. 892 s |
| `box_water_run store --run-id 17` | 51,419 water streams (validated 9,310 = WCA + BS2_S covered; provisional 42,109); oil / gas rows + 61.7 M month rows unchanged (ordered md5); ≥ 3 water analogs each; 49 calculated-fallback. 394 s |
| `box_step16d prox-measure --run-id 17` (D116 re-measure) | 51,419 PUDs, 331,392 links; haircut 9,779, single-parent 7,002, unexposed 26,189, no-forecast 8,449 (precedent 3,869 + package 4,580); identity true. `docs/box/step16d-2026-10-23/prox/` |
| `box_prox_record store --src-run 17 --outcomes … --commit --record` → **run 18** (record) | coverage = source with the 8,449 no-precedent moves; 42,970 streams per stream; oil 22,623.315 MMbbl = source × factor; gas / water rows identical; 77,346,000 month rows; haircut oil months = source × factor (0 off); analogs 604,208, water analogs 704,032 = survivors; 73,439 named parents; run 17 untouched; run 18 the one record. 1,175 s |

## 4. Run 18 (rehearsal) vs live run 14, oil

| bench | PUDs 14 → 18 | oil MMbbl 14 → 18 | median oil EUR / kft | inside the 5-mi ring |
|---|---|---|---|---|
| WCA (+ WCXY) | 5,025 → 5,026 | 3,004 → 2,881 (−4.1 %) | 69.8 → 66.8 k (−4.3 %) | 77 → 98 % |
| BS2_S | 7,044 → 7,078 | 3,457 → 3,250 (−6.0 %) | 56.2 → 53.4 k (−5.1 %) | 56 → 96 % |
| WCB_1 | 3,982 → 3,991 | 2,107 → 2,063 (−2.1 %) | 62.6 → 61.1 k (−2.4 %) | 54 → 98 % |
| WCC | 1,769 → 1,773 | 761 → 740 (−2.8 %) | 46.1 → 44.8 k (−2.8 %) | 24 → 92 % |
| AVA_0 | 351 → 350 | 208 → 208 (+0.3 %) | 79.2 → 80.9 k (+2.1 %) | 50 → 100 % |
| AVA_1 | 951 → 951 | 554 → 564 (+1.8 %) | 68.0 → 68.9 k (+1.3 %) | 54 → 95 % |
| AVA_2 | 1,755 → 1,765 | 1,022 → 956 (−6.5 %) | 67.7 → 62.6 k (−7.5 %) | 32 → 98 % |
| BS2_C | 2,139 → 2,148 | 1,324 → 1,287 (−2.8 %) | 73.2 → 69.1 k (−5.7 %) | 27 → 94 % |
| BS3_S | 5,561 → 5,580 | 3,195 → 3,148 (−1.5 %) | 69.8 → 67.5 k (−3.3 %) | 41 → 83 % |
| BS3_C | 7,137 → 7,167 | 3,658 → 3,377 (−7.7 %) | 59.0 → 53.9 k (−8.7 %) | 33 → 86 % |
| WCB_2 | 2,293 → 2,315 | 1,186 → 1,193 (+0.6 %) | 61.6 → 61.0 k (−0.9 %) | 28 → 94 % |
| BS1_S | 4,468 → 4,826 | 2,825 → 2,957 (+4.7 %) | 73.0 → 70.4 k (−3.5 %) | 19 → 60 % |
| **total** | **42,475 → 42,970** | **23,300.1 → 22,623.3 (−2.9 %)** | | |

EUR = the raw 50-yr technical integral × haircut × proximity factor, uptime-free (D63). BS1_S's total rises with +358 forecast PUDs
(r2 finds analogs where run 10 had none, and fewer of its PUDs fall to no-precedent) while its per-ft median falls.

## 5. Going live (each a GO from Michael; off-hours)

1. `box_pud_run store --out runs/box16d --record` (~15 min). The base run becomes the record until step 4 lands, so erebor shows it
   without the proximity layer for that window (~45 min).
2. `box_water_run store --out runs/box16d_water --run-id <new>` (~7 min).
3. `box_step16d prox-measure --run-id <new> --box-db live` (~10 min). Live location ids should equal the container's; if they don't,
   this file set is replaced by the live measure and committed.
4. `box_prox_record store --src-run <new> --outcomes docs/box/step16d-2026-10-23/prox/pud_outcomes.csv.gz --runs runs/box16d_prox`,
   first as the default rollback rehearsal, then `--commit --record` (~20 min each).
5. Then:
   - prune the base run (D104: never record-for-good, never priced);
   - run 14 stays, because Steven priced it;
   - Steven re-prices the new record;
   - an erebor PR for its hard-coded group labels ("box_v2_wf, D62 walk-forward haircut" → D121);
   - the step-13 refresh rescope (queued).

**Disk:** live is 111 GB (`pud_forecast_month` 30 GB). Steps 1–4 add roughly 20–25 GB (~170 M month rows: base + proximity
run). Pruning the base run returns ~half to Postgres for reuse, not to the disk.
