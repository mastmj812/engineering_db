# Landing surfaces at the extent fringe (2026-11-06, read-only)

```
python -m scripts.tag_surface_fringe --cache <scoreboard cache> --out <this folder>
```

This uses the same grain and hold-out as `surface-density-2026-11-06`: each well is held out together with
every same-code well within ¼ mi. Results are split by distance in from the BOX record extent's boundary. Two
methods are compared:
- **direct:** the code's own surface, 2 mi, ≥ 3 wells;
- **thickness:** structure from a thick, well-drilled neighbouring bench (Delaware BS2_S or the WCA family; Midland
  LSSH, JM or WCA_1), within 2 mi, plus the local median thickness from that bench to the code, measured at
  same-code wells within 5 mi. The WCA codes are the anchor, so they get no thickness prediction.

## By distance in from the extent boundary (`by_basin_zone.csv`, `node_coverage_basin_zone.csv`)

| Delaware | 0–1 mi | 1–2 mi | 2–4 mi | > 4 mi |
|---|---|---|---|---|
| held-out wells | 542 | 1,125 | 2,855 | 20,616 |
| nodes with a direct surface | **28 %** | 45 % | 55 % | 68 % |
| wells predictable, direct / either method | 66 / 80 % | 79 / 90 % | 91 / 95 % | 96 / 98 % |
| direct median / P90 error | **54 / 245 ft** | 46 / 191 | 46 / 168 | 41 / 145 |

| Midland | 0–1 mi | 1–2 mi | 2–4 mi | > 4 mi |
|---|---|---|---|---|
| held-out wells | 572 | 836 | 2,416 | 22,159 |
| nodes with a direct surface | **32 %** | 49 % | 63 % | 80 % |
| wells predictable, direct / either method | 73 / 87 % | 85 / 94 % | 91 / 96 % | 98 / 100 % |
| direct median / P90 error | **37 / 168 ft** | 36 / 130 | 35 / 126 | 36 / 119 |

**The fringe is where it gets weak.** In the outer mile, only about 30 % of the area has a surface. Delaware's tail
error grows from 145 to 245 ft. Midland holds its median (about 36 ft) but its P90 grows from 119 to 168 ft.

## Direct vs thickness, by how far the nearest same-bench well is (`by_nearest_distance.csv`)

| Nearest same-code well | Delaware direct med / P90 | Delaware thickness med / P90 | Midland direct | Midland thickness |
|---|---|---|---|---|
| 0.25–0.5 mi | **39 / 136** | 66 / 242 | **34 / 111** | 46 / 148 |
| 0.5–1 mi | **46 / 164** | 64 / 213 | **42 / 143** | 51 / 169 |
| 1–2 mi | 75 / 330 | **76 / 299** (head to head: 101 vs **76** median) | 66 / 279 | **56 / 189** |
| none within 2 mi | — (cannot) | 88 / 522, for 45 % of those wells | — | 56 / 202, for 65 % |

1. **When the bench has its own wells within about 1 mi, its own surface is better.** The thickness method adds
   15–25 ft of median error there, because the thickness varies too.
2. **When the nearest own-bench well is 1–2 mi away or more, the thickness method wins.** It also reaches wells the
   direct surface cannot. This is the fringe case: the thick neighbour keeps going where the thin bench thins out.
3. **Resolution at the fringe is family-level, not thin splits.** Out there the errors run 50–90 ft median and
   200–500 ft P90. That can separate benches 300+ ft apart (BS2_S / BS3_C, Bone Spring vs Avalon, WCA vs WCC). It
   cannot separate the 100–250 ft Wolfcamp sub-benches, which matches the blind cards (Bone Spring / Avalon held up;
   thin splits didn't).

**Implied method:**
- the direct surface where the bench has control within about 1 mi;
- structure plus thickness where its nearest control is 1–5 mi away;
- the vendor tag beyond that;
- confidence graded by that distance.
