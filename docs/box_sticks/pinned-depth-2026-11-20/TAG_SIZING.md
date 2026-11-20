# Bone Spring mistag classes in the Delaware: a first sizing

> **CORRECTION, 2026-11-20 (same day).** The counts in this file include wells that are not producing: permits (approved and
> cancelled), spuds and DUCs whose header TVD is not a round 100 passed the depth-evidence test. A permit depth is a plan,
> not evidence. Of the 619 "both witnesses" wells, 180 are producing; of the 338 in the BS3_S -> BS3_C class, 50 are
> (147 are approved permits, 90 cancelled permits, 37 spud). **Use `TAG_PRODUCERS.md` for the sizes.** The cards and
> Michael's verdicts stand as cards; 19 of the 24 group S cards are non-producing wells.

2026-11-20, read-only on live, after the Novi v4 cutover (same day). Asked by Michael after the card review
(`cards/README.md`: 45 verdicts, 12 KEEP of which 11 carry "pinned well tag wrong"). Nothing changed: the tag rule, its tables
and its seeds were only read. This is a count to decide where to look, not a re-tag.

## The measure

Michael's own test on card 03: a well's height above local Wolfcamp A control.

- Grain: horizontal wells in the Delaware with depth evidence (never a planned survey; the survey lateral median, else the
  header TVD unless a round 100; at least 4,000 ft): 34,052 wells.
- Local control: the median depth of WCA_1-tagged wells with depth evidence within 3 miles, where there are at least 5.
  30,281 wells have it; 3,771 do not (14 % of BS3_S-tagged wells, 6 % of BS3_C, 23 % of BS2_S) and are not judged.
- h = local WCA_1 depth minus the well's depth, in ft. Positive = shallower than WCA_1.

Where each tag sits, basin-wide (h, ft):

| Tag | Wells | 25th | Median | 75th |
|---|---|---|---|---|
| WCA_1 | 5,769 | -33 | 3 | 44 |
| WCXY | 2,029 | 54 | 115 | 190 |
| BS3_S | 3,160 | 145 | 233 | 425 |
| BS3_C | 1,491 | 697 | 835 | 942 |
| BS2_S | 3,865 | 1,314 | 1,430 | 1,561 |
| BS1_S | 1,159 | 1,938 | 2,168 | 2,310 |

Levels used below are the midpoints between adjacent medians: BS3_S level 0 to 534 ft, BS3_C level 534 to 1,132 ft,
BS2 level 1,132 to 1,800 ft. **These are fixed basin-wide bands; the section thickens and thins, so a well near a boundary
proves nothing.** The geologist's structure grids (`box/tops_qc.py`) are the proper instrument and were not run here.

## Does the measure agree with the card calls?

The 13 pinned wells flagged as mis-tagged on the cards:

| Card | Tag | h (ft) | Level by h | Michael's note | Agrees |
|---|---|---|---|---|---|
| 01, 02, 07, 10, 15 | BS3_C | 1,336 to 1,391 | BS2 | should be BS2_S / tag wrong | yes |
| 18 | BS3_S | 1,214 | BS2 | tag wrong | yes |
| 09 | BS3_S | 771 | BS3_C | tag wrong | yes |
| 08 | BS1_S | 2,693 | above BS1 (Avalon range) | tag wrong | yes |
| 40 | WCB_2 | -281 | WCB_1 range (median -305) | should be WCB_1 | yes |
| 42 | WCA_2 | -526 | WCB_1 to WCB_2 range | tag or depth wrong | yes |
| 11, 12 | BS2_S | 1,740 and 1,732 | BS2 | tag wrong | **no: the measure sees a BS2-level well** |
| 27 | BS3_C | no WCA_1 control (Culberson) | | is a BS2_S | not judged |

10 of 12 judged agree. On cards 11 and 12 the measure cannot see what Michael saw.

## One place the measure and Michael's read differ: card 03

Michael: the local BS3_S tags are wrong and should be BS3_C, with BS2_S at about 10,500 ft and BS3_C at about 10,700 ft.

