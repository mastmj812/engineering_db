# BOX step 20a: Midland Wolfcamp bench QC + extents. STORED 2026-10-30 (r3, §8.17); rest of gate 20a open

**Scope (plan §5 step 20a, D128 / D131 / D134 A–B / D117):** Midland WCA_1, WCB_1, WCB_2, WCC, WCD. One extent per bench, no
pooling (D128). The Delaware class rule of record applied as written; cards only for a swap class clearly unlike its Delaware
analogue (D134 B). The Delaware D23 r / c (2,640 / 3,960 ft) and D27 constants, no step-2 repeat (D134 A). Read-only: no
`box.bench_scope` row and no `box.extent` record is written; storing is a separate go.

**Built:** QC pages at 7ffd598, extents at 5e30702 (a title-wrap fix only), branch `claude/box-step20a-midland-wolfcamp`.
Producing horizontals pulled 2026-10-26 (Midland as-of last reported month 2026-09-01; Delaware analogue 2026-08-01).

Pages (serve `python -m http.server 8766 --directory docs/box`):
- `index.html`: family page (well sets, flag ledger, sensitivity, D128 context, §4b analogue test, §4c allocation screen)
- `qc_<bench>.html`: per-bench QC pages
- `cards.html`: **50 cards for you** (`cards_sample.csv` column `verdict`)
- `extents/index.html`, `extents/extent_<bench>.html`: interactive maps
- `extents/visual_<bench>.png`: the maps for your pen loops
- `extents/geology/`: NAD83 UTM 14N US-ft shapefiles. Context only (D28). No structure layers: no Midland grids exist.

## 0. Your question: shouldn't the tags be QC'd before the extent work?

They were, in this order: bench QC first, extents built on its output. Three things are still open, and they matter to
different degrees.

1. **Done: the tag QC of record.** The consensus detector, the sql/23 second vote, the GOR veto and the class rule, all as
   written (D134 B). It moves 60 wells into WCA_1 and 2 out. Applying *every* flag would move the bench cohort medians of
   12-mo oil per 1,000 ft by ≤ 0.5 % on WCA_1 / WCB_1 / WCB_2 / WCD, and **−3.2 % on WCC**.
2. **Open: the 50 cards (§1b).** By the plan's design (§5 step 20), the cards are judged at this same gate, and the extent
   regenerates from the ratified set before anything is stored (about 9 min). Measured exposure: if you accept a class,
   these modern laterals land outside the target bench's extent:

   | Class | Modern laterals flagged | Already inside the target extent | Outside it |
   |---|---:|---:|---:|
   | WCA → WCB_1 | 270 | 261 | 9 |
   | WCB_1 → WCA | 76 | 72 | 4 |
   | WCB_2 → WCB_1 | 124 | 124 | 0 |
   | WCC → WCB_2 | 28 | 25 | 3 |
   | WCB_2 → WCC | 12 | 6 | 6 |

   So the WCA_1 / WCB_1 extents cannot move materially. WCC and WCB_2 can, and those two need your loops anyway (§2).
3. **Missing: an independent tag check.** The Delaware has the tops-vs-tag QC against Holden's grids. The Midland has no
   structure grids and no tops QC (plan Phase 3, difference 8), so its tags rest on Novi + sql/23 + this detector.

**Recommendation:** judge the cards first, mainly the WCC / WCB_2 classes. Draw loops on WCA_1 / WCB_1 now; they are
insensitive to the outcome. Draw WCC / WCB_2 loops after I regenerate those two from your verdicts.

## 1. Bench QC (Delaware class rule as written)

| Bench | Tagged live | Final set | First production ≥ 2016 | D9 cohort | Moved in / out by the rule | sql/23 disagrees | Consensus flag rate |
|---|---:|---:|---:|---:|---|---:|---:|
| WCA_1 | 7,721 | 7,779 | 6,998 | 5,536 | +52 WCB_1, +5 WCB_2, +3 WCD; −2 to WCB_2 | 9.3 % | 5.1 % |
| WCB_1 | 6,164 | 6,112 | 4,511 | 3,515 | −52 to WCA_1 | 11.9 % | 4.4 % |
| WCB_2 | 2,385 | 2,382 | 1,876 | 1,477 | +2, −5 | 13.0 % | 7.3 % |
| WCC | 662 | 662 | 480 | 390 | — | **16.2 %** | 6.3 % |
| WCD | 942 | 939 | 802 | 546 | −3 to WCA_1 | 2.7 % | 0.7 % |

How these sets were built:
- No frozen Midland pools exist, so every well is new to BOX (nothing is "kept on gate-1 judgment").
- No exclusions apply.
- Planned surveys are ~0 % (no NM overprint).
- Permit-round TVDs are 1.1–2.7 %.
- No api10 sits in two sets.

**D128 context** (5-mi block + first-production-year fixed effects, D9 cohort, ratio of the second bench to the first):

| Pair | Oil per 1,000 ft | GOR |
|---|---|---|
| WCB_1 / WCA_1 | 0.970 | 1.284 |
| WCB_2 / WCB_1 | 0.937 [0.894–0.971] | 0.957 |
| WCC / WCB_2 | 0.863 | 1.144 |
| WCD / WCC | 1.124 [0.92–1.39] | 1.104 |

These agree with the gate-18 pack (WCB_2 / WCB_1 0.927); D128 stands.

**Defect found and fixed (affects a recorded step-15 number).** `family_qc.pooling_evidence` compared bench b against *every
other family member*, not just bench a. Two-bench families are unaffected, but the Delaware AVA family (3 benches, step 15)
was. Recomputed on today's data:

| AVA_1 / AVA_0 | Recorded | Corrected |
|---|---|---|
| Oil per 1,000 ft | 0.990 | 0.986 |
| GOR | 1.198 | 1.118 (CI now spans 1) |
| Shape | 0.930 | 0.885 |

On AVA_2 / AVA_1, oil moves 1.000 → 1.003 and GOR 0.820 → 0.757. No AVA decision rests on these numbers (AVA is
separate and provisional, D105). The committed step-15 page is left as the record and is not rewritten. Before the fix,
this run had printed WCB_2 / WCB_1 = 1.01; that is how the defect surfaced.

### 1b. Swap classes vs their Delaware analogue (D134 B) → `swap_classes_vs_delaware.csv`, `cards.html`

The test was stated before any card was drawn. A class is "unlike" when it has ≥ 20 Midland flags and ≥ 10 Delaware flags,
and any of these holds:
- the flag rate is ≥ 2× or ≤ ½× the Delaware rate;
- sql/23 concurrence or the GOR own-vote share differs by ≥ 25 points;
- the median own-band TVD offset is ≥ 1.5× or ≤ ⅔× the Delaware's.

**These thresholds are mine — confirm or replace them.**

| Class (rule standing) | Midland flags (per 1,000 tagged) | Delaware flags (per 1,000) | sql/23 concurs, Mid / Del | Verdict |
|---|---|---|---|---|
| WCA → WCB_1 (rejected 0.40, tag kept) | 333 (43.1) | 132 (10.8) | 70 % / 41 % | **unlike**: rate 4.0×, concurrence +29 pts, TVD 1.63× |
| WCB_1 → WCB_2 (uncalibrated) | 168 (27.3) | 34 (17.6) | 53 % / 65 % | alike: rule as written, tag kept |
| WCB_2 → WCB_1 (uncalibrated) | 146 (61.2) | 42 (34.7) | 69 % / 60 % | **unlike**: TVD 0.66×, *borderline* (cut is 0.667) |
| WCB_1 → WCA (**accepted 0.70**, 52 applied) | 90 (14.6) | 159 (82.4) | 67 % / 65 % | **unlike**: rate 0.18× |
| WCC → WCB_2 (uncalibrated) | 34 (51.4) | 35 (30.8) | 79 % / 46 % | **unlike**: concurrence +34 pts |
| WCB_2 → WCC (uncalibrated) | 21 (8.8) | 28 (23.1) | 48 % / 46 % | **unlike**: rate 0.38×, TVD 0.63× |
| WCA ↔ DEAN, LSSH → WCA | 51 / 45 / 20 | — | — | no analogue: tag kept |

Five classes are carded, 10 cards each = **50 cards**. Two of them carry the most weight:
- **WCA → WCB_1** (217 cohort wells): the Delaware rejected this class, but in the Midland it flags 4× as often and sql/23
  agrees far more.
- **WCB_1 → WCA** is the one *accepted* class being applied (52 wells).

## 2. Extents (D27 one-body envelopes; Delaware r / c and D27 constants per D134 A)

| Bench | Extent, sq mi | ≥ 2016 laterals inside | Bodies ≥ 50 laterals | Live fronts | Isolated tests outside | Undrilled Novi sticks inside (PUD + RES, D117) / basin total |
|---|---:|---:|---:|---|---:|---|
| WCA_1 | 5,613 | 6,939 of 6,998 (99 %) | 1 | none | 63 | 5,432 / 12,281 (44 %) |
| WCB_1 | 5,127 | 4,478 of 4,511 (99 %) | 1 | E | 37 | 5,401 / 9,522 (57 %) |
| WCB_2 | 2,675 | 1,593 of 1,876 (85 %) | 5 | N, W, NW | 306 | 995 / 2,096 (47 %) |
| WCC | 746 | **233 of 480 (49 %)** | 2 | SE, SW, W, NW | 256 | 853 / 8,542 (**10 %**) |
| WCD | 1,627 (2 parts) | 672 of 802 (84 %) | 2 | NW | 135 | 1,747 / 8,452 (21 %) |

Basin totals are from the live warehouse (status remaining / conflict / not yet reconciled, all categories). The
per-category split is in `extents/pud_counts_<bench>.csv`.

- **WCA_1 and WCB_1: the Delaware metric holds.** One body each (6,910 / 4,432 laterals), no visible failure, so D134 A
  stands. WCA_1 leaves a large E embayment: an undeveloped bite wider than the 8-mi bridge, open by design.
- **WCB_2, WCC and WCD fail the one-body construction visibly**, the step-15 multi-trend pattern (BS2_C / WCB_2 Delaware):
  - WCB_2 drops bodies 2 / 4 / 5 (82 / 57 / 51 laterals; N, SE).
  - WCC's D27 body holds only 105 laterals. The SE body (71) and the scattered NW development are out.
  - WCD's south body (57) is out.

  Per the step-15 convention, your **red closed loops are the extent** for these (`visual_<bench>.png`, PowerPoint pen,
  read back by `scripts.box_family_extent_edits`). Re-tuning r / c would be a new decision (D134 A); I don't recommend it.
- **Rule 11 shows up as expected.** Only 10 % of Novi's undrilled WCC sticks and 21 % of WCD's sit inside any developed
  envelope. Even WCA_1, the most developed bench, holds only 44 % of its undrilled sticks inside.

## 3. Allocation-well screen (plan Phase 3, difference 6) → §4c, `alloc_twin_pairs.csv`

**Twin laterals.** The screen looks for coinciding sticks: ≥ 80 % overlap within 150 ft, and |ΔTVD| ≤ 150 ft. Pairs touching
the family:

| Pair class | Count | What it is |
|---|---:|---|
| Stacked pair | 22 | Two benches down one surface path |
| Re-drill | 10 | One side never reached 12 months |
| Same-bench twin | 13 | Both producing, same bench |

**None of the 13 twins shows the El Campeon split** (same GOR, one side under half the other's oil). By name they are
stacked pairs that Novi tagged the same bench: WA/WB, 4209H/4309H, HL/HU.

Detector check on the Delaware: it puts 22 of the 46 recorded exclusions in a coinciding pair (10 of them with the split
signature). It works as a review list, not as a filter.

**Production sharing.** Novi's `has_production_sharing` covers 43 % of the family's D9 cohort. Within block, sharing wells
read 1.033× [1.003–1.064] oil per 1,000 ft (Delaware TX: 0.993×) and 1.025× GOR. That is a small level difference, not a
defect.

**Proposed exclusions: none.**

## 4. Gate 20a: your calls

1. **Cards:** DONE 2026-10-26, applied in r2 (§7). Verdicts on the 50 cards. Also confirm (or replace) the "unlike" thresholds, and say whether the borderline
   WCB_2 → WCB_1 class (TVD 0.66× against a 0.667 cut) needs cards at all. Then I regenerate any extent your verdicts move.
2. **Pen loops:** DONE 2026-10-26 (WCD looped; WCC loop drawn then withdrawn, deck re-saved 21:16, WCC = r2 generated; the rest accepted as generated; §7). Loops for WCB_2, WCC and WCD (they fail one-body). For WCA_1 and WCB_1, accept them as generated or draw
   loops.
3. **ANSWERED 2026-10-30 = D139: card it (§8.18, 10 cards out).** **Conflict to resolve (D128 vs D134 B).** D128 sent the WCB_1 ↔ WCB_2 and WCB_2 ↔ WCC swap classes to 20a's cards. D134 B
   cards only "unlike" classes. I followed D134 B (the later decision), so **WCB_1 → WCB_2 (168 flags, alike) is not
   carded**. Say if you want it carded per D128.
4. **ANSWERED 2026-10-30 = D140: no** (the prefix list stays Bone Spring + Avalon). **Spraberry → Wolfcamp flags (DEAN / LSSH → WCA, 65).** The rule's "never Bone Spring → Wolfcamp" names Bone Spring and
   Avalon only. These classes therefore fall to "uncalibrated, tag kept": the same membership, but the well stays a depth
   witness. Should the prefix list gain the Spraberry benches at 20b?
5. **DONE 2026-10-30 (§8.17, named WCA_1).** **Storage, on your go after 1–2** (and after D136 is applied in the same regeneration pass): five `box.bench_scope` rows (basin `midland`, `in_scope` true, `validation`
   provisional until step 21, `member_benches` = {bench}) and five `box.extent` records.

   Naming: I recommend the row be `WCA_1`, not the Delaware's pooled `WCA` (D128: one bench each; the Midland has no WCA_2 /
   WCXY tags). Note that `box/production.py` resolves sticks through `member_benches`, so either name works there.
