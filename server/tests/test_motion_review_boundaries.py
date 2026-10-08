# SPDX-FileCopyrightText: 2026 Lampway contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""Real pixel plants around self-check thresholds and requested-format verify results."""
import io

from PIL import Image
import pytest

from lampway_server import motion as M
from lampway_server.motion import check as C
from .fake_motion import FakeCapture
from .test_motion_graphics import put_scene


@pytest.mark.parametrize("rectangle,check,severity", [
    ((6, 13), "empty", "fail"),
    ((6, 15), "sparse", "warn"),
    ((36, 138), "sparse", "warn"),
    ((36, 140), None, None),
])
def test_real_png_detail_is_gated_before_rounding(rectangle, check, severity):
    im = Image.new("RGB", (1920, 1080), "black")
    w, h = rectangle
    im.paste("white", (100, 100, 100 + w, 100 + h))
    png = io.BytesIO()
    im.save(png, "PNG")
    sampled, stats = C.frame_stats(png.getvalue())
    found = C.findings(sampled, stats, {}, *im.size)
    assert [(f["check"], f["severity"]) for f in found] == ([(check, severity)] if check else [])
    if rectangle == (6, 13):
        assert stats["detail_share"] == pytest.approx(50 / 516901)
        assert round(stats["detail_share"], 5) == C.EMPTY
    elif rectangle == (36, 138):
        assert stats["detail_share"] == pytest.approx(516 / 516901)
        assert round(stats["detail_share"], 5) == C.SPARSE


@pytest.mark.parametrize("background,foreground,font_px,failed", [
    (0, 89, 24, True),       # 2.99797456 rounds to 3.0 but is below 3:1.
    (0, 90, 24, False),
    (7, 119, 22, True),      # 4.49834809 rounds to 4.5 but is below 4.5:1.
    (7, 120, 22, False),
])
def test_real_rgb_contrast_is_gated_before_rounding(background, foreground, font_px, failed):
    im = Image.new("RGB", (100, 100), (background,) * 3)
    box = [30, 30, 70, 60]
    im.paste((foreground,) * 3, tuple(box))
    audit = {"text": [{"sel": "#label", "text": "Label", "font_px": font_px, "opacity": 1, "box": box}], "marks": []}
    found = C.findings(im, {"detail_share": 0.01}, audit, *im.size)
    assert [(f["check"], f["severity"]) for f in found] == ([("legibility", "fail")] if failed else [])
    if failed:
        threshold = 3.0 if font_px >= 24 else 4.5
        assert C.text_contrast(im, box) < threshold
        assert round(C.text_contrast(im, box), 2) == threshold


@pytest.mark.parametrize("formats", [["mp4"], ["webm"], ["mp4", "webm"]])
def test_engine_mismatch_keeps_unrequested_format_equality_null(tmp_path, formats):
    scene = put_scene(tmp_path, "format-boundary", "<!doctype html>")
    rendered = M.render(tmp_path, {"scene": scene, "fps": 2, "duration_s": 0.5,
                                   "width": 320, "height": 180, "formats": formats}, FakeCapture)
    cap = FakeCapture()
    cap.product = "FakeChrome/different"
    result = M.verify(tmp_path, {"receipt": rendered["out_dir"] + "/receipt.json"}, lambda: cap)
    assert result["engine_matches"] is False and result["reproduced"] is False
    assert cap.frames_asked == [], "engine mismatch must stop before recapturing any frame"
    assert result["integrity_matches"] is True
    for fmt in ("mp4", "webm"):
        assert result[fmt + "_equal"] is (False if fmt in formats else None)
