"""BOX D84 — quarterly analog-pool refresh: bench QC + the class rule of record on NEW wells only.

Plan docs/box_type_curves_plan.md D84 (Michael, 2026-10-15): the analog pool learns from new producers through the
same step-1 pipeline that built the gate-1 set — the consensus detector (box/bench_qc.py), the ratified class rule
(box/qc_rule.py: class gate + sql/23 second vote + GOR veto + A-prime + no Bone Spring -> Wolfcamp; WCA pooled, nothing
promoted into WCXY, D19 / D20) — with NO calibration cards. Wells already judged keep their judgment:

  * the base set's rows are copied byte-for-byte; the refreshed ``wells_final_WCA.csv`` = the base file + appended rows,
    and ``verify_identity`` proves the base file is an exact byte prefix of the new one;
  * "new" = an api10 never judged before, NOT "not in the base file". Re-running the rule on old wells churns
    (2026-10-15, same data-through as gate 1: 122 frozen wells would now be decided out and 126 others in, mostly
    re-tags of wells first producing 2000-2025) — that is a re-litigation of gate 1, which D84 rules out.

The judged universe is recorded per refresh (``universe.csv``: api10 + the refresh that first judged it), so the next
refresh's "new" is an exact set difference. The gate-1 run did not record its universe; for a base without
``universe.csv`` it is reconstructed once as every api10 named in the base directory's CSVs plus every live producer
first producing on or before the newest first-production date in those CSVs (``reconstruct_seen``). Wells reported
late with an older first-production date are therefore counted as judged at gate 1; the count is stated.

BS2_S is not refreshed (v1 production is WCA only, D60): its set is copied byte-identical because the build's factor
step reads it from the same directory. ``docs/box/exclusions.csv`` stays a load-time filter (box/exclusions.py): new
rows in it are written and marked, and ``box_pud_run build`` drops them exactly as it drops the frozen ones.
"""

from __future__ import annotations

import datetime as dt
import hashlib
import html
import io
import json
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from box import exclusions
from box import qc_rule as qr
from box.flag_cards import NEVER_INTO, pool

POOL = "WCA"
WCA_TAGS: tuple[str, ...] = ("WCA_1", "WCA_2", "WCXY")
COPY_POOLS: tuple[str, ...] = ("BS2_S",)  # not refreshed (D60); copied so `build --wells <dir>` finds it
UNIVERSE = "universe.csv"
MANIFEST = "refresh.json"
NEW_WELLS = "new_wells.csv"
GATE1_DIR = Path("docs") / "box" / "step1-2026-10-06"


def final_name(pool_name: str) -> str:
    return f"wells_final_{pool_name}.csv"


# ----------------------------------------------------------------------------
# The judged universe
# ----------------------------------------------------------------------------


def reconstruct_seen(base_dir: Path, live: pd.DataFrame) -> tuple[pd.DataFrame, dict[str, Any]]:
    """(universe frame [api10, first_judged], meta) for a base directory.

    Recorded (``universe.csv`` present): read it. Otherwise (the gate-1 directory): api10s named in any of its CSVs, plus
    live producers first producing on or before the newest first-production date found there."""
    rec = base_dir / UNIVERSE
    if rec.exists():
        u = pd.read_csv(rec, dtype={"api10": str, "first_judged": str})
        return u, {"method": "recorded", "path": str(rec), "n": len(u)}
    named: set[str] = set()
    newest: dt.date | None = None
    for f in sorted(base_dir.glob("*.csv")):
        d = pd.read_csv(f, dtype={"api10": str}, low_memory=False)
        if "api10" not in d.columns:
            continue
        named |= set(d["api10"].dropna())
        if "first_production_date" in d.columns:
            fp = pd.to_datetime(d["first_production_date"], errors="coerce").max()
            if pd.notna(fp) and (newest is None or fp.date() > newest):
                newest = fp.date()
    if newest is None:
        raise ValueError(f"{base_dir}: no universe.csv and no first_production_date to reconstruct the judged universe from")
    by_fp = set(live.loc[[fp is not None and fp <= newest for fp in live["first_production_date"]], "api10"])
    ids = sorted(named | by_fp)
    meta = {
        "method": "reconstructed",
        "rule": f"api10 named in {base_dir}/*.csv, or a live producer first producing on or before {newest}",
        "fp_cut": str(newest), "n_named": len(named), "n_fp_cut": len(by_fp), "n": len(ids),
        "n_live_fp_cut_not_named": len(by_fp - named),
    }
    return pd.DataFrame({"api10": ids, "first_judged": base_dir.name}), meta


