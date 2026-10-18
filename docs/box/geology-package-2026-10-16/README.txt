BOX bench extents of record — geology hand-off package (2026-10-16T13:57:17-05:00)

Frame: NAD83 / UTM zone 14N, US-survey feet (coordinates already projected; the .prj is written from the exact
definition). Read straight from the warehouse records (box.extent, is_record) on 2026-10-16T13:57:17-05:00.

THE EXTENTS (edit these)
  BOX_<bench>_extent_RECORD.shp   one per bench, the version of record today:
    AVA_0  extent_id 28  generated          259.1 sq mi
    AVA_1  extent_id 29  generated          548.0 sq mi
    AVA_2  extent_id 30  generated          623.6 sq mi
    BS1_S  extent_id 26  geology_edited   3,247.5 sq mi
    BS2_C  extent_id 20  geology_edited   1,524.6 sq mi
    BS2_S  extent_id 7   generated        3,358.5 sq mi
    BS3_C  extent_id 18  geology_edited   3,840.2 sq mi
    BS3_S  extent_id 16  geology_edited   4,998.3 sq mi
    WCA    extent_id 6   generated        6,168.7 sq mi
    WCB_1  extent_id 22  geology_edited   3,554.1 sq mi
    WCB_2  extent_id 24  geology_edited   3,036.7 sq mi
    WCC    extent_id 27  generated        1,454.8 sq mi
  SOURCE = generated: built by the BOX development-envelope rule (D27) from >= 2016 laterals.
  SOURCE = geology_edited: drawn by Michael over structure + laterals (owner edit, 2026-10-16).

CONTEXT (read only — for judging the edits)
  <bench>/BOX_<bench>_laterals     every bench lateral: ROLE, TVD_FT, OIL12KFT (12-mo oil, bbl per 1,000 ft), QC_NOTE
  <bench>/BOX_<bench>_ctx_struct   your HCA structure grid of the bench top, contoured (context only, D25)
  <bench>/BOX_<bench>_ctx_isopach  bench isopach from your grids (context only)
  <bench>/BOX_<bench>_flags        step-out tests left out, voids/holes filled — the questions behind the edge
  BOX_potash_SOPA                  BLM Secretary's Potash Area (surface constraint, not geology)

Benches not here: WCXY (decided with step 9), Delaware WDFD and WCD (emerging, worked by hand per deal),
Midland (later phase).

HOW TO RETURN EDITS
  Edit a BOX_<bench>_extent_RECORD shape (move the edge, add or cut area; multiple parts are fine), save it as
  BOX_<bench>_extent_edited.shp (same frame), and send the set back to Michael. Each returned bench is imported,
  diffed against the record (added / removed area by side, PUDs and laterals affected), reviewed, and stored as the
  new version of record; everything downstream is re-run on it. Your edit never silently overwrites anything: the
  current record stays in the history.
