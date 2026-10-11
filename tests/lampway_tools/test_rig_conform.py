# SPDX-FileCopyrightText: 2026 Lampway contributors
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""rig_conform on a real armature (specs/canon/rig_tools/rig_conform.md; canon 16 B.4-B.7, 17), REAL binary: a Mixamo-named 22-bone rig with a
skinned mesh is conformed ON A COPY: UE names, spine_03/04 synthesized at the map's fractions, the reference hierarchy, frames from the joints
and the reference (the input roll cannot survive: R02's falsifier), heads bit-for-bit, vertex groups following their bones (a world-space
test pose finds a group that did not), the source untouched."""

import json
import sys
from pathlib import Path

import numpy as np
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent))
from features_support import run  # noqa: E402
from test_rig_tools import MIXAMO  # noqa: E402

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src/scripts"))
from mixar.modules.lampway_tools.rig_tools import core as RC  # noqa: E402


def test_native_source_copy_preserves_authored_rest_and_refuses_implicit_manny(tmp_path):
    from blender_run import run_script
    from test_native_complete_topology import PRE, BUILD
    r = run_script(PRE + BUILD + r'''
from mixar.modules.lampway_tools.features import rig_conform as CF
from mixar.modules.lampway_tools.features import rig_tools as RT
piece=skinned(arm,'native_skin')
arm.animation_data_create();action=bpy.data.actions.new('source_motion');arm.animation_data.action=action
arm.pose.bones['upperarm_l'].rotation_mode='QUATERNION';arm.pose.bones['upperarm_l'].keyframe_insert('rotation_quaternion',frame=1)
api.rig_inspect(armature=arm.name,profile='metahuman')
mapped=api.rig_map(armature=arm.name,profile='metahuman',out='native.map.json')
source_before={b.name:[list(row) for row in b.matrix_local] for b in arm.data.bones}
parents_before={b.name:b.parent.name if b.parent else None for b in arm.data.bones}
groups_before=[g.name for g in piece.vertex_groups]
weights_before=[[(g.group,g.weight) for g in v.groups] for v in piece.data.vertices]
rest_flags_before={b.name:(list(b.tail_local),b.use_connect,b.use_deform) for b in arm.data.bones}
poses_before={b.name:[list(row) for row in b.matrix_basis] for b in arm.pose.bones}
implicit=api.rig_conform(armature=arm.name,map='native.map.json',dry_run=False,out_name='implicit')
mismatch=api.rig_conform(armature=arm.name,map='native.map.json',reference='source_copy',convention='ue_axes',dry_run=False,out_name='mismatch')
merge=api.rig_conform(armature=arm.name,map='native.map.json',reference='source_copy',merge_weights={'head':'pelvis'},dry_run=False,out_name='merge')
done=api.rig_conform(armature=arm.name,map='native.map.json',reference='source_copy',dry_run=False,out_name='preserved')
out=bpy.data.objects.get('preserved')
checks={}
if out:
    mesh=bpy.data.objects[done['meshes_out'][0]]
    checks={'rest_same':source_before=={b.name:[list(row) for row in b.matrix_local] for b in out.data.bones},
      'parents_same':parents_before=={b.name:b.parent.name if b.parent else None for b in out.data.bones},
      'groups_same':groups_before==[g.name for g in mesh.vertex_groups],
      'weights_same':weights_before==[[(g.group,g.weight) for g in v.groups] for v in mesh.data.vertices],
      'rest_flags_same':rest_flags_before=={b.name:(list(b.tail_local),b.use_connect,b.use_deform) for b in out.data.bones},
      'own_data':out.data is not arm.data and mesh.data is not piece.data,
      'modifier_copy':any(m.type=='ARMATURE' and m.object is out for m in mesh.modifiers),
      'source_same':source_before=={b.name:[list(row) for row in b.matrix_local] for b in arm.data.bones},
      'source_pose_same':poses_before=={b.name:[list(row) for row in b.matrix_basis] for b in arm.pose.bones},
      'source_action_same':arm.animation_data.action is action,
      'copy_no_action':not out.animation_data,
      'refused_copies_absent':'mismatch' not in bpy.data.objects and 'merge' not in bpy.data.objects,
      'baseline_clean':not any('baseline' in o.name for o in bpy.data.objects)}
key=next(iter(RT.convention_angles(RT.read(arm))))
bpy.context.view_layer.objects.active=arm;bpy.ops.object.mode_set(mode='EDIT')
e=arm.data.edit_bones[key]
child=next(b for b in arm.data.edit_bones if b.parent and b.parent.name==key)
direction=(child.head-e.head).normalized()
axis=direction.cross(Vector((1,0,0)))
if axis.length<.1:axis=direction.cross(Vector((0,1,0)))
e.tail=e.head+axis.normalized()*.02
bpy.ops.object.mode_set(mode='OBJECT')
mixed_before={b.name:[list(row) for row in b.matrix_local] for b in arm.data.bones}
api.rig_inspect(armature=arm.name,profile='metahuman')
api.rig_map(armature=arm.name,profile='metahuman',out='mixed.map.json')
mixed=api.rig_conform(armature=arm.name,map='mixed.map.json',reference='source_copy',dry_run=False,out_name='mixed_copy')
checks['mixed_unchanged']=mixed_before=={b.name:[list(row) for row in b.matrix_local] for b in arm.data.bones} and 'mixed_copy' not in bpy.data.objects
res({'implicit':implicit,'mismatch':mismatch,'merge':merge,'mixed':mixed,'done':done,'checks':checks})
''', timeout=300)
    assert r.rc == 0, r.out[-2500:]
    got = r.results[-1]
    assert not got['implicit']['ok'] and 'explicit native reference' in got['implicit']['error'], got['implicit']
    assert got['done']['ok'], got['done']
    assert got['done']['reference_scope'] == 'source_preservation'
    assert got['done']['engine_bind_acceptance'].startswith('unverified')
    assert not got['mismatch']['ok'] and 'convention' in got['mismatch']['error']
    assert not got['merge']['ok'] and 'merge weights' in got['merge']['error']
    assert not got['mixed']['ok'] and 'convention is mixed' in got['mixed']['error'], got['mixed']
    assert got['checks'] and all(got['checks'].values()), got['checks']


@pytest.mark.parametrize('bad', ['partial', 'parent', 'mapping', 'synthesis', 'ik', 'offset', 'mixed', 'mismatch'])
def test_source_copy_plan_refuses_changes_and_unverified_convention(bad):
    import copy
    from test_native_complete_topology import PARENTS
    src = {'names':list(PARENTS),'parents':dict(PARENTS),
           'heads':{n:(0.,0.,0.) for n in PARENTS}, 'frames':{n:np.eye(3) for n in PARENTS},
           'lengths':{n:1. for n in PARENTS}}
    mapping, synth, offsets, ik, measured = {'pelvis':'pelvis'}, {}, {}, False, 'blender'
    if bad == 'partial': src['parents'].pop('pinky_03_in_l');src['names'].remove('pinky_03_in_l')
    if bad == 'parent': src['parents']['pinky_03_in_l']='ring_03_half_l'
    if bad == 'mapping': mapping={'pelvis':'head'}
    if bad == 'synthesis': synth={'spine_03':.5}
    if bad == 'ik': ik=True
    if bad == 'offset': offsets={'head':{'roll_deg':1.}}
    if bad == 'mixed': measured='mixed'
    if bad == 'mismatch': measured='ue_axes'
    before=copy.deepcopy(src)
    with pytest.raises(RC.RigRefused):
        RC.source_copy_plan(src,mapping,synth,'blender',measured,offsets,ik)
    assert src['parents']==before['parents'] and src['names']==before['names']
    assert all(np.array_equal(src['frames'][n],before['frames'][n]) for n in src['frames'])

SKIN = '''
def skinned(ob, roll=0.0):
    """A grid of vertices along every bone, each weighted 0.7 to its bone and 0.3 to the bone's parent (a real blend to deform)."""
    if roll:
        bpy.context.view_layer.objects.active = ob; bpy.ops.object.mode_set(mode="EDIT")
        for e in ob.data.edit_bones: e.roll += math.radians(roll)
        bpy.ops.object.mode_set(mode="OBJECT")
    me = bpy.data.meshes.new(ob.name + "_skin"); verts = []
    owners = []
    for b in ob.data.bones:
        for t in (0.25, 0.5, 0.75):
            p = ob.matrix_world @ (b.head_local.lerp(b.tail_local, t)); verts.append((p.x + 0.02, p.y - 0.03, p.z)); owners.append(b)
    me.from_pydata(verts, [], []); m = link(bpy.data.objects.new(ob.name + "_skin", me))
    for i, b in enumerate(owners):
        g = m.vertex_groups.get(b.name) or m.vertex_groups.new(name=b.name); g.add([i], 0.7, "REPLACE")
        if b.parent:
            q = m.vertex_groups.get(b.parent.name) or m.vertex_groups.new(name=b.parent.name); q.add([i], 0.3, "REPLACE")
    mod = m.modifiers.new("Armature", "ARMATURE"); mod.object = ob
    return m