def next_universe(seen: pd.DataFrame, live: pd.DataFrame, label: str) -> pd.DataFrame:
    """Cumulative: everything judged before keeps its first_judged; live wells judged now for the first time get `label`.
    Wells that left the warehouse stay (judged is judged)."""
    new_ids = sorted(set(live["api10"]) - set(seen["api10"]))
    out = pd.concat([seen[["api10", "first_judged"]], pd.DataFrame({"api10": new_ids, "first_judged": label})], ignore_index=True)
    return out.sort_values("api10").reset_index(drop=True)


# ----------------------------------------------------------------------------
# Classing
# ----------------------------------------------------------------------------


def flag_class(row: pd.Series) -> tuple[str, str]:
    """(swap class 'FROM->TO' on pooled labels or '', standing under the class rule of record)."""
    if row.get("cons_status") != "flag" or not isinstance(row.get("cons_suggest"), str):
        return "", str(row.get("cons_status") or "no_position")
    tag, sug = str(row["formation_blueox"]), str(row["cons_suggest"])
    cls = f"{pool(tag)}->{pool(sug)}"
    if sug in NEVER_INTO:
        return cls, "into WCXY (never applied, D20)"
    if pool(tag) == pool(sug):
        return cls, "in-pool swap (moot, D19)"
    if cls in qr.ACCEPTED_CLASSES:
        return cls, f"accepted ({qr.ACCEPTED_CLASSES[cls]:.2f})"
    if cls in qr.REJECTED_CLASSES:
        return cls, f"rejected ({qr.REJECTED_CLASSES[cls]:.2f})"
    if cls in qr.HOLD_CLASSES:
        return cls, f"hold ({qr.HOLD_CLASSES[cls]:.2f})"
    return cls, "uncalibrated (tag kept)"


def classify(scored: pd.DataFrame, base: pd.DataFrame, seen_ids: set[str], excluded_ids: set[str]) -> dict[str, pd.DataFrame]:
    """Split a rule-applied live frame (box.qc_rule.apply_rule output) against the base set + the judged universe.

    added       new (never judged) and box_bench == WCA after the rule -> appended to the pool
    rule_out    new, tagged into the WCA pool, but the rule moves it out (accepted class + sql/23 concurs)
    not_rejudged  box_bench == WCA now, not in the base file, but judged before (gate-1 decision stands, D84)
    drift       base rows whose live record now differs (gone / re-tagged / the rule would now decide otherwise);
                reported only — base rows are never changed
    """
    base_ids = set(base["api10"])
    if not base_ids <= seen_ids:
        raise ValueError(f"{len(base_ids - seen_ids)} base api10s are missing from the judged universe")
    d = scored.copy()
    fc = [flag_class(r) for _, r in d.iterrows()]
    d["flag_class"] = [c for c, _ in fc]
    d["class_status"] = [s for _, s in fc]
    d["excluded"] = d["api10"].isin(excluded_ids)
    is_new = ~d["api10"].isin(seen_ids)
    in_pool_now = d["box_bench"] == POOL
    tagged_pool = d["formation_blueox"].isin(WCA_TAGS)
    added = d[is_new & in_pool_now].sort_values("api10").reset_index(drop=True)
    rule_out = d[is_new & tagged_pool & ~in_pool_now].sort_values("api10").reset_index(drop=True)
    not_rejudged = d[~is_new & in_pool_now & ~d["api10"].isin(base_ids)].sort_values("api10").reset_index(drop=True)
    live = d.set_index("api10")
    b = base.set_index("api10")
    gone = sorted(base_ids - set(live.index))
    common = sorted(base_ids & set(live.index))
    retag = [a for a in common if live.at[a, "formation_blueox"] != b.at[a, "formation_blueox"]]
    rule_now_out = [a for a in common if live.at[a, "box_bench"] != POOL]
    drift = pd.DataFrame(
        [{"api10": a, "kind": "gone"} for a in gone]
        + [{"api10": a, "kind": "retagged", "base_tag": b.at[a, "formation_blueox"], "live_tag": live.at[a, "formation_blueox"]} for a in retag]
        + [{"api10": a, "kind": "rule_now_out", "live_box_bench": live.at[a, "box_bench"], "live_reason": live.at[a, "box_reason"]} for a in rule_now_out]
    )
    return {"added": added, "rule_out": rule_out, "not_rejudged": not_rejudged, "drift": drift, "n_new_any_bench": int(is_new.sum())}


