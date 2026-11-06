# formation_blueox rule v5.1 — the sub-bench step (2026-11-06)

**Status:** FROZEN at the commit that adds this file. Nothing is applied.

- Code: `box/tag_subbench.py` (tests: `tests/test_tag_precedence.py`, the v5.1 block).
- Development run: `scripts/tag_subbench_dev.py` → `v5_1-dev-2026-11-06/`. It computed churn, classes, crossings and a
  probe of Michael's carded sub-bench calls; no cards were drawn and no constant was changed after it ran.

## Why

v5 decides the **unit**. When the code it keeps comes only from a vendor string that names the interval but not the
sub-bench, the crosswalk writes a **placeholder**. Example: Novi "WOLFCAMP A" → WCA_1.

Michael caught it on card 62, HAY EVELYNN 17/20 002 0023WA (Culberson): proposed WCA_1, but it sits in the WCA_2
band. In the rejected Delaware WCB_1 → WCA_1 class, all 6 of his agreeing cards said WCA_2.

He chose (2026-11-06) to build v5.1 before applying anything. This **reverses Gate 0 Q1 (a) for placeholder codes
only**. Where a vendor names a sub-bench and the vendors disagree (case C), sql/16's choice still stands.

## The rule

The step runs after v5's accepted tags: Michael's carded call, else v5 in an accepted class, else today's tag.

**Placeholder strings** (basin, vendor, raw), pinned by a test:

| Basin | Vendor | String | Crosswalk writes | The unit's codes |
|---|---|---|---|---|
| Delaware | Novi | WOLFCAMP A | WCA_1 | WCXY, WCA_1, WCA_2 |
| Delaware | Novi | WOLFCAMP B | WCB_1 | WCB_1, WCB_2 |
| Midland | Novi | WOLFCAMP B | WCB_1 | WCB_1, WCB_2 |
| Delaware | Enverus | 2ND BONE SPRING | BS2_S | BS2_C, BS2_S |
| Delaware | Enverus | 3RD BONE SPRING | BS3_S | BS3_C, BS3_S |

- Enverus has no lime string in the Bone Spring, so its unqualified string is a placeholder and its SAND string is
  specific.
- **Assumption, open to Michael:** Novi's unqualified SECOND / THIRD BONE SPRING is read as Novi's sand claim, because
  Novi names the lime separately.

**Terms:**
- **Placeholder row:** the tag's code lies in a multi-code unit, and every vendor string that maps to that code is a
  placeholder. Carded calls, overrides and sql/23 codes are never placeholder rows.
- **Sub-bench witness:** a clean evidence well whose two vendors map to the same multi-code unit, and whose specific
  (non-placeholder) strings all name one code.
- **Reference:** each candidate code's witness depth at the row (`landing_surfaces.estimate`, within 2 mi, ≥ 3
  witnesses).
- **Decision:** the nearest referenced candidate, if it is ≥ 100 ft closer than every other referenced candidate and
  within 300 ft → that code (`subbench_depth`; it may confirm the placeholder). Otherwise the placeholder is kept,
  flagged `subbench_default`.

**Constants:** the v5 values, untuned. On card 62 the step falls just short of the margin: its WCA_2 lead is 87 ft,
under 100. It was left that way rather than tuned to the card.

## What it does (`v5_1-dev-2026-11-06/`)

**The placeholder problem is narrow.** Most of today's coarse-Novi wells already carry Enverus's specific sub-bench,
because sql/16 defers to Enverus there.

| | Delaware | Midland |
|---|---|---|
| Placeholder rows | 141 | 466 |
| Decided by depth | 32 | 128 |
| Placeholder kept, flagged | 109 | 338 |
| **Changes** | **26** | **2** |

- All 28 changes are inside the BOX record extents, and none changes the unit.
- **Midland WCB:** where depth decides, it confirms the WCB_1 default on 126 of 128 wells; 2 go to WCB_2 (Irion and
  Crockett). So the Midland WCB_1 written by the accepted classes is mostly right.
- **The Delaware changes:**
  - 20 Bone Spring sand → lime, 17 of them in Lea, with leads of 217–604 ft. The vendor strings are Novi
    "WOLFCAMP" / "BONE SPRING" plus Enverus's generic 2ND / 3RD BONE SPRING.
  - 4 WCA_1 → WCXY. Novi "WOLFCAMP A" vs Enverus "3RD BONE SPRING SAND"; v5 chose the WCA unit, and depth puts them at
    the top of it.
  - 2 WCA_1 → WCA_2.
- **Crossing area** is flat, as expected from 28 wells: Delaware 534 → 531 sq mi, Midland 82 → 83.

**Probe of Michael's carded calls** (not blind: he made them first). On the agreeing cards, v5.1 decided 9
placeholder wells and matched his sub-bench on all 9, with no contradictions. On 4 of his 6 WCA_2 calls it keeps the
WCA_1 default, flagged. Leads there are 100, 87, 65 ft and one has no reference.

## Acceptance (FROZEN)

- **No change class reaches 20 wells.** So acceptance is a full review: one card for each of the 28 changes, and each
  card decides only its own well. Agree applies; a bench code is Michael's call; reject keeps the accepted v5 tag.
- **Guards:** zero unit changes.
- **The 447 placeholder rows kept** are not changed, and the 132 the step confirms need no card. In the warehouse step,
  the matview carries a `subbench_basis` column on every producer: `vendor` (a vendor named the sub-bench) / `depth` /
  `vendor default` (placeholder kept) / `human` (override or carded call) / `sql23`. A consumer can then tell a
  measured sub-bench from a default.
- Applying is the separate warehouse step (a new matview replacing sql/16's decision logic, off-hours), with Michael's
  explicit go.
