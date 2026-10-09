# BOX type curves — build plan

**Status:** plan of record, drafted 2026-10-06. Step 0 done (#85). **Step 1 built 2026-10-06, at gate 1**
(deliverable `docs/box/step1-2026-10-06/` — `FINDINGS.md` + per-bench pages + well sets; builder
`scripts/box_bench_qc.py`, `box/bench_qc.py`). Gate 1 decided 2026-10-06: D19 (pool WCA for
extents/areas, split at the curve step), D20 (WCXY → WCA_1 evidence one-way), and **option A** for
planned-survey / permit-round wells (evidence unless consensus-flagged). Consensus flags are ratified
per swap class from calibration cards (`docs/box/step1-2026-10-06/cards.html`, 142 cards over 797
cross-pool flags), never per well. **Verdicts in 2026-10-07** (`VERDICTS.md`: 84 agree / 41 reject /
17 inconclusive; class rule proposed — accept into-pool classes ≥ 0.70, reject thin-boundary classes,
A′ = planned-survey flag means TVD suspect not tag wrong, never Bone Spring → Wolfcamp). Gate 1
answered 2026-10-07 (VERDICTS §6): rule ACCEPTED and applied (`box/qc_rule.py`, `scripts/box_apply_rule.py`,
card verdicts outrank the class rule per well); hold classes exhausted (5 flags each, all carded) →
per-well verdicts; GOR tiebreak FORMALISED (`gor12`, `cons_gor_vote`, veto in the rule, card panel);
Diez TVD + McGary duplicates batched with the next vintage query. **Gate 1 CLOSED 2026-10-07.**
Final well sets = `docs/box/step1-2026-10-06/wells_final_{WCA,BS2_S}.csv` (WCA 12,306 / BS2_S 4,359
wells; `box_depth_witness` marks depth evidence). **Step 2 done; gate 2 CLOSED 2026-10-07** (deliverable `docs/box/step2-2026-10-07/` — `FINDINGS.md`,
`edge_{WCA,BS2_S}.html`; builder `scripts/box_edge_gap.py`, `box/edge_gap.py`; eng_db #94). Decided: D21 (extent =
laterals + variable buffer, r is measuring-only), D22 (BS2_S W = live front), D23 (edge metric of record + step-out
table), D24 (potash ignore-gap = BLM Secretary's Potash Area), D25 (structure grids = geology context only).
**Step 3 done 2026-10-09; gate 3 redefined by D28 (geology non-blocking).** Extents are D27 development envelopes (amended 2026-10-09: ≥ 3-lateral step-out programs, no updip limit, generalized edge): WCA 6,168 / BS2_S 3,358 sq mi (eng_db #95, #96, #104 merged). Deliverable `docs/box/step3-2026-10-07/` (FINDINGS §8–§9, review pages, `geology/` package). `sql/54` box schema **LIVE 2026-10-09** (28/28 apply checks). `sql/56` (edge_class `bridge`; authored as sql/55, renumbered after the Novi mirror took 55) **LIVE 2026-10-09**. **Generated v1 STORED as the version of record 2026-10-09** (`box.extent` extent_id 6 WCA 6,168.7 sq mi / 7 BS2_S 3,358.5 sq mi, 346 / 218 edges; identical to the committed `geology/` package within 0.005 sq mi). **Gate 3 CLOSED (D28).** **Step 4 built 2026-10-09, AT GATE 4** (branch `claude/box-step4-tc-areas`; deliverable `docs/box/step4-2026-10-09/` — `FINDINGS.md` + `areas_WCA.html`; builder `scripts/box_tc_areas.py`, `box/tc_area.py`): contiguity-constrained Ward on 1-mi hex cells, log 12-mo oil/ft of 7,553 D9 cohort wells, k by blocked CV + paired 1-SE = **34 areas** (held-out R² 0.21 vs 0.22 local-kNN ceiling; curve flat past ~14, k weakly identified); sweet spot N-central along the state line. Gate-4 asks (FINDINGS §6): k = 34 vs a coarser nested level / min-area floor; area 12 TX-vs-NM ~3× step = suspected TX allocation artifact. `sql/57` box.tc_area authored + container-validated, **NOT applied** (go-apply, then `--store --record` at the chosen k). Execution model in §10, kickoff prompt in §11.
**Owner:** Michael. **Executor:** Claude sessions, one step per session unless Michael says
otherwise. **Workflow rule:** every step ends at its gate — report what exists and how to verify
it, then stop. Do not roll into the next step on a phase-level "yes".

---

## 1. Problem and end state

Novi Intelligence forecasts are not underwritable: optimistic in topfill/underfill and in thin-PDP
areas (2025Q3 hindcast: cum-6 bias −24 % Delaware / −5 % Midland; support-inflation audit
1.22–1.34× year-1 in thin-support areas). Engineering time goes to hand-built type curves per deal.

**End state.** For every reconciled Novi PUD inside a declared bench extent, a BOX (Blue Ox) type-curve
forecast generated from PDP data, risked by development scenario, stored in oilgas next to the Novi
forecast; Steven's economics on those forecasts in `box_econ`; apps able to switch Novi ↔ BOX. Novi
forecasts become a comparison, and eventually an optional subscription. Own location placement is a
**later phase** (Novi supplies locations in the interim).

## 2. Decisions of record (do not re-litigate; change only with Michael)

| # | Decision | Why |
|---|---|---|
| D1 | **Universe = reconciled PUDs**: `remaining_pud ∪ status IS NULL ∪ conflict`, inside a declared extent. **No RES/UPSIDE.** | RES/UPSIDE "faker than fairy dust". Not-yet-reconciled NULL is treated as remaining (rule 11). |
| D2 | **Emerging benches are out of scope**: Delaware `WDFD`; Midland `MISS`, `BRNT`, `MRMC`, `WDFD`. Hand-worked in narvi + anduin per deal. Config list, basin+bench pairs, Michael-owned. | Too few wells for extents, areas, or pooled factors. Excluded PUDs display as **"not covered: emerging bench"**, never zero; aggregates report the dropped count. Their PDP wells still count as neighbors for dev-scenario classification. |
| D3 | **BS2_S is IN** (proven; edge capped W/N/E, moving south). | Michael 2026-10-01. Doubles as the edge-metric asymmetry test. |
| D4 | **Pilot = Delaware WCA_1 / WCA_2**, BS2_S as the second extent test. | Mature, data-rich, dev-scenario variety; the pilot sizes storage and calibrates every threshold below. |
| D5 | **Extents** are built from **≥ 2016 horizontal PDP laterals** (concave outline). **Pre-2016 wells are negative evidence only** — they may tighten a buffer, never extend an extent. | "No modern test in 10 years means operators had a reason." |
| D6 | **Buffer from the edge-gap metric** (Michael's): walk the outline; each run between consecutive edge-pinning wells has a gap length; buffer ∝ local gap (capped), refined by the 2×2 with edge performance (§5.3). No hand-set N/E/S/W buffers. | Asymmetric, data-derived, bench-maturity falls out as median gap. |
| D7 | **Geology reviews extents as a SHAPEFILE in NAD83 / UTM 14N, US-survey ft** (ggx cannot read gpkg). Edits persist; regeneration produces a **diff**, never an overwrite. Extent cadence is **TRIGGERED**, not quarterly. | Geologist's GGX export CRS re-verified 2026-10-06 against `curated.wells` surface locations (305 control points within 10 ft vs 109 intl-ft / 6 NAD27). No standard EPSG — write `.prj` from the exact definition; coordinates must already be projected (ggx may ignore `.prj`). |
| D8 | **Surface/access constraints (potash SPA, SWD, habitat) are OUT.** Surface Land's problem. The potash drill-island pattern is caught by geology's review; add a manual "ignore-gap" polygon only if it keeps recurring. | Michael 2026-10-01. |
| D9 | **TC areas**: contiguous regionalization inside each extent, **min cohort 10 wells**, revisited after the pilot. Response variable first pass = raw performance with vintage normalized by filter (first prod ≥ 2016-01-01, lateral 6,000–13,000 ft). | Operator/completion confounding accepted for v1; stated on every map. |
| D10 | **Relaxation ladder is fixed, ordered, and stamped on every curve**: (1) strict → (2) relax lateral → (3) relax vintage → (4) borrow neighboring area → (5) transfer from parent bench (deal-intake #59 pattern). | A 4-well-2014 curve must never look like a 40-well-modern one. One pool per bench, flags not splits (eng_db #78/#80). |
| D11 | **Risking = pooled model**: area effect local; dev-scenario factors pooled **per bench across the basin** (pilot to confirm vs per-basin-across-benches). Factors per stream; decide EUR-vs-qi application in the pilot. PUD dev scenario is **computed by us** (sql/50 rules), never Novi's tag. **Match on parent bench, not just scenario.** | Thin areas still get a factor; your placement engine can produce a tag later. SM pad C-233 / WCA-over-WCB_1 findings. |
| D12 | **Deal TCs do not override BOX.** They coexist; deal-vs-BOX gap is a resolution QC. | Deal cohorts are smaller/more refined by design. |
| D13 | **Forecasts stay technical; econ is display-only.** Steven's `box_econ` columns are a screen like Novi NPV, with provenance (run id, deck, as-of, BOX curve version). **Econ never flows back into a forecast or an extent.** Placement (later phase) is technical-only; econ is a screen applied afterward. | Re-statement of the scope rule's intent. Rewording CLAUDE.md is part of step 7. |
| D14 | **Key BOX on our own `box.location`**, not Novi `stick_id`. `source` + `source_ref` columns; quarterly crosswalk (same bench + co-extent overlap, rule 9) carries `location_id` forward. | Stick ids don't survive vintages; the same table later accepts our own locations. |
| D15 | **Fitting engine = one shared package** extracted from anduin's `app/forecasting` (peak detection, per-stream anchoring, nominal Di bounds incl. water 12/yr cap, `ramp_arps.trapezoid_eur`), consumed by anduin and the BOX batch in `engineering_db`. | Two Arps implementations will drift. Michael 2026-10-06. |
| D16 | **Steven wants monthly volumes.** Monthly rows are a *derived* table generated from params via the shared `trapezoid_eur` grid, never a second truth. Storage assessed after the pilot (BOX extents expected far tighter than Novi's). | |
| D17 | **Curves refresh quarterly** with the Novi reload (inside frozen extents); **extents re-review on trigger** (§5.4). | |
| D18 | **Acceptance = hindcast vs Novi 2025Q3** (§8). Thresholds accepted 2026-10-06. | "Novi is too optimistic" is established; "BOX is better" is not. |
| D19 | **WCA_1 and WCA_2 are POOLED as `WCA` for extents and TC areas (steps 2–4); the sub-bench split happens at the curve step (5), settled by sensitivity (fit with/without the consensus reassignment), not by well inspection.** Michael 2026-10-06, gate 1. | Step-1 QC: the two bands are ~128 ft apart locally and merge (< 100 ft) in 36 % of 1.5-mi neighbourhoods; 675 of the 1,121 WCA consensus flags are WCA_1↔WCA_2 swaps, which change nothing in an extent. |
| D20 | **Asymmetric bench evidence for WCXY.** WCXY-tagged wells COUNT as WCA_1 (hence WCA) evidence; WCA_1 wells NEVER count as WCXY evidence — a consensus flag of a WCA_1 well into the WCXY band is moot for steps 2–4 and never promotes the well into a future WCXY extent or cohort. Michael 2026-10-06, gate 1. | WCXY is a regional target concentrated on the north side of the basin; southern WCA_1 producers (e.g. Reeves Co.) must not extend or suggest a WCXY extent that far south. Step-1 QC: WCXY sits in the WCA_1 band in NM (66 % merged). |
| D21 | *(construction superseded by D27, 2026-10-09; the buffer rule survives on the outer edge)* **Extent = lateral lines + variable buffer** (k × local gap, capped, 2×2-refined). The step-2 pin radius r (½ mi) is a MEASURING radius for the edge walk only, never a standoff the buffer is added on top of. Michael 2026-10-07, gate 2 (option b). | A well-pinned, rolled edge may sit closer than ½ mi to the last producer; the buffer is the only knob setting distance past the last well. |
| D22 | **BS2_S W is a live front** (31 step-outs 1–3 mi beyond the body, median first prod 2025, 0.84× interior oil/ft; Michael confirmed they are genuine BS2_S). Step 3 buffers it as a gap side. Supersedes the plan's "capped W" expectation in step 2. Michael 2026-10-07. | Step-2 step-out table. |
| D23 | **Edge metric of record = step 2 as built**: union-of-discs outline (pin radius r = 2,640 ft, closing c = 3,960 ft, smallest c making WCA one body, one value per basin), gap = unpinned outline between consecutive pinning laterals, sides by bearing from the body centroid, **plus the step-out table** (≥ 2016 laterals beyond the body by side / distance / vintage / oil-ft) as the second half of the edge read. Michael 2026-10-07, gate 2. | The literal Delaunay hull failed (stair-step chords); a gap caps at ~2c, so a moving front shows as step-outs. |
| D24 | **Potash ignore-gap polygon = the BLM Secretary's Potash Area** (D8's recurrence clause triggered: the potash footprint opens holes/gaps in BS2_S and WCA). Inside it, gaps neither widen buffers nor count as negative evidence; it never extends an extent. Michael 2026-10-07, gate 2. | Surface constraint, not geology. |
| D25 | **Structure grids are context, not an extent driver.** Holden's regional GGX grids (~1-mi nodes) are thinnest where edges need detail (few vertical penetrations to pick tops); BS2_S's edge is not structurally governed — W edge likely depth (pressure) and water saturation (Michael). Grids ship as contour layers in the step-3 geology package only. Michael 2026-10-07. | Step-2 probe (FINDINGS §8): ~100 ft/mi homocline both sides of every edge. |
| D26 | **Legacy drilled-up holes are filled.** A hole of the drilled body ≥ 90 % covered by the ½-mi footprint of pre-2016 laterals is filled into the extent, potash-area holes included. Pre-2016 wells stay negative evidence at edges (D5) and never curve evidence (D9); the rule never extends an outer edge. Michael 2026-10-08. | No modern wells there because the ground is drilled up, not because operators avoided it (WCA 14.3-sq-mi hole: 68 legacy laterals, 100 % cover, 5 D1 PUDs). Refines D5 for enclosed ground. |
| D27 | **The extent is the bench's DEVELOPMENT envelope.** (1) Development is always in: step-out clusters of **≥ 3 laterals** (within 1 mi of each other) within 8 mi of the body are inside, whatever their performance; 1–2-well step-outs and anything beyond 8 mi are tests, out and listed (amended 2026-10-09: a single test well — e.g. Tascosa's Shake 'N Bake 2 State #204H, 6.6 mi W of BS2_S — is not development). (2) No voids: gaps between development trends narrower than **8 mi** are bridged and every interior void is filled, potash area included. (3) Evidence (2×2 buffer, live fronts, potash floor, pre-2016) governs only how far the extent reaches beyond the outermost development. No updip depth limit on either bench (BS2_S 2BS 7,000 ft tried and dropped 2026-10-09: it trimmed only ~37 sq mi of reach and fought the D22 W front; low updip performance is the TC areas' job). (3a) The edge is generalized: 2-mi simplification + corner cutting, a proportional bulge wherever that would leave a developed lateral out, corners rounded at ¾ mi. (4) Performance lives in the TC areas (step 4), never in the extent. Geology cuts a void or moves an edge only for a structural or reservoir reason. Supersedes D21's construction; subsumes D26; D25 stands (grids are context). Michael 2026-10-09. | A sedimentary bench with no structural break has no voids between development trends (BS2_S SE: two strong trends, one gap). Cutting developed wells to express performance mixes the extent with the TC areas. BS2_S producers roll over updip of ~7,000 ft on the 2BS top (6,750–7,000 ft: 0.68× interior, 39 % performing; 7,000–7,250: 0.83×, 68 %; 7,250–7,500: 1.03×, 84 %). |
| D28 | **Geology review is non-blocking.** The generated D27 extents (v1) are adopted as the version of record and BOX moves on to step 4; the shapefile package stays in `docs/box/step3-2026-10-07/geology/` for geology to review whenever. When geology returns relevant edits, they are imported (`scripts/box_extents_import.py`), stored as a new version of record, and everything downstream (TC areas, curves, PUD forecasts) is re-run on the new version. Gate 3 is redefined accordingly: v1 stored as the version of record. Michael 2026-10-09. | "These extents are more than good enough to move forward with"; progress should not halt waiting on geology. |

## 3. Scope guard (what this plan does NOT do)

- No own-location placement; no RES/UPSIDE; no emerging benches; no surface constraints.
- No economics logic anywhere; no econ-limit, no truncation; EUR = raw 50-yr integral (rule 6).
- No change to anduin's fitting behavior — extraction is a refactor, baselines and the money test
  (61,642.7 bbl/1000 ft ±0.5 %) must not move.
- No app switch before step 6 passes.

## 4. Architecture

### 4.1 Where things live

| Piece | Repo | Form |
|---|---|---|
| Shared fitting package (`boxfit` working name) | new package dir inside `permian_type_curve` (publishable), pinned into `engineering_db` requirements | pure Python, DB-free, tests ported from anduin |
| Extent builder, edge-gap metric, area clustering, cohort/curve batch, risking, hindcast | `engineering_db` (`box/` package + `scripts/box_*.py`) | batch jobs; read via 5432 session pooler like ETL |
| Warehouse objects | `engineering_db` `sql/5N_box_*.sql` + `scripts/apply_box_*.py` | `warehouse-change` skill ritual |
| Geology round-trip | `engineering_db` `scripts/box_extents_export.py` / `_import.py` | shapefile, NAD83 UTM14N US-ft |
| Econ | `box_econ` schema (LIVE, eng_db #85), Steven writes | sandbox table now; contract table in step 7 |
| App surfaces | erebor first (Highgrade + Accuracy), then anduin dossier / Blue Ox drop | read-only on 6543 |

### 4.2 Data model (schema `box`, app-owned like `narvi.*`; ETL and `refresh_all()` never touch it)

```
box.bench_scope        basin, bench, in_scope bool, reason            -- D2 list, Michael-owned
box.extent             extent_id, basin, bench, version, geom (4326), source {generated|geology_edited},
                       generated_from_run, edge_gap_stats jsonb, created_at, superseded_by
box.extent_edge        extent_id, seg_no, geom (linestring), gap_ft, buffer_ft, edge_class {pinned|gap},
                       perf_class {strong|rolled|unknown}, explanation text      -- the 2×2 per segment
box.tc_area            area_id, extent_id, area_no, geom, n_wells, cohort_stats jsonb
box.type_curve         tc_id, area_id, version, stream, relaxation_step (1..5), n_wells, anchors jsonb,
                       params jsonb (qi, Di_nom, b, Df, ramp) per stream, eur_per_kft, fit_meta jsonb
box.tc_member          tc_id, api10, dev_scenario, parent_bench, included bool, drop_reason
box.risk_factor        basin, bench, stream, dev_scenario, parent_bench, factor, n_pairs, ci_lo, ci_hi,
                       applies_to {eur|qi|both}, version
box.location           location_id (ours), source {novi_<vintage>|box_placement}, source_ref,
                       basin, bench, geom, lateral_ft, dev_scenario (ours), extent_id, area_id,
                       first_seen_vintage, last_seen_vintage, crosswalk_method
box.pud_forecast       location_id, tc_id, risk_version, stream, params jsonb (scaled), eur_bbl, eur_per_kft,
                       coverage {covered|not_covered_emerging|not_covered_outside_extent|thin}
box.pud_forecast_month (derived) location_id, stream, month_no, volume   -- regenerated from params
box.hindcast_run       run_id, cutoff_report, built_at, config jsonb
box.hindcast_score     run_id, api10, bench, area_id, horizon {6,12}, actual, box_pred, novi_pred
```
Every table: UNIQUE index (CI lint), `extensions.*` schema-qualified in any matview body, geography
expression indexes created **before** any spatial builder runs (sql/26 pattern).

### 4.3 Conventions that bind every step

- Rates `rate_calday_*`; every stream on its own peak; `peak_ramp` alignment; P10 = HIGH; nominal Di
  (state 1-yr effective alongside in every summary); EUR raw 50-yr; `formation_blueox` grouping with
  `'(unmapped)'` COALESCE; api10 well key; overlap matching never min-distance; azimuths axial.
- Row-count verification by identity, never remembered constants.
- All warehouse DDL needs an explicit "go apply" from Michael (box_econ-style). Read-only exploration
  needs no permission.

## 5. Steps and gates

Each step: *deliverable → verification → gate*. "Gate" = Michael reviews a rendered surface (map or
table), not YAML.

### Step 0 — econ landing zone ✅ DONE (eng_db #85, 2026-10-01)
`box_econ` schema + `steven` writer live; sandbox phase. Open: Steven's first table → contract table
in step 7.

### Step 1 — bench QC for the pilot benches (read-only)
Delaware WCA_1, WCA_2, BS2_S.
- Count horizontals per bench; share with `DirectionalSurveyIsPlanned = TRUE`; share whose tag
  disagrees with the gunbarrel-consensus detector (v2, sql/23 bands) or sits on a permit-round TVD.
- **State-line check:** well density and median 12-mo oil/ft per bench in 10-mi bins each side of
  the TX/NM line. A step that lines up with the border = tagging artifact, flag it.
- Decide (Michael) whether planned-survey NM wells get a depth-based bench reassignment for BOX
  purposes only (no warehouse change) or are excluded from edge/cohort evidence.
- **Deliverable:** one HTML page per bench (counts, maps, the state-line plot).
- **Gate 1:** Michael confirms the QC'd well set per bench.

### Step 2 — edge-gap prototype (read-only, ~1 session)
- Concave outline (alpha shape) of ≥ 2016 laterals per bench, laterals as lines not points; alpha per
  basin, tuned so WCA comes out one body with no false holes.
- Walk the outline; for each run between consecutive pinning laterals record gap length; attach the
  nearest edge wells' 12-mo oil/ft vs interior median (perf_class).
- **Deliverable:** maps of WCA and BS2_S outlines colored by gap length, with pre-2016 wells shown
  grey; a table of gap distribution per bench (median, p90, perimeter-miles-per-pinning-well).
- **Expected result (the test):** WCA uniformly pinned; BS2_S pinned W/N/E with long S/SE gaps. If
  either fails, the metric or alpha is wrong — do not proceed to buffers.
- **Gate 2:** Michael accepts the metric.

### Step 3 — extents with buffers + geology round-trip
- buffer_ft = k × gap_ft, capped (k and cap calibrated on WCA + BS2_S together); 2×2 refinement:
  pinned+rolled → tightest; pinned+strong → tight + **flag for geology** ("edge not explained by
  performance"); gap+strong → max; gap+rolled → moderate. Pre-2016 wells inside a gap tighten it.
- Export shapefile set per bench (NAD83 UTM14N US-ft, `.prj` written; attributes: bench, version,
  segment class, gap_ft, buffer_ft, flag text) + a one-page PNG legend. Import script reads geology's
  edited shapefile back, stores as `source = geology_edited`, computes the diff vs generated.
- Warehouse: `sql/5N_box_schema.sql` (schema, `bench_scope`, `extent`, `extent_edge`) + apply script
  with identity checks. **Explicit go-apply required.**
- **Deliverable:** shapefiles to geology; diff page after their edits.
- **Gate 3:** geology's edited extents loaded as the version of record.

### Step 4 — TC areas on WCA
- Cohort filter (D9) inside the extent; response = 12-mo oil/ft (24-mo as a second map, with its own
  n — populations differ). Contiguity-constrained regionalization with min 10 wells (max-p / SKATER
  class); report the number of areas and why.
- **Gut-check maps:** bo/ft (Novi 30-yr where available, else cum), 12-mo oil/ft, 24-mo oil/ft, each
  with n per area, expected sweet-spot-in-the-middle pattern.
- `box.tc_area` DDL + apply (go-apply).
- **Gate 4:** Michael's gut check on the area map.

### Step 5 — shared fitting package + baseline curves + risk factors
5a. **Extract `boxfit`** from anduin `app/forecasting` (`peak_detection`, `fit`, `ramp_arps`, `eur`,
`types`, `cohort` as needed). anduin imports it; **560+ tests, real-well baselines, money test all
unchanged**; ruff/mypy clean on touched files. Separate anduin PR, squash-merged **before** 5b.
5b. **Baseline curve per area per stream** via the relaxation ladder (D10); stamp step, n, anchors;
EUR/1000 ft via `trapezoid_eur`; reconcile stored vs recomputed < 0.1 %.
5c. **Dev-scenario factors** pooled per bench across the basin: per stream, per (scenario,
parent_bench) pair vs the reference scenario; normalize each area's mixed cohort to the reference;
report n_pairs and CI; selection-bias note (topfill = newer completions + better rock).
5d. `box.type_curve`, `tc_member`, `risk_factor` DDL + apply (go-apply).
- **Deliverable:** per-area curve pages (fit overlay, members, relaxation step), factor table with CIs.
- **Gate 5:** Michael reviews curves and factors; decides EUR-vs-qi application and the per-bench vs
  per-basin pooling question with the pilot numbers in hand.

### Step 6 — hindcast vs Novi 2025Q3 (acceptance)
- Rebuild steps 4–5 **using only wells online before the 2025Q3 report cutoff** (same extents).
- Holdout = the ~1,742 wells retained in the trimmed 2025Q3 slices (`intel_forecast_accuracy_vintage`
  / sql/42 by-report functions), actuals through 2026-08.
- Predict each holdout well: BOX area curve × lateral × factor(its dev scenario, computed by us);
  Novi = its 2025Q3 forecast. Score cum-6 and cum-12 oil per bench-area.
- **Deliverable:** acceptance page — per bench-area bias and P10–P90 error band, BOX vs Novi, n
  holdout wells; summary verdict against §8.
- **Gate 6:** pass/fail decision. Fail → diagnose (areas? factors? relaxation?) and re-run; no app
  work until pass.

### Step 7 — production tables + Steven's contract + rule text
- `box.location` with the quarterly crosswalk, `box.pud_forecast`, derived monthly table
  (generator script), coverage classes incl. `not_covered_emerging`.
- `box_econ` **contract table** designed from Steven's sandbox table: keyed on `location_id`, with
  `run_id`, deck/assumptions name, as-of, `box_risk_version`/`tc_version` priced. Ask Steven to also
  run his deck on Novi forecasts once (apples-to-apples forecast-difference exhibit).
- Reword the CLAUDE.md scope rule per D13; add `box.*` to the "app-owned, ETL never touches" list;
  sql/31 comments + data dictionary regen (`_CONSUMERS`).
- Quarterly-reload skill: add the BOX refresh steps (crosswalk → curves → pud_forecast → monthly).
- **Gate 7:** tables live and verified by identity (pud_forecast rows = in-scope reconciled PUDs
  inside extents, exactly).

### Step 8 — app toggle (erebor first)
- Highgrade: forecast source selector Novi | BOX; BOX EUR/ft, risk factor, coverage badge; "not
  covered" rendered explicitly with counts in aggregates; econ columns with provenance label
  (the three existing Novi caveats get BOX siblings).
- Accuracy tab: BOX vs Novi hindcast surface from `box.hindcast_score`.
- anduin dossier / Blue Ox drop: BOX regional curve overlay next to the deal TC (D12), ledger entry.
- **Gate 8:** click-through on the pilot bench.

### Later phases (not this plan)
Extend to all in-scope benches both basins; own location placement (narvi engine likely; `box.location`
columns mirror `narvi.inventory_well`); Novi subscription decision.

## 6. Thresholds and knobs (initial values; pilot recalibrates)

| Knob | Initial | Where set |
|---|---|---|
| Cohort vintage | first prod ≥ 2016-01-01 | D9 |
| Cohort lateral | 6,000–13,000 ft | D9 |
| Min area cohort | 10 wells | D9 |
| Alpha (concave hull) | per basin, tuned on WCA — Delaware: r = 2,640 ft pin radius, c = 3,960 ft closing (D23, accepted gate 2) | step 2 |
| buffer = k × gap, cap | k, cap from WCA+BS2_S — **proposed** k = 0.75, cap = 7,920 ft, pinned floor 880 / 1,320 / 1,760 ft (rolled / unknown / strong), step-3 backtest; Michael's call at gate 3 | step 3 |
| Edge perf_class | edge wells' 12-mo oil/ft vs interior median: ≥ 0.85 strong, < 0.70 rolled, else unknown | step 2 |
| Extent trigger | ≥ N new ≥2016 wells within X mi of / outside the extent since last review (N, X set in step 3) | D17 |
| Dev-scenario rules | sql/50 (660 ft offset gate, 1,000 ft band, shielding) | D11 |
| Di bounds | oil/gas nominal [0.5, 4.0]/yr, water cap 12/yr, b ∈ [0.9, 1.2] | rule 1 |

## 7. Verification standard per deliverable

- **Maps/pages:** rendered, with n per unit and filters stated; never a YAML/CSV as the review surface.
- **Warehouse:** apply script with identity assertions + EXPLAIN index names; sql/26 after any
  geography object; CI `etl` check green; dictionary regenerated.
- **Shared package:** anduin suite green and baselines unchanged; the BOX batch's EUR for a known
  anduin curve equals anduin's to < 0.1 %.
- **Forecast numbers in summaries:** units, grain (wells / well-months / sticks), nominal + effective
  Di, mean-vs-P50 labeled.

## 8. Acceptance criteria (accepted 2026-10-06)

On the 2025Q3 holdout, per bench-area with ≥ 10 holdout wells, for cum-6 and cum-12 oil:
1. **Bias:** BOX mean % error within **±10 %**, and |BOX bias| < |Novi bias|.
2. **Spread:** BOX P10–P90 error band **no wider** than Novi's.
3. **Coverage:** 1 and 2 hold on a **majority** of qualifying bench-areas. Bench-areas with < 10
   holdout wells are reported but count neither way.
Reference: Novi 2025Q3 cum-6 bias −24 % Delaware / −5 % Midland.

## 9. Open items (resolve in the step named)

- Win on majority — does "majority" weight by holdout wells or by area count? (step 6, before scoring)
- EUR-vs-qi factor application; per-bench vs per-basin pooling (step 5 gate).
- ~~NM planned-survey wells: reassign by depth or exclude~~ → **option A adopted 2026-10-06**:
  planned-survey / permit-round wells are evidence unless consensus-flagged, every survey class
  (`docs/box/step1-2026-10-06/FINDINGS.md` §4/§7). BOX-only; no warehouse change.
- ~~Consensus-flag ratification~~ → DONE 2026-10-07: class rule of record in `box/qc_rule.py` (class
  gate ≥ 0.70 from card precision, sql/23 second vote, GOR veto, A′ for planned surveys, never Bone
  Spring → Wolfcamp; per-card verdicts outrank the rule). Re-calibrate only when the detector or the
  tag chain changes (quarterly reload). Edge-pinning review wells still get individual eyes at gate 2.
- Vendor data defects to batch with the next Novi vintage query: Diez Unit 10 2H (4238937383) Novi TVD
  10,896 vs Enverus 10,430 / Michael 10,383; McGary-Tudor West 4H / East 5H duplicate api10s
  (4238939884/4238941440, 4238939885/4238941441) both producing.
- anduin follow-up (not BOX): old short laterals (e.g. 3001534505, 4247535273) are not in anduin's
  synced universe; api10 search for a synced well (3002551417) showed nothing on the map.
- ~~WCA_1 vs WCA_2 handling; WCXY membership~~ → D19 / D20 (2026-10-06).
- Steven's table shape / econ case dimension (step 7, after his first upload).
- Geologist's one-line CRS confirmation (any time; D7 stands until contradicted).
- Extent trigger constants N, X (step 3).

## 10. Execution model (how the work is chunked across sessions)

**One session per step, split further where a step is large.** Expect ~14–16 sessions, not 8:

| Step | Sessions | Notes |
|---|---|---|
| 1, 2, 4, 6 | 1 each | read-only or single-deliverable |
| 3 | 2 | build + export; then import geology's edits (their turnaround in between) |
| 5 | 3 | 5a extraction (anduin PR, **plan mode first** — approve the module list before edits); 5b curves; 5c factors |
| 7 | 2 | warehouse tables + crosswalk; then Steven's contract + CLAUDE.md / skill / dictionary text |
| 8 | 1 per surface | erebor Highgrade; erebor Accuracy; anduin dossier / drop |

**Why fresh sessions:** context summarization keeps a session alive but loses exact numbers and the
reasons behind small choices. A new session that reads this file, the memory note, and the previous
step's committed deliverable starts from the record, not a compressed memory of it. Gates are the
natural boundaries — the review decision is the moment to end the session.

**End-of-session ritual (every session, including an unfinished one):**
1. Deliverable on disk and committed — the rendered page, the script that produced it, any SQL.
   Review pages go in the repo (`runs/` or `docs/`), never only in chat.
2. PR opened; Michael merges after review.
3. Memory note `box-type-curves-idea` updated with the gate outcome and the one or two numbers that
   matter.
4. **The Status line at the top of this file updated** in the same PR: "step N done, gate N passed
   <date>; next N+1" — or, if unfinished, "step N in progress: done X, Y; not Z; branch <name>".
   Resolved §9 items move into §2 or get struck. Never update this file in a separate commit on
   main (orphaned-push trap).

**Within a session:** start with the §11 prompt only (the session reads this file; don't paste it).
Heavy exploration (warehouse surveys, module inventories) goes to a subagent so raw dumps don't fill
the main context. If context runs long before the step is done, Michael says **"checkpoint"**: commit,
update the Status line, summarize, start fresh.

## 11. Session kickoff prompt (copy into a new session)

> Read `docs/box_type_curves_plan.md` in engineering_db and the memory note `box-type-curves-idea`.
> We are on **step N**. Do only step N: build the deliverable, verify it per §7, report what exists
> and how to check it, then stop at gate N. Read-only warehouse access is fine; any DDL/apply needs
> my explicit "go apply". Decisions in §2 are settled — flag conflicts, don't resolve them silently.
