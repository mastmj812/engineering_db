# Tops vs tags — V5 baseline (2026-10-22)

This is the clean baseline the geologist asked for. It uses his **V5 structure grids** (our `Grids_10-19-26`;
matched to a median 0.3 ft) with the naming decisions of 2026-10-22 applied. The 2026-10-20 folder
(`tops-qc-2026-10-20`) stays as the "before". The per-bench change in agreement between runs is the progress
measure.

**Run:** `python -m scripts.box_tops_qc --step 1|2|3 --out docs/box/tops-qc-2026-10-22` (READ ONLY).
**Pages:** `step2.html` (index + maps), `step3.html` (landing evidence), `step1.html`.
**GGX:** `ggx/` (wells, offset cells, picks needed).

## Decisions applied (geologist + Michael, 2026-10-22)

| Item | Decision |
|---|---|
| Grids | V5 is the baseline; V6 is for isopach mapping only (it scores 3–5 pts worse on Wolfcamp A/B) |
| Rule A | **One WCA bench** = WCXY + WCA_1 + WCA_2, his XY top → B1 top (RRC "Wolfcamp A" tops sit on his XY top, +2 ft over 102 wells) |
| Rule B | His XY top is the BS3_S / Wolfcamp boundary; **Lea and Ward pending** his review (flagged `rule_b_pending`, still scored) |
| Rule C | WCA_1 / WCA_2 sub-split is secondary; no rule now |
| Rule D | **Held**; he checks whether his B2 top is a deeper marker than the operator B1 / B2 split |
| WCC | **Relabel:** WCC is scored against his B2 → C interval |
| WCD | Mapped to his C → D but **held** (unscored) for his log review; WOLFCAMP_D stays suspect, WOLFCAMP-C no longer is |
| AVA_1 | Still unscored until his Middle Avalon surface exists |
| Pecos | Wolfcamp A–D and AVALON2 have no picks there → `no_control` (shown, not scored) |

The 10 ft isopach floors in V5 (B1 → B2, WCD → Strawn) are his stacking rule's minimum thickness, not picks.

## Agreement: before → V5 baseline (scored evidence wells)

| Bench | 10-20 | 2026-10-22 | Structure-suspect (10-20 → now) |
|---|---|---|---|
| WCA_1 | 56.6% | **96.0%** | 912 → 27 |
| WCXY | 70.2% | **93.1%** | 125 → 12 |
| WCA_2 | 79.6% | **86.6%** | 142 → 87 |
| WCC | not scored | **89.3%** (967 wells) | 0 (17 tag-suspect) |
| Bone Springs, Avalon, WCB_1, WCB_2 | — | unchanged (±0.2 pt) | unchanged |

The WCA bench is ~400 ft thick (XY → B1, P25–P75 319–459 ft at WCA wells), so part of its 92% comes from
thickness. It settles the naming; it does not test landing within the bench.

**Rule B pending (Lea + Ward, still scored):**

| Bench | Wells pending |
|---|---|
| BS3_S | 1,608 |
| WCA_1 | 1,291 |
| WCA_2 | 1,106 |
| WCXY | 367 |

## Open: his B2 → C interval holds three industry benches

The B2 → C interval is ~620 ft thick (P25–P75 533–721). The step-3 panel "Wolfcamp B2 / C / D" measures every well
against his B2 top.

**Who lands in it:**

| Tag | Share landing in B2 → C | Median landing |
|---|---|---|
| WCB_2 | 54% | 15 ft below his B2 top (P25–P75 99 ft above to 161 ft below): straddling it |
| WCC | 89% | 368 ft below B2, 231 ft above C |
| WCD | 60% | 519 ft below B2, ~50 ft above his C top |

**Where operators split WCB_2 | WCC**, measured below his B2 top:

| Area | Split | Separation |
|---|---|---|
| Basin | 183 ft | 0.63 |
| Reeves | 150 ft | 0.62 |
| Loving | 200 ft | 0.58 |
| Eddy | 216 ft | 0.29 (weak) |

Lea and Culberson don't separate at all. In Ward the names are inverted: WCB_2, WCC and WCD all land within
66 ft above his B2 top.

**Implication for re-landing:** a well in B2 → C cannot be called WCB_2 or WCC from these surfaces. That needs a
surface roughly 150–200 ft below his B2 top (an industry "WCC top"), or the finding that his B2 top IS the WCB_2
landing horizon. This is the same question as his B2-marker log review, and why rule D's 49% vs 53% comparison
doesn't settle it.

## Where picks are needed (V5 baseline)

| Surface | Wells landing against it | > 1 mi from a pick | 1-mi cells |
|---|---|---|---|
| WOLFCAMP-B1 | 14,136 | 6,464 (46%) | 952 |
| 3BSPGC | 6,167 | 3,086 (50%) | 485 |
| 2BSPGS | 5,046 | 2,426 (48%) | 383 |
| WOLFCAMP-B2 | 4,248 | 2,273 (54%) | 286 |
| 3BSPGS | 4,956 | 2,096 (42%) | 283 |
| WOLFCAMP_XY | 15,320 | 1,397 (9%) | 193 |
| WOLFCAMP-C | 2,496 | 1,437 (58%) | 156 |

- **WOLFCAMP_XY** now carries the whole WCA bench and is well controlled.
- **WOLFCAMP_A** drops out: no bench is bounded by it any more.
- **Offset cells:** B2 still wants up ~90 ft over 357 sq mi (the WCB_2 straddle). XY wants down ~76 ft over
  115 sq mi, where BS3_S lands into the WCA bench (Lea / Ward pending).

## For the re-landing design (his item 6, recorded for the next plan)

Each well's call should carry:

1. The bench: the interval holding most of the lateral.
2. The share of the lateral in it.
3. The distance to the nearest boundary, flagged within ~25 ft.
4. The distance to control for the bounding surfaces.
5. Agreement with the original tag.

Low share, near a boundary, or far from control = provisional.
