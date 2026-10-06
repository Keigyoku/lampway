# SPDX-FileCopyrightText: 2026 Lampway contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""Contract 07, the Way: the tool sidebar as the captain's piece runbook, one panel per step in his order, a node for
this piece and a status word for the tool (backed by a report), typed tool forms instead of free text, and no work in a
draw."""

import ast
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

ROOT = Path(__file__).resolve().parents[2]
PANELS = ROOT / "src/scripts/mixar/modules/lampway_tools/ui/panels/lampway_panels.py"


class Recorder:
    def __init__(self, log=None):
        self.log = [] if log is None else log
        self.enabled = True
        self.alert = False

    def _child(self, *a, **_kw):
        return Recorder(self.log)

    row = column = box = split = _child

    def panel(self, idname, default_closed=False):
        return Recorder(self.log), Recorder(self.log)

    def label(self, text="", icon="NONE", icon_value=0, **_kw):
        self.log.append(("label", text, icon, icon_value))

    def operator(self, idname, text="", icon="NONE", **_kw):
        self.log.append(("op", idname, text, icon))
        return SimpleNamespace()

    def prop(self, data, name, text=None, **_kw):
        self.log.append(("prop", name, text))

    def popover(self, panel, text="", **_kw):
        self.log.append(("popover", panel, text))

    def separator(self, **_kw):
        pass


@pytest.fixture
def way(monkeypatch):
    from unittest.mock import MagicMock
    monkeypatch.setitem(sys.modules, "mathutils.bvhtree", MagicMock())
    for name in ("Panel", "Operator", "UIList", "PropertyGroup", "Menu"):
        monkeypatch.setattr(sys.modules["bpy.types"], name, object, raising=False)
    monkeypatch.delitem(sys.modules, "mixar.modules.lampway_tools.ui.panels.lampway_panels", raising=False)
    import importlib
    from mixar.modules.lampway_tools import the_way
    return the_way, importlib.import_module("mixar.modules.lampway_tools.ui.panels.lampway_panels")


def test_no_free_text_tool_runner():
    """No panel draws the free-text runners (tool + tool_args, feature + feature_args)."""
    tree = ast.parse(PANELS.read_text(encoding="utf-8"))
    drawn = {n.args[1].value for n in ast.walk(tree) if isinstance(n, ast.Call) and getattr(n.func, "attr", "") == "prop"
             and len(n.args) >= 2 and isinstance(n.args[1], ast.Constant)}
    assert not drawn & {"tool", "tool_args", "feature", "feature_args"}, drawn & {"tool", "tool_args", "feature", "feature_args"}


def test_panels_follow_the_runbook_order(way):
    """The Way's steps are the captain's piece runbook (BUILD_ORDER.md Wave 2) and the panels register in that order."""
    the_way, panels = way
    order = [s["id"] for s in the_way.steps()]
    assert order == ["seeds", "uv", "mesh_qa", "parts", "mesh_paint", "fit", "bind"]
    registered = [c.bl_idname for c in panels.classes if getattr(c, "bl_parent_id", "") == "LAMPWAY_PT_way"]
    assert registered == [f"LAMPWAY_PT_way_{s}" for s in order]


def test_every_status_word_has_a_source(way):
    the_way, _ = way
    for step in the_way.steps():
        assert step["status"] in ("live", "built", "partial", "planned"), step
        if step["status"] in ("live", "built", "partial"):
            assert step.get("source") and (ROOT / step["source"]).is_file(), step
    for tool, row in the_way.tool_status().items():
        if row["status"] in ("live", "built", "partial"):
            assert (ROOT / row["source"]).is_file(), (tool, row)


def test_planned_tool_has_no_run_button(way):
    the_way, panels = way
    layout = Recorder()
    the_way.draw_tool(layout, {"name": "lampway_auto_rig", "api": "auto_rig", "batch": None, "description": "rig", "params": []},
                      status={"status": "planned", "when": "Wave 3"})
    assert not [e for e in layout.log if e[0] == "op"], layout.log
    assert any("Planned, Wave 3" in e[1] for e in layout.log if e[0] == "label")


def test_qa_review_draw_makes_no_api_call(way, monkeypatch):
    the_way, panels = way
    from mixar.modules.lampway_tools import api
    monkeypatch.setattr(api, "qa_proposals", lambda *a, **k: (_ for _ in ()).throw(AssertionError("api call in draw")))
    layout = Recorder()
    scene = SimpleNamespace(lampway_tools=SimpleNamespace())
    panels.LAMPWAY_PT_qa_review.draw(SimpleNamespace(layout=layout), SimpleNamespace(scene=scene))


def test_the_node_says_where_this_piece_is(way):
    the_way, _ = way
    done = {"seeds", "uv"}
    assert [the_way.node(s["id"], done) for s in the_way.steps()][:4] == ["node_lit", "node_lit", "node_half", "node"]
    assert the_way.progress(done) == "2 of 7 done"


def test_a_typed_tool_builds_its_arguments_like_the_agent_does():
    """The form's values become the batch tool's argv exactly as the agent's call would (positional first, then flags)."""
    from mixar.modules.lampway_tools import tool_specs
    spec = {"name": "t", "batch": "pose_clearance", "params": [
        {"name": "piece", "type": "string", "flag": None, "repeat": False, "required": True},
        {"name": "views", "type": "array", "flag": "--view", "repeat": True, "required": False},
        {"name": "verbose", "type": "boolean", "flag": "--verbose", "repeat": False, "required": False},
        {"name": "scale", "type": "number", "flag": "--scale", "repeat": False, "required": False}]}
    assert tool_specs.argv(spec, {"piece": "urn.glb", "views": ["front", "back"], "verbose": True, "scale": 1.5}) == \
        ["urn.glb", "--view", "front", "--view", "back", "--verbose", "--scale", "1.5"]
    assert tool_specs.argv(spec, {"piece": "urn.glb", "verbose": False}) == ["urn.glb"]


def test_the_tool_specs_are_the_agents():
    import subprocess
    done = subprocess.run([sys.executable, str(ROOT / "scripts/lampway/facelift/tool_specs.py"), "--check"], capture_output=True,
                          text=True)
    assert done.returncode == 0, done.stdout + done.stderr


def test_every_tool_has_a_place(way):
    """A tool the agent gains appears in the Way: in a step, or named as off the Way with the reason. Without this, a tool
    the integration adds is simply absent from the sidebar and nothing says so."""
    import json
    import tomllib
    the_way, _ = way
    specs = json.loads((ROOT / "src/scripts/mixar/modules/lampway_tools/tool_specs.json").read_text(encoding="utf-8"))["tools"]
    off = tomllib.loads((ROOT / "src/scripts/mixar/modules/lampway_tools/status.toml").read_text(encoding="utf-8")).get("off_the_way", {})
    placed = {t for s in the_way.steps() for t in s.get("tools", [])}
    homeless = sorted(s["name"] for s in specs if s["name"] not in placed and s["name"] not in off)
    assert homeless == [], homeless
    assert all(isinstance(v, str) and v for v in off.values()), off
