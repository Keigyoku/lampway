# SPDX-FileCopyrightText: 2026 Lampway contributors
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""render_textured renders the parts set open in a .blend (its usage: ``blender -b <blend> -P render_textured.py -- ...``), so
its typed form's first field is that .blend and the runner opens it before the script (the captain's ruling 6: every batch
tool reachable from the Way). Every other Blender tool runs on an empty session as before."""

from types import SimpleNamespace

from mixar.modules.lampway_tools import runner as RUN
from mixar.modules.lampway_tools import settings as S


def test_render_textured_opens_its_blend_before_the_script(monkeypatch):
    monkeypatch.setattr(S, "blender_binary", lambda s: "/opt/blender")
    s = SimpleNamespace(nice=10)
    cmd = RUN.command("render_textured", ["set.blend", "proj", "out", "chest"], s)
    i = cmd.index("/opt/blender")
    assert cmd[i:i + 6] == ["/opt/blender", "-b", "set.blend", "--python-exit-code", "1", "-P"], cmd
    assert cmd[cmd.index("--") + 1:] == ["proj", "out", "chest"]
    other = RUN.command("bake_maps", ["a", "b"], s)
    assert other[other.index("-b") + 1] == "--python-exit-code", "an empty session for the others"
