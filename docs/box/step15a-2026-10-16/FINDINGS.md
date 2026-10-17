# BOX step 15a, first half: Bone Spring 3 (BS3_S + BS3_C) bench QC. AT THE QC GATE

**Sequencing.** Michael pulled step 15a forward on 2026-10-16, ahead of steps 10–14, to run in parallel with step 9
(session box-step9a). This session works in its own worktree (branch `claude/box-step15a-bs3`). It does not touch the
plan's Status line or §2, `box/acceptance.py` or `box/analog.py`, and it reserves no `sql/NN`. Nothing has been written
to the warehouse. The next sequential session folds the gate outcome into the plan.

**Review surface:** `index.html` (family page: well sets, flag ledger, sensitivity, pooling evidence, gate asks), plus
`qc_BS3_S.html` / `qc_BS3_C.html` (the step-1 per-bench pages: counts, tag QC maps, the state-line check, the NM
planned-survey input). Serve the folder with `python -m http.server 8766 --directory docs/box` →
`http://localhost:8766/step15a-2026-10-16/`. The files open directly too.

**Build:** `python -m scripts.box_family_qc --family BS3 --out docs/box/step15a-2026-10-16` (about 2.5 min, read only).
Code: `box/family_qc.py` (new), `scripts/box_family_qc.py` (new), `tests/test_box_family_qc.py` (4 DB-free tests).
The Phase 1 modules are reused **unchanged**: `box/bench_qc.py` (pull, consensus detector, per-bench page),
`box/qc_rule.py` (class rule of record), the gate-1 card verdicts (`step1-2026-10-06/cards_sample.csv`, 84 agree / 41
reject), and the frozen D84 pools (`pool-2026-10-15`: wells_final_WCA / BS2_S + universe.csv). Because no Phase 1
module changed, the WCA and BS2_S outputs cannot move. Their tests still pass (40 tests across bench_qc / qc_rule /
flag_cards / pool_refresh / family_qc). Warehouse as of 2026-08-01 (max last_reported_month); 31,645 Delaware producing
horizontals.

## 1. Well sets (proposed)

Grain: producing horizontals, one row per api10, on the TVD-corrected `formation_blueox`.

