# BOX step 9c — production run covering WCA + BS2_S + WCXY — REHEARSED IN A CONTAINER, AT GATE 9c

**Built 2026-10-17. Nothing is written to Supabase.** The run was built read-only from the live warehouse and stored as the
record ONLY in a throwaway PostGIS container (`box9c`, port 5435). Live record is still **run 7** (WCA only).

Review surface: `index.html` (this folder) + 13 sample pad workups in `workups/` (all 2,771 pads in `runs/box9c/workups`,
git-ignored, main checkout). Code: `scripts/box_pud_run.py` (`--benches`), `box/production.py` (`PRODUCTION_BENCHES`,
coverage per group, `merge_cells_by_cutoff`), `box/production9c.py` (per-group haircut / disclosure / caveats),
`box/production_pages.py`, `scripts/box_run_compare.py`; tests in `tests/test_box_production.py`.

## 1. Kickoff decisions (Michael 2026-10-17, recorded in plan §2)

- **D102 — BS2_S production haircut:** D62-style pooling from BS2_S's own packages: its 9a tuning and 9b holdout box_v2 cells are
  merged per cutoff, then the ≥ 30-package floor applies. The holdout cells alone hold 0–40 packages, so a per-cell floor would
  admit only 2 of them.
- **D103 — spec label, no DDL:** the run row keeps `spec = 'box_v2_wf'` (the sql/60 CHECK). Each group's spec sits under
  `by_bench` in `haircut` / `calendar_factor` / `disclosure`; WCXY = raw `box_v2`, haircut `none (D97)`, factors 1.0. The run
  notes name every group's spec.
- eng_db #149 (gate-9b record, D100 / D101) merged first, so this branch carries D100 / D101.

## 2. What was built

`python -m scripts.box_pud_run build --benches WCA,BS2_S,WCXY_WCA1 --wells docs/box/pool-2026-10-15 --out runs/box9c --workers 14`
(107 min, code `842e194`, clean). One cutoff for all groups: **2026-08-01, production through 2026-07-01**. That is the same
data-through as run 7 and as the 9a / 9b scoring. Pool = the D84 refresh `pool-2026-10-15` for every group (run 7 used the frozen
step-1 set).

| Group | Spec (record) | Pool (fitted wells inside the extent) | Extent | Path |
|---|---|---|---|---|
| WCA (WCA_1 + WCA_2) | box_v2_wf, D62 haircut | 12,216 | 6 | the 7c path, unchanged |
| BS2_S | box_v2_wf, own haircut (D94, D102) | 4,233 | 7 | the 9a / 9b analog fold (`run_fold_analog`'s pool lines), label `BS2_S` |
| WCXY (WCXY_WCA1) | raw box_v2 (D97) | 7,588 (WCXY + WCA_1 tags, D93) | 6 (D95) | same analog fold, label `WCXY` |

**Harness equivalence:** for each group, 24 seeded locations were re-run through the harness's own `predict_location_v2`
(k = 600). Monthly volumes are identical, max relative diff **0.0** for WCA, BS2_S and WCXY alike. So the production path is the
path 9a / 9b scored.

**WCA vs record run 7** (`wca_vs_old.json` / `.csv`):
- Same 1,912 sticks; 1,907 have forecasts in both runs.
- **Named analog sets identical on all 1,907**, so the 2 wells the D84 refresh added are never selected.
- Oil EUR sum ratio 0.99997 and gas 0.99992. Ratios are exactly 1 (to 1e-9) on 1,723 locations for oil and 1,745 for gas.
- 178 locations moved by more than 1e-6, at most +/−0.53 %. With identical analogs, the cause is revised production in the analogs'
  own histories (the D98 drift pattern). Not traced per well.

## 3. Identity (container store, `runs/box9c/store_container.txt`)

`store --record` into the container, which holds the live box state copied read-only: `bench_scope` 18, `extent` 18,
`location` / `location_source` 33,228, and runs 4 / 6 / 7 with 7 as record. All checks green in one transaction (453 s):

| Check | Result |
|---|---|
| pud_forecast rows = universe | **121,727 = 121,727** |
| [WCA] covered + no_analogs = in-extent WCA_1/WCA_2 universe | **1,907 + 5 = 1,912** |
| [BS2_S] covered + no_analogs = in-extent BS2_S universe | **7,394 + 15 = 7,409** |
| [WCXY] covered + no_analogs = in-extent WCXY universe | **3,183 + 5 = 3,188** |
| all covered groups | 12,484 + 25 = 12,509 |
| oil / gas stream rows = covered | 12,484 / 12,484 |
| every stream: 600 months summing to its EUR within 0.1 % | 24,968 stream groups, **0 off** |
| every covered location ≥ 3 named analogs | min 3, max 20; all 12,484 covered locations carry analog rows |

Result: **run 8 stored as RECORD**, run 7 superseded and kept (D75).

Coverage: covered 12,484 · no_analogs 25 · outside_extent 9,322 · unvalidated 86,114 · emerging 13,782.

- The in-extent counts were re-derived at run time. BS2_S is **7,409**, not the ~7,478 of 7b: the D87 reconciliation refresh
  moved statuses in between.
- **The universe grew from 33,034 (run 7) to 121,727.** `box.bench_scope` gained the step-15 Delaware benches after run 7, and D67
  rows every in-scope PUD. The new benches are `not_covered_unvalidated`. Their 88,693 sticks become new `box.location` rows
  (match method `seed`, same 2026Q3 vintage). The 33,228 existing ids are reused, so live will mint different new ids than the
  container did.
- erebor's own reader functions (`app/api/box.py`: `disclosure_rows`, `haircut_method`, `calendar_factor_points`,
  `radius_ranges`), run against the container's run 8, parse it unchanged and serve the WCA keys. See ask 3.

