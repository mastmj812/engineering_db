# PDP-proximity study — step 1: precedent atlas (Delaware) — AT GATE 1

Built 2026-10-19 by `python -m scripts.box_prox_study` (133 s, read-only; nothing written to the warehouse).
Code: `box/prox_study.py` (pure), `box/prox_study_report.py`, tests `tests/test_box_prox_study.py`.
Page: `atlas.html` (serve docs/box via the `box-static` launch config, :8766).
Plan of record: the session plan "PDP-proximity study → drillability screen on PUDs".

## 1. What was measured
- **Children.** 25,889 Delaware producing horizontals with first production ≥ 2016, landing TVD known,
  lateral ≥ 1,000 ft, BOX exclusions dropped.
- **Candidates.** Every producing horizontal in the Delaware bbox, any vintage: 34,026.
- **Pair metric.** Deal-intake v14's own, applied child-relative:
  - overlap = share of the CHILD's lateral that the older well spans, ≥ 30 %;
  - gap = median perpendicular distance over that shared span;
  - dz = parent TVD − child TVD.
  
  The test suite holds it to deal-intake's `ProximityRule`: on every Chevron-fixture leg it gives the same cull set, with gap within 15 ft and overlap within 0.03.
- **Depleting parent** (decision 2026-10-19): the older well came online **≥ 12 months** before the child.
  6–12 months = "young", reported separately. ≤ 180 d = co-dev and never counts.
- **Classes are by bench pool** (D42: WCA_1 / WCA_2 / WCXY are one pool):
  - same = same pool, the horizontal-spacing case;
  - topfill = parent deeper;
  - underfill = parent shallower.
- **Excluded by default:** permit-round TVDs (rule 10), and shielded parents (sql/50's rule: a co-developed other-pool well in between).
- **Reconciliation vs sql/50 `dev_scenario`:** 97.7 % of children agree on "has a vertical parent" under the nearest equivalent gate. The misses concentrate in WCA_1 / WCA_2 / WCXY (92.6–97.0 %) because sql/50 treats WCA_1 under WCA_2 as a vertical parent, while we pool them as same-bench. Elsewhere agreement is 98.6–100 %.

## 2. Headline: precedent is NOT rare
**1,964 of 25,889 drilled wells (7.6 %) sit inside the v14 rectangle (300 ft vt / 800 ft hz) of a ≥ 12-month-old parent.**
Including permit-TVD and shielded parents raises that to 2,078. Another 538 children sit that close to a 6–12-month-old producer.

| v14 violators by class (children) | n | parent age at child FP, median (P10–P90) | parent cum at child FP, median |
|---|---:|---|---:|
| same pool (horizontal infill) | 1,279 | 3.2 yr (1.2–9.3) | 40.8 kbbl / 1,000 ft |
| topfill | 336 | 3.7 yr (1.2–10.2) | 38.3 kbbl / 1,000 ft |
| underfill | 442 | 4.4 yr (1.2–10.4) | 38.4 kbbl / 1,000 ft |

These are genuinely depleted parents, roughly 400 kbbl already out of a 10,000-ft lateral, not co-development.
The share is steady by vintage: 4.2 % (2016), 7–9 % every year 2017–2026. It is a sustained practice, not something that faded out.

Same-pool horizontal, cumulative children by gap to the nearest ≥ 12-month parent:

| | ≤ 800 ft | ≤ 1,400 ft | ≤ 2,640 ft |
|---|---:|---:|---:|
| NM (12,147 children) | 556 (4.6 %) | 1,762 (14.5 %) | 3,679 |
| TX (12,238) | 805 (6.6 %) | 2,474 (20.2 %) | 5,044 |

## 3. BS3_S over WCA — your specific worry
- **Drilled examples.** 170 of 2,432 BS3_S wells (7.0 %) violate v14. 105 of them are topfills, almost all over WCA_1 (54), WCA_2 (39) or WCXY (9). At 300 / 1,400 ft the count is 509 (20.9 %), 271 of them topfills.
- **Uptake, i.e. revealed preference.** Take WCA_1 parents that came online by mid-2022, so they've had ≥ 4 years to be infilled, and that have BS3_S development within 2 mi:

  | rule | WCA_1 parents that later got a BS3_S topfill inside it |
  |---|---:|
  | 300 / 800 | **1.8 %** (57 of 3,107) |
  | 300 / 1,400 | 5.0 % |
  | 1,000 / 2,640 | 15.3 % |

  WCA_2 parents: 1.7 % at 300 / 800. WCXY parents: 0.9 %.

  For comparison, at 300 / 800:
  - same-pool WCA infill: 3.6–5.7 %;
  - WCA_1/WCA_2 *under* a BS3_S parent: 3.5–4.5 %;
  - BS2_S same-bench: 5.0 %.

  **Close-in BS3_S over WCA is the least-taken of the common close geometries, but it has been done about 100 times.** That is enough to measure performance in step 2 at coarse bins.

## 4. What this means for the cull rule
- **The "no precedent" leg will not bind at 300 / 800 for the main benches.** Thousands of drilled examples exist, about 100 even for BS3_S over WCA. It will bind only for thin bench pairs and for the tightest cells (e.g. < 200 ft vt and < 400 ft hz). So the cull decision rests on **step 2 performance**: how those ~2,000 wells actually produced against what BOX would have forecast.
- **Survivorship still applies.** These are the infills operators chose to drill. If they show a large haircut, the undrilled PUDs are worse. If they show none, that is weak evidence for the undrilled population.
- **Uptake gives a second, performance-free signal.** Operators skip about 98 % of close-in BS3_S-over-WCA opportunities, against roughly 95 % of same-bench ones.

## 5. Gate-1 asks
1. **Definitions OK?** Child-share overlap ≥ 30 %, median gap, parent ≥ 12 months, WCA pool as one bench, permit-TVD and shielded parents excluded.
2. **Precedent floor for gate 3.** I propose a geometry cell counts as "precedented" with ≥ 30 drilled children for that bench-pair class. Below that the cull applies regardless of performance. The final number is your call at gate 3.
3. **Step-2 design.**
   - Yardstick: child actual ÷ BOX `box_v2` raw forecast at the child's location, as of Dec 31 of the year before its first production, with the child itself excluded from the analogs.
   - Population: children with ≥ 12 months of production and first production 2019–2025, about 15k wells (all of them, so the no-parent wells are the control).
   - Metrics: cum-12/24/36 oil, plus GOR-12/24.
   - Estimated runtime: several hours at `--workers 6`.
   - Alternative: score only the wells with a parent inside 1,000 vt / 2,640 hz plus a matched 2× control sample, which would roughly halve the runtime.
4. **Midland.** Not built (Delaware first, per kickoff). Running it is one flag if you want the comparison.

## 6. Caveats
- dz uses one landing TVD per well. Typical error is ±50–100 ft, so the 100–200 ft rows are soft.
- Overlap and gap use the lateral line rule (LP → BHL), and laterals are assumed straight between survey nodes. U-turn laterals read as chords (the known D56 gap).
- The uptake denominator ("child bench developed within 2 mi") is a coarse proxy for "a target there". It includes rock where operators may have rejected the bench for reasons other than proximity.
