"""BOX sticks: one generation run from the warehouse to a stored set (plan phase 4; sql/73).

    python -m scripts.box_sticks_run pull     --run <dir>                       # read-only; a NEW, empty run dir
    python -m scripts.box_sticks_run generate --run <dir> --basin delaware|midland
    python -m scripts.box_sticks_run store    --run <dir> --basin <b> [--check N] [--go]
    python -m scripts.box_sticks_run record   --set-id <n> [--go]               # make a stored set its basin's record

pull      reads every warehouse input once into <dir>/cache (never reused: a run dir is one pull), puts every frame in key
          order (no pull has an ORDER BY and several tie-breaks follow row order), and writes manifest.json: the pull time
          taken AT the database, the tag rule run live at the pull (refused if it changed during the pull), row counts
          and digests per input, extent ids, sha256 of every file input, code + narvi SHAs. Missing file input = failure.
generate  runs box.sticks over every DSU of the basin. Any DSU error fails the run (nothing drops out silently). Writes
          set_<basin>.pkl (sticks + the generator's inputs as sql/73 rows) and the phase-3 style files.
store     carries location ids from the basin's record set (the latest stored set while there is no record), writes
          box.location_set + box.location + box.location_stick + box.location_set_dsu / _bench / _well in ONE transaction,
          verifies by identity, regenerates DSUs from the STORED rows and compares, then ROLLS BACK unless --go.
          The set is stored NOT record; the record flip is a separate explicit go.
record    makes one stored set the record of its basin: the basin's previous record (if any) is superseded by it, in the
          same transaction. Checked before and after; ROLLS BACK unless --go. No stick row is touched.

!! store --go writes box.* on whatever DB_* points at: explicit authorization required. Container first
(python -m scripts.box_rehearsal env). The generator does not forecast and holds no economics.
"""
from __future__ import annotations

import argparse
import dataclasses
import hashlib
import json
import subprocess
import time
from collections import Counter
from pathlib import Path

import numpy as np
import pandas as pd
import shapely
from pyproj import Transformer

from box.sticks import checks, core, reads, store
from box.sticks import identity as idn
from dealintake import geo

ROOT = Path(__file__).resolve().parent.parent
KEYS = {"wells": ["api10"], "sticks": ["stick_id"], "extents": ["basin", "bench"], "pads": ["pad_id"], "rule": ["api10"],
        "p2a_well_geom": ["api10"], "p2a_stick_geom": ["stick_id"], "p3_preprod": ["api10"], "p2b_stick_status": ["stick_id"],
        "p2b_record": ["stick_id"], "p5_uturn": ["api10"]}
PLACES = ("wells", "extents", "pads", "p2a_well_geom", "p3_preprod", "p5_uturn")          # the inputs that place sticks; the rest feed reports
SOURCES = {"wells": "curated.wells_enriched + curated.well_lateral_survey (producing horizontals)", "extents": "box.extent WHERE is_record",
           "pads": "raw_novi_intel.pads", "p2a_well_geom": "curated.wells_enriched (lateral geometry)",
           "p3_preprod": "curated.wells_enriched (not producing: Spud / DUC / Completed / Inactive / Active, or Permit Approved with a spud date)",
           "p5_uturn": "curated.well_lateral_survey (survey paths of real U-turn wells)", "sticks": "curated.intel_locations (reports only)",
           "rule": "curated.formation_tag_rule (reports only)", "p2a_stick_geom": "curated.intel_locations (reports only)",
           "p2b_stick_status": "curated.reconciled_inventory (reports only)", "p2b_record": "box record runs (reports only)"}
_TAG_SQL = "SELECT run_id, policy_digest FROM meta.formation_tag_run WHERE status = 'written' ORDER BY run_id DESC LIMIT 1"


def _sha_file(p: Path) -> str:
    return hashlib.sha256(p.read_bytes()).hexdigest()


def _sha_frame(df: pd.DataFrame) -> str:
    d = df.drop(columns=[c for c in df.columns if c == "geom"])               # shapely objects; the WKT column carries the geometry
    d = d.apply(lambda s: s.map(lambda v: json.dumps(v, default=str) if isinstance(v, list | tuple | dict | np.ndarray) else v))
    return hashlib.sha256(pd.util.hash_pandas_object(d, index=False).to_numpy().tobytes()).hexdigest()


def _git(*a: str) -> str:
    return subprocess.run(["git", *a], capture_output=True, text=True, check=True, cwd=ROOT).stdout.strip()


def narvi_sha() -> tuple[str, str | None]:
    """(the pinned commit in requirements-dealintake.txt, the installed commit or None)."""
    import importlib.metadata as md
    pin = next(ln.split("@")[-1].strip() for ln in (ROOT / "requirements-dealintake.txt").read_text(encoding="utf-8").splitlines() if ln.startswith("narvi @"))
    try:
        inst = json.loads(md.distribution("narvi").read_text("direct_url.json") or "{}").get("vcs_info", {}).get("commit_id")
    except Exception:  # noqa: BLE001
        inst = None
    return pin, inst


