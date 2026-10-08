---
name: deal-intake
description: Process a Land-department deal (unit shapefile + depth restrictions) through the seven-gate pipeline — narvi locations, erebor Novi forecasts, anduin type curves — into a per-bench forecast-comparison dossier with a decision log. Use when a deal package arrives from Land or the user asks to run/re-run a deal evaluation.
---

# Deal intake v2 — the `dealintake` runner (Land → dossier)

Michael is the **reviewer of exceptions, not the executor of steps**. The
runner (`python -m dealintake`, package `dealintake/` in engineering_db)
computes every signal reproducibly per `config_version`; this playbook says
how to drive it, where it stops for him, and how to read what it writes.
Geology and land calls (benches, correlated window, spacing, strike
extension, TC grouping, culling wells) are surfaced with evidence and
**never auto-decided**.

All thresholds live in `config/thresholds.yaml` (versioned — bump
`config_version` on ANY value change, never hardcode a value in logic; the
run snapshots the file as `thresholds.snapshot.yaml`). The dossier is
rendered by `dealintake/render/dossier.py`; `templates/dossier.md` is the
reading guide to its sections.

**Hard rules (inherit the workspace conventions):**
- Warehouse access is READ-ONLY. No DDL, ever, from this pipeline.
- No economics anywhere. EUR is the raw 50-yr integral. Novi EUR columns
  are a screen, never authoritative.
- Whenever Di appears (dossier, flags, chat), state nominal (per-year) AND
  1-yr effective % side by side. SPE percentile orientation (P10 = HIGH).
- Formation grouping is `formation_blueox` only (narvi's `_b` split suffix
  is stripped by `bench_code`). api10 is the well key; Novi sticks are
  `stick_id` (PDP rows = `-(api10)`).
- Novi comparison figures are the **median of representative sticks** —
  not a P50, and not the erebor export's cohort mean.
- Curve names carry no spaces and no letter suffixes (Michael 2026-10-08):
  several curves on one bench are named by compass direction of the group
  from the bench's units — `WCB_2_North`, `WCB_2_Southeast` (4-point rose,
  8-point if needed; DSU name only when interleaved groups still collide).
  Save the anduin type curves under the dossier's names.
- Nothing auto-drops a well. Every exclusion carries a reason, every
  outlier is a flag, and culling happens in anduin by the reviewer.

## What the run writes, and where

| System | What the runner does | Persists? |
|---|---|---|
| oilgas warehouse | SELECTs only | never |
| narvi | parcel upload, azimuth, zones, `/api/generate` PREVIEW | nothing saved (no scenario) |
| anduin | fits wells that have NO forecast row yet; TC `compute` previews | new forecast rows only |
| anduin — short-history transfer (ON by default) | overwrites the short wells' **unlocked** forecast rows with cohort-transfer rows | **yes — listed per bench in the dossier** |

