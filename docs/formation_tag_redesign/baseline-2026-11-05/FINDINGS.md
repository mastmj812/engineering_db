# formation_blueox scoreboard — baseline 2026-11-05 (step 0)

This is a read-only score of today's tags. Nothing was written to Supabase.

**Rebuild:**

```
python -m scripts.tag_scoreboard --out docs/formation_tag_redesign/baseline-<date> --cache <dir>
```

Code: `box/tag_scoreboard.py`, with tests in `tests/test_tag_scoreboard.py`. `summary.json` carries the git sha
and the parameters.

## What was scored

- **Grain:** producing horizontals in the Delaware and Midland basins, 60,686 pulled.
  - **Clean evidence:** 56,744 wells (Delaware 28,303, Midland 28,441).
  - **Excluded:** 3,942 wells: 2,664 planned surveys, plus round-100 `tvd_ft` values where there is no survey, no
    depth, or depths under 4,000 ft.
- **Depth:** the lateral median survey TVD (sql/64) for 23,239 Delaware wells and 26,445 Midland wells. The others
  use `tvd_ft`. Every `*_tvd_ft*` file is the same score on `tvd_ft` alone, the 2026-11-05 audit's basis.
- **Candidates (three today):**

  | Candidate | What it is |
  |---|---|
  | `live` | `wells_enriched.formation_blueox` (overrides + sql/23): what downstream reads |
  | `pre_sql23` | overrides, without the sql/23 correction |
  | `vendor` | the crosswalk on the vendor string only |

- **Measures (PLAN §2), independent evidence first:**
  - (a) agreement with the geologist's grids (Delaware);
  - (b) reproduction of the labelled set: 217 carded calls, 232 class-accepted, 3 holds;
  - (c) self-consistency at 1 mi (band test, close-pair inversions within 0.25 mi, band separation).

**Check against the audit (`tvd_ft` basis, live):**

| | Audit | This baseline |
|---|---|---|
| Band disagreement, Delaware | 10.7 % | 10.71 % |
| Band disagreement, Midland | 5.5 % | 5.52 % |
| Close-pair inversions, 2+ benches apart, Delaware | 0.8 % | 0.78 % |
| Close-pair inversions, 2+ benches apart, Midland | 0.1 % | 0.09 % |

The audit is reproduced.

## Headline (depth = survey where available)

| | vendor | pre_sql23 | live |
|---|---|---|---|
| Band disagreement, Delaware, 1 mi | 10.0 % | 9.9 % | **9.8 %** |
| Band disagreement, Midland, 1 mi | 5.9 % | 5.5 % | **5.5 %** |
| Band disagreement, Delaware / Midland, 0.5 mi | 6.4 / 4.0 % | 6.4 / 3.7 % | **6.3 / 3.7 %** |
| Close pairs 2+ benches apart inverted, Delaware | 1.03 % | 1.02 % | **0.78 %** |
| Close pairs 2+ benches apart inverted, Midland | 0.18 % | 0.17 % | **0.09 %** |
| Adjacent pairs inverted, Delaware / Midland | 3.9 / 1.0 % | 3.9 / 0.9 % | **3.7 / 0.9 %** |
| Grid agreement, Delaware, all scored (25.6k wells) | 85.2 % | 85.1 % | **85.2 %** |
| Grid agreement inside control (13.8k wells) | 88.0 % | 87.9 % | **87.9 %** |
| Labelled, carded: Delaware / Midland | 1/108 / 12/103 | 93/108 / 103/103 | **93/108 / 103/103** |

### What it says

1. **The fixes remove gross errors and barely move the population.**
   - The 434 overrides and the sql/23 correction cut gross inversions (2+ benches apart) by about 25 % in Delaware
     and about 50 % in Midland.
   - They move band disagreement by 0.2 points in Delaware and 0.4 in Midland.
   - They move grid agreement by nothing.
   - This is the whack-a-mole in numbers.
2. **Survey depth helps by itself.** Delaware band disagreement is 10.7 % on `tvd_ft` and 9.8 % on survey depth,
   with no tag change. That supports PLAN principle 4.
3. **Source still splits it.**
   - Delaware: Enverus-sourced tags disagree 13.1 %, Novi 4.5 %.
   - Midland: Enverus 6.5 %, Novi 3.6 %.
