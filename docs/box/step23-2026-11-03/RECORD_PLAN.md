# BOX step 23a — record plan: the Midland record + the Delaware's D117 / D150 move, priced once

**Status: AT GATE 23a (2026-11-03). Nothing stored, nothing applied, no record touched.** Live today: the Delaware record is
the 16d record (run 19), priced by Steven (687,520 `box_econ` rows, 16 decks, re-priced 2026-11-02). The D117 record (run 25)
is stored, not record, unpriced. The Midland has no BOX run. `sql/70` is live (`box_forecast_run_record_basin_uq`, UNIQUE (basin)
WHERE is_record); erebor main reads the record per basin (erebor #28, `5afe6ba`).

**This step does not change what the Delaware screens show.** Every step that will (23b inside the container only, 23d live) says
so in its own sentence.

Code: `box/record23.py`, `scripts/box_record23.py`, `scripts/box_record23_midland.py`, `box/production.py` (nine `MID_` groups,
D151 tiers, D145 class; additive, the Delaware groups unchanged), `sql/71_box_step23.sql` (authored, NOT applied),
`tests/test_box_record23.py`. Evidence in this folder: `midland_pack_as_delivered.json` / `midland_pack_recomputed.json` (+ sha256),
`d102_d150.csv`, `delaware_measure.json`, `midland_measure.json`.

Read §7 first: the gate questions, recommendation first.

---

## 1. What is settled, and where the record conflicts with it (flagged, not resolved)

| settled (Michael, step-23 kickoff) | as built here | conflict / gap |
|---|---|---|
| Midland method = step 21 rev 8 (`5ceadc2`) + the D149 treatments + D150 Midland R3 (level 1.067, single-parent sticks get F) + the D151 tiers + WCA_1 oil D102 | `box/record23.method_block()`; `scripts/box_record23_midland` builds with `box/step21.RULES`, `basin = midland` | none. The method block equals `prospective21.DEFINITION["method"]` field by field (§2, a test). |
| Midland precedent gates: 21a pattern precedent + 400-ft floor | `box/step21_prox.decide_all` (which also runs D114 on the tag-free key, 21a revision 1: "both must hold") | **not a conflict, stated:** D114 still refuses 596 + 2 Midland sticks (precedent / package) on top of pattern (2,221) and spacing (913). |
| Water per D107 / D133, provisional on all nine | `scripts.box_water_run` on the Midland base run (it reads the run's basin and wells dirs; `water_tier` gives provisional outside WCA / BS2_S) | **untested on a Midland run**: smoke first at 23b. |
| Proximity re-measured D116-style at the build | Delaware: `measure --basin delaware` (done, §3); Midland: re-measured live on the stored base run at 23b (today: the 21b stick cache of 2026-11-01) | none |
| Delaware = run 25, table haircut divided out, level 1.046 x F_R2 on every forecast PUD; D114 bench pair + package tier | `scripts/box_record23 store --basin delaware --src-run 25` | **(g)** D114's package tier fires at "factor <= 0.80": which factor? Built on the incumbent table factor, as step 24 measured "incumbent gates kept". **(h)** sticks reconciled as drilled since run 25 leave the universe. **(f)** D145 (conflict sticks) is Midland-only as written; the Delaware keeps D1. |
| Order: store (not record) → Steven prices → flip → verify → prune | `store` never makes a record; `flip` refuses an unpriced run | **The plan's old step-23 entry said store → prune → re-price**: rewritten to the settled order (`docs/box_type_curves_plan.md` step 23). |
| One record per basin; sql/70 and erebor per-basin read live before relying on them | sql/70 index verified live (2026-11-03); erebor `box_locations.py` reads `is_record AND basin = :basin` on main | erebor's **proximity vocabulary** does not know D150 (§5): an erebor PR is needed before 23b's erebor check. |
| No economics anywhere | none computed; the flip guard only COUNTS Steven's rows | none |
| *(not in the settled list)* | | **(e) D150 needs DDL** (`sql/71`): factors > 1 and the new outcome words violate sql/65's CHECKs. Every store in 23b / 23c depends on it. |

---

## 2. The Midland build spec, field by field, against `prospective21.DEFINITION["method"]`

The 21d scorer will, before its one read (~2028), compare the Midland record run's stored spec with the frozen definition
(`record_run_check`: "base digest, D150 digest and curve, haircut table"). The record run stores `forecast_run.disclosure ->
method_23` = `box/record23.method_block()`. Every value there is read from the module or gate file that owns it, never copied
from `prospective21`, so `check_method` is a real comparison. `tests/test_box_record23.py::test_method_block_is_the_21d_definition`
asserts it returns no mismatch, and a parametrized test proves it catches drift in each field.

| 21d field (`DEFINITION["method"]`) | 21d value | record run (`method_block`) | read from | enforced in the build by |
|---|---|---|---|---|
| `base.digest` | `9780f326…` | `box/step21.DIGEST` | the frozen definition | `box/step21.RULES` passed to `production.fit_many` |
| `base.frozen_sha` | `5ceadc2…` | `GATE_21B.json frozen_sha` | gate 21b | the harness equivalence check (below) |
| `base.parts` | r2, translate 5,000 ft..inf, Cui Midland / Delaware-when-longer (D148), D119, D63, Df 0.06, D57 | `selection`, `translate_range_ft`, `df_terminal` | `step21.SELECTION / RULES`, `basin.df_terminal("midland")` | `box/analog.lateral_multiplier(basin=midland)` (LONGER_PANEL); `fit_p50_series(Df 0.06)` |
| `proximity.digest`, `frozen_sha` | `2e8bb5a7…`, `77d50a7…` | `prox_cont.DIGEST`, `GATE_24A.json` | step 24 | `record23.stick_factors` → `prox_cont.sticks` |
| `proximity.curve` | R3, F_min 0.7195, d50 485.1 ft, k 1.955, a 0.5 / 0.5, level 1.0674 | `GATE_24A.json curves.midland` | gate 24a | same |
| `proximity.form` | oil x level x F_R3; no parent → the level; gas / water untouched | `streams: ["oil"]` | — | `box_record23 store`: oil rows x new / old, gas / water md5-identical |
| `haircut.MID_WCA_1` | oil, "the D102 table AS DELIVERED by the record run" | `{"stream": "oil", "factor": {12..48}, "basis": ...}` | gate 21c (as delivered) or `d102_d150.csv` (recomputed), **gate question (a)** | `production.apply_haircut_c1` (D92) + the 9c guard (D106) |
| `haircut.others` | none | `"none"` | gate 21c tiers | `haircut_of(pack)` = None for the other eight |
| cohort groups / extents / tiers at freeze | 36 / 37 / 38 / 39 / 42 / 44 / 45 / 47 / 49; D151 tiers | `GATE_21C.json` + `step21.GROUPS` | gate 21c | `production.MIDLAND_PROVISIONAL` (test pins it to gate 21c) |
| `streams_shipped` | oil = mid_r2 x D150 (x haircut); gas = mid_r2; water = D107 on raw mid_r2 oil | same strings | — | build months_raw → haircut; water on `months_raw` (D108) |

**Equivalence (the base equals the method 21b / 21c scored).** Each group's build re-predicts a seeded sample of 24 sticks with
the HARNESS (`box/analog.predict_location_v2`, variant `mid_r2`) and refuses unless the production months match to 1e-12.
Smoke 2026-11-03: WCA_1, 30 sticks, max relative difference **0.0** on 24 / 24. The full build reports each group (§4.2).

**21d stays blind.** The base build's F(k) sample (published, not applied, D63) is drawn from the 12-month training cohort
(`c12` at the cutoff): no 2026 well can be in it at data-through 2026-08-01. The build checks it anyway and refuses if one is.
Nothing in this step reads a 2026 Midland well's production against a BOX forecast. The 2026 wells in the frozen pool are
analogs (their early months feed cohort fits), as in every BOX build. That is not a forecast-vs-actual read.

---

## 3. Data as-of, per basin, and what moved since run 25

### 3.1 Delaware (source = run 25)

| item | run 25 as built (2026-10-30) | now (2026-11-03) | moved? |
|---|---|---|---|
| production through | 2026-07-01 (run 19's build, carried) | last full month 2026-08-01 | +1 month available; a derived run keeps 2026-07-01 (no refit) |
| analog pools | run 19's sets (16d; pool-2026-10-15 WCA, the step-15 sets) | same. pool-2026-10-26 = the 13b rehearsal's PROPOSED refresh; the first live refresh is 13c (D126 / D137) | **no** |
| tag overrides | 438 live (98 Delaware), applied 2026-10-29 | 438 live; seed unchanged since 2026-10-29 | **no** |
| `formation_blueox` (vendor + consensus) | read at the 10-30 measure | live at this re-measure | drift only: the re-measure moved **774** sticks' incumbent outcome vs run 25's (configuration drift) |
| exclusions.csv | last change before 2026-10-24 | unchanged | no |
| Novi WellSpacing | read live at run 19's build (D137) | rewritten nightly (~10 % of wells in 4 days) | yes, in the analog pools' spacing: frozen in run 25's fits; a rebuild would pick it up (D137: "live is fine") |
| reconciliation | run 25's `recon_status` | live `reconciled_inventory` | **136** run-25 forecast sticks now `realized_phantom` (76.1 MMbbl of run-25 oil); 634 forecast sticks now `conflict` |

### 3.2 Midland (a new base build)

| item | value | note |
|---|---|---|
| production through / cutoff | 2026-08-01 / 2026-09-01 (live last full month) | 21b / 21c actuals ran through 2026-08-01, so the fits use the same months the method was scored on |
| analog pool | `docs/box/pool-midland-2026-10-31` (27,980 wells; every copy = its source set by sha256, checked 2026-11-03) | the step-21 sets of record. No Midland pool refresh before step 13 (D124 / D126) |
| tags | 438 live overrides, 340 Midland | **the 4 r3-seed removals are still not applied** (live 438 vs seed 434; MM 2026-10-30: "rides the next override batch") |
| exclusions.csv | 46 rows, unchanged since before 2026-10-24 | applied by the pool loader (`box/exclusions`) |
| universe | 85,849 Midland sticks today, 669 of them `not_covered_conflict` (all benches); 32,541 in-extent drillable (= 21b's stick count) | D117 PUD + RES; D145 conflict sticks classed, never fitted |

**What the 4 unapplied removals touch.** Live overrides not in the seed, each still WCB_2 in the warehouse:
4232945905 STEPHENS 6-31 E 255, 4232946987 STEPHENS 6-31 D 244 and 4246139770 MELINDA 252WB (calls: WCB_1), plus 4232943352
PARKS, ROY 316CH (call: WCC). First production 2015-06 to 2025-12, so none is a 2026 (21d) well.
- **Analog pools:** no effect. Pools read `box_bench`, which already carries the calls.
- **Stick-side proximity:** no effect. Class is by depth (21a revision 3) and the precedent key is tag-free.
- **D64 planned spacing:** yes, a little. `box_pud_run.locations` finds PDP neighbours by warehouse tag, so the four count as
  WCB_2 neighbours. Only WCB_1 / WCB_2 / WCC sticks within 2,800 ft of them see a different planned spacing.
- **21d membership:** none of the four is a 2026 well.

**Recommendation:** build without waiting. The removals land with the next override batch, a separate warehouse write that needs
its own go. The plan does not depend on it.

### 3.3 D144: derive the Delaware, or rebuild it — question (d)

D144 says rebuild the Delaware if tags or pools have moved. Pools have not moved: the refresh contract (D126) moves them at 13c,
and none has been applied. Tags have not moved by override; vendor / consensus drift shows up in the re-measure (774 sticks). What
has moved is production (+1 month), Novi spacing (D137) and reconciliation. The 13b rehearsal measured a full Delaware rebuild at
that kind of distance: oil −0.59 % vs run 19, mostly production +1 month, the proximity re-measure and spacing revisions. The
134 added pool wells moved nothing. **Recommendation: derive (D153), as settled.** See §7 (d) for the numbers.

---

## 4. Expected identities, by identity

### 4.1 Delaware derived run (from run 25; `scripts/box_record23 store --basin delaware --src-run 25`)

Checked inside the one transaction, before COMMIT; any failure rolls back:

- **universe** = run 25's pud_forecast rows − sticks reconciled as drilled since (they leave; erebor classes them `realized`).
- **forecast** (oil = gas = water stream rows) = run 25's forecast locations that the re-measure keeps (D114 as written) and that
  are not drilled since. **No stick is re-admitted**: a stick run 25 refused has no source rows, so the store refuses if the
  re-measure would forecast one (127 today: question (d)).
- **oil EUR** = Σ run-25 oil x (new factor / run-25 `prox_factor`), to 1e-9; every oil month likewise.
- **gas, water**: stream rows and months identical to run 25 (md5 / IS DISTINCT FROM = 0).
- every stream: 600 months summing to its EUR within 0.1 %.
- `pud_proximity` = one row per universe stick that was measured; oil `prox_factor` = `pud_proximity.factor` on every forecast stick.
- `pud_proximity_parent` = the D150 counting parents of kept sticks.
- no orphans: every stream / analog row has a forecast-class pud_forecast row. Run 25 untouched. The new run is NOT a record.

**Re-measure 2026-11-03** (`scripts/box_record23 measure --basin delaware`, read-only; `delaware_measure.json`,
`delaware_outcomes_23a.csv.gz`): 57,638 run-25 sticks (48,945 forecast + 8,693 no-precedent), 349k links at reference date
2026-07-01, live producers (33,900) and tags; D114 on the runs/prox precedent caches, as run 25.

| | sticks | run-25 oil, MMbbl |
|---|---|---|
| run 25 forecast | 48,945 | 25,569.9 |
| − reconciled as drilled since (leave the universe) | −136 | −76.1 |
| − newly refused by D114 (configuration drift) | −103 | −52.0 |
| = expected derived forecast | **48,706** | 25,441.9 |
| + D150 swap (oil x level x F_R2 / table factor) | | **+311.0** |
| = **expected derived oil** | | **25,752.9** (+0.7 % vs run 25; +13.8 % vs run 19) |
| re-admitted: refused in run 25, forecast by the re-measure (no source rows) | 127 | (question (d)) |

D150 swap by outcome (expected forecast sticks): unexposed 17,968 at the level 1.046, 9,760.0 → 10,208.7 MMbbl (+448.8);
single parent 6,564, factor mean 1.025, +83.8; multi parent 24,174, factor 0.922 vs the table's 0.935, −221.5. Factor mean
0.981, 61 % of forecast sticks above 1, 2,923 below 0.80 (min 0.41).

Per bench (oil MMbbl, gas Bcf; count = forecast sticks; gas changes only by the sticks that leave):

| bench | n run 19 | n run 25 | n derived | oil run 19 | oil run 25 | **oil derived** | Δ vs 25 | Δ vs 19 | gas run 25 | gas derived | factor mean (table) |
|---|---|---|---|---|---|---|---|---|---|---|---|
| AVA_0 | 350 | 377 | 371 | 208.2 | 226.7 | 225.1 | −0.7 % | +8.1 % | 2,119.6 | 2,085.3 | 1.011 (1.000) |
| AVA_1 | 951 | 973 | 971 | 563.7 | 578.7 | 591.0 | +2.1 % | +4.8 % | 6,319.3 | 6,303.8 | 1.023 (1.000) |
| AVA_2 | 1,765 | 1,783 | 1,780 | 955.7 | 968.7 | 983.9 | +1.6 % | +2.9 % | 9,633.5 | 9,621.4 | 1.019 (1.000) |
| BS1_S | 4,826 | 4,834 | 4,823 | 2,957.4 | 2,964.7 | 3,055.1 | +3.0 % | +3.3 % | 14,842.2 | 14,810.4 | 1.012 (0.981) |
| BS2_C | 2,148 | 2,140 | 2,130 | 1,287.1 | 1,280.9 | 1,313.5 | +2.5 % | +2.1 % | 3,965.4 | 3,947.9 | 1.020 (0.991) |
| BS2_S | 7,078 | 7,077 | 7,031 | 3,249.6 | 3,249.9 | 3,294.9 | +1.4 % | +1.4 % | 18,703.9 | 18,587.3 | 1.006 (0.984) |
| BS3_C | 7,167 | 7,202 | 7,138 | 3,376.7 | 3,385.0 | 3,368.7 | −0.5 % | −0.2 % | 14,910.4 | 14,805.3 | 0.940 (0.933) |
| BS3_S | 5,580 | 6,010 | 5,968 | 3,148.1 | 3,485.6 | 3,525.3 | +1.1 % | +12.0 % | 12,009.5 | 11,894.2 | 0.989 (0.973) |
| WCA_1 | 943 | 942 | 937 | 471.5 | 471.1 | 468.5 | −0.5 % | −0.6 % | 2,558.3 | 2,539.9 | 0.959 (0.956) |
| WCA_2 | 934 | 934 | 926 | 483.1 | 483.1 | 483.1 | 0.0 % | 0.0 % | 2,651.3 | 2,634.6 | 0.973 (0.963) |
| WCB_1 | 3,991 | 4,002 | 3,990 | 2,063.2 | 2,069.4 | 2,005.3 | −3.1 % | −2.8 % | 12,946.1 | 12,888.0 | 0.916 (0.937) |
| WCB_2 | 2,315 | 2,316 | 2,301 | 1,193.2 | 1,193.8 | 1,185.9 | −0.7 % | −0.6 % | 12,255.0 | 12,193.5 | 0.980 (0.977) |
| WCC | 1,773 | 2,276 | 2,274 | 740.0 | 954.3 | 989.5 | +3.7 % | +33.7 % | 17,951.8 | 17,938.1 | 1.039 (1.000) |
| WCXY | 3,149 | 8,079 | 8,066 | 1,925.9 | 4,258.0 | 4,263.2 | +0.1 % | +121.4 % | 21,312.0 | 21,266.4 | 0.968 (0.961) |
| **total** | **42,970** | **48,945** | **48,706** | **22,623.3** | **25,569.9** | **25,752.9** | **+0.7 %** | **+13.8 %** | **152,178.2** | **151,516.1** | 0.981 (0.968) |

Run 19 → run 25 is D117 (RES rows: WCXY +5,055 sticks, WCC +566, BS3_S +495; D116 re-measure). Run 25 → derived is D150 plus the
drift above. Water: per-stick identical to run 25 (128,915.5 MMbbl on run 25's 48,945; the sticks that leave take theirs).

### 4.2 Midland: base run, then the record derived from it

Base (`scripts/box_record23_midland build`, then `store` on go): universe = the Midland basin's D117 universe (85,849 today).
Per group: covered (validated WCA_1 / WCD / LSSH) or covered_provisional (the other six) + no_analogs = the in-extent drillable
universe of that group, exactly (box_pud_run's identity). Every stream 600 months = EUR. ≥ 3 named analogs per forecast stick.
Conflict sticks: `not_covered_conflict`, no search.

Record (`scripts/box_record23 store --basin midland --src-run <base>`): same identities as 4.1 with old factor = 1. The method
block stored = `method_block()` (the store refuses unless `check_method` is clean).

**Universe today** (live, 2026-11-03; `box/production.universe` with the nine `MID_` groups): 85,849 Midland sticks =
covered 15,948 (WCA_1, WCD, LSSH) + covered_provisional 16,593 (the other six) + not_covered_outside_extent 37,836 +
not_covered_emerging 14,803 (US, BRNT, MISS, MRMC, WDFD) + **not_covered_conflict 669** (D145). In-extent drillable = 32,541,
identical to 21b's stick count. Run 19's 4,154 Midland emerging rows stay on run 19 until it is pruned (sql/70 note).

**Record outcomes** (expected, from the 21b stick cache; the live re-measure at 23b re-decides them): 28,809 forecast of 32,541
in-extent drillable (21b keep set exactly); refused: pattern 2,221, spacing 913, precedent 596, package 2.

| bench | forecast sticks | multi / single / unexposed | refused (pattern / spacing / precedent) | D150 factor mean (min) |
|---|---|---|---|---|
| WCA_1 | 4,589 | 3,117 / 339 / 1,133 | 337 / 195 / 0 | 0.944 (0.52) |
| WCB_1 | 4,719 | 3,229 / 349 / 1,141 | 551 / 205 / 0 (+2 package) | 0.949 (0.62) |
| WCB_2 | 680 | 445 / 55 / 180 | 139 / 29 / 1 | 0.992 (0.73) |
| WCC | 374 | 326 / 19 / 29 | 0 / 16 / 302 | 0.934 (0.68) |
| WCD | 3,413 | 1,452 / 492 / 1,469 | 0 / 16 / 160 | 1.010 (0.71) |
| MS | 3,891 | 2,677 / 291 / 923 | 195 / 74 / 0 | 0.956 (0.63) |
| JM | 3,434 | 2,657 / 182 / 595 | 445 / 199 / 10 | 0.915 (0.57) |
| LSSH | 6,795 | 4,797 / 428 / 1,570 | 332 / 98 / 13 | 0.937 (0.50) |
| DEAN | 914 | 451 / 135 / 328 | 222 / 81 / 110 | 0.980 (0.57) |
| **total** | **28,809** | 19,151 / 2,290 / 7,368 | 2,221 / 913 / 596 (+2) | 0.951 |

Multi / single / unexposed here count the D150 parents: dv ≤ 1,000 ft, dh ≤ 2,640 ft, ≥ 30 % alongside, every existing producer.
The incumbent's D113 classes are narrower. D150 mean factor: multi 0.897, single 1.033, unexposed 1.067.

**Base-run oil / gas** (the full read-only build, `runs/step23/midland_base`, data through 2026-08-01, as-delivered haircut):
MID_BUILD

---

## 5. Schema and app consequences (new; not in the settled list)

**sql/71 (DDL, its own go; container first at 23b).** D150 cannot be stored under sql/65 as it stands:

| sql/65 / sql/63 rule | breaks on | sql/71 |
|---|---|---|
| `prox_factor <= 1`, `pud_proximity.factor <= 1` | the level: every unexposed stick carries 1.046 / 1.067; 46 % of Midland forecast sticks sit above 1 | `0 < factor <= 1.5` |
| outcome IN (as_is_*, haircut, no_forecast_precedent / package) | D150 words; Midland pattern / spacing | + `level_unexposed`, `factor_single_parent`, `factor_multi_parent`, `no_forecast_pattern`, `no_forecast_spacing` (old words stay valid for runs 19 / 25) |
| as-is ⇒ factor 1; multi ⇒ table key; unexposed ⇔ no config class | D150 rows carry a factor and no table key | scoped to the D113 words |
| `pud_proximity_parent.age_days >= 365` | Midland: every existing producer is a parent (21a revision 4) | `>= 0` |
| coverage list | D145 | + `not_covered_conflict` (only with `recon_status = 'conflict'`) |

**erebor (a PR before 23b's erebor check).** `box_locations.PROX_GROUPS` and `frontend/src/api/highgrade.ts` map only the D113
words. A D150 outcome would match no filter group. The tiles and Highgrade show `prox_factor` only when it is below 1, so a 1.067
factor would be hidden. There is no `not_covered_conflict` class yet. Proposed: as_is ← level_unexposed + factor_single_parent;
haircut ← factor_multi_parent; no_precedent ← every `no_forecast_*`; show the factor whenever it is not 1; add the conflict
class (stated, never zero). Same read-only queries, no new endpoint.

**Steven.** `box_econ.box_pud_econ` keys on run + location (provenance + `downtime_basis` required). What his loader does with
`prox_factor` is his side, not checked here. The note to him states that oil factors now run above 1 (the level), and why.

---

## 6. The run sequence (23b → 23d; every write its own go)

`scripts.box_rehearsal` seeds the container with the live box SCHEMA plus the small reference tables and the record header. It
copies no run rows and no econ rows. So the Delaware source (run 25) has to be put into the container before anything can be
derived from it. The proven way is to replay the 2026-10-30 chain from its artifacts (`runs/box_d117s3` run.pkl + water.pkl +
`runs/box_d117s4_prox` outcomes), then check it against live run 25 with `box_d117_step3 compare`, as on 10-30. The container
at that time held ~27.5 GB.

```
# 23b — container only (DB_* -> box-rehearsal). Changes nothing live; the live Delaware screens are untouched throughout.
python -m scripts.box_rehearsal up && python -m scripts.box_rehearsal seed && python -m scripts.box_rehearsal verify
#   sql/71 in the container; sql/69 re-created there
#   Delaware source: replay run 24 -> water -> run 25 from the 10-30 artifacts; compare to live run 25 (read-only both sides)
python -m scripts.box_record23 store --basin delaware --src-run <container run 25> --outcomes runs/step23/delaware/outcomes.csv.gz \
       --links runs/step23/delaware/pud_links.pkl --readmitted carry-refusal [--d145] --commit
python -m scripts.box_record23_midland store --out runs/step23/midland_base          # Midland base run (not record)
python -m scripts.box_water_run build --run-pkl runs/step23/midland_base/run.pkl --out runs/step23/midland_water   # smoke first
python -m scripts.box_water_run store --out runs/step23/midland_water --run-id <base>
#   Midland live re-measure on the stored base (D116), then:
python -m scripts.box_record23 store --basin midland --src-run <base> --outcomes ... --links ... --commit
#   flips: `flip` on an unpriced run must REFUSE (shown); then container-only synthetic econ rows (labelled synthetic, never
#   live) let erebor + sql/69 show the before / after of both flips
# 23c — live: sql/71 ("go apply"); the Delaware store; the Midland base store; Midland water; the Midland record store;
#   bench_scope.validation (nine Midland rows). Each its own go. None of these changes what the Delaware screens show
#   (no record moves).
# 23d — live, after Steven has priced both: flip --basin delaware (THIS changes the Delaware screens: new volumes, his new
#   econ); flip --basin midland; verify erebor + sql/69; prune (run 19 --include-priced, run 25, the Midland base run).
```

---

## 7. FINDINGS — gate 23a questions (recommendation first)

Error convention throughout: actual / forecast − 1 (negative = BOX high). Oil volumes are the raw 50-yr integral (rule 6).

### (a) WCA_1's D102 haircut — ★ recompute it on the D150 treatment (0.958 / 0.953 / 0.932 / 0.927)

Computed on the 21b tuning packages + the 21c holdout packages, merged per cutoff exactly as D102 / gate 21c did
(`box/step21c.d102_table`), with mid_r2 × the D150 factor (drilled side) in place of the 21 table. File `d102_d150.csv`.

| cum-k | as delivered (21 table) | recomputed (D150) | packages | shipped tuning bias, as delivered → recomputed | 21c holdout re-read, as delivered → recomputed |
|---|---|---|---|---|---|
| 12 | 0.979 | **0.958** | 1,281 | −2.2 % → 0.0 % | −2.1 % → +0.1 % |
| 24 | 0.975 | **0.953** | 1,092 | −2.3 % → 0.0 % | −2.1 % → +0.2 % |
| 36 | 0.954 | **0.932** | 865 | −2.2 % → +0.1 % | −2.8 % → −0.5 % |
| 48 | 0.950 | **0.927** | 408 | (not judged) | |

- **Why recompute.** D102 is "tuning + holdout cells of the RECORD treatment, merged per cutoff". At step 23 the record
  treatment is D150, so the rule as written gives the recomputed table. The 21c table was measured on the 21 table treatment,
  which does not ship. Keeping it leaves WCA_1, a validated bench, about 2 % high on oil at every horizon. The level is why:
  WCA_1's tuning wells average a D150 factor of 0.999, above the 21 table's.
- Effect: WCA_1 oil EUR about −2.4 % (the D92 shape's cum-48 factor, 0.927 vs 0.950). The table is monotone, so the D106 table
  half passes; the build checks the g(48) half and refuses outside [0.6, 1.2].
- It cannot move a 21d verdict (D152: a uniform per-horizon factor scales the bias and both interval ends alike). `check_method`
  passes either way; the stored block says which one shipped (`basis`).
- The as-delivered option stays available: `midland_pack_as_delivered.json` is what the full build below used. Switching
  re-applies the haircut to the cached fits. No refit.

### (b) D150's level moves WCD to −11.2 % (WCB_2 −12.0, MS −10.0) — ★ disclose only

| group (tier) | shipped, D150, tuning cum-12 / 24 / 36 | 21c holdout re-read on D150 | 21d's "on the 21 table" figure | unexposed forecast sticks (carry 1.067) |
|---|---|---|---|---|
| WCD (validated) | **−11.2 / −11.5 / −14.3 %** | −4.8 / −8.4 / −16.4 % | −7.5 % cum-12 | 1,469 of 3,413 (43 %) |
| WCB_2 (provisional) | −9.2 / −12.0 / −15.8 % | +0.6 / −2.6 / −2.0 % | −9.2 % cum-24 | 180 of 680 |
| MS (provisional) | −7.2 / −10.0 / −10.9 % | −16.0 / −13.4 / −16.2 % | −7.2 % cum-24 | 923 of 3,891 |

- **Why disclose, not act.** D150 G5 decided no bench-level offset. Exempting WCD from the level (or giving it its own) would be
  a per-bench change made after reading WCD's tuning and holdout bias, which the gate history keeps warning against. 21d judges
  WCD on exactly this treatment at cum-12 (~39 packages, production through ≥ 2028-01-01). If the over-forecast is real, WCD
  drops to provisional then (D152: keeping validated = consistency only).
- The act option, for the record: WCD with level 1.0 on its unexposed sticks brings its tuning oil back to about −7.5 %. 21d is
  frozen, so it needs a 21d amendment committed before the read (the definition allows that, "never after").
- The disclosure (§9 item 7) states the numbers on every WCD / WCB_2 / MS row.

### (c) The Midland level drifts by fold (C8 1.000 → 0.960) — ★ ship the fitted 1.067

- C8 (unexposed test children, F = 1) pooled 0.983 [0.959, 1.008]: no shortfall overall, but the newest fold reads 0.960. The level
  carries on 7,368 unexposed Midland forecast sticks (26 % of the 28,809) and lifts their oil 6.7 %. 46 % of Midland forecast
  sticks carry a factor above 1.
- The alternatives are both post-look: a level of 1.0 (the cap Michael lifted at 24a, G3) or one refitted on the latest fold.
  21d tests the level directly on 2026 wells (the method block pins 1.0674). Disclosed (§9 item 7).

### (d) Delaware: derive from run 25, or rebuild — ★ derive (D153); carry the 127 re-admitted sticks as refused

- **What moved** (§3.1): production +1 month, Novi spacing (nightly), configuration drift (774 sticks), reconciliation (136
  drilled, 634 conflict). Pools did not move: the refresh contract moves them at 13c, and none has been applied. Overrides have
  not moved since 2026-10-29, the day before run 25. D144's rebuild trigger ("tags or pools") is not met.
- **A rebuild** costs ~7 h of fits, water (~25 min) and a fresh re-measure. It brings production +1 month and the spacing
  revisions, and duplicates 13c. The 13b rehearsal measured that kind of rebuild at oil −0.59 %.
- **The derivation** is exact and checked row by row (§4.1): 48,706 forecast sticks, oil 25,752.9 MMbbl.
- **The 127 re-admitted sticks** now clear D114 because the drilled-children counts grew (BS3_S 56, BS3_C 20, others ≤ 9; 124
  multi-parent; run 25 refused them on package 70 / precedent 57). Run 25 has no rows for them. Their pre-proximity rows exist
  only in the run-24 build artifact (`runs/box_d117s3/run.pkl`, run 24 pruned). Choices:
  - **carry run 25's refusal** (`--readmitted carry-refusal`; 13c's refresh re-decides them) — recommended, 0.3 % of sticks;
  - augment them from the run-24 artifact (code not written);
  - rebuild.
  The store refuses until one is chosen (`--readmitted refuse` is the default).

### (e) sql/71 is needed before any store — ★ apply it as drafted (container at 23b, live on its own go)

D150 cannot be stored under sql/65: the factor is capped at 1, the outcome words are D113's, and named parents must be ≥ 365
days on. D145 has no coverage value (§5). The draft relaxes only those rules, keeps every run-19 / run-25 row valid, and rewrites
nothing. The new words keep the stored outcome honest about what was applied: `level_unexposed` / `factor_single_parent` /
`factor_multi_parent`, never "as_is" for a stick carrying 1.046.

### (f) D145 for the Delaware — ★ extend it now (`--d145`): one drillability rule for both records, priced together

D145 rescinded D1's conflict clause for the Midland and said the Delaware keeps it "until the Delaware is revised". Step 23 is
that revision. Extending it moves **634 forecast sticks, 366.2 MMbbl (1.4 % of the derived oil)** to `not_covered_conflict`
(WCXY 123, BS2_S 109, BS3_S 99, BS3_C 97, WCB_1 88, others ≤ 21). Michael's card-13 call was general: conflict sticks are not
drillable locations. The settled Delaware spec is silent, so this is flagged, not assumed: without the flag the derived run
keeps D1, as run 25 does.

### (g) Which factor fires D114's package tier (≤ 0.80) — ★ the incumbent table factor

Step 24 measured "incumbent gates kept" this way (GATE_24A G4). The continuous factor scales oil only. Triggering on the D150
factor would change which sticks need packages (2,923 forecast Delaware sticks sit below 0.80 on D150). That would be a new
gate, not the incumbent. Both basins: the Delaware on the D113 candidate table, the Midland on the 21b table (D149 (3)).

### (h) Sticks reconciled as drilled since run 25 — ★ drop them from the derived universe

136 run-25 forecast sticks (76.1 MMbbl) are now `realized_phantom`. The derived run leaves them out entirely, and erebor classes
them `realized` from its own reconciliation (rule 11). Carrying them would put drilled slots in front of Steven.

### (i) erebor — ★ a small erebor PR before 23b's erebor check

§5: the proximity filter groups, the factor display (> 1) and the conflict class. Read-only, no endpoint change. Without it the
Midland Map still draws, but D150 outcomes fall outside every proximity filter and factors above 1 are hidden.

### Carried, not decided here
- Midland water: `box_water_run` on a Midland run is untested; smoke first at 23b.
- The 4 unapplied seed removals ride the next override batch (§3.2). They touch D64 planned spacing only, near 4 wells.
- `bench_scope.validation` for the nine Midland rows (the D151 tiers; today every Midland row reads the default `validated`):
  its own go at 23c.
- `store` and `flip` have not yet run against a database. Their first run is 23b, in the container.

---

## 8. D151's one-line text fix

The frozen 21a wording ("provisional: D99 FAIL, or no cell judgeable, or moved at the tuning gate") reads "**moved to
provisional** at the tuning gate". The fix is a NEW file, `docs/box/step21a-2026-10-31/ERRATA.md` (E1). The pre-registration
and `box/step21.DEFINITION` stay byte-identical: digest `9780f326` is pinned by tests and quoted by 21b / 21c / 21d. The plan's
D151 row points at the erratum. No score, interval or tier changes.

---

## 9. Workup disclosures (pud_forecast.flags + forecast_run.disclosure; the Steven note)

Per Midland group, the evidence pack carries the shipped treatment's tuning bias, the 21c holdout re-read on it, the
thin-control line and the latest vintage. Group lines, oil, error = actual / forecast − 1 (negative = BOX HIGH):

| group | tier | oil cum-12 / 24 / 36, shipped tuning | holdout re-read cum-12 / 24 / 36 | gas cum-12 / 24 / 36, tuning | thin-control oil cum-24 | latest vintage (2024 cutoff) oil cum-12 |
|---|---|---|---|---|---|---|
| WCA_1 (+ D102 as delivered) | validated | −2.2 / −2.3 / −2.2 % | −2.1 / −2.1 / −2.8 % | +4.9 / +8.4 / +14.7 % | −7.9 % | −5.8 % (107 pkg) |
| WCA_1 (+ D102 recomputed) | validated | 0.0 / 0.0 / +0.1 % | +0.1 / +0.2 / −0.5 % | same | | |
| LSSH | validated | −3.7 / −4.7 / −4.0 % | −2.7 / −4.0 / −4.3 % | −1.4 / −0.4 / +3.9 % | −5.3 % | −5.3 % (85) |
| WCD | validated | −11.2 / −11.5 / −14.3 % | −4.8 / −8.4 / −16.4 % | −1.8 / +11.8 / +6.8 % | −10.2 % | −4.2 % (38) |
| WCB_1 | provisional | −3.6 / −4.2 / −6.5 % | −1.6 / −1.4 / −0.9 % | +2.9 / +4.3 / +7.9 % | −1.6 % | −4.0 % (92) |
| WCB_2 | provisional | −9.2 / −12.0 / −15.8 % | +0.6 / −2.6 / −2.0 % | +2.9 / +4.4 / +7.2 % | −1.2 % | −10.4 % (24) |
| WCC | provisional | −10.7 / −18.4 / −24.0 % | no holdout | −0.5 / −7.1 / −1.8 % | −20.2 % | +14.4 % (4) |
| MS | provisional | −7.2 / −10.0 / −10.9 % | −16.0 / −13.4 / −16.2 % | +1.1 / −0.4 / −5.5 % | −17.6 % | −1.6 % (62) |
| JM | provisional | +1.2 / +10.2 / +14.5 % | −9.7 / −1.8 / +17.0 % | +1.3 / +6.9 / +15.3 % | +17.8 % | −9.9 % (67) |
| DEAN | provisional | −3.8 / −1.9 / −5.2 % | +20.0 / +21.0 / −0.4 % | +4.3 / +26.0 / +81.8 % | −0.3 % | −9.6 % (41) |

Source: `midland_pack_*.json` (the 21b tuning and 21c holdout views re-read on the shipped treatment; packages pooled over
cutoffs; the 21c lines on the 21 table stay in `docs/box/step21c-2026-11-02/disclosure.csv`). The holdout is read again here,
not scored: no tier moves on it (D151 stands).

Run-level disclosures (Midland unless marked):
1. **Long laterals:** targets > 15,000 ft run ~5–7 % high on oil (21b, revision 8 hybrid panel, reported never judged; D149 (6)).
2. **MS ships 7–11 % high on oil, raw** (provisional, no haircut; 21c: it lost its walk-forward haircut with the tier). Under D150
   the shipped tuning oil reads −7.2 / −10.0 / −10.9 % at cum-12 / 24 / 36. The holdout re-read is −16.0 / −13.4 / −16.2 %.
3. **DEAN under-forecast:** the 21c holdout ran oil +22 / +23 % and gas +29 % (gas BOX-specific). The tuning half reads the
   other way, so the disclosure shows both lines and never the pooled figure alone (D105).
4. **WCB_2, tuning vs holdout:** tuning oil −9.2 / −12.0 / −15.8 % (BOX high) against holdout +0.6 / −2.6 / −2.0 %.
   Provisional; the 2026 cohort is its route (D152).
5. **Water provisional on all nine groups** (D149 (5)): the D107 ratio on raw oil, the TX `measured` label as sql/41 has it.
6. **Graduation route (D152):** a provisional group becomes "proposed for validated" on consistency OR accuracy at the 2026
   cohort read (cum-12 at production through ≥ 2028-01-01). An accuracy-only graduate ships raw with the cohort line until its
   own gate. WCC is never judgeable (~1 package).
7. **D150 level:** every Midland forecast stick carries level x F (1.067 when no counting parent). WCD's shipped tuning oil is
   −11.2 % (BOX high) against −7.5 % on the 21 table it was validated on. WCB_2: −12.0 vs −9.2. MS: −10.0 vs −7.2. The level
   drifts by fold (C8 1.000 → 0.960). Questions (b), (c).
8. **WCC** (provisional, no holdout): tuning oil −10.7 / −18.4 / −24.0 % at cum-12 / 24 / 36, 4 latest-vintage packages.
   Thin by construction.
9. **Delaware (D153):** the derived record's oil = run 25's x (level 1.046 x F_R2 / the D113 table factor). Unexposed sticks
   rise 4.6 %; multi-parent sticks move by the curve-vs-table difference. 13d's 2026 Delaware prospective (D125) tests run-19's
   method. The step-23 Delaware change (D150) is disclosed beside it, as D150 G6 foresaw.
