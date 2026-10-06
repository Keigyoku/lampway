# SPDX-FileCopyrightText: 2026 Lampway contributors
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""interior_diff (specs/mrmak/05-model-compare.md section 6.7 and the silhouette_compare amendment): what outline IoU cannot see, on the figure cells only."""

import sys
from pathlib import Path

import numpy as np
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src/scripts"))
from mixar.modules.lampway_tools.pipeline import interior_diff as ID  # noqa: E402


def sphere(n=160, dimple=0.0, holes=False):
    """A shaded sphere (lambert from the upper left) as (luminance, mask); ``dimple`` darkens a deep dent inside the figure without touching the outline."""
    y, x = np.mgrid[0:n, 0:n]
    cx = cy = n / 2
    r = n * 0.4
    d2 = ((x - cx) ** 2 + (y - cy) ** 2) / r ** 2
    mask = d2 <= 1.0
    z = np.sqrt(np.clip(1 - d2, 0, 1))
    lum = np.clip(0.2 + 0.8 * (0.5 * (x - cx) / r * -0.6 + 0.5 * (y - cy) / r * -0.6 + z * 0.55), 0, 1)
    if dimple:
        dd = ((x - (cx + 0.15 * r)) ** 2 + (y - (cy + 0.1 * r)) ** 2) / (0.35 * r) ** 2
        lum = np.where(dd < 1, lum * (1 - dimple * (1 - dd)), lum)
    if holes:
        hole = ((x - cx) ** 2 + (y - cy) ** 2) <= (0.12 * r) ** 2
        mask = mask & ~hole
    return lum * mask, mask


def test_outline_iou_cannot_tell_a_dimple_from_a_clean_sphere_but_the_interior_difference_does():
    a, ma = sphere()
    b, mb = sphere()
    c, mc = sphere(dimple=0.8)
    assert (ma & mb).sum() / (ma | mb).sum() == 1.0 and (ma & mc).sum() / (ma | mc).sum() == 1.0          # identical outlines
    same = ID.interior_diff(a, ma, b, mb)
    dimpled = ID.interior_diff(a, ma, c, mc)
    assert same["interior_diff"] < 1e-4 and dimpled["interior_diff"] > 0.02, (same, dimpled)
    assert same["cells_compared"] > 5000 and len(dimpled["interior_bands"]) == 10


def test_the_bands_locate_the_difference_by_height():
    a, ma = sphere()
    c, mc = sphere(dimple=0.8)
    bands = ID.interior_diff(a, ma, c, mc)["interior_bands"]
    assert max(bands) > 5 * (sorted(bands)[0] + 1e-6) and bands.index(max(bands)) in (4, 5, 6)               # the dent is near the middle of the figure, not at its top or bottom


def test_the_lattice_alignment_ignores_a_pure_translation_and_scale_of_the_figure():
    a, ma = sphere(n=160)
    small, msmall = sphere(n=96)
    d = ID.interior_diff(a, ma, small, msmall)
    assert d["interior_diff"] < 0.01                                                                          # bbox-aligned, so size and position do not count as a difference


def test_a_handful_of_cells_cannot_pass_as_evidence():
    lum = np.zeros((20, 20)); lum[9:11, 9:11] = 0.5
    mask = lum > 0
    d = ID.interior_diff(lum, mask, lum, mask)
    assert d["cells_compared"] < 50 and d["evidence"] == "insufficient" and ID.interior_diff(*sphere(), *sphere())["evidence"] == "ok"


def test_the_bounding_box_is_half_open():
    m = np.zeros((10, 12), bool); m[2:5, 3:9] = True
    assert ID.bbox(m) == (3, 2, 9, 5)                                                                          # (x0, y0, x1, y1) with x1, y1 exclusive: width 6, height 3


def test_an_enclosed_background_hole_is_found_and_the_outer_background_is_not():
    _l, solid = sphere()
    _l2, holed = sphere(holes=True)
    assert ID.enclosed_holes(solid) == {"count": 0, "area_frac": 0.0}
    h = ID.enclosed_holes(holed)
    assert h["count"] == 1 and 0.005 < h["area_frac"] < 0.1
    d = ID.interior_diff(*sphere(), *sphere(holes=True))
    assert d["hole_count_a"] == 0 and d["hole_count_b"] == 1


def test_empty_masks_are_refused():
    z = np.zeros((8, 8))
    with pytest.raises(ID.InteriorError, match="no figure"):
        ID.interior_diff(z, z > 0, z, z > 0)