| Wells | TVD (ft) | h (ft) |
|---|---|---|
| Card 03, upper row (#422H, #424H; tagged BS2_S) | 10,451 and 10,507 | 1,708 and 1,710 |
| Card 03, lower row (tagged BS3_S x5, BS3_C x2, BS2_S x1) | 10,692 to 10,790 | 1,344 to 1,459 |
| Card 04 (Occidental, tags clean), BS2_S upper | 10,147 and 10,167 | 1,740 and 1,735 |
| Card 04, BS2_S lower | 10,420 and 10,443 | 1,462 and 1,447 |
| Card 04, BS3_C (two levels) | 10,798 to 10,984 | 904 to 1,087 |

The BS3_S tags on card 03 are wrong on either reading. But by height above WCA_1 the card 03 lower row matches card 04's
**lower BS2_S** landing (about 1,450 ft), not its BS3_C (about 900 to 1,090 ft). If that holds, the row is a second BS2_S
landing and BS3_C would sit near 11,100 to 11,250 ft there. Card 03 is in Lea, card 04 in Loving, so local thickness could
account for it; the grids would say. Michael's call stands unless he changes it.

## Sizes

Wells with depth evidence and local WCA_1 control, by tag and the level their depth puts them at:

| Tag | WC (below WCA_1) | BS3_S level | BS3_C level | BS2 level | above |
|---|---|---|---|---|---|
| BS3_S (3,160) | 171 | 2,347 | 407 | 163 | 72 |
| BS3_C (1,491) | 0 | 203 | 1,215 | 73 | 0 |
| BS2_S (3,865) | 15 | 11 | 359 | 3,326 | 154 |

| Candidate class | Wells | Share of the tag | Where |
|---|---|---|---|
| BS3_S tag, depth at BS3_C level or shallower | 642 | 20 % | Lea 331, Eddy 271, Texas 40 |
| BS2_S tag, depth at BS3_C level | 359 | 9 % | Lea 322 of the 384 below BS2 level |
| BS3_S tag, depth below local WCA_1 | 171 | 5 % | not broken out |
| BS3_C tag, depth at BS2 level | 73 | 5 % | Lea 36, Eddy 22, Loving 9; 70 carry Novi "THIRD BONE SPRING LIME" |

About 1,250 wells of 8,516 tagged BS3_S, BS3_C or BS2_S (15 %), nine in ten of them in Lea and Eddy. List:
`tag_sizing_delaware.csv` (1,099 rows: the first, second and fourth classes, the second with its 25 wells below BS3_C level).

## What the tag rule records for these wells

For the 13 flagged wells and the card 03 neighbours, `curated.formation_tag_rule` shows the rule left the vendor tag alone
(`applied = false`, step 0) in every case:

- Novi "THIRD BONE SPRING LIME" taken as BS3_C (`subbench_vendor`): cards 01, 02, 07, 10, 15, 27.
- Both vendors agreeing on "Third Bone Spring" with no sand / carbonate word, taken as BS3_S (`agree`): card 09 and the five
  Chevron SD 14 23 wells on card 03.
- The gross-miss check passed them (`gm_ok`) or had no control (`gm_no_control`).

Of the 642 BS3_S wells above BS3_S level, 532 have no row in `curated.formation_tag_rule` at all. Not traced.

## Limits

- Fixed bands, one anchor (WCA_1, itself a tag), 3-mile medians. Good for a count, not for a verdict on a well.
- Wells without depth evidence are not judged, as always.
- Midland not sized: its benches separate cleanly on the same measure (LSSH 329 to 474 ft, JM 734 to 846 ft above WCA_1),
  and none of the 13 flagged wells is in the Midland.

## Next, for Michael to decide

1. Run the same question on the geologist's grids (`box/tops_qc.py`: the 3BSPGC, 3BSPGS and 2BSPGS surfaces) so the bands
   follow structure and thickness instead of a basin-wide constant. Read-only.
2. Card a sample per class for verdicts (strike section, own tag, proposed tag, adjacent bands).
3. Accepted classes go in as tag-rule seeds and a reload, on an explicit go; then a stick regeneration, also on a go.
