# BOX run 9 — the first COMPLETE record run (validated + provisional tiers) — REHEARSED IN A CONTAINER, AT THE GATE

**Built 2026-10-18. Nothing is written to Supabase.** The run was built read-only from the live warehouse and stored as the record
ONLY in a throwaway PostGIS container (`box9`, port 5435). Live record is still **run 8** (WCA + BS2_S + WCXY).

Review surface: `index.html` (coverage, haircut + F(k) per group, every group's disclosure, all 4,485 pads) + 18 sample pad workups
in `workups/` (one per group + the D101 edge classes; all 4,485 pages in `runs/box9/workups`, git-ignored). Code:
`box/production_run9.py` (groups, well sets, tier, 9c guard, disclosures, flags), `box/production.py` (run-9 groups, `covered_provisional`),
`scripts/box_pud_run.py` (build / store), `box/production_pages.py` (provisional block), `scripts/box_run9_prep.py` (inputs),
`scripts/box_run_compare.py` (every carried group); tests `tests/test_box_run9.py` (13).

## 1. What run 9 is

One record run covering **every in-scope Delaware bench** (13 groups), not appended to run 8:

| tier | coverage | groups | record spec |
|---|---|---|---|
| validated | `covered` | WCA, BS2_S | box_v2_wf, own haircut (D62 / D102), D92 C1 shape |
| validated | `covered` | WCXY (WCXY + WCA_1 analogs, D93) | raw box_v2 (D97) |
| validated | `covered` | WCB_1, WCC (holdout PASS 2026-10-18) | raw box_v2 |
| provisional (D105) | `covered_provisional` | AVA_0, AVA_1, AVA_2, BS2_C (never out-of-time tested) | raw box_v2, no haircut |
| provisional (D105) | `covered_provisional` | BS3_S, BS3_C, WCB_2, BS1_S (holdout FAIL 2026-10-18) | raw box_v2, no haircut |

- **D103 convention:** `forecast_run.spec` stays `box_v2_wf`; each group's spec, **tier**, coverage class, guard verdict, well set,
  haircut, F(k) and disclosure live under `by_bench`. Top-level jsonb keys stay WCA's, so existing readers are unchanged.
- **Build:** `python -m scripts.box_pud_run build --benches WCA,BS2_S,WCXY_WCA1,WCB_1,WCC,AVA_0,AVA_1,AVA_2,BS2_C,BS3_S,BS3_C,WCB_2,BS1_S
  --wells docs/box/pool-2026-10-15 --out runs/box9 --workers 16`. Code **66cc6a9** (clean), blueox-boxfit 3380317, deal-intake config
  v11, Novi 2026Q3, **production through 2026-07-01** (the same data-through as run 8 and every tuning / holdout run), 5 h 57 min.
- **Well sets:** WCA / BS2_S / WCXY on the D84 refresh `pool-2026-10-15` (as run 8); each step-15 group on the QC set it was tuned and
  holdout-scored on (`production_run9.wells_dir`, = the `wells_dir` of every `runs/box15t` / `box15h` summary).
- **Harness equivalence:** every group, 24 seeded locations through the harness's own `predict_location_v2` at 600 months: max relative
  difference **0.0** for all 13. The production path is the path the tuning / holdout runs scored.
- **9c haircut guard (decided 2026-10-17; reading confirmed by Michael 2026-10-18 "yes, its ok"):** refuse a D62 table whose cum-k
  factors reverse by more than 0.01, or whose MEDIAN location's D92 g(48) leaves [0.6, 1.2]. The table half runs before any fit; the
  tail half after the haircut is applied. WCA **pass** (oil g(48) 0.740–0.800, gas 1.098–1.149; gas table reversal 0.002); BS2_S **pass**
  (oil 0.653–0.722, gas median 0.667, min 0.587 — 56 of 7,394 locations below 0.6, as in run 8; passes on the median reading). The other 11 groups carry no
  haircut, verdict "not applicable".

## 2. Identity (container store, `runs/box9/store_container.txt`)

`store --record` into the container holding the live box state copied read-only (`bench_scope` 18, `extent` 18, `location` /
`location_source` 121,921, `forecast_run` 8 = record; sequences set to live's). All checks green in one transaction (717 s):

| Check | Result |
|---|---|
| pud_forecast rows = universe | **121,727 = 121,727** |
| [WCA] covered + no_analogs = in-extent WCA_1/WCA_2 | 1,907 + 5 = 1,912 |
| [BS2_S] covered + no_analogs | 7,394 + 15 = 7,409 |
| [WCXY] covered + no_analogs | 3,183 + 5 = 3,188 |
| [WCB_1] covered + no_analogs | 4,133 + 11 = 4,144 |
| [WCC] covered + no_analogs | 1,990 + 4 = 1,994 |
| [AVA_0] covered_provisional + no_analogs | 607 + 0 = 607 |
| [AVA_1] | 1,365 + 0 = 1,365 |
| [AVA_2] | 2,839 + 12 = 2,851 |
| [BS2_C] | 3,005 + 0 = 3,005 |
| [BS3_S] | 9,192 + 32 = 9,224 |
| [BS3_C] | 7,774 + 20 = 7,794 |
| [WCB_2] | 2,584 + 31 = 2,615 |
| [BS1_S] | 4,990 + **345** = 5,335 |
| no tier leaks (validated groups carry no `covered_provisional`, provisional none `covered`) | 0 / 0 per group |
| all groups | covered 18,607 + covered_provisional 32,356 + no_analogs 480 = **51,443** |
| oil / gas stream rows = covered + covered_provisional | 50,963 / 50,963 |
| every stream: 600 months summing to its EUR within 0.1 % | 101,926 stream groups, **0 off** |
| every forecast location ≥ 3 named analogs; analog rows cover all | min 3, max 20; 50,963 |

Result: **run 9 stored as RECORD in the container** (container run_id 12 — failed attempts burn ids; live will mint its own, ≥ 10),
run 8 superseded and kept until pruned (D104).

Coverage: covered 18,607 · covered_provisional 32,356 · no_analogs 480 · outside_extent 56,502 · emerging 13,782 · **unvalidated 0**
(every in-scope bench is now forecast; run 8 had 86,114 unvalidated).

**One store defect found and fixed in the rehearsal** (commit "fix(box): store writes coverage…"): sql/63 put `coverage` into the
`(run_id, location_id, coverage)` FK of `pud_forecast_stream` and `location_analog`, column default `covered`; the store did not pass it,
so the first attempt rolled back on the first provisional stream row. The store now writes each row's class. The fix touches store
code only; the artifact was built from 66cc6a9 and is unchanged.

## 3. Carried groups vs run 8 (`wca_vs_old.*`, `BS2_S_vs_old.*`, `WCXY_WCA1_vs_old.*`)

Same sticks in both runs, same data-through; differences come from pool / production revisions since 2026-10-17 (the D98 pattern;
the WCA pool reads 12,220 wells vs 12,216).

| group | locations with forecast in both | named analog set identical | EUR exactly equal (1e-9) | oil EUR Σ run 9 / run 8 | gas EUR Σ |
|---|---|---|---|---|---|
| WCA | 1,907 | 1,895 | 1,596 | 1.0008 | 1.0009 |
| BS2_S | 7,394 | 7,126 | 6,818 | 1.0007 | 1.0004 |
| WCXY | 3,183 | 3,148 | 2,874 | 1.0000 | 1.0005 |

P10 / P90 of the per-location ratio is 1.000 / 1.000 on all three: run 9 reproduces run 8 for the validated benches.

## 4. Numbers (`groups.csv`; grain = forecast PUD locations; P10 = high; raw 50-yr EUR, uptime-free, no water, no economics)

| group | tier | oil EUR MMbbl | oil EUR/kft P10 · P50 · P90 bbl | oil Di nominal median (1-yr eff) | b | gas EUR Bcf | past-5-mi |
|---|---|---|---|---|---|---|---|
| WCA | validated (×D62) | 1,097.5 | 89,246 · 63,788 · 45,817 | 3.20 /yr (76 %) | 1.01 | 5,625.9 | 26 % |
| BS2_S | validated (×D102) | 3,672.7 | 74,766 · 56,873 · 42,455 | 3.28 (77 %) | 0.99 | 13,597.6 | 44 % |
| WCXY | validated | 2,101.1 | 105,765 · 81,208 · 54,778 | 2.95 (75 %) | 0.99 | 10,406.0 | 21 % |
| WCB_1 | validated | 2,354.4 | 92,151 · 66,710 · 49,355 | 2.47 (70 %) | 1.07 | 13,893.0 | 46 % |
| WCC | validated | 873.9 | 65,305 · 46,661 · 35,219 | 2.38 (70 %) | 0.98 | 17,426.6 | 73 % |
| AVA_0 | provisional | 366.2 | 92,883 · 79,229 · 71,267 | 3.53 (79 %) | 0.90 | 3,451.7 | 45 % |
| AVA_1 | provisional | 798.8 | 84,405 · 68,653 · 55,537 | 3.98 (81 %) | 0.90 | 8,711.8 | 44 % |
| AVA_2 | provisional | 1,686.7 | 84,187 · 68,315 · 51,484 | 3.57 (79 %) | 0.91 | 16,225.6 | 67 % |
| BS2_C | provisional | 1,908.1 | 95,824 · 72,874 · 56,553 | 2.70 (72 %) | 1.07 | 6,067.6 | 72 % |
| BS3_S | provisional | 5,791.5 | 96,190 · 72,464 · 50,627 | 2.87 (74 %) | 1.01 | 19,620.7 | 57 % |
| BS3_C | provisional | 4,259.7 | 83,942 · 61,676 · 47,255 | 3.21 (76 %) | 1.01 | 16,823.1 | 67 % |
| WCB_2 | provisional | 1,384.3 | 81,769 · 63,331 · 44,069 | 2.54 (71 %) | 1.08 | 13,662.1 | 70 % |
| BS1_S | provisional | 3,264.7 | 94,655 · 75,705 · 57,863 | 3.15 (75 %) | 1.05 | 14,952.7 | 80 % |

- **Validated total 10,099.6 MMbbl oil / 60,949 Bcf gas; provisional 19,459.9 MMbbl / 99,515 Bcf.** The provisional tier is ~2/3 of the
  forecast oil. It is labelled, separately classed and disclosed, never validated.
- WCA / BS2_S / WCXY equal run 8 (§3); the haircut realised factors are run 8's (WCA oil EUR × 0.839, BS2_S × 0.767).
- **No haircut on any provisional bench, and their disclosed biases are mostly HIGH:** BS1_S oil cum-12 −12.4 % (tuning + holdout),
  holdout −20.9 %; BS3_C oil holdout −14.1 %; AVA recent cohorts −14…−18 %. A provisional EUR is the raw analog P50; read the disclosure
  next to it (D105).
- **Bound-pinned P50 fits (D79, flagged per row):** oil Di at the 4.0/yr cap (81.7 % 1-yr effective) on **47 % of AVA_1** locations,
  27 % AVA_2, 18 % AVA_0 (WCA 15 %); oil b at a bound on **73 % of AVA_1** / 57 % AVA_0. The thin AVA cohorts pin; flagged, never widened.
- Analog reach: the step-15 benches reach past the 5-mi ring on 44–80 % of locations (WCA 26 %), the D69 range that applies is the
  wider one; each group's radius range comes from its own tuning packages (`inputs/spread_by_radius_<group>.csv`).

## 5. Disclosure carried by every workup

Per group under `by_bench.<group>.disclosure` and on the pad pages; the tier / call-out / edge text also travels in `pud_forecast.flags`:

- **WCA, BS2_S, WCXY:** unchanged from run 8 (D59 cond. 3, D100, D101; WCXY call-out).
- **WCB_1, WCC (validated):** the 9c shape (D100): disclosed bias = tuning bias per D99 cell, holdout bias + frozen interval, radius range.
  Flags: WCB_1 "oil cum-36 −13 % (HIGH); gas runs LOW +11 / +19 / +35 %"; WCC "weak evidence (rule power 54 %); gas ~−11 % on the holdout".
- **AVA_0/1/2, BS2_C (D105):** pooled in-sample bias + 95 % block-bootstrap range (AVA leads with AVA 0+1+2 pooled, then its own bench),
  "measured in-sample, never out-of-time validated", and the latest-vintage line of record (AVA "recent cohorts (2022-24) produced
  14-18 % below forecast at 12 months"; BS2_C "the miss changed sign; the 2023-24 cohorts came in ~12 % above forecast").
- **BS3_S, BS3_C, WCB_2, BS1_S (holdout fail):** three lines always together — tuning, **holdout**, tuning + holdout (lead) — never the pooled
  figure alone; the frozen D99 interval it failed; the latest-vintage line computed from the 2024-cutoff cohort (tuning + holdout).
  Flag e.g. WCB_2: "cum-12 bias tuning + holdout oil +2.5 % / gas +1.8 %, HOLDOUT oil +7.1 % / gas +20.6 %".
- **Edge caveats (tuning gate 2026-10-17, numbers recomputed at the record variant = raw box_v2, `inputs/edge_regions_<group>.csv`):**
  BS3_S S −17.6 % / W −15.5 % (the tuning page's −19.7 / −12.9 % were box_v2_wf, its pre-holdout record); WCB_2 S −12.6 %; BS1_S N −19.8 /
  E −20.3 / S −56.1 %; WCC N −14.4 / E −23 / S −33 / W −29 % (oil cum-12, tuning packages; benchmark beside each). Locations carrying one:
  BS3_S 2,094; WCB_2 430; BS1_S 1,415; WCC 1,149.

## 6. BS1_S: 345 in-extent PUDs with no analog workup (D74)

All 345 reach the 20-mi cap with 0 (245), 1 (92) or 2 (8) eligible analogs. 212 sit within 5 mi of the extent-26 **south** boundary
(that edge had 5 tuning packages, oil cum-12 −56 %); the rest N 44, W 19, E 8, interior 62. Not lateral-driven (spread over every lateral
class). They row as `not_covered_no_analogs` — counted, never zero. The selection filter that empties them (geography vs the
representative-spacing / lateral band filters) was not traced; the other 12 groups are at 0–1.2 %.

## 7. Gate asks (Michael)

1. **Go to store run 9 live as the record?** From the main checkout after this PR merges (artifact copied to `runs/box9/run.pkl`, sha256 9c45e262…7082852 = the build):
   `python -m scripts.box_pud_run store --record --out runs/box9`. Pre-check: live record = run 8, `box_econ.box_pud_econ` = 0 rows.
   Container: 12 min; Supabase will be slower (the 61 M-row month COPY), one transaction, rolls back on any identity failure.
2. **Storage.** Run 9 adds **61.2 M `pud_forecast_month` rows ≈ 7.3 GB** (container; run 8 is 15.0 M ≈ 2.7 GB live; database ~76 GB).
   Per D104, run 8 becomes prunable once run 9 is record (`box_prune_runs --apply`; nothing priced). Acceptable?
3. **erebor reads `covered` only** (`app/api/box.py`: `coverage != 'covered'`, its coverage list has no `covered_provisional`). Until a
   tier-aware erebor change lands, the 32,356 provisional rows will not show a BOX forecast in Highgrade (warehouse first, then app —
   the D105 follow-up). Store first and fix erebor after, or erebor first?
4. **BS1_S 345 no-analog PUDs (§6):** accept as reported (D74), or a read-only trace of which filter empties them first?
5. **Steven note** (D86 pattern, you send): run 9 adds WCB_1, WCC (validated) and 32k `covered_provisional` rows he can now price (sql/63
   admits them); per-group tier + disclosure under `by_bench`.

Nothing here changes a frozen rule, a factor table, an interval or a tier. Live run_id sequence is at 9 (a rolled-back smoke burned one
id), so the live record will be run_id 10 or later, not "9" — the plan text calls it run 9.