def file_inputs() -> dict[str, Path]:
    from scripts import box_sticks_phase1c as p1c
    from scripts import box_sticks_phase2a as p2a
    cfg_dir = ROOT / ".claude" / "skills" / "deal-intake" / "config"
    return {"wcxy_extent": p2a.WCXY_FILE, "thickness_rank": p1c.THICK_RANK, "far_rank": p1c.FAR_RANK, "direct_holdout": p1c.THICK_RANK.parent / "holdout_direct.csv",
         "strat_column": cfg_dir / "strat_column.yaml", "thresholds": cfg_dir / "thresholds.yaml"}


def thresholds(basin: str) -> dict:
    """Every constant that moves a stick, by name (the cfg column of box.location_set)."""
    from box import landing_surfaces as ls
    from scripts import box_sticks_phase1b as p1b
    from scripts import box_sticks_phase1c as p1c
    from scripts import box_sticks_phase2a as p2a
    from scripts import box_sticks_phase2a_bands as bands
    from scripts import box_sticks_phase2a_surface as sf
    from scripts import box_sticks_phase3_pilot as p3
    from scripts import box_sticks_phase3_regional as rg

    def consts(mod, names: tuple[str, ...]) -> dict:
        return {n: getattr(mod, n) for n in names}

    out = {"generator": dataclasses.asdict(reads.default_cfg(basin)), "identity": {"corridor_ft": idn.CORRIDOR_FT, "min_share": idn.MIN_SHARE},
           "reads": {"SEARCH_FT": 2640.0, "SEP_MIN_DSU": reads.SEP_MIN_DSU},
           "landing_surface": dataclasses.asdict(ls.PARAMS),
           "chain": consts(p1c, ("MIN_SEP_FT", "SCREEN_FT", "SCREEN_MIN_N", "MISTAG_MIN_FT", "BW_FT", "GRID_FT", "LEVEL_MIN_N", "VALLEY", "SECOND_SEP_FT",
                                 "SECOND_SHARE", "THICK_RULE")) | {"CHAIN_DIRECT_ONLY": sorted(map(list, p1c.CHAIN_DIRECT_ONLY))}
           | consts(p1b, ("K_NEAREST", "MIN_SAMPLES", "MIN_SPAN_FT", "RANK_AT_MI", "MIN_PREDICTED")),
           "spacing": consts(p2a, ("SAMPLES", "SENTINEL_FT", "CODEV_DAYS", "ASOF_SLACK_DAYS", "STAGGER_FT", "FLOOR_FT", "CAP_GUESS_FT")) | {"SINCE": str(p2a.SINCE)}
           | consts(bands, ("BANDS_MI", "BAND_MIN", "ALONG_MI")) | {"CUT_SIGMA": sf.CUT_SIGMA, "BLEND_COL": p3.BLEND_COL},
           "regional": consts(rg, ("WCA_THRESHOLD", "RADIUS_MI", "MIN_LATERAL_FT", "CELL_MI", "CODEV_MIN_EACH")),
           "frame": consts(p3, ("MEMBER_FRAC", "TWO_MIN_WELLS", "TWO_MIN_SEP_FT", "TWO_MIN_SIDE", "TWO_TIGHT"))}
    return json.loads(json.dumps(out, default=str))


# ----------------------------------------------------------------------------
# pull
# ----------------------------------------------------------------------------


