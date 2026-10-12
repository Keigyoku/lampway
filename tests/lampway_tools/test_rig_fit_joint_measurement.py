# SPDX-FileCopyrightText: 2026 Lampway contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""Public own-rig centering, provenance and source-state preservation."""
from isolated_binary import run
from test_rig_fit_binding_audit import BIND


def test_public_centred_rig_refuses_unrelated_rig_and_stale_geometry(tmp_path):
    result = run(tmp_path, BIND + '''
other = arm.copy(); other.data = arm.data.copy()
bpy.context.collection.objects.link(other)
unrelated = call("rig_fit_template", example=source.name, joints="centre:rig:"+other.name, dry_run=True)
from mixar.modules.lampway_tools.features import rig_fit_measure as RM
original = RM.measure_own_rig
def stale(*args, **kwargs):
    doc = original(*args, **kwargs)
    doc["example_sha256"] = "0" * 64
    return doc
RM.measure_own_rig = stale
try:
    stale_result = call("rig_fit_template", example=source.name, joints="centre:rig:"+arm.name, dry_run=True)
finally:
    RM.measure_own_rig = original
print("RESULT", json.dumps({"unrelated": unrelated, "stale": stale_result}))
''')
    assert result.rc == 0, result.out[-3000:]
    row = result.results[0]
    assert not row["unrelated"]["ok"] and "does not deform" in str(row["unrelated"])
    assert not row["stale"]["ok"] and "does not match the example SHA256" in str(row["stale"])


def test_public_centred_rig_selector_is_bound_to_example_and_preserves_source(tmp_path):
    result = run(tmp_path, BIND + '''
before = {p.name: list(x for row in p.matrix_basis for x in row) for p in arm.pose.bones}
frame = (bpy.context.scene.frame_current, bpy.context.scene.frame_subframe)
dry = call("rig_fit_template", example=source.name, joints="centre:rig:"+arm.name, dry_run=True)
print("RESULT", json.dumps({"dry":dry,"pose_same":before=={p.name:list(x for row in p.matrix_basis for x in row) for p in arm.pose.bones},
    "frame_same":frame==(bpy.context.scene.frame_current,bpy.context.scene.frame_subframe),"position":arm.data.pose_position,
    "geometry_sha":_IO.geometry_sha256(source)}))
''')
    assert result.rc == 0, result.out[-3000:]
    row = result.results[0]
    assert row["dry"]["ok"], row
    measurement = row["dry"]["joints"]["measurement"]
    assert measurement["rays"] == 16 and measurement["iterations"] == 3
    assert row["dry"]["joints"]["example_sha256"] == row["geometry_sha"]
    assert row["dry"]["sha256"]["joints"]
    assert row["pose_same"] and row["frame_same"] and row["position"] == "POSE"


def test_measurement_rest_adapter_restores_pose_after_geometry_failure(tmp_path):
    result = run(tmp_path, BIND + '''
from mixar.modules.lampway_tools.features import rig_fit_measure as RM
from mathutils.bvhtree import BVHTree
arm.pose.bones["pelvis"].location=(10,0,0)
arm.pose.bones["pelvis"].keyframe_insert(data_path="location",frame=1)
bpy.context.scene.frame_set(1,subframe=0.25)
bpy.context.view_layer.update()
action=arm.animation_data.action; slot=arm.animation_data.action_slot
before={p.name:list(x for row in p.matrix_basis for x in row) for p in arm.pose.bones}
# A real evaluated source with invalid geometry extraction is the failure plant.
original=RM.centre
def broken(*args,**kwargs): raise RuntimeError("planted centering failure")
RM.centre=broken
try:
    try: RM.measure_own_rig(source,arm)
    except RuntimeError as exc: failed=str(exc)=="planted centering failure"
finally: RM.centre=original
print("RESULT",json.dumps({"failed":failed,"position":arm.data.pose_position,
    "pose_same":before=={p.name:list(x for row in p.matrix_basis for x in row) for p in arm.pose.bones},
    "action_same":action is arm.animation_data.action,"slot_same":slot==arm.animation_data.action_slot,
    "frame":[bpy.context.scene.frame_current,bpy.context.scene.frame_subframe]}))
''')
    assert result.rc == 0, result.out[-3000:]
    row = result.results[0]
    assert row["failed"] and row["position"] == "POSE"
    assert row["pose_same"] and row["action_same"] and row["slot_same"] and row["frame"] == [1,0.25]