The manual-override guard holds by construction: existing fits are reused,
never refreshed; a refit is refused when a target has `manual_override=TRUE,
locked=FALSE`; locked rows are skipped by the transfer. The transfer resets
`manual_override` on the rows it rewrites (anduin's behavior). Saving the
type curve and the narvi scenario stay reviewer actions.

## Prerequisites

- engineering_db `.venv` with `requirements-dealintake.txt` installed.
- narvi backend on :8078 (`NARVI_URL` to override); anduin on :8000
  (`ANDUIN_URL`). anduin credentials come ONLY from the environment —
  `ANDUIN_EMAIL` / `ANDUIN_PASSWORD` — so **Michael runs `evaluate` in his
  own shell**; never ask for or handle the password. If anduin is requested
  and unavailable the run fails loudly (exit 2) — that is deliberate: a
  silent skip once made a credential-less run look successful.
- `curated.codev_context` (sql/47), `pdp_support_for_geom` (sql/48) and the
  WellSpacing pass-through (sql/49) must exist live. "relation
  codev_context does not exist" = a quarterly rebuild ran from a checkout
  that predates them; re-apply via `scripts/apply_codev_context.py` (needs
  explicit authorization — it is a warehouse write).
- The codev constants (1,320 ft / 180 d / 30 % overlap) are baked into
  sql/47 and mirrored in the yaml; change both or neither. The vertical-
  parent gate (660 ft / 1,000 ft) and shielding live ONLY in sql/50
  (`curated.dev_scenario`, a plain view re-created by every sql/47 apply) —
  the runner reads the view; `scripts/find_analogs.py` and anduin
  `wells_api/filters.py` pin the 660 (workspace cross-repo contract).

## Stage 1 — `propose` (Gates 0–2 inputs), then STOP

```
python -m dealintake.cli propose <deal.gpkg|.zip> --run-dir runs/<deal>-<date>
       [--window MIN_FT MAX_FT --window-basis "who correlated, from what log"]
```

Writes `proposal.json`, `proposal.md`, `thresholds.snapshot.yaml`. Per unit:

- **Snapshot (Gate 0):** production vintage, Novi Intelligence vintage,
  wellspacing vintage, codev_context refresh time, config_version.
- **Ingest (Gate 1):** narvi reprojects and names the parcels. A
  MultiPolygon unit uses its largest part and is reported as a WARNING —
  have Land split it.
- **Planned azimuth = the unit's LONG AXIS** (Michael, 2026-09-26: sticks
  run parallel to the long axis; "a degree or two off" is not how a unit is
  planned). narvi's neighborhood-grid azimuth is advisory: printed beside it
  (true bearing) and a WARNING when a coherent grid disagrees by more than
  `alignment.grid_vs_long_axis_flag_deg` (5°) — the reviewer decides the
  development direction; the runner never switches on its own.
  **Bearing conventions (cross-repo, verified in narvi 2026-09-26):**
  narvi `/api/warehouse/azimuth` returns a TRUE bearing (PostGIS
  `ST_Azimuth` on geography); narvi `/api/generate` lays rows in UTM 13N, so
  its `azimuth_deg` input is a GRID bearing — the runner converts with
  `geo.true_to_grid` (≈ true − 0.9° across the Delaware). Passing a true
  bearing straight through drifts the rows ~0.9° (the VaULt 44-45 and
  2-11-14-23 sticks, first run). narvi itself feeds its true-bearing grid
  azimuth into UTM placement unconverted — the "grid vs lease line" drift its
  edge-snap works around — raised with Michael, not fixed from here.
- **Planned lateral:** median chord along the planned azimuth inside the
  unit buffered **330 ft inward on every side** (2-mi DSU → ~9,900 ft).
  Estimate only — narvi's generation setbacks are unchanged. A stair-stepped
  or skewed unit (VaULt 44-45 S2: the southern band exists only in the east
  half) legitimately yields one full row and one short row — the review
  page's map shows it; it is geometry, not an artifact.
- **Depth window:** declared land depths are echoed verbatim and are **NOT
  local depths** (often a reference-log pick miles away — Toucan 9,515′
  declared ≈ 9,950′ correlated). `--window` passes the engineer's
  CORRELATED window and requires `--window-basis`. Without it the declared
  numbers are used and labelled "declared (NOT local — correlate)".
- **Rights come from the DSU row, never the tracts** (Michael, 2026-09-26).
  The tracts narvi attaches to a DSU carry their own declared windows; the
  runner compares each to the DSU's and lists them on the review page
  (open, amber, plus a WARNING) when they differ — 44-45 S2's DSU says Top
  of Bone Spring → Top of Wolfcamp while its tracts say Surface → COE and
  Surface → 11,950′. The DSU window is used regardless; which paper governs
  is the reviewer's call.
- **Rights bounds (current land SOP):** each DSU row's `Min_Depth` /
  `Max_Depth` is `Surface`, `COE` ("center of earth" = unbounded below), a
  depth, or a **formation phrase** ("Top of Wolfcamp Formation"). A phrase is
  a position in the stratigraphic column (`config/strat_column.yaml`, a
  MIRROR of Engineering's `nomenclature.xlsx` — change the workbook first,
  then the mirror, bump `strat_version`), so the allowed benches follow by
  ORDER and no depth is ever invented: *Top of Bone Spring → Top of Wolfcamp
  = AVA_0 … BS3_S* (Avalon sits inside Bone Spring; WCXY is the top of
  Wolfcamp). An unrecognized phrase is a WARNING and that side stays open.