| | BS3_S | BS3_C |
|---|---:|---:|
| tagged in the live warehouse | 3,107 | 1,892 |
| held by a frozen Phase 1 pool (D84: stays there) | 71 (WCA 46, BS2_S 25) | 75 (BS2_S 73, WCA 2) |
| … of which re-tagged since gate 1 | 63 | 28 |
| joined from other tags (your gate-1 AGREE cards: WCA→BS3_S ×2, BS2_S→BS3_S ×3, BS2_S→BS3_C ×1) | 5 | 1 |
| old churn kept (judged at gate 1, not moved then; today's rule would move it) | 2 | 6 |
| new wells ruled out / excluded | 0 / 0 | 0 / 0 |
| **FINAL set** | **3,041** | **1,818** |
| first production ≥ 2016 | 2,365 | 1,651 |
| D9 cohort (fp ≥ 2016, lateral 6–13 kft, 12 full months) | 1,658 | 1,003 |
| TX / NM | 1,330 / 1,711 | 842 / 976 |
| tvd_suspect (A-prime / Bone Spring→Wolfcamp: tag kept, TVD not a depth witness) | 143 | 4 |

The plan's evidence table (2,426 / 1,702 modern producers) is the raw tag count. The QC'd modern counts are 2,365 /
1,651; the difference is the wells already held by the WCA / BS2_S pools.

Per-bench QC numbers (from the bench pages): planned-survey share 11.2 % / 10.4 % (NM 19.4 % / 18.8 %); permit-round
TVD 2.7 % / 1.6 %; sql/23 nearest band ≠ assigned 21.6 % / 14.4 %; consensus flags 234 (7.5 %) / 69 (3.6 %);
**state line: no border step on either bench** (border bin step 8.6 % / 9.1 % vs typical bin-to-bin 13.2 % / 16.7 %).
Cohort median 12-mo oil 20,312 / 17,179 bbl per 1,000 ft.

Files: `wells_final_BS3_S.csv`, `wells_final_BS3_C.csv` (qc_rule FINAL_COLS + `family_role`), and `family_roles.csv`,
which gives every touched well's role, frozen pool and gate-1 tag.

## 2. Flags under the rule of record

- Out of the family: BS3_S→WCA 215 (rejected class 0.40; 138 are TVD-suspect under A-prime or Bone Spring→Wolfcamp;
  75 sit in the **WCXY** band and are kept by the D20 check, see note a); BS3_C→BS2_S 66 (accepted 0.90; 48
  reassigned, all already in the frozen BS2_S pool); BS3_S→BS2_S 6 (accepted 1.00, in BS2_S); a few Bone Spring→Wolfcamp
  flags (TVD-suspect).
- Into the family: WCA→BS3_S 130 (rejected 0.40, tags kept except the 2 cards you agreed); BS2_S→BS3_C 34 (rejected
  0.33); BS2_S→BS3_S 6 (hold 0.60; your 3 AGREE cards apply).
- **No accepted class points into a BS3 bench.** BS3_S↔BS3_C swaps are never flags: the detector reports a
  sand↔carbonate swap in one interval as `ambiguous_lith` (35 BS3_S, 20 BS3_C).
- **Uncalibrated:** 17 flags in 9 small classes (AVA_2→BS3_C, BS1_S↔BS3_x, BS3_C→AVA_1, BS3_S→BS2_C, OTHER/WCB_1/WCC→BS3_S).
  The rule's default keeps the tag.
- **Sensitivity** (gate-1 pattern): applying every consensus flag touching the family moves the cohort median 12-mo
  oil/kft by +0.0 % (BS3_S) and −1.0 % (BS3_C). The flags do not move the evidence.

## 3. Pooling evidence (D19 / D33 pattern)

| measure | BS3_C vs BS3_S | compare WCA_2 vs WCA_1 (D19 / D33, pooled) |
|---|---|---|
| local band separation where both are coherent | BS3_C **496 ft shallower** (IQR 338–780), 240 neighbourhoods; TX 353 / NM 636 ft | ~128 ft |
| bands merged (< 100 ft apart) | **3 %** (TX 7 %, NM 0 %) | 36 % |
| stack order inverted | 1 % | — |
| in-family tag swaps | 55 ambiguous_lith, never flags | 675 of 1,121 WCA flags |
| 12-mo oil per 1,000 ft, same 5-mi block + fp-year FE | **0.897× [90 % CI 0.83–0.95]**, 133 blocks | ~0.96× (−3.7 / −4.1 %) |
| 12-mo GOR, same block | 1.03× [0.98–1.09] | — |
| cum-24 / cum-12 oil (shape), same block | 0.99× [0.97–1.02], 109 blocks | — |
| cohort with the other bench within 1.5 mi | BS3_S 46 % / BS3_C 52 % | — |

Raw cohort medians: BS3_S 20,134 bbl/kft, GOR 2,088 scf/bbl, TVD 10,910 ft, 58 % NM; BS3_C 17,023, 2,836, 10,054 ft,
44 % NM. The raw GOR gap disappears within block, so it is a location effect.

Reading: none of the reasons WCA_1 and WCA_2 were pooled applies here. The two BS3 benches are depth-resolved
everywhere they co-occur, swaps between them are rare, and they are different rock (sand vs carbonate) with a ~10 %
level difference that sits outside the block-to-block noise. Shape and GOR match, which matters later for the haircut
question (step 9a pattern) but not for membership.

## 4. Gate asks (QC gate)

1. **Confirm the well sets** BS3_S 3,041 / BS3_C 1,818 (§1). *Recommend: confirm.*
2. **Uncalibrated classes**: no new calibration cards; tags kept (sensitivity ≤ 1 %). *Recommend: no cards.*
3. **Pooling**: *recommend do NOT pool.* BS3_S and BS3_C stay two benches through extents (two D27 envelopes),
   analogs (the deal-intake same-bench rule, as with WCA vs BS2_S) and acceptance. Pooling would let one bench's
   development stand in for the other's in an extent, which is not a development statement for that bench, and it
   would mix a ~10 % level difference into analog cohorts.
4. **Re-tag drift since gate 1 (raised, not resolved).** 91 wells now tagged BS3 are held by a frozen pool under their
   gate-1 tag: 43 in WCA (gate-1 tags 22 WCA_1 / 10 WCA_2 / 11 WCXY; 27 in the cohort) and 48 in BS2_S. Most are Novi
   re-tags. D84 says a frozen well is never re-decided, so they stay out of the BS3 sets and no well counts twice. It
   also means ~43 wells that are now BS3 sit in the run-7 WCA analog pool. *Recommend: keep D84 here. Take "should a
   warehouse re-tag move a frozen well?" to the next WCA / BS2_S pool refresh (step 13), not this step.*

Notes (no decision needed):
- a. **Rule-order quirk.** `qc_rule.decide` checks "into WCXY, never applied (D20)" before "Bone Spring → Wolfcamp",
  so the 75 BS3_S wells flagged into the WCXY band keep `box_depth_witness = True`, while BS3_S→WCA_1/2 flags drop it.
  Membership is unaffected, and nothing downstream reads `box_depth_witness` today. Left as is (rule of record).
- b. The per-bench pages' §4 (NM planned-survey options A/B) is input already decided: option A, every bench (§9).
- c. After this gate: the extent half (step-3 tooling, D27 envelope per bench, rendered extent + geology package),
  then stop at the extent gate. Nothing is stored in `box.extent` without Michael's explicit go-apply.

## 5. QC gate — CLOSED 2026-10-16 (Michael: "accept all four recommendations")

1. Well sets confirmed: BS3_S 3,041 / BS3_C 1,818 (`wells_final_BS3_S.csv`, `wells_final_BS3_C.csv`).
2. No calibration cards for the uncalibrated classes; tags kept.
3. **BS3_S and BS3_C are NOT pooled** — two benches through extents, analogs and acceptance.
4. Re-tag drift: D84 stands here (frozen wells stay in their pool); the re-tag question goes to the next WCA / BS2_S
   pool refresh / step 13.

These are proposed as decisions of record for the next sequential session to number into plan §2 (this session does not
edit §2). Next: the extent half (`docs/box/step15a-2026-10-16/extents/`).

# Extent half — AT THE EXTENT GATE (nothing stored)

## 6. Generated D27 extents (method of record, unchanged)

`python -m scripts.box_family_extents --wells docs/box/step15a-2026-10-16 --pool BS3_S BS3_C --regress docs/box/step1-2026-10-06`
(~8 min, read only) → `extents/` (index.html, extent_<bench>.html, geology/ shapefile package NAD83 UTM 14N US-ft with
3BSPGS / 3BSPGC structure + isopach context, CSVs, summary.json). Code `box/family_extent.py`; step-3 modules reused
unchanged (one addition: `extent_package.GRIDS` gained BS3_C = 3BSPGC → 3BSPGS and BS3_S = 3BSPGS → WOLFCAMP_XY).
Parameters = the step-3 calibration of record (k 0.75, cap 7,920 ft, floor 880 ft, pool reference, D23 r 2,640 / c
3,960 ft, D27 envelope), read from `step3-2026-10-07/summary.json`, not re-picked.

**Regression guard:** the same code + parameters rebuilt from the frozen gate-1 sets reproduce the record extents:
WCA 6,168.65 sq mi exactly; BS2_S 3,358.13 vs 3,358.45 (−0.01 %, live lateral geometry drift since 2026-10-07).

**Finding — D27 assumes one development body per bench; BS3 has two.** The step-2 outline's largest component is the
body; anything > 8 mi from it is an "isolated test". BS3_S: NM body 1,489 laterals + a Texas trough-axis body
(Reeves / Ward / Loving) of 592 ~30 mi away → 758 laterals classed as tests, 770 of 2,365 modern laterals outside
(generated 2,991 sq mi). BS3_C: 1,135 + 283 SE → 413 of 1,651 outside (2,440 sq mi).

## 7. Michael's visual check + hand edit (2026-10-16)

Michael chose a visual check over a multi-body rule: the one-body extents rendered over each bench's own HCA structure
top with the PDP laterals (`extents/visual_<bench>.png`), then edits drawn in red in PowerPoint
(`Blue Ox Resources/Engineering - General/bs3_extents.pptx`, slide 1 = BS3_C, slide 2 = BS3_S).

Ingest (`python -m scripts.box_family_extent_edits --pptx … --slide 1=BS3_C --slide 2=BS3_S`): each freeform
(beziers sampled) is mapped slide EMU → PNG pixel → axes data (NAD83 UTM 14N US-ft). The maps were regenerated
bit-identical (md5) to the ones edited, so the transform is exact. The open line is closed by a chord through the
generated extent, unioned with it, voids filled (D27). Outputs in `extents/edited/`: `BOX_<bench>_extent_v1_edited.shp`
(the geology round-trip format, D7/D28), the step-3 diff page `diff_<bench>_v1.html`, `visual_<bench>_edited.png`.

| | BS3_S | BS3_C |
|---|---:|---:|
| generated v1, sq mi | 2,991 | 2,440 |
| **edited v1, sq mi** (added / removed) | **4,998** (+2,007 / 0) | **3,840** (+1,401 / 0) |
| parts | 1 | 1 |
| ≥ 2016 laterals inside (≥ 50 % of length): generated → edited | 1,595 → 2,231 of 2,365 | 1,238 → 1,521 of 1,651 |
| still outside, by county | Reeves 86 (the isolated W-Reeves cluster), Pecos 28, Eddy 14, other 6 | Eddy 47, Pecos 33, Lea 26, Reeves 16, other 8 |
| D1 PUD universe inside (≥ 50 % of stick): generated → edited | 5,289 → **9,224** | 4,831 → **7,794** |

(Plan evidence table: 13,073 / 12,621 drillable Novi PUDs basin-wide → 71 % / 62 % inside the edited extents.)
Edits: BS3_S adds the south trough-axis trend (Reeves / Ward / Loving into TX) and the western Culberson / NW-Reeves
shelf cluster; BS3_C adds the SE trough-axis trend (Reeves / Ward). Both leave the far-SE Pecos/Ward scatter out.

## 8. Extent-gate asks

1. **Accept the edited extents as v1 of record** (BS3_S 4,998 / BS3_C 3,840 sq mi). This is a hand edit by the owner,
   stored the way D28 stores a geology edit (`source = geology_edited`, parent = generated v1). It is also a method
   note for the plan: D27's one-body assumption does not hold for multi-trend benches; for this family the owner's
   visual edit replaced a multi-body rule (record as a decision for the next sequential session).
2. **Go-apply to store** (warehouse WRITE, nothing done yet). Three steps, in one session on your go:
   (a) `box.bench_scope` gains `('delaware','BS3_S',true,'{BS3_S}',…)` and `('delaware','BS3_C',true,'{BS3_C}',…)`
   (box.extent has an FK to bench_scope); (b) store generated v1 for each (not record); (c) store the edited v1 as the
   version of record. No DDL, no sql/NN.

## 9. Extent gate — CLOSED 2026-10-16: STORED LIVE (Michael: "go apply: add BS3_S + BS3_C to box.bench_scope, store generated v1, then store the edited v1 as the version of record")

`python -m scripts.box_family_extent_store --wells docs/box/step15a-2026-10-16 --pool BS3_S BS3_C` at 110c7d1 (dry run
first). Identity before writing: the rebuilt generated extent = the reviewed v1 (|Δ area| ≤ 0.0005 sq mi, symmetric
difference ≤ 0.0035 sq mi — GeoJSON 1e-6° rounding); the edited geometry = the reviewed `edited/*.geojson` exactly.
No DDL, no sql/NN.

| | box.bench_scope | generated v1 (not record) | edited v1 = **version of record** |
|---|---|---|---|
| BS3_S | `('delaware','BS3_S',true,'{BS3_S}')` | extent_id 15, 2,991.28 sq mi, 129 edges | **extent_id 16**, 4,998.33 sq mi, parent 15 |
| BS3_C | `('delaware','BS3_C',true,'{BS3_C}')` | extent_id 17, 2,439.68 sq mi, 153 edges | **extent_id 18**, 3,840.21 sq mi, parent 17 |

Read-only check after the writes: exactly one record per bench (WCA 6, BS2_S 7 unchanged; BS3_S 16, BS3_C 18). The
geodesic areas read 0.04 % above the planar UTM 13N areas, the same projection scale as the Phase 1 records.

**For the next sequential session (plan §2 / Status, which this session does not edit):** proposed decisions —
BS3 bench QC sets + no cards (§5.1–2); BS3_S and BS3_C not pooled (§5.3); re-tag drift stays under D84 until the next
refresh (§5.4); BS3 extents of record = the owner's hand edit of generated D27 v1 (§7–9), recording that D27's
one-body assumption fails on multi-trend benches and a visual owner edit replaced a multi-body rule for this family.
Next for 15a: 9a-style tuning view (D53 harness) on BS3_S / BS3_C — after step 9a generalises `box/acceptance.py`.
