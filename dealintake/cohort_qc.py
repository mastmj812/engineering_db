"""Gate 6: autoforecast QC over a TC cohort — flags only, never auto-drop.

Input rows are anduin GET /api/forecasts rows (one per well x stream):
api10, stream, di_initial (NOMINAL /yr), b, di_effective, fit_at_bound,
bound_note, eur (model 50-yr, bbl|mcf), well_lateral_ft, peak_index_months.

Di rule (Michael, 2026-09-18): the LEVEL of decline (~65-75% effective
yr-1 typical) varies by area/bench and is not a flag. DISPERSION within the
cohort is: 50% beside 70% means a different reservoir (unlikely over a small
area) or an unreliable autoforecast. Measured on 1-yr EFFECTIVE decline,
which folds b in — comparing nominal Di across different b misleads.
Water is reported, never flagged (TX water is often a vendor-calculated
flat WOR — sql/41).
"""

from __future__ import annotations

import statistics
from dataclasses import dataclass, field
from typing import Any

from dealintake.config import Config
from dealintake.decline import effective_from_nominal

STREAMS = ("oil", "gas", "water")


def _quantile(vals: list[float], q: float) -> float:
    s = sorted(vals)
    if len(s) == 1:
        return s[0]
    pos = q * (len(s) - 1)
    lo = int(pos)
    hi = min(lo + 1, len(s) - 1)
    return s[lo] + (s[hi] - s[lo]) * (pos - lo)


def robust_z(vals: list[float]) -> list[float | None]:
    """0.6745 (x - median) / MAD. None when MAD is 0 (no spread to judge)."""
    med = statistics.median(vals)
    mad = statistics.median(abs(v - med) for v in vals)
    if mad == 0:
        return [None] * len(vals)
    return [0.6745 * (v - med) / mad for v in vals]


@dataclass
class StreamQC:
    stream: str
    n: int
    de_median: float | None = None
    de_p25: float | None = None
    de_p75: float | None = None
    di_nominal_median: float | None = None
    b_median: float | None = None
    n_de_flagged: int = 0
    cohort_flag: str | None = None
    eur_per_1000ft_median: float | None = None
    flagged: bool = True  # False for report-only streams (water)


@dataclass
class QCResult:
    streams: dict[str, StreamQC] = field(default_factory=dict)
    well_flags: list[dict[str, Any]] = field(default_factory=list)


def run(rows: list[dict[str, Any]], cfg: Config) -> QCResult:
    q = cfg["qc_flags"]
    dd = q["di_dispersion"]
    pts = float(dd["well_points_from_median"]) / 100.0
    flag_streams = set(dd["streams_flagged"])
    out = QCResult()

    for stream in STREAMS:
        rs = [r for r in rows if r.get("stream") == stream]
        sq = StreamQC(stream=stream, n=len(rs), flagged=stream in flag_streams)
        out.streams[stream] = sq
        if not rs:
            continue

        # fit-at-bound: anduin recomputes against the stream's own Di cap
        # (water 12/yr) — pass through for every stream, flagged or not.
        for r in rs:
            if r.get("fit_at_bound"):
                out.well_flags.append(_flag(r, "fit_at_bound", r.get("bound_note") or "", "anduin bound check"))

        fit = [r for r in rs if r.get("di_initial") is not None and r.get("b") is not None]
        for r in fit:
            r["_de"] = effective_from_nominal(float(r["di_initial"]), float(r["b"]))
        if fit:
            des = [r["_de"] for r in fit]
            sq.de_median = statistics.median(des)
            sq.de_p25, sq.de_p75 = _quantile(des, 0.25), _quantile(des, 0.75)
            sq.di_nominal_median = statistics.median(float(r["di_initial"]) for r in fit)
            sq.b_median = statistics.median(float(r["b"]) for r in fit)
            for r in fit:
                dev = r["_de"] - sq.de_median
                if abs(dev) > pts:
                    sq.n_de_flagged += 1
                    if sq.flagged:
                        out.well_flags.append(_flag(
                            r, "di_dispersion",
                            f"{r['_de'] * 100:.1f}% eff ({float(r['di_initial']):.2f} /yr nom, b {float(r['b']):.2f}); "
                            f"{dev * 100:+.1f} pts vs cohort median {sq.de_median * 100:.1f}%",
                            f"+/-{dd['well_points_from_median']} pts",
                        ))
            iqr_pts = (sq.de_p75 - sq.de_p25) * 100
            frac = sq.n_de_flagged / len(fit)
            reasons = []
            if frac >= float(dd["cohort_flag_frac"]):
                reasons.append(f"{frac:.0%} of wells > {dd['well_points_from_median']} pts from median")
            if iqr_pts > float(dd["cohort_iqr_points"]):
                reasons.append(f"IQR {iqr_pts:.1f} pts > {dd['cohort_iqr_points']}")
            if reasons:
                prefix = "autoforecast reliability suspect: " if sq.flagged else "report-only: "
                sq.cohort_flag = prefix + "; ".join(reasons)

        # EUR per 1,000 ft robust outliers (flag, never drop).
        per = [
            (r, float(r["eur"]) / float(r["well_lateral_ft"]) * 1000.0)
            for r in rs
            if r.get("eur") is not None and r.get("well_lateral_ft")
        ]
        if per:
            sq.eur_per_1000ft_median = statistics.median(v for _, v in per)
            if len(per) >= 4 and sq.flagged:
                zmax = float(q["eur_ft_mad_z"])
                for (r, v), z in zip(per, robust_z([v for _, v in per])):
                    if z is not None and abs(z) > zmax:
                        out.well_flags.append(_flag(
                            r, "eur_per_1000ft_outlier",
                            f"{v:,.0f} per 1,000 ft (robust z {z:+.1f}; cohort median {sq.eur_per_1000ft_median:,.0f})",
                            f"|z| > {zmax}",
                        ))

        # Peak month vs the cohort's median peak for THIS stream (each stream
        # anchors on its own peak — gas commonly ~4 mo after oil).
        pk = [r for r in rs if r.get("peak_index_months") is not None]
        if pk and sq.flagged:
            med_pk = statistics.median(int(r["peak_index_months"]) for r in pk)
            tol = int(q["peak_month_tolerance"])
            for r in pk:
                if abs(int(r["peak_index_months"]) - med_pk) > tol:
                    out.well_flags.append(_flag(
                        r, "peak_month_vs_cohort",
                        f"peak month {int(r['peak_index_months'])} vs cohort median {med_pk:g}",
                        f"+/-{tol} mo",
                    ))
    return out


def _flag(r: dict[str, Any], flag: str, value: str, threshold: str) -> dict[str, Any]:
    di, b = r.get("di_initial"), r.get("b")
    return {
        "api10": r.get("api10"),
        "stream": r.get("stream"),
        "flag": flag,
        "value": value,
        "threshold": threshold,
        "di_nominal": di,
        "di_effective": effective_from_nominal(float(di), float(b)) if di is not None and b is not None else None,
        "b": b,
    }
