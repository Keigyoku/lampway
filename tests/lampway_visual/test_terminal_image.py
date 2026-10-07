# SPDX-FileCopyrightText: 2026 Lampway contributors
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""Contract 16's image fallback in the real build: inline images do not cross herdr (measured live), so an image path clicked
in the Lampway terminal shows in Blender's Image Editor."""

import harness


def test_a_clicked_image_shows_in_an_image_editor(tmp_path):
    report = harness.run_state("terminal_image", tmp_path)
    assert report["facts"]["shown"] == ["clicked.png"], report["facts"]
    assert report["facts"]["windows"] == 2, "the factory layout has no Image Editor: a new window, the user's areas untouched"
