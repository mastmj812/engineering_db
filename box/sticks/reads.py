"""Set-based inputs for the BOX sticks generator. Pilot (phase 3a): everything comes from the phase 3 cache frame
(scripts.box_sticks_phase3_pilot.build_frame), which was pulled read-only; nothing here writes anywhere.

The methods are the earlier phases', imported, not re-derived: the pair-link metric and the candidate D envelope
(phase 2b), the blended spacing surface (phase 2a), the landing chain (phase 1c), the DSU frame (phase 0).
"""
from __future__ import annotations

from dataclasses import replace

import numpy as np
import pandas as pd
import shapely
from pyproj import Transformer

from dealintake import geo

from .core import SECOND_LEVEL, Bench, Cfg, Dsu, Well, resolve_azimuth

SEP_MIN_DSU = 30                        # direct-direct DSUs needed before a separation band is used
SEARCH_M = 2640.0 / geo.FT_PER_M       # existing wells are read this far outside the DSU (the pair-link gate)
CARRIED = ("thickness", "bracket", "offset")


def direct_holdout() -> dict[tuple[str, str], tuple[float, float]]:
    """(median, P90) held-out error of the direct rung per (basin, code): reported on direct-rung sticks, never used to place."""
    from scripts import box_sticks_phase1c as p1c
    t = pd.read_csv(p1c.THICK_RANK.parent / "holdout_direct.csv")
    return {(r.basin, r.code): (round(float(r.median_ft), 1), round(float(r.p90_ft), 1)) for r in t.itertuples()}


def anchors_of(rung: str, how: object) -> tuple[str, ...]:
    return tuple(str(how).replace("+", "/").split("/")) if rung in CARRIED and isinstance(how, str) and how else ()


def link_fn():
    from scripts.box_sticks_phase2b import links
    return links


def default_cfg(basin: str) -> Cfg:
    from scripts import box_sticks_phase2b as p2b
    same_dh, rects = p2b.PROPOSED[basin]
    return Cfg(same_dv_ft=p2b.SAME_DV_FT, same_dh_ft=same_dh, min_overlap=p2b.MIN_OV, stacked=tuple(tuple(r) for r in rects))