- **The review surface is `review.html`** (written by `propose`, re-rendered
  by `python -m dealintake.cli review --run-dir …`): a deal overview map by
  lateral class, then one panel per DSU — the map (offset PDP laterals and
  Novi BASE_CASE sticks coloured by bench, inside vs crossing, the planned
  chord), the TVD strip (local bench medians against the rights window, the
  declared depth lines drawn as declared-not-local), and the bench table
  (local TVD, vs window, offset PDP ≤3 mi, PDP in unit, Novi in/crossing,
  location source, scope, why), and the **gunbarrel** (Michael, 2026-09-28):
  a cross-section perpendicular to the planned azimuth in the rule-16 frame
  (origin = unit centroid, +offset = 90° clockwise of the azimuth) — the
  PROPOSED rows (one hollow square per stick at the bench's local median
  TVD, "bench: n sticks @ spacing") against the EXISTING producers whose
  lateral overlaps the unit along the laterals (filled = ≥ 30 % co-extent
  in the unit, rule 9; faded = side/partial neighbours; a well entirely
  beyond the unit's ends is not drawn). Novi BASE_CASE sticks are NOT
  drawn — our proposal vs PDP only, nothing outside the depth rights; the
  TVD window is the proposed benches ± 1,500 ft (producers outside it are
  counted in the title, not plotted); a producer at a round-100 TVD is drawn
  hollow (permit depth, suspect — rule 10; VaULt 25-26-27 "WCB_1 at
  13,000 ft" was a 2008 well with a permit TVD). Rows are narvi previews
  at the REVIEWED benches when `benches.yaml` exists, else at the seed. It
  exists so topfill/underfill calls are made by eye on the page (BS3_S rows
  sitting over WCA_1/WCXY producers) — the runner never excludes a bench for
  being a topfill or underfill. Stacked DSUs say "same footprint as …".
  **Michael reviews the page and states the exceptions in chat; the operator
  records them in `benches.yaml` — he never reads the YAML** (feedback
  2026-09-22).
- **Reviewer keys in `benches.yaml`** (VaULt walkthrough, 2026-09-28) — the
  operator writes these from Michael's calls; `propose` previews and
  `evaluate` honour them: per bench `tvd_ft` (his landing TVD for a bench
  with thin/no local control — a geology call), `spacing_ft` (the pattern —
  Novi's de-facto spacing is only a SUGGESTION shown on the page; 880 ft is
  the fallback), `n_wells` (cap, "4-per-section" = 4 @ 1,320), `keep_side:
  west|east|north|south`, `drop_east_rows: n` (and west/north/south — the n
  rows nearest that side, for PDP there or basin-edge conservatism), `role:
  upside`, `winerack: false` (opt OUT of the default stagger — a unit's
  generated benches are placed together, adjacent benches half a spacing
  apart, Michael 2026-10-08; on a narrow unit the stagger can cost a row:
  Rally Caps 1-12 WCB_2 4 -> 3); per unit `min_leg_ft` (drop stair-step stubs). Sides are compass
  words; the runner maps them onto the rule-16 frame (on a 162° plan the
  +offset side is WSW, so "east" is the negative side). Every key lands in
  the decision log.
- **Per-unit bench seed → `benches.yaml`:** current-SOP packages carry
  **depth-severed stacked DSUs** (identical polygons, different rights and
  WI/NRI — VaULt "2-11 (Bone Spring)" over "2-11 (WCB)"), so benches are
  decided PER UNIT. `propose` seeds `benches.yaml` with a reason on every
  row: off when outside the rights by stratigraphic order, no local control,
  or thin control; numeric windows judged on LOCAL medians (in → on, out →
  off); a bench within 200 ft of a window edge is decided by the formation
  in the DSU NAME when there is one ("(WCB)"), else inside-edge on /
  outside-edge off. The file also carries each unit's `planned_lateral_ft`
  for the reviewer to correct. A re-run of `propose` never overwrites it
  (fresh seed → `benches.seed.yaml`).
- **Bench proposal:** each local bench's offset-median TVD vs the window →
  `in_window | edge (within 200 ft of a boundary) | out | no_window |
  no_depth`. Landing TVD is always offset-well medians, never tops. A bench
  with < 3 real-depth wells is marked thin control.
- **Gate 2 — location source per (unit × bench)** (Michael, 2026-09-25):
  keep Novi BASE_CASE (PUD) locations ONLY when every stick is inside the
  unit (50-ft digitizing tolerance) AND the sticks are oriented like our
  plan (axial difference ≤ `alignment.azimuth_tolerance_deg`, 20°) AND
  their lateral fits our planned lateral (± the basin tolerance). Otherwise
  **narvi generates that WHOLE bench** (never a mixed bench). Novi's guess
  at a unit's infill is often the wrong orientation or length (VaULt 44-45
  S2: 5k E-W in the west, 5k/10k N-S in the east; most VaULt BASE_CASE
  sticks are 5,080-ft N-S sticks under 2-mile E-W plans) — the PRESENCE of
  BASE_CASE sticks is the signal that the bench gets infilled, not a
  location to copy. The review page shows each bench's Novi azimuth,
  lateral and de-facto spacing with the reason. Pad IoU vs
  `intel_pad_geom` is advisory only (2026Q3 covers Midland only).
- **Spacing for generated benches:** reviewer `--spacing` → else the Novi
  BASE_CASE bench's **de-facto spacing** (median perpendicular gap between
  the sticks, gaps < 300 ft = same slot; median over the class's units) →
  else the 880-ft narvi fallback. The dossier prints which.
- PDP already in the unit (≥ 30 % overlap) per bench — feeds the tier flip.

**Reviewer gate — do not run `evaluate` until Michael confirms:** the
per-unit bench list and planned laterals (he reads `review.html`; the
operator applies his calls to `benches.yaml`, the decision of record), the
correlated window + basis, per-bench planned spacing, and any emerging
bench he wants included despite thin control. Walk him through the
"Needs a look" column of the review page's summary table first.

## Stage 2 — `evaluate` (Gates 2–7)

```
python -m dealintake.cli evaluate --run-dir runs/<deal>-<date>
       [--benches WCA_1 WCA_2 ...]       ONE deal-wide list (simple deals); omit to use benches.yaml
       [--spacing BENCH=FT ...]          per-bench planned spacing (default 880 ft narvi fallback)
       [--radius BENCH=MILES ...]        reviewer pool radius (gate 5a)
       [--tc-single BENCH ...]           reviewer: ONE TC for the bench (escalate resolved / pooled, no multiplier)
       [--tc-groups BENCH=unitA,unitB[;unitC] ...]   reviewer TC grouping (gate 5b)
       [--cohort BENCH=N|pool ...]       reviewer cohort size: nearest N pool wells, or the whole pool
       [--short-history-transfer N | --no-short-history-transfer]
       [--no-anduin]                     warehouse + narvi only; split test falls back to the Novi EUR screen
python -m dealintake.cli render --run-dir ...        re-render dossier.md from signals.json
```

Writes `signals.json`, `dossier.html` (the review surface), `dossier.md`
(text record), `map_<bench>_curve_<a..>.png` (+ `map_<bench>.png` overview on multi-curve benches),
`well_sticks.json` (TC/pool laterals for the maps), `buildup_<bench>_<group>.csv`. A re-run overwrites them — copy the folder
first to keep a comparison. (`runs/` is git-ignored.)

**One pool per bench** (`planned_lateral.pooling: bench`, config v8 —
Michael 2026-09-28): every bench is pooled, split-tested and type-curved
ONCE, per 1,000 ft, and scaled **linearly** to each unit's planned lateral.
The pool's lateral band spans the units: shortest planned lateral × (1 −
tolerance) to longest × (1 + tolerance). The per-lateral-class pools of
v4–v7 were retired as "too cute": 25 mi around VaULt, 13.5k+ ft vs 2-mile
wells ran 0 to −12 % on cum-12 oil per 1,000 ft and −13 % to +8 % (mixed
sign) on 30-yr EUR per 1,000 ft, while the per-class curves moved the
other way — pool composition, not length — and the long classes held 0–12
wells. Two FLAGS replace the classes (flags only, never a filter):

