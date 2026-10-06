# SPDX-FileCopyrightText: 2026 Lampway contributors
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""The ported recipes import through canon_io, the one importer (DOOR.md 1): a real headless run reads an FBX the recipe way (anim-compare's
read_motion, over an animated armature exported here) and the import's datablocks carry lw_raw; the part-set tools' mesh_load does the
same for a GLB. REAL binary."""

import json
from pathlib import Path

from features_support import run

RC = Path(__file__).resolve().parents[2] / "src/scripts/mixar/modules/lampway_tools/rig_convert"
PARTSEG = Path(__file__).resolve().parents[2] / "src/scripts/mixar/modules/lampway_tools/scripts/partseg"


def test_read_motion_imports_through_canon_io_and_reads_the_samples(tmp_path):
    r = run(tmp_path, f'''
import sys, importlib.util
arm = bpy.data.armatures.new("rig"); ob = link(bpy.data.objects.new("rig", arm))
bpy.context.view_layer.objects.active = ob; bpy.ops.object.mode_set(mode="EDIT")
b = arm.edit_bones.new("root"); b.head = (0, 0, 0); b.tail = (0, 0, 0.5)
c = arm.edit_bones.new("arm"); c.head = (0, 0, 0.5); c.tail = (0, 0, 1.0); c.parent = b
bpy.ops.object.mode_set(mode="POSE")
scene = bpy.context.scene; scene.render.fps = 30
for f, ang in ((1, 0.0), (4, 0.6)):
    ob.pose.bones["arm"].rotation_mode = "XYZ"; ob.pose.bones["arm"].rotation_euler = (ang, 0, 0)
    ob.pose.bones["arm"].keyframe_insert("rotation_euler", frame=f)
bpy.ops.object.mode_set(mode="OBJECT")
path = os.path.join(root, "clip.fbx")
bpy.ops.export_scene.fbx(filepath=path, bake_anim=True, add_leaf_bones=False)
sys.path.insert(0, {str(RC)!r})
spec = importlib.util.spec_from_file_location("compare", {str(RC / "recipes/anim-compare-blender.py")!r})
m = importlib.util.module_from_spec(spec); spec.loader.exec_module(m)
import animation_canon as ac
got = m.read_motion(path, ac.sample_times("0.1"), ["root", "arm", "rig"])
arms = [o for o in bpy.data.objects if o.type == "ARMATURE"]
print("RESULT", json.dumps({{"samples": len(got["samples"]) if isinstance(got, dict) else len(got), "raw": ["lw_raw" in o.keys() for o in arms]}}))
''', timeout=300)
    assert r.rc == 0, r.out[-3000:]
    o = r.results[0]
    assert o["samples"] == 4 and o["raw"] == [True], o


def test_mesh_load_imports_a_glb_through_canon_io(tmp_path):
    r = run(tmp_path, f'''
import sys
boxes("piece", [((0, 0, 0.5), (1, 1, 1))])
bpy.ops.export_scene.gltf(filepath=os.path.join(root, "p.glb"), export_format="GLB")
sys.path.insert(0, {str(PARTSEG)!r})
import mesh_load
mesh_load.load(os.path.join(root, "p.glb"))
ms = [o for o in bpy.data.objects if o.type == "MESH"]
print("RESULT", json.dumps({{"meshes": len(ms), "raw": all("lw_raw" in o.keys() for o in ms)}}))
''', timeout=300)
    assert r.rc == 0, r.out[-3000:]
    assert r.results[0] == {"meshes": 1, "raw": True}, r.results[0]