## 4. Numbers (`groups.csv`; grain = covered PUD locations; P10 = high)

| Group | Stream | Locations w/ forecast | EUR total | EUR/kft P10 · median · P90 | Haircut on EUR (sum) | Di nominal median (1-yr eff) | b median | past-5-mi | strike |
|---|---|---|---|---|---|---|---|---|---|
| WCA | oil | 1,907 | 1,096.6 MMbbl | 89,246 · 63,597 · 45,782 bbl | 0.839 | 3.21 /yr (76 %) | 1.01 | 26 % | 13 % |
| WCA | gas | 1,907 | 5,620.7 Bcf | 554.7 · 301.5 · 121.9 MMcf | 1.084 | 1.78 /yr (62 %) | 1.14 | | |
| BS2_S | oil | 7,394 | 3,670.1 MMbbl | 74,783 · 56,736 · 42,443 bbl | 0.767 | 3.28 /yr (77 %) | 0.99 | 44 % | 20 % |
| BS2_S | gas | 7,394 | 13,592.8 Bcf | 326.5 · 206.1 · 85.2 MMcf | 0.746 | 1.38 /yr (56 %) | 1.17 | | |
| WCXY | oil | 3,183 | 2,101.1 MMbbl | 105,798 · 81,208 · 54,778 bbl | 1.000 | 2.95 /yr (75 %) | 0.99 | 21 % | 10 % |
| WCXY | gas | 3,183 | 10,401.0 Bcf | 688.9 · 385.6 · 154.2 MMcf | 1.000 | 1.71 /yr (61 %) | 1.14 | | |

Gas EUR/kft = MMcf per 1,000 ft of lateral.

All EURs are the raw 50-yr integral of the **analog-cohort P50** (D57) × lateral × the stated haircut. Volumes are uptime-free:
F(k) is published, NOT applied (D63). No water (D72), no economics. WCXY carries no haircut (D97), so its numbers are not
comparable one-to-one with WCA's haircut ones: WCA's raw oil EUR is 1 / 0.839 ≈ 1.19 × its delivered EUR.

**Haircut as applied (D92 C1 rate shape), realised median cum factor at 12 / 24 / 36 / 48 months:**

| Group | Stream | D62 / D102 targets (12 / 24 / 36 / 48) | Realised (12 / 24 / 36 / 48) | Tail rate factor | EUR factor |
|---|---|---|---|---|---|
| WCA | oil | .943 / .929 / .916 / .876 | .950 / .920 / .903 / .891 | 0.768 | 0.839 |
| WCA | gas | 1.002 / 1.021 / 1.019 / 1.059 | .998 / 1.022 / 1.036 / 1.045 | 1.122 | 1.084 |
| BS2_S | oil | .891 / .873 / .832 / .828 | .895 / .861 / .841 / .827 | **0.681** | **0.767** |
| BS2_S | gas | .937 / .912 / .883 / .810 | .951 / .893 / .860 / .837 | **0.667** | **0.746** |
| WCXY | both | 1.0 | 1.0 | 1.0 | 1.0 |

The WCA rows are run 7's exactly.

**F(k) (published, not applied), at months 12 / 24 / 36 / 48:**

| Group | Oil | Gas |
|---|---|---|
| WCA | .895 / .907 / .910 / .921 | .918 / .945 / .955 / .979 |
| BS2_S | .879 / .871 / .867 / .871 | .888 / .913 / .941 / .982 |
| WCXY | .868 / .876 / .883 / .896 | .921 / .940 / .952 / .974 |

## 5. Disclosure carried by every workup (D59 cond. 3, D100, D101)

Each pad page shows one block per group on the pad (index shows all three):
- the raw box_v2 bias the haircut corrects;
- the factor applied;
- the **disclosed bias = tuning bias** (D100; the D99-pooled cell where 9b judged it);
- the 9b holdout bias with its frozen D99 interval;
- the D69 radius-class range. For BS2_S / WCXY that range comes from 9a tuning packages pooled across cutoffs
  (`spread_by_radius_<bench>.csv`, `box_pud_run radius`).