import math
'''


def test_conform_writes_a_ue_named_copy_with_reference_frames_and_leaves_the_source_alone(tmp_path):
    r = run(tmp_path, MIXAMO + SKIN + '''
ob = mixamo(); skin = skinned(ob)
ob.animation_data_create(); act = bpy.data.actions.new("walk"); ob.animation_data.action = act
pb = ob.pose.bones["mixamorig:LeftArm"]; pb.rotation_mode = "QUATERNION"; pb.keyframe_insert("rotation_quaternion", frame=1)
call("rig_inspect", armature="mx")
call("rig_map", armature="mx", out="rig/mx.map.json")
dry = call("rig_conform", armature="mx", map="rig/mx.map.json")
done = call("rig_conform", armature="mx", map="rig/mx.map.json", dry_run=False)
again = call("rig_conform", armature="mx", map="rig/mx.map.json", dry_run=False)
out = bpy.data.objects.get("mx_ue")
bones = {b.name: {"head": list(b.head_local), "parent": b.parent.name if b.parent else None, "frame": [list(r) for r in b.matrix_local.to_3x3()]}
         for b in out.data.bones} if out else {}
src_heads = {b.name: list(b.head_local) for b in ob.data.bones}
copy = bpy.data.objects.get("mx_skin_mx_ue")
insp = call("rig_inspect", armature="mx_ue")
uea = call("rig_conform", armature="mx", map="rig/mx.map.json", dry_run=False, convention="ue_axes", out_name="mx_ux")
insp_ux = call("rig_inspect", armature="mx_ux")
fc = [f.data_path for l in act.layers for s in l.strips for bag in s.channelbags for f in bag.fcurves]
print("RESULT", json.dumps({"dry": dry, "done": done, "again": again, "bones": bones, "src_heads": src_heads, "insp": insp, "uea": uea, "insp_ux": insp_ux,
    "copy_groups": sorted(g.name for g in copy.vertex_groups) if copy else None, "src_groups": sorted(g.name for g in skin.vertex_groups),
    "src_bones": sorted(b.name for b in ob.data.bones), "src_fcurves": fc, "out_action": bool(out and out.animation_data and out.animation_data.action),
    "copy_mod": copy.modifiers["Armature"].object.name if copy else None, "baseline_left": sorted(o.name for o in bpy.data.objects if "baseline" in o.name)}))
