# BOX step 20b: Midland Spraberry bench QC + extents. AT GATE 20b (nothing stored)

**Scope (plan §5 step 20b, D127 / D128 / D131 / D134 A–B / D140 / D141 / D117):** Midland MS, JM, LSSH, DEAN: one bench QC and
one D27 extent each, no pooling (D128). US is D2 emerging (D127): no QC set, no extent; it gets an `in_scope = false` scope
row on your go. The method is 20a's, transferred unchanged (D134): the Delaware class rule as written (`box/qc_rule`),
consensus detector v2.2 (D138), the sql/23 second vote and GOR veto, the allocation-well screen, and the Delaware D23 r / c
and D27 constants (`box/basin.py`). Read-only: no `box.bench_scope` row and no `box.extent` record is written.

**Built:** branch `claude/box-step20b-spraberry`, off main 4905ec8. Producing horizontals pulled 2026-10-30 after that day's
nightly (Midland as-of last reported month 2026-09-01; tags carry the 438 live overrides). Delaware analogue pulled the same
day.

Pages (serve `python -m http.server 8766 --directory docs/box`, open `step20b-2026-10-30/`):
- `index.html`: family page (well sets, flag ledger, sensitivity, D128 context, §4b analogue test, allocation screen)
- `qc_<bench>.html`: per-bench QC pages
- `cards/cards.html`: the 40 cards you judged (§1c; verdicts in `cards/cards_sample.csv`, back 2026-10-31, §1d)
- `cards/cards_strike.html`: **the same 40 cards in the new strike-section layout** (2026-10-31, §1d), for comparison
- `extents/index.html`, `extents/extent_<bench>.html`: interactive maps
- `extents/midland_spraberry_extents_2026-10-30.pptx`: **the visual-check maps for your pen loops**, one slide per bench
- `extents/geology/`: NAD83 UTM 14N US-ft shapefiles. Context only (D28); no Midland structure grids exist.
- `undrilled_split.csv`: undrilled Novi sticks inside vs outside each extent, basin-wide (§2)

## 1. Bench QC (Delaware class rule as written)

| Bench | Tagged live = final set | First production ≥ 2016 | D9 cohort | Moved by the rule | sql/23 disagrees | Consensus flag rate | Vendors disagree (Novi vs Enverus) |
|---|---:|---:|---:|---|---:|---:|---:|
| MS | 1,675 | 1,615 | 1,180 | none | 2.0 % | 0.6 % | 6.9 % |
| JM | 1,630 | 1,612 | 1,073 | none | 4.8 % | 1.9 % | 4.2 % |
| LSSH | 5,759 | 5,498 | 4,266 | none | 4.1 % | 3.0 % | 5.4 % |
| DEAN | 928 | 908 | 510 | none | **8.4 %** | **6.8 %** | **25.9 %** |

- **As built 10-30 (superseded by §1d once your verdicts came back):** the rule moves nothing. Every flag touching the family (336) sits in a class the ledger has never calibrated, so every
  tag is kept (D134 B as written; D141). The final sets are the live tags.
- No exclusion applies. Planned surveys are 0.0–0.2 %, permit-round TVDs 0.9–1.4 %, and no well is `tvd_suspect`.
- No api10 sits in two Spraberry sets, and **none sits in a stored 20a r3 Wolfcamp set** (checked against
  `step20a-2026-10-26/r3/wells_final_*.csv`). The families do not double-count.
- Your 20a owner benches and every prior card verdict were passed in (`--verdicts` step 1 / 20a / ask 3, `--owner-benches`);
  none of them is a Spraberry well, so they change nothing here.

**Your expectation vs the data: MS / JM are the CLEANEST benches by depth; DEAN is the noisiest.** DEAN tops all three
measures. The vendors disagree on 240 of its 927 tags; Novi says DEAN and Enverus says LSSH or WCA, or the other way round.
One caveat on MS / JM: the depth detector is blind where a whole neighbourhood shares one wrong label, and MS ↔ JM
naming is exactly that kind of risk, since operators name these landings differently. The 10-26 tag screen (before the
overrides) saw it as vendor disagreement: MS → JM (B) 21, US → MS (B) 14, JM → MS (A) 13. The level stakes are real:
JM produces 1.33× MS per foot in the same block (below), so a mislabeled well moves a curve. If you want an MS / JM check
beyond the detector, that is the tag screen run on the Spraberry, warehouse-first (§4, item 4).

