# Tops vs tags — step 1 findings (2026-10-20)

Plan: `~/.claude/plans/my-geologist-has-exported-buzzing-sketch.md` (step 1 of 3, gated).
Run: `python -m scripts.box_tops_qc` (READ ONLY). View: `python -m http.server 8766 --directory docs/box` →
`tops-qc-2026-10-20/step1.html`. Per-well detail: `wells_step1.csv` (UTM 14N US-ft x/y for GGX).

**Updated 2026-10-20 with the geology answers (below).** **Universe.** 31,707 Delaware producing horizontals, of which 29,618 have a tag with a grid interval. Of those
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
| WCA_1 57%, 41% **shallow** | WCA_1 | Median miss −40 ft, i.e. inside the ~97 ft XY interval just above the WCA top. Your BS3_S / WCXY / WCA_1 interface question, quantified |
| WCB_2 54%, 46% shallow | WCB_2 | Median miss −104 ft, so WCB_2-tagged wells sit in the grid's B1 interval (the Sept audit's B2/B1 story) |
| **Systematic** | WCC 6% (93% shallow, median −240 ft), WCD 13% (median −559 ft) | Not local structure: the whole tag class sits above the geologist's C / D tops. Nomenclature (what his WOLFCAMP-C top is vs Novi's WOLFCAMP C class) or a basin-wide surface offset. **Answered: C / D surfaces suspect → excluded** |
| **Systematic** | AVA_1 35% (64% **deep**, median +77 ft) | AVA_1 wells sit below the AVALON2 top. Answered: AVA_1 = Middle Avalon, no surface → excluded until one is built |

## 4. Other observations

- **Control distance barely separates agree from disagree** within a tag (≤ 1 mi vs > 1 mi from a pick, e.g.
  BS3_C 87% vs 77%, BS3_S 68% vs 59%; WCB_1 runs the other way). Disagreement is not mainly a "no control
  nearby" problem, except for the gross misses.
- **Survey vs single TVD.** Survey scoring raises agreement on the Bone Springs (BS3_S 52%→65%, BS2_S 89%→94%)
  but lowers it on WCA_1 (67%→55%), WCB_1 and WCB_2. `tvd_ft` sits about 32 ft deep, which flattered wells
  riding just above a top.

## Geology answers (2026-10-20) and how they are applied

These are decisions of record, in `box/tops_qc.py`. The step-1 page and CSV apply them; the raw geometric verdict
is kept as `verdict_raw`.

1. **WOLFCAMP-C and WOLFCAMP_D are suspect** and should be relabelled or re-picked.
   - **Applied:** WCC (965 wells) and WCD (128) are `surface_suspect` and not scored. A WCB_2 "deep" call (its base
     is the C top) is also `surface_suspect` (3 wells).
   - **Supporting data:** WOLFCAMP_D is a median ~108,000 ft from control even in Reeves.
2. **Avalon nomenclature.** AVALON1 = top Upper Avalon (operator Upper Avalon / Avalon tops +46 to +77 ft).
   AVALON2 = top Lower Avalon (+41 ft, 61 wells). Operator Middle Avalon tops sit a tight ~110 ft above AVALON2
   (29 wells, MAD 24 ft), and no surface exists there.
   - **Mapping:** AVA_0 → AVALON1–AVALON2 and AVA_2 → AVALON2–1BSPGS, both unchanged.
   - **AVA_1 straddles AVALON2.** It is `no_surface` (484 wells) until a Middle Avalon surface is built, which the
     geologist offered to do; it will be scored then.
3. **Pecos County: masked** for Wolfcamp A–D and AVALON2 (zero picks from the geologist or RRC; entirely modelled).
   - **Applied:** 210 WCA_1, 162 WCA_2, 35 WCB_1, 30 WCB_2 and 6 WCC wells are `masked`. AVA_0, AVA_2 and WCXY are
     masked there too, because AVALON2 or WOLFCAMP_A is their top or base.
   - **Still scored, with caution:** WOLFCAMP_XY, the Bone Springs and Bell/Cherry/Brushy. Their Pecos
     dist-to-control p50 is 5–9k ft, against WCA 52k, B1 47k, B2 57k, C 77k, D 241k and AVALON2 118k ft.
   - **Effect:** WCA_1 gross misses drop 46 → 19.

## Next (step 2, at the gate)

- Classify each well as agree / edge (±10/25/50 ft sensitivity) / shallow / deep / gross, plus the step-1
  exclusions (masked / surface_suspect / no_surface / not evidence).
- Attribute each disagreement to structure or tag using local same-tag bands.
- Build per-bench Leaflet maps with a `grid_offset_ft` heat layer, distance-to-control and the Pecos mask.
- Produce the GGX shapefile.
- WCC / WCD / AVA_1 stay out until the C / D re-pick and the Middle Avalon surface exist.

---

# Step 2 findings (2026-10-20): where the tag or the structure is wrong

