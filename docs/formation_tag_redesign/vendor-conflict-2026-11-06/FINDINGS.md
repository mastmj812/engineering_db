# When Novi and Enverus disagree on the unit, which does depth back? (2026-11-06, read-only)

```
python -m scripts.tag_vendor_conflict --cache <scoreboard cache> --out <this folder>
```

This is the evidence for replacing sql/16's decision logic ("Novi, unless Novi's value is coarse, then Enverus").

- **Population:** clean producing horizontals where both vendor strings map through the crosswalk.
- **Conflict:** the two vendors land in different units. A unit groups lime / sand inside one interval: Delaware AVA,
  BS1, BS2, BS3, WCA, WCB, WCC, WCD; Midland WCB; every other code is its own unit.
- **Reference:** each unit's depth comes from **witnesses**, wells whose two vendors agree on that unit: the rev-1
  estimator within 2 mi, ≥ 3 wells.
- **Call:** depth backs a vendor when the well is ≥ 100 ft closer to that vendor's unit.

## Headline

| | Conflicts | Depth decides | Of decided: Novi backed | Today's tag right, of decided |
|---|---|---|---|---|
| Delaware | 3,813 of 23,528 mapped wells (16 %) | 28 % | 63 % | **54 %** |
| Midland | 2,101 of 27,978 (8 %) | 33 % | 60 % | **44 %** |

(51,506 wells have both vendors mapped, OTHER excluded.)

1. **Where the vendors disagree on the unit, today's tag is right about half the time.** When Novi is coarse and
   sql/16 therefore takes Enverus, depth backs that choice only **38 % (Delaware) and 37 % (Midland)** of the time.
2. **Neither vendor is right overall** (Novi about 60 %), so a blanket flip of sql/16 is not safe. **But individual
   patterns are lopsided**, in both directions:

| Pattern (Novi unit vs Enverus unit) | Conflicts | Decided | Depth backs | Today's tag right |
|---|---|---|---|---|
| Delaware BS2 vs BS3 | 262 | 121 | **Novi 94 %** | 94 % |
| Delaware BS3 vs BS2 | 240 | 123 | **Enverus 73 %** (the BS3_C → BS2_S class) | 35 % |
| Delaware WCA vs BS3 (coarse Novi) | 134 | 53 | **Novi 83 %** | 17 % |
| Delaware BS1 vs BS2 | 98 | 23 | Novi 91 % | 91 % |
| Delaware BS3 vs WCA | 448 | 172 | Novi 65 % | 65 % |
| Delaware WCA vs WCB (coarse Novi) | 822 | 302 | **mixed** (Novi 56 %) | 45 % |
| Midland WCB vs WCA_1 (coarse Novi) | 539 | 240 | **Novi 78 %** | 24 % |
| Midland **LSSH vs JM** | 188 | 111 | **Enverus 99 %** | **1 %** |
| Midland WCC vs WCB | 206 | 25 | Novi 96 % | 96 % |
| Midland MS vs JM | 56 | 29 | Novi 97 % | 97 % |
| Midland JM vs LSSH | 55 | 23 | Novi 100 % | 100 % |
| Midland WCA_1 vs WCB (coarse Novi) | 334 | 138 | **mixed** (Novi 44 %) | 59 % |

3. **Gross conflicts (units two or more apart) mostly go Novi's way:** Delaware 102 of 127 decided (80 %), Midland 55
   of 61 (90 %). The Magnolia wells are this kind.
4. **Depth can decide only about 30 % of conflicts.** The rest have "no control": one of the two units has no
   witnesses within 2 mi. Whole patterns have no witnesses at all, e.g. Delaware WCB vs WCC (885 wells), WCB vs WCD
   (98), and Midland MISS vs BRNT (116). Those need either a per-pattern default or a reference built a different
   way.
5. Inside vs outside the BOX extents makes little difference; almost all conflicts (Delaware 3,736, Midland 1,975)
   are inside.

## What this implies for replacing sql/16's logic

**A precedence table learned from depth**, in place of a hard-coded coarse list:
- Where the vendors agree, use the code.
- Where they disagree on the unit, depth decides per well when it is decisive (≥ 100 ft).
- Otherwise use the pattern's learned precedence, where depth backed one vendor in, say, ≥ 75 % of ≥ 20 decided wells.
- A mixed or unlearnable pattern is flagged, falling back to a stated default.

**Examples of what changes:**
- Midland LSSH-vs-JM wells flip to JM; today's tag is wrong 99 % of the time there.
- Delaware BS3-vs-BS2 wells go to BS2.
- Coarse-Novi Wolfcamp wells whose Enverus unit is Bone Spring / Avalon keep Novi's Wolfcamp unit (Magnolia).
- WCA vs WCB stays a per-well depth call, flagged where depth can't decide.