**Do the flags move the evidence?** Applying every consensus flag moves each bench's cohort median 12-mo oil per 1,000 ft
by ≤ 0.6 % (MS +0.1 %, JM +0.3 %, LSSH −0.1 %, DEAN −0.6 %). What cards can move is membership and edges, not bench levels.

**D128 context** (D9 cohort, 5-mi block + first-production-year fixed effects, second bench / first, 90 % block-bootstrap CI):

| Pair | Oil per 1,000 ft | GOR | Shape (cum-24 / cum-12) | Local depth separation, median (merged < 100 ft) |
|---|---|---|---|---|
| JM / MS | **1.332** [1.250–1.411] | 1.121 [1.078–1.167] | 0.957 [0.939–0.976] | 331 ft (0.6 %) |
| LSSH / JM | 0.945 [0.907–0.995] | 0.943 [0.912–0.979] | 0.962 [0.950–0.973] | 356 ft (0.5 %) |
| DEAN / LSSH | **1.263** [1.159–1.376] | 1.051 [0.993–1.112] | 0.952 [0.935–0.972] | 247 ft (3.0 %) |

Every pair separates on depth, and on oil or shape with CIs clear of 1. D128 (no pooling) stands; nothing here looks like
the Delaware WCA_1 / WCA_2 (~128 ft, 36 % merged). Co-location: 76 % of MS and JM cohort wells have a cohort well of the
other bench within 1.5 mi (co-developed); 84 % of DEAN wells have an LSSH well that close, but only 36 % of LSSH wells
have a DEAN well (DEAN is developed inside part of the LSSH footprint).

### 1b. Swap classes vs their Delaware analogue (D134 B, D141) → `swap_classes_vs_delaware.csv`

As §8.21 of 20a predicted: **no Spraberry class has a Delaware analogue**, so the test as written cards nothing. Of 16
classes, 6 have ≥ 20 flags ("no analogue") and 10 are "small" (< 20, 1–9 flags each). (On the 10-27 snapshot it was 7
classes; LSSH → WCA fell from 20 to 3 flags after the overrides moved those wells.)

| Class | Flags (per 1,000 tagged) | D9 cohort | sql/23 concurs | GOR votes own / suggested | Own band absent in 1.5 mi | Top operator | Already judged (20a cards / tag screen / calls / seed) |
|---|---:|---:|---:|---|---:|---|---:|
| **LSSH → JM** | 132 (22.9) | 77 | 65 % | 10 % / 5 % | 44 % | **Exxon 103 of 132** | 0 |
| WCA → DEAN | 54 (7.0) | 36 | 52 % | 2 % / 2 % | 80 % | Occidental 13 | 5 |
| DEAN → WCA | 38 (41.0) | 17 | 74 % | 3 % / 3 % | 87 % | Diamondback 9 | 4 |
| LSSH → DEAN | 35 (6.1) | 26 | 29 % | 17 % / 9 % | 83 % | Ovintiv 8 | 0 |
| DEAN → LSSH | 25 (26.9) | 12 | 68 % | 0 % / 0 % | 92 % | Ovintiv 9 | 0 |
| JM → MS | 21 (12.9) | 13 | 62 % | 0 % / 5 % | 62 % | FireBird 8 | 0 |

The small classes (JM → LSSH 9, MS → JM 8, WCA → LSSH 3, LSSH → WCA 3, WCB_2 → JM 2, OTHER → DEAN 2, US → MS 1, JM → WCA 1,
MS → LSSH 1, MS → WCB_1 1) keep their tags under any choice, as in 20a.

