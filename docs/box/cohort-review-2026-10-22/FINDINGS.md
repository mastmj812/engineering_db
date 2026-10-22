# Step 16a — cohort-selection review, all benches (read-only) — 2026-10-22

**Trigger.** Michael, erebor Map tab, BS1_S BOX EUR/ft: Delaware Pad 1925 1BSS 3 forecast from 6 wells ~15–19 mi away while 4–5
same-bench producers sit within 2 mi. Scope of record (D118): diagnose every bench; change selection on provisional groups first;
short-history wells = test the level-only middle path, not adopted.

**What was run.** Every group's analog pool rebuilt exactly as `box_pud_run build` built it for run 10 (production cutoff pinned to
2026-08-01; run 14 = run 10 + the proximity layer, same selection), then every covered PUD (50,963) classified against its pool
wells within 3 mi (`box/cohort_review.py`, `python -m scripts.box_cohort_review pools | review`). Read-only against the warehouse;
nothing stored. The record selection reproduces exactly (same analog set + radius) on 95.9–100 % of PUDs per group (misses: BS3_S
378, WCB_1 159, BS3_C 56, WCXY 25, WCB_2 24, WCA 1 — not yet explained; the pool was rebuilt on today's `curated.production`, so
the D98 revision pattern is the first suspect, unverified).

Files: `summary_by_group.csv`, `closure_by_lateral.csv`, `pud_review.csv.gz` (one row per covered PUD).

**Definitions.** *Local wells* = pool wells within 3 mi, ≥ 12 calendar months at the cutoff, first production ≥ 2016, ANY lateral or
spacing. *Far with local control* = record radius ≥ 15 mi although ≥ 3 local wells exist. *Year-1 gap* = mean Novi cum-12 oil per
1,000 ft of the record cohort ÷ that of the local wells − 1 (actuals vs actuals; the forecast curve is not used).

## 1. Pad 1925 (the trigger)

4 BS1_S sticks, 7,720 ft. 6 analogs at 14–19 mi (5 Lea NM, 1 Loving). Pool wells within 5 mi: 8, **eligible 0 — every one fails the
lateral band 5,790–9,650 ft** (±25 % of 7,720). The five Devon QUINN 37-36-29 311H–315H (1.7–2.6 mi, 16 months, 9,927–10,112 ft,
representative spacing ~1,130 ft) miss the cap by 277–462 ft. Time on production and the 2016 floor are not binding here.
Year-1: record cohort 24.0 bbl/ft vs QUINN 19.9 (+21 %); the forecast's own month 1–12 is 28.0 bbl/ft. Record oil EUR 99.9 Mbbl per
1,000 ft; a local-first rule (±40 % band, ≥ 5 wells accepted in the 5-mi ring) gives ~72 (−28 %; 16-month history, so the shape is
borrowed-short). The spacing fix of §2 alone does NOT help this pad (still 20 mi, 9 wells): it is a lateral-band case.

## 2. Spacing artifact — a defect in the pool plumbing (all benches, validated included)