''')
    assert r.rc == 0, r.out[-3000:]
    o = r.results[0]
    m = json.loads((tmp_path / "rig/mx.map.json").read_text())
    assert o["dry"]["ok"] and o["dry"]["dry_run"] is True and "mx_ue" not in o["bones"], o["dry"]
    d = o["done"]
    assert d["ok"] and d["dry_run"] is False and d["out"] == "mx_ue", d
    b = o["bones"]
    assert {"pelvis", "spine_01", "spine_02", "spine_03", "spine_04", "spine_05", "neck_01", "head", "hand_l", "hand_r", "foot_l"} <= set(b), sorted(b)
    assert not any(n.startswith("mixamorig:") and n.replace("mixamorig:", "") in ("Hips", "LeftHand") for n in b)
    present = [(s, o["src_heads"][m["map"][s]["source"]]) for s in RC.TORSO if s in m["map"]]
    want = RC.synthesize_chain(present, {s: v["fraction"] for s, v in m["synthesized"].items()})
    for s in ("spine_03", "spine_04"):
        assert np.allclose(b[s]["head"], want[s], atol=1e-6), (s, b[s]["head"], want[s])
    assert [b[s]["parent"] for s in ("spine_03", "spine_04", "spine_05")] == ["spine_02", "spine_03", "spine_04"]
    for s, v in m["map"].items():                                         # heads never move, bit for bit
        assert b[s]["head"] == o["src_heads"][v["source"]], s
    assert d["max_frame_error_deg"]["deg"] < 2e-3, d["max_frame_error_deg"]      # Blender's float32 rest (probe: <= 1.1e-3 deg near -Y)
    assert d["rest_vertex_drift_m"] <= d["rest_bar_m"] and d["posed_skin_drift_m"] <= 1e-5, d
    assert d["sha256"]["input"] and d["sha256"]["map"] and d["sha256"]["reference"] and d["sha256"]["output"], d["sha256"]
    assert o["insp"]["ok"] and o["insp"]["convention"]["class"] == "blender", o["insp"]["convention"]
    assert o["uea"]["ok"] and o["insp_ux"]["convention"]["class"] == "ue_axes", o["insp_ux"]["convention"]
    assert "hand_l" in o["copy_groups"] and "mixamorig:LeftHand" not in o["copy_groups"], o["copy_groups"]
    assert o["copy_mod"] == "mx_ue" and o["out_action"] is False and o["baseline_left"] == []
    # the source is never touched
    assert "mixamorig:LeftHand" in o["src_groups"] and "mixamorig:Hips" in o["src_bones"] and "pelvis" not in o["src_bones"]
    assert o["src_fcurves"] == ['pose.bones["mixamorig:LeftArm"].rotation_quaternion'] * 4, o["src_fcurves"]
    assert o["again"]["ok"] is False and "already exist" in o["again"]["error"], o["again"]


def test_the_conformed_frames_do_not_carry_the_input_roll(tmp_path):
    """R02's falsifier on real armatures: the same joints rolled 40 deg conform to the same frames (a Damped Track keeps the roll)."""
    r = run(tmp_path, MIXAMO + SKIN + '''
