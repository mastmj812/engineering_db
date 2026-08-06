# Deal GeoPackage authoring spec (Land → Engineering)

**Audience:** the land department / GIS (QGIS).
**Status:** schema of record, based on the first conforming deliverable
(`Toucan v2.gpkg`, 2026-08). One `.gpkg` per deal replaces the zipped
shapefile. The apps (narvi, erebor, anduin) accept both formats; gpkg is
preferred because it carries the Tract/DSU structure and deal terms that a
shapefile cannot.

**Tolerance first:** a non-conforming file still works — geometry always maps.
Missing columns simply mean the apps can't light up the extras (depth flags,
WI display, DSU naming). Nothing below is a hard requirement except "polygons
in a real coordinate system."

---

## 1. File and layer conventions

| Item | Convention |
|---|---|
| File name | `<Deal Name>.gpkg` — one file per deal. Re-uploading a file with the same name **replaces** its polygons in anduin, so keep the name stable across revisions (use content, not filename, to version). |
| Layers | **One polygon feature layer**, named for the deal (e.g. `Toucan v2`). The layer name is display-only; the apps do not parse it. |
| Geometry | POLYGON or MULTIPOLYGON, both fine. No Z/M needed (flattened if present). Holes are preserved. |
| CRS | EPSG:4326 (WGS 84) preferred. Any proper CRS embedded in the file works — the apps reproject. **Never** export with an undefined CRS. |

## 2. Row model — `Type` column discriminates DSU vs Tract

One layer, two kinds of rows:

- **`Type = 'DSU'`** — one row per drilling/spacing unit. This is what the
  apps map and what narvi turns into a working parcel. Geometry = the full
  unit outline (union of its tracts).
- **`Type = 'Tract'`** — one row per lease tract inside a DSU. Reference
  detail: per-tract WI/NRI and depth language. Tracts are matched to their
  DSU **spatially** (a tract's polygon must sit inside/overlap its DSU) —
  there is no ID join, so keep tract geometry within its unit outline.

Rows with a missing or unrecognized `Type` are treated as unit shapes and
still map. A file with no `Type` column at all behaves exactly like a
shapefile (every polygon is a unit).

## 3. Columns

Schema of record (Toucan v2), plus one **new recommended column**
(`Depth_Basis`, §4):

| Column | Type | On rows | Meaning / guidance |
|---|---|---|---|
| `Type` | TEXT | all | `DSU` or `Tract` (case-insensitive). |
| `DSU_Num` | TEXT | DSU | Unit identifier — becomes the display/deal name (`DSU 31`, `DSU 12-15`). Keep unique within the file. |
| `Section`, `Block`, `County`, `Aliquot` | TEXT | Tract | Legal location; shown on the tract line in narvi. |
| `Min_Depth`, `Max_Depth` | TEXT | both | Depth rights. **Numeric feet TVD strongly preferred** — see §4. |
| `Depth_Basis` | TEXT | both | **NEW.** Where the depth numbers come from — see §4. |
| `Gross_Ac`, `Net_Ac` | REAL | Tract | Acreage. |
| `Tract_WI`, `Tract_NRI` | REAL | Tract | Working / net revenue interest, fraction (0–1). |
| `DSU_WI`, `DSU_NRI` | REAL | DSU | Unit-level rolled WI/NRI, fraction (0–1). |

Extra columns are harmless — they ride along into anduin's attribute store
verbatim.

## 4. Depth guidance — the part that matters most

The engineering apps **never compute on depth text**. Whatever is written in
`Min_Depth`/`Max_Depth` is displayed verbatim on the parcel card, labeled
*declared (uncorrelated)*; the engineer then enters a correlated numeric
window that actually drives bench screening. Two things make the declared
values dramatically more useful:

1. **Write numeric feet TVD (from surface) whenever possible.**
   `9950` — not `9,515'`, not `100' above Top of Wolfcamp`. Prose is legal
   and will be displayed, but it can never pre-populate anything.
   `Surface` is fine for `Min_Depth`.

2. **Say what the number is, in `Depth_Basis`:**

   | Value | Meaning |
   |---|---|
   | `log-correlated` | Depth was correlated by a geologist to logs **on or immediately offsetting the parcels**. Trustworthy locally. |
   | `ref-log` | Depth is a stratigraphic-equivalent pick on a named reference log that may be miles away. Include the log/well and distance in the cell or alongside (e.g. `ref-log: Smith 34-1, 17 mi NW`). |
   | `lease-language` | Verbatim from the lease/assignment (often prose). |

   Why this matters — the Toucan case: the lease-declared `9,515'` is the
   pick on a reference log **17 miles away**; correlated to the Toucan
   parcels it is **~9,950 ft**. A 400-ft error at the Bone Spring/Wolfcamp
   boundary flips benches in and out of the deal. Depths marked
   `log-correlated` are the ones engineering can eventually use directly
   (planned: auto-prefill of narvi's depth window from correlated numeric
   depths — still soft/overridable); everything else stays a manual step.

## 5. What each app does with the file

| App | Behavior |
|---|---|
| **narvi** (inventory planning) | `DSU` rows become selectable parcels named from `DSU_Num`; `Tract` rows attach to their DSU and show on the deal-terms card (WI/NRI, depth text). Declared depths display verbatim; the engineer's correlated window soft-flags out-of-window benches. |
| **erebor** (deal valuation) | `DSU` rows display as reference polygons with `DSU_Num` labels (zoom-to-deal). Display only — selection is always a manual lasso/box. |
| **anduin** (type curves) | **Every** row (DSU and Tract) persists with all attributes queryable; polygons render on the Map/Review tabs, toggle by source file. Re-upload with the same filename replaces. |

## 6. QGIS export walkthrough

Starting from the template (`docs/templates/dsu_tract_template.gpkg`):

1. Copy the template file, rename it to the deal (`<Deal>.gpkg`).
2. In QGIS: *Layer → Add Layer → Add Vector Layer* → the copied file. The
   layer arrives with the full column set and one example DSU + tract row.
3. Rename the layer to the deal name (right-click → *Rename Layer*, then
   *Export → Save Features As…* → GeoPackage, layer name = deal name — or
   just work in the template layer; the layer name is cosmetic).
4. Toggle editing, delete the example rows, digitize/paste the real tracts
   and DSUs, fill the attribute table.
5. Check before sending: CRS shows a real EPSG (4326 preferred); every DSU
   row has `Type=DSU` + `DSU_Num`; every tract sits inside its DSU outline;
   depths numeric where you have them + `Depth_Basis` set.

Starting from an existing layer instead: *Export → Save Features As…* →
format **GeoPackage**, CRS EPSG:4326, layer name = deal name — then add any
missing columns from §3.

---

*Template file:* `docs/templates/dsu_tract_template.gpkg`
(regenerate with `python -m scripts.make_gpkg_template`).
*App-side parsing contract:* the `gpkg_reader.py` module in each app repo
(canonical copy: narvi `src/narvi/gpkg_reader.py`).