6. **ANSWERED 2026-10-30: D117 as written** ("every category, BASE_CASE or UPSIDE, as long as it is inside the BOX extent"); the code + rehearsal = D117 step 3, before the first Midland record (step 23). **Not this step, but flagged:** `box/production._UNIVERSE_SQL` still filters `il.category = 'PUD'`, while D117 says any
   category. AUDIT step 3 ("BOX universe drops category = 'PUD'") is not on main at 414dddd. This matters before the first
   Midland record (step 23), and it already applies to the Delaware record.

## 6. One vs two Wolfcamp B landings (Michael's question, 2026-10-26) → `wcb_split/`

**The question:** is WCB_1 + WCB_2 developed in the south and a single WCB landing in the north — and if so, where is the
line, so the extents don't plan an extra WCB where only one is developed?

**Answer: yes. The PDP data shows it sharply.**

**Method (tags ignored, because a single landing carries either tag).**
- Landing depth = lateral TVD minus the local WCA_1 band median (1.5-mi consensus neighbourhood), so structure drops out.
- A lateral sits at **WCB_2 depth** when it lands ≥ 392 ft below WCA_1. That cut is the midpoint of the southern tag medians
  (WCB_1 262 ft, WCB_2 522 ft): measured from the data, not chosen.
- 4,569 of the 6,387 modern WCB laterals have a WCA_1 reference to measure from.

| Latitude °N | Laterals | Share at WCB_2 depth | Share tagged WCB_2 |
|---|---:|---:|---:|
| 31.25–31.65 | 1,601 | 48–54 % | 45–56 % |
| 31.65–31.85 | 826 | 35–38 % | 24–34 % |
| 31.85–31.95 | 370 | 10 % | 11 % |
| 31.95–32.55 | 1,609 | **0–3 %** | 7–23 % |

- **South of the line, landing depth is bimodal; north of it, unimodal at WCB_1 depth.** North, median 257 ft below WCA_1, and
  only 79 of 2,257 laterals (3.5 %) land at WCB_2 depth. South, 49 %.
- **The 279 WCB_2-tagged producers north of the line are the single landing carrying a WCB_2 tag.** They land at WCB_1
  depth (median ~290 ft below WCA_1).
- **The line is wavy, not straight E-W.** Per 0.15° longitude strip, the north edge of the last latitude bin with ≥ 20 % of
  laterals at WCB_2 depth:

  | Longitude | −102.2 | −102.1 | −101.9 | −101.8 | −101.6 | −101.5 | −101.3 |
  |---|---|---|---|---|---|---|---|
  | Boundary °N | 31.70 | 31.70 | 31.85 | 31.90 | 31.70 | 31.55 | 31.55 |

  The east end (−101.5 / −101.3) is sparse: there is no WCB development between ~31.6° and 32.3° there. North of the line,
  every strip holds 0–5 % WCB_2-depth laterals.
- **What the generated extents do north of the line.** The WCB_2 extent reaches 634 sq mi (24 %) past it, all stacked under
  WCB_1. That piece holds **144 undrilled Novi WCB_2 sticks** (PUD + RES). Novi has 872 undrilled WCB_2 sticks north of the
  line in all; the generated extent already excludes the other 728.
- **Proposal (not stored):** clip the WCB_2 extent at the line. Clipped it is 2,041 sq mi: 0 of Novi's northern WCB_2 sticks
  inside, and the 851 southern ones unchanged.

  The clip is a reservoir reason in D27's sense: there is no second WCB landing to develop there. The 872 northern sticks
  would show as `not_covered_outside_extent`, never as zero.

  The WCB_1 extent is unchanged: the single northern landing *is* WCB_1, and its 3,588 undrilled sticks inside stay.
- Files:
  - `wcb_split/index.html`: map, profile, histograms, tables;
  - `wcb_split/wcb_line.geojson` and `wcb_split/geology/BOX_MID_WCB_split_line.shp`: the line;
  - `wcb_split/extent_WCB_2_v1_clipped.geojson` and `wcb_split/geology/BOX_WCB_2_extent_v1_clipped.shp`: the clipped extent;
  - `wcb_split/visual_WCB_2_clipped.png` (+ frame): **draw your WCB_2 loops on this one** instead of the unclipped map.

**DECIDED 2026-10-26 = D136 (Michael: "Adopt the data-derived line; WCB_2 extent = D27 envelope clipped at it; count north WCB_2-tagged producers at WCB_1 depth as WCB_1 for BOX"):** (a) the data-derived line; (b) WCB_2 extent clipped at it, WCB_1 unchanged; (c) of the 430 WCB_2-tagged wells north of the line, 266 land at WCB_1 depth and count as WCB_1 (210 D9 cohort), 45 at WCB_2 depth keep WCB_2, 119 have no WCA_1 reference and keep their tag. Applied in the regeneration pass with the card verdicts (one rebuild), before storage.

**The calls as they were put (answered by D136):**

- **(a) The line.** Accept the data-derived polyline, or pen your own on the map. Your local knowledge of where operators
  stopped the second landing beats a 0.05° bin.
- **(b) The extent rule.** WCB_2 extent = the D27 envelope clipped at the line (recommended). WCB_1 stays as generated.
- **(c) The 279 northern WCB_2-tagged producers.** Leave them as WCB_2 evidence (as the rule of record does now), or count
  them as WCB_1 for BOX north of the line.

  I recommend counting them as WCB_1 when they land at WCB_1 depth: otherwise they testify as WCB_2 analogs near the line
  while producing from the WCB_1 landing. That is a BOX-only membership rule, a step-21 input.
- **(d) Cards.** If you adopt (b) + (c), the WCB_2 → WCB_1 cards (§1b) mostly answer themselves north of the line; the
  southern WCB_1 ↔ WCB_2 cards still matter.

## 7. r2 regeneration (2026-10-26): your cards + D136 + owner WCD + your WCD loop → `r2/`, `extents/edited/`

One rebuild, read-only, nothing stored. r1 (what you reviewed) is left as it was. Commits 5b5e992 (inputs) and 52a7fb2
(speed fix, below).

**Card verdicts → a Midland class ledger (D134 B, gate ≥ 0.70 as written).** 36 agree and 14 reject. Each carded class is
judged on its own Midland cards, which replace the Delaware entry (`box/qc_rule.BASIN_CLASSES`). Every other class keeps the
Delaware ledger.

| class | Delaware | Midland cards | Midland standing | reassigned r1 → r2 |
|---|---|---|---|---|
| WCA → WCB_1 | rejected 0.40 | 7 / 10 = 0.70 | **accepted (at the gate)** | 0 → 192 |
| WCB_1 → WCA | accepted 0.70 | 5 / 10 = 0.50 | **rejected** | 52 → 5 (your agree cards) |
| WCB_2 → WCB_1 | uncalibrated | 10 / 10 = 1.00 | accepted | 0 → 104 |
| WCB_2 → WCC | uncalibrated | 7 / 10 = 0.70 | accepted (at the gate) | 0 → 12 |
| WCC → WCB_2 | uncalibrated | 7 / 10 = 0.70 | accepted (at the gate) | 0 → 25 |

The sql/23 second vote and the GOR veto still apply inside the accepted classes. Three classes sit exactly at 0.70 on 10
cards, so one verdict either way flips them. The WCA → WCB_1 class matters most: it moves 192 wells (125 D9 cohort) from
WCA_1 to WCB_1.

**D136 (c):** 229 more WCB_2-tagged producers north of the line, landing at WCB_1 depth, become WCB_1 (186 cohort). With the
58 the accepted WCB_2 → WCB_1 class already moved there, that is 287 of the 430 northern WCB_2 tags. 118 have no WCA_1 band
and keep their tag. (The §6 figure of 266 counted ≥ 2016 laterals with geometry only.)

**Owner assignments** (`owner_benches.csv`, BOX-only, outrank every rule): 6 wells tagged `OTHER` in the warehouse, all
off-band in the detector, assigned to WCD. Four are Exxon's UNIVERSITY "3-19" (Upton, 2014–15) and two are SM's MARY ROSE
A 9H / B 10H (Reagan, first production 2025-10). The warehouse tag is unchanged. Carrying them into
`ref.formation_tag_overrides` is a CASCADE-window job, done only on your go.

| bench | r1 final (cohort) | r2 final (cohort) | pooling contrast vs the bench above, oil / GOR / shape, r1 → r2 |
|---|---|---|---|
| WCA_1 | 7,779 (5,536) | 7,540 (5,378) | — |
| WCB_1 | 6,112 (3,515) | 6,684 (3,927) | 0.970 / 1.284 / 0.978 → 0.962 / 1.294 / 0.979 |
| WCB_2 | 2,382 (1,477) | 2,062 (1,237) | 0.937 / 0.957 / 1.002 → 0.958 / 0.928 / 0.999 |
| WCC | 662 (390) | 649 (376) | 0.863 / 1.144 / 1.016 → 0.878 / 1.177 / 1.002 |
| WCD | 939 (546) | 945 (546) | 1.124 / 1.104 / 1.030 → 1.123 / 1.108 / 1.030 |

The benches stay separable after the moves (D128, no pooling, unaffected).

**Extents, as they would be stored** (undrilled = D117, Novi PUD + RES, ≥ 50 % of the stick inside):

| bench | extent | source | sq mi (r1 generated) | undrilled inside |
|---|---|---|---|---|
| WCA_1 | r2 generated, no loop drawn | `r2/extents/extent_WCA_1_v1.geojson` | 5,519 (5,613) | 5,204 |
| WCB_1 | r2 generated, no loop drawn | `r2/extents/extent_WCB_1_v1.geojson` | 5,220 (5,127) | 5,599 |
| WCB_2 | r2 generated, D136 clip (2,298 before the clip), no loop drawn | `r2/extents/extent_WCB_2_v1.geojson` | 2,003 (2,041 clipped) | 851 |
| WCC | r2 generated (your slide-4 loop withdrawn) | `r2/extents/extent_WCC_v1.geojson` | 652 (746) | 699 |
| WCD | **your loop** (slide 5) | `extents/edited/extent_WCD_v1_edited.geojson` | 3,371 (1,627) | 3,598 (generated: 1,747) |

The WCD loop was read as drawn (`extents/edited/reading_WCD.png`: your red stroke and the black reading coincide; the
re-saved deck re-reads byte-identical). Inside it: 771 of 804 ≥ 2016 WCD laterals.

**WCC (2026-10-26, Michael: "drop my red edit for WCC and just use the black WCC extent you originally derived").** The
re-saved deck has no stroke on slide 4; the WCC edited files are removed. The black outline on the slide was r1's (746 sq
mi, 853 undrilled). Stored = the **r2** generated extent, as for WCA_1 / WCB_1 / WCB_2: same construction, same shape, on
the r2 WCC set (649 wells; 25 moved to WCB_2, 12 in from WCB_2). It is 652 sq mi, 699 undrilled; the west flank pulls in
~1 mi (`r2/extents/visual_WCC.png` vs `extents/visual_WCC.png`). 216 of 464 ≥ 2016 WCC laterals are inside; the SE body
(72) and the scattered north development stay out, as you chose. Storing the r1 outline instead would mismatch the
membership it is stored with.

**Why (Michael):** "a lot of the midland PDP wells currently shown as formation_blueox=WCC are pretty questionable [...]
especially those to the north, so i opted to the original (black) extent towards the south." The extent is drawn only
where the WCC tags are trusted.

**What the extent does not do.** It limits where WCC PUDs are forecast. It does not take the questionable WCC-tagged wells
out of the WCC analog pool: the D54 ladder runs 5 → 7.5 → 10 → 15 → 20 mi until 10 analogs are eligible, and it can
reach outside the extent. Of the 464 ≥ 2016 WCC laterals, 217 are inside, 35 within 5 mi of the edge, 19 at 5–10 mi,
42 at 10–20 mi (32 of them north) and 151 beyond 20 mi (out of reach). The outside wells run lower (median 12-mo oil
6,600–9,700 bbl / 1,000 ft vs 11,960 inside). At ~26 modern wells per 5-mi circle on average, most locations should fill
at 5 mi; edge locations may not. The analog radius reached and the share of analogs from outside the extent are
measurable only at the forecast step. **Proposed check (21a, not a rule change):** report both for every Midland WCC
location. If outside wells carry material weight, the fix is a tag decision (13e-style, warehouse first) or a pool rule.
Either way it is your call, not decided here. Where the questionable northern wells actually land (WCB_2? WCD?) is the
same tag question.

**Flags before storage:**
- ~~WCC density~~ — resolved: loop withdrawn, WCC = generated (699 undrilled).
- **4246139575** (UNIVERSITY "3-19" 51H, one of your six WCD wells) sits just outside your WCD loop at its south tip
  (31.26°N). It is pre-2016, so it is not ≥ 2016 evidence. Extend the loop or leave it.
- **Speed fix (no number moves):** the pooling contrast fitted one dummy column per 5-mi block on every bootstrap draw
  (18 s a fit on WCA_1 / WCB_1, hours per run). It now absorbs the blocks by within-block demeaning (Frisch–Waugh). The
  coefficient is identical to 1e-14 (test pinned) and the run takes 88 s.

**Superseded order (Michael 2026-10-26, §8): fix the Midland tags first, then re-run 20a, then store.** **Still open at gate 20a:** the storage go (the five rows + extents above); asks 3, 4 and 6 in §4; the unlike-threshold
confirm (§4.1).

## 8. Midland tag screen (2026-10-26): every PDP tag vs its neighbourhood → `tag_screen/`

**Why (Michael):** many Midland PDP wells tagged WCC are questionable, worst to the north, which defeats drawing extents
around them. Screen all Midland PDP tags against their neighbourhood bands, pick a subset for manual review, fix the
tags in the warehouse, then re-run 20a. Spraberry classes are carded at 20b.

