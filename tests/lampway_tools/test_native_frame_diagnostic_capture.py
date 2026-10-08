# SPDX-FileCopyrightText: 2026 Lampway contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""Private read-only capture explains strict convention sampling on native data."""
from pathlib import Path

from blender_run import run_script


def test_native_convention_capture_keeps_source_and_strict_verdict(tmp_path):
    script = Path(__file__).parents[2] / "scripts/lampway/read_native_frame_diagnostics.py"
    result = run_script("DIAG_PATH=" + repr(str(script)) + r'''
import bpy, json, importlib.util, numpy as np
from mixar.modules.lampway_tools.features import rig_tools as rt, normalize_rigged as nr
bpy.ops.object.armature_add()
ob = bpy.context.object
bpy.ops.object.mode_set(mode="EDIT")
root = ob.data.edit_bones[0]
root.name="joint"
root.head=(0,0,0); root.tail=(0,1,0)
child=ob.data.edit_bones.new("child")
child.head=(1,0.25,0); child.tail=(1,1.25,0); child.parent=root
bpy.ops.object.mode_set(mode="OBJECT")
def snapshot():
    return {"input":rt._fingerprint(ob, rt.read(ob)),
            "keys":sorted(ob.keys()), "objects":sorted(bpy.data.objects.keys()),
            "selection":sorted(o.name for o in bpy.context.selected_objects),
            "active":bpy.context.view_layer.objects.active.name}
before=snapshot()
spec=importlib.util.spec_from_file_location("native_frame_diagnostics", DIAG_PATH)
diag=importlib.util.module_from_spec(spec);spec.loader.exec_module(diag)
got=diag.collect(bpy,rt,nr,ob.name)
print("RESULT "+json.dumps({"unchanged":before==snapshot(),
     "class":got["convention"]["class"], "rows":got["convention"]["rows"],
     "outside":got["convention"]["outside_ue_y_bar"],
     "fingerprint_matches":got["rest_fingerprint"]==before["input"],
     "raw_count":len(got["rest_input"]["frames"]),
     "source_pins":sorted(got["loaded_modules"])}))
''', timeout=120)
    assert result.rc == 0, result.out[-2500:]
    got = result.results[-1]
    assert got["unchanged"] and got["fingerprint_matches"]
    assert got["class"] == "mixed" and got["outside"] == ["joint"]
    assert got["raw_count"] == 2
    assert got["rows"][0]["child"] == "child"
    assert got["source_pins"] == ["normalize_rigged", "rig_core", "rig_tools"]
