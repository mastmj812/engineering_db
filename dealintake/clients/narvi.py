"""Thin narvi HTTP client (no auth; default http://127.0.0.1:8078).

Only the endpoints the deal-intake gates use. narvi owns gpkg parsing
(src/narvi/gpkg_reader.py is the canonical reader — this package does NOT
add a fourth copy), zone medians and stick generation. Shapes verified
against narvi backend/app 2026-09-18.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

import requests
from shapely.geometry import mapping, shape
from shapely.geometry.base import BaseGeometry

DEFAULT_URL = os.environ.get("NARVI_URL", "http://127.0.0.1:8078")


class NarviError(RuntimeError):
    pass


class Narvi:
    def __init__(self, base_url: str = DEFAULT_URL, timeout: float = 300.0) -> None:
        self.base = base_url.rstrip("/")
        self.timeout = timeout
        self.s = requests.Session()

    def _post(self, path: str, **kw: Any) -> Any:
        try:
            r = self.s.post(f"{self.base}{path}", timeout=self.timeout, **kw)
        except requests.ConnectionError as e:
            raise NarviError(f"narvi not reachable at {self.base} — start it (narvi\\start.ps1)") from e
        if r.status_code >= 400:
            raise NarviError(f"POST {path} -> {r.status_code}: {r.text[:500]}")
        return r.json()

    def upload_parcels(self, path: str | Path) -> list[dict[str, Any]]:
        """POST /api/parcels/upload (zip shapefile or gpkg). Returns parcels as
        {label, area_ac, geom (shapely, WGS84), attributes, tracts}. gpkg
        attributes (Min_Depth/Max_Depth text, WI/NRI) come back verbatim."""
        p = Path(path)
        with p.open("rb") as fh:
            data = self._post("/api/parcels/upload", files={"file": (p.name, fh)})
        out = []
        for pc in data["parcels"]:
            out.append({
                "label": pc["label"],
                "area_ac": pc["area_ac"],
                "geom": shape(pc["geojson"]),
                "attributes": pc.get("attributes") or {},
                "tracts": pc.get("tracts") or [],
            })
        return out

    def zones(self, parcel: BaseGeometry, formations: list[str], buffer_ft: float = 5280.0) -> dict[str, Any]:
        """POST /api/warehouse/zones -> {zones: [{formation, target_tvd_ft}] shallow->deep,
        stats: [{formation, wells, median_tvd_ft, multimodal, note}]}. Bimodal
        benches come back as CODE and CODE_b (strip `_b` before warehouse use)."""
        return self._post("/api/warehouse/zones", json={
            "parcel": mapping(parcel), "formations": formations, "buffer_ft": buffer_ft,
        })

    def azimuth(self, parcel: BaseGeometry, formations: list[str] | None = None) -> dict[str, Any]:
        """POST /api/warehouse/azimuth -> {azimuth_deg, coherence, wells,
        circ_std_deg, confident, note}. Use only when `confident`."""
        return self._post("/api/warehouse/azimuth", json={
            "parcel": mapping(parcel), "formations": formations, "buffer_ft": 5280.0,
        })

    def generate(
        self,
        parcel: BaseGeometry,
        zones: list[dict[str, Any]],
        *,
        setback_ft: float,
        spacing_ft: float,
        azimuth_deg: float | None = None,
        well_type: str = "single",
        setback_ns_ft: float | None = None,
        setback_ew_ft: float | None = None,
    ) -> dict[str, Any]:
        """POST /api/generate (winerack). PREVIEW only — nothing persists; the
        reviewer saves the scenario in narvi. Returns the raw response; legs are
        geojson features with kind='leg' (heel->toe, completed_lateral_ft)."""
        params: dict[str, Any] = {
            "spacing_ft": spacing_ft, "setback_ft": setback_ft,
            "azimuth_deg": azimuth_deg, "well_type": well_type,
        }
        if setback_ns_ft is not None:
            params["setback_ns_ft"] = setback_ns_ft
        if setback_ew_ft is not None:
            params["setback_ew_ft"] = setback_ew_ft
        return self._post("/api/generate", json={
            "parcel": mapping(parcel), "params": params, "mode": "winerack", "zones": zones,
        })


def legs(generate_response: dict[str, Any]) -> list[dict[str, Any]]:
    """Generated legs as {geom, formation, target_tvd_ft, completed_lateral_ft, ...}."""
    out = []
    for f in generate_response.get("geojson", {}).get("features", []):
        props = f.get("properties") or {}
        if props.get("kind") == "leg":
            out.append({**props, "geom": shape(f["geometry"])})
    return out