# ----------------------------------------------------------------------------
# Byte-identical append + identity check
# ----------------------------------------------------------------------------


def _terminator(old: bytes) -> bytes:
    first = old.split(b"\n", 1)[0]
    return b"\r\n" if first.endswith(b"\r") else b"\n"


def append_rows(old: bytes, rows: pd.DataFrame) -> bytes:
    """The base file's bytes, unchanged, followed by `rows` in the base header's column order and line terminator."""
    term = _terminator(old)
    if not old.endswith(term):
        raise ValueError("base file does not end with a line terminator; appending would alter its last row")
    header = old.split(term, 1)[0].decode("utf-8").split(",")
    missing = [c for c in header if c not in rows.columns]
    if missing:
        raise ValueError(f"new rows lack base columns {missing}")
    if rows.empty:
        return old
    text = rows[header].to_csv(index=False, header=False, lineterminator=term.decode())
    return old + text.encode("utf-8")


def sha256(b: bytes) -> str:
    return hashlib.sha256(b).hexdigest()


def verify_identity(old: bytes, new: bytes, added_api10: list[str]) -> dict[str, Any]:
    """Prove the refresh only appended: the base file is a byte prefix of the new file, the appended rows are exactly the
    added wells (in order), and none of them was already in the base. Raises AssertionError on any breach."""
    assert new.startswith(old), "base rows are not a byte-identical prefix of the refreshed file"
    tail = new[len(old):]
    header = old.split(_terminator(old), 1)[0].decode("utf-8")
    base_ids = pd.read_csv(io.BytesIO(old), dtype={"api10": str}, usecols=["api10"])["api10"]
    app = pd.read_csv(io.BytesIO(header.encode() + b"\n" + tail), dtype={"api10": str}, usecols=["api10"])["api10"] if tail else pd.Series([], dtype=str)
    assert list(app) == list(added_api10), "appended rows are not exactly the added wells"
    assert not set(app) & set(base_ids), "an appended api10 is already in the base"
    assert base_ids.is_unique and app.is_unique, "duplicate api10"
    return {"base_sha256": sha256(old), "new_sha256": sha256(new), "base_prefix_bytes": len(old), "n_base_rows": len(base_ids),
            "n_appended": len(app), "n_rows": len(base_ids) + len(app)}


# ----------------------------------------------------------------------------
# Write
# ----------------------------------------------------------------------------

REPORT_COLS = [
    "api10", "well_name", "operator", "state_code", "county", "first_production_date", "formation_blueox", "box_bench", "box_action",
    "flag_class", "class_status", "box_reason", "cons_status", "cons_suggest", "sql23_nearest", "cons_gor_vote", "planned", "tvd_ft",
    "tvd_round", "lateral_length_ft", "in_extent", "excluded", "mid_lon", "mid_lat",
]


def write_refresh(out: Path, base_dir: Path, parts: dict[str, pd.DataFrame], universe: pd.DataFrame, meta: dict[str, Any]) -> dict[str, Any]:
    """Write the refreshed set directory; identity-check every file before returning. Refuses an existing directory."""
    if out.exists() and any(out.iterdir()):
        raise FileExistsError(f"{out} exists and is not empty; a refresh never overwrites")
    out.mkdir(parents=True, exist_ok=True)
    old = (base_dir / final_name(POOL)).read_bytes()
    added = parts["added"]
    new = append_rows(old, added)
    ident = {POOL: verify_identity(old, new, list(added["api10"]))}
    (out / final_name(POOL)).write_bytes(new)
    assert (out / final_name(POOL)).read_bytes() == new
    for p in COPY_POOLS:
        src = base_dir / final_name(p)
        if src.exists():
            b = src.read_bytes()
            (out / final_name(p)).write_bytes(b)
            assert sha256((out / final_name(p)).read_bytes()) == sha256(b)
            ident[p] = {"copied": True, "sha256": sha256(b), "n_rows": b.count(_terminator(b)) - 1}
    rep = pd.concat([added.assign(refresh_class="added"), parts["rule_out"].assign(refresh_class="rule_out")], ignore_index=True)
    rep[["refresh_class"] + [c for c in REPORT_COLS if c in rep.columns]].to_csv(out / NEW_WELLS, index=False)
    universe.to_csv(out / UNIVERSE, index=False)
    man = dict(meta)
    man["identity"] = ident
    (out / MANIFEST).write_text(json.dumps(man, indent=1, default=str), encoding="utf-8")
    return man


