# BOX sticks: WCXY extent, evidence map for a hand-drawn outline (2026-11-12)

Read-only; nothing stored. `python -m scripts.box_sticks_wcxy_extent --out docs/box_sticks/wcxy-extent-2026-11-12
--verdicts docs/box_sticks/wcxy-cards-2026-11-12`.

Why hand-drawn: three automated rules were tested against Michael's 31 card calls and none beat calling every pad
XY (`../wcxy-tiers-2026-11-12/FINDINGS.md`).

**Revision (same day, Michael's request): the map now plots only WCXY-tagged wells at least 100 ft above the local
WCA_1 landing surface** (`--min-sep 100`): 925 of the 1,806 wells (Loving 536, Reeves 151, Eddy 123, Lea 49,
Culberson 38, Ward 25, Winkler 3). Wells with no WCA_1 control drop out with the rest. The dashed candidate is
rebuilt from those 925 wells and shrinks from 2,336 to 1,577 sq mi; it pulls back from western Eddy, Culberson
and northern Lea. The map window, and so the pen-edit frame, is unchanged. The description below is of the first
version (all wells); card markers and the background are the same on both.

## What is on `visual_WCXY.png`

- **Background**: the geologist's XY interval thickness, WOLFCAMP_A top minus WOLFCAMP_XY top (HCA structure
  grids, 10-19 set).
- **Small dots**: the 1,806 WCXY-tagged evidence wells with a location, coloured by how far each sits above the
  local WCA_1 landing surface (red = at WCA_1 depth, green = 200 ft or more above; grey = no WCA_1 control).
- **Large markers, numbered**: Michael's card calls. Green circle = XY, black X = one landing.
- **Dashed black**: a candidate outline, 2,336 sq mi, built with the BOX construction of record
  (`er.build_pool`, step-3 buffer parameters) from EVERY WCXY-tagged well. Well performance was not supplied, so
  every edge takes the "unknown" class. It is a guide, not a proposal.
- Dotted: the TX / NM line.

## What the map shows

1. **The geologist's XY interval does not separate the calls.** It is 108-224 ft thick (P10-P90) under the
   WCXY-tagged wells and never pinches out beneath them. Median under "XY" cards 141 ft, under "one landing" cards
   169 ft; no thickness cutoff beats calling everything XY (19 of 31). Correlation with the wells' separation
   above WCA_1 is 0.13. The grid says an XY interval is present across the whole tagged area.
2. **XY and one-landing calls are interleaved at the scale of a mile or two.** In Loving, cards 28, 31, 26 and 13
   (one landing) sit beside 3, 14, 9 and 12 (XY); in Eddy, card 2 (one landing) and 17 (XY) are the same lease.
   An extent line cannot separate neighbours like that.
3. **So the extent answers a different question from the cards.** The extent says where an XY landing exists as a
   target at all. Whether a particular WCXY-tagged well is really in it, or is an upper-WCA well with the wrong
   label, is a per-pad tag question that an outline will not settle.

## How to draw

Put `visual_WCXY.png` on a PowerPoint slide (any size; the reader takes the picture's position from the slide)
and draw the extent as one or more CLOSED RED loops, freeform or pen. The loops become the extent; the dashed
candidate is ignored. Save the .pptx and say where it is. `visual_WCXY.frame.json` beside the PNG holds the
map-to-pixel frame, so the PNG must not be cropped or re-rendered.

The edited outline is then read with `box/family_extent.pptx_freeforms` / `pptx_ink`, reported (area, WCXY-tagged
wells and card calls inside and outside), and stored as the WCXY extent of record only on an explicit go.

## Michael's hand-drawn extent (2026-11-12, `visual_wcxy.pptx`) - read, NOT stored

`python -m scripts.box_sticks_wcxy_edit --dir docs/box_sticks/wcxy-extent-2026-11-12 --pptx .../visual_wcxy.pptx`.
The picture in the pptx is byte-identical to `visual_WCXY.png` (the 100-ft version), uncropped. One closed pen
loop (ends 4 px apart). It crossed itself by a few feet near the south edge; cleaned with a zero-width buffer.
`reading_WCXY.png` shows the loop as read (red) over the map he drew on; `extent_WCXY_edited.geojson` is the
outline in lon / lat.

| | |
|---|---|
| Area | 1,730 sq mi, one piece (candidate 1,577 sq mi; 1,533 sq mi in common) |
| WCXY-tagged evidence wells inside / outside | 1,483 / 323 |
| ... of the 925 at least 100 ft above WCA_1 | 867 / 58 |
| Median ft above WCA_1, inside / outside | 120 / 47 |
| Card calls "XY" inside | 18 of 19 (card 6, Winkler, is outside) |
| Card calls "one landing" inside | 10 of 12 (cards 8 and 25 are outside) |

Outside by county: Eddy 129, Culberson 68 (all of them), Lea 62, Reeves 48, Ward 10, Winkler 6; Loving has none
outside. By state: New Mexico 191 of 610 outside, Texas 132 of 1,196. Wells outside: `wcxy_wells_outside_edited.csv`.

## Still to decide after the outline exists

- WCXY-tagged wells INSIDE the extent that sit at upper-WCA depth (the "one landing" pads): proposal, they are
  evidence for whichever landing surface they are nearest in depth, WCXY or WCA_1, and are listed for the
  formation-tag review. The tag itself is not changed by the surface builder.
- WCXY-tagged wells OUTSIDE the extent: treated as upper WCA (WCA_1).