Three things the table says:
- **LSSH → JM is an operator class.** 78 % of its flags are Exxon wells that Novi calls LOWER SPRABERRY SHALE, sitting at
  their neighbours' JM depth. Exxon holds 20 % of LSSH wells overall. Two facts bear on it. The crosswalk maps Novi's
  "LOWER SPRABERRY SAND" to JM, and 223 LSSH-tagged wells carry Enverus "JO MILL". So the class is probably a naming call:
  is Exxon's "Lower Spraberry" landing the sand (= JM for BOX) or the shale? It is the same shape as the open Discovery
  LS/SH operator × area call from 20a, and 10 cards (9 of them Exxon) are a good way to make it.
- **Most of these flags have no own-tag band nearby** (44–92 %). The well is the only one of its tag in 1.5 mi, and it sits in
  the other bench's band. The class is still a depth call, but a lone well rather than a disagreement inside a coherent
  band.
- **The two Wolfcamp crossings (WCA → DEAN, DEAN → WCA) are already decided once.** D140 keeps DEAN / LSSH → WCA
  "uncalibrated, tag kept". The tag screen carded the same boundary in 20a and you rejected it: DEAN → WCA_1 (A) 6 / 10,
  DEAN → WCA_1 (B) 1 / 5, WCA_1 → DEAN (A) 4 / 9. And accepting WCA → DEAN would move wells out of the stored WCA_1 record
  (extent 36) membership.

### 1c. Cards drawn for the gate choice → `cards/cards.html`, verdicts in `cards/cards_sample.csv`

The cards are drawn so that option (a) costs no extra round. Nothing reads them until you fill them.
- **40 cards: 10 each for the four Spraberry-internal classes** (LSSH → JM, LSSH → DEAN, DEAN → LSSH, JM → MS).
- Same sampler as 20a: evenly spaced margin quantiles. 25 are D9 cohort.
- Wells you already judged are left out first (the ask-3 pattern): every api10 in the 20a cards, ask-3 cards, tag-screen
  cards, `well_calls.csv`, `owner_benches.csv` and the override seed. None of the internal classes held one.
- **The Wolfcamp crossings are not drawn** (see above). If you want them, it is a one-minute draw that leaves out the
  9 wells already judged.
- Verdict column: agree / reject / a bench code / hold, as before. The Midland class ledger then decides each class at
  ≥ 0.70 (`qc_rule.BASIN_CLASSES`).

### 1d. Card verdicts back (2026-10-31) → the sets and extents regenerated

Your verdicts, judged on the Midland ledger at ≥ 0.70 (`qc_rule.BASIN_CLASSES["midland"]`; this is the D134 B amendment for
no-analogue classes from §4 item 1):

| Class | Accept / 10 | Class | Wells moved | of which by your card | by the class rule (sql/23 concurs, GOR not "own") |
|---|---:|---|---:|---:|---:|
| LSSH → JM | 8 | **accepted (0.80)** | 78 | 8 | 70 |
| JM → MS | 6 | rejected (0.60) | 6 | 6 | 0 |
| LSSH → DEAN | 4 | rejected (0.40) | 4 | 4 | 0 |
| DEAN → LSSH | 3 | rejected (0.30) | 3 | 3 | 0 |

In a rejected class, only the wells you accepted on a card move; every other flag in the class keeps its tag. In
LSSH → JM, 54 of the 132 flags stay LSSH: your 2 rejects plus the flags where sql/23 doesn't concur or the GOR votes for
LSSH.

| Bench | Final set (was) | D9 cohort (was) | Extent, sq mi (was) | ≥ 2016 laterals inside | Undrilled inside / basin (was) |
|---|---:|---:|---:|---|---|
| MS | 1,681 (1,675) | 1,184 (1,180) | 2,389 (2,389) | 1,579 of 1,621 (97 %) | 3,418 / 8,553 (unchanged) |
| JM | 1,702 (1,630) | 1,111 (1,073) | 2,772 (2,769): +2.9 / −0.2 | 1,658 of 1,682 (99 %) | 4,161 / 8,029 (4,154) |
| LSSH | 5,680 (5,759) | 4,223 (4,266) | 4,055 (4,055): +0.2 / −0.3 | 5,388 of 5,421 (99 %) | 6,378 / 11,703 (unchanged) |
| DEAN | 929 (928) | 511 (510) | 1,151 (1,151): +2.7 / −3.1 | **623 of 909 (69 %), still 2 bodies** | 286 / 1,882 (287) |