4. **The thin splits are where the problem is** (band separation, local median gap per neighbourhood):

   | Pair | Median gap | Inverted | Under 50 ft |
   |---|---|---|---|
   | Delaware WCXY / WCA_1 | 104 ft | 11.3 % | 23.7 % |
   | Delaware WCA_1 / WCA_2 | 128 ft | 8.7 % | 20.2 % |
   | Delaware WCB_2 / WCC | 190 ft | 9.8 % | 14.1 % |
   | Delaware BS3_S / WCXY | 172 ft | 6.0 % | 10.6 % |
   | Midland WCB_1 / WCB_2 | 169 ft | 5.2 % | 15.3 % |
   | Midland WCB_2 / WCC | 172 ft | 9.7 % | 19.4 % |

   For comparison:
   - Thick Delaware pairs invert at or below 2.5 %: BS2_C/BS2_S 446 ft, BS3_C/BS3_S 573 ft.
   - Midland's upper column inverts at or below 1.6 %: MS/JM 336 ft, JM/LSSH 355 ft, WCA_1/WCB_1 252 ft.
5. **Grid agreement by bench** (live; the grids are also judged here, not only the tags):
   - **High:** WCA_1 96.5 %, WCXY 93.9 %, BS2_S 93.5 %, AVA_0/AVA_2 about 93 %, WCC 89.8 %, WCA_2 87.0 %.
     WCA_2's misses are 12.4 % deep, below B1: the WCA_2 / WCB_1 boundary.
   - **Low, mostly at boundaries the geologist hasn't settled:**
     - **WCB_2 53.4 %**, with 46 % shallow. This is the known B2 straddle: operator WCB_2 landings sit at about
       +15 ft around his B2 top (tops-QC 2026-10-22, open).
     - **WCB_1 67.2 %**, 26 % shallow.
     - **BS3_S 66.8 %**, 26 % deep, below his XY top. That is rule B, still pending for Lea and Ward.
     - **Pecos 51 %**: no Wolfcamp control.

   So grid disagreement at WCB_2 and BS3_S is partly about where the geologist's surfaces sit, not the tag.
6. **The labelled set behaves.**
   - The only carded calls `live` misses are the 15 unapplied #230 rule-V calls (93/108 in Delaware).
   - The vendor reproduces almost none, as expected: these are wells the vendor got wrong.
   - **19 overrides are now redundant:** the vendor has since retagged those wells to the override's code (1 Delaware,
     12 Midland carded, 6 Midland class-accepted). That's harmless, because the override still wins.
7. **Overridden wells fail the band test at the background rate:** 11.4 % in Delaware, 9.5 % in Midland. Their
   neighbours carry the same noise. This is why (c) never decides on its own.
8. **Correction to the audit's vintage claim.** The audit reported Delaware close-pair inversions rising from 4.2 %
   (2014 and earlier) to 10.1 % (2024+). With pairs as the unit and survey depth:
   - adjacent-pair inversions are flat at 3.6–3.9 % from 2018;
   - band disagreement is 5.4 % for 2014 and earlier, and 9–11 % from 2015 onward.

   **It's a step at about 2015, not a rising trend.** Older wells also have fewer testable neighbours: 2,498 of 3,739
   are testable.

## For Michael (gate before step 1)

1. **Is this the scoreboard you'd judge the tag by?** Grid agreement leads, then the labelled set, then the band and
   inversion measures, all on survey depth. The current numbers are the "before".
2. **Grid boundaries still in question.** Two boundaries are where the geologist's own surfaces are open: WCB_2 at
   his B2 top, and BS3_S/WCXY at his XY top in Lea and Ward. My recommendation:
   - the step-1 criterion requires grid agreement not to get worse there;
   - it does not require it to rise there;
   - it requires a rise everywhere else.

   Otherwise a rule could "win" by fitting a surface he hasn't settled.
3. **Hygiene, listed and not done:**
   - 19 redundant overrides (keep them; they're harmless);
   - 4 stale live rows (reloaded at the step-4 apply, per Q4);
   - `curated.well_neighbors` (sql/59) never applied;
   - sql/30 `wca_delta_ft` still counts planned producers.

## Files

| Pattern | What |
|---|---|
| `summary.json` | headline numbers, params, git sha |
| `labelled_set.csv` | the human calls scored against (api10, label, tier, source) |
| `<basis>_<candidate>_band_by_{basin,bench,source,vintage,county}.csv` | band test (basis `best` = survey depth; `tvd_ft` = the audit basis) |
| `<basis>_<candidate>_inversions*.csv` | close-pair inversions (0.25 mi, > 50 ft) |
| `<basis>_<candidate>_band_separation.csv` | local gap between adjacent bench bands |
| `<basis>_<candidate>_labels.csv` | labelled-set reproduction by tier |
| `<basis>_<candidate>_disagree_wells.csv` | every band-test disagreement, well by well |
| `best_<candidate>_grid_*.csv` | grid agreement (Delaware) by bench / county / overall, plus the verdict counts |
