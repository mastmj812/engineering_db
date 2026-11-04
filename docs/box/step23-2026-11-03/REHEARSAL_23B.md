# Step 23b: container rehearsal of both record runs and both flips

**Status: BUILT 2026-11-03, at GATE 23b. Gate decision taken 2026-11-03: the no-water stick is NOT COVERED (§3.6).** Everything here ran in the throwaway `box-rehearsal` container (postgis 16-3.4, localhost:5437).
The live warehouse was only READ: deck ids, curated objects mirrored in, and the Midland re-measure's producers. Nothing was stored live, and no
DDL, flip or prune ran there. The live Delaware record is still the 16d record (run 19), and there is still no Midland record.

Container run ids collide with live ones and are not live runs (the box-run-naming rule). This document names each run by what it is,
with the container id in brackets.

## 1. What was stored (container)

| container run | what | forecast locations | oil | identities |
|---|---|---|---|---|
| [26] | replica of the D117 base run (live 24, pruned) | 48,945 | | as stored at the replay |
| [27] | replica of the D117 record (live run 25) | 48,945 | 25,569.9 MMbbl | all 7 tables equal live run 25 row for row |
| [31] | **Delaware step-23 record**, derived from [27] (D153, D154 (d)(f)(h)) | **48,072** | **25,386.6 MMbbl** | all green (`rehearsal23b/delaware_store.log`) |
| [32] | **Midland step-23 base run** (rev 8 / D149 / D151 tiers / D154 (a) haircut), data through 2026-08-01 | 32,541 | 13,520.1 MMbbl | all green (`midland_base_store.log`); water stored after, see §3 |
| [34] | Midland step-23 record, first store (no-water stick still forecast) | 28,828 | 11,128.0 MMbbl | all green (`midland_d150_store.log`); superseded |
| [36] | **Midland step-23 record, final** (gate 23b: no-water stick not covered; [35] was the same store one commit earlier, without the flag) | **28,827** | **11,127.6 MMbbl** | all green (`midland_d150_store_final.log`) |

The [33] attempt rolled back (§3, finding 4), so that id was spent with nothing written.

