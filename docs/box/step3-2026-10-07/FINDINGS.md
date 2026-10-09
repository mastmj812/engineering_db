# BOX step 3 — extents with buffers: findings (session 1 of 2: build + geology export)

**Built 2026-10-07, read-only.** Nothing was written to the warehouse. Plan: `docs/box_type_curves_plan.md`
§5 step 3, decisions D5–D8 and D21–D25. Inputs are the gate-1 final sets
(`docs/box/step1-2026-10-06/wells_final_{WCA,BS2_S}.csv`) and the step-2 edge metric of record (D23:
r = 2,640 ft pin radius, c = 3,960 ft closing).

Step 3 is two sessions (§10). This one builds the extents, calibrates the buffer, and writes the
geology package. Gate 3 ("geology's edited extents loaded as the version of record") happens in
session 2, after Holden's edits come back.

## 0. What exists and how to check it

| What | Where |
|---|---|
| Review pages | `index.html` (calibration), `extent_WCA.html`, `extent_BS2_S.html`. Serve with `python -m http.server 8766 --directory docs/box`, then open `http://localhost:8766/step3-2026-10-07/`. |
| Geology package | `geology/`: shapefiles in NAD83 / UTM 14N US-ft with `.prj` written, `BOX_<pool>_legend.png`, `README.txt` (what to edit and how to return it) |
| Data | `extent_<pool>_v1.geojson` (EPSG:4326, extent + edges), `edges_*.csv`, `stepouts_*.csv`, `holes_*.csv`, `pud_counts_*.csv`, `backtest_*.csv`, `summary.json` |
| Code | `box/extent.py` (pure rule), `box/extent_report.py` (calibration + build), `box/extent_pages.py`, `box/extent_package.py`, `box/geology_io.py` (shapefile round-trip), `box/extent_store.py` (warehouse writes, not run) |
| Scripts | `python -m scripts.box_extents_export` (rebuild, ~5 min) · `python -m scripts.box_extents_import --pool <P> --edited <shp>` (diff page; session 2) · `python -m scripts.apply_box_schema` (**DDL, needs go-apply**) |
| Warehouse DDL | `sql/54_box_schema.sql`: `box.bench_scope`, `box.extent`, `box.extent_edge`. **Authored, not applied.** |
| Tests | `tests/test_box_extent.py`, 23 DB-free tests (rule, fronts, polygon vs point rule, potash clamp, D26 hole fill, diff, `.prj`, GGX-frame point, shapefile round-trip with a hole, wrong-CRS guard). Full suite: 282 passed / 32 skipped. |

Grain: one lateral per api10. 12-mo oil = Novi `cum_12m_oil_bbl` ÷ lateral ft × 1,000 (calendar
basis, as Novi computed it). Interior references are **medians**. No forecasts are made in this
step, so there is no Di or EUR here.

## 1. The rule as built

**Extent = drilled core + per-segment buffer.**

- **Core (D21).** The step-2 outline eroded back by r, which lands it on the last laterals, plus the
  laterals' own lines. The r-dilated outline is never the extent. Core sizes after the D26 hole fill: WCA
  4,914 sq mi, BS2_S 1,964 sq mi; the step-2 measuring outlines were 5,420 and 2,468.
