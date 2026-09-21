"""Load + validate the versioned deal-intake thresholds (config/thresholds.yaml)."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml

DEFAULT_PATH = (
    Path(__file__).resolve().parent.parent
    / ".claude" / "skills" / "deal-intake" / "config" / "thresholds.yaml"
)

# Constants BAKED into curated.codev_context (sql/47). The runner refuses a
# config that disagrees: the matview cannot be re-sliced at other values.
CODEV_BAKED = {"xy_ft": 1320, "window_days": 180, "overlap_min_frac": 0.30}

TIERS = ("codev", "stack_standalone", "topfill_underfill")

_REQUIRED = {
    "config_version": (),
    "alignment": ("stick_inside_tolerance_ft", "fallback_scope"),
    "depth": ("edge_margin_ft",),
    "bench_inclusion": ("pdp_count_3mi_min",),
    "type_curve": ("first_prod_after", "min_months_data", "min_wells", "max_wells", "lateral_tolerance_by_basin"),
    "planned_lateral": ("setback_ft", "chord_step_ft"),
    "codev": ("xy_ft", "window_days", "overlap_min_frac", "tier_order_default",
              "tier_order_when_pdp_adjacent", "min_tier1_frac_warn"),
    "spacing": ("tight_below_frac", "sentinel_ft"),
    "qc_flags": ("peak_month_tolerance", "eur_ft_mad_z", "di_dispersion"),
    "split": ("min_wells_per_group", "median_ratio", "alpha"),
}


class ConfigError(ValueError):
    pass


@dataclass(frozen=True)
class Config:
    raw: dict[str, Any]
    path: Path

    @property
    def version(self) -> int:
        return int(self.raw["config_version"])

    def __getitem__(self, key: str) -> Any:
        return self.raw[key]

    def lateral_tolerance(self, basin: str | None) -> float:
        tol = self.raw["type_curve"]["lateral_tolerance_by_basin"]
        return float(tol.get((basin or "").lower(), tol["default"]))


def validate(raw: dict[str, Any]) -> None:
    for section, keys in _REQUIRED.items():
        if section not in raw:
            raise ConfigError(f"missing section: {section}")
        for k in keys:
            if k not in raw[section]:
                raise ConfigError(f"missing key: {section}.{k}")
    if int(raw["config_version"]) < 2:
        raise ConfigError("dealintake needs config_version >= 2")
    for k, v in CODEV_BAKED.items():
        if float(raw["codev"][k]) != float(v):
            raise ConfigError(
                f"codev.{k}={raw['codev'][k]} but curated.codev_context (sql/47) bakes {v}; "
                "change sql/47 and the config together or not at all"
            )
    for key in ("tier_order_default", "tier_order_when_pdp_adjacent"):
        order = raw["codev"][key]
        if sorted(order) != sorted(TIERS):
            raise ConfigError(f"codev.{key} must be a permutation of {TIERS}, got {order}")
    if int(raw["type_curve"]["max_wells"]) < int(raw["type_curve"]["min_wells"]):
        raise ConfigError("type_curve.max_wells must be >= min_wells")
    if raw["alignment"]["fallback_scope"] not in ("bench", "unit"):
        raise ConfigError("alignment.fallback_scope must be 'bench' or 'unit'")


def load(path: str | Path | None = None) -> Config:
    p = Path(path) if path else DEFAULT_PATH
    raw = yaml.safe_load(p.read_text(encoding="utf-8"))
    validate(raw)
    return Config(raw=raw, path=p)