def summarize(parts: dict[str, pd.DataFrame]) -> dict[str, Any]:
    a, ro, nr, dr = parts["added"], parts["rule_out"], parts["not_rejudged"], parts["drift"]
    return {
        "n_new_any_bench": parts["n_new_any_bench"],
        "added": len(a),
        "added_by_tag": a["formation_blueox"].value_counts().to_dict(),
        "added_by_action": a["box_action"].value_counts().to_dict(),
        "added_by_class_status": a["class_status"].value_counts().to_dict(),
        "added_in_extent": int(a["in_extent"].sum()) if "in_extent" in a else None,
        "added_excluded": int(a["excluded"].sum()),
        "rule_out": len(ro),
        "rule_out_to": ro["box_bench"].value_counts().to_dict(),
        "not_rejudged": len(nr),
        "drift": dr["kind"].value_counts().to_dict() if len(dr) else {},
        "uncalibrated_classes_new": sorted(set(pd.concat([a, ro]).loc[lambda x: x["class_status"].str.startswith("uncalibrated"), "flag_class"])),
    }


# ----------------------------------------------------------------------------
# Review page
# ----------------------------------------------------------------------------

_CSS = """
body{font:13px/1.45 -apple-system,Segoe UI,Roboto,sans-serif;color:#111827;background:#fff;margin:0 24px 48px;max-width:1500px}
h1{font-size:20px;margin:18px 0 4px} h2{font-size:16px;margin:30px 0 6px;border-top:2px solid #e5e7eb;padding-top:12px}
.meta{color:#6b7280;font-size:12px} .flag{background:#fffbeb;border-left:4px solid #d97706;padding:4px 10px;margin:6px 0}
.ok{background:#f0fdf4;border-left:4px solid #16a34a;padding:4px 10px;margin:6px 0}
table{border-collapse:collapse;font-size:12px;margin:8px 0} th,td{border:1px solid #e5e7eb;padding:3px 7px;text-align:left;vertical-align:top}
th{background:#f9fafb} td.num{text-align:right} details{margin:6px 0} summary{cursor:pointer;color:#374151;font-size:12px}
#map{height:720px;border:1px solid #d1d5db;margin:8px 0}
"""

_MAP_JS = """
<link rel="stylesheet" href="https://unpkg.com/leaflet@1.9.4/dist/leaflet.css">
<script src="https://unpkg.com/leaflet@1.9.4/dist/leaflet.js"></script>
<script>
const D = __DATA__;
const map = L.map('map', {preferCanvas: true});
L.tileLayer('https://server.arcgisonline.com/ArcGIS/rest/services/Canvas/World_Light_Gray_Base/MapServer/tile/{z}/{y}/{x}', {maxZoom: 16, attribution: 'Tiles &copy; Esri'}).addTo(map);
const ll = c => c.map(p => [p[1], p[0]]);
const esc = s => String(s ?? '').replace(/[&<>]/g, ch => ({'&':'&amp;','<':'&lt;','>':'&gt;'}[ch]));
const pop = w => `<b>${esc(w.name)}</b><br>api10 ${w.api10} · ${esc(w.op)}<br>first prod ${w.fp} · tag ${w.tag} → ${w.bb} (${w.act})<br>${esc(w.cls)} ${esc(w.st)}<br><span style="color:#6b7280">${esc(w.why)}</span>`;
const ext = L.layerGroup(D.extent.map(rings => L.polygon(rings.map(ll), {color: '#6b7280', weight: 0.8, fillColor: '#bfdbfe', fillOpacity: 0.2, interactive: false}))).addTo(map);
const base = L.layerGroup(D.base.map(p => L.circleMarker([p[1], p[0]], {radius: 1.5, stroke: false, fillColor: '#9ca3af', fillOpacity: 0.6, interactive: false}))).addTo(map);
const nr = L.layerGroup(D.not_rejudged.map(w => L.circleMarker([w.lat, w.lon], {radius: 4, color: '#d97706', weight: 1.2, fill: false}).bindPopup(pop(w) + '<br><b>judged before — not re-decided (D84)</b>')));
const out = L.layerGroup(D.rule_out.map(w => L.circleMarker([w.lat, w.lon], {radius: 6, color: '#dc2626', weight: 2, fillColor: '#fecaca', fillOpacity: 0.9}).bindPopup(pop(w) + '<br><b>new; the rule moves it OUT of the pool</b>'))).addTo(map);
const add = L.layerGroup(D.added.map(w => L.circleMarker([w.lat, w.lon], {radius: 6, color: '#1e3a8a', weight: 2, fillColor: w.ex ? '#e5e7eb' : (w.act === 'reassign' ? '#c026d3' : '#2563eb'), fillOpacity: 0.95}).bindPopup(pop(w) + (w.ex ? '<br><b>in exclusions.csv — dropped at load</b>' : '')))).addTo(map);
L.control.layers(null, {'WCA extent of record': ext, 'base pool (frozen rows)': base, 'added (blue = tag kept, magenta = reassigned in, grey = excluded)': add, 'new, ruled out of the pool': out, 'judged before, not re-decided': nr}, {collapsed: false}).addTo(map);
const pts = D.added.concat(D.rule_out).map(w => [w.lat, w.lon]);
const bounds = pts.length ? L.latLngBounds(pts).pad(0.3) : L.latLngBounds(D.base.map(p => [p[1], p[0]]));
map.fitBounds(bounds, {maxZoom: 10});
window.addEventListener('load', () => { map.invalidateSize(); map.fitBounds(bounds, {maxZoom: 10}); });
</script>
"""


