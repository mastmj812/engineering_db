# How many wells does a landing surface need? (2026-11-06, read-only)

```
python -m scripts.tag_surface_density --cache <scoreboard cache> --out <this folder>
```

- **Grain:** evidence wells (survey depth else clean `tvd_ft`, no planned survey, ≥ 4,000 ft), tagged with a BOX
  record extent's code (live tag), lateral midpoint inside that extent. Delaware's WCA extent holds WCXY / WCA_1 / WCA_2.
- **Coverage:** the share of the extent's ¼-mi nodes with ≥ N same-code wells within R.
- **Accuracy:** each well is held out together with every same-code well within ¼ mi of it, so a node is never closer
  than that to its data. Its depth is then predicted from the rest within R: a robust plane when ≥ 4 remain, else the
  median.

## Result

**The error barely depends on N; coverage depends on it heavily.** Pooled by basin (`pooled.csv`):

| Delaware | R = 1 mi | 1.5 | **2** | 3 |
|---|---|---|---|---|
| coverage, N ≥ 3 | 27 % | 46 % | **61 %** | 79 % |
| coverage, N ≥ 5 | 13 % | 32 % | 48 % | 70 % |
| median \|error\|, N ≥ 3 | 41 ft | 42 | **44** | 49 |
| P90 \|error\|, N ≥ 3 | 167 ft | 152 | **148** | 155 |
| P90 \|error\|, N ≥ 5 | 157 ft | 138 | 141 | 151 |

| Midland | R = 1 mi | 1.5 | **2** | 3 |
|---|---|---|---|---|
| coverage, N ≥ 3 | 38 % | 58 % | **71 %** | 86 % |
| coverage, N ≥ 5 | 24 % | 45 % | 60 % | 79 % |
| median \|error\|, N ≥ 3 | 35 ft | 35 | **36** | 39 |
| P90 \|error\|, N ≥ 3 | 141 ft | 124 | **119** | 122 |

1. **Median error sits at 35–45 ft, whatever N is, out to 2 mi.** That floor is the scatter of landings within a bench
   plus tag noise. More wells don't lower it, so requiring 5 instead of 3 buys almost nothing.
2. **P90 improves a little with N** (Delaware 2 mi: 148 → 141 ft going from 3 to 5 wells) but costs a lot of
   coverage (61 → 48 %).
3. **2 mi is the knee.** 1 mi halves coverage and raises the P90, because a plane through few, close wells is
   unstable. 3 mi adds 5–10 ft of median error, because dip and curvature stop being planar.

**Recommended default: R = 2 mi, N ≥ 3** (robust plane at ≥ 4 wells, median below that). Against the 1.5 mi / ≥ 5 I
first proposed, coverage roughly doubles on the sparser benches, at the same median error:

| Bench | 1.5 mi / ≥ 5 | 2 mi / ≥ 3 |
|---|---|---|
| Delaware WCB_1 | 29 % | 70 % |
| Delaware WCB_2 | 18 % | 50 % |
| Delaware BS1_S | 16 % | 41 % |
| Midland DEAN | 15 % | 37 % |

Nodes without enough wells are the sparse areas, and they keep the vendor tag.

## Per bench at the default (`coverage_accuracy.csv`)

The P90 error set against the local gap to the adjacent bench says where surfaces can separate benches at well level.
- **Clear separation (P90 well under the gap):**
  - Delaware: AVA_0, AVA_2, BS1_S, BS2_C, BS2_S, BS3_C, WCB_1.
  - Midland: MS, JM, LSSH, DEAN, WCA_1, WCB_1, WCB_2, WCD.
- **Borderline (P90 about equal to the gap):** Delaware WCXY (97 vs 104 ft), WCA_1 (98 vs 104), WCA_2 (117 vs 128),
  BS3_S (173 vs 172), WCB_2 (164 vs 190).
- **Noisy (P90 above the gap):** Delaware AVA_1 (260 vs 218), Delaware WCC (232 vs 190), Midland WCC (246 vs 172).
  The tail there is most likely mis-tagged wells inside the extent, which the crossing map should locate.