- **The verdicts don't move any edge you'd draw.** The rendered frames are byte-identical to the deck's, so loops drawn on
  the 10-30 deck georeference unchanged. The deck file itself was not regenerated (you have it open).
- The bench levels barely move: JM / MS oil per 1,000 ft 1.338 (was 1.332), LSSH / JM 0.941 (0.945), DEAN / LSSH 1.264
  (1.263).
- Uncalibrated flags fall from 336 to 123. Those left are the Wolfcamp crossings and the small classes, all tag-kept.
- One intermediate changed: DEAN's dense core went from 533 to 32 sq mi. Adding one well and dropping another broke a
  link inside the core. The extent didn't move (1,151 sq mi) and DEAN needs your loop either way.
- **A loader bug, fixed:** your verdict column says `accept`, and `qc_rule.load_verdicts` only read `AGREE`. The first
  re-run silently ignored your accepts, which showed up as 2 accepted LSSH → JM wells staying LSSH. `ACCEPT` now reads as
  AGREE (a test pins it), and the numbers above are from the corrected run.

**The card layout you asked for** (`box/flag_cards.py`; the 40 cards re-rendered in `cards/cards_strike.html`):
- **Strike section, not a radius.** The cross-section shows wells whose lateral crosses a line through the subject's
  midpoint, orthogonal to its lateral, out to ±1.5 mi. It reads per sign rule v2: W → E for N-S laterals, S → N for E-W.
  The plan inset draws the lateral and the strike line.
- **Depth axis held to the benches in play:** the subject's tag, the proposed bench, and the local bands directly above and
  below. Everything else is hidden and the count noted, so no BRNT under a DEAN card.
- **The legend sits above the plot,** never over the landings.
- The dashed band medians are still the detector's 1.5-mi radius bands, because that's what the flag was scored on. The
  detector itself is unchanged (D138). Scoring on a strike instead of a radius would be a method change, and that's your
  call.
- The pull (`bench_qc._SQL`) now carries the lateral endpoints. Without them, a card falls back to the radius view and
  says so.

## 2. Extents (D27 one-body envelopes; Delaware r / c and D27 constants per D134 A) → `extents/`

Built on the §1 final sets (the rule as written). Undrilled = D117 (Novi PUD + RES; remaining_pud / conflict / not yet
reconciled), inside = ≥ 50 % of the stick in the extent. Basin totals are from `undrilled_split.csv`.

| Bench | Extent, sq mi | ≥ 2016 laterals inside | Bodies ≥ 50 laterals | Live fronts | Undrilled inside / basin (share) | of which PUD inside / basin | RES inside / basin |
|---|---:|---:|---:|---|---|---|---|
| MS | 2,389 | 1,573 of 1,615 (97 %) | 1 | SW | 3,418 / 8,553 (40 %) | 3,418 / 5,700 | 0 / 2,853 |
| JM | 2,769 | 1,587 of 1,612 (98 %) | 1 | none | 4,154 / 8,029 (52 %) | 4,149 / 5,802 | 5 / 2,227 |
| LSSH | 4,055 (two parts) | 5,465 of 5,498 (99 %) | 1 | NE | 6,378 / 11,703 (54 %) | 6,295 / 8,099 | 83 / 3,604 |
| DEAN | 1,151 | **624 of 908 (69 %)** | **2** | NE, S, W | **287 / 1,882 (15 %)** | 270 / 1,789 | 17 / 93 |
| US | none (D2 / D127) | — | — | — | 0 / 3,756: all `not_covered_emerging`, never zero | 0 / 991 | 0 / 2,765 |

The basin totals reproduce the plan's gate-18 table: JM 8,029 and DEAN 1,882 exactly; MS 8,553 vs 8,562, LSSH 11,703 vs
11,707 and US 3,756 vs 3,751, which is live drift since 10-26. Every in-extent count equals the extent build's own count.