def _esc(v: Any) -> str:
    return html.escape("" if v is None or (isinstance(v, float) and np.isnan(v)) else str(v))


def _table(df: pd.DataFrame, cols: list[str]) -> str:
    cols = [c for c in cols if c in df.columns]
    head = "".join(f"<th>{_esc(c)}</th>" for c in cols)
    body = "".join("<tr>" + "".join(f"<td>{_esc(r[c])}</td>" for c in cols) + "</tr>" for _, r in df.iterrows())
    return f"<table><tr>{head}</tr>{body}</table>"


def _pts(df: pd.DataFrame) -> list[dict[str, Any]]:
    out = []
    for _, r in df.iterrows():
        if pd.isna(r.get("mid_lon")) or pd.isna(r.get("mid_lat")):
            continue
        out.append({"lon": round(float(r["mid_lon"]), 5), "lat": round(float(r["mid_lat"]), 5), "api10": r["api10"], "name": r.get("well_name"),
                    "op": r.get("operator"), "fp": str(r.get("first_production_date")), "tag": r.get("formation_blueox"), "bb": r.get("box_bench"),
                    "act": r.get("box_action"), "cls": r.get("flag_class"), "st": r.get("class_status"), "why": r.get("box_reason"),
                    "ex": bool(r.get("excluded", False))})
    return out


