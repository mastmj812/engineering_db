BOX extents for geology review — 2026-10-07T17:54:53-05:00
================================================================

What this is
  Generated extents for the Blue Ox (BOX) basin-wide type curves, Delaware pilot benches:
  WCA, BS2_S. One extent = where BOX will forecast reconciled Novi PUDs from PDP data.
  Plan of record: engineering_db docs/box_type_curves_plan.md (step 3).

CRS
  NAD83 / UTM zone 14N, US-survey feet (no standard EPSG; .prj written from the ESRI definition
  NAD_1983_UTM_Zone_14N_ftUS — false easting 1,640,416.667 usft, CM -99). Coordinates are
  already projected, same frame as the HCA_* GGX grids.

What to edit
  BOX_<bench>_extent_v1.shp — the ONLY layer you edit. Move, cut or add polygon area.
  Keep the BENCH attribute. Save as BOX_<bench>_extent_v1_edited.shp (all side files).
  If you add a note for a change, put it in a new text field NOTE (any length up to 254).

What to look at (not edited)
  BOX_<bench>_edges_v1  boundary pieces; RULE = what set the buffer, FLAG = the question:
      "pinned edge, strong wells"  the edge is drilled up to and the last wells are strong:
                                   performance does not explain why it stops — what does?
      "live front"                 performing step-outs ahead of the body (buffer at the cap)
      "potash"                     inside the BLM Secretary's Potash Area: a surface constraint,
                                   not geology — the gap is not widened, never treated as a dry hole
      "pre-2016 ... not followed up" old laterals beyond a gap: buffer held to the floor
  BOX_<bench>_flags             holes in the drilled body (geology hole, surface, or fill?) and
                                step-outs left out of the extent (rolled / isolated / too new)
  BOX_<bench>_laterals          every pool lateral: ROLE, TVD_FT (producers' TVD — the W-edge
                                depth question), OIL12KFT (12-mo oil, bbl per 1,000 ft), QC_NOTE
  BOX_<bench>_ctx_struct / _ctx_isopach   contours from your HCA grids (context only)
  BOX_potash_SOPA               the potash ignore-gap polygon (1986 order boundary)

Buffer rule (parameters in the extent PARAMS attribute)
  pinned edge: floor = 880 ft (rolled) / 1,320 (unknown) / 1,760 (strong)
  gap: k x gap length x perf (strong 1.0 / unknown 0.75 / rolled 0.5), k = 0.75, within [floor, cap = 7,920 ft]
  pre-2016 laterals beyond a gap -> floor; live-front side -> cap; inside the potash area -> floor; holes -> tightest floor

Return
  The *_edited shapefile set (zip is fine) to Michael. It is re-imported, diffed against this
  version, and stored as the version of record; regeneration later produces a diff, never an
  overwrite of your edits.
