---
name: blueox-curve-drop
description: Build, sweep, and stage a Blue Ox curve-drop workbook (or re-drop) for the engineering→finance handoff — scenario re-save recency, config re-pin, pre-send sweep, covering note, amendments ledger. Use when a deal is ready to hand to Steven, a narvi/anduin fix invalidates a shipped drop, Steven raises a query on a delivered workbook, or a zone split/rename/risking change forces a re-export.
---

# Blue Ox curve drop — build → sweep → stage for send

The recurring engineering→finance deliverable. Contract of record:
`docs/blue_ox_curve_drop_contract.md` (v1 + merged amendments); every deviation we emit that the
contract doesn't describe lives in `docs/blue_ox_contract_amendments_pending.md` (the ledger, §
numbers cited everywhere). Builder: anduin `exports/blueox.py` (pure); endpoint
`POST /api/deals/{id}/blueox-export.xlsx`; config pinned in `deals.blueox_config` (migration 0024).

**Hard rules:**
- One anduin deal = one Blue Ox codename = **one governing workbook**. A re-drop SUPERSEDES the
  prior file — never overwrite it; the covering note names the superseded filename.
- Column/sheet/key names are **FINAL once the first workbook carrying them ships**.
- Blue Ox percentiles are **ASCENDING** (their p10 = LOW — opposite of house SPE). The flip lives
  ONLY in `exports/blueox.LEVEL_TO_SPE_KEY`. Never re-derive it, never emit percentile water
  columns (water is P50-only), never emit partial triplets (oil+gas required at every delivered
  level).
- NGL ships all-zero with `ngl_basis = derived_by_blue_ox_via_yield` (they derive via yield).
- `reserve_category` is `PUD` / `UPSIDE` (`RES` is refused at build). `di_convention =
  nominal_annual`, always.
- **Claude prepares and sweeps; Michael sends.** Never email/transmit anything to Steven.
- Any new deviation the drop carries → ledger section written **in the same commit** as the code,
  with a "Loader impact" line marked *required* vs *tolerated*.

## 0. Kickoff — confirm the inputs

Record before building: codename; which narvi scenarios/units contribute; `curve_months`;
percentile levels (subset of P10/P25/P75/P90 — P50 always ships); `normalization_basis`
(`per_1000_lateral_ft` | `per_well`); `production_history_through` (`YYYY-MM`); risking decision
(unrisked vs `geologic_multipliers_applied` + the MULs); Novi Intelligence vintage
(`novi_intel_vintage`); whether this SUPERSEDES a prior drop and whether the zone list changed
(a §11 split/rename must be declared in the covering note).

## 1. Scenario recency + integrity (the step that keeps biting)

For every contributing `(deal_id, scenario_id)`:

1. **Re-saved after the latest relevant narvi fix?** Compare `narvi.scenario.updated_at` against
   the merge time of the most recent narvi change touching azimuth resolution, category scoring,
   overrides, `novi_rep` selection, or naming. Saved scenarios keep old-rule values indefinitely —
   the *persisted-first trap*. Anything stale → re-save in narvi first (section 2).
2. **Right parcel?** `deal_id` derives from the *selected parcel* at save time. A scenario saved
   under the wrong parcel files under the wrong deal, is invisible in the drop modal, and 422s
   config saves (*phantom pin*). Check the scenario list shows every expected unit under this deal.
