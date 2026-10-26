# BOX step 18 — Midland scope + value case (decision only)

2026-10-26. Read-only; nothing stored, no DDL. Review surface: `index.html` (headline table, bench cards, laterals, analog reach,
pooling pairs, Novi accuracy, water, Df, record-run facts, maps). Built at 586c595 (clean) by `python -m scripts.box_midland_scope`
(`box/midland_scope.py`, 12 DB-free tests; ~11 min incl. 200 block-bootstrap draws per pair). Warehouse as-of
2026-09-01 (Midland max `last_reported_month`); Novi 2026Q3 sticks; record run 19. CSVs beside the page: `cards.csv`,
`pairs.csv`, `novi_bias.csv`, `summary.json`.

**Question for gate 18:** the plan's decision list (a)–(g) for the Midland (PHASE 3, step 18). §4 is the list with a
recommendation per item; §3 lists where the plan text and the decisions of record disagree (flagged, not resolved).

## 1. How the evidence was built

- **Producers** = Midland horizontals with a first production date (`curated.wells_enriched`, `basin_blueox = 'midland'`,
  grouped on `formation_blueox`), `docs/box/exclusions.csv` applied (0 Midland rows hit). **Modern** = first production
  ≥ 2016-01-01 and lateral 5,000–15,000 ft (the r2 analog band of record, D121). **Oil / GOR** = medians of the 12-month
  calendar-day cum per 1,000 ft / scf per bbl over modern wells first-producing 2016-01 … 2025-07.
- **Undrilled sticks** = Novi PUD + RES sticks (`curated.intel_locations`, live 2026Q3) whose reconciliation status is NULL /
  `remaining_pud` / `conflict` (D117); every Midland stick is reconciled today (0 NULL). PUD-only shown alongside.
- **Identity:** the build reproduces the plan's Phase-3 table exactly on all 50 counts (modern producers, undrilled sticks, PUD
  sticks, 10 benches) and on GOR; oil medians differ by 0–4 bbl / 1,000 ft (LSSH +4, WCB_1 +4, WCB_2 +1 — production revisions
  since this morning's survey). A test pins the script's copy of the table to the plan text.
- **Analog reach** = distance from each undrilled stick midpoint to its 5th (r2 count floor) and 10th (deal-intake
  `min_wells`) nearest same-bench modern producer with ≥ 6 months, planar EPSG:32613 ft. A GEOMETRY PROXY for the r2 search:
  it ignores the spacing rule and the D55 strike ellipse, so it reads optimistic; and it runs on ALL undrilled sticks, before
  any extent (step 20 removes the far ones first — D1 / rule 11).
- **Pooling pairs** (adjacent benches, shallow → deep) = the step-1 / step-15 tests: local TVD separation in 1.5-mi
  neighbourhoods holding ≥ 3 wells of each bench (median of b − median of a), co-location within 1 mi, and 5-mi-block +
  first-production-year fixed-effect contrasts of log 12-mo oil per 1,000 ft and log GOR12 (`box/family_qc.fe_with_ci`,
  blocks holding both benches only, 200 block-bootstrap draws, 90 % CI).
- **Novi accuracy** = `curated.intel_forecast_accuracy_vintage`, report 2025Q3, direct tier, `is_latest_reported` excluded,
  bias = mean of (actual ÷ forecast − 1) per ft — the sql/38 convention (negative = Novi over-forecast).
- **D53 fold wells** = modern wells first-producing in the 12 months after each cutoff (Dec 2019 … Dec 2024). WELLS, not
  packages — a D53 / D99 cell needs ≥ 30 packages; step 14 showed well counts overstate judgeability. Package counts are 21a.
- **Df** = 3,000 oil fits of record run 19 (Delaware, md5-sampled), 50-yr EUR with Df 0.06 vs 0.08 /yr, same qi / Di / b.

## 2. What the evidence says

### (a) Value case and tier target

| | Delaware | Midland |
|---|---|---|
| Novi 2025Q3 oil bias per ft, cum-6 (wells) | −20.9 % (716) | **−5.4 %** (595) |
| same, cum-12 | −14.9 % (332) | **+4.3 %** (282) |
| gas bias per ft, cum-6 / cum-12 | −20.4 % / −17.9 % | −2.7 % / −2.0 % |
| mean drilled ÷ Novi stick lateral | 1.49 | 1.20 |

- The plan's −5 % holds at cum-6; at cum-12 Novi's Midland per-ft forecast runs slightly LOW (+4.3 %). By bench (cum-6 / cum-12):
  WCA_1 −0.8 / +2.0 %, WCB_1 +1.1 / +3.4 %, JM −2.5 / +9.7 %, MS −9.4 / 0.0 %, DEAN +5.4 / +13.5 %, WCB_2 −10.3 / +3.6 %,
  LSSH **−15.9** / +0.5 %. Novi is roughly calibrated per ft on the Midland; LSSH cum-6 is the one material over-forecast.
- So the Midland value case is NOT a bias fix. It is (1) one method and one disclosure standard across the asset base (D54 —
  every Midland number backed by named offset PDP, the investor-facing workup), (2) a Novi-independent forecast for the
  subscription decision, and (3) BOX's own screens that Novi does not have — the extent (rule 11: Novi over-states drillable
  inventory; 85,876 undrilled sticks on the ten benches vs 21,684 modern producers) and the PDP-proximity layer (stacked multi-parent
  development is the Midland norm).
