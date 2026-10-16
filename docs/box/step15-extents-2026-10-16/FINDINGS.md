# BOX step 15: generated extents for the remaining Delaware benches. AT THE EDIT PASS (nothing stored)

**What Michael asked (2026-10-16, after 15a merged):** compute the extents for the remaining benches. He supplies
first-pass edits on the computed extents, as for BS3. He expects BS2_C to break the one-body rule (a pronounced SE
development area that does not connect to the main body).

**Scope:** WCB_1, WCB_2 (15b), BS1_S (15c), WCC (15d), BS2_C, AVA_0, AVA_1, AVA_2 and WCD (the step-14 thin-bench
candidates). Three benches are not here:
- WCXY: its extent is a step-9a decision.
- WDFD: emerging, D2.
- OTHER: not a bench.

Running the thin benches does not decide their D2 status (step 14).

## 1. Well sets (bench QC, same tooling as 15a; NOT gated)

`python -m scripts.box_family_qc --family <WCB|BS1|WCC|BS2C|AVA|WCD>` → `docs/box/step15-<family>-2026-10-16/`
(per-bench QC pages, `wells_final_<bench>.csv`, index.html with flags, sensitivity and pooling evidence).

How the sets were built:
- The class rule of record and the gate-1 card verdicts, as for BS3. Uncalibrated classes keep their tag. No new cards.
- Frozen pools win: WCA, BS2_S and the BS3 sets are never re-decided (D84).
- `box_family_qc` now takes several frozen pool directories (Phase 1 + 15a).
- Regression check: the BS3 sets regenerate **byte-identical**.
- No api10 appears in two of the 13 sets (29,348 rows).

Michael went straight to the extent pass, so **these sets have not been confirmed at a QC gate**. Confirming them is
part of this review.

| bench | tagged live | final set | ≥ 2016 | D9 cohort | held by a frozen pool | uncalibrated flags (family) |
|---|---:|---:|---:|---:|---:|---|
| WCB_1 | 1,920 | 1,820 | 1,664 | 1,114 | 103 (WCA 102) | 148 in WCB, incl. WCB_1↔WCB_2 |
| WCB_2 | 1,190 | 1,181 | 1,090 | 757 | 12 (WCA) | (same) |
| BS1_S | 1,174 | 1,158 | 962 | 552 | 19 | 76 |
| WCC | 1,133 | 1,118 | 923 | 532 | 15 (+2 excluded) | 95 |
| BS2_C | 732 | 708 | 650 | 389 | 24 (BS2_S) | 33 |
| AVA_0 / AVA_1 / AVA_2 | 483 / 657 / 547 | 480 / 652 / 538 | 221 / 493 / 333 | 99 / 245 / 168 | 3 / 5 / 9 | 224 in AVA |
| WCD | 174 | 168 | 150 | 90 | 6 (WCA) | 31 |

Pooling evidence is recorded on each family page; it is not yet a decision:
- **WCB_2 vs WCB_1** (same block): 0.87× oil per kft [0.83–0.92] and 1.35× GOR. This differs more than BS3_S vs BS3_C.
- **AVA_1 vs AVA_0**: 0.99× oil, 1.20× GOR, shape 0.93×.
- **AVA_2 vs AVA_1**: 1.00× oil, 0.82× GOR.

**Caveat (WCB_2):** the known deep-TVD tagging problem (memory `wcb2-deep-tvd-screening`) is not re-screened here.
The 98 ratified overrides are already in the live tags.

## 2. Generated one-body D27 extents (method of record, calibration of record)

`python -m scripts.box_family_extents --wells docs/box/step15-<family>-2026-10-16 --pool <benches> --visual-bodies 50`
→ `…/extents/`. This writes the same pages and geology package as 15a, plus `visual_<bench>.png` (bench structure top,
PDP laterals, extent) and the PNG's pixel frame (`visual_<bench>.frame.json`). On the maps, outline components holding
≥ 50 modern laterals are dashed: **body 1** (purple) is the D27 body; the others (pink) are disconnected development.

| bench | extent sq mi | modern laterals inside | bodies ≥ 50 | D1 PUDs inside | note |
|---|---:|---:|---:|---:|---|
| BS2_C | 1,083 | 367 of 650 (56 %) | 3 | 2,247 | **SE body 2 (162 laterals) is not connected** — as Michael expected; body 3 (67) on the NW |
| WCB_1 | 3,921 | 1,580 of 1,664 (95 %) | 2 | 4,523 | |
| WCB_2 | 1,624 | 507 of 1,090 (47 %) | 4 | 1,668 | most fragmented; tagging caveat above |
| BS1_S | 1,535 | 777 of 962 (81 %) | 2 | 2,485 | |
| WCC | 1,455 | 751 of 923 (81 %) | 1 | 1,994 | |
| AVA_0 | 259 | 202 of 221 (91 %) | 1 | 607 | no AVA_0 grid: map shows the Avalon 1 top |
| AVA_1 | 548 | 409 of 493 (83 %) | 1 | 1,365 | |
| AVA_2 | 624 | 298 of 333 (89 %) | 1 | 2,851 | |
| WCD | 209 | 56 of 150 (37 %) | 0 | 20 | no body reaches 50 laterals; thin bench |

Grid assumptions (`extent_package.GRIDS`, context only, D25), as (bench top, next surface down):