- **Length check** (per bench): median per-1,000-ft of the eligible pool by
  lateral bucket (`planned_lateral.length_check.bucket_edges_ft`) vs the
  pool median; a bucket of ≥ `min_wells` beyond `flag_ratio` (1.15,
  PROVISIONAL) is flagged — linear scaling is suspect for that bench.
- **Lateral support** (per TC group × unit): cohort wells within the
  unit's own band and the cohort's lateral range. A planned lateral
  OUTSIDE the range is flagged `EXTRAPOLATED`; fewer than
  `min_wells_near_planned` (3) in band is flagged thin. The same table
  carries the curve scaled to each unit's lateral (EUR per well).

Known and accepted: a linear scale from a mostly-2-mile pool gets a 3-mile
EUR about right but front-loads year 1 by ~10 %. Say so when a long unit
is flagged. `pooling: class` restores the v4–v7 behaviour (benches keyed
`WCB_1 @ 12,620 ft`). The split test still runs per unit — a GEOGRAPHIC
split is a separate question from length. Every unit's benches + lateral
land in the decision log (gate 1), marked when edited vs the seed.

**The cohort is tier-blind** (`codev.tier_order_scope: none`, config v10 —
Michael 2026-09-29). Each TC group's cohort is the nearest `max_wells` of its
pool, whatever the wells' development scenario. Scenario is controlled at
the reviewer's bench selection (the gunbarrel step drops aggressive
placements); the dossier REPORTS it and never selects on it:

