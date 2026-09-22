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
  sql/47 and mirrored in the yaml; change both or neither.

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
- **Planned lateral:** median chord along the planned azimuth inside the
  unit buffered **330 ft inward on every side** (2-mi DSU → ~9,900 ft).
  Estimate only — narvi's generation setbacks are unchanged. Azimuth =
  narvi's neighborhood grid when confident, else the unit long axis; the
  source is printed.
- **Depth window:** declared land depths are echoed verbatim and are **NOT
  local depths** (often a reference-log pick miles away — Toucan 9,515′
  declared ≈ 9,950′ correlated). `--window` passes the engineer's
  CORRELATED window and requires `--window-basis`. Without it the declared
  numbers are used and labelled "declared (NOT local — correlate)".
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
  location source, scope, why). Stacked DSUs say "same footprint as …".
  **Michael reviews the page and states the exceptions in chat; the operator
  records them in `benches.yaml` — he never reads the YAML** (feedback
  2026-09-22).
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
- **Gate 2 — location source per (unit × bench):** every Novi BASE_CASE
  (PUD) stick inside the unit (50-ft digitizing tolerance) → keep Novi
  locations; **any stick crossing the unit line → narvi generates that
  WHOLE bench** (never a mixed bench). Pad IoU vs `intel_pad_geom` is
  advisory only (2026Q3 covers Midland only).
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
       [--tc-groups BENCH=unitA,unitB[;unitC] ...]   reviewer TC grouping (gate 5b)
       [--short-history-transfer N | --no-short-history-transfer]
       [--no-anduin]                     warehouse + narvi only; split test falls back to the Novi EUR screen
python -m dealintake.cli render --run-dir ...        re-render dossier.md from signals.json
```

Writes `signals.json`, `dossier.md`, `map_<bench>.png`,
`buildup_<bench>_<group>.csv`. A re-run overwrites them — copy the folder
first to keep a comparison. (`runs/` is git-ignored.)

**Lateral classes:** units whose planned laterals are within
`planned_lateral.class_ratio` (1.10) of the class's shortest unit share a
class. Every bench is pooled, split-tested and type-curved **per class**,
with the lateral band (± per-basin tolerance) centered on the class median
— a 3-mile unit is not type-curved from a band centered on 2-mile wells.
A bench planned in several classes appears as `WCB_1 @ 12,620 ft`, etc.
`--radius` / `--tc-groups` are keyed by bench and apply to each of its
classes. Every unit's benches + lateral land in the decision log (gate 1),
marked when edited vs the seed.

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
before `first_prod_after`; lateral outside the planned lateral ± the
per-basin tolerance (delaware 25 % / midland 40 % — mirrors ledger §9);
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

### Gate 5 — co-development tiers and the fill

Tier of each pool well vs the ADJACENT planned benches (one above / one
below in the planned stack): `codev` (adjacent bench online within ±180 d,
no earlier parent) · `stack_standalone` (no adjacent neighbor) ·
`topfill_underfill` (an adjacent bench was a parent > 180 d earlier, or
only a later child). Default order codev → stack_standalone →
topfill_underfill; **flips** to topfill_underfill first when a STRICT
MAJORITY of deal units already have PDP in an adjacent bench (tie keeps the
default). Fill: first tier nearest-first up to `max_wells` (20); later
tiers only top up to `min_wells`. Flags: `first tier capped`,
`under_count`, `first_tier_share < 50 %`. Per-tier median Novi EUR/1,000 ft
is shown so the bias direction of the tier mix is visible.

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
(document a multiplier if the reviewer sees a difference). The along-axis
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

### Gate 7 — the comparison

Per TC group, all three streams: Novi (median of the unit's representative
sticks; segment-1 Di with the share pinned at Novi's 3.65 /yr cap, segment-2
Di beside it) vs the anduin TC preview, plus **gas two ways** — independent
Arps and ratio-to-cum-oil on the TC's own oil curve (GOR fit R² shown).
Hindcast context: gas Arps runs low (−6 % → −14 % with more history, GOR
rises in the holdout); the ratio method inherits the oil forecast's error.
Arps stays the default until more deals are compared. Which forecast goes
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
- Adjacency for the co-development tiers uses the DEAL-wide planned stack,
  not each footprint's — with stacked DSUs a bench can count as "adjacent"
  because another unit plans it. Overlapping units that enable the SAME
  bench (VaULt 2-11-14-23 over the 2-11 pair) each get locations for it —
  the reviewer owns that double count in `benches.yaml`.
- The planned-lateral chord estimate misreads odd-shaped units and units
  whose azimuth fell back to the long axis (VaULt 44-45 S2: 4,620 ft) —
  correct it in `benches.yaml`; `propose` has no azimuth override.
- A bench's planned-stack TVD can rest on one well (thin control) — it is
  printed in the proposal; say so when it happens.
- `pdp_support_for_geom` is live while `intel_pdp_support` is quarterly —
  small count differences between them are data drift, not a defect.