def render_page(out: Path, base: pd.DataFrame, parts: dict[str, pd.DataFrame], man: dict[str, Any], extent_rings: list[list[list[list[float]]]]) -> Path:
    s, ident, seen = man["summary"], man["identity"][POOL], man["seen"]
    a, ro, nr, dr = parts["added"], parts["rule_out"], parts["not_rejudged"], parts["drift"]
    data = {"extent": extent_rings, "base": [[round(float(x), 4), round(float(y), 4)] for x, y in zip(base["mid_lon"], base["mid_lat"]) if pd.notna(x) and pd.notna(y)],
            "added": _pts(a), "rule_out": _pts(ro), "not_rejudged": _pts(nr)}
    cols = ["api10", "well_name", "operator", "first_production_date", "formation_blueox", "box_bench", "box_action", "flag_class", "class_status",
            "box_reason", "sql23_nearest", "planned", "tvd_ft", "lateral_length_ft", "in_extent", "excluded"]
    p = [
        f"<!doctype html><html><head><meta charset=\"utf-8\"><title>BOX pool refresh {_esc(man['label'])}</title><style>{_CSS}</style></head><body>",
        f"<h1>BOX analog-pool refresh — {_esc(man['label'])} (D84)</h1>",
        (f"<div class=meta>Base {_esc(man['base_dir'])} → {_esc(man['out_dir'])}. Live warehouse read-only, Delaware producing horizontals "
        f"{man['n_live']:,}, data through {_esc(man['asof'])}. Step-1 pipeline: consensus detector (box/bench_qc.py) + class rule of record "
        f"(box/qc_rule.py) with <b>no card verdicts</b>. Built {_esc(man['built_at'])} at {_esc(man['git_sha'])}. Nothing written to the warehouse.</div>"),
        "<h2>1. What changed in the pool</h2>",
        _table(pd.DataFrame([
            {"measure": "base rows (byte-identical prefix)", "n": f"{ident['n_base_rows']:,}"},
            {"measure": "new wells added to the WCA pool", "n": f"{s['added']:,}"},
            {"measure": "  … of them in exclusions.csv (dropped at load by build)", "n": s["added_excluded"]},
            {"measure": "  … of them inside the WCA extent of record", "n": s["added_in_extent"]},
            {"measure": "refreshed pool rows", "n": f"{ident['n_rows']:,}"},
            {"measure": "new wells tagged WCA_1 / WCA_2 / WCXY that the rule moves out", "n": s["rule_out"]},
            {"measure": "new wells, any Delaware bench (never judged before)", "n": f"{s['n_new_any_bench']:,}"},
        ]), ["measure", "n"]),
        f"<div class=ok>Identity: the base wells_final_WCA.csv (sha256 {ident['base_sha256'][:12]}…, {ident['base_prefix_bytes']:,} bytes) is an exact byte prefix "
        f"of the refreshed file (sha256 {ident['new_sha256'][:12]}…); the appended rows are exactly the {ident['n_appended']} added wells. "
        + "; ".join(f"{k} copied byte-identical (sha256 {v['sha256'][:12]}…)" for k, v in man["identity"].items() if k != POOL) + ".</div>",
        "<h2>2. Where the new wells are</h2><div id=map></div>",
        "<h2>3. New wells and their flag classes</h2>",
        ("<p>Flag class = the consensus swap on pooled labels; status = its standing under the class rule of record. With no cards, an "
        "uncalibrated class keeps the tag. A-prime (planned survey flagged) and Bone Spring → Wolfcamp keep the tag and drop the TVD as depth evidence.</p>"),
        _table(pd.concat([a.assign(refresh_class="added"), ro.assign(refresh_class="rule_out")]), ["refresh_class"] + cols) if len(a) + len(ro) else "<p>None.</p>",
        "<h2>4. Not re-decided (D84: new wells only)</h2>",
        (f"<p>{len(nr):,} wells the rule would put in the WCA pool today are not in the base file but were judged before, so their earlier decision "
        f"stands (orange rings on the map, off by default). {dr['api10'].nunique() if len(dr) else 0:,} base rows have drifted live ({_esc(s['drift'])}); base rows are never "
        "changed. Both are what re-running gate 1 on old wells would churn.</p>"),
        f"<details><summary>not re-decided ({len(nr)})</summary>{_table(nr, cols)}</details>",
        f"<details><summary>base-row drift ({len(dr)})</summary>{_table(dr, list(dr.columns))}</details>" if len(dr) else "",
        "<h2>5. The judged universe</h2>",
        f"<p>Method: <b>{_esc(seen['method'])}</b>. " + (
            f"{_esc(seen['rule'])}: {seen['n']:,} api10s ({seen['n_named']:,} named, {seen['n_fp_cut']:,} by the first-production cut; "
            f"{seen['n_live_fp_cut_not_named']:,} live wells counted as judged by the cut alone). The gate-1 run recorded {_esc(seen.get('gate1_recorded_n'))} "
            "Delaware producing horizontals; live wells within the cut beyond that are late-reported or re-tagged since and are treated as judged."
            if seen["method"] == "reconstructed" else f"{_esc(seen['path'])}: {seen['n']:,} api10s.")
        + f" This refresh records {man['n_universe']:,} judged api10s in <code>universe.csv</code>; the next refresh's new wells are exactly those not in it.</p>",
        "<p class=meta>Use: <code>python -m scripts.box_pud_run build --wells " + _esc(man["out_dir"]) + "</code>. Gate: Michael confirms the added wells.</p>",
        _MAP_JS.replace("__DATA__", json.dumps(data, default=str)),
        "</body></html>",
    ]
    path = out / "index.html"
    path.write_text("".join(p), encoding="utf-8")
    return path


def load_exclusions() -> set[str]:
    return set(exclusions.load()["api10"])
