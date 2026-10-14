# Scope — a 3-D well-spacing measure for BOX (not built; warehouse work needs a go-apply)

Michael 2026-10-12: "lateral distance to neighbor was often a very strong feature" in his Novi-platform ML work. Step 6
showed our two coarse proxies don't carry it, so this scopes a geometry-true measure.

## 1. What we have, and why it isn't enough

| Source | What it is | What step 6 found |
|---|---|---|
| `curated.codev_context` (sql/47) | co-extent neighbours within 1,320 ft (≥ 30 % overlap, rule 9), per **bench** aggregates: counts by relation, median distance / dtvd, nearest parent offset, nearest codev dtvd | "near neighbours within ±500 ft TVD" multiplier stable in training (6+ = 0.92–0.94) but over-corrects out of sample (backtest §5c) |
| `raw_novi."WellSpacing"` (3 of 11 columns passed through by sql/49) | Novi's as-of-first-production scalars: ClosestWellXY, WellsInRadius, ClosestTwoAvgXY, WellsInRadiusAvgXY, LateralCloserXY, StaggerCloserTangent, StackCloserZ (capped 1,000 ft on ~72 %), BoundednessScore, IsChild, ParentCount, ParentDaysOnline; coverage 96 % of WCA wells | no tight-spacing penalty on level (same-bench < 660 ft ≈ 1.00–1.04); ~nothing on decline shape (shape dig §2: year drift unchanged when added) |

Common limits: nearest-only scalars or per-bench aggregates; vertical position collapsed to one number per bench (or capped);
no drainage geometry (how much rock a well "owns"); no depletion (how much a parent had produced, not just that it existed).
The pair-level facts sql/47 computes internally (distance, dtvd, timing per neighbour) are aggregated away.

## 2. Proposed measure

**Pair table** `curated.well_neighbors` (matview; UNIQUE (api10, nbr_api10)): every producing horizontal × every co-extent
neighbour (any bench) within a 2,640-ft candidate gate (geography index, sql/26 pattern; EXPLAIN-asserted):

- `overlap_frac` — neighbour lateral projected on the subject lateral (sql/47's ST_LineLocatePoint span, rule 9);
- `dxy_ft` — **mean perpendicular offset over the overlapped span** (gunbarrel offset, not min distance), signed by the
  sign rule v2 frame so left / right is consistent (rule 16; `dealintake/geo.positive_offset_bearing` is the copy to reuse);
- `dz_ft` — neighbour TVD − subject TVD (v1: one TVD per well; v2 option: survey TVD along the overlapped span);
- `d3_ft` = √(dxy² + (a·dz)²) with an anisotropy factor a (frac height vs half-length; start a = 2, calibrate);
- timing: `dfp_days`, relation parent / codev (±180 d) / child; parent cum oil + gas **at the subject's first production**
  (curated.production) — the depletion the subject actually saw.

**Per-well features** `curated.well_spacing_3d` (as of first production; children excluded so it is causal):

- nearest neighbour left / right (same ±Z window) and above / below (dz), with their relation;
- `drainage_xsec_ft2` — the well's cell area in the gunbarrel cross-section (2-D Voronoi of the overlapped neighbours in
  the (dxy, a·dz) plane, bounded at the candidate gate): rock per well, the single number closest to "spacing";
- counts and Σ parent cum (per 1,000 ft of subject lateral) inside the anisotropic ellipse (e.g. 660 ft × 300 ft);
- boundedness: sides with a neighbour inside the gate (0–4).

**PUD side.** The same function runs on planned sticks (Novi locations now, BOX placement later) with *planned*
co-development, so a PUD is forecast at the spacing we would plan — Michael's "don't forecast ludicrous development".

## 3. How we would test it (before any decision of record)

1. Rolling-origin backtest (backtest/): add a variant with the drainage area + parent-depletion terms (PPML, training
   only), compare next-year bias / band against base and `lat`; Novi WellSpacing features as a head-to-head variant.
2. Shape: add the features to the shape-drift model (shape/) — do they absorb the residual ~8 % 2024-vs-2018 drift?
3. Case checks: Burton Flat 3 1 (WCA_1 ~13-well cube), one wide-spaced legacy unit.

## 4. Effort and order

| Piece | Work | Gate |
|---|---|---|
| sql/59 `well_neighbors` + `well_spacing_3d` (extend sql/47's pair join rather than a second spatial join) | 1 session; apply script with row-count identity + EXPLAIN index names; ~1.5 M pair rows Permian-wide (est.), build tens of minutes | **go-apply** (warehouse-change skill) |
| Backtest + shape variants | 1 session, read-only | your review |
| Decision of record (factor term, PUD application) | — | your call |

Open choices for you: single TVD vs survey TVD (v1 single); anisotropy a and ellipse size (start 2 / 660 × 300 ft,
calibrate in the backtest); whether the pair table covers all Permian horizontals (needed for PUD use later) or WCA + BS2_S
first.
