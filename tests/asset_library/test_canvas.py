# SPDX-FileCopyrightText: 2026 Lampway contributors
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""The Vault's pan/zoom canvas (specs/asset_library/asset_ui_views.md section 6): the screen <-> image mapping a gpu draw handler and a modal operator share. Pure math:
fit centres the picture, a wheel step zooms about the cursor (the image point under it stays under it), a drag pans, and a click maps back to image pixels (top-left
origin, as the lineage layout's node rects are) for the hit test."""

import pytest

from mixar.modules.asset_library.core.canvas import Canvas, ZOOM_MAX, ZOOM_MIN


def test_fit_centres_the_whole_picture_in_the_view():
    c = Canvas(view=(0, 0, 800, 600), image=(400, 200))
    c.fit()
    x0, y0, x1, y1 = c.quad()
    assert (x1 - x0) == pytest.approx(800) and (y1 - y0) == pytest.approx(400)
    assert (y0 + y1) / 2 == pytest.approx(300) and x0 == pytest.approx(0)


def test_zoom_keeps_the_point_under_the_cursor():
    c = Canvas(view=(0, 0, 800, 600), image=(400, 200))
    c.fit()
    before = c.to_image(600, 350)
    c.zoom_at(1.5, 600, 350)
    after = c.to_image(600, 350)
    assert after == pytest.approx(before)
    assert c.zoom == pytest.approx(c.fit_zoom * 1.5)


def test_zoom_is_clamped():
    c = Canvas(view=(0, 0, 800, 600), image=(400, 200))
    c.fit()
    for _ in range(100):
        c.zoom_at(2.0, 10, 10)
    assert c.zoom == pytest.approx(ZOOM_MAX)
    for _ in range(100):
        c.zoom_at(0.5, 10, 10)
    assert c.zoom == pytest.approx(ZOOM_MIN)


def test_pan_moves_the_picture_by_the_drag():
    c = Canvas(view=(0, 0, 800, 600), image=(400, 200))
    c.fit()
    q0 = c.quad()
    c.pan(30, -20)
    q1 = c.quad()
    assert q1[0] - q0[0] == pytest.approx(30) and q1[1] - q0[1] == pytest.approx(-20)


def test_a_click_maps_to_top_left_image_pixels_and_misses_outside():
    c = Canvas(view=(100, 50, 500, 250), image=(400, 200))
    c.fit()                                   # zoom 1: the picture fills the view exactly
    assert c.to_image(100, 250) == pytest.approx((0, 0)), "the view's top-left (Blender y-up) is image pixel (0, 0)"
    assert c.to_image(500, 50) == pytest.approx((400, 200))
    assert c.inside(300, 150) and not c.inside(90, 150)