class Context:
    """The cache frame plus the regional tables of rules 4 and 8, built once. `frame` and `measured` replace the cached
    frame and spacing gaps (the back-test passes the ones rebuilt without the hidden wells)."""

    def __init__(self, cache, frame: dict | None = None, measured: pd.DataFrame | None = None):
        from box import tag_scoreboard as sb
        from scripts import box_sticks_phase2a_bands as bands
        from scripts import box_sticks_phase2a_surface as sf
        from scripts import box_sticks_phase3_pilot as p3
        from scripts import box_sticks_phase3_regional as rg

        self.p3, self.rg, self.sf = p3, rg, sf
        F = self.F = frame if frame is not None else p3.build_frame(cache)
        self.order = sb.bench_order()
        self.direct_err = direct_holdout()
        self.to_work = Transformer.from_crs("EPSG:3083", f"EPSG:{geo.NARVI_WORK_EPSG}", always_xy=True)
        self.pads = F["pads"].set_index("pad_id")
        self.long_true = pd.Series(rg.long_axis_true(F["pads"]), index=F["pads"]["pad_id"].to_numpy())
        w = self.azw = rg.az_wells(F)
        self.az_of = pd.Series(w["az"].to_numpy(), index=w.index)
        county = w.groupby(["basin", "county"]).apply(rg.az_summary, include_groups=False)
        self.county = county[county["wells"] >= 25]["dominant_az_deg"].to_dict()
        cell = w.groupby(["basin", "cell_x", "cell_y"]).apply(rg.az_summary, include_groups=False)
        self.cell = {k: (float(r["dominant_az_deg"]), int(r["wells"])) for k, r in cell.iterrows()}
        self.az_tree = {b: (g, shapely.STRtree(shapely.points(g["x"].to_numpy(), g["y"].to_numpy()))) for b, g in w.groupby("basin")}
        t = rg.wca_table(F)
        t["cls"] = rg.wca_class(t, *rg.WCA_THRESHOLD)
        self.wca = t.set_index("pad_id")[["cls", "dominant"]].to_dict("index")
        tl = p3.two_landings(F)
        self.two = set(map(tuple, tl.loc[tl["two"], ["pad_id", "code"]].to_numpy()))
        self.levels = {(int(r.pad_id), r.code): (float(r.upper_ft), float(r.lower_ft)) for r in tl[tl["two"]].itertuples()}
        # separation between two benches where both depths are direct in the same DSU: the band a carried depth is checked against
        dd = F["db"][(F["db"]["rung"] == "direct") & F["db"]["z"].notna()]
        self.sep_band = {}
        for basin, g in dd.groupby("basin"):
            z = g.pivot_table(index="pad_id", columns="code", values="z", aggfunc="first")
            for a in z.columns:
                for b in z.columns:
                    if a != b:
                        v = (z[b] - z[a]).dropna()
                        if len(v) >= SEP_MIN_DSU:
                            self.sep_band[(basin, a, b)] = (float(v.quantile(0.025)), float(v.quantile(0.975)))
        self.m = measured if measured is not None else sf.measured(cache)
        self.band_median = bands.build(self.m, F["pads"], F["ext"])[2].set_index(["basin", "code", "band"])["median_ft"].to_dict()
        u, pre = F["u"], F["pre"]
        self.tree = {}
        for name, df in (("producer", u), ("preprod", pre)):
            for b in df["basin"].unique():
                ix = np.flatnonzero((df["basin"] == b).to_numpy())
                self.tree[(name, b)] = (ix, shapely.STRtree(df["geom"].to_numpy()[ix]))
        self.members = {"producer": F["wm"].groupby("pad_id")["i"].apply(set).to_dict(), "preprod": F["pm"].groupby("pad_id")["i"].apply(set).to_dict()}

    def work(self, g):
        return shapely.transform(g, lambda c: np.column_stack(self.to_work.transform(c[:, 0], c[:, 1])))

    def _wells(self, pid: int, basin: str, poly) -> list[Well]:
        F, out = self.F, []
        for name, df in (("producer", F["u"]), ("preprod", F["pre"])):
            if (name, basin) not in self.tree:
                continue
            ix, tree = self.tree[(name, basin)]
            mem = self.members[name].get(pid, set())
            geom, code, api = df["geom"].to_numpy(), df["live"].to_numpy(), df["api10"].to_numpy()
            planned = df["planned"].fillna(False).to_numpy(bool)
            ok = df["clean"].to_numpy(bool) & ~planned
            if "screen" in df:
                ok &= df["screen"].to_numpy() != "bad_depth"
            z = df["depth_ft"].to_numpy(float)
            for i in sorted(ix[tree.query(poly, predicate="dwithin", distance=SEARCH_M)]):
                if shapely.length(geom[i]) < 1.0:
                    continue
                out.append(Well(str(api[i]), None if pd.isna(code[i]) else str(code[i]), float(z[i]) if ok[i] and np.isfinite(z[i]) else None,
                                self.work(geom[i]), bool(i in mem), name, bool(planned[i])))
        return out

    def _azimuth(self, pid: int, r: pd.Series) -> tuple[float, str]:
        mem = [i for i in self.F["u"].index[sorted(self.members["producer"].get(pid, set()))] if i in self.az_of.index]
        g, tree = self.az_tree[r["basin"]]
        county = g["county"].to_numpy()[tree.nearest(shapely.Point(r["cx"], r["cy"]))]
        size = self.rg.CELL_MI * self.rg.MI
        cell = self.cell.get((r["basin"], int(np.floor(r["cx"] / size)), int(np.floor(r["cy"] / size))))
        return resolve_azimuth([float(self.az_of[i]) for i in mem], float(self.long_true[pid]), float(r["aspect"]), cell,
                               self.county.get((r["basin"], county)))

    def _spacing_basis(self, basin: str, code: str, poly, band: str) -> tuple[dict, float]:
        g = self.m[(self.m["basin"] == basin) & (self.m["live"] == code)]
        sg = 3.0
        d = shapely.distance(poly, shapely.points(g["x"].to_numpy(), g["y"].to_numpy())) / self.rg.MI
        k = d <= self.sf.CUT_SIGMA * sg
        med, neff = self.sf.wmedian(np.zeros(int(k.sum()), int), g["gap_ft"].to_numpy()[k], np.exp(-0.5 * (d[k] / sg) ** 2), 1)
        bm = self.band_median.get((basin, code, band))
        return {"n_eff": round(float(neff[0]), 2), "weighted_median_ft": None if np.isnan(med[0]) else round(float(med[0]), 1), "band": band,
                "band_ft": None if bm is None or np.isnan(bm) else round(float(bm), 1)}, float(neff[0])

    def dsu(self, pid: int) -> Dsu:
        r = self.pads.loc[pid]
        basin, poly = r["basin"], r["geom"]
        db = self.F["db"][self.F["db"]["pad_id"] == pid]
        benches = []
        direct = {b.code: float(b.z) for b in db.itertuples() if b.rung == "direct" and not pd.isna(b.z)}
        for b in db.itertuples():
            why = ""
            if b.rung in ("thickness", "bracket", "offset") and not pd.isna(b.z):
                for x, zx in sorted(direct.items()):
                    band = self.sep_band.get((basin, b.code, x))
                    slack = 0.0 if pd.isna(b.expected_p90_ft) else float(b.expected_p90_ft)
                    if band and not (band[0] - slack <= zx - float(b.z) <= band[1] + slack):
                        why = f"{x} direct at {zx:.0f} ft is {zx - float(b.z):+.0f} ft from this depth; {band[0]:.0f} to {band[1]:.0f} ft where both are direct"
                        break
            basis, neff = self._spacing_basis(basin, b.code, poly, b.edge_band)
            sec = getattr(b, "second_tvd_ft", np.nan)                           # absent in frames built before 0.10
            sec = None if b.rung != "thickness" or pd.isna(sec) else float(sec)
            flags = (("two_landings_observed",) if (pid, b.code) in self.two else ()) + ((SECOND_LEVEL,) if sec is not None else ())
            benches.append(Bench(code=b.code, rank=self.order[basin].index(b.code), tvd_ft=None if pd.isna(b.z) else float(b.z), rung=b.rung,
                                 spacing_ft=float(b.spacing_ft), inside_frac=float(b.inside_frac), control=neff,
                                 tvd_err_median_ft=None if pd.isna(b.expected_median_ft) else float(b.expected_median_ft),
                                 tvd_err_p90_ft=None if pd.isna(b.expected_p90_ft) else float(b.expected_p90_ft), spacing_basis=basis,
                                 flags=flags, second_tvd_ft=sec, anchors=anchors_of(b.rung, getattr(b, "how", None)),
                                 report_err=self.direct_err.get((basin, b.code)) if b.rung == "direct" else None,
                                 levels=self.levels.get((int(pid), b.code)), depth_check=why))
        az_true, basis = self._azimuth(pid, r)
        wca = self.wca.get(pid, {})
        return Dsu(pad_id=int(pid), basin=basin, polygon=self.work(poly), az_grid_deg=geo.narvi_azimuth(az_true, float(r["lon"]), float(r["lat"])),
                   az_true_deg=az_true, az_basis=basis, benches=benches, wells=self._wells(pid, basin, poly), wca_class=wca.get("cls"),
                   wca_dominant=wca.get("dominant"))


def with_basin(cfg: Cfg, basin: str) -> Cfg:
    return replace(cfg, **{k: getattr(default_cfg(basin), k) for k in ("same_dv_ft", "same_dh_ft", "min_overlap", "stacked")})