res = {}
for name, roll in (("a", 0.0), ("b", 40.0)):
    ob = mixamo(name=name); skinned(ob, roll)
    call("rig_inspect", armature=name); call("rig_map", armature=name, out=f"rig/{name}.map.json")
    res[name] = call("rig_conform", armature=name, map=f"rig/{name}.map.json", dry_run=False)
fa = {b.name: b.matrix_local.to_3x3() for b in bpy.data.objects["a_ue"].data.bones}
fb = {b.name: b.matrix_local.to_3x3() for b in bpy.data.objects["b_ue"].data.bones}
src = max((bpy.data.objects["a"].data.bones[n].matrix_local.to_3x3().to_quaternion().rotation_difference(
           bpy.data.objects["b"].data.bones[n].matrix_local.to_3x3().to_quaternion()).angle for n in ("mixamorig:LeftArm",)))
diff = max(fa[n].to_quaternion().rotation_difference(fb[n].to_quaternion()).angle for n in fa)
print("RESULT", json.dumps({"a": res["a"]["ok"], "b": res["b"].get("ok"), "berr": res["b"].get("error"), "src_deg": math.degrees(src), "out_deg": math.degrees(diff)}))
''')
    assert r.rc == 0, r.out[-3000:]
    o = r.results[0]
    assert o["a"] and o["b"], o
    assert abs(o["src_deg"] - 40.0) < 1e-3 and o["out_deg"] < 1e-3, o


def test_conform_refuses_the_uninspected_a_stale_map_and_an_unapplied_scale(tmp_path):
    r = run(tmp_path, MIXAMO + '''
ob = mixamo()
cold = call("rig_conform", armature="mx", map="rig/mx.map.json")
call("rig_inspect", armature="mx")
nomap = call("rig_conform", armature="mx", map="rig/none.map.json")
call("rig_map", armature="mx", out="rig/mx.map.json")
bpy.context.view_layer.objects.active = ob; bpy.ops.object.mode_set(mode="EDIT")
ob.data.edit_bones["mixamorig:LeftHand"].head.z += 0.01; bpy.ops.object.mode_set(mode="OBJECT")
call("rig_inspect", armature="mx")
stale = call("rig_conform", armature="mx", map="rig/mx.map.json")
s = mixamo(name="s", scale=0.01); call("rig_inspect", armature="s"); call("rig_map", armature="s", out="rig/s.map.json")
scaled = call("rig_conform", armature="s", map="rig/s.map.json")
print("RESULT", json.dumps({"cold": cold, "nomap": nomap, "stale": stale, "scaled": scaled}))
''')
    assert r.rc == 0, r.out[-3000:]
    o = r.results[0]
    assert o["cold"]["ok"] is False and "rig_inspect" in o["cold"]["error"], o["cold"]
    assert o["nomap"]["ok"] is False and "rig_map" in o["nomap"]["error"], o["nomap"]
    assert o["stale"]["ok"] is False and "different rest" in o["stale"]["error"], o["stale"]
    assert o["scaled"]["ok"] is False and "rig_normalize" in o["scaled"]["error"], o["scaled"]


def test_merge_weights_moves_only_the_named_group_and_ik_bones_stand_on_their_targets(tmp_path):
    r = run(tmp_path, MIXAMO + SKIN + '''
