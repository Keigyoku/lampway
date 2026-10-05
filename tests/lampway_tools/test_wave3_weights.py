# SPDX-FileCopyrightText: 2026 Lampway contributors
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""weight_audit, weight_cleanup and weight_transfer (wiki/weight_audit, wiki/weight_cleanup, resources/weight_transfer_robust): in the real binary on synthetic rigs."""

import os
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent))
from blender_run import run_script  # noqa: E402

PRE = r'''
import bpy, bmesh, json, math, os, tempfile
from mathutils import Vector
from mixar.modules.lampway_tools import api
root = tempfile.mkdtemp(prefix="lw_w_"); api.settings_set(project_root=root)
bpy.ops.wm.read_factory_settings(use_empty=True)

def armature(name="rig", bones=(("spine_03", (0, 0, 0), (0, 0, 1), None), ("upperarm_l", (0, 0, 1), (0, 0, 2), "spine_03"))):
    arm = bpy.data.armatures.new(name); ob = bpy.data.objects.new(name, arm); bpy.context.scene.collection.objects.link(ob)
    bpy.context.view_layer.objects.active = ob; ob.select_set(True)
    bpy.ops.object.mode_set(mode="EDIT")
    for n, h, t, p in bones:
        b = arm.edit_bones.new(n); b.head, b.tail = h, t
        if p: b.parent = arm.edit_bones[p]
    bpy.ops.object.mode_set(mode="OBJECT"); ob.select_set(False)
    return ob

def tube(name, r=0.3, z0=0.0, z1=2.0, seg=16, rings=20, loc=(0, 0, 0)):
    bm = bmesh.new()
    for i in range(rings + 1):
        z = z0 + (z1 - z0) * i / rings
        for k in range(seg):
            a = 2 * math.pi * k / seg
            bm.verts.new((r * math.cos(a), r * math.sin(a), z))
    bm.verts.ensure_lookup_table()
    for i in range(rings):
        for k in range(seg):
            a, b = i * seg + k, i * seg + (k + 1) % seg
            bm.faces.new((bm.verts[a], bm.verts[b], bm.verts[b + seg], bm.verts[a + seg]))
    me = bpy.data.meshes.new(name); bm.to_mesh(me); bm.free()
    ob = bpy.data.objects.new(name, me); bpy.context.scene.collection.objects.link(ob); ob.location = loc
    return ob

def weights(ob, arm, fn):
    """fn(vertex co) -> {group: weight}; adds the groups and the armature modifier."""
    for v in ob.data.vertices:
        for g, w in fn(v.co).items():
            vg = ob.vertex_groups.get(g) or ob.vertex_groups.new(name=g)
            if w > 0: vg.add([v.index], w, "REPLACE")
    m = ob.modifiers.new("Armature", "ARMATURE"); m.object = arm

def res(r): print("RESULT " + json.dumps(r))
'''


def run(body, **kw):
    return run_script(PRE + body, timeout=300, **kw)


def test_a_rigid_plate_on_one_bone_has_zero_other_influence():
    r = run('''
arm = armature(); plate = tube("plate", r=0.2, z0=0.2, z1=0.8)
weights(plate, arm, lambda c: {"spine_03": 1.0})
a = api.weight_audit("audit", "plate", "rig", intended={"rigid_bone": "spine_03"})
res({"pass": a["pass"], "rigid": a["rigid_check"], "unw": a["unweighted_vertices"], "sums": a["sums_not_one"]})
''')
    assert r.rc == 0, r.out[-1200:]
    d = r.results[-1]
    assert d["pass"] is True and d["rigid"]["other_influence_vertices"] == 0 and d["unw"] == 0 and d["sums"] == 0


def test_layered_plates_with_competing_bones_are_flagged_with_the_hotspot_and_the_cap():
    r = run('''
arm = armature(); t = tube("sleeve", r=0.2, z0=0.5, z1=1.5)
weights(t, arm, lambda c: {"spine_03": max(0.0, min(1.0, (1.2 - c.z) / 0.4)), "upperarm_l": max(0.0, min(1.0, (c.z - 0.8) / 0.4))})
a = api.weight_audit("audit", "sleeve", "rig", intended={"rigid_bone": "spine_03"}, max_influences=1)
res({"pass": a["pass"], "over": a["over_influence_vertices"], "hot": a["hotspots"], "other": a["rigid_check"]["other_influence_vertices"]})
''')
    d = r.results[-1]
    assert d["pass"] is False and d["over"] > 0 and d["other"] > 0 and d["hot"] and d["hot"][0]["competing_bones"] == ["spine_03", "upperarm_l"], d


def test_a_left_group_on_a_right_side_mesh_is_flagged_and_the_correct_side_is_not():
    r = run('''
arm = armature(bones=(("upperarm_l", (0, 0, 0), (0, 0, 1), None), ("upperarm_r", (0, 0, 0), (0, 0, 1), None)))
wrong = tube("wrong", r=0.1, loc=(-0.6, 0, 0)); weights(wrong, arm, lambda c: {"upperarm_l": 1.0})
good = tube("good", r=0.1, loc=(-0.6, 0, 0)); weights(good, arm, lambda c: {"upperarm_r": 1.0})
a = api.weight_audit("audit", "wrong", "rig", side="right"); b = api.weight_audit("audit", "good", "rig", side="right")
res({"wrong": a["side_check"], "good": b["side_check"]})
''')
    d = r.results[-1]
    assert d["wrong"]["groups_on_wrong_side"] == ["upperarm_l"] and d["good"]["groups_on_wrong_side"] == []


def test_the_plan_recommends_rigid_for_a_pauldron_and_deforming_for_a_sleeve_and_flips_across_the_joint():
    r = run('''
arm = armature(); p = tube("pauldron", r=0.15, z0=0.3, z1=0.6); s = tube("sleeve", r=0.15, z0=0.6, z1=1.5)
for o in (p, s): o.modifiers.new("Armature", "ARMATURE").object = arm
a, b = api.weight_audit("plan", "pauldron", "rig"), api.weight_audit("plan", "sleeve", "rig")
p.location.z += 0.45          # the pauldron now straddles the joint at z = 1: the falsifier
c = api.weight_audit("plan", "pauldron", "rig")
res({"p": a["recommendation"], "pb": a["bone"], "s": b["recommendation"], "c": c["recommendation"], "span": b["joint_span"]})
''')
    d = r.results[-1]
    assert d["p"] == "rigid" and d["pb"] == "spine_03" and d["s"] == "deforming" and d["c"] == "deforming", d


def test_an_object_without_vertex_groups_is_told_to_bind_first():
    r = run('''
arm = armature(); t = tube("t"); res({"e": api.weight_audit("audit", "t", "rig").get("error")})
''')
    assert "bind first" in r.results[-1]["e"]


def test_cleanup_removes_only_the_named_bone_caps_at_four_and_renormalises_and_refuses_mass_zeroing():
    r = run('''
bones = tuple((f"b{i}", (0, 0, i), (0, 0, i + 1), None if i == 0 else f"b{i-1}") for i in range(6))
arm = armature(bones=bones); t = tube("t", z0=0, z1=6, rings=24)
weights(t, arm, lambda c: {f"b{i}": 1.0 + 0.01 * i for i in range(6)})            # six influences everywhere
a = api.weight_audit("audit", "t", "rig")
out = api.weight_cleanup("t", "rig", ops=[{"op": "limit", "max_influences": 4}])
c = bpy.data.objects[out["object"]]
counts = [len([g for g in v.groups if g.weight > 1e-6]) for v in c.data.vertices]
sums = [sum(g.weight for g in v.groups) for v in c.data.vertices]
rem = api.weight_cleanup("t", "rig", ops=[{"op": "remove_influence", "bone": "b5", "region": {"bbox": [[-1, -1, 5.0], [1, 1, 7]]}}])
c2 = bpy.data.objects[rem["object"]]; gi = {g.index: g.name for g in c2.vertex_groups}
inside = [sum(g.weight for g in v.groups if gi[g.group] == "b5") for v in c2.data.vertices if v.co.z >= 5.0]
outside = [sum(g.weight for g in v.groups if gi[g.group] == "b5") for v in c2.data.vertices if v.co.z < 5.0]
has_b5 = max(inside)
b4_after = max(abs(sum(g.weight for g in v.groups if gi[g.group] == "b4") - sum(g.weight for g in t.data.vertices[v.index].groups if t.vertex_groups[g.group].name == "b4")) for v in c2.data.vertices if v.co.z < 5.0)
mass = api.weight_cleanup("t", "rig", ops=[{"op": "remove_influence", "bone": "b5", "region": {"bbox": [[-1, -1, -1], [1, 1, 7]]}}])
res({"max": max(counts), "sum_dev": max(abs(s - 1) for s in sums), "has_b5": has_b5, "outside_b5_kept": min(outside) > 0, "b4_after": b4_after, "orig_untouched": "t_wclean" != "t", "mass": mass.get("error"), "ok": mass.get("ok")})
''')
    d = r.results[-1]
    assert d["max"] == 4 and d["sum_dev"] < 1e-3 and d["has_b5"] < 1e-6 and d["outside_b5_kept"] is True, d
    assert "not a cleanup" in (d["mass"] or "") and d["ok"] is False


def test_a_ten_percent_region_removal_passes_the_mass_check_and_a_rigid_op_gives_one_bone_weight_one():
    r = run('''
bones = (("a", (0, 0, 0), (0, 0, 1), None), ("b", (0, 0, 1), (0, 0, 2), "a"))
arm = armature(bones=bones); t = tube("t", z0=0, z1=2, rings=20)
weights(t, arm, lambda c: {"a": 0.5, "b": 0.5})
small = api.weight_cleanup("t", "rig", ops=[{"op": "remove_influence", "bone": "b", "region": {"bbox": [[-1, -1, 1.8], [1, 1, 2.1]]}}])
rig = api.weight_cleanup("t", "rig", ops=[{"op": "rigid", "bone": "a"}])
c = bpy.data.objects[rig["object"]]; gi = {g.index: g.name for g in c.vertex_groups}
ok = all(len(v.groups) == 1 and gi[v.groups[0].group] == "a" and abs(v.groups[0].weight - 1) < 1e-6 for v in c.data.vertices)
res({"small": small.get("ok"), "changed": small["ops_applied"][0]["vertices_changed"], "rigid": ok})
''')
    d = r.results[-1]
    assert d["small"] is True and d["changed"] > 0 and d["rigid"] is True


def test_transfer_copies_matched_weights_and_inpaints_what_has_no_match_smoothly():
    r = run('''
arm = armature()
body = tube("body", r=0.30, z0=0, z1=2.0, rings=40)
weights(body, arm, lambda c: {"spine_03": max(0.0, min(1.0, (1.4 - c.z) / 0.8)), "upperarm_l": max(0.0, min(1.0, (c.z - 0.6) / 0.8))})
# the piece hugs the body at r = 0.32, plus a bump of vertices far outside it (an armpit-like pocket)
piece = tube("piece", r=0.32, z0=0.2, z1=1.8, rings=32)
for v in piece.data.vertices:
    if abs(v.co.z - 1.0) < 0.12 and v.co.x > 0.2:
        v.co.x += 0.5                      # beyond max_distance of the body: nothing to match
out = api.weight_transfer("piece", "body", max_distance=0.1, engine="algorithmic")
p = bpy.data.objects[out["object"]]
gi = {g.index: g.name for g in p.vertex_groups}
W = [{gi[g.group]: g.weight for g in v.groups} for v in p.data.vertices]
sums = [sum(w.values()) for w in W]
far = [i for i, v in enumerate(piece.data.vertices) if abs(v.co.z - 1.0) < 0.12 and v.co.x > 0.7]
res({"ok": out["ok"], "matched": out["matched_fraction"], "inpainted": out["inpainted_vertices"], "sum_dev": max(abs(s - 1) for s in sums), "groups": sorted(gi.values()),
     "far_all_weighted": all(sums[i] > 0.99 for i in far), "far_mid": [round(W[i].get("spine_03", 0), 2) for i in far[:4]], "orig": "piece" in bpy.data.objects and len(bpy.data.objects["piece"].vertex_groups)})
''')
    assert r.rc == 0, r.out[-1500:]
    d = r.results[-1]
    assert d["ok"] and 0.8 < d["matched"] < 1.0 and d["inpainted"] > 0 and d["sum_dev"] < 1e-3 and d["far_all_weighted"], d
    assert d["groups"] == ["spine_03", "upperarm_l"] and d["orig"] == 0
    assert all(0.2 < x < 0.8 for x in d["far_mid"]), d          # the pocket at z = 1 is a blend, not a copy of one side


def test_transfer_refuses_a_source_without_groups_and_a_far_max_distance():
    r = run('''
arm = armature(); body = tube("body"); piece = tube("piece")
a = api.weight_transfer("piece", "body"); weights(body, arm, lambda c: {"spine_03": 1.0})
b = api.weight_transfer("piece", "body", max_distance=0.9)
res({"a": a.get("error"), "b": b.get("error")})
''')
    d = r.results[-1]
    assert "vertex group" in d["a"] and "0.5" in d["b"]


SCI = os.environ.get("LAMPWAY_PYTHON_SCIENCE")


@pytest.mark.skipif(not SCI, reason="LAMPWAY_PYTHON_SCIENCE (numpy scipy libigl robust_laplacian) is not set")
def test_the_robust_engine_matches_the_same_vertices_and_fills_the_pocket_with_a_biharmonic_blend():
    r = run('''
arm = armature()
body = tube("body", r=0.30, z0=0, z1=2.0, rings=40)
weights(body, arm, lambda c: {"spine_03": max(0.0, min(1.0, (1.4 - c.z) / 0.8)), "upperarm_l": max(0.0, min(1.0, (c.z - 0.6) / 0.8))})
piece = tube("piece", r=0.32, z0=0.2, z1=1.8, rings=32)
for v in piece.data.vertices:
    if abs(v.co.z - 1.0) < 0.12 and v.co.x > 0.2: v.co.x += 0.5
alg = api.weight_transfer("piece", "body", max_distance=0.1, engine="algorithmic")
rob = api.weight_transfer("piece", "body", max_distance=0.1, engine="robust", name="piece_rwt")
p = bpy.data.objects[rob["object"]]; gi = {g.index: g.name for g in p.vertex_groups}
W = [{gi[g.group]: g.weight for g in v.groups} for v in p.data.vertices]
sums = [sum(w.values()) for w in W]
far = [i for i, v in enumerate(piece.data.vertices) if abs(v.co.z - 1.0) < 0.12 and v.co.x > 0.7]
res({"ok": rob.get("ok"), "err": rob.get("error"), "engine": rob.get("engine"), "same_match": abs(rob["matched_fraction"] - alg["matched_fraction"]) < 1e-9, "sum_dev": max(abs(s - 1) for s in sums),
     "far_mid": [round(W[i].get("spine_03", 0), 2) for i in far[:4]]})
''', env={"LAMPWAY_PYTHON_SCIENCE": SCI})
    assert r.rc == 0, r.out[-1500:]
    d = r.results[-1]
    assert d["ok"] is True, d
    assert d["engine"] == "robust" and d["same_match"] and d["sum_dev"] < 1e-3 and all(0.2 < x < 0.8 for x in d["far_mid"]), d
