---
name: deal-intake
description: Process a Land-department deal (unit shapefile + depth restrictions) through the seven-gate pipeline — narvi locations, erebor Novi forecasts, anduin type curves — into a per-bench forecast-comparison dossier with a decision log. Use when a deal package arrives from Land or the user asks to run/re-run a deal evaluation.
---

# Deal intake — seven-gate pipeline (Land → dossier)

Michael is the **reviewer of exceptions, not the executor of steps**. Every
gate emits a computed signal, a rule-based recommendation, and a
pass/escalate status. Deterministic steps execute; judgment heuristics become
computed flags; geology-driven decisions (strike extension, structural calls)
are auto-surfaced with evidence and **never auto-decided**.

The deal is a matrix of `(unit x bench)` rows. All thresholds live in
`config/thresholds.yaml` (versioned — bump `config_version` on any change,
never edit values in logic). The dossier template is
`templates/dossier.md`.

**Hard rules (inherit the workspace conventions):**
- Warehouse access is READ-ONLY except narvi's own save endpoints
  (`narvi.*` schema). No DDL, ever, from this pipeline.
- No economics anywhere. EUR is the raw 50-yr integral. Novi NPV columns are
  a screen, never authoritative.
- Whenever Di appears (dossier, flags, chat), state nominal (per-year) AND
  1-yr effective % side by side. SPE percentile orientation (P10 = HIGH).
- Formation grouping is `formation_blueox` only. api10 is the well key;
  Novi Intelligence sticks are `stick_id` (PDP rows = `-(api10)`).

## Gate 0 — Snapshot the run (auditability)

Before anything, record in the dossier header:
- `run_id` (deal name + date), `config_version` from the yaml.
- Production vintage: latest `meta.etl_log` `run_finished_at` for the
  novi/enverus nightly loads.
- Novi Intelligence vintage: current `report_name` (per
  `meta.intel_report_watermark` / `raw_intel.well_master`) — this stamps
  `curated.erebor_locations`.
- `wellspacing_vintage` (from `curated.wells_enriched`, once the
  LateralCloserXY column is applied — see Gate 5 spacing note).
- Every override the reviewer makes lands in the decision log with the gate,
  the computed signal, and the reason.

A dossier must be re-runnable: same inputs + same config version → same
signals.

## Gate 1 — Ingest & validate

Input: shapefile of one or more units + the Land depth-restriction terms.
- Upload via narvi `POST /api/parcels/upload` (.zip) — it reprojects to
  WGS84 and names parcels. Fail loud on: missing/unknown CRS, invalid or
  self-intersecting geometry, multipolygon units (split and report), missing
  required attributes (unit name).
- Parse depth restrictions into an **explicit allowed-bench list**
  (`formation_blueox` codes). Land's terms are typically "everything
  above/below X" — resolve against the basin strat column and echo the
  resolved list in the dossier for the reviewer to confirm. Example: Midland
  shallow rights above Wolfcamp A = `AVA_0, AVA_1, AVA_2, BS1_S, BS2_C,
  BS2_S, BS3_C, BS3_S`.

## Gate 2 — Location source (Novi vs narvi) — EXECUTES

Signal: alignment between the deal polygon and Novi's assumed DSU:
- IoU of deal polygon vs the Novi DSU pad polygon
  (`raw_novi_intel.pads` — display trio, frozen at the 3Q25 drop; treat IoU
  as advisory if the vintage predates the current intel report).
- Fraction of Novi stick endpoints (`curated.erebor_locations` PUD/RES
  `wellstick_geom`, live vintage) falling outside the unit — the primary
  signal, computed from live geometry.

Rule: `iou >= iou_min` AND `outside_frac <= outside_endpoint_frac_max` →
use Novi locations. Below the gray band → generate in narvi. In
`gray_band` → escalate with a map of both geometries.

