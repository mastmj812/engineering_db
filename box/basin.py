"""BOX basin parameters (Phase 3 step 19): every basin-specific literal on the production path, in one place.

A BOX build, pool refresh, bench QC, extent or record run names its basin; the modules read what differs from here instead of
carrying a Delaware literal. The Delaware values are the ones the Delaware record was built with, so a Delaware build is
bit-identical to the pre-step-19 code (gate 19). The Midland values are the gate-18 decisions; what step 20 / 21 still has to
measure is None, and the code that needs it refuses rather than borrowing the Delaware value.

    df_terminal       terminal decline, nominal /yr, of every cohort P50 fit (boxfit fit_p50_series): Delaware 0.08,
                      Midland 0.06 (D132)
    state_line_lat    bench QC's TX / NM split (Delaware 32.0 N); None = the basin has no state line (Midland is all Texas)
    pin_radius_ft,    the D23 edge metric, one value per basin: Delaware r = 2,640 ft / c = 3,960 ft (gate 2); the Midland
    closing_ft        adopts the same values (D134 A, gate 19); None = not set, and extent generation refuses
    grid_dirs         structure-grid folders under 'Engineering - General' (geology package context layers, D25 / D28);
                      () = none (no Midland grids exist)
    novi_basin        the Novi Snowflake report's basin token (basin_research__<token>__<vintage>)

One record run PER BASIN (D130, sql/70): box.forecast_run.basin, UNIQUE (basin) WHERE is_record.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Basin:
    name: str
    label: str
    df_terminal: float
    state_line_lat: float | None
    pin_radius_ft: float | None
    closing_ft: float | None
    grid_dirs: tuple[tuple[str, ...], ...]
    novi_basin: str


DELAWARE = "delaware"
MIDLAND = "midland"

BASINS: dict[str, Basin] = {
    DELAWARE: Basin(name=DELAWARE, label="Delaware", df_terminal=0.08, state_line_lat=32.0, pin_radius_ft=2640.0, closing_ft=3960.0,
                    grid_dirs=(("Grids", "Delaware", "Structure"), ("Structure Grids", "Delaware")), novi_basin="Delaware_Basin"),
    # D134 A (gate 19): the Midland adopts the Delaware D23 edge metric; reopened only if a Midland extent visibly fails
    MIDLAND: Basin(name=MIDLAND, label="Midland", df_terminal=0.06, state_line_lat=None, pin_radius_ft=2640.0, closing_ft=3960.0,
                   grid_dirs=(), novi_basin="Midland_Basin"),
}


def get(basin: str) -> Basin:
    """The basin's parameters; an unknown name is refused (never a silent Delaware default)."""
    try:
        return BASINS[basin]
    except KeyError:
        raise ValueError(f"unknown basin {basin!r}; known {sorted(BASINS)}") from None


def df_terminal(basin: str) -> float:
    return get(basin).df_terminal


def novi_report(basin: str, vintage: str) -> str:
    """The Novi Snowflake report name of a basin + vintage, e.g. basin_research__Delaware_Basin__2025Q3."""
    return f"basin_research__{get(basin).novi_basin}__{vintage}"


def require(value: float | None, basin: str, what: str, step: str) -> float:
    """A basin parameter that has to be measured before use (None) refuses with the step that measures it."""
    if value is None:
        raise ValueError(f"{basin}: {what} is not set; it is measured in {step}")
    return value
