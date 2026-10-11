# SPDX-FileCopyrightText: 2026 Lampway contributors
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""IMPLEMENTATION_PLAN item 3 at the TOOL level (canon 07): weld first, region constraint, no zero-weight rows, bone
segments head -> continuation child. Each test was observed failing on the tool as it stood before the change."""

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent))
from blender_run import run_script  # noqa: E402
from canon_support import LOAD_OBJ, J, goldens  # noqa: E402,F401
from test_wave3_weights import PRE  # noqa: E402


def run(body, goldens=None):
    head = PRE + LOAD_OBJ + (f"GOLD = {str(goldens)!r}\n" if goldens else "")
    r = run_script(head + body, timeout=300)
    assert r.rc == 0, r.out[-1500:]
    return r.results[-1]


def test_c04_the_transfer_fill_welds_first_so_the_unmatched_island_is_weighted(goldens):
    d = run('''
import numpy as np
from mixar.modules.lampway_tools.features import weights as WT
ob = load_obj(GOLD + "/C04_weld_inpaint/piece.obj", "piece")
mt = json.load(open(GOLD + "/C04_weld_inpaint/matches.json"))
W = WT._harmonic_fill(ob.data, np.array(mt["matched"]), np.array(mt["W_matched"]))
V = np.array([v.co[:] for v in ob.data.vertices])
dup = [(i, j) for i in range(len(V)) for j in range(i + 1, len(V)) if np.abs(V[i] - V[j]).max() < 1e-9]
res({"unweighted": int((W.sum(1) < 1e-6).sum()), "dups": len(dup), "identical": all(np.array_equal(W[i], W[j]) for i, j in dup)})
''', goldens)
    assert d == {"unweighted": 0, "dups": 5, "identical": True}


# A torso (spine_03) and a left upper arm (upperarm_l, its lower-arm child under it) as two skinned tubes; the arm runs along +x.
BODY = '''
arm = armature(bones=(("spine_03", (0, 0, 1.0), (0, 0, 1.6), None), ("upperarm_l", (0.15, 0, 1.4), (0.55, 0, 1.4), "spine_03"),
                      ("lowerarm_l", (0.25, 0, 1.4), (0.45, 0, 1.4), "upperarm_l")))
torso = tube("torso", r=0.15, z0=1.0, z1=1.6, seg=32, rings=24)
arm_t = tube("arm_t", r=0.04, z0=0.15, z1=0.55, seg=16, rings=16)
arm_t.rotation_euler = (0, math.radians(90), 0); arm_t.location = (0, 0, 1.4)
bpy.context.view_layer.objects.active = arm_t; arm_t.select_set(True); bpy.ops.object.transform_apply(location=True, rotation=True); arm_t.select_set(False)
for ob_, g in ((torso, "spine_03"), (arm_t, "lowerarm_l")):
    vg = ob_.vertex_groups.new(name=g); vg.add([v.index for v in ob_.data.vertices], 1.0, "REPLACE")
bpy.context.view_layer.objects.active = torso; torso.select_set(True); arm_t.select_set(True); bpy.ops.object.join(); torso.select_set(False)
body = torso; body.name = "body"; m = body.modifiers.new("Armature", "ARMATURE"); m.object = arm
'''


def test_plan_refuses_an_unstamped_partial_native_helper_rig_before_weights():
    d = run(BODY.replace("lowerarm_l", "upperarm_twist_01_l") + '''
piece = tube("piece", r=0.05, z0=0.30, z1=0.40)
vg = piece.vertex_groups.new(name="piece"); vg.add([v.index for v in piece.data.vertices], 1.0, "REPLACE")
before = sorted(bpy.data.objects.keys())
p = api.fit_bind("plan", piece="piece", armature="rig", roles={"piece": "cloth"},
                 bind_overrides={"piece": {"bones": ["upperarm_l"]}}, out_dir="fb")
res({"plan": p, "unchanged": before == sorted(bpy.data.objects.keys()),
     "state_written": os.path.exists(os.path.join(root, "fb", "bind_state.json"))})
''')
    assert not d["plan"]["ok"] and "complete verified native topology" in d["plan"]["error"], d
    assert d["unchanged"] and not d["state_written"], d


def test_g07_5_a_sleeve_vertex_nearer_the_torso_takes_its_arm_bone_by_the_region_constraint():
    d = run(BODY + '''
# a shoulder slab (spine_03) 2 cm above the arm, facing up like the sleeve's top: the sleeve's top lies 1 cm over it and
# 3 cm over the arm, both surfaces normal-compatible: only the region constraint keeps the sleeve on its arm
bm = bmesh.new()
q = [bm.verts.new(p) for p in ((0.16, -0.1, 1.46), (0.45, -0.1, 1.46), (0.45, 0.1, 1.46), (0.16, 0.1, 1.46))]
bm.faces.new(q); slab_me = bpy.data.meshes.new("slab"); bm.to_mesh(slab_me); bm.free()
slab = bpy.data.objects.new("slab", slab_me); bpy.context.scene.collection.objects.link(slab)
sg = slab.vertex_groups.new(name="spine_03"); sg.add([v.index for v in slab.data.vertices], 1.0, "REPLACE")
bpy.context.view_layer.objects.active = body; body.select_set(True); slab.select_set(True); bpy.ops.object.join(); body.select_set(False)
sleeve = tube("sleeve", r=0.07, z0=0.20, z1=0.30, seg=16, rings=4)
sleeve.rotation_euler = (0, math.radians(90), 0); sleeve.location = (0, 0, 1.4)
bpy.context.view_layer.objects.active = sleeve; sleeve.select_set(True); bpy.ops.object.transform_apply(location=True, rotation=True); sleeve.select_set(False)
vg = sleeve.vertex_groups.new(name="sleeve"); vg.add([v.index for v in sleeve.data.vertices], 1.0, "REPLACE")
out = os.path.join(root, "fb")
p = api.fit_bind("plan", piece="sleeve", armature="rig", roles={"sleeve": "leather"}, bind_overrides={"sleeve": {"bones": ["upperarm_l"]}}, out_dir="fb")
assert p.get("ok"), p
w = api.fit_bind("weights", piece="sleeve", armature="rig", out_dir="fb", body_object="body")
rows = []
if w.get("ok"):
    fit = bpy.data.objects[w["object"]]
    names = {g.index: g.name for g in fit.vertex_groups}
    rows = [{names[g.group]: round(g.weight, 6) for g in v.groups if g.weight > 0} for v in fit.data.vertices]
res({"rows": rows, "ok": w.get("ok"), "error": w.get("error")})
''')
    assert d["ok"], d["error"]
    assert all(r == {"upperarm_l": 1.0} for r in d["rows"]), [r for r in d["rows"] if r != {"upperarm_l": 1.0}][:5]


def test_restrict_moves_a_disallowed_bones_weight_to_its_nearest_allowed_ancestor_never_a_zero_row():
    d = run(BODY + '''
cuff = tube("cuff", r=0.05, z0=0.30, z1=0.40, seg=16, rings=4)
cuff.rotation_euler = (0, math.radians(90), 0); cuff.location = (0, 0, 1.4)
bpy.context.view_layer.objects.active = cuff; cuff.select_set(True); bpy.ops.object.transform_apply(location=True, rotation=True); cuff.select_set(False)
vg = cuff.vertex_groups.new(name="cuff"); vg.add([v.index for v in cuff.data.vertices], 1.0, "REPLACE")
p = api.fit_bind("plan", piece="cuff", armature="rig", roles={"cuff": "cloth"}, bind_overrides={"cuff": {"bones": ["upperarm_l"]}}, out_dir="fb")
assert p.get("ok"), p
w = api.fit_bind("weights", piece="cuff", armature="rig", out_dir="fb", body_object="body")
rows = []
if w.get("ok"):
    fit = bpy.data.objects[w["object"]]
    names = {g.index: g.name for g in fit.vertex_groups}
    rows = [{names[g.group]: round(g.weight, 6) for g in v.groups if g.weight > 0} for v in fit.data.vertices]
res({"rows": rows, "ok": w.get("ok"), "error": w.get("error")})
''')
    assert d["ok"], d["error"]
    assert all(r == {"upperarm_l": 1.0} for r in d["rows"]), [r for r in d["rows"] if r != {"upperarm_l": 1.0}][:5]


def test_a_restrict_part_no_allowed_surface_reaches_is_refused_naming_its_zero_rows():
    d = run(BODY + '''
far = tube("far", r=0.05, z0=0.0, z1=0.1, seg=8, rings=2, loc=(0, 0.0, 0.2))
vg = far.vertex_groups.new(name="far"); vg.add([v.index for v in far.data.vertices], 1.0, "REPLACE")
p = api.fit_bind("plan", piece="far", armature="rig", roles={"far": "cloth"}, bind_overrides={"far": {"bones": ["upperarm_l"]}}, out_dir="fb")
assert p.get("ok"), p
w = api.fit_bind("weights", piece="far", armature="rig", out_dir="fb", body_object="body")
res({"ok": w.get("ok"), "error": w.get("error")})
''')
    assert not d["ok"] and "zero" in d["error"] and "far" in d["error"], d


def test_the_bone_a_piece_is_nearest_runs_head_to_its_continuation_child_never_along_an_imported_tail():
    d = run('''
# the bones' tails point UP, 90 deg off their limbs (Blender's glTF import of a UE rig); the arm runs along +x
arm = armature(bones=(("upperarm_l", (0.2, 0, 1.4), (0.2, 0, 1.6), None), ("lowerarm_l", (0.5, 0, 1.4), (0.5, 0, 1.6), "upperarm_l"),
                      ("hand_l", (0.75, 0, 1.4), (0.75, 0, 1.6), "lowerarm_l")))
piece = tube("piece", r=0.05, z0=0.36, z1=0.44, seg=12, rings=2)
piece.rotation_euler = (0, math.radians(90), 0); piece.location = (0, 0, 1.4)
bpy.context.view_layer.objects.active = piece; piece.select_set(True); bpy.ops.object.transform_apply(location=True, rotation=True); piece.select_set(False)
p = api.weight_audit("plan", "piece", "rig")
res({"bone": p.get("bone"), "bones": p.get("bones"), "error": p.get("error")})
''')
    assert d["bone"] == "upperarm_l", d
