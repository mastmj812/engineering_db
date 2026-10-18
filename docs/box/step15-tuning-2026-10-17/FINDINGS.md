# BOX step 15, stage 2 — tuning view for the remaining Delaware benches — AT THE TUNING GATE

2026-10-17. Read-only; nothing stored; no holdout package was scored (D52 salt unchanged).

- **Review surface:** `index.html`.
- **Builder:** `python -m scripts.box_tune15` (`box/tune15_report.py`, 4 DB-free tests). It reads the seven
  `scripts.box_acceptance --bench <B> --fold analog --actuals-through 2026-07-01` runs in `runs/box15t/<B>/` (git-ignored).
- **Run cost:** 26–78 min each at `--workers 6`, three in parallel.
- **Code:** 691e964 (pre-registration commit, made before any score); blueox-boxfit @ 3380317.

**Sign convention (as every D53 table):** bias = Σ actual / Σ forecast − 1, so **+ = forecast LOW** (conservative), **− = forecast HIGH**.
Bands are scale-free (D58) and compared with the local-offsets benchmark + 0.05.

## 1. What ran (gate-14 pre-registration, `box/acceptance.BENCH_SPECS`)

| bench | pool (step-15 QC set) | extent | record pre-registered |
|---|---|---|---|
| BS3_S | 3,041 wells | 16 | `box_v2_wf` (D94 own haircut) |
| BS3_C | 1,818 | 18 | `box_v2_wf` |
| WCB_1 | 1,820 | 22 | `box_v2_wf` |
| WCB_2 | 1,181 (consensus tags + 98 overrides) | 24 | raw `box_v2` (D97 pattern) |
| BS1_S | 1,158 | 26 | raw `box_v2` |
| WCC | 1,118 | 27 | raw `box_v2` |
| BS2_C | 708 | 20 | raw `box_v2` |

Every run scores both variants. The page shows the alternative next to the record, and freezes D99 intervals for both, so the
gate can switch variant on tuning evidence without re-running anything.

## 2. A correction to step 14's holdout counts

Step 14 counted every package as scoreable. The harness scores fewer at early cutoffs: the as-of analog pool is thin there
(BS3_C had 34 training wells at the 2019 cutoff, and 37 of its 49 scored wells got no prediction), and a walk-forward haircut needs two
earlier JUDGED cutoffs. Applying the gate-14 rule (D99 cell = pooled holdout ≥ 30) to the counts each variant can actually
score — step-14 holdout counts × the variant's scored share per cutoff, no holdout read (`expected_holdout_*.csv`) — gives:

| bench | record | expected scored holdout, cum-12 / 24 / 36 | D99 cells (oil + gas) |
|---|---|---|---|
| BS3_S | box_v2_wf | 120 / 90 / 23 | cum-12, 24 |
| BS3_C | box_v2_wf | **48 / 19 / 0** | **cum-12 only** (walk-forward exists only at 2023–24) |
| BS3_C | raw (alt) | 96 / 66 / 32 | cum-12, 24, 36 |
| WCB_1 | box_v2_wf | 84 / 57 / 37 | cum-12, 24, 36 |
| WCB_1 | raw (alt) | 132 / 105 / 65 | cum-12, 24, 36 |
| WCB_2 | raw | 62 / 46 / 29 | cum-12, 24 |
| BS1_S | raw | 49 / 32 / 6 | cum-12, 24 |
| WCC | raw | 48 / 34 / 23 | cum-12, 24 |
| BS2_C | raw | 42 / **27** / 15 | **cum-12 only** |

The tuning-time analog radius is also much longer than production's: 74–87 % of tuning locations reach past 5 mi, against 76–99 %
of today's PUDs closing inside 5 mi (step 14). The old cutoffs had thin pools, so the tuning view is the pessimistic one on
proximity. The D69 radius-class disclosure carries this.

## 3. Results — pooled tuning cells (every tuning package, all cutoffs; record variant unless noted)

| bench / variant | oil cum-12 / 24 / 36 | gas cum-12 / 24 / 36 | pooled cells judged / fail | per-cutoff judged / fail |
|---|---|---|---|---|
| **BS3_S box_v2_wf** | −0.4 / +4.4 / +1.6 % | −2.1 / +5.5 / −4.2 % | **6 / 0** | 16 / 5 |
| BS3_S raw (alt) | −6.2 / −3.2 / −1.7 % | +5.2 / +10.5 / +10.6 % | 6 / 2 | — |
| BS3_C box_v2_wf | +0.2 / −7.4 / — | +13.1 / +20.7 / — | 4 / 3 | 6 / 4 |
| **BS3_C raw (alt)** | −5.0 / −2.9 / +10.6 % | +6.4 / +11.8 / +19.4 % | 6 / 4 | — |
| WCB_1 box_v2_wf | +5.0 / +11.8 / +25.8 % | −9.2 / −12.0 / −20.2 % | 6 / 4 | 18 / 12 |
| **WCB_1 raw (alt)** | −2.5 / −3.1 / −13.3 % | +11.4 / +18.9 / +35.4 % | 6 / 4 | — |
| **WCB_2 raw** | +1.2 / +0.6 / +3.7 % | −3.7 / −2.5 / −2.7 % | **6 / 1** (gas-12 spread) | 18 / 11 |
| BS1_S raw | **−10.1 / −10.3** / +5.2 % | +4.4 / +15.1 / +5.0 % | 6 / 3 | 12 / 8 |
| WCC raw | −3.6 / **−12.2 / −14.4** % | −5.1 / −7.5 / −6.3 % | 6 / 4 | 2 / 0 (only 2 cells reach 30) |
| BS2_C raw | **−7.5 / −22.5 / −32.5** % | +5.7 / −16.5 / −28.0 % | **6 / 6** | 12 / 12 |