def pull(run: Path) -> dict:
    from box import tag_scoreboard as sb
    from etl.db import get_connection
    from scripts import box_sticks_phase0 as p0
    from scripts import box_sticks_phase2a as p2a
    from scripts import box_sticks_phase2b as p2b
    from scripts import box_sticks_phase3_pilot as p3

    cache = run / "cache"
    if cache.exists() and any(cache.iterdir()):
        raise SystemExit(f"{cache} is not empty: a run dir is one pull, never reused")
    files = file_inputs()
    missing = [str(p) for p in files.values() if not p.exists()]
    if missing:
        raise SystemExit(f"file input(s) missing: {missing}")
    cache.mkdir(parents=True, exist_ok=True)
    with get_connection() as conn:
        t0 = sb._read(conn, "SELECT now() AS t", {})["t"].iloc[0]
        tag0 = sb._read(conn, _TAG_SQL, {}).iloc[0]
        sw = sb._read(conn, "SELECT use_rule FROM ref.formation_tag_switch", {})["use_rule"].iloc[0]
    p0.pull(cache)
    p2a.pull_geoms(cache)
    p3.pull_preprod(cache)
    p3.pull_uturn(cache)
    p2b.pull_stick_status(cache)
    with get_connection() as conn:
        t1 = sb._read(conn, "SELECT now() AS t", {})["t"].iloc[0]
        tag1 = sb._read(conn, _TAG_SQL, {}).iloc[0]
    if int(tag0["run_id"]) != int(tag1["run_id"]):
        raise SystemExit(f"the tag rule ran during the pull (run {tag0['run_id']} -> {tag1['run_id']}): pull again into a new run dir")
    rel = {}
    for name, key in KEYS.items():
        f = cache / f"{name}.pkl"
        df = pd.read_pickle(f)
        if name in PLACES and df[key].duplicated().any():
            raise SystemExit(f"{name}: duplicate key {key}")
        df = df.sort_values(key, kind="mergesort").reset_index(drop=True)
        df.to_pickle(f)
        rel[name] = {"rows": len(df), "sha256": _sha_frame(df), "source": SOURCES[name], "places_sticks": name in PLACES}
    ext = pd.read_pickle(cache / "extents.pkl")
    pin, inst = narvi_sha()
    man = {"pulled_at": pd.Timestamp(t0).isoformat(), "pull_finished_at": pd.Timestamp(t1).isoformat(), "tag_run_id": int(tag0["run_id"]),
           "tag_policy_digest": str(tag0["policy_digest"]), "tag_switch_use_rule": bool(sw), "dsu_vintage": p0.PAD_VINTAGE, "relations": rel,
           "extents": {f"{r.basin}/{r.bench}": int(r.extent_id) for r in ext.itertuples()},
           "files": {k: {"path": p.relative_to(ROOT).as_posix(), "sha256": _sha_file(p)} for k, p in files.items()},
           "code_sha": _git("rev-parse", "HEAD"), "code_dirty": bool(_git("status", "--porcelain")), "narvi_sha": pin, "narvi_installed": inst}
    (run / "manifest.json").write_text(json.dumps(man, indent=1), encoding="utf-8")
    F = p3.build_frame(cache)
    print(f"pulled {man['pulled_at']} (tag run {man['tag_run_id']}): {len(F['pads']):,} DSUs, {len(F['db']):,} DSU x bench, {len(F['u']):,} producers, "
          f"{len(F['pre']):,} not yet producing", flush=True)
    return man


# ----------------------------------------------------------------------------
# generate
# ----------------------------------------------------------------------------


def generate(run: Path, basin: str, limit: int | None = None) -> dict:
    man = json.loads((run / "manifest.json").read_text(encoding="utf-8"))
    for k, f in man["files"].items():
        if _sha_file(ROOT / f["path"]) != f["sha256"]:
            raise SystemExit(f"file input {k} changed since the pull")
    ctx = reads.Context(run / "cache")
    pads = ctx.pads[ctx.pads["basin"] == basin]
    with_bench = set(ctx.F["db"]["pad_id"])
    ids = [int(p) for p in pads.index if p in with_bench][:limit]
    link, cfg = reads.link_fn(), reads.default_cfg(basin)
    to_ll = Transformer.from_crs(f"EPSG:{geo.NARVI_WORK_EPSG}", "EPSG:4326", always_xy=True)
    screen = dict(zip(ctx.F["u"]["api10"].astype(str), ctx.F["u"]["screen"], strict=True)) if "screen" in ctx.F["u"] else {}
    sticks, drows, brows, wells, errors = [], [], [], {}, []
    viol: Counter = Counter()
    reasons: Counter = Counter()
    t0 = time.time()
    for n, pid in enumerate(ids, 1):
        try:
            d = ctx.dsu(pid)
            res = core.generate_dsu(d, cfg, link)
            for k, v in checks.run_all(res, d, cfg, link).items():
                viol[k] += len(v)
        except Exception as e:  # noqa: BLE001
            errors.append(f"{pid}: {type(e).__name__}: {e}")
            continue
        sticks += res.sticks
        drows.append(store.dsu_row(d, res))
        brows += store.bench_rows(d, res)
        reasons.update(r["reason"] for r in res.ledger if r["status"] == "culled")
        for w in store.well_rows(d):
            if w["api10"] not in wells:
                g = shapely.transform(w.pop("line"), lambda c: np.column_stack(to_ll.transform(c[:, 0], c[:, 1])))
                wells[w["api10"]] = w | {"wkt": shapely.to_wkt(g, rounding_precision=-1), "screen": None if pd.isna(screen.get(w["api10"])) else screen.get(w["api10"])}
        if n % 500 == 0:
            print(f"{basin} {n}/{len(ids)} dsus, {len(sticks)} sticks, {time.time() - t0:.0f} s", flush=True)
    if errors or any(viol.values()):
        raise SystemExit(f"{basin}: {len(errors)} DSU error(s), violations {dict(viol)}; nothing written. First: {errors[:5]}")
    counts = {"dsus": len(drows), "dsus_with_no_bench": int(len(pads) - len(ids)), "dsu_bench": len(brows), "sticks": len(sticks),
              "legs": sum(int(s["n_legs"]) for s in sticks), "completed_lateral_ft": round(sum(float(s["completed_lateral_ft"]) for s in sticks), 1),
              "by_rung": dict(Counter(s["tvd_basis"]["rung"] for s in sticks)), "by_well_type": dict(Counter(s["well_type"] for s in sticks)),
              "by_flag": dict(Counter(f for s in sticks for f in s["flags"])), "rows_culled": dict(reasons),
              "no_row_reason": dict(Counter(b["no_row_reason"] for b in brows if b["no_row_reason"])), "wells_read": len(wells),
              "violations": dict(viol), "errors": 0}
    out = {"basin": basin, "generator_version": core.VERSION, "manifest": man, "cfg": thresholds(basin), "counts": counts, "sticks": sticks, "dsu_rows": drows,
           "bench_rows": brows, "wells": wells}
    pd.to_pickle(out, run / f"set_{basin}.pkl")
    with (run / f"sticks_{basin}.jsonl").open("w", encoding="utf-8", newline="\n") as fh:
        for s in sticks:
            fh.write(json.dumps(s, sort_keys=True) + "\n")
    summ = {"generator_version": core.VERSION, "pulled": man["pulled_at"], "basin": basin, **counts, "seconds": round(time.time() - t0)}
    (run / f"summary_{basin}.json").write_text(json.dumps(summ, indent=1), encoding="utf-8")
    print(json.dumps(summ, indent=1), flush=True)
    return out


