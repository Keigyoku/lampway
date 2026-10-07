# SPDX-FileCopyrightText: 2026 Lampway contributors
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""Contract 16's image fallback in the real build: inline images do not cross herdr (measured live), so an image path clicked
in the Lampway terminal shows in Blender's Image Editor."""

import harness


def test_a_clicked_image_shows_in_an_image_editor(tmp_path):
    report = harness.run_state("terminal_image", tmp_path)
    assert report["facts"]["shown"] == ["clicked.png"], report["facts"]
    f = report["facts"]
    assert f["in_main"] == [False] and "IMAGE_EDITOR" not in f["main_areas"], \
        ("the factory layout has no Image Editor: a new window shows it, the main window's areas untouched", f)