`scripts/box_pud_run.build_pool` / `build_pool_analog` (and the D53 harness, `box/backtest_report.run_fold_analog`) fetch
`lateral_closer_xy_ft` only for the F(k) training cohort (`trn`, + the harness's scored wells) and pass that series to
`box.analog.build_pool` for EVERY pool well. Every other pool well gets NaN, which `dealintake.select_wells.classify` reads as
**standalone → excluded**. Deal-intake itself reads `wells_enriched` per candidate, so BOX and a deal workup disagree here (D57 says
they are the same method).

| | value |
|---|---|
| pool wells (13 groups) | 34,705 |
| NaN spacing in the BOX pool | 16,102 |
| of those, MEASURED (non-sentinel) in `wells_enriched` | **12,174 (35 % of the pool)** |
| wells with 6–12 months that are NaN | **100 %** (training cohort = 12 full months) |
| wells with lateral > 13,000 ft that are NaN | **100 %** (training cohort lateral 6,000–13,000 ft) |

Consequences: the effective time-on-production floor is ~13 months, not the 6 the config states; no analog longer than 13,000 ft can
ever be selected (bears on D77 / Pad 548 — plausible, unverified). The tuning and holdout cells were scored WITH the artifact, so the
accepted spec includes it.

Re-running the unchanged record selection with measured spacing:

| group | tier | covered | 5-mi ring now → fixed | ≥ 15 mi now → fixed | cohort changes |
|---|---|---:|---|---|---:|
| WCA | validated | 1,907 | 74 → 78 % | 5 → 5 % | 41 % |
| BS2_S | validated | 7,394 | 56 → 67 % | 9 → 5 % | 55 % |
| WCXY_WCA1 | validated | 3,183 | 79 → 83 % | 6 → 4 % | 41 % |
| WCB_1 | validated | 4,133 | 54 → 59 % | 10 → 8 % | 31 % |
| WCC | validated | 1,990 | 27 → 32 % | 22 → 19 % | 29 % |
| AVA_0 | provisional | 607 | 55 → 61 % | 12 → 9 % | 20 % |
| AVA_1 | provisional | 1,365 | 56 → 59 % | 9 → 7 % | 43 % |
| AVA_2 | provisional | 2,839 | 33 → 45 % | 12 → 10 % | 41 % |
| BS2_C | provisional | 3,005 | 28 → 44 % | 27 → 10 % | 53 % |
| BS3_S | provisional | 9,192 | 43 → 46 % | 16 → 14 % | 32 % |
| BS3_C | provisional | 7,774 | 33 → 41 % | 28 → 24 % | 48 % |
| WCB_2 | provisional | 2,584 | 30 → 38 % | 30 → 22 % | 42 % |
| BS1_S | provisional | 4,990 | 20 → 30 % | 38 → 27 % | 51 % |

Selection only — the EUR effect of these cohort changes is not measured yet (needs refits; step 16c).

## 3. The 1.5-mile lateral-band gap (all benches)

Novi sticks are quantized (5,080 / 7,720 / 10,360 / 13,000 / 15,640 ft). Under ±25 % the 7,720-ft band (5,790–9,650) falls between
the common as-drilled 1-mi and 2-mi laterals; 1-mi sticks draw the 7,500–12,500 band with Cui translation, ≥ 12,500 ft gets ±40 %.
Share of covered PUDs closing in the 5-mi ring, by stick class:

| group | 1.0 mi | **1.5 mi** | 2.0 mi | 2.5 mi | 3.0 mi |
|---|---:|---:|---:|---:|---:|
| WCA | 79 | **65** | 76 | 81 | 51 |
| WCXY_WCA1 | 81 | **64** | 85 | 76 | 76 |
| BS2_S | 62 | **39** | 60 | 68 | 48 |
| WCB_1 | 62 | **31** | 59 | 64 | 45 |
| WCC | 21 | **8** | 37 | 37 | 28 |
| AVA_0 | 80 | **9** | 68 | – | – |
| AVA_1 | 72 | **29** | 60 | 31 | 56 |
| AVA_2 | 28 | **14** | 43 | 35 | 45 |
| BS2_C | 35 | **18** | 28 | 27 | 20 |
| BS3_S | 46 | **26** | 49 | 44 | 36 |
| BS3_C | 36 | **14** | 37 | 35 | 38 |
| WCB_2 | 28 | **24** | 36 | 18 | 28 |
| BS1_S | 25 | **13** | 24 | 8 | 7 |

The spacing fix helps the 1.5-mi class least (26 → 30 % pooled across groups vs 48 → 55 % for 1-mi / 2-mi): its binder is the band.

## 4. Far with local control (the Pad 1925 class)

**5,175 PUDs** (1,553 on validated groups, 3,622 provisional). Of these, **1,529 have a record-cohort year-1 > 25 % above their local
wells' and 368 > 25 % below** — the error leans toward the far cohort overstating local rock.

| group | far with local | share of covered | year-1 gap median (P10 / P90) |
|---|---:|---:|---|
| WCA | 88 | 4.6 % | −6 % (−31 / +32) |
| BS2_S | 539 | 7.3 % | +19 % (−14 / +69) |
| WCXY_WCA1 | 155 | 4.9 % | +5 % (−16 / +54) |
| WCB_1 | 376 | 9.1 % | −7 % (−26 / +31) |
| WCC | 395 | 19.8 % | −3 % (−26 / +30) |
| AVA_0 | 66 | 10.9 % | −4 % (−13 / +21) |
| AVA_1 | 97 | 7.1 % | +3 % (−20 / +29) |
| AVA_2 | 285 | 10.0 % | +23 % (−18 / +119) |
| BS2_C | 481 | 16.0 % | +3 % (−19 / +63) |
| BS3_S | 695 | 7.6 % | +14 % (−29 / +53) |
| BS3_C | 988 | 12.7 % | +15 % (−13 / +77) |
| WCB_2 | 592 | 22.9 % | +2 % (−19 / +33) |
| BS1_S | 418 | 8.4 % | −4 % (−43 / +64) |

What excludes the class's near wells (share of excluded near-well instances; a well can fail several rules): lateral band 56–91 %,
standalone spacing 62–88 % (largely the §2 artifact), first prod < 2016 2–35 %, months < 6 2–16 %. Lifting the lateral band alone
rescues 9–29 %; lateral + spacing together 60–84 %. Lifting the 6-month floor alone rescues 0 % everywhere — every well under 6 months
also has NaN spacing (§2).

**Correction to the first-pass number.** The first BS1_S pass (same day, scratch) put the class at 711 PUDs and the gap at +40 %; that
counted pre-2016 neighbours as local evidence. With the 2016 floor: 418 PUDs, −4 % median, but the spread is the widest of any bench
(P10 −43 %, P90 +64 %). The off-trend reads are real at specific PUDs (Pad 1925 +21 %) and do not net to a bench-wide bias.

## 5. Carried from the first pass (BS1_S only, not re-run here)

- **Curve-construction offset:** the record P50 curve's month 1–12 runs **+13 to +16 % above its own cohort's actual cum-12**, under
  every selection variant tried. A large part of BS1_S's measured backtest over-forecast (tuning oil-12 −10 %, holdout −21 %) may be
  this, not selection. Provisional groups carry no haircut, so it reaches the record. Undiagnosed.
- **Six-rule counterfactual (BS1_S, 4,990 PUDs, with the artifact still in):** bench total EUR moves only +0.5…+2.7 %; individual PUDs
  P10 −19 % / P90 +27 % under "relax the rules before widening the radius". Selection reshuffles; it does not move the level.
- **Backtest by radius:** BS1_S oil-12 miss is worst at 5–7.5 mi (−30 %, local-offsets benchmark −26 %) and smallest at 20 mi
  (−12 %); Σ actual / Σ forecast cannot see compensating location errors.

## 6. What this means for D118

D118 said: change provisional first. §2 is not a rule choice but a plumbing defect, and it touches validated groups as much as
provisional ones (29–55 % of validated cohorts change). Fixing it on validated groups is still a spec change against what was
scored (D58 / D59 / D100), so it needs Michael's call: fix everywhere with re-scoring of the tuning cells, or fix on provisional
groups first like the rule changes. That is gate 16a.
