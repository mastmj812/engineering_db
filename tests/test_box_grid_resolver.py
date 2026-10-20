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


# --- distance-to-well-control grids (2026-10-20): kind='dist_to_control', lattice check, trust mask ---

NULL = 9999999999.99
SURFACES_10_19 = ("1BSPGS", "2BSPGC", "2BSPGS", "3BSPGC", "3BSPGS", "AVALON1", "AVALON2", "BELL_CANYON", "BRUSHY_CANYON", "CHERRY_CANYON",
                  "DEVONIAN", "MISSISSIPPIAN", "STRAWN", "WOLFCAMP-B1", "WOLFCAMP-B2", "WOLFCAMP-C", "WOLFCAMP_A", "WOLFCAMP_D", "WOLFCAMP_XY", "WOODFORD")


def _write_xyz(path: Path, z: np.ndarray, step: float = 5000.0, nulls: tuple[tuple[int, int], ...] = ()) -> None:
    """Full lattice like the GGX export: row i = y, col j = x, nulls written as 9999999999.99."""
    z = np.array(z, dtype=float)
    for i, j in nulls:
        z[i, j] = NULL
    ys, xs = np.arange(z.shape[0]) * step, np.arange(z.shape[1]) * step
    X, Y = np.meshgrid(xs, ys)
    np.savetxt(path, np.column_stack([X.ravel(), Y.ravel(), z.ravel()]), delimiter=",", fmt="%.6f")


def _dist_eq_x(n: int = 5) -> np.ndarray:  # distance field = x, so bilinear is exact
    return np.tile(np.arange(n) * 5000.0, (n, 1))


def test_resolves_dist_kind_new_scheme(tmp_path: Path) -> None:
    (tmp_path / "HCA_WOLFCAMP_A_STRUCTURE_MD_grid.xyz").write_text("")
    (tmp_path / "HCA_WOLFCAMP_A_DIST_TO_CONTROL_ft_grid.xyz").write_text("")
    import warnings

    with warnings.catch_warnings():
        warnings.simplefilter("error")
        assert pkg.grid_path("WOLFCAMP_A", tmp_path) == tmp_path / "HCA_WOLFCAMP_A_STRUCTURE_MD_grid.xyz"
        assert pkg.grid_path("WOLFCAMP_A", tmp_path, kind="dist_to_control") == tmp_path / "HCA_WOLFCAMP_A_DIST_TO_CONTROL_ft_grid.xyz"
        assert pkg.require_grid("WOLFCAMP_A", tmp_path, kind="dist_to_control").name == "HCA_WOLFCAMP_A_DIST_TO_CONTROL_ft_grid.xyz"


def test_dist_kind_absent_in_september_scheme(tmp_path: Path) -> None:
    (tmp_path / "HCA_WOLFCAMP_A_STRUCTURE_MDXYZ_grid.xyz").write_text("")
    (tmp_path / "WOLFCAMP-B1-STRUCTUREXYZ_grid.xyz").write_text("")
    assert pkg.grid_path("WOLFCAMP-B1", tmp_path) == tmp_path / "WOLFCAMP-B1-STRUCTUREXYZ_grid.xyz"
    for s in ("WOLFCAMP_A", "WOLFCAMP-B1"):
        with pytest.warns(UserWarning, match=f"{s} dist_to_control"):
            assert pkg.grid_path(s, tmp_path, kind="dist_to_control") is None
    with pytest.raises(FileNotFoundError, match="dist_to_control.*DIST_TO_CONTROL"):
        pkg.require_grid("WOLFCAMP_A", tmp_path, kind="dist_to_control")


def test_unknown_kind_raises(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="isopach"):
        pkg.grid_path("WOLFCAMP_A", tmp_path, kind="isopach")


def test_check_same_lattice(tmp_path: Path) -> None:
    s, d = tmp_path / "s.xyz", tmp_path / "d.xyz"
    _write_xyz(s, 9000.0 + _dist_eq_x() / 50, nulls=((4, 4),))
    _write_xyz(d, _dist_eq_x(), nulls=((4, 4),))
    pkg.check_same_lattice(s, d)
    _write_xyz(d, _dist_eq_x(), nulls=((4, 3),))
    with pytest.raises(ValueError, match="mask differs at 2 nodes"):
        pkg.check_same_lattice(s, d)
    _write_xyz(d, _dist_eq_x(), step=4000.0, nulls=((4, 4),))
    with pytest.raises(ValueError, match="lattice differs"):
        pkg.check_same_lattice(s, d)


def test_dist_bilinear_null_and_off_lattice_nan(tmp_path: Path) -> None:
    _write_xyz(tmp_path / "HCA_WOLFCAMP_A_DIST_TO_CONTROL_ft_grid.xyz", _dist_eq_x(), nulls=((4, 4),))
    pts = [(2500.0, 0.0), (12345.0, 6000.0), (17500.0, 17500.0), (20000.0, 20000.0), (-100.0, 0.0), (20100.0, 0.0), (0.0, 25000.0)]
    d = pkg.dist_to_control("WOLFCAMP_A", pts, tmp_path)
    assert d.shape == (7,)
    np.testing.assert_allclose(d[:2], [2500.0, 12345.0])
    assert np.isnan(d[2:]).all()  # cell touching the null node, the null node itself, then off-lattice W / E / N


def test_dist_missing_grid_is_all_nan(tmp_path: Path) -> None:
    with pytest.warns(UserWarning, match="NO trust mask"):
        d = pkg.dist_to_control("WOLFCAMP_A", np.zeros((3, 2)), tmp_path)
    assert d.shape == (3,) and np.isnan(d).all()


def test_trust_mask_threshold(tmp_path: Path) -> None:
    assert pkg.TRUST_MAX_FT == 5280.0
    _write_xyz(tmp_path / "HCA_WOLFCAMP_A_DIST_TO_CONTROL_ft_grid.xyz", _dist_eq_x(), nulls=((4, 4),))
    pts = np.array([[0.0, 0.0], [5280.0, 0.0], [5281.0, 0.0], [10000.0, 0.0], [19000.0, 19000.0], [-1.0, 0.0]])
    assert pkg.trust_mask("WOLFCAMP_A", pts, grid_dir=tmp_path).tolist() == [True, True, False, False, False, False]
    assert pkg.trust_mask("WOLFCAMP_A", pts, max_ft=10000.0, grid_dir=tmp_path).tolist() == [True, True, True, True, False, False]


@pytest.mark.skipif(not pkg.GRID_DIR.exists(), reason="Holden's 10-19 grid folder not on this machine")
def test_smoke_real_dist_grids() -> None:
    """Real delivery: every surface has a DIST grid, node-for-node with its STRUCTURE partner."""
    for s in SURFACES_10_19:
        sp, dp = pkg.require_grid(s), pkg.require_grid(s, kind="dist_to_control")
        pkg.check_same_lattice(sp, dp)
        xs, ys, D = pkg._grid(dp)
        assert D.shape == (163, 124) and np.nanmin(D) >= 0.0
        ok = np.isfinite(D)
        inner = ok[1:-1, 1:-1] & ok[:-2, 1:-1] & ok[2:, 1:-1] & ok[1:-1, :-2] & ok[1:-1, 2:]  # node + 4 neighbours populated
        i, j = np.argwhere(inner)[len(np.argwhere(inner)) // 2] + 1
        assert pkg.dist_to_control(s, [(xs[j], ys[i])])[0] == pytest.approx(D[i, j], abs=1e-3)
