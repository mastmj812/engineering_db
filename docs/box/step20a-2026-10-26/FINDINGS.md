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

The WCC → WCD (B) depth flag above is resolved by a full review (§8.10). Until those cards are back, the 296 includes
WCC → WCD's 8 uncarded wells.

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

**Seed effect.** WCC → WCD now contributes only the wells whose own card agrees, plus any bench you write on a card.
- Today that is the 8 carded agrees: round 1 Bandolero, Mabee DDA L1, Chaparral and Winchester, plus round 2 MB,
  Knight, John B and Conroe.
- The 8 uncarded wells wait on these cards.
- The prospective seed is 334 rows until the 8 are back, and up to 342 after.

## 5. How to check

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

**Tag screen (§8), read-only (~70 s with --cache):**
```
python -m scripts.box_tag_screen --basin midland --family MID_WC --out docs/box/step20a-2026-10-26/tag_screen \
    --prior-verdicts docs/box/step20a-2026-10-26/cards_sample.csv            # round 1
python -m scripts.box_tag_screen ... --round 2                                 # after round-1 verdicts: tops up the mixed classes
python -m scripts.box_tag_screen --basin midland --family MID_WC --out docs/box/step20a-2026-10-26/tag_screen --round 2     --prior-verdicts docs/box/step20a-2026-10-26/cards_sample.csv docs/box/step20a-2026-10-26/tag_screen_whatif_wc/cards_sample.csv     --depth-check docs/box/step20a-2026-10-26/tag_screen_whatif_wc/depth_check.csv     # §8.8: live tags, every verdict carried
    # §8.9-8.10: add  --label "round 3 (full review)" --review-all "WCC->WCD (B)"   (cards every well of that class)
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