- the tier table shows each cohort well's own history (over/under an
  unshielded vertical parent, pad-mate codev, standalone) with medians;
- the **standoff table** puts each unit's planned sticks (nearest
  other-bench producer inside the 660-ft parent gate, vertical distance)
  beside the cohort's own parent standoff. Units whose sticks are parented
  more often, or tighter, than the cohort are named in ONE flag per TC
  group — the curve does not carry that penalty and the reviewer risks by
  hand. An other-bench producer within `codev.same_landing_ft` (150 ft,
  PROVISIONAL) of a stick is the same landing under a different tag — a
  neighbour, reported apart ("same landing, different tag"): check the tag
  or the placement.

**Cohort size** defaults to the nearest `type_curve.max_wells` (20).
Nearest-first lets the units with the closest offsets set a pooled curve
(VaULt BS3_C: 12 of 20 wells sat beside two units, three units contributed
none, and the curve read 57.0k against a 51.5k pool median). `--cohort
BENCH=N|pool` is the reviewer's override, decision-logged. Show the
"Built from" table by nearest unit before recommending it.

Why (VaULt BS3_C): a topfill-first cohort gave 38.6k bbl/1,000 ft from 9
wells — 4 of them one pad on the east edge with ~9 months of history and
parents at 261–416 ft — applied to sticks with 400–570 ft of standoff.
Geology and scenario could not be separated at that n, and the penalty was
over-applied. `unit` (v9) and `bench` (v7–v8) remain as config values. A
reviewer `--tc-single` / `--tc-groups` call is scoped to the units it was
made on — re-confirm it when the pool definition changes.

Order of operations is fixed and matters: **classify the pool → fit the
whole pool in anduin → transfer → split test → fill each group's cohort**.
Filling before splitting starved remote units and hid a real split (Toucan).

### Gate 3 — bench support

Per location: `pdp_count_3mi` (Novi sticks carry it; narvi-generated sticks
get it live from `pdp_support_for_geom`, same sql/30 predicate set). Bench
status per unit = median vs `bench_inclusion.pdp_count_3mi_min`:
`pass | escalate (marginal: live re-count before excluding) | escalate
(unscorable)`. It counts RAW producers (no vintage floor, no lateral band,
no months check) — passing Gate 3 never guarantees Gate 5 finds 10 TC wells.
The quarterly matview under-states support between vintages; a marginal
fail is a re-count, never an auto-exclude. TVD excess vs 3-mi offsets is
shown beside it (WCB_2 deep-TVD context).

### Gate 5a — eligible pool

Candidates = producing horizontals in the TVD-corrected bench within the
radius. Excluded WITH REASONS (a well can carry several): first production
before `first_prod_after`; lateral outside the pool band — shortest planned
lateral × (1 − tol) to longest × (1 + tol), tol = the per-basin tolerance
(delaware 25 % / midland 40 % — mirrors ledger §9), widened to
`long_lateral.tolerance` (0.40) for a planned lateral ≥
`type_curve.long_lateral.min_ft` (12,500 ft);
`months < min_months_data`; spacing class `standalone` (NULL or ≥ 2,800
sentinel) or `tight` (< 0.65 × planned spacing), judged AS-OF-FIRST-
PRODUCTION; no codev context.