- **Buffer per walked step-2 segment** (D6 plus the plan's 2×2):
  - **Pinned:** a floor of 880 ft (rolled), 1,320 (unknown), or 1,760 (strong).
  - **Gap:** k × gap × perf multiplier (strong 1.0, unknown 0.75, rolled 0.5), clipped to
    [floor, cap].
  - **Overrides, in priority order:**
    1. Pre-2016 laterals just beyond a gap → floor (D5: tighten only).
    2. A live-front side → cap.
    3. A segment inside the potash polygon → floor (D24).
  - **Holes:** the tightest floor, and flagged. **Exception (D26, 2026-10-08):** a hole ≥ 90% covered by
    the ½-mi footprint of pre-2016 laterals is legacy drilled-up ground and is filled into the core,
    potash holes included.
- **Sectors.** Each point beyond the core takes the buffer of the nearest walked-ring sample, i.e.
  that sample's Voronoi cell. Inside the potash polygon, every point is held to its sector's floor.
  The polygon is assembled per distinct buffer value, then smoothed by 330 ft. A test checks the
  point rule and the polygon agree away from the edge.
- **Step-outs** (D23's second half):
  - Performing step-outs (≥ 0.70× interior) within 5 mi **join the core as islands**.
  - On a live-front side, step-outs too new to have a 12-mo result also join.
  - Rolled step-outs, isolated tests (> 5 mi), and too-new step-outs on a non-front side are left out
    and listed in the flags layer.
- **Live front (D22, made a detected rule).** A side is a live front when its step-outs within 5 mi
  include ≥ 3 performing tests, and those outnumber the rolled ones 2:1. **Today only BS2_S W
  qualifies** (8 performing, 1 rolled, 18 too new; performing median 0.86× interior). That matches
  D22, and nothing else trips it.

## 2. Calibration: k, cap, floor (WCA + BS2_S together)

**Method.** A time-split backtest at cutoffs 2021-01-01 and 2023-01-01.

- The step-2 metric is rebuilt from the laterals online before T. 12-mo oil counts only if 12 months
  had elapsed by T.
- Each config is scored on the later wells that landed ≥ 50% outside the T core and within 3 mi of
  it. Infill of holes that were open at T is excluded, since it isn't an edge test.
- A later well is **performing** at ≥ 0.70× the T interior median, **rolled** below that.
- J = share of performing later wells the extent would have contained − share of rolled ones.
- The grid is 120 rule configs plus 6 flat-buffer baselines: k {0.25 … 1.0} × cap {½ … 2 mi} ×
  floor {660, 880, 1,320} × reference {pool, local}.
- The selection rule was fixed before the run: best pooled J with floor ≥ 880 ft; ties within 0.02
  go to the smaller area; the §6 pool-wide reference is kept unless local wins by more than 0.02.

**Chosen: k = 0.75, cap = 7,920 ft (1.5 mi), floor = 880 ft, pool-wide reference.** It captures 52%
of later performing wells vs 37% of rolled ones (precision 0.78; J = +0.15), adding 1,813 sq mi
summed over the four backtests.

| | added sq mi (4 backtests) | performing captured | rolled captured | J | precision |
|---|---|---|---|---|---|
| **chosen rule** | 1,813 | 52% | 37% | **+0.15** | 0.78 |
| flat 2,640-ft buffer (same area) | 1,773 | 24% | 28% | −0.04 | 0.69 |
| flat 5,280-ft buffer | 3,441 | 59% | 55% | +0.04 | 0.73 |

**What the backtest says. Read this before trusting the knobs.**

1. **The rule beats a flat buffer by a wide margin at equal area** (J +0.15 vs −0.04). About
   two-thirds of that margin is the **live-front term**. With it switched off, the same config scores
   pooled J +0.03 (WCA +0.01, BS2_S −0.03), still ahead of a flat buffer of the same area (−0.02).
   With it on, WCA scores +0.22 and BS2_S +0.04. At past cutoffs the detector
   tagged WCA N (2021 and 2023, the north/WCXY push) and BS2_S W (2021) and S/SW/W (2023).
2. **The 2×2 class predicts the next well; gap length and distance do not.**
   - Later wells beyond a rolled edge performed **38–40%** of the time (median 0.60–0.65× interior).
     Beyond a strong edge it was **78–81%** (1.0×), and on a live-front side 78% (1.02×).
   - Gap length showed nothing: 68–71% performing for any gap from ¼ mi to over 1 mi.
   - Distance showed nothing out to 1.5 mi (72–78%), then a drop to 54% at 1.5–3 mi. That flat
     stretch is selection bias: operators step out only where they expect success.
   - So **k is weakly identified.** k from 0.25 to 1.0 moves pooled J by about 0.03. The cap only
     binds on fronts and long gaps. The 2×2 multipliers change capture only a little, because a few
     hundred feet of buffer is small next to where the next wells land (median ½–1 mi out).
3. **Pool vs local performance reference** (the open gate-2 question): J 0.163 vs 0.160, so the data
   can't tell them apart. **Kept pool-wide per §6.**
4. **Holes fill with good wells.** Later wells drilled into holes that were open at T performed like
   the interior: WCA 80% (1.00×), BS2_S 66% (0.80×). Today's holes are kept and flagged (see §5b).
5. **BS2_S is the harder bench.** Later wells beyond its 2021–23 edge performed only 50% of the time
   (0.70×) against a sweet interior (T interior medians 30.9–33.4k bbl / 1,000 ft vs 24.8k today).
   No buffer config discriminates well there.

## 3. The extents

| | WCA | BS2_S |
|---|---|---|
| Extent (generated v1, with D26) | **5,190 sq mi**, 12 parts, 14 holes | **2,308 sq mi**, 8 parts, 15 holes |
| Drilled core / step-2 outline | 4,914 / 5,420 sq mi | 1,964 / 2,468 sq mi |
| Legacy drilled-up holes filled (D26) | 3, 19.7 sq mi (97 pre-2016 laterals) | 8, 74.3 sq mi (273 pre-2016 laterals; 4 mostly potash) |
| Buffer, perimeter-weighted mean | 1,706 ft | 2,269 ft (W front 6,911 ft) |
| Walked perimeter: pinned floor / k×gap / potash / pre-2016 / front | 407 / 205 / 125 / 5 / 0 mi | 346 / 163 / 71 / 12 / 50 mi |
| Live fronts | none | **W** |
| Step-outs: islands / rolled out / isolated / too new | 4 (N/NW, e.g. SM MISO State 0.93–1.07×) / 15 / 2 / 4 | 29 (26 W) / 15 / 38 (22 SE Texas) / 6 |
| Geology flag: pinned edge with strong wells | 145 mi (N 65, NW 44; 2.0×-performing edge wells like Mallon 27) | 113 mi (N 35, NW 23, S 22) |

**D1 PUD universe inside** (read-only count). This is the Novi PUD category only, no RES. A stick is
inside if ≥ 50% of its length is in the extent (co-extent overlap, rule 9). D1 = remaining_pud ∪
conflict ∪ not-yet-reconciled.

| bench (Novi tag) | in generated extent | in drilled core | in step-2 outline | Delaware D1 total |
|---|---|---|---|---|
| BS2_S | **3,998** | 3,055 | 4,585 | 15,122 |
| WCA_1 + WCA_2 | **1,164** | 1,002 | 1,394 | 3,425 |
| WCXY (in the WCA extent) | 2,395 | 2,259 | 2,677 | 3,408 |

**74% of Novi's Delaware BS2_S PUDs sit outside the BOX BS2_S extent.** That is the "BOX extents far
tighter than Novi's" expectation (D16), now with a number on it.

## 4. Warehouse (not applied — needs your "go apply")

`sql/54_box_schema.sql` creates schema `box` with three tables:

- `bench_scope`, seeded with the D2 list plus the two pilot pools. The seed uses ON CONFLICT DO
  NOTHING, so your edits survive a re-apply.
- `extent`: generated or geology_edited; exactly one `is_record` row per bench, via a partial unique
  index; `parent_extent_id` and `diff_stats` for the edit.
- `extent_edge`: the per-segment 2×2, buffer, rule and flag.

It also adds GiST indexes plus the geography expression index, `analyst_ro` read access, no Data-API
access, and comments. These are additive extensions of the §4.2 sketch: `member_benches`,
`is_record`, `parent_extent_id`, `diff_stats`, `area_sqmi`, edge `side` / `rule` / `perf_ratio`, and
the `hole` edge class.

**Verified on a throwaway PostGIS 16 container, not Supabase.** All 28 checks of
`scripts/apply_box_schema.py` passed: tables, PKs, named indexes, the seed by identity, grants,
anon/authenticated with no usage, the ETL never naming `box`, the is_record uniqueness refusal, and
EXPLAIN using `box_extent_geom_gix` and `box_extent_geog_gix`. A re-apply was idempotent and kept a
hand edit.

On the same container:

- `store_generated` wrote both v1 extents with their edge rows. PostGIS geodesic area matches the
  planar figure within 0.1%.
- `store_edited` stored a synthetic edit as the version of record, with the parent linked.
- The import script diffed an unedited re-import to **0.00 sq mi**, and a +4.0 sq mi synthetic edit
  as +3.98. The gap is the UTM 14N vs 13N scale difference, not a defect.

The container has been removed.

## 5. Flags: conflicts with §2 and choices I made (none resolved silently)

a. **D24 "never extends an extent".** Inside the Secretary's Potash Area I hold the buffer to its
   **floor** (880–1,760 ft from the wells there), not to zero. The gap is never widened, and pre-2016
   wells there don't count against it. If you meant zero standoff inside the polygon, it's a
   one-line change.

b. **DECIDED 2026-10-08 — D26** (see §7) for legacy drilled-up holes. The rest of this item still stands for the
   other holes. **Holes are kept as holes** (shrunk by the 880-ft floor) and flagged for geology. The backtest
   says holes tend to fill with interior-grade wells, though today's holes are the persistent ones.
   - BS2_S: 26 holes, 209 sq mi, of which 91 sq mi is potash area; 12 holes are more than 50%
     potash.
   - WCA: 22 holes, 178 sq mi, of which 10 sq mi is potash area.
   - **Your call:** keep for geology, or fill the non-potash holes by rule before the package goes
     out.

c. **Next-row floor (my addition).** The rule requires floor ≥ 880 ft (narvi's fallback spacing), so
   the next development row beyond any producer is always inside. Without that constraint the
   optimum is 660 ft, at J 0.165 vs 0.163, which is noise.

d. **The cap optimum sits on the grid edge.** A 2-mi cap scores J 0.163 vs 0.151 at 1.5 mi, inside
   the tie band, so the smaller area wins. The cap only binds on fronts (BS2_S W today).

e. **Live front is now a detected rule,** generalised from D22. Today it agrees with D22: BS2_S W is
   the only front. It will tag new fronts at the next regeneration. That's intended, but it's a rule
   you haven't seen before.

f. **Step-out performance uses any 12-mo oil/ft,** not only D9-cohort laterals. The D9 lateral window
   normalises type-curve cohorts; it isn't a test of whether one step-out worked. This moves 4 WCA
   step-outs into islands (e.g. MISO State #163H/#168H, 1.2–1.4 mi NW, 0.93–1.07×). Backtest scoring
   stays on the D9 cohort.

g. **Potash polygon source** is `CFO_POTASH_SOPA_1986` (BLM Carlsbad FO, 497,632 ac). It came from
   the BOX1 archive and is copied to `docs/box/ref/potash_sopa_1986/`. It is the 1986-order boundary;
   if you meant the 2012 SO 3324 "Designated Potash Area" polygon, I need that file.

h. **PUD membership is a step-7 question; here it's only counted.**
   - Novi tags just 3,425 Delaware D1 PUDs as WCA_1/WCA_2, and 3,408 as WCXY. 2,395 of those WCXY
     PUDs sit inside the WCA extent.
   - D20 makes WCXY one-way *evidence*. Whether WCXY PUDs get WCA forecasts isn't decided.
   - The small WCA count may also be a Novi tagging issue (WCB_1 7,397 / BS3_S 13,085 D1 PUDs).

i. **Edge-pinning QC-caveat wells** (step 2: WCA 93, BS2_S 62) never got the individual look gate 1
   promised for gate 2. They ship in the laterals layer with `QC_NOTE` so geology sees them, but
   that review is still open.

j. **§9 extent-trigger constants (proposal).** Re-review a side when ≥ 5 new ≥ 2016 laterals that
   are performing (≥ 0.70×) land ≥ 50% outside the record extent within 3 mi of it, or when the
   live-front rule changes state on a side. Set at the first quarterly check; not built.

k. **GGX ingest is untested.** The `.prj` is the exact ESRI definition of NAD83 UTM 14N ftUS, and a
   test pins a known point to the GGX grid frame (−104.3, 31.9 → E −4,834.8 / N 11,619,496.5 usft).
   The open D7 item, "geologist's one-line CRS confirmation", still applies: ask Holden to confirm
   the layers overlay his HCA grids.

## 6. Gate 3 — what happens next

1. **You review** `extent_WCA.html` / `extent_BS2_S.html` and the calibration on `index.html`, and
   decide flags a–h above.
2. **You send** `geology/` (zip the folder) to Holden. I don't send it. `README.txt` tells him what to
   edit (the `*_extent_v1` layer only) and how to return it (`*_extent_v1_edited.shp`).
3. **"go apply"** for `sql/54`: `python -m scripts.apply_box_schema`, then
   `python -m scripts.box_extents_export --store`, which stores generated v1. This can happen any time
   before session 2.
4. **Session 2:** `python -m scripts.box_extents_import --pool <P> --edited <shp> --puds` → diff page →
   your review → `--store --record` → gate 3 closed.

## 7. D26 — legacy drilled-up holes are filled (Michael, 2026-10-08)

**Question.** Michael asked why WCA showed holes where pre-2016 laterals exist. They were holes
because the outline is built only from ≥ 2016 laterals, and D5 lets pre-2016 wells tighten, never
extend.

**Michael's diagnosis.** The 14.3-sq-mi WCA hole has no modern wells because it is completely
drilled up by legacy wells; there is no room for an operator to place a new one. The data agrees: 68
pre-2016 laterals cover 100% of it within ½ mi, and Novi lists only 5 D1 PUDs there.

**D26.** A hole of the drilled body that is ≥ 90% covered by the ½-mi footprint of pre-2016
laterals is legacy drilled-up ground. It is **filled into the extent, potash-area holes included**.
The old wells remain negative evidence at edges (D5) and are never curve evidence (D9). The rule
never extends an outer edge.

| pool | holes filled | area | pre-2016 laterals | notes |
|---|---|---|---|---|
| WCA | 3 | 19.7 sq mi | 97 | 14.3 sq mi (68 wells), 3.6 (21), 1.8 (8); 0% potash |
| BS2_S | 8 | 74.3 sq mi | 273 | four are 45–100% potash, including the 34.3-sq-mi hole at −103.86, 32.64 (116 wells, 95% cover) where Novi still lists 62 D1 PUDs — flagged for geology as possible infill room |

**Effect.**
- Extents: WCA 5,160 → **5,190** sq mi; BS2_S 2,201 → **2,308** sq mi.
- D1 PUDs inside: BS2_S 3,803 → **3,998**; WCXY in the WCA extent 2,377 → 2,395; WCA_1 + WCA_2
  unchanged.
- Calibration pick unchanged: k = 0.75, cap = 7,920 ft, floor = 880 ft, J +0.15.
- In the geology flags layer, filled holes are labelled "hole filled (D26)", green on the map.

## 8. D27 — the extent is the development envelope (Michael, 2026-10-09)

**Supersedes §1's construction and §3's numbers.** The v1 package in `geology/` is now the D27
build. The calibration in §2 is unchanged (same pick: k = 0.75, cap = 7,920 ft, floor = 880 ft).

**How we got here.**
- BS2_S showed a strong SE development lobe, a big gap, then another strong trend. Michael's view:
  a sedimentary bench with no structural break has no voids between development trends.
- Novi's BASE_CASE BS2_S inventory is one continuous blanket with no voids. It sits well beyond
  any BOX version: W and S aprons, plus a separate SE Texas body about 40 mi out.
- A 2BS structure overlay showed the BS2_S W edge on the 6,300–6,900-ft 2BS top, with producers
  rolling over updip of about 7,000 ft:

  | 2BS top | median oil ratio | share performing |
  |---|---|---|
  | 6,750–7,000 ft | 0.68× | 39% |
  | 7,000–7,250 ft | 0.83× | 68% |
  | 7,250–7,500 ft | 1.03× | 84% |

- Cutting developed wells at that contour was rejected. The extent states where the bench is
  developed; performance belongs to the TC areas.

**D27, as built**
1. **Developed is always in.** Every ≥ 2016 pool lateral within 8 mi of the body joins the
   extent, whatever its performance. Isolated tests beyond 8 mi are out and listed in the flags
   layer.
2. **No voids.** The buffered extent is closed at 4 mi radius, which bridges gaps between
   development trends narrower than 8 mi, and every interior void is filled, potash included.
   Edges placed by a bridge are classed `envelope bridge (D27)`: geology's question is whether
   a structural or reservoir break should cut there.
3. **Evidence governs reach beyond the outermost development only.** That covers the 2×2
   buffer, live fronts, the potash floor and the pre-2016 rule. **BS2_S updip limit:** where the
   2BS top is shallower than 7,000 ft (Holden's grid), the buffer is held to the floor. The
   limit ships as `BOX_BS2_S_updip`. WCA has no depth limit (see below).

**Result**

| | WCA | BS2_S |
|---|---|---|
| Buffered extent before the envelope | 5,208 sq mi | 2,307 sq mi |
| **D27 envelope** | **6,118 sq mi**, 1 part, 0 voids | **3,473 sq mi**, 2 parts, 0 voids |
| Bridged or filled | 911 sq mi | 1,166 sq mi |
| Edge placed by a bridge | 198 mi | 193 mi |
| Developed ≥ 2016 laterals outside | 1 (isolated test) | 35 (isolated tests; 22 are the SE Texas scatter) |
| D1 Novi PUDs inside (≥ 50% of stick) | WCA_1 + WCA_2 1,794; WCXY 3,157 | **7,804 of 15,122** Delaware D1 (52%) |

- **The round bites along the outer edge** are embayments wider than 8 mi with no development.
  D27 deliberately leaves them out; geology can redraw them if structure or reservoir says they
  belong in.
- **BS2_S's 2nd part** is a small W island: developed laterals within 8 mi that the bridge didn't
  join to the body.

**Backtest check** (`backtest_envelope.csv`, `index.html#envbt`). Later wells ≥ 50% outside
the cutoff-year core, within 3 mi of it, with a 12-mo result:

| | performing wells contained | rolled wells contained |
|---|---|---|
| pre-D27 buffered extent | 24–46% | 21–43% |
| D27 envelope | 82–94% | 67–87% |

The envelope is a development statement, not a performance screen: it contains most of where
operators went next, good or bad. Telling those apart is the TC areas' job in step 4.

**WCA depth check (read-only; not applied, your call).** ≥ 2016 WCA producers by depth to the
WCA top (HCA_WOLFCAMP_A grid; 95.5% covered):

| WCA top | wells | median ratio | share performing |
|---|---|---|---|
| < 7,500 ft | 34 | 0.47× | 15% |
| 7,500–8,500 ft | 133 | 0.74–0.75× | 52–59% |
| ≥ 8,500 ft | | 0.88–1.23× | 72–93% |

That's the same updip rollover as BS2_S, more gradual. A WCA limit would sit between 7,500 and
8,500 ft.

**Still open for gate 3:**
- WCA depth limit: yes or no, and at what depth.
- §5 flags a, c–k (b is closed by D26 and D27).
- go-apply sql/54.
- Sending `geology/` to Holden.

## 9. D27 amended (Michael, 2026-10-09): development needs 3+ wells; no updip limit; generalized edge

**Why.**
- **The 8-mi "developed is in" rule took single test wells as development.** On BS2_S, a lone
  2025 Tascosa well pulled a wedge out to the W: SHAKE 'N BAKE 2 STATE #204H, api10 3001555251,
  4,658-ft lateral at 5,917 ft TVD, 6.6 mi W of the body, no 12-mo result yet. Michael couldn't
  find it in anduin.
- **The 2BS 7,000-ft updip limit never removed wells.** It only held the reach past the last W
  wells to the floor. That was 37 sq mi (about 1%) of BS2_S, and it conflicted with the D22 W
  live front.
- **The round bites** left by the 8-mi bridge read as scallops.

**Amendments**
1. **Development = a step-out cluster of at least 3 laterals** (laterals within 1 mi of each
   other) within 8 mi, whatever its performance. One- and two-well step-outs are tests: listed,
   not included.
2. **No updip depth limit on either bench.** WCA was checked and declined: its W wells stay in
   and will inform a low-performing TC area. The BS2_S 7,000-ft limit is dropped. D25 stands.
3. **Generalized edge:**
   - 2-mi simplification plus corner cutting;
   - a proportional bulge wherever that would leave a developed lateral out (hull of those
     laterals and the edge within max(1.5 mi, 2.5× how far they sit out), filleted);
   - corners rounded at ¾ mi, re-guarding developed laterals.

   Rejected along the way: re-including the full buffered footprint (lumpy), a free-form outward
   push (BS2_S +981 sq mi), and plain corner smoothing (dropped 14–18 developed laterals).

**Result (the v1 package in `geology/`)**

| | WCA | BS2_S |
|---|---|---|
| Extent | **6,168 sq mi**, 1 part, 0 voids | **3,358 sq mi**, 1 part, 0 voids |
| Raw envelope before generalizing | 5,919 sq mi | 3,223 sq mi |
| Step-out programs in (≥ 3 laterals) | 10 laterals: SM Energy NW, Mongoose SE, Permian Resources W | 36 laterals: Mewbourne/Paloma W 18, Matador/Mewbourne W 11, Chevron/Conoco SW 7 |
| Tests out: 1–2-well step-outs within 8 mi / beyond 8 mi | 14 / 1 | 17 / 35 |
| ≥ 2016 laterals outside the extent | 15, all tests | 51, all tests |
| D1 Novi PUDs inside (≥ 50% of stick) | WCA_1+2 1,934; WCXY 3,211 | **7,478 of 15,122** |

The calibration pick is unchanged: k 0.75, cap 7,920 ft, floor 880 ft. The envelope backtest is
in `backtest_envelope.csv`.
