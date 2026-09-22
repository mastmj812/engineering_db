# Deal dossier — section guide (v2)

(Stage 1's review surface is `review.html` — see SKILL.md; this guide covers
the Stage 2 dossier.)

The dossier is RENDERED by `dealintake/render/dossier.py` from
`signals.json`; this file is not filled in by hand. It documents each
section in render order: what it shows, and what the reviewer does with it.
If the renderer changes, change this guide in the same commit.

Conventions (printed at the top of every dossier):
Di = nominal /yr with 1-yr effective beside it; EUR = raw 50-yr technical
integral per 1,000 ft of lateral; rates are calendar-day (stated in the
column headers); Novi figures are the MEDIAN of
representative sticks (not a P50, not the erebor export's cohort mean);
no economics.

## 1. Run snapshot (gate 0)

| Field | Meaning |
|---|---|
| production_vintage | last nightly load — the actuals the fits saw |
| intel_vintage_date | Novi Intelligence report behind the sticks |
| wellspacing_vintage | `lateral_closer_xy_ft` as-of (AS-OF-FIRST-PRODUCTION semantics) |
| codev_context_refreshed | co-development tiers as-of |
| config_version | thresholds.yaml version (snapshot copied into the run dir) |
| planned stack (shallow→deep) | evaluated benches ordered by local median TVD — defines "adjacent" |
| planned lateral (median of units) | centers the lateral band for TC candidates |

`> FLAG:` lines under it are deal-level (e.g. unit planned laterals differ
> 25 % → consider per-unit TC bands).

## 1b. Unit plan (reviewer)

One row per unit from `benches.yaml` (or `--benches`): DSU name, rights as
resolved (depths are declared-not-local; formation phrases by stratigraphic
order), benches evaluated, planned lateral, its lateral class, and whether
the reviewer edited the seed. A `FLAG` above it lists the lateral classes
when there is more than one — each bench section is then per class
(`WCB_1 @ 12,620 ft`), with a "Units: …" line naming the class's units.

## 2. Bench matrix (unit × bench)

| Column | Read it as |
|---|---|
| Locations (src) | count + `novi` (all PUD sticks inside the unit) or `generate` (a stick crossed the line → narvi preview for the whole bench) |
| pdp_count_3mi med / Gate 3 | raw-producer support; `escalate (marginal…)` = live re-count before excluding, never auto-exclude |
| TVD excess max ft | location TVD vs 3-mi offsets (deep-TVD screening context) |
| PDP in adjacent bench | feeds the tier-order flip (strict majority of units) |
| TC group | which type curve this unit uses |
| Edge | edge trigger fired for the bench |

## 3. Per bench — `## {bench} — TVD, spacing (source), basin`

1. **Map** (`map_{bench}.png`): units, locations (Novi sticks vs narvi
   preview sticks), TC wells colored by tier, eligible-not-selected hollow.
2. **Eligible pool**: n eligible, exclusions by reason (a well can carry
   several), adjacent planned benches, tier order + why. Pool notes follow
   as `>` lines: radius used (`(REVIEWER override)` when `--radius`), edge
   trigger fired / bypassed, adjacent-PDP majority.
3. **Short-history cohort transfer**: lenders → short wells, lender median
   Di (nominal + effective) and b per stream, rewritten api10s, locked rows
   kept, vintage + proppant comparison, vintage-gap flag (≥ 3 yr). Variants:
   "No short wells in the pool"; "transfer NOT applied" (anduin 422 below 5
   lenders). `With/without:` note when no transferred well sits in a cohort.
   **Bold "did not reproduce the donor medians" = anduin may not be in the
   default state — stop and check.**
4. **TC granularity (gate 5b)**: `single_tc | split_by_polygon | escalate`;
   per-unit pool counts and medians; median ratio, rank test + p, along-axis
   gradient (bbl/1,000 ft per mile, R²); notes (units under 6 wells borrow;
   continuous gradient with no clean break). `Reviewer grouping` line when
   `--tc-groups` replaced the test.

### Per TC group — `### TC group: {name} — units …`

| Block | What the reviewer checks |
|---|---|
| Tier table | TC wells per tier + per-tier median Novi EUR/1,000 ft (bias direction of the mix); flags `first tier capped`, `under_count`, `first_tier_share < 50 %` |
| Buildup table (= `buildup_{bench}_{group}.csv`) | one row per TC well: operator, first prod, lateral, spacing class, tier, months, Novi EUR/1,000 ft (screen), anduin oil EUR/1,000 ft, Di nom + eff, b, peak month, proppant. The CSV is the `included_api10s` record for saving the TC in anduin |
| Three-stream comparison | Novi median vs anduin TC preview: qi/1,000 ft (cal-day), Di nom (with share at Novi's 3.65 cap; seg-2 Di), Di eff yr-1, b, EUR/1,000 ft. Gas shown twice — Arps and ratio-to-cum-oil (GOR fit R², × Arps EUR). Equal EUR does not mean equal shape: compare qi and decline too |
| With vs without short-history transfer | only when the cohort holds transferred wells: oil + gas TC both ways, EUR delta |
| Autoforecast QC | cohort table per stream (oil flagged; gas/water report-only) + per-well flags: `fit_at_bound`, `di_dispersion`, `eur_per_1000ft_outlier`, `peak_month_vs_cohort`. Flags only — cull-or-keep is the reviewer's call, executed in anduin |

Known artifact: anduin oil **b = 1.00** throughout is the cum-fit harmonic
branch, not a fit result (tracked in anduin).

## 4. Decision log

| # | Gate | Bench | Signal | Decision | By |
|---|---|---|---|---|---|

One row per unit for `1 unit benches + lateral` (seed vs decision, "edited
vs seed" when the reviewer changed it), plus one row per reviewer override
the runner was given: `5a pool radius`
(`--radius`, with the edge signal it overrode) and `5b TC granularity`
(`--tc-groups`, with what the test said). Decisions taken outside the
runner — allowed benches, correlated window + basis, spacing, wells culled
in anduin, which forecast goes to finance — are recorded by the operator
in the deal's notes alongside the dossier until the runner carries them.

## 5. Handoff

- anduin TC: preview only — save in anduin after review
  (`included_api10s` = the buildup CSV, minus any culled wells).
- narvi scenario: generated benches are previews — build + save in narvi.
- Forecast to finance: Michael's call per bench; the Blue Ox drop follows
  the `blueox-curve-drop` skill.