- **MS, JM, LSSH: the Delaware metric holds.** Each is one body with 97–99 % of its modern laterals inside, so D134 A stands.
  - **MS, south (your loop call):** 26 of the 42 outside laterals are in Upton. Most are **Summit Petroleum's MS program
    (VERA 13 / 9 / 5 / 2, LILIAN 38 / 56) at 7.8–8.3 mi S** of the body, producing 11,500–23,200 bbl / 1,000 ft (bench cohort
    median 13,030). D27 counts them as tests: 2-well step-outs inside 8 mi, single wells just past it. They are development
    by any eye; a loop there takes them in.
  - **LSSH second part:** a 4.5-sq-mi island at 31.22° N (a ≥ 3-lateral development cluster inside 8 mi, kept as its own
    part). One loop around the main body drops it; no loop keeps it.
  - **JM:** nothing visible. 25 outside, scattered (Upton 8, Borden 6).
- **DEAN fails the one-body construction visibly,** the WCB_2 / WCC / WCD pattern from 20a.
  - The D27 body is the Martin / Howard development (590 laterals). Body 2 (50 laterals, SW) is out, and so are 284 ≥ 2016
    DEAN laterals scattered S / SW / W (Midland 81, Martin 76, Upton 45, Andrews 24).
  - **The outside DEAN is where the tags are weakest.** Outside the body: vendors disagree on 39 % of modern wells (18 %
    inside), the consensus flag rate is 13 % (3 % inside), median TVD 9,180 ft vs 8,230, and oil 14,160 vs 17,180 bbl /
    1,000 ft. The disagreement is almost all DEAN ↔ WCA_1 (80 of 110) and DEAN ↔ LSSH (27). That is the 20a WCC situation:
    an extent drawn only where the tag is trusted.
  - Per the step-15 convention, **your red closed loops are the extent** (slide 4). The black outline is the generated
    body; a slide left untouched accepts it.
- **Rule 11 shows up as expected:** Novi's UPSIDE (RES) sticks fall almost wholly outside every developed envelope (MS 0 of
  2,853, JM 5 of 2,227, LSSH 83 of 3,604). D117 lets BOX's own extent do that screening.
- **Owner-loop deck:** `extents/midland_spraberry_extents_2026-10-30.pptx` (slides 1 MS, 2 JM, 3 LSSH, 4 DEAN; manifest
  beside it). Checked: the untouched deck reads back through `box_family_extent_edits` as "no marks" on all four benches,
  generated = edited to 0.0 sq mi.

## 3. Allocation-well screen (plan Phase 3, difference 6) → `alloc_twin_pairs.csv`

