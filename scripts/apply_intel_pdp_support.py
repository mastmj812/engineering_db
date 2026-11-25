"""RETIRED (2026-11-25). curated.intel_pdp_support (sql/30) is dropped and must not be rebuilt.

BOX sticks phase 8 (docs/box_sticks_plan.md): locations are BOX sticks, Novi Intelligence is comparison only. The
matview scored Novi sticks and had no reader left; it was 100 of the 111 rebuild minutes of a quarterly reload. The score
of record is the function curated.pdp_support_for_geom (sql/48), live for any stick. The last real body of this script is
at commit eb3d0d3.
"""

from __future__ import annotations

RETIRED = "curated.intel_pdp_support is retired (BOX sticks phase 8): not rebuilt. Use curated.pdp_support_for_geom (sql/48)."


def main() -> None:
    raise SystemExit(RETIRED)


if __name__ == "__main__":
    main()