- Data depth supports **validated where data allow**: the six big benches carry 79–650 modern wells per D53 fold (WCA_1 414–652,
  LSSH 374–650, WCB_1 338–419, JM 79–236, MS 86–253, WCB_2 130–170); 10th analog median 3.7–6.4 mi.

### (b) Families and pooling

| pair (a → b) | local TVD sep. b − a, ft median | merged < 100 ft | co-located 1 mi (a / b) | oil12/kft b ÷ a [90 % CI] | GOR12 b ÷ a |
|---|---|---|---|---|---|
| US → MS | 242 | 30 % | 59 % / 6 % | 1.121 [0.938–1.373] | 0.811 [0.647–0.954] |
| MS → JM | 330 | 1 % | 69 % / 70 % | 1.314 [1.227–1.384] | 1.130 [1.088–1.174] |
| JM → LSSH | 364 | 0 % | 95 % / 56 % | 0.947 [0.907–0.986] | 0.949 [0.917–0.983] |
| LSSH → DEAN | 254 | 4 % | 33 % / 79 % | 1.262 [1.176–1.366] | 1.032 [0.984–1.080] |
| DEAN → WCA_1 | 198 | 7 % | 76 % / 25 % | 0.970 [0.930–1.028] | 0.954 [0.914–1.000] |
| WCA_1 → WCB_1 | 254 | 2 % | 73 % / 84 % | 0.973 [0.939–1.018] | 1.283 [1.245–1.326] |
| WCB_1 → WCB_2 | 210 | 22 % | 43 % / 81 % | 0.927 [0.891–0.963] | 0.956 [0.928–0.990] |
| WCB_2 → WCC | 170 | 35 % | 23 % / 57 % | 0.873 [0.812–0.936] | 1.108 [1.033–1.194] |
| WCC → WCD | 1,136 | 0 % | 15 % / 13 % | 1.099 [0.982–1.268] | 1.180 [1.008–1.327] |

Step-1 reference: Delaware WCA_1 / WCA_2 (pooled, D19 / D33) sat ~128 ft apart and merged in 36 % of neighbourhoods.

- **No Midland pair looks like WCA_1 / WCA_2.** Every Spraberry pair but US / MS is ≥ 250 ft apart locally with 0–4 % merged (US / MS is
  the exception on 66 thin neighbourhoods: 30 % merged and 29 % inverted — a US tagging problem, not a band merge).
