# SPDX-FileCopyrightText: 2026 Lampway contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""The turntable keeps its advertised rate when the main-thread poll is delayed."""
import math
import importlib.util
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

class Rotation:
    """Minimal rotation value for observing controller dispatch outside Blender."""
    def __init__(self, degrees=0.0):
        self.degrees = degrees

    def __iter__(self):
        return iter((self.degrees,))

    def __matmul__(self, other):
        return Rotation(self.degrees + other.degrees)

    def normalized(self):
        return self

    def copy(self):
        return Rotation(self.degrees)


@pytest.fixture
def turntable(monkeypatch):
    # The suite's bpy mock supplies mock base classes; use plain bases so the
    # real operator method and controller run rather than a MagicMock method.
    monkeypatch.setitem(sys.modules, "bpy.types", SimpleNamespace(Operator=object, Panel=object))
    path = Path(__file__).resolve().parents[1] / "src/scripts/mixar/modules/lampway_tools/ui/compare.py"
    spec = importlib.util.spec_from_file_location("spin_clock_compare", path)
    compare = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(compare)
    clock = SimpleNamespace(now=0.0)
    monkeypatch.setattr(compare, "time", SimpleNamespace(monotonic=lambda: clock.now), raising=False)
    monkeypatch.setitem(sys.modules, "mathutils", SimpleNamespace(
        Quaternion=lambda axis, angle: Rotation(math.degrees(angle))))
    views = [SimpleNamespace(view_rotation=Rotation(), view_location=[0.0, 0.0, 0.0], view_distance=1.0)
             for _ in range(4)]
    monkeypatch.setattr(compare, "STATE", {**compare.STATE, "areas": {k: k for k in range(4)},
                                        "last": None, "spin": False, "sync": True})
    monkeypatch.setattr(compare, "_compare_areas", lambda: [
        (None, SimpleNamespace(spaces=SimpleNamespace(active=SimpleNamespace(region_3d=view))))
        for view in views])
    toggle = compare.LAMPWAY_OT_compare_toggle()
    toggle.what = "spin"
    return clock, views, toggle, compare


@pytest.mark.parametrize("elapsed", [0.1, 1.5], ids=["nominal-poll", "delayed-main-thread-poll"])
def test_spin_advances_at_twenty_degrees_per_elapsed_second(turntable, elapsed):
    clock, views, toggle, compare = turntable
    assert toggle.execute(None) == {"FINISHED"}
    clock.now = elapsed
    assert compare._sync() == 0.1
    assert [view.view_rotation.degrees for view in views] == pytest.approx([20 * elapsed] * 4)


def test_manual_orbit_stops_spin_and_resume_excludes_time_spent_stopped(turntable):
    clock, views, toggle, compare = turntable
    toggle.execute(None)
    clock.now = 0.1
    compare._sync()
    views[0].view_rotation = Rotation(12)
    clock.now = 0.2
    compare._sync()
    assert compare.STATE["spin"] is False
    assert [view.view_rotation.degrees for view in views] == [12] * 4
    clock.now = 10.2
    compare._sync()
    assert [view.view_rotation.degrees for view in views] == [12] * 4
    toggle.execute(None)
    clock.now = 10.3
    compare._sync()
    assert [view.view_rotation.degrees for view in views] == pytest.approx([14] * 4)
