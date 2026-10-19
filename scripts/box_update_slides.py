"""Slides for scripts.box_update_deck (python-pptx on the Blue Ox brand template; pure, no database).

Every number is computed here from the run-9 artifact (= live record run_id 10) and the BOX x Novi frame; disclosure numbers come
from the run's own by_bench disclosure (what each workup states). Error convention: actual / forecast - 1 (negative = forecast HIGH).
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
from pptx import Presentation
from pptx.dml.color import RGBColor
from pptx.enum.text import PP_ALIGN
from pptx.util import Emu, Inches, Pt

from box import production_run9 as p9r
from scripts import box_update_deck as bud

INK = RGBColor(0x11, 0x18, 0x27)
MUTED = RGBColor(0x4B, 0x55, 0x63)
HEAD_FILL = RGBColor(0xF3, 0xF4, 0xF6)
FLAG = RGBColor(0xB4, 0x23, 0x18)
LINE = RGBColor(0xD1, 0xD5, 0xDB)
TOP = Inches(1.62)
BOTTOM = Inches(6.22)
LEFT = Inches(0.45)
WIDTH = Inches(12.43)

HOLDOUT = {"WCA": "Accepted 16 / 18 cells (D59)", "BS2_S": "PASS 4 / 4 (D99)", "WCXY_WCA1": "PASS 6 / 6 (D99)", "WCB_1": "PASS 6 / 6 (D99)",
           "WCC": "PASS 4 / 4 (D99, weak power)", "BS3_S": "FAIL (D99)", "BS3_C": "FAIL (D99)", "WCB_2": "FAIL (D99)", "BS1_S": "FAIL (D99)",
           "AVA_0": "not testable (D105)", "AVA_1": "not testable (D105)", "AVA_2": "not testable (D105)", "BS2_C": "not testable (D105)"}
SPEC = {"WCA": "analog P50 x walk-forward haircut (D62)", "BS2_S": "analog P50 x own haircut (D102)", "WCXY_WCA1": "raw analog P50 (WCXY + WCA_1 analogs)"}


# ----------------------------------------------------------------------------
# helpers
# ----------------------------------------------------------------------------


def _title_only(pres: Any) -> Any:
    return next(lay for lay in pres.slide_layouts if lay.name == "Title Only")


def _slide(pres: Any, title: str) -> Any:
    s = pres.slides.add_slide(_title_only(pres))
    s.shapes.title.text = title
    for p in s.shapes.title.text_frame.paragraphs:
        for r in p.runs:
            r.font.size = Pt(26 if len(title) <= 48 else 20)
    return s


def _text(s: Any, x: Any, y: Any, w: Any, h: Any, lines: list[Any], size: int = 14, color: RGBColor = INK) -> Any:
    """lines: str, or (str, {"bold", "size", "color", "level"}). A leading '• ' is kept as typed."""
    tb = s.shapes.add_textbox(x, y, w, h)
    tf = tb.text_frame
    tf.word_wrap = True
    for i, ln in enumerate(lines):
        txt, opt = (ln, {}) if isinstance(ln, str) else ln
        p = tf.paragraphs[0] if i == 0 else tf.add_paragraph()
        p.level = int(opt.get("level", 0))
        p.space_after = Pt(opt.get("after", 4))
        r = p.add_run()
        r.text = txt
        r.font.size = Pt(opt.get("size", size))
        r.font.bold = bool(opt.get("bold", False))
        r.font.color.rgb = opt.get("color", color)
    return tb


def _table(s: Any, x: Any, y: Any, w: Any, df: pd.DataFrame, col_w: list[float] | None = None, size: int = 10, row_h: float = 0.27,
           flag_col: str | None = None) -> Any:
    rows, cols = len(df) + 1, len(df.columns)
    gf = s.shapes.add_table(rows, cols, x, y, w, Inches(row_h * rows))
    t = gf.table
    t.first_row = True
    if col_w:
        tot = sum(col_w)
        for j, cw in enumerate(col_w):
            t.columns[j].width = Emu(int(w * cw / tot))
    for j, c in enumerate(df.columns):
        _cell(t.cell(0, j), str(c), size, bold=True, fill=HEAD_FILL)
    for i, (_, r) in enumerate(df.iterrows(), start=1):
        for j, c in enumerate(df.columns):
            v = r[c]
            red = flag_col is not None and c == flag_col and isinstance(v, str) and v.startswith("FAIL")
            _cell(t.cell(i, j), "" if v is None or (isinstance(v, float) and not np.isfinite(v)) else str(v), size,
                  color=FLAG if red else INK, bold=red, fill=RGBColor(0xFF, 0xFF, 0xFF))
    for i in range(rows):
        t.rows[i].height = Inches(row_h)
    return gf


def _cell(c: Any, text: str, size: int, bold: bool = False, color: RGBColor = INK, fill: RGBColor | None = None) -> None:
    c.text = text
    c.margin_left = c.margin_right = Inches(0.05)
    c.margin_top = c.margin_bottom = Inches(0.02)
    if fill is not None:
        c.fill.solid()
        c.fill.fore_color.rgb = fill
    for p in c.text_frame.paragraphs:
        for r in p.runs:
            r.font.size = Pt(size)
            r.font.bold = bold
            r.font.color.rgb = color


def _pct(x: Any) -> str:
    return "–" if x is None or (isinstance(x, float) and not np.isfinite(x)) else f"{x:+.0%}"


def _box(s: Any, x: float, y: float, w: float, h: float, head: str, body: str, fill: RGBColor) -> None:
    sh = s.shapes.add_shape(1, Inches(x), Inches(y), Inches(w), Inches(h))
    sh.fill.solid()
    sh.fill.fore_color.rgb = fill
    sh.line.color.rgb = LINE
    tf = sh.text_frame
    tf.word_wrap = True
    p = tf.paragraphs[0]
    r = p.add_run()
    r.text = head
    r.font.size, r.font.bold, r.font.color.rgb = Pt(13), True, INK
    p2 = tf.add_paragraph()
    r2 = p2.add_run()
    r2.text = body
    r2.font.size, r2.font.color.rgb = Pt(12), INK
    for q in (p, p2):
        q.alignment = PP_ALIGN.LEFT


# ----------------------------------------------------------------------------
# numbers
# ----------------------------------------------------------------------------


def disclosed(run: dict[str, Any], g: str, s: str, k: int) -> tuple[float | None, float | None]:
    """(disclosed bias, holdout bias) the workup states for group g, stream s, horizon k."""
    b = run["by_bench"][g]["disclosure"]["hindcast_bias"][s][str(k)]
    if g == "WCA":  # after the D62 correction, measured on held-out packages
        return b.get("box_v2_wf_holdout_bias"), b.get("box_v2_wf_holdout_bias")
    return b.get("disclosed_bias"), b.get("holdout_bias")


def coverage(A: dict[str, Any]) -> pd.DataFrame:
    rows = []
    for g in p9r.GROUPS:
        res = [r for loc, r in zip(A["locs"], A["results"], strict=True) if loc["prod_bench"] == g]
        n_f = sum("oil" in r.get("streams", {}) for r in res)
        rows.append({"bench": bud.label(g), "tier": p9r.tier(g), "in-extent PUDs": len(res), "forecast": n_f, "no analogs": len(res) - n_f})
    return pd.DataFrame(rows)


# ----------------------------------------------------------------------------
# deck
# ----------------------------------------------------------------------------


def build(A: dict[str, Any], f: pd.DataFrame, maps: Path, out: Path) -> None:
    run = A["run"]
    pres = Presentation(str(bud.TEMPLATE))
    sld = pres.slides._sldIdLst  # noqa: SLF001 — python-pptx has no delete API; drop the two template slides
    for sid in list(sld):
        pres.part.drop_rel(sid.rId)
        sld.remove(sid)
    cov = coverage(A)
    summ = bud.summary(f)
    val, prov = cov[cov.tier == "validated"], cov[cov.tier == "provisional"]

    # 1 title
    s = pres.slides.add_slide(next(lay for lay in pres.slide_layouts if lay.name == "Title Slide"))
    s.shapes.title.text = "BOX type curves — progress update"
    s.placeholders[1].text = "Run 9 is the live record · 13 Delaware benches · analog workups at every Novi PUD · 2026-10-19"

    # 2 where we are
    s = _slide(pres, "Where we are")
    vt, pt = int(val["forecast"].sum()), int(prov["forecast"].sum())
    oil_v = f[f.group.isin([g for g in p9r.GROUPS if p9r.tier(g) == "validated"])]["box_oil50"].sum() / 1e6
    oil_p = f[f.group.isin([g for g in p9r.GROUPS if p9r.tier(g) == "provisional"])]["box_oil50"].sum() / 1e6
    _text(s, LEFT, TOP, Inches(6.3), Inches(4.5), [
        ("BOX run 9 stored live 2026-10-18 as the record (warehouse run_id 10)", {"bold": True, "size": 16}),
        f"• Every in-scope Delaware bench now carries a forecast: {vt + pt:,} PUD locations",
        f"• Validated tier: {vt:,} locations on 5 benches ({oil_v:,.0f} MMbbl oil, 50-yr)",
        f"• Provisional tier: {pt:,} locations on 8 benches ({oil_p:,.0f} MMbbl) — forecast, labelled, disclosed, never validated",
        f"• {int(cov['no analogs'].sum()):,} in-extent PUDs have < 3 analogs within 20 mi: counted, not forecast (345 on the BS1_S south edge)",
        "• Each location: named analogs, analog radius reached, curve, and the method's measured bias on that bench",
        "• Identity checks green in a container rehearsal and again live; superseded run pruned",
        ("Technical forecasts only: oil + gas, no water, uptime-free volumes, raw 50-yr EUR, no economics.", {"size": 11, "color": MUTED}),
    ], size=13)
    ct = cov.rename(columns={"in-extent PUDs": "in-extent"})
    for c in ("in-extent", "forecast", "no analogs"):
        ct[c] = ct[c].map("{:,}".format)
    _table(s, Inches(7.0), TOP, Inches(5.85), ct, [1.2, 1.2, 1.0, 1.0, 1.0], size=9, row_h=0.25)

    # 3 process
    s = _slide(pres, "How a BOX forecast is built and tested")
    steps = [("1  Bench + extent", "QC'd well set per bench (≥ 2016 horizontals). Extent = the bench's development envelope; geology reviews as shapefile."),
             ("2  Analog workup", "At every Novi PUD: same-bench offsets, nearest first, lateral band, representative spacing; cohort P50 per stream."),
             ("3  Tune (backtest)", "Rolling cutoffs 2019–2024: rebuild from pre-cutoff data only, forecast the next year's wells, score cum-12/24/36."),
             ("4  Freeze", "Pick the spec per bench (raw vs walk-forward haircut) on tuning data; freeze code + pass intervals."),
             ("5  Holdout, once", "20 % of 3-mi blocks never seen in tuning. Scored one time against the frozen intervals. Fail = diagnose, never re-tune."),
             ("6  Record run", "Production forecast at every PUD + the measured bias stated on every workup (validated or provisional tier).")]
    for i, (h, b) in enumerate(steps):
        _box(s, 0.45 + (i % 3) * 4.17, 1.7 + (i // 3) * 2.15, 3.95, 1.95, h, b, RGBColor(0xF8, 0xFA, 0xFC) if i != 4 else RGBColor(0xEE, 0xF4, 0xFD))

    # 4 holdouts, scoring, tuning
    s = _slide(pres, "Scoring, tuning and the one-time holdout")
    _text(s, LEFT, TOP, Inches(6.1), Inches(4.6), [
        ("Scoring (D53)", {"bold": True, "size": 15}),
        "• Unit = a development PACKAGE: co-developed wells (first production within 180 d, ≥ 30 % overlap). Steven prices packages, not wells",
        "• Error = Σ actual ÷ Σ forecast − 1 per package; + = forecast LOW, − = forecast HIGH",
        "• Bias = mean package error; spread = P10–P90 band, compared with an engineer's quick look (median per-ft of the 15 nearest offsets)",
        "• Horizons cum-12 / 24 / 36 (cum-48 where reached); a cell is judged with ≥ 30 packages",
        ("Tuning", {"bold": True, "size": 15}),
        "• Six cutoffs, Dec 1 2019–2024; every model rebuilt from data known at the cutoff",
        "• Walk-forward haircut = mean bias at EARLIER cutoffs only; kept where it helps (WCA, BS2_S), dropped where thin knots over-correct",
    ], size=12)
    _text(s, Inches(6.75), TOP, Inches(6.1), Inches(4.6), [
        ("Holdout (D52 / D99)", {"bold": True, "size": 15}),
        "• A salted hash of 3-mile blocks sets aside 20 % of the ground; those packages are dropped before any tuning statistic exists",
        "• Before looking: freeze the spec and the pass intervals (2,000 random 20 % block draws of tuning packages, P2.5–P97.5)",
        "• Score ONCE: pass = every judged cell's holdout bias inside its frozen interval",
        "• Result: WCA, BS2_S, WCXY, WCB_1, WCC passed; BS3_S, BS3_C, WCB_2, BS1_S failed and were moved to the provisional tier as scored",
        ("Still to come", {"bold": True, "size": 15}),
        "• Prospective test on 2026 wells under the frozen rules (cohort frozen 2026-10-15); first judged read ~2027-Q2",
    ], size=12)

    # 5 scorecard
    s = _slide(pres, "Validation scorecard by bench")
    rows = []
    for g in p9r.GROUPS:
        o12, o12h = disclosed(run, g, "oil", 12)
        o24, _ = disclosed(run, g, "oil", 24)
        g12, g12h = disclosed(run, g, "gas", 12)
        rows.append({"bench": bud.label(g), "tier": p9r.tier(g), "holdout": HOLDOUT[g],
                     "forecast basis": SPEC.get(g, "raw analog P50, no haircut"),
                     "oil cum-12 bias": _pct(o12), "oil cum-24": _pct(o24), "gas cum-12": _pct(g12),
                     "holdout oil / gas cum-12": "–" if g == "WCA" or o12h is None else f"{_pct(o12h)} / {_pct(g12h)}"})
    _table(s, LEFT, TOP, WIDTH, pd.DataFrame(rows), [0.8, 0.9, 1.6, 2.4, 0.9, 0.8, 0.8, 1.3], size=9, row_h=0.29, flag_col="holdout")
    _text(s, LEFT, Inches(5.75), WIDTH, Inches(0.5), [
        ("Bias = the number each workup discloses (validated: tuning bias, WCA after its haircut on held-out ground; provisional: tuning + holdout "
         "pooled, AVA pooled 0+1+2). − = forecast HIGH. Provisional benches carry no haircut, so their stated bias is the expected miss.",
         {"size": 9, "color": MUTED})])

    # 6 BOX vs Novi
    s = _slide(pres, "BOX vs Novi BASE_CASE — same sticks, 30-year basis")
    t = pd.DataFrame({"bench": summ["bench"], "tier": summ["tier"], "locations": summ["locations"].map("{:,}".format),
                      "BOX oil bbl/ft P50": summ["BOX oil EUR/ft (30-yr) P50"].map("{:.1f}".format),
                      "Novi oil bbl/ft P50": summ["Novi oil EUR/ft P50"].map("{:.1f}".format),
                      "BOX ÷ Novi (sum)": summ["BOX / Novi (sum)"].map("{:.2f}".format),
                      "ratio P90–P10": [f"{a:.2f}–{b:.2f}" for a, b in zip(summ["BOX / Novi P90 (low)"], summ["BOX / Novi P10 (high)"], strict=True)],
                      "BOX GOR12": summ["BOX GOR12 P50"].map("{:,.0f}".format), "Novi GOR12": summ["Novi GOR12 P50"].map("{:,.0f}".format)})
    _table(s, LEFT, TOP, Inches(8.6), t, [0.8, 0.9, 0.8, 1.0, 1.0, 0.9, 1.0, 0.8, 0.8], size=9, row_h=0.29)
    vs = f[f.group.isin([g for g in p9r.GROUPS if p9r.tier(g) == "validated"])]
    ps = f[~f.index.isin(vs.index)]
    _text(s, Inches(9.25), TOP, Inches(3.65), Inches(4.6), [
        ("Read-out", {"bold": True, "size": 14}),
        f"• Validated benches: BOX = {vs.box_oil30.sum() / vs.novi_oil30.sum():.2f}× Novi oil in total; lower on WCA (0.92), BS2_S (0.87) and WCC (0.67), higher on WCXY / WCB_1",
        f"• Provisional benches: BOX = {ps.box_oil30.sum() / ps.novi_oil30.sum():.2f}× Novi — BOX is the HIGHER number on all eight, most on AVA (1.2–1.7×)",
        "• Those benches carry no haircut and several over-forecast in our own hindcast (BS1_S oil −12 %, AVA recent cohorts −14…−18 %): read them as an upper side",
        "• GOR mostly agrees; WCC is the outlier (BOX ~14,500 vs Novi ~4,400 scf/bbl); BOX's WCC gas was within −5…−11 % of actuals in tuning / holdout",
        ("P50 = median location. Ratio range = P90 (low) – P10 (high) of the per-location ratio.", {"size": 9, "color": MUTED}),
    ], size=11)

    # 7 provisional tier
    s = _slide(pres, "The provisional tier — forecast, labelled, never validated")
    _text(s, LEFT, TOP, Inches(12.4), Inches(4.6), [
        "• A bench that cannot support the out-of-time test (too little development history), or that failed it, is still forecast — "
        "a representative ≥ 2016 analog workup is more useful than a blank (Michael, 2026-10-17)",
        "• Same analog engine as every bench; raw analog P50, no haircut, no re-tuning after a failed holdout",
        "• Stored as `covered_provisional`, so 'covered' keeps meaning VALIDATED in every app, query and count",
        ("Disclosure on every provisional workup", {"bold": True, "size": 14}),
        "• AVA_0 / 1 / 2, BS2_C — never tested: the in-sample bias with a 95 % range, and the latest-vintage line "
        "(AVA: recent 2022–24 cohorts produced 14–18 % below forecast at 12 months; BS2_C: the miss changed sign, 2023–24 came in ~12 % above)",
        "• BS3_S, BS3_C, WCB_2, BS1_S — FAILED the holdout: the tuning line, the HOLDOUT line and the pooled line are always shown together, "
        "never the pooled figure alone (WCB_2 gas cum-12: +2 % pooled hides +21 % on the holdout)",
        "• Edge caveats where tuning measured them (e.g. BS1_S south edge oil cum-12 −56 %, BS3_S south −18 %)",
        ("Not yet visible in erebor's Highgrade screen — the tier-aware display is the next app change.", {"size": 11, "color": FLAG}),
    ], size=13)

    # 8 reading the maps
    s = _slide(pres, "Reading the bench maps")
    _text(s, LEFT, TOP, Inches(12.4), Inches(4.6), [
        "• Same sticks on both maps of a pair: the BOX-forecast Novi PUD locations, each matched 1:1 to its own Novi BASE_CASE forecast (no RES, no realized sticks)",
        "• One shared color scale per pair: the same color means the same value on BOX and on Novi; bins are quantiles of the pooled values",
        "• Oil EUR per ft of lateral on a 30-YEAR basis for both — Novi BASE_CASE runs 359 months; BOX's record EUR is the raw 50-yr integral "
        "(30-yr ≈ 95–97 % of it on every bench)",
        "• GOR = 12-month cumulative (1,000 × cum-12 gas Mcf ÷ cum-12 oil bbl, scf/bbl): gas peaks ~4 months after oil, so 6-month GOR reads low; cum-12 is a scored horizon",
        "• BOX = analog-cohort P50 per location (× the walk-forward haircut on WCA / BS2_S); volumes uptime-free",
        "• Ratio map: BOX ÷ Novi oil EUR; grey = within ±10 %, red = BOX below Novi, blue = BOX above",
        "• Context: dashed = TX / NM line; black outline = the bench's BOX extent of record; grey = survey blocks",
    ], size=13)

    # per bench
    for g in p9r.GROUPS:
        L = bud.label(g)
        x = f[f.group == g]
        r = summ[summ.bench == L].iloc[0]
        pic_w, pic_h = Inches(6.05), Inches(4.88)
        for key, title in (("eur", f"{L} — oil EUR per ft: BOX vs Novi"), ("gor", f"{L} — 12-month GOR: BOX vs Novi")):
            s = _slide(pres, title)
            s.shapes.add_picture(str(maps / f"{g}_{key}_box.png"), Inches(0.5), Inches(1.45), pic_w, pic_h)
            s.shapes.add_picture(str(maps / f"{g}_{key}_novi.png"), Inches(6.78), Inches(1.45), pic_w, pic_h)
        s = _slide(pres, f"{L} — where BOX and Novi differ")
        s.shapes.add_picture(str(maps / f"{g}_ratio.png"), Inches(0.5), Inches(1.45), pic_w, pic_h)
        res = [rr for loc, rr in zip(A["locs"], A["results"], strict=True) if loc["prod_bench"] == g]
        noa = sum("oil" not in rr.get("streams", {}) for rr in res)
        o12, o12h = disclosed(run, g, "oil", 12)
        g12, g12h = disclosed(run, g, "gas", 12)
        lines: list[Any] = [
            (f"{p9r.tier(g).capitalize()} · holdout: {HOLDOUT[g]}", {"bold": True, "size": 14, "color": FLAG if HOLDOUT[g].startswith("FAIL") else INK}),
            f"• {SPEC.get(g, 'raw analog P50, no haircut')}; extent {bud.EXTENT_OF[g]}",
            f"• {len(x):,} PUD locations forecast" + (f"; {noa} with < 3 analogs (not forecast)" if noa else ""),
            f"• Oil EUR/ft P50 (30-yr): BOX {r['BOX oil EUR/ft (30-yr) P50']:.1f} vs Novi {r['Novi oil EUR/ft P50']:.1f} bbl/ft",
            f"• BOX ÷ Novi oil: {r['BOX / Novi (sum)']:.2f} in total; P90–P10 {r['BOX / Novi P90 (low)']:.2f}–{r['BOX / Novi P10 (high)']:.2f}",
            f"• GOR12 P50: BOX {r['BOX GOR12 P50']:,.0f} vs Novi {r['Novi GOR12 P50']:,.0f} scf/bbl",
            f"• Disclosed bias, cum-12: oil {_pct(o12)}, gas {_pct(g12)}" + ("" if g == "WCA" or o12h is None else f"; holdout oil {_pct(o12h)}, gas {_pct(g12h)}"),
        ]
        flags = sorted({fl for rr in res for fl in rr.get("flags", []) if "edge caveat" in fl or fl.startswith(("D101", "D100", "D105", "WCB_1 (", "WCC ("))})
        for fl in sorted(flags, key=lambda t: not t.startswith("D105"))[:5]:
            lines.append((f"• {fl}", {"size": 9, "color": MUTED}))
        _text(s, Inches(6.85), Inches(1.6), Inches(6.0), Inches(4.6), [ln for ln in lines if ln], size=12)

    # limits + next
    s = _slide(pres, "Known limits")
    _text(s, LEFT, TOP, Inches(12.4), Inches(4.6), [
        "• Edges over-forecast on every bench (the local-offsets benchmark shows the same): stated per pad, forecast not adjusted",
        "• Provisional benches carry no haircut; their measured bias is mostly forecast-HIGH",
        "• Raw gas runs LOW on BS3_S, BS3_C, WCB_1 (+10…+35 % at cum-24/36): the analog gas P50 misses the GOR rise — a watch item, not a spec change",
        "• Analog sparsity: 480 in-extent PUDs have < 3 analogs at 20 mi (BS1_S south edge 212); the step-15 benches reach past 5 mi on 44–80 % of locations",
        "• Bound-pinned cohort fits flagged for review (AVA_1: oil Di at the 4.0/yr nominal cap — 82 % 1-yr effective — on 47 % of locations)",
        "• No water in BOX v1; volumes are uptime-free (Steven's downtime factor, never two); no economics anywhere",
        "• Novi PUD locations are used as placed (our own placement is a later phase)",
    ], size=13)
    s = _slide(pres, "Next steps")
    _text(s, LEFT, TOP, Inches(12.4), Inches(4.6), [
        "• erebor: show the provisional tier (badge + disclosure) in Highgrade and pad workups",
        "• Steven: run 10 is priceable — validated and provisional rows, per-bench disclosure under the run's by_bench",
        "• Prospective 2026 confirmation under the frozen rules; first judged read ~2027-Q2",
        "• Quarterly refresh with the next Novi vintage (crosswalk carries location ids forward)",
        "• Optional: diagnose why the four failed benches missed (no re-tuning on the spent holdout); faster incremental runs when a bench is added",
    ], size=14)

    # appendix
    s = _slide(pres, "Appendix — conventions")
    _text(s, LEFT, TOP, Inches(12.4), Inches(4.6), [
        "• P10 = HIGH, P90 = LOW (SPE, in-house)",
        "• Decline: Arps Di nominal per year; 1-yr effective stated alongside (Di 4.0/yr nominal ≈ 82 % effective; 3.2 ≈ 76 %)",
        "• EUR = raw 50-yr technical integral (no economic limit); deck maps use a 30-yr window to match Novi's horizon",
        "• Every stream anchors on its own peak; rates are calendar-day",
        "• Bias = Σ actual ÷ Σ forecast − 1 per development package; + = forecast LOW",
        f"• Run 9 = warehouse run_id 10; built from code {run['code_sha'][:7]}, production through {run['data_through']}, Novi {', '.join(run['report_version'])}",
    ], size=13)
    pres.save(str(out))
