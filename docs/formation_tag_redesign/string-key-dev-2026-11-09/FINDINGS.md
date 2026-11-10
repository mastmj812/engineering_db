# Step 1 learned table keyed on vendor STRING pairs — dev run (2026-11-09)

**What changed.** Step 1 (rule "v5") falls back to a learned winner when depth can't decide a unit conflict.

- **Before:** the winner was learned per (basin, Novi unit, Enverus unit).
- **This run:** it is learned per (basin, Novi string, Enverus string). This is `V5.pattern_key = "string"` in
  `box/tag_precedence.py`; the default stays `"unit"`, as frozen.
- **Thresholds are untouched:** ≥ 75 % share, ≥ 20 decided wells (≥ 5 when the units are two or more apart).

**How it was run.**
- Same snapshot as `../xy-rerun-2026-11-09/`, i.e. with the WOLFCAMP A (XY) → WCXY crosswalk row.
- Steps 1 → 2 → 3, unchanged otherwise. Outputs are in `v5/`, `v5_1/` and `v5_2/`. Read-only.

Three runs are compared:

| Run | Keying | XY row |
|---|---|---|
| **reviewed** | unit | no |
| **XY + unit** | unit | yes |
| **XY + string** (this run) | string | yes |

## The learned table

- **19 string pairs learn a winner** (out of 219 conflicting pairs), listed in `v5/precedence_table.csv`.
- The largest are Midland Novi WOLFCAMP B vs Enverus WOLFCAMP A (240 decided wells, Novi 0.78) and Delaware Novi SECOND
  BONE SPRING vs Enverus 3RD BONE SPRING (112, Novi 0.94).
- **No winner flips.** Every reviewed pattern decision that still has a winner points to the same vendor.

| Basis (Step 1) | reviewed | XY + unit | XY + string |
|---|---|---|---|
| pattern | 949 | 921 | 901 |
| depth | 1,579 | 1,668 | 1,668 |
| unresolved | 2,830 | 2,950 | 2,970 |

**Of the reviewed run's 949 pattern decisions, under string keying:**
- **767 keep their winner.** All 299 Midland WCB vs WCA_1 and all 77 LSSH vs JM wells, among others.
- **178 become unresolved,** because their string pair has too few decided wells. The largest are Delaware BS1 vs BS2
  (75) and Midland WCC vs WCB (39). Only **4** of the 178 were applied tags (below); the rest were in classes never
  applied.
- **4** now get a per-well depth call instead.

**134 new pattern decisions,** where the pooled unit pair had no winner but the string pair does:
- Delaware Novi THIRD BONE SPRING LIME vs Enverus 2ND BONE SPRING SAND: 100 wells, Enverus 0.77.
- Delaware Novi SECOND BONE SPRING LIME vs Enverus 1ST BONE SPRING: 34 wells, Enverus 0.96.

Both point the same way as depth classes you already accepted: BS3_C → BS2_S by depth (79 wells, 5/5) and BS2_C →
BS1_S by depth (22 wells, 7/10).

## Accepted tags (what would actually be applied)

| Comparison | Accepted tags that differ |
|---|---|
| reviewed → XY + unit | 29 |
| reviewed → **XY + string** | **16** |

**The 20 wells that lost BS3_S → WCA_1 under unit keying** (Novi WOLFCAMP A vs Enverus 3rd Bone Spring):
- **17 keep WCA_1.** The string pair WOLFCAMP A vs 3RD BONE SPRING SAND learns Novi at 0.86.
- **3 go to BS3_S:**
  - 2 now have their own depth call for BS3_S. The new WCXY witnesses give WCA a reference depth at those wells, and
    the well sits nearer BS3. This is evidence, not pooling.
  - 1 is unresolved: its Enverus string is "3RD BONE SPRING" without "SAND", a thinner pair.

**The 9 wells gaining WCB_1** (Novi WOLFCAMP B vs Enverus WOLFCAMP A LOWER) are the same as under unit keying. That
effect comes from Step 1's blended WCA unit reference, not from the learned table, so keying doesn't touch it.

**4 Midland wells lose an accepted JM** (Novi LOWER SPRABERRY SAND vs Enverus LOWER SPRABERRY: that string pair has too
few decided wells). They fall back to LSSH, sql/16's choice.

**Step 3 is identical to the XY + unit run:** 125 moves. HARACZ AMO #009H is new (AVA_0 → WCXY); SQUINTS drops out (its
input is now WCXY); card 50 now proposes WCXY.

## Change classes of ≥ 20 wells that would need cards (frozen acceptance: 10 cards, 7/10)

| Class (Step 1) | reviewed | XY + string | Why |
|---|---|---|---|
| Delaware BS3_C → BS2_S (pattern) | — | **100** | new string-pair winner |
| Delaware BS3_S → WCXY (depth) | 12 | **75** | XY row: Novi's XY is now read |
| Delaware BS2_C → BS1_S (pattern) | — | **34** | new string-pair winner |
| Delaware BS3_S → WCA_1 (depth) | 19 | **23** | crosses 20 (XY witnesses add control; also true under unit keying) |

Accepted classes that change size, with no new cards needed:
- WCA_2 → WCB_1 (depth): 29 → 38;
- BS3_S → WCA_1 (pattern): 30 → 25;
- LSSH → JM (pattern): 82 → 77.

The rejected class WCB_1 → WCA_1 (depth) goes from 163 to 132.

## Reading

- **String keying does what it was meant to.** The 20 wells keep their reviewed answer where their own string pair
  supports it. No reviewed winner reverses. Pooling no longer lets one Novi string's reliability decide another's.
- **The cost is thinner pairs:** 178 pattern decisions become unresolved. Only 4 of them were applied tags.
- **What it adds:** two new pattern classes (134 wells), both consistent with depth classes already accepted.
- **If adopted and frozen as policy v1, the card queue is:**
  - 4 classes × 10 cards;
  - HARACZ AMO #009H;
  - a re-card of card 50;
  - a confirmation on SQUINTS.