ob = mixamo(); skin = skinned(ob)
call("rig_inspect", armature="mx"); call("rig_map", armature="mx", out="rig/mx.map.json")
bad = call("rig_conform", armature="mx", map="rig/mx.map.json", dry_run=False, merge_weights={"nope": "foot_l"})
m = call("rig_conform", armature="mx", map="rig/mx.map.json", dry_run=False, merge_weights={"mixamorig:LeftToeBase": "foot_l"}, out_name="mx_m")
c = bpy.data.objects["mx_skin_mx_m"]
fl = c.vertex_groups["foot_l"].index
foot = sorted(round(g.weight, 6) for v in c.data.vertices for g in v.groups if g.group == fl)
k = call("rig_conform", armature="mx", map="rig/mx.map.json", dry_run=False, ik_bones=True, out_name="mx_ik", offsets={"hand_l": {"roll_deg": 15.0}})
a = bpy.data.objects["mx_ik"].data.bones
ik = {b.name: {"head": list(b.head_local), "parent": b.parent.name if b.parent else None} for b in a if b.name.startswith("ik_") or b.name in ("root", "pelvis", "foot_l", "hand_r")}
print("RESULT", json.dumps({"bad": bad, "m": m, "groups": sorted(g.name for g in c.vertex_groups), "foot": foot, "k": k, "ik": ik,
                            "src_groups": sorted(g.name for g in skin.vertex_groups)}))
''')
    assert r.rc == 0, r.out[-3000:]
    o = r.results[0]
    assert o["bad"]["ok"] is False and "vertex group 'nope" in o["bad"]["error"], o["bad"]
    m = o["m"]
    assert m["ok"] and m["merged_groups"] == {"mixamorig:LeftToeBase": {"to": "foot_l", "vertices": 3}}, m.get("merged_groups")
    assert "ball_l" not in o["groups"] and "ball_r" in o["groups"] and m["posed_skin_drift_m"] <= 1e-5, o["groups"]
    assert o["foot"] == [0.7, 0.7, 0.7, 1.0, 1.0, 1.0], o["foot"]        # the foot's own 0.7 x 3; the toe's 0.7 + the foot's 0.3 x 3
    assert "mixamorig:LeftToeBase" in o["src_groups"], "the source mesh keeps its groups"
    k, ik = o["k"], o["ik"]
    assert k["ok"] and k["frames"]["hand_l"] != m["frames"]["hand_l"], k
    assert ik["root"]["head"] == [0.0, 0.0, 0.0] and ik["pelvis"]["parent"] == "root" and "root" in k["synthesized"], ik
    assert ik["ik_foot_l"]["head"] == ik["foot_l"]["head"] and ik["ik_foot_l"]["parent"] == "ik_foot_root" and ik["ik_foot_root"]["parent"] == "root"
    assert ik["ik_hand_gun"]["head"] == ik["hand_r"]["head"] and ik["ik_hand_r"]["parent"] == "ik_hand_gun" and ik["ik_hand_gun"]["parent"] == "ik_hand_root"


def test_hidden_rig_conform_restores_visibility_and_reports_actionable_runtime_error(tmp_path):
    """G3: actual skinned armature, hidden both ways; source and copies retain flags."""
    from isolated_binary import run as isolated_run
    r = isolated_run(tmp_path, MIXAMO + SKIN + '''
ob = mixamo(); skin = skinned(ob)
call("rig_inspect", armature="mx")
call("rig_map", armature="mx", out="rig/mx.map.json")
ob.hide_viewport = True; ob.hide_set(True)
skin.hide_viewport = True; skin.hide_set(True)
before = [ob.hide_viewport, ob.hide_get(), skin.hide_viewport, skin.hide_get()]
done = call("rig_conform", armature="mx", map="rig/mx.map.json", dry_run=False)
after = [ob.hide_viewport, ob.hide_get(), skin.hide_viewport, skin.hide_get()]
out = bpy.data.objects.get("mx_ue"); mesh = bpy.data.objects.get("mx_skin_mx_ue")
visibility = [out.hide_viewport, out.hide_get(), mesh.hide_viewport, mesh.hide_get()] if out and mesh else []
from mixar.modules.lampway_tools.features import rig_conform as rf
original = rf.conform
rf.conform = lambda *a, **kw: (_ for _ in ()).throw(RuntimeError("Synthetic mode refusal"))
refused = call("rig_conform", armature="mx", map="rig/mx.map.json", dry_run=False, out_name="retry")
rf.conform = original
print("RESULT", json.dumps({"done": done, "before": before, "after": after, "visibility": visibility, "refused": refused}))
''')
    assert r.rc == 0, r.out[-3000:]
    receipt = r.results[0]
    assert receipt["done"]["ok"], receipt
    assert receipt["before"] == receipt["after"] == receipt["visibility"] == [True] * 4
    assert receipt["done"]["posed_skin_drift_m"] <= 1e-5
    assert not receipt["refused"]["ok"]
    assert any("lampway_rig_inspect" in h and "mx" in h for h in receipt["refused"]["help"]), receipt
