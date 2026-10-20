# PDP-proximity study — steps 1, 2, 2b, 2c (Delaware) — GATE 2c DECIDED (option a); precedent unit + shielding open

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

## 7. Gate 1 decided (Michael, 2026-10-19)
Accepted as written:
- the §1 definitions;
- the precedent floor of **≥ 30 drilled children per geometry cell per bench-pair class** (below that the cull applies regardless of performance);
- step 2 runs on **all** ~15k children, first production 2019–2025 with ≥ 12 months produced, with the no-parent wells as the control.

---

# Step 2 — dose-response vs the as-of BOX forecast (AT GATE 2)

Built 2026-10-20 by `python -m scripts.box_prox_study dose` (11 s, DB-free).
- Code: `box/prox_dose.py` (pure) and `box/prox_dose_report.py`, with tests in `tests/test_box_prox_dose.py`.
- Page: `dose.html`. Tables: `dose_*.csv`. Per-child drill-down: `dose_children.csv.gz`.

## 8. Method
- **Yardstick.** Each child's actual ÷ the `box_v2` RAW forecast made at its harness fold cutoff (Dec 1 before its first production). The analogs first produced before the cutoff, so the child is never its own analog.
- **Source of the forecasts.** The harness's own per-well views: the step-11/12a input set, tuning plus the once-scored holdout, all 13 BOX bench groups, sha256-verified against their digests. Our ln(actual/pred) matches the harness's stored `box_v2_err` to ≤ 1.8e-15 on every row, so these are the harness forecasts.
  - WCXY wells were scored in both the WCA guard pool and WCXY_WCA1. The WCXY_WCA1 row wins (D93/D97).
  - AVA_0/1/2 and BS2_C have tuning folds only (D105), so their holdout-block wells are absent.
- **Population.** 14,545 scored children with first production Dec 2019–Nov 2025 (tuning 10,638 + holdout 3,907):

  | group | wells | share |
  |---|---:|---:|
  | exposed (a ≥ 12-mo parent within 1,000 ft vt / 2,640 ft hz) | 8,818 | 61 % |
  | control (no parent there) | 3,971 | 27 % |
  | young parent only (6–12 mo) | 1,148 | 8 % |
  | permit-TVD or shielded parent only | 608 | 4 % |

  Each exposed child is placed by its worst depleting parent, using the gate-1 definitions.
- **Statistic.** Geometric-mean actual/pred, normalized by the controls of the same bench group and cutoff, so BOX's own bench and vintage bias cancels. **1.00 = produces like an unexposed well; 0.80 = a 20 % haircut BOX doesn't see.**
  - 90 % 3-mi block-bootstrap intervals, 500 draws, with the baselines re-estimated in every draw.
  - `*_vs_box` = the same cell against BOX as-is. Controls run 0.93 / 0.92 / 0.90 at cum-12/24/36 there, which is box_v2 raw's known high bias (D57/D58 tuning −7…−9 %; the walk-forward haircut corrects it on validated benches).
- **Survivorship.** Every cell is an operator-selected infill, so it is an upper bound for the undrilled PUDs at that geometry.

## 9. Results — oil, typical child vs an unexposed well (cum-12 / cum-24 / cum-36)

**Same pool (horizontal infill).** A clean monotone curve that is gone by ~1,400 ft, which matches your southern-Delaware read:

| gap to ≥ 12-mo parent | n (cum-12) | cum-12 | cum-24 | cum-36 | GOR-24 |
|---|---:|---|---|---|---|
| 0–400 ft | 143 | 0.77 [0.71–0.83] | 0.80 [0.74–0.86] | 0.84 | 1.08 |
| 400–800 | 563 | 0.85 [0.82–0.88] | 0.86 [0.83–0.90] | 0.86 | 1.05 |
| 800–1,400 | 1,602 | 0.89 [0.87–0.92] | 0.90 [0.87–0.92] | 0.89 | 1.03 |
| 1,400–2,000 | 1,220 | 0.98 [0.95–1.00] | 0.98 | 0.97 | 1.01 |
| 2,000–2,640 | 918 | 1.02 | 1.00 | 0.99 | 1.00 |

TX is steeper close in than NM: at 0–400 ft, cum-12 is TX 0.66 vs NM 0.87. GOR rises 5–8 % inside 800 ft, a depletion signature.

**Topfill (parent below).** The haircut is about 20 %, it does NOT shrink with vertical gap until ~800 ft, and it doesn't fully recover horizontally by 2,640 ft:

