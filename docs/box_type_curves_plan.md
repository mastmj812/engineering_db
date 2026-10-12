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
**Step 3 done 2026-10-09; gate 3 redefined by D28 (geology non-blocking).** Extents are D27 development envelopes (amended 2026-10-09: ≥ 3-lateral step-out programs, no updip limit, generalized edge): WCA 6,168 / BS2_S 3,358 sq mi (eng_db #95, #96, #104 merged). Deliverable `docs/box/step3-2026-10-07/` (FINDINGS §8–§9, review pages, `geology/` package). `sql/54` box schema **LIVE 2026-10-09** (28/28 apply checks). `sql/56` (edge_class `bridge`; authored as sql/55, renumbered after the Novi mirror took 55) **LIVE 2026-10-09**. **Generated v1 STORED as the version of record 2026-10-09** (`box.extent` extent_id 6 WCA 6,168.7 sq mi / 7 BS2_S 3,358.5 sq mi, 346 / 218 edges; identical to the committed `geology/` package within 0.005 sq mi). **Gate 3 CLOSED (D28).** **Step 4 done; gate 4 CLOSED 2026-10-09** (eng_db #110; deliverable `docs/box/step4-2026-10-09/`): **35 WCA TC areas kept** (D29), El Campeon / Los Vaqueros excluded via `docs/box/exclusions.csv` (D29), **gas via GOR ratio mode at a local GOR level** (D30), **gas added to §8 acceptance** (D31). `sql/57` box.tc_area **LIVE 2026-10-09** (15/15 apply checks live); **35 areas STORED as the version of record** (box.tc_area v1 on extent_id 6: 35 rows, n_wells 7,527, tile the extent — geodesic ratio 0.99999997, no overlap — identical to the reviewed deliverable); dictionary regenerated. **Gate 4 CLOSED.** **Step 5 in progress (2026-10-10): 5a built** — module list approved in plan mode; `boxfit` extracted to anduin `backend/packages/boxfit` (distribution `blueox-boxfit`; import `boxfit`), anduin consumes it through module aliases, plus pure splits `boxfit.well.fit_well_streams` (per-well pipeline) and `boxfit.tc.align` (peak_ramp anchors); anduin suite 624 passed, baselines + money test unchanged without reseed, 63-entry before/after snapshot bit-identical — anduin #93 + eng_db #111 MERGED (b7a0519). **5b built 2026-10-10, at gate 5b** (branch `claude/box-step5b-curves`; deliverable `docs/box/step5b-2026-10-10/` — `FINDINGS.md`, `curves_WCA.html`): `blueox-boxfit` pinned by git URL @ b7a0519 in `requirements-dealintake.txt`; 35 area curves per stream, all at ladder rung 1; curve of record = cohort MEAN (pending gate-5 confirm; 1.065× the P50 EUR, median); gas = ratio mode + D30 level shift (held-out GOR24 R² 0.81); BOX = anduin to ~1e-10 on clean saved curves; read-only, nothing stored. **Gate 5b answered 2026-10-11:** D32 (mean = curve of record), D33 (WCA pooled, no sub-bench split), D34 (bound-pinned fits kept for now). **Follow-up decided 2026-10-11:** D35 (no GOR split / no GOR term on oil), D36 (calendar factor F(k) for step 6; never stacked with Steven's downtime factor). **D37 2026-10-11:** ladder rung 3 retired (D26 stands). **D38 2026-10-11:** TC fits use each stream's own Di cap (anduin #94; boxfit re-pinned @ d3fabcc; 5b re-run at the 2026-07-01 cutoff, only water moved). **D39 2026-10-12:** BOX monthly volumes are exact per-month integrals (rule 6 = Σ months vs stored, passes 0.1 % on every curve). **D40 2026-10-12:** TC fits skip the per-well downtime filter (anduin #96; boxfit re-pinned @ 3380317; 5b re-run at the 2026-07-01 cutoff). **All 5b items closed.** **5c built 2026-10-11, at gate 5c** (branch `claude/box-step5c-dev-factors`; deliverable `docs/box/step5c-2026-10-11/` — `FINDINGS.md`, `factors.html`; `box/dev_factor.py`, `scripts/box_dev_factors.py`): factors vs codev_stack (location + vintage FE, 3-mi block bootstrap), WCA from the 5b record + BS2_S (1,865 wells) as the pooling test; sql/50 recomputed from bench_context, 0 mismatches on 9,391 wells; lateral infill (same-bench parent) is the dominant term (oil cum-12 0.935 WCA / 0.909 BS2_S, level shift), other-bench topfill/underfill 0.92–0.94 class level, standalone 1.03–1.06; no oil class differs between benches; area normalisation ×0.946–1.025. Gate-5c asks in FINDINGS §7 (infill in risking, same-pool parents vs D33, EUR-vs-qi, unparented PUD = reference, per-bench vs per-basin ladder, gas GOR factor, estimator). Read-only, nothing stored. **Re-run 2026-10-11 on the D37–D40 5b record (boxfit @ 3380317): every factor bit-identical; only the normalisation table's area EURs move (≤ 1.5 %), multipliers unchanged** (FINDINGS §0). **Gate 5c answered 2026-10-11** (Michael accepted every recommendation): D41 infill term, D42 same-pool parents = infill, D43 cum-12 uniform scale, D44 unparented PUD = reference, D45 factor ladder, D46 gas GOR factor, D47 PPML estimator. **5d built 2026-10-12, at gate 5d** (branch `claude/box-step5d-record`; deliverable `docs/box/step5d-2026-10-12/` — `FINDINGS.md`, `record.html`; `sql/58_box_type_curve.sql` + `scripts/apply_box_type_curve.py`, `box/tc_record*.py`, `scripts/box_tc_record.py`): record rebuilt from the committed 5b/5c deliverables and checked by identity (105 curves = 5b rows exactly; 5c frame reproduces factors.csv; live dev_scenario 0 drift); factors of record under D42 + D45 + D47 (WCA infill oil 0.923, BS2_S 0.905; oil ref_mult median ×1.007); **Gate 5d CLOSED 2026-10-12:** sql/58 **LIVE** (28/28), record **STORED** as v1 of record (box.type_curve 105 / tc_member 22,581 / risk_factor 108, = the reviewed deliverable within 5e-15), dictionary regenerated. **Step 5 complete.** **Step 6 built 2026-10-12, at gate 6** (branch `claude/box-step6-hindcast`; deliverable `docs/box/step6-2026-10-12/` — `FINDINGS.md`, `acceptance.html`; `box/hindcast*.py`, `scripts/box_hindcast.py`): D48 (area-count majority + bench-pooled test) and D49 (gas = oil thresholds, oil AND gas) set before scoring; steps 4–5 rebuilt from wells first-producing before the 2025Q3 cliff (2024-12-01), production through 2025-06 (k = 15 areas at the cutoff); **verdict FAIL** (oil FAIL, gas FAIL) — Novi-matched bench: oil cum-6 BOX −9.4 % vs Novi −13.7 % but band 0.75 vs 0.67, oil cum-12 −14.6 % vs −12.2 %, gas cum-6 PASS, gas cum-12 −10.6 %; lead diagnosis = linear per-ft lateral scaling (> 13,500-ft laterals −24 %, < 8,000 ft +9 %). Read-only, nothing stored. **Fail-branch follow-up (Michael 2026-10-12):** rolling-origin backtest (cutoffs Dec 2021–2024, next-year wells vs actuals, Novi-agnostic; `docs/box/step6-2026-10-12/backtest/`): BOX oil within ±10 % at cum-6 / cum-12 in every fold, cum-24 −9…−10 %, miss grows with months on production (shape drift); Cui & Cross lateral efficiency flattens the length gradient (≥ 13.5k −10.7 → −1.2 %); the density term as specified over-corrects (not recommended). Gate-6 asks in FINDINGS §5. Execution model in §10, kickoff prompt in §11.
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
| D10 | **Relaxation ladder is fixed, ordered, and stamped on every curve**: (1) strict → (2) relax lateral → ~~(3) relax vintage~~ *(retired by D37)* → (4) borrow neighboring area → (5) transfer from parent bench (deal-intake #59 pattern). | A 4-well-2014 curve must never look like a 40-well-modern one. One pool per bench, flags not splits (eng_db #78/#80). |
| D11 | **Risking = pooled model**: area effect local; dev-scenario factors pooled **per bench across the basin** (pilot to confirm vs per-basin-across-benches). Factors per stream; decide EUR-vs-qi application in the pilot. PUD dev scenario is **computed by us** (sql/50 rules), never Novi's tag. **Match on parent bench, not just scenario.** | Thin areas still get a factor; your placement engine can produce a tag later. SM pad C-233 / WCA-over-WCB_1 findings. |
| D12 | **Deal TCs do not override BOX.** They coexist; deal-vs-BOX gap is a resolution QC. | Deal cohorts are smaller/more refined by design. |
| D13 | **Forecasts stay technical; econ is display-only.** Steven's `box_econ` columns are a screen like Novi NPV, with provenance (run id, deck, as-of, BOX curve version). **Econ never flows back into a forecast or an extent.** Placement (later phase) is technical-only; econ is a screen applied afterward. | Re-statement of the scope rule's intent. Rewording CLAUDE.md is part of step 7. |
| D14 | **Key BOX on our own `box.location`**, not Novi `stick_id`. `source` + `source_ref` columns; quarterly crosswalk (same bench + co-extent overlap, rule 9) carries `location_id` forward. | Stick ids don't survive vintages; the same table later accepts our own locations. |
| D15 | **Fitting engine = one shared package** extracted from anduin's `app/forecasting` (peak detection, per-stream anchoring, nominal Di bounds incl. water 12/yr cap, `ramp_arps.trapezoid_eur`), consumed by anduin and the BOX batch in `engineering_db`. | Two Arps implementations will drift. Michael 2026-10-06. |
| D16 | **Steven wants monthly volumes.** Monthly rows are a *derived* table generated from params ~~via the shared `trapezoid_eur` grid~~ as exact per-month integrals of the fit (D39), never a second truth. Storage assessed after the pilot (BOX extents expected far tighter than Novi's). | |
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

| D29 | **TC areas of record = the step-4 build at k = 35** (contiguity-constrained Ward on 1-mi hex cells, log 12-mo oil/ft, D9 floor 10, k by 5-fold CV on 3-mi blocks + paired 1-SE; `box/tc_area.py`). The pad-scale / single-operator areas stay (D9 confounding accepted). **BOX well exclusions** live in `docs/box/exclusions.csv` (api10, reason, decided_by, date), applied at load in every step; first entry = El Campeon / Los Vaqueros (Novi allocation defect, 46 wells). Michael 2026-10-09, gate 4. | Held-out R² 0.21 vs 0.22 local ceiling; the curve is flat past ~14 so the rule's pick is kept rather than re-tuned. Exclusions are a record, not a per-step filter. |
| D30 | **Gas is forecast via GOR, not an independent gas Arps.** The TC areas stay oil-built (GOR does not move them). Per area, the gas stream is the ratio mode of record (anduin `forecasting/ratio.py`: ln GOR = α + β·Np, fitted vs cumulative oil on the area's per-1,000-ft mean series, constant-ratio fallback) applied to the area's oil curve; the **level** comes from the PUD's own neighbourhood (local GOR, §6) by shifting α, the area supplies the shape β. Michael 2026-10-09, gate 4. | GOR is an E→W maturity trend crossing the oil areas: oil-built areas explain ~46 % of held-out log-GOR variance vs 77 % for a local 15-well median; 16 of 35 areas mix GOR regimes (FINDINGS step 4 §6e). Reuses the 2026-08-17 ratio-mode decision; no second gas method. |
| D31 | **Gas is in the acceptance test (§8).** Step 6 scores gas cum-6 / cum-12 next to oil, against Novi 2025Q3 gas (sql/43 `pct_err_gas`). Michael 2026-10-09, gate 4. | A gas miss would otherwise pass an oil-only test silently, and gas + NGL are revenue on Steven's side. |
| D32 | **TC curve of record = the cohort MEAN** per 1,000 ft (fit to the mean of the members' peak_ramp-aligned forecasts), labelled mean, never P50; the P50 fit is kept alongside as a diagnostic. Michael 2026-10-11, gate 5b. | Step 6 scores mean per-well error (sql/43); only the mean curve predicts the cohort mean cum without a skew bias. Mean EUR = 1.065× P50 (median of 35 WCA areas). |
| D33 | **WCA_1 and WCA_2 stay POOLED at the curve step** — one WCA curve per area (closes D19's split question). Michael 2026-10-11, gate 5b. | WCA_2 ~4 % below WCA_1 within area (well FE −3.7 % tag / −4.1 % consensus), inside area-to-area noise; a split would push 9 areas' sub-bench curves onto relaxed rungs. |
| D34 | **Per-well fits pinned at a parameter bound stay in the TC panel** (for now). Michael 2026-10-11, gate 5b. | 37 % of WCA cohort oil fits sit at Di = 4.0/yr; dropping them moves the pool curve +2.7 % EUR. Revisit if the step-6 hindcast points at them. |
| D35 | **No GOR split and no GOR term on oil.** TC areas and oil curves stay GOR-blind; gas is handled only through D30's local GOR level. Michael 2026-10-11 (gate-5b follow-up). | The within-area "GOR effect on oil" was mechanical (own GOR = gas / oil). Against the neighbours' GOR the oil slope is −0.012 ± 0.011 with or without controls, and it adds nothing to held-out R² (0.441 → 0.441); gas scales 1:1 (step5b FINDINGS §9). |
| D36 | **Calendar factor F(k).** Curves of record stay as fitted (uptime-free, the anduin per-well pipeline). Calendar volumes = curve × F(k), F(k) = Σ actual / Σ curve cum at month k, pooled per bench, fitted only on wells available at the run's cutoff and stamped with it (version, cutoff, n). Step 6 scores BOX predictions WITH F(k). **F(k) and Steven's own downtime factor are alternatives, never both:** if BOX volumes carry F(k), Steven drops his factor. Which one a delivery carries is stated explicitly on it (step 7 contract + ledger). Michael 2026-10-11. | Cum-12 actual / forecast = 0.93: partial first month (~3 pts), year-1 decline steeper than the Di/b bounds (~3), downtime (~1–3). Stable by vintage (0.92–0.935) and area (P10–P90 0.89–0.95); a factor fitted on ≤ 2022 wells leaves +0.5 % at cum-12 on 2023–24 wells. Changing the fit itself is off the table (bounds rule; would move anduin). |
| D37 | **Ladder rung 3 (relax vintage) is retired; D26 stands — pre-2016 wells are never curve evidence.** Ladder = (1) strict → (2) relax lateral → (4) borrow neighbouring areas → (5) parent bench; rung numbers stay stable (3 is never emitted, and code refuses a pool stamped 3). A thin area borrows modern neighbours, not old wells. Michael 2026-10-11. | Rung 3 adds almost nothing where a ladder climbs: the thinnest WCA areas (4, 2, 18, 28, 29) hold 0 pre-2016 wells (area 1: 2). Pre-2016 wells aren't per-ft comparable: within area, 12-mo oil/kft ≤ 2011 = 0.73×, 2012–13 = 0.83× modern, and 2014–15's 0.99× rides on ~4,500-ft laterals (short laterals read high per ft). Fired once in 5b (area 23 WCA_1 sub-bench), moot under D33. |
| D38 | **Type-curve fits bound each stream by its OWN nominal Di cap** (rule 1: oil/gas 4.0/yr, water 12/yr). Cap only: the type-curve fitter's frame, absolute downtime floor and qi/b bounds stay stream-independent, so oil and gas curves are unchanged. Lives in the shared engine (`fit_p50_series(stream=…)`, `ForecastConfig.di_nominal_hi`; anduin #94, merge d3fabcc) — anduin and BOX both use it; engineering_db pins `blueox-boxfit` @ d3fabcc. Michael 2026-10-11. | `fit_p50_series` hard-coded the oil stream, so water TC curves capped at 4.0/yr: 5 of 35 WCA area water curves pinned (area 1 fit R² 0.71). Under water's cap none pin, area 1 R² 1.00; water EUR median 0.0 % (area 8 +4.9 %). The full water stream was rejected because it also imports the per-well absolute floor onto a per-1,000-ft series (see §9). |
| D39 | **BOX monthly volumes are exact per-month integrals of the fit**: month k = Cum(k/12) − Cum((k−1)/12) from boxfit's closed form (`model_cum_at_t`); ratio-mode gas = the ratio at the month's mid-point Np × that exact oil month. Every BOX monthly number uses it (Steven's D16 table, cum-k, step-6 predictions, F(k)), so the monthly rows sum to the stored EUR and rule 6 is checked as Σ months vs stored at 0.1 %. Amends D16 ("via the trapezoid_eur grid"). anduin's displays / exports keep the trapezoid; BOX is not obliged to match them to the last 0.5 %. Michael 2026-10-12. | The stored EUR is the true integral of the fitted model (matches a 0.01-month numerical integral ≤ 0.03 % on all 144 oil / water fits). The 600-month trapezoid overstates a convex curve, all of it in months 2–12: EUR +0.09 % oil median (worst 0.17 %), +0.47 % worst water (area 1, Di 8.3/yr); cum-12 +0.31 % oil median, up to +1.3 % steep water. |
| D40 | **Type-curve fits do not run the per-well downtime filter.** A per-1,000-ft cohort-mean series has no downtime; `fit_p50_series` fits every post-peak month (`ForecastConfig.filter_downtime = False`; per-well fits keep the filter, default True). Shared engine: anduin #96, merge 3380317; engineering_db pins `blueox-boxfit` @ 3380317. Michael 2026-10-12. | The per-well filter's absolute floor (oil 5 bopd) and its 1.0-rate-unit clip read as 5 / 1 per kft on a TC series, so oil TC fits saw ~91 of ~600 post-peak months (mean < 5 bopd/kft by ~yr 8) and extrapolated the rest, running up to +1.44 % above the cohort-mean 50-yr cum they summarise. With the filter off the curve reproduces that cum to ≤ 0.21 %; oil TC EUR −0.36 % median (−1.47 % worst), gas / water ± 0.3 %; anduin money test unchanged (60,959.3). |
| D41 | **Lateral infill is a BOX risking term.** A same-bench parent (sql/50 `has_same_bench_parent`: an older same-bench well inside the co-extent rule) carries its own multiplicative factor next to the (class, parent bench) pair factor; factors combine (pair × infill). Michael 2026-10-11, gate 5c. | The largest, best-determined effect: oil cum-12 0.935 [0.92–0.95] WCA / 0.909 [0.88–0.94] BS2_S on 21 % / 27 % of wells, a level shift (EUR / cum-12 1.01). sql/50 keeps it as a flag, not a class (step5c FINDINGS §6a). |
| D42 | **Same-pool vertical parents count as lateral infill** (BOX pooled-bench view): a WCA well whose sql/50 vertical parent is WCA_1 / WCA_2 / WCXY is an infill well on the reference class, not a topfill / underfill pair. Pools: WCA = {WCA_1, WCA_2, WCXY}; BS2_S = {BS2_S}. Follows D33. Michael 2026-10-11, gate 5c. | 172 of 503 WCA topfill / underfill wells had a same-pool parent; a factor keyed on WCA_1-vs-WCA_2 tags inherits the tag noise D19 / D33 pooled away. Pooled-view WCA infill 0.929 [0.91–0.95], n 1,661. |
| D43 | **Factors apply as a uniform scale of the reference curve by the cum-12 factor** (qi and EUR scale together; nominal Di and b unchanged). Michael 2026-10-11, gate 5c (plan's EUR-vs-qi question). | Observed rather than extrapolated (37 % of per-well fits pin at Di 4.0, D34), and what step 6 scores; for the classes that carry the weight the EUR factor agrees within 1–3 % (shape table, step5c FINDINGS §5c). |
| D44 | **An unparented PUD gets the reference factor (1.00), not `standalone`.** A PUD classed against PDP alone can never be `codev_stack` (its co-development is with other PUDs); `standalone` (1.03–1.06 cum-12) is used only for scoring actual wells (step 6). Michael 2026-10-11, gate 5c. | A pad-developed PUD is codev; the standalone uplift would be optimistic (step5c FINDINGS §6c). Step 7 implements the PUD classification. |
| D45 | **Factor ladder, stamped per factor:** (1) the bench's (class, parent bench) pair when it has ≥ 30 subject wells → (2) the class within the bench → (3) the class pooled across benches (per basin). Settles the per-bench vs per-basin question: per bench where data allow, basin-pooled class as the fallback. Michael 2026-10-11, gate 5c. | No oil class differs between WCA and BS2_S (every BS2_S / WCA ratio CI spans 1), but the parent bench does (BS2_S topfill \| BS3_C 0.69 vs \| BS3_S 1.09). Sandwich (16 wells across both benches) lands on rung 3. |
| D46 | **Gas carries its own GOR-level factor through the ratio:** α_PUD = α_local + ln f_GOR(class), applied on top of oil's factor (D30 shape unchanged). Factors from 12-mo GOR relative to the D30 local level; through D45's ladder. Michael 2026-10-11, gate 5c (closes the §9 gas-factor item). | Children run higher GOR than the local level: infill 1.024 [1.01–1.04] WCA / 1.063 [1.04–1.09] BS2_S; other classes ≈ 1. Inherit-only would under-predict infill gas 2.5–6 %. |
| D47 | **Factor estimator of record = Poisson PML** (ratio of arithmetic means, consistent with the D32 mean curve); location FE (TC area, or 5-mi block where a bench has no areas) + first-prod-year FE; reference = `codev_stack` with no same-bench parent; 90 % cluster-bootstrap CI over 3-mi blocks. Water carries its own factors (independent Arps). Michael 2026-10-11, gate 5c. | Agrees with log-OLS within 1 % on the terms that carry the weight (infill, standalone); ≤ 3 % on most pairs (step5c FINDINGS §5b). |
| D48 | **§8 coverage reads by area COUNT plus a bench-pooled test.** Per stream × horizon: (a) the area test — a strict majority of the TC areas with ≥ 10 Novi-matched holdout wells pass §8.1 + §8.2 (by number of areas, not wells; none qualifying = inconclusive); (b) the bench test — all Novi-matched holdout wells of the bench pooled, same §8.1 + §8.2. BOX passes only if both pass. Thin areas are reported and count neither way. Michael 2026-10-12, before step-6 scoring. | The 2025Q3 holdout is thin: 257 Novi-matched WCA wells, of which 174 have a cum-6 and 56 a cum-12; only 2 of 35 areas reach 10 wells at either horizon (cum-6: area 10 = 82, area 6 = 41). An area-count majority alone would rest on two areas; the bench pool uses every matched well. |
| D49 | **Gas acceptance = oil's thresholds; BOX passes only if oil AND gas pass.** Gas cum-6 / cum-12 use the same ±10 % bias, \|BOX\| < \|Novi\|, no-wider-band and D48 coverage rules (closes the §9 / D31 assumed form). Michael 2026-10-12, before step-6 scoring. | Gas + NGL are revenue on Steven's side; a gas miss must not pass on oil alone (D31). |

## 3. Scope guard (what this plan does NOT do)

- No own-location placement; no RES/UPSIDE; no emerging benches; no surface constraints.
- No economics logic anywhere; no econ-limit, no truncation; EUR = raw 50-yr integral (rule 6).
- No change to anduin's fitting behavior — extraction is a refactor, baselines and the money test
  (60,959.3 bbl/1000 ft ±0.5 % — re-pinned 2026-09-22 in anduin `tests/test_money_p50_eur.py`; the
  61,642.7 figure this plan was drafted with is retired) must not move.
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
                       params jsonb (qi, Di_nom, b, Df, ramp) per stream — gas: ratio-mode params
                       (mode, alpha, beta, fallback) vs cum oil, D30 — eur_per_kft, fit_meta jsonb
box.tc_member          tc_id, api10, dev_scenario, parent_bench, included bool, drop_reason
box.risk_factor        basin, bench, stream, dev_scenario, parent_bench, factor, n_pairs, ci_lo, ci_hi,
                       applies_to {eur|qi|both}, version
box.location           location_id (ours), source {novi_<vintage>|box_placement}, source_ref,
                       basin, bench, geom, lateral_ft, dev_scenario (ours), extent_id, area_id,
                       first_seen_vintage, last_seen_vintage, crosswalk_method
box.pud_forecast       location_id, tc_id, risk_version, stream, params jsonb (scaled), eur_bbl, eur_per_kft,
                       gor_level (local 12-mo GOR behind the gas alpha shift, D30),
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
`types`, `cohort` as needed, **plus `ratio` and the TC-level `type_curves/ratio_mode` builder** — D30). anduin imports it; **560+ tests, real-well baselines, money test all
unchanged**; ruff/mypy clean on touched files. Separate anduin PR, squash-merged **before** 5b.
5b. **Baseline curve per area per stream** via the relaxation ladder (D10); stamp step, n, anchors;
EUR/1000 ft via `trapezoid_eur`; reconcile stored vs recomputed < 0.1 %. **Gas = ratio mode on the oil
curve (D30)**; the PUD's local GOR level shifts α (Np rescaled per-1,000 ft → PUD lateral). Test whether
oil b / nominal Di shift with GOR within an area (if they do, that is the case for a GOR split — report,
don't act). Water stays an independent Arps fit unless the pilot says otherwise.
5c. **Dev-scenario factors** pooled per bench across the basin: per stream (gas: decide whether it
carries its own factor or inherits oil's through the ratio — §9), per (scenario,
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
  gas = ratio mode at the well's local GOR level built from pre-cutoff wells only (D30);
  Novi = its 2025Q3 forecast (sql/43 carries oil and gas). Score cum-6 and cum-12 **oil and gas** per
  bench-area (D31).
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
| TC areas | 1-mi hex cells, field kNN 15, D9 floor 10, k by 5-fold CV on 3-mi blocks + paired 1-SE → 35 on WCA | D29, step 4 |
| Local GOR level (gas) | median 12-mo GOR of the 15 nearest D9 cohort wells (77 % held-out R² on WCA); pilot may refine | D30, step 5 |

## 7. Verification standard per deliverable

- **Maps/pages:** rendered, with n per unit and filters stated; never a YAML/CSV as the review surface.
- **Warehouse:** apply script with identity assertions + EXPLAIN index names; sql/26 after any
  geography object; CI `etl` check green; dictionary regenerated.
- **Shared package:** anduin suite green and baselines unchanged; the BOX batch's EUR for a known
  anduin curve equals anduin's to < 0.1 %.
- **Forecast numbers in summaries:** units, grain (wells / well-months / sticks), nominal + effective
  Di, mean-vs-P50 labeled.

## 8. Acceptance criteria (accepted 2026-10-06)

On the 2025Q3 holdout, per bench-area with ≥ 10 holdout wells, for cum-6 and cum-12 **oil and gas**
(gas added 2026-10-09, D31):
1. **Bias:** BOX mean % error within **±10 %**, and |BOX bias| < |Novi bias|.
2. **Spread:** BOX P10–P90 error band **no wider** than Novi's.
3. **Coverage:** 1 and 2 hold on a **majority** of qualifying bench-areas. Bench-areas with < 10
   holdout wells are reported but count neither way.
Reference: Novi 2025Q3 cum-6 oil bias −24 % Delaware / −5 % Midland (gas reference from sql/43 at step 6).
Oil and gas are judged separately: BOX passes only if both pass (D49, 2026-10-12). "Majority" is by area
count, and a bench-pooled test over every matched holdout well must pass as well (D48, 2026-10-12).

## 9. Open items (resolve in the step named)

- ~~Win on majority — does "majority" weight by holdout wells or by area count?~~ → **D48 (area count + bench-pooled test), 2026-10-12.**
- ~~EUR-vs-qi factor application; per-bench vs per-basin pooling~~ → **D43 (cum-12 uniform scale) / D45 (ladder), 2026-10-11.**
- ~~Gas acceptance form (D31)~~ → **D49 (same thresholds as oil; pass = oil AND gas), 2026-10-12.**
- ~~Gas dev-scenario factor: own vs inherit~~ → **D46 (own GOR-level factor through α), 2026-10-11.**
- ~~TC curve-of-record statistic~~ → **D32 (mean), 2026-10-11.**
- ~~WCA_1 vs WCA_2 split~~ → **D33 (pooled), 2026-10-11.** ~~Within-area GOR effect on oil
  level~~ → **D35 (closed, mechanical artifact), 2026-10-11.**
- (5b, before step 6) Early-time cum: record curves run ~+10 % over calendar actuals at 12 mo (per-well
  fits trace producing curves); ~~step-6 treatment~~ → **D36 (calendar factor F(k)), 2026-10-11**; open for step 7: whether delivered monthly volumes carry F(k) (then Steven drops his downtime factor) — stated on the delivery either way. ~~At-bound fits keep vs drop~~ → D34 (keep
  for now). ~~Rule-6 reconcile tolerance for steep TC fits~~ → **D39 (exact monthly volumes), 2026-10-12.** ~~TC-level water fit on the oil Di
  bound~~ → **D38 (own cap per stream), 2026-10-11.** ~~NEW (2026-10-11, before
  step 7): the type-curve fitter applies the PER-WELL absolute downtime floor (oil 5 bopd / gas 30 mcfd /
  water 10 bwpd) to per-1,000-ft series — tail months under the floor drop out of the TC fit (oil
  ~349 of 600 months fitted; a gas floor of 30 would leave ~67). Decide whether TC fits want any
  absolute floor.~~ → **D40 (no downtime filter on TC fits), 2026-10-12.** ~~D10 rung 3 vs D26~~ → **D37 (rung 3 retired), 2026-10-11.**
- **(step 6 fail branch, 2026-10-12, Michael)** Rolling-origin backtest vs actuals (Novi-agnostic; cutoffs Dec 2021–2024,
  next-year wells, cum-6/12/24) and a development-density term (co-extent neighbours within ±500 ft TVD + same-bench
  spacing) — `docs/box/step6-2026-10-12/backtest/`. Lateral-length scaling candidate = Cui & Cross (Novi Labs), URTeC
  3723784 (2022), Delaware WCA efficiency vs 5,000 ft (10,000 ft: 0.83 at 2,000 lb / 60 bbl per ft … 0.94 at 1,000 / 30;
  `docs/box/ref/3723784.pdf`). Open: whether the backtest replaces D18 / §8 as the acceptance basis, and whether lateral
  efficiency / density become decisions of record (both touch eng_db #78/#80 lateral pooling and D11).
- erebor `packages/decline` is a third partial Arps copy (`models` + `compute_eur`, verbatim from
  anduin, identical as of 2026-10-10). D15 implies erebor moves to `blueox-boxfit`; follow-up, not BOX
  scope unless Michael says so.
- Package name: an unrelated `boxfit` exists on PyPI → the distribution is `blueox-boxfit` and is never
  listed by bare name (anduin installs editable; engineering_db pins by git URL + SHA).
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