**The blind spot it closes.** The 1.5-mi consensus bands are built from the neighbours' tags, so a neighbourhood that
shares one wrong label "agrees" with itself. The warehouse tag takes Novi's formation unless Novi's call is coarse
(sql/16), and Novi's `WOLFCAMP C` counts as fine-grained: Novi sets 563 of the 662 WCC tags. Enverus agrees on only
305 of those 563 (WCB_2 173, WCB_1 41, WCD 27, WCA_1 9, other 8). North of the WCC extent it agrees on 35 of 105.
The stack also thins northward. Below the local WCA_1 band, WCB_2 goes from ~520 ft (south) to ~300 ft (north) and
WCD from ~1,870 to ~1,200 ft. So the screen uses local bands, never fixed southern offsets.

**Rules (fixed before any card was looked at; `box/tag_screen.py`):**
- **A (depth):** the well sits in another bench's local band (consensus `flag`) AND at least one vote that does not
  come from the neighbours' tags names that bench: the other vendor's label, sql/23's nearest bench, or GOR.
  Destination = that bench.
- **B (label):** Novi and Enverus disagree AND the neighbourhood cannot confirm the tag (off band / ambiguous / no
  evidence). Destination = the other vendor's bench.
- A coarse Novi value is no vote. Sand ↔ carbonate swaps are never flags.
- Counted, not flagged: the vendors disagree but the well sits in its own tag's band (`conflict_agree.csv`). There,
  depth cannot settle naming.

Caveat: on the large Enverus-sourced classes (WCA_1 ↔ WCB_1, WCB_1 ↔ WCB_2) Novi's call is coarse, so the second vote
is almost always sql/23. sql/23 is a separate depth method (nearest of 12 reference laterals), not a fully independent
witness.

**Result** (28,859 producing horizontals, as of the 20a pull, read-only):
- **1,526 flagged (5.3 %):** 885 under rule A, 641 under rule B, in 98 classes.
- **Flag rate by tag:** WCC 24.8 % (164 of 662), DEAN 12.4 %, WCB_2 5.2 %, WCD 4.7 %, LSSH 4.6 %, WCA_1 3.7 %,
  WCB_1 2.7 %. Small tags are worse: OTHER 18 %, MISS 50 %, STRN 93 %.
- **WCC:** 164 flagged, 55 of them north of the extent's top. Proposed: WCB_2 105, WCB_1 24, WCD 18 (14 north),
  WCA_1 9, other 8. Another 112 WCC wells have Enverus disagreeing while sitting in a WCC band (85 Enverus WCB_2).
  Those are not flagged.
- **Wolfcamp scope:** 56 classes (1,042 wells) touch the Wolfcamp; 42 classes (484 wells) are Spraberry-only (20b).
  **21 classes are carded** (913 wells, 556 cohort): those with ≥ 5 D9-cohort wells. 35 small classes (129 wells, 33
  cohort) are listed only and keep their tags.
- **Spraberry ↔ Wolfcamp crossings are carded now** (DEAN → WCA_1, WCA_1 → DEAN, LSSH → WCA_1 / WCB_1). They are §4
  item 4.

**Cards (`tag_screen/cards.html`, verdicts in `tag_screen/cards_sample.csv`).** Sequential:
- 5 cards per class. 5/5 agree accepts; 0–1 of 5 rejects (even 5 more agrees cannot reach 7/10); otherwise 5 more and
  the class is judged at 7/10 (qc_rule.CLASS_GATE).
- Your 20a verdicts are reused where the same well proposes the same move: 34 wells, `verdict_source = 20a`.
  WCB_2 → WCB_1 (A) is already accepted on them (6/6).
- WCA_1 → WCB_1 (6/8), WCB_1 → WCA_1 (3/6), WCC → WCB_2 (A) (6/9) and WCB_2 → WCC (3/5) go straight to round 2.
- **92 new cards** for this round. Each card shows the tag source, both vendors' raw labels and the proposed bench.

**Warehouse fix (needs your "go apply"; nothing written).** An accepted class becomes rows in
`ref.formation_tag_overrides` (seed CSV + `scripts.apply_formation_tag_overrides`). An override wins over the vendor
labels in `curated.formation_blueox`. Live dependents (read-only pg_depend query, 2026-10-26):
- Level 1: bench_reference, codev_context, intel_formation_blueox, intel_pdp_support, producing_reference,
  wells_enriched (view).
- Level 2: formation_blueox_tvd, reconciled_inventory, erebor_locations, net_new_pdp, intel_forecast_accuracy(_vintage),
  dev_scenario (view).
- Level 3: box_scout_locations (view).

It is a REFRESH chain, not a DROP / CASCADE rebuild. I was wrong earlier on both counts: it is not a cascade rebuild,
but it is also not "just the 90k-row view". Several of these are quarterly-owned (not in the nightly) and
intel_pdp_support is the ~50-min one. sql/44's own header says to bundle with a quarterly-chain rebuild window.

**Consequences:**
- intel_formation_blueox re-infers Novi PUD / RES stick benches from bench_reference. Midland stick tags can move, which
  changes 20a's undrilled counts; the 20a re-run picks that up.
- Delaware rows don't change (Midland api10s only), but the refresh is basin-wide.

**Conflict to flag, not resolved (convention of record).** sql/44's header says a row lands in the override table "only
after MM ratifies it well-by-well (supervised rounds, no auto-flips)". Class-wholesale acceptance writes rows for wells
nobody looked at individually. Delaware precedent (2026-09-16/17): wholesale accept of the 51-well WCB_1 → WCB_2 class
was offered on a 9/10 sample and not taken. You reviewed all 51 instead: 44 ratified (13 in batch 1, 31 in batch 2),
7 rejected, 86 % against the sample's 90 %. The rejects sat at the evidence margin (82–119 ft). A wholesale accept would
have written those 7 as overrides. The opposite class, WCB_2 → WCB_1, ran ~26 % and stayed case-by-case.

Options:
- (a) Allow class-accepted rows, each with a provenance note (class, sample k/n, date). Amend the header.
- (b) Keep well-by-well. Cards then pick the classes worth a full review, and you review every well in them.
- (c) Class acceptance stays BOX-only, as 20a already does. The warehouse gets only the wells you card.

**Decided 2026-10-27 (Michael): (a).** Every well in an accepted class becomes an override row. `was` = the pre-override
tag; `note` = `class-accepted <class> k/n cards <date>` for wells nobody carded individually, `carded <date>` for the
ones you did. Rejected classes write nothing class-wide (amended 2026-10-28, §8.9: a card you agreed with, or an own-bench
call, still lands as a single-well `carded <date>` row); a well you rejected inside an accepted class is left out. The sql/44 header
and its table COMMENT are amended in the same commit as the first class-accepted rows (the COMMENT reaches the live table
only when that apply runs).

### 8.1 Round 1 back (2026-10-27) and what it showed

Your round-1 verdicts are in `tag_screen/cards_sample.csv` (126 rows: 92 yours, 34 reused from 20a). 18 are free text.
The card count reads them as follows (`box.tag_screen.clear_verdict`). The text itself is kept verbatim in every file:
- `reject …` counts as a reject.
- A bare bench code (Cypert B 221: `WCD`) is your destination for that well. It counts as a reject for its class.
- Anything else is a hold: not counted, and the well is never drawn again. This covers 8 "bad tvd", 1 "suspect tvd"
  and 6 Discovery "let's discuss".

**Shallow TVDs: Midland worse in modern wells.**
- Producing horizontals with TVD < 2,500 ft: Delaware 101, Midland 67.
- **Delaware:** 54 New Mexico wells carry a 9-ft placeholder; 86 of the 101 are pre-2016.
- **Midland:** 66 of 67 have TVD = MD (400–2,000 ft), and 45 are 2016+.
- Since 2016: Midland 0.18 % against Delaware 0.06 %.
- Novi and Enverus carry identical bad values, so the defect is upstream of the warehouse. Novi then picks the formation
  from the bad depth (Yates / Grayburg / Clear Fork), which lands the well as `OTHER`.
- Proposed, not yet built: wells more than 2,000 ft from every local band leave the screen as data defects. That catches
  all 8 "bad tvd" cards and keeps Cypert (1,276 ft).

**Discovery LS/SH (Reagan / Irion / Glasscock, ~40 wells): the label looks wrong, not the TVD.**
- Novi and Enverus agree on TVD and MD to the foot. None are on planned surveys.
- Discovery's own Reagan pads stack by median TVD: AS 7,003 → AN 7,126 → **LS 7,192** → LA 7,242 → UB 7,281 →
  **SH 7,404** → US 7,456 → CS 7,726.
- So LS and SH sit inside the Wolfcamp A/B sequence, below Wolfcamp A wells on the same pads. A Lower Spraberry Shale
  can't sit there.
- Their AS and UB benches line up with Permian Resources' Wolfcamp A / B offsets. Discovery's LS wells in Midland and
  Upton County (~8,900 ft) look genuine.
- Open: your call on LS → WCA_1, SH → WCB_1 as one group.

### 8.2 Novi WOLFCAMP C in the Midland: drafted sql/16 rule + what-if screen

**Evidence.** Novi's 'WOLFCAMP C' is not on the sql/16 coarse list, so it sets 563 of the Midland's 662 producer WCC
tags. The test below scores those wells against 2-mile bands built only from wells whose tag does not come from Novi's
WOLFCAMP C call (546 with a sane TVD and a jury):

| Nearest independent band | WCB_1 | WCB_2 | WCC | WCD |
|---|---|---|---|---|
| Wells | 113 | 203 | 190 | 16 |

- **Where Enverus disagrees, its label is usually the depth-consistent one.** For Enverus WCB_2: 99 of 168 sit nearest
  WCB_2, against 22 nearest WCC.
- **South:** both-vendor WCC sits a median 148 ft below WCB_2, under 150 ft in half the cases. WCD is ~1,300 ft down.
- **North:** there is no both-vendor WCC band anywhere.
- This is nearest-median-band with no margin gates: direction, not per-well calls.

**Draft (`sql/16`, not applied).**
- A `trig` CTE adds basin-scoped triggers: Midland 'WOLFCAMP C' defers to Enverus ENVInterval. As before, it falls back
  to Novi when Enverus is NULL.
- The Delaware is untouched.
- Pinned to `box.tag_screen.NOVI_COARSE_BY_BASIN` by a test.

**Dry run.** The new SELECT, evaluated read-only against live:
- 95,651 rows, unique on api10, same count as live.
- 1,335 Midland rows switch source to Enverus. 849 keep WCC; 486 change code: WCB_2 257, WCD 120, WCB_1 55, OTHER 22,
  WCA_1 18, other 14. These cover all wells, not just producers.
- 0 Delaware rows change.

**Blast radius.** It is a logic change, so `DROP … CASCADE`. Same chain as the override apply:
- bench_reference, codev_context, intel_formation_blueox, intel_pdp_support, producing_reference, wells_enriched;
- then formation_blueox_tvd, reconciled_inventory, **erebor_locations**, net_new_pdp, intel accuracy, dev_scenario;
- then box_scout_locations.

The sql/16 header's "nothing heavy depends on it" was stale and is corrected. The change rides the same window as the
override rows: `scripts.apply_formation_tag_overrides`, which now also asserts 0 Midland WOLFCAMP C rows still
Novi-sourced where Enverus has a value, then the quarterly tail it names. Off-hours, apps dark until the tail finishes.
Needs your "go apply".

**What-if screen (`tag_screen_whatif_wc/`).** The rule is applied to the producer tags in memory, then everything is
re-scored. sql/23 is not re-simulated; 0 corrected rows were affected.

| | Live tags | What-if |
|---|---|---|
| Producer tags changed | — | 258 (WCC → WCB_2 173, WCB_1 41, WCD 27, WCA_1 9, OTHER 5, MS 3) |
| Flagged | 1,526 (A 885, B 641) | 1,372 (A 859, B 513) |
| WCC flagged | 164 of 662 (24.8 %) | 19 of 404 (4.7 %), in line with the other Wolfcamp benches. **Partly circular, see §8.4** |
| Vendors disagree, sits in own band | 453 | 341 |
| Carded classes | 21 | 16 |

- **Retagged wells mostly sit cleanly.** Of the 258, only 6 flag again: WCB_2 → WCC (A).
- **The WCC rule-B classes disappear:** WCC → WCB_2 (75), WCC → WCB_1 (18), WCC → WCD (18) and WCC → WCA_1 (9).
- **Class states with your round-1 + 20a verdicts reused** (same well, same move):
  - Accept: WCB_2 → WCB_1 (A), 5/5.
  - Reject: WCA_1 → WCB_1 (6/10), WCB_1 → WCA_1 (4/10), DEAN → WCA_1 (B) (1/5), WCC → WCB_2 (A) (3/7),
    WCD → WCC (B) (0/5).
  - Round 2: WCB_1 → WCB_2, DEAN → WCA_1 (A), WCA_1 → DEAN, LSSH → WCA_1 (B), OTHER → WCD (B).
  - Pending: LSSH → WCA_1 (A), LSSH → WCB_1 (A), OTHER → WCA_1 (B), OTHER → WCB_1 (B), WCB_2 → WCC (A).
- **41 new cards**, none of them a well you've already seen. 13 sit in the two open groups (7 Discovery LS/SH, 6 with
  TVD < 2,500 ft); leave those blank until the Discovery group and the depth gate are decided.

### 8.3 What-if round 1 back (2026-10-27) → round 2 drawn

All 41 cards came back: 25 agree, 12 reject, 3 "bad tvd", 1 "suspect tvd". Every written verdict is kept verbatim in
`tag_screen_whatif_wc/cards_sample.csv`; the new ones carry `verdict_source = what-if round 1`. The 8 Discovery cards were
filled in too (all agree), so the two Discovery classes now decide on the count.

