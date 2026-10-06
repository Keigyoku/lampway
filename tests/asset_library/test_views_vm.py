# SPDX-FileCopyrightText: 2026 Lampway contributors
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""The Vault's inspection views on the client (specs/asset_library/asset_ui_views.md sections 4-5, tests section 10.5-10.7): the flipbook clock, what each view says when its
products are missing, the compare refusal, the duplicate-frame chip, the normal map's convention stamp."""

from mixar.modules.asset_library.core import views as V


class Clock:
    t = 10.0

    def __call__(self):
        return self.t


def test_flipbook_play_toggle_advances_frame_at_requested_fps():
    clock = Clock()
    fb = V.Flipbook(clock=clock)
    fb.load([f"/d/turn_{i:03d}.jpg" for i in range(36)], fps=12)
    assert fb.frame == 0 and fb.playing is False
    clock.t += 1.0
    assert fb.advance() is False and fb.frame == 0, "paused: time passing moves nothing"
    fb.toggle()
    clock.t += 0.5
    assert fb.advance() is True and fb.frame == 6
    clock.t += 3.0                                   # 36 more frames at 12 fps: one full turn
    fb.advance()
    assert fb.frame == 6
    fb.set_fps(24)
    clock.t += 0.25
    fb.advance()
    assert fb.frame == 12
    fb.set_fps(99)
    assert fb.fps == 24 and (fb.set_fps(1) or fb.fps) == 6
    fb.scrub(40)
    assert fb.frame == 35 and fb.path() == "/d/turn_035.jpg"


def test_each_view_says_what_is_missing_and_what_to_run():
    empty = {"turntable": [], "ball": None, "overlay": None, "sheet": None, "thumb": None, "proxy": [], "strip": None}
    assert V.view_status("preview", {"kind": "mesh"}, empty) == "no turntable yet: queued (asset_render)"
    assert V.view_status("uv", {"kind": "mesh"}, empty) == "no UV overlay yet: queued (asset_render)"
    assert V.view_status("maps", {"kind": "texture_set"}, empty) == "no maps sheet yet: queued (asset_render)"
    assert V.view_status("video", {"kind": "video"}, empty) == "no proxy frames yet: queued (asset_video)"
    assert V.view_status("preview", {"kind": "mesh"}, {**empty, "turntable": ["/t0.jpg"]}) is None


def test_compare_needs_two_assets_of_the_same_kind():
    assert V.compare_refusal([]) == "compare needs two assets of the same kind: press Compare on two"
    assert V.compare_refusal([{"id": "a", "kind": "mesh"}]) == "compare needs two assets of the same kind: press Compare on a second mesh"
    assert V.compare_refusal([{"id": "a", "kind": "mesh"}, {"id": "b", "kind": "video"}]) == "compare needs two assets of the same kind: mesh and video differ"
    assert V.compare_refusal([{"id": "a", "kind": "image"}, {"id": "b", "kind": "image"}]) is None


def test_the_duplicate_frame_chip_shows_only_above_the_gate():
    assert V.dup_chip({"dup_ratio": 0.31, "dup_frames": 37}, gate=0.1) == {"text": "37 duplicate frames", "colour": "stop", "glyph": "cross"}
    assert V.dup_chip({"dup_ratio": 0.05, "dup_frames": 6}, gate=0.1) is None
    assert V.dup_chip({}, gate=0.1) is None


def test_the_motion_badge_names_container_and_motion_fps():
    assert V.fps_badge({"container_fps": 24.0, "motion_fps": 12.0}) == "24 fps file, 12 fps motion"
    assert V.fps_badge({"container_fps": 24.0}) == "24 fps file, motion not measured"


def test_normal_map_view_shows_convention_stamp():
    assert V.normal_stamp({"kind": "map", "subtype": "normal_dx", "stats": {}}) == "DX (green down)"
    assert V.normal_stamp({"kind": "map", "subtype": "normal_gl", "stats": {}}) == "GL (green up)"
    assert V.normal_stamp({"kind": "image", "stats": {"normal_convention": "dx"}}) == "DX (green down)"
    assert V.normal_stamp({"kind": "map", "subtype": "basecolor", "stats": {}}) is None
    assert V.normal_stamp({"kind": "map", "subtype": "normal_gl", "stats": {"convention": "unknown"}}) == "GL (green up)"
