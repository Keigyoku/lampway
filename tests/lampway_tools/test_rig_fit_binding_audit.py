# SPDX-FileCopyrightText: 2026 Lampway contributors
# SPDX-License-Identifier: GPL-3.0-or-later

"""Canon20 rigged examples: one replacement binding and REST-aligned inside rays."""

from features_support import run
from test_rig_fit_template import EXAMPLE

BIND = EXAMPLE + '''
J = measured(); original = body(J)
first = call("rig_fit_template", example="example", joints=joints_file("rig/a.json", J, original), out="rig/a.blend")
assert first["ok"], first
from mixar.modules.lampway_tools.features import rig_fit as RF
source = bpy.data.objects[first["rigged"]]
arm = bpy.data.objects[first["armature"]]
'''


def test_refitting_a_rigged_example_replaces_only_the_copy_binding(tmp_path):
    r = run(tmp_path, BIND + '''
source_groups = [(v.index, [(g.group, g.weight) for g in v.groups]) for v in source.data.vertices]
second = RF.fit(source.name, joints_file("rig/b.json", J, source), root, out="rig/b.blend")
output = bpy.data.objects[second["rigged"]]
mods = [m.object.name for m in output.modifiers if m.type == "ARMATURE"]
print("RESULT", json.dumps({"bindings": mods, "expected": second["armature"], "source_binding": [m.object.name for m in source.modifiers if m.type == "ARMATURE"],
    "source_weights_equal": source_groups == [(v.index, [(g.group, g.weight) for g in v.groups]) for v in source.data.vertices]}))
''', timeout=600)
    assert r.rc == 0, r.out[-3000:]
    d = r.results[0]
    assert d["bindings"] == [d["expected"]], d
    assert d["source_binding"] == ["example_rig"] and d["source_weights_equal"], d


def test_inside_rays_use_rest_and_restore_pose_even_after_query_failure(tmp_path):
    r = run(tmp_path, BIND + '''
arm.pose.bones["pelvis"].location = (10, 0, 0)
arm.pose.bones["pelvis"].keyframe_insert(data_path="location", frame=1)
bpy.context.scene.frame_set(1, subframe=0.25)
bpy.context.view_layer.update()
pose = {p.name: list(x for row in p.matrix_basis for x in row) for p in arm.pose.bones}
action = arm.animation_data.action
frame = (bpy.context.scene.frame_current, bpy.context.scene.frame_subframe)
inside = RF._inside(source, J)
old_tree = RF.BVHTree
class BrokenTree:
    @staticmethod
    def FromObject(*args):
        raise RuntimeError("planted BVH failure")
RF.BVHTree = BrokenTree
try:
    try:
        RF._inside(source, J)
    except RuntimeError as exc:
        failed = str(exc) == "planted BVH failure"
finally:
    RF.BVHTree = old_tree
print("RESULT", json.dumps({"inside": inside, "failed": failed, "pose_position": arm.data.pose_position,
    "pose_equal": pose == {p.name: list(x for row in p.matrix_basis for x in row) for p in arm.pose.bones},
    "action_equal": action is arm.animation_data.action, "frame_equal": frame == (bpy.context.scene.frame_current, bpy.context.scene.frame_subframe)}))
''', timeout=600)
    assert r.rc == 0, r.out[-3000:]
    d = r.results[0]
    assert set(d["inside"].values()) == {6}, d
    assert d["failed"] and d["pose_position"] == "POSE", d
    assert d["pose_equal"] and d["action_equal"] and d["frame_equal"], d


def test_replacement_copy_drops_old_armature_parent_preserving_world_and_source(tmp_path):
    r = run(tmp_path, BIND + '''
source.parent = arm
source.matrix_parent_inverse = Matrix.Identity(4)
bpy.context.view_layer.update()
world = [x for row in source.matrix_world for x in row]
inverse = [x for row in source.matrix_parent_inverse for x in row]
second = RF.fit(source.name, joints_file("rig/p.json", J, source), root, out="rig/p.blend")
output = bpy.data.objects[second["rigged"]]
print("RESULT", json.dumps({"parent":output.parent.name if output.parent else None,
    "source_parent":source.parent.name,"source_inverse_equal":inverse==[x for row in source.matrix_parent_inverse for x in row],
    "world_error":max(abs(a-b) for a,b in zip(world,[x for row in output.matrix_world for x in row]))}))
''', timeout=600)
    assert r.rc == 0, r.out[-3000:]
    d = r.results[0]
    assert d["parent"] is None, d
    assert d["source_parent"] == "example_rig" and d["source_inverse_equal"] and d["world_error"] <= 1e-6, d
