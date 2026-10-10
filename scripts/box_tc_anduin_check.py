"""BOX step 5b — §7 check: the BOX curve path reproduces a saved anduin type curve (read-only).

    python -m scripts.box_tc_anduin_check [--container permian-postgres]
                                          [--curve vault_wca --curve vault_wcxy] [--out docs/box/step5b-YYYY-MM-DD]

Reads a saved anduin curve (local anduin Postgres, read through `docker exec` into the
`permian-postgres` container — host port 5432 belongs to the local Windows Postgres service): its included wells,
their per-well forecast params (anduin's global `forecasts` table) and laterals / sub-basins, then
rebuilds the curve with box.tc_curve.fit_curve and compares the EUR per 1,000 ft per stream to what
anduin stored in `type_curves.series`, AND to what anduin's own code computes today from the same
forecasts (run read-only inside the `permian-backend` container via stdin — the stored series of an
older curve goes stale when anduin refits its members). Plan §7: must agree to < 0.1 %. With --well-fits, also compares
BOX's per-well fits (the step-5b well_fits_WCA.csv, fitted from the warehouse) with anduin's stored
per-well forecasts for the same wells — those differ only through data (anduin's last sync / refit
date vs the warehouse today), never through the fitting code. Curves with per-well overrides
are refused (the BOX path has no override resolver by design). Writes anduin_check.json.
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import subprocess
import sys
from pathlib import Path

from box import tc_curve as tc

# One JSON document per curve: the saved curve + its members' forecasts and well attributes.
_SQL = """
WITH t AS (SELECT * FROM type_curves WHERE name = :'name' ORDER BY created_at DESC LIMIT 1)
SELECT json_build_object(
  'id', t.id, 'name', t.name, 'api10s', t.included_api10s, 'overrides', t.forecast_overrides,
  'created_at', t.created_at, 'align', t.alignment_method::text, 'basis', t.normalization_basis::text, 'series', t.series, 'stale', t.is_stale,
  'fc', (SELECT json_agg(json_build_object('a', f.api10, 's', f.stream::text, 'p', f.params, 'qo', f.qo, 'pim', f.peak_index_months))
         FROM forecasts f WHERE f.api10 = ANY(t.included_api10s)),
  'fc_refit_after_save', (SELECT count(*) FROM forecasts f WHERE f.api10 = ANY(t.included_api10s) AND f.updated_at > t.created_at),
  'wells', (SELECT json_agg(json_build_object('a', w.api10, 'lat', w.lateral_ft, 'sb', w.subbasin))
            FROM wells w WHERE w.api10 = ANY(t.included_api10s)))
FROM t
"""


def fetch(container: str, name: str) -> dict:
    cmd = ["docker", "exec", "-i", container, "psql", "-U", "permian", "-d", "permian", "-At", "-v", f"name={name}", "-v", "ON_ERROR_STOP=1"]
    r = subprocess.run(cmd, input="SET default_transaction_read_only = on;\n" + _SQL, capture_output=True, text=True, check=True, encoding="utf-8")
    lines = [ln for ln in r.stdout.splitlines() if ln.strip().startswith("{")]
    if not lines:
        raise SystemExit(f"no anduin type curve named {name!r}")
    return json.loads(lines[-1])


# anduin's own aggregation path (api/type_curves.py) on the CURRENT forecasts; stdin, nothing written.
_LIVE_PY = """
import json, logging, structlog
structlog.configure(wrapper_class=structlog.make_filtering_bound_logger(logging.ERROR))
from sqlalchemy import select
from app.db.session import SessionLocal
from app.db.models import TypeCurve, Well
from app.forecasting.orchestrator import df_terminal_for_cohort
from app.forecasting.types import ForecastConfig
from app.type_curves.loader import load_wells_with_forecast, cohort_ramp_anchors
from boxfit.tc.aggregate import aggregate
from boxfit.tc.fit_p50 import fit_p50_series
s = SessionLocal()
tc = s.execute(select(TypeCurve).where(TypeCurve.name == NAME).order_by(TypeCurve.created_at.desc())).scalars().first()
ids = list(tc.included_api10s)
a = cohort_ramp_anchors(s, tc, ids)
w = load_wells_with_forecast(s, tc, ids, alignment="peak_ramp", n_months=600, ramp_anchors=a)
agg = aggregate(w, normalization_basis="per_lateral_ft", alignment_method="peak_ramp", n_months=600)
df = df_terminal_for_cohort(s.execute(select(Well.subbasin).where(Well.api10.in_([x.api10 for x in w]))).scalars().all(), ForecastConfig())
out = {}
for st in ("oil", "gas", "water"):
    out[st] = {}
    for k in ("p50", "mean"):
        f = fit_p50_series(getattr(agg.streams[st], k), df_terminal_per_year=df)
        out[st][k] = None if f is None else f["eur_per_unit"]
