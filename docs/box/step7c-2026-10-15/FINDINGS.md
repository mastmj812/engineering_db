# BOX step 7c: production run of the frozen analog workup, gate 7

**Built 2026-10-15. The forecast is computed and stored as the record ONLY in a throwaway PostGIS container. Nothing is written to
Supabase.** Review surface: `index.html` (run summary, coverage, haircut, F(k), disclosure, all 624 pads) and six sample pad pages
under `workups/`. The full 624-page set is in `runs/box7c/workups` (12 MB, git-ignored; see ask 5).
Code: `box/production.py`, `box/production_pages.py`, `scripts/box_pud_run.py` (`build` / `annotate` / `store` / `render`),
`tests/test_box_production.py` (19 tests).

## 1. What ran

- **Method = the frozen spec `box_v2_wf` (D58), unchanged.**
  - The analog pool is built the way the D53 harness built it, at a production cutoff of 2026-08-01 (production through
    2026-07-01, the same as every acceptance run): the gate-1 WCA well set (exclusions applied), boxfit 3380317 per-well fits,
    D56 completed laterals and the D55 strike search. That's 12,214 pool wells.
  - Each covered location gets the box_v2 cohort **P50** per stream (oil, gas), scaled to its Novi planned lateral (Cui & Cross
    below 7,500 ft, D50).
- **Equivalence (built into `build`):** the harness's own `predict_location_v2` was re-run at 600 months on 24 sampled
  locations. Its monthly volumes are **identical** to the production path's (max relative difference **0.0**). The record
  run is the accepted method itself, not a re-implementation of it.
- **Provenance:** built from committed code **95151af** (clean code paths). The nearest-neighbour annotation that feeds the
  review flags only came from **d3a45ff**. It reproduced every stored planned gap exactly before it was allowed to write.
- **D62 haircut** (package-weighted box_v2 bias, every tuning + holdout cell with ≥ 30 packages, applied to cumulatives,
  cum-48 held to month 600):

| stream | cum-12 | cum-24 | cum-36 | cum-48 (= EUR factor) |
|---|---|---|---|---|
| oil | 0.943 | 0.929 | 0.916 | 0.876 |
| gas | 1.002 | 1.021 | 1.019 | 1.059 |

  Gas factors sit above 1 because box_v2 historically forecast gas slightly LOW (+0.2 … +5.9 %). The correction raises it.
- **D63 F(k) (published, not applied):** oil 0.895 / 0.908 / 0.910 / 0.921, gas 0.918 / 0.945 / 0.955 / 0.980 at months
  12 / 24 / 36 / 48. Calibrated exactly as the harness does: seeded 500-well sample, as-of cohorts.
  **Caveat to state on the delivery:** the haircut was measured on CALENDAR predictions (F applied). Delivering uptime-free
  volumes × haircut is right when Steven's own downtime factor plays F(k)'s role.

## 2. Results (container record, run 9)

| coverage | rows |
|---|---|
| covered | **1,929** |
| not_covered_no_analogs | 5 |
| not_covered_outside_extent | 1,491 |
| not_covered_wcxy | 3,408 |
| not_covered_unvalidated (BS2_S) | 15,122 |
| not_covered_emerging (DE WDFD + MID BRNT) | 11,207 |
| **universe** | **33,162** |

**Identity:** covered 1,929 + no_analogs 5 = 1,934 = the in-extent WCA_1 + WCA_2 universe, exactly.
- Every stream has 600 monthly rows summing to its EUR within 0.1 % (3,858 / 3,858).
- Every covered location names 6–20 analogs.
- Re-storing the same vintage reuses all 33,162 location ids.
- `--record` refuses a dirty build and supersedes the previous record cleanly.

**Forecast per covered location** (haircut applied, uptime-free, raw 50-yr technical EUR, no economics):

| | P10 (low) | median | P90 (high) |
|---|---|---|---|
| oil EUR per 1,000 ft (bbl) | 47,662 | **66,403** | 93,547 |
| gas EUR per 1,000 ft (mcf) | 119,670 | 295,333 | 543,312 |
| oil cum-12 per location (bbl) | 123,522 | 197,745 | 304,907 |
| oil P50 Di, nominal /yr (1-yr effective) | 2.23 (68 %) | 3.22 (76 %) | 4.00 (80 %) |
| oil b | 0.92 | 1.01 | 1.12 |

