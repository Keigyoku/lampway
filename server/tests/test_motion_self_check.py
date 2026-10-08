# SPDX-FileCopyrightText: 2026 Lampway contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""Synthetic pixel and audit plants for the motion self-check; no browser or media assets."""
from PIL import Image
import pytest

from lampway_server.motion import check as C


def text(**overrides):
    return {"sel": "#label", "text": "Label", "font_px": 24, "opacity": 1,
            "box": [30, 30, 70, 60], **overrides}


def contrast_image(background, foreground):
    im = Image.new("RGB", (100, 100), background)
    im.paste(foreground, (30, 30, 70, 60))
    return im


@pytest.mark.parametrize("background,foreground", [("black", "white"), ("white", "black")])
def test_contrast_works_without_the_new_pillow_pixel_api(monkeypatch, background, foreground):
    # Pillow >=10 is supported, but get_flattened_data is absent on older releases.
    monkeypatch.delattr(Image.Image, "get_flattened_data", raising=False)
    im = contrast_image(background, foreground)
    assert C.text_contrast(im, [30, 30, 70, 60]) == 21.0
    audit = {"text": [text()], "marks": []}
    assert C.findings(im, {"detail_share": 0.01}, audit, 100, 100) == []
    assert audit["text"][0]["contrast_measured"] == 21.0


@pytest.mark.parametrize("font_px,foreground,failed", [(22, 100, True), (24, 100, False), (24, 70, True)])
def test_measured_contrast_enforces_the_small_and_large_text_thresholds(font_px, foreground, failed):
    im = contrast_image("black", (foreground,) * 3)
    audit = {"text": [text(font_px=font_px)], "marks": []}
    found = C.findings(im, {"detail_share": 0.01}, audit, 100, 100)
    assert bool(found) is failed
    assert all(f["check"] == "legibility" and f["severity"] == "fail" for f in found)


def test_fading_text_is_not_contrast_checked():
    audit = {"text": [text(opacity=0.5)], "marks": []}
    assert C.findings(Image.new("RGB", (100, 100), "black"), {"detail_share": 0.01}, audit, 100, 100) == []
    assert "contrast_measured" not in audit["text"][0]


@pytest.mark.parametrize("detail_share,check,severity", [(0, "empty", "fail"), (C.EMPTY, "sparse", "warn"), (C.SPARSE, None, None)])
def test_detail_thresholds(detail_share, check, severity):
    found = C.findings(Image.new("RGB", (100, 100)), {"detail_share": detail_share}, {}, 100, 100)
    assert [(f["check"], f["severity"]) for f in found] == ([(check, severity)] if check else [])


@pytest.mark.parametrize("audit,check", [
    ({"text": [text(box=[4, 30, 70, 60], opacity=0.5)]}, "crop"),
    ({"text": [text(font_px=21, opacity=0.5)]}, "legibility"),
    ({"marks": [{"sel": "figure", "box": [-1, 10, 20, 20]}]}, "crop"),
    ({"text": [text(opacity=0.5)], "marks": [{"sel": "figure", "box": [50, 30, 80, 60]}]}, "overlap"),
    ({"text": [text(opacity=0.5)], "marks": [{"sel": "card1", "box": [50, 30, 80, 60]}]}, "overlap"),
])
def test_authored_geometry_plants(audit, check):
    found = C.findings(Image.new("RGB", (100, 100)), {"detail_share": 0.01}, audit, 100, 100)
    assert [(f["check"], f["severity"]) for f in found] == [(check, "fail")]


def test_card_tags_are_exempt_from_card_overlap():
    audit = {"text": [text(sel=".card .tag", opacity=0.5)], "marks": [{"sel": "card1", "box": [30, 30, 70, 60]}]}
    assert C.findings(Image.new("RGB", (100, 100)), {"detail_share": 0.01}, audit, 100, 100) == []
