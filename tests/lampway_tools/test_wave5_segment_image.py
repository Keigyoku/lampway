# SPDX-FileCopyrightText: 2026 Lampway contributors
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""segment_image (specs/mixar_docs/segment_image.md): one image to per-part masks by connected components on the alpha channel (transparent plates) or on the foreground of an opaque sheet. Pure NumPy and
Pillow: no model, no network. The limits are documented by tests: touching parts are ONE component."""

import json

import numpy as np
import pytest
from PIL import Image

from mixar.modules.lampway_tools.pipeline import segment_image as SI  # noqa: E402


def sheet(discs, size=(240, 120), alpha=True, bg=(255, 255, 255)):
    yy, xx = np.mgrid[0:size[1], 0:size[0]]
    a = np.zeros((size[1], size[0]), dtype=np.uint8)
    rgb = np.zeros((size[1], size[0], 3), dtype=np.uint8)
    rgb[:] = bg if not alpha else (0, 0, 0)
    for k, (cx, cy, r) in enumerate(discs):
        m = (xx - cx) ** 2 + (yy - cy) ** 2 <= r * r
        a[m] = 255
        rgb[m] = (200, (40 + 50 * k) % 256, 60)
    if alpha:
        return Image.fromarray(np.dstack([rgb, a]), "RGBA")
    return Image.fromarray(rgb, "RGB")


THREE = [(40, 60, 25), (120, 60, 25), (200, 60, 25)]


def test_three_discs_are_three_masks_with_exact_bboxes_ordered_left_to_right(tmp_path):
    p = tmp_path / "plate.png"
    sheet(THREE).save(p)
    out = SI.segment(p, tmp_path / "out", method="alpha_components", min_pixels=100)
    assert out["ok"] and [m["index"] for m in out["masks"]] == [0, 1, 2]
    assert [m["bbox"] for m in out["masks"]] == [[15, 35, 66, 86], [95, 35, 146, 86], [175, 35, 226, 86]]
    for m in out["masks"]:
        im = Image.open(m["path"])
        assert im.mode == "L" and im.size == (240, 120) and set(np.unique(np.asarray(im))) == {0, 255}
        assert int((np.asarray(im) == 255).sum()) == m["pixels"]
    assert Image.open(out["overlay"]).size == (240, 120)


def test_two_touching_discs_are_one_component_the_documented_limit(tmp_path):
    p = tmp_path / "plate.png"
    sheet([(40, 60, 30), (90, 60, 30)]).save(p)                                                  # they overlap: 30 + 30 > 50 apart
    out = SI.segment(p, tmp_path / "out", method="alpha_components", min_pixels=100)
    assert len(out["masks"]) == 1 and "touching" in out["note"]


def test_min_pixels_drops_a_speck_and_the_dropped_count_is_reported(tmp_path):
    im = sheet(THREE)
    arr = np.asarray(im).copy()
    arr[5:8, 5:8] = (255, 255, 255, 255)                                                          # a 9 px speck
    p = tmp_path / "plate.png"
    Image.fromarray(arr, "RGBA").save(p)
    out = SI.segment(p, tmp_path / "out", min_pixels=100)
    assert len(out["masks"]) == 3 and out["dropped_below_min_pixels"] == 1
    out2 = SI.segment(p, tmp_path / "out2", min_pixels=1)
    assert len(out2["masks"]) == 4


def test_an_image_without_transparency_is_refused_with_the_named_fix_and_color_regions_handles_an_opaque_sheet(tmp_path):
    p = tmp_path / "opaque.png"
    sheet(THREE, alpha=False).save(p)
    with pytest.raises(SI.SegmentError, match="this image has no transparency: use color_regions or a model engine"):
        SI.segment(p, tmp_path / "o1", method="alpha_components")
    out = SI.segment(p, tmp_path / "o2", method="color_regions", min_pixels=100)
    assert len(out["masks"]) == 3 and out["background"] == [255, 255, 255]
    with pytest.raises(SI.SegmentError, match="model engines need a configured provider"):
        SI.segment(p, tmp_path / "o3", method="model")


def test_expected_parts_label_in_reading_order_only_when_the_count_matches(tmp_path):
    p = tmp_path / "plate.png"
    sheet(THREE).save(p)
    out = SI.segment(p, tmp_path / "o", min_pixels=100, expected_parts=["helmet", "cuirass", "greaves"])
    assert [m["label"] for m in out["masks"]] == ["helmet", "cuirass", "greaves"]
    out2 = SI.segment(p, tmp_path / "o2", min_pixels=100, expected_parts=["helmet", "cuirass"])
    assert [m["label"] for m in out2["masks"]] == [None, None, None] and "expected 2 parts, found 3" in out2["note"]


def test_too_many_components_and_oversized_images_are_refused_and_a_record_is_never_overwritten(tmp_path):
    many = [(10 + 14 * i, 10 + 14 * j, 4) for i in range(9) for j in range(8)]                    # 72 separate discs
    p = tmp_path / "many.png"
    sheet(many, size=(140, 120)).save(p)
    with pytest.raises(SI.SegmentError, match="too many components: raise min_pixels"):
        SI.segment(p, tmp_path / "m", min_pixels=10)
    big = tmp_path / "big.png"
    Image.new("RGBA", (4100, 4100), (0, 0, 0, 0)).save(big)
    with pytest.raises(SI.SegmentError, match="16 megapixels"):
        SI.segment(big, tmp_path / "b")
    q = tmp_path / "plate.png"
    sheet(THREE).save(q)
    SI.segment(q, tmp_path / "keep", min_pixels=100)
    SI.segment(q, tmp_path / "keep", min_pixels=100)                                               # the same result again is fine
    sheet([(40, 60, 20), (120, 60, 25), (200, 60, 25)]).save(q)
    with pytest.raises(SI.SegmentError, match="never overwrites a record"):
        SI.segment(q, tmp_path / "keep", min_pixels=100)
