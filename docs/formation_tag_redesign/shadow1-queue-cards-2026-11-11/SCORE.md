# Shadow run 1 card queue: scored (2026-11-11)

- **Reader:** the Step 3 verdict reader (`scripts.tag_v5_2_score.read_verdict`). Each card decides only its own well.
- **Output:** `cards_scored.csv`.

**Result:** 23 cards agree with the proposal and 2 are bench calls. All 25 become human calls in the overrides seed
(`scripts.tag_rule_seeds`, card set `shadow1-queue-cards-2026-11-11`). They load only through
`apply_formation_tag_rule --seeds`, on an explicit go.

| Card | Well | Input → proposed | Verdict | Final |
|---|---|---|---|---|
| 1 | WOOL HEAD 20 STATE COM #554H (Lea) | BS3_S → BS3_C (Step 2) | BS2_S | **BS2_S**, a call |
| 2 | ST BRIDES 76 3031 111H (Loving) | WCA_1 → WCXY (Step 2) | WCXY | **WCXY** |
| 3 | BONDI 24 FEDERAL COM #122H (Eddy) | BS2_S → WCA_2 (Step 3) | WCA_1 | **WCA_1**, a call |
| 4 | SILVERTIP 76-16 UNIT Q 25H (Loving) | BS2_S → WCA_2 | WCA_2 | **WCA_2** |
| 5 | SHERMAN 6-9 UNIT 1WA (Pecos) | OTHER → WCA_1 | WCA_1 | **WCA_1** |
| 6 | PEELER D 16MA (Martin) | MS → LSSH | ACCEPT | **LSSH** |
| 7 | CHARGER H150 MIPA UNIT H150LS (Midland) | LSSH → MS | ACCEPT | **MS** |
| 8–25 | 18 Apache wells (Glasscock) | OTHER → WCD | ACCEPT | **WCD** |

**About the calls:**
- **Card 1:** the well leaves the Bone Spring 3 unit for BS2_S, where sql/23 already had it and where the strike
  section puts it.
- **Card 3:** the well leaves BS2 and goes to WCA_1, the nearer Wolfcamp A sub-bench by plain median (8,972 ft vs
  WCA_2's 9,259 ft). Novi's WCXY was not taken.

## Card 2 vs the W1 Loving calls

ST BRIDES is in the same Loving Bone Spring / Wolfcamp contact cluster as W1 cards 2–4 (PERMIT 4H, SMALL EYED 15H,
KUDU 6H). Those three were called **BS3_S**; this card was called **WCXY**.
- The README wrongly described card 2 as "the same pattern as W1 cards 2–4" without saying how those were called.
- Neither answer is out of line. The W1 score found the cluster's carded calls split both ways at the same depths.
- ST BRIDES sits at 11,842 ft. That matches the WCXY witnesses (11,848 ft, n = 37) and the depths of the WCXY calls
  there (RATTLER 11,610, PYTHON 11,637, BONGO 11,752, PERMIT 8H 11,798, SAN SABA 11,889). It is deeper than every
  BS3_S call (11,667–11,840).
- Recorded as marked (WCXY).

**Michael's reasoning (2026-11-11), a close call:** he struck a W–E section and inspected the gunbarrel of the 111H
with its BS3_S and WCXY neighbours. The 102H, slightly offset to the east, lands at 11,836 ft tvd_ft; the 111H lands at
11,964 ft. That is two benches of development in close vertical proximity, not two BS3_S landings. The 102H is the
BS3_S bench, and the slightly deeper 111H is more likely WCXY.

The unit was developed in three tiers, and the well numbers follow them:

| Tier | Wells | Survey depth (ft) | tvd_ft (ft) | Tag today |
|---|---|---|---|---|
| 10x | 101H, 102H | 11,707 / 11,695 | 11,782 / 11,836 | BS3_S |
| 11x | **111H**, 112H | 11,842 / 11,835 | 11,964 / 11,905 | BS3_S |
| 12x | 121H, 122H | 12,058 / 12,050 | 12,105 / 12,102 | WCA_1 |

**Open:** the 112H (4230135087) is the 111H's twin in the same tier. It stays BS3_S, because the rule didn't queue it
and so it was never carded.
