# SPDX-FileCopyrightText: 2026 Lampway contributors
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""The first rig tools on real armatures (specs/canon/rig_tools: rig_inspect, rig_map, rig_normalize, the rig_export_ue read-back): every other
rig tool refuses an armature rig_inspect did not read; map.json is a receipt that reproduces byte for byte; normalize applies a scale exactly
(every rest joint and keyed pose stays where it was) or refuses; the read-back compares an FBX bone by bone at the bind_mismatch bars.
REAL binary."""

import json
from pathlib import Path

from features_support import run

MIXAMO = '''
def mixamo(name="mx", scale=1.0, loc=(0, 0, 0)):
    """A Mixamo-named armature (R01's names) with a torso missing spine_03/04, in metres."""
    joints = {"mixamorig:Hips": (None, (0, -0.02, 0.93)), "mixamorig:Spine": ("mixamorig:Hips", (0, -0.015, 0.99)),
              "mixamorig:Spine1": ("mixamorig:Spine", (0, -0.005, 1.06)), "mixamorig:Spine2": ("mixamorig:Spine1", (0, 0.0, 1.35)),
              "mixamorig:Neck": ("mixamorig:Spine2", (0, 0.0, 1.50)), "mixamorig:Head": ("mixamorig:Neck", (0, 0.0, 1.58)),
              "mixamorig:LeftShoulder": ("mixamorig:Spine2", (0.05, 0, 1.45)), "mixamorig:LeftArm": ("mixamorig:LeftShoulder", (0.18, 0, 1.42)),
              "mixamorig:LeftForeArm": ("mixamorig:LeftArm", (0.45, 0, 1.40)), "mixamorig:LeftHand": ("mixamorig:LeftForeArm", (0.70, 0, 1.38)),
              "mixamorig:LeftUpLeg": ("mixamorig:Hips", (0.10, 0, 0.90)), "mixamorig:LeftLeg": ("mixamorig:LeftUpLeg", (0.10, 0, 0.50)),
              "mixamorig:LeftFoot": ("mixamorig:LeftLeg", (0.10, 0, 0.08)), "mixamorig:LeftToeBase": ("mixamorig:LeftFoot", (0.10, -0.12, 0.02))}
    for k, (p, h) in list(joints.items()):
        if "Left" in k:
            r = k.replace("Left", "Right"); joints[r] = (p.replace("Left", "Right") if p else p, (-h[0], h[1], h[2]))
    arm = bpy.data.armatures.new(name); ob = link(bpy.data.objects.new(name, arm))
    bpy.context.view_layer.objects.active = ob; bpy.ops.object.mode_set(mode="EDIT")
    for k, (p, h) in joints.items():
        b = arm.edit_bones.new(k); b.head = h; b.tail = (h[0], h[1], h[2] + 0.05)
    for k, (p, h) in joints.items():
        if p: arm.edit_bones[k].parent = arm.edit_bones[p]
    kids = {}
    for k, (p, h) in joints.items():
        if p: kids.setdefault(p, []).append(k)
    for k in joints:                                   # Blender convention: each bone's tail on its single child's head
        if len(kids.get(k, [])) == 1:
            arm.edit_bones[k].tail = joints[kids[k][0]][1]
    bpy.ops.object.mode_set(mode="OBJECT")
    ob.scale = (scale, scale, scale); ob.location = loc; bpy.context.view_layer.update()
    return ob
'''


def test_inspect_reads_family_slots_convention_units_and_animation(tmp_path):
    r = run(tmp_path, MIXAMO + '''
ob = mixamo()
ob.animation_data_create(); act = bpy.data.actions.new("walk"); ob.animation_data.action = act
pb = ob.pose.bones["mixamorig:LeftArm"]; pb.rotation_mode = "QUATERNION"
for f in (1, 10): pb.keyframe_insert("rotation_quaternion", frame=f)
ob.pose.bones["mixamorig:Hips"].keyframe_insert("location", frame=1)
r = call("rig_inspect", armature="mx")
print("RESULT", json.dumps({"r": r, "stamp": ob.get("lw_rig_inspect")}))
''')
    assert r.rc == 0, r.out[-3000:]
    o = r.results[0]["r"]
    assert o["ok"] and o["bones"] == 22 and o["family"]["name"] == "mixamo" and o["family"]["hits"]["mixamo"] >= 20, o
    assert o["slots"]["missing_required"] == [] and o["slots"]["mapped"]["hand_l"] == "mixamorig:LeftHand", o["slots"]
    assert o["convention"]["class"] == "blender" and o["roots"] == ["mixamorig:Hips"], o["convention"]
    assert abs(o["units"]["height_m"] - 1.56) < 0.02 and o["units"]["factor"] == 1.0, o["units"]
    assert o["animation"]["actions"] == ["walk"] and o["animation"]["rotation_keys"] == 8 and o["animation"]["location_keys"] == 3, o["animation"]
    assert r.results[0]["stamp"] and o["sha256"]["input"], "the receipt stamps the armature: the other rig tools require it"


def test_map_writes_a_reproducible_receipt_with_synthesized_spine_and_refuses_the_uninspected(tmp_path):
    r = run(tmp_path, MIXAMO + '''
mixamo()
cold = call("rig_map", armature="mx", out="rig/mx.map.json")
call("rig_inspect", armature="mx")
a = call("rig_map", armature="mx", out="rig/mx.map.json")
b = call("rig_map", armature="mx", out="rig/mx.map.json")
bad = call("rig_map", armature="mx", family="rigify", out="rig/x.map.json")
ob = bpy.data.objects["mx"]; bpy.context.view_layer.objects.active = ob; bpy.ops.object.mode_set(mode="EDIT")
ob.data.edit_bones["mixamorig:LeftHand"].head.z += 0.05; bpy.ops.object.mode_set(mode="OBJECT")
moved = call("rig_map", armature="mx", out="rig/y.map.json")
print("RESULT", json.dumps({"cold": cold, "a": a, "b": b, "bad": bad, "moved": moved}))
''')
    assert r.rc == 0, r.out[-3000:]
    o = r.results[0]
    assert o["cold"]["ok"] is False and "rig_inspect" in o["cold"]["error"], o["cold"]
    m = json.loads((tmp_path / "rig/mx.map.json").read_text())
    assert m["schema"] == "lampway.rig-map/1" and m["family"] == "mixamo" and m["map"]["spine_05"] == {"source": "mixamorig:Spine2", "by": "table"}, m["map"].get("spine_05")
    assert set(m["synthesized"]) == {"spine_03", "spine_04"} and m["synthesized"]["spine_03"]["chain"] == "torso", m["synthesized"]
    f3, f4 = m["synthesized"]["spine_03"]["fraction"], m["synthesized"]["spine_04"]["fraction"]
    assert 0.0 < f3 < f4 < 1.0 and m["sha256"]["reference_rest"], m        # the reference (UE5 Manny) chain's own fractions
    assert "mixamorig:LeftToeBase" not in m["unmapped"] and m["required_set"] == "ue5_body", m["unmapped"]
    assert o["a"]["ok"] and o["b"]["ok"] and o["b"]["state"] == "unchanged", o["b"]
    assert o["bad"]["ok"] is False and "missing" in o["bad"]["error"] and "pelvis" in o["bad"]["error"], o["bad"]
    assert o["moved"]["ok"] is False and "changed since rig_inspect" in o["moved"]["error"], o["moved"]


def test_normalize_applies_scale_exactly_keeps_poses_and_refuses_a_non_uniform_animated_rig(tmp_path):
    r = run(tmp_path, MIXAMO + '''
ob = mixamo(name="u", scale=0.01, loc=(0.5, 0, 0))
ob.animation_data_create(); act = bpy.data.actions.new("a"); ob.animation_data.action = act
pb = ob.pose.bones["mixamorig:Hips"]
for f, z in ((1, 0.0), (8, 10.0)):
    pb.location = (0, 0, z); pb.keyframe_insert("location", frame=f)
def world(o):
    out = {}
    for f in (1, 4, 8):
        bpy.context.scene.frame_set(f)
        out[f] = {b.name: list(o.matrix_world @ b.head) for b in o.pose.bones}
    return out
before = world(ob)
call("rig_inspect", armature="u")
dry = call("rig_normalize", armature="u")
done = call("rig_normalize", armature="u", dry_run=False)
after = world(ob)
drift = max(max(abs(a - b) for a, b in zip(before[f][n], after[f][n])) for f in before for n in before[f])
n = mixamo(name="n"); n.scale = (2.0, 1.0, 1.0)
n.animation_data_create(); n.animation_data.action = bpy.data.actions.new("r")
q = n.pose.bones["mixamorig:Spine"]; q.rotation_mode = "XYZ"; q.keyframe_insert("rotation_euler", frame=1)
call("rig_inspect", armature="n")
refused = call("rig_normalize", armature="n", dry_run=False)
print("RESULT", json.dumps({"dry": dry, "done": done, "drift": drift, "scale": list(ob.scale), "refused": refused, "nscale": list(n.scale)}))
''')
    assert r.rc == 0, r.out[-3000:]
    o = r.results[0]
    assert o["dry"]["ok"] and o["dry"]["dry_run"] is True and o["dry"]["applied_scale"] == [0.01, 0.01, 0.01], o["dry"]
    assert o["done"]["ok"] and o["done"]["keys_scaled"]["fcurves"] == 3 and o["done"]["max_world_drift_m"] < 1e-6, o["done"]
    assert o["drift"] < 1e-6 and o["scale"] == [1.0, 1.0, 1.0], o
    assert o["refused"]["ok"] is False and "non-uniform" in o["refused"]["error"] and "mixamorig:Spine" in o["refused"]["error"], o["refused"]
    assert o["nscale"] == [2.0, 1.0, 1.0], "a refusal changes nothing"


def test_the_readback_compares_an_exported_fbx_bone_by_bone(tmp_path):
    r = run(tmp_path, MIXAMO + '''
ob = mixamo()
call("rig_inspect", armature="mx")
for o in bpy.context.scene.objects: o.select_set(o is ob)
bpy.context.view_layer.objects.active = ob
bpy.ops.export_scene.fbx(filepath=os.path.join(root, "good.fbx"), use_selection=True, add_leaf_bones=False, primary_bone_axis="Y", secondary_bone_axis="X")
bpy.ops.export_scene.fbx(filepath=os.path.join(root, "turned.fbx"), use_selection=True, add_leaf_bones=False, primary_bone_axis="X", secondary_bone_axis="-Y")
good = call("rig_readback", fbx="good.fbx", reference="mx")
turned = call("rig_readback", fbx="turned.fbx", reference="mx")
print("RESULT", json.dumps({"good": good, "turned": turned}))
''', timeout=600)
    assert r.rc == 0, r.out[-3000:]
    o = r.results[0]
    g = o["good"]
    assert g["ok"] and g["readback"]["bones_compared"] == 22 and g["readback"]["over_tolerance"] == [] and g["verdict"] == "PASS", g
    t = o["turned"]
    assert t["ok"] and t["verdict"] == "FAIL" and t["readback"]["worst_rotation_deg"] > 45, t["readback"]["worst_rotation_deg"]


def test_the_rigify_table_is_verified_against_a_generated_rigify_rig(tmp_path):
    """The shipped rigify table is a claim (canon 16 H.1: each table is verified against one real rig of its family): every name it maps exists
    on a Rigify human rig generated here, and the rig reads as rigify with no required slot missing."""
    r = run(tmp_path, '''
import addon_utils
addon_utils.enable("rigify", default_set=True)
bpy.ops.object.armature_human_metarig_add()
meta = bpy.context.active_object
bpy.ops.pose.rigify_generate()
rig = next(o for o in bpy.data.objects if o.type == "ARMATURE" and o is not meta)
from mixar.modules.lampway_tools.rig_tools import core as RC
table = RC.load_family("rigify")["map"]
absent = sorted(v for v in table.values() if v not in rig.data.bones)
ins = call("rig_inspect", armature=rig.name)
print("RESULT", json.dumps({"absent": absent, "family": ins["family"], "missing": ins["slots"]["missing_required"]}))
''', timeout=600)
    assert r.rc == 0, r.out[-3000:]
    o = r.results[0]
    assert o["absent"] == [], f"rigify table rows naming no bone of a generated Rigify rig: {o['absent']}"
    assert o["family"]["name"] == "rigify" and o["missing"] == [], o


def test_readback_success_and_partial_failure_restore_nested_ids_and_selection(tmp_path):
    r = run(tmp_path, MIXAMO + '''
from mixar.modules.lampway_tools import canon_io
from mixar.modules.lampway_tools.features import rig_tools as RT
ob = mixamo()
for x in bpy.context.scene.objects: x.select_set(x is ob)
bpy.context.view_layer.objects.active = ob
path = os.path.join(root,"nested.fbx")
bpy.ops.export_scene.fbx(filepath=path,use_selection=True,add_leaf_bones=False,primary_bone_axis="Y",secondary_bone_axis="X")
before = canon_io.snapshot_ids()
original = canon_io.import_raw
def nested(*a,**kw):
    rec = original(*a,**kw)
    bpy.data.node_groups.new("imported_nested","ShaderNodeTree")
    bpy.data.textures.new("imported_texture",type="IMAGE")
    return rec
canon_io.import_raw = nested
result = RT.readback(path,"mx",root)
clean = all(set(getattr(bpy.data,k)) == before[k] for k in canon_io._KINDS) and canon_io._selection() == before["selection"]
def partial(*a,**kw):
    bpy.data.node_groups.new("partial_nested","ShaderNodeTree")
    raise RuntimeError("partial readback")
canon_io.import_raw = partial
try:
    RT.readback(path,"mx",root)
except RuntimeError as error:
    failed = str(error) == "partial readback"
finally:
    canon_io.import_raw = original
print("RESULT",json.dumps({"clean":clean,"verdict":result["verdict"],"failed":failed,"partial_clean":all(set(getattr(bpy.data,k)) == before[k] for k in canon_io._KINDS) and canon_io._selection() == before["selection"]}))
''',timeout=300)
    assert r.rc == 0,r.out[-2000:]
    assert r.results[0] == {"clean":True,"verdict":"PASS","failed":True,"partial_clean":True}