| vertical gap (hz ≤ 800) | n | cum-12 | cum-24 | cum-36 |
|---|---:|---|---|---|
| 0–100 ft | 39 | 0.89 [0.75–1.04] | 0.84 | 0.87 |
| 100–200 | 48 | 0.72 [0.62–0.82] | 0.82 | 0.83 |
| 200–300 | 79 | 0.77 [0.67–0.89] | 0.83 | 0.85 |
| 300–500 | 157 | 0.78 [0.73–0.86] | 0.79 | 0.81 |
| 500–800 | 268 | 0.81 [0.75–0.88] | 0.77 | 0.79 |
| 800–1,000 | 142 | 0.93 [0.84–1.05] | 0.96 | 1.02 |

| horizontal gap (vt ≤ 300) | n | cum-12 | cum-24 | cum-36 |
|---|---:|---|---|---|
| 0–800 ft | 166 | 0.78 | 0.83 | 0.85 |
| 800–1,400 | 190 | 0.88 | 0.89 | 0.92 |
| 1,400–2,640 | 275 | 0.94 | 0.90–0.91 | 0.91 |

**Underfill (parent above).** Milder: about −10 % within 1,400 ft horizontally (vt ≤ 300). The worst vertical bin is 300–500 ft (cum-24 0.85, cum-36 0.85), and from 500 ft vertical down it's ≈ 1.0.

**BS3_S over WCA (inside v14).**

| case | n (cum-12 / 24 / 36) | cum-12 | cum-24 | cum-36 |
|---|---|---|---|---|
| BS3_S over WCA_1 | 35 / 26 / 16 | 0.67 [0.55–0.84] | 0.76 [0.59–0.97] | 0.87 |
| BS3_S over WCA_2 | 19 / 15 / 10 | 0.80 | 1.00 | 1.03 |
| WCA *under* a BS3_S parent | 55 / 43 / 35 | 0.74 | 0.74 | 0.78 |

- The WCA_2 row is thin and noisy.
- **The penalty runs both directions between BS3_S and WCA.**

**Other reads.**
- **Young parents (6–12 months) barely matter:** 0.96 / 0.97 / 0.99. That supports the 12-month cutoff.
- **Permit-TVD or shielded-only children still show 0.92**, so shielding by a co-developed well in between does not clear the haircut (n = 515 at cum-12).
- **The parent-depletion dose isn't monotone** within v14. By parent cum, 0–20 kbbl/kft reads 0.76 at cum-24 and ≥ 60 kbbl/kft reads 0.91. By parent age, 2–4 yr is worst at 0.81. The geometry carries the signal; the parent's cum doesn't add to it.

**The v14 rule as written (300 / 800).**
- Inside it: same pool 0.85, topfill 0.83, underfill 0.92 (cum-24).
- It **misses topfills 300–800 ft above a parent**, which are as bad as inside (0.77–0.79).
- It keeps same-pool 800–1,400 ft (−10 %).

## 10. Gate-2 asks (they set up the gate-3 rule)
1. **Accept the method?** That covers the yardstick (harness views), control normalization, survivorship framing and the young-parent cutoff validated at 12 months.
2. **Which haircut defines "undrillable"?** The precedent floor (30 per cell) doesn't bind anywhere below; every cell named has n ≥ 39. Two candidate cuts, both at cum-24 and relative to an unexposed well:

   | cut | same pool | topfill | underfill |
   |---|---|---|---|
   | **≥ 15 % (≤ 0.85)** — recommended | gap < 800 ft (400–800 is borderline: 0.85–0.86) | vt ≤ 800 AND hz < 800 | no cull (300–500 vt flagged) |
   | **≥ 10 % (≤ 0.90)** | gap < 1,400 ft | vt ≤ 800 AND hz < 1,400 | vt ≤ 500 AND hz < 1,400 |

   I recommend ≥ 15 %. These are the infills operators *chose* to drill, so an undrilled PUD at that geometry would do worse still, and a 15 % haircut on the best case is already the "wouldn't drill it" line. The ≥ 10 % line culls a lot of same-pool 800–1,400 ft spacing that operators routinely drill.
3. **Shielding.** Shielded and permit-only children still lose 8 %. Keep the shielding exemption, or count shielded parents for the PUD cull?
4. **Step 4 next.** Measure every run-10 PUD against the chosen rule (cull counts per bench, the BS3_S share, a crosstab with Novi Tier-4). Read-only.

