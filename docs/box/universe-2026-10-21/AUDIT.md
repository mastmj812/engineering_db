# BOX universe = every Novi stick in a BOX extent (D117) — step 1: decision + read-only audit

2026-10-21. **Step 1 of 5. Nothing is written to Supabase in this step.**

## Decision (Michael, 2026-10-21)
> "If a Novi location is inside the BOX extent for the respective bench, we take it."

- Novi's BASE_CASE / UPSIDE (PUD / RES) tag no longer decides what BOX forecasts. This amends D1 ("No RES/UPSIDE") and D67 ("no RES").
- erebor already reads only Novi's stick geometry, DSU pads and its forecast (as a plot comparison). This decision makes BOX do the same.

Michael's read on the UPSIDE sticks, each of which an existing BOX gate already screens:

| Novi UPSIDE case | BOX gate that screens it |
|---|---|
| Far from PDP, judged geologically viable by Novi | Extent (D5 / D27): outside → `not_covered_outside_extent` |
| Aggressively spaced child in the developed area (Novi's own "less likely" call on proximity / depletion, not rock) | PDP-proximity layer: oil × factor (D113) or `not_covered_no_precedent` (D114); spacing measured like any PUD |

## Measurements (read-only, 2026-10-21)

### 1. In-extent RES sticks
Delaware, record extents, BOX's own rule: ≥ 50 % of the stick length inside the extent (`box/production.INSIDE_SHARE`).

| Pool | Bench | In extent | remaining | conflict | realized | Overlap a same-bench PUD ≥ 50 % |
|---|---|---|---|---|---|---|
| WCA | WCXY | 5,192 | 4,999 | 58 | 135 | 0 |
| WCC | WCC | 577 | 563 | 4 | 10 | 0 |
| BS3_S | BS3_S | 502 | 496 | 1 | 5 | 0 |
| BS3_C | BS3_C | 40 | 36 | 1 | 3 | 0 |
| AVA_1 | AVA_1 | 24 | 23 | 1 | 0 | 0 |
| AVA_2 | AVA_2 | 20 | 19 | 1 | 0 | 0 |
| AVA_0 | AVA_0 | 17 | 14 | 1 | 2 | 0 |
| WCB_1 | WCB_1 | 8 | 8 | 0 | 0 | 0 |
| **Total** | | **6,380** | **6,158** | **67** | **155** | **0** |

- The status columns apply sql/21's rule verbatim to RES sticks.
- **6,225 would join the D1 universe** (remaining + conflict). None duplicates an existing PUD slot.
- Spacing was measured against the nearest Novi PUD stick on the **same bench**:

| Bench | Median distance | Within 660 ft | Beyond 1 mi |
|---|---|---|---|
| WCXY | 45,105 ft | 1 | 4,812 |
| WCC | 27,970 ft | 0 | 507 |
| BS3_S | 8,862 ft | 0 | 349 |

- 6,380 of 6,380 sit on a pad that already holds Novi PUDs.
- So these are mostly Novi's stacked "upside" benches inside DSUs whose base case is another bench. They are not infill between PUDs.

**Disclosure caveat (not a blocker):**
- WCXY is judged inside the **WCA** extent (D95). It is forecast by its group's method: raw box_v2 on WCXY + WCA_1 analogs, no haircut (D93 / D97).
- The proximity layer counts PRODUCING parents (≥ 12 months). The WCA wells planned in the same DSU are not seen, so WCXY-under-WCA co-development is not haircut. The run disclosure and the workup must say so.

### 2. Reconciling every RES stick (both basins)
The sql/21 rule applied to every RES stick, read-only:

| Basin | RES | remaining | conflict | realized_phantom | realized_drift |
|---|---|---|---|---|---|
| Delaware | 49,602 | 49,188 | 120 | 294 | 0 |
| Midland | 25,100 | 25,052 | 19 | 29 | 0 |

- 312 producers would realize a RES stick (288 Delaware, 24 Midland). **None** is in `net_new_pdp` today; all are already matched to a Novi PUD.
- The live forecast-accuracy population is empty (the 2026Q3 vintage has no blind wells yet). sql/38's direct-tier shift therefore changes nothing today and starts to matter as wells come online.

## Consumer audit: what changes if `curated.reconciled_inventory` covers PUD + RES
Joins cannot multiply rows, because `stick_id` stays UNIQUE (sql/21:130).

### Output does not change (they filter to PUD first, or never read it)
- sql/20, sql/25, sql/29, sql/30, sql/32, sql/43, sql/44, sql/47, sql/50, sql/60.
- `box/production.py`, `box/extent_report.py`, `box/tc_area_report.py`, `family_extent.py`.
- anduin (no reads).
- erebor Highgrade, BOX workup, `coverage_sql`.
- narvi: TVD, bench counts and spacing queries. RES passes before status is tested.

### Output changes

| Consumer | Change |
|---|---|
| sql/22 `erebor_locations` | RES rows get a non-NULL `recon_status` (row count unchanged). The comments "NULL = RES" (sql/22:89-91, sql/31:681) go stale. |
| sql/38 `intel_forecast_accuracy` | Blind wells that realize only a RES stick move from the proxy to the direct tier. That RES stick's Novi forecast becomes the comparison. `n_sticks_for_well` can rise. |
| sql/43 accuracy_vintage | Re-derives its match from BASE_CASE only, so its direct tier diverges from sql/38's for the live vintage. |
| sql/25 `net_new_pdp` | Output unchanged, but **inconsistent**. A post-vintage producer that realizes only a RES stick stays net-new while that stick becomes `realized_drift`. That double-counts the well in the "new ≈ realized_drift + net_new" anchor (sql/25:25-26 already lists "RES exclusion" as a future refinement). |
| erebor map (`box_locations.map_coverage_sql`) | Realized RES sticks show `realized` instead of `not_screened` / `bench_not_in_box`. Wanted. |
| erebor gun-barrel / ResultsPanel "remaining only" | Realized and conflict RES drop out (they used to pass as NULL). Overhaul step 4 rewrites both anyway. |
| erebor `/api/recon_counts` | The NULL bucket shrinks by roughly the RES count. |
| narvi `_STICK_SQL` (`warehouse.py:845`) | Labels only: RES rows get a `recon_status` (Status / RECON_STAT columns). Realized RES are **still offered as inventory**, because RES bypasses the status test. |

### Breaks or must be fixed in the same change

| File | Fix |
|---|---|
| `scripts/apply_wellstick_fix.py:134-145` | Asserts `count(reconciled_inventory) == mapped PUD universe`, so it will raise. Change it to PUD + RES. |
| `.claude/skills/novi-quarterly-reload/SKILL.md` §7 | The identity "= the mapped-PUD universe exactly" becomes PUD + RES. |
| `scripts/apply_reconciled_inventory.py:111-123`, `scripts/apply_followups.py:88-99` | Split the drift anchor by category. `apply_followups` also does not rebuild sql/38 after a standalone sql/21 (an existing gap; fix it while there). |
| Stale comments | sql/21 header + :141, sql/22:89-91, sql/31 (:650, :658, :681, :779), sql/38:24, erebor `store.ts:95`, narvi `warehouse.py:829`. |

### Blast radius of a standalone sql/21 rebuild
- `DROP … CASCADE` drops `erebor_locations` (sql/22, so the erebor map goes dark) and `intel_forecast_accuracy` (sql/38).
- Rebuild in this order: sql/38, then sql/22, then sql/26, then sql/31.
- The heavy lateral pass grows by about 75k sticks: roughly +50 % build time, run off-hours.
- The quarterly chain order (novi-quarterly-reload §5) works unchanged.

## Decisions needed at the step-1 gate (recommendations first)
1. **sql/25 `net_new_pdp` counts RES too** (`category IN ('PUD','RES')`). Recommended: keeps "new ≈ realized_drift + net_new" honest.
2. **sql/43 vintage accuracy matches EMERGING too.** Recommended: live and vintage direct tiers stay comparable.
3. **narvi hides realized RES slots** like realized PUDs (status test at `warehouse.py:577/640/738/845`). Recommended: a drilled slot is not inventory, whatever Novi called it. This is a narvi PR after the warehouse step.
4. **Delivery shape for step 2:** a new `sql/68_reconcile_all_sticks.sql` that supersedes sql/21's body (sql/21 becomes a pointer, same matview name and columns), applied off-hours with the rebuild order above. Recommended over editing sql/21 in place, per the warehouse-change skill.

## Steps (D117 plan)

| # | What | Writes |
|---|---|---|
| 1 | **This PR:** D117 recorded; this audit | none |
| 2 | sql/68: reconcile every Novi stick (+ sql/25 / sql/43 per the decisions); must-fix list; off-hours apply. Verify: PUD rows identical to today; RES rows = the counts above. | **Supabase (explicit go)** |
| 3 | BOX universe drops `category = 'PUD'` (`box/production._UNIVERSE_SQL`); container rehearsal at run 14's cutoff. Run-14 rows must reproduce exactly; additions only. Proximity is re-measured on every record run (D116). Coverage per bench for the added locations. | none |
| 4 | Store run 15 as the record. Run 14 is kept because it is priced. Verify erebor (`not_screened` collapses). | **Supabase (explicit go)** |
| 5 | Steven re-prices run 15. erebor shows econ only once run 15 is priced (record-run rule). | Steven |

## Step 2 (built 2026-10-21, NOT applied)
Gate-1 decisions accepted by Michael: (1) sql/25 counts RES; (2) sql/43 matches EMERGING; (3) narvi hides realized RES (narvi PR after the live apply); (4) ship as sql/68, sql/21 a pointer.

- **New `sql/68_reconcile_all_sticks.sql`.** sql/21's body byte for byte, with the stick filter widened to `category IN ('PUD','RES')` and a `category` column (+ index) for audit splits only.
- **sql/21 is a tombstone** that keeps the rule's rationale. sql/32 `\ir`, `apply_reconciled_inventory`, `apply_followups` and `apply_wellstick_fix` now run sql/68.
- **sql/25** overlaps every Novi stick. **sql/43** matches BASE_CASE + EMERGING. Stale comments updated in sql/22, sql/31 and sql/38.
- **Must-fix list done:**
  - the `apply_wellstick_fix` identity is now PUD + RES;
  - the drift anchors are split by category;
  - `apply_followups` now rebuilds sql/38 + sql/43 (the existing gap);
  - SKILL §5 / §7 updated.
- **New `scripts/apply_reconcile_all_sticks.py`.** The live run is 68 → 25 → 38 + 43 → 22 → 26, then validation. `--dry-run` is read-only.
- **Dry run on live data (read-only, 42 s):**
  - Rows: 257,397 = the mapped PUD + RES universe exactly.
  - PUD sticks: the same set (0 missing / 0 extra).
  - PUD status x category: 176,014 remaining / 2,333 conflict / 4,348 realized_phantom. RES: 74,240 / 139 / 323.
  - `net_new_pdp`: 0 → 0 (the 2026Q3 vintage is too recent for post-vintage producers).
- **Reconciliation drift (not a rule change).**
  - sql/68's PUD rows are identical to sql/21's rule recomputed on the same data: 182,695 / 182,695.
  - The live table differs on 262 PUD rows because it is quarterly-owned while its inputs refresh nightly (D87): 183 keep their status with a moved matched well, and 79 change status.
  - Net effect: 59 PUDs leave the remaining pool (53 remaining → realized_phantom, 11 remaining → conflict, 6 conflict → realized_phantom, 1 realized → conflict) and 8 return (4 realized → remaining, 4 conflict → remaining).
  - The live apply absorbs this drift. **Step 3's identity check must expect it:** run-14 PUDs whose reconciliation moved leave or rejoin the BOX universe.

### Step 2 applied live, 2026-10-21 16:25 UTC (Michael's go, after the nightly)
`python -m scripts.apply_reconcile_all_sticks` ran in **103 s**, all checks green:

| Stage | Time / result |
|---|---|
| sql/68 | 27 s |
| sql/25 | 1 s |
| sql/38 + sql/43 | 24 s |
| sql/22 | 6 s (the erebor map was dark for about 50 s in total) |
| sql/26 | 5 s |
| Rows | 257,397 = the mapped PUD + RES universe; 0 duplicate keys |
| PUD sticks | the same set; 262 drift rows absorbed, exactly as the dry run predicted |
| `erebor_locations` | 317,913 → 317,913; all 74,702 RES rows carry a `recon_status` |
| `net_new_pdp` | 0 → 0 |
| sql/43 (2025Q3 vintage, direct tier, now incl. EMERGING) | Delaware 1,092, Midland 932 |
| GiST tile index | in use |
| CONCURRENTLY smoke | ok |

Post-apply tail:
- this data dictionary;
- narvi PR (realized RES hidden);
- an erebor comment PR;
- the workspace CLAUDE.md identity + narvi rule 11.

Next = **step 3** (BOX rehearsal) on Michael's go.

## Step 3 (built 2026-10-30, at the step-3 gate)
Run 14 has since been replaced: the record is run 19 (D123), so step 3 rehearsed against run 19. Results and the gate asks:
`step3/FINDINGS.md`.
