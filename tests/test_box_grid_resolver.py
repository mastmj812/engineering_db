"""DB-free tests for the BOX structure-grid resolver (box/extent_package.py): grids are keyed by
surface and found under either the 10-19 naming scheme or the September set's two schemes; a
missing grid is a loud warning, never a silent {}."""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pytest

from box import extent_package as pkg


def _write_grid(path: Path, z0: float, dip: float = 50.0) -> None:
    xs, ys = np.arange(0.0, 5 * 5000.0, 5000.0), np.arange(0.0, 5 * 5000.0, 5000.0)
    X, Y = np.meshgrid(xs, ys)
    np.savetxt(path, np.column_stack([X.ravel(), Y.ravel(), z0 + X.ravel() / dip]), delimiter=",", fmt="%.6f")


def test_resolves_new_scheme(tmp_path: Path) -> None:
    (tmp_path / "HCA_WOLFCAMP-B1_STRUCTURE_MD_grid.xyz").write_text("")
    (tmp_path / "HCA_WOLFCAMP_A_STRUCTURE_MD_grid.xyz").write_text("")
    assert pkg.grid_path("WOLFCAMP-B1", tmp_path) == tmp_path / "HCA_WOLFCAMP-B1_STRUCTURE_MD_grid.xyz"
    assert pkg.grid_path("WOLFCAMP_A", tmp_path) == tmp_path / "HCA_WOLFCAMP_A_STRUCTURE_MD_grid.xyz"


def test_resolves_original_schemes(tmp_path: Path) -> None:
    (tmp_path / "HCA_WOLFCAMP_A_STRUCTURE_MDXYZ_grid.xyz").write_text("")
    (tmp_path / "WOLFCAMP-B1-STRUCTUREXYZ_grid.xyz").write_text("")
    assert pkg.grid_path("WOLFCAMP_A", tmp_path) == tmp_path / "HCA_WOLFCAMP_A_STRUCTURE_MDXYZ_grid.xyz"
    assert pkg.grid_path("WOLFCAMP-B1", tmp_path) == tmp_path / "WOLFCAMP-B1-STRUCTUREXYZ_grid.xyz"


def test_missing_grid(tmp_path: Path) -> None:
    (tmp_path / "HCA_WOLFCAMP_A_STRUCTURE_MDXYZ_cont.xyz").write_text("")  # a companion is not the grid
    assert pkg.grid_path("WOLFCAMP_A", tmp_path) is None
    with pytest.raises(FileNotFoundError, match="WOLFCAMP_A"):
        pkg.require_grid("WOLFCAMP_A", tmp_path)


def test_every_pool_surface_names_a_surface() -> None:
    for top, base in pkg.GRIDS.values():
        for s in (top, base):
            assert not s.endswith(".xyz") and "STRUCTURE" not in s


def test_context_contours_missing_grid_warns(tmp_path: Path) -> None:
    _write_grid(tmp_path / "HCA_WOLFCAMP_A_STRUCTURE_MD_grid.xyz", 9000.0)
    with pytest.warns(UserWarning, match="WOLFCAMP-B1"):
        assert pkg.context_contours("WCA", None, grid_dir=tmp_path) == {}


def test_context_contours_mixed_schemes(tmp_path: Path) -> None:
    _write_grid(tmp_path / "HCA_WOLFCAMP_A_STRUCTURE_MD_grid.xyz", 9000.0)
    _write_grid(tmp_path / "WOLFCAMP-B1-STRUCTUREXYZ_grid.xyz", 9300.0, dip=25.0)  # thickens east: 300 -> 700 ft
    c = pkg.context_contours("WCA", None, grid_dir=tmp_path)
    assert c["struct"] and c["isopach"]
    assert min(lev for _, lev in c["isopach"]) >= 300.0 and max(lev for _, lev in c["isopach"]) <= 700.0
