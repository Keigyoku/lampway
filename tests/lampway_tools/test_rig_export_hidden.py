# SPDX-FileCopyrightText: 2026 Lampway contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""Hidden source copies must still produce a complete, independently read FBX."""

from features_support import run
from test_rig_export_ue import CHAIN


def test_hidden_armature_and_skin_export_without_changing_source_visibility(tmp_path):
    result = run(tmp_path, CHAIN + '''
arm = chain("hidden_source")
skin = bpy.data.objects["hidden_source_skin"]
call("rig_inspect", armature=arm.name)
for ob in (arm, skin):
    ob.select_set(False)
    ob.hide_viewport = True
    ob.hide_render = True
    ob.hide_select = True
    ob.hide_set(True)
def source_state():
    return {ob.name: {"viewport": ob.hide_viewport, "render": ob.hide_render,
                     "select": ob.hide_select, "layer": ob.hide_get(),
                     "selected": ob.select_get(), "matrix": [list(row) for row in ob.matrix_world]}
            for ob in (arm, skin)}
before = source_state()
ids = set(bpy.data.objects.keys())
good = call("rig_export_ue", armature=arm.name, out="export/hidden.fbx")
after_good = source_state()
bad = call("rig_export_ue", armature=arm.name, out="export/hidden_wrong.fbx", recipe="cm_native_ue_axes")
print("RESULT", json.dumps({"good": good, "bad": bad, "before": before,
                           "after_good": after_good, "after_bad": source_state(),
                           "ids_restored": set(bpy.data.objects.keys()) == ids}))
''', timeout=600)
    assert result.rc == 0, result.out[-3000:]
    data = result.results[0]
    assert data["good"]["ok"], data["good"]
    assert data["good"]["readback"]["bones_compared"] == 5
    assert data["good"]["normals"]["unmatched_meshes"] == 0
    assert not data["bad"]["ok"] and "read-back" in data["bad"]["error"], data["bad"]
    assert data["before"] == data["after_good"] == data["after_bad"]
    assert data["ids_restored"]


def test_export_visibility_restores_source_flags_when_writer_raises(tmp_path):
    result = run(tmp_path, CHAIN + '''
from mixar.modules.lampway_tools.features.rig_export import _export_visibility
arm = chain("hidden_source")
skin = bpy.data.objects["hidden_source_skin"]
for ob in (arm, skin):
    ob.select_set(False)
    ob.hide_viewport = ob.hide_render = ob.hide_select = True
    ob.hide_set(True)
def flags():
    return [[ob.hide_viewport, ob.hide_render, ob.hide_select, ob.hide_get()]
            for ob in (arm, skin)]
before = flags()
try:
    with _export_visibility([arm, skin]):
        admitted = flags() == [[False] * 4] * 2
        raise RuntimeError("planted writer failure")
except RuntimeError as exc:
    caught = str(exc) == "planted writer failure"
print("RESULT", json.dumps({"admitted": admitted, "caught": caught, "restored": flags() == before}))
''')
    assert result.rc == 0, result.out[-3000:]
    assert result.results[0] == {"admitted": True, "caught": True, "restored": True}