narvi generation is fully scriptable — no GUI required:
- Preview: `POST /api/generate` (`GenerateRequest`: parcel, per-bench
  `zones[]` with `target_tvd_ft`/`spacing_ft`, `well_type` single|uturn,
  setbacks, azimuth auto/override).
- Persist: `POST /api/scenarios/composed` (merges kept Novi baseline +
  generated wells, saves to `narvi.scenario` / `narvi.inventory_well`).
  Equivalent headless path: `narvi.generate_scenario`/`generate_wine_rack`
  → `persist.save_scenario` (see `demo.py ... save`).
- Per-bench spacing is user-set; 1-section DSU rule `(5280−660)/(n−1)`.
  Landing TVD from the header-table median per bench (narvi's
  `/api/warehouse/zones`), never from tops/grids.

## Gate 3 — Bench inclusion — EXECUTES

Hard filter first: bench ∈ allowed-bench list (Gate 1). Then the support
screen `pdp_count_3mi >= pdp_count_3mi_min`.

**`pdp_count_3mi` semantics (verified against sql/30 — read before changing
this gate):**
- It counts RAW qualifying producers, NOT type-curve-qualified wells:
  horizontal, same TVD-corrected `formation_blueox`, TVD ±500 ft,
  `first_production_date` ≥ 6 months old, `lateral_length_ft > 0`, min
  stick-to-stick geography distance ≤ 3 mi. **No 2016+ vintage floor, no
  6,000-ft lateral minimum, no months-of-actual-data check** — so Gate 3
  passing never guarantees Gate 5 finds 10 type-curve wells; they are
  different populations by design.
- `0` = scored and genuinely unsupported (the flag population).
  `NULL` on a PUD/RES row = not scorable (unmapped bench / missing TVD or
  geometry) → escalate, don't treat as fail. `NULL` on a PDP row = N/A.
- The matview refreshes QUARTERLY only — between vintages it conservatively
  UNDER-states support (a newly-online well only adds support). A marginal
  fail (e.g. count 2) warrants a live re-count, not an auto-exclude.
- The column exists only for Novi sticks. **narvi-generated locations have
  no pdp_count_3mi** — compute it at runtime with the same sql/30 predicate
  set against the generated stick geometry (read-only lateral query;
  `idx_curated_wells_wellstick_geog` must serve it — EXPLAIN, never accept a
  seq scan).

Per-bench aggregation: a bench passes if its locations' median count passes;
report min/median/max per DSU-bench in the dossier.

## Gate 4 — Forecast source (hybrid, settled) — EXECUTES

Always take the Novi forecast (from `curated.erebor_locations` +
`raw_intel` arps/forecast series — the same rows erebor displays).

`inflation_ratio` gate (per-location `Novi PUD oil EUR/ft ÷
offset_median_eur_ft`, 2 dp):
- Aggregate per DSU-bench as the **median**; add a dispersion flag when
  `max/min > dispersion_flag_maxmin` (inconsistent local calibration even
  when the median passes).
- Asymmetric band `inflation_ratio_band` (starting `[0.80, 1.10]` — tighter
  on optimism; calibrate later vs `intel_forecast_accuracy`).
- **True NULL → Anduin-required immediately** (unanchored forecast), not
  escalate-and-wait. NULL correlates with play-edge geography — expect the
  Gate 5 edge trigger to fire on these benches. `NULL(PDP)` never enters
  the gate.
- Ratio is OIL-ONLY. The dossier comparison must show all three streams so
  the gas/NGL blind spot stays visible.
- In-range benches get the one-click "also build Anduin" option
  (`in_range_optional_anduin`).

## Gate 5 — Type-curve construction (anduin) — EXECUTES

anduin is fully scriptable over HTTP (bearer JWT via `POST /api/auth/login`;
user provisioned with `python -m app.cli.create_user`). PPTX export is the
only GUI-coupled surface; the dossier doesn't use it.