# ----------------------------------------------------------------------------
# store
# ----------------------------------------------------------------------------

_STICK_COLS = ("basin", "pad_id", "formation_blueox", "slot_no", "well_name", "well_type", "n_legs", "completed_lateral_ft", "drilled_lateral_ft",
               "turn_radius_ft", "turn_dls_deg_per_100ft", "turn_arc_ft", "azimuth_deg", "azimuth_grid_deg", "azimuth_basis", "gunbarrel_x_ft", "setback_ft",
               "target_tvd_ft", "tvd_rung", "tvd_anchor", "tvd_err_median_ft", "tvd_err_p90_ft", "tvd_reconciled_shift_ft", "second_level_tvd_ft",
               "spacing_ft", "spacing_map_ft", "spacing_grid", "spacing_n_eff", "spacing_weighted_median_ft", "spacing_band", "spacing_band_ft", "flags",
               "match_method", "match_share", "match_offset_ft")
_DSU_COLS = ("pad_id", "azimuth_deg", "azimuth_grid_deg", "azimuth_basis", "wca_class", "wca_dominant", "well_type", "straight_ft", "clear_width_ft",
             "long_wells", "drilled_across", "turn_at_high", "wells_read", "well_api10", "well_member", "sticks", "legs")
_BENCH_COLS = ("pad_id", "formation_blueox", "bench_rank", "inside_frac", "tvd_in_ft", "tvd_rung", "tvd_anchor", "tvd_err_median_ft", "tvd_err_p90_ft",
               "second_level_tvd_ft", "two_landings", "spacing_map_ft", "no_row_reason", "target_tvd_ft", "reconciled_shift_ft", "spacing_final_ft", "grid",
               "pinned", "rows_considered", "legs_placed", "sticks")


def _py(v: object) -> object:
    if isinstance(v, np.generic):
        v = v.item()
    return None if isinstance(v, float) and np.isnan(v) else v


def _prev_set(q, basin: str) -> int | None:
    r = q("SELECT set_id FROM box.location_set WHERE basin = %s ORDER BY is_record DESC, set_id DESC LIMIT 1", (basin,)).fetchone()
    return None if r is None else int(r[0])