(The P10 / P90 columns here are percentiles across locations, ascending for readability; not the SPE high/low case.)

- **Totals:** 1,162 MMbbl oil and 5.57 Tcf gas across 1,929 locations (mean lateral 9,217 ft). That's a technical volume only.
- **Context:** the median EUR/kft of 66,403 sits next to the retired area curves' median of 65,731 bbl/kft (a mean curve,
  pre-haircut), so the two methods land in the same place regionally.
- **Search:** 1,436 locations found their analogs in the 5-mi ring. 493 went past it (238 on the D55 strike ellipse);
  35 reached the 20-mi cap. 524 locations have laterals under 7,500 ft and were Cui-translated.
- **D64 planned spacing:** median 877 ft. 52 locations have no same-formation neighbour within 2,800 ft, so they use the
  880-ft default.

**Fixed during the build (reported, so you know the first artifact isn't the record):**
1. D64 first pooled WCA_1 with WCA_2 neighbours, which read vertical staggering as 11–300 ft "gaps". It's now same-formation
   only. The change moved 7.8 % of locations' EURs; the median change is 0.
2. The build first stamped the wrong code SHA (`main`, checked out mid-run, which didn't contain the builder). It's now
   captured at start, and untracked files count as dirty.
3. A store identity query hit a 37-min nested-loop plan once 4.6 M month rows existed. It now analyzes the tables, then does
   one grouped pass (28 s for the full store).

## 3. Review flags (stored in `pud_forecast.flags` and shown on the pad pages; the forecast is unchanged)

- **306 oil P50 fits at the Di cap** (4.0/yr nominal = 81.7 % 1-yr effective) and **67 with b at a bound**. These are cohort P50
  fits, the same kind the deal-intake drops carry. Per the operating rule they're flagged for review, never silently
  accepted, and never "fixed" by widening the bounds.
- **275 covered PUDs sit within 500 ft of an existing same-formation producer** (63 within 200 ft), every one of them a PDP well
  (none to another PUD). Reconciliation calls them remaining_pud (241) or conflict (34). A PUD that close is plausibly already
  drilled and missed by sql/20's overlap match, or Novi over-stating inventory (rule 11). They're flagged and forecast at that
  gap (the representative-spacing filter then leans to tightly spaced analogs).
- **5 not_covered_no_analogs = one pad**, Delaware Pad 548: five 23,560-ft (4.5-mi) WCA_2 laterals. The deal-intake lateral
  band around 23,560 ft finds no eligible WCA analog, even at 20 mi. This is a gap in the frozen spec at the long end. The short
  end has the Cui translation; the long end has nothing.

## 4. Asks for gate 7

1. **Go to store the record on Supabase:** `python -m scripts.box_pud_run store --record` from this artifact (built at 95151af).
   - It writes 33,162 locations + location_source rows, 1 run, 33,162 pud_forecast rows, 3,858 stream rows, 2.31 M monthly
     rows and the analog rows, in one transaction, with the identity checks above before COMMIT.
   - New box rows only; about 30 s in the container.
   - Then the plan Status line and the memory note.
2. **Pad 548 (5 × 23,560-ft laterals).** Recommendation: **leave it as `not_covered_no_analogs`** (D74: counted, visible) and
   hand-work it if it matters. The alternative is a long-lateral translation (analogs 10–15k ft, Cui extrapolated past
   12,500 ft). That's a change to the frozen spec, and it would need its own acceptance.
3. **The 275 PUDs near producers.** Recommendation: **keep them forecast and flagged**, and open a separate reconciliation
   check of the 63 within 200 ft against sql/20 (a warehouse question, not a BOX one). Don't drop them inside BOX.
4. **Bound-pinned fits (306 Di, 67 b).** Recommendation: **keep them with the flag**, consistent with D34 and the deal drops.
   They're review items on the pad pages.
5. **Workup pages.** Recommendation: **the DB is the record; the pages are renders.** Commit the index + samples only (the full
   624-page set is 12 MB). Step 8 renders the pad page from `box.pud_forecast` / `location_analog` on demand, and
   `workup_ref` stays `pad:<name>` as the key.
6. **Steven (D63):** confirm before the first delivery that his downtime factor applies to the uptime-free volumes, and note the
   haircut caveat (§1). This carries into 7d.