| Class | Flagged (cohort) | Agree / judged | BOX 7/10 | Strict (5/5 or ≥ 9/10) |
|---|---|---|---|---|
| WCB_2 → WCB_1 (A) | 103 (69) | 5/5 | accept | accept |
| LSSH → WCA_1 (A) | 18 (13) | 5/5 (+2 holds) | accept | accept |
| LSSH → WCB_1 (A) | 11 (10) | 5/5 (+5 holds) | accept | accept |
| WCB_1 → WCB_2 (A) | 94 (55) | 8/10 | accept | fail |
| OTHER → WCD (B) | 48 (7) | 7/10 | accept | fail |
| WCA_1 → WCB_1 (A), WCB_1 → WCA_1 (A), DEAN → WCA_1 (A, B), WCA_1 → DEAN (A), LSSH → WCA_1 (B), WCC → WCB_2 (A), WCD → WCC (B), OTHER → WCB_1 (B) | | 6/10, 4/10, 6/10, 1/5, 5/10, 4/10, 3/7, 0/5, 0/5 | reject | reject |
| WCB_2 → WCC (A) | 11 (7) | 2/5 | round 2: 5 new cards | |
| OTHER → WCA_1 (B) | 17 (16) | 0/1 (+8 holds) | pending: 4 new cards | |

- **The two strict-bar failures both split cleanly on something you can see:**
  - WCB_1 → WCB_2: the 2 rejects have the two smallest finite margins (2.1, 2.4); every agree is ≥ 9.6 or has no own
    band at all.
  - OTHER → WCD: all 3 rejects are Irion wells at 6,616–6,852 ft TVD (2 Moriah Canyon sands, 1 Walter); every agree is
    ≥ 8,254 ft.
  - Both splits were found after seeing the verdicts. A cut drawn there would be fitted to these cards, not tested by
    them.
- **WCB_2 → WCC (A) round 2 is a direct test of the drafted rule.** The 5 new cards are Sequitur "UNIVERSITY … WC" wells
  in Irion/Reagan:
  - Novi says WOLFCAMP C; Enverus says WOLFCAMP B LOWER, so the what-if retags them to WCB_2.
  - They sit 4–55 ft from the local WCC band.
  - Agrees here mean the trigger moves these wells the wrong way.
- **OTHER → WCA_1 (B) is a TVD-defect bucket, not a naming class.** Median margin is 6,225 ft, 8 of 9 verdicts are TVD
  holds, and 3 of the 4 new cards sit under 2,000 ft TVD. A rejected or uncarded class keeps its tags, and OTHER is
  outside every cohort. Parking it costs nothing; the proposed depth gate (§8.1) would remove it.
  **Parked 2026-10-27 (Michael)** via `box.tag_screen.PARKED`. A parked class gets no more cards and is never applied,
  so its tags stay. The verdicts already written are kept. The next round run drops its 4 blank cards; they stay in
  the current file until then, so the file you're editing is never rewritten under you.
- **These classes are on the what-if basis.** Override rows are seeded by api10 from whichever basis is live when they
  are written: after the sql/16 apply, or on live tags without it.

### 8.4 What-if round 2 back (2026-10-27) + consistency audit of every verdict

Round 2 is recorded: 9 verdicts with `verdict_source = what-if round 2`, 141 rows, 0 lost, 0 edited, 0 new cards.
WCB_2 → WCC (A) now stands at 2 agree, 7 reject, 1 hold → reject. OTHER → WCA_1 (B) stays parked; its 4 cards
were filled in and are kept as written. Michael asked to be told where his calls don't hang together. Found:

1. **The 5 Sequitur cards are the only cards whose what-if tag differs from the live tag.** All 5 are live WCC and
   what-if WCB_2.
   - "reject" on these cards means "they are WCB_2", which agrees with the drafted rule.
   - If the intent was "they are WCC, leave them", these are agrees, and the class reaches 7/10 → accept.
   - University 9 2107WC ("already showing WCC") and 2109WC (reject) are on the same pad, 35 ft apart in TVD.
   - Every vote except Enverus says WCC: the operator's "WC" suffix, Novi, the local WCC band (4–55 ft away) and
     sql/23 nearest.
2. **The drafted sql/16 rule misfires where operators name their landings.** The evidence is depth; the names only
   group the wells (2026-10-27, Michael: a suffix is a clue, depth against neighbours decides; see §8.5).
   - Ovintiv, Andrews: the operator's suffix groups sit at distinct depths: WA 9,268, WB 9,725, WC 10,195 and WD
     10,643 ft median TVD. The rule moves 14 of the 15 WC wells to WCB_1 (Enverus WOLFCAMP B UPPER). That puts wells
     at ~10,195 ft in the same bench as neighbours ~470 ft shallower.
   - Sequitur: 12 "…WC" wells go to WCB_2.
   - In all, 34 of the 258 retagged producers carry a WC landing suffix.
3. **The what-if WCC flag rate (4.7 %) is partly circular, and is withdrawn as evidence for the rule.**
   - 112 of the 258 retagged wells sat inside their own WCC band on live tags. After the retag, 84 of them also sit
     inside the new band, because their neighbours were retagged with them.
   - A whole neighbourhood relabelled together looks clean to the consensus detector either way (§1, the known
     blind spot).
   - The non-circular evidence for the rule remains §8.2's independent-band test, which is net positive but noisy.
4. **OTHER → WCD (B) accepts at 7/10 but holds three different populations:**
   - Deep and consistent: Glasscock, Upton, Reagan and Terry, 9,000–11,100 ft.
   - Shallow Irion/Schleicher, 6,616–7,308 ft: your Canyon-sand rejects, with 4 unseen members, 2 of them Moriah.
   - A Diamondback Johnson Ranch / George Holt Glass pad in Martin, first production 2025-10-01: 7 wells, all at
     TVD 10,605 ft, with name series 24xx, 26xx, 28xx and 43xx. This is a pad-copied TVD, not 7 measurements.
   - Wholesale it would move all three.
5. **Discovery: accepting the two LSSH (A) classes moves 14 of 85 Discovery LSSH producers** (5 → WCA_1, 9 → WCB_1).
   - The other 71 stay LSSH, among them 43 unflagged LS-named wells. 34 of the 85 are in Midland County, where LS
     depths looked right (§8.1).
   - One SH-named well goes to WCA_1.
   - The classes are not the Discovery group call: that would be a separate operator × area decision.
6. **Own-destination calls that no class carries:** Cypert B 57-51 221 → WCD and Coachwhip 17-20 261 → WCD. Under
   convention (a) they land only as single-well `carded <date>` rows.
7. **Minor:**
   - In OTHER → WCB_1 (B), 3 of the 5 rejects are wells under 1,100 ft TVD (marked "bad tvd" elsewhere). Same
     outcome: tags stay.
   - Accepting both B1/B2 reverse classes creates 2 local inversions. One is FEE 'BN' 2110WB → WCB_1 at 9,992 ft,
     113 ft below 2101WB → WCB_2 at 9,879 ft, 0.53 mi apart.
   - Seeding rule (both bars): a well whose own card says reject is never moved by its class's accept.

### 8.5 Sequitur cards re-called as bench codes (2026-10-27)

Michael rewrote the ambiguous verdicts as bench codes:
- University 43 1010WC and 1014WC, and University 9 2107WC, 2109WC and 2914WC → **WCC**.
- University Lucy 0103H → WCB_2. Same meaning as its earlier "reject".

The re-run kept every row in place, lost nothing, and drew 0 new cards. **WCB_2 → WCC (A) is now 7/10: accept at the
BOX bar, fail at the strict bar.**

- **These are calls against the drafted sql/16 rule.** All five are Novi WOLFCAMP C wells the rule retags WCB_2. With
  Ovintiv's 14 WC → WCB_1 (§8.4 item 2), the rule now misfires on every WC-named well whose depth has been looked at.
- **Mayer 4512WB / 4512WC: the names are swapped, not the depths.** I first read this pair as a TVD swap. Michael's
  call (2026-10-27): depth against local offsets wins over the suffix.
  - 4512WB at 7,219 ft sits with the local WC wells (7,060–7,172 ft) → **WCC**. The 20a agree stands, and the class
    stays 7/10.
  - 4512WC at 6,812 ft sits with the local WB wells (6,773–6,809 ft) → **WCB_1**. It is not on any card, so the call is
    recorded in `tag_screen/well_calls.csv` with Cypert B 221 and Coachwhip 17-20 261.
  - A plausible story (Michael, conjecture, no data): both were permitted and named for their targets, then one landed
    shallower after a casing-plan change while drilling.
  - Both vendors say WOLFCAMP C for 4512WC, likely copied from the permit. So two vendors agreeing on a named well
    does not confirm its landing. Only depth can flag such a well, and here it did not, because of a detector defect:
  - **Bad-TVD witnesses poison the local bands.** 4512WC has 8 WCB_1 witnesses within 1.5 mi, but two of them are
    Mayer 4509H / 4511H at 841 / 845 ft TVD. Those two push the WCB_1 IQR to 1,588 ft, past the 150-ft coherence cap,
    so the band is dropped.
  - Without them, the band is 6 wells, median 6,799 ft, IQR 26 ft. 4512WC then sits 13 ft from it and flags
    WCC → WCB_1. 4512WB flags WCB_2 → WCC either way.
  - **Midland-wide (scratch re-score, live tags):** 20 witnesses have TVD < 2,500 ft. Excluding them restores a band
    for 57 wells, changes the status of about 20, and adds 3 Wolfcamp flags (WCB_1 → WCA_1 ×2, and this
    WCC → WCB_1).
  - The fix is the §8.1 depth gate applied to witnesses, not just subjects. It changes `box.bench_qc` for every
    basin, so it is not built: your call.
- **The file was saved from Excel.** Excel reformatted dates (m/d/yyyy), booleans (TRUE/FALSE) and float precision.
  The screen reads only api10, verdict and the destination, so nothing is affected. Rows the run regenerates come back
  clean; the 22 carried free-text rows keep Excel's formatting.

### 8.6 Consensus v2.2: TVD < 2,500 ft is never a witness (built 2026-10-27, Michael's ask)

`box.bench_qc.MIN_WITNESS_TVD_FT = 2_500`. A well that shallow is a TVD-defect row (the TVD = MD class, §8.1). It no
longer counts as depth evidence for its neighbours' bands. It is still scored as a subject. Test:
`test_score_consensus_shallow_tvd_is_not_a_witness`, built on the Mayer case, which fails without the gate. Full suite:
763 passed, 46 skipped.

| | Midland (as of 2026-09-01) | Delaware (as of 2026-08-01) |
|---|---|---|
| Producers with TVD < 2,500 ft (witnesses before) | 67 (20) | 101 (57) |
| Detector status / suggestion changed | 24 | 91 |
| BOX class-rule outcome changed (`qc_rule.apply_rule`, + D136 in the Midland) | **0** | **5**, all BS3_C → BS2_S, 1 in the D9 cohort |
| Tag screen, flagged | what-if 1,372 → 1,374; live 1,526 → 1,530 | — |

- **Midland 20a deliverable: unchanged.** 0 rule outcomes move, D136 still reassigns the same 232, and the tag-screen
  classes and every verdict are unchanged.
  - The only class-size moves are WCB_1 → WCA_1 (A) 64 → 63, WCC → WCB_1 (A) 1 → 2 and OTHER → WCB_1 (A) 3 → 5.
  - Mayer 4512WC now flags WCC → WCB_1 (A), with sql/23 as the second vote. That class has 1 cohort well, so it is
    listed, not carded. The call is in `tag_screen/well_calls.csv`.
- **Delaware: the 5 wells all gain a BS2_S band that bad-TVD witnesses had poisoned:**
  - Makers Mark Fed Com 210H
  - Mesquite 2 State Com 003H
  - Quien Sabe 25 Fed 001H
  - Devon 6 Fee 002H
  - Poker Lake Unit 15 TWR 305H (cohort; sql/23 and GOR also vote BS2_S)

  All five were first judged at step 1 (2026-10-06). The pool refresh keeps judged wells' calls (the frozen
  universe), so **no current or record pool changes.** 305H is already in `pool-2026-10-26/wells_final_BS2_S.csv`.
  The gate reaches only wells first judged at a later refresh (13c onward).
- **Ratified as D138 (Michael, 2026-10-27): v2.2 holds in both basins; the Delaware output change is accepted.** This had conflicted with D134 (B), which applies the Delaware class rule "as written", and D135, which accepted the
  parameterization as "Delaware bit-identical". The class rule is untouched; the detector feeding it changed (91
  Delaware statuses, 5 rule outcomes). Future refreshes in both basins run on v2.2.

### 8.7 Depth-only check of the drafted WOLFCAMP C rule (2026-10-27) → `tag_screen_whatif_wc/depth_check.csv`

**Question.** The drafted sql/16 rule hands every Novi-WOLFCAMP-C-sourced Midland tag to Enverus. Depth alone (no names,
vendors, GOR or sql/23), does each of the 258 producers it retags sit where its new tag says?

**Jury.** Consensus v2.2 witnesses minus every well Novi calls WOLFCAMP C (538 removed, 26,248 left; a ratified override
stays in). Neither the live nor the what-if tag can vote for itself, and the jury is the same under both.
- **Local:** coherent jury bands within 1.5 mi (2, then 3 mi when none). The new tag is confirmed when it is the nearest
  band within 120 ft, and contradicted when its band exists but sits more than 120 ft away.
- **Ladder** (regional fallback, only where the new tag has no local band): depth below the local jury WCA_1 band,
  snapped to the nearest rung. Rungs are the medians over v2.2 witnesses: WCB_1 259 ft, WCB_2 457 ft, **Novi-WC-tagged
  WCC 768 ft ("WC slot")**, WCD 1,429 ft. The 53 WCC wells NOT tagged by Novi's WOLFCAMP C sit at 470 ft, which is
  WCB_2 depth.

**Result (as of 2026-09-01).** Depth backs 31 % of the rule's moves and opposes 35 %; a third can't be measured.

