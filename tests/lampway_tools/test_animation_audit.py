# SPDX-FileCopyrightText: 2026 Lampway contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""Actual audit contracts: unsided labels and meaningful skin diagnostics."""
from test_wave4_retarget import run


def test_auto_mapping_accepts_unsided_neck_and_root_without_baking():
    r = run('''
for arm in (src, tgt):
    bpy.context.view_layer.objects.active = arm
    bpy.ops.object.mode_set(mode="EDIT")
    for name, z in (("neck_01", 1.5), ("root", 0.0)):
        bone = arm.data.edit_bones.new(name)
        bone.head, bone.tail = (0, 0, z), (0, 0, z + 0.1)
    bpy.ops.object.mode_set(mode="OBJECT")
before = len(bpy.data.actions)
out = api.animation_retarget("src", "tgt", dry_run=True)
res({"out": out, "same": before == len(bpy.data.actions)})
''')
    assert r.rc == 0, r.out[-2000:]
    d = r.results[-1]
    assert d["out"]["ok"] and d["same"], d
    assert {"neck", "root"} <= {p["label"] for p in d["out"]["mapping"]}


def test_skin_check_refuses_an_object_bound_to_a_different_rig_before_baking():
    r = run('''
mesh = tube("source_skin", r=0.05, z0=1.46, z1=1.7, seg=8, rings=3)
weights(mesh, src, lambda c: {"spine_01": 1.0})
before = len(bpy.data.actions)
out = api.animation_retarget("src", "tgt", check_objects=[mesh.name])
res({"out": out, "same": before == len(bpy.data.actions)})
''')
    assert r.rc == 0, r.out[-2000:]
    d = r.results[-1]
    assert not d["out"]["ok"] and d["same"], d
    assert "target" in d["out"]["error"]


def test_in_place_motion_does_not_claim_world_foot_plant_acceptance():
    r = run('''
out = api.animation_retarget("src", "tgt", root_motion="in_place")
res(out)
''')
    assert r.rc == 0, r.out[-2000:]
    out = r.results[-1]
    assert out["ok"]
    assert out["quality"]["accepted"] is False
    assert out["quality"]["foot_slide"]["space"] == "in_place"
    assert out["quality"]["foot_slide"]["status"] == "unmeasured_world_contact"
    assert any("root_motion" in warning for warning in out["warnings"])


def test_stretch_uses_true_rest_mesh_even_when_the_first_frame_is_already_deformed():
    r = run('''
# A constant bent clip cannot use its animated first frame as the rest denominator.
key(src, "thigh_r", 1, euler=(0, 35, 0))
soft = tube("soft", r=0.05, z0=0.2, z1=1.0, seg=8, rings=6, loc=(-0.08, 0, 0))
weights(soft, tgt, lambda c: {"pelvis": max(0.0, min(1.0, (0.8 - c.z) / 0.4)), "thigh_r": max(0.0, min(1.0, (c.z - 0.4) / 0.4))})
out = api.animation_retarget("src", "tgt", check_objects=[soft.name])
res(out)
''')
    assert r.rc == 0, r.out[-2000:]
    out = r.results[-1]
    assert out["ok"], out
    assert out["metrics"]["max_edge_stretch"]["soft"] > 1.01, out


def test_quality_names_the_unmapped_bones_that_actually_weight_checked_skin():
    r = run('''
plate = tube("plate", r=0.05, z0=1.46, z1=1.7, seg=8, rings=3)
weights(plate, tgt, lambda c: {"spine_01": 1.0})
pairs = api.animation_retarget("src", "tgt", dry_run=True)["mapping"]
pairs = [p for p in pairs if p["target"] != "spine_01"]
out = api.animation_retarget("src", "tgt", mapping=pairs, check_objects=[plate.name])
res(out)
''')
    assert r.rc == 0, r.out[-2000:]
    out = r.results[-1]
    assert out["ok"], out
    assert out["quality"]["unmapped_weighted_target"] == {"plate": ["spine_01"]}
    assert out["quality"]["stretch_threshold"] is None
    assert any("omitted" in warning for warning in out["warnings"])


def test_retarget_preserves_the_source_action_pose_and_scene_frame():
    r = run('''
bpy.context.scene.frame_set(3, subframe=0.25)
def snapshot():
    return {"action": src.animation_data.action.name, "frame": bpy.context.scene.frame_current, "subframe": bpy.context.scene.frame_subframe,
            "pose": [[float(x) for row in pb.matrix_basis for x in row] for pb in src.pose.bones]}
before = snapshot()
out = api.animation_retarget("src", "tgt")
res({"out": out, "before": before, "after": snapshot()})
''')
    assert r.rc == 0, r.out[-2000:]
    d = r.results[-1]
    assert d["out"]["ok"], d
    assert d["before"] == d["after"], d


def test_reported_rotation_difference_is_the_shortest_angle():
    r = run('''
from mathutils import Matrix
from mixar.modules.lampway_tools.features import animation
angle = animation._angle(Matrix.Rotation(math.radians(170), 4, 'Z'), Matrix.Rotation(math.radians(-170), 4, 'Z'))
res({"angle": angle})
''')
    assert r.rc == 0, r.out[-2000:]
    assert abs(r.results[-1]["angle"] - 20.0) < 0.001