Caveats also travel as `pud_forecast.flags` text, so erebor's workup table shows them today:
- **D101 BS2_S south edge:** 1,101 of 7,409 in-extent locations. Oil cum-12 −26 % tuning / −31 % holdout.
- **D101 BS2_S other-edge watch item:** 2,069 locations. Oil cum-12 +13 / +20 %, cum-24 +19 / +32 %.
- **D100 WCXY call-out:** all 3,188. Raw box_v2, no haircut, disclosed oil cum-36 −9.2 %.

Edge region = ≤ 5 mi from the extent-7 boundary; south = bearing 135–225° from the centroid (`tune9a_report.edge_classes`, the
9a definition).

## 6. Gate-9c asks

1. **Go to store live as the record?**
   - Command: `python -m scripts.box_pud_run store --record --out runs/box9c`, run from the main checkout. The artifact is copied
     there; sha256 matches the build.
   - Run 7 is superseded and kept (D75). Steven has priced nothing (`box_econ.box_pud_econ` = 0 rows).
   - The container took 7.5 min; Supabase will be slower, mostly the 15.0 M-row month COPY.
2. **Storage:** run 8 adds **15.0 M `pud_forecast_month` rows ≈ 1.9 GB** (container size). Live today is 837 MB for runs 4 / 6 / 7;
   the database is 75 GB.
   - Acceptable as is?
   - Or prune the superseded runs 4 / 6 months later? That would change D75's "kept", so it is your call; not proposed here.
3. **erebor shows WCA's disclosure on every pad (needs a small erebor change).** `disclosure_rows` / `haircut_method` /
   `calendar_factor_points` read the top level, which is WCA's (D103). So a BS2_S or WCXY pad in erebor would show WCA's haircut
   and bias table, although its flags carry the D100 / D101 text.
   - Fix: read `run["haircut"|"disclosure"|"calendar_factor"]["by_bench"][group]` by the location's bench / formation.
   - Recommend landing it **before** the live store (or storing and fixing the same day).
   - This contradicts the plan's "erebor needs no change" for the disclosure panel; coverage classes do flow through unchanged.
4. **BS2_S EUR haircut −23 % oil / −25 % gas (flag, not a proposal).**
   - The D92 shape holds the month-48 rate factor (0.68 / 0.67) for life. It is applied exactly as approved for WCA (tail 0.77).
   - But BS2_S's cum-48 knot rests on one cutoff (2021, 76 packages), and its cum-36 → 48 targets are flat (.832 → .828), while the
     rate factor that fits them keeps falling.
   - Holding the cum-36 knot instead would be a spec change needing its own decision; no change made.
5. **Steven note:** run 8 adds BS2_S + WCXY. His pricing keys on `run_id` + `location_id`. Per-group haircut / F(k) are under
   `by_bench`. D86 pattern: you send it. A draft can follow the live store.

No §2 conflict found beyond ask 3 (the plan's "erebor needs no change" for the disclosure panel) and the sql/60 spec CHECK, which
D103 settled.

## 7. Live store (2026-10-17, Michael's go: "store runs/box9c live as the BOX record (run 8); fix erebor right after")

Pre-check, read-only: live record = run 7; 33,228 locations / location_source (2026Q3 only); 18 bench_scope rows;
`box_econ.box_pud_econ` 0 rows. That is exactly the state the container rehearsed.

Store: `python -m scripts.box_pud_run store --record --out runs/box9c` against Supabase (session pooler 5432; log
`runs/box9c/store_live.txt`, 313 s, one transaction).
- **run_id 8 = RECORD.** Run 7 is superseded and kept (D75).
- 121,921 locations: 88,693 new seeds + 33,228 reused.
- Every identity check is green, the same numbers as the container: universe 121,727; WCA 1,907 + 5; BS2_S 7,394 + 15;
  WCXY 3,183 + 5; 24,968 stream groups, 0 off; ≥ 3 analogs everywhere.

Re-verified read-only after COMMIT:
- Per-group EUR totals and EUR/kft medians equal §4 exactly. Oil 1,096.6 / 3,670.1 / 2,101.1 MMbbl; gas 5,620.7 / 13,592.8 /
  10,401.0 Bcf.
- `haircut.by_bench` carries WCA, BS2_S and WCXY_WCA1.
- 14,980,800 month rows; `box.pud_forecast_month` 2,705 MB, database 76 GB.
- erebor `/api/box/meta?basin=delaware` serves run 8.
- Ask 3 fix: erebor https://github.com/mastmj812/erebor/pull/14. /meta and /pad return one disclosure block per group from
  by_bench; verified on live run 8 (Pad 1213: BS2_S ×0.891, WCXY ×1.000 with oil cum-36 −9.2 %). Open, awaiting merge.
