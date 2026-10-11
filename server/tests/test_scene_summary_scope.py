# SPDX-FileCopyrightText: 2026 Lampway contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""The maintained script pages the current scene, including its materials."""
import sys
from types import SimpleNamespace as NS

import pytest

from lampway_server.agent.tools import SCENE_SUMMARY, script_for


@pytest.mark.parametrize("args,names,next_offset", [
    ({"limit": 1}, ["Helmet"], 1),
    ({"limit": 1, "offset": 1}, ["Light"], None),
    ({"offset": 20}, [], None),
    ({"full": True, "offset": 1}, ["Helmet", "Light"], None),
])
def test_summary_excludes_other_tabs_and_unused_materials(monkeypatch, args, names, next_offset):
    bronze, old = NS(name="Bronze", users=2), NS(name="OtherTabMaterial", users=1)
    def obj(name, materials=()):
        return NS(name=name, type="MESH", location=(0, 0, 0), dimensions=(1, 1, 1),
                  parent=None, material_slots=[NS(material=m) for m in materials], hide_get=lambda: False)
    helmet, light, cube = obj("Helmet", [bronze, bronze]), obj("Light"), obj("Cube", [old])
    scene = NS(name="HelmetTab", frame_current=7, objects=[helmet, light])
    bpy = NS(data=NS(objects=[cube, helmet, light], materials=[old, bronze]),
             context=NS(scene=scene, selected_objects=[helmet], view_layer=NS(objects=NS(active=helmet))))
    monkeypatch.setitem(sys.modules, "bpy", bpy)
    scope = {}
    exec(script_for(SCENE_SUMMARY, args), scope)
    result = scope["__RESULT__"]
    assert result["scene"] == "HelmetTab" and result["object_count"] == 2
    assert [o["name"] for o in result["objects"]] == names
    assert result["next_offset"] == next_offset
    assert result["material_count"] == 1 and result["materials"] == [{"name": "Bronze", "users": 2}]
    assert result["selected"] == ["Helmet"] and result["active"] == "Helmet"
    assert bpy.data.objects == [cube, helmet, light] and scene.objects == [helmet, light]