Benchmark (local offsets, same packages) for reference: BS2_C oil −3.5 / −10.6 / −21.2 %; WCC −10.5 / −19.2 / −27.3 %; BS1_S −3.1 /
−5.6 / −8.1 %. The thin benches' over-forecast is shared by the plain offset look, as on the BS2_S south edge (D101). It is a
property of the data, not of the method.

## 4. Walk-forward haircuts, D62 tables, D92 realised factors

- **BS3_S** walk-forward is stable and small: oil −5…−7 % at cum-12/24, gas +5…+10 %. D62 tuning table: oil 0.938 / 0.968 /
  0.983 / 0.941, gas 1.052 / 1.105 / 1.106 / 0.992. D92 realised meets the targets within ~0.03, and the tail is g(48) = 0.995.
  This is the haircut working as designed.
- **BS3_C** haircut exists only at 2023–24. The D62 table is non-monotone: oil 0.915 / 0.919 / **1.106** (cum-36 rests on two
  cutoffs, 113 packages). The D92 rate shape then fits g(1) = 0.51 → **g(48) = 1.48**, i.e. the tail would be inflated ~48 %.
  Defect: the C1 log-fit extrapolates whatever slope thin knots give it.
- **WCB_1** walk-forward over-corrects in opposite directions: oil +5 / +12 / +26 % (forecast too LOW after the haircut) and gas
  −9 / −12 / −20 % (too HIGH). The D62 haircut is oil 0.975 / 0.969 / 0.867 / **0.742** and gas 1.114 / 1.189 / **1.354** / 1.252, and the
  D92 tails are **oil 0.40, gas 1.60**. Same defect class as BS3_C.
- Raw-record benches carry no haircut (D97). Their D62 tables (`d62_by_bench.csv`) are information only. BS2_C's (oil 0.907 /
  0.764 / 0.632) shows the size of its miss.

## 5. Edges (within 5 mi of the extent boundary, by compass side; oil, record variant)

| bench | interior oil-12 / 24 | edges that over-forecast (oil-12, packages) | benchmark on those edges |
|---|---|---|---|
| BS3_S | +2.3 / +7.0 % | S −19.7 % (10), W −12.9 % (21) | −25 / −16 % |
| BS3_C | +2.4 / −5.8 % | W −12.2 % (18) | −0.1 % |
| WCB_1 | +10.3 / +18.4 % | S −15.3 % (23) | −20.8 % |
| WCB_2 | +8.1 / +11.2 % | **S −12.6 / −14.8 % (65 / 56)** | −21.9 / −25.4 % |
| BS1_S | −7.1 / −9.1 % | N −19.8, E −20.3, S −56 % (18 / 15 / 5) | −15 / −5 / −11 % |
| WCC | +9.2 / −0.2 % | N −14, E −23, S −33, W −29 % (19 / 14 / 11 / 10) | −21 / −12 / −27 / −33 % |
| BS2_C | −9.5 / −23.3 % | S −12.2 % (41); N −34 % at cum-24 (11) | −4 / −21 % |

The D101 pattern holds on every bench: edges over-forecast and the interior runs low or flat, and the benchmark sees the same thing.
WCC's extent is small (1,455 sq mi), so its pooled number is edge-weighted; its interior is within ±10 %. The D55 strike search
fires on 19–33 % of locations; the median strike-vs-edge angle is under 45° on most edge sides (along the edge), but 57–78° on the N edges of WCB_1 / WCB_2 / WCC.

## 6. FROZEN D99 consistency intervals (for the one-time holdout; never redrawn)

2,000 random 20 % draws of 3-mi blocks of the TUNING packages, P2.5–P97.5 (`box/rehearse9b.consistency`, seed 5). Files:
`intervals_<bench>.csv` for the record variant, `intervals_<bench>_alt_<variant>.csv` for the alternative. The `d99_cell`
column marks the judged cells under §2. The intervals below are for the variants recommended in §7:

