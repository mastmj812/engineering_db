# Tops vs tags — step 1 findings (2026-10-20)

Plan: `~/.claude/plans/my-geologist-has-exported-buzzing-sketch.md` (step 1 of 3, gated).
Run: `python -m scripts.box_tops_qc` (READ ONLY). View: `python -m http.server 8766 --directory docs/box` →
`tops-qc-2026-10-20/step1.html`. Per-well detail: `wells_step1.csv` (UTM 14N US-ft x/y for GGX).

**Universe.** 31,707 Delaware producing horizontals, of which 29,618 have a tag with a grid interval. Of those
29,618, 22,460 were scored at every lateral survey station (sql/64) and 7,113 at the single midpoint `tvd_ft`.
The evidence set is 26,271 wells: planned surveys excluded, ≥ 6 mo online, non-round `tvd_ft` when there is no
survey, landing ≥ 4,000 ft.

## 1. Datum: PASS

Grid Z is depth below KB, so it compares directly with survey TVD. Agreement is 70% against TVD versus 0%
against subsea, for both grid sets.

## 2. The 10-19 update is a conformance and extent update, not a re-pick around wells

- **Surface order:** no crossings anywhere. The September set had 1–11% of nodes with a negative isopach
  (XY→WCA 7.5%, WCD→Strawn 11%).
- **Minimum thickness:** isopach floors sit at exactly 10 ft (B1→B2, WCD→Strawn), which looks like a
  minimum-thickness rule.
- **Movement at wells:** the median shift per surface is about 0 ft, with P10/P90 about ±30–50 ft. 8–20% of wells
  moved more than 50 ft; the Strawn moved the most (52%).
- **Consequence:** agreement is essentially unchanged from September on every tag.
- **Coverage:** the new set extends into Pecos with little control there. 46 WCA_1 gross misses sit a median
  60,000 ft from the nearest WCA pick.

## 3. Agreement by tag (new grids, evidence wells)

| Pattern | Tags | Read |
|---|---|---|
| Agree ≥ 90% | AVA_0, AVA_2, BS2_S | Grid and tag consistent |
| Agree 65–85% | BS1_S, BS2_C, BS3_C, WCXY, WCA_2, WCB_1, BS3_S | Mixed; 30–65% of misses within 50 ft of a surface (edge cases) |
| WCA_1 55%, 41% **shallow** | WCA_1 | Median miss −39 ft, i.e. inside the ~97 ft XY interval just above the WCA top. Your BS3_S / WCXY / WCA_1 interface question, quantified |
| WCB_2 54%, 46% shallow | WCB_2 | Median miss −104 ft, so WCB_2-tagged wells sit in the grid's B1 interval (the Sept audit's B2/B1 story) |
| **Systematic** | WCC 6% (93% shallow, median −240 ft), WCD 13% (median −559 ft) | Not local structure: the whole tag class sits above the geologist's C / D tops. Nomenclature (what his WOLFCAMP-C top is vs Novi's WOLFCAMP C class) or a basin-wide surface offset. **A question for the geologist, not a map** |
| **Systematic** | AVA_1 35% (64% **deep**, median +77 ft) | AVA_1 wells sit below the AVALON2 top. Likely nomenclature (which Avalon surface is AVA_1's top?). AVA_0 sits on the same AVALON1→AVALON2 interval and agrees 94% |

## 4. Other observations

- **Control distance barely separates agree from disagree** within a tag (≤ 1 mi vs > 1 mi from a pick, e.g.
  BS3_C 87% vs 77%, BS3_S 68% vs 59%; WCB_1 runs the other way). Disagreement is not mainly a "no control
  nearby" problem, except for the gross misses.
- **Survey vs single TVD.** Survey scoring raises agreement on the Bone Springs (BS3_S 52%→65%, BS2_S 89%→94%)
  but lowers it on WCA_1 (67%→55%), WCB_1 and WCB_2. `tvd_ft` sits about 32 ft deep, which flattered wells
  riding just above a top.

## Questions for the geologist (before step 2 attributes structure vs tag)

1. **WCC / WCD:** your WOLFCAMP-C and WOLFCAMP_D tops sit a median 240 / 560 ft below where Novi-tagged WCC / WCD
   laterals land. Is your C top the same horizon Novi/operators call Wolfcamp C?
2. **Avalon:** which surface is the top of AVA_1 (Middle Avalon?) — AVALON1 or AVALON2? Is there a surface
   between them?
3. **Pecos County:** the 10-19 extent adds an area with essentially no picks. Should it be masked, or are picks coming?

## Next (step 2, at the gate)

- Classify each well as agree / edge (±10/25/50 ft sensitivity) / shallow / deep / gross / no-evidence.
- Attribute each disagreement to structure or tag using local same-tag bands.
- Build per-bench Leaflet maps with a `grid_offset_ft` heat layer and distance-to-control.
- Produce the GGX shapefile.
- Exclude WCC / WCD / AVA_1 from the structure attribution until question 1/2 is answered (a systematic offset
  would paint the whole basin "structure suspect").