| New tag (wells) | Depth backs the move | Sits in the WC slot | Contradicted / other bench | Conflicting | Undecided |
|---|---|---|---|---|---|
| WCB_2 (173) | 62 (31 local, 31 ladder) | 29 | 27 | 2 | 53 |
| WCB_1 (41) | 17 (12 local, 5 ladder) | 3 | 10 | 1 | 10 |
| WCD (27) | 2 | 13 | 4 | 0 | 8 |
| WCA_1 (9) | 0 | 2 | 0 | 0 | 7 |
| MS (3) | 0 | 1 | 2 | 0 | 0 |
| OTHER (5) | 0 | 0 | 0 | 0 | 5 (OTHER is never a witness) |
| **All 258** | **81** | **48** | **43** | **3** | **83** |
| D9 cohort (118) | 36 | 30 | 12 | 1 | 39 |

- **The WCD, WCA_1 and MS destinations are wrong by depth.** The WCD-bound wells sit a median 797 ft below WCA_1, about
  630 ft above the WCD rung. The WCA_1-bound wells sit about 800 ft below their own WCA_1 band, and the MS-bound wells
  1,870 ft below MS.
- **WCB_2 is split.** Where a local jury WCB_2 band exists (72 wells): 31 sit in it, and 40 sit 122–646 ft below it
  (median 220 ft), deeper than every non-WC neighbour lands.
- **Novi's WOLFCAMP C marks a real, separate landing.** It sits about 310 ft below WCB_2 and about 660 ft above WCD,
  and no other label occupies that depth. The rule erases that call for every well, both the ones the depth backs and
  the ones it doesn't.
- **The ladder is regional and the bench spacing varies** (D136 north vs south). A ladder call is weaker than a local
  one.

**Against your cards** (28 of the 258 were carded):
- 20 have a depth call, and it matches your verdict on 15.
  - 9 moves you accepted: Brook A-2 8H, North Brook NE45S 19H, Wilde Garner 14WC 3H, the University 8-10 E/W 8WCs,
    Millie B Leon C 05H, Winchester 73 6-7 H 1W, University Central 0824OH, Marion V. Benge A18 2513CH.
  - 6 keeps: Muhly C 1612 5AA, Hartgrove 0401 2HU, and the Sequitur 1010WC / 1014WC / 2107WC / 2109WC.
- They differ on 5:
  - Bopie 2734 A 301H: depth says WC slot, you said WCB_2.
  - Bandolero 5-8 H 1W: depth says not WCD, you said WCD.
  - Chaparral 110 MIPA H110UH: depth says WC slot, you said WCD.
  - Parks, Roy 316CH: the ladder says WCB_1, you said WCB_2.
  - University 9 2914WC: local depth is 282 ft below WCB_2, agreeing with your WCC; the ladder says WCB_2.
- **Your live-basis cards on the same moves** (rule B, 5 each):
  - WCC → WCA_1: 0/5.
  - WCC → WCB_1: 4/5.
  - WCC → WCB_2: 4/5.
  - WCC → WCD: 4/5.

  Depth and your cards agree that WCA_1 is wrong. They disagree on WCD.

**Recommendation: don't apply the rule; take the WCC moves well by well.**
- Drop the sql/16 trigger from #202 (the trig CTE, its test pin and the apply-script assertion). Keep this folder as
  evidence.
- Return the screen to live tags. WCC → WCA_1 (B) is rejected at 0/5. WCC → WCB_1 / WCB_2 / WCD (B) each sit at 4/5, so
  the sequential rule draws their round 2 (10 cards each), with this depth call shown on each card as a reference.
- Classes you judged on the what-if basis carry over only where the same well makes the same move under live tags. The
  re-run will list which ones do.
- Your call: this reverses a draft you asked for.

### 8.8 Rule dropped; the screen is back on live tags (2026-10-27) → `tag_screen/` round 2

**Michael (2026-10-27): drop the drafted WOLFCAMP C rule (§8.7).**
- sql/16, sql/31 and `apply_formation_tag_overrides` are back to main's logic. Only the corrected sql/16 header (a logic
  change is a DROP CASCADE reaching erebor_locations) is kept.
- `tag_screen.NOVI_COARSE_BY_BASIN` survives for `--whatif` only. A test now pins that sql/16 carries none of it.
- `tag_screen_whatif_wc/` stays as evidence. Nothing was ever applied.

**Re-run.** The live-tag screen, consensus v2.2, as of 2026-09-01:
- 1,530 flagged (A 889, B 641); 21 classes carded.
- Prior verdicts are read from the 20a cards, the live round-1 cards and the what-if cards. A card counts only for the
  move it was drawn for (same well, same destination).
- **New: a verdict written as a bench code is your call on the well** and answers whatever move is proposed now.
- 0 of the 126 round-1 verdicts were dropped or changed. Your 92 round-1 verdicts are now stamped `round 1`.

**What carried from the what-if cards:** 42 of your 50 verdicts (38 round 1, 4 round 2), across 10 classes. The 8 that
did not:

| Well | What-if card | Your verdict | Live tags |
|---|---|---|---|
| University 43 1010WC / 1014WC, University 9 2107WC / 2109WC / 2914WC (Sequitur) | WCB_2 → WCC | WCC | Tag WCC, sits in its own band, not flagged. Your call holds with no override. |
| University Lucy 0103H | WCB_2 → WCC | WCB_2 | Tag already WCB_2 (Enverus), sits in its band. Nothing to do. |
| Elwood #16-21 4403H | WCB_1 → WCB_2 | agree | Tag WCB_1, ambiguous (4 ft from WCB_2, 63 ft from WCB_1). Not flagged → **added to `tag_screen/well_calls.csv`** |
| Horton B 2223 1HA | WCA_1 → DEAN | agree | Tag WCA_1, ambiguous (96 ft from DEAN, 134 ft from WCA_1). Not flagged → **added to `well_calls.csv`** |

**Class states** (BOX 7/10 gate, sequential 5 then 10):

| State | Classes (agree / judged) |
|---|---|
| Accept | WCB_2 → WCB_1 (A) 6/6 · LSSH → WCA_1 (A) 5/5 · LSSH → WCB_1 (A) 5/5 · OTHER → WCD (B) 7/10 |
| Round 2 | **WCC → WCB_2 (B) 4/5, WCC → WCB_1 (B) 4/5, WCC → WCD (B) 4/5** (5 new cards each) · WCB_1 → WCB_2 (A) 7/9 (1 new card) |
| Reject | WCC → WCA_1 (B) 0/5 · WCA_1 → WCB_1 (A) 6/10 · WCB_1 → WCA_1 (A) 4/10 · WCC → WCB_2 (A) 6/10 · DEAN → WCA_1 (A) 6/10 and (B) 1/5 · WCA_1 → DEAN (A) 4/9 · LSSH → WCA_1 (B) 4/10 · WCB_1 → WCC (A) 1/5 · WCD → WCC (B) 0/5 · WCB_2 → WCC (A) 3/10 · OTHER → WCB_1 (B) 0/5 |
| Parked | OTHER → WCA_1 (B) |

- **Changes from the what-if basis:**
  - WCB_1 → WCB_2 (A) needs one more card: the live class is 7/9, not 8/10.
  - WCB_2 → WCC (A) is now a reject. On the what-if basis that class held the rule's retags moving back; on live tags it
    holds the 10 natural WCB_2 → WCC wells, 3/10.
- **16 new cards.** These are the rows with a blank verdict in `tag_screen/cards_sample.csv`: Excel rows 132–137 and
  155–164.
  - Each WCC card carries a **depth only** line: the §8.7 result, the jury bands and the offsets.
  - The 15 WCC cards split: 3 depth backs the move, 3 sit in the WC slot, 2 not the new tag, 1 other rung,
    6 undecided.
- OTHER → WCD (B) still accepts at 7/10. The Irion Canyon-sand and Diamondback copied-TVD subgroups (§8.4) remain open.

### 8.9 Live round 2 back (2026-10-28): every carded class decided

Your 16 verdicts are stamped `round 2` in `tag_screen/cards_sample.csv`. The re-run draws 0 new cards, so the screen
is finished.

| Class | Round 2 | Final | State |
|---|---|---|---|
| WCC → WCB_1 (B) | 4/5 | **8/10** | **accept** (18 wells, 10 cohort) |
| WCC → WCD (B) | 4/5 | **8/10** | **accept** (18 wells, 10 cohort) |
| WCC → WCB_2 (B) | 2/5 | 6/10 | reject (75 wells) |
| WCB_1 → WCB_2 (A) | 0/1 | 7/10 | accept, exactly at the gate (95 wells) |

Every other class is unchanged from §8.8. Accepted on live tags: WCB_2 → WCB_1 (A) 6/6, WCB_1 → WCB_2 (A) 7/10,
LSSH → WCA_1 (A) 5/5, LSSH → WCB_1 (A) 5/5, OTHER → WCD (B) 7/10, WCC → WCB_1 (B) 8/10, WCC → WCD (B) 8/10.
OTHER → WCA_1 (B) stays parked.

How the §8.7 depth-only call read on the 15 WCC cards against yours:

| Class | You moved | Depth backs the move | Depth disagrees | Depth undecided |
|---|---|---|---|---|
| WCC → WCD | MB 702H, Knight 140 H140UH, John B 05WD, Conroe 15-22 3H | Conroe (ladder) | **MB, Knight, John B: WC slot (stays WCC)** | — |
| WCC → WCB_1 | University 8-10E 9WC, 8-4 WF 8WC, 8-4 WE 7WC, Amoco-Holt 2WB | 8-10E (local band) | — | the other 3 |
| WCC → WCB_2 | Affirmed N405H, Ponderosa East C 10H | — | Ponderosa C: not WCB_2 (139 ft above the local band) | Affirmed |

On the wells you kept WCC:
- Depth agrees on Mayra 8 16BL, which reads as not WCB_2.
- University East 4106CH reads WCB_1 on the ladder.
- Thomas and University West are undecided by depth.

**Flag: WCC → WCD passed 8/10, but depth says 3 of your 4 round-2 moves sit in the Novi "WC slot",** the
~768 ft-below-WCA_1 landing that §8.7 found distinct from WCD (1,429 ft).
- The WC slot is a depth band, not proof the tag is right. Your cards read the gunbarrel, which the ladder does not.
- A class accept also moves the 8 wells nobody carded. Depth reads them as:

  | Class (8 uncarded wells each) | Backs the move | WC slot | Not the new tag / other rung | Undecided |
  |---|---|---|---|---|
  | WCC → WCD | 0 | 0 | 3 | 5 |
  | WCC → WCB_1 | 3 | 2 | 2 | 1 |

  Across the 18 wells in each class, depth backs 2 of the WCD moves and 8 of the WCB_1 moves.
- I have not changed anything. Options for you:
  - Accept as carded (convention (a)).
  - Seed only the carded wells of these two classes.
  - Card the 8 uncarded wells of WCC → WCD.

**Ponderosa East pair: resolved 2026-10-28 (Michael), both WCB_2.**
- The first save had A 7H (8,698 ft) at WCB_2 and C 10H (8,816 ft) at WCB_1, which is inverted by depth.
- Michael re-saved C 10H as WCB_2, so both Crescent wells (0.24 mi apart, Upton) now carry the same bench.
- Depth alone reads them as neither cleanly:
  - A 7H sits 212 ft from both the local WCA_1 band (8,486 ft) and the local WCB_2 band (8,910 ft); the ladder says WCB_1.
  - C 10H sits 139 ft above the local WCB_2 band (8,955 ft).
- The card call stands. WCC → WCB_2 (B) moves to 6/10, still a reject, so C 10H lands only as a single-well card
  (see the conflict below).

**What "go apply" would seed on live tags (prospective, recomputed at seed time).** Convention (a) applied to
`cards_sample.csv`:
- **296 rows from the 7 accepted classes**, out of 312 flagged wells.
  - 46 carded agrees, plus 1 carded own-bench call (Ponderosa East A 7H → WCB_2, inside WCC → WCB_1).
  - 249 class-accepted wells nobody carded.
  - 16 left out: your rejects and holds.
  - 159 of the 296 are cohort wells.
- **2 own-bench calls outside the accepted classes:** Cypert → WCD and Coachwhip → WCD (§8.4 item 6).
- **3 chat or what-if calls** in `well_calls.csv`: Mayer, Elwood, Horton.

**Decided 2026-10-28 (Michael): carded agrees in rejected classes ARE corrected.** 41 cards agree with the proposed
move inside classes that were rejected, e.g. 6 in WCA_1 → WCB_1 (A). This includes Affirmed N405H and Ponderosa East C
10H, which are written as bench codes.
- A failed class means its move is not safe for the wells nobody looked at. It does not overturn the wells you did
  look at.
- Each of the 41 lands as a single-well `carded <date>` override, the same as the own-bench calls (§8.4 item 6).
  Their uncarded classmates stay put.
- Convention (a) is amended to match (§8 above).

**The seed on "go apply" is now 342 rows** (prospective, recomputed at seed time):

| Source | Rows |
|---|---|
| Accepted classes | 296 |
| Carded agrees in rejected classes | 41 |
| Own-bench calls outside the accepted classes | 2 |
| Chat / what-if calls | 3 |

The WCC → WCD (B) depth flag above is resolved by a full review (§8.10), which replaces these totals: the seed is 338.

### 8.10 WCC → WCD (B): full review (Michael, 2026-10-28) → `tag_screen/` 8 new cards

**Michael: card the 8 others.** The class passed its sample at 8/10, but depth puts 3 of the 4 round-2 moves in the Novi
WC slot (§8.9). The class now gets a full review: every one of its 18 wells is carded, and each card decides only its own
well. The class acceptance no longer moves anybody.

**Tooling.** `box_tag_screen --review-all "WCC->WCD (B)"` cards every flagged well of the named class, using
`tag_screen.card_target`. The class shows the state "full review" in `cards.html` and `summary.json`.
- The re-run is byte-identical on a second pass, and all 184 earlier verdicts are unchanged.
- The new cards are stamped `round 3 (full review)` once filled.

