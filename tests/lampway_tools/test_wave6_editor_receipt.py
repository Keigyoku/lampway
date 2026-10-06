# SPDX-FileCopyrightText: 2026 Lampway contributors
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""editor_connection_receipt (specs/wiki/editor_connection_receipt.md) in the real binary: a typed receipt of which editor, version and project the agent is
really connected to, with a disposable create-then-remove test whose object list must come back equal. Blender is native; Unity and Godot facts are validated
and stored; the Unreal leg is needs_decision until the render-parity exploration settles the UE side."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from wave6_support import go, one  # noqa: E402

SAVED = '''
sphere("a", 0.2); sphere("b", 0.2, loc=(1, 0, 0)); sphere("c", 0.2, loc=(2, 0, 0)); sphere("d", 0.2, loc=(3, 0, 0))
bpy.ops.wm.save_as_mainfile(filepath=os.path.join(root, "copy.blend"))
'''


def test_receipt_records_version_path_and_the_create_then_undo_restores_the_object_list(tmp_path):
    d = one(go(tmp_path, SAVED + '''
res = call("editor_connection_receipt", editor="blender", disposable=True, position=[0, 0, 5], transport="bridge", release="lampway-0.1")
print("RESULT", json.dumps({"res": res, "objects": sorted(o.name for o in bpy.data.objects), "meshes": sorted(m.name for m in bpy.data.meshes),
                            "version": bpy.app.version_string, "receipt": json.load(open(os.path.join(root, res["receipt_path"]))) if res.get("ok") else None}))
'''))
    res = d["res"]
    assert res["ok"], res
    assert res["editor"] == "blender" and res["editor_version"] == d["version"] and res["project_path"] == "copy.blend" and res["scene"] == "Scene"
    assert res["objects_before"] == ["a", "b", "c"] and res["object_count_before"] == 4
    assert res["test"] == {"created": True, "name": "TestConnectionCube", "location": [0.0, 0.0, 5.0], "undone": True, "objects_after_equal_before": True}
    assert d["objects"] == ["a", "b", "c", "d"] and "TestConnectionCube" not in d["meshes"]
    assert d["receipt"]["test"]["objects_after_equal_before"] is True and d["receipt"]["transport"] == "bridge"


def test_disposable_false_and_an_unsaved_or_outside_project_are_refused_before_any_mutation(tmp_path):
    d = one(go(tmp_path, '''
sphere("a", 0.2)
nodisp = call("editor_connection_receipt", editor="blender", disposable=False)
unsaved = call("editor_connection_receipt", editor="blender", disposable=True)
print("RESULT", json.dumps({"nodisp": nodisp, "unsaved": unsaved, "objects": sorted(o.name for o in bpy.data.objects)}))
'''))
    assert d["nodisp"]["ok"] is False and "the create-undo test runs in a disposable copy only" in d["nodisp"]["error"]
    assert d["unsaved"]["ok"] is False and "identity" in d["unsaved"]["error"] and d["objects"] == ["a"]


def test_other_editors_store_validated_facts_and_unreal_is_needs_decision(tmp_path):
    d = one(go(tmp_path, '''
facts = {"editor_version": "6000.0.23f1", "connector_release": "v10.0.0", "project_path": "UnityCopy", "scene": "SampleScene", "read_tool": "get_hierarchy", "undo_outcome": "removed"}
unity = call("editor_connection_receipt", editor="unity", disposable=True, transport="mcp_stdio", facts=facts)
missing = call("editor_connection_receipt", editor="godot", disposable=True, transport="mcp_stdio")
unreal = call("editor_connection_receipt", editor="unreal", disposable=True, transport="mcp_http", facts=facts)
print("RESULT", json.dumps({"unity": unity, "missing": missing, "unreal": unreal}))
'''))
    assert d["unity"]["ok"] and d["unity"]["editor_version"] == "6000.0.23f1" and d["unity"]["receipt_path"].startswith("receipts/")
    assert d["missing"]["ok"] is False and "not connected" in d["missing"]["error"]
    assert d["unreal"]["ok"] is True and d["unreal"]["state"] == "needs_decision" and "parity" in d["unreal"]["reason"]
