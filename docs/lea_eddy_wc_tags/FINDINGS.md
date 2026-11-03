# Lea / Eddy Wolfcamp B anomaly — findings (2026-11-03)

Read-only diagnosis. Nothing was written to Supabase. Producer data as of 2026-09-01 (Novi last reported month),
Novi Intelligence 2026Q3 sticks, geologist V5 grids (`Grids_10-19-26`). Rebuild everything here with
`python docs/lea_eddy_wc_tags/build.py --out docs/lea_eddy_wc_tags` (about 1 min).

## Answer

**The producer tags are not the cause. Novi's NM `Wolfcamp B` sticks are.** In Lea, 1,071 of the 1,297
anomalous sticks sit above the geologist's B1 top: at Wolfcamp A depth or shallower. 735 of them sit at or
above his XY top, which is 3rd Bone Spring Sand depth. On the same pad, Novi's own Wolfcamp B sticks sit at or
above Novi's own Wolfcamp A sticks. So H3 holds in NM. H2 (dip) explains Pecos and Ward. H1 (producer tags)
is real but small: one 52-well class, proposed below for your cards. Fixing it moves the stick picture by about 5 %.

## 1. The symptom (sticks)

`wca_delta_ft` = stick TVD minus the median TVD of WCA_1/WCA_2 producing horizontals within 3 mi (sql/30).
"Anomalous" means < −100 ft on a Novi `Wolfcamp B` stick. Grain: sticks, PUD + RES.

| County | WCB sticks | Anomalous | Median Δ (anom.) | Δ vs local WCA *plane* | WCA dip, ft/mi | WCB stick − Novi's nearest WCA stick (anom. / normal) |
|---|---|---|---|---|---|---|
| Lea | 3,217 | 1,297 | −324 ft | −235 ft | 138 | **−108 / +317 ft** |
| Eddy | 3,143 | 331 | −336 | −173 | 111 | +203 / +582 |
| Pecos | 2,228 | 274 | −244 | **+32** | 199 | +180 / +433 |
| Ward | 1,094 | 115 | −422 | **+24** | 148 | +56 / +294 |
| Reeves | 3,780 | 15 | −119 | +42 | 80 | −146 / +369 |

- **Plane:** a robust plane through the WCA producers within 3 mi, evaluated at the stick. It removes dip.
- **Novi WCA stick:** Novi's nearest `Wolfcamp A` / `A XY` stick within 1 mi. On a pad, dip cancels.
- In Lea, 857 of the 1,297 anomalous WCB sticks are shallower than Novi's own neighbouring Wolfcamp A stick. Only
  11 % of normal Lea sticks are.
- Novi pad stacks in the Lea cluster (lat 32.15–32.75, lon −103.65 to −103.25), measured against each pad's
  Wolfcamp A stick:
  - Wolfcamp B: median −4 ft (IQR −200 to +256), across 266 pads.
  - South Lea, for comparison: Wolfcamp B +238 ft, Wolfcamp C +424 ft.

## 2. Hypotheses

**H1: NM WCA producers are really WCB. Rejected as the cause.**

- *County stack is in order.* Lea producers: WCA_1 12,396 ft, WCA_2 12,400, WCB_1 12,718, WCB_2 12,947 (median TVD).
- *Planned surveys are not the driver.* 12–23 % of NM Wolfcamp producers carry them, not the 46 % NM-wide figure.
- *Tag screen* (`box.tag_screen` rules A/B, consensus v2.2). Of 3,512 NM WCA_1/WCA_2 producers, it moves 21 toward
  WCB/WCC/WCD. Many more of its flags point *up*, to WCXY / BS3_S.
- *Geologist grids.*
  - 82 % of Lea WCA_1/WCA_2 producers sit inside his XY→B1 interval, which is the WCA bench under rule A
    (1,421 of 1,726). In Eddy it is 89 %.
  - 441 NM WCA producers sit at or below his B1 top. That is an upper bound on mis-tags, because his B1 is
    46 % uncontrolled: 90 of the 284 *WCB_1*-tagged Lea producers also sit above it.
