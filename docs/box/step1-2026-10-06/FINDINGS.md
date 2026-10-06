# BOX step 1 — bench QC, Delaware pilot benches: findings for gate 1

Built 2026-10-06 from the live warehouse (read-only; nothing written). Pages: `index.html`,
`qc_WCA_1.html`, `qc_WCA_2.html`, `qc_BS2_S.html`; per-well sets `wells_<bench>.csv`;
numbers in `summary.json`. Regenerate with `python -m scripts.box_bench_qc`.

**Grain:** producing horizontals (one row per api10) in `curated.wells_enriched`,
`basin_blueox = delaware`, `is_horizontal`, `first_production_date NOT NULL`, grouped on the
TVD-corrected `formation_blueox`. Warehouse as-of (max `last_reported_month`): 2026-08-01.
**Cohort (D9):** first prod ≥ 2016-01-01, lateral 6,000–13,000 ft, 12 full months, cum12 > 0.
12-mo oil is Novi's `cum_12m_oil_bbl` pass-through; per-ft uses `lateral_length_ft`.

## 1. Counts

| bench | producing hz | TX | NM | D9 cohort | planned survey (NM) | permit-round TVD | cohort median 12-mo oil, bbl/1,000 ft (TX / NM) |
|---|---|---|---|---|---|---|---|
| WCA_1 | 5,680 | 3,601 | 2,079 | 3,623 | 7.0 % (19.1 %) | 1.5 % | 21,939 (19,859 / 26,107) |
| WCA_2 | 4,542 | 3,110 | 1,432 | 2,804 | 5.6 % (17.7 %) | 1.5 % | 20,202 (17,938 / 25,363) |
| BS2_S | 4,307 | 534 | 3,773 | 1,877 | 14.6 % (16.6 %) | 2.4 % | 23,388 (20,053 / 23,939) |

Delaware producing horizontals in total: 31,542; clean consensus witnesses: 25,458.
Planned-survey share in these benches (NM 17–19 %) is well below the dictionary's "~44 % of NM
producers" — that figure is all NM producers, all benches; not a conflict, a note.

## 2. Tag disagreement

Two measures (page §2): **sql/23 live** (40-NN bands, nearest band ≠ assigned, any margin) and the
**consensus v2 rule re-implemented** from the recorded rules (the 2026-09 script is not in the repo —
see §5 item c).

| bench | sql/23 disagree | consensus flags | flags → suggested | flagged INTO the bench | lith-ambiguous |
|---|---|---|---|---|---|
| WCA_1 | 26.7 % | 577 (10.2 %) | WCA_2 305, WCXY 182, BS3_S 61, WCB_1 15 | 748 (WCA_2 370, WCXY 228, BS3_S 117) | 0 |
| WCA_2 | 28.9 % | 544 (12.0 %) | WCA_1 370, WCB_1 114, WCXY 37 | 564 (WCA_1 305, WCB_1 154) | 0 |
| BS2_S | 7.2 % | 62 (1.4 %) | BS3_C 45, BS1_S 5, BS3_S 5 | 77 (BS3_C 68) | 19 (BS2_S↔BS2_C) |

Flag share by survey class, WCA_1: TX 8.4 % / NM actual-survey 12.4 % / NM planned 16.6 %;
WCA_2: 10.6 / 13.9 / 19.4 %; BS2_S: 1.3 / 1.3 / 2.1 %. The planned-survey flag raises the
mis-tag rate only modestly; the dominant driver in WCA is the thin WCA_1/WCA_2/WCXY stack.

**Adjacent-bench local separation** (other band median − own, where both bands are coherent in the
same 1.5-mi neighbourhood; "merged" = within 100 ft):

| pair | neighbourhoods | median sep | IQR | merged | merged TX / NM | inverted |
|---|---|---|---|---|---|---|
| WCA_1 → WCA_2 | 2,702 | +128 ft | 68–181 | 36 % | 38 % / 29 % | 8 % |
| WCA_1 → WCXY | 1,282 | −100 ft | −160–−51 | 49 % | 37 % / 66 % | 10 % |
| WCA_1 → BS3_S | 1,285 | −210 ft | | 11 % | | 3 % |
| WCA_1 → WCB_1 | 1,448 | +323 ft | | 1 % | | 0 % |
| WCA_2 → WCB_1 | 1,090 | +190 ft | 116–260 | 19 % | 21 % / 13 % | 4 % |
| BS2_S → BS3_C | 515 | +487 ft | 333–576 | 14 % | 26 % / 10 % | 9 % |