- **JM + LSSH (the plan's pooling question):** 364 ft apart, 0 % merged, never inverted; 95 % of JM wells sit within 1 mi of an
  LSSH well (JM is developed inside the LSSH footprint, not the reverse: 56 %). A pooled extent would carry LSSH's development
  onto JM — the envelope would stop being JM's own development statement (D27). Within a block LSSH runs 0.947× JM on oil per ft
  [0.907–0.986] and 0.949× on GOR — a small but resolved difference. Evidence: keep separate.
- **WCB_1 + WCB_2:** 210 ft, 22 % merged, 4 % inverted; WCB_2 oil 0.927× WCB_1 in the same block [0.891–0.963]. Closer than any Spraberry pair
  but well short of the D19 picture; the Delaware kept them apart (step 15b). Evidence: keep separate; the 22 % merged band is a
  bench-QC card class in 20a.
- **WCB_2 → WCC:** 170 ft median, **35 % merged, 7 % inverted**, P10 20 ft — the messiest boundary in the stack, and WCC oil is
  0.87× WCB_2 in the same block. WCC's tag is the weak one (see (c)); this is a 20a bench-QC item (cards on the WCB_2 ↔ WCC swap
  class), not a pooling case.
- **WCC → WCD:** 1,135 ft apart, never merged — distinct.
- Families as the plan proposes: **Spraberry = US / MS / JM / LSSH / DEAN, Wolfcamp = WCA_1 / WCB_1 / WCB_2 / WCC / WCD**, one
  extent and one curve group per bench (no WCA_2 tag exists in the Midland; WCA_1 is the whole Wolfcamp A).

### (c) Thin benches (step-14 lens)

| bench | modern producers | 2023+ share | operators (top-2 share) | 10th analog P50 / P90 mi | 5th analog beyond 20 mi | D53 fold wells 2019…2024 | undrilled (PUD) | Delaware comparable |
|---|---|---|---|---|---|---|---|---|
| **US** | 70 | 93 % | 7 (Chevron 49 %, Diamondback 41 %) | 21.0 / 48.3 | **47 %** | 0 / 1 / 0 / 7 / 19 / 30 | 3,751 (986) | none — thinner than Delaware WCD (150, emerging) |
| **WCC** | 460 | 30 % | 35 (Exxon 23 %, Sequitur 20 %) | 9.4 / 16.9 | 2 % | 31 / 45 / 57 / 50 / 55 / 23 | 8,542 (6,998) | BS2_C (547; provisional) |
| **WCD** | 669 | 66 % | 29 (Oxy 24 %, Exxon 20 %) | 10.8 / 34.8 | 18 % | 30 / 34 / 95 / 112 / 147 / 128 | 8,452 (6,769) | Delaware WCD (150, 14.1 mi; emerging) — Midland has 4.5× the wells, growing |
| **DEAN** | 780 | 63 % | 33 (Oxy 22 %, Diamondback 19 %) | 6.3 / 13.3 | 0 % | 46 / 89 / 99 / 85 / 144 / 159 | 1,882 (1,789) | AVA_1 / AVA_2 scale; reach better |