- *Sensitivity.* The stick count was recomputed with suspect producers removed from the 3-mi WCA median (midpoint
  geometry: the live count is 1,297, recomputed 1,112):

  | Producers removed | Lea | Eddy |
  |---|---|---|
  | none (recomputed) | 1,112 | 224 |
  | the 63 tag-screen WCA→deeper flags | 1,112 | 223 |
  | the rule-V class, all 89 wells (below) | 1,055 | 181 |
  | every grid-deep NM WCA producer (upper bound) | 794 | 82 |

  Even the upper bound leaves 71 % of the Lea anomaly in place. Eddy is more producer-sensitive (§4).

**H2: dip biases the 3-mi median. Explains Pecos, Ward and Reeves, and part of Lea.**

- With the plane, Pecos goes from −244 to +32 ft and Ward from −422 to +24 ft. Dip there is 148–199 ft/mi.
- Those sticks still sit *at* the WCA plane rather than about 250 ft below it. This is not resolved further:
  - Pecos has no Wolfcamp grid control (tops-QC `no_control`).
  - Ward's operator names are inverted against the grid (tops-QC 2026-10-22).
- Small counts: 274 + 115 sticks, and 8 of them in BOX record coverage.

**H3: Novi's NM `Wolfcamp B` sticks sit shallow. Holds in Lea and Eddy.** The grids are independent of both
vendors and of the producer tags. Grid interval at each anomalous stick's midpoint (stick TVD vs his surfaces):

| County | above 3BSPGS | 3BSPGS→XY | XY→A | A→B1 | **B1 or deeper** | no grid |
|---|---|---|---|---|---|---|
| Lea | 278 | 457 | 165 | 171 | **146** | 80 |
| Eddy | 17 | 96 | 55 | 65 | **98** | 0 |

- Lea anomalous sticks: median 58 ft *above* his XY top and 260 ft above his B1 top.
- Normal Lea WCB sticks: 430 ft below XY and 54 ft below B1.
- Collisions: 517 of the 1,628 Lea + Eddy anomalous sticks have another Novi stick of a *different* formation
  within 330 ft horizontally and 100 ft TVD. That is 32 %, against 10 % of normal sticks. The twins are
  3rd Bone Spring 214, WCXY 135, Wolfcamp A 83.
- Our data cannot tell whether Novi mislabelled a shallower location or carries a TVD that is 300–600 ft too
  shallow. Either way, the stick is not a Wolfcamp B location at the depth stated.

`wca_delta_ft` is therefore doing its job: it is catching bad sticks, not reporting bad producers.

## 3. What it touches

- **BOX record (run 19, Delaware, held per D144):**
  - Of the 2,120 Delaware anomalous WCB sticks, 53 are covered (39 in Lea): 43 above B1 by the grid, 10 in or
    below it.
  - Most of the rest are `not_covered_outside_extent` (1,313) or not in the run (688; RES were outside run 19).
  - Small exposure, but those 53 carry a WCB forecast at what is probably a WCA-or-shallower landing.