| bench (variant) | oil cum-12 | oil cum-24 | oil cum-36 | gas cum-12 | gas cum-24 | gas cum-36 |
|---|---|---|---|---|---|---|
| BS3_S (wf) | −10.2…+9.9 | −6.7…+16.7 | — | −16.8…+14.9 | −13.4…+27.4 | — |
| BS3_C (raw) | −16.1…+6.6 | −13.9…+10.5 | −6.5…+29.0 | −9.1…+24.3 | −7.7…+37.6 | −8.9…+70.6 |
| WCB_1 (raw) | −11.2…+4.8 | −12.9…+5.4 | −23.6…−3.8 | −5.4…+27.6 | −0.8…+38.5 | +8.7…+63.6 |
| WCB_2 (raw) | −8.2…+10.1 | −11.1…+13.0 | — | −18.3…+10.5 | −18.3…+14.7 | — |
| BS1_S (raw) | −23.6…+6.6 | −26.5…+14.2 | — | −12.2…+20.6 | −7.1…+38.4 | — |
| WCC (raw) | −21.5…+17.4 | −33.2…+10.8 | — | −19.3…+9.9 | −22.5…+8.9 | — |

How well the rule discriminates, on the same draws: it passes a forecast as good as tuning 82–92 % of the time on every bench. It
catches a 15 %-high forecast 78–92 % of the time where the holdout is big (BS3_S, WCB_1, WCB_2, BS3_C raw, WCB_1 raw), but only
44–56 % on BS1_S / WCC / BS3_C wf, and 34 % on BS2_C. On the thin benches the holdout is weak evidence either way.

## 7. Tuning-gate decisions (Michael) — recommendations

1. **BS3_S → accept as pre-registered** (`box_v2_wf`, D99 cells oil + gas cum-12 / 24). All pooled cells pass. Haircut and D92
   shape are well behaved. Edge caveat for S / W pads (D101 text).
2. **BS3_C → switch to raw `box_v2`** (D97 pattern; D99 cells cum-12 / 24 / 36 on the alt intervals). The walk-forward record can be
   judged at cum-12 only, its haircut table is non-monotone, and the D92 tail would inflate ~48 %. Raw oil is −5.0 / −2.9 / +10.6 %. Raw
   gas runs LOW (+6 / +12 / +19 %; conservative), stated on workups.
3. **WCB_1 → switch to raw `box_v2`** (D99 cells cum-12 / 24 / 36 on the alt intervals). The walk-forward over-corrects oil to +26 %
   and gas to −20 % at cum-36, with D92 tails of 0.40 / 1.60. Raw oil is −2.5 / −3.1 / −13.3 % (cum-36 over-forecast called out). Raw gas
   runs LOW (+11 / +19 / +35 %).
4. **WCB_2 → accept as pre-registered** (raw, D99 cells cum-12 / 24). This is the best bench in the set: oil within ±4 %, gas within
   ±4 %. The S-edge caveat (65 packages, −13 / −15 %) goes on S-edge pads.
5. **BS1_S → accept raw with disclosure**, or emerging. Oil is forecast ~10 % HIGH at cum-12 / 24 (−10.1 / −10.3 %), right at the
   tolerance. N / E / S edges run −20…−56 %. The benchmark is milder (−3 / −6 %), so part of this is the method. The holdout is
   thin: it catches a 15 % miss 56 % of the time. Recommendation: accept with the bias disclosed on every workup. Michael's call.
6. **WCC → accept raw with disclosure**, or emerging. Oil goes −4 / −12 / −14 %, driven by the edges of a small extent (interior
   +9 / 0 / −5 %). The benchmark is worse (−11 / −19 / −27 %). Only 2 per-cutoff cells could ever be judged. Recommendation: accept with
   bias + edge caveat disclosed. Michael's call.
7. **BS2_C → emerging (reverses the gate-14 "build").** All 6 pooled cells fail. Oil over-forecasts −8 / −23 / −33 % and gas
   −17 / −28 % at cum-24 / 36, the miss compounds with time, and the benchmark shares only part of it. Under the corrected counts
   only cum-12 is judgeable. Gate 14 rested on BS2_C being judgeable at cum-12 + cum-24; the corrected counts remove cum-24.
8. **Cross-bench watch item (no spec change):** raw `box_v2` gas runs LOW on BS3_S / BS3_C / WCB_1 (+10…+35 % at cum-24 / 36). This
   is the deal-intake gas Arps P50 (D57) missing the GOR rise on these benches. Conservative. A gas method change would carry
   its own acceptance.
9. **Haircut defect to record:** the D92 C1 rate shape must not be fed a non-monotone or two-cutoff D62 table. Applies to any
   future `box_v2_wf` bench; BS3_S is unaffected. Proposal: a 9c guard that refuses a haircut whose g(48) leaves [0.6, 1.2] or
   whose cum-k factors are not monotone in k. Michael's call.
10. **Freeze:** the chosen variant's `intervals_*.csv` and `d99_cell` column become the frozen D99 rule for that bench's one-time
    holdout (9b pattern, `--holdout-once`).
    - BS3_S needs `--history` = this run's `cells_BS3_S.csv` (D94 own haircut, read from the tuning cells).
    - The raw benches need no history.

**Next after the gate:** one-time holdout per accepted bench (9b pattern); then one production run (run 9) that adds the accepted
benches to WCA / BS2_S / WCXY. Emerging answers (AVA_0/1/2 from gate 14, BS2_C if item 7 is accepted) need a go for the
`box.bench_scope` write.