1. **Select** — `POST /api/wells/select` with the buffered deal polygon and
   filters `{formations: [bench], statuses: [PDP], first_prod_start:
   first_prod_after, lateral_min_ft: min_lateral_ft}`. The ≥
   `min_months_data` filter is NOT a selection param — post-filter the
   returned api10s on months of production before proceeding.
2. **Spacing curation (runtime, never precomputed)** — classify each
   candidate against the DEAL's planned spacing using
   `wells_enriched.lateral_closer_xy_ft`:
   standalone = NULL or > standalone cutoff; tight = `< tight_below_frac ×
   planned_spacing` (660' wells drop when planning 1320'). Remove both.
   NOTE: the column lands with `scripts/apply_lateral_closer_xy.py`, which
   is HELD until Novi confirms LateralCloserXY is as-of-first-production —
   until applied, query `raw_novi."WellSpacing"."LateralCloserXY"` directly
   (join `"API10" = api10`, `"DeletedAt" IS NULL`) and stamp the dossier
   with the unverified-semantics caveat.
3. **Count check** — need ≥ `min_wells`. Under-count and NOT near-edge →
   extend the radius concentrically and re-select. Near-edge → propose a
   strike-biased selection (this is the geological gate: show the map, the
   edge signal, and the proposed well set; **reviewer confirms before the
   forecast runs**).
4. **Edge trigger (computed, `method: density_gradient`)** — there is no
   structure surface or play-extent polygon in the warehouse; the practical
   signal is developed-extent density, reusing the sql/30 lateral at the
   unit's benches: fire when `dist_nearest_ft >
   edge_trigger.dist_nearest_ft_max` OR the ring-count decay
   `pdp_count_1mi / pdp_count_5mi < edge_trigger.ring_decay_min`
   (thresholds are provisional — calibrate; the trigger only routes to the
   reviewer-confirmed strike proposal, it decides nothing itself).
5. **Forecast** — `POST /api/forecasts/batch` (api10s ≤ 500/call,
   `alignment` stays `peak_ramp`), poll `GET /api/sync/status`. Respect the
   manual-override guard: never refit rows with `manual_override=TRUE,
   locked=FALSE` — triage first.
6. **Aggregate + save** — `POST /api/type-curves/compute` (peak_ramp) to
   preview, `POST /api/type-curves` to persist (`included_api10s` is the
   durable record), `GET /api/type-curves/{id}/export` for the CSV bundle.

## Gate 6 — Autoforecast QC — flags only

Auto-flag per well per stream; **reviewer sees flagged wells only**:
- Peak month deviates > `peak_month_tolerance` from the stream's own
  detected peak (per-stream peaks — gas commonly peaks ~4 mo after oil;
  never force streams to the oil peak).
- Di or b outside `di_bounds_per_stream` (TBD — leave configurable). A fit
  pinned at a bound (anduin's `fit_at_bound`) is flagged for review, never
  auto-accepted, never "fixed" by widening bounds.
- Well EUR vs offset P50 deviation > `eur_vs_offset_p50_tolerance`.
Report Di nominal AND 1-yr effective in every flag.

## Gate 7 — Assemble the dossier

Render `templates/dossier.md`: snapshot header, unit map(s), per-gate
signal/recommendation/status table with approve/override, the per-bench
**three-stream** Novi-vs-Anduin comparison (qi, Di nominal + effective, b,
EUR, EUR/1,000 ft, peak month), flags, and the decision log. Which forecast
goes to finance is Michael's call, informed by `inflation_ratio` — the
dossier presents both, it does not pick.

Format will iterate — match the existing map/PDF output patterns and expect
revision after the first real deal.

## Known unknowns (do not assume — re-check before relying)

- `LateralCloserXY` as-of-first-production semantics: pending Novi
  confirmation; the sql/06 column + apply script are HELD on it.
- `di_bounds_per_stream`, edge-trigger thresholds: provisional/TBD.
- `intel_forecast_accuracy` calibration of the inflation band: future work.
