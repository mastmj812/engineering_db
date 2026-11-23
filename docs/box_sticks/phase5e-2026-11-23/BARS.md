# BOX sticks phase 5e: preview in erebor. Step 1 results and the bars for steps 2 and 3

Written 2026-11-23, before any erebor code. Step 1 ran read-only through erebor's own connection (`app.db.engine`: READ ONLY
transaction, 300 s timeout, transaction pooler). Probe: `step1_probe.py` in this folder (run from `erebor/backend` with
erebor's venv). Record sets: 24 (Delaware, 46,153 sticks) and 25 (Midland, 33,122).

## Step 1 results

**Access.** erebor connects as `postgres`, read only. It can read all three relations: `box.location_stick` (79,275 rows),
`box.location_set` (7), `curated.box_location_status` (79,275). No warehouse object and no grant is needed.

**Tile query** (record sticks of one basin intersecting the tile, left-joined to the nightly status), on the tile over each
basin's densest 0.05-degree cell. Every run used `box_location_stick_geom_gix`; no sequential scan.

| Zoom | Delaware sticks | exec | tile size | Midland sticks | exec | tile size |
|---|---|---|---|---|---|---|
| 7 | 21,902 | 734 ms | 1,340 KiB | 17,257 | 507 ms | 1,054 KiB |
| 8 | 21,902 | 365 ms | 1,356 KiB | 17,257 | 278 ms | 1,067 KiB |
| 9 | 18,007 | 300 ms | 1,112 KiB | 8,002 | 127 ms | 487 KiB |
| 10 | 6,973 | 115 ms | 421 KiB | 3,130 | 45 ms | 194 KiB |
| 11 | 2,099 | 31 ms | 127 KiB | 787 | 12 ms | 49 KiB |
| 12 | 680 | 11 ms | 41 KiB | 309 | 5 ms | 19 KiB |
| 13 | 246 | 4 ms | 15 KiB | 117 | 2 ms | 7 KiB |

Sizes are uncompressed. Reading: lines below zoom 10 cost a megabyte a tile for a picture nobody can read. **The layer starts
at zoom 10.**

**Gunbarrel query** (record sticks intersecting the selection, one row per leg, with status):

| Selection | Delaware | exec | Midland | exec |
|---|---|---|---|---|
| 1 x 1 mile | 87 sticks, 12 benches | 1.4 ms | 59 sticks, 8 benches | 1.0 ms |
| 3 x 3 miles | 277 sticks (285 legs), 13 benches | 6.8 ms | 158 sticks, 8 benches | 4.3 ms |

## Decisions taken into step 2 (defaults; say so to change one)

- Layer and gunbarrel points are **off by default**, behind one switch labelled as a preview.
- **Every status is drawn.** Open, permitted and pending at full strength; producing, conflict and crowded faded, so what
  the nightly took out can be seen against the wells.
- Colour by bench, using the bench colours erebor already uses.
- A BOX stick is never clickable into the workup and never cullable in the gunbarrel: it has no forecast.
- Lines only, from zoom 10. No low-zoom points.

## Bars, step 2 (erebor backend)

| Bar | Measure | Passes when |
|---|---|---|
| E1 | erebor test suite | green from the repo root, still DB-free; new SQL-shape tests cover the tile query and the gunbarrel arm |
| E2 | Record sets only | both queries reach sticks only through `box.location_set.is_record` and bind the basin; a test asserts it |
| E3 | Tile endpoint, cost | below zoom 10 it answers an empty tile without a query; the worst zoom-10 tile is <= 500 KiB uncompressed and <= 500 ms |
| E4 | Tile endpoint, isolation | its cache entries cannot collide with the existing tiles (keyed by layer); a sample of existing Novi tiles is byte-identical before and after |
| E5 | Gunbarrel, switch off | for a fixed selection the response is identical to today's, byte for byte |
| E6 | Gunbarrel, switch on | the axis, its ends and every existing row are unchanged; BOX rows are one per leg, and their stick count equals an independent count of record sticks intersecting the selection |
| E7 | Untouched endpoints | `/select` and Highgrade answers for a fixed selection are identical before and after |
| E8 | Read-only and bound | no write; values bound, identifiers fixed in code; BOX attributes are read through `app/box_locations.py` |

## Bars, step 3 (erebor frontend)

| Bar | Measure | Passes when |
|---|---|---|
| F1 | Type check | `tsc` strict clean; switch state lives in the Zustand store |
| F2 | The layer renders | screenshots at zoom 10, 12 and 14 in both basins with the switch on; nothing drawn with it off |
| F3 | Hover | bench, landing TVD, rung and expected error, spacing, lateral length, flags, status and matching well; worded as a BOX stick with no forecast |
| F4 | Gunbarrel | BOX sticks drawn with their own marker at their landing TVD beside PDP wells; faded when taken out; not cullable; counted separately in the caption |
| F5 | Nothing else moves | with the switch off: map, colour-by, filters, counts, Highgrade and the workup behave as before (same screenshots, same counts) |
| F6 | Legend and modes | a legend entry while the switch is on; the layer follows the app modes that hide sticks |
| F7 | U-turn sticks | both legs drawn on the map; two points in the gunbarrel, same stick id |

## What step 4 needs from Michael

DSU by DSU: what looks wrong (depth, bench, row position against producers, spacing, a stick that should not exist, a missing
one). Each finding is written up with the stick ids and goes to the generator before phase 6.
