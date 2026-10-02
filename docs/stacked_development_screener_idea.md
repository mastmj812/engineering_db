# Stacked-development response screener — idea note

**Status: idea, not scheduled.** Written 2026-09-09 to capture the design behind an ad-hoc
query so it can be productized later. Nothing here is built; the prototype ran once as a
read-only psql session.

## What it is

A reusable screen that, around an area of interest, finds examples of stacked-pay
development sequencing and compares the production response of the later ("child") wells
against the earlier ("parent") level of development. Three scenario families, all
parameterized from the same matching engine:

| Scenario | Child vs parent geometry | Example |
|---|---|---|
| **Topfill** | child lands ABOVE existing development (child TVD < parent TVD) | BS3_S drilled over produced WCA_1 / WCXY / WCA_2 |
| **Underfill** | child lands BELOW existing development (child TVD > parent TVD) | WCB / WCC under a produced BS + WCA stack |
| **Child / infill** | same bench (or same bench ±150 ft TVD), lateral offset within same-bench spacing | classic parent-child depletion interference |

The intent is not just to list pairs — it is to **observe the production response**:
how do child wells perform relative to the parent-era wells they sit against, and
(optionally) does parent production respond when the child comes online.

## Inputs

- **AOI**: a shapefile (.zip) or .gpkg of interest, or a drawn polygon. Basin-wide runs
  (like the prototype) are also valid — the AOI is a filter, not a requirement.
  - Convention question to settle before building a UI: erebor's rule of record is that
    uploaded deal geometry is **display-only** and never auto-selects wells (CLAUDE.md
    rule 13). Using an uploaded shape as the *query window* of a screener is a deliberate,
    different semantic — it should be decided explicitly, not slipped in.
