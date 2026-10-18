"""BOX pre-9b rehearsal page (read-only, DB-free) — see box/rehearse9b.py.

    python -m scripts.box_rehearse9b [--runs runs/box9a] [--out docs/box/pre9b-2026-10-16] [--draws 2000]

Reads the step-9a tuning frames only (no holdout well). Writes index.html + CSVs.
"""

from __future__ import annotations

import argparse
import datetime as dt
import sys
from pathlib import Path

from box import rehearse9b as r
from box.edge_gap_report import _CSS, _table

BENCHES = (("bs2s", "tuning_BS2_S", "box_v2_wf", "BS2_S — record box_v2_wf (D94 own haircut)", ("2021-12-01", "2022-12-01", "2023-12-01", "2024-12-01"),
            (("oil", 12), ("oil", 24), ("gas", 12), ("gas", 24))),  # BS2_S cum-36 reaches 30 packages in 0.3 % of draws
           ("wcxy_wca1", "tuning_WCXY_WCA1", "box_v2", "WCXY — record raw box_v2 on the D93 pool (D97)",
            ("2019-12-01", "2020-12-01", "2021-12-01", "2022-12-01", "2023-12-01", "2024-12-01"),
            (("oil", 12), ("oil", 24), ("oil", 36), ("gas", 12), ("gas", 24), ("gas", 36))))
SCALES = (0.85, 0.90, 1.0, 1.10, 1.15)
RULES = ("per_cutoff", "pooled", "per_cutoff_bias", "pooled_bias")


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--runs", type=Path, default=Path("runs") / "box9a")
    ap.add_argument("--out", type=Path, default=Path("docs") / "box" / "pre9b-2026-10-16")
    ap.add_argument("--draws", type=int, default=2000)
    a = ap.parse_args(argv)
    a.out.mkdir(parents=True, exist_ok=True)
    built = dt.datetime.now(tz=dt.UTC).astimezone().isoformat(timespec="seconds")
    p = ["<!doctype html><html><head><meta charset=utf-8><meta name=viewport content='width=device-width,initial-scale=1'><title>BOX pre-9b rehearsal</title>",
         f"<style>{_CSS} body{{overflow-x:hidden}} table{{display:block;overflow-x:auto;max-width:100%}}</style></head><body>",
         "<h1>BOX pre-9b — rehearsing the 9b holdout rule on tuning data</h1>",
         (f"<div class=meta>built {built} · {a.draws:,} random 20 % draws of 3-mi blocks of the step-9a TUNING packages (the D52 holdout's shape; a package is in when "
          "any member is in a drawn block) · no holdout well read · cell test = D53 / D58 (|package bias| ≤ 10 % AND scale-free band ≤ benchmark + 0.05), judged at ≥ 30 "
          "packages · scale = predictions × s (s = 1.10 → forecast 10 % HIGH) to test whether the rule discriminates.</div>")]
    for d, tag, var, title, cuts, cells in BENCHES:
        t = r.package_table(r.load_frames(a.runs / d, tag), var)
        cc = r.cell_counts(t, cuts)
        res = r.rehearse(t, cuts, n_draws=a.draws, scales=SCALES)
        rate = res.groupby("scale")[list(RULES)].agg(lambda x: (x == "PASS").mean()).reset_index()
        jud = res.groupby("scale")[[f"{x}_judged" for x in RULES]].median().reset_index()
        nz = r.cell_noise(t, n_draws=a.draws)
        key = tag.removeprefix("tuning_")
        ivl, crate = r.consistency(t, cells, n_draws=a.draws)
        ivl.to_csv(a.out / f"intervals_{key}.csv", index=False)
        crate.to_csv(a.out / f"consistency_rate_{key}.csv", index=False)
        for name, df in (("cell_counts", cc), ("pass_rates", rate), ("judged", jud), ("cell_noise", nz)):
            df.to_csv(a.out / f"{name}_{key}.csv", index=False)
        p += [f"<h2>{title}</h2>", f"<div class=meta>{len(t['pkg']):,} tuning packages in {t['n_blocks']} blocks; cutoffs {', '.join(c[:4] for c in cuts)}.</div>",
              "<h3>Packages per cell at holdout size (oil; gas is the same)</h3>", _table(cc[cc.stream == "oil"], {"packages_p50": ".0f", "share_judged": ".0%"}),
              "<h3>Share of draws each rule PASSES, by forecast scale</h3>", _table(rate, {x: ".0%" for x in RULES}),
              "<h3>Median cells judged per rule</h3>", _table(jud, {}),
              "<h3>Pooled cells: what a holdout this size can resolve (forecast exactly as good as in tuning)</h3>",
              _table(nz, {"tuning_bias": "+.1%", "draw_bias_p5": "+.1%", "draw_bias_p95": "+.1%", "share_bias_ok": ".0%", "share_spread_ok": ".0%", "share_judged": ".0%",
                          "packages_p50": ".0f"}),
              "<h3>Proposed rule — consistency intervals (P2.5–P97.5 of the drawn pooled bias; FROZEN for 9b if adopted)</h3>",
              _table(ivl, {"tuning_bias": "+.1%", "interval_lo": "+.1%", "interval_hi": "+.1%"}),
              "<h3>Proposed rule — pass rate by forecast scale (1.0 = as good as tuning)</h3>", _table(crate, {"pass_rate": ".0%"})]
    p += ["<h2>Proposed 9b rules</h2>", (a.out / "proposal.html").read_text(encoding="utf-8") if (a.out / "proposal.html").exists() else "", "</body></html>"]
    (a.out / "index.html").write_text("\n".join(p), encoding="utf-8")
    print(f"wrote {a.out / 'index.html'}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