- **US** is not a bench BOX can stand behind: 70 wells, two operators, 2023+ development, half the sticks with no 5th analog
  inside 20 mi, 74 % of its 3,751 sticks are Novi RES (Novi's own doubt), 5 measured-water wells. It fits D2 exactly.
- **WCC** looks like Delaware BS2_C: real but thin, flat vintage (no growing cohort), ~23–57 wells a fold → packages almost
  certainly under 30 per cell. Provisional (D105). 8,542 sticks against 460 producers (18.6 per producer) — the extent will cut
  hardest here (rule 11), and the WCB_2 ↔ WCC tag boundary in (b) needs its 20a cards first.
- **WCD** is the judgment call: 669 producers and accelerating (95 → 147 a year), distinct 1,135 ft below WCC, but 18 % of
  sticks have no 5th analog by 20 mi and its early folds hold ~30 wells. Delaware WCD went emerging on 150 producers and a
  14-mi median reach; the Midland bench is 4.5× deeper in data. Provisional fits the evidence; emerging fits the Delaware
  precedent.
- **DEAN** is development-grade for its small inventory (0 % beyond 20 mi; folds 46–159 wells); tier decided by 21's counts like
  any other bench.

### (d) Terminal Df

Swapping Df 0.08 → 0.06 /yr on 3,000 record-run oil fits raises the 50-yr EUR by a median **+4.7 %** (P10 +3.4 %,
P90 +6.3 %), with qi / Di / b unchanged; it moves only the tail past the hyperbolic-to-exponential switch (~13 years out at Df 0.08 for a typical Di 2.8 /yr nominal =
74 % 1-yr effective, b 0.94; ~17 years at 0.06), so
cum-12 / 24 / 36 — what D53 scores — do not move. 0.06 is the in-house Midland value (CLAUDE.md sub-basin terminal decline;
anduin applies it to Midland type curves); BOX hard-codes `DF_DELAWARE = 0.08` on every fit path (`box/analog.py`,
`box/production.py`, `box/water11.py`) — the step-19 parameter.

### (e) Record-run strategy

- sql/60 `box_forecast_run_record_uq` = UNIQUE (is_record) WHERE is_record; `box.forecast_run` has no basin column. Readers keyed
  on THE record run: erebor `app/box_locations.py` + `api/highgrade.py`, sql/69 `curated.box_scout_locations`, Steven's
  `box_econ.box_pud_econ` (keyed on run_id), `scripts.box_prune_runs`, `scripts.box_refresh`.
- **D126 already rebuilds every group at every refresh** (production, fits, F(k), proximity re-measured; frozen = haircut,
  selection, tiers). A Midland landing at a 13c refresh boundary therefore costs no extra Delaware rebuild — the Delaware is
  refit in that refresh anyway — and the harness-equivalence bar belongs in step 19 (code), not step 23 (data).
- Size: run 19 holds ~77.2 M monthly rows (42.7 GB with indexes; pg_class estimate). Midland adds a comparable order (forecast PUDs × 3 streams × 600 months; Midland's in-extent
  count is unknown until step 20). Live DB 122 GB.
- A per-basin record index is DDL plus a basin key in five readers and Steven's contract, and it breaks D123's "one evergreen
  record".

### (f) Long laterals

| | Delaware | Midland |
|---|---|---|
| 2023+ horizontals ≥ 12,500 ft | 13.5 % | **35.5 %** |
| 2023+ horizontals > 15,000 ft (outside the r2 analog band) | 7.1 % | **19.8 %** |
| 2023+ horizontals ≥ 20,000 ft | 0.3 % | 0.8 % |

- Under the r2 selection of record (D121) length is a Cui translation, never a filter: analogs are 5,000–15,000-ft completed
  laterals and every cohort is translated to the location. So **no Midland PUD goes `not_covered_no_analogs` for its length** —
  the plan's option 2 in (f) does not arise (§3 flag 1).
- What does arise: (1) 15–25 % of every bench's undrilled sticks are ≥ 15,000 ft (≥ 20,000 ft ~1 %), translated on the Delaware
  WCA Cui & Cross curve EXTRAPOLATED past its last point (E = 0.801 at 12,500 ft → 0.714 at 20,000 ft vs 5,000 ft); (2) the
  Midland's 3-mile producers — 1,956 of its 2023+ wells across the ten benches (9–502 per bench) — are excluded from every analog
  pool by the 15,000-ft band edge, i.e. the wells most like the long PUDs never testify.
- The D120 condition-6 Cui-vs-linear check by length class exists; a Midland pre-registration (21a) can test a wider band (e.g.
  5,000–20,000 ft) against the r2 band on tuning folds with its own acceptance.

### (g) Water route

- Midland horizontals first-producing ≥ 2019: 65–74 % `calculated` per bench (US 79 %) (all Texas; the D107 NM amendment
  never applies). Measured cohort (≥ 6 months) per bench: WCA_1 1,227, LSSH 1,196, WCB_1 875, MS 411, JM 363, WCB_2 264,
  DEAN 212, WCD 158, WCC 65, US 5.
- Reach of the 10th measured analog from undrilled sticks (P50): LSSH 8.2, WCB_1 8.3, JM 9.0, WCA_1 10.3, MS 10.9, WCB_2 12.3,
  DEAN 13.7, WCD 19.4, **WCC 29.6** mi; ≥ 90 % of sticks close 10 measured analogs inside D107's 50-mi extension on every bench but
  WCC (89.6 %) and US (5 measured wells). Top measured operator holds 26–40 % (HHI 1,700–2,700): concentrated, not single-operator.
- So D107 as written (measured cohort + 30 / 40 / 50-mi extension, calculated fallback flagged) reaches the Midland, at radii
  3–4× the Delaware's; operator concentration and the reach are what step 22 scores.

## 3. Conflicts with the plan / decisions of record (flagged, not resolved)

1. **Step 18 (f) option 2 is moot under D121.** "≥ 12,500-ft Midland PUDs outside the analog band stay
   `not_covered_no_analogs` (D74)" is D77's band-era wording. Since D121 the analog band is fixed (5,000–15,000 ft) and every
   cohort is Cui-translated, so length never denies analogs. The live question is the Delaware Cui curve's extrapolation and the
   band edge excluding the Midland's 3-mile producers.
2. **§2 carries two rows numbered D117** (the run-10 prune, 2026-10-21, and the universe amendment, 2026-10-21); Phase 3 and
   CLAUDE.md cite D117 for the universe. Renumbering is Michael's call — suggest D117a / D117b.
3. **The plan's value-case line reads only cum-6.** Novi's Midland cum-12 per-ft bias is +4.3 % (Novi LOW), so "Novi
   over-forecasts" holds only at cum-6 and mainly on LSSH. Not a decision conflict; the §1 / Phase-3 sentence understates it.
4. **Off-list Midland tags — no gap:** `OTHER` (620 producers) and `STRN` (Strawn, 15) sit in neither the bench list nor D2's
   emerging list, but carry 0 undrilled Novi sticks (every Midland PUD / RES stick is on one of the ten benches or BRNT), so
   nothing needs a scope decision. No Midland stick or producer carries WCA_2.
5. **Df:** `DF_DELAWARE` is named for one basin and used for every bench; the step-19 parameter changes no Delaware number.

## 4. Gate 18 — the decision list (Michael decides; nothing is written)

| # | decision | recommendation | evidence |
|---|---|---|---|
| a | Build the Midland? Tier target? | **Build. Validated where data allow** (D53 / D99 path per group), D105 provisional for the rest; value case = one method + defensible workups + subscription + BOX's extent / proximity screens, NOT a Novi bias fix. | §2(a) |
| b | Benches, families, pooling | **Spraberry US / MS / JM / LSSH / DEAN; Wolfcamp WCA_1 / WCB_1 / WCB_2 / WCC / WCD; NO pooling — one extent + one curve group per bench** (JM ≠ LSSH, WCB_1 ≠ WCB_2). WCB_1 ↔ WCB_2 and WCB_2 ↔ WCC swap classes go on 20a's cards. | §2(b) |
| c | Thin benches | **US → D2 emerging. WCC → build, provisional target. WCD → build, provisional target** (alternative: emerging, the Delaware precedent). **DEAN → build**, tier from 21's counts. | §2(c) |
| d | Midland Df | **0.06 /yr** (in-house value); a basin parameter in step 19, Delaware stays 0.08 (bit-identical). Effect ~+4.7 % median 50-yr EUR vs 0.08 (measured on the Delaware record fits); cum-12/24/36 unchanged. | §2(d) |
| e | Record-run strategy | **One record run, both basins (no DDL)**; Midland lands at a 13c refresh boundary, where D126 refits the Delaware anyway; step 19 proves the code path bit-identical on the Delaware. | §2(e) |
| f | Long laterals | **Into 21a, pre-registered with its own acceptance:** r2 as is (5,000–15,000-ft band, Delaware Cui extrapolated) vs a widened Midland band (5,000–20,000 ft) on tuning folds, scored by the D120 condition-6 length classes. Whatever wins is disclosed as a Delaware curve applied to the Midland. | §2(f), §3 flag 1 |
| g | Water route into 22 | **D107 as written** (measured cohort, 30 / 40 / 50-mi extension, calculated fallback flagged); step 22 scores reach + operator concentration per group the D109 way; WCC / WCD expected thin, US moot if emerging. | §2(g) |

Also for Michael: §3 flag 2 (duplicate D117 numbering).

**Nothing is written.** Midland `box.bench_scope` rows (incl. US emerging if decided) land in step 20 with each family's extent,
on go. Next = step 19 (basin parameterization; the 13b tooling, eng_db #197, is merged).

## 5. Gate 18 — answers (Michael 2026-10-26; gate still OPEN on the items marked open)

| # | item | decision | record |
|---|---|---|---|
| c | US | **D2 emerging** (the Midland `box.bench_scope` row lands with step 20, on go). | D127 |
| c | WCD | **Build, provisional target** (D105), not the Delaware emerging precedent — 669 producers and growing. | D127 |
| b | Pooling | **No pooling anywhere**: one extent and one curve group per bench — Spraberry US / MS / JM / LSSH / DEAN (US emerging), Wolfcamp WCA_1 / WCB_1 / WCB_2 / WCC / WCD. | D128 |
| f | Long laterals | **Long producers testify through Cui & Cross, never excluded by length.** 21a pre-registers a widened Midland analog band (no exclusion of > 15,000-ft producers), every cohort Cui-translated, extrapolating past the paper's 12,500-ft range where needed, scored against the r2 band on tuning folds (D120 condition-6 length classes) with its own acceptance. Michael: more defensible in the Midland than the Delaware because the observed per-ft degradation with length is flatter — 21a measures that directly (if flatter, the Delaware curve over-penalises long laterals and the forecast reads LOW; the direction is disclosed either way). | D129 |
| e | Record run | **Per-basin record index.** One `is_record` run PER BASIN (sql/70 reserved; `box.forecast_run.basin`, run 19 backfilled `delaware`); D123 becomes "only the record run per basin"; a Midland store never waits for a Delaware rebuild or a Novi vintage. DDL container-validated in step 19 with every reader; live apply on go. | D130 |
| a | Build + tier target | **open** — recommendation stands (build; validated where data allow). | — |
| c | WCC, DEAN | **open** — recommendation stands (WCC provisional target; DEAN build). | — |
| d | Df | **open** — recommendation stands (0.06 /yr). | — |
| g | Water route | **open** — recommendation stands (D107 as written). | — |

**Correction to §2(e) / §4(e).** That recommendation leaned on "land at a 13c refresh boundary", carried over from the plan's
step-23 text and D126's cadence ("quarterly with the Novi vintage + on demand"). BOX does not need a new Novi vintage to publish —
D126 already allows an on-demand refresh — and under D130 the question disappears. What still rests on Novi Intelligence until own
placement (a later phase): the location universe = the loaded 2026Q3 sticks (D1 / D14 / D117) and their reconciliation (sql/21);
the loaded vintage stays usable for that whether or not the subscription continues (licence terms are Michael's call). D126's
cadence wording ties the refresh to the vintage — a step-13 item, flagged, not changed here.

Blast radius for D130 (step 19): `box/production.py`, `box/refresh13.py`, `scripts.box_pud_run` / `box_water_run` /
`box_prox_record` / `box_prune_runs` / `box_rehearsal`, the `apply_box_pud_forecast` + `apply_box_scout_locations` checks, sql/69
`curated.box_scout_locations` (record run -> record runs), erebor `app/box_locations.py` (reads the record run with `.scalar()`,
i.e. assumes one) + `api/highgrade.py`, and this step's builder (`run.iloc[0]`).