| bench | top | next surface |
|---|---|---|
| BS1_S | 1BSPGS | 2BSPGC |
| BS2_C | 2BSPGC | 2BSPGS |
| WCB_1 | Wolfcamp B1 | B2 |
| WCB_2 | B2 | C |
| WCC | C | Wolfcamp D |
| WCD | Wolfcamp D | Strawn |
| AVA_0 | Avalon 1 | Avalon 2 |
| AVA_1 | Avalon 1 | Avalon 2 |
| AVA_2 | Avalon 2 | 1BSPGS |

## 3. The edit deck

`remaining_extents_2026-10-16.pptx` (here, with `.manifest.json`) has one slide per bench, in this order: BS2_C,
WCB_1, WCB_2, BS1_S, WCC, AVA_0, AVA_1, AVA_2, WCD.
- Each picture is placed exactly as in Michael's bs3_extents.pptx.
- Draw red freeforms: an edit outside the black outline adds that area; one inside cuts it. Several per slide are fine.
- A slide with no drawing is accepted as generated.

Ingest command:
`python -m scripts.box_family_extent_edits --pptx <edited deck> --manifest docs/box/step15-extents-2026-10-16/remaining_extents_2026-10-16.pptx.manifest.json`

Checks on the ingest:
- Smoke test: all 9 slides parse; the picture frames round-trip to the map corners exactly.
- The BS3 edits re-ingest to the same 4,998 / 3,840 sq mi under the updated code (now additions + cuts, multiple
  freeforms, recorded frames).

Nothing is stored. Storing follows the 15a pattern (`box.bench_scope` rows, generated v1, edited v1 as record) on an
explicit go-apply per bench.

## 4. Michael's edits (2026-10-16): ingested, AT THE EXTENT GATE (nothing stored)

The edit record is the deck Michael saved here, `remaining_extents_2026-10-16.pptx` (13:15). It was read through a
copy while PowerPoint held it open. Outputs are in `step15-<family>-2026-10-16/extents/edited/`: shapefile, diff page,
`reading_<bench>.png` (his loops on the exact PNG he drew on), and summary.json.

**Convention of record (Michael, 2026-10-16): the red loops ARE the extent; ignore the black generated outline.**
Extent = union of his closed pen loops, clipped to the map shown; voids filled; pieces under 1 sq mi dropped. Benches
with no loops keep the generated extent.

**Defect found and fixed: pen strokes were being placed in the wrong spot.** PowerPoint stores pen ink in InkML
coordinates that carry their own origin. The first reader assumed "box offset + 0.01 mm × 360 EMU", which put every
pen stroke up to ~1.7 in (on the slide) away from where it was drawn. That is why the first-pass readings and the
first two readings of this deck looked wrong.
- Fix: each ink part's extent is mapped onto the box PowerPoint placed it in.
- Verified against PowerPoint's own rendering of the ink (the fallback picture): median 0.4 px, max 0.9 px on all four
  slides.
- The BS3 edits used freeforms, a separate code path that was already verified exact; they are unaffected.

| bench | generated sq mi | **owner extent sq mi** | parts | ≥ 2016 laterals inside: generated → owner | D1 PUDs inside: generated → owner | developed laterals outside (by county) |
|---|---:|---:|---:|---|---|---|
| BS2_C | 1,083 | **1,525** | 2 (main + SE) | 367 → 547 of 650 | 2,247 → 3,005 | Eddy 44, Lea 29, Loving 13, other 17 |
| WCB_1 | 3,921 | **3,554** | 1 | 1,580 → 1,538 of 1,664 | 4,523 → 4,144 | Eddy 44, Reeves 34, Pecos 23, Culberson 17, Lea 8 |
| WCB_2 | 1,624 | **3,037** | 1 | 507 → 939 of 1,090 | 1,668 → 2,615 | Eddy 50, Ward 43, Reeves 26, Pecos 23, other 9 |
| BS1_S | 1,535 | **3,247** | 1 | 777 → 894 of 962 | 2,485 → 5,335 | Reeves 35, Pecos 20, Eddy 10, other 3 |
| WCC, AVA_0, AVA_1, AVA_2, WCD | as generated | unchanged | | | | |

The laterals left outside are mostly scattered step-out tests beyond the loops. That is the owner's call: a D27
exception only where the outside laterals are development, and they read as tests.

Storing follows the 15a pattern on an explicit go-apply: `box.bench_scope` rows, generated v1, then the owner v1 (or
the generated v1 for the unchanged benches) as the version of record.

## 5. QC gate — CLOSED 2026-10-16 (Michael)

1. **WCD dropped: emerging bench** ("not enough development history to be applicable for this type of workflow, the same
   way we're not doing WDFD extents"). This is a D2 addition: WCD joins Delaware WDFD as out of scope, shown as
   "not covered: emerging", worked by hand per deal. No WCD extent is stored; its generated extent and QC set stay
   here as the record of why. The other eight sets are confirmed as built (rule of record + gate-1 cards, no new cards).
2. WCB_1 and WCB_2 are **not pooled** (WCB_2 0.87× oil/kft [0.83–0.92], 1.35× GOR within block).
3. AVA_0 / AVA_1 / AVA_2 stay **separate for now**; pooling is revisited at step 14 / tuning (thin cohorts).
4. The WCB_1 state-line step (+16.5 % oil/kft, +817 ft TVD across the line) reads as **geology, not tagging**, for now.

Open, not blocking: the WCB_2 37-well high-value tag review (memory `wcb2-deep-tvd-screening`); 72 OTHER wells in
the AVA_0 band (step-14 thin-bench call).

These are proposed decisions of record for the next sequential session to number into plan §2 (D2 gains WCD).