def write_set(cur, art: dict, backtest: dict, notes: str | None) -> tuple[int, dict]:
    """Insert one set inside the caller's transaction. Returns (set_id, crosswalk counts)."""
    from psycopg.types.json import Jsonb

    q, basin, man = cur.execute, art["basin"], art["manifest"]
    prev = _prev_set(q, basin)
    sticks = art["sticks"]
    new = [store.identity_stick(s) for s in sticks]
    if prev is None:
        slot = idn.seed(new)
        plan = {s["well_name"]: (None, slot[s["well_name"]], "seed", None, None) for s in sticks}
        xw = {"carried": 0, "new": len(sticks), "stopped": 0, "method": "seed"}
    else:
        rows = q("SELECT k.location_id, k.detail, k.slot_no FROM box.location_stick k WHERE k.set_id = %s", (prev,)).fetchall()
        used = {(int(a), b): int(m) for a, b, m in q("SELECT pad_id, formation_blueox, max(slot_no) FROM box.location WHERE source = 'box_sticks' AND basin = %s "
                                                     "AND dsu_vintage = %s GROUP BY 1, 2", (basin, man["dsu_vintage"])).fetchall()}
        x = idn.crosswalk([store.identity_stick(d, key=str(lid), slot=int(sl)) for lid, d, sl in rows], new, used=used)   # numbers are never reused, across every set
        plan = {nk: (int(pk), sl, "overlap", sh, off) for nk, (pk, sl, sh, off) in x["carried"].items()}
        plan |= {nk: (None, sl, "new", None, None) for nk, sl in x["new"].items()}
        xw = {"carried": len(x["carried"]), "new": len(x["new"]), "stopped": len(x["stopped"]), "method": "overlap", "prev_set_id": prev,
              "corridor_ft": idn.CORRIDOR_FT, "min_share": idn.MIN_SHARE}
    sid = q("INSERT INTO box.location_set (basin, generator_version, code_sha, narvi_sha, dsu_vintage, pulled_at, tag_run_id, tag_policy_digest, cfg, inputs, "
            "counts, backtest, prev_set_id, crosswalk, notes) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s) RETURNING set_id",
            (basin, art["generator_version"], man["code_sha"], man["narvi_sha"], man["dsu_vintage"], man["pulled_at"], man["tag_run_id"],
             man["tag_policy_digest"], Jsonb(art["cfg"]), Jsonb({"relations": man["relations"], "extents": man["extents"], "files": man["files"],
                                                                 "pull_finished_at": man["pull_finished_at"], "narvi_installed": man["narvi_installed"]}),
             Jsonb(art["counts"]), Jsonb(backtest), prev, Jsonb(xw), notes)).fetchone()[0]
    srows = [store.stick_row(s, *plan[s["well_name"]][1:]) for s in sticks]
    fresh = [(r, s) for r, s in zip(srows, sticks, strict=True) if plan[s["well_name"]][0] is None]
    ids: list[int] = []
    if fresh:
        cur.executemany(
            "INSERT INTO box.location (basin, formation_blueox, geom, lateral_ft, source, dsu_vintage, pad_id, slot_no, first_seen_set, last_seen_set) "
            "VALUES (%s, %s, extensions.ST_GeomFromText(%s, 4326), %s, 'box_sticks', %s, %s, %s, %s, %s) RETURNING location_id",
            [(basin, r["formation_blueox"], r["legs_wkt"], r["completed_lateral_ft"], man["dsu_vintage"], r["pad_id"], r["slot_no"], sid, sid) for r, _ in fresh],
            returning=True)
        while True:
            ids.append(cur.fetchone()[0])
            if not cur.nextset():
                break
    new_id = {s["well_name"]: i for (_, s), i in zip(fresh, ids, strict=True)}
    carried = [(r["legs_wkt"], r["completed_lateral_ft"], sid, plan[s["well_name"]][0]) for r, s in zip(srows, sticks, strict=True) if plan[s["well_name"]][0]]
    if carried:
        cur.executemany("UPDATE box.location SET geom = extensions.ST_GeomFromText(%s, 4326), lateral_ft = %s, last_seen_set = %s WHERE location_id = %s "
                        "AND source = 'box_sticks'", carried)
    cols = ", ".join(_STICK_COLS)
    cur.executemany(
        f"INSERT INTO box.location_stick (set_id, location_id, legs_geom, turn_geom, detail, {cols}) VALUES (%s, %s, extensions.ST_GeomFromText(%s, 4326), "
        f"extensions.ST_GeomFromText(%s, 4326), %s, {', '.join(['%s'] * len(_STICK_COLS))})",
        [(sid, plan[s["well_name"]][0] or new_id[s["well_name"]], r["legs_wkt"], r["turn_wkt"], Jsonb(r["detail"] | {"well_name": r["well_name"]}),
          *[_py(r[c]) for c in _STICK_COLS]) for r, s in zip(srows, sticks, strict=True)])
    cur.executemany(f"INSERT INTO box.location_set_dsu (set_id, {', '.join(_DSU_COLS)}) VALUES (%s, {', '.join(['%s'] * len(_DSU_COLS))})",
                    [(sid, *[_py(r[c]) for c in _DSU_COLS]) for r in art["dsu_rows"]])
    cur.executemany(f"INSERT INTO box.location_set_bench (set_id, spacing_basis, rows_culled, {', '.join(_BENCH_COLS)}) VALUES (%s, %s, %s, "
                    f"{', '.join(['%s'] * len(_BENCH_COLS))})",
                    [(sid, Jsonb(r["spacing_basis"]), Jsonb(r["rows_culled"]), *[_py(r[c]) for c in _BENCH_COLS]) for r in art["bench_rows"]])
    cur.executemany("INSERT INTO box.location_set_well (set_id, api10, formation_blueox, depth_ft, status, planned, screen, geom) VALUES (%s, %s, %s, %s, %s, %s, "
                    "%s, extensions.ST_GeomFromText(%s, 4326))",
                    [(sid, k, w["formation_blueox"], w["depth_ft"], w["status"], w["planned"], w["screen"], w["wkt"]) for k, w in art["wells"].items()])
    return int(sid), xw