Radius steps 5 → 7.5 → 10 mi until the pool reaches `min_wells`. The
**edge trigger** (median distance to nearest in-bench PDP > 15,840 ft, or
ring decay `pdp_count_1mi / pdp_count_5mi` < 0.04 — both PROVISIONAL)
blocks concentric extension and routes to a reviewer-confirmed
strike-biased set. **Emerging benches false-positive it**: thin in-bench
development reads as a basin edge (Toucan BS2_S: stuck at 2 wells / 5 mi).
Remedy: `--radius BENCH=MILES` — exactly that radius, edge block bypassed,
decision-logged. `min_wells: 10` is an uncalibrated scaffold value; under
it the cohort gets an `under_count` flag, not a block.

### Gate 5 — scenario tiers and the fill

**First-order scenario tiering (Michael, 2026-09-28).** For each bench ×
class the runner reads what is PRODUCING IN THE UNITS within
`codev.scenario_band_ft` (1,000 ft) above/below the planned bench (from the
gunbarrel's in-unit producers) — that set is the cohort's parent test, not
the deal-wide planned stack: `topfill_underfill` = the candidate had an
**unshielded vertical parent** in one of those benches; `codev` = an
ADJACENT planned bench came on within ±180 d (pad-mates, the greenfield
analog); `stack_standalone` = the rest. Later-child wells no longer tier as
topfill_underfill. Scenarios are NEVER chained ("WCB_2 under WCA" is
matched; "…and co-developed with WCB_1" is not — the data thins out and the
plan does not need it; VaULt: WCB_2-as-WCA-underfill has 31 analogs within
25 mi, the chained case 2). Michael's stated basis for dropping a bench is
often experience of poor performance, not zone absence; the dev_scenario
medians can test it (WCB_1 under WCA near VaULt: cum-12 13.0k vs codev
14.0k per 1,000 ft — no significant degradation) — offer the numbers, keep
his call. "Vertical parent" is the **house rule of record, `curated.dev_scenario`
(sql/50, Michael 2026-09-23)**: online > 180 d earlier, closest parent's
lateral MIDPOINT within **660 ft** of the subject lateral, TVD within
**1,000 ft**, and not **shielded** — a co-developed other-bench well sitting
between subject and parent hides it (Hellfire East E 8HU). The runner reads
the view's gated parent lists and re-checks shielding per adjacent bench
from `bench_context`; it copies no threshold. A parent beyond the gate is
NOT a parent (the ungated co-extent rule diluted the Midland topfill
hindcast signal 1.23× → 1.05×; gated 1.12–1.22×). Default order codev →
stack_standalone → topfill_underfill; **flips** to topfill_underfill first
when a STRICT MAJORITY of the class's units have producers within the band
of the bench (tie keeps the default). Fill: first tier nearest-first up to `max_wells`
(20); later tiers only top up to `min_wells`. Flags: `first tier capped`,
`under_count`, `first_tier_share < 50 %`. Per-tier median Novi EUR/1,000 ft
is shown so the bias direction of the tier mix is visible. The buildup
table and CSV carry each well's `scenario_class` (sandwich > topfill >
underfill > codev_stack > standalone) beside its deal tier — the tier is
relative to the DEAL's adjacent benches; the class is relative to ANY bench.

**Scenario-matched analogs outside the runner** (same rule, same answers):
- `python -m scripts.find_analogs --bench WCB_2 --scenario underfill
  --polygon unit.geojson` (or `--near LAT,LON --radius-mi R`) — API10 list +
  scenario detail + cum per 1,000 ft; `--parent-bench LSSH --parent-side
  above` for a bench-pair pull ("WCA_1 beneath LSSH", no vertical window,
  no shielding); `--min-parent-age-days` for parent age. Use it when the
  reviewer wants "wells that saw what these sticks will see" for a cohort
  the tiers don't express (e.g. sandwich only, or a specific parent bench).
- anduin's **Development scenario** filter section (class, subject bench,
  parent bench + side + age) is the same view synced onto `wells.scenario_*`;
  a `find_analogs` pull and an anduin lasso with the same filters return the
  same API10s (49/49 parity, 2026-09-25). The buildup waterfall has a
  `scenario` stage after spacing, so a scenario-filtered TC saved in anduin
  documents its culls. Both are the reviewer's tools for building the REAL
  curve after the runner's preview; the runner itself does not filter by
  class — it tiers and fills.