Run: `python -m scripts.box_tops_qc --step 2` (READ ONLY; 10-19 grids, the geology rules above applied). Pages:
`step2.html` (index) plus one Leaflet map per bench, `step2_<TAG>.html`. GGX: `ggx/tops_qc_wells.shp` (29.5k points)
and `ggx/tops_qc_offset.shp` (half-mile offset cells), both NAD83 UTM 14N US-ft. Per well: `wells_step2.csv`.

**Method.**
- **Classes:** edge = a shallow / deep call within 25 ft of a surface; gross = |miss| > 300 ft.
- **Attribution:** each shallow / deep well is compared with its same-tag band (≥ 3 clean wells within 1.5 mi).
  - **structure_suspect:** the band sits outside the interval too, on the same side.
  - **tag_suspect:** the band agrees with the grid.
- **Offset cells:** the median residual of all wells bounding a surface, from both sides, on half-mile cells.
- **Caveat:** "structure suspect" means the local cluster disagrees with the grid. That is either the surface or a
  local naming convention; step 3 separates the two.

## Edge tolerance

The tolerance moves the Wolfcamp interface benches a lot, and the Bone Springs hardly at all.

| Tag | Disagree @10 ft | @25 ft | @50 ft |
|---|---|---|---|
| WCA_1 | 37% | 30% | 18% |
| WCXY | 24% | 18% | 10% |
| WCB_1 | 28% | 24% | 18% |
| WCB_2 | 43% | 40% | 35% |
| BS3_S | 26% | 22% | 18% |
| BS2_S | 4% | 3% | 2% |

## Attribution: the Wolfcamp disagreements are spatially coherent, the Bone Spring ones mostly isolated tags

| Tag | Structure-suspect | Tag-suspect | Band offset p50 | Where |
|---|---|---|---|---|
| WCA_1 | 912 | 472 | −50 ft (WCA top wants up) | Reeves 560, Loving 152, Lea 95 |
| WCB_2 | 274 | 37 | −118 ft (B2 top wants up) | Reeves 243 |
| BS3_S | 267 | 213 | +105 ft (lands below the XY top) | Reeves / Loving / Lea; +120–159 ft in Loving / Reeves |
| WCB_1 | 216 | 97 | −58 ft (above the B1 top) | broad: Lea 81, Loving 41, Culberson 33 |
| WCA_2 | 142 | 267 | +30 ft | mostly isolated tags |
| WCXY | 125 | 157 | +53 ft (below the WCA top) | Loving 61 |
| BS3_C | 70 | 56 | −72 ft | Eddy / Lea / Loving |
| BS2_S, BS1_S, BS2_C | 10 / 8 / 15 | 78 / 25 / 30 | — | **Bone Spring grids hold; disagreements are individual tags** |

## Where each surface wants to move (flagged half-mile cells)

| Surface | Flagged area | Direction | \|offset\| p50 / p90 |
|---|---|---|---|
| WOLFCAMP_A | 492 sq mi | up (1,867 of 1,966 cells) | 44 / 91 ft |
| WOLFCAMP-B2 | 347 sq mi | up (1,217 of 1,387) | 89 / 151 ft |
| WOLFCAMP_XY | 273 sq mi | **down** (1,006 of 1,090) | 66 / 171 ft |
| WOLFCAMP-B1 | 111 sq mi | mostly down (324 of 442) | 60 / 172 ft |
| 3BSPGC / 3BSPGS | 49 / 47 sq mi | mostly up | 76 / 116 ft p50 |
| Other Bone Spring / Avalon | ≤ 45 sq mi each | mixed | |

**The XY interval is squeezed from both sides.** BS3_S wells above it land inside it, so the XY top wants to go
down about 66 ft. WCA_1 wells below it land inside it too, so the WCA top wants to come up about 44 ft. WOLFCAMP_A
also has the most conflict cells (254), where WCA_1 above and WCXY below pull opposite ways. The ~97 ft XY interval
as gridded is where three tag families land. That is your BS3_S / WCXY / WCA_1 interface question, and step 3's
landing-position histograms are aimed at it.

## Control distance: two different problems

Share of wells more than 1 mi from a pick of the tag-top surface:

| Tag | Agree | Structure-suspect | Read |
|---|---|---|---|
| BS3_S | 32% | 49% | Structure-suspect clusters sit where control is sparse → **more picks would help** |
| BS3_C | 47% | 73% | Same |
| WCA_2 | 40% | 56% | Same |
| WCA_1 | 35% | 27% | Clusters sit **near** existing picks → more picks will not fix it; it is definitional |
| WCB_1 | 58% | 44% | Same |
| WCB_2 | 50% | 42% | Same: the Reeves cluster is inside control circles |

For WCA_1, WCB_1 and WCB_2, the question for the geologist is not "pick more" but "does your pick of this top match
the horizon operators land relative to?" That fits the regional-strategy hypothesis (shallow WCB_1s, deep WCB_1s)
and is what step 3 is for.

## Next (step 3, at the gate)

- Landing-position histograms: ft below each interval top, by tag, faceted by area (10-mi bins + county). First
  for the XY squeeze (3BSPGS → WCXY → WCA → B1) and the WCB_1 / WCB_2 boundary.
- Output: proposed edge-naming rules for Michael and the geologist to decide. Nothing is implemented.