**Delaware [31] vs the 23a expectation.** 48,072 forecast = 48,706 − 634 D145 conflict sticks, as expected. Oil 25,386.6 MMbbl
(23a: 25,752.9 at 48,706, less D145's 366.2 = 25,386.7). Supporting counts:
- 282 sticks reconciled as drilled since run 25 left the universe (166,843 → 166,561, D154 (h)).
- The 127 re-admitted sticks keep run 25's refusal (70 package, 57 precedent, D154 (d)). 123 of them carry run 25's proximity rows
  verbatim; the other 4 are drilled or conflict sticks.
- 132,502 named D150 parents.
- Gas and water rows are identical to the source.
- Every stream's 600 months sum to its EUR within 0.1 %.

**Midland [36] vs the 23a expectation.** 28,827 forecast of 32,541: the re-measure keeps 28,828 (the 23a cache said 28,809, so +19), less stick
1545426, which is not covered (§3.6). Re-measure outcomes, before that drop:
- factor multi-parent 19,157
- level unexposed 7,466
- factor single parent 2,205
- refused: pattern 2,117, spacing 1,013, precedent 580, package 3

D150 factor mean 0.954 (min 0.503, max 1.067).

### 4.2 MID_BUILD, the Midland base run and record, per bench (fills RECORD_PLAN §4.2)

| bench | tier (D151) | base forecast | base oil (MMbbl) | base gas (Bcf) | record forecast | record oil (MMbbl) | D150 vs base, kept sticks | record gas (Bcf) |
|---|---|---|---|---|---|---|---|---|
| WCA_1 | validated | 5,121 | 1,715.4 | 9,297.9 | 4,579 | 1,418.6 | −5.6 % | 8,141.0 |
| WCB_1 | provisional | 5,477 | 2,081.2 | 11,535.7 | 4,740 | 1,663.8 | −5.5 % | 9,830.9 |
| WCB_2 | provisional | 849 | 325.3 | 2,465.9 | 687 | 258.6 | −0.3 % | 2,006.7 |
| WCC | provisional | 692 | 297.4 | 1,533.8 | 379 | 135.6 | −6.9 % | 870.1 |
| WCD | validated | 3,589 | 1,563.3 | 5,357.5 | 3,412 | 1,484.9 | +0.3 % | 5,101.9 |
| MS | provisional | 4,160 | 1,816.6 | 5,207.0 | 3,885 | 1,596.0 | −4.4 % | 4,799.7 |
| JM | provisional | 4,088 | 2,121.2 | 6,786.5 | 3,422 | 1,583.5 | −8.6 % | 5,543.5 |
| LSSH | validated | 7,238 | 2,968.9 | 9,768.7 | 6,801 | 2,577.3 | −6.7 % | 9,126.7 |
| DEAN | provisional | 1,327 | 630.8 | 1,605.1 | 922 | 409.3 | −2.1 % | 1,045.7 |
| **total** | | **32,541** | **13,520.1** | **53,558.0** | **28,827** | **11,127.6** | **−5.1 %** | **46,466.3** |

Notes on the table:
- Base build: code `1aec6b3` (= merged main for the build path), WCA_1 haircut as recomputed (D154 (a)). Every group's 24-location
  equivalence check against the 21 method was exact (max rel diff 0.0).
- "D150 vs base" compares oil on the kept sticks only (11,730.0 → 11,127.6 MMbbl). The rest of the base-to-record gap is the 3,713 refused sticks.
- Water on the record: 28,827 streams, all provisional (D149 (5)), 54,169 MMbbl. That is ~1.9 MMbbl per location, about 4.9 bbl
  water per bbl oil, reported only (D152 (3)).

## 2. sql/69 and the flips (container, synthetic econ)

Econ in the container is a **SYNTHETIC placeholder**. Each row has the constant pv10_mm = 1.0, labelled `synthetic-23b`, on the 16 deck
ids the live record is priced on (wti60–90 × hh1–4, read from live). Nothing is computed (`scripts/box_rehearsal_econ.py`). The run-[27]
record was priced this way to stand in for live's priced Delaware record.

| check | result |
|---|---|
| sql/69 created in the container | OK: 48,809 rows on record [27], oil ties to box exactly, analyst_ro can SELECT (`sql69_container.log`) |
| 1. flip Delaware → [31], unpriced | **REFUSED** |
| 2. flip Delaware → [31], priced on 15 of 16 decks | **REFUSED** |
| 3. flip Delaware → [31], all 16 decks | OK. box_scout_locations Delaware 48,809 → **48,072** (expected 48,072); oil 25,493.9 → 25,386.6 MMbbl |
| 4. flip Midland → [34], unpriced | **REFUSED** |
| 5. flip Midland → [34], priced on the default deck (wti70_hh3) only | **REFUSED** (the old guard would have flipped this; finding 2) |
| 6. flip Midland → [34], all 16 decks | OK. box_scout_locations Midland 0 → **28,828** (expected 28,828), oil 11,128.0 MMbbl; Delaware rows unchanged at 48,072 |
| 7. flip Midland [34] → [36] (record → record, after the gate decision) | OK. Midland 28,828 → **28,827** (expected 28,827), oil 11,127.6 MMbbl; Delaware unchanged |

**This step changes what the Delaware screens show, in the container only.** After flip 3, erebor's Delaware Map, econ legend, Highgrade and
popups read the D150 derive [31] in the container, priced with the placeholder. Live erebor still reads run 19.

erebor against the container (worktree on erebor main + PR #30, backend :8079):
- **Map, coloured by econ.** Before / after per basin (`3_` / `5_` / `8_` / `10_*.txt`):
  - Delaware: run 27, n = 48,945 → run 31, n = 48,072.
  - Midland: "not forecast yet" on the Delaware fallback → run 34, n = 28,828 (14,793 validated · 14,035 provisional) → run 36, n = 28,827.
  - Both carry the provenance "Steven's econ, display only … assumption set synthetic-23b … BOX run N".
- **Highgrade facets:** `econ_priced: true` in both basins.
- **Popups** (`11_midland_popups.txt`): one stick per D150 outcome reads correctly after PR #30.
  - single parent: "underfill · 1 parent · nearest WCC 551 ft vt / 2,463 ft hz", factor 1.056
  - level: "no depleted parent", factor 1.067
  - refused sticks: their D113 configuration and the refusal text
- **Cache delay:** erebor caches each basin's record id for 60 s (`box_locations._TTL_S`). For up to a minute after a flip, some screens
  still show the old record. At 23d, verify after a minute, not instantly.

## 3. What the rehearsal found (all fixed on this branch)

1. **The store's identity checks went quadratic** (`03e0bae`). The new run's rows are uncommitted inside the store transaction, so the
   planner had no statistics; the orphan anti-join ran an hour before I cancelled it. The store now ANALYZEs the new rows inside the
   transaction. The live 23c store would have hit the same thing.
2. **The flip guard had two holes** (`ded6b5d`):
   - With no Midland record, `priced()` accepted any single deck, so a run priced off the default deck would have flipped and shown 0
     Midland rows in sql/69.
   - The empty-view guard counted both basins together, so a Midland flip that showed nothing still passed on the Delaware's rows.

   Now:
   - The first Midland record needs the Delaware record's decks, all 16 (refusal 5 proves it).
   - Each basin's box_scout_locations rows must equal its priced forecast locations.
   - The other basin's rows must not move.

   New DB-free tests cover the deck rule.
3. **Carried refusals and integer casts** (`7ea7b8c`, `d6931f0`): the first two Delaware store attempts failed on CHECKs and rolled back.
   - The 127 re-admitted sticks now copy run 25's proximity rows verbatim, so their D114 keys stay with the refusal.
   - NULL-bearing integer columns are cast before COPY.
4. **The Midland re-measure dropped the configuration columns** (`e915b60`). The first Midland D150 store failed its first row on
   `n_same` NOT NULL and rolled back. The fix is the same joins `measure_delaware` does. The re-measure was re-run, then stored.
5. **erebor's configuration line contradicted the D150 label** (erebor PR #30). On a D150 run, the named parents are D150's and the
   configuration columns are D113's.
   - Disagreements: 27,957 Delaware and 20,679 Midland kept sticks; 1,830 Midland single-parent sticks have a D113 count of 0.
   - The popup said "no depleted parent" beside "single parent".
   - Fix: D150 factor outcomes count from the named parents. Refused sticks keep the D113 configuration that refused them. D113 runs
     are unchanged.
6. **DECIDED (Michael 2026-11-03, "Make it not covered"): a record stick with no water forecast ships nothing.**
   Stick 1545426 is MID_WCD, covered (validated tier), operator Bayswater, TVD 7,610 ft. It has 0 eligible water analogs within 20 mi,
   so its WOR fit fails. Its oil and gas forecast was sound (D150 `level_unexposed`, factor 1.067; 0.37 MMbbl oil, 0.65 Bcf gas).

   **In the base run** the stick keeps oil and gas without water. `box_water_run store --accept-no-water 1545426` must name exactly the
   failed sticks, and the run's water disclosure lists them (`8dd62e9`). The base run is never a record.

   **In the record**, the step-23 derive classes any source forecast stick that has no water as `not_covered_no_analogs` (`dde9005`, `d7ebf72`;
   default `--no-water not-covered`, while `refuse` stops the store):
   - `n_analogs` = its water-analog count (0);
   - no streams and no proximity row;
   - its oil search flags kept, plus a flag saying why;
   - listed in the run's proximity disclosure (`no_water_not_covered`).

   Water identity on the record is strict again (28,827 = 28,827). erebor (#30, `274a4e7`) shows the class, notes the reason, and no longer
   says "kept the forecast" for a location that ships none (`14_nowater_popup.txt`).

   Separately, 7,610 ft is shallow for WCD. The stick's bench tag may deserve a look in the next tag round.
7. Mirror gaps found by using erebor, container only: `raw_novi_intel.basin_outline`, `curated.wells_enriched`, `curated.production`.
   The mirror now covers them (`d6f7f35` and this commit). The rehearsal-econ deck read refuses to run against the container (`450faa6`).
   The water store writes NaN as JSON null (`51c2d6f`).

## 4. Timings (container; live goes through the session pooler and will be slower)

| step | time |
|---|---|
| Midland base build (read-only, 12 workers) | 5 h 20 min |
| Midland water build | 30 min |
| Midland base store | 12 min |
| water store | 5 min |
| Midland re-measure (live read) | 7 min |
| Midland D150 store | 11 min |
| Delaware D150 derive store | 24 min |

## 5. What 23c does, on "go apply" (each item its own go)

1. **sql/71 live** (DDL). Applied twice in the container, idempotent.
2. **Stores, none of them record:**
   - Delaware derive from run 25, live.
   - Midland base from `runs/step23/midland_record_base`; this needs a fresh build only if live data moved past 2026-08-01.
   - Midland water with `--accept-no-water 1545426` (base run only); the D150 store then makes it not covered (§3.6).
   - Midland re-measure, then Midland D150 store.
3. **The D151 tiers to `bench_scope.validation`.**
4. **A drafted #eng-updates post** for Steven to price both runs. Not posted without a go.

Before 23d: erebor PR #30 merged. Flips only after Steven prices both runs on all 16 decks; the guards above enforce that.
