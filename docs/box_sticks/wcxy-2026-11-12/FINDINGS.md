# BOX sticks: WCXY evidence pass, Delaware (2026-11-12)

Read-only, live tags. `python -m scripts.box_sticks_wcxy --out docs/box_sticks/wcxy-2026-11-12`.
Plan `docs/box_sticks_plan.md`, phase 1b. No extent is built here.

Grain: 1,815 WCXY-tagged evidence wells (horizontal producers; planned surveys and round-100 permit depths
excluded). 1,796 of them carry the Enverus raw value `WOLFCAMP XY` through the crosswalk. The shadow tag rule moves
none of them.

## The test

A well is compared with the WCA_1 landing surface at its own location (>= 3 WCA_1 wells within 2 mi). Real XY
development should show two distinct landings, the WCXY well clearly above WCA_1.

| Class | Meaning | Wells |
|---|---|---|
| stacked | >= 75 ft above the local WCA_1 surface | 1,114 (61 %) |
| same_depth | within 75 ft of the WCA_1 surface | 598 (33 %) |
| below | >= 75 ft below it | 41 (2 %) |
| no_wca1 | no WCA_1 surface there; depths cannot tell | 62 (3 %) |

Where WCA_1 control exists the WCXY-tagged wells sit a median 107 ft above it (P10 17 ft, P90 218 ft).

## Where they are

**No WCXY-tagged evidence well lies south of about 31.5 N.** The southern part of the pooled WCA extent (southern
Reeves, Pecos, southern Ward) has WCA_1 / WCA_2 development and no WCXY tags at all. So the vendor is not spraying
the label across the whole WCA; the problem population is inside the northern area.

| County | Wells | Stacked | Same depth | Median ft above WCA_1 |
|---|---|---|---|---|
| Loving | 809 | 77 % | 19 % | 129 |
| Reeves (north) | 246 | 72 % | 25 % | 128 |
| Culberson | 68 | 68 % | 29 % | 108 |
| Ward | 56 | 48 % | 25 % | 135 |
| Eddy | 369 | 43 % | 48 % | 62 |
| Lea | 250 | 32 % | 64 % | 54 |
| Winkler | 17 | 47 % | 53 % | 58 |

By state: Texas 1,196 wells, 73 % stacked, median 127 ft above WCA_1. New Mexico 619 wells, 38 % stacked, 55 % at
the same depth as WCA_1, median 57 ft. By latitude the split is sharp at 32.0 N (the state line): 70-86 % stacked
in the bands from 31.6 to 32.0 N, 28-43 % from 32.0 to 32.4 N (`by_lat_band.csv`, map `wcxy_evidence_map.png`).

## What the depths can and cannot say

- **Texas side (Loving, north Reeves, Culberson): the stacked signature is clear.** Two landings about 130 ft
  apart, WCA_1 wells within a quarter mile. This is real, separately developed XY.
- **New Mexico (Eddy, Lea): most WCXY-tagged wells sit at WCA_1 depth.** The test cannot tell which label is wrong.
  Either the "WOLFCAMP XY" wells are plain upper-WCA landings (Michael's concern), or the neighbouring WCA_1-tagged
  wells are themselves XY landings under another name and there is only one landing there. Depth alone shows ONE
  landing where the tags claim two; it does not say what to call it.
- Same-depth wells sit a median 184 ft below the BS3_S surface and 190 ft above WCA_2; stacked wells 124 ft below
  BS3_S and 270 ft above WCA_2. So the same-depth population is about 60-80 ft deeper in the section than true
  stacked XY, consistent with an upper-WCA_1 landing.
- 41 wells sit below WCA_1 and are simply wrong as WCXY.
- The class is stable through time (same-depth share 37-44 % for 2016+ vintages), so it is not an old-data artefact.

## For Gate 1b (Michael)

1. **Is the New Mexico same-depth population XY or upper WCA?** A geological call. It decides whether the WCXY
   extent stops near the state line / Loving-Eddy trend or runs up into Eddy and Lea.
2. **The Grisham fault complex.** Every WCXY tag is already north of about 31.5 N. If the fault is the southern
   limit, the tags do not contradict it; a line source is still needed to draw it.
3. **Candidate extent.** Proposal: build it with the BOX construction of record (`box/family_extent.py`, same
   constants as every other bench) from the 1,114 stacked wells only, then apply Michael's edits. Read-only until
   an explicit go to store.
4. Once an extent exists: WCXY-tagged wells outside it, and the same-depth wells inside it, are treated as upper
   WCA (WCA_1) by the BOX surface builder; correcting the tags themselves is a formation-tag seed after 11-16.
