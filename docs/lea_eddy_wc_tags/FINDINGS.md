# Lea / Eddy Wolfcamp B anomaly — findings (2026-11-03, revised 2026-11-04)

This is a read-only diagnosis; nothing was written to Supabase.

Sources:
- Producer data as of 2026-09-01 (Novi last reported month).
- Novi Intelligence 2026Q3 sticks.
- Geologist V5 grids (`Grids_10-19-26`).
- Delaware BOX record = run 32 (flipped 2026-11-04).

Rebuild everything here with `python docs/lea_eddy_wc_tags/build.py --out docs/lea_eddy_wc_tags` (about 1 min).

**Revision 2026-11-04: no planned surveys (Michael).** A well with `directional_survey_is_planned = TRUE` carries
the pre-drill plan for both its TVD and its lateral path. Its depth and its position are therefore not evidence.
- Michael's example: GOONCH FEDERAL COM 0409 #234H (planned) plotted almost on top of its stacked offset #214H.
- Planned wells are now never judged and never used as depth evidence. That covers the 3-mi WCA medians, the
  WCA plane, the producer grid table and the sensitivity table.
- They are never drawn on a card.
- The first version (PR #223) judged 27 planned wells among its 52 flags; that card set is withdrawn.

## Answer

**The producer tags are not the cause. Novi's NM `Wolfcamp B` sticks are.**
- In Lea, 1,071 of the 1,297 anomalous sticks sit above the geologist's B1 top, at Wolfcamp A depth or
  shallower. 735 of them sit at or above his XY top, which is 3rd Bone Spring Sand depth.
- On the same pad, Novi's own Wolfcamp B sticks sit at or above Novi's own Wolfcamp A sticks.

So H3 holds in NM, and H2 (dip) explains Pecos and Ward. H1 (producer tags) is real but small: a 31-well class
on real surveys, carded below. Dropping planned producers does not change the stick picture: Lea moves from
1,113 to 1,115 sticks.

## 1. The symptom (sticks)

`wca_delta_ft` = stick TVD minus the median TVD of WCA_1/WCA_2 producing horizontals within 3 mi (sql/30).
"Anomalous" means < −100 ft on a Novi `Wolfcamp B` stick. Grain: sticks, PUD + RES.

| County | WCB sticks | Anomalous | Median Δ (anom.) | Δ vs local WCA *plane* | WCA dip, ft/mi | WCB stick − Novi's nearest WCA stick (anom. / normal) |
|---|---|---|---|---|---|---|
| Lea | 3,217 | 1,297 | −324 ft | −238 ft | 131 | **−108 / +317 ft** |
| Eddy | 3,143 | 331 | −336 | −176 | 112 | +203 / +582 |
| Pecos | 2,228 | 274 | −244 | **+56** | 225 | +180 / +433 |
| Ward | 1,094 | 115 | −422 | **−34** | 144 | +56 / +294 |
| Reeves | 3,780 | 15 | −119 | −14 | 71 | −146 / +369 |

- **Plane:** a robust plane through the real-survey WCA producers within 3 mi, evaluated at the stick. It
  removes dip.
- **Novi WCA stick:** Novi's nearest `Wolfcamp A` / `A XY` stick within 1 mi. On a pad, dip cancels.
- In Lea, 857 of the 1,297 anomalous WCB sticks are shallower than Novi's own neighbouring Wolfcamp A stick,
  against 11 % of normal Lea sticks.
- Novi pad stacks in the Lea cluster (lat 32.15–32.75, lon −103.65 to −103.25), against each pad's Wolfcamp A
  stick:
  - Wolfcamp B: median −4 ft (IQR −200 to +256) over 266 pads.
  - South Lea, for comparison: Wolfcamp B +238 ft, Wolfcamp C +424 ft (2026-11-03 analysis).

## 2. Hypotheses

**H1: NM WCA producers are really WCB. Rejected as the cause.** All reads below use real surveys only.

- *Tag screen* (`box.tag_screen` rules A/B, consensus v2.2). Of 2,916 real-survey NM WCA_1/WCA_2 producers, it
  moves 14 toward WCB/WCC/WCD. Many more of its flags point *up*, to WCXY / BS3_S.
- *Geologist grids.*
  - 83 % of real-survey Lea WCA_1/WCA_2 producers sit inside his XY→B1 interval, which is the WCA bench under
    rule A (1,243 of 1,503). In Eddy it is 89 % (1,256 of 1,413).
  - 374 NM WCA producers sit at or below his B1 top. That is an upper bound on mis-tags, because his B1 is 46 %
    uncontrolled: 78 of the 242 real-survey *WCB_1*-tagged Lea producers also sit above it.
- *Sensitivity.* The stick count was recomputed with producers removed from the 3-mi WCA median (midpoint
  geometry: the live count is 1,297, recomputed 1,113):

  | Producers in the median | Lea | Eddy |
  |---|---|---|
  | all, including planned (recomputed live) | 1,113 | 216 |
  | real surveys only | 1,115 | 217 |
  | real only, minus the tag-screen WCA→deeper flags | 1,113 | 217 |
  | real only, minus the 31 rule-V flags | 1,111 | 217 |
  | real only, minus every grid-deep NM WCA producer (upper bound) | 733 | 79 |

  Planned producers do not drive the anomaly. Even the upper bound leaves 66 % of the Lea anomaly in place.

**H2: dip biases the 3-mi median. Explains Pecos, Ward and Reeves, and part of Lea.**

- With the plane, Pecos goes from −244 to +56 ft and Ward from −422 to −34 ft. Dip there is 144–225 ft/mi.
- Those sticks then sit at roughly the WCA plane rather than about 250 ft below it. This is not resolved further:
  - Pecos has no Wolfcamp grid control (tops-QC `no_control`).
  - Ward's operator names are inverted against the grid (tops-QC 2026-10-22).

**H3: Novi's NM `Wolfcamp B` sticks sit shallow. Holds in Lea and Eddy.** The grids are independent of both
vendors and of the producer tags. Grid interval at each anomalous stick's midpoint:

| County | above 3BSPGS | 3BSPGS→XY | XY→A | A→B1 | **B1 or deeper** | no grid |
|---|---|---|---|---|---|---|
| Lea | 278 | 457 | 165 | 171 | **146** | 80 |
| Eddy | 17 | 96 | 55 | 65 | **98** | 0 |

- Lea anomalous sticks: median 58 ft *above* his XY top and 260 ft above his B1 top.
- Normal Lea WCB sticks: 430 ft below XY and 54 ft below B1.
- Collisions (2026-11-03 analysis): 517 of the 1,628 Lea + Eddy anomalous sticks (32 %) have another Novi stick of
  a *different* formation within 330 ft horizontally and 100 ft TVD, against 10 % of normal sticks. The twins are
  3rd Bone Spring 214, WCXY 135, Wolfcamp A 83.
- Our data cannot tell whether Novi mislabelled a shallower location or carries a TVD that is 300–600 ft too
  shallow. Either way, the stick is not a Wolfcamp B location at the depth stated.

`wca_delta_ft` is therefore doing its job: it is catching bad sticks, not reporting bad producers.

## 3. What it touches

- **BOX Delaware record, run 32.** Of the 2,120 anomalous WCB sticks, 52 are covered: 42 above B1 by the grid,
  10 in or below it.
  - Most of the rest are `not_covered_outside_extent` (1,837).
  - Small exposure, but those 52 carry a WCB forecast at what is probably a WCA-or-shallower landing.
- **sql/19 / sub-bench v2 (PR #222, untouched here).** The Lea anomalous sticks are tagged WCB_1 675 / WCB_2 622.
  - A two-bench WCB model assigns a WCA-depth stick to WCB_1. It cannot see that the stick sits above both WCB
    benches.
  - That makes this a stick-side flag question for #222's gate, not a producer override.
- **Inventory (rule 11).** The 32 % that collide with another Novi bench's stick are probably duplicate locations.

## 4. The one producer class worth fixing: rule V

**Why the screen misses it.** sql/16 treats Novi `WOLFCAMP B` as coarse, so these wells take Enverus' interval.
`tag_screen.other_vendor` then counts Novi as no vote. NM wells that Novi calls Wolfcamp B but Enverus calls
Wolfcamp A are therefore invisible to the screen.

**The class.** 95 NM producing horizontals, all tagged from Enverus: 66 WCA_2, 28 WCA_1, 1 WCXY. There were 89 on
the 2026-11-03 pull, because vendor labels revise in place.

**Rule V** (fixed before any card was drawn):

1. Skip a well whose survey is planned.
2. Take its TVD minus the median of ≥ 3 clean WCA_1/WCA_2 witnesses within 1.5 mi. Clean witnesses already
   exclude planned surveys, and class wells are excluded too.
3. Place it on the nearest rung of the NM ladder: WCA 0 / WCB_1 +291 / WCB_2 +564 / WCC +814 ft. The rungs are
   medians of consensus-agree NM wells (TX: +262 / +505 / +796).

Result:

- 32 have planned surveys and are not judged.
- 14 have no depth evidence.
- 18 land on the WCA rung: depth backs Enverus, so the tag stays.
- **31 are flagged.** The grid independently puts 27 of the 31 at or below his B1 top.
  - 7 of the 31 reached WCA through the sql/23 TVD correction from an Enverus Bone Spring label. An override
    replaces that tag directly.
  - SANDLOT 9 8 FEE #825H, which Novi has since retagged to WCB_1, is no longer in the class.

| Class | Flagged | Cohort | Median ft below local WCA | Grid B1 or deeper | In a Delaware BOX record (run 32) oil pool |
|---|---|---|---|---|---|
| WCA_2→WCB_1 | 18 | 8 | 228 | 14 | 7 |
| WCA_2→WCC | 5 | 0 | 957 | 5 | 0 |
| WCA_1→WCB_2 | 4 | 2 | 537 | 4 | 2 |
| WCA_2→WCB_2 | 3 | 1 | 479 | 3 | 0 |
| WCA_1→WCC | 1 | 0 | 774 | 1 | 0 |

Caveats:
- tops-QC found that Lea does not separate WCB_2 from WCC against his B2 top. The WCB_2 vs WCC destination rests
  on the ladder alone.
- Out of scope, listed only: TX has 245 wells of the same Novi-B / Enverus-A kind, at a median 142 ft below local
  WCA, which is the WCA_2 | WCB_1 boundary (2026-11-03 analysis).

## 5. For Michael (the gate)

- **Cards:** `cards.html`, 18 cards: 5 per class, smaller classes in full, no planned-survey subjects.
  - Each card is a strike section orthogonal to the lateral. It shows the well's own tag, the proposed bench and
    the adjacent bands, with the legend above the plot.
  - Planned-survey neighbours are not drawn at all.
  - Each card states the grid interval and the ladder read.
- **Verdicts:** mark `accept` / `reject` in `cards_sample.csv`. A bench code means your own call on that well.
  - The gate is the tag screen's: 5/5 accepts the class, 0–1/5 rejects it, otherwise 5 more cards and 7/10.
- **Proposed seed:** `proposed_override_seed.csv`, 31 rows (api10, corrected_code, was, note).
  - It sits outside `seeds/`, and every row is marked NOT ratified / NOT applied.
  - It is re-derived from your verdicts by convention (a).
- **Apply is a separate go.** 9 of the 31 wells are in Delaware record (run 32) oil pools, all WCA. An apply
  moves them to WCB/WCC at the next Delaware build.
- **Stick side.** This is the actual anomaly; the steps are proposed and not done here:
  1. Raise with Novi that NM Wolfcamp B sticks are landed at or above their own Wolfcamp A sticks.
     `sticks_anomalous.csv` is the list, with pads and grid intervals.
  2. Decide at #222's gate whether "stick above the local WCA producers and above the grid's B1" becomes a
     stick-side flag, a sibling of the frontier / low-confidence flags.
- **Open, not done:** the live `wca_delta_ft` (sql/30) still counts planned producers in its WCA median. Here that
  moves nothing (1,113 vs 1,115 in Lea). Changing sql/30 is a warehouse change, if you want the rule applied
  there too.

### 5a. Verdicts (Michael, 2026-11-05)

All 18 cards were reviewed. 15 have a bench verdict and 3 are holds (free text).
- **Every judged well leaves WCA (15 of 15).**
- **13 of 15 land on the proposed rung.** The two that differ move one rung inside WCB, and in both the call
  matches the geologist's grid interval rather than the NM ladder:
  - SD EA 29 FEDERAL COM P8 #011H: proposed WCB_2, called WCB_1 (grid B1→B2).
  - SEINFELD MH FEDERAL UNIT #224H: proposed WCB_1, called WCB_2 (grid B2→C).
- **Holds:** BELL LAKE UNIT NORTH #407H and BILBREY 34 27 #001H ("lacking deep neighbors"), and JAMES RANCH UNIT DI 2
  #111H (no well-defined TVD band for deeper targets; not a candidate for this screening).

Class decisions use `box.tag_screen.decide`. A bench code that differs from the proposed one counts against its
class, and holds are not counted.

| Class | Flagged | Carded | Judged | Agree | State |
|---|---|---|---|---|---|
| WCA_1→WCB_2 | 4 | 4 | 4 | 3 | accept (full class) |
| WCA_1→WCC | 1 | 1 | 0 | 0 | pending (hold) |
| WCA_2→WCB_1 | 18 | 5 | 3 | 2 | pending: 13 wells uncarded |
| WCA_2→WCB_2 | 3 | 3 | 3 | 3 | accept (full class) |
| WCA_2→WCC | 5 | 5 | 5 | 5 | accept (full class) |

**Seed.** `proposed_override_seed.csv` is now the 15 card-level calls (convention (a)): each card decides its own
well. No accepted class has uncarded wells, so nothing moves without a card. The 13 uncarded WCA_2→WCB_1 wells
and the 3 holds keep their tags. All 15 rows are ratified but **NOT applied**, and none is in
`ref.formation_tag_overrides` today (checked live, read-only, 2026-11-05).
- **Effect if applied:** 4 of the 15 are in Delaware record (run 32) oil pools, all WCA (api10 3001545999,
  3001546491, 3001553606, 3002543270). An apply moves them out at the next Delaware build. The priced run-32
  forecasts do not change until then.

**Disposition.** These calls are held, not applied, as the labelled test set for the formation_blueox redesign under
discussion (family from the vendor, sub-bench position from depth against the geologist's surfaces; tag-consistency
audit 2026-11-05).
- A redesigned rule should reproduce the 15 calls.
- It should abstain on the 3 holds, which have no local deeper-bench control.
- Applying them on their own remains a separate go.

## Files

| File | What |
|---|---|
| `build.py` | the whole analysis, read-only (`SET TRANSACTION READ ONLY`) |
| `summary.json` | headline counts |
| `sticks_by_county.csv`, `sticks_anomalous*.csv` | stick-side reads per county / per stick, grid intervals, BOX coverage |
| `producers_nm_grid_interval.csv` | real-survey NM Wolfcamp producers by tag × grid interval |
| `sensitivity_wca_median.csv` | the H1 sensitivity table |
| `rule_v_class.csv`, `classes.csv` | the 95-well class (planned ones marked, not judged) and the 31 flags by class |
| `cards.html`, `cards_sample.csv` | review cards + verdict file |
| `proposed_override_seed.csv` | proposed override rows, not ratified, not applied |