**The 8 cards** are the rows with a blank verdict in `tag_screen/cards_sample.csv`, Excel rows 186–193. Each carries
the §8.7 depth-only line. All 8 are Novi WOLFCAMP C, Enverus WOLFCAMP D:

| Well | Operator, county | TVD | Depth only |
|---|---|---|---|
| Cross Bar Ranch H 3025WD | ConocoPhillips, Martin | 10,056 | other rung (WCB_2 on the ladder) |
| Scarlet Unit 2 2988NH | Exxon, Martin | 9,077 | other rung (WCB_2 on the ladder); local WCD band 9,876 |
| Scharbauer Ranch 302H | Exxon, Martin | 10,638 | undecided |
| Mabee J.E. 'B' NCT-2 1507H | ConocoPhillips, Martin | 10,659 | undecided |
| Barracuda 45 2H | Apache, Glasscock | 8,735 | not WCD (the local WCD band is 9,379 ft, 644 ft below the well) |
| Devaca 11H | Permian Resources, Irion | 7,217 | undecided |
| Sugg 8A-1910 1H | Compass, Irion | 7,434 | undecided (no jury within 3 mi) |
| Red Headed Stranger 1H | ConocoPhillips, Terry | 10,058 | undecided (no jury within 3 mi) |

**Back 2026-10-28.** You called 6 of the 8 and left 2 blank. The blanks are recorded as holds in your words:
"hold: too few wells in the area to infer anything" (`verdict_source` = Michael in chat 2026-10-28). A hold is never
counted, so those tags stay, and the re-run draws 0 new cards.

| Well | Your call | Depth only |
|---|---|---|
| Scharbauer Ranch 302H | WCD | undecided |
| Mabee J.E. 'B' NCT-2 1507H | WCD | undecided |
| Sugg 8A-1910 1H | WCD | undecided (no jury) |
| Scarlet Unit 2 2988NH | **WCB_2** | WCB_2 on the ladder: agrees |
| Cross Bar Ranch H 3025WD | WCC (stays) | WCB_2 on the ladder; also not WCD |
| Barracuda 45 2H | WCC (stays) | not WCD: agrees |
| Devaca 11H | hold | undecided |
| Red Headed Stranger 1H | hold | undecided (no jury) |

Depth contradicts none of your 8 calls on the WCD question.

**The whole class, card by card (18 wells):**
- 11 move to WCD: 4 from round 1, 4 from round 2, 3 from this round.
- 1 moves to WCB_2 (Scarlet).
- 4 stay WCC: University Orange, University West, Cross Bar, Barracuda.
- 2 are held.

The 8/10 sample would have moved all 18 to WCD. The full review moves 11 and sends 1 elsewhere.

**Prospective seed on "go apply": 338 rows** (recomputed at seed time):

| Source | Rows |
|---|---|
| The 6 accepted classes (WCC → WCD is no longer one) | 280 |
| WCC → WCD full review: 11 agrees + Scarlet → WCB_2 | 12 |
| Carded agrees in rejected classes | 41 |
| Own-bench calls outside the accepted classes (Cypert, Coachwhip) | 2 |
| Chat / what-if calls (Mayer, Elwood, Horton) | 3 |

Correction to §8.9's tallies: `well_calls.csv` has 5 rows, but Cypert and Coachwhip are counted once, as own-bench calls.

### 8.11 Override seed built (2026-10-28, Michael: build the seed) → `seeds/formation_tag_overrides.csv`

**Nothing is applied.** The seed and sql/44 are repo changes on #202. The warehouse sees them only on "go apply".

**Builder.** `python -m scripts.box_tag_seed --screen docs/box/step20a-2026-10-26/tag_screen [--write] [--check-live]`
uses `tag_screen.override_seed`, which applies convention (a) as amended in §8.9–8.10:
- A card decides its own well, whatever its class did:
  - "agree" moves it to the card's destination;
  - a bench code moves it to that bench (nothing when the code is the live tag);
  - reject, hold or free text leaves it alone.
- An accepted class moves its uncarded wells to the class destination.
- Full-review, parked and rejected classes move no uncarded well.
- `well_calls.csv` rows land as written. A well that also has a card must carry the same call, or the build fails.

Every row's note ends "tag screen step 20a", so a re-run replaces exactly this block. The 98 Delaware rows are untouched:
the diff is 338 added lines and nothing else.

**The 338 rows:**

| Kind | Rows |
|---|---|
| class-accepted (uncarded wells of the 6 accepted classes) | 241 |
| carded (your own card) | 94 |
| direct / what-if calls (Mayer, Elwood, Horton) | 3 |

| was → now | DEAN | WCA_1 | WCB_1 | WCB_2 | WCC | WCD | total |
|---|---|---|---|---|---|---|---|
| DEAN | | 7 | | | | | 7 |
| LSSH | | 20 | 6 | | | | 26 |
| OTHER | | | | | | 47 | 47 |
| WCA_1 | 5 | | 6 | | | | 11 |
| WCB_1 | | 4 | | 93 | 1 | | 98 |
| WCB_2 | | | 104 | | 3 | | 107 |
| WCC | | | 17 | 14 | | 11 | 42 |
| total | 5 | 31 | 133 | 107 | 4 | 58 | 338 |

**Live check, read-only (2026-10-28):**
- All 338 api10s exist in `curated.formation_blueox`.
- Every row's `was` equals the live tag, so no tag has drifted since the screen's snapshot.
- None is already a ratified override.
- The live `ref.formation_tag_overrides` holds 98 rows, the same as the seed outside this block.

**sql/44 amended in the same commit** (convention (a)):
- The header now names both kinds of ratification, well-by-well and class-accepted, with their note formats, and records
  Batch 3.
- The table COMMENT says the same. It reaches the live table only when sql/44 is re-run.
- `docs/data_dictionary.html` is generated from the live comments, so it is regenerated after the apply.

**Tests:**
- `test_tag_screen_override_seed` checks the rules on a synthetic screen.
- `test_seed_20a_block_matches_the_screen` pins the committed block to what the finished screen builds.
- The existing `test_formation_tag_overrides` checks (unique api10s, crosswalk vocabulary, a real change, a note on every
  row) pass on all 436 rows.

### 8.12 The two apply paths (2026-10-28, read-only mapping; nothing applied)

Both paths land the same 436 override rows and the same tags. They differ in downtime, in what SQL runs, and in how much
can go wrong.

**What depends on `curated.formation_blueox` (live `pg_depend`, 2026-10-28).** 11 matviews and 3 plain views. Every
matview has a plain-column, non-partial UNIQUE index, so every one can `REFRESH ... CONCURRENTLY`.

| Level | Object | Rows | Refresh time | Source of the time | Nightly? |
|---|---|---|---|---|---|
| 0 | formation_blueox | 95,346 | 3–5 s | etl_log, 10 nights | yes |
| 1 | bench_reference | 38,264 | ~1–2 s | read-only query timing today (0.8 s) | **no** |
| 1 | producing_reference | 61,171 | 5–6 s | etl_log | yes |
| 2 | formation_blueox_tvd | 61,128 | 23–24 s | etl_log | yes |
| 2 | intel_formation_blueox | 322,402 | ~15–30 s | read-only query timing today (12.8 s) | **no** |
| 3 | codev_context | 64,640 | 98–104 s | etl_log | yes |
| 3 | reconciled_inventory | 257,397 | ~22 s | live refresh 2026-10-15 | **no** |
| 3 | net_new_pdp | 0 | ~3 s | read-only query timing today | **no** |
| 3 | intel_pdp_support | 257,397 | **~50 min** | CONCURRENTLY smoke 2026-09-11 | **no** |
| 3 | intel_forecast_accuracy_vintage | 110,635 | 54–84 s | etl_log | yes |
| 4 | erebor_locations | 317,913 | 8–10 s | etl_log | yes |
| 4 | intel_forecast_accuracy | — | 1–2 s | etl_log | yes |
| views | wells_enriched, dev_scenario, box_scout_locations | — | live | — | — |

The five rows marked **no** are the quarterly-owned ones: the nightly never refreshes them. So loading the seed and
waiting for the nightly is not an option. The nightly would move PDP tags while `bench_reference`, the PUD/RES stick tags
(`intel_formation_blueox`), `reconciled_inventory` and `intel_pdp_support` stayed on the old tags. erebor would then join
mixed-vintage tags.

**PUD stick tags move too.** `intel_formation_blueox` (sql/19) tags each Novi PUD/RES stick from the TVD-nearest of its
12 nearest `bench_reference` laterals. `bench_reference` is built from `formation_blueox`, so re-tagging 338 Midland PDP
wells re-tags some Midland Wolfcamp sticks near them. That is the intended effect: the Highgrade and BOX location
universe follow corrected offsets. But the count is not knowable without running sql/19. Either path reports it
before/after.

**Path A — DROP CASCADE rebuild (`apply_formation_tag_overrides` + the quarterly tail).**
- Steps:
  1. sql/44 reload.
  2. sql/16 re-create. Its first statement drops all 11 dependent matviews and 3 views.
  3. `apply_intel_formation_blueox` (sql/14, sql/18, sql/19).
  4. `apply_reconciled_inventory` (sql/06, 20, 23, 47, 50, 68).
  5. sql/25.
  6. `apply_intel_pdp_support`: 50 min build plus a 50 min CONCURRENTLY smoke.
  7. `apply_intel_forecast_accuracy` (sql/26, 38, 43).
  8. `apply_erebor_locations` (sql/22, 69, 31).
  9. sql/26.
- **erebor is dark for ~1 h 45 m.** `erebor_locations` is gone from step 2 until step 8; the 2026-09-11 Phase 1
  precedent was ~1 h 45 m. narvi and the deal-intake runner lose `wells_enriched` and `reconciled_inventory` for most of
  that time too. Wall clock is ~2–2.5 h.
- **The tail the script documents is incomplete.** `apply_formation_tag_overrides`'s docstring lists only
  `apply_intel_formation_blueox -> apply_reconciled_inventory -> apply_intel_pdp_support -> apply_erebor_locations -> sql/26
  -> sql/31`. It is missing:
  - sql/25 (`net_new_pdp`). Without it, `apply_erebor_locations` fails, because sql/22 reads `net_new_pdp`.
  - `apply_intel_forecast_accuracy` (sql/38 + sql/43). Without it, both accuracy matviews stay missing. The nightly
    lists them as optional, so it would skip them silently.

  The quarterly skill's order has both. The docstring needs fixing either way.
- It re-creates ~14 objects from the repo files on whichever checkout runs it. Any repo-vs-live drift in any of those
  files lands with it. The sql/16 SELECT body on this branch is identical to main; the header diff is comments only.

**Path B — content refresh (sql/44 reload + `REFRESH ... CONCURRENTLY` down the chain). Recommended.**
- Steps:
  1. Reload sql/44 in **one transaction** (TRUNCATE + COPY + COMMENT). The current script autocommits the TRUNCATE before
     the COPY, which leaves an empty-table gap.
  2. Snapshot the before counts of the Midland stick tags.
  3. Refresh in level order:

     `formation_blueox` → `bench_reference`, `producing_reference` → `formation_blueox_tvd`, `intel_formation_blueox` →
     `codev_context`, `reconciled_inventory`, `net_new_pdp`, `intel_forecast_accuracy_vintage`, `intel_pdp_support` →
     `erebor_locations`, `intel_forecast_accuracy`.
  4. Verify: 436/436 overrides land with source `ratified_override`; row identities hold (`reconciled_inventory` = the
     mapped stick universe; `erebor_locations` unchanged in count); stick tags before → after.
- **Nothing goes dark.** CONCURRENTLY keeps every object readable. Wall clock is ~55–60 min, almost all of it
  `intel_pdp_support`.
- For that ~55 min, erebor shows a **mixed state**. PDP tags are already new through `wells_enriched`. The location
  layer (`erebor_locations`) stays old until its 10 s refresh at the end. Ordering erebor last keeps that layer
  internally consistent.
- **No DDL** beyond sql/44's idempotent CREATE IF NOT EXISTS and COMMENT. **No definition changes**: the live view
  bodies are reused as they are, so repo drift cannot ride along. No index rebuild either, so no sql/26 re-run is needed.
- **Built 2026-10-28 (Michael: write it).** `python -m scripts.apply_formation_tag_overrides --refresh` runs it. The
  script now requires a mode: `--refresh` or `--rebuild`. With no mode it refuses, so a plain call can no longer
  DROP CASCADE by accident.
  - The `--rebuild` docstring tail is fixed: it now includes sql/25 and `apply_intel_forecast_accuracy`.
  - **Preflight, before any write:**
    - reads the live `pg_depend` graph;
    - checks that the 12-matview `CHAIN` is exactly the set below formation_blueox;
    - checks that the order respects every edge, including edges through plain views;
    - refuses if any `meta.etl_log` run started in the last 6 h is still `running`.
  - **Verify, after the refresh:**
    - 436/436 overrides land with source `ratified_override`;
    - every PDP tag that moved is an override row (none outside the seed);
    - stick-tag moves by basin, as was → now;
    - reconciled_inventory status moves;
    - row counts before → after for all 12 matviews.
  - `--refresh --dry-run` runs the preflight and diffs the seed against the live table, inside one read-only
    transaction.
  - **Dry run against live, 2026-10-28 ~14:50 UTC:** preflight OK (12 matviews, order valid); seed 436 vs live 98 →
    add 338, change 0, remove 0. Nothing was written.
  - Tests: 6 new DB-free tests in `tests/test_formation_tag_overrides.py`:
    - the CHAIN against the live 2026-10-28 edge list;
    - seeing through views;
    - order, missing and extra matviews;
    - the sql/44 copy split;
    - the seed diff and tag moves;
    - the mode is required.

    Full suite: 774 passed, 46 skipped.