The stack order holds (WCA_2 is below WCA_1 in 92 % of neighbourhoods) but the WCA_1/WCA_2 split
is a ~130-ft sub-bench distinction and WCXY sits in the WCA_1 band in NM. BS2_S is clean against
its neighbours except BS3_C in TX.

**Detector validation:** on the 98 ratified overrides (`ref.formation_tag_overrides`, all live as
the current tag): 87 agree, 5 off-band, 6 would flag — Merciless 3002547676 (detector reproduces the
jury's WCA_2 at 39 ft that Michael overrode to WCB_1, as recorded) and five others at the evidence
margin (22–115 ft), the recorded pattern for his rejections. 89 % agreement with ratified decisions.

## 3. State-line check

Border verdict **no_step** on all three benches (cohort median 12-mo oil/ft, −10..0 vs 0..10 mi):

| bench | border step | typical adjacent-bin step | max other step |
|---|---|---|---|
| WCA_1 | 8.6 % | 12.3 % | 21.0 % |
| WCA_2 | 14.0 % | 10.8 % | 30.6 % |
| BS2_S | 10.2 % | 11.8 % | 22.5 % |

NM oil/ft is ~30 % above TX in WCA but the rise is gradual over 30+ mi (WCA_1 bins −30/−20/−10/0/+10:
20.0 / 21.0 / 23.7 / 25.9 / 28.3 kbbl per 1,000 ft) — basin position, not a border artifact.
Planned-survey share steps 0 % → 15–20 % at the line: the NMOCD reporting overprint, expected.
Median TVD in 10-mi bins steps ~770 ft (WCA_1) / ~1,240 ft (WCA_2) at the border; in 2-mi bins WCA_1
is smooth (11,662 ft at −2 mi vs 11,647 at 0) and WCA_2 jumps 10,840 → 11,535 between the −2 and 0
bins. The strips mix east–west (WCA_2 even reads shallower than WCA_1 in the same strips), and the
local separation table says the stack order holds, so this is read as position mixing, not a tag
step — but WCA_2 within ±5 mi of the line is the one place to look if Michael wants a second check.
TVD is KB-relative; the warehouse has no elevation column, so no datum correction was possible.

## 4. NM planned-survey wells — the §9 decision

| bench | NM planned | consensus: agree / off-band / flag / no-evidence / ambiguous | flags → | oil/ft NM planned vs NM actual vs TX (bbl/1,000 ft) |
|---|---|---|---|---|
| WCA_1 | 397 | 194 / 79 / 66 / 30 / 28 | WCA_2 24, WCXY 20, BS3_S 10, WCB_1 6 | 24,167 (n 294) / 26,463 (n 1,082) / 19,859 |
| WCA_2 | 253 | 120 / 56 / 49 / 15 / 13 | WCA_1 35, WCXY 6, WCB_1 4 | 24,101 (n 175) / 25,577 (n 786) / 17,938 |
| BS2_S | 628 | 288 / 227 / 13 / 97 / 2 | BS3_C 8, WCA_2 3 | 23,192 (n 390) / 24,286 (n 1,267) / 20,053 |

Effect on the D9 cohort (TX / NM):

| bench | current | A — reassign flagged planned wells by local consensus (BOX-only) | B — exclude all planned-survey wells |
|---|---|---|---|
| WCA_1 | 2,247 / 1,376 | 2,247 / 1,326 (67 out, 66 in) | 2,246 / 1,082 (400 dropped) |
| WCA_2 | 1,843 / 961 | 1,843 / 922 (49 out, 63 in) | 1,843 / 786 (253 dropped) |
| BS2_S | 220 / 1,657 | 220 / 1,649 (13 out, 6 in) | 220 / 1,267 (628 dropped) |

Recommendation (Michael decides): **A**, applied to every survey class — planned-survey wells are
not much worse than NM actual-survey wells, and TX wells flag at 8–11 % too; B would hollow out the
NM side (−21 to −29 % of NM cohort) for little gain. Under A, flagged wells (any state) leave edge and
cohort evidence for their tagged bench and join the suggested one; `ambiguous` / `off_band` /
`no_evidence` wells stay as tagged. Nothing changes in the warehouse.

## 5. Conflicts and items flagged for Michael (not resolved here)

a. **D4 pilot = WCA_1 / WCA_2 as separate benches.** Locally they are ~130 ft apart and merge in 36 % of
   neighbourhoods; swaps dominate the flags both ways. Options: keep separate and carry a ~10 %
   review class into step 2, or pool as WCA for extents/areas and split only at the curve step.
b. **WCXY.** 1,965 Delaware producers (TX 1,231 / NM 734), all Enverus-tagged, in the WCA_1 band in NM
   (66 % merged). Rule 19 already equates WCXY ≡ WCA_1 for the PDP donor pool. Whether WCXY wells are
   WCA_1 evidence for extents and cohorts is a decision, not a QC fix.
c. **"Gunbarrel-consensus detector (v2, sql/23 bands)"** in the plan: the v2 script was a session
   scratchpad and is not in the repo; sql/23 is a looser 40-NN audit (27–29 % disagreement in WCA).
   The page reports both; the consensus column is a re-implementation from the recorded rules
   (`box/bench_qc.py`, 12 DB-free tests, 89 % agreement with the ratified overrides). If the v2
   script resurfaces, swap it in; otherwise this is the detector of record for BOX.
d. **`runs/` is git-ignored** (plan §10 says "runs/ or docs/"); the deliverable lives in
   `docs/box/step1-2026-10-06/` and the CLI defaults there.
e. **BS2_S consensus coverage is thin:** 35 % off-band + 8 % no-evidence (thin, variable Bone Spring
   sands; IQR ≤ 150 ft bands rarely form). Its flags are few (1.4 %); treat the detector as weak
   evidence on BS2_S and lean on sql/23 + the lith guard there.

## 7. Gate-1 decisions (Michael, 2026-10-06) and the calibration cards

- **D19:** WCA_1 + WCA_2 pooled as `WCA` for extents and areas; the sub-bench split happens at the
  curve step, settled by sensitivity. **D20:** WCXY counts as WCA_1 evidence one-way; WCA_1 is never
  WCXY evidence (WCXY is a north-side regional target; Reeves-County WCA_1 must not extend it south).
- **Option A adopted** for planned-survey / permit-round wells: evidence unless consensus-flagged,
  every survey class. **Well-by-well review is off the table**; consensus flags are ratified per
  swap class from calibration cards.
- **Cards:** `cards.html` — 797 flags in 24 cross-pool classes touching the pilot evidence sets
  (in-pool WCA swaps and flags into WCXY are not carded), 142 cards: 10 per class at evenly spaced
  quantiles of the margin ratio (weakest first), small classes in full. Big classes: WCB_1→WCA 165,
  BS3_S→WCA 159, WCA→BS3_S 133, WCA→WCB_1 131, BS3_C→BS2_S 68, BS2_S→BS3_C 45. Each card: cross-section
  of the 1.5-mi neighbourhood (east-west offset vs TVD, tags coloured, hollow = not clean evidence,
  dashed = local band medians), plan inset, local cohort 12-mo oil/ft by bench with the subject dashed.
  Mark agree / reject by api10 in chat, or fill the `verdict` column of `cards_sample.csv`; a class
  is accepted or rejected wholesale on its precision. `flags_all.csv` lists every flag in those classes.
- **Sensitivity** (cards.html top table): applying every carded flag under option A moves the WCA
  cohort median 12-mo oil/ft from 21,735 to 21,674 bbl per 1,000 ft (−0.3 %) and BS2_S from 23,388 to
  23,381 (0.0 %); TVD IQR unchanged. The flags matter for which wells pin an extent edge, not for the
  cohort statistics.

## 6. Gate 1 asks (superseded by §7 where decided)

1. Confirm the well set per bench: `wells_<bench>.csv`, column `qc_role` (`evidence` / `review`) with
   `qc_reason`. Review class (planned survey, permit-round TVD, or a consensus flag): WCA_1 968 of
   5,680 (17 %), WCA_2 796 of 4,542 (18 %), BS2_S 737 of 4,307 (17 %); the rest are `evidence`.
2. Decide the NM planned-survey item (§4): A, B, or other.
3. Decide a / b above (WCA_1-vs-WCA_2 handling; WCXY membership) before step 2's outlines are drawn.