### Gate 5.5 — anduin fits + short-history transfer

Missing fits are created for the whole pool; existing fits are reused.
Then, ON BY DEFAULT (`type_curve.short_history_transfer_months: 9`): wells
with < 9 months AFTER PEAK receive the pool's long-well **median Di/b** per
stream, keeping their own peak qi. Hindcast basis: own-fit next-12-month
oil bias +12–16 % at 9 months → +6–11 % with the transfer; it adds
per-well scatter, so it is for type curves, not single-well forecasts.
The dossier lists lenders, lender medians (nominal + effective), rewritten
api10s, locked rows kept, and a **vintage-gap flag** when lenders are ≥ 3
years older than the short wells. anduin refuses (422, no writes) below 5
long-well lenders — recorded, not fatal; the short wells keep their own fits.

**With vs without:** for each TC group that contains transferred wells the
runner refits only those wells, computes the without-transfer TC, then
re-runs the transfer so anduin ends in the default state. A bold
**"did not reproduce the donor medians"** flag means anduin may NOT be in
the default state — stop and check before anything else touches those wells.

### Gate 5b — one type curve or several

Run on the whole pool, metric = anduin oil EUR/1,000 ft (Novi EUR screen
under `--no-anduin`). Units with ≥ 6 pool wells are testable. **Split only
when BOTH** max/min unit median > 1.25 AND the rank test is significant at
0.05 (Mann-Whitney for 2, Kruskal-Wallis for > 2); exactly one → `escalate`;
neither → `single_tc`. Indistinguishable units are merged into clusters;
units under 6 wells never split — they borrow the nearest cluster's curve
(document a multiplier if the reviewer sees a difference). The per-unit
"pool wells" count assigns each well to ONE unit (containing, else nearest),
so two adjacent units can read 29 and 0 while sharing the same offsets
(VaULt 44-45 S2 / N2); the "offsets ≤ 1 mi (shared)" column beside it is the
non-exclusive count — read that one for "does this unit have analogs". The along-axis
gradient (bbl/1,000 ft per mile, R²) is always reported. On `escalate` with
a continuous gradient and no clean break, Michael decides: one TC with the
gradient noted, or a cut where geology says — pass it back as `--tc-groups`
(named groups; the unnamed rest pool together). It is decision-logged with
what the test said.

### Gate 6 — autoforecast QC (flags only)

Per TC group: cohort table per stream (n, median 1-yr effective, IQR,
median nominal Di, median b) and per-well flags — `fit_at_bound` (anduin's own
bound check, passed through — flagged, never "fixed" by widening), `di_dispersion` (|De − cohort median|
> 10 pts), `eur_per_1000ft_outlier` (robust z > 3.5), `peak_month_vs_cohort`
(± 2 months, per-stream peaks). **The Di LEVEL is never a flag** — 65–75 %
effective is typical but varies by area/bench; SPREAD within a cohort is
the signal (different reservoir or an unreliable autofit). Di spread flags
oil only; gas and water spreads are report-only (gas tracks real GOR
behavior; TX water is often a vendor-calculated flat WOR).

### Gate 7 — the comparison, and the surface

Charts per TC group: rate vs time (log) AND cumulative vs time, oil and gas,
per 1,000 ft (Michael, 2026-09-26).

**`dossier.html` is what Michael reads** (written by `evaluate` and
`render`; `dossier.md` beside it is the plain-text record). It opens with
the unit plan and a one-row-per-curve summary (pool, n, oil EUR/1,000 ft
vs Novi and the % gap, Di nominal + effective, b, gas EUR, split verdict,
QC flag count) linking to each bench × class panel: map, pool + tiers +
transfer, split test, then per TC group the **rate-time overlay** (anduin
TC per 1,000 ft, oil + gas, log scale, 120 months — the Novi
representative-stick median as a 2-segment Arps dashed beside it, the
no-transfer curve dotted when one exists), the three-stream table, QC and
the buildup table (collapsed). Walk him through the page, not the markdown.