- **sql/19 / sub-bench v2 (PR #222, untouched here):**
  - The Lea anomalous sticks are tagged WCB_1 675 / WCB_2 622.
  - A two-bench WCB model will assign a WCA-depth stick to WCB_1. It cannot see that the stick sits above both
    WCB benches.
  - This is a stick-side flag question for #222's gate, not a producer override.
- **Inventory (rule 11):** the 32 % that collide with another Novi bench's stick are probably duplicate
  locations.

## 4. The one producer class worth fixing: rule V

**Why the screen misses it.** sql/16 treats Novi `WOLFCAMP B` as coarse, so these wells take Enverus'
interval. `tag_screen.other_vendor` then counts Novi as no vote. So NM wells that Novi calls Wolfcamp B but
Enverus calls Wolfcamp A are invisible to the screen.

**The class.** 89 NM producing horizontals, all tagged from Enverus: 60 WCA_2, 28 WCA_1, 1 WCXY. 8 of them
reached WCA through the sql/23 TVD correction from an Enverus Bone Spring label.

**Rule V** (fixed before any card was drawn):

1. Take the well's TVD minus the median of ≥ 3 clean WCA_1/WCA_2 witnesses within 1.5 mi. Class wells are
   excluded from the witnesses.
2. Place it on the nearest rung of the NM ladder: WCA 0 / WCB_1 +291 / WCB_2 +564 / WCC +814 ft.
3. The rungs are medians of consensus-agree NM wells (TX: +262 / +505 / +796).

Result:

- 17 have no depth evidence.
- 20 land on the WCA rung: depth backs Enverus, tag stays.
- **52 are flagged.** The grid independently puts 48 of the 52 at or below his B1 top.

| Class | Flagged | Cohort | Median ft below local WCA | Grid B1 or deeper | In a Delaware BOX record oil pool |
|---|---|---|---|---|---|
| WCA_2→WCB_1 | 20 | 9 | 238 | 16 | 8 |
| WCA_1→WCB_2 | 10 | 6 | 542 | 10 | 6 |
| WCA_1→WCC | 9 | 4 | 774 | 9 | 4 |
| WCA_2→WCB_2 | 7 | 3 | 496 | 7 | 2 |
| WCA_2→WCC | 5 | 4 | 719 | 5 | 4 |
| WCXY→WCB_2 | 1 | 0 | 499 | 1 | 0 |

Caveats for the cards:

- 27 of the 52 have planned surveys (rule 15). Their TVD is the pre-drill plan.
- tops-QC found that Lea does not separate WCB_2 from WCC against his B2 top, so the WCB_2 vs WCC destination
  rests on the ladder alone.
- Out of scope, listed only: TX has 245 wells of the same Novi-B / Enverus-A kind, at a median 142 ft below
  local WCA, which is the WCA_2 | WCB_1 boundary.

## 5. For Michael (the gate)

- **Cards:** `cards.html`, 26 cards (round 1 = 5 per class, the 1-well class in full). These are strike sections
  orthogonal to the lateral, showing the well's own tag, the proposed bench and the adjacent bands; the legend
  sits above the plot. Each card states the grid interval and the ladder read.
  - Mark `accept` / `reject` in `cards_sample.csv`. A bench code means your own call on that well.
  - The gate is the tag screen's: 5/5 accepts the class, 0–1/5 rejects it, otherwise 5 more and 7/10.
- **Proposed seed:** `proposed_override_seed.csv`, 52 rows (api10, corrected_code, was, note). It sits outside
  `seeds/`, every row is marked NOT ratified / NOT applied, and it is re-derived from your verdicts by
  convention (a).
- **Apply is a separate go:**
  - 24 of the 52 wells are in Delaware BOX record oil pools, so an apply changes the next Delaware build's pools.
  - The Delaware record stays held on run 19 until the Midland record is priced (D144).
- **Stick side** (the actual anomaly), proposed and not done here:
  1. Raise with Novi: NM Wolfcamp B sticks landed at or above their own Wolfcamp A sticks. `sticks_anomalous.csv`
     is the list, with pads and grid intervals.
  2. Decide at #222's gate whether "stick above the local WCA producers and above the grid's B1" becomes a
     stick-side flag. That flag would be a sibling of the frontier / low-confidence flags already decided there.

## Files

| File | What |
|---|---|
| `build.py` | the whole analysis, read-only (`SET TRANSACTION READ ONLY`) |
| `summary.json` | headline counts |
| `sticks_by_county.csv`, `sticks_anomalous*.csv` | stick-side reads per county / per stick, grid intervals, BOX coverage |
| `producers_nm_grid_interval.csv` | NM Wolfcamp producers by tag × grid interval |
| `sensitivity_wca_median.csv` | the H1 sensitivity table |
| `rule_v_class.csv`, `classes.csv` | the 89-well class and the 52 flags by class |
| `cards.html`, `cards_sample.csv` | review cards + verdict file |
| `proposed_override_seed.csv` | proposed override rows, not ratified, not applied |