**Twin laterals** touching the family: 4 same-bench twins, 4 stacked pairs and 5 re-drills. **None of the 4 twins shows the
El Campeon split** (one side under half the other's oil at the same GOR). All four are same-operator pad neighbours:
- HALL A6 06LB / A11 05LA (JM, ΔTVD 140 ft, LA / LB = two landings);
- BUTCH CASSIDY 132LS / 142LS;
- WARFIELD EAST C 103LS / D 104LS;
- HALL POWELL 3813LH / 3804LH.

The detector's Delaware check is unchanged from 20a (22 of the 46 recorded exclusions in a coinciding pair).

**Production sharing:** 45 % of the family's D9 cohort. Within block + year, sharing wells read **1.130× [1.095–1.168] oil
per 1,000 ft** at 0.98× GOR. The Wolfcamp family read 1.033× and Delaware TX 0.996×. The direction is the opposite of a
split-booking defect, which makes one side read LOW. Sharing wells are the newer pad developments (operator / completion
mix), so this is a level difference to watch, not an exclusion: both kinds stay in the analog pool. **Proposed
exclusions: none.** For 21a, worth one line in the pre-registration: report the sharing / non-sharing split of each
Spraberry cohort.

## 4. Gate 20b: your calls (recommendation first)

1. **ANSWERED 2026-10-31: you carded the four (§1d).** LSSH → JM accepted (0.80); JM → MS, LSSH → DEAN and DEAN → LSSH
   rejected. This stands as the D134 B amendment for no-analogue classes, and the two Wolfcamp crossings stay tag-kept.
   The original recommendation, for the record: recommend **card the four Spraberry-internal classes and keep
   the two Wolfcamp crossings tag-kept.**
   - Internal classes: LSSH → JM 132, LSSH → DEAN 35, DEAN → LSSH 25, JM → MS 21. The 40 cards are drawn
     (`cards/cards.html`); fill `cards/cards_sample.csv`. Each class is then judged on the Midland ledger at ≥ 0.70, and
     each card decides its own well, as at 20a.
   - Crossings (WCA → DEAN 54, DEAN → WCA 38): D140 already says tag kept, your tag-screen cards rejected that boundary,
     and accepting it would reshuffle the stored WCA_1 record's membership.
   - **Conflict to flag:** carding a class with no analogue goes beyond D134 B as written. Under D134 B with D141, the
     default for these classes is "tag kept". Carding them is your call, and it would be a new decision (an amendment to
     D134 B for no-analogue classes), not a reading of the existing one.
   - What it buys: membership, mostly on the LSSH → JM operator question. Bench levels move ≤ 0.6 % even if every flag
     applies (§1).
   - Options:
     - (a) the four internal classes (recommended; drawn);
     - (a+) all six, including the crossings (a one-minute draw, 9 already-judged wells left out);
     - (b) none: every Spraberry tag stays, and the tag screen is the only fix, warehouse-first.
2. **Pen loops** (deck `extents/midland_spraberry_extents_2026-10-30.pptx`):
   - **DEAN: needs a loop** (fails one-body; slide 4). The outside DEAN is the low-trust ground (§2), so this is the WCC
     choice again: trusted body only, or reach SW for body 2 / the S trend. Card exposure: 24 LSSH → DEAN flags lie
     outside the body. If you card that class, draw the DEAN loop after the verdicts (I regenerate first, as at 20a r2).
   - **MS: your call on the Summit Upton program** (slide 1, south tip, 7.8–8.3 mi out, performing). I lean to taking it
     in: it is development, and only the 8-mi count keeps it out.
   - **LSSH: keep or drop the 4.5-sq-mi island** (slide 3; no loop = keep). Otherwise accept as generated.
   - **JM: accept as generated** (slide 2).
   - Card verdicts cannot move the MS, JM or LSSH edges: every LSSH → JM, JM → MS and DEAN → LSSH flag already lies
     inside its target's extent. Those three slides can be drawn now.
3. **Storage, on your go after 1–2** (and the regeneration if cards move anything):
   - four `box.bench_scope` rows (basin `midland`, `in_scope` true, `member_benches` = {bench}, tier provisional until
     step 21 per D131) and four `box.extent` records (generated v1, or generated v1 + your loop as the record);
   - **plus the US row**: `in_scope` false, no extent (D127), reason "emerging bench (D2 / D127)…", decided_on
     2026-10-26.
   - Both paths are dry-run clean (§5).
4. **MS / JM tag check beyond the detector (not decided here; your call).** In 20a, §8 said the Spraberry *tag-screen*
   classes would be carded at 20b. This brief scoped 20b to the BOX class rule, so the tag screen was **not** run on the
   Spraberry; the counts in §1 are from the 10-26 screen. Recommend not now: the depth evidence puts the noise on DEAN,
   not MS / JM, and the DEAN loop handles its extent. Run the Spraberry tag screen later as a warehouse-first item (13e
   pattern) if you want the DEAN ↔ WCA_1 / LSSH and MS ↔ JM labels fixed for erebor / narvi / deal-intake too.
5. **Note for 21a (no decision):** production-sharing wells read 1.13× oil per 1,000 ft within block + year (§3). It is
   not a defect; report the split per Spraberry cohort in 21a.

**Carried from 20a, not worked (none blocks 20b):**
- **Discovery LS/SH operator × area call.** It does not touch the LSSH extent. 43 of Discovery's 49 LSSH wells are inside,
  all Midland / Upton / Martin at ~8,900 ft (the ones 20a judged fine). The 6 questioned Reagan wells are all outside.
- **Next-screen wells.** CROSS BAR RANCH H 1725H is in the DEAN set (tag DEAN, TVD 9,664) and 1717MS in the MS set
  (TVD 9,186); 1724H and Mustang Draw 24NH are in no Spraberry set. Two wells, no extent effect.
- The 4 seed removals still ride the next override batch.

## 5. Verification and how to re-run

- **Identity:**
  - basin undrilled totals = the plan's gate-18 table (JM, DEAN exact; others within live drift);
  - in-extent counts from `undrilled_split.csv` = the extent build's own;
  - store dry run (re-run 2026-10-31 on the regenerated extents, still clean, nothing written): each rebuilt extent = the reviewed one within 0.0005 sq mi of area and 0.0042 sq mi of symmetric
    difference;
  - deck round-trip: generated = edited 0.0 sq mi;
  - no api10 in two Spraberry sets or in a stored 20a Wolfcamp set;
  - US emerging dry run clean.
- **Delaware unchanged:** no Delaware code path was edited. `MID_SPR` is a new family entry, and the store and card
  scripts gain Midland-only branches. The 20a store path keeps its rows and text (test).
- **Tests:**
  - `tests/test_box_step20b.py` (6, new) + `test_box_step20a.py` / `test_box_family_qc.py` / `test_box_basin.py`: 46 passed;
  - full suite: 790 passed, 46 skipped (2026-10-30);
  - ruff clean on every touched file; mypy is not installed in this venv.
- **Nothing written to the warehouse.** Every pull ran in a READ ONLY transaction; both store paths ran `--dry-run`.

```
python -m scripts.box_family_qc --family MID_SPR --out docs/box/step20b-2026-10-30 --step 20b --analogue --cards --alloc \
    --verdicts docs/box/step1-2026-10-06/cards_sample.csv --verdicts docs/box/step20a-2026-10-26/cards_sample.csv \
    --verdicts docs/box/step20a-2026-10-26/ask3/cards_sample.csv --verdicts docs/box/step20b-2026-10-30/cards/cards_sample.csv \
    --owner-benches docs/box/step20a-2026-10-26/owner_benches.csv   # ~3 min
python -m scripts.box_noanalogue_cards --cache <mid_scored.pkl> --cmp docs/box/step20b-2026-10-30/swap_classes_vs_delaware.csv \
    --family MID_SPR --within-family --out docs/box/step20b-2026-10-30/cards --judged <20a cards, ask3, tag_screen cards,
    well_calls, owner_benches, seeds/formation_tag_overrides.csv>
python -m scripts.box_family_extents --wells docs/box/step20b-2026-10-30 --pool MS JM LSSH DEAN --basin midland --step 20b --visual-bodies 50   # ~5 min
python -m scripts.box_undrilled_split --basin midland --out docs/box/step20b-2026-10-30/undrilled_split.csv \
    MS=<ext>/extent_MS_v1.geojson JM=... LSSH=... DEAN=... --no-extent US
PYTHONPATH=<python-pptx install> python -m scripts.box_extent_pptx --out <ext>/midland_spraberry_extents_2026-10-30.pptx --basin Midland MS=<ext> JM=<ext> LSSH=<ext> DEAN=<ext>
# after your loops (read-only):
python -m scripts.box_family_extent_edits --pptx <deck> --slide 1=MS --slide 2=JM --slide 3=LSSH --slide 4=DEAN \
    --wells docs/box/step20b-2026-10-30 --ext docs/box/step20b-2026-10-30/extents --basin midland
# store, ON YOUR GO ONLY (dry runs clean 2026-10-30):
python -m scripts.box_family_extent_store --wells docs/box/step20b-2026-10-30 --pool MS JM LSSH DEAN --basin midland --step 20b --decided-on <go date> [--loop-date <deck date>]
python -m scripts.box_family_extent_store --emerging US --basin midland --step 20b
```