s.rollback(); s.close()
print("LIVE" + json.dumps(out))
"""


def live_anduin(container: str, name: str) -> dict:
    code = f"NAME = {name!r}\n" + _LIVE_PY
    r = subprocess.run(["docker", "exec", "-i", container, "python", "-"], input=code, capture_output=True, text=True, check=True, encoding="utf-8")
    line = [ln for ln in r.stdout.splitlines() if ln.startswith("LIVE")][-1]
    return json.loads(line[4:])


def _params(row_params: dict, qo: float | None, pim: int | None) -> dict:
    p = dict(row_params or {})
    if qo is not None and "qo" not in p:
        p["qo"] = qo
    if pim is not None and "peak_index_months" not in p:
        p["peak_index_months"] = pim
    return p


def check_curve(container: str, name: str, backend: str | None = None) -> dict:
    d = fetch(container, name)
    live = live_anduin(backend, name) if backend else None
    tc_id, nm, api10s, overrides, align, basis, series, stale = (d[k] for k in ("id", "name", "api10s", "overrides", "align", "basis", "series", "stale"))
    if overrides:
        raise SystemExit(f"{name}: carries forecast_overrides — not a clean reference")
    if align != "peak_ramp" or basis != "per_lateral_ft":
        raise SystemExit(f"{name}: alignment {align} / basis {basis}, BOX path is peak_ramp per_lateral_ft")
    wells = {w["a"]: (w["lat"], w["sb"]) for w in d["wells"] or []}
    by: dict[str, dict[str, dict]] = {}
    for f in d["fc"] or []:
        by.setdefault(f["a"], {})[f["s"].lower()] = _params(f["p"], f["qo"], f["pim"])
    members = [tc.Member(api10=a, lateral_ft=wells.get(a, (None, None))[0], params={s: by.get(a, {}).get(s) for s in tc.STREAMS}) for a in api10s if a in by]
    subb = [wells.get(a, (None, None))[1] for a in api10s if a in by]
    df = 0.06 if sum(1 for s in subb if (s or "").strip().lower() == "midland") / max(len(subb), 1) > 0.5 else 0.08
    curve = tc.fit_curve(members, df_terminal=df, stats=("p50", "mean"), record="p50")
    out = {"curve": nm, "type_curve_id": str(tc_id), "saved_at": d["created_at"], "is_stale": bool(stale),
           "fc_rows_refit_after_save": int(d["fc_refit_after_save"] or 0), "fc_rows": len(d["fc"] or []), "n_included": len(api10s), "n_with_forecasts": len(members),
           "n_wells_aggregated": curve["n_wells"], "df_terminal": df, "streams": {}}
    worst = 0.0
    for s in tc.STREAMS:
        st = (series or {}).get("streams", {}).get(s, {})
        stored = {"p50": (st.get("fitted") or {}).get("eur_per_unit") if (st.get("fitted") or {}).get("mode") != "ratio" else None,
                  "mean": (st.get("fitted_eur_per_unit") or {}).get("mean")}
        if stored["p50"] is None:
            stored["p50"] = (st.get("fitted_eur_per_unit") or {}).get("p50")
        row = {}
        for k in ("p50", "mean"):
            f = curve["fits"][s].get(k)
            box_eur = None if not f else float(f["eur_per_unit"])
            rel = None if (box_eur is None or not stored[k]) else box_eur / float(stored[k]) - 1.0
            if rel is not None:
                worst = max(worst, abs(rel))
            lv = None if live is None else live[s][k]
            rel_live = None if (box_eur is None or not lv) else box_eur / float(lv) - 1.0
            row[k] = {"anduin_eur_per_kft": stored[k], "box_eur_per_kft": box_eur, "rel_diff": rel,
                      "anduin_live_eur_per_kft": lv, "rel_diff_live": rel_live,
                      "box_params": None if not f else {x: f[x] for x in ("qo", "qi", "Di", "b", "Df", "peak_index")}}
        out["streams"][s] = row
    out["max_abs_rel_diff"] = worst
    lives = [abs(v["rel_diff_live"]) for r_ in out["streams"].values() for v in r_.values() if v["rel_diff_live"] is not None]
    out["max_abs_rel_diff_live"] = max(lives) if lives else None
    out["pass_live_lt_0p1pct"] = None if not lives else max(lives) < 0.001
    out["pass_lt_0p1pct"] = worst < 0.001
    # A saved curve is only a reference while its members' forecasts are the ones it was built from:
    # anduin's global refits move them without marking the curve stale (a known loss path).
    out["reference_valid"] = out["pass_lt_0p1pct"] or out["fc_rows_refit_after_save"] == 0
    return out


def compare_well_fits(container: str, path: Path) -> dict:
    import numpy as np
    import pandas as pd

    wf = pd.read_csv(path, dtype={"api10": str})
    ids = ",".join(f"'{a}'" for a in wf["api10"] if a.isdigit())
    sql = (f"SELECT json_agg(json_build_object('a', api10, 's', stream::text, 'eur', eur, 'mo', manual_override, 'u', updated_at)) "
           f"FROM forecasts WHERE api10 IN ({ids})")
    cmd = ["docker", "exec", "-i", container, "psql", "-U", "permian", "-d", "permian", "-At"]
    r = subprocess.run(cmd, input="SET default_transaction_read_only = on;\n" + sql + ";\n", capture_output=True, text=True, check=True, encoding="utf-8")
    rows = json.loads([ln for ln in r.stdout.splitlines() if ln.startswith("[")][-1])
    an = pd.DataFrame(rows)
    out: dict = {"n_box_wells": len(wf)}
    for st in ("oil", "gas", "water"):
        a = an[(an["s"].str.lower() == st) & ~an["mo"].astype(bool)].set_index("a")["eur"]
        b = wf.set_index("api10")[f"{st}_eur"]
        j = pd.concat([a.rename("anduin"), b.rename("box")], axis=1, join="inner").dropna()
        j = j[(j.anduin > 0) & (j.box > 0)]
        rel = j.box / j.anduin - 1.0
        out[st] = {"n_common_machine_fits": len(j), "share_within_0p1pct": float((rel.abs() < 0.001).mean()) if len(j) else None,
                   "share_within_5pct": float((rel.abs() < 0.05).mean()) if len(j) else None,
                   "median_rel": float(rel.median()) if len(j) else None,
                   "p10_p90_rel": [float(np.percentile(rel, 10)), float(np.percentile(rel, 90))] if len(j) else None}
    return out


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--container", default="permian-postgres")
    ap.add_argument("--well-fits", type=Path, default=None, help="step-5b well_fits_WCA.csv to compare per well with anduin's forecasts")
    ap.add_argument("--backend", default="permian-backend", help="anduin backend container for the live recompute ('' to skip)")
    ap.add_argument("--curve", action="append", default=None)
    ap.add_argument("--out", type=Path, default=Path("docs") / "box" / f"step5b-{dt.datetime.now(tz=dt.UTC).astimezone():%Y-%m-%d}")
    a = ap.parse_args(argv)
    names = a.curve or ["vault_wca", "vault_wcxy"]
    res = [check_curve(a.container, n, a.backend or None) for n in names]
    wells = compare_well_fits(a.container, a.well_fits) if a.well_fits else None
    a.out.mkdir(parents=True, exist_ok=True)
    (a.out / "anduin_check.json").write_text(json.dumps({"checked_at": dt.datetime.now(tz=dt.UTC).astimezone().isoformat(timespec="seconds"), "curves": res,
                                                         "per_well": wells}, indent=2), encoding="utf-8")
    if wells:
        print("per-well BOX vs anduin stored EUR:", json.dumps({k: v for k, v in wells.items()}, default=str))
    for r in res:
        print(f"{r['curve']}: {r['n_wells_aggregated']} wells, max |rel diff| {r['max_abs_rel_diff']:.2e} -> {'PASS' if r['pass_lt_0p1pct'] else 'FAIL'}"
              f"  ({r['fc_rows_refit_after_save']}/{r['fc_rows']} member forecast rows refit after the curve was saved)"
              + ("" if r["max_abs_rel_diff_live"] is None else f"; vs anduin live recompute {r['max_abs_rel_diff_live']:.2e} -> {'PASS' if r['pass_live_lt_0p1pct'] else 'FAIL'}"))
        for s, row in r["streams"].items():
            print("   ", s, {k: (None if v["rel_diff"] is None else f"{v['rel_diff']:+.2e}") for k, v in row.items()})
    # exit 1 only for a real disagreement: a curve whose members were never refit and still differs
    ok_saved = all(r["pass_lt_0p1pct"] for r in res if r["fc_rows_refit_after_save"] == 0) and any(r["pass_lt_0p1pct"] for r in res)
    ok_live = all(r["pass_live_lt_0p1pct"] is not False for r in res)
    return 0 if ok_saved and ok_live else 1


if __name__ == "__main__":
    sys.exit(main())