**Either path:**
- Run it outside the nightly. The cron says 11:15 UTC, but the run actually lands ~15:00–17:30 UTC (2026-10-27 refreshes
  ran 16:47–17:14 UTC), so ~10:00–12:30 CDT. A refresh colliding with the nightly's CONCURRENTLY refresh of the same
  matview waits on its lock.
- Then:
  1. Regenerate the data dictionary (it picks up the new sql/44 table comment).
  2. Re-run 20a on the corrected tags.
  3. Then the storage go.

### 8.13 Vendor drift before the apply, and four inspection calls (2026-10-29)

**What the pre-apply check found.** Two nightlies after the screen, the live tags of 15 of the 338 seed wells no longer
matched their `was` tag. Across all 28,859 scored Midland wells, 191 tags (0.7 %) moved between the 10-27 snapshot and
10-29.
- 13 of the 15 now carry exactly the seed's corrected tag: the vendor came round to MM's call. Those rows stay; they lock
  the tag in.
- 2 class-accepted wells nobody had carded had moved elsewhere: Cross Bar Ranch H 1722LS and Mustang Draw 44SH.

**Cause: the well-name suffix leaks into Novi `Formation`.**
- Novi `Formation` copies the name suffix. Novi `GridFormation` and Enverus `ENVInterval` track depth.
- sql/16 trusts Novi unless its value is a coarse trigger, so a suffix-derived LS / MS / WD label wins outright.
- A suffix-derived WOLFCAMP A / B defers to Enverus, which on Cross Bar Ranch H picks Dean at the Dean / WCA boundary.

On Cross Bar Ranch H (ConocoPhillips) the lease bands are MS 8,560–8,670 ft, LSSH 9,110–9,390 ft, WCA 9,530–9,770 ft and
WCB 9,760–9,940 ft.

| Well | TVD (ft) | Novi Formation | Novi grid | Enverus | Live | Cause |
|---|---|---|---|---|---|---|
| 1722LS | 9,659 | LOWER SPRABERRY SHALE (10-27), DEAN (10-29) | DEAN | WOLFCAMP A | DEAN | suffix |
| 1719WA | 9,659 | WOLFCAMP A | WOLFCAMP A | DEAN | DEAN | Enverus at the boundary |
| 1725H | 9,664 | WOLFCAMP A | WOLFCAMP A | DEAN | DEAN | Enverus at the boundary |
| 1717WD | 9,755 | WOLFCAMP D | WOLFCAMP A | WOLFCAMP A | WCD | suffix |
| 1717MS | 9,186 | MIDDLE SPRABERRY | LSSH | LOWER SPRABERRY | MS | suffix |
| 1724H | 9,908 | WOLFCAMP B | WOLFCAMP B | WOLFCAMP A | WCA_1 | Enverus one bench high |

Mustang Draw (Reagan): AN / AS are Wolfcamp A wells (6,800–6,984 ft) and NH / SH sit at 6,996–7,186 ft. There SH is not
Spraberry Shale. Novi read both 44SH and 24SH as LOWER SPRABERRY SHALE at screen time and has since revised both to
WOLFCAMP B. Most of the 191 moves are this kind of Novi correction (34 are LSSH → WCB_1).

The residual is small. Only 176 of 11,572 Midland producers tagged from Novi `Formation` disagree with Novi's own grid
(1.5 %, mostly JO MILL vs LOWER SPRABERRY SAND). That is not enough for a new warehouse rule; it is noted for the 20b
Spraberry work.

**MM's calls (2026-10-29, each well and its neighbours inspected in anduin), recorded in `tag_screen/well_calls.csv`:**

| Well | Call | Seed before |
|---|---|---|
| Cross Bar Ranch H 1722LS (4200347061) | WCA_1 | WCA_1, class-accepted |
| Mustang Draw 44SH (4238340017) | WCB_1 | WCA_1, class-accepted |
| Cross Bar Ranch H 1719WA (4200347042) | WCA_1 | none (class DEAN → WCA_1 (A) rejected) |
| Cross Bar Ranch H 1717WD (4200345807) | WCA_1 | none (class WCD → WCA_1 (A) too small to card) |

1725H, 1717MS and 1724H look as clear on depth, but MM left them for the next screen.

**Code changes.**
- `override_seed`: an inspection call now REPLACES a class-accepted row, since MM looked at that well. A call that
  disagrees with a card still raises. A test covers it.
- `box_tag_seed --check-live`: `was` drift is now reported, not fatal. Missing wells and already-overridden wells still
  stop it.
- `apply_formation_tag_overrides --refresh`: the preflight now reports new rows whose `was` differs from the live tag, and
  lists any whose live tag is neither `was` nor the corrected code.

**Seed now:** 340 Midland rows (239 class-accepted, 94 carded, 7 calls) + 98 Delaware = 438. sql/44 Batch 3 and the table
COMMENT are updated to match.

**Dry run (10-29, before the apply):** preflight OK; add 340, change 0, remove 0. `was` differs from live on 15 rows: 14
already carry the corrected tag; the 15th is 1722LS, where MM's WCA_1 overrides Novi's new DEAN.

### 8.14 Applied (2026-10-29, MM ran `apply_formation_tag_overrides --refresh`)

MM ran it in his own shell after the 10-29 nightly finished green (17:52 UTC). Path B as in §8.12: one-transaction seed
reload, then REFRESH CONCURRENTLY down the 12-member CHAIN. Nothing went dark. By the catalog's analyze stamps the chain
ran from ~22:10 UTC (formation_blueox) to 23:07 UTC (erebor_locations), about 57 min. intel_pdp_support finished at
23:06, so it was nearly all of that time, as forecast.

**Checked afterwards, read-only, against the live warehouse:**

| Check | Result |
|---|---|
| `ref.formation_tag_overrides` rows vs seed | 438 = 438, every `corrected_code` equal to the seed |
| `curated.formation_blueox` carries the override, source `ratified_override` | 438 / 438 |
| `curated.erebor_locations` PDP rows for the seed wells (refreshed last) | 438 / 438 on the corrected tag, source `ratified_override` |
| erebor PDP rows agreeing with `wells_enriched.formation_blueox`, all basins | 60,679 / 60,679 |
| `reconciled_inventory` vs mapped stick universe (PUD + RES, geometry, non-null blueox) | 257,397 = 257,397, no duplicate stick_id |
| `erebor_locations` | 318,076 rows = 60,679 PDP + 257,397 sticks |

Reconciliation status now: Midland 85,171 remaining_pud / 1,333 realized_phantom / 678 conflict; Delaware 165,083 /
3,545 / 1,587.

The script exits non-zero (SystemExit) on any override that did not land or any PDP tag that moved outside the seed. MM
reported it finished. The per-move tallies (PUD/RES stick tags moved, recon status moves) printed only in his window and
are not recorded here.

Data dictionary regenerated: `ref.formation_tag_overrides` is now ~438 rows with the Batch 3 COMMENT. Everything else is
nightly row-count drift.

**Next at gate 20a:** re-run the 20a family QC and extents on the corrected tags, then the storage go.

### 8.15 r3: 20a re-run on the corrected tags (2026-10-30) → `r3/`, `r3/extents/`

This is the r2 recipe (§7) unchanged: the same card verdicts, D136, owner WCD and WCD loop. The only difference is the
live tags, which now carry the 438 overrides. It is read-only and nothing is stored. Production as-of is unchanged
(2026-09-01), so the moves below come from tags alone. r2 is left as it was.

| bench | r2 final (cohort) | r3 final (cohort) | pooling contrast vs bench above, oil / GOR / shape, r2 → r3 |
|---|---|---|---|
| WCA_1 | 7,540 (5,378) | 7,575 (5,410) | — |
| WCB_1 | 6,684 (3,927) | 6,658 (3,904) | 0.962 / 1.294 / 0.979 → 0.965 / 1.290 / 0.980 |
| WCB_2 | 2,062 (1,237) | 2,146 (1,287) | 0.958 / 0.928 / 0.999 → 0.954 / 0.938 / 1.000 |
| WCC | 649 (376) | 613 (354) | 0.878 / 1.177 / 1.002 → 0.868 / 1.179 / 1.005 |
| WCD | 945 (546) | 996 (559) | 1.123 / 1.108 / 1.030 → 1.118 / 1.055 / 1.024 |

- **Wells:** 17,861 in both runs; 184 changed final bench (110 cohort). The largest flow is WCB_1 → WCB_2 (88), the class
  WCB_1 → WCB_2 (A) you accepted in the tag screen. Next come WCC → WCB_1 (18) and WCB_2 → WCB_1 (17). Then WCC → WCD (12), from
  §8.10, and WCC → WCB_2 (11).
- **Family membership:** 127 wells joined (79 are override wells: OTHER → WCD 45, LSSH → WCA_1 19, LSSH → WCB_1 7,
  DEAN → WCA_1 8; the other 48 are vendor re-tags) and 19 left. Uncalibrated flags fell from 349 to 237.
- **Separability (D128, no pooling, unaffected):** GOR and shape still separate every pair. The WCB_1 / WCA_1 oil ratio's
  90 % CI now just touches 1.0 ([0.926, 1.004]; r2 [0.923, 0.998]). That reads the same as before: the two benches differ
  on GOR (+29 %) and shape, not 12-month oil.

**Extents** (same construction; undrilled = D117, Novi PUD + RES, ≥ 50 % of the stick inside):

| bench | r2 sq mi / undrilled | r3 sq mi / undrilled | footprint vs r2 (sq mi added / removed) |
|---|---|---|---|
| WCA_1 | 5,519 / 5,204 | 5,539 / 5,235 | +38 / −18 |
| WCB_1 | 5,220 / 5,599 | 5,188 / 5,595 | +40 / −72 |
| WCB_2 (D136 clip) | 2,003 / 851 | 2,018 / 856 | +22 / −8 |
| WCC (generated) | 652 / 699 | 644 / 698 | +9 / −17 |
| WCD **your loop** | 3,371 / 3,598 | 3,371 / 3,598 | loop geometry byte-identical |

For reference, WCD as generated without your loop: 1,627 / 1,747 in r2, 1,655 / 1,770 in r3. Inside the loop, 785 of
823 ≥ 2016 WCD laterals now fall inside (r2: 771 of 804). Two WCD sticks inside moved from `conflict` to `remaining_pud`
after the reconciliation refresh; the undrilled total is unchanged. Every extent keeps ≥ 97 % of its r2 footprint.

The loop was read against r1's pixel frames, as in r2. It was written via a scratch copy so r2's `extents/edited/` stays
as it was; the r3 copy is `r3/extents/edited/`.

**Conflict to decide (not resolved here): 9 ratified wells (5 cohort) that BOX QC moves off their ratified tag.**
`r3/ratified_moved_by_box_qc.csv`. All 9 are ratified WCB_2 and BOX puts them in WCB_1.
- 8 by D136: north of the WCB split line at WCB_1 depth (151–362 ft below WCA_1). 7 come from the tag-screen class
  WCB_1 → WCB_2 (A) (convention (a)); 1 is PARKS, ROY 316CH, your round-1 card WCC → WCB_2.
- 1 by the BOX class WCB_2 → WCB_1 (precision 1.00, sql/23 concurs): MELINDA 252WB.

The two decisions disagree. The tag screen judged each well against its neighbours, and in the north those neighbours
are the WCB_2 tags D136 calls WCB_1. D136 says there is one WCB landing in the north. BOX QC does not exempt
`ratified_override` wells from its rules, in the Delaware either.

Options:
- (a) Leave BOX's D136 result, so these 9 are WCB_1 for BOX while the warehouse says WCB_2. 5 cohort wells, no visible
  effect on the contrasts.
- (b) Owner-bench them to WCB_2 (BOX-only).
- (c) Correct the 8 north ones to WCB_1 in the next override batch. This is warehouse-first, and consistent with D136.

### 8.16 The 9-well conflict: MM's doublecheck calls (2026-10-30) → `r3/ratified_moved_by_box_qc.csv` column `doublecheck`

MM re-inspected each well and its neighbours.

| call | wells | r3 BOX before | warehouse now | done |
|---|---|---|---|---|
| **WCB_2** | FREDERICK LINDSEY E 5H, T Y RANCH 65S, SXSW E UNIT B 1WB, MASSEY A UNIT 4309H, PEGGY 9 301 | WCB_1 (D136) | WCB_2 | owner bench WCB_2; seed row kept, note → the call |
| **WCC** | PARKS, ROY 316CH | WCB_1 (D136) | WCB_2 (round-1 card) | owner bench WCC; seed row REMOVED (vendor WOLFCAMP C → WCC) |
| **WCB_1** | STEPHENS 6-31 E 255, STEPHENS 6-31 D 244, MELINDA 252WB | WCB_1 | WCB_2 (class-accepted) | owner bench WCB_1; seed rows REMOVED (vendor WOLFCAMP B UPPER → WCB_1) |

**Flag, not resolved:** the 5 WCB_2 calls are per-well exceptions to D136. All 5 lie north of the line at 151–362 ft below
the local WCA_1 band, under D136's 392-ft WCB_2 threshold. The vendor raw tag on all 5 is WOLFCAMP B UPPER. Owner benches
outrank every rule by design, so D136 itself is unchanged. If more northern wells turn out to be real WCB_2, the line or
the threshold is the thing to revisit. FREDERICK LINDSEY E 5H is the shallowest, at 151 ft below WCA_1, above the
southern WCB_1 median of 262 ft.

**Code (repo only):**
- `tag_screen.override_seed`: a call dated after the well's card supersedes the card. A card with no round date never
  is, so a disagreeing call there still raises. A call back to the screen-time tag removes the row, since an override
  equal to its `was` is forbidden by the seed test. Covered by a test.
- `apply_formation_tag_overrides --refresh`: removed rows count as expected moves. Without this, the verify step would
  have failed on them as stray. The verify now checks each removed well is back on the crosswalk, and the dry run lists
  the removals.

