# SPDX-FileCopyrightText: 2026 Lampway contributors
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""rig_rest_pose (specs/canon/rig_tools/rig_rest_pose.md; canon 19 B.7-B.8, canon 04), REAL binary, golden R07 on C02's tube: the fit pose
made the rest of a COPY - the new rest mesh is LBS_P(v0) (= C02's posed mesh), every listed action re-expressed so the bones move as before,
no mesh joined, no UV layer renamed, no action deleted - and a receipt saying what a naive return through the new bind would cost (12.5 mm on
46 vertices) against the exact inverse (0). A changed rest is never changed again (no chaining); shape keys and non-uniform scale refuse."""

from pathlib import Path

from features_support import run

C02 = Path(__file__).resolve().parents[2] / "docs" / "canon" / "goldens" / "C02_inverse_lbs"

TUBE = f"C02 = {str(C02)!r}\n" + '''
w = json.loads(open(C02 + "/weights.json").read()); ex = json.loads(open(C02 + "/expected.json").read())
OBJ = [ln.split() for ln in open(C02 + "/piece_fit_pose.obj").read().splitlines()]
POSED = [[float(x) for x in l[1:4]] for l in OBJ if l and l[0] == "v"]
FACES = [[int(t.split("/")[0]) - 1 for t in l[1:]] for l in OBJ if l and l[0] == "f"]
def tube(name="tube"):
    arm = bpy.data.armatures.new(name); ob = link(bpy.data.objects.new(name, arm))
    bpy.context.view_layer.objects.active = ob; bpy.ops.object.mode_set(mode="EDIT")
    a = arm.edit_bones.new("A"); a.head, a.tail = w["heads"]["A"], (0, 0.1, 0)
    b = arm.edit_bones.new("B"); b.head, b.tail, b.parent = w["heads"]["B"], (0, 0.1, 0.3), a
    bpy.ops.object.mode_set(mode="OBJECT")
    me = bpy.data.meshes.new(name + "_skin"); me.from_pydata(ex["exact_inverse"]["rest_vertices"], [], FACES); me.uv_layers.new(name="paint")
    m = link(bpy.data.objects.new(name + "_skin", me))
    for k, n in enumerate(w["bones"]):
        g = m.vertex_groups.new(name=n)
        for i, row in enumerate(w["W"]):
            if row[k] > 0: g.add([i], row[k], "REPLACE")
    m.modifiers.new("Armature", "ARMATURE").object = ob
    ob.animation_data_create()
    fit = bpy.data.actions.new("fit"); ob.animation_data.action = fit
    pb = ob.pose.bones["B"]; pb.rotation_mode = "QUATERNION"; pb.rotation_quaternion = Quaternion((1, 0, 0), math.radians(60)); pb.keyframe_insert("rotation_quaternion", frame=1)
    wig = bpy.data.actions.new("wiggle"); ob.animation_data.action = wig
    for f in (1, 2, 3):
        ob.pose.bones["A"].rotation_mode = "QUATERNION"; ob.pose.bones["A"].rotation_quaternion = Quaternion((0, 0, 1), 0.2 * f)
        pb.rotation_quaternion = Quaternion((1, 0, 0), math.radians(20 * f)); ob.pose.bones["A"].location = (0.01 * f, 0, 0)
        for x in ("A", "B"):
            ob.pose.bones[x].keyframe_insert("rotation_quaternion", frame=f); ob.pose.bones[x].keyframe_insert("location", frame=f)
    ob.animation_data.action = None
    for x in ob.pose.bones: x.rotation_quaternion, x.location = (1, 0, 0, 0), (0, 0, 0)
    return ob, m
from mathutils import Quaternion
def evaluated(o):
    dg = bpy.context.evaluated_depsgraph_get(); e = o.evaluated_get(dg); me = e.to_mesh(); out = [list(o.matrix_world @ v.co) for v in me.vertices]; e.to_mesh_clear(); return out
'''


def test_r07_the_pose_becomes_the_rest_of_a_copy_and_the_return_cost_is_stated(tmp_path):
    r = run(tmp_path, TUBE + '''
ob, m = tube()
call("rig_inspect", armature="tube")
dry = call("rig_rest_pose", armature="tube", pose="action:fit:1", actions=["wiggle"])
done = call("rig_rest_pose", armature="tube", pose="action:fit:1", actions=["wiggle"], dry_run=False)
new, nm = bpy.data.objects.get("tube_rest2"), bpy.data.objects.get("tube_skin_rest2")
rest_new = [list(v.co) for v in nm.data.vertices] if nm else []
moved = max(max(abs(a - b) for a, b in zip(p, q)) for p, q in zip(rest_new, POSED)) if nm else None
bone_err = skin_err = blend_err = 0.0
rigid = [max(row) > 1 - 1e-12 for row in w["W"]]
for f in (1, 1.5, 2, 2.5, 3):                                                     # between keys too: the handles were mapped with the keys
    ob.animation_data.action = bpy.data.actions["wiggle"]; new.animation_data_create().action = bpy.data.actions.get("wiggle_rest2")
    bpy.context.scene.frame_set(0); bpy.context.scene.frame_set(int(f), subframe=f - int(f))   # a frame change re-evaluates the new actions
    for n in ("A", "B"):
        a, b = ob.matrix_world @ ob.pose.bones[n].matrix, new.matrix_world @ new.pose.bones[n].matrix
        bone_err = max(bone_err, (a.translation - b.translation).length, math.degrees(a.to_quaternion().rotation_difference(b.to_quaternion()).angle) / 1000)
    d = [max(abs(x - y) for x, y in zip(p, q)) for p, q in zip(evaluated(m), evaluated(nm))]
    skin_err = max(skin_err, max(e for e, r in zip(d, rigid) if r)); blend_err = max(blend_err, max(e for e, r in zip(d, rigid) if not r))
new.animation_data.action = None; bpy.context.scene.frame_set(0); bpy.context.scene.frame_set(3)
for pb in new.pose.bones: pb.matrix_basis = Matrix.Identity(4)                   # an unassigned action leaves its last values behind
bpy.context.view_layer.update()                  # the comparison is live: without its action the copy differs
live = (ob.matrix_world @ ob.pose.bones["B"].matrix).translation - (new.matrix_world @ new.pose.bones["B"].matrix).translation
live = live.length + math.degrees((ob.matrix_world @ ob.pose.bones["B"].matrix).to_quaternion().rotation_difference((new.matrix_world @ new.pose.bones["B"].matrix).to_quaternion()).angle)
ob.animation_data.action = None; bpy.context.scene.frame_set(1)
src_rest = max(max(abs(a - b) for a, b in zip(list(v.co), q)) for v, q in zip(m.data.vertices, ex["exact_inverse"]["rest_vertices"]))
call("rig_inspect", armature="tube_rest2")
chain = call("rig_rest_pose", armature="tube_rest2", pose="action:wiggle_rest2:2", dry_run=False)
print("RESULT", json.dumps({"dry": dry, "done": done, "moved": moved, "bone_err": bone_err, "skin_err": skin_err, "blend_err": blend_err, "live": live, "src_rest": src_rest, "chain": chain,
    "uv": [u.name for u in nm.data.uv_layers] if nm else None, "actions": sorted(a.name for a in bpy.data.actions), "objects": sorted(o.name for o in bpy.data.objects)}))
''', timeout=600)
    assert r.rc == 0, r.out[-3000:]
    o = r.results[0]
    assert o["dry"]["ok"] and o["dry"]["dry_run"] is True and o["dry"]["armature_out"] == "tube_rest2", o["dry"]
    d = o["done"]
    assert d["ok"] and d["dry_run"] is False and d["armature_out"] == "tube_rest2", d
    assert o["moved"] < 1e-6, "the new rest mesh is LBS_P(v0): C02's posed mesh"
    rc = d["return_cost"]["tube_skin"]
    assert abs(rc["blend_of_inverses_max_m"] - 0.0125) < 1e-4 and rc["vertices_over_1mm"] == 46 and rc["exact_return_max_m"] < 1e-9, rc
    assert d["meshes"]["tube_skin"]["out"] == "tube_skin_rest2" and d["meshes"]["tube_skin"]["moved_max_m"] > 0.01, d["meshes"]
    assert d["actions_rewritten"] == [{"source": "wiggle", "out": "wiggle_rest2", "frames": [1.0, 2.0, 3.0]}], d["actions_rewritten"]
    assert d["original_rest_sha256"] != d["new_rest_sha256"] and d["pose_sha256"], d
    assert o["bone_err"] < 1e-5 and o["skin_err"] < 1e-5, "the re-expressed action moves the bones and the rigid vertices as before"
    # a blended vertex cannot: a blend over a baked blend is not the original blend (canon 04) - the cost of any rest change, measured
    assert o["blend_err"] > 1e-3, o["blend_err"]
    assert o["live"] > 1.0, "without the rewritten action the copy is elsewhere: the comparison above is live"
    assert o["src_rest"] < 1e-6 and {"fit", "wiggle", "wiggle_rest2"} <= set(o["actions"]) and o["uv"] == ["paint"], o
    assert o["chain"]["ok"] is False and "already" in o["chain"]["error"] and "original" in o["chain"]["error"], o["chain"]


def test_rest_pose_refuses_shape_keys_non_uniform_scale_and_an_unknown_pose(tmp_path):
    r = run(tmp_path, TUBE + '''
ob, m = tube()
call("rig_inspect", armature="tube")
ref = call("rig_rest_pose", armature="tube", pose="reference")
bad = call("rig_rest_pose", armature="tube", pose="action:nope:1")
m.shape_key_add(name="Basis")
keys = call("rig_rest_pose", armature="tube", pose="action:fit:1", dry_run=False)
s, sm = tube("sq"); s.scale = (1, 2, 1); bpy.context.view_layer.update(); call("rig_inspect", armature="sq")
scaled = call("rig_rest_pose", armature="sq", pose="action:fit:1", dry_run=False)
print("RESULT", json.dumps({"ref": ref, "bad": bad, "keys": keys, "scaled": scaled}))
''', timeout=600)
    assert r.rc == 0, r.out[-3000:]
    o = r.results[0]
    assert o["ref"]["ok"] is False and "pose.json" in o["ref"]["error"], o["ref"]
    assert o["bad"]["ok"] is False and "nope" in o["bad"]["error"], o["bad"]
    assert o["keys"]["ok"] is False and "shape keys" in o["keys"]["error"], o["keys"]
    assert o["scaled"]["ok"] is False and "rig_normalize" in o["scaled"]["error"], o["scaled"]