- **Scenario spec** (all defaults from the 2026-09-09 prototype):
  - child bench set / parent bench set (`formation_blueox` codes, never raw formation)
  - TVD relation per scenario family (above / below / same ±150 ft)
  - corridor half-width for co-extent overlap: **±660 ft** default (spacing-scale, catches
    offset-stacked wells; ±150 ft is the tighter reconciliation corridor if "directly
    overhead" is wanted)
  - min overlap fraction of the CHILD lateral: **≥ 30 %** (narvi in-unit membership rule)
  - first-prod gap threshold: **≥ 1 yr** default; "clean" = EVERY overlapping parent is at
    least that much older (so a co-developed sibling disqualifies), "mixed" = at least one
  - hygiene: lateral ≥ 3,000 ft both sides, TVD non-null, same basin

## Matching engine (conventions of record — do not re-derive)

- **Co-extent overlap, never min-distance** (CLAUDE.md rule 9): overlap = length of the
  child lateral inside the parent's corridor / child lateral length. Min distance
  false-positives on end-to-end laterals across section lines.
- Source: `curated.producing_reference` for both sides (geom + prebuilt ±150 ft corridor +
  TVD-corrected `formation_blueox` code + first_production_date, GiST-indexed). Wider
  corridors are buffered on the fly after a geometry `ST_DWithin` prefilter (~0.0025°)
  that the geom GiST serves.
- Grain: producing wells; api10 keys; calendar `first_production_date`.

## Response metrics (the actual point)

Two distinct questions — keep them separate in the output:

1. **Child performance vs parent-era baseline**: child wells' per-1,000-ft normalized
   cum (oil, calday basis) at 3 / 6 / 12 / 24 months-on-production vs the SAME metric for
   the parent wells they overlap (and/or the parent-bench cohort in the AOI). Source:
   `curated.production_normalized` (already per-1,000-ft, cohort-keyed). Degradation
   ratio = child cum/ft ÷ parent cum/ft at matched MoP.
2. **Parent interference read** (optional second pass): parent wells' rate trajectory
   around the child's first-prod month — a rate step-change at child frac/first-prod is a
   frac-hit / repressurization signature. Needs care with downtime months.

Alignment for the screen is plain months-on-production; if any output graduates into
type-curve work, the `peak_ramp` alignment convention of record applies.

## Prototype (2026-09-09 BS3_S topfill screen, Delaware)

Parameters: child = BS3_S; parents = WCA_1, WCXY, WCA_2; ±660 ft corridor; overlap ≥ 0.30;
parent deeper; gap ≥ 1 yr; ll ≥ 3,000 ft. Results: **141 clean topfill** BS3_S wells,
86 mixed-timing, 1,302 stacked at all (of 3,119 BS3_S producers). Heavy EOG / Devon /
Exxon, mostly 2023–2026 child vintages over 2016–2024 Wolfcamp. Known data caveat: a few
pairs showed implausibly small vertical separation (~82–350 ft) — likely formation-tag or
TVD issues; the NM planned-survey trust flag (rule 15) also applies to fresh child TVDs.

Query skeleton (ran ~7 s basin-wide on the 6543 pooler, read-only, temp tables in a
rolled-back transaction):

```sql
WITH b AS (  -- child bench(es)
  SELECT api10, geom, tvd, first_production_date AS fp, operator, ll_ft
  FROM curated.producing_reference
  WHERE code = 'BS3_S' AND basin = 'delaware' AND ll_ft >= 3000 AND tvd IS NOT NULL
), w AS (    -- parent bench(es)
  SELECT api10, geom, code, tvd, first_production_date AS fp, operator, ll_ft
  FROM curated.producing_reference
  WHERE code IN ('WCA_1','WCXY','WCA_2') AND basin = 'delaware'
    AND ll_ft >= 3000 AND tvd IS NOT NULL
)
SELECT b.api10, w.api10, w.code,
       o.overlap,
       (b.fp - w.fp) / 365.25 AS gap_yr,
       ST_Distance(b.geom::geography, w.geom::geography) * 3.28084 AS lateral_offset_ft
FROM b
JOIN w ON ST_DWithin(b.geom, w.geom, 0.0025)   -- geom GiST prefilter, ~700-800 ft
      AND w.tvd > b.tvd                        -- topfill: parent below (flip per scenario)
CROSS JOIN LATERAL (
  SELECT ST_Length(ST_Intersection(b.geom,
           ST_Buffer(w.geom::geography, 201.17)::geometry)::geography)
         / NULLIF(ST_Length(b.geom::geography), 0) AS overlap
) o
WHERE o.overlap >= 0.30;
-- then aggregate per child well; clean topfill = MIN(gap_yr) >= 1.0 over its parents
```

AOI variant: add `AND ST_Intersects(b.geom, ST_SetSRID(ST_GeomFromGeoJSON(:aoi), 4326))`
(and the same on `w`, or let parents come from the corridor join alone).

## Where it could live (open)

- **erebor** is the natural UI home (read-only warehouse discipline, AOI draw + gpkg
  upload + gunbarrel + charts already exist) — a "Stacked" tab or a mode of Highgrade.
- Or start as a parameterized script in `engineering_db/scripts` (pairs + well-level CSV
  out) and defer the UI until the response-metric definitions have been used in anger.
- If it becomes an endpoint, the read-only transaction-GUC pattern and
  whitelist-then-interpolate SQL rules apply as usual.

## Open questions

- AOI-as-query-window vs the display-only upload convention (rule 13) — needs an explicit
  decision of record.
- Baseline definition for "parent level of production": the overlapped parents only, or
  the whole parent-bench cohort in the AOI, or vintage-matched parent analogs? (The first
  is cleanest; the last controls for completion-era drift.)
- Same-bench "child" scenario needs a lateral-offset band (e.g. 300–1,320 ft) instead of
  an overlap-only test, plus the `lateral_closer_xy_ft` as-of-first-prod semantics and the
  2800-ft no-neighbor sentinel (rule 14) if Novi spacing is brought in.
- Whether the parent-interference read (frac-hit detection) is in scope for v1 at all.
