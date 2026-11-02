"""BOX step 21b — render the review page at revision 8 (new file; the frozen `scripts/box_step21b_render` is not edited).

    python -m scripts.box_step21b_render_r8

Runs `scripts.box_step21b_render` unchanged, then (a) replaces the frozen SHA it prints (hard-coded 501d799, revision 7) with
the revision-8 SHA from `docs/box/step21b-2026-11-01/FROZEN_SHA`, and (b) inserts the revision 7 vs revision 8 section
(FINDINGS §0) from `rev8_vs_rev7/` (`scripts.box_step21b_rev8_compare`). Editing the frozen render would make every later
21b / 21c frozen-file check fail, hence the wrapper.
"""

from __future__ import annotations

import html
from pathlib import Path

import pandas as pd

from scripts import box_step21b_render as rd
from scripts import box_step21b_rev8_compare as cmp

DOCS = Path("docs") / "box" / "step21b-2026-11-01"
OLD = "frozen SHA 501d799"


def pct(v: float) -> str:
    return f"{v * 100:+.1f} %".replace("-", "−")


def section(d: Path) -> str:
    cls = pd.read_csv(d / "rev8_vs_rev7" / "by_class.csv")
    pooled = pd.read_csv(d / "rev8_vs_rev7" / "pooled.csv")
    wt = pd.read_csv(d / "rev8_vs_rev7" / "weighted.csv")
    names = cmp.NAMES[:3]
    head = "".join(f"<th>{html.escape(n)}</th>" for n in names)
    rows = []
    for c in cls["class"].unique():
        x = cls[cls["class"] == c].set_index("horizon")
        rows.append(f"<tr><td>{html.escape(c)} ft</td>" + "".join(f"<td>{' / '.join(pct(x.loc[k, n]) for k in (12, 24, 36))}</td>" for n in names) + "</tr>")
    p = pooled.set_index(["option", "horizon"])["pooled oil package bias"]
    rows.insert(0, "<tr><td><b>pooled, all lengths</b></td>" + "".join(f"<td><b>{' / '.join(pct(p[(n, k)]) for k in (12, 24, 36))}</b></td>" for n in names) + "</tr>")
    w = wt.set_index(["option", "horizon"])
    col = "stick-weighted |bias - 10-12.5k class|"
    sp = "<tr><td>stick-weighted class spread</td>" + "".join(
        "<td>" + " / ".join(f"{w.loc[(n, k), col] * 100:.1f}" for k in (12, 24, 36)) + " pt</td>" for n in names) + "</tr>"
    return ("<h2 id='rev8'>Revision 8 as run (FINDINGS §0)</h2><div class=meta>Raw <code>mid_r2</code> oil package bias, cum-12 / 24 / 36, "
            "tuning packages. The projection spliced the revision-7 twins; the harness then re-fits each variant's F(k), which re-levels "
            "(short targets 1–2 pt worse, long 3–6 pt better). The code matches the approved rule well by well (FINDINGS §0).</div>"
            f"<div class=scroll><table><tr><th>class</th>{head}</tr>{''.join(rows)}{sp}</table></div>")


def main() -> int:
    rc = rd.main([])
    sha = (DOCS / "FROZEN_SHA").read_text(encoding="utf-8").strip()
    f = DOCS / "index.html"
    s = f.read_text(encoding="utf-8")
    if s.count(OLD) != 1:
        raise RuntimeError(f"expected one '{OLD}' in the rendered page")
    s = s.replace(OLD, f"frozen SHA {sha[:7]} (revision 8, D148)")
    anchor = "<div class=toc>"
    if s.count(anchor) != 1:
        raise RuntimeError("table-of-contents anchor not found once")
    s = s.replace(anchor, section(DOCS) + anchor).replace("<a href='#summary'>summary</a>", "<a href='#rev8'>revision 8</a><a href='#summary'>summary</a>")
    f.write_text(s, encoding="utf-8")
    print(f"wrote {f} (revision 8, frozen SHA {sha[:7]})")
    return rc


if __name__ == "__main__":
    raise SystemExit(main())