3. **Overrides survived?** `SELECT` the scenarios' `params->'category_overrides'` (or the modal's
   override counts) and compare to the expected per-unit counts. A re-save that silently persisted
   empty overrides shipped 4 wrong PUD→UPSIDE flips once (toucan drop #2 → Steven query). narvi
   now 409s on `override_drop` — a `force: true` in the history is a red flag to investigate.
4. **Self-consistency sweep** (read-only, narvi schema):
   - Stored header `azimuth_deg` vs the median of the scenario's own kept-stick bearings — axial
     delta > 5° = bad frame (the toucan azimuth defect signature).
   - **§6 offset invariant:** every `inventory_well` `gunbarrel_offset_ft` must reproduce to
     0.0 ft from `dsu_meta.azimuth_deg` + the parcel centroid (recompute with
     `narvi.placement.gunbarrel_offset_ft` — axis 90° CW of the folded azimuth, +offset = east for
     N-S laterals).
   - Per-unit planned-PUD/UPSIDE counts and PDP counts match expectations; PDP azimuth spread is
     plausible against the uniform header azimuth.

## 2. Re-saves (only if step 1 found staleness)

In narvi, per scenario: load it (load resets params to defaults + scenario — correct; don't
"preserve" leftovers), **confirm the correct parcel is selected before saving**, confirm the
override chips are populated, save. Expect the 409 override guard if something would drop —
resolve, don't force. Then re-run the step-1 sweep. Every re-save bumps `updated_at`, which stales
the Blue Ox config → step 3 is now mandatory.

## 3. Config re-pin

Open the deal's BlueOxDropModal (or `GET /api/deals/{id}/blueox-config`). Stale badges mark pinned
scenarios whose `updated_at` moved. Re-confirm each pinned `(deal_id, scenario_id)` selection and
re-save the config — that re-pins. Export from a stale config 409s; `allow_stale=true` exists but
is almost always wrong — re-pin instead. Red rows that won't pin = phantom pins (step 1.2).

## 4. Zone list + scope check

- Zone names ≤26 chars, none of `: \ / ? * [ ]`, no leading/trailing space/apostrophe, not a
  reserved sheet name (`meta`, `inventory`, `manifest`, `analog_production`, `curve_params`,
  `dsu_meta`, `novi_comparison`, `novi_comparison_meta`), unique.
- Same-bench splits (§11, e.g. `WCB_2_W`/`WCB_2_E`): shared `bench` code, **scenario scopes
  disjoint and covering** — anduin hard-errors overlap or a planned well no zone's scenario covers
  (`scope_missed`). PDP wells are never dropped (unzoned PDP lands on `inventory` with the bench
  code as `area` — sanctioned, §2).
- Zone list stable vs the prior governing drop, or the rename/split is declared (a re-drop split
  SUPERSEDES the old zone name — say so in the covering note).
- Strat tab order set as Michael wants it (zone tab-order controls, anduin #33).

## 5. Risking

If risked: MULs confirmed per zone, `qi_basis = fitted_qi_risked`, manifest
`risking = geologic_multipliers_applied`, `risk_mult` column present. Risking applies at the
export boundary only — stored series stay the clean fit. Versions inherit parent multipliers;
verify the pinned curve version carries the intended ones.

## 6. Build

`POST /api/deals/{id}/blueox-export.xlsx` from the saved config (bearer JWT via
`/api/auth/login`). Filename `<codename>_curves_<YYYY-MM-DD>.xlsx` — must not contain
`type_curves` / `areas` / `pdp` / `pinned`. A 422 is `BlueOxContractError` from `_validate` —
fix the cause, never relax the validator. A 409 is staleness — back to step 3.

## 7. Pre-send sweep

`_validate` already enforced at build time: complete triplets, ascending monotonicity across
levels, curve_params oil+gas P50 coverage + `di_convention`, analog sheet exactly-one-api-column,
inventory categories + 3,000–25,000 ft lateral bounds (PDP exempt), `analog_production` two-way
tie-out minus declared exceptions, gunbarrel frame ⊆⊇ `dsu_meta`, novi_comparison exactly-once
per zone (n=0 rows required for stickless zones), vintage declared.

Now run the checks the validator can't:

- [ ] **§3 gate 2 — Block B reconciliation**: manifest per-zone `eur_oil_bbl` / `eur_gas_mcf` /
      `eur_ngl_bbl` tie the FINAL sheets within ±0.1% (Block B is computed from the sheets, not
      the source system — verify it stayed that way).
- [ ] **§3 gate 3** — `gross_locations` and avg producing/drilled lateral per zone tie the
      inventory sheet exactly (PDP display rows excluded from both).
- [ ] **§6 invariant** on the workbook itself: every `inventory.gunbarrel_offset_ft` reproduces
      to 0.0 ft from `dsu_meta.azimuth_deg` + origin.
- [ ] **§8** — all coordinate pairs lon-first; heel columns blank where the stick isn't 4-vertex
      (`ST_NPoints ≠ 4`); `wellstick_wkt` present. (Pre-2026-07-29 drops' heel columns are known
      untrustworthy — never copy from them.)
- [ ] **§10** — per-well `lateral_azimuth_deg` = own as-built bearing on adopted rows;
      `dsu_meta.azimuth_deg` = planned-stick frame. They legitimately differ.
- [ ] Per-unit counts: PUD/UPSIDE totals, override counts, and PDP rows match step 1's
      expectations; category composition vs the prior drop explained (Steven's
      per-category-count concern).
- [ ] `novi_comparison` selection is `curated.intel_representative_sticks` (sql/35): 1-mi
      stick-to-stick, per-basin lateral tolerance **±25% Delaware / ±40% Midland** (§9), `low_n`
      flagged never widened; `novi_alignment = novi_to_ip_tc_to_peak`,
      `novi_rate_to_volume_days = 30`.
- [ ] Diff vs the prior governing drop: zones, counts, EURs — every delta explainable and worth a
      line in the covering note.
- [ ] Contract §4 16-box self-check walked once, top to bottom.
- [ ] File opens clean in Excel; exactly one governing workbook will exist post-send.

## 8. Covering note (draft for Michael to send)

Must contain: codename + filename; SUPERSEDES line naming the prior file (if re-drop); what
changed and why (fix, re-save, split, risking); any zone-list change called out explicitly (§11);
any NEW ledger deviation the file carries, with the required-vs-tolerated framing; open questions
if we're forcing one of the §5 undecided formats.

## 9. Ledger + memory

- New deviation → new § in `docs/blue_ox_contract_amendments_pending.md`, dated by first emission,
  exact names/units, "Loader impact" line — **same commit** as the implementing change; PR per
  oilgas flow.
- Update the blue-ox memory: drop sent (or staged), sweep result, outstanding acks.

## Known traps (each has drawn blood)

Stale-pin 409s after any narvi re-save · phantom pins from wrong-parcel saves · silent
`category_overrides` loss (pre-guard) · persisted-first rep sets carrying an old tolerance ·
mid-lateral heel on 3-vertex sticks (caught by Steven, not us) · toucan azimuth defect
(unconfident neighborhood mean) · `RES` refused at build (rename to UPSIDE) · partial percentile
triplets · Block B recomputed from the source system instead of the sheets · reserved filename
stems · assuming a merged fix reached persisted scenarios without a re-save.