## 11. Gate 2 — Michael's answer (2026-10-20)
- "Undrillable" means uneconomic. His rough floor is ~50 bo/ft of 50-yr raw EUR. But that floor varies by bench AND by Steven's price deck, so **no bo/ft floor enters our logic** (the scope rule stands).
- **The cull is a FIXED haircut, looked up by configuration.** A PUD with several depleted parents must never get the step-2 average, which lone single-parent tests diluted.
- That led to step 2b.

---

# Step 2b — haircut by configuration (AT GATE 2b)

Built 2026-10-20 by `python -m scripts.box_prox_study config` (DB-free, seconds).
- Code: `box/prox_config_report.py`, plus `prox_dose.configuration`. The signed parent side was added to the step-1 pair metric (`prox_study.pair_signed`, `Link.dxy_ft`).
- Page: `config.html`. Tables: `config_*.csv`. Per child: `config_children.csv.gz`.
- **Re-check:** the step-1 re-run with sides reproduced every atlas CSV byte-for-byte; only timestamps changed.

## 12. Method
- **Class envelopes** (where step 2's effects faded):

  | class | envelope |
  |---|---|
  | same pool | 1,400 ft hz |
  | topfill | 800 ft vt / 1,400 ft hz |
  | underfill | 500 ft vt / 1,400 ft hz |

  Parents use the gate-1 filter: ≥ 12 mo, ≥ 30 % alongside, no permit TVD, not shielded.
- **Configuration** = the class (or *mixed* when parents sit in 2+ classes) × parent count (1 / 2 / 3+) × the nearest parent's geometry band. **Flanked** = parents on both sides of the child; a parent within 100 ft counts for both.
- **Haircuts are against BOX's calibrated level.** Each child's ln(actual ÷ as-of box_v2) minus the mean of ALL scored children of its bench group and cutoff, which is the mix BOX's analogs and walk-forward calibration represent. So **0.80 = the well makes 80 % of what BOX forecasts.**
  - Unexposed controls sit at **1.05** on this scale. The old physical-effect number is kept as `oil24_vs_control`.
- **precedent_n** counts every Delaware well drilled since 2016 in that configuration, from the 25,889-well universe. The gate-1 floor of 30 applies to it.

## 13. Results — oil cum-24 vs BOX's level (cum-36 in parentheses; 90 % CI on cum-24)

| configuration | precedent | cum-24 | CI | cum-36 | vs unexposed |
|---|---:|---:|---|---:|---:|
| **Topfill** — 1 parent | 1,192 | 0.95 | 0.92–0.98 | (0.94) | 0.88 |
| topfill — 2 parents | 340 | 0.88 | 0.82–0.94 | (0.88) | 0.77 |
| topfill — 3+ parents | 283 | **0.77** | 0.68–0.86 | (0.79) | 0.69 |
| topfill — 2+ **flanked** | 493 | **0.79** | 0.73–0.85 | (0.80) | 0.70 |
| topfill — 2+ one side only | 130 | 0.95 | 0.85–1.05 | (0.97) | 0.84 |
| **Same pool** — 1 parent | 2,691 | 0.95 | 0.93–0.96 | (0.95) | 0.90 |
| same — 2 parents | 631 | 0.93 | 0.90–0.97 | (0.93) | 0.89 |
| same — 3+ parents | 223 | **0.85** | 0.81–0.91 | (0.81) | 0.82 |
| same — 2+ flanked | 322 | 0.86 | 0.81–0.92 | (0.85) | 0.82 |
| **Underfill** — 1 parent | 857 | 0.96 | 0.93–1.00 | (0.95) | 0.93 |
| underfill — 2 parents | 270 | 0.89 | 0.84–0.94 | (0.85) | 0.85 |
| underfill — 3+ parents | 172 | 0.94 | 0.85–1.04 | (0.94) | 0.91 |
| underfill — 2+ flanked | 333 | 0.91 | 0.85–0.98 | (0.88) | 0.87 |
| **Mixed** — 2 parents total | 509 | 0.92 | 0.88–0.96 | (0.93) | 0.86 |
| mixed — 3 total | 319 | 0.84 | 0.80–0.89 | (0.83) | 0.80 |
| mixed — 4+ total | 277 | **0.78** | 0.72–0.85 | (0.77) | 0.73 |
| **BS3_S over WCA** — 1 parent | 227 | 0.96 | 0.90–1.03 | (0.95) | 0.88 |
| BS3_S over WCA — 2 parents | 64 | 0.83 | 0.66–1.00 | (0.87) | 0.76 |
| BS3_S over WCA — 3+ parents | 45 | **0.54** | 0.35–0.84 | (0.79, n=7) | 0.50 |
| BS3_S over WCA — 2+ flanked | 75 | **0.60** | 0.48–0.80 | (0.76) | 0.56 |

**What changed versus step 2.**
- **Parent count is the dominant variable.** A single parent costs about 5 % against BOX in every class. Most of step 2's "close-in" haircut came from multi-parent wells.
- **Flanking matters most for topfills.** Flanked topfills make 0.79 of BOX's forecast; one-sided topfills make 0.95.
- **Bench pair matters on top of count.** BS3_S over a flanking WCA DSU makes **0.54–0.60** of BOX, against 0.77–0.79 for topfills generally. The cells are thin: BS3_S 3+ is 14 wells at cum-24, CI 0.35–0.84.
- **Underfill stays mild** (0.89–0.96). GOR rises 16–19 % in the 2-parent cells, a depletion signature.
- **Precedent:** every pooled cell is above 30. BS3_S over WCA flanked has 75 drilled examples. Some geometry sub-bands fall below the floor (see `config_*.csv`, `below_floor`).

## 14. Gate-2b asks
1. **Lookup granularity.** I recommend a ladder: bench pair × parent count where precedent ≥ 30 (e.g. BS3_S over WCA), else class × parent count (+ flanked), else class. This mirrors D45. The geometry sub-bands are too thin to key on, so they stay as diagnostics.
2. **Horizon.** I recommend cum-24 for the haircut: most wells, tight CIs. cum-36 sits within ±0.04 everywhere it has n. Applying it to EUR assumes the haircut holds into the tail, which is untested beyond 36 months.
3. **The fixed cut X.** What each cut would cull:

   | X | culls |
   |---|---|
   | ≤ 0.80 | topfill 3+ and flanked; BS3_S over WCA 3+ and flanked; mixed 4+ |
   | ≤ 0.85 | the above, plus same-pool 3+, mixed 3, BS3_S over WCA 2 parents |
   | ≤ 0.90 | the above, plus topfill 2 and underfill 2 parents |

4. **Package dimension.** A PUD development IS a package. BS3_S over WCA with ≥ 2 parents AND ≥ 2 co-developed BS3_S siblings had **9** drilled examples (the 2026-10-20 probe), below the floor. Should the precedent test require the package configuration? If so, it culls full-DSU BS3_S topfill over developed WCA on precedent alone.
5. **Shielding** (open since gate 2). Shielded or permit-only children still lose 8 %.
6. **Next = step 4.** For every run-10 PUD: count its parents today with the same metric, look up the haircut, and apply X. Read-only, with cull counts per bench and a Tier-4 crosstab.

## 15. Gate 2b — Michael's answer (2026-10-20): DESIGN SWITCH
**PUDs get BOX × a configuration haircut, and Steven's econ does the culling.** Configurations without drilled precedent get no forecast. A haircut that becomes a forecast term has to predict out of sample, so step 2c validates it before anything else.

Defaults taken with his "yes":
- mean haircut, survivorship disclosed;
- cum-24 primary;
- a `none` factor for unexposed PUDs;
- precedent unit (parent configuration vs package) decided at this gate.

---

# Step 2c — walk-forward validation (AT GATE 2c)

- **Rule:** `PREREG_2c.md`, committed b20603d BEFORE scoring, together with the code. Scored once by `python -m scripts.box_prox_study validate` (DB-free).
- **Outputs:** `validate.html`, `validate_cells_*.csv`, `validate_children.csv.gz`, `validate_summary.json`, and `haircut_table_candidate.csv` (fit on all folds = what step 4 would read).

## 16. Verdict as pre-registered: **FAIL** (oil cum-24)

| test | result | rule | pass? |
|---|---|---|---|
| P1 — material-haircut wells (f ≤ 0.90, n = 668) | actual ÷ (BOX × haircut) = **1.060** [1.023–1.097]; no haircut 0.884 | 0.95–1.05 or CI contains 1 | **FAIL** — the haircut over-corrects by ~6 % |
| P2 — skill | RMS cell bias 0.038 with the haircut vs 0.074 without | must drop | PASS — halved |
| P3 — cell calibration | 18 of 21 cells within ±10 % (86 %) | ≥ 80 % | PASS |

Reported, not gating:

| metric | P1 | P2 | P3 | would-be verdict |
|---|---|---|---|---|
| oil cum-12 | 1.065 | pass | 70 % | FAIL |
| oil cum-36 | 1.036 [0.98–1.09] | pass | 79 % | FAIL (P3 by one cell) |
| gas cum-24 | 1.181 | **fail: the haircut makes gas worse** | 67 % | FAIL |

## 17. What drives the miss (diagnostics: POST-LOOK, not a pass)

**The configurations the haircut exists for hold out of sample.** Cell residual = actual ÷ (BOX × haircut), oil cum-24:

| cell | haircut | residual |
|---|---:|---:|
| topfill, 3+ parents, flanked | 0.74 | **1.04** |
| mixed, 3 parents | 0.83 | 1.01 |
| mixed, 4+ parents | 0.77 | 0.99 |
| same pool, 3+ parents | 0.83 | 0.96 |
| underfill, 2 parents | 0.85 | 0.99 |
| topfill, 2 parents, flanked | 0.87 | 0.96 |

Pooled over material multi-parent wells: **1.043** [1.003–1.088] at cum-24 (n = 464) and **1.005** [0.95–1.05] at cum-36 (n = 192).

**The miss is single-parent and thin bench-pair cells.** These are winner's-curse factors that sat low in training and regress toward 1 in test:

| cell | haircut | residual | n |
|---|---:|---:|---:|
| BS2_S same-bench, 1 parent | 0.87 | 1.08 | 121 |
| WCA under BS3_S, 1 parent | 0.87 | 1.35 | 22 |
| underfill 2 flanked | 0.80 | 1.36 | 19 |
| WCA same, 3+ | 0.86 | 1.19 | 24 |

Single-parent material wells pooled: 1.10 [1.04–1.16].

**Drift:** the material residual rises by test cutoff (2021: 1.02 → 2022: 1.08 → 2023: 1.10). Newer infills do relatively better than haircuts fit on older wells predict, consistent with operators adapting (completions, timing). Haircuts from older wells may overstate today's penalty. The prospective cohort is the check.

**Gas:** a fitted gas haircut over-penalizes (1.18). Depleted children lose oil more than gas; the GOR rises.

**`none` factor:** unexposed PUDs = 1.037 × BOX's mix level, residual 1.003 in test, so it is validated.

## 18. Gate-2c asks
1. **The verdict stands as FAIL as written.** Options, in the D59 manner (your call):
   - **(a) Accept with documented exceptions.** Adopt only the multi-parent haircuts: class × count ≥ 2 × flank, plus mixed 2/3/4+. Single-parent PUDs get no proximity haircut, with BOX left as-is. Oil only, no gas haircut. Disclosed basis:
     - multi-parent cells validated within ±5 % (cum-24 1.04, cum-36 1.01);
     - the single-parent miss was over-penalizing;
     - the narrowed spec is a post-look choice, so it is confirmed on the prospective 2026 cohort (first cum-12 ~2027-Q2).
   - **(b) Re-specify and wait.** Pre-register a narrowed or shrunk ladder now and validate it on the prospective cohort before any record use.
   
   **I recommend (a).** The cull-relevant configurations validated, the miss sits in small single-parent haircuts (0.93–0.97 at the class level), and BOX's record goes unhaircut there either way.
2. **`none` uplift (1.037).** Apply it to unexposed PUDs, or leave unexposed PUDs at BOX as-is? I recommend as-is under (a): one change at a time, and BOX's level is already walk-forward calibrated.
3. **Precedent unit** (still open from gate 2b): parent configuration (BS3_S over flanking WCA = 75 drilled → forecast at the haircut) vs package (with ≥ 2 co-developed siblings = 9 → no forecast).
4. **Shielding** (open since gate 2).
5. **Next = step 4.** Each run-10 PUD gets its configuration from today's producers, its haircut and its precedent class. Read-only counts and haircut EUR totals by bench, then the record-run decision.

## 19. Gate 2c decided (Michael, 2026-10-20): OPTION (a)
- **Haircuts applied:** only multi-parent configurations, at class × count ≥ 2 × flank, plus mixed 2/3/4+. Values from `haircut_table_candidate.csv`, rungs k2/k3.
- **Not haircut:** single-parent and unexposed PUDs stay at BOX as-is (no `none` uplift). No gas haircut.
- **Label on every PUD:** "validated with exception". It is confirmed or overturned on the 2026 prospective cohort (first cum-12 ~2027-Q2).
- **Still open:** precedent unit and shielding (recommendations in chat 2026-10-20).