Per TC group, all three streams: Novi (median of the unit's representative
sticks; segment-1 Di with the share pinned at Novi's 3.65 /yr cap, segment-2
Di beside it) vs the anduin TC preview, plus **gas two ways** — independent
Arps and ratio-to-cum-oil on the TC's own oil curve (GOR fit R² shown).
Hindcast context: gas Arps runs low (−6 % → −14 % with more history, GOR
rises in the holdout); the ratio method inherits the oil forecast's error.
Arps stays the default until more deals are compared. **Gas basis =
anduin** (Michael 2026-09-28); any stream where Novi and the TC differ by
more than `qc_flags.stream_gap_flag_ratio` (1.5×) is flagged on the group
and shown as "Gas: Novi/TC" in the summary table (VaULt WCB_1 @ 9,900: Novi
gas 3.6× the TC). The Novi representative-stick pull for generated legs ≥
`type_curve.long_lateral.min_ft` uses the long-lateral tolerance (0.40) —
a deal-intake-specific reading of ledger §9 so 15,000-ft legs still get a
Novi comparison; the other §9 consumers are unchanged. Which forecast goes
to finance is Michael's call per bench — the dossier presents, never picks.

## Reading the result with Michael

Lead with numbers and units; walk the dossier in this order:
1. Deal-level FLAGs (e.g. planned laterals differ > 25 % → per-unit bands).
2. Bench matrix: any `escalate`, any `generate`, Edge = yes.
3. Per bench: pool size + radius, transfer block (mismatch flag?), split
   recommendation, then each TC group's comparison and QC flags.
4. Weak or odd wells: name them (api10, operator, EUR/1,000 ft vs cohort
   median, what Novi's screen says) and ask **cull or keep** — never decide.
5. Decision log: every reviewer override must appear there.

Reviewer levers, all decision-logged or visible in the dossier:
`--benches`, `--spacing`, `--radius`, `--tc-groups`,
`--short-history-transfer N` / `--no-short-history-transfer`.

## Known gaps (state them, don't paper over)

- **anduin oil b = 1.00 is an ARTIFACT**, not a fit: the cum-fit's harmonic
  branch has zero gradient in b at the 1.0 start value. Every TC and lender
  median shows it. Being handled in a separate anduin session — do not fix
  or compensate from here.
- **Gate 4's `inflation_ratio` band is NOT in the v2 dossier.** The runner
  reads the column but reports the TC-vs-Novi three-stream comparison
  instead; the yaml `forecast_source` section is unused by the runner. The
  ratio is still visible in erebor's Highgrade tab.
- The strike-biased well set is not generated — on an edge trigger the
  runner flags and stops extending; the reviewer supplies a radius or a
  manual set.
- Provisional / uncalibrated: edge-trigger thresholds, `min_wells: 10`,
  `di_bounds_per_stream`. Residual +6–11 % transfer bias is unexplained
  (vintage-matched lenders did not remove it).
- A well's `scenario_class` is relative to ANY bench; the tier is relative
  to what is producing in the unit within the band. Read the class column
  as context, the tier as the selection driver.
- The `codev` tier still uses the DEAL-wide planned stack for "adjacent"
  (pad-mates); with stacked DSUs a bench can count as adjacent because the
  twin plans it. Genuinely overlapping polygons that enable
  the SAME bench would each get locations for it — the reviewer owns that
  double count in `benches.yaml`. Do NOT infer overlap from DSU names:
  VaULt "2-11-14-23" and "2-11" share section numbers in different blocks
  and sit 5.5 mi apart (caught by Michael 2026-09-28) — check geometry.
- The planned-lateral chord estimate misreads odd-shaped units and units
  whose azimuth fell back to the long axis (VaULt 44-45 S2: 4,620 ft) —
  correct it in `benches.yaml`; `propose` has no azimuth override. Since
  2026-09-26 the plan is the unit long axis and the grid is advisory; the
  runner still does NOT read the in-unit PDP azimuth. When a unit's PDP run
  against its long axis (VaULt 36-37-38: one 70° well under a 162° plan;
  25-26-27: 55/70° and 158/162° mixed), show Michael the numbers and take
  his azimuth.
- A bench's planned-stack TVD can rest on one well (thin control) — it is
  printed in the proposal; say so when it happens.
- `pdp_support_for_geom` is live while `intel_pdp_support` is quarterly —
  small count differences between them are data drift, not a defect.
