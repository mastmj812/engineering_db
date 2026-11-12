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

## Still to decide after the outline exists

- WCXY-tagged wells INSIDE the extent that sit at upper-WCA depth (the "one landing" pads): proposal, they are
  evidence for whichever landing surface they are nearest in depth, WCXY or WCA_1, and are listed for the
  formation-tag review. The tag itself is not changed by the surface builder.
- WCXY-tagged wells OUTSIDE the extent: treated as upper WCA (WCA_1).