def verify_set(cur, sid: int, art: dict, xw: dict, check: int | None) -> list[str]:
    """Identity checks on the stored set, then DSUs regenerated from the STORED rows against the stored sticks."""
    q, basin, bad = cur.execute, art["basin"], []

    def ck(ok: bool, msg: str) -> None:
        print(f"    {'ok  ' if ok else 'FAIL'} {msg}", flush=True)
        if not ok:
            bad.append(msg)

    n = {t: q(f"SELECT count(*) FROM box.{t} WHERE set_id = %s", (sid,)).fetchone()[0] for t in ("location_stick", "location_set_dsu", "location_set_bench", "location_set_well")}
    c = art["counts"]
    ck(n["location_stick"] == c["sticks"], f"box.location_stick rows = generated sticks ({n['location_stick']:,} = {c['sticks']:,})")
    ck(n["location_set_dsu"] == c["dsus"] and n["location_set_bench"] == c["dsu_bench"] and n["location_set_well"] == c["wells_read"],
       f"DSU / DSU x bench / well rows = generated ({n['location_set_dsu']:,} / {n['location_set_bench']:,} / {n['location_set_well']:,})")
    seen = q("SELECT count(*), count(*) FILTER (WHERE first_seen_set = %s), min(location_id) FROM box.location WHERE source = 'box_sticks' AND last_seen_set = %s",
             (sid, sid)).fetchone()
    ck(seen[0] == c["sticks"] and seen[1] == xw["new"], f"locations last seen in the set = sticks; first seen in it = new ids ({seen[0]:,}; {seen[1]:,} = {xw['new']:,})")
    ck(seen[2] is None or seen[2] >= 10_000_001, f"every BOX stick id >= 10,000,001 (min {seen[2]})")
    ck(q("SELECT count(*) FROM box.location_stick k JOIN box.location l USING (location_id) WHERE k.set_id = %s AND (l.source <> 'box_sticks' OR l.pad_id <> k.pad_id "
         "OR l.formation_blueox <> k.formation_blueox OR l.slot_no <> k.slot_no OR l.basin <> k.basin)", (sid,)).fetchone()[0] == 0,
       "every stick agrees with its location on DSU, bench, slot and basin")
    ck(q("SELECT count(*) FROM box.location_stick WHERE set_id = %s AND abs(extensions.ST_Length(legs_geom::extensions.geography) * 3.280839895 - completed_lateral_ft) "
         "> 0.005 * completed_lateral_ft + 5", (sid,)).fetchone()[0] == 0, "stored leg geometry length = completed lateral (0.5 % + 5 ft)")
    ck(q("SELECT count(*) FROM box.location_stick WHERE set_id = %s AND tvd_err_median_ft IS NULL", (sid,)).fetchone()[0] == 0, "every stick carries an expected depth error")
    ck(q("SELECT count(*) FROM box.location_set_bench b WHERE b.set_id = %s AND b.sticks <> (SELECT count(*) FROM box.location_stick k WHERE k.set_id = b.set_id "
         "AND k.pad_id = b.pad_id AND k.formation_blueox = b.formation_blueox)", (sid,)).fetchone()[0] == 0, "DSU x bench stick counts = the stick rows")
    ck(q("SELECT is_record FROM box.location_set WHERE set_id = %s", (sid,)).fetchone()[0] is False, "the set is stored NOT record")

    # regenerate from the stored rows alone (+ the DSU polygons of the set's vintage). float8 must come back exact: the
    # Supabase pooler session reads with extra_float_digits = 0 (15 digits), which is not the stored value.
    q("SET LOCAL extra_float_digits = 1")
    pads = [int(r[0]) for r in q("SELECT pad_id FROM box.location_set_dsu WHERE set_id = %s ORDER BY pad_id", (sid,)).fetchall()]
    if check is not None:
        pads = pads[:: max(1, len(pads) // max(check, 1))][:check]
    to_work = Transformer.from_crs("EPSG:3083", f"EPSG:{geo.NARVI_WORK_EPSG}", always_xy=True)
    ll_work = Transformer.from_crs("EPSG:4326", f"EPSG:{geo.NARVI_WORK_EPSG}", always_xy=True)

    def tr(g, t):
        return shapely.transform(g, lambda c: np.column_stack(t.transform(c[:, 0], c[:, 1])))

    vintage = q("SELECT dsu_vintage FROM box.location_set WHERE set_id = %s", (sid,)).fetchone()[0]
    poly = dict(q("SELECT pad_id, extensions.ST_AsText(extensions.ST_Transform(geom, 3083)) FROM raw_novi_intel.pads WHERE report_version = %s AND pad_id = ANY(%s)",
                  (vintage, pads)).fetchall())
    wl = {r[0]: {"formation_blueox": r[1], "depth_ft": r[2], "status": r[3], "planned": r[4], "line": tr(shapely.from_wkt(r[5]), ll_work)}
          for r in q("SELECT api10, formation_blueox, depth_ft, status, planned, extensions.ST_AsText(geom) FROM box.location_set_well WHERE set_id = %s", (sid,)).fetchall()}
    dcols, bcols = list(_DSU_COLS), [*_BENCH_COLS, "spacing_basis"]
    drows = {r[0]: dict(zip(dcols, r, strict=True)) for r in q(f"SELECT {', '.join(dcols)} FROM box.location_set_dsu WHERE set_id = %s AND pad_id = ANY(%s)", (sid, pads)).fetchall()}
    brows: dict[int, list] = {}
    for r in q(f"SELECT {', '.join(bcols)} FROM box.location_set_bench WHERE set_id = %s AND pad_id = ANY(%s)", (sid, pads)).fetchall():
        brows.setdefault(r[0], []).append(dict(zip(bcols, r, strict=True)))
    stored: dict[int, list] = {}
    for pid, det in q("SELECT pad_id, detail FROM box.location_stick WHERE set_id = %s AND pad_id = ANY(%s)", (sid, pads)).fetchall():
        stored.setdefault(pid, []).append(det)
    link, cfg, diffs, t0 = reads.link_fn(), reads.default_cfg(basin), [], time.time()
    for pid in pads:
        d = store.rebuild_dsu(basin, tr(shapely.from_wkt(poly[pid]), to_work), drows[pid], brows.get(pid, []), wl, stored.get(pid, []))
        res = core.generate_dsu(d, cfg, link)
        # stored names carry the slot; compare on the generator's own name kept in detail
        a = [dict(s, well_name=s["generator_name"]) for s in stored.get(pid, [])]
        diffs += [f"{pid} {x}" for x in store.diff_sticks(a, res.sticks)]
    ck(not diffs, f"{len(pads):,} DSUs regenerated from the stored rows give the stored sticks ({len(diffs)} differences, {time.time() - t0:.0f} s)")
    for x in diffs[:10]:
        print(f"         {x}", flush=True)
    return bad


def cmd_store(run: Path, basin: str, go: bool, check: int | None, backtest: Path | None, notes: str | None) -> int:
    from etl.db import get_connection

    art = pd.read_pickle(run / f"set_{basin}.pkl")
    man = art["manifest"]
    for s in art["sticks"]:
        s["generator_name"] = s["well_name"]
    bt = {} if backtest is None else {"source": backtest.as_posix(), "sha256": _sha_file(backtest), "summary": json.loads(backtest.read_text(encoding="utf-8"))}
    if go and (man["code_dirty"] or man["narvi_installed"] != man["narvi_sha"] or not bt):
        raise SystemExit("refusing --go: the run was built from a dirty tree, the installed narvi is not the pinned commit, or no --backtest was given")
    conn = get_connection()
    try:
        with conn.cursor() as cur:
            print(f"target {cur.execute('select inet_server_addr(), inet_server_port(), current_database()').fetchone()}", flush=True)
            if cur.execute("SELECT to_regclass('box.location_set')").fetchone()[0] is None:
                raise SystemExit("box.location_set does not exist here: sql/73 is not applied")
            t0 = time.time()
            sid, xw = write_set(cur, art, bt, notes)
            print(f"set {sid} ({basin}, {art['generator_version']}): {art['counts']['sticks']:,} sticks; ids {xw} ({time.time() - t0:.0f} s)", flush=True)
            bad = verify_set(cur, sid, art, xw, check)
            if bad or not go:
                conn.rollback()
                print(f"ROLLED BACK ({len(bad)} check(s) failed)" if bad else "dry run: ROLLED BACK (pass --go to keep it)", flush=True)
                return 1 if bad else 0
            conn.commit()
            print(f"STORED set {sid} (not record)", flush=True)
            return 0
    finally:
        conn.close()


def flip_record(cur, sid: int) -> tuple[list[str], dict]:
    """Make set `sid` its basin's record inside the caller's transaction. Returns (failed checks, what happened)."""
    q, bad = cur.execute, []

    def ck(ok: bool, msg: str) -> None:
        print(f"    {'ok  ' if ok else 'FAIL'} {msg}", flush=True)
        if not ok:
            bad.append(msg)

    row = q("SELECT basin, is_record, generator_version, (counts->>'sticks')::int, counts->'violations', counts->>'errors' FROM box.location_set WHERE set_id = %s",
            (sid,)).fetchone()
    if row is None:
        raise SystemExit(f"box.location_set has no set {sid}")
    basin, was, version, n_sticks, viol, errs = row
    ck(not was, f"set {sid} ({basin}, {version}) is not the record yet")
    n = q("SELECT count(*), count(DISTINCT location_id) FROM box.location_stick WHERE set_id = %s", (sid,)).fetchone()
    ck(n[0] == n_sticks == n[1], f"its stick rows = the count it was stored with ({n[0]:,} = {n_sticks:,}), one location each")
    ck(q("SELECT count(*) FROM box.location_stick k LEFT JOIN box.location l ON l.location_id = k.location_id AND l.source = 'box_sticks' AND l.basin = %s "
         "WHERE k.set_id = %s AND l.location_id IS NULL", (basin, sid)).fetchone()[0] == 0, "every stick has its BOX stick location in the basin")
    ck(not any((viol or {}).values()) and str(errs) == "0", "the set was generated with 0 invariant violations and 0 DSU errors")
    before = q("SELECT md5(string_agg(set_id::text || location_id::text || well_name || target_tvd_ft::text, '' ORDER BY set_id, location_id)) FROM box.location_stick").fetchone()[0]
    prev = [int(r[0]) for r in q("SELECT set_id FROM box.location_set WHERE basin = %s AND is_record", (basin,)).fetchall()]
    q("UPDATE box.location_set SET is_record = false, superseded_by = %s WHERE basin = %s AND is_record", (sid, basin))
    q("UPDATE box.location_set SET is_record = true WHERE set_id = %s", (sid,))
    rec = dict(q("SELECT basin, array_agg(set_id ORDER BY set_id) FROM box.location_set WHERE is_record GROUP BY 1").fetchall())
    ck(rec.get(basin) == [sid], f"the {basin} record is set {sid} and only it ({rec})")
    ck(all(q("SELECT superseded_by FROM box.location_set WHERE set_id = %s", (p,)).fetchone()[0] == sid for p in prev), f"previous {basin} record(s) {prev} superseded by {sid}")
    after = q("SELECT md5(string_agg(set_id::text || location_id::text || well_name || target_tvd_ft::text, '' ORDER BY set_id, location_id)) FROM box.location_stick").fetchone()[0]
    ck(before == after, "no stick row changed")
    return bad, {"basin": basin, "previous": prev}


def cmd_record(sid: int, go: bool) -> int:
    from etl.db import get_connection

    conn = get_connection()
    conn.autocommit = False
    try:
        with conn.cursor() as cur:
            print(f"target {cur.execute('select inet_server_addr(), inet_server_port(), current_database()').fetchone()}", flush=True)
            bad, what = flip_record(cur, sid)
            if bad or not go:
                conn.rollback()
                print(f"ROLLED BACK ({len(bad)} check(s) failed)" if bad else "dry run: ROLLED BACK (pass --go to keep it)", flush=True)
                return 1 if bad else 0
            conn.commit()
            print(f"RECORD: set {sid} is the {what['basin']} record", flush=True)
            return 0
    finally:
        conn.close()


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    for name in ("pull", "generate", "store"):
        p = sub.add_parser(name)
        p.add_argument("--run", required=True, type=Path)
        if name != "pull":
            p.add_argument("--basin", required=True, choices=("delaware", "midland"))
    sub.choices["generate"].add_argument("--limit", type=int, default=None)
    s = sub.choices["store"]
    s.add_argument("--go", action="store_true", help="commit (explicit authorization required); default is a rolled-back dry run")
    s.add_argument("--check", type=int, default=None, help="regenerate only N DSUs from the stored rows (default: every DSU)")
    s.add_argument("--backtest", type=Path, default=None, help="the back-test summary json of this generator on this pull (required with --go)")
    s.add_argument("--notes", default=None)
    r = sub.add_parser("record")
    r.add_argument("--set-id", required=True, type=int)
    r.add_argument("--go", action="store_true", help="commit (explicit authorization required); default is a rolled-back dry run")
    a = ap.parse_args(argv)
    if a.cmd == "record":
        return cmd_record(a.set_id, a.go)
    if a.cmd == "pull":
        pull(a.run)
        return 0
    if a.cmd == "generate":
        generate(a.run, a.basin, a.limit)
        return 0
    return cmd_store(a.run, a.basin, a.go, a.check, a.backtest, a.notes)


if __name__ == "__main__":
    raise SystemExit(main())