**Seed:** 336 Midland rows (231 class-accepted, 93 carded, 12 calls) + 98 Delaware = 434. sql/44 Batch 3 and the COMMENT
are updated. The dry run (read-only, 2026-10-30) gives add 0, change 5 (notes), remove 4. Under the live crosswalk, raw
WOLFCAMP B UPPER → WCB_1 on 9,201 Midland wells and WOLFCAMP C → WCC on 4,798, so the removals land on MM's calls.
**Not applied — DECIDED (MM 2026-10-30): it rides the next override batch** (`--refresh`, ~1 h, nothing dark), since
BOX already honours the calls through the owner benches. Until then live holds 438 rows and the seed 434. The 4 wells keep
WCB_2 in the warehouse (erebor, narvi, deal-intake read that) but carry the right bench in BOX.

**r3 regenerated with the 9 owner benches** (same cache, live tags unchanged): all 9 land on the call, and only those 6
of the 9 not already on their call moved. No seed well now disagrees with BOX. Bench finals (cohort):

| bench | final (cohort) |
|---|---|
| WCA_1 | 7,575 (5,410) |
| WCB_1 | 6,652 (3,900) |
| WCB_2 | 2,151 (1,290) |
| WCC | 614 (355) |
| WCD | 996 (559) |

Contrasts move ≤ 0.006. The extents are geometrically identical to pre-call r3 (0.00 sq mi added or removed per bench), so
the §8.15 extent table stands. The WCD loop is unaffected: no WCD well moved.

### 8.17 Stored (2026-10-30, MM: "go ahead on the r3 store")

`python -m scripts.box_family_extent_store --wells docs/box/step20a-2026-10-26/r3 --pool WCA_1 WCB_1 WCB_2 WCC WCD --basin midland`
(dry run first). This writes five `box.bench_scope` rows and six `box.extent` rows: five generated records, plus WCD's
generated parent and its edited loop as the record. Each row is `in_scope` true, `member_benches = {bench}` (D128), and
decided 2026-10-30. The reason text says the tier is provisional until step 21 (D131). Rows are named `WCA_1`, not
`WCA`, per the §4 item 5 recommendation: the Midland has no WCA_2 / WCXY.

**Identity before the write:** every generated extent was rebuilt with the basin's D23 metric (and the D136 clip on
WCB_2) and matched the reviewed r3 extent within 0.001 sq mi of area and 0.006 sq mi of symmetric difference. The WCD
record is the reviewed loop geometry exactly.

| bench | extent_id (record) | source | sq mi | edges | undrilled inside, live (PUD / RES) |
|---|---|---|---|---|---|
| WCA_1 | 36 | generated | 5,539.31 | 281 | 5,235 (5,233 / 2) |
| WCB_1 | 37 | generated | 5,187.55 | 282 | 5,595 (5,593 / 2) |
| WCB_2 | 38 | generated, D136 clip | 2,017.57 | 74 | 856 (856 / 0) |
| WCC | 39 | generated | 643.82 | 26 | 698 (698 / 0) |
| WCD | 41 (parent 40, generated 1,655.45) | owner loop | 3,371.00 | — | 3,598 (3,522 / 76) |

The undrilled counts are re-measured live against the stored records (D117 universe, ≥ 50 % of the stick inside). They
equal r3's exactly. One record per bench on all five.

**Fix made for the store:** `wcb_split.clip_d136` clipped the WCB_2 polygon but kept every boundary edge. 16 of 90 edges
lay wholly north of the line, and 4 crossed it. It now drops the 16 and trims the 4 to the remaining boundary
(`box.extent_edge.geom` is a LineString); there is a test. The r3 extent package was regenerated so its WCB_2 edge files
match what is stored. No geometry moved.

`box_family_extent_store` gained the Midland path: basin-keyed scope rows, the basin's edge metric, the D136 clip, and
the rule that a bench with no loop takes its generated v1 as the record.

**What changes downstream:**
- erebor: Midland WCA_1 / WCB_1 / WCB_2 / WCC / WCD sticks without a BOX forecast change class from `bench_not_in_box`
  to `not_screened` (on a BOX bench, not yet run). Sticks forecast in run 19 keep their class.
- BOX: the next Midland run (step 21 onward) builds on these records. No forecast was run here, and no record run
  changed.

**Ask 6 is now concrete:** `box/production._UNIVERSE_SQL` still filters `il.category = 'PUD'`. Inside the stored
records that leaves out 80 RES sticks, 76 of them in WCD, which D117 counts as undrilled.

**Still open at gate 20a:** asks 3, 4 and 6 in §4, the unlike-threshold confirm (§4 item 1), and the 4246139575 loop-tip
flag (§7). The 4 seed removals ride the next override batch (§8.16).

### 8.18 Asks 3 / 4 / 6 answered (MM 2026-10-30) → `ask3/cards.html`

- **Ask 3 → D139: card WCB_1 → WCB_2.** The cards are drawn on the r3 scored frame, the state that was stored.
  - The class now has 87 flags (168 in r1); the tag screen's WCB_1 → WCB_2 (A) overrides absorbed the rest.
  - 4 wells are left out because MM already judged them: HOGAN 1-24I 4315H and HUTCHISON-TEELE 20 302HB (tag-screen
    cards, rejected), HUTCHISON-TEELE 30 303HB (tag-screen card, called WCB_1), and 1 ratified override.
  - 10 cards come from the 83 that remain, a stratified sample by margin. None of the 83 was flagged by the tag screen,
    which uses a different method.
  - 3 cards lie north of the D136 line (DYER-KILGORE L 25-34 4412H, NAIL-TILLMAN W1Q 417H, 1 MILE 29 G 4307H), and 28 of
    the 87 flags do. D136 moves WCB_2 tags at WCB_1 depth north of the line, so a WCB_2 verdict there is a well-level
    call, like the 5 in §8.16.
  - Verdicts go in `ask3/cards_sample.csv` (column `verdict`: agree / reject / a bench code / hold).
  - The Midland class ledger then decides the class at the ≥ 0.70 gate. If accepted, r3 is regenerated and any extent
    that moves is re-stored on a go. If rejected, nothing moves.
- **Ask 4 → D140: no.** The prefix list stays Bone Spring + Avalon, so DEAN / LSSH → WCA stay "uncalibrated, tag kept".
- **Ask 6 → D117 as written:** every reconciled Novi stick inside the BOX extent, BASE_CASE (PUD) or UPSIDE (RES). The code
  still filters PUD (`box/production.py:95`). The work is D117 step 3 (`docs/box/universe-2026-10-21/AUDIT.md`):
  - drop the filter;
  - run a container rehearsal against the record run (run 19): its rows must reproduce exactly, additions only;
  - report coverage per bench for the added RES locations.

  It must land before the first Midland record (step 23), and the next Delaware record picks it up too. Inside the five
  stored Midland records it adds 80 RES sticks (76 in WCD). Two other PUD-only spots need a decision in that step:
  `scripts/box_update_deck.py` refuses non-PUD locations (it compares against Novi BASE_CASE forecasts), and
  `box/extent_report._PUD_SQL` (the Delaware D1 count on extent pages) still counts PUD only.

**Still open at gate 20a:** the ask-3 card verdicts, the unlike-threshold confirm (§4 item 1), and the 4246139575
loop-tip flag (§7). D117 step 3 runs separately.

### 8.19 Ask-3 verdicts back (MM 2026-10-30): WCB_1 → WCB_2 = 6 / 10, class rejected

| card | verdict | side of the D136 line |
|---|---|---|
| LHS RANCH 1708BH, MARIE 1802BH, ALDWELL K R 40 9H, BULLHEAD 723CN, DRIVER 4C-E 3-46F 106H, WILDCAT EAST I 17-43 4409H | WCB_2 (agree) | south |
| TOMAHAWK 4810 C 6HM | WCB_1 (reject) | south |
| DYER-KILGORE L 25-34 4412H, NAIL-TILLMAN W1Q 417H, 1 MILE 29 G 4307H | WCB_1 (reject) | **north** |

**Class:** 0.60, under the 0.70 gate, so it is **rejected**. The uncarded wells in the class keep their tag. That is the
same membership as before, when the class was uncalibrated. Each card still decides its own well, so the 6 agree wells
move to WCB_2 in BOX (3 of them cohort).

**DECIDED (MM 2026-10-30): keep the class rejected as carded; no south-only rule.** The split is geographic. North of the D136 line the cards went 0 / 3, which is what D136 predicts:
one WCB landing there. South they went 6 / 7 (0.86). Accepting the class south of the line only would be a new rule, a
class split by D136, so it is MM's call. As carded, the gate applies to the whole class. There are 73 uncarded flags; 49
of them lie south of the line (24 cohort), and 24 north.

**Code:**
- `qc_rule.load_verdicts` now reads a bench-code verdict: the suggested bench counts as AGREE, the well's own tag as
  REJECT, and a third bench is ignored. The earlier card files read identically (125 and 50 verdicts).
- `qc_rule.BASIN_CLASSES` midland gains `WCB_1->WCB_2: 0.60`.
- Both have a test.

**r3 regenerated:** only the 6 card wells moved. WCB_1 is now 6,646 (cohort 3,897) and WCB_2 2,157 (1,293). Contrasts
move ≤ 0.003.

**Stored extents vs the rebuild** (read-only against the live records):
- WCB_2 gains 0.20 sq mi of 2,018 (0.01 %), and its undrilled count is unchanged (856).
- The other four differ by ≤ 0.003 sq mi, which is coordinate rounding.

The stored records are kept: no location changes coverage. Re-storing WCB_2 would supersede record 38 and needs a go.

**Still open at gate 20a:** the unlike-threshold confirm (§4 item 1), and the
4246139575 loop-tip flag (§7).


```
python -m pytest -q tests/test_box_step20a.py tests/test_box_family_qc.py tests/test_box_basin.py
python -m scripts.box_family_qc --family MID_WC --out <dir> --analogue --cards --alloc     # ~8 min, read-only
python -m scripts.box_family_extents --wells <dir> --pool WCA_1 WCB_1 WCB_2 WCC WCD --basin midland --visual-bodies 50   # ~9 min
```

- **Full suite:** 761 passed, 46 skipped (2026-10-27, after §8.2).
- **Ruff:** clean on every touched file. mypy is not installed in this venv.
- **WCB split (§6):** `python -m scripts.box_wcb_split --wells docs/box/step20a-2026-10-26` (~30 s, read-only).
- **Delaware unchanged.** WCC rebuilt through the modified extent code = its step-15 build within 6e-6 sq mi. Delaware
  two-bench family membership code paths are identity-mapped (test). The AVA pooling contrast changes, by design (§1).

**r2 (§7), read-only:**
```
python -m scripts.box_family_qc --family MID_WC --out docs/box/step20a-2026-10-26/r2 --verdicts docs/box/step1-2026-10-06/cards_sample.csv \
    --verdicts docs/box/step20a-2026-10-26/cards_sample.csv --owner-benches docs/box/step20a-2026-10-26/owner_benches.csv     # ~90 s with --cache
python -m scripts.box_family_extents --wells docs/box/step20a-2026-10-26/r2 --pool WCA_1 WCB_1 WCB_2 WCC WCD --basin midland --step 20a --visual-bodies 50
python -m scripts.box_family_extent_edits --pptx docs/box/step20a-2026-10-26/extents/midland_wolfcamp_extents_2026-10-26.pptx \
    --slide 5=WCD --wells docs/box/step20a-2026-10-26/r2 --ext docs/box/step20a-2026-10-26/extents --basin midland
```
The loop ingest reads the r1 extents folder on purpose: the deck's pixel frames are r1's.

**r3 (§8.15), read-only:** the r2 commands with `--out .../r3` / `--wells .../r3` (QC 108 s uncached, extents ~11 min).
For the loop, point `--ext` at a copy of `extents/` so r2's `extents/edited/` is not overwritten, then copy `edited/`
into `r3/extents/`.

**Tag screen (§8), read-only (~70 s with --cache):**
```
python -m scripts.box_tag_screen --basin midland --family MID_WC --out docs/box/step20a-2026-10-26/tag_screen \
    --prior-verdicts docs/box/step20a-2026-10-26/cards_sample.csv            # round 1
python -m scripts.box_tag_screen ... --round 2                                 # after round-1 verdicts: tops up the mixed classes
python -m scripts.box_tag_screen --basin midland --family MID_WC --out docs/box/step20a-2026-10-26/tag_screen --round 2     --prior-verdicts docs/box/step20a-2026-10-26/cards_sample.csv docs/box/step20a-2026-10-26/tag_screen_whatif_wc/cards_sample.csv     --depth-check docs/box/step20a-2026-10-26/tag_screen_whatif_wc/depth_check.csv     # §8.8: live tags, every verdict carried
    # §8.9-8.10: add  --label "round 3 (full review)" --review-all "WCC->WCD (B)"   (cards every well of that class)
python -m scripts.box_tag_seed --screen docs/box/step20a-2026-10-26/tag_screen --check-live      # §8.11: build + read-only live check (add --write to rewrite the block)
python -m scripts.apply_formation_tag_overrides --refresh --dry-run      # §8.12: preflight + seed diff, read-only (drop --dry-run = the apply, on go only)
python -m scripts.box_tag_screen --basin midland --family MID_WC --out docs/box/step20a-2026-10-26/tag_screen_whatif_wc --whatif \
    --prior-verdicts docs/box/step20a-2026-10-26/cards_sample.csv docs/box/step20a-2026-10-26/tag_screen/cards_sample.csv
                                                                               # drafted sql/16 Midland WOLFCAMP C rule, in memory
```
Depth-only check of the drafted rule (§8.7), read-only, seconds with both caches:
```
python -m scripts.box_wc_rule_depth_check --out docs/box/step20a-2026-10-26/tag_screen_whatif_wc/depth_check.csv \
    --cache <scored.pkl> --labels-cache <labels.pkl>
```
sql/16 dry run (read-only): evaluate the CREATE body inside `SET TRANSACTION READ ONLY` and diff it against
`curated.formation_blueox` (§8.2 numbers).
