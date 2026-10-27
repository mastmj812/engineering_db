# BOX step 20a: Midland Wolfcamp bench QC + extents. AT GATE 20a (nothing stored)

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
3. **Conflict to resolve (D128 vs D134 B).** D128 sent the WCB_1 ↔ WCB_2 and WCB_2 ↔ WCC swap classes to 20a's cards. D134 B
   cards only "unlike" classes. I followed D134 B (the later decision), so **WCB_1 → WCB_2 (168 flags, alike) is not
   carded**. Say if you want it carded per D128.
4. **Spraberry → Wolfcamp flags (DEAN / LSSH → WCA, 65).** The rule's "never Bone Spring → Wolfcamp" names Bone Spring and
   Avalon only. These classes therefore fall to "uncalibrated, tag kept": the same membership, but the well stays a depth
   witness. Should the prefix list gain the Spraberry benches at 20b?
5. **Storage, on your go after 1–2** (and after D136 is applied in the same regeneration pass): five `box.bench_scope` rows (basin `midland`, `in_scope` true, `validation`
   provisional until step 21, `member_benches` = {bench}) and five `box.extent` records.

   Naming: I recommend the row be `WCA_1`, not the Delaware's pooled `WCA` (D128: one bench each; the Midland has no WCA_2 /
   WCXY tags). Note that `box/production.py` resolves sticks through `member_benches`, so either name works there.
6. **Not this step, but flagged:** `box/production._UNIVERSE_SQL` still filters `il.category = 'PUD'`, while D117 says any
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
ones you did. Rejected classes write nothing; a well you rejected inside an accepted class is left out. The sql/44 header
and its table COMMENT are amended in the same commit as the first class-accepted rows (the COMMENT reaches the live table
only when that apply runs).

## 5. How to check

```
python -m pytest -q tests/test_box_step20a.py tests/test_box_family_qc.py tests/test_box_basin.py
python -m scripts.box_family_qc --family MID_WC --out <dir> --analogue --cards --alloc     # ~8 min, read-only
python -m scripts.box_family_extents --wells <dir> --pool WCA_1 WCB_1 WCB_2 WCC WCD --basin midland --visual-bodies 50   # ~9 min
```

- **Full suite:** 749 passed, 46 skipped.
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

**Tag screen (§8), read-only (~70 s with --cache):**
```
python -m scripts.box_tag_screen --basin midland --family MID_WC --out docs/box/step20a-2026-10-26/tag_screen \n    --prior-verdicts docs/box/step20a-2026-10-26/cards_sample.csv            # round 1
python -m scripts.box_tag_screen ... --round 2                                 # after round-1 verdicts: tops up the mixed classes
```
