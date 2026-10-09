# Blue Ox curve-drop contract — pending amendments log

Tracks every deviation between the workbooks we actually ship and the checked-in
contract (`docs/blue_ox_curve_drop_contract.md`, v1 2026-07-20) that still needs
S. Murray's acknowledgement / a loader change on the Blue Ox side. The contract
doc itself co-versions with their loader (`src/inputs_loader.py` /
`src/well_inventory.py`) and is only amended once the loader change is agreed —
until then, this file is the ledger.

Conventions: entries are dated by when the engineering side started emitting the
deviation. "Loader impact" states the minimum Blue Ox must do to load our
workbooks without error; anything marked *tolerated* means a lenient loader that
ignores unknown sheets/columns already copes.

---

## 1. Zone `reserve_category`: `RES` → `UPSIDE` — **awaiting loader ack**

- **Since:** 2026-07-22 (doc amendment merged, eng_db PR #10).
- **What:** zone-level `meta.reserve_category` value `RES` renamed `UPSIDE`
  (identical semantics — non-proven, carried unscheduled) so the zone label
  matches the per-well inventory `category` column and the narvi handoff
  vocabulary. anduin refuses `RES` at build; every drop since emits
  `PUD | UPSIDE`.
- **Loader impact:** accept `UPSIDE` wherever `RES` was accepted. **Required**
  — current drops fail a loader that still whitelists only `PUD|RES`.

## 2. Inventory `category` column + PDP display rows — **awaiting loader ack**

- **Since:** 2026-07-22 (anduin PR #14/#16; first shipped in the theCan drop).
- **What:** `inventory` gains a `category` column (`PDP | PUD | UPSIDE`), and
  **PDP rows are included** — existing in-unit producers (≥30 % co-extent
  membership) carried for downstream gunbarrel reconstruction. PDP rows are
  display-only: excluded from `gross_locations` and the Block B lateral means,
  exempt from the 3,000–25,000 ft lateral bounds. Unzoned PDP rows carry their
  bench code (e.g. `WCA_1`) in `area` — the one sanctioned case where `area`
  is not a zone-sheet name.
- **Loader impact:** count only `PUD`/`UPSIDE` rows toward `gross_locations`
  and lateral means; tolerate bench-code `area` values on `PDP` rows.
  **Required** for §3 gate 3 to keep passing.

## 3. Geologic risking disclosure — **awaiting loader ack** (eng_db PR #11)

- **Since:** 2026-07-24 (anduin PR #20; first risked drop: toucan re-export
  2026-07-27, `risk_mult` 0.8 on `toucan_bs2s`).
- **What:** per-stream geologic multipliers may be applied at the export
  boundary. Disclosure: `curve_params` gains a `risk_mult` column and risked
  fits carry `qi_basis = fitted_qi_risked`; manifest `risking` reads
  `geologic_multipliers_applied` (instead of the v1-mandated `unrisked`) when
  any zone is risked. Narrows Principle 3 to "no *commercial* / no
  *undeclared* risking". Analog/observed actuals are never risked.
- **Loader impact:** accept the second `risking` token; tolerate `risk_mult`
  in `curve_params`. **Required** for risked drops.

## 4. `zone_scenario_scope` manifest keys — **awaiting ack** (tolerated)

- **Since:** 2026-07-27 (anduin PR #22).
- **What:** when a zone's curve applies to a subset of the deal's DSUs
  (wide deals carrying e.g. WEST + EAST curves on the same bench), manifest
  Block A declares `zone_scenario_scope[<zone>]` rows listing the scoped
  narvi scenarios. Absent on unscoped zones (legacy output byte-identical).
- **Loader impact:** ignore unknown Block A keys — informational only.

## 5. Format questions from the theCan dry-run — **answers outstanding**

Open since 2026-07-21; drops currently use our chosen forms:
1. Date-string format in `analog_production.date` / manifest dates.
2. Manifest exception key name: `analog_history_exceptions`.
3. `ngl_basis` token: `derived_by_blue_ox_via_yield` (NGL-via-yield amendment
   itself is in the contract doc, agreed 2026-07-20).
4. `qi_units` strings (`bbl/d`, `Mcf/d`).

## 6. Inventory gunbarrel geometry columns + `dsu_meta` sheet — **NEW (this change, 2026-07-27)**

Requested by S. Murray so Blue Ox can rebuild per-DSU gunbarrels
(PDP/PUD/UPSIDE) from the drop alone.

- **What — `inventory` additive columns** (appended after the existing
  `area, category, producing_lateral_ft, drilled_lateral_ft, well_name`;
  existing names/order unchanged):

  | Column | Units | Meaning |
  |---|---|---|
  | `dsu_id` | — | DSU/scenario key (`<narvi deal_id>/<scenario_id>`); groups rows into one gunbarrel |
  | `bench` | — | `formation_blueox` bench code (finer than `area`: a zone may span benches) |
  | `landing_tvd_ft` | ft | landing TVD (gunbarrel Y, increasing down) |
  | `gunbarrel_offset_ft` | ft | signed cross-section offset of producing leg A (gunbarrel X) |
  | `gunbarrel_offset_b_ft` | ft | leg B offset — U-turn wells only, else blank |
  | `lateral_azimuth_deg` | deg | lateral azimuth of the well |
  | `heel_a_lon`, `heel_a_lat`, `toe_a_lon`, `toe_a_lat` | deg (WGS84) | producing-leg-A endpoints |
  | `heel_b_lon`, `heel_b_lat`, `toe_b_lon`, `toe_b_lat` | deg (WGS84) | leg-B endpoints — U-turn only, else blank |

- **What — new sheet `dsu_meta`** (one row per `dsu_id`):
  `dsu_id, azimuth_deg, origin_lon, origin_lat`. Reproducibility of the
  offsets: `gunbarrel_offset_ft` = signed projection of the leg midpoint onto
  the axis 90° clockwise of `azimuth_deg` (folded to [0°, 180°)) through the
  origin (parcel centroid), in feet. *(Sign rule superseded by §13 for drops
  that carry `dsu_meta.plus_offset_bearing_deg`.)* Plotting offset vs `landing_tvd_ft`
  reproduces the narvi gunbarrel; U-turn legs A/B join at one TVD.
- **Loader impact:** extra `inventory` columns *tolerated* (ignore unknowns);
  `dsu_meta` joins the reserved sheet-name list (must never collide with a
  zone name). Gunbarrel rebuild itself is new Blue Ox-side tooling.

## 7. `novi_comparison` + `novi_comparison_meta` sheets + manifest keys — **NEW (this change, 2026-07-27)**

Requested by S. Murray: every type curve ships with the median Novi
Intelligence ML forecast of a representative location set, so the TC-vs-Novi
comparison figure in the dossier is reproducible from the drop.

- **Selection rule** (single source of truth:
  `curated.intel_representative_sticks`, sql/35): per planned well —
  *generated* narvi sticks take the neighborhood set (same `formation_blueox`
  bench, novi_intel PUD/RES sticks within 1 mi stick-to-stick, intel lateral
  within ±25 % of the subject's completed lateral; n < 3 flagged, never
  silently widened); *curated* narvi sticks (locations that ARE novi_intel
  sticks) use exactly their own stick's forecast (`self`). PDP wells
  contribute nothing (no intel ML forecast exists for producers). Per zone,
  the representative sets of all captured wells are unioned (deduped) and the
  median is taken across sticks.
- **What — new sheet `novi_comparison`** (long): `area, month, oil_bbl,
  gas_mcf, water_bbl` — median monthly volumes **per 1,000 ft lateral**
  (same not-pre-multiplied discipline as the zone sheets), months 1–600,
  Novi aligned to IP (month 1 = first forecast month; the TC zone vectors
  remain peak-fit laid at the head per `qi_basis`). Zones with no eligible
  sticks have no rows here (declared in the meta sheet).
- **What — new sheet `novi_comparison_meta`** (one row per zone):
  `area, n_sticks, n_self, n_neighborhood, n_pud, n_res, n_wells_no_set,
  radius_m, lateral_tol, intel_vintage, low_n_flag, stale_vintage_flag,
  tc_risked`.
- **What — manifest Block A keys:** `novi_intel_vintage`,
  `novi_selection_radius_m`, `novi_selection_lateral_tol`,
  `novi_alignment` (= `novi_to_ip_tc_to_peak`), `novi_rate_to_volume_days`
  (day-count constant converting Novi per-day rates to monthly volumes).
- **Loader impact:** two new reserved sheet names + Block A keys —
  *tolerated* by a lenient loader; parsing them is new Blue Ox-side tooling.
  The Novi series is a **screen/benchmark only** — the zone-sheet vectors
  remain the sole economic input (no change to §3 gates).

## 8. Analog-sheet well coordinates — **NEW (2026-07-29)** (tolerated)

Added so Blue Ox can map the type-curve (analog) wells without a separate
header pull.

- **What:** every per-zone analog sheet (`<Zone> meta`, the
  `per_well_summary` block) gains six columns appended after the existing
  twelve (existing names/order unchanged):

  | Column | Units | Meaning |
  |---|---|---|
  | `surface_lon`, `surface_lat` | deg (WGS84) | surface hole location |
  | `heel_lon`, `heel_lat` | deg (WGS84) | landing point (start of lateral; wellstick SHL→LP→MP→BHL vertex 2) |
  | `toe_lon`, `toe_lat` | deg (WGS84) | bottomhole location |

  Values rounded to 6 decimals (~0.1 m). Wells with no wellstick geometry
  carry blank heel cells but keep surface/toe; wells with no geometry at all
  carry six blanks — blank cells inside the block are sanctioned, matching
  the §6 inventory-geometry precedent. **Ordering standardized 2026-07-29
  (anduin PR #32):** lon-first pairs drop-wide, matching §6's
  `heel_a_lon, heel_a_lat` and WKT's inherent `lon lat` order. The first §8
  drops (2026-07-29 toucan/bro_time re-exports) shipped lat-first
  (`surface_lat, surface_lon, …`) — a loader that read those must key on the
  renamed headers from the next drop onward.
- **Loader impact:** extra analog-sheet columns *tolerated* (ignore
  unknowns). The api-column-uniqueness rule (§1.4) is unaffected.

**2026-07-29 follow-up — mid-lateral heel defect + `wellstick_wkt` column**
(reported by S. Murray on the bro_time drop; anduin PR #31):

- **Defect:** the warehouse wellstick builder removes NULL vertices, so a
  well whose Novi landing point is missing carries a 3-vertex SHL→MP→BHL
  stick — the first drops' "heel" (stick vertex 2) was the **mid-lateral
  point** on those wells (2,443 of ~61.7k sticks; e.g. Echo B 2254H heel→toe
  5,132 ft vs 10,675 ft stated lateral). 110 further 2-vertex sticks put the
  toe at vertex 2.
- **Fix (values, not names):** `heel_lat`/`heel_lon` now emit only when the
  stick carries all 4 vertices (vertex 2 = landing point guaranteed);
  otherwise blank per the sanctioned-blanks rule. Do not trust heel columns
  from workbooks exported before 2026-07-29 (toucan, bro_time) — re-drops
  supersede them.
- **New column `wellstick_wkt`** appended after `toe_lon`: the full wellbore
  polyline as WKT `LINESTRING(lon lat, …)`, WGS84, 6 decimals — the
  authoritative geometry (identical to the anduin map render), faithful at
  any vertex count. Parse with `shapely.wkt.loads`; prefer it over the
  scalar pairs wherever the actual path matters. Blank when the well has no
  stick at all.
- **Loader impact:** *tolerated* (one more unknown column). Plotting
  guidance: use `wellstick_wkt` verbatim; heel→toe scalar segments are only
  valid where the heel cells are populated.

## 9. Per-basin lateral-length tolerance for the Novi representative set — **NEW (2026-07-30)** (tolerated)

Amends the §7 selection rule. Midland per-foot productivity is near
length-invariant with increasing lateral length, so shorter analogs remain
representative there; Delaware per-foot degrades with length and keeps the
tight band. Motivating case: a Midland deal planning 3-mile laterals
(15,800 ft) over Novi inventory that is entirely ≤2-mile within 1 mi — the
flat ±25 % band matched zero sticks in every zone.

- **What:** the intel-lateral tolerance in the §7 neighborhood rule is now
  **per-basin**: ±25 % (Delaware, and any unresolved basin) / **±40 %
  (Midland)**. Basin resolves from the modal `basin` of the novi_intel
  sticks within 5 mi of the subject well. Radius (1 mi), the same-bench
  rule, the n < 3 `low_n` flag, and never-silently-widened semantics are
  unchanged — the band is basin-calibrated, not removed.
- **Declaration:** `novi_comparison_meta.lateral_tol` (per zone) is the
  authoritative value and now varies by basin. Manifest
  `novi_selection_lateral_tol` still declares the single value on a
  single-basin deal (the practical case); a mixed-basin deal declares the
  sentinel string `per_zone_see_novi_comparison_meta` instead of one
  zone's number.
- **Loader impact:** *tolerated* — the meta column always carries the real
  per-zone value; a loader reading the manifest key must accept the
  sentinel string (or prefer the meta column).

## 10. Per-well as-drilled `lateral_azimuth_deg` on adopted rows — **NEW (2026-08-03)** (tolerated)

Follow-up to the toucan azimuth reissue (Blue Ox query 2026-07-31). Blue Ox
observed that `inventory.lateral_azimuth_deg` carried zero spread within each
unit — one number stamped per unit rather than a per-well as-drilled figure.
That read was correct; the semantics change in their favor.

- **What — `inventory.lateral_azimuth_deg`:** on **adopted rows** (PDP
  producers and curated Novi PUD/RES sticks) the column now carries each
  well's **own as-built bearing** (geodesic-consistent, computed from the
  well's actual leg geometry in a conformal projection, folded to
  [0°, 180°)). Expect real spread within a unit (e.g. toucan_2 PDPs
  55.5–57.4°). Generated (planned-new) rows keep the uniform plan azimuth
  as before.
- **What — `dsu_meta.azimuth_deg`:** now defined as the azimuth of the
  **planned sticks** (generated + adopted PUD/RES — the development
  direction), never steered by legacy producers that happen to sit in the
  unit (existing wells only define it on a pure-PDP unit with no plan). It
  remains **the** projection frame: every `gunbarrel_offset_ft` /
  `gunbarrel_offset_b_ft` in the unit — including adopted rows whose own
  bearing differs — is the §6 signed projection on this single axis, so the
  §6 reproducibility rule is now guaranteed even on units where existing
  wells run off the plan direction.
- **Consequence:** `inventory.lateral_azimuth_deg` may legitimately differ
  from `dsu_meta.azimuth_deg` on adopted rows. For projection math always
  use `dsu_meta.azimuth_deg`; the per-well column is descriptive
  (as-drilled orientation).
- **Loader impact:** *tolerated* — no columns added, renamed, or moved.
  Only a consumer that assumed per-well azimuth == unit azimuth (or used
  the per-well column as the projection axis) needs to switch to
  `dsu_meta.azimuth_deg` for reconstruction.

## 11. Same-bench zone splits (WEST/EAST curves on one bench) — **NEW (2026-08-06)** (tolerated, re-drop supersession note)

A wide deal may need two different type curves for the SAME bench because the
geology differs across the acreage (motivating case: bro_time, where the
westward and eastward parcels each warranted their own WCB_2 curve built from
differentiated analog sets). The drop framework has supported this since §4
(scenario-scoped zones); this section fixes the naming convention and the
re-drop semantics so a split is an expected shape, not a surprise.

- **What — zone naming:** a split bench ships as two (or more) zones with
  **distinct zone names**: the bench code plus a short qualifying suffix
  (≤26 chars, Principle 2 charset). **Shipped form of record (bro_time
  re-drop, accepted by the Blue Ox loader): `WCB_2 West` / `WCB_2 East`** —
  space-separated qualifiers, now final per Principle 2; future splits
  follow this shape. (This file's first draft illustrated `WCB_2_W` /
  `WCB_2_E`; the shipped names supersede the example.) Zone names remain
  labels; the `bench` column (§6) carries the SAME bench code (`WCB_2`) on
  both zones' inventory rows — `bench`, not the zone name, is the geologic
  identity.
- **What — partition guarantees (build-refused, not conventions):** anduin
  hard-errors a drop where (a) two zones claim one bench with OVERLAPPING
  scenario scopes (no location can be double-counted), or (b) a planned well
  of a claimed bench sits in a scenario NO claiming zone covers (scope can
  never silently shrink the location count). Every split drop that builds is
  therefore a clean partition: each planned well of that bench appears in
  exactly one zone.
- **What — declaration:** both zones declare `zone_scenario_scope[<zone>]`
  in manifest Block A (§4) listing the DSUs each curve covers. The §7
  `novi_comparison` carries one row-set per split zone, each computed only
  from that zone's scoped wells' representative sets — the benchmark
  respects the split.
- **Re-drop supersession:** introducing a split on a previously-shipped deal
  REPLACES the old single zone (e.g. `WCB_2`) with the suffixed zones
  (`WCB_2 West` + `WCB_2 East`) — the old sheet/`area` value does not
  reappear. This is the one sanctioned case where a re-drop's zone list
  changes without a curve being added or removed economically; the drop
  email calls it out whenever it happens. **Exercised on the bro_time
  re-drop (2026-08): split shipped, supersession called out, Blue Ox
  analysis completed on the new file — this section is now practice, not
  proposal.**
- **Loader impact:** *tolerated* for a loader that enumerates zones from the
  workbook (the standing assumption). A loader that keys on zone names being
  stable across re-drops must treat a declared split as supersession of the
  old zone name — total location count and Block B reconciliation are
  unchanged (the split partitions rows; it never adds or drops any).

## 12. Deliverable B — the PDP workbook, as built — **NEW (2026-10-02)** (needs ack before first send)

Contract §2 specified the PDP workbook but nothing emitted it until the alchemist
deal (seller data room with daily production). anduin now builds it from the PDP
tab (`exports/blueox_pdp.py`, pure builder; `GET /api/deals/{id}/pdp/export.xlsx`).
Everything below is declared in the workbook's own `manifest`, so a lenient
loader needs nothing new except where marked.

- **What — shape (contract-conformant):** `<codename>_pdp_<YYYY-MM-DD>.xlsx`; one
  sheet per PDP group with `gross_oil_bbl`, `gross_gas_mcf`, `gross_water_bbl`;
  no date column; group aggregate, gross, monthly; Mcf not MMcf; then `manifest`.
  Curves mode only — no revenue/opex columns ever (scope rule).
- **What — `first_row_month` (new manifest key):** row 1 = the effective-date
  month when the effective date is the 1st, otherwise the following month. §2
  says "first month after the effective date", which is ambiguous for a 1st-of-
  month date; the key removes the ambiguity.
- **What — rows before data-through are ACTUALS (`history_basis`, new key):** if
  the effective date precedes the last reported day, those rows carry the
  seller's reported daily volumes summed by month (e.g. July = 3 reported days +
  28 forecast days); later rows are forecast. Value
  `seller_reported_daily_through_history_then_forecast`;
  `production_history_through` = last reported day.
- **What — default grouping is ONE SHEET PER WELL (`grouping`, new key):** WI
  differs inside leases (alchemist: Atlanta 73 72H vs 73H; Yorktown wells 30–72%),
  so aggregating would force one interest across wells. Group = well name. Lease
  grouping and custom groups remain available; the manifest declares which.
  Group names never equal a zone name (build-refused).
- **What — Block B (manifest):** one row per group: `group`, `mode` (`curves`),
  `well_count`, `dollar_basis` (`not_applicable` — curves mode carries no $),
  `eur_oil_bbl`, `eur_gas_mcf`, `eur_water_bbl` (exact sums of the delivered
  sheet columns, ±0.1% gate trivially met), `api10s`.
- **What — volume basis (`water_basis`, `forecast_method`, `forecast_horizon`):**
  forecasts are fit on seller DAILY volumes (producing-day rate × per-well
  uptime from routine downtime); water is seller-measured (`water_basis =
  seller_measured_daily_vdr`), not the Novi TX allocation. Volumes stop at each
  well's first production + 50 yr (raw technical horizon, no economic limit);
  later rows are zero. `curve_months` = the deal's curve-drop length (600).
- **What — NGL:** no `gross_ngl_bbl` column (optional in §2); `ngl_basis =
  derived_by_blue_ox_via_yield`, same as the curve drop (2026-07-20 amendment).
- **What — `review_status` (new key):** "N of M well-streams locked" — the
  engineer's sign-off state at export time. Not a gate on the Blue Ox side.
- **Kickoff inputs still owed by Blue Ox for alchemist:** the effective date and
  the grouping preference (per-well default).
- **What — non-producing wells that convey (`shut_in_wells`, new key; 2026-10-02):**
  seller `2PDNP` wells are included when the deal conveys them (alchemist: Atlanta
  73 2H, per Michael). A stream with no producing day in the trailing 365 d is
  forecast at ZERO (matching the seller's own ARIES forecast for that well); the
  well still gets its own sheet (all zeros) and counts in `well_count`. A
  reactivation case, if engineering sets one, starts at the declared restart date
  and is zero before it. `shut_in_wells` lists the zero-forecast wells (or
  `none`).
- **Loader impact:** *tolerated* if the loader ignores unknown manifest keys and
  takes group sheets by enumeration. **Ack needed** on (a) `first_row_month`
  semantics and (b) actuals in pre-data-through rows — if Blue Ox wants forecast
  only from the effective date, that is a one-flag change on our side.

## 13. Gunbarrel offset sign — v2 reading convention — **NEW (2026-10-08)** (**Loader impact: required**)

Engineering-side decision (Michael, 2026-10-08): every cross-section reads
**West → East for N-S-ish units and South → North for E-W-ish units**. Under
the §6 rule (+offset 90° clockwise of the folded azimuth) any unit planned past
135° — including every ~0°-true plan, which is ~179.5° in narvi's UTM-13N grid —
read East → West, and E-W units read North → South.

- **What — `inventory.gunbarrel_offset_ft` / `gunbarrel_offset_b_ft`:** still
  the §6 signed projection of the leg midpoint through the `dsu_meta` origin, in
  feet; the **sign rule changes**. With a = `dsu_meta.azimuth_deg` (axial,
  [0°, 180°), 0.1° precision): the +offset direction has compass bearing
  **a + 90° when a ≤ 45°, else a − 90°** — always inside (−45°, 135°], i.e. +
  points into the NE half. One seam remains, at a 45° lateral (+ = SE there);
  units planned within a few degrees of 45° on either side plot mirrored
  relative to each other. Units with a ≤ 45° are numerically unchanged; units
  with a > 45° are exactly negated relative to §6.
- **What — `dsu_meta` additive column `plus_offset_bearing_deg`** (deg,
  compass, 0.1 precision): the +offset direction, stated explicitly. Projecting
  the leg midpoint (UTM 13N work CRS, as §6) onto the unit vector
  (sin b, cos b) at this bearing reproduces every offset with no sign rule on
  the receiving side. **Its presence marks a v2-sign drop**; drops without it
  used the §6 rule.
- **Consequence:** workbooks shipped before 2026-10-08 keep the §6 sign. A
  re-drop of the same deal plots **mirrored** for every unit with a > 45°
  (e.g. bro_time ~161°, toucan ~55°, VaULt ~71°/~161°); the drop's what-changed
  note says so. Geometry, well counts and laterals are unchanged.
- **Loader impact: required.** A loader that recomputes offsets from
  `dsu_meta.azimuth_deg` must use `plus_offset_bearing_deg` when present (else
  the §6 rule for legacy drops); a v2 drop recomputed with the §6 rule fails
  reproducibility on every a > 45° unit. A loader that only plots the stored
  offsets needs no change (its plots now read W → E / S → N). `dsu_meta` gains
  one column — tolerated by a loader that ignores unknown columns.

---

*Column/sheet/key names in §6–§13 are final once the first workbook carrying
them ships; any rename during implementation updates this file in the same
commit.*

### §9 note — deal-intake long-lateral reading (2026-09-28, not a drop change)

The deal-intake runner (`engineering_db/dealintake`) applies the §9 per-basin
lateral tolerance (delaware 0.25 / midland 0.40) to the Novi representative-stick
pull EXCEPT for generated legs at or above `type_curve.long_lateral.min_ft`
(12,500 ft), which use 0.40 so a 15,000-ft VaULt leg still finds Novi's
5,080–10,360-ft sticks. anduin's dossier analog set, narvi's `warehouse.py` and
`sql/35`'s default are unchanged; nothing the Blue Ox drop emits changes.
Michael, 2026-09-28.
